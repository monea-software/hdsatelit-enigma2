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
#   - tarile si orasele (Components/HdsLocuriDate.py, din GeoNames, CC BY 4.0), cu ordinea alfabetica romaneasca;
#   - locul aflat dupa adresa de internet (Components/HdsLoculInternet.py) intra tot prin seteaza(), cu sursa
#     SURSA_INTERNET, numai dupa confirmarea omului; se arata ca un oras din tabel;
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
	return s


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
		rez.update(tara=s.tara.value, tara_nume=numeTara(s.tara.value), oras=s.oras.value, sursa=s.sursa.value,
			coordonate=textCoordonate(l[0], l[1], _zecimale(s.sursa.value)))
	except Exception as e:
		jurnal("locul nu se poate citi: %r" % (e,))
	return rez


# ---------------------------------------------------------------- textele

def _zecimale(sursa):
	return 2 if sursa in (SURSA_TABEL, SURSA_INTERNET) else 3


def textCoordonate(lat_mii, lon_mii, zecimale=2):
	"""„44,43 N, 26,11 E" in romana (V pentru vest, ca in Rotirea antenei), „44.43 N, 26.11 W" in engleza: literele si
	separatorul zecimal ale limbii meniului, din Components/HdsGrade.py, ca pozitiile satelitilor si pagina /antena/locul"""
	try:
		from Components import HdsGrade
	except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
		import HdsGrade
	return HdsGrade.coordonate(int(lat_mii) / 1000.0, int(lon_mii) / 1000.0, zecimale)


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
		# o tara care nu e in tabel (locul dupa internet) se arata cu codul ei
		tara = numeTara(s.tara.value) or s.tara.value
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


def orase(cod):
	"""[(nume, lat_mii, lon_mii)] ale tarii `cod`, in ordinea alfabetica romaneasca"""
	cheie = "orase-" + str(cod)
	if cheie not in _cache:
		lista = [(nfc(nume), int(lat) * 10, int(lon) * 10) for c, nume, lat, lon in _date().ORASE if c == cod]
		_cache[cheie] = sorted(lista, key=lambda o: cheieRomaneasca(o[0]))
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
	for _nume, sectiune, _motor in grupuriConfig():
		_scrieGrup(sectiune, lat_mii, lon_mii)
	_salveazaSettings()
	if actualizeaza_sec:
		_actualizeazaSec()
	jurnal("locul antenei: %s" % textLoc())
	_anunta()
	return True, ""


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
	"""textul refuzului cand o miscare USALS ar porni cu locul nestabilit, altfel None"""
	if stabilit():
		return None
	if cereLoc(slot, orbital):
		return _t(MESAJ_FARA_LOC)
	return None


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
