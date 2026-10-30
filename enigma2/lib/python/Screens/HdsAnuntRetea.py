# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAnuntRetea.py: mesajul mic din mijlocul ecranului cand receptorul pierde internetul sau cand internetul merge din
# nou (din 0.4.4). Cand si ce text: Components/HdsStareRetea.py (o singura data pe pierdere, numai
# cand nicio bara cu pictograma retelei nu e deschisa si receptorul nu e in standby).
#
# Fereastra e nemodala (session.instantiateDialog): nu ia tastele nimanui. Dispare singura dupa DURATA_MS sau la
# prima tasta apasata; tasta aceea merge mai departe la ce e pe ecran (bara, lista, aplicatia pe tot ecranul).
# Skinul HDSatelit o are (HdsAnuntRetea in skin.xml); in alt skin se foloseste cea de aici, scalata dupa ecran.

from enigma import eActionMap, eTimer

from Components.Label import Label
from Components.Pixmap import Pixmap
from Screens.Screen import Screen

DURATA_MS = 6000


def _jurnal(text):
	print("[HdsAnuntRetea] %s" % text)


def _cale_poza(cheie):
	"""retea/<cheie>@2x.png din skinul ales, altfel din skinul HDSatelit; "" cand nu e niciuna."""
	import os
	from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN, SCOPE_SKIN
	nume = "retea/%s@2x.png" % cheie
	for cale in (resolveFilename(SCOPE_CURRENT_SKIN, nume), resolveFilename(SCOPE_SKIN, "HDSatelit/" + nume)):
		if cale and os.path.isfile(cale):
			return cale
	return ""


class HdsAnuntRetea(Screen):
	skin = """
	<screen name="HdsAnuntRetea" resolution="1920,1080" position="center,center" size="1000,150" flags="wfNoBorder" backgroundColor="#0010162A" zPosition="10">
		<eLabel position="0,0" size="1000,2" backgroundColor="#00374EA1" zPosition="1" />
		<widget name="pictograma" position="24,39" size="96,72" alphatest="blend" zPosition="2" />
		<widget name="text" position="140,10" size="836,130" font="Regular;30" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" transparent="1" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self["pictograma"] = Pixmap()
		self["text"] = Label("")
		self.ceas = eTimer()
		self.ceas.callback.append(self.ascunde)
		self.ceasTasta = eTimer()
		self.ceasTasta.callback.append(self.ascunde)
		self.legat = False

	def anunta(self, text, cheie, durata_ms=None, ascunde_la_tasta=True):
		"""Arata textul cu pictograma cheie. durata_ms: cat sta (implicit DURATA_MS); ascunde_la_tasta=False: nu
		dispare la prima tasta (mesajele echipei din asistenta stau tot timpul lor; tastele merg oricum mai departe)."""
		self["text"].setText(text)
		cale = _cale_poza(cheie)
		try:
			if cale and self["pictograma"].instance is not None:
				from Tools.LoadPixmap import LoadPixmap
				poza = LoadPixmap(cale, cached=True)
				if poza is not None:
					self["pictograma"].instance.setPixmap(poza)
					self["pictograma"].show()
			elif not cale:
				self["pictograma"].hide()
		except Exception as e:
			_jurnal("pictograma: %r" % (e,))
		self.show()
		self.ceas.start(int(durata_ms or DURATA_MS), True)
		self._leaga(bool(ascunde_la_tasta))

	def ascunde(self):
		self.ceas.stop()
		self.ceasTasta.stop()
		self._leaga(False)
		self.hide()

	def _leaga(self, da):
		if da and not self.legat:
			eActionMap.getInstance().bindAction("", -0x7FFFFFFF, self._tasta)
			self.legat = True
		elif not da and self.legat:
			eActionMap.getInstance().unbindAction("", self._tasta)
			self.legat = False

	def _tasta(self, tasta, steag):
		"""Orice tasta ascunde mesajul; tasta merge mai departe (0). Ascunderea se face dupa ce eActionMap a terminat."""
		self.ceasTasta.start(0, True)
		return 0


_fereastra = [None]


def arata(session, text, cheie):
	"""Arata mesajul (sau il inlocuieste pe cel de pe ecran) pentru DURATA_MS."""
	if not text:
		return
	try:
		if _fereastra[0] is None:
			_fereastra[0] = session.instantiateDialog(HdsAnuntRetea)
		_fereastra[0].anunta(text, cheie)
	except Exception as e:
		_jurnal("arata: %r" % (e,))
