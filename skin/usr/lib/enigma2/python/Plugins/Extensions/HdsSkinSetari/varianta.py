# -*- coding: utf-8 -*-
# Copyright (C) 2026 Monea Software pentru HD Satelit (https://hdsatelit.com, contact@moneasoftware.com)
# Licenta: GNU GPL versiunea 2. HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
#
# Cele doua variante ale skin.xml din aceeasi sursa:
#   generala: skin.xml din pachet, merge pe toate imaginile (textOffset, secondfont);
#   noua:     pentru imaginile care au atributele noi padding si valueFont:
#             aceleasi valori sub numele noi, deci acelasi aspect si 0 avertismente [Skin] in jurnal.
# Fara importuri din enigma: acelasi cod ruleaza pe PC (tools\fa_variante.py) si pe receptor (postinst).
# Merge pe Python 2.7 si 3.x.
import io
import marshal
import os
import re
import sys

SKIN_XML = "/usr/share/enigma2/HDSatelit/skin.xml"
DOSAR_PYTHON = "/usr/lib/enigma2/python"

# numele vechi -> numele nou, exact lantul din skin.py al imaginilor noi (textOffset -> textPadding -> padding, secondfont -> valueFont)
RENUMIRI = (
	("textOffset", "padding"),
	("textPadding", "padding"),
	("secondfont", "valueFont"),
	("secondFont", "valueFont"),
)
# metodele din AttributeParser care trebuie sa existe ca imaginea sa primeasca varianta noua
CERUTE = ("padding", "valueFont")

_RX_ATRIBUT = re.compile(br'(\s)(textOffset|textPadding|secondfont|secondFont)(\s*=\s*")')
_NOU = dict((a.encode("ascii"), b.encode("ascii")) for a, b in RENUMIRI)


class EroareVarianta(Exception):
	pass


def _bloc_culori(date):
	i = date.find(b"<colors>")
	j = date.find(b"</colors>")
	if i < 0 or j < i or date.count(b"<colors>") != 1:
		return None
	return date[i:j + len(b"</colors>")]


def fa_noua(date):
	"""Varianta noua din octetii variantei generale. Schimba doar numele atributelor; restul octetilor raman."""
	nou = _RX_ATRIBUT.sub(lambda m: m.group(1) + _NOU[m.group(2)] + m.group(3), date)
	if _bloc_culori(nou) != _bloc_culori(date):
		raise EroareVarianta("blocul <colors> s-a schimbat")
	return nou


def e_noua(date):
	"""True daca skin.xml e deja in varianta noua (niciun atribut vechi ramas)."""
	return _RX_ATRIBUT.search(date) is None


def numara_vechi(date):
	rez = {}
	for m in _RX_ATRIBUT.finditer(date):
		k = m.group(2).decode("ascii")
		rez[k] = rez.get(k, 0) + 1
	return rez


# ---------------------------------------------------------------- ce stie imaginea
def _metode_din_cod(cod):
	"""Numele metodelor clasei AttributeParser din codul modulului skin; None daca nu exista clasa."""
	tip_cod = type(cod)
	stiva = [cod]
	while stiva:
		c = stiva.pop()
		for k in c.co_consts:
			if isinstance(k, tip_cod):
				if k.co_name == "AttributeParser":
					return set(x.co_name for x in k.co_consts if isinstance(x, tip_cod))
				stiva.append(k)
	return None


def _magic():
	try:
		import importlib.util
		return importlib.util.MAGIC_NUMBER
	except Exception:
		import imp
		return imp.get_magic()


def _cod_din_pyc(cale):
	# marshal citeste doar skin.pyc/skin.pyo al imaginii (fisier de sistem din /usr/lib/enigma2/python);
	# codul nu se executa, se citesc doar numele metodelor
	with open(cale, "rb") as f:
		date = f.read()
	if date[:4] != _magic():
		return None  # compilat de alt Python: nu ghicim
	if sys.version_info[0] == 2:
		antet = 8
	elif sys.version_info[:2] >= (3, 7):
		antet = 16
	else:
		antet = 12
	return marshal.loads(date[antet:])


def metode_imagine(dosar=None):
	"""(set de metode AttributeParser, fisierul citit); (None, motiv) daca nu se poate afla."""
	dosar = dosar or DOSAR_PYTHON
	sursa = os.path.join(dosar, "skin.py")
	if os.path.isfile(sursa):
		try:
			with io.open(sursa, "rb") as f:
				text = f.read()
			m = re.search(br"^class AttributeParser\b.*?(?=^\S)", text, re.M | re.S)
			if m is None:
				return None, "skin.py fara AttributeParser"
			return set(x.decode("ascii") for x in re.findall(br"^\s+def (\w+)\(self\b", m.group(0), re.M)), sursa
		except Exception as e:
			return None, "skin.py: %s" % e
	candidati = []
	tag = getattr(getattr(sys, "implementation", None), "cache_tag", None)
	if tag:
		candidati += [os.path.join(dosar, "__pycache__", "skin.%s.pyc" % tag), os.path.join(dosar, "__pycache__", "skin.%s.opt-1.pyc" % tag)]
	candidati += [os.path.join(dosar, "skin.pyc"), os.path.join(dosar, "skin.pyo")]
	for cale in candidati:
		if not os.path.isfile(cale):
			continue
		try:
			cod = _cod_din_pyc(cale)
		except Exception as e:
			return None, "%s: %s" % (cale, e)
		if cod is None:
			continue
		metode = _metode_din_cod(cod)
		if metode is None:
			return None, "%s fara AttributeParser" % cale
		return metode, cale
	return None, "nu gasesc skin.py/skin.pyc/skin.pyo potrivit in %s" % dosar


def alege(dosar=None):
	"""("noua" sau "generala", motiv)."""
	metode, unde = metode_imagine(dosar)
	if metode is None:
		return "generala", unde
	lipsa = [m for m in CERUTE if m not in metode]
	if lipsa:
		return "generala", "%s: lipseste %s" % (unde, ", ".join(lipsa))
	return "noua", unde


def aplica(cale=None, dosar=None):
	"""Pune skin.xml in varianta potrivita imaginii. Intoarce (varianta, motiv, schimbat).
	Pe imaginile vechi skin.xml ramane cum a venit din pachet (generala). Scriere atomica."""
	cale = cale or SKIN_XML
	var, motiv = alege(dosar)
	if var != "noua":
		return var, motiv, False
	with open(cale, "rb") as f:
		date = f.read()
	if e_noua(date):
		return var, motiv, False
	nou = fa_noua(date)
	from paleta import _scrie_atomic  # acelasi dosar; paleta.py nu importa nimic din enigma
	_scrie_atomic(cale, nou)
	return var, motiv, True


if __name__ == "__main__":
	v, motiv, schimbat = aplica()
	print("HDSATELIT-SKIN-VARIANTA %s %s (%s)" % (v, "scrisa" if schimbat else "la-zi", motiv))
