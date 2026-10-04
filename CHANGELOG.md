# CHANGELOG (§49)

Formát: Datum · Verze · Soubor/modul · Změna · Důvod · Test · Výsledek

---

## 2026-10-03 · v0.4.0 — Audit, vlastní predikce raket na 6 měsíců, SEC + klinické studie, evidence e-mailu

Důvod: pokyn uživatele 2026-10-03 — projít celý kód (stav, chyby se závažností, plán, diagnostika), zjednodušit web,
samostatně předpovídat firmy s růstem desítek až stovek procent za ~6 měsíců, využít všechny dostupné zdroje,
smí se použít e-mail (ale s evidencí, kolikrát a kde), kód průběžně zlepšovat.

| Soubor/modul | Změna | Důvod |
|---|---|---|
| `docs/AUDIT_2026-10-03.md` | Audit všech modulů: stav, 2× CRITICAL, 5× HIGH, 9× MEDIUM, 6× LOW, plán, diagnostika | pokyn uživatele |
| `migrations/0004_email_rockets.sql` | `email_usage` (nemazatelná, jen navyšovaná evidence), u predikcí cíl / šance na propad / základní četnost | §53, rozhodnutí uživatele |
| `contact.py` | E-mail jen pro www.sec.gov a data.sec.gov, každý pokus se před odesláním zapíše; e-mail mimo git | rozhodnutí uživatele 2026-10-03 |
| `sources/sec.py` | SEC EDGAR: XBRL frames (tržby, zisk, akcie, hotovost), full-index (8-K, 10-Q/K, emise, 13D s datem podání) | fundamenty §5 |
| `sources/clinicaltrials.py` | ClinicalTrials.gov: 18 540 studií fáze 2/3, párování sponzorů s kotovanými firmami | biotech katalyzátory |
| `discovery/fundamentals.py` | Znaky k danému dni bez look-ahead (hodnota kvartálu až od podání 10-Q/10-K) | §41 |
| `discovery/rocket.py` | Model raket na 6 měsíců: panel 352 tis. vzorků, WoE + logistická regrese, test mimo vzorek, 5 řazení, test „bez fundamentů“ | pokyn uživatele |
| `discovery/store.py` | `record_rockets`: predikce raket do ledgeru (cíl +50 %, šance, propad, základní četnost), čerstvá cena, TOO LATE filtr, automatické katalyzátory z klinických studií | §42 |
| `update.py` | **C1** predikce mimo energetický vesmír se vyhodnotí; **C2** rakety podle cíle (HIT/MISS/zatím nerozhodnuto) | audit |
| `discovery/cache.py` | **H2** chyba stahování už nesmaže uloženou historii | audit |
| `site.py`, `web/index.html` | **H1** limit 170 kB kvůli zvětšení na serveru; web 12 → 6 sekcí, rakety nahoře, vítězové jen TOP 10, evidence e-mailu | audit, pokyn uživatele |
| `diag.py`, `cli.py` | `diag`, `email`, `sources`; `status --days 45` | audit (diagnostika) |
| `catalysts.py`, `universe.py`, `model.py`, `yahoo.py`, `config.py`, `news.py`, `engine.py` | M1, M2, L1, L2, L6 | audit |
| `CLAUDE.md` | Nová pravidla e-mailu, diagnostika v denní úloze, sobotní krok „zlepšování“ | pokyn uživatele |

**Výsledek modelu raket (test 2025-07 až 2026-04, 100 205 pozorování):** +50 % do 6 měsíců u 16,7 % všech akcií;
horní 1 % podle „raketa minus propad“ 25,1 % (propad 17,6 % vs 16,0 %, medián +0,3 % vs +1,8 %). Mírná výhoda
v četnosti raket, ne jistá výhoda ve směru → predikce WATCH se šancí na raketu i propad. SEC + studie: AUC 0,7325 vs 0,7307.

**Poznámka k ledgeru:** běh objevování #2 (2026-10-03) spustil kód v0.4.0 ještě před zvýšením čísla verze — jeho
predikce mají `model_version = 0.3.0`. Ledger je append-only, zůstávají tak.

**Test:** `python -m pytest` — 86 testů (unit 78, integrační 7, end-to-end 1). **Výsledek:** 86/86 prošlo.

---

## 2026-10-02 · v0.3.0 — Global Growth Pattern, Winners & Emerging Sector Engine

Důvod: druhé zadání uživatele (docs/MASTER_PROMPT_GROWTH_ENGINE.md) + pokyn „projdi tisíce firem, najdi akcie, které
udělaly desítky procent za týden až 6 měsíců, zjisti co tomu předcházelo a jestli se to dalo předpokládat“.

| Soubor/modul | Změna | Důvod |
|---|---|---|
| `docs/MASTER_PROMPT_GROWTH_ENGINE.md` | Doslovně uložené zadání modulu | §56 |
| `discovery/listings.py` | Globální seznam: Nasdaq screener (USA), JPX xlsx (celé Japonsko), ASX CSV, 24 indexů z Wikipedie → 13 110 firem | §3, jen zdarma |
| `discovery/cache.py`, `download.py` | Kompaktní cache (zlib/array), obnovitelné stahování 5 let cen, 3 dotazy/s | §46 |
| `discovery/winners.py` | Rakety (týden/měsíc/3 m/6 m), zrcadlové propady, vítězové 3/6/12/24 m, fáze TOO LATE | §2, §38 |
| `discovery/features.py`, `study.py` | 17 znaků k T0 bez look-ahead, kontrolní skupina 1:5, lift, logistická regrese, test na celé populaci s kontrolou směru, asymetrie raketa − propad, sektorové vlny, skupiny společného pohybu, vyřazení chybných dat | §6–§14, §41 |
| `discovery/news.py` | Příčiny z titulků Google News (EN s filtrem relevance, JP podle kódu akcie), 14 kategorií, cache | §6, §15 |
| `discovery/engine.py`, `store.py` | Běh, známé případy (percentil 5 dní před raketou), nová IPO, velikostní skupiny; zápis do `discovery_runs`; kandidáti do ledgeru JEN se směrovou výhodou | §42–§47, §55 |
| `migrations/0003_discovery.sql` | `discovery_runs` (append-only), `predictions.source`, `discovery_run_id` | §53 |
| `update.py` | Vyhodnocení predikcí po 7/14/30/90/180/365 dnech | §42 |
| `model.py` | Energetický model jen nad firmami hodnotového řetězce | oddělení modulů |
| `web/index.html`, `site.py` | Sekce Globální objevy, Před raketou, Co předcházelo raketám, Vítězové a sektory, nová IPO; dokument `stav/objevy` | §55 |

**Výsledek prvního běhu:** 12 158 firem z 61 zemí, 374 oborů, 18 653 týdenních raket (≥ +30 %), 829 titulků.
Rakety jsou z cen a objemů předvídatelné jen co do velikosti pohybu, ne směru (viz lekce POUCENI-RAKETY-VOLATILITA)
→ do ledgeru zapsáno 0 kandidátů. Ručně ověřeny 2 mechanismy (ABVX klinická data, SBET krypto treasury).

**Test:** `python -m pytest` — 77 testů (unit 69, integrační 7, end-to-end 1). **Výsledek:** 77/77 prošlo.

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
