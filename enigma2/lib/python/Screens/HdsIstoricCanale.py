# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsIstoricCanale.py: fereastra mica "Canale recente", in stanga ecranului (imaginea ramane in dreapta): ultimele canale
# vazute, cel mai nou sus, cu emisiunea de acum; canalul de pe ecran e marcat "acum", iar cursorul sta pe cel de
# dinainte. OK porneste canalul ales (ca un zap nou, Components/HdsIstoricCanale.alege), EXIT inchide, < si > (ca si
# sagetile) muta cursorul. Se deschide din bara cu apasarea lunga pe < (actiunea channel_history din
# Components/HdsTasteRapide.py, schimbabila in Alocarea tastelor). Tema: ecranul HdsIstoricCanale din HDSatelit/skin.xml si
# din data/skin_default.xml. Perechea web: HdsWebControl/istoric_web.py.

from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Components import HdsIstoricCanale as I
from Screens.Screen import Screen


class HdsIstoricCanale(Screen):
	def __init__(self, session, infobar=None):
		Screen.__init__(self, session)
		self.infobar = infobar
		self.setTitle(_("Canale recente"))
		self.randuri = []
		self["list"] = List([])
		self["hint"] = StaticText(_("OK pornește canalul · EXIT închide"))
		self["gol"] = StaticText("")
		self["actions"] = ActionMap(["OkCancelActions", "InfobarChannelSelection"], {
			"ok": self.porneste,
			"cancel": self.close,
			# < coboara spre canalele mai vechi, > urca spre cele mai noi (ca pasii din bara)
			"historyBack": self.maiVechi,
			"historyNext": self.maiNou,
		}, -1)
		self.onLayoutFinish.append(self.umple)

	def umple(self):
		try:
			self.randuri = I.randuri(self.infobar)
		except Exception as e:
			print("[HdsIstoricCanale] istoricul nu se poate citi: %s" % e)
			self.randuri = []
		acum = _("acum")
		lista = []
		for i, r in enumerate(self.randuri):
			# (cheie, numarul, numele, emisiunea, eticheta "acum")
			lista.append((r["cheie"], u"%d" % (i + 1), r["nume"], r["emisiune"], acum if r["acum"] else u""))
		self["list"].setList(lista)
		if lista:
			self["list"].setIndex(I.rand_initial(self.randuri))
		else:
			self["gol"].setText(_("Încă nu ai schimbat canalul. Canalele văzute apar aici."))

	def maiVechi(self):
		self["list"].selectNext()

	def maiNou(self):
		self["list"].selectPrevious()

	def porneste(self):
		rand = self["list"].getCurrent()
		self.close()
		if rand:
			try:
				I.porneste(rand[0], self.infobar)
			except Exception as e:
				print("[HdsIstoricCanale] zap: %s" % e)
