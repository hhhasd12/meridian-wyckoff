import { useStore } from "../core/store";

export default function PositionsTab() {
  const positions = useStore((s) => s.positions);

  if (positions.length === 0) {
    return (
      <div className="text-text-muted text-sm italic p-2">
        暂无持仓
      </div>
    );
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>交易对</th>
          <th>方向</th>
          <th>入场价</th>
          <th>现价</th>
          <th>仓位</th>
          <th>盈亏</th>
          <th>盈亏%</th>
          <th>止损</th>
          <th>止盈</th>
          <th>杠杆</th>
          <th>状态</th>
          <th>风报比</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((pos, i) => (
          <tr key={i}>
            <td className="text-text-primary font-medium">{pos.symbol}</td>
            <td>
              <span
                className={`badge text-xs ${
                  pos.side === "LONG" ? "badge-green" : "badge-red"
                }`}
              >
                {pos.side === "LONG" ? "做多" : pos.side === "SHORT" ? "做空" : "—"}
              </span>
            </td>
            <td>{pos.entry_price?.toFixed(2) ?? "—"}</td>
            <td>{pos.current_price?.toFixed(2) ?? "—"}</td>
            <td>{pos.size?.toFixed(4) ?? "—"}</td>
            <td
              className={
                (pos.pnl ?? 0) >= 0 ? "text-accent-green" : "text-accent-red"
              }
            >
              {pos.pnl?.toFixed(2) ?? "—"}
            </td>
            <td
              className={
                (pos.pnl_pct ?? 0) >= 0
                  ? "text-accent-green"
                  : "text-accent-red"
              }
            >
              {pos.pnl_pct !== undefined
                ? `${pos.pnl_pct >= 0 ? "+" : ""}${(pos.pnl_pct ?? 0).toFixed(2)}%`
                : "—"}
            </td>
            <td className="text-accent-red">
              {pos.stop_loss?.toFixed(2) ?? "—"}
            </td>
            <td className="text-accent-green">
              {pos.take_profit?.toFixed(2) ?? "—"}
            </td>
            <td>{pos.leverage ?? "—"}x</td>
            <td className="text-text-secondary">
              {pos.wyckoff_state ?? "—"}
            </td>
            <td className="text-accent-cyan">
              {pos.risk_reward_ratio?.toFixed(2) ?? "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
