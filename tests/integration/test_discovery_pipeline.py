"""Integrace Growth Engine nad syntetickými daty: vítězové → studie → kandidáti → ledger (bez sítě)."""

import json
import random
import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest

from stockradar.db import open_db
from stockradar.discovery import cache, engine, store


def business_days(end: date, n: int) -> list[str]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out[::-1]


@pytest.fixture
def synthetic_cache():
    conn = cache.connect(":memory:")
    days = business_days(date(2026, 10, 2), 900)
    rng = random.Random(3)
    for k in range(60):
        sym = f"S{k:02d}"
        vol = 0.01 + (k % 6) * 0.008  # volatilnější firmy mají víc raket
        price, bars = 5 + rng.random() * 20, []
        for i, d in enumerate(days):
            jump = 0.09 if rng.random() < vol / 4 else 0.0
            price *= 1 + rng.gauss(0.0004, vol) + jump
            bars.append((d, max(price, 1.0), 2e5 + rng.random() * 3e5))
        conn.execute("INSERT INTO securities (symbol, name, country, exchange, sector, industry, source, fetched_at)"
                     " VALUES (?, ?, 'United States', 'US', 'Tech', ?, 'test', '2026-10-02T00:00:00Z')",
                     (sym, f"Synthetic {k} Corp", f"Obor {k % 4}"))
        cache.store_series(conn, sym, "USD", bars, source="test", fetched_at="2026-10-02T00:00:00Z")
    conn.commit()
    return conn


def fake_news(q, start, end, lang="en"):
    name = q.split('"')[1] if '"' in q else q
    return [{"datum": (start + timedelta(days=31)).isoformat(), "titulek": f"Why {name} stock soared on new contract",
             "zdroj": "test", "url": "https://example.com"}]


def test_discovery_end_to_end(synthetic_cache, monkeypatch):
    monkeypatch.setattr(store, "MAX_PERCENTILE", 1.0)  # syntetická data: zapsat i mimo horní 1 %
    result = engine.run_discovery(synthetic_cache, news_events=5, news_winners=3, fetch_news=fake_news, log=lambda m: None)
    st = result["statistika"]
    assert st["firem_s_daty"] == 60 and st["rakety"]["W1_30"] > 0
    for kind in ("W1_30", "M3_50"):
        test = result["studie"][kind]["test"]["populace"]
        assert {"zakladni_cetnost", "auc", "top1", "smer"} <= set(test)
        assert result["studie"][kind]["lift"]
    assert result["pricny"]["celkem"] == 5 and result["pricny"]["podle_priciny"][0]["pricina"]
    assert all(c["faze"] in ("EARLY", "DEVELOPING") for rows in result["kandidati"].values() for c in rows)
    assert any(k["vysledek"].startswith("NEOVĚŘENO") for k in result["zname_pripady"])

    main = open_db(":memory:")
    main.execute("INSERT INTO price_bars (symbol, date, close, volume, source, fetched_at)"
                 " VALUES ('SPY', '2026-10-02', 700, 1, 'test', '2026-10-02T21:00:00Z')")
    main.commit()
    now = datetime(2026, 10, 3, 8, 0, tzinfo=timezone.utc)
    run_id = store.save_run(main, result, now=now)
    created, notes = store.record_candidates(main, synthetic_cache, result, run_id, now=now)
    assert created, notes
    rows = main.execute("SELECT source, verdict, discovery_run_id, horizon FROM predictions").fetchall()
    assert {r["source"] for r in rows} == {"DISCOVERY"} and {r["verdict"] for r in rows} == {"WATCH"}
    assert {r["discovery_run_id"] for r in rows} == {run_id}
    # kandidáti nesmí vstoupit do energetického modelu (nemají článek řetězce)
    assert main.execute("SELECT COUNT(*) FROM company_chain").fetchone()[0] == 0
    # druhý zápis ve stejném týdnu nevytvoří duplicity
    again, _ = store.record_candidates(main, synthetic_cache, result, run_id, now=now + timedelta(hours=1))
    assert again == []
    with pytest.raises(sqlite3.IntegrityError, match="§53"):
        with main:
            main.execute("DELETE FROM discovery_runs")
    payload = json.loads(main.execute("SELECT result_json FROM discovery_runs").fetchone()[0])
    assert "_models" not in payload and payload["data_do"] == "2026-10-02"
