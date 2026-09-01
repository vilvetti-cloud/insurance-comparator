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
# ... (вставь сюда ВЕСЬ код из твоего main_agent.py)
# ... до самого конца

# ==================== ЗАПУСК ====================

