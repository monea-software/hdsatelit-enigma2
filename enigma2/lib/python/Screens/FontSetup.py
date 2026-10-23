# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# FontSetup: "Marimea textului" (Meniu > Interfata si aspect). Un singur reglaj, procentul tuturor textelor (80-130%),
# cu glisorul nostru (sina subtire, umplerea de la minim, procentul scris langa ea) si o proba care isi schimba marimea
# pe loc: fonturile probei se pun direct pe etichete, pentru ca procentul din skin.py se aplica numai ecranelor deschise
# dupa salvare. Logica (limitele, treptele, salvarea) e in Components/HdsMarimeText.py, aceeasi cu pagina web
# /marime-text.
#
# Skinul: ecranul HdsMarimeText din skin.xml (cadrul HdsCadru1240); pe alt skin, rezerva de mai jos, scrisa pe 1280 si
# scalata la ecran (Tools/ScaledSkin), in acelasi desen, cu culori scrise ca numere si fonturile Regular / Bold.

from enigma import gFont, getDesktop

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.ProgressBar import ProgressBar
from Components import HdsMarimeText as M
from Tools.ScaledSkin import scaledSkin

import skin as hds_skin


def initConfigFontSetup():
	M.initConfig()


def aplicaScalareFonturi():
	"""Chemata la pornire (Components/SetupDevices.py), inaintea primului ecran."""
	initConfigFontSetup()
	from Components.config import config
	hds_skin.setFontScalePercent(config.osd.fontscale.value)
	# fontul interfetei ales (Components/HdsFontInterfata.py): dupa skin, ca addFont-ul lui sa castige; o eroare aici
	# lasa Open Sans, nu opreste pornirea
	try:
		from Components import HdsFontInterfata
		HdsFontInterfata.aplicaLaPornire()
	except Exception as e:
		print("[FontSetup] fontul interfetei: %r" % (e,))


# Rezerva pe 1280 (cotele de 1920 x 2/3): fereastra 826 x 666 la 48,27, titlul si ceasul in ea, liniile, butoanele cu
# bare colorate jos, in culorile skinului HDSatelit scrise ca numere.
SKIN_REZERVA = """
<screen name="HdsMarimeText" position="48,27" size="826,666" backgroundColor="#0D10162A" flags="wfNoBorder" title="Mărimea textului">
	<eLabel position="0,0" size="826,1" backgroundColor="#99FFFFFF" zPosition="1" />
	<widget source="Title" render="Label" position="21,12" size="667,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget source="global.CurrentTime" render="Label" position="699,12" size="107,37" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" zPosition="1">
		<convert type="ClockToText">Format:%H:%M</convert>
	</widget>
	<eLabel position="21,59" size="784,1" backgroundColor="#D9FFFFFF" zPosition="1" />
	<widget name="eticheta" position="21,75" size="347,40" font="Regular;21" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget name="glisor" position="384,91" size="304,8" foregroundColor="#009FB4FF" backgroundColor="#002A3350" zPosition="2" />
	<widget name="minim" position="384,101" size="80,20" font="Regular;15" foregroundColor="#00AEB9CC" backgroundColor="#0D10162A" transparent="1" halign="left" noWrap="1" zPosition="1" />
	<widget name="maxim" position="608,101" size="80,20" font="Regular;15" foregroundColor="#00AEB9CC" backgroundColor="#0D10162A" transparent="1" halign="right" noWrap="1" zPosition="1" />
	<widget name="procent" position="699,75" size="107,40" font="Bold;21" foregroundColor="#009FB4FF" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="21,131" size="784,1" backgroundColor="#D9FFFFFF" zPosition="1" />
	<widget name="titlu_proba" position="21,139" size="784,24" font="Regular;16" foregroundColor="#00AEB9CC" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget name="proba_titlu" position="21,165" size="784,43" font="Bold;27" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget name="proba_rand" position="21,212" size="784,40" font="Regular;21" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="21,256" size="784,40" backgroundColor="#00374EA1" zPosition="1" />
	<widget name="proba_ales" position="37,256" size="752,40" font="Regular;21" foregroundColor="#00FFFFFF" backgroundColor="#00374EA1" transparent="1" valign="center" noWrap="1" zPosition="2" />
	<widget name="proba_setare" position="21,300" size="448,40" font="Regular;21" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<widget name="proba_valoare" position="480,300" size="325,40" font="Bold;20" foregroundColor="#009FB4FF" backgroundColor="#0D10162A" transparent="1" halign="right" valign="center" noWrap="1" zPosition="1" />
	<widget name="proba_mic" position="21,344" size="784,27" font="Regular;16" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="21,477" size="784,1" backgroundColor="#D9FFFFFF" zPosition="1" />
	<widget name="ajutor" position="21,485" size="784,96" font="Regular;19" foregroundColor="#00C9D2E3" backgroundColor="#0D10162A" transparent="1" zPosition="1" />
	<widget name="stare" position="21,584" size="784,27" font="Regular;16" foregroundColor="#00AEB9CC" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="21,616" size="784,1" backgroundColor="#D9FFFFFF" zPosition="1" />
	<eLabel position="21,629" size="4,21" backgroundColor="#00E5484D" zPosition="1" />
	<widget name="key_red" position="32,624" size="180,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="217,629" size="4,21" backgroundColor="#0046B06A" zPosition="1" />
	<widget name="key_green" position="228,624" size="180,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
	<eLabel position="413,629" size="4,21" backgroundColor="#00E8B93A" zPosition="1" />
	<widget name="key_yellow" position="424,624" size="180,32" font="Regular;19" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" transparent="1" valign="center" noWrap="1" zPosition="1" />
</screen>"""


def _factorEcran():
	"""Latimea ecranului fata de 1920 (skinul HDSatelit e scris pe 1920; rezerva ajunge la fel prin ScaledSkin)."""
	try:
		w = getDesktop(0).size().width()
		if w > 0:
			return w / 1920.0
	except Exception:
		pass
	return 1.0


class FontSetup(Screen):
	"""Marimea textului: Stanga / Dreapta schimba procentul, proba se schimba pe loc, Verde salveaza."""

	def __init__(self, session):
		self.skin = scaledSkin(SKIN_REZERVA)
		Screen.__init__(self, session)
		self.skinName = ["HdsMarimeText"]
		self.setTitle(_("Font Size"))
		self.salvat = M.salvat()
		self.procent = self.salvat
		self.factor = _factorEcran()

		self["eticheta"] = Label(_("Mărimea tuturor textelor"))
		self["glisor"] = ProgressBar()
		self["minim"] = Label(M.text(M.MINIM))
		self["maxim"] = Label(M.text(M.MAXIM))
		self["procent"] = Label("")
		self["titlu_proba"] = Label(_("Proba, cu mărimea aleasă:"))
		for cheie, _familie, _baza, text in M.PROBA:
			self[cheie] = Label(_(text))
		self["ajutor"] = Label(_("Stânga și Dreapta schimbă mărimea cu câte %(pas)s. Proba de deasupra se schimbă pe loc. "
			"Verde salvează: noua mărime se vede în ecranele pe care le deschizi după aceea. "
			"Galben pune înapoi mărimea din fabrică, %(implicit)s.") % {"pas": "%d%%" % M.PAS, "implicit": M.text(M.IMPLICIT)})
		self["stare"] = Label("")
		self["key_red"] = Label(_("Renunță"))
		self["key_green"] = Label(_("Salvează"))
		self["key_yellow"] = Label(_("Înapoi la %s") % M.text(M.IMPLICIT))

		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.salveaza,
			"green": self.salveaza,
			"cancel": self.renunta,
			"red": self.renunta,
			"yellow": self.implicit,
			"left": lambda: self.schimba(-1),
			"right": lambda: self.schimba(1),
			"leftRepeated": lambda: self.schimba(-1),
			"rightRepeated": lambda: self.schimba(1),
			# sus / jos nu au ce face aici; legate (si ridicarea tastelor), ca jurnalul sa nu scrie "unknown action"
			"up": self.nimic, "down": self.nimic, "upRepeated": self.nimic, "downRepeated": self.nimic,
			"upUp": self.nimic, "downUp": self.nimic, "leftUp": self.nimic, "rightUp": self.nimic,
		}, -1)
		self.onLayoutFinish.append(self.arata)
		getattr(self, "onLayoutFinish", []).append(self._ajutorMarit)

	def _ajutorMarit(self):
		"""Textul marit (marimea salvata peste 100 %, Components/HdsMarireText): ajutorul de jos (3 randuri la 100 %) creste
		in sus, in locul liber de sub proba, iar linia de deasupra lui urca odata cu el; de la 125 % se pierdea ultimul
		rand ("...fabrica, 100%."), chiar pe ecranul marimii. La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			a = MT.Asezare(self)
			sus = 0
			for cheie, _familie, _baza, _text in M.PROBA:
				sk = a.dinSkin(self[cheie].instance) if self[cheie].instance is not None else None
				if sk:
					sus = max(sus, sk[1] + sk[3] + 4)
			ajutor = self["ajutor"].instance
			if sus and ajutor is not None:
				a.creste(ajutor, MT.inaltimeText(ajutor), sus, sus=True)
		except Exception as e:
			print("[FontSetup] textul marit: %s" % e)

	def nimic(self):
		pass

	def schimba(self, directie):
		self.procent = M.urmator(self.procent, directie)
		self.arata()

	def implicit(self):
		self.procent = M.IMPLICIT
		self.arata()

	def arata(self):
		self["glisor"].setValue(M.umplere(self.procent))
		self["procent"].setText(M.text(self.procent))
		if self.procent == self.salvat:
			self["stare"].setText(_("Salvat acum: %s. Din fabrică: %s.") % (M.text(self.salvat), M.text(M.IMPLICIT)))
		else:
			self["stare"].setText(_("Nesalvat: %s. Salvat acum: %s.") % (M.text(self.procent), M.text(self.salvat)))
		for cheie, familie, baza, text in M.PROBA:
			eticheta = self[cheie]
			if eticheta.instance is None:
				continue
			# fontul inaintea textului: setText redeseneaza cu fontul pus atunci; sub alt skin ales, fontul HDSatelit al
			# ecranelor noastre (hds_skin.fontHds), ca proba sa arate ce se vede in ele
			eticheta.instance.setFont(gFont(hds_skin.fontHds(familie), M.marime(int(round(baza * self.factor)), self.procent)))
			eticheta.setText(_(text))

	def salveaza(self):
		bun, rezultat = M.seteaza(self.procent)
		if bun:
			self.close(True)
		else:
			self["stare"].setText(_(rezultat))

	def renunta(self):
		self.close(False)
