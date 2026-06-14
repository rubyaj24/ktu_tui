    title = "Main menu"
    while True:
        layout = build_layout(
            client, [], Panel(
                Align.center(Text(
                    "Use UP/DOWN arrows + Enter (or 1-6 + Enter)\n"
                    "Type L to login, Q to quit, B to go back",
                    style="dim")),
                border_style="blue", title="[bold]Home[/bold]"),
            None, last_msg="Arrows to move, Enter to pick")
        console.clear()
        console.print(layout)
        picked = pick([(k, l) for k, l, b in items], title=title)
