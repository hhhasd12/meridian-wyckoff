/** ChartPanel — Main chart container with KLineChart + Wyckoff overlays */

import { useRef } from "react";
import { useChart } from "../hooks/useChart";
import { useOverlays } from "../hooks/useOverlays";

export default function ChartPanel() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { getRefs } = useChart(containerRef);
  const refs = getRefs();

  useOverlays(refs.chart);

  return (
    <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
      <div
        ref={containerRef}
        className="flex-1 min-h-0"
      />
    </div>
  );
}
