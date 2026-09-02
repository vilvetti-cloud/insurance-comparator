from flask import Flask, request, render_template_string

app = Flask(__name__)

HTML_FORM = '''
<!DOCTYPE html>
<html>
<body>
    <h1>Тестовая форма</h1>
    <form method="POST">
        <label>Компания 1:</label>
        <input type="text" name="company1" value="РЕСО-Гарантия">
        <br>
        <label>Компания 2:</label>
        <input type="text" name="company2" value="СОГАЗ">
        <br>
        <button type="submit">Отправить</button>
    </form>
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        c1 = request.form.get('company1')
        c2 = request.form.get('company2')
        return f"<h2>Получено:</h2><p>company1 = {c1}</p><p>company2 = {c2}</p>"
    return HTML_FORM
