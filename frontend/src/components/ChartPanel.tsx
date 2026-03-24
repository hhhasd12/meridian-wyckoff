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
    <div className="h-full w-full overflow-hidden">
      <div
        ref={containerRef}
        className="h-full w-full overflow-hidden"
      />
    </div>
  );
}
