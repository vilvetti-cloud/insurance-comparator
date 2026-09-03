# app.py — АГЕНТ ДЛЯ СРАВНЕНИЯ КАСКО
# Источники: официальные сайты → агрегаторы → обзоры → отзывы → ЦБ → DuckDuckGo → fallback

from flask import Flask, render_template, request
from datetime import datetime
import json
import os
import requests
from bs4 import BeautifulSoup
import re
import time
import urllib3
from duckduckgo_search import DDGS

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==================== ЗАПАСНЫЕ ДАННЫЕ ====================

def get_fallback_data():
    return {
        "РЕСО-Гарантия": {
            "franchise": "Безусловная / условно-безусловная (с 1-го или со 2-го случая)",
            "without_certificates": "Стекла без ограничений; 1 кузовной элемент в год",
            "gap": "Отдельный риск",
            "total_loss": "75%",
            "fire": "Входит",
            "terrorism": "Входит",
            "drone": "Лимит 1% СС",
            "tow_truck": "Лимит 1% СС",
            "repair_type": "Ремонт у официального дилера",
            "payment_terms": "5 рабочих дней",
            "advantages": "Ремонт у дилера, 5 дней на выплату, без учета износа",
            "weak_points": "Требуется уточнение условий по телефону",
            "rating": "4.5",
            "offices": "1200+"
        },
        "СОГАЗ": {
            "franchise": "Безусловная / условно-безусловная / динамическая",
            "without_certificates": "Вариантно: 1 раз один элемент / Неограниченно стекла + 1 раз кузовной",
            "gap": "Указывается отдельным риском",
            "total_loss": "70%",
            "fire": "Входит",
            "terrorism": "Исключение",
            "drone": "Исключение",
            "tow_truck": "Лимит 0,5% от СС",
            "repair_type": "Ремонт на СТОА страховщика",
            "payment_terms": "30 рабочих дней",
            "advantages": "Гибкие условия, надёжность",
            "weak_points": "Тотал 70%, срок выплаты 30 дней",
            "rating": "4.3",
            "offices": "500+"
        },
        "АльфаСтрахование": {
            "franchise": "Условно-безусловная (применяется к Хищению)",
            "without_certificates": "Стекла без ограничений + 1 кузовной элемент 2 раза в год",
            "gap": "Включен по умолчанию",
            "total_loss": "75%",
            "fire": "За доп. плату, 0,8% от СС",
            "terrorism": "За доп. плату, 0,2-0,3% от СС",
            "drone": "За доп. плату",
            "tow_truck": "Петковые ТС - 5 000 руб.; Прочие - 10 000 руб.",
            "repair_type": "Ремонт на СТОА страховщика",
            "payment_terms": "7 рабочих дней",
            "advantages": "Без справок с бонусами",
            "weak_points": "Франшиза действует на Хищение, самовозгорание - за доп. плату",
            "rating": "4.6",
            "offices": "600+"
        },
        "Ингосстрах": {
            "franchise": "Условная/условно-безусловная по каждому случаю или со 2-го случая",
            "without_certificates": "1 раз в год: ЛПКП не более 1-й детали; остекление кузова",
            "gap": "Включен при отметке «Постоянная страховая сумма»",
            "total_loss": "75%",
            "fire": "Входит",
            "terrorism": "За доп. плату, 0,3%",
            "drone": "За доп. плату",
            "tow_truck": "По запросу",
            "repair_type": "Ремонт на СТОА страховщика",
            "payment_terms": "10 рабочих дней",
            "advantages": "Широкая сеть офисов, гибкие условия",
            "weak_points": "Без справок – только ЛКП 1 детали, возможны ограничения по пробегу",
            "rating": "4.4",
            "offices": "900+"
        },
        "Ренессанс": {
            "franchise": "11 видов франшиз (безусловная, франшиза виновника, со 2-го случая)",
            "without_certificates": "Вариативно (стекла 1 раз в год / без ограничений / до 5% СС 2 раза)",
            "gap": "Отдельный риск",
            "total_loss": "75%",
            "fire": "Только для электромобилей",
            "terrorism": "За доп. плату, 0,5% от СС на легковые ТС",
            "drone": "За доп. плату, 0,5% от СС на легковые",
            "tow_truck": "Петковые ТС - лимит 10 000 руб.",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "10 рабочих дней",
            "advantages": "Много вариантов франшизы, гибкие условия",
            "weak_points": "Франшиза по хищению/угону, эвакуация - за доп. плату",
            "rating": "4.3",
            "offices": "500+"
        },
        "Т-Страхование": {
            "franchise": "Условно-безусловная (для ТС старше 5 лет - обязательные франшизы)",
            "without_certificates": "Стекла: неогранич. кол-во раз; Кузовные элементы: 1 раз в год - до 3% от СС",
            "gap": "Отдельный риск",
            "total_loss": "65%",
            "fire": "Нет инф.",
            "terrorism": "Нет инф.",
            "drone": "Нет инф.",
            "tow_truck": "Лимит 10 000 руб.",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "5 рабочих дней",
            "advantages": "Онлайн-оформление, без справок",
            "weak_points": "Ниже порог тотала, обязательные франшизы для некоторых сегментов",
            "rating": "4.7",
            "offices": "онлайн"
        },
        "ВСК": {
            "franchise": "Условно-безусловная (может не применяться по отдельным рискам)",
            "without_certificates": "Стекла: 5% СС (неагрегатная); Прочие элементы: 3% СС (агрегатная)",
            "gap": "Включен, если указан 1 период страхования (1 год)",
            "total_loss": "75%",
            "fire": "Исключение из страхового покрытия",
            "terrorism": "Исключение из страхового покрытия",
            "drone": "Включен при наличии в полисе GAP и отметки официальный дилер",
            "tow_truck": "Петковые ТС - лимит 5 000 руб.; Прочие - лимит 15 000 руб.",
            "repair_type": "Ремонт на СТОА страховщика",
            "payment_terms": "10 рабочих дней",
            "advantages": "Гибкие условия по справкам",
            "weak_points": "Камеры кругового обзора не оплачиваются без справок, самовозгорание - исключено",
            "rating": "4.2",
            "offices": "800+"
        },
        "Согласие": {
            "franchise": "Условно-безусловная / динамическая",
            "without_certificates": "Неограниченно стекла (искл. крыша и люк) + 1 раз любой элемент",
            "gap": "В разделе 'Условия страхования' указывается как риск ГЭП",
            "total_loss": "70%",
            "fire": "За доп. плату, 1.15% для ФЛ",
            "terrorism": "За доп. плату, тариф 1.1% только для МСК и МО",
            "drone": "За доп. плату",
            "tow_truck": "5 000 руб. (до 3,5 т); 10 000 руб. (свыше 3,5 т)",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "10 рабочих дней",
            "advantages": "Гибкие условия",
            "weak_points": "Тотал 70% (РЕСО 75%), эвакуатор 5 000 руб. (ниже РЕСО)",
            "rating": "4.2",
            "offices": "300+"
        },
        "Югория": {
            "franchise": "Условно-безусловная (при пролонгации - 3% от СС на каждый случай)",
            "without_certificates": "Стекла: 1 раз (исключая панорамную крышу)",
            "gap": "По типу страховой суммы: неагрегатная - изменяющаяся",
            "total_loss": "Не указан",
            "fire": "Исключение из покрытия",
            "terrorism": "Нет инф.",
            "drone": "Входит",
            "tow_truck": "Лимит 5% от СС, но не более 15 000 рублей",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "10 рабочих дней",
            "advantages": "Гибкие условия пролонгации",
            "weak_points": "При пролонгации возможна доп. франшиза, самовозгорание исключено",
            "rating": "3.9",
            "offices": "400+"
        },
        "СберСтрахование": {
            "franchise": "6 видов франшиз (условная, безусловная, динамическая, со 2-го случая, агрегатная)",
            "without_certificates": "Вариантно: 1 раз - 1 деталь кузова + стекла / Только стекла",
            "gap": "Включен, если СС индексируемая",
            "total_loss": "70%",
            "fire": "Исключение",
            "terrorism": "Исключение",
            "drone": "Исключение",
            "tow_truck": "Петковые ТС - 6 000 руб.; Грузовые - 12 000 руб.",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "7 рабочих дней",
            "advantages": "Много вариантов франшизы",
            "weak_points": "Тотал 70% (РЕСО 75%), аваром/эвакуация могут быть исключены",
            "rating": "4.0",
            "offices": "1000+"
        },
        "Совкомбанк Страхование": {
            "franchise": "Условно-безусловная / Условная по отдельным группам / Обязательная 25%",
            "without_certificates": "Только ремонт или замена ветрового стекла",
            "gap": "Нет инф.",
            "total_loss": "75%",
            "fire": "Входит в группу событий №2",
            "terrorism": "Исключение",
            "drone": "Исключение",
            "tow_truck": "Лимит 6 500 руб.",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "10 рабочих дней",
            "advantages": "Группы событий",
            "weak_points": "Терроризм исключен, обязательная франшиза",
            "rating": "3.8",
            "offices": "200+"
        }
    }

# ==================== ИСТОЧНИКИ ====================

# УРОВЕНЬ 1: Официальные страницы "Раскрытие информации"
OFFICIAL_SOURCES = {
    "ВСК": ["https://www.vsk.ru/o-kompanii/dlya-kliyentov?t=pravila_i_tarifi_strahovaniya&case=pravila"],
    "Ингосстрах": ["https://www.ingos.ru/company/disclosure-info/insurance-rules/"],
    "АльфаСтрахование": ["https://alfastrah.ru/rules/avtomobil/kasko/"],
    "СОГАЗ": ["https://www.sogaz.ru/"],
    "Согласие": ["https://soglasie.ru/company/insurance-rules/"],
    "Югория": ["https://ugsk.ru/about/disclosure-information/rules/"],
    "Совкомбанк Страхование": ["https://casco.sovcombank.ru/"],
    "РЕСО-Гарантия": ["https://reso.ru/"],
    "Ренессанс": ["https://renessans.sddbk.ru/imushestvo/kvartira/"],
    "Т-Страхование": ["https://tbank.ru/insurance/help/estate/property/about/about-policy/"],
    "СберСтрахование": ["https://sberbankins.ru/products/home-insurance-online/"]
}

# УРОВЕНЬ 2: Агрегаторы правил
AGGREGATOR_SOURCES = [
    {"name": "kaskometr", "url": "https://kaskometr.ru/pravila/", "slug_style": "name"},
    {"name": "finuslugi", "url": "https://finuslugi.ru/pravila_kasko/", "slug_style": "name"},
    {"name": "asccenter", "url": "https://asccenter.ru/info/docs/pravila-tarify-kasko/", "slug_style": "name"},
    {"name": "kupipolis", "url": "https://kupipolis.ru/pravila-strahovaniya/", "slug_style": "name"}
]

# УРОВЕНЬ 3: Сравнительные обзоры
REVIEW_SOURCES = [
    "https://polis.online",
    "https://polis812.ru",
    "https://infullbroker.ru"
]

# УРОВЕНЬ 4: Отзывы клиентов
FEEDBACK_SOURCES = [
    "https://sravni.ru"
]

# УРОВЕНЬ 5: Банк России (статистика жалоб)
CBR_URL = "https://cbr.ru"

# ==================== ПАРСИНГ ====================

# LLM-парсинг через Groq (бесплатный)
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

PROVIDER_CONFIG = {
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions", "key_env": "GROQ_API_KEY", "model": GROQ_MODEL},
}

EXTRACT_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "extract_insurance_fields",
        "description": "Извлекает условия автостраховки КАСКО из текста.",
        "parameters": {
            "type": "object",
            "properties": {
                "franchise": {"type": "string", "description": "Тип и размер франшизы"},
                "without_certificates": {"type": "string", "description": "Условия выплаты без справок"},
                "gap": {"type": "string", "description": "Наличие и условия GAP-страхования"},
                "total_loss": {"type": "string", "description": "Порог полной гибели/тотала в % от страховой суммы"},
                "fire": {"type": "string", "description": "Условия покрытия самовозгорания"},
                "terrorism": {"type": "string", "description": "Условия покрытия риска терроризма"},
                "drone": {"type": "string", "description": "Условия покрытия ущерба от БПЛА/дронов"},
                "tow_truck": {"type": "string", "description": "Условия оплаты эвакуатора"},
                "repair_type": {"type": "string", "description": "Где производится ремонт (СТОА, дилер, выплата)"},
                "payment_terms": {"type": "string", "description": "Срок выплаты возмещения в рабочих днях"},
            },
            "required": []
        }
    }
}

def fetch_page(url, use_js=False):
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'}, verify=False)
        return response.text
    except Exception as e:
        print(f"      ⚠️ Ошибка загрузки {url}: {e}")
        return None
        
def parse_with_llm(text):
    """Универсальный LLM-парсинг через Groq"""
    provider = PROVIDER_CONFIG.get(LLM_PROVIDER)
    if not provider:
        return None
    api_key = os.environ.get(provider["key_env"])
    if not api_key:
        return None
    try:
        response = requests.post(
            provider["url"],
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": provider["model"],
                "messages": [{"role": "user", "content": "Извлеки условия КАСКО из текста. Заполни только то, что явно указано, ничего не выдумывай:\n\n" + text[:6000]}],
                "tools": [EXTRACT_TOOL_SCHEMA],
                "tool_choice": "auto",
            },
            timeout=20,
        )
        if not response.ok:
            return None
        choices = response.json().get("choices") or []
        message = (choices[0] or {}).get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return None
        raw = json.loads(tool_calls[0]["function"]["arguments"])
        return {k: v for k, v in raw.items() if isinstance(v, str) and v.strip() and "не найдено" not in v.lower()}
    except Exception:
        return None

def parse_url_with_llm(url, use_js=False):
    """Парсит URL через LLM"""
    html = fetch_page(url, use_js)
    if not html:
        return None
    blocks = clean_text_blocks(html)
    if len(blocks) < 5:
        return None
    return parse_with_llm("\n".join(blocks))

def company_slug(company_name):
    """Генерирует slug для URL"""
    mapping = {
        "РЕСО-Гарантия": "reso-garantiya",
        "СОГАЗ": "sogaz",
        "АльфаСтрахование": "alfa-strakhovanie",
        "Ингосстрах": "ingosstrakh",
        "Ренессанс": "renessans",
        "Т-Страхование": "t-strakhovanie",
        "ВСК": "vsk",
        "Согласие": "soglasie",
        "Югория": "yugoria",
        "СберСтрахование": "sber",
        "Совкомбанк Страхование": "sovcombank"
    }
    return mapping.get(company_name, company_name.lower().replace(" ", "-"))

def parse_official(company_name):
    """Уровень 1: Официальные сайты"""
    if company_name not in OFFICIAL_SOURCES:
        return None
    print(f"   🔍 Уровень 1: Официальный сайт...")
    for url in OFFICIAL_SOURCES[company_name]:
        result = parse_url_with_llm(url, use_js=False)
        if result:
            return result
    return None

def parse_aggregators(company_name):
    """Уровень 2: Агрегаторы правил"""
    print(f"   🔍 Уровень 2: Агрегаторы...")
    slug = company_slug(company_name)
    for agg in AGGREGATOR_SOURCES:
        url = f"{agg['url']}{slug}/"
        print(f"      📊 {agg['name']}: {url}")
        result = parse_url_with_llm(url)
        if result:
            return result
    return None

def parse_reviews(company_name):
    """Уровень 3: Сравнительные обзоры"""
    print(f"   🔍 Уровень 3: Обзоры...")
    for base_url in REVIEW_SOURCES:
        url = f"{base_url}/kasko/{company_slug(company_name)}/"
        print(f"      📰 {base_url}: {url}")
        result = parse_url_with_llm(url)
        if result:
            return result
    return None

def parse_feedback(company_name):
    """Уровень 4: Отзывы клиентов"""
    print(f"   🔍 Уровень 4: Отзывы...")
    for base_url in FEEDBACK_SOURCES:
        url = f"{base_url}/strahovanie/avto/kasko/{company_slug(company_name)}/"
        print(f"      💬 {base_url}: {url}")
        result = parse_url_with_llm(url)
        if result:
            return result
    return None

def parse_cbr(company_name):
    """Уровень 5: Банк России"""
    print(f"   🔍 Уровень 5: Банк России...")
    url = f"{CBR_URL}/statistics/"
    result = parse_url_with_llm(url)
    if result:
        return result
    return None

def parse_duckduckgo(company_name):
    """Уровень 6: DuckDuckGo поиск"""
    print(f"   🔍 Уровень 6: DuckDuckGo...")
    query = f"КАСКО {company_name} условия 2026"
    print(f"      🔎 {query}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            for r in results[:3]:
                url = r.get('href')
                if url:
                    print(f"      🌐 {url}")
                    result = parse_url_with_llm(url)
                    if result:
                        return result
    except Exception as e:
        print(f"      ⚠️ DuckDuckGo ошибка: {e}")
    return None

def parse_company(company_name):
    """Полная цепочка поиска для одной компании"""
    print(f"\n🏢 {company_name}")
    
    # Уровень 1: Официальный сайт
    result = parse_official(company_name)
    if result:
        print(f"   ✅ Данные найдены (официальный сайт)")
        return result
    
    # Уровень 2: Агрегаторы
    result = parse_aggregators(company_name)
    if result:
        print(f"   ✅ Данные найдены (агрегатор)")
        return result
    
    # Уровень 3: Обзоры
    result = parse_reviews(company_name)
    if result:
        print(f"   ✅ Данные найдены (обзор)")
        return result
    
    # Уровень 4: Отзывы
    result = parse_feedback(company_name)
    if result:
        print(f"   ✅ Данные найдены (отзывы)")
        return result
    
    # Уровень 5: Банк России
    result = parse_cbr(company_name)
    if result:
        print(f"   ✅ Данные найдены (ЦБ)")
        return result
    
    # Уровень 6: DuckDuckGo
    result = parse_duckduckgo(company_name)
    if result:
        print(f"   ✅ Данные найдены (DuckDuckGo)")
        return result
    
    # Уровень 7: Запасные данные
    print(f"   📦 Использованы запасные данные")
    return get_fallback_data().get(company_name, {})

def parse_all_companies(company_list):
    """Парсит все компании"""
    print("🔄 Сбор данных...")
    data = {}
    for company in company_list:
        result = parse_company(company)
        if result:
            data[company] = result
        time.sleep(0.5)
    data["_last_updated"] = datetime.now().isoformat()
    return data

# ==================== ДАННЫЕ ====================

ALL_COMPANIES = list(get_fallback_data().keys())
print("📦 Загрузка данных...")
INSURANCE_DATA = parse_all_companies(ALL_COMPANIES)
print(f"✅ Загружено {len(INSURANCE_DATA)} компаний")

# ==================== МАРШРУТЫ ====================

@app.route('/')
def index():
    last_updated = INSURANCE_DATA.get("_last_updated", "неизвестно")
    return render_template('index.html', 
                         companies=ALL_COMPANIES,
                         now=datetime.now().strftime("%Y-%m-%d %H:%M"),
                         last_updated=last_updated)

@app.route('/compare', methods=['POST'])
def compare():
    company1 = request.form.get('company1')
    company2 = request.form.get('company2')
    
    if not company1 or not company2:
        return "Выберите обе компании!", 400
    
    data1 = INSURANCE_DATA.get(company1, {})
    data2 = INSURANCE_DATA.get(company2, {})
    
    advantages = []
    total1 = data1.get("total_loss", "0%").replace("%", "")
    total2 = data2.get("total_loss", "0%").replace("%", "")
    if total1.isdigit() and total2.isdigit():
        if int(total1) > int(total2):
            advantages.append(f"✅ {company1} лучше по порогу тотала: {total1}% vs {total2}%")
    
    return render_template('result.html',
                         company1=company1,
                         company2=company2,
                         data1=data1,
                         data2=data2,
                         advantages=advantages,
                         timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# ==================== ШАБЛОНЫ ====================

os.makedirs('templates', exist_ok=True)

with open('templates/index.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Сравнение КАСКО</title>
<style>
body{font-family:Arial;padding:10px;background:#f5f5f5}
.container{max-width:500px;margin:0 auto;background:white;padding:20px;border-radius:10px}
h1{font-size:20px;text-align:center;color:#2c3e50}
select{width:100%;padding:12px;margin:8px 0;border:1px solid #ddd;border-radius:8px}
.btn{width:100%;padding:14px;background:#27ae60;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer}
.btn:hover{background:#219a52}
.vs{text-align:center;font-size:24px;color:#e74c3c;margin:5px 0}
.meta{text-align:center;color:#888;font-size:11px;margin-top:15px}
.update-info{text-align:center;color:#27ae60;font-size:12px;margin-top:5px}
</style>
</head>
<body>
<div class="container">
<h1>🔍 Сравнение КАСКО</h1>
<p style="text-align:center;color:#555;">Выберите две страховые компании для сравнения</p>
<div class="update-info">🤖 Данные собираются автоматически</div>
<div class="update-info">📅 Последнее обновление: {{ last_updated[:16] if last_updated != 'неизвестно' else 'неизвестно' }}</div>
<form method="post" action="/compare">
<select name="company1" required>
<option value="">-- Компания А --</option>{% for c in companies %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
</select>
<div class="vs">⚔️</div>
<select name="company2" required>
<option value="">-- Компания Б --</option>{% for c in companies %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
</select>
<button type="submit" class="btn">Сравнить →</button>
</form>
<div class="meta">Обновлено: {{ now }}</div>
</div>
</body>
</html>
''')

with open('templates/result.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Результат сравнения</title>
<style>
body{font-family:Arial;padding:10px;background:#f5f5f5}
.container{max-width:800px;margin:0 auto;background:white;padding:20px;border-radius:10px}
h1{font-size:20px;text-align:center}
table{width:100%;border-collapse:collapse;font-size:13px;margin:10px 0}
th,td{border:1px solid #ddd;padding:6px;text-align:left;vertical-align:top}
th{background:#2c3e50;color:white}
.vs-title{text-align:center;font-size:18px;font-weight:bold;margin:10px 0;padding:10px;background:#f0f8ff;border-radius:8px}
.main-badge{background:#27ae60;color:white;padding:3px 10px;border-radius:12px;font-size:12px;margin-left:10px}
.advantage{color:#27ae60}
.back{display:inline-block;margin-top:10px;color:#3498db;text-decoration:none}
.meta{text-align:center;color:#888;font-size:11px;margin-top:15px}
</style>
</head>
<body>
<div class="container">
<h1>📊 Результат сравнения</h1>
<div class="vs-title">🏆 {{ company1 }} <span class="main-badge">ОСНОВНАЯ</span><br>⚔️ {{ company2 }}</div>
<table>
<tr><th>Параметр</th><th>{{ company1 }}</th><th>{{ company2 }}</th></tr>
<tr><td><strong>Франшиза</strong></td><td>{{ data1.franchise or '—' }}</td><td>{{ data2.franchise or '—' }}</td></tr>
<tr><td><strong>Без справок</strong></td><td>{{ data1.without_certificates or '—' }}</td><td>{{ data2.without_certificates or '—' }}</td></tr>
<tr><td><strong>GAP</strong></td><td>{{ data1.gap or '—' }}</td><td>{{ data2.gap or '—' }}</td></tr>
<tr><td><strong>Порог тотала</strong></td><td>{{ data1.total_loss or '—' }}</td><td>{{ data2.total_loss or '—' }}</td></tr>
<tr><td><strong>Самовозгорание</strong></td><td>{{ data1.fire or '—' }}</td><td>{{ data2.fire or '—' }}</td></tr>
<tr><td><strong>Терроризм</strong></td><td>{{ data1.terrorism or '—' }}</td><td>{{ data2.terrorism or '—' }}</td></tr>
<tr><td><strong>БПЛА</strong></td><td>{{ data1.drone or '—' }}</td><td>{{ data2.drone or '—' }}</td></tr>
<tr><td><strong>Эвакуатор</strong></td><td>{{ data1.tow_truck or '—' }}</td><td>{{ data2.tow_truck or '—' }}</td></tr>
<tr><td><strong>Тип ремонта</strong></td><td>{{ data1.repair_type or '—' }}</td><td>{{ data2.repair_type or '—' }}</td></tr>
<tr><td><strong>Срок выплаты</strong></td><td>{{ data1.payment_terms or '—' }}</td><td>{{ data2.payment_terms or '—' }}</td></tr>
<tr><td><strong>Рейтинг</strong></td><td>{{ data1.rating or '—' }}</td><td>{{ data2.rating or '—' }}</td></tr>
<tr><td><strong>Офисы</strong></td><td>{{ data1.offices or '—' }}</td><td>{{ data2.offices or '—' }}</td></tr>
<tr><td><strong>Преимущества</strong></td><td>{{ data1.advantages or '—' }}</td><td>{{ data2.advantages or '—' }}</td></tr>
<tr><td><strong>Слабые места</strong></td><td style="color:#e74c3c;">{{ data1.weak_points or '—' }}</td><td style="color:#e74c3c;">{{ data2.weak_points or '—' }}</td></tr>
</table>
<div class="analysis"><strong>📋 Анализ</strong><ul>{% for adv in advantages %}<li class="advantage">{{ adv }}</li>{% endfor %}</ul></div>
<a href="/" class="back">← На главную</a>
<div class="meta">Обновлено: {{ timestamp }}</div>
</div>
</body>
</html>
''')
