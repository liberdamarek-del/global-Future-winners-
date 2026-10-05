-- 0006_signals.sql — v0.6.0: signální engine na 14 dní (karta pravděpodobností místo ceny) a přísný protokol testů.

-- Registr vyhodnocení modelů. LOCKED_TEST se pro jednu konfiguraci (config_hash) smí zapsat jen JEDNOU:
-- další běh výsledek jen načte. Počet různých konfigurací na zamčeném testu = počet pokusů (vidět na webu).
CREATE TABLE model_evaluations (
    id             INTEGER PRIMARY KEY,
    model_name     TEXT NOT NULL,
    config_hash    TEXT NOT NULL,
    split          TEXT NOT NULL CHECK (split IN ('VALIDATION','LOCKED_TEST','POST')),
    period_start   TEXT NOT NULL,
    period_end     TEXT NOT NULL,
    n_samples      INTEGER NOT NULL,
    n_independent  INTEGER NOT NULL,
    metrics_json   TEXT NOT NULL CHECK (json_valid(metrics_json)),
    evaluated_at   TEXT NOT NULL,
    app_version    TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_model_eval_locked ON model_evaluations(model_name, config_hash) WHERE split = 'LOCKED_TEST';
CREATE TRIGGER model_evaluations_no_update BEFORE UPDATE ON model_evaluations
BEGIN
    SELECT RAISE(ABORT, 'vyhodnocení modelu je historický záznam — nelze měnit');
END;
CREATE TRIGGER model_evaluations_no_delete BEFORE DELETE ON model_evaluations
BEGIN
    SELECT RAISE(ABORT, 'vyhodnocení modelu je historický záznam — nelze mazat');
END;

-- Jeden běh signálního enginu (souhrn testů, režim, mechanismy). Append-only.
CREATE TABLE signal_runs (
    id            INTEGER PRIMARY KEY,
    run_at        TEXT NOT NULL,
    data_through  TEXT NOT NULL,
    model_name    TEXT NOT NULL,
    config_hash   TEXT NOT NULL,
    result_json   TEXT NOT NULL CHECK (json_valid(result_json)),
    app_version   TEXT NOT NULL
);
CREATE TRIGGER signal_runs_no_update BEFORE UPDATE ON signal_runs
BEGIN
    SELECT RAISE(ABORT, 'běh signálů je historický záznam — nelze měnit');
END;
CREATE TRIGGER signal_runs_no_delete BEFORE DELETE ON signal_runs
BEGIN
    SELECT RAISE(ABORT, 'běh signálů je historický záznam — nelze mazat');
END;

-- Signální karty (i NEVÍM — aby se dalo ověřit, že odmítnutí bylo správné). Append-only, nikdy se nepřepisují.
CREATE TABLE signal_forecasts (
    id              INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES signal_runs(id),
    made_at         TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    name            TEXT,
    price           REAL NOT NULL CHECK (price > 0),
    price_date      TEXT NOT NULL,
    currency        TEXT,
    horizon_days    INTEGER NOT NULL CHECK (horizon_days > 0),
    regime          TEXT,
    p_up            REAL NOT NULL CHECK (p_up BETWEEN 0 AND 1),
    p_down          REAL NOT NULL CHECK (p_down BETWEEN 0 AND 1),
    p_flat          REAL NOT NULL CHECK (p_flat BETWEEN 0 AND 1),
    p_beat_sector   REAL CHECK (p_beat_sector BETWEEN 0 AND 1),
    p_big           REAL CHECK (p_big BETWEEN 0 AND 1),
    expected_move   REAL,
    expected_low    REAL,
    expected_high   REAL,
    confidence      INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    decision        TEXT NOT NULL CHECK (decision IN ('RŮST','POKLES','NEVÍM')),
    card_json       TEXT NOT NULL CHECK (json_valid(card_json)),
    UNIQUE (run_id, symbol)
);
CREATE TRIGGER signal_forecasts_no_update BEFORE UPDATE ON signal_forecasts
BEGIN
    SELECT RAISE(ABORT, 'signální karta je historický záznam — nelze měnit');
END;
CREATE TRIGGER signal_forecasts_no_delete BEFORE DELETE ON signal_forecasts
BEGIN
    SELECT RAISE(ABORT, 'signální karta je historický záznam — nelze mazat');
END;

-- Výsledek karty po horizon_days obchodních dnech. Jeden záznam na kartu, append-only.
CREATE TABLE signal_outcomes (
    forecast_id     INTEGER PRIMARY KEY REFERENCES signal_forecasts(id),
    evaluated_at    TEXT NOT NULL,
    end_date        TEXT NOT NULL,
    end_price       REAL NOT NULL CHECK (end_price > 0),
    ret             REAL NOT NULL,
    sector_ret      REAL,
    up5             INTEGER NOT NULL CHECK (up5 IN (0,1)),
    down5           INTEGER NOT NULL CHECK (down5 IN (0,1)),
    beat_sector     INTEGER CHECK (beat_sector IN (0,1)),
    big             INTEGER NOT NULL CHECK (big IN (0,1)),
    brier           REAL NOT NULL
);
CREATE TRIGGER signal_outcomes_no_update BEFORE UPDATE ON signal_outcomes
BEGIN
    SELECT RAISE(ABORT, 'výsledek karty je historický záznam — nelze měnit');
END;
CREATE TRIGGER signal_outcomes_no_delete BEFORE DELETE ON signal_outcomes
BEGIN
    SELECT RAISE(ABORT, 'výsledek karty je historický záznam — nelze mazat');
END;
