/** useChart — KLineChart v10 initialization + real-time candle updates */

import { useEffect, useRef, useCallback } from "react";
import { init, dispose } from "klinecharts";
import type { Chart, KLineData } from "klinecharts";
import { useStore } from "../core/store";
import type { Candle } from "../types/api";

/** Convert our Candle (ISO timestamp string) → KLineChart KLineData (ms) */
function toKLineData(c: Candle): KLineData {
  return {
    timestamp: new Date(c.timestamp).getTime(),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: c.volume,
  };
}

export interface ChartRefs {
  chart: Chart | null;
}

export function useChart(containerRef: React.RefObject<HTMLDivElement | null>) {
  const chartRef = useRef<Chart | null>(null);
  const disposedRef = useRef(false);
  const candles = useStore((s) => s.candles);

  // Initialize chart
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
          bar: {
            upColor: "#3fb950",
            downColor: "#f85149",
            upBorderColor: "#3fb950",
            downBorderColor: "#f85149",
            upWickColor: "#3fb950",
            downWickColor: "#f85149",
          },
          tooltip: {
            title: { color: "#8b949e" },
            legend: { color: "#8b949e" },
          },
        },
        indicator: {
          tooltip: {
            title: { color: "#8b949e" },
            legend: { color: "#8b949e" },
          },
        },
        xAxis: {
          axisLine: { color: "#30363d" },
          tickLine: { color: "#30363d" },
          tickText: { color: "#8b949e" },
        },
        yAxis: {
          axisLine: { color: "#30363d" },
          tickLine: { color: "#30363d" },
          tickText: { color: "#8b949e" },
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

    // Set dark background via container style (KLC uses canvas bg)
    container.style.backgroundColor = "#0d1117";

    // Add built-in VOL indicator in main candle pane's sub-pane
    chart.createIndicator("VOL", false, {
      id: "candle_pane",
    });

    chartRef.current = chart;

    // ResizeObserver → chart.resize()
    const ro = new ResizeObserver(() => {
      if (disposedRef.current) return;
      try {
        chart.resize();
      } catch {
        // chart already disposed
      }
    });
    ro.observe(container);

    return () => {
      disposedRef.current = true;
      chartRef.current = null;
      ro.disconnect();
      try {
        dispose(container);
      } catch {
        // already disposed
      }
    };
  }, [containerRef]);

  // Update data when candles change — use setDataLoader with getBars
  useEffect(() => {
    if (disposedRef.current) return;
    const chart = chartRef.current;
    if (!chart || candles.length === 0) return;

    const klineData = candles.map(toKLineData);

    try {
      // setDataLoader provides data to the chart via callback
      chart.setDataLoader({
        getBars: (params) => {
          // On 'init' or 'forward', provide all our data
          params.callback(klineData, false);
        },
      });

      // Set symbol info to trigger data loading
      chart.setSymbol({
        ticker: "BTC/USDT",
        pricePrecision: 2,
        volumePrecision: 4,
      });
    } catch {
      // chart disposed between check and setDataLoader
    }
  }, [candles]);

  const getRefs = useCallback((): ChartRefs => {
    if (disposedRef.current) {
      return { chart: null };
    }
    return { chart: chartRef.current };
  }, []);

  return { getRefs };
}
