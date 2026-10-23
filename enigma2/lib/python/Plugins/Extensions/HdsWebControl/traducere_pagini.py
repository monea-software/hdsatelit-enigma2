# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# traducere_pagini.py: paginile interfetei web in limba receptorului (HdsWebControl).
#
# Sabloanele paginilor (constantele PAGINA ale modulelor, HTML cu <script>) sunt scrise in romana. Fiecare modul da textele lor in
# TEXTE_PAGINA = {"html": (N_("..."), ...), "js": (N_("..."), ...)}, marcate pentru xgettext (po/Makefile.am), iar
# traduce(sablon, texte) inlocuieste fiecare text gasit INTREG cu traducerea lui (functia _ a enigma2, limba aleasa
# pe receptor):
#   - html: textul dintre doua etichete (cu etichetele de formatare din el: b, i, a, code, br, span...) si valorile
#     atributelor title, placeholder, aria-label si alt; spatiile dintre cuvinte se potrivesc oricum, deci un text
#     scris pe mai multe randuri in sablon e un singur msgid, cu spatii simple;
#   - js: sirurile dintre ghilimele ("..." sau '...') din <script>, intregi (spatiile de la capete raman pe loc);
#   - <html lang="ro"> primeste limba receptorului.
# O bucata dintr-un text mai lung nu se atinge, iar un text netradus ramane cum e: in romana pagina iese neschimbata,
# octet cu octet. Rezultatul se tine minte pe (limba, sablon), deci o pagina se traduce o singura data pe limba.
# Sablonul se traduce INAINTE de inlocuirile __CONFIG__, __STIL_COMUN__ si celelalte (textele cu __CHEI__ raman
# intregi).
#
# Fisierul nu importa nimic din enigma2 la incarcare (probele de pe PC dau limba si traducerea lor).

import html
import re

_SCRIPT = re.compile(r"(<script\b[^>]*>)(.*?)(</script>)", re.S | re.I)
_STIL = re.compile(r"(<style\b[^>]*>.*?</style>)", re.S | re.I)
_ATRIBUTE = "title|placeholder|aria-label|alt"
_LANG = '<html lang="ro">'
MAX_CACHE = 300
_CACHE = {}


def _gettext(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def limba():
	"""Codul limbii receptorului (de exemplu "de" din "de_DE"); "ro" fara limba citibila (probele de pe PC)."""
	try:
		from Components.Language import language
		cod = (language.getLanguage() or "").split("_")[0].lower()
	except Exception:
		cod = ""
	if 2 <= len(cod) <= 3 and cod.isalpha():
		return cod
	return "ro"


def _model(text):
	"""Expresia unui msgid: cuvintele lui, cu orice spatii intre ele."""
	return r"\s+".join(re.escape(p) for p in text.split())


def _sir_js(text):
	"""Traducerea pusa intr-un sir JS intre "..." sau '...' (si in <script>: fara "</")."""
	return (text.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'").replace("\n", "\\n")
		.replace("\r", "").replace("</", "<\\/"))


def _text_html(msgid, tradus):
	# un msgid cu etichete sau entitati are traducerea scrisa la fel (verificat la punerea in po); altfel se scapa
	if "<" in msgid or "&" in msgid:
		return tradus
	return html.escape(tradus, quote=False)


def _atribut(msgid, tradus):
	if "&" in msgid:
		return tradus.replace('"', "&quot;")
	return html.escape(tradus, quote=True)


def _harta(texte, traducere):
	"""{msgid: traducere} numai pentru textele care se schimba."""
	rez = {}
	for m in texte or ():
		t = traducere(m)
		if t and t != m:
			rez[m] = t
	return rez


def _alternative(harta, model):
	return "|".join(model(m) for m in sorted(harta, key=len, reverse=True))


def _html(text, harta):
	if not harta:
		return text
	alt = _alternative(harta, _model)
	unitate = re.compile(r"(?<=>)(\s*)(%s)(\s*)(?=<)" % alt)
	atribut = re.compile(r'(\b(?:%s)=")(%s)(")' % (_ATRIBUTE, alt))

	def u(m):
		cheie = " ".join(m.group(2).split())
		return m.group(1) + _text_html(cheie, harta[cheie]) + m.group(3)

	def a(m):
		cheie = " ".join(m.group(2).split())
		return m.group(1) + _atribut(cheie, harta[cheie]) + m.group(3)

	bucati = _STIL.split(text)
	for i in range(0, len(bucati), 2):          # bucatile impare sunt <style>...</style>, raman cum sunt
		bucati[i] = atribut.sub(a, unitate.sub(u, bucati[i]))
	return "".join(bucati)


def _js(text, harta):
	if not harta:
		return text
	sir = re.compile(r"""(["'])(\s*)(%s)(\s*)\1""" % _alternative(harta, re.escape))

	def s(m):
		return m.group(1) + m.group(2) + _sir_js(harta[m.group(3)]) + m.group(4) + m.group(1)
	return sir.sub(s, text)


def tradu(sablon, texte, fel="pagina", traducere=None, cod="ro"):
	"""Sablonul tradus (fara tinere minte). `fel`: "pagina" (HTML cu <script>) sau "js" (numai cod JS)."""
	traducere = traducere or _gettext
	texte = texte or {}
	harta_js = _harta(texte.get("js"), traducere)
	if fel == "js":
		return _js(sablon, harta_js)
	harta_html = _harta(texte.get("html"), traducere)
	rez = []
	poz = 0
	for m in _SCRIPT.finditer(sablon):
		rez.append(_html(sablon[poz:m.start()], harta_html))
		rez.append(m.group(1) + _js(m.group(2), harta_js) + m.group(3))
		poz = m.end()
	rez.append(_html(sablon[poz:], harta_html))
	text = "".join(rez)
	# lang se schimba numai cand pagina chiar are texte traduse (fara catalog ramane romaneasca)
	if cod != "ro" and (harta_html or harta_js) and _LANG in text:
		text = text.replace(_LANG, '<html lang="%s">' % cod, 1)
	return text


def traduce(sablon, texte, fel="pagina"):
	"""Sablonul in limba receptorului, tinut minte pe (limba, sablon)."""
	cod = limba()
	cheie = (cod, fel, sablon)
	rez = _CACHE.get(cheie)
	if rez is None:
		try:
			rez = tradu(sablon, texte, fel, _gettext, cod)
		except Exception as e:
			# o pagina netradusa e mai buna decat una lipsa
			print("[HdsWebControl] traducerea paginii: %r" % (e,))
			rez = sablon
		if len(_CACHE) >= MAX_CACHE:
			_CACHE.clear()
		_CACHE[cheie] = rez
	return rez
