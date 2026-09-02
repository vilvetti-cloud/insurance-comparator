# app.py — ЧИСТАЯ ВЕРСИЯ С УМНЫМ ПАРСИНГОМ

from flask import Flask, render_template, request, session, redirect, url_for
from datetime import datetime
import json
import os
import hashlib
import secrets
import requests
from bs4 import BeautifulSoup
import re
import time

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# ==================== ЗАПАСНЫЕ ДАННЫЕ (ЧИСТЫЕ) ====================

def get_fallback_data():
    return {
        "РЕСО-Гарантия": {
            "franchise": "Безусловная / условно-безусловная",
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
            "franchise": "Безусловная / условно-безусловная",
            "without_certificates": "Вариантно: 1 раз один элемент / Неограниченно стекла + 1",
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
            "franchise": "Условно-безусловная (на Хищение)",
            "without_certificates": "Стекла без ограничений + 1 кузовной элемент 2 раза в год",
            "gap": "Включен по умолчанию",
            "total_loss": "75%",
            "fire": "За доп. плату, 0,8%",
            "terrorism": "За доп. плату, 0,2-0,3%",
            "drone": "За доп. плату",
            "tow_truck": "Петковые ТС - 5 000 руб.; Прочие - 10 000 руб.",
            "repair_type": "Ремонт на СТОА страховщика",
            "payment_terms": "7 рабочих дней",
            "advantages": "Без справок с бонусами",
            "weak_points": "Франшиза на Хищение, самовозгорание - за доп. плату",
            "rating": "4.6",
            "offices": "600+"
        },
        "Ингосстрах": {
            "franchise": "Условная/условно-безусловная",
            "without_certificates": "ЛПКП 1 деталь; остекление (кроме крыши)",
            "gap": "Включен при постоянной СС",
            "total_loss": "75%",
            "fire": "Входит",
            "terrorism": "За доп. плату, 0,3%",
            "drone": "За доп. плату",
            "tow_truck": "По запросу",
            "repair_type": "Ремонт на СТОА страховщика",
            "payment_terms": "10 рабочих дней",
            "advantages": "Широкая сеть офисов",
            "weak_points": "Без справок – только ЛКП 1 детали",
            "rating": "4.4",
            "offices": "900+"
        },
        "Ренессанс": {
            "franchise": "11 видов франшиз",
            "without_certificates": "Вариативно (стекла / до 5% СС)",
            "gap": "Отдельный риск",
            "total_loss": "75%",
            "fire": "Только для электромобилей",
            "terrorism": "За доп. плату, 0,5%",
            "drone": "За доп. плату, 0,5%",
            "tow_truck": "Петковые ТС - 10 000 руб.",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "10 рабочих дней",
            "advantages": "Много вариантов франшизы",
            "weak_points": "Эвакуация - за доп. плату, франшиза по угону",
            "rating": "4.3",
            "offices": "500+"
        },
        "Т-Страхование": {
            "franchise": "Условно-безусловная (обязательная для ТС > 5 лет)",
            "without_certificates": "Стекла неогранич.; Кузов до 3% СС",
            "gap": "Отдельный риск",
            "total_loss": "65%",
            "fire": "Нет инф.",
            "terrorism": "Нет инф.",
            "drone": "Нет инф.",
            "tow_truck": "10 000 руб.",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "5 рабочих дней",
            "advantages": "Онлайн-оформление, без справок",
            "weak_points": "Ниже порог тотала",
            "rating": "4.7",
            "offices": "онлайн"
        },
        "ВСК": {
            "franchise": "Условно-безусловная",
            "without_certificates": "Стекла: 5% СС; Прочие: 3% СС",
            "gap": "Включен при 1 периоде",
            "total_loss": "75%",
            "fire": "Исключение",
            "terrorism": "Исключение",
            "drone": "Включен при наличии GAP",
            "tow_truck": "5 000 / 15 000 руб.",
            "repair_type": "Ремонт на СТОА страховщика",
            "payment_terms": "10 рабочих дней",
            "advantages": "Гибкие условия по справкам",
            "weak_points": "Камеры не оплачиваются без справок",
            "rating": "4.2",
            "offices": "800+"
        },
        "Согласие": {
            "franchise": "Условно-безусловная / динамическая",
            "without_certificates": "Неограниченно стекла + 1 элемент",
            "gap": "Отдельный риск",
            "total_loss": "70%",
            "fire": "За доп. плату, 1.15%",
            "terrorism": "За доп. плату (МСК и МО)",
            "drone": "За доп. плату",
            "tow_truck": "5 000 / 10 000 руб.",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "10 рабочих дней",
            "advantages": "Гибкие условия",
            "weak_points": "Тотал 70%",
            "rating": "4.2",
            "offices": "300+"
        },
        "Югория": {
            "franchise": "Условно-безусловная",
            "without_certificates": "Стекла: 1 раз (кроме панорамной)",
            "gap": "Неагрегатная",
            "total_loss": "Не указан",
            "fire": "Исключение",
            "terrorism": "Нет инф.",
            "drone": "Входит",
            "tow_truck": "5% от СС (до 15 000 руб.)",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "10 рабочих дней",
            "advantages": "Гибкие условия пролонгации",
            "weak_points": "При пролонгации доп. франшиза",
            "rating": "3.9",
            "offices": "400+"
        },
        "СберСтрахование": {
            "franchise": "6 видов франшиз",
            "without_certificates": "1 деталь + стекла / Только стекла",
            "gap": "Включен при индексируемой СС",
            "total_loss": "70%",
            "fire": "Исключение",
            "terrorism": "Исключение",
            "drone": "Исключение",
            "tow_truck": "6 000 / 12 000 руб.",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "7 рабочих дней",
            "advantages": "Много вариантов франшизы",
            "weak_points": "Тотал 70%",
            "rating": "4.0",
            "offices": "1000+"
        },
        "Совкомбанк Страхование": {
            "franchise": "Условно-безусловная / Обязательная 25%",
            "without_certificates": "Только ремонт или замена стекла",
            "gap": "Нет инф.",
            "total_loss": "75%",
            "fire": "Входит",
            "terrorism": "Исключение",
            "drone": "Исключение",
            "tow_truck": "6 500 руб.",
            "repair_type": "Ремонт или выплата",
            "payment_terms": "10 рабочих дней",
            "advantages": "Группы событий",
            "weak_points": "Терроризм исключен",
            "rating": "3.8",
            "offices": "200+"
        }
    }

# ==================== ИСТОЧНИКИ ====================

SOURCES = {
    "РЕСО-Гарантия": {"urls": ["https://reso.ru/individual/property/flat/"]},
    "Ингосстрах": {"urls": ["https://www.ingos.ru/property/flat"]},
    "Т-Страхование": {"urls": ["https://tbank.ru/insurance/help/estate/property/about/about-policy/"]},
    "АльфаСтрахование": {"urls": ["https://alfastrahovanie.sddbk.ru/imushestvo/strahovanie-ot-bpla/"]},
    "СберСтрахование": {"urls": ["https://sberbankins.ru/products/home-insurance-online/"]},
    "Согласие": {"urls": ["https://soglasie.ru/company/insurance-rules/"]},
    "Югория": {"urls": ["https://ugsk.ru/property/"]},
    "Совкомбанк Страхование": {"urls": ["https://sovcomins.ru/"]},
    "ВСК": {"urls": ["https://www.vsk.ru/o-kompanii/dlya-kliyentov?t=pravila_i_tarifi_strahovaniya&case=pravila"]},
    "СОГАЗ": {"urls": ["https://www.sogaz.ru/"]},
    "Ренессанс": {"urls": ["https://renessans.sddbk.ru/imushestvo/kvartira/"]}
}

# ==================== УМНЫЙ ПАРСИНГ ====================

# Ключевые слова + "маркеры единиц измерения" — блок, где рядом со словом
# встречается %, руб., "дней" и т.п., почти всегда содержательный, а не мусорный.
KEYWORDS = {
    "franchise": ["франшиз"],
    "without_certificates": ["без справок", "без документ", "лкп", "без предоставления"],
    "gap": ["gap", "гэп"],
    "total_loss": ["тотал", "полная гибель", "конструктивн"],
    "fire": ["самовозгоран", "возгоран"],
    "terrorism": ["терроризм", "терр. акт", "теракт"],
    "drone": ["бпла", "беспилот", "дрон"],
    "tow_truck": ["эвакуа"],
    "repair_type": ["ремонт на сто", "ремонт у диле", "стоа"],
    "payment_terms": ["срок выплат", "срок возмещ", "рабочих дней"],
}

UNIT_MARKERS = re.compile(r'(\d+\s?%|\d+\s?руб|\bдней\b|\bдня\b|\bмесяц)', re.IGNORECASE)

# Теги, которые никогда не должны попадать в текст: скрипты, стили, меню,
# футер, куки-баннеры и т.п. BeautifulSoup НЕ убирает script/style из
# get_text() сам по себе — их надо явно вырезать.
NOISE_TAGS = ["script", "style", "noscript", "nav", "footer", "header",
              "iframe", "svg", "form", "button"]
NOISE_CLASS_HINTS = ["cookie", "menu", "banner", "footer", "header", "modal", "popup"]


def _clean_soup(soup):
    for tag in soup.find_all(NOISE_TAGS):
        tag.decompose()
    for tag in soup.find_all(True, class_=True):
        classes = " ".join(tag.get("class", [])).lower()
        if any(hint in classes for hint in NOISE_CLASS_HINTS):
            tag.decompose()
    return soup


def _text_blocks(soup):
    """Текст по отдельным блокам (параграф/пункт списка/ячейка/заголовок),
    а НЕ вся страница одной строкой. Это главное отличие от старой версии:
    старый код склеивал весь текст страницы без разделителей, из-за чего
    хвост одного блока и начало другого превращались в одно "предложение"."""
    blocks = []
    for el in soup.find_all(["p", "li", "td", "th", "h1", "h2", "h3", "h4", "dd", "dt"]):
        t = ' '.join(el.get_text(" ", strip=True).split())
        if t:
            blocks.append(t)
    return blocks


def _score_match(block, word):
    """Чем ближе к 'настоящему' содержательному предложению — тем выше score."""
    length = len(block)
    if length < 15 or length > 300:
        return -1  # слишком короткое (обрывок меню) или слишком длинное (мусор)
    score = 0
    if UNIT_MARKERS.search(block):
        score += 3  # есть %, руб., "дней" — почти наверняка релевантно
    if block.lower().count(word) == 1:
        score += 1  # слово встречается один раз, не спам-повтор
    # штраф за типичный мусор навигации/футера
    if any(x in block.lower() for x in ["войти", "регистрац", "подпис", "©", "все права"]):
        score -= 5
    return score


# ==================== LLM-ИЗВЛЕЧЕНИЕ (основной метод) ====================
# Вместо поиска по ключевым словам отдаём очищенный текст модели и просим
# заполнить строго заданную схему через forced function calling — модель
# либо заполняет поле тем, что реально нашла в тексте, либо оставляет
# пустым, JSON на выходе гарантированно валиден.
#
# Провайдер выбирается переменной LLM_PROVIDER ("groq" по умолчанию — есть
# бесплатный ключ без карты; "openai" — если задан OPENAI_API_KEY).
# Оба используют OpenAI-совместимый REST-формат, доп. пакеты не нужны.

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

PROVIDER_CONFIG = {
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions", "key_env": "GROQ_API_KEY", "model": GROQ_MODEL},
    "openai": {"url": "https://api.openai.com/v1/chat/completions", "key_env": "OPENAI_API_KEY", "model": OPENAI_MODEL},
}

EXTRACT_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "extract_insurance_fields",
        "description": (
            "Извлекает условия автостраховки КАСКО из текста страницы сайта "
            "страховой компании. Заполняй поле только если в тексте есть "
            "явное подтверждение — если условия не упомянуты, поле нужно "
            "пропустить (не выдумывать значение)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "franchise": {"type": "string", "description": "Тип и размер франшизы"},
                "without_certificates": {"type": "string", "description": "Условия выплаты без справок из ГИБДД"},
                "gap": {"type": "string", "description": "Наличие и условия GAP-страхования"},
                "total_loss": {"type": "string", "description": "Порог полной гибели/тотала в % от страховой суммы"},
                "fire": {"type": "string", "description": "Условия покрытия самовозгорания"},
                "terrorism": {"type": "string", "description": "Условия покрытия риска терроризма"},
                "drone": {"type": "string", "description": "Условия покрытия ущерба от БПЛА/дронов"},
                "tow_truck": {"type": "string", "description": "Условия оплаты эвакуатора"},
                "repair_type": {"type": "string", "description": "Где производится ремонт (СТОА, дилер, выплата)"},
                "payment_terms": {"type": "string", "description": "Срок выплаты возмещения"},
            },
            "required": []
        }
    }
}


def parse_source_llm(url):
    """Извлечение через Groq/OpenAI (см. LLM_PROVIDER). Возвращает None, если
    ключ не настроен, страница не подходит (мало контента) или вызов не
    удался — тогда parse_all_sources() откатится на keyword-парсер, затем
    на fallback."""
    provider = PROVIDER_CONFIG.get(LLM_PROVIDER)
    if not provider:
        print(f"      ⚠️ Неизвестный LLM_PROVIDER='{LLM_PROVIDER}', ожидается 'groq' или 'openai'")
        return None

    api_key = os.environ.get(provider["key_env"])
    if not api_key:
        return None

    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        soup = _clean_soup(BeautifulSoup(response.text, 'html.parser'))
        blocks = _text_blocks(soup)

        if len(blocks) < 5:
            print(f"      ⚠️ {url}: мало контента, вероятно нужен JS-рендеринг — пропуск LLM-извлечения")
            return None

        # Ограничиваем объём текста, который уходит в модель — экономия
        # токенов и защита от случайно огромных страниц.
        page_text = "\n".join(blocks)[:12000]

        llm_response = requests.post(
            provider["url"],
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": provider["model"],
                "messages": [{
                    "role": "user",
                    "content": (
                        "Вот текст страницы сайта страховой компании (уже "
                        "очищен от меню/футера/скриптов):\n\n" + page_text
                    )
                }],
                "tools": [EXTRACT_TOOL_SCHEMA],
                "tool_choice": {"type": "function", "function": {"name": "extract_insurance_fields"}},
            },
            timeout=20,
        )

        if not llm_response.ok:
            # Печатаем реальное тело ответа, а не туманное "NoneType" —
            # там обычно прямо написано, в чём дело (нет квоты, неверный
            # ключ, неверная модель, rate limit и т.п.).
            print(f"      ⚠️ {LLM_PROVIDER} {llm_response.status_code} для {url}: {llm_response.text[:300]}")
            return None

        message = llm_response.json()["choices"][0].get("message") or {}
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return None

        raw_args = json.loads(tool_calls[0]["function"]["arguments"])
        # Убираем пустые строки и явные "не найдено" — модель иногда
        # заполняет поле фразой вместо того, чтобы его пропустить.
        data = {
            k: v for k, v in raw_args.items()
            if isinstance(v, str) and v.strip() and "не найдено" not in v.lower() and "не указано" not in v.lower()
        }
        return data or None
    except Exception as e:
        print(f"      ⚠️ LLM-извлечение не удалось для {url}: {e}")
        return None


# ==================== KEYWORD-ПАРСИНГ (запасной метод) ====================

def parse_source(url):
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(response.text, 'html.parser')
        soup = _clean_soup(soup)
        blocks = _text_blocks(soup)

        # Сигнал того, что страница рендерится через JS и requests её не видит:
        # мало текстовых блоков или почти весь текст короче ожидаемого.
        if len(blocks) < 5:
            print(f"      ⚠️ {url}: подозрительно мало контента ({len(blocks)} блоков) — "
                  f"возможно, страница требует JS-рендеринга (playwright/selenium)")
            return None

        result = {}
        for key, words in KEYWORDS.items():
            best_block, best_score = None, 0
            for word in words:
                for block in blocks:
                    if word in block.lower():
                        score = _score_match(block, word)
                        if score > best_score:
                            best_block, best_score = block, score
            if best_block:
                result[key] = best_block

        return result if result else None
    except Exception:
        return None

def parse_all_sources():
    print(f"🔄 Сбор данных...")
    all_data = {}
    
    for name, info in SOURCES.items():
        print(f"   Парсим {name}...")
        for url in info["urls"]:
            result = parse_source_llm(url) or parse_source(url)
            if result:
                all_data[name] = result
                print(f"      ✅ Найдено: {len(result)} полей")
                break
        time.sleep(0.5)
    
    # Добавляем недостающие поля из запасных данных
    fallback = get_fallback_data()
    for name, data in fallback.items():
        if name in all_data:
            for key, value in data.items():
                if key not in all_data[name] or not all_data[name][key]:
                    all_data[name][key] = value
        else:
            all_data[name] = data
            print(f"   📦 Запасные данные для {name}")
    
    all_data["_last_updated"] = datetime.now().isoformat()
    return all_data

# ==================== ЗАГРУЗКА ====================

print("📦 Загрузка данных...")
INSURANCE_DATA = parse_all_sources()
ALL_COMPANIES = [c for c in INSURANCE_DATA.keys() if not c.startswith("_")]
print(f"✅ Загружено {len(ALL_COMPANIES)} компаний")

# ==================== ПОЛЬЗОВАТЕЛИ ====================

USERS_FILE = "users.json"

def load_users():
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

# ==================== МАРШРУТЫ ====================

@app.route('/')
def index():
    user = session.get('user')
    last_updated = INSURANCE_DATA.get("_last_updated", "неизвестно")
    return render_template('index.html', 
                         companies=ALL_COMPANIES,
                         user=user,
                         now=datetime.now().strftime("%Y-%m-%d %H:%M"),
                         last_updated=last_updated)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        users = load_users()
        if username in users:
            return "❌ Пользователь уже существует! <a href='/login'>Войти</a>"
        users[username] = hashlib.sha256(password.encode()).hexdigest()
        save_users(users)
        return "✅ Регистрация успешна! <a href='/login'>Войти</a>"
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        users = load_users()
        if username in users and users[username] == hashlib.sha256(password.encode()).hexdigest():
            session['user'] = username
            return redirect('/')
        return "❌ Неверный логин или пароль!"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/compare', methods=['GET', 'POST'])
def compare():
    user = session.get('user')
    if not user:
        return redirect('/login')
    
    if request.method == 'POST':
        main_company = request.form.get('main_company')
        company2 = request.form.get('company2')
        
        if not main_company or not company2:
            return "❌ Выберите обе компании!"
        
        data1 = INSURANCE_DATA.get(main_company, {})
        data2 = INSURANCE_DATA.get(company2, {})
        
        advantages = []
        total1 = data1.get("total_loss", "0%").replace("%", "")
        total2 = data2.get("total_loss", "0%").replace("%", "")
        if total1.isdigit() and total2.isdigit():
            if int(total1) > int(total2):
                advantages.append(f"✅ {main_company} лучше по порогу тотала: {total1}% vs {total2}%")
        
        return render_template('result.html',
                             company1=main_company,
                             company2=company2,
                             main_company=main_company,
                             data1=data1,
                             data2=data2,
                             advantages=advantages,
                             timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    return render_template('compare_form.html', companies=ALL_COMPANIES)

@app.route('/payment')
def payment():
    return render_template('payment.html', user=session.get('user'))

@app.route('/update')
def manual_update():
    global INSURANCE_DATA, ALL_COMPANIES
    print("🔄 Ручное обновление...")
    INSURANCE_DATA = parse_all_sources()
    ALL_COMPANIES = [c for c in INSURANCE_DATA.keys() if not c.startswith("_")]
    return "✅ Данные обновлены! <a href='/'>На главную</a>"

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
.user-bar{text-align:right;font-size:14px;margin-bottom:15px}
.btn{display:block;width:100%;padding:14px;background:#27ae60;color:white;text-align:center;text-decoration:none;border:none;border-radius:8px;font-size:16px;cursor:pointer;margin:10px 0}
.btn-blue{background:#3498db}
.btn-orange{background:#f39c12}
.status{text-align:center;font-size:14px;padding:10px;border-radius:8px;margin:10px 0}
.status-ok{background:#d5f5e3;color:#27ae60}
.status-no{background:#fadbd8;color:#e74c3c}
.meta{text-align:center;color:#888;font-size:11px;margin-top:15px}
.update-info{text-align:center;color:#27ae60;font-size:12px;margin-top:5px}
a{color:#3498db;text-decoration:none}
</style>
</head>
<body>
<div class="container">
<div class="user-bar">{% if user %}👤 {{ user }} | <a href="/logout">Выйти</a>{% else %}<a href="/login">Войти</a> | <a href="/register">Регистрация</a>{% endif %}</div>
<h1>🔍 Сравнение КАСКО</h1>
<p style="text-align:center;color:#555;">Сравни страховые компании за 99 ₽</p>
<div class="update-info">🤖 Данные собираются автоматически</div>
<div class="update-info">📅 Последнее обновление: {{ last_updated[:16] if last_updated != 'неизвестно' else 'неизвестно' }}</div>
{% if user %}
<div class="status status-ok">✅ Вы вошли как {{ user }}</div>
<a href="/compare" class="btn">📊 Новое сравнение</a>
<a href="/payment" class="btn btn-blue">💳 Оплатить (99 ₽ / 399 ₽)</a>
<a href="/update" class="btn btn-orange">🔄 Обновить данные сейчас</a>
{% else %}
<div class="status status-no">⚠️ Войдите, чтобы сравнивать</div>
<a href="/login" class="btn btn-blue">🔑 Войти</a>
<a href="/register" class="btn btn-orange">📝 Зарегистрироваться</a>
{% endif %}
<div class="meta">Обновлено: {{ now }}</div>
</div>
</body>
</html>
''')

with open('templates/compare_form.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Сравнение</title>
<style>
body{font-family:Arial;padding:10px;background:#f5f5f5}
.container{max-width:500px;margin:0 auto;background:white;padding:20px;border-radius:10px}
select{width:100%;padding:12px;margin:8px 0;border:1px solid #ddd;border-radius:8px}
.btn{width:100%;padding:14px;background:#27ae60;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer}
.vs{text-align:center;font-size:24px;color:#e74c3c;margin:5px 0}
.back{display:inline-block;margin-top:10px;color:#3498db;text-decoration:none}
.label{font-weight:bold;color:#555;display:block;margin-top:10px}
</style>
</head>
<body>
<div class="container">
<h1>📊 Сравнение</h1>
<p style="text-align:center;color:#555;">Выберите основную компанию и вторую для сравнения</p>
<form method="post">
<label class="label">🏆 Основная компания (ваша):</label>
<select name="main_company" required>
<option value="">-- Выберите --</option>{% for c in companies %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
</select>
<div class="vs">⚔️</div>
<label class="label">Компания для сравнения:</label>
<select name="company2" required>
<option value="">-- Выберите --</option>{% for c in companies %}<option value="{{ c }}">{{ c }}</option>{% endfor %}
</select>
<button type="submit" class="btn">Сравнить →</button>
</form>
<a href="/" class="back">← На главную</a>
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
table{width:100%;border-collapse:collapse;font-size:13px;margin:10px 0}
th,td{border:1px solid #ddd;padding:6px;text-align:left;vertical-align:top}
th{background:#2c3e50;color:white}
.main-badge{background:#27ae60;color:white;padding:3px 10px;border-radius:12px;font-size:12px;margin-left:10px}
.vs-title{text-align:center;font-size:18px;font-weight:bold;margin:10px 0;padding:10px;background:#f0f8ff;border-radius:8px}
.advantage{color:#27ae60}
.back{display:inline-block;margin-top:10px;color:#3498db;text-decoration:none}
.meta{text-align:center;color:#888;font-size:11px;margin-top:15px}
</style>
</head>
<body>
<div class="container">
<h1>📊 Результат сравнения</h1>
<div class="vs-title">🏆 {{ main_company }} <span class="main-badge">ОСНОВНАЯ</span><br>⚔️ {{ company2 }}</div>
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
<a href="/compare" class="back">← Новое сравнение</a><br>
<a href="/" class="back">На главную</a>
<div class="meta">Обновлено: {{ timestamp }}</div>
</div>
</body>
</html>
''')

with open('templates/register.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Регистрация</title>
<style>body{font-family:Arial;padding:20px;background:#f5f5f5}.container{max-width:400px;margin:0 auto;background:white;padding:20px;border-radius:10px}input{width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:8px}button{width:100%;padding:12px;background:#27ae60;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer}a{color:#3498db}</style></head>
<body><div class="container"><h2>Регистрация</h2><form method="post"><input type="text" name="username" placeholder="Имя" required><input type="password" name="password" placeholder="Пароль" required><button type="submit">Зарегистрироваться</button></form><p><a href="/login">Уже есть аккаунт? Войти</a></p></div></body></html>
''')

with open('templates/login.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Вход</title>
<style>body{font-family:Arial;padding:20px;background:#f5f5f5}.container{max-width:400px;margin:0 auto;background:white;padding:20px;border-radius:10px}input{width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:8px}button{width:100%;padding:12px;background:#3498db;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer}a{color:#3498db}</style></head>
<body><div class="container"><h2>Вход</h2><form method="post"><input type="text" name="username" placeholder="Имя" required><input type="password" name="password" placeholder="Пароль" required><button type="submit">Войти</button></form><p><a href="/register">Нет аккаунта? Зарегистрироваться</a></p></div></body></html>
''')

with open('templates/payment.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Оплата</title>
<style>body{font-family:Arial;padding:20px;background:#f5f5f5}.container{max-width:400px;margin:0 auto;background:white;padding:20px;border-radius:10px}.btn{display:block;width:100%;padding:14px;margin:10px 0;border:none;border-radius:8px;font-size:16px;cursor:pointer}.btn-green{background:#27ae60;color:white}.btn-blue{background:#3498db;color:white}a{color:#3498db}</style></head>
<body><div class="container"><h2>💳 Оплата</h2><p>Пользователь: {{ user }}</p><form method="post" action="/pay"><button type="submit" name="type" value="single" class="btn btn-green">🔹 Разовое сравнение — 99 ₽</button><button type="submit" name="type" value="subscription" class="btn btn-blue">🔹 Подписка на месяц — 399 ₽</button></form><br><a href="/">На главную</a></div></body></html>
''')
