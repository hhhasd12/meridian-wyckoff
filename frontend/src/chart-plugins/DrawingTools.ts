/**
 * DrawingTools — Series Primitive
 * Renders segments, rays, and parallel channels on the chart.
 * 3-class pattern: DrawingRenderer → DrawingPaneView → DrawingTools (Plugin)
 */

import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IChartApi,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesOptionsMap,
  Time,
} from "lightweight-charts";
import type { DrawingData } from "../types/api";

/* ------------------------------------------------------------------ */
/* Color defaults                                                      */
/* ------------------------------------------------------------------ */

const TOOL_COLORS: Record<string, string> = {
  segment: "rgba(255,255,255,0.7)",
  ray: "rgba(234,179,8,0.7)",
  channel: "rgba(59,130,246,0.5)",
};

const CHANNEL_FILL = "rgba(59,130,246,0.08)";

/* ------------------------------------------------------------------ */
/* Resolved drawing coordinates                                        */
/* ------------------------------------------------------------------ */

interface ResolvedDrawing {
  tool: DrawingData["tool"];
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  y1_offset?: number; // channel parallel line
  y2_offset?: number;
  color: string;
  label?: string;
  id: string;
}

/* ------------------------------------------------------------------ */
/* Renderer                                                            */
/* ------------------------------------------------------------------ */

class DrawingRenderer implements IPrimitivePaneRenderer {
  constructor(private _drawings: ResolvedDrawing[]) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      const { width, height } = scope.mediaSize;

      for (const d of this._drawings) {
        const color = d.color;
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";

        if (d.tool === "segment") {
          this._drawSegment(ctx, d);
        } else if (d.tool === "ray") {
          this._drawRay(ctx, d, width, height);
        } else if (d.tool === "channel") {
          this._drawChannel(ctx, d, color);
        }

        // Draw endpoint dots
        if (d.tool !== "channel") {
          this._drawEndpoint(ctx, d.x1, d.y1, color);
          this._drawEndpoint(ctx, d.x2, d.y2, color);
        }

        // Draw label if present
        if (d.label) {
          this._drawLabel(ctx, d);
        }

        ctx.restore();
      }
    });
  }

  private _drawSegment(
    ctx: CanvasRenderingContext2D,
    d: ResolvedDrawing,
  ): void {
    ctx.beginPath();
    ctx.moveTo(d.x1, d.y1);
    ctx.lineTo(d.x2, d.y2);
    ctx.stroke();
  }

  private _drawRay(
    ctx: CanvasRenderingContext2D,
    d: ResolvedDrawing,
    width: number,
    height: number,
  ): void {
    const dx = d.x2 - d.x1;
    const dy = d.y2 - d.y1;

    // Find the parameter t that extends to the chart boundary
    let t = 10; // fallback large extension
    if (dx !== 0) {
      const tRight = (width - d.x1) / dx;
      const tLeft = -d.x1 / dx;
      t = dx > 0 ? Math.max(tRight, 1) : Math.max(tLeft, 1);
    }
    if (dy !== 0) {
      const tBottom = (height - d.y1) / dy;
      const tTop = -d.y1 / dy;
      const tY = dy > 0 ? Math.max(tBottom, 1) : Math.max(tTop, 1);
      t = Math.min(t, tY);
    }
    t = Math.max(t, 1);

    const extX = d.x1 + dx * t;
    const extY = d.y1 + dy * t;

    ctx.beginPath();
    ctx.moveTo(d.x1, d.y1);
    ctx.lineTo(extX, extY);
    ctx.stroke();
  }

  private _drawChannel(
    ctx: CanvasRenderingContext2D,
    d: ResolvedDrawing,
    color: string,
  ): void {
    const y1off = d.y1_offset ?? d.y1;
    const y2off = d.y2_offset ?? d.y2;

    // Fill area between two parallel lines
    ctx.fillStyle = CHANNEL_FILL;
    ctx.beginPath();
    ctx.moveTo(d.x1, d.y1);
    ctx.lineTo(d.x2, d.y2);
    ctx.lineTo(d.x2, y2off);
    ctx.lineTo(d.x1, y1off);
    ctx.closePath();
    ctx.fill();

    // Top line
    ctx.strokeStyle = color;
    ctx.beginPath();
    ctx.moveTo(d.x1, d.y1);
    ctx.lineTo(d.x2, d.y2);
    ctx.stroke();

    // Bottom line (parallel)
    ctx.beginPath();
    ctx.moveTo(d.x1, y1off);
    ctx.lineTo(d.x2, y2off);
    ctx.stroke();

    // Endpoint dots on both lines
    this._drawEndpoint(ctx, d.x1, d.y1, color);
    this._drawEndpoint(ctx, d.x2, d.y2, color);
    this._drawEndpoint(ctx, d.x1, y1off, color);
    this._drawEndpoint(ctx, d.x2, y2off, color);
  }

  private _drawEndpoint(
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    color: string,
  ): void {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
  }

  private _drawLabel(
    ctx: CanvasRenderingContext2D,
    d: ResolvedDrawing,
  ): void {
    const mx = (d.x1 + d.x2) / 2;
    const my = (d.y1 + d.y2) / 2;
    ctx.font = "11px sans-serif";
    ctx.fillStyle = d.color;
    ctx.globalAlpha = 0.9;
    const text = d.label!;
    const tm = ctx.measureText(text);
    const px = 4;
    const py = 2;

    // Background pill
    ctx.fillStyle = "rgba(30,34,45,0.85)";
    ctx.beginPath();
    ctx.roundRect(
      mx - tm.width / 2 - px,
      my - 7 - py,
      tm.width + px * 2,
      14 + py * 2,
      3,
    );
    ctx.fill();

    // Text
    ctx.fillStyle = d.color;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, mx, my);
  }
}

/* ------------------------------------------------------------------ */
/* PaneView                                                            */
/* ------------------------------------------------------------------ */

class DrawingPaneView implements IPrimitivePaneView {
  private _resolved: ResolvedDrawing[] = [];
  private _source: DrawingTools;

  constructor(source: DrawingTools) {
    this._source = source;
  }

  update(): void {
    const { series, chart } = this._source;
    if (!series || !chart) {
      this._resolved = [];
      return;
    }

    const timeScale = chart.timeScale();
    this._resolved = this._source.drawings
      .map((d): ResolvedDrawing | null => {
        const x1 = timeScale.timeToCoordinate(
          d.x1_time as unknown as Time,
        );
        const x2 = timeScale.timeToCoordinate(
          d.x2_time as unknown as Time,
        );
        const y1 = series.priceToCoordinate(d.y1_price);
        const y2 = series.priceToCoordinate(d.y2_price);

        if (x1 === null || x2 === null || y1 === null || y2 === null) {
          return null;
        }

        const result: ResolvedDrawing = {
          tool: d.tool,
          x1: x1 as number,
          y1: y1 as number,
          x2: x2 as number,
          y2: y2 as number,
          color: d.color ?? TOOL_COLORS[d.tool] ?? TOOL_COLORS.segment!,
          label: d.label,
          id: d.id,
        };

        // Channel: compute offset coordinates
        if (d.tool === "channel" && d.channel_offset != null) {
          const y1off = series.priceToCoordinate(
            d.y1_price + d.channel_offset,
          );
          const y2off = series.priceToCoordinate(
            d.y2_price + d.channel_offset,
          );
          result.y1_offset =
            y1off !== null ? (y1off as number) : undefined;
          result.y2_offset =
            y2off !== null ? (y2off as number) : undefined;
        }

        return result;
      })
      .filter(Boolean) as ResolvedDrawing[];
  }

  renderer(): DrawingRenderer {
    return new DrawingRenderer(this._resolved);
  }
}

/* ------------------------------------------------------------------ */
/* Plugin                                                              */
/* ------------------------------------------------------------------ */

export class DrawingTools implements ISeriesPrimitive<Time> {
  drawings: DrawingData[] = [];
  series: ISeriesApi<keyof SeriesOptionsMap> | null = null;
  chart: IChartApi | null = null;
  private _view: DrawingPaneView;
  private _requestUpdate?: () => void;

  constructor() {
    this._view = new DrawingPaneView(this);
  }

  attached({
    series,
    chart,
    requestUpdate,
  }: SeriesAttachedParameter<Time>): void {
    this.series = series;
    this.chart = chart;
    this._requestUpdate = requestUpdate;
  }

  detached(): void {
    this.series = null;
    this.chart = null;
    this._requestUpdate = undefined;
  }

  updateAllViews(): void {
    this._view.update();
  }

  paneViews() {
    return [this._view];
  }

  /* Public API */

  setDrawings(data: DrawingData[]): void {
    this.drawings = data;
    this._requestUpdate?.();
  }

  addDrawing(data: DrawingData): void {
    this.drawings = [...this.drawings, data];
    this._requestUpdate?.();
  }

  removeDrawing(id: string): void {
    this.drawings = this.drawings.filter((d) => d.id !== id);
    this._requestUpdate?.();
  }
}
