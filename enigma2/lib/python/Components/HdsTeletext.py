# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTeletext.py: teletextul canalului care merge, comun pentru ecranul de pe tasta TEXT (Screens/HdsTeletext.py) si
# pentru pagina web /teletext (Plugins/Extensions/HdsWebControl/teletext_web.py).
#
# Paginile le culege nucleul (lib/dvb/hdsteletext.cpp, clasa eHdsTeletext): toate paginile si subpaginile serviciului
# primar, cat timp merge, intr-o memorie marginita. Aici: numarul tastat (trei cifre), paginile vecine, tintele tastelor
# colorate (FastText, altfel TOP, altfel -1 / +1 / +100 / pagina de pornire), subpaginile si pagina ca date (celulele
# 25 x 40) pentru web.
#
# Fisierul nu cere enigma2 la incarcare: probele de pe PC dau nucleul lor (nucleu=...).
import struct

COLOANE, RANDURI = 40, 25
PAGINA_MIN, PAGINA_MAX = 100, 899
PAGINA_IMPLICITA = 100

# atributele celulelor (aceleasi ca in lib/dvb/hdsteletext.h)
A_DUBLA_INALTIME = 1
A_DUBLA_LATIME = 2
A_SEPARAT = 4
A_ASCUNS = 8
A_INTERMITENT = 16
A_CUTIE = 32
A_JUMATATE_JOS = 64
A_JUMATATE_DREAPTA = 128

# paleta teletextului: negru, rosu, verde, galben, albastru, magenta, cyan, alb
CULORI = ("#000000", "#ff0000", "#00ff00", "#ffff00", "#0000ff", "#ff00ff", "#00ffff", "#ffffff")

# tipurile din tabelul TOP (pagina 1F0): 1 subtitrare, 2-5 pagini de bloc, 6-7 de grupa, 8 si peste pagini obisnuite
TOP_SUBTITRARE = 1
TOP_BLOC = (2, 3, 4, 5)
TOP_GRUPA = (6, 7)

_CELULA = struct.Struct("<IBBBB")

# pagina aratata acum de ecranul de pe televizor (None = ecranul e inchis): pagina web porneste de la ea
PE_TELEVIZOR = {"numar": None, "subcod": -1}


def nucleu():
	"""eHdsTeletext din enigma2, sau None (nucleu fara teletext sau pe PC)."""
	try:
		from enigma import eHdsTeletext
	except ImportError:
		return None
	try:
		return eHdsTeletext.getInstance()
	except Exception:
		return None


def _n(nucleu_dat):
	return nucleu_dat if nucleu_dat is not None else nucleu()


def disponibil(nucleu_dat=None):
	return _n(nucleu_dat) is not None


def normalizeaza(numar):
	"""Numarul unei pagini, 100..899, sau None."""
	try:
		n = int(numar)
	except (TypeError, ValueError):
		return None
	return n if PAGINA_MIN <= n <= PAGINA_MAX else None


def pagina_televizor():
	"""(numar, subcod) aratate acum pe televizor, sau (None, -1) cu ecranul inchis."""
	return PE_TELEVIZOR["numar"], PE_TELEVIZOR["subcod"]


def stare(nucleu_dat=None):
	"""Ce stie nucleul acum: {pid, are_teletext, pagini, subpagini, octeti, versiune, bune, rele, nume, initiala}."""
	n = _n(nucleu_dat)
	if n is None:
		return {"pid": -1, "are_teletext": False, "pagini": 0, "subpagini": 0, "octeti": 0, "versiune": 0,
			"bune": 0, "rele": 0, "nume": "", "initiala": PAGINA_IMPLICITA, "nucleu": False}
	pid, pagini, subpagini, octeti, versiune, bune, rele = n.stare()
	initiala = normalizeaza(n.paginaInitiala()) or PAGINA_IMPLICITA
	nume = n.numeServiciu() or ""
	return {"pid": pid, "are_teletext": pid > 0, "pagini": pagini, "subpagini": subpagini, "octeti": octeti,
		"versiune": versiune, "bune": bune, "rele": rele, "nume": nume, "initiala": initiala, "nucleu": True}


def are_teletext(nucleu_dat=None):
	n = _n(nucleu_dat)
	return n is not None and n.pid() > 0


def pagini_existente(nucleu_dat=None):
	n = _n(nucleu_dat)
	return list(n.pagini()) if n is not None else []


def subpagini(numar, nucleu_dat=None):
	n = _n(nucleu_dat)
	if n is None or normalizeaza(numar) is None:
		return []
	return list(n.subpagini(int(numar)))


def subcod_text(subcod, toate):
	"""Pozitia subpaginii pentru om: "2/5"; gol cand pagina are una singura."""
	if len(toate) < 2 or subcod not in toate:
		return ""
	return "%d/%d" % (toate.index(subcod) + 1, len(toate))


def vecina(numar, pas, existente=None):
	"""Pagina urmatoare (pas > 0) sau dinainte (pas < 0) dintre cele din memorie, cu trecere de la 899 la 100;
	fara pagini cunoscute, numarul +/- 1."""
	numar = normalizeaza(numar) or PAGINA_IMPLICITA
	existente = sorted(p for p in (existente or ()) if normalizeaza(p) is not None)
	if existente:
		if pas > 0:
			mai_mari = [p for p in existente if p > numar]
			return mai_mari[0] if mai_mari else existente[0]
		mai_mici = [p for p in existente if p < numar]
		return mai_mici[-1] if mai_mici else existente[-1]
	n = numar + (1 if pas > 0 else -1)
	if n > PAGINA_MAX:
		n = PAGINA_MIN
	if n < PAGINA_MIN:
		n = PAGINA_MAX
	return n


def _plus_suta(numar, pas):
	n = numar + pas
	while n > PAGINA_MAX:
		n -= 800
	while n < PAGINA_MIN:
		n += 800
	return n


def _top_urmatoarea(top, numar, tipuri):
	"""Urmatoarea pagina dupa `numar` (cu trecere la inceput) al carei tip TOP e in `tipuri`."""
	for k in range(1, 801):
		p = PAGINA_MIN + (numar - PAGINA_MIN + k) % 800
		t = top[p - PAGINA_MIN]
		if t in tipuri:
			return p
	return 0


def taste_colorate(numar, subcod=-1, nucleu_dat=None, initiala=PAGINA_IMPLICITA):
	"""Tintele tastelor rosu, verde, galben, albastru: {"fel": fasttext|top|simplu, "tinte": [4 numere, 0 = nimic]}.
	FastText: legaturile paginii (X/27/0). TOP: pagina dinainte si urmatoarea care se transmit, urmatoarea pagina de
	grupa si de bloc. Altfel: -1, +1, +100 si pagina de pornire."""
	numar = normalizeaza(numar) or PAGINA_IMPLICITA
	n = _n(nucleu_dat)
	if n is not None:
		leg = n.legaturi(numar, subcod)
		if leg and any(leg[:4]):
			return {"fel": "fasttext", "tinte": [int(x) for x in leg[:4]]}
		top = n.top()
		if top:
			top = bytearray(top)
			transmise = tuple(range(2, 16))
			return {"fel": "top", "tinte": [
				_top_urmatoarea_inapoi(top, numar, transmise),
				_top_urmatoarea(top, numar, transmise),
				_top_urmatoarea(top, numar, TOP_GRUPA),
				_top_urmatoarea(top, numar, TOP_BLOC)]}
	return {"fel": "simplu", "tinte": [vecina(numar, -1, ()), vecina(numar, 1, ()), _plus_suta(numar, 100),
		normalizeaza(initiala) or PAGINA_IMPLICITA]}


def _top_urmatoarea_inapoi(top, numar, tipuri):
	for k in range(1, 801):
		p = PAGINA_MIN + (numar - PAGINA_MIN - k) % 800
		if top[p - PAGINA_MIN] in tipuri:
			return p
	return 0


def decodeaza(octeti):
	"""Celulele din nucleu (1000 x 8 octeti) -> 25 de randuri a cate 40 de (cod, mozaic, culoare, fundal, atribute)."""
	celule = [_CELULA.unpack_from(octeti, k * 8) for k in range(len(octeti) // 8)]
	return [celule[r * COLOANE:(r + 1) * COLOANE] for r in range(RANDURI)]


def pagina(numar, subcod=-1, stare_text="", cu_antet=True, nucleu_dat=None):
	"""Pagina randata: {"numar", "subcod", "versiune", "gasita", "randuri"} sau None (fara nucleu, numar gresit, sau
	pagina lipsa fara cu_antet). Randurile ca la decodeaza."""
	n = _n(nucleu_dat)
	numar = normalizeaza(numar)
	if n is None or numar is None:
		return None
	r = n.pagina(numar, int(subcod), (stare_text or "")[:8], 1 if cu_antet else 0)
	if r is None:
		return None
	pg, sc, versiune, octeti = r
	return {"numar": pg, "subcod": sc, "versiune": versiune, "gasita": sc >= 0, "randuri": decodeaza(octeti)}


def litera(cod, mozaic):
	"""Textul unei celule pentru copiere: litera, sau un bloc pentru mozaic."""
	if mozaic & 0x3F:
		return "█" if (mozaic & 0x3F) == 0x3F else "▒"
	try:
		return chr(cod) if cod >= 0x20 else " "
	except (ValueError, OverflowError):
		return " "


def text_randuri(randuri, arata_ascuns=False):
	"""Cele 25 de randuri ca text (fara culori): mozaicul ca blocuri, ce e ascuns ca spatiu."""
	iesire = []
	for rand in randuri:
		s = []
		for cod, mozaic, fata, fundal, atribute in rand:
			if atribute & (A_JUMATATE_JOS | A_JUMATATE_DREAPTA) or (atribute & A_ASCUNS and not arata_ascuns):
				s.append(" ")
			else:
				s.append(litera(cod, mozaic))
		iesire.append("".join(s))
	return iesire


def text_stare(numar, tastate=""):
	"""Coloanele 0-7 ale antetului: cifrele tastate ("P1--"), altfel numarul paginii ("P100")."""
	if tastate:
		return ("P" + tastate + "-" * (3 - len(tastate)))[:8]
	return "P%d" % numar if normalizeaza(numar) else "P---"


class Tastare(object):
	"""Numarul paginii din trei cifre: prima 1-8, apoi oricare. EXIT sau o tasta de navigare sterg ce s-a tastat."""

	def __init__(self):
		self.cifre = ""

	def apasa(self, cifra):
		"""-> numarul paginii cand s-au strans trei cifre, altfel None. O prima cifra 0 sau 9 nu incepe un numar."""
		c = str(cifra)
		if len(c) != 1 or not c.isdigit():
			return None
		if not self.cifre and c in ("0", "9"):
			return None
		self.cifre += c
		if len(self.cifre) < 3:
			return None
		numar = int(self.cifre)
		self.cifre = ""
		return numar

	def sterge(self):
		self.cifre = ""

	@property
	def in_curs(self):
		return bool(self.cifre)
