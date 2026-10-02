# ROADMAP (§62)

Pořadí fází je nezávazné. Po každé fázi: testy, aktualizace PROJECT_STATE.md a CHANGELOG.md.

| Fáze | Obsah | Stav |
|---|---|---|
| 1 | Databáze + projektový stav | **HOTOVO** (v0.1.0) |
| 2 | Import seznamu akcií (globální univerzum, burzy, sektory, země) | ČEKÁ — potřebuje rozhodnutí o zdroji dat |
| 3 | Ceny a historická data (10–15 let, splity, dividendy, delistované firmy) | ČEKÁ |
| 4 | Fundamenty (market cap, EV, cash, burn, runway, dilution, warrants, ATM) | ČEKÁ |
| 5 | Katalyzátory — automatický sběr (FDA/PDUFA, ClinicalTrials.gov, earnings kalendář, 8-K, IPO kalendáře) | ČEKÁ (ruční zápis už funguje) |
| 6 | News/document analysis (10-K/10-Q/20-F/6-K/8-K, earnings calls) | ČEKÁ |
| 7 | Scoring — výpočet 12 dimenzí §20 a kategorií §21 | ČEKÁ (úložiště skóre hotové) |
| 8 | Prediction ledger | **Základ HOTOVO** v Fázi 1 (append-only, XTB brána, vyhodnocení) |
| 9 | Backtesting (bez look-ahead a survivorship bias) | ČEKÁ (časové značky `published_at` / `made_at` připraveny) |
| 10 | Dashboard (tabulka jako Excel, filtry ON/OFF, detail firmy) | ČEKÁ |
| 11 | Weekly report (§35) | ČEKÁ |
| 12 | Automatické aktualizace + tlačítko UPDATE se stavem kroků (§54) | ČEKÁ |

## Otevřená rozhodnutí pro Fázi 2–4 (na uživateli)

Žádný z níže uvedených zdrojů zatím nebyl v projektu otestován — jde o kandidáty k ověření, ne doporučení.

1. **Ceny a fundamenty globálně** — placený poskytovatel s pokrytím USA + Evropy + Asie + Austrálie
   vs. bezplatné zdroje s omezeným pokrytím a nižší spolehlivostí.
2. **Regulatorní a firemní dokumenty** — SEC EDGAR (USA, veřejné API), ClinicalTrials.gov (veřejné API),
   openFDA; pro ostatní trhy burzovní oznámení (ASX, Nasdaq Nordic, LSE RNS, HKEX…).
3. **XTB dostupnost** — zjistit, zda existuje strojově čitelný seznam instrumentů. Do té doby: ruční
   ověření v xStation a zápis přes `record_xtb_check(..., source="xStation – vyhledání <datum>")`.

## Připravené rozšíření schématu

Nové tabulky (ceny, fundamenty, update runs) se přidávají jako `stockradar/migrations/0002_*.sql` —
existující migrace se nepřepisují (§50, §65).
