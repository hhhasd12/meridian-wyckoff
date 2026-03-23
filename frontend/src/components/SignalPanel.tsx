import {
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Shield,
  AlertTriangle,
  Plug,
  ChevronDown,
} from "lucide-react";
import { useStore } from "../core/store";
import { useQuery } from "@tanstack/react-query";
import { fetchSnapshot } from "../core/api";
import { useState } from "react";

export default function SignalPanel() {
  const rightOpen = useStore((s) => s.rightPanelOpen);
  const toggle = useStore((s) => s.toggleRightPanel);
  const signals = useStore((s) => s.signals);
  const positions = useStore((s) => s.positions);
  const [pluginsExpanded, setPluginsExpanded] = useState(false);

  // Get snapshot for orchestrator + plugins
  const { data: snapshot } = useQuery({
    queryKey: ["snapshot"],
    queryFn: fetchSnapshot,
    staleTime: 30_000,
  });

  const orchestrator = snapshot?.orchestrator;
  const plugins = snapshot?.plugins ?? [];
  const activePlugins = plugins.filter((p) => p.state === "ACTIVE").length;
  const totalPlugins = plugins.length;
  const circuitTripped =
    orchestrator?.circuit_breaker_tripped ||
    orchestrator?.circuit_breaker?.triggered;

  if (!rightOpen) {
    return (
      <button
        onClick={toggle}
        className="flex items-center justify-center w-6 bg-panel-surface
          border-l border-panel-border hover:bg-panel-hover/30 transition-colors"
        title="展开决策面板"
      >
        <ChevronLeft size={14} className="text-text-muted" />
      </button>
    );
  }

  return (
    <aside className="w-60 flex-shrink-0 bg-panel-surface border-l border-panel-border flex flex-col overflow-hidden">
      {/* Header */}
      <div className="panel-header">
        <span>决策信息</span>
        <button onClick={toggle} className="hover:text-text-primary">
          <ChevronRight size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {/* Orchestrator status card */}
        <div className="p-3 border-b border-panel-border">
          <div className="text-xs text-text-secondary mb-2 font-medium uppercase tracking-widest">
            编排器状态
          </div>
          <div className="space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-text-secondary">运行模式</span>
              <span
                className={`badge text-xs ${
                  orchestrator?.mode === "live"
                    ? "badge-red"
                    : "badge-yellow"
                }`}
              >
                {orchestrator?.mode === "live" ? "实盘" : "模拟盘"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">熔断器</span>
              <span
                className={`font-mono ${
                  circuitTripped
                    ? "text-accent-red"
                    : "text-accent-green"
                }`}
              >
                {circuitTripped ? "已触发" : "正常"}
              </span>
            </div>
            {orchestrator?.decision_count !== undefined && (
              <div className="flex justify-between">
                <span className="text-text-secondary">决策次数</span>
                <span className="font-mono text-text-primary">
                  {orchestrator.decision_count}
                </span>
              </div>
            )}
            {orchestrator?.signal_count !== undefined && (
              <div className="flex justify-between">
                <span className="text-text-secondary">信号次数</span>
                <span className="font-mono text-text-primary">
                  {orchestrator.signal_count}
                </span>
              </div>
            )}
            {orchestrator?.last_error && (
              <div className="mt-1 p-1.5 rounded bg-accent-red/10 border border-accent-red/20">
                <div className="flex items-center gap-1 text-accent-red text-xs mb-0.5">
                  <AlertTriangle size={10} />
                  <span>最近错误</span>
                </div>
                <div className="text-xs text-accent-red/80 truncate">
                  {orchestrator.last_error}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Signals */}
        <div className="p-3 border-b border-panel-border">
          <div className="text-xs text-text-secondary mb-2 font-medium uppercase tracking-widest">
            最近信号
          </div>
          <div className="space-y-1.5">
            {signals.length > 0 ? (
              signals.slice(0, 5).map((sig) => (
                <div
                  key={sig.id}
                  className="flex items-start gap-2 text-sm p-1.5 rounded bg-panel-bg"
                >
                  {(sig.signal ?? "").includes("buy") ? (
                    <TrendingUp
                      size={14}
                      className="text-accent-green flex-shrink-0 mt-0.5"
                    />
                  ) : (sig.signal ?? "").includes("sell") ? (
                    <TrendingDown
                      size={14}
                      className="text-accent-red flex-shrink-0 mt-0.5"
                    />
                  ) : (
                    <Shield
                      size={14}
                      className="text-text-muted flex-shrink-0 mt-0.5"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between">
                      <span
                        className={`font-medium uppercase ${
                          (sig.signal ?? "").includes("buy")
                            ? "text-accent-green"
                            : (sig.signal ?? "").includes("sell")
                              ? "text-accent-red"
                              : "text-text-secondary"
                        }`}
                      >
                        {(sig.signal ?? "neutral").replace("_", " ")}
                      </span>
                      <span className="text-text-muted font-mono">
                        {((sig.confidence ?? 0) * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="text-text-muted truncate">
                      阶段 {sig.phase} · {sig.state}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-text-muted text-sm italic">
                等待信号...
              </div>
            )}
          </div>
        </div>

        {/* Positions */}
        <div className="p-3 border-b border-panel-border">
          <div className="text-xs text-text-secondary mb-2 font-medium uppercase tracking-widest">
            当前持仓
          </div>
          <div className="space-y-2">
            {positions.length > 0 ? (
              positions.map((pos, i) => (
                <div
                  key={i}
                  className="p-2 rounded bg-panel-bg text-sm space-y-1"
                >
                  <div className="flex justify-between">
                    <span className="font-medium text-text-primary">
                      {pos.symbol}
                    </span>
                    <span
                      className={`badge text-xs ${
                        pos.side === "LONG" ? "badge-green" : "badge-red"
                      }`}
                    >
                      {pos.side === "LONG" ? "做多" : pos.side === "SHORT" ? "做空" : "—"}
                    </span>
                  </div>
                  <div className="flex justify-between text-text-secondary">
                    <span>入场价</span>
                    <span className="font-mono text-text-primary">
                      {pos.entry_price?.toFixed(2) ?? "—"}
                    </span>
                  </div>
                  {pos.pnl_pct !== undefined && (
                    <div className="flex justify-between text-text-secondary">
                      <span>盈亏</span>
                      <span
                        className={`font-mono ${
                          pos.pnl_pct >= 0
                            ? "text-accent-green"
                            : "text-accent-red"
                        }`}
                      >
                        {pos.pnl_pct >= 0 ? "+" : ""}
                        {(pos.pnl_pct ?? 0).toFixed(2)}%
                      </span>
                    </div>
                  )}
                  {pos.stop_loss && (
                    <div className="flex justify-between text-text-secondary">
                      <span>止损</span>
                      <span className="font-mono text-accent-red">
                        {(pos.stop_loss ?? 0).toFixed(2)}
                      </span>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="text-text-muted text-sm italic">
                暂无持仓
              </div>
            )}
          </div>
        </div>

        {/* Plugin health summary (collapsible) */}
        <div className="p-3">
          <button
            onClick={() => setPluginsExpanded(!pluginsExpanded)}
            className="w-full flex items-center justify-between text-xs text-text-secondary font-medium uppercase tracking-widest mb-2 hover:text-text-primary transition-colors"
          >
            <span>插件状态</span>
            <ChevronDown
              size={12}
              className={`transition-transform duration-200 ${
                pluginsExpanded ? "rotate-180" : ""
              }`}
            />
          </button>
          <div className="flex items-center gap-2 text-sm">
            <Plug size={12} className="text-text-muted" />
            <span className="text-text-primary font-mono">
              {activePlugins}/{totalPlugins}
            </span>
            <span className="text-text-secondary">活跃</span>
            {activePlugins < totalPlugins && (
              <span className="text-accent-red text-xs">
                ({totalPlugins - activePlugins} 异常)
              </span>
            )}
          </div>
          {pluginsExpanded && plugins.length > 0 && (
            <div className="mt-2 space-y-0.5 animate-fade-in">
              {plugins.map((p) => (
                <div
                  key={p.name}
                  className={`flex items-center justify-between text-xs px-1 py-0.5 rounded ${
                    p.state !== "ACTIVE"
                      ? "bg-accent-red/10 text-accent-red"
                      : "text-text-secondary"
                  }`}
                >
                  <span className="truncate mr-1">{p.display_name}</span>
                  <div className="flex items-center gap-1 shrink-0">
                    <span className="font-mono text-text-muted">
                      v{p.version}
                    </span>
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${
                        p.state === "ACTIVE"
                          ? "bg-accent-green"
                          : "bg-accent-red"
                      }`}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
