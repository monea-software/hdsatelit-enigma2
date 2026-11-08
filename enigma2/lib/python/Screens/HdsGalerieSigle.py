# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
#
# Lista si poza reala vin din acelasi modul folosit de pagina web.
# Firele citesc reteaua. Numai eTimer si ePicLoad ating widgeturile.

from __future__ import absolute_import

import threading

from enigma import ePicLoad, eTimer, getDesktop
from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components import HdsGalerieSigle as galerie
from Tools.ScaledSkin import scaledSkin


ROLURI = ("backdrop", "radio", "bootlogo")


def numeRol(rol):
	return {"bootlogo": _("Sigla timpurie a receptorului"),
		"backdrop": _("Imaginea de pornire"),
		"radio": _("La radio")}.get(rol, rol)


class HdsGalerieSigle(Screen):
	"""Sagetile aleg sigla si locul; OK o pune fara alta intrebare."""

	SKIN_REZERVA = """
	<screen name="HdsGalerieSigle" position="48,27" size="1184,666"
	 backgroundColor="#0D10162A" flags="wfNoBorder" title="Sigle de pornire">
	 <widget source="Title" render="Label" position="21,12" size="1142,38"
	  font="Bold;27" foregroundColor="#00F2F4F8" transparent="1" />
	 <eLabel position="21,59" size="1142,1" backgroundColor="#99FFFFFF" />
	 <widget name="loc" position="21,73" size="1142,36" font="Bold;23"
	  foregroundColor="#00F5B83D" transparent="1" noWrap="1" />
	 <widget name="ajutor" position="21,118" size="1142,48" font="Regular;18"
	  foregroundColor="#00C9D2E3" transparent="1" />
	 <widget name="lista" position="21,180" size="460,360" itemHeight="40"
	  font="Regular;20" textOffset="10,0" scrollbarMode="showOnDemand"
	  foregroundColor="#00F2F4F8" backgroundColor="#0D10162A"
	  backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" />
	 <widget name="poza" position="504,180" size="658,370" alphatest="off" />
	 <widget name="fara_poza" position="504,180" size="658,370" font="Regular;23"
	  foregroundColor="#00C9D2E3" backgroundColor="#000D1120"
	  halign="center" valign="center" zPosition="2" />
	 <widget name="autor" position="504,558" size="658,32" font="Regular;18"
	  foregroundColor="#00C9D2E3" transparent="1" noWrap="1" />
	 <widget name="stare" position="21,597" size="1142,47" font="Regular;18"
	  foregroundColor="#00F2F4F8" transparent="1" />
	</screen>"""

	def __init__(self, session):
		self.skin = scaledSkin(self.SKIN_REZERVA)
		Screen.__init__(self, session)
		self.setTitle(_("Sigle de pornire"))
		self._inchis = False
		self._toate = []
		self._randuri = []
		self._rol = 0
		self._roluri = ["backdrop", "radio"]
		self._lucrare = None
		self._rezultat = None
		self._preview_lucru = None
		self._preview_rezultat = None
		self._preview_ales = None
		self._preview_mislit = None
		self._decodeaza = None
		self._pixmap = {}
		try:
			d = getDesktop(0).size()
			self._rezolutie = galerie.resolution(d.width(), d.height())
		except Exception:
			self._rezolutie = galerie.resolution()
		self["loc"] = Label("")
		self["ajutor"] = Label(_("Stânga / Dreapta: unde apare. Sus / Jos: alege sigla. "
			"OK: pune sigla. EXIT: înapoi."))
		self["lista"] = MenuList([])
		self["poza"] = Pixmap()
		self["fara_poza"] = Label(_("Se încarcă galeria..."))
		self["autor"] = Label("")
		self["stare"] = Label("")
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
			"ok": self.alege, "green": self.alege,
			"cancel": self.close, "red": self.close,
			"left": lambda: self.schimbaLoc(-1),
			"right": lambda: self.schimbaLoc(1),
			"up": self["lista"].up, "down": self["lista"].down,
			"upRepeated": self["lista"].up, "downRepeated": self["lista"].down,
			"yellow": self.reincarca,
		}, -1)
		self._incarcator = ePicLoad()
		try:
			self._incarcator.PictureData.get().append(self._pozaGata)
		except AttributeError:
			self._legatura_poza = self._incarcator.PictureData.connect(self._pozaGata)
		self._ceas = eTimer()
		try:
			self._ceas.callback.append(self._bate)
		except AttributeError:
			self._legatura_ceas = self._ceas.timeout.connect(self._bate)
		self["lista"].onSelectionChanged.append(self._selectat)
		self.onLayoutFinish.append(self._porneste)
		self.onClose.append(self._inchide)

	def _porneste(self):
		m = self["poza"].instance.size()
		self._incarcator.setPara((m.width(), m.height(), 1, 1, False, 1, "#00000000"))
		self._lista()
		self._ceas.start(150, False)
		self.reincarca()

	def _inchide(self):
		self._inchis = True
		self._ceas.stop()

	def schimbaLoc(self, pas):
		if self._lucrare:
			return
		self._rol = (self._rol + pas) % len(self._roluri)
		self._lista()

	def _lista(self):
		rol = self._roluri[self._rol]
		self["loc"].setText("<  %s  >   |   %s" % (numeRol(rol), self._rezolutie))
		self._randuri = [(i.get("title", i["id"]), i["id"], i)
			for i in self._toate
			if i.get("variants", {}).get(self._rezolutie, {}).get(rol)]
		self._randuri.extend([
			(_("Pune înapoi sigla HD Satelit"), "@restore", {}),
			(_("Reîncarcă galeria"), "@refresh", {}),
		])
		self["lista"].setList([r[0] for r in self._randuri])
		self["lista"].moveToIndex(0)
		self._selectat()

	def _curent(self):
		k = self["lista"].getSelectionIndex()
		return self._randuri[k] if 0 <= k < len(self._randuri) else None

	def _selectat(self):
		if self._inchis:
			return
		rand = self._curent()
		self._preview_ales = rand[1] if rand and not rand[1].startswith("@") else None
		self._preview_mislit = None
		self["poza"].hide()
		self["fara_poza"].show()
		self["autor"].setText("")
		if self._preview_ales:
			self["autor"].setText(_("Autor: %s") % rand[2].get("author", ""))
			self["fara_poza"].setText(_("Se încarcă previzualizarea..."))
			if self._preview_ales in self._pixmap:
				self._arataPixmap(self._pixmap[self._preview_ales])
		elif rand and rand[1] == "@restore":
			self["fara_poza"].setText(_("Sigla HD Satelit\n\nOK: o pune înapoi pentru locul ales."))
		else:
			self["fara_poza"].setText(_("OK: citește din nou galeria de pe internet."))

	def _lucreaza(self, fel, functie, mesaj):
		if self._lucrare:
			self["stare"].setText(_("Se lucrează. Așteaptă câteva clipe."))
			return
		self._lucrare = fel
		self["stare"].setText(mesaj)
		def fir():
			try:
				rezultat = functie()
			except Exception:
				rezultat = {"ok": False, "message": _("Nu am putut termina. Încearcă din nou.")}
			self._rezultat = (fel, rezultat)
		t = threading.Thread(target=fir)
		t.daemon = True
		t.start()

	def reincarca(self):
		def citeste():
			r = galerie.catalog()
			r["available_roles"] = galerie.status().get("available_roles", ["backdrop", "radio"])
			return r
		self._lucreaza("catalog", citeste, _("Se încarcă galeria de pe internet..."))

	def alege(self):
		rand = self._curent()
		if not rand:
			return
		if rand[1] == "@refresh":
			self.reincarca()
		elif rand[1] == "@restore":
			rol = self._roluri[self._rol]
			self._lucreaza("restore", lambda: galerie.restore(rol),
				_("Se pune înapoi sigla HD Satelit..."))
		else:
			ident, rol, rez = rand[1], self._roluri[self._rol], self._rezolutie
			self._lucreaza("install", lambda: galerie.install(ident, rol, rez),
				_("Se descarcă și se pune sigla. Așteaptă câteva clipe..."))

	def _bate(self):
		if self._inchis:
			return
		if self._rezultat is not None:
			fel, rezultat = self._rezultat
			self._rezultat = None
			self._lucrare = None
			if fel == "catalog":
				rol = self._roluri[self._rol]
				self._roluri = [r for r in ROLURI if r in rezultat.get("available_roles", self._roluri)]
				self._roluri = self._roluri or ["backdrop"]
				self._rol = self._roluri.index(rol) if rol in self._roluri else 0
				if rezultat.get("ok"):
					self._toate = rezultat.get("items", [])
					self._lista()
					mesaj = _("Alege o siglă și apasă OK.") if len(self._randuri) > 2 else \
						_("Nu sunt încă sigle pentru locul ales. Poți pune înapoi sigla HD Satelit.")
					if rezultat.get("message"):
						mesaj = rezultat["message"]
				else:
					self._lista()
					mesaj = rezultat.get("message") or _("Galeria nu este disponibilă. Verifică internetul și reîncearcă.")
			else:
				mesaj = rezultat.get("message") or (_("Sigla a fost pusă.") if rezultat.get("ok")
					else _("Sigla nu a fost schimbată. Încearcă din nou."))
			self["stare"].setText(mesaj)
		if self._preview_rezultat is not None:
			ident, rezultat = self._preview_rezultat
			self._preview_rezultat = None
			self._preview_lucru = None
			if ident == self._preview_ales:
				if rezultat.get("ok"):
					self._decodeaza = ident
					if self._incarcator.startDecode(rezultat["path"]) != 0:
						self._decodeaza = None
						self._preview_mislit = ident
						self["fara_poza"].setText(_("Previzualizarea nu poate fi citită."))
				else:
					self["fara_poza"].setText(_("Previzualizarea nu este disponibilă.\nPoți încerca din nou alegând sigla."))
					self._preview_mislit = ident
		ident = self._preview_ales
		if (ident and ident != self._preview_mislit and ident not in self._pixmap
				and not self._preview_lucru and not self._decodeaza):
			self._preview_lucru = ident
			def fir():
				try:
					rezultat = galerie.preview(ident)
				except Exception:
					rezultat = {"ok": False}
				self._preview_rezultat = (ident, rezultat)
			t = threading.Thread(target=fir)
			t.daemon = True
			t.start()

	def _pozaGata(self, info=""):
		ident, self._decodeaza = self._decodeaza, None
		if self._inchis:
			return
		ptr = self._incarcator.getData()
		if ptr is not None and ident:
			if len(self._pixmap) >= 3:
				self._pixmap.clear()
			self._pixmap[ident] = ptr
			if ident == self._preview_ales:
				self._arataPixmap(ptr)
		elif ident == self._preview_ales:
			self["fara_poza"].setText(_("Previzualizarea nu poate fi citită."))
			self._preview_mislit = ident

	def _arataPixmap(self, ptr):
		self["poza"].instance.setPixmap(ptr)
		self["poza"].show()
		self["fara_poza"].hide()
