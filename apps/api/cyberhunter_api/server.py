"""API HTTP do funil (Starlette — compatível com migração direta para FastAPI)."""
from __future__ import annotations

import base64
import binascii
import os
import time
import urllib.error
from collections import defaultdict, deque
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import __version__
from .funnel import STAGES, GitHubSnapshot, run_funnel
from .github_client import GitHubClient, GitHubError, validate_username
from .resume_parser import MAX_UPLOAD_BYTES, ResumeError, parse_resume, parse_resume_file

STATIC = Path(__file__).resolve().parent.parent / "static"
MAX_BODY = int(MAX_UPLOAD_BYTES * 1.5)
RATE = int(os.environ.get("FUNNEL_RATE_PER_MIN", "20"))
_hits: dict[str, deque] = defaultdict(deque)


def _client_factory(token: str | None) -> GitHubClient:  # substituível nos testes
    return GitHubClient(token=token)


def build_snapshot(username: str | None, token: str | None, client: GitHubClient | None = None) -> GitHubSnapshot:
    if not username:
        return GitHubSnapshot(source="nenhuma", error="Informe o usuário do GitHub (ou inclua o link no currículo).")
    client = client or _client_factory(token)
    try:
        user = client.get_user(username)
        repos = client.list_repos(username)
        readme = client.get_readme(username, username)
        return GitHubSnapshot(user=user, repos=repos, profile_readme=readme, source="api")
    except GitHubError as exc:
        hint = " (limite de requisições: informe um token de leitura)" if exc.status in (403, 429) else ""
        return GitHubSnapshot(source="api", error=f"{exc}{hint}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return GitHubSnapshot(source="api", error=f"GitHub inacessível a partir do servidor: {exc}")


def snapshot_from_json(data: dict) -> GitHubSnapshot:
    if not isinstance(data, dict) or not isinstance(data.get("user"), dict):
        raise ValueError("Snapshot inválido: esperado objeto com 'user' e 'repos'.")
    repos = data.get("repos") or []
    if not isinstance(repos, list):
        raise ValueError("Snapshot inválido: 'repos' deve ser lista.")
    return GitHubSnapshot(user=data["user"], repos=repos, profile_readme=data.get("profile_readme"),
                          pinned=data.get("pinned"), source=str(data.get("source") or "snapshot"))


def _err(status: int, msg: str) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=status)


async def _json(request: Request) -> dict:
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        raise ValueError("Requisição grande demais.")
    body = await request.body()
    if len(body) > MAX_BODY:
        raise ValueError("Requisição grande demais.")
    import json
    data = json.loads(body or b"{}")
    if not isinstance(data, dict):
        raise ValueError("JSON deve ser um objeto.")
    return data


def _rate_limited(request: Request) -> bool:
    ip = request.client.host if request.client else "?"
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE:
        return True
    q.append(now)
    return False


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "version": __version__, "stages": [k for k, _ in STAGES]})


async def funnel_run(request: Request) -> JSONResponse:
    if _rate_limited(request):
        return _err(429, "Muitas requisições. Aguarde um minuto.")
    try:
        data = await _json(request)
        res = data.get("resume") or {}
        if isinstance(res, dict) and res.get("content_base64"):
            raw = base64.b64decode(res["content_base64"], validate=True)
            resume = parse_resume_file(str(res.get("filename") or ""), raw)
        elif isinstance(data.get("resume_text"), str) and data["resume_text"].strip():
            if len(data["resume_text"]) > MAX_UPLOAD_BYTES:
                raise ResumeError("Texto do currículo grande demais.")
            resume = parse_resume(data["resume_text"])
        else:
            return _err(400, "Envie o currículo (arquivo ou texto).")

        username = data.get("github_username") or resume.github_username
        if username:
            username = validate_username(str(username))
        if data.get("snapshot"):
            snap = snapshot_from_json(data["snapshot"])
        else:
            token = (data.get("github_token") or "").strip() or None
            snap = build_snapshot(username, token)
        report = run_funnel(resume, snap, include_email=bool(data.get("include_email")))
        return JSONResponse(report)
    except (ResumeError, ValueError, binascii.Error) as exc:
        return _err(400, str(exc))


async def funnel_apply(request: Request) -> JSONResponse:
    if _rate_limited(request):
        return _err(429, "Muitas requisições. Aguarde um minuto.")
    try:
        data = await _json(request)
        username = validate_username(str(data.get("github_username") or ""))
        markdown = str(data.get("markdown") or "")
        if not markdown.strip() or len(markdown) > 100_000:
            return _err(400, "README vazio ou grande demais.")
        if data.get("confirm") is not True:
            return JSONResponse({"status": "NOT_EXECUTED", "preview": markdown,
                                 "message": "Confirmação obrigatória: reenvie com confirm=true para abrir o pull request."},
                                status_code=409)
        token = (data.get("github_token") or "").strip()
        if not token:
            return _err(401, "Token do GitHub com permissão de escrita no repositório de perfil é obrigatório.")
        pr = _client_factory(token).open_profile_readme_pr(username, markdown)
        return JSONResponse({"status": "SUCCESS", "pull_request": pr})
    except GitHubError as exc:
        return _err(502, str(exc))
    except ValueError as exc:
        return _err(400, str(exc))


async def index(_: Request) -> FileResponse:
    return FileResponse(STATIC / "funnel.html")


def create_app() -> Starlette:
    origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if o.strip()]
    return Starlette(
        routes=[
            Route("/", index),
            Route("/api/health", health),
            Route("/api/funnel/run", funnel_run, methods=["POST"]),
            Route("/api/funnel/apply", funnel_apply, methods=["POST"]),
            Mount("/static", StaticFiles(directory=STATIC), name="static"),
        ],
        middleware=[Middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
                               allow_headers=["Content-Type"])],
    )


app = create_app()
