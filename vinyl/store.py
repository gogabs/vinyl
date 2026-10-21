"""Onde parou: um JSON só em A11Y_SAVE_DIR.

{
  "last": {"kind": "book", "key": "Dom Casmurro"},
  "books": {"Dom Casmurro": {"file": 2, "pos": 754.2, "speed": 1.25,
                              "durations": {"0": 1830.5},
                              "bookmarks": [{"file": 1, "pos": 300.0}]}},
  "music": {"folder": "Rock/Album", "track": 3, "pos": 12.0,
            "shuffle": false, "repeat": false, "order": [3, 0, 1, 2]}
}

A EASYROMS é exFAT: grava num arquivo temporário e troca com os.replace,
para um desligamento no meio da gravação não perder tudo.
"""
import json
import os

FILE = "vinyl.json"


class Store:
    def __init__(self, folder):
        self.path = os.path.join(folder, FILE)
        self.data = {"last": None, "books": {}, "music": None}
        try:
            with open(self.path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass

    def book(self, key):
        book = self.data["books"].setdefault(key, {})
        book.setdefault("file", 0)
        book.setdefault("pos", 0.0)
        book.setdefault("speed", 1.0)
        book.setdefault("durations", {})
        book.setdefault("bookmarks", [])
        return book

    def save(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass
