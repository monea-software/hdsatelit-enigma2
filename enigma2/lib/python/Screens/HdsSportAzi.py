# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ecranul Sport azi (MENU > Sport azi): meciurile, cursele si galele de azi din ghid, cu ora si canalul. OK pe o emisiune
care a inceput = canalul pe televizor; pe una care incepe mai tarziu = informatiile ei (Verde = Inregistreaza, TEXT =
Despre film). Galben = numai cele in direct. Logica: Components/HdsSportAzi.py; pagina web: /sport-azi."""
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Screens.Screen import Screen
from Components import HdsSportAzi as S


class HdsSportAzi(Screen):
	skin = """
	<screen name="HdsSportAzi" resolution="1920,1080" position="center,center" size="1500,860" title="Sport azi">
		<widget name="lista" position="30,30" size="1440,660" font="Regular;30" itemHeight="55" scrollbarMode="showOnDemand" />
		<widget name="detalii" position="30,700" size="1440,80" font="Regular;24" foregroundColor="#b0b8c8" />
		<widget name="key_red" position="30,794" size="300,46" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" />
		<widget name="key_yellow" position="350,794" size="360,46" font="Regular;24" halign="center" valign="center" backgroundColor="#a08500" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Sport azi"))
		self._randuri = []
		self._numaiDirect = False
		self["lista"] = MenuList([])
		self["detalii"] = Label("")
		self["key_red"] = Label(_("Înapoi"))
		self["key_yellow"] = Label(_("Numai în direct"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close,
			"red": self.close,
			"ok": self._ok,
			"yellow": self._comutaDirect,
		}, -1)
		self["lista"].onSelectionChanged.append(self._detalii)
		self.onLayoutFinish.append(self._incarca)

	def _incarca(self):
		try:
			self._randuri = S.sportAzi()
		except Exception as e:
			print("[HdsSportAzi] %s" % e)
			self._randuri = []
		self._arata()

	def _arata(self):
		randuri = [r for r in self._randuri if r["direct"] or not self._numaiDirect]
		self["lista"].setList([(S.textRand(r), r) for r in randuri])
		self["key_yellow"].setText(_("Toate") if self._numaiDirect else _("Numai în direct"))
		if not randuri:
			self["detalii"].setText(_("Ghidul nu are sport azi pe canalele din listele tale. Ghidul unui canal se umple după ce stai câteva secunde pe el."))
		self._detalii()

	def _curent(self):
		c = self["lista"].getCurrent()
		return c[1] if c else None

	def _detalii(self):
		r = self._curent()
		if r is None:
			return
		t = u"%s - %s  %s" % (S.ora(r["inceput"]), S.ora(r["inceput"] + r["durata"]), r["canal"])
		if r["alte"]:
			t += u"\n" + _("Și pe: %s") % u", ".join(r["alte"][:6])
		elif r["scurt"]:
			t += u"\n" + r["scurt"][:140]
		self["detalii"].setText(t)

	def _comutaDirect(self):
		self._numaiDirect = not self._numaiDirect
		self._arata()

	def _ok(self):
		r = self._curent()
		if r is None:
			return
		from enigma import eServiceReference, eEPGCache
		if r["acum"]:
			self.session.nav.playService(eServiceReference(r["ref"]))
			self.close()
			return
		ev = eEPGCache.getInstance().lookupEventId(eServiceReference(r["ref"]), r["id"])
		if ev is None:
			return
		from ServiceReference import ServiceReference
		from Screens.EventView import EventViewSimple
		self.session.open(EventViewSimple, ev, ServiceReference(r["ref"]))
