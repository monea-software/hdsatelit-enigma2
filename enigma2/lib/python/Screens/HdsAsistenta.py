# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistenta.py: ecranele "Ajutor de la distanta" pe receptor, numai pentru beta testeri: se deschid din meniul
# testerului (Meniu > Setari > Beta tester > Cere ajutor de la distanta). Logica e in Components/HdsAsistenta.py;
# aceleasi stari, acelasi text de informare si acelasi jurnal in interfata web (/asistenta).
#
# Consimtamantul, de fiecare data (fara "tine minte"):
# - HdsAsistenta: intrarea. Deschisa de cineva care nu e inscris in programul de beta testeri (si fara o sesiune
#   pornita), arata numai fraza "Asistenta de la distanta e pentru beta testeri." si Verde "Devino beta tester"
#   (acordul). Cat functia e oprita arata informarea intreaga (A.textInformare(): ce facem, ce date ajung la noi, cat le
#   pastram, cum opresti, varsta) si Verde "Pornește". Cat e pornita arata codul (cat asteapta aprobarea), timpul ramas
#   si jurnalul in timp real, cu Rosu "Oprește"; tasta verde nu are atunci ce face si nu apare. Deschis la o cerere din
#   pagina web (browserul omului, conectat cu codul de pe receptor), spune asta sus si se inchide singur dupa 5 minute
#   fara Verde. Cat ecranul e deschis, banda de semn de sus (Screens/HdsAsistentaSemn.py) se ascunde: ecranul arata el
#   starea si timpul.
# - HdsAsistentaAlege: alegerea duratei (nivelul e "Citire și probe", fix in versiunea 1), apoi confirmarea (implicit
#   "Nu"); abia dupa "Da" porneste sesiunea. Semnul de pe ecran si pornirea insasi le face Screens/HdsAsistentaSemn.py.
#
# Skinul: ecranele sunt in skinul HDSatelit (HDSatelit/skin.xml, cadrul HdsCadru1776); skinul de aici e rezerva pentru
# alt skin ales, cu aceeasi geometrie (CORP_*); in skin.xml formele se numesc HdsAjutorDistanta si
# HdsAjutorDistantaAlege (skinName). Tastele lui HdsAsistenta sunt StaticText (liniuta si textul se ascund cand textul
# e gol): in skin.xml legenda lor o arata cadrul, in skinul de rezerva LEGENDA_ASISTENTA.

import re

from enigma import eTimer

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.ConfigList import ConfigListScreen
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components.config import ConfigSelection, getConfigListEntry
from Components import HdsAsistenta as A
from Screens import HdsAsistentaSemn as Semn

CERERE_WEB_S = 5 * 60


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la folosire."""
	return text


TEXT_NUMAI_TESTERI = N_("Asistența de la distanță e pentru beta testeri.")

# culorile skinului HDSatelit (rolurile din skin.xml), scrise ca valori pentru skinul de rezerva
CULORI_SKIN = {
	"hdsPanelDialog": "#10162A",
	"hdsCell": "#282D3F",
	"hdsDivider": "#3A4255",
	"hdsText": "#F2F4F8",
	"white": "#FFFFFF",
	"hdsText2": "#C9D2E3",
	"hdsLabel": "#AEB9CC",
	"hdsBrand": "#374EA1",
	"hdsAmber": "#F5B83D",
	"key_red": "#E5484D",
	"key_green": "#46B06A",
}

# corpul ecranului, acelasi in skin.xml (in cadrul HdsCadru1776) si in skinul de rezerva: starea sus, codul mare, textul
# (informarea sau jurnalul) si ajutorul din dreapta jos
CORP_ASISTENTA = """
		<widget source="antet" render="Label" position="32,104" size="1712,56" font="HdsBold;32" foregroundColor="hdsAmber" backgroundColor="hdsPanelDialog" transparent="1" valign="center" noWrap="1" zPosition="2" />
		<widget source="cod" render="Label" position="32,168" size="1712,112" font="HdsBold;96" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" halign="center" valign="center" noWrap="1" zPosition="2" />
		<widget name="text" position="32,288" size="1712,624" font="HdsRegular;26" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" zPosition="2" />
		<widget source="ajutor" render="Label" position="904,936" size="840,48" font="HdsCond;26" foregroundColor="hdsLabel" backgroundColor="hdsPanelDialog" transparent="1" halign="right" valign="center" noWrap="1" zPosition="1" />"""

# legenda celor doua taste (se ascunde cand tasta n-are text), numai in skinul de rezerva: in skin.xml o arata cadrul
# HdsCadru1776 (si pentru tastele StaticText), iar o a doua legenda ar iesi peste ea in tema Pro
LEGENDA_ASISTENTA = """
		<widget source="key_red" render="FixedLabel" conditional="key_red" objectTypes="key_red,StaticText" position="32,944" size="6,32" backgroundColor="key_red" zPosition="1">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_red" render="Label" conditional="key_red" objectTypes="key_red,StaticText" position="48,936" size="404,48" font="HdsCond;28" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" valign="center" noWrap="1" zPosition="1" />
		<widget source="key_green" render="FixedLabel" conditional="key_green" objectTypes="key_green,StaticText" position="460,944" size="6,32" backgroundColor="key_green" zPosition="1">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_green" render="Label" conditional="key_green" objectTypes="key_green,StaticText" position="476,936" size="404,48" font="HdsCond;28" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" valign="center" noWrap="1" zPosition="1" />"""

CORP_ALEGE = """
		<widget name="config" position="32,104" size="1712,180" itemHeight="60" font="HdsRegular;30" secondfont="HdsBold;28" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" backgroundColorSelected="hdsBrand" foregroundColorSelected="white" transparent="1" scrollbarMode="showOnDemand" zPosition="2" />
		<eLabel position="32,300" size="1712,1" backgroundColor="hdsDivider" zPosition="1" />
		<widget source="text" render="Label" position="32,316" size="1712,300" font="HdsRegular;28" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" valign="top" zPosition="2" />"""


def _rezerva(nume, titlu, corp, legenda=""):
	"""Skinul de rezerva (alt skin decat HDSatelit): acelasi corp, culorile ca valori, fonturile Regular/Bold."""
	corp = re.sub(r'font="Hds(Bold|Regular|Cond);', lambda m: 'font="%s;' % ("Bold" if m.group(1) == "Bold" else
		"Regular"), corp)
	# numai valorile culorilor (source="key_red" ramane numele sursei)
	corp = re.sub(r'((?:background|foreground)Color(?:Selected)?)="([A-Za-z_0-9]+)"', lambda m: '%s="%s"' % (
		m.group(1), CULORI_SKIN.get(m.group(2), m.group(2))), corp)
	return """
	<screen name="%s" resolution="1920,1080" position="center,center" size="1776,1000" backgroundColor="#10162A" title="%s">
		<eLabel position="32,88" size="1712,1" backgroundColor="#3A4255" zPosition="1" />
		<eLabel position="32,924" size="1712,1" backgroundColor="#3A4255" zPosition="1" />%s%s
	</screen>""" % (nume, titlu, corp, legenda)


LEGENDA_ALEGE = """
		<eLabel position="32,944" size="6,32" backgroundColor="#E5484D" zPosition="1" />
		<widget name="key_red" position="48,936" size="404,48" font="Regular;28" foregroundColor="#F2F4F8" transparent="1" valign="center" noWrap="1" zPosition="1" />
		<eLabel position="460,944" size="6,32" backgroundColor="#46B06A" zPosition="1" />
		<widget name="key_green" position="476,936" size="404,48" font="Regular;28" foregroundColor="#F2F4F8" transparent="1" valign="center" noWrap="1" zPosition="1" />"""


def _nimic(*_a):
	pass


def _inscris():
	"""Omul e beta tester? (Components.HdsBetaTester; fara el, nimeni nu e.)"""
	try:
		from Components import HdsBetaTester as B
		return bool(B.inscris())
	except Exception as e:
		print("[HdsAsistenta] programul de testeri: %s" % e)
		return False


class HdsAsistenta(Screen):
	skin = _rezerva("HdsAsistenta", "Asistență de la distanță", CORP_ASISTENTA + LEGENDA_ASISTENTA)

	def __init__(self, session, din_web=None):
		Screen.__init__(self, session)
		# numele formei din skinul HDSatelit (skin.xml nu poate avea numele clasei: verificarea cuvintelor skinului)
		self.skinName = "HdsAjutorDistanta"
		self.setTitle(_("Asistență de la distanță"))
		# din_web: minutele alese in pagina web (cererea de pornire din browserul omului); None = deschis din meniu
		self.din_web = int(din_web) if din_web in A.DURATE_MIN else None
		self["antet"] = StaticText("")
		self["cod"] = StaticText("")
		self["text"] = ScrollLabel("")
		self["ajutor"] = StaticText("")
		self["key_red"] = StaticText("")
		self["key_green"] = StaticText("")
		actiuni = {
			"cancel": self.close,
			"red": self._rosu,
			"green": self._verde,
			"yellow": _nimic,
			"blue": _nimic,
		}
		# toate actiunile hartii de directii legate (fara "unknown action" in jurnal); Sus/Jos deruleaza textul
		for d, f in (("up", self["text"].pageUp), ("down", self["text"].pageDown), ("left", _nimic), ("right", _nimic)):
			actiuni[d] = f
			actiuni[d + "Repeated"] = f
			actiuni[d + "Up"] = _nimic
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], actiuni, -2)
		self._text = None
		self._tester = True
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
		self._tester = activa or _inscris()
		if not self._tester:
			# numai beta testerii pot da acces la receptor: fraza si drumul spre acord, nimic altceva
			self["antet"].setText(_(TEXT_NUMAI_TESTERI))
			self["cod"].setText("")
			self._puneText("")
			self["ajutor"].setText("")
			self["key_green"].setText(_("Devino beta tester"))
			self["key_red"].setText(_("Înapoi"))
			return
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
		# cat asistenta merge, Verde nu are ce face: fara text, legenda ei nu apare
		self["key_green"].setText("")
		self["key_red"].setText(_("Oprește"))

	def _ramas(self, s):
		return _("mai sunt") + " " + Semn._hms(s.get("ramas_s", 0))

	def _verde(self):
		if not self._tester:
			from Screens.HdsBetaTester import HdsBetaAcord
			self.session.openWithCallback(lambda *r: self.reface(), HdsBetaAcord)
			return
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
	skin = _rezerva("HdsAsistentaAlege", "Pornește asistența", CORP_ALEGE, LEGENDA_ALEGE)

	def __init__(self, session, minute=None, de_la="televizor"):
		Screen.__init__(self, session)
		self.skinName = "HdsAjutorDistantaAlege"
		self.setTitle(_("Pornește asistența"))
		self.de_la = de_la if de_la in ("televizor", "web") else "televizor"
		implicit = minute if minute in A.DURATE_MIN else A.DURATA_IMPLICITA_MIN
		alegeri = [(str(m), A.textDurata(m)) for m in A.DURATE_MIN]
		self.durata = ConfigSelection(default=str(implicit), choices=alegeri)
		lista = [getConfigListEntry(_("Cât timp"), self.durata)]
		ConfigListScreen.__init__(self, lista, session=session)
		self["text"] = StaticText(_("Nivel: Citire și probe (putem rula numai operații dintr-o listă fixă, în "
			"principal citiri; o captură arată numai meniurile, nu imaginea canalului). Poți opri oricând."))
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Pornește"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.close,
			"red": self.close,
			"green": self._porneste,
			"yellow": _nimic,
			"blue": _nimic,
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
