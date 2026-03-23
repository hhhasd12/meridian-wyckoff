/**
 * TradeMarkers — Series Primitive
 * Draws trade entry/exit markers on the equity chart.
 * Entry: triangle (up for LONG, down for SHORT)
 * Exit: x marker (green if profit, red if loss)
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

export interface TradeMarkerData {
  entryTime: Time;
  exitTime: Time;
  entryPrice: number;
  exitPrice: number;
  side: "LONG" | "SHORT";
  pnl: number;
  entryState: string;
}

interface ResolvedMarker {
  x: Coordinate | null;
  y: Coordinate | null;
  type: "entry-long" | "entry-short" | "exit-win" | "exit-loss";
  label: string;
}

class TradeMarkerRenderer implements IPrimitivePaneRenderer {
  constructor(private _markers: ResolvedMarker[]) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;

      for (const m of this._markers) {
        if (m.x === null || m.y === null) continue;

        const x = m.x;
        const y = m.y;
        const size = 5;

        ctx.save();

        if (m.type === "entry-long") {
          // Upward triangle — green
          ctx.fillStyle = "#26A69A";
          ctx.beginPath();
          ctx.moveTo(x, y - size - 2);
          ctx.lineTo(x - size, y + size - 2);
          ctx.lineTo(x + size, y + size - 2);
          ctx.closePath();
          ctx.fill();
        } else if (m.type === "entry-short") {
          // Downward triangle — red
          ctx.fillStyle = "#EF5350";
          ctx.beginPath();
          ctx.moveTo(x, y + size + 2);
          ctx.lineTo(x - size, y - size + 2);
          ctx.lineTo(x + size, y - size + 2);
          ctx.closePath();
          ctx.fill();
        } else {
          // Exit marker — x shape
          const isWin = m.type === "exit-win";
          ctx.strokeStyle = isWin ? "#26A69A" : "#EF5350";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(x - size, y - size);
          ctx.lineTo(x + size, y + size);
          ctx.moveTo(x + size, y - size);
          ctx.lineTo(x - size, y + size);
          ctx.stroke();
        }

        ctx.restore();
      }
    });
  }
}

class TradeMarkerPaneView implements IPrimitivePaneView {
  private _markers: ResolvedMarker[] = [];
  private _source: TradeMarkers;

  constructor(source: TradeMarkers) {
    this._source = source;
  }

  update(): void {
    const { series, chart } = this._source;
    if (!series || !chart) {
      this._markers = [];
      return;
    }

    const timeScale = chart.timeScale();
    const resolved: ResolvedMarker[] = [];

    for (const trade of this._source.trades) {
      // Entry marker
      const entryX = timeScale.timeToCoordinate(trade.entryTime);
      const entryY = series.priceToCoordinate(trade.entryPrice);
      resolved.push({
        x: entryX,
        y: entryY,
        type: trade.side === "LONG" ? "entry-long" : "entry-short",
        label: trade.entryState,
      });

      // Exit marker
      const exitX = timeScale.timeToCoordinate(trade.exitTime);
      const exitY = series.priceToCoordinate(trade.exitPrice);
      resolved.push({
        x: exitX,
        y: exitY,
        type: trade.pnl > 0 ? "exit-win" : "exit-loss",
        label: trade.pnl > 0 ? "WIN" : "LOSS",
      });
    }

    this._markers = resolved;
  }

  renderer(): TradeMarkerRenderer {
    return new TradeMarkerRenderer(this._markers);
  }
}

export class TradeMarkers implements ISeriesPrimitive<Time> {
  trades: TradeMarkerData[] = [];
  series: ISeriesApi<keyof SeriesOptionsMap> | null = null;
  chart: IChartApi | null = null;
  private _view: TradeMarkerPaneView;
  private _requestUpdate?: () => void;

  constructor() {
    this._view = new TradeMarkerPaneView(this);
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

  setTrades(trades: TradeMarkerData[]): void {
    this.trades = trades;
    this._requestUpdate?.();
  }
}
