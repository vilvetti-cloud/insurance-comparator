"""Edit cells of data/casco-comparison-master.json without reformatting the file.

The file is reviewed by people in git diffs, so only the changed values may
change: each value is replaced in place inside its field object.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

MASTER = Path(__file__).resolve().parents[1] / "data" / "casco-comparison-master.json"


def load(path: Path = MASTER) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _replace_attr(span: str, attr: str, value: Any) -> str:
    pattern = re.compile(r'("%s":\s*)("(?:[^"\\]|\\.)*"|\[[^\]]*\]|null|-?\d+)' % re.escape(attr), re.S)
    match = pattern.search(span)
    if not match:
        raise KeyError(attr)
    old = json.loads(match.group(2))
    if isinstance(old, str) and isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return span[: match.start(2)] + json.dumps(value, ensure_ascii=False) + span[match.end(2):]


def update_cells(updates: dict[tuple[str, str], dict[str, Any]], *, created_date: str | None = None,
                 path: Path = MASTER) -> None:
    """Apply {(company slug, field key): {attribute: value}} and optionally a new created_date.

    Raises if anything other than the requested values would change.
    """
    text = path.read_text(encoding="utf-8", newline="")
    expected = json.loads(text)
    for (slug, key), attrs in updates.items():
        company_at = text.find(f'"slug": "{slug}"')
        field_at = text.find(f'"key": "{key}"', company_at)
        if company_at < 0 or field_at < 0:
            raise KeyError(f"{slug}/{key}")
        next_field = text.find('"key": "', field_at + 10)
        end = next_field if next_field > 0 else len(text)
        span = text[field_at:end]
        company = next(c for c in expected["companies"] if c["slug"] == slug)
        field = next(f for f in company["fields"] if f["key"] == key)
        for attr, value in attrs.items():
            span = _replace_attr(span, attr, value)
            if isinstance(field.get(attr), str) and isinstance(value, list):
                value = " ".join(str(item) for item in value)
            field[attr] = value
        text = text[:field_at] + span + text[end:]
    if created_date:
        text = _replace_attr(text[:400], "created_date", created_date) + text[400:]
        expected["created_date"] = created_date
    if json.loads(text) != expected:
        raise ValueError("unexpected changes outside the updated cells")
    path.write_text(text, encoding="utf-8", newline="")


def field_of(master: dict[str, Any], company_name: str, key: str) -> dict[str, Any]:
    company = next(c for c in master["companies"] if c["name"] == company_name)
    return copy.deepcopy(next(f for f in company["fields"] if f["key"] == key))


def slug_of(master: dict[str, Any], company_name: str) -> str:
    return next(c["slug"] for c in master["companies"] if c["name"] == company_name)
