# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# SwapManager.py: crearea, activarea si oprirea unui fisier de swap pe un disc HDD/USB montat. Cod propriu.
# Lista discurilor vine din Components/Harddisk.py (harddiskmanager), fara detectie proprie.
#
# Logica (discurile, /proc/swaps, comenzile fallocate/dd, mkswap, swapon, swapoff ca liste de argumente, fara shell)
# e in Components/HdsSwap.py, folosita si de pagina web /swap (HdsWebControl/disc_web.py); televizorul si pagina impart
# aceeasi stare, deci nu pornesc doua lucrari deodata.
#
# Nota: NU s-a scris un DeviceManager.py separat: initializarea si verificarea discurilor exista deja in
# Screens/HarddiskSetup.py ("Format Hard Drive" / "Check Disk Health").

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Label import Label
from Components.Button import Button
from Components import HdsSwap

CALE_SWAPFILE = HdsSwap.CALE_SWAPFILE
MARIME_MB_IMPLICITA = HdsSwap.MARIME_MB_IMPLICITA


def _swapuriActive():
	"""Fisierele si partitiile de swap active acum (Components/HdsSwap.swapuriActive)."""
	return HdsSwap.swapuriActive()


class SwapManager(Screen):
	skin = """
	<screen name="SwapManager" resolution="1920,1080" position="center,center" size="1000,520" title="Fișier de swap (memorie virtuală)">
		<widget name="lista" position="30,30" size="940,280" font="Regular;22" itemHeight="40" scrollbarMode="showOnDemand" />
		<widget name="stare" position="30,320" size="940,100" font="Regular;20" />
		<widget name="key_red" position="30,460" size="230,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_green" position="270,460" size="230,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_yellow" position="510,460" size="230,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Fișier de swap (memorie virtuală)"))
		self._inchis = False
		self._discuri = []
		self._semnal_medii = None
		self._recauta = False
		self._prima_citire = True
		from enigma import eTimer
		self._ceas = eTimer()
		try:
			self._legatura = self._ceas.timeout.connect(self._reincarcaLista)
		except AttributeError:
			self._ceas.callback.append(self._reincarcaLista)

		self["lista"] = MenuList([])
		self["stare"] = Label("")
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Activează swap (512 MB)"))
		self["key_yellow"] = Button(_("Oprește swap pe disc"))
		self["key_green"].hide()
		self["key_yellow"].hide()

		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions"],
			{
				"cancel": self.close,
				"red": self.close,
				"green": self._activeaza,
				"yellow": self._opreste,
			}, -2)

		self.onLayoutFinish.append(self._reincarcaLista)
		self.onClose.append(self._laInchidere)
		try:
			from Components.Harddisk import harddiskmanager
			self._semnal_medii = harddiskmanager.on_partition_list_change
			self._semnal_medii.append(self._mediiSchimbate)
		except (ImportError, AttributeError):
			pass

	def _laInchidere(self):
		self._inchis = True
		self._ceas.stop()
		if self._semnal_medii is not None and self._mediiSchimbate in self._semnal_medii:
			self._semnal_medii.remove(self._mediiSchimbate)

	def _mediiSchimbate(self, *args):
		if not self._inchis:
			self._recauta = True
			self._ceas.start(300, True)

	def _reincarcaLista(self):
		if self._inchis:
			return
		st = HdsSwap.cereInventar(reface=self._prima_citire)
		self._prima_citire = False
		if st["cauta"] or HdsSwap.inLucru():
			self._ceas.start(300, True)
			return
		self._recauta = False
		if st.get("eroare"):
			self["stare"].setText(_("Discurile nu pot fi citite. Încearcă din nou."))
			return
		ales = self._discSelectat()
		punct = ales["punct"] if ales else None
		self._discuri = list(st["discuri"])
		active = st["active"]
		randuri = [HdsSwap.textRand(d) for d in self._discuri]
		self["lista"].setList(randuri or [_("Niciun disc HDD/USB montat momentan.")])
		for i, d in enumerate(self._discuri):
			if d["punct"] == punct:
				self["lista"].moveToIndex(i)
				break
		# fara disc, verde si galben nu au pe ce lucra (_discSelectat intoarce None): nu se arata
		for tasta in ("key_green", "key_yellow"):
			if self._discuri:
				self[tasta].show()
			else:
				self[tasta].hide()
		self["stare"].setText(HdsSwap.textActive(active))

	def _discSelectat(self):
		index = self["lista"].getSelectionIndex()
		if self._discuri and 0 <= index < len(self._discuri):
			return self._discuri[index]
		return None

	def _activeaza(self):
		disc = self._discSelectat()
		if disc is None:
			return
		pornit, text = HdsSwap.activeaza(disc["punct"], gata=self._dupaComanda)
		self["stare"].setText(text)

	def _opreste(self):
		disc = self._discSelectat()
		if disc is None:
			return
		pornit, text = HdsSwap.opreste(disc["punct"], gata=self._dupaComanda)
		self["stare"].setText(text)

	def _dupaComanda(self, lucru=None):
		if not self._inchis:
			self._reincarcaLista()
