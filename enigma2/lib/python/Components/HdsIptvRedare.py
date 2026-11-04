# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvRedare: ce se intampla cu canalul de internet pornit acum. Spune fereastra de incarcare (Screens/HdsIptvIncarcare.py) ce sa arate, din
# evenimentele playerului si din masuratorile releului (Components/HdsIptvAdrese.stareFlux), si noteaza canalele care n-au pornit, in fisierul
# lor mic (HdsIptvSurse.noteazaNefunctional): lista le arata cu un semn, fara sa se atinga buchetele.
#
# Partea de sus nu cere enigma2: hotararile (Stare) se probeaza pe PC.

import time

from Components import HdsIptvAdrese as A
from Components import HdsIptvSurse as I
from Components.HdsIptvSurse import N_

PAS_MS = 400
PRAG_ESEC_S = 30.0       # fara imagine dupa atat de la pornire: canalul nu merge (servicemp3 opreste si el la 30 s)
PAS_PORNIT_MS = 1000
PRAG_OPRIT_S = 3.0       # imaginea sta pe loc (sau, cat nu se stie pozitia, releul nu mai primeste nimic): se arata iar fereastra

T_CONECTARE = N_("Se conectează la server...")
T_INCARCARE = N_("Se încarcă canalul...")
T_PORNIRE = N_("Pornește imaginea...")
T_REINCARCARE = N_("Se reîncarcă...")


def textViteza(biti):
	"""6,2 Mb/s sau 850 kb/s, ca in restul imaginii, cu virgula."""
	if not biti:
		return u""
	if biti >= 1000000:
		return (u"%.1f Mb/s" % (biti / 1000000.0)).replace(u".", u",")
	return u"%d kb/s" % max(1, biti // 1000)


def textTampon(s):
	"""tampon 3,2 s; gol cat nu se stie viteza."""
	return (_("tampon %s s") % (u"%.1f" % s).replace(u".", u",")) if s is not None else u""


def textRaspuns(ms):
	return u"%d ms" % ms if ms is not None else u""


class Stare(object):
	"""Hotararile, fara nimic din enigma2. `ceas` si `flux` se dau in probe."""

	def __init__(self, ceas=None, flux=None):
		self.ceas = ceas or time.monotonic
		self.flux = flux or A.stareFlux
		self.sid = self.cheie = None
		self.inceput = 0.0
		self.pornit = False
		self.ultim_flux = 0.0
		self.octeti = 0
		self.esuat = False
		self.tampon_procent = None
		self.pozitie = None
		self.ultima_pozitie = 0.0

	def laStart(self, cale):
		"""Un serviciu nou. -> True daca e un canal de internet al omului."""
		self.sid, self.cheie = I.desparteCale(cale)
		self.inceput = self.ultim_flux = self.ceas()
		self.pornit = self.esuat = False
		self.octeti = 0
		self.tampon_procent = None
		self.pozitie = None
		return self.sid is not None

	def urmarit(self):
		return self.sid is not None

	def laEnd(self):
		self.sid = self.cheie = None

	def laPornit(self):
		"""Imaginea a pornit. -> canalul (sid, cheie) o singura data, ca semnul sa se stearga."""
		if self.sid is None or self.pornit:
			return None
		self.pornit = True
		return self.sid, self.cheie

	def laEsec(self):
		"""Playerul a spus ca nu poate. -> canalul, o singura data, numai daca n-a pornit niciodata."""
		if self.sid is None or self.pornit or self.esuat:
			return None
		self.esuat = True
		return self._deNotat()

	def _deNotat(self):
		"""Canalul, ca n-a pornit; None cand vina e a sursei (internet, cont, server): nu se marcheaza mii de canale."""
		if (self.flux(self.sid, self.cheie) or {}).get("eroare_sursa"):
			return None
		return self.sid, self.cheie

	def laTampon(self, procent):
		"""Numai pentru bara ferestrei: un flux venit exact in ritmul lui tine tamponul playerului jos, iar imaginea merge."""
		self.tampon_procent = procent

	def laPozitie(self, pozitie, pauza=False):
		"""Unde a ajuns imaginea (None cand nu se stie). In pauza omul a oprit-o: nu se socoteste."""
		acum = self.ceas()
		if pauza or pozitie != self.pozitie:
			self.pozitie = pozitie
			self.ultima_pozitie = acum

	def pas(self):
		"""(text sau None cand fereastra nu trebuie sa se vada, procent sau None, randul mic, canal esuat sau None)."""
		if self.sid is None or self.esuat:
			return None, None, u"", None
		acum = self.ceas()
		f = self.flux(self.sid, self.cheie) or {}
		octeti = f.get("octeti") or 0
		if octeti > self.octeti:
			self.octeti = octeti
			self.ultim_flux = acum
		mic = textViteza(f.get("viteza"))
		if self.pornit:
			if self.pozitie is not None:
				oprit = acum - self.ultima_pozitie >= PRAG_OPRIT_S
			else:
				oprit = octeti and not f.get("hls") and acum - self.ultim_flux >= PRAG_OPRIT_S
			if oprit:
				procent = self.tampon_procent if self.tampon_procent is not None and self.tampon_procent < 100 else None
				return T_REINCARCARE, procent, mic, None
			return None, None, u"", None
		if acum - self.inceput >= PRAG_ESEC_S:
			self.esuat = True
			return None, None, u"", self._deNotat()
		if f.get("raspuns_ms") is None:
			return T_CONECTARE, None, mic, None
		if not f.get("trimis"):
			return T_INCARCARE, f.get("preumplere"), mic, None
		return T_PORNIRE, None, mic, None


# ------------------------------------------------------------------ pe receptor

class Legatura(object):
	"""Fereastra si evenimentele, pe bara canalelor (Screens/InfoBarGenerics.py). Fara surse nu face nimic: un test pe cale la evStart."""

	def __init__(self, infobar):
		self.infobar = infobar
		self.session = infobar.session
		self.stare = Stare()
		self.ecran = None
		self.ceas = None
		self.urmaritor = None

	def _ceas(self):
		if self.ceas is None:
			from enigma import eTimer
			self.ceas = eTimer()
			self.ceas.callback.append(self._pas)
		return self.ceas

	def _fereastra(self):
		if self.ecran is None:
			from Screens.HdsIptvIncarcare import HdsIptvIncarcare
			self.ecran = self.session.instantiateDialog(HdsIptvIncarcare)
		return self.ecran

	def _cale(self):
		ref = self.session.nav.getCurrentlyPlayingServiceReference()
		if ref is not None and ref.valid() and ref.type != 1:
			return ref.getPath()
		service = self.session.nav.getCurrentService()
		info = service and service.info()
		if info:
			from enigma import iServiceInformation
			text = info.getInfoString(iServiceInformation.sServiceref) or ""
			parti = text.split(":")
			return parti[10].replace("%3a", ":") if len(parti) > 10 else ""
		return ""

	def _opresteSubtitrari(self):
		if self.urmaritor is not None:
			self.urmaritor.opreste()
			self.urmaritor = None

	def _subtitrari(self):
		"""Pistele WebVTT ale unui canal HLS (Components/HdsIptvSubtitrari.py): intra in meniul de subtitrari ca niste fisiere; se aduce numai
		cea aleasa."""
		piste, pts0 = A.pisteHls(self.stare.sid, self.stare.cheie)
		if not piste:
			return
		service = self.session.nav.getCurrentService()
		sub = service and service.subtitle()
		if not sub:
			return
		from Components import HdsIptvSubtitrari as S
		if self.urmaritor is None:
			self.urmaritor = S.Urmaritor(piste)
			self.urmaritor.start()
			sub.setExternalSubtitles([(p["nume"], p["limba"], S.TIP_WEBVTT, 0) for p in piste])
		u = self.urmaritor
		ales = getattr(self.infobar, "selected_subtitle", None)
		u.ales = ales[1] - 100 if ales and ales[0] == 2 and ales[1] >= 100 else None
		u.pts0 = pts0
		u.pozitie_ms = self.stare.pozitie // 90 if self.stare.pozitie is not None else None
		noi = u.noi()
		if noi:
			sub.setExternalSubtitleCues(noi[0], noi[1])

	def laStart(self):
		self._opresteSubtitrari()
		if self.stare.laStart(self._cale()):
			self._pas()
			self._ceas().start(PAS_MS, False)
		else:
			self._ascunde()

	def laEnd(self):
		self._opresteSubtitrari()
		self.stare.laEnd()
		self._ascunde()

	def laPornit(self):
		canal = self.stare.laPornit()
		if canal:
			I.stergeNefunctional(*canal)
			s = I.sursa(canal[0])
			if s and s.get("eroare"):
				# a pornit: ce scria pe cartela despre o redare nereusita nu mai e adevarat
				I.actualizeazaSursa(canal[0], eroare="")
			if self.ceas is not None:
				self.ceas.start(PAS_PORNIT_MS, False)
		self._pas()

	def laEsec(self):
		canal = self.stare.laEsec()
		if canal:
			I.noteazaNefunctional(*canal)
			self._ascunde()

	def laTampon(self):
		try:
			service = self.session.nav.getCurrentService()
			streamed = service and service.streamed()
			if streamed:
				self.stare.laTampon(streamed.getBufferCharge()[0])
		except Exception as e:
			print("[HdsIptvRedare] tamponul: %s" % type(e).__name__)
		self._pas()

	def _ascunde(self):
		if self.ceas is not None:
			self.ceas.stop()
		if self.ecran is not None:
			self.ecran.ascunde()

	def _pozitie(self):
		"""(unde a ajuns imaginea sau None, e in pauza)"""
		try:
			service = self.session.nav.getCurrentService()
			seek = service and service.seek()
			rez = seek.getPlayPosition() if seek else None
			pauza = getattr(self.infobar, "seekstate", (0,))[0] == 1
			return (rez[1] if rez and not rez[0] else None), pauza
		except Exception as e:
			print("[HdsIptvRedare] pozitia: %s" % type(e).__name__)
			return None, False

	def _pas(self):
		if not self.stare.urmarit():
			self._ascunde()
			return
		if self.stare.pornit:
			self.stare.laPozitie(*self._pozitie())
			try:
				self._subtitrari()
			except Exception as e:
				print("[HdsIptvRedare] subtitrarile: %s" % type(e).__name__)
		text, procent, mic, esuat = self.stare.pas()
		if esuat:
			I.noteazaNefunctional(*esuat)
		if text is None:
			if self.ecran is not None:
				self.ecran.ascunde()
			if esuat or self.stare.esuat:
				self._ascunde()
			return
		# peste bara (care in tema Pro e pe tot ecranul), dar nu peste lista de canale sau peste meniuri: acolo sta in randul de pe imagine
		if not getattr(self.infobar, "execing", True):
			if self.ecran is not None:
				self.ecran.ascunde()
			return
		self._fereastra().arata(_(text), procent, mic)
