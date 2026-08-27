import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { CalendarClock, Play, Plus, Power, Trash2 } from "lucide-react";

import {
  ApiError,
  type RunConfig,
  type Schedule,
  createSchedule,
  deleteSchedule,
  listSchedules,
  runScheduleNow,
  toggleSchedule,
} from "../services/api";
import { cn } from "../lib/utils";

interface SchedulesPanelProps {
  /** The run settings currently configured in the sidebar. */
  currentConfig: RunConfig;
  onRunStarted: (runId: string) => void;
}

const PRESETS: { label: string; cron: string }[] = [
  { label: "Every morning", cron: "0 8 * * *" },
  { label: "Weekday mornings", cron: "0 8 * * mon-fri" },
  { label: "Monday weekly", cron: "0 9 * * mon" },
  { label: "Hourly", cron: "0 * * * *" },
];

function formatWhen(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SchedulesPanel({ currentConfig, onRunStarted }: SchedulesPanelProps) {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [cron, setCron] = useState(PRESETS[0].cron);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setSchedules(await listSchedules());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load schedules");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const guard = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };

  const add = () =>
    guard(async () => {
      if (!currentConfig.theme.trim()) {
        throw new ApiError(400, "Enter a theme before scheduling it.");
      }
      await createSchedule([currentConfig.theme.trim()], cron, currentConfig);
    });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={cron}
          onChange={(event) => setCron(event.target.value)}
          className="input-field flex-1 py-2 text-xs"
          aria-label="Schedule frequency"
        >
          {PRESETS.map((preset) => (
            <option key={preset.cron} value={preset.cron}>
              {preset.label} ({preset.cron})
            </option>
          ))}
        </select>
        <button type="button" onClick={add} disabled={busy} className="btn-ghost">
          <Plus size={15} />
          Schedule
        </button>
      </div>

      {error && <p className="text-xs text-red-500">{error}</p>}

      <AnimatePresence initial={false}>
        {schedules.length === 0 ? (
          <p className="text-xs text-slate-400">
            No schedules yet. The server runs these automatically and stores each
            result in history.
          </p>
        ) : (
          schedules.map((schedule) => (
            <motion.div
              key={schedule.schedule_id}
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, height: 0 }}
              className={cn(
                "flex items-center gap-2 rounded-xl border p-2.5 text-xs",
                schedule.enabled
                  ? "border-slate-200 dark:border-slate-700"
                  : "border-dashed border-slate-200 opacity-60 dark:border-slate-700",
              )}
            >
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">
                  {schedule.themes.join(", ") || schedule.config?.theme || "Untitled"}
                </div>
                <div className="flex items-center gap-1 text-slate-400">
                  <CalendarClock size={11} />
                  <span className="font-mono">{schedule.cron_expr}</span>
                  <span>· next {formatWhen(schedule.next_run_at)}</span>
                </div>
              </div>
              <button
                type="button"
                title="Run now"
                disabled={busy}
                onClick={() =>
                  guard(async () => {
                    const { run_id } = await runScheduleNow(schedule.schedule_id);
                    onRunStarted(run_id);
                  })
                }
                className="text-slate-300 transition hover:text-brand-500"
              >
                <Play size={13} />
              </button>
              <button
                type="button"
                title={schedule.enabled ? "Disable" : "Enable"}
                disabled={busy}
                onClick={() =>
                  guard(() =>
                    toggleSchedule(schedule.schedule_id, !schedule.enabled).then(() => undefined),
                  )
                }
                className={cn(
                  "transition",
                  schedule.enabled
                    ? "text-emerald-500 hover:text-emerald-600"
                    : "text-slate-300 hover:text-slate-500",
                )}
              >
                <Power size={13} />
              </button>
              <button
                type="button"
                title="Delete"
                disabled={busy}
                onClick={() => guard(() => deleteSchedule(schedule.schedule_id))}
                className="text-slate-300 transition hover:text-red-500"
              >
                <Trash2 size={13} />
              </button>
            </motion.div>
          ))
        )}
      </AnimatePresence>
    </div>
  );
}
