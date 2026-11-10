# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Alocarea tastelor barei. Lista si salvarea sunt comune cu pagina web.

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import config, configfile, getConfigListEntry
from Components.Sources.StaticText import StaticText
from Components import HdsTasteRapide


class HdsButtonSetup(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsButtonSetup" resolution="1920,1080"
		position="center,center" size="1200,790">
		<widget name="config" position="30,25" size="1140,546"
			scrollbarMode="showOnDemand" font="Regular;24"
			secondfont="Regular;20" itemHeight="42" />
		<widget source="ghid" render="Label" position="30,590"
			size="1140,110" font="Regular;22" />
		<widget source="key_red" render="Label" position="30,725"
			size="350,40" font="Regular;22" halign="center"
			valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="425,725"
			size="350,40" font="Regular;22" halign="center"
			valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="820,725"
			size="350,40" font="Regular;22" halign="center"
			valign="center" backgroundColor="#a08000" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [], session=session)
		self.setTitle(_("Butoane colorate și taste rapide"))
		HdsTasteRapide.actualizeaza_alegeri(config)
		HdsTasteRapide.initConfigProfil(config)
		self["ghid"] = StaticText(_(
			"Alege tasta cu SUS/JOS și funcția cu OK sau STÂNGA/DREAPTA. "
			"Funcția obișnuită păstrează comportamentul de acum. "
			"Cifrele lungi se alocă în afara timeshiftului."))
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText(_("Valori implicite"))
		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions"], {
				"ok": self.keyOK,
				"cancel": self.anuleaza,
				"red": self.anuleaza,
				"green": self.salveaza,
				"yellow": self.implicite,
			}, -2)
		self._initiale = [(element, element.value) for _text, element in self._randuri()]
		self.reface_lista()

	def _randuri(self):
		return [(text, getattr(config.usage, k)) for k, _v, text in HdsTasteRapide.PROFIL_SETARI] + [
			(text, getattr(config.hds_buttons, k)) for k, text in HdsTasteRapide.SCURTE + HdsTasteRapide.BUTOANE]

	def reface_lista(self):
		self.list = [getConfigListEntry(text, element) for text, element in self._randuri()]
		self["config"].list = self.list

	def keyOK(self):
		from Screens.ChoiceBox import ChoiceBox
		curent = self["config"].getCurrent()
		if curent is None:
			return
		text, element = curent[:2]
		if not hasattr(element, "choices"):
			return ConfigListScreen.keyOK(self)
		lista = [(element.description[v], v) for v in element.choices]
		pozitie = list(element.choices).index(element.value)

		def ales(raspuns):
			if raspuns is not None:
				element.value = raspuns[1]
				self["config"].invalidate(curent)

		# Fara cifre sau culori care ar alege din greseala o functie.
		self.session.openWithCallback(ales, ChoiceBox, title=text,
			list=lista, keys=[""] * len(lista), selection=pozitie)

	def implicite(self):
		for k, v in HdsTasteRapide.VALORI_IMPLICITE.items():
			getattr(config.hds_buttons, k).value = v
		for k, v, _text in HdsTasteRapide.PROFIL_SETARI:
			getattr(config.usage, k).value = v
		self.reface_lista()

	def salveaza(self):
		HdsTasteRapide.salveaza(config)
		for k, _v, _text in HdsTasteRapide.PROFIL_SETARI:
			getattr(config.usage, k).save()
		configfile.save()
		self.close(True)

	def anuleaza(self):
		for element, valoare in self._initiale:
			element.value = valoare
		self.close(False)
