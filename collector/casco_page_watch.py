"""Deterministic official-page link monitoring; no search or LLM calls."""
import hashlib
import json
import re
from urllib.parse import urljoin, urldefrag, urlsplit
from bs4 import BeautifulSoup
from collector.casco_sources import official_url
from collector.casco_sources import sources_for


def page_urls(config):
    urls = [config.casco_url or config.official_url]
    urls.extend(u for u in config.official_doc_urls
                if not urlsplit(u).path.lower().endswith('.pdf') and '/cms/assets/' not in u)
    return tuple(dict.fromkeys(urls))


def document_links(body, page_url, insurer):
    soup = BeautifulSoup(body, 'html.parser')
    links = {}
    for a in soup.find_all('a', href=True):
        url = urldefrag(urljoin(page_url, a['href']))[0]
        if not official_url(insurer, url):
            continue
        path = urlsplit(url).path.lower()
        title = ' '.join(a.get_text(' ', strip=True).split())
        # Keep the surrounding label: dates/edition notices often sit outside <a>.
        context = ' '.join(a.parent.get_text(' ', strip=True).split())[:1600]
        if path.endswith('.pdf') or '/cms/assets/' in path:
            links[url] = {'url': url, 'title': title, 'context': context}
    return sorted(links.values(), key=lambda link: link['url'])


def link_fingerprint(links):
    return hashlib.sha256(json.dumps(links, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def casco_link(link):
    # Parent containers may list hundreds of unrelated policies. They provide
    # edition context, but must never make an unrelated link a CASCO candidate.
    return bool(re.search(r'каско|kasko|casco|\bgap\b|\bгэп\b|автотранспорт|транспортных средств',
                          link['title'] + ' ' + link['url'], re.I))


def watch_pages(config, fetcher, repository):
    results = []
    for url in page_urls(config):
        try:
            fetched = fetcher.fetch(url, referer=config.official_url)
            if not official_url(config.slug, fetched.url):
                raise ValueError('Page redirect left official hosts')
            links = document_links(fetched.body, fetched.url, config.slug)
            if not links:
                raise ValueError('No document links: page may require JavaScript or be blocked')
            previous = repository.page_state(config.slug, url)
            checksum = link_fingerprint(links)
            changed = previous is None or previous['checksum'] != checksum
            repository.save_page_state(config.slug, url, checksum, links)
            pinned = {s.url for s in sources_for(config.slug)}
            candidates = [link for link in links if link['url'] not in pinned
                and casco_link(link)]
            results.append({'insurer': config.slug, 'page': url,
                'status': 'changed' if changed else 'unchanged',
                'links': links if changed else [],
                'unregistered_candidates': candidates,
                'selection': 'review_required' if changed else 'none'})
        except Exception as exc:
            # Failed checks never replace the last successful snapshot.
            results.append({'insurer': config.slug, 'page': url,
                'status': 'unavailable', 'reason': type(exc).__name__})
    return results

