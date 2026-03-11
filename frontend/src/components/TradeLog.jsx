import React, { useRef, useEffect } from "react";

/**
 * TradeLog — scrollable table of trades.
 *
 * Props:
 *   trades   Array of trade objects
 *
 * Columns: Time, Bot, Action, Entry, Exit, P&L ($), P&L (%), Status
 * Row colours: green WIN, red LOSS, yellow OPEN
 */
export default function TradeLog({ trades }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [trades.length]);

  if (!trades.length) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-surface-700 bg-surface-900/60 py-16 px-6 text-center">
        <span className="text-4xl mb-3">📭</span>
        <p className="text-surface-400 text-sm">No trades yet. Launch a bot to start trading.</p>
      </div>
    );
  }

  const statusColor = (s) => {
    if (s === "WIN") return "text-emerald-400 bg-emerald-500/10";
    if (s === "LOSS") return "text-red-400 bg-red-500/10";
    return "text-amber-400 bg-amber-500/10";
  };

  const rowBorder = (s) => {
    if (s === "WIN") return "border-l-emerald-500";
    if (s === "LOSS") return "border-l-red-500";
    return "border-l-amber-500";
  };

  const formatTime = (iso) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleTimeString();
    } catch {
      return "—";
    }
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-surface-700 bg-surface-900/60">
      <div className="overflow-x-auto max-h-96 overflow-y-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 z-10 bg-surface-800 text-xs uppercase text-surface-400">
            <tr>
              <th className="px-4 py-3 font-medium">Time</th>
              <th className="px-4 py-3 font-medium">Bot</th>
              <th className="px-4 py-3 font-medium">Side</th>
              <th className="px-4 py-3 font-medium text-right">Entry</th>
              <th className="px-4 py-3 font-medium text-right">Exit</th>
              <th className="px-4 py-3 font-medium text-right">P&L ($)</th>
              <th className="px-4 py-3 font-medium text-right">P&L (%)</th>
              <th className="px-4 py-3 font-medium text-center">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-800">
            {trades.map((t, i) => (
              <tr key={t.id || i} className={`border-l-2 ${rowBorder(t.status)} hover:bg-surface-800/50 transition-colors`}>
                <td className="whitespace-nowrap px-4 py-3 text-surface-300">{formatTime(t.opened_at || t.created_at)}</td>
                <td className="px-4 py-3 font-medium text-surface-200">{t.bot_id?.toUpperCase()}</td>
                <td className="px-4 py-3 text-surface-300">{t.side}</td>
                <td className="px-4 py-3 text-right font-mono text-surface-200">${Number(t.entry_price).toFixed(4)}</td>
                <td className="px-4 py-3 text-right font-mono text-surface-200">
                  {t.exit_price != null ? `$${Number(t.exit_price).toFixed(4)}` : "—"}
                </td>
                <td className={`px-4 py-3 text-right font-mono font-semibold ${t.pnl_usd > 0 ? "text-emerald-400" : t.pnl_usd < 0 ? "text-red-400" : "text-surface-400"}`}>
                  {t.pnl_usd != null ? `${t.pnl_usd >= 0 ? "+" : ""}$${Number(t.pnl_usd).toFixed(4)}` : "—"}
                </td>
                <td className={`px-4 py-3 text-right font-mono font-semibold ${t.pnl_pct > 0 ? "text-emerald-400" : t.pnl_pct < 0 ? "text-red-400" : "text-surface-400"}`}>
                  {t.pnl_pct != null ? `${t.pnl_pct >= 0 ? "+" : ""}${Number(t.pnl_pct).toFixed(2)}%` : "—"}
                </td>
                <td className="px-4 py-3 text-center">
                  <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-bold ${statusColor(t.status)}`}>{t.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
