"""Section-scoped apply/discard behavior for production Settings."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.widgets import Static

from trader.settings_screen import SECTION_DESCRIPTIONS, SECTIONS, SettingsScreen
from trader.settings_store import UISettings, UISettingsError


class ProductionSettingsScreen(SettingsScreen):
    """Keep Watchlist and Appearance drafts independent."""

    def _watchlist_pending(self) -> bool:
        source, symbols, _theme, _dense, _unicode = self._saved_snapshot
        return self.watchlist_source != source or tuple(self.watchlist_symbols) != symbols

    def _appearance_pending(self) -> bool:
        _source, _symbols, theme, dense, unicode_symbols = self._saved_snapshot
        return (
            self.theme_name != theme
            or self.dense != dense
            or self.unicode_symbols != unicode_symbols
        )

    def _section_pending(self, category: str | None = None) -> bool:
        category = category or self.category
        if category == "Watchlist":
            return self._watchlist_pending()
        if category == "Appearance":
            return self._appearance_pending()
        return False

    def _pending(self) -> bool:
        return self._watchlist_pending() or self._appearance_pending()

    def _render_sections(self) -> Text:
        width = max(32, self.query_one("#settings-sections", Static).size.width or 64)
        name_width = 23
        description_width = max(0, width - name_width - 7)
        text = Text()
        for index, section in enumerate(SECTIONS):
            selected = index == self.section_index
            marker = "›" if selected and self.pane == "sections" else "•" if selected else " "
            pending = "*" if self._section_pending(section) else " "
            line = f" {marker} {section:<{name_width}} {pending}"
            if selected and self.pane == "sections":
                text.append(line, style="bold reverse")
            elif selected:
                text.append(line, style="bold cyan")
            elif pending == "*":
                text.append(line, style="yellow")
            else:
                text.append(line, style="dim")
            if description_width:
                text.append(
                    f"  {self._clip(SECTION_DESCRIPTIONS[section], description_width):<{description_width}}",
                    style="italic dim",
                )
            text.append("\n")
        return text

    def _apply(self) -> None:
        category = self.category
        if not self._section_pending(category):
            self.message = f"No pending edits in {category}."
            self.render_settings()
            return

        saved_source, saved_symbols, saved_theme, saved_dense, saved_unicode = self._saved_snapshot
        try:
            if category == "Watchlist":
                if self.watchlist_source == "IBKR":
                    self.message = (
                        "Apply blocked: the current MMR SDK does not expose broker watchlists. "
                        "Switch back to MANUAL to save."
                    )
                    self.render_settings()
                    return
                settings = UISettings(
                    watchlist_source=self.watchlist_source,
                    manual_symbols=list(self.watchlist_symbols),
                    symbol_history=list(self.store.settings.symbol_history),
                    theme=self.store.settings.theme,
                    dense=self.store.settings.dense,
                    unicode_symbols=self.store.settings.unicode_symbols,
                )
                self.store.settings = settings
                self.store.update_history(self.watchlist_symbols)
                self.store.save(self.store.settings)
                self.app_ref.watchlist = list(self.watchlist_symbols)
                self._saved_snapshot = (
                    self.watchlist_source,
                    tuple(self.watchlist_symbols),
                    saved_theme,
                    saved_dense,
                    saved_unicode,
                )
                self.message = "Watchlist applied and saved locally."
                self.app_ref.action_refresh()
            elif category == "Appearance":
                settings = UISettings(
                    watchlist_source=self.store.settings.watchlist_source,
                    manual_symbols=list(self.store.settings.manual_symbols),
                    symbol_history=list(self.store.settings.symbol_history),
                    theme=self.theme_name,
                    dense=self.dense,
                    unicode_symbols=self.unicode_symbols,
                )
                self.store.save(settings)
                self.app_ref.theme = self.theme_name
                self.app_ref.set_class(self.dense, "dense")
                self._saved_snapshot = (
                    saved_source,
                    saved_symbols,
                    self.theme_name,
                    self.dense,
                    self.unicode_symbols,
                )
                self.message = "Appearance settings applied."
        except (OSError, UISettingsError) as exc:
            self.message = f"{category} was not saved: {type(exc).__name__}: {exc}"
        self.render_settings()

    def _discard(self) -> None:
        category = self.category
        saved_source, saved_symbols, saved_theme, saved_dense, saved_unicode = self._saved_snapshot
        if category == "Watchlist":
            self.watchlist_source = saved_source
            self.watchlist_symbols = list(saved_symbols)
            self.message = "Pending Watchlist edits discarded."
        elif category == "Appearance":
            self.theme_name = saved_theme
            self.dense = saved_dense
            self.unicode_symbols = saved_unicode
            self.app_ref.theme = saved_theme
            self.app_ref.set_class(saved_dense, "dense")
            self.message = "Pending Appearance edits discarded."
        else:
            self.message = f"No editable draft in {category}."
        self.render_settings()

    def on_key(self, event: events.Key) -> None:
        if (
            not self.editing
            and self.pane == "sections"
            and event.key in {"escape", "left"}
            and self._pending()
        ):
            self.message = "Pending edits remain. Open the marked section, then press A to apply or D to discard."
            self.render_settings()
            event.stop()
            event.prevent_default()
            return
        super().on_key(event)
