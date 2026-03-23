/** AnalysisPage — State machine visualization with per-bar analysis overlays */

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type Time,
} from "lightweight-charts";
import { Play, Loader2, Activity, BarChart3 } from "lucide-react";
import { useStore } from "../core/store";
import { fetchAnalysis } from "../core/api";
import type {
  AnalyzeBarDetail,
  Candle,
  WyckoffPhase,
} from "../types/api";
import { PhaseBgSegmented, type PhaseSegment } from "../chart-plugins/PhaseBgSegmented";
import {
  WyckoffEventMarkers,
  classifyState,
  type EventMarkerData,
} from "../chart-plugins/WyckoffEventMarkers";
import { TRBoundaryBox, type TRBoundaryData } from "../chart-plugins/TRBoundaryBox";

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function tsToTime(ts: string): Time {
  return (new Date(ts).getTime() / 1000) as unknown as Time;
}

function toChartCandle(c: Candle): CandlestickData<Time> {
  return {
    time: tsToTime(c.timestamp),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  };
}

function toVolumeBar(c: Candle): HistogramData<Time> {
  return {
    time: tsToTime(c.timestamp),
    value: c.volume,
    color: c.close >= c.open ? "rgba(63,185,80,0.4)" : "rgba(248,81,73,0.4)",
  };
}

/** Group consecutive same-phase bars into segments */
function buildPhaseSegments(bars: AnalyzeBarDetail[]): PhaseSegment[] {
  if (bars.length === 0) return [];
  const segs: PhaseSegment[] = [];
  let cur = bars[0]!;
  let start = cur.timestamp;
  for (let i = 1; i < bars.length; i++) {
    const b = bars[i]!;
    if (b.p !== cur.p) {
      segs.push({ startTime: tsToTime(start), endTime: tsToTime(cur.timestamp), phase: cur.p });
      start = b.timestamp;
      cur = b;
    } else {
      cur = b;
    }
  }
  segs.push({ startTime: tsToTime(start), endTime: tsToTime(cur.timestamp), phase: cur.p });
  return segs;
}

/** Filter state-changed bars into event markers */
function buildEventMarkers(
  bars: AnalyzeBarDetail[],
  candleMap: Map<string, Candle>,
): EventMarkerData[] {
  return bars
    .filter((b) => b.sc)
    .map((b) => {
      const candle = candleMap.get(b.timestamp);
      return {
        time: tsToTime(b.timestamp),
        price: candle ? candle.close : 0,
        state: b.s,
        direction: classifyState(b.s),
      };
    })
    .filter((m) => m.price > 0);
}

/** Group consecutive bars with same ts+tr into TR boundary segments */
function buildTRBoundaries(bars: AnalyzeBarDetail[]): TRBoundaryData[] {
  const result: TRBoundaryData[] = [];
  let i = 0;
  while (i < bars.length) {
    const b = bars[i]!;
    if (b.ts !== null && b.tr !== null) {
      const startTs = b.timestamp;
      const support = b.ts;
      const resistance = b.tr;
      const confidence = b.tc ?? 0.5;
      let j = i + 1;
      while (j < bars.length && bars[j]!.ts === support && bars[j]!.tr === resistance) {
        j++;
      }
      result.push({
        startTime: tsToTime(startTs),
        endTime: tsToTime(bars[j - 1]!.timestamp),
        support,
        resistance,
        confidence,
      });
      i = j;
    } else {
      i++;
    }
  }
  return result;
}

function buildConfidenceData(bars: AnalyzeBarDetail[]): LineData<Time>[] {
  return bars.map((b) => ({
    time: tsToTime(b.timestamp),
    value: b.c,
  }));
}

/* ------------------------------------------------------------------ */
/* Phase badge colors                                                  */
/* ------------------------------------------------------------------ */

const PHASE_BADGE: Record<WyckoffPhase, string> = {
  A: "bg-[#8b949e]/15 text-[#8b949e]",
  B: "bg-[#d29922]/15 text-[#d29922]",
  C: "bg-[#3fb950]/15 text-[#3fb950]",
  D: "bg-[#58a6ff]/15 text-[#58a6ff]",
  E: "bg-[#bc8cff]/15 text-[#bc8cff]",
  IDLE: "bg-[#474D57]/15 text-[#474D57]",
};

/* ------------------------------------------------------------------ */
/* Bar Detail Panel                                                    */
/* ------------------------------------------------------------------ */

function BarDetailPanel({ bar }: { bar: AnalyzeBarDetail | null }) {
  if (!bar) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted text-sm">
        移动十字线查看每根K线的分析详情
      </div>
    );
  }

  const rows: [string, React.ReactNode][] = [
    ["状态", <span className="text-accent-purple font-medium">{bar.s}</span>],
    [
      "阶段",
      <span className={`badge text-xs ${PHASE_BADGE[bar.p]}`}>{bar.p}</span>,
    ],
    ["置信度", <span className="font-mono">{(bar.c * 100).toFixed(1)}%</span>],
    ["方向", <span className="text-text-primary">{bar.d}</span>],
    ["市场体制", <span className="text-text-primary">{bar.mr}</span>],
    ["信号强度", <span className="text-text-primary">{bar.ss}</span>],
    ["信号", <span className={bar.sig === "no_signal" ? "text-text-muted" : "text-accent-green"}>{bar.sig}</span>],
    [
      "状态变化",
      bar.sc ? (
        <span className="badge badge-green text-xs">是</span>
      ) : (
        <span className="text-text-muted">否</span>
      ),
    ],
    [
      "支撑",
      bar.ts !== null ? (
        <span className="font-mono text-accent-green">{bar.ts.toFixed(2)}</span>
      ) : (
        <span className="text-text-muted">—</span>
      ),
    ],
    [
      "阻力",
      bar.tr !== null ? (
        <span className="font-mono text-accent-red">{bar.tr.toFixed(2)}</span>
      ) : (
        <span className="text-text-muted">—</span>
      ),
    ],
  ];

  return (
    <div className="flex flex-col h-full overflow-auto">
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-panel-border/50">
        <Activity size={12} className="text-accent-purple" />
        <span className="text-text-secondary text-xs font-medium uppercase tracking-wider">
          Bar #{bar.bar_index}
        </span>
        <span className="text-text-muted text-xs font-mono ml-auto">
          {new Date(bar.timestamp).toLocaleString()}
        </span>
      </div>
      <div className="px-3 py-1.5 space-y-1">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between text-xs">
            <span className="text-text-secondary">{label}</span>
            {value}
          </div>
        ))}
      </div>
      {Object.keys(bar.cl).length > 0 && (
        <div className="px-3 py-1.5 border-t border-panel-border/50">
          <div className="text-xs text-text-secondary mb-1 uppercase tracking-wider">
            关键水平
          </div>
          {Object.entries(bar.cl).map(([k, v]) => (
            <div key={k} className="flex items-center justify-between text-xs">
              <span className="text-accent-blue">{k}</span>
              <span className="font-mono text-text-primary">{v.toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main Component                                                      */
/* ------------------------------------------------------------------ */

export default function AnalysisPage() {
  const analysisData = useStore((s) => s.analysisData);
  const setAnalysisData = useStore((s) => s.setAnalysisData);
  const isAnalyzing = useStore((s) => s.isAnalyzing);
  const setIsAnalyzing = useStore((s) => s.setIsAnalyzing);

  const [candles, setCandles] = useState<Candle[]>([]);
  const [hoveredBar, setHoveredBar] = useState<AnalyzeBarDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Chart refs
  const mainContainerRef = useRef<HTMLDivElement | null>(null);
  const confContainerRef = useRef<HTMLDivElement | null>(null);
  const mainChartRef = useRef<IChartApi | null>(null);
  const confChartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const confSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const disposedRef = useRef(false);

  // Plugin refs
  const phaseBgRef = useRef<PhaseBgSegmented | null>(null);
  const eventMarkersRef = useRef<WyckoffEventMarkers | null>(null);
  const trBoxRef = useRef<TRBoundaryBox | null>(null);

  // Build candle map for quick lookup
  const candleMap = useMemo(() => {
    const m = new Map<string, Candle>();
    for (const c of candles) m.set(c.timestamp, c);
    return m;
  }, [candles]);

  // Build bar detail lookup by unix timestamp
  const barDetailMap = useMemo(() => {
    const m = new Map<number, AnalyzeBarDetail>();
    if (!analysisData) return m;
    for (const b of analysisData.bar_details) {
      m.set(Math.floor(new Date(b.timestamp).getTime() / 1000), b);
    }
    return m;
  }, [analysisData]);

  /* ------------- Run Analysis ------------- */
  const runAnalysis = useCallback(async () => {
    setIsAnalyzing(true);
    setError(null);
    try {
      const analysis = await fetchAnalysis("ETHUSDT", 2000);
      if (analysis.error) {
        setError(analysis.error);
      } else {
        setAnalysisData(analysis);
        // K线数据从 analyze 响应获取（与分析时间完全对齐）
        setCandles(analysis.candles ?? []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "分析请求失败");
    } finally {
      setIsAnalyzing(false);
    }
  }, [setIsAnalyzing, setAnalysisData]);

  /* ------------- Initialize main chart ------------- */
  useEffect(() => {
    const container = mainContainerRef.current;
    if (!container) return;
    disposedRef.current = false;

    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: "#0d1117" }, textColor: "#8b949e", fontSize: 12 },
      grid: { vertLines: { color: "#1c2128" }, horzLines: { color: "#1c2128" } },
      crosshair: {
        vertLine: { color: "#30363d", labelBackgroundColor: "#161b22" },
        horzLine: { color: "#30363d", labelBackgroundColor: "#161b22" },
      },
      rightPriceScale: { borderColor: "#30363d", scaleMargins: { top: 0.1, bottom: 0.25 } },
      timeScale: { borderColor: "#30363d", timeVisible: true, secondsVisible: false },
      handleScroll: { vertTouchDrag: false },
    });

    const cSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#3fb950", downColor: "#f85149",
      borderUpColor: "#3fb950", borderDownColor: "#f85149",
      wickUpColor: "#3fb950", wickDownColor: "#f85149",
    });

    const vSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" }, priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    // Attach plugins
    const phaseBg = new PhaseBgSegmented();
    const eventMarkers = new WyckoffEventMarkers();
    const trBox = new TRBoundaryBox();
    cSeries.attachPrimitive(phaseBg);
    cSeries.attachPrimitive(eventMarkers);
    cSeries.attachPrimitive(trBox);

    mainChartRef.current = chart;
    candleSeriesRef.current = cSeries;
    volumeSeriesRef.current = vSeries;
    phaseBgRef.current = phaseBg;
    eventMarkersRef.current = eventMarkers;
    trBoxRef.current = trBox;

    const ro = new ResizeObserver((entries) => {
      if (disposedRef.current) return;
      for (const entry of entries) {
        try { chart.applyOptions({ width: entry.contentRect.width, height: entry.contentRect.height }); } catch { /* */ }
      }
    });
    ro.observe(container);

    return () => {
      disposedRef.current = true;
      mainChartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      phaseBgRef.current = null;
      eventMarkersRef.current = null;
      trBoxRef.current = null;
      ro.disconnect();
      try { chart.remove(); } catch { /* */ }
    };
  }, []);

  /* ------------- Initialize confidence chart ------------- */
  useEffect(() => {
    const container = confContainerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: "#131722" }, textColor: "#787B86", fontSize: 11 },
      grid: { vertLines: { color: "#1c2128" }, horzLines: { color: "#1c2128" } },
      crosshair: {
        vertLine: { color: "#30363d", labelBackgroundColor: "#161b22" },
        horzLine: { color: "#30363d", labelBackgroundColor: "#161b22" },
      },
      rightPriceScale: { borderColor: "#2A2E39" },
      timeScale: { borderColor: "#2A2E39", visible: true },
      handleScroll: { vertTouchDrag: false },
    });

    const series = chart.addSeries(LineSeries, {
      color: "#B98EFF", lineWidth: 2,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });

    confChartRef.current = chart;
    confSeriesRef.current = series;

    const ro = new ResizeObserver((entries) => {
      if (disposedRef.current) return;
      for (const entry of entries) {
        try { chart.applyOptions({ width: entry.contentRect.width }); } catch { /* */ }
      }
    });
    ro.observe(container);

    return () => {
      confChartRef.current = null;
      confSeriesRef.current = null;
      ro.disconnect();
      try { chart.remove(); } catch { /* */ }
    };
  }, []);

  /* ------------- Set candle + volume data on main chart ------------- */
  useEffect(() => {
    if (disposedRef.current || !candleSeriesRef.current) return;
    if (candles.length === 0) return;
    try {
      candleSeriesRef.current.setData(candles.map(toChartCandle));
      if (volumeSeriesRef.current) {
        volumeSeriesRef.current.setData(candles.map(toVolumeBar));
      }
    } catch { /* disposed */ }
  }, [candles]);

  /* ------------- Update overlays when analysis data changes ------------- */
  useEffect(() => {
    if (!analysisData || disposedRef.current) return;
    const bars = analysisData.bar_details;

    phaseBgRef.current?.setSegments(buildPhaseSegments(bars));
    eventMarkersRef.current?.setMarkers(buildEventMarkers(bars, candleMap));
    trBoxRef.current?.setBoundaries(buildTRBoundaries(bars));

    if (confSeriesRef.current) {
      try {
        confSeriesRef.current.setData(buildConfidenceData(bars));
        confChartRef.current?.timeScale().fitContent();
      } catch { /* disposed */ }
    }

    mainChartRef.current?.timeScale().fitContent();
  }, [analysisData, candleMap]);

  /* ------------- Crosshair sync ------------- */
  useEffect(() => {
    const mainChart = mainChartRef.current;
    const confChart = confChartRef.current;
    if (!mainChart || !confChart) return;

    let syncing = false;

    const onMainCrosshair = (param: { time?: Time }) => {
      if (syncing) return;
      syncing = true;
      if (param.time) {
        confChart.timeScale().scrollToPosition(
          mainChart.timeScale().scrollPosition(), false,
        );
        const ts = param.time as unknown as number;
        setHoveredBar(barDetailMap.get(ts) ?? null);
      }
      syncing = false;
    };

    const onConfCrosshair = (param: { time?: Time }) => {
      if (syncing) return;
      syncing = true;
      if (param.time) {
        mainChart.timeScale().scrollToPosition(
          confChart.timeScale().scrollPosition(), false,
        );
        const ts = param.time as unknown as number;
        setHoveredBar(barDetailMap.get(ts) ?? null);
      }
      syncing = false;
    };

    mainChart.subscribeCrosshairMove(onMainCrosshair);
    confChart.subscribeCrosshairMove(onConfCrosshair);

    return () => {
      try { mainChart.unsubscribeCrosshairMove(onMainCrosshair); } catch { /* */ }
      try { confChart.unsubscribeCrosshairMove(onConfCrosshair); } catch { /* */ }
    };
  }, [barDetailMap]);

  /* ------------- Computed status ------------- */
  const barCount = analysisData?.bar_details.length ?? 0;
  const stateChanges = analysisData?.bar_details.filter((b) => b.sc).length ?? 0;

  /* ------------- JSX ------------- */
  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {/* Control bar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-panel-border bg-panel-surface">
        <button
          onClick={runAnalysis}
          disabled={isAnalyzing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-accent-blue/15 text-accent-blue text-sm font-medium hover:bg-accent-blue/25 disabled:opacity-50 transition-colors"
        >
          {isAnalyzing ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Play size={14} />
          )}
          {isAnalyzing ? "分析中..." : "开始分析"}
        </button>

        <div className="flex items-center gap-1.5 text-xs text-text-secondary">
          <span className="font-mono text-text-primary">ETHUSDT</span>
          <span className="text-text-muted">&middot;</span>
          <span>H4</span>
          <span className="text-text-muted">&middot;</span>
          <span className="font-mono text-text-primary">2000</span>
          <span>根K线</span>
        </div>

        {analysisData && (
          <div className="flex items-center gap-3 ml-auto text-xs">
            <span className="text-text-secondary">
              <span className="font-mono text-text-primary">{barCount}</span> 根K线
            </span>
            <span className="text-text-secondary">
              <span className="font-mono text-accent-purple">{stateChanges}</span> 次状态变化
            </span>
          </div>
        )}

        {error && (
          <span className="text-accent-red text-xs ml-auto">{error}</span>
        )}
      </div>

      {/* Main chart (70%) */}
      <div className="flex-[7] min-h-0">
        <div ref={mainContainerRef} className="w-full h-full" />
      </div>

      {/* Bottom panels (30%) */}
      <div className="flex-[3] min-h-0 flex border-t border-panel-border">
        {/* Confidence chart (left) */}
        <div className="flex-1 flex flex-col border-r border-panel-border">
          <div className="flex items-center gap-2 px-2 py-1 border-b border-panel-border/50 bg-panel-surface">
            <BarChart3 size={12} className="text-accent-purple" />
            <span className="text-text-secondary text-xs font-medium uppercase tracking-wider">
              置信度
            </span>
          </div>
          <div ref={confContainerRef} className="flex-1" />
        </div>

        {/* Bar detail panel (right) */}
        <div className="w-[280px] flex-shrink-0 bg-panel-surface overflow-hidden">
          <BarDetailPanel bar={hoveredBar} />
        </div>
      </div>
    </div>
  );
}
