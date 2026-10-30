# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistentaSemn.py: semnul de pe ecran cat Asistenta de la distanta e activa si legatura cu receptorul (partea care
# are nevoie de enigma2). Logica e in Components/HdsAsistenta.py (fara enigma); aici sunt:
#   - banda mica de sus, mereu deasupra (fereastra nemodala, ca mesajul de retea), pe un singur rand: pana cand e
#     pornita si calea spre Oprire (Meniu > Setari > Asistenta de la distanta), fara codul sesiunii (intern); se
#     vede si peste imaginea pe tot ecranul si peste meniuri, deasupra randului cu titlul ferestrelor (nu il acopera);
#     cat ecranul asistentei e deschis (el arata starea si timpul), banda se ascunde;
#   - Controler: un observator care arata, improspateaza (o data pe secunda) si ascunde banda; tot el culege, pe firul
#     enigma2, ce cere operatorul pe ecran, fiindca brokerul ruleaza pe alt fir si nu are voie sa atinga interfata:
#     mesajele (op "mesaj"), nemodale, cu HdsAnuntRetea, fiecare cel putin MESAJ_S secunde, la rand (unul nu il
#     inlocuieste pe altul), si concluziile echipei (op "concluzii"), in fereastra modala HdsAsistentaConcluzii, care
#     sta pana la OK: o data cand sosesc si inca o data la sfarsitul sesiunii, cu multumirile;
#   - ctxReceptor(session): uneltele date brokerului care au nevoie de receptor: captura numai a meniurilor (OSD), JPEG
#     mic, refuzata pe ecranele private (Components/HdsAsistentaControl.py: modulele de acces, Accesul SSH, parolele,
#     Wi-Fi-ul, beta testerul), punerea unui mesaj si a concluziilor, si controlul (nivelul B): textul ecranului (op
#     "ecran"), tastele telecomenzii (op "taste", una pe tic de eTimer) si textul intr-un camp (op "text"), toate pe firul
#     enigma2 (Control.PeFir: reactor.callFromThread, iar ceasul controlerului goleste coada ca plasa); cat ruleaza un
#     op de control, banda de sus spune "HD Satelit lucrează acum pe receptorul tău";
#   - porneste(...) si reia(session): pornirea unei sesiuni cu ctx-ul potrivit (de pe receptor sau din web) si reluarea
#     dupa repornirea interfetei (chemata din mytest.py).
# Nu se importa la incarcarea mytest.py nimic greu; functiile se cheama la nevoie.

import subprocess

from enigma import eTimer

from Screens.Screen import Screen
from Components.Sources.StaticText import StaticText
from Components import HdsAsistenta as A
from Components import HdsAsistentaControl as Control

GRAB = "/usr/bin/grab"
CAPTURA_TERMEN_S = 8
# captura: JPEG mic (pe Octagon SF8008 un PNG al meniurilor trecea de 2 MB)
CAPTURA_LATIME = 960
CAPTURA_CALITATE = 70


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
ECRANE_FARA_BANDA = ("HdsAsistenta", "HdsAsistentaAlege", "HdsAsistentaTermeni", "HdsAsistentaConcluzii")
# cat sta pe ecran un mesaj al echipei (op "mesaj"), cel putin; urmatorul vine dupa
MESAJ_S = 30


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
		self.fereastraMesaj = None
		self.ceas = eTimer()
		self.ceas.callback.append(self._tic)
		self._mesaje = []
		self._mesaj_liber_la = 0.0
		self._concluzii = []
		self._stare_vazuta = None
		# sesiunea vazuta activa (id-ul ei): la sfarsitul ei, daca echipa a trimis concluzii, fereastra inca o data
		self._id_activ = None

	def instaleaza(self):
		A.adaugaObservator(self._schimbare)
		self._schimbare()

	def cereMesaj(self, text):
		"""Chemata de pe firul sesiunii (brokerul): pune un mesaj in coada; _tic il arata pe firul enigma2."""
		self._mesaje.append(text)

	def cereConcluzii(self, text):
		"""Chemata de pe firul sesiunii (op "concluzii"): pastreaza concluziile pe receptor (se recitesc din ecranul
		asistentei si din web) si le pune in coada; _tic deschide fereastra pe firul enigma2. -> numarul de semne."""
		ses = A.sesiune()
		intrare = A.salveazaConcluzii(text, ses.id if ses is not None else None)
		if not intrare:
			return 0
		self._concluzii.append(intrare)
		return len(intrare["text"])

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
			if self.banda is not None:
				try:
					self.banda.hide()
				except Exception:
					pass
			# sfarsitul sesiunii (fereastra concluziilor, mesajele ramase) il face _tic la urmatoarea secunda, nu aici:
			# oprirea poate veni de pe un ecran care se inchide imediat dupa (Rosu pe ecranul asistentei)
			if self._id_activ is not None or self._mesaje or self._concluzii:
				self.ceas.start(1000, False)
			else:
				self.ceas.stop()

	def _tic(self):
		import time
		# plasa: lucrul cerut de firul sesiunii pe firul enigma2, daca trezirea prin reactor n-a ajuns
		try:
			_peFir.goleste()
		except Exception as e:
			_jurnal("coada: %r" % (e,))
		ses = A.sesiune()
		activa = ses is not None and ses.activa()
		# mesajele: la rand, fiecare cel putin MESAJ_S secunde (si dupa oprire, cele ramase in coada)
		if self._mesaje and time.time() >= self._mesaj_liber_la:
			self._arataMesaj(self._mesaje.pop(0))
			self._mesaj_liber_la = time.time() + MESAJ_S
		while self._concluzii:
			self._arataConcluzii(self._concluzii.pop(0))
		if activa:
			self._id_activ = getattr(ses, "id", None) or self._id_activ
		elif self._id_activ is not None:
			# sesiunea s-a terminat (omul, termenul, serverul): concluziile ei inca o data, cu multumirile
			id_ = self._id_activ
			self._id_activ = None
			c = A.ultimeleConcluzii()
			if c and c.get("id") == id_:
				self._arataConcluzii(c, la_sfarsit=True)
		if not activa:
			if self.banda is not None:
				self.banda.hide()
			if not self._mesaje:
				self.ceas.stop()
			return
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
			if _lucreazaAcum():
				self.banda.pune(_(A.TEXT_LUCREAZA), _(TEXT_OPRESTI) % A.drumMeniu(scurt=True))
			else:
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
		# fereastra proprie (nu cea a anunturilor de retea, care s-ar putea pune peste ea), nemodala: nu ia tastele
		# nimanui si nu dispare la prima tasta, sta MESAJ_S secunde
		try:
			from Screens import HdsAnuntRetea
			if self.fereastraMesaj is None:
				self.fereastraMesaj = self.session.instantiateDialog(HdsAnuntRetea.HdsAnuntRetea)
			self.fereastraMesaj.anunta("%s %s" % (_("Mesaj de la HD Satelit:"), text), "info",
				durata_ms=MESAJ_S * 1000, ascunde_la_tasta=False)
		except Exception as e:
			_jurnal("mesaj: %r" % (e,))

	def _arataConcluzii(self, intrare, la_sfarsit=False):
		"""Fereastra concluziilor (modala, pana la OK), prin notificari: se deschide cand omul e la imaginea canalului,
		nu peste alt ecran modal. La sfarsitul sesiunii nu se deschide a doua oara daca e inca deschisa."""
		try:
			from Screens.HdsAsistenta import HdsAsistentaConcluzii
			if la_sfarsit and HdsAsistentaConcluzii.deschise:
				return
			from Tools import Notifications
			Notifications.AddNotification(HdsAsistentaConcluzii, intrare)
		except Exception as e:
			_jurnal("concluzii: %r" % (e,))


_controler = [None]


def instaleaza(session):
	"""Chemata o data din mytest.py: pregateste controlerul semnului si reia o sesiune ramasa (dupa o repornire a
	interfetei)."""
	if _controler[0] is None:
		_controler[0] = Controler(session)
		_controler[0].instaleaza()
	reia(session)


# ---------------------------------------------------------------- uneltele receptorului date brokerului

def _lucreazaAcum():
	try:
		return A.lucreazaAcum()
	except Exception:
		return False


def _trezeste(functie):
	"""Pune functia pe firul enigma2 (e2reactor: callFromThread trezeste bucla)."""
	from twisted.internet import reactor
	reactor.callFromThread(functie)


# lucrul pe firul enigma2 cerut de firul sesiunii (textul ecranului, tastele, textul, verificarea ecranului privat)
_peFir = Control.PeFir(trezeste=_trezeste)
# cat asteapta firul sesiunii un raspuns de pe firul enigma2
TERMEN_FIR_S = 15
# ceasurile sirurilor de taste in lucru
_vii = set()


def _session():
	c = _controler[0]
	return c.session if c is not None else None


def _stivaAcum():
	s = _session()
	return Control.stiva(s) if s is not None else []


def _privatAcum():
	"""(privat, clasa) pentru stiva de acum; pe firul enigma2."""
	return Control.privat(_stivaAcum(), Control._sshDeschis())


def _ecranText():
	"""Textul ecranului (op "ecran"), citit pe firul enigma2."""
	def lucru(gata):
		gata(Control.textEcran(_stivaAcum(), Control.modAscii(), Control._sshDeschis()))
	return _peFir.cere(lucru, TERMEN_FIR_S)


def _taste(lista):
	"""Tastele (op "taste"): una pe tic de eTimer, pe firul enigma2; apoi, dupa LINISTE_MS, textul ecranului.
	-> (cod, text) sau None dupa termen."""
	def lucru(gata):
		sir = Control.SirTaste(lista, _stivaAcum)
		ceas = eTimer()
		stare = {"liniste": False}

		def tic():
			if stare.get("terminat"):
				ceas.stop()
				return
			if stare["liniste"]:
				ceas.stop()
				stare["terminat"] = True
				_vii.discard(ceas)
				ecran = Control.textEcran(_stivaAcum(), Control.modAscii(), Control._sshDeschis())
				cap = "taste trimise: %s" % (" ".join(sir.trimise) or "(niciuna)")
				if sir.oprit:
					cap += "\n" + sir.oprit
				gata((1 if sir.oprit else 0, cap + "\n\n" + ecran))
				return
			try:
				mai_sunt = sir.pas()
			except Exception as e:
				_jurnal("tasta: %r" % (e,))
				sir.oprit = "eroare: %s" % type(e).__name__
				mai_sunt = False
			if not mai_sunt:
				stare["liniste"] = True
				ceas.start(Control.LINISTE_MS, False)
		ceas.callback.append(tic)
		# tinut viu cat merge (altfel ciclul ceas <-> tic poate fi strans de gunoier)
		_vii.add(ceas)
		tic()
		if not stare["liniste"]:
			ceas.start(Control.PAUZA_MS, False)
	return _peFir.cere(lucru, Control.asteptareTaste(len(lista)))


def _text(text):
	"""Textul in campul deschis (op "text"), pe firul enigma2. -> (cod, mesaj) sau None dupa termen."""
	def lucru(gata):
		from Components import HdsMouseEcran
		s = _session()
		ecrane = _stivaAcum()
		mouse = HdsMouseEcran.MouseEcran(lambda: s.current_dialog if s is not None else None,
			apasa=lambda cod: Control.apasaTasta(cod))
		cod, mesaj = Control.scrieText(ecrane, text, Control.modAscii(), mouse.text, Control._sshDeschis())
		if cod == 0:
			mesaj += "\n\n" + Control.textEcran(_stivaAcum(), Control.modAscii(), Control._sshDeschis())
		gata((cod, mesaj))
	return _peFir.cere(lucru, TERMEN_FIR_S)


def _captura():
	"""O captura numai a meniurilor (OSD), JPEG mic; None cand nu se poate, textul refuzului pe un ecran privat."""
	privat = _peFir.cere(lambda gata: gata(_privatAcum()), TERMEN_FIR_S) if _session() is not None else None
	if privat is None:
		try:
			from Components import HdsAccesSsh
			if HdsAccesSsh.ecranDeschis():
				return "(ecran privat: HdsAccesSsh; captura refuzata)"
		except Exception:
			pass
	elif privat[0]:
		return "(ecran privat: %s; captura refuzata)" % privat[1]
	try:
		p = subprocess.Popen([GRAB, "-q", "-o", "-s", "-j", str(CAPTURA_CALITATE), "-r", str(CAPTURA_LATIME)],
			stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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
	ctx["ecran"] = _ecranText
	ctx["taste"] = _taste
	ctx["text"] = _text
	if _controler[0] is not None:
		ctx["mesaj"] = _controler[0].cereMesaj
		ctx["concluzii"] = _controler[0].cereConcluzii
	else:
		ctx["mesaj"] = lambda t: None
		ctx["concluzii"] = _concluziiFaraControler
	return ctx


def _concluziiFaraControler(text):
	# fara controler (nu se intampla dupa pornirea interfetei): concluziile raman macar pentru recitire
	ses = A.sesiune()
	intrare = A.salveazaConcluzii(text, ses.id if ses is not None else None)
	return len(intrare["text"]) if intrare else 0


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


TEXT_WEB_PE_RECEPTOR = N_("Pe receptor s-a deschis Asistența de la distanță: apasă Start acolo.")
TEXT_WEB_NU_POT = N_("Nu pot deschide Asistența de la distanță pe receptor acum.")


def pornesteWeb(session, nivel="A"):
	"""Pornirea din pagina web a unui browser de incredere (conectat cu codul de pe receptor): un clic, ca Start de pe
	receptor (durata implicita, fara intrebari); nivel "B" cu randul "Control complet" bifat. -> (reusit, mesaj)."""
	ses = A.sesiune()
	if ses is not None and ses.activa():
		return False, _("Asistența merge deja.")
	return porneste(session, nivel=nivel if nivel in A.NIVELE else "A", durata_min=A.DURATA_IMPLICITA_MIN,
		de_la="web")


def cerereWeb(session, nivel="A", durata_min=None, nevoie="", detalii=""):
	"""Pornirea ceruta dintr-un browser fara cod (oricine din reteaua locala): pe receptor se deschide pagina de pornire
	(randul bifat si Start); porneste numai Start apasat acolo, ca un aparat oarecare din casa sa nu poata da acces la
	receptor fara stirea omului. durata_min, nevoie si detalii raman in semnatura pentru apelurile vechi; pornirea e cea
	de pe pagina. -> (reusit, mesaj) numai despre faptul ca s-a deschis pagina."""
	if session is None:
		return False, _(TEXT_WEB_NU_POT)
	ses = A.sesiune()
	if ses is not None and ses.activa():
		return False, _("Asistența merge deja.")
	try:
		from Tools import Notifications
		from Screens.HdsAsistenta import HdsAsistenta
		Notifications.AddNotification(HdsAsistenta, din_web=A.DURATA_IMPLICITA_MIN)
		return True, _(TEXT_WEB_PE_RECEPTOR)
	except Exception as e:
		_jurnal("cerere web: %r" % (e,))
		return False, _(TEXT_WEB_NU_POT)


def _limba():
	try:
		from Components.Language import language
		return (language.getLanguage() or "ro")[:2]
	except Exception:
		return "ro"
