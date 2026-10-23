# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPlural.py: pluralele traduse (ngettext) ale imaginii, cu formatarea care merge si cand forma aleasa nu are numarul.
#
# In romana singularul se scrie cu litere, nu cu cifra: "O intrare nouă pentru tine", "un canal", "o oră" (msgstr[0]
# din po/ro.po, fara %d), iar pluralul fara "de": "2 intrări", "20 intrări", "101 canale". Codul scrie peste tot
# ngettext(unu, multe, n) % n (sau % (n, alt_text)); cu o forma fara %d, "un canal" % 1 ar cadea ("not all arguments
# converted"). De aceea ngettext de aici intoarce o Forma: un text (str) al carui % scoate numarul din argumente cand
# forma aleasa nu il are (numarul e argumentul primului %d din msgid_plural), restul argumentelor ramanand pe locul lor.
#
# Traducerea: enigma2 instaleaza numai _ (Components/Language.py), care e metoda obiectului de traducere, deci
# ngettext-ul lui se ia de acolo (formele din Plural-Forms ale limbii). Netradus (sau pe PC): n == 1 -> msgid, altfel
# msgid_plural, adica regula romaneasca fara "de" (msgid-urile sunt in romana).
#
# Fisierul nu importa nimic din enigma2: il folosesc toate invelisurile ngettext ale modulelor (HdsImportSurse,
# HdsIndexCanale, HdsListeCabluTerestru, HdsModSigur, UsageConfig, Hds/DabT2/limba) si probele de pe PC.

import re

# un specificator de format % (numit sau nu); "%%" se numara separat
SPECIFICATOR = re.compile(r"%(?:\([^)]*\))?[#0\- +]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?[diouxXeEfFgGcrsa%]")


def specificatori(text):
	"""Specificatorii de format ai textului, fara "%%", in ordine (de pilda ["%s", "%d"])."""
	return [s for s in SPECIFICATOR.findall(text or "") if s != "%%"]


def formateaza(text, model, argumente):
	"""text % argumente; cand text are un specificator mai putin decat modelul (msgid_plural) si ii lipseste %d,
	numarul (argumentul primului %d al modelului) se scoate din argumente."""
	if not isinstance(argumente, tuple):
		argumente = (argumente,)
	st, sm = specificatori(text), specificatori(model)
	if len(st) == len(sm) - 1 and "%d" in sm and "%d" not in st:
		k = sm.index("%d")
		argumente = argumente[:k] + argumente[k + 1:]
	return text % argumente


class Forma(str):
	"""Forma de plural aleasa (un text obisnuit), cu % care merge si fara numar in forma pentru 1."""

	def __new__(cls, text, model):
		o = str.__new__(cls, text)
		o.model = model
		return o

	def __mod__(self, argumente):
		return formateaza(str(self), self.model, argumente)


def _traducere():
	try:
		import builtins
		return getattr(builtins.__dict__.get("_"), "__self__", None)
	except Exception:
		return None


def ngettext(unu, multe, n):
	"""Pluralul tradus ca Forma (vezi sus). Netradus: unu pentru n == 1, altfel multe (fara "de")."""
	rez = None
	try:
		f = getattr(_traducere(), "ngettext", None)
		if f is not None:
			rez = f(unu, multe, n)
	except Exception:
		rez = None
	if not isinstance(rez, str) or not rez:
		rez = unu if n == 1 else multe
	return Forma(rez, multe)


def forma(text, multe):
	"""Un text de plural luat din alta parte (de pilda din catalogul limbii), ca Forma."""
	return Forma(text, multe) if text is not None else None
