import { useState, type ChangeEvent } from 'react';
import {
  ArrowLeft, BadgeCheck, CheckCircle2, CircleAlert, CircleSlash, Download, FileText,
  GitPullRequest, Loader2, ScanSearch, ShieldCheck, Star, Tags, UserRound, XCircle,
} from 'lucide-react';

/* Menu separado "Currículo ATS → GitHub" do Engenheiro Reverso.
   Consome a API Python (apps/api) via proxy /api/funnel do server.ts. */

type Status = 'PLANNED' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'BLOCKED' | 'NOT_EXECUTED';
interface Finding { severity: 'alta' | 'media' | 'baixa'; item: string; fix: string }
interface Stage {
  key: string; title: string; status: Status; summary: string;
  findings?: Finding[]; problemas?: Finding[]; stats?: Record<string, unknown>;
  items?: { skill: string; category: string; status: string; evidencias: string[]; acao: string }[];
  bio?: { atual: string | null; problemas: string[]; sugestao: string };
  repos?: { name: string; html_url: string; issues: string[]; descricao_rascunho: string | null; nome_sugerido: string | null; topics_sugeridos: string[] }[];
  destaques?: { name: string; html_url: string; motivo: string; score: { total: number } }[];
  score?: number; veredito?: string; corrigir_primeiro?: string[];
  criterios?: { criterio: string; peso: number; pontos: number }[];
  precisa_mudar?: boolean | null; motivos?: string[]; proposta?: string; atual?: string | null;
  curriculo_ats?: string; nota?: string;
}
interface Report { gerado_em: string; github: { usuario: string | null; fonte: string; erro: string | null }; etapas: Stage[] }

const ICONS = [ScanSearch, BadgeCheck, Tags, Star, UserRound, FileText, ShieldCheck];
const STATUS_STYLE: Record<Status, string> = {
  SUCCESS: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
  FAILED: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
  BLOCKED: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  NOT_EXECUTED: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  PLANNED: 'bg-slate-500/15 text-slate-300 border-slate-500/30',
  RUNNING: 'bg-sky-500/15 text-sky-300 border-sky-500/30',
};
const SEV: Record<string, string> = { alta: 'text-rose-300', media: 'text-amber-300', baixa: 'text-sky-300' };

function StatusChip({ status }: { status: Status }) {
  const Icon = status === 'SUCCESS' ? CheckCircle2 : status === 'FAILED' ? XCircle : status === 'BLOCKED' ? CircleAlert : CircleSlash;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${STATUS_STYLE[status]}`}>
      <Icon className="h-3 w-3" aria-hidden />{status}
    </span>
  );
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown' }));
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ResumeGithubFunnel() {
  const [file, setFile] = useState<{ filename: string; content_base64: string } | null>(null);
  const [text, setText] = useState('');
  const [username, setUsername] = useState('');
  const [token, setToken] = useState('');
  const [report, setReport] = useState<Report | null>(null);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [readme, setReadme] = useState('');
  const [writeToken, setWriteToken] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [prState, setPrState] = useState('');

  function onFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) { setError('Arquivo maior que 5 MB.'); return; }
    const reader = new FileReader();
    reader.onload = () => setFile({ filename: f.name, content_base64: String(reader.result).split(',')[1] });
    reader.readAsDataURL(f);
  }

  async function run() {
    setError(''); setLoading(true);
    try {
      const body: Record<string, unknown> = { github_username: username.trim() || undefined, github_token: token.trim() || undefined };
      if (file) body.resume = file; else body.resume_text = text;
      const res = await fetch('/api/funnel/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Falha ao executar o funil.');
      setReport(data); setActive(0);
      setReadme(data.etapas.find((s: Stage) => s.key === 'readme_perfil')?.proposta || '');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function openPr() {
    if (!report?.github.usuario) return;
    setPrState('Abrindo pull request…');
    const res = await fetch('/api/funnel/apply', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ github_username: report.github.usuario, github_token: writeToken.trim(), markdown: readme, confirm: true }),
    });
    const data = await res.json();
    setPrState(res.ok ? `Pull request aberto: ${data.pull_request.url}` : (data.error || data.message));
  }

  const stage = report?.etapas[active];

  return (
    <div className="min-h-screen bg-[#0b0d10] text-slate-200">
      <header className="border-b border-[#262b33] bg-[#0f1319]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-4">
          <a href="/" className="flex items-center gap-2 text-sm text-slate-400 hover:text-white"><ArrowLeft className="h-4 w-4" />Engenheiro Reverso</a>
          <span className="text-sm font-semibold text-cyan-300">Currículo ATS → GitHub</span>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="text-[clamp(1.4rem,4vw,2rem)] font-bold text-white">Funil de melhoria do GitHub com currículo</h1>
        <p className="mt-2 max-w-3xl text-slate-400">
          Primeiro o GitHub completo, depois o checklist de habilidades, SEO, projetos em destaque, veredito do perfil,
          README.md e currículo ATS. Tudo com base no currículo e nos dados públicos — nada é inventado nem publicado sem confirmação.
        </p>

        <section className="mt-6 grid gap-4 rounded-xl border border-[#262b33] bg-[#12151a] p-5 md:grid-cols-2">
          <div className="space-y-3">
            <label className="block text-sm text-slate-400" htmlFor="cv">Currículo (PDF, DOCX, TXT, MD — até 5 MB)</label>
            <input id="cv" type="file" accept=".pdf,.docx,.txt,.md" onChange={onFile}
              className="w-full rounded-lg border border-dashed border-[#3a4250] bg-[#181c22] p-3 text-sm" />
            <label className="block text-sm text-slate-400" htmlFor="cvtext">…ou cole o texto</label>
            <textarea id="cvtext" value={text} onChange={(e) => setText(e.target.value)} rows={5}
              className="w-full rounded-lg border border-[#262b33] bg-[#181c22] p-3 text-sm" />
          </div>
          <div className="space-y-3">
            <label className="block text-sm text-slate-400" htmlFor="gh">Usuário do GitHub (opcional se estiver no currículo)</label>
            <input id="gh" value={username} onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-[#262b33] bg-[#181c22] p-3 text-sm" />
            <label className="block text-sm text-slate-400" htmlFor="tk">Token de leitura (opcional, não é armazenado)</label>
            <input id="tk" type="password" value={token} onChange={(e) => setToken(e.target.value)} autoComplete="off"
              className="w-full rounded-lg border border-[#262b33] bg-[#181c22] p-3 text-sm" />
            <button onClick={run} disabled={loading || (!file && !text.trim())}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 font-semibold text-white hover:bg-blue-500 disabled:opacity-50">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}Executar funil
            </button>
            {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
          </div>
        </section>

        {report && (
          <section className="mt-8">
            <p className="text-xs text-slate-500">GitHub: {report.github.usuario || '—'} · fonte: {report.github.fonte}{report.github.erro ? ` · ${report.github.erro}` : ''}</p>
            <ol className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
              {report.etapas.map((s, i) => {
                const Icon = ICONS[i];
                return (
                  <li key={s.key}>
                    <button onClick={() => setActive(i)} aria-current={i === active}
                      className={`h-full w-full rounded-lg border p-3 text-left text-xs ${i === active ? 'border-blue-500 bg-[#181c22]' : 'border-[#262b33] bg-[#12151a]'}`}>
                      <Icon className="mb-1 h-4 w-4 text-cyan-300" aria-hidden />
                      <span className="block text-slate-500">Etapa {i + 1}</span>
                      <span className="block font-medium text-slate-200">{s.title}</span>
                      <span className="mt-1 block"><StatusChip status={s.status} /></span>
                    </button>
                  </li>
                );
              })}
            </ol>

            {stage && (
              <article className="mt-4 rounded-xl border border-[#262b33] bg-[#12151a] p-5 text-sm">
                <h2 className="flex flex-wrap items-center gap-2 text-lg font-semibold text-white">{stage.title}<StatusChip status={stage.status} /></h2>
                <p className="mt-1 text-slate-300">{stage.summary}</p>

                {[...(stage.findings || []), ...(stage.problemas || [])].length > 0 && (
                  <ul className="mt-4 space-y-2">
                    {[...(stage.findings || []), ...(stage.problemas || [])].map((f, i) => (
                      <li key={i}><span className={`mr-2 text-[11px] font-bold uppercase ${SEV[f.severity]}`}>{f.severity}</span>{f.item} — <span className="text-slate-400">{f.fix}</span></li>
                    ))}
                  </ul>
                )}

                {stage.items && (
                  <div className="mt-4 overflow-x-auto">
                    <table className="w-full text-left">
                      <thead className="text-slate-500"><tr><th className="py-2">Habilidade</th><th>Status</th><th>Evidências</th><th>Ação</th></tr></thead>
                      <tbody>{stage.items.map((it) => (
                        <tr key={it.skill} className="border-t border-[#262b33] align-top">
                          <td className="py-2">{it.skill}<div className="text-xs text-slate-500">{it.category}</div></td>
                          <td className={it.status === 'COMPROVADA' ? 'text-emerald-300' : it.status === 'SEM_EVIDENCIA' ? 'text-amber-300' : 'text-cyan-300'}>{it.status.replace(/_/g, ' ')}</td>
                          <td>{it.evidencias.join(', ') || '—'}</td>
                          <td className="text-slate-400">{it.acao}</td>
                        </tr>))}
                      </tbody>
                    </table>
                  </div>
                )}

                {stage.bio && (
                  <div className="mt-4 space-y-1">
                    <p><b>Bio atual:</b> {stage.bio.atual || '—'}</p>
                    {stage.bio.problemas.map((p) => <p key={p} className="text-amber-200">• {p}</p>)}
                    <p><b>Bio sugerida:</b> {stage.bio.sugestao}</p>
                  </div>
                )}
                {stage.repos && stage.repos.map((r) => (
                  <div key={r.name} className="mt-3 rounded-lg border border-[#262b33] p-3">
                    <a href={r.html_url} target="_blank" rel="noopener noreferrer" className="font-medium text-cyan-300">{r.name}</a>
                    <p className="text-slate-400">{r.issues.join(' ')}</p>
                    {r.nome_sugerido && <p>Nome sugerido: <code>{r.nome_sugerido}</code></p>}
                    {r.descricao_rascunho && <p className="italic">{r.descricao_rascunho}</p>}
                    <p className="text-xs text-slate-500">Topics: {r.topics_sugeridos.join(', ') || '—'}</p>
                  </div>
                ))}

                {stage.destaques && (
                  <ol className="mt-4 list-decimal space-y-2 pl-5">
                    {stage.destaques.map((p) => (
                      <li key={p.name}><a href={p.html_url} target="_blank" rel="noopener noreferrer" className="text-cyan-300">{p.name}</a> · {p.score.total} pts<div className="text-slate-400">{p.motivo}</div></li>
                    ))}
                  </ol>
                )}

                {stage.criterios && (
                  <div className="mt-4">
                    <p className="text-3xl font-bold text-white">{stage.score}/100 · {stage.veredito}</p>
                    <ul className="mt-2 space-y-1 text-slate-400">{stage.criterios.map((c) => <li key={c.criterio}>{c.criterio}: {c.pontos}/{c.peso}</li>)}</ul>
                    {!!stage.corrigir_primeiro?.length && <ul className="mt-3 space-y-1 text-amber-200">{stage.corrigir_primeiro.map((c) => <li key={c}>• {c}</li>)}</ul>}
                  </div>
                )}

                {stage.proposta !== undefined && (
                  <div className="mt-4 space-y-3">
                    {stage.motivos?.map((m) => <p key={m} className="text-amber-200">• {m}</p>)}
                    <textarea value={readme} onChange={(e) => setReadme(e.target.value)} rows={18}
                      className="w-full rounded-lg border border-[#262b33] bg-[#0a0c0f] p-3 font-mono text-xs" aria-label="Proposta de README" />
                    <button onClick={() => download('README.md', readme)} className="inline-flex items-center gap-2 rounded-lg border border-[#262b33] px-3 py-2"><Download className="h-4 w-4" />Baixar README.md</button>
                    <div className="rounded-lg border border-[#262b33] bg-[#181c22] p-4">
                      <p className="font-semibold">Publicar via pull request</p>
                      <p className="text-xs text-slate-400">Nada é publicado sem sua confirmação. Token com escrita no repositório de perfil.</p>
                      <input type="password" value={writeToken} onChange={(e) => setWriteToken(e.target.value)} autoComplete="off" aria-label="Token com escrita"
                        className="mt-2 w-full rounded-lg border border-[#262b33] bg-[#0b0d10] p-2" />
                      <label className="mt-2 flex items-center gap-2 text-xs"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />Revisei e autorizo abrir o pull request</label>
                      <button onClick={openPr} disabled={!confirmed || !writeToken.trim()} className="mt-2 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 font-semibold text-white disabled:opacity-50"><GitPullRequest className="h-4 w-4" />Abrir pull request</button>
                      {prState && <p className="mt-2 break-all text-xs">{prState}</p>}
                    </div>
                  </div>
                )}

                {stage.curriculo_ats && (
                  <div className="mt-4 space-y-3">
                    <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-lg border border-[#262b33] bg-[#0a0c0f] p-3 text-xs">{stage.curriculo_ats}</pre>
                    <button onClick={() => download('curriculo-ats.md', stage.curriculo_ats!)} className="inline-flex items-center gap-2 rounded-lg border border-[#262b33] px-3 py-2"><Download className="h-4 w-4" />Baixar currículo ATS</button>
                  </div>
                )}
                {stage.nota && <p className="mt-3 text-xs text-slate-500">{stage.nota}</p>}
              </article>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
