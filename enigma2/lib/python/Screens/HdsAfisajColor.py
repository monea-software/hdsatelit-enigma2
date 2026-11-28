# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# LCD-ul primeste acelasi cadru ca meniul si pagina web.
#
# Afisajul Dream (DM900/DM920, /proc/stb/lcd/colorformat = BGR_565_LE) arata rosul si albastrul inversate fata de cadrul
# randat (fundalul albastru-inchis iesea maro, siglele cu rosu si albastru schimbate; TODO 23.11 01:35, 23.11 18:50).
# Pe el ecranul incarca o copie a cadrului cu rosul si albastrul schimbate, langa original; pagina web primeste tot
# originalul. Copiile se tin minte (cel mult COPII_BGR), deci paginile care se schimba intre ele nu se convertesc din nou.

from collections import OrderedDict
import os

from Screens.Screen import Screen
from Components.Pixmap import Pixmap

COPII_BGR = 8


def _bgr(cale="/proc/stb/lcd/colorformat"):
	"""Afisajul vrea rosul si albastrul inversate (driverul Dream spune BGR_565_LE)."""
	try:
		with open(cale, "r") as f:
			return f.read().strip() == "BGR_565_LE"
	except (OSError, IOError):
		return False


_BGR = _bgr()
_copii = OrderedDict()   # cadrul original -> copia cu rosul si albastrul schimbate


def cadruBgr(cale, bgr=None):
	"""Calea de incarcat pe LCD: originalul, sau pe afisajul BGR copia lui cu rosul si albastrul schimbate."""
	if not (_BGR if bgr is None else bgr) or not cale:
		return cale
	nou = _copii.get(cale)
	if nou is not None:
		_copii.move_to_end(cale)
		return nou
	nou = cale[:-4] + ".bgr.png" if cale.endswith(".png") else cale + ".bgr.png"
	try:
		from PIL import Image
		im = Image.open(cale)
		im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
		benzi = im.split()
		Image.merge(im.mode, (benzi[2], benzi[1], benzi[0]) + tuple(benzi[3:])).save(nou, format="PNG", compress_level=1)
	except Exception as e:
		print("[HdsAfisajColor] cadrul BGR: %s" % e)
		return cale
	_copii[cale] = nou
	while len(_copii) > COPII_BGR:
		_vechi, copie = _copii.popitem(last=False)
		try:
			os.unlink(copie)
		except OSError:
			pass
	return nou


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
			self["cadru"].instance.setPixmapFromFile(cadruBgr(self._cale))

	def arataCadru(self, cale):
		if cale != self._cale:
			self._cale = cale
			if self._pregatit:
				self["cadru"].instance.setPixmapFromFile(cadruBgr(cale))
