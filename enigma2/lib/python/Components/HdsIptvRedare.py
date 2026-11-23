# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIptvRedare: ce se intampla cu canalul de internet pornit acum. Spune fereastra de incarcare (Screens/HdsIptvIncarcare.py) ce sa arate, din
# evenimentele playerului si din masuratorile releului (Components/HdsIptvAdrese.stareFlux), si noteaza canalele care n-au pornit, in fisierul
# lor mic (HdsIptvSurse.noteazaNefunctional): lista le arata cu un semn, fara sa se atinga buchetele.
#
# PRIMA IMAGINE: fereastra se inchide cand PTS-ul decodorului (VIDEO_GET_PTS pe un descriptor video0 deschis numai pentru citire) se
# misca. Unele drivere refuza ioctl-ul pe un astfel de descriptor (ZGEMMA H8.2H Plus, hi3716mv430: EPERM de fiecare data, cat
# dvbvideosink tine decodorul); atunci fereastra statea „Pornește redarea...” 30 s si peste canalele care aveau imagine dupa 3 s.
# Numai cand ioctl-ul e refuzat (PTS_REFUZAT), imaginea se judeca dupa ce spune playerul: marimea imaginii cunoscuta si pozitia
# redarii care a crescut cu AVANS_FARA_PTS. Unde PTS-ul se citeste (Vu+, Viper, SF8008...) nimic nu se schimba.
#
# Partea de sus nu cere enigma2: hotararile (Stare) se probeaza pe PC.

import time

from Components import HdsIptvAdrese as A
from Components import HdsIptvSurse as I
from Components.HdsIptvSurse import N_

PAS_MS = 400
PRAG_ESEC_S = 30.0       # fara imagine dupa atat de la pornire: canalul nu merge (servicemp3 opreste si el la 30 s)
PAS_PORNIT_MS = 1000
# IPF1 (0.7.9): evBuffering (GST_MESSAGE_BUFFERING din servicemp3) vine la IPTV de 25-186 de ori pe secunda (masurat pe ZGEMMA H8.2H Plus
# cu un contor in Navigation.dispatchEvent, |RX| Cute Baby Animals, 4 Mb/s), iar laTampon chema la fiecare _pas (serviciul, pozitia
# din player, decodorul, subtitrarile), ~20 ms pe acel procesor: firul principal statea 0,9-1 s din fiecare secunda in ascultatori,
# deci tastele, pagina web si bataia paznicului asteptau 4-120 s (paznicul a repornit interfata dupa 125 s fara bataie). _pas il cheama
# oricum ceasul (PAS_MS pana la prima imagine, PAS_PORNIT_MS dupa); laTampon tine minte numai incarcarea tamponului (bara ferestrei),
# cel mult o data la CITIRE_TAMPON_S, iar una sarita o citeste ceasul la urmatorul _pas.
CITIRE_TAMPON_S = 0.5  # Eduard 23.11.2026: 2 pe secunda (IPF1 pusese 5)
PRAG_OPRIT_S = 3.0       # imaginea sta pe loc (sau, cat nu se stie pozitia, releul nu mai primeste nimic): se arata iar fereastra
PTS_REFUZAT = -1         # _ptsVideo: driverul refuza VIDEO_GET_PTS pe descriptorul de citire (None = inca nu se stie)
AVANS_FARA_PTS = 45000   # 0,5 s (ceasul de 90 kHz): cat trebuie sa creasca pozitia redarii, cu marimea imaginii stiuta, cand PTS_REFUZAT
# errno-urile cu care un driver spune ca nu da deloc PTS-ul pe un descriptor deschis numai pentru citire (masurat: EPERM pe ZGEMMA H8).
# EINVAL si EBUSY nu: pot fi „nu acum”, inainte de pornirea decodorului, iar pe celelalte placi purtarea ramane cea de dinainte
_ERRNO_REFUZ = ("EPERM", "EACCES", "ENOTTY", "EOPNOTSUPP", "ENOSYS")

T_CONECTARE = N_("Se conectează la server...")
T_INCARCARE = N_("Se încarcă canalul...")
T_PORNIRE = N_("Pornește redarea...")
T_REINCARCARE = N_("Se reîncarcă...")
# canalele 4K pe receptoarele care redau cel mult 1080p (Components/HdsIptvFullHd.py, releul: HdsIptvAdrese.inlocuireFullHd)
T_FULL_HD_PERECHE = N_("Receptorul tău redă cel mult Full HD (1080p), așa că pornește același canal fără 4K: %s.")
# fara pereche masurata sub 4K: numai ce se stie sigur (o pereche nemasurata poate fi si ea 4K)
T_FULL_HD_4K = N_("Canalul acesta e 4K, iar receptorul tău redă cel mult Full HD (1080p).")
MESAJ_FULL_HD_S = 8
REPETARE_MESAJ_4K_S = 120  # acelasi canal 4K pornit din nou la rand (reconectarea): randul despre el nu se repeta mai des; alt canal sterge semnul

_fereastra_esec_notat = False
_executor_disc = None
_executor_video = None
_video_in_curs = None
_mesaj_4k = (None, 0.0)   # (canalul 4K si ce i s-a spus, cand): REPETARE_MESAJ_4K_S
_fond_4k = None           # fereastra neagra sub mesajul 4K (IPF1)


def _fondNegru(session, arata):
	"""IPF1 (0.7.9): sub mesajul "Canalul acesta e 4K..." ramanea cadrul inghetat al canalului de dinainte (Ultima imagine), de parca
	ar fi mers acela. Acum ecran negru sub mesaj (fondul din Screens/HdsEcranNegru, nemodal, sub bare si ferestre, fara taste), pana
	vine evEnd sau porneste orice alt serviciu (Legatura.laEnd, chemat si din laStart)."""
	global _fond_4k
	try:
		if arata:
			if _fond_4k is None:
				from Screens.HdsEcranNegru import HdsEcranNegruFond
				_fond_4k = session.instantiateDialog(HdsEcranNegruFond)
			_fond_4k.show()
		elif _fond_4k is not None:
			_fond_4k.hide()
	except Exception as e:
		print("[HdsIptvRedare] fondul negru: %s" % type(e).__name__)


def _inFundal(functie, *args):
	"""Citirile video nu asteapta notarea pe disc; fara obiecte enigma2."""
	global _executor_disc, _executor_video, _video_in_curs
	from concurrent.futures import ThreadPoolExecutor
	if functie is _citesteVideo:
		if _video_in_curs is not None and not _video_in_curs.done():
			# Nu adunam cereri la fiecare zap in spatele unui driver blocat.
			raise RuntimeError("video busy")
		if _executor_video is None:
			_executor_video = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hds-iptv-video")
		_video_in_curs = _executor_video.submit(functie, *args)
		return _video_in_curs
	if _executor_disc is None:
		_executor_disc = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hds-iptv-redare")
	return _executor_disc.submit(functie, *args)


def _citesteVideo(tip, video, marime):
	from Components.HdsIptvReconectare import redaServiceApp
	if video < 0 and marime and redaServiceApp(tip):
		video = 1
	return _ptsVideo(), video


def _pornireInCurs(infobar):
	"""Components/HdsIptvReconectare a programat pornirea din nou a canalului care n-a dat inca imagine (IPT8)."""
	try:
		from Components import HdsIptvReconectare as R
		return R.pornireInCurs(infobar)
	except Exception:
		return False


def _notaPornit(canal, durata):
	try:
		I.stergeNefunctional(*canal)
		if not _eArhiva(canal[1]):
			I.notaPornire(canal[0], canal[1], durata)
		s = I.sursa(canal[0])
		if s and s.get("eroare"):
			I.actualizeazaSursa(canal[0], eroare="")
	except Exception as e:
		print("[HdsIptvRedare] notarea pornirii: %s" % type(e).__name__)


def _notaEsuat(canal, codec):
	try:
		I.noteazaNefunctional(canal[0], canal[1], canal[2], codec)
	except Exception as e:
		print("[HdsIptvRedare] notarea esecului: %s" % type(e).__name__)


def _refuz(eroare):
	"""True cand OSError-ul spune ca driverul nu da PTS-ul pe un descriptor de citire (vezi _ERRNO_REFUZ)."""
	import errno
	return errno.errorcode.get(getattr(eroare, "errno", None)) in _ERRNO_REFUZ


def _ptsVideo():
	"""PTS-ul imaginii afisate, prin VIDEO_GET_PTS al decodorului nativ; None cand nu se stie inca, PTS_REFUZAT cand driverul il
	refuza pe un descriptor deschis numai pentru citire (ZGEMMA H8: EPERM)."""
	try:
		import array
		import fcntl
		import os
		import platform
		# MIPS are alt bit _IOC_READ decat ARM si x86.
		cerere = 0x40086f39 if platform.machine().lower().startswith("mips") else 0x80086f39
		try:
			fd = os.open("/dev/dvb/adapter0/video0", os.O_RDONLY | os.O_NONBLOCK)
		except OSError as e:
			return PTS_REFUZAT if _refuz(e) else None
		try:
			pts = array.array("Q", [0])
			try:
				fcntl.ioctl(fd, cerere, pts, True)
			except OSError as e:
				return PTS_REFUZAT if _refuz(e) else None
			return int(pts[0]) if pts[0] < (1 << 33) else None
		finally:
			os.close(fd)
	except (ImportError, OSError, ValueError):
		return None


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


def _eArhiva(cheie):
	"""Cheia unei emisiuni din arhiva furnizorului (Components/HdsIptvClient.eArhiva, 0.7.5 IPI), nu a unui canal."""
	try:
		from Components import HdsIptvClient as C
		return bool(getattr(C, "eArhiva", lambda c: False)(cheie))
	except Exception:
		return False


def _motiv(f):
	"""Motivul pe scurt (HdsIptvSurse.MOTIVE) din masuratorile releului: ce a spus serverul, altfel ce s-a vazut."""
	if f.get("motiv"):
		return f["motiv"]
	if f.get("raspuns_ms") is None:
		return "server"
	if not f.get("octeti"):
		return "gol"
	return "format"           # fluxul a venit, dar imaginea n-a pornit


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
		self.full_hd_spus = False

	def laStart(self, cale):
		"""Un serviciu nou. -> True daca e un canal de internet al omului."""
		self.sid, self.cheie = I.desparteCale(cale)
		self.inceput = self.ultim_flux = self.ceas()
		self.pornit = self.esuat = False
		self.octeti = 0
		self.tampon_procent = None
		self.pozitie = None
		self.ultima_pozitie = self.inceput
		self.full_hd_spus = False
		return self.sid is not None

	def urmarit(self):
		return self.sid is not None

	def fullHd(self):
		"""Ce a facut releul cu un canal 4K pe un receptor Full HD (HdsIptvAdrese.inlocuireFullHd), o singura data pe pornire:
		("pereche", numele canalului adus) sau ("4k", "") sau None."""
		if self.sid is None or self.full_hd_spus:
			return None
		f = self.flux(self.sid, self.cheie) or {}
		fel = f.get("full_hd")
		if fel not in ("pereche", "4k"):
			return None
		self.full_hd_spus = True
		return fel, f.get("nume_full_hd") or ""

	def laEnd(self):
		self.sid = self.cheie = None

	def laPornit(self):
		"""Imaginea a pornit. -> canalul (sid, cheie) o singura data, ca semnul sa se stearga."""
		if self.sid is None or self.pornit or self.esuat:
			return None
		self.pornit = True
		self.ultim_flux = self.ultima_pozitie = self.ceas()
		return self.sid, self.cheie

	def laEsec(self):
		"""Playerul a spus ca nu poate. -> canalul, o singura data, numai daca n-a pornit niciodata."""
		if self.sid is None or self.pornit or self.esuat:
			return None
		self.esuat = True
		return self._deNotat()

	def _deNotat(self):
		"""(sid, cheie, motiv), ca n-a pornit; None cand vina e a sursei (internet, cont, server): nu se marcheaza mii de canale."""
		f = self.flux(self.sid, self.cheie) or {}
		if f.get("eroare_sursa"):
			return None
		return self.sid, self.cheie, _motiv(f)

	def durata(self):
		"""Secunde de la pornirea serviciului pana acum (la laPornit: cat a durat pornirea)."""
		return self.ceas() - self.inceput

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
		self.fereastra_esuata = False
		self.inchis = False
		# EXL6: fereastra inchisa de om cu EXIT tinut apasat, pana la urmatoarea pornire de canal (laStart)
		self.inchisa_de_om = False
		self._harta_exit = None
		self._exit_legat = False
		self.generatie = 0
		self._callback_ceas = None
		self._callback_ecran = None
		self.serviciu = self.referinta = None
		self.pts_video = self.pozitie_audio = None
		self.marime = False          # playerul stie marimea imaginii (sVideoWidth si sVideoHeight > 0)
		self.baza_fara_pts = None    # pozitia de la care se masoara AVANS_FARA_PTS, cand driverul refuza PTS-ul
		self._citire_video = None
		self._notari = []
		self.tip = 4097
		self._tampon_la = None       # cand s-a citit ultima oara incarcarea tamponului (laTampon)
		self._tampon_sarit = False   # un evBuffering sarit: il citeste ceasul la urmatorul _pas
		if hasattr(infobar, "onClose"):
			infobar.onClose.append(self.inchide)

	def _ceas(self):
		if self._callback_ceas is None:
			from enigma import eTimer
			self.ceas = eTimer()
			generatie = self.generatie
			self._callback_ceas = lambda: self._pas() if generatie == self.generatie and not self.inchis else None
			self.ceas.callback.append(self._callback_ceas)
		return self.ceas

	def _fereastra(self):
		from Components.config import config
		if not getattr(getattr(config.usage, "hds_iptv_fereastra", None), "value", True):
			if self.ecran is not None:
				self.ecran.ascunde()
			return None
		if self.fereastra_esuata:
			return None
		if self.ecran is None:
			try:
				from Screens.HdsIptvIncarcare import HdsIptvIncarcare
				self.ecran = self.session.instantiateDialog(HdsIptvIncarcare)
				if hasattr(self.ecran, "onClose"):
					ecran = self.ecran
					self._callback_ecran = lambda: self._fereastraInchisa(ecran)
					self.ecran.onClose.append(self._callback_ecran)
				# EXL6: cand fereastra se ascunde (din orice loc), tasta lunga nu mai e legata
				if hasattr(self.ecran, "onHide"):
					self.ecran.onHide.append(lambda: self._tastaExit(False))
			except Exception as err:
				self.fereastra_esuata = True
				global _fereastra_esec_notat
				if not _fereastra_esec_notat:
					_fereastra_esec_notat = True
					print("[HdsIptvRedare] " + _("Fereastra de încărcare IPTV nu poate fi deschisă (%s); redarea continuă fără ea.") % type(err).__name__)
				return None
		return self.ecran

	def _tastaExit(self, legata):
		"""EXL6: EXIT tinut apasat (contextul HdsIptvFereastraActions) legat cat fereastra se vede si optiunea e Da."""
		try:
			if legata:
				from Components.config import config
				if not getattr(getattr(config.usage, "hds_iptv_fereastra_exit", None), "value", False):
					legata = False
			if legata == self._exit_legat:
				return
			if self._harta_exit is None:
				from Components.ActionMap import ActionMap
				self._harta_exit = ActionMap(["HdsIptvFereastraActions"], {"inchideFereastra": self._exitLung}, -1)
			if legata:
				self._harta_exit.execBegin()
			else:
				self._harta_exit.execEnd()
			self._exit_legat = legata
		except Exception as e:
			print("[HdsIptvRedare] EXIT lung: %s" % type(e).__name__)

	def _exitLung(self):
		"""EXIT tinut apasat peste fereastra: o inchide pana la urmatorul canal; canalul se incarca mai departe la fel."""
		from Components.config import config
		if self.ecran is None or not getattr(getattr(config.usage, "hds_iptv_fereastra_exit", None), "value", False):
			self._tastaExit(False)
			return 0
		self.inchisa_de_om = True
		self.ecran.ascunde()
		self._tastaExit(False)
		return 1

	def _fereastraInchisa(self, ecran):
		if self.ecran is not ecran:
			return
		# Screen parcurge direct onClose; nu modificam lista in timpul parcurgerii.
		self._callback_ecran = None
		self.ecran = None
		self.laEnd()

	def inchide(self):
		self.inchis = True
		self.laEnd()
		self._tastaExit(False)
		if self.ecran is not None:
			inchideri = getattr(self.ecran, "onClose", [])
			if self._callback_ecran in inchideri:
				inchideri.remove(self._callback_ecran)
			self._callback_ecran = None
			self.session.deleteDialog(self.ecran)
			self.ecran = None

	def _identitate(self):
		"""Instanta serviciului si referinta, inclusiv la repornirea aceluiasi canal."""
		nav = getattr(self.session, "nav", None)
		if nav is None:
			return None, None
		service = nav.getCurrentService()
		ref = nav.getCurrentlyPlayingServiceReference()
		return (service.getPtrString() if service else None), (ref.toString() if ref else None)

	def _curent(self):
		if self.inchis or not self.stare.urmarit() or self.stare.esuat:
			return False
		try:
			acum = self._identitate()
		except Exception:
			acum = None
		if acum is not None and acum[0] == self.serviciu and self.referinta is None:
			# Referinta poate fi publicata de Navigation abia dupa evStart.
			self.referinta = acum[1]
		if acum != (self.serviciu, self.referinta):
			self.laEnd()
			return False
		return True

	def _videoNou(self):
		"""Culege numai o citire terminata; una singura poate astepta in coada."""
		video, marime = self._pisteVideo()
		self.marime = marime
		if video == 0:
			# Serviciul audio nu depinde de decodorul video.
			return True, None, 0
		if self._citire_video is None:
			try:
				nav = getattr(self.session, "nav", None)
				ref = nav.getCurrentlyPlayingServiceReference() if nav else None
				self.tip = getattr(ref, "type", self.tip)
				self._citire_video = _inFundal(_citesteVideo, self.tip, video, marime)
			except Exception:
				return False, None, -1
		if not self._citire_video.done():
			return False, None, -1
		citire, self._citire_video = self._citire_video, None
		try:
			pts, video = citire.result()
			return True, pts, video
		except Exception:
			return True, None, -1

	def _pisteVideo(self):
		"""Informatii ale serviciului, capturate pe firul principal INAINTE de citirea PTS: (pistele video, playerul stie marimea
		imaginii). Marimea se cere numai cand trebuie: cat pistele nu se stiu (_citesteVideo) si, cand driverul refuza PTS-ul, pana la
		prima imagine (_pornitFaraPts); altfel ca inainte, fara citiri in plus pe firul principal."""
		try:
			from enigma import iServiceInformation
			service = self.session.nav.getCurrentService()
			info = service and service.info()
			video = info.getInfo(iServiceInformation.sUser + 17) if info is not None else -1
			vreau = video < 0 or (self.pts_video == PTS_REFUZAT and not self.stare.pornit)
			marime = bool(vreau and info is not None and info.getInfo(iServiceInformation.sVideoWidth) > 0
				and info.getInfo(iServiceInformation.sVideoHeight) > 0)
			return video, marime
		except Exception:
			return -1, False

	def _primulCadru(self, nou, pts, video):
		"""PTS video nou; pozitia audio numai cand serviciul confirma lipsa pistelor video."""
		if video < 0:
			# Pana la preroll, decodorul poate pastra cadrele serviciului dinainte.
			if nou:
				self.pts_video = pts
			return False
		if video == 0:
			pozitie, pauza = self._pozitie()
			veche = self.pozitie_audio
			self.pozitie_audio = pozitie
			return not pauza and pozitie is not None and veche is not None and pozitie > veche
		if not nou:
			return False
		vechi = self.pts_video
		self.pts_video = pts
		if pts == PTS_REFUZAT:
			return self._pornitFaraPts()
		return pts is not None and pts > 0 and vechi is not None and pts != vechi

	def _pornitFaraPts(self):
		"""Driverul nu da PTS-ul (PTS_REFUZAT): imaginea a pornit cand playerul stie marimea ei si pozitia redarii a crescut cu
		AVANS_FARA_PTS de atunci. In pauza, fara pozitie sau fara marime se ia de la capat; o pozitie care scade e o baza noua."""
		pozitie, pauza = self._pozitie()
		if pauza or pozitie is None or not self.marime:
			self.baza_fara_pts = None
			return False
		if self.baza_fara_pts is None or pozitie < self.baza_fara_pts:
			self.baza_fara_pts = pozitie
			return False
		return pozitie - self.baza_fara_pts >= AVANS_FARA_PTS

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
			urmaritor = self.urmaritor
			self.urmaritor = None
			try:
				urmaritor.opreste()
			except Exception as e:
				print("[HdsIptvRedare] oprirea subtitrarilor: %s" % type(e).__name__)

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
		if self.inchis:
			return
		self.laEnd()
		self.inchisa_de_om = False
		eIptv = self.stare.laStart(self._cale())
		global _mesaj_4k
		if _mesaj_4k[0] is not None and _mesaj_4k[0][:2] != (self.stare.sid, self.stare.cheie):
			# alt canal: la intoarcerea pe canalul 4K randul se spune din nou (numai repornirile la rand ale aceluiasi canal tac)
			_mesaj_4k = (None, 0.0)
		if eIptv:
			self.serviciu, self.referinta = self._identitate()
			ref = self.session.nav.getCurrentlyPlayingServiceReference() if getattr(self.session, "nav", None) else None
			self.tip = getattr(ref, "type", 4097)
			self.pozitie_audio = self._pozitie()[0]
			self._ceas().start(PAS_MS, False)
			self._pas()
		else:
			self._ascunde()

	def laEnd(self):
		# evEnd (alt canal, un film, o inregistrare redata, standby) si laStart: fondul negru al unui canal 4K pleaca
		_fondNegru(self.session, False)
		self._opresteSubtitrari()
		self.stare.laEnd()
		self.serviciu = self.referinta = None
		self.pts_video = self.pozitie_audio = None
		self.marime = False
		self.baza_fara_pts = None
		if self._citire_video is not None:
			self._citire_video.cancel()
			self._citire_video = None
		for nota in self._notari:
			nota.cancel()
		self._notari = []
		self._ascunde()

	def laPornit(self):
		# Marimea video si PLAYING sunt indicii, nu dovada unui cadru afisat.
		self._pas()

	def _confirmaPornit(self):
		canal = self.stare.laPornit()
		if canal:
			if self.ecran is not None:
				self.ecran.ascunde()
			if self.ceas is not None:
				self.ceas.start(PAS_PORNIT_MS, False)
			self._notaInFundal(_notaPornit, canal, self.stare.durata())

	def _notaInFundal(self, functie, *args):
		self._notari = [nota for nota in self._notari if not nota.done()]
		try:
			self._notari.append(_inFundal(functie, *args))
		except Exception as e:
			print("[HdsIptvRedare] coada notarilor: %s" % type(e).__name__)

	def _codec(self):
		"""Codecul video spus de player (pentru motivul „format”), sau ""."""
		try:
			from enigma import iServiceInformation
			service = self.session.nav.getCurrentService()
			info = service and service.info()
			return (info.getInfoString(iServiceInformation.sTagVideoCodec) or "") if info else ""
		except Exception:
			return ""

	def _noteaza(self, canal):
		if _eArhiva(canal[1]):
			return                      # o emisiune din arhiva nu primeste semnul canalului
		self._notaInFundal(_notaEsuat, canal, self._codec() if canal[2] == "format" else "")

	def laEsec(self):
		if not self._curent():
			self._ascunde()
			return
		if _pornireInCurs(self.infobar):
			# IPT8: canalul n-a dat inca imagine si Components/HdsIptvReconectare il porneste singur din nou: fereastra ramane
			# (T_CONECTARE la pornirea din nou), semnul "n-a pornit" se pune numai la caderea finala
			return
		canal = self.stare.laEsec()
		if canal:
			self._noteaza(canal)
		self.stare.esuat = True
		self._opresteSubtitrari()
		self._ascunde()

	def laTampon(self):
		"""evBuffering: numai incarcarea tamponului, cel mult o data la CITIRE_TAMPON_S; _pas vine de la ceas (vezi CITIRE_TAMPON_S)."""
		acum = self.stare.ceas()
		if self._tampon_la is not None and acum - self._tampon_la < CITIRE_TAMPON_S:
			self._tampon_sarit = True
			return
		self._tampon_la = acum
		self._citesteTampon()

	def _citesteTampon(self):
		self._tampon_sarit = False
		if self.inchis or not self.stare.urmarit():
			return
		try:
			service = self.session.nav.getCurrentService()
			streamed = service and service.streamed()
			if streamed:
				self.stare.laTampon(streamed.getBufferCharge()[0])
		except Exception as e:
			print("[HdsIptvRedare] tamponul: %s" % type(e).__name__)

	def _ascunde(self):
		self.generatie += 1
		if self._citire_video is not None:
			self._citire_video.cancel()
			self._citire_video = None
		if self.ceas is not None:
			self.ceas.stop()
			if self._callback_ceas in self.ceas.callback:
				self.ceas.callback.remove(self._callback_ceas)
		self._callback_ceas = None
		if self.ecran is not None:
			self.ecran.ascunde()

	def _pozitie(self):
		"""(unde a ajuns imaginea sau None, e in pauza)"""
		if getattr(self.session, "nav", None) is None:
			return None, False
		try:
			service = self.session.nav.getCurrentService()
			seek = service and service.seek()
			rez = seek.getPlayPosition() if seek else None
			pauza = getattr(self.infobar, "seekstate", (0,))[0] == 1
			return (rez[1] if rez and not rez[0] else None), pauza
		except Exception as e:
			print("[HdsIptvRedare] pozitia: %s" % type(e).__name__)
			return None, False

	def _mesajFullHd(self, fel, nume):
		"""Randul scurt despre un canal 4K pe un receptor Full HD: mesajul care pleaca singur si nu ia tastele (Screens/Toast.py)."""
		global _mesaj_4k
		canal, cand = _mesaj_4k
		acum = self.stare.ceas()
		if canal == (self.stare.sid, self.stare.cheie, fel) and acum - cand < REPETARE_MESAJ_4K_S:
			return
		_mesaj_4k = ((self.stare.sid, self.stare.cheie, fel), acum)
		try:
			from Screens.Toast import Toast
			text = (_(T_FULL_HD_PERECHE) % nume) if fel == "pereche" else _(T_FULL_HD_4K)
			Toast.instance.showToast(text, Toast.TYPE_INFO, MESAJ_FULL_HD_S)
		except Exception as e:
			print("[HdsIptvRedare] mesajul Full HD: %s" % type(e).__name__)

	def _pas(self):
		if not self._curent():
			self._ascunde()
			return
		if self._tampon_sarit:
			self._citesteTampon()
		hd = self.stare.fullHd()
		if hd:
			self._mesajFullHd(*hd)
			if hd[0] == "4k" and not self.stare.pornit:
				# canal masurat 4K fara pereche pe un receptor Full HD: mesajul acum, nu fereastra Porneste redarea 30 s; sub el
				# ecran negru, nu cadrul canalului de dinainte (dupa laEnd, care il ascunde)
				self.laEnd()
				_fondNegru(self.session, True)
				return
		nou, pts, video = self._videoNou()
		if not self.stare.pornit and self._primulCadru(nou, pts, video):
			self._confirmaPornit()
		if not nou or ((pts is None or pts == PTS_REFUZAT) and video != 0):
			# Lipsa observatiei nu dovedeste un canal defect. La termen renuntam
			# la fereastra, fara notare si fara a accepta rezultatele intarziate.
			# Cu PTS_REFUZAT la fel: pozitia si marimea sunt spuse de player, nu masurate din decodor.
			if not self.stare.pornit and self.stare.durata() >= PRAG_ESEC_S:
				self.laEnd()
				return
		if self.stare.pornit:
			self.stare.laPozitie(*self._pozitie())
			if nou and pts is not None and pts > 0 and self.pts_video is not None and pts != self.pts_video:
				# Video in miscare inseamna redare si cand ceasul audio nu se poate citi.
				self.stare.ultima_pozitie = self.stare.ultim_flux = self.stare.ceas()
			if nou:
				self.pts_video = pts
			try:
				self._subtitrari()
			except Exception as e:
				print("[HdsIptvRedare] subtitrarile: %s" % type(e).__name__)
		text, procent, mic, esuat = self.stare.pas()
		if esuat:
			self._noteaza(esuat)
		if text is None:
			if self.ecran is not None:
				self.ecran.ascunde()
			if esuat or self.stare.esuat:
				self._opresteSubtitrari()
				self._ascunde()
			return
		# peste bara (care in tema Pro e pe tot ecranul), dar nu peste lista de canale sau peste meniuri: acolo sta in randul de pe imagine
		if not getattr(self.infobar, "execing", True):
			if self.ecran is not None:
				self.ecran.ascunde()
			return
		if self.inchisa_de_om:
			# EXL6: omul a inchis-o cu EXIT tinut apasat; ramane inchisa pana la urmatorul canal, observarea merge mai departe
			if self.ecran is not None:
				self.ecran.ascunde()
			return
		ecran = self._fereastra()
		if self.stare.pornit and (not nou or (pts is None and video != 0)):
			# Fara observatie video nu redeschidem fereastra; ascunderea ramane activa.
			return
		if ecran is not None:
			ecran.arata(_(text), procent, mic)
			self._tastaExit(True)
