-- Pet Store Agentic — Phase 1 deterministic-core schema.
-- Schema name is set via POSTGRES_SCHEMA (see .env.example) — "petstore" below
-- matches this project's own database, but nothing here hardcodes it beyond
-- this DDL file itself; application code always reads the schema name from
-- config/env, never assumes it.

CREATE SCHEMA IF NOT EXISTS petstore;

-- ── Catalog ──────────────────────────────────────────────────────────────
-- category: 'supplies' | 'livestock' | 'veterinary' (project.md §2)
CREATE TABLE IF NOT EXISTS petstore.sku (
    sku_id          TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL CHECK (category IN ('supplies', 'livestock', 'veterinary')),
    description     TEXT,
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    is_livestock    BOOLEAN NOT NULL DEFAULT FALSE,
    is_prescription BOOLEAN NOT NULL DEFAULT FALSE,
    species         TEXT,                      -- populated only for livestock SKUs
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS petstore.inventory (
    sku_id          TEXT PRIMARY KEY REFERENCES petstore.sku(sku_id),
    quantity_on_hand INTEGER NOT NULL CHECK (quantity_on_hand >= 0),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Orders ───────────────────────────────────────────────────────────────
-- state values enumerated in petstore/services/order_state.py's OrderState —
-- kept as TEXT + CHECK here rather than a Postgres ENUM so the Python enum
-- stays the single source of truth (adding a state is a one-line Python change
-- plus a migration, not an ALTER TYPE).
CREATE TABLE IF NOT EXISTS petstore.orders (
    order_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id     TEXT NOT NULL,
    state           TEXT NOT NULL CHECK (state IN (
                        'created', 'payment_authorized', 'fulfilling',
                        'shipped', 'delivered', 'cancelled'
                    )),
    subtotal_cents  INTEGER NOT NULL DEFAULT 0,
    tax_cents       INTEGER NOT NULL DEFAULT 0,
    shipping_cents  INTEGER NOT NULL DEFAULT 0,
    total_cents     INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS petstore.order_items (
    order_item_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id        UUID NOT NULL REFERENCES petstore.orders(order_id),
    sku_id          TEXT NOT NULL REFERENCES petstore.sku(sku_id),
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents_at_order INTEGER NOT NULL
);

-- Every transition recorded — the finite state machine's own audit trail.
-- Not required for Phase 1's demo to run, but it's what lets a reader
-- verify "order state transitions" really is a finite, enumerated machine
-- rather than an assertion (project.md §3, deterministic capability table).
CREATE TABLE IF NOT EXISTS petstore.order_state_history (
    id              BIGSERIAL PRIMARY KEY,
    order_id        UUID NOT NULL REFERENCES petstore.orders(order_id),
    from_state      TEXT,
    to_state        TEXT NOT NULL,
    transitioned_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS petstore.shipping_labels (
    order_id        UUID PRIMARY KEY REFERENCES petstore.orders(order_id),
    carrier         TEXT NOT NULL,
    tracking_number TEXT NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON petstore.order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_state_history_order_id ON petstore.order_state_history(order_id);
