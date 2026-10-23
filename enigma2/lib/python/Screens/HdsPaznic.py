# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPaznic.py: ecranul „Paznicul receptorului”. Meniu > Sistem & Dispozitive.
#
# Arata starea paznicului (hds-watchdog.py) si cele doua setari ale lui, din Components/HdsPaznic.py:
#   - „Repornește interfața când nu mai răspunde” (config.hds_paznic.interfata, implicit Da);
#   - „Așteaptă înainte de repornire” (config.hds_paznic.asteptare, 1, 2 sau 5 minute, implicit 2);
#   - "Elibereaza memoria decodorului in standby" (config.hds_paznic.repornire_noapte, implicit Da; repornirea
#     nevazuta in standby din Components/HdsMemorieDriver.py).
# Paznicul placii (60 s) si oprirea la un blocaj de nucleu raman mereu pornite. In timpul unei scanari, al citirii
# pistelor sau al unei rotiri de antena paznicul asteapta (semnul „ocupat”).
# Aceleasi setari si aceeasi stare in interfata web: /paznic (HdsWebControl/paznic_web.py).

import time

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText
from Components.config import config, configfile, getConfigListEntry
from Components import HdsPaznic as P
from Components import HdsMemorieDriver as M

P.initConfig()
M.initConfig()

# cate semne dintr-un rand al jurnalului se arata (cele de acum au pana la ~130: data, ora, mesajul, calea raportului)
RAND_JURNAL_MAXIM = 240


def textEcran(s, randuri_jurnal):
	"""Textul de sub setari: memoria pozelor si a filmelor (cand lipseste), starea, memoria decodorului, ce
	asteapta, ultima repornire si ultimele randuri din jurnal. Numai informatie."""
	randuri = [s.get("avertisment", ""), s.get("text", ""), (s.get("memorie_driver") or {}).get("text", "")]
	if s.get("reporniri"):
		randuri.append(_("Reporniri ale interfeței de la pornirea receptorului: %d.") % s["reporniri"])
	if s.get("ultima_actiune_ora"):
		randuri.append(_("Ultima: %s.") % time.strftime("%d.%m %H:%M", time.localtime(s["ultima_actiune_ora"])))
	if randuri_jurnal:
		randuri.append(_("Jurnalul paznicului:"))
		# randurile intregi (un rand lung trece pe randul urmator); numai cele foarte lungi se opresc
		randuri.extend(r[:RAND_JURNAL_MAXIM] for r in randuri_jurnal)
	return "\n".join(r for r in randuri if r)


class HdsPaznic(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsPaznic" resolution="1920,1080" position="center,center" size="1100,640" title="Paznicul receptorului">
		<widget name="config" position="30,25" size="1040,130" scrollbarMode="showOnDemand" font="Regular;22" secondfont="Regular;20" itemHeight="40" />
		<widget source="descriere" render="Label" position="30,165" size="1040,60" font="Regular;18" halign="left" valign="top" />
		<widget source="stare" render="Label" position="30,235" size="1040,340" font="Regular;18" halign="left" valign="top" />
		<widget source="key_red" render="Label" position="30,590" size="220,35" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="270,590" size="220,35" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Paznicul receptorului"))
		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))
		self["descriere"] = StaticText(_("Paznicul repornește interfața numai când nu mai dă semn de viață și nici "
			"interfața web nu răspunde. În timpul unei scanări, al citirii pistelor sau al unei rotiri de antenă "
			"așteaptă. Paznicul plăcii rămâne mereu pornit."))
		self["stare"] = StaticText("")
		self.list = []
		ConfigListScreen.__init__(self, self.list, session=session)
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.keySave,
			"green": self.keySave,
			"cancel": self.keyCancel,
			"red": self.keyCancel,
		}, -2)
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.actualizeaza)
		self.onClose.append(self.ceas.stop)
		self.creeaza()
		self.actualizeaza()
		self.ceas.start(3000, False)
		getattr(self, "onLayoutFinish", []).append(self._textMarit)

	def _eticheta(self, nume):
		sursa = self.get(nume)
		for r in getattr(self, "renderer", ()):
			if getattr(r, "source", None) is sursa and getattr(r, "instance", None) is not None:
				return r.instance
		return None

	def _textMarit(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): descrierea de sub lista creste cat ii
		cere textul, iar starea de sub ea coboara si se scurteaza (marginea ei de jos ramane deasupra tastelor); de la
		120 % se pierdea ultimul rand al descrierii. La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			a = MT.Asezare(self)
			desc, stare = self._eticheta("descriere"), self._eticheta("stare")
			sk = a.dinSkin(stare) if stare is not None else None
			if desc is None or sk is None:
				return
			a.creste(desc, MT.inaltimeText(desc), sk[1] + sk[3], maxim=sk[3] // 2)
		except Exception as e:
			print("[%s] textul marit: %s" % (self.__class__.__name__, e))

	def creeaza(self):
		self.list = [getConfigListEntry(_("Repornește interfața când nu mai răspunde"), config.hds_paznic.interfata)]
		if config.hds_paznic.interfata.value:
			self.list.append(getConfigListEntry(_("Așteaptă înainte de repornire"), config.hds_paznic.asteptare))
		self.list.append(getConfigListEntry(_("Eliberează memoria decodorului în standby"),
			config.hds_paznic.repornire_noapte))
		self["config"].list = self.list
		self["config"].setList(self.list)

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self.creeaza()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self.creeaza()

	def actualizeaza(self):
		try:
			self["stare"].setText(textEcran(P.stare(), P.ultimeleRanduriJurnal(randuri=6)))
		except Exception as e:
			print("[HdsPaznic] starea: %r" % (e,))

	def keySave(self):
		# toate, si cand randul asteptarii e ascuns; paznicul le citeste din settings, deci salvarea pe disc conteaza
		config.hds_paznic.repornire_noapte.save()
		config.hds_paznic.interfata.save()
		config.hds_paznic.asteptare.save()
		configfile.save()
		self.close()

	def keyCancel(self):
		config.hds_paznic.interfata.cancel()
		config.hds_paznic.asteptare.cancel()
		config.hds_paznic.repornire_noapte.cancel()
		self.close()
