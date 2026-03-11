import React from "react";

/**
 * SessionSummary — stat cards for the current session.
 *
 * Props:
 *   status  { total_trades, wins, losses, win_rate, session_pnl }
 */
export default function SessionSummary({ status }) {
  const { total_trades = 0, wins = 0, losses = 0, win_rate = 0, session_pnl = 0 } = status || {};

  const cards = [
    { label: "Total Trades", value: total_trades, icon: "📊", color: "text-brand-400" },
    { label: "Wins", value: wins, icon: "✅", color: "text-emerald-400" },
    { label: "Losses", value: losses, icon: "❌", color: "text-red-400" },
    { label: "Win Rate", value: `${win_rate.toFixed(1)}%`, icon: "🎯", color: "text-amber-400" },
    {
      label: "Session P&L",
      value: `${session_pnl >= 0 ? "+" : ""}$${session_pnl.toFixed(4)}`,
      icon: session_pnl >= 0 ? "💰" : "📉",
      color: session_pnl >= 0 ? "text-emerald-400" : "text-red-400",
      highlight: true,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {cards.map((c) => (
        <div
          key={c.label}
          className={`
            rounded-2xl border border-surface-700 bg-surface-900/60 p-4
            ${c.highlight ? (session_pnl >= 0 ? "border-emerald-500/30 bg-emerald-500/5" : "border-red-500/30 bg-red-500/5") : ""}
            transition-colors hover:bg-surface-800/60
          `}
        >
          <div className="flex items-center gap-2 text-xs text-surface-400 mb-2">
            <span>{c.icon}</span>
            <span>{c.label}</span>
          </div>
          <p className={`text-xl font-bold ${c.color}`}>{c.value}</p>
        </div>
      ))}
    </div>
  );
}
