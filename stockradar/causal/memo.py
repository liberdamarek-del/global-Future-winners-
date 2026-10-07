"""Sdílená paměť výpočtů: týdenní řady oborů a citlivost na komodity (Exposure) podle otisku vstupů.

`signals` i `causal` potřebují stejné týdenní řady a citlivosti. Ceny akcií se mění jednou týdně (sobotní stažení),
týdenní mřížka končí posledním dnem cen akcií, takže denní ceny komodit po tomto dni výsledek nemění.
Otisk = seznam firem s cenami (počet, poslední den, počet dní, čas stažení) + ceny komodit do posledního dne akcií
+ verze výpočtu. Stejný otisk → načte se uložený výsledek (~1 s) místo načtení 12 000 řad a přepočtu (~60 s).
Soubor je v data/ (mimo git); kdykoli se dá smazat.
"""

import bisect
import hashlib
import json
import pickle
from datetime import date
from pathlib import Path

from stockradar.causal import data as cdata
from stockradar.causal.exposure import MIN_STOCKS, MIN_WEEKS, WINDOW, build_exposure, build_weekly
from stockradar.config import db_path

CALC_VERSION = 1        # zvýšit při změně výpočtu týdenních řad nebo citlivosti


def cache_path() -> Path:
    return db_path().parent / "cache_kauzalni.pkl"


def fingerprint(cache_conn, commodities: dict | None = None) -> tuple[str, str | None]:
    """(otisk, poslední den cen akcií)."""
    stock = cache_conn.execute("SELECT COUNT(*), MAX(s.last_day), SUM(s.n), MAX(s.fetched_at) FROM series s"
                               " JOIN securities m ON m.symbol = s.symbol WHERE s.n >= 250").fetchone()
    end = stock[1]
    h = hashlib.sha256(json.dumps([list(stock), CALC_VERSION, WINDOW, MIN_WEEKS, MIN_STOCKS]).encode())
    if end:
        cut = date.fromisoformat(end).toordinal()
        for cid, b in sorted((commodities if commodities is not None else cdata.load(cache_conn)).items()):
            k = bisect.bisect_right(b.days, cut)
            h.update(f"{cid}:{k}:{b.days[0] if k else 0}:{round(sum(b.closes[:k]), 6)}".encode())
    return h.hexdigest()[:16], end


def load_or_build(cache_conn, *, data=None, path: Path | None = None, log=print):
    """Vrátí (Exposure, poslední den dat jako ordinal, z_cache). `data` (study.Data) stačí dodat, když je už načtené;
    jinak se načte jen při změně otisku."""
    path = path or cache_path()
    comm = cdata.load(cache_conn)
    fp, _ = fingerprint(cache_conn, comm)
    if path.exists():
        try:
            with path.open("rb") as fh:
                saved = pickle.load(fh)
            if saved.get("otisk") == fp:
                log(f"Týdenní řady a citlivosti: z paměti (otisk {fp}, beze změny dat)")
                return saved["exposure"], saved["data_end"], True
        except Exception as exc:                       # poškozený soubor → přepočítat
            log(f"Paměť výpočtů nečitelná ({exc}) — přepočítávám")
    if data is None:
        from stockradar.discovery import study
        data = study.load_data(cache_conn)
    ex = build_exposure(build_weekly(data, comm, log=log))
    tmp = path.with_suffix(".tmp")
    with tmp.open("wb") as fh:
        pickle.dump({"otisk": fp, "exposure": ex, "data_end": data.data_end}, fh, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(path)
    log(f"Týdenní řady a citlivosti: přepočítány a uloženy (otisk {fp})")
    return ex, data.data_end, False
