import os
import unittest

from helpers import tempdir, touch
from vinyl import library


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.root = tempdir(self)
        self.books = os.path.join(self.root, "audiolivros")
        self.music = os.path.join(self.root, "musica")

    def test_natural_order_puts_2_before_10(self):
        names = ["Capitulo 10.mp3", "Capitulo 2.mp3", "capitulo 1.mp3"]
        self.assertEqual(sorted(names, key=library.natural_key),
                         ["capitulo 1.mp3", "Capitulo 2.mp3", "Capitulo 10.mp3"])

    def test_book_is_folder_with_subfolders_in_order_or_single_file(self):
        touch(os.path.join(self.books, "Dom Casmurro", "CD 2", "01.mp3"))
        touch(os.path.join(self.books, "Dom Casmurro", "CD 1", "02.mp3"))
        touch(os.path.join(self.books, "Dom Casmurro", "CD 1", "01.mp3"))
        touch(os.path.join(self.books, "Dom Casmurro", "capa.jpg"))
        touch(os.path.join(self.books, "O_Alienista.m4b"))
        touch(os.path.join(self.books, "Vazio", "leia.txt"))
        books = library.books(self.books)
        self.assertEqual([b.title for b in books], ["Dom Casmurro", "O Alienista"])
        self.assertEqual([os.path.relpath(f, books[0].path) for f in books[0].files],
                         ["CD 1/01.mp3", "CD 1/02.mp3", "CD 2/01.mp3"])
        self.assertEqual(books[1].key, "O_Alienista.m4b")

    def test_music_lists_only_folders_with_tracks(self):
        touch(os.path.join(self.music, "Rock", "Album", "1.flac"))
        touch(os.path.join(self.music, "Rock", "solta.mp3"))
        touch(os.path.join(self.music, "Fotos", "a.jpg"))
        root = library.music_folder(root=self.music)
        self.assertEqual([os.path.basename(s) for s in root.subfolders], ["Rock"])
        self.assertEqual(root.title, "Música")
        self.assertEqual([os.path.relpath(f, self.music) for f in library.playable_folders(self.music)],
                         ["Rock", "Rock/Album"])


if __name__ == "__main__":
    unittest.main()
