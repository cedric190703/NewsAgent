import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Newspaper,
  Play,
  Loader2,
  Moon,
  Sun,
  SlidersHorizontal,
  Download,
  History,
  Trash2,
  AlertCircle,
  X,
  Sparkles,
  Square,
  Wifi,
  WifiOff,
  Database,
  CalendarClock,
} from "lucide-react";

import {
  ApiError,
  type ArticleSummary,
  type AppStatus,
  type ExportFormat,
  type GoodNewsMode,
  type Length,
  type Newsletter,
  type NodeEvent,
  type RunConfig,
  type Tone,
  type Topology,
  addBookmark,
  createRun,
  deleteRun,
  exportRun,
  getRun,
  getStatus,
  getTopology,
  listBookmarks,
  listRuns,
  removeBookmark,
  streamRunEvents,
  type RunHistoryItem,
} from "./services/api";
import { PipelineView } from "./components/PipelineView";
import { NewsletterView } from "./components/NewsletterView";
import { SchedulesPanel } from "./components/SchedulesPanel";
import { FeedbackBar } from "./components/FeedbackBar";
import { DotPattern } from "./components/ui/dot-pattern";
import { AnimatedGradientText } from "./components/ui/animated-gradient-text";
import { ShimmerButton } from "./components/ui/shimmer-button";
import { BorderBeam } from "./components/ui/border-beam";
import { NumberTicker } from "./components/ui/number-ticker";
import { cn } from "./lib/utils";

const MODES: { value: GoodNewsMode; label: string }[] = [
  { value: "uplifting", label: "Uplifting" },
  { value: "balanced", label: "Balanced" },
  { value: "high_signal", label: "High-signal" },
];

const TONES: { value: Tone; label: string }[] = [
  { value: "neutral", label: "Neutral" },
  { value: "warm", label: "Warm" },
  { value: "punchy", label: "Punchy" },
  { value: "analytical", label: "Analytical" },
];

const LENGTHS: { value: Length; label: string }[] = [
  { value: "brief", label: "Brief" },
  { value: "standard", label: "Standard" },
  { value: "deep", label: "Deep" },
];

const STATUS_COLOR: Record<string, string> = {
  done: "text-emerald-600 dark:text-emerald-400",
  running: "text-brand-600 dark:text-brand-400",
  partial: "text-amber-600 dark:text-amber-400",
  error: "text-red-500",
  cancelled: "text-slate-400",
};

/** ApiError already carries a readable per-field message; fall back for the rest. */
function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export function App() {
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem("dark-mode");
    return saved === "true" || (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches);
  });

  const [theme, setTheme] = useState("");
  const [mode, setMode] = useState<GoodNewsMode>("balanced");
  const [tone, setTone] = useState<Tone>("neutral");
  const [length, setLength] = useState<Length>("standard");
  const [subtopicCount, setSubtopicCount] = useState(3);
  const [maxSources, setMaxSources] = useState(8);
  const [factcheck, setFactcheck] = useState(true);
  const [showFilters, setShowFilters] = useState(false);

  const [topology, setTopology] = useState<Topology | null>(null);
  const [events, setEvents] = useState<NodeEvent[]>([]);
  const [newsletter, setNewsletter] = useState<Newsletter | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bookmarkedIds, setBookmarkedIds] = useState<Set<string>>(new Set());
  const [history, setHistory] = useState<RunHistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [showSchedules, setShowSchedules] = useState(false);
  const [activeTab, setActiveTab] = useState<"pipeline" | "newsletter">("pipeline");
  const [status, setStatus] = useState<AppStatus | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("dark-mode", String(dark));
  }, [dark]);

  useEffect(() => {
    getTopology().then(setTopology).catch(() => {});
    getStatus().then(setStatus).catch(() => {});
  }, []);

  const refreshHistory = useCallback(() => {
    listRuns().then(setHistory).catch(() => {});
  }, []);

  const handleBookmark = useCallback(
    async (article: ArticleSummary) => {
      if (!runId) return;
      const id = article.article_id;
      const saved = bookmarkedIds.has(id);

      // Update optimistically, then roll back if the server disagrees.
      setBookmarkedIds((prev) => {
        const next = new Set(prev);
        if (saved) next.delete(id);
        else next.add(id);
        return next;
      });

      try {
        if (saved) {
          await removeBookmark(runId, id);
        } else {
          await addBookmark(runId, id, article.url, article.headline, article.source_name);
        }
      } catch (err) {
        setBookmarkedIds((prev) => {
          const next = new Set(prev);
          if (saved) next.add(id);
          else next.delete(id);
          return next;
        });
        setError(describeError(err, "Could not update the bookmark"));
      }
    },
    [runId, bookmarkedIds],
  );

  const handleExport = useCallback(
    async (fmt: ExportFormat) => {
      if (!runId) return;
      try {
        const blob = await exportRun(runId, fmt);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `newsletter-${runId}.${fmt === "markdown" ? "md" : fmt}`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (err) {
        setError(describeError(err, "Export failed"));
      }
    },
    [runId],
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!theme.trim() || streaming) return;

    setError(null);
    setEvents([]);
    setNewsletter(null);
    setBookmarkedIds(new Set());
    setActiveTab("pipeline");

    try {
      const { run_id } = await createRun(currentConfig);
      setRunId(run_id);
      setStreaming(true);
      refreshHistory();

      abortRef.current = streamRunEvents(
        run_id,
        (evt) => {
          setEvents((prev) => [...prev, evt]);
        },
        (nl) => {
          setNewsletter(nl);
          setActiveTab("newsletter");
        },
        (msg) => setError(msg),
        () => {
          setStreaming(false);
          refreshHistory();
        },
      );
    } catch (err) {
      setError(describeError(err, "Failed to start run"));
      setStreaming(false);
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const loadHistoryRun = async (id: string) => {
    try {
      // Bookmarks are per-run and stored server-side, so a loaded run has to
      // fetch its own — otherwise every saved article looked unsaved.
      const [detail, bookmarks] = await Promise.all([getRun(id), listBookmarks(id)]);
      setRunId(id);
      setBookmarkedIds(new Set(bookmarks.map((bookmark) => bookmark.article_id)));
      if (detail.newsletter) {
        setNewsletter(detail.newsletter);
        setActiveTab("newsletter");
      } else {
        setNewsletter(null);
        setActiveTab("pipeline");
        setError(
          detail.error ?? `This run finished with status "${detail.status}" and has no newsletter.`,
        );
      }
      setEvents([]);
      setShowHistory(false);
    } catch (err) {
      setError(describeError(err, "Failed to load run"));
    }
  };

  const handleDeleteRun = async (id: string) => {
    try {
      await deleteRun(id);
      refreshHistory();
    } catch {
      // ignore
    }
  };

  const currentConfig: RunConfig = {
    theme: theme.trim(),
    good_news_mode: mode,
    tone,
    length,
    subtopic_count: subtopicCount,
    max_sources: maxSources,
    enable_factcheck: factcheck,
  };

  const startStreaming = (id: string) => {
    setRunId(id);
    setStreaming(true);
    setEvents([]);
    setNewsletter(null);
    setActiveTab("pipeline");
    abortRef.current = streamRunEvents(
      id,
      (evt) => setEvents((prev) => [...prev, evt]),
      (nl) => {
        setNewsletter(nl);
        setActiveTab("newsletter");
      },
      (msg) => setError(msg),
      () => {
        setStreaming(false);
        refreshHistory();
      },
    );
  };

  const totalArticles = newsletter?.sections.reduce((acc, s) => acc + s.items.length, 0) ?? 0;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div className="grid min-h-screen lg:grid-cols-[minmax(340px,400px)_minmax(0,1fr)] max-lg:grid-cols-1">
        {/* === Left Panel === */}
        <aside className="relative flex flex-col gap-6 border-r border-slate-200/80 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
          <DotPattern className="text-slate-200/50 dark:text-slate-700/30" width={20} height={20} cr={1} />

          <div className="relative flex items-center gap-3">
            <div className="inline-grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-purple-600 text-white shadow-lg shadow-brand-500/20">
              <Newspaper size={22} />
            </div>
            <div>
              <h1 className="text-lg font-bold">
                <AnimatedGradientText>Good News Agent</AnimatedGradientText>
              </h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">AI-powered newsletter pipeline</p>
            </div>
            <button
              onClick={() => setDark(!dark)}
              className="ml-auto rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 dark:hover:bg-slate-800"
              aria-label="Toggle dark mode"
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>

          <form onSubmit={handleSubmit} className="relative flex flex-col gap-4">
            <div>
              <label className="label-text" htmlFor="theme">Theme / Topic</label>
              <input
                id="theme"
                className="input-field"
                type="text"
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
                placeholder="e.g. ocean restoration, AI in healthcare…"
                disabled={streaming}
              />
            </div>

            <button
              type="button"
              onClick={() => setShowFilters(!showFilters)}
              className="flex items-center gap-2 text-sm font-medium text-slate-500 transition hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
            >
              <SlidersHorizontal size={15} />
              {showFilters ? "Hide" : "Show"} filters
            </button>

            <AnimatePresence>
              {showFilters && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="flex flex-col gap-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-900/50">
                    <div>
                      <label className="label-text">Good news mode</label>
                      <div className="flex gap-1.5">
                        {MODES.map((m) => (
                          <button
                            key={m.value}
                            type="button"
                            onClick={() => setMode(m.value)}
                            className={cn("chip", mode === m.value ? "chip-active" : "chip-idle")}
                          >
                            {m.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div>
                      <label className="label-text">Tone</label>
                      <div className="flex flex-wrap gap-1.5">
                        {TONES.map((t) => (
                          <button
                            key={t.value}
                            type="button"
                            onClick={() => setTone(t.value)}
                            className={cn("chip", tone === t.value ? "chip-active" : "chip-idle")}
                          >
                            {t.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div>
                      <label className="label-text">Length</label>
                      <div className="flex gap-1.5">
                        {LENGTHS.map((l) => (
                          <button
                            key={l.value}
                            type="button"
                            onClick={() => setLength(l.value)}
                            className={cn("chip", length === l.value ? "chip-active" : "chip-idle")}
                          >
                            {l.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div>
                      <label className="label-text">
                        Sub-topics: <span className="font-bold text-brand-600">{subtopicCount}</span>
                      </label>
                      <input
                        type="range"
                        min={1}
                        max={6}
                        value={subtopicCount}
                        onChange={(e) => setSubtopicCount(Number(e.target.value))}
                        className="w-full accent-brand-600"
                      />
                    </div>

                    <div>
                      <label className="label-text">
                        Max sources: <span className="font-bold text-brand-600">{maxSources}</span>
                      </label>
                      <input
                        type="range"
                        min={3}
                        max={20}
                        value={maxSources}
                        onChange={(e) => setMaxSources(Number(e.target.value))}
                        className="w-full accent-brand-600"
                      />
                    </div>

                    <label className="flex items-center gap-2 text-sm font-medium text-slate-600 dark:text-slate-300">
                      <input
                        type="checkbox"
                        checked={factcheck}
                        onChange={(e) => setFactcheck(e.target.checked)}
                        className="h-4 w-4 accent-brand-600"
                      />
                      Enable fact-check & dedup
                    </label>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="flex items-start gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400"
                >
                  <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                  <span>{error}</span>
                  <button onClick={() => setError(null)} className="ml-auto">
                    <X size={14} />
                  </button>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="flex gap-2">
              <ShimmerButton
                type="submit"
                disabled={!theme.trim() || streaming}
                borderRadius="12px"
                background="rgba(79, 70, 229, 1)"
                className="flex-1"
              >
                {streaming ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Generating…
                  </>
                ) : (
                  <>
                    <Play size={16} />
                    Generate newsletter
                  </>
                )}
              </ShimmerButton>
              {streaming && (
                <motion.button
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  type="button"
                  onClick={handleCancel}
                  className="inline-flex items-center gap-2 rounded-xl border border-red-200 px-4 py-2.5 text-sm font-medium text-red-600 transition hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20"
                >
                  <Square size={15} fill="currentColor" />
                  Cancel
                </motion.button>
              )}
            </div>
          </form>

          {/* Data source indicator */}
          {status && (
            <div className={cn(
              "relative flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium",
              status.using_real_data
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300"
                : "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300"
            )}>
              {status.using_real_data ? <Wifi size={14} /> : <WifiOff size={14} />}
              {status.using_real_data
                ? `Live data · ${status.search_providers.join(", ")}`
                : "Mock data — add API keys for real sources"}
              <span className="ml-auto flex items-center gap-1 text-slate-400">
                <Database size={12} />
                {status.llm_model}
              </span>
            </div>
          )}

          <div className="relative mt-auto flex items-center gap-2">
            <button
              onClick={() => {
                refreshHistory();
                setShowHistory(!showHistory);
                setShowSchedules(false);
              }}
              className={cn("btn-ghost", showHistory && "bg-slate-100 dark:bg-slate-800")}
            >
              <History size={15} />
              History
            </button>
            <button
              onClick={() => {
                setShowSchedules(!showSchedules);
                setShowHistory(false);
              }}
              className={cn("btn-ghost", showSchedules && "bg-slate-100 dark:bg-slate-800")}
              title={
                status?.scheduler_running
                  ? "Recurring newsletters run on the server"
                  : "The server scheduler is disabled"
              }
            >
              <CalendarClock size={15} />
              Schedules
            </button>
            {newsletter && runId && (
              <div className="ml-auto flex items-center gap-1">
                <button onClick={() => handleExport("markdown")} className="btn-ghost" title="Export Markdown">
                  <Download size={15} />
                  MD
                </button>
                <button onClick={() => handleExport("html")} className="btn-ghost" title="Export HTML">
                  HTML
                </button>
                <button onClick={() => handleExport("pdf")} className="btn-ghost" title="Export PDF">
                  PDF
                </button>
              </div>
            )}
          </div>

          <AnimatePresence>
            {showHistory && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="relative flex flex-col gap-1.5 overflow-hidden"
              >
                {history.length === 0 ? (
                  <p className="text-xs text-slate-400">No runs yet.</p>
                ) : (
                  history.map((item) => (
                    <div
                      key={item.run_id}
                      className="flex items-center gap-2 rounded-xl border border-slate-200 p-2.5 text-xs dark:border-slate-700"
                    >
                      <button
                        onClick={() => loadHistoryRun(item.run_id)}
                        className="min-w-0 flex-1 text-left transition hover:text-brand-600"
                      >
                        <div className="truncate font-medium">
                          {item.config?.theme ?? "Untitled"}
                        </div>
                        <div className="flex items-center gap-1.5 text-slate-400">
                          <span>{new Date(item.created_at).toLocaleDateString()}</span>
                          <span className={cn("font-medium", STATUS_COLOR[item.status])}>
                            {item.status}
                          </span>
                          {item.source.startsWith("schedule:") && (
                            <CalendarClock size={10} aria-label="scheduled run" />
                          )}
                        </div>
                      </button>
                      <button
                        onClick={() => handleDeleteRun(item.run_id)}
                        className="text-slate-300 transition hover:text-red-500"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  ))
                )}
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {showSchedules && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="relative overflow-hidden"
              >
                <SchedulesPanel currentConfig={currentConfig} onRunStarted={startStreaming} />
              </motion.div>
            )}
          </AnimatePresence>
        </aside>

        {/* === Right Panel === */}
        <main className="flex flex-col overflow-y-auto max-h-screen max-lg:min-h-[60vh]">
          {/* Tab bar */}
          <div className="sticky top-0 z-10 flex items-center gap-1 border-b border-slate-200 bg-white/80 px-6 py-3 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/80">
            <button
              onClick={() => setActiveTab("pipeline")}
              className={cn(
                "rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all",
                activeTab === "pipeline"
                  ? "bg-brand-600 text-white shadow-sm shadow-brand-600/20"
                  : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
              )}
            >
              Pipeline
            </button>
            <button
              onClick={() => setActiveTab("newsletter")}
              className={cn(
                "rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all",
                activeTab === "newsletter"
                  ? "bg-brand-600 text-white shadow-sm shadow-brand-600/20"
                  : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
              )}
              disabled={!newsletter}
            >
              Newsletter
              {newsletter && (
                <span className="ml-1.5 rounded-full bg-white/20 px-1.5 text-xs">
                  {totalArticles}
                </span>
              )}
            </button>
            {streaming && (
              <div className="ml-auto flex items-center gap-2 text-xs text-brand-600">
                <Loader2 size={14} className="animate-spin" />
                <NumberTicker value={events.length} className="text-brand-600" /> events
              </div>
            )}
          </div>

          <div className="flex-1 p-6">
            {activeTab === "pipeline" ? (
              <div className="mx-auto max-w-md">
                <div className="mb-5 flex items-center gap-2">
                  <Sparkles size={16} className="text-brand-500" />
                  <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">
                    LangGraph Pipeline
                  </h2>
                </div>
                <PipelineView topology={topology} events={events} active={streaming} />
                {streaming && events.length === 0 && (
                  <div className="mt-6 flex flex-col items-center gap-3 text-slate-400">
                    <div className="flex gap-1.5">
                      {[0, 1, 2].map((i) => (
                        <motion.div
                          key={i}
                          animate={{ opacity: [0.3, 1, 0.3] }}
                          transition={{ duration: 1.2, delay: i * 0.2, repeat: Infinity }}
                          className="h-2 w-2 rounded-full bg-brand-500"
                        />
                      ))}
                    </div>
                    <p className="text-xs">Waiting for first event from the pipeline…</p>
                  </div>
                )}
                {events.length === 0 && !streaming && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.3 }}
                    className="mt-8 text-center"
                  >
                    <div className="relative mx-auto mb-4 grid h-16 w-16 place-items-center rounded-2xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
                      <Newspaper size={28} className="text-slate-300 dark:text-slate-600" />
                      <BorderBeam size={40} duration={8} colorFrom="#6366f1" colorTo="#a855f7" />
                    </div>
                    <p className="text-sm text-slate-400">
                      Enter a theme and click <strong className="text-slate-600 dark:text-slate-300">Generate</strong> to see the pipeline execute live.
                    </p>
                  </motion.div>
                )}
              </div>
            ) : newsletter ? (
              <div className="flex flex-col gap-6">
                <NewsletterView
                  newsletter={newsletter}
                  onBookmark={handleBookmark}
                  bookmarkedIds={bookmarkedIds}
                />
                {runId && !streaming && <FeedbackBar key={runId} runId={runId} />}
              </div>
            ) : (
              <div className="grid place-items-center py-20 text-center">
                <div className="flex flex-col items-center gap-3 text-slate-400">
                  <Newspaper size={32} />
                  <h2 className="text-lg font-bold text-slate-500 dark:text-slate-300">
                    Your newsletter will appear here
                  </h2>
                  <p className="max-w-xs text-sm">
                    The pipeline is working. Once the composer finishes, your curated newsletter will show up in this view.
                  </p>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
