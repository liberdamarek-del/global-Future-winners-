-- 0012_pohyby.sql — v0.17.0: raketový deník sleduje i propady a jednodenní skoky, ke každému pohybu přidá podání u SEC
-- (primární zdroj), měří, co následovalo (5 / 20 / 60 obchodních dní), ukládá historickou studii „co následuje po pohybu“
-- a denní přehled trhu a sektorů. Vše append-only.
-- Zadání uživatele 2026-10-23: analyzovat, proč akcie vyletěla (i +100 % za den) nebo spadla a proč se hýbal sektor.

-- Směr pohybu (+1 raketa, −1 propad), pohyb za jeden den a objem dne proti běžnému. Staré záznamy jsou rakety (+1).
ALTER TABLE rocket_events ADD COLUMN direction INTEGER NOT NULL DEFAULT 1 CHECK (direction IN (1, -1));
ALTER TABLE rocket_events ADD COLUMN move_1d REAL;
ALTER TABLE rocket_events ADD COLUMN rel_volume REAL;      -- objem posledního dne / medián objemu 20 předchozích dní
CREATE INDEX ix_rocket_events_dir ON rocket_events(direction, end_day);

-- Podání u SEC v okně pohybu (EDGAR submissions API, 1 dotaz na firmu): 8-K s čísly bodů (2.02 výsledky, 1.01 smlouva,
-- 3.02 prodej akcií …), 10-Q/10-K, emise, 13D/13G, fúze. Jeden záznam na pohyb; BEZ_CIK = firma není v seznamu SEC
-- (zahraniční, fond) a dotaz se neposlal. Obsah dokumentu se nečte — jen typ podání a odkaz na něj.
CREATE TABLE move_sec (
    id           INTEGER PRIMARY KEY,
    event_id     INTEGER NOT NULL UNIQUE REFERENCES rocket_events(id),
    cik          INTEGER,
    status       TEXT NOT NULL CHECK (status IN ('OK', 'BEZ_CIK')),
    filings_json TEXT NOT NULL CHECK (json_valid(filings_json)),
    checked_at   TEXT NOT NULL
);
CREATE TRIGGER move_sec_no_update BEFORE UPDATE ON move_sec
BEGIN
    SELECT RAISE(ABORT, 'podání k pohybu jsou historický záznam — nelze měnit');
END;
CREATE TRIGGER move_sec_no_delete BEFORE DELETE ON move_sec
BEGIN
    SELECT RAISE(ABORT, 'podání k pohybu jsou historický záznam — nelze mazat');
END;

-- Co následovalo: cena po `horizon` obchodních dnech od posledního dne pohybu, proti S&P 500 (SPY).
CREATE TABLE move_outcomes (
    id              INTEGER PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES rocket_events(id),
    horizon         INTEGER NOT NULL CHECK (horizon IN (5, 20, 60)),
    base_day        TEXT NOT NULL,
    base_price      REAL NOT NULL CHECK (base_price > 0),
    day             TEXT NOT NULL,
    price           REAL NOT NULL CHECK (price > 0),
    return_pct      REAL NOT NULL,
    spy_return_pct  REAL,                        -- NULL, když SPY za to období chybí
    recorded_at     TEXT NOT NULL,
    UNIQUE (event_id, horizon)
);
CREATE TRIGGER move_outcomes_no_update BEFORE UPDATE ON move_outcomes
BEGIN
    SELECT RAISE(ABORT, 'výsledek po pohybu je historický záznam — nelze měnit');
END;
CREATE TRIGGER move_outcomes_no_delete BEFORE DELETE ON move_outcomes
BEGIN
    SELECT RAISE(ABORT, 'výsledek po pohybu je historický záznam — nelze mazat');
END;

-- Historická studie (5 let cen z cache): stejná pravidla jako živý deník, co následovalo po 5 / 20 / 60 dnech podle
-- směru, typu pohybu a podání u SEC. Popis historie, ne předpověď; přepočítává se nejvýš jednou za týden.
CREATE TABLE move_studies (
    id            INTEGER PRIMARY KEY,
    run_at        TEXT NOT NULL,
    data_through  TEXT NOT NULL,
    version       TEXT NOT NULL,
    result_json   TEXT NOT NULL CHECK (json_valid(result_json))
);
CREATE TRIGGER move_studies_no_update BEFORE UPDATE ON move_studies
BEGIN
    SELECT RAISE(ABORT, 'studie je historický záznam — nelze měnit');
END;
CREATE TRIGGER move_studies_no_delete BEFORE DELETE ON move_studies
BEGIN
    SELECT RAISE(ABORT, 'studie je historický záznam — nelze mazat');
END;

-- Denní přehled trhu a sektorů (popis souvislostí, ne prokázané příčiny). Jeden záznam za obchodní den.
CREATE TABLE market_days (
    id          INTEGER PRIMARY KEY,
    day         TEXT NOT NULL UNIQUE,
    result_json TEXT NOT NULL CHECK (json_valid(result_json)),
    recorded_at TEXT NOT NULL
);
CREATE TRIGGER market_days_no_update BEFORE UPDATE ON market_days
BEGIN
    SELECT RAISE(ABORT, 'přehled dne je historický záznam — nelze měnit');
END;
CREATE TRIGGER market_days_no_delete BEFORE DELETE ON market_days
BEGIN
    SELECT RAISE(ABORT, 'přehled dne je historický záznam — nelze mazat');
END;
