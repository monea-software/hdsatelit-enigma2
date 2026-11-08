# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Pluginul cere prognoza redusa, datele pentru detalii si cautarea localitatilor.
# Toate modurile folosesc Open-Meteo pe un fir de lucru, fara cheie.

import builtins
import copy
from datetime import datetime
from gettext import gettext
import json
import math
import threading
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_GEOCODARE = "https://geocoding-api.open-meteo.com/v1/search"
_PROGNOZA = "https://api.open-meteo.com/v1/forecast"
_LIMITA = 2 * 1024 * 1024
_CURENT = (
	"temperature_2m", "relative_humidity_2m", "apparent_temperature",
	"is_day", "weather_code", "pressure_msl", "wind_speed_10m",
	"wind_direction_10m",
	"wind_gusts_10m", "visibility", "uv_index", "precipitation",
	"precipitation_probability",
)
_ZILNIC = (
	"weather_code", "temperature_2m_max", "temperature_2m_min",
	"sunrise", "sunset", "precipitation_probability_max",
	"wind_speed_10m_max", "wind_direction_10m_dominant",
	"apparent_temperature_max", "apparent_temperature_min",
	"wind_gusts_10m_max", "uv_index_max", "precipitation_sum",
)
_ORAR = (
	"temperature_2m", "apparent_temperature", "relative_humidity_2m",
	"pressure_msl", "precipitation_probability", "wind_speed_10m",
	"wind_gusts_10m", "wind_direction_10m", "uv_index", "visibility",
	"weather_code",
)

# Corespondenta proprie, cu tinte prezente in comutarile zi/noapte din dovezi.
# Mai multe coduri WMO impart o tinta; aspectul fontului nu apare in dovezi.
_WMO_ICON = {
	0: ("32", "B"), 1: ("34", "B"), 2: ("30", "H"),
	3: ("28", "H"), 45: ("28", "H"), 48: ("28", "H"),
	51: ("11", "J"), 53: ("11", "J"), 55: ("11", "J"),
	56: ("16", "J"), 57: ("16", "J"),
	61: ("12", "J"), 63: ("12", "J"), 65: ("12", "J"),
	66: ("16", "J"), 67: ("16", "J"),
	71: ("16", "J"), 73: ("16", "J"), 75: ("16", "J"), 77: ("16", "J"),
	80: ("40", "J"), 81: ("40", "J"), 82: ("40", "J"),
	85: ("42", "J"), 86: ("42", "J"),
	95: ("4", "3"), 97: ("4", "3"), 96: ("3", "3"), 99: ("3", "3"),
}
_WMO_TEXT = {
	0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
	45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle",
	55: "Dense drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
	61: "Light rain", 63: "Rain", 65: "Heavy rain",
	66: "Freezing rain", 67: "Freezing rain", 71: "Light snow",
	73: "Snow", 75: "Heavy snow", 77: "Snow grains",
	80: "Rain showers", 81: "Rain showers", 82: "Heavy rain showers",
	85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorm",
	96: "Thunderstorm with hail", 97: "Heavy thunderstorm",
	99: "Thunderstorm with hail",
}


def _sir(valoare):
	return "" if valoare is None else str(valoare)


def _data_iso(valoare):
	if isinstance(valoare, str):
		try:
			datetime.fromisoformat(valoare)
			return valoare
		except ValueError:
			pass
	return ""


def _valoare(valoare, implicit=""):
	if isinstance(valoare, (int, float)) and not isinstance(valoare, bool):
		return valoare if math.isfinite(valoare) else implicit
	return implicit


def _element(date, cheie, index, implicit=""):
	lista = date.get(cheie, [])
	if isinstance(lista, list) and 0 <= index < len(lista):
		return implicit if lista[index] is None else lista[index]
	return implicit


def _icons(cod):
	try:
		pereche = _WMO_ICON.get(int(cod), ("", ""))
	except (ValueError, TypeError, OverflowError):
		pereche = ("", "")
	return dict(zip(("yahooCode", "meteoCode"), pereche))


def _text(cod):
	try:
		text = _WMO_TEXT.get(int(cod), "")
	except (ValueError, TypeError, OverflowError):
		text = ""
	return getattr(builtins, "_", gettext)(text) if text else ""


def _direction(grade):
	grade = _valoare(grade, None)
	if grade is None:
		return " "
	index = int((grade % 360 + 22.5) // 45) % 8
	return ("↓ N", "↙ NE", "← E", "↖ SE", "↑ S", "↗ SW", "→ W", "↘ NW")[index]


def _perioada():
	date = dict.fromkeys((
		"date", "day", "shortDay", "text", "daySummary0", "nightSummary0",
		"source", "observationPoint", "observationTime", "sunrise", "sunset",
		"moonrise", "moonset", "temp", "feelsLike", "humidity", "raintext",
		"windDir", "uvIndex", "visibility", "pressure", "maxTemp", "minTemp",
		"maxFeelsLike", "minFeelsLike", "domWindDir", "maxUvIndex",
		"maxVisibility", "precipitation", "umbrellaIndex", "yahooCode", "meteoCode",
	), "")
	date.update(dict.fromkeys(("windSpeed", "windGusts", "maxWindSpeed", "maxWindGusts"), 0))
	date.update({"isNight": False, "windDirSign": " ", "domWindDirSign": " "})
	return date


def _detalii_ready(info, mode):
	if mode == "owm":
		return bool(info.get("list"))
	if mode == "msn":
		try:
			zile = info["responses"][0]["weather"][0]["forecast"]["days"]
			return bool(zile[0]["hourly"])
		except (KeyError, IndexError, TypeError):
			return False
	ora = info.get("hourly", {})
	timpi = ora.get("time", [])
	if not timpi:
		return False
	for i, timp in enumerate(timpi):
		try:
			datetime.fromisoformat(timp)
		except (ValueError, TypeError):
			return False
		for cheie in _ORAR:
			if _valoare(_element(ora, cheie, i), None) is None:
				return False
	zile = info.get("daily", {})
	numar_zile = len({timp[:10] for timp in timpi})
	return len(zile.get("sunrise", [])) == len(zile.get("sunset", [])) >= numar_zile > 0


def _redus(native, geodata, units):
	curent, zilnic, orar = native["current"], native["daily"], native["hourly"]
	imperial = units == "imperial"
	divizor = 1609.344 if imperial else 1000
	def vizibilitate(val):
		val = _valoare(val, None)
		return round(val / divizor, 2) if val is not None else ""

	def agregat(cheie, data, functie):
		valori = [
			_valoare(_element(orar, cheie, i), None)
			for i, timp in enumerate(orar["time"]) if _sir(timp).startswith(data + "T")
		]
		valori = [v for v in valori if v is not None]
		return functie(valori) if valori else ""

	prognoza = {}
	for i in range(max(5, len(zilnic["time"]))):
		zi = _perioada()
		data = _sir(_element(zilnic, "time", i))
		zi["date"] = data
		if data:
			moment = datetime.fromisoformat(data)
			zi["day"] = getattr(builtins, "_", gettext)(moment.strftime("%A"))
			zi["shortDay"] = getattr(builtins, "_", gettext)(moment.strftime("%a"))
		for cheie, camp in (
			("maxTemp", "temperature_2m_max"), ("minTemp", "temperature_2m_min"),
			("maxFeelsLike", "apparent_temperature_max"), ("minFeelsLike", "apparent_temperature_min"),
			("maxUvIndex", "uv_index_max"), ("precipitation", "precipitation_sum"),
			("umbrellaIndex", "precipitation_probability_max"),
		):
			zi[cheie] = _valoare(_element(zilnic, camp, i))
		zi["maxWindSpeed"] = _valoare(_element(zilnic, "wind_speed_10m_max", i), 0)
		zi["maxWindGusts"] = _valoare(_element(zilnic, "wind_gusts_10m_max", i), 0)
		grade = _valoare(_element(zilnic, "wind_direction_10m_dominant", i))
		zi["domWindDir"] = _sir(grade)
		zi["domWindDirSign"] = zi["windDirSign"] = _direction(grade)
		for cheie in ("sunrise", "sunset"):
			zi[cheie] = _sir(_element(zilnic, cheie, i))
		cod = _element(zilnic, "weather_code", i)
		zi.update(_icons(cod))
		zi["text"] = _text(cod)
		zi["pressure"] = agregat("pressure_msl", data, lambda v: round(sum(v) / len(v), 1)) if data else ""
		zi["maxVisibility"] = vizibilitate(agregat("visibility", data, max)) if data else ""
		prognoza[i] = zi

	acum = copy.deepcopy(prognoza[0])
	acum.update({
		"source": "Open-Meteo", "observationPoint": _sir(geodata[0]),
		"observationTime": _sir(curent.get("time")),
		"isNight": curent.get("is_day") == 0,
		"windDirSign": _direction(curent.get("wind_direction_10m")),
		"windDir": _sir(_valoare(curent.get("wind_direction_10m"))),
		"visibility": vizibilitate(curent.get("visibility")),
	})
	for cheie, camp in (
		("temp", "temperature_2m"), ("feelsLike", "apparent_temperature"),
		("humidity", "relative_humidity_2m"), ("pressure", "pressure_msl"),
		("uvIndex", "uv_index"), ("precipitation", "precipitation"),
		("umbrellaIndex", "precipitation_probability"),
	):
		acum[cheie] = _valoare(curent.get(camp))
	acum["windSpeed"] = _valoare(curent.get("wind_speed_10m"), 0)
	acum["windGusts"] = _valoare(curent.get("wind_gusts_10m"), 0)
	acum.update(_icons(curent.get("weather_code")))
	acum["text"] = _text(curent.get("weather_code"))
	return {
		"name": _sir(geodata[0]), "pressunit": "hPa", "tempunit": "°F" if imperial else "°C",
		"windunit": "mph" if imperial else "km/h", "visibiliyunit": "mile" if imperial else "km",
		"precunit": "inch" if imperial else "mm", "current": acum, "forecast": prognoza,
	}


def _json(url):
	cerere = Request(url, headers={"User-Agent": "HDSatelit-Weather/0.7.1"})
	with urlopen(cerere, timeout=10) as raspuns:
		continut = raspuns.read(_LIMITA + 1)
	if len(continut) > _LIMITA:
		raise ValueError("raspuns prea mare")
	date = json.loads(continut.decode("utf-8"))
	if not isinstance(date, dict) or date.get("error"):
		raise ValueError("raspuns meteo invalid")
	return date


def _coordonate(latitude, longitude):
	lat, lon = float(latitude), float(longitude)
	if not math.isfinite(lat) or not math.isfinite(lon):
		raise ValueError("coordonate invalide")
	if not -90 <= lat <= 90 or not -180 <= lon <= 180:
		raise ValueError("coordonate in afara limitelor")
	return lat, lon


def _gol():
	# Forma nativa este pastrata separat de dictionarul redus al pluginului.
	return {
		"latitude": "", "longitude": "", "timezone": "",
		"current": dict.fromkeys(("time",) + _CURENT, ""),
		"daily": {cheie: [] for cheie in ("time",) + _ZILNIC},
		"current_units": {}, "daily_units": {},
		"hourly": {cheie: [] for cheie in ("time",) + _ORAR}, "hourly_units": {},
		"utc_offset_seconds": 0,
	}


def _full_info(native, mode, geodata, units):
	# Detaliile citesc forma serviciului, pastrand separat datele Open-Meteo.
	from datetime import timedelta, timezone
	info = copy.deepcopy(native)
	info["open_meteo"] = copy.deepcopy(native)
	try:
		from Components.config import config
		windunit = config.plugins.OAWeather.windspeedMetricUnit.value
	except Exception:
		windunit = "km/h"
	windunit = "m/s" if windunit == "m/s" else "km/h"
	if windunit == "m/s":
		factor = 0.44704 if units == "imperial" else 1.0 / 3.6
	else:
		factor = 1.609344 if units == "imperial" else 1.0

	def wind_value(value):
		number = _valoare(value, None)
		return number * factor if number is not None else value

	hourly = info.get("hourly", {})
	if not isinstance(hourly, dict):
		hourly = {}
	aliases = {
		"relativehumidity_2m": "relative_humidity_2m",
		"windspeed_10m": "wind_speed_10m",
		"winddirection_10m": "wind_direction_10m",
		"weathercode": "weather_code",
	}
	for old, new in aliases.items():
		if new in hourly:
			hourly[old] = copy.deepcopy(hourly[new])
	for key in ("windspeed_10m", "wind_gusts_10m"):
		if isinstance(hourly.get(key), list):
			hourly[key] = [wind_value(value) for value in hourly[key]]
	hourunits = info.setdefault("hourly_units", {})
	if isinstance(hourunits, dict):
		hourunits["windspeed_10m"] = windunit
		hourunits["wind_gusts_10m"] = windunit
	info["hourly"] = hourly
	# Parserul itereaza rasaritul si indexeaza apusul cu acelasi indice.
	# Orele absente raman goale, fara evenimente astronomice inventate.
	for key in ("sunrise", "sunset"):
		info["daily"][key] = [
			_data_iso(_element(native["daily"], key, index))
			for index in range(len(native["daily"]["time"]))
		]
	if mode == "omw":
		return info

	current = info.get("current", {})
	if not isinstance(current, dict):
		current = {}
	daily = info.get("daily", {})
	if not isinstance(daily, dict):
		daily = {}
	current_aliases = {
		"relative_humidity_2m": "relativehumidity_2m",
		"wind_speed_10m": "windspeed_10m",
		"wind_direction_10m": "winddirection_10m",
		"weather_code": "weathercode",
	}
	for new, old in current_aliases.items():
		if new not in current and old in current:
			current[new] = current[old]
	offset = _valoare(info.get("utc_offset_seconds"), 0)
	if not -86400 < offset < 86400:
		offset = 0
	zone = timezone(timedelta(seconds=offset))

	def iso(value):
		value = _sir(value)
		try:
			datetime.fromisoformat(value)
		except (ValueError, TypeError):
			return ""
		return value

	def timestamp(value):
		value = iso(value)
		if not value:
			return 0
		date = datetime.fromisoformat(value)
		if date.tzinfo is None:
			date = date.replace(tzinfo=zone)
		return int(date.timestamp())

	def symbol(value):
		value = _valoare(value, None)
		return "hds-wmo:%d" % int(value) if value is not None else ""

	def numeric(target, source, fields):
		for outkey, inkey in fields.items():
			value = _valoare(source.get(inkey), None)
			if value is not None:
				target[outkey] = value

	raw_hourly = native.get("hourly", {})
	if not isinstance(raw_hourly, dict):
		raw_hourly = {}
	times = raw_hourly.get("time", [])
	if not isinstance(times, list):
		times = []
	rows = []
	for index, value in enumerate(times):
		value = iso(value)
		if value:
			row = {"time": value}
			for key in raw_hourly:
				if key != "time":
					row[key] = _element(raw_hourly, key, index, None)
			for old, new in aliases.items():
				if new not in row and old in row:
					row[new] = row[old]
			rows.append(row)

	if mode == "msn":
		fields = {
			"baro": "pressure_msl", "temp": "temperature_2m",
			"feels": "apparent_temperature", "rh": "relative_humidity_2m",
			"windSpd": "wind_speed_10m", "windDir": "wind_direction_10m",
			"windGust": "wind_gusts_10m", "uv": "uv_index",
		}

		def msn_row(source):
			text = _text(source.get("weather_code"))
			result = {"pvdrCap": "Open-Meteo", "raintext": text, "summary": text}
			numeric(result, source, fields)
			for key in ("windSpd", "windGust"):
				if key in result:
					result[key] = wind_value(result[key])
			visibility = _valoare(source.get("visibility"), None)
			if visibility is not None:
				result["vis"] = visibility / 1000.0
			result["symbol"] = symbol(source.get("weather_code"))
			return result

		weather_current = msn_row(current)
		weather_current["created"] = iso(current.get("time"))
		days = []
		daytimes = daily.get("time", [])
		if not isinstance(daytimes, list):
			daytimes = []
		for index, day in enumerate(daytimes):
			day = _sir(day)[:10]
			almanac = {
				"sunrise": iso(_element(daily, "sunrise", index)),
				"sunset": iso(_element(daily, "sunset", index)),
				"moonrise": "", "moonset": "",
			}
			# Fara ora curenta nu exista o comparatie corecta cu rasaritul.
			if index == 0 and not weather_current["created"]:
				almanac["sunrise"] = almanac["sunset"] = ""
			hours = []
			for row in rows:
				if row["time"][:10] == day:
					precip = _valoare(row.get("precipitation_probability"), None)
					if precip is None:
						continue
					hour = msn_row(row)
					hour["valid"] = row["time"]
					hour["precip"] = precip
					hours.append(hour)
			days.append({"almanac": almanac, "hourly": hours})
		if days:
			weather = {"current": weather_current, "forecast": {"days": days}}
			info["responses"] = [{"weather": [weather]}]
		return info

	if mode == "owm":
		def owm_row(source):
			main = {}
			wind = {}
			numeric(main, source, {
				"pressure": "pressure_msl", "temp": "temperature_2m",
				"feels_like": "apparent_temperature",
				"humidity": "relative_humidity_2m",
			})
			numeric(wind, source, {
				"speed": "wind_speed_10m", "deg": "wind_direction_10m",
				"gust": "wind_gusts_10m",
			})
			for key in ("speed", "gust"):
				if key in wind:
					wind[key] = wind_value(wind[key])
			result = {
				"main": main, "wind": wind,
				"weather": [{"id": symbol(source.get("weather_code")),
					"description": _text(source.get("weather_code"))}],
			}
			numeric(result, source, {"visibility": "visibility"})
			precip = _valoare(source.get("precipitation_probability"), None)
			if precip is not None:
				result["pop"] = precip / 100.0
			return result

		info.update(owm_row(current))
		info["dt"] = timestamp(current.get("time"))
		info["city"] = {
			"name": _sir(geodata[0]),
			"sunrise": timestamp(_element(daily, "sunrise", 0)),
			"sunset": timestamp(_element(daily, "sunset", 0)),
		}
		info["list"] = []
		for row in rows:
			item = owm_row(row)
			item["dt"] = timestamp(row["time"])
			item["dt_txt"] = datetime.fromtimestamp(item["dt"]).isoformat()
			info["list"].append(item)
	return info


class Weatherinfo:
	def __init__(self, mode="omw", apikey=""):
		# Toate modurile observate folosesc aici acelasi serviciu fara cheie.
		self._lock = threading.RLock()
		self._generation = 0
		self._thread = None
		self.callback = None
		self.info = {}
		self.set_mode(mode, apikey)

	def stop(self):
		# Cererea HTTP are timeout; oprirea nu asteapta firul si nu mai publica datele.
		with self._lock:
			self._generation += 1
			self._thread = None
			self.callback = None
			self._ready = False

	def set_mode(self, mode="omw", apikey=""):
		with self._lock:
			self.stop()
			self.mode = mode
			self.apikey = apikey
			self.info = {}
			self.error = None if mode in ("msn", "omw", "owm") else "mod meteo necunoscut"

	def get_data_ready(self):
		return self._ready and not self.error

	@staticmethod
	def direction_sign(grade):
		return _direction(grade)

	@staticmethod
	def convert2icon(source, code):
		# MSN/OWM sunt aici adaptoare locale; nu pretindem coduri ale altui serviciu.
		if isinstance(code, str) and code.startswith("hds-wmo:"):
			return _icons(code.split(":", 1)[1])
		return _icons(code) if str(source).upper() == "OMW" else _icons(None)

	def start(self, geodata=None, units="metric", scheme="en-GB", reduced=True, callback=None):
		# Resetarea vine si de pe worker. Callbackul poate cere o noua localitate.
		with self._lock:
			return self._start(geodata, units, scheme, reduced, callback)

	def _start(self, geodata, units, scheme, reduced, callback):
		self.stop()
		self.callback = callback
		self.info = {}
		self.error = None
		mode = self.mode

		def lucru():
			if mode not in ("msn", "omw", "owm"):
				raise ValueError("mod meteo necunoscut")
			if not isinstance(geodata, (tuple, list)) or len(geodata) != 3:
				raise ValueError("localitate invalida")
			if units not in ("metric", "imperial"):
				raise ValueError("unitati invalide")
			# Selectia pluginului pastreaza ordinea nume, longitudine, latitudine.
			date = self._weather(geodata[2], geodata[1], units)
			return _full_info(date, mode, geodata, units), _redus(date, geodata, units)

		def incheie(rezultat, eroare):
			self.error = eroare
			self.info = {} if eroare else rezultat[0]
			self._ready = not eroare and _detalii_ready(self.info, mode)
			date = None if eroare else (rezultat[1] if reduced else self.info)
			if self.callback is not None:
				self.callback(date, eroare)

		# scheme este limba ceruta; Open-Meteo da coduri, textele trec prin _().
		return self._lanseaza(lucru, incheie, None)

	def _citylist(self, weathercity, language, count):
		count = max(1, min(100, int(count)))
		limba = str(language or "en").replace("_", "-").split("-")[0].lower()
		url = _GEOCODARE + "?" + urlencode({
			"name": str(weathercity), "language": limba, "count": count,
			"format": "json",
		})
		date = _json(url)
		intrari = date.get("results", [])
		if not isinstance(intrari, list):
			raise ValueError("lista de localitati invalida")
		lista = []
		for intrare in intrari[:count]:
			if not isinstance(intrare, dict):
				continue
			try:
				lat, lon = _coordonate(intrare["latitude"], intrare["longitude"])
			except (KeyError, ValueError, TypeError, OverflowError):
				continue
			nume = ", ".join(dict.fromkeys(
				_sir(intrare.get(camp)) for camp in ("name", "admin1", "country") if intrare.get(camp)
			))
			if nume:
				lista.append((nume, str(lon), str(lat)))
		return lista

	def get_citylist(self, weathercity, language, count=15):
		# Apelul observat asteapta imediat o lista, fara callback.
		# Pe firul principal nu putem astepta reteaua; intoarcem esecul gol.
		if threading.current_thread() is threading.main_thread():
			self.error = "cautarea localitatilor necesita fir de lucru"
			return []
		try:
			lista = self._citylist(weathercity, language, count)
			self.error = None
			return lista
		except Exception as eroare:
			self.error = type(eroare).__name__
			return []

	def _weather(self, latitude, longitude, units="metric"):
		lat, lon = _coordonate(latitude, longitude)
		url = _PROGNOZA + "?" + urlencode({
			"latitude": lat, "longitude": lon, "timezone": "auto",
			"current": ",".join(_CURENT), "daily": ",".join(_ZILNIC),
			"hourly": ",".join(_ORAR),
			"forecast_days": 7, "temperature_unit": "fahrenheit" if units == "imperial" else "celsius",
			"wind_speed_unit": "mph" if units == "imperial" else "kmh",
			"precipitation_unit": "inch" if units == "imperial" else "mm",
		})
		date = _json(url)
		curent, zilnic = date.get("current"), date.get("daily")
		if not isinstance(curent, dict) or not isinstance(zilnic, dict):
			raise ValueError("date meteo lipsa")
		rezultat = _gol()
		for cheie in ("latitude", "longitude", "timezone", "utc_offset_seconds"):
			rezultat[cheie] = date.get(cheie, "")
		rezultat["utc_offset_seconds"] = _valoare(date.get("utc_offset_seconds"), 0)
		for cheie in rezultat["current"]:
			valoare = curent.get(cheie)
			rezultat["current"][cheie] = "" if valoare is None else valoare
		rezultat["current"]["time"] = _data_iso(rezultat["current"]["time"])
		for cheie in rezultat["daily"]:
			valoare = zilnic.get(cheie)
			rezultat["daily"][cheie] = ["" if v is None else v for v in valoare] if isinstance(valoare, list) else []
		for cheie in ("time", "sunrise", "sunset"):
			rezultat["daily"][cheie] = [_data_iso(v) for v in rezultat["daily"][cheie]]
		orar = date.get("hourly", {})
		if isinstance(orar, dict):
			for cheie in rezultat["hourly"]:
				valoare = orar.get(cheie)
				rezultat["hourly"][cheie] = ["" if v is None else v for v in valoare] if isinstance(valoare, list) else []
		for cheie in ("current_units", "daily_units", "hourly_units"):
			valoare = date.get(cheie)
			rezultat[cheie] = valoare if isinstance(valoare, dict) else {}
		return rezultat

	def _lanseaza(self, lucru, incheie, gol):
		with self._lock:
			generatie = self._generation

		def publica(date, eroare):
			with self._lock:
				if generatie != self._generation:
					return
				self._thread = None
				try:
					incheie(date, eroare)
				except Exception as esec:
					print("[Weatherinfo] callback: %s" % type(esec).__name__)

		try:
			from twisted.internet import reactor
		except Exception:
			self.error = "bucla principala indisponibila"
			if threading.current_thread() is threading.main_thread():
				publica(gol, self.error)
			return None

		def lucreaza():
			try:
				date, eroare = lucru(), None
			except Exception as esec:
				date, eroare = gol, type(esec).__name__
			try:
				reactor.callFromThread(publica, date, eroare)
			except Exception:
				with self._lock:
					if generatie == self._generation:
						self.error = "bucla principala indisponibila"

		try:
			fir = threading.Thread(target=lucreaza, name="Weatherinfo", daemon=True)
			self._thread = fir
			fir.start()
			return fir
		except Exception as esec:
			if threading.current_thread() is threading.main_thread():
				publica(gol, type(esec).__name__)
			else:
				try:
					reactor.callFromThread(publica, gol, type(esec).__name__)
				except Exception:
					self.error = "bucla principala indisponibila"
			return None

	def _request(self, lucru, callback, error_callback, gol):
		def incheie(date, esec):
			self.error = esec
			if esec and error_callback is not None:
				error_callback()
			elif callback is not None:
				callback(date)

		return self._lanseaza(lucru, incheie, gol)

	def request_citylist(self, weathercity, language, callback, error_callback=None, count=15):
		# Extensie proprie: callback(lista), error_callback(), pe firul principal.
		return self._request(
			lambda: self._citylist(weathercity, language, count),
			callback, error_callback, [],
		)

	def request_weather(self, latitude, longitude, callback, error_callback=None):
		# Extensie proprie: date Open-Meteo native; codurile vremii raman WMO.
		return self._request(
			lambda: self._weather(latitude, longitude),
			callback, error_callback, _gol(),
		)
