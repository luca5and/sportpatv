"""Skriver de statiska sidorna som Google kan läsa direkt.

Läser docs/data/swedes-on-tv.json (från build.py) och skriver:
- docs/index.html: startsidan med dagens matcher redan i HTML:en
- docs/spelare/<namn>/: en sida per svensk spelare
- docs/lag/<namn>/: en sida per lag med svenskar
- docs/sitemap.xml och docs/robots.txt
Sidorna finns kvar 60 dagar efter att spelaren senast hade en match, så att
adresserna inte försvinner mellan veckorna.
"""
import datetime as dt
import html
import json
import re
import shutil
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA_FILE = DOCS / "data" / "swedes-on-tv.json"
REGISTRY_FILE = ROOT / "data" / "generated" / "pages.json"
TEMPLATE = ROOT / "templates" / "index.html"
SITE = json.loads((ROOT / "data" / "site.json").read_text())

TZ = ZoneInfo("Europe/Stockholm")
NIGHT_END = 6       # matcher före 06:00 hör till kvällen innan
KEEP_DAYS = 60      # så länge en sida finns kvar utan matcher
WEEKDAYS = ["mån", "tis", "ons", "tors", "fre", "lör", "sön"]
MONTHS = ["jan", "feb", "mars", "apr", "maj", "juni", "juli", "aug", "sep", "okt", "nov", "dec"]
TV_TEXT = {"none": "Sänds inte i Sverige", "unknown": "Ej bekräftat"}

esc = html.escape


def local(iso):
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)


def event_day(iso):
    return (local(iso) - dt.timedelta(hours=NIGHT_END)).date()


def fmt_day(d):
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def fmt_when(iso):
    t = local(iso)
    night = " (natt)" if t.hour < NIGHT_END else ""
    return f"{fmt_day(event_day(iso))} kl {t:%H:%M}{night}"


def slugify(text):
    s = unicodedata.normalize("NFKD", text.replace("ø", "o").replace("æ", "ae").replace("ß", "ss"))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def tv_text(tv):
    if tv["status"] in ("confirmed", "likely"):
        label = f'{tv["service"]} · {tv["channel"]}' if tv.get("channel") else tv["service"]
        return label + ("" if tv["status"] == "confirmed" else " (bör sändas)")
    return TV_TEXT.get(tv["status"], "Ej bekräftat")


def teams_of(event):
    return event["title"].split(" – ", 1)


# --- adresser -------------------------------------------------------------

def assign_pages(events, registry, today):
    """Ger varje spelare och lag en stabil adress och sparar dem i registret."""
    players, teams = registry.setdefault("players", {}), registry.setdefault("teams", {})

    def claim(table, key, base, extra):
        for slug, entry in table.items():
            if entry["key"] == key:
                return slug
        slug = base
        if slug in table:
            slug = f"{base}-{slugify(extra)}"
        n = 2
        while slug in table:
            slug, n = f"{base}-{n}", n + 1
        table[slug] = {"key": key}
        return slug

    for e in events:
        e["teams"] = []
        for name in teams_of(e):
            slug = claim(teams, f'{e["sport"]}|{name}', slugify(name), e["sport"])
            teams[slug].update({"name": name, "sport": e["sport"], "last_seen": today})
            e["teams"].append({"name": name, "page": f"lag/{slug}/"})
        for s in e["swedes"]:
            key = s.get("url") or f'{s["name"]}|{s["team"]}'
            slug = claim(players, key, slugify(s["name"]), s["team"])
            players[slug].update({"name": s["name"], "team": s["team"], "sport": e["sport"],
                                  "wiki": s.get("url"), "last_seen": today})
            s["page"] = f"spelare/{slug}/"

    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=KEEP_DAYS)).isoformat()
    for kind, table in (("spelare", players), ("lag", teams)):
        for slug in [s for s, e in table.items() if e.get("last_seen", today) < cutoff]:
            del table[slug]
            shutil.rmtree(DOCS / kind / slug, ignore_errors=True)


# --- HTML -----------------------------------------------------------------

def event_html(e, prefix="", show_day=False):
    tv = e["tv"]
    cls = tv["status"] if tv["status"] in ("confirmed", "likely", "none") else "unknown"
    label = TV_TEXT.get(tv["status"]) or (f'{tv["service"]} · {tv["channel"]}' if tv.get("channel") else tv["service"])
    note = tv.get("note") if tv["status"] != "confirmed" and tv.get("note") != "Sänds inte i Sverige" else None
    swedes = "".join(
        f'<span class="swede"><a href="{esc(prefix + s["page"])}">{esc(s["name"])}</a> <small>{esc(s["team"])}</small></span>'
        for s in e["swedes"])
    t = local(e["start"])
    night = '<small class="night">natt</small>' if t.hour < NIGHT_END else ""
    # På spelar- och lagsidor syns flera dagar i samma lista, så dagen visas ovanför tiden.
    day = f'<small class="day">{esc(fmt_day(event_day(e["start"])))}</small>' if show_day else ""
    return (
        f'<li class="event"><div class="time">{day}<time datetime="{esc(e["start"])}">{t:%H:%M}</time>{night}</div>'
        f'<div class="body"><div class="meta">{esc(e["sport"])} · {esc(e["competition"])}</div>'
        f'<div class="title">{esc(e["title"])}</div><div class="swedes">{swedes}</div>'
        f'<div class="tv"><span class="badge {cls}">{esc(label)}</span>{esc(note) if note else ""}</div></div></li>'
    )


def sports_event_ld(e):
    return {
        "@type": "SportsEvent",
        "name": f'{e["title"]} ({e["competition"]})',
        "startDate": e["start"],
        "sport": e["sport"],
        "eventStatus": "https://schema.org/EventScheduled",
        "competitor": [{"@type": "SportsTeam", "name": n} for n in teams_of(e)],
        "description": f'Svenskar: {", ".join(s["name"] for s in e["swedes"])}. TV i Sverige: {tv_text(e["tv"])}.',
    }


def json_ld(data):
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def page_html(*, title, description, path, h1, lede, events, links, updated):
    prefix = "../../"
    items = "".join(event_html(e, prefix, show_day=True) for e in events) or '<li class="empty-row">Inga matcher de närmaste sju dagarna.</li>'
    ld = {"@context": "https://schema.org", "@type": "ItemList",
          "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": sports_event_ld(e)}
                              for i, e in enumerate(events)]}
    url = f'{SITE["base_url"]}/{path}'
    return f"""<!doctype html>
<html lang="sv">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}">
  <link rel="canonical" href="{esc(url)}">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="sv_SE">
  <meta property="og:site_name" content="{esc(SITE["name"])}">
  <meta property="og:title" content="{esc(h1)}">
  <meta property="og:description" content="{esc(description)}">
  <meta property="og:url" content="{esc(url)}">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📺</text></svg>">
  <link rel="stylesheet" href="{prefix}style.css">
  <script type="application/ld+json">{json_ld(ld)}</script>
</head>
<body>
  <header class="top">
    <div class="wrap">
      <a class="logo" href="{prefix}">Sport<span>på</span>TV</a>
      <nav class="tabs" aria-label="Flikar">
        <a class="tab" href="{prefix}">🇸🇪 Svenskar på TV</a>
        <a class="coffee" href="{esc(SITE["coffee_url"])}" rel="noopener" target="_blank">☕ Bjud på kaffe</a>
      </nav>
    </div>
  </header>
  <main class="wrap">
    <nav class="crumbs"><a href="{prefix}">Alla svenskar på TV</a></nav>
    <h1 class="intro">{esc(h1)}</h1>
    <p class="lede">{lede}</p>
    <ol class="list">{items}</ol>
    <p class="links">{links}</p>
  </main>
  <footer class="wrap foot">
    <p>Ingen reklam, inga cookies. Tider i svensk tid. {esc(updated)}</p>
    <p><a class="coffee" href="{esc(SITE["coffee_url"])}" rel="noopener" target="_blank">☕ Bjud på kaffe</a></p>
  </footer>
  <script src="{prefix}usage.js" defer></script>
</body>
</html>
"""


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def render_player(slug, entry, events, updated):
    name, team = entry["name"], entry["team"]
    mine = [e for e in events if any(s.get("page") == f"spelare/{slug}/" for s in e["swedes"])]
    if mine:
        e = mine[0]
        lede = (f"{esc(name)} ({esc(team)}) spelar nästa gång <b>{esc(fmt_when(e['start']))}</b>: "
                f"{esc(e['title'])} i {esc(e['competition'])}. TV i Sverige: <b>{esc(tv_text(e['tv']))}</b>.")
        description = f"{name} spelar {fmt_when(e['start'])}: {e['title']}. TV i Sverige: {tv_text(e['tv'])}."
    else:
        lede = f"{esc(name)} ({esc(team)}) har ingen match på TV de närmaste sju dagarna."
        description = f"Var du ser {name} ({team}) på TV i Sverige. Inga matcher de närmaste sju dagarna."
    team_slug = next((t["page"] for e in mine for t in e["teams"] if team in t["name"]), None)
    links = []
    if entry.get("wiki"):
        links.append(f'<a href="{esc(entry["wiki"])}" rel="noopener" target="_blank">Om {esc(name)} på Wikipedia</a>')
    if team_slug:
        links.append(f'<a href="../../{esc(team_slug)}">{esc(team)} på TV</a>')
    write(DOCS / "spelare" / slug / "index.html", page_html(
        title=f"{name} på TV – nästa match och kanal | {SITE['name']}",
        description=description, path=f"spelare/{slug}/", h1=f"{name} på TV",
        lede=lede, events=mine, links=" · ".join(links), updated=updated))


def render_team(slug, entry, events, updated):
    name = entry["name"]
    mine = [e for e in events if any(t["page"] == f"lag/{slug}/" for t in e["teams"])]
    swedes = sorted({s["name"] for e in mine for s in e["swedes"] if s["team"] in name or name in s["team"]})
    if mine:
        e = mine[0]
        lede = (f"Nästa match med svenskar: <b>{esc(e['title'])}</b>, {esc(fmt_when(e['start']))}. "
                f"TV i Sverige: <b>{esc(tv_text(e['tv']))}</b>.")
        description = f"{name} på TV: {e['title']} {fmt_when(e['start'])}, {tv_text(e['tv'])}."
    else:
        lede = f"{esc(name)} har ingen match med svenskar på TV de närmaste sju dagarna."
        description = f"Var du ser {name} på TV i Sverige."
    if swedes:
        lede += " Svenskar i laget: " + esc(", ".join(swedes)) + "."
    write(DOCS / "lag" / slug / "index.html", page_html(
        title=f"{name} på TV – matcher och kanal | {SITE['name']}",
        description=description, path=f"lag/{slug}/", h1=f"{name} på TV",
        lede=lede, events=mine, links="", updated=updated))


def render_index(events, registry, updated):
    days = sorted({event_day(e["start"]) for e in events})
    first = [e for e in events if days and event_day(e["start"]) == days[0]]
    names = sorted({(s["name"], s["page"]) for e in events for s in e["swedes"]})
    links = ", ".join(f'<a href="{esc(p)}">{esc(n)}</a>' for n, p in names) or "inga just nu"
    seen = list(dict.fromkeys(s["name"] for e in events[:40] for s in e["swedes"]))[:3]
    description = ("Var du ser svenskarna i fotboll och NHL på TV idag"
                   + (f" – {', '.join(seen)} och fler" if seen else "") + ". Kanal och tid, utan reklam.")
    ld = {"@context": "https://schema.org", "@type": "ItemList",
          "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": sports_event_ld(e)}
                              for i, e in enumerate(events[:50])]}
    page = TEMPLATE.read_text()
    for key, value in {
        "{{DESCRIPTION}}": esc(description),
        "{{BASE_URL}}": esc(SITE["base_url"]),
        "{{COFFEE_URL}}": esc(SITE["coffee_url"]),
        "{{JSONLD}}": json_ld(ld),
        "{{LIST}}": "".join(event_html(e) for e in first),
        "{{PLAYER_LINKS}}": links,
        "{{UPDATED}}": esc(updated),
    }.items():
        page = page.replace(key, value)
    write(DOCS / "index.html", page)


def render_sitemap(registry, today):
    base = SITE["base_url"]
    urls = [f"{base}/"] + [f"{base}/spelare/{s}/" for s in sorted(registry["players"])] \
        + [f"{base}/lag/{s}/" for s in sorted(registry["teams"])]
    body = "".join(f"  <url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in urls)
    write(DOCS / "sitemap.xml",
          f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n')
    write(DOCS / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    return len(urls)


def main(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.astimezone(TZ).date().isoformat()
    data = json.loads(DATA_FILE.read_text())
    events = data.get("events", [])
    try:
        registry = json.loads(REGISTRY_FILE.read_text())
    except (FileNotFoundError, ValueError):
        registry = {}

    assign_pages(events, registry, today)
    stamp = now.astimezone(TZ)
    updated = f"Uppdaterad {fmt_day(stamp.date())} {stamp:%H:%M}."

    for slug, entry in registry["players"].items():
        render_player(slug, entry, events, updated)
    for slug, entry in registry["teams"].items():
        render_team(slug, entry, events, updated)
    render_index(events, registry, updated)
    count = render_sitemap(registry, today)

    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")  # nu med sidadresser
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(registry, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(f'{len(registry["players"])} spelarsidor, {len(registry["teams"])} lagsidor, {count} adresser i sitemap')


if __name__ == "__main__":
    main()
