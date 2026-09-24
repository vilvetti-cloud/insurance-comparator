from __future__ import annotations

import re


GENERIC_VALUES = {
    "каско",
    "страхование",
    "автострахование",
    "авиация и беспилотники",
    "беспилотники",
    "ремонт",
    "полная гибель",
    "mentioned",
    "present",
    "not mentioned",
    "yes",
    "no",
    "true",
    "false",
    "упоминается",
    "не упоминается",
    "оплатить",
    "продлить",
}


def is_supported_condition(field_key: str, value: str | None, quote: str | None = None) -> bool:
    """Reject values whose evidence does not actually support the comparison field."""
    if not value:
        return False

    normalized_value = " ".join(str(value).lower().split())
    if normalized_value in GENERIC_VALUES:
        return False
    if len(normalized_value) > 520:
        return False

    evidence = f"{value or ''} {quote or ''}".lower()

    navigation_noise = bool(
        re.search(
            r"помощь\s+вопросы\s+и\s+ответы|продлить\s+оплатить|"
            r"активировать\s+проверить|подарочн\w*\s+сертификат",
            evidence,
        )
    )
    testimonial_noise = bool(
        re.search(
            r"плохо\s+себя\s+чувств|ехала\s+на\s+эвакуатор|"
            r"мне\s+(?:выплат|отремонт|предостав)|мой\s+автомоб",
            evidence,
        )
    )

    if field_key == "franchise":
        has_franchise = "франшиз" in evidence
        has_terms = bool(re.search(r"безуслов|условн|размер|сумм|руб|%|примен|устанавл", evidence))
        return has_franchise and has_terms
    if field_key == "without_certificates":
        return bool(re.search(r"без\s+(?:справ|документ)|упрощ", evidence))
    if field_key == "gap":
        return bool(re.search(r"\bgap\b|гэп|сохран\w*\s+стоим", evidence))
    if field_key == "total_loss":
        has_total = bool(re.search(r"тотал|полная\s+гибел|конструктив\w*\s+гибел", evidence))
        has_threshold = bool(re.search(r"\d+\s*%|процент|превыш|составля|равн", evidence))
        return has_total and has_threshold
    if field_key == "self_ignition":
        has_risk = bool(re.search(r"самовозгор|возгоран|пожар", evidence))
        has_meaning = bool(re.search(r"покрыв|страхов\w*\s+(?:случ|риск)|возмещ|включ|исключ|не\s+явля", evidence))
        return has_risk and has_meaning
    if field_key == "terrorism":
        has_terror = "террор" in evidence
        has_meaning = bool(re.search(r"покрыв|страхов\w*\s+(?:случ|риск)|возмещ|включ|исключ|не\s+явля|ущерб", evidence))
        return has_terror and has_meaning
    if field_key == "drone":
        if navigation_noise:
            return False
        has_drone = bool(re.search(r"бпла|дрон|беспилот", evidence))
        has_coverage = bool(
            re.search(
                r"ущерб|повреж|атак|паден|покрыв|возмещ|исключ|"
                r"страхов\w*\s+(?:случ|риск)",
                evidence,
            )
        )
        return has_drone and has_coverage
    if field_key == "tow_truck":
        if testimonial_noise:
            return False
        has_tow = bool(re.search(r"эвакуатор|эвакуац", evidence))
        has_service = bool(
            re.search(
                r"расход|возмещ|оплат|предостав|лимит|услуг|транспортир",
                evidence,
            )
        )
        return has_tow and has_service
    if field_key == "repair_type":
        if re.search(r"уступк|право\s+требован|цесси", evidence):
            return False
        has_repair = bool(re.search(r"ремонт|стоа|дилер|станци\w*\s+тех|денежн\w*\s+форм", evidence))
        has_form = bool(re.search(r"форма|возмещ|направлен|осуществ|выплат|стоа|дилер", evidence))
        return has_repair and has_form
    if field_key == "payment_terms":
        if navigation_noise:
            return False
        has_days = bool(
            re.search(
                r"\d+\s*(?:(?:рабоч|календарн)\w*\s+)?дн|срок\w*.*\d+",
                evidence,
            )
        )
        has_payment_context = bool(
            re.search(
                r"выплат|возмещ|направлен\w*\s+на\s+ремонт|"
                r"принят\w*\s+решен|рассмотрен\w*\s+заяв",
                evidence,
            )
        )
        return has_days and has_payment_context

    return True


def semantic_alignment_issue(
    field_key: str,
    value: str | None,
    quote: str | None,
) -> str | None:
    """Detect cases where a plausible-looking value is not actually supported by its quote.

    This is deliberately conservative: an uncertain case is quarantined rather
    than converted into a sales fact.
    """
    if not value or not quote:
        return "Нет значения или подтверждающей цитаты для смысловой сверки."

    value_n = " ".join(str(value).lower().split())
    quote_n = " ".join(str(quote).lower().split())

    # Numeric facts must be traceable to the quote. This prevents a model from
    # attaching a correct-looking but unsupported percentage/term to evidence.
    if field_key in {"total_loss", "payment_terms", "tow_truck", "franchise"}:
        value_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", value_n))
        quote_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", quote_n))
        unsupported = value_numbers - quote_numbers
        if unsupported:
            return (
                "В сохранённом значении есть число, которого нет в подтверждающей "
                f"цитате: {', '.join(sorted(unsupported))}."
            )

    if field_key == "total_loss":
        value_pct = re.findall(r"(\d+(?:[.,]\d+)?)\s*%", value_n)
        quote_pct = re.findall(r"(\d+(?:[.,]\d+)?)\s*%", quote_n)
        if value_pct and not set(value_pct).issubset(set(quote_pct)):
            return "Процент порога полной гибели не подтверждается цитатой."

    # Coverage fields need semantic polarity agreement. A frequent extraction
    # failure is turning an exclusion into a positive coverage statement.
    if field_key in {"gap", "self_ignition", "terrorism", "drone", "tow_truck"}:
        positive_re = re.compile(
            r"покрыва|входит|включен|включён|предусмотрен|возмеща|оплачива|"
            r"предоставля|доступен|страховым случаем",
            re.I,
        )
        negative_re = re.compile(
            r"не\s+(?:покрыва|входит|включ|предусмотр|возмеща|оплачива|"
            r"предоставля|явля)|исключен|исключён|исключени|не страховым случаем",
            re.I,
        )
        value_pos = bool(positive_re.search(value_n)) and not bool(negative_re.search(value_n))
        value_neg = bool(negative_re.search(value_n))
        quote_pos = bool(positive_re.search(quote_n)) and not bool(negative_re.search(quote_n))
        quote_neg = bool(negative_re.search(quote_n))

        if value_pos and quote_neg:
            return "Значение говорит о наличии покрытия, а цитата описывает исключение/отсутствие покрытия."
        if value_neg and quote_pos:
            return "Значение говорит об отсутствии покрытия, а цитата подтверждает его наличие."

    if field_key == "without_certificates":
        value_allows = bool(re.search(r"без\s+(?:справ|документ)|упрощ", value_n))
        quote_requires = bool(
            re.search(
                r"обязан\w*\s+предостав|необходим\w*\s+(?:справ|документ)|"
                r"требует\w*\s+(?:справ|документ)",
                quote_n,
            )
        )
        if value_allows and quote_requires and not re.search(r"не\s+треб", quote_n):
            return "Значение обещает урегулирование без справок, но цитата требует документы."

    if field_key == "repair_type":
        value_stoa = bool(re.search(r"стоа|станци\w* техническ|дилер", value_n))
        value_cash = bool(re.search(r"денежн\w* (?:выплат|форм|компенсац)", value_n))
        quote_stoa = bool(re.search(r"стоа|станци\w* техническ|дилер|направлен\w* на ремонт", quote_n))
        quote_cash = bool(re.search(r"денежн\w* (?:выплат|форм|компенсац)", quote_n))
        if value_stoa and not quote_stoa:
            return "В значении указан ремонт/СТОА, но цитата этого не подтверждает."
        if value_cash and not quote_cash:
            return "В значении указана денежная форма, но цитата этого не подтверждает."

    return None
