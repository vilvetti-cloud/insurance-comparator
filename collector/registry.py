from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InsurerConfig:
    slug: str
    name: str
    short_name: str
    official_url: str
    casco_url: str | None = None
    rules_url: str | None = None
    official_doc_urls: tuple[str, ...] = ()


INSURERS = (
    InsurerConfig("reso", "РЕСО-Гарантия", "РЕСО", "https://reso.ru/", "https://reso.ru/individual/auto/kasko/"),
    InsurerConfig(
        "vsk",
        "ВСК",
        "ВСК",
        "https://vsk.ru/",
        rules_url="https://www.vsk.ru/cms/assets/1179953c-dc8f-45f9-9d46-8eaba56b9c10",
        official_doc_urls=(
            "https://www.vsk.ru/cms/assets/3274076a-21b6-4bc7-96e8-26f1eb2bbcde.pdf",
        ),
    ),
    InsurerConfig(
        "ingos",
        "Ингосстрах",
        "Ингосстрах",
        "https://www.ingos.ru/",
        rules_url="https://cdn.ingos.ru/docs/prav_strakh_ats-2024.pdf",
    ),
    InsurerConfig(
        "renins",
        "Ренессанс Страхование",
        "Ренессанс",
        "https://www.renins.ru/",
        rules_url="https://www.renins.ru/Media/Default/doc/rules/157.pdf",
    ),
    InsurerConfig(
        "alfa",
        "АльфаСтрахование",
        "Альфа",
        "https://www.alfastrah.ru/",
        "https://www.alfastrah.ru/individuals/auto/kasko/",
        "https://alfastrah.com/upload/iblock/da8/6hxelk9vq4cnlhue3okjcluz1lowk2k0.pdf",
    ),
    InsurerConfig(
        "soglasie",
        "Согласие",
        "Согласие",
        "https://www.soglasie.ru/",
        "https://www.soglasie.ru/individuals/avto/kasko/pravila-strakhovaniya-transportnykh-sredstv/",
        "https://api.soglasie.ru/storage/managed/upload/docs/auto/pravila-strakhovaniya-transportnykh-sredstv.pdf",
    ),
    InsurerConfig("rgs", "Росгосстрах", "РГС", "https://www.rgs.ru/", "https://www.rgs.ru/auto/ekasko/kasko-ot-ugona-i-gibeli"),
    InsurerConfig(
        "t-insurance",
        "Т-Страхование",
        "Т-Страхование",
        "https://www.tbank.ru/",
        "https://www.tbank.ru/insurance/kasko/",
        "https://cdn.tinsurance.ru/static/documents/kasko_rules.pdf",
    ),
    InsurerConfig(
        "sber",
        "СберСтрахование",
        "Сбер",
        "https://sberbankins.ru/",
        "https://sberbankins.ru/products/kasko/",
        "https://sberbankins.ru/upload/iblock/4aa/wef0vo0p52bngziwkksqhic13381u1j9/pravila_134_19.pdf",
    ),
    InsurerConfig(
        "yugoria",
        "Югория",
        "Югория",
        "https://www.ugsk.ru/",
        rules_url="https://ugsk.ru/pravila/Kasko.pdf",
    ),
    InsurerConfig(
        "sovcom",
        "Совкомбанк Страхование",
        "Совкомбанк",
        "https://sovcomins.ru/",
        "https://sovcomins.ru/product/car/",
    ),
)


def get_insurer(slug: str) -> InsurerConfig:
    for insurer in INSURERS:
        if insurer.slug == slug:
            return insurer
    raise KeyError(f"Unknown insurer: {slug}")
