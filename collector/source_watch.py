"""Nightly check that the official rules on insurer sites still match our copies.

No database and no AI: every file listed in docs/source-urls.md is downloaded
from the insurer site and compared byte for byte (SHA-256) with the copy in
data/sources/. Insurer pages are scanned for new CASCO documents. The result is
written to data/source-check.json, which the site reads.

A changed file or a new document never changes the agreed answers by itself:
it is reported, and the owner decides when the answers are re-checked.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable

from collector.casco_page_watch import casco_link, document_links, page_urls
from collector.casco_sources import official_url
from collector.registry import INSURERS

ROOT = Path(__file__).resolve().parents[1]
SOURCES_TABLE = ROOT / "docs" / "source-urls.md"
SOURCES_DIR = ROOT / "data" / "sources"
STATUS_FILE = ROOT / "data" / "source-check.json"
MOSCOW = timezone(timedelta(hours=3))


@dataclass(frozen=True)
class SourceFile:
    company: str
    file: str
    url: str


def load_source_table(path: Path = SOURCES_TABLE) -> list[SourceFile]:
    """Rows of the «Компания | Файл | Ссылка» table in docs/source-urls.md."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|\s*(https?://\S+?)\s*\|$", line)
        if match:
            rows.append(SourceFile(company=match.group(1), file=match.group(2), url=match.group(3)))
    return rows


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unavailable_reason(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    if status in (401, 403):
        return "сайт закрыт для автоматической проверки"
    if status in (404, 410):
        return "файл по ссылке удалён — возможно, вышла новая редакция"
    return "сайт не ответил"


def check_file(source: SourceFile, slug: str, fetch: Callable[[str], Any],
               sources_dir: Path = SOURCES_DIR) -> dict[str, Any]:
    result = {"file": source.file, "url": source.url}
    local = sources_dir / source.file
    try:
        fetched = fetch(source.url)
        if not official_url(slug, fetched.url):
            raise ValueError("redirect left the insurer site")
        body = fetched.body
        if not body.lstrip().startswith(b"%PDF"):
            # A block page, a "not a robot" check or a removed file page.
            result.update(status="unavailable", reason="сайт отдал страницу вместо файла правил")
            return result
        if not local.is_file():
            result.update(status="changed", reason="в проекте нет сохранённой копии")
        elif _sha256(body) == _sha256(local.read_bytes()):
            result.update(status="unchanged")
        else:
            result.update(status="changed", reason="файл на сайте отличается от сохранённой копии",
                          remote_sha256=_sha256(body), remote_size=len(body))
    except Exception as exc:  # noqa: BLE001 - every failure is reported, never raised
        result.update(status="unavailable", reason=_unavailable_reason(exc))
    return result


def check_pages(insurer, fetch: Callable[[str], Any], previous: dict[str, Any],
                pinned_urls: set[str]) -> list[dict[str, Any]]:
    """Look for CASCO documents that appeared on the insurer pages.

    Every link seen on a page is remembered. A new CASCO-looking link that is
    not one of our pinned files stays flagged until the owner accepts it
    (see accept_new_documents), so one night's alarm is not lost the next night.
    """
    results = []
    for page in page_urls(insurer):
        before = previous.get(page, {})
        known = set(before.get("known_links", []))
        try:
            fetched = fetch(page)
            if not official_url(insurer.slug, fetched.url):
                raise ValueError("redirect left the insurer site")
            links = document_links(fetched.body, fetched.url, insurer.slug)
            if not links:
                results.append({"url": page, "status": "unavailable",
                                "reason": "страница не открылась для проверки",
                                "known_links": sorted(known)})
                continue
            current = {link["url"]: link for link in links}
            first_visit = not before
            new = [link for url, link in current.items()
                   if url not in known and url not in pinned_urls and casco_link(link)]
            if first_visit:
                # The first visit only records what is already published.
                known |= set(current)
                new = []
            else:
                known |= {url for url, link in current.items() if not casco_link(link)}
            flagged = {link["url"]: link for link in before.get("new_documents", [])
                       if link["url"] in current}
            flagged.update({link["url"]: {"url": link["url"], "title": link["title"]} for link in new})
            results.append({
                "url": page,
                "status": "new_documents" if flagged else "unchanged",
                "new_documents": sorted(flagged.values(), key=lambda link: link["url"]),
                "known_links": sorted(known),
            })
        except Exception as exc:  # noqa: BLE001
            results.append({"url": page, "status": "unavailable", "reason": _unavailable_reason(exc),
                            "known_links": sorted(known)})
    return results


def company_status(files: list[dict[str, Any]], pages: list[dict[str, Any]]) -> str:
    """changed > unavailable > ok. "ok" means every rules file was verified."""
    if any(f["status"] == "changed" for f in files) or any(p["status"] == "new_documents" for p in pages):
        return "changed"
    if not files or any(f["status"] == "unavailable" for f in files):
        return "unavailable"
    return "ok"


def run_check(fetch: Callable[[str], Any], *, previous: dict[str, Any] | None = None,
              table: list[SourceFile] | None = None, sources_dir: Path = SOURCES_DIR,
              now: datetime | None = None) -> dict[str, Any]:
    previous = previous or {}
    table = table if table is not None else load_source_table()
    checked_at = (now or datetime.now(MOSCOW)).astimezone(MOSCOW).isoformat(timespec="minutes")
    companies = {}
    for insurer in INSURERS:
        rows = [row for row in table if row.company == insurer.name]
        files = [check_file(row, insurer.slug, fetch, sources_dir) for row in rows]
        before = previous.get("companies", {}).get(insurer.name, {})
        prior_pages = {page["url"]: page for page in before.get("pages", [])}
        pages = check_pages(insurer, fetch, prior_pages, {row.url for row in rows})
        status = company_status(files, pages)
        companies[insurer.name] = {
            "status": status,
            "verified_at": checked_at if status == "ok" else before.get("verified_at"),
            "files": files,
            "pages": pages,
        }
    return {"version": 1, "checked_at": checked_at, "companies": companies}


def accept_new_documents(status: dict[str, Any], company: str) -> dict[str, Any]:
    """Owner reviewed the flagged documents of one company: stop flagging them."""
    for page in status.get("companies", {}).get(company, {}).get("pages", []):
        known = set(page.get("known_links", []))
        known |= {link["url"] for link in page.get("new_documents", [])}
        page["known_links"] = sorted(known)
        page["new_documents"] = []
        if page.get("status") == "new_documents":
            page["status"] = "unchanged"
    return status


def load_status(path: Path = STATUS_FILE) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_status(status: dict[str, Any], path: Path = STATUS_FILE) -> None:
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
