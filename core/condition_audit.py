from __future__ import annotations

import re
from dataclasses import dataclass

from core.evidence_quality import is_supported_condition, semantic_alignment_issue


@dataclass(frozen=True)
class ConditionAudit:
    status: str
    label: str
    sales_eligible: bool
    reason: str


STATUS_LABELS = {
    "confirmed": "Подтверждено",
    "conditional": "Зависит от программы/договора",
    "review": "Нужно перепроверить",
    "missing": "Не найдено",
}


_CONDITIONAL_RE = re.compile(
    r"зависит от|определяется (?:выбранной )?(?:программой|договором|условиями договора)|"
    r"если .*предусмотрен|при наличии соответств|"
    r"не (?:является )?универсальн|не подтвержден|не заявлен|не установлен|"
    r"не выделен|не указан|единый .* не|конкретн\w* .* определяется|"
    r"необходимо (?:проверять|определять) по|"
    r"в отдельных программах|в ряде программ|доступен в отдельных",
    re.I,
)


def audit_condition(
    field_key: str,
    value: str | None,
    quote: str | None,
    *,
    source_level: int | None,
    source_type: str | None,
    confidence: float | None,
    verification_status: str | None,
) -> ConditionAudit:
    if not value:
        return _result("missing", "Значение отсутствует.")

    if verification_status == "rejected":
        return _result(
            "review",
            "Кандидат ранее отклонён проверкой и не может считаться подтверждённым.",
        )

    text = " ".join(f"{value or ''} {quote or ''}".lower().split())
    normalized_value = " ".join(str(value).lower().split())

    if source_level not in {1, 2}:
        return _result(
            "review",
            "Источник не относится к официальным правилам или официальному сайту страховщика.",
        )

    if source_type in {"web_search", "fallback"}:
        return _result(
            "review",
            "Значение получено из резервного/поискового источника, а не из официального материала.",
        )

    if confidence is not None:
        try:
            if float(confidence) < 0.75:
                return _result(
                    "review",
                    "У извлечения недостаточная уверенность для использования в продаже.",
                )
        except (TypeError, ValueError):
            return _result("review", "Некорректное значение confidence.")

    mismatch = _field_mismatch(field_key, normalized_value, text, quote)
    if mismatch:
        return _result("review", mismatch)

    # Snapshots are synthesized summaries, not verbatim primary-source
    # evidence. Keep them visible for diagnostics but never count them as a
    # reportable fact until the underlying document/page is captured directly.
    if source_type == "official_snapshot":
        return _result(
            "review",
            "Snapshot содержит подготовленный пересказ без прямой цитаты из первоисточника; требуется подтверждение исходным документом.",
        )

    # Contract/program-specific statements are useful for completeness, but
    # they must never be promoted to a comparative sales advantage.
    if _CONDITIONAL_RE.search(text):
        return _result(
            "conditional",
            "Официальный источник показывает, что условие зависит от программы, договора или дополнительной опции.",
        )

    # A quote is mandatory for a fully confirmed fact. Snapshots also persist a
    # checked evidence fragment, so absence of evidence is suspicious for all
    # current source types.
    if not quote or not str(quote).strip():
        return _result(
            "review",
            "Нет сохранённого подтверждающего фрагмента источника.",
        )

    normalized_quote = " ".join(str(quote).strip().split())
    normalized_value_original = " ".join(str(value).strip().split())
    raw_same = normalized_value_original.lower() == normalized_quote.lower()
    looks_broken_start = bool(
        re.match(
            r"^(?:ния|ние|ний|ка|ки|го|ой|ых|их|случаю|случая|"
            r"размеру|стоимости|целях|быть\s+застрахован)\b|^\(",
            normalized_value_original.lower(),
        )
    )
    looks_broken_suffix = bool(
        re.search(r"\b[а-яё]{4,}\s+(?:ся|сь)\b", normalized_value_original.lower())
    )
    has_unbalanced_brackets = (
        normalized_value_original.count("(") != normalized_value_original.count(")")
        or normalized_value_original.count("[") != normalized_value_original.count("]")
    )
    looks_unfinished_tail = bool(
        re.search(
            r"\b(?:размер|по\s+риску|в\s+случае|при\s+условии|"
            r"страхование\s+по\s+риску|на\s+которой\s+будет\s+производиться|"
            r"а\s+страховщик)\s*$",
            normalized_value_original.lower(),
        )
    )
    if raw_same and (
        (
            len(normalized_value_original) < 180
            and not re.search(r"[.!?;:%»”\)\]]$", normalized_value_original)
        )
        or looks_broken_start
        or looks_broken_suffix
        or has_unbalanced_brackets
        or looks_unfinished_tail
    ):
        return _result(
            "review",
            "Сохранён сырой/OCR-обрывок источника, а не сформулированное условие для сравнения.",
        )

    if not is_supported_condition(field_key, value, quote):
        return _result(
            "review",
            "Подтверждающий фрагмент не доказывает именно этот параметр сравнения.",
        )

    alignment_issue = semantic_alignment_issue(field_key, value, quote)
    if alignment_issue:
        return _result("review", alignment_issue)

    # Never silently promote a database candidate that is still explicitly
    # marked for review. This was the main reason questionable collector output
    # could appear as "confirmed" in the report.
    if verification_status != "verified":
        return _result(
            "review",
            "Кандидат ещё не имеет статуса verified и изолирован от итогового отчёта.",
        )

    return _result(
        "confirmed",
        "Значение подтверждено официальным источником, проверено и подходит для сравнительного анализа.",
    )


def _field_mismatch(
    field_key: str,
    value: str,
    text: str,
    quote: str | None = None,
) -> str | None:
    if field_key == "without_certificates":
        if re.search(
            r"угон\w*\s+(?:тс\s+)?без\s+документ\w*\s+и\s+ключ|"
            r"без\s+документ\w*\s+и\s+ключ\w*",
            text,
        ):
            has_claims_without_certificates = bool(
                re.search(
                    r"без\s+справ|без\s+предоставлен\w*\s+документ\w*\s+"
                    r"(?:компетент|гибдд|полици)|урегулир\w*\s+без\s+справ",
                    text,
                )
            )
            if not has_claims_without_certificates:
                return (
                    "Фрагмент относится к риску «угон ТС без документов/ключей», "
                    "а не к урегулированию повреждений без справок."
                )

    if field_key == "total_loss":
        if not re.search(r"\d+\s*%|процент|превыш|составля|равн", text):
            # Generic references to total loss are only acceptable as
            # conditional statements; that case is handled by _CONDITIONAL_RE.
            if not _CONDITIONAL_RE.search(text):
                return "Нет конкретного критерия/порога признания полной гибели."

    if field_key == "repair_type":
        has_form = bool(
            re.search(
                r"стоа|станци\w* техническ|официальн\w* дилер|"
                r"направлен\w* на ремонт|форма возмещ|денежн\w* (?:выплат|форм)|"
                r"по\s+калькуляц|по\s+факту\s+ремонт|"
                r"одн\w*\s+из\s+следующ\w*\s+форм",
                text,
            )
        )
        if not has_form:
            return "Фрагмент не определяет форму возмещения или место ремонта."
        if re.match(r"компонент|узл|агрегат", value) and "форма" not in value:
            return "Сохранён соседний фрагмент про детали ремонта, а не сама форма возмещения."
        if re.search(r"65\s*%|75\s*%|полная\s+гибел", value):
            if not re.search(r"стоа|дилер|форма\s+возмещ", value):
                return "В поле типа ремонта сохранён фрагмент про критерий полной гибели."

    if field_key == "payment_terms":
        if re.search(
            r"страхователь\s+обязан|предоставить\w*\s+(?:дополнительн\w*\s+)?объяснен|"
            r"сообщить\w*\s+страховщик|уведомить\w*\s+страховщик",
            value,
        ):
            return (
                "В значение срока выплаты подмешан срок исполнения обязанности "
                "страхователя, а не срок урегулирования страховщиком."
            )
        has_time = bool(
            re.search(
                r"(?:\d+|одн\w*|дв\w*|тр\w*|четыр\w*|пят\w*|шест\w*|сем\w*|"
                r"восем\w*|девят\w*|десят\w*|пятнадцат\w*|двадцат\w*|"
                r"тридцат\w*|сорок\w*|сорока\w*|шестидесят\w*)\s*"
                r"(?:(?:рабоч|календарн)\w*\s+)?дн|"
                r"\d+\s*час|в течение\s+\d+",
                text,
            )
        )
        has_context = bool(
            re.search(
                r"выплат|возмещ|урегулир|направлен\w* на ремонт|"
                r"рассмотрен\w* заяв|принят\w* решен",
                text,
            )
        )
        if not (has_time and has_context) and not _CONDITIONAL_RE.search(text):
            return "Фрагмент не содержит конкретного срока урегулирования/выплаты."

    if field_key == "self_ignition":
        if not re.search(r"самовозгор|возгоран", text):
            return "Фрагмент говорит о пожаре в целом, но не подтверждает именно самовозгорание автомобиля."
        if re.search(r"жизни и здоровью|застрахованн\w* лиц", text):
            if not re.search(r"ущерб\w* (?:тс|автомоб)|поврежд\w* (?:тс|автомоб)", text):
                return (
                    "Фрагмент относится к вреду жизни/здоровью при пожаре, а не "
                    "к покрытию повреждения самого автомобиля."
                )

    if field_key == "terrorism":
        quote_text = " ".join(str(quote or "").lower().split())
        aml_context = bool(
            re.search(
                r"115-фз|115\s*[-–—]?\s*фз|легализац\w*\s*\(отмыван|"
                r"финансировани\w*\s+терроризм|идентификац\w*\s+(?:клиент|страховат)|"
                r"представля\w*\s+(?:страховщик\w*\s+)?(?:оригинал|копи)\w*\s+документ",
                quote_text,
            )
        )
        direct_terror_coverage = bool(
            re.search(
                r"(?:страхов\w*\s+случ|покрыв|возмещ|исключ|"
                r"ущерб\s+(?:вследствие|от)|риск\w*\s+террорист)",
                quote_text,
            )
        )
        # "Оценка страхового риска" in AML/KYC clauses is not evidence that
        # terrorism itself is an insured risk.
        if aml_context and not direct_terror_coverage:
            return (
                "Упоминание терроризма относится к 115-ФЗ/AML/KYC или идентификации клиента, "
                "а не к страховому покрытию террористического риска."
            )

        anti_terror_operation_context = bool(
            re.search(
                r"антитеррористическ\w*\s+операц|контртеррористическ\w*\s+операц|"
                r"территори\w*.*(?:военн|специальн|антитеррористическ|контртеррористическ)\w*\s+операц",
                quote_text,
            )
        )
        explicit_terror_event = bool(
            re.search(
                r"террористическ\w*\s+(?:акт|действ|риск)|"
                r"ущерб\w*.*террорист|вследствие\s+террорист",
                quote_text,
            )
        )
        if anti_terror_operation_context and not explicit_terror_event:
            return (
                "Фрагмент описывает территориальные ограничения для антитеррористических/"
                "контртеррористических операций, а не покрытие террористического акта."
            )

    if field_key in {"terrorism", "drone", "self_ignition", "tow_truck"}:
        required = {
            "terrorism": r"террор",
            "drone": r"бпла|дрон|беспилот",
            "self_ignition": r"самовозгор|возгоран|пожар",
            "tow_truck": r"эвакуатор|эвакуац",
        }[field_key]
        if not re.search(required, text):
            return "Подтверждающий фрагмент относится к другому риску/услуге."

    return None


def _result(status: str, reason: str) -> ConditionAudit:
    return ConditionAudit(
        status=status,
        label=STATUS_LABELS[status],
        sales_eligible=status == "confirmed",
        reason=reason,
    )
