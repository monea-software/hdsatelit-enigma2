# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsFundalPro: "Fundalul temei Pro" (Meniu > Interfata si aspect), fundalurile tematice puse peste tema Pro (TPR, Eduard
# 04.11 si 08.11). Lista: "Pro, cum e acum, fara fundal", temele din receptor, apoi cele de pe serverul nostru (citite pe un
# fir, cu previzualizare). Un singur pas: Sus / Jos alege, OK sau Verde pune fundalul; tema de pe server se descarca singura,
# apoi interfata reporneste singura (skinul se citeste numai la pornire). Rosu sau EXIT inchide. Logica, dosarele si
# descarcarea: Components/HdsFundalPro.py, aceeasi cu sectiunea "Fundalul temei Pro" de pe pagina web /tema-tv.
#
# Skinul: HdsFundalPro din skin.xml / skin_pro.xml daca exista; altfel rezerva de mai jos, pe 1280.

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components import HdsFundalPro as F
from Tools.ScaledSkin import scaledSkin

SKIN_REZERVA = """
<screen name="HdsFundalPro" position="48,27" size="1184,666" backgroundColor="#0D10162A" flags="wfNoBorder" title="Fundalul temei Pro">
	<eLabel position="0,0" size="1184,1" backgroundColor="#99FFFFFF" zPosition="1" />
	<widget source="Title" render="Label" position="21,12" size="1024,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget source="global.CurrentTime" render="Label" position="1056,12" size="107,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" zPosition="1">
		<convert type="ClockToText">Format:%H:%M</convert>
	</widget>
	<eLabel position="21,59" size="1141,1" backgroundColor="#D9FFFFFF" zPosition="1" />
	<widget name="lista" position="21,72" size="520,430" itemHeight="43" font="Regular;24" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" transparent="1" scrollbarMode="showOnDemand" zPosition="2" />
	<widget name="poza" position="562,72" size="600,338" alphatest="on" scale="1" zPosition="2" />
	<widget name="descriere" position="562,418" size="600,84" font="Regular;17" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" zPosition="1" />
	<widget name="nota" position="21,512" size="1141,40" font="Regular;17" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" zPosition="1" />
	<widget name="mesaj" position="21,556" size="1141,50" font="Regular;19" foregroundColor="#00F5B83D" backgroundColor="#0D10162A" transparent="1" zPosition="1" />
	<eLabel position="21,616" size="1141,1" backgroundColor="#D9FFFFFF" zPosition="1" />
	<eLabel position="21,629" size="4,21" backgroundColor="#00E5484D" zPosition="1" />
	<widget name="key_red" position="32,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="307,629" size="4,21" backgroundColor="#0046B06A" zPosition="1" />
	<widget name="key_green" position="317,624" size="269,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
</screen>"""


class HdsFundalPro(Screen):
	"""Fundalul temei Pro: Sus / Jos alege, OK sau Verde pune fundalul (descarcarea si repornirea singure)."""

	def __init__(self, session):
		self.skin = scaledSkin(SKIN_REZERVA)
		Screen.__init__(self, session)
		self.skinName = ["HdsFundalPro"]
		self.setTitle(_("Fundalul temei Pro"))
		self.randuri = []
		self["lista"] = MenuList([])
		self["poza"] = Pixmap()
		self["descriere"] = Label(_(F.TEXT_DESCRIERE))
		self["nota"] = Label("")
		self["mesaj"] = Label("")
		self["key_red"] = Label(_("Închide"))
		self["key_green"] = Label(_("Pune fundalul"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.alege,
			"green": self.alege,
			"cancel": self.close,
			"red": self.close,
			"up": self.sus,
			"down": self.jos,
			"left": self.paginaSus,
			"right": self.paginaJos,
		}, -1)
		from enigma import eTimer
		self.ceas = eTimer()
		try:
			self._legatura = self.ceas.timeout.connect(self.urmareste)
		except AttributeError:
			self.ceas.callback.append(self.urmareste)
		self.ultimaPoza = None
		self.onLayoutFinish.append(self.porneste)
		self.onClose.append(self.ceas.stop)

	def porneste(self):
		self.arata()
		F.citesteServer()
		self.ceas.start(500, False)

	def arata(self, pastreaza=None):
		teme, motiv, citeste = F.server()
		s = F.stare(server=teme, motiv=motiv, traducere=_)
		self.randuri = s["randuri"]
		ales = pastreaza if pastreaza is not None else s["ales"]
		elemente = []
		for r in self.randuri:
			text = r["nume"]
			if r["aleasa"]:
				text = "%s  (%s)" % (text, _("acum"))
			elif r["sursa"] == "server":
				text = "%s  (%s)" % (text, _("de pe server"))
			elemente.append(text)
		self["lista"].setList(elemente)
		for i, r in enumerate(self.randuri):
			if r["id"] == ales:
				self["lista"].moveToIndex(i)
				break
		nota = s["nota"]
		if citeste and not nota:
			nota = _("Se citesc fundalurile de pe server...")
		self["nota"].setText(nota)
		self.arataPoza()

	def rand(self):
		i = self["lista"].getSelectedIndex()
		return self.randuri[i] if 0 <= i < len(self.randuri) else None

	def arataPoza(self):
		r = self.rand()
		cale = r.get("previzualizare") if r else ""
		if cale == self.ultimaPoza:
			return
		self.ultimaPoza = cale
		w = self["poza"]
		if not cale or w.instance is None:
			w.hide()
			return
		try:
			from Tools.LoadPixmap import LoadPixmap
			p = LoadPixmap(cale)
			if p is not None:
				w.instance.setPixmap(p)
				w.show()
				return
		except Exception as e:
			print("[HdsFundalPro] previzualizarea: %s" % e)
		w.hide()

	def sus(self):
		self["lista"].up()
		self.arataPoza()

	def jos(self):
		self["lista"].down()
		self.arataPoza()

	def paginaSus(self):
		self["lista"].pageUp()
		self.arataPoza()

	def paginaJos(self):
		self["lista"].pageDown()
		self.arataPoza()

	def alege(self):
		r = self.rand()
		if r is None:
			return
		if F.stareLucru()["lucreaza"]:
			return
		if r["sursa"] == "server":
			self["mesaj"].setText(_("Se descarcă fundalul..."))
		else:
			self["mesaj"].setText(_("Se pune fundalul..."))
		if not F.porneste(r["id"], sesiune=self.session, traducere=_):
			self["mesaj"].setText("")
		self.lucru = r["id"]

	def urmareste(self):
		teme, _motiv, citeste = F.server()
		if not citeste and getattr(self, "_serverVazut", None) != len(teme):
			self._serverVazut = len(teme)
			r = self.rand()
			self.arata(pastreaza=r["id"] if r else None)
		l = F.stareLucru()
		if getattr(self, "lucru", None) is not None and not l["lucreaza"] and l["id"] == self.lucru:
			self.lucru = None
			self["mesaj"].setText(l["mesaj"])
			r = self.rand()
			self.arata(pastreaza=r["id"] if r else None)
