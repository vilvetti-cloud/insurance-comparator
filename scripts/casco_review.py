"""Inspect or repair cached review candidates without a new document collection."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.casco_review import review_insurer
from collector.registry import INSURERS
from db import init_db


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--insurer', required=True, choices=[i.slug for i in INSURERS])
    p.add_argument('--apply', action='store_true')
    p.add_argument('--ai', action='store_true')
    args = p.parse_args()
    if not os.getenv('DATABASE_URL') or not init_db():
        raise SystemExit('Database unavailable')
    report = review_insurer(args.insurer, apply=args.apply, use_ai=args.ai)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write('## Explicit CASCO review\n\n```json\n' + text + '\n```\n')
    if report.get('provider_error'):
        raise SystemExit(1)
