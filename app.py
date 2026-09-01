# app.py — для Streamlit Cloud

from flask import Flask, render_template, request, session, redirect, url_for
from datetime import datetime, timedelta
import json
import os
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# ==================== ДАННЫЕ ====================
# # main_agent.py — ПОЛНАЯ ВЕРСИЯ С МОНЕТИЗАЦИЕЙ

from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from datetime import datetime, timedelta
import json
import os
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# ==================== ФАЙЛЫ ДЛЯ ХРАНЕНИЯ ====================
USERS_FILE = "users.json"
PAYMENTS_FILE = "payments.json"

# ==================== ДАННЫЕ ====================
INSURANCE_DATA = {
    "РЕСО-Гарантия": {
        "franchise": "Безусловная / условно-безусловная",
        "without_certificates": "Стекла без ограничений; 1 кузовной элемент в год",
        "gap": "Отдельный риск",
        "total_loss": "75%",
        "drone": "Лимит 1% СС",
        "advantages": "Ремонт у дилера, 5 дней на выплату, без учета износа",
        "weak_points": "Требуется уточнение условий",
        "rating": "4.5",
        "offices": "1200+",
        "highlight": {
            "total_loss": "✅ Самый высокий порог тотала — 75%",
            "repair": "✅ Ремонт у официального дилера",
            "payment": "✅ Выплата за 5 дней — быстрее всех"
        }
    },
    "СОГАЗ": {
        "franchise": "Безусловная / условно-безусловная",
        "without_certificates": "Вариантно: 1 раз один элемент / Неограниченно стекла + 1 раз кузовной",
        "gap": "Отдельный риск",
        "total_loss": "70%",
        "drone": "Исключение",
        "advantages": "Гибкие условия, надёжность",
        "weak_points": "Тотал 70%, выплата 30 дней",
        "rating": "4.3",
        "offices": "500+",
        "highlight": {
            "reliability": "✅ Надёжность подтверждена рейтингами"
        }
    },
    "АльфаСтрахование": {
        "franchise": "Условно-безусловная",
        "without_certificates": "Стекла без ограничений + 1 кузовной элемент 2 раза в год",
        "gap": "Включен по умолчанию",
        "total_loss": "75%",
        "drone": "За доп. плату",
        "advantages": "Без справок с бонусами",
        "weak_points": "Франшиза на Хищение",
        "rating": "4.6",
        "offices": "600+",
        "highlight": {
            "without_certificates": "✅ Щедрые лимиты без справок"
        }
    },
    "Ингосстрах": {
        "franchise": "Условная/условно-безусловная",
        "without_certificates": "ЛПКП 1 деталь; остекление (кроме крыши)",
        "gap": "Включен при постоянной СС",
        "total_loss": "75%",
        "drone": "За доп. плату",
        "advantages": "Широкая сеть офисов",
        "weak_points": "Без справок – только ЛКП 1 детали",
        "rating": "4.4",
        "offices": "900+",
        "highlight": {
            "offices": "✅ Более 900 офисов по всей стране"
        }
    },
    "Ренессанс": {
        "franchise": "11 видов франшиз",
        "without_certificates": "Вариативно (стекла / до 5% СС)",
        "gap": "Отдельный риск",
        "total_loss": "75%",
        "drone": "За доп. плату",
        "advantages": "Много вариантов франшизы",
        "weak_points": "Эвакуация за доп. плату",
        "rating": "4.3",
        "offices": "500+",
        "highlight": {
            "franchise": "✅ 11 видов франшизы на выбор"
        }
    },
    "Т-Страхование": {
        "franchise": "Условно-безусловная",
        "without_certificates": "Стекла неогранич.; Кузов до 3% СС",
        "gap": "Отдельный риск",
        "total_loss": "65%",
        "drone": "Нет инф.",
        "advantages": "Онлайн-оформление",
        "weak_points": "Ниже порог тотала",
        "rating": "4.7",
        "offices": "онлайн",
        "highlight": {
            "online": "✅ Полностью онлайн-оформление"
        }
    },
    "ВСК": {
        "franchise": "Условно-безусловная",
        "without_certificates": "Стекла: 5% СС; Прочие: 3% СС",
        "gap": "Включен при 1 периоде",
        "total_loss": "75%",
        "drone": "Включен при наличии GAP",
        "advantages": "Гибкие условия по справкам",
        "weak_points": "Камеры не оплачиваются без справок",
        "rating": "4.2",
        "offices": "800+",
        "highlight": {
            "flexibility": "✅ Гибкие условия по справкам"
        }
    },
    "Согласие": {
        "franchise": "Условно-безусловная / динамическая",
        "without_certificates": "Неограниченно стекла + 1 элемент",
        "gap": "Отдельный риск",
        "total_loss": "70%",
        "drone": "За доп. плату",
        "advantages": "Гибкие условия",
        "weak_points": "Тотал 70%",
        "rating": "4.2",
        "offices": "300+",
        "highlight": {
            "flexibility": "✅ Гибкие условия"
        }
    },
    "Югория": {
        "franchise": "Условно-безусловная",
        "without_certificates": "Стекла: 1 раз (кроме панорамной)",
        "gap": "Неагрегатная",
        "total_loss": "Не указан",
        "drone": "Входит",
        "advantages": "Гибкие условия пролонгации",
        "weak_points": "При пролонгации доп. франшиза",
        "rating": "3.9",
        "offices": "400+",
        "highlight": {
            "prolongation": "✅ Гибкие условия пролонгации"
        }
    },
    "СберСтрахование": {
        "franchise": "6 видов франшиз",
        "without_certificates": "1 деталь + стекла / Только стекла",
        "gap": "Включен при индексируемой СС",
        "total_loss": "70%",
        "drone": "Исключение",
        "advantages": "Много вариантов франшизы",
        "weak_points": "Тотал 70%",
        "rating": "4.0",
        "offices": "1000+",
        "highlight": {
            "franchise": "✅ 6 видов франшизы"
        }
    },
    "Совкомбанк Страхование": {
        "franchise": "Условно-безусловная / Обязательная 25%",
        "without_certificates": "Только ремонт или замена стекла",
        "gap": "Нет инф.",
        "total_loss": "75%",
        "drone": "Исключение",
        "advantages": "Группы событий",
        "weak_points": "Терроризм исключен",
        "rating": "3.8",
        "offices": "200+",
        "highlight": {
            "events": "✅ Группы событий"
        }
    }
}

ALL_COMPANIES = list(INSURANCE_DATA.keys())

# ==================== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ====================

def load_users():
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def load_payments():
    try:
        with open(PAYMENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_payments(payments):
    with open(PAYMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(payments, f, ensure_ascii=False, indent=2)

def get_user_payments(username):
    payments = load_payments()
    return payments.get(username, [])

def add_payment(username, payment_type, amount):
    payments = load_payments()
    if username not in payments:
        payments[username] = []
    payments[username].append({
        "type": payment_type,  # "single" или "subscription"
        "amount": amount,
        "date": datetime.now().isoformat(),
        "expires": (datetime.now() + timedelta(days=30)).isoformat() if payment_type == "subscription" else None
    })
    save_payments(payments)

def has_active_subscription(username):
    payments = get_user_payments(username)
    for p in payments:
        if p["type"] == "subscription" and p.get("expires"):
            expires = datetime.fromisoformat(p["expires"])
            if expires > datetime.now():
                return True
    return False

def has_single_payment_today(username):
    payments = get_user_payments(username)
    today = datetime.now().date()
    for p in payments:
        if p["type"] == "single":
            date = datetime.fromisoformat(p["date"]).date()
            if date == today:
                return True
    return False

def can_compare(username):
    if not username:
        return False, "Войдите в аккаунт"
    
    # Проверяем подписку
    if has_active_subscription(username):
        return True, "✅ Подписка активна"
    
    # Проверяем разовый платёж сегодня
    if has_single_payment_today(username):
        return True, "✅ Разовый платёж сегодня выполнен"
    
    return False, "❌ Нет активной подписки или разового платежа"

# ==================== СРАВНЕНИЕ ====================

def get_highlighted_comparison(company1_data, company2_data, main_company_name):
    """Сравнивает две компании, выделяя преимущества основной"""
    result = {
        "main_company": main_company_name,
        "advantages": [],
        "disadvantages": [],
        "comparison": {}
    }
    
    # Сравниваем по параметрам
    params = ["total_loss", "rating", "offices", "franchise"]
    for param in params:
        v1 = company1_data.get(param, "—")
        v2 = company2_data.get(param, "—")
        
        # Убираем проценты для сравнения
        v1_clean = v1.replace("%", "").strip() if v1 != "—" else "—"
        v2_clean = v2.replace("%", "").strip() if v2 != "—" else "—"
        
        result["comparison"][param] = {
            "company1": v1,
            "company2": v2
        }
        
        # Если есть числовые значения — сравниваем
        if v1_clean != "—" and v2_clean != "—" and v1_clean.isdigit() and v2_clean.isdigit():
            if int(v1_clean) > int(v2_clean):
                if main_company_name == "РЕСО-Гарантия":  # Определяем, какая компания основная
                    result["advantages"].append(f"✅ {main_company_name} лучше по {param}: {v1} vs {v2}")
                else:
                    result["disadvantages"].append(f"⚠️ {main_company_name} уступает по {param}: {v1} vs {v2}")
            elif int(v1_clean) < int(v2_clean):
                if main_company_name != "РЕСО-Гарантия":
                    result["advantages"].append(f"✅ {main_company_name} лучше по {param}: {v1} vs {v2}")
                else:
                    result["disadvantages"].append(f"⚠️ {main_company_name} уступает по {param}: {v1} vs {v2}")
    
    return result

# ==================== МАРШРУТЫ ====================

@app.route('/')
def index():
    user = session.get('user')
    return render_template('index.html', 
                         companies=ALL_COMPANIES,
                         user=user,
                         now=datetime.now().strftime("%Y-%m-%d %H:%M"))

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
    
    return '''
    <h2>Регистрация</h2>
    <form method="post">
        <input type="text" name="username" placeholder="Имя" required>
        <input type="password" name="password" placeholder="Пароль" required>
        <button type="submit">Зарегистрироваться</button>
    </form>
    <a href="/login">Уже есть аккаунт? Войти</a>
    '''

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
    
    return '''
    <h2>Вход</h2>
    <form method="post">
        <input type="text" name="username" placeholder="Имя" required>
        <input type="password" name="password" placeholder="Пароль" required>
        <button type="submit">Войти</button>
    </form>
    <a href="/register">Нет аккаунта? Зарегистрироваться</a>
    '''

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

@app.route('/payment')
def payment():
    user = session.get('user')
    if not user:
        return redirect('/login')
    
    return '''
    <h2>💳 Оплата</h2>
    <p>Пользователь: ''' + user + '''</p>
    <form method="post" action="/pay">
        <button type="submit" name="type" value="single">🔹 Разовое сравнение — 99 ₽</button>
        <br><br>
        <button type="submit" name="type" value="subscription">🔹 Подписка на месяц — 399 ₽</button>
    </form>
    <br>
    <a href="/">На главную</a>
    '''

@app.route('/pay', methods=['POST'])
def pay():
    user = session.get('user')
    if not user:
        return redirect('/login')
    
    payment_type = request.form.get('type')
    if payment_type == "single":
        add_payment(user, "single", 99)
        return "✅ Оплата 99 ₽ прошла успешно! <a href='/'>На главную</a>"
    elif payment_type == "subscription":
        add_payment(user, "subscription", 399)
        return "✅ Подписка на месяц оформлена! <a href='/'>На главную</a>"
    
    return "❌ Ошибка оплаты"

@app.route('/compare', methods=['GET', 'POST'])
def compare():
    user = session.get('user')
    if not user:
        return redirect('/login')
    
    if request.method == 'POST':
        main_company = request.form.get('main_company')
        company2 = request.form.get('company2')
        
        # Исправление: если company1 не пришла, используем main_company
        company1 = request.form.get('company1')
        if not company1:
            company1 = main_company
        
        if not main_company or not company2:
            return "Выберите все компании", 400
        
        data_main = INSURANCE_DATA.get(main_company, {})
        data_comp = INSURANCE_DATA.get(company2, {})
        
        advantages = []
        total_main = data_main.get("total_loss", "0%").replace("%", "")
        total_comp = data_comp.get("total_loss", "0%").replace("%", "")
        if total_main.isdigit() and total_comp.isdigit():
            if int(total_main) > int(total_comp):
                advantages.append(f"✅ {main_company} лучше по порогу тотала: {total_main}% vs {total_comp}%")
        
        return render_template('result.html',
                             company1=company1,
                             company2=company2,
                             main_company=main_company,
                             data1=data_main,
                             data2=data_comp,
                             advantages=advantages,
                             timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    return render_template('compare.html', companies=ALL_COMPANIES)
# ==================== ШАБЛОНЫ ====================

# Создаём папку templates
os.makedirs('templates', exist_ok=True)

# index.html
with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write('''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Сравнение КАСКО</title>
    <style>
        body{font-family:Arial;padding:10px;background:#f5f5f5}
        .container{max-width:500px;margin:0 auto;background:white;padding:20px;border-radius:10px}
        h1{font-size:20px;text-align:center;color:#2c3e50}
        .user-bar{text-align:right;font-size:14px;margin-bottom:15px}
        .btn{display:block;width:100%;padding:14px;background:#27ae60;color:white;text-align:center;text-decoration:none;border:none;border-radius:8px;font-size:16px;cursor:pointer;margin:10px 0}
        .btn:hover{background:#219a52}
        .btn-blue{background:#3498db}
        .btn-blue:hover{background:#2980b9}
        .btn-orange{background:#f39c12}
        .btn-orange:hover{background:#e67e22}
        .meta{text-align:center;color:#888;font-size:11px;margin-top:15px}
        a{color:#3498db;text-decoration:none}
        .status{text-align:center;font-size:14px;padding:10px;border-radius:8px;margin:10px 0}
        .status-ok{background:#d5f5e3;color:#27ae60}
        .status-no{background:#fadbd8;color:#e74c3c}
    </style>
</head>
<body>
<div class="container">
    <div class="user-bar">
        {% if user %}
            👤 {{ user }} | <a href="/logout">Выйти</a>
        {% else %}
            <a href="/login">Войти</a> | <a href="/register">Регистрация</a>
        {% endif %}
    </div>
    
    <h1>🔍 Сравнение КАСКО</h1>
    <p style="text-align:center;color:#555;">Сравни страховые компании за 99 ₽</p>
    
    {% if user %}
        <div class="status status-ok">✅ Вы вошли как {{ user }}</div>
        <a href="/compare" class="btn">📊 Новое сравнение</a>
        <a href="/payment" class="btn btn-blue">💳 Оплатить (99 ₽ / 399 ₽)</a>
    {% else %}
        <div class="status status-no">⚠️ Войдите, чтобы сравнивать</div>
        <a href="/login" class="btn btn-blue">🔑 Войти</a>
        <a href="/register" class="btn btn-orange">📝 Зарегистрироваться</a>
    {% endif %}
    
    <div class="meta">Обновлено: {{ now }}</div>
</div>
</body>
</html>''')

# compare_form.html
with open('templates/compare_form.html', 'w', encoding='utf-8') as f:
    f.write('''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Сравнение</title>
    <style>
        body{font-family:Arial;padding:10px;background:#f5f5f5}
        .container{max-width:500px;margin:0 auto;background:white;padding:20px;border-radius:10px}
        h1{font-size:20px;text-align:center}
        select{width:100%;padding:12px;font-size:16px;margin:8px 0;border:1px solid #ddd;border-radius:8px}
        .btn{width:100%;padding:14px;background:#27ae60;color:white;border:none;border-radius:8px;font-size:16px;cursor:pointer}
        .btn:hover{background:#219a52}
        .back{display:inline-block;margin-top:10px;color:#3498db;text-decoration:none}
        .label{font-weight:bold;color:#555;margin-top:10px;display:block}
        .vs{text-align:center;font-size:20px;color:#e74c3c;margin:5px 0}
    </style>
</head>
<body>
<div class="container">
    <h1>📊 Сравнение</h1>
    <p style="text-align:center;color:#555;">Выберите основную компанию и вторую для сравнения</p>
    
    <form method="post">
        <label class="label">🏆 Основная компания (ваша):</label>
        <select name="main_company" required>
            <option value="">-- Выберите --</option>
            {% for c in companies %}
            <option value="{{ c }}">{{ c }}</option>
            {% endfor %}
        </select>
        
        <div class="vs">⚔️</div>
        
        <label class="label">Компания для сравнения:</label>
        <select name="company2" required>
            <option value="">-- Выберите --</option>
            {% for c in companies %}
            <option value="{{ c }}">{{ c }}</option>
            {% endfor %}
        </select>
        
        <input type="hidden" name="company1" value="{{ main_company or '' }}">
        
        <button type="submit" class="btn">Сравнить →</button>
    </form>
    
    <a href="/" class="back">← На главную</a>
</div>
</body>
</html>''')

# result.html
with open('templates/result.html', 'w', encoding='utf-8') as f:
    f.write('''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Результат сравнения</title>
    <style>
        body{font-family:Arial;padding:10px;background:#f5f5f5}
        .container{max-width:600px;margin:0 auto;background:white;padding:20px;border-radius:10px}
        h1{font-size:20px;text-align:center}
        .vs-title{text-align:center;font-size:18px;font-weight:bold;margin:10px 0;padding:10px;background:#f0f8ff;border-radius:8px}
        .main-badge{background:#27ae60;color:white;padding:3px 10px;border-radius:12px;font-size:12px;margin-left:10px}
        table{width:100%;border-collapse:collapse;font-size:14px;margin:10px 0}
        th,td{border:1px solid #ddd;padding:8px;text-align:left}
        th{background:#2c3e50;color:white}
        .analysis{background:#f0f8ff;padding:15px;border-radius:8px;margin:10px 0}
        .analysis ul{padding-left:20px}
        .analysis li{margin:5px 0}
        .advantage{color:#27ae60}
        .disadvantage{color:#e74c3c}
        .back{display:inline-block;margin-top:10px;color:#3498db;text-decoration:none}
        .meta{text-align:center;color:#888;font-size:11px;margin-top:15px}
    </style>
</head>
<body>
<div class="container">
    <h1>📊 Результат сравнения</h1>
    
    <div class="vs-title">
        🏆 {{ main_company }} <span class="main-badge">ОСНОВНАЯ</span>
        <br>
        ⚔️ {{ company2 }}
    </div>
    
    <table>
        <tr><th>Параметр</th><th>{{ company1 }}</th><th>{{ company2 }}</th></tr>
        <tr><td>Франшиза</td><td>{{ data1.franchise or '—' }}</td><td>{{ data2.franchise or '—' }}</td></tr>
        <tr><td>Без справок</td><td>{{ data1.without_certificates or '—' }}</td><td>{{ data2.without_certificates or '—' }}</td></tr>
        <tr><td>Порог тотала</td><td>{{ data1.total_loss or '—' }}</td><td>{{ data2.total_loss or '—' }}</td></tr>
        <tr><td>БПЛА</td><td>{{ data1.drone or '—' }}</td><td>{{ data2.drone or '—' }}</td></tr>
        <tr><td>Рейтинг</td><td>{{ data1.rating or '—' }}</td><td>{{ data2.rating or '—' }}</td></tr>
        <tr><td>Офисы</td><td>{{ data1.offices or '—' }}</td><td>{{ data2.offices or '—' }}</td></tr>
    </table>
    
    <div class="analysis">
        <strong>📋 Анализ</strong>
        
        {% if comparison.advantages %}
        <p style="color:#27ae60;margin-top:10px;"><strong>✅ Преимущества {{ main_company }}:</strong></p>
        <ul>
            {% for adv in comparison.advantages %}
            <li class="advantage">{{ adv }}</li>
            {% endfor %}
        </ul>
        {% endif %}
        
        {% if comparison.disadvantages %}
        <p style="color:#e74c3c;margin-top:10px;"><strong>⚠️ Где {{ main_company }} уступает:</strong></p>
        <ul>
            {% for dis in comparison.disadvantages %}
            <li class="disadvantage">{{ dis }}</li>
            {% endfor %}
        </ul>
        {% endif %}
        
        {% if not comparison.advantages and not comparison.disadvantages %}
        <p>Нет данных для сравнения</p>
        {% endif %}
    </div>
    
    <a href="/compare" class="back">← Новое сравнение</a>
    <br>
    <a href="/" class="back">На главную</a>
    
    <div class="meta">Обновлено: {{ timestamp }}</div>
</div>
</body>
</html>''')


# ==================== ЗАПУСК ====================

