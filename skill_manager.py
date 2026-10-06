import base64
import io
import os
import zipfile
import requests

OPENAI_SKILLS_URL = "https://api.openai.com/v1/skills"
BUNDLE_PATH = os.path.join(os.path.dirname(__file__), "openai-skills-bundle.b64")
SKILL_NAMES = [
    "frontend-design", "mcp-builder", "pdf", "pptx",
    "skill-creator", "web-artifacts-builder", "webapp-testing", "xlsx",
]

def _headers():
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return {"Authorization": f"Bearer {key}"}

def _bundle_bytes():
    with open(BUNDLE_PATH, "r", encoding="ascii") as f:
        return base64.b64decode(f.read())

def list_remote_skills():
    r = requests.get(OPENAI_SKILLS_URL, headers=_headers(), params={"limit": 100}, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])

def install_all():
    existing = {x["name"]: x for x in list_remote_skills()}
    results = []
    with zipfile.ZipFile(io.BytesIO(_bundle_bytes())) as bundle:
        for name in SKILL_NAMES:
            if name in existing:
                results.append({"name": name, "status": "already_installed", "id": existing[name]["id"]})
                continue
            filename = f"{name}.zip"
            payload = bundle.read(filename)
            r = requests.post(
                OPENAI_SKILLS_URL,
                headers=_headers(),
                files={"files": (filename, payload, "application/zip")},
                timeout=120,
            )
            if not r.ok:
                results.append({"name": name, "status": "error", "http_status": r.status_code, "error": r.text[:1000]})
                continue
            data = r.json()
            results.append({"name": name, "status": "installed", "id": data.get("id"), "version": data.get("latest_version")})
            existing[name] = data
    return results

def skills_for_response():
    skills = list_remote_skills()
    by_name = {x["name"]: x for x in skills}
    return [
        {"type": "skill_reference", "skill_id": by_name[name]["id"], "version": "latest"}
        for name in SKILL_NAMES if name in by_name
    ]

def run_agent(prompt):
    refs = skills_for_response()
    if not refs:
        raise RuntimeError("No installed skills found")
    key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("OPENAI_MODEL", "gpt-6-astra")
    r = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "tools": [{"type": "shell", "environment": {"type": "container_auto", "skills": refs}}],
            "input": prompt,
        },
        timeout=180,
    )
    if not r.ok:
        raise RuntimeError(f"OpenAI Responses API {r.status_code}: {r.text[:1500]}")
    return r.json()

def register_skill_routes(app):
    from flask import request

    @app.get("/skills/status")
    def skills_status():
        try:
            data = list_remote_skills()
            return {"ok": True, "skills": [
                {"name": x.get("name"), "id": x.get("id"), "version": x.get("latest_version")}
                for x in data
            ]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}, 500

    @app.get("/skills/install")
    def skills_install():
        expected = os.environ.get("SKILLS_INSTALL_TOKEN")
        if expected and request.args.get("token") != expected:
            return {"ok": False, "error": "invalid install token"}, 403
        try:
            return {"ok": True, "results": install_all()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}, 500

    @app.post("/skills/run")
    def skills_run():
        body = request.get_json(silent=True) or {}
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return {"ok": False, "error": "JSON body must contain a non-empty 'prompt'"}, 400
        try:
            return {"ok": True, "response": run_agent(prompt)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}, 500
