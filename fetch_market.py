#!/usr/bin/env python3
"""Deterministic Polymarket-odds fetch helper for the WC2026 simulator.

Fetches the live "2026 FIFA World Cup Winner" outright prices from Polymarket's
public Gamma API (free, no key) and writes market_odds.json. The prices of the
still-alive teams are (approximately) de-vigged champion probabilities: the
market is negative-risk, so they sum to ~1 by construction.

Like the other fetchers it never invents numbers: it reads the live source,
maps Polymarket team names to our canonical keys, validates, and writes the
file atomically. If it cannot fetch, parse, or validate, it raises rather than
fabricating — the daily workflow treats that as "no market data today" and
simulate.py falls back to pure Elo.

CLI:
    python fetch_market.py          fetch live, write market_odds.json, print prices
    python fetch_market.py --check  validate the current market_odds.json

Pure stdlib only (json, urllib, datetime, argparse, os).
"""

import argparse
import datetime
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MARKET_FILE = os.path.join(HERE, "market_odds.json")
ELO_FILE = os.path.join(HERE, "elo_ratings.json")

EVENT_SLUG = "world-cup-winner"   # Polymarket "2026 FIFA World Cup Winner" event
API_URL = "https://gamma-api.polymarket.com/events?slug=" + EVENT_SLUG

# Ignore resolved/eliminated outcomes: their Yes price is 0 (or dust).
MIN_PRICE = 0.001

# Polymarket team names that differ from our canonical 48 keys. Anything not
# in this map must already BE a canonical key, otherwise we refuse the data.
ALIASES = {
    "United States": "USA",
    "Korea Republic": "South Korea",
    "Czechia": "Czech Republic",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    "Bosnia": "Bosnia & Herzegovina",
    "DR Congo": "D.R. Congo",
    "Congo DR": "D.R. Congo",
    "Côte d'Ivoire": "Ivory Coast",
    "Cabo Verde": "Cape Verde",
    "Curaçao": "Curacao",
}


def canonical_teams():
    """The 48 canonical team keys (source of truth: elo_ratings.json)."""
    with open(ELO_FILE, encoding="utf-8") as f:
        return set(json.load(f)["ratings"])


def _team_of(market):
    """Polymarket's team name for one Yes/No sub-market of the outright event."""
    name = market.get("groupItemTitle") or ""
    if not name:
        # fallback: parse the question, e.g. "Will Spain win the 2026 FIFA World Cup?"
        q = market.get("question", "")
        if q.startswith("Will ") and " win the " in q:
            name = q[5:q.index(" win the ")]
    return name.strip()


def fetch_live(url=API_URL, timeout=30):
    """Fetch + parse current outright prices. Returns dict{ourname: prob}.

    Keeps only outcomes priced above MIN_PRICE (i.e. teams still alive).
    Raises RuntimeError on fetch failure, unknown team names carrying real
    price, or an implausible probability sum — never returns partial junk.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (wc2026-simulator daily refresh)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            events = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # network / HTTP / JSON failures
        raise RuntimeError("fetch_live: could not fetch %s (%s)" % (url, exc)) from exc

    if not events:
        raise RuntimeError("fetch_live: event %r not found on Polymarket" % EVENT_SLUG)

    known = canonical_teams()
    prices, unknown = {}, []
    for m in events[0].get("markets", []):
        try:
            yes = float(json.loads(m.get("outcomePrices", "[]"))[0])
        except (ValueError, IndexError, TypeError):
            continue
        if yes < MIN_PRICE:
            continue
        name = _team_of(m)
        team = ALIASES.get(name, name)
        if team in known:
            prices[team] = yes
        else:
            unknown.append("%s (%.3f)" % (name or "<unnamed>", yes))

    if unknown:
        raise RuntimeError(
            "fetch_live: unmapped team name(s) with live prices: %s. "
            "Extend ALIASES; refusing partial data." % ", ".join(unknown)
        )
    if not prices:
        raise RuntimeError("fetch_live: parsed zero live prices; source format "
                           "may have changed. Not fabricating values.")
    total = sum(prices.values())
    if not 0.90 <= total <= 1.05:
        raise RuntimeError(
            "fetch_live: live prices sum to %.3f (expected ~1.0) across %d "
            "teams — market in a weird state, refusing." % (total, len(prices))
        )
    return prices


def apply_prices(prices, fetched_at=None):
    """Validate and write market_odds.json atomically. Returns what was written."""
    known = canonical_teams()
    bad = [t for t in prices if t not in known]
    if bad:
        raise ValueError("apply_prices: non-canonical team(s): %s" % ", ".join(bad))
    for t, p in prices.items():
        if not isinstance(p, (int, float)) or not 0.0 < p <= 1.0:
            raise ValueError("apply_prices: bad probability %s=%r" % (t, p))
    if fetched_at is None:
        fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    data = {
        "source": "polymarket",
        "event": EVENT_SLUG,
        "fetched_at": fetched_at,
        "prices": {t: round(float(p), 5) for t, p in sorted(prices.items())},
    }
    tmp = MARKET_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, MARKET_FILE)  # atomic on same filesystem
    return data


def check_file():
    """Validate the current market_odds.json. Returns the parsed doc or raises."""
    with open(MARKET_FILE, encoding="utf-8") as f:
        data = json.load(f)
    prices = data.get("prices")
    if not isinstance(prices, dict) or not prices:
        raise ValueError("market_odds.json: missing or empty 'prices'")
    known = canonical_teams()
    bad = [t for t in prices if t not in known]
    if bad:
        raise ValueError("market_odds.json: non-canonical team(s): %s" % ", ".join(bad))
    for t, p in prices.items():
        if not isinstance(p, (int, float)) or not 0.0 < p <= 1.0:
            raise ValueError("market_odds.json: bad probability %s=%r" % (t, p))
    total = sum(prices.values())
    if not 0.90 <= total <= 1.05:
        raise ValueError("market_odds.json: prices sum to %.3f, expected ~1.0" % total)
    datetime.datetime.fromisoformat(data["fetched_at"])  # raises if malformed
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="only validate the current market_odds.json")
    args = parser.parse_args(argv)

    if args.check:
        data = check_file()
        print("OK: market_odds.json has %d live prices (sum %.3f, fetched %s)."
              % (len(data["prices"]), sum(data["prices"].values()), data["fetched_at"]))
        return 0

    prices = fetch_live()
    data = apply_prices(prices)
    print("Wrote market_odds.json (%d live teams, fetched %s):"
          % (len(prices), data["fetched_at"]))
    for t, p in sorted(prices.items(), key=lambda kv: -kv[1]):
        print("  %-22s %6.2f%%" % (t, 100 * p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
