"""Leitura e interpretação de currículos (PDF, DOCX, TXT, Markdown).

Tudo é determinístico: o parser só extrai o que está escrito no arquivo.
Nada é inferido ou inventado.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from .skills import find_skills

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md", ".markdown"}


class ResumeError(ValueError):
    """Erro de validação ou leitura do currículo."""


@dataclass
class ParsedResume:
    name: str = ""
    headline: str = ""
    location: str = ""
    emails: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    github_username: str | None = None
    sections: dict[str, str] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    experience_highlights: list[str] = field(default_factory=list)
    layout_multicolumn: bool = False
    raw_text: str = ""

    def to_dict(self, include_raw: bool = False) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "raw_text"}
        d["emails"] = [mask_email(e) for e in self.emails]
        if include_raw:
            d["raw_text"] = self.raw_text
        return d


def mask_email(email: str) -> str:
    user, _, domain = email.partition("@")
    return (user[:2] + "***@" + domain) if domain else "***"


# ---------------------------------------------------------------- extração

def extract_text(filename: str, data: bytes) -> tuple[str, list[str]]:
    """Retorna (texto, links) do arquivo. Valida tamanho, extensão e assinatura."""
    if not data:
        raise ResumeError("Arquivo vazio.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ResumeError("Arquivo maior que 5 MB.")
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ResumeError(f"Formato não suportado: {ext or 'sem extensão'}. Use PDF, DOCX, TXT ou MD.")

    if ext == ".pdf":
        if not data.startswith(b"%PDF"):
            raise ResumeError("O arquivo não tem assinatura de PDF válida.")
        return _pdf_text(data), _pdf_links(data)
    if ext == ".docx":
        if not data.startswith(b"PK"):
            raise ResumeError("O arquivo não tem assinatura de DOCX válida.")
        return _docx_text(data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    return text, re.findall(r"https?://[^\s)>\]]+", text)


def _pdf_text(data: bytes) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise ResumeError("Leitura de PDF indisponível: instale poppler-utils (pdftotext) ou envie TXT/DOCX.")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.pdf"
        src.write_bytes(data)
        proc = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(src), "-"],
                              capture_output=True, timeout=30, check=False)
    if proc.returncode != 0:
        raise ResumeError("Não foi possível ler o PDF (arquivo corrompido ou protegido).")
    return proc.stdout.decode("utf-8", "replace")


def _pdf_links(data: bytes) -> list[str]:
    found = re.findall(rb"/URI\s*\((https?://[^)]+)\)", data)
    found += re.findall(rb"https?://[A-Za-z0-9./_%#?=&-]+", data)
    out: list[str] = []
    for raw in found:
        url = raw.decode("latin-1").rstrip(").,")
        if url not in out and "w3.org" not in url and "adobe.com" not in url:
            out.append(url)
    return out


def _docx_text(data: bytes) -> tuple[str, list[str]]:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            info = zf.getinfo("word/document.xml")
            if info.file_size > 20 * 1024 * 1024:
                raise ResumeError("DOCX descompactado excede o limite.")
            xml = zf.read(info)
            rels = zf.read("word/_rels/document.xml.rels") if "word/_rels/document.xml.rels" in zf.namelist() else b""
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ResumeError("DOCX inválido.") from exc
    root = ElementTree.fromstring(xml)
    lines = []
    for p in root.iter(f"{{{ns['w']}}}p"):
        lines.append("".join(t.text or "" for t in p.iter(f"{{{ns['w']}}}t")))
    links = re.findall(r'Target="(https?://[^"]+)"', rels.decode("utf-8", "replace"))
    return "\n".join(lines), links


# ---------------------------------------------------------------- interpretação

_HEADING = re.compile(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9&/,\-\s]{6,}$")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PAGE_FOOTER = re.compile(r"page \d+ of \d+|página \d+ de \d+", re.I)


def parse_resume(text: str, links: list[str] | None = None) -> ParsedResume:
    links = list(dict.fromkeys(links or []))
    raw_lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n")]
    lines = [ln for ln in raw_lines if ln.strip() and not _PAGE_FOOTER.search(ln)]
    if not lines:
        raise ResumeError("Nenhum texto legível foi encontrado no currículo.")

    r = ParsedResume(raw_text=text, links=links)
    r.name = lines[0].strip().lstrip("#").strip()

    # Título: linhas logo após o nome, antes da linha de contato
    head: list[str] = []
    for ln in lines[1:6]:
        if _EMAIL.search(ln) or "•" in ln or "|" not in ln and head and not ln.isupper():
            break
        if _HEADING.match(ln.strip()) and head and "|" not in ln and "|" not in head[-1] and not head[-1].rstrip().endswith("&"):
            break
        head.append(ln.strip())
    r.headline = " ".join(head).replace("  ", " ")

    for ln in lines[:8]:
        if _EMAIL.search(ln) or "•" in ln:
            first = re.split(r"\s*[•|]\s*", ln.strip())[0]
            if first and not _EMAIL.search(first):
                r.location = first
            break

    r.emails = list(dict.fromkeys(_EMAIL.findall(text)))
    for url in links:
        m = re.match(r"https?://(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})/?$", url)
        if m:
            r.github_username = m.group(1)
            break

    # Seções por cabeçalhos em caixa alta
    current = "_inicio"
    buf: dict[str, list[str]] = {current: []}
    for ln in lines[1:]:
        s = ln.strip()
        if _HEADING.match(s) and len(s) < 80 and not _EMAIL.search(s) and s not in r.headline:
            current = s.lstrip("#").strip()
            buf.setdefault(current, [])
        else:
            buf[current].append(s)
    r.sections = {k: "\n".join(v).strip() for k, v in buf.items() if v and k != "_inicio"}

    r.skills = sorted(find_skills(text, prose=True))

    for title, body in r.sections.items():
        if re.search(r"CERTIFICA|BADGE|INSÍGNIA", title, re.I):
            items = re.split(r"\n|(?<=\))\s+(?=[A-Z])", body)
            r.certifications = [i.strip(" •-") for i in items if len(i.strip()) > 3]
        if re.search(r"EXPERI|RESUMO|BUG BOUNTY|PESQUISA", title, re.I):
            for ln in body.split("\n"):
                if ":" in ln and len(ln) > 30:
                    r.experience_highlights.append(ln.split(":")[0].strip(" •-"))

    # Layout em colunas: muitas linhas com grandes blocos de espaços no meio
    wide_gaps = sum(1 for ln in raw_lines if re.search(r"\S\s{8,}\S", ln))
    r.layout_multicolumn = wide_gaps >= 4
    return r


def parse_resume_file(filename: str, data: bytes) -> ParsedResume:
    text, links = extract_text(filename, data)
    return parse_resume(text, links)
