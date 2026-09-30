"""Read one cached T-insurance document, write a diagnostic report, never publish."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.casco_document import ParsedDocument
from collector.casco_pilot import analyze_pilot
from collector.casco_provider import get_provider
from database.repositories.casco_revision import CascoRevisionRepository


def run(repository, provider):
    for row in repository.review_documents('t-insurance'):
        parsed = row.get('parsed') or {}
        if parsed.get('parser') != 'docling' or parsed.get('warning') or not parsed.get('pages'):
            continue
        document = ParsedDocument({int(n): t for n, t in parsed['pages'].items()})
        report = analyze_pilot(document, provider)
        report.update(insurer='t-insurance', source_url=row['url'], checksum=row['checksum'])
        return report
    return {'status': 'no_cached_document', 'ai_requests': 0, 'fields': {}}


if __name__ == '__main__':
    report = run(CascoRevisionRepository(), get_provider())
    text = json.dumps(report, ensure_ascii=False, indent=2)
    Path('casco-pilot-report.json').write_text(text, encoding='utf-8')
    print(text)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write('## T-insurance answer-first pilot\n\n```json\n' + text + '\n```\n')
    raise SystemExit(0 if report['status'] == 'analyzed' else 1)
