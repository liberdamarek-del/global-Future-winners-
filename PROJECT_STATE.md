# PROJECT_STATE — zdroj pravdy projektu (§48)

**Aktualizováno:** 2026-10-02 · **Verze:** v0.2.0 · **Schema DB:** v2
**Specifikace:** [docs/MASTER_PROMPT.md](docs/MASTER_PROMPT.md) · **Web:** viz [web/dashboard.json](web/dashboard.json)

> Nikdy nepředpokládej, že modul funguje jen proto, že ho někdo napsal. Stav HOTOVO = existuje test, který prošel.

---

## Rozhodnutí uživatele (2026-10-02)

- Pouze **bezplatné** zdroje dat.
- **XTB není povinná podmínka** (stav XTB se jen informativně zapisuje).
- Fokus: AI → elektřina → jádro/fúze → palivo → síť, dohody Google a dalších Big Tech, raketový potenciál.
- Web aktualizovaný denně: staré predikce + vyhodnocení, nové predikce, model se sám přeučuje.

## Stav analýz

| Položka | Stav |
|---|---|
| Firmy na radaru | 46 veřejných firem v 11 článcích řetězce AI → elektřina + Holtec (před IPO) + 9 případů z §31 |
| Dohody Big Tech | 22 se zdrojem (11× Google, 4× Meta, 2× Amazon, 2× Microsoft, 3 ostatní) |
| Katalyzátory | 8 (žádný s ověřeným přesným datem; odhady jako okno) |
| Predikce v ledgeru | 5 živých z 2026-10-02 (HPS-A.TO, VST, RR.L, 6501.T, DJT), vyhodnocení +7/+14/+30 dní se doplní samo |
| MAIN PICK | ŽÁDNÝ (nikdo nesplnil skóre ≥ 70 a šanci ≥ 55 %) |
| Model | verze vah 1; test mimo vzorek (03–09/2026): IC +0,07, TOP 5 porazilo S&P 500 v 45 % případů |
| XTB | u žádné firmy neověřeno (už není podmínka) |

## HOTOVO (ověřeno testy — 65 testů prošlo 2026-10-02)

| Modul | Co dělá | Testy |
|---|---|---|
| `migrations/0001_initial.sql` | Schéma v1, pravidla MASTER PROMPTu v triggerech/CHECK | `tests/unit/*` |
| `migrations/0002_energy_radar.sql` | Řetězec, dohody, cache cen, verze a běhy modelu, benchmark; zrušena DB brána XTB | `test_ledger.py`, `test_universe.py` |
| `db.py`, `companies.py`, `catalysts.py`, `ledger.py`, `lessons.py`, `snapshots.py`, `state_io.py` | Jádro z v0.1.0; ledger nově s benchmarkem (nadvýnos vůči S&P 500) a volitelnou XTB bránou | unit + integrace |
| `sources/yahoo.py`, `ingest.py` | Bezplatné denní ceny, objemy a kurzy (Yahoo chart API), cache `price_bars` | `test_update_pipeline.py` (offline) + ostrý běh 53/53 symbolů |
| `universe.py` | Výzkum: uzly řetězce, firmy, dohody, katalyzátory se zdroji; API pro denní výzkum | `test_universe.py` |
| `model.py` | 9 faktorů, učení vah z historie (IC, bez look-ahead), kalibrace, test mimo vzorek, verze modelu | `test_model.py` |
| `update.py` | Denní běh: ceny → vyhodnocení → učení → skóre → predikce → snapshot → export → web | `test_update_pipeline.py` |
| `site.py` | Data pro web (3 dokumenty, limit 240 kB) | `test_update_pipeline.py` |
| `web/index.html` | Webový přehled (artifact s db) | syntax check; čtení dat ověřeno na úrovni `view` |
| `cli.py` | + příkaz `update` | `tests/end_to_end/test_cli.py` |

## ROZPRACOVÁNO

| Co | Stav |
|---|---|
| Denní rutina | `trig_014DLvB7z2E2pdZPBQ9W1WVp`, po–pá 22:47 (Praha), spouští se do session 01DgCocSAmUmZvDnxF2gb7wH; první běh 2026-10-02 večer |

## BLOKOVÁNO

| Co | Proč | Co je potřeba |
|---|---|---|
| SEC EDGAR (počet akcií → market cap, emise S-3/424B → ředění) | SEC vyžaduje kontaktní e-mail v User-Agent (bez něj HTTP 403) | Souhlas uživatele s použitím e-mailu (proměnná `STOCKRADAR_USER_AGENT`) |
| Tržní kapitalizace a data výsledků z Yahoo | `quote`/`quoteSummary` vyžadují crumb, odsud HTTP 401/429 | Zatím náhrada: velikost odhadnutá z obratu v USD |

## NEOVĚŘENO

| Co | Poznámka |
|---|---|
| Kalibrace pravděpodobností | Spočítaná na stejné historii, na které se model učil, a na dnešním výběru firem (selection bias) → optimistická. Pravdu ukáže ledger. |
| Faktor „Dohoda s Big Tech“ | Na historii IC −0,05 (málo firem s dohodou); model mu váhu snížil na 0,07. |
| Faktor „Katalyzátor do 45 dní“ | Jen 3 historická data — váha je skoro celá apriorní. |
| Růst `state/` | `model_runs` ~16 kB denně; při ~6 MB/rok zvážit kompresi nebo týdenní agregaci. |
| Identita firem §31 | Odvozeno z tickerů. |

## DEPRECATED

| Co | Proč |
|---|---|
| DB trigger `predictions_xtb_gate` | Zrušen migrací 0002 na pokyn uživatele (XTB není podmínka). Python brána zůstává volitelná. |

---

## Jak se pracuje se stavem

1. `python -m stockradar init` — pracovní DB z `state/` (DB ani cache cen nejsou v gitu).
2. `python -m stockradar update` — denní běh (stáhne ceny, při prázdné cache 5 let historie).
3. Výzkum přes Python API (`universe.add_relationship`, `add_tracked_company`, `catalysts.add_catalyst`).
4. `python -m stockradar status` nesmí hlásit neexportované změny; commit `state/`.
5. Web: zapsat `data/web/stav_*.json` do db dokumentů artifactu (viz `CLAUDE.md`, Denní úloha).
