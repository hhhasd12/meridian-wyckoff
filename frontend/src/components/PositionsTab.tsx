import { useStore } from "../core/store";

export default function PositionsTab() {
  const positions = useStore((s) => s.positions);

  if (positions.length === 0) {
    return (
      <div className="text-text-muted text-xs italic p-2">
        No open positions
      </div>
    );
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Side</th>
          <th>Entry</th>
          <th>Current</th>
          <th>Size</th>
          <th>PnL</th>
          <th>PnL%</th>
          <th>SL</th>
          <th>TP</th>
          <th>Lev</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((pos, i) => (
          <tr key={i}>
            <td className="text-text-primary font-medium">{pos.symbol}</td>
            <td>
              <span
                className={`badge ${
                  pos.side === "LONG" ? "badge-green" : "badge-red"
                }`}
              >
                {pos.side ?? "—"}
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
                ? `${pos.pnl_pct >= 0 ? "+" : ""}${pos.pnl_pct.toFixed(2)}%`
                : "—"}
            </td>
            <td className="text-accent-red">
              {pos.stop_loss?.toFixed(2) ?? "—"}
            </td>
            <td className="text-accent-green">
              {pos.take_profit?.toFixed(2) ?? "—"}
            </td>
            <td>{pos.leverage ?? "—"}x</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
