/** TradingPage -- 实盘监控页面 */

import Header from "./Header";
import AlertBanner from "./AlertBanner";
import WyckoffPanel from "./WyckoffPanel";
import ChartPanel from "./ChartPanel";
import SignalPanel from "./SignalPanel";
import PrinciplesPanel from "./PrinciplesPanel";
import BottomTabs from "./BottomTabs";
import PositionsTab from "./PositionsTab";
import TradesTab from "./TradesTab";
import DecisionHistoryTab from "./DecisionHistoryTab";
import LogsTab from "./LogsTab";

export default function TradingPage() {
  const bottomTabs = [
    { id: "positions", label: "持仓", content: <PositionsTab /> },
    { id: "trades", label: "交易记录", content: <TradesTab /> },
    { id: "decisions", label: "决策历史", content: <DecisionHistoryTab /> },
    { id: "logs", label: "日志", content: <LogsTab /> },
  ];

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Alert banner (circuit breaker) */}
      <AlertBanner />

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

        {/* Right panel: Decision info + V4 Principles */}
        <div className="flex flex-col min-h-0">
          <SignalPanel />
          <PrinciplesPanel />
        </div>
      </div>
    </div>
  );
}
