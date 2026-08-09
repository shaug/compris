"""Contract invariants for the outer-loop-companion positioning #139 adds.

Checks stable identifiers, not phrasing: that the README lead names the
"outer loop" framing, names superpowers, and links to the "Using beside peer
skills" section; and that every marketplace/plugin description surface
carries the same "outer loop" / "compose with, not depend on" positioning.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
README = REPOSITORY_ROOT / "README.md"


def compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class ReadmeLeadPositioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        text = README.read_text()
        # The lead is everything before the first "## " heading.
        cls.lead = compact(text.split("\n## ", 1)[0])

    def test_the_lead_names_the_outer_loop_framing(self) -> None:
        self.assertIn("outer-loop companion", self.lead)
        self.assertIn("superpowers", self.lead)

    def test_the_lead_links_the_peer_composition_section(self) -> None:
        self.assertIn("Using beside peer skills", self.lead)
        self.assertIn("#using-beside-peer-skills", self.lead)

    def test_the_lead_states_standalone_function(self) -> None:
        self.assertIn("fully functional without a peer installed", self.lead)


class MarketplacePositioningTests(unittest.TestCase):
    def test_every_description_surface_carries_the_outer_loop_positioning(
        self,
    ) -> None:
        surfaces = {
            ".claude-plugin/plugin.json": lambda m: m["description"],
            ".codex-plugin/plugin.json": lambda m: m["description"],
            ".codex-plugin/plugin.json#longDescription": lambda m: m["interface"][
                "longDescription"
            ],
            ".claude-plugin/marketplace.json#metadata": lambda m: m["metadata"][
                "description"
            ],
            ".claude-plugin/marketplace.json#plugin-entry": lambda m: m["plugins"][0][
                "description"
            ],
        }
        for label, extract in surfaces.items():
            rel = label.split("#", 1)[0]
            manifest = json.loads((REPOSITORY_ROOT / rel).read_text())
            with self.subTest(surface=label):
                text = extract(manifest)
                self.assertIn("outer loop", text)
                self.assertIn("superpowers", text)
                self.assertRegex(text, r"compose(?:s)? with, not depend(?:s)? on")


if __name__ == "__main__":
    unittest.main()
