"""Cliente mínimo da API REST do GitHub (somente biblioteca padrão).

O transporte é injetável para testes. O token nunca é registrado em logs
nem devolvido em respostas.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable

API = "https://api.github.com"
USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")

# transport(method, url, headers, body) -> (status, json|None)
Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]


class GitHubError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub {status}: {message}")
        self.status = status


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, Any]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (URL fixa da API)
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = None
        return exc.code, payload


def validate_username(username: str) -> str:
    username = (username or "").strip().lstrip("@")
    m = re.match(r"^https?://(?:www\.)?github\.com/([^/?#]+)", username)
    if m:
        username = m.group(1)
    if not USERNAME_RE.match(username):
        raise ValueError("Nome de usuário GitHub inválido.")
    return username


class GitHubClient:
    def __init__(self, token: str | None = None, transport: Transport | None = None):
        self._token = token or None
        self._transport = transport or urllib_transport

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    def _req(self, method: str, path: str, body: dict | None = None, ok=(200,)) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "CyberHunterLab-Funnel",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        data = json.dumps(body).encode() if body is not None else None
        if data:
            headers["Content-Type"] = "application/json"
        status, payload = self._transport(method, API + path, headers, data)
        if status not in ok:
            msg = (payload or {}).get("message", "erro") if isinstance(payload, dict) else "erro"
            raise GitHubError(status, msg)
        return payload

    # ------------------------------------------------------------ leitura
    def get_user(self, username: str) -> dict:
        return self._req("GET", f"/users/{validate_username(username)}")

    def list_repos(self, username: str, max_pages: int = 3) -> list[dict]:
        username = validate_username(username)
        repos: list[dict] = []
        for page in range(1, max_pages + 1):
            batch = self._req("GET", f"/users/{username}/repos?per_page=100&sort=pushed&page={page}")
            repos.extend(batch or [])
            if not batch or len(batch) < 100:
                break
        return repos

    def get_readme(self, owner: str, repo: str) -> str | None:
        try:
            payload = self._req("GET", f"/repos/{validate_username(owner)}/{_safe_repo(repo)}/readme")
        except GitHubError as exc:
            if exc.status == 404:
                return None
            raise
        content = payload.get("content", "") if isinstance(payload, dict) else ""
        return base64.b64decode(content).decode("utf-8", "replace") if content else ""

    # ------------------------------------------------------------ escrita (exige confirmação)
    def open_profile_readme_pr(self, username: str, markdown: str, branch: str = "cyberhunterlab/perfil-readme") -> dict:
        """Cria branch, grava README.md e abre PR no repositório de perfil."""
        if not self.authenticated:
            raise GitHubError(401, "Token necessário para abrir pull request.")
        owner = validate_username(username)
        repo = owner
        info = self._req("GET", f"/repos/{owner}/{repo}")
        base = info["default_branch"]
        ref = self._req("GET", f"/repos/{owner}/{repo}/git/ref/heads/{base}")
        self._req("POST", f"/repos/{owner}/{repo}/git/refs",
                  {"ref": f"refs/heads/{branch}", "sha": ref["object"]["sha"]}, ok=(201,))
        sha = None
        try:
            current = self._req("GET", f"/repos/{owner}/{repo}/contents/README.md?ref={branch}")
            sha = current.get("sha")
        except GitHubError as exc:
            if exc.status != 404:
                raise
        body = {"message": "docs: README de perfil profissional (CyberHunterLab)",
                "content": base64.b64encode(markdown.encode()).decode(), "branch": branch}
        if sha:
            body["sha"] = sha
        self._req("PUT", f"/repos/{owner}/{repo}/contents/README.md", body, ok=(200, 201))
        pr = self._req("POST", f"/repos/{owner}/{repo}/pulls", {
            "title": "docs: README de perfil profissional",
            "head": branch, "base": base,
            "body": "Proposta gerada pelo funil Currículo → GitHub do CyberHunterLab. Revise antes de mesclar.",
        }, ok=(201,))
        return {"url": pr.get("html_url"), "number": pr.get("number"), "branch": branch}


def _safe_repo(name: str) -> str:
    if not re.match(r"^[A-Za-z0-9._-]{1,100}$", name or "") or name in {".", ".."}:
        raise ValueError("Nome de repositório inválido.")
    return name
