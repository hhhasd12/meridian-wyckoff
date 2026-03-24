/**
 * AnnotationLayer — Series Primitive
 * Renders user annotations: event ranges, horizontal levels, structure labels.
 * 3-class pattern: Renderer → PaneView → Plugin (matches TRBoundaryBox).
 */

import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  Coordinate,
  IChartApi,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesOptionsMap,
  Time,
} from "lightweight-charts";

export interface AnnotationData {
  id: string;
  type: "event" | "level" | "structure";
  event_type?: string;
  start_time?: number;
  end_time?: number;
  price?: number;
  level_label?: string;
  structure_type?: string;
  color?: string;
}

/* Color by event type */
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

function structureColor(st?: string): string {
  if (!st) return "rgba(156,163,175,0.08)";
  return st.toUpperCase().includes("ACC")
    ? "rgba(34,197,94,0.08)"
    : "rgba(239,68,68,0.08)";
}

/* Resolved coordinates per annotation */
interface ResolvedAnnotation {
  data: AnnotationData;
  x1: number | null;
  x2: number | null;
  y: number | null;
}

/* ------------------------------------------------------------------ */
/* Renderer                                                            */
/* ------------------------------------------------------------------ */

class AnnotationRenderer implements IPrimitivePaneRenderer {
  constructor(private _items: ResolvedAnnotation[]) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      const w = scope.mediaSize.width;
      const h = scope.mediaSize.height;

      for (const item of this._items) {
        const d = item.data;

        if (d.type === "event") {
          if (item.x1 === null || item.x2 === null) continue;
          const x = Math.min(item.x1, item.x2);
          const rw = Math.max(Math.abs(item.x2 - item.x1), 24); // 最小24px确保可见
          const baseColor = d.color ?? eventColor(d.event_type);
          ctx.fillStyle = baseColor;
          ctx.fillRect(x, 0, rw, h);
          // Border for clarity
          ctx.strokeStyle = baseColor.replace("0.2)", "0.6)");
          ctx.lineWidth = 1;
          ctx.strokeRect(x, 0, rw, h);
          // Top label with background
          ctx.save();
          ctx.font = "bold 12px sans-serif";
          const label = d.event_type ?? "?";
          const tm = ctx.measureText(label);
          ctx.fillStyle = "rgba(0,0,0,0.6)";
          ctx.fillRect(x + 2, 2, tm.width + 6, 18);
          ctx.fillStyle = "#e6edf3";
          ctx.fillText(label, x + 5, 16);
          ctx.restore();
        } else if (d.type === "level") {
          if (item.y === null) continue;
          ctx.save();
          ctx.strokeStyle = d.color ?? "rgba(255,255,255,0.6)";
          ctx.lineWidth = 1;
          ctx.setLineDash([5, 5]);
          ctx.beginPath();
          ctx.moveTo(0, item.y);
          ctx.lineTo(w, item.y);
          ctx.stroke();
          // Right label
          const label = d.level_label ?? `${(d.price ?? 0).toFixed(1)}`;
          ctx.setLineDash([]);
          ctx.font = "12px sans-serif";
          const tm = ctx.measureText(label);
          const lx = w - tm.width - 12;
          ctx.fillStyle = "rgba(30,30,30,0.8)";
          ctx.fillRect(lx - 4, item.y - 12, tm.width + 8, 16);
          ctx.fillStyle = "#e6edf3";
          ctx.fillText(label, lx, item.y);
          ctx.restore();
        } else if (d.type === "structure") {
          if (item.x1 === null || item.x2 === null) continue;
          const x = Math.min(item.x1, item.x2);
          const rw = Math.abs(item.x2 - item.x1) || 8;
          ctx.fillStyle = d.color ?? structureColor(d.structure_type);
          ctx.fillRect(x, 0, rw, h);
          // Center label
          ctx.save();
          ctx.font = "bold 13px sans-serif";
          ctx.fillStyle = "#8b949e";
          ctx.globalAlpha = 0.7;
          ctx.textAlign = "center";
          ctx.fillText(d.structure_type ?? "", x + rw / 2, h / 2);
          ctx.restore();
        }
      }
    });
  }
}

/* ------------------------------------------------------------------ */
/* PaneView                                                            */
/* ------------------------------------------------------------------ */

class AnnotationPaneView implements IPrimitivePaneView {
  private _items: ResolvedAnnotation[] = [];
  private _source: AnnotationLayer;

  constructor(source: AnnotationLayer) {
    this._source = source;
  }

  update(): void {
    const { series, chart } = this._source;
    if (!series || !chart) { this._items = []; return; }
    const ts = chart.timeScale();

    this._items = this._source.annotations.map((d) => {
      let x1: Coordinate | null = null;
      let x2: Coordinate | null = null;
      let y: Coordinate | null = null;
      if (d.start_time != null) x1 = ts.timeToCoordinate(d.start_time as unknown as Time);
      if (d.end_time != null) x2 = ts.timeToCoordinate(d.end_time as unknown as Time);
      if (d.price != null) y = series.priceToCoordinate(d.price);
      return { data: d, x1: x1 as number | null, x2: x2 as number | null, y: y as number | null };
    });
  }

  zOrder(): "bottom" { return "bottom"; }
  renderer(): AnnotationRenderer { return new AnnotationRenderer(this._items); }
}

/* ------------------------------------------------------------------ */
/* Plugin                                                              */
/* ------------------------------------------------------------------ */

export class AnnotationLayer implements ISeriesPrimitive<Time> {
  annotations: AnnotationData[] = [];
  series: ISeriesApi<keyof SeriesOptionsMap> | null = null;
  chart: IChartApi | null = null;
  private _view: AnnotationPaneView;
  private _requestUpdate?: () => void;

  constructor() { this._view = new AnnotationPaneView(this); }

  attached({ series, chart, requestUpdate }: SeriesAttachedParameter<Time>): void {
    this.series = series; this.chart = chart; this._requestUpdate = requestUpdate;
  }
  detached(): void {
    this.series = null; this.chart = null; this._requestUpdate = undefined;
  }
  updateAllViews(): void { this._view.update(); }
  paneViews() { return [this._view]; }

  setAnnotations(data: AnnotationData[]): void {
    this.annotations = data; this._requestUpdate?.();
  }
  addAnnotation(data: AnnotationData): void {
    this.annotations = [...this.annotations, data]; this._requestUpdate?.();
  }
  removeAnnotation(id: string): void {
    this.annotations = this.annotations.filter((a) => a.id !== id); this._requestUpdate?.();
  }
}
