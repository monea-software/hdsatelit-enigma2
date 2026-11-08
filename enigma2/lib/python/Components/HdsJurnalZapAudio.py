# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Jurnal pasiv al primelor opt secunde de sunet dupa un zap DVB principal.

Zece esantioane, ultimul cu rezumat, cel mult 600 de randuri in orice ora.
PORNIT este intrerupatorul ascuns. Nu se comanda redarea sau placa de sunet.
Driverul se cere numai prin cititorii existenti, intr-un singur lucrator fara
asteptare pe firul principal. Un lucrator blocat nu este inlocuit cu altul.
Virsta formatului ramane necunoscuta: cache-ul HdsSunet nu are timestamp.
Stabilizarea observata inseamna ultima schimbare urmata de probe egale;
iesire_stabila_ms ramane ?, fara dovada unor achizitii noi ale formatului.
"""

from collections import deque
import sys
import threading
import time

PORNIT = True
TIMPI_MS = (0, 250, 500, 1000, 2000, 3000, 4000, 5000, 6000, 8000)
MAX_RANDURI_ORA = 600
_monoton = time.monotonic


def _numar(v, minim=0, maxim=2147483647):
	return v if isinstance(v, int) and minim <= v <= maxim else None


def _text(v):
	return "?" if v is None else str(int(v) if isinstance(v, bool) else v)


def _alege(v, permise):
	return v if isinstance(v, str) and v in permise else None


def _sigur(f):
	def apel(self, *args, **kwargs):
		try:
			return f(self, *args, **kwargs)
		except Exception:
			self._eroare()
	return apel


class JurnalZapAudio:
	def __init__(self):
		self.seq = 0
		self.serie = None
		self.ceas = None
		self.randuri = deque()
		self._fir = None
		self._driver = None
		self._motor = (None, None)
		self._motor_legat = False

	def _curataLimita(self, acum):
		while self.randuri and acum - self.randuri[0] >= 3600:
			self.randuri.popleft()

	def _scrie(self, faza, campuri=()):
		acum = _monoton()
		self._curataLimita(acum)
		if len(self.randuri) >= MAX_RANDURI_ORA:
			return
		s = self.serie
		dt = max(0, round((acum - s["t0"]) * 1000)) if s else 0
		mesaj = "[zap-audio] seq=%d dt_ms=%d faza=%s" % (self.seq, dt, faza)
		mesaj += "".join(" %s=%s" % (k, _text(v)) for k, v in campuri)
		# Nu se exporta exceptii, descrieri libere, nume sau referinte.
		from Components import HdsJurnal
		self.randuri.append(acum)
		HdsJurnal.info("zap", "zap-audio", mesaj)

	def _opreste(self):
		self.serie = None
		if self.ceas is not None:
			self.ceas.stop()

	def _eroare(self):
		try:
			self._scrie("eroare", (("motiv", "citire-sau-jurnal"),))
		except Exception:
			pass
		try:
			self._opreste()
		except Exception:
			pass

	def _principal(self, nav):
		from enigma import eServiceReference, iServiceInformation
		service = nav.getCurrentService()
		if service is None:
			return None
		ref = nav.getCurrentlyPlayingServiceReference()
		# evStart vine sincron din pnav.playService, inainte ca Navigation sa
		# publice referinta. Serviciul C++ o are deja. Textul nu se jurnalizeaza.
		if ref is None:
			info = service.info()
			text = info.getInfoString(iServiceInformation.sServiceref) if info else None
			ref = eServiceReference(text) if text else None
		if ref is None or ref.type != eServiceReference.idDVB or ref.getPath():
			return None
		# DVB da interfata seek pentru fisier sau timeshift activat, inclusiv
		# cand bufferul exista dar redarea inca este live. Nu apelam timeshift().
		if service.seek() is not None:
			return None
		return service, ref

	@_sigur
	def incepe(self, nav):
		if self.serie is not None:
			self.inchide("zap-nou")
		if not PORNIT or nav is None:
			return
		acum = _monoton()
		self._curataLimita(acum)
		# Rezervam toate probele si un rand de eroare/inchidere. Nicio serie
		# noua nu consuma locul inchiderii seriei curente.
		if len(self.randuri) + len(TIMPI_MS) + 1 > MAX_RANDURI_ORA:
			return
		if self._principal(nav) is None:
			return
		self.seq += 1
		self._driver = None
		self.serie = {"nav": nav, "t0": acum, "i": 0, "pista": None,
			"format": None, "intarziere": None, "schimbari": [None, None, None],
			"stabil": None, "repetari": 0, "lipsa_format": True}
		if self.ceas is None:
			from enigma import eTimer
			self.ceas = eTimer()
			self.ceas.callback.append(self._laCeas)
		if not self._motor_legat:
			from Components import HdsEgalizator
			# stareMotor() cere si calculul spectrului; ascultam doar semnalele
			# motorului deja folosit de imagine, fara a-l crea sau a-l sonda.
			HdsEgalizator.asculta(self._laMotor)
			self._motor_legat = True
		self._laCeas()

	@_sigur
	def inchide(self, motiv="standby"):
		if self.serie is not None:
			self._scrie("intrerupt", (("motiv", "standby" if motiv == "standby" else "zap-nou"),))
		self._opreste()

	@_sigur
	def _laMotor(self, cod):
		self._motor = ({1: "merge", 2: "oprit", 3: "eroare", 4: "fara-date", 5: "proba-gata"}.get(cod), _monoton())

	def _citesteDriver(self, seq):
		try:
			from Components import HdsSunet, HdsSetariSunet
			fmt = HdsSunet.formatIesire()
			# Pe acest fir citestePlaca -> HdsProcFundal executa cititorul
			# existent direct. Stampila apartine acestei citiri, nu cache-ului.
			placa = HdsSetariSunet.citestePlaca()
			date = (fmt, placa, _monoton(), False, seq)
		except Exception:
			date = (None, None, None, True, seq)
		# Un raspuns lent al zap-ului vechi nu apartine noii serii.
		# Generatia se verifica si la consum, nu doar inainte de publicare.
		self._driver = date

	def _cereDriver(self):
		if self._driver is not None and self._driver[4] == self.seq and self._driver[3]:
			return
		if self._fir is None or not self._fir.is_alive():
			seq = self.seq
			self._fir = threading.Thread(target=lambda: self._citesteDriver(seq), name="HdsZapAudio", daemon=True)
			self._fir.start()
		# Fara join. decodoare() nu este ieftin: poate citi avplay blocat.

	def _ui(self, nav):
		mod = sys.modules.get("Screens.InfoBar")
		bara = getattr(getattr(mod, "InfoBar", None), "instance", None)
		session = getattr(bara, "session", None)
		if session is None or getattr(session, "nav", None) is not nav:
			return None, None
		stare = getattr(bara, "seekstate", None)
		redare = {0: "play", 1: "pauza"}.get(stare[0]) if stare else None
		# FrontendStatus este cache-ul citirilor frontendInfo ale sesiunii.
		# getFrontendInfo(lockState) ar face inca un FE_READ_STATUS ioctl.
		screen = getattr(session, "screen", {})
		sursa = screen.get("FrontendStatus")
		return redare, _numar(getattr(sursa, "lock", None), maxim=1)

	def _probe(self, service, ref, nav):
		from enigma import iServiceInformation, eDVBVolumecontrol
		from Components import AVSwitch
		from Components import HdsSetariSunet
		from Components.config import config
		info = service.info()
		criptat = _numar(info.getInfo(iServiceInformation.sIsCrypted), maxim=1) if info else None
		index = pid = codec = None
		tracks = service.audioTracks()
		if tracks is not None:
			index = _numar(tracks.getCurrentTrack())
			if index is not None and index < tracks.getNumberOfTracks():
				track = tracks.getTrackInfo(index)
				pid = _numar(track.getPID(), maxim=8191)
				codec = _alege(track.getDescription(), ("MPEG", "AC3", "AAC", "AAC-HE", "DTS", "DTS-HD", "AC3+", "LPCM"))
			else:
				index = None
		vol = eDVBVolumecontrol.getInstance()
		volum = _numar(vol.getVolume(), maxim=100) if vol else None
		mut = _numar(vol.isMuted(), maxim=1) if vol else None
		# intarzieriDorite cauta memoria prin Navigation. In timpul evStart
		# referinta poate lipsi; un zero implicit nu ar fi o masurare valida.
		dorite = (HdsSetariSunet.intarzieriDorite() or {}) if nav.getCurrentlyPlayingServiceReference() is not None else {}
		c = getattr(config, "hds_setari_sunet", None)
		avc = _alege(getattr(getattr(c, "volum_egal", None), "value", None), ("oprit", "usor", "puternic"))
		c = getattr(config, "hds_egalizator", None)
		eq = _numar(getattr(getattr(c, "pornit", None), "value", None), maxim=1)
		redare, lock = self._ui(nav)
		fel = ref.getData(0)
		campuri = [("serviciu", ("radio" if fel in (2, 10) else "tv") if _numar(fel, minim=1) else None), ("criptat", criptat),
			("index", index), ("codec", codec), ("pid", "0x%x" % pid if pid is not None else None),
			("redare", redare), ("lock", lock),
			("ac3_comandat", _alege(AVSwitch.AUDIO_SCRIS.get("ac3"), ("downmix", "passthrough"))),
			("dts_comandat", _alege(AVSwitch.AUDIO_SCRIS.get("dts"), ("downmix", "passthrough"))),
			("intarziere_dorita_ms", _numar(dorite.get("HDMI0"), maxim=500)),
			("intarziere_optic_dorita_ms", _numar(dorite.get("SPDIF0"), maxim=500)),
			("volum", volum), ("mut", mut), ("avc", avc),
			("eq", None if eq is None else ("pornit" if eq else "oprit")),
			("eq_motor", self._motor[0]),
			("eq_motor_varsta_ms", None if self._motor[1] is None else max(0, round((_monoton() - self._motor[1]) * 1000)))]
		return campuri, (index, pid, codec)

	def _probeDriver(self):
		date = self._driver
		if date is not None and date[4] != self.seq:
			date = None
		if date is not None and date[3]:
			raise RuntimeError("cititor")
		fmt, placa, t = date[:3] if date else (None, None, None)
		fmt, placa = fmt or {}, placa or {}
		formate, intarzieri = [], []
		campuri = []
		varsta = None if t is None else max(0, round((_monoton() - t) * 1000))
		for cheie, nume, sufix in (("hdmi", "HDMI0", ""), ("optic", "SPDIF0", "_optic")):
			f = _alege(fmt.get(cheie), ("PCM", "RAW", "BITSTREAM", "Bitstream", "bitstream", "pcm"))
			f = "pcm" if f in ("PCM", "pcm") else ("bitstream" if f else None)
			p = placa.get(nume) or {}
			intarziere = _numar(p.get("intarziere"), maxim=500)
			formate.append(f)
			intarzieri.append(intarziere)
			stare = _alege(p.get("stare"), ("start", "stop", "START", "STOP", "OPEN START", "OPEN STOP"))
			campuri.extend((("iesire" + sufix, f), ("iesire" + sufix + "_varsta_ms", None),
				("placa" + sufix + "_varsta_ms", varsta if p else None),
				("stare" + sufix + "_placa", stare.replace(" ", "_").lower() if stare else None),
				("mut" + sufix + "_placa", _numar(p.get("mut"), maxim=1)),
				("volum" + sufix + "_placa", _numar(p.get("volum"), maxim=100)),
				("intarziere" + sufix + "_placa_ms", intarziere)))
		return campuri, tuple(formate), tuple(intarzieri)

	def _schimbari(self, pista, formate, intarzieri, dt):
		s = self.serie
		pista_schimbata = None
		for i, (cheie, nou) in enumerate((("pista", pista), ("format", formate), ("intarziere", intarzieri))):
			vechi = s[cheie]
			comparabile = vechi is not None and any(a is not None and b is not None for a, b in zip(vechi, nou))
			schimbat = comparabile and any(a != b for a, b in zip(vechi, nou) if a is not None and b is not None)
			if comparabile:
				s["schimbari"][i] = (s["schimbari"][i] or 0) + int(schimbat)
			if cheie == "pista":
				pista_schimbata = "schimbata" if schimbat else ("aceeasi" if comparabile else None)
			if cheie == "format":
				cunoscut = any(v is not None for v in nou)
				if not cunoscut:
					s["stabil"], s["repetari"] = None, 0
				elif schimbat or s["stabil"] is None or s["lipsa_format"] or nou != vechi:
					s["stabil"], s["repetari"] = dt, 1
				else:
					s["repetari"] += 1
				s["lipsa_format"] = not cunoscut
			s[cheie] = nou
		return pista_schimbata

	@_sigur
	def _laCeas(self):
		s = self.serie
		if s is None:
			return
		if not PORNIT:
			self.inchide()
			return
		dt = max(0, round((_monoton() - s["t0"]) * 1000))
		if dt < TIMPI_MS[s["i"]]:
			self.ceas.start(TIMPI_MS[s["i"]] - dt, True)
			return
		principal = self._principal(s["nav"])
		if principal is None:
			self.inchide("serviciu-oprit")
			return
		campuri, pista = self._probe(principal[0], principal[1], s["nav"])
		self._cereDriver()
		driver, formate, intarzieri = self._probeDriver()
		dorite = dict(campuri)
		intarzieri += (dorite["intarziere_dorita_ms"], dorite["intarziere_optic_dorita_ms"])
		p = self._schimbari(pista, formate, intarzieri, dt)
		final = dt >= TIMPI_MS[-1]
		faza = "final" if final else ("start" if s["i"] == 0 else "proba")
		campuri.append(("pista", p))
		campuri.extend(driver)
		if final:
			campuri.extend(zip(("schimbari_pista", "schimbari_format", "schimbari_intarziere"), s["schimbari"]))
			campuri.append(("iesire_stabila_ms", None))
			campuri.append(("iesire_observata_stabila_ms", s["stabil"] if s["repetari"] >= 2 else None))
		self._scrie(faza, campuri)
		if final:
			self._opreste()
			return
		s["i"] += 1
		# Daca bucla UI a intarziat, sarim probele ratate; nu inventam trecutul
		# si nu scriem rafale de randuri cu aceeasi citire.
		while s["i"] < len(TIMPI_MS) - 1 and TIMPI_MS[s["i"]] <= dt:
			s["i"] += 1
		ramase = TIMPI_MS[s["i"]] - round((_monoton() - s["t0"]) * 1000)
		self.ceas.start(max(1, ramase), True)


_jurnal = JurnalZapAudio()


def incepe(nav=None):
	try:
		if nav is None:
			import NavigationInstance
			nav = NavigationInstance.instance
		_jurnal.incepe(nav)
	except Exception:
		_jurnal._eroare()


def inchide(motiv="standby"):
	try:
		_jurnal.inchide(motiv)
	except Exception:
		_jurnal._eroare()
