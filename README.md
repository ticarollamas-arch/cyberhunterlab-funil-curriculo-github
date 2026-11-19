# CyberHunterLab — monorepo

Plataforma de engenharia de software e cibersegurança. Esta entrega traz o **funil Currículo ATS → GitHub** funcionando, com um menu separado dentro do **Engenheiro Reverso**.

```
apps/
  api/                  API Python (Starlette, migrável para FastAPI) + CLI + UI web testada
  engenheiro-reverso/   App Vite/React original + novo menu /curriculo-ats
docs/STATUS.md          O que foi executado, o que não foi e o que está PLANNED
```

## Funil Currículo ATS → GitHub (ordem das etapas)

1. **Auditoria completa do GitHub**: bio, nome, site, README de perfil, descrições, topics, licenças, repositórios vazios, genéricos e forks.
2. **Checklist de habilidades e capacidades**: cada habilidade do currículo marcada como COMPROVADA, SEM_EVIDENCIA ou SO_NO_GITHUB, com os repositórios que a comprovam.
3. **SEO de títulos**: bio sugerida, nomes em kebab-case, rascunhos de descrição e topics por projeto.
4. **Projetos importantes em destaque**: ranking justificado de até 6 pins, mais o que trocar nos pins atuais.
5. **Veredito do perfil principal**: nota de 0 a 100 (BOM / PRECISA MELHORAR / FRACO), critérios ponderados e inconsistências entre currículo e GitHub.
6. **README.md do perfil**: diz se precisa mudar e por quê, e gera uma proposta editável. Para publicar, abre um pull request **só com confirmação explícita e token de escrita**.
7. **Currículo ATS**: aponta problemas (colunas, seções, datas) e gera uma versão em coluna única.

Regras: o sistema nunca inventa cargos, datas, certificações ou descrições (lacunas aparecem como `[PENDENTE]` ou `[o que resolve]`), nunca altera visibilidade de repositórios e nunca publica sem confirmação. Tokens não são armazenados nem registrados em logs.

## Rodar

```bash
cd apps/api
pip install -r requirements.txt          # também é preciso o poppler-utils para ler PDF
uvicorn cyberhunter_api.server:app --port 8000
# abra http://localhost:8000 (UI do funil)
python -m pytest -q                       # 17 testes

# CLI
python -m cyberhunter_api.cli --resume curriculo.pdf --github usuario --out saida/
python -m cyberhunter_api.cli --resume curriculo.pdf --snapshot snapshot.json   # offline
```

Engenheiro Reverso com o menu novo:

```bash
cd apps/engenheiro-reverso
cp .env.example .env    # FUNNEL_API_URL=http://127.0.0.1:8000
npm install && npm run dev   # http://localhost:3000/curriculo-ats
```

Ou suba tudo com `docker compose up --build`.

## API

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/health` | status e lista das etapas |
| POST | `/api/funnel/run` | `{resume:{filename,content_base64} \| resume_text, github_username?, github_token?, snapshot?, include_email?}` |
| POST | `/api/funnel/apply` | `{github_username, github_token, markdown, confirm:true}`: abre PR no repositório de perfil. Sem `confirm` responde 409 com uma prévia. |
