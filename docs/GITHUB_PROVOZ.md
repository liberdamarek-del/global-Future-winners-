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
  v režimu `stin` se jeho nové záznamy nezachovají a podání u SEC se doplňují každý večer znovu, nejvýš 60 dotazů). Kauzální radar bez cen akcií hlásí
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
