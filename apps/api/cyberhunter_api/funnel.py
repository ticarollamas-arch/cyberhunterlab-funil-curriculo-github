"""Funil Currículo ATS → GitHub.

Etapas (em ordem):
 1. auditoria_github      — perfil e higiene dos repositórios
 2. checklist_habilidades — currículo x evidências no GitHub
 3. seo_titulos           — bio, descrições, topics e nomes
 4. projetos_destaque     — quais projetos fixar (pin) e por quê
 5. veredito_perfil       — o perfil principal está bom ou não
 6. readme_perfil         — precisa trocar o README.md do perfil? (proposta + motivos)
 7. curriculo_ats         — checagem ATS e versão em coluna única

Cada etapa tem status PLANNED | RUNNING | SUCCESS | FAILED | BLOCKED | NOT_EXECUTED
e nunca declara SUCCESS sem os dados que a sustentam.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .readme_builder import build_ats_resume, build_profile_readme
from .resume_parser import ParsedResume
from .skills import GITHUB_LANGUAGE_MAP, SKILLS, find_skills, normalize, skill_by_name

STAGES = [
    ("auditoria_github", "Auditoria completa do GitHub"),
    ("checklist_habilidades", "Checklist de habilidades e capacidades"),
    ("seo_titulos", "SEO de títulos, descrições e topics"),
    ("projetos_destaque", "Projetos importantes em destaque"),
    ("veredito_perfil", "O perfil principal está bom?"),
    ("readme_perfil", "README.md do perfil principal"),
    ("curriculo_ats", "Currículo ATS"),
]

GENERIC_NAMES = {"test", "teste", "testes", "projeto", "project", "demo", "app", "novo", "new", "untitled",
                 "my-app", "hello-world", "exemplo", "example", "temp", "tmp", "repo"}
PHONE_RE = re.compile(r"(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]?\d{4}")


@dataclass
class GitHubSnapshot:
    """Dados públicos do GitHub usados pelo funil. Pode vir da API ou de um JSON exportado."""
    user: dict[str, Any] | None = None
    repos: list[dict[str, Any]] = field(default_factory=list)
    profile_readme: str | None = None
    pinned: list[str] | None = None  # REST não expõe pins; preencher se conhecido
    source: str = "api"
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.user is not None


def _stage(key: str, status: str, summary: str, **data: Any) -> dict:
    title = dict(STAGES)[key]
    return {"key": key, "title": title, "status": status, "summary": summary, **data}


def _finding(severity: str, item: str, fix: str) -> dict:
    return {"severity": severity, "item": item, "fix": fix}


def _days_since(iso: str | None, now: datetime) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (now - dt).days


def repo_skills(repo: dict) -> list[str]:
    text = " ".join([repo.get("name", ""), repo.get("description") or "", " ".join(repo.get("topics") or [])])
    found = find_skills(text, prose=False)
    lang = GITHUB_LANGUAGE_MAP.get(repo.get("language") or "")
    if lang:
        found.add(lang)
    return sorted(found)


def _own_repos(snap: GitHubSnapshot) -> list[dict]:
    login = (snap.user or {}).get("login", "").lower()
    return [r for r in snap.repos if not r.get("fork") and not r.get("archived")
            and r.get("name", "").lower() != login]


# ------------------------------------------------------------------ etapa 1
def audit_github(snap: GitHubSnapshot, now: datetime) -> dict:
    if not snap.available:
        return _stage("auditoria_github", "BLOCKED", snap.error or "Dados do GitHub indisponíveis.")
    u = snap.user
    f: list[dict] = []
    checks = {
        "name": ("alta", "Nome de exibição vazio", "Defina o nome profissional completo em Settings → Profile."),
        "bio": ("alta", "Bio vazia", "Escreva uma bio de até 160 caracteres com cargo + especialidades."),
        "location": ("baixa", "Localização vazia", "Informe cidade/estado — recrutadores filtram por região."),
        "blog": ("media", "Sem site/portfólio", "Adicione portfólio, LinkedIn ou página pessoal."),
    }
    for key, (sev, item, fix) in checks.items():
        if not (u.get(key) or "").strip():
            f.append(_finding(sev, item, fix))
    if u.get("name") and u.get("login") and re.sub(r"\W", "", u["name"].lower()) == re.sub(r"\W", "", u["login"].lower()):
        f.append(_finding("media", f"Nome de exibição igual ao usuário ({u['name']})", "Use o nome real com espaços e acentos."))
    if u.get("name") and " " not in u["name"].strip():
        f.append(_finding("media", f"Nome de exibição sem espaços: '{u['name']}'", "Use o nome como no currículo, ex.: 'Nome Sobrenome'."))
    if not u.get("hireable"):
        f.append(_finding("baixa", "Disponibilidade para contratação desativada", "Ative 'Available for hire' se estiver buscando vagas."))

    own = _own_repos(snap)
    forks = [r for r in snap.repos if r.get("fork")]
    no_desc = [r["name"] for r in own if not (r.get("description") or "").strip()]
    no_topics = [r["name"] for r in own if not r.get("topics")]
    no_license = [r["name"] for r in own if not r.get("license")]
    empty = [r["name"] for r in own if (r.get("size") or 0) == 0]
    stale = [r["name"] for r in own if (_days_since(r.get("pushed_at"), now) or 0) > 365]
    generic = [r["name"] for r in own if normalize(r["name"]).replace(" ", "-") in GENERIC_NAMES]

    if not snap.profile_readme:
        f.append(_finding("alta", "Sem README de perfil (repositório usuário/usuário)", "Criar o repositório de perfil com README — ver etapa 6."))
    if own and len(no_desc) / len(own) > 0.2:
        f.append(_finding("alta", f"{len(no_desc)} de {len(own)} repositórios sem descrição", "Adicionar descrições — sugestões na etapa 3."))
    if own and len(no_topics) / len(own) > 0.3:
        f.append(_finding("media", f"{len(no_topics)} repositórios sem topics", "Adicionar 4–8 topics por projeto — sugestões na etapa 3."))
    if empty:
        f.append(_finding("media", f"{len(empty)} repositórios vazios", "Popular, arquivar ou tornar privado (você decide a visibilidade)."))
    if generic:
        f.append(_finding("media", f"Nomes genéricos: {', '.join(generic[:5])}", "Renomear para nomes descritivos (o GitHub redireciona o link antigo)."))
    if len(snap.repos) > 30 and len(forks) > len(snap.repos) * 0.4:
        f.append(_finding("baixa", f"{len(forks)} forks dominam a lista", "Arquivar forks sem contribuição própria para destacar seu trabalho."))
    if own and len(no_license) / len(own) > 0.5:
        f.append(_finding("baixa", f"{len(no_license)} projetos sem licença", "Escolher uma licença onde for apropriado (nunca substituir uma existente sem autorização)."))

    stats = {"total": len(snap.repos), "proprios_ativos": len(own), "forks": len(forks),
             "arquivados": sum(1 for r in snap.repos if r.get("archived")),
             "sem_descricao": len(no_desc), "sem_topics": len(no_topics), "sem_licenca": len(no_license),
             "vazios": len(empty), "sem_push_12_meses": len(stale),
             "linguagens": _language_counts(own)}
    return _stage("auditoria_github", "SUCCESS", f"{len(f)} pontos de melhoria encontrados.", findings=f, stats=stats,
                  lists={"sem_descricao": no_desc[:50], "sem_topics": no_topics[:50], "vazios": empty, "genericos": generic})


def _language_counts(repos: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in repos:
        if r.get("language"):
            out[r["language"]] = out.get(r["language"], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# ------------------------------------------------------------------ etapa 2
def skills_checklist(resume: ParsedResume, snap: GitHubSnapshot) -> dict:
    evidence: dict[str, list[str]] = {}
    for r in _own_repos(snap):
        for s in repo_skills(r):
            evidence.setdefault(s, []).append(r["name"])
    if snap.profile_readme:
        for s in find_skills(snap.profile_readme, prose=True):
            evidence.setdefault(s, []).append("README do perfil")

    resume_set = set(resume.skills)
    items = []
    for sk in SKILLS:
        in_cv = sk.name in resume_set
        ev = evidence.get(sk.name, [])
        if not in_cv and not ev:
            continue
        repos_ev = [e for e in ev if e != "README do perfil"]
        if not snap.available:
            status, action = "NAO_VERIFICADA", "Conecte o GitHub para verificar evidências."
        elif in_cv and repos_ev:
            status, action = "COMPROVADA", f"Fixe ou cite {repos_ev[0]} como prova."
        elif in_cv:
            status, action = "SEM_EVIDENCIA", f"Publique um projeto ou adicione o topic '{sk.topic}' a um repositório que use {sk.name}."
        else:
            status, action = "SO_NO_GITHUB", f"Você usa {sk.name} no GitHub — considere incluir no currículo se dominar."
        items.append({"skill": sk.name, "category": sk.category, "no_curriculo": in_cv,
                      "evidencias": repos_ev[:5], "status": status, "acao": action})

    if not resume.skills:
        return _stage("checklist_habilidades", "FAILED", "Nenhuma habilidade reconhecida no currículo.", items=items)
    counts = {k: sum(1 for i in items if i["status"] == k) for k in ("COMPROVADA", "SEM_EVIDENCIA", "SO_NO_GITHUB", "NAO_VERIFICADA")}
    status = "SUCCESS" if snap.available else "NOT_EXECUTED"
    summary = (f"{counts['COMPROVADA']} comprovadas, {counts['SEM_EVIDENCIA']} sem evidência pública, "
               f"{counts['SO_NO_GITHUB']} só no GitHub." if snap.available
               else f"{len(resume.skills)} habilidades no currículo; evidências não verificadas sem GitHub.")
    return _stage("checklist_habilidades", status, summary, items=items, counts=counts)


# ------------------------------------------------------------------ etapa 3
def _humanize(name: str) -> str:
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("-", " ").replace("_", " ").split()
    return " ".join(w if w.isupper() and len(w) > 1 else w.capitalize() for w in words)


def suggest_topics(repo: dict, limit: int = 8) -> list[str]:
    current = list(repo.get("topics") or [])
    for s in repo_skills(repo):
        sk = skill_by_name(s)
        if sk and sk.topic not in current:
            current.append(sk.topic)
    return current[:limit]


def seo_review(resume: ParsedResume, snap: GitHubSnapshot) -> dict:
    if not snap.available:
        return _stage("seo_titulos", "BLOCKED", snap.error or "Dados do GitHub indisponíveis.")
    u = snap.user
    bio = (u.get("bio") or "").strip()
    bio_issues = []
    if not bio:
        bio_issues.append("Bio vazia.")
    elif len(bio) < 40:
        bio_issues.append("Bio curta demais para busca (menos de 40 caracteres).")
    head_skills = find_skills(resume.headline)
    bio_skills = find_skills(bio)
    if bio and resume.headline and not (head_skills & bio_skills):
        bio_issues.append("A bio não repete nenhuma palavra-chave do título do currículo.")
    extra = sorted(bio_skills - set(resume.skills))
    if extra:
        bio_issues.append(f"A bio cita {', '.join(extra)}, que não aparece(m) no currículo — alinhe as duas fontes.")
    bio_suggestion = _title_case_headline(resume.headline)[:160] if resume.headline else ""

    repos = []
    for r in sorted(_own_repos(snap), key=lambda r: -_repo_score(r, set(resume.skills))["total"])[:20]:
        issues = []
        desc = (r.get("description") or "").strip()
        if not desc:
            issues.append("Sem descrição.")
        elif len(desc) < 50:
            issues.append("Descrição curta (ideal 50–160 caracteres com palavras-chave).")
        elif len(desc) > 200:
            issues.append("Descrição longa — o GitHub corta na listagem.")
        if not r.get("topics"):
            issues.append("Sem topics.")
        if re.search(r"[A-Z_ ]", r["name"]) and not re.match(r"^[A-Z][a-z]+$", r["name"]):
            issues.append("Nome fora do padrão kebab-case (ex.: meu-projeto).")
        if normalize(r["name"]).replace(" ", "-") in GENERIC_NAMES:
            issues.append("Nome genérico — não indica o que o projeto faz.")
        if not r.get("homepage") and r.get("has_pages"):
            issues.append("GitHub Pages ativo sem homepage configurada.")
        if not issues:
            continue
        skills = repo_skills(r)
        draft = None
        if not desc or len(desc) < 50:
            draft = f"{_humanize(r['name'])} — [o que resolve] com {', '.join(skills[:3]) or r.get('language') or '[stack]'}."
        repos.append({"name": r["name"], "html_url": r.get("html_url"), "description": desc or None,
                      "issues": issues, "descricao_rascunho": draft,
                      "nome_sugerido": _kebab(r["name"]) if "kebab-case" in " ".join(issues) else None,
                      "topics_sugeridos": suggest_topics(r)})
    return _stage("seo_titulos", "SUCCESS", f"Bio: {len(bio_issues)} ajuste(s); {len(repos)} repositório(s) com melhorias de SEO.",
                  bio={"atual": bio or None, "problemas": bio_issues, "sugestao": bio_suggestion}, repos=repos,
                  nota="Rascunhos marcados com [ ] precisam ser completados por você — o sistema não inventa o que o projeto faz.")


def _title_case_headline(h: str) -> str:
    small = {"de", "da", "do", "e", "&", "|"}
    return " ".join(w.lower() if w.lower() in small else (w.capitalize() if w.isupper() and len(w) > 3 else w) for w in h.split())


def _kebab(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ------------------------------------------------------------------ etapa 4
def _repo_score(r: dict, cv_skills: set[str], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    skills = set(repo_skills(r))
    relevance = len(skills & cv_skills)
    days = _days_since(r.get("pushed_at"), now)
    recency = 3 if days is not None and days < 90 else 2 if days is not None and days < 365 else 0
    parts = {
        "estrelas": min((r.get("stargazers_count") or 0) * 2, 10),
        "relevancia_curriculo": min(relevance * 3, 12),
        "recencia": recency,
        "descricao": 2 if (r.get("description") or "").strip() else 0,
        "topics": 1 if r.get("topics") else 0,
        "homepage": 1 if r.get("homepage") else 0,
        "tamanho": 1 if (r.get("size") or 0) > 50 else 0,
    }
    parts["total"] = sum(parts.values())
    return parts


def featured_projects(resume: ParsedResume, snap: GitHubSnapshot, now: datetime, limit: int = 6) -> dict:
    if not snap.available:
        return _stage("projetos_destaque", "BLOCKED", snap.error or "Dados do GitHub indisponíveis.")
    cv = set(resume.skills)
    ranked = []
    for r in _own_repos(snap):
        if (r.get("size") or 0) == 0:
            continue
        sc = _repo_score(r, cv, now)
        ranked.append({"name": r["name"], "html_url": r.get("html_url"), "description": r.get("description"),
                       "language": r.get("language"), "skills": repo_skills(r), "score": sc})
    ranked.sort(key=lambda x: (-x["score"]["total"], x["name"].lower()))
    picks = ranked[:limit]
    for p in picks:
        reasons = []
        if p["score"]["relevancia_curriculo"]:
            reasons.append(f"comprova {', '.join(sorted(set(p['skills']) & cv)[:3])} do currículo")
        if p["score"]["estrelas"]:
            reasons.append("tem estrelas")
        if p["score"]["recencia"] == 3:
            reasons.append("atualizado nos últimos 90 dias")
        if not p["description"]:
            reasons.append("ATENÇÃO: adicionar descrição antes de fixar")
        p["motivo"] = "; ".join(reasons) or "melhor pontuação disponível"
    pinned_review = None
    if snap.pinned is not None:
        pick_names = {p["name"] for p in picks}
        pinned_review = {"fixados_hoje": snap.pinned,
                         "manter": [n for n in snap.pinned if n in pick_names],
                         "trocar": [n for n in snap.pinned if n not in pick_names and n.lower() != (snap.user or {}).get("login", "").lower()],
                         "adicionar": [n for n in pick_names if n not in snap.pinned]}
    covered = set().union(*[set(p["skills"]) for p in picks]) if picks else set()
    gaps = sorted(cv - covered)
    return _stage("projetos_destaque", "SUCCESS" if picks else "FAILED",
                  f"{len(picks)} projetos recomendados para fixar." if picks else "Nenhum repositório próprio com conteúdo.",
                  destaques=picks, pins=pinned_review,
                  habilidades_sem_projeto_fixado=gaps,
                  como_fixar="No seu perfil: Customize your pins → marque os projetos → Save pins.")


# ------------------------------------------------------------------ etapa 5
def profile_verdict(audit: dict, checklist: dict, seo: dict, featured: dict, resume: ParsedResume, snap: GitHubSnapshot) -> dict:
    if not snap.available:
        return _stage("veredito_perfil", "BLOCKED", "Sem dados do GitHub não é possível avaliar o perfil.")
    u = snap.user
    st = audit["stats"]
    own = max(st["proprios_ativos"], 1)
    counts = checklist.get("counts", {})
    cv_total = max(counts.get("COMPROVADA", 0) + counts.get("SEM_EVIDENCIA", 0), 1)
    checks = [
        ("Nome, bio, localização e site preenchidos", 15, sum(bool((u.get(k) or "").strip()) for k in ("name", "bio", "location", "blog")) / 4),
        ("README de perfil existe", 15, 1.0 if snap.profile_readme else 0.0),
        ("Repositórios com descrição", 15, 1 - st["sem_descricao"] / own),
        ("Repositórios com topics", 10, 1 - st["sem_topics"] / own),
        ("Habilidades do currículo comprovadas no GitHub", 20, counts.get("COMPROVADA", 0) / cv_total),
        ("Projetos fortes para fixar (6)", 10, min(len(featured.get("destaques", [])) / 6, 1.0)),
        ("Bio alinhada ao currículo", 10, 0.0 if seo["bio"]["problemas"] else 1.0),
        ("Sem repositórios vazios ou genéricos", 5, 0.0 if (st["vazios"] or audit["lists"]["genericos"]) else 1.0),
    ]
    score = round(sum(w * v for _, w, v in checks))
    verdict = "BOM" if score >= 75 else "PRECISA MELHORAR" if score >= 50 else "FRACO"
    consistency = _consistency(resume, snap)
    must = [f["item"] for f in audit["findings"] if f["severity"] == "alta"] + consistency
    return _stage("veredito_perfil", "SUCCESS", f"Perfil {verdict} — {score}/100.", score=score, veredito=verdict,
                  criterios=[{"criterio": n, "peso": w, "atingido": round(v, 2), "pontos": round(w * v, 1)} for n, w, v in checks],
                  consistencia_curriculo_github=consistency, corrigir_primeiro=must)


def _consistency(resume: ParsedResume, snap: GitHubSnapshot) -> list[str]:
    out = []
    login = (snap.user or {}).get("login", "")
    if resume.github_username and login and resume.github_username.lower() != login.lower():
        out.append(f"O currículo aponta para github.com/{resume.github_username}, mas o perfil analisado é {login}.")
    if not resume.github_username:
        out.append("O currículo não tem link para o GitHub — adicione github.com/" + (login or "usuario") + ".")
    name = (snap.user or {}).get("name") or ""
    if resume.name and name and normalize(resume.name).replace(" ", "") not in normalize(name).replace(" ", "") \
            and normalize(name).replace(" ", "") != normalize(resume.name).replace(" ", ""):
        out.append(f"Nome no GitHub ('{name}') diferente do currículo ('{resume.name}').")
    readme = snap.profile_readme or ""
    for bad in set(re.findall(r"github\.com/([A-Za-z0-9-]+)", readme)):
        if login and bad.lower() != login.lower() and _similar(bad.lower(), login.lower()):
            out.append(f"README do perfil tem link para github.com/{bad} (provável erro de digitação de {login}).")
    return out


def _similar(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 2:
        return False
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio() > 0.85


# ------------------------------------------------------------------ etapa 6
def profile_readme_stage(resume: ParsedResume, snap: GitHubSnapshot, featured: dict, include_email: bool) -> dict:
    username = (snap.user or {}).get("login") or resume.github_username
    picks = featured.get("destaques", []) if featured.get("status") == "SUCCESS" else []
    proposal = build_profile_readme(resume, picks, username, include_email=include_email)
    current = snap.profile_readme
    reasons: list[str] = []
    if not snap.available:
        return _stage("readme_perfil", "NOT_EXECUTED",
                      "README proposto só com o currículo; sem GitHub não há projetos nem comparação com o atual.",
                      precisa_mudar=None, motivos=[], proposta=proposal, atual=None)
    if current is None:
        reasons.append(f"Não existe README de perfil. Crie o repositório público '{username}' com este README.")
    else:
        norm = normalize(current)
        missing = [s for s in resume.skills[:12] if normalize(s) not in norm]
        if len(missing) > 4:
            reasons.append(f"O README atual não cita {len(missing)} competências centrais do currículo: {', '.join(missing[:6])}…")
        if picks and not any(p["name"].lower() in current.lower() for p in picks[:3]):
            reasons.append("O README não linka os projetos de maior destaque.")
        if PHONE_RE.search(current):
            reasons.append("O README expõe um número de telefone — remova dados pessoais sensíveis.")
        if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", current) and not include_email:
            reasons.append("O README expõe e-mail em texto — avalie se deseja manter público.")
        for c in _consistency(resume, snap):
            if "README" in c:
                reasons.append(c)
        if resume.headline and not (find_skills(resume.headline) & find_skills(current)):
            reasons.append("O título do README não reflete o título do currículo.")
        if len(current) > 12000:
            reasons.append("README muito longo — recrutadores leem os primeiros segundos; resuma.")
    need = bool(reasons)
    summary = "Recomendado atualizar o README do perfil." if need else "README atual está adequado; proposta disponível como alternativa."
    return _stage("readme_perfil", "SUCCESS", summary, precisa_mudar=need, motivos=reasons, proposta=proposal,
                  atual=current, publicar="Nada é publicado automaticamente: revise e confirme para abrir um pull request.")


# ------------------------------------------------------------------ etapa 7
def ats_stage(resume: ParsedResume, snap: GitHubSnapshot, featured: dict) -> dict:
    issues = []
    if resume.layout_multicolumn:
        issues.append(_finding("alta", "Layout em duas colunas", "Muitos ATS leem colunas fora de ordem; use coluna única."))
    titles = " ".join(resume.sections).lower()
    for label, keys in [("Experiência profissional", ("experi",)), ("Formação acadêmica", ("forma", "educa")),
                        ("Competências técnicas", ("compet", "habilidade", "skills"))]:
        if not any(k in titles for k in keys):
            issues.append(_finding("alta" if label != "Competências técnicas" else "media",
                                   f"Seção '{label}' não encontrada", f"Adicione uma seção com o título padrão '{label.upper()}'."))
    if not resume.emails:
        issues.append(_finding("alta", "Sem e-mail de contato", "Inclua e-mail em texto (não só ícone)."))
    if not resume.github_username:
        issues.append(_finding("media", "Sem link do GitHub em texto", "Escreva github.com/usuario por extenso."))
    if re.search(r"[-]", resume.raw_text):
        issues.append(_finding("media", "Ícones/glifos especiais no texto", "Substitua ícones por texto simples."))
    if re.search(r"\(\s*\w{3}/20\d\d\)", resume.raw_text) is None and resume.certifications:
        issues.append(_finding("baixa", "Certificações sem data", "Informe mês/ano de emissão."))
    period = re.compile(r"\b(?:\w{3}/)?(?:19|20)\d{2}\s*[-–a]\s*(?:(?:\w{3}/)?(?:19|20)\d{2}|atual|presente|o momento)", re.I)
    if not period.search(resume.raw_text):
        issues.append(_finding("media", "Experiências sem período (mês/ano de início e fim)", "ATS e recrutadores esperam datas em cada experiência."))
    username = (snap.user or {}).get("login") or resume.github_username
    picks = featured.get("destaques", []) if featured.get("status") == "SUCCESS" else []
    text = build_ats_resume(resume, username, picks)
    score = max(0, 100 - sum({"alta": 20, "media": 10, "baixa": 5}[i["severity"]] for i in issues))
    return _stage("curriculo_ats", "SUCCESS", f"Compatibilidade ATS estimada: {score}/100 ({len(issues)} ajuste(s)).",
                  score=score, problemas=issues, curriculo_ats=text,
                  nota="Itens [PENDENTE] precisam ser preenchidos por você; o sistema não inventa formação, datas ou cargos.")


# ------------------------------------------------------------------ orquestração
def run_funnel(resume: ParsedResume, snap: GitHubSnapshot, include_email: bool = False,
               now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    results: dict[str, dict] = {}

    def safe(key: str, fn, *args):
        try:
            results[key] = fn(*args)
        except Exception as exc:  # uma etapa com erro não derruba o funil
            results[key] = _stage(key, "FAILED", f"Erro interno: {type(exc).__name__}: {exc}")
        return results[key]

    audit = safe("auditoria_github", audit_github, snap, now)
    checklist = safe("checklist_habilidades", skills_checklist, resume, snap)
    seo = safe("seo_titulos", seo_review, resume, snap)
    featured = safe("projetos_destaque", featured_projects, resume, snap, now)
    if all(results[k]["status"] == "SUCCESS" for k in ("auditoria_github", "seo_titulos", "projetos_destaque")) \
            and checklist["status"] == "SUCCESS":
        safe("veredito_perfil", profile_verdict, audit, checklist, seo, featured, resume, snap)
    else:
        results["veredito_perfil"] = _stage("veredito_perfil", "BLOCKED", "Depende das etapas 1–4 concluídas com sucesso.")
    safe("readme_perfil", profile_readme_stage, resume, snap, featured, include_email)
    safe("curriculo_ats", ats_stage, resume, snap, featured)

    return {
        "gerado_em": now.isoformat(timespec="seconds"),
        "github": {"usuario": (snap.user or {}).get("login") or resume.github_username,
                   "fonte": snap.source, "disponivel": snap.available, "erro": snap.error},
        "curriculo": resume.to_dict(),
        "etapas": [results[k] for k, _ in STAGES],
    }
