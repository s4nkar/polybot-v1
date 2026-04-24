import { useState, useEffect, useCallback } from "react";
import { getAllTrades, getAnalytics } from "../services/api";

const MODE_TABS = [
  { key: "all", label: "All Trades" },
  { key: "live", label: "🔴 Live" },
  { key: "paper", label: "🧪 Paper" },
];

const PAGE_SIZE = 25;

function getDateRange(filterType, filterValue) {
  if (!filterValue) return { dateFrom: null, dateTo: null };
  if (filterType === "day") {
    return {
      dateFrom: `${filterValue}T00:00:00`,
      dateTo: `${filterValue}T23:59:59.999999`,
    };
  }
  // month: filterValue is "YYYY-MM"
  const [year, month] = filterValue.split("-").map(Number);
  const lastDay = new Date(year, month, 0).getDate();
  return {
    dateFrom: `${filterValue}-01T00:00:00`,
    dateTo: `${filterValue}-${String(lastDay).padStart(2, "0")}T23:59:59.999999`,
  };
}

export default function Analytics() {
  const [mode, setMode] = useState("all");
  const [filterType, setFilterType] = useState(null); // "day" | "month" | null
  const [filterValue, setFilterValue] = useState("");
  const [analytics, setAnalytics] = useState(null);
  const [trades, setTrades] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);

  const { dateFrom, dateTo } = getDateRange(filterType, filterValue);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [a, t] = await Promise.all([
        getAnalytics(mode, dateFrom, dateTo),
        getAllTrades(PAGE_SIZE, page * PAGE_SIZE, mode, dateFrom, dateTo),
      ]);
      setAnalytics(a);
      setTrades(t.trades || []);
      setTotal(t.total || 0);
    } catch (err) {
      console.error("Analytics fetch error", err);
    } finally {
      setLoading(false);
    }
  }, [mode, page, dateFrom, dateTo]);

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 15000);
    return () => clearInterval(id);
  }, [fetchData]);

  // Reset page when mode or date filter changes
  useEffect(() => setPage(0), [mode, filterType, filterValue]);

  const handleDayChange = (e) => {
    setFilterType(e.target.value ? "day" : null);
    setFilterValue(e.target.value);
  };

  const handleMonthChange = (e) => {
    setFilterType(e.target.value ? "month" : null);
    setFilterValue(e.target.value);
  };

  const clearDateFilter = () => {
    setFilterType(null);
    setFilterValue("");
  };

  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      const BATCH = 200;
      const pages = Math.ceil(total / BATCH);
      const all = [];
      for (let i = 0; i < pages; i++) {
        const res = await getAllTrades(BATCH, i * BATCH, mode, dateFrom, dateTo);
        all.push(...(res.trades || []));
      }
      if (!all?.length) return;

      const headers = [
        "Time", "Bot", "Mode", "Side",
        "Entry Price", "Exit Price", "Shares", "Amount USD",
        "P&L USD", "P&L %", "Status", "Market",
      ];

      const escape = (v) => {
        const s = v == null ? "" : String(v);
        return s.includes(",") || s.includes('"') || s.includes("\n")
          ? `"${s.replace(/"/g, '""')}"` : s;
      };

      const rows = all.map((t) => [
        t.opened_at || t.created_at || "",
        t.bot_id?.toUpperCase() ?? "",
        t.trading_mode || (t.dry_run ? "paper" : "live"),
        t.side ?? "",
        t.entry_price ?? "",
        t.exit_price ?? "",
        t.shares ?? "",
        t.amount_usd ?? "",
        t.pnl_usd ?? "",
        t.pnl_pct ?? "",
        t.status ?? "",
        t.market_slug ?? "",
      ].map(escape).join(","));

      const csv = [headers.join(","), ...rows].join("\r\n");
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const label = filterValue ? `_${filterValue}` : "";
      a.href = url;
      a.download = `polybot_trades_${mode}${label}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export failed", err);
    } finally {
      setExporting(false);
    }
  };

  const totalPages = Math.ceil(total / PAGE_SIZE) || 1;

  const statCards = analytics
    ? [
      { label: "Total Trades", value: analytics.total_trades, icon: "📊", color: "text-brand-400" },
      { label: "Wins", value: analytics.wins, icon: "✅", color: "text-emerald-400" },
      { label: "Losses", value: analytics.losses, icon: "❌", color: "text-red-400" },
      { label: "Win Rate", value: `${analytics.win_rate.toFixed(1)}%`, icon: "🎯", color: "text-amber-400" },
      {
        label: "Total P&L",
        value: `${analytics.total_pnl >= 0 ? "+" : ""}$${analytics.total_pnl.toFixed(4)}`,
        icon: analytics.total_pnl >= 0 ? "💰" : "📉",
        color: analytics.total_pnl >= 0 ? "text-emerald-400" : "text-red-400",
        highlight: true,
      },
      {
        label: "Avg P&L / Trade",
        value: `${analytics.avg_pnl_per_trade >= 0 ? "+" : ""}$${analytics.avg_pnl_per_trade.toFixed(4)}`,
        icon: "📈",
        color: analytics.avg_pnl_per_trade >= 0 ? "text-emerald-400" : "text-red-400",
      },
      {
        label: "Best Trade",
        value: `+$${analytics.best_trade_pnl.toFixed(4)}`,
        icon: "🏆",
        color: "text-emerald-400",
      },
      {
        label: "Worst Trade",
        value: `$${analytics.worst_trade_pnl.toFixed(4)}`,
        icon: "💔",
        color: "text-red-400",
      },
      {
        label: "Total Volume",
        value: `$${analytics.total_volume.toFixed(2)}`,
        icon: "💵",
        color: "text-brand-400",
      },
      {
        label: "Open Trades",
        value: analytics.open_trades,
        icon: "⏳",
        color: "text-amber-400",
      },
    ]
    : [];

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
      return new Date(iso).toLocaleString();
    } catch {
      return "—";
    }
  };

  const modeColor = (m) => {
    if (m === "live") return "text-emerald-400 bg-emerald-500/10";
    return "text-amber-400 bg-amber-500/10";
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight">
          <span className="bg-gradient-to-r from-brand-400 to-brand-600 bg-clip-text text-transparent">Analytics</span>{" "}
          <span className="text-surface-300">Dashboard</span>
        </h1>
        <p className="mt-1 text-sm text-surface-400">
          Comprehensive trading performance across all sessions
        </p>
      </div>

      {/* Filters row */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Mode tabs */}
        <div className="flex gap-2">
          {MODE_TABS.map((tab) => (
            <button
              key={tab.key}
              id={`tab-${tab.key}`}
              onClick={() => setMode(tab.key)}
              className={`
                rounded-xl px-5 py-2.5 text-sm font-semibold transition-all duration-200
                ${mode === tab.key
                  ? "bg-brand-500/15 text-brand-400 shadow-sm shadow-brand-500/10"
                  : "text-surface-400 hover:text-surface-200 hover:bg-surface-800"}
              `}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="h-6 w-px bg-surface-700 hidden sm:block" />

        {/* Date filters */}
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 rounded-xl border border-surface-700 bg-surface-900/60 px-3 py-2 text-xs text-surface-400 transition-colors hover:border-surface-600 focus-within:border-brand-500/50">
            <span>Day</span>
            <input
              type="date"
              value={filterType === "day" ? filterValue : ""}
              onChange={handleDayChange}
              className="bg-transparent text-surface-200 outline-none [color-scheme:dark] cursor-pointer"
            />
          </label>

          <label className="flex items-center gap-1.5 rounded-xl border border-surface-700 bg-surface-900/60 px-3 py-2 text-xs text-surface-400 transition-colors hover:border-surface-600 focus-within:border-brand-500/50">
            <span>Month</span>
            <input
              type="month"
              value={filterType === "month" ? filterValue : ""}
              onChange={handleMonthChange}
              className="bg-transparent text-surface-200 outline-none [color-scheme:dark] cursor-pointer"
            />
          </label>

          {filterValue && (
            <button
              onClick={clearDateFilter}
              className="rounded-xl border border-surface-700 bg-surface-900/60 px-3 py-2 text-xs text-surface-400 hover:text-surface-200 hover:border-surface-600 transition-colors"
              title="Clear date filter"
            >
              ✕ Clear
            </button>
          )}
        </div>

        {/* Active filter badge */}
        {filterValue && (
          <span className="rounded-full bg-brand-500/15 px-2.5 py-1 text-xs font-medium text-brand-400">
            {filterValue}
          </span>
        )}

        <div className="ml-auto">
          <button
            onClick={handleExport}
            disabled={exporting || !total}
            className="flex items-center gap-1.5 rounded-xl border border-surface-700 bg-surface-900/60 px-3 py-2 text-xs font-medium text-surface-300 hover:text-surface-100 hover:border-surface-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title="Export filtered trades to CSV"
          >
            {exporting ? (
              <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5m0 0l5-5m-5 5V4" />
              </svg>
            )}
            {exporting ? "Exporting…" : "Export CSV"}
          </button>
        </div>
      </div>

      {/* Loading spinner */}
      {loading && !analytics ? (
        <div className="flex items-center justify-center py-20">
          <svg className="h-8 w-8 animate-spin text-brand-500" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>
      ) : (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {statCards.map((c) => (
              <div
                key={c.label}
                className={`
                  rounded-2xl border border-surface-700 bg-surface-900/60 p-4
                  ${c.highlight
                    ? analytics?.total_pnl >= 0
                      ? "border-emerald-500/30 bg-emerald-500/5"
                      : "border-red-500/30 bg-red-500/5"
                    : ""
                  }
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

          {/* Trade history table */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-bold text-surface-200">Trade History</h2>
              <span className="text-xs text-surface-500">
                {total} trade{total !== 1 ? "s" : ""} total
              </span>
            </div>

            {!trades.length ? (
              <div className="flex flex-col items-center justify-center rounded-2xl border border-surface-700 bg-surface-900/60 py-16 px-6 text-center">
                <span className="text-4xl mb-3">📭</span>
                <p className="text-surface-400 text-sm">No trades found for the selected filter.</p>
              </div>
            ) : (
              <div className="overflow-hidden rounded-2xl border border-surface-700 bg-surface-900/60">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="sticky top-0 z-10 bg-surface-800 text-xs uppercase text-surface-400">
                      <tr>
                        <th className="px-4 py-3 font-medium">Time</th>
                        <th className="px-4 py-3 font-medium">Bot</th>
                        <th className="px-4 py-3 font-medium">Mode</th>
                        <th className="px-4 py-3 font-medium">Side</th>
                        <th className="px-4 py-3 font-medium text-right">Entry</th>
                        <th className="px-4 py-3 font-medium text-right">Exit</th>
                        <th className="px-4 py-3 font-medium text-right">Shares</th>
                        <th className="px-4 py-3 font-medium text-right">Amount</th>
                        <th className="px-4 py-3 font-medium text-right">P&L ($)</th>
                        <th className="px-4 py-3 font-medium text-right">P&L (%)</th>
                        <th className="px-4 py-3 font-medium text-center">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-800">
                      {trades.map((t, i) => (
                        <tr
                          key={t.id || i}
                          className={`border-l-2 ${rowBorder(t.status)} hover:bg-surface-800/50 transition-colors`}
                        >
                          <td className="whitespace-nowrap px-4 py-3 text-surface-300 text-xs">
                            {formatTime(t.opened_at || t.created_at)}
                          </td>
                          <td className="px-4 py-3 font-medium text-surface-200">
                            {t.bot_id?.toUpperCase()}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-bold ${modeColor(t.trading_mode || (t.dry_run ? "paper" : "live"))}`}>
                              {(t.trading_mode || (t.dry_run ? "paper" : "live")).toUpperCase()}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-surface-300">{t.side}</td>
                          <td className="px-4 py-3 text-right font-mono text-surface-200">
                            ${Number(t.entry_price).toFixed(4)}
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-surface-200">
                            {t.exit_price != null ? `$${Number(t.exit_price).toFixed(4)}` : "—"}
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-surface-300">
                            {Number(t.shares).toFixed(2)}
                          </td>
                          <td className="px-4 py-3 text-right font-mono text-surface-300">
                            ${Number(t.amount_usd).toFixed(2)}
                          </td>
                          <td className={`px-4 py-3 text-right font-mono font-semibold ${t.pnl_usd > 0 ? "text-emerald-400" : t.pnl_usd < 0 ? "text-red-400" : "text-surface-400"
                            }`}>
                            {t.pnl_usd != null ? `${t.pnl_usd >= 0 ? "+" : ""}$${Number(t.pnl_usd).toFixed(4)}` : "—"}
                          </td>
                          <td className={`px-4 py-3 text-right font-mono font-semibold ${t.pnl_pct > 0 ? "text-emerald-400" : t.pnl_pct < 0 ? "text-red-400" : "text-surface-400"
                            }`}>
                            {t.pnl_pct != null ? `${t.pnl_pct >= 0 ? "+" : ""}${Number(t.pnl_pct).toFixed(2)}%` : "—"}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-bold ${statusColor(t.status)}`}>
                              {t.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex items-center justify-between border-t border-surface-700 px-4 py-3">
                    <span className="text-xs text-surface-500">
                      Page {page + 1} of {totalPages}
                    </span>
                    <div className="flex gap-2">
                      <button
                        id="btn-prev-page"
                        onClick={() => setPage((p) => Math.max(0, p - 1))}
                        disabled={page === 0}
                        className="rounded-lg px-3 py-1.5 text-xs font-medium text-surface-300 bg-surface-800 hover:bg-surface-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        ← Previous
                      </button>
                      <button
                        id="btn-next-page"
                        onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                        disabled={page >= totalPages - 1}
                        className="rounded-lg px-3 py-1.5 text-xs font-medium text-surface-300 bg-surface-800 hover:bg-surface-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        Next →
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
