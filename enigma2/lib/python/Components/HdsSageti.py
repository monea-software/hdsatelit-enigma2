# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSageti.py - ce fac sagetile SUS si JOS la privit (fara niciun meniu deschis), dupa setarea "Săgețile sus și jos la
# privit" (config.usage.hds_sageata_sus, Setari > Personalizare si /setari pe web).
#
# O singura regula pentru bara TV (Screens/InfoBarGenerics.py, InfoBarChannelSelection.switchChannelUp/Down) si pentru
# ecranul radio (Screens/HdsEcranRadio.py, listaSus/listaJos), ca cele doua sa nu se contrazica. Fiecare sageata face
# una din trei: "radio" (lista de canale radio), "tv" (lista de canale TV) sau "zap" (SUS canalul urmator, JOS cel
# anterior, ca CH+ si CH-). Valorile vechi ale setarii (0.1.6: "radio" si "tv") isi pastreaza intelesul.

# valoarea setarii -> (ce face SUS, ce face JOS)
SAGETI = {
	"radio": ("radio", "tv"),        # implicit: SUS lista radio, JOS lista TV (ca pana acum)
	"tv_radio": ("tv", "radio"),
	"tv": ("tv", "tv"),              # amandoua lista TV (0.1.6: "Lista de canale TV")
	"radio_radio": ("radio", "radio"),
	"zap": ("zap", "zap"),
}
IMPLICIT = "radio"


def ce_face(valoare, sus):
	"""Ce face sageata (sus=True: SUS, altfel JOS) cu valoarea data a setarii: "radio", "tv" sau "zap". O valoare
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
