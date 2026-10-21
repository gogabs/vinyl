"""Pede ao a11yd que não suspenda sozinho e apague a tela enquanto toca.

O arquivo $XDG_RUNTIME_DIR/a11y-reproduzindo guarda o PID de quem toca. O
a11yd ignora o arquivo se o processo já morreu, então um fechamento à força
não deixa o console acordado para sempre. Usa game.keep_awake do Mage Core
quando a versão instalada tiver.
"""
import os
import tempfile


def flag_path():
    return os.environ.get("A11Y_REPRODUZINDO") or os.path.join(
        os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(), "a11y-reproduzindo")


def keep_awake(on):
    path = flag_path()
    try:
        if on:
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                f.write(str(os.getpid()))
            os.replace(tmp, path)
        else:
            with open(path) as f:
                mine = f.read().strip() == str(os.getpid())
            if mine:
                os.remove(path)
    except OSError:
        pass


def for_game(game):
    return getattr(game, "keep_awake", None) or keep_awake
