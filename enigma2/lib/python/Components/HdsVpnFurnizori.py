# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsVpnFurnizori.py: "alege furnizorul, scrie contul, alege tara", fara fisiere, pentru furnizorii VPN care au o cale
# OFICIALA si documentata. O singura logica pentru ecranul de pe televizor (Screens/HdsVpnFurnizor.py) si pentru pagina
# web /vpn-furnizor (Plugins/Extensions/HdsWebControl/vpn_furnizori_web.py). Profilurile facute aici merg mai departe
# prin functiile publice din Components/HdsVpn.py (importa, salveazaCont, schimba, pornesteVpn): aceeasi lista alba,
# aceleasi fisiere 0600, aceeasi pornire. Fisierul nu schimba nimic in HdsVpn.py.
#
# Furnizorii cu cale oficiala (verificati pe 11.11.2026, sursele in lucru-sesiune/paralel-1111b/STADIU-V3-*):
#   mullvad    WireGuard. Pagina lor "WireGuard on Linux terminal (advanced)" si scriptul lor mullvad-wg.sh: lista
#              publica a serverelor (api.mullvad.net/public/relays/wireguard/v1/) si inregistrarea cheii publice cu
#              numarul contului (POST api.mullvad.net/wg, in corpul cererii). Cheia privata se face PE receptor
#              (X25519 de mai jos) si nu pleaca nicaieri; aceeasi cheie merge la toate serverele, deci se inregistreaza
#              o singura data (contul are un numar limitat de aparate). Numarul contului nu se pastreaza.
#   nordvpn    OpenVPN cu datele de serviciu (Service credentials, nu e-mailul). Nord nu are o lista de servere
#              documentata; oficiale sunt arhiva ovpn.zip (ghidul lor de Linux, 68 MB) si adresa fisierului unui server
#              (ghidul lor de OpenWrt). Se citeste numai CUPRINSUL arhivei (doua cereri HTTP Range, ~3,3 MB), de unde
#              ies numele serverelor pe tara, apoi se descarca fisierele a cateva servere din tara aleasa.
#   pia        Private Internet Access, OpenVPN cu numele (p...) si parola din e-mailul de la cumparare. Arhiva oficiala
#              din articolul lor "Linux - Set Up a Manual OpenVPN Connection Through Terminal" (166 de regiuni).
#              Directiva disable-occ din fisierele lor nu e in lista alba din HdsVpn.py; se scoate inainte de import
#              (opreste numai o verificare de potrivire a optiunilor, legatura merge si fara ea).
#   surfshark  OpenVPN cu datele de serviciu (Manual setup > Credentials). Arhiva oficiala din articolul lor "How to
#              set up manual OpenVPN connection using Linux Terminal".
#   ipvanish   OpenVPN cu numele si parola contului IPVanish. Directorul PUBLIC configs.ipvanish.com/openvpn/v2.6.0-0/
#              din ghidurile lor de Linux ("OpenVPN: Linux Command-Line", "OpenVPN setup in Ubuntu"; site-ul lor
#              refuza uneltele noastre, ghidurile le-a citit coordonatorul in Chrome pe 11.11.2026): lista serverelor
#              din pagina directorului, cateva servere din tara aleasa, ca.ipvanish.com.crt alaturi cand lipseste din
#              fisier.
# Calea cu jeton a PIA (WireGuard, addKey) nu se foloseste: jetonul tine 24 de ore si addKey il cere in adresa.
#
# Furnizorii fara cale oficiala pentru aparate terte (Proton VPN, ExpressVPN, CyberGhost, Windscribe, HMA) au numai
# textul de ajutor (de unde iei fisierele si datele de serviciu, dupa pagina lor), iar fisierele se importa din ecranul
# VPN. CyberGhost: configuratia se face in contul online (VPN, Configure Device, protocol, tara, grup, Save, View).
#
# Ce primeste omul: alege furnizorul, scrie contul (o singura data; cel salvat nu se mai cere), alege tara. Receptorul
# descarca, importa cate un server pe oras (Nord si IPVanish: cateva servere din tara), alege primul, instaleaza
# programele daca lipsesc si porneste VPN-ul (cu VPN-ul deja pornit pe alt server il reporneste).
#
# Datele omului (numele, parola, numarul contului, cheia privata) nu intra in jurnal (_jurnal le ascunde, apoi
# HdsVpn.jurnal), nu intra in nicio adresa (Mullvad: in corpul cererii POST) si nu ajung in copia setarilor: totul sta
# in HdsVpn.DOSAR (/etc/hdsatelit-vpn, 0700), fisierele 0600. Numai HTTPS, cu certificatul verificat
# (ssl.create_default_context), fara proxy, redirectionarile numai spre https; raspunsurile au marime maxima.
#
# FIRUL: functiile cu retea merg numai prin HdsVpn.LUCRARI (un fir deodata, comun televizorului si paginii web);
# ecranul si pagina citesc stare(), care nu face nicio cerere. Dupa o configurare reusita, _dupa() asteapta sfarsitul
# lucrarii si aplica (schimba, instalarea programelor, pornirea VPN-ului) pe un fir mic al lui. Fisierul nu importa
# nimic din enigma2 la incarcare: probele de pe PC dau V (modulul HdsVpn), DESCARCATOR si SINCRON.

import base64
import ipaddress
import json
import os
import random
import re
import struct
import threading
import time
import zipfile
import io

# probele de pe PC: modulul HdsVpn, cine face cererile HTTPS (url, date, interval, maxim) -> (cod, octeti)
V = None
DESCARCATOR = None

MAX_DESCARCARE = 8 * 1024 * 1024
MAX_JSON = 2 * 1024 * 1024
MAX_FISIER = 65536
MAX_ORASE = 60
SERVERE_ALESE = 3
TIMP_S = 30
VALABIL_LISTA_S = 6 * 3600
VALABIL_ARHIVA_S = 3600
ASTEPTARE_LUCRARE_S = 1800

LUCRARE_TARI = "furnizor-tari"
LUCRARE_CONFIGURARE = "furnizor-configurare"

CALE_FURNIZORI = "/furnizori.json"          # sub HdsVpn.DOSAR: al cui e contul salvat (fara secrete)
CALE_MULLVAD = "/furnizor-mullvad.json"     # sub HdsVpn.DOSAR: cheia privata si adresa din tunel (0600)

ADRESA_MULLVAD_SERVERE = "https://api.mullvad.net/public/relays/wireguard/v1/"
ADRESA_MULLVAD_CHEIE = "https://api.mullvad.net/wg"
DNS_MULLVAD = "10.64.0.1"
PORT_MULLVAD = 51820
ADRESA_NORD_ARHIVA = "https://downloads.nordcdn.com/configs/archives/servers/ovpn.zip"
ADRESA_NORD_SERVER = "https://downloads.nordcdn.com/configs/files/ovpn_udp/servers/%s.nordvpn.com.udp.ovpn"
ADRESA_PIA = "https://www.privateinternetaccess.com/openvpn/openvpn.zip"
ADRESA_SURFSHARK = "https://surfshark.com/api/v1/server/configurations"
ADRESA_IPVANISH = "https://configs.ipvanish.com/openvpn/v2.6.0-0/"


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la folosire."""
	return text


def _hv():
	global V
	if V is None:
		from Components import HdsVpn
		V = HdsVpn
	return V


SINCRON = False   # probele: _dupa() aplica pe loc, fara fir


# ---------------------------------------------------------------- tarile (codul ISO, numele englezesc din fisierele
# PIA, numele in romana, tradus la afisare)

TARI = (
	("ad", "andorra", N_("Andorra")), ("ae", "united_arab_emirates", N_("Emiratele Arabe Unite")),
	("af", "afghanistan", N_("Afganistan")), ("ag", "antigua_and_barbuda", N_("Antigua și Barbuda")),
	("al", "albania", N_("Albania")), ("am", "armenia", N_("Armenia")), ("ao", "angola", N_("Angola")),
	("ar", "argentina", N_("Argentina")), ("at", "austria", N_("Austria")), ("au", "australia", N_("Australia")),
	("az", "azerbaijan", N_("Azerbaidjan")), ("ba", "bosnia_and_herzegovina", N_("Bosnia și Herțegovina")),
	("bb", "barbados", N_("Barbados")), ("bd", "bangladesh", N_("Bangladesh")), ("be", "belgium", N_("Belgia")),
	("bf", "burkina_faso", N_("Burkina Faso")), ("bg", "bulgaria", N_("Bulgaria")), ("bh", "bahrain", N_("Bahrain")),
	("bj", "benin", N_("Benin")), ("bm", "bermuda", N_("Bermude")), ("bn", "brunei", N_("Brunei")),
	("bo", "bolivia", N_("Bolivia")), ("br", "brazil", N_("Brazilia")), ("bs", "bahamas", N_("Bahamas")),
	("bt", "bhutan", N_("Bhutan")), ("bw", "botswana", N_("Botswana")), ("bz", "belize", N_("Belize")),
	("ca", "canada", N_("Canada")), ("ch", "switzerland", N_("Elveția")), ("cl", "chile", N_("Chile")),
	("cn", "china", N_("China")), ("co", "colombia", N_("Columbia")), ("cr", "costa_rica", N_("Costa Rica")),
	("cv", "cape_verde", N_("Capul Verde")), ("cy", "cyprus", N_("Cipru")), ("cz", "czech_republic", N_("Cehia")),
	("de", "germany", N_("Germania")), ("dk", "denmark", N_("Danemarca")),
	("do", "dominican_republic", N_("Republica Dominicană")), ("dz", "algeria", N_("Algeria")),
	("ec", "ecuador", N_("Ecuador")), ("ee", "estonia", N_("Estonia")), ("eg", "egypt", N_("Egipt")),
	("es", "spain", N_("Spania")), ("et", "ethiopia", N_("Etiopia")), ("fi", "finland", N_("Finlanda")),
	("fj", "fiji", N_("Fiji")), ("fr", "france", N_("Franța")), ("gb", "united_kingdom", N_("Regatul Unit")),
	("gd", "grenada", N_("Grenada")), ("ge", "georgia", N_("Georgia")), ("gh", "ghana", N_("Ghana")),
	("gi", "gibraltar", N_("Gibraltar")), ("gl", "greenland", N_("Groenlanda")), ("gm", "gambia", N_("Gambia")),
	("gq", "equatorial_guinea", N_("Guineea Ecuatorială")), ("gr", "greece", N_("Grecia")),
	("gt", "guatemala", N_("Guatemala")), ("gu", "guam", N_("Guam")), ("gy", "guyana", N_("Guyana")),
	("hk", "hong_kong", N_("Hong Kong")), ("hn", "honduras", N_("Honduras")), ("hr", "croatia", N_("Croația")),
	("ht", "haiti", N_("Haiti")),
	("hu", "hungary", N_("Ungaria")), ("id", "indonesia", N_("Indonezia")), ("ie", "ireland", N_("Irlanda")),
	("il", "israel", N_("Israel")), ("im", "isle_of_man", N_("Insula Man")), ("in", "india", N_("India")),
	("iq", "iraq", N_("Irak")), ("is", "iceland", N_("Islanda")), ("it", "italy", N_("Italia")),
	("je", "jersey", N_("Jersey")), ("jm", "jamaica", N_("Jamaica")), ("jo", "jordan", N_("Iordania")),
	("jp", "japan", N_("Japonia")), ("ke", "kenya", N_("Kenya")), ("kg", "kyrgyzstan", N_("Kârgâzstan")),
	("kh", "cambodia", N_("Cambodgia")), ("km", "comoros", N_("Comore")), ("kr", "south_korea", N_("Coreea de Sud")),
	("kw", "kuwait", N_("Kuweit")), ("ky", "cayman_islands", N_("Insulele Cayman")),
	("kz", "kazakhstan", N_("Kazahstan")), ("la", "laos", N_("Laos")), ("lb", "lebanon", N_("Liban")),
	("lc", "saint_lucia", N_("Sfânta Lucia")), ("li", "liechtenstein", N_("Liechtenstein")),
	("lk", "sri_lanka", N_("Sri Lanka")), ("lr", "liberia", N_("Liberia")), ("ls", "lesotho", N_("Lesotho")),
	("lt", "lithuania", N_("Lituania")), ("lu", "luxembourg", N_("Luxemburg")), ("lv", "latvia", N_("Letonia")),
	("ly", "libya", N_("Libia")), ("ma", "morocco", N_("Maroc")), ("mc", "monaco", N_("Monaco")),
	("md", "moldova", N_("Republica Moldova")), ("me", "montenegro", N_("Muntenegru")),
	("mg", "madagascar", N_("Madagascar")), ("mk", "north_macedonia", N_("Macedonia de Nord")),
	("mm", "myanmar", N_("Myanmar")), ("mn", "mongolia", N_("Mongolia")), ("mo", "macao", N_("Macao")),
	("mr", "mauritania", N_("Mauritania")), ("mt", "malta", N_("Malta")), ("mu", "mauritius", N_("Mauritius")),
	("mv", "maldives", N_("Maldive")), ("mw", "malawi", N_("Malawi")), ("mx", "mexico", N_("Mexic")),
	("my", "malaysia", N_("Malaysia")), ("mz", "mozambique", N_("Mozambic")), ("ng", "nigeria", N_("Nigeria")),
	("ni", "nicaragua", N_("Nicaragua")),
	("nl", "netherlands", N_("Țările de Jos")), ("no", "norway", N_("Norvegia")), ("np", "nepal", N_("Nepal")),
	("nz", "new_zealand", N_("Noua Zeelandă")), ("pa", "panama", N_("Panama")), ("pe", "peru", N_("Peru")),
	("pg", "papua_new_guinea", N_("Papua-Noua Guinee")), ("ph", "philippines", N_("Filipine")),
	("pk", "pakistan", N_("Pakistan")), ("pl", "poland", N_("Polonia")), ("pr", "puerto_rico", N_("Puerto Rico")),
	("pt", "portugal", N_("Portugalia")), ("py", "paraguay", N_("Paraguay")), ("qa", "qatar", N_("Qatar")),
	("ro", "romania", N_("România")), ("rs", "serbia", N_("Serbia")), ("sa", "saudi_arabia", N_("Arabia Saudită")),
	("sc", "seychelles", N_("Seychelles")), ("se", "sweden", N_("Suedia")), ("sg", "singapore", N_("Singapore")),
	("si", "slovenia", N_("Slovenia")), ("sk", "slovakia", N_("Slovacia")), ("sl", "sierra_leone", N_("Sierra Leone")),
	("sm", "san_marino", N_("San Marino")), ("sn", "senegal", N_("Senegal")), ("so", "somalia", N_("Somalia")),
	("sr", "suriname", N_("Suriname")), ("sv", "el_salvador", N_("El Salvador")), ("td", "chad", N_("Ciad")),
	("th", "thailand", N_("Thailanda")), ("tj", "tajikistan", N_("Tadjikistan")), ("tn", "tunisia", N_("Tunisia")),
	("tr", "turkey", N_("Turcia")), ("tt", "trinidad_and_tobago", N_("Trinidad și Tobago")),
	("tw", "taiwan", N_("Taiwan")), ("tz", "tanzania", N_("Tanzania")), ("ua", "ukraine", N_("Ucraina")),
	("us", "united_states", N_("Statele Unite")), ("uy", "uruguay", N_("Uruguay")),
	("uz", "uzbekistan", N_("Uzbekistan")), ("ve", "venezuela", N_("Venezuela")), ("vn", "vietnam", N_("Vietnam")),
	("ws", "samoa", N_("Samoa")), ("ye", "yemen", N_("Yemen")), ("za", "south_africa", N_("Africa de Sud")),
	("zm", "zambia", N_("Zambia")),
)
_TARA = dict((c, ro) for c, _en, ro in TARI)
_ENGLEZA = dict((en, c) for c, en, _ro in TARI)
_COD = re.compile(r"^[a-z]{2}\Z")


def codTara(cod):
	"""Codul ISO din codul furnizorului (Nord si Surfshark scriu uk pentru Regatul Unit)."""
	cod = (cod or "").lower()
	return "gb" if cod == "uk" else cod


def numeTara(cod):
	"""Numele tarii in limba receptorului; un cod necunoscut ramane cu majuscule."""
	ro = _TARA.get(cod)
	return _(ro) if ro else (cod or "?").upper()


# ---------------------------------------------------------------- X25519 (RFC 7748), pentru cheia WireGuard

_P = 2 ** 255 - 19


def _x25519(scalar, u):
	k = bytearray(scalar)
	k[0] &= 248
	k[31] &= 127
	k[31] |= 64
	k = int.from_bytes(bytes(k), "little")
	uu = bytearray(u)
	uu[31] &= 127
	x1 = int.from_bytes(bytes(uu), "little") % _P
	x2, z2, x3, z3, schimb = 1, 0, x1, 1, 0
	for t in range(254, -1, -1):
		bit = (k >> t) & 1
		schimb ^= bit
		if schimb:
			x2, x3, z2, z3 = x3, x2, z3, z2
		schimb = bit
		a = x2 + z2
		aa = a * a % _P
		b = x2 - z2
		bb = b * b % _P
		e = aa - bb
		c = x3 + z3
		d = x3 - z3
		da = d * a % _P
		cb = c * b % _P
		x3 = (da + cb) * (da + cb) % _P
		z3 = x1 * (da - cb) * (da - cb) % _P
		x2 = aa * bb % _P
		z2 = e * (aa + 121665 * e) % _P
	if schimb:
		x2, x3, z2, z3 = x3, x2, z3, z2
	return (x2 * pow(z2, _P - 2, _P) % _P).to_bytes(32, "little")


def cheiePublica(privata_b64):
	return base64.b64encode(_x25519(base64.b64decode(privata_b64), b"\x09" + b"\x00" * 31)).decode("ascii")


def cheieNoua():
	"""Cheia privata WireGuard, ca `wg genkey`: 32 de octeti din os.urandom, potriviti (clamped), in base64."""
	k = bytearray(os.urandom(32))
	k[0] &= 248
	k[31] &= 127
	k[31] |= 64
	return base64.b64encode(bytes(k)).decode("ascii")


# ---------------------------------------------------------------- jurnalul si fisierele noastre

_SECRETE = set()


def _jurnal(text):
	text = "%s" % (text,)
	for s in sorted(_SECRETE, key=len, reverse=True):
		if s and len(s) >= 3:
			text = text.replace(s, "***")
	_hv().jurnal("furnizori: " + text)


def _cale(rel):
	v = _hv()
	return v.RADACINA + v.DOSAR + rel


def _citesteJson(rel):
	try:
		with open(_cale(rel), "rb") as f:
			return json.loads(f.read(MAX_FISIER).decode("utf-8", "replace"))
	except (OSError, IOError, ValueError):
		return None


def _scrieJson(rel, obiect):
	"""Scris intreg sau deloc (fisier .nou, fsync, os.replace), 0600, in DOSAR (0700)."""
	v = _hv()
	dosar = v.RADACINA + v.DOSAR
	if not os.path.isdir(dosar):
		os.makedirs(dosar, 0o700)
	tinta = _cale(rel)
	tmp = tinta + ".nou"
	date = json.dumps(obiect, ensure_ascii=False, sort_keys=True).encode("utf-8")
	fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
	try:
		os.write(fd, date)
		os.fsync(fd)
	finally:
		os.close(fd)
	os.chmod(tmp, 0o600)
	os.replace(tmp, tinta)


def _sterge(rel):
	try:
		os.remove(_cale(rel))
		return True
	except OSError:
		return False


def _semnCont():
	"""Semnul fisierului cu numele si parola din HdsVpn (marimea, momentul scrierii, inodul), fara continutul lui:
	daca omul scrie alt cont din ecranul VPN, semnul se schimba si contul nu mai trece drept al furnizorului de aici."""
	v = _hv()
	try:
		st = os.stat(v.RADACINA + v.CALE_CONT)
	except OSError:
		return None
	return [st.st_size, st.st_mtime_ns, st.st_ino]


def contulEsteAl():
	"""Furnizorul pentru care s-au scris numele si parola din ecranul acesta (numai daca HdsVpn le mai are,
	neschimbate)."""
	date = _citesteJson(CALE_FURNIZORI) or {}
	f = date.get("cont")
	if not isinstance(f, str) or not _hv().areCont():
		return ""
	semn = _semnCont()
	return f if (semn is not None and date.get("semn") == semn) else ""


def _contAl(furnizor):
	date = _citesteJson(CALE_FURNIZORI) or {}
	date["cont"] = furnizor
	date["semn"] = _semnCont()
	_scrieJson(CALE_FURNIZORI, date)


# ---------------------------------------------------------------- cererile HTTPS

class EroareRetea(Exception):
	pass


def _numaiHttps():
	from urllib.request import HTTPRedirectHandler

	class NumaiHttps(HTTPRedirectHandler):
		def redirect_request(self, req, fp, code, msg, headers, newurl):
			if not str(newurl).lower().startswith("https://"):
				return None
			return HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)
	return NumaiHttps()


def _descarca(url, date=None, interval=None, maxim=MAX_DESCARCARE):
	"""(codul HTTP, octetii raspunsului). `date`: dict trimis in corpul unei cereri POST (niciodata in adresa);
	`interval`: antetul Range ("-65557", "100-199"). Numai https, certificat verificat, fara proxy."""
	if not url.startswith("https://"):
		raise EroareRetea("numai https")
	if DESCARCATOR is not None:
		return DESCARCATOR(url, date, interval, maxim)
	import ssl
	from urllib.error import HTTPError
	from urllib.parse import urlencode
	from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener
	antet = {"User-Agent": _hv().UA}
	if interval:
		antet["Range"] = "bytes=%s" % interval
	corp = urlencode(date).encode("ascii") if date else None
	if corp is not None:
		antet["Content-Type"] = "application/x-www-form-urlencoded"
	cerere = Request(url, data=corp, headers=antet)
	deschizator = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _numaiHttps())
	try:
		r = deschizator.open(cerere, timeout=TIMP_S)
		cod = r.getcode()
		continut = r.read(maxim + 1)
	except HTTPError as eroare:
		cod = eroare.code
		try:
			continut = eroare.read(4096)
		except Exception:
			continut = b""
	if len(continut) > maxim:
		raise EroareRetea("raspuns prea mare")
	return cod, continut


def _mesajRetea(eroare, furnizor):
	try:
		from Components import HdsCeasHttps
		ceas = HdsCeasHttps.mesaj(eroare)
	except Exception:
		ceas = None
	if ceas:
		return ceas
	return _("Nu am putut vorbi cu %s. Verifică legătura la internet și încearcă din nou.") % furnizor


def _cere(url, furnizor, coduri=(200,), **k):
	cod, continut = _descarca(url, **k)
	if cod not in coduri:
		_jurnal("%s: HTTP %s la %s" % (furnizor, cod, url))
		raise EroareRetea(_("%s a răspuns neașteptat (HTTP %s).") % (furnizor, cod))
	return continut


# ---------------------------------------------------------------- furnizorii

_GAZDA = re.compile(r"^(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9\-]{0,62}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,62}[A-Za-z0-9])?)+\Z")
_CHEIE_WG = re.compile(r"^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=\Z")
_ORAS = re.compile(r"[^\w .'\-]", re.U)


class Furnizor(object):
	"""Ce cere omului, de unde ia lista tarilor si cum face fisierele pentru HdsVpn.importa."""
	id = ""
	titlu = ""
	fel = "openvpn"
	cont = "nume_parola"       # sau "numar"

	def tari(self):
		"""{cod: [oras, ...]} (lucrare cu retea)"""
		raise NotImplementedError

	def fisiere(self, cod, cont):
		"""[(numele fisierului, octeti)] pentru tara `cod` (lucrare cu retea)"""
		raise NotImplementedError

	def numeFisier(self, cod, oras, extensie):
		parti = [self.titlu.split(" ")[0], numeTara(cod)] + ([oras] if oras else [])
		return ".".join(re.sub(r"[._\-/\\]+", " ", p).strip() for p in parti) + extensie


class _ArhivaOvpn(Furnizor):
	"""Furnizorii cu arhiva oficiala a fisierelor OpenVPN (un fisier pe loc): lista tarilor din numele fisierelor."""
	adresa = ""
	_cache = None

	def _arhiva(self):
		c = type(self)._cache
		if c and time.time() - c[0] < VALABIL_ARHIVA_S:
			return c[1]
		date = _cere(self.adresa, self.titlu)
		try:
			z = zipfile.ZipFile(io.BytesIO(date))
		except (zipfile.BadZipFile, ValueError):
			raise EroareRetea(_("Arhiva de la %s nu se poate deschide.") % self.titlu)
		type(self)._cache = (time.time(), z)
		return z

	def loc(self, nume):
		"""(cod, oras) din numele fisierului sau None"""
		raise NotImplementedError

	def _locuri(self):
		z = self._arhiva()
		rez = {}
		for info in z.infolist():
			n = info.filename.replace("\\", "/").rsplit("/", 1)[-1]
			if info.is_dir() or info.file_size > MAX_FISIER or not n.lower().endswith(".ovpn"):
				continue
			l = self.loc(n)
			if l:
				rez.setdefault(l[0], []).append((l[1], info.filename))
		for cod in rez:
			rez[cod].sort()
		return rez

	def tari(self):
		return dict((cod, [o for o, _n in l]) for cod, l in self._locuri().items())

	def curata(self, text):
		return text

	def fisiere(self, cod, cont):
		z = self._arhiva()
		rez = []
		for oras, nume in self._locuri().get(cod, [])[:MAX_ORASE]:
			text = z.read(nume).decode("utf-8", "replace")
			rez.append((self.numeFisier(cod, oras, ".ovpn"), self.curata(text).encode("utf-8")))
		return rez


class Surfshark(_ArhivaOvpn):
	id = "surfshark"
	titlu = "Surfshark"
	adresa = ADRESA_SURFSHARK
	_NUME = re.compile(r"^([a-z]{2})-([a-z0-9]{2,8})\.prod\.surfshark\.com_udp\.ovpn\Z")

	def loc(self, nume):
		m = self._NUME.match(nume)
		return (codTara(m.group(1)), m.group(2).upper()) if m else None


class Pia(_ArhivaOvpn):
	id = "pia"
	titlu = "PIA (Private Internet Access)"
	adresa = ADRESA_PIA
	_NUME = re.compile(r"^([a-z0-9_]{2,60})\.ovpn\Z")

	def loc(self, nume):
		m = self._NUME.match(nume.lower())
		if not m:
			return None
		baza = m.group(1)
		if re.match(r"^[a-z]{2}_", baza):
			cod, rest = codTara(baza[:2]), baza[3:]
		else:
			cod, rest = "", ""
			for en in sorted(_ENGLEZA, key=len, reverse=True):
				if baza == en or baza.startswith(en + "_"):
					cod, rest = _ENGLEZA[en], baza[len(en) + 1:]
					break
			if not cod:
				return None
		return cod, " ".join(x.capitalize() for x in rest.split("_") if x)

	def curata(self, text):
		# disable-occ: nu e in lista alba din HdsVpn.py; opreste numai verificarea potrivirii optiunilor
		return "\n".join(r for r in text.split("\n") if r.strip().lower() != "disable-occ")


class Nordvpn(Furnizor):
	id = "nordvpn"
	titlu = "NordVPN"
	_cache = None
	_NUME = re.compile(r"^ovpn_udp/([a-z]{2})([0-9]{1,5})\.nordvpn\.com\.udp\.ovpn\Z")

	def _servere(self):
		"""{cod ISO: [numele serverelor]} din cuprinsul arhivei oficiale (fara s-o descarce intreaga)."""
		c = type(self)._cache
		if c and time.time() - c[0] < VALABIL_LISTA_S:
			return c[1]
		coada = _cere(ADRESA_NORD_ARHIVA, self.titlu, coduri=(206,), interval="-65557", maxim=65557)
		i = coada.rfind(b"PK\x05\x06")
		if i < 0 or len(coada) < i + 22:
			raise EroareRetea(_("Lista serverelor %s nu se poate citi.") % self.titlu)
		_s, _d, _cd, _n, total, marime, inceput, _l = struct.unpack("<IHHHHIIH", coada[i:i + 22])
		if total == 0xFFFF or marime == 0xFFFFFFFF or inceput == 0xFFFFFFFF or marime > MAX_DESCARCARE:
			raise EroareRetea(_("Lista serverelor %s nu se poate citi.") % self.titlu)
		cd = _cere(ADRESA_NORD_ARHIVA, self.titlu, coduri=(206,), interval="%d-%d" % (inceput, inceput + marime - 1),
			maxim=marime)
		rez = {}
		p = 0
		while p + 46 <= len(cd) and cd[p:p + 4] == b"PK\x01\x02":
			ln, le, lc = struct.unpack("<HHH", cd[p + 28:p + 34])
			nume = cd[p + 46:p + 46 + ln].decode("utf-8", "replace")
			p += 46 + ln + le + lc
			m = self._NUME.match(nume)
			if m:
				rez.setdefault(codTara(m.group(1)), []).append(m.group(1) + m.group(2))
		if not rez:
			raise EroareRetea(_("Lista serverelor %s nu se poate citi.") % self.titlu)
		type(self)._cache = (time.time(), rez)
		return rez

	def tari(self):
		return dict((cod, l) for cod, l in self._servere().items())

	def fisiere(self, cod, cont):
		servere = list(self._servere().get(cod, []))
		alese = _alegeServere(self.id, servere, r"\s([a-z]{2}[0-9]{1,5})(?: \(UDP\))?\Z", lambda m: m.group(1))
		rez = []
		for s in sorted(alese, key=lambda x: (len(x), x)):
			text = _cere(ADRESA_NORD_SERVER % s, self.titlu, maxim=MAX_FISIER)
			rez.append((self.numeFisier(cod, s, ".ovpn"), text))
		return rez


def _alegeServere(fid, servere, tipar, cheie):
	"""Cel mult SERVERE_ALESE servere din `servere`: intai cele ale tarii puse deja (recunoscute in titluri cu `tipar`;
	`cheie(potrivire)` da numele serverului), ca a doua alegere a tarii sa nu adune altele; altfel la intamplare."""
	puse = []
	for p in _hv().profiluriGrup(grupPentru(fid)):
		m = re.search(tipar, p.get("titlu", ""))
		if m and cheie(m) in servere and cheie(m) not in puse:
			puse.append(cheie(m))
	return puse[:SERVERE_ALESE] or random.sample(servere, min(SERVERE_ALESE, len(servere)))


class Ipvanish(Furnizor):
	"""IPVanish: directorul PUBLIC al fisierelor OpenVPN (ghidurile lor de Linux de pe support.ipvanish.com, citite de
	coordonator in Chrome pe 11.11.2026: "OpenVPN: Linux Command-Line" si "OpenVPN setup in Ubuntu"). Lista serverelor
	vine din pagina directorului (un fisier pe server, ipvanish-<TARA>-<Oras>-<cod>-<nr>.ovpn), fara arhiva intreaga;
	se descarca fisierele a cateva servere din tara aleasa; ca.ipvanish.com.crt se adauga numai daca un fisier nu are
	certificatul in el. Contul: numele si parola contului IPVanish."""
	id = "ipvanish"
	titlu = "IPVanish"
	_cache = None
	_ca = None
	_NUME = re.compile(r"^ipvanish-([A-Z]{2})-([A-Za-z0-9.\-]{1,80}?)-([a-z]{3})-([a-z][0-9]{2,4})\.ovpn\Z")
	_HREF = re.compile(r'href="(?:\./)?(ipvanish-[A-Za-z0-9.\-]{1,120}\.ovpn)"')

	def _servere(self):
		"""{cod ISO: [numele fisierelor]} din pagina directorului public."""
		c = type(self)._cache
		if c and time.time() - c[0] < VALABIL_LISTA_S:
			return c[1]
		html = _cere(ADRESA_IPVANISH, self.titlu, maxim=MAX_DESCARCARE).decode("utf-8", "replace")
		rez = {}
		for nume in self._HREF.findall(html):
			m = self._NUME.match(nume)
			if m:
				l = rez.setdefault(codTara(m.group(1).lower()), [])
				if nume not in l:
					l.append(nume)
		if not rez:
			raise EroareRetea(_("Lista serverelor %s nu se poate citi.") % self.titlu)
		type(self)._cache = (time.time(), rez)
		return rez

	def tari(self):
		return dict((cod, l) for cod, l in self._servere().items())

	@classmethod
	def descriere(cls, nume):
		"""(orasul, serverul) din numele fisierului: ipvanish-RO-Bucharest-otp-a01.ovpn -> ("Bucharest", "otp-a01")."""
		m = cls._NUME.match(nume)
		return re.sub(r"\s+", " ", m.group(2).replace("-", " ")).strip(), "%s-%s" % (m.group(3), m.group(4))

	def _certificat(self):
		if type(self)._ca is None:
			ca = _cere(ADRESA_IPVANISH + "ca.ipvanish.com.crt", self.titlu, maxim=MAX_FISIER)
			if b"-----BEGIN CERTIFICATE-----" not in ca:
				raise EroareRetea(_("Certificatul %s nu se poate citi.") % self.titlu)
			type(self)._ca = ca
		return type(self)._ca

	def fisiere(self, cod, cont):
		servere = list(self._servere().get(cod, []))
		dupa_server = dict((self.descriere(n)[1], n) for n in servere)
		alese = _alegeServere(self.id, list(dupa_server), r"\s([a-z]{3}) ([a-z][0-9]{2,4})(?: \(UDP\))?\Z",
			lambda m: "%s-%s" % (m.group(1), m.group(2)))
		rez = []
		cu_ca = False
		for s in sorted(alese):
			nume = dupa_server[s]
			text = _cere(ADRESA_IPVANISH + nume, self.titlu, maxim=MAX_FISIER)
			oras, server = self.descriere(nume)
			cu_ca = cu_ca or b"<ca>" not in text
			rez.append((self.numeFisier(cod, "%s %s" % (oras, server), ".ovpn"), text))
		if cu_ca:
			rez.append(("ca.ipvanish.com.crt", self._certificat()))
		return rez


class Mullvad(Furnizor):
	id = "mullvad"
	titlu = "Mullvad"
	fel = "wireguard"
	cont = "numar"
	_cache = None

	def _relee(self):
		c = type(self)._cache
		if c and time.time() - c[0] < VALABIL_LISTA_S:
			return c[1]
		try:
			date = json.loads(_cere(ADRESA_MULLVAD_SERVERE, self.titlu, maxim=MAX_JSON).decode("utf-8"))
		except ValueError:
			raise EroareRetea(_("Lista serverelor %s nu se poate citi.") % self.titlu)
		rez = {}
		for tara in (date.get("countries") or []) if isinstance(date, dict) else []:
			cod = codTara(str(tara.get("code") or ""))
			if not _COD.match(cod):
				continue
			for oras in tara.get("cities") or []:
				nume = _ORAS.sub("", str(oras.get("name") or ""))[:40].strip()
				bune = []
				for r in oras.get("relays") or []:
					try:
						ip = str(ipaddress.IPv4Address(str(r.get("ipv4_addr_in"))))
					except (ipaddress.AddressValueError, ValueError):
						continue
					cheie = str(r.get("public_key") or "")
					gazda = str(r.get("hostname") or "")
					if _CHEIE_WG.match(cheie) and re.match(r"^[a-z0-9\-]{1,40}\Z", gazda):
						bune.append((gazda, ip, cheie))
				if nume and bune:
					rez.setdefault(cod, []).append((nume, sorted(bune)[0]))
		if not rez:
			raise EroareRetea(_("Lista serverelor %s nu se poate citi.") % self.titlu)
		for cod in rez:
			rez[cod].sort()
		type(self)._cache = (time.time(), rez)
		return rez

	def tari(self):
		return dict((cod, [o for o, _r in l]) for cod, l in self._relee().items())

	@staticmethod
	def numarBun(numar):
		n = re.sub(r"[\s\-]", "", numar or "")
		return n if re.match(r"^[0-9]{16}\Z", n) else ""

	def cheia(self, numar):
		"""(cheia privata, adresa din tunel): cea inregistrata deja, altfel una noua, inregistrata cu numarul contului."""
		date = _citesteJson(CALE_MULLVAD) or {}
		if _CHEIE_WG.match(str(date.get("cheie") or "")) and adresaMullvadBuna(str(date.get("adresa") or "")):
			_SECRETE.add(date["cheie"])
			return date["cheie"], date["adresa"]
		n = self.numarBun(numar)
		if not n:
			raise EroareRetea(_("Scrie numărul contului Mullvad (16 cifre)."))
		_SECRETE.add(n)
		privata = cheieNoua()
		_SECRETE.add(privata)
		cod, continut = _descarca(ADRESA_MULLVAD_CHEIE, date={"account": n, "pubkey": cheiePublica(privata)},
			maxim=4096)
		text = continut.decode("utf-8", "replace").strip()
		if cod != 200 or not adresaMullvadBuna(text):
			motiv = re.sub(r"[^A-Za-z0-9 .,:_\-]", "", text)[:120]
			_jurnal("mullvad: cheia nu s-a inregistrat (HTTP %s) %s" % (cod, motiv))
			if cod in (400, 401, 403, 404):
				raise EroareRetea(_("Mullvad nu a primit cheia: verifică numărul contului și dacă mai are timp sau loc "
					"pentru un aparat nou."))
			raise EroareRetea(_("%s a răspuns neașteptat (HTTP %s).") % (self.titlu, cod))
		adresa = ", ".join(x.strip() for x in text.split(","))
		_scrieJson(CALE_MULLVAD, {"cheie": privata, "adresa": adresa})
		_jurnal("mullvad: cheia receptorului s-a inregistrat")
		return privata, adresa

	def fisiere(self, cod, cont):
		privata, adresa = self.cheia(cont.get("numar", ""))
		rez = []
		for oras, (_gazda, ip, cheie) in self._relee().get(cod, [])[:MAX_ORASE]:
			text = ("[Interface]\nPrivateKey = %s\nAddress = %s\nDNS = %s\n\n[Peer]\nPublicKey = %s\nAllowedIPs = "
				"0.0.0.0/0, ::/0\nEndpoint = %s:%d\n") % (privata, adresa, DNS_MULLVAD, cheie, ip, PORT_MULLVAD)
			rez.append((self.numeFisier(cod, oras, ".conf"), text.encode("ascii")))
		return rez


def adresaMullvadBuna(text):
	"""Adresa data de Mullvad la inregistrarea cheii: 1-2 retele (IPv4 si IPv6) cu prefix, despartite prin virgula."""
	if not text or len(text) > 120 or not re.match(r"^[0-9a-fA-F:/., ]+\Z", text):
		return False
	parti = [x.strip() for x in text.split(",") if x.strip()]
	if not 1 <= len(parti) <= 2:
		return False
	try:
		for x in parti:
			ipaddress.ip_interface(x)
			if "/" not in x:
				return False
	except ValueError:
		return False
	return True


FURNIZORI = {"mullvad": Mullvad(), "nordvpn": Nordvpn(), "pia": Pia(), "surfshark": Surfshark(), "ipvanish": Ipvanish()}
ORDINE = ("nordvpn", "surfshark", "pia", "ipvanish", "mullvad")

# furnizorii fara cale oficiala pentru aparate terte: numai textul de ajutor (fisierele se importa din ecranul VPN)
CU_FISIERE = ("protonvpn", "expressvpn", "cyberghost", "windscribe", "hma")


def titlu(fid):
	if fid in FURNIZORI:
		return FURNIZORI[fid].titlu
	return {"protonvpn": "Proton VPN", "expressvpn": "ExpressVPN", "cyberghost": "CyberGhost",
		"windscribe": "Windscribe", "hma": "HMA (HideMyAss)"}.get(fid, fid)


def grupPentru(fid):
	"""Grupul din HdsVpn in care intra serverele: furnizorul, cand HdsVpn il are in FURNIZORI, altfel felul lui."""
	f = FURNIZORI[fid]
	return fid if fid in _hv().FURNIZORI else f.fel


def grupFisiere(fid):
	"""Grupul din HdsVpn pentru importul de fisiere al unui furnizor fara cale oficiala."""
	return fid if fid in _hv().FURNIZORI else "openvpn"


def indisponibil(fid):
	"""Textul pentru un furnizor care nu merge pe acest receptor, altfel sirul gol."""
	v = _hv()
	if fid in FURNIZORI and FURNIZORI[fid].fel == "wireguard" and v.wireguardIndisponibil():
		return _(v.TEXT_WG_INDISPONIBIL)
	return ""


# ---------------------------------------------------------------- starea (fara retea, fara secrete)

_STARE = {"tari": {}, "eroare": {}, "gata": None, "aplica": ""}
_LACAT = threading.Lock()


def contSalvat(fid):
	if fid == "mullvad":
		date = _citesteJson(CALE_MULLVAD) or {}
		return bool(_CHEIE_WG.match(str(date.get("cheie") or "")))
	return contulEsteAl() == fid


def listaTarilor(fid):
	"""[{"cod", "titlu", "orase"}] dupa numele tarii, sau None daca lista nu s-a citit inca."""
	with _LACAT:
		t = _STARE["tari"].get(fid)
	if not t:
		return None
	rez = [{"cod": cod, "titlu": numeTara(cod), "orase": len(orase)} for cod, orase in t[1].items()]
	rez.sort(key=lambda x: _fara_diacritice(x["titlu"]).lower())
	return rez


def _fara_diacritice(text):
	import unicodedata
	return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def stare(fid=""):
	"""Ce arata ecranul si pagina: furnizorii, iar pentru `fid` contul (salvat sau nu), tarile, lucrarea."""
	v = _hv()
	l = v.LUCRARI.stare()
	rez = {
		"furnizori": [[f, titlu(f)] for f in ORDINE] + [[f, titlu(f)] for f in CU_FISIERE],
		"cu_cont": list(ORDINE), "cu_fisiere": list(CU_FISIERE),
		"lucreaza": l["lucreaza"], "ultima": l["ultima"],
		"text_lucreaza": textLucrare(l["lucreaza"]) if l["lucreaza"] else "",
		"aplica": _STARE["aplica"],
	}
	if fid in FURNIZORI:
		f = FURNIZORI[fid]
		rez.update({"furnizor": fid, "titlu": f.titlu, "fel": f.fel, "fel_cont": f.cont, "cont": contSalvat(fid),
			"eticheta_cont": textCont(fid), "nota_cont": textNotaCont(fid), "tari": listaTarilor(fid),
			"eroare": _STARE["eroare"].get(fid, ""), "indisponibil": indisponibil(fid), "ajutor": textAjutor(fid)})
	elif fid in CU_FISIERE:
		rez.update({"furnizor": fid, "titlu": titlu(fid), "ajutor": textAjutor(fid), "fel": "fisiere"})
	return rez


# ---------------------------------------------------------------- lucrarile (prin HdsVpn.LUCRARI)

def _jobTari(fid):
	f = FURNIZORI[fid]
	try:
		t = f.tari()
	except EroareRetea as eroare:
		mesaj = "%s" % eroare
		_STARE["eroare"][fid] = mesaj
		return False, mesaj
	except Exception as eroare:
		mesaj = _mesajRetea(eroare, f.titlu)
		_jurnal("%s: lista: %r" % (fid, eroare))
		_STARE["eroare"][fid] = mesaj
		return False, mesaj
	with _LACAT:
		_STARE["tari"][fid] = (time.time(), t)
	_STARE["eroare"].pop(fid, None)
	return True, _("Țări: %d. Alege țara.") % len(t)


def pornesteTarile(fid, din_nou=False):
	"""Numarul lucrarii care citeste lista tarilor, 0 daca lista e deja citita, None daca merge alta lucrare."""
	if fid not in FURNIZORI:
		return None
	with _LACAT:
		t = _STARE["tari"].get(fid)
	if t and not din_nou and time.time() - t[0] < VALABIL_LISTA_S:
		return 0
	return _hv().LUCRARI.porneste(LUCRARE_TARI, _jobTari, fid)


def verificaCont(fid, nume="", parola="", numar=""):
	"""(bun, mesaj, contul de dat lucrarii): contul scris acum sau, daca nu s-a scris nimic, cel salvat."""
	f = FURNIZORI.get(fid)
	if f is None:
		return False, _("Alege întâi furnizorul."), None
	v = _hv()
	if f.cont == "numar":
		if contSalvat(fid) and not numar:
			return True, "", {}
		n = Mullvad.numarBun(numar)
		if not n:
			return False, _("Scrie numărul contului Mullvad (16 cifre)."), None
		return True, "", {"numar": n}
	if not nume and not parola:
		if contSalvat(fid):
			return True, "", {}
		return False, _("Scrie întâi numele și parola de serviciu."), None
	nume = (nume or "").strip()
	if not (0 < len(nume) <= v.MAX_CAMP_CONT) or not (0 < len(parola or "") <= v.MAX_CAMP_CONT):
		return False, _("Scrie întâi numele și parola de serviciu."), None
	return True, "", {"nume": nume, "parola": parola}


def _jobConfigureaza(fid, cod, cont):
	v = _hv()
	f = FURNIZORI[fid]
	for x in cont.values():
		_SECRETE.add(x)
	if indisponibil(fid):
		return False, indisponibil(fid)
	with _LACAT:
		t = _STARE["tari"].get(fid)
	if t and cod not in t[1]:
		return False, _("Țara aleasă nu mai este în lista furnizorului.")
	if f.fel == "openvpn" and cont.get("nume"):
		reusit, mesaj = v.salveazaCont(cont["nume"], cont["parola"])
		if not reusit:
			return False, mesaj
		_contAl(fid)
	try:
		fisiere = f.fisiere(cod, cont)
	except EroareRetea as eroare:
		return False, "%s" % eroare
	except Exception as eroare:
		_jurnal("%s: fisierele: %r" % (fid, eroare))
		return False, _mesajRetea(eroare, f.titlu)
	if not fisiere:
		return False, _("%s nu are servere în %s acum.") % (f.titlu, numeTara(cod))
	grup = grupPentru(fid)
	inainte = set(p["id"] for p in v.profiluriGrup(grup))
	reusit, mesaj, detalii = v.importa(fisiere, grup)
	if not reusit:
		return False, mesaj
	# serverele (fara certificatele de alaturi, de pilda ca.ipvanish.com.crt)
	servere = [n for n, _d in fisiere if n.lower().endswith((".ovpn", ".conf"))]
	titluri = [v.titluDinNume(n, "udp" if f.fel == "openvpn" else "") for n in servere]
	acum = v.profiluriGrup(grup)
	noi = [p for p in acum if p["id"] not in inainte]
	ales = None
	for tt in titluri:
		for p in (noi or acum):
			if p["titlu"] == tt:
				ales = p
				break
		if ales:
			break
	if ales is None and noi:
		ales = noi[0]
	if ales is None:
		return False, mesaj
	_STARE["gata"] = {"furnizor": fid, "grup": grup, "profil": ales["id"], "fel": f.fel}
	_jurnal("%s: %s, %d servere (%s)" % (fid, cod, len(servere), mesaj))
	return True, _("Gata: %s, %s (servere: %d). VPN-ul pornește.") % (f.titlu, numeTara(cod), len(servere))


def configureaza(fid, cod, cont):
	"""Porneste lucrarea care face profilurile pentru tara `cod` (contul din verificaCont). Numarul lucrarii sau None
	daca merge alta. La reusita, _aplica() alege serverul si porneste VPN-ul."""
	v = _hv()
	if fid not in FURNIZORI or not _COD.match(cod or ""):
		return None
	_STARE["gata"] = None
	numar = v.LUCRARI.porneste(LUCRARE_CONFIGURARE, _jobConfigureaza, fid, cod, dict(cont or {}))
	if numar is not None:
		_dupa(numar, _aplica)
	return numar


def _asteapta(numar=None, maxim=ASTEPTARE_LUCRARE_S):
	"""Asteapta sfarsitul lucrarii `numar` (sau al oricarei lucrari); ultima lucrare (dict) sau None."""
	v = _hv()
	pana = time.time() + maxim
	while True:
		s = v.LUCRARI.stare()
		if not s["lucreaza"] and (numar is None or (s["ultima"] and s["ultima"]["id"] >= numar)):
			return s["ultima"]
		if time.time() > pana:
			return None
		time.sleep(0.3)


def _dupa(numar, functie):
	if SINCRON or _hv().LUCRARI.sincron:
		u = _hv().LUCRARI.stare()["ultima"]
		if u and u["id"] == numar and u["reusit"]:
			functie()
		return

	def fir():
		u = _asteapta(numar)
		if u and u["id"] == numar and u["reusit"]:
			try:
				functie()
			except Exception as eroare:
				_jurnal("aplicarea: %r" % (eroare,))
	t = threading.Thread(target=fir, name="HdsVpnFurnizori-dupa")
	t.daemon = True
	t.start()


def _aplica():
	"""Dupa configurare: programele (instalate daca lipsesc), serverul ales in HdsVpn, VPN-ul pornit sau repornit."""
	v = _hv()
	g = _STARE["gata"]
	if not g:
		return
	_STARE["aplica"] = ""
	s = v.setari()
	if s["pornit"] and s["furnizor"] != g["grup"]:
		numar = v.opresteVpn()
		if numar is None or not _asteapta(numar):
			_STARE["aplica"] = _("Oprește VPN-ul și alege apoi serverul din ecranul VPN.")
			return
		s = v.setari()
	# programele felului acestui furnizor (nu ale furnizorului ales inainte in HdsVpn)
	if not v.programe().get(g["fel"], True):
		numar = v.pornesteInstalarea(g["fel"])
		u = _asteapta(numar) if numar is not None else None
		if not u or not u["reusit"]:
			_STARE["aplica"] = _("Instalează programele VPN din ecranul VPN, apoi pornește VPN-ul.")
			return
	reusit, mesaj, numar = v.schimba(furnizor=g["grup"], profil=g["profil"])
	if not reusit:
		_STARE["aplica"] = mesaj
		return
	if not v.setari()["pornit"]:
		if v.pornesteVpn() is None:
			_STARE["aplica"] = _("Pornește VPN-ul din ecranul VPN.")


def stergeDatele(fid):
	"""Sterge de pe receptor contul acestui furnizor (cheia Mullvad, ori numele si parola salvate pentru el)."""
	v = _hv()
	if fid == "mullvad":
		_sterge(CALE_MULLVAD)
		_jurnal("mullvad: cheia receptorului a fost stearsa")
		return True, _("Cheia Mullvad a fost ștearsă de pe receptor. Serverele importate rămân până le ștergi din "
			"ecranul VPN.")
	if fid in FURNIZORI and contulEsteAl() == fid:
		v.stergeCont()
		date = _citesteJson(CALE_FURNIZORI) or {}
		date.pop("cont", None)
		_scrieJson(CALE_FURNIZORI, date)
		return True, _("Numele și parola au fost șterse de pe receptor.")
	return False, _("Nu sunt date salvate pentru acest furnizor.")


# ---------------------------------------------------------------- textele

def textLucrare(nume):
	if nume == LUCRARE_TARI:
		return _("Se citește lista țărilor de la furnizor...")
	if nume == LUCRARE_CONFIGURARE:
		return _("Se pregătesc serverele țării alese...")
	return _hv().textLucrare(nume)


def textCont(fid):
	if fid == "mullvad":
		return _("Numărul contului Mullvad")
	if fid == "pia":
		return _("Numele și parola PIA")
	if fid == "ipvanish":
		return _("Numele și parola IPVanish")
	return _("Numele și parola de serviciu")


def textNotaCont(fid):
	if fid == "mullvad":
		return _("Cele 16 cifre ale contului. Receptorul își face singur cheia WireGuard și o înregistrează o singură "
			"dată; numărul nu se păstrează.")
	if fid == "pia":
		return _("Numele (începe cu p) și parola din e-mailul primit la cumpărarea abonamentului PIA. După salvare nu "
			"se mai arată nicăieri.")
	if fid == "nordvpn":
		return _("Din contul Nord: NordVPN, Set up NordVPN manually, Service credentials. Nu sunt e-mailul și parola "
			"contului. După salvare nu se mai arată nicăieri.")
	if fid == "ipvanish":
		return _("Numele și parola contului IPVanish, cele cu care intri în aplicația lor. După salvare nu se mai arată "
			"nicăieri.")
	return _("Din contul Surfshark: VPN, Manual setup, OpenVPN, Credentials. Nu sunt e-mailul și parola contului. "
		"După salvare nu se mai arată nicăieri.")


def textAjutor(fid):
	"""Pe scurt, ce face receptorul (furnizorii cu cale oficiala) sau de unde iei fisierele (ceilalti)."""
	if fid == "mullvad":
		return _("Mullvad: scrii numărul contului și alegi țara. Receptorul ia lista serverelor de la Mullvad și "
			"folosește WireGuard.")
	if fid == "nordvpn":
		return _("NordVPN: scrii datele de serviciu și alegi țara. Receptorul ia fișierele OpenVPN ale serverelor de "
			"la Nord.")
	if fid == "pia":
		return _("PIA: scrii numele și parola și alegi țara. Receptorul ia fișierele OpenVPN de la PIA.")
	if fid == "surfshark":
		return _("Surfshark: scrii datele de serviciu și alegi țara. Receptorul ia fișierele OpenVPN de la Surfshark.")
	if fid == "ipvanish":
		return _("IPVanish: scrii numele și parola contului și alegi țara. Receptorul ia fișierele OpenVPN ale "
			"serverelor de la IPVanish.")
	if fid == "protonvpn":
		return _("Proton VPN nu are o cale pentru receptoare fără fișiere. În contul Proton: Downloads, OpenVPN "
			"configuration files (câte unul pe server); numele și parola sunt cele de OpenVPN din Account, nu cele de "
			"logare. Fișierele le imporți din ecranul VPN, la furnizorul Proton VPN.")
	if fid == "expressvpn":
		return _("ExpressVPN nu are o cale pentru receptoare fără fișiere. Pe pagina lor de configurare: Advanced setup "
			"(sau Show other devices), Manual configuration; numele și parola sunt la pasul 1, iar fișierele .ovpn pe "
			"locație la pasul 2. Fișierele le imporți din ecranul VPN, la furnizorul OpenVPN.")
	if fid == "cyberghost":
		return _("CyberGhost nu are o cale pentru receptoare fără fișiere. În contul online CyberGhost: VPN, Configure "
			"Device; alegi protocolul (OpenVPN UDP sau TCP), țara și grupul de servere, apoi Save Configuration. La "
			"configurația făcută apeși View: acolo sunt numele și parola de serviciu și fișierele. O țară pe "
			"configurație. Fișierele le imporți din ecranul VPN, la furnizorul OpenVPN.")
	if fid == "windscribe":
		return _("Windscribe nu are o cale pentru receptoare fără fișiere. Fișierele OpenVPN sau WireGuard se fac din "
			"Config Generators, pe site-ul lor, cu un cont plătit. Le imporți din ecranul VPN.")
	if fid == "hma":
		return _("HMA a oprit în 2023 configurarea manuală pentru routere și Linux, deci nu are cale pentru receptor. "
			"Alege alt furnizor din listă.")
	return ""
