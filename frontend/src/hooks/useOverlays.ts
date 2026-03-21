/** useOverlays — Manages LWC Wyckoff overlay primitives lifecycle */

import { useEffect, useRef } from "react";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { useStore } from "../core/store";
import { WyckoffPhaseBg } from "../chart-plugins/WyckoffPhaseBg";
import { SupportResistance } from "../chart-plugins/SupportResistance";
import { FvgZones } from "../chart-plugins/FvgZones";
import { StateMarkers } from "../chart-plugins/StateMarkers";

export function useOverlays(
  chart: IChartApi | null,
  series: ISeriesApi<"Candlestick"> | null,
) {
  const wyckoff = useStore((s) => s.wyckoffState);

  const phaseBgRef = useRef<WyckoffPhaseBg | null>(null);
  const srRef = useRef<SupportResistance | null>(null);
  const fvgRef = useRef<FvgZones | null>(null);
  const markersRef = useRef<StateMarkers | null>(null);

  // Attach primitives when chart/series are ready
  useEffect(() => {
    if (!chart || !series) return;

    const phaseBg = new WyckoffPhaseBg();
    const sr = new SupportResistance();
    const fvg = new FvgZones();
    const markers = new StateMarkers();

    // Phase background is a pane primitive (draws behind everything)
    const pane = chart.panes()[0];
    if (pane) {
      pane.attachPrimitive(phaseBg);
    }

    // Others are series primitives
    series.attachPrimitive(sr);
    series.attachPrimitive(fvg);
    series.attachPrimitive(markers);

    phaseBgRef.current = phaseBg;
    srRef.current = sr;
    fvgRef.current = fvg;
    markersRef.current = markers;

    return () => {
      if (pane) {
        pane.detachPrimitive(phaseBg);
      }
      series.detachPrimitive(sr);
      series.detachPrimitive(fvg);
      series.detachPrimitive(markers);

      phaseBgRef.current = null;
      srRef.current = null;
      fvgRef.current = null;
      markersRef.current = null;
    };
  }, [chart, series]);

  // Update overlays when wyckoff state changes
  useEffect(() => {
    if (!wyckoff) return;

    phaseBgRef.current?.setPhase(wyckoff.phase);
    srRef.current?.setLevels(wyckoff.critical_levels);
    markersRef.current?.setState(wyckoff.current_state, wyckoff.phase);
  }, [wyckoff]);
}
