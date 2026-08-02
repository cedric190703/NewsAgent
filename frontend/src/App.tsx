import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Shield,
  Newspaper,
  Lock,
  Loader2,
  ArrowLeft,
  Moon,
  Sun,
  AlertCircle,
} from "lucide-react";

import { UserView } from "./components/UserView";
import { AdminView } from "./components/AdminView";
import { verifyAdminKey } from "./services/api";

type AuthState = "user" | "login" | "admin";

export function App() {
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem("dark-mode");
    return saved === "true" || (!saved && window.matchMedia("(prefers-color-scheme: dark)").matches);
  });

  const [authState, setAuthState] = useState<AuthState>(() => {
    const saved = localStorage.getItem("admin-authed");
    return saved === "true" ? "admin" : "user";
  });

  const [adminKey, setAdminKey] = useState(() => localStorage.getItem("admin-key") || "");

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("dark-mode", String(dark));
  }, [dark]);

  const toggleDark = () => setDark(!dark);

  const handleLogin = async (key: string) => {
    const valid = await verifyAdminKey(key);
    if (valid) {
      setAdminKey(key);
      localStorage.setItem("admin-key", key);
      localStorage.setItem("admin-authed", "true");
      setAuthState("admin");
      return true;
    }
    return false;
  };

  const handleLogout = () => {
    localStorage.removeItem("admin-authed");
    setAuthState("user");
  };

  if (authState === "admin") {
    return (
      <AdminView
        dark={dark}
        onToggleDark={toggleDark}
        adminKey={adminKey}
        onLogout={handleLogout}
      />
    );
  }

  if (authState === "login") {
    return (
      <LoginScreen
        dark={dark}
        onToggleDark={toggleDark}
        onBack={() => setAuthState("user")}
        onLogin={handleLogin}
      />
    );
  }

  return (
    <div className="relative">
      <UserView dark={dark} onToggleDark={toggleDark} />
      <button
        onClick={() => setAuthState("login")}
        className="fixed bottom-6 right-6 inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-500 shadow-lg transition hover:text-brand-600 hover:ring-2 hover:ring-brand-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400"
        title="Admin access"
      >
        <Shield size={16} />
        Admin
      </button>
    </div>
  );
}

function LoginScreen({
  dark,
  onToggleDark,
  onBack,
  onLogin,
}: {
  dark: boolean;
  onToggleDark: () => void;
  onBack: () => void;
  onLogin: (key: string) => Promise<boolean>;
}) {
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) return;
    setLoading(true);
    setError(null);
    const valid = await onLogin(password.trim());
    if (!valid) {
      setError("Invalid admin password. Please try again.");
      setLoading(false);
    }
  };

  return (
    <div className="relative grid min-h-screen place-items-center bg-slate-50 dark:bg-slate-950">
      <div
        className="absolute inset-0 opacity-[0.03] dark:opacity-[0.06]"
        style={{
          backgroundImage:
            "radial-gradient(circle at 25% 25%, #6366f1 0%, transparent 50%), radial-gradient(circle at 75% 75%, #a855f7 0%, transparent 50%)",
        }}
      />

      <button
        onClick={onToggleDark}
        className="absolute top-6 right-6 rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 dark:hover:bg-slate-800"
        aria-label="Toggle dark mode"
      >
        {dark ? <Sun size={18} /> : <Moon size={18} />}
      </button>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="relative w-full max-w-md px-6"
      >
        <div className="card overflow-hidden p-8">
          <div className="flex flex-col items-center text-center">
            <div className="relative mb-5">
              <div className="inline-grid h-16 w-16 place-items-center rounded-2xl bg-gradient-to-br from-brand-500 to-purple-600 text-white shadow-lg shadow-brand-500/30">
                <Newspaper size={30} />
              </div>
              <div className="absolute -bottom-1 -right-1 inline-grid h-7 w-7 place-items-center rounded-full bg-slate-100 dark:bg-slate-800">
                <Lock size={14} className="text-brand-600 dark:text-brand-400" />
              </div>
            </div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white">
              Admin Dashboard
            </h1>
            <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">
              Sign in to manage newsletters, topics, and subscribers
            </p>
          </div>

          <form onSubmit={handleSubmit} className="mt-7 flex flex-col gap-4">
            <div>
              <label
                className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400"
                htmlFor="adminPassword"
              >
                Admin Password
              </label>
              <div className="relative">
                <Lock
                  size={16}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <input
                  id="adminPassword"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your admin password…"
                  autoFocus
                  disabled={loading}
                  className="input-field pl-11"
                />
              </div>
            </div>

            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="flex items-center gap-2 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400"
                >
                  <AlertCircle size={16} className="flex-shrink-0" />
                  <span>{error}</span>
                </motion.div>
              )}
            </AnimatePresence>

            <button
              type="submit"
              disabled={!password.trim() || loading}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-600 to-purple-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-brand-500/20 transition hover:shadow-brand-500/40 disabled:opacity-50 disabled:shadow-none"
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Verifying…
                </>
              ) : (
                <>
                  <Shield size={16} />
                  Sign In
                </>
              )}
            </button>
          </form>

          <button
            onClick={onBack}
            className="mt-5 inline-flex w-full items-center justify-center gap-1.5 text-xs font-medium text-slate-400 transition hover:text-slate-600 dark:hover:text-slate-300"
          >
            <ArrowLeft size={13} />
            Back to newsletter viewer
          </button>
        </div>

        <p className="mt-6 text-center text-xs text-slate-400">
          Protected area · Authorized personnel only
        </p>
      </motion.div>
    </div>
  );
}
