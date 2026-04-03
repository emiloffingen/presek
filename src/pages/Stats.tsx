import React, { useEffect, useState } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { Line, Doughnut } from 'react-chartjs-2';
import { fetchStatsFull, StatsFullData } from '@/api/client';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

export const Stats: React.FC = () => {
  const [data, setData] = useState<StatsFullData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [themeColors, setThemeColors] = useState({ text: '#121212', border: '#E2E2E2' });

  useEffect(() => {
    const updateColors = () => {
      const _cs = getComputedStyle(document.documentElement);
      setThemeColors({
        text: _cs.getPropertyValue('--text-primary').trim() || '#121212',
        border: _cs.getPropertyValue('--border').trim() || '#E2E2E2'
      });
    };
    updateColors();
    window.addEventListener('themeChanged', updateColors);
    
    const load = async () => {
      try {
        const d = await fetchStatsFull();
        setData(d);
      } catch (e) {
        console.error(e);
      } finally {
        setIsLoading(false);
      }
    };
    load();
    return () => window.removeEventListener('themeChanged', updateColors);
  }, []);

  if (isLoading || !data) {
    return (
      <div className="page-content fade-in">
        <header className="page-header">
          <div className="skeleton-box" style={{ height: '40px', width: '300px' }}></div>
          <div className="skeleton-box" style={{ height: '20px', width: '500px', marginTop: '1rem' }}></div>
        </header>
        <div className="kpi-grid">
           {[1, 2, 3, 4].map(i => <div key={i} className="kpi-item"><div className="skeleton-box" style={{ height: '40px', width: '100px' }}></div></div>)}
        </div>
      </div>
    );
  }

  const velocityData = {
    labels: (data.velocity || []).map(v => new Date(v.t).getHours() + ':00'),
    datasets: [{
      data: (data.velocity || []).map(v => v.n),
      borderColor: themeColors.text,
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
      tension: 0.3
    }]
  };

  const categoryData = {
    labels: (data.by_category || []).map(c => c.cat),
    datasets: [{
      data: (data.by_category || []).map(c => c.n),
      backgroundColor: [themeColors.text, '#444', '#666', '#888', '#AAA', '#BBB', '#CCC', '#DDD'],
      borderWidth: 0
    }]
  };

  const renderBars = (items: any[], valKey: string, labelKey: string) => {
    const max = items.length ? Math.max(...items.map(i => i[valKey])) : 1;
    return items.slice(0, 8).map((i, idx) => (
      <div key={idx} className="bar-row">
        <span className="bar-label" title={i[labelKey]}>{i[labelKey]}</span>
        <div className="bar-track"><div className="bar-fill" style={{ width: `${(i[valKey] / max) * 100}%` }}></div></div>
        <span className="bar-val">{i[valKey]}</span>
      </div>
    ));
  };

  return (
    <div className="page-content fade-in">
      <header className="page-header">
        <h1 className="nyt-title">Медиумски Пулс</h1>
        <p className="page-subtitle">Анализа на македонскиот информативен простор во реално време</p>
      </header>

      <div className="kpi-grid">
        <div className="kpi-item">
          <span className="kpi-value">{(data.total_articles || 0).toLocaleString()}</span>
          <span className="rail-label">Вкупно Објави</span>
        </div>
        <div className="kpi-item">
          <span className="kpi-value">{(data.last_24h || 0).toLocaleString()}</span>
          <span className="rail-label">Последни 24ч</span>
        </div>
        <div className="kpi-item">
          <span className="kpi-value">{(data.summarized_pct || 0)}%</span>
          <span className="rail-label">Системски Резимирани</span>
        </div>
        <div className="kpi-item">
          <span className="kpi-value">{data.uptime || '—'}</span>
          <span className="rail-label">Системски Uptime</span>
        </div>
      </div>

      <div className="charts-grid">
        <div>
          <h3 className="rail-label section-header">Брзина на Ингестија (24ч)</h3>
          <div className="chart-wrap">
            <Line
              data={velocityData}
              options={{
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                  y: { grid: { color: themeColors.border }, ticks: { color: themeColors.text, font: { size: 10 } } },
                  x: { grid: { display: false }, ticks: { color: themeColors.text, font: { size: 10 }, maxRotation: 0 } }
                }
              }}
            />
          </div>
        </div>
        <div>
          <h3 className="rail-label section-header">По Категорија</h3>
          <div className="chart-wrap">
            <Doughnut
              data={categoryData}
              options={{
                responsive: true,
                maintainAspectRatio: false,
                cutout: '80%',
                plugins: { legend: { display: false } }
              }}
            />
          </div>
        </div>
      </div>

      <div className="half-grid">
        <div>
          <h3 className="rail-label section-header">Најактивни Извори</h3>
          <div id="sourcesStats">{renderBars(data.by_source, 'n', 'source')}</div>
        </div>
        <div>
          <h3 className="rail-label section-header">Најбрзи Медиуми (7д)</h3>
          <div id="speedStats">{renderBars(data.speed_leaderboard, 'first_count', 'source')}</div>
        </div>
      </div>

      <div className="stat-table">
        <h3 className="rail-label">Системски Информации</h3>
        <div className="stat-row-grid">
          <div className="stat-row">
            <span className="stat-row-label">База (PostgreSQL)</span>
            <strong>{data.db_size_mb} MB</strong>
          </div>
          <div className="stat-row">
            <span className="stat-row-label">Активни Фидови</span>
            <strong>{data.total_feeds}</strong>
          </div>
          <div className="stat-row">
            <span className="stat-row-label">Најстара Статија</span>
            <strong>{data.oldest_article ? new Date(data.oldest_article).toLocaleDateString('mk-MK') : '—'}</strong>
          </div>
          <div className="stat-row">
            <span className="stat-row-label">Последно Ажурирање</span>
            <strong>{new Date(data.new_article || data.newest_article || Date.now()).toLocaleTimeString('mk-MK')}</strong>
          </div>
        </div>
      </div>
    </div>
  );
};
