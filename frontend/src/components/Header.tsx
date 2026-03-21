import { Activity, Clock, Wifi, WifiOff } from "lucide-react";
import { useStore } from "../core/store";
import { TIMEFRAMES } from "../types/api";
import type { Timeframe } from "../types/api";

export default function Header() {
  const symbol = useStore((s) => s.symbol);
  const timeframe = useStore((s) => s.timeframe);
  const setTimeframe = useStore((s) => s.setTimeframe);
  const wsStatus = useStore((s) => s.wsStatus);
  const isRunning = useStore((s) => s.isRunning);
  const uptime = useStore((s) => s.uptime);

  const formatUptime = (seconds: number): string => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  };

  return (
    <header className="flex items-center justify-between px-4 py-2 bg-panel-surface border-b border-panel-border">
      {/* Symbol */}
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-text-primary tracking-wide">
          {symbol}
        </h1>
        <span
          className={`badge ${isRunning ? "badge-green" : "badge-red"}`}
        >
          <Activity size={12} className="mr-1" />
          {isRunning ? "Running" : "Stopped"}
        </span>
      </div>

      {/* Timeframe selector */}
      <div className="flex items-center gap-1">
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            onClick={() => setTimeframe(tf as Timeframe)}
            className={`px-2.5 py-1 text-xs font-mono rounded transition-colors ${
              timeframe === tf
                ? "bg-accent-blue/20 text-accent-blue border border-accent-blue/30"
                : "text-text-secondary hover:text-text-primary hover:bg-panel-hover"
            }`}
          >
            {tf}
          </button>
        ))}
      </div>

      {/* Status indicators */}
      <div className="flex items-center gap-4 text-xs text-text-secondary">
        <div className="flex items-center gap-1.5">
          {wsStatus === "connected" ? (
            <Wifi size={14} className="text-accent-green" />
          ) : (
            <WifiOff size={14} className="text-accent-red" />
          )}
          <span className="capitalize">{wsStatus}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Clock size={14} />
          <span>{formatUptime(uptime)}</span>
        </div>
      </div>
    </header>
  );
}
