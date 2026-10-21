"""Som num ouvido só, pela SDL2_mixer, para jogos em dupla (modo dueto).

No dueto cada jogador fica com um lado do fone. O áudio 3D (Audio, pela
OpenAL com HRTF) imita uma cabeça e por isso um som "à esquerda" também chega,
mais baixo, ao ouvido direito. Aqui não: cada som vai para o canal esquerdo,
para o direito ou para os dois, sem vazar.

    ears = game.ears
    remo = ears.load("remo", "sounds/remo.wav")       # WAV ou OGG
    voz = remo.play(ear="left", volume=0.8)            # "left", "right" ou "both"
    voz.set_ear("right"); voz.set_volume(0.3, fade=0.5); voz.stop(fade=0.2)
    ears.swap = True                                   # troca os lados de tudo

Toca junto com game.sound e com a fala (todos passam pelo dmix do ALSA no
console). Sem a SDL2_mixer, cai para game.sound com pan -1/1 e avisa: o jogo
continua, mas o som vaza para o outro ouvido.
"""
import ctypes
import os
import sys

from . import native
from .audio import sound_file

SDL_INIT_AUDIO = 0x10
AUDIO_S16SYS = 0x8010 if sys.byteorder == "little" else 0x9010
MIX_MAX_VOLUME = 128
CHANNELS = 32

EARS = ("left", "right", "both")
_OTHER = {"left": "right", "right": "left", "both": "both"}


def _signatures(sdl, mix):
    sdl.SDL_InitSubSystem.argtypes = [ctypes.c_uint32]
    sdl.SDL_QuitSubSystem.argtypes = [ctypes.c_uint32]
    sdl.SDL_GetError.restype = ctypes.c_char_p
    sdl.SDL_RWFromFile.restype = ctypes.c_void_p
    sdl.SDL_RWFromFile.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    mix.Mix_OpenAudio.argtypes = [ctypes.c_int, ctypes.c_uint16, ctypes.c_int, ctypes.c_int]
    mix.Mix_AllocateChannels.argtypes = [ctypes.c_int]
    mix.Mix_LoadWAV_RW.restype = ctypes.c_void_p
    mix.Mix_LoadWAV_RW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    mix.Mix_FreeChunk.argtypes = [ctypes.c_void_p]
    mix.Mix_PlayChannelTimed.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                                         ctypes.c_int]
    mix.Mix_SetPanning.argtypes = [ctypes.c_int, ctypes.c_uint8, ctypes.c_uint8]
    mix.Mix_Volume.argtypes = [ctypes.c_int, ctypes.c_int]
    mix.Mix_HaltChannel.argtypes = [ctypes.c_int]
    mix.Mix_Playing.argtypes = [ctypes.c_int]
    mix.Mix_Paused.argtypes = [ctypes.c_int]
    mix.Mix_Pause.argtypes = [ctypes.c_int]
    mix.Mix_Resume.argtypes = [ctypes.c_int]
    mix.Mix_GetChunk.restype = ctypes.c_void_p
    mix.Mix_GetChunk.argtypes = [ctypes.c_int]


def pan_for(ear):
    """Ganho (esquerdo, direito) de 0 a 255 para um ouvido."""
    if ear == "left":
        return 255, 0
    if ear == "right":
        return 0, 255
    return 255, 255


class EarSound:
    """Um som carregado. Toque com play()."""

    def __init__(self, ears, name, chunk):
        self.ears = ears
        self.name = name
        self.chunk = chunk

    def play(self, ear="both", loop=False, volume=1.0):
        """Toca num ouvido ("left", "right" ou "both") e devolve a EarVoice."""
        return self.ears._play(self, ear, loop, volume)


class EarVoice:
    """Um som tocando num canal da SDL2_mixer."""

    def __init__(self, ears, channel, chunk, ear, volume):
        self.ears = ears
        self.channel = channel
        self.chunk = chunk
        self.ear = ear
        self.volume = volume
        self.fade = None   # (volume inicial, final, duração, decorrido, parar no fim)

    @property
    def playing(self):
        return self.ears._owns(self) and bool(self.ears.mix.Mix_Playing(self.channel))

    def set_ear(self, ear):
        self.ear = ear
        if self.ears._owns(self):
            self.ears._pan(self.channel, ear)

    def set_volume(self, volume, fade=0.0):
        if not self.ears._owns(self):
            return
        if fade > 0:
            self.fade = (self.volume, volume, fade, 0.0, False)
        else:
            self.fade = None
            self._gain(volume)

    def _gain(self, volume):
        self.volume = max(0.0, min(1.0, volume))
        self.ears.mix.Mix_Volume(self.channel, int(round(self.volume * MIX_MAX_VOLUME)))

    def pause(self):
        if self.ears._owns(self):
            self.ears.mix.Mix_Pause(self.channel)

    def resume(self):
        if self.ears._owns(self):
            self.ears.mix.Mix_Resume(self.channel)

    def stop(self, fade=0.0):
        if not self.ears._owns(self):
            return
        if fade > 0:
            self.fade = (self.volume, 0.0, fade, 0.0, True)
        else:
            self.ears.mix.Mix_HaltChannel(self.channel)


class _NullVoice:
    """Devolvida quando não há áudio; aceita tudo e não faz nada."""
    playing = False
    ear = "both"
    volume = 0.0

    def set_ear(self, ear):
        pass

    def set_volume(self, volume, fade=0.0):
        pass

    def pause(self):
        pass

    def resume(self):
        pass

    def stop(self, fade=0.0):
        pass


class _FallbackSound:
    """Sem SDL2_mixer: toca pela OpenAL com pan -1/1 (vaza para o outro ouvido)."""

    def __init__(self, ears, sound):
        self.ears = ears
        self.sound = sound
        self.name = sound.name

    def play(self, ear="both", loop=False, volume=1.0):
        voice = self.sound.play(loop=loop, volume=volume,
                                pan=_FALLBACK_PAN[self.ears._side(ear)])
        voice = _FallbackVoice(self.ears, voice, ear)
        self.ears._fallback_voices.append(voice)
        return voice


_FALLBACK_PAN = {"left": -1.0, "right": 1.0, "both": 0.0}


class _FallbackVoice:
    def __init__(self, ears, voice, ear):
        self.ears = ears
        self.voice = voice
        self.ear = ear

    playing = property(lambda self: self.voice.playing)
    volume = property(lambda self: self.voice.volume)

    def set_ear(self, ear):
        self.ear = ear
        self.voice.set_pan(_FALLBACK_PAN[self.ears._side(ear)])

    def set_volume(self, volume, fade=0.0):
        self.voice.set_volume(volume, fade)

    def pause(self):
        self.voice.pause()

    def resume(self):
        self.voice.resume()

    def stop(self, fade=0.0):
        self.voice.stop(fade)


class Ears:
    """Sons por ouvido. Crie pelo game.ears (que também cuida do laço e do fim)."""

    def __init__(self, base_dir=".", fallback=None, frequency=44100, buffer=1024):
        self.base_dir = base_dir
        self.fallback = fallback      # um Audio, usado sem a SDL2_mixer
        self.available = False
        self.sounds = {}
        self.voices = {}              # canal -> EarVoice
        self._fallback_voices = []
        self._swap = False
        try:
            self._open(frequency, buffer)
        except OSError as exc:
            print("[r36s_a11y] som por ouvido indisponível (%s); usando a OpenAL, "
                  "que vaza para o outro ouvido" % exc, file=sys.stderr)

    def _open(self, frequency, buffer):
        self.sdl = native.load(["libSDL2-2.0.so.0", "SDL2", "SDL2.dll"],
                               mode=getattr(ctypes, "RTLD_GLOBAL", None))
        self.mix = native.load(["libSDL2_mixer-2.0.so.0", "SDL2_mixer", "SDL2_mixer.dll"])
        _signatures(self.sdl, self.mix)
        if self.sdl.SDL_InitSubSystem(SDL_INIT_AUDIO) != 0:
            raise OSError("SDL sem áudio: %s" % self.sdl.SDL_GetError().decode(errors="replace"))
        if self.mix.Mix_OpenAudio(frequency, AUDIO_S16SYS, 2, buffer) != 0:
            error = self.sdl.SDL_GetError().decode(errors="replace")
            self.sdl.SDL_QuitSubSystem(SDL_INIT_AUDIO)
            raise OSError("Mix_OpenAudio: %s" % error)
        self.mix.Mix_AllocateChannels(CHANNELS)
        self.available = True

    # --- lados -----------------------------------------------------------
    @property
    def swap(self):
        """True troca esquerda e direita de todos os sons, inclusive os que já
        estão tocando. Serve para trocar os papéis sem os jogadores trocarem
        de fone."""
        return self._swap

    @swap.setter
    def swap(self, value):
        self._swap = bool(value)
        for channel, voice in self.voices.items():
            self._pan(channel, voice.ear)
        for voice in self._fallback_voices:
            voice.set_ear(voice.ear)

    def _side(self, ear):
        if ear not in EARS:
            raise ValueError("ouvido deve ser left, right ou both: %r" % (ear,))
        return _OTHER[ear] if self._swap else ear

    def _pan(self, channel, ear):
        left, right = pan_for(self._side(ear))
        self.mix.Mix_SetPanning(channel, left, right)

    # --- sons ------------------------------------------------------------
    def load(self, name, path):
        full = sound_file(path if os.path.isabs(path) else os.path.join(self.base_dir, path))
        if not self.available:
            if self.fallback is None:
                return None
            sound = _FallbackSound(self, self.fallback.load(name, full))
            self.sounds[name] = sound
            return sound
        rw = self.sdl.SDL_RWFromFile(full.encode("utf-8"), b"rb")
        chunk = self.mix.Mix_LoadWAV_RW(rw, 1) if rw else None
        if not chunk:
            raise OSError("não carregou %s: %s"
                          % (full, self.sdl.SDL_GetError().decode(errors="replace")))
        sound = EarSound(self, name, chunk)
        self.sounds[name] = sound
        return sound

    def __getitem__(self, name):
        return self.sounds[name]

    def _owns(self, voice):
        return self.available and self.voices.get(voice.channel) is voice

    def _play(self, sound, ear, loop, volume):
        side = self._side(ear)  # confere o nome antes de tocar
        if not self.available:
            return _NullVoice()
        channel = self.mix.Mix_PlayChannelTimed(-1, sound.chunk, -1 if loop else 0, -1)
        if channel < 0:
            return _NullVoice()   # todos os canais ocupados
        left, right = pan_for(side)
        self.mix.Mix_SetPanning(channel, left, right)
        voice = EarVoice(self, channel, sound.chunk, ear, volume)
        voice._gain(volume)
        self.voices[channel] = voice
        return voice

    # --- laço ------------------------------------------------------------
    def update(self, dt):
        """Avança fades e esquece canais que terminaram."""
        if not self.available:
            self._fallback_voices = [v for v in self._fallback_voices if v.playing]
            return
        mix = self.mix
        for channel, voice in list(self.voices.items()):
            if voice.fade is not None:
                start, end, total, elapsed, stop = voice.fade
                elapsed += dt
                t = min(1.0, elapsed / total)
                voice._gain(start + (end - start) * t)
                if t >= 1.0:
                    voice.fade = None
                    if stop:
                        mix.Mix_HaltChannel(channel)
                else:
                    voice.fade = (start, end, total, elapsed, stop)
            if voice.fade is None and not mix.Mix_Playing(channel):
                del self.voices[channel]

    def pause_all(self):
        if self.available:
            self.mix.Mix_Pause(-1)

    def resume_all(self):
        if self.available:
            self.mix.Mix_Resume(-1)

    def stop_all(self):
        if self.available:
            self.mix.Mix_HaltChannel(-1)
            self.voices.clear()

    def close(self):
        if not self.available:
            return
        self.stop_all()
        for sound in self.sounds.values():
            self.mix.Mix_FreeChunk(sound.chunk)
        self.sounds.clear()
        self.mix.Mix_CloseAudio()
        self.sdl.SDL_QuitSubSystem(SDL_INIT_AUDIO)
        self.available = False
