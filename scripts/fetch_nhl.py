"""Hämtar NHL-matcher kommande vecka och svenskarna i varje lag.

Källa: NHL:s publika webb-API (api-web.nhle.com). Det är inofficiellt och
saknar publicerade villkor; vi använder bara fakta (tider, lag, spelare).
Skriver data/generated/nhl.json. Misslyckas en del behålls den gamla.
"""
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "generated" / "nhl.json"
API = "https://api-web.nhle.com/v1"
USER_AGENT = "sportpatv/0.1 (https://github.com/luca5and/sportpatv)"


def get(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def text(value):
    """NHL-API:t ger namn som {"default": "..."}."""
    return value.get("default") if isinstance(value, dict) else value


def team(t):
    name = " ".join(x for x in (text(t.get("placeName")), text(t.get("commonName"))) if x)
    return {"abbrev": t["abbrev"], "name": name or t["abbrev"], "short": text(t.get("commonName")) or t["abbrev"]}


def parse_schedule(data):
    games = []
    for day in data.get("gameWeek", []):
        for g in day.get("games", []):
            games.append({
                "id": str(g["id"]),
                "start": g["startTimeUTC"],
                "state": g.get("gameState"),
                "type": g.get("gameType"),
                "home": team(g["homeTeam"]),
                "away": team(g["awayTeam"]),
            })
    return games


def parse_roster(data):
    """Spelare födda i Sverige (birthCountry SWE)."""
    players = []
    for group in ("forwards", "defensemen", "goalies"):
        for p in data.get(group, []):
            if p.get("birthCountry") == "SWE":
                players.append(f'{text(p.get("firstName"))} {text(p.get("lastName"))}')
    return sorted(players)


def main():
    try:
        old = json.loads(OUT.read_text())
    except (FileNotFoundError, ValueError):
        old = {}

    try:
        games = parse_schedule(get(f"/schedule/{dt.date.today().isoformat()}"))
    except Exception as exc:
        print(f"NHL-schema misslyckades, behåller gammalt: {exc}", file=sys.stderr)
        games = old.get("games", [])

    swedes = dict(old.get("swedes", {}))
    teams = sorted({g[side]["abbrev"] for g in games for side in ("home", "away")})
    failed = 0
    for abbrev in teams:
        try:
            swedes[abbrev] = parse_roster(get(f"/roster/{abbrev}/current"))
        except Exception as exc:
            failed += 1
            print(f"NHL-trupp {abbrev} misslyckades: {exc}", file=sys.stderr)
        time.sleep(0.3)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"games": games, "swedes": swedes}, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    total = sum(len(v) for k, v in swedes.items() if k in teams)
    print(f"{len(games)} NHL-matcher, {len(teams) - failed}/{len(teams)} trupper, {total} svenskar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
