"""Checks on the factory's own shipped config. Factory-only (tests/): a generated ecosystem renders its own values
from its blueprint (tests/test_generate_t13.py checks those). Moved here from engine/tests/test_usage_t08.py in T1.3."""
import json
import unittest

from support import REPO


class ShippedCeilingTests(unittest.TestCase):
    def test_shipped_ceiling_is_marked_provisional(self):
        caps = json.loads((REPO / "config/caps.json").read_text(encoding="utf-8"))
        u = caps["usage_ceiling"]
        self.assertIn("PROVISIONAL", u["_provisional"])
        self.assertIn("T1.4", u["_provisional"])
        self.assertEqual((u["tokens"], u["agent_minutes"], u["per_call_warning_tokens"]), (2000000, 180, 500000))


if __name__ == "__main__":
    unittest.main()
