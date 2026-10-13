-- 0010_rocket_diary.sql — v0.13.0: raketový deník (rakety za 5 / 10 / 21 obchodních dní + ověřená příčina). Append-only.
-- Jedna epizoda = jedna firma v okně 21 kalendářních dní (týdenní a měsíční raketa téže firmy je stejný příběh).
CREATE TABLE rocket_events (
    id              INTEGER PRIMARY KEY,
    symbol          TEXT NOT NULL,
    name            TEXT,
    detected_on     TEXT NOT NULL,           -- den běhu
    start_day       TEXT NOT NULL,           -- začátek nejdelšího splněného okna
    end_day         TEXT NOT NULL,           -- poslední den ceny
    windows         TEXT NOT NULL,           -- splněná okna, např. "5d,21d"
    move_5d         REAL,
    move_10d        REAL,
    move_21d        REAL,
    price           REAL NOT NULL,
    turnover_usd    REAL,
    market_cap_usd  REAL,
    auto_cause      TEXT,                    -- kód z titulků (AUTO, neověřeno) nebo NULL
    auto_json       TEXT CHECK (auto_json IS NULL OR json_valid(auto_json)),
    recorded_at     TEXT NOT NULL
);
CREATE INDEX ix_rocket_events_symbol ON rocket_events(symbol, end_day);
CREATE TRIGGER rocket_events_no_update BEFORE UPDATE ON rocket_events
BEGIN
    SELECT RAISE(ABORT, 'raketa je historický záznam — nelze měnit');
END;
CREATE TRIGGER rocket_events_no_delete BEFORE DELETE ON rocket_events
BEGIN
    SELECT RAISE(ABORT, 'raketa je historický záznam — nelze mazat');
END;

-- Ověřená příčina (ruční výzkum z primárního zdroje). Nový názor = nový záznam.
CREATE TABLE rocket_causes (
    id              INTEGER PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES rocket_events(id),
    cause_code      TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('OVĚŘENO', 'NEOVĚŘENO')),
    scheduled       INTEGER CHECK (scheduled IS NULL OR scheduled IN (0, 1)),   -- termín znám předem?
    pre_signals     TEXT,                    -- co bylo vidět předem (fakta) nebo NULL
    summary         TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    source          TEXT NOT NULL CHECK (length(trim(source)) > 0),
    source_url      TEXT NOT NULL CHECK (source_url LIKE 'https://%'),
    published_on    TEXT NOT NULL,
    recorded_at     TEXT NOT NULL
);
CREATE TRIGGER rocket_causes_no_update BEFORE UPDATE ON rocket_causes
BEGIN
    SELECT RAISE(ABORT, 'příčina je historický záznam — nový názor = nový záznam');
END;
CREATE TRIGGER rocket_causes_no_delete BEFORE DELETE ON rocket_causes
BEGIN
    SELECT RAISE(ABORT, 'příčina je historický záznam — nelze mazat');
END;
