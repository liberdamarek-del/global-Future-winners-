# Výzkum a zlepšování agenta (denní úloha od 2026-10-13)

Zadání uživatele 2026-10-13: dlouhodobě a samostatně zkoumat nové přístupy k autonomním agentům (plánování,
dlouhodobá paměť, nástroje, experimentování, učení ze zpětné vazby, sebehodnocení), převádět je na konkrétní návrhy
pro Stock Radar, navrhovat srovnávací experimenty a vše ukládat tak, aby další běh vycházel z předchozích. Plus
**raketový deník**: rakety za týden / 14 dní / měsíc → ověřená příčina z internetu → data pro model.

Pravidla navíc: nic nevymýšlet; když není nic nového, napsat to; korelace ≠ příčina; úspěch na několika příkladech
není důkaz; neopakovat stejné návrhy; zdroje vždy s URL a datem. Do veřejných diskusí se nepíše (jen čtení).

## Soubory (trvalá evidence, v gitu)

| Soubor | Obsah | Jak se mění |
|---|---|---|
| `smery.json` | výzkumné směry: priorita 0–1, počet běhů, prázdné běhy po sobě, stav | přepisuje se po každém běhu |
| `zdroje.jsonl` | jedno zjištění = jeden řádek (zdroj, URL, datum zdroje, zjištění, zralost, důvěryhodnost, využití) | jen přidávat |
| `navrhy.jsonl` | návrh pro Stock Radar (problém, implementace, náklady, rizika, závislosti, metrika, experiment); změna stavu = nový řádek se stejným `id` | jen přidávat |
| `reporty/RRRR-MM-DD.md` | report běhu (i „nic nového“) | nový soubor za běh |

Formát hlídá `tests/unit/test_agent_research.py` (povinná pole, výčty, unikátní URL + klíč myšlenky).

### `zdroje.jsonl` — pole
`id` (Z-RRRRMMDD-n), `beh` (datum běhu), `smer` (id směru), `klic` (krátký klíč myšlenky, slouží k odhalení
opakování), `nazev`, `url` (https), `datum_zdroje` (RRRR-MM-DD, RRRR-MM nebo RRRR), `typ_zdroje`
(CLANEK_RECENZOVANY / PREPRINT / DOKUMENTACE / OPEN_SOURCE / BLOG / DISKUSE), `zjisteni` (konkrétní fakt, čísla),
`zralost` (PRAXE / VYZKUM / HYPOTEZA), `duveryhodnost` (VYSOKA / STREDNI / NIZKA) + `duvod_duvery`, `vyuziti`
(k čemu u nás), `navrh` (id návrhu nebo null), `overeno_primarnim_zdrojem` (true/false).

- **PRAXE** = běžně nasazené nebo v oficiální dokumentaci s výsledky; **VYZKUM** = článek/preprint s měřením;
  **HYPOTEZA** = nápad bez měření (naše vlastní kombinace patří sem, dokud ji neotestujeme).
- **VYSOKA** = primární zdroj (recenzovaný článek, oficiální dokumentace, kód s reprodukovatelnými výsledky);
  **STREDNI** = preprint nebo odborný blog s daty; **NIZKA** = diskuse, marketing, bez dat.

### `navrhy.jsonl` — pole
`id` (N-n), `datum`, `nazev`, `klic`, `zdroje` (id zjištění), `problem` (co u nás řeší + důkaz z diag / system /
lessons / VYZKUM.md), `implementace` (soubory, moduly, kroky), `naklady` (hodiny, výpočet, dotazy), `rizika`,
`zavislosti`, `metrika` (předem daná, objektivní), `experiment` (současná verze × nová: data, kontrola, minimální
vzorek, kritérium úspěchu, kdy vyhodnotit), `priorita` (0–1), `stav` (NAVRZENO / EXPERIMENT / ZAVEDENO / ZAMITNUTO /
ODLOZENO). Změna stavu: nový řádek `{"id", "datum", "stav", "duvod", "vysledek"}`.

## Co systém už má (aby se to znovu nenavrhovalo)

Pevný protokol TRAIN / VALIDATION / LOCKED TEST (zamčený test jen jednou na konfiguraci, počet pokusů veřejně),
kalibrace a odpověď NEVÍM, centrum důkazů se spolehlivostí rolí ze zamčených testů a živých výsledků, rozpory mezi
moduly, poučení (`lessons`) navázaná na role, deník běhů a registr modulů, paměť výpočtů podle otisku dat, předem
zapsané hypotézy (`docs/VYZKUM.md`, E1–E4), studie událostí s kontrolní skupinou, append-only ledger predikcí.

## Denní postup (14:13 Praha, ~60–90 min)

1. **Načíst:** tento soubor, `smery.json`, posledních 5 reportů, `navrhy.jsonl` (otevřené), `docs/VYZKUM.md`,
   `python -m stockradar system` a `diag` (skutečné slabiny agenta = zdroj problémů pro návrhy).
2. **Vybrat směry:** hlavní = nejvyšší priorita; průzkumný = směr s nejmenším počtem běhů (rotace).
   Pravidlo přesměrování: běh bez nového zjištění → `prazdnych_behu_po_sobe` + 1; po 3 prázdných bězích se priorita
   sníží na polovinu (stav UTLUMENY); nové zjištění s návrhem → priorita + 0,1 (max 1).
3. **Hledat:** WebSearch (extended u novinek), primární zdroje číst přes WebFetch (arXiv, dokumentace, GitHub,
   recenzované články); diskuse (HN, Reddit) jen jako vodítko → NIZKA, dokud se neověří primárním zdrojem.
   Před zápisem zkontrolovat `zdroje.jsonl` (stejná URL nebo stejný `klic` = není nové).
4. **Převést na návrh:** jen zjištění, které řeší doložený problém Stock Radaru; jinak zapsat jako zjištění bez návrhu.
5. **Experiment:** nejvýš jeden za týden se opravdu zavede (vratně, s testem, za přepínačem), metrika a kritérium
   předem v `navrhy.jsonl`; vyhodnocení až po minimálním vzorku; výsledek (i neúspěch) do `navrhy.jsonl` a `lessons`.
6. **Raketový deník** (viz níže).
7. **Report** `reporty/RRRR-MM-DD.md`: nejdůležitější nové poznatky (nebo výslovně „nic nového“), ověřené zdroje,
   nejlepší nový nápad, doporučený experiment, míra jistoty, další krok; rakety dne s ověřenou příčinou.
8. `python -m pytest`, commit + push; uživateli 3–6 vět česky.

## Raketový deník (rakety za týden / 14 dní / měsíc)

**Dnes (stav 2026-10-13):** týdenní objevování hledá rakety ≥ +30 % za 5 dní a ≥ +50 % za 21 dní (+ 3 a 6 měsíců),
u 120 největších týdenních raket za 2 roky čte titulky Google News a příčinu určí **automaticky podle klíčových slov**
(AUTO, neověřeno; poslední běh: 61 ze 120 s příčinou, 59 bez zpráv). Příčiny se ukazují jen jako statistika na webu
— **do modelu se nedostávají** a internet se u jednotlivých raket ručně neověřuje (výjimky v `lessons`: ABVX, AEMD,
SharpLink). Okno 14 dní se samostatně nehledá.

**Stav 2026-10-13: postaveno (v0.13.0, `python -m stockradar rakety`).** Plán:
1. Denně jeden dotaz na Nasdaq screener (už ho používáme) → snímek cen všech amerických akcií — ve 14:13 (Praha); večer v 22:47 screener ještě ukazuje předchozí den, kontrola shodných cen snímek přeskočí (ověřeno 2026-10-13); spolu s týdenními
   cenami z Yahoo → rakety ≥ +30 % za 5, ≥ +40 % za 10 a ≥ +50 % za 21 obchodních dní (likvidní, cena ≥ 1 USD).
2. Pro 5 největších nových raket dne: ověřit příčinu na internetu z **primárního zdroje** (8-K, tisková zpráva,
   FDA, SEC) — kód příčiny (stejné kódy jako AUTO), zda byl termín znám předem, co bylo vidět předem (insideři, 13D,
   objem, katalyzátor v kalendáři), URL + datum. Neověřené zůstane NEOVERENO.
3. Uložit do nové tabulky (migrace, append-only) a do `state/`; v centru jako kontext u firmy.
4. **Do modelu poctivě:** příčina je známá až po pohybu, takže sama nic nepředpoví. Použije se dvakrát:
   (a) **předzvěsti** — co bylo vidět PŘED raketou podle typu příčiny → nové znaky do studie případů a kontrol a do
   modelu raket jen po validaci a zamčeném testu; (b) **co bude po raketě** — pokračování nebo vyfouknutí za 1–3
   měsíce podle typu příčiny (studie událostí s kontrolou) → při t ≥ 2 mimo vzorek nová role v centru (varování
   „vyfoukne“). Předem daná hypotéza H-R1: rakety z financování, AI-hype, squeeze a sektorové vlny se do 3 měsíců
   vyfouknou častěji než rakety z klinických dat, převzetí a výsledků (AUTO statistika to naznačuje, ale n je malé).
   Navíc se změří přesnost AUTO klasifikátoru proti ověřeným příčinám (kolik titulků určilo příčinu špatně).
