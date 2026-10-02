"""Hodnotový řetězec AI → elektřina (§25, §42): uzly, firmy, dohody s Big Tech a katalyzátory.

Výzkum 2026-10-02. Každá dohoda a katalyzátor má zdroj (URL) a datum; odhad je vždy označen jako odhad.
Seed je idempotentní: při opakovaném spuštění přidá jen to, co v databázi ještě není.
"""

import sqlite3
from datetime import datetime, timezone

from stockradar.catalysts import add_catalyst
from stockradar.companies import add_company, add_listing, change_status, find_company
from stockradar.lessons import add_lesson
from stockradar.timeutil import to_iso, utcnow

RESEARCH_SOURCE = "Výzkum radaru 2026-10-02 (web, zdroje u jednotlivých dohod)"
HYPERSCALERS = ("Google", "Microsoft", "Amazon", "Meta")

# (kód, vrstva, název, popis, horizont)
CHAIN_NODES = [
    ("AI_DEMAND", 1, "Poptávka AI datacenter",
     "Google, Microsoft, Amazon a Meta podepisují dlouhodobé smlouvy na stabilní bezemisní elektřinu.", "teď"),
    ("FIRM_POWER_NOW", 2, "Elektřina dnes: jaderné flotily a utility",
     "Existující jaderné elektrárny, restarty a navyšování výkonu — nejrychlejší zdroj stabilní elektřiny.", "0–3 roky"),
    ("ONSITE_POWER", 2, "Elektřina u datacenter: turbíny a palivové články",
     "Plynové turbíny a palivové články jako most, než se postaví nová jádra.", "0–3 roky"),
    ("GEOTHERMAL", 2, "Geotermální energie nové generace",
     "Vrtná technologie z ropného průmyslu; stabilní výkon 24/7.", "1–5 let"),
    ("GRID", 2, "Síť: transformátory, kabely, rozvaděče, výstavba",
     "Úzké hrdlo: dlouhé dodací lhůty transformátorů a vysokonapěťových kabelů.", "0–5 let"),
    ("DC_INFRA", 2, "Napájení a chlazení datacenter", "UPS, rozvody a chlazení uvnitř datacenter.", "0–3 roky"),
    ("STORAGE", 2, "Ukládání energie", "Baterie pro vyrovnání sítě a datacenter.", "0–5 let"),
    ("FUEL_CYCLE", 3, "Jaderné palivo: uran, konverze, obohacování, HALEU",
     "Každý nový reaktor potřebuje palivo; HALEU pro pokročilé reaktory je v USA nedostatkové.", "1–10 let"),
    ("NUCLEAR_SUPPLY", 3, "Komponenty a služby pro jádro",
     "Výkovky tlakových nádob, čerpadla, detekce, EPC výstavba.", "1–10 let"),
    ("ADV_NUCLEAR", 3, "Nová jádra: SMR a pokročilé reaktory",
     "Malé modulární a pokročilé reaktory; první komerční bloky kolem 2030.", "3–10 let"),
    ("FUSION", 4, "Fúze", "Nejvzdálenější a nejrizikovější článek; první elektřina cílena na konec dekády.", "5–15 let"),
]

# název, země, sektor, obor, yahoo symbol, burza, měna, uzly, poznámka
COMPANIES = [
    ("Constellation Energy", "US", "Utilities", "Jaderná flotila (největší v USA)", "CEG", "NASDAQ", "USD", ["FIRM_POWER_NOW"], None),
    ("Vistra", "US", "Utilities", "Výrobce elektřiny (jádro + plyn)", "VST", "NYSE", "USD", ["FIRM_POWER_NOW"], None),
    ("Talen Energy", "US", "Utilities", "Výrobce elektřiny (JE Susquehanna)", "TLN", "NASDAQ", "USD", ["FIRM_POWER_NOW"], None),
    ("NextEra Energy", "US", "Utilities", "Utilita + obnovitelné zdroje", "NEE", "NYSE", "USD", ["FIRM_POWER_NOW"], None),
    ("Southern Company", "US", "Utilities", "Utilita (JE Vogtle a Hatch)", "SO", "NYSE", "USD", ["FIRM_POWER_NOW"], None),
    ("Fervo Energy", "US", "Energy", "Geotermální energie nové generace (EGS)", "FRVO", "NASDAQ", "USD", ["GEOTHERMAL"],
     "IPO 13. 5. 2026 na Nasdaqu."),
    ("Ormat Technologies", "US", "Energy", "Geotermální elektrárny", "ORA", "NYSE", "USD", ["GEOTHERMAL"], None),
    ("Bloom Energy", "US", "Industrials", "Palivové články pro napájení u datacenter", "BE", "NYSE", "USD", ["ONSITE_POWER"], None),
    ("GE Vernova", "US", "Industrials", "Plynové turbíny, síť, SMR BWRX-300", "GEV", "NYSE", "USD",
     ["ONSITE_POWER", "GRID", "ADV_NUCLEAR"], None),
    ("Siemens Energy", "DE", "Industrials", "Plynové turbíny a síťová technika", "ENR.DE", "XETRA", "EUR",
     ["ONSITE_POWER", "GRID"], None),
    ("Oklo", "US", "Energy", "Pokročilé reaktory Aurora", "OKLO", "NYSE", "USD", ["ADV_NUCLEAR"],
     "Riziko ředění: 11. 9. 2026 ohlášen ATM program až 1 mld. USD (zdroj: 24/7 Wall St., 2026-09-10/18)."),
    ("NuScale Power", "US", "Industrials", "Malé modulární reaktory (SMR)", "SMR", "NYSE", "USD", ["ADV_NUCLEAR"], None),
    ("X-Energy", "US", "Energy", "Reaktor Xe-100 + palivo TRISO", "XE", "NASDAQ", "USD", ["ADV_NUCLEAR", "FUEL_CYCLE"],
     "IPO 24. 4. 2026 za 23 USD (Nasdaq: XE)."),
    ("NANO Nuclear Energy", "US", "Energy", "Mikroreaktory", "NNE", "NASDAQ", "USD", ["ADV_NUCLEAR"], None),
    ("Terrestrial Energy", "US", "Energy", "Reaktor s roztavenou solí (IMSR)", "IMSR", "NASDAQ", "USD", ["ADV_NUCLEAR"], None),
    ("Rolls-Royce Holdings", "GB", "Industrials", "Rolls-Royce SMR + letecké motory", "RR.L", "LSE", "GBp", ["ADV_NUCLEAR"], None),
    ("General Fusion", "CA", "Energy", "Fúze (magnetizovaná terčová fúze, LM26)", "GFUZ", "NASDAQ", "USD", ["FUSION"],
     "První veřejně obchodovaná čistě fúzní firma (Nasdaq od 13. 7. 2026), ~150 mil. USD hotovosti při vstupu. Nízká likvidita."),
    ("Trump Media & Technology Group", "US", "Communication", "Slučuje se s fúzní firmou TAE Technologies", "DJT", "NASDAQ", "USD",
     ["FUSION"], "Expozice na TAE (investor Google) až po dokončení fúze; dnes hlavně mediální firma."),
    ("Cameco", "CA", "Energy", "Těžba uranu, konverze, podíl ve Westinghouse", "CCJ", "NYSE", "USD", ["FUEL_CYCLE"], None),
    ("Uranium Energy", "US", "Energy", "Těžba uranu (ISR)", "UEC", "NYSE American", "USD", ["FUEL_CYCLE"], None),
    ("NexGen Energy", "CA", "Energy", "Vývoj ložiska uranu Rook I", "NXE", "NYSE", "USD", ["FUEL_CYCLE"], None),
    ("Denison Mines", "CA", "Energy", "Vývoj uranu (Phoenix ISR)", "DNN", "NYSE American", "USD", ["FUEL_CYCLE"], None),
    ("Energy Fuels", "US", "Materials", "Uran + vzácné zeminy", "UUUU", "NYSE American", "USD", ["FUEL_CYCLE"], None),
    ("Centrus Energy", "US", "Energy", "Obohacování uranu LEU/HALEU", "LEU", "NYSE", "USD", ["FUEL_CYCLE"], None),
    ("ASP Isotopes", "US", "Materials", "Obohacování izotopů", "ASPI", "NASDAQ", "USD", ["FUEL_CYCLE"], None),
    ("Lightbridge", "US", "Energy", "Pokročilé jaderné palivo", "LTBR", "NASDAQ", "USD", ["FUEL_CYCLE"], None),
    ("BWX Technologies", "US", "Industrials", "Reaktorové komponenty, palivo TRISO", "BWXT", "NYSE", "USD", ["NUCLEAR_SUPPLY"], None),
    ("Curtiss-Wright", "US", "Industrials", "Čerpadla a komponenty pro reaktory", "CW", "NYSE", "USD", ["NUCLEAR_SUPPLY"], None),
    ("Mirion Technologies", "US", "Industrials", "Detekce záření", "MIR", "NYSE", "USD", ["NUCLEAR_SUPPLY"], None),
    ("Japan Steel Works", "JP", "Industrials", "Výkovky tlakových nádob reaktorů", "5631.T", "TSE", "JPY", ["NUCLEAR_SUPPLY"], None),
    ("Doosan Enerbility", "KR", "Industrials", "Reaktorové nádoby, výroba SMR, turbíny", "034020.KS", "KRX", "KRW",
     ["NUCLEAR_SUPPLY", "ONSITE_POWER"], None),
    ("Fluor", "US", "Industrials", "EPC výstavba (Centrus Piketon), podíl v NuScale", "FLR", "NYSE", "USD", ["NUCLEAR_SUPPLY"], None),
    ("HD Hyundai Electric", "KR", "Industrials", "Velké transformátory", "267260.KS", "KRX", "KRW", ["GRID"], None),
    ("Hyosung Heavy Industries", "KR", "Industrials", "Transformátory", "298040.KS", "KRX", "KRW", ["GRID"], None),
    ("LS Electric", "KR", "Industrials", "Rozvaděče a transformátory", "010120.KS", "KRX", "KRW", ["GRID"], None),
    ("Hitachi", "JP", "Industrials", "Hitachi Energy — síťová technika", "6501.T", "TSE", "JPY", ["GRID"], None),
    ("Prysmian", "IT", "Industrials", "Vysokonapěťové kabely", "PRY.MI", "Borsa Italiana", "EUR", ["GRID"], None),
    ("Nexans", "FR", "Industrials", "Kabely", "NEX.PA", "Euronext Paris", "EUR", ["GRID"], None),
    ("NKT", "DK", "Industrials", "Vysokonapěťové kabely", "NKT.CO", "Nasdaq Copenhagen", "DKK", ["GRID"], None),
    ("Hammond Power Solutions", "CA", "Industrials", "Suché transformátory", "HPS-A.TO", "TSX", "CAD", ["GRID"], None),
    ("Powell Industries", "US", "Industrials", "Rozvaděče", "POWL", "NASDAQ", "USD", ["GRID"], None),
    ("Eaton", "IE", "Industrials", "Elektrotechnika pro síť a datacentra", "ETN", "NYSE", "USD", ["GRID", "DC_INFRA"], None),
    ("Quanta Services", "US", "Industrials", "Výstavba přenosové soustavy", "PWR", "NYSE", "USD", ["GRID"], None),
    ("Vertiv", "US", "Industrials", "Napájení a chlazení datacenter", "VRT", "NYSE", "USD", ["DC_INFRA"], None),
    ("Fluence Energy", "US", "Industrials", "Bateriová úložiště", "FLNC", "NASDAQ", "USD", ["STORAGE"], None),
    ("Eos Energy Enterprises", "US", "Industrials", "Zinkové baterie", "EOSE", "NASDAQ", "USD", ["STORAGE"], None),
]

# §23: firmy před vstupem na burzu (bez listingu).
PRE_IPO = [
    ("Holtec Nuclear", "US", "Industrials", "Jaderné služby, SMR-300, skladování paliva", "PRE_IPO",
     "S-1 podáno 2026; IPO (ticker HNUC) odloženo 16. 9. 2026 kvůli propadu trhu (zdroj: IPOScoop, Bloomberg 2026-07-10)."),
]

# (yahoo symbol firmy nebo None, strana, protistrana, typ, závaznost, MW, USD, popis, datum oznámení, zdroj, URL)
RELATIONSHIPS = [
    (None, "Kairos Power", "Google", "PPA", "FRAMEWORK", 500, None,
     "Rámcová dohoda: až 500 MW z pokročilých reaktorů Kairos do roku 2035, první blok do 2030.",
     "2024-10-14", "Google blog",
     "https://blog.google/company-news/outreach-and-initiatives/sustainability/google-kairos-power-nuclear-energy-agreement/"),
    (None, "Kairos Power – Hermes 2 (TVA)", "Google", "PPA", "FIRM", 50, None,
     "TVA odebere až 50 MW z Hermes 2 (Oak Ridge) pro datacentra Google; provoz 2030. První PPA utility na reaktor IV. generace.",
     "2025-08-18", "World Nuclear News",
     "https://www.world-nuclear-news.org/articles/google-kairos-power-tva-announce-collaboration"),
    (None, "Commonwealth Fusion Systems", "Google", "PPA", "FIRM", 200, None,
     "200 MW z první fúzní elektrárny ARC (Virginie) + investice Google. Demonstrátor SPARC: první plazma cílena 2027.",
     "2025-06-30", "Carbon Credits",
     "https://carboncredits.com/google-backs-fusion-energy-signs-200mw-offtake-agreement-with-commonwealth-fusion-systems/"),
    ("DJT", "TAE Technologies (fúze s DJT)", "Google", "INVESTMENT", "PENDING", None, None,
     "Google je investorem TAE. Expozice přes DJT vznikne až dokončením fúze (cíl Q4 2026).",
     "2025-12-19", "World Nuclear News",
     "https://www.world-nuclear-news.org/articles/trump-media-announces-merger-with-fusion-firm-tae-technologies"),
    ("DJT", "TAE Technologies", "Trump Media & Technology Group", "MERGER", "PENDING", None, 6e9,
     "Fúze akciemi ~50/50, hodnota >6 mld. USD; TMTG dává TAE až 300 mil. USD. S-4 podáno 30. 9. 2026, uzavření cíleno Q4 2026.",
     "2025-12-19", "World Nuclear News; SEC S-4 (2026-09-30)",
     "https://www.world-nuclear-news.org/articles/trump-media-announces-merger-with-fusion-firm-tae-technologies"),
    (None, "Elementl Power", "Google", "DEVELOPMENT_FUNDING", "OPTION", 1800, None,
     "Kapitál na přípravu 3 jaderných lokalit (každá ≥600 MW); Google má opci na odběr elektřiny.",
     "2025-05-08", "S&P Global / ANS Nuclear Newswire",
     "https://www.ans.org/news/2025-05-09/article-7012/elementl-and-google-agree-on-sitefirst-approach-to-three-nuclear-projects/"),
    ("NEE", "NextEra – JE Duane Arnold (restart)", "Google", "PPA", "FIRM", None, None,
     "25letá smlouva na elektřinu z restartované JE Duane Arnold (Iowa); restart cílen na Q1 2029, DOE půjčka až 1,9 mld. USD.",
     "2025-10-27", "ANS Nuclear Newswire",
     "https://www.ans.org/news/article-7501/nextera-and-google-ink-a-deal-to-restart-duane-arnold/"),
    (None, "Intersect Power", "Google", "ACQUISITION", "FIRM", None, 4.75e9,
     "Alphabet koupil vývojáře energetických a datacentrových projektů (několik GW); akvizice uzavřena v 1. pololetí 2026.",
     "2026-01-05", "pv magazine", "https://www.pv-magazine.com/2026/01/05/google-acquires-intersect-power-for-nearly-5-billion/"),
    ("FRVO", "Fervo – Cape Station", "Google", "PPA", "FIRM", 396, None,
     "396 MW z Cape Station (Utah) od 2028 + opce na ~600 MW (celkem ~1 GW do 2030). Největší geotermální PPA.",
     "2026-09-01", "GlobeNewswire (Fervo)",
     "https://www.globenewswire.com/news-release/2026/09/01/3354109/0/en/fervo-energy-and-google-sign-396-mw-ppa.html"),
    ("SO", "Georgia Power – navýšení výkonu JE Vogtle a Hatch", "Google", "TARIFF_SUBSCRIPTION", "PENDING", 96, None,
     "Google předplácí ~96 MW navýšení výkonu (tarif NU-1); vyžaduje schválení Georgia PSC.",
     "2026-09-21", "Southern Company (tisková zpráva)",
     "https://southerncompany.mediaroom.com/2026-09-21-Georgia-Power-agreement-with-Google-to-provide-approximately-900-million-in-projected-benefits-for-customers-and-advance-nuclear-energy-in-Georgia"),
    (None, "TotalEnergies – solár Texas", "Google", "PPA", "FIRM", 1000, None,
     "Dvě 15letá PPA na 1 GW solárních elektráren v Texasu.",
     "2026-02-09", "National Law Review", "https://natlawreview.com/article/totalenergies-and-googles-1-gw-texas-solar-deal"),
    (None, "Clearway Energy Group", "Google", "PPA", "FIRM", 1170, None,
     "Tři 20letá PPA (Missouri, Texas, Západní Virginie), nové zdroje 2027–2028. Protistranou je Clearway Energy Group, ne kotovaná CWEN.",
     "2026-01-20", "ESG Dive",
     "https://www.esgdive.com/news/google-inks-ppas-clearway-energy-power-data-centers-with-carbon-free-wv-missouri-tx/810006/"),
    ("VST", "Vistra – JE Beaver Valley, Perry, Davis-Besse", "Meta", "PPA", "FIRM", 2100, None,
     "20leté smlouvy na >2,1 GW + navýšení výkonu; dodávky začínají koncem 2026.",
     "2026-01-09", "Utility Dive",
     "https://www.utilitydive.com/news/meta-nuclear-deal-oklo-vistra-terrapower-ai-data-centers/809215/"),
    ("OKLO", "Oklo – kampus Pike County (Ohio)", "Meta", "PARTNERSHIP", "FRAMEWORK", 1200, None,
     "Kampus pokročilých reaktorů až 1,2 GW do roku 2034.",
     "2026-01-09", "Utility Dive",
     "https://www.utilitydive.com/news/meta-nuclear-deal-oklo-vistra-terrapower-ai-data-centers/809215/"),
    (None, "TerraPower – 2× Natrium", "Meta", "DEVELOPMENT_FUNDING", "FIRM", 690, None,
     "Financování 2 bloků Natrium (2×345 MW), dodávky nejdřív 2032. NRC vydala stavební povolení pro Kemmerer 4. 3. 2026.",
     "2026-01-09", "Utility Dive",
     "https://www.utilitydive.com/news/meta-nuclear-deal-oklo-vistra-terrapower-ai-data-centers/809215/"),
    ("XE", "X-energy", "Amazon", "INVESTMENT", "FIRM", None, 5e8,
     "Amazon investoval ~500 mil. USD (2024) do SMR Xe-100; IPO 24. 4. 2026 za 23 USD.",
     "2024-10-16", "U.S. News / Reuters",
     "https://money.usnews.com/investing/news/articles/2026-04-23/amazon-backed-x-energy-raises-over-1-billion-in-ipo"),
    ("CEG", "Constellation – Crane (TMI-1, restart)", "Microsoft", "PPA", "FIRM", 835, None,
     "20leté PPA na restartovaný blok TMI-1 (Crane Clean Energy Center), provoz cílen 2028.",
     "2024-09-20", "Constellation 8-K (SEC)",
     "https://www.sec.gov/Archives/edgar/data/1868275/000186827524000058/ceg-20240920.htm"),
    ("CEG", "Constellation – JE Clinton", "Meta", "PPA", "FIRM", 1121, None,
     "20leté virtuální PPA od června 2027 + uprate 30 MW; prodlužuje provoz JE Clinton.",
     "2025-06-03", "Constellation (tisková zpráva)",
     "https://www.constellationenergy.com/news/2025/constellation-meta-sign-20-year-deal-for-clean-reliable-nuclear-energy-in-illinois.html"),
    ("TLN", "Talen – JE Susquehanna", "Amazon", "PPA", "FIRM", 1920, None,
     "1,92 GW pro AWS do roku 2042, plný objem nejpozději 2032.",
     "2025-06-11", "Talen 8-K (SEC)",
     "https://www.sec.gov/Archives/edgar/data/1622536/000162828025030559/a20250611pressreleasebusin.htm"),
    ("LEU", "Centrus – Piketon HALEU", "US DOE", "GOVERNMENT_AWARD", "FIRM", None, 9e8,
     "Zakázka DOE 900 mil. USD (+ opce 170 mil.) na komerční výrobu HALEU; kontingentní backlog 3,0 mld. USD.",
     "2026-08-05", "Centrus 8-K (SEC)",
     "https://www.sec.gov/Archives/edgar/data/0001065059/000162828026053433/ex991-10q2026_08x05.htm"),
    ("FLR", "Fluor – EPC pro Centrus Piketon", "Centrus Energy", "SUPPLY", "FIRM", None, None,
     "Fluor je EPC dodavatelem rozšíření obohacovacího závodu Centrus v Piketonu.",
     "2026-02-12", "ANS Nuclear Newswire",
     "https://www.ans.org/news/2026-02-12/article-7754/fluor-to-serve-as-epc-contractor-for-centruss-piketon-plant-expansion/"),
    (None, "Helion Energy", "Microsoft", "PPA", "FIRM", 50, None,
     "PPA na elektřinu z fúze od 2028 (elektrárna Orion). Dřívější cíl čisté elektřiny z Polaris (2024) nebyl splněn.",
     "2023-05-10", "Helion Energy",
     "https://www.helionenergy.com/blog/announcing-helion-fusion-ppa-with-microsoft-constellation"),
]

# (yahoo symbol, typ, popis, stav data, datum nebo okno, zdroj, URL, zveřejněno)
CATALYSTS = [
    ("DJT", "M_AND_A", "Uzavření fúze Trump Media + TAE Technologies (S-4 podáno 30. 9. 2026)", "ESTIMATED",
     ("2026-10-01", "2026-12-31"), "Benzinga 2026-06; SEC S-4 2026-09-30",
     "https://www.benzinga.com/m-a/26/06/53125690/trump-media-tae-technologies-confirm-merger-timeline", "2026-09-30"),
    ("XE", "REGULATORY_OTHER",
     "NRC dokončí finální bezpečnostní hodnocení Long Mott (Xe-100, Dow) → rozhodnutí o stavebním povolení", "ESTIMATED",
     ("2026-11-01", "2026-11-30"), "POWER Magazine / NRC dashboard",
     "https://www.powermag.com/nrc-clears-long-motts-environmental-review-on-a-faster-path-another-milestone-for-commercial-advanced-nuclear/",
     None),
    ("VST", "CONTRACT", "Začátek dodávek elektřiny pro Meta (Beaver Valley, Perry, Davis-Besse)", "UNCERTAIN",
     ("2026-10-01", "2026-12-31"), "Utility Dive 2026-01-09",
     "https://www.utilitydive.com/news/meta-nuclear-deal-oklo-vistra-terrapower-ai-data-centers/809215/", "2026-01-09"),
    ("FRVO", "PRODUCTION_START", "Cape Station fáze I: zbývající 2 bloky (2×33 MW) do komerčního provozu, smluvně do 1. 1. 2027",
     "ESTIMATED", ("2026-10-01", "2027-01-01"), "GlobeNewswire (Fervo) 2026-09-24",
     "https://www.globenewswire.com/news-release/2026/09/24/3368115/0/en/fervo-energy-achieves-first-power-at-cape-station-a-landmark-moment-for-the-future-of-enhanced-geothermal-systems.html",
     "2026-09-24"),
    ("SO", "REGULATORY_OTHER", "Georgia PSC: schválení tarifu NU-1 (Google platí navýšení výkonu Vogtle/Hatch)", "NEOVERENO",
     None, "Southern Company 2026-09-21",
     "https://southerncompany.mediaroom.com/2026-09-21-Georgia-Power-agreement-with-Google-to-provide-approximately-900-million-in-projected-benefits-for-customers-and-advance-nuclear-energy-in-Georgia",
     "2026-09-21"),
    ("NEE", "PRODUCTION_START", "Restart JE Duane Arnold (smlouva s Google)", "ESTIMATED", ("2029-01-01", "2029-03-31"),
     "ANS Nuclear Newswire", "https://www.ans.org/news/article-7501/nextera-and-google-ink-a-deal-to-restart-duane-arnold/",
     "2025-10-27"),
    ("CEG", "PRODUCTION_START", "Restart Crane (TMI-1) pro Microsoft", "ESTIMATED", ("2028-01-01", "2028-12-31"),
     "Constellation 8-K", "https://www.sec.gov/Archives/edgar/data/1868275/000186827524000058/ceg-20240920.htm", "2024-09-20"),
    ("GFUZ", "TECH_DEMO", "LM26: ohřev plazmatu na 1 keV (10 mil. °C), dále 10 keV — termín neověřen (program do 2028)",
     "NEOVERENO", None, "General Fusion",
     "https://generalfusion.com/post/general-fusion-becomes-first-publicly-listed-fusion-company/", "2026-07-13"),
]


def _iso_day(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


def add_tracked_company(conn: sqlite3.Connection, name: str, *, yahoo_symbol: str, exchange: str, currency: str,
                        nodes: list[str], country: str | None = None, sector: str | None = None,
                        industry: str | None = None, notes: str | None = None, reason: str = RESEARCH_SOURCE,
                        now: datetime | None = None) -> int:
    """Přidá veřejnou firmu do radaru: firma + listing s Yahoo symbolem + zařazení v řetězci."""
    now = now or utcnow()
    company_id = add_company(conn, name, country=country, sector=sector, industry=industry, notes=notes, now=now)
    listing_id = add_listing(conn, company_id, yahoo_symbol.split(".")[0], exchange, currency=currency,
                             is_primary=True, now=now)
    with conn:
        conn.execute("UPDATE listings SET yahoo_symbol = ? WHERE id = ?", (yahoo_symbol, listing_id))
        for node in nodes:
            conn.execute("INSERT INTO company_chain (company_id, node_code) VALUES (?, ?)", (company_id, node))
    change_status(conn, company_id, "radar_status", "ACTIVE", reason=reason, source=reason, now=now)
    return company_id


def add_relationship(conn: sqlite3.Connection, *, party: str, counterparty: str, rel_type: str, binding: str,
                     description: str, announced_on: str, source: str, source_url: str,
                     company_id: int | None = None, capacity_mw: float | None = None, amount_usd: float | None = None,
                     now: datetime | None = None) -> int:
    """§24: zapíše dohodu/investici se zdrojem. Rámcová dohoda = FRAMEWORK, ne FIRM."""
    datetime.fromisoformat(announced_on)
    with conn:
        cur = conn.execute(
            "INSERT INTO relationships (company_id, party, counterparty, rel_type, binding, capacity_mw, amount_usd,"
            " description, announced_on, source, source_url, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (company_id, party, counterparty, rel_type, binding, capacity_mw, amount_usd, description, announced_on,
             source, source_url, to_iso(now or utcnow())))
    return cur.lastrowid


def seed_energy_universe(conn: sqlite3.Connection, *, now: datetime | None = None) -> dict[str, int]:
    """Založí uzly, firmy, listingy, dohody a katalyzátory (idempotentně)."""
    now = now or utcnow()
    created = {"chain_nodes": 0, "companies": 0, "relationships": 0, "catalysts": 0}
    with conn:
        for code, layer, name, desc, horizon in CHAIN_NODES:
            cur = conn.execute("INSERT OR IGNORE INTO chain_nodes (code, layer, name, description, horizon)"
                               " VALUES (?, ?, ?, ?, ?)", (code, layer, name, desc, horizon))
            created["chain_nodes"] += cur.rowcount

    by_symbol: dict[str, int] = {}
    for name, country, sector, industry, symbol, exchange, currency, nodes, note in COMPANIES:
        row = find_company(conn, name)
        if row is None:
            company_id = add_tracked_company(conn, name, yahoo_symbol=symbol, exchange=exchange, currency=currency,
                                             nodes=nodes, country=country, sector=sector, industry=industry,
                                             notes=note, reason="Hodnotový řetězec AI → elektřina (výzkum 2026-10-02)",
                                             now=now)
            created["companies"] += 1
        else:
            company_id = row["id"]
        by_symbol[symbol] = company_id

    for name, country, sector, industry, status, note in PRE_IPO:
        if find_company(conn, name) is None:
            company_id = add_company(conn, name, country=country, sector=sector, industry=industry,
                                     listing_status=status, notes=note, now=now)
            with conn:
                conn.execute("INSERT INTO company_chain (company_id, node_code) VALUES (?, 'ADV_NUCLEAR')", (company_id,))
            change_status(conn, company_id, "radar_status", "WATCH",
                          reason="§23 pre-IPO: IPO odloženo, sledovat nový termín", source=RESEARCH_SOURCE, now=now)
            created["companies"] += 1

    existing_rel = {(r["party"], r["counterparty"], r["rel_type"], r["announced_on"])
                    for r in conn.execute("SELECT party, counterparty, rel_type, announced_on FROM relationships")}
    for symbol, party, cp, rtype, binding, mw, usd, desc, day, source, url in RELATIONSHIPS:
        if (party, cp, rtype, day) in existing_rel:
            continue
        add_relationship(conn, party=party, counterparty=cp, rel_type=rtype, binding=binding, description=desc,
                         announced_on=day, source=source, source_url=url,
                         company_id=by_symbol.get(symbol) if symbol else None, capacity_mw=mw, amount_usd=usd, now=now)
        created["relationships"] += 1

    existing_cat = {(r["company_id"], r["description"]) for r in conn.execute("SELECT company_id, description FROM catalysts")}
    for symbol, ctype, desc, date_status, when, source, url, published in CATALYSTS:
        company_id = by_symbol[symbol]
        if (company_id, desc) in existing_cat:
            continue
        kwargs = {"window": when} if date_status in ("ESTIMATED", "UNCERTAIN") else {}
        if date_status == "VERIFIED":
            kwargs = {"event_date": when}
        add_catalyst(conn, company_id, ctype, desc, date_status=date_status, source=source, source_url=url,
                     published_at=_iso_day(published) if published else None, now=now, **kwargs)
        created["catalysts"] += 1

    if conn.execute("SELECT 1 FROM lessons WHERE case_key = 'XTB-VOLITELNE'").fetchone() is None:
        add_lesson(conn, "XTB-VOLITELNE", title="Rozhodnutí uživatele: XTB není povinná podmínka",
                   outcome_type="REFERENCE",
                   summary="2026-10-02 uživatel rozhodl: dostupnost na XTB nebrat jako podmínku doporučení.",
                   lessons=["Stav XTB se zapisuje jen informativně.",
                            "Brána z poučení XSPRAY je vypnutá (config.REQUIRE_XTB_FOR_BUY = False, migrace 0002)."],
                   source="Uživatel, chat 2026-10-02", now=now)
    return created
