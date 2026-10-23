# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCampText.py: campurile de text pe un singur rand in care se scrie numai la coada (tastatura de pe ecran, Caută
# setări, randul „Nume” din Caută canale).
#
# Cat textul incape in caseta, se deseneaza ca pana acum, cu alinierea din skin. Cand nu mai incape, se aliniaza la
# dreapta: tot randul se muta spre stanga, se taie la marginea din stanga a casetei si se vede coada lui (ce scrii
# acum); la stergere, cand incape din nou, revine la alinierea din skin. Alinierea la dreapta a unui rand mai lat decat
# caseta il muta spre stanga (eTextPara::realign, lib/gdi/font.cpp: deplasarea iese negativa), iar caseta il taie
# (eticheta: marginea widgetului; lista: dreptunghiul intrarii, lib/gui/elistboxcontent.cpp).
#
# Campurile cu cursor care se misca (caseta InputBox, setarile de text din liste) le muta nucleul, dupa litera cu
# cursorul (lib/gui/elabel.cpp, lib/gui/elistboxcontent.cpp), nu de aici.
#
# Masurarea: eLabel.calculateSize() pe o eticheta fara rupere de rand (noWrap) da latimea intregului rand. O eticheta
# cu rupere de rand nu iese niciodata din latime (randurile se rup), deci ramane cum era.

from .Label import Label

# numele din skin -> numele constantei eLabel (skin.py, "halign")
ALINIERI = {"left": "alignLeft", "center": "alignCenter", "right": "alignRight", "block": "alignBlock"}


def latimeRand(eticheta):
	"""Latimea textului de acum al unei eLabel, in pixeli; None daca nu se poate masura."""
	try:
		return int(eticheta.calculateSize().width())
	except Exception:
		return None


def preaLat(eticheta, latime=None):
	"""Textul etichetei nu incape in caseta ei (sau in `latime` pixeli)? La o eroare de masurare: False (ca pana acum)."""
	l = latimeRand(eticheta)
	if l is None:
		return False
	try:
		if latime is None:
			latime = eticheta.size().width()
		return l > int(latime)
	except Exception:
		return False


class CampText(Label):
	"""Eticheta unui camp de text pe un rand (noWrap): cat textul incape, alinierea din skin; cand nu mai incape, la
	dreapta (se vede coada). Orice setText (si cele venite din afara ecranului, de ex. textul trimis din panoul web) trece
	pe aici. getText() da textul intreg, ca la Label."""

	def __init__(self, text=""):
		self.aliniereSkin = "left"   # alinierea din skin (halign); fara ea, la stanga
		self.alinierePusa = None     # ce am pus noi pe eticheta; None = a ramas cea din skin
		Label.__init__(self, text)

	def applySkin(self, desktop, parent):
		for (atribut, valoare) in (self.skinAttributes or ()):
			if atribut == "halign" and valoare in ALINIERI:
				self.aliniereSkin = valoare
		rezultat = Label.applySkin(self, desktop, parent)
		# skinul tocmai a pus alinierea lui; un text lung de la deschidere (de ex. o adresa) se vede de la coada
		self.alinierePusa = None
		self.potriveste()
		return rezultat

	def setText(self, text):
		Label.setText(self, text)
		self.potriveste()

	def potriveste(self):
		"""Alinierea dupa latimea textului de acum; schimbata pe eticheta numai cand chiar se schimba (setHAlign
		redeseneaza eticheta)."""
		inst = getattr(self, "instance", None)
		if inst is None:
			return
		dorita = "right" if preaLat(inst) else self.aliniereSkin
		if dorita == (self.alinierePusa or self.aliniereSkin):
			return
		try:
			inst.setHAlign(getattr(inst, ALINIERI[dorita]))
		except Exception:
			return
		self.alinierePusa = dorita

	def laCoada(self):
		"""True cand se vede coada textului (textul nu incape si e aliniat la dreapta)."""
		return self.alinierePusa == "right" and self.aliniereSkin != "right"


class Masura(object):
	"""Latimea unui text intr-un font, pentru casetele desenate in liste (MultiContent), unde nu exista o eticheta de
	masurat: o eticheta ascunsa, facuta din cod in fereastra ecranului (fara nimic in skin). Ultima masurare se tine
	minte (un rand redesenat fara text nou nu masoara din nou). inchide() o scoate (la inchiderea ecranului)."""

	def __init__(self, parinte, font):
		self.eticheta = None
		self.ultima = (None, None)
		if parinte is None:
			return
		try:
			from enigma import eLabel
			e = eLabel(parinte)
			e.hide()
			e.setNoWrap(1)
			e.setFont(font)
			self.eticheta = e
		except Exception as ex:
			print("[HdsCampText] masura: %s" % ex)

	def latime(self, text):
		"""Latimea textului in pixeli, sau None."""
		if self.ultima[0] == text:
			return self.ultima[1]
		e = self.eticheta
		if e is None:
			return None
		try:
			e.setText(text)
			l = latimeRand(e)
		except Exception:
			l = None
		self.ultima = (text, l)
		return l

	def preaLat(self, text, latime):
		"""Textul nu incape in `latime` pixeli? Fara masurare: False (ca pana acum)."""
		l = self.latime(text)
		return l is not None and l > latime

	def inchide(self):
		self.eticheta = None
		self.ultima = (None, None)
