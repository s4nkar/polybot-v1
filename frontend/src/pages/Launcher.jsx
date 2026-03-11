import React, { useState, useEffect, useCallback, useRef } from "react";
import BotCard from "../components/BotCard";
import BotForm from "../components/BotForm";
import TradeLog from "../components/TradeLog";
import SessionSummary from "../components/SessionSummary";
import { startBot, stopBot, getBotStatus, getTrades, createTradeSocket } from "../services/api";

export default function Launcher() {
  const [selectedBot, setSelectedBot] = useState("bot1");
  const [tradingMode, setTradingMode] = useState("paper"); // "live" | "paper"
  const [status, setStatus] = useState({ running: false });
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);

  // ── Fetch status + trades on mount and every 5s ────────
  const refresh = useCallback(async () => {
    try {
      const [s, t] = await Promise.all([getBotStatus(), getTrades()]);
      setStatus(s);
      setTrades(t);
    } catch (err) {
      console.error("Refresh error", err);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  // ── WebSocket connection ───────────────────────────────
  useEffect(() => {
    const ws = createTradeSocket((msg) => {
      if (msg.trade) {
        setTrades((prev) => {
          const idx = prev.findIndex((t) => t.id === msg.trade.id);
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = msg.trade;
            return updated;
          }
          return [msg.trade, ...prev];
        });
      }
      // Re-fetch status to update summary cards
      getBotStatus().then(setStatus).catch(() => {});
    });
    wsRef.current = ws;
    return () => ws.close();
  }, []);

  // ── Launch handler ─────────────────────────────────────
  const handleLaunch = async (payload) => {
    setLoading(true);
    setError(null);
    try {
      const res = await startBot(payload);
      if (!res.ok) {
        setError(res.error || "Failed to start bot");
      } else {
        await refresh();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // ── Stop handler ───────────────────────────────────────
  const handleStop = async () => {
    setLoading(true);
    setError(null);
    try {
      await stopBot(selectedBot);
      // Give the bot a moment to wind down
      setTimeout(refresh, 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const isRunning = status.running === true;
  const runningBotId = status.bot_id;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight">
          <span className="bg-gradient-to-r from-brand-400 to-brand-600 bg-clip-text text-transparent">Polybot</span>{" "}
          <span className="text-surface-300">Dashboard</span>
        </h1>
        <p className="mt-1 text-sm text-surface-400">Automated Polymarket BTC 5-min prediction trading</p>
      </div>

      {/* Error banner */}
      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          ⚠️ {error}
        </div>
      )}

      {/* ── Trading Mode Toggle ─────────────────────────────── */}
      <div className="rounded-2xl border border-surface-700 bg-surface-900/60 p-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-surface-200 uppercase tracking-wider mb-1">Trading Mode</h2>
            <p className="text-xs text-surface-400">
              {tradingMode === "paper"
                ? "Simulated orders — no real money at risk"
                : "Real orders placed on Polymarket"}
            </p>
          </div>

          {/* Toggle switch */}
          <div className="flex items-center gap-4">
            <span className={`text-sm font-semibold transition-colors ${tradingMode === "paper" ? "text-amber-400" : "text-surface-500"}`}>
              🧪 Paper
            </span>
            <button
              id="trading-mode-toggle"
              type="button"
              onClick={() => setTradingMode((m) => (m === "paper" ? "live" : "paper"))}
              disabled={isRunning}
              className={`
                relative inline-flex h-7 w-14 shrink-0 cursor-pointer rounded-full border-2 border-transparent
                transition-colors duration-300 ease-in-out focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 focus:ring-offset-surface-900
                ${tradingMode === "live"
                  ? "bg-gradient-to-r from-emerald-500 to-emerald-400"
                  : "bg-surface-600"
                }
                ${isRunning ? "opacity-50 cursor-not-allowed" : ""}
              `}
            >
              <span
                className={`
                  pointer-events-none inline-block h-6 w-6 rounded-full bg-white shadow-lg
                  transform transition-transform duration-300 ease-in-out
                  ${tradingMode === "live" ? "translate-x-7" : "translate-x-0"}
                `}
              />
            </button>
            <span className={`text-sm font-semibold transition-colors ${tradingMode === "live" ? "text-emerald-400" : "text-surface-500"}`}>
              🔴 Live
            </span>
          </div>
        </div>

        {/* Live mode warning */}
        {tradingMode === "live" && (
          <div className="mt-4 flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3">
            <span className="text-lg">⚠️</span>
            <p className="text-sm text-red-300">
              <strong>Live Mode</strong> — Real orders will be placed on Polymarket using your connected wallet. Proceed with caution.
            </p>
          </div>
        )}

        {/* Running mode indicator */}
        {isRunning && (
          <div className="mt-3 space-y-2">
            <div className="flex items-center gap-2">
              <span className="flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
              </span>
              <span className="text-xs font-semibold text-surface-300">
                Currently running in{" "}
                <span className={status.trading_mode === "live" ? "text-emerald-400" : "text-amber-400"}>
                  {(status.trading_mode || "paper").toUpperCase()}
                </span>{" "}
                mode
              </span>
            </div>
            {/* Live activity feed */}
            {status.last_activity && (
              <div className="flex items-start gap-2 rounded-lg border border-surface-700 bg-surface-800/50 px-3 py-2">
                <span className="mt-0.5 text-xs">📡</span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-mono text-brand-300 truncate">{status.last_activity}</p>
                  {status.round_number > 0 && (
                    <p className="mt-0.5 text-[10px] text-surface-500">Round {status.round_number}</p>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bot cards */}
      <div className="grid gap-4 sm:grid-cols-2">
        <BotCard
          id="bot1"
          title="Bot 1 — Scalp to Target"
          subtitle="Short-term scalping with signal scoring & take-profit / stop-loss exits"
          selected={selectedBot === "bot1"}
          running={isRunning && runningBotId === "bot1"}
          onSelect={() => setSelectedBot("bot1")}
        />
        <BotCard
          id="bot2"
          title="Bot 2 — Hold to Resolution"
          subtitle="Buy at value odds and hold until the 5-min market resolves"
          selected={selectedBot === "bot2"}
          running={isRunning && runningBotId === "bot2"}
          onSelect={() => setSelectedBot("bot2")}
        />
      </div>

      {/* Bot form */}
      <div className="rounded-2xl border border-surface-700 bg-surface-900/60 p-6">
        <h2 className="mb-5 text-lg font-bold text-surface-200">
          {selectedBot === "bot1" ? "Bot 1 — Scalp to Target" : "Bot 2 — Hold to Resolution"} Configuration
        </h2>
        <BotForm
          botId={selectedBot}
          tradingMode={tradingMode}
          onLaunch={handleLaunch}
          onStop={handleStop}
          running={isRunning && runningBotId === selectedBot}
          loading={loading}
        />
      </div>

      {/* Session summary */}
      <SessionSummary status={status} />

      {/* Trade log */}
      <div>
        <h2 className="mb-3 text-lg font-bold text-surface-200">Trade Log</h2>
        <TradeLog trades={trades} />
      </div>
    </div>
  );
}
