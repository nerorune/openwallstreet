"""Final active-section UI semantics for the production Settings screen."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from trader.settings_scoped import ProductionSettingsScreen
from trader.settings_screen import SettingsRow


class OpenWallStreetSettingsScreen(ProductionSettingsScreen):
    """Show apply/discard hints only for the section that owns the draft."""

    def _rows(self) -> list[SettingsRow]:
        rows = super()._rows()
        if self.category == "Watchlist" and len(rows) > 1:
            rows[1] = SettingsRow(
                "Persistence",
                "Unsaved changes" if self._watchlist_pending() else "Saved locally",
            )
        return rows

    def _status(self) -> Text:
        text = Text()
        text.append(f" {self.message} ", style="bold")
        text.append("│", style="magenta")
        if self.editing:
            hints = " Type edit  ←/→ cursor  Enter stage  Esc cancel "
            suggestions = self.store.suggestions(self._edit_value)
            if self._edit_row and self._edit_row.key == "watchlist-new" and suggestions:
                hints += " Suggestions: " + ", ".join(suggestions)
        elif self.pane == "sections":
            hints = " ↑/↓ move  Enter open  Esc close  Ctrl+Q exit "
        else:
            hints = " ↑/↓ move  Enter edit/select  Space select  Esc back  H details "
            if self.category == "Watchlist":
                hints += " N add  X remove  Shift+↑/↓ priority "
            elif self.category == "Diagnostics":
                hints += " R run "
        text.append(hints, style="dim")
        if self._section_pending():
            text.append("│ A apply  D discard ", style="bold yellow")
        return text

    def render_settings(self) -> None:
        super().render_settings()
        pending = self.query_one("#settings-pending", Static)
        pending.display = self._section_pending()
        pending.update("PENDING EDITS · A APPLY · D DISCARD" if pending.display else "")
