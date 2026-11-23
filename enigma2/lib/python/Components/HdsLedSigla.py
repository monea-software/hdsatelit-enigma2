# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLedSigla.py: sigla luminata „A” a receptoarelor ZGEMMA H8 (fara afisaj), cu culori si efecte dupa ce face receptorul.
#
# PLACA (masurat pe ZGEMMA H8.2H Plus cu 0.7.8):
# - sigla are doua LED-uri (doua culori), fiecare pe o linie GPIO a SoC-ului HiSilicon (controler PL061, grupa GPIO5 de la
#   0xF8004000): gpio40 (bitul 0) culoarea de pornit, gpio45 (bitul 5) culoarea de standby, aprinse pe nivelul 1. Le comanda
#   driverul placii (modulul ofuscat h8_4, prin gpiolib): la pornit bitul 0 = /proc/stb/power/powerled si bitul 5 stins; cu
#   „aux” in /proc/stb/avs/0/input (enigma2 la intrarea in standby) bitul 0 stins si bitul 5 = standbyled; suspendled il ia
#   microcontrolerul la oprirea completa. Nodurile au numai „off” / „on”.
# - Nu exista PWM, LED RGB sau microcontroler de panou pe i2c. Scris direct, driverul nu rescrie pinii: cele doua culori se
#   pot aprinde fiecare, amandoua deodata (a treia nuanta, amestecul) sau deloc; clipirile se fac din program (eTimer), iar
#   trecerile line (respiratia) dintr-un proces python3 separat care aprinde si stinge liniile de PWM_HZ ori pe secunda
#   (masurat: ~4% dintr-un nucleu, numai cat merge respiratia).
# - ZGEMMA H8.2H SE (h8se_*) nu e masurat: driverul lui n-are powerled, numai standbyled / suspendled.
# - Liniile se scriu prin /dev/mem, cu adresarea mascata PL061 (baza + (masca << 2)): se ating numai cei doi biti ai siglei,
#   niciodata ceilalti pini ai grupei. Directia nu se schimba: modulul lucreaza numai daca driverul le-a facut deja iesiri.
# - Ce lasa driverul pe cele doua linii la pornit si in standby se tine minte (STARE_FABRICA, pe tmpfs) si se pune la loc
#   cand efectul se termina, deci „Ca din fabrică” inseamna exact purtarea driverului.
#
# STARILE, de la cea mai importanta: actualizarea care se instaleaza, cautarea de canale, antena care se roteste, semnalul
# prins (cateva secunde), inregistrarea, asistenta pornita; apoi starea de baza: pornit sau standby. Starile se afla din ce
# exista deja: registrul „ocupat” al paznicului (Components/HdsPaznic.py: scanare, cautare oarba, piste, motor,
# actualizare), motorul din nucleu (eDVBSatelliteEquipmentControl.hdsRotorMovingSlot), Components/HdsActualizari.py,
# inregistrarile din Navigation, sesiunea asistentei (Components/HdsAsistenta.py) si evTunedIn.
#
# DIN FABRICA nu se scrie nimic pe pini: pornit si standby „Ca din fabrică”, „Sigla arată ce face receptorul” Nu. Singura
# scriere din fabrica e suspendled „on” (randul opririi complete, „Aprinsă”): asa il pune imaginea producatorului, iar
# driverul porneste cu „off” (pe 0.7.8 sigla ramanea stinsa la oprirea completa). Orice alegere schimbata (pe televizor sau
# in web, /setari?id=hds_led_sigla) se vede pe loc PREVIZUALIZARE_S secunde.
# Pe un model fara pinii masurati (PLACI) raman numai randul opririi complete (suspendled) si nimic din rest.
#
# FIRUL: totul pe firul enigma2 (eTimer); ceasul starilor bate numai cand ceva nu e „din fabrica”, iar ceasul efectului
# numai cat ruleaza un efect cu cadre. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc
# direct, iar procesul de respiratie il ruleaza ca program (--pwm).

import math
import os
import signal
import subprocess
import sys
import time

# Pinii siglei, numai unde au fost masurati pe placa adevarata. baza: grupa PL061; a / b: bitul culorii de pornit / de
# standby in grupa; sus_*: True cand nivelul 1 aprinde culoarea; fabrica: octetul lasat de driver pe cei doi biti la pornit
# si in standby (cu powerled / standbyled „on”), folosit pana cand modulul il citeste singur de pe placa.
PLACI = {
	"zgemmah82hplus": {"baza": 0xF8004000, "a": 0, "b": 5, "sus_a": True, "sus_b": True,
		"fabrica": {"pornit": 0x01, "standby": 0x20}},
}
MODELE_H8 = ("zgemmah82hplus", "zgemmah8se", "zgemmah82h", "zgemmah8")

NOD_OPRIRE = "/proc/stb/power/suspendled"
DEV_MEM = "/dev/mem"
STARE_FABRICA = "/tmp/hds-led-sigla-fabrica"    # ce lasa driverul: „pornit=<octet>” si „standby=<octet>”
DATE_PL061 = 0x3FC
DIRECTIE_PL061 = 0x400

TIC_STARI_MS = 500           # cat de des se privesc starile (si se pune la loc sigla pe care driverul a schimbat-o)
INTARZIERE_STANDBY_MS = 500  # dupa intrarea / iesirea din standby: driverul isi pune intai culoarea lui
PREVIZUALIZARE_S = 6.0
SEMNAL_S = 3.0               # cat arata sigla „semnalul prins”
PWM_HZ = 100
PRAG_PWM = 0.0002       # sub 0,2 ms aprins = stins
RESPIRA_S = 3.0
LIN_S = 4.0
GAMA = 2.2


def N_(text):
	return text


try:
	_
except NameError:      # probele de pe PC
	def _(text):
		return text


# ---------------------------------------------------------------- efectele

# (valoarea, eticheta). „fabrica” numai la pornit si standby, „obisnuit” numai la starile de mai sus.
EFECTE = (
	("fabrica", N_("Ca din fabrică")),
	("obisnuit", N_("Nu se schimbă")),
	("a", N_("Culoarea de pornit")),
	("b", N_("Culoarea de standby")),
	("ab", N_("Amândouă culorile deodată")),
	("stins", N_("Stinsă")),
	("clipa", N_("Clipește în culoarea de pornit")),
	("clipb", N_("Clipește în culoarea de standby")),
	("repede", N_("Clipește repede, amândouă culorile")),
	("alterneaza", N_("Schimbă cele două culori")),
	("pe_rand", N_("Toate culorile, pe rând")),
	("respira", N_("Respiră încet, culoarea de standby")),
	("lin", N_("Trece lin prin toate culorile")),
)
# cadrele: (culoarea de pornit, culoarea de standby, milisecunde); 0 ms = static
CADRE = {
	"a": ((1, 0, 0),),
	"b": ((0, 1, 0),),
	"ab": ((1, 1, 0),),
	"stins": ((0, 0, 0),),
	"clipa": ((1, 0, 600), (0, 0, 600)),
	"clipb": ((0, 1, 600), (0, 0, 600)),
	"repede": ((1, 1, 150), (0, 0, 150)),
	"alterneaza": ((1, 0, 500), (0, 1, 500)),
	"pe_rand": ((1, 0, 350), (1, 1, 350), (0, 1, 350), (1, 1, 350)),
}
EFECTE_PWM = ("respira", "lin")
# fara procesul de respiratie (python3 lipsa, proces cazut): cel mai apropiat efect cu cadre
INLOCUIRE_PWM = {"respira": "clipb", "lin": "pe_rand"}

# randurile: (cheia din config.hds_led_sigla, starea, valoarea din fabrica)
STARI_BAZA = (("pornit", "fabrica"), ("standby", "fabrica"))
STARI_EVENIMENT = (
	("actualizare", "respira"),
	("cautare", "alterneaza"),
	("motor", "pe_rand"),
	("semnal", "ab"),
	("inregistrare", "clipb"),
	("asistenta", "ab"),
)
ORDINE = tuple(s for s, _i in STARI_EVENIMENT)     # de la cea mai importanta
MOTIVE_CAUTARE = ("scanare", "oarba", "piste")


def alegeriBaza():
	return [(v, _(e)) for v, e in EFECTE if v != "obisnuit"]


def alegeriEveniment():
	return [(v, _(e)) for v, e in EFECTE if v != "fabrica"]


def alegeriOprire():
	return [("on", _("Aprinsă")), ("off", _("Stinsă"))]


def cadre(efect):
	"""Cadrele unui efect fara respiratie; None pentru „fabrica” / „obisnuit” / efectele cu respiratie."""
	return CADRE.get(efect)


def nivelePwm(efect, t):
	"""(nivelul culorii de pornit, al celei de standby), 0..1 dupa gama, la t secunde de la inceputul efectului."""
	if efect == "respira":
		x = (1.0 - math.cos(2.0 * math.pi * (t % RESPIRA_S) / RESPIRA_S)) / 2.0
		return 0.0, x ** GAMA
	if efect == "lin":
		u = math.cos(2.0 * math.pi * (t % LIN_S) / LIN_S)
		return ((1.0 + u) / 2.0) ** GAMA, ((1.0 - u) / 2.0) ** GAMA
	return 0.0, 0.0


def _jurnal(text):
	print("[HdsLedSigla] %s" % text)


# ---------------------------------------------------------------- pinii

class Pini(object):
	"""Cele doua linii ale siglei intr-o grupa PL061, prin /dev/mem. Scrierea mascata atinge numai bitii siglei."""

	def __init__(self, baza, a, b, sus_a=True, sus_b=True, cale=DEV_MEM):
		self.baza, self.bit_a, self.bit_b = baza, a, b
		self.sus_a, self.sus_b = sus_a, sus_b
		self.masca = (1 << a) | (1 << b)
		self.cale = cale
		self.mm = None
		self.cuvinte = None

	def deschide(self):
		if self.cuvinte is not None:
			return True
		import mmap
		fd = os.open(self.cale, os.O_RDWR | getattr(os, "O_SYNC", 0))
		try:
			self.mm = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=self.baza)
		finally:
			os.close(fd)
		self.cuvinte = memoryview(self.mm).cast("I")
		return True

	def inchide(self):
		if self.cuvinte is not None:
			self.cuvinte.release()
			self.cuvinte = None
		if self.mm is not None:
			self.mm.close()
			self.mm = None

	def iesiri(self):
		"""True cand driverul a facut ambele linii iesiri (registrul de directie)."""
		return (self.cuvinte[DIRECTIE_PL061 >> 2] & self.masca) == self.masca

	def citesteBrut(self):
		return self.cuvinte[DATE_PL061 >> 2] & self.masca

	def scrieBrut(self, valoare):
		# adresa baza + (masca << 2): numai bitii din masca se schimba (PL061), deci indexul cuvantului e chiar masca
		self.cuvinte[self.masca] = valoare & self.masca

	def brut(self, a, b):
		v = 0
		if bool(a) == self.sus_a:
			v |= 1 << self.bit_a
		if bool(b) == self.sus_b:
			v |= 1 << self.bit_b
		return v

	def scrie(self, a, b):
		self.scrieBrut(self.brut(a, b))


# ---------------------------------------------------------------- procesul de respiratie (--pwm)

def ruleazaPwm(baza, a, b, sus_a, sus_b, efect, parinte=None, durata=None):
	"""Aprinde si stinge liniile de PWM_HZ ori pe secunda, cu nivelele din nivelePwm. Se opreste la SIGTERM sau cand
	enigma2 (parintele) nu mai exista; nu pune nimic la loc (o face enigma2, care stie ce urmeaza)."""
	pini = Pini(baza, a, b, sus_a, sus_b)
	pini.deschide()
	oprit = []
	signal.signal(signal.SIGTERM, lambda *x: oprit.append(1))
	perioada = 1.0 / PWM_HZ
	inceput = time.monotonic()
	urmatorul_control = inceput + 1.0
	while not oprit:
		acum = time.monotonic()
		t = acum - inceput
		if durata is not None and t >= durata:
			break
		if acum >= urmatorul_control:
			urmatorul_control = acum + 1.0
			if parinte is not None and os.getppid() != parinte:
				break
		na, nb = nivelePwm(efect, t)
		ta, tb = na * perioada, nb * perioada
		stari = [ta > PRAG_PWM, tb > PRAG_PWM]
		pini.scrie(stari[0], stari[1])
		trecut = 0.0
		for durata_pas, care in sorted(((ta, 0), (tb, 1))):
			if durata_pas <= PRAG_PWM or durata_pas >= perioada - PRAG_PWM:
				continue        # stinsa toata perioada, sau aprinsa toata perioada
			time.sleep(max(0.0, durata_pas - trecut))
			trecut = durata_pas
			stari[care] = False
			pini.scrie(stari[0], stari[1])
		time.sleep(max(0.0, perioada - trecut))
	pini.inchide()


# ---------------------------------------------------------------- motorul

class Sigla(object):
	"""Alege efectul dupa stare si il pune pe pini. Starile si ceasurile se dau din afara la probe (stari, ceas)."""

	def __init__(self, pini, setari, stari=None, ceas=None, cale_fabrica=STARE_FABRICA, porneste_pwm=None,
			fabrica_implicita=None):
		self.pini = pini
		self.setari = setari                # functie: cheie -> valoare (config.hds_led_sigla.<cheie>.value)
		self.stari = stari or StariReceptor()
		self.ceas = ceas or time.monotonic
		self.cale_fabrica = cale_fabrica
		self.porneste_pwm = porneste_pwm or self._pornestePwm
		self.fabrica = dict(fabrica_implicita or {})
		citit, suprascris = self._citesteFabrica()
		self.citit = set(citit)             # starile de baza citite de pe placa in aceasta pornire a receptorului
		self.fabrica.update(citit)
		# pinii sunt acum ai nostri (nu ai driverului); dupa o cadere a enigma2 in mijlocul unui efect, din fisier
		self.suprascris = suprascris
		self.captura = False
		self.efect = None                   # efectul pus acum (None = al driverului)
		self.cadre = None
		self.index = 0
		self.pwm = None
		self.pwm_esuat = False
		self.previzualizare = None          # (efect, pana_la)
		self.semnal_pana = 0.0
		self.pauza = False                  # intre schimbarea standby-ului si citirea culorii driverului
		self.cere_cadru = None              # functie(ms): ceasul efectului (eTimer.start)
		self.opreste_cadru = None

	# ---- starea driverului ----

	def _citesteFabrica(self):
		"""({starea: octetul driverului} citite pe placa, pinii erau ai nostri) din STARE_FABRICA (tmpfs)."""
		d, suprascris = {}, False
		try:
			with open(self.cale_fabrica, "r") as f:
				for rand in f.read(256).splitlines():
					k, _s, v = rand.partition("=")
					if k in ("pornit", "standby"):
						d[k] = int(v) & 0xFF
					elif k == "suprascris":
						suprascris = v.strip() == "1"
		except (IOError, OSError, ValueError):
			pass
		return d, suprascris

	def _scrieFabrica(self):
		try:
			with open(self.cale_fabrica, "w") as f:
				f.write("".join("%s=%d\n" % (k, self.fabrica[k]) for k in sorted(self.citit) if k in self.fabrica))
				f.write("suprascris=%d\n" % (1 if self.suprascris else 0))
		except (IOError, OSError) as e:
			_jurnal("nu pot tine minte culoarea driverului: %s" % e)

	def baza(self):
		return "standby" if self.stari.inStandby() else "pornit"

	def tineMinteDriverul(self):
		"""Ce a lasat driverul pe pini pentru starea de baza de acum; numai cand pinii nu sunt ai nostri."""
		if self.suprascris:
			return
		baza = self.baza()
		self.fabrica[baza] = self.pini.citesteBrut()
		self.citit.add(baza)
		self._scrieFabrica()

	# ---- alegerea ----

	def efectDorit(self):
		acum = self.ceas()
		if self.previzualizare is not None:
			efect, pana = self.previzualizare
			if acum < pana and efect != "_baza":
				return efect
			if acum < pana:
				return self._efectBaza() or "_driver"
			self.previzualizare = None
		if self.setari("stari"):
			for stare in self.stariActive(acum):
				efect = self.setari(stare)
				if efect and efect != "obisnuit":
					return efect
		return self._efectBaza()

	def _efectBaza(self):
		efect = self.setari(self.baza())
		return None if efect in (None, "fabrica", "obisnuit") else efect

	def stariActive(self, acum=None):
		acum = self.ceas() if acum is None else acum
		active = set()
		try:
			active = set(self.stari.active())
		except Exception as e:
			_jurnal("starile: %r" % (e,))
		if acum < self.semnal_pana:
			active.add("semnal")
		return [s for s in ORDINE if s in active]

	def laSemnal(self):
		self.semnal_pana = self.ceas() + SEMNAL_S
		self.aplica()

	def previzualizeaza(self, efect):
		"""O alegere schimbata se vede PREVIZUALIZARE_S: „fabrica” arata culoarea driverului, „obisnuit” (o stare care
		nu schimba nimic) efectul starii de baza. Un efect cu respiratie ales din nou se incearca iar cu procesul."""
		if efect in EFECTE_PWM:
			self.pwm_esuat = False
		self.previzualizare = ({"fabrica": "_driver", "obisnuit": "_baza"}.get(efect, efect),
			self.ceas() + PREVIZUALIZARE_S)
		self.aplica()

	def activ(self):
		"""Trebuie ceasul starilor? Numai cand ceva nu e din fabrica (sau o previzualizare)."""
		if self.previzualizare is not None or self.suprascris:
			return True
		if self.setari("stari"):
			return True
		return any(self.setari(k) not in (None, "fabrica") for k, _i in STARI_BAZA)

	# ---- punerea pe pini ----

	def aplica(self):
		if self.pauza:
			return
		efect = self.efectDorit()
		if efect == "_driver":
			efect = None
		if efect == self.efect and not (efect is None and self.suprascris):
			if efect is not None and self.cadre is not None and len(self.cadre) == 1:
				self._reafirma()
			return
		self._oprestePwm()
		self._opresteCadre()
		self.efect = efect
		if efect is None:
			self._puneDriverul()
			return
		if efect in EFECTE_PWM and not self.pwm_esuat:
			self._incepeSuprascrierea()
			if self.porneste_pwm(efect):
				return
			self.pwm_esuat = True
		cad = cadre(INLOCUIRE_PWM.get(efect, efect) if efect in EFECTE_PWM else efect)
		if not cad:
			self.efect = None
			self._puneDriverul()
			return
		self._incepeSuprascrierea()
		self.cadre, self.index = cad, 0
		self._cadru()

	def _incepeSuprascrierea(self):
		if not self.suprascris:
			if self.baza() not in self.citit:
				self.tineMinteDriverul()
			self.suprascris = True
			self._scrieFabrica()

	def _puneDriverul(self):
		if not self.suprascris:
			return
		brut = self.fabrica.get(self.baza())
		if brut is not None:
			self.pini.scrieBrut(brut)
		self.suprascris = False
		self._scrieFabrica()

	def _reafirma(self):
		a, b, _ms = self.cadre[0]
		if self.pini.citesteBrut() != self.pini.brut(a, b):
			self.pini.scrie(a, b)

	def _cadru(self):
		if not self.cadre:
			return
		a, b, ms = self.cadre[self.index % len(self.cadre)]
		self.pini.scrie(a, b)
		self.index += 1
		if ms and len(self.cadre) > 1 and self.cere_cadru is not None:
			self.cere_cadru(ms)

	def _opresteCadre(self):
		self.cadre = None
		if self.opreste_cadru is not None:
			self.opreste_cadru()

	# ---- respiratia ----

	def _pornestePwm(self, efect):
		python = "/usr/bin/python3"
		fisier = os.path.abspath(__file__)
		if not os.path.exists(python) or not os.path.exists(fisier):
			return False
		p = self.pini
		try:
			self.pwm = subprocess.Popen([python, fisier, "--pwm", str(p.baza), str(p.bit_a), str(p.bit_b),
				"1" if p.sus_a else "0", "1" if p.sus_b else "0", efect, str(os.getpid())],
				stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
		except (OSError, ValueError) as e:
			_jurnal("respiratia nu porneste: %s" % e)
			self.pwm = None
			return False
		return True

	def _oprestePwm(self):
		p, self.pwm = self.pwm, None
		if p is None:
			return
		try:
			p.terminate()
			p.wait(1.0)
		except Exception:
			try:
				p.kill()
				p.wait(1.0)
			except Exception:
				pass

	def verificaPwm(self):
		"""Procesul de respiratie cazut: efectul trece pe cadre (INLOCUIRE_PWM)."""
		if self.pwm is not None and self.pwm.poll() is not None:
			_jurnal("respiratia s-a oprit (cod %s), trec pe clipire" % self.pwm.returncode)
			self.pwm = None
			self.pwm_esuat = True
			self.efect = None
			self.aplica()

	# ---- standby ----

	def laSchimbareaStandby(self):
		"""Intrarea sau iesirea din standby: efectul se opreste (driverul isi pune culoarea lui), apoi peste
		INTARZIERE_STANDBY_MS se pune efectul starii noi. Culoarea driverului se citeste numai cand pinii erau ai lui
		(fara efect): altfel ar putea ramane pe pini ultimul cadru al nostru, iar la sfarsitul efectului se pune cea
		stiuta pentru starea noua."""
		self.captura = not self.suprascris
		self._oprestePwm()
		self._opresteCadre()
		self.efect = None
		self.pauza = True

	def dupaStandby(self):
		self.pauza = False
		if self.captura:
			self.tineMinteDriverul()
		self.captura = False
		self.aplica()

	def opreste(self):
		"""La iesirea enigma2: pinii ai driverului, ca in fabrica."""
		self._oprestePwm()
		self._opresteCadre()
		self.efect = None
		self._puneDriverul()


# ---------------------------------------------------------------- starile receptorului (enigma2)

class StariReceptor(object):
	"""Ce face receptorul acum, din ce exista deja in imagine. Fiecare privire e ieftina si nu arunca niciodata."""

	def __init__(self, session=None):
		self.session = session
		self._opkg = (0.0, False)

	def inStandby(self):
		m = sys.modules.get("Screens.Standby")
		return getattr(m, "inStandby", None) is not None

	def active(self):
		stari = set()
		motive = self._motivePaznic()
		if motive & set(MOTIVE_CAUTARE):
			stari.add("cautare")
		if "motor" in motive or self._rotor():
			stari.add("motor")
		if "actualizare" in motive or self._actualizare():
			stari.add("actualizare")
		if self._inregistrare():
			stari.add("inregistrare")
		if self._asistenta():
			stari.add("asistenta")
		return stari

	def _motivePaznic(self):
		m = sys.modules.get("Components.HdsPaznic")
		b = getattr(m, "_unic", [None])[0] if m is not None else None
		if b is None:
			return set()
		try:
			with b.lacat:
				return set(v[0] for v in b.ocupat.values())
		except Exception:
			return set()

	def _rotor(self):
		try:
			from enigma import eDVBSatelliteEquipmentControl
			sec = eDVBSatelliteEquipmentControl.getInstance()
			return sec is not None and int(sec.hdsRotorMovingSlot()) >= 0
		except Exception:
			return False

	def _actualizare(self):
		m = sys.modules.get("Components.HdsActualizari")
		if m is None:
			return False
		if getattr(getattr(m, "actualizari", None), "faza", None) == "instalez":
			return True
		# opkg pornit din Extensii sau din SSH: /proc/locks, cel mult o data la 2 s
		acum = time.monotonic()
		if acum - self._opkg[0] >= 2.0:
			try:
				self._opkg = (acum, bool(m.opkg_ocupat()))
			except Exception:
				self._opkg = (acum, False)
		return self._opkg[1]

	def _inregistrare(self):
		"""Numai inregistrarile adevarate (temporizatoarele care inregistreaza, si cele pornite pe loc): getRecordings
		numara si fluxurile trimise in retea (StreamService)."""
		try:
			import NavigationInstance
			nav = NavigationInstance.instance
			return nav is not None and bool(nav.RecordTimer.isRecording())
		except Exception:
			return False

	def _asistenta(self):
		m = sys.modules.get("Components.HdsAsistenta")
		if m is None:
			return False
		try:
			s = m.sesiune()
			return s is not None and bool(s.activa())
		except Exception:
			return False


# ---------------------------------------------------------------- legatura cu enigma2

_sigla = None
_ceasuri = {}


def masina():
	try:
		from Components.SystemInfo import SystemInfo
		m = SystemInfo.get("machinebuild")
		if m and m != "unknown":
			return str(m).lower()
	except Exception:
		pass
	return ""


def placa(m=None):
	return PLACI.get(masina() if m is None else m)


def areOprire(m=None):
	m = masina() if m is None else m
	return m in MODELE_H8 and os.path.exists(NOD_OPRIRE)


def areCulori(m=None):
	"""Pinii siglei masurati pentru model, /dev/mem deschis si liniile deja iesiri ale driverului."""
	p = placa(m)
	if p is None or not os.path.exists(DEV_MEM):
		return False
	pini = Pini(p["baza"], p["a"], p["b"], p["sus_a"], p["sus_b"])
	try:
		pini.deschide()
		return pini.iesiri()
	except (IOError, OSError, ValueError, TypeError) as e:
		_jurnal("pinii siglei nu se pot citi: %s" % e)
		return False
	finally:
		pini.inchide()


def initConfig():
	"""config.hds_led_sigla si SystemInfo HdsLedSigla (intrarea din meniu) / HdsLedSiglaCulori (randurile cu culori)."""
	from Components.config import config
	if "hds_led_sigla" in config.content.items:
		return
	from Components.config import ConfigSubsection, ConfigSelection, ConfigYesNo
	c = ConfigSubsection()
	config.hds_led_sigla = c
	c.oprire = ConfigSelection(default="on", choices=alegeriOprire())
	c.stari = ConfigYesNo(default=False)
	for cheie, implicit in STARI_BAZA:
		setattr(c, cheie, ConfigSelection(default=implicit, choices=alegeriBaza()))
	for cheie, implicit in STARI_EVENIMENT:
		setattr(c, cheie, ConfigSelection(default=implicit, choices=alegeriEveniment()))
	culori = False
	try:
		culori = areCulori()
	except Exception as e:
		_jurnal("pinii: %r" % (e,))
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsLedSiglaCulori"] = culori
		SystemInfo["HdsLedSigla"] = culori or areOprire()
	except Exception as e:
		_jurnal("SystemInfo: %r" % (e,))


def _cfg():
	from Components.config import config
	initConfig()
	return config.hds_led_sigla


def aplicaOprirea(element=None):
	"""Sigla la oprirea completa: suspendled, ca setarea din fabrica (driverul o da microcontrolerului)."""
	if not areOprire():
		return
	try:
		valoare = _cfg().oprire.value
		with open(NOD_OPRIRE, "r") as f:
			if f.read(16).strip() == valoare:
				return
		fd = os.open(NOD_OPRIRE, os.O_WRONLY | os.O_TRUNC)
		with os.fdopen(fd, "w") as f:
			f.write(valoare)
	except (IOError, OSError) as e:
		_jurnal("nu pot scrie %s: %s" % (NOD_OPRIRE, e))


def _ceas(nume, functie):
	t = _ceasuri.get(nume)
	if t is None:
		from enigma import eTimer
		t = eTimer()
		t.callback.append(functie)
		_ceasuri[nume] = t
	return t


def _ticStari():
	s = _sigla
	if s is None:
		return
	s.verificaPwm()
	s.aplica()
	if not s.activ():
		_ceasuri["stari"].stop()


def _pornesteStarile():
	if _sigla is not None and _sigla.activ():
		t = _ceas("stari", _ticStari)
		if not t.isActive():
			t.start(TIC_STARI_MS, False)


def _ticCadru():
	if _sigla is not None:
		_sigla._cadru()


def _dupaStandby():
	if _sigla is not None:
		_sigla.dupaStandby()
		_pornesteStarile()


def _laStandby(element=None):
	ecran = getattr(sys.modules.get("Screens.Standby"), "inStandby", None)
	if ecran is None or _sigla is None:
		return
	_sigla.laSchimbareaStandby()
	_ceas("standby", _dupaStandby).start(INTARZIERE_STANDBY_MS, True)
	try:
		if _laIesireStandby not in ecran.onClose:
			ecran.onClose.append(_laIesireStandby)
	except AttributeError:
		pass


def _laIesireStandby():
	if _sigla is None:
		return
	_sigla.laSchimbareaStandby()
	_ceas("standby", _dupaStandby).start(INTARZIERE_STANDBY_MS, True)


def _laEveniment(ev):
	try:
		from enigma import iPlayableService
	except ImportError:
		return
	if ev == getattr(iPlayableService, "evTunedIn", None) and _sigla is not None and _sigla.setari("stari"):
		_sigla.laSemnal()
		_pornesteStarile()


def _laSchimbare(cheie, valoare):
	# ultima valoare vazuta: la „Închide fără salvare” ecranul Setup pune la loc fiecare rand (si anunta), dar numai un
	# rand schimbat de adevarat se previzualizeaza
	ultima = [valoare]

	def notificator(element):
		if _sigla is None:
			return
		if element.value == ultima[0]:
			return
		ultima[0] = element.value
		if cheie != "stari":
			_sigla.previzualizeaza(element.value)
		else:
			_sigla.aplica()
		_pornesteStarile()
	return notificator


def porneste(session):
	"""Din mytest.py, dupa sesiune. Fara pinii masurati: numai randul opririi complete."""
	global _sigla
	initConfig()
	c = _cfg()
	aplicaOprirea()
	c.oprire.addNotifier(aplicaOprirea, initial_call=False)
	if _sigla is not None:
		return
	from Components.SystemInfo import SystemInfo
	if not SystemInfo.get("HdsLedSiglaCulori"):
		return
	p = placa()
	pini = Pini(p["baza"], p["a"], p["b"], p["sus_a"], p["sus_b"])
	try:
		pini.deschide()
	except (IOError, OSError, ValueError) as e:
		_jurnal("pinii siglei: %s" % e)
		return
	s = Sigla(pini, lambda k: getattr(c, k).value, StariReceptor(session), fabrica_implicita=p.get("fabrica"))
	s.cere_cadru = lambda ms: _ceas("cadru", _ticCadru).start(ms, True)
	s.opreste_cadru = lambda: _ceasuri.get("cadru") and _ceasuri["cadru"].stop()
	_sigla = s
	if s.baza() not in s.citit:
		s.tineMinteDriverul()
	from Components.config import config
	config.misc.standbyCounter.addNotifier(_laStandby, initial_call=False)
	for cheie in ("stari",) + tuple(k for k, _i in STARI_BAZA) + ORDINE:
		element = getattr(c, cheie)
		element.addNotifier(_laSchimbare(cheie, element.value), initial_call=False)
	try:
		session.nav.event.append(_laEveniment)
	except AttributeError:
		pass
	s.aplica()
	_pornesteStarile()


def opreste():
	"""La iesirea enigma2: pinii la driver (oprirea completa o tine microcontrolerul, dupa suspendled)."""
	global _sigla
	s, _sigla = _sigla, None
	for t in _ceasuri.values():
		t.stop()
	if s is not None:
		try:
			s.opreste()
		finally:
			s.pini.inchide()


if __name__ == "__main__" and len(sys.argv) >= 8 and sys.argv[1] == "--pwm":
	ruleazaPwm(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5] == "1", sys.argv[6] == "1",
		sys.argv[7], parinte=int(sys.argv[8]) if len(sys.argv) > 8 else None)
