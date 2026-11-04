# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAdaugaFeed.py: fereastra „Adaugă feed” din Extensii (Screens/HdsExtensii.py, design-web-stitch/skin-pro/anoste/adauga-feed).
# O singura fereastra in locul celor trei de dinainte (tastatura pentru nume, tastatura pentru adresa, intrebarea de la capat): doua randuri,
# OK pe un rand deschide tastatura de pe ecran, verde adauga. Numele se ia singur din adresa cand n-a fost scris; se poate schimba.
# Ce nu trece verificarea (Components/HdsPachete.verifica_sursa) se spune in fereastra, pe randul rosu. Nota despre pachete sta mereu in
# fereastra, deci nu mai e nevoie de o intrebare. close((nume, adresa)) sau close(None).

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.StaticText import StaticText
from Components import HdsPachete as P
from Screens.VirtualKeyBoard import VirtualKeyBoard

RAND_NUME = 0
RAND_ADRESA = 1


def numeDinAdresa(adresa):
	"""Numele propus pentru o adresa: gazda ei, curatata ca un nume de feed; „” cand nu se poate afla."""
	text = (adresa or "").strip().split("://", 1)
	if len(text) != 2:
		return ""
	gazda = text[1].split("/", 1)[0].split(":", 1)[0].split("@")[-1]
	return P.curata_nume_sursa(gazda)


class HdsAdaugaFeed(Screen):
	skin = """
	<screen name="HdsAdaugaFeed" position="center,center" size="1100,452" flags="wfNoBorder" backgroundColor="#0010162A">
		<widget source="Title" render="Label" position="48,16" size="1020,56" font="Regular;36" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" transparent="1" valign="center" noWrap="1" />
		<widget name="et0" position="48,96" size="240,72" font="Regular;26" foregroundColor="#00AEB9CC" backgroundColor="#0010162A" valign="center" noWrap="1" />
		<widget name="val0" position="292,96" size="776,72" font="Regular;30" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" />
		<widget name="et1" position="48,176" size="240,72" font="Regular;26" foregroundColor="#00AEB9CC" backgroundColor="#0010162A" valign="center" noWrap="1" />
		<widget name="val1" position="292,176" size="776,72" font="Regular;30" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" />
		<widget name="nota" position="48,262" size="1020,44" font="Regular;26" foregroundColor="#00C9D2E3" backgroundColor="#0010162A" valign="center" noWrap="1" />
		<widget name="eroare" position="48,306" size="1020,72" font="Regular;26" foregroundColor="#00FF6B5E" backgroundColor="#0010162A" valign="center" />
		<widget source="key_red" render="Label" position="48,398" size="300,40" font="Regular;24" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" />
		<widget source="key_green" render="Label" position="360,398" size="300,40" font="Regular;24" foregroundColor="#00F2F4F8" backgroundColor="#0010162A" valign="center" noWrap="1" />
	</screen>"""

	def __init__(self, session, existente=()):
		Screen.__init__(self, session)
		self.existente = existente
		self.setTitle(_("Adaugă feed"))
		self.valori = ["", "https://"]
		self.rand = RAND_ADRESA
		# numele scris de om nu se mai schimba singur cand se schimba adresa
		self.numeScris = False
		self["et0"] = Label(_("Numele"))
		self["et1"] = Label(_("Adresa"))
		self["val0"] = Label("")
		self["val1"] = Label("")
		self["fond0"] = Label("")
		self["fond1"] = Label("")
		self["nota"] = Label(_("Extensiile din acest feed nu sunt verificate de HD Satelit."))
		self["eroare"] = Label("")
		self["semnEroare"] = Label("")
		self["tastaOk"] = Label("OK")
		self["indiciu"] = StaticText(_("Tastatură"))
		self["key_red"] = StaticText(_("Renunță"))
		self["key_green"] = StaticText(_("Adaugă"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.tastatura,
			"cancel": self.renunta,
			"red": self.renunta,
			"green": self.adauga,
			"up": self.sus,
			"down": self.jos,
		}, -1)
		self.onLayoutFinish.append(self._arata)

	def _arata(self):
		"""Valorile si randul ales: fundalul albastru al temei si textul alb, numai cand skinul are fundalurile."""
		self["val0"].setText(self.valori[RAND_NUME])
		self["val1"].setText(self.valori[RAND_ADRESA])
		for i in (RAND_NUME, RAND_ADRESA):
			ales = i == self.rand
			eticheta = _("Numele") if i == RAND_NUME else _("Adresa")
			# orice componenta are instanta; numai cele din skin au atribute. Fara fundaluri, randul ales are un semn in text
			if self["fond%d" % i].skinAttributes is None:
				self["et%d" % i].setText(("> " if ales else "") + eticheta)
				continue
			from skin import parseColor
			fond = self["fond%d" % i].instance
			fond.setBackgroundColor(parseColor("hdsBrand" if ales else "hdsCell"))
			fond.invalidate()
			self["et%d" % i].instance.setForegroundColor(parseColor("white" if ales else "hdsLabel"))
			self["val%d" % i].instance.setForegroundColor(parseColor("white" if ales else "hdsText"))
		eroare = bool(self["eroare"].getText())
		if eroare:
			self["semnEroare"].show()
		else:
			self["semnEroare"].hide()

	def sus(self):
		self.rand = RAND_NUME
		self._arata()

	def jos(self):
		self.rand = RAND_ADRESA
		self._arata()

	def tastatura(self):
		if self.rand == RAND_NUME:
			titlu = _("Numele feedului: litere mici, cifre și -")
		else:
			titlu = _("Adresă nouă (http:// sau https://)")
		self.session.openWithCallback(self._scris, VirtualKeyBoard, title=titlu, text=self.valori[self.rand])

	def _scris(self, text):
		if text is None:
			return
		self["eroare"].setText("")
		if self.rand == RAND_NUME:
			self.valori[RAND_NUME] = P.curata_nume_sursa(text)
			self.numeScris = bool(self.valori[RAND_NUME])
		else:
			self.valori[RAND_ADRESA] = (text or "").strip()
			if not self.numeScris:
				self.valori[RAND_NUME] = numeDinAdresa(self.valori[RAND_ADRESA])
		self._arata()

	def adauga(self):
		nume, adresa = self.valori
		motiv = P.verifica_sursa(nume, adresa, self.existente)
		if motiv:
			self["eroare"].setText(motiv)
			self._arata()
			return
		self.close((nume, adresa))

	def renunta(self):
		self.close(None)
