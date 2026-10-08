# PROJECT_STATE — zdroj pravdy projektu (§48)

**Aktualizováno:** 2026-10-07 · **Verze:** v0.10.0 · **Schema DB:** v8 · **Audit:** [docs/AUDIT_2026-10-03.md](docs/AUDIT_2026-10-03.md) · **Smart money:** [docs/SMART_MONEY_2026-10-05.md](docs/SMART_MONEY_2026-10-05.md) · **Signály 14 dní / 1 měsíc + žebříček:** [docs/SIGNALS_2026-10-05.md](docs/SIGNALS_2026-10-05.md) · **Kauzální radar + 6 měsíců:** [docs/CAUSAL_2026-10-06.md](docs/CAUSAL_2026-10-06.md) · **Architektura a propojení:** [docs/ARCHITEKTURA_2026-10-07.md](docs/ARCHITEKTURA_2026-10-07.md)
**Specifikace:** [docs/MASTER_PROMPT.md](docs/MASTER_PROMPT.md) + [docs/MASTER_PROMPT_GROWTH_ENGINE.md](docs/MASTER_PROMPT_GROWTH_ENGINE.md) · **Web:** viz [web/dashboard.json](web/dashboard.json)

> Nikdy nepředpokládej, že modul funguje jen proto, že ho někdo napsal. Stav HOTOVO = existuje test, který prošel.

---

## Rozhodnutí uživatele (2026-10-02 … 2026-10-07)

- Pouze **bezplatné** zdroje dat.
- **XTB není povinná podmínka** (stav XTB se jen informativně zapisuje).
- Fokus: AI → elektřina → jádro/fúze → palivo → síť, dohody Google a dalších Big Tech, raketový potenciál.
- Web aktualizovaný denně: staré predikce + vyhodnocení, nové predikce, model se sám přeučuje.
- ~~E-mail zatím nikam~~ → 2026-10-03: e-mail smí být použit, pokud pomůže; uživatel musí vědět, kolikrát denně
  a kde. Používá se jen pro SEC EDGAR (www.sec.gov, data.sec.gov), každé použití v `email_usage` + web + denní zpráva.
- 2026-10-03: Claude dělá vše sám a průběžně zlepšuje kód; cíl = předpovědět firmy s růstem desítek až stovek %
  za ~6 měsíců; využít všechny dostupné zdroje; jednodušší web.
- 2026-10-05: hlavní obrazovka = **žebříček TOP 20** v záložkách „Do 14 dní / Do 1 měsíce / Do 6 měsíců“ (jakýkoli
  sektor a země, první = nejsilnější kandidát), detail po rozkliknutí firmy; ostatní analýzy zůstávají sbalené.
- 2026-10-05 (2): v žebříčku **jen akcie, které nabízí XTB** (broker uživatele nemá např. australské a japonské
  akcie); ověřuje se na xtb.com před zařazením. Ledger se nemění (XTB dál není podmínkou predikcí).
- 2026-10-06: kauzální radar (svět → událost → komodita → obory → firmy) a „další Microsoft“ = firma s šancí na
  ~+40 % za 6 měsíců (model SIGNAL_6M). Zpráva [docs/CAUSAL_2026-10-06.md](docs/CAUSAL_2026-10-06.md).
- 2026-10-07: systém = **propojená síť specializovaných částí** (předávají si kontext, kontrolují se, učí se ze zpětné
  vazby), paměť běhů a výsledků, žádné opakované výpočty bez důvodu, stavy HOTOVO/OVĚŘENO, ROZPRACOVÁNO, BLOKOVÁNO,
  NEOVĚŘENO, CHYBA; postup POZOROVAT → POCHOPIT → PROPOJIT → ANALYZOVAT → NAVRHNOUT → IMPLEMENTOVAT → OTESTOVAT →
  VYHODNOTIT. Zpráva [docs/ARCHITEKTURA_2026-10-07.md](docs/ARCHITEKTURA_2026-10-07.md).

## Stav analýz

| Položka | Stav |
|---|---|
| Firmy na radaru | 46 veřejných firem v 11 článcích řetězce AI → elektřina + Holtec (před IPO) + 9 případů z §31 |
| Dohody Big Tech | 22 se zdrojem (11× Google, 4× Meta, 2× Amazon, 2× Microsoft, 3 ostatní) |
| Katalyzátory | 8 (žádný s ověřeným přesným datem; odhady jako okno) |
| Predikce v ledgeru | 35 živých: #35 SO (energie, update běh #7, 2026-10-05), 5 nových raket na 6 měsíců z běhu objevování #4 (2026-10-05: PNR.AX, 4DX.AX, MGNX, ELS.AX, KOS; ostatní z TOP 10 už v ledgeru byly), 12 smart money z 2026-10-05 (#18–#29; WATCH „lépe než S&P 500 za 6 m“; WIX #19 neplatná — poučení SM-ESPP-FLIP-WIX) a 17 starších: 7 energetických (HPS-A.TO, VST, RR.L, 6501.T, DJT, FLR, NKT; „lépe než S&P 500 za 30 dní“) a 10 raket na 6 měsíců z 2026-10-03 (8338.T, MLX.AX, DSV.TO, PDI.AX, NXL.AX, IRWD, SBC, 010950.KS, 7389.T, 8550.T; cíl +50 % do 2027-04-01) |
| MAIN PICK | ŽÁDNÝ (nikdo nesplnil skóre ≥ 70 a šanci ≥ 55 %) |
| Model | verze vah 3 (2026-10-05: Trend 120 dní 0,68 → 0,58, malá firma 0,13 → 0,05, objem 0,08 → 0,02); původně verze 1; test mimo vzorek (03–09/2026): IC +0,07, TOP 5 porazilo S&P 500 v 45 % případů |
| XTB | žebříček jen z nabídky XTB (ověřeno na xtb.com 2026-10-05); ledger bez podmínky XTB, u predikcí v ledgeru se XTB nezapisuje |

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
| Stabilita (v0.4.1) | šance na raketu v horním 1 % 1,5–2,4× vyšší než u všech akcií ve 3 obdobích (2024-H1, 2025-H1, 2025-H2–2026); medián lepší jen v 2025-H1 |
| Kvalita dat (v0.4.1) | 26 řad s neupraveným reverse splitem se před analýzou upraví (DHY, WCT …) |
| Evidence e-mailu | 2026-10-03: 174 dotazů (první stažení SEC), 2026-10-04: 40 (týdenní obnova); po opravě v0.4.1 týdně ~20 |

## Smart money (v0.5.0, běh #3, 2026-10-05)

| Položka | Stav |
|---|---|
| Data | SEC Form 3/4/5 sady 2021Q4–2026Q1 (32 555 aktivních nákupů insiderů, 1 058 automatických 10b5-1, 347 „koupil a do 10 dní prodal“), Sněmovna 7 771 + Senát 1 248 nákupů, 3 496 × 13D, 31 995 × 13G, 8 511 firmo-let buybacků |
| Metoda | vstup den po zveřejnění; 1 t–12 m; S&P 500 + kontrola ze stejného oboru (pevný výběr); aktivní − pasivní ve stejném měsíci; učení 2021–24 / test 2025–26 |
| Výsledek | opakovatelný vzorec NEPOTVRZEN: insideři po propadu +5,7 % (t 4,9) v učení → −5,1 % (t −2,3) v testu; politici −1,6 % (t −0,7); Pelosi vs QQQ 6 m medián −0,5 %, 48 % porazilo (n 25); 13D −8,0 % (t −4,3); buybacky bez efektu |
| Skóre | test 2025–26: odliší jen nejslabší pětinu (0–20) |
| Signály | 10 ověřených ve Form 4 (SBLK, GRNT, BLX, INR = STŘEDNÍ; NOMD, PRE, CC, KMPR, ELAN, AVBC = NÍZKÁ); žádná VYSOKÁ |
| Web | sekce Smart money, dokument `stav/smartmoney` (~37 kB) |
| NEOVĚŘENO | Trump (OGE 278-T jsou skeny), 13F, short interest, oznámení buybacků z 8-K, EPS, zisk opcí |

## Signály na 14 dní (v0.6.0, běhy #1–#2, 2026-10-05)

| Položka | Stav |
|---|---|
| Výstup | karta: P(+5 %), P(−5 %), P(flat), P(lépe než obor), P(±10 %), očekávaný pohyb + rozpětí, důvěra 0–100, RŮST / POKLES / NEVÍM, analogie, katalyzátor, novost a kvalita zpráv, skóre složek |
| Protokol | TRAIN ≤ 2024-06-28 · VALIDATION 2024-07-19…2025-06-27 · LOCKED TEST 2025-07-18…2026-03-27 (jednou, konfigurace `a1b0f2e61e6c56cc`, pokus č. 1) · POST od 2026-04-17 · LIVE `signal_forecasts` |
| Data | 168 586 vzorků = 24 942 nezávislých (týden × obor), 198 týdnů; trh 108 dvoutýdnů |
| Zamčený test | AUC +5 % 0,60 · −5 % 0,69 · ±10 % 0,83 · obor 0,53; RŮST bez výhody (+0,6 %, šum 65 %); POKLES −0,9 % (šum 10 %) |
| Dnes | 3 673 akcií: RŮST 0, POKLES 193, NEVÍM 3 480; trh NEVÍM |
| NEVÍM / NEOVĚŘENO | konsenzus analytiků, short interest, opční toky, zprávy jako prediktor, mechanismy (nestabilní), mispricing (nepotvrzen), akcie mimo USA |

## Žebříček na hlavní stránce (v0.8.0, signály běhy #13–#14, objevování #5, 2026-10-05)

| Horizont | Zdroj | Dnes (data k 2026-10-02) |
|---|---|---|
| Do 14 dní | SIGNAL_14D, TOP 20 z 3 673 US akcií, jen z nabídky XTB | 1. TGTX, 2. KMX, 3. CRH (na XTB jako CRH.UK); prověřeno 21, vyřazen 1 (EOLS); šance +5 % u všech 32 % (základ 23 %); silných signálů RŮST 0; Vistra celkově 370. |
| Do 1 měsíce | SIGNAL_1M (zamčený test: AUC +10 % 0,64, −10 % 0,74; směr nepotvrzen), TOP 20 z nabídky XTB | 1. SND, 2. TGTX, 3. INSW; prověřeno 21, vyřazen 1 (FBRT); šance +10 % 25 % (základ 17 %); Vistra celkově 642. |
| Do 6 měsíců | model raket (celý svět); web: TOP z nabídky XTB, ledger: TOP 10 modelu beze změny | 19 firem (z prvních 151 v pořadí modelu; HBM.TO a HBM = jedna firma): 1. MGNX, 2. KOS, 3. IRWD, 4. Lasertec (6K8.DE), 5. Frontline (FRO.NO); model sám vede PDI.AX, MLX.AX, PNR.AX (XTB je nenabízí) |
| Pravidlo řazení | vybrané na validaci; při shodě šance menší riziko poklesu | průměrný výnos TOP 20 proti týdnu ≈ 0 → vyšší šance na velký růst, ne jistota |

## Kauzální radar a model na 6 měsíců (v0.9.0, 2026-10-06)

| Položka | Stav |
|---|---|
| Komodity | 26 z Yahoo (10/2021–10/2026); cukr Yahoo nevrací; GDELT blokován (HTTP 429) |
| Citlivost | 125 oborů USA × 26 komodit, beta za 78 týdnů jen z minulosti; 456 vazeb s \|t\| ≥ 2 z 3 250 |
| Test řetězců (`b3e10705103a8221`, zamčený test jednou) | v ceně do 4 týdnů +2,9 % (t 3,8); potom 13 týdnů +0,9 % (t 0,5) → bez zpožděné výhody; logika 2.–3. řádu opačný směr (t −2,4) |
| Radar | běhy #1–#5: dnes 10 karet (3 cenové šoky: železná ruda, ocel, dolar; 7 GDACS = sledovat), 2 příležitosti (dolar ↑ → těžaři zlata a kovů ↓, v ceně 75–80 %); predikce jen při shodě dat a logiky |
| SIGNAL_6M (`5703f7e451f2ff54`) | zamčený test: AUC +40 % 0,68, −25 % 0,75; dolní desetina −25 % v 57 % (t −4,0); horní desetina bez výhody |
| Dnes (data k 2026-10-02) | všechny: KOS, ACDC, PUMP, NESR, DK…; velké: DINO, MPC, VLO, TWLO, QXO…; riziko pádu: LWLG, BW, SUNE, FCUV, HUT…; MSFT 2 457. z 3 673 |
| Vzorec uživatele (základna u supportu) | 1 412 případů: medián 3 m +1,5 % vs +2,1 % → bez výhody |

## Propojený systém (v0.10.0, 2026-10-07) — `python -m stockradar system`

| Položka | Stav |
|---|---|
| Moduly (registr) | HOTOVO/OVĚŘENO 2 (signály, smart money), HOTOVO 3 (ceny, XTB, centrum), NEOVĚŘENO 4 (energie, objevování, kauzální radar, ruční výzkum), ROZPRACOVÁNO 1 (vyhodnocení predikcí) |
| Ověřené role mimo vzorek | varování 1 měsíc (t 3,7), varování 6 měsíců (t 4,0), aktivní nákup insiderů (t 2,7 proti podobným akciím) |
| Neověřené role | výběry 14 d / 1 m / 6 m, rakety 6 m, kauzální příležitosti, energetika TOP 5, ruční výzkum |
| Centrum (běh #2) | 151 firem, 307 důkazů: příležitost 103 (téměř vše neověřené), riziko 28, rozpor 7 (DINO, MPC, VLO, DK, ASM, HBM, LAC), nevím 13 |
| Ruční výzkum | #1–#8: G7 uvolňuje až 100 mil. barelů ropy a nafty → tlak na marže rafinérií (DINO, MPC, VLO, PSX, PBF, DK, CVI, PARR), platí do 2027-02-03 |
| Zpětná vazba | 0 vyhodnocených, 236 čeká; první vyhodnocení 2026-10-09; živé výsledky přebijí testy od 30 případů v 6 týdnech |
| Zdroje BLOKOVÁNO | GDELT (HTTP 429); cukr Yahoo od 2026-10-07 vrací (27 komodit; zamčený test řetězců zůstává z 2026-10-06 podle protokolu) |

## HOTOVO (ověřeno testy — 134 testů prošlo 2026-10-07)

| Modul | Co dělá | Testy |
|---|---|---|
| `migrations/0001_initial.sql` | Schéma v1, pravidla MASTER PROMPTu v triggerech/CHECK | `tests/unit/*` |
| `migrations/0002_energy_radar.sql` | Řetězec, dohody, cache cen, verze a běhy modelu, benchmark; zrušena DB brána XTB | `test_ledger.py`, `test_universe.py` |
| `db.py`, `companies.py`, `catalysts.py`, `ledger.py`, `lessons.py`, `snapshots.py`, `state_io.py` | Jádro z v0.1.0; ledger nově s benchmarkem (nadvýnos vůči S&P 500) a volitelnou XTB bránou | unit + integrace |
| `sources/yahoo.py`, `ingest.py` | Bezplatné denní ceny, objemy a kurzy (Yahoo chart API), cache `price_bars` | `test_update_pipeline.py` (offline) + ostrý běh 53/53 symbolů |
| `universe.py` | Výzkum: uzly řetězce, firmy, dohody, katalyzátory se zdroji; API pro denní výzkum | `test_universe.py` |
| `model.py` | 9 faktorů, učení vah z historie (IC, bez look-ahead), kalibrace, test mimo vzorek, verze modelu | `test_model.py` |
| `update.py` | Denní běh: ceny → vyhodnocení → učení → skóre → predikce → snapshot → export → web | `test_update_pipeline.py` |
| `site.py` | Data pro web (7 dokumentů `stav/*` včetně `zebricek`, limit 170 kB kvůli serveru) | `test_update_pipeline.py`, `test_discovery_pipeline.py` |
| `web/index.html` | Webový přehled (artifact s db): hlavní stránka = žebříček se záložkami, ostatní v „Další analýzy“ | syntax check; vykreslení desktop/mobil (Playwright); čtení dat ověřeno na úrovni `view` |
| `cli.py` | + `update`, `discover`, `sources`, `email`, `diag` | `tests/end_to_end/test_cli.py` |
| `contact.py`, `migrations/0004` | E-mail jen pro SEC, evidence každého použití (nemazatelná) | `tests/unit/test_sources.py` |
| `sources/sec.py`, `sources/clinicaltrials.py`, `discovery/fundamentals.py` | SEC + ClinicalTrials.gov, znaky k danému dni bez look-ahead | `tests/unit/test_sources.py` |
| `discovery/rocket.py`, `discovery/store.record_rockets` | Model raket na 6 měsíců, test mimo vzorek, ledger, automatické katalyzátory ze studií | `test_rocket.py`, `test_discovery_pipeline.py` |
| `update.evaluate_predictions` | Vyhodnocení raket podle cíle (HIT/MISS/zatím nerozhodnuto) i mimo energetický vesmír | `test_rocket.py` |
| `sources/xtb.py` | Nabídka XTB: symbol na domácí burze, pak jméno firmy (CRH → CRH.UK, Lasertec → 6K8.DE); akcie / CFD / NE; cache `xtb_offer` 30 dní; po 5 chybách sítě stop | `tests/unit/test_xtb.py` (6) |
| `causal/*`, `migrations/0007` | Kauzální radar: komodity, graf řetězců, citlivost bez pohledu do budoucnosti, test řetězců se zamčeným testem, GDACS + zprávy, karty, predikce a vyhodnocení | `tests/unit/test_causal.py` (7) |
| `diag.py` | Diagnostika (čerstvost, zpožděná vyhodnocení, web, e-mail) | `test_cli.py` |
| `signals/*`, `migrations/0006` | Signály na 14 dní a 1 měsíc + žebříček TOP 20: režim, panel, protokol se zamčeným testem, modely podle režimu, kalibrace, důvěra a NEVÍM, analogie, zprávy, mechanismy | `tests/unit/test_signals.py` (14) |
| `hub/*`, `migrations/0008` | Centrum důkazů, spolehlivost rolí, pohled na firmu s rozpory a poučeními, registr modulů a zdrojů, deník běhů, ruční výzkum | `tests/unit/test_hub.py` (10) |
| `causal/memo.py` | Paměť výpočtů (týdenní řady, citlivosti) podle otisku dat; `signals` bez nových dat se přeskočí | `test_hub.py`, ostrý běh (56 s → 0,5 s, shodný výsledek) |
| `smartmoney/*`, `migrations/0005` | Smart money: zdroje (SEC, Sněmovna, Senát), typy transakcí, event study, skóre, aktuální signály ověřené ve Form 4, ledger, web | `tests/unit/test_smartmoney.py` (8) |

## ROZPRACOVÁNO

| Co | Stav |
|---|---|
| Denní rutina | `trig_014DLvB7z2E2pdZPBQ9W1WVp`, po–pá 22:47 (Praha): `update` + `causal` (centrum se obnoví samo) + diag + výzkum (`research`) + web (10 dokumentů včetně `stav/prehled`), spouští se do session 01DgCocSAmUmZvDnxF2gb7wH |
| Živá zpětná vazba | Role se zatím hodnotí jen z testů; první živé výsledky 2026-10-09, spolehlivé po ~30 případech v 6 týdnech |
| Vyhodnocení ručního výzkumu | Výzkum se ukládá a propojuje, ale zatím se neměří proti cenám (role VÝZKUM = NEOVĚŘENO) |
| Kauzální radar mezi sobotami | Šok komodity se počítá na týdenní mřížce, která končí posledním dnem cen akcií (sobotní stažení) → denní pohyby komodit po tomto dni radar uvidí až po dalším `discover --download`; karty se proto přes týden opakují (zjištěno 2026-10-08, kandidát na týdenní zlepšení: šok z denních cen komodit, citlivost dál z týdenních řad) |
| Týdenní objevování + zlepšování | `trig_01FbMAHzeDTDMQMvqonAW29k`, sobota 9:41 (Praha): `system` + `discover --universe --download` (+ SEC, studie, rakety) + `smart-money` + `signals` (14 dní, 1 měsíc, 6 měsíců; bez nových cen přeskočí) + `update` + `causal` + `diag` + `hub` + jedno zlepšení kódu s testem + web (10 dokumentů) |
| Učení z ledgeru (H3) | Energetický model se učí z historie cen, ne z vlastních výsledků — plán P2.1 |
| Kroky běhu v `model_runs` (M3) | Ukládají se před koncem běhu |

## BLOKOVÁNO

| Co | Proč | Co je potřeba |
|---|---|---|
| GDELT (světové zprávy) | HTTP 429 ze sdílené adresy serveru | jiný server nebo jiný bezplatný zdroj; zatím Google News RSS |
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
| Váhy důvěry v centru | Průhledné pravidlo (t / 4, neověřené 0,1, stará data polovina), ne naučený model. |
| Obor firmy pro kauzální radar | Ze seznamu Nasdaq; občas nepřesný (HF Sinclair = „natural gas distribution“), proto se výzkum rafinérií zapsal po firmách. |

## DEPRECATED

| Co | Proč |
|---|---|
| DB trigger `predictions_xtb_gate` | Zrušen migrací 0002 na pokyn uživatele (XTB není podmínka). Python brána zůstává volitelná. |
| Tabulky `sec_filings`, `sec_shares`, sloupec `listings.sec_cik` (migrace 0002) | Nikdy nepoužité; SEC data jsou v cache objevování (`data/market_cache.db`). Migrace se nepřepisují. |

---

## Jak se pracuje se stavem

1. `python -m stockradar init` — pracovní DB z `state/` (DB ani cache cen nejsou v gitu); `python -m stockradar system`
   ukáže stav všech modulů, zdrojů, spolehlivost rolí a deník běhů.
2. `python -m stockradar update` — denní běh (stáhne ceny, při prázdné cache 5 let historie); pak `diag`.
3. Výzkum přes Python API (`universe.add_relationship`, `add_tracked_company`, `catalysts.add_catalyst`); zprávy, které
   nejsou dohoda ani katalyzátor, přes `python -m stockradar research --entita … --url …` (fakt a úsudek odděleně).
4. `python -m stockradar status` nesmí hlásit neexportované změny; commit `state/`.
5. Web: zapsat `data/web/stav_*.json` do db dokumentů artifactu (viz `CLAUDE.md`, Denní úloha).
