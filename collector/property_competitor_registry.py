from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Readiness = Literal["full", "partial", "rules_only", "not_confirmed"]


@dataclass(frozen=True)
class PropertyCompetitorScenario:
    readiness: Readiness
    product_urls: tuple[str, ...] = ()
    rules_urls: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class PropertyCompetitor:
    slug: str
    name: str
    official_domains: tuple[str, ...]
    apartment: PropertyCompetitorScenario
    house: PropertyCompetitorScenario


PROPERTY_COMPETITORS: tuple[PropertyCompetitor, ...] = (
    PropertyCompetitor(
        slug="vsk",
        name="ВСК",
        official_domains=("vsk.ru",),
        apartment=PropertyCompetitorScenario(
            readiness="full",
            product_urls=("https://www.vsk.ru/klientam/imuschestvo",),
            rules_urls=(
                "https://www.vsk.ru/cms/assets/b201287e-6d64-40b5-b73b-2dd198e6a215",
            ),
            notes=(
                "Текущая страница квартиры/апартаментов содержит объекты, риски, "
                "лимиты и урегулирование без справок."
            ),
        ),
        house=PropertyCompetitorScenario(
            readiness="rules_only",
            rules_urls=(
                "https://www.vsk.ru/cms/assets/b201287e-6d64-40b5-b73b-2dd198e6a215",
            ),
            notes=(
                "Правила №199 охватывают жилые дома, коттеджи, таунхаусы, бани "
                "и хозпостройки, но отдельная актуальная публичная страница продукта "
                "для дома не подтверждена."
            ),
        ),
    ),
    PropertyCompetitor(
        slug="ingos",
        name="Ингосстрах",
        official_domains=("ingos.ru", "cdn.ingos.ru"),
        apartment=PropertyCompetitorScenario(
            readiness="partial",
            product_urls=(
                "https://www.ingos.ru/company/news/2026/002e2e55-50e9-49e2-9af6-c217e57af9c8",
            ),
            rules_urls=(
                "https://cdn.ingos.ru/docs/pravila_ot_ognya_fl_4.10.2024.pdf",
            ),
            notes=(
                "Текущая официальная публикация подтверждает страхование квартиры "
                "и онлайн-конструктор; отдельная продуктовая landing page не найдена."
            ),
        ),
        house=PropertyCompetitorScenario(
            readiness="partial",
            product_urls=(
                "https://www.ingos.ru/company/news/2026/002e2e55-50e9-49e2-9af6-c217e57af9c8",
            ),
            rules_urls=(
                "https://cdn.ingos.ru/docs/pravila_ot_ognya_fl_4.10.2024.pdf",
            ),
            notes=(
                "Официальная публикация подтверждает страхование дома и дачи; "
                "правила прямо включают отдельно стоящие жилые дома и постройки."
            ),
        ),
    ),
    PropertyCompetitor(
        slug="renins",
        name="Ренессанс страхование",
        official_domains=("renins.ru", "content.renins.ru"),
        apartment=PropertyCompetitorScenario(
            readiness="partial",
            product_urls=(
                "https://content.renins.ru/kvartira/strahovanie-bpla/",
                "https://content.renins.ru/kvartira/kak-i-ot-chego-mozhno-zastrakhovat-imushchestvo/",
            ),
            rules_urls=(
                "https://www.renins.ru/Media/Default/doc/rules_new/105.pdf",
            ),
            notes=(
                "Текущие официальные материалы подтверждают онлайн-калькулятор "
                "квартиры и опции БПЛА; отдельная landing page продукта не найдена."
            ),
        ),
        house=PropertyCompetitorScenario(
            readiness="partial",
            product_urls=(
                "https://content.renins.ru/kvartira/strahovanie-chastnogo-doma/",
            ),
            rules_urls=(
                "https://www.renins.ru/Media/Default/doc/rules_new/105.pdf",
            ),
            notes=(
                "Официальный материал 2026 года описывает страхование частного дома "
                "и предварительную оценку по фотографиям."
            ),
        ),
    ),
    PropertyCompetitor(
        slug="alfa",
        name="АльфаСтрахование",
        official_domains=("alfastrah.ru",),
        apartment=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://www.alfastrah.ru/individuals/housing/",
                "https://www.alfastrah.ru/individuals/housing/flat/calculator/",
            ),
            notes=(
                "АльфаКВАРТИРА/АльфаРЕМОНТ: конструктив, отделка, имущество, ГО, "
                "дополнительные риски и настраиваемые страховые суммы."
            ),
        ),
        house=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://www.alfastrah.ru/individuals/housing/",
            ),
            notes=(
                "Текущий раздел жилья отдельно подтверждает страхование загородных "
                "домов, коттеджей, дач, оборудования, имущества и хозпостроек."
            ),
        ),
    ),
    PropertyCompetitor(
        slug="soglasie",
        name="Согласие",
        official_domains=("soglasie.ru",),
        apartment=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://www.soglasie.ru/individuals/nedvijimost/",
                "https://www.soglasie.ru/individuals/nedvijimost/moya-kvartira/",
            ),
            notes=(
                "«Моя Квартира» — продукт-конструктор с конструктивом, отделкой, "
                "оборудованием, движимым/ценным имуществом и ГО."
            ),
        ),
        house=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://www.soglasie.ru/individuals/nedvijimost/zagor-dom-classic/",
                "https://www.soglasie.ru/individuals/nedvijimost/zagor-dom-express/",
            ),
            notes=(
                "«Дом Классика» и «Дом Экспресс» покрывают строения, баню/хозпостройки, "
                "движимое имущество и гражданскую ответственность."
            ),
        ),
    ),
    PropertyCompetitor(
        slug="rgs",
        name="Росгосстрах",
        official_domains=("rgs.ru", "life.rgs.ru"),
        apartment=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://life.rgs.ru/property/strakhovanie-kvartiry-online",
                "https://life.rgs.ru/property",
            ),
            rules_urls=(
                "https://www.rgs.ru/about/dokumenty/pravila-strakhovaniya-i-strakhovye-tarify",
            ),
            notes=(
                "Текущий онлайн-продукт квартиры, гибкая настройка рисков и сумм, "
                "оформление без осмотра; действующие правила имущества опубликованы."
            ),
        ),
        house=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://www.rgs.ru/property/strakhovanie-doma-online",
                "https://life.rgs.ru/property",
            ),
            rules_urls=(
                "https://www.rgs.ru/about/dokumenty/pravila-strakhovaniya-i-strakhovye-tarify",
            ),
            notes=(
                "Дом/дача/коттедж/таунхаус, движимое имущество, допстроения, "
                "ландшафт и сервис «Мастер на дом»."
            ),
        ),
    ),
    PropertyCompetitor(
        slug="t-insurance",
        name="Т-Страхование",
        official_domains=("tbank.ru",),
        apartment=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://www.tbank.ru/insurance/property/",
                "https://www.tbank.ru/insurance/help/estate/property/",
            ),
            notes=(
                "Текущий онлайн-продукт: более 25 рисков, БПЛА, ГО, без осмотра, "
                "выплата заявлена в течение недели после документов."
            ),
        ),
        house=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://www.tbank.ru/insurance/property/house/",
                "https://www.tbank.ru/insurance/help/estate/property/",
            ),
            notes=(
                "Дом/дача/коттедж/таунхаус, постройки, конструктив, отделка, "
                "инженерия и БПЛА; для оформления требуются фотографии."
            ),
        ),
    ),
    PropertyCompetitor(
        slug="sber",
        name="СберСтрахование",
        official_domains=("sberbankins.ru",),
        apartment=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://sberbankins.ru/products/home-insurance-online/",
            ),
            notes=(
                "Единый текущий продукт квартиры и дома: без осмотра, настраиваемые "
                "объекты/суммы, вода, пожар, кража, БПЛА и ГО."
            ),
        ),
        house=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://sberbankins.ru/products/home-insurance-online/",
            ),
            notes=(
                "Тот же продукт прямо поддерживает дачный дом/коттедж и заявляет "
                "отдельный лимит защиты дома."
            ),
        ),
    ),
    PropertyCompetitor(
        slug="yugoria",
        name="Югория",
        official_domains=("ugsk.ru",),
        apartment=PropertyCompetitorScenario(
            readiness="rules_only",
            rules_urls=(
                "https://ugsk.ru/pravila/pravila08_7.pdf",
                "https://ugsk.ru/pochtaros/%D0%9A%D0%BB%D1%8E%D1%87%D0%B5%D0%B2%D0%BE%D0%B9%20%D0%B8%D0%BD%D1%84%D0%BE%D1%80%D0%BC%D0%B0%D1%86%D0%B8%D0%BE%D0%BD%D0%BD%D1%8B%D0%B9%20%D0%B4%D0%BE%D0%BA%D1%83%D0%BC%D0%B5%D0%BD%D1%82%20%D0%BF%D0%BE%D1%87%D1%82%D0%B0%20%D0%A0%D0%A4",
            ),
            notes=(
                "Есть официальные правила имущества физлиц и КИД жилого помещения, "
                "но актуальная основная продуктовая страница не подтверждена."
            ),
        ),
        house=PropertyCompetitorScenario(
            readiness="rules_only",
            rules_urls=(
                "https://ugsk.ru/pravila/pravila08_7.pdf",
            ),
            notes=(
                "Общие правила имущества физлиц доступны; актуальный отдельный "
                "продукт для загородного дома публично не подтверждён."
            ),
        ),
    ),
    PropertyCompetitor(
        slug="sovcom",
        name="Совкомбанк Страхование",
        official_domains=("sovcomins.ru",),
        apartment=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://sovcomins.ru/product/property/",
                "https://sovcomins.ru/product/kvartira/",
            ),
            notes=(
                "«Моя квартира» и классическая программа: конструктив, отделка, "
                "имущество, ГО, франшиза, без справок и БПЛА/терроризм."
            ),
        ),
        house=PropertyCompetitorScenario(
            readiness="full",
            product_urls=(
                "https://sovcomins.ru/product/property/",
                "https://sovcomins.ru/product/dom/",
            ),
            notes=(
                "Дом/баня/гараж/хозблок, инженерия, ландшафт, специальные риски, "
                "франшиза и дополнительные расходы."
            ),
        ),
    ),
)


def get_property_competitor(slug: str) -> PropertyCompetitor:
    for competitor in PROPERTY_COMPETITORS:
        if competitor.slug == slug:
            return competitor
    raise KeyError(f"Unknown property competitor: {slug}")


def scenario_readiness(scenario: str) -> dict[str, Readiness]:
    if scenario not in {"apartment", "house"}:
        raise KeyError(f"Unknown property scenario: {scenario}")
    return {
        competitor.slug: getattr(competitor, scenario).readiness
        for competitor in PROPERTY_COMPETITORS
    }


def ready_for_collection(scenario: str) -> tuple[PropertyCompetitor, ...]:
    return tuple(
        competitor
        for competitor in PROPERTY_COMPETITORS
        if getattr(competitor, scenario).readiness in {"full", "partial"}
    )
