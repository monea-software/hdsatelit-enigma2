# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# meniu_pagini_web.py: paginile web ale intrarilor de meniu care, pana in 0.3.4, se deschideau numai pe televizor
# (semnul "TV" din meniul web). Regula: fiecare ecran sau setare de pe receptor are pereche in interfata web, cu
# aceleasi setari si actiuni. Adunate intr-un singur loc, ca aspect_web.py sa le lege cu un singur nume din
# lista lui MODULE (plugin.py nu se schimba):
#   alimentare_web       /alimentare            Meniu > Alimentare & Repornire (somn, standby, repornire, oprire)
#   resetare_web         /resetare-fabrica      Meniu > Setari > Sistem & Dispozitive > Resetare la valorile din fabrica
#                        /curatenie             ... > Curatenia discului (CleanupWizard)
#   parental_web         /control-parental      ... > Control parental (ParentalControlSetup)
#   disc_web             /locuri-inregistrari   Meniu > Setari > Inregistrari & Stocare > Locurile inregistrarilor
#                        /discuri               ... > Formatarea si verificarea discului (HarddiskSetup)
#                        /swap                  ... > Fisier de swap (SwapManager)
#   jurnale_sistem_web   /jurnale-sistem        Meniu > Setari > Sistem & Dispozitive > Jurnalele sistemului (LogManager)
#                        /jurnale-cadere        ... > Jurnalele de cadere (HdsCrashlogAutoSubmit)
#   canal_info_web       /informatii-canal      Meniu > Informatii despre sistem > Informatii despre canal (ServiceInfo)
#   retea_web            /retea, /dns           Meniu > Setari > Retea & Internet (NetworkSetup)
#   unelte_retea_web     /wifi-canale,          ... > Cat de aglomerat e Wi-Fi-ul, Ce aparate sunt in retea
#                        /aparate-retea         (HdsUnelteRetea), plus starea trecerii pe alta retea (0.4.4)
#   internet_web         /dvb-i, /mabr, /iptv,  Meniu > Setari > Surse Internet (HdsDvbI, HdsDvbMABR, IptvSetup,
#                        /interfata-web         HdsWebControlSetup)
#   intrari_web          /dispozitive-intrare,  Meniu > Setari > Sistem & Dispozitive (InputDeviceSetup, ButtonSetup) si
#                        /taste-rapide, /skin   Interfata & Aspect > Aspectul ecranelor (SkinSelector)
#   media_web            /player, /poze         Meniu > Media (MediaPlayer, PicturePlayer)
#   extensii_web         /extensii              Meniu > Extensii & Aplicatii (HdsExtensii)
#   diseqc_web           /proba-diseqc          Meniu > Orientarea si setarea antenei > Proba DiSEqC (DiseqcTester)
#   vpn_web              /vpn                   Meniu > Setari > Retea & Internet > VPN (HdsVpn)
#
# Fiecare modul are rute(baza, resource) -> ({nume: resursa /api}, {nume: resursa pagina}), ca modulele din
# aspect_web.MODULE. Un modul care nu se poate incarca nu strica restul: se scrie in jurnal si paginile lui lipsesc.

MODULE = ("alimentare_web", "resetare_web", "parental_web", "disc_web", "jurnale_sistem_web", "canal_info_web",
	"retea_web", "unelte_retea_web", "internet_web", "intrari_web", "media_web", "extensii_web", "diseqc_web", "vpn_web",
	"asistenta_web")


def _modul(nume):
	if "." in __name__:
		return __import__(__name__.rsplit(".", 1)[0] + "." + nume, fromlist=[nume])
	return __import__(nume)


def rute(baza, resource):
	api, pagini = {}, {}
	for nume in MODULE:
		try:
			a, p = _modul(nume).rute(baza, resource)
		except Exception as eroare:
			print("[HdsWebControl] %s nu s-a incarcat: %r" % (nume, eroare))
			continue
		for k in a:
			if k in api:
				print("[HdsWebControl] %s: ruta /api/%s e deja a altui modul" % (nume, k.decode("ascii", "replace")))
		api.update(a)
		pagini.update(p)
	return api, pagini
