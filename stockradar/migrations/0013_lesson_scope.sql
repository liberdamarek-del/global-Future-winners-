-- 0013_lesson_scope.sql — v0.17.24 (N-34): rozsah platnosti poučení.
-- Poučení se nepřepisují (§30), ale mohou popisovat starý model nebo jiné řazení. 17. 11. 2026 ukazovalo centrum u 73 a
-- 36 firem poučení #13 a #19 o čistém skóre raket, zatímco kandidáti se řadí pravidlem vydrzi_asym s opačným profilem
-- propadů. Rozsah se zapisuje jako nový záznam (jen přidávání); platí poslední záznam k poučení.
CREATE TABLE lesson_scope (
    id             INTEGER PRIMARY KEY,
    lesson_id      INTEGER NOT NULL REFERENCES lessons(id),
    stav           TEXT NOT NULL CHECK (stav IN ('PLATI', 'MIMO_ROZSAH', 'NAHRAZENO')),
    plati_pro_json TEXT CHECK (plati_pro_json IS NULL OR json_valid(plati_pro_json)),  -- {"model": "RAKETY_6M", "razeni": "raketa"}
    nahrazeno_id   INTEGER REFERENCES lessons(id),
    duvod          TEXT NOT NULL,
    source         TEXT,
    recorded_at    TEXT NOT NULL
);
CREATE INDEX ix_lesson_scope_lesson ON lesson_scope(lesson_id, id);
CREATE TRIGGER lesson_scope_no_update BEFORE UPDATE ON lesson_scope
BEGIN
    SELECT RAISE(ABORT, 'rozsah poučení je historický záznam — přidej nový');
END;
CREATE TRIGGER lesson_scope_no_delete BEFORE DELETE ON lesson_scope
BEGIN
    SELECT RAISE(ABORT, 'rozsah poučení se nemaže');
END;
