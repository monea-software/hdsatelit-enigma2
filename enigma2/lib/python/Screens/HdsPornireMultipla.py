# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPornireMultipla.py: lista imaginilor din meniul de oprire, pentru
# receptoare cu bootoptions sau kexec instalat (SystemInfo["HdsMultiboot"]).
#
# La deschidere ecranul cauta imaginile instalate in memorie, pe card, pe stick si pe HDD (Components/HdsPornireMultipla.py:
# STARTUP_N de pe partitia bootoptions sau, la Vu+ 4K cu kexec, de pe radacina flash de la /boot, cu Recovery ca locul 0,
# nucleul si sistemul fiecarui loc), pe un fir separat, ca interfata sa nu stea, si le arata, oricare ar fi locul pornit,
# cu imaginea pornita acum marcata; locurile goale nu apar. OK (sau VERDE) pe o imagine: o intrebare scurta, apoi
# STARTUP scris sigur si repornirea receptorului in ea. Daca la repornire receptorul intreaba (o inregistrare, o lucrare) si
# raspunzi Nu, STARTUP se pune la loc. Un loc care nu se alege spune de ce pe rand, iar OK arata motivul intreg. Cat ecranul
# e deschis, lista se reface singura cand se pune sau se scoate un disc. ROSU inchide. Aceeasi lista si aceeasi alegere in
# web: cardul flash din /alimentare (HdsWebControl/alimentare_web.py).
# Skinul HDSatelit: forma ecranului HdsNavigatorFavorite (lista + nota, cadrul HdsCadru1240), aceleasi nume de widgeturi.

import threading
import time

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Components import HdsPornireMultipla as P


class HdsPornireMultipla(Screen):
	skin = """
	<screen name="HdsPornireMultipla" resolution="1920,1080" position="center,center" size="1240,760" title="Repornește în altă imagine">
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
		self.citire = None      # ce intoarce firul citirii cat merge
		self.semn = None        # discurile puse la ultima citire
		self["lista"].onSelectionChanged.append(self.butoane)
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.citeste)
		self.ceasFir = eTimer()
		self.ceasFir.callback.append(self.veziFirul)
		self.ceasDiscuri = eTimer()
		self.ceasDiscuri.callback.append(self.veziDiscurile)
		self.onClose.append(self.opresteCeasurile)
		self.ceas.start(50, True)

	def opresteCeasurile(self):
		self.ceas.stop()
		self.ceasFir.stop()
		self.ceasDiscuri.stop()

	def citeste(self):
		"""Citirea listei pe un fir: mounturile si citirile de pe card nu tin interfata pe loc."""
		if self.citire is not None:
			return
		self.citire = citire = {}
		self.semn = P.semnDiscuri()

		def lucreaza():
			inceput = time.time()
			try:
				stare = P.locuri()
			except Exception as e:
				print("[HdsPornireMultipla] %r" % (e,))
				stare = {"locuri": [], "eroare": True}
			print("[HdsPornireMultipla] lista: %d locuri in %d ms" % (len(stare["locuri"]), (time.time() - inceput) * 1000))
			citire["stare"] = stare

		fir = threading.Thread(target=lucreaza, name="HdsPornireMultipla")
		fir.daemon = True
		fir.start()
		self.ceasFir.start(100, False)

	def veziFirul(self):
		if self.citire is None or "stare" not in self.citire:
			return
		self.ceasFir.stop()
		self.stare, self.citire = self.citire["stare"], None
		ales = self._ales()
		randuri = [(text, l) for text, l in zip(P.randuri(self.stare), self.stare["locuri"])]
		self["lista"].setList(randuri)
		if ales:
			for i, (_text, l) in enumerate(randuri):
				if l["loc"] == ales["loc"]:
					self["lista"].moveToIndex(i)
					break
		self["nota"].setText(P.nota(self.stare))
		self.butoane()
		self.ceasDiscuri.start(2000, False)

	def veziDiscurile(self):
		"""S-a pus sau s-a scos un disc: lista se reface, ca omul sa nu aiba de deschis ecranul din nou."""
		if self.citire is None and P.semnDiscuri() != self.semn:
			self.citeste()

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
		if not l.get("alegere"):
			self.session.open(MessageBox, P.textRefuz(l), MessageBox.TYPE_ERROR, timeout=10)
			return
		asteptat = (l.get("date"), l["imagine"])
		self.session.openWithCallback(lambda da, loc=l["loc"]: self.confirmat(da, loc, asteptat), MessageBox,
			_(P.INTREBARE) % l["imagine"], MessageBox.TYPE_YESNO, default=True)

	def confirmat(self, da, loc, asteptat=None):
		if not da:
			return
		ok, text = P.reporneste(self.session, loc, asteptat=asteptat)
		if not ok:
			from Screens.MessageBox import MessageBox
			self.session.open(MessageBox, text, MessageBox.TYPE_ERROR, timeout=10)
			self.citeste()


class HdsKexecInstalare(Screen):
	"""Pornire multipla Vu+ (Kexec), din meniul Putere numai pe Vu+ 4K pornit direct din flash, fara pornire multipla
	(SystemInfo["HdsKexecInstalabil"]). VERDE: aduce pachetul kexec-multiboot-<masina> din feedul extern (daca nu e deja),
	o singura intrebare, apoi Components/HdsPornireMultipla.kexecInstaleaza (verificarile si scrierea, acolo) si
	repornirea. Aceeasi instalare in web: cardul kexec din /alimentare (HdsWebControl/alimentare_web.py)."""
	skin = """
	<screen name="HdsKexecInstalare" resolution="1920,1080" position="center,center" size="1240,560" title="Pornire multiplă Vu+ (Kexec)">
		<widget source="nota" render="Label" position="30,25" size="1180,450" font="Regular;28" halign="left" valign="top" />
		<widget source="key_red" render="Label" position="30,505" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="310,505" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_(P.KEXEC_TITLU))
		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText("")
		self["nota"] = StaticText("")
		self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
			"ok": self.instaleaza,
			"green": self.instaleaza,
			"cancel": self.inchide,
			"red": self.inchide,
		}, -2)
		self.lucreaza = False
		self.arata()

	def arata(self):
		st = P.kexecStare()
		self.stare = st
		if st["instalabil"]:
			self["nota"].setText(_(P.KEXEC_DESPRE))
			self["key_green"].setText(_(P.KEXEC_BUTON))
		else:
			self["nota"].setText(_(st["motiv"]))
			self["key_green"].setText("")

	def inchide(self):
		if not self.lucreaza:
			self.close()

	def instaleaza(self):
		from Screens.MessageBox import MessageBox
		if self.lucreaza or not self.stare.get("instalabil"):
			return
		self.session.openWithCallback(self.confirmat, MessageBox, _(P.KEXEC_INTREBARE), MessageBox.TYPE_YESNO,
			default=False)

	def confirmat(self, da):
		if not da:
			return
		self.lucreaza = True
		self["key_green"].setText("")
		if P.kexecStare()["fisiere"]:
			self.scrie()
			return
		self["nota"].setText(_(P.KEXEC_DESCARC))
		from Components.Console import Console
		self.consola = Console()
		self.consola.ePopen(P.kexecComandaPachet(self.stare["masina"]), self.descarcat)

	def descarcat(self, rezultat, cod, *_a):
		print("[HdsKexecInstalare] opkg: %r" % (cod,))
		if not P.kexecStare()["fisiere"]:
			self.lucreaza = False
			self.arata()
			self["nota"].setText(_(P.KEXEC_FARA_PACHET))
			return
		self.scrie()

	def scrie(self):
		self["nota"].setText(_(P.KEXEC_SCRIU))
		from enigma import eTimer
		self.ceas = eTimer()
		self.ceas.callback.append(self.scrieAcum)
		self.ceas.start(300, True)   # textul apare inainte de scrierea partitiei (o secunda sau doua)

	def scrieAcum(self):
		ok, text = P.kexecInstaleaza()
		self["nota"].setText(text)
		if not ok:
			self.lucreaza = False
			return
		from Screens.Standby import TryQuitMainloop
		self.session.open(TryQuitMainloop, 2)
