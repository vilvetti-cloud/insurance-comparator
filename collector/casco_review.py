"""Explicit, bounded review of cached extractions; daily collection never retries these."""
import re
from collector.casco_document import ParsedDocument
from collector.casco_validation import normalize, validate_fact
from collector.casco_provider import get_provider, ProviderUnavailable
from collector.registry import get_insurer
from database.repositories.casco_revision import CascoRevisionRepository


def locate_quote(fact, document):
    """Correct exact page/section metadata, never the quotation or answer."""
    if not isinstance(fact, dict):
        return fact
    def correct(item):
        if not isinstance(item, dict) or not isinstance(item.get('exact_quote'), str):
            return item
        quote = normalize(item['exact_quote'])
        result = dict(item)
        if len(quote) >= 25:
            pages = [n for n, text in document.pages.items() if quote in normalize(text)]
            if len(pages) == 1:
                result['page'] = pages[0]
        if not result.get('section'):
            table_option = re.match(r'\|\s*(ГЭП\d+)\s*\|', item['exact_quote'], re.I)
            if table_option:
                result['section'] = table_option.group(1)
        return result
    if isinstance(fact.get('evidence'), list) and fact['evidence']:
        evidence = [correct(item) for item in fact['evidence']]
        return dict(fact, evidence=evidence,
                    **{key: evidence[0].get(key) for key in ('exact_quote', 'page', 'section')})
    return correct(fact)


def review_insurer(insurer, *, apply=False, use_ai=False, repository=None, provider=None):
    if use_ai and not apply:
        raise ValueError('AI repair requires explicit apply mode')
    repository = repository or CascoRevisionRepository()
    result = {'insurer': insurer, 'ai_requests': 0, 'published_fields': [], 'documents': []}
    for row in repository.review_documents(insurer):
        parsed = row['parsed']
        if not parsed or parsed.get('parser') != 'docling' or parsed.get('warning'):
            result['documents'].append({'url': row['url'], 'status': 'no_valid_cached_parse'})
            continue
        document = ParsedDocument({int(n): t for n, t in parsed['pages'].items()},
                                  structure=parsed.get('structure', {}))
        candidates, fields, details, failed = [], {}, [], []
        for old in row['candidates']:
            key = old['field_key']
            fields[key] = {'id': old['field_id']}
            if old['validation_status'] == 'PASS':
                details.append({'field': key, 'status': 'already_passed'})
                continue
            fact = locate_quote(old['payload'], document)
            verdict = validate_fact(key, fact, document, insurer=insurer, source_url=row['url'])
            candidates.append((key, fact, verdict))
            details.append({'field': key, 'before': old['reason'], 'after': verdict.reason,
                            'value': fact.get('value') if isinstance(fact, dict) else None,
                            'evidence': fact})
            if not verdict.passed:
                failed.append(key)
        if use_ai and failed and result['ai_requests'] == 0:
            provider = provider or get_provider()
            result['model'] = getattr(provider, 'model', provider.name)
            if not provider.available:
                result['provider_error'] = 'GEMINI_API_KEY missing'
            else:
                result['ai_requests'] += 1
                try:
                    facts = provider.extract(document=document, company=get_insurer(insurer).name,
                        source_url=row['url'], field_keys=failed)
                    replacements = {}
                    for key in failed:
                        fact = locate_quote(facts.get(key, {}), document)
                        verdict = validate_fact(key, fact, document, insurer=insurer, source_url=row['url'])
                        replacements[key] = (key, fact, verdict)
                        details.append({'field': key, 'after_ai': verdict.reason,
                            'value': fact.get('value'), 'evidence': fact,
                            'diagnostics': getattr(provider, 'diagnostics', {}).get(key)})
                    candidates = [replacements.get(key, (key, fact, verdict)) for key, fact, verdict in candidates]
                except ProviderUnavailable as exc:
                    result['provider_error'] = str(exc)
        if apply and candidates:
            passed = repository.publish(source={'id': row['source_id'], 'source_level': row['source_level']},
                document={'id': row['document_id']}, checksum=row['checksum'], parsed=parsed,
                provider='explicit_review', candidates=candidates, fields=fields, repair=True)
            result['published_fields'].extend(sorted(passed))
        result['documents'].append({'url': row['url'], 'checksum': row['checksum'], 'fields': details})
    return result

