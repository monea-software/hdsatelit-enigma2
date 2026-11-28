# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Vreme comuna pentru tema, afisaj si web. Memoria nu se scrie pe disc.

import errno
import json
import math
import os
import socket
import threading
import time
from datetime import date as DataCalendar
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PERIOADA = 30 * 60
# AS179 (0.8.0): dupa o cerere cazuta (retea, open-meteo, orasul negasit) urmatoarea vine dupa acesti pasi, nu dupa
# PERIOADA; dupa ultimul pas ramane PERIOADA. Dupa un refuz de limita (HTTP 429, 503) tot PERIOADA, ca sa nu se ceara des
# (Tools/Weatherinfo.py, DRG). Jurnalul are un rand la primul esec dintr-un sir si unul la revenire.
REINCERCARI = (60, 120, 300, 600)
CODURI_LIMITA = (429, 503)
TIMEOUT = 8
MAX_RASPUNS = 128 * 1024
UNITATI = ("C", "F", "K")
TEME = ("nu", "bara", "principal", "ambele")
ZILE = ("1", "2", "3")
SCARI = ("100", "85", "75")
# VRM6 (pirobi1, LinuxSat 164191 #971391): locul vremii cand e in bara canalului: "sus" langa ceas, in randul emisiunii
# (din fabrica, ca acum), sau "jos" = panoul mai mare din coltul din dreapta al barei, cum era inainte de 0.7.7
LOCURI_BARA = ("sus", "jos")
POZE = "/usr/share/enigma2/vremea"
PROGNOZA = "https://api.open-meteo.com/v1/forecast"
GEOCODARE = "https://geocoding-api.open-meteo.com/v1/search"
TABEL_FUSURI = "/usr/share/zoneinfo/zone.tab"
_FUS_TARA = {}


def N_(text):
	return text


MESAJE_CAUTARE = {
	"nume_scurt": N_("Scrie cel puțin două litere din numele orașului."),
	"nume_invalid": N_("Numele orașului nu este valid."),
	"fara_retea": N_("Rețeaua nu este disponibilă. Verifică legătura la internet și încearcă din nou."),
	"serviciu": N_("Serviciul de căutare a orașelor nu răspunde. Încearcă din nou mai târziu."),
	"fara_rezultate": N_("Nu s-a găsit niciun oraș. Încearcă numele fără diacritice sau în engleză."),
}


def _t(text):
	try:
		import builtins
		return builtins._(text)
	except (ImportError, AttributeError):
		return text


def _numar(v):
	if isinstance(v, bool):
		raise ValueError("Numar nevalid")
	v = float(v)
	if not math.isfinite(v):
		raise ValueError("Numar nevalid")
	return v


def temperatura(celsius, unitate="C"):
	v = _numar(celsius)
	if unitate == "F":
		return v * 1.8 + 32
	if unitate == "K":
		return v + 273.15
	if unitate != "C":
		raise ValueError("Unitate necunoscuta")
	return v


def textTemperatura(celsius, unitate="C"):
	if celsius is None:
		return ""
	v = temperatura(celsius, unitate)
	# Jumatatile se rotunjesc in afara lui zero, la fel in toate locurile.
	n = int(math.copysign(math.floor(abs(v) + 0.5), v))
	return "%d%s" % (n, "K" if unitate == "K" else "°" + unitate)


def textPatru(celsius, unitate="C"):
	t = textTemperatura(celsius, unitate)
	if len(t) <= 4:
		return t
	if unitate != "K":
		t = t[:-1]
	if len(t) <= 4:
		return t
	# Nu taiem semnul sau cifrele unei temperaturi care nu incape.
	return "----"


def initConfig():
	from Components.config import config, ConfigSubsection
	from Components.config import ConfigSelection, ConfigText, ConfigYesNo
	if "hds_vremea" not in config.content.items:
		config.hds_vremea = ConfigSubsection()
		c = config.hds_vremea
		# aceleasi texte ca alegerile din ecranul Vremea (Screens/HdsVremea.UNITATI si LOCURI), traduse la afisare
		c.unitate = ConfigSelection(default="C", choices=[
			("C", N_("Celsius")), ("F", N_("Fahrenheit")), ("K", N_("Kelvin"))])
		c.oras = ConfigText(default="", fixed_size=False)
		c.tema = ConfigSelection(default="nu", choices=[
			("nu", N_("Nu")), ("bara", N_("Bara canalului")),
			("principal", N_("Ecranul principal")), ("ambele", N_("Ambele"))])
		# 0.7.8 (CR3, Ozgur 18.11.2026): omul a ales "Vremea pe TV" macar o data (pe televizor sau in web). enigma2 nu salveaza
		# valoarea egala cu cea din fabrica, deci "Nu" ales de om nu se deosebeste altfel de "Nu" din fabrica (seteaza).
		c.tema_aleasa = ConfigYesNo(default=False)
	c = config.hds_vremea
	if not hasattr(c, "zile"):
		c.zile = ConfigSelection(default="1", choices=[
			("1", N_("1 zi")), ("2", N_("2 zile")), ("3", N_("3 zile"))])
	if not hasattr(c, "scara"):
		c.scara = ConfigSelection(default="100", choices=[(v, v + "%") for v in SCARI])
	if not hasattr(c, "loc_bara"):
		c.loc_bara = ConfigSelection(default="sus", choices=[
			("sus", N_("Sus, lângă ceas")), ("jos", N_("Jos în dreapta, mai mare"))])
	return config.hds_vremea


def _text(v, maxim):
	if not isinstance(v, str) or len(v) > maxim:
		raise ValueError("Text nevalid")
	if any(ord(c) < 32 or ord(c) == 127 for c in v):
		raise ValueError("Text nevalid")
	return v.strip()


def _oras(v):
	if isinstance(v, str):
		if len(v) > 1000:
			raise ValueError("Oras nevalid")
		v = json.loads(v)
	if not isinstance(v, dict):
		raise ValueError("Oras nevalid")
	nume = _text(v.get("nume"), 160)
	lat = _numar(v.get("latitudine"))
	lon = _numar(v.get("longitudine"))
	fus = _text(v.get("fus", ""), 80)
	if not nume or not -90 <= lat <= 90 or not -180 <= lon <= 180:
		raise ValueError("Oras nevalid")
	return dict(nume=nume, latitudine=round(lat, 2),
		longitudine=round(lon, 2), fus=fus)


def codOras(v):
	return json.dumps(_oras(v), ensure_ascii=False, sort_keys=True,
		separators=(",", ":"))


def setari():
	try:
		c = initConfig()
		rez = dict(unitate=c.unitate.value, oras=c.oras.value,
			tema=c.tema.value, oras_nume="",
			zile=getattr(getattr(c, "zile", None), "value", "1"),
			scara=getattr(getattr(c, "scara", None), "value", "100"),
			loc_bara=getattr(getattr(c, "loc_bara", None), "value", "sus"))
		if rez["oras"]:
			rez["oras_nume"] = _oras(rez["oras"])["nume"]
		return rez
	except (ImportError, KeyError, AttributeError, TypeError, ValueError):
		return dict(unitate="C", oras="", oras_nume="", tema="nu", zile="1", scara="100", loc_bara="sus")


def seteaza(valori):
	if not isinstance(valori, dict) or set(valori) - {"unitate", "oras", "tema", "zile", "scara", "loc_bara"}:
		return False, _t("Setare necunoscută.")
	nou = {}
	try:
		for k, v in valori.items():
			if k == "unitate" and v not in UNITATI:
				raise ValueError()
			if k == "tema" and v not in TEME:
				raise ValueError()
			if k == "zile" and v not in ZILE:
				raise ValueError()
			if k == "scara" and v not in SCARI:
				raise ValueError()
			if k == "loc_bara" and v not in LOCURI_BARA:
				raise ValueError()
			nou[k] = codOras(v) if k == "oras" and v != "" else v
	except (TypeError, ValueError, OverflowError):
		return False, _t("Alegerea nu este validă.")
	c = initConfig()
	# Restore both active and saved values when the common writer reports failure.
	vechi = [(e, e.value, getattr(e, "saved_value", None))
		for e in [getattr(c, k) for k in nou] + ([c.tema] if "tema" not in nou else [])
		+ ([c.tema_aleasa] if hasattr(c, "tema_aleasa") else [])]
	mesaj = _t("Vremea este setată.")
	# 0.7.8 (CR3, Ozgur 18.11.2026, regula 1f): cine alege un oras vrea sa vada vremea; cu "Vremea pe TV" lasat pe "Nu" din
	# fabrica nu aparea nicaieri si parea o greseala. Alegerea unui oras nou o pune singura in bara canalului si o spune;
	# un "Nu" ales de om (tema_aleasa) ramane, iar cine nu alege oras ramane cum era.
	schimbat = False
	# Pe televizor si in web la fel: webul trimite mereu toate cele trei campuri, deci "ales de om" = schimbat de om.
	aleasa = getattr(c, "tema_aleasa", None)
	tema_schimbata = "tema" in nou and nou["tema"] != c.tema.value
	if aleasa is None:
		pass
	elif tema_schimbata:
		if not aleasa.value:
			aleasa.value = True
			aleasa.save()
			schimbat = True
	elif nou.get("oras") and nou["oras"] != c.oras.value and c.tema.value == "nu" and not aleasa.value:
		nou["tema"] = "bara"
		mesaj = _t("Vremea apare acum în bara canalului.")
	for k, v in nou.items():
		e = getattr(c, k)
		if e.value != v:
			e.value = v
			e.save()
			schimbat = True
	if schimbat:
		from Components.config import configfile
		try:
			configfile.save()
			# The common writer returns None on success and on disk failure.
			# Its last-written text confirms persistence without opening user files.
			if hasattr(configfile, "_scris"):
				from Components.config import config
				if hasattr(config, "pickle") and configfile._scris != config.pickle():
					raise OSError("Weather settings were not written")
		except (IOError, OSError):
			for e, valoare, salvata in vechi:
				e.value = valoare
				if hasattr(e, "saved_value"):
					e.saved_value = salvata
				else:
					e.save()
			return False, _t("Setările vremii nu se pot salva acum.")
	return True, mesaj


def _citesteJson(url):
	r = Request(url, headers={"User-Agent": "HDSatelit-Vremea/1",
		"Accept": "application/json"})
	with urlopen(r, timeout=TIMEOUT) as raspuns:
		raw = raspuns.read(MAX_RASPUNS + 1)
	if len(raw) > MAX_RASPUNS:
		raise ValueError("Raspuns prea mare")
	v = json.loads(raw.decode("utf-8"))
	if not isinstance(v, dict) or v.get("error"):
		raise ValueError("Raspuns nevalid")
	return v


def _limbaOrase():
	"""Numele oraselor urmeaza limba meniului, inclusiv limba de rezerva."""
	try:
		from Components.Language import limbaInterfata
		valoare = limbaInterfata()
	except (ImportError, AttributeError):
		valoare = ""
	if not valoare:
		try:
			from Components.config import config
			valoare = config.osd.language.value
		except (ImportError, AttributeError, KeyError):
			valoare = ""
	if isinstance(valoare, str):
		cod = valoare.strip().lower().replace("-", "_").split("_")[0]
		if len(cod) == 2 and cod.isascii() and cod.isalpha():
			return cod
	return "en"


def cautaOrase(nume):
	"""Apel cu retea: ecranele si web il ruleaza pe fir separat."""
	nume = _text(nume, 80)
	if len(nume) < 2:
		return []
	v = _citesteJson(GEOCODARE + "?" + urlencode(dict(
		name=nume, count=20, language=_limbaOrase(), format="json")))
	lista = v.get("results", [])
	if not isinstance(lista, list):
		raise ValueError("Lista de orase nevalida")
	rez, vazute = [], set()
	for oras in lista[:20]:
		try:
			parti = [oras["name"], oras.get("admin1"), oras.get("country")]
			eticheta = ", ".join(dict.fromkeys(p for p in parti if p))
			o = _oras(dict(nume=eticheta,
				latitudine=oras["latitude"], longitudine=oras["longitude"],
				fus=oras.get("timezone", "")))
			cod = codOras(o)
			if cod not in vazute:
				vazute.add(cod)
				rez.append(o)
		except (KeyError, TypeError, ValueError, OverflowError):
			continue
	if lista and not rez:
		raise ValueError("Orase nevalide")
	return rez


def mesajCautare(motiv):
	return _t(MESAJE_CAUTARE.get(motiv, MESAJE_CAUTARE["serviciu"]))


def _faraRetea(eroare):
	"""Ruta sau rezolvarea numelui lipseste, fara o alta cerere de retea."""
	coduri = {getattr(errno, nume, None) for nume in
		("ENETDOWN", "ENETUNREACH", "EHOSTDOWN", "EHOSTUNREACH")}
	coduri.discard(None)
	# URLError pastreaza eroarea de socket in reason.
	for _pas in range(4):
		if isinstance(eroare, socket.gaierror):
			return True
		if isinstance(eroare, OSError) and eroare.errno in coduri:
			return True
		motiv = getattr(eroare, "reason", None)
		if not isinstance(motiv, BaseException) or motiv is eroare:
			break
		eroare = motiv
	return False


def cautaOraseRezultat(nume):
	"""Un singur rezultat si aceleasi motive pentru ecran si interfata web."""
	try:
		nume = _text(nume, 80)
	except (TypeError, ValueError):
		motiv = "nume_invalid"
	else:
		if len(nume) < 2:
			motiv = "nume_scurt"
		else:
			try:
				orase = cautaOrase(nume)
			except Exception as eroare:
				motiv = "fara_retea" if _faraRetea(eroare) else "serviciu"
			else:
				motiv = "" if orase else "fara_rezultate"
				return dict(result=True, orase=orase, motiv=motiv,
					message=mesajCautare(motiv) if motiv else "")
	return dict(result=False, orase=[], motiv=motiv, message=mesajCautare(motiv))


def _fus():
	fus = os.environ.get("TZ", "").lstrip(":")
	try:
		from Components.config import config
		from Components.Timezones import timezones
		ales = config.timezone.val.value
		fus = next((z for n, z in timezones.timezones
			if ales in (n, z)), fus)
	except (ImportError, AttributeError, KeyError):
		pass
	if not fus:
		try:
			fus = os.path.realpath("/etc/localtime").split("/zoneinfo/")[1]
		except (OSError, IndexError):
			pass
	return fus


def orasImplicit():
	"""Orasul fusului, niciodata coordonatele antenei sau localizare IP."""
	fus = _fus()
	if "/" not in fus or fus.startswith(("Etc/", "SystemV/")):
		fus = _fusDinTara()
	if fus == "Europe/Bucharest":
		return dict(nume="București", latitudine=44.43,
			longitudine=26.1, fus=fus)
	if "/" in fus and not fus.startswith(("Etc/", "SystemV/")):
		return dict(cauta=fus.rsplit("/", 1)[-1].replace("_", " "), fus=fus)
	return None


def _fusDinTara():
	try:
		from Components.config import config
		tara = config.hds_locul.tara.value
	except (ImportError, AttributeError, KeyError):
		return ""
	if not isinstance(tara, str) or len(tara) != 2 or not tara.isalpha():
		return ""
	tara = tara.upper()
	if tara not in _FUS_TARA:
		_FUS_TARA[tara] = ""
		try:
			with open(TABEL_FUSURI, "r", encoding="utf-8") as f:
				for linie in f.read(128 * 1024).splitlines():
					campuri = linie.split()
					if len(campuri) >= 3 and tara in campuri[0].split(","):
						_FUS_TARA[tara] = campuri[2]
						break
		except (OSError, UnicodeError):
			pass
	return _FUS_TARA[tara]


def _stare(cod, zi=True):
	if cod == 0:
		return (N_("Soare"), "soare") if zi else (N_("Senin"), "noapte")
	if cod in (1, 2):
		return N_("Parțial noros"), "nori"
	if cod == 3:
		return N_("Noros"), "nori"
	if cod in (45, 48):
		return N_("Ceață"), "ceata"
	if cod in (51, 53, 55, 56, 57):
		return N_("Burniță"), "ploaie"
	if cod in (61, 63, 65, 66, 67, 80, 81, 82):
		return N_("Ploaie"), "ploaie"
	if cod in (71, 73, 75, 77, 85, 86):
		return N_("Ninsoare"), "zapada"
	if cod in (95, 96, 97, 99):
		return N_("Furtună"), "furtuna"
	return N_("Stare necunoscută"), "nori"


def _prognoza(v, oras):
	curent = v["current"]
	t = _numar(curent["temperature_2m"])
	if not -150 <= t <= 100:
		raise ValueError("Temperatura nevalida")
	stare, poza = _stare(int(curent["weather_code"]),
		bool(curent.get("is_day", 1)))
	rez = dict(temperatura=t, oras=oras["nume"], stare=stare,
		pictograma=POZE + "/" + poza + ".png", cod=int(curent["weather_code"]),
		actualizat=time.time())
	zile = v.get("daily")
	if not isinstance(zile, dict):
		zile = {}
	rez["zile"] = []
	for zi, i in (("azi", 0), ("maine", 1), ("poimaine", 2)):
		# Data si codul provin din aceeasi pozitie a seriilor furnizorului.
		# Nu construim o zi lipsa adunand 24 de ore si nu reutilizam codul de azi.
		data = _ziPrognoza(_seriePrognoza(zile, "time", i))
		cod = _codPrognoza(_seriePrognoza(zile, "weather_code", i))
		rez[zi + "_data"], rez[zi + "_cod"] = data, cod
		zi_date = dict(data=data, cod=cod)
		for fel in ("min", "max"):
			try:
				v = _numar(_seriePrognoza(zile, "temperature_2m_" + fel, i))
				if not -150 <= v <= 100:
					raise ValueError("Temperatura nevalida")
				rez[zi + "_" + fel] = v
			except (TypeError, ValueError, OverflowError):
				rez[zi + "_" + fel] = None
			zi_date[fel] = rez[zi + "_" + fel]
		rez["zile"].append(zi_date)
	return rez


def _seriePrognoza(zile, cheie, i):
	lista = zile.get(cheie)
	return lista[i] if isinstance(lista, (list, tuple)) and i < len(lista) else None


def _ziPrognoza(valoare):
	if not isinstance(valoare, str) or len(valoare) != 10:
		return None
	try:
		return DataCalendar.fromisoformat(valoare).isoformat()
	except ValueError:
		return None


def _codPrognoza(valoare):
	try:
		cod = _numar(valoare)
		return int(cod) if 0 <= cod <= 99 and cod == int(cod) else None
	except (TypeError, ValueError, OverflowError):
		return None


class Serviciu(object):
	def __init__(self, citeste_json=None, ceas=None):
		self._citeste_json = citeste_json or _citesteJson
		self._ceas = ceas or time.monotonic
		self._lacat = threading.Lock()
		self._cheie = None
		self._date = {}
		self._urmator = 0
		self._ocupat = False
		self._fir = None
		self._esecuri = 0

	def _esec(self, cheie, motiv, limita=False):
		"""Cererea pentru `cheie` a cazut: urmatoarea dupa pasul din REINCERCARI, sau dupa PERIOADA la un refuz de limita
		(apelat sub lacat)."""
		if cheie != self._cheie:
			return
		pas = REINCERCARI[self._esecuri] if self._esecuri < len(REINCERCARI) and not limita else PERIOADA
		self._esecuri += 1
		self._urmator = self._ceas() + pas
		if self._esecuri == 1:
			print("[HdsVremea] cerere esuata: %s; reincerc in %d s" % (motiv, pas))

	def citeste(self, oras):
		"""Intoarce imediat memoria; cel mult un fir pentru cererea noua."""
		cheie = json.dumps(oras, sort_keys=True, ensure_ascii=False)
		with self._lacat:
			if cheie != self._cheie:
				self._cheie = cheie
				self._date = {}
				self._urmator = 0
				self._esecuri = 0
			if oras and not self._ocupat and self._ceas() >= self._urmator:
				self._ocupat = True
				self._urmator = self._ceas() + PERIOADA
				self._fir = threading.Thread(target=self._lucreaza,
					args=(dict(oras), cheie), name="HdsVremea")
				self._fir.daemon = True
				self._fir.start()
			return dict(self._date)

	def _lucreaza(self, oras, cheie):
		try:
			if "cauta" in oras:
				lista = cautaOrase(oras["cauta"])
				oras = next((o for o in lista if o["fus"] == oras["fus"]), None)
				if oras is None:
					with self._lacat:
						self._esec(cheie, "orasul cautat nu a fost gasit")
					return
			oras = _oras(oras)
			url = PROGNOZA + "?" + urlencode(dict(
				latitude=oras["latitudine"], longitude=oras["longitudine"],
				current="temperature_2m,weather_code,is_day",
				daily="temperature_2m_min,temperature_2m_max,weather_code",
				forecast_days=3, temperature_unit="celsius", timezone="auto"))
			nou = _prognoza(self._citeste_json(url), oras)
			with self._lacat:
				if cheie == self._cheie:
					self._date = nou
					if self._esecuri:
						print("[HdsVremea] cererea merge din nou dupa %d esecuri" % self._esecuri)
					self._esecuri = 0
		except Exception as e:
			# Fara retea ramane ultima valoare a aceluiasi oras.
			with self._lacat:
				self._esec(cheie, "%s: %s" % (e.__class__.__name__, e), getattr(e, "code", None) in CODURI_LIMITA)
		finally:
			with self._lacat:
				self._ocupat = False


_serviciu = Serviciu()


def date():
	s = setari()
	try:
		oras = _oras(s["oras"]) if s["oras"] else orasImplicit()
	except (TypeError, ValueError):
		oras = None
	return _serviciu.citeste(oras)
