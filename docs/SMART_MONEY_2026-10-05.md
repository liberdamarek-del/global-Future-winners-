# Smart money — historická a aktuální analýza velkých nákupů akcií

**Datum:** 2026-10-05 · **Běh:** smart money #3 (2026-10-05T08:51:08Z) · **Ceny do:** 2026-10-02 · **Verze:** v0.5.0
**Data ke každé transakci:** `data/smart_money_udalosti.csv` (106 015 řádků; insideři, politici, 13D/13G,
buybacky) a `data/smart_money_politici.csv` — vznikají příkazem `python -m stockradar smart-money` (nejsou v gitu kvůli velikosti).

> Pravidla zprávy: žádná data nejsou vymyšlená. Co nejde ověřit, je označeno **NEOVĚŘENO**. Primární zdroje jsou SEC
> (Form 4, 13D/13G, 10-K/10-Q/8-K, XBRL) a oficiální výkazy Kongresu; média jen jako doplněk (u Trumpa).
> Nic z toho není doporučení k nákupu.

---

## 0. Odpověď na hlavní otázku

**„Existuje v datech skutečně opakovatelný vzorec, že určité typy nákupů velkých hráčů, insiderů, politiků nebo firem
předcházejí nadprůměrnému růstu akcií?“**

**Ne — opakovatelný (stabilní v čase a statisticky potvrzený) vzorec jsem v datech 2021–2026 nenašel.**

- **Nejsilnější typ v historii** byl **aktivní nákup insidera (kód P, vlastní peníze, bez plánu 10b5-1) po propadu akcie
  o 30 % a víc od ročního maxima**: v letech 2021–2024 porazil pasivní transakce (odměny, opce) ve stejném měsíci
  o **+5,7 % za 6 měsíců (t +4,94)**. Jenže v letech 2025–2026, které model neviděl, vyšel
  **−5,1 % (t −2,30)** — výhoda se otočila. Vzorec tedy **nebyl opakovatelný**.
- Aktivní nákupy insiderů celkem: učení 2021–24 +2,1 % (t +2,91) → test 2025–26
  −4,1 % (t −2,90). Po letech (nad kontrolní skupinou za 6 m): 2021 −2,4 %, 2022 +3,0 %, 2023 +3,3 %, 2024 +7,2 %, 2025 −0,1 %, 2026 −0,3 %.
- **Kladně v obou obdobích, ale bez statistické jistoty** (t < 2 aspoň v jednom): 10% vlastník — bez propadu (do −10 %): +6,1 % → +4,1 %; CFO — po propadu 30 %+: +8,2 % → +2,0 %; CFO — mikro (obrat < 1 mil. USD/den): +1,9 % → +1,6 %; 10% vlastník: +1,1 % → +1,3 %; 10% vlastník — mikro (obrat < 1 mil. USD/den): +1,0 % → +2,6 %. Tohle je jediné, co se dá nazvat „slabě opakovatelné“ — nejčastěji
  **CFO** a **10% vlastníci (fondy, majitelé)**. Na sázku to nestačí; slouží to jen k řazení signálů.
- **Politici (Kongres) jako celek:** 6 111 změřených aktivních nákupů, za 6 m −1,6 % proti
  kontrolní skupině (t −0,70), S&P 500 porazilo 43 % → **žádná výhoda.**
- **Nancy Pelosi:** průměr vypadá dobře (12 m nad Nasdaq 100 +11,3 %, n = 21), ale medián za 6 m
  −0,5 %, QQQ porazila za 6 m jen v 48 % nákupů a výsledek táhne pár obchodů
  (NVDA 11/2023). **Statisticky neprokázané** (6 m nad kontrolní skupinou +14,6 %, t +0,58, n = 11). „Pelosi koupila → akcie vyroste“ data **nepotvrzují**.
- **Velké podíly:** nové 13D (aktivista) **−8,0 % za 6 m (t −4,32)**,
  13G −2,4 % (t −2,41) → **spíš negativní signál** (malé firmy, SPAC, restrukturalizace).
- **Buybacky:** žádný statisticky významný efekt; buyback ≥ 2 % při **klesajících** tržbách porazil S&P za 12 m jen
  v 28 % případů (maskování slabosti).
- **Závěr pro praxi:** nákup „smart money“ sám o sobě **nepředpovídá** nadprůměrný růst. Může být jedním z několika
  znaků (spolu s fundamentem a katalyzátorem); proto žádný aktuální signál nemá verdikt VYSOKÁ.

---

## 1. Data a zdroje

| Zdroj | Typ | Co | Období | Počet |
|---|---|---|---|---|
| [SEC Insider Transactions Data Sets](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets) | primární (Form 3/4/5) | každá transakce: kdo, role, kód, akcie, cena, plán 10b5-1, prodeje kupujících | podání 2021-10 → 2026-03 | 52 997 změřených událostí (firma × den × typ; pasivní jen 20% vzorek) |
| [Form 4 XML na sec.gov](https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4) | primární | ověření každého aktuálního signálu (kód, cena, plán, prodej do 10 dní) | posledních 60 dní | 2 Form 4 na signál |
| [openinsider.com](http://openinsider.com/) | sekundární | jen seznam čerstvých nákupů (SEC sady končí 2026Q1) | 60 dní | 1 245 nákupů |
| [Sněmovna — Clerk PTR](https://disclosures-clerk.house.gov/FinancialDisclosure) | primární (PDF) | obchody poslanců a jejich rodin | 2021 → 2026 | 7 771 nákupů |
| [Senát — eFD](https://efdsearch.senate.gov/search/) | primární (HTML) | obchody senátorů a rodin | 2021 → 2026 | 1 248 nákupů |
| [SEC EDGAR full-index](https://www.sec.gov/Archives/edgar/full-index/) | primární | 13D, 13G (nové podíly > 5 %), 10-K/10-Q/8-K | 2021 → 2026 | 3 496 × 13D, 31 995 × 13G |
| [SEC XBRL frames](https://data.sec.gov/api/xbrl/frames/us-gaap/PaymentsForRepurchaseOfCommonStock/USD/CY2024.json) | primární | skutečně vyplacené zpětné odkupy za rok (cash flow) | 2020 → 2025 | 8 508 firmo-let |
| Yahoo Finance chart API | sekundární (ceny) | denní ceny 12 158 firem, SPY, QQQ | 2021-10 → 2026-10-02 | |
| [ClinicalTrials.gov](https://clinicaltrials.gov/) | primární | blížící se konce studií fáze 3 (katalyzátor) | aktuální | |

**E-mail:** dotazy na www.sec.gov / data.sec.gov nesou e-mail (SEC to vyžaduje); každé použití je v `email_usage`.

## 2. Metodika (předem daná, ne vybraná podle výsledku)

1. **Událost** = firma × den zveřejnění × typ transakce (víc osob a řádků v jeden den se sečte).
2. **Vstup až den PO zveřejnění** (první závěrečná cena po dni podání) — dřív se o obchodu nedalo vědět.
   Zpoždění zveřejnění (medián): insideři 2 dny, Sněmovna 28 dní,
   Senát 30 dní.
3. **Horizonty:** 1 týden (5 obchodních dní), 1, 3, 6, 12 měsíců (21/63/126/252 dní); maximum a minimum ceny do 6 měsíců.
4. **Srovnání:** S&P 500 (SPY), u technologií politiků Nasdaq 100 (QQQ), a **kontrolní skupina** = 5 náhodných firem ze
   stejného oboru a podobného obratu (1/3× až 3×) ve stejný den. Výnosy nad +500 % se pro průměr ořezávají.
5. **Statistika:** t přes kalendářní měsíce (nákupy ve stejném měsíci nejsou nezávislé); |t| ≥ 2 ≈ málo pravděpodobná náhoda.
6. **Typ transakce (zadání §3):**
   - **AKTIVNÍ NÁKUP** — kód P (nákup na trhu za vlastní peníze), bez plánu 10b5-1, akcie se neprodaly do 10 dní;
     u politiků nákup bez poznámky o uplatnění opce, reinvestici nebo správci.
   - **AUTOMATICKÝ** — kód P v předem nastaveném plánu 10b5-1 (příznak AFF10B5ONE); u politiků reinvestice dividend.
   - **PASIVNÍ** — kód A (přidělené akcie, odměna), kód M (uplatnění opce), nákup se slevou > 12 % proti trhu
     (zaměstnanecký plán); u politiků uplatnění opce nebo obchod správce.
   - **NEJASNÉ** — chybí cena, nebo insider koupené akcie **do 10 dní prodal** (347 případů,
     nově v této verzi — viz chyba WIX v kap. 9).
7. **Hlavní past:** i **pasivní** transakce (odměny, opce) „porážejí“ kontrolní skupinu (6 m: přidělení +1,6 %,
   t +2,84; opce +2,1 %, t +3,37). Firmy, které podávají Form 4, jsou
   jiná populace než náhodná kontrola (a v cenových datech chybí firmy, které mezitím zkrachovaly a zmizely z burzy —
   **survivorship bias**). **Férový přínos aktivního nákupu = aktivní − pasivní ve stejném měsíci a stejné situaci.**
8. **Učení a test:** učení = zveřejnění do 2024-12-31, test = od 2025-01-01 (data, která model ani pravidla neviděla).
9. **Katalyzátor po nákupu:** v CSV je jen to, co je v primárních datech — dny do dalšího 10-Q/10-K a počet 8-K do 90 dní.
   Konkrétní obsah katalyzátoru (výsledky studie, smlouva) je u historie **NEOVĚŘENO**.
10. **Neanalyzováno (NEOVĚŘENO):** short interest (zdarma bez historie), 13F (čtvrtletní držby fondů, zpoždění 45 dní),
    oznámení buybacků z 8-K (měří se skutečně vyplacené odkupy), EPS (jen mechanicky přes počet akcií).

## 3. Insideři (CEO, CFO, ředitelé, 10% vlastníci)

### 3.1 Výsledky po zveřejnění (vstup den po podání Form 4)


| Skupina | Počet | Medián 1 t | Medián 1 m | Medián 3 m | Medián 6 m | Medián 12 m | Max růst 6 m (medián) | Max pokles 6 m (medián) | Porazilo S&P 6 m | Nad kontrolou 6 m (průměr) | t (6 m) | Nad kontrolou 12 m | t (12 m) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Insider: přidělené akcie (odměna) | 8 523 | −0,1 % | −0,3 % | −1,0 % | −0,2 % | +0,9 % | +17,1 % | −16,1 % | 39 % | +1,6 % | +2,84 | +3,3 % | +3,82 |
| Insider: uplatnění opce | 9 228 | −0,1 % | −0,8 % | −1,2 % | −0,7 % | +0,5 % | +16,3 % | −16,8 % | 40 % | +2,1 % | +3,37 | +3,5 % | +3,98 |
| Insider: nákup a do 10 dní prodej (např. zaměstnanecký plán) | 328 | −0,1 % | −1,6 % | −1,8 % | −5,6 % | −0,7 % | +10,0 % | −14,7 % | 27 % | −3,6 % | −1,67 | +7,0 % | +0,94 |
| Insider: AKTIVNÍ nákup (všechny) | 30 657 | +0,0 % | −0,4 % | +0,0 % | −0,1 % | −0,8 % | +17,2 % | −15,6 % | 38 % | +2,8 % | +2,67 | +4,1 % | +2,83 |
| Insider aktivní: 3+ insideři do 30 dní | 7 152 | +0,0 % | −0,7 % | +0,1 % | −0,2 % | −1,9 % | +17,6 % | −15,4 % | 39 % | +3,0 % | +3,15 | +5,0 % | +2,46 |
| Insider aktivní: hodnota ≥ 1 mil. USD | 3 363 | +0,1 % | −1,0 % | −1,7 % | −1,9 % | −3,3 % | +18,4 % | −20,4 % | 37 % | +0,5 % | −0,28 | +2,2 % | +0,71 |
| Insider aktivní: mikro (obrat < 1 mil. USD/den) | 11 852 | +0,0 % | −0,5 % | −0,2 % | −0,8 % | −1,6 % | +17,1 % | −15,1 % | 37 % | +3,6 % | +1,62 | +5,3 % | +1,73 |
| Insider aktivní: CEO | 6 651 | +0,0 % | −0,8 % | −1,6 % | −3,3 % | −5,0 % | +18,3 % | −19,1 % | 36 % | +2,3 % | +0,87 | +2,6 % | +0,16 |
| Insider aktivní: pod 25 tis. USD | 10 569 | +0,0 % | −0,2 % | +0,0 % | −0,3 % | −0,9 % | +16,1 % | −14,0 % | 38 % | +1,9 % | +0,76 | +3,5 % | +0,95 |
| Insider aktivní: 10% vlastník (fond, majitel) | 4 268 | +0,2 % | −0,0 % | +0,4 % | +0,9 % | +0,2 % | +16,5 % | −16,0 % | 35 % | +3,5 % | +1,84 | +4,8 % | +1,74 |
| Insider aktivní: jen člen představenstva | 11 797 | −0,1 % | −0,4 % | +0,4 % | +0,9 % | +1,7 % | +16,6 % | −14,5 % | 40 % | +2,9 % | +3,03 | +6,0 % | +5,06 |
| Insider aktivní: 100 tis.–1 mil. USD | 8 855 | −0,0 % | −0,5 % | +0,1 % | −0,2 % | −0,9 % | +17,0 % | −16,2 % | 37 % | +2,7 % | +2,12 | +4,0 % | +1,87 |
| Insider aktivní: CFO | 2 465 | +0,0 % | −0,1 % | +0,8 % | −0,2 % | −1,5 % | +20,4 % | −16,4 % | 41 % | +5,7 % | +2,94 | +7,6 % | +2,92 |
| Insider aktivní: pozice navýšena o 20 %+ | 9 215 | −0,0 % | −0,5 % | −0,5 % | −1,0 % | −2,2 % | +17,3 % | −16,8 % | 37 % | +2,4 % | +2,13 | +4,1 % | +1,86 |
| Insider: nejasné (bez ceny) | 246 | +0,0 % | −2,7 % | −2,8 % | +0,9 % | −7,9 % | +23,2 % | −21,5 % | 44 % | +6,8 % | +0,49 | +2,8 % | −0,13 |
| Insider aktivní: velké (obrat > 20 mil. USD/den) | 7 180 | +0,1 % | +0,0 % | +1,4 % | +2,7 % | +4,3 % | +18,7 % | −14,8 % | 44 % | +1,9 % | +1,38 | +3,8 % | +2,04 |
| Insider aktivní: malé (1–20 mil. USD/den) | 11 625 | −0,1 % | −0,5 % | −0,6 % | −1,0 % | −2,5 % | +16,3 % | −16,7 % | 36 % | +2,4 % | +2,22 | +3,0 % | +1,61 |
| Insider aktivní: po propadu 30 %+ od ročního maxima | 12 758 | +0,0 % | −0,7 % | +0,5 % | −0,6 % | −1,4 % | +27,1 % | −21,6 % | 39 % | +4,9 % | +3,91 | +7,7 % | +4,53 |
| Insider aktivní: po růstu 50 %+ za 6 měsíců | 1 579 | +0,0 % | −0,3 % | −2,9 % | −6,6 % | −8,3 % | +29,7 % | −25,8 % | 37 % | +5,5 % | +2,06 | +9,2 % | +1,27 |
| Insider aktivní: CEO/CFO po propadu 30 %+ | 4 255 | −0,1 % | −0,8 % | −0,9 % | −3,2 % | −5,7 % | +26,4 % | −23,6 % | 37 % | +4,4 % | +2,12 | +5,5 % | +1,36 |
| Insider aktivní: 3+ insideři po propadu 30 %+ | 3 234 | +0,0 % | −0,1 % | +1,3 % | +0,1 % | −2,5 % | +25,7 % | −20,3 % | 38 % | +4,4 % | +2,57 | +6,1 % | +1,50 |
| Insider: automatický nákup (plán 10b5-1) | 1 039 | +0,4 % | +1,4 % | +3,0 % | −0,2 % | +5,5 % | +22,4 % | −17,2 % | 38 % | +7,0 % | +1,82 | +11,8 % | +1,76 |

Čtení: medián výnosu 6 m u aktivních nákupů −0,1 %, S&P porazilo jen 38 %
(trh 2021–26 táhlo pár velkých firem); proti kontrolní skupině +2,8 % (t +2,67) — ale
pasivní transakce mají +1,6 % až +2,1 %, takže skutečný přínos je rozdíl (3.2).

### 3.2 Aktivní nákup minus pasivní transakce ve stejném měsíci a situaci (férové srovnání)

**Celé období 2021–2026:**


| Situace | Kdo nakupuje | Aktivních nákupů | Měsíců | Aktivní − pasivní (6 m) | t | Kladných měsíců |
|---|---|---|---|---|---|---|
| vše | aktivní nákup (vše) | 30 657 | 54 | +0,4 % | +0,53 | 61 % |
| vše | CEO | 6 651 | 54 | −0,4 % | −0,26 | 52 % |
| vše | CFO | 2 465 | 54 | +3,1 % | +1,87 | 67 % |
| vše | jen člen představenstva | 11 797 | 54 | +0,6 % | +0,71 | 57 % |
| vše | 10% vlastník | 4 268 | 54 | +1,2 % | +0,84 | 56 % |
| vše | 3+ insideři do 30 dní | 7 152 | 54 | +1,1 % | +1,17 | 57 % |
| vše | hodnota ≥ 1 mil. USD | 3 363 | 54 | −2,0 % | −1,52 | 37 % |
| vše | pozice +20 % | 9 215 | 54 | +0,1 % | +0,12 | 46 % |
| po propadu 30 %+ | aktivní nákup (vše) | 12 758 | 48 | +2,3 % | +1,82 | 62 % |
| po propadu 30 %+ | CEO | 3 423 | 48 | +0,7 % | +0,30 | 60 % |
| po propadu 30 %+ | CFO | 1 225 | 48 | +6,2 % | +2,00 | 69 % |
| po propadu 30 %+ | jen člen představenstva | 4 446 | 48 | +0,4 % | +0,18 | 56 % |
| po propadu 30 %+ | 10% vlastník | 1 688 | 48 | +1,8 % | +0,51 | 44 % |
| po propadu 30 %+ | 3+ insideři do 30 dní | 3 234 | 48 | +2,5 % | +1,25 | 71 % |
| po propadu 30 %+ | hodnota ≥ 1 mil. USD | 1 440 | 48 | −3,1 % | −1,37 | 35 % |
| po propadu 30 %+ | pozice +20 % | 4 184 | 48 | −0,1 % | −0,04 | 50 % |
| bez propadu (do −10 %) | aktivní nákup (vše) | 4 931 | 48 | −1,3 % | −0,88 | 50 % |
| bez propadu (do −10 %) | CEO | 678 | 48 | +1,2 % | +0,45 | 44 % |
| bez propadu (do −10 %) | CFO | 280 | 48 | +3,6 % | +1,39 | 54 % |
| bez propadu (do −10 %) | jen člen představenstva | 1 860 | 48 | +0,1 % | +0,10 | 40 % |
| bez propadu (do −10 %) | 10% vlastník | 1 069 | 48 | +5,5 % | +1,61 | 69 % |
| bez propadu (do −10 %) | 3+ insideři do 30 dní | 769 | 48 | +1,6 % | +0,69 | 48 % |
| bez propadu (do −10 %) | hodnota ≥ 1 mil. USD | 533 | 48 | +1,4 % | +0,53 | 58 % |
| bez propadu (do −10 %) | pozice +20 % | 1 317 | 48 | +1,3 % | +0,64 | 48 % |
| velké (> 20 mil.) | aktivní nákup (vše) | 7 180 | 54 | +0,9 % | +0,87 | 56 % |
| velké (> 20 mil.) | CEO | 1 306 | 53 | −1,9 % | −1,14 | 49 % |
| velké (> 20 mil.) | CFO | 501 | 53 | +1,7 % | +0,80 | 57 % |
| velké (> 20 mil.) | jen člen představenstva | 3 289 | 54 | +1,6 % | +1,46 | 61 % |
| velké (> 20 mil.) | 10% vlastník | 888 | 52 | −1,9 % | −0,46 | 44 % |
| velké (> 20 mil.) | 3+ insideři do 30 dní | 1 276 | 53 | −0,1 % | −0,08 | 49 % |
| velké (> 20 mil.) | hodnota ≥ 1 mil. USD | 1 511 | 54 | −3,1 % | −1,76 | 44 % |
| velké (> 20 mil.) | pozice +20 % | 2 486 | 54 | −0,2 % | −0,15 | 59 % |

**Učení 2021–2024:**

| Situace | Kdo nakupuje | Aktivních nákupů | Měsíců | Aktivní − pasivní (6 m) | t | Kladných měsíců |
|---|---|---|---|---|---|---|
| vše | aktivní nákup (vše) | 22 217 | 39 | +2,1 % | +2,91 | 72 % |
| vše | CEO | 4 995 | 39 | +0,9 % | +0,46 | 54 % |
| vše | CFO | 1 729 | 39 | +4,3 % | +2,49 | 69 % |
| vše | jen člen představenstva | 8 572 | 39 | +2,0 % | +2,32 | 67 % |
| vše | 10% vlastník | 3 063 | 39 | +1,1 % | +0,62 | 54 % |
| vše | 3+ insideři do 30 dní | 5 399 | 39 | +1,8 % | +2,14 | 64 % |
| vše | hodnota ≥ 1 mil. USD | 2 402 | 39 | −3,5 % | −2,41 | 31 % |
| vše | pozice +20 % | 6 465 | 39 | +1,7 % | +1,88 | 59 % |
| po propadu 30 %+ | aktivní nákup (vše) | 8 983 | 33 | +5,7 % | +4,94 | 79 % |
| po propadu 30 %+ | CEO | 2 491 | 33 | +3,9 % | +1,40 | 67 % |
| po propadu 30 %+ | CFO | 823 | 33 | +8,2 % | +2,21 | 76 % |
| po propadu 30 %+ | jen člen představenstva | 3 188 | 33 | +4,3 % | +1,90 | 67 % |
| po propadu 30 %+ | 10% vlastník | 1 129 | 33 | +4,3 % | +0,85 | 46 % |
| po propadu 30 %+ | 3+ insideři do 30 dní | 2 399 | 33 | +4,6 % | +2,73 | 79 % |
| po propadu 30 %+ | hodnota ≥ 1 mil. USD | 969 | 33 | −4,2 % | −1,55 | 33 % |
| po propadu 30 %+ | pozice +20 % | 2 823 | 33 | +4,1 % | +2,52 | 64 % |
| bez propadu (do −10 %) | aktivní nákup (vše) | 3 235 | 33 | +1,6 % | +1,57 | 58 % |
| bez propadu (do −10 %) | CEO | 474 | 33 | +2,1 % | +0,57 | 46 % |
| bez propadu (do −10 %) | CFO | 192 | 33 | +4,9 % | +1,46 | 58 % |
| bez propadu (do −10 %) | jen člen představenstva | 1 194 | 33 | +0,2 % | +0,13 | 36 % |
| bez propadu (do −10 %) | 10% vlastník | 754 | 33 | +6,1 % | +1,30 | 73 % |
| bez propadu (do −10 %) | 3+ insideři do 30 dní | 502 | 33 | +1,0 % | +0,31 | 48 % |
| bez propadu (do −10 %) | hodnota ≥ 1 mil. USD | 359 | 33 | +0,2 % | +0,08 | 55 % |
| bez propadu (do −10 %) | pozice +20 % | 841 | 33 | +2,6 % | +0,99 | 48 % |
| velké (> 20 mil.) | aktivní nákup (vše) | 4 773 | 39 | +2,5 % | +2,15 | 64 % |
| velké (> 20 mil.) | CEO | 902 | 38 | +1,2 % | +0,70 | 60 % |
| velké (> 20 mil.) | CFO | 321 | 38 | +4,4 % | +2,20 | 60 % |
| velké (> 20 mil.) | jen člen představenstva | 2 150 | 39 | +2,8 % | +2,35 | 67 % |
| velké (> 20 mil.) | 10% vlastník | 553 | 37 | −2,9 % | −0,52 | 40 % |
| velké (> 20 mil.) | 3+ insideři do 30 dní | 839 | 38 | +1,7 % | +0,90 | 60 % |
| velké (> 20 mil.) | hodnota ≥ 1 mil. USD | 1 058 | 39 | −4,5 % | −2,16 | 46 % |
| velké (> 20 mil.) | pozice +20 % | 1 576 | 39 | +2,5 % | +1,77 | 67 % |

**Test 2025–2026 (mimo vzorek):**

| Situace | Kdo nakupuje | Aktivních nákupů | Měsíců | Aktivní − pasivní (6 m) | t | Kladných měsíců |
|---|---|---|---|---|---|---|
| vše | aktivní nákup (vše) | 8 440 | 15 | −4,1 % | −2,90 | 33 % |
| vše | CEO | 1 656 | 15 | −3,6 % | −1,45 | 47 % |
| vše | CFO | 736 | 15 | +0,1 % | +0,02 | 60 % |
| vše | jen člen představenstva | 3 225 | 15 | −3,1 % | −2,30 | 33 % |
| vše | 10% vlastník | 1 205 | 15 | +1,3 % | +0,67 | 60 % |
| vše | 3+ insideři do 30 dní | 1 753 | 15 | −1,0 % | −0,41 | 40 % |
| vše | hodnota ≥ 1 mil. USD | 961 | 15 | +1,9 % | +0,74 | 53 % |
| vše | pozice +20 % | 2 750 | 15 | −4,0 % | −2,52 | 13 % |
| po propadu 30 %+ | aktivní nákup (vše) | 3 775 | 15 | −5,1 % | −2,30 | 27 % |
| po propadu 30 %+ | CEO | 932 | 15 | −6,2 % | −1,51 | 47 % |
| po propadu 30 %+ | CFO | 402 | 15 | +2,0 % | +0,34 | 53 % |
| po propadu 30 %+ | jen člen představenstva | 1 258 | 15 | −8,2 % | −2,45 | 33 % |
| po propadu 30 %+ | 10% vlastník | 559 | 15 | −3,6 % | −1,35 | 40 % |
| po propadu 30 %+ | 3+ insideři do 30 dní | 835 | 15 | −2,2 % | −0,44 | 53 % |
| po propadu 30 %+ | hodnota ≥ 1 mil. USD | 471 | 15 | −0,7 % | −0,16 | 40 % |
| po propadu 30 %+ | pozice +20 % | 1 361 | 15 | −9,2 % | −2,80 | 20 % |
| bez propadu (do −10 %) | aktivní nákup (vše) | 1 696 | 15 | −7,8 % | −2,00 | 33 % |
| bez propadu (do −10 %) | CEO | 204 | 15 | −0,6 % | −0,16 | 40 % |
| bez propadu (do −10 %) | CFO | 88 | 15 | +0,9 % | +0,21 | 47 % |
| bez propadu (do −10 %) | jen člen představenstva | 666 | 15 | −0,1 % | −0,04 | 47 % |
| bez propadu (do −10 %) | 10% vlastník | 315 | 15 | +4,1 % | +1,07 | 60 % |
| bez propadu (do −10 %) | 3+ insideři do 30 dní | 267 | 15 | +3,1 % | +0,94 | 47 % |
| bez propadu (do −10 %) | hodnota ≥ 1 mil. USD | 174 | 15 | +4,0 % | +0,70 | 67 % |
| bez propadu (do −10 %) | pozice +20 % | 476 | 15 | −1,6 % | −0,52 | 47 % |
| velké (> 20 mil.) | aktivní nákup (vše) | 2 407 | 15 | −3,3 % | −1,79 | 33 % |
| velké (> 20 mil.) | CEO | 404 | 15 | −9,9 % | −3,10 | 20 % |
| velké (> 20 mil.) | CFO | 180 | 15 | −5,1 % | −0,97 | 47 % |
| velké (> 20 mil.) | jen člen představenstva | 1 139 | 15 | −1,6 % | −0,75 | 47 % |
| velké (> 20 mil.) | 10% vlastník | 335 | 15 | +0,5 % | +0,13 | 53 % |
| velké (> 20 mil.) | 3+ insideři do 30 dní | 437 | 15 | −4,8 % | −1,78 | 20 % |
| velké (> 20 mil.) | hodnota ≥ 1 mil. USD | 453 | 15 | +0,4 % | +0,11 | 40 % |
| velké (> 20 mil.) | pozice +20 % | 910 | 15 | −7,2 % | −2,12 | 40 % |

**Interpretace:** výhoda aktivních nákupů v letech 2021–24 (hlavně po propadu akcie) byla reálná a silná (t +4,94),
ale v 2025–26 zmizela a otočila se. Nejpravděpodobnější vysvětlení: v letech 2022–24 nakupovali insideři po velkém propadu
malých firem a ty se pak odrazily (návrat k průměru, ne informace insidera); v 2025–26 trh táhly jiné firmy
(AI, velké technologie) a nákupy insiderů ve slabých firmách slabé zůstaly. **CEO** nemá výhodu v žádném období
(celkem −0,4 % (t −0,26)); **velké nákupy ≥ 1 mil. USD** také ne (−2,0 % (t −1,52)).

### 3.3 Nákup po zveřejněné informaci vs. bez zprávy


| Situace | Počet | Nad kontrolou 6 m | t | Nad kontrolou 12 m | t (12 m) |
|---|---|---|---|---|---|
| Nákup do 10 dní po výsledcích / 8-K | 15 496 | +3,0 % | +2,59 | +4,5 % | +3,01 |
| Nákup bez zprávy v předchozích 10 dnech | 15 161 | +2,5 % | +1,65 | +3,7 % | +1,83 |

Nákupy „bez zprávy“ (kde by insider mohl mít vlastní informaci) **nejsou lepší** než nákupy po zveřejněných výsledcích.
Data nepodporují představu, že insider ví něco, co trh neví.

### 3.4 Nákupy s okamžitým prodejem (nově rozpoznané)

328 událostí, kdy insider koupil a do 10 dní prodal aspoň polovinu: za 6 m −3,6 % proti kontrole
(t −1,67), S&P porazilo 27 %. Nejsou to sázky na růst → vyřazeno z aktivních nákupů.

## 4. Velcí držitelé a fondy (13D / 13G)


| Skupina | Počet | Medián 1 t | Medián 1 m | Medián 3 m | Medián 6 m | Medián 12 m | Max růst 6 m (medián) | Max pokles 6 m (medián) | Porazilo S&P 6 m | Nad kontrolou 6 m (průměr) | t (6 m) | Nad kontrolou 12 m | t (12 m) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Velký podíl: 13D aktivista | 2 753 | −1,0 % | −2,7 % | −6,6 % | −12,3 % | −18,5 % | +18,7 % | −29,9 % | 28 % | −8,0 % | −4,32 | −13,9 % | −6,18 |
| Velký podíl: 13G pasivní investor | 24 409 | −0,4 % | −1,2 % | −3,1 % | −5,5 % | −2,9 % | +14,1 % | −22,2 % | 35 % | −2,4 % | −2,41 | −3,4 % | −2,74 |

Nové hlášení podílu nad 5 % **předchází podprůměrnému** vývoji (13D za 12 m −13,9 %, t −6,18;
S&P porazilo 24 %). Velká část 13D jsou malé firmy, SPAC a restrukturalizace (věřitelé přebírají podíl).
**Korelace, ne příčina** — 13D nákup akcii nepoškozuje, jen se objevuje u firem v potížích. Hedge fondy přes 13F: **NEOVĚŘENO**.

## 5. Zpětné odkupy (buybacky)

Měří se **skutečně vyplacené** odkupy za fiskální rok (výkaz peněžních toků, XBRL) vůči tržní kapitalizaci v den podání 10-K.
Oznámení programů z 8-K **NEOVĚŘENO** (text se neparsuje).


| Skupina | Počet | Medián 1 t | Medián 1 m | Medián 3 m | Medián 6 m | Medián 12 m | Max růst 6 m (medián) | Max pokles 6 m (medián) | Porazilo S&P 6 m | Nad kontrolou 6 m (průměr) | t (6 m) | Nad kontrolou 12 m | t (12 m) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Buyback 0–2 % | 3 207 | −0,5 % | −2,0 % | −2,5 % | +0,6 % | +0,7 % | +13,7 % | −15,1 % | 38 % | +1,2 % | +1,04 | +0,8 % | −0,63 |
| Buyback 2–5 % | 1 739 | −0,8 % | −2,8 % | −2,6 % | +1,0 % | +3,7 % | +12,9 % | −14,9 % | 37 % | +1,4 % | −0,02 | +0,7 % | +0,68 |
| Buyback ≥ 2 % při klesajících tržbách | 765 | −0,5 % | −3,5 % | −2,1 % | +1,1 % | −1,4 % | +15,5 % | −16,7 % | 36 % | +1,3 % | +0,79 | −5,8 % | −0,59 |
| Buyback žádný | 1 621 | −1,0 % | −2,1 % | −3,7 % | −1,3 % | −1,8 % | +14,0 % | −18,6 % | 38 % | +2,7 % | +1,38 | +1,6 % | +1,01 |
| Buyback nový nebo výrazně zvýšený (≥ 2 %) | 1 509 | −0,9 % | −3,0 % | −3,4 % | −0,3 % | +1,9 % | +13,8 % | −17,0 % | 39 % | +2,7 % | +0,09 | +2,9 % | +0,30 |
| Buyback ≥ 2 % při rostoucích tržbách | 1 412 | −0,5 % | −2,7 % | −1,2 % | +4,2 % | +9,4 % | +15,5 % | −14,0 % | 39 % | +1,9 % | −0,51 | +3,7 % | +0,96 |
| Buyback ≥ 2 % a počet akcií klesl o 3 %+ | 1 365 | −0,5 % | −3,3 % | −1,9 % | +2,9 % | +7,2 % | +15,3 % | −14,5 % | 39 % | +1,6 % | −0,09 | +2,5 % | +0,76 |
| Buyback ≥5 % kapitalizace | 1 459 | −0,6 % | −2,5 % | −2,5 % | +1,0 % | +3,9 % | +15,2 % | −16,0 % | 40 % | +2,3 % | −0,22 | +3,5 % | −0,47 |

Odpovědi na otázky zadání:
- **Velikost vůči kapitalizaci:** ani buyback ≥ 5 % kapitalizace nemá významný náskok (+2,3 % za 6 m, t −0,22).
- **Klesl počet akcií (EPS mechanicky roste)?** Buyback ≥ 2 % a počet akcií −3 % a víc: medián 12 m +7,2 %,
  nad kontrolou +2,5 % (t +0,76) — nevýznamné. Skutečný EPS: **NEOVĚŘENO**.
- **Následoval růst, nebo buyback maskoval slabost?** Při rostoucích tržbách medián 12 m +9,4 %;
  při klesajících −1,4 % a S&P porazilo jen 28 % → u firem s klesajícími
  tržbami buyback spíš **maskuje slabost**.
- **Kupuje firma levně, nebo draze?** Ocenění v okamžiku odkupu (P/S, P/E) zatím **NEOVĚŘENO** (není v datech po čtvrtletích).

## 6. Politici (Sněmovna a Senát USA)

### 6.1 Skupiny

| Skupina | Počet | Medián 1 t | Medián 1 m | Medián 3 m | Medián 6 m | Medián 12 m | Max růst 6 m (medián) | Max pokles 6 m (medián) | Porazilo S&P 6 m | Nad kontrolou 6 m (průměr) | t (6 m) | Nad kontrolou 12 m | t (12 m) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Politici: AKTIVNÍ nákup (všichni) | 6 111 | +0,4 % | +0,9 % | +2,0 % | +3,5 % | +7,5 % | +15,4 % | −10,7 % | 43 % | −1,6 % | −0,70 | −2,4 % | −0,17 |
| Politici: Sněmovna | 5 391 | +0,4 % | +0,8 % | +1,8 % | +3,1 % | +7,0 % | +15,1 % | −10,8 % | 42 % | −1,8 % | −0,89 | −2,7 % | +0,02 |
| Politici: Senát | 720 | +0,5 % | +2,0 % | +4,0 % | +6,2 % | +9,7 % | +17,3 % | −10,0 % | 45 % | −0,2 % | −0,24 | −0,5 % | −1,18 |
| Politici: pasivní | 125 | +0,4 % | +0,1 % | −2,6 % | +1,0 % | +3,9 % | +11,1 % | −11,8 % | 50 % | −4,0 % | −1,04 | −7,8 % | −0,99 |
| Politici: automatický | 278 | +0,1 % | +0,8 % | +1,2 % | +3,6 % | +4,4 % | +12,2 % | −8,8 % | 42 % | −0,0 % | +0,29 | +0,9 % | +1,16 |
| Politici: částka ≥ 250 tis. USD | 20 | +0,7 % | −2,8 % | −4,7 % | −2,7 % | −10,1 % | +11,1 % | −20,6 % | 40 % | +4,5 % | +0,68 | +0,3 % | −0,07 |
| Politici: nákup opcí | 47 | −0,5 % | −4,4 % | −12,8 % | −27,2 % | −35,4 % | +10,9 % | −40,1 % | 17 % | −12,5 % | −0,98 | −17,8 % | −0,70 |
| Politici: Nancy Pelosi (většinou manžel) | 11 | −1,4 % | −6,8 % | −9,3 % | −4,0 % | −26,4 % | +4,2 % | −27,5 % | 36 % | +14,6 % | +0,58 | +40,5 % | +1,86 |

### 6.2 Technologické nákupy politiků vs. Nasdaq 100 (QQQ)

1 818 nákupů: za 6 m porazilo QQQ 45,6 %, medián −2,3 %, průměr +1,7 %.
Průměr je kladný díky malému počtu velkých vítězů, ale medián (typický nákup) je záporný a QQQ porazila menšina nákupů.
**Efekt tedy dělá hlavně trh/technologie, ne nákup.**

### 6.3 Sektory (aktivní nákupy, 6 m)


| Sektor | Počet | Medián výnosu | Porazilo S&P | Nad kontrolou | t |
|---|---|---|---|---|---|
| Real Estate | 180 | +0,8 % | 35 % | +3,3 % | +2,99 |
| Basic Materials | 121 | +3,1 % | 47 % | +3,1 % | +1,27 |
| Health Care | 766 | +4,0 % | 44 % | +3,0 % | +2,38 |
| (neznámý) | 36 | +2,3 % | 33 % | +1,8 % | +0,86 |
| Consumer Discretionary | 1 225 | +2,3 % | 38 % | +0,6 % | −0,56 |
| Consumer Staples | 222 | −2,1 % | 27 % | −0,9 % | −0,87 |
| Utilities | 211 | +4,5 % | 48 % | −1,1 % | −1,68 |
| Energy | 285 | +8,7 % | 48 % | −1,2 % | −0,99 |
| Finance | 763 | +4,1 % | 44 % | −2,1 % | −1,39 |
| Industrials | 765 | +3,2 % | 42 % | −3,8 % | −2,86 |
| Technology | 1 366 | +5,6 % | 47 % | −4,6 % | −1,05 |
| Telecommunications | 156 | +3,4 % | 42 % | −13,5 % | −1,60 |

Statisticky lépe než kontrola ze stejného oboru (t ≥ 2): Real Estate, Health Care; hůř (t ≤ −2): Industrials.
Při 11 testovaných sektorech jsou 1–2 výsledky s |t| > 2 očekávatelné i náhodou → **NEOVĚŘENO jako trvalý vzorec**.

### 6.4 Jednotlivci (aspoň 15 nákupů v databázi; „Počet“ = změřené za 6 m; seřazeno podle výsledku proti kontrole)

Jména jsou přesně podle výkazů — tatáž osoba může být zapsána dvakrát (např. Greene, Franklin); sloučení **NEOVĚŘENO**.


| Politik | Počet | Medián 6 m | Porazilo S&P | Nad kontrolou 6 m | t |
|---|---|---|---|---|---|
| Zoe Lofgren | 11 | +9,6 % | 64 % | +16,4 % | +1,78 |
| Nancy Pelosi | 11 | −4,0 % | 36 % | +14,6 % | +0,58 |
| Cindy Axne | 14 | −4,7 % | 71 % | +13,6 % | +1,74 |
| Maria Elvira Salazar | 6 | +16,1 % | 50 % | +12,6 % | +0,92 |
| Kevin Hern | 19 | −12,2 % | 58 % | +10,5 % | +2,50 |
| Alan S. Lowenthal | 23 | +4,9 % | 65 % | +8,0 % | +2,11 |
| Pete Sessions | 15 | +4,4 % | 53 % | +6,9 % | +0,24 |
| Daniel S Sullivan | 12 | +14,5 % | 67 % | +6,7 % | +0,31 |
| C. Scott Franklin | 22 | −0,9 % | 36 % | +6,6 % | — |
| Katie Britt | 8 | +13,4 % | 62 % | +5,6 % | — |
| Thomas H. Kean | 43 | +3,4 % | 42 % | +5,6 % | +0,83 |
| Victoria Spartz | 15 | −0,5 % | 33 % | +5,1 % | +2,20 |
| John Curtis | 38 | +0,9 % | 47 % | +4,6 % | +1,66 |
| Christopher L. Jacobs | 63 | −6,1 % | 35 % | +2,7 % | +0,25 |
| Angus S King, Jr. | 22 | +8,9 % | 50 % | +2,7 % | +0,05 |
| Josh Gottheimer | 564 | +3,0 % | 47 % | +2,7 % | +1,49 |
| Tim Moore | 106 | +22,6 % | 71 % | +2,5 % | +0,00 |
| Richard Dean Dr McCormick | 42 | +1,8 % | 40 % | +2,4 % | — |
| William R. Keating | 22 | +10,9 % | 64 % | +2,2 % | +0,78 |
| Thomas H Tuberville | 270 | +0,4 % | 43 % | +2,0 % | +2,00 |
| John James | 107 | +0,8 % | 43 % | +2,0 % | — |
| Sheldon Whitehouse | 14 | +8,5 % | 50 % | +1,6 % | +0,65 |
| Kathy Manning | 243 | +0,1 % | 51 % | +0,9 % | +0,66 |
| Valerie Hoyle | 161 | −1,6 % | 45 % | +0,7 % | — |
| Markwayne Mullin | 204 | +14,0 % | 46 % | +0,6 % | +0,98 |
| Michael Patrick Guest | 32 | +11,1 % | 38 % | +0,4 % | −0,70 |
| Shelley M Capito | 30 | +12,2 % | 50 % | +0,2 % | +0,35 |
| Lisa McClain | 641 | +4,1 % | 46 % | −0,0 % | −1,08 |
| Julie Johnson | 69 | +14,7 % | 57 % | −0,4 % | +1,10 |
| Lois Frankel | 117 | +0,5 % | 42 % | −0,5 % | +0,69 |
| Virginia Foxx | 196 | −2,9 % | 40 % | −0,8 % | −0,68 |
| Rick Larsen | 16 | +6,4 % | 44 % | −0,8 % | −1,03 |
| Marjorie Taylor Mrs Greene | 94 | +1,0 % | 50 % | −1,1 % | −0,88 |
| Daniel Goldman | 203 | −1,3 % | 29 % | −1,2 % | −0,48 |
| Dan Newhouse | 74 | +6,4 % | 47 % | −1,7 % | −0,78 |
| Dwight Evans | 13 | +6,6 % | 62 % | −1,7 % | +0,33 |
| Michael C. Burgess | 31 | +5,8 % | 35 % | −1,8 % | −0,77 |
| Marjorie Taylor Greene | 192 | +6,7 % | 47 % | −1,9 % | +0,63 |
| Byron Donalds | 36 | −4,8 % | 25 % | −2,1 % | +0,48 |
| Earl Blumenauer | 27 | −0,1 % | 41 % | −2,1 % | −0,27 |
| Thomas Suozzi | 49 | +2,8 % | 49 % | −2,3 % | −0,09 |
| Jared Moskowitz | 158 | +5,2 % | 44 % | −2,4 % | −0,58 |
| Cleo Fields | 95 | +9,3 % | 53 % | −2,6 % | +0,74 |
| Julia Letlow | 122 | +2,4 % | 39 % | −2,8 % | — |
| James Comer | 18 | +8,1 % | 50 % | −3,6 % | — |
| Jefferson Shreve | 168 | +9,4 % | 33 % | −4,1 % | −0,75 |
| Robert J. Wittman | 27 | +2,3 % | 48 % | −4,6 % | −0,77 |
| Bruce Westerman | 68 | +17,0 % | 29 % | −4,8 % | — |
| Gilbert Cisneros | 484 | +2,8 % | 37 % | −5,1 % | −0,86 |
| Thomas R Carper | 69 | −5,3 % | 33 % | −5,4 % | −1,14 |
| Greg Stanton | 78 | +14,1 % | 38 % | −5,8 % | — |
| Richard W. Allen | 67 | +10,4 % | 45 % | −6,1 % | −1,57 |
| Jonathan Jackson | 86 | +4,8 % | 38 % | −7,2 % | −0,36 |
| David J. Taylor | 69 | +4,8 % | 32 % | −8,0 % | −0,93 |
| Carol Devine Miller | 27 | +1,1 % | 15 % | −9,8 % | −3,05 |
| Marie Newman | 5 | −76,6 % | 0 % | −10,3 % | — |
| Rob Bresnahan | 198 | +6,3 % | 30 % | −10,6 % | −3,85 |
| John Boozman | 52 | +15,3 % | 56 % | −11,6 % | −2,30 |
| Scott Scott Franklin | 29 | +0,7 % | 24 % | −11,9 % | −1,51 |
| April McClain Delaney | 105 | +1,4 % | 24 % | −12,2 % | −3,10 |
| Greg Landsman | 45 | +8,8 % | 49 % | −13,6 % | −2,32 |
| James R. Langevin | 45 | −27,3 % | 9 % | −16,9 % | −2,23 |

Z 62 politiků má t ≥ 2 jen 4: Kevin Hern (n = 19, t +2,50), Alan S. Lowenthal (n = 23, t +2,11), Victoria Spartz (n = 15, t +2,20), Thomas H Tuberville (n = 270, t +2,00); t ≤ −2 má 6: Carol Devine Miller (n = 27, t −3,05), Rob Bresnahan (n = 198, t −3,85), John Boozman (n = 52, t −2,30), April McClain Delaney (n = 105, t −3,10), Greg Landsman (n = 45, t −2,32), James R. Langevin (n = 45, t −2,23).
Při 62 testech je asi 3 výsledků s |t| ≥ 2 očekávatelných náhodou. Kladní mají t jen těsně nad 2
a nikdo z nich nebyl ověřen na datech mimo vzorek; výraznější jsou naopak politici, jejichž nákupy zaostávaly →
**žádný politik nemá prokázanou opakovatelnou výhodu** (kopírovat nikoho z nich data nedoporučují).

## 7. Nancy Pelosi — databáze a test

Zdroj: Sněmovna, výkazy PTR (obchody provádí převážně manžel Paul Pelosi, „SP“). V databázi 117 transakcí:
78 nákupů (z toho 58 aktivních, 20 uplatnění opcí)
a 39 prodejů. Změřit lze 33 aktivních nákupů
(nákupy z roku 2021 jsou před začátkem cenových dat, investice do soukromých firem a LLC nemají ticker).
U opcí se měří **podkladová akcie**, ne zisk opce (ten je pákový — **NEOVĚŘENO**).

**Statistika aktivních nákupů (vstup den po zveřejnění):**

| Srovnání | 1 m | 6 m | 12 m |
|---|---|---|---|
| Porazilo Nasdaq 100 (QQQ) | 58 % | 48 % | 62 % |
| Průměr nad QQQ | +5,1 % | +6,2 % | +11,3 % |
| Medián nad QQQ | +0,6 % | −0,5 % | +8,1 % |
| Počet | 33 | 25 | 21 |

Proti kontrolní skupině (6 m): +14,6 %, t +0,58, n = 11. Toto srovnání je
u Pelosi slabé: obří firmy (NVDA, AAPL, MSFT) nemají v oboru 5 firem s podobným obratem, takže zbude jen 11 nákupů
(převážně série z 12/2021) a výsledek se s jiným výběrem kontroly měnil od +3 % do +15 %. Rozhodující je srovnání s QQQ
výše. **Statisticky významné není ani jedno.** Silné průměry dělá několik obchodů: NVDA calls 11/2023 (+159 % za 6 m),
AVGO calls 6/2024 (+34 %), GOOGL calls 1/2025 (+67 % za 12 m). Proti tomu série z 12/2021 (GOOG, DIS, RBLX, CRM, MU calls)
skončila za 6 m −25 až −65 %.

**Korelace vs. příčina:** obchody jsou soustředěné do velkých technologií. Za 2021–26 rostly technologie silně celkově,
takže průměr nad QQQ je **hlavně expozice vůči sektoru a pár velkých sázek s pákou**, ne prokázaná informační výhoda.
Kopírování navíc přichází se zpožděním ~4 týdnů (Sněmovna medián 28 dní).

**Všechny nákupy Pelosi (aktivní i uplatnění opcí; výnosy od vstupu den po zveřejnění, v %):**


| Obchod | Zveřejněno | Ticker | Aktivum | Typ | Částka | Popis (PTR) | 1 t | 1 m | 3 m | 6 m | 12 m | Max 6 m | Min 6 m | vs S&P 6 m | vs QQQ 6 m | vs QQQ 12 m | Zdroj |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2020-12-22 | 2021-01-21 | AB | akcie | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 20,000 shares. | — | — | — | — | — | — | — | — | — | — | House PTR 20018011 |
| 2020-12-22 | 2021-01-21 | AAPL | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 100 call options with a strike price of $100 and an expirati | — | — | — | — | — | — | — | — | — | — | House PTR 20018011 |
| 2020-12-22 | 2021-01-21 | TSLA | opce | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 25 call options with a strike price of $500 and an expiratio | — | — | — | — | — | — | — | — | — | — | House PTR 20018011 |
| 2020-12-22 | 2021-01-21 | DIS | opce | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 100 call options with a strike price of $100 and an expirati | — | — | — | — | — | — | — | — | — | — | House PTR 20018011 |
| 2020-12-22 | 2021-04-09 | AB | kód OL | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 20,000 units in a global asset management firm providing inv | — | — | — | — | — | — | — | — | — | — | House PTR 20018539 |
| 2021-02-18 | 2021-03-09 | AB | akcie | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 15,000 shares. | — | — | — | — | — | — | — | — | — | — | House PTR 20018355 |
| 2021-02-18 | 2021-04-09 | AB | kód OL | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 15,000 units in a global asset management firm providing inv | — | — | — | — | — | — | — | — | — | — | House PTR 20018539 |
| 2021-02-23 | 2021-03-09 | AB | akcie | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 25,000 shares. | — | — | — | — | — | — | — | — | — | — | House PTR 20018355 |
| 2021-02-23 | 2021-04-09 | AB | kód OL | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 25,000 units in a global asset management firm providing inv | — | — | — | — | — | — | — | — | — | — | House PTR 20018539 |
| 2021-03-10 | 2021-04-09 | (bez tickeru) | kód OT | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 10,000 shares. | — | — | — | — | — | — | — | — | — | — | House PTR 20018539 |
| 2021-03-19 | 2021-04-09 | MSFT | akcie | PASIVNÍ | 1 000 001–5 000 000 USD | Exercised 150 call options (15,000 shares) expiring 3/19/2021 at a str | — | — | — | — | — | — | — | — | — | — | House PTR 20018539 |
| 2021-05-21 | 2021-07-02 | AMZN | opce | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 20 call options with a strike price of $3,000 and an expirat | — | — | — | — | — | — | — | — | — | — | House PTR 20019004 |
| 2021-05-21 | 2021-07-02 | AAPL | opce | AKTIVNÍ NÁKUP | 100 001–250 000 USD | Purchased 50 call options with a strike price of $100 and an expiratio | — | — | — | — | — | — | — | — | — | — | House PTR 20019004 |
| 2021-06-03 | 2021-07-02 | NVDA | opce | AKTIVNÍ NÁKUP | 1 000 001–5 000 000 USD | Purchased 50 call options with a strike price of $400 and an expiratio | — | — | — | — | — | — | — | — | — | — | House PTR 20019004 |
| 2021-06-18 | 2021-07-02 | GOOGL | akcie | PASIVNÍ | 1 000 001–5 000 000 USD | Exercised 40 call options (4,000 shares) expiring 6/18/21 at a strike  | — | — | — | — | — | — | — | — | — | — | House PTR 20019004 |
| 2021-07-13 | 2021-08-20 | (bez tickeru) | kód AB | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Investment in llC which is acquiring eleven Marriott-branded hotels (R | — | — | — | — | — | — | — | — | — | — | House PTR 20019331 |
| 2021-07-23 | 2021-08-20 | NVDA | akcie | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 5,000 shares. | — | — | — | — | — | — | — | — | — | — | House PTR 20019331 |
| 2021-07-23 | 2021-08-20 | NVDA | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 50 call options with a strike price of $100 and an expiratio | — | — | — | — | — | — | — | — | — | — | House PTR 20019331 |
| 2021-12-17 | 2021-12-29 | GOOG | opce | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 10 call options with a strike price of $2000 and an expirati | −5,8 % | −7,1 % | −4,4 % | −25,3 % | −39,2 % | +1,4 % | −27,5 % | −5,4 % | +4,2 % | −5,7 % | House PTR 20020106 |
| 2021-12-17 | 2021-12-29 | DIS | opce | AKTIVNÍ NÁKUP | 100 001–250 000 USD | Purchased 50 call options with a strike price of $130 and an expiratio | +0,6 % | −8,3 % | −12,0 % | −38,3 % | −44,3 % | +1,3 % | −40,2 % | −18,4 % | −8,8 % | −10,8 % | House PTR 20020106 |
| 2021-12-20 | 2021-12-29 | RBLX | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 100 call options with a strike price of $100 and an expirati | −11,3 % | −34,5 % | −54,0 % | −65,1 % | −71,7 % | +2,6 % | −76,9 % | −45,2 % | −35,6 % | −38,2 % | House PTR 20020106 |
| 2021-12-20 | 2021-12-29 | CRM | opce | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 100 call options with a strike price of $210 and an expirati | −10,3 % | −8,9 % | −16,8 % | −34,1 % | −48,1 % | +0,1 % | −39,1 % | −14,2 % | −4,6 % | −14,6 % | House PTR 20020106 |
| 2021-12-20 | 2021-12-29 | CRM | opce | AKTIVNÍ NÁKUP | 100 001–250 000 USD | Purchased 30 call options with a strike price of $210 and an expiratio | −10,3 % | −8,9 % | −16,8 % | −34,1 % | −48,1 % | +0,1 % | −39,1 % | −14,2 % | −4,6 % | −14,6 % | House PTR 20020106 |
| 2021-12-21 | 2021-12-29 | MU | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 100 call options with a strike price of $50 and an expiratio | +1,9 % | −12,4 % | −17,0 % | −42,9 % | −46,8 % | +3,7 % | −42,9 % | −22,9 % | −13,3 % | −13,3 % | House PTR 20020106 |
| 2021-12-22 | 2021-12-29 | TWO | kód AB | AKTIVNÍ NÁKUP | 50 001–100 000 USD | Additional investment in llC which acquired five Courtyard by Marriott | — | — | — | — | — | — | — | — | — | — | House PTR 20020106 |
| 2022-01-21 | 2022-02-28 | AXP | akcie | PASIVNÍ | 250 001–500 000 USD | Exercised 50 call options (5,000 shares) expiring 1/21/22 at a strike  | −10,1 % | +6,6 % | −5,2 % | −13,1 % | −1,5 % | +7,5 % | −23,4 % | −5,8 % | −1,3 % | +12,5 % | House PTR 20020515 |
| 2022-01-21 | 2022-02-28 | AAPL | akcie | PASIVNÍ | 1 000 001–5 000 000 USD | Exercised 100 call options (10,000 shares) expiring 1/21/22 at a strik | −3,5 % | +8,9 % | −8,8 % | −2,6 % | −10,6 % | +9,7 % | −20,3 % | +4,8 % | +9,2 % | +3,4 % | House PTR 20020515 |
| 2022-01-21 | 2022-02-28 | PYPL | akcie | PASIVNÍ | 500 001–1 000 000 USD | Exercised 50 call options (5,000 shares) expiring 1/21/22 at a strike  | −10,9 % | +11,2 % | −20,0 % | −13,8 % | −30,4 % | +14,4 % | −34,7 % | −6,4 % | −2,0 % | −16,4 % | House PTR 20020515 |
| 2022-01-21 | 2022-02-28 | DIS | akcie | PASIVNÍ | 1 000 001–5 000 000 USD | Exercised 100 call options (10,000 shares) expiring 1/21/22 at a strik | −9,6 % | −3,3 % | −24,2 % | −22,8 % | −32,1 % | +1,1 % | −37,0 % | −15,4 % | −11,0 % | −18,1 % | House PTR 20020515 |
| 2022-01-27 | 2022-02-28 | AB | kód OL | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 10,000 units in a global asset management firm providing inv | — | — | — | — | — | — | — | — | — | — | House PTR 20020515 |
| 2022-03-17 | 2022-03-21 | TSLA | akcie | PASIVNÍ | 1 000 001–5 000 000 USD | Exercised 25 call options (2,500 shares) expiring 3/18/22 at a strike  | +10,6 % | +1,5 % | −28,7 % | −9,2 % | −42,0 % | +15,2 % | −36,8 % | +6,8 % | +11,3 % | −28,8 % | House PTR 20020662 |
| 2022-05-13 | 2022-06-03 | AAPL | opce | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 100 call options with a strike price of $80 and an expiratio | −9,8 % | +0,1 % | +5,7 % | +0,3 % | +21,7 % | +19,4 % | −11,0 % | +3,3 % | +6,7 % | +8,1 % | House PTR 20021142 |
| 2022-05-24 | 2022-06-03 | AAPL | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 50 call options with a strike price of $80 and an expiration | −9,8 % | +0,1 % | +5,7 % | +0,3 % | +21,7 % | +19,4 % | −11,0 % | +3,3 % | +6,7 % | +8,1 % | House PTR 20021142 |
| 2022-05-24 | 2022-06-03 | MSFT | opce | AKTIVNÍ NÁKUP | 50 001–100 000 USD | Purchased 10 call options with a strike price of $180 and an expiratio | −9,9 % | −0,1 % | −5,8 % | −6,9 % | +20,3 % | +9,2 % | −20,3 % | −3,9 % | −0,5 % | +6,8 % | House PTR 20021142 |
| 2022-05-24 | 2022-06-03 | MSFT | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 40 call options with a strike price of $180 and an expiratio | −9,9 % | −0,1 % | −5,8 % | −6,9 % | +20,3 % | +9,2 % | −20,3 % | −3,9 % | −0,5 % | +6,8 % | House PTR 20021142 |
| 2022-06-17 | 2022-07-14 | NVDA | akcie | PASIVNÍ | 1 000 001–5 000 000 USD | Exercised 200 call options (20,000 shares) expiring 6/17/22 at a strik | +9,9 % | +20,7 % | −24,1 % | +7,2 % | +201,3 % | +21,9 % | −28,8 % | +3,7 % | +10,9 % | +169,2 % | House PTR 20021374 |
| 2022-08-24 | 2022-09-09 | TWO | kód AB | AKTIVNÍ NÁKUP | 15 001–50 000 USD | Additional investment in LLC which acquired five Courtyard by Marriott | — | — | — | — | — | — | — | — | — | — | House PTR 20021675 |
| 2022-09-16 | 2022-10-14 | GOOG | akcie | PASIVNÍ | 1 000 001–5 000 000 USD | Exercised 200 call options purchased 12/17/21 (20,000 shares) at a str | +2,2 % | −2,0 % | −8,9 % | +4,2 % | +38,2 % | +8,6 % | −17,2 % | −8,7 % | −14,1 % | +3,3 % | House PTR 20021837 |
| 2022-12-27 | 2023-01-12 | TWO | kód AB | AKTIVNÍ NÁKUP | 15 001–50 000 USD | Additional investment in LLC which acquired five Courtyard by Marriott | — | — | — | — | — | — | — | — | — | — | House PTR 20022260 |
| 2023-03-09 | 2023-04-06 | (bez tickeru) | kód AB | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Investment in LLC which is acquiring and restoring a luxury hotel prop | — | — | — | — | — | — | — | — | — | — | House PTR 20022664 |
| 2023-03-17 | 2023-04-06 | AAPL | akcie | PASIVNÍ | 500 001–1 000 000 USD | Exercised 100 call options purchased 5/13/22 (10,000 shares) at a stri | +2,0 % | +6,0 % | +16,1 % | +10,5 % | +3,5 % | +21,2 % | −1,2 % | +4,9 % | −4,9 % | −34,4 % | House PTR 20022664 |
| 2023-06-15 | 2023-06-22 | AAPL | akcie | PASIVNÍ | 250 001–500 000 USD | Exercised 50 call options purchased 5/24/22 (5,000 shares) at a strike | +3,9 % | +3,7 % | −6,4 % | +4,3 % | +12,0 % | +6,1 % | −10,6 % | −4,8 % | −8,2 % | −20,2 % | House PTR 20023192 |
| 2023-06-15 | 2023-06-22 | MSFT | akcie | PASIVNÍ | 500 001–1 000 000 USD | Exercised 50 call options purchased 5/24/22 (5,000 shares) at a strike | +1,6 % | +4,8 % | −5,4 % | +11,5 % | +34,6 % | +14,2 % | −6,8 % | +2,4 % | −1,0 % | +2,4 % | House PTR 20023192 |
| 2023-11-22 | 2023-12-21 | NVDA | opce | AKTIVNÍ NÁKUP | 1 000 001–5 000 000 USD | Purchased 50 call options with a strike price of $120 and an expiratio | −1,4 % | +26,2 % | +89,6 % | +158,9 % | +187,2 % | +177,7 % | −2,6 % | +143,7 % | +141,2 % | +157,4 % | House PTR 20024186 |
| 2024-02-12 | 2024-02-23 | PANW | opce | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 50 call options with a strike price of $200 and an expiratio | −1,1 % | −5,3 % | +6,2 % | +14,6 % | +23,9 % | +21,5 % | −12,4 % | +3,8 % | +5,8 % | +9,3 % | House PTR 20024542 |
| 2024-02-21 | 2024-02-23 | PANW | opce | AKTIVNÍ NÁKUP | 100 001–250 000 USD | Purchased 20 call options with a strike price of $200 and an expiratio | −1,1 % | −5,3 % | +6,2 % | +14,6 % | +23,9 % | +21,5 % | −12,4 % | +3,8 % | +5,8 % | +9,3 % | House PTR 20024542 |
| 2024-03-04 | 2024-03-21 | (bez tickeru) | kód AB | AKTIVNÍ NÁKUP | 1 000 001–5 000 000 USD | Investment in fund that owns Databricks stock. Databricks is a San Fra | — | — | — | — | — | — | — | — | — | — | House PTR 20024625 |
| 2024-06-24 | 2024-07-02 | AVGO | opce | AKTIVNÍ NÁKUP | 1 000 001–5 000 000 USD | Purchased 20 call options with a strike price of $800 and an expiratio | −1,3 % | −16,8 % | −1,3 % | +34,2 % | +57,2 % | +44,6 % | −21,2 % | +28,1 % | +30,2 % | +44,7 % | House PTR 20025368 |
| 2024-06-26 | 2024-07-02 | NVDA | akcie | AKTIVNÍ NÁKUP | 1 000 001–5 000 000 USD | Purchased 10,000 shares. | −0,7 % | −16,4 % | −7,4 % | +7,8 % | +24,7 % | +16,1 % | −22,9 % | +1,8 % | +3,9 % | +12,2 % | House PTR 20025368 |
| 2024-07-26 | 2024-07-30 | NVDA | akcie | AKTIVNÍ NÁKUP | 1 000 001–5 000 000 USD | Purchased 10,000 shares. | −15,5 % | +0,5 % | +20,7 % | +2,6 % | +53,8 % | +27,7 % | −15,5 % | −6,7 % | −8,3 % | +34,1 % | House PTR 20025535 |
| 2024-08-13 | 2024-09-11 | (bez tickeru) | kód AB | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Investment in LLC which is acquiring and managing a commercial office  | — | — | — | — | — | — | — | — | — | — | House PTR 20025819 |
| 2024-12-20 | 2025-01-17 | NVDA | akcie | PASIVNÍ | 500 001–1 000 000 USD | Exercised 500 call options purchased 11/22/23 (50,000 shares) at a str | −8,4 % | −0,5 % | −29,8 % | +21,3 % | +31,3 % | +22,8 % | −33,0 % | +16,1 % | +13,8 % | +13,0 % | House PTR 20026590 |
| 2024-12-20 | 2025-01-17 | PANW | akcie | PASIVNÍ | 1 000 001–5 000 000 USD | Exercised 140 call options purchased 2/12/24 & 2/21/24 (14,000 shares) | +5,1 % | +8,3 % | −10,8 % | +8,6 % | −0,7 % | +13,5 % | −16,9 % | +3,4 % | +1,1 % | −19,0 % | House PTR 20026590 |
| 2025-01-14 | 2025-01-17 | GOOGL | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 50 call options with a strike price of $150 and an expiratio | −1,4 % | −6,8 % | −23,5 % | −3,9 % | +66,9 % | +4,2 % | −26,9 % | −9,1 % | −11,4 % | +48,6 % | House PTR 20026590 |
| 2025-01-14 | 2025-01-17 | AMZN | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 50 call options with a strike price of $150 and an expiratio | +3,2 % | −3,4 % | −24,9 % | −1,0 % | +1,6 % | +4,9 % | −27,5 % | −6,2 % | −8,5 % | −16,7 % | House PTR 20026590 |
| 2025-01-14 | 2025-01-17 | NVDA | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 50 call options with a strike price of $80 and an expiration | −8,4 % | −0,5 % | −29,8 % | +21,3 % | +31,3 % | +22,8 % | −33,0 % | +16,1 % | +13,8 % | +13,0 % | House PTR 20026590 |
| 2025-01-14 | 2025-01-17 | TEM | opce | AKTIVNÍ NÁKUP | 50 001–100 000 USD | Purchased 50 call options with a strike price of $20 and an expiration | +7,1 % | +61,0 % | −9,3 % | +36,1 % | +43,5 % | +87,7 % | −21,9 % | +31,0 % | +28,7 % | +25,2 % | House PTR 20026590 |
| 2025-01-14 | 2025-01-17 | VST | opce | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 50 call options with a strike price of $50 and an expiration | −19,3 % | −12,0 % | −39,2 % | +8,0 % | −13,5 % | +8,0 % | −47,1 % | +2,8 % | +0,5 % | −31,8 % | House PTR 20026590 |
| 2025-06-20 | 2025-07-09 | AVGO | akcie | PASIVNÍ | 1 000 001–5 000 000 USD | Exercised 200 call options purchased 6/24/24 (20,000 shares) at a stri | +4,0 % | +10,7 % | +25,5 % | +20,7 % | +39,5 % | +50,0 % | −0,4 % | +10,5 % | +9,0 % | +11,3 % | House PTR 20030630 |
| 2025-12-30 | 2026-01-23 | GOOGL | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 20 call options with a strike price of $150 and an expiratio | +3,1 % | −6,1 % | +5,1 % | +0,1 % | — | +20,8 % | −17,9 % | −6,8 % | −7,9 % | — | House PTR 20033725 |
| 2025-12-30 | 2026-01-23 | AMZN | opce | AKTIVNÍ NÁKUP | 100 001–250 000 USD | Purchased 20 call options with a strike price of $120 and an expiratio | +1,9 % | −11,7 % | +9,5 % | −3,2 % | — | +15,3 % | −16,6 % | −10,1 % | −11,2 % | — | House PTR 20033725 |
| 2025-12-30 | 2026-01-23 | AAPL | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 20 call options with a strike price of $100 and an expiratio | +5,7 % | +7,4 % | +4,8 % | +33,2 % | — | +33,2 % | −3,4 % | +26,2 % | +25,2 % | — | House PTR 20033725 |
| 2025-12-30 | 2026-01-23 | NVDA | opce | AKTIVNÍ NÁKUP | 100 001–250 000 USD | Purchased 20 call options with a strike price of $100 and an expiratio | −0,5 % | +4,9 % | +16,2 % | +5,7 % | — | +26,4 % | −11,4 % | −1,3 % | −2,3 % | — | House PTR 20033725 |
| 2026-01-16 | 2026-01-23 | AB | kód AB | AKTIVNÍ NÁKUP | 1 000 001–5 000 000 USD | Purchased 25,000 shares. | — | — | — | — | — | — | — | — | — | — | House PTR 20033725 |
| 2026-01-16 | 2026-01-23 | GOOGL | akcie | PASIVNÍ | 500 001–1 000 000 USD | Exercised 50 call options purchased 1/14/25 (5,000 shares) at a strike | +3,1 % | −6,1 % | +5,1 % | +0,1 % | — | +20,8 % | −17,9 % | −6,8 % | −7,9 % | — | House PTR 20033725 |
| 2026-01-16 | 2026-01-23 | AMZN | akcie | PASIVNÍ | 500 001–1 000 000 USD | Exercised 50 call options purchased 1/14/25 (5,000 shares) at a strike | +1,9 % | −11,7 % | +9,5 % | −3,2 % | — | +15,3 % | −16,6 % | −10,1 % | −11,2 % | — | House PTR 20033725 |
| 2026-01-16 | 2026-01-23 | NVDA | akcie | PASIVNÍ | 250 001–500 000 USD | Exercised 50 call options purchased 1/14/25 (5,000 shares) at a strike | −0,5 % | +4,9 % | +16,2 % | +5,7 % | — | +26,4 % | −11,4 % | −1,3 % | −2,3 % | — | House PTR 20033725 |
| 2026-01-16 | 2026-01-23 | TEM | akcie | PASIVNÍ | — | Exercised 50 call options purchased 1/14/25 (5,000 shares) at a strike | −13,4 % | −20,6 % | −22,1 % | −36,6 % | — | −1,2 % | −37,4 % | −43,5 % | −44,6 % | — | House PTR 20033725 |
| 2026-01-16 | 2026-01-23 | VST | akcie | PASIVNÍ | 100 001–250 000 USD | Exercised 50 call options purchased 1/14/25 (5,000 shares) at a strike | −2,9 % | +10,4 % | +4,9 % | −6,4 % | — | +11,3 % | −15,2 % | −13,4 % | −14,4 % | — | House PTR 20033725 |
| 2026-05-29 | 2026-06-23 | INTC | opce | AKTIVNÍ NÁKUP | 1 000 001–5 000 000 USD | Purchased 200 call options with a strike price of $50 and an expiratio | −3,5 % | −29,9 % | −6,9 % | — | — | +6,1 % | −37,8 % | — | — | — | House PTR 20034836 |
| 2026-05-29 | 2026-06-23 | UBER | opce | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 200 call options with a strike price of $50 and an expiratio | −1,6 % | −10,7 % | −6,0 % | — | — | +8,8 % | −10,7 % | — | — | — | House PTR 20034836 |
| 2026-07-24 | 2026-08-21 | BE | akcie | AKTIVNÍ NÁKUP | 1 000 001–5 000 000 USD | Purchased 10,000 shares. | +1,1 % | +34,9 % | — | — | — | +43,0 % | +1,1 % | — | — | — | House PTR 20035143 |
| 2026-07-24 | 2026-08-21 | BE | opce | AKTIVNÍ NÁKUP | 1 000 001–5 000 000 USD | Purchased 100 call options with a strike price of $100 and an expirati | +1,1 % | +34,9 % | — | — | — | +43,0 % | +1,1 % | — | — | — | House PTR 20035143 |
| 2026-07-24 | 2026-08-21 | INTC | opce | AKTIVNÍ NÁKUP | 250 001–500 000 USD | Purchased 50 call options with a strike price of $50 and an expiration | +2,6 % | +40,5 % | — | — | — | +46,0 % | +0,3 % | — | — | — | House PTR 20035143 |
| 2026-07-24 | 2026-08-21 | INTC | akcie | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 10,000 shares. | +2,6 % | +40,5 % | — | — | — | +46,0 % | +0,3 % | — | — | — | House PTR 20035143 |
| 2026-07-27 | 2026-08-21 | (bez tickeru) | kód AB | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Additional investment in LLC which is acquiring and restoring a luxury | — | — | — | — | — | — | — | — | — | — | House PTR 20035143 |
| 2026-07-28 | 2026-08-21 | BE | akcie | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 5,000 shares. | +1,1 % | +34,9 % | — | — | — | +43,0 % | +1,1 % | — | — | — | House PTR 20035143 |
| 2026-07-28 | 2026-08-21 | BE | opce | AKTIVNÍ NÁKUP | 500 001–1 000 000 USD | Purchased 100 call options with a strike price of $100 and an expirati | +1,1 % | +34,9 % | — | — | — | +43,0 % | +1,1 % | — | — | — | House PTR 20035143 |

Prodeje Pelosi (39) jsou v databázi (`smart_money_runs`), do statistiky nákupů se nepočítají.

**Nejnovější zveřejněné nákupy (2026):** BE (akcie + call opce, obchody 24. a 28. 7. 2026, zveřejněno 21. 8. 2026),
INTC (akcie + call opce, 24. 7. 2026), INTC a UBER call opce (29. 5. 2026, zveřejněno 23. 6. 2026). Od vstupu po zveřejnění
BE a INTC za 1 měsíc +35 % a +41 %, INTC z června −30 % za 1 m. Jednotlivé případy nic nedokazují — viz statistika výše.

## 8. Donald Trump — **NEOVĚŘENO** (statisticky)

- Primární zdroj jsou výkazy **OGE Form 278-T** ([10/2025](https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/18353894FE440B3685258D430031A337/$FILE/Donald%20J.%20Trump%2010.20.2025%20278-T%20(2).pdf),
  [11/2025 na whitehouse.gov](https://www.whitehouse.gov/wp-content/uploads/2025/11/President-Donald-J.-Trump-Periodic-Transaction-Report-11.14.25.pdf)).
  Jsou to **naskenované PDF bez textové vrstvy** (stovky stran) → strojově je teď nezpracuji; statistický test proto **NEOVĚŘENO**.
- Podle médií (sekundární): výkaz z 8. 5. 2026 za 6. 1.–30. 3. 2026 obsahuje 3 642 transakcí (2 346 nákupů, 1 296 prodejů);
  nákupy mj. NVDA, AMD, AVGO, PLTR, MSFT, ORCL, INTC; podle Trump Organization obchody řídí **nezávislí správci**
  ([CNBC 15. 5. 2026](https://www.cnbc.com/2026/05/15/trump-stock-trade-tech-oge.html),
  [Benzinga](https://www.benzinga.com/news/politics/26/05/52576337/trump-q1-2026-trade-disclosure-nvidia-amd-palantir-microsoft-oracle),
  [davemanuel.com 14. 5. 2026](https://www.davemanuel.com/2026/05/14/trump-278t-filings-3711-trades-may-2026/),
  [Axios 19. 5. 2026](https://www.axios.com/2026/05/19/trump-stocks-nvidia-boeing),
  metodika extrakce [tigzig](https://www.tigzig.com/tremor/trump-trades-methodology)).
- Klasifikace: **PASIVNÍ / NEJASNÉ** — tisíce obchodů za čtvrtletí odpovídají spravovanému portfoliu, ne jednotlivým
  rozhodnutím; kdo o obchodu rozhodl, z výkazu nevyplývá.
- Trump Media (DJT) je sledovaná firma radaru (fúze s TAE Technologies, S-4 podáno 30. 9. 2026) — to je firemní událost,
  ne nákup akcií.

## 9. SMART MONEY SCORE 0–100

Model (váha důkazu + logistická regrese) se učil na 18 684 aktivních nákupech insiderů zveřejněných do
2024-12-31 a odhaduje šanci, že akcie za 6 měsíců porazí kontrolní skupinu. Skóre = percentil předpovědi mezi nákupy
v učení (50 = průměrný nákup, ne 50% šance). Znaky: velikost nákupu, navýšení pozice, počet insiderů do 30 dní (klastr),
role (CEO/CFO/ředitel/10% vlastník), předchozí úspěšnost téže osoby (bez pohledu do budoucnosti), buyback, 13D,
růst tržeb, P/S, hotovost, ředění, 8-K, studie fáze 3, propad od maxima, pohyb před nákupem, obrat (velikost),
nákup po zveřejněné informaci. **Short interest: NEOVĚŘENO** (není zdarma s historií).

**Test 2025–26 (8 287 nákupů, model je neviděl):**


| Skóre | Nákupů | Porazilo kontrolu | Porazilo S&P | Výnos 6 m: dolní pětina | medián | horní pětina |
|---|---|---|---|---|---|---|
| 0–20 | 1 654 | 42,7 % | 33,7 % | −31,3 % | −1,0 % | +27,3 % |
| 20–40 | 1 676 | 47,0 % | 39,1 % | −19,2 % | +4,3 % | +30,8 % |
| 40–60 | 1 655 | 48,6 % | 39,1 % | −16,3 % | +3,7 % | +29,7 % |
| 60–80 | 1 708 | 49,6 % | 38,0 % | −13,0 % | +5,0 % | +26,3 % |
| 80–100 | 1 594 | 50,7 % | 38,2 % | −10,1 % | +4,2 % | +25,6 % |

Skóre spolehlivě odliší jen **nejslabší pětinu** (0–20: S&P porazila třetina); mezi 20 a 100 rozdíl skoro není a horní
pětina má hlavně menší propady (dolní pětina výnosu), ne vyšší medián. Proto se skóre používá jen k vyřazení slabých nákupů, verdikt dělá
předem dané pravidlo (kap. 10). Váhy jsou v `smart_money_runs.result_json` → `skore.vahy`.

**Chyba nalezená při této analýze (WIX):** běh #1 zařadil 5 nákupů vedení Wix.com jako aktivní. Originální Form 4 ukazuje
nákup 479 ks za 59,89 USD při tržní ceně 88,25 USD a prodej všech 479 ks druhý den — zaměstnanecký nákup se slevou,
ne sázka na růst. Opraveno (kontrola prodeje do 10 dní a slevy proti trhu), historická data SEC stažena znovu i s prodeji
kupujících (běh #2). Běh #3 navíc vybírá kontrolní skupinu pro každý nákup pevně (dřív závisela na pořadí měření ostatních
událostí — výsledek malých skupin, např. Pelosi, se tím měnil). Závěry ani výběr 10 signálů se mezi během #2 a #3 nezměnily. Predikce #19 z běhu #1 v ledgeru zůstává (historie se nemění), poučení `SM-ESPP-FLIP-WIX`.

## 10. TOP 10 aktuálních „SMART MONEY“ signálů

Výběr: 1 245 nákupů insiderů za 60 dní (openinsider) → 254 kandidátů
(cena ≥ 2 USD, obrat ≥ 0,5 mil. USD/den, cena od zveřejnění nevzrostla o víc než 15 % = růst ještě neproběhl, akcie
nevyrostla o 80 % za 6 m před nákupem, skóre ≥ 20, bez SPAC) → seřazeno předem daným pravidlem (typ nakupujícího
s kladným výsledkem v obou obdobích, víc insiderů, skóre) → **každý ověřen v originálním Form 4**.

**Verdikt (předem daná pravidla):**
- **VYSOKÁ** — jen pro typ nákupu s výhodou statisticky potvrzenou v učení i testu (t ≥ 2). **Takový typ teď neexistuje → žádná VYSOKÁ.**
- **STŘEDNÍ** — nakupuje typ, který měl kladný výsledek v obou obdobích (CFO, 10% vlastník), a žádný typ se záporným testem.
- **NÍZKÁ** — skóre < 20, nákup do 10 dní po výsledcích / 8-K (insider reaguje na známou informaci), nebo typ bez výhody v 2025–26 (CEO).

**Potenciální upside** = rozpětí výnosu za 6 m u nákupů se stejným pásmem skóre v testu 2025–26 (dolní pětina / medián /
horní pětina). Není to cíl ani slib.


### 1. SBLK — Star Bulk Carriers Corp. · **STŘEDNÍ SIGNALIZAČNÍ HODNOTA**

| Položka | Hodnota |
|---|---|
| Kdo nakupuje | Erhardt Koert, Karellis Nikolaos, Pappa Milena Maria, Pappas Alexandros a další (celkem 8 insiderů) — Dir Chief Strategy Officer Dir Head of Operations COO co CFO Dir Dir |
| Typ nákupu | AKTIVNÍ NÁKUP (ověřeno ve Form 4); ověřeno: [Zagari Raffaele](https://www.sec.gov/Archives/edgar/data/1386716/000200503726000014/primary_doc.xml) AKTIVNÍ NÁKUP, 1 696 200 USD; [Plakantonaki Charis](https://www.sec.gov/Archives/edgar/data/1386716/000197860426000008/primary_doc.xml) AKTIVNÍ NÁKUP, 84 810 USD |
| Datum | obchod 2026-09-15, zveřejněno 2026-09-17 |
| Velikost | 6 920 496 USD |
| Cena při nákupu | 28,27 USD (v den zveřejnění 31,75 USD) |
| Aktuální cena | 30,75 USD (+8,8 % od ceny insidera, −3,8 % od zveřejnění) |
| Historická úspěšnost insidera | NEOVĚŘENO (méně než 2 změřené předchozí nákupy) |
| Buyback | 2.7 % kapitalizace za poslední rok (SEC) |
| Fundament | hotovost 14 % kapitalizace; počet akcií za rok −3,6 % |
| Nejbližší katalyzátor | 2026-12-07..2026-12-27 (ESTIMATED: poslední 10-Q/10-K 2026-03-19 + 3 měsíce) |
| SMART MONEY SCORE | **62** / 100 |
| Potenciální upside (6 m, test 2025–26) | −13 % / **+5 %** / +26 % |
| Hlavní riziko | běžné tržní riziko |
| Korelace vs. příčina | V 10 dnech před nákupem nebyly výsledky ani 8-K: nákup může nést vlastní informaci, ale v datech 2025–26 to výhodu nepřineslo — NEOVĚŘENO. |
| Verdikt | **STŘEDNÍ** — typ nakupujícího (CFO) měl výhodu v obou obdobích |
| Ledger | predikce #18 (WATCH, „lépe než S&P 500 za 6 měsíců“, vyhodnotí se sama) |

### 2. GRNT — Granite Ridge Resources, Inc. · **STŘEDNÍ SIGNALIZAČNÍ HODNOTA**

| Položka | Hodnota |
|---|---|
| Kdo nakupuje | Kettler Ronald Kyle, McCartney John, Miller Matthew Reade — Dir CFO Dir |
| Typ nákupu | AKTIVNÍ NÁKUP (ověřeno ve Form 4); ověřeno: [Miller Matthew Reade](https://www.sec.gov/Archives/edgar/data/1928446/000162828026061771/wk-form4_1789400621.xml) AKTIVNÍ NÁKUP, 50 300 USD; [Kettler Ronald Kyle](https://www.sec.gov/Archives/edgar/data/1928446/000162828026060851/wk-form4_1788888543.xml) AKTIVNÍ NÁKUP, 30 300 USD |
| Datum | obchod 2026-09-01, zveřejněno 2026-09-14 |
| Velikost | 105 800 USD |
| Cena při nákupu | 5,04 USD (v den zveřejnění 5,12 USD) |
| Aktuální cena | 4,47 USD (−11,3 % od ceny insidera, −12,7 % od zveřejnění) |
| Historická úspěšnost insidera | -7.5 % nad kontrolou v průměru předchozích nákupů (6 m) |
| Buyback | žádný vykázaný |
| Fundament | tržby +36,7 % meziročně; P/S 1,1; počet akcií za rok +0,5 % |
| Nejbližší katalyzátor | 2026-10-26..2026-11-15 (ESTIMATED: poslední 10-Q/10-K 2026-08-06 + 3 měsíce) |
| SMART MONEY SCORE | **49** / 100 |
| Potenciální upside (6 m, test 2025–26) | −16 % / **+4 %** / +30 % |
| Hlavní riziko | běžné tržní riziko |
| Korelace vs. příčina | V 10 dnech před nákupem nebyly výsledky ani 8-K: nákup může nést vlastní informaci, ale v datech 2025–26 to výhodu nepřineslo — NEOVĚŘENO. |
| Verdikt | **STŘEDNÍ** — typ nakupujícího (CFO) měl výhodu v obou obdobích |
| Ledger | predikce #20 (WATCH, „lépe než S&P 500 za 6 měsíců“, vyhodnotí se sama) |

### 3. NOMD — Nomad Foods Ltd · **NÍZKÁ SIGNALIZAČNÍ HODNOTA**

| Položka | Hodnota |
|---|---|
| Kdo nakupuje | Baldew Ruben, Brisby Dominic — CEO CFO |
| Typ nákupu | AKTIVNÍ NÁKUP (ověřeno ve Form 4); ověřeno: [BRISBY DOMINIC](https://www.sec.gov/Archives/edgar/data/1651717/000211158026000010/wk-form4_1787775819.xml) AKTIVNÍ NÁKUP, 619 000 USD; [BALDEW RUBEN](https://www.sec.gov/Archives/edgar/data/1651717/000211199926000009/wk-form4_1787344214.xml) AKTIVNÍ NÁKUP, 335 231 USD |
| Datum | obchod 2026-08-19, zveřejněno 2026-08-26 |
| Velikost | 954 231 USD |
| Cena při nákupu | 12,12 USD (v den zveřejnění 12,15 USD) |
| Aktuální cena | 10,65 USD (−12,1 % od ceny insidera, −12,8 % od zveřejnění) |
| Historická úspěšnost insidera | NEOVĚŘENO (méně než 2 změřené předchozí nákupy) |
| Buyback | žádný vykázaný |
| Fundament | počet akcií za rok −8,8 % |
| Nejbližší katalyzátor | 2026-11-16..2026-12-06 (ESTIMATED: poslední 10-Q/10-K 2026-02-26 + 3 měsíce) |
| SMART MONEY SCORE | **78** / 100 |
| Potenciální upside (6 m, test 2025–26) | −13 % / **+5 %** / +26 % |
| Hlavní riziko | běžné tržní riziko |
| Korelace vs. příčina | V 10 dnech před nákupem nebyly výsledky ani 8-K: nákup může nést vlastní informaci, ale v datech 2025–26 to výhodu nepřineslo — NEOVĚŘENO. |
| Verdikt | **NÍZKÁ** — typ nákupu neměl výhodu v testu 2025–26 (CEO) |
| Ledger | predikce #21 (WATCH, „lépe než S&P 500 za 6 měsíců“, vyhodnotí se sama) |

### 4. BLX — Bladex, Inc. · **STŘEDNÍ SIGNALIZAČNÍ HODNOTA**

| Položka | Hodnota |
|---|---|
| Kdo nakupuje | Tizzoni Alejandro Horacio, Van Hoorde Annette Marie — CFO Chief Risk Officer |
| Typ nákupu | AKTIVNÍ NÁKUP (ověřeno ve Form 4); ověřeno: [Van Hoorde Annette Marie](https://www.sec.gov/Archives/edgar/data/890541/000089054126000011/form4.xml) AKTIVNÍ NÁKUP, 79 970 USD; [Tizzoni Alejandro Horacio](https://www.sec.gov/Archives/edgar/data/890541/000089054126000009/form4.xml) AKTIVNÍ NÁKUP, 98 050 USD |
| Datum | obchod 2026-08-21, zveřejněno 2026-08-31 |
| Velikost | 178 020 USD |
| Cena při nákupu | 54,00 USD (v den zveřejnění 53,92 USD) |
| Aktuální cena | 54,78 USD (+1,4 % od ceny insidera, +1,4 % od zveřejnění) |
| Historická úspěšnost insidera | NEOVĚŘENO (méně než 2 změřené předchozí nákupy) |
| Buyback | žádný vykázaný |
| Fundament | NEOVĚŘENO (chybí XBRL fundamenty) |
| Nejbližší katalyzátor | 2026-10-09..2026-10-29 (ESTIMATED: poslední 10-Q/10-K 2026-04-20 + 3 měsíce) |
| SMART MONEY SCORE | **50** / 100 |
| Potenciální upside (6 m, test 2025–26) | −16 % / **+4 %** / +30 % |
| Hlavní riziko | běžné tržní riziko |
| Korelace vs. příčina | V 10 dnech před nákupem nebyly výsledky ani 8-K: nákup může nést vlastní informaci, ale v datech 2025–26 to výhodu nepřineslo — NEOVĚŘENO. |
| Verdikt | **STŘEDNÍ** — typ nakupujícího (CFO) měl výhodu v obou obdobích |
| Ledger | predikce #22 (WATCH, „lépe než S&P 500 za 6 měsíců“, vyhodnotí se sama) |

### 5. INR — Infinity Natural Resources, Inc. · **STŘEDNÍ SIGNALIZAČNÍ HODNOTA**

| Položka | Hodnota |
|---|---|
| Kdo nakupuje | Baetz Cary D, Gieselman Scott — EVP, CFO Dir |
| Typ nákupu | AKTIVNÍ NÁKUP (ověřeno ve Form 4); ověřeno: [Baetz Cary D](https://www.sec.gov/Archives/edgar/data/2029118/000202911826000113/wk-form4_1790632866.xml) AKTIVNÍ NÁKUP, 299 993 USD; [Gieselman Scott](https://www.sec.gov/Archives/edgar/data/2029118/000202911826000108/wk-form4_1790196092.xml) AKTIVNÍ NÁKUP, 363 777 USD |
| Datum | obchod 2026-09-21, zveřejněno 2026-09-28 |
| Velikost | 663 770 USD |
| Cena při nákupu | 13,11 USD (v den zveřejnění 12,53 USD) |
| Aktuální cena | 12,91 USD (−1,5 % od ceny insidera, +3,0 % od zveřejnění) |
| Historická úspěšnost insidera | NEOVĚŘENO (méně než 2 změřené předchozí nákupy) |
| Buyback | NEOVĚŘENO (firma nepodává XBRL) |
| Fundament | tržby +129,6 % meziročně |
| Nejbližší katalyzátor | 2026-10-30..2026-11-19 (ESTIMATED: poslední 10-Q/10-K 2026-08-10 + 3 měsíce) |
| SMART MONEY SCORE | **35** / 100 |
| Potenciální upside (6 m, test 2025–26) | −19 % / **+4 %** / +31 % |
| Hlavní riziko | akcie -34.8 % pod ročním maximem |
| Korelace vs. příčina | V 10 dnech před nákupem nebyly výsledky ani 8-K: nákup může nést vlastní informaci, ale v datech 2025–26 to výhodu nepřineslo — NEOVĚŘENO. |
| Verdikt | **STŘEDNÍ** — typ nakupujícího (CFO) měl výhodu v obou obdobích |
| Ledger | predikce #23 (WATCH, „lépe než S&P 500 za 6 měsíců“, vyhodnotí se sama) |

### 6. PRE — Prenetics Global Ltd · **NÍZKÁ SIGNALIZAČNÍ HODNOTA**

| Položka | Hodnota |
|---|---|
| Kdo nakupuje | Rosin Brian J, Yeung Danny Sheng Wu — CFO of IM8 (US) LLC CEO |
| Typ nákupu | AKTIVNÍ NÁKUP (ověřeno ve Form 4); ověřeno: [Rosin Brian J](https://www.sec.gov/Archives/edgar/data/1876431/000162828026058994/wk-form4_1787747026.xml) AKTIVNÍ NÁKUP, 497 700 USD; [Yeung Danny Sheng Wu](https://www.sec.gov/Archives/edgar/data/1876431/000162828026058760/wk-form4_1787622111.xml) AKTIVNÍ NÁKUP, 501 998 USD |
| Datum | obchod 2026-08-20, zveřejněno 2026-08-26 |
| Velikost | 999 698 USD |
| Cena při nákupu | 20,95 USD (v den zveřejnění 25,78 USD) |
| Aktuální cena | 20,17 USD (−3,7 % od ceny insidera, −21,8 % od zveřejnění) |
| Historická úspěšnost insidera | NEOVĚŘENO (méně než 2 změřené předchozí nákupy) |
| Buyback | žádný vykázaný |
| Fundament | počet akcií za rok +30,0 % |
| Nejbližší katalyzátor | 2026-10-19..2026-11-08 (ESTIMATED: poslední 10-Q/10-K 2026-04-30 + 3 měsíce) |
| SMART MONEY SCORE | **30** / 100 |
| Potenciální upside (6 m, test 2025–26) | −19 % / **+4 %** / +31 % |
| Hlavní riziko | ředění 30.0 % za rok |
| Korelace vs. příčina | V 10 dnech před nákupem nebyly výsledky ani 8-K: nákup může nést vlastní informaci, ale v datech 2025–26 to výhodu nepřineslo — NEOVĚŘENO. |
| Verdikt | **NÍZKÁ** — typ nákupu neměl výhodu v testu 2025–26 (CEO) |
| Ledger | predikce #24 (WATCH, „lépe než S&P 500 za 6 měsíců“, vyhodnotí se sama) |

### 7. CC — Chemours Co · **NÍZKÁ SIGNALIZAČNÍ HODNOTA**

| Položka | Hodnota |
|---|---|
| Kdo nakupuje | Cowan Alister, Cranston Mary B, Dignam Denise, Familiar Calderon Gerardo a další (celkem 7 insiderů) — See Remarks CEO Dir See Remarks Dir See Remarks CFO |
| Typ nákupu | AKTIVNÍ NÁKUP (ověřeno ve Form 4); ověřeno: [Familiar Calderon Gerardo](https://www.sec.gov/Archives/edgar/data/1627223/000119312526349656/ownership.xml) AKTIVNÍ NÁKUP, 30 051 USD; [Dignam Denise](https://www.sec.gov/Archives/edgar/data/1627223/000119312526349607/ownership.xml) AKTIVNÍ NÁKUP, 50 501 USD |
| Datum | obchod 2026-08-06, zveřejněno 2026-08-13 |
| Velikost | 488 620 USD |
| Cena při nákupu | 15,41 USD (v den zveřejnění 15,26 USD) |
| Aktuální cena | 13,71 USD (−11,0 % od ceny insidera, −10,2 % od zveřejnění) |
| Historická úspěšnost insidera | 26.9 % nad kontrolou v průměru předchozích nákupů (6 m) |
| Buyback | 3.0 % kapitalizace za poslední rok (SEC) |
| Fundament | tržby −1,5 % meziročně; P/S 0,4; hotovost 29 % kapitalizace; počet akcií za rok +0,5 % |
| Nejbližší katalyzátor | 2026-10-25..2026-11-14 (ESTIMATED: poslední 10-Q/10-K 2026-08-05 + 3 měsíce) |
| SMART MONEY SCORE | **99** / 100 |
| Potenciální upside (6 m, test 2025–26) | −10 % / **+4 %** / +26 % |
| Hlavní riziko | akcie -45.4 % pod ročním maximem |
| Korelace vs. příčina | Nákup přišel do 10 dní po výsledcích nebo 8-K: insider spíš reaguje na informaci, kterou trh už zná. |
| Verdikt | **NÍZKÁ** — nákup následoval po zveřejněných výsledcích / 8-K |
| Ledger | predikce #25 (WATCH, „lépe než S&P 500 za 6 měsíců“, vyhodnotí se sama) |

### 8. KMPR — Kemper Corp · **NÍZKÁ SIGNALIZAČNÍ HODNOTA**

| Položka | Hodnota |
|---|---|
| Kdo nakupuje | Camden Bradley T, Evans Carl Thomas Jr., Gorevic Jason N, Laderman Gerald a další (celkem 5 insiderů) — Pres, CEO EVP, Sec., GC EVP, CFO Dir Dir |
| Typ nákupu | AKTIVNÍ NÁKUP (ověřeno ve Form 4); ověřeno: [McAnena Stephen J](https://www.sec.gov/Archives/edgar/data/860748/000197668426000011/wk-form4_1786654429.xml) AKTIVNÍ NÁKUP, 79 500 USD; [Evans Carl Thomas Jr.](https://www.sec.gov/Archives/edgar/data/860748/000164182326000009/wk-form4_1786486288.xml) AKTIVNÍ NÁKUP, 26 530 USD |
| Datum | obchod 2026-08-10, zveřejněno 2026-08-13 |
| Velikost | 367 880 USD |
| Cena při nákupu | 26,35 USD (v den zveřejnění 26,91 USD) |
| Aktuální cena | 25,67 USD (−2,6 % od ceny insidera, −4,0 % od zveřejnění) |
| Historická úspěšnost insidera | -23.3 % nad kontrolou v průměru předchozích nákupů (6 m) |
| Buyback | 19.0 % kapitalizace za poslední rok (SEC) |
| Fundament | tržby −10,8 % meziročně; P/S 0,4; počet akcií za rok −6,1 % |
| Nejbližší katalyzátor | 2026-10-25..2026-11-14 (ESTIMATED: poslední 10-Q/10-K 2026-08-05 + 3 měsíce) |
| SMART MONEY SCORE | **85** / 100 |
| Potenciální upside (6 m, test 2025–26) | −10 % / **+4 %** / +26 % |
| Hlavní riziko | akcie -50.5 % pod ročním maximem |
| Korelace vs. příčina | Nákup přišel do 10 dní po výsledcích nebo 8-K: insider spíš reaguje na informaci, kterou trh už zná. |
| Verdikt | **NÍZKÁ** — nákup následoval po zveřejněných výsledcích / 8-K |
| Ledger | predikce #27 (WATCH, „lépe než S&P 500 za 6 měsíců“, vyhodnotí se sama) |

### 9. ELAN — Elanco Animal Health Inc · **NÍZKÁ SIGNALIZAČNÍ HODNOTA**

| Položka | Hodnota |
|---|---|
| Kdo nakupuje | Harrington Michael J, Herendeen Paul, Kurzius Lawrence Erik, O'Neill Shiv a další (celkem 5 insiderů) — Dir GC, CORP SEC Dir EVP, CFO Dir |
| Typ nákupu | AKTIVNÍ NÁKUP (ověřeno ve Form 4); ověřeno: [Kurzius Lawrence Erik](https://www.sec.gov/Archives/edgar/data/1739104/000135209026000006/form4-08212026_080841.xml) AKTIVNÍ NÁKUP, 935 920 USD; [O'Neill Shiv](https://www.sec.gov/Archives/edgar/data/1739104/000200117126000006/form4-08182026_080805.xml) AKTIVNÍ NÁKUP, 94 273 USD |
| Datum | obchod 2026-08-07, zveřejněno 2026-08-21 |
| Velikost | 1 473 069 USD |
| Cena při nákupu | 23,11 USD (v den zveřejnění 23,97 USD) |
| Aktuální cena | 22,14 USD (−4,2 % od ceny insidera, −7,7 % od zveřejnění) |
| Historická úspěšnost insidera | 1.1 % nad kontrolou v průměru předchozích nákupů (6 m) |
| Buyback | žádný vykázaný |
| Fundament | tržby +10,2 % meziročně; P/S 2,2; hotovost 4 % kapitalizace; počet akcií za rok +0,6 % |
| Nejbližší katalyzátor | 2026-10-25..2026-11-14 (ESTIMATED: poslední 10-Q/10-K 2026-08-05 + 3 měsíce) |
| SMART MONEY SCORE | **53** / 100 |
| Potenciální upside (6 m, test 2025–26) | −16 % / **+4 %** / +30 % |
| Hlavní riziko | běžné tržní riziko |
| Korelace vs. příčina | Nákup přišel do 10 dní po výsledcích nebo 8-K: insider spíš reaguje na informaci, kterou trh už zná. |
| Verdikt | **NÍZKÁ** — nákup následoval po zveřejněných výsledcích / 8-K |
| Ledger | predikce #29 (WATCH, „lépe než S&P 500 za 6 měsíců“, vyhodnotí se sama) |

### 10. AVBC — Avidia Bancorp, Inc. · **NÍZKÁ SIGNALIZAČNÍ HODNOTA**

| Položka | Hodnota |
|---|---|
| Kdo nakupuje | Doane Thomas, Grimaldo Joseph F, Murphy Michael Dennis, Nelson Jonathan Michael a další (celkem 5 insiderů) — Chairman of the Board CFO, Treasurer Dir EVP- HR Dir Dir |
| Typ nákupu | AKTIVNÍ NÁKUP (ověřeno ve Form 4); ověřeno: [Murphy Michael Dennis](https://www.sec.gov/Archives/edgar/data/2058758/000143774926030507/rdgdoc.xml) AKTIVNÍ NÁKUP, 110 600 USD; [Nelson Jonathan Michael](https://www.sec.gov/Archives/edgar/data/2058758/000143774926029624/rdgdoc.xml) AKTIVNÍ NÁKUP, 99 855 USD |
| Datum | obchod 2026-08-11, zveřejněno 2026-09-16 |
| Velikost | 586 569 USD |
| Cena při nákupu | 21,95 USD (v den zveřejnění 22,29 USD) |
| Aktuální cena | 22,24 USD (+1,3 % od ceny insidera, −0,9 % od zveřejnění) |
| Historická úspěšnost insidera | -25.3 % nad kontrolou v průměru předchozích nákupů (6 m) |
| Buyback | žádný vykázaný |
| Fundament | NEOVĚŘENO (chybí XBRL fundamenty) |
| Nejbližší katalyzátor | 2026-11-02..2026-11-22 (ESTIMATED: poslední 10-Q/10-K 2026-08-13 + 3 měsíce) |
| SMART MONEY SCORE | **50** / 100 |
| Potenciální upside (6 m, test 2025–26) | −16 % / **+4 %** / +30 % |
| Hlavní riziko | běžné tržní riziko |
| Korelace vs. příčina | Nákup přišel do 10 dní po výsledcích nebo 8-K: insider spíš reaguje na informaci, kterou trh už zná. |
| Verdikt | **NÍZKÁ** — nákup následoval po zveřejněných výsledcích / 8-K |
| Ledger | predikce #28 (WATCH, „lépe než S&P 500 za 6 měsíců“, vyhodnotí se sama) |


**Přehled:**


| # | Ticker | Kdo | Velikost | Zveřejněno | Cena nákup → teď | Skóre | Verdikt |
|---|---|---|---|---|---|---|---|
| 1 | SBLK | Dir Chief Strategy Officer Dir Head of O | 6,92 mil. USD | 2026-09-17 | 28,27 → 30,75 | 62 | STŘEDNÍ |
| 2 | GRNT | Dir CFO Dir | 0,11 mil. USD | 2026-09-14 | 5,04 → 4,47 | 49 | STŘEDNÍ |
| 3 | NOMD | CEO CFO | 0,95 mil. USD | 2026-08-26 | 12,12 → 10,65 | 78 | NÍZKÁ |
| 4 | BLX | CFO Chief Risk Officer | 0,18 mil. USD | 2026-08-31 | 54,00 → 54,78 | 50 | STŘEDNÍ |
| 5 | INR | EVP, CFO Dir | 0,66 mil. USD | 2026-09-28 | 13,11 → 12,91 | 35 | STŘEDNÍ |
| 6 | PRE | CFO of IM8 (US) LLC CEO | 1,00 mil. USD | 2026-08-26 | 20,95 → 20,17 | 30 | NÍZKÁ |
| 7 | CC | See Remarks CEO Dir See Remarks Dir See  | 0,49 mil. USD | 2026-08-13 | 15,41 → 13,71 | 99 | NÍZKÁ |
| 8 | KMPR | Pres, CEO EVP, Sec., GC EVP, CFO Dir Dir | 0,37 mil. USD | 2026-08-13 | 26,35 → 25,67 | 85 | NÍZKÁ |
| 9 | ELAN | Dir GC, CORP SEC Dir EVP, CFO Dir | 1,47 mil. USD | 2026-08-21 | 23,11 → 22,14 | 53 | NÍZKÁ |
| 10 | AVBC | Chairman of the Board CFO, Treasurer Dir | 0,59 mil. USD | 2026-09-16 | 21,95 → 22,24 | 50 | NÍZKÁ |

**Nové nákupy politiků (posledních 60 dní, Sněmovna/Senát):** 218 transakcí, z toho 189 v nejnižším pásmu
1 001–15 000 USD. Protože politici jako skupina výhodu nemají (kap. 6), nejsou mezi signály. Velké nákupy (≥ 250 tis. USD):


| Politik | Kdo | Ticker | Aktivum | Částka (USD) | Obchod | Zveřejněno | Cena obchod → poslední | Zdroj |
|---|---|---|---|---|---|---|---|---|
| Josh Gottheimer | JT | MSFT | OP | 250 001–500 000 | 2026-08-14 | 2026-09-14 | 495,40 → 515,02 | HOUSE PTR 20035455 |
| Josh Gottheimer | JT | MSFT | OP | 500 001–1 000 000 | 2026-08-14 | 2026-09-14 | 495,40 → 515,02 | HOUSE PTR 20035455 |
| Nancy Pelosi | SP | BE | ST | 1 000 001–5 000 000 | 2026-07-24 | 2026-08-21 | 184,89 → 291,71 | HOUSE PTR 20035143 |
| Nancy Pelosi | SP | BE | OP | 1 000 001–5 000 000 | 2026-07-24 | 2026-08-21 | 184,89 → 291,71 | HOUSE PTR 20035143 |
| Nancy Pelosi | SP | BE | ST | 500 001–1 000 000 | 2026-07-28 | 2026-08-21 | 166,84 → 291,71 | HOUSE PTR 20035143 |
| Nancy Pelosi | SP | BE | OP | 500 001–1 000 000 | 2026-07-28 | 2026-08-21 | 166,84 → 291,71 | HOUSE PTR 20035143 |
| Nancy Pelosi | SP | INTC | OP | 250 001–500 000 | 2026-07-24 | 2026-08-21 | 92,32 → 120,04 | HOUSE PTR 20035143 |
| Nancy Pelosi | SP | INTC | ST | 500 001–1 000 000 | 2026-07-24 | 2026-08-21 | 92,32 → 120,04 | HOUSE PTR 20035143 |


## 11. Korelace vs. příčina — shrnutí

| Případ | Proč to může vypadat jako signál | Co ukazují data |
|---|---|---|
| Insider po propadu 2021–24 | velký náskok, t {t(best['t_uceni'])} | v 2025–26 {p(best['test'])}; pravděpodobně odraz malých firem po propadu 2022 (hypotéza), ne trvalá informace insidera |
| Pelosi | NVDA, AVGO, GOOGL velké zisky | malý počet, medián kolem nuly, tech sektor rostl celý → expozice, ne prokázaná informace |
| Politici celkem | populární „kopírovací“ strategie | {p(PA['nad_kontrolou_prumer'])} proti kontrole, zveřejnění se zpožděním ~4 týdnů |
| 13D | „aktivista vidí hodnotu“ | {p(D13['6m']['nad_kontrolou_prumer'])} za 6 m — 13D se objevuje u firem v potížích |
| Buyback | „firma věří své akcii“ | bez významného efektu; při klesajících tržbách maskuje slabost |

## 12. Co dál (automaticky, bez zásahu uživatele)

- Týdenní běh (sobota): `python -m stockradar smart-money` — nová data SEC/Kongres, přepočet, nové signály do ledgeru;
  ledger po 6 měsících ukáže, jestli signály STŘEDNÍ porazily S&P 500.
- Plán zlepšení: 13F (fondy), oznámení buybacků z 8-K, ocenění při odkupu, Trumpovy výkazy přes OCR (pokud bude
  k dispozici bezplatný nástroj), zisk opcí místo podkladové akcie.
