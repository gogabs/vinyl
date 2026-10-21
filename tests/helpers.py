"""Peças comuns dos testes: um mpv de mentira e pastas com áudio."""
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP))
# Mage Core: a cópia de reserva em r36s_a11y/, ou outra em A11Y_SDK.
if os.environ.get("A11Y_SDK"):
    sys.path.insert(0, os.environ["A11Y_SDK"])


class FakeMpv:
    def __init__(self):
        self.props = {}
        self.sent = []
        self.events = []
        self.observed = []

    def observe(self, name):
        self.observed.append(name)

    def command(self, *args):
        self.sent.append(args)

    def set(self, name, value):
        self.sent.append(("set_property", name, value))

    def stop(self):
        self.sent.append(("quit",))

    def poll(self):
        events, self.events = self.events, []
        for event in events:
            if event.get("event") == "property-change":
                self.props[event["name"]] = event.get("data")
        return events

    # --- ajudas dos testes ---
    def last(self, kind):
        for args in reversed(self.sent):
            if args[0] == kind:
                return args
        return None

    def prop_sets(self, name):
        return [a[2] for a in self.sent if a[0] == "set_property" and a[1] == name]

    def loaded(self, duration=None, pos=0.0, **props):
        """Simula o mpv abrindo o arquivo pedido."""
        self.events.append({"event": "file-loaded"})
        if duration is not None:
            self.events.append({"event": "property-change", "name": "duration", "data": duration})
        self.events.append({"event": "property-change", "name": "time-pos", "data": pos})
        for name, value in props.items():
            self.events.append({"event": "property-change", "name": name.replace("_", "-"), "data": value})


def silence(path, seconds=1.0, rate=8000):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(rate * seconds))
    return path


def touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").close()
    return path


def tempdir(test):
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    return tmp.name
