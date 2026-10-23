# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsComutareRetea.py: trecerea singura pe alta retea cand se pierde internetul, si inapoi (din 0.4.4).
#
# CAILE: cablul (o placa fara fir cu randuri in /etc/network/interfaces) si retelele Wi-Fi salvate (blocurile cu nume
# din /etc/wpa_supplicant.conf, pe o placa Wi-Fi cu randurile wpa-conf in /etc/network/interfaces), in ordinea aleasa:
# "Cablul, apoi Wi-Fi" (din fabrica) sau "Wi-Fi, apoi cablul"; retelele Wi-Fi intre ele in ordinea din fisier. Cu o
# singura cale (de pilda numai cablul) nu se face nimic. Setarea e PORNITA din fabrica (config.usage.hds_retea_comutare).
#
# CAND: internetul il verifica Components/HdsStareRetea.py (aceleasi raspunsuri ca pictograma din bara). Dupa primul
# raspuns rau se cere o verificare noua la REVERIFICARE_S, nu la un minut; dupa PRAG_TRECERE raspunsuri rele la rand
# receptorul incearca pe rand celelalte cai: o porneste (daca era oprita), asteapta adresa, verifica internetul CHIAR
# PRIN EA (intrebarea DNS legata de placa, SO_BINDTODEVICE) si numai daca merge ramane pe ea. Fara nicio cale buna,
# totul ramane cum era si se incearca din nou dupa PAUZA_DUPA_ESEC_S.
# INAPOI: cat sta pe alta cale, calea preferata se verifica la intervalul verificarii internetului, tot prin ea (cablul
# si Wi-Fi-ul pot fi pornite deodata); dupa PRAG_INAPOI raspunsuri bune la rand receptorul se intoarce. Doua retele
# Wi-Fi pe aceeasi placa nu se pot verifica deodata: la PAUZA_WIFI_INAPOI_S receptorul incearca preferata (daca se
# aude) si, daca nu merge, se intoarce pe cea de acum.
# NU: in timpul unei actualizari (HdsActualizari, opkg), al unei inregistrari dintr-o sursa din retea si (pentru
# intoarcere) al unui canal din retea privit pe televizor: trecerea se amana pana se termina.
#
# CUM: rutele explicite, fara repornirea retelei. Ruta implicita a caii parasite se muta la METRICA_REZERVA (ramane,
# ca sa poata fi verificata), calea noua isi pune ruta ei (DHCP: udhcpc reinnoit; static: poarta din interfaces).
# Inapoi: ruta veche la metrica ei, placa pornita de noi se opreste. Doua retele Wi-Fi: wpa_cli select_network, apoi
# adresa noua prin udhcpc (eliberare + cerere). Fisierele de setari NU se schimba: dupa o repornire receptorul porneste
# pe calea lui obisnuita si o ia de la capat.
#
# ADRESA: pe cablul care merge inca (routerul fara internet) adresa ramane. Cand cablul e scos si placa lui are adresa
# scrisa de om (static in interfaces), adresa aceea se pune si pe placa Wi-Fi (daca e in aceeasi retea), iar ruta
# implicita prin Wi-Fi pleaca de la ea: receptorul raspunde la aceeasi adresa si pe Wi-Fi (muta_adresa_fixa); la
# intoarcere se ia de pe Wi-Fi. Altfel receptorul are adresa primita pe Wi-Fi. Se anunta: mesajul de pe televizor
# (adresa), numele hdsatelit.local (avahi il publica din nou cu adresa rutei implicite: /etc/init.d/hds-nume-local),
# pagina /retea (cardul trecerii).
#
# NUCLEUL (pregateste_nucleul, la pornire): rutele unei placi fara legatura (cablul scos) nu se mai folosesc
# (ignore_routes_with_linkdown), altfel ruta prin cablul scos castiga si nimic nu iese pe Wi-Fi; fiecare placa raspunde
# la ARP numai pentru adresele ei (arp_ignore = 1, arp_announce = 2), ca doua placi in aceeasi retea sa nu raspunda una
# in locul celeilalte; verificarea adresei de plecare a pachetelor primite e cea larga (rp_filter = 2): cu cea stricta
# (1, din sysctl.conf) raspunsurile venite pe placa care nu are ruta castigatoare se aruncau, deci nici verificarea
# internetului prin cealalta placa, nici calculatorul pe Wi-Fi nu primeau raspuns.
#
# CABLUL SCOS: cand placa rutei castigatoare e un cablu fara legatura, trecerea porneste pe loc (fara cele 3
# verificari). Fara nicio retea Wi-Fi salvata, pe televizor se spune o data de ce receptorul nu poate trece singur.
#
# FIRUL: deciziile pe firul enigma2 (tic() la TIC_MS, eTimer din porneste()); comenzile (ip, ifup, ifdown, wpa_cli,
# kill) pe un fir separat, numai liste de argumente (fara shell), cu termen. Fisierul nu importa nimic din enigma2 la
# incarcare: probele de pe PC dau un sistem fals.

import os
import signal
import struct
import subprocess
import sys
import threading
import time

TIC_MS = 3000
PRAG_TRECERE = 3            # raspunsuri rele la rand inainte de trecere
PRAG_INAPOI = 2             # verificari bune la rand ale caii preferate inainte de intoarcere
REVERIFICARE_S = 10.0       # dupa un raspuns rau, urmatoarea verificare
PAUZA_DUPA_ESEC_S = 600.0   # dupa o incercare fara nicio cale buna
PAUZA_WIFI_INAPOI_S = 900.0 # doua retele Wi-Fi pe aceeasi placa: cat de des se incearca preferata
PROBA_MINIM_S = 30.0        # cat de des se verifica, cel mult, calea preferata
METRICA_REZERVA = 300
TERMEN_ADRESA_S = 40.0
TERMEN_ASOCIERE_S = 30.0
TERMEN_RUTA_S = 10.0
TERMEN_COMANDA_S = 60
SO_BINDTODEVICE = getattr(__import__("socket"), "SO_BINDTODEVICE", 25)
# semnalele lui udhcpc (Linux: USR1 = cere adresa din nou, USR2 = elibereaza adresa); numerele de pe ARM/x86 cand
# modulul signal nu le are (probele de pe Windows)
SEMNAL_CERE = getattr(signal, "SIGUSR1", 10)
SEMNAL_ELIBEREAZA = getattr(signal, "SIGUSR2", 12)

CALE_INTERFACES = "/etc/network/interfaces"
CALE_WPA = "/etc/wpa_supplicant.conf"
CALE_RUTE = "/proc/net/route"
SYS_NET = "/sys/class/net/"
CTRL_WPA = "/var/run/wpa_supplicant"
NUME_LOCAL = "/etc/init.d/hds-nume-local"
VIRTUALE = ("lo", "tun", "tap", "wg", "ppp", "ipsec", "gre", "sit", "dummy", "docker", "veth", "br-")
CONF_NUCLEU = "/proc/sys/net/ipv4/conf/"
SETARI_NUCLEU = (("ignore_routes_with_linkdown", "1"), ("arp_ignore", "1"), ("arp_announce", "2"), ("rp_filter", "2"))
TERMEN_SINGURA_S = 15.0     # dupa ifup: cat se asteapta ca supplicantul sa se lege singur, inainte de select_network

CABLU = "cablu"
WIFI = "wifi"
NORMAL = "normal"
COMUTAT = "comutat"


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _ipv6DupaRetea():
	"""Dupa ifup: IPv6 oprit se aplica din nou (ifup porneste clientul IPv6; Components/HdsIpv6.dupaRetea)."""
	try:
		from Components import HdsIpv6
		HdsIpv6.dupaRetea()
	except Exception as eroare:
		_jurnal("IPv6 dupa ifup: %s" % eroare)


def _jurnal(text):
	print("[HdsComutareRetea] %s" % text)


def _citeste(cale, maxim=262144):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (IOError, OSError):
		return ""


# ---------------------------------------------------------------- setarile

def initConfig():
	"""config.usage.hds_retea_comutare (Da din fabrica) si config.usage.hds_retea_ordine ("cablu" din fabrica). Chemata
	din Components/UsageConfig.py, ca randurile din setup.xml sa le gaseasca."""
	from Components.config import config, ConfigYesNo, ConfigSelection
	u = config.usage
	if "hds_retea_comutare" not in u.content.items:
		u.hds_retea_comutare = ConfigYesNo(default=True)
	if "hds_retea_ordine" not in u.content.items:
		u.hds_retea_ordine = ConfigSelection(default=CABLU, choices=[
			(CABLU, _("Cablul, apoi Wi-Fi")),
			(WIFI, _("Wi-Fi, apoi cablul")),
		])
	return u.hds_retea_comutare, u.hds_retea_ordine


def _setare(nume, implicit):
	try:
		m = sys.modules.get("Components.config")
		return getattr(m.config.usage, nume).value
	except Exception:
		return implicit


def pornita():
	return bool(_setare("hds_retea_comutare", True))


def ordinea():
	v = _setare("hds_retea_ordine", CABLU)
	return v if v in (CABLU, WIFI) else CABLU


# ---------------------------------------------------------------- caile (pasiv, din fisiere)

def stanze(text):
	"""{placa: {"metoda": "dhcp"/"static"/..., "wpa": bool, "poarta": "a.b.c.d" sau ""}} din /etc/network/interfaces."""
	rez = {}
	cur = None
	for rand in text.splitlines():
		t = rand.strip()
		if not t or t.startswith("#"):
			continue
		p = t.split()
		if p[0] == "iface" and len(p) >= 4 and p[2] == "inet":
			cur = rez.setdefault(p[1], {"metoda": p[3], "wpa": False, "poarta": "", "adresa": "", "masca": ""})
			cur["metoda"] = p[3]
			continue
		if p[0] in ("auto", "allow-hotplug", "mapping", "source", "iface"):
			cur = None if p[0] != "iface" else cur
			continue
		if cur is None:
			continue
		if p[0] in ("wpa-conf", "wpa-ssid", "wpa-driver"):
			cur["wpa"] = True
		elif p[0] == "gateway" and len(p) >= 2:
			cur["poarta"] = p[1]
		elif p[0] == "address" and len(p) >= 2:
			cur["adresa"] = p[1].split("/")[0]
			if "/" in p[1]:
				cur["masca"] = p[1].split("/")[1]
		elif p[0] == "netmask" and len(p) >= 2:
			cur["masca"] = p[1]
	return rez


def _ip_num(ip):
	try:
		a = [int(x) for x in ip.split(".")]
	except (AttributeError, ValueError):
		return None
	if len(a) != 4 or any(x < 0 or x > 255 for x in a):
		return None
	return (a[0] << 24) | (a[1] << 16) | (a[2] << 8) | a[3]


def prefix(masca):
	"""Lungimea prefixului din "255.255.255.0" sau "24"; None cand nu se intelege."""
	if masca is None:
		return None
	masca = str(masca).strip()
	if masca.isdigit():
		n = int(masca)
		return n if 0 <= n <= 32 else None
	m = _ip_num(masca)
	if m is None:
		return None
	n = bin(m).count("1")
	return n if m == ((0xFFFFFFFF << (32 - n)) & 0xFFFFFFFF if n else 0) else None


def aceeasi_retea(a, b, lungime):
	x, y = _ip_num(a), _ip_num(b)
	if x is None or y is None or lungime is None:
		return False
	m = (0xFFFFFFFF << (32 - lungime)) & 0xFFFFFFFF if lungime else 0
	return (x & m) == (y & m)


def pregateste_nucleul(radacina=""):
	"""SETARI_NUCLEU pe toate placile (si "all", "default" pentru cele care apar mai tarziu, de pilda un stick Wi-Fi):
	numarul valorilor schimbate. Numai /proc, nimic scris pe disc: se pune din nou la fiecare pornire."""
	baza = radacina + CONF_NUCLEU
	try:
		placi = sorted(os.listdir(baza))
	except OSError:
		return 0
	n = 0
	for p in placi:
		if p == "lo":
			continue
		for nume, valoare in SETARI_NUCLEU:
			cale = baza + p + "/" + nume
			try:
				with open(cale, encoding="utf-8") as f:
					if f.read().strip() == valoare:
						continue
				with open(cale, "w", encoding="utf-8") as f:
					f.write(valoare)
				n += 1
			except (IOError, OSError):
				pass
	if n:
		_jurnal("nucleul: %d valori puse (rutele placilor fara legatura sarite, ARP numai pe placa adresei)" % n)
	return n


def _virtuala(nume):
	return not nume or nume.startswith(VIRTUALE)


def _e_wifi(radacina, nume):
	return os.path.exists(radacina + SYS_NET + nume + "/wireless") or os.path.exists(radacina + SYS_NET + nume + "/phy80211")


def cai(radacina="", ordine=None):
	"""Caile, in ordinea de incercare: [{"id", "fel", "placa", "ssid" (octeti, la Wi-Fi), "nume"}]."""
	from Components import WlanTools
	ordine = ordine or ordinea()
	st = stanze(_citeste(radacina + CALE_INTERFACES))
	try:
		placi = sorted(os.listdir(radacina + SYS_NET))
	except OSError:
		placi = []
	cabluri, wifi = [], []
	conf = None
	for p in placi:
		if _virtuala(p) or p not in st:
			continue
		if _e_wifi(radacina, p):
			if not st[p]["wpa"]:
				continue
			if conf is None:
				conf = WlanTools.savedNetworks(_citeste(radacina + CALE_WPA))
			for ssid in conf:
				wifi.append({"id": "wifi:%s:%s" % (p, ssid.hex()), "fel": WIFI, "placa": p, "ssid": ssid,
					"nume": WlanTools.ssidName(ssid)})
		else:
			cabluri.append({"id": "cablu:%s" % p, "fel": CABLU, "placa": p, "ssid": None, "nume": p})
	return cabluri + wifi if ordine == CABLU else wifi + cabluri


def text_cale(c):
	if c is None:
		return ""
	if c["fel"] == WIFI:
		return _("Wi-Fi %s") % c["nume"]
	return _("cablu")


def rute_implicite(radacina=""):
	"""[(placa, poarta, metrica)] din /proc/net/route, in ordinea nucleului (castiga metrica cea mai mica)."""
	rez = []
	for rand in _citeste(radacina + CALE_RUTE, 16384).splitlines()[1:]:
		p = rand.split()
		if len(p) < 8 or p[1] != "00000000" or p[7] != "00000000":
			continue
		try:
			steaguri = int(p[3], 16)
			metrica = int(p[6])
			v = int(p[2], 16)
		except ValueError:
			continue
		if not steaguri & 1:
			continue
		poarta = "%d.%d.%d.%d" % (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF) if steaguri & 2 else ""
		rez.append((p[0], poarta, metrica))
	return rez


def ruta_castigatoare(radacina=""):
	r = rute_implicite(radacina)
	if not r:
		return None
	return min(enumerate(r), key=lambda x: (x[1][2], x[0]))[1]


# ---------------------------------------------------------------- paza (actualizare, inregistrare, canal din retea)

def _ref_din_retea(ref):
	"""O referinta de serviciu cu o adresa de retea care nu e a receptorului insusi (127.x, localhost)."""
	t = (ref or "").lower().replace("%3a", ":")
	if "://" not in t:
		return False
	gazda = t.split("://", 1)[1].split("/", 1)[0].split("@")[-1].split(":")[0]
	return gazda not in ("127.0.0.1", "localhost", "0.0.0.0", "") and not gazda.startswith("127.")


def motiv_ocupat(inapoi=False):
	"""Textul pentru care trecerea se amana acum, sau "": actualizarea, inregistrarea dintr-o sursa din retea si, la
	intoarcere, un canal din retea privit pe televizor (intoarcerea l-ar intrerupe)."""
	try:
		a = sys.modules.get("Components.HdsActualizari")
		if a is not None and (a.actualizari.ocupat() or a.opkg_ocupat()):
			return _("se instalează o actualizare")
	except Exception:
		pass
	try:
		t = sys.modules.get("Components.HdsTransmisie")
		if t is not None and any(_ref_din_retea(r) for r in t.inregistrariPornite()):
			return _("se înregistrează un canal din rețea")
	except Exception:
		pass
	if inapoi:
		try:
			import NavigationInstance
			nav = NavigationInstance.instance
			ref = nav.getCurrentlyPlayingServiceReference() if nav is not None else None
			if ref is not None and _ref_din_retea(ref.toString()):
				return _("pe televizor merge un canal din rețea")
		except Exception:
			pass
	return ""


# ---------------------------------------------------------------- comenzile (pe firul lucrului)

class Sistem(object):
	"""Comenzile si fisierele, pe receptor. Probele de pe PC dau un sistem fals cu aceleasi metode."""

	def __init__(self, radacina=""):
		self.radacina = radacina

	def ceas(self):
		return time.monotonic()

	def dormi(self, s):
		time.sleep(s)

	def cmd(self, argv, termen=TERMEN_COMANDA_S):
		"""(codul, iesirea) unei comenzi date ca lista (fara shell); 127 cand programul lipseste."""
		try:
			r = subprocess.run(list(argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=termen)
			return r.returncode, r.stdout.decode("utf-8", "replace")
		except FileNotFoundError:
			return 127, ""
		except subprocess.TimeoutExpired:
			return 124, ""
		except OSError as e:
			return 126, str(e)

	def fisier(self, cale):
		return _citeste(self.radacina + cale)

	def exista(self, cale):
		return os.path.exists(self.radacina + cale)

	def rute(self):
		return rute_implicite(self.radacina)

	def semnal(self, pid, sig):
		os.kill(pid, sig)

	def proba_dns(self, placa, server, nume, termen):
		"""Intrebarea DNS a lui HdsStareRetea, legata de placa (pleaca numai pe acolo, oricare e ruta implicita)."""
		import socket
		from Components import HdsStareRetea as S
		ident = struct.unpack(">H", os.urandom(2))[0]
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:
			s.setsockopt(socket.SOL_SOCKET, SO_BINDTODEVICE, placa.encode("ascii") + b"\0")
			s.settimeout(termen)
			s.connect((server, 53))
			s.send(S.intrebare_dns(nume, ident))
			sfarsit = time.monotonic() + termen
			while True:
				rest = sfarsit - time.monotonic()
				if rest <= 0:
					return False
				s.settimeout(rest)
				potrivit, adrese = S.adrese_a(s.recv(1500), ident)
				if potrivit:
					return any(S.adresa_publica(a) for a in adrese)
		except (OSError, ValueError, struct.error):
			return False
		finally:
			s.close()


class Lucru(object):
	"""Pasii unei treceri, pe firul lucrului. trece() si inapoi() intorc un dict cu "bun" si ce s-a facut (ca sa se
	poata desface): rutele mutate la rezerva cu metrica lor veche, placa pornita de noi, reteaua Wi-Fi de dinainte."""

	def __init__(self, sistem):
		self.s = sistem

	# ---- citiri
	def adresa(self, placa):
		return self.adresa_si_prefix(placa)[0]

	def adresa_si_prefix(self, placa):
		"""(prima adresa IPv4 a placii, lungimea prefixului) sau ("", None)."""
		cod, iesire = self.s.cmd(("ip", "-4", "-o", "addr", "show", "dev", placa), 10)
		if cod != 0:
			return "", None
		for rand in iesire.splitlines():
			p = rand.split()
			if "inet" in p:
				i = p.index("inet")
				if i + 1 < len(p):
					a = p[i + 1].split("/")
					return a[0], (prefix(a[1]) if len(a) > 1 else 32)
		return "", None

	def legatura(self, placa):
		"""True / False dupa /sys/class/net/<placa>/carrier; None cand placa e oprita (fisierul nu se poate citi)."""
		t = self.s.fisier(SYS_NET + placa + "/carrier").strip()
		return True if t == "1" else (False if t == "0" else None)

	def cablu_bagat(self, placa):
		"""Cablul e bagat? Pe o placa oprita, legatura se afla numai pornind-o (ip link set up) cateva secunde; daca
		nu e cablu, placa se opreste la loc."""
		v = self.legatura(placa)
		if v is not None:
			return v
		self.s.cmd(("ip", "link", "set", placa, "up"), 10)
		v = self.asteapta(lambda: self.legatura(placa), 4.0)
		if not v:
			self.s.cmd(("ip", "link", "set", placa, "down"), 10)
		return bool(v)

	def rute_placa(self, placa):
		return [(p, g, m) for p, g, m in self.s.rute() if p == placa]

	def ruta_buna(self, placa):
		"""Placa are o ruta implicita care nu e la rezerva."""
		return [r for r in self.rute_placa(placa) if r[2] != METRICA_REZERVA]

	def wpa(self, placa, *argumente):
		return self.s.cmd(("wpa_cli", "-p", CTRL_WPA, "-i", placa) + tuple(argumente), 15)

	def ssid_acum(self, placa):
		from Components import WlanTools
		cod, iesire = self.wpa(placa, "status")
		st = WlanTools.parseStatus(iesire) if cod == 0 else {}
		if st.get("wpa_state") == "COMPLETED" and st.get("ssid"):
			return WlanTools.decodeSsid(st["ssid"])
		return None

	def id_retea(self, placa, ssid):
		"""Numarul retelei in supplicant (wpa_cli list_networks) dupa nume, sau None."""
		from Components import WlanTools
		cod, iesire = self.wpa(placa, "list_networks")
		if cod != 0:
			return None
		for rand in iesire.splitlines()[1:]:
			p = rand.split("\t")
			if len(p) >= 2 and p[0].strip().isdigit() and WlanTools.decodeSsid(p[1]) == ssid:
				return p[0].strip()
		return None

	def internet_prin(self, placa, incercari=2):
		from Components import HdsStareRetea as S
		for _k in range(incercari):
			for server, nume in S.REZOLVOARE_PUBLICE:
				if self.s.proba_dns(placa, server, nume, S.TERMEN_DNS_S):
					return True
		return False

	def asteapta(self, conditie, termen, pas=1.0):
		sfarsit = self.s.ceas() + termen
		while True:
			v = conditie()
			if v or self.s.ceas() >= sfarsit:
				return v
			self.s.dormi(pas)

	def se_aude(self, placa, ssid):
		"""Reteaua `ssid` apare in cautarea supplicantului cu un semnal folosibil (cel putin -80 dBm)."""
		from Components import WlanTools
		self.wpa(placa, "scan")
		self.s.dormi(4.0)
		cod, iesire = self.wpa(placa, "scan_results")
		if cod != 0:
			return False
		for rand in iesire.splitlines()[1:]:
			p = rand.split("\t", 4)
			if len(p) == 5 and WlanTools.decodeSsid(p[4]) == ssid:
				try:
					v = int(p[2])
				except ValueError:
					continue
				if v >= -80 or v > 0:
					return True
		return False

	# ---- schimbari
	def muta_ruta(self, placa, poarta, din_metrica, in_metrica):
		if not poarta or din_metrica == in_metrica:
			return
		self.s.cmd(("ip", "route", "replace", "default", "via", poarta, "dev", placa, "metric", str(in_metrica)), 10)
		self.s.cmd(("ip", "route", "del", "default", "via", poarta, "dev", placa, "metric", str(din_metrica)), 10)

	def reinnoieste_dhcp(self, placa, elibereaza=False):
		"""udhcpc al placii (pornit de ifup, /var/run/udhcpc.<placa>.pid): eliberare (USR2) si cerere (USR1)."""
		try:
			pid = int(self.s.fisier("/var/run/udhcpc.%s.pid" % placa).strip())
		except ValueError:
			return False
		try:
			if elibereaza:
				self.s.semnal(pid, SEMNAL_ELIBEREAZA)
				self.s.dormi(1.0)
			self.s.semnal(pid, SEMNAL_CERE)
			return True
		except OSError:
			return False

	def pune_ruta(self, placa, poarta_statica=""):
		"""Ruta implicita a placii, care sa castige: o ruta lasata la rezerva se aduce la 0; altfel o pune DHCP
		(udhcpc reinnoit) sau, la adresa fixa, poarta din interfaces. True daca placa are o ruta care nu e la rezerva."""
		if self.ruta_buna(placa):
			return True
		for p, g, m in self.rute_placa(placa):
			self.muta_ruta(p, g, m, 0)
		if self.ruta_buna(placa):
			return True
		if poarta_statica:
			self.s.cmd(("ip", "route", "replace", "default", "via", poarta_statica, "dev", placa, "metric", "0"), 10)
		else:
			self.reinnoieste_dhcp(placa)
		if self.asteapta(lambda: self.ruta_buna(placa), TERMEN_RUTA_S):
			return True
		# scriptul udhcpc vechi (busybox-udhcpc fara reteta noastra) pune ruta fara "dev": nucleul o duce pe alta placa
		# (cablul scos). Atunci ruta prin placa noua se pune aici, cu poarta din reteaua ei (luata din rutele de acum)
		ip, lungime = self.adresa_si_prefix(placa)
		for _p, g, _m in self.s.rute():
			if g and ip and aceeasi_retea(g, ip, lungime):
				self.s.cmd(("ip", "route", "replace", "default", "via", g, "dev", placa, "metric", "0"), 10)
				return bool(self.ruta_buna(placa))
		return False

	def nume_local(self):
		"""hdsatelit.local cu adresa de acum (scriptul nu schimba nimic cand adresa e aceeasi)."""
		if self.s.exista(NUME_LOCAL):
			self.s.cmd((NUME_LOCAL, "start"), 20)

	def alege_wifi(self, placa, ssid):
		"""Supplicantul trece pe reteaua salvata `ssid` (select_network; apoi toate retelele pornite din nou, ca
		supplicantul sa le poata folosi ca de obicei); True cand s-a asociat."""
		n = self.id_retea(placa, ssid)
		if n is None:
			return False
		self.wpa(placa, "select_network", n)
		bun = self.asteapta(lambda: self.ssid_acum(placa) == ssid, TERMEN_ASOCIERE_S)
		self.wpa(placa, "enable_network", "all")
		return bool(bun)

	def muta_adresa_fixa(self, cablu, placa):
		"""Cablul scos avea adresa scrisa de om: aceeasi adresa si pe placa Wi-Fi (adresa a doua, langa cea primita
		acolo), iar ruta implicita prin Wi-Fi pleaca de la ea. Numai cand adresa e in reteaua Wi-Fi-ului. Intoarce ce
		s-a facut (pentru intoarcere) sau None."""
		st = stanze(self.s.fisier(CALE_INTERFACES)).get(cablu, {})
		fixa = st.get("adresa", "")
		if st.get("metoda") != "static" or _ip_num(fixa) is None:
			return None
		ip_wifi, lungime = self.adresa_si_prefix(placa)
		if not ip_wifi or ip_wifi == fixa or not aceeasi_retea(fixa, ip_wifi, lungime):
			return None
		rute = self.ruta_buna(placa)
		if not rute or not rute[0][1]:
			return None
		_p, poarta, metrica = rute[0]
		cod, iesire = self.s.cmd(("ip", "addr", "add", "%s/%d" % (fixa, lungime), "dev", placa), 10)
		if cod != 0 and "exists" not in iesire:
			_jurnal("adresa fixa pe %s: %s" % (placa, iesire.strip()[:120]))
			return None
		self.s.cmd(("ip", "route", "replace", "default", "via", poarta, "dev", placa, "metric", str(metrica),
			"src", fixa), 10)
		_jurnal("adresa fixa %s pusa si pe %s" % (fixa, placa))
		return {"adresa": fixa, "prefix": lungime, "placa": placa, "poarta": poarta, "metrica": metrica}

	def ia_adresa_fixa(self, f):
		"""Desface muta_adresa_fixa: ruta implicita prin Wi-Fi fara adresa fixa (intai, altfel nucleul o sterge odata
		cu adresa), apoi adresa luata de pe placa Wi-Fi."""
		if not f:
			return
		if self.rute_placa(f["placa"]):
			self.s.cmd(("ip", "route", "replace", "default", "via", f["poarta"], "dev", f["placa"], "metric",
				str(f["metrica"])), 10)
		self.s.cmd(("ip", "addr", "del", "%s/%d" % (f["adresa"], f["prefix"]), "dev", f["placa"]), 10)

	def trece(self, din, spre, poarta_statica=""):
		"""De pe calea `din` (sau None) pe calea `spre`; la esec totul ramane ca inainte.
		{"bun", "pornita_de_noi", "mutate": [(placa, poarta, metrica veche)], "ssid_vechi", "adresa", "adresa_fixa",
		"motiv" (la esec: pasul care n-a mers, pentru jurnal, /retea si mesajul de pe televizor)}."""
		rez = {"bun": False, "pornita_de_noi": False, "mutate": [], "ssid_vechi": None, "adresa": "",
			"adresa_fixa": None, "motiv": ""}
		placa = spre["placa"]
		if din is None or din["placa"] != placa:
			if not self.adresa(placa):
				if spre["fel"] == CABLU and not self.cablu_bagat(placa):
					rez["motiv"] = _("cablul nu e bagat")
					return rez
				cod, iesire = self.s.cmd(("ifup", placa), TERMEN_COMANDA_S)
				rez["pornita_de_noi"] = True
				if cod != 0:
					_jurnal("ifup %s: cod %d %s" % (placa, cod, iesire.strip()[-160:]))
				_ipv6DupaRetea()
				if spre["fel"] == WIFI:
					# supplicantul pornit de ifup se leaga singur de o retea salvata; select_network numai daca nu
					# s-a legat de cea ceruta
					self.asteapta(lambda: self.ssid_acum(placa) is not None, TERMEN_SINGURA_S)
			if spre["fel"] == WIFI and self.ssid_acum(placa) != spre["ssid"]:
				rez["ssid_vechi"] = self.ssid_acum(placa)
				if not self.alege_wifi(placa, spre["ssid"]):
					rez["motiv"] = _("placa Wi-Fi nu s-a legat la rețeaua %s") % spre["nume"]
					return self._esec(din, spre, rez)
				self.reinnoieste_dhcp(placa, elibereaza=True)
			if not self.asteapta(lambda: self.adresa(placa), TERMEN_ADRESA_S):
				rez["motiv"] = _("routerul nu a dat o adresă IP")
				return self._esec(din, spre, rez)
			# rutele caii vechi la rezerva: raman, ca sa poata fi verificata, dar nu mai castiga
			if din is not None:
				for p, g, m in self.ruta_buna(din["placa"]):
					if g:
						self.muta_ruta(p, g, m, METRICA_REZERVA)
						rez["mutate"].append((p, g, m))
			if not self.pune_ruta(placa, poarta_statica):
				rez["motiv"] = _("routerul nu a dat o rută spre internet")
				return self._esec(din, spre, rez)
		else:
			# doua retele Wi-Fi pe aceeasi placa
			rez["ssid_vechi"] = self.ssid_acum(placa)
			if not self.alege_wifi(placa, spre["ssid"]):
				rez["motiv"] = _("placa Wi-Fi nu s-a legat la rețeaua %s") % spre["nume"]
				return self._esec(din, spre, rez)
			self.reinnoieste_dhcp(placa, elibereaza=True)
			if not self.asteapta(lambda: self.adresa(placa) and self.ruta_buna(placa), TERMEN_ADRESA_S):
				rez["motiv"] = _("routerul nu a dat o adresă IP")
				return self._esec(din, spre, rez)
		if not self.internet_prin(placa):
			rez["motiv"] = _("nici pe acolo nu merge internetul")
			return self._esec(din, spre, rez)
		rez["bun"] = True
		rez["adresa"] = self.adresa(placa)
		if spre["fel"] == WIFI and din is not None and din["fel"] == CABLU and self.legatura(din["placa"]) is False:
			rez["adresa_fixa"] = self.muta_adresa_fixa(din["placa"], placa)
			if rez["adresa_fixa"]:
				rez["adresa"] = rez["adresa_fixa"]["adresa"]
		self.nume_local()
		return rez

	def _esec(self, din, spre, rez):
		self.inapoi(din, spre, rez)
		rez["bun"] = False
		return rez

	def inapoi(self, preferata, spre, facut):
		"""Desface trecerea de pe `preferata` pe `spre` (facut = ce a intors trece): rutele inapoi la metrica lor,
		placa pornita de noi oprita, reteaua Wi-Fi de dinainte aleasa din nou."""
		facut = facut or {}
		self.ia_adresa_fixa(facut.get("adresa_fixa"))
		for p, g, m in facut.get("mutate", []):
			self.muta_ruta(p, g, METRICA_REZERVA, m)
		if facut.get("pornita_de_noi") and (preferata is None or preferata["placa"] != spre["placa"]):
			self.s.cmd(("ifdown", spre["placa"]), TERMEN_COMANDA_S)
		elif facut.get("ssid_vechi") and self.ssid_acum(spre["placa"]) != facut["ssid_vechi"]:
			if self.alege_wifi(spre["placa"], facut["ssid_vechi"]):
				self.reinnoieste_dhcp(spre["placa"], elibereaza=True)
		self.nume_local()
		return {"bun": True, "adresa": self.adresa(preferata["placa"]) if preferata is not None else ""}


# ---------------------------------------------------------------- deciziile (pe firul enigma2)

class Comutator(object):
	"""Starea trecerii si hotararile. tic() numai pe firul enigma2; pasii (Lucru) pe firul lor, sau pe loc in probe
	(porneste_fir=False). Toate trecerile pornesc din starea obisnuita (NORMAL): din COMUTAT se intoarce intai pe
	calea preferata, deci ce e de desfacut e mereu o singura trecere."""

	def __init__(self, urmaritor=None, sistem=None, ceas=None, porneste_fir=True, anunta=None, cai_fn=None,
			ocupat=None, pornita_fn=None, interval=None):
		self._urmaritor = urmaritor
		self.sistem = sistem or Sistem()
		self.lucru = Lucru(self.sistem)
		self.ceas = ceas or time.monotonic
		self.porneste_fir = porneste_fir
		self.anunta = anunta
		self.anunta_rau = None      # mesajul unei treceri care n-a mers (text, cale); porneste() il pune
		self.cai_fn = cai_fn or (lambda: cai(self.sistem.radacina))
		self.ocupat = ocupat or motiv_ocupat
		self.pornita_fn = pornita_fn or pornita
		self.interval = interval
		self._zavor = threading.Lock()
		self.mod = NORMAL
		self.preferata = None       # calea parasita (la ea se intoarce)
		self.activa = None          # calea pe care a trecut
		self.facut = None           # ce a facut trecerea (de desfacut la intoarcere)
		self.rele = 0
		self.bune_pref = 0
		self.ultim_gen = None
		self.t_cerere = None
		self.pauza_pana = None
		self.lucreaza = False
		self.rezultat = None
		self.t_proba = None
		self.t_wifi_inapoi = None
		self.amanat = ""
		self.ultimul = ""
		self.t_ultimul = None
		self.adresa = ""
		self.treceri = 0
		self.intoarceri = 0
		self.anuntat_pierderea = False  # mesajul de esec / "nicio retea Wi-Fi salvata": o data la fiecare pierdere

	def urmaritor(self):
		if self._urmaritor is None:
			from Components import HdsStareRetea
			self._urmaritor = HdsStareRetea.urmaritor()
		return self._urmaritor

	def _interval(self):
		if self.interval is not None:
			return self.interval()
		try:
			from Components import HdsStareRetea
			return HdsStareRetea.interval_ales()
		except Exception:
			return 60

	# ---- starea pentru web si televizor
	def stare(self):
		try:
			lista = self.cai_fn()
		except Exception:
			lista = []
		return {"pornita": bool(self.pornita_fn()), "mod": self.mod,
			"cai": [{"id": c["id"], "fel": c["fel"], "placa": c["placa"], "nume": text_cale(c)} for c in lista],
			"activa": text_cale(self.activa), "preferata": text_cale(self.preferata), "adresa": self.adresa,
			"lucreaza": self.lucreaza, "amanat": self.amanat, "ultimul": self.ultimul, "t_ultimul": self.t_ultimul,
			"fara_alternative": len(lista) < 2}

	# ---- pe firul enigma2
	def tic(self, acum=None):
		acum = self.ceas() if acum is None else acum
		self._primeste(acum)
		if self.lucreaza:
			return
		if not self.pornita_fn():
			self.rele = 0
			if self.mod == COMUTAT:
				self._porneste(acum, "inapoi", self._lucru_inapoi)
			return
		try:
			lista = self.cai_fn()
		except Exception as e:
			_jurnal("caile: %r" % (e,))
			lista = []
		self._esantion(acum)
		if self.mod == NORMAL:
			scos = self._cablu_scos(lista)
			if scos:
				# cablul scos e un raspuns sigur: trecerea porneste acum, fara cele 3 verificari
				self.rele = max(self.rele, PRAG_TRECERE)
			if len(lista) >= 2 and self.rele >= PRAG_TRECERE and self._se_poate(acum, False):
				self.rele = 0
				self._porneste(acum, "trece", self._lucru_trece, lista)
			elif len(lista) < 2 and scos and not self.anuntat_pierderea and self._are_wifi():
				self.anuntat_pierderea = True
				self._noteaza(_("Receptorul nu poate trece singur pe Wi-Fi: nu e nicio rețea Wi-Fi salvată și pornită. "
					"Conectează receptorul o dată la Wi-Fi (Rețea și internet), apoi trecerea se face singură."),
					None, rau=True)
			return
		# pe alta cale (COMUTAT)
		if self.rele >= PRAG_TRECERE and self._se_poate(acum, False):
			# si calea de acum a pierdut internetul: inapoi pe preferata, apoi celelalte (fara cea de acum)
			self.rele = 0
			self._porneste(acum, "inapoi_si_trece", self._lucru_inapoi_si_trece, lista)
			return
		self._reafirma(acum)
		if self.lucreaza or self.preferata is None or self.activa is None:
			return
		if self.facut and self.facut.get("adresa_fixa") and self.preferata["fel"] == CABLU and \
				self.lucru.legatura(self.preferata["placa"]) is True:
			# cablul e bagat la loc: adresa fixa ramane numai pe cablu (altfel doua placi raspund la ea pana la intoarcere)
			self._porneste(acum, "ia_adresa", self._lucru_ia_adresa)
			return
		if self.preferata["placa"] != self.activa["placa"]:
			pas = max(PROBA_MINIM_S, float(self._interval()))
			if self.t_proba is None or acum - self.t_proba >= pas:
				self.t_proba = acum
				if self.preferata["fel"] == CABLU and not self.lucru.legatura(self.preferata["placa"]):
					self.bune_pref = 0
					return
				self._porneste(acum, "proba", self._lucru_proba)
		elif self.t_wifi_inapoi is None or acum - self.t_wifi_inapoi >= PAUZA_WIFI_INAPOI_S:
			if self._se_poate(acum, True, pauza=False):
				self.t_wifi_inapoi = acum
				self._porneste(acum, "incearca_inapoi", self._lucru_incearca_inapoi)

	def _cablu_scos(self, lista):
		"""Placa rutei castigatoare e un cablu fara legatura (scos din receptor sau din router)."""
		try:
			r = self.sistem.rute()
		except Exception:
			return False
		if not r:
			return False
		placa = min(enumerate(r), key=lambda x: (x[1][2], x[0]))[1][0]
		return any(c["placa"] == placa and c["fel"] == CABLU for c in lista) and self.lucru.legatura(placa) is False

	def _are_wifi(self):
		try:
			placi = os.listdir(self.sistem.radacina + SYS_NET)
		except OSError:
			return False
		return any(not _virtuala(p) and _e_wifi(self.sistem.radacina, p) for p in placi)

	def _se_poate(self, acum, inapoi, pauza=True):
		if pauza and self.pauza_pana is not None and acum < self.pauza_pana:
			return False
		motiv = self.ocupat(inapoi)
		self.amanat = motiv
		if motiv:
			_jurnal("amanat: %s" % motiv)
		return not motiv

	def _esantion(self, acum):
		u = self.urmaritor()
		try:
			st = u.stare()
			gen = u.gen
			lucreaza = u.lucreaza
		except Exception:
			return
		cod = st.get("cod")
		if cod is None or lucreaza or gen == self.ultim_gen:
			return
		self.ultim_gen = gen
		if cod == "ok":
			self.rele = 0
			self.anuntat_pierderea = False
			return
		self.rele += 1
		if self.rele < PRAG_TRECERE and (self.t_cerere is None or acum - self.t_cerere >= REVERIFICARE_S):
			self.t_cerere = acum
			try:
				u.cere_verificare()
			except Exception:
				pass

	def _reafirma(self, acum):
		"""Cat sta pe alta placa: daca ruta caii parasite castiga din nou (udhcpc a reinnoit-o), se muta iar la rezerva."""
		if self.activa is None or self.preferata is None or self.activa["placa"] == self.preferata["placa"]:
			return
		r = self.sistem.rute()
		if not r:
			return
		castiga = min(enumerate(r), key=lambda x: (x[1][2], x[0]))[1]
		if castiga[0] == self.preferata["placa"] and castiga[2] != METRICA_REZERVA:
			self._porneste(acum, "reafirma", self._lucru_reafirma)

	# ---- lucrul pe fir
	def _porneste(self, acum, fel, functie, *argumente):
		self.lucreaza = True
		pref, activa, facut = self.preferata, self.activa, self.facut

		def merge():
			try:
				rez = functie(pref, activa, facut, *argumente)
			except Exception as e:
				_jurnal("%s: %r" % (fel, e))
				rez = {"bun": False, "eroare": repr(e)}
			with self._zavor:
				self.rezultat = (fel, rez)
		if self.porneste_fir:
			fir = threading.Thread(target=merge)
			fir.daemon = True
			fir.start()
		else:
			merge()
			self._primeste(acum)

	def _poarta_statica(self, c):
		st = stanze(self.sistem.fisier(CALE_INTERFACES)).get(c["placa"], {})
		return st.get("poarta", "") if st.get("metoda") == "static" else ""

	def _calea_de_acum(self, lista):
		"""Calea pe care iese acum receptorul: placa rutei implicite si, la Wi-Fi, reteaua la care e legata."""
		r = self.sistem.rute()
		if not r:
			return None
		placa = min(enumerate(r), key=lambda x: (x[1][2], x[0]))[1][0]
		wifi = [c for c in lista if c["placa"] == placa]
		for c in wifi:
			if c["fel"] == CABLU:
				return c
		if wifi:
			ssid = self.lucru.ssid_acum(placa)
			for c in wifi:
				if c["ssid"] == ssid:
					return c
			return wifi[0]
		return None

	def _incearca(self, din, lista, sari=()):
		motive = []
		for c in lista:
			if (din is not None and c["id"] == din["id"]) or c["id"] in sari:
				continue
			rez = self.lucru.trece(din, c, self._poarta_statica(c))
			if rez.get("bun"):
				rez["din"] = din
				rez["spre_cale"] = c
				return rez
			motive.append((c, rez.get("motiv", "")))
			_jurnal("%s: n-a mers (%s)" % (c["id"], rez.get("motiv", "")))
		return {"bun": False, "din": din, "motive": motive}

	def _lucru_trece(self, pref, activa, facut, lista):
		return self._incearca(self._calea_de_acum(lista), lista)

	def _lucru_inapoi(self, pref, activa, facut):
		return self.lucru.inapoi(pref, activa, facut)

	def _lucru_inapoi_si_trece(self, pref, activa, facut, lista):
		"""Calea de acum (activa) a pierdut si ea internetul: intai preferata (daca merge prin ea, ramane acolo), apoi
		celelalte, fara cea de acum. Fara nicio cale buna ramane pe preferata (starea obisnuita)."""
		r = self.lucru.inapoi(pref, activa, facut)
		if pref is not None and self.lucru.internet_prin(pref["placa"], 1):
			r["inapoi"] = True
			return r
		rez = self._incearca(pref, lista, sari=(activa["id"],) if activa else ())
		rez["inapoi_facut"] = True
		return rez

	def _lucru_ia_adresa(self, pref, activa, facut):
		# fara nume_local aici: adresa fixa raspunde acum pe cablu, unde arata deja numele; ruta implicita e inca prin
		# Wi-Fi, fara adresa fixa, iar scriptul ar fi anuntat adresa primita pe Wi-Fi pana la intoarcere (17.10: .126
		# intre 09:44:48 si 09:46:04). Intoarcerea (inapoi) il cheama cu ruta prin cablu.
		self.lucru.ia_adresa_fixa(facut.get("adresa_fixa"))
		facut["adresa_fixa"] = None
		return {"bun": True}

	def _lucru_proba(self, pref, activa, facut):
		return {"bun": self.lucru.internet_prin(pref["placa"], 1)}

	def _lucru_reafirma(self, pref, activa, facut):
		for p, g, m in self.lucru.ruta_buna(pref["placa"]):
			if g:
				self.lucru.muta_ruta(p, g, m, METRICA_REZERVA)
				if facut is not None and (p, g, m) not in facut.get("mutate", []):
					facut.setdefault("mutate", []).append((p, g, m))
		return {"bun": True}

	def _lucru_incearca_inapoi(self, pref, activa, facut):
		if not self.lucru.se_aude(pref["placa"], pref["ssid"]):
			return {"bun": False, "neauzita": True}
		return self.lucru.trece(activa, pref)

	# ---- rezultatele (pe firul enigma2)
	def _primeste(self, acum):
		with self._zavor:
			r = self.rezultat
			self.rezultat = None
		if r is None:
			return
		self.lucreaza = False
		fel, rez = r
		if fel in ("trece", "inapoi_si_trece"):
			pref_veche = self.preferata
			if rez.get("inapoi"):
				self._normal(acum, rez, pref_veche)
			elif rez.get("bun"):
				self.mod = COMUTAT
				self.preferata = rez.get("din")
				self.activa = rez["spre_cale"]
				self.facut = rez
				self.adresa = rez.get("adresa", "")
				self.bune_pref = 0
				self.t_proba = acum
				self.t_wifi_inapoi = acum
				self.pauza_pana = None
				self.treceri += 1
				self._noteaza(_("Internetul nu mergea prin %s. Receptorul a trecut pe %s.") %
					(text_cale(rez.get("din")) or _("rețeaua de până acum"), text_cale(self.activa)), self.activa)
			else:
				if rez.get("inapoi_facut"):
					self.mod, self.preferata, self.activa, self.facut = NORMAL, None, None, None
				self.pauza_pana = acum + PAUZA_DUPA_ESEC_S
				motive = [m for m in rez.get("motive", []) if m[1]]
				if motive:
					text = _("Receptorul nu a putut trece pe %s: %s. Încearcă din nou peste 10 minute.") % (
						text_cale(motive[0][0]), motive[0][1])
				else:
					text = _("Internetul nu merge și nicio altă rețea nu are internet acum. Receptorul încearcă din nou peste 10 minute.")
				_jurnal("nicio cale buna; din nou peste %d s" % PAUZA_DUPA_ESEC_S)
				if not self.anuntat_pierderea:
					self.anuntat_pierderea = True
					self._noteaza(text, None, rau=True)
				else:
					self.ultimul = text
					self.t_ultimul = time.time()
		elif fel == "proba":
			self.bune_pref = self.bune_pref + 1 if rez.get("bun") else 0
			if self.bune_pref >= PRAG_INAPOI and self._se_poate(acum, True, pauza=False):
				self._porneste(acum, "inapoi", self._lucru_inapoi)
		elif fel == "inapoi":
			self._normal(acum, rez, self.preferata)
		elif fel == "incearca_inapoi":
			if rez.get("bun"):
				self._normal(acum, rez, self.preferata)

	def _normal(self, acum, rez, pref):
		self.mod, self.preferata, self.activa, self.facut = NORMAL, None, None, None
		self.bune_pref = 0
		self.rele = 0
		self.adresa = rez.get("adresa", "")
		self.intoarceri += 1
		if pref is not None:
			self._noteaza(_("Receptorul s-a întors pe %s: internetul merge din nou acolo.") % text_cale(pref), pref)

	def _noteaza(self, text, cale, rau=False):
		linii = [text]
		if self.adresa and not rau:
			linii.append(_("Adresa receptorului: %s (sau hdsatelit.local).") % self.adresa)
		self.ultimul = " ".join(linii)
		self.t_ultimul = time.time()
		_jurnal(self.ultimul)
		f = self.anunta_rau if rau else self.anunta
		if f is not None:
			try:
				f("\n".join(linii), cale)
			except Exception as e:
				_jurnal("mesajul: %r" % (e,))


_unic = [None]
_ceas = [None]


def comutator():
	if _unic[0] is None:
		_unic[0] = Comutator()
	return _unic[0]


def stare():
	return comutator().stare()


def curata_wpa_la_pornire(cale=CALE_WPA):
	"""Blocul "orice retea deschisa" din fisierul vechi al pachetului wpa-supplicant (WlanTools.isWildcardBlock) se
	scoate o data, la pornire: altfel supplicantul pornit de ifup s-ar putea lega de reteaua deschisa a unui vecin."""
	try:
		from Components import WlanTools
		if not os.path.exists(cale):
			return 0
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			text = f.read()
		curat, scoase = WlanTools.cleanConf(text)
		if scoase and WlanTools.writeConfAtomic(cale, curat):
			_jurnal("%d bloc(uri) fara nume de retea scoase din %s" % (scoase, cale))
			# supplicantul pornit deja de ifup le tine inca in memorie: il pune sa citeasca fisierul din nou (pe un fir,
			# pornirea nu asteapta)
			try:
				placi = [p for p in os.listdir(CTRL_WPA) if not p.startswith(".")]
			except OSError:
				placi = []
			if placi:
				def citeste_din_nou():
					s = Sistem()
					for p in placi:
						s.cmd(("wpa_cli", "-p", CTRL_WPA, "-i", p, "reconfigure"), 10)
				fir = threading.Thread(target=citeste_din_nou)
				fir.daemon = True
				fir.start()
		return scoase
	except Exception as e:
		_jurnal("curatarea fisierului Wi-Fi: %r" % (e,))
		return 0


def porneste(session=None):
	"""Din mytest.py, dupa HdsStareRetea.porneste(session): ceasul de TIC_MS pe firul enigma2 si mesajul pe ecran."""
	pregateste_nucleul()
	curata_wpa_la_pornire()
	c = comutator()
	if session is not None:
		def anunta(text, cale, bun=True):
			try:
				from Screens import Standby
				if Standby.inStandby is not None:
					return
			except Exception:
				pass
			from Screens import HdsAnuntRetea
			from Components import HdsStareRetea
			fel = HdsStareRetea.WIFI if cale is not None and cale["fel"] == WIFI else HdsStareRetea.CABLU
			HdsAnuntRetea.arata(session, text, HdsStareRetea.cheie_pictograma({"cod": HdsStareRetea.OK if bun else
				HdsStareRetea.FARA_INTERNET, "fel": fel, "treapta": 4}))
		c.anunta = anunta
		c.anunta_rau = lambda text, cale: anunta(text, cale, False)
	if _ceas[0] is None:
		from enigma import eTimer
		t = eTimer()
		t.callback.append(c.tic)
		_ceas[0] = t
	_ceas[0].start(TIC_MS, False)
