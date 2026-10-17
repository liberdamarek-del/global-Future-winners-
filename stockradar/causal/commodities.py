"""Komodity a obchodní uzly: SVĚT → KOMODITA → OBORY (řád 1–4) → FIRMY.

Každý řetězec je HYPOTÉZA z ekonomické logiky („cena X roste → obor Y má dražší vstupy“). O tom, zda se dá použít
k predikci, rozhoduje historický test v `chains.py` (učení / validace / zamčený test proti náhodným dvojicím).
Výrobní země jsou NEOVĚŘENO, dokud u nich není zdroj (USGS, USDA, ICCO, EIA… → VERIFIED_PRODUCERS) — slouží k přiřazení události
(např. hurikán v Pobřeží slonoviny → kakao) a vždy se tak i zobrazí.

`smer` = dopad na obor, když cena komodity ROSTE (+1 pomáhá, −1 škodí). Obory jsou vzory na názvy oborů v datech
(Nasdaq screener / Yahoo), malými písmeny.
"""

import re

NEOVERENO = "NEOVĚŘENO"

# (řád, vzor oboru, směr při růstu ceny, proč)
COMMODITIES = [
    {"id": "BRENT", "symbol": "BZ=F", "nazev": "Ropa Brent", "skupina": "energie",
     "slova": r"\b(oil|crude|brent|opec|refiner\w*|pipeline|tanker)\b",
     "vyrobci": ["USA", "Saúdská Arábie", "Rusko", "Kanada", "Irák", "SAE", "Írán", "Brazílie", "Kuvajt", "Norsko"],
     "uzly": ["Hormuzský průliv", "Rudé moře / Bab al-Mandab", "Suezský průplav"],
     "retez": [(1, r"oil & gas production|integrated oil", +1, "vyšší cena = vyšší tržby těžařů"),
               (2, r"oilfield services|oil and gas field machinery", +1, "těžaři víc investují do vrtů (zpoždění měsíce)"),
               (1, r"air freight/delivery", -1, "palivo je velká část nákladů letectví a dopravy"),
               (2, r"trucking|railroads|marine transportation", -1, "dražší nafta a lodní palivo"),
               (2, r"major chemicals|plastic products|specialty chemicals", -1, "ropa je surovina chemie a plastů"),
               (3, r"restaurants|hotels/resorts|other specialty stores|clothing/shoe", -1, "méně peněz domácností na ostatní útraty")]},
    {"id": "WTI", "symbol": "CL=F", "nazev": "Ropa WTI", "skupina": "energie", "slova": r"\b(wti|shale|permian|cushing)\b",
     "vyrobci": ["USA"], "uzly": [],
     "retez": [(1, r"oil & gas production|integrated oil", +1, "tržby amerických těžařů"),
               (2, r"oilfield services|oil and gas field machinery", +1, "investice do vrtů v USA")]},
    {"id": "NATGAS", "symbol": "NG=F", "nazev": "Zemní plyn (Henry Hub)", "skupina": "energie",
     "slova": r"\b(natural gas|lng|gas pipeline|henry hub)\b",
     "vyrobci": ["USA", "Rusko", "Írán", "Čína", "Kanada", "Katar", "Norsko", "Austrálie"], "uzly": [],
     "retez": [(1, r"oil & gas production", +1, "tržby producentů plynu"),
               (1, r"agricultural chemicals", -1, "plyn je hlavní surovina dusíkatých hnojiv"),
               (2, r"farming/seeds/milling", -1, "dražší hnojiva → vyšší náklady farem"),
               (2, r"major chemicals", -1, "energie a surovina chemie"),
               (3, r"packaged foods|meat/poultry", -1, "dražší vstupy potravin")]},
    {"id": "DIESEL", "symbol": "HO=F", "nazev": "Nafta / topný olej", "skupina": "energie", "slova": r"\b(diesel|distillate|heating oil)\b",
     "vyrobci": [], "uzly": [],
     "retez": [(1, r"oil refining", +1, "marže rafinerií"),
               (1, r"trucking|railroads|air freight", -1, "palivo dopravy"),
               (3, r"food chains|food distributors", -1, "dražší distribuce")]},
    {"id": "GASOLINE", "symbol": "RB=F", "nazev": "Benzín", "skupina": "energie", "slova": r"\b(gasoline|refinery outage|refinery fire)\b",
     "vyrobci": [], "uzly": [],
     "retez": [(1, r"oil refining", +1, "marže rafinerií"),
               (2, r"restaurants|hotels/resorts|services-misc. amusement", -1, "dražší cestování a menší útraty")]},
    {"id": "GOLD", "symbol": "GC=F", "nazev": "Zlato", "skupina": "kovy", "slova": r"\b(gold|bullion)\b",
     "vyrobci": ["Čína", "Rusko", "Austrálie", "Kanada", "USA", "Ghana"], "uzly": [],
     "retez": [(1, r"precious metals", +1, "marže těžařů zlata rostou rychleji než cena")]},
    {"id": "SILVER", "symbol": "SI=F", "nazev": "Stříbro", "skupina": "kovy", "slova": r"\bsilver\b",
     "vyrobci": ["Mexiko", "Čína", "Peru", "Bolívie", "Chile"], "uzly": [],
     "retez": [(1, r"precious metals", +1, "tržby těžařů stříbra"),
               (2, r"electrical products|electronic components", -1, "stříbro v elektronice a solárních panelech")]},
    {"id": "COPPER", "symbol": "HG=F", "nazev": "Měď", "skupina": "kovy", "slova": r"\b(copper|smelter)\b",
     "vyrobci": ["Chile", "Peru", "DR Kongo", "Čína", "USA", "Indonésie", "Zambie", "Mexiko"], "uzly": [],
     "retez": [(1, r"metal mining|other metals and minerals", +1, "tržby těžařů mědi"),
               (2, r"electrical products|electronic components|water sewer pipeline", -1, "měď v kabelech a elektro"),
               (3, r"homebuilding|building products", -1, "dražší instalace ve stavbách")]},
    {"id": "ALUMINIUM", "symbol": "ALI=F", "nazev": "Hliník", "skupina": "kovy", "slova": r"\b(alumin(i)?um|bauxite|alumina)\b",
     "vyrobci": ["Čína", "Indie", "Rusko", "Kanada", "SAE", "Bahrajn"], "uzly": ["Guinea (bauxit)", "Austrálie (bauxit)"],
     "retez": [(1, r"aluminum|metal mining", +1, "tržby hutí a těžařů"),
               (2, r"containers/packaging|beverages", -1, "plechovky a obaly"),
               (2, r"aerospace|auto manufacturing|motor vehicles", -1, "hliník v letadlech a autech")]},
    {"id": "IRONORE", "symbol": "TIO=F", "nazev": "Železná ruda", "skupina": "kovy", "slova": r"\b(iron ore)\b",
     "vyrobci": ["Austrálie", "Brazílie", "Čína", "Indie", "Rusko", "Írán"], "uzly": [],
     "retez": [(1, r"metal mining|steel/iron ore", +1, "tržby těžařů rudy"),
               (2, r"marine transportation", +1, "objem námořní přepravy rudy")]},
    {"id": "STEEL", "symbol": "HRC=F", "nazev": "Ocel (US HRC)", "skupina": "kovy", "slova": r"\b(steel|tariff\w* on steel)\b",
     "vyrobci": ["Čína", "Indie", "Japonsko", "USA", "Rusko"], "uzly": [],
     "retez": [(1, r"steel/iron ore", +1, "ceny a marže oceláren"),
               (2, r"auto manufacturing|motor vehicles|construction/ag equipment|industrial machinery|metal fabrications", -1,
                "ocel je hlavní vstup strojírenství a aut")]},
    {"id": "PLATINUM", "symbol": "PL=F", "nazev": "Platina", "skupina": "kovy", "slova": r"\bplatinum\b",
     "vyrobci": ["Jižní Afrika", "Rusko", "Zimbabwe"], "uzly": [],
     "retez": [(1, r"precious metals", +1, "tržby těžařů"), (2, r"auto parts", -1, "katalyzátory aut")]},
    {"id": "PALLADIUM", "symbol": "PA=F", "nazev": "Palladium", "skupina": "kovy", "slova": r"\bpalladium\b",
     "vyrobci": ["Rusko", "Jižní Afrika", "Kanada", "USA"], "uzly": [],
     "retez": [(1, r"precious metals", +1, "tržby těžařů"), (2, r"auto parts", -1, "katalyzátory aut")]},
    {"id": "URANIUM", "symbol": "U-UN.TO", "nazev": "Uran (Sprott Physical Uranium Trust)", "skupina": "energie",
     "slova": r"\b(uranium|enrichment|nuclear fuel)\b",
     "vyrobci": ["Kazachstán", "Kanada", "Namibie", "Austrálie", "Uzbekistán", "Niger"], "uzly": [],
     "retez": [(1, r"other metals and minerals|metal mining", +1, "tržby těžařů uranu"),
               (2, r"power generation|electric utilities", -1, "palivo jaderných elektráren (malý podíl nákladů)")]},
    {"id": "CORN", "symbol": "ZC=F", "nazev": "Kukuřice", "skupina": "zemědělství", "slova": r"\b(corn|maize|ethanol)\b",
     "vyrobci": ["USA", "Čína", "Brazílie", "Argentina", "Ukrajina", "Indie", "EU"], "uzly": [],
     "retez": [(1, r"farming/seeds/milling|agricultural chemicals", +1, "tržby farem a dodavatelů osiv a hnojiv"),
               (2, r"meat/poultry/fish", -1, "krmivo je hlavní náklad chovu"),
               (3, r"packaged foods|restaurants", -1, "dražší potraviny")]},
    {"id": "WHEAT", "symbol": "ZW=F", "nazev": "Pšenice", "skupina": "zemědělství", "slova": r"\b(wheat|grain export\w*|grain corridor)\b",
     "vyrobci": ["Čína", "Indie", "Rusko", "USA", "EU", "Kanada", "Austrálie", "Ukrajina", "Argentina", "Kazachstán", "Pákistán"],
     "uzly": ["Černé moře"],
     "retez": [(1, r"farming/seeds/milling", +1, "mlýny a obchodníci s obilím"),
               (2, r"packaged foods|specialty foods", -1, "mouka v pečivu a těstovinách"),
               (3, r"restaurants|food chains", -1, "dražší potraviny")]},
    {"id": "SOY", "symbol": "ZS=F", "nazev": "Sója", "skupina": "zemědělství", "slova": r"\b(soy\w*)\b",
     "vyrobci": ["Brazílie", "USA", "Argentina", "Čína", "Paraguay"], "uzly": [],
     "retez": [(1, r"farming/seeds/milling|agricultural chemicals", +1, "zpracovatelé a dodavatelé farem"),
               (2, r"meat/poultry/fish", -1, "sójový šrot jako krmivo")]},
    {"id": "COFFEE", "symbol": "KC=F", "nazev": "Káva (arabika)", "skupina": "zemědělství", "slova": r"\b(coffee|arabica|robusta)\b",
     "vyrobci": ["Brazílie", "Vietnam", "Kolumbie", "Indonésie", "Etiopie", "Honduras"], "uzly": [],
     "retez": [(1, r"packaged foods|beverages", -1, "pražírny a výrobci kávy"),
               (2, r"restaurants", -1, "kavárenské řetězce")]},
    {"id": "COCOA", "symbol": "CC=F", "nazev": "Kakao", "skupina": "zemědělství", "slova": r"\b(cocoa|cacao)\b",
     "vyrobci": ["Pobřeží slonoviny", "Ghana", "Ekvádor", "Kamerun", "Nigérie", "Indonésie"], "uzly": [],
     "retez": [(1, r"packaged foods|specialty foods|consumer specialties", -1, "výrobci čokolády a cukrovinek"),
               (2, r"food chains|food distributors", -1, "dražší sortiment, nižší objem prodeje")]},
    {"id": "SUGAR", "symbol": "SB=F", "nazev": "Cukr", "skupina": "zemědělství", "slova": r"\b(sugar|sugarcane)\b",
     "vyrobci": ["Brazílie", "Indie", "Thajsko", "Čína", "EU", "USA", "Pákistán", "Rusko"], "uzly": [],
     "retez": [(1, r"farming/seeds/milling", +1, "producenti cukru a etanolu"),
               (2, r"packaged foods|beverages", -1, "cukr v nápojích a sladkostech")]},
    {"id": "COTTON", "symbol": "CT=F", "nazev": "Bavlna", "skupina": "zemědělství", "slova": r"\bcotton\b",
     "vyrobci": ["Čína", "Indie", "USA", "Brazílie", "Pákistán", "Austrálie"], "uzly": [],
     "retez": [(1, r"textiles|apparel|garments and clothing", -1, "bavlna je hlavní surovina oděvů"),
               (2, r"clothing/shoe/accessory stores|department/specialty retail", -1, "marže prodejců oblečení")]},
    {"id": "ORANGEJUICE", "symbol": "OJ=F", "nazev": "Pomerančová šťáva", "skupina": "zemědělství", "slova": r"\b(orange juice|citrus)\b",
     "vyrobci": ["Brazílie", "USA (Florida)"], "uzly": [],
     "retez": [(1, r"beverages", -1, "výrobci džusů")]},
    {"id": "CATTLE", "symbol": "LE=F", "nazev": "Skot", "skupina": "zemědělství", "slova": r"\b(cattle|beef)\b",
     "vyrobci": ["USA", "Brazílie", "Čína", "Argentina", "Austrálie"], "uzly": [],
     "retez": [(1, r"meat/poultry/fish", -1, "zpracovatelé masa nakupují dobytek"),
               (2, r"restaurants|food chains", -1, "dražší maso v restauracích")]},
    {"id": "HOGS", "symbol": "HE=F", "nazev": "Prasata", "skupina": "zemědělství", "slova": r"\b(hogs?|pork|swine fever)\b",
     "vyrobci": ["Čína", "EU", "USA", "Brazílie", "Vietnam", "Rusko"], "uzly": [],
     "retez": [(1, r"meat/poultry/fish", +1, "producenti vepřového (část zpracovatelů prodělává)")]},
    {"id": "LUMBER", "symbol": "LBR=F", "nazev": "Řezivo", "skupina": "stavba", "slova": r"\b(lumber|timber|sawmill|wildfire)\b",
     "vyrobci": ["Kanada", "USA", "Rusko", "Švédsko"], "uzly": [],
     "retez": [(1, r"forest products|paper", +1, "tržby pil a lesnických firem"),
               (2, r"homebuilding|building products|retail: building materials", -1, "dřevo je velký náklad stavby domů")]},
    {"id": "DRYBULK", "symbol": "BDRY", "nazev": "Námořní přeprava sypkých nákladů (ETF futures)", "skupina": "doprava",
     "slova": r"\b(dry bulk|shipping rates|baltic dry|freight rates|canal|port strike|port closure)\b",
     "vyrobci": [], "uzly": ["Panamský průplav", "Suezský průplav", "Rudé moře"],
     "retez": [(1, r"marine transportation", +1, "vyšší sazby = vyšší tržby rejdařů"),
               (2, r"steel/iron ore|farming/seeds/milling", -1, "dražší přeprava surovin")]},
    {"id": "USD", "symbol": "DX-Y.NYB", "nazev": "Dolarový index", "skupina": "makro", "slova": r"\b(dollar index|federal reserve|fed rate)\b",
     "vyrobci": [], "uzly": [],
     "retez": [(1, r"precious metals|metal mining", -1, "silný dolar = levnější komodity v USD")]},
]

BY_ID = {c["id"]: c for c in COMMODITIES}

# Ověřené podíly hlavních výrobců (primární zdroj, rok dat). Komodita bez záznamu = výrobci NEOVĚŘENO.
VERIFIED_PRODUCERS = {
    "ALUMINIUM": {"zdroj": "USGS Mineral Commodity Summaries 2026 — Aluminum (výroba hutí, 2025 odhad)",
                  "url": "https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-aluminum.pdf", "rok": "2025e",
                  "podily": {"Čína": 0.608, "Indie": 0.057, "Rusko": 0.053, "Kanada": 0.045, "SAE": 0.036,
                             "Bahrajn": 0.022, "Austrálie": 0.020}, "overeno": "2026-10-17"},
    "IRONORE": {"zdroj": "USGS Mineral Commodity Summaries 2026 — Iron Ore (těžba, použitelná ruda, 2025 odhad)",
                "url": "https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-iron-ore.pdf", "rok": "2025e",
                "podily": {"Austrálie": 0.377, "Brazílie": 0.162, "Indie": 0.119, "Čína": 0.112, "Írán": 0.036,
                           "Rusko": 0.033, "Kanada": 0.027}, "overeno": "2026-10-17"},
    "CORN": {"zdroj": "USDA FAS — World Agricultural Production, říjen 2026 (Table 04, 2026/27 projekce)",
             "url": "https://apps.fas.usda.gov/psdonline/circulars/production.pdf", "rok": "2026/27",
             "podily": {"USA": 0.315, "Čína": 0.237, "Brazílie": 0.107, "Argentina": 0.043, "Indie": 0.039,
                        "EU": 0.037, "Ukrajina": 0.025}, "overeno": "2026-10-17"},
    "WHEAT": {"zdroj": "USDA FAS — World Agricultural Production, říjen 2026 (Table 02, 2026/27 projekce)",
              "url": "https://apps.fas.usda.gov/psdonline/circulars/production.pdf", "rok": "2026/27",
              "podily": {"Čína": 0.171, "EU": 0.162, "Indie": 0.147, "Rusko": 0.107, "USA": 0.051, "Kanada": 0.044,
                         "Austrálie": 0.038, "Pákistán": 0.035, "Ukrajina": 0.032}, "overeno": "2026-10-17"},
    "SUGAR": {"zdroj": "USDA FAS — Sugar: World Markets and Trade, květen 2026 (2026/27 předpověď, svět 186,1 mil. t)",
              "url": "https://apps.fas.usda.gov/psdonline/circulars/sugar.pdf", "rok": "2026/27",
              "podily": {"Brazílie": 0.228, "Indie": 0.181, "EU": 0.077, "Čína": 0.068, "Thajsko": 0.051, "USA": 0.043,
                         "Pákistán": 0.037, "Rusko": 0.034}, "overeno": "2026-10-17"},
    "HOGS": {"zdroj": "USDA FAS — Livestock and Poultry: World Markets and Trade, 9. 10. 2026 (vepřové, 2026)",
             "url": "https://apps.fas.usda.gov/psdonline/circulars/livestock_poultry.pdf", "rok": "2026",
             "podily": {"Čína": 0.495, "EU": 0.183, "USA": 0.104, "Brazílie": 0.041, "Vietnam": 0.034, "Rusko": 0.033},
             "overeno": "2026-10-17"},
}


def producers_status(commodity_id: str) -> dict:
    """Stav výrobců pro kartu: OVĚŘENO se zdrojem a podíly, jinak NEOVĚŘENO (jen seznam pro přiřazení událostí)."""
    v = VERIFIED_PRODUCERS.get(commodity_id)
    if not v:
        return {"stav": NEOVERENO}
    return {"stav": f"OVĚŘENO ({v['zdroj']})", "podily": v["podily"], "url": v["url"], "rok": v["rok"], "overeno": v["overeno"]}
BY_SYMBOL = {c["symbol"]: c for c in COMMODITIES}
_PAT = {c["id"]: [(r, re.compile(p, re.I), s, why) for r, p, s, why in c["retez"]] for c in COMMODITIES}


def chain_for(commodity_id: str, industry: str | None) -> tuple[int, int, str] | None:
    """(řád, směr, proč) pro obor, pokud ho logický řetězec komodity obsahuje; jinak None."""
    ind = (industry or "").lower()
    for rad, pat, smer, why in _PAT.get(commodity_id, []):
        if pat.search(ind):
            return rad, smer, why
    return None


def match_text(text: str) -> list[str]:
    """Které komodity zmiňuje text události (titulek, popis)."""
    t = text or ""
    return [c["id"] for c in COMMODITIES if re.search(c["slova"], t, re.I)]


def producers_in(country_text: str) -> list[str]:
    """Komodity, jejichž výrobní země (NEOVĚŘENO) se objevuje v textu — např. „Côte d'Ivoire“ → kakao."""
    t = (country_text or "").lower()
    aliases = {"Pobřeží slonoviny": ["ivory coast", "côte d'ivoire", "cote d'ivoire"], "Ghana": ["ghana"],
               "Ekvádor": ["ecuador"], "Kamerun": ["cameroon"], "Nigérie": ["nigeria"], "Indonésie": ["indonesia"],
               "Brazílie": ["brazil"], "Vietnam": ["vietnam", "viet nam"], "Kolumbie": ["colombia"], "Etiopie": ["ethiopia"],
               "Honduras": ["honduras"], "Chile": ["chile"], "Peru": ["peru"], "DR Kongo": ["congo"], "Zambie": ["zambia"],
               "Mexiko": ["mexico"], "Čína": ["china"], "Indie": ["india"], "Rusko": ["russia"], "Ukrajina": ["ukraine"],
               "USA": ["united states", "usa", "u.s."], "Kanada": ["canada"], "Austrálie": ["australia"],
               "Argentina": ["argentina"], "Kazachstán": ["kazakhstan"], "Saúdská Arábie": ["saudi"], "Irák": ["iraq"],
               "Írán": ["iran"], "SAE": ["emirates", "uae"], "Kuvajt": ["kuwait"], "Katar": ["qatar"], "Norsko": ["norway"],
               "Jižní Afrika": ["south africa"], "Zimbabwe": ["zimbabwe"], "Namibie": ["namibia"], "Niger": ["niger "],
               "Uzbekistán": ["uzbekistan"], "Thajsko": ["thailand"], "Pákistán": ["pakistan"], "Paraguay": ["paraguay"],
               "Bolívie": ["bolivia"], "Guinea (bauxit)": ["guinea"], "Bahrajn": ["bahrain"], "Švédsko": ["sweden"],
               "USA (Florida)": ["florida"], "Japonsko": ["japan"],
               "EU": ["european union", "europe", "france", "germany", "poland", "spain", "italy", "romania"],
               "Hormuzský průliv": ["hormuz"], "Rudé moře / Bab al-Mandab": ["red sea", "bab el-mandeb", "houthi"],
               "Rudé moře": ["red sea", "houthi"], "Suezský průplav": ["suez"], "Panamský průplav": ["panama canal"],
               "Černé moře": ["black sea"], "Austrálie (bauxit)": ["australia"]}
    out = []
    for c in COMMODITIES:
        for country in c["vyrobci"] + c["uzly"]:
            if any(a in t for a in aliases.get(country, [country.lower()])):
                out.append(c["id"])
                break
    return out
