# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
# Fereastra de pe LCD foloseste poze PNG si fonturile native.

import os
import time

from Screens.Screen import Screen
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.HdsAfisajColor import DOSAR
from enigma import ePoint, eSize


class HdsAfisajColor(Screen):
	def __init__(self, session, info):
		self.w, self.h = info["latime"], info["inaltime"]
		self.sx, self.sy = self.w / 480.0, self.h / 320.0
		self.marime = "400x240" if self.w == 400 else "480x320"
		def drept(x, y, w, h):
			return '%d,%d" size="%d,%d' % (
				x * self.sx, y * self.sy, w * self.sx, h * self.sy)
		poze = []
		for nume, zona in (("fond", (0, 0, 480, 320)),
			("icoana", (18, 88, 72, 72)), ("poza", (0, 0, 480, 320)),
			("bara", (18, 276, 444, 18))):
			poze.append('<widget name="%s" position="%s" '
				'alphatest="blend" scale="1" />' % (nume, drept(*zona)))
		texte = []
		for nume, zona, font in (("titlu", (18, 18, 320, 58), 24),
			("ora", (346, 20, 116, 42), 30),
			("valoare", (18, 178, 444, 76), 46)):
			texte.append('<widget name="%s" position="%s" '
				'font="Regular;%d" foregroundColor="#00f2f4f8" '
				'transparent="1" noWrap="1" />' %
				(nume, drept(*zona), max(16, int(font * self.sy))))
		self.skin = '<screen position="0,0" size="%d,%d" '
		self.skin %= (self.w, self.h)
		self.skin += 'flags="wfNoBorder" backgroundColor="#00000000">'
		# La expresii, poza acopera fondul; textele se ascund.
		self.skin += ''.join(poze + texte) + '</screen>'
		Screen.__init__(self, session)
		for nume in ("fond", "icoana", "poza", "bara"):
			self[nume] = Pixmap()
		for nume in ("titlu", "ora", "valoare"):
			self[nume] = Label("")
		self._fisiere = {}
		self._pixmaps = {}
		self._marimi = {}
		self._texte = {}
		self._cheie = None
		self._latimeText = 0
		self._nivel = 0.0
		self.animat = False

	def _text(self, nume, text):
		if self._texte.get(nume) != text:
			self[nume].setText(text)
			self._texte[nume] = text

	def _poza(self, nume, cale):
		p = self[nume]
		if not cale:
			p.hide()
			return
		if self._fisiere.get(nume) != cale and p.instance is not None:
			from Tools.LoadPixmap import LoadPixmap
			if cale not in self._pixmaps:
				# Limita include cadrele robotului, fondul si pictogramele.
				if len(self._pixmaps) >= 32:
					self._pixmaps.clear()
				self._pixmaps[cale] = LoadPixmap(cale)
			p.instance.setPixmap(self._pixmaps[cale])
			self._fisiere[nume] = cale
		p.show()

	def _asset(self, nume):
		return os.path.join(DOSAR, self.marime, nume + ".png")

	def arata(self, titlu, text, imagine, fel, pereche, id_,
			secunde, viteza, stins=False, cu_ora=True):
		self.animat = False
		for nume in ("titlu", "ora", "valoare"):
			self[nume].hide() if stins else self[nume].show()
		if stins:
			for nume in ("fond", "icoana", "poza", "bara"):
				self._poza(nume, "")
			return
		self._poza("fond", self._asset("fond"))
		if fel == "personaj":
			self["poza"].instance.move(ePoint(0, 0))
			self["poza"].instance.resize(eSize(self.w, self.h))
			for nume in ("titlu", "ora", "valoare"):
				self[nume].hide()
			self._poza("icoana", "")
			self._poza("bara", "")
			cale = os.path.join(os.path.dirname(DOSAR), imagine)
			self._poza("poza", cale)
			return
		self._poza("poza", imagine if fel == "picon" else "")
		if fel == "picon":
			# Piconul isi pastreaza proportiile intr-un cadru central.
			if imagine not in self._marimi:
				png = self._pixmaps.get(imagine)
				marime = png.size() if png is not None else None
				self._marimi = {imagine: (marime.width(), marime.height())
					if marime is not None else (360, 140)}
			w, h = self._marimi[imagine]
			factor = min(360 * self.sx / max(1, w), 140 * self.sy / max(1, h))
			w, h = max(1, int(w * factor)), max(1, int(h * factor))
			self["poza"].instance.move(ePoint((self.w - w) // 2,
				int(62 * self.sy + (140 * self.sy - h) / 2)))
			self["poza"].instance.resize(eSize(w, h))
		else:
			self["poza"].instance.move(ePoint(0, 0))
			self["poza"].instance.resize(eSize(self.w, self.h))
		self._text("titlu", titlu)
		self._text("ora", time.strftime("%H:%M") if cu_ora else "")
		cheie = (id_, text)
		label = self["valoare"].instance
		if cheie != self._cheie:
			self._text("valoare", text)
			self._latimeText = label.calculateSize().width()
			label.resize(eSize(max(int(444 * self.sx), self._latimeText), int(76 * self.sy)))
			self._cheie = cheie
		latime = int(444 * self.sx)
		depasire = max(0, self._latimeText - latime)
		# Se misca numai textul care nu incape, cu pauza la ambele capete.
		pas = max(30.0, 18000.0 / max(100, viteza)) * self.sx
		durata = depasire / pas if depasire else 0
		t = secunde % (durata + 3.0)
		offset = min(depasire, max(0, (t - 1.5) * pas))
		# Intrarea unei valori aluneca scurt, fara alte ceasuri.
		intrare = max(0, 1.0 - secunde / 0.3)
		label.move(ePoint(int(18 * self.sx - offset + 16 * self.sx * intrare),
			int(210 * self.sy if fel == "picon" else 178 * self.sy)))
		self.animat = bool(depasire or intrare)
		icoana = "ceas" if id_.startswith(("ceas.", "asteptare.")) else "canal"
		if id_.startswith("semnal.") or id_ == "evenimente.fara_semnal":
			icoana = "semnal"
		elif "volum" in id_ or id_.startswith("sunet.") or id_ == "evenimente.mut":
			icoana = "volum"
		elif id_.startswith("inregistrari.") or id_ == "evenimente.rec":
			icoana = "rec"
		elif "usb" in id_:
			icoana = "usb"
		elif fel in ("inel", "sageti"):
			icoana = "lucru"
		cale = imagine if fel == "vremea" else self._asset(icoana)
		# Lampa REC pulseaza din fotografia ei, fara desen din linii.
		if icoana == "rec":
			self.animat = True
			if int(secunde * 2) % 2:
				cale = ""
		self._poza("icoana", "" if fel == "picon" else cale)
		if fel == "bara":
			tinta = max(0.0, min(1.0, float(pereche[1])))
			diferenta = tinta - self._nivel
			self._nivel += diferenta * 0.3 if abs(diferenta) > 0.005 else diferenta
			self.animat = self.animat or abs(diferenta) > 0.005
			self._poza("bara", self._asset("nivel") if self._nivel > 0 else "")
			self["bara"].instance.resize(eSize(max(1, int(latime * self._nivel)),
				max(1, int(18 * self.sy))))
		else:
			self._poza("bara", "")
		if fel in ("inel", "sageti"):
			self.animat = True
			x = 18 + (secunde * 60 % 320)
			if fel == "sageti" and pereche[1] == "vest":
				x = 338 - (secunde * 60 % 320)
			self["icoana"].instance.move(ePoint(int(x * self.sx), int(88 * self.sy)))
		else:
			self["icoana"].instance.move(ePoint(int(18 * self.sx), int(88 * self.sy)))
