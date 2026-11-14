# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsScreensavere.py: lista screensaverelor (protectia ecranului) si datele lor, fara enigma2 la incarcare (probele de pe PC
# il incarca direct). Ecranele sunt in Screens/HdsScreensaver.py; pagina web in HdsWebControl/screensaver_web.py.
#
# Regulile tuturor screensaverelor: nimic nu ramane pe loc (blocul intreg se muta incet, cu pozitieDrift), litere mari
# pentru canapea, usor pentru procesor (o schimbare la cateva secunde, fara animatii cu multe cadre, fara rotiri de poze).
# Omul nu configureaza nimic aici: orasul vremii vine din setarea vremii (sau din fusul orar), tara calendarului din
# „Locul meu” (config.hds_locul.tara) sau din fusul orar, pozele din dosarele Poze/Pictures/DCIM de pe stick sau disc.
#
# Alegerea omului: config.usage.hds_screensaver (id-ul din LISTA). Pornirea dupa timp si canalele numai cu sunet sunt
# ale mecanismului din Screens/ScreenSaver.py (InfoBarScreenSaver), care cheama Screens.HdsScreensaver.ecranAles().

from __future__ import absolute_import

import calendar
import datetime
import json
import math
import os
import random
import threading
import time


def N_(text):
	return text


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# (id, nume, descriere): ordinea din lista de pe televizor si din web; primul e implicit.
LISTA = (
	("automat", N_("Automat"), N_("Ziua: ora, vremea și ce urmează pe canal. Noaptea: cerul întunecat, cu ora.")),
	("ceas", N_("Ceas"), N_("Ora mare, cu ziua și data. Se mută încet pe ecran.")),
	("mozaic", N_("Ceas, vremea și canalul"), N_("Ora, vremea de afară și ce urmează pe canal, pe un singur ecran.")),
	("vremea", N_("Vremea"), N_("Vremea din orașul tău acum și în zilele următoare.")),
	("urmeaza", N_("Ce urmează pe canal"), N_("Emisiunea de acum și următoarele trei de pe canalul pe care l-ai lăsat.")),
	("galerie", N_("Galeria de poze"), N_("Pozele tale de pe stick sau disc, una după alta. Fără ele, imaginile noastre.")),
	("stiri", N_("Știri HD Satelit"), N_("Titlurile noi de pe hdsatelit.com, câte unul.")),
	("sigla", N_("Sigla canalului"), N_("Sigla canalului plutește încet pe ecranul negru.")),
	("calendar", N_("Calendarul"), N_("Luna de acum, cu ziua de azi și zilele libere ale țării tale.")),
	("receptor", N_("Receptorul"), N_("Temperatura, procesorul, discul, semnalul și următoarea înregistrare.")),
	("cer", N_("Cer de noapte"), N_("Stele care se aprind încet și luna în faza de azi.")),
	("pe-rand", N_("Pe rând, câte unul"), N_("De fiecare dată când pornește, altul din listă.")),
)
SPECIALE = ("automat", "pe-rand")
IDURI = tuple(i for i, _n, _d in LISTA)
IMPLICIT = "automat"
NOAPTEA = (23, 6)  # de la 23:00 pana la 06:00, „Automat” arata cerul de noapte
PREVIZUALIZARI = "/usr/share/enigma2/HDSatelit/screensaver"  # din tema (stratul: receptor/skin/src)


def initConfig():
	"""Setarea alegerii. Cand mecanismul (Screens/ScreenSaver.py) are config.usage.screenSaverMode cu felurile de aici in
	alegeri, omul are o singura setare si o folosim pe ea; altfel config.usage.hds_screensaver, o singura data."""
	from Components.config import config, ConfigSelection, ConfigSubsection
	mod = getattr(getattr(config, "usage", None), "screenSaverMode", None)
	try:
		if mod is not None and IMPLICIT in [c[0] if isinstance(c, (tuple, list)) else c for c in mod.choices.choices]:
			return mod
	except AttributeError:
		pass
	if not hasattr(config, "usage"):
		config.usage = ConfigSubsection()
	if not hasattr(config.usage, "hds_screensaver"):
		config.usage.hds_screensaver = ConfigSelection(
			default=IMPLICIT, choices=[(i, _t(n)) for i, n, _d in LISTA])
	return config.usage.hds_screensaver


def ales():
	try:
		v = initConfig().value
	except Exception:
		return IMPLICIT
	return v if v in IDURI else IMPLICIT


def alege(ident):
	"""Pune screensaverul ales; intoarce True cand id-ul e cunoscut."""
	if ident not in IDURI:
		return False
	c = initConfig()
	c.value = ident
	c.save()
	_porneste_felul_ales(c)
	try:
		from Components.config import configfile
		configfile.save()
	except Exception:
		pass
	return True


def _porneste_felul_ales(c):
	"""0.7.5 (R075): alegerea din meniu sau din web face screensaverul si cel aratat de protectia ecranului: felul
	config.usage.screenSaverMode trece pe „Screensaverul ales” (Components/HdsRadioSetari.PROTECTIE_FEL_ALES), ca omul
	sa nu mai caute a doua setare. Nimic cand alegerea sta chiar in screenSaverMode sau cand mecanismul lipseste."""
	try:
		from Components.config import config
		mod = getattr(getattr(config, "usage", None), "screenSaverMode", None)
		if mod is None or mod is c:
			return
		from Components.HdsRadioSetari import PROTECTIE_FEL_ALES
		if PROTECTIE_FEL_ALES in [x[0] if isinstance(x, (tuple, list)) else x for x in mod.choices.choices]:
			mod.value = PROTECTIE_FEL_ALES
			mod.save()
	except Exception as e:
		print("[HdsScreensavere] felul protectiei: %s" % e)


def nume(ident):
	for i, n, _d in LISTA:
		if i == ident:
			return _t(n)
	return ident


def descriere(ident):
	for i, _n, d in LISTA:
		if i == ident:
			return _t(d)
	return ""


def previzualizare(ident):
	"""Calea pozei mici (PNG 576x324) a screensaverului, sau sir gol."""
	cale = os.path.join(PREVIZUALIZARI, ident + ".png")
	return cale if os.path.isfile(cale) else ""


def automat(ora=None):
	"""Pentru „Automat”: noaptea cerul de noapte, ziua mozaicul (ora, vremea si canalul)."""
	ora = time.localtime().tm_hour if ora is None else ora
	return "cer" if ora >= NOAPTEA[0] or ora < NOAPTEA[1] else "mozaic"


def urmatorulPeRand(curent):
	"""Pentru „Pe rand”: urmatorul screensaver din lista (fara „automat” si „pe-rand”)."""
	ids = [i for i in IDURI if i not in SPECIALE]
	if curent not in ids:
		return ids[0]
	return ids[(ids.index(curent) + 1) % len(ids)]


# ---------------------------------------------------------------- mutarea lenta (nimic pe loc)

def pozitieDrift(pas, lat_ecran, inalt_ecran, lat_bloc, inalt_bloc, margine=0.05):
	"""Pozitia blocului la pasul dat: o curba lenta si inchisa (Lissajous) prin toata zona sigura, fara salturi mari.
	Cu un pas la 30 s, blocul trece prin tot ecranul in cateva ore si nu sta niciodata pe loc."""
	mx, my = int(lat_ecran * margine), int(inalt_ecran * margine)
	liber_x = max(0, lat_ecran - lat_bloc - 2 * mx)
	liber_y = max(0, inalt_ecran - inalt_bloc - 2 * my)
	x = mx + int(liber_x * (0.5 + 0.5 * math.sin(pas * 0.071)))
	y = my + int(liber_y * (0.5 + 0.5 * math.sin(pas * 0.053 + 1.3)))
	return x, y


def pasRicoseu(x, y, dx, dy, lat_ecran, inalt_ecran, lat_bloc, inalt_bloc):
	"""Un pas al siglei care se loveste de margini: intoarce (x, y, dx, dy)."""
	x, y = x + dx, y + dy
	if x <= 0 or x + lat_bloc >= lat_ecran:
		dx = -dx
		x = min(max(x, 0), max(0, lat_ecran - lat_bloc))
	if y <= 0 or y + inalt_bloc >= inalt_ecran:
		dy = -dy
		y = min(max(y, 0), max(0, inalt_ecran - inalt_bloc))
	return x, y, dx, dy


# ---------------------------------------------------------------- ceas, data

ZILE = (N_("Luni"), N_("Marți"), N_("Miercuri"), N_("Joi"), N_("Vineri"), N_("Sâmbătă"), N_("Duminică"))
ZILE_SCURT = (N_("Lu"), N_("Ma"), N_("Mi"), N_("Jo"), N_("Vi"), N_("Sâ"), N_("Du"))
LUNI = (N_("ianuarie"), N_("februarie"), N_("martie"), N_("aprilie"), N_("mai"), N_("iunie"), N_("iulie"),
	N_("august"), N_("septembrie"), N_("octombrie"), N_("noiembrie"), N_("decembrie"))
LUNI_TITLU = (N_("Ianuarie"), N_("Februarie"), N_("Martie"), N_("Aprilie"), N_("Mai"), N_("Iunie"), N_("Iulie"),
	N_("August"), N_("Septembrie"), N_("Octombrie"), N_("Noiembrie"), N_("Decembrie"))


def textData(t=None, cu_anul=True):
	"""„Joi, 12 noiembrie 2026”."""
	z = datetime.date.fromtimestamp(t if t is not None else time.time())
	s = "%s, %d %s" % (_t(ZILE[z.weekday()]), z.day, _t(LUNI[z.month - 1]))
	return s + (" %d" % z.year if cu_anul else "")


def textOra(t=None):
	return time.strftime("%H:%M", time.localtime(t if t is not None else time.time()))


# ---------------------------------------------------------------- luna

LUNA_SINODICA = 29.530588853
LUNA_NOUA_REPER = 947182440.0  # 6 ianuarie 2000, 18:14 UTC


def fazaLunii(t=None):
	"""(varsta in zile 0..29.5, partea luminata 0..1, numele fazei)."""
	t = time.time() if t is None else t
	varsta = ((t - LUNA_NOUA_REPER) / 86400.0) % LUNA_SINODICA
	luminata = (1 - math.cos(2 * math.pi * varsta / LUNA_SINODICA)) / 2
	if varsta < 1.0 or varsta > LUNA_SINODICA - 1.0:
		n = N_("Lună nouă")
	elif abs(varsta - LUNA_SINODICA / 2) < 1.0:
		n = N_("Lună plină")
	elif varsta < LUNA_SINODICA / 2:
		n = N_("Lună în creștere")
	else:
		n = N_("Lună în descreștere")
	return varsta, luminata, n


def stele(numar, lat, inalt, samanta=None):
	"""Pozitiile si marimile stelelor (x, y, marime 2..5), aceleasi pentru aceeasi samanta."""
	r = random.Random(samanta)
	return [(r.randint(0, lat - 6), r.randint(0, inalt - 6), r.choice((2, 2, 2, 3, 3, 4, 5))) for _i in range(numar)]


# ---------------------------------------------------------------- zilele libere

def pasteOrtodox(an):
	"""Data Pastelui ortodox (calendarul gregorian), algoritmul lui Meeus pentru calendarul iulian + 13 zile."""
	a, b, c = an % 4, an % 7, an % 19
	d = (19 * c + 15) % 30
	e = (2 * a + 4 * b - d + 34) % 7
	luna = (d + e + 114) // 31
	zi = (d + e + 114) % 31 + 1
	return datetime.date(an, luna, zi) + datetime.timedelta(days=13)


def pasteCatolic(an):
	"""Algoritmul anonim gregorian (Meeus/Jones/Butcher)."""
	a, b, c = an % 19, an // 100, an % 100
	d, e = b // 4, b % 4
	f = (b + 8) // 25
	g = (b - f + 1) // 3
	h = (19 * a + b - d - g + 15) % 30
	i, k = c // 4, c % 4
	l = (32 + 2 * e + 2 * i - h - k) % 7
	m = (a + 11 * h + 22 * l) // 451
	luna = (h + l - 7 * m + 114) // 31
	zi = (h + l - 7 * m + 114) % 31 + 1
	return datetime.date(an, luna, zi)


ANUL_NOU = N_("Anul Nou")
CRACIUN = N_("Crăciunul")
CRACIUN2 = N_("A doua zi de Crăciun")
PASTE = N_("Paștele")
PASTE2 = N_("A doua zi de Paște")
VINEREA = N_("Vinerea Mare")
RUSALII = N_("Rusaliile")
RUSALII2 = N_("A doua zi de Rusalii")
INALTARE = N_("Înălțarea Domnului")
MUNCA = N_("Ziua Muncii")
NATIONALA = N_("Ziua Națională")
ADORMIREA = N_("Adormirea Maicii Domnului")
TOTI_SFINTII = N_("Ziua tuturor sfinților")
BOBOTEAZA = N_("Boboteaza")
COPILULUI = N_("Ziua Copilului")
CORPUS = N_("Corpus Christi")
VICTORIEI = N_("Ziua Victoriei")
INDEPENDENTEI = N_("Ziua Independenței")
CONSTITUTIEI = N_("Ziua Constituției")
UNIRII = N_("Ziua Unirii")
ANDREI = N_("Sfântul Andrei")
REVOLUTIEI = N_("Ziua Revoluției")
FEMEII = N_("Ziua Femeii")
REPUBLICII = N_("Ziua Republicii")
UNITATII = N_("Ziua Unității")
LIBERARII = N_("Ziua Eliberării")

# tara: (felul Pastelui: "o" ortodox, "c" catolic, "" fara), [(luna, zi, nume)], [(zile dupa Paste, nume)]
ZILE_LIBERE = {
	"RO": ("o", [(1, 1, ANUL_NOU), (1, 2, ANUL_NOU), (1, 6, BOBOTEAZA), (1, 7, N_("Sfântul Ioan")), (1, 24, UNIRII),
		(5, 1, MUNCA), (6, 1, COPILULUI), (8, 15, ADORMIREA), (11, 30, ANDREI), (12, 1, NATIONALA), (12, 25, CRACIUN), (12, 26, CRACIUN2)],
		[(-2, VINEREA), (0, PASTE), (1, PASTE2), (49, RUSALII), (50, RUSALII2)]),
	"MD": ("o", [(1, 1, ANUL_NOU), (1, 7, CRACIUN), (1, 8, CRACIUN2), (3, 8, FEMEII), (5, 1, MUNCA), (5, 9, VICTORIEI),
		(6, 1, COPILULUI), (8, 27, INDEPENDENTEI), (8, 31, N_("Limba noastră")), (12, 25, CRACIUN)],
		[(0, PASTE), (1, PASTE2), (8, N_("Paștele Blajinilor"))]),
	"HU": ("c", [(1, 1, ANUL_NOU), (3, 15, NATIONALA), (5, 1, MUNCA), (8, 20, NATIONALA), (10, 23, NATIONALA),
		(11, 1, TOTI_SFINTII), (12, 25, CRACIUN), (12, 26, CRACIUN2)], [(-2, VINEREA), (0, PASTE), (1, PASTE2), (50, RUSALII2)]),
	"PL": ("c", [(1, 1, ANUL_NOU), (1, 6, BOBOTEAZA), (5, 1, MUNCA), (5, 3, CONSTITUTIEI), (8, 15, ADORMIREA),
		(11, 1, TOTI_SFINTII), (11, 11, INDEPENDENTEI), (12, 24, CRACIUN), (12, 25, CRACIUN), (12, 26, CRACIUN2)],
		[(0, PASTE), (1, PASTE2), (49, RUSALII), (60, CORPUS)]),
	"DE": ("c", [(1, 1, ANUL_NOU), (5, 1, MUNCA), (10, 3, UNITATII), (12, 25, CRACIUN), (12, 26, CRACIUN2)],
		[(-2, VINEREA), (1, PASTE2), (39, INALTARE), (50, RUSALII2)]),
	"AT": ("c", [(1, 1, ANUL_NOU), (1, 6, BOBOTEAZA), (5, 1, MUNCA), (8, 15, ADORMIREA), (10, 26, NATIONALA),
		(11, 1, TOTI_SFINTII), (12, 8, N_("Imaculata Concepție")), (12, 25, CRACIUN), (12, 26, CRACIUN2)],
		[(1, PASTE2), (39, INALTARE), (50, RUSALII2), (60, CORPUS)]),
	"IT": ("c", [(1, 1, ANUL_NOU), (1, 6, BOBOTEAZA), (4, 25, LIBERARII), (5, 1, MUNCA), (6, 2, REPUBLICII),
		(8, 15, ADORMIREA), (11, 1, TOTI_SFINTII), (12, 8, N_("Imaculata Concepție")), (12, 25, CRACIUN), (12, 26, CRACIUN2)],
		[(0, PASTE), (1, PASTE2)]),
	"ES": ("c", [(1, 1, ANUL_NOU), (1, 6, BOBOTEAZA), (5, 1, MUNCA), (8, 15, ADORMIREA), (10, 12, NATIONALA),
		(11, 1, TOTI_SFINTII), (12, 6, CONSTITUTIEI), (12, 8, N_("Imaculata Concepție")), (12, 25, CRACIUN)],
		[(-2, VINEREA)]),
	"FR": ("c", [(1, 1, ANUL_NOU), (5, 1, MUNCA), (5, 8, VICTORIEI), (7, 14, NATIONALA), (8, 15, ADORMIREA),
		(11, 1, TOTI_SFINTII), (11, 11, N_("Ziua Armistițiului")), (12, 25, CRACIUN)], [(1, PASTE2), (39, INALTARE), (50, RUSALII2)]),
	"GB": ("c", [(1, 1, ANUL_NOU), (12, 25, CRACIUN), (12, 26, CRACIUN2)], [(-2, VINEREA), (1, PASTE2)]),
	"NL": ("c", [(1, 1, ANUL_NOU), (4, 27, N_("Ziua Regelui")), (12, 25, CRACIUN), (12, 26, CRACIUN2)],
		[(0, PASTE), (1, PASTE2), (39, INALTARE), (49, RUSALII), (50, RUSALII2)]),
	"BE": ("c", [(1, 1, ANUL_NOU), (5, 1, MUNCA), (7, 21, NATIONALA), (8, 15, ADORMIREA), (11, 1, TOTI_SFINTII),
		(11, 11, N_("Ziua Armistițiului")), (12, 25, CRACIUN)], [(1, PASTE2), (39, INALTARE), (50, RUSALII2)]),
	"PT": ("c", [(1, 1, ANUL_NOU), (4, 25, LIBERARII), (5, 1, MUNCA), (6, 10, NATIONALA), (8, 15, ADORMIREA),
		(10, 5, REPUBLICII), (11, 1, TOTI_SFINTII), (12, 1, INDEPENDENTEI), (12, 8, N_("Imaculata Concepție")),
		(12, 25, CRACIUN)], [(-2, VINEREA), (0, PASTE), (60, CORPUS)]),
	"CZ": ("c", [(1, 1, ANUL_NOU), (5, 1, MUNCA), (5, 8, LIBERARII), (7, 5, N_("Sfinții Chiril și Metodiu")),
		(7, 6, N_("Ziua lui Jan Hus")), (9, 28, NATIONALA), (10, 28, INDEPENDENTEI), (11, 17, N_("Ziua Libertății")),
		(12, 24, CRACIUN), (12, 25, CRACIUN), (12, 26, CRACIUN2)], [(-2, VINEREA), (1, PASTE2)]),
	"SK": ("c", [(1, 1, ANUL_NOU), (1, 6, BOBOTEAZA), (5, 1, MUNCA), (5, 8, VICTORIEI), (7, 5, N_("Sfinții Chiril și Metodiu")),
		(8, 29, NATIONALA), (9, 15, N_("Fecioara Maria a celor Șapte Dureri")), (11, 1, TOTI_SFINTII),
		(11, 17, N_("Ziua Libertății")), (12, 24, CRACIUN), (12, 25, CRACIUN), (12, 26, CRACIUN2)],
		[(-2, VINEREA), (1, PASTE2)]),
	"UA": ("o", [(1, 1, ANUL_NOU), (3, 8, FEMEII), (5, 1, MUNCA), (5, 8, VICTORIEI), (6, 28, CONSTITUTIEI),
		(7, 15, N_("Ziua Statalității")), (8, 24, INDEPENDENTEI), (10, 1, N_("Ziua Apărătorilor")), (12, 25, CRACIUN)],
		[(0, PASTE), (49, RUSALII)]),
	"RU": ("", [(1, 1, ANUL_NOU), (1, 2, ANUL_NOU), (1, 7, CRACIUN), (2, 23, N_("Ziua Apărătorului Patriei")),
		(3, 8, FEMEII), (5, 1, MUNCA), (5, 9, VICTORIEI), (6, 12, NATIONALA), (11, 4, UNITATII)], []),
	"BG": ("o", [(1, 1, ANUL_NOU), (3, 3, LIBERARII), (5, 1, MUNCA), (5, 6, N_("Sfântul Gheorghe")),
		(5, 24, N_("Ziua Culturii")), (9, 6, UNIRII), (9, 22, INDEPENDENTEI), (12, 24, CRACIUN), (12, 25, CRACIUN),
		(12, 26, CRACIUN2)], [(-2, VINEREA), (0, PASTE), (1, PASTE2)]),
	"GR": ("o", [(1, 1, ANUL_NOU), (1, 6, BOBOTEAZA), (3, 25, INDEPENDENTEI), (5, 1, MUNCA), (8, 15, ADORMIREA),
		(10, 28, NATIONALA), (12, 25, CRACIUN), (12, 26, CRACIUN2)], [(-48, N_("Lunea Curată")), (-2, VINEREA), (0, PASTE),
		(1, PASTE2), (50, RUSALII2)]),
	"RS": ("o", [(1, 1, ANUL_NOU), (1, 2, ANUL_NOU), (1, 7, CRACIUN), (2, 15, NATIONALA), (2, 16, NATIONALA),
		(5, 1, MUNCA), (5, 2, MUNCA), (11, 11, N_("Ziua Armistițiului"))], [(-2, VINEREA), (0, PASTE), (1, PASTE2)]),
	"HR": ("c", [(1, 1, ANUL_NOU), (1, 6, BOBOTEAZA), (5, 1, MUNCA), (5, 30, NATIONALA), (6, 22, N_("Ziua Luptei Antifasciste")),
		(8, 5, VICTORIEI), (8, 15, ADORMIREA), (11, 1, TOTI_SFINTII), (11, 18, N_("Ziua Amintirii")), (12, 25, CRACIUN),
		(12, 26, CRACIUN2)], [(0, PASTE), (1, PASTE2), (60, CORPUS)]),
	"TR": ("", [(1, 1, ANUL_NOU), (4, 23, N_("Ziua Suveranității și a Copilului")), (5, 1, MUNCA),
		(5, 19, N_("Ziua Tineretului și Sportului")), (7, 15, N_("Ziua Democrației")), (8, 30, VICTORIEI),
		(10, 29, REPUBLICII)], []),
}


def tara():
	"""Tara omului (cod din doua litere): „Locul meu”, apoi fusul orar; sir gol cand nu se stie."""
	try:
		from Components.config import config
		t = config.hds_locul.tara.value
		if isinstance(t, str) and len(t) == 2 and t.isalpha():
			return t.upper()
	except Exception:
		pass
	try:
		fus = os.path.realpath("/etc/localtime").split("/zoneinfo/")[1]
		with open("/usr/share/zoneinfo/zone.tab", "r", encoding="utf-8") as f:
			for linie in f.read(128 * 1024).splitlines():
				c = linie.split()
				if len(c) >= 3 and not linie.startswith("#") and c[2] == fus:
					return c[0].upper()
	except (OSError, IndexError, UnicodeError):
		pass
	return ""


# Tarile al caror tabel e verificat cu lista oficiala; celelalte arata calendarul fara zile libere pana la verificare
# (ce vede omul trebuie sa fie adevarat; de pilda Marea Britanie si Turcia au si zile mobile care nu sunt inca in tabel).
VERIFICATE = ("RO", "MD")


def zileLibere(cod_tara, an, toate=False):
	"""Lista sortata (data, nume netradus) a zilelor libere legale ale tarii in anul dat; goala pentru tari necunoscute
	sau neverificate (toate=True: si cele neverificate, pentru probe)."""
	cod_tara = (cod_tara or "").upper()
	if not toate and cod_tara not in VERIFICATE:
		return []
	r = ZILE_LIBERE.get(cod_tara)
	if not r:
		return []
	fel, fixe, mobile = r
	zile = {}
	for luna, zi, n in fixe:
		zile.setdefault(datetime.date(an, luna, zi), n)
	if fel:
		paste = pasteOrtodox(an) if fel == "o" else pasteCatolic(an)
		for dupa, n in mobile:
			zile.setdefault(paste + datetime.timedelta(days=dupa), n)
	return sorted(zile.items())


def zileLibereApropiate(cod_tara, azi=None, cate=3):
	"""Urmatoarele zile libere de la azi (inclusiv), din anul acesta si urmatorul."""
	azi = azi or datetime.date.today()
	toate = zileLibere(cod_tara, azi.year) + zileLibere(cod_tara, azi.year + 1)
	return [(d, n) for d, n in toate if d >= azi][:cate]


def grilaLunii(an, luna):
	"""Saptamanile lunii, de luni pana duminica; 0 pentru zilele din alte luni."""
	return calendar.Calendar(firstweekday=0).monthdayscalendar(an, luna)


# ---------------------------------------------------------------- stirile de pe hdsatelit.com

STIRI_ADRESA = "https://www.hdsatelit.com/feed"
STIRI_CACHE = "/tmp/hds-screensaver-stiri.json"
STIRI_PERIOADA = 60 * 60
STIRI_MAX_OCTETI = 512 * 1024


def citesteRss(octeti, maxim=10):
	"""[(titlu, ora unix sau None)] din fluxul RSS 2.0 al sitului; lista goala la orice greseala."""
	import xml.etree.ElementTree as ET
	from email.utils import parsedate_tz, mktime_tz
	try:
		radacina = ET.fromstring(octeti)
	except (ET.ParseError, ValueError, TypeError):
		return []
	rez = []
	for item in radacina.iter("item"):
		titlu = (item.findtext("title") or "").strip()
		if not titlu:
			continue
		titlu = " ".join(titlu.split())[:160]
		cand = None
		data = item.findtext("pubDate")
		if data:
			p = parsedate_tz(data.strip())
			if p:
				try:
					cand = mktime_tz(p)
				except (OverflowError, ValueError):
					cand = None
		rez.append((titlu, cand))
		if len(rez) >= maxim:
			break
	return rez


class Stiri(object):
	"""Titlurile, cu cel mult o cerere pe ora si numai pe fir separat; ecranul citeste memoria (citeste()) pe ceasul lui."""

	def __init__(self, descarca=None, ceas=None, cale=STIRI_CACHE):
		self._descarca = descarca or self._descarcaUrl
		self._ceas = ceas or time.time
		self._cale = cale
		self._lacat = threading.Lock()
		self._fir = None
		self._titluri, self._cand = self._incarca()

	def _incarca(self):
		try:
			with open(self._cale, "r", encoding="utf-8") as f:
				d = json.load(f)
			return [tuple(x) for x in d.get("titluri", [])], float(d.get("cand", 0))
		except (OSError, ValueError, TypeError):
			return [], 0.0

	@staticmethod
	def _descarcaUrl():
		from urllib.request import Request, urlopen
		cerere = Request(STIRI_ADRESA, headers={"User-Agent": "HDSatelit-receptor"})
		r = urlopen(cerere, timeout=10)
		try:
			return r.read(STIRI_MAX_OCTETI)
		finally:
			r.close()

	def _lucreaza(self):
		try:
			titluri = citesteRss(self._descarca())
		except Exception:
			titluri = []
		with self._lacat:
			self._cand = self._ceas()
			if titluri:
				self._titluri = titluri
				try:
					with open(self._cale, "w", encoding="utf-8") as f:
						json.dump({"cand": self._cand, "titluri": titluri}, f, ensure_ascii=False)
				except OSError:
					pass
			self._fir = None

	def citeste(self):
		"""Intoarce imediat titlurile tinute minte; porneste cel mult un fir cand au trecut peste o ora."""
		with self._lacat:
			vechi = self._ceas() - self._cand >= STIRI_PERIOADA
			if vechi and self._fir is None:
				self._fir = threading.Thread(target=self._lucreaza, name="hds-ssv-stiri")
				self._fir.daemon = True
				self._fir.start()
			return list(self._titluri)


# ---------------------------------------------------------------- galeria de poze

DOSARE_POZE = ("Poze", "poze", "Pictures", "pictures", "Photos", "photos", "DCIM", "Imagini", "imagini", "Fotografii")
EXTENSII_POZE = (".jpg", ".jpeg", ".png")
MAX_POZE = 400
MAX_OCTETI_POZA = 15 * 1024 * 1024


def cautaPoze(radacini=None, maxim=MAX_POZE):
	"""Pozele omului din dosarele Poze/Pictures/DCIM de pe stick-uri si discuri (cel mult doua niveluri sub ele)."""
	if radacini is None:
		try:
			radacini = [os.path.join("/media", d) for d in sorted(os.listdir("/media"))]
		except OSError:
			radacini = []
	rez, vazute = [], set()
	for r in radacini:
		for d in DOSARE_POZE:
			baza = os.path.join(r, d)
			cheie = os.path.normcase(os.path.realpath(baza))
			if cheie in vazute or not os.path.isdir(baza):
				continue
			vazute.add(cheie)
			for cale, dosare, fisiere in os.walk(baza):
				if cale[len(baza):].count(os.sep) >= 2:
					dosare[:] = []
				dosare[:] = [x for x in dosare if not x.startswith(".")]
				for f in sorted(fisiere):
					if f.lower().endswith(EXTENSII_POZE) and not f.startswith("."):
						p = os.path.join(cale, f)
						try:
							if os.path.getsize(p) > MAX_OCTETI_POZA:
								continue  # o poza uriasa ar tine procesorul ocupat secunde intregi la fiecare schimbare
						except OSError:
							continue
						rez.append(p)
						if len(rez) >= maxim:
							return rez
	return rez


def pozeNoastre():
	"""Fara pozele omului: imaginile de pornire si de radio din galeria noastra, deja pe receptor."""
	rez = []
	for d in ("/etc/enigma2/hdsatelit/sigle-pornire", "/tmp/hds-galerie-sigle"):
		try:
			for f in sorted(os.listdir(d)):
				if f.lower().endswith(EXTENSII_POZE):
					rez.append(os.path.join(d, f))
		except OSError:
			pass
	return rez[:MAX_POZE]


# ---------------------------------------------------------------- receptorul

def temperatura():
	"""Temperatura receptorului in grade Celsius (int), sau None."""
	for cale in ("/proc/stb/sensors/temp0/value", "/proc/stb/fp/temp_sensor_avs", "/proc/stb/fp/temp_sensor",
			"/sys/devices/virtual/thermal/thermal_zone0/temp", "/sys/class/thermal/thermal_zone0/temp"):
		try:
			with open(cale) as f:
				v = int(f.read(32).strip().split()[0])
		except (OSError, ValueError, IndexError):
			continue
		if v > 1000:
			v //= 1000
		if 0 < v < 150:
			return v
	return None


def _jiffies():
	try:
		with open("/proc/stat") as f:
			c = [int(x) for x in f.readline().split()[1:8]]
		return sum(c), c[3] + c[4]
	except (OSError, ValueError):
		return None


class Procesor(object):
	"""Ocuparea procesorului intre doua citiri (procente), din /proc/stat."""

	def __init__(self, citire=None):
		self._citire = citire or _jiffies
		self._ultim = self._citire()

	def procent(self):
		acum = self._citire()
		vechi, self._ultim = self._ultim, acum
		if not acum or not vechi or acum[0] <= vechi[0]:
			return None
		total, inactiv = acum[0] - vechi[0], acum[1] - vechi[1]
		return max(0, min(100, int(round(100.0 * (total - inactiv) / total))))


def disc(cai=("/media/hdd", "/media/usb", "/media/mmc")):
	"""(cale, liber in octeti, total in octeti) pentru primul disc montat, sau None."""
	for c in cai:
		try:
			if not os.path.ismount(c):
				continue
			s = os.statvfs(c)
		except OSError:
			continue
		total = s.f_blocks * s.f_frsize
		if total > 0:
			return c, s.f_bavail * s.f_frsize, total
	return None


def textOcteti(n):
	for unitate, prag in (("TB", 1 << 40), ("GB", 1 << 30), ("MB", 1 << 20)):
		if n >= prag:
			v = n / float(prag)
			return ("%.1f %s" % (v, unitate)) if v < 10 else ("%d %s" % (int(v), unitate))
	return "%d KB" % (n // 1024)
