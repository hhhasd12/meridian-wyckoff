import { useMemo, useState } from "react";
import { useStore } from "../core/store";
import type { EvolutionCycleResult } from "../types/api";
import { startEvolution, stopEvolution } from "../core/api";
import {
  Dna,
  TrendingUp,
  Shield,
  ShieldCheck,
  ShieldX,
  Activity,
  Play,
  Square,
} from "lucide-react";

/* -- 状态栏 ------------------------------------------------ */

export function StatusBar({
  cycles,
  isRunning,
  onToggle,
  toggling,
}: {
  cycles: EvolutionCycleResult[];
  isRunning: boolean;
  onToggle: () => void;
  toggling: boolean;
}) {
  const latest = cycles[cycles.length - 1];
  const items = [
    {
      label: "周期数",
      value: cycles.length.toString(),
      color: "text-accent-cyan",
    },
    {
      label: "最佳适应度",
      value: latest ? (latest.best_fitness ?? 0).toFixed(4) : "—",
      color: "text-accent-green",
    },
    {
      label: "WFA",
      value: latest?.wfa_passed ? "通过" : latest ? "未通过" : "—",
      color: latest?.wfa_passed ? "text-accent-green" : "text-accent-red",
    },
  ];

  return (
    <div className="flex items-center gap-4 px-3 py-1.5 border-b border-panel-border">
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-1.5">
          <span className="text-text-muted text-xs uppercase tracking-wider">
            {it.label}
          </span>
          <span className={`font-mono text-sm font-semibold ${it.color}`}>
            {it.value}
          </span>
        </div>
      ))}
      <div className="ml-auto flex items-center gap-1.5">
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
          onClick={onToggle}
          disabled={toggling}
          className={`ml-2 flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium transition-colors ${
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
  );
}

/* -- SVG 适应度曲线 ---------------------------------------- */

export const CHART_H = 120;
export const CHART_PAD = { top: 12, right: 8, bottom: 20, left: 44 };

export function FitnessChart({ cycles }: { cycles: EvolutionCycleResult[] }) {
  const pathData = useMemo(() => {
    if (cycles.length < 2) return null;
    const xs = cycles.map((_, i) => i);
    const bestVals = cycles.map((c) => c.best_fitness);
    const avgVals = cycles.map((c) => c.avg_fitness);
    const allVals = [...bestVals, ...avgVals];
    const minV = Math.min(...allVals);
    const maxV = Math.max(...allVals);
    const range = maxV - minV || 1;
    const w = 1;
    const plotW = w - CHART_PAD.left - CHART_PAD.right;
    const plotH = CHART_H - CHART_PAD.top - CHART_PAD.bottom;

    const toX = (i: number) =>
      CHART_PAD.left + (i / (xs.length - 1)) * plotW;
    const toY = (v: number) =>
      CHART_PAD.top + (1 - (v - minV) / range) * plotH;

    const makePath = (vals: number[]) =>
      vals.map((v, i) => `${i === 0 ? "M" : "L"}${toX(i)},${toY(v)}`).join("");

    const ticks = Array.from({ length: 5 }, (_, i) => {
      const v = minV + (range * i) / 4;
      return { y: toY(v), label: (v ?? 0).toFixed(3) };
    });

    const xLabels = [
      { x: toX(0), label: cycles[0]?.cycle.toString() ?? "0" },
      {
        x: toX(Math.floor(xs.length / 2)),
        label: cycles[Math.floor(xs.length / 2)]?.cycle.toString() ?? "",
      },
      {
        x: toX(xs.length - 1),
        label: cycles[xs.length - 1]?.cycle.toString() ?? "",
      },
    ];

    return { best: makePath(bestVals), avg: makePath(avgVals), ticks, xLabels, plotW };
  }, [cycles]);

  if (!pathData) {
    return (
      <div
        className="rounded bg-panel-surface border border-panel-border flex items-center justify-center"
        style={{ height: CHART_H }}
      >
        <div className="flex items-center gap-2 text-text-muted text-sm">
          <Activity size={14} className="opacity-50" />
          <span>需要 ≥2 个周期绘制曲线</span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded bg-panel-surface border border-panel-border overflow-hidden">
      <div className="flex items-center gap-3 px-2 py-1 border-b border-panel-border/50">
        <TrendingUp size={12} className="text-accent-cyan" />
        <span className="text-text-secondary text-xs font-medium uppercase tracking-wider">
          适应度曲线
        </span>
        <div className="ml-auto flex items-center gap-3">
          <span className="flex items-center gap-1 text-xs text-accent-green">
            <span className="w-3 h-[2px] bg-accent-green inline-block rounded" />
            最优
          </span>
          <span className="flex items-center gap-1 text-xs text-accent-purple">
            <span className="w-3 h-[2px] bg-accent-purple inline-block rounded opacity-60" />
            均值
          </span>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${CHART_PAD.left + pathData.plotW + CHART_PAD.right} ${CHART_H}`}
        className="w-full"
        style={{ height: CHART_H }}
        preserveAspectRatio="none"
      >
        {pathData.ticks.map((t, i) => (
          <g key={i}>
            <line
              x1={CHART_PAD.left} x2={CHART_PAD.left + pathData.plotW}
              y1={t.y} y2={t.y}
              stroke="#2A2E39" strokeWidth={0.5} strokeDasharray="2,2"
            />
            <text x={CHART_PAD.left - 3} y={t.y + 3}
              fill="#474D57" fontSize={7} textAnchor="end" fontFamily="monospace">
              {t.label}
            </text>
          </g>
        ))}
        {pathData.xLabels.map((xl, i) => (
          <text key={i} x={xl.x} y={CHART_H - 4}
            fill="#474D57" fontSize={7} textAnchor="middle" fontFamily="monospace">
            C{xl.label}
          </text>
        ))}
        <path d={pathData.avg} fill="none"
          stroke="#B98EFF" strokeWidth={1.2} opacity={0.5} />
        <path d={pathData.best} fill="none"
          stroke="#26A69A" strokeWidth={1.5} />
      </svg>
    </div>
  );
}

/* -- 参数面板 ---------------------------------------------- */

export function ParamsPanel({ latest }: { latest: EvolutionCycleResult | null }) {
  if (!latest) {
    return (
      <div className="rounded bg-panel-surface border border-panel-border p-2">
        <span className="text-text-muted text-sm italic">无参数数据</span>
      </div>
    );
  }

  const cfg = latest.config ?? latest.best_config ?? {};
  const weights = (cfg.period_weight_filter as Record<string, unknown>)?.weights as
    | Record<string, number>
    | undefined;
  const thresholds = cfg.threshold_parameters as Record<string, number> | undefined;

  const weightEntries = weights ? Object.entries(weights) : [];
  const maxW = weightEntries.length > 0
    ? Math.max(...weightEntries.map(([, v]) => v))
    : 1;

  return (
    <div className="rounded bg-panel-surface border border-panel-border overflow-hidden">
      <div className="panel-header text-xs">
        <Dna size={12} className="text-accent-purple" />
        <span className="ml-1">最优参数</span>
      </div>
      <div className="p-2 space-y-2 max-h-40 overflow-auto">
        {weightEntries.length > 0 && (
          <div className="space-y-1">
            <div className="text-text-muted text-xs uppercase tracking-wider">
              周期权重
            </div>
            {weightEntries.map(([tf, w]) => (
              <div key={tf} className="flex items-center gap-2">
                <span className="text-text-secondary font-mono text-xs w-8 shrink-0">
                  {tf}
                </span>
                <div className="flex-1 h-2.5 bg-panel-bg rounded overflow-hidden">
                  <div
                    className="h-full rounded bg-accent-purple/70 transition-all"
                    style={{ width: `${(w / maxW) * 100}%` }}
                  />
                </div>
                <span className="text-text-muted font-mono text-xs w-8 text-right">
                  {(w ?? 0).toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        )}
        {thresholds && Object.keys(thresholds).length > 0 && (
          <div className="space-y-0.5">
            <div className="text-text-muted text-xs uppercase tracking-wider">
              阈值参数
            </div>
            {Object.entries(thresholds).map(([k, v]) => (
              <div key={k} className="flex justify-between text-xs">
                <span className="text-text-secondary truncate mr-2">{k}</span>
                <span className="text-accent-cyan font-mono shrink-0">
                  {typeof v === "number" ? (v ?? 0).toFixed(4) : String(v)}
                </span>
              </div>
            ))}
          </div>
        )}
        {weightEntries.length === 0 && !thresholds && (
          <span className="text-text-muted text-xs italic">
            无结构化参数
          </span>
        )}
      </div>
    </div>
  );
}

/* -- 验证面板 ---------------------------------------------- */

export function ValidationPanel({ latest }: { latest: EvolutionCycleResult | null }) {
  if (!latest) {
    return (
      <div className="rounded bg-panel-surface border border-panel-border p-2">
        <span className="text-text-muted text-sm italic">无验证数据</span>
      </div>
    );
  }

  const wfaPassed = latest.wfa_passed;
  const oosDr = latest.oos_dr;
  const antiOverfit = (latest.config ?? latest.best_config)?.anti_overfit as
    | Record<string, unknown>
    | undefined;

  return (
    <div className="rounded bg-panel-surface border border-panel-border overflow-hidden">
      <div className="panel-header text-xs">
        <Shield size={12} className="text-accent-blue" />
        <span className="ml-1">验证状态</span>
      </div>
      <div className="p-2 space-y-2">
        <div className="flex items-center gap-2">
          {wfaPassed ? (
            <ShieldCheck size={16} className="text-accent-green" />
          ) : (
            <ShieldX size={16} className="text-accent-red" />
          )}
          <div>
            <div className={`text-sm font-semibold ${
              wfaPassed ? "text-accent-green" : "text-accent-red"
            }`}>
              WFA {wfaPassed ? "通过" : "未通过"}
            </div>
            <div className="text-text-muted text-xs">
              OOS退化率: {((oosDr ?? 0) * 100).toFixed(1)}%
            </div>
          </div>
        </div>
        <div className="h-1.5 bg-panel-bg rounded overflow-hidden">
          <div
            className={`h-full rounded transition-all ${
              oosDr < 0.3
                ? "bg-accent-green"
                : oosDr < 0.5
                  ? "bg-accent-yellow"
                  : "bg-accent-red"
            }`}
            style={{ width: `${Math.min(oosDr * 100, 100)}%` }}
          />
        </div>
        {antiOverfit && (
          <div className="space-y-0.5 pt-1 border-t border-panel-border/50">
            <div className="text-text-muted text-xs uppercase tracking-wider">
              防过拟合
            </div>
            {Object.entries(antiOverfit).map(([k, v]) => (
              <div key={k} className="flex justify-between text-xs">
                <span className="text-text-secondary truncate mr-2">{k}</span>
                <span className="text-accent-cyan font-mono shrink-0">
                  {typeof v === "number" ? (v ?? 0).toFixed(4) : String(v)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* -- 历史表格 ---------------------------------------------- */

export function HistoryTable({ cycles }: { cycles: EvolutionCycleResult[] }) {
  const recent = cycles.slice(-5).reverse();
  if (recent.length === 0) return null;

  return (
    <div className="rounded bg-panel-surface border border-panel-border overflow-hidden">
      <table className="data-table">
        <thead>
          <tr>
            <th>周期</th>
            <th>适应度</th>
            <th>均值</th>
            <th>WFA</th>
            <th>OOS退化率</th>
          </tr>
        </thead>
        <tbody>
          {recent.map((c) => (
            <tr key={c.cycle}>
              <td className="text-text-primary font-medium">C{c.cycle}</td>
              <td className="text-accent-green">{(c.best_fitness ?? 0).toFixed(4)}</td>
              <td className="text-accent-purple">{(c.avg_fitness ?? 0).toFixed(4)}</td>
              <td>
                <span className={`badge text-xs ${
                  c.wfa_passed ? "badge-green" : "badge-red"
                }`}>
                  {c.wfa_passed ? "通过" : "未通过"}
                </span>
              </td>
              <td className={
                c.oos_dr < 0.3
                  ? "text-accent-green"
                  : c.oos_dr < 0.5
                    ? "text-accent-yellow"
                    : "text-accent-red"
              }>
                {((c.oos_dr ?? 0) * 100).toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* -- 主组件 ------------------------------------------------ */

export default function EvolutionTab() {
  const cycles = useStore((s) => s.evolutionCycles);
  const evo = useStore((s) => s.evolution);
  const isRunning = evo?.is_running ?? false;
  const [toggling, setToggling] = useState(false);

  const handleToggle = async () => {
    setToggling(true);
    try {
      if (isRunning) {
        const result = await stopEvolution();
        console.log("[Evolution] stop result:", result);
        if (result.status === "stopped" || result.status === "already_stopped") {
          useStore.getState().setEvolution({
            ...evo,
            status: "stopped",
            is_running: false,
          });
        }
      } else {
        const result = await startEvolution(10);
        console.log("[Evolution] start result:", result);
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

  if (cycles.length === 0 && !evo) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2">
        <Dna size={28} className="text-text-muted opacity-40" />
        <span className="text-text-muted text-sm italic">
          等待进化结果...
        </span>
      </div>
    );
  }

  // 实时进度显示（进化正在跑但还没出 cycle 结果时）
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

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <StatusBar cycles={cycles} isRunning={isRunning} onToggle={handleToggle} toggling={toggling} />

      {/* 实时评估进度条 */}
      {showProgress && (
        <div className="px-2 py-1.5 border-b border-panel-border bg-panel-surface/50 space-y-1">
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
                <span className="ml-2 text-text-muted">
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

      <div className="flex-1 flex flex-col min-h-0 overflow-auto p-2 gap-2">
        <FitnessChart cycles={cycles} />
        <div className="grid grid-cols-2 gap-2">
          <ParamsPanel latest={cycles[cycles.length - 1] ?? null} />
          <ValidationPanel latest={cycles[cycles.length - 1] ?? null} />
        </div>
        <HistoryTable cycles={cycles} />
      </div>
    </div>
  );
}
