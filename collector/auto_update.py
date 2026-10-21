"""Update the agreed answers by themselves when an insurer publishes new rules.

Runs after the nightly source check. For every insurer whose rules changed:

1. The new file is compared with our copy as text. A re-upload of the same
   text only refreshes the copy.
2. Only parameters whose wording is touched by the change are re-read.
3. The AI (Claude or free Gemini) writes each touched answer from the new rules (collector.answer_writer)
   and the answer is accepted only if its quotes are found word for word in
   the new rules and every amount is backed by them.
4. Accepted answers, the new copy of the rules and the check status are saved;
   the site is redeployed by the push. Anything that fails a check keeps the
   old answer and is reported for a manual look.

A new CASCO document found on an insurer page is treated as a new edition of
the main rules when its text is close to them; otherwise it is noted and
accepted. Owner's decision (20.10.2026): fully automatic, owner notified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Callable

from collector import answers_store
from collector.answer_writer import FIELD_PATTERNS, Draft, answer_client, write_answer
from collector.rules_text import changed_sentences, comparable, pdf_pages, similarity
from collector.source_watch import (
    MOSCOW, ROOT, SOURCES_DIR, SOURCES_TABLE, accept_new_documents, load_source_table,
)
from core.catalog import KASKO_FIELDS

LOG_FILE = ROOT / "data" / "auto-update-log.json"
LABELS = {item["key"]: item["label"] for item in KASKO_FIELDS}

@dataclass
class Report:
    updated: list[str] = field(default_factory=list)      # «Ингосстрах — Эвакуация: было …, стало …»
    unchanged: list[str] = field(default_factory=list)    # refreshed copies, no answer changed
    manual: list[str] = field(default_factory=list)       # needs a person
    notes: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.updated or self.unchanged or self.manual or self.notes)

    def markdown(self, checked_at: str) -> str:
        lines = [f"Ночная проверка правил КАСКО: {checked_at}", ""]
        if self.updated:
            lines += ["**Ответы обновлены автоматически:**", *[f"- {item}" for item in self.updated], ""]
        if self.unchanged:
            lines += ["**Файлы правил обновлены, ответы не изменились:**", *[f"- {item}" for item in self.unchanged], ""]
        if self.manual:
            lines += ["**Нужно посмотреть вручную (старые ответы оставлены):**", *[f"- {item}" for item in self.manual], ""]
        if self.notes:
            lines += ["**Заметки:**", *[f"- {item}" for item in self.notes], ""]
        return "\n".join(lines).strip() + "\n"


def _fields_citing(company: dict[str, Any], file: str) -> list[dict[str, Any]]:
    main = company.get("main_pdf")
    result = []
    for item in company["fields"]:
        pdfs = item.get("source_pdfs") or []
        pdfs = [pdfs] if isinstance(pdfs, str) else pdfs
        cited = [p.strip() for chunk in pdfs for p in str(chunk).split(";")]
        if file in cited or (not cited and file == main):
            result.append(item)
    return result


def affected_fields(company: dict[str, Any], file: str, new_pages: list[str],
                    added: list[str], removed: list[str],
                    old_pages: list[str] | None = None) -> list[dict[str, Any]]:
    """Parameters that cite this file and whose wording the change touches."""
    new_text = comparable(" ".join(new_pages))
    old_text = comparable(" ".join(old_pages)) if old_pages is not None else None
    changed = added + removed
    result = []
    for item in _fields_citing(company, file):
        quote = comparable(item.get("evidence_quote") or "")[:160]
        # A quoted clause that disappeared from the rules: the answer lost its basis.
        was_there = old_text is None or quote in old_text
        quote_gone = bool(quote) and was_there and quote not in new_text
        touched = any(re.search(FIELD_PATTERNS[item["key"]], sentence) for sentence in changed)
        if quote_gone or touched:
            result.append(item)
    return result


def _load_log(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"attempts": {}}


def _replace_table_url(table_file: Path, file: str, url: str) -> None:
    text = table_file.read_text(encoding="utf-8")
    text = re.sub(rf"(\|\s*`{re.escape(file)}`\s*\|\s*)https?://\S+?(\s*\|)",
                  lambda m: m.group(1) + url + m.group(2), text)
    table_file.write_text(text, encoding="utf-8")


class AutoUpdater:
    def __init__(self, *, status: dict[str, Any], download_dir: Path, client=None,
                 fetch: Callable[[str], Any] | None = None, now: datetime | None = None,
                 sources_dir: Path = SOURCES_DIR, master_path: Path = answers_store.MASTER,
                 writer: Callable[..., Draft] = write_answer,
                 read_pages: Callable[[bytes | Path], list[str]] = pdf_pages,
                 log_file: Path = None, table_file: Path = None):
        self.status = status
        self.download_dir = download_dir
        self.client = client
        self.fetch = fetch
        self.now = (now or datetime.now(MOSCOW)).astimezone(MOSCOW)
        self.sources_dir = sources_dir
        self.master_path = master_path
        self.writer = writer
        self.read_pages = read_pages
        self.log_file = log_file or LOG_FILE
        self.table_file = table_file or SOURCES_TABLE
        self.report = Report()
        self.log = _load_log(self.log_file)

    # -- one changed file -------------------------------------------------
    def _process_file(self, company_name: str, file: str, new_body: bytes, remote_sha: str) -> bool:
        """True when the file was fully handled (answers updated or untouched)."""
        attempt_key = f"{file}@{remote_sha}"
        if self.log["attempts"].get(attempt_key, {}).get("result") == "manual":
            # This exact file already failed the checks: do not pay for it again.
            return False
        master = answers_store.load(self.master_path)
        company = next(c for c in master["companies"] if c["name"] == company_name)
        local = self.sources_dir / file
        new_pages = self.read_pages(new_body)
        old_pages = self.read_pages(local) if local.is_file() else []
        added, removed = changed_sentences(old_pages, new_pages)
        if not added and not removed:
            self._save_copy(local, new_body)
            self.report.unchanged.append(f"{company_name}: {file} — перезалит без изменений текста")
            return True
        touched = affected_fields(company, file, new_pages, added, removed, old_pages)
        if not touched:
            self._save_copy(local, new_body)
            self.report.unchanged.append(
                f"{company_name}: {file} — текст изменился, но не в пунктах о 10 параметрах сравнения")
            return True
        if self.client is None:
            self.report.manual.append(
                f"{company_name}: {file} — изменились пункты о параметрах "
                f"({', '.join(LABELS[f['key']] for f in touched)}), но ключ ИИ (Claude или Gemini) не настроен")
            self.log["attempts"][attempt_key] = {"result": "manual", "at": self.now.isoformat(timespec="minutes")}
            return False

        drafts: dict[str, Draft] = {}
        request_failed = False
        for item in touched:
            try:
                drafts[item["key"]] = self.writer(
                    self.client, company=company_name, field_key=item["key"], field_label=LABELS[item["key"]],
                    pages=new_pages, current_answer=item.get("key_conditions") or item.get("direct_answer") or "",
                    changed_sentences=added + removed,
                )
            except Exception as exc:  # noqa: BLE001 - network, limits, malformed output: keep the old answer
                request_failed = True
                problem = f"ошибка запроса к ИИ ({type(self.client).__name__}): {type(exc).__name__}: {str(exc)[:300]}"
                drafts[item["key"]] = Draft(False, "", [], "", problems=[problem])
        failed = {key: draft for key, draft in drafts.items() if not draft.valid}
        if failed:
            for key, draft in failed.items():
                self.report.manual.append(
                    f"{company_name} — {LABELS[key]}: автоматическая проверка не пройдена ({'; '.join(draft.problems)})")
            # A failed request (limits, a busy server) is retried with the next check;
            # an answer that failed the checks is not, until the file changes again.
            if not request_failed:
                self.log["attempts"][attempt_key] = {"result": "manual", "at": self.now.isoformat(timespec="minutes")}
            return False

        stamp = self.now.strftime("%d.%m.%Y")
        updates = {}
        for key, draft in drafts.items():
            updates[(company["slug"], key)] = {
                "direct_answer": re.split(r"(?<=[.!?])\s+(?=[А-ЯЁA-Z«])", draft.key_conditions, maxsplit=1)[0],
                "key_conditions": draft.key_conditions,
                "evidence_quote": " | ".join(quote["text"] for quote in draft.quotes),
                "text_search_pages": draft.pages,
                "audit_status": f"Автообновление по новой редакции правил {stamp}",
                "source_analysis_status": "found",
                "source_quote_check": f"цитата найдена в новой редакции правил (автопроверка {stamp})",
                "limitations": "",
            }
            line = f"{company_name} — {LABELS[key]}: {draft.change_summary}"
            (self.report.updated if draft.changed else self.report.unchanged).append(line)
        answers_store.update_cells(updates, created_date=self.now.date().isoformat(), path=self.master_path)
        self._save_copy(local, new_body)
        self.log["attempts"][attempt_key] = {"result": "updated", "at": self.now.isoformat(timespec="minutes")}
        return True

    def _save_copy(self, local: Path, body: bytes) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(body)

    # -- new documents on insurer pages ------------------------------------
    def _process_new_document(self, company_name: str, link: dict[str, Any]) -> bool:
        """True when the document was a new edition of a rules file and was handled."""
        if self.fetch is None:
            return False
        try:
            body = self.fetch(link["url"]).body
        except Exception:  # noqa: BLE001 - reported as a note
            self.report.notes.append(f"{company_name}: новый документ не скачался — {link['url']}")
            return False
        if not body.lstrip().startswith(b"%PDF"):
            return False
        candidate = self.read_pages(body)
        best_file, best_score = None, 0.0
        for row in load_source_table(self.table_file):
            if row.company != company_name or not (self.sources_dir / row.file).is_file():
                continue
            score = similarity(self.read_pages(self.sources_dir / row.file), candidate)
            if score > best_score:
                best_file, best_score = row, score
        if best_file is None or best_score < 0.3:
            self.report.notes.append(
                f"{company_name}: на сайте новый документ «{link.get('title') or link['url']}» — "
                "это не новая редакция наших правил, ответы не затронуты")
            return False
        handled = self._process_file(company_name, best_file.file, body, hashlib.sha256(body).hexdigest())
        if handled:
            _replace_table_url(self.table_file, best_file.file, link["url"])
            self.report.notes.append(f"{company_name}: правила теперь берутся по новой ссылке {link['url']}")
        return handled

    # -- whole night -------------------------------------------------------
    def run(self) -> Report:
        for company_name, item in self.status.get("companies", {}).items():
            if item.get("status") != "changed":
                continue
            all_handled = True
            for file in item.get("files", []):
                if file.get("status") != "changed":
                    continue
                downloaded = self.download_dir / file["file"]
                if not downloaded.is_file():
                    all_handled = False
                    continue
                if self._process_file(company_name, file["file"], downloaded.read_bytes(), file.get("remote_sha256", "")):
                    file["status"] = "unchanged"
                    file.pop("reason", None)
                else:
                    all_handled = False
            for page in item.get("pages", []):
                for link in list(page.get("new_documents", [])):
                    self._process_new_document(company_name, link)
            # New documents are now known: they were handled or noted.
            accept_new_documents(self.status, company_name)
            if all_handled:
                item["status"] = "ok"
                item["verified_at"] = self.now.isoformat(timespec="minutes")
                item["auto_updated_at"] = self.now.isoformat(timespec="minutes")
        self.log_file.write_text(json.dumps(self.log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self.report


# Kept for callers of the earlier name.
anthropic_client = answer_client
