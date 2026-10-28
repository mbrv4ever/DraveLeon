# -*- coding: utf-8 -*-
# DraveLeon - Copyright (C) 2026 Dravenlock (Roger & Claudio).
"""leon.py - Leon (neuvoice) spreekt een stukje tekst uit. Elke uitgesproken tekst wordt bewaard, dus maar één keer gemaakt."""
import hashlib
import math
import os
import re
import struct
import threading
import wave

_tts = None
_stijl = None
_sr = 44100
_lock = threading.Lock()
status = "uit"           # uit | laden | klaar | geen


def _laad():
    global _tts, _stijl, _sr, status
    if _tts is not None or status == "geen":
        return _tts is not None
    with _lock:
        if _tts is not None:
            return True
        try:
            status = "laden"
            from neuvoice import TTS
            _tts = TTS(auto_download=True)
            namen = list(getattr(_tts, "voice_style_names", []) or [])
            _stijl = _tts.get_voice_style("Leon" if "Leon" in namen else namen[0])
            _sr = int(getattr(_tts, "sample_rate", 44100) or 44100)
            status = "klaar"
            return True
        except Exception:
            status = "geen"
            return False


def spreekbaar(t):
    t = t.replace("&", " en ").replace("NOS", "N O S").replace("NU.nl", "Nu punt en el").replace(".nl", " punt en el")
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"[_|/\\\[\](){}*#\"“”]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def zinnen(tekst):
    delen = re.split(r"(?<=[.!?])\s+", tekst.strip())
    uit, buf = [], ""
    for d in delen:                                  # korte zinnen samen nemen, lange zinnen knippen bij een komma
        if len(buf) + len(d) < 160:
            buf = (buf + " " + d).strip()
            continue
        if buf:
            uit.append(buf)
        while len(d) > 220 and "," in d[60:200]:
            k = d.index(",", 60) + 1
            uit.append(d[:k].strip())
            d = d[k:].strip()
        buf = d
    if buf:
        uit.append(buf)
    return [z for z in uit if z.strip()]


def maak(tekst, map_, taal="nl", ruw=False):
    """Maakt (of vindt) een wav-bestand met Leon voor één stukje tekst. Geeft het pad terug, of None."""
    os.makedirs(map_, exist_ok=True)
    try:
        from uitspraak import uitspraak
        tekst = spreekbaar(tekst) if ruw else uitspraak(spreekbaar(tekst), taal)
    except Exception:
        tekst = spreekbaar(tekst)
    pad = os.path.join(map_, hashlib.md5((taal + tekst).encode("utf-8")).hexdigest()[:16] + ".wav")
    if os.path.exists(pad):
        return pad
    if not _laad():
        return None
    try:
        import numpy as np
        wav, _ = _tts.synthesize(tekst, voice_style=_stijl, total_steps=10, speed=0.9, lang=taal)
        x = np.asarray(wav, dtype=np.float32).flatten()
        stil = np.zeros(int(_sr * 0.18), np.float32)
        x = np.concatenate([stil, x, stil])
        x = x / (np.max(np.abs(x)) or 1) * 0.9
        with wave.open(pad, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(_sr)
            w.writeframes((x * 32767).astype("<i2").tobytes())
        return pad
    except Exception:
        return None


def belletje(pad):
    """Een zacht tussen-belletje (twee tonen), zelf gemaakt."""
    if os.path.exists(pad):
        return pad
    sr = 44100
    data = bytearray()
    for i in range(int(sr * 1.4)):
        t = i / sr
        v = 0.0
        for f, start in ((880.0, 0.0), (1318.5, 0.18)):
            if t >= start:
                tt = t - start
                v += math.sin(2 * math.pi * f * tt) * math.exp(-tt * 3.2) * 0.22
                v += math.sin(2 * math.pi * f * 2 * tt) * math.exp(-tt * 5) * 0.05
        data += struct.pack("<h", int(max(-1, min(1, v)) * 32767))
    os.makedirs(os.path.dirname(pad), exist_ok=True)
    with wave.open(pad, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(data))
    return pad
