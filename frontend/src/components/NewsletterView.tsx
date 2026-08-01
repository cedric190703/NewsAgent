import { motion } from "motion/react";
import { Bookmark, ExternalLink, FileDown, AlertTriangle, Quote, Clock, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

import type { ArticleSummary, Newsletter, SourceRef } from "../services/api";
import { cn } from "../lib/utils";

interface NewsletterViewProps {
  newsletter: Newsletter;
  runId: string;
  onBookmark: (article: ArticleSummary) => void;
  bookmarkedIds: Set<string>;
}

function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 75 ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
    : pct >= 50 ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
    : "bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-300";
  return <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-bold", color)}>{pct}</span>;
}

function ArticleCard({
  item,
  runId,
  onBookmark,
  bookmarked,
}: {
  item: ArticleSummary;
  runId: string;
  onBookmark: (a: ArticleSummary) => void;
  bookmarked: boolean;
}) {
  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="card group overflow-hidden transition-all hover:shadow-md"
    >
      {item.image_url && (
        <div className="relative h-40 w-full overflow-hidden">
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
        <div className="flex items-start justify-between gap-2">
          <h4 className="text-sm font-bold leading-snug text-slate-800 dark:text-slate-100">
            {item.headline}
          </h4>
          <ScoreBadge score={item.scores.composite} />
        </div>

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
                <span className="mt-1 h-1 w-1 flex-shrink-0 rounded-full bg-brand-500" />
                {bullet}
              </li>
            ))}
          </ul>
        )}

        {item.key_facts.length > 0 && (
          <div className="mt-3.5 space-y-2">
            {item.key_facts.map((fact, i) => (
              <div
                key={i}
                className="rounded-xl bg-slate-50 p-3 dark:bg-slate-900/60"
              >
                <p className="text-xs font-medium text-slate-700 dark:text-slate-200">
                  {fact.claim}
                </p>
                <div className="mt-1.5 flex items-start gap-2">
                  <Quote size={13} className="mt-0.5 flex-shrink-0 text-brand-400" />
                  <p className="text-xs italic text-slate-500 dark:text-slate-400">
                    {fact.quote}
                  </p>
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
            Read article
          </a>
          <button
            onClick={() => onBookmark(item)}
            className={cn(
              "inline-flex items-center gap-1.5 text-xs font-medium transition",
              bookmarked
                ? "text-amber-600 dark:text-amber-400"
                : "text-slate-400 hover:text-amber-500"
            )}
          >
            <Bookmark size={13} fill={bookmarked ? "currentColor" : "none"} />
            {bookmarked ? "Saved" : "Save"}
          </button>
        </div>
      </div>
    </motion.article>
  );
}

function SourceList({ sources }: { sources: SourceRef[] }) {
  return (
    <div className="card p-5">
      <h3 className="mb-3 text-sm font-bold text-slate-700 dark:text-slate-200">
        Sources ({sources.length})
      </h3>
      <ol className="space-y-2">
        {sources.map((src, i) => (
          <li key={src.article_id} className="flex items-start gap-2 text-xs">
            <span className="flex-shrink-0 font-bold text-slate-400">{i + 1}.</span>
            <a
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-600 hover:underline dark:text-brand-400"
            >
              {src.source_name}
            </a>
            <span className="text-slate-400">— {src.title}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function NewsletterView({ newsletter, runId, onBookmark, bookmarkedIds }: NewsletterViewProps) {
  const [showSources, setShowSources] = useState(false);
  const totalArticles = newsletter.sections.reduce((acc, s) => acc + s.items.length, 0);

  return (
    <div className="flex flex-col gap-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="card relative overflow-hidden p-6"
      >
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white">{newsletter.title}</h2>
        {newsletter.subtitle && (
          <p className="mt-1.5 text-sm italic text-slate-500 dark:text-slate-400">
            {newsletter.subtitle}
          </p>
        )}
        <p className="mt-4 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
          {newsletter.intro}
        </p>

        <div className="mt-4 flex items-center gap-4 text-xs text-slate-400">
          <span>{newsletter.sections.length} sections</span>
          <span>·</span>
          <span>{totalArticles} articles</span>
          <span>·</span>
          <span>{newsletter.sources.length} sources</span>
        </div>

        {newsletter.degraded && (
          <div className="mt-4 flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-2.5 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
            <AlertTriangle size={14} />
            This newsletter ran in degraded mode — fewer sources than requested were available.
          </div>
        )}

        {newsletter.notes.length > 0 && (
          <div className="mt-3 space-y-1">
            {newsletter.notes.map((note, i) => (
              <p key={i} className="text-xs text-slate-400">· {note}</p>
            ))}
          </div>
        )}
      </motion.div>

      {newsletter.sections.map((section, si) => (
        <motion.div
          key={section.subtopic_id}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: si * 0.1 }}
          className="flex flex-col gap-3"
        >
          <div className="flex items-baseline gap-3">
            <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100">
              {section.title}
            </h3>
            <span className="text-xs text-slate-400">{section.items.length} stories</span>
          </div>
          {section.blurb && (
            <p className="text-sm text-slate-500 dark:text-slate-400">{section.blurb}</p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            {section.items.map((item) => (
              <ArticleCard
                key={item.article_id}
                item={item}
                runId={runId}
                onBookmark={onBookmark}
                bookmarked={bookmarkedIds.has(item.article_id)}
              />
            ))}
          </div>
        </motion.div>
      ))}

      {newsletter.conflicts.length > 0 && (
        <div className="card border-amber-200 p-5 dark:border-amber-800/50">
          <h3 className="flex items-center gap-2 text-sm font-bold text-amber-700 dark:text-amber-300">
            <AlertTriangle size={16} />
            Flagged conflicts ({newsletter.conflicts.length})
          </h3>
          <ul className="mt-2.5 space-y-2">
            {newsletter.conflicts.map((conflict, i) => (
              <li key={i} className="text-xs text-slate-600 dark:text-slate-300">
                <span className="font-bold uppercase text-amber-600">[{conflict.severity}]</span>{" "}
                {conflict.claim} — {conflict.note}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <button
          onClick={() => setShowSources(!showSources)}
          className="btn-ghost"
        >
          {showSources ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
          {showSources ? "Hide" : "Show"} source list
        </button>
        {showSources && <div className="mt-3"><SourceList sources={newsletter.sources} /></div>}
      </div>

      {newsletter.outro && (
        <p className="text-center text-sm italic text-slate-400">{newsletter.outro}</p>
      )}
    </div>
  );
}
