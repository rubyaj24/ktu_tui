def show_main_menu_arrow(client):
    """Arrow-key navigable main menu. Returns the same strings as
    show_main_menu: 'quit', 'login', 'settings', or a menu key like '1'.
    """
    from ktu_input import pick, KEY_ENTER, KEY_UP, KEY_DOWN
    items = []
    for m in MAIN_MENU:
        if m["key"] == "0":
            continue
        items.append((m["key"], m["label"], m.get("blurb", "")))
