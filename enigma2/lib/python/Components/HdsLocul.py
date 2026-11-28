# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLocul.py - locul antenei (latitudinea si longitudinea casei): o singura sursa pentru motorul USALS.
#
# Pana la 0.2.4 motorul USALS lucra cu 45,300 N / 23,270 E (valorile implicite din NimManager.py) cand locul nu era
# scris in Setari tuner. Oricine statea in alt loc primea antena rotita gresit, fara niciun semn.
#
# Ce face modulul:
#   - config.hds_locul e locul unic (miimi de grad, nord si est pozitive) si spune daca e stabilit;
#   - copiile pe care le citeste nucleul (config.Nims[N] in modul simplu si config.Nims[N].advanced.lnb[M] cu DiSEqC
#     1.2, NimManager.SecConfigure -> sec.cpp, calculul USALS) le scrie numai acest modul: toate la alegerea locului;
#     la pornire si la un LNB nou cu DiSEqC 1.2, numai cele care nu au nicio cheie a locului in settings;
#   - migrarea, o singura data, la prima pornire a versiunii care o aduce (semnul: config.hds_locul.migrat in settings;
#     FISIER_SEMN e numai o nota pe disc): unde un tuner are motor si cheile locului lipsesc din settings, se scriu
#     explicit valorile vechi (VECHI), deci antena se misca exact ca inainte. Fara motor, locul ramane nestabilit. O
#     copie de setari 0.2.4 pusa la loc dupa migrare (aceeasi amprenta, deci acelasi receptor, care folosea valorile
#     vechi) aduce settings fara semn: migrarea se face din nou si locul ramane cel de pana atunci;
#   - cu locul nestabilit SecConfigure nu da nucleului satelitii care cer calculul USALS: nicio cale (zap, inregistrare,
#     scanare, „Mergi la satelit") nu poate roti antena dupa un loc inventat. Pasii, miscarea continua, pozitiile
#     memorate si limitele nu au nevoie de loc si merg ca inainte;
#   - tarile si orasele (din GeoNames, CC BY 4.0): toata lumea din 0.8.0, cu numele tarii in limba meniului
#     (tariAfisate) si cautarea dupa litere (potriveste). Tarile stau in Components/HdsLocuriDate.py (numele lor sunt
#     msgid), orasele (~76.000 din 0.8.0, LOC2) in FISIER_ORASE, citit numai cand cineva cere orasele unei tari;
#   - locul aflat dupa adresa de internet (Components/HdsLoculInternet.py) intra tot prin seteaza(), cu sursa
#     SURSA_INTERNET, fara nicio intrebare (LOC2, 26.11.2026: implicit cat timp e internet): cat omul nu a
#     ales singur un oras sau coordonate (automat()), receptorul afla locul singur la pornire si la deschiderea
#     ecranului; fara internet ramane ultimul loc stiut. Un oras sau coordonatele alese de om opresc asta (mod "ales"),
#     "Afla locul dupa internet" il porneste iar (mod "internet");
#   - ecranele deschise afla de un loc nou (scris de pe televizor sau din pagina web) prin laSchimbare(): seteaza() isi
#     anunta abonatii dupa ce locul e scris.
#
# La import nu se atinge nimic din enigma: config, configfile si nimmanager se iau in functii, ca probele de pe PC sa
# poata pune obiecte false.
import json
import os
import unicodedata

FISIER_SEMN = "/etc/enigma2/hds-locul-migrat"
# pozitia motorului tinuta minte intre porniri (Components/HdsMotorPozitie.py): semn ca motorul a fost folosit
FISIER_POZITII = "/etc/enigma2/hds-motor-pozitie.json"

CAMPURI = ("latitude", "latitudeOrientation", "longitude", "longitudeOrientation")
# valorile implicite de pana la 0.2.4 (NimManager.py, ConfigFloat [45,300] si [23,270], „north" si „east"), in forma
# scrisa in settings; se scriu numai la migrare, numai unde cheia lipseste
VECHI = {"latitude": "45.300", "latitudeOrientation": "north", "longitude": "23.270", "longitudeOrientation": "east"}

SURSA_TABEL = "tabel"
SURSA_MANA = "mana"
SURSA_MIGRARE = "migrare"
SURSA_TUNER = "tuner"
SURSA_INTERNET = "internet"

ATRIBUIRE = "GeoNames (geonames.org), CC BY 4.0"
LAT_MAX = 90000
LON_MAX = 180000


def N_(text):
	return text


def _t(text):
	"""traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC"""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


MESAJ_FARA_LOC = N_("Locul antenei nu e stabilit, deci motorul nu știe încotro să rotească antena. Alege țara și orașul sau scrie coordonatele, apoi încearcă din nou.")
MESAJ_MISCARE = N_("Antena se rotește acum. Locul se schimbă după ce se oprește motorul.")
MESAJ_INREGISTRARE = N_("O înregistrare folosește acum tunerul. Locul se schimbă după ce se termină.")
MESAJ_LIMITE = N_("Latitudinea se scrie între 0 și 90 de grade, longitudinea între 0 și 180 de grade.")
MESAJ_ORAS = N_("Orașul ales nu e în tabel.")
# locul scris de mana departe de tara receptorului, cu o varianta apropiata (emisferele schimbate sau latitudinea cu
# longitudinea inversate): intrebarea de pe televizor si din pagina web; "Da" scrie varianta, "Nu" scrie ce s-a scris
# satelitul sub orizont din locul antenei (acelasi calcul ca nucleul, Components/DishMath.py): fara comanda USALS spre el
MESAJ_SUB_ORIZONT = N_("Din locul antenei (%(loc)s), satelitul %(sat)s e sub orizont, deci motorul nu rotește antena spre el. Verifică Locul antenei: emisfera (Nord sau Sud) și partea față de Greenwich (Est sau Vest).")
MESAJ_DEPARTE = N_("Locul scris (%(scris)s) e departe de %(tara)s. Probabil emisfera (Nord sau Sud) ori partea față de Greenwich (Est sau Vest) e aleasă greșit. Salvez %(propus)s?")
TEXT_NESTABILIT = N_("nestabilit")
TEXT_MANA = N_("scris de mână")
TEXT_MIGRARE = N_("din setările tunerului de dinainte")


def jurnal(text):
	print("[HdsLocul] %s" % text)


# ---------------------------------------------------------------- setarile

def initConfig():
	"""config.hds_locul (creat o data). Subsectiunea se leaga de config inainte de campuri, ca fiecare camp sa-si ia
	valoarea din settings (config.py, ConfigSubsection.__setattr__)."""
	from Components.config import config, ConfigSubsection, ConfigYesNo, ConfigInteger, ConfigText
	if "hds_locul" in config.content.items:
		return config.hds_locul
	config.hds_locul = ConfigSubsection()
	s = config.hds_locul
	s.stabilit = ConfigYesNo(default=False)
	s.lat = ConfigInteger(default=0, limits=(-LAT_MAX, LAT_MAX))
	s.lon = ConfigInteger(default=0, limits=(-LON_MAX, LON_MAX))
	s.tara = ConfigText(default="", fixed_size=False)
	s.oras = ConfigText(default="", fixed_size=False)
	s.sursa = ConfigText(default="", fixed_size=False)
	s.migrat = ConfigYesNo(default=False)
	# "" = omul nu a ales inca nimic (vezi automat()), MOD_INTERNET = locul dupa internet, MOD_ALES = ales de om
	s.mod = ConfigText(default="", fixed_size=False)
	return s


MOD_INTERNET = "internet"
MOD_ALES = "ales"


def automat():
	"""True cand locul se afla singur dupa internet: omul a ales "Afla locul dupa internet" (mod internet) sau nu a
	ales inca nimic si locul e nestabilit sau tot de pe internet. Un loc din tabel, scris de mana sau ramas din setarile
	tunerului de dinainte (migrare, tuner) e al omului: o actualizare nu muta in tacere o antena care merge."""
	try:
		s = initConfig()
		mod = s.mod.value
		if mod == MOD_INTERNET:
			return True
		if mod == MOD_ALES:
			return False
		return not s.stabilit.value or s.sursa.value in ("", SURSA_INTERNET)
	except Exception as e:
		jurnal("felul locului nu se poate citi: %r" % (e,))
		return False


def alegeInternet():
	"""omul a ales "Afla locul dupa internet": de acum locul se afla singur (si la pornire)"""
	try:
		s = initConfig()
		if s.mod.value != MOD_INTERNET:
			s.mod.value = MOD_INTERNET
			s.mod.save()
			_salveazaSettings()
	except Exception as e:
		jurnal("felul locului nu se poate scrie: %r" % (e,))


def stabilit():
	try:
		return bool(initConfig().stabilit.value)
	except Exception as e:
		jurnal("starea locului nu se poate citi: %r" % (e,))
		return False


def locul():
	"""(latitudine, longitudine) in miimi de grad, nord si est pozitive; None cand locul nu e stabilit"""
	try:
		s = initConfig()
		if not s.stabilit.value:
			return None
		return int(s.lat.value), int(s.lon.value)
	except Exception as e:
		jurnal("locul nu se poate citi: %r" % (e,))
		return None


def grade():
	"""(latitudine, longitudine) in grade, nord si est pozitive; None cand locul nu e stabilit"""
	l = locul()
	if l is None:
		return None
	return l[0] / 1000.0, l[1] / 1000.0


def stare():
	"""tot ce trebuie ecranelor si paginii web (cand setarile nu se pot citi: nestabilit)"""
	l = locul()
	rez = {"stabilit": l is not None, "tara": "", "tara_nume": "", "oras": "", "sursa": "", "lat": None, "lon": None,
		"text": textLoc(), "coordonate": ""}
	if l is None:
		return rez
	rez.update(lat=l[0] / 1000.0, lon=l[1] / 1000.0, coordonate=textCoordonate(l[0], l[1]))
	try:
		s = initConfig()
		rez.update(tara=s.tara.value, tara_nume=_t(numeTara(s.tara.value)) if numeTara(s.tara.value) else "",
			oras=s.oras.value, sursa=s.sursa.value,
			coordonate=textCoordonate(l[0], l[1], _zecimale(s.sursa.value)))
	except Exception as e:
		jurnal("locul nu se poate citi: %r" % (e,))
	return rez


# ---------------------------------------------------------------- textele

def _zecimale(sursa):
	return 2 if sursa in (SURSA_TABEL, SURSA_INTERNET) else 3


_HDS_GRADE = []


def _grade_():
	"""Components/HdsGrade.py, cautat o singura data (un import cazut costa cat zeci de randuri de lista)"""
	if not _HDS_GRADE:
		try:
			from Components import HdsGrade
		except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
			import HdsGrade
		_HDS_GRADE.append(HdsGrade)
	return _HDS_GRADE[0]


def textCoordonate(lat_mii, lon_mii, zecimale=2, cod=None):
	"""„44,43 N, 26,11 E" in romana (V pentru vest, ca in Rotirea antenei), „44.43 N, 26.11 W" in engleza: literele si
	separatorul zecimal ale limbii meniului, din Components/HdsGrade.py, ca pozitiile satelitilor si pagina /antena/locul.
	`cod` (limba, HdsGrade.limba()) se da o data pentru o lista lunga (LOC2: SUA are ~8.600 de locuri)"""
	return _grade_().coordonate(int(lat_mii) / 1000.0, int(lon_mii) / 1000.0, zecimale, cod)


def textCoordonateLista(orase_):
	"""coordonatele scrise ale fiecarui oras din [(nume, lat_mii, lon_mii)], cu limba aflata o singura data"""
	try:
		cod = _grade_().limba()
	except Exception:
		cod = None
	return [textCoordonate(lat, lon, 2, cod) for _nume, lat, lon in orase_]


def textOrase(orase_):
	"""[(textul aratat in lista, nume)] pentru orasele unei tari: numele si coordonatele"""
	return [(u"%s   (%s)" % (o[0], text), o[0]) for o, text in zip(orase_, textCoordonateLista(orase_))]


def textLoc():
	"""„București, România (44,43 N, 26,11 E)"; „44,430 N, 26,100 E (scris de mână)"; „nestabilit\""""
	try:
		s = initConfig()
	except Exception:
		return _t(TEXT_NESTABILIT)
	l = locul()
	if l is None:
		return _t(TEXT_NESTABILIT)
	sursa = s.sursa.value
	coordonate = textCoordonate(l[0], l[1], _zecimale(sursa))
	if sursa in (SURSA_TABEL, SURSA_INTERNET) and s.oras.value:
		# o tara care nu e in tabel (locul dupa internet) se arata cu codul ei; numele, in limba meniului
		tara = numeTaraAfisat(s.tara.value)
		loc = "%s, %s" % (s.oras.value, tara) if tara else s.oras.value
		return "%s (%s)" % (loc, coordonate)
	if sursa in (SURSA_MIGRARE, SURSA_TUNER):
		return "%s (%s)" % (coordonate, _t(TEXT_MIGRARE))
	return "%s (%s)" % (coordonate, _t(TEXT_MANA))


# ---------------------------------------------------------------- tabelul tarilor si oraselor

_ORDINE = u"aăâbcdefghiîjklmnopqrsștțuvwxyz"
_RANG = dict((c, i) for i, c in enumerate(_ORDINE))
# s si t cu sedila (forma veche, din fonturile de dinainte de Unicode 3) sunt literele romanesti cu virgula
_CEDILA = {u"ş": u"ș", u"Ş": u"Ș", u"ţ": u"ț", u"Ţ": u"Ț"}
_LIGATURI = {u"ß": u"ss", u"æ": u"ae", u"œ": u"oe", u"ø": u"o", u"ł": u"l", u"đ": u"d", u"ð": u"d", u"ı": u"i",
	u"þ": u"th"}


def nfc(text):
	return unicodedata.normalize("NFC", text or u"")


def curata(text):
	"""forma NFC, cu ș si ț cu virgula (textele romanesti; in turca sedila e corecta, deci numele oraselor raman cum sunt
	in tabel)"""
	text = unicodedata.normalize("NFC", text or u"")
	return u"".join(_CEDILA.get(c, c) for c in text)


def cheieRomaneasca(text):
	"""Cheia de sortare dupa alfabetul romanesc: a ă â b ... i î ... s ș t ț ... z. Literele altor limbi cu semne
	(é, ö, ç, ł...) stau la litera lor de baza si trec dupa ea numai cand restul e la fel. Spatiile, cratimele,
	apostrofurile si parantezele nu conteaza la prima comparare; cifrele vin inaintea literelor."""
	primar, secundar = [], []
	for c in curata(text).lower():
		if c in _RANG:
			primar.append(_RANG[c])
			secundar.append(0)
			continue
		if c in _LIGATURI:
			for x in _LIGATURI[c]:
				primar.append(_RANG[x])
				secundar.append(1)
			continue
		if c.isdigit():
			primar.append(-10 + (int(c) if c in u"0123456789" else 0))
			secundar.append(0)
			continue
		baza = unicodedata.normalize("NFD", c)[0]
		if baza in _RANG:
			primar.append(_RANG[baza])
			secundar.append(1 + sum(ord(x) for x in unicodedata.normalize("NFD", c)[1:]) % 1000)
	return (primar, secundar, text)


def _date():
	from Components import HdsLocuriDate
	return HdsLocuriDate


_cache = {}


def tari():
	"""[(cod, nume)] in ordinea alfabetica romaneasca"""
	if "tari" not in _cache:
		_cache["tari"] = sorted(((cod, nfc(nume)) for cod, nume in _date().TARI), key=lambda t: cheieRomaneasca(t[1]))
	return list(_cache["tari"])


def numeTara(cod):
	for c, nume in tari():
		if c == cod:
			return nume
	return ""


# Toata lumea (LOC1, 26.11.2026; lme, Canada, LinuxSat 163972: "Canada & us are not even listed in the dish location
# menu"): tabelul are acum fiecare tara cu orase in GeoNames (~245) si ~2900 de orase, deci listele se arata cu numele
# tarii in limba meniului, in ordinea alfabetica a acelui nume, si se pot cauta dupa litere (Screens/HdsLocul.py,
# HdsLoculAlegere; pagina /antena/locul).

def _limbaMeniului():
	try:
		from Components import HdsGrade
	except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
		try:
			import HdsGrade
		except ImportError:
			return "ro"
	try:
		return (HdsGrade.limba() or "ro")[:2].lower()
	except Exception:
		return "ro"


def faraSemne(text):
	"""textul pentru cautare: litere mici, fara semne (ă->a, é->e, ß->ss), fara spatii, cratime si apostrofuri, ca
	"sao", "São" si "SAO" sa se potriveasca; literele altor alfabete raman (chirilice, grecesti). Tinut minte: lista
	unei tari mari (SUA, ~8.600 de orase) se filtreaza la fiecare tasta."""
	try:
		return _faraSemneTinut[text]
	except (KeyError, TypeError):
		pass
	rez = _faraSemne(text)
	if isinstance(text, str):
		if len(_faraSemneTinut) >= 30000:
			_faraSemneTinut.clear()
		_faraSemneTinut[text] = rez
	return rez


_faraSemneTinut = {}


def _faraSemne(text):
	# o singura descompunere NFD pe tot textul (LOC2: de cateva ori mai repede pe listele lungi decat litera cu litera)
	t = curata(text).lower()
	if not t.isascii():
		t = u"".join(_LIGATURI.get(c, c) for c in t)
		t = unicodedata.normalize("NFD", t)
		return u"".join(x for x in t if x.isalnum() and unicodedata.category(x) != "Mn")
	return u"".join(x for x in t if x.isalnum())


def potriveste(nume, cautat):
	"""True daca literele cautate (fara semne) sunt in nume; un text gol se potriveste cu orice"""
	c = faraSemne(cautat)
	return not c or c in faraSemne(nume)


def filtreaza(randuri, cautat, nume=lambda r: r):
	"""randurile al caror nume (functia `nume`) contine literele cautate: intai cele al caror nume incepe cu ele, apoi
	cele cu un cuvant care incepe cu ele ("york" -> "New York City"), apoi restul, fiecare grup in ordinea de pana atunci
	(din 0.8.0 lista unei tari are si mii de locuri: "mont" in Canada da intai Mont-Laurier, Montmagny, Montréal...,
	apoi Deux-Montagnes, apoi Edmonton)"""
	c = faraSemne(cautat)
	if not c:
		return list(randuri)
	intai, cuvant, apoi = [], [], []
	for r in randuri:
		n = nume(r)
		f = faraSemne(n)
		if c not in f:
			continue
		if f.startswith(c):
			intai.append(r)
		elif any(faraSemne(x).startswith(c) for x in curata(n).replace("-", " ").split()):
			cuvant.append(r)
		else:
			apoi.append(r)
	return intai + cuvant + apoi


def cheieAfisare(text, limba=None):
	"""cheia de sortare a unui nume aratat: alfabetul romanesc in romana, altfel literele fara semne"""
	if (limba or _limbaMeniului()) == "ro":
		return cheieRomaneasca(text)
	return (faraSemne(text), text)


def numeTaraAfisat(cod):
	"""numele tarii in limba meniului (traducerea numelui romanesc din tabel); codul cand tara nu e in tabel"""
	nume = numeTara(cod)
	return _t(nume) if nume else (cod or "")


def tariAfisate():
	"""[(cod, numele in limba meniului)] in ordinea alfabetica a numelui aratat"""
	limba = _limbaMeniului()
	lista = [(cod, nfc(_t(nume))) for cod, nume in tari()]
	return sorted(lista, key=lambda t: cheieAfisare(t[1], limba))


def taraImplicita():
	"""tara aleasa dinainte in liste: cea aleasa ultima data, altfel tara limbii meniului, daca e in tabel"""
	try:
		tara = initConfig().tara.value
		if tara and numeTara(tara):
			return tara
	except Exception:
		pass
	try:
		from Components import NimManager
		tara = NimManager.taraReceptorului()
		if tara and numeTara(tara):
			return tara
	except Exception:
		pass
	return ""


# Orasele (LOC2, 26.11.2026; pana atunci 35 de orase in Canada si 122 in SUA, prea putine): toate asezarile de
# cel putin 5000 de locuitori din GeoNames, plus capitalele si resedintele (PPLA, PPLA2) oricat de mici, ~76.000. Ca
# tuple Python ar fi >10 MB in memorie si ~2 MB de .py incarcat la prima folosire, deci stau intr-un fisier gzip (~0,7 MB)
# facut de scripturi/locuri/genereaza_locuri.py: antetul are randuri "#..." si unul "#index CC,inceput,sfarsit;..."
# (octetii fiecarei tari dupa antet), apoi, tara dupa tara, randuri "nume<TAB>lat<TAB>lon" (sutimi de grad), deja in
# ordinea alfabetica romaneasca. Se citeste numai cand cineva cere orasele unei tari; in memorie raman numai orasele
# ultimelor TARI_TINUTE tari, nu toata lumea.
FISIER_ORASE = "/usr/share/enigma2/hds-locuri.tsv.gz"
TARI_TINUTE = 3


def caleOrase():
	"""fisierul oraselor: cel din imagine, altfel (pe PC, in probe) data/ din arborele sursei"""
	if os.path.exists(FISIER_ORASE):
		return FISIER_ORASE
	aici = os.path.dirname(os.path.abspath(__file__))
	for sus in (("..", "..", ".."), ("..", "..")):
		cale = os.path.normpath(os.path.join(aici, *(sus + ("data", "hds-locuri.tsv.gz"))))
		if os.path.exists(cale):
			return cale
	return FISIER_ORASE


def _citesteOrase(cod, cale=None):
	"""[(nume, lat_mii, lon_mii)] ale tarii `cod` din fisierul oraselor, in ordinea din fisier; [] cand lipseste"""
	import gzip
	try:
		with gzip.open(cale or caleOrase(), "rb") as f:
			date = f.read()
	except (IOError, OSError, EOFError) as e:
		jurnal("orasele nu se pot citi: %r" % (e,))
		return []
	i, index = 0, {}
	while date.startswith(b"#", i):
		j = date.find(b"\n", i)
		if j < 0:
			return []
		rand = date[i:j]
		if rand.startswith(b"#index "):
			for bucata in rand[7:].decode("ascii").split(";"):
				c, a, b = bucata.split(",")
				index[c] = (int(a), int(b))
		i = j + 1
	if cod not in index:
		return []
	a, b = index[cod]
	rez = []
	for rand in date[i + a:i + b].decode("utf-8").split("\n"):
		if not rand:
			continue
		nume, lat, lon = rand.split("\t")
		rez.append((nume, int(lat) * 10, int(lon) * 10))
	return rez


def toateOrasele(cale=None):
	"""(cod, nume, lat_mii, lon_mii) pentru fiecare oras al lumii, dintr-o singura citire a fisierului, fara sa le tina
	pe toate in memorie (cel mai apropiat oras cand tara nu e in tabel, HdsLoculInternet.pentruLista)"""
	import gzip
	try:
		with gzip.open(cale or caleOrase(), "rb") as f:
			date = f.read()
	except (IOError, OSError, EOFError) as e:
		jurnal("orasele nu se pot citi: %r" % (e,))
		return
	i, index = 0, []
	while date.startswith(b"#", i):
		j = date.find(b"\n", i)
		if j < 0:
			return
		if date.startswith(b"#index ", i):
			index = [x.split(",") for x in date[i + 7:j].decode("ascii").split(";")]
		i = j + 1
	for cod, a, b in index:
		for rand in date[i + int(a):i + int(b)].decode("utf-8").split("\n"):
			if rand:
				nume, lat, lon = rand.split("\t")
				yield cod, nume, int(lat) * 10, int(lon) * 10


_tinute = []


def orase(cod):
	"""[(nume, lat_mii, lon_mii)] ale tarii `cod`, in ordinea alfabetica romaneasca"""
	cheie = "orase-" + str(cod)
	if cheie not in _cache:
		_cache[cheie] = _citesteOrase(cod)
		_tinute.append(cheie)
		while len(_tinute) > TARI_TINUTE:
			_cache.pop(_tinute.pop(0), None)
	return list(_cache[cheie])


def gasesteOras(cod, nume):
	"""(lat_mii, lon_mii) sau None"""
	nume = nfc(nume)
	for n, lat, lon in orase(cod):
		if n == nume:
			return lat, lon
	return None


# ---------------------------------------------------------------- copiile din config.Nims

def _camp(sectiune, nume):
	try:
		return sectiune.content.items.get(nume)
	except AttributeError:
		return None


def _valoare(sectiune, nume, implicit=None):
	el = _camp(sectiune, nume)
	try:
		return el.value if el is not None else implicit
	except Exception:
		return implicit


def _esteFloat(el):
	from Components.config import ConfigFloat
	return isinstance(el, ConfigFloat)


def grupuriConfig():
	"""[(nume, sectiune, motor)] pentru fiecare loc din config.Nims unde stau coordonatele: tunerul de satelit insusi
	(modul simplu; campurile exista pe orice tuner DVB-S) si fiecare LNB avansat care le are (DiSEqC 1.2). `motor` =
	tunerul chiar trimite comenzi de motor din aceste coordonate (simplu „positioner"; LNB 1.2 folosit de un satelit)."""
	from Components.config import config
	rez = []
	nims = config.content.items.get("Nims")
	if nims is None:
		return rez
	for slot in range(len(nims)):
		nim = nims[slot]
		if not _esteFloat(_camp(nim, "latitude")):
			continue
		mod = _valoare(nim, "configMode", "nothing")
		rez.append(("config.Nims.%d" % slot, nim, mod == "simple" and _valoare(nim, "diseqcMode") == "positioner"))
		avansat = _camp(nim, "advanced")
		lnburi = _camp(avansat, "lnb") if avansat is not None else None
		if lnburi is None:
			continue
		folosite = set()
		sateliti = _camp(avansat, "sat")
		for _orbital, sat in (list(sateliti.items()) if sateliti is not None else []):
			try:
				folosite.add(int(sat.lnb.value))
			except Exception:
				continue
		for numar in sorted(lnburi.keys()):
			sectiune = lnburi[numar]
			if not _esteFloat(_camp(sectiune, "latitude")):
				continue
			motor = mod == "advanced" and int(numar) in folosite and _valoare(sectiune, "diseqcMode") == "1_2"
			rez.append(("config.Nims.%d.advanced.lnb.%d" % (slot, int(numar)), sectiune, motor))
	return rez


def _cheiScrise(sectiune):
	"""{camp: textul din settings} pentru cheile locului care sunt in settings"""
	rez = {}
	for camp in CAMPURI:
		el = _camp(sectiune, camp)
		if el is not None and el.saved_value is not None:
			rez[camp] = el.saved_value
	return rez


def _inFloat(mii):
	a = abs(int(mii))
	return [a // 1000, a % 1000]


def _scrieGrup(sectiune, lat_mii, lon_mii, salveaza=True):
	"""Cele 4 campuri ale unei copii. Cu salveaza, si save(): coordonatele (altele decat implicitul neutru 0,000) intra
	in settings la urmatorul configfile.save(); orientarile egale cu implicitul raman implicite, ca in restul
	setarilor. Fara save_forced: un save_forced ramas pe element ar scrie in settings si valoarea pusa inapoi de
	„Configurare LNB" la „Revino" (HdsLnbAplicare), care trebuie sa lipseasca."""
	valori = {"latitude": _inFloat(lat_mii), "latitudeOrientation": "north" if lat_mii >= 0 else "south",
		"longitude": _inFloat(lon_mii), "longitudeOrientation": "east" if lon_mii >= 0 else "west"}
	for camp in CAMPURI:
		el = _camp(sectiune, camp)
		if el is None:
			continue
		el.value = valori[camp]
		if salveaza:
			el.save()


def umpleGrup(sectiune):
	"""O copie noua (un LNB trecut acum pe DiSEqC 1.2, NimManager.configDiSEqCModeChanged): cu locul stabilit si fara
	nicio cheie a locului in settings, ia locul unic, numai in memorie (ca un implicit): pe disc ajunge prin cine salveaza
	LNB-ul (Setari tuner, Configurare LNB) sau la pornirea urmatoare (sincronizeaza). Asa o proba nepastrata din
	„Configurare LNB" nu lasa nimic in settings. Cu locul nestabilit nu se schimba nimic."""
	try:
		l = locul()
		if l is None or _cheiScrise(sectiune):
			return
		_scrieGrup(sectiune, l[0], l[1], salveaza=False)
	except Exception as e:
		jurnal("copia noua a locului: %r" % (e,))


# ---------------------------------------------------------------- migrarea (o singura data)

def miiDinText(text):
	"""textul unui ConfigFloat din settings -> miimi de grad. Partea de dupa punct sunt miimile scrise fara zerouri in
	fata (config.py, ConfigSequence.tostring): „45.300" = 45,300, iar „44.30" = 44,030, nu 44,30."""
	parti = str(text).strip().split(".")
	grade_ = int(parti[0])
	mii = int(parti[1]) if len(parti) > 1 and parti[1] else 0
	return grade_ * 1000 + mii


def coordonateGrup(valori):
	"""{camp: text} cu toate cele 4 campuri -> (lat_mii, lon_mii) semnate"""
	lat = miiDinText(valori["latitude"])
	lon = miiDinText(valori["longitude"])
	if valori["latitudeOrientation"] == "south":
		lat = -lat
	if valori["longitudeOrientation"] == "west":
		lon = -lon
	return lat, lon


def planMigrare(grupuri, pozitii_exista):
	"""Planul migrarii, fara nimic din enigma. `grupuri`: [{"nume", "motor": bool, "scrise": {camp: text}}] (scrise =
	cheile locului care sunt in settings). Intoarce {"scrie": [(nume, camp, text)], "locul": (lat_mii, lon_mii) sau
	None}: numai grupurile cu motor primesc cheile lipsa, cu valorile vechi; locul unic e al primului grup cu motor (ce
	folosea nucleul pana acum); fara motor, dar cu pozitii de motor tinute minte, locul unic e cel vechi; altfel None
	(nestabilit)."""
	scrie = []
	loc = None
	for g in grupuri:
		if not g.get("motor"):
			continue
		scrise = g.get("scrise") or {}
		valori = {}
		for camp in CAMPURI:
			if camp in scrise:
				valori[camp] = scrise[camp]
			else:
				valori[camp] = VECHI[camp]
				scrie.append((g["nume"], camp, VECHI[camp]))
		if loc is None:
			loc = coordonateGrup(valori)
	if loc is None and pozitii_exista:
		loc = coordonateGrup(VECHI)
	return {"scrie": scrie, "locul": loc}


def pozitiiExista(fisier=None):
	"""True daca fisierul pozitiei motorului (HdsMotorPozitie) are vreun tuner: motorul a fost folosit pe receptor"""
	try:
		with open(fisier or FISIER_POZITII, "rb") as f:
			date = json.loads(f.read().decode("utf-8"))
		sloturi = date.get("sloturi") or {}
		return any(isinstance(v, dict) for v in sloturi.values())
	except Exception:
		return False


def migrat():
	"""Numai semnul din settings hotaraste: settings venit dintr-o copie mai veche (fara semn) se migreaza din nou, cu
	valorile vechi, ca si la prima pornire. Fisierul e doar rezerva cand config nu se poate citi."""
	try:
		s = initConfig()
		return bool(s.migrat.value)
	except Exception:
		return os.path.exists(FISIER_SEMN)


def _salveazaSettings():
	from Components.config import configfile
	configfile.save()


def _scrieSemn():
	nou = FISIER_SEMN + ".nou"
	try:
		with open(nou, "w", encoding="utf-8") as f:
			f.write("locul antenei: migrarea facuta\n")
		os.replace(nou, FISIER_SEMN)
	except Exception as e:
		jurnal("semnul migrarii nu s-a putut scrie (%r); ramane cel din settings" % (e,))


def _puneLocul(s, loc, tara, oras, sursa):
	s.lat.value = int(loc[0])
	s.lon.value = int(loc[1])
	s.tara.value = tara or ""
	s.oras.value = oras or ""
	s.sursa.value = sursa
	s.stabilit.value = True
	for el in (s.stabilit, s.lat, s.lon, s.tara, s.oras, s.sursa):
		el.save()


def migreaza():
	"""Migrarea propriu-zisa, pe elementele din config (vezi planMigrare). Se noteaza in settings si in FISIER_SEMN,
	abia dupa ce settings e scris."""
	s = initConfig()
	grupuri = grupuriConfig()
	intrare = [{"nume": nume, "motor": motor, "scrise": _cheiScrise(sectiune)} for nume, sectiune, motor in grupuri]
	plan = planMigrare(intrare, pozitiiExista())
	dupa_nume = dict((nume, sectiune) for nume, sectiune, _m in grupuri)
	for nume, camp, text in plan["scrie"]:
		el = _camp(dupa_nume[nume], camp)
		el.value = el.fromstring(text)
		el.save_forced = True
		el.save()
	if plan["locul"] is not None:
		_puneLocul(s, plan["locul"], "", "", SURSA_MIGRARE)
	s.migrat.value = True
	s.migrat.save()
	_salveazaSettings()
	_scrieSemn()
	if plan["locul"] is not None:
		jurnal("migrare: motor gasit, locul de pana acum ramane (%s); chei scrise: %d" % (
			textCoordonate(plan["locul"][0], plan["locul"][1], 3), len(plan["scrie"])))
	else:
		jurnal("migrare: niciun motor; locul ramane nestabilit pana il alege omul")
	return plan


def _preiaDinTuner(s):
	"""Locul nestabilit, dar un tuner cu motor are coordonatele scrise explicit in settings (o copie de setari mai
	veche pusa la loc dupa migrare): acelea sunt alese de om, deci devin locul unic."""
	for _nume, sectiune, motor in grupuriConfig():
		if not motor:
			continue
		scrise = _cheiScrise(sectiune)
		if "latitude" not in scrise or "longitude" not in scrise:
			continue
		valori = dict(VECHI)
		valori.update(dict((c, str(_valoare(sectiune, c))) for c in ("latitudeOrientation", "longitudeOrientation")))
		valori["latitude"], valori["longitude"] = scrise["latitude"], scrise["longitude"]
		loc = coordonateGrup(valori)
		if loc == (0, 0):
			# implicitul neutru scris cumva explicit nu e un loc ales de om
			continue
		_puneLocul(s, loc, "", "", SURSA_TUNER)
		_salveazaSettings()
		jurnal("locul luat din coordonatele scrise ale tunerului: %s" % textLoc())
		return True
	return False


def sincronizeaza():
	"""Copiile fara nicio cheie a locului in settings iau locul unic (locul stabilit). Intoarce cate s-au scris."""
	l = locul()
	if l is None:
		return 0
	n = 0
	for _nume, sectiune, _motor in grupuriConfig():
		if _cheiScrise(sectiune):
			continue
		_scrieGrup(sectiune, l[0], l[1])
		n += 1
	return n


def laPornire():
	"""Chemata din NimManager.InitNimManager, dupa ce config.Nims e complet si inainte de SecConfigure: migrarea (o
	data), locul luat din coordonatele scrise ale unui tuner cu motor (cand e nestabilit), copiile fara chei."""
	try:
		s = initConfig()
		if not migrat():
			migreaza()
		if not s.stabilit.value:
			_preiaDinTuner(s)
		if sincronizeaza():
			_salveazaSettings()
	except Exception as e:
		jurnal("pornirea: %r" % (e,))


# ---------------------------------------------------------------- alegerea locului

def _miscareInCurs():
	try:
		from Components import HdsMotorTuner
		sec = HdsMotorTuner.controlSec()
		return sec is not None and int(sec.hdsRotorMovingSlot()) >= 0
	except Exception:
		return False


def _inregistrareInCurs():
	"""True cat merge o inregistrare (sau lista lor nu se poate citi): sec.update() schimba LNB-urile nucleului si uita
	pozitia motorului, deci nu se face sub o inregistrare (aceeasi regula ca la comenzile motorului si la Configurare
	LNB)"""
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
	except Exception:
		return False
	if nav is None:
		return False
	try:
		return bool(nav.getRecordings())
	except Exception:
		return True


def _actualizeazaSec():
	"""nucleul primeste copiile noi (si, cu locul stabilit, satelitii USALS). sec.update() uita pozitia motorului pe
	toate tunerele (sec.cpp:1020-1021): urmatorul acord trimite din nou comanda, acum cu locul cel bun."""
	try:
		from Components.NimManager import nimmanager
		nimmanager.sec.update()
		return True
	except Exception as e:
		jurnal("sec.update() dupa schimbarea locului: %r" % (e,))
		return False


_ascultatori = []


def laSchimbare(functie):
	"""`functie()` se cheama dupa fiecare loc scris cu seteaza(), de oriunde vine (ecranul de pe televizor, pagina web):
	ecranul deschis isi arata singur locul nou. Cine se aboneaza se si dezaboneaza (nuMaiAscultaLaSchimbare)."""
	if functie not in _ascultatori:
		_ascultatori.append(functie)


def nuMaiAscultaLaSchimbare(functie):
	if functie in _ascultatori:
		_ascultatori.remove(functie)


def _anunta():
	"""fiecare abonat primeste anuntul; unul care cade nu-i opreste pe ceilalti"""
	for functie in list(_ascultatori):
		try:
			functie()
		except Exception as e:
			jurnal("abonat la schimbarea locului: %r" % (e,))


def seteaza(lat_mii, lon_mii, tara="", oras="", sursa=SURSA_MANA, actualizeaza_sec=True):
	"""Locul nou: locul unic, toate copiile din config.Nims, settings scris, nucleul la zi. (True, "") sau (False,
	motivul pentru om). Dupa ce locul e scris, abonatii (laSchimbare) afla."""
	try:
		lat_mii, lon_mii = int(lat_mii), int(lon_mii)
	except (TypeError, ValueError):
		return False, _t(MESAJ_LIMITE)
	if not (-LAT_MAX <= lat_mii <= LAT_MAX and -LON_MAX <= lon_mii <= LON_MAX):
		return False, _t(MESAJ_LIMITE)
	if _miscareInCurs():
		return False, _t(MESAJ_MISCARE)
	if actualizeaza_sec and _inregistrareInCurs():
		return False, _t(MESAJ_INREGISTRARE)
	s = initConfig()
	_puneLocul(s, (lat_mii, lon_mii), tara, oras, sursa)
	# locul dupa internet tine felul "internet"; orice loc ales de om (tabel, de mana) opreste aflarea singura
	s.mod.value = MOD_INTERNET if sursa == SURSA_INTERNET else MOD_ALES
	s.mod.save()
	for _nume, sectiune, _motor in grupuriConfig():
		_scrieGrup(sectiune, lat_mii, lon_mii)
	_salveazaSettings()
	if actualizeaza_sec:
		_actualizeazaSec()
	jurnal("locul antenei: %s" % textLoc())
	_anunta()
	return True, ""


# Locul scris de mana, judecat dupa tara receptorului (ROT, 14.11.2026, asistenta 681415, Turcia): omul alesese corect
# Sultanbeyli din tabel, apoi a scris de mana "30,000 S, 41,000 V" si "41,000 S, 29,000 V" (numerele bune, emisferele
# schimbate cu sagetile, prima data si latitudinea cu longitudinea inversate, ordinea din Setarile tunerului altor
# imagini). USALS a trimis antena spre capatul cursei, iar ecranul spunea mereu ca se misca. Un loc mai departe de
# PRAG_DEPARTE_KM de orice oras al tarii din tabel, cu o varianta apropiata, se intreaba inainte de scriere.
PRAG_DEPARTE_KM = 800


def _distantaKm(lat1, lon1, lat2, lon2):
	"""distanta pe glob (formula haversinus, raza medie 6371 km), coordonatele in grade"""
	import math
	f1, f2 = math.radians(lat1), math.radians(lat2)
	df, dl = f2 - f1, math.radians(lon2 - lon1)
	a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
	return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


def taraVerificare():
	"""Tara dupa care se judeca un loc scris de mana: cea aleasa ultima data din tabel, altfel tara limbii meniului
	(NimManager.taraReceptorului); "" cand niciuna nu are orase in tabel."""
	try:
		tara = initConfig().tara.value
		if tara and orase(tara):
			return tara
	except Exception:
		pass
	try:
		from Components import NimManager
		tara = NimManager.taraReceptorului()
		if tara and orase(tara):
			return tara
	except Exception:
		pass
	return ""


def variantaPotrivita(lat_mii, lon_mii, tara=None):
	"""Pentru un loc scris de mana: (lat_mii, lon_mii) ale variantei cu emisferele schimbate sau cu latitudinea si
	longitudinea inversate care e aproape de tara (cel mult PRAG_DEPARTE_KM de un oras al ei din tabel), cand locul scris
	e departe de toate orasele ei; altfel None (locul pare bun, tara nu se stie sau nicio varianta nu se potriveste:
	omul poate fi chiar in alta tara)."""
	tara = taraVerificare() if tara is None else tara
	lista = orase(tara) if tara else []
	if not lista:
		return None
	lat_mii, lon_mii = int(lat_mii), int(lon_mii)

	def departe(lat, lon):
		return min(_distantaKm(lat / 1000.0, lon / 1000.0, o[1] / 1000.0, o[2] / 1000.0) for o in lista)

	if departe(lat_mii, lon_mii) <= PRAG_DEPARTE_KM:
		return None
	variante = set()
	for a, b in ((lat_mii, lon_mii), (lon_mii, lat_mii)):
		if abs(a) > LAT_MAX or abs(b) > LON_MAX:
			continue
		for semn_a in (1, -1):
			for semn_b in (1, -1):
				variante.add((semn_a * abs(a), semn_b * abs(b)))
	variante.discard((lat_mii, lon_mii))
	cea = None
	for v in sorted(variante):
		d = departe(v[0], v[1])
		if d <= PRAG_DEPARTE_KM and (cea is None or d < cea[0]):
			cea = (d, v)
	return cea[1] if cea else None


def intrebareDeparte(lat_mii, lon_mii, tara=None):
	"""(textul intrebarii, (lat_mii, lon_mii) propuse) pentru televizor si web, sau (None, None) cand nu e nimic de
	intrebat"""
	tara = taraVerificare() if tara is None else tara
	v = variantaPotrivita(lat_mii, lon_mii, tara)
	if v is None:
		return None, None
	return _t(MESAJ_DEPARTE) % {"scris": textCoordonate(lat_mii, lon_mii, 3), "tara": _t(numeTara(tara)),
		"propus": textCoordonate(v[0], v[1], 3)}, v


def seteazaOras(tara, oras):
	"""locul din tabel: (True, "") sau (False, motivul)"""
	loc = gasesteOras(tara, oras)
	if loc is None:
		return False, _t(MESAJ_ORAS)
	return seteaza(loc[0], loc[1], tara, nfc(oras), SURSA_TABEL)


# ---------------------------------------------------------------- miscarile care cer locul

def _nims():
	from Components.config import config
	return config.Nims


def cereLoc(slot, orbital=None):
	"""True daca acordul tunerului `slot` pe `orbital` (sau pe oricare satelit, cu orbital=None) ar roti antena cu
	calculul USALS, adica dupa loc. Aceeasi regula ca SecConfigure (NimManager.py): simplu „positioner" = toti
	satelitii; avansat = LNB cu DiSEqC 1.2 si „Use usals" pe satelit, sau LNB-urile „toti satelitii" 34-36 (33 fara
	usals merge pe pozitia memorata)."""
	try:
		nim = _nims()[slot]
		mod = nim.configMode.value
		if mod == "simple":
			return nim.diseqcMode.value == "positioner"
		if mod != "advanced":
			return False
		sateliti = nim.advanced.sat
		lnburi = nim.advanced.lnb

		def ceLnb(orb):
			try:
				return int(sateliti[orb].lnb.value)
			except Exception:
				return 0

		def lnbCere(numar, orb):
			if not numar or numar not in lnburi:
				return False
			sectiune = lnburi[numar]
			if numar > 32:
				return bool(sateliti[3604 - (36 - numar)].usals.value) or numar >= 34
			return _valoare(sectiune, "diseqcMode") == "1_2" and bool(sateliti[orb].usals.value)

		toate = [ceLnb(x) for x in range(3601, 3605)]
		if orbital is None:
			if any(lnbCere(n, None) for n in toate if n):
				return True
			return any(lnbCere(ceLnb(orb), orb) for orb in list(sateliti.keys()) if int(orb) < 3600)
		numar = ceLnb(orbital)
		if numar:
			return lnbCere(numar, orbital)
		return any(lnbCere(n, orbital) for n in toate if n)
	except Exception as e:
		jurnal("cereLoc(%s, %s): %r" % (slot, orbital, e))
		return False


def refuzUsals(slot, orbital=None):
	"""textul refuzului cand o miscare USALS ar porni cu locul nestabilit sau spre un satelit sub orizont din locul
	antenei, altfel None"""
	if stabilit():
		if orbital is not None and not vizibilDinLoc(orbital) and cereLoc(slot, int(orbital)):
			return textSubOrizont(orbital)
		return None
	if cereLoc(slot, orbital):
		return _t(MESAJ_FARA_LOC)
	return None


def gradeOrbital(orbital):
	"""pozitia orbitala (0..3599, vestul peste 1800) in grade, est pozitiv"""
	orbital = int(orbital)
	return (orbital - 3600) / 10.0 if orbital > 1800 else orbital / 10.0


def elevatieDinLoc(orbital, loc=None):
	"""elevatia satelitului `orbital` din locul antenei (grade, cu refractia, ca nucleul: Components/DishMath.py), sau
	None cand locul nu e stabilit"""
	loc = locul() if loc is None else loc
	if loc is None:
		return None
	try:
		from Components import DishMath
	except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
		import DishMath
	try:
		return DishMath.elevation(gradeOrbital(orbital) % 360.0, loc[0] / 1000.0, (loc[1] / 1000.0) % 360.0)
	except (ValueError, ZeroDivisionError, TypeError):
		return -99.0


def vizibilDinLoc(orbital, loc=None):
	"""True cand satelitul e deasupra orizontului din locul antenei sau cand locul nu se stie (atunci hotaraste regula
	locului nestabilit); False numai cand locul e stabilit si satelitul e sub orizont (ar fi si peste arcul vizibil al
	motorului, Components/HdsMotorPlafon.py)"""
	e = elevatieDinLoc(orbital, loc)
	return e is None or e >= 0.0


def textSubOrizont(orbital, loc=None):
	loc = locul() if loc is None else loc
	try:
		from Components import HdsGrade
	except ImportError:
		import HdsGrade
	return _t(MESAJ_SUB_ORIZONT) % {"loc": textCoordonate(loc[0], loc[1], 3) if loc else u"",
		"sat": HdsGrade.pozitie(gradeOrbital(orbital))}


def blocatDeOrizont(orbital):
	"""True daca satelitul `orbital` nu se poate prinde fiindca e sub orizont din locul stabilit: cel putin un tuner l-ar
	prinde cu motorul USALS si niciun tuner nu il prinde fara USALS (antena fixa, pozitie memorata); ca blocatDeLoc."""
	if not stabilit() or vizibilDinLoc(orbital):
		return False
	try:
		from Components.NimManager import nimmanager
		gasit = False
		for nim in nimmanager.nim_slots:
			try:
				if not nim.isCompatible("DVB-S"):
					continue
				if int(orbital) not in [int(x[0]) for x in nimmanager.getSatListForNim(nim.slot)]:
					continue
			except Exception:
				continue
			if cereLoc(nim.slot, int(orbital)):
				gasit = True
			else:
				return False
		return gasit
	except Exception as e:
		jurnal("blocatDeOrizont(%s): %r" % (orbital, e))
		return False


def blocatDeLoc(orbital):
	"""True daca satelitul `orbital` nu se poate prinde acum numai fiindca locul nu e stabilit: cel putin un tuner l-ar
	prinde cu motorul USALS si niciun tuner nu il prinde fara loc (antena fixa, pozitie memorata)."""
	if stabilit():
		return False
	try:
		from Components.NimManager import nimmanager
		gasit = False
		for nim in nimmanager.nim_slots:
			try:
				if not nim.isCompatible("DVB-S"):
					continue
				if int(orbital) not in [int(x[0]) for x in nimmanager.getSatListForNim(nim.slot)]:
					continue
			except Exception:
				continue
			if cereLoc(nim.slot, int(orbital)):
				gasit = True
			else:
				return False
		return gasit
	except Exception as e:
		jurnal("blocatDeLoc(%s): %r" % (orbital, e))
		return False


def orbitalDinReferinta(ref):
	"""pozitia orbitala (0..3599) a unui serviciu DVB-S din referinta lui (namespace >> 16), sau None"""
	try:
		text = ref.toString() if hasattr(ref, "toString") else str(ref)
		campuri = text.split(":")
		ns = int(campuri[6], 16)
	except Exception:
		return None
	orbital = (ns >> 16) & 0xFFFF
	if orbital in (0xEEEE, 0xFFFF) or orbital >= 3600:
		return None
	return orbital


# Gradele din "Coordonatele antenei" tastate ca la calculator (LOC, 14.11.2026, orion_bilo, LinuxSat comment7467, GigaBlue
# UHD Quad 4K Pro). ConfigFloat (ConfigSequence, config.py) scrie fiecare cifra pe o pozitie fixa a campului de grade (2
# pozitii la latitudine, 3 la longitudine). In ordinea veche omul scria "030" pe primul rand (latitudinea): "03" si zeroul in
# zecimale, deci "zeroul din fata nu intra, numai la coada". Cu longitudinea pe primul rand ramanea capcana mai rea: "30"
# dadea 3 pe sute (300, strans la 180), apoi 100, adica 100 E, fara niciun semn. Aici cifrele gradelor se aduna ca la
# calculator: "30" si "030" dau 30; "41" si "041" dau 41 la latitudine; campul trece singur la zecimale cand mai
# are 3 cifre sau cand inca o cifra ar trece peste maxim (90 sau 180). Zecimalele raman pe pozitii, ca pana acum.
# DREAPTA din grade sare la zecimale, STANGA din zecimale intoarce la inceputul gradelor; la intoarcerea pe rand se
# incepe iar de la grade. Setarile tunerului (NimManager, ConfigFloat 0..359) nu se schimba.
_CLASA_GRADE = []


def _clasaGrade():
	if _CLASA_GRADE:
		return _CLASA_GRADE[0]
	from Components import config as C

	class ConfigGradeCalculator(C.ConfigFloat):
		def __init__(self, default, limits):
			C.ConfigFloat.__init__(self, default=default, limits=limits)
			self.hdsCifre = ""

		def hdsLatime(self):
			"""cate pozitii are campul gradelor pe ecran (2 pentru 90, 3 pentru 180)"""
			return len(str(self.limits[0][1]))

		def handleKey(self, key):
			latime = self.hdsLatime()
			if key in C.KEY_NUMBERS or key == C.KEY_ASCII:
				if self.marked_pos >= latime:
					self.hdsCifre = ""
					return C.ConfigFloat.handleKey(self, key)
				if key == C.KEY_ASCII:
					cod = C.getPrevAsciiCode()
					if cod < 48 or cod > 57:
						return
					cifra = cod - 48
				else:
					cifra = C.getKeyNumber(key)
				maxim = self.limits[0][1]
				self.hdsCifre += str(cifra)
				self._value[0] = min(int(self.hdsCifre), maxim)
				if len(self.hdsCifre) >= 3 or int(self.hdsCifre + "0") > maxim:
					self.hdsCifre = ""
					self.marked_pos = latime
				else:
					self.marked_pos = min(len(self.hdsCifre), latime - 1)
				self.changed()
				return
			self.hdsCifre = ""
			inainte = self.marked_pos
			C.ConfigFloat.handleKey(self, key)
			if key == C.KEY_LEFT and self.marked_pos < latime:
				self.marked_pos = 0
			elif key == C.KEY_RIGHT and inainte < latime:
				self.marked_pos = latime

		def onSelect(self, session):
			self.hdsCifre = ""
			self.marked_pos = 0
			C.ConfigFloat.onSelect(self, session)

		def onDeselect(self, session):
			self.hdsCifre = ""
			C.ConfigFloat.onDeselect(self, session)

	_CLASA_GRADE.append(ConfigGradeCalculator)
	return ConfigGradeCalculator


def campGrade(maxim, valoare_mii):
	"""campul de grade al ecranului "Coordonatele antenei": `maxim` 90 (latitudinea) sau 180 (longitudinea), valoarea
	absoluta in miimi de grad; [grade, miimi] ca ConfigFloat, cu gradele tastate ca la calculator"""
	valoare_mii = abs(int(valoare_mii))
	return _clasaGrade()(default=[valoare_mii // 1000, valoare_mii % 1000], limits=[(0, int(maxim)), (0, 999)])
