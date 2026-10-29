# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsJurnaleSloturi.py: ecranul „Jurnalele celorlalte sloturi”. Meniu > Sistem & Dispozitive, langa jurnalele de cadere.
#
# Cand o imagine dintr-un alt slot nu porneste, pasii pornirilor ei, rapoartele si jurnalele de cadere raman acolo. La
# deschidere ecranul cauta sloturile (Components/HdsJurnaleSloturi.py, prin tools/hds-raport.sh) si arata ce a gasit;
# VERDE (sau OK) le pune pe stick si le trimite, intr-un singur raport, fara nicio alegere, si arata codul raportului
# mare. ROSU inchide. Aceeasi pagina
# in interfata web: /jurnale-sloturi (HdsWebControl/sloturi_web.py). Skinul HDSatelit are blocul lui
# (<screen name="HdsJurnaleSloturi">, cadrul comun HdsCadru1240); cel de aici e pentru celelalte skinuri.

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components import HdsJurnaleSloturi as J


class HdsJurnaleSloturi(Screen):
	skin = """
	<screen name="HdsJurnaleSloturi" resolution="1920,1080" position="center,center" size="1240,760" title="Jurnalele celorlalte sloturi">
		<widget source="descriere" render="Label" position="30,25" size="1180,110" font="Regular;24" halign="left" valign="top" />
		<widget source="eticheta_sloturi" render="Label" position="30,140" size="1180,30" font="Regular;20" halign="left" valign="center" />
		<widget source="sloturi" render="Label" position="30,175" size="1180,300" font="Regular;24" halign="left" valign="top" />
		<widget source="rezultat" render="Label" position="30,495" size="840,190" font="Regular;26" halign="left" valign="top" />
		<widget source="eticheta_cod" render="Label" position="890,495" size="320,30" font="Regular;20" halign="right" valign="center" />
		<widget source="cod" render="Label" position="890,530" size="320,80" font="Regular;64" halign="right" valign="center" foregroundColor="#f1c40f" />
		<widget source="key_red" render="Label" position="30,705" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="310,705" size="420,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_(J.TITLU))
		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText("")
		self["descriere"] = StaticText(_(J.DESCRIERE))
		self["sloturi"] = StaticText(_(J.CAUT))
		self["rezultat"] = StaticText("")
		self["eticheta_sloturi"] = StaticText(_(J.ETICHETA_SLOTURI))
		self["eticheta_cod"] = StaticText("")
		self["cod"] = StaticText("")
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.pune,
			"green": self.pune,
			"cancel": self.close,
			"red": self.close,
		}, -2)
		self.lucrare = J.lucrare()
		self.asteapta = ""
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.actualizeaza)
		self.onClose.append(self.ceas.stop)
		if self.lucrare.porneste("cauta"):
			self.asteapta = "cauta"
		self.ceas.start(500, False)

	def pune(self):
		s = self.lucrare.stare()
		if s["merge"] or not s["sloturi"]:
			return
		if self.lucrare.porneste("pune"):
			self.asteapta = "pune"
			self["key_green"].setText("")
			self["rezultat"].setText(_(J.LUCREZ))

	def actualizeaza(self):
		s = self.lucrare.stare()
		if s["merge"]:
			if s["fel"] == "pune":
				self["rezultat"].setText(_(J.LUCREZ))
			return
		if s["sloturi"] is not None or s["fel"] == "cauta":
			self["sloturi"].setText(J.textSloturi(s["sloturi"]))
		if self.asteapta == "pune" and s["fel"] == "pune":
			self["rezultat"].setText(J.textRezultat(s["rezultat"]))
			cod = J.codRezultat(s["rezultat"])
			self["cod"].setText(cod)
			self["eticheta_cod"].setText(_(J.ETICHETA_COD) if cod else "")
		self.asteapta = ""
		self["key_green"].setText(_(J.BUTON) if s["sloturi"] else "")
