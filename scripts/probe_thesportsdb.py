"""Tillfällig kontroll av TheSportsDB:s gratisnyckel (123).

Svarar på: finns gårdagens/helgens Premier League-matcher, och ger en spelad
match laguppställning och händelser (mål, byten)? Skriver bara till loggen.
"""
import datetime as dt
import json
import sys
import urllib.request

API = "https://www.thesportsdb.com/api/v1/json/123"
LEAGUES = {"Premier League": 4328, "Serie A": 4332, "Bundesliga": 4331}


def get(path):
    req = urllib.request.Request(f"{API}/{path}", headers={"User-Agent": "patv.se"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main():
    try:
        today = dt.date.today()
        for league, lid in LEAGUES.items():
            event = None
            for back in range(0, 4):
                day = (today - dt.timedelta(days=back)).isoformat()
                ev = (get(f"eventsday.php?d={day}&l={lid}") or {}).get("events") or []
                done = [e for e in ev if e.get("intHomeScore") not in (None, "")]
                print(f"TheSportsDB {league} {day}: {len(ev)} matcher, {len(done)} med resultat")
                if done:
                    event = done[0]
                    break
            if not event:
                continue
            eid = event["idEvent"]
            print(f"  match {eid}: {event.get('strEvent')} {event.get('intHomeScore')}–{event.get('intAwayScore')}")
            lu = (get(f"lookuplineup.php?id={eid}") or {}).get("lineup") or []
            starters = [p for p in lu if (p.get("strSubstitute") or "").lower() == "no"]
            print(f"  lineup: {len(lu)} spelare, startande {len(starters)}; "
                  f"nycklar: {sorted(lu[0].keys())[:12] if lu else '-'}")
            tl = (get(f"lookuptimeline.php?id={eid}") or {}).get("timeline") or []
            kinds = sorted({t.get("strTimeline") for t in tl})
            print(f"  timeline: {len(tl)} händelser, typer: {kinds}")
            goals = [f'{t.get("strPlayer")} {t.get("intTime")}\'' for t in tl if t.get("strTimeline") == "Goal"]
            print(f"  mål: {goals[:6]}")
            break
    except Exception as exc:
        print(f"TheSportsDB-kontroll misslyckades: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
