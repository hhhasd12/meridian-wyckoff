import { useEffect } from "react";
import { fetchTrades } from "../core/api";
import { useStore } from "../core/store";

export default function TradesTab() {
  const trades = useStore((s) => s.trades);
  const setTrades = useStore((s) => s.setTrades);

  useEffect(() => {
    fetchTrades()
      .then((res) => setTrades(res.trades ?? []))
      .catch(() => {});
  }, [setTrades]);

  if (trades.length === 0) {
    return (
      <div className="text-text-muted text-sm italic p-2">
        暂无交易记录
      </div>
    );
  }

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>方向</th>
          <th>入场价</th>
          <th>出场价</th>
          <th>仓位</th>
          <th>盈亏</th>
          <th>盈亏%</th>
          <th>持仓</th>
          <th>原因</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody>
        {trades.map((t, i) => (
          <tr key={i}>
            <td>
              <span
                className={`badge text-xs ${
                  t.side === "LONG" ? "badge-green" : "badge-red"
                }`}
              >
                {t.side === "LONG" ? "做多" : "做空"}
              </span>
            </td>
            <td>{(t.entry_price ?? 0).toFixed(2)}</td>
            <td>{(t.exit_price ?? 0).toFixed(2)}</td>
            <td>{(t.size ?? 0).toFixed(4)}</td>
            <td
              className={
                t.pnl >= 0 ? "text-accent-green" : "text-accent-red"
              }
            >
              {(t.pnl ?? 0).toFixed(2)}
            </td>
            <td
              className={
                t.pnl_pct >= 0 ? "text-accent-green" : "text-accent-red"
              }
            >
              {t.pnl_pct >= 0 ? "+" : ""}
              {(t.pnl_pct ?? 0).toFixed(2)}%
            </td>
            <td>{t.hold_bars} 根K线</td>
            <td className="text-text-secondary">{t.exit_reason}</td>
            <td className="text-text-secondary">{t.entry_state}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
