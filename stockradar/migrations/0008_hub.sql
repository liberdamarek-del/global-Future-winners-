-- 0008_hub.sql — v0.10.0: paměť a propojení systému (centrum důkazů, deník běhů, integrace). Vše append-only.

-- Ruční výzkum jako trvalý důkaz: ověřená zpráva se zdrojem navázaná na firmu, obor nebo komoditu.
CREATE TABLE research_evidence (
    id            INTEGER PRIMARY KEY,
    entity_type   TEXT NOT NULL CHECK (entity_type IN ('firma', 'obor', 'komodita', 'trh')),
    entity        TEXT NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('prilezitost', 'riziko', 'katalyzator', 'kontext')),
    direction     INTEGER NOT NULL CHECK (direction IN (-1, 0, 1)),
    horizon_days  INTEGER NOT NULL CHECK (horizon_days > 0),
    summary       TEXT NOT NULL,
    source        TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    published_on  TEXT NOT NULL,
    valid_until   TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('OVĚŘENO', 'NEOVĚŘENO')),
    recorded_at   TEXT NOT NULL
);
CREATE TRIGGER research_evidence_no_update BEFORE UPDATE ON research_evidence
BEGIN
    SELECT RAISE(ABORT, 'výzkum je historický záznam — nový názor = nový záznam');
END;
CREATE TRIGGER research_evidence_no_delete BEFORE DELETE ON research_evidence
BEGIN
    SELECT RAISE(ABORT, 'výzkum je historický záznam — nelze mazat');
END;

-- Deník: každý spuštěný příkaz (co, s čím, kdy, jak dopadl, chyba). Paměť toho, co systém udělal a proč.
CREATE TABLE system_runs (
    id            INTEGER PRIMARY KEY,
    command       TEXT NOT NULL,
    args_json     TEXT NOT NULL CHECK (json_valid(args_json)),
    started_at    TEXT NOT NULL,
    finished_at   TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('OK', 'CHYBA', 'PŘESKOČENO')),
    summary_json  TEXT NOT NULL CHECK (json_valid(summary_json)),
    error         TEXT,
    app_version   TEXT NOT NULL
);
CREATE TRIGGER system_runs_no_update BEFORE UPDATE ON system_runs
BEGIN
    SELECT RAISE(ABORT, 'deník je historický záznam — nelze měnit');
END;
CREATE TRIGGER system_runs_no_delete BEFORE DELETE ON system_runs
BEGIN
    SELECT RAISE(ABORT, 'deník je historický záznam — nelze mazat');
END;

-- Integrace: souhrn jednoho běhu centra (spolehlivost rolí, stavy modulů, rozpory, nejsilnější pohledy).
CREATE TABLE hub_runs (
    id            INTEGER PRIMARY KEY,
    run_at        TEXT NOT NULL,
    summary_json  TEXT NOT NULL CHECK (json_valid(summary_json)),
    app_version   TEXT NOT NULL
);
CREATE TRIGGER hub_runs_no_update BEFORE UPDATE ON hub_runs
BEGIN
    SELECT RAISE(ABORT, 'běh centra je historický záznam — nelze měnit');
END;
CREATE TRIGGER hub_runs_no_delete BEFORE DELETE ON hub_runs
BEGIN
    SELECT RAISE(ABORT, 'běh centra je historický záznam — nelze mazat');
END;
