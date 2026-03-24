/**
 * klc-overlays.ts — KLineChart v10 custom overlay registrations
 * Replaces 5 deleted LWC ISeriesPrimitive plugins with KLC native overlays.
 * All overlays are non-interactive (totalStep: 0), data via extendData.
 */

import { registerOverlay } from "klinecharts";
import type { OverlayTemplate, OverlayFigure, OverlayCreateFiguresCallbackParams } from "klinecharts";
import type { WyckoffPhase } from "../types/api";

/* ------------------------------------------------------------------ */
/* Phase background colors                                             */
/* ------------------------------------------------------------------ */

const PHASE_COLORS: Record<string, string> = {
  A: "rgba(139,148,158,0.08)",
  B: "rgba(210,153,34,0.08)",
  C: "rgba(63,185,80,0.08)",
  D: "rgba(88,166,255,0.08)",
  E: "rgba(188,140,255,0.08)",
  IDLE: "rgba(0,0,0,0)",
};

/* ------------------------------------------------------------------ */
/* Event marker direction classification                               */
/* ------------------------------------------------------------------ */

const BULLISH_STATES = new Set(["SC", "SPRING", "SOS", "TEST", "JOC", "LPS"]);
const BEARISH_STATES = new Set(["LPSY", "UTAD", "SOW", "UT"]);

export function classifyState(state: string): "bullish" | "bearish" | "neutral" {
  const abbrev = state.toUpperCase().replace(/[^A-Z]/g, "");
  if (BULLISH_STATES.has(abbrev)) return "bullish";
  if (BEARISH_STATES.has(abbrev)) return "bearish";
  return "neutral";
}

/* ------------------------------------------------------------------ */
/* Annotation event color helpers                                      */
/* ------------------------------------------------------------------ */

function eventColor(et?: string): string {
  if (!et) return "rgba(156,163,175,0.2)";
  const upper = et.toUpperCase();
  if (upper === "SC" || upper === "BC") return "rgba(239,68,68,0.2)";
  if (upper === "AR" || upper === "AR_DIST") return "rgba(59,130,246,0.2)";
  if (upper === "SPRING" || upper === "UTAD") return "rgba(234,179,8,0.2)";
  if (upper === "ST" || upper === "TEST" || upper === "ST_DIST") return "rgba(168,85,247,0.2)";
  if (upper === "SOS" || upper === "SOW" || upper === "JOC") return "rgba(34,197,94,0.2)";
  return "rgba(156,163,175,0.2)";
}

/* ------------------------------------------------------------------ */
/* Shared types for extendData                                         */
/* ------------------------------------------------------------------ */

export interface PhaseSegment {
  startTs: number; // ms timestamp
  endTs: number;
  phase: WyckoffPhase;
}

export interface EventMarkerData {
  timestamp: number; // ms
  price: number;
  state: string;
  direction: "bullish" | "bearish" | "neutral";
}

export interface TRBoundaryData {
  startTs: number; // ms
  endTs: number;
  support: number;
  resistance: number;
  confidence: number;
}

export interface AnnotationData {
  id: string;
  type: "event" | "level" | "structure";
  event_type?: string;
  start_time?: number; // unix seconds
  end_time?: number;
  price?: number;
  level_label?: string;
  structure_type?: string;
  color?: string;
}

/* ------------------------------------------------------------------ */
/* Registration (call once)                                            */
/* ------------------------------------------------------------------ */

let registered = false;

export function registerAnalysisOverlays(): void {
  if (registered) return;
  registered = true;

  registerPhaseBgOverlay();
  registerEventMarkerOverlay();
  registerTRBoundaryOverlay();
  registerAnnotationOverlay();
}

/* ================================================================== */
/* 1. Phase Background Overlay                                         */
/* ================================================================== */

function registerPhaseBgOverlay(): void {
  const template: OverlayTemplate = {
    name: "phaseBgOverlay",
    totalStep: 0,
    createPointFigures: (params: OverlayCreateFiguresCallbackParams<unknown>) => {
      const segments = params.overlay.extendData as PhaseSegment[] | undefined;
      if (!segments?.length) return [];
      const { xAxis, yAxis, bounding } = params;
      if (!xAxis || !yAxis) return [];

      const figures: OverlayFigure[] = [];
      for (const seg of segments) {
        const x1 = xAxis.convertTimestampToPixel(seg.startTs);
        const x2 = xAxis.convertTimestampToPixel(seg.endTs);
        const color = PHASE_COLORS[seg.phase] ?? "rgba(0,0,0,0)";
        if (color === "rgba(0,0,0,0)") continue;

        figures.push({
          type: "rect",
          attrs: {
            x: Math.min(x1, x2),
            y: 0,
            width: Math.abs(x2 - x1),
            height: bounding.height,
          },
          styles: { style: "fill", color, borderSize: 0 },
          ignoreEvent: true,
        });
      }
      return figures;
    },
  };
  registerOverlay(template);
}

/* ================================================================== */
/* 2. Event Marker Overlay                                             */
/* ================================================================== */

function registerEventMarkerOverlay(): void {
  const template: OverlayTemplate = {
    name: "eventMarkerOverlay",
    totalStep: 0,
    createPointFigures: (params: OverlayCreateFiguresCallbackParams<unknown>) => {
      const markers = params.overlay.extendData as EventMarkerData[] | undefined;
      if (!markers?.length) return [];
      const { xAxis, yAxis } = params;
      if (!xAxis || !yAxis) return [];

      const figures: OverlayFigure[] = [];
      for (const m of markers) {
        const x = xAxis.convertTimestampToPixel(m.timestamp);
        const y = yAxis.convertToPixel(m.price);
        const size = 5;

        let markerColor: string;
        if (m.direction === "bullish") {
          markerColor = "#3fb950";
          // Green triangle ▲ above price
          figures.push({
            type: "polygon",
            attrs: {
              coordinates: [
                { x, y: y - size - 4 },
                { x: x - size, y: y + size - 4 },
                { x: x + size, y: y + size - 4 },
              ],
            },
            styles: { style: "fill", color: markerColor },
            ignoreEvent: true,
          });
        } else if (m.direction === "bearish") {
          markerColor = "#f85149";
          // Red triangle ▼ below price
          figures.push({
            type: "polygon",
            attrs: {
              coordinates: [
                { x, y: y + size + 4 },
                { x: x - size, y: y - size + 4 },
                { x: x + size, y: y - size + 4 },
              ],
            },
            styles: { style: "fill", color: markerColor },
            ignoreEvent: true,
          });
        } else {
          markerColor = "#8b949e";
          // Gray circle
          figures.push({
            type: "circle",
            attrs: { x, y: y - 8, r: 3 },
            styles: { style: "fill", color: markerColor },
            ignoreEvent: true,
          });
        }

        // Text label
        const textY = m.direction === "bearish" ? y + size + 16 : y - size - 16;
        figures.push({
          type: "text",
          attrs: { x, y: textY, text: m.state, align: "center", baseline: "middle" },
          styles: {
            style: "fill",
            color: markerColor,
            size: 9,
            family: "JetBrains Mono, monospace",
            weight: "bold",
          },
          ignoreEvent: true,
        });
      }
      return figures;
    },
  };
  registerOverlay(template);
}

/* ================================================================== */
/* 3. TR Boundary Box Overlay                                          */
/* ================================================================== */

function registerTRBoundaryOverlay(): void {
  const template: OverlayTemplate = {
    name: "trBoundaryOverlay",
    totalStep: 0,
    createPointFigures: (params: OverlayCreateFiguresCallbackParams<unknown>) => {
      const boundaries = params.overlay.extendData as TRBoundaryData[] | undefined;
      if (!boundaries?.length) return [];
      const { xAxis, yAxis, bounding: _bounding } = params;
      if (!xAxis || !yAxis) return [];

      const figures: OverlayFigure[] = [];
      for (const b of boundaries) {
        const x1 = xAxis.convertTimestampToPixel(b.startTs);
        const x2 = xAxis.convertTimestampToPixel(b.endTs);
        const yTop = yAxis.convertToPixel(b.resistance);
        const yBot = yAxis.convertToPixel(b.support);
        const alpha = Math.max(0.02, Math.min(0.12, b.confidence * 0.12));

        // Fill
        figures.push({
          type: "rect",
          attrs: {
            x: Math.min(x1, x2),
            y: Math.min(yTop, yBot),
            width: Math.abs(x2 - x1),
            height: Math.abs(yBot - yTop),
          },
          styles: { style: "fill", color: `rgba(88,166,255,${alpha})`, borderSize: 0 },
          ignoreEvent: true,
        });

        // Top dashed line (resistance)
        const borderAlpha = Math.min(0.5, b.confidence * 0.5);
        figures.push({
          type: "line",
          attrs: { coordinates: [{ x: x1, y: yTop }, { x: x2, y: yTop }] },
          styles: {
            style: "dashed",
            color: `rgba(88,166,255,${borderAlpha})`,
            size: 1,
            dashedValue: [4, 3],
          },
          ignoreEvent: true,
        });

        // Bottom dashed line (support)
        figures.push({
          type: "line",
          attrs: { coordinates: [{ x: x1, y: yBot }, { x: x2, y: yBot }] },
          styles: {
            style: "dashed",
            color: `rgba(88,166,255,${borderAlpha})`,
            size: 1,
            dashedValue: [4, 3],
          },
          ignoreEvent: true,
        });
      }
      return figures;
    },
  };
  registerOverlay(template);
}

/* ================================================================== */
/* 4. Annotation Overlay (events + levels + structures)                */
/* ================================================================== */

function registerAnnotationOverlay(): void {
  const template: OverlayTemplate = {
    name: "annotationOverlay",
    totalStep: 0,
    createPointFigures: (params: OverlayCreateFiguresCallbackParams<unknown>) => {
      const annotations = params.overlay.extendData as AnnotationData[] | undefined;
      if (!annotations?.length) return [];
      const { xAxis, yAxis, bounding } = params;
      if (!xAxis || !yAxis) return [];

      const figures: OverlayFigure[] = [];
      for (const d of annotations) {
        if (d.type === "event") {
          if (d.start_time == null || d.end_time == null) continue;
          const x1 = xAxis.convertTimestampToPixel(d.start_time * 1000);
          const x2 = xAxis.convertTimestampToPixel(d.end_time * 1000);
          const x = Math.min(x1, x2);
          const w = Math.max(Math.abs(x2 - x1), 24);
          const bgColor = d.color ?? eventColor(d.event_type);

          // Background rect
          figures.push({
            type: "rect",
            attrs: { x, y: 0, width: w, height: bounding.height },
            styles: { style: "fill", color: bgColor, borderSize: 1, borderColor: bgColor.replace("0.2)", "0.6)") },
            ignoreEvent: true,
          });

          // Top label
          figures.push({
            type: "text",
            attrs: { x: x + 5, y: 16, text: d.event_type ?? "?", align: "left", baseline: "middle" },
            styles: { style: "fill", color: "#e6edf3", size: 12, family: "sans-serif", weight: "bold", backgroundColor: "rgba(0,0,0,0.6)" },
            ignoreEvent: true,
          });
        } else if (d.type === "level") {
          if (d.price == null) continue;
          const y = yAxis.convertToPixel(d.price);
          const label = d.level_label ?? `${d.price.toFixed(1)}`;

          // Horizontal dashed line
          figures.push({
            type: "line",
            attrs: { coordinates: [{ x: 0, y }, { x: bounding.width, y }] },
            styles: { style: "dashed", color: d.color ?? "rgba(255,255,255,0.6)", size: 1, dashedValue: [5, 5] },
            ignoreEvent: true,
          });

          // Right label
          figures.push({
            type: "text",
            attrs: { x: bounding.width - 12, y, text: label, align: "right", baseline: "middle" },
            styles: { style: "fill", color: "#e6edf3", size: 12, family: "sans-serif", backgroundColor: "rgba(30,30,30,0.8)" },
            ignoreEvent: true,
          });
        } else if (d.type === "structure") {
          if (d.start_time == null || d.end_time == null) continue;
          const x1 = xAxis.convertTimestampToPixel(d.start_time * 1000);
          const x2 = xAxis.convertTimestampToPixel(d.end_time * 1000);
          const x = Math.min(x1, x2);
          const w = Math.abs(x2 - x1) || 8;
          const st = d.structure_type?.toUpperCase() ?? "";
          const bgColor = st.includes("ACC") ? "rgba(34,197,94,0.08)" : "rgba(239,68,68,0.08)";

          figures.push({
            type: "rect",
            attrs: { x, y: 0, width: w, height: bounding.height },
            styles: { style: "fill", color: bgColor, borderSize: 0 },
            ignoreEvent: true,
          });

          // Center label
          figures.push({
            type: "text",
            attrs: { x: x + w / 2, y: bounding.height / 2, text: d.structure_type ?? "", align: "center", baseline: "middle" },
            styles: { style: "fill", color: "#8b949e", size: 13, family: "sans-serif", weight: "bold" },
            ignoreEvent: true,
          });
        }
      }
      return figures;
    },
  };
  registerOverlay(template);
}
