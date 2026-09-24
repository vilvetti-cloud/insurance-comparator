"""Two stages share downloaded bytes, never redownload before extraction."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.casco_pipeline import CascoCollectionPipeline
from db import init_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["check", "analyze"])
    parser.add_argument("--directory", type=Path, default=Path("work/casco"))
    parser.add_argument("--insurer", action="append")
    args = parser.parse_args()
    if not os.getenv("DATABASE_URL") or not init_db():
        print("Database unavailable", file=sys.stderr)
        return 2
    pipeline = CascoCollectionPipeline()
    if args.stage == "check":
        result = pipeline.checksum_check(directory=args.directory, insurer_slugs=args.insurer)
        if os.getenv("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
                handle.write(f"pending={len(result['pending'])}\n")
        print(json.dumps({"pending": len(result["pending"]), "unchanged": len(result["unchanged"]),
                          "errors": result["errors"]}, ensure_ascii=False))
        # Still analyze reachable documents when a different source is unavailable.
        return 0
    result = pipeline.analyze(directory=args.directory)
    summary = json.dumps(result, ensure_ascii=False, indent=2)
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write("## CASCO document collection\n\n```json\n" + summary + "\n```\n")
    if result["degraded"]:
        print("::warning::CASCO analysis degraded; previous verified values preserved")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
