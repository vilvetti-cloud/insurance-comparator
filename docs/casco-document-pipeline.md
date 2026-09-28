# CASCO document collection

The public CascoCollectionPipeline import now uses pinned official documents.
The existing UI tables and field keys remain unchanged.

## Daily processing

At 03:00 UTC, scripts/casco_documents.py check downloads every pinned document,
checks the final host and PDF signature, and hashes the original bytes with SHA-256.
Successfully analyzed unchanged revisions skip parsing and AI entirely.
The downloaded bytes pass to the analyze stage through a local manifest, with
a second hash check before parsing. No PDF is downloaded twice in a run.

Docling is installed only for pending documents when GEMINI_API_KEY is available.
It exports per-page Markdown and its complete structured document into the revision
record. Physical page numbers start at 1. A pypdf fallback is explicitly review-only.

One Gemini structured-output request per document returns all ten fields with
value, exact_quote, page and section (all null for missing evidence).
Set GEMINI_API_KEY as a repository Actions secret. GEMINI_MODEL is an optional
repository variable; the default is gemini-3.8-flash. No Groq key is needed.
Missing keys, API limits, invalid output and parser failures explicitly defer
analysis and preserve verified values. Unchanged failed attempts require an explicit retry. No silent truncation,
per-field calls, or automatic provider switching occurs.

The gate checks official host, parser status, verbatim normalized quotation on
the claimed page, section presence, numeric values/units, field relevance,
contract conditions and semantic/polarity contradictions. It is a conservative
rule-based gate, not a proof of arbitrary natural-language entailment. Ambiguous
clauses should remain review candidates. Whitespace normalization is permitted;
word deletion and fuzzy quote matching are not.

PASS candidates publish value and evidence in one transaction. FAIL candidates
live in casco_review_candidates, never in the active conditions. Old conditions
and evidence are archived on a successful replacement. Conflicting equal/stronger
sources are retained for review instead of overwriting one another. Existing
legacy snapshots are not promoted; the snapshot module is diagnostic data only
and is absent from the daily path. Historical snapshot-only conditions are moved idempotently to diagnostic status.
This also recognizes exact known snapshot value/quote pairs after legacy shared
source metadata changes. Conditions with real document/page evidence are preserved.
A change-log entry records each quarantine; no row is deleted.

The sources.casco_analyzed_checksum marker is written only when analysis completes,
separately from the latest downloaded checksum. Degraded runs cannot poison the
skip cache. A source reverting to an older revision is processed again.
Review-only successful extraction is complete (the same rejected output is not
repeated every day); operator reprocessing can clear that source's analyzed marker
after fixing extraction/validation.

## Operations

### Cost controls and source-page monitoring

Daily runs check the configured product/document pages before pinned PDFs. The
`casco_page_watch` table retains the last successful list of official PDF links,
labels and surrounding edition/date notices. A changed URL or label is reported
without any LLM call. New CASCO/GAP links remain visible as unregistered candidates
until the registry is updated; they are **not automatically selected as current rules**.
Archive/product ambiguity needs review. No-links responses are reported as unavailable
and never overwrite a successful snapshot. Pages rendered only through JavaScript
need a site-specific adapter; homepage fallbacks do not guarantee edition coverage.

Normal scheduled runs process at most one previously unattempted document. A failed
unchanged revision is queued for explicit retry instead of consuming tokens each day.
The first HTTP 429 stops further provider calls in that run. Safe quota identifiers
and retry delays are recorded, not raw error bodies. HTTP 5xx permits at most three
attempts per document. Code pushes run CI only; they no longer trigger paid collection.

For initial backfill or retries use workflow_dispatch with `insurer`, `retry_failed`
and `max_documents` (0–20), or `check --retry-failed --max-documents 5`.
Use `--max-documents 0` for a zero-AI check. Analyze still writes the check report.
All ten explicit business questions live in `collector/casco_questions.py`.

If PDF bytes change, Docling text is compared against the latest completed revision.
Only whitespace/Unicode normalization and page boundaries are ignored. Identical
text skips AI and preserves the original evidence/page references. Changed wording,
numbers or punctuation still triggers full-document extraction within the budget.
Selective per-field extraction and automatic promotion of newly discovered URLs
are not yet implemented.

- Run all stages: python scripts/run_collection.py
- Check only: python scripts/casco_documents.py check --insurer reso
- Analyze downloaded pending files: python scripts/casco_documents.py analyze
- Examine work/casco/report.json and the Actions summary/artifact.
- Review candidates: join casco_review_candidates with casco_document_revisions
  and comparison_fields; payload preserves all four original evidence fields.
- For a confirmed 404/410 only, run scripts/casco_recover_source.py --insurer SLUG
  --url PINNED_URL. It independently rechecks the failure and proposes official
  search results. Verify the document/product/version and change registry.py.
  Search snippets never become evidence. 403/429/timeouts do not trigger search.

Database setup uses CREATE TABLE / ADD COLUMN IF NOT EXISTS. Migration runs on
the normal init_db path. Production data is not deleted. Only identifiable synthetic snapshot hints are quarantined.
Docling remains out of requirements.txt and the web deployment.

## Validation

Unit coverage includes unchanged hash, absent secrets, replaced bytes, one AI
request, exact quote/page/section, numeric mismatch, polarity and snapshot exclusion.
CI runs PostgreSQL integration tests for idempotent migration, preserving old
verified values/evidence, atomic rollback and document reversion. A separate real
Docling smoke test confirms page provenance on a two-page PDF.

References:
- https://docling-project.github.io/docling/reference/docling_document/
- https://ai.google.dev/api/generate-content
# Explicit review of cached extractions

`Explicit CASCO review` is a manual workflow, separate from daily monitoring.
Select one insurer. With `apply=false` it reports validation results without AI
or card writes. `apply=true` can repair failed candidates whose exact quotation
has one unambiguous page in the stored Docling document. It never changes the
quotation or value to manufacture evidence. With `ai=true`, at most one document
is submitted with questions/schema restricted to failed fields. Full document
context is retained to avoid losing exclusions; token-level excerpt retrieval
is not implemented. Already-passed fields are excluded and protected again
inside the publication transaction. A concurrent checksum change rejects repair.
No Docling installation or PDF download is needed for this cached-review mode.

CLI: `python scripts/casco_review.py --insurer t-insurance` (read-only), then add
`--apply` for deterministic repairs or `--apply --ai` for one targeted extraction.
