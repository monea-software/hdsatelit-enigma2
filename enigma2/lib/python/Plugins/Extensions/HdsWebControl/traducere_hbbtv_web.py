# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# traducere_hbbtv_web.py: calea locala prin care scriptul din paginile HbbTV (HdsNavigator/hds-hbbtv.js) cere
# traducerea textelor vazute ("Tradu HbbTV", Components/HdsTraducereTexte.py, instanta "hbbtv").
#
#   POST /api/traducere-hbbtv   corpul (text simplu, JSON): {"k": cheia pornirii, "t": [texte]}
#                               raspunsul: {"result": true, "t": [traducerea | 0 | null]}: traducerea textului, 0 =
#                               ramane originalul (deja in limba ta, intors neschimbat), null = inca se traduce (se
#                               cere din nou mai tarziu); {"result": false, "oprit": true} cand setarea e oprita sau
#                               niciun serviciu nu e gata (scriptul se opreste, pagina ramane in original)
#
# POARTA (a ei, nu cea a panoului): navigatorul HbbTV ruleaza pe receptor, deci clientul e numai 127.0.0.1; o aplicatie
# HbbTV ruleaza acum si cheia trimisa e cheia pornirii ei (HdsHbbtvPornire.cheieTraducere: noua la fiecare pornire,
# data paginii numai pe stdin, in config); setarea "Tradu HbbTV" pornita. Cel mult MAX_TEXTE texte de cel mult
# MAX_TEXT semne, un corp de cel mult MAX_CORP octeti, cel mult CERERI_PE_SECUNDA cereri pe secunda. Raspunsul are
# Access-Control-Allow-Origin: * (pagina e pe domeniul aplicatiei; fara cookie-uri), cererea e "simpla" (POST cu
# text simplu, fara antete), deci fara cerere de verificare; OPTIONS raspunde oricum.
#
# FIRUL: render_POST ruleaza pe firul enigma2 (reactorul); traduceri() numai cauta in memorie si pune textele lipsa in
# coada traducatorului (cererea HTTP spre serviciu pleaca pe firul lui). Fisierul nu importa nimic din enigma2 la
# incarcare: probele de pe PC dau modulele lor.

import json
import time

MAX_CORP = 48 * 1024
MAX_TEXTE = 60
MAX_TEXT = 1500
CERERI_PE_SECUNDA = 8

_DEBIT = {"inceput": 0.0, "n": 0}


def _module(X=None, H=None):
	if X is None:
		from Components import HdsTraducereTexte as X
	if H is None:
		from Components import HdsHbbtvPornire as H
	return X, H


def _local(adresa):
	return adresa in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


def debitBun(acum=None):
	"""cel mult CERERI_PE_SECUNDA cereri intr-o secunda"""
	acum = time.monotonic() if acum is None else acum
	if acum - _DEBIT["inceput"] >= 1.0:
		_DEBIT["inceput"] = acum
		_DEBIT["n"] = 0
	_DEBIT["n"] += 1
	return _DEBIT["n"] <= CERERI_PE_SECUNDA


def raspunde(adresa, corp, X=None, H=None, acum=None):
	"""(cod HTTP, dict) pentru o cerere: adresa clientului, corpul (octeti)"""
	if not _local(adresa):
		return 403, {"result": False, "message": "numai navigatorul receptorului"}
	if corp is None or len(corp) > MAX_CORP:
		return 413, {"result": False, "message": "corp prea mare"}
	if not debitBun(acum):
		return 429, {"result": False, "message": "prea multe cereri"}
	try:
		d = json.loads(corp.decode("utf-8"))
	except (ValueError, UnicodeDecodeError):
		return 400, {"result": False, "message": "corp gresit"}
	if not isinstance(d, dict):
		return 400, {"result": False, "message": "corp gresit"}
	texte = d.get("t")
	cheie = d.get("k")
	if not isinstance(texte, list) or len(texte) > MAX_TEXTE or not all(isinstance(t, str) and len(t) <= MAX_TEXT
			for t in texte):
		return 400, {"result": False, "message": "texte gresite"}
	try:
		X, H = _module(X, H)
	except Exception:
		return 503, {"result": False, "oprit": True}
	buna = H.cheieTraducere()
	if not buna or not isinstance(cheie, str) or cheie != buna:
		return 403, {"result": False, "message": "cheie gresita"}
	if not X.poartaDeschisa("hbbtv"):
		return 200, {"result": False, "oprit": True}
	lista, stare = X.traduceri("hbbtv", texte)
	if stare == X.STARE_OPRIT:
		return 200, {"result": False, "oprit": True}
	rez = []
	for t, v in zip(texte, lista):
		if v is None:
			rez.append(None)
		elif v == t or not v:
			rez.append(0)
		else:
			rez.append(v)
	return 200, {"result": True, "t": rez}


def _adresaClient(request):
	try:
		a = request.getClientAddress()
		if a is not None and hasattr(a, "host"):
			return a.host
	except Exception:
		pass
	try:
		return request.getClientIP()
	except Exception:
		return None


def rute(resource):
	"""{nume: resursa de sub /api}; `resource` e twisted.web.resource"""

	class TraducereHbbtvResource(resource.Resource):
		isLeaf = True

		def _antete(self, request, cod):
			request.setResponseCode(cod)
			request.setHeader(b"content-type", b"application/json; charset=utf-8")
			request.setHeader(b"cache-control", b"no-store")
			request.setHeader(b"access-control-allow-origin", b"*")

		def render_OPTIONS(self, request):
			self._antete(request, 204)
			request.setHeader(b"access-control-allow-methods", b"POST")
			request.setHeader(b"access-control-allow-headers", b"content-type")
			request.setHeader(b"access-control-max-age", b"600")
			return b""

		def render_POST(self, request):
			try:
				corp = request.content.read(MAX_CORP + 1) if request.content is not None else b""
			except Exception:
				corp = None
			try:
				cod, d = raspunde(_adresaClient(request), corp)
			except Exception as e:
				print("[HdsWebControl] traducere HbbTV: %s" % e.__class__.__name__)
				cod, d = 500, {"result": False}
			self._antete(request, cod)
			return json.dumps(d, ensure_ascii=False).encode("utf-8", "replace")

		def render_GET(self, request):
			self._antete(request, 405)
			request.setHeader(b"allow", b"POST, OPTIONS")
			return b'{"result": false}'

	return {b"traducere-hbbtv": TraducereHbbtvResource()}
