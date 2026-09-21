"""Smoke for commands package."""

import ghostcopyeditor.commands as commands_pkg


def test_commands_package_importable() -> None:
    assert commands_pkg.__name__ == "ghostcopyeditor.commands"
