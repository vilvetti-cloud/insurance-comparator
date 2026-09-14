from __future__ import annotations

import json
import os
from typing import Any


class InternalFallback:
    """Optional curated fallback. It is empty unless explicitly configured."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or os.getenv("INTERNAL_FALLBACK_JSON")
        self._data: dict[str, Any] | None = None

    def get(self, company_slug: str) -> dict[str, Any]:
        data = self._load()
        company = data.get(company_slug, {})
        return company if isinstance(company, dict) else {}

    def _load(self) -> dict[str, Any]:
        if self._data is not None:
            return self._data
        if not self.path:
            self._data = {}
            return self._data
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self._data = payload if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            self._data = {}
        return self._data
