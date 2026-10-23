# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMarimeText: marimea tuturor textelor de pe ecran (config.osd.fontscale), aceeasi logica pentru ecranul de pe
# televizor (Screens/FontSetup.py) si pentru pagina web /marime-text (HdsWebControl/marime_text_web.py).
#
# Procentul se aplica in skin.py (setFontScalePercent): fiecare font citit din skin dupa aceea e inmultit cu el, deci
# ecranele deschise de acum. Ecranele deja desenate raman cum sunt; de aceea ecranul are o proba proprie, cu fonturile
# puse direct pe etichete (marime(baza, procent)), aceeasi formula ca skin._hds_scaleaza.
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc cu un config al lor.

MINIM = 80
MAXIM = 130
PAS = 5
IMPLICIT = 100


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textele se traduc la folosire."""
	return text


# Proba de pe ecran si din web: (cheia, familia din skin, marimea de baza la 1920, textul). Familiile sunt cele de pe
# orice skin (Regular, Bold, Fixed: skin.xml HDSatelit le leaga de HdsRegular, HdsBold, HdsCond), marimile sunt cele
# ale skinului HDSatelit: titlul ferestrei 40, randul de lista 32, valoarea 30, eticheta mica 24.
PROBA = (
	("proba_titlu", "Bold", 40, N_("Știri de seară, la ora 20:00")),
	("proba_rand", "Regular", 32, N_("Rândul obișnuit al unei liste: emisiunea de acum")),
	("proba_ales", "Regular", 32, N_("Rândul ales din listă")),
	("proba_setare", "Regular", 32, N_("Calitatea semnalului")),
	("proba_valoare", "Bold", 30, "87%"),
	("proba_mic", "Fixed", 24, N_("Text mic: ăâîșț ĂÂÎȘȚ 0123456789")),
)


def limiteaza(valoare):
	"""Procentul intre MINIM si MAXIM, pe treptele de PAS (de la MINIM); orice altceva da IMPLICIT."""
	try:
		v = int(valoare)
	except (TypeError, ValueError):
		return IMPLICIT
	v = max(MINIM, min(MAXIM, v))
	return MINIM + ((v - MINIM) + PAS // 2) // PAS * PAS


def urmator(valoare, directie):
	"""Procentul dupa o apasare pe Stanga (-1) sau Dreapta (+1), oprit la capete."""
	return limiteaza(limiteaza(valoare) + (PAS if directie > 0 else -PAS))


def umplere(valoare):
	"""Cat din sina glisorului se umple (0-100): de la MINIM, nu de la zero (80% = gol, 130% = plin)."""
	v = limiteaza(valoare)
	return (v - MINIM) * 100 // (MAXIM - MINIM)


def marime(baza, procent):
	"""Marimea fontului `baza` la `procent`, ca in skin.py (_hds_scaleaza)."""
	p = limiteaza(procent)
	if p == 100:
		return int(baza)
	return max(1, (int(baza) * p) // 100)


def text(valoare):
	return "%d%%" % limiteaza(valoare)


def initConfig(config=None):
	"""config.osd.fontscale (aceeasi cheie de la inceput, deci valoarea salvata ramane)."""
	if config is None:
		from Components.config import config
	if "osd" not in config.content.items:
		from Components.config import ConfigSubsection
		config.osd = ConfigSubsection()
	if "fontscale" not in config.osd.content.items:
		from Components.config import ConfigSlider
		config.osd.fontscale = ConfigSlider(default=IMPLICIT, increment=PAS, limits=(MINIM, MAXIM))
	return config.osd.fontscale


def salvat(config=None):
	return limiteaza(initConfig(config).value)


def aplica(procent, skin_modul=None):
	"""Procentul pentru fonturile citite de acum inainte din skin."""
	if skin_modul is None:
		import skin as skin_modul
	skin_modul.setFontScalePercent(limiteaza(procent))


def seteaza(procent, config=None, skin_modul=None, configfile=None):
	"""Salveaza procentul si il aplica. (True, procentul) sau (False, motivul)."""
	try:
		cerut = int(procent)
	except (TypeError, ValueError):
		return False, N_("Mărimea se dă în procente, între 80 și 130.")
	if cerut < MINIM or cerut > MAXIM:
		return False, N_("Mărimea se dă în procente, între 80 și 130.")
	v = limiteaza(cerut)
	el = initConfig(config)
	el.value = v
	el.save()
	if configfile is None:
		try:
			from Components.config import configfile
		except ImportError:
			configfile = None
	if configfile is not None:
		configfile.save()
	aplica(v, skin_modul)
	return True, v


def stare(config=None, traducere=None):
	"""Pentru pagina web: valoarea salvata, limitele si proba (textele traduse)."""
	t = traducere or (lambda s: s)
	v = salvat(config)
	return {
		"procent": v,
		"text": text(v),
		"umplere": umplere(v),
		"minim": MINIM,
		"maxim": MAXIM,
		"pas": PAS,
		"implicit": IMPLICIT,
		"proba": [{"cheie": c, "familie": f, "baza": b, "text": t(s)} for c, f, b, s in PROBA],
	}
