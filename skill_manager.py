import os
import requests

from flask import request

from local_skills import LOCAL_SKILLS, SKILL_NAMES, SKILLS_VERSION

GEMINI_OPENAI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GROQ_OPENAI_URL = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"

PROVIDER_ORDER = ("gemini", "groq")


def _provider_config():
    preferred = os.environ.get("FREE_AI_PROVIDER", "").strip().lower()

    configs = {
        "gemini": {
            "key": os.environ.get("GEMINI_API_KEY", ""),
            "url": GEMINI_OPENAI_URL,
            "model": os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        },
        "groq": {
            "key": os.environ.get("GROQ_API_KEY", ""),
            "url": GROQ_OPENAI_URL,
            "model": os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL),
        },
    }

    order = [preferred] if preferred in configs else []
    order.extend(name for name in PROVIDER_ORDER if name not in order)

    for name in order:
        cfg = configs[name]
        if cfg["key"]:
            return name, cfg

    raise RuntimeError(
        "No free AI provider is configured. Set GEMINI_API_KEY or GROQ_API_KEY."
    )


def _skill_context(skill_name):
    if skill_name in (None, "", "general"):
        return (
            "Work as a practical software/content agent. "
            "Follow the user's exact request, state assumptions, and produce a usable result."
        )

    if skill_name not in LOCAL_SKILLS:
        raise ValueError(
            "Unknown skill. Choose one of: " + ", ".join(SKILL_NAMES)
        )

    skill = LOCAL_SKILLS[skill_name]
    return (
        f"You are operating with the local '{skill_name}' skill. "
        "Treat these instructions as task-specific guidance.\n\n"
        + skill["instructions"]
    )


def run_agent(prompt, skill_name=None):
    provider, cfg = _provider_config()
    system = _skill_context(skill_name)

    response = requests.post(
        cfg["url"],
        headers={
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type": "application/json",
        },
        json={
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        timeout=120,
    )

    if not response.ok:
        raise RuntimeError(
            f"{provider.upper()} API {response.status_code}: "
            f"{response.text[:1500]}"
        )

    data = response.json()
    message = ((data.get("choices") or [{}])[0].get("message") or {})
    content = message.get("content")

    if not content:
        raise RuntimeError("AI provider returned no text content")

    return {
        "provider": provider,
        "model": cfg["model"],
        "skill": skill_name or "general",
        "text": content,
        "usage": data.get("usage"),
    }


def register_skill_routes(app):
    @app.get("/skills/status")
    def skills_status():
        try:
            provider, cfg = _provider_config()
            return {
                "ok": True,
                "mode": "free-provider",
                "provider": provider,
                "model": cfg["model"],
                "openai_api_required": False,
                "skills_version": SKILLS_VERSION,
                "skills": [
                    {
                        "name": name,
                        "version": SKILLS_VERSION,
                        "source": "bundled-local-instructions",
                    }
                    for name in SKILL_NAMES
                ],
                "missing": [],
            }
        except Exception as exc:
            return {
                "ok": False,
                "mode": "free-provider",
                "openai_api_required": False,
                "error": str(exc),
            }, 503

    @app.post("/skills/run")
    def skills_run():
        expected_token = os.environ.get("SKILLS_RUN_TOKEN")
        if not expected_token:
            return {
                "ok": False,
                "error": "SKILLS_RUN_TOKEN is not configured",
            }, 503

        if request.headers.get("X-Skills-Token") != expected_token:
            return {"ok": False, "error": "unauthorized"}, 401

        body = request.get_json(silent=True) or {}
        prompt = body.get("prompt")
        skill_name = body.get("skill", "general")

        if not isinstance(prompt, str) or not prompt.strip():
            return {
                "ok": False,
                "error": "JSON body must contain a non-empty 'prompt'",
            }, 400

        try:
            result = run_agent(prompt, skill_name)
            return {"ok": True, "response": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}, 502
