# app.py — ПАРСИНГ СТРАНИЦ КАСКО + PDF + ПАМЯТЬ

from flask import Flask, render_template, request, redirect
from datetime import datetime
import json
import os
import requests
import urllib3
import re
import time
import random
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
from urllib.parse import quote_plus, urljoin

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==================== КОНФИГУРАЦИЯ ====================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]

# ==================== УРЛЫ СТРАНИЦ КАСКО ====================

KASKO_PAGES = {
    "РЕСО-Гарантия": "https://reso.ru/individual/auto/kasko/",
    "ВСК": "https://www.vsk.ru/klientam/avto/kasko/",
    "Ингосстрах": "https://www.ingos.ru/auto/kasko/",
    "Ренессанс": "https://www.renins.ru/auto/kasko/",
    "АльфаСтрахование": "https://www.alfastrah.ru/individuals/auto/kasko/",
    "Согласие": "https://www.soglasie.ru/individuals/avto/kasko/",
    "РГС": "https://www.rgs.ru/auto/ekasko/",
    "Т-Страхование": "https://www.tbank.ru/insurance/kasko/",
    "СберСтрахование": "https://sberbankins.ru/products/kasko/",
    "Югория": "https://ugsk.ru/auto/kasko/",
    "Совкомбанк Страхование": "https://sovcomins.ru/product/kasko/"
}

# ==================== ДАННЫЕ ИЗ PDF (УРОВЕНЬ 6 — ПАМЯТЬ) ====================

KASKO_PDF_DATA = {
    "РЕСО-Гарантия": {
        "franchise": "Безусловная \\ Условно-безусловная (с 1-го или со 2-го случая). Не применяется к риску 'Хищение'.",
        "without_certificates": "Стекла без ограничений (включая стеклянную крышу и люк); 1 раз в год 1 кузовной элемент (для VIP 2 раза/год). Камеры входят в состав элемента: зеркала, крышки багажника, облицовки бампера.",
        "gap": "Отдельный риск",
        "total_loss": "75% от СС",
        "fire": "Входит",
        "terrorism": "Входит",
        "drone": "Лимит 1% СС по риску «Ущерб»",
        "tow_truck": "Лимит 1% СС",
        "repair_type": "Ремонт у официального дилера",
        "payment_terms": "5 рабочих дней",
        "advantages": "Ремонт у дилера, быстрая выплата, без учета износа, VIP-условия",
        "weak_points": "Требуется уточнение условий по телефону",
        "rating": "4.5",
        "offices": "1200+"
    },
    "ВСК": {
        "franchise": "Условно-безусловная. Может не применяться по отдельным рискам.",
        "without_certificates": "Стекла: 5% СС (неагрегатная). Прочие элементы: 3% СС (агрегатная). Панорамная крыша, стеклянная крыша и камеры не покрываются.",
        "gap": "Включен, если указан 1 период страхования (1 год). Если страховые суммы разбиты по кварталам – GAP отсутствует.",
        "total_loss": "75% от СС",
        "fire": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "terrorism": "Особые условия включения",
        "drone": "Включен при наличии в полисе GAP и отметки 'официальный дилер'",
        "tow_truck": "Петковые ТС - лимит 5 000 руб. Прочие - лимит 15 000 руб.",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "10 рабочих дней",
        "advantages": "Гибкие условия по справкам",
        "weak_points": "Камеры не оплачиваются без справок. Самовозгорание исключено.",
        "rating": "4.2",
        "offices": "800+"
    },
    "Ингосстрах": {
        "franchise": "Условная\\условно-безусловная. По каждому случаю или со 2-го случая (Авто-профи).",
        "without_certificates": "Базовый вариант: 1 раз в год – 1 из вариантов: ЛКП не более 1-й детали; остекление кузова (ИСКЛЮЧАЯ стеклянную крышу); внешние световые приборы; зеркала; антенна.",
        "gap": "Включен при отметке «Постоянная страховая сумма».",
        "total_loss": "75% от СС",
        "fire": "Входит",
        "terrorism": "За доп. плату, тариф 0,3%.",
        "drone": "Включен, но лимит 0,3%.",
        "tow_truck": "По запросу",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "10 рабочих дней",
        "advantages": "Широкая сеть офисов",
        "weak_points": "Без справок – только ЛКП 1 детали. Возможны ограничения по пробегу и СТОА.",
        "rating": "4.4",
        "offices": "900+"
    },
    "Ренессанс": {
        "franchise": "11 видов франшиз. Чаще всего: Франшиза виновника, Безусловная, Франшиза со 2-го случая.",
        "without_certificates": "Вариативно: стекла 1 раз в год \\ стекла без ограничений \\ до 5% СС 2 раза \\ до 3% СС 1 раз \\ не предусмотрено.",
        "gap": "Отдельный риск",
        "total_loss": "75% от СС",
        "fire": "Только для электромобилей",
        "terrorism": "За доп. плату, 0,5% от СС на легковые ТС",
        "drone": "За доп. плату, 0,5% от СС на легковые",
        "tow_truck": "Петковые ТС - лимит 10 000 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Много вариантов франшизы",
        "weak_points": "Франшиза по хищению. Эвакуация за доп. плату.",
        "rating": "4.3",
        "offices": "500+"
    },
    "АльфаСтрахование": {
        "franchise": "Условно-безусловная. Применяется к Хищению.",
        "without_certificates": "Базовый вариант: стекла без ограничений + 1 кузовной элемент 2 раза в год",
        "gap": "Включен по умолчанию",
        "total_loss": "75% от СС",
        "fire": "За доп. плату, 0,8% от СС",
        "terrorism": "За доп. плату, 0,2-0,3% от СС",
        "drone": "За доп. плату",
        "tow_truck": "Петковые ТС - лимит 5 000 руб. Прочие - лимит 10 000 руб.",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "7 рабочих дней",
        "advantages": "Без справок с бонусами",
        "weak_points": "Франшиза на Хищение, самовозгорание - за доп. плату",
        "rating": "4.6",
        "offices": "600+"
    },
    "Т-Страхование": {
        "franchise": "Условно-безусловная. Для ТС старше 5 лет - обязательные франшизы",
        "without_certificates": "Стекла: неогранич. кол-во раз – ИСКЛЮЧАЯ стеклянную крышу. Кузовные элементы: 1 раз в год - до 3% от СС",
        "gap": "Отдельный риск",
        "total_loss": "65% от СС",
        "fire": "Нет инф.",
        "terrorism": "Нет инф.",
        "drone": "Нет инф.",
        "tow_truck": "Лимит 10 000 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "5 рабочих дней",
        "advantages": "Онлайн-оформление, без справок",
        "weak_points": "Ниже порог тотала (65%). Обязательные франшизы.",
        "rating": "4.7",
        "offices": "онлайн"
    },
    "РГС": {
        "franchise": "Безусловная – по умолчанию. Возможны динамическая, условно-безусловная, агрегатная.",
        "without_certificates": "Стекла: неограниченное кол-во раз - ИСКЛЮЧАЯ стеклянную крышу. Кузовные элементы: 1 раз в год.",
        "gap": "Включен, если СС индексируемая. Не включен, если не индексируемая.",
        "total_loss": "75% от СС",
        "fire": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "terrorism": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "drone": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "tow_truck": "Петковые ТС - лимит 7 000 руб. Грузовые ТС - лимит 10 000 руб.",
        "repair_type": "Ремонт на СТОА страховщика",
        "payment_terms": "10 рабочих дней",
        "advantages": "Гибкие условия",
        "weak_points": "Самовозгорание и Терроризм исключены. Износ за 1-ый месяц - 7% (у РЕСО - 3%).",
        "rating": "4.1",
        "offices": "700+"
    },
    "Югория": {
        "franchise": "Условно-безусловная франшиза. При пролонгации возможна доп. франшиза.",
        "without_certificates": "Стекла: 1 раз, за исключением панорамной крыши и люка",
        "gap": "Неагрегатная - изменяющаяся",
        "total_loss": "Не указан",
        "fire": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "terrorism": "Нет инф.",
        "drone": "Входит",
        "tow_truck": "Лимит 5% от СС, но не более 15 000 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Гибкие условия пролонгации",
        "weak_points": "При пролонгации доп. франшиза. Самовозгорание исключено.",
        "rating": "3.9",
        "offices": "400+"
    },
    "СберСтрахование": {
        "franchise": "6 видов франшиз: условная, безусловная, безусловная при ДТП, динамическая, безусловная со 2-го случая, агрегатная.",
        "without_certificates": "Вариантно: 1 раз - 1 деталь кузова + стекла. Только стекла.",
        "gap": "Включен, если СС индексируемая. Не включен, если не индексируемая.",
        "total_loss": "70% от СС",
        "fire": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "terrorism": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "drone": "ИСКЛЮЧЕНИЕ из страхового покрытия",
        "tow_truck": "Петковые ТС - лимит 6 000 руб. Грузовые ТС - лимит 12 000 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "7 рабочих дней",
        "advantages": "Много вариантов франшизы",
        "weak_points": "Тотал 70%. Самовозгорание и Терроризм исключены.",
        "rating": "4.0",
        "offices": "1000+"
    },
    "Согласие": {
        "franchise": "Условно-безусловная \\ динамическая",
        "without_certificates": "Стандартно: Неограниченно стекла (искл. крыша и люк) + 1 раз любой элемент",
        "gap": "В разделе 'Условия страхования' указывается как риск ГЭП",
        "total_loss": "70% от СС",
        "fire": "За доп. плату, 1.15 для ФЛ и 1.05 для ЮЛ",
        "terrorism": "За доп. плату, тариф 1.1% только для МСК и МО",
        "drone": "За доп. плату, только для МСК и МО",
        "tow_truck": "5 000 руб. (до 3,5 т). 10 000 руб. (свыше 3,5 т и за рубежом)",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Гибкие условия",
        "weak_points": "Тотал 70%. Эвакуатор 5 000 руб. (ниже РЕСО).",
        "rating": "4.2",
        "offices": "300+"
    },
    "Совкомбанк Страхование": {
        "franchise": "Условно-безусловная. Обязательная франшиза 25% (при не уведомлении о смене региона)",
        "without_certificates": "Только ремонт или замена ветрового стекла",
        "gap": "Нет инф.",
        "total_loss": "75% от СС",
        "fire": "Входит в группу событий №2",
        "terrorism": "ИСКЛЮЧЕНИЕ из покрытия",
        "drone": "ИСКЛЮЧЕНИЕ из покрытия",
        "tow_truck": "6 500 руб.",
        "repair_type": "Ремонт или выплата",
        "payment_terms": "10 рабочих дней",
        "advantages": "Группы событий",
        "weak_points": "Терроризм исключен. Обязательная франшиза.",
        "rating": "3.8",
        "offices": "200+"
    }
}

# ==================== ПОЛЯ КАСКО ====================

KASKO_FIELDS = [
    "franchise", "without_certificates", "gap", "total_loss", "fire", "terrorism",
    "drone", "tow_truck", "repair_type", "payment_terms", "advantages",
    "weak_points", "rating", "offices"
]

FIELD_LABELS = {
    "franchise": "Франшиза",
    "without_certificates": "Без справок",
    "gap": "GAP",
    "total_loss": "Тотал",
    "fire": "Самовозгорание",
    "terrorism": "Терроризм",
    "drone": "БПЛА",
    "tow_truck": "Эвакуатор",
    "repair_type": "Тип ремонта",
    "payment_terms": "Срок выплаты",
    "advantages": "Преимущества",
    "weak_points": "Слабые места",
    "rating": "Рейтинг",
    "offices": "Офисы"
}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def get_headers() -> Dict:
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
    }

def fetch_url(url: str, timeout: int = 20) -> Optional[str]:
    """Загрузить URL с обходом блокировок"""
    for attempt in range(3):
        try:
            response = requests.get(url, headers=get_headers(), timeout=timeout, verify=False)
            if response.status_code == 200:
                return response.text
            elif response.status_code == 403:
                time.sleep(1)
                continue
        except:
            pass
        time.sleep(1)
    return None

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_source_info(level: int) -> Dict:
    levels = {
        1: {"emoji": "🟢", "label": "Официальный сайт", "type": "official"},
        2: {"emoji": "🔵", "label": "Агрегатор", "type": "aggregator"},
        3: {"emoji": "🟣", "label": "Спец. агрегатор", "type": "special"},
        4: {"emoji": "🟠", "label": "Рейтинг", "type": "rating"},
        5: {"emoji": "🟡", "label": "Интернет-поиск", "type": "search"},
        6: {"emoji": "⚪", "label": "Внутренняя база", "type": "memory"},
    }
    return levels.get(level, {"emoji": "⬜", "label": "Неизвестно", "type": "unknown"})

# ==================== РАБОТА С PDF ====================

def extract_text_from_pdf(pdf_url: str) -> Optional[str]:
    """Скачать PDF и извлечь текст"""
    try:
        # Пробуем импортировать PyPDF2
        import PyPDF2
        
        response = requests.get(pdf_url, headers=get_headers(), timeout=30, verify=False)
        if response.status_code != 200:
            return None
        
        temp_file = "temp.pdf"
        with open(temp_file, 'wb') as f:
            f.write(response.content)
        
        reader = PyPDF2.PdfReader(temp_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        
        os.remove(temp_file)
        return text if text else None
        
    except ImportError:
        print("    ⚠️ PyPDF2 не установлен, PDF не будет парситься")
        return None
    except Exception as e:
        print(f"    ⚠️ Ошибка при работе с PDF: {e}")
        return None

def find_pdf_links(html: str, base_url: str) -> List[str]:
    """Найти ссылки на PDF на странице"""
    soup = BeautifulSoup(html, 'html.parser')
    pdf_links = []
    
    # Ищем все ссылки
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if not href:
            continue
        
        # Проверяем, что это PDF
        if href.lower().endswith('.pdf') or '.pdf?' in href.lower():
            full_url = urljoin(base_url, href)
            pdf_links.append(full_url)
        # Ищем по тексту
        text = link.get_text().lower()
        if 'правила' in text and 'страхова' in text:
            full_url = urljoin(base_url, href)
            if full_url not in pdf_links:
                pdf_links.append(full_url)
    
    # Ищем ссылки на PDF в тексте
    for tag in soup.find_all(['div', 'p', 'li']):
        text = tag.get_text().lower()
        if '.pdf' in text:
            # Ищем URL в тексте
            match = re.search(r'https?://[^\s]+\.pdf', text)
            if match:
                pdf_links.append(match.group(0))
    
    return pdf_links

# ==================== ПАРСИНГ СТРАНИЦЫ КАСКО + PDF ====================

def parse_kasko_page(company: str, url: str) -> Dict:
    """Парсинг страницы КАСКО + поиск и парсинг PDF"""
    print(f"  📂 Уровень 1: Страница КАСКО — {url}")
    
    result = {}
    html = fetch_url(url)
    
    if not html:
        print(f"    ⚠️ Не удалось загрузить страницу")
        return result
    
    # ---- 1. Парсим текст страницы ----
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()
    
    text = clean_text(soup.get_text())
    
    # Ищем ключевые данные на странице
    field_patterns = {
        "franchise": ["франшиз", "франшиза", "безусловн", "условн"],
        "total_loss": ["тотал", "полная гибель", "гибель", "75%", "70%", "65%"],
        "gap": ["gap", "гэп", "сохранение стоимости"],
        "without_certificates": ["без справок", "без документ"],
        "fire": ["самовозгоран", "возгоран", "пожар"],
        "terrorism": ["терроризм", "терр. акт"],
        "drone": ["бпла", "беспилот", "дрон"],
        "tow_truck": ["эвакуа"],
        "repair_type": ["ремонт", "стоа", "дилер"],
        "payment_terms": ["срок выплат", "рабочих дней", "дней"]
    }
    
    for field, keywords in field_patterns.items():
        for kw in keywords:
            if kw in text.lower():
                sentences = re.split(r'[.!?]', text)
                for sentence in sentences:
                    if kw in sentence.lower():
                        value = clean_text(sentence)
                        if len(value) > 15 and len(value) < 300:
                            result[field] = {
                                "value": value,
                                "source": {
                                    "level": 1,
                                    "name": f"Страница КАСКО {company}",
                                    "url": url,
                                    "found_at": datetime.now().isoformat()
                                }
                            }
                            print(f"    ✅ Найдено: {FIELD_LABELS.get(field, field)}")
                            break
                    if field in result:
                        break
            if field in result:
                break
    
    # ---- 2. Ищем и парсим PDF ----
    print(f"    🔍 Ищем PDF на странице...")
    pdf_links = find_pdf_links(html, url)
    
    if pdf_links:
        print(f"    📄 Найдено PDF: {len(pdf_links)}")
        
        # Парсим каждый PDF
        for pdf_url in pdf_links[:3]:  # Ограничиваем 3 PDF
            print(f"      📥 Загружаем PDF: {pdf_url[:80]}...")
            
            pdf_text = extract_text_from_pdf(pdf_url)
            if not pdf_text:
                continue
            
            pdf_text_lower = pdf_text.lower()
            
            # Ищем данные в PDF
            for field, keywords in field_patterns.items():
                if field in result:  # Уже нашли на странице
                    continue
                    
                for kw in keywords:
                    if kw in pdf_text_lower:
                        sentences = re.split(r'[.!?]', pdf_text)
                        for sentence in sentences:
                            if kw in sentence.lower():
                                value = clean_text(sentence)
                                if len(value) > 15 and len(value) < 400:
                                    result[field] = {
                                        "value": value,
                                        "source": {
                                            "level": 1,
                                            "name": f"PDF {company}",
                                            "url": pdf_url,
                                            "found_at": datetime.now().isoformat()
                                        }
                                    }
                                    print(f"      ✅ Из PDF: {FIELD_LABELS.get(field, field)}")
                                    break
                            if field in result:
                                break
                    if field in result:
                        break
    
    print(f"    📊 Найдено: {len(result)} полей")
    return result

# ==================== УРОВЕНЬ 6: ПАМЯТЬ ====================

def get_from_memory(company: str, field: str) -> Optional[Dict]:
    if company not in KASKO_PDF_DATA:
        return None
    value = KASKO_PDF_DATA[company].get(field)
    if not value or value in ["Нет инф.", "Не указан"]:
        return None
    return {
        "value": value,
        "source": {
            "level": 6,
            "name": "Внутренняя база (PDF)",
            "url": None,
            "found_at": "2026-09-04"
        }
    }

# ==================== СБОР ДАННЫХ ====================

def collect_company_data(company: str) -> Dict:
    print(f"\n🔍 {company}")
    print("━" * 50)
    
    result = {}
    found = set()
    
    # Уровень 1: Страница КАСКО + PDF
    if company in KASKO_PAGES:
        data = parse_kasko_page(company, KASKO_PAGES[company])
        for field, val in data.items():
            if field not in found:
                result[field] = val
                found.add(field)
    
    # Уровень 6: Память (заполняем пропуски)
    print(f"  📂 Уровень 6: Внутренняя база (PDF)")
    for field in KASKO_FIELDS:
        if field in found:
            continue
        memory_data = get_from_memory(company, field)
        if memory_data:
            result[field] = memory_data
            found.add(field)
            print(f"    ✅ Из памяти: {FIELD_LABELS.get(field, field)}")
    
    print(f"\n📊 {company}: собрано {len(found)}/{len(KASKO_FIELDS)} полей")
    return result

def collect_all_data() -> Dict:
    print("\n" + "=" * 60)
    print("📊 СБОР ДАННЫХ: КАСКО")
    print("=" * 60)
    
    all_data = {}
    for company in KASKO_PDF_DATA.keys():
        all_data[company] = collect_company_data(company)
        time.sleep(1)
    
    all_data["_last_updated"] = datetime.now().isoformat()
    return all_data

# ==================== ЗАГРУЗКА/СОХРАНЕНИЕ ====================

DATA_FILE = "insurance_data.json"

def load_data() -> Dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"📦 Загружено из кэша")
                return data
        except:
            pass
    
    print("🔄 Сбор данных...")
    data = collect_all_data()
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

# ==================== FLASK ====================

print("🚀 Загрузка...")
INSURANCE_DATA = load_data()
ALL_COMPANIES = [c for c in INSURANCE_DATA.keys() if not c.startswith("_")]

@app.route('/')
def index():
    last_updated = INSURANCE_DATA.get("_last_updated", "неизвестно")
    return render_template('index.html', companies=ALL_COMPANIES, last_updated=last_updated[:16] if last_updated != "неизвестно" else "неизвестно")

@app.route('/compare', methods=['POST'])
def compare():
    c1 = request.form.get('company1')
    c2 = request.form.get('company2')
    if not c1 or not c2 or c1 == c2:
        return "❌ Ошибка выбора <a href='/'>Назад</a>"
    
    data1 = INSURANCE_DATA.get(c1, {})
    data2 = INSURANCE_DATA.get(c2, {})
    
    return render_template('result.html',
                         company1=c1, company2=c2,
                         data1=data1, data2=data2,
                         fields=KASKO_FIELDS,
                         field_labels=FIELD_LABELS,
                         timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

@app.route('/update')
def update():
    global INSURANCE_DATA, ALL_COMPANIES
    INSURANCE_DATA = collect_all_data()
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(INSURANCE_DATA, f, ensure_ascii=False, indent=2)
    ALL_COMPANIES = [c for c in INSURANCE_DATA.keys() if not c.startswith("_")]
    return "✅ Данные обновлены! <a href='/'>На главную</a>"

@app.route('/login')
@app.route('/register')
@app.route('/logout')
@app.route('/payment')
def old():
    return redirect('/')

# ==================== ШАБЛОНЫ ====================

os.makedirs('templates', exist_ok=True)

with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Сравнение КАСКО</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:#f0f2f5;padding:20px;display:flex;justify-content:center;align-items:center;min-height:100vh}
.container{background:#fff;padding:40px;border-radius:16px;max-width:520px;width:100%}
h1{font-size:24px;color:#1a1a2e;text-align:center}
.subtitle{text-align:center;color:#6b7280;font-size:14px;margin:8px 0 24px}
.update-info{text-align:center;font-size:12px;color:#9ca3af;padding:8px;background:#f9fafb;border-radius:8px;margin-bottom:24px}
select{width:100%;padding:12px;border:1.5px solid #e5e7eb;border-radius:10px;font-size:15px;margin:6px 0}
.btn{width:100%;padding:14px;background:#2563eb;color:#fff;border:none;border-radius:10px;font-size:16px;font-weight:600;cursor:pointer}
.btn-update{background:#6b7280;margin-top:10px}
.vs{text-align:center;font-size:20px;color:#9ca3af;margin:8px 0}
.footer{margin-top:20px;text-align:center;font-size:12px;color:#9ca3af}
.badge{display:inline-block;font-size:11px;padding:2px 10px;border-radius:12px;background:#e5e7eb;color:#4b5563;margin:4px}
</style>
</head>
<body>
<div class="container">
    <h1>🚗 Сравнение КАСКО</h1>
    <p class="subtitle">Выберите две компании для сравнения</p>
    <div class="update-info">📅 Данные обновлены: {{ last_updated }}</div>
    <form method="POST" action="/compare">
        <select name="company1" required>
            <option value="">— Первая компания —</option>
            {% for c in companies %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
        </select>
        <div class="vs">⚔️</div>
        <select name="company2" required>
            <option value="">— Вторая компания —</option>
            {% for c in companies %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
        </select>
        <button type="submit" class="btn">📊 Сравнить</button>
    </form>
    <a href="/update"><button class="btn btn-update">🔄 Обновить данные</button></a>
    <div class="footer">
        <span class="badge">11 компаний</span>
        <span class="badge">14 параметров</span>
    </div>
</div>
</body>
</html>
''')

with open('templates/result.html', 'w', encoding='utf-8') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Результат сравнения</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:#f0f2f5;padding:20px}
.container{max-width:1000px;margin:0 auto;background:#fff;padding:30px;border-radius:16px}
h1{font-size:22px;color:#1a1a2e;text-align:center}
.subtitle{text-align:center;color:#6b7280;font-size:14px;margin-bottom:20px}
.vs-title{text-align:center;font-size:16px;padding:12px;background:#f8fafc;border-radius:10px;margin-bottom:20px}
.main-badge{background:#2563eb;color:#fff;padding:2px 14px;border-radius:12px;font-size:12px;margin-left:8px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#1a1a2e;color:#fff;padding:10px;text-align:left}
td{padding:10px;border-bottom:1px solid #f0f2f5;vertical-align:top}
.param{font-weight:600;color:#374151;background:#f8fafc;width:16%}
.value{word-break:break-word}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0;padding:14px;background:#f8fafc;border-radius:10px;font-size:13px}
.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:20px}
.btn{padding:10px 24px;background:#2563eb;color:#fff;text-decoration:none;border-radius:8px;font-weight:600}
.btn-secondary{background:#6b7280}
.footer{margin-top:20px;text-align:center;font-size:12px;color:#9ca3af;border-top:1px solid #f3f4f6;padding-top:16px}
.missing{color:#9ca3af;font-style:italic}
</style>
</head>
<body>
<div class="container">
    <h1>📊 Сравнение КАСКО</h1>
    <div class="vs-title">🏆 {{ company1 }} <span class="main-badge">ОСНОВНАЯ</span> ⚔️ {{ company2 }}</div>
    <div class="legend">
        <span>🟢 Официальный сайт</span>
        <span>⚪ Внутренняя база</span>
    </div>
    <table>
        <tr><th>Параметр</th><th>{{ company1 }}</th><th>{{ company2 }}</th></tr>
        {% for field in fields %}
        <tr>
            <td class="param">{{ field_labels.get(field, field) }}</td>
            <td class="value">
                {% if field in data1 and data1[field] %}
                    {{ data1[field].value if data1[field] is mapping and 'value' in data1[field] else data1[field] }}
                    {% if data1[field] is mapping and 'source' in data1[field] %}
                        <span>{% if data1[field].source.level == 1 %}🟢{% else %}⚪{% endif %}</span>
                    {% endif %}
                {% else %}<span class="missing">—</span>{% endif %}
            </td>
            <td class="value">
                {% if field in data2 and data2[field] %}
                    {{ data2[field].value if data2[field] is mapping and 'value' in data2[field] else data2[field] }}
                    {% if data2[field] is mapping and 'source' in data2[field] %}
                        <span>{% if data2[field].source.level == 1 %}🟢{% else %}⚪{% endif %}</span>
                    {% endif %}
                {% else %}<span class="missing">—</span>{% endif %}
            </td>
        </tr>
        {% endfor %}
    </table>
    <div class="actions">
        <a href="/" class="btn">← Новое сравнение</a>
        <a href="/update" class="btn btn-secondary">🔄 Обновить</a>
    </div>
    <div class="footer">Обновлено: {{ timestamp }}</div>
</div>
</body>
</html>
''')

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
