/** AnalysisPage — State machine visualization with per-bar analysis overlays (KLineChart v10) */

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { init, dispose } from "klinecharts";
import type { Chart, KLineData, Crosshair } from "klinecharts";
import { Play, Loader2, Activity } from "lucide-react";
import { useStore } from "../core/store";
import { fetchAnalysis, fetchAnnotations, createAnnotation, deleteAnnotation } from "../core/api";
import type { AnalyzeBarDetail, Candle, WyckoffAnnotation, WyckoffPhase } from "../types/api";
import DiagnosisChatPanel from "./DiagnosisChatPanel";
import AnnotationComparePanel from "./AnnotationComparePanel";
import {
  registerAnalysisOverlays,
  classifyState,
  type PhaseSegment,
  type EventMarkerData,
  type TRBoundaryData,
  type AnnotationData,
} from "../chart-plugins/klc-overlays";

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function toKLineData(c: Candle): KLineData {
  return {
    timestamp: new Date(c.timestamp).getTime(),
    open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume,
  };
}

function tsMs(iso: string): number {
  return new Date(iso).getTime();
}

/** Map our timeframe string to KLineChart Period */
function tfToPeriod(tf: string): { type: "hour" | "minute" | "day"; span: number } {
  switch (tf) {
    case "M5":  return { type: "minute", span: 5 };
    case "M15": return { type: "minute", span: 15 };
    case "H1":  return { type: "hour", span: 1 };
    case "H4":  return { type: "hour", span: 4 };
    case "D1":  return { type: "day", span: 1 };
    default:    return { type: "hour", span: 4 };
  }
}

function buildPhaseSegments(bars: AnalyzeBarDetail[]): PhaseSegment[] {
  if (bars.length === 0) return [];
  const segs: PhaseSegment[] = [];
  let cur = bars[0]!;
  let start = cur.timestamp;
  for (let i = 1; i < bars.length; i++) {
    const b = bars[i]!;
    if (b.p !== cur.p) {
      segs.push({ startTs: tsMs(start), endTs: tsMs(cur.timestamp), phase: cur.p });
      start = b.timestamp; cur = b;
    } else { cur = b; }
  }
  segs.push({ startTs: tsMs(start), endTs: tsMs(cur.timestamp), phase: cur.p });
  return segs;
}

function buildEventMarkers(bars: AnalyzeBarDetail[], candleMap: Map<string, Candle>): EventMarkerData[] {
  return bars.filter((b) => b.sc).map((b) => {
    const candle = candleMap.get(b.timestamp);
    return { timestamp: tsMs(b.timestamp), price: candle ? candle.close : 0, state: b.s, direction: classifyState(b.s) };
  }).filter((m) => m.price > 0);
}

function buildTRBoundaries(bars: AnalyzeBarDetail[]): TRBoundaryData[] {
  const result: TRBoundaryData[] = [];
  let i = 0;
  while (i < bars.length) {
    const b = bars[i]!;
    if (b.ts !== null && b.tr !== null) {
      const support = b.ts, resistance = b.tr, confidence = b.tc ?? 0.5;
      let j = i + 1;
      while (j < bars.length && bars[j]!.ts === support && bars[j]!.tr === resistance) j++;
      result.push({ startTs: tsMs(b.timestamp), endTs: tsMs(bars[j - 1]!.timestamp), support, resistance, confidence });
      i = j;
    } else { i++; }
  }
  return result;
}

/* ------------------------------------------------------------------ */
/* KLC dark theme styles (shared with useChart.ts)                     */
/* ------------------------------------------------------------------ */

const KLC_DARK_STYLES = {
  grid: { horizontal: { color: "#1c2128" }, vertical: { color: "#1c2128" } },
  candle: {
    bar: {
      upColor: "#3fb950", downColor: "#f85149",
      upBorderColor: "#3fb950", downBorderColor: "#f85149",
      upWickColor: "#3fb950", downWickColor: "#f85149",
    },
    tooltip: { title: { color: "#8b949e" }, legend: { color: "#8b949e" } },
  },
  indicator: { tooltip: { title: { color: "#8b949e" }, legend: { color: "#8b949e" } } },
  xAxis: { axisLine: { color: "#30363d" }, tickLine: { color: "#30363d" }, tickText: { color: "#8b949e" } },
  yAxis: { axisLine: { color: "#30363d" }, tickLine: { color: "#30363d" }, tickText: { color: "#8b949e" } },
  crosshair: {
    horizontal: { line: { color: "#30363d" }, text: { backgroundColor: "#161b22", color: "#c9d1d9" } },
    vertical: { line: { color: "#30363d" }, text: { backgroundColor: "#161b22", color: "#c9d1d9" } },
  },
  separator: { color: "#1c2128" },
};

/* ------------------------------------------------------------------ */
/* Phase badge colors                                                  */
/* ------------------------------------------------------------------ */

const PHASE_BADGE: Record<WyckoffPhase, string> = {
  A: "bg-[#8b949e]/15 text-[#8b949e]", B: "bg-[#d29922]/15 text-[#d29922]",
  C: "bg-[#3fb950]/15 text-[#3fb950]", D: "bg-[#58a6ff]/15 text-[#58a6ff]",
  E: "bg-[#bc8cff]/15 text-[#bc8cff]", IDLE: "bg-[#474D57]/15 text-[#474D57]",
};

/* ------------------------------------------------------------------ */
/* Bar Detail Panel (sub-component)                                    */
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
    ["阶段", <span className={`badge text-xs ${PHASE_BADGE[bar.p]}`}>{bar.p}</span>],
    ["置信度", <span className="font-mono">{(bar.c * 100).toFixed(1)}%</span>],
    ["方向", <span className="text-text-primary">{bar.d}</span>],
    ["市场体制", <span className="text-text-primary">{bar.mr}</span>],
    ["信号强度", <span className="text-text-primary">{bar.ss}</span>],
    ["信号", <span className={bar.sig === "no_signal" ? "text-text-muted" : "text-accent-green"}>{bar.sig}</span>],
    ["状态变化", bar.sc
      ? <span className="badge badge-green text-xs">是</span>
      : <span className="text-text-muted">否</span>],
    ["支撑", bar.ts !== null
      ? <span className="font-mono text-accent-green">{bar.ts.toFixed(2)}</span>
      : <span className="text-text-muted">—</span>],
    ["阻力", bar.tr !== null
      ? <span className="font-mono text-accent-red">{bar.tr.toFixed(2)}</span>
      : <span className="text-text-muted">—</span>],
  ];
  return (
    <div className="flex flex-col h-full overflow-auto">
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-panel-border/50">
        <Activity size={12} className="text-accent-purple" />
        <span className="text-text-secondary text-xs font-medium uppercase tracking-wider">Bar #{bar.bar_index}</span>
        <span className="text-text-muted text-xs font-mono ml-auto">{new Date(bar.timestamp).toLocaleString()}</span>
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
          <div className="text-xs text-text-secondary mb-1 uppercase tracking-wider">关键水平</div>
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
  const annotations = useStore((s) => s.annotations);
  const setAnnotations = useStore((s) => s.setAnnotations);

  const [candles, setCandles] = useState<Candle[]>([]);
  const [hoveredBar, setHoveredBar] = useState<AnalyzeBarDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Annotation mode
  const [annotationMode, setAnnotationMode] = useState<"none" | "event" | "level">("none");
  const [selectedEventType, setSelectedEventType] = useState("SC");
  const [annotationListOpen, setAnnotationListOpen] = useState(false);
  const [deletePopover, setDeletePopover] = useState<{id: string; x: number; y: number; label: string} | null>(null);

  // Drawing tools — KLC built-in overlays
  type DrawingMode = "none" | "segment" | "rayLine" | "priceChannelLine" | "fibonacciLine";
  const [drawingMode, setDrawingMode] = useState<DrawingMode>("none");

  // Selection
  const [symbol, setSymbol] = useState("ETHUSDT");
  const [timeframe, setTimeframe] = useState("H4");
  const [barCount, setBarCount] = useState(2000);

  // Chat panel
  const [chatVisible, setChatVisible] = useState(false);
  const [selectedBarIndex, setSelectedBarIndex] = useState<number | undefined>();

  // Chart refs
  const mainContainerRef = useRef<HTMLDivElement | null>(null);
  const confContainerRef = useRef<HTMLDivElement | null>(null);
  const mainChartRef = useRef<Chart | null>(null);
  const confChartRef = useRef<Chart | null>(null);
  const disposedRef = useRef(false);

  // Annotation data for overlay
  const annotDataRef = useRef<AnnotationData[]>([]);

  // Candle data ref for chart data loader
  const candleDataRef = useRef<KLineData[]>([]);

  // Build candle map for quick lookup
  const candleMap = useMemo(() => {
    const m = new Map<string, Candle>();
    for (const c of candles) m.set(c.timestamp, c);
    return m;
  }, [candles]);

  // Build bar detail lookup by ms timestamp
  const barDetailMap = useMemo(() => {
    const m = new Map<number, AnalyzeBarDetail>();
    if (!analysisData) return m;
    for (const b of analysisData.bar_details) m.set(tsMs(b.timestamp), b);
    return m;
  }, [analysisData]);

  /* ------------- Register overlays (once) ------------- */
  useEffect(() => { registerAnalysisOverlays(); }, []);

  /* ------------- Initialize main chart ------------- */
  useEffect(() => {
    const container = mainContainerRef.current;
    if (!container) return;
    disposedRef.current = false;
    container.style.backgroundColor = "#0d1117";

    const chart = init(container, { styles: KLC_DARK_STYLES });
    if (!chart) return;

    chart.createIndicator("VOL", true, { id: "candle_pane" });

    // Create analysis overlays
    chart.createOverlay({ name: "phaseBgOverlay", lock: true, visible: true });
    chart.createOverlay({ name: "eventMarkerOverlay", lock: true, visible: true });
    chart.createOverlay({ name: "trBoundaryOverlay", lock: true, visible: true });
    chart.createOverlay({ name: "annotationOverlay", lock: true, visible: true });

    // Crosshair → bar detail
    chart.subscribeAction("onCrosshairChange", (data) => {
      const crosshair = data as Crosshair | undefined;
      if (!crosshair?.timestamp) return;
      const detail = barDetailMap.get(crosshair.timestamp) ?? null;
      setHoveredBar(detail);
      if (detail) setSelectedBarIndex(detail.bar_index);
    });

    mainChartRef.current = chart;

    let rafId1 = 0;
    const ro = new ResizeObserver(() => {
      if (disposedRef.current) return;
      cancelAnimationFrame(rafId1);
      rafId1 = requestAnimationFrame(() => {
        if (!disposedRef.current) { try { chart.resize(); } catch { /* */ } }
      });
    });
    ro.observe(container);

    return () => {
      disposedRef.current = true;
      mainChartRef.current = null;
      cancelAnimationFrame(rafId1);
      ro.disconnect();
      try { dispose(container); } catch { /* */ }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* ------------- Initialize confidence chart ------------- */
  useEffect(() => {
    const container = confContainerRef.current;
    if (!container) return;
    container.style.backgroundColor = "#131722";

    const chart = init(container, {
      styles: {
        ...KLC_DARK_STYLES,
        candle: { ...KLC_DARK_STYLES.candle, tooltip: { ...KLC_DARK_STYLES.candle.tooltip, showRule: "none" as const } },
      },
    });
    if (!chart) return;

    confChartRef.current = chart;

    let rafId2 = 0;
    const ro = new ResizeObserver(() => {
      if (disposedRef.current) return;
      cancelAnimationFrame(rafId2);
      rafId2 = requestAnimationFrame(() => {
        if (!disposedRef.current) { try { chart.resize(); } catch { /* */ } }
      });
    });
    ro.observe(container);

    return () => {
      confChartRef.current = null;
      cancelAnimationFrame(rafId2);
      ro.disconnect();
      try { dispose(container); } catch { /* */ }
    };
  }, []);

  /* ------------- Run Analysis ------------- */
  const runAnalysis = useCallback(async () => {
    setIsAnalyzing(true);
    setError(null);
    try {
      const analysis = await fetchAnalysis(symbol, barCount, timeframe);
      if (analysis.error) { setError(analysis.error); }
      else { setAnalysisData(analysis); setCandles(analysis.candles ?? []); }
    } catch (e) {
      setError(e instanceof Error ? e.message : "分析请求失败");
    } finally { setIsAnalyzing(false); }
  }, [symbol, barCount, timeframe, setIsAnalyzing, setAnalysisData]);

  /* ------------- Annotation helpers ------------- */
  const loadAnnotations = useCallback(async () => {
    try {
      const res = await fetchAnnotations(symbol, timeframe);
      setAnnotations(res.annotations);
      const ad: AnnotationData[] = res.annotations.map((a) => ({
        id: a.id, type: a.type, event_type: a.event_type,
        start_time: a.start_time, end_time: a.end_time,
        price: a.price, level_label: a.level_label, structure_type: a.structure_type,
      }));
      annotDataRef.current = ad;
      try { mainChartRef.current?.overrideOverlay({ name: "annotationOverlay", extendData: ad }); } catch { /* */ }
    } catch { /* backend may not be running */ }
  }, [symbol, timeframe, setAnnotations]);

  const handleCreateAnnotation = useCallback(async (partial: Partial<WyckoffAnnotation>) => {
    try { await createAnnotation({ ...partial, symbol, timeframe }); await loadAnnotations(); } catch { /* */ }
  }, [symbol, timeframe, loadAnnotations]);

  const handleDeleteAnnotation = useCallback(async (id: string) => {
    try { await deleteAnnotation(id, symbol, timeframe); await loadAnnotations(); } catch { /* */ }
  }, [symbol, timeframe, loadAnnotations]);

  /* ------------- Feed data to main chart when candles change ------------- */
  useEffect(() => {
    const chart = mainChartRef.current;
    if (!chart || candles.length === 0 || disposedRef.current) return;
    const klineData = candles.map(toKLineData);
    candleDataRef.current = klineData;
    console.log("[KLC-main] data ready:", klineData.length, "bars, first:", klineData[0]);
    try {
      // Order matters: setDataLoader → setPeriod → setSymbol
      // KLC v10 triggers _processDataLoad('init') on each call, but only fires
      // getBars when ALL THREE (dataLoader + symbol + period) are non-null.
      chart.setDataLoader({
        getBars: (params) => {
          const data = candleDataRef.current;
          console.log("[KLC-main] getBars type:", params.type, "len:", data.length);
          params.callback(params.type === "init" ? data : [], false);
        },
      });
      chart.setPeriod(tfToPeriod(timeframe));
      chart.setSymbol({ ticker: symbol, pricePrecision: 2, volumePrecision: 4 });
    } catch (e) { console.error("[KLC-main] setDataLoader error:", e); }
  }, [candles, symbol, timeframe]);

  /* ------------- Feed data to confidence chart ------------- */
  useEffect(() => {
    const chart = confChartRef.current;
    if (!chart || !analysisData || disposedRef.current) return;
    const confData: KLineData[] = analysisData.bar_details.map((b) => ({
      timestamp: tsMs(b.timestamp), open: b.c, high: b.c, low: b.c, close: b.c, volume: 0,
    }));
    console.log("[KLC-conf] data ready:", confData.length, "bars");
    try {
      chart.setDataLoader({
        getBars: (params) => {
          console.log("[KLC-conf] getBars type:", params.type, "len:", confData.length);
          params.callback(params.type === "init" ? confData : [], false);
        },
      });
      chart.setPeriod(tfToPeriod(timeframe));
      chart.setSymbol({ ticker: "confidence", pricePrecision: 4, volumePrecision: 0 });
    } catch { /* disposed */ }
  }, [analysisData, timeframe]);

  /* ------------- Update overlays when analysis data changes ------------- */
  useEffect(() => {
    if (!analysisData || disposedRef.current) return;
    const chart = mainChartRef.current;
    if (!chart) return;
    const bars = analysisData.bar_details;
    try {
      chart.overrideOverlay({ name: "phaseBgOverlay", extendData: buildPhaseSegments(bars) });
      chart.overrideOverlay({ name: "eventMarkerOverlay", extendData: buildEventMarkers(bars, candleMap) });
      chart.overrideOverlay({ name: "trBoundaryOverlay", extendData: buildTRBoundaries(bars) });
    } catch { /* disposed */ }
  }, [analysisData, candleMap]);

  /* ------------- Load annotations after analysis ------------- */
  useEffect(() => { if (analysisData) loadAnnotations(); }, [analysisData, loadAnnotations]);

  /* ------------- Auto-load on mount ------------- */
  useEffect(() => { runAnalysis(); }, [symbol, barCount, timeframe]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ------------- Drawing tools: use KLC built-in overlays ------------- */
  const handleDrawingTool = useCallback((tool: DrawingMode) => {
    const chart = mainChartRef.current;
    if (!chart) return;
    setAnnotationMode("none");
    if (tool === drawingMode || tool === "none") {
      setDrawingMode("none");
      return;
    }
    setDrawingMode(tool);
    chart.createOverlay(tool);
  }, [drawingMode]);

  const clearDrawings = useCallback(() => {
    mainChartRef.current?.removeOverlay({ name: "segment" });
    mainChartRef.current?.removeOverlay({ name: "rayLine" });
    mainChartRef.current?.removeOverlay({ name: "priceChannelLine" });
    mainChartRef.current?.removeOverlay({ name: "fibonacciLine" });
    setDrawingMode("none");
  }, []);

  /* ------------- Highlight bars from AI diagnosis ------------- */
  const handleHighlightBars = useCallback((barIndices: number[]) => {
    if (!analysisData) return;
    const kept = annotDataRef.current.filter((a) => !a.id.startsWith("__highlight_"));
    const highlights: AnnotationData[] = barIndices.map((idx) => {
      const bar = analysisData.bar_details.find((b) => b.bar_index === idx);
      if (!bar) return null;
      const ts = Math.floor(tsMs(bar.timestamp) / 1000);
      return { id: `__highlight_${idx}`, type: "event" as const, event_type: `#${idx}`, start_time: ts, end_time: ts + 14400, color: "rgba(255, 200, 0, 0.35)" };
    }).filter(Boolean) as AnnotationData[];
    const combined = [...kept, ...highlights];
    annotDataRef.current = combined;
    try { mainChartRef.current?.overrideOverlay({ name: "annotationOverlay", extendData: combined }); } catch { /* */ }
  }, [analysisData]);

  /* ------------- Annotation event mode handler ------------- */
  useEffect(() => {
    const chart = mainChartRef.current;
    const container = mainContainerRef.current;
    if (!chart || !container || annotationMode !== "event") return;

    let isDragging = false;
    let dragStartTs: number | null = null;
    let previewDiv: HTMLDivElement | null = null;

    const onMouseDown = (e: MouseEvent) => {
      const rect = container.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const info = chart.convertFromPixel([{ x, y: 0 }], { paneId: "candle_pane" });
      const pt = Array.isArray(info) ? info[0] : info;
      if (!pt?.timestamp) return;
      isDragging = true;
      dragStartTs = pt.timestamp;
      previewDiv = document.createElement("div");
      previewDiv.style.cssText = "position:absolute;top:0;bottom:0;background:rgba(59,130,246,0.15);border-left:1px solid rgba(59,130,246,0.5);border-right:1px solid rgba(59,130,246,0.5);pointer-events:none;z-index:10;";
      previewDiv.style.left = x + "px";
      previewDiv.style.width = "2px";
      container.style.position = "relative";
      container.appendChild(previewDiv);
      e.preventDefault();
    };

    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging || !previewDiv || dragStartTs === null) return;
      const rect = container.getBoundingClientRect();
      const currentX = e.clientX - rect.left;
      const startPx = chart.convertToPixel([{ timestamp: dragStartTs }], { paneId: "candle_pane" });
      const sp = Array.isArray(startPx) ? startPx[0] : startPx;
      if (sp?.x != null) {
        const left = Math.min(sp.x, currentX);
        const width = Math.abs(currentX - sp.x);
        previewDiv.style.left = left + "px";
        previewDiv.style.width = Math.max(width, 2) + "px";
      }
    };

    const onMouseUp = (e: MouseEvent) => {
      if (!isDragging || dragStartTs === null) return;
      isDragging = false;
      if (previewDiv) { previewDiv.remove(); previewDiv = null; }
      const rect = container.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const info = chart.convertFromPixel([{ x, y: 0 }], { paneId: "candle_pane" });
      const pt = Array.isArray(info) ? info[0] : info;
      const endTs = pt?.timestamp;
      if (!endTs) { dragStartTs = null; return; }
      const startSec = Math.floor(Math.min(dragStartTs, endTs) / 1000);
      const endSec = Math.floor(Math.max(dragStartTs, endTs) / 1000);
      dragStartTs = null;
      if (endSec - startSec < 3600) return;
      handleCreateAnnotation({ type: "event", event_type: selectedEventType, start_time: startSec, end_time: endSec });
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

  /* ------------- Level click handler ------------- */
  useEffect(() => {
    const chart = mainChartRef.current;
    if (!chart || annotationMode !== "level") return;
    const cb = (data: unknown) => {
      const cross = data as Crosshair | undefined;
      if (!cross?.kLineData) return;
      const price = cross.kLineData.close;
      const label = prompt("水平线标签 (如 SC_LOW, AR_HIGH):", "支撑") ?? "Level";
      handleCreateAnnotation({ type: "level", price, level_label: label });
    };
    chart.subscribeAction("onCandleBarClick", cb);
    return () => { try { chart.unsubscribeAction("onCandleBarClick", cb); } catch { /* */ } };
  }, [annotationMode, handleCreateAnnotation]);

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
        <select value={symbol} onChange={e => setSymbol(e.target.value)}
          className="bg-panel-surface text-text-primary text-xs px-2 py-1.5 rounded border border-panel-border">
          <option value="ETHUSDT">ETH/USDT</option>
          <option value="BTCUSDT">BTC/USDT</option>
          <option value="SOLUSDT">SOL/USDT</option>
        </select>
        <select value={timeframe} onChange={e => setTimeframe(e.target.value)}
          className="bg-panel-surface text-text-primary text-xs px-2 py-1.5 rounded border border-panel-border">
          <option value="H4">H4</option><option value="H1">H1</option>
          <option value="D1">D1</option><option value="M15">M15</option>
        </select>
        <select value={barCount} onChange={e => setBarCount(Number(e.target.value))}
          className="bg-panel-surface text-text-primary text-xs px-2 py-1.5 rounded border border-panel-border">
          <option value={500}>500根</option><option value={1000}>1000根</option>
          <option value={2000}>2000根</option><option value={3000}>3000根</option>
        </select>

        <button onClick={runAnalysis} disabled={isAnalyzing}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-accent-blue/15 text-accent-blue text-sm font-medium hover:bg-accent-blue/25 disabled:opacity-50 transition-colors">
          {isAnalyzing ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          {isAnalyzing ? "分析中..." : "重新分析"}
        </button>

        {/* Annotation tools */}
        <div className="flex items-center gap-1 border-l border-panel-border/50 pl-3">
          <button
            onClick={() => { setAnnotationMode((m) => m === "event" ? "none" : "event"); setDrawingMode("none"); }}
            className={`px-2 py-1 text-xs rounded transition-colors ${annotationMode === "event" ? "bg-accent-blue text-white" : "bg-panel-surface text-text-secondary hover:text-text-primary border border-panel-border"}`}>
            📌 标注事件
          </button>
          <button
            onClick={() => { setAnnotationMode((m) => m === "level" ? "none" : "level"); setDrawingMode("none"); }}
            className={`px-2 py-1 text-xs rounded transition-colors ${annotationMode === "level" ? "bg-accent-blue text-white" : "bg-panel-surface text-text-secondary hover:text-text-primary border border-panel-border"}`}>
            ─ 水平线
          </button>
          {annotationMode === "event" && (
            <select value={selectedEventType} onChange={(e) => setSelectedEventType(e.target.value)}
              className="bg-panel-surface text-text-primary text-xs px-1.5 py-1 rounded border border-panel-border">
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
          <AnnotationComparePanel symbol={symbol} timeframe={timeframe} />
        </div>

        {/* Drawing tools — KLC built-in overlays */}
        <div className="flex items-center gap-1 border-l border-panel-border/50 pl-2">
          <button onClick={() => handleDrawingTool("segment")}
            className={`px-2 py-1 text-xs rounded transition-colors ${drawingMode === "segment" ? "bg-white/90 text-[#0d1117] font-medium" : "bg-panel-surface text-text-secondary hover:text-text-primary border border-panel-border"}`}>
            ╱ 线段
          </button>
          <button onClick={() => handleDrawingTool("rayLine")}
            className={`px-2 py-1 text-xs rounded transition-colors ${drawingMode === "rayLine" ? "bg-accent-yellow text-[#0d1117] font-medium" : "bg-panel-surface text-text-secondary hover:text-text-primary border border-panel-border"}`}>
            → 射线
          </button>
          <button onClick={() => handleDrawingTool("priceChannelLine")}
            className={`px-2 py-1 text-xs rounded transition-colors ${drawingMode === "priceChannelLine" ? "bg-accent-blue text-white font-medium" : "bg-panel-surface text-text-secondary hover:text-text-primary border border-panel-border"}`}>
            ⫼ 通道
          </button>
          <button onClick={() => handleDrawingTool("fibonacciLine")}
            className={`px-2 py-1 text-xs rounded transition-colors ${drawingMode === "fibonacciLine" ? "bg-accent-purple text-white font-medium" : "bg-panel-surface text-text-secondary hover:text-text-primary border border-panel-border"}`}>
            Fib
          </button>
          <button onClick={clearDrawings}
            className="px-2 py-1 text-xs rounded bg-panel-surface text-accent-red/70 hover:text-accent-red border border-panel-border ml-1 transition-colors">
            清除绘图
          </button>
        </div>

        {/* Status info */}
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
            <button onClick={() => setAnnotationListOpen((v) => !v)}
              className="px-2 py-0.5 text-xs rounded bg-panel-surface border border-panel-border text-text-secondary hover:text-text-primary">
              标注({annotations.length})
            </button>
          </div>
        )}
        {error && <span className="text-accent-red text-xs ml-auto">{error}</span>}
      </div>

      {/* Main chart (70%) */}
      <div className="flex-[7] min-h-0 relative overflow-hidden">
        <div ref={mainContainerRef} className="w-full h-full" />
        {deletePopover && (
          <div className="absolute z-30 bg-panel-surface border border-panel-border rounded-lg shadow-lg p-2"
            style={{ left: deletePopover.x + 10, top: deletePopover.y - 20 }}>
            <p className="text-xs text-text-primary mb-2">
              删除标注 <span className="text-accent-blue font-mono">{deletePopover.label}</span> ?
            </p>
            <div className="flex gap-2">
              <button onClick={() => { handleDeleteAnnotation(deletePopover.id); setDeletePopover(null); }}
                className="px-2 py-1 text-xs bg-accent-red/15 text-accent-red rounded hover:bg-accent-red/25">删除</button>
              <button onClick={() => setDeletePopover(null)}
                className="px-2 py-1 text-xs bg-panel-surface text-text-secondary rounded border border-panel-border hover:text-text-primary">取消</button>
            </div>
          </div>
        )}
      </div>

      {/* Confidence chart (30%) */}
      <div className="flex-[3] min-h-0 border-t border-panel-border overflow-hidden">
        <div ref={confContainerRef} className="w-full h-full" />
      </div>

      {/* Annotation list popover */}
      {annotationListOpen && (
        <div className="absolute bottom-16 right-4 z-30 w-80 max-h-64 overflow-auto bg-panel-surface border border-panel-border rounded-lg shadow-xl">
          <div className="flex items-center justify-between px-3 py-2 border-b border-panel-border/50">
            <span className="text-xs font-medium text-text-primary">标注列表 ({annotations.length})</span>
            <button onClick={() => setAnnotationListOpen(false)}
              className="text-text-muted hover:text-text-primary text-xs">✕</button>
          </div>
          {annotations.length === 0 ? (
            <div className="px-3 py-4 text-xs text-text-muted text-center">暂无标注</div>
          ) : (
            <div className="divide-y divide-panel-border/30">
              {annotations.map((a) => (
                <div key={a.id} className="flex items-center justify-between px-3 py-1.5 hover:bg-panel-hover/30">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-accent-blue font-mono">{a.type === "event" ? a.event_type : "Level"}</span>
                    <span className="text-text-muted">{a.type}</span>
                  </div>
                  <button
                    onClick={(e) => setDeletePopover({ id: a.id, x: e.clientX, y: e.clientY, label: a.event_type ?? a.level_label ?? a.type })}
                    className="text-accent-red/50 hover:text-accent-red text-xs">🗑</button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      </div>

      {/* Right panel: Bar Detail + AI Diagnosis */}
      <div className="w-80 flex-shrink-0 flex flex-col border-l border-panel-border bg-panel-surface overflow-hidden">
        <div className="flex-1 min-h-0 overflow-auto border-b border-panel-border">
          <BarDetailPanel bar={hoveredBar} />
        </div>
        <div className="flex-1 min-h-0 overflow-hidden">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-panel-border/50">
            <span className="text-xs text-text-secondary font-medium uppercase tracking-wider">AI 诊断</span>
            <button onClick={() => setChatVisible((v) => !v)}
              className="text-xs text-accent-blue hover:underline">
              {chatVisible ? "收起" : "展开"}
            </button>
          </div>
          {chatVisible && (
            <DiagnosisChatPanel
              visible={chatVisible}
              onToggle={() => setChatVisible(false)}
              selectedBar={selectedBarIndex}
              analysisData={analysisData}
              onHighlightBars={handleHighlightBars}
            />
          )}
        </div>
      </div>
    </div>
  );
}
