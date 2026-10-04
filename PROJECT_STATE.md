# PROJECT_STATE — zdroj pravdy projektu (§48)

**Aktualizováno:** 2026-10-03 · **Verze:** v0.4.0 · **Schema DB:** v4 · **Audit:** [docs/AUDIT_2026-10-03.md](docs/AUDIT_2026-10-03.md)
**Specifikace:** [docs/MASTER_PROMPT.md](docs/MASTER_PROMPT.md) + [docs/MASTER_PROMPT_GROWTH_ENGINE.md](docs/MASTER_PROMPT_GROWTH_ENGINE.md) · **Web:** viz [web/dashboard.json](web/dashboard.json)

> Nikdy nepředpokládej, že modul funguje jen proto, že ho někdo napsal. Stav HOTOVO = existuje test, který prošel.

---

## Rozhodnutí uživatele (2026-10-02, 2026-10-03)

- Pouze **bezplatné** zdroje dat.
- **XTB není povinná podmínka** (stav XTB se jen informativně zapisuje).
- Fokus: AI → elektřina → jádro/fúze → palivo → síť, dohody Google a dalších Big Tech, raketový potenciál.
- Web aktualizovaný denně: staré predikce + vyhodnocení, nové predikce, model se sám přeučuje.
- ~~E-mail zatím nikam~~ → 2026-10-03: e-mail smí být použit, pokud pomůže; uživatel musí vědět, kolikrát denně
  a kde. Používá se jen pro SEC EDGAR (www.sec.gov, data.sec.gov), každé použití v `email_usage` + web + denní zpráva.
- 2026-10-03: Claude dělá vše sám a průběžně zlepšuje kód; cíl = předpovědět firmy s růstem desítek až stovek %
  za ~6 měsíců; využít všechny dostupné zdroje; jednodušší web.

## Stav analýz

| Položka | Stav |
|---|---|
| Firmy na radaru | 46 veřejných firem v 11 článcích řetězce AI → elektřina + Holtec (před IPO) + 9 případů z §31 |
| Dohody Big Tech | 22 se zdrojem (11× Google, 4× Meta, 2× Amazon, 2× Microsoft, 3 ostatní) |
| Katalyzátory | 8 (žádný s ověřeným přesným datem; odhady jako okno) |
| Predikce v ledgeru | 17 živých: 7 energetických (HPS-A.TO, VST, RR.L, 6501.T, DJT, FLR, NKT; „lépe než S&P 500 za 30 dní“) a 10 raket na 6 měsíců z 2026-10-03 (8338.T, MLX.AX, DSV.TO, PDI.AX, NXL.AX, IRWD, SBC, 010950.KS, 7389.T, 8550.T; cíl +50 % do 2027-04-01) |
| MAIN PICK | ŽÁDNÝ (nikdo nesplnil skóre ≥ 70 a šanci ≥ 55 %) |
| Model | verze vah 1; test mimo vzorek (03–09/2026): IC +0,07, TOP 5 porazilo S&P 500 v 45 % případů |
| XTB | u žádné firmy neověřeno (už není podmínka) |

## Globální objevování (Growth Engine) — první běh 2026-10-02

| Položka | Stav |
|---|---|
| Rozsah | 13 110 firem v seznamu, 12 158 s historií ≥ 1 rok, 61 zemí, 374 oborů, data 2021-10-04 → 2026-10-02; 22 řad vyřazeno jako chyba dat |
| Rakety | 18 653 týdenních (≥ +30 %), 10 434 měsíčních (≥ +50 %), 13 063 tříměsíčních (≥ +50 %), 4 046 šestiměsíčních (≥ +100 %) |
| Předvídatelnost | Velikost pohybu ANO (AUC 0,87–0,89), směr NE: horní 1 % má i víc propadů a horší medián než trh; asymetrie směrovou výhodu nedala |
| Příčiny | 58 ze 120 největších týdenních raket vysvětleno z titulků (AUTO); udrželo se málo — výjimkou klinická data (3/4) |
| Ručně ověřeno | ABVX (fáze 3, +586 %), SBET (ETH treasury) → lekce MECH-KLINICKA-DATA, MECH-KRYPTO-TREASURY |
| Známé případy po datu tréninku | Nebius horní 2,7 %, CAPR horní 12,5 %, Moderna horní 12 % (5 dní před raketou) |
| Ledger | 0 kandidátů týden/3 měsíce (brána směrové výhody); 10 predikcí raket na 6 měsíců (běh #2) |
| Web dokument `stav/objevy` | 22 kB (výtah; limit kontroly 170 kB kvůli zvětšení na serveru ×1,4–1,5) |

## Model raket na 6 měsíců (v0.4.0, běh objevování #2, 2026-10-03)

| Položka | Stav |
|---|---|
| Cíl | cena během 126 obchodních dní aspoň 2 dny po sobě ≥ +50 %; zrcadlově propad ≤ −33 % |
| Data | panel 352 075 vzorků (každých 14 dní), cena/objem + sektorová vlna + SEC fundamenty a filingy (5 430 US firem) + klinické studie (496 firem) |
| Test mimo vzorek | učení 2022-04..2024-12, test 2025-07..2026-04: všechny akcie raketa 16,7 % / propad 16,0 % / medián +1,8 %; horní 1 % (raketa − propad) 25,1 % / 17,6 % / +0,3 % |
| Přínos SEC + studií | AUC 0,7325 vs 0,7307 jen z ceny — malý |
| Verdikt | mírná výhoda v četnosti raket, ne ve směru → predikce WATCH se šancí na raketu i propad; vyhodnotí je ledger |
| Evidence e-mailu | 2026-10-03: 174 dotazů (data.sec.gov 147, www.sec.gov 27) — první stažení SEC; týdně pak ~25 |

## HOTOVO (ověřeno testy — 86 testů prošlo 2026-10-03)

| Modul | Co dělá | Testy |
|---|---|---|
| `migrations/0001_initial.sql` | Schéma v1, pravidla MASTER PROMPTu v triggerech/CHECK | `tests/unit/*` |
| `migrations/0002_energy_radar.sql` | Řetězec, dohody, cache cen, verze a běhy modelu, benchmark; zrušena DB brána XTB | `test_ledger.py`, `test_universe.py` |
| `db.py`, `companies.py`, `catalysts.py`, `ledger.py`, `lessons.py`, `snapshots.py`, `state_io.py` | Jádro z v0.1.0; ledger nově s benchmarkem (nadvýnos vůči S&P 500) a volitelnou XTB bránou | unit + integrace |
| `sources/yahoo.py`, `ingest.py` | Bezplatné denní ceny, objemy a kurzy (Yahoo chart API), cache `price_bars` | `test_update_pipeline.py` (offline) + ostrý běh 53/53 symbolů |
| `universe.py` | Výzkum: uzly řetězce, firmy, dohody, katalyzátory se zdroji; API pro denní výzkum | `test_universe.py` |
| `model.py` | 9 faktorů, učení vah z historie (IC, bez look-ahead), kalibrace, test mimo vzorek, verze modelu | `test_model.py` |
| `update.py` | Denní běh: ceny → vyhodnocení → učení → skóre → predikce → snapshot → export → web | `test_update_pipeline.py` |
| `site.py` | Data pro web (4 dokumenty, limit 170 kB kvůli serveru) | `test_update_pipeline.py`, `test_discovery_pipeline.py` |
| `web/index.html` | Webový přehled (artifact s db) | syntax check; čtení dat ověřeno na úrovni `view` |
| `cli.py` | + `update`, `discover`, `sources`, `email`, `diag` | `tests/end_to_end/test_cli.py` |
| `contact.py`, `migrations/0004` | E-mail jen pro SEC, evidence každého použití (nemazatelná) | `tests/unit/test_sources.py` |
| `sources/sec.py`, `sources/clinicaltrials.py`, `discovery/fundamentals.py` | SEC + ClinicalTrials.gov, znaky k danému dni bez look-ahead | `tests/unit/test_sources.py` |
| `discovery/rocket.py`, `discovery/store.record_rockets` | Model raket na 6 měsíců, test mimo vzorek, ledger, automatické katalyzátory ze studií | `test_rocket.py`, `test_discovery_pipeline.py` |
| `update.evaluate_predictions` | Vyhodnocení raket podle cíle (HIT/MISS/zatím nerozhodnuto) i mimo energetický vesmír | `test_rocket.py` |
| `diag.py` | Diagnostika (čerstvost, zpožděná vyhodnocení, web, e-mail) | `test_cli.py` |

## ROZPRACOVÁNO

| Co | Stav |
|---|---|
| Denní rutina | `trig_014DLvB7z2E2pdZPBQ9W1WVp`, po–pá 22:47 (Praha), spouští se do session 01DgCocSAmUmZvDnxF2gb7wH |
| Týdenní objevování + zlepšování | `trig_01FbMAHzeDTDMQMvqonAW29k`, sobota 9:41 (Praha): `discover --universe --download` (+ SEC, studie, rakety) + `update` + `diag` + jedno zlepšení kódu s testem + web |
| Učení z ledgeru (H3) | Energetický model se učí z historie cen, ne z vlastních výsledků — plán P2.1 |
| Kroky běhu v `model_runs` (M3) | Ukládají se před koncem běhu |

## BLOKOVÁNO

| Co | Proč | Co je potřeba |
|---|---|---|
| Tržní kapitalizace mimo USA a data výsledků z Yahoo | `quote`/`quoteSummary` vyžadují crumb, odsud HTTP 401/429 | US firmy: kapitalizace ze SEC (akcie × cena); ostatní odhad z obratu |

## NEOVĚŘENO

| Co | Poznámka |
|---|---|
| Kalibrace pravděpodobností | Energie: spočítaná na stejné historii, na které se model učil → optimistická. Rakety: šance = četnost v testu mimo vzorek (horký trh 2025–26, může přeceňovat). Pravdu ukáže ledger. |
| Klinické studie v historii | Dnešní datum dokončení (look-ahead u 2 znaků) — přínos v testu malý |
| Faktor „Dohoda s Big Tech“ | Na historii IC −0,05 (málo firem s dohodou); model mu váhu snížil na 0,07. |
| Faktor „Katalyzátor do 45 dní“ | Jen 3 historická data — váha je skoro celá apriorní. |
| Růst `state/` | `model_runs` ~16 kB denně; při ~6 MB/rok zvážit kompresi nebo týdenní agregaci. |
| Identita firem §31 | Odvozeno z tickerů. |

## DEPRECATED

| Co | Proč |
|---|---|
| DB trigger `predictions_xtb_gate` | Zrušen migrací 0002 na pokyn uživatele (XTB není podmínka). Python brána zůstává volitelná. |
| Tabulky `sec_filings`, `sec_shares`, sloupec `listings.sec_cik` (migrace 0002) | Nikdy nepoužité; SEC data jsou v cache objevování (`data/market_cache.db`). Migrace se nepřepisují. |

---

## Jak se pracuje se stavem

1. `python -m stockradar init` — pracovní DB z `state/` (DB ani cache cen nejsou v gitu).
2. `python -m stockradar update` — denní běh (stáhne ceny, při prázdné cache 5 let historie); pak `diag`.
3. Výzkum přes Python API (`universe.add_relationship`, `add_tracked_company`, `catalysts.add_catalyst`).
4. `python -m stockradar status` nesmí hlásit neexportované změny; commit `state/`.
5. Web: zapsat `data/web/stav_*.json` do db dokumentů artifactu (viz `CLAUDE.md`, Denní úloha).
