import { useStore } from "../core/store";
import type { WyckoffPhase } from "../types/api";
import { ChevronLeft, ChevronRight } from "lucide-react";
import MultiTFStatus from "./MultiTFStatus";

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

const DIRECTION_MAP: Record<string, string> = {
  ACCUMULATION: "吸筹",
  DISTRIBUTION: "派发",
  TRENDING: "趋势",
  IDLE: "空闲",
};

const SIGNAL_MAP: Record<string, string> = {
  buy_signal: "买入信号",
  sell_signal: "卖出信号",
  no_signal: "无信号",
};

const STRENGTH_MAP: Record<string, string> = {
  strong: "强",
  medium: "中",
  weak: "弱",
  none: "无",
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
          border-r border-panel-border hover:bg-panel-hover/30 transition-colors"
        title="展开威科夫面板"
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
        <span>威科夫状态</span>
        <button onClick={toggle} className="hover:text-text-primary">
          <ChevronLeft size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {!wyckoff ? (
          /* Skeleton loading */
          <div className="space-y-3 animate-pulse">
            <div className="text-center">
              <div className="h-3 bg-panel-border/30 rounded w-16 mx-auto mb-2" />
              <div className="h-12 bg-panel-border/20 rounded-lg" />
            </div>
            <div className="space-y-2">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="flex justify-between">
                  <div className="h-3 bg-panel-border/30 rounded w-12" />
                  <div className="h-3 bg-panel-border/30 rounded w-16" />
                </div>
              ))}
            </div>
            <div className="h-6 bg-panel-border/20 rounded" />
          </div>
        ) : (
        <>
        {/* Phase display */}
        <div className="text-center">
          <div className="text-xs text-text-secondary mb-1">当前阶段</div>
          <div
            className={`text-3xl font-bold ${phaseColor} ${phaseBg} rounded py-2`}
          >
            {phase}
          </div>
          <div className="text-sm text-text-muted mt-1">
            {DIRECTION_MAP[wyckoff?.direction ?? "IDLE"] ?? wyckoff?.direction ?? "空闲"}
          </div>
        </div>

        {/* State info */}
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-text-secondary">状态</span>
            <span className="font-mono text-text-primary">
              {wyckoff?.current_state ?? "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">置信度</span>
            <span className="font-mono text-text-primary">
              {wyckoff ? `${((wyckoff.confidence ?? 0) * 100).toFixed(0)}%` : "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">信号</span>
            <span
              className={`font-mono ${
                wyckoff?.signal === "buy_signal"
                  ? "text-accent-green"
                  : wyckoff?.signal === "sell_signal"
                    ? "text-accent-red"
                    : "text-text-muted"
              }`}
            >
              {SIGNAL_MAP[wyckoff?.signal ?? ""] ?? wyckoff?.signal ?? "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">强度</span>
            <span className="font-mono text-text-primary">
              {STRENGTH_MAP[wyckoff?.signal_strength ?? ""] ?? wyckoff?.signal_strength ?? "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">遗产分数</span>
            <span className="font-mono text-text-primary">
              {wyckoff ? (wyckoff.heritage_score ?? 0).toFixed(2) : "—"}
            </span>
          </div>
        </div>

        {/* Phase progress */}
        <div>
          <div className="text-xs text-text-secondary mb-1.5">
            阶段进度
          </div>
          <div className="flex gap-1">
            {(["A", "B", "C", "D", "E"] as const).map((p) => (
              <div
                key={p}
                className={`flex-1 text-center py-1 rounded text-sm font-bold transition-colors ${
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

        {/* Multi-TF status comparison */}
        <MultiTFStatus />

        {/* Evidence chain */}
        <div>
          <div className="text-xs text-text-secondary mb-1.5">
            证据链
          </div>
          <div className="space-y-1">
            {wyckoff?.evidences && wyckoff.evidences.length > 0 ? (
              wyckoff.evidences.slice(0, 8).map((ev, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-sm"
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
                      {(ev.confidence ?? 0).toFixed(2)}
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-text-muted text-sm italic">
                暂无证据数据
              </div>
            )}
          </div>
        </div>

        {/* Critical levels */}
        {wyckoff?.critical_levels &&
          Object.keys(wyckoff.critical_levels).length > 0 && (
            <div>
              <div className="text-xs text-text-secondary mb-1.5">
                关键价位
              </div>
              <div className="space-y-1">
                {Object.entries(wyckoff.critical_levels).map(([k, v]) => (
                  <div
                    key={k}
                    className="flex justify-between text-sm"
                  >
                    <span className="text-text-secondary">{k}</span>
                    <span className="font-mono text-accent-yellow">
                      {(v ?? 0).toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
        )}
      </div>
    </aside>
  );
}
