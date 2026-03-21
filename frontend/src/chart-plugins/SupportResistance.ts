/**
 * SupportResistance — Series Primitive
 * Draws horizontal S/R lines from critical_levels (SC_LOW, AR_HIGH, BC_HIGH, etc.)
 */

import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  Coordinate,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesOptionsMap,
  Time,
} from "lightweight-charts";

const LEVEL_COLORS: Record<string, string> = {
  SC_LOW: "#3fb950",
  AR_HIGH: "#f85149",
  BC_HIGH: "#d29922",
  ST_LOW: "#58a6ff",
  SPRING_LOW: "#39d2c0",
  LPSY_HIGH: "#bc8cff",
};

const DEFAULT_COLOR = "#8b949e";

interface LevelLine {
  price: number;
  label: string;
  color: string;
  y: Coordinate | null;
}

class SRPaneRenderer implements IPrimitivePaneRenderer {
  constructor(private _lines: LevelLine[]) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      const width = scope.bitmapSize.width;

      for (const line of this._lines) {
        if (line.y === null) continue;

        const yBitmap = Math.round(line.y * scope.verticalPixelRatio);

        // Dashed line
        ctx.save();
        ctx.strokeStyle = line.color;
        ctx.lineWidth = Math.max(1, scope.verticalPixelRatio);
        const dash = 4 * scope.horizontalPixelRatio;
        ctx.setLineDash([dash, dash]);
        ctx.beginPath();
        ctx.moveTo(0, yBitmap + 0.5);
        ctx.lineTo(width, yBitmap + 0.5);
        ctx.stroke();

        // Label
        ctx.setLineDash([]);
        const fontSize = Math.round(10 * scope.verticalPixelRatio);
        ctx.font = `${fontSize}px sans-serif`;
        const text = `${line.label} ${line.price.toFixed(1)}`;
        const tm = ctx.measureText(text);
        const pad = 4 * scope.horizontalPixelRatio;
        const lx = 6 * scope.horizontalPixelRatio;
        const ly = yBitmap - fontSize - 2 * scope.verticalPixelRatio;

        ctx.fillStyle = line.color;
        ctx.globalAlpha = 0.85;
        ctx.beginPath();
        ctx.roundRect(lx, ly, tm.width + pad * 2, fontSize + pad, 3 * scope.horizontalPixelRatio);
        ctx.fill();

        ctx.globalAlpha = 1;
        ctx.fillStyle = "#ffffff";
        ctx.textBaseline = "top";
        ctx.fillText(text, lx + pad, ly + pad / 2);
        ctx.restore();
      }
    });
  }
}

class SRPaneView implements IPrimitivePaneView {
  private _lines: LevelLine[] = [];
  private _source: SupportResistance;

  constructor(source: SupportResistance) {
    this._source = source;
  }

  update(): void {
    const series = this._source.series;
    if (!series) {
      this._lines = [];
      return;
    }
    this._lines = Object.entries(this._source.levels).map(([label, price]) => ({
      price,
      label,
      color: LEVEL_COLORS[label] ?? DEFAULT_COLOR,
      y: series.priceToCoordinate(price),
    }));
  }

  renderer(): SRPaneRenderer {
    return new SRPaneRenderer(this._lines);
  }
}

export class SupportResistance implements ISeriesPrimitive<Time> {
  levels: Record<string, number> = {};
  series: ISeriesApi<keyof SeriesOptionsMap> | null = null;
  private _view: SRPaneView;
  private _requestUpdate?: () => void;

  constructor() {
    this._view = new SRPaneView(this);
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

  setLevels(levels: Record<string, number>): void {
    this.levels = levels;
    this._requestUpdate?.();
  }
}
