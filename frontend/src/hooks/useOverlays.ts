/** useOverlays — KLineChart v10 custom overlay registration + lifecycle */

import { useEffect, useRef } from "react";
import { registerOverlay } from "klinecharts";
import type { Chart } from "klinecharts";
import { useStore } from "../core/store";

// Track whether overlays have been registered (module-level, once per app)
let overlaysRegistered = false;

/**
 * Register 4 custom overlay templates (idempotent).
 * totalStep: 0 = non-interactive (programmatically placed).
 * Rendering logic is skeleton — will be fleshed out in Wave 2.
 */
function ensureOverlaysRegistered(): void {
  if (overlaysRegistered) return;
  overlaysRegistered = true;

  // 1. Wyckoff Phase Background — colored backdrop per phase
  registerOverlay({
    name: "wyckoffPhaseBg",
    totalStep: 0,
    createPointFigures: () => {
      // Wave 2: draw colored rect behind candles based on phase
      return [];
    },
  });

  // 2. Support / Resistance lines
  registerOverlay({
    name: "supportResistance",
    totalStep: 0,
    createPointFigures: () => {
      // Wave 2: draw horizontal lines at critical_levels
      return [];
    },
  });

  // 3. FVG (Fair Value Gap) zones
  registerOverlay({
    name: "fvgZone",
    totalStep: 0,
    createPointFigures: () => {
      // Wave 2: draw semi-transparent rectangles for FVG gaps
      return [];
    },
  });

  // 4. State markers (wyckoff event labels)
  registerOverlay({
    name: "stateMarker",
    totalStep: 0,
    createPointFigures: () => {
      // Wave 2: draw text labels / icons at state change points
      return [];
    },
  });
}

export function useOverlays(chart: Chart | null) {
  const wyckoff = useStore((s) => s.wyckoffState);
  const overlayIdsRef = useRef<string[]>([]);

  // Register overlay templates on first mount
  useEffect(() => {
    ensureOverlaysRegistered();
  }, []);

  // Create overlay instances when chart is ready
  useEffect(() => {
    if (!chart) return;

    // Create the 4 overlay instances
    const ids: string[] = [];

    const bgId = chart.createOverlay({
      name: "wyckoffPhaseBg",
      lock: true,
      visible: true,
    });
    if (bgId && typeof bgId === "string") ids.push(bgId);

    const srId = chart.createOverlay({
      name: "supportResistance",
      lock: true,
      visible: true,
    });
    if (srId && typeof srId === "string") ids.push(srId);

    const fvgId = chart.createOverlay({
      name: "fvgZone",
      lock: true,
      visible: true,
    });
    if (fvgId && typeof fvgId === "string") ids.push(fvgId);

    const markerId = chart.createOverlay({
      name: "stateMarker",
      lock: true,
      visible: true,
    });
    if (markerId && typeof markerId === "string") ids.push(markerId);

    overlayIdsRef.current = ids;

    return () => {
      // Clean up overlays
      try {
        for (const id of overlayIdsRef.current) {
          chart.removeOverlay({ id });
        }
      } catch {
        // chart already disposed
      }
      overlayIdsRef.current = [];
    };
  }, [chart]);

  // Update overlay data when wyckoff state changes
  useEffect(() => {
    if (!chart || !wyckoff) return;

    // Wave 2: pass data to overlays via overrideOverlay extendData
    try {
      chart.overrideOverlay({
        name: "wyckoffPhaseBg",
        extendData: { phase: wyckoff.phase ?? "IDLE" },
      });
      chart.overrideOverlay({
        name: "supportResistance",
        extendData: { levels: wyckoff.critical_levels ?? {} },
      });
      chart.overrideOverlay({
        name: "stateMarker",
        extendData: {
          state: wyckoff.current_state ?? "",
          phase: wyckoff.phase ?? "IDLE",
        },
      });
    } catch {
      // chart disposed
    }
  }, [chart, wyckoff]);
}
