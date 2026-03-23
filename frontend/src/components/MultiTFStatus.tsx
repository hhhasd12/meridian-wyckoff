/** MultiTFStatus — 多时间框架威科夫状态对比 */

import { useQuery } from "@tanstack/react-query";
import { fetchSnapshot } from "../core/api";

const DIRECTION_MAP: Record<string, string> = {
  ACCUMULATION: "吸筹",
  DISTRIBUTION: "派发",
  TRENDING: "趋势",
  IDLE: "空闲",
};

interface TFState {
  current_state: string;
  direction: string | null;
  confidence: number;
}

export default function MultiTFStatus() {
  const { data: snapshot } = useQuery({
    queryKey: ["snapshot"],
    queryFn: fetchSnapshot,
    staleTime: 30_000,
  });

  const engineData = snapshot?.wyckoff_engine as Record<string, unknown> | null;
  const stateMachines = (engineData?.state_machines ?? {}) as Record<
    string,
    TFState
  >;

  const tfEntries = Object.entries(stateMachines);

  if (tfEntries.length === 0) {
    return (
      <div className="text-text-muted text-xs italic">
        等待多TF数据...
      </div>
    );
  }

  return (
    <div>
      <div className="text-xs text-text-secondary mb-1.5">
        多周期状态对比
      </div>
      <div className="space-y-1">
        {tfEntries.map(([tf, state]) => (
          <div
            key={tf}
            className="flex items-center gap-2 text-sm p-1.5 rounded bg-panel-bg"
          >
            <span className="font-mono text-accent-blue w-8 shrink-0 font-bold text-xs">
              {tf}
            </span>
            <span className="font-mono text-text-primary flex-1 truncate text-xs">
              {state.current_state}
            </span>
            <span className="text-text-muted text-xs shrink-0">
              {DIRECTION_MAP[state.direction ?? ""] ?? state.direction ?? "—"}
            </span>
            <span className="font-mono text-accent-cyan text-xs w-8 text-right shrink-0">
              {((state.confidence ?? 0) * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
