"""Tillfällig kontroll av TheSportsDB:s gratisnyckel (123).

Svarar på: finns gårdagens/helgens Premier League-matcher, och ger en spelad
match laguppställning och händelser (mål, byten)? Skriver bara till loggen.
"""
import datetime as dt
import json
import sys
import time
import urllib.request

API = "https://www.thesportsdb.com/api/v1/json/123"
LEAGUES = {"Premier League": 4328, "Serie A": 4332, "Bundesliga": 4331}


def get(path):
    time.sleep(3)  # gratisnyckeln tål inte täta anrop (429)
    req = urllib.request.Request(f"{API}/{path}", headers={"User-Agent": "patv.se"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def show(eid):
    lu = (get(f"lookuplineup.php?id={eid}") or {}).get("lineup") or []
    starters = [p for p in lu if (p.get("strSubstitute") or "").lower() == "no"]
    print(f"  lineup {eid}: {len(lu)} spelare, startande {len(starters)}; nycklar: {sorted(lu[0].keys()) if lu else '-'}")
    if lu:
        print(f"  exempel: {[(p.get('strPlayer'), p.get('strPosition'), p.get('strSubstitute')) for p in lu[:3]]}")
    tl = (get(f"lookuptimeline.php?id={eid}") or {}).get("timeline") or []
    print(f"  timeline {eid}: {len(tl)} händelser, typer: {sorted({t.get('strTimeline') for t in tl})}")
    print(f"  händelser: {[(t.get('strTimeline'), t.get('strTimelineDetail'), t.get('strPlayer'), t.get('intTime')) for t in tl[:8]]}")
    if tl:
        print(f"  nycklar: {sorted(tl[0].keys())}")


def main():
    try:
        show("2508414")  # Bayern – Köln 1–1, 20 nov (hittad i förra körningen)
        return 0
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
