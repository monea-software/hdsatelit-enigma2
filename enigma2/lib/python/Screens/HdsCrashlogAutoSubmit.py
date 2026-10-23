# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCrashlogAutoSubmit.py: Jurnalele de cădere (bsod.cpp, Dreambox upstream, NEATINS aici).
# Cod 100% propriu, scris de la zero.
#
# DE CE UN ECRAN NOU: `main/bsod.cpp`, compilat, deja scrie un jurnal XML complet la o prabusire totala a
# lui enigma2 (`bsodFatal()`) si deja citeste doua chei de configurare,
# `config.plugins.crashlogautosubmit.sendAnonCrashlog` si `.addNetwork`, direct din
# `/etc/enigma2/settings` (in siguranta, din interiorul handler-ului de semnal, fara Python) -- dar
# NICIUN cod Python nu definea vreodata aceste chei, deci userul n-avea de unde sa le schimbe, si
# NICIUN ecran nu arata jurnalele scrise. Acest fisier NU reimplementeaza mecanismul C++, doar il
# configureaza si arata rezultatul.
#
# NUME EXACT AL CHEILOR, obligatoriu identic cu bsod.cpp (linia ~190, ~194) -- daca as fi ales alt
# spatiu de nume, codul C++ nu le-ar fi vazut niciodata, indiferent ce ar fi salvat userul aici.
#
# GOL REAL (verificat prin SSH, doar citire, pe receptorul de proba, NU o presupunere):
# calea FIXA din bsod.cpp, "/media/hdd/enigma2_crash_<timestamp>.log", NU exista pe acest receptor --
# `/media` e tmpfs gol, stick-ul de pornire e montat in alta parte
# ("/run/media/<eticheta>-sda1"). `fopen()` esueaza silentios daca directorul lipseste: jurnalul de
# cădere nu se scrie DELOC, fara nicio eroare vizibila. Reparat pe doua planuri:
#   1. `hds-watchdog.py` (ruleaza deja la fiecare pornire, root, respawn din inittab) creeaza acum
#      `/media/hdd` daca lipseste, chiar la pornirea lui -- INAINTE ca enigma2 sa apuce sa se
#      prabuseasca (vezi ensure_crash_log_dir() acolo, adaugat).
#   2. Acest ecran repeta aceeasi creare, best-effort, la deschidere -- util si in emulator (unde
#      hds-watchdog.py nu ruleaza deloc, procesul de init fiind altul).
# NU era o reparare definitiva: `/media` ramane tmpfs (RAM) -- un jurnal scris acolo NU supravietuieste
# unei reporniri.
# bsod.cpp scrie acum in CRASH_LOG_DIR = /home/root/logs (memoria
# interna, unde stau si celelalte jurnale; rezerva /tmp), mytest.py la fel pentru ecranele cazute, iar hds-watchdog.py
# creeaza dosarul la pornire si pastreaza numai ultimele 5 jurnale. CALE_PRINCIPALA de mai jos e aceeasi cale (testul
# test_paznic_sistem o compara cu bsod.cpp); /tmp si vechiul /media/hdd se cauta in continuare.
#
# CAUTARE MAI LARGA DECAT DOAR "/media/hdd", tocmai din cauza golului de mai sus: acest ecran cauta
# jurnale si in orice alt folder montat sub /media, /run/media, si in /home/root -- ca un jurnal scris
# candva (alt receptor, alta configuratie de montare) sa tot fie gasit.
#
# TRIMITEREA RAMANE MANUALA, DELIBERAT (cf. deciziei "n-avem infrastructura de upload inca"):
# `CRASH_EMAILADDR` din bsod.cpp e deja "https://hdsatelit.com" (o adresa web, nu un email, desi
# comentariul C++ zice "email this crashlog to above address") -- nu exista nicaieri in bsod.cpp cod
# de trimitere automata prin retea, doar scriere pe disc. Ecranul arata asta cinstit userului, nu
# promite o trimitere care nu exista.

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import config, configfile, getConfigListEntry
from Components.MenuList import MenuList
from Components.Label import Label
from Components.Button import Button
from Components.Sources.StaticText import StaticText
from Components import HdsJurnale
from Screens.MessageBox import MessageBox
from .LogManager import HdsLogManagerViewLog

# Logica (caile, cautarea, setarile config.plugins.crashlogautosubmit) e in Components/HdsJurnale.py, folosita si de
# pagina web /jurnale-cadere (HdsWebControl/jurnale_sistem_web.py). CALE_PRINCIPALA e aceeasi cale ca in bsod.cpp.
CALE_PRINCIPALA = HdsJurnale.CALE_PRINCIPALA

# Numele EXACTE cerute de bsod.cpp, facute la incarcare, ca inainte (HdsJurnale.initConfigCadere verifica in
# config.plugins.content.items: o cheie lipsa da KeyError, nu AttributeError).
HdsJurnale.initConfigCadere()


def _asiguraDirectorPrincipal():
	"""Best-effort, la deschiderea ecranului (vezi explicatia din capul fisierului)."""
	HdsJurnale.asiguraDirectorPrincipal()


def _foldereCandidate():
	return HdsJurnale.foldereCandidate()


def _cautaJurnale():
	"""Jurnalele 'enigma2_crash_*.log' din toate dosarele candidate: (cale, nume, marime, mtime), cele mai noi primele."""
	return HdsJurnale.cautaJurnaleCadere()


class HdsCrashlogAutoSubmit(Screen):
	skin = """
	<screen name="HdsCrashlogAutoSubmit" resolution="1920,1080" position="center,center" size="1300,760" title="Jurnalele de cădere">
		<widget name="text" position="30,20" size="1240,110" font="Regular;20" />
		<widget name="lista" position="30,140" size="1240,520" font="Regular;22" itemHeight="40" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="30,700" size="290,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_green" position="340,700" size="290,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_yellow" position="650,700" size="290,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
		<widget name="key_blue" position="960,700" size="290,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#185090" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Jurnalele de cădere"))

		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button(_("Vizualizează"))
		self["key_yellow"] = Button(_("Șterge"))
		self["key_blue"] = Button(_("Setări"))

		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions", "DirectionActions"],
			{
				"cancel": self.close,
				"red": self.close,
				"ok": self._vizualizeaza,
				"green": self._vizualizeaza,
				"yellow": self._sterge,
				"blue": self._setari,
				"up": self._sus,
				"down": self._jos,
			}, -2)

		_asiguraDirectorPrincipal()

		self["text"] = Label("")
		self["lista"] = MenuList([])
		self._jurnale = []
		self._reincarca()
		getattr(self, "onLayoutFinish", []).append(self._textMarit)

	def _textMarit(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): textul de sus creste cat ii cere, iar
		lista jurnalelor coboara si se scurteaza (la 130 % se pierdea ultimul rand). La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			if not MT.marit():
				return
			a = MT.Asezare(self)
			lista, text = a.dinSkin(self["lista"].instance), self["text"].instance
			if lista and text is not None:
				a.creste(text, MT.inaltimeText(text), lista[1] + lista[3], maxim=lista[3] // 3)
		except Exception as e:
			print("[HdsCrashlogAutoSubmit] textul marit: %s" % e)

	def _reincarca(self):
		self._jurnale = _cautaJurnale()
		if self._jurnale:
			randuri = [HdsJurnale.textRand(nume, marime, mtime) for _cale, nume, marime, mtime in self._jurnale]
		else:
			randuri = [_("Niciun jurnal de cădere găsit.")]
		self["lista"].setList(randuri)
		self["text"].setText(
			_(
				"Găsite: %d. Trimiterea rămâne manuală: un jurnal găsit aici se poate trimite prin "
				"formularul de contact de pe hdsatelit.com; nu există încă o trimitere automată prin "
				"rețea.\nSe caută în „%s”, în /tmp și în orice alt folder montat sub /media, /run/media, /home/root."
			) % (len(self._jurnale), CALE_PRINCIPALA)
		)

	def _sus(self):
		self["lista"].up()

	def _jos(self):
		self["lista"].down()

	def _selectat(self):
		index = self["lista"].getSelectionIndex()
		if self._jurnale and 0 <= index < len(self._jurnale):
			return self._jurnale[index]
		return None

	def _vizualizeaza(self):
		sel = self._selectat()
		if sel:
			self.session.open(HdsLogManagerViewLog, sel[0])

	def _sterge(self):
		sel = self._selectat()
		if not sel:
			return
		cale, nume = sel[0], sel[1]
		self.session.openWithCallback(
			lambda raspuns: self._dupaConfirmareStergere(raspuns, cale),
			MessageBox,
			_("Ștergi jurnalul „%s”?") % nume,
			MessageBox.TYPE_YESNO,
			default=False,
		)

	def _dupaConfirmareStergere(self, raspuns, cale):
		if not raspuns:
			return
		HdsJurnale.stergeFisier(cale)
		self._reincarca()

	def _setari(self):
		self.session.open(HdsCrashlogSetari)


class HdsCrashlogSetari(Screen, ConfigListScreen):
	skin = """
	<screen name="HdsCrashlogSetari" resolution="1920,1080" position="center,center" size="1100,600" title="Setări pentru jurnalele de cădere">
		<widget name="config" position="20,20" size="1060,140" scrollbarMode="showOnDemand" />
		<widget name="text" position="20,180" size="1060,360" font="Regular;20" />
		<widget name="key_red" position="20,540" size="510,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_green" position="570,540" size="510,40" zPosition="1" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [], session=session)
		self.setTitle(_("Setări pentru jurnalele de cădere"))

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("Save"))

		cfg = config.plugins.crashlogautosubmit
		self._campuri = [cfg.sendAnonCrashlog, cfg.addNetwork]
		self._initiale = [c.value for c in self._campuri]

		self.list = [
			getConfigListEntry(_("Păstrează jurnalul anonim (fără cartelă CA, fără setările contului)"), cfg.sendAnonCrashlog),
			getConfigListEntry(_("Include informații de rețea în jurnal (interfețe, DNS, ruta implicită)"), cfg.addNetwork),
		]
		self["config"].list = self.list

		self["text"] = Label(
			_(
				"Aceste două opțiuni sunt citite direct de codul C++ care scrie jurnalul de cădere "
				"(bsod.cpp), inclusiv la o prăbușire completă. Parola Wi-Fi nu e inclusă NICIODATĂ, "
				"indiferent de setări.\n\n"
				"„Anonim” = DA (implicit): jurnalul nu identifică receptorul sau contul.\n"
				"„Anonim” = NU: jurnalul include și cartela CA și setările (fără parole); folosește doar "
				"dacă trimiți jurnalul manual cuiva care chiar are nevoie de acele detalii.\n\n"
				"„Informații de rețea” = NU (implicit): jurnalul nu include nimic despre rețea.\n"
				"„Informații de rețea” = DA: jurnalul include interfețele, DNS și ruta implicită (util la "
				"probleme legate de rețea, dar arată adrese interne)."
			)
		)

		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.anuleaza,
			"red": self.anuleaza,
			"green": self.salveaza,
		}, -2)

	def salveaza(self):
		for c in self._campuri:
			c.save()
		# bsod.cpp citeste setarile direct din /etc/enigma2/settings, chiar la o cadere: fisierul se scrie acum, nu
		# abia la oprirea interfetei (pagina web face la fel)
		configfile.save()
		self.close(True)

	def anuleaza(self):
		for c, valoare in zip(self._campuri, self._initiale):
			c.value = valoare
		self.close(False)
