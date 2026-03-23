import { useStore } from "../core/store";

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: "text-text-muted",
  INFO: "text-accent-blue",
  WARNING: "text-accent-yellow",
  ERROR: "text-accent-red",
};

const LEVEL_LABELS: Record<string, string> = {
  DEBUG: "调试",
  INFO: "信息",
  WARNING: "警告",
  ERROR: "错误",
};

export default function LogsTab() {
  const logs = useStore((s) => s.logs);

  if (logs.length === 0) {
    return (
      <div className="text-text-muted text-sm italic p-2">
        日志服务未启用 — 后端需新增 get_recent_logs() 方法
      </div>
    );
  }

  return (
    <div className="font-mono text-[13px] space-y-0.5 p-1">
      {logs.map((log, i) => (
        <div key={i} className="flex gap-2 hover:bg-panel-hover/30 px-1 rounded">
          <span className="text-text-muted flex-shrink-0 w-16">
            {new Date(log.timestamp).toLocaleTimeString()}
          </span>
          <span
            className={`flex-shrink-0 w-8 ${
              LEVEL_COLORS[log.level] ?? "text-text-secondary"
            }`}
          >
            {LEVEL_LABELS[log.level] ?? (log.level ?? "INFO").slice(0, 4)}
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
