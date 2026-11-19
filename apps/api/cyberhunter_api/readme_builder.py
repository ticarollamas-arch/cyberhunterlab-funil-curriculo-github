"""Geração de README de perfil e currículo ATS a partir de evidências.

Regra: todo texto vem do currículo ou dos dados públicos do GitHub.
Nada de experiência, cargo, certificação ou métrica inventada.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .resume_parser import ParsedResume
from .skills import SKILLS, skill_by_name

_BADGE_COLORS = {
    "Linguagens": "1f6feb", "Backend & Web": "0e7490", "Cloud & DevOps": "2563eb",
    "Segurança": "b91c1c", "IA & Dados": "7c3aed", "Automação": "0f766e",
}


def badge(label: str, category: str) -> str:
    color = _BADGE_COLORS.get(category, "334155")
    text = quote(label.replace("-", "--").replace("_", "__"), safe="")
    return f"![{label}](https://img.shields.io/badge/{text}-{color}?style=flat-square)"


def _title_case(name: str) -> str:
    if name.isupper():
        return " ".join(w.capitalize() if len(w) > 2 else w.lower() for w in name.split())
    return name


def _section(resume: ParsedResume, *keys: str) -> str:
    for title, body in resume.sections.items():
        if any(k.lower() in title.lower() for k in keys):
            return body
    return ""


def _clean_paragraph(text: str) -> str:
    """Junta linhas quebradas pelo PDF e remove marcadores; mantém o conteúdo original."""
    text = re.sub(r"[-]", "", text)  # glifos de ícones privados de PDFs
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def build_profile_readme(resume: ParsedResume, featured: list[dict], username: str | None,
                         include_email: bool = False) -> str:
    name = _title_case(resume.name) or (username or "")
    lines: list[str] = [f"# {name}", ""]
    if resume.headline:
        lines += [f"**{_title_case(resume.headline)}**", ""]
    meta = [m for m in [resume.location] if m]
    if meta:
        lines += [" · ".join(meta), ""]

    about = _clean_paragraph(_section(resume, "POSICIONAMENTO", "SOBRE", "RESUMO", "PERFIL"))
    if about:
        lines += ["## Sobre", "", about, ""]

    by_cat: dict[str, list[str]] = {}
    for s in resume.skills:
        sk = skill_by_name(s)
        if sk:
            by_cat.setdefault(sk.category, []).append(s)
    if by_cat:
        lines += ["## Stack e competências", ""]
        order = [c for c in _BADGE_COLORS if c in by_cat]
        for cat in order:
            lines.append(f"**{cat}**  ")
            lines.append(" ".join(badge(s, cat) for s in by_cat[cat]))
            lines.append("")

    if featured:
        lines += ["## Projetos em destaque", "", "| Projeto | Descrição | Stack |", "|---|---|---|"]
        for r in featured:
            desc = (r.get("description") or "Descrição pendente — adicionar no repositório.").replace("|", "\\|")
            stack = ", ".join(r.get("skills", [])[:4]) or (r.get("language") or "—")
            lines.append(f"| [{r['name']}]({r['html_url']}) | {desc} | {stack} |")
        lines.append("")

    research = _section(resume, "PESQUISA EM SEGURANÇA", "BUG BOUNTY")
    highlights = resume.experience_highlights
    if highlights:
        lines += ["## Experiência e pesquisa", ""]
        lines += [f"- {h}" for h in highlights]
        lines.append("")
    elif research:
        lines += ["## Pesquisa em segurança", "", _clean_paragraph(research), ""]

    if resume.certifications:
        lines += ["## Certificações e badges", ""]
        lines += [f"- {c}" for c in resume.certifications]
        lines.append("")

    contact = []
    if username:
        contact.append(f"[GitHub](https://github.com/{username})")
    for url in resume.links:
        if "linkedin.com" in url:
            contact.append(f"[LinkedIn]({url})")
        elif "github.com" not in url:
            contact.append(f"[Site]({url})")
    if include_email and resume.emails:
        contact.append(f"[E-mail](mailto:{resume.emails[0]})")
    if contact:
        lines += ["## Contato", "", " · ".join(dict.fromkeys(contact)), ""]

    lines += ["<!-- Gerado pelo funil Currículo → GitHub do CyberHunterLab a partir do currículo e dos",
              "     repositórios públicos. Revise todo o conteúdo antes de publicar. -->", ""]
    return "\n".join(lines)


def build_ats_resume(resume: ParsedResume, username: str | None, featured: list[dict]) -> str:
    """Currículo em coluna única, sem tabelas/ícones, com seções padrão para ATS."""
    out = [_title_case(resume.name).upper() or "NOME", ""]
    if resume.headline:
        out.append(_title_case(resume.headline))
    contact = [resume.location] + resume.emails[:1]
    if username:
        contact.append(f"github.com/{username}")
    contact += [u.replace("https://", "") for u in resume.links if "linkedin.com" in u]
    out += [" | ".join(c for c in contact if c), ""]

    about = _clean_paragraph(_section(resume, "RESUMO", "POSICIONAMENTO", "PERFIL"))
    if about:
        out += ["RESUMO PROFISSIONAL", about, ""]

    exp = _section(resume, "EXPERIÊNCIA", "EXPERIENCIA")
    if exp or resume.experience_highlights:
        out.append("EXPERIÊNCIA")
        out += [f"- {h}" for h in resume.experience_highlights]
        out.append("")

    if resume.skills:
        out.append("COMPETÊNCIAS TÉCNICAS")
        cats: dict[str, list[str]] = {}
        for s in resume.skills:
            sk = skill_by_name(s)
            cats.setdefault(sk.category if sk else "Outras", []).append(s)
        out += [f"{c}: {', '.join(v)}" for c, v in cats.items()]
        out.append("")

    if featured:
        out.append("PROJETOS")
        for r in featured:
            desc = r.get("description") or ""
            out.append(f"- {r['name']}{' — ' + desc if desc else ''} ({r['html_url'].replace('https://', '')})")
        out.append("")

    edu = _section(resume, "FORMAÇÃO", "FORMACAO", "EDUCAÇÃO", "EDUCATION")
    out += ["FORMAÇÃO ACADÊMICA", _clean_paragraph(edu) if edu else "[PENDENTE — informe sua formação; não consta no currículo enviado]", ""]

    if resume.certifications:
        out.append("CERTIFICAÇÕES")
        out += [f"- {c}" for c in resume.certifications]
        out.append("")
    return "\n".join(out)


ALL_CATEGORIES = list(dict.fromkeys(s.category for s in SKILLS))
