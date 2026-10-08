"""Hämtar kommande fotbollsmatcher från football-data.org (gratisnivån).

Kräver miljövariabeln FOOTBALL_DATA_TOKEN. Skriver data/generated/matches.json.
"""
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "generated" / "matches.json"
DAYS_AHEAD = 7  # gratisnivån tillåter högst 10 dagar per anrop


def main():
    token = os.environ.get("FOOTBALL_DATA_TOKEN")
    if not token:
        print("FOOTBALL_DATA_TOKEN saknas, hoppar över matcher", file=sys.stderr)
        return 0

    today = dt.date.today()
    url = (
        "https://api.football-data.org/v4/matches"
        f"?dateFrom={today.isoformat()}&dateTo={(today + dt.timedelta(days=DAYS_AHEAD)).isoformat()}"
    )
    req = urllib.request.Request(url, headers={"X-Auth-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
    except Exception as exc:
        print(f"football-data.org misslyckades, behåller gammal fil: {exc}", file=sys.stderr)
        return 0

    matches = [
        {
            "id": str(m["id"]),
            "start": m["utcDate"],
            "status": m["status"],
            "competition": {"code": m["competition"]["code"], "name": m["competition"]["name"]},
            "home": {k: m["homeTeam"].get(k) for k in ("name", "shortName", "tla")},
            "away": {k: m["awayTeam"].get(k) for k in ("name", "shortName", "tla")},
        }
        for m in data.get("matches", [])
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"fetched": today.isoformat(), "matches": matches}, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(matches)} matcher sparade")
    return 0


if __name__ == "__main__":
    sys.exit(main())
