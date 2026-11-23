# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAspectLista.py (0.7.5): „Aspectul listei de canale” (config.usage.hds_aspect_lista; Setări > Personalizare, langa
# „Rânduri pe pagină” si „Mărimea textului în lista de canale”; in web /setari?id=usage).
#   „Obișnuit” (din fabrica): ecranele de pana acum ale temei (HdsListaCanale, HdsListaCanaleRadio, HdsListaCanaleSimpla).
#   „Lista mare”: aceleasi ecrane cu „Mare” in nume (HdsListaCanaleMare...): pe tot ecranul, lista pe ~2/3 in stanga, imaginea
#   canalului si ghidul in dreapta, tastele colorate in dreapta jos. Daca tema nu are ecranul mare (o tema straina), skin.readSkin
#   trece la urmatorul nume din skinName, deci ramane lista obisnuita a temei.
# Listele radio si cea simpla se fac la fiecare deschidere, deci iau ecranul ales din skinName (ecrane()). Lista TV a barei se face
# o data, la pornire (InfoBarGenerics: InfoBar.servicelist); la schimbarea setarii ecranul ei se reface pe loc, fara repornire si
# fara sa se ruleze iar constructorul (ca rezerva temelor straine din mytest.py, ecranCuRezerva): numai cat lista nu se vede;
# schimbata din web cu lista deschisa pe televizor, se reface la prima inchidere a listei.

PREFIX = "HdsListaCanale"
SUFIX_MARE = "Mare"


def initCompatLista(usage):
	"""Expune numele compatibile fara preferinte duble sau notificari recursive."""
	from Components.config import ConfigSelection, ConfigYesNo

	class Punte:
		def leaga(self, tinta, citeste, scrie):
			self.tinta, self.citeste, self.scrie = tinta, citeste, scrie
			self._initializare = True
			self._ultima = citeste(tinta.value)

		def getValue(self):
			return self.citeste(self.tinta.value)

		def setValue(self, value):
			if not self._initializare:
				noua = self.scrie(value)
				if noua != self.tinta.value:
					self.tinta.value = noua

		value = property(getValue, setValue)

		def save(self):
			self.tinta.save()
			self.saved_value = None

		def load(self):
			# ConfigSubsection incarca numele vechi salvat la instalarea puntii.
			if self.saved_value is not None:
				if self.tinta.saved_value is None:
					self.setValue(self.saved_value)
					self.tinta.save()
				self.saved_value = None
			else:
				self.tinta.load()

		def cancel(self):
			self.tinta.cancel()

		def isChanged(self):
			return self.tinta.isChanged()

		def getSavedValue(self):
			v = self.tinta.saved_value
			return None if v is None else self.tostring(self.citeste(self.tinta.fromstring(v)))

		def setSavedValue(self, value):
			self.tinta.saved_value = None if value is None else self.tinta.tostring(self.scrie(value))

		def schimba(self, element):
			noua = self.getValue()
			if noua != self._ultima:
				self._ultima = noua
				self._descr = None
				self.changed()

	class DouaRanduri(Punte, ConfigYesNo):
		def __init__(self):
			def scrie(v):
				activ = v is True or v == 1 or isinstance(v, str) and v.lower() in ("true", "1", "yes")
				return ("mare_doua_randuri" if activ else "mare") if usage.hds_aspect_lista.value in (
					"mare", "mare_doua_randuri") else (
					"doua_randuri" if activ else "obisnuit")
			self.leaga(usage.hds_aspect_lista, lambda v: v in ("doua_randuri", "mare_doua_randuri"), scrie)
			ConfigYesNo.__init__(self, default=False)
			self._initializare = False
			self.tinta.addNotifier(self.schimba, initial_call=False)

	class Randuri(Punte, ConfigSelection):
		def __init__(self):
			def scrie(v):
				# Numai intregi zecimali; valorile gresite sau excesive inseamna tema.
				s = str(v)
				return s if s in usage.hds_randuri_lista.choices else "tema"
			def citeste(v):
				return int(v) if v != "tema" and v in usage.hds_randuri_lista.choices else 0
			self.leaga(usage.hds_randuri_lista, citeste, scrie)
			ConfigSelection.__init__(self, choices=list(range(41)), default=0)
			self._initializare = False
			self.tinta.addNotifier(self.schimba, initial_call=False)

	usage.servicelist_twolines = DouaRanduri()
	usage.serviceitems_per_page = Randuri()


def sablonDouaRanduri(latime, inaltime, fonturi, numar, progres):
	"""Face doua randuri prin mecanismul de sabloane existent al imaginii."""
	from xml.etree.ElementTree import Element, SubElement
	root = Element("template", component="serviceList", fonts=",".join(
		"%s;%d" % (f.family, f.pointSize) for f in fonturi))
	jumatate = inaltime // 2
	numar = max(0, min(numar, latime // 4))
	icon = max(1, min(96, inaltime * 2, latime // 4))
	for mod in ("services", "bouquets", "other"):
		m = SubElement(root, "mode", name=mod, itemHeight=str(inaltime))
		def text(index, x, y, w, h, font):
			SubElement(m, "text", index=index, position="%d,%d" % (x, y),
				size="%d,%d" % (w, h), font=str(font), verticalAlignment="center")
		text("Number", 0, 0, numar, inaltime, 2)
		start = numar + 10 if numar else 0
		for index in ("Picon", "FolderImage", "MarkerImage"):
			SubElement(m, "pixmap", index=index, position="%d,0" % start,
				size="%d,%d" % (icon, inaltime), alpha="blend", scale="centerScaled")
		start = min(latime - 1, start + icon + 10)
		text("ServiceName", start, 0, max(1, latime - start), jumatate, 0)
		text("Title1", start, jumatate, max(1, latime - start), inaltime - jumatate, 1)
		rec = max(1, min(inaltime // 4, 24))
		SubElement(m, "pixmap", index="RecordingIndicator", position="%d,0" % max(0, latime - rec),
			size="%d,%d" % (rec, rec), alpha="blend", scale="centerScaled")
		if progres:
			SubElement(m, "progress", index="Progress", position="%d,%d" % (start, inaltime - 2),
				size="%d,2" % max(1, latime - start), borderWidth="0")
	return root


def potrivesteSablon(sablon, inaltime):
	"""Potriveste copia sablonului temei la numarul cerut, fara a modifica tema."""
	from enigma import gFont
	limite = {}
	for nume, (veche, tupluri) in list(sablon.moduri.items()):
		rez = []
		for t in tupluri:
			y = max(0, min(inaltime - 1, t[2] * inaltime // max(1, veche)))
			h = max(1, min(inaltime - y, t[4] * inaltime // max(1, veche)))
			rez.append(t[:2] + (y, t[3], h) + t[5:])
			if t[0] == 0 and t[7] != "":
				limite[t[5]] = min(limite.get(t[5], 10000), max(1, (h - 4) * 7 // 10))
		sablon.moduri[nume] = (inaltime, rez)
	sablon.fonturi = [gFont(f.family, min(f.pointSize, limite.get(i, f.pointSize)))
		for i, f in enumerate(sablon.fonturi)]


def mare():
	try:
		from Components.config import config
		return getattr(getattr(config.usage, "hds_aspect_lista", None), "value", "obisnuit") in ("mare", "mare_doua_randuri")
	except Exception:
		return False


def numeMare(nume):
	"""HdsListaCanale -> HdsListaCanaleMare, HdsListaCanaleRadio -> HdsListaCanaleMareRadio"""
	if not nume.startswith(PREFIX) or nume.startswith(PREFIX + SUFIX_MARE):
		return None
	return PREFIX + SUFIX_MARE + nume[len(PREFIX):]


def ecrane(nume):
	"""skinName pentru o lista a imaginii: [ecranul mare] + nume cu „Lista mare”, altfel nume (o copie)."""
	nume = [n for n in nume if not n.startswith(PREFIX + SUFIX_MARE)]
	if mare():
		mari = [m for m in (numeMare(n) for n in nume) if m]
		# chiar inaintea primului ecran al listei: ce sta inaintea lui (stilul ales al unei teme straine) ramane primul
		i = next((k for k, n in enumerate(nume) if n.startswith(PREFIX)), 0)
		return nume[:i] + mari + nume[i:]
	return nume


def _listaTv():
	try:
		from Screens.InfoBar import InfoBar
		return getattr(InfoBar.instance, "servicelist", None) if InfoBar.instance is not None else None
	except Exception:
		return None


def reface(ecran):
	"""Ecranul (deja facut) primeste asezarea aleasa: skinName nou, tema citita din nou, aceleasi componente si surse.
	-> True daca s-a refacut acum, False daca nu era nevoie sau ramane pentru prima inchidere a listei."""
	if ecran is None or getattr(ecran, "instance", None) is None:
		return False
	dorit = ecrane(list(ecran.skinName) if isinstance(ecran.skinName, (list, tuple)) else [ecran.skinName])
	if list(dorit) == list(ecran.skinName if isinstance(ecran.skinName, (list, tuple)) else [ecran.skinName]):
		return False
	if getattr(ecran, "shown", False):
		# schimbata din web cu lista pe televizor: la prima inchidere
		ecran.hdsAspectAsteapta = True
		if not getattr(ecran, "hdsAspectLegat", False):
			ecran.hdsAspectLegat = True
			ecran.onHide.append(lambda: _dupaInchidere(ecran))
		return False
	from skin import readSkin
	desktop = ecran.desktop
	lista = getattr(ecran, "servicelist", None)
	curent = None
	try:
		curent = lista.getCurrent() if lista is not None and lista.instance is not None else None
	except Exception:
		curent = None
	for r in list(getattr(ecran, "renderer", [])):
		try:
			r.disconnectAll()
		except Exception as e:
			print("[HdsAspectLista] disconnectAll: %s" % e)
		try:
			if getattr(r, "instance", None) is not None:
				r.GUIdelete()
		except Exception as e:
			print("[HdsAspectLista] GUIdelete: %s" % e)
	ecran.deleteGUIScreen()
	ecran.instance = None
	ecran.onLayoutFinish[:] = [f for f in ecran.onLayoutFinish if callable(f)]
	ecran.skinName = dorit
	readSkin(ecran, None, ecran.skinName, desktop)
	ecran.setDesktop(desktop)
	ecran.applySkin()
	# lista noua (eListbox) porneste de la primul rand: cursorul inapoi pe canalul de dinainte
	try:
		if curent is not None and curent.valid() and lista is not None and lista.instance is not None:
			lista.setCurrent(curent)
	except Exception as e:
		print("[HdsAspectLista] cursorul: %s" % e)
	print("[HdsAspectLista] lista de canale refacuta: %s" % ecran.skinName[0])
	return True


def _dupaInchidere(ecran):
	if not getattr(ecran, "hdsAspectAsteapta", False):
		return
	ecran.hdsAspectAsteapta = False
	# dupa ascunderea de acum (onHide ruleaza in timpul hide()): cu un ceas de 0, ca ecranul sa fie deja ascuns
	try:
		from enigma import eTimer
		ceas = eTimer()

		def _acum():
			ecran.hdsAspectCeas = None
			reface(ecran)
		ceas.callback.append(_acum)
		ecran.hdsAspectCeas = ceas
		ceas.start(0, True)
	except Exception as e:
		print("[HdsAspectLista] dupa inchidere: %s" % e)


def laSchimbare(configElement=None):
	"""notifierul setarii (Components/UsageConfig.py): lista TV a barei se reface pe loc (sau la prima inchidere)"""
	try:
		reface(_listaTv())
	except Exception as e:
		import traceback
		print("[HdsAspectLista] refacerea listei: %s" % e)
		traceback.print_exc()
