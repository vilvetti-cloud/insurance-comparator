"""Registration, sign-in, personal account, purchases and the free-comparison limit.

Switched on when ACCOUNTS_DATABASE_URL and SECRET_KEY are set (on Vercel the
first one is the Supabase connection string). Without them the site works as
before, without limits.

Payments: PAYMENTS_TEST=1 shows a test checkout that marks a purchase paid;
a real payment provider is connected later (the owner has to register first).
ADMIN_EMAILS (comma separated) see the service menu «Контроль данных».
"""
from __future__ import annotations

import os
import secrets
from functools import wraps
from urllib.parse import urlsplit

from flask import (Blueprint, abort, flash, g, redirect, render_template, request, session, url_for)

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
    if not enabled():
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
        payments_test=os.environ.get("PAYMENTS_TEST") == "1",
    )


@bp.route("/buy/<plan>", methods=["POST"])
@login_required
def buy(plan):
    _check_csrf()
    if plan not in PLANS:
        abort(404)
    if os.environ.get("PAYMENTS_TEST") != "1":
        flash("Оплата скоро заработает. Пока подписку можно получить у владельца сервиса.")
        return redirect(url_for("accounts.account"))
    purchase_id = store().create_purchase(current_user()["id"], plan, provider="test")
    return redirect(url_for("accounts.test_checkout", purchase_id=purchase_id, next=request.args.get("next")))


@bp.route("/checkout/test/<int:purchase_id>", methods=["GET", "POST"])
@login_required
def test_checkout(purchase_id):
    if os.environ.get("PAYMENTS_TEST") != "1":
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
