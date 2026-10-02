# CHANGELOG (§49)

Formát: Datum · Verze · Soubor/modul · Změna · Důvod · Test · Výsledek

---

## 2026-10-02 · v0.1.0 — Fáze 1: databáze + projektový stav

| Soubor/modul | Změna | Důvod |
|---|---|---|
| `docs/MASTER_PROMPT.md` | Doslovně uložená specifikace projektu | §56, §71: zadání nesmí žít jen v chatu |
| `stockradar/migrations/0001_initial.sql` | Schéma: companies, listings, xtb_checks, catalysts, predictions, prediction_outcomes, status_changes, lessons, snapshots | §62 Fáze 1 |
| — | DB triggery: ledger, vyhodnocení, historie verdiktů, poučení a snapshoty jsou append-only | §29, §30, §34, §53 |
| — | DB trigger `predictions_xtb_gate`: spekulativní BUY / MAIN PICK jen s XTB kontrolou = ANO | §5, poučení XSPRAY |
| — | CHECK: přesné datum katalyzátoru jen u VERIFIED se zdrojem; odhad = okno | §10, §32 |
| — | Firmy nelze smazat; listing_status + historie tickerů | §60 survivorship bias |
| `stockradar/ledger.py` | Zápis predikcí a vyhodnocení; zákaz BUY na proběhlém/probíhajícím katalyzátoru; look-ahead kontrola; FRESH/STALE cena; XTB kontrola max. 30 dní stará | §2, §5, §19, §28, §52, §59, poučení RARE |
| `stockradar/companies.py`, `catalysts.py`, `lessons.py`, `snapshots.py`, `data_quality.py` | Doménové moduly | §10, §30, §31, §34, §52, §53 |
| `stockradar/state_io.py` | `state/*.jsonl` v gitu jako zdroj pravdy, DB je obnovitelná pracovní kopie | §56 |
| `stockradar/cli.py` | Příkazy init / status / ledger / lessons / snapshot / export / restore / seed-lessons | §54 (základ) |
| `state/` | Založeno 9 učebních případů z §31 + počáteční snapshot; žádné vymyšlené predikce | §31, §71 |

**Test:** `python -m pytest` — 53 testů (unit 48, integrační 4, end-to-end 1).
**Výsledek:** 53/53 prošlo.
