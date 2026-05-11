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
        <h2 className="stats-section-title">Lokalna Analitika Na Predlozi</h2>
        <p className="stats-empty-copy">
          Koga ce pocnete da gledate predlozi za sledenje na pocetna, klaster, tema ili „Za Vas“, tuka ce se pojavi lokalna slika za toa sto navistina vi ubeduva da sledite tema ili izvor.
        </p>
      </section>
    );
  }

  return (
    <section className="stats-module">
      <div className="reader-analytics-head">
        <div>
          <h2 className="stats-section-title">Lokalna Analitika Na Predlozi</h2>
          <p className="reader-analytics-copy">
            Na ovoj ured: koi povrsini najcesto dobivaat sledenje, i dali podobro rabotat predlozi za temi ili za izvori.
          </p>
        </div>
        <div className="reader-analytics-total">
          <span><Sparkles size={13} /> {summary.totals.impressions} impresii</span>
          <strong>{summary.totals.follows} sledenja</strong>
          <small>{summary.totals.conversion_rate}% konverzija</small>
        </div>
      </div>

      <div className="reader-analytics-kind-grid">
        {Object.values(summary.totals.by_kind).map((item: any) => (
          <div key={item.kind} className="reader-analytics-kind-card">
            <p className="reader-analytics-kind-kicker">{item.label}</p>
            <strong>{item.follows}</strong>
            <p>{item.impressions} impresii · {item.conversion_rate}% konverzija</p>
          </div>
        ))}
      </div>

      <div className="reader-analytics-surface-list">
        {summary.surfaces.map((surface: any) => (
          <div key={surface.surface} className="reader-analytics-surface-card">
            <div className="reader-analytics-surface-head">
              <div>
                <h3>{surface.label}</h3>
                <p>{surface.impressions} impresii · {surface.follows} sledenja</p>
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
              <p className="reader-analytics-dismissals">Skrieno {surface.dismissals} pati</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
