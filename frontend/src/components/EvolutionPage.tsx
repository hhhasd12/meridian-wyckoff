/** EvolutionPage — Dense, TradingView-quality evolution optimization layout
 *
 * Three-row structure:
 *  1. Top bar (36px): Title + GA config inline + start/stop button
 *  2. Main area (flex-1): Two columns — left (evolution data), right (backtest)
 *  3. Floating AI advisor button (bottom-right) → slide-over panel
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useStore } from "../core/store";
import {
  fetchEvolutionConfig,
  startEvolution,
  stopEvolution,
} from "../core/api";
import {
  Settings,
  Brain,
  Dna,
  Play,
  Square,
  X,
  BarChart3,
} from "lucide-react";
import type { EvolutionCycleResult } from "../types/api";

/* --- Imported sub-components from EvolutionTab --- */
import {
  FitnessChart,
  ParamsPanel,
  ValidationPanel,
  HistoryTable,
} from "./EvolutionTab";

/* --- Imported sub-components from BacktestViewer --- */
import { StatsBar, EquityChart, TradesTable } from "./BacktestViewer";
import { fetchBacktestDetail } from "../core/api";

/* --- Advisor (whole component) --- */
import AdvisorTab from "./AdvisorTab";

/* ================================================================== */
/* GA Config inline display                                            */
/* ================================================================== */

function formatConfigValue(v: unknown): string {
  if (v == null) return "\u2014";
  if (typeof v === "number") return v.toFixed(4);
  if (typeof v === "string" || typeof v === "boolean") return String(v);
  if (typeof v === "object") {
    const flat = Object.entries(v as Record<string, unknown>)
      .map(([k2, v2]) => {
        if (typeof v2 === "number") return `${k2}=${v2.toFixed(2)}`;
        if (typeof v2 === "object" && v2 !== null)
          return formatConfigValue(v2);
        return `${k2}=${String(v2)}`;
      })
      .join(" ");
    return flat || "{}";
  }
  return String(v);
}

function GAConfigInline() {
  const { data } = useQuery({
    queryKey: ["evolution-config"],
    queryFn: fetchEvolutionConfig,
    staleTime: 60_000,
  });

  const config = data?.config ?? {};
  const entries = Object.entries(config);
  if (entries.length === 0) return null;

  return (
    <div className="flex items-center gap-3 overflow-hidden">
      <Settings size={10} className="text-text-muted shrink-0" />
      {entries.slice(0, 6).map(([k, v]) => (
        <div key={k} className="flex items-center gap-1 text-xs shrink-0">
          <span className="text-text-muted">{k}:</span>
          <span className="font-mono text-accent-cyan">
            {formatConfigValue(v)}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ================================================================== */
/* Empty state for left column                                         */
/* ================================================================== */

function EvolutionEmptyState({
  onStart,
  toggling,
}: {
  onStart: () => void;
  toggling: boolean;
}) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3">
      <Dna size={36} className="text-text-muted opacity-30" />
      <span className="text-text-muted text-sm">
        启动进化以查看数据
      </span>
      <button
        onClick={onStart}
        disabled={toggling}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
          bg-accent-green/15 text-accent-green hover:bg-accent-green/25 transition-colors
          ${toggling ? "opacity-50 cursor-not-allowed" : ""}`}
      >
        <Play size={12} />
        启动进化
      </button>
    </div>
  );
}

/* ================================================================== */
/* Backtest empty state for right column                               */
/* ================================================================== */

function BacktestEmptyState() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="flex flex-col items-center gap-2">
        <BarChart3 size={24} className="text-text-muted opacity-30" />
        <span className="text-text-muted text-xs">暂无回测数据</span>
      </div>
    </div>
  );
}

/* ================================================================== */
/* Right column: Backtest panel                                        */
/* ================================================================== */

function BacktestPanel({ cycleIndex }: { cycleIndex: number }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["backtest-detail", cycleIndex],
    queryFn: () => fetchBacktestDetail(cycleIndex),
    staleTime: 30_000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-text-muted text-xs">加载回测数据...</span>
      </div>
    );
  }

  if (error || !data || !data.backtest_detail) {
    return <BacktestEmptyState />;
  }

  const detail = data.backtest_detail;

  return (
    <>
      {/* Cycle meta */}
      <div className="flex items-center gap-2 px-2 py-1 text-xs text-text-secondary shrink-0 border-b border-panel-border/50">
        <span>
          C<span className="font-mono text-text-primary">{data.cycle}</span>
        </span>
        <span>
          G<span className="font-mono text-text-primary">{data.generation}</span>
        </span>
        <span>
          F<span className="font-mono text-accent-green">{data.best_fitness.toFixed(4)}</span>
        </span>
        <span
          className={`badge text-xs ${data.adopted ? "badge-green" : "badge-red"}`}
        >
          {data.adopted ? "已采纳" : "未采纳"}
        </span>
      </div>

      {/* Stats bar - compact single row */}
      <div className="shrink-0">
        <StatsBar detail={detail} />
      </div>

      {/* Equity curve - fills available space */}
      {detail.equity_curve.length > 0 ? (
        <div className="flex-1 min-h-[120px]">
          <EquityChart
            equityCurve={detail.equity_curve}
            chartHeight={280}
            className="h-full"
          />
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-text-muted text-xs">无权益曲线</span>
        </div>
      )}

      {/* Trades table - scrollable, max height */}
      <div className="shrink-0 max-h-[200px] overflow-auto">
        <TradesTable trades={detail.trades} />
      </div>
    </>
  );
}

/* ================================================================== */
/* Main EvolutionPage                                                  */
/* ================================================================== */

export default function EvolutionPage() {
  const cycles = useStore((s) => s.evolutionCycles);
  const evo = useStore((s) => s.evolution);
  const isRunning = evo?.is_running ?? false;
  const [toggling, setToggling] = useState(false);
  const [advisorOpen, setAdvisorOpen] = useState(false);
  const [cycleInput, setCycleInput] = useState("-1");

  const cycleIndex = (() => {
    const n = parseInt(cycleInput, 10);
    return Number.isNaN(n) ? -1 : n;
  })();

  const latest: EvolutionCycleResult | null =
    cycles.length > 0 ? cycles[cycles.length - 1] ?? null : null;
  const hasData = cycles.length > 0 || evo !== null;

  // 实时进度
  const evalCompleted = evo?.eval_completed ?? 0;
  const evalTotal = evo?.eval_total ?? 0;
  const evalGen = evo?.eval_generation ?? evo?.generation ?? 0;
  const evalEta = evo?.eval_eta ?? 0;
  const evalElapsed = evo?.eval_elapsed ?? 0;
  const evalWorkers = evo?.eval_workers ?? 0;
  const bestFitness = evo?.best_fitness ?? 0;
  const avgFitness = evo?.avg_fitness ?? 0;
  const cycleCount = evo?.cycle_count ?? 0;
  const maxCycles = evo?.max_cycles ?? 0;
  const showProgress = isRunning && evalTotal > 0;

  const handleToggle = async () => {
    setToggling(true);
    try {
      if (isRunning) {
        const result = await stopEvolution();
        if (result.status === "stopped" || result.status === "already_stopped") {
          useStore.getState().setEvolution({
            ...evo,
            status: "stopped",
            is_running: false,
          });
        }
      } else {
        const result = await startEvolution(10);
        if (result.status === "started") {
          useStore.getState().setEvolution({
            ...evo,
            status: "running",
            is_running: true,
          });
        }
      }
    } catch (err) {
      console.error("[Evolution] toggle failed:", err);
    } finally {
      setToggling(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-panel-bg">
      {/* ============================================================ */}
      {/* TOP BAR — Title + GA config + start/stop                     */}
      {/* ============================================================ */}
      <div className="flex items-center gap-3 px-3 h-9 shrink-0 border-b border-panel-border bg-panel-surface">
        {/* Title */}
        <div className="flex items-center gap-1.5 shrink-0">
          <Dna size={14} className="text-accent-purple" />
          <span className="text-sm font-medium text-text-primary">
            进化优化
          </span>
        </div>

        {/* Separator */}
        <div className="w-px h-4 bg-panel-border shrink-0" />

        {/* GA config inline (scrolls if overflow) */}
        <div className="flex-1 min-w-0 overflow-hidden">
          <GAConfigInline />
        </div>

        {/* Status indicator + toggle button */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="relative">
            <div
              className={`w-1.5 h-1.5 rounded-full ${
                isRunning ? "bg-accent-green" : "bg-text-muted"
              }`}
            />
            {isRunning && (
              <div className="absolute inset-0 w-1.5 h-1.5 rounded-full bg-accent-green animate-ping opacity-75" />
            )}
          </div>
          <span className="text-text-muted text-xs">
            {isRunning ? "进化中" : "空闲"}
          </span>
          <button
            onClick={handleToggle}
            disabled={toggling}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors ${
              isRunning
                ? "bg-accent-red/15 text-accent-red hover:bg-accent-red/25"
                : "bg-accent-green/15 text-accent-green hover:bg-accent-green/25"
            } ${toggling ? "opacity-50 cursor-not-allowed" : ""}`}
          >
            {isRunning ? (
              <>
                <Square size={10} />
                停止
              </>
            ) : (
              <>
                <Play size={10} />
                启动
              </>
            )}
          </button>
        </div>
      </div>

      {/* ============================================================ */}
      {/* MAIN AREA — Two-column split                                 */}
      {/* ============================================================ */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* -------------------------------------------------------- */}
        {/* LEFT COLUMN (~65%) — Evolution data                       */}
        {/* -------------------------------------------------------- */}
        <div className="flex flex-col min-h-0 overflow-hidden border-r border-panel-border"
          style={{ width: "65%" }}
        >
          {!hasData ? (
            <EvolutionEmptyState onStart={handleToggle} toggling={toggling} />
          ) : (
            <div className="flex-1 flex flex-col min-h-0 overflow-auto p-1.5 gap-1.5">
              {/* 实时评估进度条 */}
              {showProgress && (
                <div className="rounded bg-panel-surface border border-panel-border p-1.5 space-y-1 shrink-0">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary">
                      Gen{evalGen} 评估中
                      <span className="font-mono text-text-primary ml-1">
                        {evalCompleted}/{evalTotal}
                      </span>
                      {evalWorkers > 1 && (
                        <span className="text-text-muted ml-1">[{evalWorkers}P]</span>
                      )}
                    </span>
                    <span className="text-text-muted font-mono">
                      {evalEta > 0 ? `~${Math.ceil(evalEta)}s` : ""}
                      {evalElapsed > 0 && (
                        <span className="ml-2">
                          {Math.floor(evalElapsed / 60)}m{Math.floor(evalElapsed % 60)}s
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="h-1.5 bg-panel-bg rounded overflow-hidden">
                    <div
                      className="h-full rounded bg-accent-blue transition-all duration-500"
                      style={{ width: evalTotal > 0 ? `${(evalCompleted / evalTotal) * 100}%` : "0%" }}
                    />
                  </div>
                  <div className="flex items-center gap-4 text-xs">
                    <span className="text-text-muted">
                      周期 <span className="font-mono text-accent-cyan">{cycleCount}/{maxCycles}</span>
                    </span>
                    {bestFitness > 0 && (
                      <span className="text-text-muted">
                        最佳 <span className="font-mono text-accent-green">{bestFitness.toFixed(4)}</span>
                      </span>
                    )}
                    {avgFitness > 0 && (
                      <span className="text-text-muted">
                        均值 <span className="font-mono text-accent-purple">{avgFitness.toFixed(4)}</span>
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Fitness chart — takes available space, min 120px */}
              <div className="min-h-[120px]">
                <FitnessChart cycles={cycles} />
              </div>

              {/* Params + Validation side by side */}
              <div className="grid grid-cols-2 gap-1.5 shrink-0">
                <ParamsPanel latest={latest} />
                <ValidationPanel latest={latest} />
              </div>

              {/* History table — last 5 cycles */}
              <div className="shrink-0">
                <HistoryTable cycles={cycles} />
              </div>
            </div>
          )}
        </div>

        {/* -------------------------------------------------------- */}
        {/* RIGHT COLUMN (~35%) — Backtest visualization              */}
        {/* -------------------------------------------------------- */}
        <div
          className="flex flex-col min-h-0 overflow-hidden"
          style={{ width: "35%" }}
        >
          {/* Backtest header */}
          <div className="flex items-center gap-2 px-2 py-1 border-b border-panel-border bg-panel-surface shrink-0">
            <BarChart3 size={12} className="text-accent-cyan" />
            <span className="text-xs font-medium text-text-secondary uppercase tracking-wider">
              回测
            </span>
            <div className="ml-auto flex items-center gap-1.5">
              <label className="text-xs text-text-muted">周期:</label>
              <input
                type="number"
                value={cycleInput}
                onChange={(e) => setCycleInput(e.target.value)}
                className="w-14 px-1 py-0.5 rounded bg-panel-bg border border-panel-border
                  text-text-primary font-mono text-xs
                  focus:outline-none focus:border-accent-cyan/50"
                placeholder="-1"
              />
              <span className="text-xs text-text-muted">-1=最新</span>
            </div>
          </div>

          {/* Backtest content */}
          <div className="flex-1 flex flex-col min-h-0 overflow-auto">
            <BacktestPanel cycleIndex={cycleIndex} />
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/* FLOATING AI ADVISOR BUTTON + SLIDE-OVER PANEL                */}
      {/* ============================================================ */}

      {/* Floating trigger button (bottom-right) */}
      {!advisorOpen && (
        <button
          onClick={() => setAdvisorOpen(true)}
          className="fixed bottom-4 right-4 z-50 w-8 h-8 rounded-lg
            bg-accent-purple/20 border border-accent-purple/30
            flex items-center justify-center
            hover:bg-accent-purple/30 transition-colors
            shadow-lg shadow-black/30"
          title="AI 顾问"
        >
          <Brain size={16} className="text-accent-purple" />
        </button>
      )}

      {/* Slide-over backdrop + panel */}
      {advisorOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40 bg-black/40 animate-fade-in"
            onClick={() => setAdvisorOpen(false)}
          />
          {/* Panel */}
          <div className="fixed top-0 right-0 bottom-0 z-50 w-80
            bg-panel-surface border-l border-panel-border
            flex flex-col animate-slide-right shadow-2xl shadow-black/50"
          >
            {/* Panel header */}
            <div className="flex items-center gap-2 px-3 py-2 border-b border-panel-border shrink-0">
              <Brain size={14} className="text-accent-purple" />
              <span className="text-sm font-medium text-text-primary">
                AI 顾问
              </span>
              <button
                onClick={() => setAdvisorOpen(false)}
                className="ml-auto p-1 rounded hover:bg-panel-hover/30 transition-colors"
              >
                <X size={14} className="text-text-muted" />
              </button>
            </div>
            {/* Panel content */}
            <div className="flex-1 min-h-0 overflow-auto">
              <AdvisorTab />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
