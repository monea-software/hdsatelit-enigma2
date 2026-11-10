# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
# LCD-ul primeste acelasi cadru ca meniul si pagina web.

from Screens.Screen import Screen
from Components.Pixmap import Pixmap


class HdsAfisajColor(Screen):
	def __init__(self, session, info):
		self.w, self.h = info["latime"], info["inaltime"]
		self.skin = ('<screen position="0,0" size="%d,%d" '
			'flags="wfNoBorder" backgroundColor="#00000000">'
			'<widget name="cadru" position="0,0" size="%d,%d" '
			'alphatest="off" scale="1" /></screen>') % (
			self.w, self.h, self.w, self.h)
		Screen.__init__(self, session)
		self["cadru"] = Pixmap()
		self.animat = False
		self._cale = None
		self._pregatit = False
		if hasattr(self, "onLayoutFinish"):
			self.onLayoutFinish.append(self._gata)
		else:
			self._pregatit = self["cadru"].instance is not None

	def _gata(self):
		self._pregatit = True
		if self._cale:
			self["cadru"].instance.setPixmapFromFile(self._cale)

	def arataCadru(self, cale):
		if cale != self._cale:
			self._cale = cale
			if self._pregatit:
				self["cadru"].instance.setPixmapFromFile(cale)
