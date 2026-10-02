# PROJECT_STATE — zdroj pravdy projektu (§48)

**Aktualizováno:** 2026-10-02 · **Verze:** v0.1.0 · **Schema DB:** v1
**Specifikace:** [docs/MASTER_PROMPT.md](docs/MASTER_PROMPT.md)

> Nikdy nepředpokládej, že modul funguje jen proto, že ho někdo napsal. Stav HOTOVO = existuje test, který prošel.

---

## Historický stav analýz (§71)

| Položka | Stav |
|---|---|
| Repozitář před 2026-10-02 | **Prázdný.** Žádná dřívější databáze, ledger, snapshot ani report v projektu neexistoval. |
| Predikce v ledgeru | **0.** Dřívější predikce z chatů nejsou v projektu doložené, proto nebyly zpětně vytvořeny. |
| Učební případy §31 | 9 případů zapsáno jako poučení (`state/lessons.jsonl`). Obsahují jen to, co je uvedeno v MASTER PROMPTu. |
| Tržní data (ceny, market cap, fundamenty) | **Žádná nejsou načtena.** Nebyl proveden žádný živý screening. |
| XTB dostupnost | U žádné firmy zatím **NEOVĚŘENO**. |
| MAIN PICK | **ŽÁDNÝ.** |

Firmy na radaru (ze §31): CAPR, NBIS, Unitree (ticker neověřen), MRNA, RARE = `REFERENCE` (učební případy);
BEAM, TLX, SLS = `WATCH`; XSPRAY = `NEOVĚŘENO`. Kategorie a verdikt u žádné firmy zatím nejsou stanoveny.

---

## HOTOVO (ověřeno testy — 53 testů, všechny prošly 2026-10-02)

| Modul | Co dělá | Testy |
|---|---|---|
| `stockradar/migrations/0001_initial.sql` | Schéma DB, pravidla MASTER PROMPTu vynucená triggery a CHECK omezeními | `tests/unit/*` |
| `stockradar/db.py` | Připojení SQLite, verzované migrace (`PRAGMA user_version`) | `test_db.py` |
| `stockradar/companies.py` | Firmy, listingy (více burz, historie tickerů), kontroly XTB, změny verdiktu s povinným důvodem (§34) | `test_companies.py` |
| `stockradar/catalysts.py` | Katalyzátory: VERIFIED = přesné datum + zdroj, odhad = okno (§10); posun termínu = nový záznam | `test_catalysts.py` |
| `stockradar/ledger.py` | Append-only prediction ledger (§29), XTB brána (§5), ochrana před honěním proběhlých katalyzátorů (§2), look-ahead ochrana (§59), vyhodnocení +7/+14/+30 d (§28) | `test_ledger.py` |
| `stockradar/data_quality.py` | FRESH / DATA STALE (§52) | `test_data_quality.py` |
| `stockradar/lessons.py` | Učební případy §30/§31, idempotentní seed | `test_lessons.py` |
| `stockradar/snapshots.py` | Historický snapshot stavu radaru (§53) | `test_state_roundtrip.py` |
| `stockradar/state_io.py` | Export/obnova `state/` (JSONL v gitu), detekce neexportovaných změn (§56) | `test_state_roundtrip.py` |
| `stockradar/cli.py` | `init`, `status`, `ledger`, `lessons`, `snapshot`, `export`, `restore`, `seed-lessons` | `tests/end_to_end/test_cli.py` |

## ROZPRACOVÁNO

— nic —

## BLOKOVÁNO

| Co | Proč | Co je potřeba |
|---|---|---|
| Fáze 2–4: import akcií, ceny, fundamenty | Není rozhodnut datový zdroj ani API klíče | Rozhodnutí uživatele o poskytovateli dat (viz ROADMAP.md) |
| Automatická kontrola XTB | Zdroj seznamu instrumentů XTB není ověřen | Zjistit, zda XTB poskytuje strojově čitelný seznam instrumentů; jinak ruční ověření v xStation se zápisem zdroje |

## NEOVĚŘENO

| Co | Poznámka |
|---|---|
| Identita firem §31 | Názvy firem odvozeny z tickerů v MASTER PROMPTu (např. RARE = Ultragenyx). Ověřit při první aktualizaci dat. |
| Výkon DB při tisících firem | Testováno jen na malých datech. |

## DEPRECATED

— nic —

---

## Jak se pracuje se stavem

1. `python -m stockradar init` — vytvoří pracovní DB z `state/` (DB není v gitu).
2. Práce (Python API nebo CLI). Příkazy CLI, které mění data, exportují automaticky.
3. Po práci přes Python API: `python -m stockradar export`.
4. `python -m stockradar status` musí hlásit, že nejsou neexportované změny.
5. Commit `state/` + aktualizace tohoto souboru a `CHANGELOG.md`.
