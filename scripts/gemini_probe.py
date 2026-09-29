"""Bounded API diagnostics: no database, insurance documents, or retries."""
import json
import os
from pathlib import Path
import re
import sys
import time
import requests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collector.casco_provider import error_summary, FACT_SCHEMA


def probe(key, model, client=requests):
    if not key:
        return {'error': 'GEMINI_API_KEY missing', 'requests': []}
    if not re.fullmatch(r'gemini-[a-zA-Z0-9.-]+', model):
        return {'error': 'Invalid model identifier', 'requests': []}
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}'
    headers = {'x-goog-api-key': key}
    report = {'model': model, 'requests': []}
    for stage in ('model_access', 'plain', 'structured'):
        started = time.monotonic()
        try:
            if stage == 'model_access':
                response = client.get(url, headers=headers, timeout=(10, 30))
            else:
                config = {'temperature': 0, 'maxOutputTokens': 256}
                prompt = 'Reply with the single word OK.'
                if stage == 'structured':
                    config.update(responseMimeType='application/json', responseJsonSchema=FACT_SCHEMA)
                    prompt = 'Return value="OK", exact_quote="probe", page=1, section="test". No other text.'
                response = client.post(url + ':generateContent', headers=headers,
                    json={'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': config},
                    timeout=(10, 60))
            entry = {'stage': stage, 'http_status': response.status_code,
                     'seconds': round(time.monotonic() - started, 2)}
            if response.status_code != 200:
                entry['error'] = error_summary(response)
            else:
                body = response.json()
                if stage == 'model_access':
                    entry['generate_supported'] = 'generateContent' in body.get('supportedGenerationMethods', [])
                else:
                    candidates = body.get('candidates', [])
                    candidate = candidates[0] if candidates else {}
                    entry['finish_reason'] = candidate.get('finishReason')
                    answer = ''.join(p.get('text', '') for p in candidate.get('content', {}).get('parts', []))
                    if stage == 'plain':
                        entry['valid'] = answer.strip() == 'OK'
                    else:
                        try:
                            entry['valid'] = json.loads(answer) == {'value': 'OK', 'exact_quote': 'probe', 'page': 1, 'section': 'test'}
                        except ValueError:
                            entry['valid'] = False
                    entry['usage'] = {k: v for k, v in body.get('usageMetadata', {}).items()
                                      if k in {'promptTokenCount', 'candidatesTokenCount', 'totalTokenCount', 'thoughtsTokenCount'} and type(v) is int}
            report['requests'].append(entry)
            response.close()
            # Authentication/quota failures cannot be fixed by changing prompt shape.
            if response.status_code in (400, 401, 403, 404, 429):
                break
        except (requests.RequestException, ValueError, TypeError) as exc:
            report['requests'].append({'stage': stage, 'error': type(exc).__name__})
            break
    return report


if __name__ == '__main__':
    report = probe(os.getenv('GEMINI_API_KEY'), os.getenv('GEMINI_MODEL') or 'gemini-3.8-flash')
    summary = json.dumps(report, ensure_ascii=False, indent=2)
    print(summary)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write('## Gemini API probe\n\n```json\n' + summary + '\n```\n')
    raise SystemExit(0 if len(report['requests']) == 3 and all(r.get('http_status') == 200 and r.get('valid', True) for r in report['requests']) else 1)
