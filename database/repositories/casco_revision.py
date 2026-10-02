"""CASCO revisions and atomic publication into the existing UI tables."""
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .base import BaseRepository
from core.condition_audit import audit_condition


class CascoRevisionRepository(BaseRepository):
    def review_documents(self, insurer):
        """Current pinned revisions only; no historical document can repair today's card."""
        from collector.casco_sources import sources_for
        urls = [s.url for s in sources_for(insurer)]
        rows = self.fetch_all('''SELECT r.*,s.url,s.source_level,d.id AS document_id
            FROM casco_document_revisions r
            JOIN sources s ON s.id=r.source_id AND s.checksum=r.checksum
            JOIN companies co ON co.id=s.company_id
            JOIN documents d ON d.source_id=s.id AND d.checksum=r.checksum
            WHERE co.slug=%s AND s.url=ANY(%s)
            ORDER BY s.source_level,r.id DESC''', (insurer, urls))
        for row in rows:
            row['candidates'] = self.fetch_all('''SELECT DISTINCT ON (c.field_id)
                c.*,f.field_key FROM casco_review_candidates c
                JOIN comparison_fields f ON f.id=c.field_id
                WHERE c.revision_id=%s ORDER BY c.field_id,c.id DESC''', (row['id'],))
        return rows

    def reuse_identical_content(self, source_id, checksum, parsed):
        from collector.casco_document import content_fingerprint
        if parsed.get('parser') != 'docling' or parsed.get('warning') or not parsed.get('pages'):
            return False
        with self.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute('SELECT checksum FROM sources WHERE id=%s FOR UPDATE', (source_id,))
                current = cur.fetchone()
                if not current or current['checksum'] != checksum:
                    raise ValueError('Source changed during content comparison')
                cur.execute('''SELECT parsed FROM casco_document_revisions
                    WHERE source_id=%s AND status='complete' AND checksum<>%s
                    ORDER BY analyzed_at DESC NULLS LAST,id DESC LIMIT 1''', (source_id,checksum))
                previous = cur.fetchone()
                old = previous and previous['parsed']
                if (not old or old.get('parser') != 'docling' or old.get('warning')
                        or not old.get('pages')
                        or content_fingerprint(old['pages']) != content_fingerprint(parsed['pages'])):
                    return False
                # Evidence remains attached to the original physical document/pages.
                cur.execute('''INSERT INTO casco_document_revisions(source_id,checksum,status,parsed,provider,analyzed_at)
                    VALUES (%s,%s,'complete',%s,'content_equal',NOW())
                    ON CONFLICT(source_id,checksum) DO UPDATE SET status='complete',parsed=EXCLUDED.parsed,
                    provider='content_equal',error=NULL,analyzed_at=NOW()''', (source_id,checksum,Jsonb(parsed)))
                cur.execute('UPDATE sources SET casco_analyzed_checksum=%s WHERE id=%s', (checksum,source_id))
                return True

    def page_state(self, insurer, url):
        return self.fetch_one('SELECT checksum,links FROM casco_page_watch WHERE insurer=%s AND url=%s',
                              (insurer, url))

    def save_page_state(self, insurer, url, checksum, links):
        self.execute('''INSERT INTO casco_page_watch(insurer,url,checksum,links) VALUES (%s,%s,%s,%s)
            ON CONFLICT(insurer,url) DO UPDATE SET checksum=EXCLUDED.checksum,
            links=EXCLUDED.links,checked_at=NOW()''', (insurer,url,checksum,Jsonb(links)))

    def attempted(self, source_id, checksum):
        return bool(self.fetch_one("SELECT id FROM casco_document_revisions WHERE source_id=%s AND checksum=%s AND status<>'complete'",
                                  (source_id,checksum)))

    def review_summary(self):
        return self.fetch_all(
            """SELECT co.slug AS insurer, f.field_key AS field, c.reason, COUNT(*) AS count
               FROM casco_review_candidates c
               JOIN casco_document_revisions r ON r.id=c.revision_id
               JOIN sources s ON s.id=r.source_id AND s.checksum=r.checksum
               JOIN companies co ON co.id=s.company_id
               JOIN comparison_fields f ON f.id=c.field_id
               WHERE c.validation_status='FAIL'
               GROUP BY co.slug,f.field_key,c.reason
               ORDER BY co.slug,f.field_key,c.reason""")

    def cached_parse(self, source_id, checksum):
        row = self.fetch_one(
            "SELECT parsed FROM casco_document_revisions WHERE source_id=%s AND checksum=%s",
            (source_id, checksum))
        parsed = row and row["parsed"]
        if (isinstance(parsed, dict) and parsed.get("parser") == "docling"
                and not parsed.get("warning") and parsed.get("pages")):
            return parsed
        return None

    def quarantine_legacy_snapshots(self, company_id, snapshots):
        """Retain historical hints outside active cards; preserve real page evidence."""
        signatures = {(s.field_key, s.value, s.evidence) for s in snapshots}
        with self.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """SELECT c.id,c.value,f.field_key,s.source_type,
                              e.text_fragment,e.document_id,e.page_number
                       FROM conditions c JOIN comparison_fields f ON f.id=c.field_id
                       JOIN products p ON p.id=f.product_id
                       LEFT JOIN sources s ON s.id=c.source_id
                       LEFT JOIN LATERAL (
                         SELECT * FROM evidence WHERE condition_id=c.id ORDER BY id DESC LIMIT 1
                       ) e ON TRUE
                       WHERE p.company_id=%s AND p.product_type='casco' AND c.status='active'
                       FOR UPDATE OF c""", (company_id,))
                for row in cur.fetchall():
                    if row["document_id"] is not None or row["page_number"] is not None:
                        continue
                    known = (row["field_key"], row["value"], row["text_fragment"]) in signatures
                    if row["source_type"] == "official_snapshot" or known:
                        cur.execute("UPDATE conditions SET status='diagnostic' WHERE id=%s", (row["id"],))
                        cur.execute(
                            """INSERT INTO change_log(entity_type,entity_id,field_name,
                               old_value,new_value,reason)
                               VALUES ('condition',%s,'status','active','diagnostic','snapshot_is_not_evidence')""",
                            (row["id"],))


    def completed(self, source_id: int, checksum: str) -> bool:
        row = self.fetch_one(
            "SELECT r.status FROM casco_document_revisions r JOIN sources s ON s.id=r.source_id "
            "WHERE r.source_id=%s AND r.checksum=%s AND s.casco_analyzed_checksum=r.checksum",
            (source_id, checksum),
        )
        return bool(row and row["status"] == "complete")

    def save_degraded(self, *, source_id, checksum, reason, parsed=None):
        self.execute(
            """INSERT INTO casco_document_revisions(source_id, checksum, status, error, parsed)
               VALUES (%s,%s,'degraded',%s,%s)
               ON CONFLICT(source_id,checksum) DO UPDATE SET
                 status=CASE WHEN casco_document_revisions.status='complete' THEN 'complete' ELSE 'degraded' END,
                 error=EXCLUDED.error, checked_at=NOW(),
                 parsed=COALESCE(EXCLUDED.parsed,casco_document_revisions.parsed)""",
            (source_id, checksum, reason, Jsonb(parsed) if parsed else None),
        )

    def publish(self, *, source, document, checksum, parsed, provider, candidates, fields,
                repair=False):
        """All evidence, candidates, active values and completion marker commit together."""
        with self.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Serialize even the first condition insert for this product.
                for field_id in sorted(row["id"] for row in fields.values()):
                    cur.execute("SELECT id FROM comparison_fields WHERE id=%s FOR UPDATE", (field_id,))
                cur.execute(
                    """INSERT INTO casco_document_revisions
                         (source_id,checksum,status,parsed,provider)
                       VALUES (%s,%s,'processing',%s,%s)
                       ON CONFLICT(source_id,checksum) DO UPDATE SET checked_at=NOW()
                       RETURNING id,status""",
                    (source["id"], checksum, Jsonb(parsed), provider),
                )
                revision = cur.fetchone()
                cur.execute("SELECT casco_analyzed_checksum,checksum FROM sources WHERE id=%s FOR UPDATE", (source["id"],))
                source_state = cur.fetchone()
                if source_state["checksum"] and source_state["checksum"] != checksum:
                    raise ValueError("Source changed during analysis; stale candidate not published")
                if source_state["casco_analyzed_checksum"] == checksum and not repair:
                    return set()
                passed = set()
                for key, fact, verdict in candidates:
                    if repair:
                        cur.execute('''SELECT validation_status FROM casco_review_candidates
                            WHERE revision_id=%s AND field_id=%s ORDER BY id DESC LIMIT 1''',
                            (revision['id'], fields[key]['id']))
                        previous = cur.fetchone()
                        # This explicit mode can repair FAIL candidates only, never
                        # replace a successful field or create a new extraction.
                        if not previous or previous['validation_status'] != 'FAIL':
                            continue
                    cur.execute(
                        """INSERT INTO casco_review_candidates
                             (revision_id,field_id,payload,validation_status,reason)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (revision["id"], fields[key]["id"], Jsonb(fact),
                         "PASS" if verdict.passed else "FAIL", verdict.reason),
                    )
                    if not verdict.passed:
                        continue
                    cur.execute(
                        """SELECT c.*, s.source_type, e.document_id, e.page_number, e.text_fragment
                           FROM conditions c LEFT JOIN sources s ON s.id=c.source_id LEFT JOIN LATERAL
                             (SELECT (array_agg(document_id ORDER BY id DESC))[1] AS document_id,
                                     (array_agg(page_number ORDER BY id DESC))[1] AS page_number,
                                     string_agg(text_fragment, E'\n\n' ORDER BY id DESC) AS text_fragment
                              FROM evidence WHERE condition_id=c.id) e ON TRUE
                           WHERE c.field_id=%s AND c.status='active'
                           ORDER BY c.source_level NULLS LAST,c.id DESC""",
                        (fields[key]["id"],),
                    )
                    current_rows = list(cur.fetchall())
                    # A supplement cannot overwrite rules; multiple same-level sources
                    # with different values require review rather than last-write-wins.
                    conflict = any(
                        row.get("verification_status") == "verified"
                        and audit_condition(key, row.get("value"), row.get("text_fragment"),
                            source_level=row.get("source_level"), source_type=row.get("source_type"),
                            confidence=float(row["confidence"]) if row.get("confidence") is not None else None,
                            verification_status=row.get("verification_status")).status in {"confirmed", "conditional"}
                        and row.get("source_id") != source["id"]
                        and (row.get("source_level") or 4) <= source["source_level"]
                        and row.get("value") != fact["value"]
                        for row in current_rows
                    )
                    if conflict:
                        cur.execute(
                            """UPDATE casco_review_candidates SET validation_status='FAIL',
                               reason='conflicting_or_stronger_verified_source'
                               WHERE revision_id=%s AND field_id=%s""",
                            (revision["id"], fields[key]["id"]),
                        )
                        continue
                    for row in current_rows:
                        cur.execute(
                            """INSERT INTO condition_versions
                               (condition_id,value,source_id,document_id,page_number,text_fragment,verification_status)
                               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                            (row["id"], row["value"], row.get("source_id"), row.get("document_id"),
                             row.get("page_number"), row.get("text_fragment"), row["verification_status"]),
                        )
                    cur.execute("UPDATE conditions SET status='archived' WHERE field_id=%s AND status='active'",
                                (fields[key]["id"],))
                    cur.execute(
                        """INSERT INTO conditions
                           (field_id,source_id,value,source_level,confidence,status,verification_status,checked_at)
                           VALUES (%s,%s,%s,%s,1.0,'active','verified',NOW()) RETURNING id""",
                        (fields[key]["id"], source["id"], fact["value"], source["source_level"]),
                    )
                    condition_id = cur.fetchone()["id"]
                    # Keep all independently checked passages in the existing
                    # evidence table. Insert the primary last for older UI
                    # queries that display only the latest evidence row.
                    for item in reversed(fact.get("evidence") or [fact]):
                        cur.execute(
                            """INSERT INTO evidence
                               (condition_id,source_id,document_id,page_number,text_fragment,verification_status,
                                verified_at,verified_by,section,document_checksum)
                               VALUES (%s,%s,%s,%s,%s,'verified',NOW(),'casco-evidence-gate',%s,%s)""",
                            (condition_id, source["id"], document["id"], item["page"],
                             item["exact_quote"], item["section"], checksum),
                        )
                    cur.execute(
                        """INSERT INTO change_log(entity_type,entity_id,field_name,new_value,reason)
                           VALUES ('condition',%s,'value',%s,'casco_document_PASS')""",
                        (condition_id, fact["value"]),
                    )
                    passed.add(key)
                cur.execute(
                    """UPDATE casco_document_revisions SET status='complete',parsed=%s,
                       provider=%s,error=NULL,analyzed_at=NOW() WHERE id=%s""",
                    (Jsonb(parsed), provider, revision["id"]),
                )
                if parsed.get("parser") == "docling" and not parsed.get("warning"):
                    cur.execute("UPDATE sources SET casco_analyzed_checksum=%s WHERE id=%s",
                                (checksum, source["id"]))
                else:
                    cur.execute("UPDATE casco_document_revisions SET status='degraded',error='parser_degraded' WHERE id=%s",
                                (revision["id"],))
                return passed

