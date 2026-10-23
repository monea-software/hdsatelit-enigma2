# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ButtonSetup.py — Personalizare butoane colorate si taste rapide telecomanda.
# Cod 100% propriu, scris de la zero. NICIO linie copiata din alta distributie.
#
# STARE:
# Facut: ecranul salveaza in configuratie ce vrea utilizatorul sa
# faca fiecare buton colorat la apasare LUNGA in InfoBar (vizionare live).
# Nefacut inca: legarea reala in InfoBar (detectarea apasarii lungi
# si declansarea actiunii alese) — necesita un mecanism de timer pe apasare/
# ridicare tasta in InfoBarGenerics.py, testat cu o telecomanda IR reala (pe
# tastatura de PC din emulator apasarea lunga nu se comporta la fel ca pe o
# telecomanda IR, deci nu poate fi validata corect aici). Pana atunci, valorile
# salvate aici NU au niciun efect vizibil, doar sunt pastrate, gata de folosit
# cand se face legarea in InfoBar; intrarea din meniu are stare="in-lucru".

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import config, getConfigListEntry
from Components.Sources.StaticText import StaticText
# actiunile, butoanele, setarile si salvarea sunt comune cu interfata web (/taste-rapide): Components/HdsTasteRapide.py
from Components.HdsTasteRapide import ACTIUNI_DISPONIBILE, BUTOANE, initConfigButtonSetup
from Components import HdsTasteRapide


class HdsButtonSetup(Screen, ConfigListScreen):
	# HDSatelit (gasit printr-un grep pe `<screen name="..."` din skin.xml):
	# clasa se numea `ButtonSetup`, nume
	# care COLIDA cu `<screen name="ButtonSetup">` deja existent in skin.xml (widget-uri "list"/"choosen",
	# un chooser cu doua coloane -- nimic din ce foloseste codul propriu, "config"/"ghid"/"key_red"/
	# "key_green"). Redenumit `Hds...`, acelasi tipar ca HdsSoftwareUpdate/TempFanControl/HdsLogManager.
	skin = """
	<screen name="HdsButtonSetup" resolution="1920,1080" position="center,center" size="900,420" title="Butoane colorate și taste rapide">
		<widget name="config" position="30,30" size="840,200" scrollbarMode="showOnDemand" font="Regular;24" secondfont="Regular;16" itemHeight="42" />
		<widget source="ghid" render="Label" position="30,250" size="840,110" font="Regular;20" />
		<widget source="key_red" render="Label" position="30,360" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="310,360" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [], session=session)
		self.setTitle(_("Butoane colorate și taste rapide"))
		initConfigButtonSetup()

		# intrarea din meniu poarta semnul "in lucru" (data/menu.xml), deci aici nu se mai explica stadiul
		self["ghid"] = StaticText(_("Alege ce se deschide la apăsarea LUNGĂ a fiecărui buton colorat, cât te uiți la TV."))
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))

		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions"],
			{
				"cancel": self.anuleaza,
				"red": self.anuleaza,
				"green": self.salveaza,
			}, -2)

		self._initiale = {cheie: getattr(config.hds_buttons, cheie).value for cheie, _t in BUTOANE}
		self.list = [getConfigListEntry(text, getattr(config.hds_buttons, cheie)) for cheie, text in BUTOANE]
		self["config"].list = self.list

	def salveaza(self):
		HdsTasteRapide.salveaza(config)
		self.close(True)

	def anuleaza(self):
		for cheie, valoare in self._initiale.items():
			getattr(config.hds_buttons, cheie).value = valoare
		self.close(False)
