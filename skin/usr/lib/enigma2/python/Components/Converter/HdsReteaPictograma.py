# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
# Convertorul skinului HDSatelit pentru pictograma retelei din bare (din 0.4.4): cablu sau Wi-Fi (cu
# treptele semnalului) si starea: internetul merge / routerul nu are internet / fara legatura cu routerul / se verifica.
#
#   <widget source="session.CurrentService" render="Pixmap" position=".." size="48,36" alphatest="blend">
#     <convert type="HdsReteaPictograma">Pictograma</convert></widget>
#
# Tipuri: Pictograma (pixmap = HDSatelit/retea/<cheie>.png, 48x36, text = cheia), Pictograma2x (aceeasi stare, 96x72),
# Text (textul scurt al starii, ca ajutorul din web).
#
# Starea vine din Components/HdsStareRetea.py (numai pe imaginea HDSatelit: citirea pasiva si verificarea pe firul ei).
# Convertorul nu intreaba reteaua si nu porneste fire: citeste memoria modulului. Pe alte imagini (fara modul) se
# arata numai felul legaturii (cablu sau Wi-Fi), dupa ruta implicita (HdsCommon.net_default), fara insigna.
# Cronometrul merge numai cat widgetul se vede; cat se vede, modulul stie ca pictograma e pe ecran (atunci nu mai
# arata mesajul de pe mijlocul ecranului la pierderea internetului).
#
# Setarea "Arata pictograma internetului in bare" (config.usage.hds_internet_pictograma, din fabrica da): oprita,
# widgetul pictogramei nu se vede si nu conteaza ca pictograma pe ecran (mesajul de pe mijlocul ecranului apare dupa
# regula lui). Dupa "|", argumentul poate avea regulile vecinilor care isi iau inapoi locul cat pictograma e ascunsa
# (Components/HdsPictogramaBare.py, numai pe imaginea HDSatelit); convertorul nu le foloseste.
from __future__ import absolute_import

from Components.Converter.Converter import Converter
from Components.Converter.Poll import Poll
from Components.Element import cached

try:
	from Components.Converter import HdsCommon as C
except Exception as _e:
	C = None
	print("[HdsReteaPictograma] HdsCommon lipseste: %s" % _e)

TIPURI = ("Pictograma", "Pictograma2x", "Text")
INTERVAL_MS = 2000
DOSAR = "retea/"


def _modul():
	try:
		from Components import HdsStareRetea
		return HdsStareRetea
	except ImportError:
		return None


def stare_acum():
	"""Starea pentru pictograma: din HdsStareRetea; pe alte imagini numai felul legaturii, fara raspuns despre
	internet (cod None = fara insigna) sau, fara ruta implicita, fara legatura."""
	m = _modul()
	if m is not None:
		try:
			return m.stare()
		except Exception as e:
			if C is not None:
				C.log_once("HdsReteaPictograma stare", e)
	iface, ip, wifi = C.net_default() if C is not None else (u"", u"", False)
	if not iface:
		return {"cod": "fara_router", "fel": "cablu", "treapta": 0}
	return {"cod": None, "fel": "wifi" if wifi else "cablu", "treapta": 0}


def cheie(st):
	m = _modul()
	if m is not None:
		return m.cheie_pictograma(st)
	fel = st.get("fel") or "cablu"
	if st.get("cod") == "fara_router":
		return "%s_fara_router" % fel
	return "%s_verific" % fel


def text_stare(st):
	m = _modul()
	if m is not None:
		return m.text_ajutor(st)
	return u""


def aratata():
	"""Setarea "Arata pictograma internetului in bare" (HdsStareRetea.pictograma_aratata); pe alte imagini mereu da."""
	m = _modul()
	if m is None:
		return True
	try:
		return bool(m.pictograma_aratata())
	except Exception:
		return True


class HdsReteaPictograma(Poll, Converter):
	def __init__(self, arg):
		Converter.__init__(self, arg)
		Poll.__init__(self)
		# dupa "|" pot veni regulile vecinilor (Components/HdsPictogramaBare.py)
		self._tip = str(arg or "").split("|")[0].split(",")[0].strip()
		if self._tip not in TIPURI:
			print("[HdsReteaPictograma] tip necunoscut: %r" % (arg,))
			self._tip = "Pictograma"
		self._cheie = None
		self._text = u""
		self._vazut = False
		self._activ = False
		self._aratata = True if self._tip == "Text" else aratata()
		self.poll_interval = INTERVAL_MS

	def connectDownstream(self, downstream):
		Converter.connectDownstream(self, downstream)
		# pictograma ascunsa din setari: widgetul nu se vede de la inceput
		if not self._aratata:
			try:
				downstream.visible = False
			except Exception:
				pass

	def _potriveste(self):
		"""Setarea citita din nou; cand s-a schimbat, widgetul pictogramei se arata sau se ascunde. -> True la schimbare."""
		if self._tip == "Text":
			return False
		a = aratata()
		if a == self._aratata:
			return False
		self._aratata = a
		for x in self.downstream_elements:
			try:
				x.visible = a
			except Exception:
				pass
		return True

	def _citeste(self):
		try:
			st = stare_acum()
			k = cheie(st)
			t = text_stare(st) if self._tip == "Text" else u""
		except Exception as e:
			if C is not None:
				C.log_once("HdsReteaPictograma", e)
			k, t = "cablu_verific", u""
		schimbat = k != self._cheie or t != self._text
		self._cheie = k
		self._text = t
		return schimbat

	def _pe_ecran(self, da):
		m = _modul()
		if m is None or self._vazut == da:
			return
		self._vazut = da
		try:
			if da:
				m.arata_pictograma(id(self))
			else:
				m.ascunde_pictograma(id(self))
		except Exception:
			pass

	def doSuspend(self, suspended):
		try:
			self._activ = not suspended
			if suspended:
				self.poll_enabled = False
				self._pe_ecran(False)
			else:
				self._potriveste()
				self._pe_ecran(self._aratata)
				self.poll_enabled = True
				self._citeste()
				Converter.changed(self, (self.CHANGED_POLL,))
		except Exception as e:
			if C is not None:
				C.log_once("HdsReteaPictograma doSuspend", e)

	def changed(self, what):
		try:
			if what[0] == self.CHANGED_POLL:
				if self._potriveste() and self._activ:
					self._pe_ecran(self._aratata)
				if not self._citeste():
					return   # aceeasi poza: nimic de redesenat
			elif what[0] == self.CHANGED_SPECIFIC:
				return       # evenimentele canalului nu schimba reteaua
			Converter.changed(self, what)
		except Exception as e:
			if C is not None:
				C.log_once("HdsReteaPictograma changed", e)

	@cached
	def getText(self):
		if self._cheie is None:
			self._citeste()
		return (self._text if self._tip == "Text" else self._cheie) or u""

	text = property(getText)

	@cached
	def getBoolean(self):
		return bool(self.getText())

	boolean = property(getBoolean)

	@cached
	def getPixmap(self):
		if self._cheie is None:
			self._citeste()
		try:
			from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
			from Tools.LoadPixmap import LoadPixmap
			nume = DOSAR + self._cheie + ("@2x" if self._tip == "Pictograma2x" else "") + ".png"
			return LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, nume), cached=True)
		except Exception as e:
			if C is not None:
				C.log_once("HdsReteaPictograma poza", e)
			return None

	pixmap = property(getPixmap)

	def destroy(self):
		try:
			self.poll_enabled = False
			self._pe_ecran(False)
		except Exception:
			pass
		try:
			Poll.destroy(self)
		except Exception:
			pass
		try:
			Converter.destroy(self)
		except Exception:
			pass
