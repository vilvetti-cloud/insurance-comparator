"""Read one cached T-insurance document, write a diagnostic report, never publish."""
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.casco_document import ParsedDocument
from collector.casco_pilot import analyze_pilot, get_pilot_provider, select_pages, FIELD_KEYS
from database.repositories.casco_revision import CascoRevisionRepository


def run(repository, provider, field=None):
    for row in repository.review_documents('t-insurance'):
        parsed = row.get('parsed') or {}
        if parsed.get('parser') != 'docling' or parsed.get('warning') or not parsed.get('pages'):
            continue
        document = ParsedDocument({int(n): t for n, t in parsed['pages'].items()})
        selected_pages = list(document.pages)
        if field:
            document, selected_pages = select_pages(document, field)
            if document is None:
                return {'status': 'no_relevant_pages', 'ai_requests': 0, 'fields': {},
                        'field': field, 'next_step': 'search_official_site'}
        report = analyze_pilot(document, provider, field_keys=(field,)) if field else analyze_pilot(document, provider)
        report.update(insurer='t-insurance', source_url=row['url'], checksum=row['checksum'])
        report['selected_pages'] = selected_pages
        report['selected_text_chars'] = len(document.text)
        report['document_scope'] = 'selected_pages' if field else 'whole_document'
        return report
    return {'status': 'no_cached_document', 'ai_requests': 0, 'fields': {}}


def run_all(repository, provider):
    """Initial one-insurer collection: one bounded question per field."""
    results = {}
    for field in FIELD_KEYS:
        result = run(repository, provider, field=field)
        results[field] = result
        if result['status'] in ('provider_error', 'provider_unavailable'):
            break  # A quota or service failure cannot be fixed by asking nine more questions.
    return {'insurer': 't-insurance', 'status': 'complete' if len(results) == len(FIELD_KEYS)
            and all(r['status'] == 'analyzed' for r in results.values()) else 'incomplete',
            'ai_requests': sum(r.get('ai_requests', 0) for r in results.values()), 'questions': results}


if __name__ == '__main__':
    repository, provider = CascoRevisionRepository(), get_pilot_provider()
    field = os.getenv('PILOT_FIELD') or None
    report = run_all(repository, provider) if field == 'all' else run(repository, provider, field)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    Path('casco-pilot-report.json').write_text(text, encoding='utf-8')
    print(text)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write('## T-insurance answer-first pilot\n\n```json\n' + text + '\n```\n')
    raise SystemExit(0 if report['status'] in ('analyzed', 'complete') else 1)
