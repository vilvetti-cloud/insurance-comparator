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


INSURERS = (
    InsurerConfig("reso", "РЕСО-Гарантия", "РЕСО", "https://reso.ru/", "https://reso.ru/individual/auto/kasko/"),
    InsurerConfig(
        "vsk",
        "ВСК",
        "ВСК",
        "https://vsk.ru/",
        rules_url="https://www.vsk.ru/cms/assets/1179953c-dc8f-45f9-9d46-8eaba56b9c10",
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
    InsurerConfig("t-insurance", "Т-Страхование", "Т-Страхование", "https://www.tbank.ru/", "https://www.tbank.ru/insurance/kasko/"),
    InsurerConfig("sber", "СберСтрахование", "Сбер", "https://www.sberbank.ru/"),
    InsurerConfig("yugoria", "Югория", "Югория", "https://www.ugsk.ru/"),
    InsurerConfig("sovcom", "Совкомбанк Страхование", "Совкомбанк", "https://sovcomins.ru/"),
)


def get_insurer(slug: str) -> InsurerConfig:
    for insurer in INSURERS:
        if insurer.slug == slug:
            return insurer
    raise KeyError(f"Unknown insurer: {slug}")
