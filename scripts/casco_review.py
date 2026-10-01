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


def review_selected(insurer, *, apply=False, ai=False, reviewer=review_insurer):
    if insurer == 'all' and ai:
        raise ValueError('Run AI review for one insurer at a time to respect provider limits')
    slugs = [i.slug for i in INSURERS] if insurer == 'all' else [insurer]
    reports = [reviewer(slug, apply=apply, use_ai=ai) for slug in slugs]
    return {'insurers': reports, 'published_fields': sum(len(r['published_fields']) for r in reports),
            'provider_errors': [r['provider_error'] for r in reports if r.get('provider_error')]}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--insurer', required=True, choices=[i.slug for i in INSURERS] + ['all'])
    p.add_argument('--apply', action='store_true')
    p.add_argument('--ai', action='store_true')
    args = p.parse_args()
    if not os.getenv('DATABASE_URL') or not init_db():
        raise SystemExit('Database unavailable')
    report = review_selected(args.insurer, apply=args.apply, ai=args.ai)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    Path('casco-review-report.json').write_text(text, encoding='utf-8')
    summary = {'insurers': len(report['insurers']), 'published_fields': report['published_fields'],
               'provider_errors': report['provider_errors'], 'full_report': 'casco-review-report.json'}
    print(json.dumps(summary, ensure_ascii=False))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write('## Explicit CASCO review\n\n```json\n' + json.dumps(summary, ensure_ascii=False, indent=2) + '\n```\n')
    if report['provider_errors']:
        raise SystemExit(1)
