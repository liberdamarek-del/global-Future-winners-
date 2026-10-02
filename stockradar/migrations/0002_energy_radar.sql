-- 0002_energy_radar.sql — v0.2.0: bezplatná data, hodnotový řetězec AI → elektřina, samoučící model
--
-- Rozhodnutí uživatele 2026-10-02: dostupnost na XTB NENÍ povinná podmínka doporučení.
-- Stav XTB se dál zapisuje (informativně), ale databáze už predikci kvůli němu neodmítne.
DROP TRIGGER predictions_xtb_gate;

-- Symboly pro bezplatné zdroje dat.
ALTER TABLE listings ADD COLUMN yahoo_symbol TEXT;
ALTER TABLE listings ADD COLUMN sec_cik TEXT;

-- §25: hodnotový řetězec (AI → elektřina → jádro/fúze → palivo → síť …).
CREATE TABLE chain_nodes (
    code         TEXT PRIMARY KEY,
    layer        INTEGER NOT NULL,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL,
    horizon      TEXT NOT NULL
);

CREATE TABLE company_chain (
    company_id  INTEGER NOT NULL REFERENCES companies(id),
    node_code   TEXT NOT NULL REFERENCES chain_nodes(code),
    role        TEXT,
    PRIMARY KEY (company_id, node_code)
);

-- §24: kontrakty, investice, akvizice. Rámcová dohoda se nesmí tvářit jako pevná objednávka.
CREATE TABLE relationships (
    id            INTEGER PRIMARY KEY,
    company_id    INTEGER REFERENCES companies(id),   -- veřejná firma v radaru; NULL = soukromá / mimo radar
    party         TEXT NOT NULL,                       -- firma nebo projekt (např. 'Kairos Power')
    counterparty  TEXT NOT NULL,                       -- např. 'Google', 'Meta', 'US DOE'
    rel_type      TEXT NOT NULL CHECK (rel_type IN ('INVESTMENT','PPA','ACQUISITION','DEVELOPMENT_FUNDING',
                                                    'SUPPLY','MERGER','TARIFF_SUBSCRIPTION','PARTNERSHIP',
                                                    'GOVERNMENT_AWARD')),
    binding       TEXT NOT NULL CHECK (binding IN ('FIRM','FRAMEWORK','OPTION','PENDING','NEOVERENO')),
    capacity_mw   REAL CHECK (capacity_mw IS NULL OR capacity_mw > 0),
    amount_usd    REAL CHECK (amount_usd IS NULL OR amount_usd > 0),
    description   TEXT NOT NULL CHECK (length(trim(description)) > 0),
    announced_on  TEXT NOT NULL,                       -- datum oznámení / zdroje (look-ahead ochrana)
    source        TEXT NOT NULL CHECK (length(trim(source)) > 0),
    source_url    TEXT NOT NULL CHECK (source_url LIKE 'https://%'),
    recorded_at   TEXT NOT NULL
);
CREATE INDEX ix_relationships_company ON relationships(company_id);

CREATE TRIGGER relationships_no_update BEFORE UPDATE ON relationships
BEGIN
    SELECT RAISE(ABORT, '§24: vztah se nepřepisuje — zapiš nový záznam (např. změna stavu dohody)');
END;
CREATE TRIGGER relationships_no_delete BEFORE DELETE ON relationships
BEGIN
    SELECT RAISE(ABORT, '§24: vztahy se nemažou');
END;

-- Cache bezplatných dat (NENÍ v state/, kdykoli se dá stáhnout znovu).
CREATE TABLE price_bars (
    symbol      TEXT NOT NULL,
    date        TEXT NOT NULL,
    close       REAL NOT NULL CHECK (close > 0),
    volume      REAL,
    source      TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE sec_filings (
    accession    TEXT PRIMARY KEY,
    cik          TEXT NOT NULL,
    form         TEXT NOT NULL,
    filing_date  TEXT NOT NULL,
    fetched_at   TEXT NOT NULL
);
CREATE INDEX ix_sec_filings_cik ON sec_filings(cik, filing_date);

CREATE TABLE sec_shares (
    cik         TEXT NOT NULL,
    period_end  TEXT NOT NULL,
    filed       TEXT NOT NULL,
    shares      REAL NOT NULL CHECK (shares > 0),
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (cik, period_end, filed)
);

-- §58: samoučící model. Každá změna vah = nová verze s důvodem (nikdy se nepřepisuje).
CREATE TABLE model_versions (
    id                INTEGER PRIMARY KEY,
    created_at        TEXT NOT NULL,
    weights_json      TEXT NOT NULL CHECK (json_valid(weights_json)),
    metrics_json      TEXT NOT NULL CHECK (json_valid(metrics_json)),
    calibration_json  TEXT NOT NULL CHECK (json_valid(calibration_json)),
    training_window   TEXT NOT NULL,
    n_samples         INTEGER NOT NULL,
    reason            TEXT NOT NULL CHECK (length(trim(reason)) > 0)
);

CREATE TRIGGER model_versions_no_update BEFORE UPDATE ON model_versions
BEGIN
    SELECT RAISE(ABORT, '§50: verze modelu se nepřepisuje — vytvoř novou');
END;
CREATE TRIGGER model_versions_no_delete BEFORE DELETE ON model_versions
BEGIN
    SELECT RAISE(ABORT, '§50: verze modelu se nemaže');
END;

-- §53/§54: denní běh — skóre všech firem, stav kroků UPDATE, varování.
CREATE TABLE model_runs (
    id                INTEGER PRIMARY KEY,
    run_at            TEXT NOT NULL,
    data_date         TEXT NOT NULL,
    model_version_id  INTEGER NOT NULL REFERENCES model_versions(id),
    scores_json       TEXT NOT NULL CHECK (json_valid(scores_json)),
    steps_json        TEXT NOT NULL CHECK (json_valid(steps_json)),
    warnings_json     TEXT NOT NULL CHECK (json_valid(warnings_json))
);

CREATE TRIGGER model_runs_no_update BEFORE UPDATE ON model_runs
BEGIN
    SELECT RAISE(ABORT, '§53: běh modelu je historický záznam');
END;
CREATE TRIGGER model_runs_no_delete BEFORE DELETE ON model_runs
BEGIN
    SELECT RAISE(ABORT, '§53: běh modelu je historický záznam');
END;

-- Predikce a vyhodnocení proti benchmarku (S&P 500 = SPY).
ALTER TABLE predictions ADD COLUMN benchmark_symbol TEXT;
ALTER TABLE predictions ADD COLUMN benchmark_price REAL CHECK (benchmark_price IS NULL OR benchmark_price > 0);
ALTER TABLE predictions ADD COLUMN p_rocket_pct REAL CHECK (p_rocket_pct IS NULL OR p_rocket_pct BETWEEN 0 AND 100);
ALTER TABLE predictions ADD COLUMN model_run_id INTEGER REFERENCES model_runs(id);

ALTER TABLE prediction_outcomes ADD COLUMN benchmark_return_pct REAL;
ALTER TABLE prediction_outcomes ADD COLUMN excess_return_pct REAL;
