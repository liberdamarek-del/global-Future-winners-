# ROADMAP (§62)

Pořadí fází je nezávazné. Po každé fázi: testy, aktualizace PROJECT_STATE.md a CHANGELOG.md.

| Fáze | Obsah | Stav |
|---|---|---|
| 1 | Databáze + projektový stav | **HOTOVO** (v0.1.0) |
| 2 | Import seznamu akcií (globální univerzum, burzy, sektory, země) | **ČÁSTEČNĚ** — 46 firem řetězce AI → elektřina (v0.2.0); další sektory čekají |
| 3 | Ceny a historická data (10–15 let, splity, dividendy, delistované firmy) | **ČÁSTEČNĚ** — Yahoo, 5 let denních dat (v0.2.0) |
| 4 | Fundamenty (market cap, EV, cash, burn, runway, dilution, warrants, ATM) | **ČÁSTEČNĚ** (v0.4.0) — SEC XBRL: tržby, zisk, počet akcií, hotovost, tržní kapitalizace, ředění, emise; burn/runway/warranty čekají |
| 5 | Katalyzátory — automatický sběr (FDA/PDUFA, ClinicalTrials.gov, earnings kalendář, 8-K, IPO kalendáře) | **ČÁSTEČNĚ** — ClinicalTrials.gov automaticky (v0.4.0), 8-K/13D/emise jako znaky; FDA a earnings kalendář čekají |
| 6 | News/document analysis (10-K/10-Q/20-F/6-K/8-K, earnings calls) | ČEKÁ |
| 7 | Scoring — výpočet 12 dimenzí §20 a kategorií §21 | **ČÁSTEČNĚ** — samoučící kvantitativní model (9 faktorů) |
| 8 | Prediction ledger | **HOTOVO** — automatické predikce a vyhodnocení vůči S&P 500 |
| 9 | Backtesting (bez look-ahead a survivorship bias) | ČÁSTEČNĚ — panel 3 roky + test mimo vzorek; survivorship bias zatím neřešen |
| 10 | Dashboard (tabulka jako Excel, filtry ON/OFF, detail firmy) | **ČÁSTEČNĚ** — web artifact (řazení, hledání, filtr řetězce) |
| 11 | Weekly report (§35) | ČEKÁ |
| 12 | Automatické aktualizace + tlačítko UPDATE se stavem kroků (§54) | **HOTOVO** — `update` + denní rutina |

## Zdroje dat (rozhodnuto 2026-10-02: jen zdarma)

| Zdroj | Stav |
|---|---|
| Yahoo Finance chart API — ceny, objemy, kurzy | **používá se** |
| SEC EDGAR — fundamenty (XBRL frames), filingy s datem (full-index) | **používá se** od v0.4.0 (e-mail povolen 2026-10-03, každé použití evidováno) |
| ClinicalTrials.gov API v2 — klinické studie | **používá se** od v0.4.0 (znaky modelu raket + automatické katalyzátory) |
| NRC, World Nuclear News, ANS, Utility Dive, tiskové zprávy | ruční ověřování v denní rutině |
| XTB | není podmínka (rozhodnutí uživatele) |

## Growth Engine (docs/MASTER_PROMPT_GROWTH_ENGINE.md)

| Část | Stav |
|---|---|
| §2 vítězové 3/6/12/24 m, §3 globální dosah | **HOTOVO** (v0.3.0) — ~13 000 firem, ~30 zemí |
| §6 příčiny, §15 text mining | **ČÁSTEČNĚ** — titulky Google News, klasifikace klíčovými slovy (AUTO); výroční zprávy zatím ne |
| §8 kontrolní skupina, §9 před růstem, §41 backtest bez look-ahead | **HOTOVO** — case-control + test na populaci po datu tréninku |
| §13–14 nové sektory | **ČÁSTEČNĚ** — vlny podle oborů + skupiny společného pohybu; R&D/patenty/VC/hiring nedostupné zdarma |
| §5, §18–23 fundamenty (tržby, capex, backlog, marže) | **ČÁSTEČNĚ** — SEC (USA): tržby, zisk, akcie, hotovost; capex/backlog čekají |
| Vlastní predikce raket na 6 měsíců | **HOTOVO** (v0.4.0) — panel 352 tis. vzorků, test mimo vzorek, ledger s cílem +50 % |
| §37 pre-winner skóre, §38 too late, §45–47 why now / why not / změna názoru | **HOTOVO** (cenové a zprávové signály) |
| §42 ledger 7/14/30/90/180/365 dní | **HOTOVO** |

## Další kroky

1. Ruční ověřování příčin největších raket (týdenní rutina) → databáze mechanismů (§64).
2. Weekly report (§35) z `model_runs`, `discovery_runs` a ledgeru.
3. Survivorship bias: doplnit delistované firmy (zdroj zdarma zatím nenalezen).
4. Signál z globálního modelu jako faktor energetického modelu (propojení modulů).
5. Plán P2/P3 z auditu: `docs/AUDIT_2026-10-03.md` (kapitola 3) — učení z ledgeru, test modelu raket po obdobích,
   insider nákupy (Form 4), obsah 8-K, delistované firmy ze SEC, inkrementální stahování, openFDA.

## Připravené rozšíření schématu

Nové tabulky (ceny, fundamenty, update runs) se přidávají jako `stockradar/migrations/NNNN_*.sql` (poslední 0004) —
existující migrace se nepřepisují (§50, §65).
