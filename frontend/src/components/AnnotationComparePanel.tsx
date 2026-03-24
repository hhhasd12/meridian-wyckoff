/** AnnotationComparePanel — 标注对比结果面板，可折叠，颜色编码差异 */

import { useState } from "react";
import { GitCompareArrows, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import type { MatchReport, MatchResult } from "../types/api";
import { fetchAnnotationCompare } from "../core/api";

/* ------------------------------------------------------------------ */
/* Color + Label mapping                                               */
/* ------------------------------------------------------------------ */

const TYPE_STYLE: Record<MatchResult["type"], { bg: string; text: string; label: string }> = {
  matched:        { bg: "bg-accent-green/10", text: "text-accent-green",  label: "✅ 匹配" },
  missed:         { bg: "bg-accent-red/10",   text: "text-accent-red",    label: "❌ 遗漏" },
  false_positive: { bg: "bg-accent-yellow/10",text: "text-accent-yellow", label: "⚠️ 误判" },
  type_mismatch:  { bg: "bg-orange-500/10",   text: "text-orange-400",    label: "🔄 类型错误" },
};

/* ------------------------------------------------------------------ */
/* Props                                                               */
/* ------------------------------------------------------------------ */

interface Props {
  symbol: string;
  timeframe: string;
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export default function AnnotationComparePanel({ symbol, timeframe }: Props) {
  const [report, setReport] = useState<MatchReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runCompare = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetchAnnotationCompare(symbol, timeframe);
      setReport(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "对比请求失败");
    } finally {
      setLoading(false);
    }
  };

  const scorePct = report ? (report.match_score * 100).toFixed(0) : null;

  /* ---------- Collapsed ---------- */
  if (!expanded) {
    return (
      <div className="flex items-center gap-3 px-4 py-1.5 border-t border-panel-border bg-panel-surface">
        <button
          onClick={() => setExpanded(true)}
          className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary transition-colors"
        >
          <ChevronRight size={12} />
          <GitCompareArrows size={12} className="text-accent-blue" />
          <span>标注对比</span>
        </button>
        {report && (
          <span className="text-xs font-mono text-text-muted">
            匹配度: <span className="text-text-primary">{scorePct}%</span>
          </span>
        )}
      </div>
    );
  }

  /* ---------- Expanded ---------- */
  return (
    <div className="border-t border-panel-border bg-panel-surface animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-1.5 border-b border-panel-border/50">
        <button
          onClick={() => setExpanded(false)}
          className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary transition-colors"
        >
          <ChevronDown size={12} />
          <GitCompareArrows size={12} className="text-accent-blue" />
          <span className="uppercase tracking-wider font-medium">标注对比</span>
        </button>
        <button
          onClick={runCompare}
          disabled={loading}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded bg-accent-blue/15 text-accent-blue hover:bg-accent-blue/25 disabled:opacity-50 transition-colors"
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <GitCompareArrows size={12} />}
          {loading ? "对比中..." : "运行对比"}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="px-4 py-2 text-xs text-accent-red">{error}</div>
      )}

      {/* Report body */}
      {report && (
        <div className="px-4 py-2 max-h-52 overflow-auto space-y-2">
          {/* Stats row */}
          <div className="flex items-center gap-4 text-xs">
            <span className="text-accent-green">
              匹配 <span className="font-mono font-bold">{report.matched}</span>
            </span>
            <span className="text-accent-red">
              遗漏 <span className="font-mono font-bold">{report.missed}</span>
            </span>
            <span className="text-accent-yellow">
              误判 <span className="font-mono font-bold">{report.false_positives}</span>
            </span>
            <span className="text-orange-400">
              类型错 <span className="font-mono font-bold">{report.type_mismatches}</span>
            </span>
            <span className="ml-auto text-text-primary font-mono font-bold">
              {scorePct}%
            </span>
          </div>

          {/* Score bar */}
          <div className="h-1.5 bg-panel-border rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{
                width: `${report.match_score * 100}%`,
                background: report.match_score >= 0.7
                  ? "#26A69A"
                  : report.match_score >= 0.4
                    ? "#FCD535"
                    : "#EF5350",
              }}
            />
          </div>

          {/* Totals */}
          <div className="flex gap-4 text-xs text-text-muted">
            <span>标注 {report.total_annotations}</span>
            <span>检测 {report.total_detections}</span>
          </div>

          {/* Results list */}
          {report.results.length > 0 && (
            <div className="space-y-1 pt-1">
              {report.results.map((r, i) => {
                const style = TYPE_STYLE[r.type];
                return (
                  <div
                    key={i}
                    className={`flex items-start gap-2 px-2 py-1 rounded text-xs ${style.bg}`}
                  >
                    <span className={`font-mono whitespace-nowrap ${style.text}`}>
                      {style.label}
                    </span>
                    <span className="text-text-secondary">{r.details}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!report && !error && !loading && (
        <div className="px-4 py-3 text-xs text-text-muted text-center">
          点击"运行对比"将人工标注与系统检测结果进行匹配对比
        </div>
      )}
    </div>
  );
}
