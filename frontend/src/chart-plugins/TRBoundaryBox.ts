/**
 * TRBoundaryBox — Series Primitive
 * Draws semi-transparent rectangles between support/resistance for trading ranges.
 * Uses chart ref for time coordinate and series ref for price coordinate.
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

export interface TRBoundaryData {
  startTime: Time;
  endTime: Time;
  support: number;
  resistance: number;
  confidence: number;
}

interface ResolvedBox {
  x1: Coordinate | null;
  x2: Coordinate | null;
  yTop: Coordinate | null;
  yBot: Coordinate | null;
  confidence: number;
}

class TRBoxRenderer implements IPrimitivePaneRenderer {
  constructor(private _boxes: ResolvedBox[]) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;

      for (const box of this._boxes) {
        if (
          box.x1 === null ||
          box.x2 === null ||
          box.yTop === null ||
          box.yBot === null
        )
          continue;

        const x = Math.min(box.x1, box.x2);
        const w = Math.abs(box.x2 - box.x1);
        const y = Math.min(box.yTop, box.yBot);
        const h = Math.abs(box.yBot - box.yTop);

        const alpha = Math.max(0.02, Math.min(0.12, box.confidence * 0.12));

        // Fill
        ctx.fillStyle = `rgba(88,166,255,${alpha})`;
        ctx.fillRect(x, y, w, h);

        // Border — top (resistance)
        ctx.save();
        ctx.strokeStyle = `rgba(88,166,255,${Math.min(0.5, box.confidence * 0.5)})`;
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 3]);

        ctx.beginPath();
        ctx.moveTo(x, box.yTop);
        ctx.lineTo(x + w, box.yTop);
        ctx.stroke();

        // Border — bottom (support)
        ctx.beginPath();
        ctx.moveTo(x, box.yBot);
        ctx.lineTo(x + w, box.yBot);
        ctx.stroke();

        ctx.restore();
      }
    });
  }
}

class TRBoxPaneView implements IPrimitivePaneView {
  private _boxes: ResolvedBox[] = [];
  private _source: TRBoundaryBox;

  constructor(source: TRBoundaryBox) {
    this._source = source;
  }

  update(): void {
    const { series, chart } = this._source;
    if (!series || !chart) {
      this._boxes = [];
      return;
    }

    const timeScale = chart.timeScale();
    this._boxes = this._source.boundaries.map((b) => ({
      x1: timeScale.timeToCoordinate(b.startTime),
      x2: timeScale.timeToCoordinate(b.endTime),
      yTop: series.priceToCoordinate(b.resistance),
      yBot: series.priceToCoordinate(b.support),
      confidence: b.confidence,
    }));
  }

  zOrder(): "bottom" {
    return "bottom";
  }

  renderer(): TRBoxRenderer {
    return new TRBoxRenderer(this._boxes);
  }
}

export class TRBoundaryBox implements ISeriesPrimitive<Time> {
  boundaries: TRBoundaryData[] = [];
  series: ISeriesApi<keyof SeriesOptionsMap> | null = null;
  chart: IChartApi | null = null;
  private _view: TRBoxPaneView;
  private _requestUpdate?: () => void;

  constructor() {
    this._view = new TRBoxPaneView(this);
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

  setBoundaries(boundaries: TRBoundaryData[]): void {
    this.boundaries = boundaries;
    this._requestUpdate?.();
  }
}
