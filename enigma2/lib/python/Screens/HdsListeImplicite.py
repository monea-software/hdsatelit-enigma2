# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsListeImplicite.py: ecranul „Liste implicite de canale” (Meniu > Scanare, modul avansat; data/menu.xml,
# entryID default_lists). Înainte intrarea deschidea direct asistentul vechi (Screens/ScanSetup.DefaultSatLists), care
# pe o imagine fără pachete de liste arăta o fereastră goală, fără titlu, cu un singur rând.
#
# Acum ecranul are titlul intrării din meniu și, pe rânduri (numai săgețile și OK), ce se poate face: scanarea pe
# satelit, prin cablu sau terestru (numai pentru tunerele pe care le are receptorul) și importul dintr-o copie de pe
# stick. Dacă imaginea are pachete de liste (fișiere .info cu eticheta „services” în /usr/share/enigma2/defaults, cele
# pe care le caută asistentul vechi), primul rând deschide asistentul vechi. Căutarea pachetelor citește numai
# fișierele .info mici, fără mount (asistentul vechi încerca la deschidere un mount pe /dev/mtdblock6).
#
# Aceleași rânduri și texte le folosește pagina web /liste-implicite (HdsWebControl/scanare_liste_web.py), prin
# funcțiile de modul de mai jos, care nu cer ecran.

import os
import re

from Screens.Screen import Screen

DOSAR_LISTE = "/usr/share/enigma2/defaults"
TIPAR_LISTE = re.compile(r"<tag\s+type\s*=\s*[\"']services[\"']")
MARIME_INFO = 64 * 1024
# (cheia, tipul de tuner cerut sau None, modulul și clasa ecranului, felul dat ecranului, pagina web)
ACTIUNI = (
	("satelit", "DVB-S", "Screens.ScanerSatelit", "ScanerSatelit", "satelit", "/scanare/satelit/satelit"),
	("cablu", "DVB-C", "Screens.ScanerCablu", "ScanerCablu", "operator", "/scanare/cablu/operator"),
	("terestru", "DVB-T", "Screens.ScanerTerestru", "ScanerTerestru", "regiune", "/scanare/terestru/regiune"),
	("import", None, "Plugins.Extensions.HdsImportSetari.plugin", "HdsImportSetariScreen", None, "/import"),
)


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def are_liste(dosar=DOSAR_LISTE, adancime=3):
	"""True dacă imaginea are pachete de liste de canale (ce ar arăta asistentul vechi)."""
	baza = dosar.rstrip(os.sep).count(os.sep)
	for radacina, dosare, fisiere in os.walk(dosar):
		if radacina.count(os.sep) - baza >= adancime:
			dosare[:] = []
		for nume in fisiere:
			if not nume.endswith(".info"):
				continue
			try:
				with open(os.path.join(radacina, nume), "r", encoding="utf-8", errors="replace") as f:
					if TIPAR_LISTE.search(f.read(MARIME_INFO)):
						return True
			except (OSError, IOError):
				pass
	return False


def texte_actiune(cheie):
	"""(textul rândului, explicația lui)."""
	return {
		"pachete": (_t("Instalează listele din imagine"),
			_t("Deschide asistentul listelor gata făcute din imagine.")),
		"satelit": (_t("Caută canalele pe satelit"),
			_t("Deschide Scanare, Satelit, După satelit: toate transponderele unui satelit al antenei.")),
		"cablu": (_t("Caută canalele prin cablu"),
			_t("Deschide Scanare, Cablu, După operator: întâi operatorii din țara ta.")),
		"terestru": (_t("Caută canalele terestre"),
			_t("Deschide Scanare, Terestru, După regiune sau operator.")),
		"import": (_t("Importă canalele de pe un stick"),
			_t("Deschide Import canale și setări: o copie de pe stick sau din altă imagine.")),
	}[cheie]


def text_intro(cu_liste):
	if cu_liste:
		return _t("Imaginea are liste de canale gata făcute. Canalele se pot găsi și cu o scanare sau se pot aduce "
			"dintr-o copie de pe stick.")
	return _t("Această imagine nu are încă liste de canale gata făcute. Canalele se găsesc cu o scanare, pe satelit, "
		"prin cablu sau terestru, sau se aduc dintr-o copie de pe stick.")


def actiuni(are_tuner, cu_liste=False):
	"""Rândurile: [{"cheie", "text", "explicatie", "web"}]; scanările numai pentru tunerele pe care le are receptorul
	(are_tuner(tip) -> bool), importul mereu."""
	rez = []
	if cu_liste:
		text, explicatie = texte_actiune("pachete")
		rez.append({"cheie": "pachete", "text": text, "explicatie": explicatie, "web": ""})
	for cheie, tip, _modul, _clasa, _fel, web in ACTIUNI:
		if tip is not None and not are_tuner(tip):
			continue
		text, explicatie = texte_actiune(cheie)
		rez.append({"cheie": cheie, "text": text, "explicatie": explicatie, "web": web})
	return rez


def are_tuner(tip):
	try:
		from Components.NimManager import nimmanager
		return bool(nimmanager.hasNimType(tip))
	except Exception:
		return True


def _nimic():
	pass


class HdsListeImplicite(Screen):
	"""Rândurile din actiuni(); OK sau Verde deschide ecranul rândului luminat."""

	def __init__(self, session):
		Screen.__init__(self, session)
		from Components.ActionMap import ActionMap
		from Components.Label import Label
		from Components.Sources.List import List
		from Components.Sources.StaticText import StaticText
		from Screens.ScanerCablu import skin_rezerva, culoare_valoare, fonturi_texte, TASTE_RIDICATE
		self.skin = skin_rezerva("HdsListeImplicite", {"eticheta": 744})
		self._fonturi = fonturi_texte("HdsListeImplicite")
		self.cu_liste = are_liste()
		self.actiuni = actiuni(are_tuner, self.cu_liste)
		culoare = culoare_valoare()
		self["lista"] = List([(a["text"], a["cheie"], "", culoare) for a in self.actiuni], enableWrapAround=True)
		self["preview"] = Label("")
		self["stare"] = Label(_t("Alege cu săgețile și apasă OK."))
		self["key_red"] = StaticText(_t("Înapoi"))
		self["key_green"] = StaticText(_t("Deschide"))
		# tastele nefolosite rămân goale (skinul de rezervă le cere pe toate patru, fără text nu se văd)
		self["key_yellow"] = StaticText("")
		self["key_blue"] = StaticText("")
		actiuni_taste = {
			"ok": self.deschide,
			"green": self.deschide,
			"cancel": self.close,
			"red": self.close,
			"up": self.sus,
			"down": self.jos,
			"upRepeated": self.sus,
			"downRepeated": self.jos,
			"left": _nimic,
			"right": _nimic,
		}
		actiuni_taste.update((nume, _nimic) for nume in TASTE_RIDICATE)
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], actiuni_taste, -1)
		# titlul intrării din meniu (data/menu.xml, default_lists): duce și la cablu, terestru și import, nu numai la
		# sateliți
		self.setTitle(_t("Liste implicite de canale"))
		# rândul luminat se știe abia după ce lista e desenată
		self.onLayoutFinish.append(self._arataExplicatia)

	def _cheie(self):
		curent = self["lista"].getCurrent()
		return curent[1] if curent else None

	def _arataExplicatia(self):
		cheie = self._cheie()
		explicatie = texte_actiune(cheie)[1] if cheie else ""
		self["preview"].setText(text_intro(self.cu_liste) + ("\n\n" + explicatie if explicatie else ""))
		# cu fonturile mărite (Mărimea textului peste 100 %) textul care nu mai încape se scrie mai mic
		from Screens.ScanerCablu import potriveste_textul
		for nume in ("preview", "stare"):
			potriveste_textul(self[nume], *self._fonturi[nume])

	def sus(self):
		self["lista"].selectPrevious()
		self._arataExplicatia()

	def jos(self):
		self["lista"].selectNext()
		self._arataExplicatia()

	def deschide(self):
		cheie = self._cheie()
		if cheie == "pachete":
			from Screens.ScanSetup import DefaultSatLists
			self.session.open(DefaultSatLists)
			return
		for c, _tip, modul, clasa, fel, _web in ACTIUNI:
			if c == cheie:
				import importlib
				ecran = getattr(importlib.import_module(modul), clasa)
				if fel is None:
					self.session.open(ecran)
				else:
					self.session.open(ecran, fel)
				return
