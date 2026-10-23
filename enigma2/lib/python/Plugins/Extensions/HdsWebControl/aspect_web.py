# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# aspect_web.py: paginile web ale ecranelor de aspect si de informatii, adunate intr-un singur loc, ca plugin.py sa le
# lege cu doua bucle (rutele de sub /api si paginile de la radacina):
#   marime_text_web     /marime-text        Meniu > Interfata si aspect > Marimea textului (Screens/FontSetup.py)
#   margini_web         /margini-ecran      Meniu > Interfata si aspect > Marginile ecranului (Screens/OSDCalibration.py)
#   font_interfata_web  /font-interfata     Meniu > Interfata si aspect > Fontul interfetei (Screens/HdsFontInterfata.py)
#   culori_web          /culori-skin        Setari skin > Culori pe roluri (pluginul skinului, HdsSkinSetari)
#   informatii_tabel_web /informatii        Informatii despre sistem ca tabele (inlocuieste ruta din informatii_web.py)
#   tema_tv_web         /tema-tv            Meniu > Interfata si aspect > Tema interfetei (Clasic / Pro, numai pe TV;
#                                           Screens/HdsTemaInterfata.py)
#   meniu_pagini_web    paginile intrarilor de meniu care se deschideau numai pe televizor (alimentarea, discurile,
#                                           jurnalele, reteaua, media, extensiile si celelalte; lista in modulul lui)
#   playlisturi_web     /playlisturi        listele de canale gata facute pentru playerele din casa (numai in web;
#                                           butonul din /canale)
#
# Fiecare modul are rute(baza, resource) -> ({nume: resursa /api}, {nume: resursa pagina}). Un modul care nu se poate
# incarca nu strica restul: se scrie in jurnal si paginile lui lipsesc.

MODULE = ("marime_text_web", "margini_web", "font_interfata_web", "culori_web", "informatii_tabel_web", "tema_tv_web",
	"meniu_pagini_web", "playlisturi_web")


def rute(baza, resource):
	api, pagini = {}, {}
	for nume in MODULE:
		try:
			modul = __import__(__name__.rsplit(".", 1)[0] + "." + nume, fromlist=[nume]) if "." in __name__ else __import__(nume)
			a, p = modul.rute(baza, resource)
		except Exception as eroare:
			print("[HdsWebControl] %s nu s-a incarcat: %r" % (nume, eroare))
			continue
		api.update(a)
		pagini.update(p)
	return api, pagini
