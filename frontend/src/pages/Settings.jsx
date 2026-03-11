import React, { useState, useEffect } from "react";
import { getConfig, updateConfig } from "../services/api";

export default function Settings() {
  const [form, setForm] = useState({
    polymarket_api_key: "",
    polymarket_wallet_address: "",
    polymarket_private_key: "",
    telegram_bot_token: "",
    telegram_chat_id: "",
    telegram_enabled: true,
    default_dry_run: true,
    default_amount_usd: 5,
    environment: "dev",
  });

  const [showApiKey, setShowApiKey] = useState(false);
  const [showPrivateKey, setShowPrivateKey] = useState(false);
  const [showTelegramToken, setShowTelegramToken] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null); // { type: "success"|"error", message }
  const [loaded, setLoaded] = useState(false);

  // ── Load config on mount ───────────────────────────────
  useEffect(() => {
    getConfig()
      .then((cfg) => {
        setForm((prev) => ({ ...prev, ...cfg }));
        setLoaded(true);
      })
      .catch((err) => {
        setToast({ type: "error", message: err.message });
        setLoaded(true);
      });
  }, []);

  // ── Auto-dismiss toast ─────────────────────────────────
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const handleChange = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      // Only send fields that have changed (non-masked, non-empty)
      const payload = {};
      for (const [k, v] of Object.entries(form)) {
        // Don't send masked values back
        if (typeof v === "string" && v.includes("****")) continue;
        if (v !== "" && v !== null && v !== undefined) {
          payload[k] = v;
        }
      }
      await updateConfig(payload);
      setToast({ type: "success", message: "Settings saved successfully!" });
    } catch (err) {
      setToast({ type: "error", message: err.message });
    } finally {
      setSaving(false);
    }
  };

  // ── Styling helpers ────────────────────────────────────
  const inputCls =
    "w-full rounded-lg border border-surface-600 bg-surface-800 px-4 py-2.5 text-sm text-surface-100 placeholder-surface-500 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500 transition-colors";
  const labelCls = "block text-xs font-medium text-surface-300 mb-1.5";

  const EyeToggle = ({ show, onToggle }) => (
    <button type="button" onClick={onToggle} className="absolute right-3 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-200 transition-colors" aria-label={show ? "Hide" : "Show"}>
      {show ? (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878L21 21" />
        </svg>
      ) : (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
        </svg>
      )}
    </button>
  );

  if (!loaded) {
    return (
      <div className="flex items-center justify-center py-32">
        <svg className="h-8 w-8 animate-spin text-brand-500" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight text-surface-50">Settings</h1>
        <p className="mt-1 text-sm text-surface-400">Configure API keys, Telegram, and default bot parameters</p>
      </div>

      {/* Toast */}
      {toast && (
        <div
          className={`rounded-xl border px-4 py-3 text-sm transition-all ${
            toast.type === "success"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
              : "border-red-500/30 bg-red-500/10 text-red-300"
          }`}
        >
          {toast.type === "success" ? "✅" : "⚠️"} {toast.message}
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* Polymarket section */}
        <div className="rounded-2xl border border-surface-700 bg-surface-900/60 p-6">
          <h2 className="mb-5 text-base font-bold text-surface-200 flex items-center gap-2">
            <span className="text-lg">🔗</span> Polymarket
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="relative">
              <label className={labelCls} htmlFor="polymarket_api_key">API Key</label>
              <input
                id="polymarket_api_key"
                className={inputCls}
                type={showApiKey ? "text" : "password"}
                value={form.polymarket_api_key}
                onChange={(e) => handleChange("polymarket_api_key", e.target.value)}
                placeholder="pk_..."
              />
              <EyeToggle show={showApiKey} onToggle={() => setShowApiKey(!showApiKey)} />
            </div>
            <div>
              <label className={labelCls} htmlFor="polymarket_wallet_address">Wallet Address</label>
              <input
                id="polymarket_wallet_address"
                className={inputCls}
                value={form.polymarket_wallet_address}
                onChange={(e) => handleChange("polymarket_wallet_address", e.target.value)}
                placeholder="0x..."
              />
            </div>
            <div className="relative sm:col-span-2">
              <label className={labelCls} htmlFor="polymarket_private_key">Private Key</label>
              <input
                id="polymarket_private_key"
                className={inputCls}
                type={showPrivateKey ? "text" : "password"}
                value={form.polymarket_private_key}
                onChange={(e) => handleChange("polymarket_private_key", e.target.value)}
                placeholder="••••••••"
              />
              <EyeToggle show={showPrivateKey} onToggle={() => setShowPrivateKey(!showPrivateKey)} />
            </div>
          </div>
        </div>

        {/* Telegram section */}
        <div className="rounded-2xl border border-surface-700 bg-surface-900/60 p-6">
          <h2 className="mb-5 text-base font-bold text-surface-200 flex items-center gap-2">
            <span className="text-lg">📬</span> Telegram
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="relative">
              <label className={labelCls} htmlFor="telegram_bot_token">Bot Token</label>
              <input
                id="telegram_bot_token"
                className={inputCls}
                type={showTelegramToken ? "text" : "password"}
                value={form.telegram_bot_token}
                onChange={(e) => handleChange("telegram_bot_token", e.target.value)}
                placeholder="123456789:ABC..."
              />
              <EyeToggle show={showTelegramToken} onToggle={() => setShowTelegramToken(!showTelegramToken)} />
            </div>
            <div>
              <label className={labelCls} htmlFor="telegram_chat_id">Chat ID</label>
              <input
                id="telegram_chat_id"
                className={inputCls}
                value={form.telegram_chat_id}
                onChange={(e) => handleChange("telegram_chat_id", e.target.value)}
                placeholder="-1001234567890"
              />
            </div>
          </div>
          <label className="mt-4 flex cursor-pointer items-center gap-3" htmlFor="telegram_enabled">
            <div className="relative">
              <input id="telegram_enabled" type="checkbox" checked={form.telegram_enabled} onChange={(e) => handleChange("telegram_enabled", e.target.checked)} className="sr-only peer" />
              <div className="h-6 w-11 rounded-full bg-surface-600 peer-checked:bg-brand-500 transition-colors" />
              <div className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform peer-checked:translate-x-5" />
            </div>
            <span className="text-sm font-medium text-surface-300">Enable Telegram alerts</span>
          </label>
        </div>

        {/* Defaults section */}
        <div className="rounded-2xl border border-surface-700 bg-surface-900/60 p-6">
          <h2 className="mb-5 text-base font-bold text-surface-200 flex items-center gap-2">
            <span className="text-lg">⚙️</span> Defaults
          </h2>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className={labelCls} htmlFor="default_amount_usd">Default Amount (USD)</label>
              <input
                id="default_amount_usd"
                className={inputCls}
                type="number"
                step="0.01"
                min="0.01"
                value={form.default_amount_usd}
                onChange={(e) => handleChange("default_amount_usd", Number(e.target.value))}
              />
            </div>
            <div>
              <label className={labelCls} htmlFor="environment">Environment</label>
              <select
                id="environment"
                className={inputCls}
                value={form.environment}
                onChange={(e) => handleChange("environment", e.target.value)}
              >
                <option value="dev">Development</option>
                <option value="prod">Production</option>
              </select>
            </div>
            <div className="flex items-end pb-1">
              <label className="flex cursor-pointer items-center gap-3" htmlFor="default_dry_run">
                <div className="relative">
                  <input id="default_dry_run" type="checkbox" checked={form.default_dry_run} onChange={(e) => handleChange("default_dry_run", e.target.checked)} className="sr-only peer" />
                  <div className="h-6 w-11 rounded-full bg-surface-600 peer-checked:bg-amber-500 transition-colors" />
                  <div className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform peer-checked:translate-x-5" />
                </div>
                <span className="text-sm font-medium text-surface-300">Default Dry-Run</span>
              </label>
            </div>
          </div>
        </div>

        {/* Save button */}
        <button
          id="btn-save-settings"
          type="submit"
          disabled={saving}
          className="w-full rounded-xl bg-gradient-to-r from-brand-600 to-brand-500 px-6 py-3.5 text-sm font-bold text-white shadow-lg shadow-brand-500/25 transition-all hover:shadow-brand-500/40 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Saving…
            </span>
          ) : (
            "💾 Save Settings"
          )}
        </button>
      </form>
    </div>
  );
}
