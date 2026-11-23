# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsImagineDupaPlayer.py (0.7.8): primul canal din tuner dupa un player (un canal de pe internet, un film) vine cu sunet si
# fara imagine; canalul se porneste singur din nou, o data.
#
# Ce s-a vazut (AX HD51 / Mut@nt HD51 cu modul CI, asistenta 905152, forum 676): dupa un flux redat de servicemp3 (GStreamer,
# dvbvideosink pe /dev/dvb/adapter0/video0), primul canal de satelit da sunetul, decodorul citeste antetul imaginii
# (evenimentul video, 1920x1080), dar nu arata niciun cadru: PTS-ul video sta pe loc (hds-zap.log, "PTS-ul video sta pe
# loc"), minute intregi, pana la zap-ul urmator, care merge. 7 din 7 treceri flux -> canal TV din jurnalele lui; si cu tunerul
# ramas deschis (deci nu acordarea). Comenzile catre decodor sunt aceleasi ca la un zap bun, deci cauza e starea lasata de
# player in driver (nedovedita: vezi peticul optional al sursei DEMUX la deschiderea decodorului, ca in OE-Alliance).
#
# CE FACE: dupa un serviciu care nu e DVB (tipul referintei nu e 1: 4097 GStreamer, 5001/5002 ServiceApp, orice player, si
# filmele de pe disc), pe primul canal TV din tuner (tip 1, fara cale, nu radio), cand
#   - evenimentul video a venit (antetul imaginii citit, deci descifrarea merge; fara eveniment nimic: zap-urile prin modulul
#     CI de dupa pornire dau imaginea la 10-12 s fara eveniment, si acolo nu e nimic blocat),
#   - PTS-ul video (getInfo(sUser + 40), lib/service/servicedvb.cpp) e bun si nu s-a miscat deloc PRAG_BLOCAT_S dupa
#     eveniment (zap-urile bune pe HD51, si prin modulul CI: cadrele la cel mult ~1,1 s dupa eveniment),
#   - iar PTS-ul s-a vazut miscandu-se dupa eveniment pe un canal din tuner in pornirea de acum a interfetei (o placa unde
#     PTS-ul nu se misca niciodata nu porneste nimic, scrie numai randul),
# canalul se porneste din nou (Navigation.playService cu forceRestart: ce face omul cu un canal mai sus si inapoi), o singura
# data pe trecere. Fara mesaj pe ecran si fara setare: omul vede bara canalului si imaginea.
# Nu: radio, timeshift sau pauza, standby, alt canal ales intre timp; PiP are alt decodor si nu trece pe aici.
#
# IN hds-zap.log (componenta zap, modulul decodor):
#   AVERT "imaginea sta dupa un player (tip 4097): eveniment video la 5,4 s, PTS-ul video pe loc 5,0 s (video P, sunet S,
#          sunet-video D ms); canalul pornit din nou singur, o data | canal: ref=..."
#   INFO  "dupa pornirea din nou: imaginea a venit la 4,9 s" sau AVERT "dupa pornirea din nou: tot fara imagine dupa 20,0 s".
# PTS-ul sunetului (getInfo(sUser + 41), din 0.7.8) e numai pentru rand: un PTS video departe de cel al sunetului spune un
# cadru vechi ramas in decodor, unul aproape spune un cadru care asteapta ceasul decodorului. Pe un nucleu fara cheie: "?".
#
# Partea de sus (Decizie) nu cere enigma2: probele pe PC, teste/test_ipz_imagine_dupa_player_078.py (depozitul de unelte).

import time

PRAG_BLOCAT_S = 5.0           # PTS-ul video pe loc atat dupa evenimentul video: imaginea sta
MIN_CITIRI = 3                # citiri bune dupa eveniment, toate cu acelasi PTS, inainte de pornirea din nou
ASTEAPTA_CITIRI_S = 3.0       # dupa prag, cat se mai asteapta citirile bune care lipsesc
ASTEAPTA_EVENIMENT_S = 20.0   # fara eveniment video atat de la pornirea canalului: nu se mai urmareste
INVATA_FARA_EVENIMENT = 3     # atatea zap-uri la rand fara eveniment video: placa nu-l trimite, nu se mai invata
URMARESTE_DUPA_S = 20.0       # dupa pornirea din nou: cat se asteapta imaginea pentru randul din jurnal
PAS_MS = 500                  # citirea PTS-ului, numai cat se urmareste un canal
MAX_RANDURI_ORA = 20
INFO_PTS_VIDEO = 40           # iServiceInformation.sUser + 40 (servicedvb.cpp)
INFO_PTS_SUNET = 41           # iServiceInformation.sUser + 41 (servicedvb.cpp, din 0.7.8)
TIP_DVB = "1"
STYPE_RADIO = (2, 10)
INFO = "INFO"
AVERT = "AVERT"

ARMAT = "armat"               # dupa un player: se poate porni din nou
INVATA = "invata"             # se afla numai daca PTS-ul se misca pe acest receptor
URMARIRE = "urmarire"         # dupa pornirea din nou: numai randul din jurnal


def desparteRef(text):
	"""Referinta (text) -> (tip, stype, cale); ("", -1, "") cand nu se poate citi."""
	p = (text or "").split(":")
	if len(p) < 10:
		return "", -1, ""
	try:
		stype = int(p[2] or "0", 16)
	except ValueError:
		stype = -1
	return p[0].strip(), stype, (p[10] if len(p) > 10 else "").strip()


def eTvDinTuner(text):
	"""Un canal TV din tuner: tip 1, fara cale (nu flux IPTV prin servicedvb, nu inregistrare), nu radio."""
	tip, stype, cale = desparteRef(text)
	return tip == TIP_DVB and not cale and stype >= 0 and stype not in STYPE_RADIO


def secunde(s):
	"""2.25 -> "2,2" (virgula: patru numere cu punct ar parea o adresa filtrelor jurnalului)."""
	return ("%.1f" % s).replace(".", ",")


def textPts(video, sunet):
	"""Partea cu PTS-urile din randul de avertisment."""
	if sunet is None or sunet <= 0:
		return "video %d, sunet ?" % video
	d = (sunet - video) & 0x7fffffff
	if d >= 0x40000000:
		d -= 0x80000000
	return "video %d, sunet %d, sunet-video %+d ms" % (video, sunet, int(round(d / 90.0)))


class Decizie(object):
	"""Starea urmaririi, fara nimic din enigma2. ceas(): secunde, monoton."""

	def __init__(self, ceas=None):
		self.ceas = ceas or time.monotonic
		self.tip_dinainte = None      # tipul referintei pornite inainte in fereastra principala
		self.dovedit = False          # PTS-ul video s-a vazut miscandu-se dupa eveniment pe un canal din tuner
		self.repornit = None          # (referinta, ora, tipul playerului) pornita din nou de aici, pana la evStart-ul ei
		self.fara_eveniment = 0       # zap-uri la rand urmarite fara eveniment video
		self._gol()

	def _gol(self):
		self.ref = None
		self.stare = None
		self.dupa = None              # tipul playerului de dinainte
		self.t0 = None
		self.t_ev = None
		self.pts = None               # PTS-ul video citit dupa eveniment
		self.citiri = 0               # citiri bune dupa eveniment, toate cu acelasi PTS
		self.t_repornire = None

	def activ(self):
		return self.stare is not None

	def laStart(self, ref_text):
		"""evStart in fereastra principala. -> True cand canalul se urmareste (citirile PTS-ului pornesc)."""
		tip = desparteRef(ref_text)[0]
		dinainte, self.tip_dinainte = self.tip_dinainte, tip
		repornit, self.repornit = self.repornit, None
		self._gol()
		if not eTvDinTuner(ref_text):
			return False
		if repornit is not None and repornit[0] == ref_text:
			self.stare, self.dupa, self.t_repornire = URMARIRE, repornit[2], repornit[1]
		elif dinainte and dinainte != TIP_DVB:
			self.stare, self.dupa = ARMAT, dinainte
		elif not self.dovedit and self.fara_eveniment < INVATA_FARA_EVENIMENT:
			self.stare = INVATA
		else:
			return False
		self.ref = ref_text
		self.t0 = self.ceas()
		return True

	def laEnd(self):
		"""evEnd: canalul s-a oprit (zap, standby, iesire); o pornire din nou ceruta de aici ramane pana la evStart."""
		self._gol()

	def laEveniment(self):
		"""evVideoSizeChanged: antetul imaginii citit; de acum se numara citirile PTS-ului."""
		if self.stare is not None and self.t_ev is None:
			self.fara_eveniment = 0
			self.t_ev = self.ceas()
			self.pts = None
			self.citiri = 0

	def marcheazaRepornirea(self):
		"""Pornirea din nou se cere acum: evStart-ul aceleiasi referinte o urmareste (fara alta pornire)."""
		self.repornit = (self.ref, self.ceas(), self.dupa)
		self._gol()

	def pas(self, pts, pts_sunet=None, blocat=False):
		"""O citire. pts: PTS-ul video (<= 0 sau None = necitit), pts_sunet la fel, blocat: standby, timeshift sau pauza.
		-> None (citirile continua) sau (fapta, rand): fapta "gata" (citirile se opresc) sau "reporneste" (canalul se
		porneste din nou); rand = (nivel, text) de scris in jurnal, sau None."""
		if self.stare is None:
			return ("gata", None)
		if blocat:
			self._gol()
			return ("gata", None)
		acum = self.ceas()
		stare = self.stare
		if self.t_ev is None:
			if acum - self.t0 < ASTEAPTA_EVENIMENT_S:
				return None
			rand = None
			if stare == URMARIRE:
				rand = (AVERT, "dupa pornirea din nou: fara eveniment video in %s s" % secunde(acum - self.t_repornire))
			self.fara_eveniment += 1
			self._gol()
			return ("gata", rand)
		bun = pts is not None and pts > 0
		if bun and self.pts is not None and pts != self.pts:
			self.dovedit = True
			rand = None
			if stare == URMARIRE:
				rand = (INFO, "dupa pornirea din nou: imaginea a venit la %s s (PTS-ul video se misca)" %
					secunde(acum - self.t_repornire))
			self._gol()
			return ("gata", rand)
		if bun:
			self.pts = pts
			self.citiri += 1
		blocat_de = acum - self.t_ev
		if stare == URMARIRE:
			if acum - self.t_repornire < URMARESTE_DUPA_S:
				return None
			rand = (AVERT, "dupa pornirea din nou: tot fara imagine dupa %s s" % secunde(acum - self.t_repornire))
			self._gol()
			return ("gata", rand)
		if blocat_de < PRAG_BLOCAT_S:
			return None
		if self.citiri < MIN_CITIRI:
			if blocat_de < PRAG_BLOCAT_S + ASTEAPTA_CITIRI_S:
				return None
			self._gol()
			return ("gata", None)
		if stare == INVATA:
			self._gol()
			return ("gata", None)
		text = "imaginea sta dupa un player (tip %s): eveniment video la %s s, PTS-ul video pe loc %s s (%s)" % (
			self.dupa, secunde(self.t_ev - self.t0), secunde(blocat_de), textPts(self.pts, pts_sunet))
		if not self.dovedit:
			self._gol()
			return ("gata", (AVERT, text + "; nimic pornit: PTS-ul video nu s-a vazut inca miscandu-se pe acest receptor"))
		return ("reporneste", (AVERT, text + "; canalul pornit din nou singur, o data"))


# ------------------------------------------------------------------ legatura cu enigma2 (numai pe receptor)

def _refAcum(nav):
	"""Referinta serviciului pornit acum: intai cea data de serviciu (la evStart Navigation n-a pus-o inca), apoi a lui
	Navigation. -> text sau None."""
	try:
		from enigma import iServiceInformation
		service = nav.getCurrentService()
		info = service and service.info()
		text = info and info.getInfoString(iServiceInformation.sServiceref)
		if text:
			return text
	except Exception:
		pass
	try:
		ref = nav.getCurrentlyPlayingServiceReference()
		return ref.toString() if ref is not None else None
	except Exception:
		return None


def _standby():
	try:
		import Screens.Standby
		return Screens.Standby.inStandby is not None or bool(Screens.Standby.inTryQuitMainloop)
	except Exception:
		return False


def _pauza(service):
	"""Timeshift pornit sau pauza ceruta de om pe bara canalului."""
	try:
		ts = service and service.timeshift()
		if ts and ts.isTimeshiftActive():
			return True
	except Exception:
		pass
	try:
		from Screens.InfoBar import InfoBar
		bara = InfoBar.instance
		return bara is not None and getattr(bara, "seekstate", (0,))[0] == 1
	except Exception:
		return False


class Legatura(object):
	"""Ascultatorul din Navigation.dispatchEvent. Probele dau ceasul, temporizatorul si scriitorul jurnalului."""

	def __init__(self, ceas=None, temporizator=None, scrie=None):
		self.decizie = Decizie(ceas)
		self.ceas = ceas or time.monotonic
		self._temporizator = temporizator
		self._scrie = scrie
		self._ora = []
		self.nav = None

	def _ceasPornit(self, porneste):
		if self._temporizator is None:
			if not porneste:
				return
			from enigma import eTimer
			self._temporizator = eTimer()
			self._temporizator.callback.append(self._pasSigur)
		if porneste:
			self._temporizator.start(PAS_MS, False)
		else:
			self._temporizator.stop()

	def _rand(self, nivel, text, ref=None):
		acum = self.ceas()
		self._ora = [t for t in self._ora if acum - t < 3600]
		if len(self._ora) >= MAX_RANDURI_ORA:
			return
		self._ora.append(acum)
		canal = {"ref": ref} if ref else None
		if self._scrie is not None:
			self._scrie(nivel, text, canal)
			return
		from Components import HdsJurnal
		if nivel == AVERT:
			HdsJurnal.avert("zap", "decodor", text, canal)
		else:
			HdsJurnal.info("zap", "decodor", text)

	def eveniment(self, nav, ev):
		from enigma import iPlayableService
		self.nav = nav
		if ev == iPlayableService.evStart:
			self._ceasPornit(self.decizie.laStart(_refAcum(nav)))
		elif ev == iPlayableService.evEnd:
			self.decizie.laEnd()
			self._ceasPornit(False)
		elif ev == iPlayableService.evVideoSizeChanged:
			self.decizie.laEveniment()

	def _pasSigur(self):
		"""Chemat de eTimer: o exceptie de aici ar ajunge in C++ (ePython::call), deci nu iese niciodata."""
		try:
			self.pas()
		except Exception as e:
			try:
				print("[HdsImagineDupaPlayer] pas: %r" % (e,))
			except Exception:
				pass

	def pas(self):
		nav = self.nav
		if nav is None or not self.decizie.activ():
			self._ceasPornit(False)
			return
		from enigma import iServiceInformation
		service = nav.getCurrentService()
		info = service and service.info()
		video = info.getInfo(iServiceInformation.sUser + INFO_PTS_VIDEO) if info else -2
		sunet = info.getInfo(iServiceInformation.sUser + INFO_PTS_SUNET) if info else -2
		ref_text = self.decizie.ref
		rez = self.decizie.pas(video, sunet, _standby() or _pauza(service))
		if rez is None:
			return
		fapta, rand = rez
		self._ceasPornit(False)
		if fapta != "reporneste":
			if rand is not None:
				self._rand(rand[0], rand[1], ref_text)
			return
		ref = nav.getCurrentlyPlayingServiceReference()
		vpid = info.getInfo(iServiceInformation.sVideoPID) if info else -1
		if ref is None or vpid is None or vpid <= 0:
			self.decizie.laEnd()
			return
		self._rand(rand[0], rand[1], ref_text)
		self.decizie.marcheazaRepornirea()
		try:
			nav.playService(ref, checkParentalControl=False, forceRestart=True, adjust=False)
		except TypeError:
			nav.playService(ref, forceRestart=True)


_legatura = None


def eveniment(nav, ev):
	"""Din Navigation.dispatchEvent: un eveniment al serviciului principal. Nu arunca niciodata."""
	global _legatura
	try:
		if _legatura is None:
			_legatura = Legatura()
		_legatura.eveniment(nav, ev)
	except Exception as e:
		try:
			print("[HdsImagineDupaPlayer] %r" % (e,))
		except Exception:
			pass
