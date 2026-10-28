# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistenta.py: ecranele „Ajutor de la distanta" pe televizor (Meniu > Setari > Retea si internet > Asistenta de
# la distanta; meniul testerilor poate deschide acelasi ecran). Logica e in Components/HdsAsistenta.py; aceleasi stari,
# acelasi text de informare si acelasi jurnal in interfata web (/asistenta).
#
# Consimtamantul, de fiecare data (fara „tine minte"):
# - HdsAsistenta: intrarea. Cat functia e oprita arata informarea intreaga (A.textInformare(): ce facem, ce date ajung
#   la noi, cat le pastram, cum opresti, varsta) si Verde „Pornește". Cat e pornita arata codul (cat asteapta
#   aprobarea), timpul ramas si jurnalul in timp real, cu Rosu „Oprește". Deschis la o cerere din pagina web (browserul
#   omului, conectat cu codul de pe televizor), spune asta sus si se inchide singur dupa 5 minute fara Verde.
# - HdsAsistentaAlege: alegerea duratei (nivelul e „Citire și probe", fix in versiunea 1), apoi confirmarea (implicit
#   „Nu"); abia dupa „Da" porneste sesiunea. Semnul de pe ecran si pornirea insasi le face Screens/HdsAsistentaSemn.py.

from enigma import eTimer, getDesktop

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components.config import ConfigSelection, getConfigListEntry
from Components import HdsAsistenta as A
from Screens import HdsAsistentaSemn as Semn

ROSU = "#9f1313"
VERDE = "#1f771f"
CERERE_WEB_S = 5 * 60


def _skin(latime, inaltime):
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))

	taste = []
	lat = x(360)
	for i, (nume, culoare) in enumerate((("key_red", ROSU), ("key_green", VERDE))):
		taste.append('<widget source="%s" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" '
			'halign="center" valign="center" backgroundColor="%s" foregroundColor="#00ffffff" transparent="0" '
			'zPosition="2" />' % (nume, x(40) + i * (lat + x(30)), y(960), lat, y(60), y(26), culoare))
	return """
	<screen name="HdsAsistenta" position="center,center" size="%d,%d" title="Asistență de la distanță">
		<widget source="antet" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" halign="left" valign="center" foregroundColor="#00f5b83d" transparent="1" />
		<widget source="cod" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="center" foregroundColor="#00ffffff" transparent="1" />
		<widget name="text" position="%d,%d" size="%d,%d" font="Regular;%d" />
		<widget source="ajutor" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" halign="right" valign="center" foregroundColor="#00a0a8b0" transparent="1" />
		%s
	</screen>""" % (
		x(1400), y(1040),
		x(40), y(30), x(1320), y(56), y(30),
		x(40), y(96), x(1320), y(90), y(64),
		x(40), y(200), x(1320), y(740), y(24),
		x(820), y(960), x(540), y(60), y(20),
		"\n\t\t".join(taste))


class HdsAsistenta(Screen):
	def __init__(self, session, din_web=None):
		marime = getDesktop(0).size()
		self.skin = _skin(marime.width(), marime.height())
		Screen.__init__(self, session)
		self.setTitle(_("Asistență de la distanță"))
		# din_web: minutele alese in pagina web (cererea de pornire din browserul omului); None = deschis din meniu
		self.din_web = int(din_web) if din_web in A.DURATE_MIN else None
		self["antet"] = StaticText("")
		self["cod"] = StaticText("")
		self["text"] = ScrollLabel("")
		self["ajutor"] = StaticText("")
		self["key_red"] = StaticText("")
		self["key_green"] = StaticText("")
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"cancel": self.close,
			"red": self._rosu,
			"green": self._verde,
			"up": self["text"].pageUp,
			"down": self["text"].pageDown,
		}, -2)
		self._text = None
		self.ceas = eTimer()
		self.ceas.callback.append(self.reface)
		self.onClose.append(self.ceas.stop)
		self.onClose.append(lambda: A.scoateObservator(self.reface))
		A.adaugaObservator(self.reface)
		self.ceasWeb = None
		if self.din_web is not None:
			# o cerere din web neconfirmata in 5 minute moare (ecranul se inchide singur cat functia e oprita)
			self.ceasWeb = eTimer()
			self.ceasWeb.callback.append(self._cerereWebExpirata)
			self.onClose.append(self.ceasWeb.stop)
		self.onLayoutFinish.append(self._porneste)

	def _porneste(self):
		self.ceas.start(1000, False)
		if self.ceasWeb is not None:
			self.ceasWeb.start(CERERE_WEB_S * 1000, True)
		self.reface()

	def _cerereWebExpirata(self):
		if A.stare().get("stare") == A.OPRIT:
			self.close()

	def _puneText(self, text):
		# ScrollLabel se intoarce sus la fiecare setText: textul se pune numai cand se schimba
		if text != self._text:
			self._text = text
			self["text"].setText(text)

	def reface(self):
		s = A.stare()
		stare = s.get("stare")
		activa = stare in (A.INREGISTRARE, A.ASTEAPTA, A.CONECTAT, A.SE_OPRESTE)
		if not s.get("disponibil"):
			self["antet"].setText(_("Funcția nu e disponibilă pe această imagine."))
			self["cod"].setText("")
			self._puneText("")
			self["ajutor"].setText("")
			self["key_green"].setText("")
			self["key_red"].setText(_("Înapoi"))
			return
		if not activa:
			if self.din_web is not None:
				self["antet"].setText(_("Ai cerut pornirea din pagina web. Citește, apoi apasă Verde dacă vrei."))
			else:
				self["antet"].setText(_("Oprită. O pornești tu, dacă vrei să ne ajuți."))
			self["cod"].setText("")
			self._puneText(A.textInformare())
			self["ajutor"].setText(_("Sus/Jos: tot textul"))
			self["key_green"].setText(_("Pornește"))
			self["key_red"].setText(_("Înapoi"))
			return
		if stare == A.ASTEAPTA and s.get("cod"):
			self["antet"].setText(_("Spune-ne acest cod. Nu îl da altcuiva.") + "  " + self._ramas(s))
			self["cod"].setText(_cod(s["cod"]))
		elif stare == A.CONECTAT:
			self["antet"].setText(_("Conectat.") + "  " + self._ramas(s))
			self["cod"].setText("")
		else:
			self["antet"].setText(_("Se pregătește...") + "  " + self._ramas(s))
			self["cod"].setText("")
		self._puneText("\n".join(s.get("jurnal") or []))
		self["ajutor"].setText("")
		self["key_green"].setText("")
		self["key_red"].setText(_("Oprește"))

	def _ramas(self, s):
		return _("mai sunt") + " " + Semn._hms(s.get("ramas_s", 0))

	def _verde(self):
		s = A.stare()
		if s.get("disponibil") and s.get("stare") == A.OPRIT:
			self.session.openWithCallback(self._dupaAlege, HdsAsistentaAlege,
				minute=self.din_web if self.din_web is not None else A.DURATA_IMPLICITA_MIN,
				de_la="web" if self.din_web is not None else "televizor")

	def _dupaAlege(self, pornita=None):
		if pornita:
			# dupa pornire ecranul ramane deschis: arata codul mare
			self.din_web = None
			if self.ceasWeb is not None:
				self.ceasWeb.stop()
			self.reface()

	def _rosu(self):
		s = A.stare()
		if s.get("stare") in (A.INREGISTRARE, A.ASTEAPTA, A.CONECTAT):
			self.session.openWithCallback(self._opreste, MessageBox,
				_("Oprești asistența? Cheia se șterge și legătura se închide."), MessageBox.TYPE_YESNO, default=True)
		else:
			self.close()

	def _opreste(self, da):
		if da:
			A.opreste("de om")


def _cod(cod):
	cod = str(cod or "")
	return " ".join(cod[i:i + 2] for i in range(0, len(cod), 2))


class HdsAsistentaAlege(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsAsistentaAlege" position="center,center" size="1000,560" title="Pornește asistența">
		<widget name="config" position="30,30" size="940,220" scrollbarMode="showOnDemand" />
		<widget source="text" render="Label" position="30,270" size="940,200" font="Regular;22" />
		<widget source="key_red" render="Label" position="30,500" size="450,50" font="Regular;22" halign="center" valign="center" backgroundColor="#9f1313" foregroundColor="#00ffffff" />
		<widget source="key_green" render="Label" position="520,500" size="450,50" font="Regular;22" halign="center" valign="center" backgroundColor="#1f771f" foregroundColor="#00ffffff" />
	</screen>"""

	def __init__(self, session, minute=None, de_la="televizor"):
		Screen.__init__(self, session)
		self.setTitle(_("Pornește asistența"))
		self.de_la = de_la if de_la in ("televizor", "web") else "televizor"
		implicit = minute if minute in A.DURATE_MIN else A.DURATA_IMPLICITA_MIN
		alegeri = [(str(m), A.textDurata(m)) for m in A.DURATE_MIN]
		self.durata = ConfigSelection(default=str(implicit), choices=alegeri)
		lista = [getConfigListEntry(_("Cât timp"), self.durata)]
		ConfigListScreen.__init__(self, lista, session=session)
		self["text"] = StaticText(_("Nivel: Citire și probe (putem rula numai operații dintr-o listă fixă, în "
			"principal citiri; o captură arată numai meniurile, nu imaginea canalului). Poți opri oricând."))
		self["key_red"] = StaticText(_("Înapoi"))
		self["key_green"] = StaticText(_("Pornește"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close,
			"red": self.close,
			"green": self._porneste,
		}, -2)

	def _porneste(self):
		durata = int(self.durata.value)
		fraza = _("Dai acces la distanță pentru %s, nivel „Citire și probe”. Pornind, confirmi că ai cel puțin 16 "
			"ani sau acordul unui părinte. Poți opri oricând. Pornești?") % A.textDurata(durata)
		self.session.openWithCallback(lambda da: self._confirmat(da, durata), MessageBox, fraza,
			MessageBox.TYPE_YESNO, default=False)

	def _confirmat(self, da, durata):
		if not da:
			return
		reusit, mesaj = Semn.porneste(self.session, nivel="A", durata_min=durata, de_la=self.de_la)
		if not reusit:
			self.session.open(MessageBox, mesaj, MessageBox.TYPE_INFO, timeout=6)
		self.close(bool(reusit))
