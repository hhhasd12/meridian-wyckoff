/**
 * PhaseBgSegmented — Series Primitive
 * Per-bar phase background coloring with segmented rectangles.
 * Uses chart ref for time coordinate mapping (like TradeMarkers).
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
import type { WyckoffPhase } from "../types/api";

const PHASE_COLORS: Record<WyckoffPhase, string> = {
  A: "rgba(139,148,158,0.08)",
  B: "rgba(210,153,34,0.08)",
  C: "rgba(63,185,80,0.08)",
  D: "rgba(88,166,255,0.08)",
  E: "rgba(188,140,255,0.08)",
  IDLE: "rgba(0,0,0,0)",
};

export interface PhaseSegment {
  startTime: Time;
  endTime: Time;
  phase: WyckoffPhase;
}

interface ResolvedRect {
  x1: Coordinate | null;
  x2: Coordinate | null;
  color: string;
}

class PhaseBgRenderer implements IPrimitivePaneRenderer {
  constructor(private _rects: ResolvedRect[]) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      const h = scope.mediaSize.height;

      for (const r of this._rects) {
        if (r.x1 === null || r.x2 === null) continue;
        if (r.color === "rgba(0,0,0,0)") continue;

        const x = Math.min(r.x1, r.x2);
        const w = Math.abs(r.x2 - r.x1);

        ctx.fillStyle = r.color;
        ctx.fillRect(x, 0, w, h);
      }
    });
  }
}

class PhaseBgPaneView implements IPrimitivePaneView {
  private _rects: ResolvedRect[] = [];
  private _source: PhaseBgSegmented;

  constructor(source: PhaseBgSegmented) {
    this._source = source;
  }

  update(): void {
    const { chart } = this._source;
    if (!chart) {
      this._rects = [];
      return;
    }

    const timeScale = chart.timeScale();
    this._rects = this._source.segments.map((seg) => ({
      x1: timeScale.timeToCoordinate(seg.startTime),
      x2: timeScale.timeToCoordinate(seg.endTime),
      color: PHASE_COLORS[seg.phase] ?? "rgba(0,0,0,0)",
    }));
  }

  zOrder(): "bottom" {
    return "bottom";
  }

  renderer(): PhaseBgRenderer {
    return new PhaseBgRenderer(this._rects);
  }
}

export class PhaseBgSegmented implements ISeriesPrimitive<Time> {
  segments: PhaseSegment[] = [];
  series: ISeriesApi<keyof SeriesOptionsMap> | null = null;
  chart: IChartApi | null = null;
  private _view: PhaseBgPaneView;
  private _requestUpdate?: () => void;

  constructor() {
    this._view = new PhaseBgPaneView(this);
  }

  attached({ series, chart, requestUpdate }: SeriesAttachedParameter<Time>): void {
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

  setSegments(segments: PhaseSegment[]): void {
    this.segments = segments;
    this._requestUpdate?.();
  }
}
