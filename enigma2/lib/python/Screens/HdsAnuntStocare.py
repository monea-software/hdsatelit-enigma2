# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAnuntStocare.py: fereastra anuntului de la punerea si scoaterea unui stick, hard disk sau card (din 0.8.0).
# Cand si ce text: Components/HdsAnuntStocare.py.
#
# Fereastra e nemodala (session.instantiateDialog) si sta PESTE orice ecran (zPosition 100; temele isi pun ecranele intre
# 0 si 10): nu intra in sirul ecranelor si nu ia tastele ecranului de dedesubt. Pleaca singura dupa durata ei. Cat e pe
# ecran, numai tasta Detaliilor e a ei: INFO sau EPG deschide pagina discului (randul de jos o spune). Celelalte taste merg mai departe la
# ecranul de dedesubt; dupa primele TINE_LA_TASTA_S secunde (ca o tasta apasata chiar atunci sa nu stearga anuntul necitit)
# orice alta tasta il si ascunde.

import time

from enigma import eActionMap, eTimer

from Components.Label import Label
from Screens.Screen import Screen

# tastele Detaliilor: INFO sau EPG (pe unele telecomenzi e numai una dintre ele)
KEY_INFO = 358
KEY_EPG = 365
TASTE_DETALII = (KEY_INFO, KEY_EPG)
TINE_LA_TASTA_S = 3.0


def _inStandby():
	try:
		from Screens import Standby
		return Standby.inStandby is not None
	except Exception:
		return False


class HdsAnuntStocare(Screen):
	skin = """
	<screen name="HdsAnuntStocare" resolution="1920,1080" position="center,center" size="1100,250" flags="wfNoBorder" backgroundColor="#0010162A" zPosition="100">
		<eLabel position="0,0" size="1100,2" backgroundColor="#00374EA1" zPosition="1" />
		<eLabel position="0,0" size="12,250" backgroundColor="#00374EA1" zPosition="1" />
		<widget name="text" position="36,12" size="1040,176" font="Regular;28" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" transparent="1" valign="center" zPosition="2" />
		<eLabel position="36,194" size="1040,1" backgroundColor="#00374EA1" zPosition="1" />
		<widget name="taste" position="36,200" size="1040,40" font="Regular;24" foregroundColor="#00B8C0D0" backgroundColor="#0010162A" transparent="1" valign="center" zPosition="2" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self["text"] = Label("")
		self["taste"] = Label("")
		self.ceas = eTimer()
		self.ceas.callback.append(self.ascunde)
		self.ceasTasta = eTimer()
		self.ceasTasta.callback.append(self._dupaTasta)
		self.legat = False
		self.disc = None
		self.aratatLa = 0.0
		self.infoApasat = False
		self.deschide = False

	def anunta(self, text, disc, durata_ms):
		"""disc: numele discului pentru Detalii (None: fara tasta, de pilda la scoatere)."""
		self.disc = disc
		self.deschide = False
		self["text"].setText(text)
		self.ceasTasta.stop()
		self["taste"].setText(_("INFO sau EPG: detalii și formatare") if disc else "")
		self.aratatLa = time.monotonic()
		self.show()
		self.ceas.start(int(durata_ms), True)
		self._leaga(True)

	def ascunde(self):
		self.ceas.stop()
		self.ceasTasta.stop()
		# tasta Detaliilor inca apasata (anuntul a expirat intre apasare si ridicare): legarea ramane pana la ridicare, ca
		# ridicarea sa nu ajunga la ecranul de dedesubt, care n-a vazut apasarea
		if not self.infoApasat:
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
		"""INFO sau EPG (cand anuntul are Detalii) e a ferestrei, de la apasare pana la ridicare (1 = tasta oprita aici); pagina se
		deschide la ridicare, dupa ce eActionMap a terminat. Orice alta tasta merge mai departe (0)."""
		if not self.shown:
			# anuntul a plecat cu tasta Detaliilor apasata: ridicarea ei se opreste aici si legarea se desface
			if tasta in TASTE_DETALII and steag != 1:
				return 1
			self.infoApasat = False
			self._leaga(False)
			return 1 if tasta in TASTE_DETALII else 0
		if _inStandby():
			self.infoApasat = False
			self.ceasTasta.start(0, True)
			return 0
		if self.disc and tasta in TASTE_DETALII:
			if steag == 0:
				self.infoApasat = True
			elif steag == 1 and self.infoApasat:
				self.infoApasat = False
				self.deschide = True
				self.ceasTasta.start(0, True)
			return 1
		if steag == 0 and time.monotonic() - self.aratatLa >= TINE_LA_TASTA_S:
			self.deschide = False
			self.ceasTasta.start(0, True)
		return 0

	def _dupaTasta(self):
		deschide, disc = self.deschide, self.disc
		self.deschide = False
		self.ascunde()
		if deschide and disc:
			from Components import HdsAnuntStocare as C
			C.deschideDetalii(self.session, disc)


_fereastra = [None]


def arata(session, text, disc=None, durata_ms=12000):
	"""Arata anuntul (sau il inlocuieste pe cel de pe ecran)."""
	if not text:
		return
	if _fereastra[0] is None:
		_fereastra[0] = session.instantiateDialog(HdsAnuntStocare)
	_fereastra[0].anunta(text, disc, durata_ms)
