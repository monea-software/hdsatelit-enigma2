# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
"""Functiile imaginii, deschise din meniul potrivit si din web.

Ecranul, lista de setari si salvarea raman ale pachetului original.
Nu importam pluginul la simpla citire a meniului.
"""

import importlib
import os
import xml.etree.ElementTree as ET

FUNCTII = {
	"afisaj": ("SystemPlugins/VFDControl", "LED_GigaSetup",
		"Afișaj și LED", "save", "cancel"),
	"telecomanda": ("SystemPlugins/RemoteControlCode", "RemoteControlCode",
		"Codul telecomenzii", "keySave", "keyCancel"),
	"marcaje": ("Extensions/HdsCutListEditor", "HdsCutListEditor",
		"Editor marcaje", "close", "close"),
}
_deschise = {}


def disponibil(cheie, radacina=""):
	"""Numai cu pachetul din manifest si cu ecranul instalat pe model."""
	from Components.HdsPluginuriImagine import pluginImagine
	date = FUNCTII.get(cheie)
	if date is None or not pluginImagine(date[0], radacina):
		return False
	dosar = os.path.join(radacina, "usr/lib/enigma2/python/Plugins", date[0])
	if not radacina:
		dosar = "/" + dosar
	from importlib.machinery import EXTENSION_SUFFIXES
	nume = ("plugin.py", "plugin.pyc", "plugin.pyo", "plugin.so")
	nume += tuple("plugin" + s for s in EXTENSION_SUFFIXES)
	return any(os.path.isfile(os.path.join(dosar, n)) for n in nume)


def deschide(session, cheie):
	"""Deschide ecranul original, inclusiv confirmarile si revenirea lui."""
	if not disponibil(cheie):
		raise ValueError("Funcția nu este disponibilă pe acest receptor.")
	if cheie == "marcaje":
		serviciu = session.nav.getCurrentService()
		if serviciu is None or serviciu.cueSheet() is None or serviciu.seek() is None:
			raise ValueError("Pornește o înregistrare cu marcaje, apoi deschide editorul.")
	vechi = _deschise.get(cheie)
	if vechi is not None:
		if getattr(session, "current_dialog", None) is vechi:
			return vechi
		raise ValueError("Închide mai întâi fereastra de pe televizor.")
	date = FUNCTII[cheie]
	modul = importlib.import_module("Plugins." + date[0].replace("/", ".") + ".plugin")
	ecran = session.open(getattr(modul, date[1]))
	if ecran is None:
		raise ValueError("Ecranul nu s-a putut deschide.")
	_deschise[cheie] = ecran
	if cheie == "marcaje":
		ecran._hdsReferintaWeb = _referinta(session)

	def inchis():
		if _deschise.get(cheie) is ecran:
			_deschise.pop(cheie, None)
	ecran.onClose.append(inchis)
	return ecran


def ecranCurent(session, cheie):
	"""Webul poate modifica numai ecranul sau, cat timp este in fata."""
	ecran = _deschise.get(cheie)
	if ecran is not None and getattr(session, "current_dialog", None) is ecran:
		return ecran
	return None


def ecranDeschis(session, cheie):
	"""Ecranul detinut de acest adaptor, inclusiv sub confirmarea lui."""
	ecran = _deschise.get(cheie)
	if ecran is None:
		return None
	if ecranCurent(session, cheie) is ecran:
		return ecran
	for rand in getattr(session, "dialog_stack", ()):
		if rand and rand[0] is ecran:
			return ecran
	return None


def randuri(ecran):
	try:
		return list(ecran["config"].list or [])
	except (KeyError, TypeError, AttributeError):
		return []


def incheie(session, cheie, salveaza):
	ecran = ecranCurent(session, cheie)
	if ecran is None:
		raise ValueError("Revino la setări pe televizor și încearcă din nou.")
	date = FUNCTII[cheie]
	getattr(ecran, date[3] if salveaza else date[4])()


def schimba(session, cheie, nr, semn, text, S):
	"""Aceeasi setare ConfigElement, cu notificatorii ecranului original."""
	ecran = ecranCurent(session, cheie)
	lista = randuri(ecran)
	if ecran is None or nr < 0 or nr >= len(lista) or len(lista[nr]) < 2:
		raise ValueError("Lista setărilor s-a schimbat. Reîncarcă pagina.")
	rand = lista[nr]
	el = rand[1]
	if semn != str(id(el)):
		raise ValueError("Lista setărilor s-a schimbat. Reîncarcă pagina.")
	if not getattr(el, "enabled", True):
		raise ValueError("Această setare este dezactivată pe televizor.")
	nod = ET.Element("item", text=str(rand[0]))
	fel = S._fel(el, nod)
	if fel not in ("bool", "alegere", "numar", "glisor", "cifre"):
		raise ValueError("Această setare se schimbă de pe televizor.")
	valoare = S._valoareNoua(el, fel, text)
	if valoare is None:
		raise ValueError("Valoarea nu este în lista setării.")
	ecran["config"].setCurrentIndex(nr)
	el.value = valoare
	if hasattr(el, "changedFinal"):
		el.changedFinal()
	if hasattr(ecran, "newConfig"):
		ecran.newConfig()
	if hasattr(ecran, "changedEntry"):
		ecran.changedEntry()
	ecran["config"].invalidate(rand)


def _referinta(session):
	try:
		ref = session.nav.getCurrentlyPlayingServiceReference()
		return ref.toString() if ref is not None else ""
	except AttributeError:
		return ""


def _editorMarcaje(session):
	ecran = ecranCurent(session, "marcaje")
	if ecran is None:
		raise ValueError("Revino la editorul de marcaje pe televizor și încearcă din nou.")
	if getattr(ecran, "_hdsReferintaWeb", "") != _referinta(session):
		raise ValueError("Filmul s-a schimbat. Închide editorul și deschide-l din nou.")
	return ecran


def marcaje(session):
	"""Lista reala a editorului, fara recitire care ar muta selectia de pe televizor."""
	ecran = _editorMarcaje(session)
	modul = importlib.import_module("Plugins.Extensions.HdsCutListEditor.plugin")
	nume = modul._numeTip()
	lista = [{"pts": str(pts), "tip": int(tip),
		"text": "%s · %s" % (modul._formatTimp(pts), nume.get(tip, str(tip)))}
		for pts, tip in ecran._cut_list]
	return {"marcaje": lista, "pozitie": modul._formatTimp(ecran._pozitiaCurenta())}


def actiuneMarcaje(session, operatie, pts=None, tip=None):
	"""Metodele editorului original pastreaza scrierea si confirmarile lui."""
	ecran = _editorMarcaje(session)
	if operatie == "adauga-marcaj":
		ecran._adaugaMarcaj()
	elif operatie in ("start", "stop"):
		ecran._alesStartStop((operatie, 0 if operatie == "start" else 1))
	elif operatie in ("sari", "sterge"):
		try:
			punct = (int(pts), int(tip))
			index = ecran._cut_list.index(punct)
		except (TypeError, ValueError):
			raise ValueError("Marcajele s-au schimbat. Reîncarcă lista.")
		ecran["lista"].moveToIndex(index)
		if ecran._selectat() != punct:
			raise ValueError("Selecția nu este pregătită pe televizor. Încearcă din nou.")
		if operatie == "sari":
			ecran._sariLaSelectie()
		else:
			ecran._stergeSelectie()
	else:
		raise ValueError("Acțiunea nu este disponibilă.")
