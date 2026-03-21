/**
 * FvgZones — Series Primitive
 * Draws FVG gap zones as semi-transparent rectangles.
 * Bullish = green, Bearish = red
 */

import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  Coordinate,
  ISeriesApi,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesOptionsMap,
  Time,
} from "lightweight-charts";
import type { FVGSignal } from "../types/api";

interface FvgRect {
  topY: Coordinate | null;
  bottomY: Coordinate | null;
  color: string;
  opacity: number;
}

class FvgPaneRenderer implements IPrimitivePaneRenderer {
  constructor(private _rects: FvgRect[]) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const width = scope.bitmapSize.width;

      for (const rect of this._rects) {
        if (rect.topY === null || rect.bottomY === null) continue;

        const y1 = Math.round(rect.topY * scope.verticalPixelRatio);
        const y2 = Math.round(rect.bottomY * scope.verticalPixelRatio);
        const top = Math.min(y1, y2);
        const height = Math.abs(y2 - y1);

        ctx.save();
        ctx.globalAlpha = rect.opacity;
        ctx.fillStyle = rect.color;
        ctx.fillRect(0, top, width, Math.max(height, 1));

        // Border line at top and bottom
        ctx.globalAlpha = rect.opacity * 2;
        ctx.strokeStyle = rect.color;
        ctx.lineWidth = Math.max(1, scope.verticalPixelRatio);
        ctx.beginPath();
        ctx.moveTo(0, top + 0.5);
        ctx.lineTo(width, top + 0.5);
        ctx.moveTo(0, top + height + 0.5);
        ctx.lineTo(width, top + height + 0.5);
        ctx.stroke();
        ctx.restore();
      }
    });
  }
}

class FvgPaneView implements IPrimitivePaneView {
  private _rects: FvgRect[] = [];
  private _source: FvgZones;

  constructor(source: FvgZones) {
    this._source = source;
  }

  update(): void {
    const series = this._source.series;
    if (!series) {
      this._rects = [];
      return;
    }

    this._rects = this._source.fvgSignals.map((fvg) => {
      const isBullish = fvg.direction === "BULLISH";
      return {
        topY: series.priceToCoordinate(fvg.gap_top),
        bottomY: series.priceToCoordinate(fvg.gap_bottom),
        color: isBullish ? "#3fb950" : "#f85149",
        opacity: Math.max(0.08, 0.2 * (1 - fvg.fill_ratio)),
      };
    });
  }

  zOrder(): "bottom" {
    return "bottom";
  }

  renderer(): FvgPaneRenderer {
    return new FvgPaneRenderer(this._rects);
  }
}

export class FvgZones implements ISeriesPrimitive<Time> {
  fvgSignals: FVGSignal[] = [];
  series: ISeriesApi<keyof SeriesOptionsMap> | null = null;
  private _view: FvgPaneView;
  private _requestUpdate?: () => void;

  constructor() {
    this._view = new FvgPaneView(this);
  }

  attached({ series, requestUpdate }: SeriesAttachedParameter<Time>): void {
    this.series = series;
    this._requestUpdate = requestUpdate;
  }

  detached(): void {
    this.series = null;
    this._requestUpdate = undefined;
  }

  updateAllViews(): void {
    this._view.update();
  }

  paneViews() {
    return [this._view];
  }

  setFvgSignals(signals: FVGSignal[]): void {
    this.fvgSignals = signals;
    this._requestUpdate?.();
  }
}
