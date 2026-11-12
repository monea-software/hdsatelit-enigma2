# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# tema_export.py: culorile si stilul interfetei receptorului, scrise intr-un fisier CSS mic si stabil, pentru celelalte
# interfete web de pe receptor (intai OSCam Retuned, pe portul lui, care il serveste la /receiver-theme.css).
# Cererea lui Eduard (11.11.2026, 20:00): „Tema sa urmeze tema receptorului, in primul rand cu culorile receptorului:
# daca se schimba culorile in receptor sau alte stiluri, se schimba si in tema OSCam Retuned.”
#
# FISIERUL: /etc/enigma2/hds-tema-web.css, numai ASCII, un singur bloc :root{...} cu variabile CSS (contractul de mai jos;
# numele nu se schimba, se pot adauga altele). Il scrie numai acest modul, atomic (fisier.nou + os.replace) si numai cand
# continutul difera, deci data lui se schimba numai cand se schimba culorile.
#
# DE UNDE VIN (aceleasi culori ca interfata web a receptorului, motorul din cadru_web.py, nimic calculat de doua ori):
# - culorile: implicitele de pe receptor ale interfetei web (cadru_web.implicite(): config.plugins.hdswebcontrol.culori_web,
#   implicit „Ca pe televizor” = blocul <colors> din HDSatelit/skin.xml, pe care HdsSkinSetari il rescrie pe loc cand omul
#   alege paleta pe televizor; sau paleta pusa implicita pe receptor din web, palete.txt + paleta.deriva);
# - tema web Clasic / Pro (config.plugins.hdswebcontrol.tema_web): suprafetele (cadru_web.variabile) si coltii;
# - modul luminos / intunecat: dupa panoul paletei (aceeasi regula ca cadru_web: luminanta > 0,35 = luminos);
# - fontul interfetei web (Open Sans, al skinului).
# NU intra: alegerea proprie a unui browser (cookie-urile hds_tema / hds_culori: OSCam urmeaza receptorul, nu un
# browser), tema de pe televizor Clasic / Pro si „Aspectul meniului” (lista / dale), care schimba numai asezarea pe TV.
#
# CAND SE RESCRIE (omul nu apasa nimic): la pornirea interfetei web (plugin.porneste), cand se schimba tema sau culorile
# implicite din web (notificari pe cele doua setari) si cand se rescrie skin.xml sau palete.txt (alegerea paletei pe
# televizor scrie skin.xml pe loc, iar repornirea interfetei e lasata pe mai tarziu): o privire la 30 s la data celor
# doua fisiere si la cele doua setari, fara nimic altceva.
#
# CONTRACTUL (variabilele din :root):
#   --mod (light|dark), --tema (clasic|pro), --paleta (id-ul alegerii), color-scheme
#   suprafete: --fundal --panou --panou-2 --rand --camp --buton --buton-peste --chenar --dezactivat --antet --meniu-fundal
#              --ales --marca-fond --bine-fond --rau-fond
#   texte:     --text --text-2 --text-slab --legatura --marca --ales-text --bine --atentie --rau --chihlimbar
#   pline:     --accent (fond pentru text alb, --pe-accent) --rosu --verde --albastru --galben --bine-plin --atentie-plin
#              --rau-plin
#   pentru modul celalalt (cand omul forteaza luminos pe un receptor intunecat sau invers): --accent-pe-luminos,
#              --accent-pe-intunecat (accentul ca text, cu contrast AA pe o pagina alba / pe una bleumarin)
#   stil:      --raza (butoane, campuri), --raza-card (panouri, tabele), --font
# Contrastul AA al perechilor text / fond e cel impus de cadru_web.variabile (PERECHI).
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC dau caile si setarile.

import os

try:
	from . import cadru_web as C
except (ImportError, ValueError):  # probele de pe PC il incarca fara pachet
	import cadru_web as C

CALE = "/etc/enigma2/hds-tema-web.css"
INTERVAL_MS = 30000
MARIME_MAX = 16384  # aceeasi margine ca in OSCam (un fisier mai mare nu se serveste)

RAZE = {"pro": ("8px", "12px"), "clasic": ("4px", "4px")}
FONT = '"Open Sans",system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif'

# pagina alba / bleumarin a temei OSCam Retuned (luminoasa: #F3F5FA, panouri albe; intunecata: #0B1020, #10162A, #161E38)
FONDURI_LUMINOASE = ("#ffffff", "#f3f5fa", "#f1f5f9", "#f8fafc")
FONDURI_INTUNECATE = ("#0b1020", "#10162a", "#161e38")

# (nume in fisier, variabila din cadru_web.variabile)
DIN_VARIABILE = (
	("--fundal", "--fundal"), ("--panou", "--panou"), ("--panou-2", "--panou-2"), ("--rand", "--rand"),
	("--camp", "--camp"), ("--buton", "--buton"), ("--buton-peste", "--buton-peste"), ("--chenar", "--bordura"),
	("--dezactivat", "--dezactivat"), ("--antet", "--antet"), ("--meniu-fundal", "--meniu-fundal"), ("--ales", "--ales"),
	("--marca-fond", "--marca-fond"), ("--bine-fond", "--bine-fond"), ("--rau-fond", "--pericol-fond"),
	("--text", "--text"), ("--text-2", "--text-2"), ("--text-slab", "--text-slab"), ("--legatura", "--legatura"),
	("--marca", "--marca"), ("--ales-text", "--ales-text"), ("--bine", "--bine"), ("--atentie", "--atentie"),
	("--rau", "--eroare"), ("--chihlimbar", "--chihlimbar"),
	("--accent", "--accent"), ("--rosu", "--rosu"), ("--verde", "--verde"), ("--albastru", "--albastru"),
	("--galben", "--galben"), ("--bine-plin", "--bine-plin"), ("--atentie-plin", "--atentie-plin"),
)


def _jurnal(text):
	try:
		C._jurnal("tema_export: %s" % text)
	except Exception:
		pass


def alegere():
	"""(tema, id_culori, culori) implicite de pe receptor; culorile skinului cand alegerea nu se mai gaseste."""
	tema, pid = C.implicite()
	c = C.culoriPaleta(pid)
	if c is None:
		pid, c = C.CULORI_TV, C.culoriSkin()
	return tema, pid, c


def continut(tema, pid, c):
	"""Textul fisierului pentru tema web, id-ul culorilor si culorile date (cheile din cadru_web.CULORI_IMPLICITE)."""
	if tema not in C.TEME:
		tema = C.TEMA_IMPLICITA
	if not C._RE_ID_PALETA.match(pid or ""):
		pid = C.CULORI_TV
	v = dict(C.variabile(tema, c))
	luminos = C.luminanta(c["hdsPanelSolid"]) > 0.35
	mod = "light" if luminos else "dark"
	raza, raza_card = RAZE[tema]
	accent = v["--accent"]
	randuri = [("color-scheme", mod), ("--mod", mod), ("--tema", tema), ("--paleta", pid)]
	randuri += [(nume, v[sursa]) for nume, sursa in DIN_VARIABILE]
	randuri += [
		("--pe-accent", C.ALB),
		("--rau-plin", c["hdsBad"]),
		("--accent-pe-luminos", C.asigura(accent, FONDURI_LUMINOASE, C.PRAG_TEXT, C.NEGRU)),
		("--accent-pe-intunecat", C.asigura(c["hdsBrandLight"], FONDURI_INTUNECATE, C.PRAG_TEXT, C.ALB)),
		("--raza", raza), ("--raza-card", raza_card), ("--font", FONT),
	]
	cap = ("/* HD Satelit: the colours and the style of the receiver web interface (theme %s, colours %s, %s).\n"
		" * Written by the receiver (HdsWebControl/tema_export.py) whenever they change; do not edit. */\n" % (tema, pid, mod))
	text = cap + ":root{\n" + "".join("%s:%s;\n" % (n, x) for n, x in randuri) + "}\n"
	return text.encode("ascii", "replace").decode("ascii")


def scrie(cale=None):
	"""Scrie fisierul cu alegerea de acum, numai daca difera. True = scris, False = era la zi sau n-a mers."""
	cale = cale or CALE
	try:
		text = continut(*alegere())
	except Exception as eroare:
		_jurnal("nu pot face culorile: %s" % eroare)
		return False
	date = text.encode("ascii")
	if len(date) > MARIME_MAX:
		_jurnal("fisierul ar avea %d octeti, peste %d" % (len(date), MARIME_MAX))
		return False
	try:
		with open(cale, "rb") as f:
			if f.read(MARIME_MAX + 1) == date:
				return False
	except (IOError, OSError):
		pass
	nou = cale + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(date)
		os.chmod(nou, 0o644)
		os.replace(nou, cale)
	except (IOError, OSError) as eroare:
		_jurnal("nu pot scrie %s: %s" % (cale, eroare))
		try:
			os.remove(nou)
		except OSError:
			pass
		return False
	return True


def _mtime(cale):
	try:
		return os.path.getmtime(cale)
	except (OSError, TypeError):
		return None


def semn():
	"""Ce poate schimba fisierul: data lui skin.xml si palete.txt si cele doua setari web."""
	s = C._configWeb()
	valori = ()
	if s is not None:
		try:
			valori = (s.tema_web.value, s.culori_web.value)
		except Exception:
			valori = ()
	return (_mtime(C._caleSkin()), _mtime(C._calePalete())) + valori


_STARE = {"ceas": None, "semn": None, "cale": None}


def _verifica():
	try:
		acum = semn()
		if acum != _STARE["semn"]:
			_STARE["semn"] = acum
			scrie(_STARE["cale"])
	except Exception as eroare:
		_jurnal("verificarea: %s" % eroare)


def _laSchimbare(_element=None):
	_STARE["semn"] = None
	_verifica()


def porneste(cale=None):
	"""Scrie fisierul acum si il tine la zi (notificari pe setarile web si privirea la 30 s). O singura data."""
	_STARE["cale"] = cale
	_verifica()
	if _STARE.get("pornit"):
		return  # WHERE_SESSIONSTART poate veni de doua ori: notificarile si ceasul o singura data
	_STARE["pornit"] = True
	s = C._configWeb()
	if s is not None:
		for element in (s.tema_web, s.culori_web):
			try:
				element.addNotifier(_laSchimbare, initial_call=False)
			except Exception as eroare:
				_jurnal("notificarea: %s" % eroare)
	try:
		from enigma import eTimer
		ceas = eTimer()
		try:
			ceas.callback.append(_verifica)
		except AttributeError:
			ceas.timeout.get().append(_verifica)
		ceas.start(INTERVAL_MS, False)
		_STARE["ceas"] = ceas  # tinut aici: fara referinta, GC il culege si nu mai bate
	except Exception as eroare:
		_jurnal("ceasul: %s" % eroare)
