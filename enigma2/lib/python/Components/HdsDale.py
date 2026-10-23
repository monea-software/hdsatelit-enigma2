# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDale: meniul cu dale (Screens/Menu.py, aspectul "dale" din config.skin.layout_meniu, numai cu skinul HDSatelit).
# Aici stau partile fara ecran, ca probele de pe PC sa le foloseasca direct:
#   - geometria unei dale la marimea textului aleasa (100 % si 130 %, liniar intre ele, rotunjit la par);
#   - ruperea numelui pe cel mult doua randuri, dupa latimea masurata a cuvintelor;
#   - mutarea cu sagetile in grila de 3 coloane si fereastra de 3 randuri vazute pe ecran (motorul listelor sare pe
#     pagini, deci lista primeste numai randurile vazute, iar fereastra se muta aici cate un rand);
#   - tuplul unui rand de dale si sablonul TemplatedMultiContent care il deseneaza (acelasi in skin si in cod).
# Modulul nu importa nimic din enigma2 la incarcare.
#
# Un rand al listei are trei dale. Tuplul randului:
#   [0] numele dalei alese (pe randul ales) sau al primei dale: il arata afisajul din fata prin StringListSelection;
#   [1..4] culorile etichetelor de stare: fondul si textul pentru "în lucru", fondul si textul pentru "netestat";
#   apoi, pentru fiecare dala k (0, 1, 2), campurile CAMPURI_DALA de la INCEPUT_DALE + k * LUNGIME_DALA. O dala care
#   lipseste (ultimul rand nu e plin) are None peste tot: motorul nu deseneaza nimic pentru None (text sau imagine).
# Pe randul ales motorul ia culorile din color_sel / backcolor_sel, deci fiecare text ia ambele culori din tuplu: altfel
# dalele nealese de pe randul ales s-ar colora ca alese.
import math

COLOANE = 3
RANDURI_VIZIBILE = 3

# grila din skin (ecranul MenuDale, la 1920x1080): lista la 16,104, 1744x792, randul de 264 px
INALTIME_RAND = 264
LATIME_GRILA = 1744
LATIME_DALA = 544
DALE_X = (16, 600, 1184)

# geometria la 100 % si la 130 % (coordonate in interiorul dalei, coltul ei stanga sus = 0,0). Caseta numelui are doua
# randuri intregi ale fontului (inaltimea randului in lib/gdi/font.cpp: 1,36 x marimea fontului), ca rupturile sa nu
# taie literele de jos ale randului al doilea, si e cu 8 px mai lata decat textul rupt (REZERVA_NUME): numele se rup la
# 520 px, iar masurarea si motorul pot diferi cu cativa px.
GEOMETRIE_100 = {
	"inaltime": 224, "y": 20, "stralucire": 16,
	"cifra_x": 12, "cifra_y": 12, "cifra": 36, "cifra_font": 24,
	"eticheta_y": 14, "eticheta_h": 32, "eticheta_font": 22, "eticheta_spatiu": 24, "eticheta_dreapta": 532,
	"pictograma_x": 236, "pictograma_y": 52, "pictograma": 72,
	"nume_x": 8, "nume_y": 132, "nume_l": 528, "nume_h": 84, "nume_font": 30,
}
GEOMETRIE_130 = {
	"inaltime": 248, "y": 8, "stralucire": 8,
	"cifra_x": 12, "cifra_y": 12, "cifra": 44, "cifra_font": 31,
	"eticheta_y": 12, "eticheta_h": 40, "eticheta_font": 28, "eticheta_spatiu": 32, "eticheta_dreapta": 532,
	"pictograma_x": 236, "pictograma_y": 60, "pictograma": 72,
	"nume_x": 8, "nume_y": 136, "nume_l": 528, "nume_h": 108, "nume_font": 39,
}
FONTURI = ("nume_font", "cifra_font", "eticheta_font")
FONT_DALA = "HdsBold"
# cat se lasa liber din latimea numelui la rupere (masurarea si motorul pot diferi cu cativa px)
REZERVA_NUME = 8

# pictogramele: HDSatelit/meniu/<culoare>/<glif>.png (72x72); fondurile dalei: HDSatelit/meniu/dala/<stare>-<procent>.png
CULORI_PICTOGRAMA = ("deschis", "inchis", "alb")
GLIF_EXTENSIE = "extensie"
GLIF_INTRARE = "intrare"
PROCENTE_FOND = (100, 105, 110, 115, 120, 125, 130)
STARI_FOND = ("normala", "aleasa")

# campurile unei dale in tuplul randului
CAMPURI_DALA = (
	"fond",               # imaginea dalei (normala sau aleasa, cu stralucirea), None fara imagine
	"plat",               # "" cand dala se deseneaza fara imagine (dreptunghi plin cu chenar), altfel None
	"plat_fond",          # culoarea dreptunghiului plin
	"plat_chenar",        # culoarea chenarului lui
	"pictograma",         # imaginea pictogramei, None daca lipseste
	"nume",               # numele rupt pe cel mult doua randuri, None cand se arata numele pe un rand
	"nume_rand",          # numele pe un singur rand: numai pe dala aleasa, cand nu incape in doua randuri (deruleaza)
	"culoare_nume",
	"cifra",              # "1".."9" sau None
	"culoare_cifra",
	"fond_cifra",
	"eticheta_lucru",     # "ÎN LUCRU" sau None
	"eticheta_netestat",  # "NETESTAT" sau None
)
LUNGIME_DALA = len(CAMPURI_DALA)
INCEPUT_DALE = 5
LUNGIME_RAND = INCEPUT_DALE + COLOANE * LUNGIME_DALA
LATIME_ETICHETA_SKIN = 249   # cea mai lunga eticheta din cele 13 limbi la 22 px (sablonul din skin, fara masurare)


def indice(k, camp):
	"""Locul campului `camp` al dalei k in tuplul randului."""
	return INCEPUT_DALE + k * LUNGIME_DALA + CAMPURI_DALA.index(camp)


# ---------------------------------------------------------------- geometria
def _par(v):
	return int(math.floor(v / 2.0 + 0.5)) * 2


def _font(baza, procent):
	"""Marimea fontului ca in skin.py (_hds_scaleaza): baza * procent // 100."""
	if procent == 100:
		return baza
	return max(1, (baza * procent) // 100)


def procentCurat(procent):
	try:
		p = int(procent)
	except (TypeError, ValueError):
		p = 100
	return max(80, min(130, p))


def geometrie(procent=100):
	"""Geometria dalei la marimea textului `procent` (80-130). Pana la 100 % geometria e cea de 100 %, iar fonturile
	scad ca in restul ecranelor; intre 100 si 130 % fiecare marime trece liniar spre cea de 130 %, rotunjita la par;
	fonturile cresc ca in skin.py."""
	p = procentCurat(procent)
	g = {}
	for cheie, a in GEOMETRIE_100.items():
		b = GEOMETRIE_130[cheie]
		if cheie in FONTURI:
			g[cheie] = _font(a, p)
		elif p <= 100 or a == b:
			g[cheie] = a
		elif p >= 130:
			g[cheie] = b
		else:
			g[cheie] = _par(a + (b - a) * (p - 100) / 30.0)
	g["procent"] = p
	g["procent_fond"] = procentFond(p)
	return g


def procentFond(procent):
	"""Treapta imaginilor de fond (100, 105 ... 130) pentru marimea textului."""
	p = max(100, min(130, procentCurat(procent)))
	return 100 + (p - 100) // 5 * 5


def marimeFond(g, scara=None):
	"""(latimea, inaltimea) imaginii de fond a unei dale: dala si stralucirea din jur."""
	s = scara or Scara()
	st = g["stralucire"]
	return s.l(LATIME_DALA + 2 * st), s.h(g["inaltime"] + 2 * st)


class Scara(object):
	"""Scara ecranului (skin.ScaraEcran pentru fisierele HDSatelit, None la 1920x1080): x cu sx, y cu sy, fonturile si
	grosimile cu sf (cea mai mica dintre ele). Fractiile sunt (numarator, numitor), ca in skin.py."""

	def __init__(self, sx=(1, 1), sy=(1, 1), sf=None):
		self.sx, self.sy = tuple(sx), tuple(sy)
		self.sf = tuple(sf) if sf else (self.sx if self.sx[0] * self.sy[1] <= self.sy[0] * self.sx[1] else self.sy)

	@staticmethod
	def din(scara):
		"""Din skin.ScaraEcran (sau None)."""
		if scara is None or not getattr(scara, "scaleaza", False):
			return Scara()
		return Scara(scara.sx, scara.sy, scara.sf)

	@staticmethod
	def _ori(v, f):
		n, d = f
		q = (2 * abs(v) * n + d) // (2 * d)
		return q if v >= 0 else -q

	def x(self, v):
		return self._ori(v, self.sx)

	def y(self, v):
		return self._ori(v, self.sy)

	def l(self, v):
		return max(1, self._ori(v, self.sx)) if v > 0 else 0

	def h(self, v):
		return max(1, self._ori(v, self.sy)) if v > 0 else 0

	def f(self, v):
		return max(1, self._ori(v, self.sf))


# ---------------------------------------------------------------- numele
def rupeNume(text, latime, maxim, randuri=2):
	"""Numele rupt pe cuvinte, ca sa incapa in `maxim` px pe cel mult `randuri` randuri. `latime(sir)` = latimea unui
	sir in px cu fontul dalei. Intoarce (randurile, incape): incape = False cand ar trebui mai multe randuri sau cand
	un cuvant singur e mai lat decat caseta; randurile sunt atunci toate cele rupte (mai multe decat `randuri`)."""
	cuvinte = (text or "").split()
	if not cuvinte:
		return [""], True
	facute = []
	curent = cuvinte[0]
	incape = latime(curent) <= maxim
	for c in cuvinte[1:]:
		proba = curent + " " + c
		if latime(proba) <= maxim:
			curent = proba
			continue
		facute.append(curent)
		curent = c
		if latime(c) > maxim:
			incape = False
	facute.append(curent)
	if len(facute) > randuri:
		incape = False
	return facute, incape


# ---------------------------------------------------------------- mutarea in grila
def randuri(n):
	"""Cate randuri de dale au n intrari."""
	return (n + COLOANE - 1) // COLOANE if n > 0 else 0


def dreapta(i, n):
	"""Dala urmatoare; la capatul randului, prima dala a randului urmator; pe ultima dala, prima dala."""
	return (i + 1) % n if n else 0


def stanga(i, n):
	"""Dala dinainte; la inceputul randului, ultima dala a randului dinainte; pe prima dala, ultima dala."""
	return (i - 1) % n if n else 0


def _laRand(rand, coloana, n):
	return min(rand * COLOANE + coloana, n - 1)


def jos(i, n):
	"""Aceeasi coloana pe randul urmator (ultima lui dala daca e mai scurt); pe ultimul rand, primul rand."""
	if not n:
		return 0
	r, c = divmod(i, COLOANE)
	return _laRand(r + 1 if r + 1 < randuri(n) else 0, c, n)


def sus(i, n):
	"""Aceeasi coloana pe randul dinainte; pe primul rand, ultimul rand (aceeasi coloana sau ultima lui dala)."""
	if not n:
		return 0
	r, c = divmod(i, COLOANE)
	return _laRand(r - 1 if r > 0 else randuri(n) - 1, c, n)


def dupaCifra(numar, n):
	"""Indexul intrarii cu cifra `numar` (1-9), None cand nu exista."""
	try:
		i = int(numar) - 1
	except (TypeError, ValueError):
		return None
	return i if 0 <= i < min(n, 9) else None


def fereastra(rand, inceput, total, vizibile=RANDURI_VIZIBILE):
	"""Primul rand vazut pe ecran dupa ce randul ales devine `rand`: fereastra se muta cat mai putin (cate un rand)."""
	if rand < inceput:
		inceput = rand
	elif rand >= inceput + vizibile:
		inceput = rand - vizibile + 1
	return max(0, min(inceput, max(0, total - vizibile)))


# ---------------------------------------------------------------- tuplul randului
def dalaGoala():
	return (None,) * LUNGIME_DALA


def tupluRand(dale, culori, nume_afisaj=None):
	"""Tuplul unui rand. `dale` = cel mult 3 dictionare cu cheile din CAMPURI_DALA (o cheie lipsa = None); `culori` =
	dict cu "lucru_fond", "lucru_text", "netestat_fond", "netestat_text"; `nume_afisaj` = textul pentru afisajul din
	fata (numele dalei alese sau al primei)."""
	rand = [nume_afisaj or "", culori.get("lucru_fond"), culori.get("lucru_text"), culori.get("netestat_fond"),
		culori.get("netestat_text")]
	for k in range(COLOANE):
		if k < len(dale) and dale[k] is not None:
			rand.extend(dale[k].get(camp) for camp in CAMPURI_DALA)
		else:
			rand.extend(dalaGoala())
	return tuple(rand)


def latimeEticheta(latime_text, g):
	"""Latimea etichetei de stare: textul plus spatiul din geometrie."""
	return int(latime_text) + g["eticheta_spatiu"]


def sablon(g, latimi, M, scara=None):
	"""Sablonul TemplatedMultiContent al randului: lista de intrari facute cu functiile din `M` (un obiect cu
	MultiContentEntryText, MultiContentEntryPixmapAlphaBlend, MultiContentTemplateColor si steagurile RT_*);
	`latimi` = (latimea etichetei "în lucru", latimea etichetei "netestat"), in px la 1920, cu spatiul inclus.
	Fonturile: 0 numele, 1 cifra, 2 eticheta (vezi fonturi())."""
	s = scara or Scara()
	T = M.MultiContentTemplateColor
	intrari = []
	h = g["inaltime"]
	y0 = g["y"]
	st = g["stralucire"]
	centru = M.RT_HALIGN_CENTER | M.RT_VALIGN_CENTER
	for k in range(COLOANE):
		x0 = DALE_X[k]

		def i(camp):
			return indice(k, camp)
		# fondul: imaginea are stralucirea in jur, deci incepe mai sus si mai la stanga decat dala
		intrari.append(M.MultiContentEntryPixmapAlphaBlend(pos=(s.x(x0 - st), s.y(y0 - st)),
			size=(s.l(LATIME_DALA + 2 * st), s.h(h + 2 * st)), png=i("fond")))
		# fara imagine: dreptunghi plin cu chenar (colturi drepte, fara stralucire)
		intrari.append(M.MultiContentEntryText(pos=(s.x(x0), s.y(y0)), size=(s.l(LATIME_DALA), s.h(h)), font=0,
			flags=centru, text=i("plat"), backcolor=T(i("plat_fond")), backcolor_sel=T(i("plat_fond")),
			border_width=s.f(4), border_color=T(i("plat_chenar"))))
		p = g["pictograma"]
		intrari.append(M.MultiContentEntryPixmapAlphaBlend(pos=(s.x(x0 + g["pictograma_x"]),
			s.y(y0 + g["pictograma_y"])), size=(s.l(p), s.h(p)), png=i("pictograma")))
		nx, ny, nl, nh = x0 + g["nume_x"], y0 + g["nume_y"], g["nume_l"], g["nume_h"]
		intrari.append(M.MultiContentEntryText(pos=(s.x(nx), s.y(ny)), size=(s.l(nl), s.h(nh)), font=0,
			flags=M.RT_HALIGN_CENTER | M.RT_VALIGN_TOP | M.RT_WRAP, text=i("nume"), color=T(i("culoare_nume")),
			color_sel=T(i("culoare_nume"))))
		intrari.append(M.MultiContentEntryText(pos=(s.x(nx), s.y(ny)), size=(s.l(nl), s.h(nh // 2)), font=0,
			flags=M.RT_HALIGN_CENTER | M.RT_VALIGN_TOP, text=i("nume_rand"), color=T(i("culoare_nume")),
			color_sel=T(i("culoare_nume"))))
		c = g["cifra"]
		intrari.append(M.MultiContentEntryText(pos=(s.x(x0 + g["cifra_x"]), s.y(y0 + g["cifra_y"])),
			size=(s.l(c), s.h(c)), font=1, flags=centru, text=i("cifra"), color=T(i("culoare_cifra")),
			color_sel=T(i("culoare_cifra")), backcolor=T(i("fond_cifra")), backcolor_sel=T(i("fond_cifra"))))
		for camp, latime, fond, text in (("eticheta_lucru", latimi[0], 1, 2), ("eticheta_netestat", latimi[1], 3, 4)):
			ex = x0 + g["eticheta_dreapta"] - latime
			intrari.append(M.MultiContentEntryText(pos=(s.x(ex), s.y(y0 + g["eticheta_y"])),
				size=(s.l(latime), s.h(g["eticheta_h"])), font=2, flags=centru, text=i(camp), color=T(text),
				color_sel=T(text), backcolor=T(fond), backcolor_sel=T(fond)))
	return intrari


def fonturi(g, scara=None):
	"""(familia, marimea) pentru fonturile 0, 1, 2 ale sablonului, cu scara ecranului."""
	s = scara or Scara()
	return [(FONT_DALA, s.f(g["nume_font"])), (FONT_DALA, s.f(g["cifra_font"])), (FONT_DALA, s.f(g["eticheta_font"]))]


# ---------------------------------------------------------------- textul sablonului din skin
class _Steag(str):
	def __or__(self, alt):
		return _Steag("%s | %s" % (self, alt))


class _Text(object):
	"""In locul functiilor MultiContent: scrie textul lor (sablonul din skin, facut de unealta skinului)."""
	RT_HALIGN_CENTER = _Steag("RT_HALIGN_CENTER")
	RT_VALIGN_CENTER = _Steag("RT_VALIGN_CENTER")
	RT_VALIGN_TOP = _Steag("RT_VALIGN_TOP")
	RT_WRAP = _Steag("RT_WRAP")
	ORDINE = ("pos", "size", "font", "flags", "text", "png", "color", "color_sel", "backcolor", "backcolor_sel",
		"border_width", "border_color")

	@staticmethod
	def MultiContentTemplateColor(n):
		return _Steag("MultiContentTemplateColor(%d)" % n)

	def _intrare(self, nume, k):
		def arg(v):
			return v if isinstance(v, str) else repr(v)
		return "%s(%s)" % (nume, ", ".join("%s=%s" % (a, arg(k[a])) for a in self.ORDINE if a in k))

	def MultiContentEntryText(self, **k):
		return self._intrare("MultiContentEntryText", k)

	def MultiContentEntryPixmapAlphaBlend(self, **k):
		return self._intrare("MultiContentEntryPixmapAlphaBlend", k)


def sablonSkin(procent=100):
	"""Textul convertorului TemplatedMultiContent al ecranului MenuDale din skin (rezerva, cand codul nu poate pune
	sablonul lui): geometria de la `procent`, etichetele cat cea mai lunga din cele 13 limbi."""
	g = geometrie(procent)
	latime = latimeEticheta(LATIME_ETICHETA_SKIN * g["eticheta_font"] // GEOMETRIE_100["eticheta_font"], g)
	intrari = sablon(g, (latime, latime), _Text())
	f = ", ".join('gFont("%s", %d)' % x for x in fonturi(g))
	return '{"template": [%s], "fonts": [%s], "itemHeight": %d}' % (", ".join(intrari), f, INALTIME_RAND)


# ---------------------------------------------------------------- pictogramele si culorile
def glifCurat(glif):
	"""Numele glifului din menu.xml (litere mici, cifre, liniuta) sau None."""
	if not glif:
		return None
	glif = glif.strip()
	if not glif or len(glif) > 40 or not all(("a" <= c <= "z") or ("0" <= c <= "9") or c == "-" for c in glif):
		return None
	return glif


def culoarePictograma(aleasa, luminos):
	"""Dosarul culorii pictogramei: alb pe dala aleasa, inchis pe paletele luminoase, deschis pe celelalte."""
	if aleasa:
		return "alb"
	return "inchis" if luminos else "deschis"


def luminanta(rgb):
	"""Luminanta relativa (0-1) a unei culori 0x..RRGGBB."""
	def lin(c):
		c = c / 255.0
		return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
	return 0.2126 * lin((rgb >> 16) & 255) + 0.7152 * lin((rgb >> 8) & 255) + 0.0722 * lin(rgb & 255)


def amesteca(c1, c2, t):
	"""Culoarea opaca dintre c1 si c2 (0x..RRGGBB), t intre 0 (c1) si 1 (c2)."""
	rez = 0
	for d in (16, 8, 0):
		a, b = (c1 >> d) & 255, (c2 >> d) & 255
		rez |= int(a + (b - a) * t + 0.5) << d
	return rez & 0x00FFFFFF


# culorile implicite (paleta implicita din skin.xml), cand skinul nu are una dintre ele
CULORI_IMPLICITE = {
	"hdsPanelSolid": 0x0010162A, "hdsText": 0x00F2F4F8, "hdsText2": 0x00C9D2E3, "hdsBrand": 0x00374EA1,
	"hdsBrandLight": 0x009FB4FF, "hdsAmber": 0x00F5B83D, "hdsTrack": 0x002A3350, "hdsDisabled": 0x00667085,
	"hdsMarkedText": 0x0010162A, "white": 0x00FFFFFF,
}


def culoriDale(c):
	"""Culorile dalelor (int 0x00RRGGBB, opace) din culorile skinului `c` (nume -> int): cartonasul e cu putin mai
	deschis (sau mai inchis, la paletele luminoase) decat panoul."""
	def v(nume):
		return (c.get(nume, CULORI_IMPLICITE[nume]) if c else CULORI_IMPLICITE[nume]) & 0x00FFFFFF
	panou, text, brand, brand_l = v("hdsPanelSolid"), v("hdsText"), v("hdsBrand"), v("hdsBrandLight")
	return {
		"luminos": luminanta(panou) > 0.4,
		"panou": panou,
		"cartonas": amesteca(panou, text, 0.06),
		"chenar": v("hdsTrack"),
		"marca": brand,
		"marca_deschis": brand_l,
		"nume": v("hdsText2"),
		"nume_ales": v("white"),
		"cifra": v("hdsText2"),
		"cifra_fond": panou,
		"cifra_aleasa": v("white"),
		"cifra_aleasa_fond": amesteca(brand, brand_l, 0.3),
		"lucru_fond": v("hdsAmber"),
		"lucru_text": v("hdsMarkedText"),
		"netestat_fond": v("hdsDisabled"),
		"netestat_text": v("hdsText"),
	}
