# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSubtitrariFilm.py (ecranul): alegerea unui fisier de subtitrare pentru filmul care merge, din tasta SUB
# („Alege alt fișier…”). Navigatorul de fisiere porneste din dosarul filmului si arata numai dosarele si fisierele cu
# extensiile de subtitrare citite de Components/HdsSubtitrariFilm.py; se poate merge pe alt dispozitiv (stick, retea).
# Fisierul ales se cerceteaza pe un fir (Components/HdsSubtitrariFilm.adaugaFisier cu `gata`): daca nu e subtitrare,
# mesajul apare jos si navigatorul ramane deschis; altfel fisierul intra in lista filmului si ecranul intoarce
# (calea, numarul in lista serviciului). EXIT intoarce None. Numai sagetile si OK: OK intra in dosar sau alege fisierul.

from __future__ import absolute_import

import os

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.FileList import FileList
from Components.HdsNavigator import HdsPanouFisiere
from Components.Label import Label

from Components import HdsSubtitrariFilm as sf

TIPAR_SUBTITRARI = r"(?i)^.*\.(%s)$" % u"|".join(e[1:] for e in sf.EXTENSII)


class HdsAlegeSubtitrare(Screen):
	"""Navigatorul de fisiere, oprit la subtitrari. Intoarce (calea, numarul in lista serviciului) sau None."""

	skin = """
	<screen name="HdsAlegeSubtitrare" position="center,center" size="1240,900" title="Alege fișierul de subtitrare">
		<widget name="hds_cale" position="30,20" size="1180,44" font="Regular;30" foregroundColor="#00ffcc66" noWrap="1" />
		<widget name="lista" position="30,76" size="1180,594" itemHeight="54" scrollbarMode="showOnDemand" />
		<widget name="hds_stare" position="30,76" size="1180,594" font="Regular;30" halign="center" valign="center" transparent="1" zPosition="2" />
		<widget name="stare" position="30,690" size="1180,120" font="Regular;28" />
		<widget name="key_red" position="30,830" size="300,50" backgroundColor="#009f1313" font="Regular;28" halign="center" valign="center" />
		<widget name="key_green" position="350,830" size="300,50" backgroundColor="#001f771f" font="Regular;28" halign="center" valign="center" />
	</screen>"""

	def __init__(self, session, dosar=None):
		Screen.__init__(self, session)
		self.setTitle(_("Alege fișierul de subtitrare"))
		if dosar and not os.path.isdir(dosar):
			dosar = None
		self.lista = FileList(dosar and (dosar.rstrip("/") + "/"), matchingPattern=TIPAR_SUBTITRARI)
		self["lista"] = self.lista
		self.panou = HdsPanouFisiere(self, self.lista, details=False)
		self["stare"] = Label(_("Alege un fișier de subtitrare (srt, sub, ass, ssa, vtt, smi, txt; la DVD fișierul idx, la "
			"Blu-ray sup) și apasă OK. Rămâne în listă la filmul acesta."))
		self["key_red"] = Label(_("Înapoi"))
		self["key_green"] = Label(_("Alege"))
		self.inLucru = False
		self.inchis = False
		self.onClose.append(self._inchis)
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"ok": self.alege,
			"green": self.alege,
			"cancel": self.inapoi,
			"red": self.inapoi,
		}, -1)
		getattr(self, "onLayoutFinish", []).append(self._textMarit)

	def _textMarit(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): randul de stare de sub lista (cel mai lung
		e indemnul de la deschidere) creste in sus cat ii cere textul, iar lista fisierelor se scurteaza; de la 125 % se
		pierdea ultimul rand. La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			a = MT.Asezare(self)
			lista, stare = a.dinSkin(self["lista"].instance), self["stare"].instance
			if lista and stare is not None:
				a.creste(stare, MT.inaltimeText(stare), lista[1], sus=True, maxim=lista[3] // 3)
		except Exception as e:
			print("[HdsAlegeSubtitrare] textul marit: %s" % e)

	def _inchis(self):
		self.inchis = True

	def inapoi(self):
		self.close(None)

	def alege(self):
		if self.lista.canDescent():
			self.lista.descent()
			return
		dosar = self.lista.getCurrentDirectory() or ""
		nume = self.lista.getFilename() or ""
		if not nume:
			return
		cale = nume if os.path.isabs(nume) else os.path.join(dosar, nume)
		if os.path.splitext(cale)[1].lower() not in sf.EXTENSII:
			self["stare"].setText(_("Fișierul acesta nu este o subtitrare."))
			return
		if self.inLucru:
			return
		reusit, mesaj, numar = sf.adaugaFisier(cale, gata=lambda r, m, n: self._gata(cale, r, m, n))
		if not reusit:
			self["stare"].setText(mesaj)
			return
		self.inLucru = True
		self["stare"].setText(_("Se citește fișierul..."))

	def _gata(self, cale, reusit, mesaj, numar):
		"""Pe firul enigma2, dupa cercetarea fisierului: inchide cu fisierul ales sau arata de ce nu merge."""
		self.inLucru = False
		if self.inchis:
			return
		if not reusit or numar is None:
			self["stare"].setText(mesaj or _("Fișierul acesta nu este o subtitrare."))
			return
		self.close((cale, numar))
