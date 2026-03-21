import type { TradeRecord } from "../types/api";

// Trades come from system snapshot or WS — for now, placeholder
const DEMO_TRADES: TradeRecord[] = [];

export default function TradesTab() {
  const trades = DEMO_TRADES;

  if (trades.length === 0) {
    return (
      <div className="text-text-muted text-xs italic p-2">
        No trade history
      </div>
    );
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Side</th>
          <th>Entry</th>
          <th>Exit</th>
          <th>Size</th>
          <th>PnL</th>
          <th>PnL%</th>
          <th>Hold</th>
          <th>Reason</th>
          <th>State</th>
        </tr>
      </thead>
      <tbody>
        {trades.map((t, i) => (
          <tr key={i}>
            <td>
              <span
                className={`badge ${
                  t.side === "LONG" ? "badge-green" : "badge-red"
                }`}
              >
                {t.side}
              </span>
            </td>
            <td>{t.entry_price.toFixed(2)}</td>
            <td>{t.exit_price.toFixed(2)}</td>
            <td>{t.size.toFixed(4)}</td>
            <td
              className={
                t.pnl >= 0 ? "text-accent-green" : "text-accent-red"
              }
            >
              {t.pnl.toFixed(2)}
            </td>
            <td
              className={
                t.pnl_pct >= 0 ? "text-accent-green" : "text-accent-red"
              }
            >
              {t.pnl_pct >= 0 ? "+" : ""}
              {t.pnl_pct.toFixed(2)}%
            </td>
            <td>{t.hold_bars} bars</td>
            <td className="text-text-secondary">{t.exit_reason}</td>
            <td className="text-text-secondary">{t.entry_state}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
