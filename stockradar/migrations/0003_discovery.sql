-- 0003_discovery.sql — v0.3.0: Global Growth Pattern, Winners & Emerging Sector Engine
-- (docs/MASTER_PROMPT_GROWTH_ENGINE.md)

-- Jeden běh globálního objevování: statistika (§7), výsledky (§55 A–E) a koeficienty modelů. Append-only.
CREATE TABLE discovery_runs (
    id            INTEGER PRIMARY KEY,
    run_at        TEXT NOT NULL,
    data_through  TEXT NOT NULL,
    stats_json    TEXT NOT NULL CHECK (json_valid(stats_json)),
    result_json   TEXT NOT NULL CHECK (json_valid(result_json)),
    models_json   TEXT NOT NULL CHECK (json_valid(models_json)),
    app_version   TEXT NOT NULL
);

CREATE TRIGGER discovery_runs_no_update BEFORE UPDATE ON discovery_runs
BEGIN
    SELECT RAISE(ABORT, '§53: běh objevování je historický záznam — nelze měnit');
END;
CREATE TRIGGER discovery_runs_no_delete BEFORE DELETE ON discovery_runs
BEGIN
    SELECT RAISE(ABORT, '§53: běh objevování je historický záznam — nelze mazat');
END;

-- Odkud predikce pochází: energetický model (NULL / 'ENERGY_MODEL') nebo globální objevování ('DISCOVERY').
ALTER TABLE predictions ADD COLUMN source TEXT CHECK (source IS NULL OR source IN ('ENERGY_MODEL','DISCOVERY'));
ALTER TABLE predictions ADD COLUMN discovery_run_id INTEGER REFERENCES discovery_runs(id);
