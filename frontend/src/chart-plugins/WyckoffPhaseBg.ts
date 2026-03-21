/**
 * WyckoffPhaseBg — Pane Primitive
 * Draws phase background color across the entire chart pane.
 * Phase A=gray, B=yellow, C=green, D=blue, E=purple
 */

import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  IPanePrimitive,
  PaneAttachedParameter,
  Time,
} from "lightweight-charts";
import type { WyckoffPhase } from "../types/api";

const PHASE_BG_COLORS: Record<WyckoffPhase, string> = {
  A: "rgba(139,148,158,0.06)",
  B: "rgba(210,153,34,0.06)",
  C: "rgba(63,185,80,0.06)",
  D: "rgba(88,166,255,0.06)",
  E: "rgba(188,140,255,0.06)",
  IDLE: "rgba(0,0,0,0)",
};

interface PhaseBgRenderer {
  draw(target: CanvasRenderingTarget2D): void;
}

class PhaseBgPaneRenderer implements PhaseBgRenderer {
  constructor(private _color: string) {}

  draw(target: CanvasRenderingTarget2D): void {
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      ctx.fillStyle = this._color;
      ctx.fillRect(0, 0, scope.bitmapSize.width, scope.bitmapSize.height);
    });
  }
}

class PhaseBgPaneView {
  private _color: string = "rgba(0,0,0,0)";

  setColor(color: string): void {
    this._color = color;
  }

  zOrder(): "bottom" {
    return "bottom";
  }

  renderer(): PhaseBgPaneRenderer {
    return new PhaseBgPaneRenderer(this._color);
  }
}

export class WyckoffPhaseBg implements IPanePrimitive<Time> {
  private _view = new PhaseBgPaneView();
  private _requestUpdate?: () => void;
  private _phase: WyckoffPhase = "IDLE";

  attached({ requestUpdate }: PaneAttachedParameter<Time>): void {
    this._requestUpdate = requestUpdate;
  }

  detached(): void {
    this._requestUpdate = undefined;
  }

  updateAllViews(): void {
    this._view.setColor(PHASE_BG_COLORS[this._phase]);
  }

  paneViews() {
    return [this._view];
  }

  setPhase(phase: WyckoffPhase): void {
    this._phase = phase;
    this._requestUpdate?.();
  }
}
