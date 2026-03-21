/**
 * StateMarkers — Series Primitive
 * Draws state event labels (SC, AR, Spring, JOC, etc.) as text markers on chart.
 */

import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
} from "lightweight-charts";
import type { WyckoffPhase } from "../types/api";

const STATE_COLORS: Record<string, string> = {
  PS: "#8b949e",
  SC: "#3fb950",
  AR: "#f85149",
  ST: "#58a6ff",
  SPRING: "#39d2c0",
  TEST: "#d29922",
  SOS: "#3fb950",
  LPS: "#58a6ff",
  BU: "#d29922",
  JOC: "#bc8cff",
  LPSY: "#f85149",
  UT: "#f85149",
  UTAD: "#f85149",
  SOW: "#f85149",
};

class StateMarkerRenderer implements IPrimitivePaneRenderer {
  constructor(
    private _state: string,
    private _phase: WyckoffPhase,
    private _color: string,
  ) {}

  draw(target: CanvasRenderingTarget2D): void {
    // Draw current state label in top-right corner
    target.useMediaCoordinateSpace((scope) => {
      const ctx = scope.context;
      const { width } = scope.mediaSize;

      if (!this._state) return;

      const text = `${this._state} [${this._phase}]`;
      ctx.font = "bold 13px JetBrains Mono, monospace";
      const tm = ctx.measureText(text);
      const pad = 6;
      const x = width - tm.width - pad * 2 - 10;
      const y = 10;

      // Background pill
      ctx.fillStyle = "rgba(22,27,34,0.9)";
      ctx.beginPath();
      ctx.roundRect(x, y, tm.width + pad * 2, 22, 4);
      ctx.fill();

      // Border
      ctx.strokeStyle = this._color;
      ctx.lineWidth = 1;
      ctx.stroke();

      // Text
      ctx.fillStyle = this._color;
      ctx.textBaseline = "middle";
      ctx.fillText(text, x + pad, y + 11);
    });
  }
}

class StateMarkerPaneView implements IPrimitivePaneView {
  private _state = "";
  private _phase: WyckoffPhase = "IDLE";
  private _color = "#8b949e";

  setData(state: string, phase: WyckoffPhase): void {
    this._state = state;
    this._phase = phase;
    // Pick color from state abbreviation
    const abbrev = state.toUpperCase().replace(/[^A-Z]/g, "");
    this._color = STATE_COLORS[abbrev] ?? "#8b949e";
  }

  renderer(): StateMarkerRenderer {
    return new StateMarkerRenderer(this._state, this._phase, this._color);
  }
}

export class StateMarkers implements ISeriesPrimitive<Time> {
  private _view = new StateMarkerPaneView();
  private _requestUpdate?: () => void;

  attached({ requestUpdate }: SeriesAttachedParameter<Time>): void {
    this._requestUpdate = requestUpdate;
  }

  detached(): void {
    this._requestUpdate = undefined;
  }

  updateAllViews(): void {
    // View data is set externally via setState
  }

  paneViews() {
    return [this._view];
  }

  setState(state: string, phase: WyckoffPhase): void {
    this._view.setData(state, phase);
    this._requestUpdate?.();
  }
}
