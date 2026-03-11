import React, { useState, useMemo } from "react";

/**
 * BotForm — renders the correct parameter fields for Bot 1 or Bot 2.
 *
 * Props:
 *   botId        "bot1" | "bot2"
 *   tradingMode  "live" | "paper"
 *   onLaunch     (payload) => void
 *   onStop       () => void
 *   running      boolean
 *   loading      boolean
 */
export default function BotForm({ botId, tradingMode, onLaunch, onStop, running, loading }) {
  const isBot1 = botId === "bot1";
  const isLive = tradingMode === "live";
  const dryRun = !isLive;

  // ── Shared fields ───────────────────────────────────────
  const [marketSlug, setMarketSlug] = useState("btc-updown-5m");
  const [amountUsd, setAmountUsd] = useState("5");

  // ── Bot 1 specific ─────────────────────────────────────
  const [useScoreThreshold, setUseScoreThreshold] = useState(true);
  const [scoreThreshold, setScoreThreshold] = useState("0.6");
  const [targetProfitPct, setTargetProfitPct] = useState("20");
  const [stopLossPct, setStopLossPct] = useState("50");
  const [timeStopSeconds, setTimeStopSeconds] = useState("45");
  const [maxRoundsBot1, setMaxRoundsBot1] = useState("");

  // ── Bot 2 specific ─────────────────────────────────────
  const [minGapPct, setMinGapPct] = useState("0.10");
  const [maxEntryPrice, setMaxEntryPrice] = useState("0.70");
  const [maxRoundsBot2, setMaxRoundsBot2] = useState("");

  // ── Validation ─────────────────────────────────────────
  const isValid = useMemo(() => {
    if (!marketSlug.trim()) return false;
    if (isNaN(Number(amountUsd)) || Number(amountUsd) <= 0) return false;

    if (isBot1) {
      if (useScoreThreshold && (isNaN(Number(scoreThreshold)) || Number(scoreThreshold) < 0 || Number(scoreThreshold) > 1)) return false;
      if (isNaN(Number(targetProfitPct)) || Number(targetProfitPct) <= 0) return false;
      if (isNaN(Number(stopLossPct)) || Number(stopLossPct) <= 0) return false;
      if (isNaN(Number(timeStopSeconds)) || Number(timeStopSeconds) <= 0) return false;
    } else {
      if (isNaN(Number(minGapPct)) || Number(minGapPct) < 0) return false;
      if (isNaN(Number(maxEntryPrice)) || Number(maxEntryPrice) <= 0 || Number(maxEntryPrice) > 1) return false;
    }
    return true;
  }, [marketSlug, amountUsd, isBot1, useScoreThreshold, scoreThreshold, targetProfitPct, stopLossPct, timeStopSeconds, minGapPct, maxEntryPrice]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!isValid) return;

    const payload = {
      bot_id: botId,
      dry_run: dryRun,
      trading_mode: tradingMode,
    };

    if (isBot1) {
      payload.bot1_params = {
        market_slug: marketSlug,
        amount_usd: Number(amountUsd),
        use_score_threshold: useScoreThreshold,
        score_threshold: useScoreThreshold ? Number(scoreThreshold) : 0.0,
        target_profit_pct: Number(targetProfitPct),
        stop_loss_pct: Number(stopLossPct),
        time_stop_seconds: Number(timeStopSeconds),
        max_rounds: maxRoundsBot1 ? Number(maxRoundsBot1) : null,
      };
    } else {
      payload.bot2_params = {
        market_slug: marketSlug,
        amount_usd: Number(amountUsd),
        min_gap_pct: Number(minGapPct),
        max_entry_price: Number(maxEntryPrice),
        max_rounds: maxRoundsBot2 ? Number(maxRoundsBot2) : null,
      };
    }

    onLaunch(payload);
  };

  // ── Render ─────────────────────────────────────────────
  const inputCls =
    "w-full rounded-lg border border-surface-600 bg-surface-800 px-4 py-2.5 text-sm text-surface-100 placeholder-surface-500 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 transition-colors";
  const labelCls = "block text-xs font-medium text-surface-300 mb-1.5";

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Mode banner */}
      <div className={`flex items-center gap-3 rounded-xl border px-4 py-3 ${isLive
        ? "border-emerald-500/30 bg-emerald-500/10"
        : "border-amber-500/30 bg-amber-500/10"
        }`}>
        <span className="text-lg">{isLive ? "🔴" : "🧪"}</span>
        <p className={`text-sm ${isLive ? "text-emerald-300" : "text-amber-300"}`}>
          {isLive ? (
            <><strong>Live Mode</strong> — real orders will be placed on Polymarket.</>
          ) : (
            <><strong>Paper Mode</strong> — orders will be simulated, not placed on Polymarket.</>
          )}
        </p>
      </div>

      {/* Info about 24hr / 5-min */}
      <div className="flex items-center gap-3 rounded-xl border border-brand-500/20 bg-brand-500/5 px-4 py-3">
        <span className="text-lg">⏰</span>
        <p className="text-sm text-brand-300">
          Bot will run for <strong>24 hours</strong>, making a trade every <strong>5 minutes</strong>. You can stop it at any time.
        </p>
      </div>

      {/* Shared fields */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className={labelCls} htmlFor="marketSlug">Market Slug</label>
          <input id="marketSlug" className={inputCls} value={marketSlug} onChange={(e) => setMarketSlug(e.target.value)} placeholder="btc-5min" />
        </div>
        <div>
          <label className={labelCls} htmlFor="amountUsd">Amount (USD)</label>
          <input id="amountUsd" className={inputCls} type="number" step="0.01" min="0.01" value={amountUsd} onChange={(e) => setAmountUsd(e.target.value)} />
        </div>
      </div>

      {/* Bot 1 fields */}
      {isBot1 && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <div className="flex items-center justify-between rounded-lg border border-surface-600 bg-surface-800 px-4 py-3">
              <div>
                <p className="text-sm font-medium text-surface-200">Score Threshold Filter</p>
                <p className="text-xs text-surface-400 mt-0.5">
                  {useScoreThreshold
                    ? "Trades must pass signal score filter before entry"
                    : "Disabled — all trades bypass score filter"}
                </p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={useScoreThreshold}
                onClick={() => setUseScoreThreshold(!useScoreThreshold)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 focus:ring-offset-surface-900 ${useScoreThreshold ? "bg-brand-500" : "bg-surface-600"
                  }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${useScoreThreshold ? "translate-x-5" : "translate-x-0"
                    }`}
                />
              </button>
            </div>
          </div>
          <div className={!useScoreThreshold ? "opacity-40 pointer-events-none" : ""}>
            <label className={labelCls} htmlFor="scoreThreshold">Score Threshold (0–1)</label>
            <input id="scoreThreshold" className={inputCls} type="number" step="0.01" min="0" max="1" value={scoreThreshold} onChange={(e) => setScoreThreshold(e.target.value)} disabled={!useScoreThreshold} />
          </div>
          <div>
            <label className={labelCls} htmlFor="targetProfitPct">Target Profit %</label>
            <input id="targetProfitPct" className={inputCls} type="number" step="1" min="1" value={targetProfitPct} onChange={(e) => setTargetProfitPct(e.target.value)} />
          </div>
          <div>
            <label className={labelCls} htmlFor="stopLossPct">Stop Loss %</label>
            <input id="stopLossPct" className={inputCls} type="number" step="1" min="1" value={stopLossPct} onChange={(e) => setStopLossPct(e.target.value)} />
          </div>
          <div>
            <label className={labelCls} htmlFor="timeStopSeconds">Time Stop (seconds)</label>
            <input id="timeStopSeconds" className={inputCls} type="number" step="1" min="1" value={timeStopSeconds} onChange={(e) => setTimeStopSeconds(e.target.value)} />
          </div>
          <div className="sm:col-span-2">
            <label className={labelCls} htmlFor="maxRoundsBot1">Max Rounds (optional)</label>
            <input id="maxRoundsBot1" className={inputCls} type="number" step="1" min="1" value={maxRoundsBot1} onChange={(e) => setMaxRoundsBot1(e.target.value)} placeholder="Unlimited" />
          </div>
        </div>
      )}

      {/* Bot 2 fields */}
      {!isBot1 && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelCls} htmlFor="minGapPct">Min BTC Gap %</label>
            <input id="minGapPct" className={inputCls} type="number" step="0.01" min="0" value={minGapPct} onChange={(e) => setMinGapPct(e.target.value)} />
          </div>
          <div>
            <label className={labelCls} htmlFor="maxEntryPrice">Max Entry Price (0–1)</label>
            <input id="maxEntryPrice" className={inputCls} type="number" step="0.01" min="0.01" max="1" value={maxEntryPrice} onChange={(e) => setMaxEntryPrice(e.target.value)} />
          </div>
          <div className="sm:col-span-2">
            <label className={labelCls} htmlFor="maxRoundsBot2">Max Rounds (optional)</label>
            <input id="maxRoundsBot2" className={inputCls} type="number" step="1" min="1" value={maxRoundsBot2} onChange={(e) => setMaxRoundsBot2(e.target.value)} placeholder="Unlimited" />
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-3 pt-2">
        {!running ? (
          <button
            id="btn-launch"
            type="submit"
            disabled={!isValid || loading}
            className={`flex-1 rounded-xl px-6 py-3 text-sm font-bold text-white shadow-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none ${isLive
              ? "bg-gradient-to-r from-emerald-600 to-emerald-500 shadow-emerald-500/25 hover:shadow-emerald-500/40"
              : "bg-gradient-to-r from-brand-600 to-brand-500 shadow-brand-500/25 hover:shadow-brand-500/40"
              }`}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Launching…
              </span>
            ) : (
              `🚀 Launch ${isLive ? "LIVE" : "Paper"}`
            )}
          </button>
        ) : (
          <button
            id="btn-stop"
            type="button"
            onClick={onStop}
            disabled={loading}
            className="flex-1 rounded-xl bg-gradient-to-r from-red-600 to-red-500 px-6 py-3 text-sm font-bold text-white shadow-lg shadow-red-500/25 transition-all hover:shadow-red-500/40 disabled:opacity-40"
          >
            {loading ? "Stopping…" : "⏹ Stop Bot"}
          </button>
        )}
      </div>
    </form>
  );
}
