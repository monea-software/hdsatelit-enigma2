# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Panoul radio online din meniul Pro: aceleasi date si acelasi analizor ca ecranul radio si pagina /radio.
Fara retea, decodor sau analizor separat; ceasul merge numai cat meniul care are panoul este in fata.
"""
import time


def N_(text):
	return text


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def date_panou(d, RD=None):
	"""Date de afisat, pure si comune cu HdsWebControl. Nu se expune adresa fluxului."""
	if RD is None:
		from Components import HdsRadioDate as RD
	online = bool(d.get("radio") and d.get("adresa") and str(d.get("ref") or "").startswith("4097:"))
	debit = (d.get("sunet") or {}).get("debit") or 0
	aproximativ = (d.get("sunet") or {}).get("debit_masurat")
	return {"online": online, "titlu": _t(N_("Radio online")) if online else "",
		"debit": ((_t(N_("cam %d kbit/s")) if aproximativ else _t(N_("%d kbit/s"))) % debit) if debit else _t(N_("Debitul nu este disponibil")),
		"sunet": RD.text_sunet(d) if online else ""}


class PanouRadioMeniu(object):
	def __init__(self, ecran):
		from enigma import eTimer
		from Components.Label import Label
		from Components.Sources.Boolean import Boolean
		from Components.Sources.CanvasSource import CanvasSource
		self.ecran = ecran
		self.panza = None
		self.randat = False
		self.ref = None
		self.date = None
		self.citit_la = 0
		self.canvas = None
		self.activ = False
		ecran["radio_meniu_online"] = Boolean(False)
		for nume in ("titlu", "debit", "sunet", "mesaj"):
			ecran["radio_meniu_" + nume] = Label("")
		ecran["radio_meniu_bare"] = CanvasSource()
		self.ceas = eTimer()
		self.ceas.callback.append(self._pas)
		ecran.onLayoutFinish.append(self._aseaza)
		ecran.onShow.append(self._arata)
		ecran.onHide.append(self._ascunde)
		ecran.onClose.append(self._inchide)

	def _aseaza(self):
		from Components import HdsRadioDesen as DES
		e = self.ecran
		self.canvas = next((r for r in e.renderer if getattr(r, "source", None) is e["radio_meniu_bare"]
			and getattr(r, "instance", None) is not None), None)
		if self.canvas is None:
			return
		marime = self.canvas.instance.size()
		try:
			from skin import colorNames
			fond = colorNames["hdsPanelSolid"].argb() & 0xFFFFFF
		except Exception:
			fond = 0x10162A
		self.panza = DES.Panza(marime.width(), marime.height(), fel="bare", fundal=fond)
		DES.aplica(e["radio_meniu_bare"], self.panza.goleste())
		self._arata()

	def _arata(self):
		if self.canvas is None:
			return
		self.activ = True
		self.citit_la = 0
		self._pas()
		if self.activ:
			self.ceas.start(100)

	def _ascunde(self):
		self.activ = False
		self.ceas.stop()

	def _inchide(self):
		self._ascunde()
		self.ceas.callback.remove(self._pas)
		self.ecran = None

	def _vizibil(self, online):
		e = self.ecran
		if e["radio_meniu_online"].boolean != online:
			e["radio_meniu_online"].boolean = online
		for nume in ("titlu", "debit", "sunet", "mesaj"):
			(e["radio_meniu_" + nume].show if online else e["radio_meniu_" + nume].hide)()
		if self.canvas is not None:
			self.canvas.visible = online

	def _text(self, nume, text):
		eticheta = self.ecran["radio_meniu_" + nume]
		if eticheta.getText() != text:
			eticheta.setText(text)

	def _pas(self):
		if not self.activ or self.ecran is None:
			return
		try:
			self._actualizeaza()
		except Exception:
			# Nicio eroare a panoului radio nu trebuie sa strice navigarea in meniu.
			self._vizibil(False)
			self._ascunde()
			print("[HdsRadioMeniu] panoul nu se poate actualiza")

	def _actualizeaza(self):
		from Components import HdsRadioDate as RD, HdsRadioDesen as DES
		from Screens.HdsEcranRadio import legatura
		e = self.ecran
		acum = time.time()
		leg = legatura()
		if acum - self.citit_la >= 1:
			ref = RD.ref_curenta(e.session)[1]
			if not (ref.startswith("4097:") and RD.adresa_publica(ref)):
				# La un canal TV sau la radio din satelit meniul nu plateste citirea datelor postului.
				self.citit_la = acum
				self.date = self.ref = None
				if e["radio_meniu_online"].boolean or self.randat:
					DES.aplica(e["radio_meniu_bare"], self.panza.goleste())
					self.randat = False
				self._vizibil(False)
				return
			analiza = leg.analiza() if leg is not None else None
			if self.date is None or self.ref != ref:
				self.date = RD.date(e.session, 0, analiza, acum)
				self.ref = ref
			else:
				self.date = RD.rapid(self.date, e.session, analiza, acum)
			panou = date_panou(self.date, RD)
			self._vizibil(panou["online"])
			if panou["online"]:
				for nume in ("titlu", "debit", "sunet"):
					self._text(nume, panou[nume])
				if leg is not None:
					leg.cerereWeb()
			self.citit_la = acum
		if not e["radio_meniu_online"].boolean:
			return
		an = getattr(leg, "analizor", None) if leg is not None else None
		nivele = an.nivele(0.25) if an is not None else None
		if nivele:
			info = an.flux.info or {}
			DES.aplica(e["radio_meniu_bare"], self.panza.cadru(nivele, 24, acum, info.get("esantionare", 48000)))
			self._text("mesaj", "")
			self.randat = True
		else:
			if self.randat:
				DES.aplica(e["radio_meniu_bare"], self.panza.goleste())
				self.randat = False
			self._text("mesaj", RD.text_bare(leg.analiza() if leg is not None else None, "bare"))
