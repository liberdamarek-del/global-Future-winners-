# CHANGELOG (§49)

Formát: Datum · Verze · Soubor/modul · Změna · Důvod · Test · Výsledek

---

## 2026-10-02 · v0.2.0 — AI → elektřina radar, bezplatná data, samoučící model, denní web

Důvod: zadání uživatele 2026-10-02 (jen bezplatné zdroje, XTB není podmínka, fokus na energii pro AI, jádro, fúzi
a dohody Google; denně aktualizovaný web se starými predikcemi, jejich vyhodnocením a samoučícím modelem).

| Soubor/modul | Změna | Důvod |
|---|---|---|
| `migrations/0002_energy_radar.sql` | Tabulky chain_nodes, company_chain, relationships (append-only), price_bars, sec_*, model_versions, model_runs; benchmark u predikcí a vyhodnocení; zrušen trigger `predictions_xtb_gate` | §24, §25, §53, §58; rozhodnutí uživatele o XTB |
| `config.py`, `ledger.py` | `REQUIRE_XTB_FOR_BUY = False`; vyhodnocení s nadvýnosem vůči S&P 500 | rozhodnutí uživatele; měřitelná predikce |
| `sources/yahoo.py`, `ingest.py` | Bezplatné ceny/objemy/kurzy z Yahoo chart API | jen bezplatné zdroje |
| `universe.py` | 46 firem, 11 článků řetězce, 22 dohod Big Tech a 8 katalyzátorů se zdroji; API pro denní výzkum | výzkum 2026-10-02 |
| `model.py` | 9 faktorů, učení vah z IC (bez look-ahead), kalibrace, test mimo vzorek, verzování vah | §55, §58, §59 |
| `update.py`, `site.py`, `cli.py update` | Denní běh se stavem kroků a daty pro web | §54 |
| `web/index.html` | Webový přehled (artifact, db dokumenty `stav/*`) | zadání uživatele |
| `CLAUDE.md` | Denní úloha a rozhodnutí uživatele | §56 |

**Poznámka k ledgeru:** prvních 5 predikcí (2026-10-02) vzniklo při ostrém běhu během vývoje v0.2.0, ještě před
zvýšením čísla verze — mají `model_version = 0.1.0`, ale počítala je verze vah modelu 1. Ledger je append-only, proto
zůstávají tak, jak byly zapsány.

**Test:** `python -m pytest` — 65 testů (unit 58, integrační 6, end-to-end 1). **Výsledek:** 65/65 prošlo.
Ostrý běh: 53/53 symbolů staženo, model v1, 5 predikcí, data webu ověřena čtením na úrovni `view`.

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
