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


def cursor_pe_canal():
	"""CUR6 (tamiciav7, LinuxSat 164122 #971593): lista deschisa cu SUS/JOS are cursorul pe canalul care merge, dupa
	config.usage.hds_sageata_cursor (Nu din fabrica: cursorul un rand mai sus sau mai jos, ca pana acum)."""
	try:
		from Components.config import config
		return bool(config.usage.hds_sageata_cursor.value)
	except Exception:
		return False


def sageata(sus):
	"""Ce face sageata acum, dupa config.usage.hds_sageata_sus."""
	try:
		from Components.config import config
		valoare = config.usage.hds_sageata_sus.value
	except Exception:
		valoare = IMPLICIT
	return ce_face(valoare, sus)


def stanga_dreapta_pe_flux(tasta, actiune, alegere, flux_in_direct, derulare_activa):
	"""LRI9 (Schpountz, DM920, 0.7.8): STANGA sau DREAPTA la privit pe un flux de internet in direct (IPTV 4097/5001/5002 din
	liste sau buchete). Harta derularii (InfobarSeekActions, KEY_LEFT/KEY_RIGHT = seekBack/seekFwd) e pornita pe orice serviciu
	derulabil, deci si pe fluxul in direct, si lua sagetile inaintea schimbarii canalului. Intoarce "zapUp" (STANGA) sau
	"zapDown" (DREAPTA) cand sagetile trebuie sa schimbe canalul ca pe satelit, altfel None (tasta merge mai departe ca pana
	acum). Numai cand: tasta are functia obisnuita (o actiune aleasa de om ramane a lui), setarea "Stanga si dreapta la privit"
	nu e "volum" (volumul are harta lui), fluxul e in direct si redat normal (filmele, arhiva, pauza si derularea pornita
	raman la derulare) si harta derularii e pornita (altfel InfobarChannelSelection schimba oricum canalul)."""
	if tasta not in ("left", "right") or actiune != "default" or alegere == "volum":
		return None
	if not flux_in_direct or not derulare_activa:
		return None
	return "zapUp" if tasta == "left" else "zapDown"
