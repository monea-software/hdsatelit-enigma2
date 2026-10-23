# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMargini: marginile ecranului (overscan), aceeasi logica pentru ecranul de pe televizor (Screens/OSDCalibration.py)
# si pentru pagina web /margini-ecran (HdsWebControl/margini_web.py).
#
# Patru margini (sus, dreapta, jos, stanga), in pixeli ai ecranului (1920 x 1080 la skinul HDSatelit), fiecare intre 0
# si 5% din latura ei. Se tin in aceleasi setari ca pana acum: config.osd.cal_left = stanga, cal_top = sus,
# cal_width = -(stanga + dreapta), cal_height = -(sus + jos); deci valorile salvate raman.
#
# Driverul receptorului (/proc/stb/fb/dst_left, dst_top, dst_width, dst_height si dst_apply) citeste numerele in baza 16,
# in spatiul 720 x 576, si cere afisajului o micsorare pe tot ecranul (imaginea TV si meniurile): stanga = left * W /
# 720, sus = top * H / 576, dreapta = (720 - left - width) * W / 720, jos = (576 - top - height) * H / 576, cel mult 200
# de puncte pe latura. Pe un receptor fara aceste fisiere (si in
# emulator) nimic nu se scrie: ecranul arata numai unde ar ajunge marginile.
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc cu un config si un dosar ale lor.
import os

LATURI = ("sus", "dreapta", "jos", "stanga")
TOATE = "toate"
ALEGERI = (TOATE,) + LATURI
PAS = 2
PROCENT_MAXIM = 5
CALE_FB = "/proc/stb/fb"
SPATIU = (720, 576)


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textele se traduc la folosire."""
	return text


NUME = {
	TOATE: N_("Toate laturile odată"),
	"sus": N_("Latura de sus"),
	"dreapta": N_("Latura din dreapta"),
	"jos": N_("Latura de jos"),
	"stanga": N_("Latura din stânga"),
}


def implicite():
	return dict((l, 0) for l in LATURI)


def maxim(latura, latime, inaltime):
	"""Cea mai mare margine pentru latura: 5% din latime (stanga, dreapta) sau din inaltime (sus, jos), numar par."""
	baza = inaltime if latura in ("sus", "jos") else latime
	return int(baza * PROCENT_MAXIM // 100) // 2 * 2


def limiteaza(margini, latime, inaltime):
	"""Marginile intregi, intre 0 si maxim; o latura lipsa sau stricata e 0."""
	rez = {}
	for l in LATURI:
		try:
			v = int((margini or {}).get(l, 0))
		except (TypeError, ValueError):
			v = 0
		rez[l] = max(0, min(maxim(l, latime, inaltime), v))
	return rez


def muta(margini, latura, delta, latime, inaltime):
	"""Marginile dupa ce latura aleasa (sau toate) s-a dus cu `delta` spre mijloc (+) sau spre margine (-)."""
	m = dict(limiteaza(margini, latime, inaltime))
	for l in (LATURI if latura == TOATE else (latura,)):
		if l in m:
			m[l] += delta
	return limiteaza(m, latime, inaltime)


def delta_sageata(latura, sageata, pas=PAS):
	"""Cat se schimba marginea la o sageata: sageata spre marginea laturii o micsoreaza, cea opusa o mareste; la toate
	laturile Sus si Dreapta maresc cadrul, Jos si Stanga il micsoreaza; o sageata de-a lungul laturii nu face nimic."""
	if latura == TOATE:
		return -pas if sageata in ("up", "right") else pas
	spre_margine = {"sus": "up", "jos": "down", "stanga": "left", "dreapta": "right"}[latura]
	opusa = {"up": "down", "down": "up", "left": "right", "right": "left"}[spre_margine]
	if sageata == spre_margine:
		return -pas
	if sageata == opusa:
		return pas
	return 0


def urmatoarea(latura):
	"""Latura de dupa `latura` la OK: toate, sus, dreapta, jos, stanga, apoi iar toate."""
	i = ALEGERI.index(latura) if latura in ALEGERI else 0
	return ALEGERI[(i + 1) % len(ALEGERI)]


def dreptunghi(margini, latime, inaltime):
	"""(x, y, latime, inaltime) al zonei ramase intre margini."""
	m = limiteaza(margini, latime, inaltime)
	return m["stanga"], m["sus"], latime - m["stanga"] - m["dreapta"], inaltime - m["sus"] - m["jos"]


def valori_driver(margini, latime, inaltime):
	"""(left, top, width, height) pentru /proc/stb/fb/dst_*, in spatiul 720 x 576."""
	m = limiteaza(margini, latime, inaltime)
	sx, sy = SPATIU
	stanga = int(round(m["stanga"] * sx / float(latime)))
	dreapta = int(round(m["dreapta"] * sx / float(latime)))
	sus = int(round(m["sus"] * sy / float(inaltime)))
	jos = int(round(m["jos"] * sy / float(inaltime)))
	return stanga, sus, sx - stanga - dreapta, sy - sus - jos


def areDriver(cale=CALE_FB):
	return os.path.isfile(os.path.join(cale, "dst_apply"))


def aplica(margini, latime, inaltime, cale=CALE_FB, la_pornire=False):
	"""Scrie marginile in driver (in baza 16, cum le citeste el). La pornire, cu toate marginile 0, nu scrie nimic
	(afisajul porneste oricum fara micsorare). True daca s-a scris."""
	if not areDriver(cale):
		return False
	m = limiteaza(margini, latime, inaltime)
	if la_pornire and not any(m.values()):
		return False
	stanga, sus, w, h = valori_driver(m, latime, inaltime)
	try:
		for nume, v in (("dst_left", stanga), ("dst_top", sus), ("dst_width", w), ("dst_height", h)):
			with open(os.path.join(cale, nume), "w", encoding="ascii") as f:
				f.write("%08x\n" % v)
		with open(os.path.join(cale, "dst_apply"), "w", encoding="ascii") as f:
			f.write("1\n")
	except (IOError, OSError) as e:
		print("[HdsMargini] nu s-a putut scrie in %s: %s" % (cale, e))
		return False
	return True


def initConfig(config=None):
	if config is None:
		from Components.config import config
	if "osd" not in config.content.items:
		from Components.config import ConfigSubsection
		config.osd = ConfigSubsection()
	items = config.osd.content.items
	if "cal_left" not in items or "cal_top" not in items or "cal_width" not in items or "cal_height" not in items:
		from Components.config import ConfigInteger
		# limitele cuprind si valorile salvate de ecranul vechi (deplasari negative); ecranul le aduce intre 0 si maxim
		if "cal_left" not in items:
			config.osd.cal_left = ConfigInteger(default=0, limits=(-60, 200))
		if "cal_top" not in items:
			config.osd.cal_top = ConfigInteger(default=0, limits=(-60, 200))
		if "cal_width" not in items:
			config.osd.cal_width = ConfigInteger(default=0, limits=(-400, 0))
		if "cal_height" not in items:
			config.osd.cal_height = ConfigInteger(default=0, limits=(-400, 0))
	return config.osd


def citeste(latime, inaltime, config=None):
	"""Marginile salvate (sau puse acum in config), aduse intre 0 si maxim."""
	o = initConfig(config)
	stanga, sus = int(o.cal_left.value), int(o.cal_top.value)
	return limiteaza({"stanga": stanga, "sus": sus, "dreapta": -int(o.cal_width.value) - stanga,
		"jos": -int(o.cal_height.value) - sus}, latime, inaltime)


def pune(margini, latime, inaltime, config=None, salveaza=False, configfile=None):
	"""Marginile in config (cal_*); cu salveaza=True si pe disc."""
	o = initConfig(config)
	m = limiteaza(margini, latime, inaltime)
	o.cal_left.value = m["stanga"]
	o.cal_top.value = m["sus"]
	o.cal_width.value = -(m["stanga"] + m["dreapta"])
	o.cal_height.value = -(m["sus"] + m["jos"])
	if salveaza:
		for el in (o.cal_left, o.cal_top, o.cal_width, o.cal_height):
			el.save()
		if configfile is None:
			try:
				from Components.config import configfile
			except ImportError:
				configfile = None
		if configfile is not None:
			configfile.save()
	return m


def marimeEcran():
	try:
		from enigma import getDesktop
		s = getDesktop(0).size()
		if s.width() > 0 and s.height() > 0:
			return s.width(), s.height()
	except Exception:
		pass
	return 1920, 1080


def textValori(margini, traducere=None):
	t = traducere or (lambda s: s)
	# N_: xgettext vede textul numai prin cuvintele cheie din po/Makefile.am (t nu e unul dintre ele)
	return t(N_("Sus %(sus)s · Dreapta %(dreapta)s · Jos %(jos)s · Stânga %(stanga)s")) % dict(
		(l, "%d px" % margini[l]) for l in LATURI)


def stare(config=None, latime=None, inaltime=None, cale=CALE_FB, traducere=None):
	"""Pentru pagina web."""
	t = traducere or (lambda s: s)
	if latime is None or inaltime is None:
		latime, inaltime = marimeEcran()
	m = citeste(latime, inaltime, config)
	driver = areDriver(cale)
	return {
		"margini": m,
		"maxim": dict((l, maxim(l, latime, inaltime)) for l in LATURI),
		"pas": PAS,
		"latime": latime,
		"inaltime": inaltime,
		"driver": driver,
		"text": textValori(m, t),
		"nota": t(N_("Receptorul micșorează imaginea pe loc, cât reglezi.")) if driver else
			t(N_("Acest receptor nu poate muta imaginea; cadrul arată numai unde ar ajunge marginile.")),
	}


def seteaza(argumente, config=None, latime=None, inaltime=None, cale=CALE_FB, configfile=None):
	"""Marginile din web (sus, dreapta, jos, stanga, in pixeli; lipsa = cum sunt), salvate si aplicate.
	(True, marginile) sau (False, motivul)."""
	if latime is None or inaltime is None:
		latime, inaltime = marimeEcran()
	m = citeste(latime, inaltime, config)
	for l in LATURI:
		v = argumente.get(l)
		if v is None or v == "":
			continue
		try:
			n = int(v)
		except (TypeError, ValueError):
			return False, N_("Marginile se dau în pixeli, numere întregi.")
		if n < 0 or n > maxim(l, latime, inaltime):
			return False, N_("O margine e între 0 și 5 la sută din latura ei.")
		m[l] = n
	m = pune(m, latime, inaltime, config, salveaza=True, configfile=configfile)
	aplica(m, latime, inaltime, cale)
	return True, m
