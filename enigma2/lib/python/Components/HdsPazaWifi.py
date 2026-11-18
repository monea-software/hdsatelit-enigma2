# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPazaWifi.py: paznicul Wi-Fi-ului (0.7.7). O placa Wi-Fi USB care ramane fara legatura isi porneste cipul din nou
# singura, fara omul (fara setare, fara text pe ecran, fara repornirea receptorului).
#
# De ce (asistenta 906594, Octagon SF8008 V3, Realtek RTL8822CU, driverul 88x2cu; 15.11 si 10.11.2026): cipul a ramas
# „surd” (cadrele catre router fara confirmare, apoi 12 minute, alta data 2 ore, de cautari fara sa mai auda routerul),
# desi wpa_supplicant cauta tot timpul; ifdown/ifup nu reinitializeaza cipul. Numai initializarea completa a cipului
# (repornirea receptorului) l-a legat imediat. Economia de energie e deja oprita in driver (IPS_mode=0, LPS_mode=0).
#
# CE: pe ceasul jurnalului retelei (Components/HdsJurnalSistem.py, la 30 s, pe firul lui, cu starea pe care o citeste
# oricum din /sys), pentru fiecare placa Wi-Fi:
#   - legata (legatura sus): totul se sterge; daca venea dupa o repornire a cipului, un rand in jurnal (s-a legat din nou);
#   - fara legatura NEINTRERUPT cel putin PRAG_S (placa vazuta legata de cand a pornit interfata) sau PRAG_NELEGATA_S
#     (niciodata legata de atunci, iar receptorul nu are alta placa cu legatura si adresa: altfel internetul merge pe
#     cablu si Wi-Fi-ul ramas in setari nu se atinge), daca placa e configurata de om („auto” si wpa-conf in
#     /etc/network/interfaces) si e USB: /usr/bin/hds-wifi-reporneste.py (tools/), pe un fir separat: ifdown, cipul
#     dezlegat si legat din nou (incercarile 2, 4...: resetul portului USB), ifup.
#   - dupa o incercare fara legatura, urmatoarea abia dupa PAUZE_S (3 min, 10 min, 30 min, apoi o ora): un router oprit
#     peste noapte e un lucru obisnuit, iar repornirea cipului nu strica nimic, dar nici nu trebuie facuta des.
# Paznicul NU se dezarmeaza singur: dupa o repornire a cipului care lasa placa jos (sau wpa_supplicant oprit), placa
# ramane in grija lui cat timp e in setari, pana se leaga.
# NU: cat lucreaza trecerea pe alta retea (Components/HdsComutareRetea.py) sau cat receptorul sta pe alta cale dupa ea
# (rutele le tine ea, iar intoarcerea pe Wi-Fi tot ea o face), sau se instaleaza o actualizare (acelasi motiv_ocupat);
# orice lucru de retea al omului (Repornire retea, placa oprita/pornita, conectarea: Components/Network.py; cautarea
# retelelor: Components/WlanControl.py, NU si citirea starii, ceruta mereu de bara si de pagina /retea) muta
# numaratoarea de la capat; o singura repornire odata. Dupa repornire: setarile nucleului ale placii si IPv6 oprit, din
# nou (dupa_repornire).
# JURNAL: hds-retea.log (HdsJurnal "retea", "wifi"): incercarea (cat a stat fara legatura, felul, codul programului) si
# legarea de dupa ea. Fara numele retelei, fara adrese.
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau ceasul, starea, sistemul si pornirea firului.

import os
import subprocess
import sys
import threading
import time

PRAG_S = 90.0
PRAG_NELEGATA_S = 300.0
PAUZE_S = (180.0, 600.0, 1800.0, 3600.0)
PROGRAM = "/usr/bin/hds-wifi-reporneste.py"
# ca tools/enigma2.sh cu hds-actualizare-intrerupta.py: python3 izolat, fara site si fara .pyc (programul are numai
# biblioteca standard), deci nu depinde nici de bitul de executie, nici de /usr/bin/env
PYTHON = ("python3", "-I", "-S", "-B")
TERMEN_PROGRAM_S = 150
CALE_INTERFACES = "/etc/network/interfaces"
SYS_NET = "/sys/class/net/"


def _citeste(cale, maxim=262144):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (IOError, OSError):
		return ""


def configurate(text):
	"""Placile pe care omul le vrea pornite cu Wi-Fi: „auto <placa>” si wpa-conf (sau wpa-ssid) in stanza ei."""
	auto, wpa = set(), set()
	cur = None
	for rand in text.splitlines():
		p = rand.split()
		if not p or p[0].startswith("#"):
			continue
		if p[0] in ("auto", "allow-auto"):
			auto.update(p[1:])
			cur = None
		elif p[0] == "iface" and len(p) >= 2:
			cur = p[1]
		elif p[0] in ("mapping", "source", "allow-hotplug"):
			cur = None
		elif cur is not None and p[0] in ("wpa-conf", "wpa-ssid"):
			wpa.add(cur)
	return auto & wpa


def eUsb(iface, radacina=""):
	"""Placa e pe USB (calea ei in sysfs trece prin subsistemul usb)."""
	if not iface or "/" in iface:
		return False
	dev = os.path.realpath(radacina + SYS_NET + iface + "/device")
	return os.path.basename(os.path.realpath(dev + "/subsystem")) == "usb" and ":" in os.path.basename(dev)


def eWifi(iface, radacina=""):
	return os.path.isdir(radacina + SYS_NET + iface + "/wireless") or os.path.exists(radacina + SYS_NET + iface + "/phy80211")


def deRepornit(placi, radacina="", program=PROGRAM):
	"""Placile Wi-Fi USB din `placi` pentru Repornire retea (Network.restartNetwork); nimic fara program."""
	if not os.path.exists(radacina + program):
		return []
	return [p for p in placi if eWifi(p, radacina) and eUsb(p, radacina)]


def motiv_ocupat():
	"""Textul pentru care paznicul asteapta acum, sau "": trecerea pe alta retea lucreaza sau receptorul a trecut pe alta
	cale (COMUTAT: rutele si placile le tine ea in ordine, iar intoarcerea pe Wi-Fi o face tot ea), se instaleaza o
	actualizare (sau, ca la trecere, se inregistreaza un canal din retea)."""
	c = sys.modules.get("Components.HdsComutareRetea")
	if c is None:
		return ""
	try:
		unic = c._unic[0]
		if unic is not None and unic.lucreaza:
			return "lucreaza trecerea pe alta retea"
		if unic is not None and unic.mod != c.NORMAL:
			return "receptorul a trecut pe alta retea"
		return c.motiv_ocupat() or ""
	except Exception:
		return ""


def dupa_repornire():
	"""Dupa repornirea cipului (pe firul ei): interfata e alta in nucleu, deci setarile ei din /proc se pun din nou
	(HdsComutareRetea.pregateste_nucleul; si „default” le are deja), iar IPv6 oprit se aplica din nou dupa ifup
	(HdsIpv6.dupaRetea), ca dupa orice ifup din imagine."""
	c = sys.modules.get("Components.HdsComutareRetea")
	if c is not None:
		try:
			c.pregateste_nucleul()
		except Exception as e:
			print("[HdsPazaWifi] setarile nucleului: %r" % (e,))
	try:
		from Components import HdsIpv6
		HdsIpv6.dupaRetea()
	except Exception as e:
		print("[HdsPazaWifi] IPv6 dupa ifup: %r" % (e,))


def _jurnal(nivel, text):
	try:
		from Components import HdsJurnal
		(HdsJurnal.avert if nivel == "avert" else HdsJurnal.info)("retea", "wifi", text)
	except Exception:
		print("[HdsPazaWifi] %s" % text)


def _porneste_fir(tinta):
	fir = threading.Thread(target=tinta, name="HdsPazaWifi")
	fir.daemon = True
	fir.start()


def ruleaza_program(iface, usb, program=PROGRAM, termen=TERMEN_PROGRAM_S):
	"""(cod, text) de la /usr/bin/hds-wifi-reporneste.py; 127 fara program, 124 la termen."""
	argv = list(PYTHON) + [program] + (["--usb"] if usb else []) + [iface]
	try:
		r = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=termen)
		return r.returncode, r.stdout.decode("utf-8", "replace").strip()
	except FileNotFoundError:
		return 127, ""
	except subprocess.TimeoutExpired:
		return 124, ""
	except OSError as e:
		return 126, str(e)


class Paza(object):
	"""Starea si hotararile. tic(stare) de pe firul jurnalului retelei; repornirea pe firul ei (porneste_fir)."""

	def __init__(self, ceas=None, interfaces=None, usb=None, ocupat=None, program=None, porneste_fir=None,
			jurnal=None, dupa=None):
		self.ceas = ceas or time.monotonic
		self.interfaces = interfaces or (lambda: _citeste(CALE_INTERFACES))
		self.usb = usb or eUsb
		self.ocupat = ocupat or motiv_ocupat
		self.program = program or ruleaza_program
		self.porneste_fir = porneste_fir or _porneste_fir
		self.jurnal = jurnal or _jurnal
		self.dupa = dupa or dupa_repornire
		self._zavor = threading.Lock()
		self.placi = {}
		self.lucreaza = False
		self.t_amanat = None
		self.ultimul_ocupat = ""

	def amana(self, acum=None):
		"""Un lucru de retea al omului (sau Repornire retea): numaratoarea fara legatura incepe din nou de acum. Vine de
		pe firul interfetei, deci numai tine minte ora, fara zavor (tic tine zavorul cat citeste fisiere); tic o
		aplica."""
		self.t_amanat = self.ceas() if acum is None else acum

	def _placa(self, iface, acum):
		return self.placi.setdefault(iface, {"jos_din": None, "legata": False, "incercari": 0, "urmatoarea": None,
			"t_reset": None})

	def tic(self, stare, acum=None):
		"""stare = HdsJurnalSistem.stareRetea(): {placa: {"wifi", "sus", "ipv4"...}}. Intoarce placa pentru care a
		pornit o repornire, sau None."""
		acum = self.ceas() if acum is None else acum
		alta_merge = any(s.get("sus") and s.get("ipv4") for s in stare.values())
		de_pornit = None
		t_amanat = self.t_amanat
		with self._zavor:
			for iface, s in stare.items():
				if not s.get("wifi"):
					continue
				p = self._placa(iface, acum)
				if s.get("sus"):
					if p["incercari"] and p["t_reset"] is not None:
						self.jurnal("info", "%s legata din nou dupa repornirea cipului (incercarea %d, la %d s dupa ea)"
							% (iface, p["incercari"], int(max(0, acum - p["t_reset"]))))
					p.update(jos_din=None, legata=True, incercari=0, urmatoarea=None, t_reset=None)
				elif p["jos_din"] is None:
					p["jos_din"] = acum
			if t_amanat is not None:
				for p in self.placi.values():
					if p["jos_din"] is not None and p["jos_din"] < t_amanat:
						p["jos_din"] = min(t_amanat, acum)
			if self.lucreaza:
				return None
			for iface in sorted(self.placi):
				s = stare.get(iface)
				p = self.placi[iface]
				if s is None or s.get("sus") or p["jos_din"] is None:
					continue
				prag = PRAG_S if p["legata"] else PRAG_NELEGATA_S
				if acum - p["jos_din"] < prag or (p["urmatoarea"] is not None and acum < p["urmatoarea"]):
					continue
				if not p["legata"] and alta_merge:
					continue
				if iface not in configurate(self.interfaces()) or not self.usb(iface):
					continue
				motiv = self.ocupat()
				if motiv:
					if motiv != self.ultimul_ocupat:
						self.jurnal("info", "%s fara legatura, repornirea cipului asteapta: %s" % (iface, motiv))
					self.ultimul_ocupat = motiv
					return None
				self.ultimul_ocupat = ""
				p["incercari"] += 1
				self.lucreaza = True
				de_pornit = (iface, p["incercari"], int(acum - p["jos_din"]))
				break
		if de_pornit is None:
			return None
		# in afara zavorului: firul (sau, in probe, lucrul facut pe loc) il ia din nou la sfarsit
		self._lanseaza(*de_pornit)
		return de_pornit[0]

	def _lanseaza(self, iface, incercarea, fara_s):
		usb = incercarea % 2 == 0
		fel = "reset USB" if usb else "dezlegare/legare"
		self.jurnal("avert", "%s fara legatura de %d s: cipul Wi-Fi pornit din nou (incercarea %d, %s)"
			% (iface, fara_s, incercarea, fel))

		def lucru():
			cod, text = 126, ""
			try:
				cod, text = self.program(iface, usb)
				self.dupa()
			except Exception as e:
				text = text or str(e)
			finally:
				self._gata(iface, incercarea, cod, text)
		try:
			self.porneste_fir(lucru)
		except Exception as e:
			self._gata(iface, incercarea, 126, str(e))

	def _gata(self, iface, incercarea, cod, text):
		acum = self.ceas()
		with self._zavor:
			p = self.placi.get(iface)
			if p is not None:
				p["t_reset"] = acum
				p["urmatoarea"] = acum + PAUZE_S[min(incercarea, len(PAUZE_S)) - 1]
			self.lucreaza = False
		if cod == 0:
			self.jurnal("info", "%s: %s" % (iface, text or "cipul pornit din nou"))
		else:
			self.jurnal("avert", "%s: repornirea cipului n-a mers (cod %d) %s" % (iface, cod, text))


_unic = [None]


def paza():
	if _unic[0] is None:
		_unic[0] = Paza()
	return _unic[0]


def tic(stare):
	"""Din HdsJurnalSistem._tic (firul jurnalului retelei), cu starea citita deja."""
	return paza().tic(stare)


def amana():
	"""Din Components/Network.py si Components/WlanControl.py: omul (sau interfata) lucreaza cu reteaua acum."""
	try:
		paza().amana()
	except Exception:
		pass
