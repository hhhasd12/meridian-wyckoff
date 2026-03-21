import { useStore } from "../core/store";
import type { WyckoffPhase } from "../types/api";
import { ChevronLeft, ChevronRight } from "lucide-react";

const PHASE_COLORS: Record<WyckoffPhase, string> = {
  A: "text-text-secondary",
  B: "text-accent-yellow",
  C: "text-accent-green",
  D: "text-accent-blue",
  E: "text-accent-purple",
  IDLE: "text-text-muted",
};

const PHASE_BG: Record<WyckoffPhase, string> = {
  A: "bg-text-secondary/10",
  B: "bg-accent-yellow/10",
  C: "bg-accent-green/10",
  D: "bg-accent-blue/10",
  E: "bg-accent-purple/10",
  IDLE: "bg-text-muted/10",
};

export default function WyckoffPanel() {
  const wyckoff = useStore((s) => s.wyckoffState);
  const leftOpen = useStore((s) => s.leftPanelOpen);
  const toggle = useStore((s) => s.toggleLeftPanel);

  if (!leftOpen) {
    return (
      <button
        onClick={toggle}
        className="flex items-center justify-center w-6 bg-panel-surface
          border-r border-panel-border hover:bg-panel-hover transition-colors"
        title="Expand Wyckoff Panel"
      >
        <ChevronRight size={14} className="text-text-muted" />
      </button>
    );
  }

  const phase = wyckoff?.phase ?? "IDLE";
  const phaseColor = PHASE_COLORS[phase] ?? "text-text-muted";
  const phaseBg = PHASE_BG[phase] ?? "bg-text-muted/10";

  return (
    <aside className="w-56 flex-shrink-0 bg-panel-surface border-r border-panel-border flex flex-col overflow-hidden">
      {/* Header */}
      <div className="panel-header">
        <span>Wyckoff State</span>
        <button onClick={toggle} className="hover:text-text-primary">
          <ChevronLeft size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* Phase display */}
        <div className="text-center">
          <div className="text-xs text-text-secondary mb-1">Current Phase</div>
          <div
            className={`text-3xl font-bold ${phaseColor} ${phaseBg} rounded-lg py-2`}
          >
            {phase}
          </div>
          <div className="text-xs text-text-muted mt-1">
            {wyckoff?.direction ?? "IDLE"}
          </div>
        </div>

        {/* State info */}
        <div className="space-y-2 text-xs">
          <div className="flex justify-between">
            <span className="text-text-secondary">State</span>
            <span className="font-mono text-text-primary">
              {wyckoff?.current_state ?? "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Confidence</span>
            <span className="font-mono text-text-primary">
              {wyckoff ? `${(wyckoff.confidence * 100).toFixed(0)}%` : "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Signal</span>
            <span
              className={`font-mono ${
                wyckoff?.signal === "buy_signal"
                  ? "text-accent-green"
                  : wyckoff?.signal === "sell_signal"
                    ? "text-accent-red"
                    : "text-text-muted"
              }`}
            >
              {wyckoff?.signal ?? "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Strength</span>
            <span className="font-mono text-text-primary">
              {wyckoff?.signal_strength ?? "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Heritage</span>
            <span className="font-mono text-text-primary">
              {wyckoff ? wyckoff.heritage_score.toFixed(2) : "—"}
            </span>
          </div>
        </div>

        {/* Phase selector (visual) */}
        <div>
          <div className="text-xs text-text-secondary mb-1.5">
            Phase Progress
          </div>
          <div className="flex gap-1">
            {(["A", "B", "C", "D", "E"] as const).map((p) => (
              <div
                key={p}
                className={`flex-1 text-center py-1 rounded text-xs font-bold transition-colors ${
                  phase === p
                    ? `${PHASE_COLORS[p]} ${PHASE_BG[p]} ring-1 ring-current`
                    : "text-text-muted bg-panel-bg"
                }`}
              >
                {p}
              </div>
            ))}
          </div>
        </div>

        {/* Evidence chain */}
        <div>
          <div className="text-xs text-text-secondary mb-1.5">
            Evidence Chain
          </div>
          <div className="space-y-1">
            {wyckoff?.evidences && wyckoff.evidences.length > 0 ? (
              wyckoff.evidences.slice(0, 8).map((ev, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-xs"
                >
                  <span className="text-text-secondary truncate mr-2">
                    {ev.evidence_type}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <div className="w-12 h-1.5 bg-panel-bg rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent-cyan rounded-full"
                        style={{ width: `${ev.confidence * 100}%` }}
                      />
                    </div>
                    <span className="font-mono text-text-primary w-8 text-right">
                      {ev.confidence.toFixed(2)}
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-text-muted text-xs italic">
                No evidence data
              </div>
            )}
          </div>
        </div>

        {/* Critical levels */}
        {wyckoff?.critical_levels &&
          Object.keys(wyckoff.critical_levels).length > 0 && (
            <div>
              <div className="text-xs text-text-secondary mb-1.5">
                Critical Levels
              </div>
              <div className="space-y-1">
                {Object.entries(wyckoff.critical_levels).map(([k, v]) => (
                  <div
                    key={k}
                    className="flex justify-between text-xs"
                  >
                    <span className="text-text-secondary">{k}</span>
                    <span className="font-mono text-accent-yellow">
                      {v.toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
      </div>
    </aside>
  );
}
