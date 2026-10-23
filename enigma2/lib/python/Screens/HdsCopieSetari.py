# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCopieSetari: ecranul „Copia setărilor” (Meniu > Setări > Software & Firmware, langa actualizarea software): copia
# setarilor pe un stick sau un disc, copia automata zilnica, copiile gasite si punerea lor la loc. Logica e in
# Components/HdsCopieSetari.py, aceeasi pentru pagina web /copie-setari (HdsWebControl/copie_setari_web.py).
#
# Randurile ca la scanere si la import (sursa List, eticheta si valoarea), in skinul HDSatelit ecranul
# HdsCopieSetariScreen, pe alte skinuri skinul de rezerva al scanerelor (Screens/ScanerCablu.skin_rezerva). Totul merge
# numai cu sagetile si OK; tastele colorate scurteaza: VERDE face copia, GALBEN pune la loc copia luminata, ALBASTRU o
# sterge. Cautarea copiilor si facerea copiei merg pe un fir separat (un stick poate fi lent); punerea la loc NU se face
# cat interfata ruleaza: se scrie cererea, interfata reporneste si enigma2.sh pune copia la loc inaintea ei. Punerea la
# loc si stergerea intreaba inainte, cu „Nu” ales.

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen

from Components import HdsCopieSetari as C
from Components.HdsCursorLista import pune_randurile

# coloana etichetei (480 la 1920, ca HdsImportSetariScreen); valoarea are 632 px (HdsBold 30)
COTE = {"eticheta": 480}
LATIME_VALOARE = 632


def _nimic():
	pass


def scurt(text, latime=LATIME_VALOARE):
	"""Valoarea unui rand, dupa latimea masurata (HdsBold 30): intreaga daca incape, altfel fara paranteza de la
	sfarsit, apoi taiata la dreapta cu „…”; textul intreg e in descrierea de sub lista."""
	from Components.HdsLatimeText import incape, scurteaza
	if incape(text, latime, "HdsBold", 30):
		return text
	if text.endswith(")") and " (" in text:
		return scurt(text[:text.rindex(" (")], latime)
	return scurteaza(text, latime, "HdsBold", 30)


def eticheta_copie(c):
	return _("Copia din %s") % c["data_text"]


def valoare_copie(c):
	receptor = _("acest receptor") if c["acest"] else _("alt receptor")
	return "%s, %s" % (c["versiune"] or "?", receptor)


class HdsCopieSetariScreen(Screen):
	"""Randurile: „Fă copia acum”, „Locul copiei”, „Copie automată”, „Copii automate păstrate”, copiile gasite, „Caută din
	nou” (si „Renunță la punerea la loc” cat asteapta o cerere)."""

	def __init__(self, session):
		Screen.__init__(self, session)
		from Screens.ScanerCablu import (skin_rezerva, culoare_valoare, _culoare_skin, fonturi_texte, potriveste_textul,
			TASTE_RIDICATE)
		self.skin = skin_rezerva("HdsCopieSetariScreen", COTE)
		self._fonturi = fonturi_texte("HdsCopieSetariScreen")
		self._potriveste = potriveste_textul
		self._culoare = culoare_valoare()
		self._culoare_stinsa = _culoare_skin("hdsLabel")
		self._culoare_nota = _culoare_skin("hdsAmber")
		if self._culoare_stinsa is None:
			self._culoare_stinsa = 0x8A93A6
		if self._culoare_nota is None:
			self._culoare_nota = 0xF5B83D
		self.cfg = C.config_copie()
		st = C.stare()
		self.medii = list(st["medii"] or [])
		self.copii = list(st["copii"] or [])
		implicit = C.mediu_implicit(self.medii)
		self.id_mediu = implicit["id"] if implicit else None
		self._cauta = True
		self._inchis = False
		self._rezultat = []
		self["lista"] = List([], enableWrapAround=True)
		self["preview"] = Label("")
		self["stare"] = Label("")
		self["key_red"] = StaticText(_("Înapoi"))
		self["key_green"] = StaticText(_("Fă copia"))
		self["key_yellow"] = StaticText("")
		self["key_blue"] = StaticText("")
		actiuni = {
			"ok": self.ok,
			"cancel": self.close,
			"red": self.close,
			"green": self.faCopia,
			"yellow": self.puneLaLoc,
			"blue": self.sterge,
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
		self.setTitle(_("Copia setărilor"))
		from enigma import eTimer
		self._ceas = eTimer()
		try:
			self._legatura = self._ceas.timeout.connect(self._verifica)
		except AttributeError:
			self._ceas.callback.append(self._verifica)
		self._arata()
		self.onClose.append(self._laInchidere)
		self.onFirstExecBegin.append(self.cautaDinNou)
		self.onLayoutFinish.append(self._potrivesteTextele)

	# ---- starea comuna (ecran si web) ----
	def cautaDinNou(self):
		self._cauta = True
		C.porneste_cautarea()
		self._arata()
		self._ceas.start(300, False)

	def _verifica(self):
		st = C.stare()
		if st["cauta"] or st["lucreaza"]:
			self._arata()
			return
		self._ceas.stop()
		self._cauta = False
		self.medii = list(st["medii"] or [])
		self.copii = list(st["copii"] or [])
		if C.mediu_dupa_id(self.id_mediu, self.medii) is None:
			implicit = C.mediu_implicit(self.medii)
			self.id_mediu = implicit["id"] if implicit else None
		if st.get("ultimul") is not None and self._asteapta_copia:
			self._rezultat = list(st["ultimul"].get("mesaje") or [])
			self._asteapta_copia = False
		self._arata()

	_asteapta_copia = False

	def mediu(self):
		return C.mediu_dupa_id(self.id_mediu, self.medii)

	def copie(self):
		cheie = self._cheie()
		if cheie and cheie.startswith("copie:"):
			return C.copie_dupa_id(cheie[6:], self.copii)
		return None

	def _cerere(self):
		return C.cerere_in_asteptare()

	# ---- desenul ----
	def _randuri(self):
		automat = self.cfg.automat.value == "zilnic"
		m = self.mediu()
		if m is not None:
			# valorile raman intregi: un rand care nu incape deruleaza (lib/gui/elabel.h)
			unde, culoare_unde = m["nume"], self._culoare
		elif self._cauta:
			unde, culoare_unde = _("Se caută…"), self._culoare_stinsa
		else:
			unde, culoare_unde = _("niciun stick sau disc"), self._culoare_nota
		randuri = [
			(_("Fă copia acum"), "fa", _("se face…") if C.ocupat() else "", self._culoare_stinsa),
			(_("Locul copiei"), "mediu", unde, culoare_unde),
			(_("Copie automată"), "automat", _("Zilnic") if automat else _("Oprită"), self._culoare),
			(_("Copii automate păstrate"), "pastrate", self.cfg.pastrate.value,
				self._culoare if automat else self._culoare_stinsa),
		]
		for c in self.copii:
			randuri.append((eticheta_copie(c), "copie:" + c["id"], valoare_copie(c),
				self._culoare if c["acest"] else self._culoare_stinsa))
		if not self.copii and not self._cauta:
			randuri.append((_("Nicio copie găsită"), "nimic", "", self._culoare_stinsa))
		if self._cerere():
			randuri.append((_("Renunță la punerea la loc"), "anuleaza", "", self._culoare_nota))
		randuri.append((_("Caută din nou"), "cauta", "", self._culoare))
		return randuri

	def _textPreview(self):
		if self._rezultat:
			return "\n".join(self._rezultat)
		cheie = self._cheie()
		c = self.copie()
		if c is not None:
			return C.descriere_copie(c) + "\n" + C.text_avertisment()
		if C.ocupat():
			return _("Se face copia. Nu scoate stickul până nu scrie „Copia e gata”.")
		if cheie in ("automat", "pastrate"):
			return C.text_automat() + "\n" + _("Copia automată merge pe stickul de actualizare, dacă e băgat, altfel pe "
				"primul stick sau disc găsit.")
		if cheie == "anuleaza":
			return _("O copie așteaptă să fie pusă la loc la repornirea interfeței.")
		m = self.mediu()
		if m is None:
			if self._cauta:
				return _("Se caută stickurile, discurile și copiile de pe ele…")
			return _("Bagă un stick USB sau un disc în receptor, apoi alege „Caută din nou”.")
		return (_("Copia merge pe %s: canalele, buchetele, listele DAB+ și DVB-T2, setările, rețeaua și Wi-Fi, "
			"cheile SSH și modulele de acces condiționat.") % m["nume"]) + "\n" + C.text_avertisment()

	def _ajutor(self):
		cheie = self._cheie()
		if cheie == "fa":
			return _("OK sau VERDE: copia se face acum pe locul ales la „Locul copiei”.")
		if cheie == "mediu":
			return _("Schimbă cu stânga, dreapta sau OK.") if len(self.medii) > 1 else _("Numai acest loc e găsit.")
		if cheie == "automat":
			return _("Zilnic: o copie pe zi, singură, cât receptorul e pornit.")
		if cheie == "pastrate":
			return _("Câte copii automate rămân pe stick; cele făcute de mână nu se șterg singure.")
		if cheie and cheie.startswith("copie:"):
			return _("OK: ce faci cu copia. GALBEN: pune la loc. ALBASTRU: șterge.")
		if cheie == "anuleaza":
			return _("OK: copia nu se mai pune la loc.")
		return _("Caută din nou stickurile și copiile.")

	def _arata(self, stare=None):
		# cursorul ramane pe randul lui dupa cheie: randurile copiilor, "nimic" si "anuleaza" apar si dispar deasupra
		# randului "cauta", deci numarul randului nu ajunge
		pune_randurile(self["lista"], self._randuri())
		self["preview"].setText(self._textPreview())
		self["stare"].setText(stare or self._ajutor())
		self._taste()
		self._potrivesteTextele()

	def _taste(self):
		c = self.copie()
		self["key_green"].setText(_("Fă copia") if self.mediu() is not None and not C.ocupat() else "")
		self["key_yellow"].setText(_("Pune la loc") if c is not None else "")
		self["key_blue"].setText(_("Șterge") if c is not None else "")

	def _potrivesteTextele(self, nume=("preview", "stare")):
		for n in nume:
			self._potriveste(self[n], *self._fonturi[n])

	def _cheie(self):
		curent = self["lista"].getCurrent()
		return curent[1] if curent else None

	# ---- tastele ----
	def _mutat(self):
		self._rezultat = []
		self["preview"].setText(self._textPreview())
		self["stare"].setText(self._ajutor())
		self._taste()
		self._potrivesteTextele()

	def sus(self):
		self["lista"].selectPrevious()
		self._mutat()

	def jos(self):
		self["lista"].selectNext()
		self._mutat()

	def _schimba(self, pas):
		cheie = self._cheie()
		self._rezultat = []
		if cheie == "mediu" and self.medii:
			ids = [m["id"] for m in self.medii]
			i = ids.index(self.id_mediu) if self.id_mediu in ids else -1
			self.id_mediu = ids[(i + pas) % len(ids)]
		elif cheie == "automat":
			ok, mesaj = C.seteaza_automat("oprita" if self.cfg.automat.value == "zilnic" else "zilnic")
			self._arata(mesaj)
			return
		elif cheie == "pastrate":
			n = (int(self.cfg.pastrate.value) - 1 + pas) % C.PASTRATE_MAXIM + 1
			ok, mesaj = C.seteaza_automat(pastrate=n)
			self._arata(mesaj)
			return
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
			if len(self.medii) > 1:
				from Screens.ScanerCablu import AlegereDinLista
				randuri = [(m["nume"], m["id"]) for m in self.medii]
				poz = [i for i, r in enumerate(randuri) if r[1] == self.id_mediu]
				self.session.openWithCallback(self._dupaMediu, AlegereDinLista, title=_("Locul copiei"), list=randuri,
					selection=poz[0] if poz else 0)
			elif not self.medii:
				self.cautaDinNou()
		elif cheie in ("automat", "pastrate"):
			self._schimba(1)
		elif cheie and cheie.startswith("copie:"):
			c = self.copie()
			from Screens.ScanerCablu import AlegereDinLista
			self.session.openWithCallback(self._dupaAlegereCopie, AlegereDinLista, title=eticheta_copie(c),
				list=[(_("Pune la loc din copie"), "pune"), (_("Șterge copia"), "sterge")], selection=0)
		elif cheie == "anuleaza":
			C.anuleaza_cererea()
			self._arata(_("Copia nu se mai pune la loc."))
		elif cheie == "cauta":
			self.cautaDinNou()

	def _dupaMediu(self, rand=None):
		if rand and rand[1] is not None:
			self.id_mediu = rand[1]
		self._arata()

	def _dupaAlegereCopie(self, rand=None):
		if rand and rand[1] == "pune":
			self.puneLaLoc()
		elif rand and rand[1] == "sterge":
			self.sterge()

	def faCopia(self):
		m = self.mediu()
		if m is None:
			self._arata(_("Bagă un stick sau un disc și alege „Caută din nou”."))
			return
		self._rezultat = []
		pornit, mesaj = C.porneste_copia(m["id"])
		self._asteapta_copia = pornit
		self._arata(mesaj)
		if pornit:
			self._ceas.start(300, False)

	def puneLaLoc(self):
		c = self.copie()
		if c is None:
			return
		self.session.openWithCallback(lambda da: self._dupaIntrebarePunere(da, c), MessageBox,
			C.text_intrebare_punere(c), MessageBox.TYPE_YESNO, default=False)

	def _dupaIntrebarePunere(self, da, c):
		if not da:
			return
		ok, mesaj = C.cere_punerea(c["id"], self.copii)
		if not ok:
			self._arata(mesaj)
			return
		from Screens.Standby import TryQuitMainloop
		self.session.open(TryQuitMainloop, 3)

	def sterge(self):
		c = self.copie()
		if c is None:
			return
		self.session.openWithCallback(lambda da: self._dupaIntrebareStergere(da, c), MessageBox,
			C.text_intrebare_stergere(c), MessageBox.TYPE_YESNO, default=False)

	def _dupaIntrebareStergere(self, da, c):
		if not da:
			return
		ok, mesaj = C.sterge_copia(c["id"], self.copii)
		self._rezultat = [mesaj]
		self.cautaDinNou()

	def _laInchidere(self):
		self._inchis = True
		self._ceas.stop()


def main(session, **kwargs):
	session.open(HdsCopieSetariScreen)
