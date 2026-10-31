# Provoz na GitHubu bez Claude (v0.16.0, 23. 10. 2026)

_Rozhodnutí uživatele 23. 10. 2026: radar má běžet sám na serveru zdarma, aktualizovat se denně, učit se a stránka se má
otevřít v obyčejném prohlížeči (stejně jako FXBOT). Části, které potřebují AI, se vypouštějí. Týden běží GitHub souběžně
s rutinami Claude, pak se rutiny Claude vypnou. E-mail pro SEC uloží uživatel do secretu GitHubu._

## Co kde běží

| Část | Workflow | Kdy |
|---|---|---|
| Denní běh: `init` (ze state/), `update` (ceny, vyhodnocení, učení modelu, predikce, web), `causal`, `rakety` (snímek trhu, rakety, příčiny z titulků = AUTO), `diag`, `email` | `.github/workflows/radar-denni.yml` | po–pá 22:47 Praha + záložní slot |
| Týdenní objevování: `discover --universe --download` → `smart-money` + `funds` → `signals`, `update`, `causal`, `diag`, testy | `.github/workflows/radar-tyden.yml` (3 joby, každý do 6 h) | sobota 9:41 Praha + záložní slot |
| Testy (`python -m pytest`) | `.github/workflows/radar-testy.yml` | při každé změně kódu |
| Stránka | GitHub Pages: `index.html` (= `web/index.html` v celém dokumentu), `stav_*.json`, `provoz.json` (`tools/github_beh.py stranka`) | po každém běhu, jen když projde kontrolou v prohlížeči |
| Oznámení na telefon | ntfy.sh, jen se secretem `NTFY_TEMA` | po denním a týdenním běhu; selhání |

**Neběží (potřebuje AI, uživatel to vypustil):** ruční ověřování zpráv se zdrojem (katalyzátory, dohody Big Tech, IPO,
`research`, ověřené příčiny raket), sobotní zlepšování kódu, denní výzkum agenta (`docs/agent_vyzkum/`). Automatické příčiny
raket z titulků zůstávají označené AUTO / neověřené. Kdykoli to jde udělat ručně v rozhovoru s Claude.

## Data mezi běhy

* `state/` (git) = zdroj pravdy; každý běh si z něj sestaví `data/stockradar.db` (`init` po smazání staré DB).
* `data/market_cache.db` (ceny ~13 000 firem, SEC, studie, insideři, 13F, XTB, snímky raketového deníku) a paměť
  kauzálního radaru `data/cache_kauzalni.pkl` se přenáší cache GitHubu (`radar-data-<běh>`; obnoví se nejnovější). Ukládá se i po selhání, takže přerušené stahování pokračuje.
  První běh na GitHubu začíná s prázdnou cache: stáhne všechno znovu (hodiny; 23. 10. 13 097 řad za ~73 min). Raketový deník
  bere ceny z Yahoo v cache + vlastní denní snímky Nasdaq (od v0.17.0 i propady, podání u SEC, výsledky a přehled trhu;
  v režimu `stin` se jeho nové záznamy nezachovají a podání u SEC se doplňují každý večer znovu, nejvýš 60 dotazů).
  Screener Nasdaq vydá závěr dne D až ráno D+1, takže večerní běh má deník a přehled trhu **za předchozí obchodní den**
  (snímek se ukládá pod dnem, na který sedí závěry z Yahoo — oprava v0.17.0 po běhu 23. 10.). Kauzální radar bez cen akcií hlásí
  BLOKOVÁNO a nic nezapíše (první denní běh 23. 10.), dokud první sobotní objevování cache nenaplní.
* Mezi joby týdenního běhu jde `data/stockradar.db` jako artefakt (3 dny).
* Ceny sledovaných firem a S&P 500 (`price_bars`) ve state/ nejsou: týdenní běh je proto po `init` stáhne příkazem
  `python -m stockradar ceny` (v0.17.0). První sobotní běh 23. 10. bez nich nezapsal do ledgeru nic (objevování ani smart
  money) a signály spadly; signály teď bez SPY hlásí BLOKOVÁNO.
* Výkazy Sněmovny jsou PDF → job smart money instaluje `pdftotext` (poppler-utils).
* E-mail pro SEC: secret `STOCKRADAR_CONTACT_EMAIL` → proměnná prostředí, kterou čte `stockradar.contact` (v logu je
  maskovaný, do gitu ani na stránku se nedostane; `tools/github_beh.py stranka` odmítne zveřejnit data s e-mailovou adresou
  a zpráva o běhu adresy nahrazuje `<e-mail>`). Každé použití se dál eviduje v `email_usage`.

## Režim: stín / ostrý (`provoz/github.json`)

* **stin** (od 23. 10. 2026): GitHub počítá a zveřejní stránku, ale **nic necommituje** (state/ zapisují rutiny Claude).
  Pozor: v souběhu používá e-mail pro SEC i GitHub (sobotní běh); jeho použití je ve zprávě o běhu (`email.txt`) a v souhrnu,
  ale do `state/email_usage` se v tomto režimu nezapíše.
* **ostry**: GitHub je jediný zapisovatel; po úspěšném `update` commituje `state/` do `ccr-07430f55-or3jhd`.
  **Před přepnutím vypnout rutiny Claude** (denní radar, týdenní objevování, denní výzkum agenta).

## Jak se hlídá, že běh proběhl právě jednou

`tools/github_beh.py plan`: `denni` = poslední všední večer od 21:30 Praha, který už nastal (záložní noční slot i ruční běh
přes den patří k předchozímu večeru); `tyden` = poslední sobota od 9:00 Praha. Značka `radar-beh-<druh>-<klíč>` v cache
GitHubu; ruční spuštění (Actions → workflow → Run workflow) běží vždy.

## Kontrola a zprávy

* Stránka se před nasazením otevře v Chrome (Playwright): stav se musí vykreslit, skript nesmí hlásit chybu, na stránce nesmí
  být e-mailová adresa, šířka na telefonu (390 px) nesmí přetékat. Jinak se nenasadí a zůstane předchozí verze.
* Zpráva o každém běhu je ve větvi `provoz-zprava` (výstupy příkazů, diagnostika, e-mail, vykreslená stránka) - logy jobů
  nejsou ze sezení Claude čitelné.

## Rizika a slabá místa

| Riziko | Dopad | Co s tím |
|---|---|---|
| xtb.com ze serverů GitHubu (blokace) | do žebříčku jdou jen akcie ověřené u XTB → žebříček z nového běhu může být prázdný | **NEOVĚŘENO**; ověří první sobotní běh (počet dotazů a chyb XTB ve zprávě) |
| Nasdaq API, Yahoo (13 000 firem), Senát, openinsider z datacentra | chybějící data | **NEOVĚŘENO**; kroky hlásí chyby, cache se ukládá i po selhání |
| Zpoždění nebo vypadnutí plánovaného běhu | stará data | víc slotů; stránka po termínu (`provoz.json`) varuje |
| 60 dní bez aktivity → GitHub plány vypne | běhy přestanou | v ostrém režimu commituje bot denně (zda to stačí, NEOVĚŘENO) |
| Velikost cache | GitHub drží nejvýš 10 GB na repozitář, staré záznamy maže | ukládá se jen `market_cache.db`; velikost ve zprávě o běhu |
| Bez AI části | méně ověřených důkazů v centru, žádné nové zlepšení kódu | ručně v rozhovoru s Claude |

## Srovnání souběhu (N-13, od v0.17.3)

Každý běh na GitHubu uloží do zprávy `otisk.json` (konečný stav: predikce, vyhodnocení, karty, TOP 10, den dat, e-mail).
`python -m stockradar porovnani` ho porovná se stavem Claude podle kritérií daných předem (docs/agent_vyzkum/navrhy.jsonl, N-13)
a zapíše `docs/provoz/srovnani_DEN.md`. O přepnutí do režimu `ostry` rozhoduje uživatel.

### Vyhodnocení N-13 (2026-10-31, po týdnu souběhu)

| Běh | Den dat | Predikce | Vyhodnocení | Karty | Překryv TOP 10 (14 d / 1 m / 6 m / 6 m vše / 6 m velké) | Kritéria |
|---|---|---|---|---|---|---|
| denní 26. 10. | 26. 10. | 73 = 73 | 104 = 104 | 90 = 90 | 1,0 všude | SPLNĚNA |
| denní 27. 10. | 27. 10. | 73 = 73 | 105 = 105 | 90 = 90 | 1,0 všude | SPLNĚNA |
| denní 28. 10. | 28. 10. | 73 = 73 | 106 = 106 | 90 = 90 | 1,0 všude | SPLNĚNA |
| denní 29. 10. | 29. 10. | 73 = 73 | 107 = 107 | 90 = 90 | 1,0 všude | SPLNĚNA |
| denní 30. 10. | 30. 10. | 73 = 73 | 108 = 108 | 90 = 90 | 1,0 všude | SPLNĚNA |
| týdenní 31. 10. | 30. 10. | 85 × 85, ale 5 + 5 jiných firem | 108 = 108 | 181 = 181 | 0,82 / **0,33** / **0,33** / 0,67 / 1,0 | **NESPLNĚNA** |

- **Denní běh** (`update`, `causal`) dává na GitHubu stejný výsledek jako rutina Claude, 5 z 5 dnů.
- **Týdenní běh** se liší, ale **příčinou jsou vstupní data, ne kód**:
  - GitHub dostal ze seznamů 13 132 symbolů a Claude 13 237. Chyb stahování z Yahoo měl GitHub 248 a Claude 297, takže
    vyšlo 12 286 × 12 307 firem.
  - Model raket si na validaci vybral jiné pravidlo řazení: GitHub „výdrž“, Claude „raketa“ (AUC testu 0,735 × 0,732).
  - Ze 7 a 6 predikcí raket jsou společné jen 2 (RXT, PEPG).
  - Signály měly 3 573 × 3 578 akcií. Žebříček na 1 měsíc a model raket jsou na tak malý rozdíl dat citlivé (překryv
    TOP 10 jen 0,33).
- **Závěr:** přepnutí na GitHub by kód ani denní výsledky nezměnilo. Týdenní tipy jsou ale z velké části dané náhodou
  ve vstupních datech (která stažení selžou) — to platí stejně pro Claude.
  - Doporučení před přepnutím: zkontrolovat stabilitu výběru (opakovaný běh na mírně jiných datech; samostatný
    návrh).
  - O přepnutí do režimu `ostry` rozhoduje uživatel.
- Oprava (31. 10. odpoledne): druhý týdenní běh (09:16 UTC, druhý slot cronu kvůli konci letního času) **nic
  nespustil**. Ve frontě počkal na skupinu `radar-provoz`, po skončení prvního běhu našel značku
  `radar-beh-tyden-…` v cache a všechny kroky přeskočil (`bezet=false`, joby „skipped“). Ochrana proti dvojímu
  běhu funguje; dřívější věta „spustil dvakrát“ byla chybná.
