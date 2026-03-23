/** PrinciplesPanel -- V4 State Machine visualization: principle scores, hypothesis, boundaries, bar features */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";
import { fetchV4State } from "../core/api";
import { useStore } from "../core/store";
import type { V4StateMachineEntry } from "../types/api";

// Primary timeframe to display
const PRIMARY_TF = "H4";

// Status badge color mapping
const STATUS_STYLE: Record<string, string> = {
  hypothetical: "bg-accent-yellow/15 text-accent-yellow",
  testing: "bg-accent-blue/15 text-accent-blue",
  rejected: "bg-accent-red/15 text-accent-red",
  exhausted: "bg-text-muted/15 text-text-muted",
};

const STATUS_LABEL: Record<string, string> = {
  hypothetical: "HYPOTHETICAL",
  testing: "TESTING",
  rejected: "REJECTED",
  exhausted: "EXHAUSTED",
};

/** Bipolar bar: renders a horizontal bar for -1..+1 range with center line */
function BipolarBar({
  label,
  value,
  leftColor,
  rightColor,
}: {
  label: string;
  value: number;
  leftColor: string;
  rightColor: string;
}) {
  // Clamp to -1..+1
  const clamped = Math.max(-1, Math.min(1, value));
  // Convert to 0..100 percentage from center
  const pct = Math.abs(clamped) * 50;
  const isPositive = clamped >= 0;

  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between">
        <span className="text-text-secondary text-xs">{label}</span>
        <span className="font-mono text-text-primary text-xs">
          {clamped >= 0 ? "+" : ""}
          {clamped.toFixed(2)}
        </span>
      </div>
      <div className="relative w-full h-2 bg-panel-bg rounded-full overflow-hidden">
        {/* Center line */}
        <div className="absolute left-1/2 top-0 w-px h-full bg-text-muted/50 z-10" />
        {/* Fill bar */}
        {isPositive ? (
          <div
            className="absolute top-0 h-full rounded-r-full transition-all duration-300"
            style={{
              left: "50%",
              width: `${pct}%`,
              backgroundColor: rightColor,
            }}
          />
        ) : (
          <div
            className="absolute top-0 h-full rounded-l-full transition-all duration-300"
            style={{
              right: "50%",
              width: `${pct}%`,
              backgroundColor: leftColor,
            }}
          />
        )}
      </div>
    </div>
  );
}

/** Unipolar bar: renders a horizontal bar for 0..1 range */
function UnipolarBar({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  const clamped = Math.max(0, Math.min(1, value));

  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between">
        <span className="text-text-secondary text-xs">{label}</span>
        <span className="font-mono text-text-primary text-xs">
          {clamped.toFixed(2)}
        </span>
      </div>
      <div className="relative w-full h-2 bg-panel-bg rounded-full overflow-hidden">
        <div
          className="absolute top-0 left-0 h-full rounded-full transition-all duration-300"
          style={{
            width: `${clamped * 100}%`,
            backgroundColor: color,
          }}
        />
      </div>
    </div>
  );
}

/** Hypothesis section */
function HypothesisSection({ entry }: { entry: V4StateMachineEntry }) {
  const hyp = entry.hypothesis;

  if (!hyp) {
    return (
      <div className="text-text-muted text-sm italic">
        无活跃假设
      </div>
    );
  }

  const statusClass = STATUS_STYLE[hyp.status ?? ""] ?? "bg-text-muted/15 text-text-muted";
  const statusLabel = STATUS_LABEL[hyp.status ?? ""] ?? (hyp.status ?? "--");

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-text-primary font-bold text-sm">
          {hyp.event_name}
        </span>
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${statusClass}`}>
          {statusLabel}
        </span>
      </div>
      <div className="space-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-text-secondary">持续K线</span>
          <span className="font-mono text-text-primary">{hyp.bars_held}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-secondary">置信度</span>
          <span className="font-mono text-text-primary">
            {(hyp.confidence * 100).toFixed(0)}%
          </span>
        </div>
        {/* Confirmation quality bar */}
        <div className="space-y-0.5">
          <div className="flex items-center justify-between">
            <span className="text-text-secondary text-xs">确认质量</span>
            <span className="font-mono text-text-primary text-xs">
              {hyp.confirmation_quality.toFixed(2)}
            </span>
          </div>
          <div className="w-full h-1.5 bg-panel-bg rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${Math.min(1, hyp.confirmation_quality) * 100}%`,
                backgroundColor: "#36D9C4",
              }}
            />
          </div>
        </div>
        {hyp.rejection_reason && (
          <div className="p-1.5 rounded bg-accent-red/10 border border-accent-red/20">
            <div className="text-xs text-accent-red truncate">
              {hyp.rejection_reason}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function PrinciplesPanel() {
  const setV4State = useStore((s) => s.setV4State);
  const [collapsed, setCollapsed] = useState(false);

  // Poll V4 state every 5 seconds
  const { data: v4State } = useQuery({
    queryKey: ["v4-state"],
    queryFn: fetchV4State,
    refetchInterval: 5_000,
    select: (data) => {
      setV4State(data);
      return data;
    },
  });

  // Extract primary TF entry
  const entry: V4StateMachineEntry | null =
    v4State?.state_machines?.[PRIMARY_TF] ?? null;

  return (
    <div className="flex flex-col bg-panel-surface border-t border-panel-border overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="panel-header cursor-pointer hover:bg-panel-hover/20 transition-colors"
      >
        <span>V4 原则分析</span>
        {collapsed ? (
          <ChevronDown size={14} />
        ) : (
          <ChevronUp size={14} />
        )}
      </button>

      {collapsed ? null : (
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {!entry ? (
            /* Loading skeleton */
            <div className="space-y-3 animate-pulse">
              <div className="space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i}>
                    <div className="flex justify-between mb-1">
                      <div className="h-3 bg-panel-border/30 rounded w-10" />
                      <div className="h-3 bg-panel-border/30 rounded w-8" />
                    </div>
                    <div className="h-2 bg-panel-border/20 rounded-full" />
                  </div>
                ))}
              </div>
              <div className="h-8 bg-panel-border/20 rounded" />
              <div className="h-4 bg-panel-border/20 rounded w-24" />
            </div>
          ) : (
            <>
              {/* (a) Principle Score Bars */}
              <div>
                <div className="text-xs text-text-secondary mb-1.5 font-medium uppercase tracking-widest">
                  三大原则
                </div>
                <div className="space-y-2">
                  {entry.principles ? (
                    <>
                      <BipolarBar
                        label="供需"
                        value={entry.principles.supply_demand}
                        leftColor="#EF5350"
                        rightColor="#26A69A"
                      />
                      <UnipolarBar
                        label="因果"
                        value={entry.principles.cause_effect}
                        color="#36D9C4"
                      />
                      <BipolarBar
                        label="努力结果"
                        value={entry.principles.effort_result}
                        leftColor="#5B9CF6"
                        rightColor="#FCD535"
                      />
                    </>
                  ) : (
                    <div className="text-text-muted text-sm italic">
                      暂无原则数据
                    </div>
                  )}
                </div>
              </div>

              {/* (b) Hypothesis Status */}
              <div>
                <div className="text-xs text-text-secondary mb-1.5 font-medium uppercase tracking-widest">
                  当前假设
                </div>
                <HypothesisSection entry={entry} />
              </div>

              {/* (c) Last Confirmed Event */}
              <div>
                <div className="text-xs text-text-secondary mb-1.5 font-medium uppercase tracking-widest">
                  最近确认事件
                </div>
                <div className="font-mono text-accent-cyan text-sm">
                  {entry.last_confirmed_event || "--"}
                </div>
              </div>

              {/* (d) Key Boundaries */}
              {entry.boundaries &&
                Object.keys(entry.boundaries).length > 0 && (
                  <div>
                    <div className="text-xs text-text-secondary mb-1.5 font-medium uppercase tracking-widest">
                      关键边界
                    </div>
                    <div className="space-y-1">
                      {Object.entries(entry.boundaries).map(([k, v]) => (
                        <div
                          key={k}
                          className="flex justify-between text-sm"
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

              {/* (e) Bar Features Quick Stats */}
              {entry.bar_features && (
                <div>
                  <div className="text-xs text-text-secondary mb-1.5 font-medium uppercase tracking-widest">
                    K线特征
                  </div>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-text-secondary">量比</span>
                      <span
                        className={`font-mono ${
                          entry.bar_features.volume_ratio > 1.5
                            ? "text-accent-yellow"
                            : "text-text-primary"
                        }`}
                      >
                        {entry.bar_features.volume_ratio.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-secondary">实体比</span>
                      <span className="font-mono text-text-primary">
                        {entry.bar_features.body_ratio.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-text-secondary">停止行为</span>
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            entry.bar_features.is_stopping_action
                              ? "bg-accent-green"
                              : "bg-text-muted"
                          }`}
                        />
                        <span className="font-mono text-text-primary text-xs">
                          {entry.bar_features.is_stopping_action
                            ? "YES"
                            : "NO"}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Recent evidence (compact) */}
              {entry.recent_evidence && entry.recent_evidence.length > 0 && (
                <div>
                  <div className="text-xs text-text-secondary mb-1.5 font-medium uppercase tracking-widest">
                    近期证据
                  </div>
                  <div className="space-y-1">
                    {entry.recent_evidence.slice(0, 5).map((ev, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between text-sm"
                      >
                        <span className="text-text-secondary truncate mr-2">
                          {ev.type}
                        </span>
                        <div className="flex items-center gap-1.5">
                          <div className="w-10 h-1.5 bg-panel-bg rounded-full overflow-hidden">
                            <div
                              className="h-full bg-accent-cyan rounded-full"
                              style={{
                                width: `${ev.confidence * 100}%`,
                              }}
                            />
                          </div>
                          <span className="font-mono text-text-primary w-8 text-right text-xs">
                            {ev.confidence.toFixed(2)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
