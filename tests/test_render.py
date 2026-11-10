import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import render  # noqa: E402


def event(title, swedes, sport="Fotboll", start="2026-10-10T19:00:00Z"):
    return {"title": title, "sport": sport, "start": start, "competition": "X",
            "swedes": [dict(s) for s in swedes], "tv": {"status": "unknown"}}


class SlugTest(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(render.slugify("Viktor Gyökeres"), "viktor-gyokeres")
        self.assertEqual(render.slugify("Elias Pettersson #25"), "elias-pettersson-25")
        self.assertEqual(render.slugify("Bodø/Glimt"), "bodo-glimt")


class NightTest(unittest.TestCase):
    def test_night_game_belongs_to_evening_before(self):
        # 01:00 svensk tid natten mot söndag räknas till lördag
        self.assertEqual(str(render.event_day("2026-10-10T23:00:00Z")), "2026-10-10")
        self.assertEqual(render.fmt_when("2026-10-10T23:00:00Z"), "lör 10 okt kl 01:00 (natt)")


class AssignPagesTest(unittest.TestCase):
    def test_same_name_different_players_get_different_pages(self):
        registry = {}
        events = [
            event("Stoke – Hull", [{"name": "Viktor Johansson", "team": "Stoke", "url": "w/A"}]),
            event("Leeds – Derby", [{"name": "Viktor Johansson", "team": "Derby", "url": "w/B"}]),
        ]
        render.assign_pages(events, registry, "2026-10-09")
        pages = [events[0]["swedes"][0]["page"], events[1]["swedes"][0]["page"]]
        self.assertEqual(pages, ["spelare/viktor-johansson/", "spelare/viktor-johansson-derby/"])
        self.assertEqual(events[0]["teams"][0]["page"], "lag/stoke/")

    def test_page_address_is_stable_between_runs(self):
        registry = {}
        first = [event("A – B", [{"name": "Viktor Johansson", "team": "Derby", "url": "w/B"}])]
        render.assign_pages(first, registry, "2026-10-09")
        second = [event("A – B", [{"name": "Viktor Johansson", "team": "Stoke", "url": "w/A"}]),
                  event("C – D", [{"name": "Viktor Johansson", "team": "Derby", "url": "w/B"}])]
        render.assign_pages(second, registry, "2026-10-10")
        self.assertEqual(second[1]["swedes"][0]["page"], "spelare/viktor-johansson/")

    def test_old_pages_are_kept_for_google(self):
        registry = {"players": {"gammal": {"key": "k", "last_seen": "2026-01-01"}}, "teams": {}}
        render.assign_pages([], registry, "2026-10-09")
        self.assertIn("gammal", registry["players"])

    def test_nhl_names_get_swedish_letters_from_wikipedia(self):
        events = [event("A – B", [{"name": "Adam Edstrom", "team": "Predators",
                                   "url": "https://sv.wikipedia.org/wiki/Adam_Edstr%C3%B6m"}])]
        registry = {}
        render.assign_pages(events, registry, "2026-10-10")
        self.assertEqual(events[0]["swedes"][0]["name"], "Adam Edström")
        self.assertEqual(events[0]["swedes"][0]["page"], "spelare/adam-edstrom/")
        self.assertEqual(registry["players"]["adam-edstrom"]["competitions"], ["X"])

    def test_wiki_name_only_when_same_letters(self):
        self.assertEqual(render.wiki_name("Isak Rosen", "https://sv.wikipedia.org/wiki/Isak_Ros%C3%A9n"), "Isak Rosén")
        self.assertEqual(render.wiki_name("Elias Pettersson",
                         "https://sv.wikipedia.org/wiki/Elias_Pettersson_(ishockeyspelare_f%C3%B6dd_1998)"),
                         "Elias Pettersson")
        self.assertEqual(render.wiki_name("Hugo Larsson", "https://sv.wikipedia.org/wiki/Hugo_Andersson"), "Hugo Larsson")
        self.assertEqual(render.wiki_name("X", None), "X")


class HtmlTest(unittest.TestCase):
    def test_event_html_escapes_and_links(self):
        e = event("A <b> – B", [{"name": "X", "team": "A", "page": "spelare/x/"}])
        e["tv"] = {"status": "confirmed", "service": "Viaplay", "channel": None}
        out = render.event_html(e, "../../")
        self.assertIn("A &lt;b&gt; – B", out)
        self.assertIn('href="../../spelare/x/"', out)
        self.assertIn('badge confirmed">Viaplay<', out)


if __name__ == "__main__":
    unittest.main()


class RightsTest(unittest.TestCase):
    def test_rights_sentences(self):
        self.assertIn("Viaplay", render.rights_sentence("Premier League"))
        self.assertIn("Prime Video", render.rights_sentence("Premier League"))
        self.assertIn("Disney+", render.rights_sentence("NHL"))
        self.assertIn("TV4 Play", render.rights_sentence("Serie A"))
        self.assertIn("inte hittat", render.rights_sentence("Okänd liga"))

    def test_where_to_watch_escapes(self):
        out = render.where_to_watch("A <b>", ["Serie A"])
        self.assertIn("A &lt;b&gt;", out)
        self.assertEqual(render.where_to_watch("A", []), "")


class LeagueTest(unittest.TestCase):
    def test_league_links_only_for_known_leagues(self):
        links = render.league_links(["Premier League", "Okänd"], "../../")
        self.assertEqual(links, ['<a href="../../liga/premier-league/">Premier League på TV</a>'])

    def test_every_league_has_about_text(self):
        for r in render.leagues():
            self.assertTrue(r.get("about"), r["name"])


class AssetTest(unittest.TestCase):
    def test_asset_has_version(self):
        self.assertRegex(render.asset("style.css"), r"^style\.css\?v=[0-9a-f]{8}$")


class TeamNameTest(unittest.TestCase):
    def test_short_names_get_full_names(self):
        self.assertEqual(render.TEAM_NAMES["AZ"], "AZ Alkmaar")


class WeekendTest(unittest.TestCase):
    def test_weekend_days(self):
        import datetime as dt
        fri, sat, sun = dt.date(2026, 11, 13), dt.date(2026, 11, 14), dt.date(2026, 11, 15)
        for today in (dt.date(2026, 11, 9), dt.date(2026, 11, 12), fri, sat, sun):  # mån, tors, fre, lör, sön
            self.assertEqual(render.weekend_days(today), [fri, sat, sun], today)

    def test_range_across_months(self):
        import datetime as dt
        self.assertEqual(render.fmt_range(render.weekend_days(dt.date(2026, 10, 30))), "30 okt–1 nov")
