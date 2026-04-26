"""
tests/test_phase30_app_aliases.py
Phase 30 — App Alias Resolution Tests

Verifies:
1. All new Phase 30 aliases resolve to a non-None, non-empty value.
2. Resolution is case-insensitive (e.g. "WhatsApp" → same as "whatsapp").
3. Discord / Teams entries are lists (multi-arg subprocess args).
4. List entries contain the expected --processStart flag.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from desktop_action_manager import _resolve_app, APP_REGISTRY, _USERNAME


# ── Basic resolution ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "whatsapp",
    "whats app",
    "discord",
    "telegram",
    "zoom",
    "microsoft teams",
    "teams",
    "slack",
    "obs",
    "steam",
    "skype",
])
def test_alias_resolves_to_something(name):
    """Every Phase 30 alias must return a non-empty result."""
    result = _resolve_app(name)
    assert result, f"_resolve_app('{name}') returned empty/None"
    if isinstance(result, list):
        assert all(part for part in result), f"List entry for '{name}' has empty elements: {result}"
    else:
        assert len(result) > 0


# ── Case-insensitive resolution ───────────────────────────────────────────────

def test_whatsapp_case_insensitive():
    """'WhatsApp' and 'whatsapp' must resolve to the same entry."""
    lower = _resolve_app("whatsapp")
    upper = _resolve_app("WhatsApp")
    mixed = _resolve_app("WHATSAPP")
    assert lower == upper == mixed, (
        f"Case mismatch: lower={lower!r}, upper={upper!r}, mixed={mixed!r}"
    )


def test_discord_case_insensitive():
    lower = _resolve_app("discord")
    upper = _resolve_app("Discord")
    assert lower == upper


# ── List-based entries for multi-arg launchers ────────────────────────────────

def test_discord_is_list():
    """Discord entry must be a list so Popen receives correct args."""
    entry = _resolve_app("discord")
    assert isinstance(entry, list), f"Expected list, got {type(entry)}: {entry!r}"


def test_discord_has_processstart_flag():
    """Discord list entry must contain --processStart."""
    entry = _resolve_app("discord")
    assert isinstance(entry, list)
    assert "--processStart" in entry, f"Missing --processStart in {entry}"


def test_discord_executable_in_list():
    """Discord list entry must end with Discord.exe."""
    entry = _resolve_app("discord")
    assert isinstance(entry, list)
    assert "Discord.exe" in entry


def test_teams_is_list():
    entry = _resolve_app("teams")
    assert isinstance(entry, list)


def test_microsoft_teams_is_list():
    entry = _resolve_app("microsoft teams")
    assert isinstance(entry, list)


def test_teams_has_processstart_flag():
    entry = _resolve_app("teams")
    assert isinstance(entry, list)
    assert "--processStart" in entry


# ── Username expansion was applied at module load ────────────────────────────

def test_user_placeholder_not_in_any_string_entry():
    """{user} must not appear in any final registry string value."""
    for key, val in APP_REGISTRY.items():
        if isinstance(val, str):
            assert "{user}" not in val, (
                f"Registry entry '{key}' still contains {{user}} placeholder: {val!r}"
            )
        elif isinstance(val, list):
            for part in val:
                assert "{user}" not in part, (
                    f"Registry list entry '{key}' part still contains {{user}}: {part!r}"
                )


def test_username_applied_in_whatsapp():
    """The resolved WhatsApp path should contain the actual username."""
    entry = _resolve_app("whatsapp")
    assert isinstance(entry, str)
    assert _USERNAME in entry, (
        f"Expected username '{_USERNAME}' in path, got: {entry!r}"
    )
