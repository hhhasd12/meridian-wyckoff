import { useStore } from "../core/store";

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: "text-text-muted",
  INFO: "text-accent-blue",
  WARNING: "text-accent-yellow",
  ERROR: "text-accent-red",
};

export default function LogsTab() {
  const logs = useStore((s) => s.logs);

  if (logs.length === 0) {
    return (
      <div className="text-text-muted text-xs italic p-2">
        No log entries
      </div>
    );
  }

  return (
    <div className="font-mono text-[11px] space-y-0.5 p-1">
      {logs.map((log, i) => (
        <div key={i} className="flex gap-2 hover:bg-panel-hover px-1 rounded">
          <span className="text-text-muted flex-shrink-0 w-16">
            {new Date(log.timestamp).toLocaleTimeString()}
          </span>
          <span
            className={`flex-shrink-0 w-8 ${
              LEVEL_COLORS[log.level] ?? "text-text-secondary"
            }`}
          >
            {log.level.slice(0, 4)}
          </span>
          <span className="text-text-muted flex-shrink-0 w-24 truncate">
            {log.module}
          </span>
          <span className="text-text-primary">{log.message}</span>
        </div>
      ))}
    </div>
  );
}
