# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLoculInternet.py - locul antenei aflat dupa adresa de internet a receptorului, ca propunere pe care omul o
# confirma. Locul unic al motorului USALS ramane in Components/HdsLocul.py; aici numai se afla si se propune.
#
# Cum merge:
#   - numai cand omul alege "Afla locul dupa internet" (ecranul Screens/HdsLocul.py sau pagina web /antena/locul); la
#     pornire, la zap sau in fundal nu se intreaba nimic;
#   - fara ruta spre internet (citita local din /proc/net/route si /proc/net/ipv6_route, nicio conexiune) nu pleaca
#     nicio cerere: omul afla ca receptorul nu are internet si primeste lista tarilor si oraselor, ca inainte;
#   - cu ruta: o singura cerere HTTPS GET spre serverul nostru (ADRESA), fara parametri si fara nimic despre receptor.
#     Serverul vede numai adresa de internet de la care vine cererea, cauta orasul in baza lui (DB-IP Lite, CC BY 4.0)
#     si raspunde cu orasul, tara si coordonatele; adresa nu o pastreaza. Niciun serviciu strain nu e intrebat;
#   - raspunsul se verifica (marime, JSON, fiecare camp, limitele coordonatelor); un oras din tabelul imaginii
#     (Components/HdsLocuriDate.py) aflat la cel mult RAZA_KM, in aceeasi tara, ii ia locul: numele romanesc si
#     coordonatele din tabel, ca la alegerea din lista;
#   - cand omul nu primeste locul gasit, lista tarilor si oraselor se deschide pe orasul din tabel cel mai apropiat de el
#     (pentruLista), chiar daca orasul gasit nu e in tabel;
#   - locul se scrie (HdsLocul.seteaza, sursa "internet") numai dupa confirmarea omului: Cautare.foloseste().
#
# Firul enigma2 nu asteapta: cererea merge pe un fir separat (Cautare.porneste), iar ecranul si pagina web intreaba
# starea (Cautare.stare) pe un ceas. La import nu se atinge nimic din enigma, ca probele de pe PC sa poata pune obiecte
# false; cererea, ruta si firul se pot inlocui din probe.
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
INTREBARE = N_("Locul găsit după adresa de internet a receptorului:\n\n%(loc)s\n%(coordonate)s\nSursa: %(sursa)s\n\nDe obicei este orașul tău, dar uneori este orașul furnizorului de internet. Folosești acest loc? (Nu: alegi țara și orașul din listă.)")
NOTA_SURSA = N_("Coordonatele orașelor din listă: %s. Receptorul întreabă serverul HD Satelit numai când alegi „Află locul după internet”, iar serverul nu păstrează adresa de internet.")
TEXT_SERVER = N_("prin serverul HD Satelit")


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


# ---------------------------------------------------------------- cererea si verificarea raspunsului

def _citesteUrl(adresa, timp, limita):
	"""(cod HTTP, corp) pentru un GET; arunca numai la erorile de retea (fara raspuns, timp depasit, certificat).
	Corpul se citeste cel mult pana la limita + 1 octeti."""
	try:
		from urllib.request import Request, urlopen
		from urllib.error import HTTPError
	except ImportError:  # Python 2, numai pe PC
		from urllib2 import Request, urlopen, HTTPError
	cerere = Request(adresa, headers={"User-Agent": AGENT, "Accept": "application/json", "Accept-Encoding": "identity"})
	try:
		r = urlopen(cerere, timeout=timp)
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
		orase = orase or _locul().orase
		cel = _celMaiAproape(lat, lon, orase(rez["tara"]))
		if cel is not None:
			return rez["tara"], cel[1]
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


def intrebare(rez):
	return _t(INTREBARE) % {"loc": textLoc(rez), "coordonate": textCoordonate(rez), "sursa": textSursa(rez)}


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


class Cautare(object):
	"""Starea cautarii, aceeasi pentru televizor si pentru pagina web. porneste() nu asteapta; stare() se cheama de pe
	un ceas; foloseste() scrie locul gasit, numai la confirmarea omului."""

	def __init__(self, cauta_=None, retea_=None, fir=None, ceas=None):
		self._cauta = cauta_ or cauta
		self._retea = retea_ or retea
		self._fir = fir or _firDaemon
		self._ceas = ceas or time.time
		self._zavor = threading.Lock()
		self._generatie = 0
		self._inceput = None
		self._pune(NIMIC)

	def _pune(self, stare, rezultat=None, mesaj=""):
		self._stare = stare
		self._rezultat = rezultat
		self._mesaj = mesaj
		self._semn = semn(rezultat) if rezultat is not None else ""
		# orasul din tabel pe care se deschide lista la "Nu" (o singura data, cand se afla locul)
		self._lista = pentruLista(rezultat) if rezultat is not None else ("", "")
		self._cand = self._ceas() if rezultat is not None else None

	def porneste(self):
		"""True: o cautare a pornit (sau era deja in curs). False: receptorul nu are ruta spre internet, deci nu pleaca
		nicio cerere; stare() spune de ce."""
		with self._zavor:
			if self._stare == LUCREAZA:
				return True
		if not self._retea():
			with self._zavor:
				self._generatie += 1
				self._pune(FARA_RETEA, mesaj=_t(MESAJ_FARA_RETEA))
			return False
		with self._zavor:
			self._generatie += 1
			generatie = self._generatie
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
			if stare == GASIT:
				self._pune(GASIT, rezultat=x)
			else:
				self._pune(EROARE, mesaj=x)

	def stare(self):
		"""{"stare", "mesaj", "semn", "gasit": {...} sau None, "intrebare"}: o copie, buna de dat ecranului si paginii.
		O cautare care trece de LIMITA_S devine aici eroare ("serverul nu a raspuns"); firul ei nu mai schimba nimic."""
		with self._zavor:
			if self._stare == LUCREAZA and self._inceput is not None and \
					not 0 <= self._ceas() - self._inceput <= LIMITA_S:
				jurnal("cautarea a trecut de %d s" % LIMITA_S)
				self._generatie += 1
				self._pune(EROARE, mesaj=_t(MESAJ_NU_RASPUNDE))
			st, rez, mesaj, s, lista = self._stare, self._rezultat, self._mesaj, self._semn, self._lista
		d = {"stare": st, "mesaj": mesaj, "semn": s, "gasit": None, "intrebare": ""}
		if st == GASIT and rez is not None:
			# tara_lista si oras_lista: unde se deschide lista la "Nu" (orasul gasit poate lipsi din tabel)
			d["gasit"] = {"oras": rez["oras"], "tara": rez["tara"], "tara_nume": numeTara(rez),
				"lat": rez["lat_mii"] / 1000.0, "lon": rez["lon_mii"] / 1000.0, "coordonate": textCoordonate(rez),
				"sursa": textSursa(rez), "loc": textLoc(rez), "din_tabel": bool(rez.get("din_tabel")),
				"tara_lista": lista[0], "oras_lista": lista[1]}
			d["intrebare"] = intrebare(rez)
		return d

	def foloseste(self, semn_=None, actualizeaza_sec=True):
		"""Locul gasit devine locul antenei (HdsLocul.seteaza, sursa internet), dupa confirmarea omului. Cu `semn_` (pagina
		web), numai daca e chiar locul aratat si nu a trecut VALABIL_S. -> (True, "") sau (False, motivul)."""
		with self._zavor:
			st, rez, s, cand = self._stare, self._rezultat, self._semn, self._cand
		if st != GASIT or rez is None or (semn_ is not None and semn_ != s):
			return False, _t(MESAJ_EXPIRAT)
		acum = self._ceas()
		if cand is not None and not 0 <= acum - cand <= VALABIL_S:
			return False, _t(MESAJ_EXPIRAT)
		L = _locul()
		return L.seteaza(rez["lat_mii"], rez["lon_mii"], rez["tara"], rez["oras"], L.SURSA_INTERNET,
			actualizeaza_sec=actualizeaza_sec)


CAUTARE = Cautare()
