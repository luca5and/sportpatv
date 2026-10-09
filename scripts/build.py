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


def tv_status(match_id, competition_code, rights, confirmations, round_count=0):
    """Status per match:
    confirmed = matchen är kontrollerad, eller hela turneringen sänds hos en tjänst
    likely    = slutsats från omgången (Premier League: omgångens Prime-match är en annan)
    none      = turneringen visar utvalda matcher och omgångens urval är känt utan den här
    unknown   = vi vet inte. Vi gissar aldrig.

    round_count = antal bekräftade matcher i samma omgång hos omgångsundantaget
    (split) eller hos tjänsten med utvalda matcher (selected)."""
    conf = confirmations.get(match_id)
    if conf:
        if not conf.get("service"):
            return {"status": "none", "service": None, "channel": None, "source": conf.get("source"),
                    "note": "Sänds inte i Sverige"}
        return {"status": "confirmed", "service": conf.get("service"), "channel": conf.get("channel"),
                "source": conf.get("source"), "note": None}
    r = rights.get(competition_code) or {}
    services = r.get("services") or []
    coverage = r.get("coverage")
    if coverage == "all" and len(services) == 1:
        return {"status": "confirmed", "service": services[0], "channel": None,
                "source": r.get("source"), "note": "Alla matcher i turneringen sänds här"}
    if coverage == "split" and r.get("default") and round_count >= 1:
        return {"status": "likely", "service": r["default"], "channel": None, "source": r.get("source"),
                "note": None}
    if coverage == "selected" and r.get("per_round") and round_count >= r["per_round"]:
        return {"status": "none", "service": None, "channel": None, "source": None,
                "note": f'Inte bland omgångens {r["per_round"]} matcher på {services[0]}'}
    if coverage == "selected" and services and r.get("per_round"):
        note = f'{services[0]} visar {r["per_round"]} utvalda matcher per omgång'
    else:
        note = ("Troligen " + " eller ".join(services)) if services else None
    return {"status": "unknown", "service": None, "channel": None, "source": None, "note": note}


def round_counts(matches, rights, confirmations):
    """{(turnering, omgång): antal bekräftade omgångsmatcher} för delade ligor
    (räknar undantagstjänsten) och ligor med utvalda matcher (räknar tjänsten)."""
    counts = {}
    for m in matches:
        code = m["competition"]["code"]
        r = rights.get(code) or {}
        conf = confirmations.get(m["id"])
        if not conf or not m.get("matchday"):
            continue
        if r.get("coverage") == "split":
            counted = conf.get("service") == r.get("per_round_exception")
        elif r.get("coverage") == "selected":
            counted = conf.get("service") in (r.get("services") or [])
        else:
            counted = False
        if counted:
            key = (code, m["matchday"])
            counts[key] = counts.get(key, 0) + 1
    return counts


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
    counts = round_counts(matches, rights, confirmations)
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
            "competition": rights.get(m["competition"]["code"], {}).get("name") or m["competition"]["name"],
            "start": m["start"],
            "title": f'{m["home"].get("shortName") or m["home"]["name"]} – {m["away"].get("shortName") or m["away"]["name"]}',
            "swedes": swedes,
            "tv": tv_status(m["id"], m["competition"]["code"], rights, confirmations,
                            counts.get((m["competition"]["code"], m.get("matchday")), 0)),
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
