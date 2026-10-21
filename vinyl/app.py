"""As telas do Vinyl: biblioteca falada e a tela de reprodução."""
import os

from r36s_a11y import DOWN, REPEAT, Menu

from . import awake, library, mpv as mpv_mod
from .player import SLEEP_CHOICES, SPEED_STEP, Player
from .store import Store

SKIP = 30           # esquerda e direita no livro, L2 e R2 na música
BIG_SKIP = 300      # L2 e R2 no livro

BOOK_HELP = ("B toca e pausa. Esquerda e direita, 30 segundos. L2 e R2, 5 minutos. "
             "L1 e R1, capítulo. Cima e baixo, velocidade. X cria marcador, Y lista os marcadores. "
             "Select fala a posição. Start abre as opções. A volta à biblioteca sem parar.")
MUSIC_HELP = ("B toca e pausa. Esquerda e direita, faixa. L2 e R2, 30 segundos. "
              "L1 e R1, pasta. Cima liga o aleatório, baixo liga o repetir. "
              "Select fala a faixa. Start abre as opções. A volta à biblioteca sem parar.")


class BookmarkMenu(Menu):
    HELP = "Cima e baixo escolhem. B vai ao marcador. X apaga. A volta."

    def __init__(self, game, title, items, on_select, on_back, on_delete):
        Menu.__init__(self, game, title, items, on_select, on_back)
        self.on_delete = on_delete

    def handle_button(self, button, state, ms):
        if button == "x" and state == DOWN:
            self.on_delete(self.index)
        else:
            Menu.handle_button(self, button, state, ms)


class NowPlaying:
    """A tela de reprodução: recebe os botões enquanto está em foco."""

    def __init__(self, app):
        self.app = app

    def handle_button(self, button, state, ms):
        if state not in (DOWN, REPEAT):
            return
        player = self.app.player
        book = player.kind == "book"
        repeatable = {"left", "right", "up", "down", "l2", "r2"} if book else {"l2", "r2"}
        if state == REPEAT and button not in repeatable:
            return
        if button == "b":
            player.toggle()
        elif button in ("left", "right"):
            sign = 1 if button == "right" else -1
            player.seek(sign * SKIP) if book else player.chapter(sign)
        elif button in ("l2", "r2"):
            sign = 1 if button == "r2" else -1
            player.seek(sign * (BIG_SKIP if book else SKIP))
        elif button in ("l1", "r1"):
            sign = 1 if button == "r1" else -1
            player.chapter(sign) if book else self.app.next_folder(sign)
        elif button in ("up", "down"):
            if book:
                player.change_speed(SPEED_STEP if button == "up" else -SPEED_STEP)
            elif button == "up":
                player.toggle_shuffle()
            else:
                player.toggle_repeat()
        elif button == "x" and book:
            player.add_bookmark()
        elif button == "y" and book:
            self.app.bookmarks_menu()
        elif button == "select":
            self.app.say(player.position_text())
        elif button == "start":
            self.app.options_menu()
        elif button == "a":
            self.app.leave_now_playing()


class App:
    def __init__(self, game, mpv=None):
        self.game = game
        self.mpv = mpv
        self.player = None
        self.menu = None
        self.now_playing = NowPlaying(self)
        self.playing_focus = False
        self.music_trail = []     # [(pasta, índice escolhido)] da raiz até a pasta aberta
        self.store = Store(game.save_dir)
        self._say = game.say
        game.say = self.say       # os menus do Mage Core também abaixam o som
        game.on_start(self.start)
        game.on_update(lambda dt: self.player and self.player.update())
        game.on_quit(self.quit)

    # --- fala por cima do som ------------------------------------------
    def say(self, text, queue=False, on_done=None):
        player = self.player
        if player is None:
            self._say(text, queue=queue, on_done=on_done)
            return
        player.duck(True)

        def done(finished):
            player.duck(False)
            if on_done:
                on_done(finished)
        self._say(text, queue=queue, on_done=done)

    # --- ciclo de vida -------------------------------------------------
    def start(self):
        if self.mpv is None:
            if not mpv_mod.available():
                self.missing_mpv()
                return
            self.mpv = mpv_mod.Mpv()
            try:
                self.mpv.start()
            except mpv_mod.MpvError:
                self.missing_mpv()
                return
        self.player = Player(self.mpv, self.store, self.say, awake.for_game(self.game))
        self.main_menu()

    def missing_mpv(self):
        self.mpv = None
        menu = Menu(self.game, "O Vinyl precisa do mpv, que não está instalado neste console",
                    ["Sair"], lambda i, t: self.game.quit(), self.game.quit)
        self._show(menu)

    def quit(self):
        if self.player:
            self.player.stop()
        if self.mpv:
            self.mpv.stop()

    # --- navegação -----------------------------------------------------
    def _show(self, menu, index=0, help=True):
        self._hide()
        self.menu = menu
        if menu.items:
            menu.open(index=min(index, len(menu.items) - 1), announce_help=help)

    def _hide(self):
        if self.menu is not None and self.menu.is_open:
            self.menu.close()
        self.menu = None
        if self.playing_focus:
            self.game.pop_focus(self.now_playing)
            self.playing_focus = False

    def show_now_playing(self, announce=True):
        self._hide()
        self.game.push_focus(self.now_playing)
        self.playing_focus = True
        if announce:
            help = BOOK_HELP if self.player.kind == "book" else MUSIC_HELP
            self.say("%s. %s. %s" % (self.player.title, self.player.item_name(), help))

    def leave_now_playing(self):
        self.main_menu()

    # --- biblioteca ----------------------------------------------------
    def main_menu(self, index=0):
        items, actions = [], []
        if self.player.kind:
            items.append("Tocando agora: " + self.player.title)
            actions.append(self.show_now_playing)
        else:
            resume = self._resume_action()
            if resume:
                items.append("Continuar: " + resume[0])
                actions.append(resume[1])
        items += ["Audiolivros", "Música"]
        actions += [self.books_menu, lambda: self.music_menu(None)]
        menu = Menu(self.game, "Vinyl", items,
                    lambda i, t: actions[i](), self.game.quit)
        menu.HELP = "Cima e baixo escolhem. B confirma. A sai do Vinyl."
        self._show(menu, index)

    def _resume_action(self):
        last = self.store.data.get("last") or {}
        if last.get("kind") == "book":
            for book in library.books():
                if book.key == last.get("key"):
                    return book.title, lambda: self.open_book(book)
        elif last.get("kind") == "music" and self.store.data.get("music"):
            saved = self.store.data["music"]
            path = self._music_path(saved.get("folder", "."))
            files = library.tracks_in(path, recursive=bool(saved.get("recursive")))
            if files:
                return (library.display_name(path) if saved.get("folder") != "." else "Música",
                        lambda: self._resume_music(saved, files))
        return None

    def _resume_music(self, saved, files):
        self.player.open_music(saved.get("folder", "."), files, start=saved.get("track", 0),
                               shuffle=saved.get("shuffle", False), pos=saved.get("pos", 0.0),
                               recursive=saved.get("recursive", False), order=saved.get("order"),
                               repeat=saved.get("repeat", False))
        self.show_now_playing()

    def book_status(self, book):
        saved = self.store.data["books"].get(book.key)
        if not saved:
            return "novo"
        if saved.get("finished"):
            return "terminado"
        fraction = self.player.progress(saved, book.files)
        if fraction is not None:
            return "%d%% ouvido" % int(fraction * 100)
        if len(book.files) > 1:
            return "capítulo %d de %d" % (saved.get("file", 0) + 1, len(book.files))
        return "começado"

    def books_menu(self, index=0):
        books = library.books()
        if not books:
            self.say("Nenhum audiolivro. Copie os livros para a pasta audiolivros do cartão, "
                     "uma pasta por livro.")
            return
        items = ["%s, %s" % (b.title, self.book_status(b)) for b in books]
        menu = Menu(self.game, "Audiolivros", items,
                    lambda i, t: self.open_book(books[i]),
                    lambda: self.main_menu(1 if self.player.kind or self._resume_action() else 0))
        self._show(menu, index, help=False)

    def open_book(self, book):
        self.player.open_book(book)
        self.show_now_playing()

    def _music_path(self, key):
        root = library.roots()[1]
        return root if key in (None, ".") else os.path.join(root, key)

    def music_menu(self, path, index=0):
        folder = library.music_folder(path)
        everything = library.tracks_in(folder.path, recursive=True)
        if not everything:
            self.say("Nenhuma música. Copie as músicas para a pasta musica do cartão.")
            return
        if path is None:
            self.music_trail = []
        items = ["Tocar tudo", "Tocar tudo em ordem aleatória"]
        actions = [lambda: self.play_folder(folder, everything, 0, recursive=True),
                   lambda: self.play_folder(folder, everything, 0, shuffle=True, recursive=True)]
        for i, sub in enumerate(folder.subfolders):
            items.append("Pasta " + library.display_name(sub))
            actions.append(lambda sub=sub, i=i: self.enter_folder(folder.path, i + 2, sub))
        for i, track in enumerate(folder.tracks):
            items.append(library.display_name(track))
            actions.append(lambda i=i: self.play_folder(folder, folder.tracks, i))
        menu = Menu(self.game, folder.title, items, lambda i, t: actions[i](), self.music_back)
        self._show(menu, index, help=False)

    def enter_folder(self, parent, index, sub):
        self.music_trail.append((parent, index))
        self.music_menu(sub)

    def music_back(self):
        if self.music_trail:
            parent, index = self.music_trail.pop()
            self.music_menu(parent if parent != library.roots()[1] else None, index)
            if parent == library.roots()[1]:
                self.music_trail = []
        else:
            self.main_menu(2 if self.player.kind or self._resume_action() else 1)

    def play_folder(self, folder, files, start, shuffle=False, recursive=False):
        self.player.open_music(folder.key, files, start=start, shuffle=shuffle, recursive=recursive)
        self.show_now_playing()

    def next_folder(self, step):
        folders = library.playable_folders()
        current = self._music_path(self.player.saved.get("folder"))
        paths = [os.path.normpath(f) for f in folders]
        here = os.path.normpath(current)
        if here in paths:
            target = paths.index(here) + step
        else:
            target = 0 if step > 0 else len(paths) - 1
        if not 0 <= target < len(folders):
            self.say("Última pasta" if step > 0 else "Primeira pasta")
            return
        folder = library.music_folder(folders[target])
        self.player.open_music(folder.key, folder.tracks, 0,
                               shuffle=self.player.saved.get("shuffle", False),
                               repeat=self.player.saved.get("repeat", False),
                               play=not self.player.paused)
        self.say("Pasta %s. %s" % (folder.title, self.player.item_name()))

    # --- menus da reprodução -------------------------------------------
    def options_menu(self):
        player = self.player
        items, actions = ["Timer para dormir"], [self.sleep_menu]
        if player.kind == "book":
            items += ["Ir para capítulo", "Marcadores", "Velocidade normal"]
            actions += [self.chapters_menu, self.bookmarks_menu,
                        lambda: (player.reset_speed(), self.show_now_playing(False))]
        else:
            items += ["Aleatório " + ("ligado" if player.saved["shuffle"] else "desligado"),
                      "Repetir " + ("ligado" if player.saved["repeat"] else "desligado")]
            actions += [lambda: (player.toggle_shuffle(), self.show_now_playing(False)),
                        lambda: (player.toggle_repeat(), self.show_now_playing(False))]
        items.append("Voltar à biblioteca")
        actions.append(self.main_menu)
        menu = Menu(self.game, "Opções", items, lambda i, t: actions[i](), self._back_to_player)
        self._show(menu, help=False)

    def _back_to_player(self):
        self.show_now_playing(False)
        self.say(self.player.title)

    def sleep_menu(self):
        player = self.player
        items, actions = [], []
        if player.sleep_at is not None or player.sleep_chapter:
            items.append("Desligar o timer, " + player.sleep_text())
            actions.append(player.cancel_sleep)
        for minutes in SLEEP_CHOICES:
            items.append("%d minutos" % minutes)
            actions.append(lambda m=minutes: player.set_sleep(m))
        items.append("Fim do capítulo" if player.kind == "book" else "Fim da faixa")
        actions.append(lambda: player.set_sleep(end_of_chapter=True))

        def chosen(i, text):
            self.show_now_playing(False)
            actions[i]()
        menu = Menu(self.game, "Timer para dormir", items, chosen, self._back_to_player)
        self._show(menu, help=False)

    def chapters_menu(self):
        names = self.player.chapter_names()
        if len(names) < 2:
            self.say("Este livro não tem capítulos")
            return
        current = self.player.index if len(self.player.files) > 1 else (
            self.mpv.props.get("chapter") or 0)

        def chosen(i, text):
            self.show_now_playing(False)
            self.player.go_to_chapter(i)
        items = ["%d. %s" % (i + 1, n) for i, n in enumerate(names)]
        self._show(Menu(self.game, "Capítulos", items, chosen, self._back_to_player),
                   current, help=False)

    def bookmarks_menu(self, index=0, title="Marcadores"):
        player = self.player
        marks = list(player.saved["bookmarks"])
        if not marks:
            self.show_now_playing(False)
            self.say("Nenhum marcador. X cria um aqui.")
            return
        items = [player.bookmark_label(m) for m in marks]

        def chosen(i, text):
            self.show_now_playing(False)
            player.go_to_bookmark(marks[i])

        def delete(i):
            player.delete_bookmark(marks[i], announce=False)
            if player.saved["bookmarks"]:
                self.bookmarks_menu(max(0, i - 1), "Marcador apagado. Marcadores")
            else:
                self.show_now_playing(False)
                self.say("Marcador apagado. Não sobrou nenhum.")
        self._show(BookmarkMenu(self.game, title, items, chosen, self._back_to_player, delete),
                   index, help=title == "Marcadores")
