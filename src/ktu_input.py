"""Arrow-key menu picker for KTU TUI.

Reads one keypress at a time without readchar or prompt_toolkit.
Supports arrow up/down navigation, enter to confirm, and number keys
for direct pick.  Cross-platform (Unix tty/termios, Windows msvcrt).
"""

import os
import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.align import Align

console = Console()

KEY_UP = "UP"
KEY_DOWN = "DOWN"
KEY_ENTER = "ENTER"
KEY_ESC = "ESC"
KEY_CTRL_C = "CTRL_C"


# ---------------------------------------------------------------------------
# Platform-specific raw key reader
# ---------------------------------------------------------------------------

if os.name == "nt":
    import msvcrt  # Windows console I/O

    def read_key() -> str:
        if not msvcrt.kbhit():
            return ""
        ch = msvcrt.getch()
        if ch == b"\xe0":
            ch2 = msvcrt.getch()
            return {b"H": KEY_UP, b"P": KEY_DOWN}.get(ch2, "")
        if ch in (b"\r", b"\n"):
            return KEY_ENTER
        if ch == b"\x03":
            return KEY_CTRL_C
        if ch == b"\x1b":
            return KEY_ESC
        try:
            return ch.decode("utf-8")
        except UnicodeDecodeError:
            return ""

else:
    import tty
    import termios

    def read_key() -> str:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        if not ch:
            return ""
        if ch == "\x1b":
            fd2 = sys.stdin.fileno()
            old2 = termios.tcgetattr(fd2)
            try:
                tty.setraw(fd2)
                ch2 = sys.stdin.read(1)
            finally:
                termios.tcsetattr(fd2, termios.TCSADRAIN, old2)
            if ch2 == "[":
                try:
                    tty.setraw(fd2)
                    ch3 = sys.stdin.read(1)
                finally:
                    termios.tcsetattr(fd2, termios.TCSADRAIN, old2)
                return {"A": KEY_UP, "B": KEY_DOWN}.get(ch3, "")
            return KEY_ESC
        if ch in (chr(13), chr(10)):
            return KEY_ENTER
        if ch == "\x03":
            return KEY_CTRL_C
        return ch


def _render_picker(items, selected, title="Pick") -> None:
    """Print the picker table to the terminal (used by :func:`pick`)."""
    table = Table(show_header=False, border_style="cyan", title=title)
    table.add_column(width=4, justify="right", style="bold")
    table.add_column()
    table.add_column(style="dim")
    for i, item in enumerate(items):
        if isinstance(item, tuple):
            key = str(item[0])
            label = str(item[1]) if len(item) > 1 else key
            blurb = str(item[2]) if len(item) > 2 else ""
        else:
            key = str(i + 1)
            label = str(item)
            blurb = ""
        if i == selected:
            table.add_row(
                f"▶ {key}",
                f"[reverse bold cyan]{label}[/reverse bold cyan]",
                f"[reverse bold cyan]{blurb}[/reverse bold cyan]" if blurb else "",
            )
        else:
            table.add_row(
                f"  {key}",
                label,
                f"[dim]{blurb}[/dim]" if blurb else "",
            )
    console.print(Panel(table, border_style="cyan"))
    console.print("[dim]↑↓ Navigate • Enter Select • Esc Back • (l)ogin • (q)uit[/dim]")


def pick(items, title="Pick", start=0):
    """Arrow-key navigable picker.

    Renders once, then redraws in-place on each keypress (no flicker).
    Returns the selected item (tuple or scalar), or *None* on Esc, or a
    single-character command string (*l*, *q*, *b*, *r*) for callers that
    want to handle those keys directly.
    """
    selected = start
    lines = len(items) + 4  # estimated render height
    first = True
    while True:
        if first:
            first = False
        else:
            # move cursor back up and clear for in-place redraw
            sys.stdout.write(f"\x1b[{lines}A\x1b[J")
            sys.stdout.flush()
        _render_picker(items, selected, title)

        k = read_key()
        if k == KEY_UP:
            selected = (selected - 1) % len(items)
        elif k == KEY_DOWN:
            selected = (selected + 1) % len(items)
        elif k == KEY_ENTER:
            return items[selected]
        elif k == KEY_ESC:
            return None
        elif k == KEY_CTRL_C:
            sys.exit(0)
        elif len(k) == 1 and k.isdigit():
            n = int(k)
            if 1 <= n <= len(items):
                return items[n - 1]
        elif len(k) == 1 and k in ("l", "q", "b", "r"):
            return k