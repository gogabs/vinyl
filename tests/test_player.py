import os
import unittest

from helpers import FakeMpv, tempdir, touch
from vinyl import library
from vinyl.player import Player
from vinyl.store import Store


class Clock:
    def __init__(self):
        self.t = 1000.0
        self.wall_offset = 0.0

    def now(self):
        return self.t

    def wall(self):
        return self.t + self.wall_offset


class PlayerTests(unittest.TestCase):
    def setUp(self):
        root = tempdir(self)
        self.save_dir = os.path.join(root, "saves")
        os.makedirs(self.save_dir)
        for i in (1, 2, 3):
            touch(os.path.join(root, "audiolivros", "Livro", "cap %d.mp3" % i))
        touch(os.path.join(root, "audiolivros", "Unico.m4b"))
        self.books = {b.key: b for b in library.books(os.path.join(root, "audiolivros"))}
        self.mpv = FakeMpv()
        self.said = []
        self.awake = []
        self.clock = Clock()
        self.store = Store(self.save_dir)
        self.player = Player(self.mpv, self.store, self.said.append, self.awake.append,
                             now=self.clock.now, wall=self.clock.wall)

    def open(self, key="Livro", duration=600.0, pos=0.0, **props):
        self.player.open_book(self.books[key])
        self.mpv.loaded(duration=duration, pos=pos, **props)
        self.player.update()

    def test_resumes_book_at_saved_chapter_position_and_speed(self):
        self.store.book("Livro").update(file=1, pos=754.2, speed=1.5)
        self.player.open_book(self.books["Livro"])
        self.assertEqual(self.mpv.last("loadfile")[1], self.books["Livro"].files[1])
        self.assertEqual(self.mpv.prop_sets("start")[-1], "754.200")
        self.assertEqual(self.mpv.prop_sets("speed")[-1], 1.5)
        self.assertEqual(self.mpv.prop_sets("pause")[-1], False)
        self.assertEqual(self.awake, [True])
        self.mpv.loaded(duration=900.0, pos=754.2)
        self.player.update()
        # depois de abrir, o próximo arquivo começa do zero
        self.assertEqual(self.mpv.prop_sets("start")[-1], "none")

    def test_pause_saves_and_releases_keep_awake(self):
        self.open(pos=42.0)
        self.player.toggle()
        self.assertEqual(self.said[-1], "Pausado")
        self.assertEqual(self.awake, [True, False])
        reloaded = Store(self.save_dir)
        self.assertEqual(reloaded.book("Livro")["pos"], 42.0)
        self.assertEqual(reloaded.data["last"], {"kind": "book", "key": "Livro"})

    def test_seek_inside_file_and_into_next_chapter(self):
        self.open(duration=600.0, pos=100.0)
        self.player.seek(30)
        self.assertEqual(self.mpv.last("seek"), ("seek", 130.0, "absolute"))
        self.assertEqual(self.said[-1], "Avançou 30 segundos")
        self.mpv.props["time-pos"] = 590.0
        self.player.seek(30)
        self.assertEqual(self.mpv.last("loadfile")[1], self.books["Livro"].files[1])
        self.assertEqual(self.mpv.prop_sets("start")[-1], "20.000")

    def test_seek_back_crosses_into_previous_chapter_when_its_length_is_known(self):
        self.store.book("Livro").update(file=1, pos=10.0, durations={"0": 500.0})
        self.player.open_book(self.books["Livro"])
        self.mpv.loaded(duration=600.0, pos=10.0)
        self.player.update()
        self.player.seek(-30)
        self.assertEqual(self.mpv.last("loadfile")[1], self.books["Livro"].files[0])
        self.assertEqual(self.mpv.prop_sets("start")[-1], "480.000")

    def test_previous_chapter_restarts_current_one_first(self):
        self.store.book("Livro").update(file=1, pos=200.0)
        self.player.open_book(self.books["Livro"])
        self.mpv.loaded(duration=600.0, pos=200.0)
        self.player.update()
        self.player.chapter(-1)
        self.assertEqual(self.mpv.last("loadfile")[1], self.books["Livro"].files[1])
        self.assertEqual(self.said[-1], "Capítulo 2 de 3, cap 2")
        self.mpv.loaded(duration=600.0, pos=1.0)
        self.player.update()
        self.player.chapter(-1)
        self.assertEqual(self.mpv.last("loadfile")[1], self.books["Livro"].files[0])
        self.player.chapter(-1)
        self.assertEqual(self.said[-1], "Primeiro capítulo")

    def test_embedded_chapters_of_single_file(self):
        chapters = [{"title": "Abertura", "time": 0.0}, {"title": "O Alienista", "time": 300.0},
                    {"title": "Fim", "time": 900.0}]
        self.open("Unico.m4b", duration=1200.0, pos=310.0, chapter=1, chapter_list=chapters)
        self.player.chapter(1)
        self.assertEqual(self.mpv.last("seek"), ("seek", 900.0, "absolute"))
        self.assertEqual(self.said[-1], "Capítulo 3 de 3, Fim")
        self.player.chapter(-1)   # 10 s dentro do capítulo 2: volta ao começo dele
        self.assertEqual(self.mpv.last("seek"), ("seek", 300.0, "absolute"))
        self.assertEqual(self.player.chapter_names(), ["Abertura", "O Alienista", "Fim"])

    def test_speed_steps_and_limits(self):
        self.open()
        self.player.change_speed(0.05)
        self.assertEqual(self.said[-1], "1,05 vezes")
        for _ in range(100):
            self.player.change_speed(0.05)
        self.assertEqual(self.mpv.prop_sets("speed")[-1], 3.0)
        self.player.reset_speed()
        self.assertEqual(self.mpv.prop_sets("speed")[-1], 1.0)

    def test_bookmarks_are_sorted_saved_and_deleted(self):
        self.open(pos=125.0)
        self.player.add_bookmark()
        self.assertEqual(self.said[-1], "Marcador criado: capítulo 1, 2 minutos")
        self.mpv.props["time-pos"] = 20.0
        self.player.add_bookmark()
        marks = Store(self.save_dir).book("Livro")["bookmarks"]
        self.assertEqual(marks, [{"file": 0, "pos": 20.0}, {"file": 0, "pos": 125.0}])
        self.player.go_to_bookmark(marks[1])
        self.assertEqual(self.mpv.prop_sets("start")[-1], "125.000")
        self.player.delete_bookmark(self.player.saved["bookmarks"][0])
        self.assertEqual(len(Store(self.save_dir).book("Livro")["bookmarks"]), 1)

    def test_end_of_file_plays_next_and_end_of_book_resets(self):
        self.open()
        self.mpv.events.append({"event": "end-file", "reason": "eof"})
        self.player.update()
        self.assertEqual(self.mpv.last("loadfile")[1], self.books["Livro"].files[1])
        self.player._load(2)
        self.mpv.loaded(duration=10.0)
        self.mpv.events.append({"event": "end-file", "reason": "eof"})
        self.player.update()
        self.assertEqual(self.said[-1], "Fim do livro")
        self.assertTrue(Store(self.save_dir).book("Livro")["finished"])
        self.assertEqual(self.awake[-1], False)
        self.player.open_book(self.books["Livro"])  # abrir de novo começa do início
        self.assertEqual(self.mpv.last("loadfile")[1], self.books["Livro"].files[0])

    def test_replacing_a_file_is_not_an_end(self):
        self.open()
        self.mpv.events.append({"event": "end-file", "reason": "stop"})
        self.player.update()
        self.assertEqual(self.player.index, 0)

    def test_sleep_timer_fades_and_pauses(self):
        self.open()
        self.player.set_sleep(15)
        self.assertEqual(self.said[-1], "Timer: pausa em 15 minutos")
        self.clock.t += 15 * 60 - 15   # faltam 15 s: metade do volume
        self.player.update()
        self.assertEqual(self.mpv.prop_sets("volume")[-1], 50)
        self.clock.t += 16
        self.player.update()
        self.assertEqual(self.said[-1], "Timer terminou. Pausado.")
        self.assertTrue(self.player.paused)
        self.assertEqual(self.mpv.prop_sets("volume")[-1], 100)
        self.assertEqual(self.awake[-1], False)

    def test_sleep_at_end_of_chapter_stops_on_next_chapter(self):
        self.open()
        self.player.set_sleep(end_of_chapter=True)
        self.mpv.events.append({"event": "end-file", "reason": "eof"})
        self.player.update()
        self.assertEqual(self.mpv.last("loadfile")[1], self.books["Livro"].files[1])
        self.assertEqual(self.mpv.prop_sets("pause")[-1], True)
        self.assertEqual(Store(self.save_dir).book("Livro")["file"], 1)

    def test_voice_lowers_the_audio_while_speaking(self):
        self.open()
        self.player.duck(True)
        self.assertEqual(self.mpv.prop_sets("volume")[-1], 40)
        self.player.duck(False)
        self.assertEqual(self.mpv.prop_sets("volume")[-1], 100)

    def test_suspend_pauses_on_resume(self):
        self.open()
        self.clock.wall_offset += 3600   # o relógio de parede andou, o monotônico não
        self.player.update()
        self.assertTrue(self.player.paused)

    def test_position_text_with_all_lengths_known(self):
        self.store.book("Livro").update(durations={"0": 600.0, "1": 600.0, "2": 600.0}, speed=2.0)
        self.open(duration=600.0, pos=300.0)
        self.assertEqual(self.player.position_text(),
                         "Capítulo 1 de 3, cap 1. 5 minutos de 10 minutos. "
                         "faltam 12 minutos no livro. 2 vezes")
        self.assertAlmostEqual(self.player.progress(), 300 / 1800)

    def test_periodic_save_while_playing(self):
        self.open(pos=10.0)
        self.mpv.props["time-pos"] = 30.0
        self.clock.t += 16
        self.player.update()
        self.assertEqual(Store(self.save_dir).book("Livro")["pos"], 30.0)


class MusicTests(PlayerTests.__bases__[0]):
    def setUp(self):
        self.mpv = FakeMpv()
        self.said = []
        self.store = Store(tempdir(self))
        self.player = Player(self.mpv, self.store, self.said.append)
        self.files = ["/m/a.mp3", "/m/b.mp3", "/m/c.mp3", "/m/d.mp3"]

    def test_shuffle_keeps_current_track_first(self):
        self.player.open_music("Rock", self.files, start=2, shuffle=True)
        self.assertEqual(self.mpv.last("loadfile")[1], "/m/c.mp3")
        self.assertEqual(sorted(self.player.files), self.files)
        self.assertEqual(self.player.saved["order"][0], 2)

    def test_toggle_shuffle_and_repeat_wraps(self):
        self.player.open_music("Rock", self.files, start=1)
        self.mpv.loaded(duration=200.0, metadata={"title": "Bê", "ARTIST": "Banda"})
        self.player.update()
        self.assertEqual(self.player.item_name(), "Faixa 2 de 4, Bê, Banda")
        self.player.toggle_shuffle()
        self.assertEqual(self.player.files[self.player.index], "/m/b.mp3")
        self.player.toggle_shuffle()
        self.assertEqual(self.player.files, self.files)
        self.player.toggle_repeat()
        self.player._load(3)
        self.player.chapter(1)
        self.assertEqual(self.mpv.last("loadfile")[1], "/m/a.mp3")

    def test_end_of_folder_stops_without_repeat(self):
        self.player.open_music("Rock", self.files, start=3)
        self.mpv.events.append({"event": "end-file", "reason": "eof"})
        self.player.update()
        self.assertEqual(self.said[-1], "Fim da pasta")
        self.assertTrue(self.player.paused)


if __name__ == "__main__":
    unittest.main()
