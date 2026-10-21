"""O mpv sem interface, controlado pelo socket JSON (--input-ipc-server).

Só a biblioteca padrão, para rodar no Python 3.7 do ArkOS e no 3.13 do
dArkOS. Nada aqui bloqueia: poll() lê o que o mpv mandou e devolve os
eventos, e o app chama poll() a cada quadro.
"""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time

CONNECT_TIMEOUT = 5.0  # segundos para o mpv abrir o socket


def socket_path():
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(base, "vinyl-mpv.sock")


def audio_args():
    """Saída de som: sempre o mixer compartilhado, para a fala tocar junto.

    VINYL_AO escolhe outra (por exemplo "null" nos testes). Com o PulseAudio
    rodando (dArkOS), vai por ele; senão, o "default" do ALSA, que é o dmix.
    No PC, o mpv escolhe sozinho.
    """
    choice = os.environ.get("VINYL_AO")
    if choice:
        return ["--ao=" + choice]
    if os.environ.get("A11Y_PLATAFORMA") == "pc":
        return []
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if runtime and os.path.exists(os.path.join(runtime, "pulse", "native")):
        return ["--ao=pulse"]
    return ["--ao=alsa", "--audio-device=alsa/default"]


def available():
    return shutil.which(os.environ.get("VINYL_MPV", "mpv")) is not None


class MpvError(Exception):
    pass


class Mpv:
    """Um processo mpv e a conexão com ele.

    command() e set() mandam sem esperar resposta. observe() pede ao mpv
    que avise quando uma propriedade mudar; o último valor fica em
    self.props. poll() devolve os eventos (dicionários do mpv) que chegaram.
    """

    def __init__(self, path=None):
        self.path = path or socket_path()
        self.process = None
        self.sock = None
        self.buffer = b""
        self.props = {}
        self._observed = {}
        self._next_id = 1

    def start(self):
        try:
            os.remove(self.path)
        except OSError:
            pass
        args = [os.environ.get("VINYL_MPV", "mpv"), "--idle=yes", "--no-video",
                "--no-terminal", "--no-config", "--audio-display=no",
                "--input-ipc-server=" + self.path, "--volume=100",
                "--keep-open=no"] + audio_args()
        try:
            self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL)
        except OSError as exc:
            raise MpvError("mpv não abriu: %s" % exc)
        deadline = time.monotonic() + CONNECT_TIMEOUT
        while True:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(self.path)
                break
            except OSError:
                sock.close()
                if self.process.poll() is not None or time.monotonic() > deadline:
                    self.stop()
                    raise MpvError("mpv não abriu o socket")
                time.sleep(0.05)
        sock.setblocking(False)
        self.sock = sock

    def alive(self):
        return self.process is not None and self.process.poll() is None and self.sock is not None

    def stop(self):
        if self.sock is not None:
            try:
                self._send({"command": ["quit"]})
            except OSError:
                pass
            self.sock.close()
            self.sock = None
        if self.process is not None:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
        try:
            os.remove(self.path)
        except OSError:
            pass

    # --- envio ---------------------------------------------------------
    def _send(self, message):
        data = (json.dumps(message) + "\n").encode("utf-8")
        self.sock.setblocking(True)
        try:
            self.sock.sendall(data)
        finally:
            self.sock.setblocking(False)

    def command(self, *args):
        if self.sock is None:
            return
        request = self._next_id
        self._next_id += 1
        self._send({"command": list(args), "request_id": request})

    def set(self, name, value):
        self.command("set_property", name, value)

    def observe(self, name):
        if name in self._observed:
            return
        ident = len(self._observed) + 1
        self._observed[name] = ident
        self.command("observe_property", ident, name)

    # --- recebimento ---------------------------------------------------
    def poll(self):
        events = []
        if self.sock is None:
            return events
        while True:
            try:
                chunk = self.sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                chunk = b""
            if not chunk:   # o mpv fechou
                self.sock.close()
                self.sock = None
                events.append({"event": "vinyl-closed"})
                break
            self.buffer += chunk
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            try:
                message = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            if message.get("event") == "property-change":
                self.props[message.get("name")] = message.get("data")
            if "event" in message:
                events.append(message)
        return events
