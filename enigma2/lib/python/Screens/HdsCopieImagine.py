# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCopieImagine: ecranul „Copia completă a imaginii” (Meniu > Setări > Software & Firmware, langa „Copia setărilor”).
# Logica e in Components/HdsCopieImagine.py, aceeasi pentru pagina web /copie-imagine (HdsWebControl/copie_imagine_web.py).
#
# Cat mai putini pasi: stickul cu cel mai mult loc e ales singur, OK (sau VERDE) pe „Fă copia acum” o porneste, fara
# intrebari (copia numai citeste de pe receptor). Copia merge pe firul ei: pasul, procentul si timpul ramas se vad aici
# si in web; EXIT inchide ecranul si copia continua (la sfarsit un mesaj pe televizor), GALBEN o opreste. Copia se pune
# inapoi cu „Imagine nouă de pe stick”, ca orice imagine de pe site.
#
# Skinul: cel de rezerva al scanerelor (Screens/ScanerCablu.skin_rezerva), pe orice tema, ca HdsCopieSetariScreen.

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Screens.Screen import Screen

from Components import HdsCopieImagine as C
from Components.HdsCursorLista import pune_randurile

COTE = {"eticheta": 480}


def _nimic():
	pass


class HdsCopieImagineScreen(Screen):
	"""Randurile: „Fă copia acum”, „Locul copiei”, „Caută din nou”."""

	def __init__(self, session):
		Screen.__init__(self, session)
		from Screens.ScanerCablu import (skin_rezerva, culoare_valoare, _culoare_skin, fonturi_texte, potriveste_textul,
			TASTE_RIDICATE)
		self.skin = skin_rezerva("HdsCopieImagineScreen", COTE)
		self._fonturi = fonturi_texte("HdsCopieImagineScreen")
		self._potriveste = potriveste_textul
		self._culoare = culoare_valoare()
		self._culoare_stinsa = _culoare_skin("hdsLabel")
		self._culoare_nota = _culoare_skin("hdsAmber")
		if self._culoare_stinsa is None:
			self._culoare_stinsa = 0x8A93A6
		if self._culoare_nota is None:
			self._culoare_nota = 0xF5B83D
		self.suport, self.motiv = C.suport()
		self.medii = []
		self.id_mediu = None
		self._inchis = False
		self._mesaj = ""
		self._semnal_medii = None
		self["lista"] = List([], enableWrapAround=True)
		self["preview"] = Label("")
		self["stare"] = Label("")
		self["key_red"] = StaticText(_("Înapoi"))
		self["key_green"] = StaticText("")
		self["key_yellow"] = StaticText("")
		self["key_blue"] = StaticText("")
		actiuni = {
			"ok": self.ok,
			"cancel": self.close,
			"red": self.close,
			"green": self.faCopia,
			"yellow": self.opreste,
			"up": self.sus,
			"down": self.jos,
			"left": self.stanga,
			"right": self.dreapta,
			"upRepeated": self.sus,
			"downRepeated": self.jos,
			"leftRepeated": self.stanga,
			"rightRepeated": self.dreapta,
		}
		actiuni.update((nume, _nimic) for nume in TASTE_RIDICATE)
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], actiuni, -1)
		self.setTitle(_("Copia completă a imaginii"))
		from enigma import eTimer
		self._ceas = eTimer()
		try:
			self._legatura = self._ceas.timeout.connect(self._verifica)
		except AttributeError:
			self._ceas.callback.append(self._verifica)
		try:
			from Components.Harddisk import harddiskmanager
			self._semnal_medii = harddiskmanager.on_partition_list_change
			self._semnal_medii.append(self._mediiSchimbate)
		except (ImportError, AttributeError):
			pass
		self.onClose.append(self._laInchidere)
		self.onLayoutFinish.append(self._laInceput)
		C.ecrane.append(self)

	# ---- starea ----
	def _laInceput(self):
		self.cautaDinNou()
		if C.ocupat():
			self._ceas.start(1000, False)

	def cautaDinNou(self):
		if self._inchis:
			return
		try:
			self.medii = C.medii() if self.suport else []
		except Exception as eroare:
			print("[HdsCopieImagine] medii: %r" % (eroare,))
			self.medii = []
		if not any(m["id"] == self.id_mediu for m in self.medii):
			implicit = C.mediuImplicit(self.medii)
			self.id_mediu = implicit["id"] if implicit else None
		self._arata()

	def _mediiSchimbate(self, *args):
		if not self._inchis and not C.ocupat():
			self.cautaDinNou()

	def _verifica(self):
		if self._inchis:
			return
		if not C.ocupat():
			self._ceas.stop()
			r = C.stare()["rezultat"]
			if r is not None:
				self._mesaj = r["mesaj"]
			self.cautaDinNou()
			return
		self._arata()

	def mediu(self):
		for m in self.medii:
			if m["id"] == self.id_mediu:
				return m
		return None

	# ---- desenul ----
	def _randuri(self):
		m = self.mediu()
		if C.ocupat():
			fa = (_("Fă copia acum"), "fa", _("se face…"), self._culoare_stinsa)
		else:
			fa = (_("Fă copia acum"), "fa", "", self._culoare if m is not None else self._culoare_stinsa)
		if not self.suport:
			unde, culoare = _("nu se poate pe acest receptor"), self._culoare_nota
		elif m is not None:
			unde, culoare = m["nume"], self._culoare
		else:
			unde, culoare = _("niciun stick sau disc USB"), self._culoare_nota
		return [fa, (_("Locul copiei"), "mediu", unde, culoare), (_("Caută din nou"), "cauta", "", self._culoare)]

	def _textPreview(self):
		if not self.suport:
			return C.textSuport(self.motiv)
		st = C.stare()
		if st["lucreaza"]:
			if st["oprit"]:
				return _("Copia se oprește…")
			return st["text"] + "\n" + _("Nu scoate stickul până nu scrie „Copia e gata”. Poți ieși din ecran: copia "
				"continuă, iar la sfârșit apare un mesaj.")
		if self._mesaj:
			return self._mesaj
		despre = C.textDespre() + "\n" + C.textParole() + "\n"
		if self.mediu() is None:
			return despre + _("Bagă un stick sau un disc USB în receptor. Lista se reface singură.")
		return despre + _("Copia merge pe %s.") % self.mediu()["nume"]

	def _ajutor(self):
		if C.ocupat():
			return _("GALBEN: oprește copia. EXIT: ieși, copia continuă.")
		cheie = self._cheie()
		if cheie == "fa":
			return _("OK sau VERDE: copia se face acum pe locul ales la „Locul copiei”.")
		if cheie == "mediu":
			return _("Schimbă cu stânga, dreapta sau OK.") if len(self.medii) > 1 else _("Numai acest loc e găsit.")
		return _("Caută din nou stickurile și discurile.")

	def _arata(self, stare=None):
		pune_randurile(self["lista"], self._randuri())
		self["preview"].setText(self._textPreview())
		self["stare"].setText(stare or self._ajutor())
		lucreaza = C.ocupat()
		self["key_green"].setText(_("Fă copia") if self.mediu() is not None and not lucreaza else "")
		self["key_yellow"].setText(_("Oprește copia") if lucreaza else "")
		for n in ("preview", "stare"):
			self._potriveste(self[n], *self._fonturi[n])

	def _cheie(self):
		curent = self["lista"].getCurrent()
		return curent[1] if curent else None

	# ---- tastele ----
	def sus(self):
		self["lista"].selectPrevious()
		self._arata()

	def jos(self):
		self["lista"].selectNext()
		self._arata()

	def _schimba(self, pas):
		if self._cheie() == "mediu" and self.medii and not C.ocupat():
			ids = [m["id"] for m in self.medii]
			i = ids.index(self.id_mediu) if self.id_mediu in ids else -1
			self.id_mediu = ids[(i + pas) % len(ids)]
			self._mesaj = ""
			self._arata()

	def stanga(self):
		self._schimba(-1)

	def dreapta(self):
		self._schimba(1)

	def ok(self):
		cheie = self._cheie()
		if cheie == "fa":
			self.faCopia()
		elif cheie == "mediu":
			self._schimba(1)
		elif cheie == "cauta":
			self._mesaj = ""
			self.cautaDinNou()

	def faCopia(self):
		if C.ocupat() or not self.suport:
			return
		if self.mediu() is None:
			self.cautaDinNou()
		m = self.mediu()
		if m is None:
			self._arata(_("Bagă un stick sau un disc USB și apasă din nou „Fă copia”."))
			return
		try:
			from Components.config import configfile
			configfile.save()  # setarile de acum intra in copie
		except Exception as eroare:
			print("[HdsCopieImagine] setarile: %r" % (eroare,))
		self._mesaj = ""
		pornit, mesaj = C.porneste(m["id"])
		if not pornit:
			self._mesaj = mesaj
		self._arata()
		if pornit:
			self._ceas.start(1000, False)

	def opreste(self):
		if C.opreste():
			self._arata()

	def _laInchidere(self):
		self._inchis = True
		self._ceas.stop()
		if self in C.ecrane:
			C.ecrane.remove(self)
		if self._semnal_medii is not None and self._mediiSchimbate in self._semnal_medii:
			self._semnal_medii.remove(self._mediiSchimbate)


def main(session, **kwargs):
	session.open(HdsCopieImagineScreen)
