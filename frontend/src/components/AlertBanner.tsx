/** AlertBanner — 顶部错误/告警横幅 */

import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchSnapshot } from "../core/api";

export default function AlertBanner() {
  const [dismissed, setDismissed] = useState(false);

  const { data: snapshot } = useQuery({
    queryKey: ["snapshot"],
    queryFn: fetchSnapshot,
    staleTime: 30_000,
  });

  const orchestrator = snapshot?.orchestrator;
  const circuitTripped =
    orchestrator?.circuit_breaker_tripped ||
    orchestrator?.circuit_breaker?.triggered;
  const lastError = orchestrator?.last_error;

  // Only show for circuit breaker trips
  if (!circuitTripped || dismissed) return null;

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-accent-red/10 border-b border-accent-red/20 animate-fade-in">
      <AlertTriangle size={14} className="text-accent-red shrink-0" />
      <div className="flex-1 text-sm">
        <span className="text-accent-red font-medium">熔断器已触发</span>
        {lastError && (
          <span className="text-accent-red/70 ml-2">{lastError}</span>
        )}
      </div>
      <button
        onClick={() => setDismissed(true)}
        className="text-accent-red/50 hover:text-accent-red transition-colors"
      >
        <X size={14} />
      </button>
    </div>
  );
}
