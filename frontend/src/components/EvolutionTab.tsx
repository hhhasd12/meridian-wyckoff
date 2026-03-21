import { useStore } from "../core/store";
import { Dna, TrendingUp, BarChart3, Target, FlaskConical } from "lucide-react";

export default function EvolutionTab() {
  const evo = useStore((s) => s.evolution);

  if (!evo) {
    return (
      <div className="text-text-muted text-xs italic p-2">
        Evolution data not available
      </div>
    );
  }

  const metrics = [
    {
      icon: Dna,
      label: "Generation",
      value: evo.generation?.toString() ?? "—",
      color: "text-accent-purple",
    },
    {
      icon: Target,
      label: "Fitness",
      value: evo.fitness?.toFixed(3) ?? "—",
      color: "text-accent-cyan",
    },
    {
      icon: TrendingUp,
      label: "Sharpe Ratio",
      value: evo.sharpe_ratio?.toFixed(2) ?? "—",
      color: "text-accent-green",
    },
    {
      icon: BarChart3,
      label: "OOS Degradation",
      value: evo.degradation_rate?.toFixed(2) ?? "—",
      color:
        (evo.degradation_rate ?? 0) > 0.5
          ? "text-accent-red"
          : "text-accent-green",
    },
    {
      icon: FlaskConical,
      label: "PBO",
      value: evo.pbo?.toFixed(2) ?? "—",
      color:
        (evo.pbo ?? 0) > 0.5 ? "text-accent-red" : "text-accent-green",
    },
    {
      icon: BarChart3,
      label: "Monte Carlo p",
      value: evo.monte_carlo_p?.toFixed(3) ?? "—",
      color:
        (evo.monte_carlo_p ?? 1) < 0.05
          ? "text-accent-green"
          : "text-accent-yellow",
    },
  ];

  return (
    <div className="grid grid-cols-3 gap-3 p-2">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="flex items-center gap-2 p-2 rounded bg-panel-bg"
        >
          <m.icon size={16} className={m.color} />
          <div>
            <div className="text-text-muted text-[10px]">{m.label}</div>
            <div className={`font-mono text-sm font-medium ${m.color}`}>
              {m.value}
            </div>
          </div>
        </div>
      ))}

      {/* Running status */}
      <div className="col-span-3 flex items-center gap-2 text-xs">
        <div
          className={`w-2 h-2 rounded-full ${
            evo.is_running ? "bg-accent-green animate-pulse" : "bg-text-muted"
          }`}
        />
        <span className="text-text-secondary">
          {evo.is_running ? "Evolution running" : "Evolution idle"}
        </span>
      </div>
    </div>
  );
}
