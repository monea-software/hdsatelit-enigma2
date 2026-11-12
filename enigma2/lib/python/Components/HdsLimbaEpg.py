# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLimbaEpg.py: limba ghidului de programe (EPG), ca in OE-Alliance (0.7.4, forumul 588 #1914).
#
# Un canal poate trimite titlul si descrierea unei emisiuni in mai multe limbi (Digi pe Thor 0,8 grade Vest: romana si
# maghiara). Nucleul (lib/service/event.cpp, eServiceEvent::parseFrom) alege la fiecare citire din ghidul tinut minte:
# limba ghidului, apoi limba a doua, apoi engleza, apoi prima limba gasita. Pana acum limba ghidului era numai limba
# meniului (mytest.py); acum:
# - „Limba ghidului de programe” (config.misc.hds_epg_limba): Automat = limba meniului (ca pana acum), sau o limba aleasa;
# - „A doua limbă a ghidului” (config.misc.hds_epg_limba2): cand emisiunea nu are text in prima; Niciuna = ca pana acum.
# Valorile sunt coduri ISO 639 (cele doua forme ale aceleiasi limbi, de pilda „ron rum”), date nucleului ca atare;
# Automat da nucleului limba meniului („ro_RO”), pe care el o traduce in coduri (ISOtbl).
# Schimbarea se vede pe loc in ghid, fara scanare noua: nucleul alege limba la fiecare citire, din descrierile primite.
# Emisiunea de acum de pe bara canalului privit se schimba la urmatoarea actualizare trimisa de canal.
# Fara traducere: textul e cel trimis de canal. Daca un canal trimite o emisiune numai in maghiara, ramane in maghiara
# (traducerea automata a ghidului e in Components/HdsTraducereEpg.py, separata).
# In web: aceleasi doua randuri, pe pagina generica /setari?id=usage (din data/setup.xml).
# Modulul nu importa nimic din enigma la incarcare (probele de pe PC: teste/test_limba_epg_sz_074.py).

# (coduri ISO 639-2, numele limbii ca in lista limbilor meniului, deci deja tradus)
LIMBI = (
	("ron rum", "Romanian"),
	("hun", "Hungarian"),
	("eng", "English"),
	("deu ger", "German"),
	("fra fre", "French"),
	("ita", "Italian"),
	("spa esl", "Spanish"),
	("por", "Portuguese"),
	("nld dut", "Dutch"),
	("pol", "Polish"),
	("ces cze", "Czech"),
	("slk slo", "Slovakian"),
	("slv", "Slovenian"),
	("hrv scr", "Croatian"),
	("srp scc", "Serbian"),
	("bul", "Bulgarian"),
	("ell gre", "Greek"),
	("tur", "Turkish"),
	("rus", "Russian"),
	("ukr", "Ukrainian"),
	("ara", "Arabic"),
	("dan", "Danish"),
	("swe", "Swedish"),
	("nor", "Norwegian"),
	("fin", "Finnish"),
	("est", "Estonian"),
	("lav", "Latvian"),
	("lit", "Lithuanian"),
	("isl ice", "Icelandic"),
)
AUTOMAT = "auto"
NICIUNA = "---"  # ca in OE-Alliance; nucleul il ia drept „fara a doua limba”


def _t(text):
	try:
		import builtins
		return builtins._(text)
	except Exception:
		return text


def alegeri(prima=True):
	"""Randurile setarii: prima limba (cu Automat) sau a doua (cu Niciuna)."""
	limbi = [(cod, _t(nume)) for cod, nume in LIMBI]
	if prima:
		return [(AUTOMAT, _t("Automat (limba meniului)"))] + limbi
	return [(NICIUNA, _t("Niciuna"))] + limbi


def pentruNucleu(valoare, limba_meniului):
	"""Ce primeste eServiceEvent.setEPGLanguage: limba meniului pentru Automat (si pentru o valoare necunoscuta), altfel codurile."""
	if valoare == AUTOMAT or valoare not in [cod for cod, _n in LIMBI]:
		return limba_meniului
	return valoare


def initConfig():
	from Components.config import config, ConfigSelection
	if not hasattr(config.misc, "hds_epg_limba"):
		config.misc.hds_epg_limba = ConfigSelection(choices=alegeri(True), default=AUTOMAT)
		config.misc.hds_epg_limba2 = ConfigSelection(choices=alegeri(False), default=NICIUNA)
	return config.misc


def aplica(*_argumente):
	"""Limbile setarii, date nucleului; chemat la pornire, la schimbarea limbii meniului si a setarilor."""
	from enigma import eServiceEvent
	from Components.Language import language
	s = initConfig()
	meniu = language.getLanguage()
	prima = pentruNucleu(s.hds_epg_limba.value, meniu)
	a_doua = s.hds_epg_limba2.value
	if not prima:
		# la pornire, inainte ca limba meniului sa fie activa (masurat pe .122): limba de acum a nucleului ramane pana la
		# chemarea din Language.addCallback
		return
	print("language set to", meniu, "- ghidul:", prima, "/", a_doua)
	eServiceEvent.setEPGLanguage(prima)
	# un enigma2 mai vechi decat imaginea (biblioteca fara limba a doua): numai prima
	if hasattr(eServiceEvent, "setEPGLanguageAlternative"):
		eServiceEvent.setEPGLanguageAlternative(a_doua)


def porneste():
	"""mytest.py: setarile, aplicate acum si la fiecare schimbare (a lor si a limbii meniului)."""
	from Components.Language import language
	s = initConfig()
	language.addCallback(aplica)
	s.hds_epg_limba.addNotifier(aplica, initial_call=False)
	s.hds_epg_limba2.addNotifier(aplica, initial_call=False)
	aplica()
