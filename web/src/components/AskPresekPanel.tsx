import React, { useEffect, useRef, useState } from 'react';
import { Loader2, MessageCircle, Send, ShieldCheck, TriangleAlert, GitCompareArrows, Link2 } from 'lucide-react';
import { apiBaseUrl } from '../lib/apiBase';

type Citation = {
  source?: string;
  title?: string;
  link?: string;
  snippet?: string;
  created_at?: string;
};

type AskPresekResponse = {
  status: 'success' | 'error';
  answer: string;
  response?: string;
  confidence?: 'high' | 'medium' | 'low' | string;
  confirmed_points?: string[];
  unclear_points?: string[];
  source_differences?: string;
  citations?: Citation[];
  related_questions?: string[];
};

type Props = {
  clusterId: string;
  suggestions: string[];
  initialQuestion?: string;
};

const CONFIDENCE_LABELS: Record<string, string> = {
  high: 'Висока сигурност',
  medium: 'Средна сигурност',
  low: 'Ниска сигурност',
};

function normalizeQuestion(value: string) {
  return value.replace(/\s+/g, ' ').trim();
}

function formatRelativeTime(value?: string) {
  if (!value) return '';
  try {
    return new Date(value).toLocaleTimeString('mk-MK', {
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '';
  }
}

export default function AskPresekPanel({ clusterId, suggestions, initialQuestion = '' }: Props) {
  const [question, setQuestion] = useState(initialQuestion);
  const [result, setResult] = useState<AskPresekResponse | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const autoAskedRef = useRef(false);

  async function submitQuestion(nextQuestion?: string) {
    const normalized = normalizeQuestion(nextQuestion ?? question);
    if (!normalized || isLoading) return;

    setQuestion(normalized);
    setError('');
    setIsLoading(true);

    try {
      const response = await fetch(`${apiBaseUrl()}/chat_cluster`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cluster_id: clusterId,
          query: normalized,
        }),
      });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.detail || 'Не успеав да добијам одговор.');
      }

      setResult(payload as AskPresekResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не успеав да добијам одговор.');
    } finally {
      setIsLoading(false);
    }
  }

  function jumpToCitation(link?: string) {
    if (!link) return;
    const target = document.querySelector<HTMLElement>(`[data-article-link="${encodeURIComponent(link)}"]`);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.add('ask-citation-targeted');
    window.setTimeout(() => target.classList.remove('ask-citation-targeted'), 2200);
  }

  const confidenceLabel = CONFIDENCE_LABELS[String(result?.confidence || '').toLowerCase()] || 'Проверка во текстот';
  const confidenceTone = String(result?.confidence || '').toLowerCase();

  useEffect(() => {
    const normalized = normalizeQuestion(initialQuestion);
    if (!normalized || autoAskedRef.current) return;
    autoAskedRef.current = true;
    void submitQuestion(normalized);
  }, [initialQuestion]);

  return (
    <div className="ask-presek">
      <div className="ask-intro">
        <p className="micro-label mb-2 text-nyt-accent">Контекст само од овој кластер</p>
        <h3 className="nyt-section-label flex items-center gap-2 mb-2 text-foreground">
          <MessageCircle size={14} /> ПРАШАЈ ГО ПРЕСЕК
        </h3>
        <p className="font-serif italic text-sm text-muted-foreground leading-relaxed">
          Прашај што е потврдено, што останува нејасно и каде изворите се разликуваат.
        </p>
      </div>

      <div className="ask-suggestions">
        {suggestions.map((item) => (
          <button
            key={item}
            type="button"
            className="ask-suggestion"
            onClick={() => void submitQuestion(item)}
            disabled={isLoading}
          >
            {item}
          </button>
        ))}
      </div>

      <form
        className="ask-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submitQuestion();
        }}
      >
        <textarea
          className="ask-input"
          rows={4}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="На пример: Кои факти се повторуваат кај повеќе извори?"
          maxLength={500}
        />
        <button type="submit" className="ask-submit" disabled={isLoading || !normalizeQuestion(question)}>
          {isLoading ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          Одговор
        </button>
      </form>

      {error && <p className="ask-error">{error}</p>}

      {result && (
        <div className="ask-result">
          <div className="ask-result-head">
            <strong className="nyt-section-label tracking-[0.18em]">Што можеме да кажеме сега</strong>
            <span className={`ask-confidence ask-confidence-${confidenceTone || 'medium'}`}>{confidenceLabel}</span>
          </div>

          <p className="ask-scope-note">Овој одговор е составен само од изворите во овој кластер.</p>

          <p className="ask-answer">{result.answer || result.response}</p>

          {Array.isArray(result.citations) && result.citations.length > 0 && (
            <div className="ask-inline-citations">
              <span className="ask-inline-citations-label">Поткрепено со</span>
              {result.citations.map((item, index) => (
                <button
                  type="button"
                  key={`inline-${item.link || item.title || item.source || index}`}
                  className="ask-inline-citation"
                  onClick={() => jumpToCitation(item.link)}
                >
                  [{index + 1}]
                </button>
              ))}
            </div>
          )}

          {Array.isArray(result.confirmed_points) && result.confirmed_points.length > 0 && (
            <div className="ask-evidence-block">
              <h4 className="ask-section-title">
                <ShieldCheck size={14} /> Потврдено
              </h4>
              <ul className="ask-evidence-list">
                {result.confirmed_points.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {Array.isArray(result.unclear_points) && result.unclear_points.length > 0 && (
            <div className="ask-evidence-block">
              <h4 className="ask-section-title">
                <TriangleAlert size={14} /> Што останува нејасно
              </h4>
              <ul className="ask-evidence-list ask-evidence-list-muted">
                {result.unclear_points.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {result.source_differences && (
            <div className="ask-evidence-block">
              <h4 className="ask-section-title">
                <GitCompareArrows size={14} /> Каде се разликуваат
              </h4>
              <p className="ask-answer ask-answer-compact">{result.source_differences}</p>
            </div>
          )}

          {Array.isArray(result.citations) && result.citations.length > 0 && (
            <div className="ask-evidence-block">
              <h4 className="ask-section-title">
                <Link2 size={14} /> Извори зад одговорот
              </h4>
              <div className="ask-citation-list">
                {result.citations.map((item, index) => (
                  <button
                    type="button"
                    key={`${item.link || item.title || item.source || index}`}
                    className="ask-citation"
                    onClick={() => jumpToCitation(item.link)}
                  >
                    <div>
                      <strong>
                        [{index + 1}] {item.source || 'Извор'}{item.created_at ? ` · ${formatRelativeTime(item.created_at)}` : ''}
                      </strong>
                      <span>{item.title || 'Отвори го поврзаниот извор'}</span>
                      {item.snippet && <small>{item.snippet}</small>}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {Array.isArray(result.related_questions) && result.related_questions.length > 0 && (
            <div className="ask-evidence-block">
              <h4 className="ask-section-title">Прашај следно</h4>
              <div className="ask-suggestions">
                {result.related_questions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className="ask-suggestion"
                    onClick={() => void submitQuestion(item)}
                    disabled={isLoading}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
