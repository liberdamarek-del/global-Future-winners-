# ROADMAP (§62)

Pořadí fází je nezávazné. Po každé fázi: testy, aktualizace PROJECT_STATE.md a CHANGELOG.md.

| Fáze | Obsah | Stav |
|---|---|---|
| 1 | Databáze + projektový stav | **HOTOVO** (v0.1.0) |
| 2 | Import seznamu akcií (globální univerzum, burzy, sektory, země) | **ČÁSTEČNĚ** — 46 firem řetězce AI → elektřina (v0.2.0); další sektory čekají |
| 3 | Ceny a historická data (10–15 let, splity, dividendy, delistované firmy) | **ČÁSTEČNĚ** — Yahoo, 5 let denních dat (v0.2.0) |
| 4 | Fundamenty (market cap, EV, cash, burn, runway, dilution, warrants, ATM) | BLOKOVÁNO — SEC vyžaduje kontaktní e-mail |
| 5 | Katalyzátory — automatický sběr (FDA/PDUFA, ClinicalTrials.gov, earnings kalendář, 8-K, IPO kalendáře) | ČÁSTEČNĚ — denní výzkum v rutině |
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
| SEC EDGAR — filingy, počet akcií, ředění | vypnuto: vyžaduje kontaktní e-mail (čeká na souhlas uživatele) |
| ClinicalTrials.gov API v2 — klinické studie | dostupné, zatím nevyužito (biotech radar) |
| NRC, World Nuclear News, ANS, Utility Dive, tiskové zprávy | ruční ověřování v denní rutině |
| XTB | není podmínka (rozhodnutí uživatele) |

## Další kroky

1. Weekly report (§35) z `model_runs` a ledgeru.
2. Biotech/ostatní sektory do radaru (ClinicalTrials.gov) — stejný model, jiný řetězec.
3. Survivorship bias: přidat do backtestu i firmy, které z řetězce vypadly (delisting, krach).
4. Po souhlasu uživatele zapnout SEC EDGAR → tržní kapitalizace a faktor ředění.

## Připravené rozšíření schématu

Nové tabulky (ceny, fundamenty, update runs) se přidávají jako `stockradar/migrations/0002_*.sql` —
existující migrace se nepřepisují (§50, §65).
