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
