# -*- coding: utf-8 -*-
# DraveLeon - Copyright (C) 2026 Dravenlock (Roger & Claudio). Vrije software onder de GNU GPL v3.0.
"""DraveLeon - leer Leon (de stem van alle Drave-apps) woorden goed uitspreken.

Typ een zin of woord. Leon zegt het. Per woord kies je Goed of Slecht; bij Slecht schrijf je op hoe het
moet klinken (bijvoorbeeld Roger -> Rozjee), test je het en bewaar je het. De lijst staat in één bestand
dat je zelf kiest; alle Drave-apps (vanaf hun volgende versie) lezen die lijst en spreken het dan ook goed uit.
"""
import json
import os
import re
import sys
import threading
import time

from PyQt6.QtCore import Qt, QObject, QUrl, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QGridLayout, QScrollArea, QTabWidget, QListWidget, QListWidgetItem, QDialog,
                             QFileDialog, QMessageBox, QFrame)

import leon
import uitspraak

APP_NAAM = "DraveLeon"
APP_VERSION = "0.1"
LIJST_NAAM = "leon_uitspraak.json"


def app_map():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


def bron(naam):
    for b in (getattr(sys, "_MEIPASS", None), app_map()):
        if b and os.path.exists(os.path.join(b, naam)):
            return os.path.join(b, naam)
    return os.path.join(app_map(), naam)


DATA = os.path.join(app_map(), "DraveLeon-data")
os.makedirs(DATA, exist_ok=True)
CACHE = os.path.join(DATA, "geluid")


def stijl(f):
    p = lambda n: "%dpt" % round(n * f)
    return """
* { font-family: 'Segoe UI'; color: #e2e2ec; }
QMainWindow, QWidget#basis, QDialog, QScrollArea, QWidget#vel, QTabWidget::pane { background: #0a0810; border: 0; }
QLabel#titel { font-size: %(t)s; font-weight: 700; }
QLabel#kop { font-size: %(kop)s; font-weight: 700; color: #ffde3c; }
QLabel#klein { font-size: %(klein)s; color: #9a96aa; }
QLabel#tekst, QDialog QLabel { font-size: %(tekst)s; }
QLabel#woord { font-size: %(groot)s; font-weight: 700; }
QLabel#zegt { font-size: %(klein)s; color: #ffde3c; }
QPushButton { background: #18122a; border: 2px solid #9a5ae6; border-radius: 12px; padding: 9px 15px;
              font-size: %(knop)s; font-weight: 600; }
QPushButton:hover { border-color: #ffde3c; }
QPushButton#groen { background: #1d6b3a; border-color: #46c86e; }
QPushButton#rood { background: #7a2424; border-color: #ff6e6e; }
QPushButton#paars { background: #9a5ae6; color: #0a0810; border-color: #ffde3c; font-size: %(groot)s; padding: 12px 18px; }
QLineEdit { background: #fafaff; color: #0a0810; border: 3px solid #ffde3c; border-radius: 10px; padding: 8px 12px;
            font-size: %(groot)s; }
QFrame#kaart { background: #120d20; border: 2px solid #46307a; border-radius: 14px; }
QFrame#kaart[staat="goed"] { border-color: #46c86e; }
QFrame#kaart[staat="beter"] { border-color: #ffde3c; }
QTabBar::tab { background: #18122a; border: 2px solid #46307a; padding: 10px 22px; font-size: %(knop)s; font-weight: 600;
               border-top-left-radius: 10px; border-top-right-radius: 10px; margin-right: 4px; }
QTabBar::tab:selected { background: #9a5ae6; color: #0a0810; border-color: #ffde3c; }
QListWidget { background: #0f0b1a; border: 2px solid #46307a; border-radius: 12px; font-size: %(tekst)s; }
QListWidget::item { border-bottom: 1px solid #241a3a; padding: 10px; }
QListWidget::item:selected { background: #2c1d50; }
""" % dict(t=p(24), kop=p(16), klein=p(12), tekst=p(15), knop=p(14), groot=p(19))


# ------------------------------------------------------------------ de lijst
class Lijst:
    """De verbeteringen in één json-bestand op een plek die Roger kiest. Het pad staat ook in het register,
    zodat de andere Drave-apps het vinden."""

    def __init__(self):
        self.inst = {}
        try:
            with open(os.path.join(DATA, "instellingen.json"), encoding="utf-8") as f:
                self.inst = json.load(f)
        except Exception:
            pass
        self.pad = self.inst.get("lijst") or uitspraak.lijst_pad()
        self.woorden, self.goed = {}, []
        self.laad()

    def laad(self):
        uitspraak.PAD = self.pad
        uitspraak._eigen["regex"] = None
        self.woorden, self.goed = {}, []
        if self.pad and os.path.exists(self.pad):
            try:
                with open(self.pad, encoding="utf-8-sig") as f:
                    d = json.load(f)
                self.woorden = {k.lower(): v for k, v in (d.get("woorden") or {}).items()}
                self.goed = [g.lower() for g in d.get("goed", [])]
            except Exception:
                pass

    def zet_pad(self, map_):
        self.pad = os.path.join(map_, LIJST_NAAM)
        uitspraak.PAD = self.pad
        if os.path.exists(self.pad):
            self.laad()                     # er stond al een lijst: die gebruiken
        else:
            self.bewaar()
        self.inst["lijst"] = self.pad
        with open(os.path.join(DATA, "instellingen.json"), "w", encoding="utf-8") as f:
            json.dump(self.inst, f, ensure_ascii=False, indent=1)
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Dravenlock") as k:
                winreg.SetValueEx(k, "LeonUitspraak", 0, winreg.REG_SZ, self.pad)
        except Exception:
            pass

    def bewaar(self):
        if not self.pad:
            return
        tmp = self.pad + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(versie=1, uitleg="Lijst van DraveLeon: zo spreekt Leon deze woorden uit.",
                           woorden=dict(sorted(self.woorden.items())), goed=sorted(set(self.goed))),
                      f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.pad)
        uitspraak.PAD = self.pad
        uitspraak._eigen["regex"] = None    # meteen opnieuw lezen

    def verbeter(self, woord, zo):
        w = woord.lower()
        self.woorden[w] = zo
        self.goed = [g for g in self.goed if g != w]
        self.bewaar()

    def keur_goed(self, woord):
        w = woord.lower()
        if w not in self.goed:
            self.goed.append(w)
        self.bewaar()

    def weg(self, woord):
        self.woorden.pop(woord.lower(), None)
        self.bewaar()


# ------------------------------------------------------------------ venster
class Sein(QObject):
    klaar = pyqtSignal(str, int)       # pad, beurt


class Verbeter(QDialog):
    def __init__(self, ouder, woord, nu):
        super().__init__(ouder)
        self.ouder = ouder
        self.setWindowTitle("Hoe moet het klinken?")
        self.resize(760, 380)
        l = QVBoxLayout(self)
        l.setContentsMargins(28, 22, 28, 22)
        l.setSpacing(14)
        k = QLabel("Hoe moet <b>%s</b> klinken?" % woord)
        k.setObjectName("kop")
        l.addWidget(k)
        uitleg = QLabel("Schrijf het op zoals je het zegt. Bijvoorbeeld: Roger wordt Rozjee (op zijn Frans). "
                        "Tik op Proberen om het te horen, en bewaar het als het goed klinkt.")
        uitleg.setWordWrap(True)
        uitleg.setObjectName("tekst")
        l.addWidget(uitleg)
        self.veld = QLineEdit(nu)
        self.veld.selectAll()
        l.addWidget(self.veld)
        rij = QHBoxLayout()
        p = QPushButton("🔊  Proberen")
        p.clicked.connect(lambda: self.ouder.zeg(self.veld.text(), ruw=True))
        b = QPushButton("✓  Bewaren")
        b.setObjectName("groen")
        b.clicked.connect(self._ok)
        a = QPushButton("Annuleren")
        a.clicked.connect(self.reject)
        rij.addWidget(p)
        rij.addStretch(1)
        rij.addWidget(a)
        rij.addWidget(b)
        l.addLayout(rij)
        self.veld.returnPressed.connect(lambda: self.ouder.zeg(self.veld.text(), ruw=True))

    def _ok(self):
        if self.veld.text().strip():
            self.accept()


class DraveLeon(QMainWindow):
    def __init__(self):
        super().__init__()
        self.f = 1.0
        self.lijst = Lijst()
        self.sein = Sein()
        self.sein.klaar.connect(self._speel)
        self.beurt = 0
        self.uit = QAudioOutput()
        self.speler = QMediaPlayer()
        self.speler.setAudioOutput(self.uit)
        self.setWindowTitle("DraveLeon - Leon leren praten")
        self.setWindowIcon(QIcon(bron(os.path.join("assets", "icon.ico"))))
        self.resize(1250, 900)
        self._bouw()
        self.setStyleSheet(stijl(self.f))
        threading.Thread(target=leon._laad, daemon=True).start()     # Leon alvast wakker maken
        self.klok = QTimer(self)
        self.klok.timeout.connect(self._status)
        self.klok.start(500)
        if not self.lijst.pad:
            QTimer.singleShot(400, self.kies_map)

    # ---- opbouw
    def _bouw(self):
        basis = QWidget()
        basis.setObjectName("basis")
        self.setCentralWidget(basis)
        l = QVBoxLayout(basis)
        l.setContentsMargins(22, 16, 22, 12)
        kop = QHBoxLayout()
        logo = QLabel()
        from PyQt6.QtGui import QPixmap
        pm = QPixmap(bron(os.path.join("assets", "icon.png")))
        if not pm.isNull():
            logo.setPixmap(pm.scaledToHeight(56, Qt.TransformationMode.SmoothTransformation))
        kop.addWidget(logo)
        t = QLabel("DraveLeon")
        t.setObjectName("titel")
        kop.addWidget(t)
        kop.addStretch(1)
        for tekst, d in (("A−", -0.1), ("A+", 0.1)):
            k = QPushButton(tekst)
            k.clicked.connect(lambda _=False, d=d: self.letter(d))
            kop.addWidget(k)
        l.addLayout(kop)
        self.tabs = QTabWidget()
        l.addWidget(self.tabs, 1)
        # tab 1: proberen
        t1 = QWidget()
        t1.setObjectName("vel")
        v = QVBoxLayout(t1)
        v.setContentsMargins(4, 14, 4, 4)
        uitleg = QLabel("Typ een zin of een woord. Leon zegt het. Klik per woord op Goed of Slecht.")
        uitleg.setObjectName("tekst")
        uitleg.setWordWrap(True)
        v.addWidget(uitleg)
        rij = QHBoxLayout()
        self.invoer = QLineEdit()
        self.invoer.setPlaceholderText("Bijvoorbeeld: Goedemorgen Roger, kijk op dravenlock.nl")
        self.invoer.returnPressed.connect(self.uitspreken)
        rij.addWidget(self.invoer, 1)
        k = QPushButton("🔊  Uitspreken")
        k.setObjectName("paars")
        k.clicked.connect(self.uitspreken)
        rij.addWidget(k)
        v.addLayout(rij)
        self.zo = QLabel("")
        self.zo.setObjectName("klein")
        self.zo.setWordWrap(True)
        v.addWidget(self.zo)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.vel = QWidget()
        self.vel.setObjectName("vel")
        self.grid = QGridLayout(self.vel)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.vel)
        v.addWidget(self.scroll, 1)
        self.tabs.addTab(t1, "Proberen")
        # tab 2: mijn lijst
        t2 = QWidget()
        t2.setObjectName("vel")
        w = QVBoxLayout(t2)
        w.setContentsMargins(4, 14, 4, 4)
        self.aantal = QLabel("")
        self.aantal.setObjectName("kop")
        w.addWidget(self.aantal)
        self.lijstw = QListWidget()
        self.lijstw.itemDoubleClicked.connect(lambda it: self.pas_aan(it.data(Qt.ItemDataRole.UserRole)))
        w.addWidget(self.lijstw, 1)
        rij = QHBoxLayout()
        for tekst, fn, naam in (("🔊  Luisteren", self._luister_gekozen, None), ("✎  Aanpassen", self._pas_gekozen, None),
                                ("🗑  Weghalen", self._weg_gekozen, "rood")):
            k = QPushButton(tekst)
            if naam:
                k.setObjectName(naam)
            k.clicked.connect(fn)
            rij.addWidget(k)
        rij.addStretch(1)
        w.addLayout(rij)
        self.waar = QLabel("")
        self.waar.setObjectName("klein")
        self.waar.setWordWrap(True)
        self.waar.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        w.addWidget(self.waar)
        k = QPushButton("📁  Andere map voor de lijst kiezen")
        k.clicked.connect(self.kies_map)
        w.addWidget(k, 0, Qt.AlignmentFlag.AlignLeft)
        self.tabs.addTab(t2, "Mijn lijst")
        self.status = QLabel("")
        self.status.setObjectName("klein")
        l.addWidget(self.status)
        self.vul_lijst()

    def letter(self, d):
        self.f = max(0.7, min(1.8, self.f + d))
        self.setStyleSheet(stijl(self.f))

    def _status(self):
        s = {"uit": "Leon wordt wakker...", "laden": "Leon wordt wakker... (de eerste keer duurt dat even)",
             "klaar": "Leon is er.", "geen": "Leon kan niet starten (neuvoice ontbreekt)."}.get(leon.status, "")
        self.status.setText("%s   ·   DraveLeon %s  -  Dravenlock (Roger & Claudio)" % (s, APP_VERSION))

    # ---- spreken
    def zeg(self, tekst, ruw=False):
        tekst = (tekst or "").strip()
        if not tekst:
            return
        self.beurt += 1
        beurt = self.beurt
        self.speler.stop()

        def werk():
            p = leon.maak(tekst, CACHE, ruw=ruw)
            if p:
                self.sein.klaar.emit(p, beurt)
        threading.Thread(target=werk, daemon=True).start()

    def _speel(self, pad, beurt):
        if beurt != self.beurt:
            return
        self.speler.setSource(QUrl.fromLocalFile(pad))
        self.speler.play()

    # ---- proberen
    def uitspreken(self):
        tekst = self.invoer.text().strip()
        if not tekst:
            return
        self.zeg(tekst)
        zo = uitspraak.uitspraak(leon.spreekbaar(tekst))
        self.zo.setText(("Leon leest dit als:  " + zo) if zo != tekst else "")
        self.toon_woorden(tekst)

    def toon_woorden(self, tekst):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        woorden, gezien = [], set()
        for w in re.findall(r"[\w'’\-]+", tekst):
            if w.lower() not in gezien and re.search(r"\w", w):
                gezien.add(w.lower())
                woorden.append(w)
        for i, w in enumerate(woorden):
            self.grid.addWidget(self.kaart(w), i // 3, i % 3)

    def kaart(self, woord):
        k = QFrame()
        k.setObjectName("kaart")
        lw = woord.lower()
        k.setProperty("staat", "beter" if lw in self.lijst.woorden else ("goed" if lw in self.lijst.goed else ""))
        v = QVBoxLayout(k)
        v.setContentsMargins(14, 10, 14, 12)
        t = QLabel(woord)
        t.setObjectName("woord")
        v.addWidget(t)
        z = QLabel(("Leon zegt: " + self.lijst.woorden[lw]) if lw in self.lijst.woorden else
                   ("✓ goedgekeurd" if lw in self.lijst.goed else " "))
        z.setObjectName("zegt")
        v.addWidget(z)
        rij = QHBoxLayout()
        b = QPushButton("🔊")
        b.setToolTip("Laat Leon dit woord zeggen")
        b.clicked.connect(lambda: self.zeg(woord))
        g = QPushButton("✓ Goed")
        g.setObjectName("groen")
        g.clicked.connect(lambda: self.goed(woord))
        s = QPushButton("✗ Slecht")
        s.setObjectName("rood")
        s.clicked.connect(lambda: self.pas_aan(woord))
        for x in (b, g, s):
            rij.addWidget(x)
        v.addLayout(rij)
        return k

    def goed(self, woord):
        if not self._heeft_pad():
            return
        if woord.lower() in self.lijst.woorden:
            if QMessageBox.question(self, APP_NAAM, "Voor '%s' staat er al een verbetering (%s).\n\nKlinkt het nu goed? "
                                    "Dan laat ik de verbetering staan." % (woord, self.lijst.woorden[woord.lower()])) \
                    != QMessageBox.StandardButton.Yes:
                return
        self.lijst.keur_goed(woord)
        self.ververs()

    def pas_aan(self, woord):
        if not woord or not self._heeft_pad():
            return
        d = Verbeter(self, woord, self.lijst.woorden.get(woord.lower(), woord))
        d.setStyleSheet(stijl(self.f))
        if d.exec() == 1:
            self.lijst.verbeter(woord, d.veld.text().strip())
            self.zeg(woord)
            self.ververs()

    def ververs(self):
        tekst = self.invoer.text().strip()
        if tekst:
            self.toon_woorden(tekst)
            zo = uitspraak.uitspraak(leon.spreekbaar(tekst))
            self.zo.setText(("Leon leest dit als:  " + zo) if zo != tekst else "")
        self.vul_lijst()

    # ---- mijn lijst
    def vul_lijst(self):
        self.lijstw.clear()
        for w, zo in sorted(self.lijst.woorden.items()):
            it = QListWidgetItem("%s   →   %s" % (w, zo))
            it.setData(Qt.ItemDataRole.UserRole, w)
            self.lijstw.addItem(it)
        n = len(self.lijst.woorden)
        self.aantal.setText("%d %s verbeterd · %d goedgekeurd" % (n, "woord" if n == 1 else "woorden", len(self.lijst.goed)))
        self.waar.setText(("De lijst staat in:  %s\nAlle Drave-apps gebruiken deze lijst vanaf hun volgende versie." % self.lijst.pad)
                          if self.lijst.pad else "Nog geen map gekozen voor de lijst.")

    def _gekozen(self):
        it = self.lijstw.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _luister_gekozen(self):
        w = self._gekozen()
        if w:
            self.zeg(w)

    def _pas_gekozen(self):
        self.pas_aan(self._gekozen())

    def _weg_gekozen(self):
        w = self._gekozen()
        if w and QMessageBox.question(self, APP_NAAM, "De verbetering voor '%s' weghalen?" % w) == QMessageBox.StandardButton.Yes:
            self.lijst.weg(w)
            self.ververs()

    # ---- de plek van de lijst
    def _heeft_pad(self):
        if self.lijst.pad:
            return True
        self.kies_map()
        return bool(self.lijst.pad)

    def kies_map(self):
        QMessageBox.information(self, APP_NAAM, "Kies een map waar de lijst met Leon's uitspraak mag staan.\n\n"
                                "Alle Drave-apps lezen deze lijst. Kies een map die blijft bestaan, bijvoorbeeld op D:.")
        begin = os.path.dirname(self.lijst.pad) if self.lijst.pad else ("D:\\" if os.path.exists("D:\\") else os.path.expanduser("~"))
        m = QFileDialog.getExistingDirectory(self, "Map voor de lijst van DraveLeon", begin)
        if m:
            self.lijst.zet_pad(m)
            self.ververs()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAAM)
    w = DraveLeon()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
