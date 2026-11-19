"""CLI: python -m cyberhunter_api.cli --resume cv.pdf [--github usuario] [--snapshot snap.json] [--out pasta]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .funnel import run_funnel
from .resume_parser import ResumeError, parse_resume_file
from .server import build_snapshot, snapshot_from_json


def render_markdown(report: dict) -> str:
    out = [f"# Relatório do funil Currículo → GitHub", "",
           f"- Gerado em: {report['gerado_em']}",
           f"- GitHub: {report['github']['usuario'] or '—'} (fonte: {report['github']['fonte']})", ""]
    if report["github"]["erro"]:
        out += [f"> GitHub indisponível: {report['github']['erro']}", ""]
    for i, st in enumerate(report["etapas"], 1):
        out += [f"## {i}. {st['title']} — `{st['status']}`", "", st["summary"], ""]
        for f in st.get("findings", []) + st.get("problemas", []):
            out.append(f"- **[{f['severity']}]** {f['item']} → {f['fix']}")
        for it in st.get("items", []):
            ev = ", ".join(it["evidencias"]) or "—"
            out.append(f"- [{'x' if it['status'] == 'COMPROVADA' else ' '}] **{it['skill']}** ({it['category']}) — {it['status']} — evidências: {ev}")
        if st.get("bio"):
            b = st["bio"]
            out += [f"- Bio atual: {b['atual'] or '—'}", *[f"  - {p}" for p in b["problemas"]], f"- Bio sugerida: {b['sugestao']}"]
        for r in st.get("repos", []):
            out.append(f"- **{r['name']}**: {' '.join(r['issues'])} Topics: {', '.join(r['topics_sugeridos']) or '—'}"
                       + (f" Rascunho: _{r['descricao_rascunho']}_" if r.get("descricao_rascunho") else ""))
        for p in st.get("destaques", []):
            out.append(f"- **{p['name']}** ({p['score']['total']} pts) — {p['motivo']}")
        if st.get("criterios"):
            out += ["", "| Critério | Peso | Pontos |", "|---|---|---|"]
            out += [f"| {c['criterio']} | {c['peso']} | {c['pontos']} |" for c in st["criterios"]]
        for c in st.get("corrigir_primeiro", []):
            out.append(f"- Corrigir primeiro: {c}")
        for m in st.get("motivos", []):
            out.append(f"- {m}")
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Funil Currículo ATS → GitHub (CyberHunterLab)")
    ap.add_argument("--resume", required=True)
    ap.add_argument("--github")
    ap.add_argument("--snapshot", help="JSON com user/repos/profile_readme (modo offline)")
    ap.add_argument("--include-email", action="store_true")
    ap.add_argument("--out", default="funil-saida")
    a = ap.parse_args(argv)
    try:
        resume = parse_resume_file(a.resume, Path(a.resume).read_bytes())
    except (OSError, ResumeError) as exc:
        print(f"Erro no currículo: {exc}", file=sys.stderr)
        return 2
    if a.snapshot:
        snap = snapshot_from_json(json.loads(Path(a.snapshot).read_text("utf-8")))
    else:
        snap = build_snapshot(a.github or resume.github_username, os.environ.get("GITHUB_TOKEN"))
    report = run_funnel(resume, snap, include_email=a.include_email)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "relatorio.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
    (out / "relatorio.md").write_text(render_markdown(report), "utf-8")
    stages = {s["key"]: s for s in report["etapas"]}
    (out / "README-perfil-proposta.md").write_text(stages["readme_perfil"]["proposta"], "utf-8")
    (out / "curriculo-ats.md").write_text(stages["curriculo_ats"].get("curriculo_ats", ""), "utf-8")
    for s in report["etapas"]:
        print(f"{s['status']:<13} {s['title']}: {s['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
