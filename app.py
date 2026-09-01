from flask import Flask, render_template, request, session, redirect, url_for
from datetime import datetime
import json
import os
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# ДАННЫЕ
INSURANCE_DATA = {
    "РЕСО-Гарантия": {
        "franchise": "Безусловная / условно-безусловная",
        "total_loss": "75%",
        "rating": "4.5",
        "offices": "1200+"
    },
    "СОГАЗ": {
        "franchise": "Безусловная / условно-безусловная",
        "total_loss": "70%",
        "rating": "4.3",
        "offices": "500+"
    },
    "АльфаСтрахование": {
        "franchise": "Условно-безусловная",
        "total_loss": "75%",
        "rating": "4.6",
        "offices": "600+"
    },
    "Ингосстрах": {
        "franchise": "Условная/условно-безусловная",
        "total_loss": "75%",
        "rating": "4.4",
        "offices": "900+"
    },
    "Ренессанс": {
        "franchise": "11 видов франшиз",
        "total_loss": "75%",
        "rating": "4.3",
        "offices": "500+"
    },
    "Т-Страхование": {
        "franchise": "Условно-безусловная",
        "total_loss": "65%",
        "rating": "4.7",
        "offices": "онлайн"
    },
    "ВСК": {
        "franchise": "Условно-безусловная",
        "total_loss": "75%",
        "rating": "4.2",
        "offices": "800+"
    },
    "Согласие": {
        "franchise": "Условно-безусловная / динамическая",
        "total_loss": "70%",
        "rating": "4.2",
        "offices": "300+"
    },
    "Югория": {
        "franchise": "Условно-безусловная",
        "total_loss": "Не указан",
        "rating": "3.9",
        "offices": "400+"
    },
    "СберСтрахование": {
        "franchise": "6 видов франшиз",
        "total_loss": "70%",
        "rating": "4.0",
        "offices": "1000+"
    },
    "Совкомбанк Страхование": {
        "franchise": "Условно-безусловная / Обязательная 25%",
        "total_loss": "75%",
        "rating": "3.8",
        "offices": "200+"
    }
}

ALL_COMPANIES = list(INSURANCE_DATA.keys())
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

@app.route('/')
def index():
    user = session.get('user')
    return render_template('index.html', companies=ALL_COMPANIES, user=user, now=datetime.now().strftime("%Y-%m-%d %H:%M"))

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
        # ВСЕ ДАННЫЕ ИЗ ФОРМЫ
        main_company = request.form.get('main_company')
        company2 = request.form.get('company2')
        
        # ОТЛАДКА — покажем, что пришло
        debug_info = f"""
        <h3>Отладка:</h3>
        <p>main_company = {main_company}</p>
        <p>company2 = {company2}</p>
        <p><a href="/compare">Назад</a></p>
        """
        
        if not main_company or not company2:
            return debug_info + "<p>❌ Одна из компаний не выбрана!</p>"
        
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

# ==================== СОЗДАНИЕ ШАБЛОНОВ ====================
os.makedirs('templates', exist_ok=True)

with open('templates/index.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
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
        .btn-blue{background:#3498db}
        .btn-orange{background:#f39c12}
        .status{text-align:center;font-size:14px;padding:10px;border-radius:8px;margin:10px 0}
        .status-ok{background:#d5f5e3;color:#27ae60}
        .status-no{background:#fadbd8;color:#e74c3c}
        .meta{text-align:center;color:#888;font-size:11px;margin-top:15px}
        a{color:#3498db;text-decoration:none}
    </style>
</head>
<body>
<div class="container">
    <div class="user-bar">{% if user %}👤 {{ user }} | <a href="/logout">Выйти</a>{% else %}<a href="/login">Войти</a> | <a href="/register">Регистрация</a>{% endif %}</div>
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
</html>
''')

with open('templates/compare_form.html', 'w') as f:
    f.write('''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Сравнение</title>
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
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Результат сравнения</title>
    <style>
        body{font-family:Arial;padding:10px;background:#f5f5f5}
        .container{max-width:600px;margin:0 auto;background:white;padding:20px;border-radius:10px}
        table{width:100%;border-collapse:collapse;font-size:14px;margin:10px 0}
        th,td{border:1px solid #ddd;padding:8px;text-align:left}
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
        <tr><td>Франшиза</td><td>{{ data1.franchise or '—' }}</td><td>{{ data2.franchise or '—' }}</td></tr>
        <tr><td>Порог тотала</td><td>{{ data1.total_loss or '—' }}</td><td>{{ data2.total_loss or '—' }}</td></tr>
        <tr><td>Рейтинг</td><td>{{ data1.rating or '—' }}</td><td>{{ data2.rating or '—' }}</td></tr>
        <tr><td>Офисы</td><td>{{ data1.offices or '—' }}</td><td>{{ data2.offices or '—' }}</td></tr>
    </table>
    <div class="analysis"><strong>📋 Анализ</strong><ul>{% for adv in advantages %}<li class="advantage">✅ {{ adv }}</li>{% endfor %}</ul></div>
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
