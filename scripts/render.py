"""Skriver de statiska sidorna som Google kan läsa direkt.

Läser docs/data/swedes-on-tv.json (från build.py) och skriver:
- docs/index.html: startsidan med dagens matcher redan i HTML:en
- docs/spelare/<namn>/: en sida per svensk spelare
- docs/lag/<namn>/: en sida per lag med svenskar
- docs/liga/<namn>/: en sida per liga – vem som visar den i Sverige och veckans matcher
- docs/sitemap.xml och docs/robots.txt
Sidorna finns kvar även när spelaren inte har någon match, så att adresser som
Google redan känner till inte försvinner. lastmod i sitemap ändras bara när
sidans innehåll ändras.
"""
import datetime as dt
import hashlib
import html
import json
import re
import unicodedata
import urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA_FILE = DOCS / "data" / "swedes-on-tv.json"
REGISTRY_FILE = ROOT / "data" / "generated" / "pages.json"
CHANGED_FILE = ROOT / "data" / "generated" / "changed-urls.txt"
TEMPLATE = ROOT / "templates" / "index.html"
SITE = json.loads((ROOT / "data" / "site.json").read_text())
TEAM_NAMES = json.loads((ROOT / "data" / "team_names.json").read_text())["names"]
RIGHTS = json.loads((ROOT / "data" / "broadcasters.json").read_text()).get("competitions", {})

TZ = ZoneInfo("Europe/Stockholm")
NIGHT_END = 6       # matcher före 06:00 hör till kvällen innan
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


def wiki_name(name, url):
    """Wikipedias stavning när den bara skiljer sig i å/ä/ö och accenter.

    NHL:s data saknar svenska tecken (Adam Edstrom), men folk söker på Adam Edström."""
    if not url or "/wiki/" not in url:
        return name
    title = urllib.parse.unquote(url.rsplit("/wiki/", 1)[1]).replace("_", " ")
    title = re.sub(r"\s*\([^)]*\)$", "", title).strip()
    return title if title and slugify(title) == slugify(name) else name


def rights_sentence(competition):
    """En mening om vem som visar turneringen i Sverige, från data/broadcasters.json."""
    r = next((v for v in RIGHTS.values() if isinstance(v, dict) and v.get("name") == competition), None)
    if not r or not r.get("services"):
        return f"Vi har inte hittat någon svensk kanal som visar {competition}."
    services = r["services"]
    if r.get("coverage") == "all":
        return f"{competition} visas på {' och '.join(services)} i Sverige."
    if r.get("coverage") == "split" and r.get("per_round_exception"):
        return (f"{competition} visas på {r['default']} i Sverige, utom en match per omgång "
                f"som bara går på {r['per_round_exception']}.")
    if r.get("coverage") == "split":
        other = [x for x in services if x != r.get("default")]
        return (f"{competition} visas på {r.get('default') or services[0]} i Sverige, "
                f"men vissa matcher går bara på {' och '.join(other)}.")
    if r.get("coverage") == "selected" and r.get("per_round"):
        return f"{services[0]} visar {r['per_round']} utvalda matcher per omgång i {competition}."
    return f"{competition} visas delvis på {' och '.join(services)} i Sverige."


def league_slug(competition):
    return slugify(competition)


def league_links(competitions, prefix):
    known = {v.get("name") for v in RIGHTS.values() if isinstance(v, dict)}
    return [f'<a href="{prefix}liga/{league_slug(c)}/">{esc(c)} på TV</a>' for c in competitions if c in known]


def where_to_watch(subject, competitions, extra=""):
    """Text som alltid finns på sidan, även när det inte är någon match i veckan."""
    sentences = [rights_sentence(c) for c in competitions]
    if not sentences:
        return ""
    return (f'<section class="watch"><h2>Var kan man se {esc(subject)} på TV?</h2>'
            f'<p>{esc(extra)}{esc(" ".join(sentences))} '
            f'Tiderna här är svensk tid och kanalen kontrolleras mot flera källor. '
            f'Står det "Ej bekräftat" vet vi inte säkert än.</p></section>')


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
            add_competition(teams[slug], e["competition"])
            e["teams"].append({"name": name, "page": f"lag/{slug}/"})
        for s in e["swedes"]:
            s["name"] = wiki_name(s["name"], s.get("url"))
            key = s.get("url") or f'{s["name"]}|{s["team"]}'
            slug = claim(players, key, slugify(s["name"]), s["team"])
            players[slug].update({"name": s["name"], "team": s["team"], "sport": e["sport"],
                                  "wiki": s.get("url"), "last_seen": today})
            add_competition(players[slug], e["competition"])
            full = next((t for t in e["teams"] if s["team"] and s["team"] in t["name"]), None)
            if full:  # NHL ger bara "Predators"; spara "Nashville Predators" och lagsidan
                players[slug].update({"team_full": full["name"], "team_page": full["page"]})
            s["page"] = f"spelare/{slug}/"


def add_competition(entry, competition):
    comps = entry.setdefault("competitions", [])
    if competition not in comps:
        comps.append(competition)


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


def page_html(*, title, description, path, h1, lede, events, links, updated, watch=""):
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
  <meta property="og:image" content="{esc(SITE["base_url"])}/og.png">
  <link rel="icon" href="{prefix}favicon.ico" sizes="32x32">
  <link rel="icon" href="{prefix}icon.svg" type="image/svg+xml">
  <link rel="icon" href="{prefix}icon-192.png" type="image/png" sizes="192x192">
  <link rel="apple-touch-icon" href="{prefix}apple-touch-icon.png">
  <link rel="stylesheet" href="{prefix}{asset("style.css")}">
  <script type="application/ld+json">{json_ld(ld)}</script>
</head>
<body>
  <header class="top">
    <div class="wrap">
      <a class="logo" href="{prefix}" aria-label="Svenskar på TV – startsidan"><span class="brand"><span class="flag">🇸🇪 Svenskar</span>på<span class="tvword">TV</span></span><small>i fotboll och NHL</small></a>
      <nav class="tabs" aria-label="Länkar">
        <a class="coffee" href="{esc(SITE["coffee_url"])}" rel="noopener" target="_blank" aria-label="Bjud på kaffe">☕<span class="txt"> Bjud på kaffe</span></a>
      </nav>
    </div>
  </header>
  <main class="wrap">
    <nav class="crumbs"><a href="{prefix}">Alla svenskar på TV</a></nav>
    <h1 class="intro">{esc(h1)}</h1>
    <p class="lede">{lede}</p>
    <ol class="list">{items}</ol>
    {watch}
    <p class="links">{links}</p>
  </main>
  <footer class="wrap foot">
    <p>Ingen reklam, inga cookies. Tider i svensk tid. {esc(updated)}</p>
    <p><a class="coffee" href="{esc(SITE["coffee_url"])}" rel="noopener" target="_blank">☕ Bjud på kaffe</a></p>
  </footer>
  <script src="{prefix}{asset("usage.js")}" defer></script>
  <script defer src="/_vercel/insights/script.js"></script>
</body>
</html>
"""


def asset(name):
    """Adress med versionsnummer, så att mobiler inte blandar ny HTML med gammal CSS/JS ur cachen."""
    return f"{name}?v={hashlib.sha1((DOCS / name).read_bytes()).hexdigest()[:8]}"


PAGE_HASHES = {}   # adress -> hash av innehållet utan "Uppdaterad ..."-raden


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if path.name == "index.html":
        url_path = path.parent.relative_to(DOCS).as_posix()
        stable = re.sub(r"Uppdaterad [^<]*", "", text)
        PAGE_HASHES["" if url_path == "." else url_path + "/"] = hashlib.sha1(stable.encode()).hexdigest()


def render_player(slug, entry, events, updated):
    name, team = entry["name"], entry.get("team_full") or entry["team"]
    mine = [e for e in events if any(s.get("page") == f"spelare/{slug}/" for s in e["swedes"])]
    if mine:
        e = mine[0]
        lede = (f"{esc(name)} ({esc(team)}) spelar nästa gång <b>{esc(fmt_when(e['start']))}</b>: "
                f"{esc(e['title'])} i {esc(e['competition'])}. TV i Sverige: <b>{esc(tv_text(e['tv']))}</b>.")
        description = f"{name} spelar {fmt_when(e['start'])}: {e['title']}. TV i Sverige: {tv_text(e['tv'])}."
    else:
        lede = f"{esc(name)} ({esc(team)}) har ingen match på TV de närmaste sju dagarna."
        description = f"Var du ser {name} ({team}) på TV i Sverige. Inga matcher de närmaste sju dagarna."
    team_slug = entry.get("team_page") or next((t["page"] for e in mine for t in e["teams"] if team in t["name"]), None)
    links = []
    if entry.get("wiki"):
        links.append(f'<a href="{esc(entry["wiki"])}" rel="noopener" target="_blank">Om {esc(name)} på Wikipedia</a>')
    if team_slug:
        links.append(f'<a href="../../{esc(team_slug)}">{esc(team)} på TV</a>')
    links += league_links(entry.get("competitions", []), "../../")
    write(DOCS / "spelare" / slug / "index.html", page_html(
        title=f"{name} på TV – nästa match och kanal | {SITE['name']}",
        description=description, path=f"spelare/{slug}/", h1=f"{name} på TV",
        lede=lede, events=mine, links=" · ".join(links), updated=updated,
        watch=where_to_watch(name, entry.get("competitions", []), f"{name} spelar i {team}. ")))


def render_team(slug, entry, events, updated):
    short = entry["name"]
    name = TEAM_NAMES.get(short, short)  # "AZ" -> "AZ Alkmaar" i titel och rubrik
    if name != short and short not in name:
        name = f"{name} ({short})"  # "Paris Saint-Germain (PSG)" så att båda sökningarna träffar
    mine = [e for e in events if any(t["page"] == f"lag/{slug}/" for t in e["teams"])]
    swedes = sorted({s["name"] for e in mine for s in e["swedes"] if s["team"] in short or short in s["team"]})
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
        lede=lede, events=mine, links=" · ".join(league_links(entry.get("competitions", []), "../../")),
        updated=updated,
        watch=where_to_watch(name, entry.get("competitions", []))))


def render_league(r, events, registry, updated):
    name, slug = r["name"], league_slug(r["name"])
    mine = [e for e in events if e["competition"] == name]
    rights = rights_sentence(name)
    count = f"{len(mine)} matcher med svenskar de närmaste sju dagarna." if mine else \
        "Inga matcher med svenskar de närmaste sju dagarna."
    lede = f"{esc(rights)} {esc(count)}"
    players = sorted(((e["name"], s) for s, e in registry["players"].items() if name in e.get("competitions", [])),
                     key=lambda x: x[0])
    teams = sorted(((e["name"], s) for s, e in registry["teams"].items() if name in e.get("competitions", [])),
                   key=lambda x: x[0])
    parts = [f'<section class="watch"><h2>Vem visar {esc(name)} i Sverige?</h2>'
             f'<p>{esc(r.get("about") or rights)}'
             + (f' <a href="{esc(r["source"])}" rel="noopener" target="_blank">Källa</a>.' if r.get("source") else "")
             + "</p></section>"]
    if players:
        parts.append(f'<section class="watch"><h2>Svenskar i {esc(name)}</h2><p class="players">'
                     + ", ".join(f'<a href="../../spelare/{s}/">{esc(n)}</a>' for n, s in players) + "</p></section>")
    if teams:
        parts.append(f'<section class="watch"><h2>Lagen</h2><p class="players">'
                     + ", ".join(f'<a href="../../lag/{s}/">{esc(n)}</a>' for n, s in teams) + "</p></section>")
    description = f"{rights} Tider och kanal för veckans matcher med svenskar i {name}."
    write(DOCS / "liga" / slug / "index.html", page_html(
        title=f"{name} på TV i Sverige – kanal, tider och svenskarna | {SITE['name']}",
        description=description, path=f"liga/{slug}/", h1=f"{name} på TV",
        lede=lede, events=mine, links="", updated=updated, watch="\n    ".join(parts)))


def leagues():
    return [r for r in RIGHTS.values() if isinstance(r, dict) and r.get("name")]


def render_index(events, registry, updated):
    days = sorted({event_day(e["start"]) for e in events})
    first = [e for e in events if days and event_day(e["start"]) == days[0]]
    names = sorted({(s["name"], s["page"]) for e in events for s in e["swedes"]})
    links = ", ".join(f'<a href="{esc(p)}">{esc(n)}</a>' for n, p in names) or "inga just nu"
    seen = list(dict.fromkeys(s["name"] for e in events[:40] for s in e["swedes"]))[:3]
    description = ("Var du ser svenskarna i fotboll och NHL på TV idag"
                   + (f" – {', '.join(seen)} och fler" if seen else "") + ". Kanal och tid för varje match.")
    ld = {"@context": "https://schema.org", "@type": "ItemList",
          "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": sports_event_ld(e)}
                              for i, e in enumerate(events[:50])]}
    page = TEMPLATE.read_text()
    for key, value in {
        "{{DESCRIPTION}}": esc(description),
        "{{BASE_URL}}": esc(SITE["base_url"]),
        "{{COFFEE_URL}}": esc(SITE["coffee_url"]),
        "{{STYLE_CSS}}": asset("style.css"),
        "{{APP_JS}}": asset("app.js"),
        "{{USAGE_JS}}": asset("usage.js"),
        "{{JSONLD}}": json_ld(ld),
        "{{SITE_JSONLD}}": json_ld({"@context": "https://schema.org", "@type": "WebSite",
                                    "name": SITE["name"], "alternateName": ["patv.se", "Svenskar på TV"],
                                    "url": SITE["base_url"] + "/", "inLanguage": "sv-SE"}),
        "{{LIST}}": "".join(event_html(e) for e in first),
        "{{PLAYER_LINKS}}": links,
        "{{LEAGUE_LINKS}}": ", ".join(f'<a href="liga/{league_slug(r["name"])}/">{esc(r["name"])}</a>'
                                      for r in leagues()),
        "{{UPDATED}}": esc(updated),
    }.items():
        page = page.replace(key, value)
    write(DOCS / "index.html", page)


def render_sitemap(registry, today):
    base = SITE["base_url"]
    paths = [""] + [f"liga/{league_slug(r['name'])}/" for r in leagues()] \
        + [f"spelare/{s}/" for s in sorted(registry["players"])] \
        + [f"lag/{s}/" for s in sorted(registry["teams"])]
    known = registry.setdefault("lastmod", {})
    changed = []
    for path in paths:
        h = PAGE_HASHES.get(path)
        if h and known.get(path, {}).get("hash") != h:
            known[path] = {"hash": h, "date": today}
            changed.append(f"{base}/{path}")
    # Läses av scripts/indexnow.py, som berättar för Bing m.fl. vilka sidor som ändrats.
    CHANGED_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHANGED_FILE.write_text("".join(u + "\n" for u in changed))
    body = "".join(f"  <url><loc>{esc(base + '/' + p)}</loc><lastmod>{known.get(p, {}).get('date', today)}</lastmod></url>\n"
                   for p in paths)
    urls = paths
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
    for r in leagues():
        render_league(r, events, registry, updated)
    render_index(events, registry, updated)
    count = render_sitemap(registry, today)

    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")  # nu med sidadresser
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(registry, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(f'{len(registry["players"])} spelarsidor, {len(registry["teams"])} lagsidor, '
          f'{len(leagues())} ligasidor, {count} adresser i sitemap')


if __name__ == "__main__":
    main()
