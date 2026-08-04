import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Mail, Check, Loader2, AlertCircle } from "lucide-react";
import { unsubscribe as unsubscribeApi } from "../services/api";

export function UnsubscribeView() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const emailParam = params.get("email");
    if (emailParam) {
      setEmail(emailParam);
      doUnsubscribe(emailParam);
    }
  }, []);

  const doUnsubscribe = async (emailToUnsub: string) => {
    setStatus("loading");
    try {
      const result = await unsubscribeApi(emailToUnsub);
      setStatus("done");
      setMessage(
        result.status === "unsubscribed"
          ? "You've been unsubscribed. You won't receive any more newsletters."
          : "We couldn't find that email. You may have already unsubscribed."
      );
    } catch {
      setStatus("error");
      setMessage("Something went wrong. Please try again.");
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (email.trim()) doUnsubscribe(email.trim());
  };

  return (
    <div className="grid min-h-screen place-items-center bg-slate-50 dark:bg-slate-950">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md px-6"
      >
        <div className="card overflow-hidden p-8">
          <div className="flex flex-col items-center text-center">
            <div className="inline-grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-br from-slate-400 to-slate-600 text-white shadow-lg">
              <Mail size={30} />
            </div>
            <h1 className="mt-5 text-xl font-bold text-slate-900 dark:text-white">
              Unsubscribe
            </h1>
            <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
              We're sorry to see you go. Confirm your email to stop receiving newsletters.
            </p>
          </div>

          {status === "done" ? (
            <div className="mt-7 flex flex-col items-center gap-3 text-center">
              <div className="inline-grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400">
                <Check size={24} />
              </div>
              <p className="text-sm text-slate-600 dark:text-slate-300">{message}</p>
            </div>
          ) : status === "error" ? (
            <div className="mt-7 flex items-center gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">
              <AlertCircle size={16} className="flex-shrink-0" />
              <span>{message}</span>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="mt-7 flex flex-col gap-4">
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Email address
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  required
                  disabled={status === "loading"}
                  className="input-field"
                />
              </div>
              <button
                type="submit"
                disabled={!email.trim() || status === "loading"}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100"
              >
                {status === "loading" ? (
                  <><Loader2 size={16} className="animate-spin" /> Unsubscribing…</>
                ) : (
                  "Unsubscribe"
                )}
              </button>
            </form>
          )}
        </div>
      </motion.div>
    </div>
  );
}
