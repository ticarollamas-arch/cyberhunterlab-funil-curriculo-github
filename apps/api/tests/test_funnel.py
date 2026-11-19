import asyncio
import base64
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cyberhunter_api import server
from cyberhunter_api.funnel import STAGES, GitHubSnapshot, run_funnel
from cyberhunter_api.github_client import GitHubClient, GitHubError, validate_username
from cyberhunter_api.resume_parser import ResumeError, extract_text, parse_resume, parse_resume_file
from cyberhunter_api.skills import find_skills

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)


@pytest.fixture
def resume():
    return parse_resume_file("cv.txt", (FIX / "curriculo_ficticio.txt").read_bytes())


@pytest.fixture
def snap():
    return server.snapshot_from_json(json.loads((FIX / "snapshot_ficticio.json").read_text("utf-8")))


# ------------------------------------------------------------ skills / parser
def test_find_skills_symbols_and_ambiguity():
    assert {"C++", "C#", "CI/CD"} <= find_skills("Experiência com C++, C# e CI/CD")
    assert "Go" not in find_skills("Let's go to the market")
    assert "Go" in find_skills("Linguagens: Python, Go, Rust")


def test_parse_resume_fields(resume):
    assert resume.name == "MARINA EXEMPLO SOUZA"
    assert "PYTHON" in resume.headline
    assert resume.location.startswith("Curitiba")
    assert resume.github_username == "marina-exemplo"
    assert {"Python", "FastAPI", "Docker", "AppSec", "SAST", "Kubernetes"} <= set(resume.skills)
    assert resume.certifications == ["Certificação Fictícia de Segurança (Mai/2024)"]
    assert resume.to_dict()["emails"] == ["ma***@example.com"]
    assert not resume.layout_multicolumn


def test_upload_validation():
    with pytest.raises(ResumeError):
        extract_text("cv.exe", b"MZ...")
    with pytest.raises(ResumeError):
        extract_text("cv.pdf", b"not a pdf")
    with pytest.raises(ResumeError):
        extract_text("cv.txt", b"")
    with pytest.raises(ResumeError):
        extract_text("cv.txt", b"a" * (6 * 1024 * 1024))


def test_docx_parsing():
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           '<w:p><w:r><w:t>JOAO TESTE</w:t></w:r></w:p><w:p><w:r><w:t>Python e Docker</w:t></w:r></w:p>'
           '</w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    r = parse_resume_file("cv.docx", buf.getvalue())
    assert r.name == "JOAO TESTE"
    assert {"Python", "Docker"} <= set(r.skills)


def test_multicolumn_detection():
    text = "NOME\nTITULO | X\n" + "\n".join(f"esquerda {i}            direita {i}" for i in range(6))
    assert parse_resume(text).layout_multicolumn


# ------------------------------------------------------------ funil
def test_full_funnel(resume, snap):
    rep = run_funnel(resume, snap, now=NOW)
    st = {s["key"]: s for s in rep["etapas"]}
    assert [s["key"] for s in rep["etapas"]] == [k for k, _ in STAGES]
    assert all(s["status"] == "SUCCESS" for s in rep["etapas"]), [(s["key"], s["summary"]) for s in rep["etapas"]]

    items = {f["item"] for f in st["auditoria_github"]["findings"]}
    assert "Localização vazia" in items and any("vazios" in i for i in items)
    assert st["auditoria_github"]["stats"]["forks"] == 1

    ck = {i["skill"]: i["status"] for i in st["checklist_habilidades"]["items"]}
    assert ck["FastAPI"] == "COMPROVADA"
    assert ck["Kubernetes"] == "SEM_EVIDENCIA"
    assert ck["Go"] == "SO_NO_GITHUB"

    seo = st["seo_titulos"]
    assert any("AWS" in p for p in seo["bio"]["problemas"])
    scanner = next(r for r in seo["repos"] if r["name"] == "My_Scanner")
    assert scanner["nome_sugerido"] == "my-scanner"
    assert "golang" in scanner["topics_sugeridos"]

    names = [p["name"] for p in st["projetos_destaque"]["destaques"]]
    assert names[0] == "api-pedidos-fastapi"
    assert "react" not in names and "Teste" not in names and "marina-exemplo" not in names
    assert "react" in st["projetos_destaque"]["pins"]["trocar"]

    v = st["veredito_perfil"]
    assert v["veredito"] in {"FRACO", "PRECISA MELHORAR"} and 0 <= v["score"] < 75
    assert any("marinna-exemplo" in c for c in v["consistencia_curriculo_github"])
    assert any("marinaexemplo" in c for c in v["consistencia_curriculo_github"])

    rd = st["readme_perfil"]
    assert rd["precisa_mudar"] is True
    assert any("telefone" in m for m in rd["motivos"])
    assert "api-pedidos-fastapi" in rd["proposta"]
    assert "marina.exemplo@example.com" not in rd["proposta"]  # e-mail fora por padrão
    assert "Kubernetes" in rd["proposta"]  # só habilidades do currículo

    ats = st["curriculo_ats"]
    assert "FORMAÇÃO ACADÊMICA" in ats["curriculo_ats"]
    assert ats["score"] >= 80


def test_funnel_without_github_never_claims_success(resume):
    rep = run_funnel(resume, GitHubSnapshot(source="nenhuma", error="offline"), now=NOW)
    st = {s["key"]: s["status"] for s in rep["etapas"]}
    assert st["auditoria_github"] == "BLOCKED"
    assert st["seo_titulos"] == "BLOCKED"
    assert st["veredito_perfil"] == "BLOCKED"
    assert st["checklist_habilidades"] == "NOT_EXECUTED"
    assert st["readme_perfil"] == "NOT_EXECUTED"
    assert st["curriculo_ats"] == "SUCCESS"


def test_readme_never_invents(resume, snap):
    rep = run_funnel(resume, snap, now=NOW)
    proposal = next(s for s in rep["etapas"] if s["key"] == "readme_perfil")["proposta"]
    assert "AWS" not in proposal  # está na bio do GitHub, não no currículo
    assert "Go" not in proposal.split("Stack e competências")[1].split("Projetos")[0]


# ------------------------------------------------------------ GitHub client
class FakeTransport:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, json.loads(body) if body else None))
        for (m, suffix), resp in self.routes.items():
            if m == method and url.endswith(suffix):
                return resp
        return 404, {"message": "Not Found"}


def test_validate_username():
    assert validate_username("https://github.com/octo-cat") == "octo-cat"
    assert validate_username("@octo") == "octo"
    for bad in ["../etc", "a" * 40, "-x", "a/b"]:
        with pytest.raises(ValueError):
            validate_username(bad)


def test_client_reads_and_handles_missing_readme():
    t = FakeTransport({("GET", "/users/octo"): (200, {"login": "octo"}),
                       ("GET", "/users/octo/repos?per_page=100&sort=pushed&page=1"): (200, [{"name": "a"}])})
    c = GitHubClient(token="secret", transport=t)
    snap = server.build_snapshot("octo", None, client=c)
    assert snap.available and snap.repos == [{"name": "a"}] and snap.profile_readme is None
    assert t.calls[0][2]["Authorization"] == "Bearer secret"


def test_build_snapshot_rate_limit_message():
    t = FakeTransport({("GET", "/users/octo"): (403, {"message": "API rate limit exceeded"})})
    snap = server.build_snapshot("octo", None, client=GitHubClient(transport=t))
    assert not snap.available and "token" in snap.error


def test_open_pr_flow():
    t = FakeTransport({
        ("GET", "/repos/octo/octo"): (200, {"default_branch": "main"}),
        ("GET", "/git/ref/heads/main"): (200, {"object": {"sha": "abc"}}),
        ("POST", "/git/refs"): (201, {}),
        ("GET", "/contents/README.md?ref=cyberhunterlab/perfil-readme"): (200, {"sha": "old"}),
        ("PUT", "/contents/README.md"): (200, {}),
        ("POST", "/pulls"): (201, {"html_url": "https://github.com/octo/octo/pull/1", "number": 1}),
    })
    pr = GitHubClient(token="t", transport=t).open_profile_readme_pr("octo", "# Oi")
    assert pr["number"] == 1
    put = next(c for c in t.calls if c[0] == "PUT")
    assert put[3]["sha"] == "old" and base64.b64decode(put[3]["content"]) == b"# Oi"
    with pytest.raises(GitHubError):
        GitHubClient(transport=t).open_profile_readme_pr("octo", "# Oi")


# ------------------------------------------------------------ HTTP (ASGI direto, sem rede)
def asgi(method, path, body=None):
    payload = json.dumps(body).encode() if body is not None else b""
    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(), "query_string": b"",
             "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(payload)).encode())],
             "client": ("127.0.0.1", 1), "server": ("test", 80), "scheme": "http", "http_version": "1.1", "root_path": ""}
    out = {"body": b""}
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
        elif msg["type"] == "http.response.body":
            out["body"] += msg.get("body", b"")

    asyncio.run(server.app(scope, receive, send))
    try:
        return out["status"], json.loads(out["body"])
    except json.JSONDecodeError:
        return out["status"], out["body"]


def test_http_health():
    status, data = asgi("GET", "/api/health")
    assert status == 200 and data["status"] == "ok" and len(data["stages"]) == 7


def test_http_run_with_file_and_snapshot():
    b64 = base64.b64encode((FIX / "curriculo_ficticio.txt").read_bytes()).decode()
    snap = json.loads((FIX / "snapshot_ficticio.json").read_text("utf-8"))
    status, data = asgi("POST", "/api/funnel/run", {"resume": {"filename": "cv.txt", "content_base64": b64}, "snapshot": snap})
    assert status == 200
    assert [s["status"] for s in data["etapas"]].count("SUCCESS") == 7
    assert "raw_text" not in data["curriculo"]


def test_http_run_errors():
    assert asgi("POST", "/api/funnel/run", {})[0] == 400
    assert asgi("POST", "/api/funnel/run", {"resume": {"filename": "x.exe", "content_base64": "TVo="}})[0] == 400
    assert asgi("POST", "/api/funnel/run", {"resume_text": "NOME\nX", "github_username": "../x"})[0] == 400


def test_http_apply_requires_confirmation_and_token(monkeypatch):
    status, data = asgi("POST", "/api/funnel/apply", {"github_username": "octo", "markdown": "# Oi"})
    assert status == 409 and data["status"] == "NOT_EXECUTED"
    status, _ = asgi("POST", "/api/funnel/apply", {"github_username": "octo", "markdown": "# Oi", "confirm": True})
    assert status == 401


def test_static_ui_served():
    status, body = asgi("GET", "/")
    assert status == 200 and b"Funil" in body
