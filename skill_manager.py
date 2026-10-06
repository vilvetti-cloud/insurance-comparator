import os
import requests

OPENAI_SKILLS_URL = "https://api.openai.com/v1/skills"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

SKILL_NAMES = [
    "frontend-design",
    "mcp-builder",
    "pdf",
    "pptx",
    "skill-creator",
    "web-artifacts-builder",
    "webapp-testing",
    "xlsx",
]


def _headers():
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return {"Authorization": f"Bearer {key}"}


def list_remote_skills():
    response = requests.get(
        OPENAI_SKILLS_URL,
        headers=_headers(),
        params={"limit": 100},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("data", [])


def skills_for_response():
    skills = list_remote_skills()
    by_name = {skill.get("name"): skill for skill in skills}

    missing = [name for name in SKILL_NAMES if name not in by_name]
    if missing:
        raise RuntimeError(
            "Required OpenAI Skills are not installed: " + ", ".join(missing)
        )

    return [
        {
            "type": "skill_reference",
            "skill_id": by_name[name]["id"],
            "version": "latest",
        }
        for name in SKILL_NAMES
    ]


def run_agent(prompt):
    refs = skills_for_response()
    key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("OPENAI_MODEL", "gpt-6-astra")

    response = requests.post(
        OPENAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "tools": [
                {
                    "type": "shell",
                    "environment": {
                        "type": "container_auto",
                        "skills": refs,
                    },
                }
            ],
            "input": prompt,
        },
        timeout=180,
    )

    if not response.ok:
        raise RuntimeError(
            f"OpenAI Responses API {response.status_code}: "
            f"{response.text[:1500]}"
        )

    return response.json()


def register_skill_routes(app):
    from flask import request

    @app.get("/skills/status")
    def skills_status():
        try:
            data = list_remote_skills()
            installed = {
                skill.get("name"): skill
                for skill in data
                if skill.get("name") in SKILL_NAMES
            }

            return {
                "ok": True,
                "skills": [
                    {
                        "name": name,
                        "id": installed[name].get("id"),
                        "version": installed[name].get("latest_version"),
                    }
                    for name in SKILL_NAMES
                    if name in installed
                ],
                "missing": [
                    name for name in SKILL_NAMES if name not in installed
                ],
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}, 500

    @app.post("/skills/run")
    def skills_run():
        expected_token = os.environ.get("SKILLS_RUN_TOKEN")
        if not expected_token:
            return {
                "ok": False,
                "error": "SKILLS_RUN_TOKEN is not configured",
            }, 503

        supplied_token = request.headers.get("X-Skills-Token")
        if supplied_token != expected_token:
            return {"ok": False, "error": "unauthorized"}, 401

        body = request.get_json(silent=True) or {}
        prompt = body.get("prompt")

        if not isinstance(prompt, str) or not prompt.strip():
            return {
                "ok": False,
                "error": "JSON body must contain a non-empty 'prompt'",
            }, 400

        try:
            return {"ok": True, "response": run_agent(prompt)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}, 500
