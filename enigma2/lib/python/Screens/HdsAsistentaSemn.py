# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistentaSemn.py: semnul de pe ecran cat Asistenta de la distanta e activa si legatura cu receptorul (partea care
# are nevoie de enigma2). Logica e in Components/HdsAsistenta.py (fara enigma); aici sunt:
#   - banda mica de sus, mereu deasupra (fereastra nemodala, ca mesajul de retea): „Asistenta activa, mai sunt H:MM:SS"
#     si, dedesubt, calea spre Oprire (Meniu > Setari > Retea si internet > Asistenta de la distanta); se vede si peste
#     imaginea pe tot ecranul si peste meniuri;
#   - Controler: un observator care arata, improspateaza (o data pe secunda) si ascunde banda; tot el culege, pe firul
#     enigma2, mesajele cerute de operator (op „mesaj") si le arata cu HdsAnuntRetea, fiindca brokerul ruleaza pe alt
#     fir si nu are voie sa atinga interfata direct;
#   - ctxReceptor(session): uneltele date brokerului care au nevoie de receptor: captura numai a meniurilor (OSD),
#     refuzata cat ecranul „Acces SSH" e deschis (parola lui root pe ecran), si punerea unui mesaj pe ecran;
#   - porneste(...) si reia(session): pornirea unei sesiuni cu ctx-ul potrivit (din ecranul TV sau din web) si reluarea
#     dupa repornirea interfetei (chemata din mytest.py).
# Nu se importa la incarcarea mytest.py nimic greu; functiile se cheama la nevoie.

import subprocess

from enigma import eActionMap, eTimer, getDesktop

from Screens.Screen import Screen
from Components.Sources.StaticText import StaticText
from Components import HdsAsistenta as A

GRAB = "/usr/bin/grab"
CAPTURA_TERMEN_S = 8
CAPTURA_LATIME = 1280


def _jurnal(text):
	print("[HdsAsistentaSemn] %s" % text)


def _hms(secunde):
	secunde = max(0, int(secunde))
	return "%d:%02d:%02d" % (secunde // 3600, (secunde % 3600) // 60, secunde % 60)


# ---------------------------------------------------------------- banda de semn (fereastra nemodala)

def _skinBanda(latime, inaltime):
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))

	lat = x(1240)
	return """
	<screen name="HdsAsistentaSemn" position="%d,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#00101828" zPosition="20">
		<eLabel position="0,0" size="%d,%d" backgroundColor="#00c0392b" zPosition="1" />
		<widget source="text" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="center" foregroundColor="#00ffffff" backgroundColor="#00101828" transparent="1" zPosition="2" />
		<widget source="cale" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="center" foregroundColor="#00c8d0d8" backgroundColor="#00101828" transparent="1" zPosition="2" />
	</screen>""" % (
		(latime - lat) // 2, y(14), lat, y(84),
		lat, max(2, y(3)),
		x(18), y(6), lat - x(36), y(40), y(26),
		x(18), y(46), lat - x(36), y(32), y(20))


class HdsAsistentaSemn(Screen):
	def __init__(self, session):
		marime = getDesktop(0).size()
		self.skin = _skinBanda(marime.width(), marime.height())
		Screen.__init__(self, session)
		self["text"] = StaticText("")
		self["cale"] = StaticText("")

	def pune(self, text, cale=""):
		self["text"].setText(text)
		self["cale"].setText(cale)


# ---------------------------------------------------------------- controlerul (observator + ceas + mesaje)

class Controler(object):
	def __init__(self, session):
		self.session = session
		self.banda = None
		self.ceas = eTimer()
		self.ceas.callback.append(self._tic)
		self._mesaje = []

	def instaleaza(self):
		A.adaugaObservator(self._schimbare)
		self._schimbare()

	def cereMesaj(self, text):
		"""Chemata de pe firul sesiunii (brokerul): pune un mesaj in coada; _tic il arata pe firul enigma2."""
		self._mesaje.append(text)

	def _schimbare(self):
		ses = A.sesiune()
		if ses is not None and ses.activa():
			if self.banda is None:
				try:
					self.banda = self.session.instantiateDialog(HdsAsistentaSemn)
				except Exception as e:
					_jurnal("banda: %r" % (e,))
			self._tic()
			self.ceas.start(1000, False)
		else:
			self.ceas.stop()
			if self.banda is not None:
				try:
					self.banda.hide()
				except Exception:
					pass

	def _tic(self):
		ses = A.sesiune()
		if ses is None or not ses.activa():
			self.ceas.stop()
			if self.banda is not None:
				self.banda.hide()
			return
		while self._mesaje:
			text = self._mesaje.pop(0)
			self._arataMesaj(text)
		if self.banda is not None:
			self.banda.pune("%s  ·  %s %s" % (_("Asistență de la distanță activă"), _("mai sunt"), _hms(ses.ramasS())),
				_("Oprești din %s") % A.drumMeniu())
			self.banda.show()

	def _arataMesaj(self, text):
		try:
			from Screens import HdsAnuntRetea
			HdsAnuntRetea.arata(self.session, "%s %s" % (_("Mesaj de la HD Satelit:"), text), "info")
		except Exception as e:
			_jurnal("mesaj: %r" % (e,))


_controler = [None]


def instaleaza(session):
	"""Chemata o data din mytest.py: pregateste controlerul semnului si reia o sesiune ramasa (dupa o repornire a
	interfetei)."""
	if _controler[0] is None:
		_controler[0] = Controler(session)
		_controler[0].instaleaza()
	reia(session)


# ---------------------------------------------------------------- uneltele receptorului date brokerului

def _captura():
	"""O captura numai a meniurilor (OSD), ca octeti PNG; None cand nu se poate sau cand ecranul „Acces SSH" e deschis."""
	try:
		from Components import HdsAccesSsh
		if HdsAccesSsh.ecranDeschis():
			return None
	except Exception:
		pass
	try:
		p = subprocess.Popen([GRAB, "-o", "-s", "-r", str(CAPTURA_LATIME)], stdout=subprocess.PIPE,
			stderr=subprocess.DEVNULL)
	except Exception:
		return None
	try:
		iesire, _err = p.communicate(timeout=CAPTURA_TERMEN_S)
	except subprocess.TimeoutExpired:
		try:
			p.kill()
		except Exception:
			pass
		return None
	return iesire or None


def ctxReceptor(session):
	ctx = {}
	ctx["captura"] = _captura
	if _controler[0] is not None:
		ctx["mesaj"] = _controler[0].cereMesaj
	else:
		ctx["mesaj"] = lambda t: None
	return ctx


# ---------------------------------------------------------------- pornirea si reluarea

def porneste(session, nivel="A", durata_min=None, de_la="televizor", versiune_text=None):
	if versiune_text is None:
		versiune_text = A.VERSIUNE_TEXT
	if durata_min is None:
		durata_min = A.DURATA_IMPLICITA_MIN
	limba = _limba()
	return A.porneste(nivel=nivel, durata_min=durata_min, limba=limba, de_la=de_la,
		versiune_text=versiune_text, ctx=ctxReceptor(session))


def reia(session):
	try:
		A.reia(ctx=ctxReceptor(session))
	except Exception as e:
		_jurnal("reluare: %r" % (e,))


def cerereWeb(session, nivel="A", durata_min=None):
	"""Pornirea ceruta din pagina web (browserul omului, conectat cu codul de pe televizor): pe televizor se deschide
	ecranul Asistentei cu informarea intreaga si durata aleasa; abia dupa Verde, alegere si „Da" porneste sesiunea
	(nimic nu porneste fara apasare pe televizor). -> (reusit, mesaj) numai despre faptul ca s-a cerut confirmarea."""
	if session is None:
		return False, _("Nu pot cere confirmarea pe televizor acum.")
	if durata_min not in A.DURATE_MIN:
		durata_min = A.DURATA_IMPLICITA_MIN
	ses = A.sesiune()
	if ses is not None and ses.activa():
		return False, _("Asistența merge deja.")
	try:
		from Tools import Notifications
		from Screens.HdsAsistenta import HdsAsistenta
		Notifications.AddNotification(HdsAsistenta, din_web=durata_min)
		return True, _("Pe televizor s-a deschis Asistența de la distanță: citește și apasă Verde acolo.")
	except Exception as e:
		_jurnal("cerere web: %r" % (e,))
		return False, _("Nu pot cere confirmarea pe televizor acum.")


def _limba():
	try:
		from Components.Language import language
		return (language.getLanguage() or "ro")[:2]
	except Exception:
		return "ro"
