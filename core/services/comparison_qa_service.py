from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.catalog import KASKO_FIELDS
from core.services.sales_insights_service import SalesInsightsService


FIELD_KEYS = [item["key"] for item in KASKO_FIELDS]
FIELD_LABELS = {item["key"]: item["label"] for item in KASKO_FIELDS}


@dataclass
class PairQA:
    company: str
    competitor: str
    advantage_count: int
    errors: list[str] = field(default_factory=list)


@dataclass
class ComparisonQAReport:
    company_count: int
    pair_count: int
    advantage_count: int
    error_count: int
    pairs_without_advantages: int
    pair_results: list[PairQA]

    @property
    def ok(self) -> bool:
        return self.error_count == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "company_count": self.company_count,
            "pair_count": self.pair_count,
            "advantage_count": self.advantage_count,
            "error_count": self.error_count,
            "pairs_without_advantages": self.pairs_without_advantages,
            "errors": [
                {
                    "company": pair.company,
                    "competitor": pair.competitor,
                    "errors": pair.errors,
                }
                for pair in self.pair_results
                if pair.errors
            ],
        }


class ComparisonQAService:
    """Validate every directed insurer comparison against the live snapshot."""

    def __init__(self) -> None:
        self.sales = SalesInsightsService()

    def run(self, snapshot: dict[str, Any]) -> ComparisonQAReport:
        companies = sorted(
            key
            for key, value in snapshot.items()
            if not key.startswith("_") and isinstance(value, dict)
        )

        pair_results: list[PairQA] = []
        advantage_count = 0
        pairs_without_advantages = 0

        for company in companies:
            for competitor in companies:
                if company == competitor:
                    continue

                own = self._prepare(snapshot, company)
                other = self._prepare(snapshot, competitor)
                sales = self.sales.analyze(
                    company=company,
                    competitor=competitor,
                    data=own,
                    competitor_data=other,
                    field_labels=FIELD_LABELS,
                )
                advantages = sales.get("advantages") or []
                errors = self._validate_pair(
                    company=company,
                    competitor=competitor,
                    own=own,
                    other=other,
                    sales=sales,
                )

                if not advantages:
                    pairs_without_advantages += 1
                advantage_count += len(advantages)
                pair_results.append(
                    PairQA(
                        company=company,
                        competitor=competitor,
                        advantage_count=len(advantages),
                        errors=errors,
                    )
                )

        error_count = sum(len(item.errors) for item in pair_results)
        return ComparisonQAReport(
            company_count=len(companies),
            pair_count=len(pair_results),
            advantage_count=advantage_count,
            error_count=error_count,
            pairs_without_advantages=pairs_without_advantages,
            pair_results=pair_results,
        )

    def _validate_pair(
        self,
        *,
        company: str,
        competitor: str,
        own: dict[str, Any],
        other: dict[str, Any],
        sales: dict[str, Any],
    ) -> list[str]:
        errors: list[str] = []
        advantages = sales.get("advantages") or []
        cards = sales.get("cards") or []

        field_keys: list[str] = []
        phrases: list[str] = []

        for index, item in enumerate(advantages, start=1):
            prefix = f"advantage[{index}]"
            key = item.get("field_key")
            if key not in FIELD_KEYS:
                errors.append(f"{prefix}: invalid or missing field_key={key!r}")
                continue

            field_keys.append(key)
            if own.get(f"{key}_quality_status") != "confirmed":
                errors.append(f"{prefix}: own value is not confirmed")
            if other.get(f"{key}_quality_status") != "confirmed":
                errors.append(f"{prefix}: competitor value is not confirmed")
            if not own.get(f"{key}_sales_eligible", False):
                errors.append(f"{prefix}: own value is not sales eligible")
            if not other.get(f"{key}_sales_eligible", False):
                errors.append(f"{prefix}: competitor value is not sales eligible")
            if own.get(f"{key}_source_level") not in {1, 2}:
                errors.append(f"{prefix}: own source is not official")
            if other.get(f"{key}_source_level") not in {1, 2}:
                errors.append(f"{prefix}: competitor source is not official")

            own_value = self._norm(str(own.get(key) or ""))
            other_value = self._norm(str(other.get(key) or ""))
            item_own = self._norm(str(item.get("own_value") or ""))
            item_other = self._norm(str(item.get("competitor_value") or ""))

            if item_own != own_value:
                errors.append(f"{prefix}: own_value does not match source field")
            if item_other != other_value:
                errors.append(f"{prefix}: competitor_value does not match source field")
            if own_value == other_value:
                errors.append(f"{prefix}: identical values were called an advantage")
            if not item.get("comparison_basis"):
                errors.append(f"{prefix}: comparison_basis is missing")

            phrase = self._norm(str(item.get("client_phrase") or ""))
            if not phrase:
                errors.append(f"{prefix}: client phrase is empty")
            elif phrase in phrases:
                errors.append(f"{prefix}: duplicate client phrase")
            phrases.append(phrase)

            if key == "payment_terms":
                own_term = self.sales._payment_term(str(own.get(key) or "").lower())
                other_term = self.sales._payment_term(str(other.get(key) or "").lower())
                if not own_term or not other_term:
                    errors.append(f"{prefix}: payment terms are not parseable")
                elif (
                    own_term.context != other_term.context
                    or own_term.unit != other_term.unit
                ):
                    errors.append(
                        f"{prefix}: incomparable payment clocks were compared"
                    )
                elif own_term.amount >= other_term.amount:
                    errors.append(
                        f"{prefix}: payment term is not directionally better"
                    )

        if len(field_keys) != len(set(field_keys)):
            errors.append("duplicate advantage for the same field")

        expected_cards = advantages[:3]
        if cards != expected_cards:
            errors.append("cards are not exactly the first three validated advantages")

        message = str(sales.get("client_message") or "")
        if advantages:
            allowed_numbers = set(
                re.findall(
                    r"\d+(?:[.,]\d+)?",
                    " ".join(
                        str(item.get("own_value") or "")
                        + " "
                        + str(item.get("competitor_value") or "")
                        for item in advantages[:3]
                    ),
                )
            )
            message_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", message))
            unsupported = message_numbers - allowed_numbers
            if unsupported:
                errors.append(
                    "client_message contains unsupported numbers: "
                    + ", ".join(sorted(unsupported))
                )

        if company == competitor:
            errors.append("self-comparison must never be produced")

        return errors

    @staticmethod
    def _prepare(snapshot: dict[str, Any], company: str) -> dict[str, Any]:
        raw = snapshot.get(company, {})
        prepared: dict[str, Any] = {}
        for key in FIELD_KEYS:
            item = raw.get(key, {})
            if not isinstance(item, dict):
                item = {}
            prepared[key] = item.get("value", "Не найдено") or "Не найдено"
            prepared[f"{key}_source_level"] = item.get("source_level")
            prepared[f"{key}_confidence"] = item.get("confidence")
            prepared[f"{key}_quality_status"] = item.get(
                "quality_status", "missing"
            )
            prepared[f"{key}_sales_eligible"] = bool(
                item.get("sales_eligible", False)
            )
        return prepared

    @staticmethod
    def _norm(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().lower()
