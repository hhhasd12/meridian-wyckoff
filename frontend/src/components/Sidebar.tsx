import {
  BarChart3,
  Dna,
  Eye,
  Wifi,
  WifiOff,
  Clock,
  Plug,
  AlertTriangle,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { useStore } from "../core/store";
import { useQuery } from "@tanstack/react-query";
import { fetchSnapshot } from "../core/api";
import { useState } from "react";

const NAV_ITEMS = [
  { id: "trading" as const, label: "实盘监控", icon: BarChart3 },
  { id: "evolution" as const, label: "进化优化", icon: Dna },
  { id: "analysis" as const, label: "状态分析", icon: Eye },
];

export default function Sidebar() {
  const activePage = useStore((s) => s.activePage);
  const setActivePage = useStore((s) => s.setActivePage);
  const wsStatus = useStore((s) => s.wsStatus);
  const isRunning = useStore((s) => s.isRunning);
  const uptime = useStore((s) => s.uptime);
  const symbol = useStore((s) => s.symbol);
  const timeframe = useStore((s) => s.timeframe);
  const [errorExpanded, setErrorExpanded] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  const { data: snapshot } = useQuery({
    queryKey: ["snapshot"],
    queryFn: fetchSnapshot,
    staleTime: 30_000,
  });

  const plugins = snapshot?.plugins ?? [];
  const activePlugins = plugins.filter((p) => p.state === "ACTIVE").length;
  const totalPlugins = plugins.length;
  const lastError = snapshot?.orchestrator?.last_error;
  const hasError = !!lastError;

  const formatUptime = (seconds: number): string => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return `${h}h ${m}m`;
  };

  return (
    <aside
      className={`flex-shrink-0 bg-panel-surface border-r border-panel-border flex flex-col h-full transition-all duration-300 ${
        collapsed ? "w-[56px]" : "w-[140px]"
      }`}
    >
      {/* Logo / Title */}
      <div className="px-3 py-3 border-b border-panel-border">
        {collapsed ? (
          <div className="text-[13px] font-bold text-text-primary text-center">W</div>
        ) : (
          <>
            <div className="text-[13px] font-bold text-text-primary tracking-wide">
              威科夫引擎
            </div>
            <div className="text-[11px] text-text-muted mt-0.5">
              Wyckoff Engine
            </div>
          </>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-2">
        {NAV_ITEMS.map((item) => {
          const isActive = activePage === item.id;
          const Icon = item.icon;
          return (
            <button
              key={item.id}
              onClick={() => setActivePage(item.id)}
              title={collapsed ? item.label : undefined}
              className={`w-full flex items-center ${collapsed ? "justify-center" : ""} gap-2.5 px-3 py-2.5 text-sm transition-all duration-200 relative ${
                isActive
                  ? "text-accent-blue bg-accent-blue/8"
                  : "text-text-secondary hover:text-text-primary hover:bg-panel-hover/30"
              }`}
            >
              {isActive && (
                <div className="absolute left-0 top-1 bottom-1 w-[3px] bg-accent-blue rounded-r" />
              )}
              <Icon size={16} />
              {!collapsed && <span className="font-medium">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Bottom status area */}
      <div
        className={`border-t px-3 py-2.5 space-y-1.5 transition-colors ${
          hasError
            ? "border-accent-red/50 bg-accent-red/5"
            : "border-panel-border"
        }`}
      >
        {collapsed ? (
          /* Collapsed: minimal status */
          <div className="flex flex-col items-center gap-2">
            <div className="relative">
              <div
                className={`w-2 h-2 rounded-full ${
                  isRunning ? "bg-accent-green" : "bg-text-muted"
                }`}
              />
              {isRunning && (
                <div className="absolute inset-0 w-2 h-2 rounded-full bg-accent-green animate-ping opacity-75" />
              )}
            </div>
            {wsStatus === "connected" ? (
              <Wifi size={10} className="text-accent-green" />
            ) : (
              <WifiOff size={10} className="text-accent-red" />
            )}
            <span className="text-[11px] font-mono text-text-muted">
              {activePlugins}/{totalPlugins}
            </span>
          </div>
        ) : (
          /* Expanded: full status */
          <>
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono text-text-primary font-medium">
                {symbol}
              </span>
              <span className="text-xs font-mono text-text-muted">
                {timeframe}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="relative">
                <div
                  className={`w-1.5 h-1.5 rounded-full ${
                    isRunning ? "bg-accent-green" : "bg-text-muted"
                  }`}
                />
                {isRunning && (
                  <div className="absolute inset-0 w-1.5 h-1.5 rounded-full bg-accent-green animate-ping opacity-75" />
                )}
              </div>
              <span className="text-xs text-text-secondary">
                {isRunning ? "运行中" : "已停止"}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              {wsStatus === "connected" ? (
                <Wifi size={10} className="text-accent-green" />
              ) : wsStatus === "connecting" ? (
                <Wifi size={10} className="text-accent-yellow" />
              ) : (
                <WifiOff size={10} className="text-accent-red" />
              )}
              <span className="text-xs text-text-secondary">
                {wsStatus === "connected"
                  ? "已连接"
                  : wsStatus === "connecting"
                    ? "连接中"
                    : "已断开"}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <Clock size={10} className="text-text-muted" />
              <span className="text-xs text-text-muted font-mono">
                {formatUptime(uptime)}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <Plug size={10} className="text-text-muted" />
              <span className="text-xs text-text-secondary">
                <span className="font-mono text-text-primary">
                  {activePlugins}/{totalPlugins}
                </span>
                {" 活跃"}
              </span>
            </div>
            {hasError && (
              <button
                onClick={() => setErrorExpanded(!errorExpanded)}
                className="w-full flex items-center gap-1 text-xs text-accent-red hover:text-accent-red/80 transition-colors"
              >
                <AlertTriangle size={10} />
                <span className="truncate">
                  {errorExpanded ? "收起" : "查看错误"}
                </span>
              </button>
            )}
            {hasError && errorExpanded && (
              <div className="text-[11px] text-accent-red/70 bg-accent-red/10 rounded p-1.5 break-words animate-fade-in">
                {lastError}
              </div>
            )}
          </>
        )}
      </div>

      {/* Collapse toggle button */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center justify-center py-2 border-t border-panel-border text-text-muted hover:text-text-primary hover:bg-panel-hover/30 transition-colors"
      >
        {collapsed ? (
          <PanelLeftOpen size={14} />
        ) : (
          <PanelLeftClose size={14} />
        )}
      </button>
    </aside>
  );
}
