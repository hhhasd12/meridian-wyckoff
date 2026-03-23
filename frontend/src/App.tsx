/** App — Sidebar navigation + page routing with WS connection + REST data fetching */

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import Sidebar from "./components/Sidebar";
import TradingPage from "./components/TradingPage";
import EvolutionPage from "./components/EvolutionPage";
import AnalysisPage from "./components/AnalysisPage";
import { fetchCandles, fetchSnapshot, fetchEvolutionResults } from "./core/api";
import { WsManager, buildWsUrl } from "./core/ws";
import { useStore } from "./core/store";
import type { WsServerMessage, SignalAlert, LogEntry } from "./types/api";

function App() {
  const activePage = useStore((s) => s.activePage);
  const symbol = useStore((s) => s.symbol);
  const timeframe = useStore((s) => s.timeframe);
  const setCandles = useStore((s) => s.setCandles);
  const setWyckoffState = useStore((s) => s.setWyckoffState);
  const setPositions = useStore((s) => s.setPositions);
  const setEvolution = useStore((s) => s.setEvolution);
  const setEvolutionCycles = useStore((s) => s.setEvolutionCycles);
  const setSystemInfo = useStore((s) => s.setSystemInfo);
  const setWsStatus = useStore((s) => s.setWsStatus);
  const appendCandle = useStore((s) => s.appendCandle);

  const wsRef = useRef<WsManager | null>(null);

  // Fetch initial candles
  useQuery({
    queryKey: ["candles", symbol, timeframe],
    queryFn: () => fetchCandles(symbol, timeframe),
    select: (data) => {
      setCandles(data);
      return data;
    },
    staleTime: 30_000,
  });

  // Fetch system snapshot (polling every 30s)
  useQuery({
    queryKey: ["snapshot"],
    queryFn: fetchSnapshot,
    refetchInterval: 30_000,
    select: (data) => {
      setSystemInfo(data.uptime, data.is_running);
      if (data.wyckoff_engine) setWyckoffState(data.wyckoff_engine);
      if (data.positions) setPositions(data.positions);
      if (data.evolution) {
        const evo = {
          ...data.evolution,
          is_running: data.evolution.status === "running",
        };
        setEvolution(evo);
      }
      return data;
    },
  });

  // Fetch evolution cycle results (polling every 30s, only when on evolution page)
  useQuery({
    queryKey: ["evolution-results"],
    queryFn: fetchEvolutionResults,
    refetchInterval: 30_000,
    enabled: activePage === "evolution",
    select: (data) => {
      setEvolutionCycles(data.cycles);
      return data;
    },
  });

  // WebSocket connection
  useEffect(() => {
    const handleMessage = (msg: WsServerMessage) => {
      switch (msg.type) {
        case "candle_update":
          appendCandle(msg.data);
          break;
        case "wyckoff_state":
          setWyckoffState(msg.data);
          // Extract latest signal for SignalPanel
          if (
            msg.data &&
            typeof msg.data === "object" &&
            "latest_signal" in msg.data &&
            (msg.data as Record<string, unknown>).latest_signal
          ) {
            useStore
              .getState()
              .addSignal(
                (msg.data as Record<string, unknown>).latest_signal as SignalAlert,
              );
          }
          break;
        case "position_update":
          setPositions(msg.data);
          break;
        case "evolution_progress":
          setEvolution({
            ...msg.data,
            is_running: (msg.data as Record<string, unknown>).status === "running",
          });
          break;
        case "system_status": {
          // Extract system info
          const statusData = msg.data as Record<string, unknown>;
          if (statusData.uptime !== undefined) {
            setSystemInfo(
              statusData.uptime as number,
              (statusData.is_running as boolean) ?? false,
            );
          }
          // Extract recent logs for LogsTab
          if (Array.isArray(statusData.recent_logs)) {
            for (const log of statusData.recent_logs as LogEntry[]) {
              useStore.getState().addLog(log);
            }
          }
          break;
        }
        case "pong":
          // heartbeat response
          break;
      }
    };

    const ws = new WsManager(
      buildWsUrl(),
      ["candles", "wyckoff", "positions", "evolution", "system_status"],
      handleMessage,
      setWsStatus,
    );
    ws.connect();
    wsRef.current = ws;

    return () => {
      ws.disconnect();
      wsRef.current = null;
    };
  }, [
    appendCandle,
    setWyckoffState,
    setPositions,
    setEvolution,
    setSystemInfo,
    setWsStatus,
  ]);

  return (
    <div className="h-full flex bg-panel-bg">
      {/* Sidebar navigation */}
      <Sidebar />

      {/* Page content */}
      {activePage === "trading" ? (
        <TradingPage />
      ) : activePage === "evolution" ? (
        <EvolutionPage />
      ) : (
        <AnalysisPage />
      )}
    </div>
  );
}

export default App;
