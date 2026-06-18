import { AlertCircle, ExternalLink, FileText, Lightbulb, ShieldCheck } from "lucide-react";

import type { NewsQueryResponse } from "../services/api";

interface ResultPanelProps {
  result: NewsQueryResponse | null;
}

export function ResultPanel({ result }: ResultPanelProps) {
  if (!result) {
    return (
      <section className="empty-state">
        <FileText size={28} />
        <h2>Ready for a briefing</h2>
        <p>Submit a topic to generate a structured professional news answer.</p>
      </section>
    );
  }

  return (
    <section className="result-panel">
      <div className="result-panel__header">
        <div>
          <span className="eyebrow">{result.output_format.replace("_", " ")}</span>
          <h2>{result.topic}</h2>
        </div>
        <span className="confidence">Confidence: {result.confidence}</span>
      </div>

      <section className="result-section">
        <h3>Executive Summary</h3>
        <p>{result.executive_summary}</p>
      </section>

      <section className="result-section">
        <h3>Key Points</h3>
        <ul>
          {result.key_points.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
      </section>

      <section className="result-section">
        <h3>Analysis</h3>
        <p className="analysis-text">{result.analysis}</p>
      </section>

      <section className="result-section">
        <h3>Sources</h3>
        <div className="source-list">
          {result.sources.map((source) => (
            <article className="source-item" key={`${source.source_type}-${source.title}`}>
              <div>
                <strong>{source.title}</strong>
                <span>{source.publisher ?? source.source_type}</span>
              </div>
              {source.url ? (
                <a href={source.url} target="_blank" rel="noreferrer" aria-label={source.title}>
                  <ExternalLink size={16} />
                </a>
              ) : null}
            </article>
          ))}
        </div>
      </section>

      <section className="result-grid">
        <div className="compact-panel">
          <h3>
            <ShieldCheck size={16} />
            Critic Notes
          </h3>
          <ul>
            {result.critic_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
        <div className="compact-panel">
          <h3>
            <Lightbulb size={16} />
            Follow-ups
          </h3>
          <ul>
            {result.suggested_followups.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </div>
      </section>

      {result.sources.length === 0 ? (
        <p className="inline-warning">
          <AlertCircle size={16} />
          Citations are hidden for this result.
        </p>
      ) : null}
    </section>
  );
}
