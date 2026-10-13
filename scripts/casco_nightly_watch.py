from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "work" / "casco-nightly-watch"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collector.casco_pipeline import CascoCollectionPipeline
from collector.casco_document import CascoDocumentParser
from db import init_db


def main() -> int:
    if not init_db():
        raise RuntimeError("Database initialization failed; check DATABASE_URL")

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    pipeline = CascoCollectionPipeline(parser=CascoDocumentParser())
    manifest = pipeline.checksum_check(
        directory=OUT_ROOT,
        track_run=True,
        retry_failed=False,
        watch=True,
    )
    report = pipeline.analyze(directory=OUT_ROOT, manifest=manifest)
    result = {
        "mode": "nightly_checksum_first",
        "source_documents_pending": len(manifest.get("pending", [])),
        "unchanged_documents": len(manifest.get("unchanged", [])),
        "source_errors": manifest.get("errors", []),
        "deferred": manifest.get("deferred", []),
        "page_watch": manifest.get("pages", []),
        "analysis": report,
    }
    (OUT_ROOT / "nightly-report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "pending": result["source_documents_pending"],
        "unchanged": result["unchanged_documents"],
        "source_errors": len(result["source_errors"]),
        "degraded": len(report.get("degraded", [])),
        "page_changes": sum(p.get("status") == "changed" for p in result["page_watch"]),
        "unregistered_candidates": sum(len(p.get("unregistered_candidates", [])) for p in result["page_watch"]),
        "run_id": manifest.get("run_id"),
    }, ensure_ascii=False, indent=2))
    return 1 if result["source_errors"] or report.get("degraded") else 0


if __name__ == "__main__":
    raise SystemExit(main())
