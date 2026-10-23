# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTasteRapide.py: setarile ecranului "Butoane colorate si taste rapide" (Screens/ButtonSetup.py, HdsButtonSetup),
# aceleasi pe televizor si in interfata web (HdsWebControl/intrari_web.py, pagina /taste-rapide): cele patru butoane
# colorate (apasare lunga), cele opt actiuni de ales, config.hds_buttons.* si salvarea (Verde: save() pe fiecare
# buton). Mutate din ecran; ecranul le ia de aici.
#
# Intrarea din meniu are semnul "in lucru" (data/menu.xml, stare="in-lucru"): valorile se salveaza, dar InfoBar nu le
# foloseste inca (legarea apasarii lungi cere proba pe telecomanda fizica).
#
# Textele se traduc la incarcarea modulului, ca inainte in ecran (modulul se incarca dupa alegerea limbii). Nimic din
# enigma2 nu se importa la incarcare: config se ia la folosire.

ACTIUNI_DISPONIBILE = [
	("none", _("Nimic")),
	("epg", _("Ghid programe (EPG)")),
	("menu", _("Meniu principal")),
	("plugins", _("Lista de extensii")),
	("info", _("Informații sistem")),
	("audio", _("Selectare pistă audio")),
	("subtitle", _("Subtitrări")),
	("channellist", _("Lista de canale")),
]

BUTOANE = [
	("red", _("Roșu (apăsare lungă)")),
	("green", _("Verde (apăsare lungă)")),
	("yellow", _("Galben (apăsare lungă)")),
	("blue", _("Albastru (apăsare lungă)")),
]

VALORI_IMPLICITE = {"red": "channellist", "green": "audio", "yellow": "subtitle", "blue": "epg"}


def _config(config=None):
	if config is not None:
		return config
	from Components.config import config
	return config


def initConfigButtonSetup(config=None):
	# hasattr(config, ...) NU e sigur: ConfigSubsection.__getattr__ arunca KeyError (nu AttributeError) pentru o cheie
	# lipsa, iar hasattr() din Python 3 prinde doar AttributeError (explicatia completa in HdsWebControl/plugin.py).
	config = _config(config)
	if "hds_buttons" not in config.content.items:
		from Components.config import ConfigSubsection, ConfigSelection
		config.hds_buttons = ConfigSubsection()
		for cheie, _text in BUTOANE:
			setattr(config.hds_buttons, cheie,
				ConfigSelection(default=VALORI_IMPLICITE.get(cheie, "none"), choices=ACTIUNI_DISPONIBILE))
	return config.hds_buttons


def salveaza(config=None):
	"""Verde pe ecran: save() pe fiecare buton."""
	b = initConfigButtonSetup(config)
	for cheie, _text in BUTOANE:
		getattr(b, cheie).save()
