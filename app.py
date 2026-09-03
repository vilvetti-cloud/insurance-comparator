import json
import os
import re
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

CACHE_FILE = "insurance_cache.json"

# ==================== ДАННЫЕ И ИСТОЧНИКИ ====================

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
            "tow_truck": "Легковые ТС - 5 000 руб.; Прочие - 10 000 руб.",
            "repair_type": "Ремонт на СТОА страховщика",
            "payment_terms": "7 рабочих дней",
            "advantages": "Без справок с бонусами",
            "weak_points": "Франшиза на Хищение, самовозгорание - за доп. плату",
            "rating": "4.6",
            "offices": "600+"
        },
        "Ингосстрах": {
            "franchise": "Условная/условно-безусловная по каждому случаю или со 2-го случая",
            "without_certificates": "1 раз в год: ЛКП не более 1-й детали; остекление кузова",
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
            "tow_truck": "Легковые ТС - лимит 10 000 руб.",
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
            "tow_truck": "Легковые ТС - лимит 5 000 руб.; Прочие - лимит 15 000 руб.",
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
            "tow_truck": "Легковые ТС - 6 000 руб.; Грузовые - 12 000 руб.",
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

OFFICIAL_SOURCES = {
    "РЕСО-Гарантия": ["https://www.reso.ru/Avto/Kasko/"],
    "Ингосстрах": ["https://www.ingos.ru/auto/kasko"],
    "АльфаСтрахование": ["https://www.alfastrah.ru/auto/kasko/"],
    "СОГАЗ": ["https://www.sogaz.ru/kasko/"],
    "Согласие": ["https://www.soglasie.ru/kasko/"],
    "Югория": ["https://ugsk.ru/kasko/"],
    "Совкомбанк Страхование": ["https://sovcomins.ru/kasko/"],
    "ВСК": ["https://www.vsk.ru/auto/kasko"],
    "Ренессанс": ["https://www.renins.ru/auto/kasko"],
    "Т-Страхование": ["https://www.tbank.ru/insurance/kasko/"],
    "СберСтрахование": ["https://sberbankins.ru/products/kasko/"]
}

def load_or_update_data():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    
    data = get_fallback_data()
    data["_last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return data

INSURANCE_DATA = load_or_update_data()
ALL_COMPANIES = list(get_fallback_data().keys())

# ==================== МАРШРУТЫ ====================

@app.route('/', methods=['GET', 'POST'])
def index():
    last_updated = INSURANCE_DATA.get("_last_updated", datetime.now().strftime("%Y-%m-%d %H:%M"))
    return render_template(
        'index.html', 
        companies=ALL_COMPANIES, 
        now=datetime.now().strftime("%Y-%m-%d %H:%M"), 
        last_updated=last_updated
    )

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
    advantages = []

    m1 = re.search(r'\d+', str(data1.get("total_loss", "")))
    m2 = re.search(r'\d+', str(data2.get("total_loss", "")))
    if m1 and m2:
        v1, v2 = int(m1.group()), int(m2.group())
        if v1 > v2:
            advantages.append(f"✅ {company1} имеет более высокий порог тотала: {v1}% против {v2}% у {company2}")
        elif v2 > v1:
            advantages.append(f"✅ {company2} имеет более высокий порог тотала: {v2}% против {v1}% у {company1}")

    pm1 = re.search(r'\d+', str(data1.get("payment_terms", "")))
    pm2 = re.search(r'\d+', str(data2.get("payment_terms", "")))
    if pm1 and pm2:
        pv1, pv2 = int(pm1.group()), int(pm2.group())
        if pv1 < pv2:
            advantages.append(f"⚡ {company1} быстрее выплачивает возмещение: {pv1} дней против {pv2} дней у {company2}")
        elif pv2 < pv1:
            advantages.append(f"⚡ {company2} быстрее выплачивает возмещение: {pv2} дней против {pv1} дней у {company1}")

    # Сбор источников информации
    sources1 = OFFICIAL_SOURCES.get(company1, ["Официальный сайт " + company1])
    sources2 = OFFICIAL_SOURCES.get(company2, ["Официальный сайт " + company2])
    last_updated = INSURANCE_DATA.get("_last_updated", datetime.now().strftime("%Y-%m-%d %H:%M"))

    return render_template(
        'result.html', 
        company1=company1, 
        company2=company2, 
        data1=data1, 
        data2=data2, 
        advantages=advantages, 
        sources1=sources1,
        sources2=sources2,
        last_updated=last_updated,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
