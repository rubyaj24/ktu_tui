def render_picker(items, selected, title="Pick"):
    from rich.table import Table
    from rich.panel import Panel
    from rich.console import Console
    from rich.text import Text
    c = Console()
    t = Table(show_header=False, border_style="cyan", title=title)
    t.add_column(width=4, justify="right", style="bold")
    t.add_column()
    for i, item in enumerate(items):
        marker = ">" if i == selected else " "
        style = "reverse bold cyan" if i == selected else ""
        if isinstance(item, tuple):
            label, blurb = item[0], item[1] if len(item) > 1 else ""
        else:
            label, blurb = str(item), ""
        t.add_row(f"{marker} {i+1}", f"[{style}]{label}[/{'style' if style else '[/'}]")
    c.print(Panel(t, border_style="cyan"))
    c.print("[dim]arrows + Enter | number + Enter | Esc cancel[/dim]")

