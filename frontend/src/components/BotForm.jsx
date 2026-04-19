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
 *
 * Bot 1 params updated to WebSocket scalper strategy:
 *   REMOVED: use_score_threshold, score_threshold, target_profit_pct, stop_loss_pct
 *   ADDED:   entry_min, entry_max, take_profit_cents, stop_loss_cents
 */
export default function BotForm({ botId, tradingMode, onLaunch, onStop, running, loading }) {
  const isBot1 = botId === "bot1";
  const isLive = tradingMode === "live";
  const dryRun = !isLive;

  // ── Shared fields ───────────────────────────────────────
  const [marketSlug, setMarketSlug] = useState("btc-updown-5m");
  const [amountUsd, setAmountUsd] = useState("5");

  // ── Bot 1 fields (new WebSocket scalper params) ────────
  const [entryMin, setEntryMin] = useState("0.28");
  const [entryMax, setEntryMax] = useState("0.30");
  const [takeProfitCents, setTakeProfitCents] = useState("0.11");
  const [stopLossCents, setStopLossCents] = useState("0.05");
  const [timeStopSeconds, setTimeStopSeconds] = useState("45");
  const [maxRoundsBot1, setMaxRoundsBot1] = useState("");

  // ── Bot 2 fields (unchanged) ───────────────────────────
  const [minGapPct, setMinGapPct] = useState("0.10");
  const [maxEntryPrice, setMaxEntryPrice] = useState("0.70");
  const [maxRoundsBot2, setMaxRoundsBot2] = useState("");

  // ── Validation ─────────────────────────────────────────
  const isValid = useMemo(() => {
    if (!marketSlug.trim()) return false;
    if (isNaN(Number(amountUsd)) || Number(amountUsd) <= 0) return false;

    if (isBot1) {
      const eMin = Number(entryMin);
      const eMax = Number(entryMax);
      const tp = Number(takeProfitCents);
      const sl = Number(stopLossCents);
      const ts = Number(timeStopSeconds);

      if (isNaN(eMin) || eMin < 0.01 || eMin > 0.99) return false;
      if (isNaN(eMax) || eMax < 0.01 || eMax > 0.99) return false;
      if (eMin >= eMax) return false;  // zone must be a range
      if (isNaN(tp) || tp <= 0) return false;
      if (isNaN(sl) || sl <= 0) return false;
      if (isNaN(ts) || ts <= 0) return false;
    } else {
      if (isNaN(Number(minGapPct)) || Number(minGapPct) < 0) return false;
      if (isNaN(Number(maxEntryPrice)) || Number(maxEntryPrice) <= 0
        || Number(maxEntryPrice) > 1) return false;
    }
    return true;
  }, [
    marketSlug, amountUsd, isBot1,
    entryMin, entryMax, takeProfitCents, stopLossCents, timeStopSeconds,
    minGapPct, maxEntryPrice,
  ]);

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
        entry_min: Number(entryMin),
        entry_max: Number(entryMax),
        take_profit_cents: Number(takeProfitCents),
        stop_loss_cents: Number(stopLossCents),
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

  // ── Styles ─────────────────────────────────────────────
  const inputCls =
    "w-full rounded-lg border border-surface-600 bg-surface-800 px-4 py-2.5 text-sm text-surface-100 placeholder-surface-500 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 transition-colors";
  const labelCls = "block text-xs font-medium text-surface-300 mb-1.5";
  const hintCls = "mt-1.5 text-xs text-surface-500";

  return (
    <form onSubmit={handleSubmit} className="space-y-5">

      {/* Mode banner */}
      <div className={`flex items-center gap-3 rounded-xl border px-4 py-3 ${isLive
          ? "border-emerald-500/30 bg-emerald-500/10"
          : "border-amber-500/30 bg-amber-500/10"
        }`}>
        <span className="text-lg">{isLive ? "🔴" : "🧪"}</span>
        <p className={`text-sm ${isLive ? "text-emerald-300" : "text-amber-300"}`}>
          {isLive
            ? <><strong>Live Mode</strong> — real orders will be placed on Polymarket.</>
            : <><strong>Paper Mode</strong> — orders will be simulated, not placed on Polymarket.</>
          }
        </p>
      </div>

      {/* Strategy info banner — Bot 1 only */}
      {isBot1 && (
        <div className="flex items-start gap-3 rounded-xl border border-brand-500/20 bg-brand-500/5 px-4 py-3">
          <span className="text-lg">⚡</span>
          <p className="text-sm text-brand-300">
            <strong>WebSocket Scalper</strong> — monitors live price continuously. Enters when
            either side's ask hits the entry zone, exits at fixed-cent TP / SL or time stop.
          </p>
        </div>
      )}

      {/* Bot 2 info banner */}
      {!isBot1 && (
        <div className="flex items-center gap-3 rounded-xl border border-brand-500/20 bg-brand-500/5 px-4 py-3">
          <span className="text-lg">⏰</span>
          <p className="text-sm text-brand-300">
            Bot will run for <strong>24 hours</strong>, making a trade every{" "}
            <strong>5 minutes</strong>. You can stop it at any time.
          </p>
        </div>
      )}

      {/* Shared fields */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className={labelCls} htmlFor="marketSlug">Market Slug</label>
          <input
            id="marketSlug"
            className={inputCls}
            value={marketSlug}
            onChange={(e) => setMarketSlug(e.target.value)}
            placeholder="btc-updown-5m"
          />
        </div>
        <div>
          <label className={labelCls} htmlFor="amountUsd">Amount (USD)</label>
          <input
            id="amountUsd"
            className={inputCls}
            type="number"
            step="0.01"
            min="0.01"
            value={amountUsd}
            onChange={(e) => setAmountUsd(e.target.value)}
          />
        </div>
      </div>

      {/* ── Bot 1 fields ─────────────────────────────────── */}
      {isBot1 && (
        <div className="space-y-4">

          {/* Entry zone */}
          <div>
            <p className={`${labelCls} mb-2`}>Entry Zone (token ask price)</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className={labelCls} htmlFor="entryMin">Min (floor)</label>
                <input
                  id="entryMin"
                  className={inputCls}
                  type="number"
                  step="0.01"
                  min="0.01"
                  max="0.99"
                  value={entryMin}
                  onChange={(e) => setEntryMin(e.target.value)}
                />
                <p className={hintCls}>Enter when ask ≥ this value</p>
              </div>
              <div>
                <label className={labelCls} htmlFor="entryMax">Max (ceiling)</label>
                <input
                  id="entryMax"
                  className={inputCls}
                  type="number"
                  step="0.01"
                  min="0.01"
                  max="0.99"
                  value={entryMax}
                  onChange={(e) => setEntryMax(e.target.value)}
                />
                <p className={hintCls}>Enter when ask ≤ this value</p>
              </div>
            </div>
            {/* Zone validation warning */}
            {Number(entryMin) >= Number(entryMax) && entryMin && entryMax && (
              <p className="mt-2 text-xs text-red-400">⚠ Min must be less than Max</p>
            )}
          </div>

          {/* TP / SL */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className={labelCls} htmlFor="takeProfitCents">Take Profit (cents)</label>
              <input
                id="takeProfitCents"
                className={inputCls}
                type="number"
                step="0.01"
                min="0.01"
                value={takeProfitCents}
                onChange={(e) => setTakeProfitCents(e.target.value)}
              />
              <p className={hintCls}>
                Exit when bid rises by this much above entry
                {entryMin && takeProfitCents
                  ? ` (e.g. ${Number(entryMin).toFixed(2)} → ${(Number(entryMin) + Number(takeProfitCents)).toFixed(2)})`
                  : ""}
              </p>
            </div>
            <div>
              <label className={labelCls} htmlFor="stopLossCents">Stop Loss (cents)</label>
              <input
                id="stopLossCents"
                className={inputCls}
                type="number"
                step="0.01"
                min="0.01"
                value={stopLossCents}
                onChange={(e) => setStopLossCents(e.target.value)}
              />
              <p className={hintCls}>
                Exit when bid drops by this much below entry
                {entryMin && stopLossCents
                  ? ` (e.g. ${Number(entryMin).toFixed(2)} → ${(Number(entryMin) - Number(stopLossCents)).toFixed(2)})`
                  : ""}
              </p>
            </div>
          </div>

          {/* Time stop + max rounds */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className={labelCls} htmlFor="timeStopSeconds">Time Stop (seconds)</label>
              <input
                id="timeStopSeconds"
                className={inputCls}
                type="number"
                step="1"
                min="1"
                value={timeStopSeconds}
                onChange={(e) => setTimeStopSeconds(e.target.value)}
              />
              <p className={hintCls}>Force-sell when this many seconds remain</p>
            </div>
            <div>
              <label className={labelCls} htmlFor="maxRoundsBot1">Max Trades (optional)</label>
              <input
                id="maxRoundsBot1"
                className={inputCls}
                type="number"
                step="1"
                min="1"
                value={maxRoundsBot1}
                onChange={(e) => setMaxRoundsBot1(e.target.value)}
                placeholder="Unlimited"
              />
              <p className={hintCls}>Stop after this many completed trades</p>
            </div>
          </div>

          {/* Live preview card */}
          {isValid && (
            <div className="rounded-xl border border-surface-600 bg-surface-800/50 px-4 py-3 space-y-1">
              <p className="text-xs font-medium text-surface-300 mb-2">Strategy preview</p>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="rounded-lg bg-surface-700 px-3 py-2">
                  <p className="text-xs text-surface-400">Entry zone</p>
                  <p className="text-sm font-semibold text-surface-100">
                    {Number(entryMin).toFixed(2)}–{Number(entryMax).toFixed(2)}
                  </p>
                </div>
                <div className="rounded-lg bg-emerald-900/40 border border-emerald-500/20 px-3 py-2">
                  <p className="text-xs text-emerald-400">Take profit</p>
                  <p className="text-sm font-semibold text-emerald-300">
                    +{Number(takeProfitCents).toFixed(2)}¢
                  </p>
                </div>
                <div className="rounded-lg bg-red-900/40 border border-red-500/20 px-3 py-2">
                  <p className="text-xs text-red-400">Stop loss</p>
                  <p className="text-sm font-semibold text-red-300">
                    −{Number(stopLossCents).toFixed(2)}¢
                  </p>
                </div>
              </div>
              <p className="text-xs text-surface-500 text-center pt-1">
                Risk/reward: 1 : {(Number(takeProfitCents) / Number(stopLossCents)).toFixed(2)}
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── Bot 2 fields (unchanged) ──────────────────────── */}
      {!isBot1 && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelCls} htmlFor="minGapPct">Min BTC Gap %</label>
            <input
              id="minGapPct"
              className={inputCls}
              type="number"
              step="0.01"
              min="0"
              value={minGapPct}
              onChange={(e) => setMinGapPct(e.target.value)}
            />
          </div>
          <div>
            <label className={labelCls} htmlFor="maxEntryPrice">Max Entry Price (0–1)</label>
            <input
              id="maxEntryPrice"
              className={inputCls}
              type="number"
              step="0.01"
              min="0.01"
              max="1"
              value={maxEntryPrice}
              onChange={(e) => setMaxEntryPrice(e.target.value)}
            />
          </div>
          <div className="sm:col-span-2">
            <label className={labelCls} htmlFor="maxRoundsBot2">Max Rounds (optional)</label>
            <input
              id="maxRoundsBot2"
              className={inputCls}
              type="number"
              step="1"
              min="1"
              value={maxRoundsBot2}
              onChange={(e) => setMaxRoundsBot2(e.target.value)}
              placeholder="Unlimited"
            />
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