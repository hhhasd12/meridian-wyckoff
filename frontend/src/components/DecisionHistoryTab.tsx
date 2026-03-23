/** DecisionHistoryTab — 决策历史 Tab */

import { useEffect, useState } from "react";
import { fetchDecisions } from "../core/api";
import type { DecisionRecord } from "../core/api";

export default function DecisionHistoryTab() {
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchDecisions()
      .then((res) => {
        if (!cancelled) setDecisions(res.decisions ?? []);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="text-text-muted text-sm italic p-2 animate-pulse">
        加载决策历史...
      </div>
    );
  }

  if (decisions.length === 0) {
    return (
      <div className="text-text-muted text-sm italic p-2">
        暂无决策历史 — 系统运行后将自动记录
      </div>
    );
  }

  return (
    <div className="space-y-1 p-1">
      {decisions.slice(0, 20).map((d) => (
        <div
          key={d.id}
          className="flex items-start gap-2 text-sm p-1.5 rounded bg-panel-bg hover:bg-panel-hover/30 transition-colors"
        >
          <span
            className={`badge text-xs shrink-0 ${
              (d.signal ?? "").includes("buy")
                ? "badge-green"
                : (d.signal ?? "").includes("sell")
                  ? "badge-red"
                  : "badge-blue"
            }`}
          >
            {(d.signal ?? "").includes("buy")
              ? "买入"
              : (d.signal ?? "").includes("sell")
                ? "卖出"
                : "观望"}
          </span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-text-primary text-xs">
                置信度 {((d.confidence ?? 0) * 100).toFixed(0)}%
              </span>
              {d.timestamp && (
                <span className="text-text-muted text-xs">
                  {new Date(d.timestamp).toLocaleTimeString()}
                </span>
              )}
            </div>
            {d.reasoning && d.reasoning.length > 0 && (
              <div className="text-text-muted text-xs mt-0.5 truncate">
                {d.reasoning.slice(0, 2).join(" · ")}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
