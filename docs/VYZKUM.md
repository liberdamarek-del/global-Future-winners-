# Výzkumný deník (autonomní režim od 2026-10-11)

Zadání uživatele 2026-10-11: samostatně zkoumat, vytvářet hypotézy, experimentovat a učit se z výsledků; hlavní cíl =
najít firmy s šancí na desítky až stovky procent za ~6 měsíců. Každý experiment: hypotéza **předem**, postup, výsledek,
verdikt (POTVRZENO / NEPOTVRZENO / NEOVĚŘENO), poučení. Neúspěchy se zapisují stejně jako úspěchy.

Hranice: jen bezplatné zdroje; žádné obcházení blokací (xtb.com, GDELT); do veřejných diskusí se nepíše (nejsou
nástroje ani účty a vystupovalo by se za uživatele); zamčené testy jen jednou na konfiguraci.

---

## E1 · 2026-10-11 · Spojení dvou ověřených rolí: nákup insiderů × varování modelu 6 m

- **Hypotéza:** aktivní nákup insiderů (ověřeno: +2,8 % proti podobným akciím za 6 m) u firmy, kterou SIGNAL_6M neřadí
  mezi nejslabší, dá vyšší šanci na +40 % a menší riziko −25 % než nákup insiderů bez filtru.
- **Postup:** `stockradar/signals/combo.py`; model SIGNAL_6M naučený jen na TRAIN; 4 předem daná pravidla (R0 bez filtru,
  R10, R30, R50 = percentil směrového skóre v témže týdnu); výběr na validaci; zamčený test jednou
  (`model_evaluations`, INSIDER_X_6M, konfigurace `6a8a133a4b73180d`).
- **Výsledek (zamčený test 2025-07…2026-03, 2 463 nákupů, 1 353 nezávislých):**

| Skupina | +40 % | −25 % | Výnos nad průměrem týdne |
|---|---|---|---|
| Všechny akcie | 13,6 % | 17,8 % | – |
| R0 všechny nákupy insiderů | 11,5 % | 14,3 % | +2,0 % (t 0,4) |
| **R50 vybrané na validaci** | **5,0 %** | **6,0 %** | −0,8 % (t −0,3) |
| Nákup u nejslabší desetiny modelu | 19,9 % | 44,8 % | +0,6 % (t −0,05) |

- **Verdikt:** NEPOTVRZENO jako výběr vítězů. POTVRZENO jako snížení rizika (na validaci i testu), ale za cenu stejně
  nižší šance na růst a bez lepšího výnosu.
- **Poučení:** modely poznají rozkolísanost, ne směr. Spojení modulů vybírá klidnější akcie, ne vítěze. Zapsáno jako
  poučení `POUCENI-KOMBINACE-INSIDER-6M` (centrum ho ukazuje u signálů smart money).

## E2 · 2026-10-11 · Koš nejrozkolísanějších kandidátů (rakety) vs trh

- **Hypotéza:** když modely poznají rozkolísanost, ne směr, mohl by mít KOŠ TOP N raket díky šikmému rozdělení vyšší
  průměrný výnos než trh, i když u jednotlivé firmy směr neznáme.
- **Postup:** model raket naučený do 2024-12-31; řazení vybrané nově na validaci (viz oprava níže); pro každý den
  testu (2025-07…, 20 kohort po 14 dnech) koš TOP 10 / 20 / 50 proti průměru všech akcií téhož dne, 6 m; t přes kohorty
  s korekcí na překryv (13×). Průzkum na období, které už bylo dřív použito k hodnocení modelu → nejde o zamčený test.
- **Výsledek:**

| Koš | Průměr 6 m | Trh | Rozdíl (t) | Rakety +50 % | Propady −33 % | Koš porazil trh |
|---|---|---|---|---|---|---|
| TOP 10 | +1,1 % | +6,7 % | −5,6 % (−0,3) | 39,5 % | 60,0 % | 40 % kohort |
| TOP 20 | +2,4 % | +6,7 % | −4,3 % (−0,4) | 40,8 % | 58,0 % | 25 % kohort |
| TOP 50 | +3,5 % | +6,7 % | −3,2 % (−0,3) | 41,5 % | 54,4 % | 30 % kohort |

- **Ověření výběru řazení (validace):** „raketa“ měla na obou validačních pololetích nejlepší (rakety − propady):
  2024 H1 +0,04 (horní 1 %: průměr +29 %), 2025 H1 +0,24 (průměr +66 %); „asymetrie“ +0,03 a +0,12.
  Stejné řazení v testu: rakety 40 %, propady 54–60 %, výnos pod trhem.
- **Verdikt:** NEPOTVRZENO. Koš raket v testu trh neporazil. Výhoda raket **závisí na režimu trhu** (v horkém 1. pololetí
  2025 velká, potom záporná) — není stabilní.
- **Poučení:** dřívější lepší čísla raket („asymetrie“, test +25 % raket / 18 % propadů) byla zčásti dána výběrem řazení
  přímo na testu (opraveno). Rakety jsou loterie s režimovou závislostí, ne vítězové. Zapsáno `POUCENI-RAKETY-REZIM`.

## E3 · 2026-10-11 · Velká federální zakázka USA → výnos za 6 měsíců (nový typ informace)

- **Hypotéza (předem):** nová zakázka (Mod 0) v hodnotě ≥ 10 % tržní hodnoty firmy → výnos za 6 m lepší než kontrolní
  skupina (5 akcií ze stejného oboru s podobným obratem). POTVRZENO jen při t ≥ 2 a stejném znaménku v obou polovinách.
- **Data:** USAspending.gov (zdarma, bez klíče), transakce zakázek — částka známá v den akce (součet „Award Amount“
  obsahuje i pozdější navýšení → nepoužito). Vstup až ≥ 7 dní po akci (měří se pokračování, ne reakce na oznámení).
  Tržní hodnota z akcií ze SEC známých k danému dni. Studie událostí z `smartmoney/events.py` (žádný nový duplicitní výpočet).
- **Krok 1 (všechny transakce ≥ 10 mil. USD, 2021-01…2026-09):** 53 921 transakcí, 20 181 nových zakázek, spárováno 98
  příjemců (2 479 zakázek) — téměř jen velké firmy. Skupina ≥ 10 % hodnoty firmy: **jen 5 případů** → nelze vyhodnotit;
  5–10 %: 8 případů, +7 % nad kontrolou (t 1,6); velké firmy (< 2 %, 1 556 případů): −1,6 % (t −0,6).
- **Krok 2 (cílené stažení):** zakázky ≥ 1 mil. USD pro 921 menších firem (20 mil.–5 mld. USD) z oborů s vládními
  zakázkami (obrana, letectví a vesmír, IT služby, stavby, elektronika, biotech/BARDA) → 2 313 transakcí. Předem
  doplněno: jedna událost na firmu a měsíc (největší zakázka).
- **Kontrola párování (na jménech, ne na výnosech):** shoda přes první dvě slova jména dala 3 chybné shody z 29 událostí
  ≥ 5 % hodnoty firmy (Asia Pacific Wire & Cable ← Asia Pacific Aerospace, Energy Services of America ← Energy
  Services Group, Alpha Technology Group ← Alpha Technology Associate). Jediná z nich (ATGL, +362 % nad kontrolou)
  zvedla průměr skupiny 5–10 % na +62 %. → platí jen přesná shoda celého jména.
- **Výsledek (874 událostí, 6 měsíců, nad kontrolní skupinou ze stejného oboru):**

| Zakázka / tržní hodnota | Případů | Medián výnosu | Nad kontrolou průměr (medián) | t | 2021–23 / 2024+ |
|---|---|---|---|---|---|
| **≥ 10 % (hlavní hypotéza)** | **6** | +9,6 % | +15,9 % (−1,9 %) | 0,8 | +6,1 % / +64,8 % (1 případ) |
| 5–10 % | 10 | +11,0 % | +4,5 % (+0,2 %) | 1,1 | +8,6 % / +0,4 % |
| 2–5 % | 35 | −4,9 % | −8,0 % (−3,2 %) | −1,5 | −3,9 % / −11,1 % |
| < 2 % (velké firmy) | 667 | +6,6 % | +1,9 % (+2,0 %) | 1,3 | +4,0 % / +0,2 % |

- **Verdikt:** NEOVĚŘENO — hlavní hypotéza má jen 6 případů za 5,7 roku (potřeba ≥ 30). Žádná skupina nemá výhodu
  s t ≥ 2 stabilní v obou polovinách; u velkých firem slábne k nule (2024+: +0,2 %).
- **Poučení:** velká zakázka vzhledem k velikosti firmy je u kótovaných firem vzácná (většina menších dodavatelů vlády
  je soukromá), takže jako systematický zdroj vítězů nestačí. Chybné párování jmen dokáže z jednoho případu vyrobit
  „objev“ → u každého nového zdroje nejdřív kontrola párování. Zapsáno `POUCENI-ZAKAZKY-SHODA-JMEN`. Zakázky se do
  modelu ani centra nezapojují; jednotlivou velkou zakázku lze brát jen jako ručně ověřený katalyzátor.

## E4 · 2026-10-11 · „Nejsilnější sázka“ fondů (SEC 13F) → výnos za 6 měsíců (nový typ informace)

- **Předloha:** Cohen, Polk & Silli (2010), „Best Ideas“ — pozice, kterou správce drží nejvíc nad běžnou vahou, měla
  v USA vyšší výnos než trh. Ověřuje se, zda to platí i v letech 2021–2026 a hlavně u menších firem.
- **Hypotéza (předem, před stažením dat):** akcie, která je „nejsilnější sázkou“ aspoň jednoho rozloženého správce,
  má za 6 měsíců vyšší výnos než kontrolní skupina (5 akcií ze stejného oboru s podobným obratem).
- **Protokol (pevný):**
  - data: SEC Form 13F Data Sets (zdarma, www.sec.gov, e-mail evidován), období zpráv 2021-03-31 … 2026-03-31;
  - správci: původní 13F-HR (bez dodatků) podané do 45 dní po konci čtvrtletí; 20–500 akciových pozic (bez opcí);
  - váha pozice w = hodnota / součet hodnot správce; běžná váha W = průměr w přes všechny takové správce v témže
    čtvrtletí (nezávisí na jednotkách, které SEC v roce 2023 změnila z tisíců na dolary);
  - nejsilnější sázka = mezi 20 největšími pozicemi správce ta s největším (w − W), jen akcie z našeho vesmíru
    (CUSIP → symbol ze souborů SEC Fails-to-Deliver; ETF a fondy vypadnou);
  - vstup = první závěr po 46. dni od konce čtvrtletí (všechny použité zprávy už jsou veřejné); jedna událost na
    akcii a čtvrtletí;
  - skupiny: G1 ≥ 1 správce (hlavní), G2 ≥ 3 správci, G3 = G1 u firem < 2 mld. USD;
  - POTVRZENO jen při t ≥ 2 (přes kalendářní měsíce) a stejném znaménku v obou polovinách (do 2023 / od 2024);
    vedle toho podíl +40 % a −25 % za 6 m.
- **Před výnosy:** kontrola párování CUSIP → symbol na jménech (poučení E3).
- **Kontrola párování (2026-10-11, jen jména, výnosy ještě neviděny):** 22 čtvrtletí, 3 118–6 254 správců za
  čtvrtletí; 30 567 CUSIP ze 23 souborů Fails-to-Deliver. Nalezeno a opraveno:
  1. náš seznam firem obsahuje i uzavřené fondy (Nuveen, PIMCO, BlackRock…) → vyřazeno 281 fondů podle jména;
  2. ticker přidělený znovu (Barnes Group „B“ → Barrick „B“ 2025; ceny jsou podle dnešního tickeru) → u tickeru
     platí jen nejnovější CUSIP, starší jen u stejné firmy (stejné první slovo);
  3. chyby správců: u ETF nebo jiné firmy uvedou cizí CUSIP („SPDR S&P 500“ s CUSIP Sherwin-Williams, „ALPHABET
     INC-C“ s CUSIP Global Net Lease) → taková pozice by vypadala jako nejsilnější sázka. Pozice se přijme jen když
     jméno z 13F odpovídá našemu jménu, popisu z FTD nebo jménu, které pro CUSIP v čtvrtletí používají ≥ 2 správci
     (odmítnuto 1,7 % pozic).
  Po opravách: 20 696 událostí, shoda prvního slova jména 95,7 %, náhodný vzorek 40 bez chyby; zbylé neshody jsou
  převážně přejmenování (J2 → Ziff Davis, MicroStrategy → Strategy, Square → Block).
- **Výsledek (fund_runs #1–#2, 6 měsíců nad kontrolou ze stejného oboru s podobným obratem):** ceny začínají 2021-10,
  takže efektivně 18 čtvrtletí (vstupy 2021-11 … 2026-02); 20 635 událostí, ve studii 19 002.

| Skupina | Případů | Nad kontrolou průměr (medián) | t | t Newey-West | 2021–23 / 2024+ (t) | +40 % / −25 % |
|---|---|---|---|---|---|---|
| **G1 ≥ 1 správce (hlavní)** | 17 187 | **+0,9 %** (−0,3 %) | **3,4** | 3,1 | +1,3 % (4,7) / +0,4 % (1,1) | 7,8 % / 12,0 % |
| G2 ≥ 3 správci | 4 131 | +1,5 % (+0,2 %) | 3,5 | 3,1 | +2,2 % (4,2) / +0,8 % (1,3) | 7,3 % / 7,2 % |
| G3 malé firmy < 2 mld. USD | 3 126 | +1,9 % (−0,7 %) | 2,7 | 2,6 | +2,8 % (4,3) / +1,0 % (0,8) | 11,5 % / 17,6 % |
| Všechny akcie (stejné dny) | 59 789 | – | – | – | – | 9,4 % / 18,5 % |

- **Verdikt podle předem daného pravidla:** POTVRZENO (G1: t 3,4 ≥ 2, kladné v obou polovinách; i po korekci na
  překryv 6 měsíců t 3,1). **Prakticky slabé:** +0,9 % za 6 m, medián pod kontrolou (výhoda jen v pravém chvostu),
  od 2024 slábne (t 1,1). Šance na +40 % NENÍ vyšší než u všech akcií (G1 7,8 % proti 9,4 %); nižší je riziko −25 %
  (velké firmy). G2 jsou převážně obří firmy (AAPL je nejsilnější sázkou 662 malých správců, NVDA 512) — od 2024 ~0.
  Malé firmy (G3) +1,9 %, ale po čtvrtletích kolísají (2024-11 −5 %, 2025-05 −4 %, 2025-08 až 2026-02 +4 až +5 %).
- **Použití (v0.12.0):** modul `fondy` (příkaz `funds`, čtvrtletně, jen při nové sadě SEC) → do centra jen aktuální
  sázky na MALÉ firmy (G3, cíl uživatele = menší firmy), role `FONDY_13F:sazka` s menším z t (obyčejné / Newey-West)
  = 2,6 → OVĚŘENO, ale váha důkazu nejvýš 0,5 (malý a kolísavý efekt). Není to výběr raket; je to slabý kladný náklon.
- **Poučení:** u nového zdroje rozhodla kvalita párování (fondy v seznamu akcií, znovu přidělené tickery, chybné
  CUSIP správců) — bez ní by „nejsilnější sázky“ obsahovaly ETF a cizí firmy. Zapsáno `POUCENI-FONDY-13F`.

## N-1 · 2026-10-15 · Doplnění registru testů o studii smart money (experiment N-1 pokračuje)

**Pravidlo dané předem (před výpočtem dopadu):** do `docs/testy_hypotez.jsonl` se zapíše KAŽDÁ t-statistika ze studie
smart money (`smart_money_runs #4`, data k 2026-10-09), bez výběru podle výsledku (`hub/multitest.smart_money_rows`).

| | Před (13 testů E1–E4) | Po (481 testů) |
|---|---|---|
| Testů ze studie smart money | 0 | 468 (|t| ≥ 2: 112, |t| ≥ 3: 30; testy se překrývají — stejné události, horizonty a období) |
| Varování 1 m (t 3,68) | prošlo, q (BY) 0,012 | prošlo, q 0,052 |
| Varování 6 m (t 3,98) | prošlo, q 0,007 | prošlo, q 0,023 |
| Nákup insiderů (t 3,05) | prošlo, q 0,046 | **NEPROŠLO**, q 0,24 |
| Fondy 13F u malých firem (t 2,56) | neprošlo, q 0,15 | neprošlo, q 0,56 |

**Závěr:** po poctivém započtení všech testů studie smart money už „nákup insiderů“ přísné pravidlo nesplňuje. Podle
Chordia–Goyal–Saretto (RFS 2020) by práh pro časové řady byl dokonce 3,84 — pak by prošlo jen varování 6 m. Váhy se
NEMĚNÍ (N-1 jen zapisuje do 2027-01-06); do té doby rozhodnou živé výsledky. Chybí ještě varianty modelů signálů a
studie E2 (doplnit).

**Doplnění 2026-10-16:** pravidlo dané předem — každá t ze všech vyhodnocení modelů (`model_evaluations`: SIGNAL_14D,
SIGNAL_1M, SIGNAL_6M, CAUSAL_CHAINS, INSIDER_X_6M; u opakovaného vyhodnocení téhož modelu, konfigurace a období jen
poslední; 3 testy E1 už evidované se nezdvojí); E2 už v registru byl. +111 testů → **592 celkem**. Varování 1 m
q (BY) 0,038, varování 6 m 0,017 (prošla), nákup insiderů 0,22 a fondy 13F 0,56 (neprošly). Závěr se nemění.

**Doplnění 2026-10-20 (síla přísného pravidla):** v registru 592 testů odpovídá q (BY) ≤ 0,10 prahu zhruba
**t ≈ 3,4** (t 3,0 → q 0,24; t 3,5 → q 0,07; t 3,84 → q 0,03); q (BH) ≤ 0,10 by stačilo t ≈ 2,5. Hrubý odhad síly
(normální aproximace): role se skutečným efektem t = 3 projde jen asi ve 34 %, t = 4 asi v 72 %. Přísné pravidlo
tedy často přehlédne skutečné, ale menší efekty (Harvey–Liu 2020) — při vyhodnocení N-1 uvést i tuto sílu.

## Zvážené, ale odložené hypotézy

| Hypotéza | Proč odloženo (2026-10-11) |
|---|---|
| Spin-offy (SEC 10-12B) po prvním měsíci obchodování porážejí obor | cenová data obsahují jen dnes obchodované firmy (zkreslení přeživších), ~150 případů za 5 let, literatura rozporná (2010–2019 spin-offy zaostávaly o −2,7 % ročně, jiné studie +8 % proti oboru) → výsledek by nebyl spolehlivý |

## Opravy nalezené při průzkumu (2026-10-11)

| Nález | Dopad | Oprava |
|---|---|---|
| Model raket vybíral pravidlo řazení (z 5) přímo na testovacích datech | test nebyl nezávislý; výsledky raket mohly vypadat lepší | výběr na validačních pololetích před testem (`rocket.choose_ranking`), test jen měří |
| Kauzální radar počítal šok komodity jen k poslednímu dni cen akcií (týdenní stažení) | pohyby komodit během týdne radar neviděl, karty se opakovaly | šok z denních cen k dni běhu (`exposure.daily_shock`); citlivost a „v ceně“ dál k datu cen akcií |
| Vyhodnocení predikcí čekalo na 21:00 UTC | večerní běh v létě dnešní závěr neviděl | závěrka New York 16:15 místního času (v0.10.1) |
| xtb.com blokuje server (HTTP 403) | žebříčky by se po 30 dnech vyprázdnily | poslední známé ověření s datem; registr ukazuje BLOKOVÁNO (v0.10.1) |
