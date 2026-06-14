def pick(items, title="Pick", start=0):
    selected = start
    while True:
        k = read_key()
        if k == KEY_UP:
            selected = (selected - 1) % len(items)
        elif k == KEY_DOWN:
            selected = (selected + 1) % len(items)
        elif k == KEY_ENTER:
            return selected
        elif k == KEY_CTRL_C:
            raise KeyboardInterrupt
        elif k == KEY_ESC:
            return -1
        elif len(k) == 1 and k.isdigit():
            n = int(k)
            if 1 <= n <= len(items):
                return n - 1

