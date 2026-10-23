# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsStareRetea.py: legatura receptorului cu routerul si cu internetul. O folosesc pictograma din bare (convertorul
# Components/Converter/HdsReteaPictograma.py), antetul paginilor web (HdsWebControl/stare_retea_web.py), pagina receptorului din
# a doua bara si afisajul din fata (internet(): True / False / None) si mesajul de pe mijlocul ecranului la pierderea
# internetului (Screens/HdsAnuntRetea.py). Din 0.4.4.
#
# Raspunsul (cod):
#   OK             internetul merge: un rezolvor DNS public a dat un raspuns valid (sau ora a venit prin NTP de curand)
#   FARA_INTERNET  receptorul e legat la router (poarta implicita raspunde), dar niciun rezolvor public nu raspunde:
#                  routerul nu are internet, problema e probabil la furnizorul de internet
#   FARA_ROUTER    receptorul nu e legat la router: cablul scos, Wi-Fi neasociat, nicio adresa, nicio ruta implicita
#                  sau poarta implicita nu raspunde
#   None           nu s-a aflat inca (se verifica)
#
# Cum se afla, cu cat mai putine cereri. NICIO cerere spre serverele HD Satelit (mii de receptoare nu au voie sa
# incarce serverul nostru) si nicio cerere HTTP spre adresele de verificare ale telefoanelor sau ale altor sisteme:
#   1. pasiv, din fisierele nucleului, fara nimic trimis: ruta implicita si poarta (/proc/net/route), adresa
#      (/proc/net/fib_trie), cablul (/sys/class/net/<if>/carrier), Wi-Fi si puterea semnalului (/proc/net/wireless).
#      Fara ruta, fara legatura fizica sau fara adresa: FARA_ROUTER pe loc. O sincronizare NTP reusita de curand
#      (Components/HdsCeas) inseamna OK fara nicio cerere noua.
#   2. o intrebare DNS mica (tip A; numele intrebat e chiar numele rezolvorului, publicat de el) spre rezolvoarele
#      publice gratuite, facute ca sa le foloseasca oricine: Cloudflare 1.1.1.1, Quad9 9.9.9.9, Google Public DNS
#      8.8.8.8; pe rand, UDP 53, cel mult TERMEN_DNS_S fiecare, oprire la primul raspuns valid (acelasi id, fara eroare,
#      macar o adresa A publica: un portal care raspunde cu o adresa din reteaua locala nu trece). Rezolvoarele puse in
#      receptor (/etc/resolv.conf) se intreaba dupa ele numai cand au adresa publica: routerul (adresa locala) raspunde
#      din memoria lui si cand nu mai are internet.
#   3. niciun rezolvor public nu raspunde: poarta implicita raspunde? Intrebarea DNS catre ea (orice raspuns, si "port
#      inchis"), apoi o conectare TCP pe 80 (conectat sau refuzat), apoi intrarea ARP a portii (completa, cu adresa
#      fizica). Da -> FARA_INTERNET, nu -> FARA_ROUTER.
#
# Cand: firul enigma2 cheama tic() la TIC_MS (eTimer pornit de porneste(), din mytest.py): citirea pasiva (cateva
# fisiere mici) si, cand e cazul, o verificare pe un fir separat: la intervalul ales (config.usage.hds_internet_interval:
# 30 s, 1, 2 sau 5 minute; din fabrica 1 minut) si imediat la orice schimbare a retelei (interfata, poarta, adresa,
# cablul). Firul enigma2 nu asteapta niciodata: toate raspunsurile vin din memorie.
#
# Mesajul de pe ecran: la trecerea din OK in FARA_ROUTER sau FARA_INTERNET, o singura data pe pierdere, numai cand pe
# ecran nu se vede nicio pictograma a retelei (convertorul spune cand o arata) si receptorul nu e in standby; la
# revenirea in OK, "Internetul merge din nou.", numai daca pierderea a fost anuntata.
#
# Setarea "Arata pictograma internetului in bare" (config.usage.hds_internet_pictograma, din fabrica da): oprita,
# pictograma nu se mai vede in bare, in capul ferestrelor Pro si in antetul paginilor web, iar vecinii ei isi iau
# inapoi locul (Components/HdsPictogramaBare.py). Verificarea merge mai departe; mesajul de pe ecran urmeaza regula lui
# (fara pictograma vazuta, apare si cu bara deschisa).
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import os
import struct
import sys
import threading
import time

OK = "ok"
FARA_INTERNET = "fara_internet"
FARA_ROUTER = "fara_router"
CABLU = "cablu"
WIFI = "wifi"

# rezolvoarele publice gratuite (adresa, numele lor publicat): fiecare e intrebat de propriul nume
REZOLVOARE_PUBLICE = (
	("1.1.1.1", "one.one.one.one"),   # Cloudflare
	("9.9.9.9", "dns.quad9.net"),     # Quad9
	("8.8.8.8", "dns.google"),        # Google Public DNS
)
TERMEN_DNS_S = 2.0
TERMEN_POARTA_S = 1.5
INTERVALE_S = (30, 60, 120, 300)
INTERVAL_IMPLICIT_S = 60
TIC_MS = 3000

CALE_RUTE = "/proc/net/route"
CALE_FIB = "/proc/net/fib_trie"
CALE_WIRELESS = "/proc/net/wireless"
CALE_ARP = "/proc/net/arp"
CALE_RESOLV = "/etc/resolv.conf"
SYS_NET = "/sys/class/net/"

# interfete care nu sunt legatura fizica (VPN, tunel): felul se ia de la placa adevarata
VIRTUALE = ("tun", "tap", "wg", "ppp", "ipsec", "gre", "sit", "lo")


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def N_(text):
	return text


def _jurnal(text):
	print("[HdsStareRetea] %s" % text)


# ---------------------------------------------------------------- citirea pasiva (fara nimic trimis)

def _citeste(cale, maxim=65536):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (IOError, OSError):
		return ""


def _hex_ip(h):
	"""Adresa IPv4 din /proc/net/route (8 cifre hex in ordinea nucleului: 0100000A = 10.0.0.1)."""
	try:
		v = int(h, 16)
	except ValueError:
		return None
	return (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF)


def _text_ip(t):
	return "%d.%d.%d.%d" % t if t else ""


def _tuplu_ip(s):
	try:
		p = tuple(int(x) for x in s.split("."))
	except (ValueError, AttributeError):
		return None
	return p if len(p) == 4 and all(0 <= x <= 255 for x in p) else None


def adresa_publica(ip):
	"""True pentru o adresa IPv4 de pe internet; False pentru retele locale, bucla, legatura locala, CGNAT, multicast
	si rezervate."""
	t = _tuplu_ip(ip)
	if t is None:
		return False
	a, b = t[0], t[1]
	if a in (0, 10, 127) or a >= 224:
		return False
	if a == 172 and 16 <= b <= 31:
		return False
	if a == 192 and b == 168:
		return False
	if a == 169 and b == 254:
		return False
	if a == 100 and 64 <= b <= 127:
		return False
	if a == 198 and b in (18, 19):
		return False
	if t[:3] in ((192, 0, 0), (192, 0, 2), (198, 51, 100), (203, 0, 113)):
		return False
	return True


def _virtuala(nume):
	return not nume or nume.startswith(VIRTUALE)


def _e_wifi(radacina, nume):
	return os.path.exists(radacina + SYS_NET + nume + "/wireless") or os.path.exists(radacina + SYS_NET + nume + "/phy80211")


def _fizic(radacina, nume):
	"""Legatura fizica a interfetei: True (cablul bagat / Wi-Fi asociat), False, None (nu se poate citi)."""
	t = _citeste(radacina + SYS_NET + nume + "/carrier", 16).strip()
	if t == "1":
		return True
	if t == "0":
		return False
	stare = _citeste(radacina + SYS_NET + nume + "/operstate", 32).strip()
	if stare in ("down", "lowerlayerdown", "notpresent"):
		return False
	return None


def _local_ipv4(radacina):
	"""Adresele IPv4 ale receptorului, din /proc/net/fib_trie (randurile "/32 host LOCAL"), fara bucla locala."""
	text = _citeste(radacina + CALE_FIB, 131072)
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


def treapta_wifi(radacina, nume):
	"""Puterea semnalului Wi-Fi in 4 trepte (1..4) din /proc/net/wireless; 0 cand nu se poate citi.
	Nivelul in dBm: >= -55 4, >= -65 3, >= -75 2, altfel 1; fara dBm, calitatea legaturii (din 70)."""
	for rand in _citeste(radacina + CALE_WIRELESS, 8192).splitlines()[2:]:
		nume_rand, _sep, rest = rand.partition(":")
		if nume_rand.strip() != nume:
			continue
		p = rest.split()
		if len(p) < 3:
			return 0
		try:
			calitate = float(p[1].rstrip("."))
			nivel = float(p[2].rstrip("."))
		except ValueError:
			return 0
		if nivel >= 128:
			nivel -= 256
		if nivel < 0:
			if nivel >= -55:
				return 4
			if nivel >= -65:
				return 3
			if nivel >= -75:
				return 2
			return 1
		maxim = 100.0 if calitate > 70 else 70.0
		procent = calitate * 100.0 / maxim
		if procent <= 0:
			return 0
		if procent >= 75:
			return 4
		if procent >= 50:
			return 3
		if procent >= 25:
			return 2
		return 1
	return 0


def fel_fizic(radacina=""):
	"""Felul legaturii cand nu e o ruta pe o placa adevarata (fara retea, VPN): Wi-Fi daca o placa Wi-Fi e pornita si
	asociata sau macar pornita, altfel cablu."""
	try:
		nume = sorted(os.listdir(radacina + SYS_NET))
	except OSError:
		return CABLU
	wifi = [n for n in nume if not _virtuala(n) and _e_wifi(radacina, n)]
	for n in wifi:
		if _fizic(radacina, n):
			return WIFI
	for n in nume:
		if not _virtuala(n) and not _e_wifi(radacina, n) and _fizic(radacina, n):
			return CABLU
	for n in wifi:
		if _citeste(radacina + SYS_NET + n + "/operstate", 32).strip() in ("up", "dormant"):
			return WIFI
	return CABLU


def legatura(radacina=""):
	"""Starea pasiva, citita acum din fisierele nucleului (nimic trimis in retea):
	{"interfata", "fel" (cablu / wifi / ""), "poarta", "ip", "fizic" (True / False / None), "treapta" (0..4)}."""
	interfata = ""
	poarta = ""
	poarta_oricare = ""
	retele = []
	implicite = []
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
		if steaguri & 2 and not poarta_oricare:
			poarta_oricare = _text_ip(_hex_ip(p[2]))
		if p[1] == "00000000" and p[7] == "00000000":
			try:
				metrica = int(p[6])
			except ValueError:
				metrica = 0
			implicite.append((metrica, len(implicite), p[0], _text_ip(_hex_ip(p[2])) if steaguri & 2 else ""))
		elif p[1] != "00000000":
			retele.append((p[0], _hex_ip(p[1]), _hex_ip(p[7])))
	# ruta pe care o foloseste nucleul: metrica cea mai mica, fara rutele unei placi adevarate fara legatura (cablul
	# scos), pe care nucleul le sare (ignore_routes_with_linkdown, Components/HdsComutareRetea.py); daca toate sunt
	# fara legatura, prima dintre ele (starea "fara router")
	cu_legatura = [r for r in implicite if _virtuala(r[2]) or _fizic(radacina, r[2]) is not False]
	if implicite:
		_m, _i, interfata, poarta = min(cu_legatura or implicite)
	if not interfata or "/" in interfata or interfata.startswith("."):
		return {"interfata": "", "fel": "", "poarta": "", "ip": "", "fizic": None, "treapta": 0}
	ip = ""
	locale = _local_ipv4(radacina)
	for nume, retea, masca in retele:
		if nume != interfata or retea is None or masca is None:
			continue
		for a in locale:
			t = _tuplu_ip(a)
			if t is not None and all((t[k] & masca[k]) == retea[k] for k in range(4)):
				ip = a
				break
		if ip:
			break
	if not ip and _virtuala(interfata) and locale:
		ip = locale[0]
	if _virtuala(interfata):
		fel = fel_fizic(radacina)
		fizic = None
	else:
		fel = WIFI if _e_wifi(radacina, interfata) else CABLU
		fizic = _fizic(radacina, interfata)
	treapta = treapta_wifi(radacina, interfata) if fel == WIFI and not _virtuala(interfata) else 0
	return {"interfata": interfata, "fel": fel, "poarta": poarta or poarta_oricare, "ip": ip, "fizic": fizic,
		"treapta": treapta}


def semnatura(s):
	"""Ce inseamna "reteaua s-a schimbat": alta interfata, alta poarta, alta adresa, cablul bagat sau scos."""
	return (s.get("interfata"), s.get("poarta"), s.get("ip"), s.get("fizic"))


def fara_router_pasiv(s):
	"""Fara ruta implicita, fara adresa sau fara legatura fizica: nu e nimic de intrebat."""
	return not s.get("interfata") or not s.get("ip") or s.get("fizic") is False


# ---------------------------------------------------------------- intrebarile mici (pe firul verificarii)

def intrebare_dns(nume, ident):
	"""Intrebarea DNS tip A, clasa IN, cu recursivitate ceruta."""
	q = b"".join(struct.pack("B", len(e)) + e.encode("ascii") for e in nume.strip(".").split(".") if e)
	return struct.pack(">HHHHHH", ident, 0x0100, 1, 0, 0, 0) + q + b"\x00" + struct.pack(">HH", 1, 1)


def _sari_nume(date, i):
	"""Pozitia de dupa un nume din mesajul DNS (etichete sau trimitere)."""
	for _pas in range(128):
		if i >= len(date):
			raise ValueError("nume taiat")
		n = bytearray(date[i:i + 1])[0]
		if n == 0:
			return i + 1
		if n & 0xC0 == 0xC0:
			return i + 2
		i += 1 + n
	raise ValueError("nume prea lung")


def adrese_a(date, ident):
	"""(id-ul se potriveste, adresele A) dintr-un raspuns DNS. Adresele sunt [] cand raspunsul nu e bun: alt id,
	nu e raspuns, are eroare, nu are raspunsuri sau e stricat."""
	if len(date) < 12:
		return False, []
	rid, steaguri, qd, an, _ns, _ar = struct.unpack(">HHHHHH", date[:12])
	if rid != ident:
		return False, []
	if not steaguri & 0x8000 or steaguri & 0x000F or qd != 1 or an == 0:
		return True, []
	try:
		i = _sari_nume(date, 12) + 4
		rez = []
		for _k in range(an):
			i = _sari_nume(date, i)
			if i + 10 > len(date):
				break
			tip, clasa, _ttl, lung = struct.unpack(">HHIH", date[i:i + 10])
			i += 10
			rd = bytearray(date[i:i + lung])
			i += lung
			if tip == 1 and clasa == 1 and lung == 4 and len(rd) == 4:
				rez.append("%d.%d.%d.%d" % tuple(rd))
		return True, rez
	except (ValueError, struct.error):
		return True, []


def _ident():
	return struct.unpack(">H", os.urandom(2))[0]


def intreaba_dns(server, nume, termen=TERMEN_DNS_S, port=53):
	"""True daca `server` da in `termen` secunde un raspuns valid cu macar o adresa A publica. Un singur pachet UDP mic
	(intrebarea), fara nimic despre om sau despre receptor."""
	import socket
	ident = _ident()
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		s.settimeout(termen)
		s.connect((server, port))
		s.send(intrebare_dns(nume, ident))
		sfarsit = time.monotonic() + termen
		while True:
			rest = sfarsit - time.monotonic()
			if rest <= 0:
				return False
			s.settimeout(rest)
			potrivit, adrese = adrese_a(s.recv(1500), ident)
			if potrivit:
				return any(adresa_publica(a) for a in adrese)
	except (OSError, ValueError, struct.error):
		return False
	finally:
		s.close()


def arp_complet(poarta, radacina=""):
	"""Intrarea ARP a portii e completa (routerul a raspuns la ARP): steagul 0x2 si o adresa fizica."""
	for rand in _citeste(radacina + CALE_ARP, 32768).splitlines()[1:]:
		p = rand.split()
		if len(p) < 4 or p[0] != poarta:
			continue
		try:
			steaguri = int(p[2], 16)
		except ValueError:
			continue
		return bool(steaguri & 0x2) and p[3] != "00:00:00:00:00:00"
	return False


def poarta_raspunde(poarta, termen=TERMEN_POARTA_S, radacina="", port_dns=53, port_tcp=80):
	"""Routerul (poarta implicita) raspunde? Pe rand: intrebarea DNS catre el (orice raspuns cu acelasi id, si "port
	inchis"), o conectare TCP pe portul 80 (conectat sau refuzat, fara nimic trimis), intrarea ARP completa. "Port
	inchis" vine pe Linux ca ConnectionRefusedError (ICMP pe soclul UDP legat); pe Windows (probele) ca
	ConnectionResetError."""
	if not _tuplu_ip(poarta):
		return False
	import socket
	ident = _ident()
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		s.settimeout(termen)
		s.connect((poarta, port_dns))
		s.send(intrebare_dns(REZOLVOARE_PUBLICE[0][1], ident))
		sfarsit = time.monotonic() + termen
		while True:
			rest = sfarsit - time.monotonic()
			if rest <= 0:
				break
			s.settimeout(rest)
			date = s.recv(1500)
			if len(date) >= 2 and struct.unpack(">H", date[:2])[0] == ident:
				return True
	except (ConnectionRefusedError, ConnectionResetError):
		return True
	except (OSError, struct.error):
		pass
	finally:
		s.close()
	try:
		c = socket.create_connection((poarta, port_tcp), termen)
		c.close()
		return True
	except ConnectionRefusedError:
		return True
	except OSError:
		pass
	return arp_complet(poarta, radacina)


def rezolvoare_proprii(radacina=""):
	"""Rezolvoarele puse in receptor (/etc/resolv.conf) care au adresa publica si nu sunt deja in lista publica."""
	publice = set(a for a, _n in REZOLVOARE_PUBLICE)
	rez = []
	for rand in _citeste(radacina + CALE_RESOLV, 8192).splitlines():
		p = rand.split()
		if len(p) >= 2 and p[0] == "nameserver" and adresa_publica(p[1]) and p[1] not in publice and p[1] not in rez:
			rez.append(p[1])
	return rez


def ntp_proaspat(fereastra_s):
	"""Ora a venit prin NTP (Components/HdsCeas) in ultimele `fereastra_s` secunde: internetul a mers fara nicio cerere
	noua. Numai daca modulul ceasului e deja incarcat (pe receptor, de la pornire)."""
	m = sys.modules.get("Components.HdsCeas")
	if m is None:
		return False
	try:
		s = m._unic[0]
		t = s.ntp_reusit_mono if s is not None else None
		return t is not None and 0.0 <= s.mono() - t < fereastra_s
	except Exception:
		return False


def verifica(s, interval_s=INTERVAL_IMPLICIT_S, dns=None, poarta=None, ntp=None, proprii=None, radacina=""):
	"""(cod, sursa) pentru starea pasiva `s`. Ruleaza pe firul verificarii (poate astepta cateva secunde)."""
	dns = dns or intreaba_dns
	poarta = poarta or poarta_raspunde
	ntp = ntp or ntp_proaspat
	if fara_router_pasiv(s):
		return FARA_ROUTER, "pasiv"
	if ntp(interval_s):
		return OK, "ntp"
	servere = list(REZOLVOARE_PUBLICE)
	for a in (rezolvoare_proprii(radacina) if proprii is None else proprii):
		servere.append((a, REZOLVOARE_PUBLICE[0][1]))
	for server, nume in servere:
		if dns(server, nume):
			return OK, server
	if poarta(s.get("poarta") or ""):
		return FARA_INTERNET, "poarta"
	return FARA_ROUTER, "poarta"


# ---------------------------------------------------------------- pictograma vazuta pe ecran (convertorul HdsReteaPictograma)

_vazute = set()


def arata_pictograma(cheie):
	_vazute.add(cheie)


def ascunde_pictograma(cheie):
	_vazute.discard(cheie)


def pictograma_pe_ecran():
	return bool(_vazute)


def in_standby():
	m = sys.modules.get("Screens.Standby")
	try:
		return m is not None and m.inStandby is not None
	except Exception:
		return False


# ---------------------------------------------------------------- setarea

def initConfig():
	"""config.usage.hds_internet_interval: cat de des se verifica internetul (30 s, 1, 2 sau 5 minute; din fabrica
	1 minut); config.usage.hds_internet_pictograma: pictograma internetului in bare (din fabrica da). Chemata din
	Components/UsageConfig.py, ca randurile din setup.xml sa le gaseasca."""
	from Components.config import config, ConfigSelection, ConfigYesNo
	u = config.usage
	if "hds_internet_pictograma" not in u.content.items:
		u.hds_internet_pictograma = ConfigYesNo(default=True)
	if "hds_internet_interval" not in u.content.items:
		u.hds_internet_interval = ConfigSelection(default=str(INTERVAL_IMPLICIT_S), choices=[
			("30", _("30 de secunde")),
			("60", _("un minut")),
			("120", _("2 minute")),
			("300", _("5 minute")),
		])
	return u.hds_internet_interval


def pictograma_aratata():
	"""True cand pictograma internetului se arata in bare si in antetul web (setarea, din fabrica da); la orice citire
	nereusita True."""
	try:
		m = sys.modules.get("Components.config")
		return bool(m.config.usage.hds_internet_pictograma.value)
	except Exception:
		return True


def interval_ales():
	"""Secundele intre doua verificari, din setare; din fabrica (sau la orice citire nereusita) 60."""
	try:
		m = sys.modules.get("Components.config")
		v = int(m.config.usage.hds_internet_interval.value)
		return v if v in INTERVALE_S else INTERVAL_IMPLICIT_S
	except Exception:
		return INTERVAL_IMPLICIT_S


# ---------------------------------------------------------------- textele

def text_mesaj(cod, fel):
	"""Mesajul de pe mijlocul ecranului (si ajutorul din web) pentru o pierdere sau pentru revenire."""
	if cod == FARA_ROUTER:
		if fel == WIFI:
			return _("Receptorul nu e conectat la router (Wi-Fi). Verifică rețeaua Wi-Fi sau routerul.")
		return _("Receptorul nu e conectat la router (cablu). Verifică cablul sau routerul.")
	if cod == FARA_INTERNET:
		return _("Receptorul e conectat la router, dar routerul nu are internet. Problema e probabil la furnizorul de internet.")
	if cod == OK:
		return _("Internetul merge din nou.")
	return ""


def text_ajutor(st):
	"""Textul scurt la pictograma (titlul la trecerea mouse-ului in web)."""
	cod = st.get("cod")
	fel = st.get("fel") or CABLU
	if cod == OK:
		if fel == WIFI:
			n = st.get("treapta") or 0
			if n:
				return _("Internet prin Wi-Fi: merge (semnal %d din 4)") % n
			return _("Internet prin Wi-Fi: merge")
		return _("Internet prin cablu: merge")
	if cod in (FARA_ROUTER, FARA_INTERNET):
		return text_mesaj(cod, fel)
	return _("Se verifică internetul...")


def cheie_pictograma(st):
	"""Numele pozei (fara .png) din HDSatelit/retea/ si al desenului din web pentru starea `st`."""
	cod = st.get("cod")
	fel = st.get("fel") or CABLU
	if fel == WIFI:
		if cod == FARA_ROUTER:
			return "wifi_fara_router"
		n = st.get("treapta") or 4
		n = max(1, min(4, n))
		if cod == OK:
			return "wifi%d_ok" % n
		if cod == FARA_INTERNET:
			return "wifi%d_fara_internet" % n
		return "wifi_verific"
	if cod == OK:
		return "cablu_ok"
	if cod == FARA_INTERNET:
		return "cablu_fara_internet"
	if cod == FARA_ROUTER:
		return "cablu_fara_router"
	return "cablu_verific"


PICTOGRAME = ("cablu_ok", "cablu_fara_internet", "cablu_fara_router", "cablu_verific",
	"wifi1_ok", "wifi2_ok", "wifi3_ok", "wifi4_ok",
	"wifi1_fara_internet", "wifi2_fara_internet", "wifi3_fara_internet", "wifi4_fara_internet",
	"wifi_fara_router", "wifi_verific")


# ---------------------------------------------------------------- urmaritorul (pe firul enigma2)

class Urmaritor(object):
	"""Starea tinuta minte si hotararea cand se verifica. tic() se cheama numai pe firul enigma2; verificarea ruleaza
	pe firul ei (sau pe loc, in probele de pe PC: porneste_fir=False)."""

	def __init__(self, citeste=None, verifica_fn=None, interval=None, ceas=None, porneste_fir=True, anunta=None,
			vizibil=None, standby=None, fel_gol=None):
		self.citeste = citeste or legatura
		self.verifica_fn = verifica_fn or verifica
		self.interval = interval or interval_ales
		self.ceas = ceas or time.monotonic
		self.porneste_fir = porneste_fir
		self.anunta = anunta
		self.vizibil = vizibil or pictograma_pe_ecran
		self.standby = standby or in_standby
		self.fel_gol = fel_gol or fel_fizic
		self._zavor = threading.Lock()
		self.pasiv = {"interfata": "", "fel": "", "poarta": "", "ip": "", "fizic": None, "treapta": 0}
		self.cod = None
		self.sursa = ""
		self.semn = None
		self.t_verificare = None
		self.t_tic = None
		self.lucreaza = False
		self.din_nou = False
		self.gen = 0
		self.fel_tinut = ""
		self.ultim_definit = None
		self.pierdere = False
		self.pierdere_anuntata = False
		self.verificari = 0

	# ---- starea

	def stare(self):
		with self._zavor:
			st = dict(self.pasiv)
			st["cod"] = self.cod
			st["sursa"] = self.sursa
		return st

	def tic(self, acum=None):
		acum = self.ceas() if acum is None else acum
		self.t_tic = acum
		s = self.citeste()
		if s.get("fel"):
			self.fel_tinut = s["fel"]
		else:
			s = dict(s)
			s["fel"] = self.fel_tinut or self.fel_gol()
		semn = semnatura(s)
		porneste = None
		with self._zavor:
			self.pasiv = s
			schimbat = self.semn is not None and semn != self.semn
			prima = self.semn is None
			self.semn = semn
			if fara_router_pasiv(s):
				# raspunsul se stie fara nicio cerere; o verificare in curs nu mai conteaza
				self.cod = FARA_ROUTER
				self.sursa = "pasiv"
				self.t_verificare = acum
				self.gen += 1
				self.din_nou = False
			else:
				if schimbat:
					self.din_nou = True
					if self.cod == FARA_ROUTER and self.sursa == "pasiv":
						self.cod = None   # cablul bagat la loc: "se verifica" pana vine raspunsul
				datorat = prima or self.din_nou or self.t_verificare is None or \
					not 0.0 <= acum - self.t_verificare < self.interval()
				if datorat and not self.lucreaza:
					self.lucreaza = True
					self.din_nou = False
					self.t_verificare = acum
					self.gen += 1
					porneste = (self.gen, dict(s))
		if porneste is not None:
			self.verificari += 1
			if self.porneste_fir:
				fir = threading.Thread(target=self._verifica, args=porneste)
				fir.daemon = True
				fir.start()
			else:
				self._verifica(*porneste)
		self._tranzitii()

	def cere_verificare(self):
		"""O verificare noua la urmatorul tic, inainte de interval: trecerea singura pe alta retea
		(Components/HdsComutareRetea.py) vrea 2-3 raspunsuri la rand dupa o pierdere, nu cate unul pe minut."""
		with self._zavor:
			self.din_nou = True

	def _verifica(self, gen, s):
		try:
			cod, sursa = self.verifica_fn(s, self.interval())
		except Exception as e:
			_jurnal("verificarea: %r" % (e,))
			cod, sursa = None, "eroare"
		with self._zavor:
			self.lucreaza = False
			if gen == self.gen and cod is not None:
				self.cod = cod
				self.sursa = sursa

	# ---- mesajul de pe ecran (numai pe firul enigma2)

	def _tranzitii(self):
		with self._zavor:
			cod = self.cod
			fel = self.pasiv.get("fel") or self.fel_tinut or CABLU
		if cod is None or cod == self.ultim_definit:
			return
		inainte = self.ultim_definit
		self.ultim_definit = cod
		if inainte == OK and cod in (FARA_ROUTER, FARA_INTERNET):
			self.pierdere = True
			self.pierdere_anuntata = False
			if self._se_poate_anunta():
				self.pierdere_anuntata = True
				self._anunta(cod, fel)
		elif cod == OK and self.pierdere:
			anuntata = self.pierdere_anuntata
			self.pierdere = False
			self.pierdere_anuntata = False
			if anuntata and self._se_poate_anunta():
				self._anunta(OK, fel)

	def _se_poate_anunta(self):
		try:
			return not self.vizibil() and not self.standby()
		except Exception:
			return False

	def _anunta(self, cod, fel):
		if self.anunta is None:
			return
		try:
			self.anunta(cod, fel)
		except Exception as e:
			_jurnal("mesajul: %r" % (e,))


_unic = [None]
_ceas = [None]


def urmaritor():
	if _unic[0] is None:
		_unic[0] = Urmaritor()
	return _unic[0]


def stare(acum=None):
	"""Starea pentru pictograma si web: {"cod", "fel", "treapta", "interfata", "ip", "poarta", "sursa"}. Pe firul enigma2:
	cand ceasul modulului nu a batut de mai mult de doua tacte (sau n-a pornit), tic() se face acum."""
	u = urmaritor()
	acum = u.ceas() if acum is None else acum
	if u.t_tic is None or not 0.0 <= acum - u.t_tic < 2.0 * TIC_MS / 1000.0:
		u.tic(acum)
	return u.stare()


def internet(acum=None):
	"""True / False / None (nu s-a aflat inca). Pentru pagina receptorului din a doua bara si afisajul din fata."""
	cod = stare(acum).get("cod")
	if cod == OK:
		return True
	if cod in (FARA_ROUTER, FARA_INTERNET):
		return False
	return None


def porneste(session=None):
	"""Din mytest.py, dupa pornirea sesiunii: ceasul de TIC_MS pe firul enigma2 si fereastra mesajului."""
	u = urmaritor()
	if session is not None:
		def anunta(cod, fel):
			from Screens import HdsAnuntRetea
			HdsAnuntRetea.arata(session, text_mesaj(cod, fel), cheie_pictograma({"cod": cod, "fel": fel, "treapta": 4}))
		u.anunta = anunta
	if _ceas[0] is None:
		from enigma import eTimer
		t = eTimer()
		t.callback.append(u.tic)
		_ceas[0] = t
	_ceas[0].start(TIC_MS, False)
	u.tic()
