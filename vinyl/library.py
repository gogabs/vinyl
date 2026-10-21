"""As pastas do cartão: audiolivros e música.

Um livro é uma pasta dentro de audiolivros (os arquivos, em ordem, são os
capítulos; subpastas como "CD 1" e "CD 2" entram na ordem) ou um arquivo só
(um .m4b com capítulos embutidos, por exemplo). Na música, cada pasta com
faixas é uma pasta tocável.
"""
import os
import re

AUDIO = {".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wav", ".wma"}


def roots():
    """As duas pastas do cartão (VINYL_AUDIOLIVROS e VINYL_MUSICA mudam)."""
    return (os.environ.get("VINYL_AUDIOLIVROS", "/roms/audiolivros"),
            os.environ.get("VINYL_MUSICA", "/roms/musica"))


def natural_key(name):
    """Ordem de gente: "Capítulo 2" antes de "Capítulo 10"."""
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", name)]


def is_audio(name):
    return not name.startswith(".") and os.path.splitext(name)[1].lower() in AUDIO


def display_name(path):
    """Nome falado: sem extensão, sem sublinhados."""
    name = os.path.basename(path.rstrip("/"))
    if is_audio(name):
        name = os.path.splitext(name)[0]
    return re.sub(r"[_]+", " ", name).strip() or name


def _entries(folder):
    try:
        names = os.listdir(folder)
    except OSError:
        return [], []
    dirs, files = [], []
    for name in sorted(names, key=natural_key):
        if name.startswith("."):
            continue
        path = os.path.join(folder, name)
        if os.path.isdir(path):
            dirs.append(path)
        elif is_audio(name):
            files.append(path)
    return dirs, files


def tracks_in(folder, recursive=False):
    dirs, files = _entries(folder)
    if recursive:
        for sub in dirs:
            files += tracks_in(sub, True)
    return files


class Book:
    """Um livro: uma chave estável (o caminho relativo) e os arquivos."""

    def __init__(self, root, path):
        self.path = path
        self.key = os.path.relpath(path, root).replace(os.sep, "/")
        self.title = display_name(path)
        self.files = tracks_in(path, recursive=True) if os.path.isdir(path) else [path]


def books(root=None):
    root = root or roots()[0]
    dirs, files = _entries(root)
    found = [Book(root, d) for d in dirs] + [Book(root, f) for f in files]
    return [b for b in found if b.files]


class Folder:
    """Uma pasta de música: subpastas que têm música e as faixas dela."""

    def __init__(self, root, path):
        self.root = root
        self.path = path
        self.key = os.path.relpath(path, root).replace(os.sep, "/")
        self.title = display_name(path) if self.key != "." else "Música"
        dirs, self.tracks = _entries(path)
        self.subfolders = [d for d in dirs if tracks_in(d, recursive=True)]


def music_folder(path=None, root=None):
    root = root or roots()[1]
    return Folder(root, path or root)


def playable_folders(root=None):
    """Todas as pastas com faixas, na ordem de navegação (para L1 e R1)."""
    root = root or roots()[1]
    found = []

    def walk(folder):
        dirs, files = _entries(folder)
        if files:
            found.append(folder)
        for sub in dirs:
            walk(sub)
    walk(root)
    return found
