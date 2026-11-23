# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Optional VPN badge. Reads the guard cache; no network work on the UI thread."""

from enigma import eTimer, eSize
from Components.Pixmap import Pixmap
from Components import HdsVpn as V


class LegaturaVpn(object):
	def __init__(self, bara):
		self.bara = bara
		self.vecini = []
		self.asezat = None
		self.skinGata = False
		self.veciniCititi = False
		for nume in ("hdsVpnPornit", "hdsVpnOprit"):
			bara[nume] = Pixmap()
			bara[nume].hide()
		self.ceas = None
		bara.onLayoutFinish.append(self._dupaSkin)
		bara.onShow.append(self.actualizeaza)
		bara.onHide.append(self.ascunde)
		# onShown runs after Screen has set execing=True, including returns from menus.
		bara.onShown.append(self.actualizeaza)
		bara.onExecEnd.append(self.ascunde)
		bara.onClose.append(self.inchide)
		# The option can change from the web while the bar is on screen: no timer runs with it off.
		V._OBSERVATORI_ICONITA.append(self.actualizeaza)

	def _dupaSkin(self):
		self.skinGata = True
		self.actualizeaza()

	def _pregatesteVecinii(self):
		if not self.skinGata or self.veciniCititi:
			return
		self.veciniCititi = True
		self.asezat = None
		# Only Clasic needs room in the next-event row. Pro has a free slot.
		poza = self.bara["hdsVpnPornit"]
		if dict(poza.skinAttributes or []).get("position") == "1464,148":
			from Components.HdsPictogramaBare import _obiecte, _scara
			n, d = _scara(self.bara)
			for o in _obiecte(self.bara):
				a = dict(o.skinAttributes)
				if (a.get("position"), a.get("size")) in (
						("152,144", "1346,40"), ("752,144", "750,40"), ("760,144", "740,40")):
					self.vecini.append((o, o.instance.size().width(), 44 * n // d))

	def _aseaza(self, activ):
		if self.asezat == activ:
			return
		for o, latime, scade in self.vecini:
			o.instance.resize(eSize(max(1, latime - scade) if activ else latime, o.instance.size().height()))
		self.asezat = activ

	def ascunde(self):
		if self.ceas is not None:
			self.ceas.stop()
		if self.bara is not None:
			for nume in ("hdsVpnPornit", "hdsVpnOprit"):
				self.bara[nume].hide()

	def inchide(self):
		try:
			V._OBSERVATORI_ICONITA.remove(self.actualizeaza)
		except ValueError:
			pass
		self.ascunde()
		self.bara = None
		self.vecini = []

	def actualizeaza(self):
		b = self.bara
		self.ascunde()
		if b is None or not b.shown or not b.execing or b.session.current_dialog is not b:
			return
		try:
			stare = V.stareBara()
			if stare:
				self._pregatesteVecinii()
			self._aseaza(bool(stare))
			if stare:
				b["hdsVpnPornit" if stare == "pornit" else "hdsVpnOprit"].show()
		except Exception:
			self._aseaza(False)
			return
		if not stare:
			return
		if self.ceas is None:
			self.ceas = eTimer()
			self.ceas.callback.append(self.actualizeaza)
		self.ceas.start(2000, True)
