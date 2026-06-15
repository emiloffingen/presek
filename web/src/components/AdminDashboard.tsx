import React, { useState, useEffect } from 'react';
import { apiBaseUrl } from '../lib/apiBase';
import { buildCsrfHeadersAsync } from '../lib/personalization.js';
import {
  Shield, Layout, Activity, Zap,
  Settings, Terminal, AlertTriangle, CheckCircle2,
  RefreshCw, BarChart3, Database, Globe
} from 'lucide-react';

export default function AdminDashboard({ lang = 'sr' }: { lang?: string }) {
  const [token, setToken] = useState('');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<any>(null);

  const fetchDashboard = async (overrideToken?: string) => {
    const activeToken = overrideToken || token;
    if (!activeToken) return;

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl()}/admin/dashboard?lang=${lang}`, {
        headers: { 'Authorization': `Bearer ${activeToken}` }
      });
      if (res.ok) {
        const payload = await res.json();
        setData(payload);
        setIsAuthenticated(true);
        if (typeof window !== 'undefined') sessionStorage.setItem('presek_admin_token', activeToken);
      } else {
        setError(lang === 'sr' ? 'Pristup je odbijen. Nevalidan token.' : 'Пристапот е одбиен. Невалиден токен.');
      }
    } catch {
      setError(lang === 'sr' ? 'Greška pri povezivanju sa serverom.' : 'Грешка при поврзување со серверот.');
    } finally {
      setLoading(false);
    }
  };

  const triggerNewsletter = async () => {
    try {
      const res = await fetch(`${apiBaseUrl()}/admin/tasks/trigger-newsletter?lang=${lang}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, ...(await buildCsrfHeadersAsync()) }
      });
      const data = await res.json();
      alert(data.message || (lang === 'sr' ? 'Bilten je aktiviran.' : 'Билтенот е активиран.'));
    } catch {
      alert(lang === 'sr' ? 'Greška pri aktiviranju biltena.' : 'Грешка при активирање на билтенот.');
    }
  };

  const clearFailedTasks = async () => {
    try {
      await fetch(`${apiBaseUrl()}/admin/tasks/retry-failed?lang=${lang}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, ...(await buildCsrfHeadersAsync()) }
      });
      fetchDashboard();
    } catch {
      alert(lang === 'sr' ? 'Greška pri restartovanju zadataka.' : 'Грешка при рестартирање на задачите.');
    }
  };

  const drainStaleClusters = async () => {
    try {
      const res = await fetch(`${apiBaseUrl()}/admin/tasks/drain-stale-clusters?lang=${lang}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, ...(await buildCsrfHeadersAsync()) }
      });
      const payload = await res.json();
      alert(payload.message || (lang === 'sr' ? 'Backlog osvežavanje pokrenuto.' : 'Backlog освежување е стартувано.'));
      fetchDashboard();
    } catch {
      alert(lang === 'sr' ? 'Greška pri osvežavanju zastarelih klastera.' : 'Грешка при освежување на застарени кластери.');
    }
  };

  const upgradeStuckFastSyntheses = async () => {
    try {
      const res = await fetch(`${apiBaseUrl()}/admin/tasks/upgrade-stuck-fast-syntheses?lang=${lang}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, ...(await buildCsrfHeadersAsync()) }
      });
      const payload = await res.json();
      alert(payload.message || (lang === 'sr' ? 'Nadogradnja pokrenuta.' : 'Надградбата е стартувана.'));
      fetchDashboard();
    } catch {
      alert(lang === 'sr' ? 'Greška pri nadogradnji sinteze.' : 'Грешка при надградба на синтеза.');
    }
  };

  const refreshFallbackSyntheses = async () => {
    try {
      const res = await fetch(`${apiBaseUrl()}/admin/tasks/refresh-fallback-syntheses?lang=${lang}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, ...(await buildCsrfHeadersAsync()) }
      });
      const payload = await res.json();
      alert(payload.message || (lang === 'sr' ? 'Osvežavanje fallback sinteze pokrenuto.' : 'Освежување fallback синтеза е стартувано.'));
      fetchDashboard();
    } catch {
      alert(lang === 'sr' ? 'Greška pri osvežavanju fallback sinteze.' : 'Грешка при освежување fallback синтеза.');
    }
  };

  const refreshLowScoreSyntheses = async () => {
    try {
      const res = await fetch(`${apiBaseUrl()}/admin/tasks/refresh-low-score-syntheses?lang=${lang}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, ...(await buildCsrfHeadersAsync()) }
      });
      const payload = await res.json();
      alert(payload.message || (lang === 'sr' ? 'Osvežavanje niskog kvaliteta pokrenuto.' : 'Освежување низок квалитет е стартувано.'));
      fetchDashboard();
    } catch {
      alert(lang === 'sr' ? 'Greška pri osvežavanju niskog kvaliteta.' : 'Грешка при освежување низок квалитет.');
    }
  };

  const clearFailedIngestion = async () => {
    try {
      const res = await fetch(`${apiBaseUrl()}/admin/tasks/clear-failed-ingestion?lang=${lang}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, ...(await buildCsrfHeadersAsync()) }
      });
      const payload = await res.json();
      alert(payload.message || (lang === 'sr' ? 'Ingestija restartovana.' : 'Ingestijata е рестартирана.'));
      fetchDashboard();
    } catch {
      alert(lang === 'sr' ? 'Greška pri čišćenju ingestion grešaka.' : 'Грешка при чистење ingestion грешки.');
    }
  };

  const openWeeklyReport = async () => {
    try {
      const res = await fetch(`${apiBaseUrl()}/admin/ops/weekly-report?lang=${lang}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const payload = await res.json();
      const blob = new Blob([JSON.stringify(payload.report || payload, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch {
      alert(lang === 'sr' ? 'Greška pri učitavanju nedeljnog izveštaja.' : 'Грешка при вчитување на неделен извештај.');
    }
  };

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const stored = sessionStorage.getItem('presek_admin_token') || '';
    if (stored) {
      setToken(stored);
      fetchDashboard(stored);
    }
  }, []);

  if (!isAuthenticated) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center p-4">
        <div className="bg-zinc-900 border border-zinc-800 p-8 rounded-2xl shadow-2xl w-full max-w-md">
          <div className="flex flex-col items-center mb-8">
            <div className="p-4 bg-nyt-accent/10 rounded-2xl mb-4">
              <Shield className="text-nyt-accent" size={32} />
            </div>
            <h2 className="text-xl font-bold text-center uppercase tracking-tight">{lang === 'sr' ? 'ADMIN AUTENTIKACIJA' : 'ADMIN АВТЕНТИКАЦИЈА'}</h2>
          </div>
          <div className="space-y-4">
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={lang === 'sr' ? "UNESITE ADMIN TOKEN" : "ВНЕСЕТЕ АДМИН ТОКЕН"}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 font-mono text-xs focus:ring-1 focus:ring-nyt-accent outline-none"
              onKeyDown={(e) => e.key === 'Enter' && fetchDashboard()}
            />
            <button
              onClick={() => fetchDashboard()}
              disabled={loading}
              className="w-full bg-zinc-100 text-black font-black text-xs py-3 rounded-lg hover:bg-white transition-all disabled:opacity-50"
            >
              {loading ? (lang === 'sr' ? 'AUTENTIKACIJA...' : 'АВТЕНТИКАЦИЈА...') : (lang === 'sr' ? 'PRISTUP KOKPITU' : 'ПРИСТАП ДО КОКПИТ')}
            </button>
            {error && <p className="text-red-500 text-[10px] font-mono text-center uppercase">{error}</p>}
          </div>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const systemOk = Boolean(data?.db?.ok && data?.redis?.ok);
  const aiCascade = Array.isArray(data.ai.fallback_order) ? data.ai.fallback_order.join(' -> ') : data.ai.current_provider;
  const ops = data.ops || {};
  const opsAlerts = Array.isArray(ops.alerts) ? ops.alerts : [];
  const opsStatus = ops.status || 'ok';
  const opsStatusClass =
    opsStatus === 'critical' ? 'bg-red-500/10 text-red-400 border-red-500/20'
    : opsStatus === 'warn' ? 'bg-amber-500/10 text-amber-300 border-amber-500/20'
    : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {ops.checked_at && (
        <section className="bg-zinc-950 border border-zinc-800 rounded-2xl p-6 space-y-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-xs font-black uppercase tracking-[0.18em] text-zinc-400">
                {lang === 'sr' ? 'EDITORIAL OPS KOKPIT' : 'EDITORIAL OPS КОКПИТ'}
              </h2>
              <p className="text-[11px] text-zinc-500 mt-2 max-w-2xl">
                {lang === 'sr'
                  ? 'Jedan pogled: ingestija, backlog sinteze, redovi i zastareli klasteri.'
                  : 'Еден поглед: инgestија, backlog на синтеза, редови и застарени кластери.'}
              </p>
            </div>
            <span className={`text-[10px] font-black uppercase px-3 py-1 rounded border ${opsStatusClass}`}>
              {opsStatus}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-[var(--grid-gap)]">
            <OpsMetric
              label={lang === 'sr' ? 'Ingestija' : 'Инgestија'}
              value={ops.ingestion?.label || ops.ingestion?.freshness_status || '—'}
              sub={ops.ingestion?.age_minutes != null ? `${ops.ingestion.age_minutes} min` : '—'}
            />
            <OpsMetric
              label={lang === 'sr' ? 'Nesintetizovano 24h' : 'Несинтетизирано 24ч'}
              value={ops.synthesis?.unsummarized_24h ?? '—'}
              sub={`${ops.synthesis?.unsummarized_total ?? 0} ${lang === 'sr' ? 'ukupno' : 'вкупно'}`}
            />
            <OpsMetric
              label={lang === 'sr' ? 'Najopterećeniji red' : 'Најоптоварен ред'}
              value={ops.queues?.busiest_queue_depth ?? '—'}
              sub={ops.queues?.busiest_queue || '—'}
            />
            <OpsMetric
              label={lang === 'sr' ? 'Zastareli klasteri' : 'Застарени кластери'}
              value={ops.stale_clusters?.count ?? 0}
              sub={`${Math.round((ops.synthesis?.fallback_ratio_24h || 0) * 100)}% ${lang === 'sr' ? 'fallback 24h' : 'fallback 24ч'}`}
            />
            <OpsMetric
              label={lang === 'sr' ? 'Provisional 24h' : 'Привремени 24ч'}
              value={ops.synthesis?.provisional_count_24h ?? 0}
              sub={`${ops.synthesis?.stuck_fast_count ?? 0} ${lang === 'sr' ? 'zaglavljenih' : 'заглавени'}`}
            />
            <OpsMetric
              label={lang === 'sr' ? 'Nizak kvalitet 24h' : 'Низок квалитет 24ч'}
              value={ops.synthesis?.low_score_count_24h ?? 0}
              sub={`${ops.synthesis?.fallback_count_24h ?? 0} ${lang === 'sr' ? 'fallback' : 'fallback'}`}
            />
          </div>

          {opsAlerts.length > 0 ? (
            <div className="space-y-2">
              {opsAlerts.map((alert: any) => (
                <div
                  key={`${alert.code}-${alert.metric || ''}`}
                  className={`flex items-start gap-3 rounded-lg border px-3 py-2 ${
                    alert.severity === 'critical'
                      ? 'border-red-500/20 bg-red-500/5 text-red-300'
                      : 'border-amber-500/20 bg-amber-500/5 text-amber-200'
                  }`}
                >
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-wide">{alert.code}</p>
                    <p className="text-[11px] text-zinc-300">{alert.message}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-500">
              {lang === 'sr' ? 'Nema aktivnih ops upozorenja' : 'Нема активни ops предупредувања'}
            </p>
          )}

          {Array.isArray(ops.stale_clusters?.sample_cluster_ids) && ops.stale_clusters.sample_cluster_ids.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {ops.stale_clusters.sample_cluster_ids.map((clusterId: string) => (
                <code key={clusterId} className="text-[10px] font-mono bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-zinc-400">
                  {clusterId}
                </code>
              ))}
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-1">
            <button
              onClick={drainStaleClusters}
              className="text-[10px] font-black uppercase px-3 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white"
            >
              {lang === 'sr' ? 'Osveži zastarele' : 'Освежи застарени'}
            </button>
            <button
              onClick={upgradeStuckFastSyntheses}
              className="text-[10px] font-black uppercase px-3 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white"
            >
              {lang === 'sr' ? 'Nadogradi zaglavljene' : 'Надгради заглавени'}
            </button>
            <button
              onClick={refreshFallbackSyntheses}
              className="text-[10px] font-black uppercase px-3 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white"
            >
              {lang === 'sr' ? 'Osveži fallback' : 'Освежи fallback'}
            </button>
            <button
              onClick={refreshLowScoreSyntheses}
              className="text-[10px] font-black uppercase px-3 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white"
            >
              {lang === 'sr' ? 'Osveži nizak kvalitet' : 'Освежи низок квалитет'}
            </button>
            <button
              onClick={clearFailedIngestion}
              className="text-[10px] font-black uppercase px-3 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-white"
            >
              {lang === 'sr' ? 'Očisti ingestion' : 'Исчисти ingestion'}
            </button>
            <button
              onClick={openWeeklyReport}
              className="text-[10px] font-black uppercase px-3 py-2 rounded-lg border border-zinc-700 text-zinc-300 hover:text-white"
            >
              {lang === 'sr' ? 'Nedeljni izveštaj' : 'Неделен извештај'}
            </button>
          </div>
        </section>
      )}

      {/* Top Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-[var(--grid-gap)]">
        <StatCard
          icon={<Zap size={18} />}
          label={lang === 'sr' ? 'SINTETIČKI PREGLED' : 'СИНТЕТИЧКИ ПРЕГЛЕД'}
          value={data.clusters.total_summaries}
          sub={`${data.clusters.total_clusters} ${lang === 'sr' ? 'KLASTERA UKUPNO' : 'КЛАСТЕРИ ВКУПНО'}`}
          trend={systemOk ? 'SISTEM OK' : 'ISSUE'}
          color="text-nyt-accent"
        />
        <StatCard
          icon={<Globe size={18} />}
          label={lang === 'sr' ? 'ZDRAVLJE KRAVLERA' : 'ЗДРАВЈЕ НА КРАВЛЕР'}
          value={data.scrapers.healthy_feeds}
          sub={`${data.scrapers.total_sources} ${lang === 'sr' ? 'AKTIVNIH IZVORA' : 'АКТИВНИ ИЗВОРИ'}`}
          trend={`${Math.round((data.scrapers.healthy_feeds / data.scrapers.total_feeds) * 100)}%`}
          color="text-emerald-500"
        />
        <StatCard
          icon={<Activity size={18} />}
          label={lang === 'sr' ? 'INGESTIJA 24Č' : 'ИНГЕСТИЈА 24Ч'}
          value={data.articles.last_24h}
          sub={`${data.articles.last_1h} ${lang === 'sr' ? 'U POSLEDNJEM ČASU' : 'ВО ПОСЛЕДНИОТ ЧАС'}`}
          trend="+4.2%"
          color="text-blue-500"
        />
        <StatCard
          icon={<AlertTriangle size={18} />}
          label={lang === 'sr' ? 'NEUSPELI ZADACI' : 'НЕУСПЕШНИ ЗАДАЧИ'}
          value={data.tasks.failed_tasks}
          sub="CELERY QUEUE"
          trend={data.tasks.failed_tasks > 0 ? 'ACTION' : 'CLEAN'}
          color={data.tasks.failed_tasks > 0 ? "text-red-500" : "text-zinc-500"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-[var(--grid-gap)]">
        {/* System Health Section */}
        <div className="space-y-6">
          <StatusTile
            icon={<Database size={16} />}
            label="POSTGRESQL"
            value={data.db?.version || 'Connected'}
            detail={`${data.db?.pool_size || 0} active connections`}
            ok={data.db?.ok}
          />
          <StatusTile
            icon={<Activity size={16} />}
            label="REDIS / CACHE"
            value={data.redis?.ping === 'PONG' ? 'Active' : 'Offline'}
            detail={data.redis?.error || 'Cache and queues reachable'}
            ok={data.redis?.ok}
          />

          {data.queues && (
            <div className="bg-zinc-900/40 border border-zinc-800 rounded-2xl p-6">
              <h3 className="text-xs font-black uppercase tracking-widest flex items-center gap-[var(--grid-gap)] mb-4">
                <BarChart3 size={14} className="text-zinc-500" />
                {lang === 'sr' ? 'CELERY REDOVI' : 'CELERY РЕДОВИ'}
              </h3>
              <div className="flex items-center justify-between mb-4">
                <span className="text-[10px] font-black uppercase text-zinc-500">intel-heavy</span>
                <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded ${
                  data.queues.intel_status === 'ok' ? 'bg-emerald-500/10 text-emerald-500'
                  : data.queues.intel_status === 'elevated' ? 'bg-yellow-500/10 text-yellow-500'
                  : data.queues.intel_status === 'busy' ? 'bg-orange-500/10 text-orange-500'
                  : 'bg-red-500/10 text-red-500'
                }`}>
                  {data.queues.intel_status}
                </span>
              </div>
              <div className="space-y-2">
                {Object.entries(data.queues.depths || {}).map(([name, depth]: [string, any]) => {
                  const numericDepth = Number(depth) || 0;
                  const full = data.queues.thresholds?.full || 800;
                  const pct = Math.min(100, Math.round((numericDepth / full) * 100));
                  return (
                    <div key={name}>
                      <div className="flex justify-between text-[9px] font-mono text-zinc-500 mb-1">
                        <span>{name}</span>
                        <span>{numericDepth}</span>
                      </div>
                      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div
                          className={`h-full ${name === 'intel-heavy' && numericDepth >= (data.queues.thresholds?.secondary || 150) ? 'bg-red-500' : 'bg-nyt-accent'}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="bg-nyt-accent/5 border border-nyt-accent/20 rounded-2xl p-6">
            <h3 className="text-xs font-black uppercase tracking-widest flex items-center gap-[var(--grid-gap)] mb-4 text-nyt-accent">
              <Zap size={14} /> {lang === 'sr' ? 'SISTEMSKA KASKADA' : 'СИСТЕМСКА КАСКАДА'}
            </h3>
            <div className="flex justify-between items-end">
              <div>
                <p className="text-xl font-black uppercase">{data.ai.current_provider}</p>
                <p className="text-[9px] text-zinc-500 uppercase font-mono tracking-tighter">{lang === 'sr' ? 'Primarni provajder' : 'Примарен провајдер'}</p>
              </div>
              <p className="text-xs font-bold text-zinc-400 text-right max-w-[55%]">{aiCascade}</p>
            </div>
          </div>
        </div>

        {/* Scraper Status Table */}
        <div className="lg:col-span-2 bg-zinc-900/40 border border-zinc-800 rounded-2xl overflow-hidden">
          <div className="p-6 border-b border-zinc-800 flex items-center justify-between">
            <h3 className="text-xs font-black uppercase tracking-widest flex items-center gap-[var(--grid-gap)]">
              <Layout size={14} className="text-zinc-500" /> {lang === 'sr' ? 'MONITORING IZVORA' : 'МОНИТОРИНГ НА ИЗВОРИ'}
            </h3>
            <span className="px-3 py-1 bg-zinc-800 rounded-full text-[9px] font-black text-zinc-400">LATEST FEED UPDATES</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px] font-mono">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800/50">
                  <th className="p-4 font-black">{lang === 'sr' ? 'IZVOR' : 'ИЗВОР'}</th>
                  <th className="p-4 font-black">{lang === 'sr' ? 'STATUS' : 'СТАТУС'}</th>
                  <th className="p-4 font-black">{lang === 'sr' ? 'POSLEDNJE' : 'ПОСЛЕДНО'}</th>
                  <th className="p-4 font-black">{lang === 'sr' ? 'VOLUMEN' : 'ВОЛУМЕН'}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {data.scrapers.recent_activity?.slice(0, 10).map((s: any, i: number) => (
                  <tr key={i} className="hover:bg-zinc-800/30 transition-colors">
                    <td className="p-4 font-bold text-zinc-300">{s.source}</td>
                    <td className="p-4">
                      <span className={`px-2 py-0.5 rounded-sm text-[9px] font-black ${s.is_active ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500'}`}>
                        {s.is_active ? 'ACTIVE' : 'ISSUES'}
                      </span>
                    </td>
                    <td className="p-4 text-zinc-500">{new Date(s.last_fetched).toLocaleTimeString()}</td>
                    <td className="p-4 text-zinc-400">{s.recent_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Action Panels */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-[var(--grid-gap)]">
          <div className="bg-zinc-900/40 border border-zinc-800 rounded-2xl p-6">
            <h3 className="text-xs font-black uppercase tracking-widest flex items-center gap-[var(--grid-gap)] mb-6">
              <Terminal size={14} className="text-zinc-500" /> {lang === 'sr' ? 'POSLEDNJE GREŠKE' : 'ПОСЛЕДНИ ГРЕШКИ'}
            </h3>
            <div className="space-y-3">
              {data.tasks.recent_failures?.length > 0 ? (
                <>
                  {data.tasks.recent_failures.map((f: any, i: number) => (
                    <div key={i} className="p-3 bg-red-500/5 border border-red-500/10 rounded-lg">
                      <p className="text-[10px] font-black text-red-400 uppercase mb-1">{f.task_name}</p>
                      <p className="text-[10px] font-mono text-zinc-500 line-clamp-2">{f.error}</p>
                    </div>
                  ))}
                  <button
                    onClick={clearFailedTasks}
                    className="w-full mt-4 flex items-center justify-center gap-[var(--grid-gap)] bg-zinc-800 hover:bg-zinc-700 text-white text-[10px] font-bold py-3 rounded-lg transition-all"
                  >
                    {lang === 'sr' ? 'IZBRIŠI GREŠKE' : 'ИЗБРИШИ ГРЕШКИ'}
                  </button>
                </>
              ) : (
                <div className="flex flex-col items-center justify-center py-10 opacity-30">
                  <CheckCircle2 size={32} className="mb-3" />
                  <p className="text-[10px] font-bold uppercase tracking-widest">{lang === 'sr' ? 'Nema aktivnih grešaka' : 'Нема активни грешки'}</p>
                </div>
              )}
            </div>
          </div>

          <div className="bg-zinc-900/40 border border-zinc-800 rounded-2xl p-6">
            <h3 className="text-xs font-black uppercase tracking-widest flex items-center gap-[var(--grid-gap)] mb-6">
              <Settings size={14} className="text-zinc-500" /> {lang === 'sr' ? 'SISTEMSKE KONTROLE' : 'СИСТЕМСКИ КОНТРОЛИ'}
            </h3>
            <div className="grid grid-cols-1 gap-[var(--grid-gap)]">
                <button
                  onClick={triggerNewsletter}
                  className="w-full flex items-center justify-center gap-[var(--grid-gap)] bg-nyt-accent hover:bg-nyt-accent/80 text-black text-[10px] font-black py-3 rounded-lg transition-all"
                >
                  <Zap size={14} /> {lang === 'sr' ? 'TRIGERUJ BILTEN' : 'ТРИГЕРУВАЈ БИЛТЕН'}
                </button>
                <button
                  onClick={() => fetchDashboard()}
                  className="w-full flex items-center justify-center gap-[var(--grid-gap)] bg-zinc-800 hover:bg-zinc-700 text-white text-[10px] font-bold py-3 rounded-lg transition-all"
                >
                  <RefreshCw size={14} /> {lang === 'sr' ? 'OSVEŽI KOKPIT' : 'ОСВЕЖИ КОКПИТ'}
                </button>
            </div>
          </div>
      </div>
    </div>
  );
}

function OpsMetric({ label, value, sub }: { label: string; value: string | number; sub: string }) {
  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4">
      <p className="text-[9px] font-black uppercase tracking-widest text-zinc-500 mb-2">{label}</p>
      <p className="text-2xl font-black text-zinc-100">{typeof value === 'number' ? value.toLocaleString() : value}</p>
      <p className="text-[9px] text-zinc-600 mt-2 font-bold uppercase">{sub}</p>
    </div>
  );
}

function StatCard({ icon, label, value, sub, trend, color }: any) {
  return (
    <div className="bg-zinc-900/40 border border-zinc-800 p-6 rounded-2xl group hover:border-zinc-700 transition-all">
      <div className="flex items-center justify-between mb-4">
        <div className={`p-2 rounded-lg bg-zinc-800/50 ${color}`}>
          {icon}
        </div>
        {trend && (
          <span className="text-[9px] font-black bg-zinc-800 px-2 py-0.5 rounded text-zinc-500 tracking-tighter">
            {trend}
          </span>
        )}
      </div>
      <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-1">{label}</p>
      <h4 className="text-3xl font-black tracking-tight">{value?.toLocaleString() || 0}</h4>
      <p className="text-[9px] text-zinc-600 mt-2 font-bold uppercase">{sub}</p>
    </div>
  );
}

function StatusTile({ icon, label, value, detail, ok }: any) {
  return (
    <div className="flex items-center gap-[var(--grid-gap)] p-4 bg-zinc-900/40 border border-zinc-800 rounded-2xl">
      <div className={`p-3 rounded-xl ${ok ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500'}`}>
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[9px] font-black text-zinc-500 uppercase tracking-widest">{label}</p>
        <p className="font-bold text-sm truncate">{value}</p>
        <p className="text-[9px] text-zinc-600 truncate">{detail}</p>
      </div>
      <div className={`w-2 h-2 rounded-full ${ok ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-red-500'}`} />
    </div>
  );
}
