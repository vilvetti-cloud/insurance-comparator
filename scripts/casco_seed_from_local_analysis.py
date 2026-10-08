from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

import fitz
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_PATH = ROOT / "reports" / "local-casco-analysis" / "analysis.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.casco_sources import sources_for
from collector.casco_version import CASCO_EXTRACTOR_VERSION
from core.catalog import KASKO_FIELDS
from core.condition_audit import audit_condition
from database.repositories.company import CompanyRepository
from database.repositories.document import DocumentRepository
from database.repositories.field import ComparisonFieldRepository
from database.repositories.product import ProductRepository
from database.repositories.source import SourceRepository
from collector.registry import get_insurer
from db import _connect, init_db


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text or "").split())


def page_numbers(value: Any) -> list[int]:
    if value is None:
        return []
    nums = [int(x) for x in re.findall(r"\d+", str(value))]
    return sorted(set(n for n in nums if n > 0))


def exact_quote_location(pdf_path: Path, quote: str | None, requested_pages: Any) -> tuple[int | None, str | None]:
    if not isinstance(quote, str) or not quote.strip():
        return None, "missing_quote"
    if "..." in quote or "…" in quote:
        return None, "quote_contains_ellipsis"

    wanted = normalize(quote)
    if len(wanted) < 25:
        return None, "quote_too_short"

    doc = fitz.open(pdf_path)
    try:
        candidates = page_numbers(requested_pages)
        if not candidates:
            candidates = list(range(1, len(doc) + 1))

        found: list[int] = []
        for page_number in candidates:
            if not 1 <= page_number <= len(doc):
                continue
            text = normalize(doc[page_number - 1].get_text("text") or "")
            if wanted in text:
                found.append(page_number)

        if len(found) == 1:
            return found[0], "exact"
        if len(found) > 1:
            return found[0], "exact_multiple_pages"
        return None, "quote_not_found_on_claimed_pages"
    finally:
        doc.close()


def load_analysis() -> dict:
    if not ANALYSIS_PATH.is_file():
        raise FileNotFoundError(f"Missing {ANALYSIS_PATH}")
    return json.loads(ANALYSIS_PATH.read_text(encoding="utf-8"))


def seed_insurer(slug: str, analysis: dict, *, force: bool = False) -> dict[str, Any]:
    insurer = get_insurer(slug)
    pdf_path = ROOT / "data" / "sources" / slug / "technical.pdf"
    if not pdf_path.is_file():
        raise FileNotFoundError(f"{slug}: missing {pdf_path}")

    body = pdf_path.read_bytes()
    if not body.startswith(b"%PDF"):
        raise ValueError(f"{slug}: local technical.pdf is not a PDF")
    checksum = hashlib.sha256(body).hexdigest()
    source_pin = sources_for(slug)[0]

    company = CompanyRepository().upsert(
        name=insurer.name,
        slug=insurer.slug,
        short_name=insurer.short_name,
        official_url=insurer.official_url,
    )
    product = ProductRepository().upsert(
        company_id=company["id"],
        name="КАСКО",
        slug="casco",
        product_type="casco",
    )
    fields = {
        field["key"]: ComparisonFieldRepository().upsert(
            product_id=product["id"],
            field_key=field["key"],
            label=field["label"],
            category=field["category"],
            sort_order=field["sort_order"],
        )
        for field in KASKO_FIELDS
    }
    source = SourceRepository().upsert(
        company_id=company["id"],
        url=source_pin.url,
        title="Закреплённый официальный документ КАСКО — локальный seed",
        source_type="pdf",
        source_level=1,
        status="active",
        http_status=200,
        checksum=checksum,
        success=True,
    )
    document = DocumentRepository().upsert(
        source_id=source["id"],
        document_url=source_pin.url,
        title="Правила/условия КАСКО — локальный seed",
        checksum=checksum,
    )

    answers = ((analysis.get("results") or {}).get(slug) or {}).get("answers") or {}
    if not answers:
        raise ValueError(f"{slug}: no answers in local analysis")

    conn = _connect()
    if conn is None:
        raise RuntimeError("DATABASE_URL is not configured or database is unavailable")

    result = {
        "insurer": slug,
        "checksum": checksum,
        "fields_total": len(KASKO_FIELDS),
        "verified": 0,
        "needs_review": 0,
        "not_found": 0,
        "skipped_existing": 0,
        "details": {},
    }

    with conn:
        with conn.cursor(row_factory=dict_row) as cur:
            current = cur.execute(
                """SELECT status FROM casco_document_revisions
                   WHERE source_id=%s AND checksum=%s AND extractor_version=%s
                   ORDER BY id DESC LIMIT 1""",
                (source["id"], checksum, CASCO_EXTRACTOR_VERSION),
            ).fetchone()
            if current and current["status"] == "complete" and not force:
                result["skipped_existing"] = len(KASKO_FIELDS)
                result["status"] = "already_seeded"
                return result

            cur.execute(
                """INSERT INTO casco_document_revisions
                   (source_id, checksum, status, parsed, provider, extractor_version)
                   VALUES (%s,%s,'processing',%s,%s,%s)
                   ON CONFLICT(source_id,checksum) DO UPDATE SET
                     status='processing',
                     parsed=EXCLUDED.parsed,
                     provider=EXCLUDED.provider,
                     extractor_version=EXCLUDED.extractor_version,
                     error=NULL,
                     checked_at=NOW()
                   RETURNING id""",
                (
                    source["id"],
                    checksum,
                    Jsonb({
                        "parser": "local_seed",
                        "source": str(ANALYSIS_PATH.relative_to(ROOT)),
                        "pdf": str(pdf_path.relative_to(ROOT)),
                        "model": analysis.get("model"),
                    }),
                    "local-manus-seed",
                    CASCO_EXTRACTOR_VERSION,
                ),
            )
            revision_id = cur.fetchone()["id"]

            for field in KASKO_FIELDS:
                key = field["key"]
                answer = answers.get(key) or {}
                status = answer.get("status")
                if status == "found":
                    status = "answered"

                value = answer.get("value") or answer.get("answer")
                quote = answer.get("quote") or answer.get("exact_quote")
                requested_page = answer.get("page")
                explanation = answer.get("explanation") or answer.get("reason") or ""
                missing_information = answer.get("missing_information") or ""

                if status == "not_found" or not value:
                    result["not_found"] += 1
                    result["details"][key] = {
                        "status": "not_found",
                        "verification_status": None,
                        "reason": explanation,
                    }
                    continue

                located_page, locate_status = exact_quote_location(
                    pdf_path, quote, requested_page
                )
                exact = located_page is not None and locate_status.startswith("exact")

                verification_status = "verified" if status == "answered" and exact else "needs_review"
                confidence = 1.0 if verification_status == "verified" else 0.70

                audit = audit_condition(
                    key,
                    str(value),
                    quote if exact else quote,
                    source_level=1,
                    source_type="pdf",
                    confidence=confidence,
                    verification_status=verification_status,
                    trust_official_context=exact,
                )

                if verification_status == "verified" and audit.status not in {"confirmed", "conditional"}:
                    verification_status = "needs_review"
                    confidence = 0.70

                cur.execute(
                    """UPDATE conditions SET status='archived'
                       WHERE field_id=%s AND source_id=%s AND status='active'""",
                    (fields[key]["id"], source["id"]),
                )

                meta = {
                    "answer_status": status,
                    "explanation": explanation,
                    "missing_information": missing_information,
                    "seed_provider": "local-manus-seed",
                    "seed_model": analysis.get("model"),
                    "seed_evidence_check": locate_status,
                }

                cur.execute(
                    """INSERT INTO conditions
                       (field_id,source_id,value,value_json,source_level,confidence,status,
                        verification_status,checked_at)
                       VALUES (%s,%s,%s,%s,1,%s,'active',%s,NOW())
                       RETURNING id""",
                    (
                        fields[key]["id"],
                        source["id"],
                        str(value),
                        Jsonb(meta),
                        confidence,
                        verification_status,
                    ),
                )
                condition_id = cur.fetchone()["id"]

                if quote:
                    cur.execute(
                        """INSERT INTO evidence
                           (condition_id,source_id,document_id,page_number,text_fragment,
                            verification_status,verified_at,verified_by,section,document_checksum)
                           VALUES (%s,%s,%s,%s,%s,%s,
                                   CASE WHEN %s THEN NOW() ELSE NULL END,
                                   %s,NULL,%s)""",
                        (
                            condition_id,
                            source["id"],
                            document["id"],
                            located_page or (page_numbers(requested_page)[0] if page_numbers(requested_page) else None),
                            str(quote),
                            verification_status,
                            verification_status == "verified",
                            "local-manus-seed" if verification_status == "verified" else "local-manus-seed-review",
                            checksum,
                        ),
                    )

                result["details"][key] = {
                    "status": status,
                    "verification_status": verification_status,
                    "quality_status": audit.status,
                    "evidence_check": locate_status,
                    "page": located_page or requested_page,
                }
                if verification_status == "verified":
                    result["verified"] += 1
                else:
                    result["needs_review"] += 1

            cur.execute(
                """UPDATE sources
                   SET casco_analyzed_checksum=%s,
                       casco_analyzed_version=%s,
                       last_checked_at=NOW(),
                       last_success_at=NOW()
                   WHERE id=%s""",
                (checksum, CASCO_EXTRACTOR_VERSION, source["id"]),
            )
            cur.execute(
                """UPDATE casco_document_revisions
                   SET status='complete', analyzed_at=NOW(), error=NULL
                   WHERE id=%s""",
                (revision_id,),
            )

    result["status"] = "seeded"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed CASCO facts from the checked-in Manus local analysis")
    parser.add_argument("--insurer", action="append", dest="insurers")
    parser.add_argument("--force", action="store_true", help="Rebuild seed rows for the selected insurers")
    parser.add_argument("--check-only", action="store_true", help="Validate report/files without writing the database")
    args = parser.parse_args()

    if not init_db():
        print("Database initialization failed", file=sys.stderr)
        return 2

    analysis = load_analysis()
    requested = args.insurers or list((analysis.get("results") or {}).keys())
    known = {item.slug for item in [get_insurer(i.slug) for i in [get_insurer(s) for s in requested]]} if requested else set()
    # Re-resolve through registry so an accidental unknown slug fails early.
    for slug in requested:
        get_insurer(slug)

    results = []
    errors = []

    for slug in requested:
        try:
            if args.check_only:
                pdf_path = ROOT / "data" / "sources" / slug / "technical.pdf"
                if not pdf_path.is_file():
                    raise FileNotFoundError(str(pdf_path))
                results.append({
                    "insurer": slug,
                    "status": "check_ok",
                    "checksum": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                })
            else:
                results.append(seed_insurer(slug, analysis, force=args.force))
        except Exception as exc:
            errors.append({
                "insurer": slug,
                "error": f"{type(exc).__name__}: {str(exc)[:500]}",
            })

    report = {
        "source": str(ANALYSIS_PATH.relative_to(ROOT)),
        "model": analysis.get("model"),
        "request_count": analysis.get("request_count"),
        "results": results,
        "errors": errors,
    }
    out = ROOT / "work" / "casco-seed"
    out.mkdir(parents=True, exist_ok=True)
    (out / "seed-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
