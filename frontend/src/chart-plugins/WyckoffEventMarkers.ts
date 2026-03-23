/**
 * WyckoffEventMarkers — Series Primitive
 * Draws state transition markers (triangles, circles) on bars where state changed.
 * Bullish events: green ▲, Bearish: red ▼, Neutral: gray ●
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

const BULLISH_STATES = new Set([
  "SC", "SPRING", "SOS", "TEST", "JOC", "LPS",
]);
const BEARISH_STATES = new Set([
  "LPSY", "UTAD", "SOW", "UT",
]);

export interface EventMarkerData {
  time: Time;
  price: number;
  state: string;
  direction: "bullish" | "bearish" | "neutral";
}

interface ResolvedEvent {
  x: Coordinate | null;
  y: Coordinate | null;
  state: string;
  direction: "bullish" | "bearish" | "neutral";
}

function classifyState(state: string): "bullish" | "bearish" | "neutral" {
  const abbrev = state.toUpperCase().replace(/[^A-Z]/g, "");
  if (BULLISH_STATES.has(abbrev)) return "bullish";
  if (BEARISH_STATES.has(abbrev)) return "bearish";
  return "neutral";
}

class EventMarkerRenderer implements IPrimitivePaneRenderer {
  constructor(private _events: ResolvedEvent[]) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;

      for (const evt of this._events) {
        if (evt.x === null || evt.y === null) continue;

        const x = evt.x;
        const y = evt.y;
        const size = 5;

        ctx.save();

        if (evt.direction === "bullish") {
          // Green upward triangle ▲
          ctx.fillStyle = "#3fb950";
          ctx.beginPath();
          ctx.moveTo(x, y - size - 4);
          ctx.lineTo(x - size, y + size - 4);
          ctx.lineTo(x + size, y + size - 4);
          ctx.closePath();
          ctx.fill();
          // Label above
          ctx.font = "bold 9px JetBrains Mono, monospace";
          ctx.fillStyle = "#3fb950";
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          ctx.fillText(evt.state, x, y - size - 6);
        } else if (evt.direction === "bearish") {
          // Red downward triangle ▼
          ctx.fillStyle = "#f85149";
          ctx.beginPath();
          ctx.moveTo(x, y + size + 4);
          ctx.lineTo(x - size, y - size + 4);
          ctx.lineTo(x + size, y - size + 4);
          ctx.closePath();
          ctx.fill();
          // Label below
          ctx.font = "bold 9px JetBrains Mono, monospace";
          ctx.fillStyle = "#f85149";
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.fillText(evt.state, x, y + size + 6);
        } else {
          // Gray circle ●
          ctx.fillStyle = "#8b949e";
          ctx.beginPath();
          ctx.arc(x, y - 8, 3, 0, Math.PI * 2);
          ctx.fill();
          // Label above
          ctx.font = "bold 9px JetBrains Mono, monospace";
          ctx.fillStyle = "#8b949e";
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          ctx.fillText(evt.state, x, y - 13);
        }

        ctx.restore();
      }
    });
  }
}

class EventMarkerPaneView implements IPrimitivePaneView {
  private _events: ResolvedEvent[] = [];
  private _source: WyckoffEventMarkers;

  constructor(source: WyckoffEventMarkers) {
    this._source = source;
  }

  update(): void {
    const { series, chart } = this._source;
    if (!series || !chart) {
      this._events = [];
      return;
    }

    const timeScale = chart.timeScale();
    this._events = this._source.markers.map((m) => ({
      x: timeScale.timeToCoordinate(m.time),
      y: series.priceToCoordinate(m.price),
      state: m.state,
      direction: m.direction,
    }));
  }

  renderer(): EventMarkerRenderer {
    return new EventMarkerRenderer(this._events);
  }
}

export class WyckoffEventMarkers implements ISeriesPrimitive<Time> {
  markers: EventMarkerData[] = [];
  series: ISeriesApi<keyof SeriesOptionsMap> | null = null;
  chart: IChartApi | null = null;
  private _view: EventMarkerPaneView;
  private _requestUpdate?: () => void;

  constructor() {
    this._view = new EventMarkerPaneView(this);
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

  setMarkers(markers: EventMarkerData[]): void {
    this.markers = markers;
    this._requestUpdate?.();
  }
}

export { classifyState };
