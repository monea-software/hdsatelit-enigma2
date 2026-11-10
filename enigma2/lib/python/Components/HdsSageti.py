# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSageti.py - ce fac sagetile SUS si JOS la privit (fara niciun meniu deschis), dupa setarea "Săgețile sus și jos la
# privit" (config.usage.hds_sageata_sus, Setari > Personalizare si /setari pe web).
#
# O singura regula pentru bara TV (Screens/InfoBarGenerics.py, InfoBarChannelSelection.switchChannelUp/Down) si pentru
# ecranul radio (Screens/HdsEcranRadio.py, listaSus/listaJos), ca cele doua sa nu se contrazica. Fiecare sageata face
# "current" (lista modului curent), "radio" (lista radio), "tv" (lista TV), "zap" (SUS urmatorul, JOS anteriorul)
# sau "zap_invers" (SUS canalul anterior, JOS cel urmator). Valorile vechi ale setarii isi pastreaza intelesul.

# valoarea setarii -> (ce face SUS, ce face JOS)
SAGETI = {
	"current": ("current", "current"),
	"radio": ("radio", "tv"),        # SUS lista radio, JOS lista TV (implicitul pana la 0.6.19)
	"tv_radio": ("tv", "radio"),
	"tv": ("tv", "tv"),
	"radio_radio": ("radio", "radio"),
	"zap": ("zap", "zap"),
	"zap_invers": ("zap_invers", "zap_invers"),
}
IMPLICIT = "current"


def ce_face(valoare, sus):
	"""Ce face sageata (sus=True: SUS, altfel JOS): "current", "radio", "tv", "zap" sau "zap_invers". O valoare
	necunoscuta (setari dintr-o versiune viitoare, fisier stricat) se poarta ca implicitul."""
	return SAGETI.get(valoare, SAGETI[IMPLICIT])[0 if sus else 1]


def sageata(sus):
	"""Ce face sageata acum, dupa config.usage.hds_sageata_sus."""
	try:
		from Components.config import config
		valoare = config.usage.hds_sageata_sus.value
	except Exception:
		valoare = IMPLICIT
	return ce_face(valoare, sus)
