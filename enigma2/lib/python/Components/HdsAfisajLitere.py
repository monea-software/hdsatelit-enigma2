# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAfisajLitere.py: ce se poate desena pe afisajul din fata (4 cifre de 7 segmente) si cum: tabelul caracterelor,
# transcrierea unui text in forme, potrivirea pe 4 pozitii, cadrele derularii, numerele cu punct, bara de nivel,
# segmentul care inconjoara afisajul si previzualizarea (desen SVG si text).
#
# Driverul primeste caractere, nu segmente: fiecare octet scris in /dev/dbox/oled0 aprinde o forma fixa, aleasa de
# driver dupa valoarea octetului (drvFP_SetString, cate un cuvant pe octet). Pe afisaj pot aparea deci numai formele
# pe care le are driverul: 53, cu locul gol si punctul singur (OCTET_PENTRU_FORMA). Tabelul de aici (FORME_CARACTERE)
# spune, pentru fiecare caracter pe care il aratam, forma pe care o vrem; octetul trimis e cel care aprinde exact acea
# forma. Asa literele pe care driverul le deseneaza greu de citit primesc forma cea mai apropiata dintre cele existente:
# K si X ieseau ca C, M ca trei bare orizontale, V si W ca cifra 4. M si W au si o forma pe doua pozitii (rn, uu),
# folosita cand incape.
#
# Masca unei pozitii: bitul 0 = a (sus), 1 = b (dreapta sus), 2 = c (dreapta jos), 3 = d (jos), 4 = e (stanga jos),
# 5 = f (stanga sus), 6 = g (mijloc), 7 = punctul. Pozitia 0 e cifra din stanga.
#
# Reguli ale driverului de care tine scrierea (octetii intorsi de octeti() le respecta):
#   - octetul 0 incheie sirul, iar pozitiile nescrise primesc masca implicita a driverului, nu locul gol: se scriu
#     mereu toate pozitiile, locul gol ca spatiu (0x20);
#   - un ':' pe pozitiile 2-4 ale sirului face ca nimic sa nu se afiseze, iar un sfarsit de rand (0x0A) de la capat e
#     taiat: niciunul nu se trimite;
#   - punctul (masca 0x80) se aprinde numai singur pe pozitie si numai pe primele doua pozitii: pe ultimele doua bitul 7
#     il pune driverul tastelor, dupa alt semn. Textele obisnuite nu il folosesc (in derulare ar clipi).
#
# O litera are o singura forma, oricum ar fi scrisa (mare sau mica): numele canalelor amesteca marimile la intamplare,
# iar la 3 m o forma constanta se citeste mai usor. Inainte de tabel textul se transcrie in litere latine fara semne:
# diacriticele se scot, chirilica si greaca se transcriu, ghilimelele si punctul dispar, restul devine spatiu.
#
# Fisierul e numai ASCII si nu importa nimic din enigma2: il folosesc afisajul, ecranul, pagina web si probele de pe PC.

try:
	import unicodedata
except ImportError:     # receptor fara modulul unicodedata: diacriticele devin spatii
	unicodedata = None

LATIME = 4
GOL = 0x00
PUNCT = 0x80

_BITI = {"a": 0x01, "b": 0x02, "c": 0x04, "d": 0x08, "e": 0x10, "f": 0x20, "g": 0x40, ".": 0x80}


def masca(segmente):
	"""Masca din literele segmentelor: masca("bc") = 0x06."""
	m = 0
	for s in segmente:
		m |= _BITI[s]
	return m


def segmenteDin(m):
	"""Literele segmentelor aprinse de masca m, in ordinea a..g si punctul."""
	return "".join(s for s in "abcdefg." if m & _BITI[s])


# ---------------------------------------------------------------- formele driverului

# Formele pe care le aprinde driverul si, pentru fiecare, octetul trimis (cand mai multi octeti aprind aceeasi forma,
# unul singur, de preferat un caracter tiparibil). Numai formele de aici pot aparea pe afisaj.
OCTET_PENTRU_FORMA = {
	0x00: 0x20,   # locul gol (spatiu)
	0x01: 0x7E,   # a
	0x02: 0x27,   # b
	0x06: 0x31,   # b c
	0x08: 0x5F,   # d
	0x0F: 0x29,   # a b c d
	0x10: 0x69,   # e
	0x18: 0x1C,   # d e
	0x1C: 0x75,   # c d e
	0x1E: 0x4A,   # b c d e
	0x20: 0x60,   # f
	0x22: 0x22,   # b f
	0x27: 0x37,   # a b c f
	0x30: 0x49,   # e f
	0x38: 0x4C,   # d e f
	0x39: 0x43,   # a d e f
	0x3D: 0x47,   # a c d e f
	0x3E: 0x55,   # b c d e f
	0x3F: 0x30,   # a b c d e f
	0x40: 0x2D,   # g
	0x46: 0x2B,   # b c g
	0x48: 0x3D,   # d g
	0x49: 0x4D,   # a d g
	0x4F: 0x33,   # a b c d g
	0x50: 0x72,   # e g
	0x52: 0x2F,   # b e g
	0x53: 0x3F,   # a b e g
	0x54: 0x6E,   # c e g
	0x58: 0x63,   # d e g
	0x5B: 0x32,   # a b d e g
	0x5C: 0x6F,   # c d e g
	0x5E: 0x64,   # b c d e g
	0x5F: 0x61,   # a b c d e g
	0x63: 0xF8,   # a b f g (semnul de grad)
	0x64: 0x5C,   # c f g
	0x66: 0x34,   # b c f g
	0x67: 0x71,   # a b c f g
	0x6D: 0x35,   # a c d f g
	0x6E: 0x79,   # b c d f g
	0x6F: 0x39,   # a b c d f g
	0x70: 0x3E,   # e f g
	0x71: 0x46,   # a e f g
	0x73: 0x50,   # a b e f g
	0x74: 0x68,   # c e f g
	0x76: 0x48,   # b c e f g
	0x77: 0x41,   # a b c e f g
	0x78: 0x74,   # d e f g
	0x79: 0x45,   # a d e f g
	0x7B: 0x65,   # a b d e f g
	0x7C: 0x62,   # c d e f g
	0x7D: 0x36,   # a c d e f g
	0x7F: 0x38,   # toate
	0x80: 0x2E,   # numai punctul
}

# ---------------------------------------------------------------- tabelul caracterelor

# Caracterul -> segmentele (un sir pe pozitie; M si W au doua pozitii). Cheile sunt caracterele de dupa transcriere.
_LATE = {
	" ": "",
	"0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg",
	"5": "acdfg", "6": "acdefg", "7": "abcf", "8": "abcdefg", "9": "abcdfg",
	"A": "abcefg",
	"B": "cdefg",          # b
	"C": "adef",
	"D": "bcdeg",          # d
	"E": "adefg",
	"F": "aefg",
	"G": "acdef",
	"H": "bcefg",
	"I": "ef",             # bara din stanga: cea din dreapta e cifra 1
	"J": "bcde",
	"K": "cefg",           # ca un h: bratul de jos al lui k; driverul il desena C
	"L": "def",
	"M": ("eg", "ceg"),    # rn; driverul il desena ca trei bare
	"N": "ceg",            # n
	"O": "cdeg",           # o mic, ca sa nu semene cu cifra 0
	"P": "abefg",
	"Q": "abcfg",          # q
	"R": "eg",             # r
	"S": "acdfg",          # la fel cu 5: alta forma nu exista
	"T": "defg",           # t
	"U": "cde",            # u mic: U mare e pastrat pentru V
	"V": "bcdef",          # U mare; driverul il desena ca 4
	"W": ("cde", "cde"),   # uu; driverul il desena ca 4
	"X": "bcefg",          # ca H: nicio forma nu are diagonale
	"Y": "bcdfg",          # y
	"Z": "abdeg",          # la fel cu 2
	"-": "g",
	"_": "d",
	"=": "dg",
	"?": "abeg",
	"/": "beg",
	"\\": "cfg",
	"(": "adef",
	")": "abcd",
	"[": "adef",
	"]": "abcd",
	"<": "bcg",
	">": "efg",
	"+": "bcg",
	"%": ("abfg", "cdeg"),  # semnul de grad si o mic, pe doua pozitii
	u"\u00b0": "abfg",      # semnul de grad
}

# Forma pe o singura pozitie, pentru un text care altfel nu incape (potrivit()).
_INGUSTE = {
	"M": "ceg",
	"W": "cde",
	"%": "beg",
}


def _forme(tabel):
	rez = {}
	for c, s in tabel.items():
		if isinstance(s, tuple):
			rez[c] = tuple(masca(x) for x in s)
		else:
			rez[c] = (masca(s),)
	return rez


FORME_CARACTERE = _forme(_LATE)
FORME_INGUSTE = _forme(_INGUSTE)

# ---------------------------------------------------------------- transcrierea

# Caracterele care nu se desfac in litera de baza plus semne (NFKD): transcrierea lor.
_SPECIALE = {
	u"\u00df": "SS", u"\u00e6": "AE", u"\u00f8": "O", u"\u0153": "OE", u"\u0111": "D", u"\u0142": "L",
	u"\u00fe": "TH", u"\u00f0": "D", u"\u0131": "I", u"\u0127": "H", u"\u0138": "K", u"\u014b": "N",
	u"\u2044": "/", u"\u2013": "-", u"\u2014": "-", u"\u2212": "-", u"\u00b0": u"\u00b0", u"\u00ba": u"\u00b0",
	u"\u00a0": " ",
}

# Semnele care dispar (ghilimelele, apostroful, punctul, semnul exclamarii) si cele care devin spatiu.
_DISPAR = set(u"\"'`.!\u201c\u201d\u201e\u201f\u2018\u2019\u201a\u00ab\u00bb\u2039\u203a")
_SPATIU = set(u",;:|*#&@$^~\t\r\n")

# Chirilica: U+0430 .. U+044F (a .. ya), dupa litera mica.
_CHIRILICA = (
	"A", "B", "V", "G", "D", "E", "ZH", "Z", "I", "I", "K", "L", "M", "N", "O", "P",
	"R", "S", "T", "U", "F", "H", "TS", "CH", "SH", "SCH", "", "Y", "", "E", "YU", "YA",
)
_CHIRILICA_ALTE = {
	u"\u0451": "E", u"\u0452": "DJ", u"\u0453": "G", u"\u0454": "IE", u"\u0455": "DZ", u"\u0456": "I",
	u"\u0457": "I", u"\u0458": "J", u"\u0459": "LJ", u"\u045a": "NJ", u"\u045b": "C", u"\u045c": "K",
	u"\u045e": "U", u"\u045f": "DZ", u"\u0491": "G",
}
# Greaca: U+03B1 .. U+03C9 (alfa .. omega), dupa litera mica.
_GREACA = (
	"A", "V", "G", "D", "E", "Z", "I", "TH", "I", "K", "L", "M", "N", "X", "O", "P",
	"R", "S", "S", "T", "Y", "F", "CH", "PS", "O",
)


def _litera(ch):
	"""Un caracter (dupa NFKD, fara semne) -> sirul lui in caracterele tabelului."""
	if ch in _DISPAR:
		return ""
	if ch in _SPATIU:
		return " "
	if ch in _SPECIALE:
		return _SPECIALE[ch]
	mare = ch.upper()
	if mare in FORME_CARACTERE:
		return mare
	mic = ch.lower()
	cod = ord(mic)
	if 0x430 <= cod <= 0x44F:
		return _CHIRILICA[cod - 0x430]
	if mic in _CHIRILICA_ALTE:
		return _CHIRILICA_ALTE[mic]
	if 0x3B1 <= cod <= 0x3C9:
		return _GREACA[cod - 0x3B1]
	if mic in _SPECIALE:
		return _SPECIALE[mic]
	return " "


def _text(text):
	if text is None:
		return u""
	if isinstance(text, bytes):
		return text.decode("utf-8", "replace")
	return text


def transcrie(text):
	"""Textul in caracterele tabelului: litere latine mari fara semne, cifre si semnele desenabile; spatiile repetate
	se strang, iar cele de la capete se taie."""
	text = _text(text)
	if unicodedata is not None:
		text = unicodedata.normalize("NFKD", text)
		text = u"".join(c for c in text if not unicodedata.combining(c))
	rez = u"".join(_litera(c) for c in text)
	return u" ".join(rez.split())


# ---------------------------------------------------------------- formele unui text

def forme(text, ingust=False):
	"""Mastile pozitiilor pentru un text: M, W si % pe doua pozitii, afara de ingust=True."""
	rez = []
	for c in transcrie(text):
		f = (FORME_INGUSTE.get(c) if ingust else None) or FORME_CARACTERE.get(c, (GOL,))
		rez.extend(f)
	return rez


def latimeText(text):
	"""Cate pozitii ia textul pe afisaj (cu formele late)."""
	return len(forme(text))


def potrivit(text, latime=LATIME, dreapta=False):
	"""Exact `latime` masti pentru un text fix: formele late daca incap, altfel cele inguste; ce tot nu incape se taie
	la dreapta. dreapta=True aliniaza la dreapta (numere)."""
	f = forme(text)
	if len(f) > latime:
		f = forme(text, ingust=True)
	f = f[:latime]
	gol = [GOL] * (latime - len(f))
	return gol + f if dreapta else f + gol


def cadre(text, latime=LATIME, pana_iese=False):
	"""Cadrele derularii, fiecare de `latime` masti; un pas = o pozitie. Un text care incape da un singur cadru (cel
	din potrivit()). Fara pana_iese derularea se opreste pe ultimele pozitii ale textului; cu pana_iese textul trece de
	tot, pana la afisajul gol, ca sa reia de la capat."""
	f = forme(text)
	if len(f) <= latime:
		return [potrivit(text, latime)]
	if pana_iese:
		f = f + [GOL] * latime
	return [f[i:i + latime] for i in range(0, len(f) - latime + 1)]


def octeti(masti):
	"""Octetii de scris in dispozitiv pentru mastile date; o masca pe care driverul nu o are devine spatiu. Niciodata
	0x00, 0x0A sau ':'."""
	return bytes(bytearray(OCTET_PENTRU_FORMA.get(m, 0x20) for m in masti))


def octetiText(text, latime=LATIME, dreapta=False):
	"""Octetii unui text fix, exact `latime` (potrivit())."""
	return octeti(potrivit(text, latime, dreapta))


# ---------------------------------------------------------------- forme speciale

POZITII_CU_PUNCT = 2        # punctul se aprinde numai pe primele doua pozitii
_TREPTE_BARA = (GOL, 0x08, 0x48, 0x49)     # nimic, o bara jos, doua bare, trei bare


def potrivitCuPunct(text, latime=LATIME):
	"""Un numar cu punct zecimal (0.45, 5.1, .75): punctul ia o pozitie a lui, cu punctul singur aprins, aliniat la
	stanga. None cand punctul ar cadea dincolo de primele POZITII_CU_PUNCT pozitii sau cand textul nu incape: atunci
	se alege alta forma (fara punct, numarul s-ar citi gresit)."""
	rez = []
	for i, parte in enumerate(_text(text).split(".")):
		if i > 0:
			if len(rez) >= POZITII_CU_PUNCT:
				return None
			rez.append(PUNCT)
		rez.extend(forme(parte))
	if len(rez) > latime:
		return None
	return rez + [GOL] * (latime - len(rez))


def bara(fractie, latime=LATIME):
	"""Un nivel intre 0 si 1 ca bara de la stanga la dreapta: fiecare pozitie are trei trepte (o bara jos, doua, trei),
	deci 3 * latime trepte. Orice valoare peste 0 aprinde cel putin prima treapta."""
	try:
		f = float(fractie)
	except (TypeError, ValueError):
		f = 0.0
	if f != f:      # NaN
		f = 0.0
	f = min(1.0, max(0.0, f))
	trepte = int(round(f * 3 * latime))
	if f > 0 and trepte == 0:
		trepte = 1
	return [_TREPTE_BARA[min(3, max(0, trepte - 3 * i))] for i in range(latime)]


def inel(latime=LATIME):
	"""Cadrele unui segment care inconjoara afisajul (asteptare, cautare): sus de la stanga la dreapta, marginea din
	dreapta, jos de la dreapta la stanga, marginea din stanga. Driverul nu are segmentul c singur, deci marginile sunt
	intregi (b cu c in dreapta, e cu f in stanga)."""
	rez = []

	def cadru(i, m):
		c = [GOL] * latime
		c[i] = m
		return c
	for i in range(latime):
		rez.append(cadru(i, 0x01))
	rez.append(cadru(latime - 1, 0x06))
	for i in range(latime - 1, -1, -1):
		rez.append(cadru(i, 0x08))
	rez.append(cadru(0, 0x30))
	return rez


# ---------------------------------------------------------------- previzualizarea

def desenText(masti):
	"""Trei randuri de text, ca pe afisaj (jurnal, probe, documentatie). Fiecare pozitie are 3 coloane si o coloana
	pentru punct."""
	r0, r1, r2 = [], [], []
	for m in masti:
		r0.append(" " + ("_" if m & 0x01 else " ") + "  ")
		r1.append(("|" if m & 0x20 else " ") + ("_" if m & 0x40 else " ") + ("|" if m & 0x02 else " ") + " ")
		r2.append(("|" if m & 0x10 else " ") + ("_" if m & 0x08 else " ") + ("|" if m & 0x04 else " ")
			+ ("." if m & 0x80 else " "))
	return "\n".join("".join(r).rstrip() for r in (r0, r1, r2))


# geometria unei pozitii in desenul SVG: celula 56 x 100, segmente de 10, pasul intre pozitii 74
_GROS = 10.0
_LAT = 56.0
_INALT = 100.0
_PAS = 74.0


def _orizontal(x0, x1, y):
	t = _GROS / 2.0
	return ((x0, y), (x0 + t, y - t), (x1 - t, y - t), (x1, y), (x1 - t, y + t), (x0 + t, y + t))


def _vertical(x, y0, y1):
	t = _GROS / 2.0
	return ((x, y0), (x + t, y0 + t), (x + t, y1 - t), (x, y1), (x - t, y1 - t), (x - t, y0 + t))


def _segmenteGeometrie():
	s = _GROS / 2.0
	st, dr = s, _LAT - s
	sus, mij, jos = s, _INALT / 2.0, _INALT - s
	g = 1.5     # rostul dintre segmente
	return (
		(0x01, _orizontal(st + g, dr - g, sus)),
		(0x02, _vertical(dr, sus + g, mij - g)),
		(0x04, _vertical(dr, mij + g, jos - g)),
		(0x08, _orizontal(st + g, dr - g, jos)),
		(0x10, _vertical(st, mij + g, jos - g)),
		(0x20, _vertical(st, sus + g, mij - g)),
		(0x40, _orizontal(st + g, dr - g, mij)),
	)


_GEOMETRIE = _segmenteGeometrie()


def svg(masti, inaltime=48, aprins="#ff3b30", stins="#3a1c1c", fundal="#0b0b0b", titlu=None):
	"""Desenul pozitiilor ca SVG, cu segmentele aprinse si, mai sterse, cele stinse (pagina web, ecranul de alegere).
	`inaltime` in pixeli; latimea urmeaza proportia. `titlu` (optional) e textul pentru cititoarele de ecran."""
	n = max(1, len(masti))
	margine = 12.0
	lat = margine * 2 + _PAS * (n - 1) + _LAT + 12.0
	inalt = margine * 2 + _INALT
	px = int(round(inaltime * lat / inalt))
	parti = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img"%s>'
		% (lat, inalt, px, inaltime, ' aria-label="%s"' % _atribut(titlu) if titlu else "")]
	parti.append('<rect width="100%%" height="100%%" rx="8" fill="%s"/>' % fundal)
	for i, m in enumerate(masti):
		x0 = margine + i * _PAS
		y0 = margine
		for bit, puncte in _GEOMETRIE:
			culoare = aprins if m & bit else stins
			p = " ".join("%.1f,%.1f" % (x0 + x, y0 + y) for x, y in puncte)
			parti.append('<polygon points="%s" fill="%s"/>' % (p, culoare))
		parti.append('<circle cx="%.1f" cy="%.1f" r="5" fill="%s"/>'
			% (x0 + _LAT + 7.0, y0 + _INALT - 5.0, aprins if m & PUNCT else stins))
	parti.append("</svg>")
	return "".join(parti)


def _atribut(text):
	return (_text(text).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;"))
