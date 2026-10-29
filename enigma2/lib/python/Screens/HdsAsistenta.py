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
#   pastram, cum opresti, cat poate ramane pornita, varsta) si Verde "Pornește". Cat e pornita arata codul (cat asteapta
#   aprobarea, fara termen: echipa intra oricand cat e pornita), pana cand e pornita (A.textPana: "până la ZZ.LL, HH:MM"
#   sau "fără sfârșit") si jurnalul in timp real, cu Rosu "Oprește"; tasta verde nu are atunci ce face si nu apare.
#   Deschis la o cerere din pagina web (browserul omului, conectat cu codul de pe receptor), spune asta sus si ramane
#   deschis pana raspunde omul. Cat ecranul e deschis, banda de semn de sus (Screens/HdsAsistentaSemn.py) se ascunde:
#   ecranul arata el starea si pana cand e pornita.
# - HdsAsistentaAlege: alegerea duratei (nivelul e "Citire și probe", fix in versiunea 1) si, optional, "Cu ce te
#   ajutăm?" (o alegere din lista A.NEVOI, implicit "Nimic anume", si un rand de text scris cu tastatura de pe ecran),
#   apoi confirmarea (implicit "Nu"); abia dupa "Da" porneste sesiunea. Cine nu vrea sa spuna nimic apasa Verde ca
#   inainte: zero pasi in plus. Stanga/Dreapta schimba o alegere, OK deschide lista ei (ChoiceBox) sau tastatura.
#   Codul de pe ecran nu trebuie spus nimanui: serverul ni-l trimite singur, cu nevoia aleasa. Semnul de pe ecran si
#   pornirea insasi le face Screens/HdsAsistentaSemn.py.
#
# Skinul: ecranele sunt in skinul HDSatelit (HDSatelit/skin.xml, cadrul HdsCadru1776); skinul de aici e rezerva pentru
# alt skin ales, cu aceeasi geometrie (CORP_*); in skin.xml formele se numesc HdsAjutorDistanta si
# HdsAjutorDistantaAlege (skinName). Tastele lui HdsAsistenta sunt StaticText (liniuta si textul se ascund cand textul
# e gol): in skin.xml legenda lor o arata cadrul, in skinul de rezerva LEGENDA_ASISTENTA.

import re

from enigma import eTimer

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.ConfigList import ConfigListScreen
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components.config import ConfigSelection, ConfigText, getConfigListEntry
from Components import HdsAsistenta as A
from Screens import HdsAsistentaSemn as Semn



def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la folosire."""
	return text


TEXT_NUMAI_TESTERI = N_("Asistența de la distanță e pentru beta testeri.")
# cat codul asteapta aprobarea: omul nu trebuie sa ni-l spuna (vine la noi pe e-mail); il vede ca sa stie ca e
# cererea lui
TEXT_COD_PRIMIT = N_("Am primit cererea ta, cu codul de mai jos. Nu trebuie să faci nimic.")
# sub cod, cat cererea asteapta: omul poate iesi de pe ecran si se uita mai departe (banda de sus si anuntul de la
# conectare ii spun ce se intampla)
TEXT_ASTEPTARE = N_("Te anunțăm când intrăm. Poți folosi receptorul între timp.")
TEXT_NEVOIE = N_("Cu ce te ajutăm?")
TEXT_DETALII = N_("Scrie pe scurt (opțional)")
TEXT_NEVOIE_AJUTOR = N_("Dacă vrei, alege cu ce te ajutăm și scrie pe scurt ce se întâmplă (OK deschide lista sau "
	"tastatura). Nu e obligatoriu: Verde pornește oricum.")
# confirmarea la "permanent" (la celelalte durate: "Dai acces la distanță pentru %s, ...")
TEXT_CONFIRMA_PERMANENT = N_("Dai acces la distanță permanent, până îl oprești tu, nivel „Citire și probe”. Pornind, "
	"confirmi că ai cel puțin 16 ani sau acordul unui părinte. Poți opri oricând. Pornești?")
# cheia alegerii "Nimic anume" in lista de pe ecran (ConfigSelection vrea o cheie nevida); A.curataNevoie o face ""
NEVOIE_ECRAN_NIMIC = "nimic"

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

	def __init__(self, session, din_web=None, nevoie="", detalii=""):
		Screen.__init__(self, session)
		# numele formei din skinul HDSatelit (skin.xml nu poate avea numele clasei: verificarea cuvintelor skinului)
		self.skinName = "HdsAjutorDistanta"
		self.setTitle(_("Asistență de la distanță"))
		# din_web: minutele alese in pagina web (cererea de pornire din browserul omului); None = deschis din meniu
		self.din_web = int(din_web) if din_web in A.DURATE_MIN else None
		# "Cu ce te ajutăm?" ales in pagina web: ecranul de pornire il arata deja ales (omul il poate schimba)
		self.nevoie, self.detalii = A.curataNevoie(nevoie, detalii)
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
		self.onLayoutFinish.append(self._porneste)

	def _porneste(self):
		self.ceas.start(1000, False)
		self.reface()

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
			self["antet"].setText(_(TEXT_COD_PRIMIT))
			self["cod"].setText(_cod(s["cod"]))
		elif stare == A.CONECTAT:
			self["antet"].setText(_("Conectat."))
			self["cod"].setText("")
		else:
			self["antet"].setText(_("Se pregătește..."))
			self["cod"].setText("")
		jurnal = "\n".join(s.get("jurnal") or [])
		if stare == A.ASTEAPTA and s.get("cod"):
			jurnal = _(TEXT_ASTEPTARE) + "\n\n" + jurnal
		self._puneText(jurnal)
		# jos in dreapta, langa Rosu "Oprește": pana cand e pornita (antetul are un singur rand, pentru stare)
		self["ajutor"].setText(self._ramas(s))
		# cat asistenta merge, Verde nu are ce face: fara text, legenda ei nu apare
		self["key_green"].setText("")
		self["key_red"].setText(_("Oprește"))

	def _ramas(self, s):
		# pana cand e pornita ("Pornită până la ZZ.LL, HH:MM." / "Pornită, fără sfârșit; o poți opri oricând.")
		return s.get("pana_text") or ""

	def _verde(self):
		if not self._tester:
			from Screens.HdsBetaTester import HdsBetaAcord
			self.session.openWithCallback(lambda *r: self.reface(), HdsBetaAcord)
			return
		s = A.stare()
		if s.get("disponibil") and s.get("stare") == A.OPRIT:
			self.session.openWithCallback(self._dupaAlege, HdsAsistentaAlege,
				minute=self.din_web if self.din_web is not None else A.DURATA_IMPLICITA_MIN,
				de_la="web" if self.din_web is not None else "televizor", nevoie=self.nevoie, detalii=self.detalii)

	def _dupaAlege(self, pornita=None):
		if pornita:
			# dupa pornire ecranul ramane deschis: arata codul mare
			self.din_web = None
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

	def __init__(self, session, minute=None, de_la="televizor", nevoie="", detalii=""):
		Screen.__init__(self, session)
		self.skinName = "HdsAjutorDistantaAlege"
		self.setTitle(_("Pornește asistența"))
		self.de_la = de_la if de_la in ("televizor", "web") else "televizor"
		implicit = minute if minute in A.DURATE_MIN else A.DURATA_IMPLICITA_MIN
		self._alegeri = {}
		alegeri = [(str(m), A.textDurata(m)) for m in A.DURATE_MIN]
		self.durata = ConfigSelection(default=str(implicit), choices=alegeri)
		self._alegeri[id(self.durata)] = alegeri
		# "Cu ce te ajutăm?": implicit "Nimic anume", deci Verde porneste ca inainte, fara pasi in plus
		nevoie, detalii = A.curataNevoie(nevoie, detalii)
		alegeri = [(cheie or NEVOIE_ECRAN_NIMIC, text) for cheie, text in A.alegeriNevoie()]
		self.nevoie = ConfigSelection(default=nevoie or NEVOIE_ECRAN_NIMIC, choices=alegeri)
		self._alegeri[id(self.nevoie)] = alegeri
		self.detalii = ConfigText(default=detalii, fixed_size=False, visible_width=48)
		# trei randuri: exact cat incape in lista formei HdsAjutorDistantaAlege (180 px, randuri de 60)
		lista = [getConfigListEntry(_("Cât timp"), self.durata), getConfigListEntry(_(TEXT_NEVOIE), self.nevoie),
			getConfigListEntry(_(TEXT_DETALII), self.detalii)]
		ConfigListScreen.__init__(self, lista, session=session)
		self["text"] = StaticText(_("Nivel: Citire și probe (putem rula numai operații dintr-o listă fixă, în "
			"principal citiri; o captură arată numai meniurile, nu imaginea canalului). Poți opri oricând.") + "\n\n"
			+ _(TEXT_NEVOIE_AJUTOR))
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Pornește"))
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			# OK legat aici (harta are OkCancelActions): altfel jurnalul scrie "unknown action" la fiecare OK
			"ok": self.keyOK,
			"cancel": self.close,
			"red": self.close,
			"green": self._porneste,
			"yellow": _nimic,
			"blue": _nimic,
		}, -2)

	def keyOK(self):
		# OK pe o alegere deschide lista ei (ChoiceBox); pe randul de text, tastatura de pe ecran (ConfigListScreen)
		cur = self["config"].getCurrent()
		el = cur[1] if cur is not None and len(cur) > 1 else None
		if el is not None and id(el) in self._alegeri:
			alegeri = self._alegeri[id(el)]
			chei = [cheie for cheie, _text in alegeri]
			sel = chei.index(el.value) if el.value in chei else 0
			self.session.openWithCallback(lambda ales: self._ales(el, ales), ChoiceBox, title=cur[0],
				list=[(text, cheie) for cheie, text in alegeri], selection=sel)
			return
		ConfigListScreen.keyOK(self)

	def _ales(self, el, ales):
		if ales:
			el.value = ales[1]
			self["config"].invalidateCurrent()

	def _porneste(self):
		durata = int(self.durata.value)
		if durata == A.DURATA_PERMANENTA:
			fraza = _(TEXT_CONFIRMA_PERMANENT)
		else:
			fraza = _("Dai acces la distanță pentru %s, nivel „Citire și probe”. Pornind, confirmi că ai cel puțin 16 "
				"ani sau acordul unui părinte. Poți opri oricând. Pornești?") % A.textDurata(durata)
		self.session.openWithCallback(lambda da: self._confirmat(da, durata), MessageBox, fraza,
			MessageBox.TYPE_YESNO, default=False)

	def _confirmat(self, da, durata):
		if not da:
			return
		nevoie, detalii = A.curataNevoie(self.nevoie.value, self.detalii.value)
		reusit, mesaj = Semn.porneste(self.session, nivel="A", durata_min=durata, de_la=self.de_la, nevoie=nevoie,
			detalii=detalii)
		if not reusit:
			self.session.open(MessageBox, mesaj, MessageBox.TYPE_INFO, timeout=6)
		self.close(bool(reusit))
