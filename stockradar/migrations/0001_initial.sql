-- 0001_initial.sql — Fáze 1: databáze + projektový stav (v0.1.0)
--
-- Konvence:
--   * časy:  ISO 8601 UTC 'YYYY-MM-DDTHH:MM:SSZ'
--   * data:  'YYYY-MM-DD'
--   * hodnota 'NEOVERENO' se v UI zobrazuje jako 'NEOVĚŘENO'
--
-- Pravidla MASTER PROMPTu vynucená přímo v databázi (nejdou obejít ani ručním SQL):
--   §10  přesné datum katalyzátoru smí mít jen VERIFIED (se zdrojem); odhad = okno, ne datum
--   §29  prediction ledger je append-only (UPDATE/DELETE zakázán)
--   §5   spekulativní BUY / MAIN PICK vyžaduje XTB kontrolu se stavem ANO pro daný listing
--   §34  každá změna verdiktu/kategorie/statusu má povinný důvod a je trvale zapsaná
--   §60  firmy se nemažou; delisting/převzetí/změna tickeru se eviduje (survivorship bias)

CREATE TABLE companies (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE CHECK (length(trim(name)) > 0),
    country         TEXT,
    sector          TEXT,
    industry        TEXT,
    listing_status  TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (listing_status IN ('ACTIVE','PRE_IPO','PRIVATE','DELISTED',
                                              'BANKRUPT','ACQUIRED','MERGED','UNKNOWN')),
    radar_status    TEXT NOT NULL DEFAULT 'NEOVERENO'
                    CHECK (radar_status IN ('ACTIVE','WATCH','WAIT','TOO_LATE','REJECT',
                                            'REFERENCE','REMOVED','NEOVERENO')),
    category        TEXT CHECK (category IN ('A+','A','B','C','D','E','NEOVERENO')),
    verdict         TEXT CHECK (verdict IN ('SPEC_BUY','WATCH','HOLD','NEKUPOVAT','TOO_LATE','AVOID')),
    notes           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TRIGGER companies_no_delete BEFORE DELETE ON companies
BEGIN
    SELECT RAISE(ABORT, '§60: firmy se nemažou — nastav listing_status / radar_status');
END;

-- Jedna firma může mít více listingů (např. ASX + Nasdaq ADS) a ticker se může v čase měnit.
CREATE TABLE listings (
    id              INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(id),
    ticker          TEXT NOT NULL CHECK (length(trim(ticker)) > 0),
    exchange        TEXT NOT NULL CHECK (length(trim(exchange)) > 0),
    currency        TEXT,
    security_type   TEXT NOT NULL DEFAULT 'COMMON'
                    CHECK (security_type IN ('COMMON','ADR','ADS','PREFERRED','OTHER')),
    is_primary      INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    valid_from      TEXT,
    valid_to        TEXT,
    created_at      TEXT NOT NULL,
    CHECK (valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to)
);
CREATE UNIQUE INDEX ux_listings_ticker ON listings(ticker, exchange, COALESCE(valid_from, ''));

-- §5: historie kontrol dostupnosti na XTB. Platí poslední kontrola daného listingu.
-- instruments = čárkou oddělené hodnoty z {STOCK, CFD, ETF, OTHER} (skutečná akcie vs CFD vs jiné).
CREATE TABLE xtb_checks (
    id              INTEGER PRIMARY KEY,
    listing_id      INTEGER NOT NULL REFERENCES listings(id),
    status          TEXT NOT NULL CHECK (status IN ('ANO','NE','NEOVERENO')),
    instruments     TEXT,
    xtb_symbol      TEXT,
    source          TEXT NOT NULL CHECK (length(trim(source)) > 0),
    note            TEXT,
    checked_at      TEXT NOT NULL,
    CHECK (status <> 'ANO' OR (instruments IS NOT NULL AND length(trim(instruments)) > 0))
);
CREATE INDEX ix_xtb_checks_listing ON xtb_checks(listing_id, checked_at);

CREATE TRIGGER xtb_checks_no_update BEFORE UPDATE ON xtb_checks
BEGIN
    SELECT RAISE(ABORT, 'xtb_checks jsou historie — zapiš novou kontrolu místo úpravy staré');
END;
CREATE TRIGGER xtb_checks_no_delete BEFORE DELETE ON xtb_checks
BEGIN
    SELECT RAISE(ABORT, 'xtb_checks jsou historie — nelze mazat');
END;

CREATE TABLE catalyst_types (
    code   TEXT PRIMARY KEY,
    label  TEXT NOT NULL
);
INSERT INTO catalyst_types (code, label) VALUES
    ('FDA_DECISION',        'FDA rozhodnutí (PDUFA apod.)'),
    ('REGULATORY_OTHER',    'EMA/CHMP/PMDA/NMPA nebo jiný regulatorní krok'),
    ('CLINICAL_DATA',       'Klinická data'),
    ('EARNINGS',            'Výsledky'),
    ('GUIDANCE',            'Guidance'),
    ('CONTRACT',            'Nový kontrakt'),
    ('GOVERNMENT_CONTRACT', 'Vládní zakázka'),
    ('PRODUCT_LAUNCH',      'Nový produkt'),
    ('PROJECT_APPROVAL',    'Schválení projektu'),
    ('PARTNERSHIP',         'Zásadní partnerství'),
    ('M_AND_A',             'Akvizice / fúze'),
    ('IPO',                 'IPO / listing'),
    ('SPIN_OFF',            'Spin-off / demerger'),
    ('TECH_DEMO',           'Technologická demonstrace'),
    ('PRODUCTION_START',    'Výrobní start'),
    ('NEW_CUSTOMER',        'Nový zákazník'),
    ('PRODUCTION_UPDATE',   'Zásadní oznámení o produkci'),
    ('REGULATION_CHANGE',   'Změna regulace'),
    ('MACRO',               'Makro rozhodnutí ovlivňující sektor'),
    ('OTHER',               'Jiné');

-- §10 + §59: katalyzátor. published_at = kdy byla informace veřejně dostupná (look-ahead ochrana).
CREATE TABLE catalysts (
    id              INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies(id),
    type_code       TEXT NOT NULL REFERENCES catalyst_types(code),
    description     TEXT NOT NULL CHECK (length(trim(description)) > 0),
    date_status     TEXT NOT NULL CHECK (date_status IN ('VERIFIED','ESTIMATED','UNCERTAIN','NEOVERENO')),
    event_date      TEXT,
    window_start    TEXT,
    window_end      TEXT,
    status          TEXT NOT NULL DEFAULT 'UPCOMING'
                    CHECK (status IN ('UPCOMING','IN_PROGRESS','OCCURRED','DELAYED','CANCELLED','SUPERSEDED')),
    superseded_by   INTEGER REFERENCES catalysts(id),
    source          TEXT,
    source_url      TEXT,
    published_at    TEXT NOT NULL,
    recorded_at     TEXT NOT NULL,
    -- přesné datum <=> VERIFIED; VERIFIED musí mít zdroj a nemá okno
    CHECK ((date_status = 'VERIFIED') = (event_date IS NOT NULL)),
    CHECK (date_status <> 'VERIFIED'
           OR (source IS NOT NULL AND length(trim(source)) > 0 AND window_start IS NULL AND window_end IS NULL)),
    -- odhad (měsíc/kvartál/období) = okno od-do, nikdy přesné datum
    CHECK (date_status NOT IN ('ESTIMATED','UNCERTAIN')
           OR (window_start IS NOT NULL AND window_end IS NOT NULL AND window_start <= window_end)),
    CHECK (date_status <> 'NEOVERENO' OR (window_start IS NULL AND window_end IS NULL)),
    CHECK ((status = 'SUPERSEDED') = (superseded_by IS NOT NULL))
);
CREATE INDEX ix_catalysts_company ON catalysts(company_id);

-- Obsah katalyzátoru se nepřepisuje. Posun termínu = nový záznam + starý SUPERSEDED.
CREATE TRIGGER catalysts_immutable_content
BEFORE UPDATE OF company_id, type_code, description, date_status, event_date, window_start,
                 window_end, source, source_url, published_at, recorded_at ON catalysts
BEGIN
    SELECT RAISE(ABORT, '§10: obsah katalyzátoru nelze přepsat — vytvoř nový záznam a starý označ SUPERSEDED');
END;
CREATE TRIGGER catalysts_no_delete BEFORE DELETE ON catalysts
BEGIN
    SELECT RAISE(ABORT, 'katalyzátory se nemažou — nastav status CANCELLED/SUPERSEDED');
END;

-- §28 + §29: PREDICTION LEDGER (append-only).
CREATE TABLE predictions (
    id                    INTEGER PRIMARY KEY,
    mode                  TEXT NOT NULL CHECK (mode IN ('LIVE','BACKTEST')),
    made_at               TEXT NOT NULL,
    recorded_at           TEXT NOT NULL,
    company_id            INTEGER NOT NULL REFERENCES companies(id),
    listing_id            INTEGER NOT NULL REFERENCES listings(id),
    horizon               TEXT NOT NULL CHECK (horizon IN ('D0_14','D15_45','M6_PLUS')),
    -- §3: cena != market cap
    price                 REAL NOT NULL CHECK (price > 0),
    currency              TEXT NOT NULL,
    price_as_of           TEXT NOT NULL,
    price_source          TEXT NOT NULL CHECK (length(trim(price_source)) > 0),
    price_freshness       TEXT NOT NULL CHECK (price_freshness IN ('FRESH','STALE')),
    market_cap            REAL CHECK (market_cap > 0),
    market_cap_currency   TEXT,
    -- katalyzátor zkopírovaný v okamžiku predikce (pozdější změna katalyzátoru predikci nemění)
    catalyst_id           INTEGER REFERENCES catalysts(id),
    catalyst_text         TEXT,
    catalyst_date_text    TEXT,
    catalyst_date_status  TEXT CHECK (catalyst_date_status IN ('VERIFIED','ESTIMATED','UNCERTAIN','NEOVERENO')),
    -- §21 + §37
    category              TEXT NOT NULL CHECK (category IN ('A+','A','B','C','D','E','NEOVERENO')),
    verdict               TEXT NOT NULL CHECK (verdict IN ('SPEC_BUY','WATCH','HOLD','NEKUPOVAT','TOO_LATE','AVOID')),
    is_main_pick          INTEGER NOT NULL DEFAULT 0 CHECK (is_main_pick IN (0,1)),
    -- §5: stav XTB převzatý z xtb_checks v okamžiku predikce
    xtb_check_id          INTEGER REFERENCES xtb_checks(id),
    xtb_status            TEXT NOT NULL CHECK (xtb_status IN ('ANO','NE','NEOVERENO')),
    xtb_instruments       TEXT,
    -- §19: pravděpodobnost a velikost pohybu jsou oddělené veličiny
    probability_pct       REAL CHECK (probability_pct BETWEEN 0 AND 100),
    bull_move_pct         REAL,
    base_move_pct         REAL,
    bear_move_pct         REAL,
    bull_case             TEXT,
    base_case             TEXT,
    bear_case             TEXT,
    key_risk              TEXT,
    rationale             TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
    -- §20: vícerozměrné skóre 0–100. U *_risk platí: 100 = nejvyšší riziko.
    score_fundament         INTEGER CHECK (score_fundament BETWEEN 0 AND 100),
    score_catalyst          INTEGER CHECK (score_catalyst BETWEEN 0 AND 100),
    score_catalyst_timing   INTEGER CHECK (score_catalyst_timing BETWEEN 0 AND 100),
    score_upside            INTEGER CHECK (score_upside BETWEEN 0 AND 100),
    score_surprise          INTEGER CHECK (score_surprise BETWEEN 0 AND 100),
    score_financial_health  INTEGER CHECK (score_financial_health BETWEEN 0 AND 100),
    score_valuation         INTEGER CHECK (score_valuation BETWEEN 0 AND 100),
    score_technical         INTEGER CHECK (score_technical BETWEEN 0 AND 100),
    score_dilution_risk     INTEGER CHECK (score_dilution_risk BETWEEN 0 AND 100),
    score_execution_risk    INTEGER CHECK (score_execution_risk BETWEEN 0 AND 100),
    score_rocket            INTEGER CHECK (score_rocket BETWEEN 0 AND 100),
    score_overall_setup     INTEGER CHECK (score_overall_setup BETWEEN 0 AND 100),
    model_version         TEXT NOT NULL,
    -- živá predikce nesmí být zpětně datovaná
    CHECK (mode = 'BACKTEST' OR made_at = recorded_at),
    CHECK (price_as_of <= made_at),
    CHECK (bull_move_pct IS NULL OR bear_move_pct IS NULL OR bull_move_pct >= bear_move_pct)
);
CREATE INDEX ix_predictions_company ON predictions(company_id, made_at);

CREATE TRIGGER predictions_no_update BEFORE UPDATE ON predictions
BEGIN
    SELECT RAISE(ABORT, '§29: prediction ledger je append-only — historickou predikci nelze měnit');
END;
CREATE TRIGGER predictions_no_delete BEFORE DELETE ON predictions
BEGIN
    SELECT RAISE(ABORT, '§29: prediction ledger je append-only — historickou predikci nelze smazat');
END;

-- §5 + poučení XSPRAY: bez ověřené dostupnosti na XTB žádné doporučení.
CREATE TRIGGER predictions_xtb_gate BEFORE INSERT ON predictions
WHEN (NEW.verdict = 'SPEC_BUY' OR NEW.is_main_pick = 1)
 AND (NEW.xtb_status <> 'ANO'
      OR NOT EXISTS (SELECT 1 FROM xtb_checks x
                     WHERE x.id = NEW.xtb_check_id
                       AND x.listing_id = NEW.listing_id
                       AND x.status = 'ANO'
                       AND x.checked_at <= NEW.made_at))
BEGIN
    SELECT RAISE(ABORT, '§5: spekulativní BUY / MAIN PICK vyžaduje ověřenou dostupnost na XTB (stav ANO)');
END;

-- §28 druhá tabulka + §30: vyhodnocení predikce. Také append-only.
CREATE TABLE prediction_outcomes (
    id              INTEGER PRIMARY KEY,
    prediction_id   INTEGER NOT NULL REFERENCES predictions(id),
    horizon_days    INTEGER NOT NULL CHECK (horizon_days > 0),
    observed_at     TEXT NOT NULL,
    price           REAL NOT NULL CHECK (price > 0),
    price_source    TEXT NOT NULL CHECK (length(trim(price_source)) > 0),
    max_price       REAL CHECK (max_price > 0),
    min_price       REAL CHECK (min_price > 0),
    return_pct      REAL NOT NULL,
    result          TEXT NOT NULL CHECK (result IN ('HIT','PARTIAL','MISS','INVALIDATED','NEOVERENO')),
    deviation       TEXT,
    reason          TEXT,
    lesson          TEXT,
    recorded_at     TEXT NOT NULL,
    UNIQUE (prediction_id, horizon_days),
    CHECK (min_price IS NULL OR max_price IS NULL OR min_price <= max_price)
);

CREATE TRIGGER prediction_outcomes_no_update BEFORE UPDATE ON prediction_outcomes
BEGIN
    SELECT RAISE(ABORT, '§30: vyhodnocení se nepřepisuje — nikdy nepřepisuj historii');
END;
CREATE TRIGGER prediction_outcomes_no_delete BEFORE DELETE ON prediction_outcomes
BEGIN
    SELECT RAISE(ABORT, '§30: vyhodnocení se nemaže — nikdy nepřepisuj historii');
END;

-- §34: MĚNÍM VERDIKT — trvalý záznam každé změny s povinným důvodem.
CREATE TABLE status_changes (
    id          INTEGER PRIMARY KEY,
    company_id  INTEGER NOT NULL REFERENCES companies(id),
    field       TEXT NOT NULL CHECK (field IN ('category','verdict','radar_status')),
    old_value   TEXT,
    new_value   TEXT NOT NULL,
    reason      TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    source      TEXT,
    changed_at  TEXT NOT NULL
);
CREATE INDEX ix_status_changes_company ON status_changes(company_id, changed_at);

CREATE TRIGGER status_changes_no_update BEFORE UPDATE ON status_changes
BEGIN
    SELECT RAISE(ABORT, '§34: historie verdiktů se nepřepisuje');
END;
CREATE TRIGGER status_changes_no_delete BEFORE DELETE ON status_changes
BEGIN
    SELECT RAISE(ABORT, '§34: historie verdiktů se nemaže');
END;

-- §30 + §31: učební případy a poučení (append-only).
CREATE TABLE lessons (
    id                INTEGER PRIMARY KEY,
    case_key          TEXT NOT NULL UNIQUE,
    company_id        INTEGER REFERENCES companies(id),
    prediction_id     INTEGER REFERENCES predictions(id),
    title             TEXT NOT NULL,
    outcome_type      TEXT NOT NULL CHECK (outcome_type IN ('HIT','MISS','PROCESS_ERROR','WATCH','REFERENCE')),
    summary           TEXT NOT NULL,
    lessons_json      TEXT NOT NULL CHECK (json_valid(lessons_json) AND json_type(lessons_json) = 'array'),
    model_correction  TEXT,
    source            TEXT NOT NULL CHECK (length(trim(source)) > 0),
    recorded_at       TEXT NOT NULL
);

CREATE TRIGGER lessons_no_update BEFORE UPDATE ON lessons
BEGIN
    SELECT RAISE(ABORT, '§30: poučení se nepřepisují — přidej nové');
END;
CREATE TRIGGER lessons_no_delete BEFORE DELETE ON lessons
BEGIN
    SELECT RAISE(ABORT, '§30: poučení se nemažou');
END;

-- §53: historický snapshot stavu radaru.
CREATE TABLE snapshots (
    id           INTEGER PRIMARY KEY,
    taken_at     TEXT NOT NULL,
    label        TEXT,
    app_version  TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json))
);

CREATE TRIGGER snapshots_no_update BEFORE UPDATE ON snapshots
BEGIN
    SELECT RAISE(ABORT, '§53: snapshot je historický záznam — nelze měnit');
END;
CREATE TRIGGER snapshots_no_delete BEFORE DELETE ON snapshots
BEGIN
    SELECT RAISE(ABORT, '§53: snapshot je historický záznam — nelze mazat');
END;
