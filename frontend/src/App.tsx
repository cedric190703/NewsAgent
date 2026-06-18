import { Loader2, Newspaper, Send } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import { ResultPanel } from "./components/ResultPanel";
import { SourceToggle } from "./components/SourceToggle";
import {
  type NewsQueryResponse,
  type OutputFormat,
  type SourceType,
  queryNews,
} from "./services/api";

const sourceOptions: Array<{ label: string; value: SourceType }> = [
  { label: "RSS", value: "rss" },
  { label: "Web", value: "web" },
  { label: "Knowledge Base", value: "knowledge_base" },
];

const outputOptions: Array<{ label: string; value: OutputFormat }> = [
  { label: "Briefing", value: "briefing" },
  { label: "Analysis", value: "analysis" },
  { label: "Newsletter", value: "newsletter" },
  { label: "Sources", value: "source_list" },
];

export function App() {
  const [topic, setTopic] = useState("AI regulation in Europe");
  const [section, setSection] = useState("Technology");
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("briefing");
  const [sources, setSources] = useState<SourceType[]>(["rss"]);
  const [depth, setDepth] = useState(3);
  const [includeCitations, setIncludeCitations] = useState(true);
  const [result, setResult] = useState<NewsQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const canSubmit = useMemo(() => topic.trim().length >= 3 && sources.length > 0, [topic, sources]);

  function toggleSource(value: SourceType) {
    setSources((current) =>
      current.includes(value)
        ? current.filter((source) => source !== value)
        : [...current, value],
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await queryNews({
        topic,
        section,
        output_format: outputFormat,
        sources,
        depth,
        include_citations: includeCitations,
      });
      setResult(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unexpected request failure.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="query-panel">
        <div className="brand">
          <span className="brand__mark">
            <Newspaper size={22} />
          </span>
          <div>
            <h1>AI News Agent</h1>
            <p>Professional multi-source briefings</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="query-form">
          <label>
            Topic
            <textarea
              value={topic}
              onChange={(event) => setTopic(event.target.value)}
              rows={4}
              placeholder="Ask for a topic, trend, sector, company, or theme"
            />
          </label>

          <label>
            Section
            <input
              value={section}
              onChange={(event) => setSection(event.target.value)}
              placeholder="Technology, finance, geopolitics..."
            />
          </label>

          <fieldset>
            <legend>Output</legend>
            <div className="segmented-control">
              {outputOptions.map((option) => (
                <button
                  className={outputFormat === option.value ? "is-active" : ""}
                  key={option.value}
                  type="button"
                  onClick={() => setOutputFormat(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset>
            <legend>Sources</legend>
            <div className="source-toggle-group">
              {sourceOptions.map((option) => (
                <SourceToggle
                  key={option.value}
                  label={option.label}
                  value={option.value}
                  selected={sources.includes(option.value)}
                  onChange={toggleSource}
                />
              ))}
            </div>
          </fieldset>

          <label>
            Depth
            <input
              type="range"
              min="1"
              max="5"
              value={depth}
              onChange={(event) => setDepth(Number(event.target.value))}
            />
            <span className="range-value">{depth}</span>
          </label>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={includeCitations}
              onChange={(event) => setIncludeCitations(event.target.checked)}
            />
            Include citations
          </label>

          <button className="submit-button" disabled={!canSubmit || isLoading} type="submit">
            {isLoading ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
            Generate briefing
          </button>

          {error ? <p className="form-error">{error}</p> : null}
        </form>
      </aside>

      <ResultPanel result={result} />
    </main>
  );
}
