"""As telas: biblioteca, reprodução e opções, com o Game do Mage Core sem laço."""
import os
import unittest
from unittest.mock import patch

from helpers import FakeMpv, tempdir, touch

import r36s_a11y as a11y
from vinyl.app import App
from vinyl.store import Store


class AppTests(unittest.TestCase):
    def setUp(self):
        root = tempdir(self)
        self.root = root
        env = patch.dict(os.environ, {
            "A11Y_FALA": "terminal", "A11Y_PLATAFORMA": "", "A11Y_SAVE_DIR": os.path.join(root, "saves"),
            "A11Y_HISTORICO_FALAS": os.path.join(root, "h.txt"),
            "A11Y_REPRODUZINDO": os.path.join(root, "a11y-reproduzindo"),
            "VINYL_AUDIOLIVROS": os.path.join(root, "audiolivros"),
            "VINYL_MUSICA": os.path.join(root, "musica")})
        env.start()
        self.addCleanup(env.stop)
        for i in (1, 2):
            touch(os.path.join(root, "audiolivros", "Dom Casmurro", "%02d.mp3" % i))
        touch(os.path.join(root, "musica", "Rock", "a.mp3"))
        touch(os.path.join(root, "musica", "Rock", "b.mp3"))
        touch(os.path.join(root, "musica", "Jazz", "c.mp3"))
        self.game = a11y.Game(fps=10, repeat=True)
        self.said = []
        self.game.speech.say = lambda text, queue=False, on_done=None: self.said.append(text)
        self.mpv = FakeMpv()
        self.app = App(self.game, mpv=self.mpv)
        self.app.start()

    def press(self, *buttons):
        for b in buttons:
            self.game._dispatch_button(b, a11y.DOWN, 0)

    def flag(self):
        return os.path.exists(os.environ["A11Y_REPRODUZINDO"])

    def test_open_book_from_library_and_control_it(self):
        self.assertTrue(self.said[-1].startswith("Vinyl. Audiolivros, 1 de 2"))
        self.press("b")
        self.assertEqual(self.said[-1], "Audiolivros. Dom Casmurro, novo, 1 de 1")
        self.press("b")
        self.assertTrue(self.said[-1].startswith("Dom Casmurro. Capítulo 1 de 2. B toca e pausa"))
        self.assertTrue(self.flag())
        self.press("up")
        self.assertEqual(self.said[-1], "1,05 vezes")
        self.press("r1")
        self.assertTrue(self.mpv.last("loadfile")[1].endswith("02.mp3"))
        self.press("x")
        self.assertEqual(self.said[-1], "Marcador criado: capítulo 2, começo")
        self.press("b")
        self.assertEqual(self.said[-1], "Pausado")
        self.assertFalse(self.flag())
        self.press("a")
        self.assertTrue(self.said[-1].startswith("Vinyl. Tocando agora: Dom Casmurro, 1 de 3"))
        self.press("b")   # volta à reprodução
        self.press("y")
        self.assertTrue(self.said[-1].startswith("Marcadores. capítulo 2, começo, 1 de 1"))
        self.press("x")
        self.assertEqual(self.said[-1], "Marcador apagado. Não sobrou nenhum.")

    def test_start_opens_options_and_sleep_timer(self):
        self.press("b", "b")
        self.press("start")
        self.assertTrue(self.said[-1].startswith("Opções. Timer para dormir, 1 de 5"))
        self.press("b")
        self.press("down", "b")   # 30 minutos
        self.assertEqual(self.said[-1], "Timer: pausa em 30 minutos")
        self.press("select")
        self.assertIn("timer em 30 minutos", self.said[-1])

    def test_continue_from_last_session(self):
        store = Store(os.environ["A11Y_SAVE_DIR"])
        store.data["last"] = {"kind": "book", "key": "Dom Casmurro"}
        store.book("Dom Casmurro").update(file=1, pos=90.0)
        store.save()
        app = App(self.game, mpv=FakeMpv())
        app.start()
        self.assertTrue(self.said[-1].startswith("Vinyl. Continuar: Dom Casmurro, 1 de 3"))
        self.press("b")
        self.assertTrue(app.mpv.last("loadfile")[1].endswith("02.mp3"))

    def test_music_folders_and_folder_jump(self):
        self.press("down", "b")
        self.assertTrue(self.said[-1].startswith("Música. Tocar tudo, 1 de 4"))
        self.press("down", "down", "b")      # Pasta Jazz
        self.assertTrue(self.said[-1].startswith("Jazz. Tocar tudo"))
        self.press("down", "down", "b")      # a faixa c
        self.assertTrue(self.mpv.last("loadfile")[1].endswith("c.mp3"))
        self.press("r1")
        self.assertTrue(self.said[-1].startswith("Pasta Rock. Faixa 1 de 2, a"))
        self.press("up")
        self.assertEqual(self.said[-1], "Aleatório ligado")

    def test_back_in_music_returns_to_the_folder_item(self):
        self.press("down", "b", "down", "down", "down", "b")   # Pasta Rock
        self.press("a")
        self.assertTrue(self.said[-1].startswith("Música. Pasta Rock, 4 de 4"))

    def test_quit_pauses_and_clears_flag(self):
        self.press("b", "b")
        self.app.quit()
        self.assertFalse(self.flag())
        self.assertEqual(self.mpv.prop_sets("pause")[-1], True)


class MissingMpvTests(unittest.TestCase):
    def test_says_mpv_is_missing(self):
        root = tempdir(self)
        with patch.dict(os.environ, {"A11Y_FALA": "terminal", "A11Y_SAVE_DIR": root,
                                     "A11Y_HISTORICO_FALAS": os.path.join(root, "h.txt"),
                                     "VINYL_MPV": "nao-existe-mpv"}):
            game = a11y.Game()
            said = []
            game.speech.say = lambda text, queue=False, on_done=None: said.append(text)
            App(game).start()
        self.assertTrue(said[-1].startswith("O Vinyl precisa do mpv"))


if __name__ == "__main__":
    unittest.main()
