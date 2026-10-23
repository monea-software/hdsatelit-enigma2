# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HD Satelit - Data, ora și fusul orar
# Implementare 100% curată bazată pe Dreambox upstream
#
# setările și sincronizarea stau acum în Components/HdsCeas.py și pornesc odată cu
# enigma2 (mytest.py), nu la deschiderea acestui ecran. NTP chiar merge (ntpdate sau ntpd din BusyBox, fără să oprească
# pornirea când nu e rețea), ora din transponder mută ceasul cât ora nu e confirmată (lib/dvb/dvbtime.cpp), iar ora se
# salvează periodic în fake-hwclock. „Manual” (nu făcea nimic) a ieșit; implicit e „Internet, apoi transponder”.
# Aceleași setări și aceeași stare în interfața web: /ceas (HdsWebControl/ceas_web.py).

import time
from .Screen import Screen
from Components.ConfigList import ConfigListScreen
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.config import config, configfile, getConfigListEntry
from Components import HdsCeas

HdsCeas.initConfig()

# tm_wday: 0 = luni. Numele zilelor au traducere in toate limbile imaginii; lunile nu, deci data e cu cifre, ca in
# interfata web (/ceas). %A si %B din strftime ar iesi in limba sistemului (C), adica in engleza.
def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: numele se traduc la folosire."""
	return text


_ZILE = (N_("Monday"), N_("Tuesday"), N_("Wednesday"), N_("Thursday"), N_("Friday"), N_("Saturday"), N_("Sunday"))


def textDataOra(t):
	"""„Duminică, 27.12.2026, 03:22:10” din time.struct_time; fara linie lunga, data si ora despartite prin virgula."""
	return "%s, %s" % (_(_ZILE[t.tm_wday]), time.strftime("%d.%m.%Y, %H:%M:%S", t))


# Skinul ecranului dupa marimea textului (config.osd.fontscale, skin.py mareste fontul, nu si caseta): tastele colorate
# se latesc si cresc cu procentul (la 115 % "Sincronizeaza acum" trecea pe doua randuri si se taia), iar randul cu ora
# receptorului creste (cozile literelor se taiau). Un text care incape la 100 % incape si marit. Valorile din lista au
# secondfont dat, ca sa creasca si ele cu procentul: Regular 20, aproape cat etichetele (22), ca in listele de setari ale
# skinului (32 / 30); cu Regular 16 (cat punea C++-ul fara el) valorile erau mult mai mici decat etichetele.
SKIN_TIME = """
	<screen resolution="1920,1080" position="center,center" size="900,560" title="Data, ora și fusul orar">
		<widget name="config" position="30,30" size="840,270" scrollbarMode="showOnDemand" font="Regular;22" secondfont="Regular;20" itemHeight="38" />
		<widget source="current_time" render="Label" position="30,310" size="840,%(ora)d" font="Regular;22" halign="center" />
		<widget source="stare" render="Label" position="30,350" size="840,140" font="Regular;19" halign="left" valign="top" />
		<widget source="key_red" render="Label" position="30,500" size="%(lat)d,%(inalt)d" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="%(x2)d,500" size="%(lat)d,%(inalt)d" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget source="key_yellow" render="Label" position="%(x3)d,500" size="%(lat)d,%(inalt)d" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
	</screen>
	"""


def skinTime(procent=None):
	"""Skinul ecranului la marimea textului data (implicit cea aleasa); la 100 % (si sub) cel de dinainte."""
	if procent is None:
		try:
			import skin
			procent = int(skin.getFontScalePercent())
		except Exception:
			procent = 100
	k = max(100, int(procent))
	lat = 200 * k // 100
	return SKIN_TIME % {"ora": min(40, 32 * k // 100), "lat": lat, "inalt": 35 * k // 100, "x2": 30 + lat + 20,
		"x3": 30 + 2 * (lat + 20)}


class Time(Screen, ConfigListScreen):
	skin = skinTime(100)

	def __init__(self, session):
		self.skin = skinTime()
		Screen.__init__(self, session)
		self.setTitle(_("Data, ora și fusul orar"))

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["key_yellow"] = StaticText(_("Sincronizează acum"))
		self["current_time"] = StaticText("")
		self["stare"] = StaticText("")
		self.mesaj = ""

		self.list = []
		ConfigListScreen.__init__(self, self.list, session=session)

		self["actions"] = ActionMap(["SetupActions", "ColorActions"],
		{
			"ok": self.keySave,
			"cancel": self.keyCancel,
			"green": self.keySave,
			"red": self.keyCancel,
			"yellow": self.syncNow
		}, -2)

		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.updateCurrentTime)
		self.onClose.append(self.ceas.stop)

		self.createSetup()
		self.updateCurrentTime()
		self.ceas.start(1000, False)

	def createSetup(self):
		self.list = []
		if "timezone" in config.content.items:
			self.list.append(getConfigListEntry(_("Fus orar"), config.timezone.val))
		self.list.append(getConfigListEntry(_("De unde se ia ora"), config.hds_time.sync_mode))
		if config.hds_time.sync_mode.value in ("auto", "ntp"):
			self.list.append(getConfigListEntry(_("Server NTP"), config.hds_time.ntp_server))
		self["config"].list = self.list
		self["config"].setList(self.list)

	def updateCurrentTime(self):
		self["current_time"].setText(_("Ora receptorului: %s") % textDataOra(time.localtime()))
		try:
			s = HdsCeas.stare()
			randuri = [s["sursa_text"], s["ultima_text"]]
			if s["in_curs"]:
				randuri.append(_("Se sincronizează acum prin Internet."))
		except Exception as e:
			print("[Time] starea ceasului: %r" % (e,))
			randuri = []
		if self.mesaj:
			randuri.append(self.mesaj)
		self["stare"].setText("\n".join(r for r in randuri if r))

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self.createSetup()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self.createSetup()

	def syncNow(self):
		# numele serverului e verificat și dat programului NTP ca un singur argument, fără interpretor de
		# comenzi (Components/HdsCeas.py), în afara firului principal, cu limită de timp
		for x in self["config"].list:
			x[1].save()
		configfile.save()
		pornit, self.mesaj = HdsCeas.sincronizeazaAcum()
		self.updateCurrentTime()

	def keySave(self):
		for x in self["config"].list:
			x[1].save()
		configfile.save()
		if "timezone" in config.content.items:
			from Components.Timezones import timezones
			timezones.activateTimezone(config.timezone.val.index)
		self.close()

	def keyCancel(self):
		for x in self["config"].list:
			x[1].cancel()
		self.close()
