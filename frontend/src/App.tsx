/** App — Three-column layout with WS connection + REST data fetching */

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import Header from "./components/Header";
import WyckoffPanel from "./components/WyckoffPanel";
import ChartPanel from "./components/ChartPanel";
import SignalPanel from "./components/SignalPanel";
import BottomTabs from "./components/BottomTabs";
import PositionsTab from "./components/PositionsTab";
import TradesTab from "./components/TradesTab";
import EvolutionTab from "./components/EvolutionTab";
import AdvisorTab from "./components/AdvisorTab";
import LogsTab from "./components/LogsTab";
import { fetchCandles, fetchSnapshot } from "./core/api";
import { WsManager, buildWsUrl } from "./core/ws";
import { useStore } from "./core/store";
import type { WsServerMessage } from "./types/api";

function App() {
  const symbol = useStore((s) => s.symbol);
  const timeframe = useStore((s) => s.timeframe);
  const setCandles = useStore((s) => s.setCandles);
  const setWyckoffState = useStore((s) => s.setWyckoffState);
  const setPositions = useStore((s) => s.setPositions);
  const setEvolution = useStore((s) => s.setEvolution);
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
      if (data.evolution) setEvolution(data.evolution);
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
          break;
        case "position_update":
          setPositions(msg.data);
          break;
        case "evolution_progress":
          setEvolution(msg.data);
          break;
        case "system_status":
          // system_status data shape is generic
          break;
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
    setWsStatus,
  ]);

  const bottomTabs = [
    { id: "positions", label: "Positions", content: <PositionsTab /> },
    { id: "trades", label: "Trade History", content: <TradesTab /> },
    { id: "evolution", label: "Evolution", content: <EvolutionTab /> },
    { id: "advisor", label: "AI Analysis", content: <AdvisorTab /> },
    { id: "logs", label: "Logs", content: <LogsTab /> },
  ];

  return (
    <div className="h-full flex flex-col bg-panel-bg">
      {/* Top bar */}
      <Header />

      {/* Main content: 3-column layout */}
      <div className="flex-1 flex min-h-0">
        {/* Left panel: Wyckoff state */}
        <WyckoffPanel />

        {/* Center: Chart + Bottom tabs */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Chart area (70% height) */}
          <div className="flex-[7] min-h-0">
            <ChartPanel />
          </div>

          {/* Bottom tabs (30% height) */}
          <div className="flex-[3] min-h-0">
            <BottomTabs tabs={bottomTabs} />
          </div>
        </div>

        {/* Right panel: Signals & Positions */}
        <SignalPanel />
      </div>
    </div>
  );
}

export default App;
