"""Hämtar aktuella trupper med nationalitet från football-data.org.

En fråga per turnering (gratisnivån: högst 10 frågor/minut, därav pausen).
Kräver FOOTBALL_DATA_TOKEN. Skriver data/generated/squads.json; lag som
inte gick att hämta behåller sin gamla trupp.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "generated" / "squads.json"
COMPETITIONS = ["PL", "ELC", "PD", "SA", "BL1", "FL1", "DED", "PPL", "CL", "BSA"]
PAUSE = 7  # sekunder mellan frågor


def main():
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        print("FOOTBALL_DATA_TOKEN saknas, hoppar över trupper", file=sys.stderr)
        return 0

    try:
        teams = json.loads(OUT.read_text())["teams"]
    except (FileNotFoundError, KeyError, ValueError):
        teams = {}

    ok = 0
    for i, code in enumerate(COMPETITIONS):
        if i:
            time.sleep(PAUSE)
        req = urllib.request.Request(
            f"https://api.football-data.org/v4/competitions/{code}/teams",
            headers={"X-Auth-Token": token},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp)
        except Exception as exc:
            print(f"{code}: misslyckades ({exc})", file=sys.stderr)
            continue
        ok += 1
        for t in data.get("teams", []):
            squad = [{"name": p["name"], "nationality": p.get("nationality")} for p in t.get("squad") or []]
            if squad:
                teams[str(t["id"])] = {"name": t["name"], "players": squad}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"teams": teams}, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    swedes = sum(1 for t in teams.values() for p in t["players"] if p["nationality"] == "Sweden")
    print(f"{ok}/{len(COMPETITIONS)} turneringar, {len(teams)} lag med trupp, {swedes} svenskar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
