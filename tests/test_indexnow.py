import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import indexnow  # noqa: E402


class PayloadTest(unittest.TestCase):
    def test_payload_uses_host_and_key_file(self):
        site = {"base_url": "https://patv.se", "indexnow_key": "abc123"}
        p = indexnow.payload(["https://patv.se/", "https://patv.se/liga/nhl/"], site)
        self.assertEqual(p["host"], "patv.se")
        self.assertEqual(p["keyLocation"], "https://patv.se/abc123.txt")
        self.assertEqual(len(p["urlList"]), 2)

    def test_key_file_matches_site_json(self):
        key = indexnow.SITE["indexnow_key"]
        self.assertEqual((indexnow.ROOT / "docs" / f"{key}.txt").read_text().strip(), key)
