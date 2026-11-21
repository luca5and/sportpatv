"""Tillfällig kontroll av API-Football (api-sports.io), gratisplanen.

Svarar på: ingår innevarande säsong, och ger en spelad match laguppställningar,
händelser (mål/byten) och minuter per spelare? Skriver bara till loggen och
sparar inget. Nyckeln läses från miljövariabeln API_FOOTBALL_KEY och skrivs
aldrig ut. Använder högst 6 anrop.
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://v3.football.api-sports.io"
PREMIER_LEAGUE = 39


def get(path, **params):
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, headers={"x-apisports-key": os.environ["API_FOOTBALL_KEY"],
                                               "User-Agent": "patv.se"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main():
    if not os.environ.get("API_FOOTBALL_KEY"):
        print("API-Football: ingen nyckel, hoppar över")
        return 0
    try:
        st = get("/status").get("response") or {}
        sub = st.get("subscription") or {}
        req = st.get("requests") or {}
        print(f"API-Football: plan={sub.get('plan')} aktiv={sub.get('active')} "
              f"anrop idag={req.get('current')}/{req.get('limit_day')}")

        today = dt.date.today()
        season = today.year if today.month >= 7 else today.year - 1
        fixture = None
        for back in range(1, 4):
            day = (today - dt.timedelta(days=back)).isoformat()
            d = get("/fixtures", league=PREMIER_LEAGUE, season=season, date=day)
            print(f"  fixtures {day} säsong {season}: {d.get('results')} st, fel: {d.get('errors') or 'inga'}")
            done = [f for f in d.get("response", []) if (f.get("fixture") or {}).get("status", {}).get("short") == "FT"]
            if done:
                fixture = done[0]
                break
            if d.get("errors"):
                break
        if not fixture:
            print("  ingen spelad match hittad – säsongen ingår troligen inte i gratisplanen")
            return 0
        fid = fixture["fixture"]["id"]
        teams = fixture.get("teams") or {}
        print(f"  match {fid}: {teams.get('home', {}).get('name')} – {teams.get('away', {}).get('name')}")

        lu = get("/fixtures/lineups", fixture=fid)
        print(f"  lineups: {lu.get('results')} lag, startelva hemma: "
              f"{len((lu.get('response') or [{}])[0].get('startXI') or [])}, fel: {lu.get('errors') or 'inga'}")
        ev = get("/fixtures/events", fixture=fid)
        kinds = sorted({e.get("type") for e in ev.get("response", [])})
        print(f"  events: {ev.get('results')} st, typer: {kinds}, fel: {ev.get('errors') or 'inga'}")
        pl = get("/fixtures/players", fixture=fid)
        players = [p for t in pl.get("response", []) for p in t.get("players", [])]
        sample = (players[0]["statistics"][0] if players and players[0].get("statistics") else {})
        print(f"  players: {len(players)} spelare, fel: {pl.get('errors') or 'inga'}; "
              f"exempel-nycklar: games={sorted((sample.get('games') or {}).keys())}, "
              f"goals={sorted((sample.get('goals') or {}).keys())}")
    except Exception as exc:
        print(f"API-Football-kontroll misslyckades: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
