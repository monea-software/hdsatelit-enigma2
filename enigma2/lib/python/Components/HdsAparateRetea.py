# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAparateRetea.py: utilitarul "Ce aparate sunt in retea" (din 0.4.4), aceeasi logica pe televizor
# (Screens/HdsUnelteRetea.py, HdsAparateReteaScreen) si in interfata web (HdsWebControl/unelte_retea_web.py,
# /aparate-retea).
#
# NUMAI IN RETEAUA LOCALA, NIMIC IN AFARA EI. Cum se afla aparatele:
#   1. reteaua: placa prin care iese receptorul (ruta implicita), adresa lui si masca retelei (/proc/net/route,
#      /proc/net/fib_trie). O retea mai mare de /22 nu se cauta toata: numai cele 254 de adrese din /24-ul receptorului.
#   2. o cautare usoara: catre fiecare adresa din retea pleaca UN singur pachet UDP mic, intrebarea de nume NetBIOS
#      (portul 137, "cum te cheama?"). Ca sa-l trimita, nucleul afla adresa fizica a fiecarui aparat (ARP), deci tabela
#      de vecini (/proc/net/arp) se umple cu toate aparatele pornite; cele cu Windows sau Samba raspund si cu numele.
#      FARA cautari de porturi: nicio conexiune TCP, niciun alt port. Pachetele pleaca cu o pauza mica intre ele.
#   3. numele, numai de la aparatele din retea: raspunsurile NetBIOS de mai sus; o intrebare mDNS (adresa de grup
#      224.0.0.251, portul 5353, raspunsul vine numai de la aparatele din aceeasi retea: telefoane, televizoare,
#      imprimante); numele inverse (PTR) intrebate numai routerul sau serverele DNS din /etc/resolv.conf care au adresa
#      LOCALA (routerul stie numele date prin DHCP). Un server DNS de pe internet (1.1.1.1 de pilda) NU se intreaba:
#      ar afla adresele din casa.
#   4. producatorul: dupa primele 6, 7 sau 9 cifre ale adresei fizice, din lista din imagine
#      (/usr/share/enigma2/hds-producatori-mac.txt.gz, facuta din lista Wireshark, GPL-2.0-or-later; vezi Licente).
#      O adresa "administrata local" (al doilea bit al primului octet) e aleasa la intamplare de aparat: telefoanele si
#      tabletele noi o folosesc ca adresa privata in fiecare retea Wi-Fi.
# Orice pachet trece prin Cautare._trimite, care il opreste daca destinatia nu e in reteaua receptorului (sau grupul
# mDNS): proba de pe PC numara fiecare destinatie.
#
# FIRUL: totul merge pe un fir separat (socluri cu termen, cateva fisiere mici); ecranul si pagina citesc rezultatul din
# memorie (rezultat()). O cautare tine cateva secunde; doua nu merg deodata.
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import gzip
import os
import socket
import struct
import threading
import time

CALE_RUTE = "/proc/net/route"
CALE_ARP = "/proc/net/arp"
CALE_FIB = "/proc/net/fib_trie"
CALE_RESOLV = "/etc/resolv.conf"
SYS_NET = "/sys/class/net/"
CALE_PRODUCATORI = "/usr/share/enigma2/hds-producatori-mac.txt.gz"
MDNS = ("224.0.0.251", 5353)
PORT_NETBIOS = 137
PORT_DNS = 53
PREFIX_MINIM = 22          # o retea mai mare: numai /24-ul receptorului
PACHETE_PE_RAND = 16       # cate pachete pleaca inainte de o pauza
PAUZA_S = 0.02
ASTEPTARE_ARP_S = 2.5      # dupa ultimul pachet: raspunsurile ARP si NetBIOS
ASTEPTARE_NUME_S = 1.5     # mDNS si DNS invers
INTREBARI_MDNS = 24        # cate intrebari intr-un pachet mDNS
PAUZA_INTRE_CAUTARI_S = 10.0


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsAparateRetea] %s" % text)


def _citeste(cale, maxim=262144):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (IOError, OSError):
		return ""


# ---------------------------------------------------------------- adrese

def ip_num(ip):
	try:
		p = [int(x) for x in ip.split(".")]
	except (ValueError, AttributeError):
		return None
	if len(p) != 4 or not all(0 <= x <= 255 for x in p):
		return None
	return (p[0] << 24) | (p[1] << 16) | (p[2] << 8) | p[3]


def ip_text(n):
	return "%d.%d.%d.%d" % ((n >> 24) & 255, (n >> 16) & 255, (n >> 8) & 255, n & 255)


def _hex_ip(h):
	"""Adresa din /proc/net/route (8 cifre hexa, ordinea nucleului: 0100000A = 10.0.0.1) ca numar."""
	try:
		v = int(h, 16)
	except ValueError:
		return None
	return ((v & 0xFF) << 24) | (((v >> 8) & 0xFF) << 16) | (((v >> 16) & 0xFF) << 8) | ((v >> 24) & 0xFF)


def prefix_din_masca(m):
	if m is None:
		return None
	inv = (~m) & 0xFFFFFFFF
	if inv & (inv + 1):
		return None
	return 32 - bin(inv).count("1")


def in_retea(ip, retea, prefix):
	n = ip_num(ip) if isinstance(ip, str) else ip
	if n is None or prefix is None:
		return False
	masca = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF if prefix else 0
	return (n & masca) == (retea & masca)


def adresa_locala(ip):
	"""Adresa dintr-o retea privata (RFC 1918), legatura locala sau CGNAT (nu de pe internet)."""
	n = ip_num(ip)
	if n is None:
		return False
	a, b = n >> 24, (n >> 16) & 255
	return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168) or (a == 169 and b == 254) or \
		(a == 100 and 64 <= b <= 127)


def mac_curat(mac):
	m = (mac or "").strip().lower().replace("-", ":")
	p = m.split(":")
	if len(p) != 6 or not all(len(x) == 2 and all(c in "0123456789abcdef" for c in x) for x in p):
		return ""
	if m in ("00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff"):
		return ""
	return m


def mac_aleatoare(mac):
	"""Adresa "administrata local": aleasa de aparat (adresa privata a telefoanelor), nu data de fabricant."""
	m = mac_curat(mac)
	return bool(m) and bool(int(m[:2], 16) & 0x02)


# ---------------------------------------------------------------- reteaua receptorului (pasiv, din fisierele nucleului)

def _adrese_locale(radacina=""):
	text = _citeste(radacina + CALE_FIB)
	ultima = None
	rez = []
	for rand in text.splitlines():
		t = rand.strip()
		if t.startswith("|--") or t.startswith("+--"):
			rest = t[3:].strip()
			ultima = rest.split("/")[0].split()[0] if rest else None
		elif "/32 host LOCAL" in t and ultima and not ultima.startswith("127.") and ultima not in rez:
			rez.append(ultima)
	return rez


def reteaua(radacina=""):
	"""{"placa", "ip", "prefix", "retea" (numar), "poarta", "mac"} pentru placa rutei implicite, sau None."""
	placa = ""
	poarta = None
	retele = []
	for rand in _citeste(radacina + CALE_RUTE, 16384).splitlines()[1:]:
		p = rand.split()
		if len(p) < 8:
			continue
		try:
			steaguri = int(p[3], 16)
		except ValueError:
			continue
		if not steaguri & 1:
			continue
		if p[1] == "00000000" and p[7] == "00000000":
			if not placa:
				placa = p[0]
				poarta = _hex_ip(p[2]) if steaguri & 2 else None
		elif p[1] != "00000000":
			retele.append((p[0], _hex_ip(p[1]), _hex_ip(p[7])))
	if not placa or "/" in placa or placa.startswith("."):
		return None
	locale = [ip_num(a) for a in _adrese_locale(radacina)]
	for nume, retea, masca in retele:
		if nume != placa or retea is None or masca is None:
			continue
		prefix = prefix_din_masca(masca)
		if prefix is None or prefix < 8:
			continue
		for a in locale:
			if a is not None and (a & masca) == retea:
				mac = mac_curat(_citeste(radacina + SYS_NET + placa + "/address", 64))
				return {"placa": placa, "ip": ip_text(a), "prefix": prefix, "retea": retea,
					"poarta": ip_text(poarta) if poarta else "", "mac": mac}
	return None


def adrese_de_intrebat(r):
	"""(adresele de intrebat, prefixul cautat): toate gazdele retelei in afara de receptor; o retea mai mare de
	/PREFIX_MINIM se cauta numai in /24-ul receptorului."""
	prefix = r["prefix"]
	ip = ip_num(r["ip"])
	if prefix < PREFIX_MINIM:
		prefix = 24
	if prefix >= 31:
		return [], prefix
	masca = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
	baza = ip & masca
	ultima = baza | (~masca & 0xFFFFFFFF)
	return [ip_text(n) for n in range(baza + 1, ultima) if n != ip], prefix


def tabela_arp(placa=None, radacina=""):
	"""{ip: mac} din /proc/net/arp: numai intrarile complete (steagul 0x2), cu adresa fizica, pe placa data."""
	rez = {}
	for rand in _citeste(radacina + CALE_ARP, 131072).splitlines()[1:]:
		p = rand.split()
		if len(p) < 6:
			continue
		try:
			steaguri = int(p[2], 16)
		except ValueError:
			continue
		mac = mac_curat(p[3])
		if not steaguri & 0x2 or not mac:
			continue
		if placa and p[5] != placa:
			continue
		if ip_num(p[0]) is not None:
			rez[p[0]] = mac
	return rez


def servere_dns_locale(r, radacina=""):
	"""Serverele de unde se pot cere numele inverse fara sa iasa nimic din casa: routerul si serverele DNS cu adresa
	locala din /etc/resolv.conf, numai din reteaua receptorului."""
	rez = []
	if r.get("poarta") and in_retea(r["poarta"], r["retea"], r["prefix"]):
		rez.append(r["poarta"])
	for rand in _citeste(radacina + CALE_RESOLV, 8192).splitlines():
		p = rand.split()
		if len(p) >= 2 and p[0] == "nameserver" and adresa_locala(p[1]) and in_retea(p[1], r["retea"], r["prefix"]) \
				and p[1] not in rez and p[1] != r["ip"]:
			rez.append(p[1])
	return rez


# ---------------------------------------------------------------- pachetele (NetBIOS, DNS, mDNS)

def _nume_netbios_codat(nume=b"*"):
	nume = (nume + b"\0" * 16)[:16]
	return bytes(bytearray([0x20]) + bytearray(b"".join(bytes(bytearray([0x41 + (c >> 4), 0x41 + (c & 0xF)]))
		for c in bytearray(nume))) + bytearray([0]))


def intrebare_netbios(ident):
	"""Intrebarea NBSTAT (RFC 1002, 4.2.17): "ce nume ai?", numele "*"."""
	return struct.pack(">HHHHHH", ident, 0x0000, 1, 0, 0, 0) + _nume_netbios_codat() + struct.pack(">HH", 0x21, 1)


def raspuns_netbios(date):
	"""Numele aparatului (sau "") din raspunsul NBSTAT: primul nume unic cu sufixul 0x00 (al calculatorului)."""
	try:
		if len(date) < 12:
			return ""
		_id, steaguri, _qd, an = struct.unpack(">HHHH", date[:8])
		if not steaguri & 0x8000 or an < 1:
			return ""
		i = 12
		if bytearray(date[i:i + 1])[0] == 0x20:
			i += 34
		else:
			return ""
		tip, _cls, _ttl, lung = struct.unpack(">HHIH", date[i:i + 10])
		i += 10
		if tip != 0x21:
			return ""
		n = bytearray(date[i:i + 1])[0]
		i += 1
		for k in range(n):
			bucata = date[i + 18 * k:i + 18 * k + 18]
			if len(bucata) < 18:
				break
			nume = bucata[:15].decode("ascii", "replace").strip()
			sufix = bytearray(bucata[15:16])[0]
			fl = struct.unpack(">H", bucata[16:18])[0]
			if sufix == 0x00 and not fl & 0x8000 and nume and "�" not in nume:
				return nume
	except (struct.error, IndexError, ValueError):
		return ""
	return ""


def _nume_dns(nume):
	return b"".join(struct.pack("B", len(e)) + e.encode("ascii") for e in nume.strip(".").split(".") if e) + b"\x00"


def arpa(ip):
	return ".".join(reversed(ip.split("."))) + ".in-addr.arpa"


def intrebare_ptr(ident, ips, unicast=False):
	"""O intrebare DNS (sau mDNS) de tip PTR pentru fiecare adresa (numele invers). In mDNS bitul "raspunde-mi direct"
	(QU) cere raspunsul la portul de unde a plecat intrebarea."""
	clasa = 0x8001 if unicast else 1
	corp = b"".join(_nume_dns(arpa(ip)) + struct.pack(">HH", 12, clasa) for ip in ips)
	steaguri = 0x0000 if unicast else 0x0100
	return struct.pack(">HHHHHH", ident, steaguri, len(ips), 0, 0, 0) + corp


def _citeste_nume(date, i, adancime=0):
	"""(numele, pozitia de dupa el) dintr-un mesaj DNS, cu trimiterile (comprimarea) urmate."""
	parti = []
	sfarsit = None
	for _pas in range(64):
		if i >= len(date):
			raise ValueError("nume taiat")
		n = bytearray(date[i:i + 1])[0]
		if n == 0:
			i += 1
			break
		if n & 0xC0 == 0xC0:
			if adancime > 8 or i + 1 >= len(date):
				raise ValueError("trimiteri prea multe")
			tinta = ((n & 0x3F) << 8) | bytearray(date[i + 1:i + 2])[0]
			if sfarsit is None:
				sfarsit = i + 2
			rest, _j = _citeste_nume(date, tinta, adancime + 1)
			if rest:
				parti.append(rest)
			i = sfarsit
			return ".".join(parti), sfarsit
		parti.append(date[i + 1:i + 1 + n].decode("utf-8", "replace"))
		i += 1 + n
	return ".".join(parti), (sfarsit if sfarsit is not None else i)


def raspuns_ptr(date):
	"""{ip: nume} din raspunsurile PTR ale unui mesaj DNS / mDNS (si din sectiunile in plus, unde mDNS le pune uneori)."""
	rez = {}
	try:
		if len(date) < 12:
			return rez
		_id, steaguri, qd, an, ns, ar = struct.unpack(">HHHHHH", date[:12])
		if not steaguri & 0x8000 or steaguri & 0x000F:
			return rez
		i = 12
		for _k in range(qd):
			_n, i = _citeste_nume(date, i)
			i += 4
		for _k in range(an + ns + ar):
			nume, i = _citeste_nume(date, i)
			tip, _cls, _ttl, lung = struct.unpack(">HHIH", date[i:i + 10])
			i += 10
			if tip == 12 and nume.lower().endswith(".in-addr.arpa"):
				tinta, _j = _citeste_nume(date, i)
				parti = nume.lower()[:-len(".in-addr.arpa")].split(".")
				if len(parti) == 4 and tinta:
					rez[".".join(reversed(parti))] = tinta
			i += lung
	except (struct.error, ValueError, IndexError):
		pass
	return rez


def nume_scurt(nume):
	"""Numele de aratat: fara domeniul retelei de acasa (".local", ".lan", ".home", ".fritz.box"...)."""
	n = (nume or "").strip().rstrip(".")
	if not n:
		return ""
	return n.split(".")[0] if "." in n else n


# ---------------------------------------------------------------- producatorii

def producatori(macs, cale=CALE_PRODUCATORI):
	"""{mac: producator} pentru adresele date, dintr-o singura trecere prin lista (despachetata pe rand, fara sa stea
	toata in memorie). Potrivirea cea mai lunga castiga (9, apoi 7, apoi 6 cifre)."""
	dorite = {}
	for m in macs:
		c = mac_curat(m)
		if not c:
			continue
		h = c.replace(":", "").upper()
		for lung in (9, 7, 6):
			dorite.setdefault(h[:lung], []).append(c)
	gasite = {}
	if not dorite:
		return gasite
	try:
		with gzip.open(cale, "rt", encoding="utf-8", errors="replace") as f:
			for rand in f:
				if rand.startswith("#"):
					continue
				p, _sep, nume = rand.rstrip("\n").partition("\t")
				if p in dorite:
					for c in dorite[p]:
						vechi = gasite.get(c)
						if vechi is None or len(p) > vechi[0]:
							gasite[c] = (len(p), nume)
	except (IOError, OSError, EOFError, ValueError) as e:
		_jurnal("lista producatorilor: %r" % (e,))
	return dict((c, n) for c, (_l, n) in gasite.items())


def text_producator(mac, gasit):
	if gasit:
		return gasit
	if mac_aleatoare(mac):
		return _("Adresă aleatoare (telefon sau tabletă cu adresă privată)")
	return _("necunoscut")


# ---------------------------------------------------------------- cautarea (pe firul ei)

class Cautare(object):
	"""Cautarea aparatelor. Pentru probe: `radacina` (fisierele nucleului false), `fabrica_soclu` (socket.socket fals),
	`ceas`, `dormi`, `cale_producatori`, `nume_gazda`."""

	def __init__(self, radacina="", fabrica_soclu=None, ceas=None, dormi=None, cale_producatori=CALE_PRODUCATORI,
			nume_gazda=None):
		self.radacina = radacina
		self.fabrica_soclu = fabrica_soclu or socket.socket
		self.ceas = ceas or time.monotonic
		self.dormi = dormi or time.sleep
		self.cale_producatori = cale_producatori
		self.nume_gazda = nume_gazda or socket.gethostname
		self._zavor = threading.Lock()
		self.r = None
		self.trimise = []          # destinatiile (adresa, port) ale fiecarui pachet trimis
		self.oprite = []           # destinatiile oprite de paza (n-ar trebui sa fie niciuna)
		self.st = {"stare": "nimic", "aparate": [], "retea": "", "mesaj": "", "cand": None, "faza": ""}

	# ---- starea (citita de ecran si de pagina)
	def rezultat(self):
		with self._zavor:
			st = dict(self.st)
			st["aparate"] = [dict(a) for a in self.st["aparate"]]
		return st

	def _pune(self, **k):
		with self._zavor:
			self.st.update(k)

	def lucreaza(self):
		return self.rezultat()["stare"] == "lucreaza"

	# ---- paza: nimic in afara retelei
	def _permis(self, ip):
		if ip == MDNS[0]:
			return True
		r = self.r
		return r is not None and in_retea(ip, r["retea"], r["prefix"]) and ip != r["ip"]

	def _trimite(self, soclu, date, dest):
		if not self._permis(dest[0]):
			self.oprite.append(dest)
			_jurnal("oprit: o destinatie in afara retelei locale")
			return False
		for incercare in (0, 1):
			try:
				soclu.sendto(date, dest)
				self.trimise.append(dest)
				return True
			except (OSError, socket.error):
				# coada nucleului pentru adresele inca neaflate (ARP) e plina: o pauza mica si inca o data
				if incercare == 0:
					self.dormi(PAUZA_S * 5)
		return False

	# ---- pasii
	def porneste(self, pe_loc=False):
		"""Porneste cautarea (pe un fir; pe_loc=True in probe). False daca una merge deja."""
		with self._zavor:
			if self.st["stare"] == "lucreaza":
				return False
			self.st = {"stare": "lucreaza", "aparate": [], "retea": "", "mesaj": "", "cand": None,
				"faza": _("Se caută aparatele din rețea...")}
		if pe_loc:
			self._lucreaza()
		else:
			fir = threading.Thread(target=self._lucreaza)
			fir.daemon = True
			fir.start()
		return True

	def _lucreaza(self):
		try:
			self._cauta()
		except Exception as e:
			_jurnal("cautarea: %r" % (e,))
			self._pune(stare="eroare", mesaj=_("Căutarea n-a reușit: %s") % e, faza="")

	def _cauta(self):
		r = self.r = reteaua(self.radacina)
		if r is None:
			self._pune(stare="eroare", mesaj=_("Receptorul nu e conectat la nicio rețea."), faza="")
			return
		adrese, prefix = adrese_de_intrebat(r)
		retea_text = "%s/%d" % (ip_text(r["retea"] & ((0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF)), prefix)
		nota = ""
		if prefix != r["prefix"]:
			nota = _("Rețeaua e mare (/%d): se caută numai în cele 254 de adrese din jurul receptorului.") % r["prefix"]
		self._pune(retea=retea_text, mesaj=nota)
		nume_netbios = self._netbios(adrese)
		vecini = tabela_arp(r["placa"], self.radacina)
		vecini = dict((ip, mac) for ip, mac in vecini.items() if in_retea(ip, r["retea"], r["prefix"]) and ip != r["ip"])
		self._pune(faza=_("Se află numele aparatelor..."))
		ips = sorted(vecini, key=ip_num)
		nume_mdns = self._mdns(ips)
		nume_dns = self._dns_invers(ips)
		prod = producatori(list(vecini.values()) + ([r["mac"]] if r["mac"] else []), self.cale_producatori)
		aparate = []
		for ip in ips:
			mac = vecini[ip]
			nume, sursa = "", ""
			for n, s in ((nume_mdns.get(ip), "mdns"), (nume_netbios.get(ip), "netbios"), (nume_dns.get(ip), "dns")):
				if n:
					nume, sursa = nume_scurt(n), s
					break
			aparate.append({"ip": ip, "mac": mac, "nume": nume, "sursa_nume": sursa,
				"producator": text_producator(mac, prod.get(mac)), "aleatoare": mac_aleatoare(mac),
				"eticheta": "router" if ip == r["poarta"] else ""})
		try:
			gazda = self.nume_gazda() or ""
		except Exception:
			gazda = ""
		aparate.append({"ip": r["ip"], "mac": r["mac"], "nume": gazda, "sursa_nume": "receptor",
			"producator": text_producator(r["mac"], prod.get(r["mac"])), "aleatoare": False, "eticheta": "receptor"})
		aparate.sort(key=lambda a: ip_num(a["ip"]))
		self._pune(stare="gata", aparate=aparate, cand=time.time(), faza="")

	def _soclu_udp(self):
		s = self.fabrica_soclu(socket.AF_INET, socket.SOCK_DGRAM)
		s.settimeout(0.2)
		return s

	def _asculta(self, s, termen, prelucreaza):
		sfarsit = self.ceas() + termen
		while True:
			rest = sfarsit - self.ceas()
			if rest <= 0:
				return
			try:
				s.settimeout(min(0.2, rest))
				date, dela = s.recvfrom(4096)
			except socket.timeout:
				continue
			except (OSError, socket.error):
				# o eroare a soclului (un ICMP intors, de pilda): se asteapta mai departe, fara sa se roteasca in gol
				self.dormi(0.05)
				continue
			if dela and self._permis(dela[0]):
				prelucreaza(date, dela[0])

	def _netbios(self, adrese):
		"""Cate un pachet NBSTAT spre fiecare adresa (umple tabela ARP), apoi raspunsurile: {ip: nume}."""
		nume = {}
		s = self._soclu_udp()
		try:
			ident = struct.unpack(">H", os.urandom(2))[0]
			pachet = intrebare_netbios(ident)
			for k, ip in enumerate(adrese):
				self._trimite(s, pachet, (ip, PORT_NETBIOS))
				if (k + 1) % PACHETE_PE_RAND == 0:
					self.dormi(PAUZA_S)
					self._culege_netbios(s, nume)

			def p(date, dela):
				n = raspuns_netbios(date)
				if n:
					nume[dela] = n
			self._asculta(s, ASTEPTARE_ARP_S, p)
		finally:
			s.close()
		return nume

	def _culege_netbios(self, s, nume):
		"""Raspunsurile venite deja (fara asteptare), ca sa nu se piarda cand coada soclului se umple."""
		try:
			s.settimeout(0.0)
			while True:
				date, dela = s.recvfrom(4096)
				if dela and self._permis(dela[0]):
					n = raspuns_netbios(date)
					if n:
						nume[dela[0]] = n
		except (OSError, socket.error, socket.timeout):
			pass
		finally:
			try:
				s.settimeout(0.2)
			except (OSError, socket.error):
				pass

	def _mdns(self, ips):
		"""Numele inverse cerute prin mDNS (o intrebare pentru mai multe adrese); raspunde fiecare aparat de el insusi."""
		nume = {}
		if not ips:
			return nume
		s = self._soclu_udp()
		try:
			try:
				s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
				s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.r["ip"]))
			except (OSError, socket.error, AttributeError):
				pass
			for k in range(0, len(ips), INTREBARI_MDNS):
				self._trimite(s, intrebare_ptr(0, ips[k:k + INTREBARI_MDNS], unicast=True), MDNS)

			def p(date, dela):
				for ip, n in raspuns_ptr(date).items():
					if ip in ips:
						nume.setdefault(ip, n)
			self._asculta(s, ASTEPTARE_NUME_S, p)
		finally:
			s.close()
		return nume

	def _dns_invers(self, ips):
		"""Numele inverse cerute routerului (sau serverelor DNS locale): routerul le stie din DHCP."""
		nume = {}
		servere = servere_dns_locale(self.r, self.radacina)
		if not servere or not ips:
			return nume
		s = self._soclu_udp()
		try:
			baza = struct.unpack(">H", os.urandom(2))[0]
			for k, ip in enumerate(ips):
				self._trimite(s, intrebare_ptr((baza + k) & 0xFFFF, [ip]), (servere[0], PORT_DNS))
				if (k + 1) % PACHETE_PE_RAND == 0:
					self.dormi(PAUZA_S)

			def p(date, dela):
				if dela not in servere:
					return
				for ip, n in raspuns_ptr(date).items():
					if ip in ips:
						nume.setdefault(ip, n)
			self._asculta(s, ASTEPTARE_NUME_S, p)
		finally:
			s.close()
		return nume


_unic = [None]
_ultima_pornire = [None]


def cautare():
	if _unic[0] is None:
		_unic[0] = Cautare()
	return _unic[0]


def porneste():
	"""Ecranul si pagina: porneste o cautare noua, daca nu merge una si daca ultima a pornit de mai mult de
	PAUZA_INTRE_CAUTARI_S secunde. (True, "") sau (False, motivul)."""
	c = cautare()
	if c.lucreaza():
		return False, _("O căutare e deja în curs.")
	acum = time.monotonic()
	if _ultima_pornire[0] is not None and 0 <= acum - _ultima_pornire[0] < PAUZA_INTRE_CAUTARI_S:
		return False, _("Așteaptă câteva secunde înainte de o căutare nouă.")
	_ultima_pornire[0] = acum
	return c.porneste(), ""


def rezultat():
	return cautare().rezultat()


# ---------------------------------------------------------------- pagina web a unui aparat (OK in lista de pe televizor)

PORTURI_WEB = ((80, "http"), (443, "https"))
TERMEN_WEB_S = 2.0


def _conecteaza(ip, port, termen):
	try:
		s = socket.create_connection((ip, port), termen)
	except (OSError, socket.error, ValueError):
		return False
	try:
		s.close()
	except (OSError, socket.error):
		pass
	return True


def adresa_web(ip, termen=TERMEN_WEB_S, conecteaza=None):
	"""Adresa paginii web a unui aparat din lista: "http://ip/" cand raspunde portul 80, "https://ip/" cand raspunde
	numai 443, "" cand niciunul. Numai adresele din retelele locale (adresa_locala): nimic spre internet. Se cheama pe un
	fir (pana la doua conectari TCP cu termen)."""
	if not adresa_locala(ip):
		return ""
	conecteaza = conecteaza or _conecteaza
	for port, schema in PORTURI_WEB:
		if conecteaza(ip, port, termen):
			return "%s://%s/" % (schema, ip)
	return ""


def text_eticheta(e):
	return {"router": _("routerul"), "receptor": _("acest receptor")}.get(e, "")
