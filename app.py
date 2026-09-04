# app.py — МНОГОУРОВНЕВЫЙ ПАРСЕР КАСКО (6 УРОВНЕЙ) — УЛУЧШЕННАЯ ВЕРСИЯ

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
from urllib.parse import quote_plus

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==================== КОНФИГУРАЦИЯ ====================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edge/120.0.0.0 Safari/537.36",
]

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

# ==================== ОФИЦИАЛЬНЫЕ САЙТЫ (УРОВЕНЬ 1) ====================

OFFICIAL_URLS = {
    "РЕСО-Гарантия": "https://reso.ru/auto/",
    "ВСК": "https://www.vsk.ru/o-kompanii/dlya-kliyentov?t=pravila_i_tarifi_strahovaniya&case=pravila",
    "Ингосстрах": "https://www.ingos.ru/auto/",
    "Ренессанс": "https://www.renins.ru/auto/",
    "АльфаСтрахование": "https://www.alfastrah.ru/auto/",
    "Т-Страхование": "https://tbank.ru/insurance/help/auto/kasko/",
    "РГС": "https://www.rgs.ru/products/auto/",
    "Югория": "https://ugsk.ru/auto/",
    "СберСтрахование": "https://sberbankins.ru/avtostrahovanie",
    "Согласие": "https://soglasie.ru/auto/",
    "Совкомбанк Страхование": "https://sovcomins.ru/auto/"
}

# ==================== АГРЕГАТОРЫ С URL КОМПАНИЙ ====================

AGGREGATOR_COMPANY_URLS = {
    "РЕСО-Гарантия": {
        "Сравни.ру": "https://www.sravni.ru/strahovanie/company/reso-garantija/",
        "Банки.ру": "https://www.banki.ru/insurance/reso-garantiya/",
        "Инсмарт": "https://insmart.ru/company/reso-garantiya/"
    },
    "ВСК": {
        "Сравни.ру": "https://www.sravni.ru/strahovanie/company/vsk/",
        "Банки.ру": "https://www.banki.ru/insurance/vsk/",
        "Инсмарт": "https://insmart.ru/company/vsk/"
    },
    "Ингосстрах": {
        "Сравни.ру": "https://www.sravni.ru/strahovanie/company/ingosstrakh/",
        "Банки.ру": "https://www.banki.ru/insurance/ingosstrakh/",
        "Инсмарт": "https://insmart.ru/company/ingosstrakh/"
    },
    "Ренессанс": {
        "Сравни.ру": "https://www.sravni.ru/strahovanie/company/renessans/",
        "Банки.ру": "https://www.banki.ru/insurance/renessans/",
        "Инсмарт": "https://insmart.ru/company/renessans/"
    },
    "АльфаСтрахование": {
        "Сравни.ру": "https://www.sravni.ru/strahovanie/company/alfastrakhovanie/",
        "Банки.ру": "https://www.banki.ru/insurance/alfastrakhovanie/",
        "Инсмарт": "https://insmart.ru/company/alfastrah/"
    },
    "Т-Страхование": {
        "Сравни.ру": "https://www.sravni.ru/strahovanie/company/t-bank/",
        "Банки.ру": "https://www.banki.ru/insurance/t-bank/",
        "Инсмарт": "https://insmart.ru/company/t-bank/"
    },
    "РГС": {
        "Сравни.ру": "https://www.sravni.ru/strahovanie/company/rosgosstrakh/",
        "Банки.ру": "https://www.banki.ru/insurance/rosgosstrakh/",
        "Инсмарт": "https://insmart.ru/company/rgs/"
    },
    "Югория": {
        "Сравни.ру": "https://www.sravni.ru/strahovanie/company/ugoriya/",
        "Банки.ру": "https://www.banki.ru/insurance/ugoriya/",
        "Инсмарт": "https://insmart.ru/company/yugoriya/"
    },
    "СберСтрахование": {
        "Сравни.ру": "https://www.sravni.ru/strahovanie/company/sberstrakhovanie/",
        "Банки.ру": "https://www.banki.ru/insurance/sberstrakhovanie/",
        "Инсмарт": "https://insmart.ru/company/sberbank-insurance/"
    },
    "Согласие": {
        "Сравни.ру": "https://www.sravni.ru/strahovanie/company/soglasie/",
        "Банки.ру": "https://www.banki.ru/insurance/soglasie/",
        "Инсмарт": "https://insmart.ru/company/soglasie/"
    },
    "Совкомбанк Страхование": {
        "Сравни.ру": "https://www.sravni.ru/strahovanie/company/sovkomstrakh/",
        "Банки.ру": "https://www.banki.ru/insurance/sovcomins/",
        "Инсмарт": "https://insmart.ru/company/sovcomins/"
    }
}

# ==================== ПОЛЯ КАСКО ====================

KASKO_FIELDS = [
    "franchise",
    "without_certificates",
    "gap",
    "total_loss",
    "fire",
    "terrorism",
    "drone",
    "tow_truck",
    "repair_type",
    "payment_terms",
    "advantages",
    "weak_points",
    "rating",
    "offices"
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
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

def fetch_url(url: str, timeout: int = 20) -> Optional[str]:
    """Загрузить URL с обходом блокировок"""
    for attempt in range(3):
        try:
            headers = get_headers()
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                verify=False,
                allow_redirects=True
            )
            if response.status_code == 200:
                return response.text
            elif response.status_code == 403:
                # Пробуем другой User-Agent
                continue
            else:
                return None
        except requests.exceptions.SSLError:
            try:
                response = requests.get(
                    url,
                    headers=get_headers(),
                    timeout=timeout,
                    verify=False,
                    allow_redirects=True
                )
                if response.status_code == 200:
                    return response.text
            except:
                pass
            return None
        except Exception as e:
            if attempt == 2:
                print(f"      ⚠️ Ошибка загрузки {url}: {type(e).__name__}")
            time.sleep(1)
    return None

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_value_from_text(text: str, keywords: List[str]) -> Optional[str]:
    """Извлечь значение из текста по ключевым словам"""
    if not text:
        return None
    text_lower = text.lower()
    for keyword in keywords:
        if keyword in text_lower:
            # Находим предложение или фрагмент с ключевым словом
            sentences = re.split(r'[.!?]', text)
            for sentence in sentences:
                if keyword in sentence.lower():
                    # Очищаем и возвращаем
                    cleaned = clean_text(sentence)
                    if len(cleaned) > 10:  # Не слишком короткое
                        return cleaned
    return None

def get_source_level_info(level: int) -> Dict:
    levels = {
        1: {"type": "official", "label": "Официальный сайт", "emoji": "🟢"},
        2: {"type": "aggregator", "label": "Агрегатор", "emoji": "🔵"},
        3: {"type": "special", "label": "Спец. агрегатор", "emoji": "🟣"},
        4: {"type": "rating", "label": "Рейтинг", "emoji": "🟠"},
        5: {"type": "search", "label": "Интернет-поиск", "emoji": "🟡"},
        6: {"type": "memory", "label": "Внутренняя база", "emoji": "⚪"},
    }
    return levels.get(level, {"type": "unknown", "label": "Неизвестно", "emoji": "⬜"})

# ==================== УРОВЕНЬ 1: ОФИЦИАЛЬНЫЙ САЙТ (УЛУЧШЕННЫЙ) ====================

def parse_official_site(company: str, url: str) -> Dict[str, Dict]:
    """Парсинг официального сайта — ищем по заголовкам разделов"""
    print(f"  📂 Уровень 1: Официальный сайт")
    print(f"    🔗 {url}")
    
    result = {}
    html = fetch_url(url)
    
    if not html:
        print(f"    ⚠️ Не удалось загрузить страницу")
        return result
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Удаляем шум
        for tag in soup.find_all(["script", "style", "noscript", "nav", "footer", "header", "iframe"]):
            tag.decompose()
        
        # Ищем заголовки разделов и их содержимое
        section_keywords = {
            "franchise": ["франшиз", "франшиза", "безусловн", "условн"],
            "without_certificates": ["без справок", "без документ", "без предостав"],
            "gap": ["gap", "гэп", "gар"],
            "total_loss": ["тотал", "полная гибель", "конструктивн", "гибел"],
            "fire": ["самовозгоран", "возгоран", "пожар"],
            "terrorism": ["терроризм", "терр. акт", "теракт"],
            "drone": ["бпла", "беспилот", "дрон"],
            "tow_truck": ["эвакуа"],
            "repair_type": ["ремонт", "стоа", "дилер"],
            "payment_terms": ["срок выплат", "рабочих дней", "дней"]
        }
        
        # Собираем весь текст страницы
        all_text = clean_text(soup.get_text())
        
        # Ищем по каждому полю
        for field, keywords in section_keywords.items():
            value = extract_value_from_text(all_text, keywords)
            if value:
                # Проверяем, что это не меню и не навигация
                if len(value) > 20 and not any(x in value.lower() for x in ["войти", "регистрац", "подпис", "©"]):
                    result[field] = {
                        "value": value[:200],
                        "source": {
                            "level": 1,
                            "type": "official",
                            "name": f"Официальный сайт {company}",
                            "url": url,
                            "found_at": datetime.now().isoformat()
                        }
                    }
                    print(f"    ✅ Найдено: {FIELD_LABELS.get(field, field)}")
        
        print(f"    📊 Найдено {len(result)} полей на официальном сайте")
        
    except Exception as e:
        print(f"    ⚠️ Ошибка парсинга: {e}")
    
    return result

# ==================== УРОВЕНЬ 2: АГРЕГАТОРЫ (УЛУЧШЕННЫЙ) ====================

def parse_aggregator_page(company: str, aggregator_name: str, url: str, level: int) -> Dict[str, Dict]:
    """Парсинг страницы компании на агрегаторе"""
    print(f"    🔗 {aggregator_name}: {url}")
    
    result = {}
    html = fetch_url(url)
    
    if not html:
        print(f"    ⚠️ Не удалось загрузить страницу")
        return result
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Удаляем шум
        for tag in soup.find_all(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()
        
        # Ищем таблицы и списки с условиями
        tables = soup.find_all('table')
        list_items = soup.find_all(['li', 'p', 'div'])
        
        all_text = clean_text(soup.get_text())
        
        # Ключевые слова для поиска
        field_keywords = {
            "franchise": ["франшиз", "франшиза", "безусловн", "условн"],
            "without_certificates": ["без справок", "без документ"],
            "gap": ["gap", "гэп"],
            "total_loss": ["тотал", "гибель"],
            "fire": ["самовозгоран", "возгоран"],
            "terrorism": ["терроризм"],
            "drone": ["бпла", "беспилот"],
            "tow_truck": ["эвакуа"],
            "repair_type": ["ремонт", "стоа"],
            "payment_terms": ["срок", "дней"]
        }
        
        for field, keywords in field_keywords.items():
            value = extract_value_from_text(all_text, keywords)
            if value and len(value) > 15:
                # Проверяем, что это не реклама
                if not any(x in value.lower() for x in ["подпис", "новост", "акци"]):
                    result[field] = {
                        "value": value[:200],
                        "source": {
                            "level": level,
                            "type": "aggregator" if level == 2 else "special",
                            "name": aggregator_name,
                            "url": url,
                            "found_at": datetime.now().isoformat()
                        }
                    }
                    print(f"      ✅ Найдено: {FIELD_LABELS.get(field, field)}")
        
    except Exception as e:
        print(f"    ⚠️ Ошибка парсинга: {e}")
    
    return result

# ==================== УРОВЕНЬ 5: ПОИСК В ИНТЕРНЕТЕ (УЛУЧШЕННЫЙ) ====================

def search_internet(company: str, field: str) -> Optional[Dict]:
    """Поиск в интернете через Google (попытка)"""
    query = f"{company} КАСКО {FIELD_LABELS.get(field, field)} условия"
    print(f"    🔍 Запрос: '{query}'")
    
    # Пробуем Google
    search_urls = [
        f"https://www.google.com/search?q={quote_plus(query)}&hl=ru",
        f"https://www.google.ru/search?q={quote_plus(query)}&hl=ru",
    ]
    
    for search_url in search_urls:
        html = fetch_url(search_url, timeout=15)
        if html:
            try:
                soup = BeautifulSoup(html, 'html.parser')
                
                # Ищем ссылки на результаты
                for link in soup.find_all('a'):
                    href = link.get('href', '')
                    if '/url?q=' in href and 'http' in href:
                        # Извлекаем реальный URL
                        match = re.search(r'/url\?q=([^&]+)', href)
                        if match:
                            real_url = match.group(1)
                            if any(x in real_url.lower() for x in ['.ru', '.com', '.рф']):
                                # Пробуем загрузить страницу результата
                                page_html = fetch_url(real_url, timeout=10)
                                if page_html:
                                    page_soup = BeautifulSoup(page_html, 'html.parser')
                                    page_text = clean_text(page_soup.get_text())
                                    
                                    # Ищем ответ
                                    field_keywords = {
                                        "franchise": ["франшиз"],
                                        "total_loss": ["тотал", "гибель"],
                                        "without_certificates": ["без справок"],
                                        "gap": ["gap"],
                                        "fire": ["самовозгоран"],
                                        "terrorism": ["терроризм"],
                                        "drone": ["бпла"],
                                        "tow_truck": ["эвакуа"],
                                        "payment_terms": ["срок", "дней"],
                                        "repair_type": ["ремонт", "стоа"]
                                    }
                                    
                                    keywords = field_keywords.get(field, [])
                                    for kw in keywords:
                                        if kw in page_text.lower():
                                            # Находим предложение с ключевым словом
                                            sentences = re.split(r'[.!?]', page_text)
                                            for sentence in sentences:
                                                if kw in sentence.lower() and len(sentence) > 20:
                                                    return {
                                                        "value": clean_text(sentence[:200]),
                                                        "source": {
                                                            "level": 5,
                                                            "type": "search",
                                                            "name": "Интернет-поиск (Google)",
                                                            "url": real_url,
                                                            "found_at": datetime.now().isoformat()
                                                        }
                                                    }
            except Exception as e:
                print(f"    ⚠️ Ошибка парсинга поиска: {e}")
    
    print(f"    ❌ Не найдено в интернете")
    return None

# ==================== УРОВЕНЬ 6: ПАМЯТЬ ====================

def get_from_memory(company: str, field: str) -> Optional[Dict]:
    if company not in KASKO_PDF_DATA:
        return None
    
    value = KASKO_PDF_DATA[company].get(field)
    if not value or value == "Нет инф." or value == "Не указан":
        return None
    
    return {
        "value": value,
        "source": {
            "level": 6,
            "type": "memory",
            "name": "PDF: КАСКО Сравнение с конкурентами (июль 2026)",
            "url": None,
            "found_at": "2026-09-04"
        }
    }

# ==================== СБОР ДАННЫХ ДЛЯ ОДНОЙ КОМПАНИИ ====================

def collect_company_data(company: str) -> Dict:
    """Сбор данных для одной компании по всем 6 уровням"""
    print(f"\n🔍 {company}")
    print("━" * 50)
    
    result = {}
    found_fields = set()
    source_stats = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
    
    # УРОВЕНЬ 1: Официальный сайт
    if company in OFFICIAL_URLS:
        official_data = parse_official_site(company, OFFICIAL_URLS[company])
        for field, data in official_data.items():
            if field not in found_fields:
                result[field] = data
                found_fields.add(field)
                source_stats[1] += 1
    
    # УРОВЕНЬ 2: Агрегаторы (страницы компаний)
    if company in AGGREGATOR_COMPANY_URLS:
        for agg_name, url in AGGREGATOR_COMPANY_URLS[company].items():
            if len(found_fields) >= len(KASKO_FIELDS):
                break
            print(f"  📂 Уровень 2: Агрегатор — {agg_name}")
            agg_data = parse_aggregator_page(company, agg_name, url, 2)
            for field, data in agg_data.items():
                if field not in found_fields:
                    result[field] = data
                    found_fields.add(field)
                    source_stats[2] += 1
                    print(f"    ✅ Добавлено: {FIELD_LABELS.get(field, field)} (уровень 2)")
    
    # УРОВЕНЬ 3: Спец. агрегаторы (Инсмарт уже в списке выше)
    # Дополнительные спец. агрегаторы
    special_aggregators = [
        ("Пампаду", "https://pampadu.ru/company/"),
        ("Полис Онлайн", "https://polis.online/companies/"),
    ]
    
    for agg_name, base_url in special_aggregators:
        if len(found_fields) >= len(KASKO_FIELDS):
            break
        # Формируем URL для компании
        company_slug = company.replace(" ", "-").lower()
        url = f"{base_url}{company_slug}/"
        print(f"  📂 Уровень 3: Спец. агрегатор — {agg_name}")
        agg_data = parse_aggregator_page(company, agg_name, url, 3)
        for field, data in agg_data.items():
            if field not in found_fields:
                result[field] = data
                found_fields.add(field)
                source_stats[3] += 1
                print(f"    ✅ Добавлено: {FIELD_LABELS.get(field, field)} (уровень 3)")
    
    # УРОВЕНЬ 4: Рейтинги (простой вариант)
    if "rating" not in found_fields:
        print(f"  📂 Уровень 4: Рейтинг (Эксперт RA)")
        # Пробуем найти рейтинг через быстрый поиск
        try:
            expert_url = "https://raexpert.ru/ratings/insurance/"
            html = fetch_url(expert_url, timeout=10)
            if html:
                # Ищем упоминание компании
                if company in html:
                    # Пробуем найти рейтинг
                    pattern = rf'{company}.*?([А-Я]{{2,5}}\+?)'
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        rating_text = match.group(0)
                        result["rating"] = {
                            "value": f"Рейтинг {company}: {rating_text[:50]}",
                            "source": {
                                "level": 4,
                                "type": "rating",
                                "name": "Эксперт RA",
                                "url": expert_url,
                                "found_at": datetime.now().isoformat()
                            }
                        }
                        found_fields.add("rating")
                        source_stats[4] += 1
                        print(f"    ✅ Найдено: rating")
        except Exception as e:
            print(f"    ⚠️ Ошибка: {e}")
    
    # УРОВЕНЬ 5: Интернет-поиск
    print(f"  📂 Уровень 5: Интернет-поиск")
    for field in KASKO_FIELDS:
        if field in found_fields:
            continue
        
        search_result = search_internet(company, field)
        if search_result:
            result[field] = search_result
            found_fields.add(field)
            source_stats[5] += 1
            print(f"    ✅ Найдено: {FIELD_LABELS.get(field, field)}")
        else:
            # Не печатаем для каждого поля, чтобы не засорять логи
            pass
    
    # УРОВЕНЬ 6: Память (PDF)
    print(f"  📂 Уровень 6: Внутренняя память (PDF)")
    memory_fields = []
    for field in KASKO_FIELDS:
        if field in found_fields:
            continue
        
        memory_data = get_from_memory(company, field)
        if memory_data:
            result[field] = memory_data
            found_fields.add(field)
            source_stats[6] += 1
            memory_fields.append(field)
            print(f"    ✅ Из PDF: {FIELD_LABELS.get(field, field)}")
    
    if not memory_fields:
        print(f"    ⚠️ Нет данных в PDF для недостающих полей")
    
    # ИТОГ
    print(f"\n📊 {company}: собрано {len(found_fields)}/{len(KASKO_FIELDS)} полей")
    for level, count in source_stats.items():
        if count > 0:
            info = get_source_level_info(level)
            print(f"  {info['emoji']} {info['label']}: {count}")
    
    return result

# ==================== СБОР ВСЕХ ДАННЫХ ====================

def collect_all_data() -> Dict:
    """Сбор данных для всех компаний"""
    print("\n" + "=" * 60)
    print("📊 СБОР ДАННЫХ: КАСКО")
    print("=" * 60)
    print(f"Компаний: {len(KASKO_PDF_DATA)}")
    print(f"Поля: {len(KASKO_FIELDS)}")
    print(f"Уровни: 6 (официальный → агрегаторы → спец.агрегаторы → рейтинги → поиск → память)")
    print("=" * 60)
    
    all_data = {}
    
    for company in KASKO_PDF_DATA.keys():
        company_data = collect_company_data(company)
        all_data[company] = company_data
        time.sleep(1.5)  # Задержка между компаниями
    
    all_data["_last_updated"] = datetime.now().isoformat()
    all_data["_product"] = "kasko"
    all_data["_fields"] = KASKO_FIELDS
    
    print("\n" + "=" * 60)
    print("✅ СБОР ЗАВЕРШЁН")
    print("=" * 60)
    
    return all_data

# ==================== ЗАГРУЗКА / СОХРАНЕНИЕ ДАННЫХ ====================

DATA_FILE = "insurance_data.json"

def load_data() -> Dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"📦 Загружено из кэша: {len(data) - 1} компаний")
                return data
        except Exception as e:
            print(f"⚠️ Ошибка загрузки кэша: {e}")
    
    print("🔄 Данных нет, запускаем сбор...")
    data = collect_all_data()
    save_data(data)
    return data

def save_data(data: Dict) -> None:
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 Данные сохранены в {DATA_FILE}")
    except Exception as e:
        print(f"⚠️ Ошибка сохранения: {e}")

# ==================== ЗАГРУЗКА ПРИ СТАРТЕ ====================

print("🚀 Загрузка приложения...")
INSURANCE_DATA = load_data()
ALL_COMPANIES = [c for c in INSURANCE_DATA.keys() if not c.startswith("_")]

# ==================== FLASK МАРШРУТЫ ====================

@app.route('/')
def index():
    last_updated = INSURANCE_DATA.get("_last_updated", "неизвестно")
    return render_template('index.html',
                         companies=ALL_COMPANIES,
                         last_updated=last_updated[:16] if last_updated != "неизвестно" else "неизвестно")

@app.route('/compare', methods=['POST'])
def compare():
    company1 = request.form.get('company1')
    company2 = request.form.get('company2')
    
    if not company1 or not company2:
        return "❌ Выберите обе компании! <a href='/'>Назад</a>"
    
    if company1 == company2:
        return "❌ Выберите разные компании! <a href='/'>Назад</a>"
    
    data1 = INSURANCE_DATA.get(company1, {})
    data2 = INSURANCE_DATA.get(company2, {})
    
    # Подготовка источников
    sources1 = {}
    sources2 = {}
    
    for field in KASKO_FIELDS:
        if field in data1 and 'source' in data1[field]:
            sources1[field] = data1[field]['source']
        if field in data2 and 'source' in data2[field]:
            sources2[field] = data2[field]['source']
    
    return render_template('result.html',
                         company1=company1,
                         company2=company2,
                         data1=data1,
                         data2=data2,
                         sources1=sources1,
                         sources2=sources2,
                         fields=KASKO_FIELDS,
                         field_labels=FIELD_LABELS,
                         timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

@app.route('/update')
def update():
    global INSURANCE_DATA, ALL_COMPANIES
    print("🔄 Ручное обновление...")
    INSURANCE_DATA = collect_all_data()
    save_data(INSURANCE_DATA)
    ALL_COMPANIES = [c for c in INSURANCE_DATA.keys() if not c.startswith("_")]
    return "✅ Данные обновлены! <a href='/'>На главную</a>"

# Заглушки для старых URL
@app.route('/login')
@app.route('/register')
@app.route('/logout')
@app.route('/payment')
def old_routes():
    return redirect('/')

# ==================== ШАБЛОНЫ ====================

os.makedirs('templates', exist_ok=True)

# index.html
with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write('''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Сравнение КАСКО</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #f0f2f5; min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
        .container { background: #fff; padding: 40px; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); max-width: 520px; width: 100%; }
        h1 { font-size: 24px; color: #1a1a2e; text-align: center; margin-bottom: 8px; }
        .subtitle { text-align: center; color: #6b7280; font-size: 14px; margin-bottom: 30px; }
        .update-info { text-align: center; font-size: 12px; color: #9ca3af; margin-bottom: 24px; padding: 8px; background: #f9fafb; border-radius: 8px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; font-weight: 600; font-size: 14px; color: #374151; margin-bottom: 6px; }
        select { width: 100%; padding: 12px 14px; border: 1.5px solid #e5e7eb; border-radius: 10px; font-size: 15px; background: #fff; transition: border-color 0.2s; appearance: none; }
        select:focus { outline: none; border-color: #2563eb; }
        .vs { text-align: center; font-size: 20px; color: #9ca3af; margin: 8px 0; }
        .btn { width: 100%; padding: 14px; background: #2563eb; color: #fff; border: none; border-radius: 10px; font-size: 16px; font-weight: 600; cursor: pointer; transition: background 0.2s; margin-top: 8px; }
        .btn:hover { background: #1d4ed8; }
        .btn-update { background: #6b7280; margin-top: 12px; }
        .btn-update:hover { background: #4b5563; }
        .footer { margin-top: 24px; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #f3f4f6; padding-top: 16px; }
        .badge { display: inline-block; font-size: 11px; padding: 2px 10px; border-radius: 12px; background: #e5e7eb; color: #4b5563; margin-top: 8px; }
    </style>
</head>
<body>
<div class="container">
    <h1>🚗 Сравнение КАСКО</h1>
    <p class="subtitle">Выберите две компании для сравнения</p>
    <div class="update-info">📅 Данные обновлены: {{ last_updated }}</div>
    
    <form action="/compare" method="POST">
        <div class="form-group">
            <label>🏢 Первая компания</label>
            <select name="company1" required>
                <option value="">— Выберите —</option>
                {% for c in companies %}
                <option value="{{ c }}">{{ c }}</option>
                {% endfor %}
            </select>
        </div>
        
        <div class="vs">⚔️</div>
        
        <div class="form-group">
            <label>🏢 Вторая компания</label>
            <select name="company2" required>
                <option value="">— Выберите —</option>
                {% for c in companies %}
                <option value="{{ c }}">{{ c }}</option>
                {% endfor %}
            </select>
        </div>
        
        <button type="submit" class="btn">📊 Сравнить</button>
    </form>
    
    <a href="/update"><button class="btn btn-update">🔄 Обновить данные сейчас</button></a>
    
    <div class="footer">
        <span class="badge">11 компаний</span>
        <span class="badge">14 параметров</span>
        <span class="badge">6 уровней поиска</span>
    </div>
</div>
</body>
</html>
''')

# result.html
with open('templates/result.html', 'w', encoding='utf-8') as f:
    f.write('''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Сравнение КАСКО</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background: #f0f2f5; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; background: #fff; padding: 30px; border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }
        h1 { font-size: 22px; color: #1a1a2e; text-align: center; margin-bottom: 6px; }
        .subtitle { text-align: center; color: #6b7280; font-size: 14px; margin-bottom: 24px; }
        .vs-title { text-align: center; font-size: 16px; padding: 12px; background: #f8fafc; border-radius: 10px; margin-bottom: 24px; }
        .main-badge { background: #2563eb; color: #fff; padding: 2px 14px; border-radius: 12px; font-size: 12px; margin-left: 8px; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { background: #1a1a2e; color: #fff; padding: 10px 12px; text-align: left; }
        td { padding: 10px 12px; border-bottom: 1px solid #f0f2f5; vertical-align: top; }
        .param { font-weight: 600; color: #374151; background: #f8fafc; width: 16%; }
        .value { word-break: break-word; }
        .source-icon { display: inline-block; font-size: 14px; margin-right: 4px; cursor: help; }
        .source-tooltip { display: none; font-size: 11px; color: #6b7280; margin-top: 2px; }
        .value:hover .source-tooltip { display: block; }
        .legend { display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0 16px; padding: 14px; background: #f8fafc; border-radius: 10px; font-size: 13px; }
        .legend-item { display: flex; align-items: center; gap: 4px; }
        .btn { display: inline-block; padding: 10px 24px; background: #2563eb; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 14px; transition: background 0.2s; }
        .btn:hover { background: #1d4ed8; }
        .btn-secondary { background: #6b7280; }
        .btn-secondary:hover { background: #4b5563; }
        .actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 20px; }
        .footer { margin-top: 20px; text-align: center; font-size: 12px; color: #9ca3af; border-top: 1px solid #f3f4f6; padding-top: 16px; }
        .missing { color: #9ca3af; font-style: italic; }
        .source-url { font-size: 11px; color: #6b7280; word-break: break-all; }
        .source-url a { color: #2563eb; text-decoration: none; }
        .source-url a:hover { text-decoration: underline; }
        @media (max-width: 768px) {
            .container { padding: 16px; }
            table { font-size: 12px; }
            td, th { padding: 6px 8px; }
            .param { width: 20%; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>📊 Сравнение КАСКО</h1>
    <div class="subtitle">Сравнительный анализ условий страхования</div>
    
    <div class="vs-title">
        🏆 {{ company1 }} <span class="main-badge">ОСНОВНАЯ</span>
        &nbsp;⚔️&nbsp; {{ company2 }}
    </div>
    
    <div class="legend">
        <span class="legend-item">🟢 Уровень 1 — Официальный сайт</span>
        <span class="legend-item">🔵 Уровень 2 — Агрегатор</span>
        <span class="legend-item">🟣 Уровень 3 — Спец. агрегатор</span>
        <span class="legend-item">🟠 Уровень 4 — Рейтинг</span>
        <span class="legend-item">🟡 Уровень 5 — Интернет-поиск</span>
        <span class="legend-item">⚪ Уровень 6 — Внутренняя база</span>
    </div>
    
    <table>
        <thead>
            <tr>
                <th class="param">Параметр</th>
                <th>{{ company1 }}</th>
                <th>{{ company2 }}</th>
            </tr>
        </thead>
        <tbody>
            {% for field in fields %}
            <tr>
                <td class="param">{{ field_labels.get(field, field) }}</td>
                <td class="value">
                    {% if field in data1 and data1[field] %}
                        {% if data1[field] is mapping and 'value' in data1[field] %}
                            {{ data1[field].value }}
                        {% else %}
                            {{ data1[field] }}
                        {% endif %}
                        {% if field in sources1 and sources1[field] %}
                            {% set s = sources1[field] %}
                            <span class="source-icon" title="Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})">{% if s.level == 1 %}🟢{% elif s.level == 2 %}🔵{% elif s.level == 3 %}🟣{% elif s.level == 4 %}🟠{% elif s.level == 5 %}🟡{% else %}⚪{% endif %}</span>
                            <div class="source-tooltip">
                                Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})
                                {% if s.url %}<br><span class="source-url"><a href="{{ s.url }}" target="_blank">{{ s.url }}</a></span>{% endif %}
                            </div>
                        {% endif %}
                    {% else %}
                        <span class="missing">—</span>
                    {% endif %}
                </td>
                <td class="value">
                    {% if field in data2 and data2[field] %}
                        {% if data2[field] is mapping and 'value' in data2[field] %}
                            {{ data2[field].value }}
                        {% else %}
                            {{ data2[field] }}
                        {% endif %}
                        {% if field in sources2 and sources2[field] %}
                            {% set s = sources2[field] %}
                            <span class="source-icon" title="Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})">{% if s.level == 1 %}🟢{% elif s.level == 2 %}🔵{% elif s.level == 3 %}🟣{% elif s.level == 4 %}🟠{% elif s.level == 5 %}🟡{% else %}⚪{% endif %}</span>
                            <div class="source-tooltip">
                                Источник: {{ s.label if s.label else s.type }} (уровень {{ s.level }})
                                {% if s.url %}<br><span class="source-url"><a href="{{ s.url }}" target="_blank">{{ s.url }}</a></span>{% endif %}
                            </div>
                        {% endif %}
                    {% else %}
                        <span class="missing">—</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    
    <div class="actions">
        <a href="/" class="btn">← Новое сравнение</a>
        <a href="/update" class="btn btn-secondary">🔄 Обновить данные</a>
    </div>
    
    <div class="footer">
        Обновлено: {{ timestamp }}
    </div>
</div>
</body>
</html>
''')

# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
