# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsStareMeniu - starea intrarilor de meniu si a randurilor de setari („in-lucru”, „netestat”) si semnele lor.
#
# REGULA: starea NU se mai arata omului. Imaginea e toata beta, deci un semn „(netestat)” sau „(în lucru)” langa o
# intrare nu spune nimic in plus si incarca meniul. Nicio functie noua nu primeste semn: STARI_ARATATE ramane gol, iar
# cuSemn() si aratata() de mai jos sunt singurul loc in care s-ar hotari afisarea (meniul, setarile, dalele, lista
# functiilor, interfata web trec toate pe aici). Starea ramane in menu.xml / setup.xml si in cod, pentru probe si
# pentru lista functiilor de pe site (campul probat).
#
# STAREA STA INTR-UN SINGUR LOC, langa intrare: atributul stare= din data/menu.xml (si din data/setup.xml, pentru un
# rand de setari), cu valorile:
#   „in-lucru”  intrarea nu face inca ce promite (de exemplu setari pe care nu le citeste nimeni);
#   „netestat”  intrarea e terminata, dar nu a fost probata inca pe receptor.
# Numele intrarii nu se schimba (traducerile ei raman), semnul se adauga la afisare: Screens/Menu.py pe televizor,
# Screens/Setup.py pentru randurile de setari, HdsWebControl (scanare_web.py si subsolul paginii principale din
# plugin.py) in interfata web. Semnul se scoate din menu.xml dupa proba intrarii pe receptor.
# Inainte de 1.0.0 nu are voie sa ramana niciun semn (proba teste/test_semne_meniu.py cade altfel).
#
# Fisierul nu importa nimic din enigma2: se foloseste si din probele de pe PC.

STARI = ("in-lucru", "netestat")
# starile al caror semn se vede pe receptor si in web: niciuna (vezi REGULA de sus)
STARI_ARATATE = ()


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: formele de mai jos se traduc la folosire."""
	return text


# textul cu semn; „%s” e numele intrarii, deja tradus
_FORME = {
	"in-lucru": N_("%s (în lucru)"),
	"netestat": N_("%s (netestat)"),
}


def _(text):
	"""Traducerea imaginii (builtins._ pus de Components/Language.py); pe PC, textul asa cum e."""
	try:
		import builtins
		f = builtins.__dict__.get("_")
	except Exception:
		f = None
	if f is None or f is _:
		return text
	return f(text)


def stare(nod):
	"""Starea unui nod din menu.xml / setup.xml („in-lucru”, „netestat”) sau None. O valoare necunoscuta nu pune
	niciun semn (o greseala de scriere nu strica meniul)."""
	try:
		valoare = (nod.get("stare") or "").strip()
	except AttributeError:
		return None
	return valoare if valoare in STARI else None


def aratata(starea):
	"""Starea, daca semnul ei se arata (STARI_ARATATE), altfel None."""
	return starea if starea in STARI_ARATATE else None


def cuSemn(text, starea, traducere=None):
	"""Textul deja tradus al intrarii, cu semnul starii dupa el numai daca starea se arata (STARI_ARATATE); altfel
	textul neschimbat."""
	if starea not in _FORME or aratata(starea) is None:
		return text
	tr = traducere or _
	try:
		return tr(_FORME[starea]) % (text,)
	except (TypeError, ValueError):
		# o traducere stricata (fara %s) nu are voie sa ascunda intrarea
		return _FORME[starea] % (text,)


def textNod(nod, traducere=None, text=None):
	"""Numele tradus al unui nod din menu.xml / setup.xml, cu semnul lui. `text` = numele deja tradus, cand
	apelantul il are (de exemplu titlul unui <setup>)."""
	tr = traducere or _
	if text is None:
		text = tr(nod.get("text") or "??")
	return cuSemn(text, stare(nod), tr)


# ------------------------------------------------------------------ interfata web
# Paginile web scrise in romana (subsolul panoului si al lui /ecrane) primesc acelasi semn ca intrarea de pe
# televizor care are pagina aceea (atributul web= din menu.xml); pagina /accel primeste semnul randului din setup.xml.
# Fisierele se citesc o data si se recitesc numai cand se schimba (menu.xml ~30 KB, setup.xml ~20 KB).

import os as _os
import re as _re
import xml.etree.ElementTree as _ET

_CACHE = {}


def _radacina(cale):
	try:
		semn = _os.path.getmtime(cale)
	except OSError:
		return None
	vechi = _CACHE.get(cale)
	if vechi is not None and vechi[0] == semn:
		return vechi[1]
	try:
		radacina = _ET.parse(cale).getroot()
	except Exception as eroare:
		print("[HdsStareMeniu] nu pot citi %s: %s" % (cale, eroare))
		radacina = None
	_CACHE[cale] = (semn, radacina)
	return radacina


def stariWeb(cale_meniu):
	"""{pagina web: stare} pentru intrarile din menu.xml care au si web=, si stare=."""
	radacina = _radacina(cale_meniu)
	rez = {}
	if radacina is None:
		return rez
	for nod in radacina.iter():
		if nod.tag in ("item", "menu"):
			web = (nod.get("web") or "").strip()
			s = stare(nod)
			if web and s:
				rez[web] = s
	return rez


def stareSetare(cale_setup, setare):
	"""Starea randului din setup.xml care arata setarea `setare` (de exemplu „config.usage.hds_accel_2d”)."""
	radacina = _radacina(cale_setup)
	if radacina is None:
		return None
	for nod in radacina.iter("item"):
		if (nod.text or "").strip() == setare:
			return stare(nod)
	return None


def semneInLegaturi(pagina, stari, traducere=None):
	"""Legaturile <a href="/cale">Nume</a> ale unei pagini web primesc semnul intrarii cu aceeasi pagina. Paginile
	sunt scrise in romana, deci implicit semnul ramane in romana (traducere = textul asa cum e)."""
	if not stari:
		return pagina
	tr = traducere or (lambda text: text)
	for web, s in stari.items():
		model = _re.compile(r'(<a href="%s">)([^<]+)(</a>)' % _re.escape(web))
		pagina = model.sub(lambda m: m.group(1) + cuSemn(m.group(2), s, tr) + m.group(3), pagina)
	return pagina
