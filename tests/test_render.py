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

    def test_old_pages_are_dropped_after_keep_days(self):
        registry = {"players": {"gammal": {"key": "k", "last_seen": "2026-01-01"}}, "teams": {}}
        render.assign_pages([], registry, "2026-10-09")
        self.assertNotIn("gammal", registry["players"])


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
