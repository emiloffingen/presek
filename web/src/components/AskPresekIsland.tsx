import React, { useMemo, useState } from 'react';
import { LoaderCircle, MessageCircleMore, ArrowUpRight, Quote } from 'lucide-react';

type Citation = {
  source: string;
  title: string;
  link?: string;
  created_at?: string;
  snippet?: string;
};

type AskResponse = {
  answer: string;
  citations: Citation[];
  related_questions: string[];
  confidence: 'high' | 'medium' | 'low';
  confirmed_points: string[];
  unclear_points: string[];
  source_differences?: string;
};

type HistoryItem = {
  question: string;
  result: AskResponse;
};

const confidenceLabels: Record<string, string> = {
  high: 'Висока сигурност',
  medium: 'Средна сигурност',
  low: 'Ограничена сигурност',
};

export default function AskPresekIsland({
  clusterId,
  suggestedQuestions,
}: {
  clusterId: string;
  suggestedQuestions: string[];
}) {
  const API_URL =
    typeof window !== 'undefined'
      ? '/api'
      : import.meta.env.PUBLIC_API_URL || 'http://127.0.0.1:5000/api';

  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<AskResponse | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  const visibleSuggestions = useMemo(
    () => suggestedQuestions.filter(Boolean).slice(0, 3),
    [suggestedQuestions]
  );

  const submitQuestion = async (nextQuestion?: string) => {
    const finalQuestion = (nextQuestion ?? question).trim();
    if (!finalQuestion || loading) return;

    setLoading(true);
    setError('');

    try {
      let res = await fetch(`${API_URL}/chat_cluster`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ cluster_id: clusterId, query: finalQuestion }),
      });

      if (!res.ok && (res.status === 404 || res.status === 405)) {
        res = await fetch(`${API_URL}/cluster/${clusterId}/ask`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ question: finalQuestion }),
        });
      }

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || data?.message || 'Неуспешно прашање.');
      }

      const nextResult = {
        answer: data.answer || '',
        citations: Array.isArray(data.citations) ? data.citations : [],
        related_questions: Array.isArray(data.related_questions) ? data.related_questions : [],
        confidence: data.confidence || 'medium',
        confirmed_points: Array.isArray(data.confirmed_points) ? data.confirmed_points : [],
        unclear_points: Array.isArray(data.unclear_points) ? data.unclear_points : [],
        source_differences: data.source_differences || '',
      } as AskResponse;

      setQuestion(finalQuestion);
      setResult(nextResult);
      setHistory((prev) => {
        const next = prev.filter((item) => item.question !== finalQuestion);
        next.unshift({ question: finalQuestion, result: nextResult });
        return next.slice(0, 4);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Се појави грешка.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ask-presek">
      <p className="rail-copy ask-intro">
        Имате прашање за оваа вест? Пресек одговара врз основа на споредените извори во овој кластер.
      </p>

      <div className="ask-suggestions">
        {visibleSuggestions.map((item) => (
          <button
            key={item}
            type="button"
            className="ask-suggestion"
            onClick={() => {
              setQuestion(item);
              submitQuestion(item);
            }}
          >
            {item}
          </button>
        ))}
      </div>

      <div className="ask-form">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Прашајте што е ново, што е спорно или како се разликуваат изворите..."
          className="ask-input"
          rows={4}
        />
        <button type="button" className="ask-submit" onClick={() => submitQuestion()} disabled={loading}>
          {loading ? (
            <>
              <LoaderCircle size={14} className="animate-spin" /> Обработувам
            </>
          ) : (
            <>
              <MessageCircleMore size={14} /> Прашај
            </>
          )}
        </button>
      </div>

      {error && <p className="ask-error">{error}</p>}

      {result && (
        <div className="ask-result">
          <div className="ask-result-head">
            <span className="nyt-section-label text-muted-foreground">Одговор</span>
            <span className="ask-confidence">{confidenceLabels[result.confidence] || confidenceLabels.medium}</span>
          </div>
          <p className="ask-answer">{result.answer}</p>

          {result.confirmed_points.length > 0 && (
            <div className="ask-evidence-block">
              <p className="nyt-section-label text-muted-foreground">Потврдено од изворите</p>
              <ul className="ask-evidence-list">
                {result.confirmed_points.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {result.unclear_points.length > 0 && (
            <div className="ask-evidence-block">
              <p className="nyt-section-label text-muted-foreground">Што останува нејасно</p>
              <ul className="ask-evidence-list ask-evidence-list-muted">
                {result.unclear_points.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {result.source_differences && (
            <div className="ask-source-differences">
              <p className="nyt-section-label text-muted-foreground">Разлики меѓу изворите</p>
              <p>{result.source_differences}</p>
            </div>
          )}

          {result.citations.length > 0 && (
            <div className="ask-citations">
              <p className="nyt-section-label text-muted-foreground">Поткрепено со</p>
              <div className="ask-citation-list">
                {result.citations.map((citation) => (
                  <a
                    key={`${citation.source}-${citation.title}`}
                    href={citation.link || '#'}
                    target={citation.link ? '_blank' : undefined}
                    rel={citation.link ? 'noopener noreferrer' : undefined}
                    className="ask-citation"
                  >
                    <Quote size={12} />
                    <div>
                      <strong>{citation.source}</strong>
                      <span>{citation.title}</span>
                      {citation.snippet && <small>{citation.snippet}</small>}
                    </div>
                    {citation.link && <ArrowUpRight size={12} />}
                  </a>
                ))}
              </div>
            </div>
          )}

          {result.related_questions.length > 0 && (
            <div className="ask-followups">
              <p className="nyt-section-label text-muted-foreground">Побарај и</p>
              <div className="ask-suggestions">
                {result.related_questions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className="ask-suggestion"
                    onClick={() => {
                      setQuestion(item);
                      submitQuestion(item);
                    }}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {history.length > 1 && (
        <div className="ask-history">
          <p className="nyt-section-label text-muted-foreground">Последни прашања</p>
          <div className="ask-history-list">
            {history.slice(1).map((item) => (
              <button
                key={item.question}
                type="button"
                className="ask-history-item"
                onClick={() => {
                  setQuestion(item.question);
                  setResult(item.result);
                  setError('');
                }}
              >
                <strong>{item.question}</strong>
                <span>{item.result.answer}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
