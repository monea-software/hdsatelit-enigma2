# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsJurnalZapFlux.py: fluxurile de pe internet in jurnalul zap-ului (hds-zap.log, Components/HdsJurnal, componenta "zap",
# modulul "flux"). Randurile canalelor DVB le scrie nucleul (lib/service/hdsjurnalzap, numai in eDVBServicePlay); un
# serviciu redat de servicemp3 (4097, 5001, 5002: posturile Radio online pe 127.0.0.1:8895, canalele IPTV, orice adresa
# http, https, rtsp...) nu ajungea acolo, deci la asistenta nu se vedea cand a pornit si cand s-a oprit un post, iar ora
# opririi se pierdea cu rotirea lui hds-interfata.log (TODO 12.11 20:36, AS4).
#
# CE SE SCRIE (doua randuri pe flux, cel mult MAX_RANDURI_ORA pe ora):
#   INFO  "flux pornit: <nume> | <tip> | local:<port>" pentru un releu de pe receptor (Radio online 8895) sau
#         "internet (<schema>)" pentru un server din afara: niciodata gazda, calea, contul, parola sau parametrii adresei
#         (acolo stau datele liniei IPTV; jurnalul pleaca la testeri si spre forum);
#   INFO  "flux oprit dupa <durata>: oprit (...) | <nume> | redarea pornita dupa N ms" la oprirea ceruta (alt canal,
#         stand-by, iesirea din player);
#   AVERT acelasi rand cand fluxul s-a oprit singur: sfarsitul fluxului (serverul a inchis) sau eroarea playerului
#         (codul evUser+N: 10 sunetul refuzat, 11 imaginea refuzata, 12 element lipsa, 16 alta eroare; in rand "cod N",
#         nu "evUser", pe care filtrul forumului il ia drept nume de utilizator), ori redarea n-a pornit.
# Chemat din Navigation.dispatchEvent, dupa ascultatori. Nu schimba nimic in redare. Nimic din enigma2 la incarcare: probele
# de pe PC dau un nav fals si constantele evenimentelor (EVENIMENTE).
#
# JURNALUL REDARII (0.7.5, IJR, TODO 15.11 00:02; asistenta 011723, Vu+ Solo SE: inghetari si mozaic pe canalele de internet,
# prin exteplayer3 si 4097, iar omul isi nota singur orele). Cat merge un flux de pe internet, o data pe secunda (un eTimer,
# numai atunci), se citesc /proc/net/dev (octetii primiti: cea mai mare crestere dintre interfete, fara lo, deci cablul,
# Wi-Fi-ul sau VPN-ul, nu suma lor) si /proc/net/tcp, tcp6 (cea mai mare coada de primire a unei legaturi TCP stabilite spre
# o adresa din afara receptorului; numai marimea, niciodata adresa). In hds-zap.log, modulul "redare":
#   AVERT "oprire: fara date de N s, la +T de la pornire | ultimele secunde (Mb/s): ... | coada X: <cauza>" cand, dupa ce au
#         venit date, nu mai vine nimic (sub PRAG_ZERO_BPS) mai mult de PRAG_OPRIRE_S; coada goala = nu vine nimic din retea
#         (serverul sau drumul pana la el), coada plina = datele au ajuns, dar playerul nu le citeste;
#   INFO  "oprirea s-a terminat dupa D" cand datele vin din nou;
#   INFO  "debit 1 min: 4,1-17,0 Mb/s (medie 9,2) | coada pana la 2,6 MB | opriri 0", la minutul cu ceva de vazut (o oprire,
#         debitul cazut sub jumatate din medie) si oricum din MINUTE_RAND in MINUTE_RAND minute (hds-zap.log e comun cu zap-urile
#         DVB si se roteste la 256 KB: un rand pe fiecare minut ar fi injumatatit istoria cuiva care tine IPTV toata ziua);
#   iar randul "flux oprit" primeste rezumatul intregului flux (debitul, opririle, cea mai lunga) si playerul extern.
# Playerul extern al lui ServiceApp (exteplayer3, gstplayer): la oprirea lui ServiceApp trimite numai evEOF, iar codul de
# iesire il arunca (sursa sig3 485bb98f: PlayerApp::appClosed -> handleProcessStopped -> recvStopped(0) -> evEOF; si cand
# fluxul nu se deschide: exteplayer3 iese cu 10, tot evEOF; evUser+12 nu vine niciodata de la exteplayer3). De aceea procesul
# se cauta aici, printre procesele aparute dupa pornire (numai pana e gasit, cel mult CAUTA_PLAYER_S), iar evEOF cu playerul
# vazut se scrie "playerul extern (exteplayer3) s-a oprit singur". Redarea pornita: evUser+17 (servicemp3),
# evVideoSizeChanged (oricare) sau evUpdatedInfo cu playerul extern vazut (ServiceApp il trimite la 1 s dupa PLAYBACK_PLAY).
# Radioul redat de servicedvb (tip 1: posturile DAB+ si DVB-T2 prin releul de pe receptor, fluxurile TS de radio) n-are
# imagine, deci nici evVideoSizeChanged: acolo pornirea se vede dupa sunet, la evUpdatedInfo cu PMT-ul citit, cu sunet si fara
# imagine (doarSunet).
# MESAJUL PE ECRAN: cand fluxul se opreste singur (evEOF sau eroarea playerului), o singura data pe flux, un mesaj care pleaca
# singur dupa MESAJ_S: "Canalul nu a putut fi deschis." daca redarea n-a pornit, "Canalul s-a oprit singur." daca a mers;
# la pornirea fluxului urmator mesajul ramas se sterge (ca HdsFilm la InfoBarFilmRefuz). Un evEOF intarziat al canalului de
# dinainte nu ajunge la cel nou: eNavigation::stopService taie legatura evenimentelor (m_service_event_conn = 0) inainte ca
# bucla principala sa livreze mesajul stop al lui ServiceApp.
# Nu apare: in stand-by; cand servicemp3 a dat motivul (InfoBarFilmRefuz are mesajul lui, HdsFilmRedare.verdictDinInfo); la
# sfarsitul unui film (lungime cunoscuta); la un canal al omului care a mers si pe care HdsIptvReconectare il porneste singur;
# la un canal care n-a dat inca imagine si pe care HdsIptvReconectare il porneste singur din nou (pornirea cu rabdare, IPT8):
# T_NEDESCHIS vine numai la caderea finala, dupa HdsIptvReconectare.PORNIRE_S.

import os
import time
from collections import deque
from urllib.parse import unquote, urlsplit

MAX_RANDURI_ORA = 240
SCHEME = ("http", "https", "rtsp", "rtmp", "rtmps", "rtp", "udp", "mms", "hls")
ERORI = {10: "sunetul refuzat", 11: "imaginea refuzata", 12: "element lipsa", 16: "alta eroare"}
PORNIT_REDARE = 17            # evUser+17: primul cadru a ajuns la iesire (servicemp3, GST_STATE_CHANGE_PAUSED_TO_PLAYING)

PAS_MS = 1000                 # cat de des se citeste debitul, numai cat merge un flux de pe internet
PRAG_ZERO_BPS = 32000         # sub atat pe secunda = nimic (DNS, ceasul retelei, asistenta trec mereu cativa KB)
PRAG_DATE_BPS = 96000         # de la atat = vine fluxul: numai asa incepe masurarea opririlor si se termina o oprire; intre
                              # cele doua praguri (cativa KB de fundal) o oprire nu incepe si nici nu se termina (pe receptorul de proba,
                              # cu fluxul servit chiar de receptor, traficul de fundal dadea 9 opriri false pe minut)
PRAG_OPRIRE_S = 2.0           # fara date mai mult de atat (dupa ce au venit) = o oprire
SERIE = 10                    # secundele din urma scrise in randul opririi
MINUT_S = 60.0
MINUTE_RAND = 5               # randul pe minut si fara nimic de vazut, o data la atatea minute
MAX_OPRIRI_ORA = 40           # randurile opririlor pe ora; peste, numai numaratoarea din rezumat
COADA_PLINA = 64 * 1024       # o coada de primire mai mare in timpul unei opriri: datele stau la receptor, playerul nu citeste
CAUTA_PLAYER_S = 20.0
PLAYERE = ("exteplayer3", "gstplayer")    # inceputul lui /proc/<pid>/comm (gstplayer_gst-1.0 apare taiat la 15 caractere)
MESAJ_S = 8


def N_(text):
	return text


T_NEDESCHIS = N_("Canalul nu a putut fi deschis.")
T_OPRIT = N_("Canalul s-a oprit singur.")

# constantele iPlayableService; None = luate din enigma la primul eveniment (probele le pun singure; "video" si "info" pot
# lipsi din dictionarul probelor vechi)
EVENIMENTE = None


def _evenimente():
	global EVENIMENTE
	if EVENIMENTE is None:
		from enigma import iPlayableService as I
		EVENIMENTE = {"start": I.evStart, "end": I.evEnd, "eof": I.evEOF, "user": I.evUser,
			"video": I.evVideoSizeChanged, "info": I.evUpdatedInfo}
	return EVENIMENTE


def gazdaPort(cale):
	"""Adresa fluxului -> "local:<port>" sau "internet (<schema>)", "" cand nu e o adresa de flux."""
	try:
		cale = unquote(cale or "").strip()
		if "://" not in cale or cale.split("://", 1)[0].lower() not in SCHEME:
			return ""
		p = urlsplit(cale)
		gazda = p.hostname or "?"
		if gazda != "localhost" and not gazda.startswith("127."):
			# un server de pe internet: jurnalul pleaca in pachetul testerilor si spre forum, iar gazda unui furnizor
			# IPTV spune linia omului; ramane numai felul adresei
			return "internet (%s)" % p.scheme.lower()
		try:
			port = p.port
		except ValueError:
			port = None
		# un releu de pe receptor (Radio online 8895, releul IPTV): portul spune care
		return "local:%s" % port if port else "local"
	except Exception:
		return "?"


def porturiDinTuner():
	"""Porturile releelor DAB+ si DVB-T2 din satelit (Hds/DabT2: 8898, 8889 si porturile lor vechi). Datele lor vin din
	tuner, prin serverul 8001 si pe lo, nu din retea: /proc/net/dev (fara lo) le vede 0 Mb/s cat fluxul merge, deci la ele
	debitul si opririle de retea nu se masoara (asistenta 213800: "oprire: fara date ... nu vine nimic din retea" si
	"debit 0,0" cu 12,5 Mb/s si imagine pe releul T2). Radio online (8895) si releul IPTV iau datele din retea: raman."""
	try:
		from Hds.DabT2 import profil
		return set(profil.DAB.porturi_ref()) | set(profil.T2.porturi_ref())
	except Exception:
		return set((8889, 8898, 8888))


def doarSunet(nav):
	"""Serviciul pornit are PMT-ul citit, cu sunet si fara imagine: radio redat de servicedvb. La un flux tip 1 serviciul nu
	are PID-uri tinute minte (eServiceFactoryDVB.lookupService face un eDVBService nou pentru orice cale), deci pistele vin
	din PMT; releul DAB+ scrie PAT/PMT numai odata cu cadrele de sunet (Hds/DabT2/dab/motor/dab_edi.TsAudio.pachete), deci
	PMT-ul citit spune ca sunetul a venit. -> bool; False la orice eroare (si fara enigma, in probele de pe PC)."""
	try:
		service = nav.getCurrentService()
		if service is None:
			return False
		piste = service.audioTracks()
		if piste is None or piste.getNumberOfTracks() <= 0:
			return False
		info = service.info()
		if not info:
			return False
		from enigma import iServiceInformation
		vpid = info.getInfo(iServiceInformation.sVideoPID)
		# imagine = un PID video adevarat, ca in randul radio din lib/service/hdsjurnalzap.cpp
		return not (0 < vpid < 0x2000)
	except Exception:
		return False


def _durata(s):
	s = max(0, int(round(s)))
	if s < 60:
		return "%d s" % s
	if s < 3600:
		return "%d min %d s" % (s // 60, s % 60)
	return "%d h %d min" % (s // 3600, (s % 3600) // 60)


def _refAcum(nav):
	"""Referinta serviciului pornit acum: intai cea data de player (la evStart Navigation n-a pus-o inca), apoi a lui
	Navigation. -> (text referinta, nume) sau (None, None)."""
	text = None
	nume = ""
	try:
		service = nav.getCurrentService()
		info = service and service.info()
		if info:
			from enigma import iServiceInformation
			text = info.getInfoString(iServiceInformation.sServiceref) or None
			nume = info.getName() or ""
	except Exception:
		pass
	if not text:
		for f in ("getCurrentlyPlayingServiceReference", "getCurrentServiceReferenceOriginal"):
			try:
				ref = getattr(nav, f)()
				if ref is not None:
					text = ref.toString()
					break
			except Exception:
				pass
	return text, nume


def _desparte(text):
	"""Referinta 4097:0:...:adresa:nume -> (tip, adresa, nume din referinta)."""
	parti = (text or "").split(":")
	if len(parti) < 11:
		return "", "", ""
	tip = parti[0]
	adresa = parti[10]
	nume = ":".join(parti[11:]) if len(parti) > 11 else ""
	if "@" in nume and "@" not in adresa:
		# ":" necodat in contul adresei (user:parola@gazda): restul e tot adresa; numele nu se mai poate desparti
		adresa, nume = ":".join(parti[10:]), ""
	return tip, adresa, nume


# ------------------------------------------------------------------ jurnalul redarii (debitul, opririle, coada)

def _mb(bps):
	"""Biti pe secunda -> "6,1" (Mb/s), cu virgula: patru numere cu punct ar parea o adresa IP filtrelor jurnalului."""
	return ("%.1f" % (bps / 1000000.0)).replace(".", ",")


def _octeti(n):
	if n >= 1024 * 1024:
		return ("%.1f MB" % (n / 1048576.0)).replace(".", ",")
	return "%d KB" % (n // 1024)


def octetiInterfete(text):
	"""/proc/net/dev -> {interfata: octeti primiti}, fara lo."""
	rez = {}
	for rand in (text or "").splitlines()[2:]:
		if ":" not in rand:
			continue
		nume, rest = rand.split(":", 1)
		nume = nume.strip()
		if not nume or nume == "lo":
			continue
		campuri = rest.split()
		try:
			rez[nume] = int(campuri[0])
		except (IndexError, ValueError):
			pass
	return rez


def _eLocal(hexip):
	"""Adresa din /proc/net/tcp (hex, ordinea octetilor a procesorului: receptoarele noastre sunt little-endian) e 127.x.x.x
	sau ::1 (si ::ffff:127.x.x.x)."""
	h = hexip.upper()
	if len(h) == 8:
		return h.endswith("7F")
	if len(h) == 32:
		return h == "00000000000000000000000001000000" or (h.startswith("0000000000000000FFFF0000") and h.endswith("7F"))
	return False


def coadaMaxima(text):
	"""/proc/net/tcp sau tcp6 -> cea mai mare coada de primire (octeti) a unei legaturi stabilite spre afara receptorului.
	Adresele se citesc numai ca sa se sara peste legaturile locale (releul de pe 127.0.0.1); nu ies din functie."""
	maxim = 0
	for rand in (text or "").splitlines()[1:]:
		c = rand.split()
		if len(c) < 5 or c[3] != "01":           # 01 = ESTABLISHED
			continue
		if _eLocal(c[2].split(":", 1)[0]):
			continue
		try:
			maxim = max(maxim, int(c[4].split(":", 1)[1], 16))
		except (IndexError, ValueError):
			pass
	return maxim


class Esantionare(object):
	"""Debitul si opririle unui flux, din citirile /proc date de `citeste` (cale -> text) si procesele date de `procese`
	(-> lista de pid). Nimic din enigma2: probele dau citiri false si ceasul."""

	def __init__(self, ceas, citeste, procese=None):
		self.ceas = ceas
		self.citeste = citeste
		self.procese = procese
		self.t0 = ceas()
		self.prev = None
		self.serie = deque(maxlen=SERIE)
		self.au_venit = False
		self.zero_s = 0.0
		self.oprire = None
		self.opriri = 0
		self.cea_mai_lunga = 0.0
		self.minim = self.maxim = None
		self.suma = 0.0
		self.n = 0
		self.coada_max = 0
		self.minut = self._minutNou(self.t0)
		self.minute = 0
		self._ore_opriri = []
		self.player = None
		self.prag_pid = self._pidMaxim()

	@staticmethod
	def _minutNou(t):
		return {"t": t, "min": None, "max": None, "suma": 0.0, "n": 0, "coada": 0, "opriri": 0}

	def _pidMaxim(self):
		if self.procese is None:
			return 0
		try:
			return max([0] + list(self.procese()))
		except Exception:
			return 0

	def _cautaPlayer(self, acum):
		"""Playerul extern pornit de ServiceApp dupa evStart: numai printre procesele noi (pid mai mare decat la pornire), ca
		playerul canalului de dinainte, care inca se inchide, sa nu fie luat drept al acestui flux."""
		if self.player is not None or self.procese is None or acum - self.t0 > CAUTA_PLAYER_S:
			return
		try:
			pids = sorted(p for p in self.procese() if p > self.prag_pid)
		except Exception:
			return
		for pid in pids:
			try:
				nume = (self.citeste("/proc/%d/comm" % pid) or "").strip()
			except Exception:
				continue
			for p in PLAYERE:
				if nume.startswith(p):
					self.player = p
					return
		if pids:
			# un proces nou care nu e player nu se mai citeste o data pe secunda
			self.prag_pid = pids[-1]

	def _poateOprire(self, acum):
		self._ore_opriri = [t for t in self._ore_opriri if acum - t < 3600]
		if len(self._ore_opriri) >= MAX_OPRIRI_ORA:
			return False
		self._ore_opriri.append(acum)
		return True

	def pas(self):
		"""O citire. -> lista de (nivel, mesaj) de scris."""
		acum = self.ceas()
		rez = []
		self._cautaPlayer(acum)
		try:
			dev = octetiInterfete(self.citeste("/proc/net/dev"))
		except Exception:
			return rez
		coada = 0
		for cale in ("/proc/net/tcp", "/proc/net/tcp6"):
			try:
				coada = max(coada, coadaMaxima(self.citeste(cale)))
			except Exception:
				pass
		prev, self.prev = self.prev, (acum, dev)
		if prev is None:
			return rez
		dt = acum - prev[0]
		if dt <= 0.2:
			return rez
		delta = 0
		for nume, octeti in dev.items():
			inainte = prev[1].get(nume)
			if inainte is not None and octeti >= inainte:
				delta = max(delta, octeti - inainte)
		bps = delta * 8.0 / dt
		self.serie.append(bps)
		self.coada_max = max(self.coada_max, coada)
		self.minim = bps if self.minim is None else min(self.minim, bps)
		self.maxim = bps if self.maxim is None else max(self.maxim, bps)
		self.suma += bps
		self.n += 1
		m = self.minut
		m["min"] = bps if m["min"] is None else min(m["min"], bps)
		m["max"] = bps if m["max"] is None else max(m["max"], bps)
		m["suma"] += bps
		m["n"] += 1
		m["coada"] = max(m["coada"], coada)
		if bps >= PRAG_DATE_BPS:
			if self.oprire is not None:
				durata = self.zero_s          # secundele fara date (cea de acum a adus date)
				self.cea_mai_lunga = max(self.cea_mai_lunga, durata)
				if self.oprire["scris"]:
					rez.append(("INFO", "oprirea s-a terminat dupa %s (coada pana la %s)" % (_durata(durata),
						_octeti(self.oprire["coada"]))))
				self.oprire = None
			self.au_venit = True
			self.zero_s = 0.0
		elif self.oprire is not None:
			# o oprire se termina numai cand vine iar fluxul, nu la cativa KB de fundal
			self.zero_s += dt
			self.oprire["coada"] = max(self.oprire["coada"], coada)
		elif self.au_venit and bps >= PRAG_ZERO_BPS:
			self.zero_s = 0.0
		elif self.au_venit:
			# inainte de primele date (legatura cu serverul) nu e o oprire: acolo raspunde randul "redarea n-a pornit"
			self.zero_s += dt
			if self.zero_s > PRAG_OPRIRE_S:
				inceput = acum - self.zero_s
				self.opriri += 1
				m["opriri"] += 1
				self.oprire = {"t": inceput, "coada": coada, "scris": self._poateOprire(acum)}
				if self.oprire["scris"]:
					cauza = ("datele au ajuns, playerul nu le citeste" if coada >= COADA_PLINA else
						"nu vine nimic din retea (serverul sau drumul pana la el)")
					rez.append(("AVERT", "oprire: fara date de %s, la +%s de la pornire | ultimele secunde (Mb/s): %s | "
						"coada %s: %s" % (_durata(self.zero_s), _durata(inceput - self.t0),
						" ".join(_mb(b) for b in self.serie), _octeti(coada), cauza)))
		if acum - m["t"] >= MINUT_S and m["n"]:
			self.minute += 1
			medie = m["suma"] / m["n"]
			if m["opriri"] or m["min"] < medie / 2 or self.minute % MINUTE_RAND == 0:
				rez.append(("INFO", "debit 1 min: %s-%s Mb/s (medie %s) | coada pana la %s | opriri %d" % (_mb(m["min"]),
					_mb(m["max"]), _mb(medie), _octeti(m["coada"]), m["opriri"])))
			self.minut = self._minutNou(acum)
		return rez

	def rezumat(self):
		"""Partea adaugata la randul "flux oprit" (gol cand nu s-a masurat nimic)."""
		parti = []
		if self.player:
			parti.append("player %s" % self.player)
		if self.n:
			parti.append("debit %s-%s Mb/s (medie %s)" % (_mb(self.minim), _mb(self.maxim), _mb(self.suma / self.n)))
			lunga = self.cea_mai_lunga
			if self.oprire is not None:
				lunga = max(lunga, self.zero_s)
			parti.append("opriri %d (cea mai lunga %s)" % (self.opriri, _durata(lunga)) if self.opriri else "fara opriri")
			parti.append("coada pana la %s" % _octeti(self.coada_max))
			if self.oprire is not None:
				parti.append("inchis in timpul unei opriri")
		return " | ".join(parti)


def deAnuntat(pornit, standby=False, refuz=False, film=False, reconectare=False, pornire=False):
	"""Textul mesajului pe ecran cand fluxul s-a oprit singur, sau None (vezi sus: cand nu apare). pornire: canalul n-a dat inca
	imagine si HdsIptvReconectare il porneste singur din nou (IPT8): "nu a putut fi deschis" asteapta caderea finala."""
	if standby or refuz:
		return None
	if not pornit:
		return None if pornire else T_NEDESCHIS
	if film or reconectare:
		return None
	return T_OPRIT


class Urmaritor(object):
	"""scrie(nivel, mesaj) si ceas: probele. citeste/procese (Esantionare), temporizator (start/stop, la PAS_MS chema pas()),
	anunta(nav, pornit, cod) si curata() (sterge mesajul la pornirea unui serviciu): pe receptor; fara ele (probele vechi)
	nimic masurat si nimic pe ecran."""

	def __init__(self, scrie=None, ceas=None, citeste=None, procese=None, temporizator=None, anunta=None, curata=None):
		self._scrie = scrie
		self.ceas = ceas or time.monotonic
		self.curent = None
		self._ora = []
		self._citeste = citeste
		self._procese = procese
		self.temporizator = temporizator
		self._anunta = anunta
		self._curata = curata

	def _rand(self, nivel, mesaj, modul="flux"):
		acum = self.ceas()
		self._ora = [t for t in self._ora if acum - t < 3600]
		if len(self._ora) >= MAX_RANDURI_ORA:
			return
		self._ora.append(acum)
		if self._scrie is not None:
			self._scrie(nivel, mesaj)
			return
		from Components import HdsJurnal
		(HdsJurnal.avert if nivel == "AVERT" else HdsJurnal.info)("zap", modul, mesaj)

	def _esantionare(self):
		return self.curent.get("es") if self.curent is not None else None

	def _pornitRedarea(self):
		if self.curent.get("redare_ms") is None:
			self.curent["redare_ms"] = int(round((self.ceas() - self.curent["t0"]) * 1000))

	def eveniment(self, nav, ev):
		E = _evenimente()
		if ev == E["start"]:
			if self.curent is not None:
				self._inchide("oprit (alt canal)")
			if self._curata is not None:
				try:
					self._curata()
				except Exception as e:
					print("[HdsJurnalZapFlux] mesajul vechi: %r" % (e,))
			self._porneste(nav)
		elif self.curent is None:
			return
		elif ev == E["end"]:
			self._inchide()
		elif ev == E["eof"]:
			if not self.curent.get("motiv"):
				es = self._esantionare()
				if es is not None and es.player:
					# ServiceApp: orice iesire a playerului extern (si fluxul care nu s-a deschis) ajunge aici
					self.curent["motiv"] = "playerul extern (%s) s-a oprit singur" % es.player
				else:
					self.curent["motiv"] = "sfarsitul fluxului (serverul a inchis)"
			self._oprireSingura(nav, None)
		elif ev == E["user"] + PORNIT_REDARE or ev == E.get("video"):
			self._pornitRedarea()
		elif ev == E.get("info"):
			es = self._esantionare()
			if es is not None and es.player:
				self._pornitRedarea()
			elif self.curent.get("tip") == "1" and self.curent.get("redare_ms") is None and doarSunet(nav):
				# servicemp3 trimite evUpdatedInfo inainte sa cante (are evUser+17), ServiceApp are regula de sus
				self._pornitRedarea()
		elif ev - E["user"] in ERORI:
			if not self.curent.get("motiv"):
				self.curent["motiv"] = "eroarea playerului: %s (cod %d)" % (ERORI[ev - E["user"]], ev - E["user"])
			self._oprireSingura(nav, ev - E["user"])

	def _oprireSingura(self, nav, cod):
		"""Mesajul pe ecran, o singura data pe flux (anunta hotaraste daca si ce)."""
		c = self.curent
		if c is None or c.get("anuntat") or self._anunta is None:
			return
		c["anuntat"] = True
		try:
			self._anunta(nav, c.get("redare_ms") is not None, cod)
		except Exception as e:
			print("[HdsJurnalZapFlux] mesajul: %r" % (e,))

	def pas(self):
		"""La PAS_MS cat merge un flux: debitul si opririle in jurnal."""
		es = self._esantionare()
		if es is None:
			if self.temporizator is not None:
				self.temporizator.stop()
			return
		for nivel, mesaj in es.pas():
			self._rand(nivel, mesaj, "redare")

	def _porneste(self, nav):
		text, nume_info = _refAcum(nav)
		tip, adresa, nume_ref = _desparte(text)
		gp = gazdaPort(adresa)
		if not gp:
			if self.temporizator is not None:
				self.temporizator.stop()
			return
		nume = (nume_ref or nume_info or "?").strip()
		if "//" in nume or "@" in nume or "%3a" in nume.lower():
			# o referinta cu ":" necodat in adresa: bucata de dupa ar fi tot adresa (cu cont), nu numele
			nume = "?"
		self.curent = {"t0": self.ceas(), "nume": nume, "redare_ms": None, "motiv": "", "tip": tip}
		self._rand("INFO", "flux pornit: %s | %s | %s" % (nume, tip, gp))
		din_tuner = gp.startswith("local:") and gp[6:].isdigit() and int(gp[6:]) in porturiDinTuner()
		if self._citeste is not None and not din_tuner:
			self.curent["es"] = Esantionare(self.ceas, self._citeste, self._procese)
			if self.temporizator is not None:
				self.temporizator.start()

	def _inchide(self, motiv=None):
		c, self.curent = self.curent, None
		if c is None:
			return
		if self.temporizator is not None:
			self.temporizator.stop()
		motiv_singur = c.get("motiv")
		if not motiv_singur and not motiv:
			motiv = "oprit (alt canal, stand-by sau iesire)"
			try:
				import Screens.Standby
				if Screens.Standby.inStandby is not None or Screens.Standby.inTryQuitMainloop:
					motiv = "oprit (stand-by sau oprire)"
			except Exception:
				pass
		redare = c.get("redare_ms")
		parti = ["flux oprit dupa %s: %s" % (_durata(self.ceas() - c["t0"]), motiv_singur or motiv), c["nume"],
			"redarea pornita dupa %d ms" % redare if redare is not None else "redarea n-a pornit"]
		es = c.get("es")
		if es is not None:
			rezumat = es.rezumat()
			if rezumat:
				parti.append(rezumat)
		self._rand("AVERT" if motiv_singur or redare is None else "INFO", " | ".join(parti))


# ------------------------------------------------------------------ pe receptor

def _citesteFisier(cale):
	with open(cale) as f:
		return f.read()


def _procese():
	return [int(x) for x in os.listdir("/proc") if x.isdigit()]


class _Temporizator(object):
	"""eTimer-ul jurnalului redarii, facut la primul flux (nimic din enigma la incarcare)."""

	def __init__(self, functie):
		self.functie = functie
		self.ceas = None

	def start(self):
		if self.ceas is None:
			from enigma import eTimer
			self.ceas = eTimer()
			self.ceas.callback.append(self.functie)
		self.ceas.start(PAS_MS, False)

	def stop(self):
		if self.ceas is not None:
			self.ceas.stop()


def _standby():
	try:
		import Screens.Standby
		return Screens.Standby.inStandby is not None or bool(Screens.Standby.inTryQuitMainloop)
	except Exception:
		return False


def _refuzServicemp3(nav, ref):
	"""servicemp3 a dat motivul (sUser+15): Screens/InfoBarGenerics.InfoBarFilmRefuz arata mesajul lui (numai tipul 4097)."""
	try:
		if ref is None or ref.type != 4097:
			return False
		from Components import HdsFilmRedare
		service = nav.getCurrentService()
		info = service and service.info()
		return HdsFilmRedare.verdictDinInfo(info, ref.getPath(), canal=True) is not None
	except Exception:
		return False


def _film(nav):
	"""O lungime cunoscuta = un fisier (un film): acolo EOF e sfarsitul firesc."""
	try:
		service = nav.getCurrentService()
		seek = service and service.seek()
		lungime = seek.getLength() if seek else None
		return bool(lungime and not lungime[0] and lungime[1] > 0)
	except Exception:
		return False


def _reconectare(ref):
	"""Un canal pe care Components/HdsIptvReconectare il porneste singur din nou (cu optiunea pornita)."""
	try:
		from Components import HdsIptvReconectare as R
		# si fluxurile din afara surselor noastre (liste .m3u in buchete, XStreamity, Bouquet Maker): IRC, 15.11.2026
		return R.seReconecteaza(ref)
	except Exception:
		return False


def _pornire(cod):
	"""Canalul n-a dat inca imagine si Components/HdsIptvReconectare il porneste singur din nou dupa caderea asta (IPT8)."""
	try:
		from Components import HdsIptvReconectare as R
		return R.pornireaContinua(cod)
	except Exception:
		return False


def _anuntaPeEcran(nav, pornit, cod):
	ref = nav.getCurrentlyPlayingServiceReference()
	text = deAnuntat(pornit, standby=_standby(), refuz=_refuzServicemp3(nav, ref), film=pornit and _film(nav),
		reconectare=pornit and _reconectare(ref), pornire=not pornit and _pornire(cod))
	if text is None:
		return
	from Screens.MessageBox import MessageBox
	from Tools import Notifications
	Notifications.RemovePopup(id="HdsFlux")
	Notifications.AddPopup(text=_(text), type=MessageBox.TYPE_INFO if pornit else MessageBox.TYPE_ERROR, timeout=MESAJ_S,
		id="HdsFlux")


def _curataEcranul():
	from Tools import Notifications
	Notifications.RemovePopup(id="HdsFlux")


def _pas():
	try:
		_urmaritor.pas()
	except Exception as e:
		try:
			print("[HdsJurnalZapFlux] pas: %r" % (e,))
		except Exception:
			pass


_urmaritor = Urmaritor(citeste=_citesteFisier, procese=_procese, temporizator=_Temporizator(_pas), anunta=_anuntaPeEcran,
	curata=_curataEcranul)


def eveniment(nav, ev):
	"""Din Navigation.dispatchEvent: un eveniment al serviciului principal. Nu arunca niciodata."""
	try:
		_urmaritor.eveniment(nav, ev)
	except Exception as e:
		try:
			print("[HdsJurnalZapFlux] %r" % (e,))
		except Exception:
			pass
