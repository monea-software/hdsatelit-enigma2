# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPornireMultipla.py: ecranul Porneste alte imagini. Meniu > Standby si repornire, numai pe Octagon SF8008 si
# SF8008 MINI (SystemInfo["HdsMultiboot"]).
#
# La deschidere ecranul cauta imaginile instalate in locurile din memorie (Components/HdsPornireMultipla.py: STARTUP_N
# de pe partitia bootoptions, nucleul si sistemul fiecarui loc) si le arata, cu imaginea pornita acum marcata; locurile
# goale nu apar. OK (sau VERDE) pe o imagine: o intrebare scurta, apoi STARTUP scris sigur si repornirea receptorului in
# ea. Daca la repornire receptorul intreaba (o inregistrare, o lucrare) si raspunzi Nu, STARTUP se pune la loc. ROSU
# inchide. Aceeasi lista si aceeasi alegere in web: cardul flash din /alimentare (HdsWebControl/alimentare_web.py).
# Skinul HDSatelit: forma ecranului HdsNavigatorFavorite (lista + nota, cadrul HdsCadru1240), aceleasi nume de widgeturi.

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Components import HdsPornireMultipla as P


class HdsPornireMultipla(Screen):
	skin = """
	<screen name="HdsPornireMultipla" resolution="1920,1080" position="center,center" size="1240,760" title="Pornește alte imagini">
		<widget name="lista" position="30,25" size="1180,480" itemHeight="56" font="Regular;30" scrollbarMode="showOnDemand" />
		<widget source="nota" render="Label" position="30,520" size="1180,170" font="Regular;24" halign="left" valign="top" />
		<widget source="key_red" render="Label" position="30,705" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="310,705" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = ["HdsPornireMultipla", "HdsNavigatorFavorite"]
		self.setTitle(_(P.TITLU))
		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText("")
		self["lista"] = MenuList([])
		self["nota"] = StaticText(_(P.CAUT))
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.alege,
			"green": self.alege,
			"cancel": self.close,
			"red": self.close,
		}, -2)
		self.stare = {"locuri": []}
		self["lista"].onSelectionChanged.append(self.butoane)
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.citeste)
		self.onClose.append(self.ceas.stop)
		self.ceas.start(50, True)

	def citeste(self):
		try:
			self.stare = P.locuri()
		except Exception as e:
			print("[HdsPornireMultipla] %r" % (e,))
			self.stare = {"locuri": [], "eroare": True}
		self["lista"].setList([(text, l) for text, l in zip(P.randuri(self.stare), self.stare["locuri"])])
		self["nota"].setText(P.nota(self.stare))
		self.butoane()

	def _ales(self):
		rand = self["lista"].getCurrent()
		return rand[1] if rand else None

	def butoane(self):
		l = self._ales()
		self["key_green"].setText(_(P.BUTON) if l and l.get("alegere") else "")

	def alege(self):
		from Screens.MessageBox import MessageBox
		l = self._ales()
		if not l:
			return
		if l.get("acum"):
			self.session.open(MessageBox, _(P.DEJA), MessageBox.TYPE_INFO, timeout=5)
			return
		if l["fel"] != "emmc":
			self.session.open(MessageBox, _(P.PE_STICK), MessageBox.TYPE_INFO, timeout=8)
			return
		if not l.get("alegere"):
			self.session.open(MessageBox, _(P.REFUZ) % l["loc"], MessageBox.TYPE_ERROR, timeout=10)
			return
		self.session.openWithCallback(lambda da, loc=l["loc"]: self.confirmat(da, loc), MessageBox,
			_(P.INTREBARE) % l["imagine"], MessageBox.TYPE_YESNO, default=True)

	def confirmat(self, da, loc):
		if not da:
			return
		ok, text = P.reporneste(self.session, loc)
		if not ok:
			from Screens.MessageBox import MessageBox
			self.session.open(MessageBox, text, MessageBox.TYPE_ERROR, timeout=10)
			self.citeste()
