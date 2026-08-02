"""Real Textual themes used by the OpenWallStreet terminal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from textual.theme import Theme


@dataclass(frozen=True)
class ThemeDefinition:
    name: str
    label: str
    description: str
    theme: Theme


def _theme(
    name: str,
    label: str,
    description: str,
    *,
    primary: str,
    secondary: str,
    accent: str,
    foreground: str,
    background: str,
    surface: str,
    panel: str,
    success: str,
    warning: str,
    error: str,
    dark: bool,
) -> ThemeDefinition:
    return ThemeDefinition(
        name=name,
        label=label,
        description=description,
        theme=Theme(
            name=name,
            primary=primary,
            secondary=secondary,
            accent=accent,
            foreground=foreground,
            background=background,
            surface=surface,
            panel=panel,
            success=success,
            warning=warning,
            error=error,
            dark=dark,
            variables={
                "footer-key-foreground": accent,
                "footer-description-foreground": foreground,
                "block-cursor-background": accent,
                "block-cursor-foreground": background,
                "input-selection-background": f"{secondary} 45%",
            },
        ),
    )


THEMES: tuple[ThemeDefinition, ...] = (
    _theme("openwallstreet-dark", "OpenWallStreet Dark", "Balanced operational dark theme.", primary="#2A6E7B", secondary="#6750A4", accent="#68D6E7", foreground="#E8EDF2", background="#090C10", surface="#10151B", panel="#171D25", success="#55C98B", warning="#F0BE62", error="#E06C75", dark=True),
    _theme("midnight", "Midnight", "Deep blue low-glare terminal.", primary="#3B82F6", secondary="#6366F1", accent="#93C5FD", foreground="#E5ECF6", background="#050A14", surface="#0B1322", panel="#111C30", success="#34D399", warning="#FBBF24", error="#FB7185", dark=True),
    _theme("terminal-green", "Terminal Green", "Classic green phosphor styling.", primary="#2FD66F", secondary="#1FA454", accent="#8BFFB3", foreground="#D9FFE5", background="#020805", surface="#06120B", panel="#0A1C10", success="#62FF95", warning="#D6E85B", error="#FF6B73", dark=True),
    _theme("amber-crt", "Amber CRT", "Warm amber monochrome inspired display.", primary="#E5A84B", secondary="#B97822", accent="#FFD38A", foreground="#FFE8BD", background="#0C0802", surface="#171006", panel="#23180A", success="#D4D85B", warning="#FFC857", error="#FF7A59", dark=True),
    _theme("nord", "Nord", "Cool arctic blue palette.", primary="#88C0D0", secondary="#81A1C1", accent="#B48EAD", foreground="#D8DEE9", background="#2E3440", surface="#3B4252", panel="#434C5E", success="#A3BE8C", warning="#EBCB8B", error="#BF616A", dark=True),
    _theme("dracula", "Dracula", "Purple-accented dark palette.", primary="#BD93F9", secondary="#6272A4", accent="#FF79C6", foreground="#F8F8F2", background="#191A21", surface="#282A36", panel="#343746", success="#50FA7B", warning="#F1FA8C", error="#FF5555", dark=True),
    _theme("solarized-dark", "Solarized Dark", "Low-contrast precision dark theme.", primary="#268BD2", secondary="#2AA198", accent="#B58900", foreground="#EEE8D5", background="#002B36", surface="#073642", panel="#0B4552", success="#859900", warning="#B58900", error="#DC322F", dark=True),
    _theme("solarized-light", "Solarized Light", "Warm, readable light theme.", primary="#268BD2", secondary="#2AA198", accent="#B58900", foreground="#073642", background="#FDF6E3", surface="#EEE8D5", panel="#E4DDC9", success="#859900", warning="#B58900", error="#DC322F", dark=False),
    _theme("monochrome", "Monochrome", "Neutral grayscale terminal.", primary="#BFC5CC", secondary="#8C939C", accent="#FFFFFF", foreground="#F0F2F4", background="#08090B", surface="#141619", panel="#202328", success="#D8DCE1", warning="#B8BDC4", error="#FFFFFF", dark=True),
    _theme("high-contrast", "High Contrast", "Maximum separation for accessibility.", primary="#00E5FF", secondary="#FF00D4", accent="#FFFF00", foreground="#FFFFFF", background="#000000", surface="#080808", panel="#151515", success="#00FF66", warning="#FFFF00", error="#FF3B3B", dark=True),
    _theme("paper", "Paper", "Clean light theme for bright environments.", primary="#215A75", secondary="#654A8A", accent="#A33D22", foreground="#20252A", background="#FAF7F0", surface="#F0ECE3", panel="#E4DED2", success="#287A4B", warning="#9B6500", error="#B3261E", dark=False),
    _theme("cyberpunk", "Cyberpunk", "Neon cyan and magenta on deep black.", primary="#00F0FF", secondary="#7A5CFF", accent="#FF2BD6", foreground="#F5F7FF", background="#03030A", surface="#0B0B18", panel="#151526", success="#39FF88", warning="#FFE65B", error="#FF4567", dark=True),
)


_BY_NAME = {definition.name: definition for definition in THEMES}
_BY_LABEL = {definition.label: definition for definition in THEMES}


def theme_names() -> tuple[str, ...]:
    return tuple(definition.name for definition in THEMES)


def theme_labels() -> tuple[str, ...]:
    return tuple(definition.label for definition in THEMES)


def normalize_theme(name_or_label: str) -> str:
    definition = _BY_NAME.get(name_or_label) or _BY_LABEL.get(name_or_label)
    return definition.name if definition else THEMES[0].name


def theme_label(name: str) -> str:
    return _BY_NAME.get(normalize_theme(name), THEMES[0]).label


def register_themes(app: object) -> None:
    register = getattr(app, "register_theme")
    for definition in THEMES:
        register(definition.theme)


def iter_themes() -> Iterable[ThemeDefinition]:
    return THEMES
