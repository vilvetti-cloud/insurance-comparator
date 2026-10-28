"""Registration, sign-in, personal account, purchases and the free-comparison limit.

Switched on when ACCOUNTS_DATABASE_URL and SECRET_KEY are set (on Vercel the
first one is the Supabase connection string). Without them the site works as
before, without limits.

Payments: until a real provider is connected, users are told to get a
subscription from the owner, who grants it on /admin. The owner can try the
test checkout (PAYMENTS_TEST=1). ADMIN_EMAILS (comma separated) see the
service menu «Контроль данных» and the admin page.
"""
from __future__ import annotations

import os
import secrets
from functools import wraps
from urllib.parse import urlsplit

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request, session,
                   url_for)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from core import mailer
from core.accounts import FREE_COMPARISONS, PLANS, AccountStore

bp = Blueprint("accounts", __name__)
_store: AccountStore | None = None
VISITOR_COOKIE = "vid"


def enabled() -> bool:
    return bool(os.environ.get("ACCOUNTS_DATABASE_URL") and os.environ.get("SECRET_KEY"))


def store() -> AccountStore:
    global _store
    if _store is None:
        _store = AccountStore(os.environ["ACCOUNTS_DATABASE_URL"])
    return _store


def reset_store() -> None:
    """Tests switch databases between cases."""
    global _store
    _store = None


def client_ip() -> str:
    # Vercel puts the visitor's address first in X-Forwarded-For.
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr or "unknown"


def visitor_id() -> str:
    if "visitor" not in g:
        g.visitor = request.cookies.get(VISITOR_COOKIE) or secrets.token_urlsafe(16)
    return g.visitor


def current_user() -> dict | None:
    if not enabled() or "user_id" not in session:
        return None
    if "user" not in g:
        g.user = store().user(session["user_id"])
    return g.user


def is_admin() -> bool:
    user = current_user()
    admins = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}
    return bool(user and user["email"] in admins)


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def _check_csrf() -> None:
    if request.form.get("csrf") != session.get("csrf"):
        abort(400)


def _safe_next(target: str | None) -> str:
    # Only our own comparison pages; never another site.
    if target and target.startswith("/") and not target.startswith("//") and not urlsplit(target).netloc:
        return target
    return url_for("accounts.account")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not enabled():
            abort(404)
        if current_user() is None:
            return redirect(url_for("accounts.login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapped


def comparison_gate(company1: str, company2: str):
    """None when the comparison may be shown (and is counted), otherwise a redirect."""
    if not enabled() or is_admin():  # the owner compares without a limit
        return None
    user = current_user()
    user_id = user["id"] if user else None
    pair = f"{company1}|{company2}"
    access = store().check(user_id=user_id, ip=client_ip(), visitor=visitor_id(), pair=pair)
    if not access.allowed:
        return redirect(url_for("accounts.limit", next=request.full_path))
    store().use(access, user_id=user_id, ip=client_ip(), visitor=visitor_id(), pair=pair)
    g.access_kind = access.kind
    return None


@bp.app_context_processor
def account_context() -> dict:
    user = current_user()
    return {
        "accounts_enabled": enabled(),
        "current_user": user,
        "is_admin": is_admin(),
        "csrf_token": csrf_token if enabled() else (lambda: ""),
    }


@bp.after_app_request
def remember_visitor(response):
    if enabled() and "visitor" in g and request.cookies.get(VISITOR_COOKIE) != g.visitor:
        response.set_cookie(VISITOR_COOKIE, g.visitor, max_age=3600 * 24 * 365, httponly=True,
                            samesite="Lax", secure=request.is_secure)
    return response


@bp.route("/health/accounts")
def accounts_health():
    """Called daily by keep-alive.yml; a failure (503) makes GitHub email the owner."""
    if not enabled():
        return {"accounts": "off"}
    try:
        store().ping()
    except Exception:  # noqa: BLE001 - any database error means sign-in is down
        return {"accounts": "error"}, 503
    return {"accounts": "ok"}


@bp.route("/limit")
def limit():
    if not enabled():
        return redirect("/")
    return render_template("limit.html", next=_safe_next(request.args.get("next")), plans=PLANS,
                           free=FREE_COMPARISONS)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if not enabled():
        abort(404)
    from web_app import COMPANIES

    form = request.form
    if request.method == "POST":
        _check_csrf()
        email = form.get("email", "").strip()
        problems = []
        if not all(form.get(name, "").strip() for name in ("first_name", "last_name", "email", "password")):
            problems.append("Заполните все поля.")
        if form.get("main_insurer") not in COMPANIES:
            problems.append("Выберите основную страховую.")
        if "@" not in email or "." not in email.split("@")[-1]:
            problems.append("Проверьте адрес почты.")
        if len(form.get("password", "")) < 6:
            problems.append("Пароль — не короче 6 символов.")
        if not problems and store().email_taken(email):
            problems.append("Эта почта уже зарегистрирована — войдите.")
        if not problems:
            session.clear()
            session["user_id"] = store().create_user(
                email=email, password=form["password"], first_name=form["first_name"],
                last_name=form["last_name"], main_insurer=form["main_insurer"])
            return redirect(_safe_next(request.args.get("next")))
        for problem in problems:
            flash(problem)
    return render_template("register.html", companies=COMPANIES, form=form,
                           next=request.args.get("next", ""))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not enabled():
        abort(404)
    if request.method == "POST":
        _check_csrf()
        user_id = store().check_login(request.form.get("email", ""), request.form.get("password", ""))
        if user_id:
            session.clear()
            session["user_id"] = user_id
            return redirect(_safe_next(request.args.get("next")))
        flash("Неверная почта или пароль.")
    return render_template("login.html", next=request.args.get("next", ""))


RESET_MAX_AGE = 3600  # a reset link works for one hour


def _reset_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(os.environ["SECRET_KEY"], salt="password-reset")


@bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    if not enabled():
        abort(404)
    if request.method == "POST":
        _check_csrf()
        email = request.form.get("email", "").strip()
        user_id = store().user_id_by_email(email) if mailer.enabled() else None
        if user_id:
            token = _reset_serializer().dumps({"u": user_id, "s": store().password_stamp(user_id)})
            link = url_for("accounts.reset", token=token, _external=True)
            try:
                mailer.send(email, "Новый пароль — Страховой аналитик",
                            "Здравствуйте!\n\nЧтобы задать новый пароль, откройте ссылку (она действует 1 час):\n"
                            f"{link}\n\nЕсли вы не просили сменить пароль, просто удалите это письмо.\n")
            except Exception:  # noqa: BLE001 - a mail failure must not show who is registered
                current_app.logger.exception("Password reset e-mail was not sent")
        # The same answer for any address: the page does not reveal who is registered.
        flash("Если эта почта зарегистрирована, мы отправили на неё письмо со ссылкой. "
              "Проверьте и папку «Спам».")
        return redirect(url_for("accounts.forgot"))
    return render_template("forgot.html", mail=mailer.enabled())


@bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    if not enabled():
        abort(404)
    try:
        data = _reset_serializer().loads(token, max_age=RESET_MAX_AGE)
    except (BadSignature, SignatureExpired):
        data = None
    if not data or store().password_stamp(data.get("u")) != data.get("s"):
        flash("Ссылка устарела или уже использована. Запросите новую.")
        return redirect(url_for("accounts.forgot"))
    if request.method == "POST":
        _check_csrf()
        password = request.form.get("password", "")
        if len(password) < 6:
            flash("Пароль — не короче 6 символов.")
        else:
            store().set_password(data["u"], password)
            session.clear()
            session["user_id"] = data["u"]
            flash("Пароль изменён.")
            return redirect("/account")
    return render_template("reset.html")


@bp.route("/logout", methods=["POST"])
def logout():
    _check_csrf()
    session.clear()
    return redirect("/")


@bp.route("/account")
@login_required
def account():
    from datetime import datetime, timezone

    user = current_user()
    until = store().monthly_until(user["id"])
    active_until = until if until and until > datetime.now(timezone.utc) else None
    return render_template(
        "account.html", user=user, plans=PLANS,
        monthly_until=active_until.astimezone().strftime("%d.%m.%Y") if active_until else None,
        oneoff_left=max(store().oneoff_left(user["id"]), 0),
        free_left=max(FREE_COMPARISONS - store().free_used(user_id=user["id"], ip=client_ip(),
                                                           visitor=visitor_id()), 0),
        purchases=store().purchases(user["id"]),
        payments_test=_test_payments(),
    )


def _test_payments() -> bool:
    # Test payments are open to the owner only: partners use the live site (28.10.2026).
    return os.environ.get("PAYMENTS_TEST") == "1" and is_admin()


@bp.route("/buy/<plan>", methods=["POST"])
@login_required
def buy(plan):
    _check_csrf()
    if plan not in PLANS:
        abort(404)
    if not _test_payments():
        flash("Оплата картой скоро заработает. Пока подписку можно получить у владельца сервиса: "
              "напишите ему, и он подключит её в вашем кабинете.")
        return redirect(url_for("accounts.account"))
    purchase_id = store().create_purchase(current_user()["id"], plan, provider="test")
    return redirect(url_for("accounts.test_checkout", purchase_id=purchase_id, next=request.args.get("next")))


@bp.route("/checkout/test/<int:purchase_id>", methods=["GET", "POST"])
@login_required
def test_checkout(purchase_id):
    if not _test_payments():
        abort(404)
    purchase = store().purchase(purchase_id)
    if not purchase or purchase["user_id"] != current_user()["id"]:
        abort(404)
    if request.method == "POST":
        _check_csrf()
        store().mark_paid(purchase_id, provider_id="test")
        flash("Тестовая оплата прошла — подписка подключена.")
        # Back to the comparison the visitor wanted, if there was one.
        return redirect(_safe_next(request.args.get("next")))
    return render_template("test_checkout.html", purchase=purchase, plan=PLANS[purchase["plan"]])


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not enabled() or not is_admin():
            abort(404)
        return view(*args, **kwargs)
    return wrapped


@bp.route("/admin")
@admin_required
def admin():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    rows = []
    for user in store().users():
        until = store().monthly_until(user["id"])
        rows.append(dict(
            user,
            registered=datetime.fromisoformat(user["created_at"]).astimezone().strftime("%d.%m.%Y"),
            monthly_until=until.astimezone().strftime("%d.%m.%Y") if until and until > now else None,
            oneoff_left=max(store().oneoff_left(user["id"]), 0),
            comparisons=store().comparisons_made(user["id"]),
        ))
    return render_template("admin.html", users=rows, plans=PLANS, active_section="admin")


@bp.route("/admin/grant/<int:user_id>/<plan>", methods=["POST"])
@admin_required
def admin_grant(user_id, plan):
    _check_csrf()
    user = store().user(user_id)
    if not user or plan not in PLANS:
        abort(404)
    store().grant(user_id, plan)
    flash(f"{user['first_name']} {user['last_name']}: подключена подписка «{PLANS[plan]['title']}».")
    return redirect(url_for("accounts.admin"))


@bp.route("/admin/password/<int:user_id>", methods=["POST"])
@admin_required
def admin_password(user_id):
    _check_csrf()
    user = store().user(user_id)
    if not user:
        abort(404)
    password = secrets.token_urlsafe(6)
    store().set_password(user_id, password)
    flash(f"Новый пароль для {user['email']}: {password} — передайте его пользователю, "
          "он сможет войти с ним.")
    return redirect(url_for("accounts.admin"))
