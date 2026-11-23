# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFusTara.py: fusul orar aflat dupa adresa de internet, de pe serverul nostru, numai cat omul nu l-a ales singur.
#
# De ce: inainte, Timezones.autoDetectTimezone intreba un serviciu strain (ip-api.com) o singura data, la pornirea
# interfetei, cu 2,5 s de asteptare: la prima pornire reteaua nu era inca gata, deci fusul ramanea Europe/Bucharest
# pana la o repornire; iar la fiecare pornire cu internet suprascria fusul, si cand omul alesese altul (cu VPN: fus
# gresit). Acum:
#   - config.timezone.automat (Da implicit): Nu = fusul ales de om, nu se mai atinge. Devine Nu singur cand omul alege
#     un fus pe televizor (Screens/Time.py) sau in pagina web /ceas (Components/HdsCeas.seteaza); randul
#     "Fus orar dupa internet" il intoarce la Da;
#   - raspunsul vine de la serverul nostru (HdsLoculInternet.ADRESA, /receptor/locul): tara si coordonatele orasului.
#     Pentru UA: Europe/Kyiv sau aliasul Europe/Kiev, daca exista in lista ecranului; altfel fusul ramane neschimbat.
#     Pentru celelalte tari: campul "fus" daca serverul il da; altfel fusul tarii din /usr/share/zoneinfo/zone.tab (pachetul
#     tzdata-core, pe toate modelele) cel mai apropiat de coordonate (Spania: Madrid sau Canare; Rusia: 11 fusuri).
#     Numai fusurile din /etc/timezone.xml (lista ecranului) se pot pune. Niciun serviciu strain nu e intrebat;
#   - la prima pornire limba asistentului (Components/HdsLimbaTara.py) intreaba deja serverul: fusul foloseste acelasi
#     raspuns (o singura cerere). La celelalte porniri un fir propriu asteapta ruta implicita (fara conexiune, numai
#     tabelele nucleului) si reincearca pana la TERMEN_S (dupa flash certificatul poate parea nevalabil pana la NTP);
#   - dupa primul NTP reusit al pornirii (Components/HdsCeas.py), daca fusul nu s-a aflat inca, o incercare noua: la om
#     internetul vine uneori abia dupa o cadere, la zeci de minute;
#   - fusul se pune pe firul enigma2 (reactor.callFromThread), nu din fir: notificarea lui config.timezone.val schimba
#     /etc/localtime si TZ.
#
# Fisierul nu importa nimic din enigma la incarcare: probele de pe PC inlocuiesc reteaua, cererea, firul, fisierele
# si aplicarea.

import json
import math
import threading
import time

FISIER_ZONE = "/usr/share/zoneinfo/zone.tab"
MARIME_MAX = 4096
ASTEPTARE_RETEA_S = 60.0
PAS_RETEA_S = 1.0
TIMP_CERERE_S = 4.0
PAUZA_S = 5.0
TERMEN_S = 180.0
# cat asteapta firul raspunsul limbii la prima pornire (HdsLimbaTara.TERMEN_S e 90 s)
ASTEPTARE_LIMBA_S = 100.0

NIMIC = "nimic"
LUCREAZA = "lucreaza"
GATA = "gata"

_STARE = {"stare": NIMIC, "fus": "", "motiv": "", "dupa_ntp": False}
_ZAVOR = threading.Lock()


def N_(text):
	return text


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


RAND_AUTOMAT = N_("Fus orar după internet")
TEXT_AUTOMAT = N_("Fusul orar se află singur după internet, de la serverul HD Satelit, la fiecare pornire.")
TEXT_ALES = N_("Fusul orar l-ai ales tu și rămâne așa. Pentru cel aflat după internet, pune Da la Fus orar după internet.")


def jurnal(text):
	print("[HdsFusTara] %s" % text)


def stare():
	with _ZAVOR:
		return dict(_STARE)


def _pune(**valori):
	with _ZAVOR:
		_STARE.update(valori)


# ---------------------------------------------------------------- alegerea fusului (fara efecte)

def coordonate(text):
	"""coordonatele din zone.tab (ISO 6709: +DDMM+DDDMM sau +DDMMSS+DDDMMSS) -> (lat, lon) in grade; None daca nu"""
	if not isinstance(text, str) or len(text) < 11 or text[0] not in "+-":
		return None
	for i in range(1, len(text)):
		if text[i] in "+-":
			break
	else:
		return None
	a, b = text[:i], text[i:]

	def grade(t, cifre_grade):
		semn = -1 if t[0] == "-" else 1
		t = t[1:]
		if not t.isdigit() or len(t) not in (cifre_grade + 2, cifre_grade + 4):
			return None
		g, m, s = int(t[:cifre_grade]), int(t[cifre_grade:cifre_grade + 2]), int(t[cifre_grade + 2:] or 0)
		return semn * (g + m / 60.0 + s / 3600.0)
	lat, lon = grade(a, 2), grade(b, 3)
	if lat is None or lon is None:
		return None
	return lat, lon


def citesteZone(cale=None, text=None):
	"""zone.tab -> [(tara, lat, lon, fus)], in ordinea din fisier; [] daca lipseste"""
	if text is None:
		try:
			with open(cale or FISIER_ZONE, "r", encoding="utf-8") as f:
				text = f.read()
		except (IOError, OSError):
			return []
	zone = []
	for rand in text.splitlines():
		if not rand or rand.startswith("#"):
			continue
		c = rand.split("\t")
		if len(c) < 3 or len(c[0]) != 2:
			continue
		xy = coordonate(c[1])
		if xy is None:
			continue
		zone.append((c[0].upper(), xy[0], xy[1], c[2].strip()))
	return zone


def _numar(x, maxim):
	if isinstance(x, bool) or not isinstance(x, (int, float)):
		return None
	x = float(x)
	if math.isnan(x) or math.isinf(x) or not -maxim <= x <= maxim:
		return None
	return x


def dinRaspuns(corp):
	"""corpul raspunsului serverului (octeti) -> {"tara", "lat", "lon", "fus"}; lat/lon None si fus "" cand lipsesc.
	ValueError daca nu se poate folosi (fara codul tarii nu se stie nimic)."""
	if not isinstance(corp, (bytes, bytearray)) or len(corp) > MARIME_MAX:
		raise ValueError("raspuns lipsa sau prea mare")
	try:
		d = json.loads(bytes(corp).decode("utf-8"))
	except (UnicodeDecodeError, ValueError):
		raise ValueError("raspunsul nu e JSON")
	if not isinstance(d, dict):
		raise ValueError("raspunsul nu e un obiect")
	tara = d.get("tara")
	if not isinstance(tara, str) or len(tara) != 2 or not all("A" <= c <= "Z" for c in tara.upper()):
		raise ValueError("codul tarii lipseste sau nu e bun")
	lat, lon = _numar(d.get("lat"), 90), _numar(d.get("lon"), 180)
	if lat is None or lon is None or (abs(lat) < 0.01 and abs(lon) < 0.01):
		lat = lon = None
	fus = d.get("fus")
	if not isinstance(fus, str) or not 0 < len(fus) <= 64 or not all(ch.isalnum() or ch in "/_-+" for ch in fus):
		fus = ""
	return {"tara": tara.upper(), "lat": lat, "lon": lon, "fus": fus}


def distantaKm(lat1, lon1, lat2, lon2):
	f1, f2 = math.radians(lat1), math.radians(lat2)
	df, dl = f2 - f1, math.radians(lon2 - lon1)
	a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
	return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


def alegeFus(loc, zone, disponibile):
	"""loc (din dinRaspuns), zone (citesteZone), disponibile (fusurile din timezone.xml) -> (fus, motiv); fus "" cand
	nu se poate alege fara sa ghicim"""
	disponibile = set(disponibile or ())
	# Punctele din zone.tab nu delimiteaza teritoriul unui fus orar.
	if loc["tara"] == "UA":
		for fus in ("Europe/Kyiv", "Europe/Kiev"):
			if fus in disponibile:
				return fus, _t("Fusul automat pentru Ucraina.")
		return "", _t("Fusurile Europe/Kyiv și Europe/Kiev lipsesc din lista receptorului; fusul actual rămâne neschimbat.")
	if loc.get("fus") and loc["fus"] in disponibile:
		return loc["fus"], "fusul dat de server"
	ale_tarii = [z for z in zone if z[0] == loc["tara"] and z[3] in disponibile]
	if not ale_tarii:
		return "", "tara %s nu are niciun fus in lista receptorului" % loc["tara"]
	if len(ale_tarii) == 1:
		return ale_tarii[0][3], "singurul fus al tarii %s" % loc["tara"]
	if loc.get("lat") is None:
		return "", "tara %s are mai multe fusuri, iar serverul nu a dat locul" % loc["tara"]
	z = min(ale_tarii, key=lambda z: distantaKm(loc["lat"], loc["lon"], z[1], z[2]))
	return z[3], "cel mai apropiat fus al tarii %s" % loc["tara"]


# ---------------------------------------------------------------- semnul omului si fusurile ecranului (enigma)

def automat():
	"""True cat omul nu a ales singur fusul (config.timezone.automat); True si cand semnul nu exista inca"""
	try:
		from Components.config import config
		el = config.timezone.content.items.get("automat")
		return True if el is None else bool(el.value)
	except Exception:
		return True


def _disponibile():
	"""[(nume din ecran, fus)] din /etc/timezone.xml (Components/Timezones.py)"""
	from Components.Timezones import timezones
	return list(timezones.timezones)


def aplica(fus, motiv):
	"""Pe firul enigma2: pune fusul in config.timezone.val (notificarea lui schimba /etc/localtime), daca omul tot nu
	l-a ales intre timp. -> True daca s-a schimbat ceva."""
	if not automat():
		jurnal("fusul %s nu se pune: omul a ales intre timp fusul" % fus)
		return False
	from Components.config import config, configfile
	nume = next((a for (a, b) in _disponibile() if b == fus), None)
	if nume is None:
		return False
	el = config.timezone.val
	if el.value == nume:
		jurnal("fusul ramane %s (%s)" % (fus, motiv))
		return False
	el.value = nume
	el.save()
	configfile.save()
	jurnal("fusul pus dupa internet: %s (%s)" % (fus, motiv))
	return True


def _peFirulPrincipal(functie):
	principal = getattr(threading, "main_thread", None)
	if principal is not None and threading.current_thread() is principal():
		functie()
		return
	from twisted.internet import reactor
	reactor.callFromThread(functie)


# ---------------------------------------------------------------- cererea (pe fir)

def _locul():
	from Components import HdsLoculInternet
	return HdsLoculInternet


def _limba():
	from Components import HdsLimbaTara
	return HdsLimbaTara


def raspunsLimba(ceas=None, dormi=None, limba=None):
	"""La prima pornire: raspunsul pe care l-a primit cautarea limbii (asteapta cat ea lucreaza). -> (cod, corp) sau
	None daca limba nu a intrebat serverul (sau nu a primit raspuns)"""
	ceas = ceas or time.monotonic
	dormi = dormi or time.sleep
	try:
		L = limba or _limba()
		inceput = ceas()
		while L.inLucru():
			if ceas() - inceput >= ASTEPTARE_LIMBA_S:
				return None
			dormi(0.5)
		s = L.stare()
	except Exception:
		return None
	if s.get("cod") in (200, 404):
		return s["cod"], s.get("corp") or b""
	return None


def cere(retea_=None, citeste_url=None, ceas=None, dormi=None, adresa=None):
	"""Blocanta, numai pe fir: -> (cod, corp) sau (None, motiv)"""
	ceas = ceas or time.monotonic
	dormi = dormi or time.sleep
	if retea_ is None or citeste_url is None or adresa is None:
		L = _locul()
		retea_ = retea_ or L.retea
		citeste_url = citeste_url or L._citesteUrl
		adresa = adresa or L.ADRESA
	inceput = ceas()
	while not retea_():
		if ceas() - inceput >= ASTEPTARE_RETEA_S:
			return None, "fara retea"
		dormi(PAS_RETEA_S)
	while True:
		try:
			return citeste_url(adresa, TIMP_CERERE_S, MARIME_MAX)
		except Exception as e:
			motiv = "eroare de retea %s" % type(e).__name__
			if ceas() - inceput + PAUZA_S >= TERMEN_S:
				return None, motiv
			dormi(PAUZA_S)


def afla(raspuns=None, zone=None, disponibile=None, **k):
	"""-> (fus, motiv). `raspuns` = (cod, corp) deja primit (prima pornire); altfel o cerere."""
	cod, corp = raspuns if raspuns is not None else cere(**k)
	if cod is None:
		return "", corp
	if cod == 404:
		return "", "adresa fara loc in baza serverului"
	if cod != 200:
		return "", "serverul a raspuns HTTP %s" % cod
	try:
		loc = dinRaspuns(corp)
	except ValueError as e:
		return "", "raspunsul serverului nu se poate folosi (%s)" % e
	if zone is None:
		zone = citesteZone()
	if disponibile is None:
		disponibile = [b for (a, b) in _disponibile()]
	return alegeFus(loc, zone, disponibile)


def _lucreaza(prima, aplica_=None, pe_fir=None, **k):
	try:
		raspuns = raspunsLimba() if prima else None
		fus, motiv = afla(raspuns=raspuns, **k)
	except Exception as e:
		fus, motiv = "", "eroare %s" % type(e).__name__
	_pune(stare=GATA, fus=fus, motiv=motiv)
	if not fus:
		jurnal("fusul nu s-a aflat: %s" % motiv)
		return
	aplica_ = aplica_ or aplica
	(pe_fir or _peFirulPrincipal)(lambda: aplica_(fus, motiv))


def porneste(prima=False, fir=None, **k):
	"""Porneste aflarea pe un fir daemon (nu asteapta). Nimic daca omul a ales fusul sau daca firul lucreaza deja."""
	if not automat():
		return False
	with _ZAVOR:
		if _STARE["stare"] == LUCREAZA:
			return False
		_STARE.update(stare=LUCREAZA, fus="", motiv="")

	def functie():
		_lucreaza(prima, **k)
	if fir is not None:
		fir(functie)
		return True
	t = threading.Thread(target=functie, name="HdsFusTara")
	t.daemon = True
	t.start()
	return True


def laPornire(prima=None, **k):
	"""Din Components/SetupDevices.py, dupa limba (HdsLimbaTara.laPornire). Nu arunca."""
	try:
		_pune(stare=NIMIC, fus="", motiv="", dupa_ntp=False)
		if not automat():
			jurnal("fusul orar l-a ales omul: nu se cauta")
			return
		if prima is None:
			prima = _limba()._primaPornire()
		porneste(prima=prima, **k)
	except Exception as e:
		jurnal("aflarea fusului nu a pornit: %r" % (e,))


def dupaNtp(**k):
	"""Din Components/HdsCeas.py, pe firul enigma2, dupa un NTP reusit: o incercare noua, o data pe pornire, daca fusul
	nu s-a aflat inca. Nu arunca."""
	try:
		s = stare()
		if s["dupa_ntp"] or s["stare"] == LUCREAZA or (s["stare"] == GATA and s["fus"]):
			return False
		_pune(dupa_ntp=True)
		return porneste(prima=False, **k)
	except Exception as e:
		jurnal("aflarea fusului dupa NTP: %r" % (e,))
		return False


def omulAAles():
	"""Din ecran si din web, cand omul alege un fus: semnul Nu, salvat."""
	try:
		from Components.config import config
		el = config.timezone.content.items.get("automat")
		if el is not None and el.value:
			el.value = False
			el.save()
	except Exception as e:
		jurnal("semnul fusului ales: %r" % (e,))


def textStare():
	"""randul de stare pentru ecran si web"""
	return _t(TEXT_AUTOMAT) if automat() else _t(TEXT_ALES)
