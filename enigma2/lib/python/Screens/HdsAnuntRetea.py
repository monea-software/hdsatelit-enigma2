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
# Un text care nu incape (mesajul unui plugin extern, Components/HdsPluginExtern: patru fraze) face fereastra si textul
# mai inalte, centrate pe ecran; un text care incape lasa marimile din skin (_potriveste).

import time

from enigma import eActionMap, eTimer

from Components.Label import Label
from Components.Pixmap import Pixmap
from Screens.Screen import Screen

DURATA_MS = 6000
# CPT1: un mesaj ascuns de o tasta cu cel mult atatea secunde inainte de o captura intra in captura (o tasta colorata
# tinuta apasata porneste captura dupa ~1 s, ROSU scurt la ridicare; un mesaj inchis de om cu alta tasta nu mai revine
# dupa atat)
CAPTURA_DUPA_TASTA_S = 1.5


def _jurnal(text):
	print("[HdsAnuntRetea] %s" % text)


def _tastaDeLaEchipa():
	"""Tasta de acum e trimisa de echipa prin asistenta (Components/HdsAsistentaControl.apasaTasta), nu apasata de om;
	numai din ce e deja incarcat (fara asistenta pornita, modulul nici nu e incarcat)."""
	import sys
	C = sys.modules.get("Components.HdsAsistentaControl")
	try:
		return bool(C is not None and C.tastaDeLaEchipa())
	except Exception:
		return False


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
		# bara si marginile ferestrei din tema (numai in skinul HDSatelit); tin toata inaltimea
		for nume in ("felBara", "ramaDr", "ramaJos"):
			self[nume] = Label("")
		self.ceas = eTimer()
		self.ceas.callback.append(self.ascunde)
		self.ceasTasta = eTimer()
		self.ceasTasta.callback.append(self.ascunde)
		# ascunderea la tasta pornita mai tarziu (ascunde_la_tasta in ms)
		self.ceasLegare = eTimer()
		self.ceasLegare.callback.append(lambda: self._leaga(True))
		self.legat = False
		self._marimi = None
		# CPT1: ora ascunderii la tasta si mesajul tinut pe ecran pentru o captura
		self.ascunsDeTastaLa = None
		self.pentruCaptura = False
		_toate.append(self)

	def anunta(self, text, cheie, durata_ms=None, ascunde_la_tasta=True):
		"""Arata textul cu pictograma cheie. durata_ms: cat sta (implicit DURATA_MS); ascunde_la_tasta=False: nu
		dispare la prima tasta (tastele merg oricum mai departe); un numar (ms): dispare la prima tasta apasata dupa
		atatea milisecunde, ca o tasta apasata chiar atunci sa nu-l stearga necitit (mesajele echipei din asistenta)."""
		self["text"].setText(text)
		# un mesaj nou nu mai e cel ascuns de tasta (si nici cel tinut pentru o captura)
		self.ascunsDeTastaLa = None
		self.pentruCaptura = False
		cale = _cale_poza(cheie)
		try:
			if cale and self["pictograma"].instance is not None:
				# la marimea ecranelor HDSatelit (tema la 2K: din setul HDSatelit/2k/, ca fereastra marita de 4/3)
				import skin
				poza = skin.pozaHds(cale)
				if poza is not None:
					self["pictograma"].instance.setPixmap(poza)
					self["pictograma"].show()
			elif not cale:
				self["pictograma"].hide()
		except Exception as e:
			_jurnal("pictograma: %r" % (e,))
		self._potriveste()
		self.show()
		self.ceas.start(int(durata_ms or DURATA_MS), True)
		self.ceasLegare.stop()
		if isinstance(ascunde_la_tasta, bool) or not ascunde_la_tasta:
			self._leaga(bool(ascunde_la_tasta))
		else:
			self._leaga(False)
			self.ceasLegare.start(int(ascunde_la_tasta), True)

	def _potriveste(self):
		"""Inaltimea ferestrei dupa text: marimile din skin, iar cand textul nu incape in eticheta, eticheta si fereastra
		cresc cu cat lipseste (cel mult pana la marginile ecranului) si fereastra ramane centrata pe acelasi loc."""
		try:
			from enigma import ePoint, eSize, getDesktop
			fer, et = self.instance, self["text"].instance
			if fer is None or et is None:
				return
			if self._marimi is None:
				self._marimi = (fer.size().width(), fer.size().height(), fer.position().x(), fer.position().y(),
					et.size().width(), et.size().height())
			fl, fh, fx, fy, el, eh = self._marimi
			et.resize(eSize(el, eh))
			from Components.HdsMarireText import inaltimeText
			plus = max(0, inaltimeText(et) + 8 - eh)
			plus = min(plus, max(0, getDesktop(0).size().height() - fh - 40))
			et.resize(eSize(el, eh + plus))
			fer.resize(eSize(fl, fh + plus))
			fer.move(ePoint(fx, max(0, fy - plus // 2)))
			if self["felBara"].skinAttributes is not None:
				for nume in ("felBara", "ramaDr"):
					w = self[nume].instance
					w.resize(eSize(w.size().width(), fh + plus))
				self["ramaJos"].instance.move(ePoint(0, fh + plus - 1))
		except Exception as e:
			_jurnal("marimea mesajului: %r" % (e,))

	def ascunde(self):
		self.ceas.stop()
		self.ceasTasta.stop()
		self.ceasLegare.stop()
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
		"""Orice tasta a omului ascunde mesajul; tasta merge mai departe (0). Ascunderea se face dupa ce eActionMap a
		terminat. Tastele trimise de echipa prin asistenta (op taste, op text) nu il ascund: mesajul e pentru om."""
		if _tastaDeLaEchipa():
			return 0
		# CPT1: tasta care il ascunde poate fi chiar tasta capturii (ROSU scurt porneste captura la ridicare): ora
		# ascunderii ramane, ca mesajul sa poata intra in captura (tinePentruCaptura)
		self.ascunsDeTastaLa = time.monotonic()
		self.ceasTasta.start(0, True)
		return 0


_fereastra = [None]
# CPT1: toate ferestrele de felul acesta (cea de aici si cele ale altor module, de pilda mesajele echipei din asistenta)
_toate = []


def _tine(f):
	"""O fereastra pentru captura -> True cand captura o prinde."""
	if f.shown:
		if not f.legat:
			# mesajul nu pleaca la tasta (sau inca nu): ramane cu durata lui, captura il prinde oricum
			return True
		# pleca la tasta: ascunderea, durata si tastele asteapta captura
		f.ceasTasta.stop()
		f.ceas.stop()
		f.ceasLegare.stop()
		f._leaga(False)
	else:
		la = getattr(f, "ascunsDeTastaLa", None)
		if la is None or not 0 <= time.monotonic() - la <= CAPTURA_DUPA_TASTA_S:
			return False
		f.show()
	f.pentruCaptura = True
	return True


def tinePentruCaptura():
	"""CPT1 (Components/HdsCapturi.captureaza, pe firul enigma2): mesajul de pe ecran care pleaca la tasta ramane pana dupa
	captura, iar unul ascuns de tasta care a pornit captura (de cel mult CAPTURA_DUPA_TASTA_S) se arata din nou pentru
	ea, fara taste legate. True cand captura prinde un mesaj; dupaCaptura() ii ascunde apoi pe cei tinuti."""
	prins = False
	for f in list(_toate):
		try:
			prins = _tine(f) or prins
		except Exception as e:
			_jurnal("mesajul pentru captura: %r" % (e,))
	return prins


def dupaCaptura():
	"""Dupa captura: mesajele tinute pentru ea se ascund (tasta apasata le ascundea oricum)."""
	ascunse = False
	for f in list(_toate):
		if not getattr(f, "pentruCaptura", False):
			continue
		f.pentruCaptura = False
		f.ascunsDeTastaLa = None
		try:
			f.ascunde()
			ascunse = True
		except Exception as e:
			_jurnal("mesajul dupa captura: %r" % (e,))
	return ascunse


def arata(session, text, cheie, durata_ms=None):
	"""Arata mesajul (sau il inlocuieste pe cel de pe ecran) pentru durata_ms (implicit DURATA_MS)."""
	if not text:
		return
	try:
		if _fereastra[0] is None:
			_fereastra[0] = session.instantiateDialog(HdsAnuntRetea)
		if durata_ms:
			_fereastra[0].anunta(text, cheie, durata_ms)
		else:
			_fereastra[0].anunta(text, cheie)
	except Exception as e:
		_jurnal("arata: %r" % (e,))
