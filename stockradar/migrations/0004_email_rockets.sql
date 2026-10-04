-- 0004_email_rockets.sql — v0.4.0: evidence použití e-mailu, predikce raket na 6 měsíců
--
-- Rozhodnutí uživatele 2026-10-03: e-mail se smí použít, pokud pomůže (SEC EDGAR ho vyžaduje v hlavičce),
-- ale uživatel musí vědět, kolikrát denně a na jakých stránkách byl použit. Proto každý dotaz s e-mailem
-- zvýší počítadlo (den, server, účel). Záznam se nemaže a počet nejde snížit; exportuje se do state/.
CREATE TABLE email_usage (
    day        TEXT NOT NULL,                        -- YYYY-MM-DD (UTC)
    host       TEXT NOT NULL,                        -- např. data.sec.gov
    purpose    TEXT NOT NULL,                        -- k čemu byl dotaz (např. fundamenty, seznam filingů)
    requests   INTEGER NOT NULL CHECK (requests > 0),
    first_at   TEXT NOT NULL,
    last_at    TEXT NOT NULL,
    PRIMARY KEY (day, host, purpose)
);

CREATE TRIGGER email_usage_no_delete BEFORE DELETE ON email_usage
BEGIN
    SELECT RAISE(ABORT, 'evidence použití e-mailu se nemaže');
END;
CREATE TRIGGER email_usage_no_decrease BEFORE UPDATE ON email_usage
WHEN NEW.requests < OLD.requests OR NEW.day <> OLD.day OR NEW.host <> OLD.host OR NEW.purpose <> OLD.purpose
BEGIN
    SELECT RAISE(ABORT, 'evidenci použití e-mailu lze jen navyšovat');
END;

-- Predikce raket (zdroj DISCOVERY): cíl pohybu (např. +50 % do 6 měsíců), šance na propad a základní četnost
-- (kolik % všech akcií cíl splní) — aby šlo poctivě porovnat predikci s náhodným výběrem.
ALTER TABLE predictions ADD COLUMN target_move_pct REAL;
ALTER TABLE predictions ADD COLUMN p_drop_pct REAL CHECK (p_drop_pct IS NULL OR p_drop_pct BETWEEN 0 AND 100);
ALTER TABLE predictions ADD COLUMN base_rate_pct REAL CHECK (base_rate_pct IS NULL OR base_rate_pct BETWEEN 0 AND 100);
