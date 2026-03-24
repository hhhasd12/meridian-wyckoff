/** BacktestViewer — Backtest detail visualization for a given evolution cycle */

import { useEffect, useRef, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { init, dispose } from "klinecharts";
import type { Chart, KLineData } from "klinecharts";
import { fetchBacktestDetail } from "../core/api";
import type { BacktestDetail, BacktestTradeRecord } from "../types/api";
import { TrendingUp, BarChart3, Target, ShieldAlert, Percent, Hash } from "lucide-react";

/* ------------------------------------------------------------------ */
/* Stats bar                                                           */
/* ------------------------------------------------------------------ */

export function StatsBar({ detail }: { detail: BacktestDetail }) {
  const items = [
    {
      icon: TrendingUp,
      label: "总收益",
      value: `${(detail.total_return * 100).toFixed(2)}%`,
      color: detail.total_return >= 0 ? "text-accent-green" : "text-accent-red",
    },
    {
      icon: BarChart3,
      label: "Sharpe",
      value: detail.sharpe_ratio.toFixed(2),
      color: detail.sharpe_ratio >= 1 ? "text-accent-green" : detail.sharpe_ratio >= 0.5 ? "text-accent-yellow" : "text-accent-red",
    },
    {
      icon: ShieldAlert,
      label: "最大回撤",
      value: `${(detail.max_drawdown * 100).toFixed(2)}%`,
      color: detail.max_drawdown < 0.1 ? "text-accent-green" : detail.max_drawdown < 0.2 ? "text-accent-yellow" : "text-accent-red",
    },
    {
      icon: Target,
      label: "胜率",
      value: `${(detail.win_rate * 100).toFixed(1)}%`,
      color: detail.win_rate >= 0.5 ? "text-accent-green" : "text-accent-red",
    },
    {
      icon: Percent,
      label: "盈亏比",
      value: detail.profit_factor.toFixed(2),
      color: detail.profit_factor >= 1.5 ? "text-accent-green" : detail.profit_factor >= 1 ? "text-accent-yellow" : "text-accent-red",
    },
    {
      icon: Hash,
      label: "交易数",
      value: detail.total_trades.toString(),
      color: "text-accent-cyan",
    },
  ];

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-3 py-2 border-b border-panel-border bg-panel-surface">
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-1.5">
          <it.icon size={12} className="text-text-muted" />
          <span className="text-text-muted text-xs uppercase tracking-wider">
            {it.label}
          </span>
          <span className={`font-mono text-sm font-semibold ${it.color}`}>
            {it.value}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Equity curve chart (KLineChart v10)                                 */
/* ------------------------------------------------------------------ */

/** Base timestamp for synthetic equity timeline (2024-01-01 00:00 UTC) */
const EQUITY_BASE_TS = 1704067200000;
/** 4-hour bar interval in ms */
const EQUITY_INTERVAL = 4 * 60 * 60 * 1000;

export function EquityChart({
  equityCurve,
  chartHeight,
  className,
}: {
  equityCurve: number[];
  chartHeight?: number;
  className?: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<Chart | null>(null);
  const disposedRef = useRef(false);

  /** Convert equity array → KLineData[] with area-style rendering */
  const klineData: KLineData[] = useMemo(
    () =>
      equityCurve.map((value, i) => ({
        timestamp: EQUITY_BASE_TS + i * EQUITY_INTERVAL,
        open: value,
        high: value,
        low: value,
        close: value,
        volume: 0,
      })),
    [equityCurve],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    disposedRef.current = false;

    const chart = init(container, {
      styles: {
        grid: {
          horizontal: { color: "#1c2128" },
          vertical: { color: "#1c2128" },
        },
        candle: {
          type: "area",
          area: {
            lineSize: 2,
            lineColor: "#26A69A",
            smooth: true,
            value: "close",
            backgroundColor: [
              { offset: 0, color: "rgba(38,166,154,0.25)" },
              { offset: 1, color: "rgba(38,166,154,0.01)" },
            ],
          },
          tooltip: {
            title: { color: "#8b949e" },
            legend: { color: "#8b949e" },
          },
        },
        xAxis: {
          axisLine: { color: "#2A2E39" },
          tickLine: { color: "#2A2E39" },
          tickText: { color: "#787B86" },
        },
        yAxis: {
          axisLine: { color: "#2A2E39" },
          tickLine: { color: "#2A2E39" },
          tickText: { color: "#787B86" },
        },
        crosshair: {
          horizontal: {
            line: { color: "#30363d" },
            text: { backgroundColor: "#161b22", color: "#c9d1d9" },
          },
          vertical: {
            line: { color: "#30363d" },
            text: { backgroundColor: "#161b22", color: "#c9d1d9" },
          },
        },
        separator: { color: "#1c2128" },
      },
    });

    if (!chart) return;

    container.style.backgroundColor = "#131722";
    chartRef.current = chart;

    let rafId = 0;
    const ro = new ResizeObserver(() => {
      if (disposedRef.current) return;
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        if (disposedRef.current) return;
        try {
          chart.resize();
        } catch {
          // chart disposed
        }
      });
    });
    ro.observe(container);

    return () => {
      disposedRef.current = true;
      chartRef.current = null;
      cancelAnimationFrame(rafId);
      ro.disconnect();
      try {
        dispose(container);
      } catch {
        // already disposed
      }
    };
  }, [chartHeight]);

  useEffect(() => {
    if (disposedRef.current) return;
    const chart = chartRef.current;
    if (!chart || klineData.length === 0) return;

    try {
      chart.setDataLoader({
        getBars: (params) => {
          params.callback(klineData, false);
        },
      });
      chart.setSymbol({
        ticker: "EQUITY",
        pricePrecision: 0,
        volumePrecision: 0,
      });
    } catch {
      // chart disposed
    }
  }, [klineData]);

  return (
    <div className={`rounded bg-panel-surface border border-panel-border overflow-hidden ${className ?? ""}`}>
      <div className="flex items-center gap-2 px-2 py-1 border-b border-panel-border/50">
        <TrendingUp size={12} className="text-accent-green" />
        <span className="text-text-secondary text-xs font-medium uppercase tracking-wider">
          权益曲线
        </span>
      </div>
      <div ref={containerRef} style={{ height: chartHeight ?? 200 }} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Trades table                                                        */
/* ------------------------------------------------------------------ */

export function TradesTable({ trades }: { trades: BacktestTradeRecord[] }) {
  if (trades.length === 0) {
    return (
      <div className="text-text-muted text-sm italic p-2">
        暂无交易记录
      </div>
    );
  }

  return (
    <div className="rounded bg-panel-surface border border-panel-border overflow-hidden">
      <div className="overflow-auto" style={{ maxHeight: 200 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>方向</th>
              <th>入场状态</th>
              <th>入场价</th>
              <th>出场价</th>
              <th>盈亏</th>
              <th>盈亏%</th>
              <th>出场原因</th>
              <th>持仓</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i}>
                <td className="text-text-muted">{i + 1}</td>
                <td>
                  <span
                    className={`badge text-xs ${
                      t.side === "LONG" ? "badge-green" : "badge-red"
                    }`}
                  >
                    {t.side === "LONG" ? "LONG" : "SHORT"}
                  </span>
                </td>
                <td className="text-accent-purple">{t.entry_state}</td>
                <td className="font-mono">{t.entry_price.toFixed(2)}</td>
                <td className="font-mono">{t.exit_price.toFixed(2)}</td>
                <td
                  className={`font-mono ${
                    t.pnl >= 0 ? "text-accent-green" : "text-accent-red"
                  }`}
                >
                  {t.pnl >= 0 ? "+" : ""}
                  {t.pnl.toFixed(2)}
                </td>
                <td
                  className={`font-mono ${
                    t.pnl_pct >= 0 ? "text-accent-green" : "text-accent-red"
                  }`}
                >
                  {t.pnl_pct >= 0 ? "+" : ""}
                  {(t.pnl_pct * 100).toFixed(2)}%
                </td>
                <td className="text-text-secondary">{t.exit_reason}</td>
                <td className="font-mono text-text-secondary">
                  {t.hold_bars}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main component                                                      */
/* ------------------------------------------------------------------ */

export default function BacktestViewer({
  cycleIndex,
}: {
  cycleIndex: number;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["backtest-detail", cycleIndex],
    queryFn: () => fetchBacktestDetail(cycleIndex),
    staleTime: 30_000,
    retry: 1,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <span className="text-text-muted text-sm">加载回测数据...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-8">
        <span className="text-accent-red text-sm">
          加载失败: {error instanceof Error ? error.message : "未知错误"}
        </span>
      </div>
    );
  }

  if (!data || !data.backtest_detail) {
    return (
      <div className="flex items-center justify-center py-8">
        <span className="text-text-muted text-sm italic">
          {data?.error ?? "该周期无回测数据"}
        </span>
      </div>
    );
  }

  const detail = data.backtest_detail;

  return (
    <div className="flex flex-col gap-2">
      {/* Cycle meta info */}
      <div className="flex items-center gap-3 px-3 py-1.5 text-xs text-text-secondary">
        <span>
          周期 <span className="font-mono text-text-primary">C{data.cycle}</span>
        </span>
        <span>
          代数 <span className="font-mono text-text-primary">{data.generation}</span>
        </span>
        <span>
          适应度{" "}
          <span className="font-mono text-accent-green">
            {data.best_fitness.toFixed(4)}
          </span>
        </span>
        <span
          className={`badge text-xs ${data.adopted ? "badge-green" : "badge-red"}`}
        >
          {data.adopted ? "已采纳" : "未采纳"}
        </span>
      </div>

      {/* Stats bar */}
      <StatsBar detail={detail} />

      {/* Equity curve */}
      {detail.equity_curve.length > 0 && (
        <EquityChart equityCurve={detail.equity_curve} />
      )}

      {/* Trades table */}
      <TradesTable trades={detail.trades} />
    </div>
  );
}
