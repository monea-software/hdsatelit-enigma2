# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# limbi.py: codurile limbilor intre imagine (codul canonic ISO 639-2/T din Components/HdsPisteLimbi.py: ron, eng, deu)
# si surse (ISO 639-1: ro, en, de), plus limbile cautate implicit: preferintele de subtitrare ale receptorului
# („Limba sunetului și a subtitrărilor”), apoi engleza.

DOUA = {
	"ron": "ro", "eng": "en", "deu": "de", "fra": "fr", "ita": "it", "spa": "es", "por": "pt", "hun": "hu",
	"ces": "cs", "pol": "pl", "rus": "ru", "tur": "tr", "nld": "nl", "bul": "bg", "ell": "el", "srp": "sr",
	"hrv": "hr", "slv": "sl", "slk": "sk", "ukr": "uk", "swe": "sv", "nor": "no", "dan": "da", "fin": "fi",
	"ara": "ar", "heb": "he", "est": "et", "lit": "lt", "lav": "lv", "cat": "ca", "isl": "is", "mkd": "mk",
	"sqi": "sq", "bos": "bs", "hin": "hi", "jpn": "ja", "kor": "ko", "zho": "zh", "vie": "vi", "tha": "th",
	"ind": "id", "msa": "ms", "fas": "fa",
}
TREI = dict((v, k) for k, v in DOUA.items())
MAX_LIMBI = 3


def _L():
	try:
		from Components import HdsPisteLimbi
		return HdsPisteLimbi
	except Exception:
		return None


def canonic(text):
	"""Un cod sau nume de limba de la o sursa („ro”, „RO”, „rum”, „Romanian”, „pt-br”) -> ron, eng, ...; sau None."""
	if not text:
		return None
	t = str(text).strip().lower()
	if t in TREI:
		return TREI[t]
	if t in DOUA:
		return t
	baza = t.split("-")[0].split("_")[0]
	if baza in TREI:
		return TREI[baza]
	L = _L()
	return L.limbaCanonica(text) if L is not None else None


def nume(cod):
	"""Numele limbii pentru om (tradus), din codul canonic."""
	L = _L()
	if L is not None and cod:
		try:
			return L.numeLimba(cod)
		except Exception:
			pass
	return cod or ""


def implicite():
	"""Limbile cautate implicit, coduri canonice: preferintele de subtitrare ale receptorului, apoi engleza."""
	rez = []
	L = _L()
	if L is not None:
		try:
			for pref in L.preferinteSubtitrare():
				if pref == L.PREF_RECEPTOR:
					c = L.limbaCanonica(L.limbaReceptor())
				elif pref in (L.PREF_NIMIC, L.PREF_CANAL, None, ""):
					c = None
				else:
					c = L.limbaCanonica(pref)
				if c and c not in rez:
					rez.append(c)
		except Exception:
			rez = []
	if "eng" not in rez:
		rez.append("eng")
	return rez[:MAX_LIMBI]
