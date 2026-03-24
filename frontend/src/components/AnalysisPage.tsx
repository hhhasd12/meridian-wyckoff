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
import { Play, Loader2, Activity, BarChart3, Trash2 } from "lucide-react";
import { useStore } from "../core/store";
import { fetchAnalysis, fetchAnnotations, createAnnotation, deleteAnnotation } from "../core/api";
import type {
  AnalyzeBarDetail,
  Candle,
  DrawingData,
  WyckoffAnnotation,
  WyckoffPhase,
} from "../types/api";
import DiagnosisChatPanel from "./DiagnosisChatPanel";
import { DrawingTools } from "../chart-plugins/DrawingTools";
import { PhaseBgSegmented, type PhaseSegment } from "../chart-plugins/PhaseBgSegmented";
import {
  WyckoffEventMarkers,
  classifyState,
  type EventMarkerData,
} from "../chart-plugins/WyckoffEventMarkers";
import { TRBoundaryBox, type TRBoundaryData } from "../chart-plugins/TRBoundaryBox";
import { AnnotationLayer, type AnnotationData } from "../chart-plugins/AnnotationLayer";
import AnnotationComparePanel from "./AnnotationComparePanel";

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
          <div key={label} className="flex items-center justify-between text-sm">
            <span className="text-text-secondary text-xs">{label}</span>
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

  // Annotation mode
  const [annotationMode, setAnnotationMode] = useState<"none" | "event" | "level">("none");
  const [selectedEventType, setSelectedEventType] = useState("SC");
  const [annotationListOpen, setAnnotationListOpen] = useState(false);
  const annotations = useStore((s) => s.annotations);
  const setAnnotations = useStore((s) => s.setAnnotations);
  const [deletePopover, setDeletePopover] = useState<{id: string; x: number; y: number; label: string} | null>(null);

  // Drawing tools
  type DrawingMode = "none" | "segment" | "ray" | "channel";
  const [drawingMode, setDrawingMode] = useState<DrawingMode>("none");
  const [drawings, setDrawings] = useState<DrawingData[]>([]);
  const [pendingPoint, setPendingPoint] = useState<{time: number; price: number} | null>(null);
  const drawingIdCounter = useRef(0);

  // Symbol / timeframe / bar count selection
  const [symbol, setSymbol] = useState("ETHUSDT");
  const [timeframe, setTimeframe] = useState("H4");
  const [barCount, setBarCount] = useState(2000);

  // Chat panel
  const [chatVisible, setChatVisible] = useState(false);
  const [selectedBarIndex, setSelectedBarIndex] = useState<number | undefined>();

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
  const annotLayerRef = useRef<AnnotationLayer | null>(null);
  const drawingToolsRef = useRef<DrawingTools | null>(null);

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
      const analysis = await fetchAnalysis(symbol, barCount, timeframe);
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
  }, [symbol, barCount, timeframe, setIsAnalyzing, setAnalysisData]);

  /* ------------- Annotation helpers ------------- */
  const loadAnnotations = useCallback(async () => {
    try {
      const res = await fetchAnnotations(symbol, timeframe);
      setAnnotations(res.annotations);
      // Sync to chart plugin
      const ad: AnnotationData[] = res.annotations.map((a) => ({
        id: a.id, type: a.type,
        event_type: a.event_type, start_time: a.start_time, end_time: a.end_time,
        price: a.price, level_label: a.level_label, structure_type: a.structure_type,
      }));
      annotLayerRef.current?.setAnnotations(ad);
    } catch { /* backend may not be running */ }
  }, [symbol, timeframe, setAnnotations]);

  const handleCreateAnnotation = useCallback(async (partial: Partial<WyckoffAnnotation>) => {
    try {
      await createAnnotation({ ...partial, symbol, timeframe });
      await loadAnnotations();
    } catch { /* ignore */ }
  }, [symbol, timeframe, loadAnnotations]);

  const handleDeleteAnnotation = useCallback(async (id: string) => {
    try {
      await deleteAnnotation(id, symbol, timeframe);
      await loadAnnotations();
    } catch { /* ignore */ }
  }, [symbol, timeframe, loadAnnotations]);

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
    const annotLayer = new AnnotationLayer();
    const drawingTools = new DrawingTools();
    cSeries.attachPrimitive(phaseBg);
    cSeries.attachPrimitive(eventMarkers);
    cSeries.attachPrimitive(trBox);
    cSeries.attachPrimitive(annotLayer);
    cSeries.attachPrimitive(drawingTools);

    mainChartRef.current = chart;
    candleSeriesRef.current = cSeries;
    volumeSeriesRef.current = vSeries;
    phaseBgRef.current = phaseBg;
    eventMarkersRef.current = eventMarkers;
    trBoxRef.current = trBox;
    annotLayerRef.current = annotLayer;
    drawingToolsRef.current = drawingTools;

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
      annotLayerRef.current = null;
      drawingToolsRef.current = null;
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
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: 0, maxValue: 1 },
      }),
    });

    // 0.5 baseline for confidence readability
    series.createPriceLine({
      price: 0.5,
      color: "rgba(255,255,255,0.15)",
      lineWidth: 1,
      lineStyle: 2, // dashed
      axisLabelVisible: false,
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
        const detail = barDetailMap.get(ts) ?? null;
        setHoveredBar(detail);
        if (detail) setSelectedBarIndex(detail.bar_index);
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
        const detail = barDetailMap.get(ts) ?? null;
        setHoveredBar(detail);
        if (detail) setSelectedBarIndex(detail.bar_index);
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

  /* ------------- Annotation drag handler (event mode) ------------- */
  useEffect(() => {
    const chart = mainChartRef.current;
    const series = candleSeriesRef.current;
    const container = mainContainerRef.current;
    if (!chart || !series || !container || annotationMode !== "event") return;

    let isDragging = false;
    let dragStartTime: number | null = null;
    let previewDiv: HTMLDivElement | null = null;

    const getTimeFromX = (clientX: number): number | null => {
      const rect = container.getBoundingClientRect();
      const x = clientX - rect.left;
      const logical = chart.timeScale().coordinateToLogical(x as unknown as import("lightweight-charts").Coordinate);
      if (logical === null || logical < 0) return null;
      // Use candle data to map logical index → time
      const data = series.data();
      if (!data || data.length === 0) return null;
      const idx = Math.round(logical as unknown as number);
      const clamped = Math.max(0, Math.min(idx, data.length - 1));
      return data[clamped]?.time as unknown as number ?? null;
    };

    const onMouseDown = (e: MouseEvent) => {
      const t = getTimeFromX(e.clientX);
      if (t === null) return;
      isDragging = true;
      dragStartTime = t;
      previewDiv = document.createElement("div");
      previewDiv.style.cssText =
        "position:absolute;top:0;bottom:0;background:rgba(59,130,246,0.15);border-left:1px solid rgba(59,130,246,0.5);border-right:1px solid rgba(59,130,246,0.5);pointer-events:none;z-index:10;";
      const rect = container.getBoundingClientRect();
      const startX = e.clientX - rect.left;
      previewDiv.style.left = startX + "px";
      previewDiv.style.width = "2px";
      container.style.position = "relative";
      container.appendChild(previewDiv);
      e.preventDefault();
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging || !previewDiv || dragStartTime === null) return;
      const startCoord = chart.timeScale().timeToCoordinate(dragStartTime as unknown as Time);
      const rect = container.getBoundingClientRect();
      const currentX = e.clientX - rect.left;
      if (startCoord !== null) {
        const left = Math.min(startCoord as number, currentX);
        const width = Math.abs(currentX - (startCoord as number));
        previewDiv.style.left = left + "px";
        previewDiv.style.width = Math.max(width, 2) + "px";
      }
    };

    const onMouseUp = (e: MouseEvent) => {
      if (!isDragging || dragStartTime === null) return;
      isDragging = false;
      if (previewDiv) { previewDiv.remove(); previewDiv = null; }

      const endTime = getTimeFromX(e.clientX);
      if (endTime === null) { dragStartTime = null; return; }

      const start = Math.min(dragStartTime, endTime);
      const end = Math.max(dragStartTime, endTime);
      dragStartTime = null;

      if (end - start < 3600) return; // Too narrow, ignore

      handleCreateAnnotation({
        type: "event",
        event_type: selectedEventType,
        start_time: start,
        end_time: end,
      });
    };

    container.addEventListener("mousedown", onMouseDown);
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);

    return () => {
      container.removeEventListener("mousedown", onMouseDown);
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      if (previewDiv) previewDiv.remove();
    };
  }, [annotationMode, selectedEventType, handleCreateAnnotation]);

  /* ------------- Level click handler (level mode) ------------- */
  useEffect(() => {
    const chart = mainChartRef.current;
    const series = candleSeriesRef.current;
    if (!chart || !series || annotationMode !== "level") return;

    const onClick = (param: { time?: Time; point?: { x: number; y: number } }) => {
      if (!param.point) return;
      const price = series.coordinateToPrice(param.point.y as unknown as import("lightweight-charts").Coordinate);
      if (price !== null) {
        const label = prompt("水平线标签 (如 SC_LOW, AR_HIGH):", "支撑") ?? "Level";
        handleCreateAnnotation({ type: "level", price: price as number, level_label: label });
      }
    };

    chart.subscribeClick(onClick);
    return () => { try { chart.unsubscribeClick(onClick); } catch { /* */ } };
  }, [annotationMode, handleCreateAnnotation]);

  /* ------------- Drawing tools click handler ------------- */
  useEffect(() => {
    const chart = mainChartRef.current;
    const series = candleSeriesRef.current;
    if (!chart || !series || drawingMode === "none") return;

    const onClick = (param: { time?: Time; point?: { x: number; y: number } }) => {
      if (!param.time || !param.point) return;
      const clickTime = param.time as unknown as number;
      const price = series.coordinateToPrice(
        param.point.y as unknown as import("lightweight-charts").Coordinate,
      );
      if (price === null) return;
      const clickPrice = price as number;

      if (!pendingPoint) {
        // First click — set start point
        setPendingPoint({ time: clickTime, price: clickPrice });
      } else {
        // Second click — create drawing
        const id = `draw_${Date.now()}_${drawingIdCounter.current++}`;
        const newDrawing: DrawingData = {
          id,
          tool: drawingMode,
          x1_time: pendingPoint.time,
          y1_price: pendingPoint.price,
          x2_time: clickTime,
          y2_price: clickPrice,
        };

        // Channel: auto-calculate offset (half the price difference)
        if (drawingMode === "channel") {
          const priceDiff = Math.abs(clickPrice - pendingPoint.price);
          newDrawing.channel_offset = -(priceDiff * 0.5);
        }

        const updated = [...drawings, newDrawing];
        setDrawings(updated);
        drawingToolsRef.current?.setDrawings(updated);
        setPendingPoint(null);
      }
    };

    chart.subscribeClick(onClick);
    return () => { try { chart.unsubscribeClick(onClick); } catch { /* */ } };
  }, [drawingMode, pendingPoint, drawings]);

  /* ------------- Click annotation to delete (none mode) ------------- */
  useEffect(() => {
    const chart = mainChartRef.current;
    if (!chart || annotationMode !== "none" || drawingMode !== "none") { setDeletePopover(null); return; }

    const onClick = (param: { time?: Time; point?: { x: number; y: number } }) => {
      if (!param.time || !param.point) return;
      const clickTime = param.time as unknown as number;
      const hit = annotations.find((a) => {
        if (a.type === "event" && a.start_time && a.end_time) {
          return clickTime >= a.start_time && clickTime <= a.end_time;
        }
        return false;
      });
      if (hit) {
        setDeletePopover({
          id: hit.id,
          x: param.point.x,
          y: param.point.y,
          label: hit.event_type ?? hit.level_label ?? "标注",
        });
      } else {
        setDeletePopover(null);
      }
    };

    chart.subscribeClick(onClick);
    return () => { try { chart.unsubscribeClick(onClick); } catch { /* */ } };
  }, [annotationMode, drawingMode, annotations]);

  /* ------------- Load annotations after analysis ------------- */
  useEffect(() => {
    if (analysisData) loadAnnotations();
  }, [analysisData, loadAnnotations]);

  /* ------------- Auto-load on mount and when selection changes ------------- */
  useEffect(() => {
    runAnalysis();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, barCount, timeframe]);

  /* ------------- Highlight bars from AI diagnosis ------------- */
  const handleHighlightBars = useCallback(
    (barIndices: number[]) => {
      if (!analysisData || !annotLayerRef.current) return;
      // Keep non-highlight annotations, replace highlights
      const kept = annotLayerRef.current.annotations.filter(
        (a) => !a.id.startsWith("__highlight_"),
      );
      const highlights: AnnotationData[] = barIndices
        .map((idx) => {
          const bar = analysisData.bar_details.find(
            (b) => b.bar_index === idx,
          );
          if (!bar) return null;
          const ts = Math.floor(new Date(bar.timestamp).getTime() / 1000);
          return {
            id: `__highlight_${idx}`,
            type: "event" as const,
            event_type: `#${idx}`,
            start_time: ts,
            end_time: ts + 14400, // H4 = 4 hours
            color: "rgba(255, 200, 0, 0.35)",
          };
        })
        .filter(Boolean) as AnnotationData[];
      annotLayerRef.current.setAnnotations([...kept, ...highlights]);
    },
    [analysisData],
  );

  /* ------------- Computed status ------------- */
  const analyzedBarCount = analysisData?.bar_details.length ?? 0;
  const stateChanges = analysisData?.bar_details.filter((b) => b.sc).length ?? 0;

  /* ------------- JSX ------------- */
  return (
    <div className="flex-1 flex h-full overflow-hidden relative">
      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
      {/* Control bar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-panel-border bg-panel-surface">
        {/* Symbol selector */}
        <select value={symbol} onChange={e => setSymbol(e.target.value)}
          className="bg-panel-surface text-text-primary text-xs px-2 py-1.5 rounded border border-panel-border">
          <option value="ETHUSDT">ETH/USDT</option>
          <option value="BTCUSDT">BTC/USDT</option>
          <option value="SOLUSDT">SOL/USDT</option>
        </select>

        {/* Timeframe selector */}
        <select value={timeframe} onChange={e => setTimeframe(e.target.value)}
          className="bg-panel-surface text-text-primary text-xs px-2 py-1.5 rounded border border-panel-border">
          <option value="H4">H4</option>
          <option value="H1">H1</option>
          <option value="D1">D1</option>
          <option value="M15">M15</option>
        </select>

        {/* Bar count selector */}
        <select value={barCount} onChange={e => setBarCount(Number(e.target.value))}
          className="bg-panel-surface text-text-primary text-xs px-2 py-1.5 rounded border border-panel-border">
          <option value={500}>500根</option>
          <option value={1000}>1000根</option>
          <option value={2000}>2000根</option>
          <option value={3000}>3000根</option>
        </select>

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
          {isAnalyzing ? "分析中..." : "重新分析"}
        </button>

        {/* Annotation tools */}
        <div className="flex items-center gap-1 border-l border-panel-border/50 pl-3">
          <button
            onClick={() => { setAnnotationMode((m) => m === "event" ? "none" : "event"); setDrawingMode("none"); setPendingPoint(null); }}
            className={`px-2 py-1 text-xs rounded transition-colors ${annotationMode === "event" ? "bg-accent-blue text-white" : "bg-panel-surface text-text-secondary hover:text-text-primary border border-panel-border"}`}
          >
            📌 标注事件
          </button>
          <button
            onClick={() => { setAnnotationMode((m) => m === "level" ? "none" : "level"); setDrawingMode("none"); setPendingPoint(null); }}
            className={`px-2 py-1 text-xs rounded transition-colors ${annotationMode === "level" ? "bg-accent-blue text-white" : "bg-panel-surface text-text-secondary hover:text-text-primary border border-panel-border"}`}
          >
            ─ 水平线
          </button>
          {annotationMode === "event" && (
            <select
              value={selectedEventType}
              onChange={(e) => setSelectedEventType(e.target.value)}
              className="bg-panel-surface text-text-primary text-xs px-1.5 py-1 rounded border border-panel-border"
            >
              <optgroup label="吸筹">
                <option value="PS">PS</option><option value="SC">SC</option>
                <option value="AR">AR</option><option value="ST">ST</option>
                <option value="TEST">TEST</option><option value="SPRING">SPRING</option>
                <option value="LPS">LPS</option><option value="SOS">SOS</option>
                <option value="JOC">JOC</option><option value="BU">BU</option>
              </optgroup>
              <optgroup label="派发">
                <option value="PSY">PSY</option><option value="BC">BC</option>
                <option value="AR_DIST">AR_DIST</option><option value="ST_DIST">ST_DIST</option>
                <option value="UTAD">UTAD</option><option value="LPSY">LPSY</option>
                <option value="SOW">SOW</option>
              </optgroup>
            </select>
          )}
          {annotationMode === "event" && (
            <span className="text-xs text-accent-blue/70">拖拽选择K线范围</span>
          )}

      {/* Annotation compare panel */}
      <AnnotationComparePanel symbol={symbol} timeframe={timeframe} />
    </div>

        {/* Drawing tools */}
        <div className="flex items-center gap-1 border-l border-panel-border/50 pl-2">
          <button
            onClick={() => { setDrawingMode((m) => m === "segment" ? "none" : "segment"); setAnnotationMode("none"); setPendingPoint(null); }}
            className={`px-2 py-1 text-xs rounded transition-colors ${drawingMode === "segment" ? "bg-white/90 text-[#0d1117] font-medium" : "bg-panel-surface text-text-secondary hover:text-text-primary border border-panel-border"}`}
          >
            ╱ 线段
          </button>
          <button
            onClick={() => { setDrawingMode((m) => m === "ray" ? "none" : "ray"); setAnnotationMode("none"); setPendingPoint(null); }}
            className={`px-2 py-1 text-xs rounded transition-colors ${drawingMode === "ray" ? "bg-accent-yellow text-[#0d1117] font-medium" : "bg-panel-surface text-text-secondary hover:text-text-primary border border-panel-border"}`}
          >
            → 射线
          </button>
          <button
            onClick={() => { setDrawingMode((m) => m === "channel" ? "none" : "channel"); setAnnotationMode("none"); setPendingPoint(null); }}
            className={`px-2 py-1 text-xs rounded transition-colors ${drawingMode === "channel" ? "bg-accent-blue text-white font-medium" : "bg-panel-surface text-text-secondary hover:text-text-primary border border-panel-border"}`}
          >
            ⫼ 通道
          </button>
          {drawingMode !== "none" && (
            <span className="text-xs text-accent-yellow/70 ml-1">
              {pendingPoint ? "点击终点完成绘制" : "点击起点开始绘制"}
            </span>
          )}
          {drawings.length > 0 && (
            <button
              onClick={() => { setDrawings([]); drawingToolsRef.current?.setDrawings([]); }}
              className="px-2 py-1 text-xs rounded bg-panel-surface text-accent-red/70 hover:text-accent-red border border-panel-border ml-1 transition-colors"
            >
              清除绘图({drawings.length})
            </button>
          )}
        </div>

        <div className="flex items-center gap-1.5 text-xs text-text-secondary">
          <span className="font-mono text-text-primary">{symbol}</span>
          <span className="text-text-muted">&middot;</span>
          <span>{timeframe}</span>
          <span className="text-text-muted">&middot;</span>
          <span className="font-mono text-text-primary">{barCount}</span>
          <span>根K线</span>
        </div>

        {analysisData && (
          <div className="flex items-center gap-3 ml-auto text-xs">
            <span className="text-text-secondary">
              <span className="font-mono text-text-primary">{analyzedBarCount}</span> 根K线
            </span>
            <span className="text-text-secondary">
              <span className="font-mono text-accent-purple">{stateChanges}</span> 次状态变化
            </span>
            <button
              onClick={() => setAnnotationListOpen((v) => !v)}
              className="px-2 py-0.5 text-xs rounded bg-panel-surface border border-panel-border text-text-secondary hover:text-text-primary"
            >
              标注({annotations.length})
            </button>
          </div>
        )}

        {error && (
          <span className="text-accent-red text-xs ml-auto">{error}</span>
        )}
      </div>

      {/* Main chart (70%) */}
      <div className="flex-[7] min-h-0 relative">
        <div ref={mainContainerRef} className="w-full h-full" />
        {deletePopover && (
          <div className="absolute z-30 bg-panel-surface border border-panel-border rounded-lg shadow-lg p-2"
            style={{ left: deletePopover.x + 10, top: deletePopover.y - 20 }}>
            <p className="text-xs text-text-primary mb-2">
              删除标注 <span className="text-accent-blue font-mono">{deletePopover.label}</span> ?
            </p>
            <div className="flex gap-2">
              <button onClick={() => { handleDeleteAnnotation(deletePopover.id); setDeletePopover(null); }}
                className="px-2 py-1 text-xs bg-accent-red/15 text-accent-red rounded hover:bg-accent-red/25">
                删除
              </button>
              <button onClick={() => setDeletePopover(null)}
                className="px-2 py-1 text-xs bg-panel-surface text-text-secondary rounded border border-panel-border hover:text-text-primary">
                取消
              </button>
            </div>
          </div>
        )}
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

      {/* Annotation list panel (collapsible) */}
      {annotationListOpen && annotations.length > 0 && (
        <div className="max-h-[160px] overflow-auto border-t border-panel-border bg-panel-surface">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-text-secondary border-b border-panel-border/50">
                <th className="text-left px-3 py-1.5 font-medium">类型</th>
                <th className="text-left px-3 py-1.5 font-medium">事件/标签</th>
                <th className="text-left px-3 py-1.5 font-medium">时间/价格</th>
                <th className="text-left px-3 py-1.5 font-medium">创建时间</th>
                <th className="px-3 py-1.5 w-8"></th>
              </tr>
            </thead>
            <tbody>
              {annotations.map((a) => (
                <tr key={a.id} className="border-b border-panel-border/30 hover:bg-panel-surface/80">
                  <td className="px-3 py-1">{a.type}</td>
                  <td className="px-3 py-1 text-text-primary font-medium">
                    {a.event_type ?? a.level_label ?? a.structure_type ?? "—"}
                  </td>
                  <td className="px-3 py-1 font-mono text-text-muted">
                    {a.price != null ? a.price.toFixed(2) : a.start_time ? new Date(a.start_time * 1000).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-3 py-1 text-text-muted">
                    {new Date(a.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-1">
                    <button
                      onClick={() => handleDeleteAnnotation(a.id)}
                      className="text-text-muted hover:text-accent-red transition-colors"
                    >
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      </div>

      {/* AI Diagnosis Chat Panel */}
      <DiagnosisChatPanel
        visible={chatVisible}
        onToggle={() => setChatVisible((v) => !v)}
        selectedBar={selectedBarIndex}
        analysisData={analysisData}
        onHighlightBars={handleHighlightBars}
      />
    </div>
  );
}
