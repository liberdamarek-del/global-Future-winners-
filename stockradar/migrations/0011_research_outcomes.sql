-- 0011_research_outcomes.sql — v0.15.0: vyhodnocení ručního výzkumu proti cenám (dosud se neměřil, role VÝZKUM byla
-- vždy NEOVĚŘENO). Jen směrové záznamy o firmách (riziko ↓ / příležitost ↑) po uplynutí horizontu. Append-only.
CREATE TABLE research_outcomes (
    id                    INTEGER PRIMARY KEY,
    research_id           INTEGER NOT NULL UNIQUE REFERENCES research_evidence(id),
    symbol                TEXT NOT NULL,
    direction             INTEGER NOT NULL CHECK (direction IN (-1, 1)),
    start_day             TEXT NOT NULL,           -- první obchodní den od zveřejnění zprávy
    end_day               TEXT NOT NULL,           -- poslední obchodní den do konce horizontu
    start_price           REAL NOT NULL CHECK (start_price > 0),
    end_price             REAL NOT NULL CHECK (end_price > 0),
    return_pct            REAL NOT NULL,
    benchmark_return_pct  REAL NOT NULL,           -- S&P 500 (SPY) ve stejném období
    excess_return_pct     REAL NOT NULL,
    in_direction_pct      REAL NOT NULL,           -- směr × nadvýnos (kladné = výzkum měl pravdu)
    result                TEXT NOT NULL CHECK (result IN ('HIT', 'MISS')),
    price_source          TEXT NOT NULL,
    recorded_at           TEXT NOT NULL
);
CREATE TRIGGER research_outcomes_no_update BEFORE UPDATE ON research_outcomes
BEGIN
    SELECT RAISE(ABORT, 'vyhodnocení výzkumu je historický záznam — nelze měnit');
END;
CREATE TRIGGER research_outcomes_no_delete BEFORE DELETE ON research_outcomes
BEGIN
    SELECT RAISE(ABORT, 'vyhodnocení výzkumu je historický záznam — nelze mazat');
END;
