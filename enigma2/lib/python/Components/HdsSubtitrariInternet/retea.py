# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# retea.py: cererile HTTPS ale surselor de subtitrari, numai cu modulele standard (urllib, ssl cu certificatele
# sistemului). Ruleaza numai pe firul de lucru al descarcarii (lucru.py), niciodata pe firul enigma2.
#
# - un timp de asteptare pe fiecare cerere (TIMP_S) si o limita de marime a raspunsului (MAX_OCTETI);
# - cel putin PAUZA_S intre doua cereri catre aceeasi gazda (OpenSubtitles cere cel mult 5 pe secunda);
# - User-Agent „HDSatelit v<versiunea imaginii>”, cum cer sursele;
# - raspunsul vine ca (cod HTTP, antete, octeti); o eroare de retea ridica EroareRetea cu un text pentru om;
# - redirectionarile: numai http(s), fara coborare de pe https pe http, fara chei spre alta gazda (_Redirectionare).
# Nimic din cereri (antete cu chei, corpuri cu parole, raspunsuri cu jetoane) nu se scrie in jurnal.

import json
import ssl
import threading
import time

try:
	from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
	from urllib.error import HTTPError, URLError
	from urllib.parse import urlencode, urlsplit
except ImportError:  # Python 2 nu e tinta; importul nu trebuie sa cada pe unelte vechi
	Request = build_opener = HTTPSHandler = HTTPRedirectHandler = HTTPError = URLError = urlencode = urlsplit = None

TIMP_S = 20
MAX_OCTETI = 10 * 1024 * 1024
PAUZA_S = 0.25


class EroareRetea(Exception):
	"""O cerere care nu a ajuns la raspuns (fara retea, nume necunoscut, timp depasit, certificat). ceas: certificatul a
	cazut din cauza ceasului receptorului (textul comun din Components/HdsCeasHttps.py), acelasi la toate sursele."""
	ceas = False


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _mesajCeas(eroare):
	"""Textul comun „ceasul e în urmă” cand certificatul cade din cauza ceasului receptorului, altfel None. Verificarea
	certificatelor ramane pornita; aici se alege numai textul."""
	try:
		from Components import HdsCeasHttps
		return HdsCeasHttps.mesaj(eroare)
	except Exception:
		return None


def agent():
	"""User-Agent: „HDSatelit v0.1.5”."""
	versiune = ""
	try:
		from Components.About import about
		versiune = (about.getImageVersionString() or "").split(" ")[0]
	except Exception:
		versiune = ""
	return "HDSatelit v%s" % (versiune or "1")


_ULTIMA = {}
_LACAT = threading.Lock()


def _asteapta(gazda):
	with _LACAT:
		acum = time.time()
		urmatoarea = _ULTIMA.get(gazda, 0) + PAUZA_S
		if urmatoarea > acum:
			time.sleep(urmatoarea - acum)
		_ULTIMA[gazda] = time.time()


# antetele care poarta chei sau jetoane: nu trec la alta gazda sau pe alta schema la o redirectionare
ANTETE_SECRETE = frozenset(("api-key", "x-subs-api-key", "authorization", "cookie"))


def _gazdaSiSchema(adresa):
	p = urlsplit(adresa)
	return (p.scheme or "").lower(), (p.hostname or "").lower(), p.port


if HTTPRedirectHandler is not None:
	class _Redirectionare(HTTPRedirectHandler):
		"""Redirectionarile surselor: numai spre http(s), niciodata de pe https pe http; spre alta gazda (sau alt port,
		alta schema) cererea noua pleaca fara antetele din ANTETE_SECRETE. urllib le copiaza pe toate (in afara de
		content-*), deci o descarcare trimisa spre un CDN ar fi dus acolo cheia omului si jetonul contului."""

		def redirect_request(self, req, fp, code, msg, headers, newurl):
			vechi = _gazdaSiSchema(req.full_url)
			nou = _gazdaSiSchema(newurl)
			if nou[0] not in ("http", "https") or (vechi[0] == "https" and nou[0] != "https"):
				return None
			cerere_noua = HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)
			if cerere_noua is not None and nou != vechi:
				for nume in list(cerere_noua.headers):
					if nume.lower() in ANTETE_SECRETE:
						del cerere_noua.headers[nume]
				for nume in list(cerere_noua.unredirected_hdrs):
					if nume.lower() in ANTETE_SECRETE:
						del cerere_noua.unredirected_hdrs[nume]
			return cerere_noua
else:
	_Redirectionare = None


def _deschizator():
	context = ssl.create_default_context()
	return build_opener(HTTPSHandler(context=context), _Redirectionare())


def cerere(metoda, adresa, antete=None, parametri=None, corp_json=None, maxim=MAX_OCTETI, timp=TIMP_S):
	"""-> (cod, antete (dict cu nume mici), octeti). Parametrii se pun in adresa in ordine alfabetica (cum cere
	OpenSubtitles). Un raspuns de eroare HTTP (4xx, 5xx) nu ridica: se intoarce cu codul lui."""
	if parametri:
		adresa += ("&" if "?" in adresa else "?") + urlencode(sorted((k, v) for k, v in parametri.items() if v not in (None, "")))
	antete = dict(antete or {})
	antete.setdefault("User-Agent", agent())
	date = None
	if corp_json is not None:
		date = json.dumps(corp_json).encode("utf-8")
		antete["Content-Type"] = "application/json"
	_asteapta(urlsplit(adresa).netloc)
	r = Request(adresa, data=date, headers=antete, method=metoda)
	try:
		raspuns = _deschizator().open(r, timeout=timp)
		cod = raspuns.getcode()
	except HTTPError as e:
		raspuns = e
		cod = e.code
	except (URLError, ssl.SSLError, OSError) as e:
		motiv = getattr(e, "reason", e)
		ceas = _mesajCeas(e)
		if ceas:
			eroare = EroareRetea(ceas)
			eroare.ceas = True
			raise eroare
		raise EroareRetea(_t("Receptorul nu a putut ajunge la %s (%s).") % (urlsplit(adresa).netloc, motiv))
	try:
		corp = raspuns.read(maxim + 1)
	except (OSError, ValueError) as e:
		raise EroareRetea(_t("Răspunsul de la %s s-a întrerupt (%s).") % (urlsplit(adresa).netloc, e))
	finally:
		try:
			raspuns.close()
		except Exception:
			pass
	if len(corp) > maxim:
		raise EroareRetea(_t("Răspunsul de la %s e prea mare.") % urlsplit(adresa).netloc)
	antete_r = dict((k.lower(), v) for k, v in (raspuns.headers.items() if getattr(raspuns, "headers", None) else []))
	return cod, antete_r, corp


def json_din(corp):
	"""Octetii unui raspuns -> obiectul JSON, sau None."""
	try:
		return json.loads(corp.decode("utf-8"))
	except (ValueError, UnicodeDecodeError, AttributeError):
		return None
