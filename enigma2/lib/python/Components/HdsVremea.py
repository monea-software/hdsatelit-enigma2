# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Vreme comuna pentru tema, afisaj si web. Memoria nu se scrie pe disc.

import json
import math
import os
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PERIOADA = 30 * 60
TIMEOUT = 8
MAX_RASPUNS = 128 * 1024
UNITATI = ("C", "F", "K")
TEME = ("nu", "bara", "principal", "ambele")
POZE = "/usr/share/enigma2/vremea"
PROGNOZA = "https://api.open-meteo.com/v1/forecast"
GEOCODARE = "https://geocoding-api.open-meteo.com/v1/search"
TABEL_FUSURI = "/usr/share/zoneinfo/zone.tab"
_FUS_TARA = {}


def N_(text):
	return text


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
	from Components.config import ConfigSelection, ConfigText
	if "hds_vremea" not in config.content.items:
		config.hds_vremea = ConfigSubsection()
		c = config.hds_vremea
		c.unitate = ConfigSelection(default="C", choices=[
			("C", "Celsius"), ("F", "Fahrenheit"), ("K", "Kelvin")])
		c.oras = ConfigText(default="", fixed_size=False)
		c.tema = ConfigSelection(default="nu", choices=[
			("nu", "Nu"), ("bara", "Bara de informatii"),
			("principal", "Ecranul principal"), ("ambele", "Ambele")])
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
			tema=c.tema.value, oras_nume="")
		if rez["oras"]:
			rez["oras_nume"] = _oras(rez["oras"])["nume"]
		return rez
	except (ImportError, KeyError, AttributeError, TypeError, ValueError):
		return dict(unitate="C", oras="", oras_nume="", tema="nu")


def seteaza(valori):
	if not isinstance(valori, dict) or set(valori) - {"unitate", "oras", "tema"}:
		return False, _t("Setare necunoscută.")
	nou = {}
	try:
		for k, v in valori.items():
			if k == "unitate" and v not in UNITATI:
				raise ValueError()
			if k == "tema" and v not in TEME:
				raise ValueError()
			nou[k] = codOras(v) if k == "oras" and v != "" else v
	except (TypeError, ValueError, OverflowError):
		return False, _t("Alegerea nu este validă.")
	c = initConfig()
	schimbat = False
	for k, v in nou.items():
		e = getattr(c, k)
		if e.value != v:
			e.value = v
			e.save()
			schimbat = True
	if schimbat:
		from Components.config import configfile
		configfile.save()
	return True, _t("Vremea este setată.")


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


def cautaOrase(nume):
	"""Apel cu retea: ecranele si web il ruleaza pe fir separat."""
	nume = _text(nume, 80)
	if len(nume) < 2:
		return []
	v = _citesteJson(GEOCODARE + "?" + urlencode(dict(
		name=nume, count=20, language="ro", format="json")))
	rez, vazute = [], set()
	for oras in v.get("results", [])[:20]:
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
	return rez


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
	for zi, i in (("azi", 0), ("maine", 1)):
		for fel in ("min", "max"):
			lista = zile.get("temperature_2m_" + fel, [])
			try:
				if not isinstance(lista, (list, tuple)):
					raise ValueError("Serie nevalida")
				v = _numar(lista[i])
				if not -150 <= v <= 100:
					raise ValueError("Temperatura nevalida")
				rez[zi + "_" + fel] = v
			except (IndexError, TypeError, ValueError):
				rez[zi + "_" + fel] = None
	return rez


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

	def citeste(self, oras):
		"""Intoarce imediat memoria; cel mult un fir pentru cererea noua."""
		cheie = json.dumps(oras, sort_keys=True, ensure_ascii=False)
		with self._lacat:
			if cheie != self._cheie:
				self._cheie = cheie
				self._date = {}
				self._urmator = 0
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
					return
			oras = _oras(oras)
			url = PROGNOZA + "?" + urlencode(dict(
				latitude=oras["latitudine"], longitude=oras["longitudine"],
				current="temperature_2m,weather_code,is_day",
				daily="temperature_2m_min,temperature_2m_max",
				forecast_days=2, temperature_unit="celsius", timezone="auto"))
			nou = _prognoza(self._citeste_json(url), oras)
			with self._lacat:
				if cheie == self._cheie:
					self._date = nou
		except Exception:
			# Fara retea ramane ultima valoare a aceluiasi oras.
			pass
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
