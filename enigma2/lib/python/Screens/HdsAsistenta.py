# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistenta.py: ecranele "Asistență de la distanță" pe receptor, pentru oricine: Meniu > Setari > Asistenta de la
# distanta (data/menu.xml). Logica e in Components/HdsAsistenta.py; aceleasi stari, aceleasi texte si acelasi jurnal
# in interfata web (/asistenta).
#
# Un clic, fara pasi in plus:
# - HdsAsistentaAlege: pagina de pornire. Numai randul scurt (A.TEXT_SCURT), randul bifat dinainte "Accept termenii și
#   condițiile" (Stanga/Dreapta schimba bifa; OK deschide HdsAsistentaTermeni, fereastra derulanta cu textul intreg,
#   A.textTermeni) si Verde "Start". Start porneste pe loc, fara nicio intrebare: durata A.DURATA_IMPLICITA_MIN,
#   nevoia "Nimic anume". Fara bifa, Start nu porneste si pagina spune scurt de ce.
# - HdsAsistenta: intrarea din meniu. Cat asistenta e oprita deschide pe loc pagina de pornire (la prima executie,
#   onFirstExecBegin: un ecran modal se deschide numai cand cel de dedesubt ruleaza); iesirea de pe pagina fara Start
#   inchide si intrarea. Cat e pornita arata numai pana cand e pornita (A.textPana) si, dedesubt, jurnalul (fiecare
#   cerere a echipei, cum promit termenii), cu Rosu "Oprește" (oprire pe loc). Codul sesiunii nu se arata nicaieri: el
#   ramane intern, intre receptor, server si echipa. Deschis la o cerere din pagina web (un browser fara cod, vezi
#   Screens/HdsAsistentaSemn.cerereWeb), deschide aceeasi pagina de pornire. Cat ecranele asistentei sunt deschise,
#   banda de semn de sus (Screens/HdsAsistentaSemn.py) se ascunde: ecranul arata el starea si pana cand e pornita.
#   Cand echipa a trimis concluzii (op "concluzii"), Galben "Ultimele concluzii" le deschide din nou.
# - HdsAsistentaConcluzii: fereastra "Ce am găsit și ce am făcut" (concluziile echipei si multumirile), modala, pana la
#   OK; o deschide Screens/HdsAsistentaSemn.Controler cand sosesc concluziile si o data la sfarsitul sesiunii.
#
# Skinul: ecranele sunt in skinul HDSatelit (HDSatelit/skin.xml, cadrul HdsCadru1776); skinul de aici e rezerva pentru
# alt skin ales, cu aceeasi geometrie (CORP_*); in skin.xml formele se numesc HdsAjutorDistanta (si fereastra
# termenilor si a concluziilor) si HdsAjutorDistantaAlege (skinName). Tastele lui HdsAsistenta sunt StaticText (liniuta si textul se
# ascund cand textul e gol): in skin.xml legenda lor o arata cadrul, in skinul de rezerva LEGENDA_ASISTENTA.

import re

from enigma import eTimer

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.ConfigList import ConfigListScreen
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components.config import ConfigYesNo, getConfigListEntry
from Components import HdsAsistenta as A
from Screens import HdsAsistentaSemn as Semn



def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la folosire."""
	return text


# sub randul bifat: ce face OK pe el (pe receptor nu exista legatura de apasat ca in web)
TEXT_OK_TERMENI = N_("OK pe rândul de sus: termenii și condițiile.")
# cat cererea asteapta echipa: omul poate iesi de pe ecran si se uita mai departe (banda de sus si anuntul de la
# conectare ii spun ce se intampla)
TEXT_ASTEPTARE = N_("Te anunțăm când intrăm. Poți folosi receptorul între timp.")

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

# corpul ecranului, acelasi in skin.xml (in cadrul HdsCadru1776) si in skinul de rezerva: starea sus, randul mare
# (gol: codul nu se arata), textul (jurnalul sau termenii) si ajutorul din dreapta jos
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

# a treia tasta (Galben "Ultimele concluzii"), numai pe ecranul asistentei, in skinul de rezerva; ajutorul din dreapta
# jos e aliniat la dreapta, deci incape langa ea
LEGENDA_GALBEN = """
		<widget source="key_yellow" render="FixedLabel" conditional="key_yellow" objectTypes="key_yellow,StaticText" position="888,944" size="6,32" backgroundColor="hdsAmber" zPosition="1">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_yellow" render="Label" conditional="key_yellow" objectTypes="key_yellow,StaticText" position="904,936" size="404,48" font="HdsCond;28" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" valign="center" noWrap="1" zPosition="1" />"""

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
		<widget name="key_green" position="476,936" size="404,48" font="Regular;28" foregroundColor="#F2F4F8" transparent="1" valign="center" noWrap="1" zPosition="1" />
		<widget source="key_yellow" render="FixedLabel" conditional="key_yellow" objectTypes="key_yellow,StaticText" position="888,944" size="6,32" backgroundColor="#F5B83D" zPosition="1">
			<convert type="ConditionalShowHide" />
		</widget>
		<widget source="key_yellow" render="Label" conditional="key_yellow" objectTypes="key_yellow,StaticText" position="904,936" size="404,48" font="Regular;28" foregroundColor="#F2F4F8" transparent="1" valign="center" noWrap="1" zPosition="1" />"""


def _nimic(*_a):
	pass


def _activa(s):
	return s.get("stare") in (A.INREGISTRARE, A.ASTEAPTA, A.CONECTAT, A.SE_OPRESTE)


class HdsAsistenta(Screen):
	skin = _rezerva("HdsAsistenta", "Asistență de la distanță", CORP_ASISTENTA + LEGENDA_ASISTENTA + LEGENDA_GALBEN)

	def __init__(self, session, din_web=None, nevoie="", detalii=""):
		Screen.__init__(self, session)
		# numele formei din skinul HDSatelit (skin.xml nu poate avea numele clasei: verificarea cuvintelor skinului)
		self.skinName = "HdsAjutorDistanta"
		self.setTitle(_("Asistență de la distanță"))
		# din_web: deschis la o cerere din pagina web (orice valoare in afara de None); durata si nevoia venite de
		# acolo nu mai conteaza: pornirea e cea de pe pagina, cu valorile implicite
		self.din_web = din_web is not None
		self["antet"] = StaticText("")
		# randul mare al formei ramane gol: codul sesiunii nu se arata omului
		self["cod"] = StaticText("")
		self["text"] = ScrollLabel("")
		self["ajutor"] = StaticText("")
		self["key_red"] = StaticText("")
		self["key_green"] = StaticText("")
		self["key_yellow"] = StaticText("")
		actiuni = {
			"cancel": self.close,
			"red": self._rosu,
			"green": self._verde,
			"yellow": self._galben,
			"blue": _nimic,
		}
		# toate actiunile hartii de directii legate (fara "unknown action" in jurnal); Sus/Jos deruleaza textul
		for d, f in (("up", self["text"].pageUp), ("down", self["text"].pageDown), ("left", _nimic), ("right", _nimic)):
			actiuni[d] = f
			actiuni[d + "Repeated"] = f
			actiuni[d + "Up"] = _nimic
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], actiuni, -2)
		self._text = None
		self.ceas = eTimer()
		self.ceas.callback.append(self.reface)
		self.onClose.append(self.ceas.stop)
		self.onClose.append(lambda: A.scoateObservator(self.reface))
		A.adaugaObservator(self.reface)
		self.onLayoutFinish.append(self._porneste)
		# pagina de pornire se deschide la prima executie (nu la onLayoutFinish: atunci ecranul inca nu ruleaza si
		# enigma2 refuza deschiderea unui ecran modal peste el)
		self.onFirstExecBegin.append(self._laIntrare)

	def _porneste(self):
		self.ceas.start(1000, False)
		self.reface()

	def _laIntrare(self):
		s = A.stare()
		if s.get("disponibil") and not _activa(s):
			self._deschidePagina(inchide_la_iesire=True)

	def _deschidePagina(self, inchide_la_iesire=False):
		self.session.openWithCallback(lambda pornita=None: self._dupaPagina(pornita, inchide_la_iesire),
			HdsAsistentaAlege, de_la="web" if self.din_web else "televizor")

	def _dupaPagina(self, pornita, inchide_la_iesire):
		self.din_web = False
		if pornita:
			# dupa Start ecranul ramane deschis: arata pana cand e pornita
			self.reface()
		elif inchide_la_iesire and not _activa(A.stare()):
			# iesirea de pe pagina de pornire fara Start: omul n-a vrut asistenta, nu ramane un ecran gol
			self.close()

	def _puneText(self, text):
		# ScrollLabel se intoarce sus la fiecare setText: textul se pune numai cand se schimba
		if text != self._text:
			self._text = text
			self["text"].setText(text)

	def reface(self):
		s = A.stare()
		self["cod"].setText("")
		# Galben: ultimele concluzii ale echipei, cand exista (si dupa oprire)
		self["key_yellow"].setText(_(A.TEXT_ULTIMELE_CONCLUZII) if s.get("are_concluzii") else "")
		if not s.get("disponibil"):
			self["antet"].setText(_("Funcția nu e disponibilă pe această imagine."))
			self._puneText("")
			self["ajutor"].setText("")
			self["key_green"].setText("")
			self["key_red"].setText(_("Înapoi"))
			return
		jurnal = "\n".join(s.get("jurnal") or [])
		if not _activa(s):
			# oprita (s-a oprit singura cat ecranul era deschis, sau sub pagina de pornire): Verde deschide pagina
			self["antet"].setText(_("Oprită. O pornești tu, dacă vrei să ne ajuți."))
			self._puneText(jurnal)
			self["ajutor"].setText("")
			self["key_green"].setText(_("Start"))
			self["key_red"].setText(_("Înapoi"))
			return
		# pornita: numai pana cand ("Pornită până la ZZ.LL, HH:MM." / "Pornită, fără sfârșit; ..."), jurnalul dedesubt
		self["antet"].setText(s.get("pana_text") or "")
		if s.get("stare") == A.ASTEAPTA:
			jurnal = _(TEXT_ASTEPTARE) + "\n\n" + jurnal
		self._puneText(jurnal)
		self["ajutor"].setText(_("Sus/Jos: tot textul"))
		# cat asistenta merge, Verde nu are ce face: fara text, legenda ei nu apare
		self["key_green"].setText("")
		self["key_red"].setText(_("Oprește"))

	def _verde(self):
		s = A.stare()
		if s.get("disponibil") and not _activa(s):
			self._deschidePagina()

	def _rosu(self):
		if _activa(A.stare()):
			# oprirea e pe loc, fara intrebare (a opri nu primejduieste nimic); ecranul se inchide
			A.opreste("de om")
		self.close()

	def _galben(self):
		c = A.ultimeleConcluzii()
		if c:
			self.session.open(HdsAsistentaConcluzii, c)


class HdsAsistentaConcluzii(Screen):
	"""Concluziile echipei la finalul asistentei: "Ce am găsit și ce am făcut", textul derulant (Sus/Jos), la sfarsit
	multumirile. Sta pana la OK (sau EXIT); fara intrebari. intrare: {"text", "ora", "id"} (A.ultimeleConcluzii)."""
	skin = _rezerva("HdsAsistentaConcluzii", "Asistență de la distanță", CORP_ASISTENTA + LEGENDA_ASISTENTA)
	# cate ferestre ale concluziilor sunt deschise acum (la sfarsitul sesiunii nu se deschide a doua daca e una)
	deschise = 0

	def __init__(self, session, intrare=None):
		Screen.__init__(self, session)
		self.skinName = "HdsAjutorDistanta"
		self.setTitle(_("Asistență de la distanță"))
		intrare = intrare or A.ultimeleConcluzii() or {}
		ora = intrare.get("ora") or 0
		self["antet"] = StaticText(_(A.TEXT_CONCLUZII))
		self["cod"] = StaticText("")
		self["text"] = ScrollLabel(A.textConcluzii(intrare))
		self["ajutor"] = StaticText(("%s  ·  %s" % (A.oraSfarsit(ora), _("Sus/Jos: tot textul"))) if ora else
			_("Sus/Jos: tot textul"))
		self["key_red"] = StaticText("")
		self["key_green"] = StaticText(_("OK"))
		actiuni = {
			"ok": self.close,
			"cancel": self.close,
			"red": _nimic,
			"green": self.close,
			"yellow": _nimic,
			"blue": _nimic,
		}
		for d, f in (("up", self["text"].pageUp), ("down", self["text"].pageDown), ("left", _nimic), ("right", _nimic)):
			actiuni[d] = f
			actiuni[d + "Repeated"] = f
			actiuni[d + "Up"] = _nimic
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], actiuni, -2)
		HdsAsistentaConcluzii.deschise += 1
		self.onClose.append(self._inchisa)

	def _inchisa(self):
		HdsAsistentaConcluzii.deschise = max(0, HdsAsistentaConcluzii.deschise - 1)


class HdsAsistentaTermeni(Screen):
	"""Fereastra derulanta cu termenii si conditiile intregi (A.textTermeni), deschisa cu OK de pe randul bifat."""
	skin = _rezerva("HdsAsistentaTermeni", "Termenii și condițiile", CORP_ASISTENTA + LEGENDA_ASISTENTA)

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = "HdsAjutorDistanta"
		self.setTitle(_("Asistență de la distanță"))
		self["antet"] = StaticText(_(A.TEXT_TERMENI))
		self["cod"] = StaticText("")
		self["text"] = ScrollLabel(A.textTermeni())
		self["ajutor"] = StaticText(_("Sus/Jos: tot textul"))
		self["key_red"] = StaticText(_("Înapoi"))
		self["key_green"] = StaticText("")
		actiuni = {
			"ok": self.close,
			"cancel": self.close,
			"red": self.close,
			"green": _nimic,
			"yellow": _nimic,
			"blue": _nimic,
		}
		for d, f in (("up", self["text"].pageUp), ("down", self["text"].pageDown), ("left", _nimic), ("right", _nimic)):
			actiuni[d] = f
			actiuni[d + "Repeated"] = f
			actiuni[d + "Up"] = _nimic
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], actiuni, -2)


class HdsAsistentaAlege(Screen, ConfigListScreen):
	"""Pagina de pornire: randul scurt, randul bifat dinainte si Start. -> close(True) dupa pornire."""
	skin = _rezerva("HdsAsistentaAlege", "Asistență de la distanță", CORP_ALEGE, LEGENDA_ALEGE)

	def __init__(self, session, de_la="televizor", **_vechi):
		Screen.__init__(self, session)
		self.skinName = "HdsAjutorDistantaAlege"
		self.setTitle(_("Asistență de la distanță"))
		self.de_la = de_la if de_la in ("televizor", "web") else "televizor"
		# bifat dinainte: omul apasa Start si atat
		self.accept = ConfigYesNo(default=True)
		ConfigListScreen.__init__(self, [getConfigListEntry(_(A.TEXT_ACCEPT), self.accept)], session=session)
		self["text"] = StaticText("")
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Start"))
		# Galben: ultimele concluzii ale echipei, cand exista (dupa o sesiune, de aici le reciteste omul)
		self["key_yellow"] = StaticText(_(A.TEXT_ULTIMELE_CONCLUZII) if A.ultimeleConcluzii() else "")
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			# OK legat aici (harta are OkCancelActions): OK pe rand deschide termenii si conditiile
			"ok": self.keyOK,
			"cancel": self.close,
			"red": self.close,
			"green": self._start,
			"yellow": self._galben,
			"blue": _nimic,
		}, -2)
		self._fara_bifa = False
		self.accept.addNotifier(self._bifa, initial_call=False)
		self._puneText()

	def _puneText(self):
		dedesubt = A.TEXT_FARA_BIFA if self._fara_bifa and not self.accept.value else TEXT_OK_TERMENI
		self["text"].setText(_(A.TEXT_SCURT) + "\n\n" + _(dedesubt))

	def _bifa(self, *_a):
		if self.accept.value:
			self._fara_bifa = False
		self._puneText()

	def keyOK(self):
		self.session.open(HdsAsistentaTermeni)

	def _galben(self):
		c = A.ultimeleConcluzii()
		if c:
			self.session.open(HdsAsistentaConcluzii, c)

	def _start(self):
		if not self.accept.value:
			self._fara_bifa = True
			self._puneText()
			return
		# fara intrebari: durata implicita, nevoia "Nimic anume"
		reusit, mesaj = Semn.porneste(self.session, nivel="A", durata_min=A.DURATA_IMPLICITA_MIN, de_la=self.de_la)
		if not reusit:
			# de ce n-a pornit, pe pagina (o fereastra deschisa inainte de close ar lasa pagina sub ea)
			self["text"].setText(_(A.TEXT_SCURT) + "\n\n" + (mesaj or ""))
			return
		self.close(True)
