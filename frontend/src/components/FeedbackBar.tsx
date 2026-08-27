import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Check, Star } from "lucide-react";

import { ApiError, submitFeedback } from "../services/api";
import { cn } from "../lib/utils";

interface FeedbackBarProps {
  runId: string;
}

const RATINGS = [1, 2, 3, 4, 5];

/** Ratings are persisted server-side so answer quality can be tracked over time. */
export function FeedbackBar({ runId }: FeedbackBarProps) {
  const [rating, setRating] = useState<number | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const send = async (value: number, note: string) => {
    setSending(true);
    setError(null);
    try {
      await submitFeedback(runId, value, note);
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save feedback");
    } finally {
      setSending(false);
    }
  };

  if (sent) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="flex items-center justify-center gap-2 text-sm text-emerald-600 dark:text-emerald-400"
      >
        <Check size={15} />
        Thanks — your rating was saved.
      </motion.div>
    );
  }

  return (
    <div className="card flex flex-col gap-3 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
          Was this newsletter useful?
        </span>
        <div className="flex items-center gap-0.5" onMouseLeave={() => setHovered(null)}>
          {RATINGS.map((value) => {
            const active = (hovered ?? rating ?? 0) >= value;
            return (
              <button
                key={value}
                type="button"
                aria-label={`Rate ${value} out of 5`}
                onMouseEnter={() => setHovered(value)}
                onClick={() => setRating(value)}
                className="rounded p-1 transition hover:scale-110"
              >
                <Star
                  size={18}
                  className={cn(
                    "transition-colors",
                    active ? "text-amber-400" : "text-slate-300 dark:text-slate-600",
                  )}
                  fill={active ? "currentColor" : "none"}
                />
              </button>
            );
          })}
        </div>
      </div>

      <AnimatePresence>
        {rating !== null && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="flex flex-col gap-2 overflow-hidden"
          >
            <textarea
              className="input-field min-h-[68px] resize-y"
              placeholder="What worked, what didn't? (optional)"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              maxLength={2000}
            />
            <button
              type="button"
              className="btn-primary self-start"
              disabled={sending}
              onClick={() => send(rating, comment)}
            >
              {sending ? "Saving…" : "Send feedback"}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
