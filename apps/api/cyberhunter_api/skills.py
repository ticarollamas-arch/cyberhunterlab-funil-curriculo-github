"""Taxonomia de habilidades usada pelo funil Currículo → GitHub.

Cada habilidade tem um nome canônico, uma categoria e aliases que podem
aparecer em currículos, nomes de repositórios, descrições, topics ou na
linguagem principal detectada pelo GitHub.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
    name: str
    category: str
    aliases: tuple[str, ...]
    topic: str  # topic GitHub recomendado (kebab-case, minúsculo)


_RAW: list[tuple[str, str, tuple[str, ...], str]] = [
    # Linguagens
    ("Python", "Linguagens", ("python", "python3", "py"), "python"),
    ("Go", "Linguagens", ("golang", "go lang"), "golang"),
    ("JavaScript", "Linguagens", ("javascript", "js", "ecmascript"), "javascript"),
    ("TypeScript", "Linguagens", ("typescript", "ts"), "typescript"),
    ("Java", "Linguagens", ("java",), "java"),
    ("C++", "Linguagens", ("c++", "cpp"), "cpp"),
    ("C#", "Linguagens", ("c#", "csharp", ".net", "dotnet"), "csharp"),
    ("Rust", "Linguagens", ("rust",), "rust"),
    ("Shell", "Linguagens", ("bash", "shell", "shell script"), "shell"),
    ("YAML", "Linguagens", ("yaml", "yml"), "yaml"),
    ("SQL", "Linguagens", ("sql", "postgresql", "postgres", "mysql", "sqlite"), "sql"),
    # Backend / web
    ("Node.js", "Backend & Web", ("node.js", "nodejs", "node", "express"), "nodejs"),
    ("FastAPI", "Backend & Web", ("fastapi",), "fastapi"),
    ("Flask", "Backend & Web", ("flask",), "flask"),
    ("Django", "Backend & Web", ("django",), "django"),
    ("React", "Backend & Web", ("react", "reactjs", "react.js"), "react"),
    ("Next.js", "Backend & Web", ("next.js", "nextjs"), "nextjs"),
    ("APIs REST", "Backend & Web", ("api", "apis", "rest", "rest api", "integração de apis"), "rest-api"),
    ("Microsserviços", "Backend & Web", ("microsserviços", "microservices", "microsservicos"), "microservices"),
    ("Full Stack", "Backend & Web", ("full stack", "fullstack", "full-stack"), "fullstack"),
    # Cloud & DevOps
    ("Google Cloud", "Cloud & DevOps", ("google cloud", "gcp", "google cloud platform", "vertex ai", "bigquery", "firebase"), "google-cloud"),
    ("AWS", "Cloud & DevOps", ("aws", "amazon web services"), "aws"),
    ("Docker", "Cloud & DevOps", ("docker", "docker compose", "dockerfile", "docker-compose"), "docker"),
    ("Kubernetes", "Cloud & DevOps", ("kubernetes", "k8s"), "kubernetes"),
    ("Terraform", "Cloud & DevOps", ("terraform", "iac"), "terraform"),
    ("CI/CD", "Cloud & DevOps", ("ci/cd", "cicd", "github actions", "pipeline"), "github-actions"),
    # Segurança
    ("AppSec", "Segurança", ("appsec", "application security", "segurança de aplicações"), "appsec"),
    ("DevSecOps", "Segurança", ("devsecops",), "devsecops"),
    ("SAST", "Segurança", ("sast", "análise estática", "static analysis", "semgrep", "codeql"), "sast"),
    ("DAST", "Segurança", ("dast", "zap", "owasp zap"), "dast"),
    ("OWASP Top 10", "Segurança", ("owasp", "owasp top 10"), "owasp"),
    ("CWE/CVE", "Segurança", ("cwe", "cve"), "cwe"),
    ("Threat Modeling", "Segurança", ("threat modeling", "modelagem de ameaças"), "threat-modeling"),
    ("Pentest", "Segurança", ("pentest", "pentesting", "penetration testing", "teste de intrusão"), "pentesting"),
    ("Bug Bounty", "Segurança", ("bug bounty", "hackerone", "bugcrowd", "vrp", "recon", "reconnaissance", "reconhecimento"), "bug-bounty"),
    ("Engenharia Reversa", "Segurança", ("engenharia reversa", "reverse engineering", "apk", "decompile"), "reverse-engineering"),
    ("Taint Analysis", "Segurança", ("taint analysis", "taint"), "taint-analysis"),
    ("Nuclei", "Segurança", ("nuclei",), "nuclei"),
    # IA & Dados
    ("LLMs", "IA & Dados", ("llm", "llms", "large language models", "gpt", "gemini", "ollama"), "llm"),
    ("Agentes de IA", "IA & Dados", ("multiagentes", "multi-agent", "agentes", "agents", "agentic"), "ai-agents"),
    ("Engenharia de Prompts", "IA & Dados", ("engenharia de prompts", "prompt engineering", "prompts"), "prompt-engineering"),
    ("Machine Learning", "IA & Dados", ("machine learning", "ml", "mlops"), "machine-learning"),
    ("Pandas", "IA & Dados", ("pandas",), "pandas"),
    ("NumPy", "IA & Dados", ("numpy",), "numpy"),
    # Automação
    ("Automação", "Automação", ("automação", "automacao", "automation", "workflows", "scripts", "bot", "scraper"), "automation"),
]

SKILLS: tuple[Skill, ...] = tuple(Skill(n, c, a, t) for n, c, a, t in _RAW)

# Linguagem principal do GitHub → habilidade canônica
GITHUB_LANGUAGE_MAP = {
    "Python": "Python", "Go": "Go", "JavaScript": "JavaScript", "TypeScript": "TypeScript",
    "Java": "Java", "C++": "C++", "C#": "C#", "Rust": "Rust", "Shell": "Shell",
    "HCL": "Terraform", "Dockerfile": "Docker", "Jupyter Notebook": "Python",
}


def normalize(text: str) -> str:
    """Minúsculas, sem acentos e com separadores uniformizados."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def _alias_pattern(alias: str) -> re.Pattern[str]:
    a = re.escape(normalize(alias))
    # bordas que funcionam com símbolos como c++, c#, ci/cd e .net
    return re.compile(rf"(?<![a-z0-9]){a}(?![a-z0-9])")


_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    s.name: [_alias_pattern(a) for a in (s.aliases + (s.name,))] for s in SKILLS
}

# Aliases curtos e ambíguos só contam em texto técnico já filtrado (topics, nomes);
# em prosa livre do currículo exigem a forma longa.
_AMBIGUOUS_IN_PROSE = {"go lang", "ts", "js", "py", "ml", "node", "api", "apis", "rest", "agentes",
                       "agents", "scripts", "bot", "pipeline", "iac", "taint", "apk", "recon", "zap"}
_PROSE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    s.name: [_alias_pattern(a) for a in (s.aliases + (s.name,)) if normalize(a) not in _AMBIGUOUS_IN_PROSE]
    for s in SKILLS
}


def find_skills(text: str, prose: bool = True) -> set[str]:
    """Retorna nomes canônicos de habilidades encontradas no texto."""
    norm = normalize(text)
    table = _PROSE_PATTERNS if prose else _PATTERNS
    found = {name for name, pats in table.items() if any(p.search(norm) for p in pats)}
    # "Go" só em prosa quando aparece como linguagem listada (evita o verbo "go")
    if prose and "Go" in found and not re.search(r"(?<![a-z])(golang|python, go|go,)(?![a-z])", norm):
        found.discard("Go")
    return found


def skill_by_name(name: str) -> Skill | None:
    return next((s for s in SKILLS if s.name == name), None)
