"""Calibrated T-insurance clauses from the pinned 2024 CASCO rules.

Only exact spans of the cached Docling parse are used as evidence. If an
edition changes its structure, no fact is produced and normal review applies.
"""
import re

from collector.casco_validation import validate_fact


RULES = {
    "franchise": (
        "6.8.", "6.8.1.",
        "В договоре может быть установлена безусловная франшиза. При ее установлении "
        "страховая выплата по каждому страховому случаю уменьшается на размер франшизы; "
        "договором могут быть предусмотрены дополнительные условия применения или иные виды франшизы."),
    "without_certificates": (
        "12.6.", "12.9.",
        "По риску «Ущерб» выплата без справок возможна, если это предусмотрено договором: "
        "при повреждении остекления, фар, фонарей или зеркал либо при неправомерных действиях "
        "третьих лиц с указанными исключениями. Один раз за срок договора, не более 3% страховой "
        "суммы; только при отсутствии пострадавших."),
    "gap": (
        "13.6.", "13.6.1.",
        "По риску GAP выплачивается разница между страховой суммой ТС при заключении договора "
        "и выплатой при хищении либо полной гибели по риску «Ущерб» или «Миникаско»."),
    "total_loss": (
        "1.5.14.", "1.5.15.",
        "Полная гибель ТС наступает, если стоимость восстановительного ремонта равна или "
        "превышает 65% страховой суммы ТС на дату страхового случая. Договором или "
        "дополнительным соглашением сторон этот процент и иные условия могут быть изменены."),
    "tow_truck": (
        "б)", "в)",
        "При повреждении ТС, которое не может двигаться самостоятельно, возмещаются до двух "
        "эвакуаций за страховой случай в пределах 10 000 рублей суммарно; организация "
        "страховщика или по согласованию со страховщиком. По соглашению сторон лимиты могут быть увеличены."),
    "payment_terms": (
        "11.4.4.", "11.4.5.",
        "В течение не более 30 рабочих дней после получения необходимых документов и выполнения "
        "обязанностей страхователя страховщик рассматривает заявление и производит выплату "
        "либо выдаёт направление на ремонт; исключения указаны в п. 11.3.8 Правил. "
        "Если договором предусмотрен ремонт, его срок согласуется со СТОА."),
}


def _span(page_text, start_marker, end_marker):
    start_re = re.compile(r"(?m)^\s*(?:[-*]\s*)?" + re.escape(start_marker) + r"(?=\s|$)")
    end_re = re.compile(r"(?m)^\s*(?:[-*]\s*)?" + re.escape(end_marker) + r"(?=\s|$)")
    start = start_re.search(page_text)
    if not start:
        return None
    end = end_re.search(page_text, start.end())
    if not end:
        return None
    return page_text[start.start():end.start()].strip()


def calibration(key, document, *, insurer="t-insurance", source_url):
    if insurer != "t-insurance" or key not in RULES or not document.promotable:
        return None, "no_calibrated_rule"
    start, end, value = RULES[key]
    reason = "section_span_not_found"
    for page, page_text in document.pages.items():
        quote = _span(page_text, start, end)
        if quote is None:
            continue
        # The lettered towing clause starts on a continuation page. Its own
        # clause letter is the truthful section identifier on that page.
        fact = {"value": value, "exact_quote": quote, "page": page, "section": start}
        verdict = validate_fact(key, fact, document, insurer=insurer, source_url=source_url)
        if verdict.passed:
            return fact, "PASS"
        reason = verdict.reason
    return None, reason


def calibrated_fact(key, document, *, insurer="t-insurance", source_url):
    return calibration(key, document, insurer=insurer, source_url=source_url)[0]
