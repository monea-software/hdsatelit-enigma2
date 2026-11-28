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
#
# Din 0.8.0 fisierul tine si PAZNICUL RETELEI (sectiunea de la coada, PaznicRetea): acelasi fisier rulat singur, ca proces
# separat de enigma2 (`python3 -I -S -B HdsPazaWifi.py paznic`), care readuce stickul Wi-Fi cazut de pe USB si porneste
# din nou placa ramasa fara adresa sau fara client. Setarea "Repara singur reteaua" (initConfig) le opreste pe amandoua.

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
		self._generatie = object()
		self.ultimul_ocupat = ""

	def amana(self, acum=None):
		"""Un lucru de retea al omului (sau Repornire retea): numaratoarea fara legatura incepe din nou de acum. Vine de
		pe firul interfetei, deci numai tine minte ora, fara zavor (tic tine zavorul cat citeste fisiere); tic o
		aplica."""
		self.t_amanat = self.ceas() if acum is None else acum
		self._generatie = object()

	def _placa(self, iface, acum):
		return self.placi.setdefault(iface, {"jos_din": None, "legata": False, "incercari": 0, "urmatoarea": None,
			"t_reset": None, "generatie": object()})

	def tic(self, stare, acum=None):
		"""stare = HdsJurnalSistem.stareRetea(): {placa: {"wifi", "sus", "ipv4"...}}. Intoarce placa pentru care a
		pornit o repornire, sau None."""
		acum = self.ceas() if acum is None else acum
		alta_merge = any(s.get("sus") and s.get("ipv4") for s in stare.values())
		de_pornit = None
		generatie = self._generatie
		t_amanat = self.t_amanat
		with self._zavor:
			for iface, p in self.placi.items():
				if not stare.get(iface, {}).get("wifi"):
					p["generatie"] = object()
			for iface, s in stare.items():
				if not s.get("wifi"):
					continue
				p = self._placa(iface, acum)
				if s.get("sus"):
					p["generatie"] = object()
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
				de_pornit = (iface, p["incercari"], int(acum - p["jos_din"]), generatie, p["generatie"])
				break
		if de_pornit is None:
			return None
		# in afara zavorului: firul (sau, in probe, lucrul facut pe loc) il ia din nou la sfarsit
		self._lanseaza(*de_pornit)
		return de_pornit[0]

	def _valabila(self, iface, generatie, generatie_placa):
		# Only the worker reads disk/sysfs here. The UI invalidates a queued
		# decision without waiting for the watchdog lock or for this I/O.
		if generatie is not self._generatie:
			return False
		if iface not in configurate(self.interfaces()) or not self.usb(iface) or self.ocupat():
			return False
		with self._zavor:
			p = self.placi.get(iface)
			return (generatie is self._generatie and p is not None
				and generatie_placa is p["generatie"] and p["jos_din"] is not None)

	def _anuleaza(self, iface, incercarea):
		with self._zavor:
			p = self.placi.get(iface)
			if p is not None:
				# A skipped command is not an attempt and must not increase backoff.
				p["incercari"] = min(p["incercari"], incercarea - 1)
			self.lucreaza = False
		self.jurnal("info", "%s: repornirea cipului anulata, starea retelei s-a schimbat" % iface)

	def _lanseaza(self, iface, incercarea, fara_s, generatie, generatie_placa):
		usb = incercarea % 2 == 0
		fel = "reset USB" if usb else "dezlegare/legare"
		self.jurnal("avert", "%s fara legatura de %d s: repornirea cipului Wi-Fi programata (incercarea %d, %s)"
			% (iface, fara_s, incercarea, fel))

		def lucru():
			cod, text = 126, ""
			pornit = False
			try:
				if not self._valabila(iface, generatie, generatie_placa):
					return
				pornit = True
				cod, text = self.program(iface, usb)
				self.dupa()
			except Exception as e:
				text = text or str(e)
				if not pornit:
					self.jurnal("avert", "%s: reverificarea repornirii cipului a esuat" % iface)
			finally:
				if pornit:
					self._gata(iface, incercarea, cod, text)
				else:
					self._anuleaza(iface, incercarea)
		try:
			self.porneste_fir(lucru)
		except Exception as e:
			self._gata(iface, incercarea, 126, str(e))

	def _gata(self, iface, incercarea, cod, text):
		acum = self.ceas()
		with self._zavor:
			p = self.placi.get(iface)
			if p is not None and p["incercari"] == incercarea and p["jos_din"] is not None:
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


_paznic_cerut = [False]


def tic(stare):
	"""Din HdsJurnalSistem._tic (firul jurnalului retelei), cu starea citita deja. La primul ceas porneste si paznicul
	retelei (procesul separat de mai jos), daca nu l-a pornit deja tools/enigma2.sh; cu setarea "Repara singur reteaua"
	= Nu nu reporneste nici cipul."""
	if not _paznic_cerut[0]:
		_paznic_cerut[0] = True
		try:
			porneste_paznic()
		except Exception as e:
			print("[HdsPazaWifi] paznicul retelei: %r" % (e,))
	if os.path.exists(SEMN_OPRIT):
		return None
	return paza().tic(stare)


def amana():
	"""Din Components/Network.py si Components/WlanControl.py: omul (sau interfata) lucreaza cu reteaua acum. Si paznicul
	retelei (procesul separat) asteapta PAUZA_OM_S de la ora fisierului STAMPILA_OM."""
	try:
		paza().amana()
	except Exception:
		pass
	try:
		with open(STAMPILA_OM, "w"):
			pass
		os.utime(STAMPILA_OM, None)
	except (IOError, OSError):
		pass


def initConfig():
	"""config.usage.hds_retea_repara ("Repara singur reteaua", Da din fabrica; setup.xml hds_retea_comutare, randul 2, si
	cardul din pagina web /retea). Nu = semnul SEMN_OPRIT, citit de paznicul retelei la fiecare ceas si de tic(): nici
	paznicul retelei, nici repornirea cipului Wi-Fi. Chemata din Components/UsageConfig.py."""
	from Components.config import config, ConfigYesNo
	u = config.usage
	if "hds_retea_repara" not in u.content.items:
		u.hds_retea_repara = ConfigYesNo(default=True)
		u.hds_retea_repara.addNotifier(aplicaSetarea, initial_call=True, immediate_feedback=False)
	return u.hds_retea_repara


def aplicaSetarea(element=None, cale=None):
	"""Semnul SEMN_OPRIT dupa setare: scris la Nu, sters la Da (numai cand nu e deja asa: fara scrieri pe flash la
	fiecare pornire)."""
	cale = cale or SEMN_OPRIT
	pornita = True if element is None else bool(element.value)
	try:
		if pornita and os.path.exists(cale):
			os.remove(cale)
		elif not pornita and not os.path.exists(cale):
			with open(cale, "w") as f:
				f.write("Repara singur reteaua: Nu\n")
	except (IOError, OSError) as e:
		print("[HdsPazaWifi] semnul setarii: %r" % (e,))


# ====================================================================================================================
# PAZNICUL RETELEI (0.8.0, NET1, Eduard 25.11.2026 08:07): un proces separat, care nu depinde de enigma2
# ====================================================================================================================
#
# De ce (Amiko Viper 4K V20, 25.11.2026 01:40): stickul Wi-Fi USB (RTL8188FU, portul 1-2) a cazut de pe magistrala chiar
# in timpul incarcarii firmware-ului la pornire ("USB disconnect", scrieri -71 apoi -19); nucleul nu l-a mai enumerat
# deloc, placa wlan0 nu a mai aparut, iar receptorul (numai pe Wi-Fi) a stat 4,5 ore fara retea pana l-a oprit omul de
# mana. Paznicul Wi-Fi de mai sus lucreaza numai cu o placa PREZENTA si numai cat merge enigma2. Eduard: "de multe ori
# cand se lua curentul, nu mai mergea netul ... nici chiar pe cablu": receptorul porneste in ~30 s, routerul in 2-3
# minute; udhcpc din ifup ("-R -b -t 10 -T 1 -A 3", busybox din OE-Alliance) nu renunta, dar daca ifup a cazut la
# pornire (placa lipsea, wpa_supplicant n-a pornit) sau clientul DHCP a murit, nimeni nu-l mai cheama.
#
# CUM: `python3 -I -S -B HdsPazaWifi.py paznic`, pornit de tools/enigma2.sh inainte de enigma2 (la fiecare pornire a
# lui din inittab; fara Python cand paznicul ruleaza deja) si, ca rezerva, din tic() de mai sus, o data pe pornire a
# interfetei. Un singur paznic odata (flock pe PID_PAZNIC). La CEAS_S citeste /etc/network/interfaces si /sys; pentru
# placile "auto" din interfaces face cel mult un pas pe ceas, dupa PRAG_PAZNIC_S de cand a vazut lipsa, cu pauze care cresc:
#   - placa Wi-Fi configurata LIPSESTE: portul USB pe care a fost vazuta legata (STARE_USB, scris numai cand se
#     schimba, ca sa se stie si dupa o repornire: dupa deconectare sysfs nu-l mai arata). Daca portul e gol sau are
#     acelasi dispozitiv (VID:PID) fara placa de retea: alimentarea LUI oprita si pornita (ClearPortFeature /
#     SetPortFeature PORT_POWER prin usbfs, pe hub-ul lui; ca scoaterea si bagarea stickului), numai daca hub-ul comuta
#     porturile unul cate unul (sau toate celelalte porturi ale lui sunt goale); altfel, daca stickul e acolo, numai el
#     scos si pus din nou logic (authorized 0/1); apoi ifdown -f / ifup -f. Un reset USB nu ajunge: interfata fara
#     driver ramane fara driver (probat pe V20). NICIODATA un port cu alt dispozitiv (un disc poate inregistra),
#     niciodata un hub intreg sau controlerul; cel mult len(PAUZE_USB_S) incercari pe pornire;
#   - placa prezenta, dar oprita (fara IFF_UP), Wi-Fi fara wpa_supplicant, sau DHCP cu legatura, fara adresa si fara
#     udhcpc viu: ifdown -f, apoi ifup -f (ifup porneste singurul udhcpc al placii; niciodata killall udhcpc);
#   - DHCP cu legatura si udhcpc viu, dar fara adresa: SIGUSR1 (cere adresa acum, nu la runda lui);
#   - Wi-Fi cu wpa_supplicant viu, dar neasociat: `wpa_cli reassociate` (cipul il reporneste paznicul Wi-Fi din enigma2).
# NU face nimic: cu setarea "Repara singur reteaua" = Nu (SEMN_OPRIT, pus de initConfig), pentru o placa fara "auto"
# (oprita de om in Retea) sau cu adresa scrisa de om (static: o muta trecerea pe alta retea), daca omul a lucrat cu
# reteaua in ultimele PAUZA_OM_S (STAMPILA_OM, din amana()), cat ruleaza opkg (o actualizare) sau o repornire a cipului
# (lacatul lui hds-wifi-reporneste.py, tinut si de paznic cat face un pas), daca o placa are legatura si adresa
# (reteaua merge). O inregistrare din retea nu poate suferi: pasii se fac numai cand nicio placa nu are retea.
# JURNAL: hds-retea.log, modulul "paznic": ce a vazut, ce a facut si daca a ajutat (placa are din nou legatura si adresa).
# Probele de pe PC dau sistemul fals (clasa Sistem); numai biblioteca standard.

SEMN_OPRIT = "/etc/hds-retea-fara-reparare"
STAMPILA_OM = "/var/run/hds-retea-om"
PID_PAZNIC = "/var/run/hds-paza-retea.pid"
STARE_USB = "/etc/hds-retea-wifi-usb"
LACAT_REPORNIRE = "/var/run/hds-wifi-reporneste.lock"
CALE_JURNAL = "/home/root/logs/hds-retea.log"
SYS_USB = "/sys/bus/usb/devices/"
IFUP = "/sbin/ifup"
IFDOWN = "/sbin/ifdown"
CEAS_S = 30.0
PRAG_PAZNIC_S = 60.0
PAUZA_OM_S = 120.0
PAUZE_IFUP_S = (60.0, 180.0, 600.0, 1800.0, 3600.0)
PAUZE_DHCP_S = (60.0, 120.0, 300.0, 600.0)
PAUZE_ASOCIERE_S = (120.0, 300.0, 900.0, 1800.0, 3600.0)
PAUZE_USB_S = (120.0, 300.0, 900.0, 1800.0, 3600.0)
ASTEAPTA_PLACA_S = 25.0
# adresa venita in cel mult atat dupa sfarsitul unui pas e de la el ("a ajutat"); mai tarziu, de la altceva
DUPA_PAS_S = 45.0
# Portul GOL (stickul a cazut de pe magistrala, ca pe V20 la 25.11 01:40): alimentarea portului oprita 2 s si pornita il
# aduce inapoi. Probat pe V20 (25.11 10:14-10:25, pe cablu): stickul scos de pe magistrala cu /sys/bus/usb/devices/1-2/remove
# (portul ramane alimentat, legat, dar neactiv, ca dupa caderea reala), paznicul a repornit portul si wlan0 a avut adresa
# la +90 s, de 3 ori din 3. De stiut (proba din 09:04): pe ehci-ul acestui nucleu un port lasat NEALIMENTAT nu se vede in
# nucleu ca deconectare (placa ramane, cu legatura raportata de driver), deci alimentarea se porneste mereu la loc.
# False = numai un rand in jurnal.
PORT_GOL_REPORNIT = True
RADACINA_RECEPTOR = "/proc/stb"


def stanze(text):
	"""{placa: {"auto": bool, "mod": "dhcp"/"static"/..., "wpa": bool}} din /etc/network/interfaces (fara lo)."""
	r = {}
	auto = set()
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
			r.setdefault(cur, {"mod": p[3] if len(p) >= 4 else "", "wpa": False})
		elif p[0] in ("mapping", "source", "allow-hotplug"):
			cur = None
		elif cur is not None and p[0] in ("wpa-conf", "wpa-ssid"):
			r[cur]["wpa"] = True
	for n, s in r.items():
		s["auto"] = n in auto
	return dict((n, s) for n, s in r.items() if n != "lo" and "/" not in n)


def port_din_cale(cale):
	"""Portul USB al unei placi din calea ei reala in sysfs: .../usb1/1-2/1-2:1.0 -> "1-2"; altfel None."""
	b = os.path.basename(cale.rstrip("/"))
	if ":" not in b:
		return None
	port = b.split(":")[0]
	return port if hub_si_port(port) is not None else None


def hub_si_port(port):
	"""("usb1", 2) pentru "1-2", ("1-1", 3) pentru "1-1.3"; None pentru altceva."""
	try:
		bus, rest = port.split("-", 1)
		if "." in rest:
			sus, nr = rest.rsplit(".", 1)
			if not sus or not all(x.isdigit() for x in sus.split(".")):
				return None
			return "%d-%s" % (int(bus), sus), int(nr)
		return "usb%d" % int(bus), int(rest)
	except (ValueError, AttributeError):
		return None


def _jurnal_paznic(nivel, text):
	"""Un rand in hds-retea.log, in forma lui Components/HdsJurnal.py, scris direct (paznicul nu ruleaza in enigma2)."""
	try:
		rand = "%s [%s] [paznic] %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
			"AVERT" if nivel == "avert" else "INFO", " ".join(("%s" % text).split())[:900])
		d = os.path.dirname(CALE_JURNAL)
		if not os.path.isdir(d):
			os.makedirs(d)
		try:
			if os.path.getsize(CALE_JURNAL) >= 256 * 1024:
				if os.path.exists(CALE_JURNAL + ".1"):
					os.replace(CALE_JURNAL + ".1", CALE_JURNAL + ".2")
				os.replace(CALE_JURNAL, CALE_JURNAL + ".1")
		except OSError:
			pass
		fd = os.open(CALE_JURNAL, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
		try:
			os.write(fd, rand.encode("utf-8", "replace"))
		finally:
			os.close(fd)
	except Exception:
		pass


class Sistem(object):
	"""Tot ce citeste si atinge paznicul pe receptor; probele de pe PC dau unul fals."""

	def __init__(self):
		self._sock = None

	def acum(self):
		return time.monotonic()

	def ceas(self):
		return time.time()

	def dormi(self, s):
		time.sleep(s)

	def citeste(self, cale, maxim=262144):
		return _citeste(cale, maxim)

	def exista(self, cale):
		return os.path.exists(cale)

	def mtime(self, cale):
		try:
			return os.stat(cale).st_mtime
		except OSError:
			return None

	def realpath(self, cale):
		return os.path.realpath(cale)

	def listeaza(self, cale):
		try:
			return sorted(os.listdir(cale))
		except OSError:
			return []

	def scrie(self, cale, text):
		try:
			nou = cale + ".nou"
			with open(nou, "w") as f:
				f.write(text)
				f.flush()
				os.fsync(f.fileno())
			os.replace(nou, cale)
			return True
		except (IOError, OSError):
			return False

	def ipv4(self, iface):
		"""Adresa IPv4 principala a placii (SIOCGIFADDR), sau ""."""
		import fcntl
		import socket
		import struct
		try:
			if self._sock is None:
				self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			r = fcntl.ioctl(self._sock.fileno(), 0x8915, struct.pack("256s", iface[:15].encode()))
			return socket.inet_ntoa(r[20:24])
		except (IOError, OSError):
			return ""

	def viu(self, cale_pid, nume):
		"""PID-ul din fisier, daca e viu si e programul `nume` (/proc/<pid>/comm); altfel 0."""
		t = _citeste(cale_pid, 64).strip()
		if not t.isdigit():
			return 0
		return int(t) if _citeste("/proc/%s/comm" % t, 64).strip() == nume else 0

	def ruleaza(self, nume):
		"""Un proces cu numele `nume` (/proc/<pid>/comm) ruleaza acum."""
		for p in self.listeaza("/proc"):
			if p.isdigit() and _citeste("/proc/%s/comm" % p, 64).strip() == nume:
				return True
		return False

	def semnal(self, pid, sig):
		try:
			os.kill(pid, sig)
			return True
		except OSError:
			return False

	def comanda(self, argv, termen=60):
		try:
			r = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
				timeout=termen)
			return r.returncode, " ".join(r.stdout.decode("utf-8", "replace").split())[-300:]
		except FileNotFoundError:
			return 127, ""
		except subprocess.TimeoutExpired:
			return 124, ""
		except OSError as e:
			return 126, str(e)

	def ia_lacat(self):
		"""Lacatul lui hds-wifi-reporneste.py, fara asteptare: descriptorul, None daca il tine altcineva, -1 fara lacat."""
		import fcntl
		try:
			fd = os.open(LACAT_REPORNIRE, os.O_RDWR | os.O_CREAT, 0o644)
		except OSError:
			return -1
		try:
			fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
			return fd
		except (IOError, OSError):
			os.close(fd)
			return None

	def lasa_lacat(self, fd):
		if fd is not None and fd >= 0:
			try:
				os.close(fd)
			except OSError:
				pass

	def nod_usb(self, dispozitiv):
		bus = _citeste(SYS_USB + dispozitiv + "/busnum", 16).strip()
		dev = _citeste(SYS_USB + dispozitiv + "/devnum", 16).strip()
		if not (bus.isdigit() and dev.isdigit()):
			return None
		return "/dev/bus/usb/%03d/%03d" % (int(bus), int(dev))

	def _control(self, nod, tip, cerere, valoare, index, lungime=0):
		"""USBDEVFS_CONTROL pe nodul usbfs (struct usbdevfs_ctrltransfer, asezarea nativa: si pe 64 de biti)."""
		import ctypes
		import fcntl
		import struct
		buf = ctypes.create_string_buffer(max(lungime, 1))
		s = struct.pack("@BBHHHIP", tip, cerere, valoare, index, lungime, 2000, ctypes.addressof(buf) if lungime else 0)
		ioc = (3 << 30) | (len(s) << 16) | (ord("U") << 8) | 0
		fd = os.open(nod, os.O_RDWR)
		try:
			fcntl.ioctl(fd, ioc, s)
		finally:
			os.close(fd)
		return buf.raw[:lungime]

	def hub_individual(self, hub):
		"""True: hub-ul comuta alimentarea fiecarui port (wHubCharacteristics, bitii 0-1 = 01); False: toate odata sau
		deloc; None: necitit."""
		nod = self.nod_usb(hub)
		if nod is None:
			return None
		try:
			d = self._control(nod, 0xA0, 6, 0x2900, 0, 9)  # GET_DESCRIPTOR, descriptorul hub-ului
			return (bytearray(d)[3] & 3) == 1
		except (IOError, OSError, IndexError):
			return None

	def alimentare_port(self, hub, port, pornit):
		"""SetPortFeature / ClearPortFeature(PORT_POWER) pe portul `port` al hub-ului (cererea uhubctl, prin usbfs)."""
		nod = self.nod_usb(hub)
		if nod is None:
			raise OSError("hub-ul %s nu are nod in /dev/bus/usb" % hub)
		self._control(nod, 0x23, 3 if pornit else 1, 8, port)

	def reautorizeaza(self, dispozitiv):
		"""Dispozitivul USB scos si pus din nou logic (authorized 0, apoi 1): interfetele lui se fac din nou si driverul
		le ia de la capat, fara sa atinga alt port."""
		cale = SYS_USB + dispozitiv + "/authorized"
		with open(cale, "w") as f:
			f.write("0")
		time.sleep(1.0)
		with open(cale, "w") as f:
			f.write("1")

	def jurnal(self, nivel, text):
		_jurnal_paznic(nivel, text)


def _pauza(pauze, n):
	return pauze[min(max(n, 1), len(pauze)) - 1]


def _placa_noua():
	return {"rau": None, "din": None, "n": 0, "urm": None, "pas": "", "t_pas": None}


class PaznicRetea(object):
	"""Hotararile paznicului retelei; tic() o data la CEAS_S."""

	def __init__(self, sistem=None, stare_usb=STARE_USB):
		self.s = sistem or Sistem()
		self.stare_usb = stare_usb
		self.pornit = self.s.acum()
		self.placi = {}
		self.ultimul_motiv = None
		self.memorie_usb = self._citeste_memoria()

	# ---- memoria portului USB al placilor Wi-Fi (ramane si dupa o repornire)

	def _citeste_memoria(self):
		m = {}
		for rand in self.s.citeste(self.stare_usb, 4096).splitlines():
			p = rand.split()
			if len(p) == 3 and hub_si_port(p[1]) is not None:
				m[p[0]] = (p[1], p[2])
		return m

	def _tine_minte(self, iface, port, vidpid):
		if self.memorie_usb.get(iface) == (port, vidpid):
			return
		self.memorie_usb[iface] = (port, vidpid)
		text = "".join("%s %s %s\n" % (n, v[0], v[1]) for n, v in sorted(self.memorie_usb.items()))
		if self.s.scrie(self.stare_usb, text):
			self.s.jurnal("info", "%s tinuta minte pe portul USB %s (%s)" % (iface, port, vidpid))

	def _vidpid(self, dispozitiv):
		v = self.s.citeste(SYS_USB + dispozitiv + "/idVendor", 16).strip()
		p = self.s.citeste(SYS_USB + dispozitiv + "/idProduct", 16).strip()
		return "%s:%s" % (v, p) if v and p else ""

	# ---- starea

	def _stare(self, iface):
		r = {"exista": self.s.exista(SYS_NET + iface), "wifi": False, "legatura": False, "pornita": False, "ipv4": ""}
		if not r["exista"]:
			return r
		r["wifi"] = self.s.exista(SYS_NET + iface + "/wireless") or self.s.exista(SYS_NET + iface + "/phy80211")
		r["legatura"] = self.s.citeste(SYS_NET + iface + "/carrier", 16).strip() == "1"
		try:
			r["pornita"] = int(self.s.citeste(SYS_NET + iface + "/flags", 32).strip() or "0", 16) & 1 == 1
		except ValueError:
			r["pornita"] = False
		r["ipv4"] = self.s.ipv4(iface)
		if r["wifi"] and r["legatura"]:
			port = port_din_cale(self.s.realpath(SYS_NET + iface + "/device"))
			if port and self.s.exista(SYS_USB + port):
				vp = self._vidpid(port)
				if vp:
					self._tine_minte(iface, port, vp)
		return r

	def _motiv_asteptare(self):
		if self.s.exista(SEMN_OPRIT):
			return "setarea Repara singur reteaua e Nu"
		t = self.s.mtime(STAMPILA_OM)
		if t is not None and 0 <= self.s.ceas() - t < PAUZA_OM_S:
			return "omul lucreaza cu reteaua"
		if self.s.ruleaza("opkg"):
			return "se instaleaza o actualizare"
		return ""

	def _problema(self, iface, cfg, st):
		"""(felul, textul) pentru ce nu merge la placa, sau (None, "")."""
		if not st["exista"]:
			if cfg["wpa"]:
				return "lipsa", "placa Wi-Fi %s lipseste" % iface
			return None, ""
		wifi = cfg["wpa"]
		if wifi and not st["wifi"]:
			return None, ""
		# cu adresa si legatura merge; un cablu scos (adresa ramasa, fara legatura) nu e treaba paznicului, dar un Wi-Fi
		# neasociat isi tine adresa veche (udhcpc nu o sterge la pierderea legaturii), deci adresa singura nu ajunge
		if st["ipv4"] and (st["legatura"] or not wifi):
			return None, ""
		if not st["pornita"]:
			return "oprita", "%s nu e pornita" % iface
		if wifi and not self.s.viu("/var/run/wpa_supplicant.%s.pid" % iface, "wpa_supplicant") \
				and not self.s.exista("/var/run/wpa_supplicant/" + iface):
			return "fara-wpa", "%s fara wpa_supplicant" % iface
		if wifi and not st["legatura"]:
			return "neasociat", "%s nu e legata la reteaua Wi-Fi" % iface
		if st["ipv4"] or not st["legatura"] or cfg["mod"] != "dhcp":
			return None, ""
		if self.s.viu("/var/run/udhcpc.%s.pid" % iface, "udhcpc"):
			return "fara-adresa", "%s are legatura, dar nu are adresa (udhcpc o cere)" % iface
		return "fara-dhcp", "%s are legatura, dar nu are adresa si nici client DHCP" % iface

	def tic(self):
		"""Un ceas: citeste starea, scrie ce s-a reparat, face cel mult un pas. Intoarce (placa, pas) sau None."""
		acum = self.s.acum()
		cfg = stanze(self.s.citeste(CALE_INTERFACES))
		stari = dict((n, self._stare(n)) for n, c in cfg.items() if c["auto"])
		merge = sorted(n for n, st in stari.items() if st["exista"] and st["legatura"] and st["ipv4"])
		probleme = {}
		for n in sorted(stari):
			fel, text = self._problema(n, cfg[n], stari[n])
			p = self.placi.setdefault(n, _placa_noua())
			if fel is None:
				if p["rau"] is not None and stari[n]["ipv4"]:
					if p["pas"] and acum - p["t_pas"] <= DUPA_PAS_S:
						self.s.jurnal("info", "%s merge din nou (legatura si adresa), la %d s dupa pasul: %s (a ajutat)"
							% (n, int(max(0, acum - p["t_pas"])), p["pas"]))
					elif p["pas"]:
						self.s.jurnal("info", "%s merge din nou (legatura si adresa), la %d s dupa ultimul meu pas (%s): nu de la el"
							% (n, int(max(0, acum - p["t_pas"])), p["pas"]))
					else:
						self.s.jurnal("info", "%s merge din nou (legatura si adresa), fara niciun pas al paznicului" % n)
				self.placi[n] = _placa_noua()
				continue
			if p["rau"] != fel:
				# alt fel de lipsa (de pilda trecerea pe alta retea opreste placa ramasa fara adresa): numaratoarea
				# merge mai departe de la prima lipsa, pauzele o iau de la capat
				p.update(rau=fel, din=acum if p["din"] is None else p["din"], n=0, urm=None)
				self.s.jurnal("info", "am vazut: %s" % text)
			probleme[n] = fel
		for n in [n for n in self.placi if n not in stari]:
			del self.placi[n]
		if not probleme:
			self.ultimul_motiv = None
			return None
		motiv = ("reteaua merge pe %s" % ", ".join(merge)) if merge else self._motiv_asteptare()
		if motiv:
			if motiv != self.ultimul_motiv:
				self.s.jurnal("info", "nu fac nimic acum: %s" % motiv)
			self.ultimul_motiv = motiv
			if motiv == "omul lucreaza cu reteaua":
				for p in self.placi.values():
					if p["din"] is not None:
						p["din"] = acum
			return None
		self.ultimul_motiv = None
		for n in sorted(probleme):
			fel = probleme[n]
			p = self.placi[n]
			if acum - max(p["din"], self.pornit) < PRAG_PAZNIC_S or (p["urm"] is not None and acum < p["urm"]):
				continue
			if fel == "lipsa" and p["n"] >= len(PAUZE_USB_S):
				continue
			lacat = self.s.ia_lacat()
			if lacat is None:
				self.s.jurnal("info", "%s: astept, paznicul Wi-Fi reporneste cipul acum" % n)
				return None
			try:
				p["n"] += 1
				pas = self._pas(n, fel, p["n"])
			finally:
				self.s.lasa_lacat(lacat)
			acum = self.s.acum()
			pauze = {"lipsa": PAUZE_USB_S, "fara-adresa": PAUZE_DHCP_S, "neasociat": PAUZE_ASOCIERE_S}.get(fel, PAUZE_IFUP_S)
			p["urm"] = acum + (_pauza(pauze, p["n"]) if pas else PAUZE_IFUP_S[-1])
			if pas:
				p["pas"], p["t_pas"] = pas, acum
				return n, pas
		return None

	# ---- pasii

	def _reporneste_placa(self, iface):
		c1, t1 = self.s.comanda([IFDOWN, "-f", iface], 60)
		c2, t2 = self.s.comanda([IFUP, "-f", iface], 90)
		return c2, t2 or t1

	def _pas(self, iface, fel, n):
		"""Face pasul; intoarce ce a facut (pentru jurnal), sau "" daca n-a facut nimic."""
		if fel == "fara-adresa":
			pid = self.s.viu("/var/run/udhcpc.%s.pid" % iface, "udhcpc")
			if not pid or not self.s.semnal(pid, 10):  # SIGUSR1 = cere adresa acum
				return ""
			self.s.jurnal("info", "%s fara adresa: i-am cerut lui udhcpc sa ceara adresa acum (incercarea %d)" % (iface, n))
			return "cererea DHCP din nou"
		if fel == "neasociat":
			c, t = self.s.comanda(["wpa_cli", "-i", iface, "reassociate"], 20)
			self.s.jurnal("info", "%s neasociat: am cerut asocierea din nou, wpa_cli reassociate (incercarea %d, cod %d)"
				% (iface, n, c))
			return "asocierea Wi-Fi din nou"
		if fel in ("fara-wpa", "oprita", "fara-dhcp"):
			c, t = self._reporneste_placa(iface)
			self.s.jurnal("avert" if c else "info", "%s: am pornit placa din nou, ifdown -f si ifup -f (incercarea %d, cod %d) %s"
				% (iface, n, c, t))
			return "pornirea placii din nou (ifup)"
		if fel == "lipsa":
			return self._readu_usb(iface, n)
		return ""

	def _porturi_ocupate(self, hub):
		"""Dispozitivele de pe porturile hub-ului, din sysfs: "1-1", "1-2" pentru usb1; "1-1.2" pentru 1-1."""
		return [d for d in self.s.listeaza(SYS_USB) if ":" not in d and (hub_si_port(d) or ("",))[0] == hub]

	def _readu_usb(self, iface, n):
		m = self.memorie_usb.get(iface)
		if m is None:
			if n == 1:
				self.s.jurnal("info", "%s lipseste, dar n-am vazut-o niciodata pe USB: nu stiu ce port sa repornesc" % iface)
			return ""
		port, vidpid = m
		hub, nr = hub_si_port(port)
		acolo = self._vidpid(port) if self.s.exista(SYS_USB + port) else ""
		if acolo and acolo != vidpid:
			self.s.jurnal("info", "%s lipseste, dar pe portul %s e alt dispozitiv (%s): nu-l ating" % (iface, port, acolo))
			return ""
		# portul e gol (stickul a cazut de pe magistrala) sau are stickul nostru fara placa de retea (driverul n-a pornit):
		# alimentarea portului oprita si pornita, ca la scoaterea si bagarea stickului (cipul porneste de la zero); fara
		# comutare pe fiecare port si cu alte dispozitive pe hub, numai stickul de acolo, scos si pus din nou logic
		if not acolo and not PORT_GOL_REPORNIT:
			if n == 1:
				self.s.jurnal("avert", "%s lipseste: stickul a cazut de pe portul USB %s (portul e gol); il aduce inapoi "
					"oprirea receptorului din priza" % (iface, port))
			return ""
		ind = self.s.hub_individual(hub)
		ocupate = [d for d in self._porturi_ocupate(hub) if d != port]
		if ind is True or (ind is False and not ocupate):
			try:
				self.s.alimentare_port(hub, nr, False)
			except (IOError, OSError) as e:
				self.s.jurnal("avert", "%s: portul USB %s nu s-a oprit: %s" % (iface, port, e))
				return ""
			self.s.dormi(2.0)
			try:
				self.s.alimentare_port(hub, nr, True)
			except (IOError, OSError) as e:
				self.s.dormi(1.0)
				try:
					self.s.alimentare_port(hub, nr, True)
				except (IOError, OSError):
					self.s.jurnal("avert", "%s: portul USB %s nu s-a pornit la loc: %s" % (iface, port, e))
					return "oprirea portului USB %s" % port
			fel = "oprirea si pornirea portului USB %s" % port
		elif acolo:
			try:
				self.s.reautorizeaza(port)
			except (IOError, OSError) as e:
				self.s.jurnal("avert", "%s: stickul de pe portul %s nu s-a scos si pus din nou: %s" % (iface, port, e))
				return ""
			fel = "stickul de pe portul USB %s scos si pus din nou (authorized 0/1)" % port
		else:
			self.s.jurnal("info", "%s lipseste: hub-ul %s nu poate opri numai portul %d%s; nu-l ating"
				% (iface, hub, nr, (" (pe alte porturi: %s)" % ", ".join(ocupate)) if ocupate else ""))
			return ""
		self.s.jurnal("avert", "%s lipseste: %s (incercarea %d din %d)" % (iface, fel, n, len(PAUZE_USB_S)))
		capat = self.s.acum() + ASTEAPTA_PLACA_S
		while self.s.acum() < capat and not self.s.exista(SYS_NET + iface):
			self.s.dormi(1.0)
		if not self.s.exista(SYS_NET + iface):
			self.s.jurnal("avert", "%s nu a aparut in %d s dupa %s" % (iface, int(ASTEAPTA_PLACA_S), fel))
			return fel
		c, t = self._reporneste_placa(iface)
		self.s.jurnal("info", "%s a aparut din nou; am pornit-o, ifdown -f si ifup -f (cod %d) %s" % (iface, c, t))
		return fel


def paznic_viu():
	"""PID-ul paznicului retelei care ruleaza, sau 0."""
	t = _citeste(PID_PAZNIC, 64).strip()
	if t.isdigit() and "HdsPazaWifi" in _citeste("/proc/%s/cmdline" % t, 4096):
		return int(t)
	return 0


def porneste_paznic(program=None):
	"""Paznicul retelei intr-o sesiune a lui, daca nu ruleaza deja (enigma2 nu-l asteapta si nu-l tine). Numai pe un
	receptor (/proc/stb): nici pe PC, nici in emulatorul enigma2, unde ifup/ifdown ar atinge reteaua calculatorului."""
	if not os.path.isdir(RADACINA_RECEPTOR) or paznic_viu():
		return False
	program = program or os.path.abspath(__file__)
	if program.endswith((".pyc", ".pyo")) and os.path.exists(program[:-1]):
		program = program[:-1]
	if not os.path.exists(program):
		return False
	try:
		subprocess.Popen(list(PYTHON) + [program, "paznic"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
		return True
	except OSError:
		return False


def bucla(paznic=None, ceas_s=CEAS_S):
	"""Paznicul retelei, pana la oprirea receptorului; 0 fara sa porneasca daca altul tine deja lacatul."""
	import fcntl
	try:
		fd = os.open(PID_PAZNIC, os.O_RDWR | os.O_CREAT, 0o644)
		fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
	except (IOError, OSError):
		return 0
	os.ftruncate(fd, 0)
	os.write(fd, ("%d\n" % os.getpid()).encode())
	paznic = paznic or PaznicRetea()
	paznic.s.jurnal("info", "paznicul retelei pornit (pid %d); placi Wi-Fi tinute minte pe USB: %s" % (os.getpid(),
		", ".join("%s pe portul %s" % (n, v[0]) for n, v in sorted(paznic.memorie_usb.items())) or "niciuna"))
	cazut = False
	while True:
		try:
			paznic.tic()
			cazut = False
		except Exception as e:
			if not cazut:
				paznic.s.jurnal("avert", "paznicul retelei: %r" % (e,))
			cazut = True
		time.sleep(ceas_s)


if __name__ == "__main__":
	if sys.argv[1:2] == ["paznic"]:
		sys.exit(bucla() or 0)
	if sys.argv[1:2] == ["o-data"]:
		print(PaznicRetea().tic())
		sys.exit(0)
	print("folosire: HdsPazaWifi.py paznic | o-data")
	sys.exit(1)
