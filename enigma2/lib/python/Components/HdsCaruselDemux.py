# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCaruselDemux.py: caruselul DSM-CC al canalului redat, citit din demux-ul receptorului pe un fir separat.
# Components/HdsCarusel.py face restul (modulele, BIOP, arborele pe disc); aici sunt numai filtrele si bucla.
#
# Filtrele: numai filtre de SECTIUNI (DMX_SET_FILTER, prin HdsAnalizaFlux.SursaDemux, ca analiza fluxului), cate unul
# pe pista, fara table_id (pe pistele de carusel vin numai 0x3B, 0x3C si 0x3D; altceva se arunca in Python), fara
# DMX_CHECK_CRC (aceeasi forma ca filtrele de masura ale analizei fluxului, folosite pe receptor; CRC-ul il verifica
# HdsCarusel in Python, prin zlib) si cu un tampon de TAMPON octeti. Niciodata filtre PES
# sau TS (DMX_OUT_TAP, dvr): pe HiSilicon un filtru pe un PID pe care il foloseste televizorul se leaga de canalul
# gasit pe acel PID, iar un filtru de alt fel poate lasa canalul legat de el (vezi lib/dvb/hdspazademux.h). Toate
# filtrele se inchid (DMX_STOP, close) in finally: la oprire, la o eroare, la sfarsitul firului.
#
# Pistele: intai pista DSI-ului (component_tag-ul transportului din AIT -> PID, HdsCarusel.pid_dsi) si pistele date in
# plus (de pilda pista evenimentelor de flux); dupa DII, pistele modulelor (tap-urile BIOP_OBJECT_USE,
# HdsCarusel.piste_module), cel mult MAX_FILTRE filtre deodata (HbbTV cere cel putin 3 piste pe carusel si una pentru
# evenimente, ETSI TS 102 796 cap. 10.2.1).
#
# PMT-ul (pmt = (PID-ul PMT, SID, aplicatia din AIT), cand pista DSI-ului nu se da): citit tot pe firul cititorului,
# inaintea pistelor caruselului, cu un singur filtru de sectiuni (0x02, extensia = SID, cu DMX_CHECK_CRC: forma
# SarcinaTabel a analizei fluxului, folosita pe receptor), cel mult TERMEN_PMT_S, inchis inainte de restul; din el
# harta pistelor (HdsCarusel.harta_pmt) si pista DSI-ului aplicatiei (HdsCarusel.pid_dsi). Fara PMT sau fara pista:
# FAZA_FARA cu "motiv" ("pmt", "pista"), fara niciun alt filtru.
#
# Arborele se scrie in `dosar` (HdsCarusel.scrie_arbore, cu dosar + ".json" alaturi) cand caruselul s-a schimbat: pe loc
# cand e complet, altfel cel mult o data la SCRIERE_MIN_S. la_schimbare(stare) se cheama atunci DE PE FIRUL
# CITITORULUI: cine il leaga de enigma2 il trece pe firul principal (eTimer), nu atinge ecranul de aici.
#
# Starea (stare(), de pe orice fir): "faza" (FAZA_PMT cat se citeste PMT-ul, FAZA_ASTEPT pana la DSI, FAZA_MODULE cat
# lipsesc module, FAZA_GATA cand arborele e complet, FAZA_FARA cand niciun DSI nu a venit in TERMEN_DSI_S, FAZA_EROARE),
# modulele gata din cate, fisierele scrise, octetii tinuti, sectiunile primite si cele cu CRC gresit, "prea_mare"
# (un modul sau caruselul peste limitele din HdsCarusel), depasirile tamponului, filtrele deschise, ultimele erori.
#
# Neprobat pe receptor; pe PC se probeaza cu o sursa falsa si un ceas fals (test_hbbtv_carusel.py).

from __future__ import absolute_import

import threading

try:
	from Components import HdsAnalizaFlux as A
	from Components import HdsCarusel as C
except ImportError:  # pe PC: dosarul modulelor e in sys.path
	import HdsAnalizaFlux as A
	import HdsCarusel as C

POLL_MS = 100              # un pas al buclei; oprirea ceruta se vede cel tarziu dupa atat
TAMPON = 1024 * 1024       # tamponul unui filtru (DMX_SET_BUFFER_SIZE)
MAX_FILTRE = 4             # filtrele deschise deodata
MAX_CITIRI = 256           # citiri pe filtru intr-un pas
SCRIERE_MIN_S = 2.0        # un arbore incomplet se scrie cel mult o data la atat
TERMEN_DSI_S = 20.0        # fara DSI in atat: caruselul nu vine (pista gresita, criptata sau semnal slab)
TERMEN_PMT_S = 3.0         # PMT-ul serviciului (o sectiune), cand pista DSI-ului se afla aici
TAMPON_PMT = 64 * 1024

FAZA_ASTEPT, FAZA_MODULE, FAZA_GATA, FAZA_FARA, FAZA_EROARE = "astept", "module", "gata", "fara_carusel", "eroare"
FAZA_PMT = "pmt"


def _jurnal(text):
	print("[HdsCaruselDemux] %s" % text)


class CititorCarusel(object):
	"""Caruselul unui serviciu, citit pe un fir separat din demux-ul `demux` al adaptorului 0.

	pid_dsi: pista DSI-ului; harta: HdsCarusel.harta_pmt(PMT) pentru pistele modulelor (None: numai pista DSI-ului);
	dosar: unde se scrie arborele; piste_in_plus: alte piste citite de la inceput (evenimentele de flux); pmt: (PID-ul
	PMT, SID, aplicatia din AIT) cand pid_dsi e None (PMT-ul se citeste pe fir, vezi antetul). sursa, ceas si carusel
	se dau in probe (implicit: HdsAnalizaFlux.SursaDemux(demux), ceasul monoton, un HdsCarusel.Carusel nou)."""

	def __init__(self, demux, pid_dsi, dosar, harta=None, la_schimbare=None, piste_in_plus=(), sursa=None, ceas=None,
			carusel=None, pmt=None):
		self.demux = demux
		self.pid_dsi = pid_dsi
		self.dosar = dosar
		self.harta = harta
		self.la_schimbare = la_schimbare
		self.piste_in_plus = [p for p in piste_in_plus if p != pid_dsi]
		self.pmt = pmt if pid_dsi is None else None
		self.sursa = sursa
		self.ceas = ceas or A._monoton
		self.carusel = carusel or C.Carusel()
		self.oprit = threading.Event()
		self.zavor = threading.Lock()
		self.fir = None
		self.fds = {}
		self._rest = {}
		self.scrisa = 0
		self.ultima_scriere = None
		self._incomplet_la = None
		self._stare = {"faza": FAZA_PMT if self.pmt else FAZA_ASTEPT, "pid_dsi": pid_dsi, "module_gata": 0, "module": 0,
			"fisiere": 0, "complet": False, "octeti": 0, "depasiri": 0, "filtre": 0, "sectiuni": 0, "crc": 0,
			"prea_mare": False, "motiv": "", "erori": [], "lipsa": [], "dosar": dosar, "ruleaza": False}

	# ------------------------------------------------ de pe firul enigma2

	def porneste(self):
		"""Porneste firul. False daca a pornit deja."""
		if self.fir is not None:
			return False
		self.fir = threading.Thread(target=self.ruleaza, name="HdsCarusel")
		self.fir.daemon = True
		self.fir.start()
		return True

	def opreste(self, asteapta_s=1.0):
		"""Cere oprirea; asteapta firul cel mult asteapta_s (filtrele se inchid in finally, cel tarziu dupa un pas)."""
		self.oprit.set()
		f = self.fir
		if f is not None and f is not threading.current_thread():
			f.join(asteapta_s)

	def stare(self):
		with self.zavor:
			d = dict(self._stare)
			d["erori"] = list(d["erori"])
			d["lipsa"] = list(d["lipsa"])
			return d

	# ------------------------------------------------ pe firul cititorului

	def _pune(self, **k):
		with self.zavor:
			self._stare.update(k)

	def _deschide(self, pid):
		if pid is None or pid in self.fds.values() or len(self.fds) >= MAX_FILTRE:
			return
		fd = self.sursa.sectiuni(pid, crc=False, tampon=TAMPON)
		self.fds[fd] = pid
		self._rest[fd] = b""
		self._pune(filtre=len(self.fds))

	def _citeste(self, fd):
		pid = self.fds.get(fd)
		rest = self._rest.get(fd, b"")
		depasiri = 0
		for _k in range(MAX_CITIRI):
			buf = self.sursa.citeste(fd)
			if buf is None:
				break
			if buf == b"":
				depasiri += 1
				rest = b""
				continue
			sectiuni, rest = A.imparte(buf, rest)
			for s in sectiuni:
				self.carusel.sectiune(s, pid)
		self._rest[fd] = rest
		if depasiri:
			with self.zavor:
				self._stare["depasiri"] += depasiri

	def _scrie(self, acum):
		car = self.carusel
		if car.versiune == self.scrisa:
			return
		if self.ultima_scriere is not None and acum - self.ultima_scriere < SCRIERE_MIN_S and \
				self._incomplet_la == car.versiune:
			return
		arb = car.arbore()
		if not arb["complet"] and self.ultima_scriere is not None and acum - self.ultima_scriere < SCRIERE_MIN_S:
			self._incomplet_la = car.versiune    # acelasi arbore incomplet nu se mai socoteste pana trece timpul
			return
		scrise, erori = C.scrie_arbore(arb, self.dosar)
		C.scrie_json(self.dosar + ".json", C.manifest(car, arb, {"pid_dsi": self.pid_dsi, "erori_disc": erori}))
		self.scrisa, self.ultima_scriere = car.versiune, acum
		self._pune(faza=FAZA_GATA if arb["complet"] else FAZA_MODULE, fisiere=scrise, complet=arb["complet"],
			lipsa=arb["lipsa"][:8])
		if self.la_schimbare is not None:
			try:
				self.la_schimbare(self.stare())
			except Exception as e:
				_jurnal("la_schimbare: %s" % e)

	def _progres(self, inceput, acum):
		car = self.carusel
		module = list(car.module.values())
		k = {"module": len(module), "module_gata": sum(1 for m in module if car.modul_gata(m.descarcare, m.id)),
			"octeti": car.tinuti, "sectiuni": car.contoare["sectiuni"], "crc": car.contoare["crc"], "erori": car.erori[-5:],
			"prea_mare": car.contoare["prea_mult"] > 0 or any((m.eroare or "").startswith("modul prea mare") for m in module)}
		if car.dsi is None:
			k["faza"] = FAZA_FARA if acum - inceput > TERMEN_DSI_S else FAZA_ASTEPT
		elif self.scrisa == 0:
			k["faza"] = FAZA_MODULE
		self._pune(**k)

	def _citestePmt(self, inceput, durata_s):
		"""PMT-ul serviciului -> harta si pista DSI-ului aplicatiei (vezi antetul). -> True cand pista e aflata."""
		pid_pmt, sid, aplicatie = self.pmt
		harta, rest = None, b""
		fd = self.sursa.sectiuni(pid_pmt, tid=0x02, ext=sid, crc=True, tampon=TAMPON_PMT)
		self._pune(filtre=1)
		try:
			while harta is None and not self.oprit.is_set():
				acum = self.ceas()
				if acum - inceput >= TERMEN_PMT_S or (durata_s is not None and acum - inceput >= durata_s):
					break
				for _fd in self.sursa.asteapta([fd], POLL_MS):
					for _k in range(MAX_CITIRI):
						buf = self.sursa.citeste(fd)
						if buf is None:
							break
						if buf == b"":
							rest = b""
							continue
						sectiuni, rest = A.imparte(buf, rest)
						for s in sectiuni:
							h = C.harta_pmt(s)
							if h is not None and h["program"] == sid:
								harta = h
		finally:
			self.sursa.inchide(fd)
			self._pune(filtre=0)
		if harta is None:
			if not self.oprit.is_set():
				self._pune(faza=FAZA_FARA, motiv="pmt")
			return False
		pid, motiv = C.pid_dsi(harta, aplicatie)
		if pid is None:
			_jurnal("pista DSI-ului: %s" % motiv)
			self._pune(faza=FAZA_FARA, motiv="pista")
			return False
		self.pid_dsi, self.harta = pid, harta
		self.piste_in_plus = [p for p in self.piste_in_plus if p != pid]
		self._pune(faza=FAZA_ASTEPT, pid_dsi=pid)
		return True

	def ruleaza(self, durata_s=None):
		"""Bucla cititorului, pana la opreste() (sau, in probe, pana trec durata_s secunde pe ceasul dat)."""
		inceput = self.ceas()
		self._pune(ruleaza=True)
		try:
			if self.sursa is None:
				self.sursa = A.SursaDemux(self.demux)
			if self.pid_dsi is None:
				if not self.pmt or not self._citestePmt(inceput, durata_s):
					return
				inceput = self.ceas()
			self._deschide(self.pid_dsi)
			for p in self.piste_in_plus:
				self._deschide(p)
			while not self.oprit.is_set():
				for fd in self.sursa.asteapta(list(self.fds), POLL_MS):
					self._citeste(fd)
				acum = self.ceas()
				for pid in C.piste_module(self.carusel, self.harta):
					self._deschide(pid)
				self._scrie(acum)
				self._progres(inceput, acum)
				if durata_s is not None and acum - inceput >= durata_s:
					break
		except Exception as e:
			_jurnal("oprit de o eroare: %s" % e)
			self._pune(faza=FAZA_EROARE, erori=[str(e)[:200]])
		finally:
			for fd in list(self.fds):
				try:
					self.sursa.inchide(fd)
				except Exception as e:
					_jurnal("inchiderea filtrului: %s" % e)
			self.fds.clear()
			self._rest.clear()
			self._pune(filtre=0, ruleaza=False)
