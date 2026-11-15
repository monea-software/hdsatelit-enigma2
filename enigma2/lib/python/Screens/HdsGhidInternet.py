# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ecranul Ghidul TV din internet (Media > Ghidul TV din internet, MENU in ghid): tara omului si sursele ei; OK sau Verde =
EPG Import instalat daca lipseste, sursele tarii bifate, importul pornit acum si zilnic. Galben = alta tara. Cand tara nu e
sigura, OK intreaba intai tara (cele aflate primele). Logica: Components/HdsGhidInternet.py; pagina web: /ghid-internet."""
from Components.ActionMap import ActionMap
from Components.Label import Label
from Screens.Screen import Screen
from Components import HdsGhidInternet as G


class HdsGhidInternet(Screen):
	skin = """
	<screen name="HdsGhidInternet" resolution="1920,1080" position="center,center" size="1400,640" title="Ghidul TV din internet">
		<widget name="text" position="30,30" size="1340,500" font="Regular;30" />
		<widget name="key_red" position="30,574" size="300,46" font="Regular;24" halign="center" valign="center" backgroundColor="#9f1313" />
		<widget name="key_green" position="350,574" size="360,46" font="Regular;24" halign="center" valign="center" backgroundColor="#1f771f" />
		<widget name="key_yellow" position="730,574" size="360,46" font="Regular;24" halign="center" valign="center" backgroundColor="#a08500" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Ghidul TV din internet"))
		self._stare = {}
		self["text"] = Label("")
		self["key_red"] = Label(_("Înapoi"))
		self["key_green"] = Label(_("Pornește"))
		self["key_yellow"] = Label(_("Altă țară"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close,
			"red": self.close,
			"ok": self._porneste,
			"green": self._porneste,
			"yellow": self._altaTara,
		}, -1)
		G.asculta(self._arata)
		self.onClose.append(lambda: G.lasa(self._arata))
		self.onLayoutFinish.append(self._arata)

	def _arata(self):
		try:
			self._stare = G.stare()
			self["text"].setText(G.textStare(self._stare))
		except Exception as e:
			print("[HdsGhidInternet] %r" % (e,))
			self["text"].setText(_("Eroare pe receptor."))
		self["key_green"].setText(_("Pornește din nou") if self._stare.get("programat") and self._stare.get("bifate") else _("Pornește"))

	def _porneste(self):
		s = self._stare
		if s.get("in_lucru"):
			return
		if s.get("tara") and s.get("are_sursa"):
			self._cu(s["tara"])
		else:
			self._altaTara()

	def _altaTara(self):
		s = self._stare
		primele = [c["cod"] for c in s.get("candidati", []) if c.get("are")]
		lista = [(G.numeTara(c), c) for c in primele]
		lista += [(t["nume"], t["cod"]) for t in s.get("tari", []) if t["cod"] not in primele]
		from Screens.ChoiceBox import ChoiceBox
		self.session.openWithCallback(self._ales, ChoiceBox, title=_("Țara ghidului TV din internet"), list=lista)

	def _ales(self, ales):
		if ales:
			self._cu(ales[1])

	def _cu(self, tara):
		text = G.porneste(tara, self.session)
		if text:
			from Screens.MessageBox import MessageBox
			self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=8)
		self._arata()
