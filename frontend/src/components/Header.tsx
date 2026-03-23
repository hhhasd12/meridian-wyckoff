import { useStore } from "../core/store";
import { TIMEFRAMES } from "../types/api";
import type { Timeframe } from "../types/api";

export default function Header() {
  const symbol = useStore((s) => s.symbol);
  const timeframe = useStore((s) => s.timeframe);
  const setTimeframe = useStore((s) => s.setTimeframe);
  const isRunning = useStore((s) => s.isRunning);

  return (
    <header className="flex items-center justify-between px-4 py-1.5 bg-panel-surface border-b border-panel-border">
      {/* Symbol + Mode badge */}
      <div className="flex items-center gap-3">
        <h1 className="text-base font-bold text-text-primary tracking-wide font-mono">
          {symbol}
        </h1>
        <span
          className={`badge text-xs ${
            isRunning ? "badge-green" : "badge-red"
          }`}
        >
          {isRunning ? "模拟盘" : "已停止"}
        </span>
      </div>

      {/* Timeframe selector */}
      <div className="flex items-center gap-1">
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            onClick={() => setTimeframe(tf as Timeframe)}
            className={`px-2 py-1 text-[13px] font-mono rounded transition-colors ${
              timeframe === tf
                ? "bg-accent-blue/20 text-accent-blue border border-accent-blue/30"
                : "text-text-secondary hover:text-text-primary hover:bg-panel-hover/30"
            }`}
          >
            {tf}
          </button>
        ))}
      </div>
    </header>
  );
}
