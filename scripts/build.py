"""Slår ihop matcher, svenska spelare och TV-rättigheter till sidans data.

Läser data/*.json och data/generated/*.json, skriver docs/data/swedes-on-tv.json.
"""
import datetime as dt
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs" / "data" / "swedes-on-tv.json"

# Ord som skiljer sig mellan källorna men inte säger något om vilket lag det är.
NOISE = {
    "fc", "afc", "cf", "sc", "ac", "as", "ss", "ssc", "sv", "fk", "if", "bk", "sk",
    "club", "de", "calcio", "football", "futbol", "fútbol", "1", "cd", "ud", "rc", "ca",
    "the", "and", "hove", "albion",
}


def normalize(name):
    """'FC Bayern München' -> 'bayern munchen', 'Arsenal F.C.' -> 'arsenal'."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace(".", "")  # 'f.c.' -> 'fc'
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(t for t in s.split() if t not in NOISE)


def load(path, default=None):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def team_keys(team, aliases):
    keys = {normalize(team.get("name")), normalize(team.get("shortName"))}
    keys.update(normalize(a) for a in aliases.get(team.get("name"), []))
    keys.discard("")
    return keys


def build_club_index(players, manual):
    """normaliserat klubbnamn -> lista av spelare."""
    removed = set(manual.get("remove", []))
    index = {}
    for p in players:
        if p["name"] in removed:
            continue
        for n in {normalize(c) for c in p["club_names"]}:
            if n:
                index.setdefault(n, []).append(p)
    return index


def person_key(name):
    s = unicodedata.normalize("NFKD", name or "")
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).lower().split())


def swedes_in(team, index, manual, aliases, squads=None):
    """Finns lagets aktuella trupp (football-data.org) används den: spelare med
    svensk nationalitet, plus svenskar enligt Wikidata som faktiskt står i
    truppen (fångar dubbla medborgarskap). Annars Wikidata-matchning på namn."""
    label = team.get("shortName") or team.get("name")
    removed = set(manual.get("remove", []))
    found = {}
    squad = (squads or {}).get(str(team.get("id")), {}).get("players") or []
    wikidata = {p["name"] for key in team_keys(team, aliases) for p in index.get(key, [])}
    if squad:
        wikidata_keys = {person_key(n) for n in wikidata}
        for p in squad:
            if p.get("nationality") == "Sweden" or person_key(p["name"]) in wikidata_keys:
                found[p["name"]] = {"name": p["name"], "team": label}
    else:
        for name in wikidata:
            found[name] = {"name": name, "team": label}
    for extra in manual.get("add", []):
        if extra.get("team") in (team.get("name"), team.get("shortName")):
            found[extra["name"]] = {"name": extra["name"], "team": label}
    return sorted((v for k, v in found.items() if k not in removed), key=lambda s: s["name"])


def tv_status(match_id, competition_code, rights, confirmations):
    """confirmed = kontrollerad hos kanalen, likely = ligan sänds i sin helhet
    hos en tjänst, unknown = vi vet inte. Vi gissar aldrig mer än så."""
    conf = confirmations.get(match_id)
    if conf:
        return {"status": "confirmed", "service": conf.get("service"), "channel": conf.get("channel"),
                "source": conf.get("source"), "note": None}
    r = rights.get(competition_code)
    if r and r.get("coverage") == "all" and len(r.get("services", [])) == 1:
        return {"status": "likely", "service": r["services"][0], "channel": None,
                "source": r.get("source"), "note": None}
    services = (r or {}).get("services") or []
    note = ("Troligen " + " eller ".join(services)) if services else None
    return {"status": "unknown", "service": None, "channel": None, "source": None, "note": note}


def build(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    matches = (load(DATA / "generated" / "matches.json", {}) or {}).get("matches", [])
    players = (load(DATA / "generated" / "swedes.json", {}) or {}).get("players", [])
    rights = load(DATA / "broadcasters.json", {}).get("competitions", {})
    confirmations = load(DATA / "confirmations.json", {}).get("matches", {})
    manual = load(DATA / "players_manual.json", {})
    aliases = {k: v for k, v in manual.get("club_aliases", {}).items() if not k.startswith("_")}
    manual_events = load(DATA / "manual_events.json", {}).get("events", [])
    squads = (load(DATA / "generated" / "squads.json", {}) or {}).get("teams", {})

    index = build_club_index(players, manual)
    events = []
    for m in matches:
        if m.get("status") in ("FINISHED", "CANCELLED", "POSTPONED", "AWARDED"):
            continue
        swedes = (swedes_in(m["home"], index, manual, aliases, squads)
                  + swedes_in(m["away"], index, manual, aliases, squads))
        if not swedes:
            continue
        events.append({
            "id": m["id"],
            "sport": "Fotboll",
            "competition": m["competition"]["name"],
            "start": m["start"],
            "title": f'{m["home"].get("shortName") or m["home"]["name"]} – {m["away"].get("shortName") or m["away"]["name"]}',
            "swedes": swedes,
            "tv": tv_status(m["id"], m["competition"]["code"], rights, confirmations),
        })

    for e in manual_events:
        e = dict(e)
        conf = confirmations.get(e["id"])
        if conf:
            e["tv"] = tv_status(e["id"], None, {}, confirmations)
        e.setdefault("tv", {"status": "unknown", "service": None, "channel": None, "source": None, "note": None})
        events.append(e)

    cutoff = now - dt.timedelta(hours=3)  # visa pågående matcher en stund till
    events = [e for e in events if dt.datetime.fromisoformat(e["start"].replace("Z", "+00:00")) >= cutoff]
    events.sort(key=lambda e: (e["start"], e["title"]))
    return {"generated": now.isoformat(timespec="minutes"), "events": events}


def main():
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(f'{len(result["events"])} händelser med svenskar')


if __name__ == "__main__":
    main()
