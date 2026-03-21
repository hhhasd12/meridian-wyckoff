import {
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Shield,
} from "lucide-react";
import { useStore } from "../core/store";

export default function SignalPanel() {
  const rightOpen = useStore((s) => s.rightPanelOpen);
  const toggle = useStore((s) => s.toggleRightPanel);
  const signals = useStore((s) => s.signals);
  const positions = useStore((s) => s.positions);

  if (!rightOpen) {
    return (
      <button
        onClick={toggle}
        className="flex items-center justify-center w-6 bg-panel-surface
          border-l border-panel-border hover:bg-panel-hover transition-colors"
        title="Expand Signal Panel"
      >
        <ChevronLeft size={14} className="text-text-muted" />
      </button>
    );
  }

  return (
    <aside className="w-60 flex-shrink-0 bg-panel-surface border-l border-panel-border flex flex-col overflow-hidden">
      {/* Header */}
      <div className="panel-header">
        <span>Signals & Positions</span>
        <button onClick={toggle} className="hover:text-text-primary">
          <ChevronRight size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Signals */}
        <div className="p-3 border-b border-panel-border">
          <div className="text-xs text-text-secondary mb-2 font-medium">
            Recent Signals
          </div>
          <div className="space-y-1.5">
            {signals.length > 0 ? (
              signals.slice(0, 6).map((sig) => (
                <div
                  key={sig.id}
                  className="flex items-start gap-2 text-xs p-1.5 rounded bg-panel-bg"
                >
                  {sig.signal.includes("buy") ? (
                    <TrendingUp
                      size={14}
                      className="text-accent-green flex-shrink-0 mt-0.5"
                    />
                  ) : sig.signal.includes("sell") ? (
                    <TrendingDown
                      size={14}
                      className="text-accent-red flex-shrink-0 mt-0.5"
                    />
                  ) : (
                    <Shield
                      size={14}
                      className="text-text-muted flex-shrink-0 mt-0.5"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between">
                      <span
                        className={`font-medium uppercase ${
                          sig.signal.includes("buy")
                            ? "text-accent-green"
                            : sig.signal.includes("sell")
                              ? "text-accent-red"
                              : "text-text-secondary"
                        }`}
                      >
                        {sig.signal.replace("_", " ")}
                      </span>
                      <span className="text-text-muted font-mono">
                        {(sig.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="text-text-muted truncate">
                      Phase {sig.phase} · {sig.state}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-text-muted text-xs italic">
                No signals yet
              </div>
            )}
          </div>
        </div>

        {/* Positions */}
        <div className="p-3">
          <div className="text-xs text-text-secondary mb-2 font-medium">
            Open Positions
          </div>
          <div className="space-y-2">
            {positions.length > 0 ? (
              positions.map((pos, i) => (
                <div
                  key={i}
                  className="p-2 rounded bg-panel-bg text-xs space-y-1"
                >
                  <div className="flex justify-between">
                    <span className="font-medium text-text-primary">
                      {pos.symbol}
                    </span>
                    <span
                      className={`badge ${
                        pos.side === "LONG" ? "badge-green" : "badge-red"
                      }`}
                    >
                      {pos.side ?? "—"}
                    </span>
                  </div>
                  <div className="flex justify-between text-text-secondary">
                    <span>Entry</span>
                    <span className="font-mono text-text-primary">
                      {pos.entry_price?.toFixed(2) ?? "—"}
                    </span>
                  </div>
                  {pos.pnl_pct !== undefined && (
                    <div className="flex justify-between text-text-secondary">
                      <span>PnL</span>
                      <span
                        className={`font-mono ${
                          pos.pnl_pct >= 0
                            ? "text-accent-green"
                            : "text-accent-red"
                        }`}
                      >
                        {pos.pnl_pct >= 0 ? "+" : ""}
                        {pos.pnl_pct.toFixed(2)}%
                      </span>
                    </div>
                  )}
                  {pos.stop_loss && (
                    <div className="flex justify-between text-text-secondary">
                      <span>SL</span>
                      <span className="font-mono text-accent-red">
                        {pos.stop_loss.toFixed(2)}
                      </span>
                    </div>
                  )}
                  {pos.leverage && (
                    <div className="flex justify-between text-text-secondary">
                      <span>Leverage</span>
                      <span className="font-mono text-text-primary">
                        {pos.leverage}x
                      </span>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="text-text-muted text-xs italic">
                No open positions
              </div>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
}
