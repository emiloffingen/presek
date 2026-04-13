import React, { useEffect, useRef, useState } from 'react';
import { Loader2, MessageCircle, Send, ShieldCheck, TriangleAlert, GitCompareArrows, Link2, Share2 } from 'lucide-react';
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

type HistoryEntry = {
  question: string;
  result: AskPresekResponse;
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

const CONFIDENCE_EXPLANATIONS: Record<string, (citationCount: number) => string> = {
  high: (n) => n >= 2 ? `${n} извори се согласуваат` : 'Поткрепено со силен доказ',
  medium: (n) => n >= 2 ? `${n} извори, делумно согласни` : 'Ограничена поткрепа',
  low: (n) => n >= 2 ? `${n} извори со спротивставени информации` : 'Само 1 извор',
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

function SkeletonResult() {
  return (
    <div className="ask-result ask-skeleton" aria-busy="true" aria-label="Се вчитува одговор...">
      <div className="ask-result-head">
        <div className="ask-skeleton-line" style={{ width: '55%', height: '0.7rem' }} />
        <div className="ask-skeleton-line" style={{ width: '20%', height: '0.6rem' }} />
      </div>
      <div className="ask-skeleton-line" style={{ width: '100%', height: '0.65rem' }} />
      <div className="ask-skeleton-block">
        <div className="ask-skeleton-line" style={{ width: '100%' }} />
        <div className="ask-skeleton-line" style={{ width: '92%' }} />
        <div className="ask-skeleton-line" style={{ width: '78%' }} />
      </div>
      <div className="ask-skeleton-block">
        <div className="ask-skeleton-line" style={{ width: '35%', height: '0.65rem' }} />
        <div className="ask-skeleton-line" style={{ width: '88%' }} />
        <div className="ask-skeleton-line" style={{ width: '70%' }} />
      </div>
    </div>
  );
}

function ResultBlock({ result, question, clusterId }: { result: AskPresekResponse; question: string; clusterId: string }) {
  const [copied, setCopied] = useState(false);
  const confidenceTone = String(result.confidence || '').toLowerCase();
  const confidenceLabel = CONFIDENCE_LABELS[confidenceTone] || 'Проверка во текстот';
  const citationCount = Array.isArray(result.citations) ? result.citations.length : 0;
  const confidenceExplain = CONFIDENCE_EXPLANATIONS[confidenceTone]?.(citationCount) || '';

  function jumpToCitation(link?: string) {
    if (!link) return;
    const target = document.querySelector<HTMLElement>(`[data-article-link="${encodeURIComponent(link)}"]`);
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.classList.add('ask-citation-targeted');
    window.setTimeout(() => target.classList.remove('ask-citation-targeted'), 2200);
  }

  function shareAnswer() {
    const url = new URL(window.location.href);
    url.searchParams.set('ask', question);
    navigator.clipboard.writeText(url.toString()).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="ask-result" aria-live="polite">
      <div className="ask-result-head">
        <strong className="nyt-section-label tracking-[0.18em]">Што можеме да кажеме сега</strong>
        <div className="ask-confidence-group">
          <span className={`ask-confidence ask-confidence-${confidenceTone || 'medium'}`} aria-label={`Ниво на сигурност: ${confidenceLabel}`}>
            {confidenceLabel}
          </span>
          {confidenceExplain && (
            <span className="ask-confidence-why">{confidenceExplain}</span>
          )}
        </div>
      </div>

      <div className="ask-scope-row">
        <p className="ask-scope-note">
          {clusterId === 'frontpage'
            ? 'Одговорот е составен од денешните вести на насловната страница.'
            : 'Овој одговор е составен само од изворите во овој кластер.'}
        </p>
        <button type="button" className="ask-share-btn" onClick={shareAnswer} aria-label="Сподели го одговорот">
          <Share2 size={12} />
          {copied ? 'Копирано!' : 'Сподели'}
        </button>
      </div>

      <p className="ask-answer">{result.answer || result.response}</p>

      {Array.isArray(result.citations) && result.citations.length > 0 && (
        <div className="ask-inline-citations" aria-label="Цитати">
          <span className="ask-inline-citations-label">Поткрепено со</span>
          {result.citations.map((item, index) => (
            <button
              type="button"
              key={`inline-${item.link || item.title || item.source || index}`}
              className="ask-inline-citation"
              onClick={() => jumpToCitation(item.link)}
              aria-label={`Скокни до извор ${index + 1}: ${item.source || ''}`}
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
    </div>
  );
}

export default function AskPresekPanel({ clusterId, suggestions, initialQuestion = '' }: Props) {
  const [question, setQuestion] = useState(initialQuestion);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const autoAskedRef = useRef(false);
  const resultRef = useRef<HTMLFormElement>(null);

  async function submitQuestion(nextQuestion?: string) {
    const normalized = normalizeQuestion(nextQuestion ?? question);
    if (!normalized || isLoading) return;

    setQuestion('');
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

      setHistory((prev) => [...prev, { question: normalized, result: payload as AskPresekResponse }]);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 100);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не успеав да добијам одговор.');
    } finally {
      setIsLoading(false);
    }
  }

  const latestResult = history.length > 0 ? history[history.length - 1].result : null;
  const followUpSuggestions = latestResult?.related_questions;

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

      {history.length === 0 && (
        <div className="ask-suggestions" aria-label="Предложени прашања">
          {suggestions.map((item) => (
            <button
              key={item}
              type="button"
              className="ask-suggestion"
              onClick={() => void submitQuestion(item)}
              disabled={isLoading}
              aria-label={`Прашај: ${item}`}
            >
              {item}
            </button>
          ))}
        </div>
      )}

      {history.length > 0 && (
        <div className="ask-history">
          {history.map((entry, idx) => (
            <div key={idx} className="ask-turn">
              <div className="ask-turn-question">
                <MessageCircle size={12} />
                <span>{entry.question}</span>
              </div>
              <ResultBlock result={entry.result} question={entry.question} clusterId={clusterId} />
            </div>
          ))}
        </div>
      )}

      {isLoading && <SkeletonResult />}

      {error && <p className="ask-error" role="alert">{error}</p>}

      {Array.isArray(followUpSuggestions) && followUpSuggestions.length > 0 && !isLoading && (
        <div className="ask-evidence-block">
          <h4 className="ask-section-title">Прашај следно</h4>
          <div className="ask-suggestions">
            {followUpSuggestions.map((item) => (
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

      <form
        className="ask-form"
        ref={resultRef}
        onSubmit={(event) => {
          event.preventDefault();
          void submitQuestion();
        }}
      >
        <textarea
          className="ask-input"
          rows={history.length > 0 ? 2 : 4}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={history.length > 0 ? 'Прашај следно...' : 'На пример: Кои факти се повторуваат кај повеќе извори?'}
          maxLength={500}
          aria-label="Вашето прашање"
        />
        <button
          type="submit"
          className="ask-submit"
          disabled={isLoading || !normalizeQuestion(question)}
          aria-label="Испрати прашање"
        >
          {isLoading ? <Loader2 size={14} className="animate-spin" aria-hidden="true" /> : <Send size={14} aria-hidden="true" />}
          Одговор
        </button>
      </form>
    </div>
  );
}
