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
  X,
  UserPlus,
  Check,
  Loader2,
  LogOut,
} from "lucide-react";

import {
  type Newsletter,
  type NewsletterListItem,
  type ArticleSummary,
  type Question,
  listNewsletters,
  listMyNewsletters,
  listQuestions,
  registerSubscriber,
  exportRun,
} from "../services/api";
import { cn } from "../lib/utils";
import { Logo } from "./Logo";

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

function RegistrationModal({ onClose, onRegistered }: { onClose: () => void; onRegistered: (email: string, groups: string[], token: string) => void }) {
  const [step, setStep] = useState<"intro" | "form" | "questions" | "review" | "result">("intro");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [assignedGroups, setAssignedGroups] = useState<string[]>([]);
  const [authToken, setAuthToken] = useState("");

  const steps = ["Welcome", "Details", "Profile", "Review", "Done"] as const;
  const stepIndex = { intro: 0, form: 1, questions: 2, review: 3, result: 4 }[step];

  const toggleAnswer = (qid: string, oid: string) => {
    setAnswers(prev => {
      const current = prev[qid] || [];
      return {
        ...prev,
        [qid]: current.includes(oid) ? current.filter(id => id !== oid) : [...current, oid],
      };
    });
  };

  const startQuestions = async () => {
    if (!email.trim()) { setError("Please enter your email"); return; }
    setError(null);
    setSubmitting(true);
    try {
      const qs = await listQuestions();
      if (qs.length === 0) {
        setError("No questions configured yet. Please check back later.");
        setSubmitting(false);
        return;
      }
      setQuestions(qs);
      setStep("questions");
    } catch {
      setError("Failed to load questions. Please try again.");
    }
    setSubmitting(false);
  };

  const goToReview = () => {
    const unanswered = questions.filter(q => (answers[q.question_id] || []).length === 0);
    if (unanswered.length > 0) { setError(`Please answer all questions (${unanswered.length} remaining)`); return; }
    setError(null);
    setStep("review");
  };

  const previewGroups = (() => {
    const groups = new Set<string>();
    for (const q of questions) {
      for (const oid of (answers[q.question_id] || [])) {
        const opt = q.options.find(o => o.option_id === oid);
        if (opt?.group_name) groups.add(opt.group_name);
      }
    }
    return Array.from(groups);
  })();

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const answerList = questions.map(q => ({
        question_id: q.question_id,
        option_ids: answers[q.question_id] || [],
      }));
      const result = await registerSubscriber(email.trim(), name.trim(), answerList);
      setAssignedGroups(result.assigned_groups);
      setAuthToken(result.token);
      setStep("result");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    }
    setSubmitting(false);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.96, opacity: 0, y: 8 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.96, opacity: 0, y: 8 }}
        transition={{ type: "spring", duration: 0.4 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-900 dark:ring-1 dark:ring-slate-700"
      >
        {/* Header */}
        <div className="relative border-b border-slate-100 px-7 pb-5 pt-6 dark:border-slate-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Logo size={32} />
              <div>
                <h2 className="text-base font-bold tracking-tight text-slate-900 dark:text-white">Good News Agent</h2>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Personalized newsletter portal</p>
              </div>
            </div>
            <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200">
              <X size={16} />
            </button>
          </div>

          {/* Step indicator */}
          <div className="relative mt-5 flex items-center gap-1.5">
            {steps.map((s, i) => (
              <div key={s} className="flex flex-1 flex-col gap-1">
                <div className={cn(
                  "h-1 rounded-full transition-all duration-300",
                  i <= stepIndex ? "bg-slate-900 dark:bg-white" : "bg-slate-200 dark:bg-slate-700"
                )} />
                <span className={cn(
                  "text-[10px] font-medium transition",
                  i <= stepIndex ? "text-slate-700 dark:text-slate-200" : "text-slate-400"
                )}>{s}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="px-7 py-7">
          {step === "intro" && (
            <div className="flex flex-col gap-5">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Welcome</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-slate-500 dark:text-slate-400">
                  Create your account in under a minute. Answer a few questions about your interests and we'll place you in the right newsletter groups — tailored content, delivered to your inbox.
                </p>
              </div>
              <div className="flex flex-col gap-2 rounded-xl bg-slate-50 p-4 dark:bg-slate-800/50">
                {[
                  { icon: Check, text: "Personalized newsletters based on your interests" },
                  { icon: Check, text: "Select multiple interests — join multiple groups" },
                  { icon: Check, text: "One combined email with all your groups' content" },
                  { icon: Check, text: "Sign in anytime to view your newsletter history" },
                ].map((item, i) => (
                  <div key={i} className="flex items-center gap-2.5">
                    <div className="inline-grid h-5 w-5 place-items-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400">
                      <item.icon size={12} />
                    </div>
                    <span className="text-xs text-slate-600 dark:text-slate-300">{item.text}</span>
                  </div>
                ))}
              </div>
              <button onClick={() => setStep("form")} className="w-full rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100">
                Get started — it's free
              </button>
            </div>
          )}

          {step === "form" && (
            <div className="flex flex-col gap-4">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Your details</h3>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">We'll use your email to deliver newsletters and sign you in.</p>
              </div>
              <div className="flex flex-col gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Email address</label>
                  <input className="input-field" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Full name <span className="font-normal text-slate-400">(optional)</span></label>
                  <input className="input-field" type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" />
                </div>
              </div>
              {error && (
                <div className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600 dark:bg-red-900/20 dark:text-red-400">
                  <AlertTriangle size={14} /> {error}
                </div>
              )}
              <div className="flex gap-2">
                <button onClick={startQuestions} disabled={submitting} className="flex-1 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100">
                  {submitting ? <Loader2 size={16} className="animate-spin" /> : "Continue"}
                </button>
                <button onClick={() => setStep("intro")} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-500 transition hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
                  Back
                </button>
              </div>
            </div>
          )}

          {step === "questions" && (
            <div className="flex flex-col gap-4">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Your interests</h3>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Select all that apply. You can choose multiple answers per question — this determines which groups you join.</p>
              </div>
              <div className="flex flex-col gap-5 max-h-[50vh] overflow-y-auto pr-1">
                {questions.map((q, qi) => (
                  <div key={q.question_id} className="flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <label className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                        <span className="text-brand-600 dark:text-brand-400">Q{qi + 1}.</span> {q.text}
                      </label>
                      {(answers[q.question_id] || []).length > 0 && (
                        <span className="text-[10px] font-medium text-brand-600 dark:text-brand-400">
                          {(answers[q.question_id] || []).length} selected
                        </span>
                      )}
                    </div>
                    <div className="flex flex-col gap-1.5">
                      {q.options.map((opt) => {
                        const selected = (answers[q.question_id] || []).includes(opt.option_id);
                        return (
                          <button
                            key={opt.option_id}
                            onClick={() => toggleAnswer(q.question_id, opt.option_id)}
                            className={cn(
                              "flex items-center gap-2.5 rounded-xl border px-3.5 py-2.5 text-left text-sm transition-all",
                              selected
                                ? "border-brand-500 bg-brand-50 text-brand-700 shadow-sm dark:border-brand-400 dark:bg-brand-900/20 dark:text-brand-300"
                                : "border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:bg-slate-800/50"
                            )}
                          >
                            <div className={cn(
                              "inline-grid h-4 w-4 flex-shrink-0 place-items-center rounded-md border-2 transition",
                              selected
                                ? "border-brand-500 bg-brand-500"
                                : "border-slate-300 dark:border-slate-600"
                            )}>
                              {selected && <Check size={11} className="text-white" />}
                            </div>
                            {opt.text}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
              {error && (
                <div className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600 dark:bg-red-900/20 dark:text-red-400">
                  <AlertTriangle size={14} /> {error}
                </div>
              )}
              <div className="flex gap-2">
                <button onClick={goToReview} className="flex-1 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100">
                  Review my selections
                </button>
                <button onClick={() => setStep("form")} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-500 transition hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
                  Back
                </button>
              </div>
            </div>
          )}

          {step === "review" && (
            <div className="flex flex-col gap-4">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">Review your groups</h3>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Based on your answers, you'll be added to the following groups. You'll receive one combined newsletter with content from all your groups.</p>
              </div>
              <div className="flex flex-col gap-2 max-h-[40vh] overflow-y-auto pr-1">
                {questions.map((q, qi) => {
                  const selectedOpts = q.options.filter(o => (answers[q.question_id] || []).includes(o.option_id));
                  if (selectedOpts.length === 0) return null;
                  return (
                    <div key={q.question_id} className="rounded-xl border border-slate-200 p-3.5 dark:border-slate-700">
                      <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">
                        <span className="text-brand-600 dark:text-brand-400">Q{qi + 1}.</span> {q.text}
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedOpts.map(opt => (
                          <span key={opt.option_id} className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                            <Check size={11} className="text-brand-600 dark:text-brand-400" />
                            {opt.text}
                            <span className="text-slate-400">→ {opt.group_name}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="rounded-xl bg-slate-50 p-4 dark:bg-slate-800/50">
                <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">You'll join {previewGroups.length} group(s):</p>
                <div className="flex flex-wrap gap-1.5">
                  {previewGroups.map(g => (
                    <span key={g} className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700 ring-1 ring-inset ring-brand-200 dark:bg-brand-900/20 dark:text-brand-300 dark:ring-brand-800">
                      <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
                      {g}
                    </span>
                  ))}
                </div>
              </div>
              {error && (
                <div className="flex items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600 dark:bg-red-900/20 dark:text-red-400">
                  <AlertTriangle size={14} /> {error}
                </div>
              )}
              <div className="flex gap-2">
                <button onClick={handleSubmit} disabled={submitting} className="flex-1 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100">
                  {submitting ? <Loader2 size={16} className="animate-spin" /> : "Confirm & create account"}
                </button>
                <button onClick={() => setStep("questions")} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-500 transition hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800">
                  Back
                </button>
              </div>
            </div>
          )}

          {step === "result" && (
            <div className="flex flex-col items-center gap-4 text-center">
              <motion.div
                initial={{ scale: 0, rotate: -180 }}
                animate={{ scale: 1, rotate: 0 }}
                transition={{ type: "spring", duration: 0.6 }}
                className="inline-grid h-16 w-16 place-items-center rounded-full bg-gradient-to-br from-emerald-400 to-emerald-600 text-white shadow-lg shadow-emerald-500/30"
              >
                <Check size={32} />
              </motion.div>
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">You're all set!</h3>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                  Welcome{name.trim() && `, ${name.trim()}`}. You've been added to {assignedGroups.length} group(s):
                </p>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {assignedGroups.map(g => (
                  <span key={g} className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3.5 py-1.5 text-xs font-semibold text-brand-700 ring-1 ring-inset ring-brand-200 dark:bg-brand-900/20 dark:text-brand-300 dark:ring-brand-800">
                    <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
                    {g}
                  </span>
                ))}
              </div>
              <p className="text-xs text-slate-400">You'll receive one combined newsletter with content from all your groups. Sign in anytime with your email to view them.</p>
              <button
                onClick={() => onRegistered(email.trim(), assignedGroups, authToken)}
                className="w-full rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100"
              >
                View my newsletters
              </button>
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}

function SignInModal({ onClose, onSignIn, emailInput, setEmailInput }: { onClose: () => void; onSignIn: (e: React.FormEvent) => void; emailInput: string; setEmailInput: (v: string) => void }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.96, opacity: 0, y: 8 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        exit={{ scale: 0.96, opacity: 0, y: 8 }}
        transition={{ type: "spring", duration: 0.4 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm overflow-hidden rounded-2xl bg-white shadow-2xl dark:bg-slate-900 dark:ring-1 dark:ring-slate-700"
      >
        <div className="border-b border-slate-100 px-6 pb-5 pt-6 dark:border-slate-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <Logo size={32} />
              <div>
                <h2 className="text-base font-bold tracking-tight text-slate-900 dark:text-white">Welcome back</h2>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">Sign in to view your newsletters</p>
              </div>
            </div>
            <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200">
              <X size={16} />
            </button>
          </div>
        </div>
        <div className="px-6 py-6">
          <form onSubmit={onSignIn} className="flex flex-col gap-4">
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Email address</label>
              <input
                type="email"
                value={emailInput}
                onChange={(e) => setEmailInput(e.target.value)}
                placeholder="you@company.com"
                className="input-field"
                autoFocus
              />
            </div>
            <button type="submit" className="w-full rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100">
              Sign in
            </button>
            <p className="text-center text-xs text-slate-400">
              Don't have an account yet?{" "}
              <button type="button" onClick={onClose} className="font-medium text-brand-600 hover:underline dark:text-brand-400">
                Create one
              </button>
            </p>
          </form>
        </div>
      </motion.div>
    </motion.div>
  );
}

export function UserView({ dark, onToggleDark }: { dark: boolean; onToggleDark: () => void }) {
  const [newsletters, setNewsletters] = useState<NewsletterListItem[]>([]);
  const [selected, setSelected] = useState<NewsletterListItem | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [userEmail, setUserEmail] = useState<string | null>(() => localStorage.getItem("user-email"));
  const [userToken, setUserToken] = useState<string | null>(() => localStorage.getItem("user-token"));
  const [emailInput, setEmailInput] = useState("");
  const [showRegistration, setShowRegistration] = useState(false);
  const [showSignIn, setShowSignIn] = useState(false);
  const [previewNewsletters, setPreviewNewsletters] = useState<NewsletterListItem[]>([]);

  const refresh = useCallback(() => {
    if (!userToken && !userEmail) { setNewsletters([]); setLoading(false); return; }
    setLoading(true);
    listMyNewsletters(userToken || "", userEmail || undefined)
      .then(setNewsletters)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [userToken, userEmail]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    listNewsletters().then(setPreviewNewsletters).catch(() => {});
  }, []);

  const handleEmailSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (emailInput.trim()) {
      setUserEmail(emailInput.trim());
      localStorage.setItem("user-email", emailInput.trim());
      setShowSignIn(false);
    }
  };

  const handleSignOut = () => {
    setUserEmail(null);
    setUserToken(null);
    setEmailInput("");
    localStorage.removeItem("user-email");
    localStorage.removeItem("user-token");
  };

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
      <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl dark:border-slate-800/80 dark:bg-slate-950/90">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-6 py-3.5">
          <div className="flex items-center gap-3">
            <Logo size={36} />
            <div>
              <h1 className="text-base font-bold tracking-tight text-slate-900 dark:text-white">Good News Agent</h1>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">Curated newsletters, tailored to you</p>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2.5">
            {userEmail ? (
              <div className="flex items-center gap-2.5">
                <div className="hidden items-center gap-2 rounded-full bg-slate-100 py-1 pl-1 pr-3 dark:bg-slate-800/60 sm:flex">
                  <div className="inline-grid h-6 w-6 place-items-center rounded-full bg-slate-900 text-[10px] font-bold text-white dark:bg-white dark:text-slate-900">
                    {userEmail.charAt(0).toUpperCase()}
                  </div>
                  <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{userEmail}</span>
                </div>
                <button
                  onClick={handleSignOut}
                  className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-500 transition hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                >
                  <LogOut size={13} />
                  Sign out
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowSignIn(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  Sign in
                </button>
                <button
                  onClick={() => setShowRegistration(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100"
                >
                  <UserPlus size={13} />
                  Create account
                </button>
              </div>
            )}
            <div className="h-5 w-px bg-slate-200 dark:bg-slate-700" />
            <button
              onClick={onToggleDark}
              className="rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              aria-label="Toggle dark mode"
            >
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-5xl p-6">
        {userEmail ? (
          <>
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
                      : "No newsletters have been sent to your groups yet."}
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
          </>
        ) : (
          /* Landing / Preview page for non-authenticated users */
          <div className="flex flex-col gap-10">
            {/* Hero */}
            <div className="flex flex-col items-center gap-6 py-10 text-center">
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5 }}
              >
                <Logo size={56} />
              </motion.div>
              <div className="flex flex-col gap-3">
                <h2 className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
                  Curated newsletters, <span className="text-brand-600 dark:text-brand-400">tailored to you</span>
                </h2>
                <p className="max-w-lg text-base leading-relaxed text-slate-500 dark:text-slate-400">
                  Create an account, answer a few questions about your interests, and receive curated newsletters delivered straight to your inbox. No noise — just the stories that matter to your groups.
                </p>
              </div>
              <div className="flex flex-col items-center gap-3 sm:flex-row">
                <button
                  onClick={() => setShowRegistration(true)}
                  className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100"
                >
                  <UserPlus size={16} />
                  Create your free account
                </button>
                <button
                  onClick={() => setShowSignIn(true)}
                  className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-6 py-3 text-sm font-medium text-slate-600 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  Sign in
                </button>
              </div>
            </div>

            {/* Feature highlights */}
            <div className="grid gap-4 sm:grid-cols-3">
              {[
                { icon: Search, title: "Personalized content", desc: "Answer a few questions and get placed in groups that match your interests." },
                { icon: Newspaper, title: "Curated sources", desc: "AI scans dozens of sources to deliver only the most relevant stories to your groups." },
                { icon: Clock, title: "Delivered to your inbox", desc: "Newsletters are sent directly to your email. Sign in anytime to browse the archive." },
              ].map((feature, i) => (
                <div key={i} className="card flex flex-col gap-3 p-5">
                  <div className="inline-grid h-10 w-10 place-items-center rounded-xl bg-brand-50 text-brand-600 dark:bg-brand-900/20 dark:text-brand-400">
                    <feature.icon size={20} />
                  </div>
                  <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100">{feature.title}</h3>
                  <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">{feature.desc}</p>
                </div>
              ))}
            </div>

            {/* Preview newsletters (blurred/locked) */}
            {previewNewsletters.length > 0 && (
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Newsletter preview</h3>
                  <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                    {previewNewsletters.length} available
                  </span>
                </div>
                <div className="relative grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {previewNewsletters.slice(0, 6).map((item) => {
                    const nl = item.newsletter as Newsletter;
                    const totalArticles = nl?.sections?.reduce((acc, s) => acc + s.items.length, 0) ?? 0;
                    return (
                      <div
                        key={item.run_id}
                        className="card flex flex-col p-5"
                      >
                        <div className="mb-2 flex items-center gap-2 text-xs text-slate-400">
                          <Clock size={11} />
                          {formatDate(item.created_at)}
                        </div>
                        <h3 className="text-base font-bold leading-snug text-slate-800 dark:text-slate-100">
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
                      </div>
                    );
                  })}
                  {/* Overlay with CTA */}
                  <div className="absolute inset-0 flex items-center justify-center rounded-2xl bg-gradient-to-b from-white/40 via-white/60 to-white/90 backdrop-blur-sm dark:from-slate-950/40 dark:via-slate-950/60 dark:to-slate-950/90">
                    <div className="flex flex-col items-center gap-3 text-center">
                      <div className="inline-grid h-12 w-12 place-items-center rounded-full bg-white shadow-lg dark:bg-slate-800">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-brand-600 dark:text-brand-400">
                          <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
                          <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                        </svg>
                      </div>
                      <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Sign in to read full newsletters</p>
                      <button
                        onClick={() => setShowRegistration(true)}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white transition hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100"
                      >
                        <UserPlus size={13} />
                        Create account
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <AnimatePresence>
        {showRegistration && (
          <RegistrationModal
            onClose={() => setShowRegistration(false)}
            onRegistered={(email, _groups, token) => {
              setShowRegistration(false);
              setUserEmail(email);
              setUserToken(token);
              localStorage.setItem("user-email", email);
              localStorage.setItem("user-token", token);
              setEmailInput("");
            }}
          />
        )}
        {showSignIn && (
          <SignInModal
            onClose={() => setShowSignIn(false)}
            onSignIn={handleEmailSubmit}
            emailInput={emailInput}
            setEmailInput={setEmailInput}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
