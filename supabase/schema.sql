-- ============================================================
-- Polybot Phase 1 — Supabase Schema
-- ============================================================

-- 1. Trades table — one row per order placed (or simulated)
CREATE TABLE IF NOT EXISTS trades (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id      UUID NOT NULL,
    bot_id          TEXT NOT NULL CHECK (bot_id IN ('bot1', 'bot2')),
    market_id       TEXT NOT NULL,
    market_slug     TEXT,
    side            TEXT NOT NULL CHECK (side IN ('UP', 'DOWN')),
    entry_price     NUMERIC(10, 4) NOT NULL,
    exit_price      NUMERIC(10, 4),
    shares          NUMERIC(12, 4) NOT NULL,
    amount_usd      NUMERIC(12, 4) NOT NULL,
    pnl_usd         NUMERIC(12, 4),
    pnl_pct         NUMERIC(8, 4),
    status          TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'WIN', 'LOSS', 'SKIP')),
    signal_score    NUMERIC(6, 4),
    btc_price_entry NUMERIC(14, 2),
    btc_price_exit  NUMERIC(14, 2),
    dry_run         BOOLEAN NOT NULL DEFAULT TRUE,
    trading_mode    TEXT NOT NULL DEFAULT 'paper' CHECK (trading_mode IN ('live', 'paper')),
    error_message   TEXT,
    opened_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Global config table — single row for app-wide settings
CREATE TABLE IF NOT EXISTS global_config (
    id                      SERIAL PRIMARY KEY,
    polymarket_api_key      TEXT,
    polymarket_wallet_address TEXT,
    polymarket_private_key  TEXT,
    telegram_bot_token      TEXT,
    telegram_chat_id        TEXT,
    telegram_enabled        BOOLEAN NOT NULL DEFAULT TRUE,
    default_dry_run         BOOLEAN NOT NULL DEFAULT TRUE,
    default_amount_usd      NUMERIC(12, 4) NOT NULL DEFAULT 5.0,
    environment             TEXT NOT NULL DEFAULT 'dev',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Indexes for performance
CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_bot_id ON trades (bot_id);
CREATE INDEX IF NOT EXISTS idx_trades_session_id ON trades (session_id);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades (status);

-- 4. Updated-at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to both tables
CREATE TRIGGER set_trades_updated_at
    BEFORE UPDATE ON trades
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER set_global_config_updated_at
    BEFORE UPDATE ON global_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 5. Seed global_config with a single default row
INSERT INTO global_config (telegram_enabled, default_dry_run, default_amount_usd, environment)
VALUES (TRUE, TRUE, 5.0, 'dev')
ON CONFLICT DO NOTHING;


-- ============================================================
-- Fix Polybot trades table — add missing columns from Bot1
-- ============================================================
-- Run this in Supabase SQL Editor to add columns that bot1.py needs

-- 1. Add columns if they don't exist (for Bot1 specifically)
ALTER TABLE trades ADD COLUMN IF NOT EXISTS order_id TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS token_id TEXT;
ALTER TABLE trades ADD COLUMN IF NOT EXISTS target_price NUMERIC(10, 4);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS stop_price NUMERIC(10, 4);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS take_profit_cents NUMERIC(6, 4);
ALTER TABLE trades ADD COLUMN IF NOT EXISTS stop_loss_cents NUMERIC(6, 4);

-- 2. Verify all required columns exist
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'trades'
ORDER BY ordinal_position;

-- 3. (Optional) Add comments to document new columns
COMMENT ON COLUMN trades.order_id IS 'Order ID from place_order() or dry-run-simulated';
COMMENT ON COLUMN trades.token_id IS 'Polymarket token ID for this trade (UP or DOWN side)';
COMMENT ON COLUMN trades.target_price IS 'Take-profit exit level (entry_price + take_profit_cents/100)';
COMMENT ON COLUMN trades.stop_price IS 'Stop-loss exit level (entry_price - stop_loss_cents/100)';
COMMENT ON COLUMN trades.take_profit_cents IS 'TP in cents (e.g. 0.11 = 11 cents above entry)';
COMMENT ON COLUMN trades.stop_loss_cents IS 'SL in cents (e.g. 0.25 = 25 cents below entry)';