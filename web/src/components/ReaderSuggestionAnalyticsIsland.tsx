import React, { useEffect, useState } from 'react';
import { MousePointerClick, Sparkles } from 'lucide-react';
import { getSuggestionConversionSummary } from '../lib/personalization.js';

export default function ReaderSuggestionAnalyticsIsland() {
  const [summary, setSummary] = useState<any>(() => getSuggestionConversionSummary());

  useEffect(() => {
    setSummary(getSuggestionConversionSummary());
  }, []);

  if (!summary?.surfaces?.length) {
    return (
      <section className="stats-module">
        <h2 className="stats-section-title">Локална Аналитика На Предлози</h2>
        <p className="stats-empty-copy">
          Кога ќе почнете да гледате предлози за следење на почетна, кластер, тема или „За Вас“, тука ќе се појави локална слика за тоа што навистина ве убедува да следите тема или извор.
        </p>
      </section>
    );
  }

  return (
    <section className="stats-module">
      <div className="reader-analytics-head">
        <div>
          <h2 className="stats-section-title">Локална Аналитика На Предлози</h2>
          <p className="reader-analytics-copy">
            На овој уред: кои површини најчесто добиваат следење, и дали подобро работат предлози за теми или за извори.
          </p>
        </div>
        <div className="reader-analytics-total">
          <span><Sparkles size={13} /> {summary.totals.impressions} импресии</span>
          <strong>{summary.totals.follows} следења</strong>
          <small>{summary.totals.conversion_rate}% конверзија</small>
        </div>
      </div>

      <div className="reader-analytics-kind-grid">
        {Object.values(summary.totals.by_kind).map((item: any) => (
          <div key={item.kind} className="reader-analytics-kind-card">
            <p className="reader-analytics-kind-kicker">{item.label}</p>
            <strong>{item.follows}</strong>
            <p>{item.impressions} импресии · {item.conversion_rate}% конверзија</p>
          </div>
        ))}
      </div>

      <div className="reader-analytics-surface-list">
        {summary.surfaces.map((surface: any) => (
          <div key={surface.surface} className="reader-analytics-surface-card">
            <div className="reader-analytics-surface-head">
              <div>
                <h3>{surface.label}</h3>
                <p>{surface.impressions} импресии · {surface.follows} следења</p>
              </div>
              <div className="reader-analytics-surface-rate">
                <MousePointerClick size={13} />
                <strong>{surface.conversion_rate}%</strong>
              </div>
            </div>

            <div className="reader-analytics-surface-kinds">
              {surface.by_kind.map((item: any) => (
                <div key={item.kind} className="reader-analytics-surface-kind">
                  <span>{item.label}</span>
                  <span>{item.follows}/{item.impressions || 0}</span>
                </div>
              ))}
            </div>

            {surface.dismissals > 0 && (
              <p className="reader-analytics-dismissals">Скриено {surface.dismissals} пати</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
