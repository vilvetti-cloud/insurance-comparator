from __future__ import annotations

import re


NUMBER_WORD_VALUES = {
    "одн": "1",
    "дв": "2",
    "тр": "3",
    "четыр": "4",
    "пят": "5",
    "шест": "6",
    "сем": "7",
    "восем": "8",
    "девят": "9",
    "десят": "10",
    "пятнадцат": "15",
    "двадцат": "20",
    "тридцат": "30",
    "сорок": "40",
    "сорока": "40",
    "шестидесят": "60",
}

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
        quote_n = " ".join(str(quote or "").lower().split())
        has_franchise = "франшиз" in quote_n
        has_terms = bool(re.search(r"безуслов|условн|размер|сумм|руб|%|примен|устанавл|вычет", quote_n))
        # A clipped fragment like "вышает размер франшизы)" is not a usable
        # comparison fact even if it contains the keyword.
        looks_clipped = bool(
            quote_n
            and (
                re.match(r"^(?:вышает|расценок|тс»|страховщиком\b)", quote_n)
                or quote_n.endswith(("(", ":", ","))
            )
        )
        return has_franchise and has_terms and not looks_clipped
    if field_key == "without_certificates":
        quote_n = " ".join(str(quote or "").lower().split())
        # A catalog/list that merely names an add-on such as "Выплата без
        # справок" does not establish what damage can be settled or the limit.
        if len(re.findall(r"№\s*\d+", quote_n)) >= 3:
            return False
        has_without = bool(
            re.search(
                r"без\s+(?:(?:предоставлен|предъявлен)\w*\s+)?(?:справ|документ)|упрощ",
                quote_n,
            )
        )
        has_scope = bool(
            re.search(
                r"урегулир|поврежд|стекл|кузов|элемент|"
                r"страхов\w*\s+случ|не\s+более|\d+\s*(?:раз|руб|%)",
                quote_n,
            )
        )
        return has_without and has_scope
    if field_key == "gap":
        return bool(re.search(r"\bgap\b|гэп|сохран\w*\s+стоим", evidence))
    if field_key == "total_loss":
        has_total = bool(re.search(r"тотал|полная\s+гибел|конструктив\w*\s+гибел", evidence))
        has_threshold = bool(re.search(r"\d+\s*%|процент|превыш|составля|равн", evidence))
        return has_total and has_threshold
    if field_key == "self_ignition":
        quote_n = " ".join(str(quote or "").lower().split())
        has_risk = bool(re.search(r"самовозгор|возгоран|пожар", quote_n))
        has_meaning = bool(
            re.search(
                r"покрыв|застрахован|страхов\w*\s+(?:случ|риск)|"
                r"возмещ|включ|исключ|не\s+явля|не\s+покрыв",
                quote_n,
            )
        )
        return has_risk and has_meaning
    if field_key == "terrorism":
        quote_n = " ".join(str(quote or "").lower().split())
        # Dot leaders are characteristic of a table of contents / heading and
        # do not prove whether the risk is covered or excluded.
        if re.search(r"(?:\.{4,}|…{3,})", quote_n):
            return False
        has_terror = "террор" in quote_n
        has_meaning = bool(
            re.search(
                r"покрыв|застрахован|страхов\w*\s+(?:случ|риск)|"
                r"возмещ|включ|исключ|не\s+явля|не\s+покрыв|ущерб\s+от",
                quote_n,
            )
        )
        return has_terror and has_meaning
    if field_key == "drone":
        if navigation_noise:
            return False
        quote_n = " ".join(str(quote or "").lower().split())
        has_drone = bool(re.search(r"бпла|дрон|беспилот", quote_n))
        # Merely naming "падение беспилотного аппарата" is not enough; the
        # quote must connect it to insured damage/coverage or exclusion.
        has_coverage = bool(
            re.search(
                r"ущерб|повреж|гибел|покрыв|возмещ|исключ|"
                r"страхов\w*\s+(?:случ|риск)|не\s+явля",
                quote_n,
            )
        )
        return has_drone and has_coverage
    if field_key == "tow_truck":
        if testimonial_noise:
            return False
        quote_n = " ".join(str(quote or "").lower().split())
        has_tow = bool(re.search(r"эвакуатор|эвакуац", quote_n))
        # Definition of evacuation/transportation alone is not a benefit.
        has_service = bool(
            re.search(
                r"расход|возмещ|оплат|компенс|предостав|лимит|"
                r"услуг|один\s+раз|не\s+более|до\s+\d",
                quote_n,
            )
        )
        return has_tow and has_service
    if field_key == "repair_type":
        quote_n = " ".join(str(quote or "").lower().split())
        if re.search(r"уступк|право\s+требован|цесси", quote_n):
            return False
        # A definition of an STOA, rates, or documents after repair does not
        # establish the settlement form.
        if re.search(
            r"документ\w*\s+из\s+стоа|расценок\s+стоа|"
            r"стоа\s+официального\s+дилера\s+[—-]\s+юрид|"
            r"издели\w*\s*\(|детал\w*|узл\w*|агрегат\w*|подлежащ\w*\s+замен",
            quote_n,
        ):
            return False
        has_repair = bool(
            re.search(
                r"ремонт|стоа|дилер|станци\w*\s+тех|"
                r"денежн\w*\s+(?:форм|выплат|компенсац)|"
                r"калькуляц|по\s+факту\s+ремонт",
                quote_n,
            )
        )
        has_form = bool(
            re.search(
                r"форма\s+возмещ|направлен\w*\s+на\s+ремонт|"
                r"возмещени\w*\s+(?:осуществ|производ)|"
                r"страхов\w*\s+возмещ\w*.*(?:форм|калькуляц|факту\s+ремонт)|"
                r"выплат\w*\s+(?:производ|осуществ)|"
                r"одн\w*\s+из\s+следующ\w*\s+форм|"
                r"по\s+калькуляц|по\s+факту\s+ремонт|"
                r"ремонт\w*\s+(?:на|в)\s+стоа",
                quote_n,
            )
        )
        return has_repair and has_form
    if field_key == "payment_terms":
        if navigation_noise:
            return False
        has_days = bool(
            re.search(
                r"(?:\d+|одн\w*|дв\w*|тр\w*|четыр\w*|пят\w*|шест\w*|сем\w*|"
                r"восем\w*|девят\w*|десят\w*|пятнадцат\w*|двадцат\w*|"
                r"тридцат\w*|сорок\w*|сорока\w*|шестидесят\w*)\s*"
                r"(?:(?:рабоч|календарн)\w*\s+)?дн|срок\w*.*\d+",
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
        for stem, numeric in NUMBER_WORD_VALUES.items():
            if re.search(rf"\b{stem}[а-яё]*\b", quote_n):
                quote_numbers.add(numeric)
        unsupported = value_numbers - quote_numbers
        if unsupported:
            return (
                "В сохранённом значении есть число, которого нет в подтверждающей "
                f"цитате: {', '.join(sorted(unsupported))}."
            )

    if field_key == "franchise":
        franchise_terms = [
            "безуслов", "условн", "условно-безуслов", "прогрессив",
            "динамич", "временн", "льготн",
        ]
        claimed = [term for term in franchise_terms if term in value_n]
        missing_terms = [term for term in claimed if term not in quote_n]
        if missing_terms:
            return (
                "Значение добавляет типы франшизы, которых нет в подтверждающей "
                "цитате: " + ", ".join(missing_terms) + "."
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
