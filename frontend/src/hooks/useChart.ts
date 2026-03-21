/** useChart — LWC initialization + real-time candle updates */

import { useEffect, useRef, useCallback } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type Time,
  ColorType,
} from "lightweight-charts";
import { useStore } from "../core/store";
import type { Candle } from "../types/api";

function toChartCandle(c: Candle): CandlestickData<Time> {
  return {
    time: (new Date(c.timestamp).getTime() / 1000) as unknown as Time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  };
}

function toVolumeBar(c: Candle): HistogramData<Time> {
  return {
    time: (new Date(c.timestamp).getTime() / 1000) as unknown as Time,
    value: c.volume,
    color: c.close >= c.open ? "rgba(63,185,80,0.4)" : "rgba(248,81,73,0.4)",
  };
}

export interface ChartRefs {
  chart: IChartApi | null;
  candleSeries: ISeriesApi<"Candlestick"> | null;
  volumeSeries: ISeriesApi<"Histogram"> | null;
}

export function useChart(containerRef: React.RefObject<HTMLDivElement | null>) {
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const candles = useStore((s) => s.candles);

  // Initialize chart
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: "#0d1117" },
        textColor: "#8b949e",
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "#1c2128" },
        horzLines: { color: "#1c2128" },
      },
      crosshair: {
        vertLine: { color: "#30363d", labelBackgroundColor: "#161b22" },
        horzLine: { color: "#30363d", labelBackgroundColor: "#161b22" },
      },
      rightPriceScale: {
        borderColor: "#30363d",
        scaleMargins: { top: 0.1, bottom: 0.25 },
      },
      timeScale: {
        borderColor: "#30363d",
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: { vertTouchDrag: false },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#3fb950",
      downColor: "#f85149",
      borderUpColor: "#3fb950",
      borderDownColor: "#f85149",
      wickUpColor: "#3fb950",
      wickDownColor: "#f85149",
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    // Auto-resize
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        chart.applyOptions({ width, height });
      }
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [containerRef]);

  // Update data when candles change
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current) return;
    if (candles.length === 0) return;

    const chartData = candles.map(toChartCandle);
    const volumeData = candles.map(toVolumeBar);

    candleSeriesRef.current.setData(chartData);
    volumeSeriesRef.current.setData(volumeData);
  }, [candles]);

  const getRefs = useCallback((): ChartRefs => {
    return {
      chart: chartRef.current,
      candleSeries: candleSeriesRef.current,
      volumeSeries: volumeSeriesRef.current,
    };
  }, []);

  return { getRefs };
}
