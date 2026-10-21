"""O que está tocando: um livro ou uma fila de música, sobre o mpv.

O Vinyl toca um arquivo por vez e passa para o próximo sozinho no fim
(end-file com reason "eof"). Assim a posição é sempre (arquivo, segundos),
igual em qualquer versão do mpv, e retomar é carregar o arquivo com a opção
"start".
"""
import math
import random
import time

from . import texts
from .library import display_name

SAVE_EVERY = 15.0        # segundos entre gravações enquanto toca
RESTART_THRESHOLD = 3.0  # voltar capítulo/faixa depois disto volta ao começo dele
SPEED_MIN, SPEED_MAX, SPEED_STEP = 0.5, 3.0, 0.05
DUCK_VOLUME = 40         # volume do mpv enquanto a voz fala
FADE = 30.0              # o timer para dormir baixa o volume nestes últimos segundos
SLEEP_CHOICES = (15, 30, 45, 60)
SUSPEND_GAP = 5.0        # salto do relógio que denuncia uma suspensão


class Player:
    def __init__(self, mpv, store, say, keep_awake=None, now=time.monotonic, wall=time.time):
        self.mpv = mpv
        self.store = store
        self.say = say
        self.keep_awake = keep_awake or (lambda on: None)
        self.now = now
        self.wall = wall
        self.kind = None       # "book", "music" ou None
        self.title = ""
        self.files = []        # na ordem em que tocam
        self.index = 0
        self.paused = True
        self.book = None       # library.Book
        self.saved = None      # o dicionário do store que guarda a posição
        self.loaded = False    # o arquivo atual já abriu no mpv
        self.ducked = 0
        self.sleep_at = None   # quando o timer para dormir pausa (relógio monotônico)
        self.sleep_chapter = False
        self.last_save = 0.0
        self._volume = None
        self._awake = None
        self._clock_gap = None
        self._start_pos = 0.0
        for name in ("time-pos", "duration", "chapter", "chapter-list", "metadata"):
            mpv.observe(name)

    # --- propriedades do mpv -------------------------------------------
    @property
    def pos(self):
        value = self.mpv.props.get("time-pos")
        return float(value) if isinstance(value, (int, float)) and self.loaded else self._start_pos

    @property
    def duration(self):
        value = self.mpv.props.get("duration")
        return float(value) if isinstance(value, (int, float)) and self.loaded else None

    def _chapters(self):
        chapters = self.mpv.props.get("chapter-list") if self.loaded else None
        return chapters if isinstance(chapters, list) and len(chapters) > 1 else None

    # --- abrir ---------------------------------------------------------
    def open_book(self, book, play=True):
        self._close_current()
        self.kind = "book"
        self.book = book
        self.title = book.title
        self.files = list(book.files)
        self.saved = self.store.book(book.key)
        if self.saved.get("finished"):
            self.saved.update(file=0, pos=0.0, finished=False)
        index = self.saved["file"] if 0 <= self.saved["file"] < len(self.files) else 0
        self.store.data["last"] = {"kind": "book", "key": book.key}
        self.mpv.set("speed", self.saved["speed"])
        self._load(index, self.saved["pos"], play)

    def open_music(self, folder_key, files, start=0, shuffle=False, pos=0.0, play=True,
                   recursive=False, order=None, repeat=False):
        self._close_current()
        self.kind = "music"
        self.book = None
        self.title = display_name(folder_key) if folder_key != "." else "Música"
        self.base_files = list(files)
        if order is None or sorted(order) != list(range(len(files))):
            order = list(range(len(files)))
            if shuffle:
                rest = [i for i in order if i != start]
                random.shuffle(rest)
                order = [start] + rest
                start = 0
            else:
                order = list(range(len(files)))
        self.files = [self.base_files[i] for i in order]
        self.saved = {"folder": folder_key, "recursive": recursive, "shuffle": shuffle,
                      "repeat": repeat, "order": order, "track": start, "pos": pos}
        self.store.data["music"] = self.saved
        self.store.data["last"] = {"kind": "music", "key": folder_key}
        self.mpv.set("speed", 1.0)
        self._load(start, pos, play)

    def _load(self, index, pos=0.0, play=True):
        self.index = max(0, min(index, len(self.files) - 1))
        self._start_pos = max(0.0, float(pos or 0.0))
        self.loaded = False
        self.paused = not play
        self.mpv.props.pop("time-pos", None)
        self.mpv.props.pop("duration", None)
        self.mpv.set("pause", not play)
        self.mpv.set("start", "%.3f" % self._start_pos if self._start_pos > 0 else "none")
        self.mpv.command("loadfile", self.files[self.index], "replace")
        self._remember()
        self._update_awake()

    def _close_current(self):
        if self.kind:
            self.save()
        self.cancel_sleep(quiet=True)

    def stop(self):
        """Ao sair do app: pausa e grava."""
        if self.kind:
            self.mpv.set("pause", True)
            self.paused = True
            self.save()
        self._set_awake(False)

    # --- tocar e pausar ------------------------------------------------
    def toggle(self):
        if not self.kind:
            return
        self.paused = not self.paused
        self.mpv.set("pause", self.paused)
        if self.paused:
            self.save()
        self._update_awake()
        self.say("Pausado" if self.paused else "Tocando")

    def pause(self, announce=None):
        if self.kind and not self.paused:
            self.paused = True
            self.mpv.set("pause", True)
            self.save()
            self._update_awake()
        if announce:
            self.say(announce)

    # --- andar no tempo ------------------------------------------------
    def seek(self, delta):
        if not self.kind:
            return
        target = self.pos + delta
        durations = self._durations()
        index = self.index
        if target < 0:
            previous = durations.get(index - 1)
            if index > 0 and previous and self._chapters() is None:
                index, target = index - 1, max(0.0, previous + target)
            else:
                target = 0.0
        elif self.duration and target >= self.duration - 1:
            if index + 1 < len(self.files):
                index, target = index + 1, max(0.0, target - self.duration)
            else:
                target = max(0.0, self.duration - 1)
        if index != self.index:
            self._load(index, target, not self.paused)
        elif self.loaded:
            self.mpv.command("seek", target, "absolute")
        else:
            self._start_pos = target
        word = "Avançou" if delta > 0 else "Voltou"
        self.say("%s %s" % (word, texts.duration(abs(delta))))

    def chapter(self, step):
        """Capítulo (livro) ou faixa (música) seguinte ou anterior."""
        if not self.kind:
            return
        chapters = self._chapters() if self.kind == "book" else None
        if chapters:
            current = self.mpv.props.get("chapter") or 0
            start = chapters[current].get("time", 0) if 0 <= current < len(chapters) else 0
            if step < 0 and self.pos - start > RESTART_THRESHOLD:
                self.mpv.command("seek", start, "absolute")
                target = current
            else:
                target = current + step
                if not 0 <= target < len(chapters):
                    self.say("Último capítulo" if step > 0 else "Primeiro capítulo")
                    return
                self.mpv.command("seek", chapters[target].get("time", 0), "absolute")
            self.say(self._chapter_name(target, len(chapters), chapters[target].get("title")))
            return
        if step < 0 and self.pos > RESTART_THRESHOLD:
            target = self.index
        else:
            target = self.index + step
        if not 0 <= target < len(self.files):
            if self.kind == "music" and self.saved.get("repeat"):
                target %= len(self.files)
            else:
                if self.kind == "book":
                    self.say("Último capítulo" if step > 0 else "Primeiro capítulo")
                else:
                    self.say("Última faixa" if step > 0 else "Primeira faixa")
                return
        self._load(target, 0.0, not self.paused)
        self.say(self.item_name())

    def _chapter_name(self, index, total, title=None):
        text = "Capítulo %d de %d" % (index + 1, total)
        return text + (", " + title if title and not title.isdigit() else "")

    def item_name(self):
        if self.kind == "book":
            if len(self.files) > 1:
                return self._chapter_name(self.index, len(self.files), display_name(self.files[self.index]))
            chapters = self._chapters()
            if chapters:
                current = self.mpv.props.get("chapter") or 0
                return self._chapter_name(current, len(chapters), chapters[current].get("title"))
            return self.title
        return "Faixa %d de %d, %s" % (self.index + 1, len(self.files), self.track_title())

    def track_title(self):
        meta = self.mpv.props.get("metadata") if self.loaded else None
        meta = {str(k).lower(): v for k, v in meta.items()} if isinstance(meta, dict) else {}
        title = meta.get("title") or display_name(self.files[self.index])
        artist = meta.get("artist")
        return "%s, %s" % (title, artist) if artist else title

    # --- velocidade ----------------------------------------------------
    def change_speed(self, step):
        if self.kind != "book":
            return
        value = round(self.saved["speed"] + step, 2)
        value = max(SPEED_MIN, min(SPEED_MAX, value))
        self.saved["speed"] = value
        self.mpv.set("speed", value)
        self.say(texts.speed(value))

    def reset_speed(self):
        if self.kind == "book":
            self.saved["speed"] = 1.0
            self.mpv.set("speed", 1.0)
            self.say("Velocidade normal")

    # --- música --------------------------------------------------------
    def toggle_shuffle(self):
        if self.kind != "music":
            return
        current = self.saved["order"][self.index]
        shuffle = not self.saved["shuffle"]
        order = list(range(len(self.base_files)))
        if shuffle:
            rest = [i for i in order if i != current]
            random.shuffle(rest)
            order = [current] + rest
        self.saved.update(shuffle=shuffle, order=order)
        self.files = [self.base_files[i] for i in order]
        self.index = order.index(current)
        self._remember()
        self.say("Aleatório ligado" if shuffle else "Aleatório desligado")

    def toggle_repeat(self):
        if self.kind != "music":
            return
        self.saved["repeat"] = not self.saved["repeat"]
        self.say("Repetir ligado" if self.saved["repeat"] else "Repetir desligado")

    # --- marcadores ----------------------------------------------------
    def add_bookmark(self):
        if self.kind != "book":
            return
        mark = {"file": self.index, "pos": round(self.pos, 1)}
        marks = self.saved["bookmarks"]
        marks.append(mark)
        marks.sort(key=lambda m: (m["file"], m["pos"]))
        self.save()
        self.say("Marcador criado: " + self.bookmark_label(mark))

    def bookmark_label(self, mark):
        if len(self.files) > 1:
            return "capítulo %d, %s" % (mark["file"] + 1, texts.clock(mark["pos"]))
        return texts.clock(mark["pos"])

    def go_to_bookmark(self, mark):
        self._load(mark["file"], mark["pos"], not self.paused)
        self.say("No marcador: " + self.bookmark_label(mark))

    def delete_bookmark(self, mark, announce=True):
        marks = self.saved["bookmarks"]
        if mark in marks:
            marks.remove(mark)
            self.save()
            if announce:
                self.say("Marcador apagado")

    def go_to_chapter(self, index):
        chapters = self._chapters()
        if len(self.files) <= 1 and chapters:
            self.mpv.command("seek", chapters[index].get("time", 0), "absolute")
        else:
            self._load(index, 0.0, not self.paused)
        self.say(self.item_name() if len(self.files) > 1 else self._chapter_name(index, len(chapters)))

    def chapter_names(self):
        if self.kind != "book":
            return []
        if len(self.files) > 1:
            return [display_name(f) for f in self.files]
        return [c.get("title") or "Capítulo %d" % (i + 1) for i, c in enumerate(self._chapters() or [])]

    # --- onde está -----------------------------------------------------
    def _durations(self):
        if self.kind != "book":
            return {}
        return {int(k): v for k, v in self.saved["durations"].items()}

    def progress(self, saved=None, files=None):
        """Fração ouvida do livro, ou None se ainda faltam durações."""
        saved = saved or self.saved
        files = files or self.files
        durations = {int(k): v for k, v in saved.get("durations", {}).items()}
        if len(durations) < len(files) or not files:
            return None
        total = sum(durations.values())
        done = sum(durations[i] for i in range(saved["file"])) + saved["pos"]
        return done / total if total else None

    def position_text(self):
        if not self.kind:
            return "Nada tocando"
        parts = [self.item_name()]
        duration = self.duration
        if duration:
            parts.append("%s de %s" % (texts.clock(self.pos), texts.duration(duration)))
        else:
            parts.append(texts.clock(self.pos))
        if self.kind == "book":
            durations = self._durations()
            if len(durations) == len(self.files):
                done = sum(durations[i] for i in range(self.index)) + self.pos
                left = (sum(durations.values()) - done) / self.saved["speed"]
                parts.append("faltam %s no livro" % texts.duration(left))
            if self.saved["speed"] != 1.0:
                parts.append(texts.speed(self.saved["speed"]))
        if self.paused:
            parts.append("pausado")
        if self.sleep_at is not None or self.sleep_chapter:
            parts.append(self.sleep_text())
        return ". ".join(parts)

    # --- timer para dormir ---------------------------------------------
    def set_sleep(self, minutes=None, end_of_chapter=False):
        self.sleep_chapter = end_of_chapter
        self.sleep_at = self.now() + minutes * 60 if minutes else None
        self._apply_volume()
        if end_of_chapter:
            self.say("Timer: pausa no fim do capítulo" if self.kind == "book"
                     else "Timer: pausa no fim da faixa")
        elif minutes:
            self.say("Timer: pausa em %s" % texts.duration(minutes * 60))

    def cancel_sleep(self, quiet=False):
        was = self.sleep_at is not None or self.sleep_chapter
        self.sleep_at = None
        self.sleep_chapter = False
        self._apply_volume()
        if was and not quiet:
            self.say("Timer desligado")

    def sleep_text(self):
        if self.sleep_chapter:
            return "timer no fim do capítulo" if self.kind == "book" else "timer no fim da faixa"
        left = max(0, self.sleep_at - self.now())
        return "timer em %s" % texts.duration(math.ceil(left / 60) * 60 if left >= 60 else left)

    def _sleep_done(self):
        self.sleep_at = None
        self.sleep_chapter = False
        self.pause()
        self._apply_volume()
        self.say("Timer terminou. Pausado.")

    # --- volume (voz por cima e fim do timer) ----------------------------
    def duck(self, speaking):
        self.ducked = max(0, self.ducked + (1 if speaking else -1))
        self._apply_volume()

    def _apply_volume(self):
        volume = DUCK_VOLUME if self.ducked else 100
        if self.sleep_at is not None:
            left = self.sleep_at - self.now()
            if left < FADE:
                volume = volume * max(0.0, left) / FADE
        volume = int(round(volume))
        if volume != self._volume:
            self._volume = volume
            self.mpv.set("volume", volume)

    # --- manter acordado -----------------------------------------------
    def _update_awake(self):
        self._set_awake(bool(self.kind) and not self.paused)

    def _set_awake(self, on):
        if on != self._awake:
            self._awake = on
            self.keep_awake(on)

    # --- gravar --------------------------------------------------------
    def _remember(self):
        if self.kind == "book":
            self.saved["file"] = self.index
            self.saved["pos"] = round(self.pos, 1)
            if not self.paused:
                self.saved["finished"] = False
        elif self.kind == "music":
            self.saved["track"] = self.index
            self.saved["pos"] = round(self.pos, 1)

    def save(self):
        if self.kind:
            self._remember()
            self.store.save()
            self.last_save = self.now()

    # --- a cada quadro -------------------------------------------------
    def update(self):
        for event in self.mpv.poll():
            self._event(event)
        now = self.now()
        gap = self.wall() - now
        if self._clock_gap is not None and gap - self._clock_gap > SUSPEND_GAP:
            # o console suspendeu e voltou: o livro não sai falando no bolso
            self.pause()
        self._clock_gap = gap
        if self.sleep_at is not None:
            if now >= self.sleep_at:
                self._sleep_done()
            else:
                self._apply_volume()
        if self.kind and not self.paused and now - self.last_save >= SAVE_EVERY:
            self.save()

    def _event(self, event):
        name = event.get("event")
        if name == "file-loaded":
            self.loaded = True
            self.mpv.set("start", "none")
            self._record_duration()
        elif name == "property-change" and event.get("name") == "duration":
            self._record_duration()
        elif name == "end-file" and event.get("reason") in ("eof", "error"):
            if event.get("reason") == "error":
                self.say("Não consegui tocar %s" % display_name(self.files[self.index]))
            self._finished_file()
        elif name == "vinyl-closed":
            self.kind = None
            self._set_awake(False)
            self.say("O mpv fechou. Saia e abra o Vinyl de novo.")

    def _record_duration(self):
        if self.kind == "book" and self.duration:
            self.saved["durations"][str(self.index)] = round(self.duration, 1)

    def _finished_file(self):
        if not self.kind:
            return
        if self.sleep_chapter:
            following = self.index + 1 if self.index + 1 < len(self.files) else 0
            self.sleep_chapter = False
            self._load(following, 0.0, play=False)
            self.save()
            self.say("Timer terminou. Pausado.")
            self._update_awake()
            return
        if self.index + 1 < len(self.files):
            self._load(self.index + 1, 0.0, not self.paused)
            return
        if self.kind == "music" and self.saved.get("repeat"):
            self._load(0, 0.0, not self.paused)
            return
        self.paused = True
        self._update_awake()
        if self.kind == "book":
            self._load(0, 0.0, play=False)
            self.saved["finished"] = True
            self.store.save()
            self.say("Fim do livro")
        else:
            self._load(0, 0.0, play=False)
            self.save()
            self.say("Fim da pasta")
