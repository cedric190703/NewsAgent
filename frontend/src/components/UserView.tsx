import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Newspaper,
  Moon,
  Sun,
  Search,
  ArrowLeft,
  Clock,
  ExternalLink,
  Bookmark,
  Quote,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Download,
} from "lucide-react";

import {
  type Newsletter,
  type NewsletterListItem,
  type ArticleSummary,
  listNewsletters,
  exportRun,
} from "../services/api";
import { cn } from "../lib/utils";

function formatDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function ArticleCard({ item }: { item: ArticleSummary }) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="card group overflow-hidden transition-all hover:shadow-md"
    >
      {item.image_url && (
        <div className="relative h-44 w-full overflow-hidden">
          <img
            src={item.image_url}
            alt=""
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
            loading="lazy"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        </div>
      )}
      <div className="p-5">
        <h4 className="text-base font-bold leading-snug text-slate-800 dark:text-slate-100">
          {item.headline}
        </h4>
        <div className="mt-2 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
          <span className="font-medium">{item.source_name}</span>
          {item.published_at && (
            <>
              <span>·</span>
              <Clock size={11} />
              <span>{formatDate(item.published_at)}</span>
            </>
          )}
        </div>

        {item.bullets.length > 0 && (
          <ul className="mt-3.5 space-y-1.5">
            {item.bullets.map((bullet, i) => (
              <li key={i} className="flex gap-2 text-sm text-slate-600 dark:text-slate-300">
                <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-brand-500" />
                {bullet}
              </li>
            ))}
          </ul>
        )}

        {item.key_facts.length > 0 && (
          <div className="mt-3.5 space-y-2">
            {item.key_facts.map((fact, i) => (
              <div key={i} className="rounded-xl bg-slate-50 p-3 dark:bg-slate-900/60">
                <p className="text-xs font-medium text-slate-700 dark:text-slate-200">{fact.claim}</p>
                <div className="mt-1.5 flex items-start gap-2">
                  <Quote size={13} className="mt-0.5 flex-shrink-0 text-brand-400" />
                  <p className="text-xs italic text-slate-500 dark:text-slate-400">{fact.quote}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 flex items-center gap-3 border-t border-slate-100 pt-3 dark:border-slate-800">
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-brand-600 transition hover:text-brand-700 dark:text-brand-400"
          >
            <ExternalLink size={13} />
            Read full article
          </a>
        </div>
      </div>
    </motion.article>
  );
}

function NewsletterReader({ item, onBack }: { item: NewsletterListItem; onBack: () => void }) {
  const newsletter = item.newsletter as Newsletter;
  const [showSources, setShowSources] = useState(false);
  const totalArticles = newsletter?.sections?.reduce((acc, s) => acc + s.items.length, 0) ?? 0;

  const handleExport = async (fmt: "markdown" | "html" | "pdf") => {
    try {
      const blob = await exportRun(item.run_id, fmt);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `newsletter-${item.run_id}.${fmt === "markdown" ? "md" : fmt}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };

  if (!newsletter) return null;

  return (
    <div className="mx-auto max-w-3xl">
      <button onClick={onBack} className="mb-6 inline-flex items-center gap-2 text-sm font-medium text-slate-500 transition hover:text-brand-600 dark:text-slate-400">
        <ArrowLeft size={16} />
        Back to newsletters
      </button>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="card relative overflow-hidden p-8"
      >
        <div className="mb-2 flex items-center gap-2 text-xs text-slate-400">
          <Clock size={12} />
          {formatDate(item.created_at)}
        </div>
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white">{newsletter.title}</h1>
        {newsletter.subtitle && (
          <p className="mt-2 text-base italic text-slate-500 dark:text-slate-400">{newsletter.subtitle}</p>
        )}
        <p className="mt-5 text-sm leading-relaxed text-slate-700 dark:text-slate-300">{newsletter.intro}</p>

        <div className="mt-5 flex items-center gap-4 text-xs text-slate-400">
          <span>{newsletter.sections.length} sections</span>
          <span>·</span>
          <span>{totalArticles} articles</span>
          <span>·</span>
          <span>{newsletter.sources.length} sources</span>
          <div className="ml-auto flex gap-1">
            <button onClick={() => handleExport("markdown")} className="btn-ghost text-xs" title="Export MD">
              <Download size={13} /> MD
            </button>
            <button onClick={() => handleExport("html")} className="btn-ghost text-xs" title="Export HTML">
              <Download size={13} /> HTML
            </button>
          </div>
        </div>

        {newsletter.degraded && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-2.5 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
            <AlertTriangle size={14} />
            This newsletter ran in degraded mode — fewer sources than requested were available.
          </div>
        )}
      </motion.div>

      {newsletter.sections.map((section, si) => (
        <motion.div
          key={section.subtopic_id}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: si * 0.08 }}
          className="mt-8 flex flex-col gap-3"
        >
          <div className="flex items-baseline gap-3">
            <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100">{section.title}</h2>
            <span className="text-xs text-slate-400">{section.items.length} stories</span>
          </div>
          {section.blurb && <p className="text-sm text-slate-500 dark:text-slate-400">{section.blurb}</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            {section.items.map((item) => (
              <ArticleCard key={item.article_id} item={item} />
            ))}
          </div>
        </motion.div>
      ))}

      {newsletter.conflicts.length > 0 && (
        <div className="card mt-6 border-amber-200 p-5 dark:border-amber-800/50">
          <h3 className="flex items-center gap-2 text-sm font-bold text-amber-700 dark:text-amber-300">
            <AlertTriangle size={16} />
            Flagged conflicts ({newsletter.conflicts.length})
          </h3>
          <ul className="mt-2.5 space-y-2">
            {newsletter.conflicts.map((c, i) => (
              <li key={i} className="text-xs text-slate-600 dark:text-slate-300">
                <span className="font-bold uppercase text-amber-600">[{c.severity}]</span> {c.claim} — {c.note}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-6">
        <button onClick={() => setShowSources(!showSources)} className="btn-ghost">
          {showSources ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
          {showSources ? "Hide" : "Show"} source list ({newsletter.sources.length})
        </button>
        {showSources && (
          <div className="card mt-3 p-5">
            <ol className="space-y-2">
              {newsletter.sources.map((src, i) => (
                <li key={src.article_id} className="flex items-start gap-2 text-xs">
                  <span className="flex-shrink-0 font-bold text-slate-400">{i + 1}.</span>
                  <a href={src.url} target="_blank" rel="noopener noreferrer" className="text-brand-600 hover:underline dark:text-brand-400">
                    {src.source_name}
                  </a>
                  <span className="text-slate-400">— {src.title}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {newsletter.outro && (
        <p className="mt-8 text-center text-sm italic text-slate-400">{newsletter.outro}</p>
      )}
    </div>
  );
}

export function UserView({ dark, onToggleDark }: { dark: boolean; onToggleDark: () => void }) {
  const [newsletters, setNewsletters] = useState<NewsletterListItem[]>([]);
  const [selected, setSelected] = useState<NewsletterListItem | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    listNewsletters()
      .then(setNewsletters)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const filtered = newsletters.filter((n) =>
    n.theme.toLowerCase().includes(search.toLowerCase()) ||
    n.title.toLowerCase().includes(search.toLowerCase())
  );

  if (selected) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
        <div className="mx-auto max-w-5xl p-6">
          <NewsletterReader item={selected} onBack={() => setSelected(null)} />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/80">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-6 py-4">
          <div className="inline-grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-purple-600 text-white shadow-lg shadow-brand-500/20">
            <Newspaper size={20} />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 dark:text-white">Good News Agent</h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">Curated AI newsletters</p>
          </div>
          <button
            onClick={onToggleDark}
            className="ml-auto rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 dark:hover:bg-slate-800"
            aria-label="Toggle dark mode"
          >
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-5xl p-6">
        {/* Search */}
        <div className="relative mb-6">
          <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search newsletters…"
            className="input-field pl-12"
          />
        </div>

        {/* Newsletter grid */}
        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="card h-48 animate-pulse bg-slate-100 dark:bg-slate-800" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="grid place-items-center py-20 text-center">
            <div className="flex flex-col items-center gap-3 text-slate-400">
              <Newspaper size={40} className="text-slate-300 dark:text-slate-600" />
              <h2 className="text-lg font-bold text-slate-500 dark:text-slate-300">
                {search ? "No newsletters found" : "No newsletters yet"}
              </h2>
              <p className="max-w-xs text-sm">
                {search
                  ? "Try a different search term."
                  : "Newsletters will appear here once the admin generates them."}
              </p>
            </div>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <AnimatePresence>
              {filtered.map((item, i) => {
                const nl = item.newsletter as Newsletter;
                const totalArticles = nl?.sections?.reduce((acc, s) => acc + s.items.length, 0) ?? 0;
                return (
                  <motion.button
                    key={item.run_id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                    onClick={() => setSelected(item)}
                    className="card group flex flex-col p-5 text-left transition-all hover:shadow-lg hover:ring-2 hover:ring-brand-500/20"
                  >
                    <div className="mb-2 flex items-center gap-2 text-xs text-slate-400">
                      <Clock size={11} />
                      {formatDate(item.created_at)}
                    </div>
                    <h3 className="text-base font-bold leading-snug text-slate-800 transition group-hover:text-brand-600 dark:text-slate-100">
                      {item.title}
                    </h3>
                    {item.subtitle && (
                      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400 line-clamp-2">{item.subtitle}</p>
                    )}
                    <div className="mt-auto pt-4 flex items-center gap-3 text-xs text-slate-400">
                      <span>{nl?.sections?.length ?? 0} sections</span>
                      <span>·</span>
                      <span>{totalArticles} articles</span>
                      <span>·</span>
                      <span>{nl?.sources?.length ?? 0} sources</span>
                    </div>
                  </motion.button>
                );
              })}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
}
