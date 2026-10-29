# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsTasteRapide.py: setarile ecranului "Butoane colorate si taste rapide" (Screens/ButtonSetup.py, HdsButtonSetup),
# aceleasi pe televizor si in interfata web (HdsWebControl/intrari_web.py, pagina /taste-rapide): cele patru butoane
# colorate (apasare lunga), VERDE apasat scurt, cele noua actiuni de ales, config.hds_buttons.* si salvarea (Verde:
# save() pe fiecare rand). Mutate din ecran; ecranul le ia de aici.
#
# VERDE apasat scurt in bara (Screens/InfoBar.py, InfoBar.subserviceSelection, harta InfobarSubserviceSelectionActions
# din data/keymap.xml, la eliberare): pe un canal cu subcanale lista lor, ca inainte; altfel actiunea din
# config.hds_buttons.green_short, implicit pagina de pluginuri (PluginBrowser), cum face VERDE si in alte imagini.
# Inainte VERDE scurt nu facea nimic pe un canal fara subcanale. Aceleasi actiuni de ales ca la apasarea lunga.
#
# Apasarea lunga in bara (Screens/InfoBar.py, harta HdsTasteColorateActions din data/keymap.xml): ApasareLunga de mai
# jos, cu aceeasi logica de trei pasi ca POWER (mytest.py, PowerKey), AUDIO si FAV: apasarea sterge semnul si lasa
# tasta mai departe (apasarea scurta ramane cum era, fara intarziere), apasarea lunga (flagLong, la a patra repetare,
# main/enigma.cpp) face actiunea aleasa si pune semnul, eliberarea cu semn e oprita (nu mai face si actiunea scurta).
#
# cauta_meniu: un <menu> din data/menu.xml dupa <id val="...">, cautat in tot arborele (radacina e <menuxml>, cu un
# singur copil, meniul principal); folosit de POWER lung (meniul "shutdown") si de actiunea "info" ("information").
#
# Textele se traduc la incarcarea modulului, ca inainte in ecran (modulul se incarca dupa alegerea limbii). Nimic din
# enigma2 nu se importa la incarcare: config se ia la folosire.

ACTIUNI_DISPONIBILE = [
	("none", _("Nimic")),
	("epg", _("Ghid programe (EPG)")),
	("menu", _("Meniu principal")),
	("plugins", _("Plugins & Applications")),    # numele din meniul principal: Extensii si aplicatii (PluginBrowser)
	("info", _("Informații sistem")),
	("audio", _("Selectare pistă audio")),
	("subtitle", _("Subtitrări")),
	("channellist", _("Lista de canale")),
	# captura ecranului (Components/HdsCapturi.py), pentru telecomenzile fara tasta de captura
	("captura", _("Captură de ecran")),
]

BUTOANE = [
	("red", _("Roșu (apăsare lungă)")),
	("green", _("Verde (apăsare lungă)")),
	("yellow", _("Galben (apăsare lungă)")),
	("blue", _("Albastru (apăsare lungă)")),
]

# apasarea scurta: numai VERDE (celelalte culori au in bara actiunile lor obisnuite)
SCURTE = [
	("green_short", _("Verde (apăsare scurtă)")),
]

VALORI_IMPLICITE = {"red": "channellist", "green": "audio", "yellow": "subtitle", "blue": "epg", "green_short": "plugins"}


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
		for cheie, _text in BUTOANE + SCURTE:
			setattr(config.hds_buttons, cheie,
				ConfigSelection(default=VALORI_IMPLICITE.get(cheie, "none"), choices=ACTIUNI_DISPONIBILE))
	return config.hds_buttons


def salveaza(config=None):
	"""Verde pe ecran: save() pe fiecare rand (apasarea lunga a celor patru butoane si VERDE scurt)."""
	b = initConfigButtonSetup(config)
	for cheie, _text in BUTOANE + SCURTE:
		getattr(b, cheie).save()


def actiune_aleasa(buton, config=None):
	"""Actiunea salvata pentru apasarea lunga a butonului ("red", "green", "yellow", "blue") sau pentru VERDE apasat
	scurt ("green_short"); "none" pentru un buton necunoscut."""
	if buton not in dict(BUTOANE + SCURTE):
		return "none"
	return getattr(initConfigButtonSetup(config), buton).value


def cauta_meniu(radacina, id_meniu):
	"""Primul <menu> din tot arborele lui menu.xml (radacina = mdom.getroot()) care are copilul <id val="id_meniu"/>,
	sau None. Nu numai copiii directi ai radacinii: in menu.xml radacina e <menuxml> si toate meniile sunt in meniul
	principal (de aceea POWER lung nu gasea meniul "shutdown" si nu deschidea nimic)."""
	if radacina is None:
		return None
	for meniu in radacina.iter("menu"):
		ident = meniu.find("id")
		if ident is not None and ident.get("val") == id_meniu:
			return meniu
	return None


class ApasareLunga(object):
	"""Apasarea lunga a celor patru butoane colorate, pentru o harta cu trei actiuni pe buton (apasat "m", lung "l",
	eliberat "b"). porneste(buton, actiune) face actiunea si intoarce True; False cand butonul nu e al barei acum
	(aplicatia HbbTV a luat ROSU, ecranul radio ia tastele colorate): atunci totul merge ca pana acum.
	Rezultatele sunt cele ale hartilor (Components/ActionMap.py): 0 = tasta merge mai departe, 1 = oprita aici."""

	def __init__(self, porneste, config=None):
		self.porneste = porneste
		self.config = config
		self.semne = set()

	def apasat(self, buton):
		self.semne.discard(buton)
		return 0

	def lung(self, buton):
		try:
			actiune = actiune_aleasa(buton, self.config)
		except Exception as e:
			print("[HdsTasteRapide] %s lung: setarea nu se poate citi: %s" % (buton, e))
			return 0
		if actiune == "none" or not self.porneste(buton, actiune):
			return 0
		self.semne.add(buton)
		return 1

	def eliberat(self, buton):
		if buton in self.semne:
			self.semne.discard(buton)
			return 1
		return 0
