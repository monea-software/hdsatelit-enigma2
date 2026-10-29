# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistentaSemn.py: semnul de pe ecran cat Asistenta de la distanta e activa si legatura cu receptorul (partea care
# are nevoie de enigma2). Logica e in Components/HdsAsistenta.py (fara enigma); aici sunt:
#   - banda mica de sus, mereu deasupra (fereastra nemodala, ca mesajul de retea), pe un singur rand: "Asistenta
#     activa, mai sunt H:MM:SS" si calea spre Oprire (Meniu > Setari > Beta tester > Cere ajutor de la distanta); se
#     vede si peste imaginea pe tot ecranul si peste meniuri, deasupra randului cu titlul ferestrelor (nu il acopera);
#     cat ecranul asistentei e deschis (el arata starea si timpul), banda se ascunde;
#   - Controler: un observator care arata, improspateaza (o data pe secunda) si ascunde banda; tot el culege, pe firul
#     enigma2, mesajele cerute de operator (op „mesaj") si le arata cu HdsAnuntRetea, fiindca brokerul ruleaza pe alt
#     fir si nu are voie sa atinga interfata direct;
#   - ctxReceptor(session): uneltele date brokerului care au nevoie de receptor: captura numai a meniurilor (OSD),
#     refuzata cat ecranul „Acces SSH" e deschis (parola lui root pe ecran), si punerea unui mesaj pe ecran;
#   - porneste(...) si reia(session): pornirea unei sesiuni cu ctx-ul potrivit (din ecranul TV sau din web) si reluarea
#     dupa repornirea interfetei (chemata din mytest.py).
# Nu se importa la incarcarea mytest.py nimic greu; functiile se cheama la nevoie.

import subprocess

from enigma import eTimer

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

# Banda (si in skinul HDSatelit, HDSatelit/skin.xml, forma HdsAjutorDistantaSemn): un rand de 40 px la y 14, deasupra
# titlului ferestrelor mari (cadrul lor are titlul la y 58); textul si calea pe acelasi rand.
SKIN_BANDA = """
	<screen name="HdsAsistentaSemn" resolution="1920,1080" position="290,14" size="1340,40" flags="wfNoBorder" backgroundColor="#00101828" zPosition="20">
		<eLabel position="0,0" size="6,40" backgroundColor="#00c0392b" zPosition="1" />
		<widget source="text" render="Label" position="22,0" size="1300,40" font="Regular;24" halign="center" valign="center" foregroundColor="#00ffffff" backgroundColor="#00101828" transparent="1" noWrap="1" zPosition="2" />
	</screen>"""

# ecranele care arata ele starea asistentei: cat sunt deasupra, banda nu se arata (le-ar acoperi titlul)
ECRANE_FARA_BANDA = ("HdsAsistenta", "HdsAsistentaAlege")


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la folosire."""
	return text


# de unde se opreste, pe banda de sus (oricand, si la "permanent")
TEXT_OPRESTI = N_("Oprești oricând din %s")
# anuntul de pe ecran cand echipa aproba cererea (ecranul asistentei ii spunea omului "Te anunțăm când intrăm")
TEXT_CONECTAT = N_("Echipa HD Satelit s-a conectat. Poți folosi receptorul ca de obicei.")


class HdsAsistentaSemn(Screen):
	skin = SKIN_BANDA

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = "HdsAjutorDistantaSemn"
		self["text"] = StaticText("")

	def pune(self, text, cale=""):
		self["text"].setText("%s  ·  %s" % (text, cale) if cale else text)


# ---------------------------------------------------------------- controlerul (observator + ceas + mesaje)

class Controler(object):
	def __init__(self, session):
		self.session = session
		self.banda = None
		self.ceas = eTimer()
		self.ceas.callback.append(self._tic)
		self._mesaje = []
		self._stare_vazuta = None

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
		# cererea a fost aprobata (asteapta -> conectat): omul afla, oriunde ar fi pe receptor (pe ecranul asistentei
		# scrie deja "Conectat."); dupa o reluare a interfetei starea de dinainte nu se stie, deci nu se anunta
		if self._stare_vazuta == A.ASTEAPTA and ses.stare == A.CONECTAT and not self._ecranAsistenta():
			try:
				from Screens import HdsAnuntRetea
				HdsAnuntRetea.arata(self.session, _(TEXT_CONECTAT), "info")
			except Exception as e:
				_jurnal("anuntul conectarii: %r" % (e,))
		self._stare_vazuta = ses.stare
		if self.banda is not None:
			if self._ecranAsistenta():
				self.banda.hide()
				return
			# mereu: ca e pornita si pana cand ("până la ZZ.LL, HH:MM" / "fără sfârșit") si de unde se opreste
			self.banda.pune(A.textPana(ses, banda=True), _(TEXT_OPRESTI) % A.drumMeniu(scurt=True))
			self.banda.show()

	def _ecranAsistenta(self):
		"""Ecranul asistentei e deasupra (arata el starea si timpul): banda nu se arata peste el."""
		try:
			dlg = self.session.current_dialog
			return type(dlg).__name__ in ECRANE_FARA_BANDA
		except Exception:
			return False

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

def porneste(session, nivel="A", durata_min=None, de_la="televizor", versiune_text=None, nevoie="", detalii=""):
	if versiune_text is None:
		versiune_text = A.VERSIUNE_TEXT
	if durata_min is None:
		durata_min = A.DURATA_IMPLICITA_MIN
	limba = _limba()
	return A.porneste(nivel=nivel, durata_min=durata_min, limba=limba, de_la=de_la,
		versiune_text=versiune_text, ctx=ctxReceptor(session), nevoie=nevoie, detalii=detalii)


def reia(session):
	try:
		A.reia(ctx=ctxReceptor(session))
	except Exception as e:
		_jurnal("reluare: %r" % (e,))


def cerereWeb(session, nivel="A", durata_min=None, nevoie="", detalii=""):
	"""Pornirea ceruta din pagina web (browserul omului, conectat cu codul de pe televizor): pe televizor se deschide
	ecranul Asistentei cu informarea intreaga si durata aleasa; abia dupa Verde, alegere si „Da" porneste sesiunea
	(nimic nu porneste fara apasare pe televizor). nevoie/detalii ("Cu ce te ajutam?", optionale) apar deja alese pe
	ecranul de pornire. -> (reusit, mesaj) numai despre faptul ca s-a cerut confirmarea."""
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
		nevoie, detalii = A.curataNevoie(nevoie, detalii)
		Notifications.AddNotification(HdsAsistenta, din_web=durata_min, nevoie=nevoie, detalii=detalii)
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
