"""Primární zdroje smart money (vše zdarma):

* SEC — Insider Transactions Data Sets (strukturovaná data Form 3/4/5 po kvartálech, s příznakem plánu 10b5-1).
  Dotaz na sec.gov nese e-mail → každý se eviduje (contact.http_get).
* Sněmovna USA — rejstřík výkazů (FD.zip) a výkazy transakcí PTR v PDF (text přes `pdftotext`; skeny = BEZ_TEXTU).
* Senát USA — eFD: elektronické výkazy transakcí (HTML tabulka); papírové = BEZ_TEXTU.
"""

import csv
import html
import http.cookiejar
import io
import json
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime

from stockradar import contact
from stockradar.timeutil import to_iso, utcnow

UA = {"User-Agent": "Mozilla/5.0"}
INSIDER_URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{y}q{q}_form345.zip"
KEEP_CODES = {"P", "A", "M"}  # nákup na trhu, přidělení (odměna), uplatnění opce
# Prodej (S) se ukládá jen u osoby, která ve stejném souboru tutéž firmu koupila (P): pozná se tak „nákup a hned
# prodej“ (např. zaměstnanecký plán ESPP — koupí se slevou, druhý den prodá), což není aktivní nákup.
HOUSE_INDEX = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
HOUSE_PTR = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc}.pdf"
SENATE = "https://efdsearch.senate.gov"


def _d(value: str) -> str | None:
    value = (value or "").strip()
    for fmt in ("%d-%b-%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _f(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get(url: str, *, data: bytes | None = None, headers: dict | None = None, opener=None, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with (opener.open if opener else urllib.request.urlopen)(req, timeout=timeout) as r:
        return r.read()


# ------------------------------------------------------------------ SEC Form 3/4/5

def parse_insider_zip(raw: bytes) -> list[tuple]:
    z = zipfile.ZipFile(io.BytesIO(raw))

    def rows(name):
        with z.open(name) as f:
            yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter="\t",
                                      quoting=csv.QUOTE_NONE)

    subs = {}
    for r in rows("SUBMISSION.tsv"):
        if r["DOCUMENT_TYPE"] not in ("4", "4/A", "5", "5/A"):
            continue
        subs[r["ACCESSION_NUMBER"]] = (_d(r["FILING_DATE"]), _f(r["ISSUERCIK"]), (r["ISSUERTRADINGSYMBOL"] or "").strip().upper(),
                                       r["ISSUERNAME"], 1 if (r.get("AFF10B5ONE") or "").strip() in ("1", "true", "Y") else 0,
                                       r["DOCUMENT_TYPE"])
    owners: dict[str, list] = {}
    for r in rows("REPORTINGOWNER.tsv"):
        acc = r["ACCESSION_NUMBER"]
        if acc not in subs:
            continue
        o = owners.setdefault(acc, [_f(r["RPTOWNERCIK"]), r["RPTOWNERNAME"], set(), set()])
        o[2].update(x.strip() for x in (r["RPTOWNER_RELATIONSHIP"] or "").split(",") if x.strip())
        if r["RPTOWNER_TITLE"]:
            o[3].add(r["RPTOWNER_TITLE"].strip())
    out, sales, buyers = [], [], set()
    for r in rows("NONDERIV_TRANS.tsv"):
        acc = r["ACCESSION_NUMBER"]
        code = (r["TRANS_CODE"] or "").strip()
        if acc not in subs or code not in KEEP_CODES | {"S"}:
            continue
        filed, cik, ticker, issuer, plan, form = subs[acc]
        o = owners.get(acc, [None, None, set(), set()])
        if code == "P":
            buyers.add((int(o[0]) if o[0] else None, int(cik) if cik else None))
        (sales if code == "S" else out).append((acc, int(r["NONDERIV_TRANS_SK"]), filed, _d(r["TRANS_DATE"]), int(cik) if cik else None,
                    ticker.replace(".", "-") or None, issuer, int(o[0]) if o[0] else None, o[1], ",".join(sorted(o[2])),
                    "; ".join(sorted(o[3])) or None, code, _f(r["TRANS_SHARES"]), _f(r["TRANS_PRICEPERSHARE"]),
                    (r["TRANS_ACQUIRED_DISP_CD"] or "").strip(), _f(r["SHRS_OWND_FOLWNG_TRANS"]),
                    (r["DIRECT_INDIRECT_OWNERSHIP"] or "").strip(), plan, form))
    return out + [t for t in sales if (t[7], t[4]) in buyers]


def fetch_insiders(cache_conn, *, start: tuple[int, int] = (2021, 4), end: date | None = None, log=print) -> dict:
    end = end or utcnow().date()
    done = {r[0] for r in cache_conn.execute("SELECT quarter FROM insider_done")}
    if done and not cache_conn.execute("SELECT 1 FROM insider_tx WHERE code = 'S' LIMIT 1").fetchone():
        done = set()  # data stažená před verzí 0.5.0 neobsahují prodeje kupujících → jednou stáhnout znovu
    y, q = start
    last = (end.year, (end.month - 1) // 3 + 1)
    fetched = rows_total = 0
    while (y, q) <= last:
        key = f"{y}Q{q}"
        recent = (y, q) >= ((end.year, (end.month - 1) // 3) if end.month > 3 else (end.year - 1, 4))
        if key not in done or recent:
            try:
                raw = contact.http_get(INSIDER_URL.format(y=y, q=q), "insider transakce Form 4 (strukturovaná data SEC)",
                                       timeout=180)
            except Exception as exc:  # kvartál ještě nezveřejněn (404)
                log(f"SEC insider {key}: {str(exc)[:80]}")
            else:
                rows = parse_insider_zip(raw)
                with cache_conn:
                    cache_conn.executemany(
                        "INSERT OR REPLACE INTO insider_tx (accession, sk, filing_date, trans_date, issuer_cik, ticker, issuer,"
                        " owner_cik, owner, rel, title, code, shares, price, ad, owned_after, direct, plan10b51, form)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
                    cache_conn.execute("INSERT OR REPLACE INTO insider_done (quarter, n, fetched_at) VALUES (?, ?, ?)",
                                       (key, len(rows), to_iso(utcnow())))
                fetched += 1
                rows_total += len(rows)
                log(f"SEC insider {key}: {len(rows)} transakcí")
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return {"kvartalu": fetched, "transakci": rows_total}


# ------------------------------------------------------------------ Sněmovna (PTR v PDF)

AMOUNT = re.compile(r"\$([\d,]+)")
ROW = re.compile(r"^(?P<pre>.*?)\s(?P<type>P|S \(partial\)|S|E)\s+(?P<tx>\d{2}/\d{2}/\d{4})\s+(?P<notif>\d{2}/\d{2}/\d{4})\s+"
                 r"(?P<amt>\$[\d,]+(?:\s*-)?|Over \$[\d,]+|Spouse/DC Over \$[\d,]+)")
OWNERS = {"SP", "JT", "DC"}


def parse_house_ptr(text: str) -> list[dict]:
    """Řádky výkazu PTR (výstup `pdftotext -layout`). Vrací nákupy i prodeje; transakce bez tickeru se ponechají."""
    lines = [l for l in text.splitlines() if l.strip()]
    starts = [i for i, l in enumerate(lines) if ROW.match(l)]
    out = []
    for n, i in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        m = ROW.match(lines[i])
        block = lines[i:end]
        pre = m.group("pre").strip()
        owner = None
        first = pre.split()[0] if pre.split() else ""
        if first in OWNERS:
            owner, pre = first, pre[len(first):].strip()
        asset_lines = [pre]
        desc = []
        for l in block[1:]:
            s = l.strip()
            label = s.split(":", 1)[0].strip().lower() if ":" in s else ""
            if label in ("d", "description", "c", "comments"):
                desc.append(s.split(":", 1)[1].strip())
                continue
            if (re.match(r"^(F\s+S|S\s+O|ID\s+Owner|Filing ID|\* For the complete)", s, re.I) or label in ("filing status", "f s")
                    or label.startswith("subholding") or s.startswith("D ")):
                continue
            left = re.split(r"\s{3,}", s)[0]
            if not AMOUNT.fullmatch(left.strip()):
                asset_lines.append(left)
        asset = " ".join(a for a in asset_lines if a).strip()
        # starší výkazy mají ticker i typ malými písmeny kvůli fontu („gOOgl“, „AAPl“)
        tick = re.search(r"\(([A-Za-z][A-Za-z0-9.\-]{0,6})\)", asset)
        atype = re.search(r"\[([A-Za-z]{2})\]", asset)
        amounts = [int(a.replace(",", "")) for a in AMOUNT.findall(" ".join(block))]
        lo = amounts[0] if amounts else None
        hi = amounts[1] if len(amounts) > 1 and amounts[1] > (lo or 0) else None
        out.append({"owner": owner or "Self", "asset": re.sub(r"\s*\[[A-Za-z]{2}\]", "", asset)[:200],
                    "ticker": tick.group(1).upper().replace(".", "-") if tick else None,
                    "asset_type": atype.group(1).upper() if atype else None,
                    "tx_type": m.group("type"), "tx_date": _d(m.group("tx")), "amount_min": lo, "amount_max": hi,
                    "description": " ".join(desc)[:300] or None})
    return out


def house_index(year: int) -> list[dict]:
    z = zipfile.ZipFile(io.BytesIO(_get(HOUSE_INDEX.format(year=year))))
    xml = z.read(f"{year}FD.xml").decode("utf-8", "replace")
    out = []
    for m in re.finditer(r"<Member>(.*?)</Member>", xml, re.S):
        rec = dict(re.findall(r"<(\w+)>([^<]*)</\1>", m.group(1)))
        if rec.get("FilingType") == "P" and rec.get("DocID"):
            out.append({"doc_id": rec["DocID"], "member": f"{rec.get('First', '')} {rec.get('Last', '')}".strip(),
                        "filed": _d(rec.get("FilingDate", "")), "year": year})
    return out


def fetch_house(cache_conn, *, years=range(2021, 2027), pause: float = 0.6, refetch: bool = False, log=print) -> dict:
    if not shutil.which("pdftotext"):
        return {"stav": "VYPNUTO — chybí pdftotext"}
    have = set() if refetch else {r[0] for r in cache_conn.execute("SELECT doc_id FROM congress_docs WHERE chamber = 'HOUSE'")}
    stats = {"vykazu": 0, "s_textem": 0, "bez_textu": 0, "transakci": 0}
    for year in years:
        try:
            docs = house_index(year)
        except Exception as exc:
            log(f"Sněmovna {year}: rejstřík nedostupný ({exc})")
            continue
        log(f"Sněmovna {year}: {len(docs)} výkazů transakcí")
        for d in docs:
            if d["doc_id"] in have or not d["filed"]:
                continue
            url = HOUSE_PTR.format(year=year, doc=d["doc_id"])
            status, rows = "CHYBA", []
            try:
                pdf = _get(url, timeout=60)
                text = subprocess.run(["pdftotext", "-layout", "-", "-"], input=pdf, capture_output=True,
                                      timeout=60).stdout.decode("utf-8", "replace")
                rows = parse_house_ptr(text)
                status = "OK" if rows else "BEZ_TEXTU"
            except Exception as exc:
                log(f"  {d['doc_id']}: {str(exc)[:80]}")
            if refetch:
                with cache_conn:
                    cache_conn.execute("DELETE FROM congress_tx WHERE doc_id = ?", (d["doc_id"],))
            _store_doc(cache_conn, d["doc_id"], "HOUSE", d["member"], d["filed"], url, status, rows)
            stats["vykazu"] += 1
            stats["s_textem" if status == "OK" else "bez_textu"] += 1
            stats["transakci"] += len(rows)
            time.sleep(pause)
    return stats


def _store_doc(cache_conn, doc_id, chamber, member, filed, url, status, rows):
    with cache_conn:
        cache_conn.execute("INSERT OR REPLACE INTO congress_docs (doc_id, chamber, member, filed, url, status, n_rows, fetched_at)"
                           " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (doc_id, chamber, member, filed, url, status, len(rows),
                                                                 to_iso(utcnow())))
        cache_conn.executemany(
            "INSERT OR REPLACE INTO congress_tx (doc_id, row, chamber, member, owner, filed, tx_date, ticker, asset, asset_type,"
            " tx_type, amount_min, amount_max, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(doc_id, i, chamber, member, r["owner"], filed, r["tx_date"], r["ticker"], r["asset"], r["asset_type"],
              r["tx_type"], r["amount_min"], r["amount_max"], r["description"]) for i, r in enumerate(rows)])


# ------------------------------------------------------------------ Senát (eFD)

def _senate_session():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    home = _get(f"{SENATE}/search/home/", opener=op).decode()
    tok = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', home).group(1)
    _get(f"{SENATE}/search/home/", opener=op, headers={"Referer": f"{SENATE}/search/home/"},
         data=urllib.parse.urlencode({"prohibition_agreement": "1", "csrfmiddlewaretoken": tok}).encode())
    csrf = next(c.value for c in cj if c.name == "csrftoken")
    return op, csrf


TAGS = re.compile(r"<[^>]+>")


def parse_senate_ptr(page: str) -> list[dict]:
    body = page.split("<tbody>", 1)[-1].split("</tbody>", 1)[0]
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [html.unescape(TAGS.sub(" ", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        cells = [re.sub(r"\s+", " ", c) for c in cells]
        if len(cells) < 8:
            continue
        _, tx_date, owner, ticker, asset, atype, ttype, amount = cells[:8]
        amounts = [int(a.replace(",", "")) for a in AMOUNT.findall(amount)]
        tick = ticker.strip() if ticker.strip() not in ("--", "") else None
        out.append({"owner": owner, "asset": asset[:200], "ticker": tick.replace(".", "-") if tick else None,
                    "asset_type": "ST" if atype.lower().startswith("stock") else "OP" if "option" in atype.lower() else atype[:20],
                    "tx_type": "P" if ttype.lower().startswith("purchase") else "S" if ttype.lower().startswith("sale") else
                    "E" if ttype.lower().startswith("exchange") else ttype[:20],
                    "tx_date": _d(tx_date), "amount_min": amounts[0] if amounts else None,
                    "amount_max": amounts[1] if len(amounts) > 1 else None,
                    "description": (cells[8] if len(cells) > 8 and cells[8] not in ("--", "") else None)})
    return out


def fetch_senate(cache_conn, *, start: str = "01/01/2021", pause: float = 0.6, part: int = 0, parts: int = 1,
                 log=print) -> dict:
    op, csrf = _senate_session()
    have = {r[0] for r in cache_conn.execute("SELECT doc_id FROM congress_docs WHERE chamber = 'SENATE'")}
    reports, offset = [], 0
    while True:
        body = urllib.parse.urlencode({"start": str(offset), "length": "100", "report_types": "[11]", "filer_types": "[]",
                                       "submitted_start_date": f"{start} 00:00:00", "submitted_end_date": "",
                                       "candidate_state": "", "senator_state": "", "office_id": "", "first_name": "",
                                       "last_name": "", "csrfmiddlewaretoken": csrf}).encode()
        page = json.loads(_get(f"{SENATE}/search/report/data/", data=body, opener=op,
                               headers={"Referer": f"{SENATE}/search/", "X-CSRFToken": csrf}))
        rows = page.get("data", [])
        for first, last, _full, link, filed in rows:
            href = re.search(r'href="([^"]+)"', link).group(1)
            reports.append({"doc_id": href.strip("/").split("/")[-1], "member": f"{first} {last}".strip(),
                            "filed": _d(filed), "url": SENATE + href, "paper": "/paper/" in href})
        offset += len(rows)
        if not rows or offset >= page.get("recordsTotal", 0):
            break
        time.sleep(pause)
    log(f"Senát: {len(reports)} výkazů transakcí")
    stats = {"vykazu": 0, "s_textem": 0, "bez_textu": 0, "transakci": 0}
    for k, r in enumerate(reports):
        if k % parts != part or r["doc_id"] in have or not r["filed"]:
            continue
        status, rows = "BEZ_TEXTU", []
        if not r["paper"]:
            try:
                rows = parse_senate_ptr(_get(r["url"], opener=op).decode("utf-8", "replace"))
                status = "OK" if rows else "BEZ_TEXTU"
            except Exception as exc:
                status = "CHYBA"
                log(f"  {r['doc_id']}: {str(exc)[:80]}")
            time.sleep(pause)
        _store_doc(cache_conn, r["doc_id"], "SENATE", r["member"], r["filed"], r["url"], status, rows)
        stats["vykazu"] += 1
        stats["s_textem" if status == "OK" else "bez_textu"] += 1
        stats["transakci"] += len(rows)
    return stats


def senate_roles(cache_conn, *, start: str = "01/01/2021") -> int:
    """Doplní ke jménu v Senátu roli z vyhledávání (Senator / Former Senator / Candidate …); kandidáti nejsou
    zákonodárci a v analýze politiků se oddělí."""
    op, csrf = _senate_session()
    roles, offset = {}, 0
    while True:
        body = urllib.parse.urlencode({"start": str(offset), "length": "100", "report_types": "[11]", "filer_types": "[]",
                                       "submitted_start_date": f"{start} 00:00:00", "submitted_end_date": "",
                                       "candidate_state": "", "senator_state": "", "office_id": "", "first_name": "",
                                       "last_name": "", "csrfmiddlewaretoken": csrf}).encode()
        page = json.loads(_get(f"{SENATE}/search/report/data/", data=body, opener=op,
                               headers={"Referer": f"{SENATE}/search/", "X-CSRFToken": csrf}))
        for _first, _last, full, link, _filed in page.get("data", []):
            href = re.search(r'href="([^"]+)"', link).group(1)
            m = re.search(r"\(([^)]+)\)\s*$", full)
            roles[href.strip("/").split("/")[-1]] = m.group(1) if m else "?"
        offset += len(page.get("data", []))
        if not page.get("data") or offset >= page.get("recordsTotal", 0):
            break
    n = 0
    with cache_conn:
        for doc, role in roles.items():
            if role != "Senator":
                n += cache_conn.execute("UPDATE congress_tx SET member = member || ' (' || ? || ')' WHERE doc_id = ?"
                                        " AND member NOT LIKE '%(%'", (role, doc)).rowcount
                cache_conn.execute("UPDATE congress_docs SET member = member || ' (' || ? || ')' WHERE doc_id = ?"
                                   " AND member NOT LIKE '%(%'", (role, doc))
    return n
