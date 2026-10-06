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
    InsurerConfig(
        "reso",
        "РЕСО-Гарантия",
        "РЕСО",
        "https://reso.ru/",
        "https://reso.ru/individual/auto/kasko/",
        "https://reso.ru/individual/auto/kasko/sredstv-avtotransporta-03022025.pdf",
    ),
    InsurerConfig(
        "vsk",
        "ВСК",
        "ВСК",
        "https://vsk.ru/",
        "https://www.vsk.ru/klientam/avto/kasko-kompakt-minimum",
        rules_url="https://www.vsk.ru/cms/assets/1179953c-dc8f-45f9-9d46-8eaba56b9c10",
        official_doc_urls=(
            "https://www.vsk.ru/cms/assets/209bfe0b-8b20-474c-8428-82d51132f54b",
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
        "https://www.renins.ru/auto/kasko/",
        "https://www.renins.ru/Media/Default/doc/rules_new/49.pdf",
        official_doc_urls=("https://www.renins.ru/about/rules/",),
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
        "https://www.soglasie.ru/individuals/avto/kasko/",
        "https://api.soglasie.ru/storage/managed/pravila_strahovania/4/Правила%20страхования.pdf",
        official_doc_urls=(
            "https://www.soglasie.ru/individuals/avto/kasko/pravila-strakhovaniya-transportnykh-sredstv/",
        ),
    ),
    InsurerConfig(
        "rgs",
        "Росгосстрах",
        "РГС",
        "https://www.rgs.ru/",
        "https://www.rgs.ru/auto/ekasko/kasko-ot-ugona-i-gibeli",
        "https://www-data.rgs.ru/upload/iblock/c24/g1xtpnmp9yuzbacb6jrcwrxd1wf7ljyv/171_-Pravila_24022026.pdf",
    ),
    InsurerConfig(
        "t-insurance",
        "Т-Страхование",
        "Т-Страхование",
        "https://www.tinsurance.ru/",
        "https://www.tinsurance.ru/kasko/",
        "https://cdn.tinsurance.ru/static/documents/kasko_rules.pdf",
        official_doc_urls=(
            "https://www.tbank.ru/insurance/help/auto/kasko/get-kasko/conditions/",
        ),
    ),
    InsurerConfig(
        "sber",
        "СберСтрахование",
        "Сбер",
        "https://sberbankins.ru/",
        "https://sberbankins.ru/products/kasko/",
        "https://sberbankins.ru/upload/iblock/4aa/wef0vo0p52bngziwkksqhic13381u1j9/pravila_134_19.pdf",
        official_doc_urls=(
            "https://sberbankins.ru/upload/iblock/c2c/zjn30vv4p5vsvvmr88nfnm5vne7amz1t/Pravila-strakhovaniya-finansovykh-riskov-vladeltsev-transportnykh-sredstv-GAP-_-16.1.pdf",
            "https://sberbankins.ru/about/disclosure/",
        ),
    ),
    InsurerConfig(
        "yugoria",
        "Югория",
        "Югория",
        "https://www.ugsk.ru/",
        "https://ugsk.ru/",
        rules_url="https://ugsk.ru/pravila/%D0%9F%D1%80%D0%B0%D0%B2%D0%B8%D0%BB%D0%B0%D0%9A%D0%90%D0%A1%D0%9A%D0%9E_04_%D1%80%D0%B5%D0%B4.9.0.pdf",
        official_doc_urls=(
            "https://ugsk.ru/pravila/%D0%9F%D1%80%D0%B0%D0%B2%D0%B8%D0%BB%D0%B0%20GAP%20(105%20%D1%80%D0%B5%D0%B4.2).pdf",
        ),
    ),
    InsurerConfig(
        "sovcom",
        "Совкомбанк Страхование",
        "Совкомбанк",
        "https://sovcomins.ru/",
        "https://sovcomins.ru/product/kasko/",
        "https://sovcomins.ru/upload/pravila/kasko_11_23.pdf",
        official_doc_urls=("https://sovcomins.ru/product/superkasko/",),
    ),
)


def get_insurer(slug: str) -> InsurerConfig:
    for insurer in INSURERS:
        if insurer.slug == slug:
            return insurer
    raise KeyError(f"Unknown insurer: {slug}")

