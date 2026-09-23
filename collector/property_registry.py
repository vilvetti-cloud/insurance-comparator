from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PropertyScenarioConfig:
    insurer_slug: str
    insurer_name: str
    scenario: str
    product_name: str
    product_slug: str
    product_url: str
    rules_urls: tuple[str, ...]
    additional_urls: tuple[str, ...] = ()


RESO_PROPERTY_RULES = (
    "https://reso.ru/about/rules/individual/property/imushestva-fizlic-03-2025.pdf"
)
RESO_LIABILITY_RULES = "https://reso.ru/about/rules/individual/go_01-04-2023.pdf"

RESO_PROPERTY_SCENARIOS = {
    "apartment": PropertyScenarioConfig(
        insurer_slug="reso",
        insurer_name="РЕСО-Гарантия",
        scenario="apartment",
        product_name="Домовой",
        product_slug="domovoy",
        product_url="https://reso.ru/individual/property/flat/",
        rules_urls=(RESO_PROPERTY_RULES, RESO_LIABILITY_RULES),
        additional_urls=(
            "https://reso.ru/individual/property/flat/faq/",
            "https://reso.ru/individual/property/flat/bpla/",
            "https://reso.ru/individual/property/flat/domovoy-servis/",
            "https://reso.ru/individual/property/flat/domovoy-otpusk/",
            "https://reso.ru/individual/property/flat/vse-vklucheno/",
        ),
    ),
    "house": PropertyScenarioConfig(
        insurer_slug="reso",
        insurer_name="РЕСО-Гарантия",
        scenario="house",
        product_name="РЕСО-Дом",
        product_slug="reso-dom",
        product_url="https://reso.ru/individual/property/reso-dom/",
        rules_urls=(RESO_PROPERTY_RULES, RESO_LIABILITY_RULES),
        additional_urls=(
            "https://reso.ru/individual/property/reso-dom/faq/",
            "https://reso.ru/individual/property/reso-dom/reso-dom-express/",
            "https://reso.ru/individual/property/reso-dom/reso-dom-express/faq/",
        ),
    ),
}


def get_reso_property_scenario(scenario: str) -> PropertyScenarioConfig:
    try:
        return RESO_PROPERTY_SCENARIOS[scenario]
    except KeyError as exc:
        raise KeyError(f"Unknown RESO property scenario: {scenario}") from exc
