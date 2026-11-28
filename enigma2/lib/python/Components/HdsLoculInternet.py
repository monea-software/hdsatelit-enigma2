# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLoculInternet.py - locul antenei aflat dupa adresa de internet a receptorului. Locul unic al motorului USALS
# ramane in Components/HdsLocul.py; aici se afla si se scrie prin HdsLocul.seteaza (sursa "internet").
#
# Pana la 0.7.9 locul gasit era numai o propunere: omul alegea "Afla locul dupa internet" si raspundea Da la o
# intrebare (locul dupa adresa e aproximativ, uneori orasul furnizorului). Din 0.8.0 (LOC2: implicit cat timp e
# internet, inactiv numai fara internet) e locul implicit, fara nicio intrebare:
#   - cat HdsLocul.automat() (omul nu a ales singur un oras sau coordonate), locul se afla singur la fiecare pornire
#     (laPornire, din Components/SetupDevices.py: acelasi raspuns ca fusul orar, Components/HdsFusTara.py, deci nicio
#     cerere in plus cand fusul a intrebat deja), dupa primul NTP reusit daca la pornire nu a mers (dupaNtp) si la
#     deschiderea ecranului sau a paginii web; se scrie numai cand difera de locul de acum (seteaza face sec.update(),
#     care uita pozitia motorului), iar cat antena se roteste sau merge o inregistrare se mai incearca o data mai tarziu;
#   - "Afla locul dupa internet" (ecran, web) face din nou locul cel dupa internet si il scrie pe loc;
#   - cu un VPN pornit pe receptor cererea iese direct, pe langa tunel (LOC3, ocolesteVpn mai jos), deci serverul vede
#     adresa de acasa a omului, nu pe a serverului VPN; cand nu se poate iesi direct, nu pleaca nicio cerere;
#   - fara ruta spre internet (citita local din /proc/net/route si /proc/net/ipv6_route, nicio conexiune) nu pleaca
#     nicio cerere: ramane ultimul loc stiut, iar omul poate alege din lista tarilor si oraselor;
#   - cu ruta: o singura cerere HTTPS GET spre serverul nostru (ADRESA), fara parametri si fara nimic despre receptor.
#     Serverul vede numai adresa de internet de la care vine cererea, cauta orasul in baza lui (DB-IP Lite, CC BY 4.0)
#     si raspunde cu orasul, tara si coordonatele; adresa nu o pastreaza. Niciun serviciu strain nu e intrebat;
#   - raspunsul se verifica (marime, JSON, fiecare camp, limitele coordonatelor); un oras din tabelul imaginii
#     (HdsLocul.orase, fisierul oraselor) aflat la cel mult RAZA_KM, in aceeasi tara, ii ia locul: numele romanesc si
#     coordonatele din tabel, ca la alegerea din lista;
#   - lista tarilor si oraselor se deschide pe orasul din tabel cel mai apropiat de locul gasit (pentruLista), chiar
#     daca orasul gasit nu e in tabel.
#
# Firul enigma2 nu asteapta: cererea merge pe un fir separat (Cautare.porneste), locul se scrie pe firul enigma2
# (reactor.callFromThread), iar ecranul si pagina web intreaba starea (Cautare.stare) pe un ceas. La import nu se
# atinge nimic din enigma, ca probele de pe PC sa poata pune obiecte false; cererea, ruta si firele se pot inlocui din
# probe.
import hashlib
import json
import math
import threading
import time
import unicodedata

ADRESA = "https://stb.hdsatelit.com/receptor/locul"
TIMP_S = 8.0
# cat asteapta omul cel mult: urlopen nu margineste aflarea numelui (DNS), care cu ruta dar fara internet poate tine
# zeci de secunde; dupa LIMITA_S cautarea e "serverul nu a raspuns", iar raspunsul intarziat al firului nu se mai ia
LIMITA_S = TIMP_S + 4.0
MARIME_MAX = 4096
RAZA_KM = 10.0
# cat de departe poate fi orasul din tabel pe care se deschide lista, cand tara gasita nu e in tabel (pentruLista)
RAZA_LISTA_KM = 1500.0
# cat ramane bun un loc gasit pentru confirmarea din pagina web (semnul lui)
VALABIL_S = 1800.0
AGENT = "hdsatelit-receptor/1"
FISIER_RUTE4 = "/proc/net/route"
FISIER_RUTE6 = "/proc/net/ipv6_route"
# atribuirea ceruta de licenta bazei de pe server, cand raspunsul nu o aduce
SURSA_IMPLICITA = "IP Geolocation by DB-IP (db-ip.com), CC BY 4.0"
LUNGIME_ORAS = 80
LUNGIME_SURSA = 160

# steagurile rutelor din nucleul Linux (include/uapi/linux/route.h)
RTF_UP = 0x0001
RTF_REJECT = 0x0200

NIMIC = "nimic"
LUCREAZA = "lucreaza"
GASIT = "gasit"
EROARE = "eroare"
FARA_RETEA = "fara_retea"


def N_(text):
	return text


def _t(text):
	"""traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC"""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


OPTIUNE = N_("Află locul după internet")
CAUT = N_("Caut locul după adresa de internet a receptorului...")
MESAJ_FARA_RETEA = N_("Receptorul nu are internet acum, deci locul nu se poate afla singur. Alege țara și orașul din listă.")
MESAJ_NU_RASPUNDE = N_("Serverul HD Satelit nu a răspuns sau nu poate da locul acum. Alege țara și orașul din listă.")
MESAJ_STRICAT = N_("Răspunsul serverului HD Satelit nu se poate folosi. Alege țara și orașul din listă.")
MESAJ_NEGASIT = N_("După adresa de internet a receptorului nu se știe orașul. Alege țara și orașul din listă.")
MESAJ_PREA_DES = N_("Locul s-a cerut de prea multe ori de la această adresă de internet. Încearcă peste un minut sau alege țara și orașul din listă.")
MESAJ_EXPIRAT = N_("Locul găsit nu mai este cel arătat. Caută din nou sau alege țara și orașul din listă.")
NOTA_SURSA = N_("Coordonatele orașelor din listă: %s. Locul după internet vine de la serverul HD Satelit, care nu păstrează adresa de internet.")
TEXT_SERVER = N_("prin serverul HD Satelit")
# felul locului, pe televizor si in pagina web (LOC2)
TEXT_AUTOMAT = N_("Locul se află singur după internet. Dacă nu e orașul tău, alege-l din listă.")
# %s = randul OPTIUNE, tradus (acelasi nume ca in lista ecranului)
TEXT_ALES = N_("Locul l-ai ales tu. Ca să se afle singur, alege: %s.")


def jurnal(text):
	print("[HdsLoculInternet] %s" % text)


def _locul():
	from Components import HdsLocul
	return HdsLocul


# ---------------------------------------------------------------- ruta spre internet (numai fisiere locale)

def _citesteRanduri(cale):
	try:
		with open(cale, "r", encoding="utf-8") as f:
			return f.read().splitlines()
	except (IOError, OSError):
		return []


def _steaguri(text):
	try:
		return int(text, 16)
	except ValueError:
		return None


def _ruta4(cale):
	"""o ruta implicita IPv4 pornita, nerefuzata, pe o interfata adevarata (nu lo, nu *)"""
	for rand in _citesteRanduri(cale)[1:]:
		c = rand.split()
		if len(c) < 8:
			continue
		interfata, destinatie, steaguri, masca = c[0], c[1], _steaguri(c[3]), c[7]
		if steaguri is None or destinatie != "00000000" or masca != "00000000":
			continue
		if steaguri & RTF_UP and not steaguri & RTF_REJECT and interfata not in ("lo", "*"):
			return True
	return False


def _ruta6(cale):
	"""o ruta implicita IPv6 (::/0) pornita, nerefuzata, pe o interfata adevarata; ruta ::/0 'unreachable' pe lo, pe care
	nucleul o pune singur, nu se socoteste"""
	for rand in _citesteRanduri(cale):
		c = rand.split()
		if len(c) < 10:
			continue
		destinatie, prefix, steaguri, interfata = c[0], c[1], _steaguri(c[8]), c[9]
		if steaguri is None or destinatie != "0" * 32 or prefix != "00":
			continue
		if steaguri & RTF_UP and not steaguri & RTF_REJECT and interfata != "lo":
			return True
	return False


def retea(rute4=None, rute6=None):
	"""True daca receptorul are o ruta implicita (IPv4 sau IPv6). Nicio conexiune: numai tabelele de rute ale
	nucleului. Fara ruta, nicio cerere nu pleaca."""
	return _ruta4(rute4 or FISIER_RUTE4) or _ruta6(rute6 or FISIER_RUTE6)


# ---------------------------------------------------------------- ocolirea VPN-ului receptorului (LOC3)
#
# Din 0.8.0 VPN-ul nu se aplica la ce se afla dupa locul omului pe internet: locul antenei, fusul
# orar (HdsFusTara) si limba aleasa singura dupa tara (HdsLimbaTara). Toate trei cer serverul nostru prin _citesteUrl,
# deci ocolirea sta numai aici.
#
# Cum: cand pe receptor exista o interfata de tunel (VPN-ul imaginii, Components/HdsVpn.py: hdsvpn0..5 si ipsec0,
# rutate prin tabela 51830 si reguli "ip rule"; sau un OpenVPN/WireGuard pus altfel: tun, tap, wg), adresele IPv4 ale
# serverului primesc pe durata cererii cate o ruta /32 in tabela main, prin poarta rutei implicite din main (cea de
# dinainte de VPN, pe care HdsVpn nu o atinge). Regula HdsVpn "lookup main suppress_prefixlength 0" lasa un /32 sa
# treaca inaintea tabelei VPN (si inaintea opririi totale, "unreachable default" din tabela VPN), iar un /32 bate si jumatatile
# /1 ale unui OpenVPN strain. Dupa "ip route replace" se verifica cu "ip -4 route get" ca iesirea e interfata directa;
# cererea merge numai spre adresele rutate (IPv4; certificatul si SNI raman ale numelui serverului), iar rutele se scot
# in finally. Fara interfata de tunel nu ruleaza nicio comanda: cererea e cea de pana acum.
# Cand ocolirea nu se poate (nicio ruta implicita directa in main, "ip" cade, verificarea arata tot tunelul) cererea nu
# pleaca: locul, fusul si limba raman cele stiute, ca sa nu se mute motorul pe orasul serverului VPN.
# Un VPN pe routerul omului nu se vede de pe receptor si nu se poate ocoli: atunci serverul vede iesirea VPN-ului, iar
# omul isi alege orasul din lista.

# interfetele tunelurilor: OpenVPN tun/tap, WireGuard wg, HdsVpn hdsvpnN, strongSwan kernel-libipsec ipsec0
PREFIXE_TUNEL = ("tun", "tap", "wg", "hdsvpn", "ipsec")
FISIER_INTERFETE = "/proc/net/dev"
PROGRAM_IP = "/sbin/ip"
TIMP_IP_S = 5
RTF_GATEWAY = 0x0002
# cate adrese IPv4 ale serverului se ruteaza cel mult (Cloudflare da doua)
MAX_ADRESE = 4
# probele de pe PC: fn(argv fara /sbin/ip, timp) -> (cod, text); fn(gazda, port) -> [adrese IPv4]
RULATOR = None
REZOLVA = None
_ZAVOR_OCOLIRE = threading.Lock()


class FaraOcolire(IOError):
	"""VPN pornit pe receptor, dar cererea nu poate iesi direct: nu pleaca"""


def interfeteTunel(cale=None):
	"""numele interfetelor de tunel VPN ale receptorului (din /proc/net/dev, fara nicio conexiune)"""
	rez = []
	for rand in _citesteRanduri(cale or FISIER_INTERFETE):
		if ":" not in rand:
			continue
		nume = rand.split(":", 1)[0].strip()
		# tunl0 (ipip) exists on some kernels without any VPN
		if nume.startswith(PREFIXE_TUNEL) and not nume.startswith("tunl"):
			rez.append(nume)
	return rez


def _ipDinHex(text):
	"""adresa IPv4 din /proc/net/route (ordinea octetilor gazdei, little-endian pe toate receptoarele)"""
	import socket
	import struct
	return socket.inet_ntoa(struct.pack("<I", int(text, 16)))


def poartaDirecta(rute4=None):
	"""(interfata, poarta sau None) a rutei implicite IPv4 din tabela main care nu e pe un tunel, cu metrica cea mai
	mica; None daca nu exista (de exemplu un VPN strain care a inlocuit ruta implicita)"""
	bune = []
	for rand in _citesteRanduri(rute4 or FISIER_RUTE4)[1:]:
		c = rand.split()
		if len(c) < 8 or c[1] != "00000000" or c[7] != "00000000":
			continue
		steaguri = _steaguri(c[3])
		if steaguri is None or not steaguri & RTF_UP or steaguri & RTF_REJECT:
			continue
		if c[0] in ("lo", "*") or c[0].startswith(PREFIXE_TUNEL):
			continue
		try:
			metrica = int(c[6])
			poarta = _ipDinHex(c[2]) if steaguri & RTF_GATEWAY else None
		except (ValueError, OSError):
			continue
		bune.append((metrica, c[0], poarta))
	if not bune:
		return None
	bune.sort(key=lambda x: x[0])
	return bune[0][1], bune[0][2]


def _ip(argv, timp=TIMP_IP_S):
	if RULATOR is not None:
		return RULATOR(list(argv), timp)
	import subprocess
	try:
		p = subprocess.run([PROGRAM_IP] + list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT, timeout=timp)
		return p.returncode, p.stdout.decode("utf-8", "replace")
	except (OSError, subprocess.SubprocessError) as e:
		return -1, "%s: %s" % (type(e).__name__, e)


def iesirea(adresa):
	"""interfata pe care pleaca acum un pachet spre `adresa` (ip -4 route get, cu regulile VPN-ului); None daca ruta
	e refuzata (oprirea totala) sau nu se stie"""
	import re
	cod, text = _ip(["-4", "route", "get", adresa])
	if cod != 0:
		return None
	m = re.search(r"\bdev\s+(\S+)", text)
	return m.group(1) if m else None


def _adreseIpv4(gazda, port):
	if REZOLVA is not None:
		return list(REZOLVA(gazda, port))
	import socket
	rez = []
	for _f, _t2, _p, _c, sa in socket.getaddrinfo(gazda, port, socket.AF_INET, socket.SOCK_STREAM):
		if sa[0] not in rez:
			rez.append(sa[0])
	return rez


def _rutaArgv(adresa, interfata, poarta):
	return [adresa + "/32"] + (["via", poarta] if poarta else []) + ["dev", interfata]


def _deschideSpre(adrese):
	"""urlopen pe adresele IPv4 date (in ordine), cu numele serverului pastrat pentru certificat, SNI si Host"""
	import socket
	import http.client
	import urllib.request

	def conecteaza(adresa, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None, *a, **k):
		eroare = None
		for ip in adrese:
			try:
				return socket.create_connection((ip, adresa[1]), timeout, source_address)
			except (OSError, socket.error) as e:
				eroare = e
		raise eroare or IOError("nicio adresa")

	class _Conexiune(http.client.HTTPSConnection):
		def __init__(self, *a, **k):
			http.client.HTTPSConnection.__init__(self, *a, **k)
			self._create_connection = conecteaza

	class _Https(urllib.request.HTTPSHandler):
		def https_open(self, req):
			return self.do_open(_Conexiune, req, context=self._context)

	return urllib.request.build_opener(_Https()).open


def ocolesteVpn(adresa, cerere, tunele=None, rute4=None):
	"""Ruleaza `cerere(deschide)` cu cererea spre `adresa` iesind direct, nu prin VPN-ul receptorului.
	`deschide(Request, timeout=)` e urlopen-ul de folosit. Arunca FaraOcolire cand nu se poate iesi direct."""
	try:
		from urllib.parse import urlsplit
	except ImportError:  # Python 2, numai pe PC
		from urlparse import urlsplit
	tunele = interfeteTunel() if tunele is None else tunele
	if not tunele:
		return cerere(None)
	u = urlsplit(adresa)
	poarta = poartaDirecta(rute4)
	if poarta is None:
		raise FaraOcolire("VPN pornit (%s), dar nicio ruta implicita directa in main" % ",".join(tunele))
	interfata, gw = poarta
	adrese = _adreseIpv4(u.hostname, u.port or 443)[:MAX_ADRESE]
	if not adrese:
		raise FaraOcolire("serverul nu are adresa IPv4")
	with _ZAVOR_OCOLIRE:
		puse = []
		try:
			for ip in adrese:
				if iesirea(ip) == interfata:
					continue
				cod, text = _ip(["-4", "route", "replace"] + _rutaArgv(ip, interfata, gw))
				if cod != 0:
					raise FaraOcolire("ip route replace %s: %s" % (ip, text.strip()[:200]))
				puse.append(ip)
				dev = iesirea(ip)
				if dev != interfata:
					raise FaraOcolire("%s iese tot pe %s" % (ip, dev))
			jurnal("VPN pornit (%s): cererea iese direct pe %s" % (",".join(tunele), interfata))
			return cerere(_deschideSpre(adrese))
		finally:
			for ip in puse:
				cod, text = _ip(["-4", "route", "del"] + _rutaArgv(ip, interfata, gw))
				if cod != 0:
					jurnal("ruta %s/32 nu s-a scos: %s" % (ip, text.strip()[:200]))


# ---------------------------------------------------------------- cererea si verificarea raspunsului

def _citesteUrl(adresa, timp, limita):
	"""(cod HTTP, corp) pentru un GET; arunca numai la erorile de retea (fara raspuns, timp depasit, certificat).
	Corpul se citeste cel mult pana la limita + 1 octeti. Cu VPN pe receptor cererea iese direct (ocolesteVpn)."""
	return ocolesteVpn(adresa, lambda deschide: _citesteUrlPrin(deschide, adresa, timp, limita))


def _citesteUrlPrin(deschide, adresa, timp, limita):
	try:
		from urllib.request import Request, urlopen
		from urllib.error import HTTPError
	except ImportError:  # Python 2, numai pe PC
		from urllib2 import Request, urlopen, HTTPError
	cerere = Request(adresa, headers={"User-Agent": AGENT, "Accept": "application/json", "Accept-Encoding": "identity"})
	try:
		r = (deschide or urlopen)(cerere, timeout=timp)
	except HTTPError as e:
		try:
			corp = e.read(limita + 1)
		except Exception:
			corp = b""
		return e.code, corp
	try:
		return r.getcode(), r.read(limita + 1)
	finally:
		r.close()


def _numar(x, maxim):
	if isinstance(x, bool) or not isinstance(x, (int, float)):
		return None
	x = float(x)
	if math.isnan(x) or math.isinf(x) or not -maxim <= x <= maxim:
		return None
	return x


def _text(x, maxim):
	"""un text scurt de afisat: forma NFC, fara caractere de control, fara spatii la capete; None daca lipseste sau e
	prea lung"""
	if not isinstance(x, str):
		return None
	x = unicodedata.normalize("NFC", x)
	x = u"".join(c for c in x if not unicodedata.category(c).startswith("C")).strip()
	if not x or len(x) > maxim:
		return None
	return x


def verifica(corp):
	"""Corpul raspunsului (octeti) -> {"oras", "tara", "tara_nume", "lat_mii", "lon_mii", "sursa"}; ValueError cu
	motivul daca nu se poate folosi. Coordonatele sunt in miimi de grad, nord si est pozitive."""
	if not isinstance(corp, (bytes, bytearray)):
		raise ValueError("corpul nu e octeti")
	if len(corp) > MARIME_MAX:
		raise ValueError("raspuns prea mare")
	try:
		d = json.loads(bytes(corp).decode("utf-8"))
	except (UnicodeDecodeError, ValueError):
		raise ValueError("raspunsul nu e JSON")
	if not isinstance(d, dict):
		raise ValueError("raspunsul nu e un obiect")
	lat, lon = _numar(d.get("lat"), 90), _numar(d.get("lon"), 180)
	if lat is None or lon is None:
		raise ValueError("coordonate lipsa sau in afara limitelor: %r, %r" % (d.get("lat"), d.get("lon")))
	if abs(lat) < 0.01 and abs(lon) < 0.01:
		raise ValueError("coordonatele 0, 0 nu sunt un loc")
	tara = d.get("tara")
	if not isinstance(tara, str) or len(tara) != 2 or not all("A" <= c <= "Z" for c in tara.upper()):
		raise ValueError("codul tarii lipseste sau nu e bun: %r" % (tara,))
	oras = _text(d.get("oras"), LUNGIME_ORAS)
	if oras is None:
		raise ValueError("orasul lipseste sau nu e bun")
	return {"oras": oras, "tara": tara.upper(), "tara_nume": _text(d.get("tara_nume"), LUNGIME_ORAS) or "",
		"lat_mii": int(round(lat * 1000)), "lon_mii": int(round(lon * 1000)),
		"sursa": _text(d.get("sursa"), LUNGIME_SURSA) or SURSA_IMPLICITA}


def distantaKm(lat1, lon1, lat2, lon2):
	"""distanta pe sfera (haversine), in km; coordonatele in grade"""
	f1, f2 = math.radians(lat1), math.radians(lat2)
	df, dl = f2 - f1, math.radians(lon2 - lon1)
	a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
	return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


def potrivesteTabel(rez, orase=None):
	"""Orasul cel mai apropiat din tabelul imaginii, din aceeasi tara si la cel mult RAZA_KM, ia locul celui gasit
	(numele si coordonatele din tabel, din_tabel=True); altfel raman cele de pe server, rotunjite la 0,01 grade, ca in
	tabel. `orase` (probele): [(nume, lat_mii, lon_mii)] ale tarii."""
	rez = dict(rez)
	if orase is None:
		try:
			orase = _locul().orase(rez["tara"])
		except Exception as e:
			jurnal("tabelul oraselor: %r" % (e,))
			orase = []
	lat, lon = rez["lat_mii"] / 1000.0, rez["lon_mii"] / 1000.0
	cel_mai_bun = None
	for nume, lat_t, lon_t in orase:
		d = distantaKm(lat, lon, lat_t / 1000.0, lon_t / 1000.0)
		if d <= RAZA_KM and (cel_mai_bun is None or d < cel_mai_bun[0]):
			cel_mai_bun = (d, nume, lat_t, lon_t)
	if cel_mai_bun is not None:
		rez.update(oras=cel_mai_bun[1], lat_mii=int(cel_mai_bun[2]), lon_mii=int(cel_mai_bun[3]), din_tabel=True)
	else:
		rez.update(lat_mii=int(round(rez["lat_mii"] / 10.0)) * 10, lon_mii=int(round(rez["lon_mii"] / 10.0)) * 10,
			din_tabel=False)
	return rez


def _celMaiAproape(lat, lon, orase):
	"""(distanta in km, nume) al orasului din `orase` [(nume, lat_mii, lon_mii)] cel mai aproape de lat, lon (grade);
	None cand lista e goala"""
	cel = None
	for nume, lat_t, lon_t in orase:
		d = distantaKm(lat, lon, lat_t / 1000.0, lon_t / 1000.0)
		if cel is None or d < cel[0]:
			cel = (d, nume)
	return cel


def pentruLista(rez, orase=None, coduri=None):
	"""(tara, oras) din tabelul imaginii pe care se deschide lista cand omul nu primeste locul gasit: orasul cel mai
	apropiat de locul gasit din tara gasita, oricat de departe (potrivesteTabel il inlocuieste numai la cel mult
	RAZA_KM). Cand tara gasita nu e in tabel: cel mai apropiat oras al oricarei tari din tabel, cel mult RAZA_LISTA_KM.
	("", "") cand nimic nu se potriveste (lista se deschide pe locul de acum). `orase(cod)` -> [(nume, lat_mii,
	lon_mii)] si `coduri` (codurile tarilor) se inlocuiesc in probe."""
	try:
		lat, lon = rez["lat_mii"] / 1000.0, rez["lon_mii"] / 1000.0
		din_fisier = orase is None
		orase = orase or _locul().orase
		cel = _celMaiAproape(lat, lon, orase(rez["tara"]))
		if cel is not None:
			return rez["tara"], cel[1]
		if din_fisier and coduri is None:
			# toata lumea dintr-o singura citire a fisierului oraselor (nu cate o citire pe tara)
			for cod, nume, lat_t, lon_t in _locul().toateOrasele():
				d = distantaKm(lat, lon, lat_t / 1000.0, lon_t / 1000.0)
				if d <= RAZA_LISTA_KM and (cel is None or d < cel[0]):
					cel = (d, nume, cod)
			return (cel[2], cel[1]) if cel is not None else ("", "")
		if coduri is None:
			coduri = [cod for cod, _nume in _locul().tari()]
		for cod in coduri:
			g = _celMaiAproape(lat, lon, orase(cod))
			if g is not None and g[0] <= RAZA_LISTA_KM and (cel is None or g[0] < cel[0]):
				cel = (g[0], g[1], cod)
		if cel is not None:
			return cel[2], cel[1]
	except Exception as e:
		jurnal("orasul pentru lista: %r" % (e,))
	return "", ""


def _mesajCeas(eroare):
	"""textul "ceasul receptorului e gresit" cand certificatul cade din cauza ceasului (Components/HdsCeasHttps.py)"""
	try:
		from Components import HdsCeasHttps
		return HdsCeasHttps.mesaj(eroare)
	except Exception:
		return None


def cauta(citeste_url=None, adresa=None, timp=TIMP_S):
	"""Cererea si verificarea. Blocanta: numai pe firul cautarii. -> (GASIT, rezultat) sau (EROARE, mesajul pentru om).
	`citeste_url(adresa, timp, limita)` -> (cod HTTP, corp) se inlocuieste in probe."""
	citeste_url = citeste_url or _citesteUrl
	try:
		cod, corp = citeste_url(adresa or ADRESA, timp, MARIME_MAX)
	except Exception as e:
		jurnal("cererea nu a mers: %s: %s" % (type(e).__name__, e))
		return EROARE, _mesajCeas(e) or _t(MESAJ_NU_RASPUNDE)
	if cod == 429:
		return EROARE, _t(MESAJ_PREA_DES)
	if cod == 404:
		# 404 cu {"eroare": "negasit"} e raspunsul serviciului (adresa nu are oras in baza); orice alt 404 (pagina
		# serverului web, serviciul nepus inca) inseamna ca serverul nu poate da locul
		try:
			negasit = json.loads(bytes(corp).decode("utf-8")).get("eroare") == "negasit"
		except Exception:
			negasit = False
		return EROARE, _t(MESAJ_NEGASIT if negasit else MESAJ_NU_RASPUNDE)
	if cod != 200:
		jurnal("serverul a raspuns HTTP %s" % cod)
		return EROARE, _t(MESAJ_NU_RASPUNDE)
	try:
		rez = verifica(corp)
	except ValueError as e:
		jurnal("raspuns respins: %s" % e)
		return EROARE, _t(MESAJ_STRICAT)
	return GASIT, potrivesteTabel(rez)


# ---------------------------------------------------------------- textele pentru om

def numeTara(rez):
	"""numele tarii in tabelul imaginii (romanesc), altfel cel de pe server, altfel codul"""
	try:
		nume = _locul().numeTara(rez["tara"])
	except Exception:
		nume = ""
	return nume or rez.get("tara_nume") or rez["tara"]


def textCoordonate(rez):
	try:
		return _locul().textCoordonate(rez["lat_mii"], rez["lon_mii"], 2)
	except Exception:
		return "%.2f, %.2f" % (rez["lat_mii"] / 1000.0, rez["lon_mii"] / 1000.0)


def textLoc(rez):
	return u"%s, %s" % (rez["oras"], numeTara(rez))


def textSursa(rez):
	return u"%s, %s" % (rez["sursa"], _t(TEXT_SERVER))


def textFel():
	"""ce face locul de acum: se afla singur dupa internet sau l-a ales omul"""
	try:
		return _t(TEXT_AUTOMAT) if _locul().automat() else _t(TEXT_ALES) % _t(OPTIUNE)
	except Exception:
		return ""


def semn(rez):
	"""semnul locului gasit: pagina web confirma exact locul pe care l-a aratat"""
	text = u"%s|%s|%d|%d" % (rez["tara"], rez["oras"], rez["lat_mii"], rez["lon_mii"])
	return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- cautarea (una singura, a ecranului si a paginii web)

def _firDaemon(functie):
	t = threading.Thread(target=functie, name="hds-locul-internet")
	t.daemon = True
	t.start()
	return t


def _peFirulPrincipal(functie):
	"""`functie` pe firul enigma2 (locul se scrie in config si nucleu numai de acolo)"""
	principal = getattr(threading, "main_thread", None)
	if principal is not None and threading.current_thread() is principal():
		functie()
		return
	from twisted.internet import reactor
	reactor.callFromThread(functie)


def laFel(rez, L=None):
	"""True cand locul gasit e chiar locul de acum (aceleasi coordonate, aceeasi tara si acelasi oras): nu se scrie din
	nou (seteaza ar face sec.update(), care uita pozitia motorului)"""
	L = L or _locul()
	try:
		st = L.stare()
	except Exception:
		return False
	return bool(st.get("stabilit")) and L.locul() == (int(rez["lat_mii"]), int(rez["lon_mii"])) and \
		st.get("tara") == rez["tara"] and st.get("oras") == rez["oras"]


def aplica(rez, actualizeaza_sec=True, L=None):
	"""Locul gasit devine locul antenei (HdsLocul.seteaza, sursa internet), fara intrebare. Pe firul enigma2.
	-> (True, "") (scris sau deja acelasi) sau (False, motivul pentru om: antena se roteste, o inregistrare...)"""
	L = L or _locul()
	if laFel(rez, L):
		jurnal("locul dupa internet ramane %s" % textLoc(rez))
		return True, ""
	ok, text = L.seteaza(rez["lat_mii"], rez["lon_mii"], rez["tara"], rez["oras"], L.SURSA_INTERNET,
		actualizeaza_sec=actualizeaza_sec)
	if ok:
		jurnal("locul dupa internet scris: %s" % textLoc(rez))
	return ok, text


class Cautare(object):
	"""Starea cautarii, aceeasi pentru televizor si pentru pagina web. porneste() nu asteapta; stare() se cheama de pe
	un ceas. Cu porneste(scrie=True) locul gasit se scrie singur, pe firul enigma2 (aplica), inainte ca stare() sa spuna
	"gasit"; "scris" si "mesaj_scris" spun ce a iesit."""

	def __init__(self, cauta_=None, retea_=None, fir=None, ceas=None, pe_fir=None, aplica_=None):
		self._cauta = cauta_ or cauta
		self._retea = retea_ or retea
		self._fir = fir or _firDaemon
		self._ceas = ceas or time.time
		self._peFir = pe_fir or _peFirulPrincipal
		self._aplica = aplica_ or aplica
		self._zavor = threading.Lock()
		self._generatie = 0
		self._inceput = None
		self._scrie = False
		self._actualizeaza_sec = True
		self._pune(NIMIC)

	def _pune(self, stare, rezultat=None, mesaj="", scris=None, mesaj_scris=""):
		self._stare = stare
		self._rezultat = rezultat
		self._mesaj = mesaj
		self._scris = scris
		self._mesajScris = mesaj_scris
		self._semn = semn(rezultat) if rezultat is not None else ""
		# orasul din tabel pe care se deschide lista (o singura data, cand se afla locul)
		self._lista = pentruLista(rezultat) if rezultat is not None else ("", "")
		self._cand = self._ceas() if rezultat is not None else None

	def porneste(self, scrie=False, actualizeaza_sec=True):
		"""True: o cautare a pornit (sau era deja in curs). False: receptorul nu are ruta spre internet, deci nu pleaca
		nicio cerere; stare() spune de ce. Cu `scrie`, locul gasit devine locul antenei fara intrebare."""
		with self._zavor:
			if self._stare == LUCREAZA:
				self._scrie = self._scrie or scrie
				return True
		if not self._retea():
			with self._zavor:
				self._generatie += 1
				self._pune(FARA_RETEA, mesaj=_t(MESAJ_FARA_RETEA))
			return False
		with self._zavor:
			self._generatie += 1
			generatie = self._generatie
			self._scrie = scrie
			self._actualizeaza_sec = actualizeaza_sec
			self._pune(LUCREAZA, mesaj=_t(CAUT))
			self._inceput = self._ceas()
		self._fir(lambda: self._lucreaza(generatie))
		return True

	def _lucreaza(self, generatie):
		try:
			stare, x = self._cauta()
		except Exception as e:
			jurnal("cautarea: %r" % (e,))
			stare, x = EROARE, _t(MESAJ_NU_RASPUNDE)
		with self._zavor:
			if generatie != self._generatie:
				return
			scrie, actualizeaza_sec = self._scrie, self._actualizeaza_sec
		if stare == GASIT and scrie:
			self._peFir(lambda: self._scrieSiPune(generatie, x, actualizeaza_sec))
			return
		with self._zavor:
			if generatie != self._generatie:
				return
			if stare == GASIT:
				self._pune(GASIT, rezultat=x)
			else:
				self._pune(EROARE, mesaj=x)

	def _scrieSiPune(self, generatie, rez, actualizeaza_sec):
		# omul a ales singur un oras sau coordonatele cat se cauta (raspunsul poate veni dupa ~12 s): alegerea lui ramane
		try:
			automat = _locul().automat()
		except Exception:
			automat = False
		if not automat:
			jurnal("locul gasit nu se scrie: omul a ales intre timp locul")
			with self._zavor:
				if generatie == self._generatie:
					self._pune(GASIT, rezultat=rez, scris=None)
			return
		try:
			ok, text = self._aplica(rez, actualizeaza_sec=actualizeaza_sec)
		except Exception as e:
			jurnal("scrierea locului gasit: %r" % (e,))
			ok, text = False, _t(MESAJ_NU_RASPUNDE)
		with self._zavor:
			if generatie != self._generatie:
				return
			self._pune(GASIT, rezultat=rez, scris=bool(ok), mesaj_scris=text or "")

	def stare(self):
		"""{"stare", "mesaj", "semn", "gasit": {...} sau None, "scris": True/False/None, "mesaj_scris"}: o copie, buna de
		dat ecranului si paginii. O cautare care trece de LIMITA_S devine aici eroare ("serverul nu a raspuns"); firul ei
		nu mai schimba nimic."""
		with self._zavor:
			if self._stare == LUCREAZA and self._inceput is not None and \
					not 0 <= self._ceas() - self._inceput <= LIMITA_S:
				jurnal("cautarea a trecut de %d s" % LIMITA_S)
				self._generatie += 1
				self._pune(EROARE, mesaj=_t(MESAJ_NU_RASPUNDE))
			st, rez, mesaj, s, lista = self._stare, self._rezultat, self._mesaj, self._semn, self._lista
			scris, mesaj_scris = self._scris, self._mesajScris
		d = {"stare": st, "mesaj": mesaj, "semn": s, "gasit": None, "scris": scris, "mesaj_scris": mesaj_scris}
		if st == GASIT and rez is not None:
			# tara_lista si oras_lista: unde se deschide lista (orasul gasit poate lipsi din tabel)
			d["gasit"] = {"oras": rez["oras"], "tara": rez["tara"], "tara_nume": numeTara(rez),
				"lat": rez["lat_mii"] / 1000.0, "lon": rez["lon_mii"] / 1000.0, "coordonate": textCoordonate(rez),
				"sursa": textSursa(rez), "loc": textLoc(rez), "din_tabel": bool(rez.get("din_tabel")),
				"tara_lista": lista[0], "oras_lista": lista[1]}
		return d

	def foloseste(self, semn_=None, actualizeaza_sec=True):
		"""Locul gasit devine locul antenei (HdsLocul.seteaza, sursa internet). Cu `semn_` (pagina web de pana la 0.8.0),
		numai daca e chiar locul aratat si nu a trecut VALABIL_S. -> (True, "") sau (False, motivul)."""
		with self._zavor:
			st, rez, s, cand = self._stare, self._rezultat, self._semn, self._cand
		if st != GASIT or rez is None or (semn_ is not None and semn_ != s):
			return False, _t(MESAJ_EXPIRAT)
		acum = self._ceas()
		if cand is not None and not 0 <= acum - cand <= VALABIL_S:
			return False, _t(MESAJ_EXPIRAT)
		_locul().alegeInternet()
		return aplica(rez, actualizeaza_sec=actualizeaza_sec)


CAUTARE = Cautare()


# ---------------------------------------------------------------- locul singur, la pornire (LOC2)

# de cate ori si la ce interval se mai incearca scrierea cand antena se roteste sau merge o inregistrare
REINCERCARI = 10
PAUZA_REINCERCARE_S = 120.0
# cat asteapta firul pornirii raspunsul fusului orar (HdsFusTara: pana la TERMEN_S, 180 s, plus asteptarea limbii)
ASTEPTARE_FUS_S = 300.0

_PORNIRE = {"facut": False, "dupa_ntp": False, "lucreaza": False}
_ZAVOR_PORNIRE = threading.Lock()


def _fus():
	from Components import HdsFusTara
	return HdsFusTara


def _maiTarziu(secunde, functie):
	from twisted.internet import reactor
	reactor.callLater(secunde, functie)


def _raspunsPornire(fus=None, ceas=None, dormi=None):
	"""(cod, corp) pentru locul de la pornire: raspunsul primit de fusul orar (o singura cerere pe pornire), altfel o
	cerere a noastra (HdsFusTara.cere: asteapta ruta, reincearca la erorile de retea)"""
	F = fus or _fus()
	ceas = ceas or time.monotonic
	dormi = dormi or time.sleep
	inceput = ceas()
	try:
		while F.stare().get("stare") == F.LUCREAZA and ceas() - inceput < ASTEPTARE_FUS_S:
			dormi(1.0)
		r = F.stare().get("raspuns")
	except Exception:
		r = None
	if r and r[0] == 200:
		return r
	return F.cere()


def _dinRaspuns(raspuns):
	"""(cod, corp) -> rezultatul potrivit cu tabelul sau None"""
	cod, corp = raspuns
	if cod != 200:
		jurnal("locul la pornire: serverul a raspuns %s" % (corp if cod is None else "HTTP %s" % cod))
		return None
	try:
		return potrivesteTabel(verifica(corp))
	except ValueError as e:
		jurnal("locul la pornire: raspuns respins: %s" % e)
		return None


def _scrieLaPornire(rez, ramase, L=None, mai_tarziu=None):
	"""pe firul enigma2: locul gasit, daca locul e tot cel dupa internet; cat antena se roteste sau merge o
	inregistrare, inca o incercare peste PAUZA_REINCERCARE_S (de cel mult REINCERCARI ori)"""
	L = L or _locul()
	if not L.automat():
		jurnal("locul l-a ales omul intre timp: ramane")
		return False
	ok, text = aplica(rez, L=L)
	if ok:
		return True
	jurnal("locul dupa internet nu s-a scris acum (%s)" % text)
	if ramase > 0:
		(mai_tarziu or _maiTarziu)(PAUZA_REINCERCARE_S, lambda: _scrieLaPornire(rez, ramase - 1, L, mai_tarziu))
	return False


def _lucreazaPornire(raspuns_=None, pe_fir=None, mai_tarziu=None):
	try:
		rez = _dinRaspuns((raspuns_ or _raspunsPornire)())
	except Exception as e:
		jurnal("locul la pornire: %r" % (e,))
		rez = None
	finally:
		with _ZAVOR_PORNIRE:
			_PORNIRE["lucreaza"] = False
	if rez is None:
		return False
	with _ZAVOR_PORNIRE:
		_PORNIRE["facut"] = True
	(pe_fir or _peFirulPrincipal)(lambda: _scrieLaPornire(rez, REINCERCARI, mai_tarziu=mai_tarziu))
	return True


def porneste(fir=None, L=None, **k):
	"""Aflarea singura, pe un fir (nu asteapta). Nimic cand omul a ales locul sau cand firul lucreaza deja. Cu VPN-ul
	receptorului pornit cererea iese direct (ocolesteVpn)."""
	L = L or _locul()
	if not L.automat():
		jurnal("locul l-a ales omul: nu se cauta dupa internet")
		return False
	with _ZAVOR_PORNIRE:
		if _PORNIRE["lucreaza"]:
			return False
		_PORNIRE["lucreaza"] = True
	(fir or _firDaemon)(lambda: _lucreazaPornire(**k))
	return True


def laPornire(**k):
	"""Din Components/SetupDevices.py, dupa fusul orar (HdsFusTara.laPornire). Nu arunca."""
	try:
		return porneste(**k)
	except Exception as e:
		jurnal("aflarea locului la pornire nu a pornit: %r" % (e,))
		return False


def dupaNtp(**k):
	"""Din Components/HdsCeas.py, dupa un NTP reusit: inca o incercare, o data pe pornire, daca locul nu s-a aflat inca
	(internetul vine uneori abia dupa o cadere). Nu arunca."""
	try:
		with _ZAVOR_PORNIRE:
			if _PORNIRE["facut"] or _PORNIRE["dupa_ntp"] or _PORNIRE["lucreaza"]:
				return False
			_PORNIRE["dupa_ntp"] = True
		return porneste(**k)
	except Exception as e:
		jurnal("aflarea locului dupa NTP: %r" % (e,))
		return False
