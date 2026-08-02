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
  Plus,
  LogOut,
  Users,
  Send,
  RefreshCw,
  HelpCircle,
  Layers,
} from "lucide-react";

import {
  type ArticleSummary,
  type AppStatus,
  type GoodNewsMode,
  type Length,
  type Newsletter,
  type NodeEvent,
  type RunConfig,
  type Tone,
  type Topology,
  type NewsletterListItem,
  addBookmark,
  createRun,
  deleteRun,
  exportRun,
  getRun,
  getStatus,
  getTopology,
  listRuns,
  listNewsletters,
  listSubscribers,
  addSubscriber,
  deleteSubscriber,
  sendNewsletter,
  listGroups,
  createGroup,
  deleteGroup,
  addSubscriberToGroup,
  removeSubscriberFromGroup,
  removeBookmark,
  streamRunEvents,
  listQuestions,
  createQuestion,
  deleteQuestion,
  batchCreateRuns,
  type BatchRunResult,
  type RunHistoryItem,
  type Subscriber,
  type Group,
  type Question,
} from "../services/api";
import { PipelineView } from "./PipelineView";
import { Logo } from "./Logo";
import { DotPattern } from "./ui/dot-pattern";
import { ShimmerButton } from "./ui/shimmer-button";
import { BorderBeam } from "./ui/border-beam";
import { NumberTicker } from "./ui/number-ticker";
import { cn } from "../lib/utils";

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

export function AdminView({ dark, onToggleDark, adminKey, onLogout }: {
  dark: boolean;
  onToggleDark: () => void;
  adminKey: string;
  onLogout: () => void;
}) {
  const [theme, setTheme] = useState("");
  const [audience, setAudience] = useState("");
  const [mode, setMode] = useState<GoodNewsMode>("balanced");
  const [tone, setTone] = useState<Tone>("neutral");
  const [length, setLength] = useState<Length>("standard");
  const [subtopicCount, setSubtopicCount] = useState(4);
  const [maxSources, setMaxSources] = useState(20);
  const [factcheck, setFactcheck] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [customFeeds, setCustomFeeds] = useState("");
  const [customUrls, setCustomUrls] = useState("");

  const [topology, setTopology] = useState<Topology | null>(null);
  const [events, setEvents] = useState<NodeEvent[]>([]);
  const [newsletter, setNewsletter] = useState<Newsletter | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bookmarkedIds, setBookmarkedIds] = useState<Set<string>>(new Set());
  const [history, setHistory] = useState<RunHistoryItem[]>([]);
  const [activeTab, setActiveTab] = useState<"pipeline" | "configs">("pipeline");
  const [status, setStatus] = useState<AppStatus | null>(null);
  const [subscribers, setSubscribers] = useState<Subscriber[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [newSubEmail, setNewSubEmail] = useState("");
  const [newSubName, setNewSubName] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [newGroupDesc, setNewGroupDesc] = useState("");
  const [newGroupTheme, setNewGroupTheme] = useState("");
  const [batchStatus, setBatchStatus] = useState<string | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [selectedGroupIds, setSelectedGroupIds] = useState<Set<string>>(new Set());
  const [sendStatus, setSendStatus] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [sidebarTab, setSidebarTab] = useState<"generate" | "subscribers" | "questions" | "history">("generate");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [newQuestionText, setNewQuestionText] = useState("");
  const [newQuestionOptions, setNewQuestionOptions] = useState<{ text: string; group_name: string }[]>([
    { text: "", group_name: "" },
    { text: "", group_name: "" },
  ]);

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

  const refreshSubscribers = useCallback(() => {
    listSubscribers().then(setSubscribers).catch(() => {});
  }, []);

  const refreshGroups = useCallback(() => {
    listGroups().then(setGroups).catch(() => {});
  }, []);

  const refreshQuestions = useCallback(() => {
    listQuestions().then(setQuestions).catch(() => {});
  }, []);

  const handleBookmark = useCallback(
    async (article: ArticleSummary) => {
      if (!runId) return;
      const id = article.article_id;
      if (bookmarkedIds.has(id)) {
        await removeBookmark(runId, id);
        setBookmarkedIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      } else {
        await addBookmark(runId, id, article.url, article.headline, article.source_name);
        setBookmarkedIds((prev) => new Set(prev).add(id));
      }
    },
    [runId, bookmarkedIds],
  );

  const handleExport = useCallback(
    async (fmt: "markdown" | "html" | "pdf") => {
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
        setError(err instanceof Error ? err.message : "Export failed");
      }
    },
    [runId],
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!theme.trim() || streaming || !adminKey.trim()) return;

    setError(null);
    setEvents([]);
    setNewsletter(null);
    setBookmarkedIds(new Set());
    setActiveTab("pipeline");
    localStorage.setItem("admin-key", adminKey);

    const config: RunConfig = {
      theme: theme.trim(),
      audience: audience.trim() || undefined,
      good_news_mode: mode,
      tone,
      length,
      subtopic_count: subtopicCount,
      max_sources: maxSources,
      enable_factcheck: factcheck,
      custom_feeds: customFeeds.trim() ? customFeeds.trim().split(/\s+/).filter(Boolean) : undefined,
      custom_urls: customUrls.trim() ? customUrls.trim().split(/\s+/).filter(Boolean) : undefined,
    };

    try {
      const { run_id } = await createRun(config, adminKey);
      setRunId(run_id);
      setStreaming(true);
      refreshHistory();

      abortRef.current = streamRunEvents(
        run_id,
        (evt) => setEvents((prev) => [...prev, evt]),
        (nl) => { setNewsletter(nl); },
        (msg) => setError(msg),
        () => { setStreaming(false); refreshHistory(); },
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run");
      setStreaming(false);
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const handleAddSubscriber = async () => {
    if (!newSubEmail.trim() || !adminKey.trim()) return;
    try {
      await addSubscriber(newSubEmail.trim(), newSubName.trim(), adminKey);
      setNewSubEmail("");
      setNewSubName("");
      refreshSubscribers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add subscriber");
    }
  };

  const handleDeleteSubscriber = async (id: string) => {
    try { await deleteSubscriber(id, adminKey); refreshSubscribers(); } catch { /* ignore */ }
  };

  const handleCreateGroup = async () => {
    if (!newGroupName.trim() || !adminKey.trim()) return;
    try {
      await createGroup(newGroupName.trim(), newGroupDesc.trim(), adminKey, newGroupTheme.trim() || undefined);
      setNewGroupName("");
      setNewGroupDesc("");
      setNewGroupTheme("");
      refreshGroups();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create group");
    }
  };

  const handleDeleteGroup = async (id: string) => {
    try { await deleteGroup(id, adminKey); refreshGroups(); refreshSubscribers(); } catch { /* ignore */ }
  };

  const handleBatchGenerate = async () => {
    if (!adminKey.trim() || groups.length === 0) return;
    setBatchLoading(true);
    setBatchStatus(null);
    try {
      const result = await batchCreateRuns(
        {
          audience: audience.trim() || undefined,
          tone,
          length,
          good_news_mode: mode,
          subtopic_count: subtopicCount,
          max_sources: maxSources,
          enable_factcheck: factcheck,
        },
        adminKey,
      );
      const createdCount = result.created.length;
      const skippedCount = result.skipped.length;
      if (createdCount > 0) {
        setBatchStatus(`Created ${createdCount} run(s) for groups: ${result.created.map(r => r.group_name).join(", ")}`);
        refreshHistory();
      } else {
        setBatchStatus("No runs created — all groups lack a theme.");
      }
      if (skippedCount > 0) {
        setBatchStatus(prev => prev ? `${prev} (Skipped: ${result.skipped.map(s => s.name).join(", ")})` : `Skipped: ${result.skipped.map(s => s.name).join(", ")}`);
      }
    } catch (err) {
      setBatchStatus(err instanceof Error ? err.message : "Batch generation failed");
    } finally {
      setBatchLoading(false);
    }
  };

  const handleToggleSubscriberGroup = async (subscriberId: string, groupId: string) => {
    const sub = subscribers.find(s => s.subscriber_id === subscriberId);
    const isInGroup = sub?.groups?.some(g => g.group_id === groupId);
    try {
      if (isInGroup) {
        await removeSubscriberFromGroup(subscriberId, groupId, adminKey);
      } else {
        await addSubscriberToGroup(subscriberId, groupId, adminKey);
      }
      refreshSubscribers();
      refreshGroups();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update group membership");
    }
  };

  const handleToggleSendGroup = (groupId: string) => {
    setSelectedGroupIds(prev => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  };

  const handleCreateQuestion = async () => {
    if (!newQuestionText.trim() || !adminKey.trim()) return;
    const opts = newQuestionOptions.filter(o => o.text.trim() && o.group_name.trim());
    if (opts.length < 2) { setError("Need at least 2 options with text and group name"); return; }
    try {
      await createQuestion(newQuestionText.trim(), opts, adminKey);
      setNewQuestionText("");
      setNewQuestionOptions([{ text: "", group_name: "" }, { text: "", group_name: "" }]);
      refreshQuestions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create question");
    }
  };

  const handleDeleteQuestion = async (id: string) => {
    try { await deleteQuestion(id, adminKey); refreshQuestions(); } catch { /* ignore */ }
  };

  const handleSendNewsletter = async () => {
    const targetRunId = selectedRunId || runId;
    if (!targetRunId || !adminKey.trim()) return;
    setSendStatus("Sending…");
    try {
      const groupIds = selectedGroupIds.size > 0 ? Array.from(selectedGroupIds) : undefined;
      const result = await sendNewsletter(targetRunId, adminKey, groupIds);
      setSendStatus(result.detail);
    } catch (err) {
      setSendStatus(err instanceof Error ? err.message : "Failed to send");
    }
  };

  const loadHistoryRun = async (id: string) => {
    try {
      const detail = await getRun(id);
      setRunId(id);
      if (detail.newsletter) {
        setNewsletter(detail.newsletter);
      }
      setEvents([]);
      setError(null);
      setSidebarTab("history");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run");
    }
  };

  const handleDeleteRun = async (id: string) => {
    try { await deleteRun(id); refreshHistory(); } catch { /* ignore */ }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <div className="grid min-h-screen lg:grid-cols-[minmax(340px,400px)_minmax(0,1fr)] max-lg:grid-cols-1">
        {/* === Left Panel === */}
        <aside className="relative flex flex-col gap-6 border-r border-slate-200/80 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
          <DotPattern className="text-slate-200/50 dark:text-slate-700/30" width={20} height={20} cr={1} />

          <div className="relative flex items-center gap-3">
            <Logo size={40} />
            <div>
              <h1 className="text-lg font-bold text-slate-900 dark:text-white">
                Admin Dashboard
              </h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">Pipeline & topic management</p>
            </div>
            <div className="ml-auto flex items-center gap-1">
              <button
                onClick={onLogout}
                className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 dark:hover:bg-slate-800"
                title="Sign out"
              >
                <LogOut size={18} />
              </button>
              <button
                onClick={onToggleDark}
                className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 dark:hover:bg-slate-800"
                aria-label="Toggle dark mode"
              >
                {dark ? <Sun size={18} /> : <Moon size={18} />}
              </button>
            </div>
          </div>

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
                <Database size={12} /> {status.llm_model}
              </span>
            </div>
          )}

          {/* Quick generate form */}
          <form onSubmit={handleSubmit} className="relative flex flex-col gap-3">
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
            <div>
              <label className="label-text" htmlFor="audience">Target Audience</label>
              <input
                id="audience"
                className="input-field"
                type="text"
                value={audience}
                onChange={(e) => setAudience(e.target.value)}
                placeholder="e.g. healthcare execs, climate investors…"
                disabled={streaming}
              />
            </div>

            <div className="flex gap-2">
              <ShimmerButton type="submit" disabled={!theme.trim() || streaming || !adminKey.trim()}
                borderRadius="12px" background="rgba(79, 70, 229, 1)" className="flex-1">
                {streaming ? (
                  <><Loader2 size={16} className="animate-spin" /> Generating…</>
                ) : (
                  <><Play size={16} /> Generate</>
                )}
              </ShimmerButton>
              {streaming && (
                <motion.button
                  initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
                  type="button" onClick={handleCancel}
                  className="inline-flex items-center gap-2 rounded-xl border border-red-200 px-4 py-2.5 text-sm font-medium text-red-600 transition hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20"
                >
                  <Square size={15} fill="currentColor" /> Cancel
                </motion.button>
              )}
            </div>
          </form>

          <button
            onClick={() => setActiveTab("configs")}
            className="btn-ghost w-full justify-center text-xs"
          >
            <SlidersHorizontal size={14} />
            Open Configs for full settings
          </button>

          {/* Export & send actions */}
          {newsletter && runId && (
            <div className="relative flex flex-col gap-2">
              <button
                onClick={handleSendNewsletter}
                disabled={!adminKey.trim()}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100"
              >
                <Send size={15} />
                Send to mailing list
              </button>
              {sendStatus && (
                <div className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:bg-slate-900/50 dark:text-slate-300">
                  {sendStatus}
                </div>
              )}
              <div className="relative flex items-center gap-2">
                <span className="text-xs font-medium text-slate-400">Export:</span>
                <button onClick={() => handleExport("markdown")} className="btn-ghost" title="Export Markdown">
                  <Download size={15} /> MD
                </button>
                <button onClick={() => handleExport("html")} className="btn-ghost" title="Export HTML">HTML</button>
                <button onClick={() => handleExport("pdf")} className="btn-ghost" title="Export PDF">PDF</button>
              </div>
            </div>
          )}
        </aside>

        {/* === Right Panel === */}
        <main className="flex flex-col overflow-y-auto max-h-screen max-lg:min-h-[60vh]">
          <div className="sticky top-0 z-10 flex items-center gap-1 border-b border-slate-200 bg-white/80 px-6 py-3 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/80">
            <button
              onClick={() => setActiveTab("pipeline")}
              className={cn("rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all",
                activeTab === "pipeline" ? "bg-brand-600 text-white shadow-sm shadow-brand-600/20" : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800")}
            >
              Pipeline
            </button>
            <button
              onClick={() => setActiveTab("configs")}
              className={cn("rounded-lg px-3.5 py-1.5 text-sm font-medium transition-all",
                activeTab === "configs" ? "bg-brand-600 text-white shadow-sm shadow-brand-600/20" : "text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800")}
            >
              Configs
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
                  <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">LangGraph Pipeline</h2>
                </div>
                <PipelineView topology={topology} events={events} active={streaming} />
                {streaming && events.length === 0 && (
                  <div className="mt-6 flex flex-col items-center gap-3 text-slate-400">
                    <div className="flex gap-1.5">
                      {[0, 1, 2].map((i) => (
                        <motion.div key={i} animate={{ opacity: [0.3, 1, 0.3] }}
                          transition={{ duration: 1.2, delay: i * 0.2, repeat: Infinity }}
                          className="h-2 w-2 rounded-full bg-brand-500" />
                      ))}
                    </div>
                    <p className="text-xs">Waiting for first event from the pipeline…</p>
                  </div>
                )}
                {events.length === 0 && !streaming && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="mt-8 text-center">
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
            ) : activeTab === "configs" ? (
              <div className="mx-auto max-w-2xl">
                <div className="mb-5 flex gap-1 rounded-xl bg-slate-100 p-1 dark:bg-slate-800/50">
                  {([
                    { id: "generate", label: "Generate", icon: Play },
                    { id: "subscribers", label: "Mailing", icon: Users },
                    { id: "questions", label: "Questions", icon: HelpCircle },
                    { id: "history", label: "History", icon: History },
                  ] as const).map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => {
                        setSidebarTab(tab.id);
                        if (tab.id === "subscribers") { refreshSubscribers(); refreshGroups(); refreshHistory(); }
                        if (tab.id === "questions") refreshQuestions();
                        if (tab.id === "history") refreshHistory();
                      }}
                      className={cn(
                        "flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                        sidebarTab === tab.id
                          ? "bg-white text-brand-600 shadow-sm dark:bg-slate-900 dark:text-brand-400"
                          : "text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                      )}
                    >
                      <tab.icon size={15} />
                      {tab.label}
                    </button>
                  ))}
                </div>

                {sidebarTab === "generate" && (
                  <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                    <div>
                      <label className="label-text" htmlFor="cfg-theme">Theme / Topic</label>
                      <input id="cfg-theme" className="input-field" type="text" value={theme}
                        onChange={(e) => setTheme(e.target.value)}
                        placeholder="e.g. ocean restoration, AI in healthcare…" disabled={streaming} />
                    </div>
                    <div>
                      <label className="label-text" htmlFor="cfg-audience">Target Audience</label>
                      <input id="cfg-audience" className="input-field" type="text" value={audience}
                        onChange={(e) => setAudience(e.target.value)}
                        placeholder="e.g. healthcare execs, climate investors, startup founders…" disabled={streaming} />
                      <p className="mt-1 text-xs text-slate-400">Describe who will receive this newsletter — the AI will tailor research angles, article selection, and writing to their interests.</p>
                    </div>
                    <button type="button" onClick={() => setShowFilters(!showFilters)}
                      className="flex items-center gap-2 text-sm font-medium text-slate-500 transition hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200">
                      <SlidersHorizontal size={15} />
                      {showFilters ? "Hide" : "Show"} advanced filters
                    </button>
                    <AnimatePresence>
                      {showFilters && (
                        <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                          <div className="flex flex-col gap-4 rounded-xl bg-slate-50 p-4 dark:bg-slate-900/50">
                            <div>
                              <label className="label-text">Good news mode</label>
                              <div className="flex gap-1.5">
                                {MODES.map((m) => (
                                  <button key={m.value} type="button" onClick={() => setMode(m.value)}
                                    className={cn("chip", mode === m.value ? "chip-active" : "chip-idle")}>{m.label}</button>
                                ))}
                              </div>
                            </div>
                            <div>
                              <label className="label-text">Tone</label>
                              <div className="flex flex-wrap gap-1.5">
                                {TONES.map((t) => (
                                  <button key={t.value} type="button" onClick={() => setTone(t.value)}
                                    className={cn("chip", tone === t.value ? "chip-active" : "chip-idle")}>{t.label}</button>
                                ))}
                              </div>
                            </div>
                            <div>
                              <label className="label-text">Length</label>
                              <div className="flex gap-1.5">
                                {LENGTHS.map((l) => (
                                  <button key={l.value} type="button" onClick={() => setLength(l.value)}
                                    className={cn("chip", length === l.value ? "chip-active" : "chip-idle")}>{l.label}</button>
                                ))}
                              </div>
                            </div>
                            <div>
                              <label className="label-text">Sub-topics: <span className="font-bold text-brand-600">{subtopicCount}</span></label>
                              <input type="range" min={1} max={6} value={subtopicCount}
                                onChange={(e) => setSubtopicCount(Number(e.target.value))} className="w-full accent-brand-600" />
                            </div>
                            <div>
                              <label className="label-text">Max sources: <span className="font-bold text-brand-600">{maxSources}</span></label>
                              <input type="range" min={5} max={40} value={maxSources}
                                onChange={(e) => setMaxSources(Number(e.target.value))} className="w-full accent-brand-600" />
                            </div>
                            <label className="flex items-center gap-2 text-sm font-medium text-slate-600 dark:text-slate-300">
                              <input type="checkbox" checked={factcheck} onChange={(e) => setFactcheck(e.target.checked)}
                                className="h-4 w-4 accent-brand-600" />
                              Enable fact-check & dedup
                            </label>
                            <div>
                              <label className="label-text">Custom RSS feeds (one URL per line)</label>
                              <textarea value={customFeeds} onChange={(e) => setCustomFeeds(e.target.value)}
                                placeholder={"https://example.com/feed.xml\nhttps://example.com/rss"}
                                rows={2} className="input-field text-xs resize-y" />
                            </div>
                            <div>
                              <label className="label-text">Custom article URLs (one URL per line)</label>
                              <textarea value={customUrls} onChange={(e) => setCustomUrls(e.target.value)}
                                placeholder={"https://example.com/article1\nhttps://example.com/article2"}
                                rows={2} className="input-field text-xs resize-y" />
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                    <AnimatePresence>
                      {error && (
                        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                          className="flex items-start gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
                          <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                          <span>{error}</span>
                          <button onClick={() => setError(null)} className="ml-auto"><X size={14} /></button>
                        </motion.div>
                      )}
                    </AnimatePresence>
                    <div className="flex gap-2">
                      <ShimmerButton type="submit" disabled={!theme.trim() || streaming || !adminKey.trim()}
                        borderRadius="12px" background="rgba(79, 70, 229, 1)" className="flex-1">
                        {streaming ? (
                          <><Loader2 size={16} className="animate-spin" /> Generating…</>
                        ) : (
                          <><Play size={16} /> Generate newsletter</>
                        )}
                      </ShimmerButton>
                      {streaming && (
                        <motion.button initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
                          type="button" onClick={handleCancel}
                          className="inline-flex items-center gap-2 rounded-xl border border-red-200 px-4 py-2.5 text-sm font-medium text-red-600 transition hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/20">
                          <Square size={15} fill="currentColor" /> Cancel
                        </motion.button>
                      )}
                    </div>
                  </form>
                )}

                {sidebarTab === "subscribers" && (
                  <div className="flex flex-col gap-4">
                    <div>
                      <h3 className="text-base font-bold text-slate-700 dark:text-slate-200">Mailing List</h3>
                      <p className="text-sm text-slate-400 mt-0.5">{subscribers.length} subscriber(s) · {groups.length} group(s)</p>
                    </div>

                    {/* Groups section */}
                    <div className="flex flex-col gap-2 rounded-xl bg-slate-50 p-3 dark:bg-slate-900/50">
                      <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Groups</div>
                      <div className="flex gap-2">
                        <input className="input-field flex-1" type="text" value={newGroupName}
                          onChange={(e) => setNewGroupName(e.target.value)} placeholder="Group name (e.g. AI in Healthcare)" />
                        <button onClick={handleCreateGroup} className="rounded-lg bg-brand-600 p-2.5 text-white transition hover:bg-brand-700">
                          <Plus size={16} />
                        </button>
                      </div>
                      <input className="input-field" type="text" value={newGroupDesc}
                        onChange={(e) => setNewGroupDesc(e.target.value)} placeholder="Description (optional)" />
                      <input className="input-field" type="text" value={newGroupTheme}
                        onChange={(e) => setNewGroupTheme(e.target.value)} placeholder="Newsletter theme (e.g. 'AI in healthcare')" />
                      <div className="flex flex-col gap-1.5">
                        {groups.map((g) => (
                          <div key={g.group_id} className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-800">
                            <div className="flex-1">
                              <div className="flex items-center gap-1.5">
                                <span className="font-medium">{g.name}</span>
                                <span className="text-slate-400">({g.subscriber_count})</span>
                              </div>
                              {g.theme && (
                                <div className="text-[10px] text-brand-600 dark:text-brand-400 mt-0.5">Theme: {g.theme}</div>
                              )}
                            </div>
                            <button onClick={() => handleDeleteGroup(g.group_id)} className="text-slate-300 transition hover:text-red-500">
                              <X size={12} />
                            </button>
                          </div>
                        ))}
                        {groups.length === 0 && (
                          <span className="text-xs text-slate-400">No groups yet.</span>
                        )}
                      </div>
                      {groups.length > 0 && (
                        <>
                          <button
                            onClick={handleBatchGenerate}
                            disabled={batchLoading || !adminKey.trim()}
                            className="inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-brand-600 to-indigo-600 px-3 py-2 text-xs font-semibold text-white transition hover:from-brand-700 hover:to-indigo-700 disabled:opacity-50"
                          >
                            {batchLoading ? (
                              <><Loader2 size={14} className="animate-spin" /> Generating…</>
                            ) : (
                              <><Layers size={14} /> Generate for all groups</>
                            )}
                          </button>
                          {batchStatus && (
                            <div className="text-xs text-slate-500 dark:text-slate-400">{batchStatus}</div>
                          )}
                        </>
                      )}
                    </div>

                    {/* Add subscriber */}
                    <div className="flex flex-col gap-2">
                      <input className="input-field" type="email" value={newSubEmail}
                        onChange={(e) => setNewSubEmail(e.target.value)} placeholder="subscriber@email.com" />
                      <div className="flex gap-2">
                        <input className="input-field flex-1" type="text" value={newSubName}
                          onChange={(e) => setNewSubName(e.target.value)} placeholder="Name (optional)" />
                        <button onClick={handleAddSubscriber} className="rounded-lg bg-brand-600 p-2.5 text-white transition hover:bg-brand-700">
                          <Plus size={16} />
                        </button>
                      </div>
                    </div>

                    {/* Subscriber list with group badges */}
                    <div className="flex flex-col gap-2">
                      {subscribers.map((s) => (
                        <div key={s.subscriber_id} className="flex flex-col gap-1.5 rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                          <div className="flex items-center gap-2">
                            <div className="flex-1 truncate">
                              <div className="font-medium truncate">{s.email}</div>
                              {s.name && <div className="text-xs text-slate-400">{s.name}</div>}
                            </div>
                            <button onClick={() => handleDeleteSubscriber(s.subscriber_id)} className="text-slate-300 transition hover:text-red-500">
                              <Trash2 size={15} />
                            </button>
                          </div>
                          {groups.length > 0 && (
                            <div className="flex flex-wrap gap-1">
                              {groups.map((g) => {
                                const inGroup = s.groups?.some(sg => sg.group_id === g.group_id);
                                return (
                                  <button key={g.group_id}
                                    onClick={() => handleToggleSubscriberGroup(s.subscriber_id, g.group_id)}
                                    className={cn(
                                      "rounded-md px-2 py-0.5 text-[10px] font-medium transition",
                                      inGroup
                                        ? "bg-brand-600 text-white"
                                        : "bg-slate-100 text-slate-400 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-500"
                                    )}
                                  >
                                    {g.name}
                                  </button>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      ))}
                      {subscribers.length === 0 && (
                        <div className="flex flex-col items-center gap-2 py-12 text-center">
                          <Users size={32} className="text-slate-300 dark:text-slate-600" />
                          <p className="text-sm text-slate-400">No subscribers yet.<br />Add one above to get started.</p>
                        </div>
                      )}
                    </div>

                    {/* Send to groups */}
                    <div className="flex flex-col gap-2 border-t border-slate-200 pt-4 dark:border-slate-800">
                      <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Send newsletter</div>
                      <select className="input-field" value={selectedRunId} onChange={(e) => setSelectedRunId(e.target.value)}>
                        <option value="">— Select a newsletter —</option>
                        {history.filter(h => h.status === "done" || h.status === "partial").map(h => (
                          <option key={h.run_id} value={h.run_id}>
                            {h.config?.theme || "Untitled"} — {formatDate(h.created_at)}
                          </option>
                        ))}
                      </select>

                      {groups.length > 0 ? (
                        <div className="flex flex-col gap-1.5">
                          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Select groups to send to</div>
                          <div className="flex flex-wrap gap-1.5">
                            {groups.map((g) => (
                              <button key={g.group_id}
                                onClick={() => handleToggleSendGroup(g.group_id)}
                                className={cn(
                                  "rounded-lg px-3 py-1.5 text-xs font-medium transition",
                                  selectedGroupIds.has(g.group_id)
                                    ? "bg-brand-600 text-white shadow-sm"
                                    : "bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400"
                                )}
                              >
                                {g.name} ({g.subscriber_count})
                              </button>
                            ))}
                          </div>
                          <p className="text-xs text-slate-400">
                            {selectedGroupIds.size > 0
                              ? `Will send to ${selectedGroupIds.size} group(s). Subscribers in any selected group will receive the newsletter.`
                              : "Select at least one group to send the newsletter."}
                          </p>
                        </div>
                      ) : (
                        <p className="text-xs text-slate-400">Create a group and assign subscribers to it before sending.</p>
                      )}
                      <button onClick={handleSendNewsletter} disabled={!adminKey.trim() || selectedGroupIds.size === 0 || !selectedRunId}
                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100"
                      >
                        <Send size={15} />
                        {selectedGroupIds.size > 0 && selectedRunId ? `Send to ${selectedGroupIds.size} group(s)` : "Select newsletter and groups"}
                      </button>
                      {sendStatus && (
                        <div className="rounded-xl bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:bg-slate-900/50 dark:text-slate-300">
                          {sendStatus}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {sidebarTab === "history" && (
                  <div className="flex flex-col gap-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-base font-bold text-slate-700 dark:text-slate-200">Run History</h3>
                        <p className="text-sm text-slate-400 mt-0.5">{history.length} run(s)</p>
                      </div>
                      <button onClick={refreshHistory} className="btn-ghost text-xs">
                        <RefreshCw size={14} /> Refresh
                      </button>
                    </div>
                    <div className="flex flex-col gap-2">
                      {history.length === 0 ? (
                        <div className="flex flex-col items-center gap-2 py-12 text-center">
                          <History size={32} className="text-slate-300 dark:text-slate-600" />
                          <p className="text-sm text-slate-400">No runs yet.<br />Generate a newsletter to see it here.</p>
                        </div>
                      ) : (
                        history.map((item) => (
                          <div key={item.run_id} className="flex items-center gap-2 rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                            <button onClick={() => loadHistoryRun(item.run_id)} className="flex-1 text-left transition hover:text-brand-600">
                              <div className="font-medium truncate">{item.config?.theme ?? "Untitled"}</div>
                              <div className="text-xs text-slate-400">{new Date(item.created_at).toLocaleDateString()} · {item.status}</div>
                            </button>
                            <button onClick={() => handleDeleteRun(item.run_id)} className="text-slate-300 transition hover:text-red-500">
                              <Trash2 size={15} />
                            </button>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}

                {sidebarTab === "questions" && (
                  <div className="flex flex-col gap-4">
                    <div>
                      <h3 className="text-base font-bold text-slate-700 dark:text-slate-200">Registration Questions</h3>
                      <p className="text-sm text-slate-400 mt-0.5">Questions shown to new users during account creation. Each option maps to a group.</p>
                    </div>

                    <div className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                      <div>
                        <label className="label-text">Question text</label>
                        <input className="input-field" type="text" value={newQuestionText}
                          onChange={(e) => setNewQuestionText(e.target.value)}
                          placeholder="e.g. What industry are you most interested in?" />
                      </div>
                      <div className="flex flex-col gap-2">
                        <label className="label-text">Answer options (each maps to a group)</label>
                        {newQuestionOptions.map((opt, i) => (
                          <div key={i} className="flex gap-2">
                            <input className="input-field flex-1" type="text" value={opt.text}
                              onChange={(e) => setNewQuestionOptions(prev => prev.map((o, j) => j === i ? { ...o, text: e.target.value } : o))}
                              placeholder={`Option ${i + 1} text`} />
                            <input className="input-field w-32" type="text" value={opt.group_name}
                              onChange={(e) => setNewQuestionOptions(prev => prev.map((o, j) => j === i ? { ...o, group_name: e.target.value } : o))}
                              placeholder="Group name" />
                            {newQuestionOptions.length > 2 && (
                              <button onClick={() => setNewQuestionOptions(prev => prev.filter((_, j) => j !== i))}
                                className="text-slate-300 transition hover:text-red-500">
                                <X size={16} />
                              </button>
                            )}
                          </div>
                        ))}
                        <button onClick={() => setNewQuestionOptions(prev => [...prev, { text: "", group_name: "" }])}
                          className="inline-flex items-center gap-1 text-xs font-medium text-brand-600 transition hover:text-brand-700">
                          <Plus size={14} /> Add option
                        </button>
                      </div>
                      <button onClick={handleCreateQuestion} disabled={!newQuestionText.trim() || !adminKey.trim()}
                        className="inline-flex items-center justify-center gap-2 rounded-xl bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:opacity-50">
                        <Plus size={15} /> Create question
                      </button>
                    </div>

                    <div className="flex flex-col gap-2">
                      {questions.length === 0 ? (
                        <div className="flex flex-col items-center gap-2 py-12 text-center">
                          <HelpCircle size={32} className="text-slate-300 dark:text-slate-600" />
                          <p className="text-sm text-slate-400">No questions yet.<br />Create one above to set up the registration flow.</p>
                        </div>
                      ) : (
                        questions.map((q, qi) => (
                          <div key={q.question_id} className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex-1">
                                <div className="font-medium text-sm text-slate-700 dark:text-slate-200">{qi + 1}. {q.text}</div>
                                <div className="mt-2 flex flex-wrap gap-1.5">
                                  {q.options.map((opt) => (
                                    <span key={opt.option_id} className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                                      {opt.text} → <span className="font-medium text-brand-600 dark:text-brand-400">{opt.group_name}</span>
                                    </span>
                                  ))}
                                </div>
                              </div>
                              <button onClick={() => handleDeleteQuestion(q.question_id)} className="text-slate-300 transition hover:text-red-500">
                                <Trash2 size={15} />
                              </button>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="grid place-items-center py-20 text-center">
                <div className="flex flex-col items-center gap-3 text-slate-400">
                  <Newspaper size={32} />
                  <h2 className="text-lg font-bold text-slate-500 dark:text-slate-300">No configuration selected</h2>
                  <p className="max-w-xs text-sm">Use the Configs tab to generate a new newsletter.</p>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
