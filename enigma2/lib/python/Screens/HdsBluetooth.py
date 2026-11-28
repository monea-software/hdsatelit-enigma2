# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Bluetooth remote pairing without stopping the current channel."""
from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.HdsBluetooth import manager
from Components.HdsBluetoothSunet import sunet, poate
from enigma import eTimer


class HdsBluetooth(Screen):
	skin = """<screen resolution="1920,1080" position="center,center" size="1000,600" title="Bluetooth">
		<widget name="nota" position="25,20" size="950,90" font="Regular;24" />
		<widget name="lista" position="25,120" size="950,240" />
		<widget name="sunet" position="25,365" size="950,90" font="Regular;22" />
		<widget name="stare" position="25,458" size="950,85" font="Regular;22" />
		<widget name="taste" position="25,550" size="950,35" font="Regular;23" />
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Telecomandă Bluetooth"))
		self["nota"] = Label(_("Pune telecomanda în modul de asociere, apoi apasă GALBEN. Telecomanda cu infraroșu funcționează în continuare."))
		self["lista"] = MenuList([])
		self["stare"] = Label("")
		# the film and IPTV sound in a headset: one row, only where an adapter exists (Components/HdsBluetoothSunet.py)
		self["sunet"] = Label("")
		self.ultimSunet = None
		self.managerOcupat = False
		self.areAdaptor = False
		self["taste"] = Label(_("ROȘU: închide   GALBEN: caută   OK: asociază"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"cancel": self.close, "red": self.close, "yellow": self.cauta, "ok": self.asociaza,
			"green": self.asociaza, "blue": self.schimbaSunetul,
			"left": self.intarziereMinus, "right": self.intarziereaPlus}, -2)
		self.timer = eTimer()
		self.timer.callback.append(self.actualizeaza)
		self.timer.callback.append(self.actualizeazaSunetul)
		self.onClose.append(self.timer.stop)
		self.last = None
		self.onFirstExecBegin.append(self.incepe)

	def incepe(self):
		manager.porneste("citeste")
		self.areAdaptor = poate()
		if self.areAdaptor:
			sunet.porneste()
			sunet.citeste()
		self.actualizeaza()
		self.timer.start(500)

	def _intarziere(self, pas):
		if self.areAdaptor:
			from Components.HdsBluetoothSunet import INTARZIERE_PAS
			sunet.intarziere(sunet.stare().get("intarziere", 0) + pas * INTARZIERE_PAS)
			self.actualizeazaSunetul()

	def intarziereMinus(self):
		self._intarziere(-1)

	def intarziereaPlus(self):
		self._intarziere(1)

	def schimbaSunetul(self):
		if self.areAdaptor:
			sunet.alege(sunet.urmatorul())
			self.actualizeazaSunetul()

	def cauta(self):
		manager.porneste("cauta")
		self.actualizeaza()

	def asociaza(self):
		cur = self["lista"].getCurrent()
		if cur:
			manager.porneste("asociaza", cur[1])
			self.actualizeaza()

	def actualizeaza(self):
		s = manager.stare()
		rows = [(r["nume"] + " - " + (_("legătură Bluetooth activă") if r["conectata"] else _("asociată") if r["asociata"] else _("nouă")), r["id"]) for r in s["dispozitive"]]
		if rows != self.last:
			from Components.HdsCursorLista import pune_randurile
			pune_randurile(self["lista"], rows, cheie=1)
			self.last = rows
		self["stare"].setText(s["message"])

	def actualizeazaSunetul(self):
		if not self.areAdaptor:
			return
		ocupat = manager.stare()["ocupat"]
		# a search for remotes also finds the headsets: they are read again when it ends
		if self.managerOcupat and not ocupat:
			sunet.citeste()
		self.managerOcupat = ocupat
		s = sunet.stare()
		text = sunet.eticheta() + "   " + _("ALBASTRU: schimbă") + "\n" + \
			_("Întârzierea sunetului în cască: %d ms   STÂNGA/DREAPTA: schimbă") % s.get("intarziere", 0) + "\n" + s["message"]
		if text != self.ultimSunet:
			self["sunet"].setText(text)
			self.ultimSunet = text
