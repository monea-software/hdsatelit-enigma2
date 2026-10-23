# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTemaTv: tema interfetei de pe televizor, Clasic sau Pro. Logica comuna a ecranului "Tema interfeței" (Meniu >
# Interfata si aspect, Screens/HdsTemaInterfata.py) si a paginii web /tema-tv (HdsWebControl/tema_tv_web.py).
#
# - Setarea: config.skin.tema_tv ("clasic" / "pro"), facuta in skin.py (se citeste la pornire, inainte de ecrane).
# - Tema Pro = ecranele din /usr/share/enigma2/HDSatelit/skin_pro.xml (pachetul skinului) incarcate peste cele cu
#   acelasi nume din skin.xml; culorile raman ale paletei alese in Setari skin. Fara fisier, tema Pro nu se poate alege.
# - Schimbarea se aplica la repornirea interfetei (TryQuitMainloop 3, calea sigura din meniu): skinul se citeste o
#   singura data, la pornire. Setarile nu se pierd (se scriu in /etc/enigma2/settings inainte de repornire).
# - E separata de tema interfetei web (config.plugins.hdswebcontrol.tema_web, cookie-ul browserului): nimic de aici nu
#   o citeste si nu o scrie.
# - Tema e o varianta a skinului HDSatelit (skin_pro.xml sta langa skin.xml-ul lui): se alege numai cand skinul ales
#   (config.skin.primary_skin, Components/HdsSkinuri.py) e HDSatelit; cu alt skin ales, skin.py nu incarca skin_pro.xml,
#   iar ecranul si pagina spun de ce nu se poate alege.
#
# Modulul nu importa nimic din enigma2 la incarcare (probele de pe PC dau config si caile).

import os

TEME = ("clasic", "pro")
IMPLICITA = "clasic"
DOSAR_SKIN = "/usr/share/enigma2/HDSatelit"
FISIER_PRO = "skin_pro.xml"
# previzualizarile din pachetul skinului (capturi din emulator, 640x360, paleta implicita)
POZE = {"clasic": "tema/clasic.jpg", "pro": "tema/pro.jpg"}


def N_(text):
	return text


# numele si descrierile, traduse la afisare (in romana in cod, ca restul ecranelor Hds)
NUME = {"clasic": N_("Clasic"), "pro": N_("Pro")}
ETICHETA = {"clasic": N_("Aerisit"), "pro": N_("Dens")}
SCURT = {
	"clasic": N_("Aspect aerisit, ca până acum"),
	"pro": N_("Mai multe informații pe ecran"),
}
DESCRIERE = {
	"clasic": N_("Rânduri mari și puține lucruri pe ecran; meniurile lasă imaginea televizorului să se vadă în dreapta."),
	"pro": N_("Panouri cu informații tehnice (semnal, emisiune, receptor), litere mai mici, bara de sus cu ceasul și data, legenda tastelor jos."),
}


# textele scrise in HDSatelit/skin_pro.xml (text="..."), traduse de skin.py prin _(): marcate aici ca sa ajunga in po/
# (xgettext nu citeste skinul). Lista o da unealta skinului (fa_skin_pro.py --texte); proba
# test_skin_pro_tv.py cere ca fiecare text din skin_pro.xml sa fie aici.
TEXTE_SKIN_PRO = (
	N_("Înregistrează"),
	N_("Sunet"),
	N_("Extensii"),
	N_("Ghid TV"),
	N_("Închide"),
	N_("Volum"),
	N_("Despre această setare"),
)


def _t(traducere, text):
	if traducere is None:
		return text
	try:
		return traducere(text)
	except Exception:
		return text


def _config(config=None):
	if config is not None:
		return config
	from Components.config import config as c
	return c


SKIN_IMAGINE = "HDSatelit/skin.xml"


def skinAles(config=None):
	"""Valoarea skinului ales (config.skin.primary_skin), "HDSatelit/skin.xml" cand nu se poate citi."""
	try:
		return _config(config).skin.primary_skin.value or SKIN_IMAGINE
	except Exception:
		return SKIN_IMAGINE


def skinImaginii(config=None):
	"""True cand skinul ales e HDSatelit (singurul cu teme)."""
	v = skinAles(config)
	return v in (SKIN_IMAGINE, "skin.xml") or not v.endswith("/skin.xml")


TEXT_ALT_SKIN = N_("Tema se alege numai cu skinul HD Satelit; acum e ales skinul %s. Alege mai întâi skinul "
	"HDSatelit.")


def textAltSkin(config=None, traducere=None):
	v = skinAles(config)
	return _t(traducere, TEXT_ALT_SKIN) % v[:-len("/skin.xml")]


def caleFisierPro(dosar=None):
	return os.path.join(dosar or DOSAR_SKIN, FISIER_PRO)


def proDisponibil(dosar=None, exista=None):
	"""True cand pachetul skinului are ecranele Pro (skin_pro.xml)."""
	exista = exista or os.path.isfile
	try:
		return bool(exista(caleFisierPro(dosar)))
	except Exception:
		return False


def aleasa(config=None):
	"""Tema aleasa (cea de la urmatoarea pornire a interfetei)."""
	try:
		v = _config(config).skin.tema_tv.value
	except Exception:
		return IMPLICITA
	return v if v in TEME else IMPLICITA


def activa(dom_skins=None):
	"""Tema cu care a pornit interfata acum: "pro" daca skin.py a incarcat skin_pro.xml (radacina lui are
	hds-tema="pro"; caile nu ajung, skin.xml si skin_pro.xml stau in acelasi dosar), altfel "clasic"."""
	if dom_skins is None:
		try:
			import skin
			dom_skins = skin.dom_skins
		except Exception:
			return IMPLICITA
	for _cale, radacina in dom_skins:
		try:
			if radacina.get("hds-tema") == "pro":
				return "pro"
		except Exception:
			pass
	return "clasic"


def seteaza(tema, config=None, configfile=None, dosar=None, exista=None, traducere=None, dom_skins=None):
	"""Alege tema. (bun, mesaj, schimbata): schimbata = tema aleasa difera acum de cea cu care a pornit interfata."""
	if tema not in TEME:
		return False, _t(traducere, "Tema necunoscută."), False
	if not skinImaginii(config):
		return False, textAltSkin(config, traducere), False
	if tema == "pro" and not proDisponibil(dosar, exista):
		return False, _t(traducere, "Tema Pro lipsește din skinul instalat. Actualizează skinul HDSatelit."), False
	c = _config(config)
	try:
		c.skin.tema_tv.value = tema
		c.skin.tema_tv.save()
		if configfile is None:
			from Components.config import configfile as cf
			configfile = cf
		configfile.save()
	except Exception as eroare:
		return False, _t(traducere, "Setarea nu se poate salva acum.") + " (%s)" % eroare, False
	return True, _t(traducere, "Tema interfeței de pe televizor: %s.") % _t(traducere, NUME[tema]), tema != activa(dom_skins)


def stare(config=None, dosar=None, exista=None, traducere=None, dom_skins=None):
	"""Ce arata ecranul si pagina web: temele, alegerea, tema de acum, daca trebuie repornita interfata."""
	ales = aleasa(config)
	acum = activa(dom_skins)
	pro = proDisponibil(dosar, exista)
	teme = []
	for t in TEME:
		teme.append({
			"id": t,
			"nume": _t(traducere, NUME[t]),
			"eticheta": _t(traducere, ETICHETA[t]),
			"scurt": _t(traducere, SCURT[t]),
			"descriere": _t(traducere, DESCRIERE[t]),
			"aleasa": t == ales,
			"activa": t == acum,
			"disponibila": t != "pro" or pro,
		})
	imaginii = skinImaginii(config)
	return {"aleasa": ales, "activa": acum, "pro_disponibil": pro, "repornire": imaginii and ales != acum, "teme": teme,
		"skin_imaginii": imaginii, "nota_skin": "" if imaginii else textAltSkin(config, traducere)}


def cale_poza(tema, dosar=None):
	"""Calea previzualizarii unei teme (None pentru o tema necunoscuta)."""
	if tema not in POZE:
		return None
	return os.path.join(dosar or DOSAR_SKIN, POZE[tema])
