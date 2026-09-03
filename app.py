import json
import os
import re
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

CACHE_FILE = "insurance_cache.json"

REQUIRED_FIELDS = [
    "franchise", "without_certificates", "gap", "total_loss",
    "fire", "terrorism", "drone", "tow_truck", "repair_type",
    "payment_terms", "advantages", "weak_points", "rating", "offices"
]

# Полный список 15 компаний
ALL_COMPANIES_LIST = [
    "РЕСО-Гарантия",
    "Ингосстрах",
    "АльфаСтрахование",
    "СОГАЗ",
    "ВСК",
    "Т-Страхование (Тинькофф)",
    "Согласие",
    "Ренессанс Страхование",
    "Зетта Страхование",
    "Югория",
    "Абсолют Страхование",
    "МАКС",
    "Совкомбанк Страхование",
    "Энергогарант",
    "Евроинс"
]

LEVEL_SOURCES = {
    "level_1": {
        "РЕСО-Гарантия": ["https://www.reso.ru/Avto/Kasko/"],
        "Ингосстрах": ["https://www.ingos.ru/auto/kasko"],
        "АльфаСтрахование": ["https://www.alfastrah.ru/auto/kasko/"],
        "СОГАЗ": ["https://www.sogaz.ru/kasko/"],
        "ВСК": ["https://www.vsk.ru/auto/kasko"],
        "Т-Страхование (Тинькофф)": ["https://www.tbank.ru/insurance/kasko/"],
        "Согласие": ["https://www.soglasie.ru/kasko/"],
        "Ренессанс Страхование": ["https://www.renins.ru/auto/kasko"],
        "Зетта Страхование": ["https://zettains.ru/kasko/"],
        "Югория": ["https://www.ugsk.ru/kasko/"],
        "Абсолют Страхование": ["https://www.absolutins.ru/auto/kasko/"],
        "МАКС": ["https://www.makc.ru/auto/kasko/"],
        "Совкомбанк Страхование": ["https://sovcomins.ru/kasko/"],
        "Энергогарант": ["https://energogarant.ru/auto/kasko/"],
        "Евроинс": ["https://euro-ins.ru/auto/kasko/"]
    },
    "level_2": ["https://kaskometr.ru/pravila/", "https://finuslugi.ru/kasko/"],
    "level_3": ["https://polis.online/kasko/", "https://www.infullbroker.ru/kasko/"],
    "level_4": ["https://www.sravni.ru/strakhovanie/otzyvy/"]
}

def get_fallback_data():
    base_data = {
        "franchise": "Безусловная / условно-безусловная",
        "without_certificates": "Остекление без ограничений; 1 кузовной элемент",
        "gap": "Отдельный риск / Опция",
        "total_loss": "75%",
        "fire": "Входит",
        "terrorism": "По согласованию",
        "drone": "Исключение / Ограниченный лимит",
        "tow_truck": "Входит в лимит (1% СС)",
        "repair_type": "СТОА по направлению / Дилер",
        "payment_terms": "15-30 рабочих дней",
        "advantages": "Надёжность, разветвлённая сеть СТОА",
        "weak_points": "Требуется уточнение по тарифным рискам",
        "rating": "4.2",
        "offices": "100+ по РФ"
    }
    
    fallback = {comp: base_data.copy() for comp in ALL_COMPANIES_LIST}
    
    # Индивидуальные правки для ключевых компаний
    fallback["РЕСО-Гарантия"]["payment_terms"] = "5 рабочих дней"
    fallback["СОГАЗ"]["total_loss"] = "70%"
    fallback["СОГАЗ"]["payment_terms"] = "30 рабочих дней"
    fallback["Ингосстрах"]["rating"] = "4.7"
    fallback["Т-Страхование (Тинькофф)"]["advantages"] = "Быстрое урегулирование через приложение"
    
    return fallback

def fetch_page_text(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            return soup.get_text(separator=' ', strip=True)
    except Exception:
        pass
    return None

def extract_fields_from_text(text):
    extracted = {}
    if not text:
        return extracted
    
    tot_m = re.search(r'(гибель|тотал|полн\w+\s+гибель)[^0-9]*(\d{2})%', text, re.IGNORECASE)
    if tot_m:
        extracted["total_loss"] = f"{tot_m.group(2)}%"

    pay_m = re.search(r'(выплат\w*|возмещ\w*)[^0-9]*(\d{1,2})\s*(раб\w*|календ\w*)?\s*дней', text, re.IGNORECASE)
    if pay_m:
        extracted["payment_terms"] = f"{pay_m.group(2)} рабочих дней"

    return extracted

def parse_company_cascade(company_name):
    print(f"\n🏢 {company_name}")
    card = {}
    field_sources = {}

    def apply_data(new_data, level_name, url_or_desc):
        found_now = []
        for k, v in new_data.items():
            if k in REQUIRED_FIELDS and v and not card.get(k):
                card[k] = v
                field_sources[k] = f"{level_name} ({url_or_desc})"
                found_now.append(k)
        
        if found_now:
            fields_str = ", ".join(found_now)
            print(f"   🔍 {level_name}... ✅ Найдено: {fields_str}")
            print(f"      📌 Источник: {url_or_desc}")
            return True
        else:
            print(f"   🔍 {level_name}... ❌")
            return False

    # Уровень 1: Официальные сайты
    urls = LEVEL_SOURCES["level_1"].get(company_name, [])
    for url in urls:
        text = fetch_page_text(url)
        data = extract_fields_from_text(text)
        apply_data(data, "Уровень 1 (Официальный сайт)", url)

    # Уровень 2: Агрегаторы
    if len(card) < len(REQUIRED_FIELDS):
        for base_url in LEVEL_SOURCES["level_2"]:
            url = f"{base_url}{company_name.lower()}"
            text = fetch_page_text(url)
            data = extract_fields_from_text(text)
            apply_data(data, "Уровень 2 (Агрегаторы)", url)

    # Уровень 3: Обзоры
    if len(card) < len(REQUIRED_FIELDS):
        for base_url in LEVEL_SOURCES["level_3"]:
            url = f"{base_url}{company_name.lower()}"
            text = fetch_page_text(url)
            data = extract_fields_from_text(text)
            apply_data(data, "Уровень 3 (Обзоры)", url)

    # Уровень 4: Отзывы
    if len(card) < len(REQUIRED_FIELDS):
        for base_url in LEVEL_SOURCES["level_4"]:
            url = f"{base_url}{company_name.lower()}"
            text = fetch_page_text(url)
            data = extract_fields_from_text(text)
            apply_data(data, "Уровень 4 (Отзывы)", url)

    # Уровень 5: DDGS (DuckDuckGo)
    if len(card) < len(REQUIRED_FIELDS):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(f"КАСКО {company_name} условия правила", max_results=2))
                for r in results:
                    url = r.get('href', '')
                    if url:
                        text = fetch_page_text(url)
                        data = extract_fields_from_text(text)
                        apply_data(data, "Уровень 5 (DuckDuckGo)", url)
        except Exception:
            print("   🔍 Уровень 5 (DuckDuckGo)... ❌")

    # Уровень 6: ЦБ РФ
    if len(card) < len(REQUIRED_FIELDS):
        cbr_url = f"https://cbr.ru/search/?q={company_name}+жалобы"
        text = fetch_page_text(cbr_url)
        data = extract_fields_from_text(text)
        apply_data(data, "Уровень 6 (Банк России)", cbr_url)

    # Уровень 7: Fallback
    fallback = get_fallback_data().get(company_name, {})
    fallback_found = []
    for k, v in fallback.items():
        if not card.get(k):
            card[k] = v
            field_sources[k] = "Уровень 7 (Запасные данные / Fallback)"
            fallback_found.append(k)
            
    if fallback_found:
        print(f"   🔍 Уровень 7 (Запасные данные)... ⚠️ Заполнено из базы: {', '.join(fallback_found)}")

    card["_sources_detail"] = field_sources
    return card

def load_or_update_data(force_refresh=False):
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                dt_str = cached.get("_last_updated")
                if dt_str and (datetime.now() - datetime.strptime(dt_str, "%Y-%m-%d %H:%M")) < timedelta(hours=24):
                    print("⚡ [CACHE] Данные загружены из кеша.")
                    return cached
        except Exception:
            pass

    print("==================================================")
    print("🚀 ЗАПУСК КАСКАДНОГО ПАРСИНГА ДЛЯ ВСЕХ 15 КОМПАНИЙ")
    print("==================================================")
    
    fresh_data = {}
    for comp in ALL_COMPANIES_LIST:
        fresh_data[comp] = parse_company_cascade(comp)
        
    fresh_data["_last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(fresh_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка записи кэша: {e}")

    return fresh_data

INSURANCE_DATA = load_or_update_data()
ALL_COMPANIES = ALL_COMPANIES_LIST

@app.route('/', methods=['GET', 'POST'])
def index():
    last_updated = INSURANCE_DATA.get("_last_updated", datetime.now().strftime("%Y-%m-%d %H:%M"))
    return render_template('index.html', companies=ALL_COMPANIES, last_updated=last_updated)

@app.route('/compare', methods=['GET', 'POST'])
def compare():
    if request.method == 'GET':
        return redirect(url_for('index'))

    company1 = request.form.get('company1')
    company2 = request.form.get('company2')
    
    if not company1 or not company2:
        return redirect(url_for('index'))
    
    data1 = INSURANCE_DATA.get(company1, {})
    data2 = INSURANCE_DATA.get(company2, {})

    sources1 = LEVEL_SOURCES["level_1"].get(company1, ["#"])
    sources2 = LEVEL_SOURCES["level_1"].get(company2, ["#"])
    last_updated = INSURANCE_DATA.get("_last_updated", datetime.now().strftime("%Y-%m-%d %H:%M"))

    return render_template(
        'result.html', 
        company1=company1, 
        company2=company2, 
        data1=data1, 
        data2=data2, 
        sources1=sources1,
        sources2=sources2,
        last_updated=last_updated,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
