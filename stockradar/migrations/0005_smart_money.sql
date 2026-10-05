-- 0005_smart_money.sql — v0.5.0: strategie predikce (např. SMART_MONEY = nákupy insiderů)
--
-- Predikce smart money mají source = 'DISCOVERY' (objevování mimo energetický řetězec) a strategy = 'SMART_MONEY'.
-- Tvrzení predikce: „akcie za 6 měsíců porazí S&P 500“ — vyhodnocuje se stejně jako energetický model.
ALTER TABLE predictions ADD COLUMN strategy TEXT CHECK (strategy IS NULL OR strategy IN ('ROCKET_6M', 'SMART_MONEY'));

-- Jeden běh analýzy smart money (historický test + aktuální signály). Append-only.
CREATE TABLE smart_money_runs (
    id            INTEGER PRIMARY KEY,
    run_at        TEXT NOT NULL,
    data_through  TEXT NOT NULL,
    result_json   TEXT NOT NULL CHECK (json_valid(result_json)),
    app_version   TEXT NOT NULL
);
CREATE TRIGGER smart_money_runs_no_update BEFORE UPDATE ON smart_money_runs
BEGIN
    SELECT RAISE(ABORT, 'běh smart money je historický záznam — nelze měnit');
END;
CREATE TRIGGER smart_money_runs_no_delete BEFORE DELETE ON smart_money_runs
BEGIN
    SELECT RAISE(ABORT, 'běh smart money je historický záznam — nelze mazat');
END;
ALTER TABLE predictions ADD COLUMN smart_money_run_id INTEGER REFERENCES smart_money_runs(id);
