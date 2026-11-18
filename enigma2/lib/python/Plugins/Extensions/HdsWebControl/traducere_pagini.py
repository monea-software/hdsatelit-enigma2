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


# Potrivirea fara expresia uriasa (TJB, 15.11.2026). Inainte, fiecare pagina compila o alternare cu TOATE textele traduse
# ale modulului (sute de msgid-uri; pe PC 0,3 s pentru panou, 96% compilarea expresiei), pe firul interfetei, la prima
# deschidere a fiecarei pagini in fiecare limba in afara de romana: pe un receptor mips (Solo SE) 6,5 s si 60 s in
# re._parse <- render_GET. Acum textul dintre etichete, valoarea atributului si sirul JS se cauta in harta (dictionar);
# textele cu etichete in ele se potrivesc cuvant cu cuvant, dupa inceputul primului cuvant. Rezultatul e acelasi, octet cu octet
# (proba test_tjb_traducere_pagini_075 compara cu potrivirea veche pe toate paginile, in mai multe limbi).
_ATRIBUT_ORICE = re.compile(r'(\b(?:%s)=")([^"]*)(")' % _ATRIBUTE)
_GHILIMELE = re.compile(r"[\"']")


def _cu_etichete(harta):
	"""Textele cu etichete in ele (singurele care trec peste un "<"), dupa inceputul primului cuvant (cel mult 8 semne):
	{inceput: [(ordinea, cuvintele, msgid)]}; ordinea = locul in alternarea veche (cele lungi intai). None fara ele."""
	rez = {}
	for ordinea, m in enumerate(sorted(harta, key=len, reverse=True)):
		if "<" not in m:
			continue
		cuvinte = m.split()
		if cuvinte:
			rez.setdefault(cuvinte[0][:8], []).append((ordinea, cuvinte, m))
	return rez or None


def _potriveste_cuvinte(text, p, cuvinte):
	"""Capatul potrivirii vechi de la p (spatii, cuvintele legate prin spatii, spatii, apoi "<"), sau -1."""
	n = len(text)
	i = p
	while i < n and text[i].isspace():
		i += 1
	ultim = len(cuvinte) - 1
	for k, c in enumerate(cuvinte):
		if not text.startswith(c, i):
			return -1
		i += len(c)
		if k < ultim:
			j = i
			while j < n and text[j].isspace():
				j += 1
			if j == i:
				return -1
			i = j
	while i < n and text[i].isspace():
		i += 1
	return i if i < n and text[i] == "<" else -1


def _cu_etichete_la(text, p, etichete):
	"""(capatul, msgid) pentru primul text cu etichete (in ordinea alternarii vechi) care se potriveste de la p."""
	i = p
	n = len(text)
	while i < n and text[i].isspace():
		i += 1
	candidati = []
	for k in range(1, 9):
		candidati.extend(etichete.get(text[i:i + k], ()))
	for _ordinea, cuvinte, m in sorted(candidati, key=lambda x: x[0]):
		e = _potriveste_cuvinte(text, p, cuvinte)
		if e >= 0:
			return e, m
	return None


def _unitati(text, harta, etichete):
	"""Textele intregi dintre ">" si "<" (spatiile dinauntru oricare) inlocuite cu traducerea, ca alternarea veche:
	dupa fiecare ">" intai textele cu etichete, apoi textul pana la primul "<"; dupa o potrivire cautarea merge de la
	capatul ei, altfel de la urmatorul ">" (si unul din mijlocul textului)."""
	rez = []
	copiat = 0
	i = text.find(">")
	while i >= 0:
		p = i + 1
		if etichete is not None:
			gasit = _cu_etichete_la(text, p, etichete)
			if gasit:
				e, _m = gasit
				bucata = text[p:e]
				cheie = " ".join(bucata.split())
				fara_inceput = bucata.lstrip()
				inainte = bucata[:len(bucata) - len(fara_inceput)]
				dupa = fara_inceput[len(fara_inceput.rstrip()):]
				rez.append(text[copiat:p])
				rez.append(inainte + _text_html(cheie, harta[cheie]) + dupa)
				copiat = e
				i = text.find(">", e)
				continue
		e = text.find("<", p)
		if e < 0:
			break
		bucata = text[p:e]
		cheie = " ".join(bucata.split())
		if cheie and cheie in harta:
			fara_inceput = bucata.lstrip()
			inainte = bucata[:len(bucata) - len(fara_inceput)]
			dupa = fara_inceput[len(fara_inceput.rstrip()):]
			rez.append(text[copiat:p])
			rez.append(inainte + _text_html(cheie, harta[cheie]) + dupa)
			copiat = e
			i = text.find(">", e)
			continue
		i = text.find(">", p)
	rez.append(text[copiat:])
	return "".join(rez)


def _html(text, harta):
	if not harta:
		return text
	etichete = _cu_etichete(harta)

	def a(m):
		valoare = m.group(2)
		# ca alternarea veche: valoarea intreaga, fara spatii la capete (cuvintele msgid-ului legate prin \s+)
		if not valoare or valoare[0].isspace() or valoare[-1].isspace():
			return m.group(0)
		cheie = " ".join(valoare.split())
		if cheie not in harta:
			return m.group(0)
		return m.group(1) + _atribut(cheie, harta[cheie]) + m.group(3)

	bucati = _STIL.split(text)
	for i in range(0, len(bucati), 2):          # bucatile impare sunt <style>...</style>, raman cum sunt
		bucati[i] = _ATRIBUT_ORICE.sub(a, _unitati(bucati[i], harta, etichete))
	return "".join(bucati)


def _js(text, harta):
	"""Sirurile "..." si '...' care sunt un msgid intreg (cu spatii oricate la capete), ca alternarea veche: de la fiecare
	ghilimea, pana la urmatoarea de acelasi fel; dupa o potrivire cautarea merge de dupa ea, altfel de la semnul urmator."""
	if not harta:
		return text
	dupa_miez = {}
	for ordinea, m in enumerate(sorted(harta, key=len, reverse=True)):
		dupa_miez.setdefault(m.strip(), []).append((ordinea, m))
	rez = []
	copiat = 0
	g = _GHILIMELE.search(text)
	while g:
		i = g.start()
		q = text[i]
		e = text.find(q, i + 1)
		gasit = None
		if e >= 0:
			continut = text[i + 1:e]
			miez = continut.strip()
			inceput = continut[:len(continut) - len(continut.lstrip())]
			sfarsit = continut[len(continut.rstrip()):]
			# ca alternarea veche: (\s*) de la inceput cat mai lung, apoi msgid-urile in ordinea lor (cele lungi intai)
			bune = []
			for ordinea, m in (dupa_miez.get(miez, ()) if miez else ()):
				a = m[:len(m) - len(m.lstrip())]
				b = m[len(m.rstrip()):]
				if inceput.endswith(a) and sfarsit.startswith(b):
					bune.append((len(a), ordinea, m, a, b))
			if bune:
				_la, _o, m, a, b = min(bune)
				gasit = q + inceput[:len(inceput) - len(a)] + _sir_js(harta[m]) + sfarsit[len(b):] + q
		if gasit is not None:
			rez.append(text[copiat:i])
			rez.append(gasit)
			copiat = e + 1
			g = _GHILIMELE.search(text, copiat)
		else:
			g = _GHILIMELE.search(text, i + 1)
	rez.append(text[copiat:])
	return "".join(rez)


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
