"""Com o mpv de verdade (saída nula): o livro toca, passa de capítulo e retoma."""
import os
import time
import unittest
from unittest.mock import patch

from helpers import silence, tempdir
from vinyl import library, mpv
from vinyl.player import Player
from vinyl.store import Store


@unittest.skipUnless(mpv.available(), "mpv não instalado")
class RealMpvTests(unittest.TestCase):
    def setUp(self):
        root = tempdir(self)
        env = patch.dict(os.environ, {"VINYL_AO": "null", "XDG_RUNTIME_DIR": root})
        env.start()
        self.addCleanup(env.stop)
        books = os.path.join(root, "audiolivros")
        silence(os.path.join(books, "Livro", "1.wav"), 1.0)
        silence(os.path.join(books, "Livro", "2.wav"), 3.0)
        self.book = library.books(books)[0]
        self.store = Store(root)
        self.mpv = mpv.Mpv()
        self.mpv.start()
        self.addCleanup(self.mpv.stop)
        self.said = []
        self.player = Player(self.mpv, self.store, self.said.append)

    def wait(self, condition, seconds=8.0):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.player.update()
            if condition():
                return True
            time.sleep(0.02)
        return False

    def test_plays_through_chapters_at_double_speed_and_saves(self):
        self.player.open_book(self.book)
        self.player.change_speed(1.0)   # 2x
        self.assertTrue(self.wait(lambda: self.player.index == 1 and self.player.loaded))
        self.assertTrue(self.wait(lambda: self.player.pos > 0.8))
        self.player.toggle()
        saved = Store(self.store.path.rsplit(os.sep, 1)[0]).book("Livro")
        self.assertEqual(saved["file"], 1)
        self.assertGreaterEqual(saved["pos"], 0.8)
        self.assertEqual(saved["durations"]["0"], 1.0)

    def test_resume_starts_inside_the_file(self):
        self.store.book("Livro").update(file=1, pos=2.0)
        self.player.open_book(self.book)
        self.assertTrue(self.wait(lambda: self.player.loaded and self.player.pos >= 2.0))
        self.assertLess(self.player.pos, 2.9)

    def test_end_of_book(self):
        self.store.book("Livro").update(file=1, pos=2.5)
        self.player.open_book(self.book)
        self.assertTrue(self.wait(lambda: "Fim do livro" in self.said))


if __name__ == "__main__":
    unittest.main()
