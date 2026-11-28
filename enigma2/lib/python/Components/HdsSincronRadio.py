# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Radioul fara sunet pe placile cu libreader (Octagon SF8008 si familia lui): sincronul placii scos numai unde blocheaza.

Pe aceste placi sunetul unui canal din tuner se sincronizeaza pe PCR (/proc/msp/sync00: SyncRef PCR). Masurat pe un
SF8008 prin tunerul virtual al placii: cadrele de sunet fara PTS nu pornesc niciodata (pre-sincronizarea nu se termina:
PreSyncFinish 0, AudFirstPlay 0, desi decodorul le decodeaza), iar cele al caror PTS ramane in urma PCR-ului cu peste
~1 s sunt aruncate toate (tot AudFirstPlay 0). Radioul tace, desi toate comenzile reusesc; asa erau unele posturi AAC
de pe 99.1W, cu PCR pe un PID separat. AUDIO_SET_AV_SYNC 0 (SyncRef NONE) le reda pe toate.

Sincronul ramane pornit pe orice post care merge (el tine si ceasul placii dupa al postului; fara el tamponul scade
incet). Deci: la un serviciu DVB din tuner fara imagine, la ~3 s dupa pornire (pre-sincronizarea normala se termina in
cel mult 1 s), daca placa a primit sunet (AudFirstCome 1), il decodeaza (cadrele cresc) si n-a inceput sa-l redea
(AudFirstPlay 0) la trei citiri pe 1,5 s, se trimite AUDIO_SET_AV_SYNC 0 pe /dev/dvb/adapter0/audio0, dintr-un
descriptor separat, si se scrie un rand in jurnal. AUDIO_PLAY (urmatorul zap, alta pista) pune singur sincronul inapoi
pe PCR, deci nu e nimic de pus la loc; dupa o schimbare de pista sau de informatii verificarea porneste din nou.

Citirile din /proc/msp si ioctl-ul se fac pe un fir de fundal, niciodata pe firul interfetei; un fir inca ocupat nu e
dublat. Pe celelalte placi (fara /dev/phi sau fara /proc/msp/sync00) nu se face nimic.
"""

import os
import re
import threading
import time

PRIMA_CITIRE_MS = 3000       # dupa pornirea serviciului; pre-sincronizarea normala: cel mult 1000 ms (PreSyncTimeoutMs)
INTRE_CITIRI_S = 0.75        # trei citiri, deci starea blocata se vede pe 1,5 s, nu numai la o clipa
AUDIO_SET_AV_SYNC = 0x6F07   # _IO('o', 7), linux/dvb/audio.h
AUDIO_STOP = 0x6F01          # _IO('o', 1)
AUDIO_PLAY = 0x6F02          # _IO('o', 2)
AUDIO_SET_BYPASS_MODE = 0x6F08   # _IO('o', 8); 1 = MPEG, 8 = AAC (ADTS), ca in eDVBAudio
BYPASS_MPEG = 1
BYPASS_AAC = 8
DUPA_AAC_S = 2.0             # cat asteapta cadrele AAC dupa schimbarea decodorului
RADACINA = ""                # probele de pe PC dau un dosar cu proc/msp si dev


def _cale(c):
	return RADACINA + c


def esteLibreader():
	"""Placa din familia libreader: hi_dvb are /dev/phi, iar sincronul se vede in /proc/msp/sync00."""
	return os.path.exists(_cale("/dev/phi")) and os.path.exists(_cale("/proc/msp/sync00"))


def _citeste(cale):
	try:
		with open(_cale(cale), "rb") as f:
			return f.read(65536).decode("latin-1")
	except (IOError, OSError):
		return ""


def _camp(text, nume):
	m = re.search(r"(?:^|\|)\s*" + re.escape(nume) + r"\s*:\s*(-?\d+)", text, re.M)
	return int(m.group(1)) if m else None


def stare():
	"""(AudFirstCome, AudFirstPlay, cadre decodate) din /proc/msp/sync00 si adec00; None la ce lipseste."""
	s = _citeste("/proc/msp/sync00")
	a = _citeste("/proc/msp/adec00")
	m = re.search(r"FrameNum\(Total/Error\)\s*:\s*(\d+)", a)
	return _camp(s, "AudFirstCome"), _camp(s, "AudFirstPlay"), int(m.group(1)) if m else None


def decodor():
	"""(numele decodorului placii, cadre decodate, cereri de cadre incercate) din /proc/msp/adec00."""
	a = _citeste("/proc/msp/adec00")
	n = re.search(r"DecoderName\s*:\s*(.*)", a)
	f = re.search(r"FrameNum\(Total/Error\)\s*:\s*(\d+)", a)
	r = re.search(r"SendStream\(Try/OK\)\s*:\s*\d+/(\d+)", a)
	return (n.group(1).strip() if n else "", int(f.group(1)) if f else None, int(r.group(1)) if r else None)


def mp3FaraCadre(*dec):
	"""True cand placa a pornit decodorul MP3 (pista semnalata MPEG in PMT), fluxul intra (SendStream creste), dar nu iese
	niciun cadru, la toate citirile. Asa arata un post care trimite AAC (ADTS) semnalat ca MPEG (WRVO-KuHUB, 99.1W)."""
	if len(dec) < 2:
		return False
	for d in dec:
		if "mp3" not in d[0].lower() or d[1] != 0 or d[2] is None:
			return False
	return dec[-1][2] > dec[0][2]


def schimbaDecodorul(bypass):
	"""STOP, AUDIO_SET_BYPASS_MODE, PLAY pe decodorul de sunet al placii, dintr-un descriptor separat. -> None sau eroarea."""
	import fcntl
	try:
		fd = os.open(_cale("/dev/dvb/adapter0/audio0"), os.O_RDWR | os.O_NONBLOCK)
	except OSError as e:
		return str(e)
	try:
		fcntl.ioctl(fd, AUDIO_STOP)
		fcntl.ioctl(fd, AUDIO_SET_BYPASS_MODE, bypass)
		fcntl.ioctl(fd, AUDIO_PLAY)
		return None
	except (IOError, OSError) as e:
		return str(e)
	finally:
		os.close(fd)


def blocat(*stari):
	"""True cand placa a primit si decodeaza sunetul (cadrele cresc de la o citire la alta), dar nu l-a pornit, la toate
	citirile (cel putin doua)."""
	if len(stari) < 2:
		return False
	for s in stari:
		if s[0] != 1 or s[1] != 0 or s[2] is None:
			return False
	return all(b[2] > a[2] for a, b in zip(stari, stari[1:]))


def opresteSincronul():
	"""AUDIO_SET_AV_SYNC 0 pe decodorul de sunet al placii, dintr-un descriptor separat. -> None sau textul erorii."""
	import fcntl
	try:
		fd = os.open(_cale("/dev/dvb/adapter0/audio0"), os.O_RDWR | os.O_NONBLOCK)
	except OSError as e:
		return str(e)
	try:
		fcntl.ioctl(fd, AUDIO_SET_AV_SYNC, 0)
		return None
	except (IOError, OSError) as e:
		return str(e)
	finally:
		os.close(fd)


class SincronRadio:
	def __init__(self):
		self.ceas = None
		self.generatie = 0
		self.fir = None
		self.nav = None

	def _radioDinTuner(self):
		from enigma import eServiceReference, iServiceInformation
		nav = self.nav
		if nav is None:
			return False
		ref = nav.getCurrentlyPlayingServiceReference()
		if ref is None or ref.type != eServiceReference.idDVB or ref.getPath():
			return False
		service = nav.getCurrentService()
		if service is None or service.seek() is not None:     # inregistrare sau timeshift: redare, alt sincron
			return False
		info = service.info()
		return info is not None and info.getInfo(iServiceInformation.sVideoPID) == -1

	def incepe(self, nav):
		"""La pornirea unui serviciu, la informatii noi si la alta pista: verificarea de la capat."""
		self.generatie += 1
		self.nav = nav
		if not esteLibreader():
			return
		if self.ceas is None:
			from enigma import eTimer
			self.ceas = eTimer()
			self.ceas.callback.append(self._laCeas)
		self.ceas.start(PRIMA_CITIRE_MS, True)

	def opreste(self):
		self.generatie += 1
		if self.ceas is not None:
			self.ceas.stop()

	def _laCeas(self):
		try:
			if not self._radioDinTuner():
				return
		except Exception as e:
			print("[HdsSincronRadio] verificarea serviciului: %s" % e)
			return
		if self.fir is not None and self.fir.is_alive():
			return
		gen = self.generatie
		self.fir = threading.Thread(target=self._verifica, args=(gen,), name="HdsSincronRadio")
		self.fir.daemon = True
		self.fir.start()

	def _aacInLocDeMp3(self, gen):
		"""Postul semnalat MPEG care trimite AAC: decodorul MP3 nu scoate cadre. Se incearca AAC; daca nici el nu
		decodeaza, MP3 se pune la loc. -> True cand s-a schimbat pe AAC si merge."""
		dec = [decodor()]
		for _ in range(2):
			time.sleep(INTRE_CITIRI_S)
			if gen != self.generatie:
				return False
			dec.append(decodor())
		if gen != self.generatie or not mp3FaraCadre(*dec):
			return False
		eroare = schimbaDecodorul(BYPASS_AAC)
		if eroare:
			print("[HdsSincronRadio] decodorul MP3 nu scoate cadre (flux %s -> %s); trecerea pe AAC refuzata: %s" % (dec[0][2], dec[-1][2], eroare))
			return False
		time.sleep(DUPA_AAC_S)
		d = decodor()
		if gen != self.generatie:
			return False
		if "aac" in d[0].lower() and d[1]:
			print("[HdsSincronRadio] pista semnalata MPEG, dar fluxul e AAC (decodorul MP3: 0 cadre): decodata ca AAC (%s, %s cadre)" % (d[0], d[1]))
			return True
		schimbaDecodorul(BYPASS_MPEG)
		print("[HdsSincronRadio] decodorul MP3 nu scoate cadre, nici AAC (%s, %s cadre): pus MPEG la loc" % (d[0], d[1]))
		return False

	def _verifica(self, gen):
		try:
			self._aacInLocDeMp3(gen)
			if gen != self.generatie:
				return
			stari = [stare()]
			for _ in range(2):
				time.sleep(INTRE_CITIRI_S)
				if gen != self.generatie:
					return
				stari.append(stare())
			s1, s2 = stari[0], stari[-1]
			if gen != self.generatie or not blocat(*stari):
				return
			eroare = opresteSincronul()
			if eroare:
				print("[HdsSincronRadio] sunetul radioului nu porneste cu sincronul pe PCR (cadre %s -> %s), AUDIO_SET_AV_SYNC 0 refuzat: %s"
					% (s1[2], s2[2], eroare))
			else:
				print("[HdsSincronRadio] sunetul radioului nu pornea cu sincronul pe PCR (cadre %s -> %s, AudFirstPlay 0): redat pe ceasul placii (AUDIO_SET_AV_SYNC 0)"
					% (s1[2], s2[2]))
		except Exception as e:
			print("[HdsSincronRadio] %s" % e)


_INSTANTA = SincronRadio()


def incepe(nav):
	try:
		_INSTANTA.incepe(nav)
	except Exception as e:
		print("[HdsSincronRadio] %s" % e)


def opreste():
	try:
		_INSTANTA.opreste()
	except Exception as e:
		print("[HdsSincronRadio] %s" % e)
