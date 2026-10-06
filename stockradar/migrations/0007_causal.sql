-- 0007_causal.sql — v0.9.0: kauzální radar (událost → komodita → obory → firmy). Vše append-only.

-- Jeden běh radaru: události, řetězce, scénáře, příležitosti, výsledky historického testu.
CREATE TABLE causal_runs (
    id            INTEGER PRIMARY KEY,
    run_at        TEXT NOT NULL,
    data_through  TEXT NOT NULL,
    result_json   TEXT NOT NULL CHECK (json_valid(result_json)),
    app_version   TEXT NOT NULL
);
CREATE TRIGGER causal_runs_no_update BEFORE UPDATE ON causal_runs
BEGIN
    SELECT RAISE(ABORT, 'běh kauzálního radaru je historický záznam — nelze měnit');
END;
CREATE TRIGGER causal_runs_no_delete BEFORE DELETE ON causal_runs
BEGIN
    SELECT RAISE(ABORT, 'běh kauzálního radaru je historický záznam — nelze mazat');
END;

-- Kauzální predikce: obor (a jeho firmy) se má pohnout daným směrem v daném horizontu kvůli dané události.
-- Vyhodnotí se proti trhu (výnos oboru nad mediánem trhu). Jedna predikce na (den, komodita, obor, horizont).
CREATE TABLE causal_forecasts (
    id             INTEGER PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES causal_runs(id),
    made_at        TEXT NOT NULL,
    price_date     TEXT NOT NULL,
    commodity      TEXT NOT NULL,
    industry       TEXT NOT NULL,
    chain_order    INTEGER,
    direction      INTEGER NOT NULL CHECK (direction IN (-1, 1)),
    horizon_days   INTEGER NOT NULL CHECK (horizon_days > 0),
    expected_move  REAL,
    priced_ratio   REAL,
    evidence       TEXT NOT NULL CHECK (evidence IN ('EMPIRICKY', 'LOGIKA_NEOVERENO', 'EMPIRICKY_I_LOGIKA')),
    score          REAL,
    card_json      TEXT NOT NULL CHECK (json_valid(card_json)),
    UNIQUE (price_date, commodity, industry, horizon_days)
);
CREATE TRIGGER causal_forecasts_no_update BEFORE UPDATE ON causal_forecasts
BEGIN
    SELECT RAISE(ABORT, 'kauzální predikce je historický záznam — nelze měnit');
END;
CREATE TRIGGER causal_forecasts_no_delete BEFORE DELETE ON causal_forecasts
BEGIN
    SELECT RAISE(ABORT, 'kauzální predikce je historický záznam — nelze mazat');
END;

CREATE TABLE causal_outcomes (
    forecast_id    INTEGER PRIMARY KEY REFERENCES causal_forecasts(id),
    evaluated_at   TEXT NOT NULL,
    end_date       TEXT NOT NULL,
    industry_excess REAL NOT NULL,
    hit            INTEGER NOT NULL CHECK (hit IN (0, 1))
);
CREATE TRIGGER causal_outcomes_no_update BEFORE UPDATE ON causal_outcomes
BEGIN
    SELECT RAISE(ABORT, 'vyhodnocení je historický záznam — nelze měnit');
END;
CREATE TRIGGER causal_outcomes_no_delete BEFORE DELETE ON causal_outcomes
BEGIN
    SELECT RAISE(ABORT, 'vyhodnocení je historický záznam — nelze mazat');
END;
