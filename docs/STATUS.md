# Status da entrega — 19/11/2026

## Executado e verificado neste ambiente

| Item | Status | Evidência |
|---|---|---|
| API do funil (7 etapas) | SUCCESS | `pytest`: 17 testes aprovados (parser PDF/DOCX/TXT, validação de upload, 7 etapas, cliente GitHub com transporte simulado, fluxo de PR, rotas HTTP via ASGI) |
| UI web do funil (`apps/api/static/funnel.html`) | SUCCESS | Playwright/Chromium em 390px e 1280px: 7 etapas SUCCESS, sem erros JS, sem overflow horizontal, botão de PR bloqueado até confirmação + token |
| CLI | SUCCESS | Rodada com fixture fictícia e com um currículo real em PDF |
| Sintaxe TS/TSX das alterações no Engenheiro Reverso | SUCCESS | `typescript.transpileModule` sem diagnósticos |
| Correção de segurança: `envPrefix` do Vite expunha `NVIDIA_API_KEY` ao navegador | SUCCESS | Agora só `VITE_*` |

## Não executado

| Item | Status | Motivo |
|---|---|---|
| `npm install` / `vite build` / `tsc` com tipos do Engenheiro Reverso | NOT_EXECUTED | Sem acesso a registros de pacotes neste ambiente |
| Chamadas reais à API do GitHub | NOT_EXECUTED | API bloqueada aqui; o cliente foi testado com transporte simulado |
| Abertura real de pull request | NOT_EXECUTED | Exige token do usuário e confirmação |
| Docker / docker-compose | NOT_EXECUTED | Sem Docker no ambiente |
| Migração Starlette → FastAPI | PLANNED | FastAPI não instalável aqui; as rotas são compatíveis |

## Roadmap do prompt mestre (PLANNED)

Fase 1 landing nova cyberhuntlab.com.br · Fase 2 AI Code Studio (workspace, ferramentas de arquivo, execução isolada, ZIP) · Fase 3 orquestrador multiagente · Fase 4 GitHub OAuth/App + operações em massa com prévia · Fase 5 Security Lab (Semgrep, Trivy, Gitleaks…) com escopo autorizado · Fase 6 Open Source & GSoC · Fase 7 hardening e deploy Vercel + VPS.

Limitações conhecidas do parser: em PDFs de duas colunas, termos quebrados entre colunas (ex.: "engenharia / reversa") podem não ser detectados, e certificações listadas na mesma linha podem vir juntas.
