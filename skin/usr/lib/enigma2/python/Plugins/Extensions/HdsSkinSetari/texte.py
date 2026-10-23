# -*- coding: utf-8 -*-
# Copyright (C) 2026 Monea Software pentru HD Satelit (https://hdsatelit.com, contact@moneasoftware.com)
# Licenta: GNU GPL versiunea 2. HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
# Textele panoului de setari al skinului HDSatelit, din mecanismul comun de limbi al skinului:
# Components/Converter/HdsLang.py (engleza) si HdsLang_<cod>.py (limba aleasa), generate din limbi-staging/*.json.
# Cheile panoului: set_*, pv_*, fam_*, role_*. Aici nu se tine niciun text; cheie noua = JSON + genereaza_module.py.
# "{0}" se inlocuieste in cod.
import sys

_CONV = "Components.Converter.HdsCommon"
# raw = config.osd.language citit ultima data; t = tabelul limbii; en = engleza
_st = {"raw": object(), "t": {}, "en": {}, "din_conv": False}


def _limba_raw():
	try:
		mod = sys.modules.get("Components.config")
		if mod is None:
			from Components.config import config
		else:
			config = mod.config
		return config.osd.language.value
	except Exception:
		return None


def _tabele():
	"""(tabelul limbii, engleza). Daca skinul e activ, convertorul are deja limba in memorie si se foloseste aceea;
	altfel se incarca o singura data, la schimbarea limbii."""
	raw = _limba_raw()
	C = sys.modules.get(_CONV)
	# daca s-a incarcat convertorul dupa noi, tabelul lui il inlocuieste pe al nostru (fara doua copii in memorie)
	if raw == _st["raw"] and (_st["din_conv"] or C is None):
		return _st["t"], _st["en"]
	t, en = {}, {}
	din_conv = False
	try:
		if C is not None:
			C.refresh_lang()
			t, en = C._lang["t"], C._EN
			din_conv = True
		else:
			from Components.Converter import HdsLang as L
			en = L.EN
			t = L.incarca(L.cod_limba(raw))
	except Exception as e:
		print("[HdsSkinSetari] limba: %s" % e)
	_st["raw"], _st["t"], _st["en"] = raw, t if isinstance(t, dict) else {}, en if isinstance(en, dict) else {}
	_st["din_conv"] = din_conv
	return _st["t"], _st["en"]


def tr(cheie, *args):
	"""Textul cheii in limba interfetei, engleza daca lipseste. Nu cade niciodata: cheie necunoscuta -> cheia insasi."""
	try:
		t, en = _tabele()
		s = t.get(cheie) or en.get(cheie) or cheie
	except Exception:
		s = cheie
	if not isinstance(s, type(u"")):
		try:
			s = s.decode("utf-8")
		except Exception:
			s = u"%s" % (s,)
	try:
		for i, a in enumerate(args):
			s = s.replace(u"{%d}" % i, a if isinstance(a, type(u"")) else u"%s" % (a,))
	except Exception:
		pass
	return s


def tr_str(cheie, *args):
	"""Ca tr(), dar intoarce str (bytes utf-8 pe Python 2, unde Label si MenuList vor str)."""
	s = tr(cheie, *args)
	if str is bytes:
		return s.encode("utf-8")
	return s
