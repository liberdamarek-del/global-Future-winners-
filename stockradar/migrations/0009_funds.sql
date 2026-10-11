-- 0009_funds.sql — v0.12.0: nejsilnější sázky fondů (SEC 13F, výzkum E4). Běh = studie událostí + aktuální seznam.
CREATE TABLE fund_runs (
    id            INTEGER PRIMARY KEY,
    run_at        TEXT NOT NULL,
    data_through  TEXT NOT NULL,
    period        TEXT NOT NULL,          -- poslední čtvrtletí zpráv 13F v aktuálním seznamu
    result_json   TEXT NOT NULL CHECK (json_valid(result_json)),
    app_version   TEXT NOT NULL
);
CREATE TRIGGER fund_runs_no_update BEFORE UPDATE ON fund_runs
BEGIN
    SELECT RAISE(ABORT, 'běh fondů je historický záznam — nelze měnit');
END;
CREATE TRIGGER fund_runs_no_delete BEFORE DELETE ON fund_runs
BEGIN
    SELECT RAISE(ABORT, 'běh fondů je historický záznam — nelze mazat');
END;
