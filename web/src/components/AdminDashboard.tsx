import React, { useState, useEffect } from 'react';
import { 
  Activity, 
  Cpu, 
  Database, 
  ShieldAlert, 
  RefreshCcw, 
  Globe, 
  Zap, 
  CheckCircle2, 
  Terminal,
  ChevronRight
} from 'lucide-react';
import { apiBaseUrl } from '../lib/apiBase';

export default function AdminDashboard() {
  const [token, setToken] = useState<string>('');
  const [isAuth, setIsAuth] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  const fetchDashboard = async (overrideToken?: string) => {
    const activeToken = overrideToken || token;
    if (!activeToken) return;

    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBaseUrl()}/admin/dashboard`, {
        headers: { 'X-Admin-Token': activeToken }
      });
      if (res.ok) {
        const payload = await res.json();
        setData(payload);
        setIsAuth(true);
        sessionStorage.setItem('presek_admin_token', activeToken);
      } else {
        setError('Пристапот е одбиен. Невалиден токен.');
        setIsAuth(false);
      }
    } catch (e) {
      setError('Грешка при поврзување со API-то.');
    } finally {
      setLoading(false);
    }
  };

  const clearFailedTasks = async () => {
    setActionLoading(true);
    try {
      await fetch(`${apiBaseUrl()}/admin/tasks/retry-failed`, {
        method: 'POST',
        headers: { 'X-Admin-Token': token }
      });
      fetchDashboard();
    } catch (e) {
      alert('Грешка при рестартирање задачи.');
    } finally {
      setActionLoading(false);
    }
  };

  useEffect(() => {
    const stored = sessionStorage.getItem('presek_admin_token') || '';
    if (stored) {
      setToken(stored);
      fetchDashboard(stored);
    }
  }, []);

  if (!isAuth) {
    return (
      <div className="max-w-md mx-auto py-20">
        <div className="bg-zinc-900 border border-zinc-800 p-8 rounded-2xl shadow-2xl">
          <div className="flex justify-center mb-6">
            <ShieldAlert size={48} className="text-nyt-accent" />
          </div>
          <h2 className="text-xl font-bold text-center mb-6">ADMIN AUTHENTICATION</h2>
          <div className="space-y-4">
            <input 
              type="password" 
              placeholder="ENTER ADMIN TOKEN" 
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-3 font-mono text-xs focus:ring-1 focus:ring-nyt-accent outline-none"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && fetchDashboard()}
            />
            <button 
              onClick={() => fetchDashboard()}
              disabled={loading}
              className="w-full bg-zinc-100 text-black font-black text-xs py-3 rounded-lg hover:bg-white transition-all disabled:opacity-50"
            >
              {loading ? 'AUTHENTICATING...' : 'ACCESS COCKPIT'}
            </button>
            {error && <p className="text-red-500 text-[10px] font-mono text-center uppercase">{error}</p>}
          </div>
        </div>
      </div>
    );
  }

  const aiPercent = data ? Math.min(100, (data.ai.gemini_usage_today / data.ai.gemini_daily_limit) * 100) : 0;

  return (
    <div className="space-y-8 font-sans">
      {/* Top Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard 
          icon={<Cpu size={20} />} 
          label="AI PIPELINE" 
          value={data.ai.current_provider.toUpperCase()} 
          sub={`${(data.ai.gemini_usage_today / 1000).toFixed(1)}k / 2.0M tokens`}
          trend={aiPercent}
          color="text-nyt-accent"
        />
        <StatCard 
          icon={<Globe size={20} />} 
          label="CRAWLER HEALTH" 
          value={`${(data.scrapers.global_acceptance_rate * 100).toFixed(0)}%`} 
          sub={`${data.scrapers.total_sources} ACTIVE SOURCES`}
          trend={data.scrapers.global_acceptance_rate * 100}
          color="text-emerald-500"
        />
        <StatCard 
          icon={<Database size={20} />} 
          label="DATABASE" 
          value={`${data.db.size_mb.toFixed(0)} MB`} 
          sub={`${data.db.article_count.toLocaleString()} ARTICLES`}
          trend={75}
          color="text-blue-500"
        />
        <StatCard 
          icon={<Activity size={20} />} 
          label="FAILED TASKS" 
          value={data.tasks.failed_recent.length} 
          sub="LAST 24 HOURS"
          trend={data.tasks.failed_recent.length > 0 ? 100 : 0}
          color={data.tasks.failed_recent.length > 0 ? "text-red-500" : "text-zinc-500"}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Scraper Status Table */}
        <div className="lg:col-span-2 bg-zinc-900/40 border border-zinc-800 rounded-2xl overflow-hidden">
          <div className="p-6 border-b border-zinc-800 flex items-center justify-between">
            <h3 className="text-xs font-black uppercase tracking-widest flex items-center gap-2">
              <Globe size={14} className="text-zinc-500" /> SOURCE FEED HEALTH
            </h3>
            <span className="text-[10px] font-mono text-zinc-500">REAL-TIME MONITOR</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[11px] font-mono">
              <thead>
                <tr className="bg-zinc-900/80 text-zinc-500 uppercase">
                  <th className="px-6 py-3 font-medium">Source</th>
                  <th className="px-6 py-3 font-medium">Status</th>
                  <th className="px-6 py-3 font-medium text-right">Acceptance</th>
                  <th className="px-6 py-3 font-medium text-right">Last Sync</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {Object.values(data.scrapers.statuses).map((s: any) => (
                  <tr key={s.source} className="hover:bg-zinc-800/30 transition-colors">
                    <td className="px-6 py-4 font-bold text-zinc-200">{s.source}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <span className={`w-1.5 h-1.5 rounded-full ${s.degraded ? 'bg-red-500 animate-pulse' : 'bg-emerald-500'}`}></span>
                        <span className={s.degraded ? 'text-red-400' : 'text-zinc-400'}>{s.quality_label}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                       <span className={s.acceptance_ratio < 0.5 ? 'text-amber-500' : 'text-zinc-300'}>
                         {(s.acceptance_ratio * 100).toFixed(0)}%
                       </span>
                    </td>
                    <td className="px-6 py-4 text-right text-zinc-500 text-[10px]">
                      {new Date(s.updated_at).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Task Queue & Maintenance */}
        <div className="space-y-6">
          <div className="bg-zinc-900/40 border border-zinc-800 rounded-2xl p-6">
            <h3 className="text-xs font-black uppercase tracking-widest flex items-center gap-2 mb-6">
              <Terminal size={14} className="text-zinc-500" /> RECENT FAILURES
            </h3>
            {data.tasks.failed_recent.length > 0 ? (
              <div className="space-y-4">
                {data.tasks.failed_recent.map((task: any, i: number) => (
                  <div key={i} className="p-3 bg-zinc-950 border-l-2 border-red-500 rounded-r-lg">
                    <p className="text-[10px] font-bold text-zinc-200 truncate">{task.task_name}</p>
                    <p className="text-[9px] text-zinc-500 line-clamp-1 mt-1">{task.error_message}</p>
                    <p className="text-[8px] font-mono text-zinc-600 mt-2 uppercase">{new Date(task.failed_at).toLocaleString()}</p>
                  </div>
                ))}
                <button 
                  onClick={clearFailedTasks}
                  disabled={actionLoading}
                  className="w-full mt-4 flex items-center justify-center gap-2 bg-zinc-800 hover:bg-zinc-700 text-white text-[10px] font-bold py-3 rounded-lg transition-all"
                >
                  <RefreshCcw size={12} className={actionLoading ? 'animate-spin' : ''} />
                  CLEAR FAILURES
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-10 opacity-30">
                <CheckCircle2 size={32} className="mb-2" />
                <p className="text-[10px] font-bold uppercase tracking-widest">No Active Failures</p>
              </div>
            )}
          </div>

          <div className="bg-nyt-accent/5 border border-nyt-accent/20 rounded-2xl p-6">
            <h3 className="text-xs font-black uppercase tracking-widest flex items-center gap-2 mb-4 text-nyt-accent">
              <Zap size={14} /> AI USAGE QUOTA
            </h3>
            <div className="relative h-2 bg-zinc-800 rounded-full overflow-hidden mb-4">
              <div 
                className="absolute top-0 left-0 h-full bg-nyt-accent transition-all duration-1000"
                style={{ width: `${aiPercent}%` }}
              ></div>
            </div>
            <div className="flex justify-between items-end">
              <div>
                <p className="text-[20px] font-black">{aiPercent.toFixed(1)}%</p>
                <p className="text-[9px] text-zinc-500 uppercase font-mono tracking-tighter">Budget Utilization</p>
              </div>
              <div className="text-right">
                <p className="text-[10px] font-mono text-zinc-300">{(data.ai.gemini_usage_today / 1000).toFixed(0)}K TOKENS</p>
                <p className="text-[9px] text-zinc-500 uppercase font-mono tracking-tighter">DAILY CAP: 2M</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon, label, value, sub, trend, color }: any) {
  return (
    <div className="bg-zinc-900/40 border border-zinc-800 p-6 rounded-2xl group hover:border-zinc-700 transition-all">
      <div className="flex items-center justify-between mb-4">
        <div className={`p-2 bg-zinc-950 rounded-lg ${color}`}>
          {icon}
        </div>
        <div className="flex items-center gap-1">
          <span className={`text-[10px] font-mono ${trend > 90 ? 'text-red-400' : 'text-emerald-400'}`}>
            {trend > 90 ? 'HIGH' : 'STABLE'}
          </span>
          <ChevronRight size={10} className="text-zinc-600" />
        </div>
      </div>
      <p className="text-[10px] font-black text-zinc-500 uppercase tracking-widest mb-1">{label}</p>
      <h3 className="text-2xl font-black text-white mb-1 tracking-tight">{value}</h3>
      <p className="text-[10px] font-mono text-zinc-500 uppercase">{sub}</p>
    </div>
  );
}
