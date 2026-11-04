# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# Catalogul se citeste pe fir separat; in memorie ramane numai pagina ceruta.

from collections import OrderedDict
import copy
import re
import threading
import time
import uuid

from Components import HdsIptvClient as C
from Components import HdsIptvSurse as I


def N_(text):
	return text


E_SURSA = N_("Alege un cont pentru seriale.")
E_DATE = N_("Serialul sau sezonul ales nu mai este disponibil.")
E_OCUPAT = N_("Se încarcă alte pagini. Încearcă din nou peste câteva clipe.")
E_EXPIRAT = N_("Pagina a expirat. Deschide din nou lista de seriale.")
E_LUNG = N_("Lista de seriale nu a răspuns la timp. Încearcă o căutare mai precisă.")
T_SEZOANE_LIMITA = N_("Serialul are prea multe sezoane. Sunt afișate primele 500.")
PE_PAGINA = 50
MAX_SEZOANE = 500
MAX_CERERI = 16
MAX_PAGINA = 20000
PASTREAZA_S = 120
TERMEN_S = 45
_NUMAR = re.compile(r"^[0-9]{1,12}$")
_EXT = re.compile(r"^[A-Za-z0-9]{1,5}$")
_lacat = threading.Lock()
_lucrari = OrderedDict()
_coada = []
_fir = None


def _numar(text):
	text = str(text) if text is not None else ""
	return text if _NUMAR.fullmatch(text) else ""


def _text(text, maxim=2000):
	if not isinstance(text, (str, int, float)):
		return ""
	return " ".join("".join(c if ord(c) >= 32 and ord(c) != 127 and c not in "<>" else " "
		for c in str(text)).split())[:maxim]


def _argumente(sid, serial_id, sezon, pagina, cautare):
	if not isinstance(sid, str) or not re.fullmatch(r"[0-9a-f]{8}", sid):
		raise ValueError(E_SURSA)
	serial_id, sezon = str(serial_id or ""), str(sezon or "")
	if (serial_id and not _numar(serial_id)) or (sezon and (not serial_id or not _numar(sezon))):
		raise ValueError(E_DATE)
	try:
		pagina = int(pagina)
	except (TypeError, ValueError):
		raise ValueError(E_DATE)
	if not 0 <= pagina <= MAX_PAGINA:
		raise ValueError(E_DATE)
	return sid, serial_id, sezon, pagina, _text(cautare, 80)


def _pagina(randuri, pagina):
	inceput = pagina * PE_PAGINA
	gasite, altele = [], False
	for i, rand in enumerate(randuri):
		if i < inceput:
			continue
		if len(gasite) == PE_PAGINA:
			altele = True
			break
		gasite.append(rand)
	return gasite, altele


def _catalog(sursa, cautare):
	inceput = time.monotonic()
	lista = C.listaXtream(sursa, "get_series")
	try:
		for obj in lista:
			if time.monotonic() - inceput > TERMEN_S:
				raise C.EroareIptv(E_LUNG)
			if not isinstance(obj, dict):
				continue
			serial_id = _numar(obj.get("series_id"))
			nume = _text(obj.get("name"), 300)
			if serial_id and nume and (not cautare or cautare.casefold() in nume.casefold()):
				yield {"id": serial_id, "nume": nume, "descriere": _text(obj.get("plot"))}
	finally:
		inchide = getattr(lista, "close", None)
		if inchide:
			inchide()


def _episoade(lista):
	for obj in lista:
		if not isinstance(obj, dict):
			continue
		episod_id = _numar(obj.get("id"))
		ext = str(obj.get("container_extension") or "mp4").lower()
		if not episod_id or not _EXT.fullmatch(ext):
			continue
		info = obj.get("info") if isinstance(obj.get("info"), dict) else {}
		yield {"id": episod_id, "cheie": "e%s.%s" % (episod_id, ext), "nume": _text(obj.get("title"), 300) or episod_id,
			"numar": _text(obj.get("episode_num"), 20), "descriere": _text(info.get("plot")),
			"durata": _text(info.get("duration"), 30)}


def lucreaza(sid, serial_id="", sezon="", pagina=0, cautare=""):
	"""O pagina publica, fara adrese, antete sau date de acces. Numai pe firul de lucru."""
	try:
		sid, serial_id, sezon, pagina, cautare = _argumente(sid, serial_id, sezon, pagina, cautare)
	except ValueError as e:
		return {"result": False, "message": str(e)}
	sursa = I.sursa(sid)
	if not sursa or sursa.get("fel") != "xtream":
		return {"result": False, "message": E_SURSA}
	rez = {"result": True, "id": sid, "serial": serial_id, "sezon": sezon, "pagina": pagina,
		"cautare": cautare, "nivel": "seriale", "titlu": "", "descriere": "", "message": ""}
	try:
		if not serial_id:
			catalog = _catalog(sursa, cautare)
			try:
				rez["randuri"], rez["altele"] = _pagina(catalog, pagina)
			finally:
				catalog.close()
			return rez
		date = C.dateXtream(sursa, "get_series_info", {"series_id": serial_id})
		if not isinstance(date, dict) or not isinstance(date.get("episodes"), dict):
			raise C.EroareIptv(E_DATE)
		info = date.get("info") if isinstance(date.get("info"), dict) else {}
		rez["titlu"], rez["descriere"] = _text(info.get("name"), 300), _text(info.get("plot"))
		episoade = date["episodes"]
		if not sezon:
			rez["nivel"] = "sezoane"
			# Detaliile sunt limitate la 2 MB de client; nu se pastreaza catalogul brut.
			sezoane = sorted((k for k in episoade if _numar(k) and isinstance(episoade[k], list)), key=int)
			if len(sezoane) > MAX_SEZOANE:
				rez["message"] = T_SEZOANE_LIMITA
			sezoane = sezoane[:MAX_SEZOANE]
			rez["randuri"], rez["altele"] = _pagina(({"id": k, "numar": k,
				"episoade": len(episoade[k])} for k in sezoane), pagina)
		else:
			rez["nivel"] = "episoade"
			lista = episoade.get(sezon)
			if not isinstance(lista, list):
				raise C.EroareIptv(E_DATE)
			rez["randuri"], rez["altele"] = _pagina(_episoade(lista), pagina)
		return rez
	except C.EroareIptv as e:
		return {"result": False, "message": e.mesaj}
	except Exception:
		# Exceptiile HTTP pot contine parola; nu ies nici in pagina, nici in jurnal.
		return {"result": False, "message": C.E_NU_RASPUNDE}


def _curata():
	acum = time.monotonic()
	for cheie, lucrare in list(_lucrari.items()):
		if lucrare.get("gata") and acum - lucrare["gata"] > PASTREAZA_S:
			del _lucrari[cheie]


def _bucla():
	global _fir
	while True:
		with _lacat:
			if not _coada:
				_fir = None
				return
			cheie = _coada.pop(0)
			argumente = _lucrari[cheie]["argumente"]
		rez = lucreaza(*argumente)
		with _lacat:
			_lucrari[cheie]["rezultat"] = rez
			_lucrari[cheie]["gata"] = time.monotonic()


def cere(sid, serial_id="", sezon="", pagina=0, cautare=""):
	"""Intoarce imediat cheia lucrarii; rezultat(cheie) se citeste din UI/web. Gol = coada plina."""
	global _fir
	try:
		argumente = _argumente(sid, serial_id, sezon, pagina, cautare)
	except ValueError:
		return ""
	with _lacat:
		_curata()
		for cheie, lucrare in _lucrari.items():
			if lucrare["argumente"] == argumente:
				return cheie
		if len(_lucrari) >= MAX_CERERI:
			terminate = [k for k, v in _lucrari.items() if v.get("gata")]
			if not terminate:
				return ""
			del _lucrari[terminate[0]]
		cheie = uuid.uuid4().hex
		_lucrari[cheie] = {"argumente": argumente}
		_coada.append(cheie)
		if _fir is None:
			_fir = threading.Thread(target=_bucla, name="HdsIptvSeriale")
			_fir.daemon = True
			_fir.start()
	return cheie


def rezultat(cheie):
	with _lacat:
		_curata()
		lucrare = _lucrari.get(cheie)
		if lucrare is None:
			return {"result": False, "lucreaza": False, "message": E_EXPIRAT}
		if not lucrare.get("gata"):
			return {"result": True, "lucreaza": True, "cerere": cheie}
		return dict(copy.deepcopy(lucrare["rezultat"]), lucreaza=False, cerere=cheie)


def episodDinPagina(cheie, episod):
	"""Redarea accepta numai un episod dintr-o pagina ceruta si inca pastrata."""
	rez = rezultat(cheie)
	if rez.get("result") and rez.get("nivel") == "episoade" and not rez.get("lucreaza"):
		for rand in rez.get("randuri", ()):
			if rand.get("cheie") == episod:
				sursa = I.sursa(rez["id"])
				if sursa and sursa.get("fel") == "xtream":
					return I.refCanal(rez["id"], episod)
	return None
