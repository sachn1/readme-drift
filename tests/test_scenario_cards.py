"""Keep the generated scenario images current and referenced from the docs."""

from pathlib import Path

import pytest

from scenario_cards import CARDS, OUT_DIR, render_card

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", CARDS)
def test_committed_card_matches_a_fresh_run(name):
    """The committed SVG equals what the tool produces now; run `make cards` to refresh."""
    committed = (OUT_DIR / f"{name}.svg").read_text(encoding="utf-8")
    assert committed == render_card(name)


def test_every_card_is_shown_on_the_scenarios_page():
    """Each generated image is embedded in docs/scenarios.md."""
    page = (ROOT / "docs" / "scenarios.md").read_text()
    assert [n for n in CARDS if f"assets/scenarios/{n}.svg" not in page] == []


def test_readme_shows_the_hero_card():
    """The README embeds the first scenario image above the fold."""
    assert "docs/assets/scenarios/py-rename.svg" in (ROOT / "README.md").read_text()
