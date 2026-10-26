# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# CleanupWizard.py: Curățenia discului (fișiere temporare, cache pachete opkg).
# Cod 100% propriu, scris de la zero.
#
# SCOP DELIBERAT INGUST, cf. deciziei explicite: STRICT curățenie de cache/temporare
# regenerabile, NICIODATĂ setări, canale, înregistrări sau cronometre. Resetarea COMPLETĂ la
# valorile din fabrică există deja, separat ("Reset to Factory Defaults", `Screens/FactoryReset.py`,
# `data/menu.xml`) -- acest ecran NU o dublează și nu o înlocuiește.
#
# De ce doar aceste două categorii, verificate direct pe receptor (SSH, doar citire):
# `/tmp` și `/var/cache/opkg` există amândouă pe imagine, sunt STRICT regenerabile prin
# design (opkg redescarcă pachetele la nevoie, `/tmp` se golește oricum la fiecare repornire) — spre
# deosebire de jurnalele din `/home/root/logs/`, deja gestionate separat de `Screens/LogManager.py`
# (NEDUPLICAT aici, ca să nu existe două ecrane care fac același lucru).
#
# "Se golește oricum la repornire" e adevărat pentru `/tmp` DOAR la boot, nu și LIVE, cât sistemul
# rulează: `/tmp` poate conține obiecte active — socket-uri
# (`/tmp/mmi.socket`, dialogul MMI cu modulul CAM) și steagul propriu `hds-pornire-stick.ruleaza`
# (`porneste.sh`). `_ePastrat()` le protejează automat, nu doar avertizează.

import os

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Label import Label
from Components.Button import Button
from Screens.MessageBox import MessageBox
# logica (categoriile, marimile, ce se pastreaza, golirea) e in Components/HdsCuratenie.py, folosita si de pagina web
# /curatenie; numele de aici raman pentru cine le folosea
from Components import HdsCuratenie

_marimeFolder = HdsCuratenie.marimeFolder
_ePastrat = HdsCuratenie.ePastrat
_curataFolder = HdsCuratenie.curataFolder
_formatMB = HdsCuratenie.formatMB
NUME_EXCLUSE_TMP = HdsCuratenie.NUME_EXCLUSE_TMP
CATEGORII = HdsCuratenie.categorii()


class CleanupWizard(Screen):
	skin = """
	<screen name="CleanupWizard" resolution="1920,1080" position="center,center" size="900,420" title="Curățenia discului">
		<widget name="lista" position="30,30" size="840,220" scrollbarMode="showOnDemand" font="Regular;22" itemHeight="42" />
		<widget name="ghid" position="30,260" size="840,100" zPosition="1" font="Regular;18" halign="left" />
		<widget name="buton_rosu" position="30,368" size="410,42" zPosition="1" backgroundColor="#9f1313" font="Regular;20" halign="center" valign="center" />
		<widget name="buton_verde" position="460,368" size="410,42" zPosition="1" backgroundColor="#1f771f" font="Regular;20" halign="center" valign="center" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Curățenia discului"))

		self["ghid"] = Label(_(
			"Șterge doar fișiere temporare și cache de pachete; nu atinge NICIODATĂ "
			"canale, înregistrări, cronometre sau setări. Pentru resetare completă, "
			"folosește „Reset to Factory Defaults” din meniul Sistem."))
		self["buton_rosu"] = Button(_("Înapoi"))
		self["buton_verde"] = Button(_("Curăță selecția"))

		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions", "DirectionActions"],
			{
				"cancel": self.close,
				"red": self.close,
				"green": self._confirmaCuratare,
				"ok": self._confirmaCuratare,
				"up": self._sus,
				"down": self._jos,
			}, -2)

		self["lista"] = MenuList([])
		self._reincarcaListaSiMarimi()

	def _randCategorie(self, cheie, eticheta, cale):
		marime = _marimeFolder(cale) if os.path.isdir(cale) else 0
		return "%-38s %10s" % (eticheta, _formatMB(marime))

	def _reincarcaListaSiMarimi(self):
		randuri = [self._randCategorie(cheie, eticheta, cale) for cheie, eticheta, cale, _nume_excluse in CATEGORII]
		self["lista"].setList(randuri)

	def _sus(self):
		self["lista"].up()

	def _jos(self):
		self["lista"].down()

	def _confirmaCuratare(self):
		index = self["lista"].getSelectionIndex()
		if not (0 <= index < len(CATEGORII)):
			return
		cheie, eticheta, cale, nume_excluse = CATEGORII[index]
		self.session.openWithCallback(
			lambda raspuns: self._dupaConfirmare(raspuns, eticheta, cale, nume_excluse),
			MessageBox,
			_("Ștergi conținutul „%s”?\nCale: %s\nAcțiunea nu poate fi anulată.\n"
				"Fișierele folosite acum de programe și steagul de probă prin stick "
				"sunt păstrate automat.") % (eticheta, cale),
			MessageBox.TYPE_YESNO,
			default=False,
		)

	def _dupaConfirmare(self, raspuns, eticheta, cale, nume_excluse):
		if not raspuns:
			return
		if not os.path.isdir(cale):
			self.session.open(MessageBox, _("Folderul „%s” nu există pe acest sistem.") % cale, MessageBox.TYPE_INFO)
			self._reincarcaListaSiMarimi()
			return
		sterse, eliberati = _curataFolder(cale, nume_excluse)
		self._reincarcaListaSiMarimi()
		self.session.open(
			MessageBox,
			_("„%s” curățat: %d fișiere șterse, %s eliberați.") % (eticheta, sterse, _formatMB(eliberati)),
			MessageBox.TYPE_INFO,
		)
