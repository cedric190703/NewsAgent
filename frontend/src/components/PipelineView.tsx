import { motion, AnimatePresence } from "motion/react";
import { CheckCircle2, Circle, Loader2, AlertCircle, SkipForward } from "lucide-react";

import type { NodeEvent, Topology } from "../services/api";
import { cn } from "../lib/utils";

interface PipelineViewProps {
  topology: Topology | null;
  events: NodeEvent[];
  active: boolean;
}

const STATUS_ICON: Record<string, React.ReactNode> = {
  done: <CheckCircle2 size={18} className="text-emerald-500" />,
  running: <Loader2 size={18} className="text-brand-500 animate-spin" />,
  error: <AlertCircle size={18} className="text-red-500" />,
  skipped: <SkipForward size={18} className="text-slate-400" />,
  pending: <Circle size={18} className="text-slate-300 dark:text-slate-600" />,
};

const STATUS_RING: Record<string, string> = {
  done: "ring-emerald-500/20",
  running: "ring-brand-500/30",
  error: "ring-red-500/20",
  pending: "ring-slate-200 dark:ring-slate-700",
};

export function PipelineView({ topology, events, active }: PipelineViewProps) {
  const topLevelStatus: Record<string, string> = {};
  for (const evt of events) {
    if (evt.branch) {
      topLevelStatus[evt.node] = topLevelStatus[evt.node] ?? "running";
    } else {
      topLevelStatus[evt.node] = evt.status;
    }
  }

  if (!topology) {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-400">
        <Loader2 size={16} className="animate-spin" />
        Loading graph topology…
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1">
      {topology.nodes.map((node, i) => {
        const status = topLevelStatus[node.id] ?? "pending";
        const statusClass =
          status === "done"
            ? "node-done"
            : status === "running"
              ? "node-running"
              : status === "error"
                ? "node-error"
                : "node-pending";

        const branchEvents = events.filter((e) => e.node === node.id && e.branch);

        return (
          <div key={node.id}>
            <motion.div
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05, duration: 0.3 }}
              className={cn(
                "relative flex items-center gap-3.5 rounded-xl border px-4 py-3 transition-all duration-300",
                statusClass,
                status === "running" && "ring-2 " + STATUS_RING.running,
              )}
            >
              <div
                className={cn(
                  "flex-shrink-0 rounded-full p-1.5 ring-2 transition-all",
                  STATUS_RING[status] ?? STATUS_RING.pending,
                )}
              >
                {STATUS_ICON[status] ?? STATUS_ICON.pending}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                    {node.label}
                  </span>
                  <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400 dark:text-slate-500">
                    {node.kind}
                  </span>
                </div>
                <p className="truncate text-xs text-slate-500 dark:text-slate-400">
                  {node.description}
                </p>
              </div>
              {branchEvents.length > 0 && (
                <motion.span
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="flex-shrink-0 rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-bold text-brand-600 dark:bg-brand-900/40 dark:text-brand-300"
                >
                  {branchEvents.length}
                </motion.span>
              )}
            </motion.div>

            <AnimatePresence>
              {branchEvents.length > 0 && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="ml-7 mt-1 mb-1 flex flex-col gap-0.5 overflow-hidden"
                >
                  {branchEvents.slice(-4).map((evt, j) => (
                    <motion.div
                      key={`${evt.branch}-${j}`}
                      initial={{ opacity: 0, y: -4 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: j * 0.05 }}
                      className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-xs text-slate-500 dark:text-slate-400"
                    >
                      {STATUS_ICON[evt.status] ?? STATUS_ICON.pending}
                      <span className="truncate">{evt.detail}</span>
                    </motion.div>
                  ))}
                  {branchEvents.length > 4 && (
                    <div className="px-2.5 text-xs text-slate-400">
                      +{branchEvents.length - 4} more branches…
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>

            {i < topology.nodes.length - 1 && (
              <div className="ml-7 h-3 w-px bg-slate-200 dark:bg-slate-700" />
            )}
          </div>
        );
      })}
    </div>
  );
}
