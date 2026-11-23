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
#     mesajele (op "mesaj"), nemodale, cu HdsAnuntRetea, peste orice ecran, la rand (unul nu il inlocuieste pe altul
#     mai devreme de MESAJ_S secunde); fiecare sta pana la prima tasta apasata dupa MESAJ_TASTA_MS (tasta merge mai
#     departe, nu e luata), cel mult MESAJ_MAX_S, si ramane intreg in jurnalul asistentei (televizor si web); si
#     concluziile echipei (op "concluzii"), in fereastra modala HdsAsistentaConcluzii, care sta pana la OK, deschisa
#     indata peste orice ecran (nu in coada notificarilor, care o arata abia la imaginea canalului, uneori peste o sesiune
#     noua), o data cand sosesc si inca o data la sfarsitul sesiunii, cu multumirile; si intrebarile echipei
#     (op "intrebare", 0.7.7): o fereastra Da/Nu (MessageBox) cu variantele, peste orice ecran, inchisa inainte ca
#     raspunsul sa plece la echipa (_intrebare), cu fereastra mesajului ascunsa cat sta; din 0.7.8 si raspunsul scris
#     ("*" in variante): randul "Scrie răspunsul" deschide tastatura de pe ecran (VirtualKeyBoard), care devine fereastra
#     intrebarii; EXIT sau un text gol intorc la intrebare;
#   - ctxReceptor(session): settings de acum pentru copia facuta cand intra echipa („Pune înapoi cum era”, setari_acum,
#     pe firul enigma2) si uneltele date brokerului care au nevoie de receptor: captura video cu OSD, JPEG mic, aceeasi
#     cu ce e pe televizor (fara ecrane ascunse si fara steluțe).
#     Punerea unui mesaj si a concluziilor, si controlul (nivelul B): textul ecranului (op
#     "ecran"), tastele telecomenzii (op "taste", una pe tic de eTimer) si textul intr-un camp (op "text"), toate pe firul
#     enigma2 (Control.PeFir: reactor.callFromThread, iar ceasul controlerului goleste coada ca plasa); cat ruleaza un
#     op de control, banda de sus spune "HD Satelit lucrează acum pe receptorul tău";
#   - porneste(...) si reia(session): pornirea unei sesiuni cu ctx-ul potrivit (de pe receptor sau din web) si reluarea
#     dupa repornirea interfetei (chemata din mytest.py);
#   - puneInapoi(session): Albastru "Pune înapoi cum era" de pe ecranele asistentei (intrebarea, cererea, repornirea).
#   - PesteNavigator (0.7.8, ASV4): intrebarile, mesajele, concluziile si anunturile se vad si primesc tastele si cat
#     navigatorul (HbbTV sau web) tine ecranul: navigatorul se ascunde inainte si revine o data dupa ultima fereastra.
# Nu se importa la incarcarea mytest.py nimic greu; functiile se cheama la nevoie.

import subprocess
import sys

from enigma import eTimer

from Screens.Screen import Screen
from Components.Sources.StaticText import StaticText
from Components import HdsAsistenta as A
from Components import HdsAsistentaControl as Control

GRAB = "/usr/bin/grab"
# grab ruleaza pe firul sesiunii asistentei, niciodata pe firul enigma2: pe receptorul nostru de probe (HiSilicon, ca Trio 4K
# si SF8008) grab dura 1,2 s din ssh, dar pornit pe firul enigma2, cu bucla oprita cat asteapta, trecea de termen (8 s), deci
# nicio captura prin asistenta n-a mers din 09.11 pana in 0.7.5 (2) (TRI, TODO 09.11 07:10, FAA7MED). Interfata web il
# rula deja in fir separat. Pe firul enigma2 raman numai stiva ecranelor (inainte si dupa) si curatarea copiei.
CAPTURA_TERMEN_S = 8
# Cu navigatorul deschis (HbbTV sau web, WebKit desenat pe procesor, de pilda pe Solo4K) grab-ul poate dura mai mult:
# pana la CAPTURA_TERMEN_NAVIGATOR_S, pe firul sesiunii asistentei, nu pe firul enigma2 (interfata si tastele
# navigatorului nu stau dupa el). Hotararea coordonatorului (12.11.2026), dupa „captura nu s-a putut face acum” la olo.
CAPTURA_TERMEN_NAVIGATOR_S = 15
# Dupa termen grab e oprit cu kill(); firul sesiunii mai asteapta iesirea lui cel mult CAPTURA_OPRIRE_S. Un grab blocat
# in driver (starea D, nu moare la SIGKILL) ramane in _grabRamase si nicio captura noua nu porneste cat traieste, ca
# ASTEPTARE_OPRIRE_S si _grabRamasInViata din HdsWebControl/plugin.py (0.7.5 FIR, TODO 15.11 06:15 (TRI, grab
# marginit): inainte communicate() fara termen dupa kill() tinea firul sesiunii pe loc).
CAPTURA_OPRIRE_S = 2
_grabRamase = []
# captura: JPEG mic pentru a ramane sub plafonul brokerului
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
# mesajele echipei (op "mesaj"): urmatorul il inlocuieste pe cel de pe ecran abia dupa MESAJ_S secunde; fiecare sta pana
# la prima tasta apasata dupa MESAJ_TASTA_MS (o tasta apasata chiar atunci nu-l sterge necitit; tasta merge mai departe la
# ecranul de dedesubt), cel mult MESAJ_MAX_S; textul ramane in jurnalul asistentei
MESAJ_S = 30
MESAJ_TASTA_MS = 5000
MESAJ_MAX_S = 180
# raspunsurile ferestrei intrebarii (op "intrebare") care nu sunt ale omului: timpul ferestrei s-a terminat, sau am inchis-o
# noi (raspuns din web, timpul intrebarii, oprirea asistentei)
INTREBARE_TERMEN = "termen"
INTREBARE_INCHISA = "inchisa"


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la folosire."""
	return text


# de unde se opreste, pe banda de sus (oricand, si la "permanent")
TEXT_OPRESTI = N_("Oprești oricând din %s")
# anuntul de pe ecran cand echipa aproba cererea (ecranul asistentei ii spunea omului "Te anunțăm când intrăm")
TEXT_CONECTAT = N_("Echipa HD Satelit s-a conectat. Poți folosi receptorul ca de obicei.")


# ---------------------------------------------------------------- peste navigator (HbbTV sau web)
#
# 0.7.8 (ASV4): navigatorul (Plugins/Extensions/HdsNavigator/lansator.py) e un proces separat
# care, cat e pe ecran, tine stratul grafic (fbClass.lock: enigma2 nu mai deseneaza) si telecomanda (bindAction cu
# prioritatea -0x7FFFFFFF; in modul HbbTV o leaga Components/HdsHbbtvPornire.Controlor). O fereastra a asistentei
# deschisa atunci (intrebarea, mesajul, concluziile) era nevazuta, iar tastele mergeau la aplicatie; EXIT inchidea si
# aplicatia HbbTV (Controlor._tasta -> inchide). Ca la pluginul HbbTV din OE-Alliance (fereastra enigma2 numai cu fb si
# rc deblocate, apoi blocate la loc), inainte de fereastra navigatorul se ascunde prin contractul lui (ascunde/reia,
# aceleasi ca la ferestrele cerute de pagina) si tastele Controlorului se dezleaga; dupa ultima fereastra totul se pune
# la loc o singura data. Pagina nu afla nimic (fara evenimentul "vizibil"), aplicatia nu se inchide, canalul nu se
# schimba. Fara navigator nimic nu se schimba fata de 0.7.7. Numai citiri de atribute in memorie (sys.modules), fara
# importuri, disc sau asteptari pe firul enigma2.

def _navigatorSiControlor():
	"""(modulul lansator sau None, navigatorul deschis sau None, controlorul HbbTV sau None), numai din ce e deja incarcat:
	un modul neincarcat inseamna ca nu s-a deschis nimic de la pornire."""
	L = sys.modules.get("Plugins.Extensions.HdsNavigator.lansator")
	nav = None
	if L is not None:
		try:
			nav = L.activ()
		except Exception:
			nav = None
	c = None
	P = sys.modules.get("Components.HdsHbbtvPornire")
	if P is not None:
		lista = getattr(P, "_CONTROLOR", None) or []
		c = lista[0] if lista else None
	return L, nav, c


class PesteNavigator(object):
	"""Contractul ferestrelor asistentei peste navigator: gata() inainte de fiecare fereastra, reda() dupa ultima. Jetonul
	tine minte ce am facut noi (navigatorul ascuns, tastele Controlorului dezlegate) si pe cine; reda() pune la loc numai
	atat, o singura data, si numai daca e acelasi navigator si mai are nevoie (pagina ascunsa intre timp de aplicatie
	ramane ascunsa, o pagina inchisa nu mai are ce relua)."""

	def __init__(self, gaseste=None):
		self._gaseste = gaseste or _navigatorSiControlor
		self._jeton = None

	@staticmethod
	def _const(L, nume):
		return getattr(L, nume, nume.lower())

	def _lucreaza(self, L, nav, c):
		"""Navigatorul tine ecranul (pe ecran sau ascunderea inca in curs) sau Controlorul HbbTV tine tastele."""
		if nav is not None and (nav.stare == self._const(L, "ARATAT") or getattr(nav, "_fb_blocat", False)):
			return True
		return c is not None and c.nav is not None and bool(getattr(c, "_taste", False))

	def tine(self):
		"""O fereastra a asistentei deschisa acum ar fi sub navigator sau i-ar lua aplicatia tastele (sau am suspendat noi
		navigatorul pentru o fereastra)."""
		try:
			L, nav, c = self._gaseste()
			if self._jeton is not None and self._jeton["nav"] is not nav:
				self.reda()      # navigatorul suspendat s-a inchis: nimic de pus la loc pe altul
			return self._jeton is not None or self._lucreaza(L, nav, c)
		except Exception as e:
			_jurnal("navigatorul: %r" % (e,))
			return False

	def suspendat(self):
		return self._jeton is not None

	def gata(self, trezeste=None):
		"""Inainte de o fereastra a asistentei: True cand se poate deschide acum (ecranul si tastele sunt ale enigma2);
		False cand se asteapta (ascunderea navigatorului e in curs, trezeste() vine cand e gata, sau o aplicatie HbbTV
		se incarca: o fereastra peste bara ar inchide-o) si se incearca la tic-ul urmator."""
		try:
			L, nav, c = self._gaseste()
			j = self._jeton
			if j is not None and j["nav"] is not nav:
				# navigatorul de la suspendare s-a inchis (sau altul i-a luat locul): nu atingem altul
				self._jeton = j = None
			hbbtv = c is not None and c.nav is not None and c.nav is nav
			if nav is not None and nav.stare in (self._const(L, "PORNIRE"), self._const(L, "INCARCARE")) and \
					not (hbbtv and c.fundal):
				# se incarca: la prima pagina ar lua ecranul peste fereastra (o aplicatie pornita automat ramane ascunsa)
				return False
			if j is None and not self._lucreaza(L, nav, c):
				return True
			if hbbtv and not c.fundal and not c.aratat and (not c.pornita or getattr(c, "_asteapta_arata", False)):
				# prima pagina sau show() inca asteptate: Controlor._cereArata ar inchide aplicatia ("alta fereastra peste
				# bara"); TERMEN_ARATA_MS (10 s) o lasa ascunsa, apoi fereastra se deschide
				return False
			if j is None:
				j = self._jeton = {"nav": nav, "controlor": c if hbbtv or (c is not None and c.nav is not None) else None,
					"ascuns": False, "taste": False}
				_jurnal("ferestrele asistentei peste navigator: suspendat (mod %s, stare %s)" % (
					getattr(nav, "mod", "-"), getattr(nav, "stare", "-")))
			if c is not None and c.nav is not None and getattr(c, "_taste", False):
				c._legaTaste(False)
				j["taste"] = True
				j["controlor"] = c
			if nav is not None and nav.stare == self._const(L, "ARATAT"):
				j["ascuns"] = True
				nav.ascunde(trezeste)
				return False
			return not getattr(nav, "_fb_blocat", False) if nav is not None else True
		except Exception as e:
			_jurnal("suspendarea navigatorului: %r" % (e,))
			return True

	def reda(self):
		"""Dupa ultima fereastra: tastele Controlorului legate la loc si pagina reluata, numai ce am luat noi, o data.
		-> True cand era ceva suspendat."""
		j, self._jeton = self._jeton, None
		if j is None:
			return False
		try:
			L, nav, c = self._gaseste()
			c0 = j["controlor"]
			if j["taste"] and c0 is not None and c0 is c and c.nav is not None and not c.fundal and \
					not getattr(c, "_taste", False) and (j["nav"] is None or c.nav is j["nav"]):
				c._legaTaste(True)
			if j["ascuns"] and nav is not None and nav is j["nav"] and nav.stare == self._const(L, "ASCUNS"):
				if c is not None and c.nav is nav:
					# HbbTV: numai daca aplicatia mai vrea sa fie vazuta (un hide() al ei intre timp ramane)
					if c.aratat and not c.fundal:
						nav.reia()
				else:
					nav.reia()
			_jurnal("ferestrele asistentei peste navigator: redat")
		except Exception as e:
			_jurnal("reluarea navigatorului: %r" % (e,))
		return True


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
		self._mesaj_aratat = None
		self._concluzii = []
		self._stare_vazuta = None
		# sesiunea vazuta activa (id-ul ei): la sfarsitul ei, daca echipa a trimis concluzii, fereastra inca o data
		self._id_activ = None
		# intrebarile echipei (op "intrebare", A.Intrebare) de deschis pe televizor si (nr, fereastra) celei deschise
		self._intrebari = []
		self.fereastraIntrebare = None
		# intrebarile (nr) la care omul a ales "Scrie răspunsul": la deschidere din coada vine tastatura, nu fereastra
		self._deScris = set()
		# peste navigator (0.7.8, ASV4): contractul, ferestrele de aratat cat navigatorul tine ecranul ((fel, date):
		# "concluzii" (intrare, la_sfarsit) si "anunt" text; mesajele echipei raman in _mesaje) si fereastra deschisa
		self.navigator = PesteNavigator()
		self._coadaNav = []
		self._dlgNav = None
		# ferestrele concluziilor (si cea de sfarsit) care asteapta sa se poata deschide acum ((intrare, la_sfarsit)): la
		# fiecare tic, peste orice ecran; cele ale unei sesiuni vechi nu se mai deschid (A.fereastraVeche)
		self._amanate = []

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
			if self._id_activ is not None or self._mesaje or self._concluzii or self._coadaNav or self._amanate or \
					self.navigator.suspendat():
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
		if self._intrebari:
			self._deschideIntrebarea(activa)
		# mesajele: la rand, fiecare cel putin MESAJ_S secunde (si dupa oprire, cele ramase in coada); nu cat e deschisa o
		# intrebare a echipei: fereastra mesajului, nemodala si deasupra, ar acoperi-o (vazut pe receptor peste Da/Nu).
		# Cat navigatorul tine ecranul, mesajele, concluziile si anunturile vin peste el, modale (_pesteNavigator).
		if self._pesteNavigator():
			pass
		elif self._mesaje and time.time() >= self._mesaj_liber_la and self.fereastraIntrebare is None and not self._deScris:
			self._mesaj_aratat = self._mesaje.pop(0)
			self._arataMesaj(self._mesaj_aratat)
			self._mesaj_liber_la = time.time() + MESAJ_S
		while self._concluzii:
			self._arataConcluzii(self._concluzii.pop(0))
		# ferestrele concluziilor care n-au putut fi deschise la tic-ul de dinainte (o inchidere in curs, standby)
		self._deschideAmanate()
		if activa:
			self._id_activ = getattr(ses, "id", None) or self._id_activ
		elif self._id_activ is not None:
			# sesiunea s-a terminat (omul, termenul, serverul): concluziile ei inca o data, cu multumirile
			id_ = self._id_activ
			self._id_activ = None
			c = A.ultimeleConcluzii()
			de_om = A.opritDeOm(id_)
			if c and c.get("id") == id_:
				self._arataConcluzii(dict(c, de_om=True) if de_om else c, la_sfarsit=True)
			elif de_om:
				# CR4 (0.7.8, Eduard 18.11 17:25): oprita de om fara concluzii: tot fereastra, cu confirmarea si multumirea
				self._arataConcluzii({"text": "", "ora": 0, "id": id_, "de_om": True}, la_sfarsit=True)
			# si un anunt scurt, nemodal, cand s-a oprit fara om (echipa a inchis-o, a trecut timpul): omul afla ca
			# s-a terminat si cand fereastra concluziilor e deja deschisa sau a fost inchisa (orion_bilo, 14.11.2026)
			self._anuntaSfarsit(id_)
		self._redaDacaLiber()
		if not activa:
			if self.banda is not None:
				self.banda.hide()
			if not self._mesaje and not self._coadaNav and not self._amanate and not self.navigator.suspendat():
				self.ceas.stop()
			return
		# cererea a fost aprobata (asteapta -> conectat): omul afla, oriunde ar fi pe receptor (pe ecranul asistentei
		# scrie deja "Conectat."); dupa o reluare a interfetei starea de dinainte nu se stie, deci nu se anunta
		if self._stare_vazuta == A.ASTEAPTA and ses.stare == A.CONECTAT and not self._ecranAsistenta():
			self._anunta(_(TEXT_CONECTAT), "anuntul conectarii")
		self._stare_vazuta = ses.stare
		if self.banda is not None:
			if self._ecranAsistenta():
				self.banda.hide()
				return
			# mereu de unde se opreste; in stanga ce face echipa ("lucrează acum" dupa orice cerere, "a terminat..." dupa
			# concluzii), altfel ca e pornita si pana cand ("până la ZZ.LL, HH:MM" / "fără sfârșit")
			activitate = _activitate(ses)
			self.banda.pune(activitate or A.textPana(ses, banda=True), _(TEXT_OPRESTI) % A.drumMeniu(scurt=True))
			self.banda.show()

	def _anuntaSfarsit(self, id_):
		try:
			text = A.textSfarsit(id_)
		except Exception as e:
			_jurnal("anuntul de sfarsit: %r" % (e,))
			return
		if text:
			self._anunta(text, "anuntul de sfarsit")

	def _anunta(self, text, ce):
		"""Anuntul scurt, nemodal (HdsAnuntRetea), ca pana acum; cat navigatorul tine ecranul vine peste el, modal."""
		if self.navigator.tine():
			self._coadaNav.append(("anunt", text))
			return
		try:
			from Screens import HdsAnuntRetea
			HdsAnuntRetea.arata(self.session, text, "info")
		except Exception as e:
			_jurnal("%s: %r" % (ce, e))

	def _ecranAsistenta(self):
		"""Ecranul asistentei e deasupra (arata el starea si timpul): banda nu se arata peste el."""
		try:
			dlg = self.session.current_dialog
			return type(dlg).__name__ in ECRANE_FARA_BANDA
		except Exception:
			return False

	def _arataMesaj(self, text):
		# fereastra proprie (nu cea a anunturilor de retea, care s-ar putea pune peste ea), nemodala, deasupra oricarui
		# ecran: nu ia tastele nimanui; sta pana la prima tasta apasata dupa MESAJ_TASTA_MS (tasta merge mai departe),
		# cel mult MESAJ_MAX_S
		try:
			from Screens import HdsAnuntRetea
			if self.fereastraMesaj is None:
				self.fereastraMesaj = self.session.instantiateDialog(HdsAnuntRetea.HdsAnuntRetea)
			self.fereastraMesaj.anunta("%s %s" % (_("Mesaj de la HD Satelit:"), text), "info",
				durata_ms=MESAJ_MAX_S * 1000, ascunde_la_tasta=MESAJ_TASTA_MS)
		except Exception as e:
			_jurnal("mesaj: %r" % (e,))

	def _arataConcluzii(self, intrare, la_sfarsit=False, verifica_navigatorul=True):
		"""Fereastra concluziilor (modala, pana la OK), deschisa indata peste orice ecran (meniu, plugin, film, imaginea
		canalului, ecranul asistentei); cand Session.open nu poate deschide acum (o inchidere in curs, standby), la
		tic-ul urmator (_deschideAmanate). La sfarsitul sesiunii nu se deschide a doua oara daca e inca deschisa.
		0.7.6 (ASF, asistenta 222923): pe ecranul asistentei indata. 0.7.8 (ASV4): cat navigatorul tine ecranul, fereastra
		vine peste el (_pesteNavigator), nu nevazuta sub el. Inainte, peste alt ecran decat al asistentei,
		fereastra mergea in coada notificarilor si se deschidea abia la imaginea canalului: omul care oprise asistenta si o
		pornise din nou din meniu a vazut „Asistența s-a oprit la cererea ta” al sesiunii vechi peste cea noua, 8 minute
		mai tarziu. Acum se deschide indata, iar una a altei sesiuni decat cea care merge nu se mai deschide."""
		if verifica_navigatorul and self.navigator.tine():
			self._coadaNav.append(("concluzii", (intrare, la_sfarsit)))
			return
		self._amanate.append((intrare, la_sfarsit))
		self._deschideAmanate()

	def _deschideAmanate(self):
		"""Prima fereastra a concluziilor care asteapta, daca se poate deschide acum; cele ale unei sesiuni vechi (alta
		sesiune merge acum) si cea de sfarsit cand fereastra concluziilor e deja deschisa se lasa. Ceasul controlerului
		ramane pornit cat asteapta una."""
		while self._amanate:
			intrare, la_sfarsit = self._amanate[0]
			try:
				from Screens.HdsAsistenta import HdsAsistentaConcluzii
				if _fereastraVeche(intrare):
					self._amanate.pop(0)
					_jurnal("concluziile sesiunii %s nu se mai arata: merge alta sesiune" % (intrare.get("id"),))
					continue
				if la_sfarsit and HdsAsistentaConcluzii.deschise:
					self._amanate.pop(0)
					continue
				if not self._poateDeschideFereastra():
					self.ceas.start(1000, False)
					return
			except Exception as e:
				self._amanate.pop(0)
				_jurnal("concluzii: %r" % (e,))
				return
			self._amanate.pop(0)
			try:
				continut = dict(intrare, sfarsit=True) if la_sfarsit else intrare
				self.session.open(HdsAsistentaConcluzii, continut)
			except Exception as e:
				_jurnal("concluzii: %r" % (e,))
			# una pe tic: dupa o deschidere Session.open asteapta pana ruleaza fereastra noua
			return

	def _poateDeschideFereastra(self):
		"""O fereastra a asistentei se poate deschide acum peste ecranul de sus: Session.open poate, receptorul nu e in
		standby si intrebarea echipei (sau tastatura ei) nu e deschisa."""
		if self.fereastraIntrebare is not None or self._deScris or not self._poateDeschide():
			return False
		try:
			from Screens import Standby
			return not Standby.inStandby
		except Exception:
			return True

	def _poateDeschidePesteAsistenta(self):
		"""Ecranul asistentei e sus, in executie, si nicio inchidere nu asteapta (altfel Session.open ar cadea)."""
		return self._ecranAsistenta() and self._poateDeschide()

	def _poateDeschide(self):
		"""Ecranul de sus e in executie si nicio inchidere nu asteapta: Session.open poate deschide o fereastra acum."""
		s = self.session
		if not getattr(s, "in_exec", False):
			return False
		try:
			return not s.delay_timer.isActive()
		except Exception:
			return False

	# ---- peste navigator (0.7.8, ASV4)

	def _ocupatDeNoi(self):
		"""O fereastra a asistentei e deschisa sau urmeaza indata (intrebarea, tastatura, mesajul sau concluziile)."""
		return self.fereastraIntrebare is not None or bool(self._deScris) or self._dlgNav is not None or \
			bool(self._intrebari)

	def _pesteNavigator(self):
		"""Ferestrele din _coadaNav si mesajele echipei cat navigatorul tine ecranul: una cate una, modale (OK sau EXIT le
		inchide, mesajul si singur dupa MESAJ_S), dupa ce navigatorul s-a ascuns. -> True cand s-au ocupat de ele aici
		(aratate sau in asteptare); False: mesajele merg pe calea obisnuita, nemodala."""
		mesaj_nav = bool(self._mesaje) and self.navigator.tine()
		if not self._coadaNav and not mesaj_nav:
			return False
		if not self.navigator.tine():
			# navigatorul s-a inchis intre timp: ferestrele asteptate se arata ca fara navigator
			coada, self._coadaNav = self._coadaNav, []
			for fel, date in coada:
				if fel == "concluzii":
					self._arataConcluzii(date[0], date[1], verifica_navigatorul=False)
				else:
					self._anunta(date, "anuntul")
			return False
		if self._ocupatDeNoi() or not self._poateDeschide():
			return True
		if not self.navigator.gata(self._trezesteTic):
			return True
		try:
			from Screens.MessageBox import MessageBox
			if self._coadaNav:
				fel, date = self._coadaNav.pop(0)
				if fel == "concluzii":
					from Screens.HdsAsistenta import HdsAsistentaConcluzii
					intrare, la_sfarsit = date
					if (la_sfarsit and HdsAsistentaConcluzii.deschise) or _fereastraVeche(intrare):
						return True
					continut = dict(intrare, sfarsit=True) if la_sfarsit else intrare
					self._dlgNav = self.session.openWithCallback(self._dupaFereastraNav, HdsAsistentaConcluzii, continut) or True
				else:
					self._dlgNav = self.session.openWithCallback(self._dupaFereastraNav, MessageBox, date,
						MessageBox.TYPE_INFO, timeout=MESAJ_S) or True
				return True
			text = self._mesaje.pop(0)
			self._mesaj_aratat = None
			self._dlgNav = self.session.openWithCallback(self._dupaFereastraNav, MessageBox, "%s %s" % (
				_("Mesaj de la HD Satelit:"), text), MessageBox.TYPE_INFO, timeout=MESAJ_S) or True
		except Exception as e:
			_jurnal("fereastra peste navigator: %r" % (e,))
			self._dlgNav = None
		return True

	def _dupaFereastraNav(self, *rez):
		"""Mesajul, anuntul sau concluziile de peste navigator s-au inchis (OK, EXIT, timpul): urmatoarea, sau pagina
		inapoi."""
		self._dlgNav = None
		self._redaDacaLiber()
		if self._coadaNav or self._mesaje:
			self._trezesteTic()

	def _redaDacaLiber(self):
		"""Navigatorul suspendat de noi primeste ecranul si tastele inapoi cand nicio fereastra a asistentei nu mai e
		deschisa si niciuna nu asteapta sa vina peste el (doua intrebari la rand: o singura reluare)."""
		if not self.navigator.suspendat() or self._ocupatDeNoi() or self._coadaNav or self._mesaje or self._concluzii:
			return
		if self._id_activ is not None:
			ses = A.sesiune()
			if ses is None or not ses.activa():
				# _tic adauga intai ferestrele de sfarsit; pagina nu revine intre ele si intrebare.
				return
		self.navigator.reda()

	# ---- intrebarea echipei (op "intrebare", 0.7.7)

	def cereIntrebare(self, q):
		"""Chemata de pe firul sesiunii (_intrebare): pune intrebarea in coada; _tic o deschide pe firul enigma2."""
		self._intrebari.append(q)

	def _deschideIntrebarea(self, activa):
		"""Prima intrebare din coada, pe televizor: o fereastra Da/Nu (MessageBox) cu variantele intrebarii, prima aleasa
		(fara variante: Nu), cu timpul ramas al intrebarii, peste orice ecran, cand Session.open poate deschide acum
		(altfel la tic-ul urmator). In standby nu se arata: echipa afla pe loc. Fereastra mesajului se ascunde cat sta."""
		q = self._intrebari[0]
		if q.gata.is_set() or q.ramasS() <= 1 or not activa:
			self._intrebari.pop(0)
			self._deScris.discard(q.id)
			return
		try:
			from Screens import Standby
			if Standby.inStandby:
				self._intrebari.pop(0)
				self._deScris.discard(q.id)
				A.inchideIntrebarea(q.id, "standby")
				return
		except Exception:
			pass
		if not self._poateDeschide():
			return
		if self.fereastraIntrebare is not None:
			# o intrebare veche ramasa pe ecran (inlocuita de aceasta) se inchide intai, ca omul sa vada numai intrebarea de
			# acum; cea noua se deschide la tic-ul urmator (dupa o inchidere Session.open trebuie sa astepte)
			self._inchideFereastraIntrebarii()
			return
		if not self.navigator.gata(self._trezesteTic):
			# 0.7.8 (ASV4): navigatorul se ascunde intai (sau aplicatia HbbTV inca se incarca); la tic-ul urmator
			return
		self._intrebari.pop(0)
		if q.id in self._deScris:
			self._deschideTastatura(q)
			return
		try:
			from Screens.MessageBox import MessageBox
			if self.fereastraMesaj is not None:
				# mesajul inca pe ecran (omul n-a apasat nicio tasta de cand a venit) vine iar dupa intrebare (echipa trimite
				# des mesaj, apoi intrebare); unul inchis de om ramane numai in jurnal
				pe_ecran = getattr(self.fereastraMesaj, "shown", None)
				if pe_ecran is None:
					# o fereastra fara starea ei (alta decat HdsAnuntRetea): ca inainte, in primele MESAJ_S secunde
					import time
					pe_ecran = time.time() < self._mesaj_liber_la
				self.fereastraMesaj.ascunde()
				if self._mesaj_aratat is not None and pe_ecran:
					self._mesaje.insert(0, self._mesaj_aratat)
				self._mesaj_aratat = None
				self._mesaj_liber_la = 0.0
			lista = [(eticheta, str(i)) for i, eticheta in enumerate(q.etichete)]
			if getattr(q, "scris", False):
				# raspunsul scris (0.7.8): ultimul rand; la "*" singur e singurul, deci deja ales
				# AST8: intrebarea de inceput are eticheta ei ("Altceva, scriu eu")
				lista.append((getattr(q, "eticheta_scris", None) or _(A.TEXT_INTREBARE_SCRIE), A.INTREBARE_SCRIS))
			dlg = self.session.openWithCallback(lambda rez=None, nr=q.id: self._dupaIntrebare(nr, rez), MessageBox, q.text,
				MessageBox.TYPE_YESNO, timeout=max(1, q.ramasS()), timeout_default=INTREBARE_TERMEN, list=lista,
				default=0, title=_(A.TEXT_INTREBARE_TITLU))
			self.fereastraIntrebare = (q.id, dlg)
			q.aratata = True
		except Exception as e:
			_jurnal("intrebarea: %r" % (e,))
			A.inchideIntrebarea(q.id, "nearatata: %s" % type(e).__name__)

	def _dupaIntrebare(self, nr, rez):
		"""Raspunsul ferestrei: OK pe o varianta ("0", "1" ...) e raspunsul omului; EXIT (False) inchide fara raspuns;
		timpul ferestrei (INTREBARE_TERMEN) si inchiderea de catre noi (INTREBARE_INCHISA) nu mai schimba nimic."""
		if self.fereastraIntrebare is not None and self.fereastraIntrebare[0] == nr:
			self.fereastraIntrebare = None
		if isinstance(rez, str) and rez.isdigit():
			A.raspundeIntrebare(nr, int(rez), "televizor")
		elif rez == getattr(A, "INTREBARE_SCRIS", None):
			# "Scrie răspunsul" (0.7.8): aceeasi intrebare se deschide din coada ca tastatura, pe firul enigma2, la tic
			q = A.intrebareCuNr(nr)
			if q is not None and q.scris:
				self._deScris.add(nr)
				self._intrebari.insert(0, q)
				self._trezesteTic()
		elif rez is False or rez is None or rez is True:
			# True: Verde (alwaysOK al ferestrei Da/Nu) nu e o varianta; ca EXIT, ca echipa sa nu astepte degeaba tot timpul
			A.inchideIntrebarea(nr, "exit")
		# 0.7.8 (ASV4): pagina navigatorului inapoi, daca nu mai vine nicio fereastra a asistentei (o data)
		self._redaDacaLiber()

	def _trezesteTic(self):
		"""_tic indata (dupa inchiderea ferestrei de acum), nu la urmatoarea secunda a ceasului; ceasul ramane plasa."""
		try:
			_trezeste(self._tic)
		except Exception as e:
			_jurnal("trezirea intrebarii: %r" % (e,))

	def _deschideTastatura(self, q):
		"""Tastatura de pe ecran pentru raspunsul scris (0.7.8): antetul e intrebarea (vazuta intreaga in fereastra de
		dinainte), titlul "Întrebare de la HD Satelit"; Verde (Confirm) sau OK pe tasta OK trimite. Ea e acum fereastra
		intrebarii: o inchidem noi la raspunsul din web, la timp si la oprire (inchideIntrebare). Intrebarea primeste timp
		pentru scris (A.incepeScrisul)."""
		self._deScris.discard(q.id)
		try:
			from Screens.VirtualKeyBoard import VirtualKeyBoard
			if self.fereastraMesaj is not None:
				self.fereastraMesaj.ascunde()
			A.incepeScrisul(q.id)
			dlg = self.session.openWithCallback(lambda text=None, nr=q.id: self._dupaTastatura(nr, text), VirtualKeyBoard,
				title=q.text, text="", windowTitle=_(A.TEXT_INTREBARE_TITLU))
			if dlg is None:
				raise RuntimeError("tastatura nu s-a deschis")
			dlg.hdsRaspunsScris = True
			self.fereastraIntrebare = (q.id, dlg)
		except Exception as e:
			_jurnal("tastatura raspunsului: %r" % (e,))
			A.gataScrisul(q.id)
			# fara tastatura omul alege tot din fereastra intrebarii (variantele, sau EXIT)
			if A.intrebareCuNr(q.id) is not None:
				self._intrebari.insert(0, q)

	def _dupaTastatura(self, nr, text=None):
		"""Tastatura raspunsului s-a inchis. Un text (curatat, negol) e raspunsul omului; daca intrebarea s-a inchis intre
		timp, omul afla pe ecran (nu pierde in tacere ce a scris). EXIT sau un text gol: inapoi la fereastra intrebarii, prin
		coada (tic). O inchidere facuta de noi (close(None), dupa ce fereastraIntrebare a fost scoasa) nu face nimic."""
		try:
			self._dupaTastaturaIntrebarii(nr, text)
		finally:
			# 0.7.8 (ASV4): pagina navigatorului inapoi, daca nu mai vine nicio fereastra a asistentei (o data)
			self._redaDacaLiber()

	def _dupaTastaturaIntrebarii(self, nr, text):
		al_nostru = self.fereastraIntrebare is not None and self.fereastraIntrebare[0] == nr
		if al_nostru:
			self.fereastraIntrebare = None
		A.gataScrisul(nr)
		text = A.curataRaspunsScris(text) if isinstance(text, str) else ""
		if text:
			if not A.raspundeIntrebareText(nr, text, "televizor"):
				self._anunta(_(A.TEXT_INTREBARE_INCHISA), "anuntul intrebarii inchise")
			return
		if not al_nostru:
			return
		q = A.intrebareCuNr(nr)
		if q is not None:
			self._intrebari.insert(0, q)
			self._trezesteTic()

	def inchideIntrebare(self, nr):
		"""Pe firul enigma2, dupa ce firul sesiunii a primit raspunsul (sau timpul a trecut, sau s-a raspuns din web):
		intrebarea nr iese din coada, iar fereastra ei se inchide inainte ca echipa sa primeasca raspunsul, ca o tasta OK
		trimisa apoi de echipa sa n-o poata alege in locul omului. -> True."""
		self._intrebari = [q for q in self._intrebari if q.id != nr]
		self._deScris.discard(nr)
		if self.fereastraIntrebare is not None and self.fereastraIntrebare[0] == nr:
			self._inchideFereastraIntrebarii()
		return True

	def _inchideFereastraIntrebarii(self):
		"""Fereastra intrebarii deschise jos, cand e ecranul de sus; altfel o inchide timpul ei, iar un raspuns dat acolo
		mai tarziu nu mai e luat (intrebarea nu mai e deschisa)."""
		f = self.fereastraIntrebare
		self.fereastraIntrebare = None
		if f is None:
			return
		try:
			if self.session.current_dialog is f[1]:
				# tastatura raspunsului (0.7.8) da textul la inchidere: None, ca nimic sa nu para scris de om
				f[1].close(None if getattr(f[1], "hdsRaspunsScris", False) else INTREBARE_INCHISA)
		except Exception as e:
			_jurnal("inchiderea intrebarii: %r" % (e,))


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


def _activitate(ses):
	"""Textul benzii despre ce face echipa (A.textActivitate), sau "" la orice greseala."""
	try:
		return A.textActivitate(ses)
	except Exception:
		return ""


def _fereastraVeche(intrare):
	"""Fereastra concluziilor e a altei sesiuni decat cea care merge acum (A.fereastraVeche); False la orice greseala."""
	try:
		return bool(A.fereastraVeche(intrare))
	except Exception:
		return False


def _trezeste(functie):
	"""Pune functia pe firul enigma2 (e2reactor: callFromThread trezeste bucla)."""
	from twisted.internet import reactor
	reactor.callFromThread(functie)


# lucrul pe firul enigma2 cerut de firul sesiunii (textul ecranului, tastele, textul)
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


def _navigatorDeschis():
	"""Randul navigatorului deschis peste ecran (HbbTV sau web), sau "": e un proces separat, stiva nu il vede."""
	try:
		from Plugins.Extensions.HdsNavigator import lansator
		return lansator.textAsistenta()
	except Exception as e:
		_jurnal("navigatorul: %r" % (e,))
		return ""


def _ecranText():
	"""Textul ecranului (op "ecran"), citit pe firul enigma2; cu navigatorul deschis, intai randul lui."""
	def lucru(gata):
		text = Control.textEcran(_stivaAcum(), Control.modAscii())
		nav = _navigatorDeschis()
		gata(nav + "\n" + text if nav else text)
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
				ecran = Control.textEcran(_stivaAcum(), Control.modAscii())
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
		cod, mesaj = Control.scrieText(ecrane, text, Control.modAscii(), mouse.text)
		if cod == 0:
			mesaj += "\n\n" + Control.textEcran(_stivaAcum(), Control.modAscii())
		gata((cod, mesaj))
	return _peFir.cere(lucru, TERMEN_FIR_S)


def _grab(termen_s, navigator=""):
	"""Octetii JPEG ai capturii (video si OSD), sau None; la esec scrie motivul in jurnalul interfetei
	(hds-interfata.log): termenul depasit, iesirea goala (cu codul) sau eroarea pornirii."""
	cu = " (navigatorul deschis)" if navigator else ""
	# un grab oprit cu kill() care n-a iesit (blocat in driver): altul s-ar bloca la fel (poll() il si culege cand iese)
	_grabRamase[:] = [x for x in _grabRamase if x.poll() is None]
	if _grabRamase:
		_jurnal("captura nereusita%s: grab-ul de dinainte, oprit dupa termen, n-a iesit inca" % cu)
		return None
	try:
		p = subprocess.Popen([GRAB, "-q", "-s", "-j", str(CAPTURA_CALITATE), "-r", str(CAPTURA_LATIME)],
			stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
	except Exception as e:
		_jurnal("captura nereusita%s: grab nu porneste: %r" % (cu, e))
		return None
	try:
		rez, _err = p.communicate(timeout=termen_s)
	except subprocess.TimeoutExpired:
		try:
			p.kill()
		except OSError:
			pass
		try:
			# dupa kill() asteptarea e marginita: un grab in starea D nu moare la SIGKILL si ar tine firul sesiunii
			p.communicate(timeout=CAPTURA_OPRIRE_S)
		except subprocess.TimeoutExpired:
			_grabRamase.append(p)
			try:
				p.stdout.close()
			except Exception:
				pass
		_jurnal("captura nereusita%s: grab a depasit %d s" % (cu, termen_s))
		return None
	if not rez:
		_jurnal("captura nereusita%s: grab nu a dat nimic (cod %s)" % (cu, p.returncode))
		return None
	return rez


def _refuzText():
	"""Textul pentru echipa cand curatarea a refuzat captura (motivul din Control.motivCaptura), sau False cand nu se
	stie motivul (raspunsul ramane "captura nu s-a putut face acum"). 0.7.5 JRN, TODO 12.11 20:36 (EventView pe Trio)."""
	motiv = Control.motivCaptura()
	return "(captura oprita: %s)" % motiv if motiv else False


def _captura():
	"""Video si OSD, cu datele conturilor scoase numai din copia pentru echipa. grab-ul ruleaza aici, pe firul sesiunii
	(CAPTURA_TERMEN_S, cu navigatorul deschis CAPTURA_TERMEN_NAVIGATOR_S), cu bucla enigma2 libera (vezi GRAB); pe firul
	enigma2 numai stiva ecranelor inainte de grab, apoi compararea ei si curatarea. Un ecran deschis sau inchis in timpul
	grab-ului refuza captura cu motiv (curatarea ar acoperi zonele altui ecran decat cel din poza); se compara numai
	ecranele (id), nu textele lor: ecranul Asistenta isi scrie jurnalul la fiecare cerere (bucla din 0.7.2)."""
	navigator = _navigatorDeschis()
	cu = " (navigatorul deschis)" if navigator else ""
	if _session() is None:
		return "(captura: interfata nu e gata)"
	inainte = _peFir.cere(lambda gata: gata([id(e) for e in _stivaAcum()]), TERMEN_FIR_S)
	if inainte is None:
		_jurnal("captura nereusita%s: firul interfetei nu a raspuns in %d s" % (cu, TERMEN_FIR_S))
		return None
	brut = _grab(CAPTURA_TERMEN_NAVIGATOR_S if navigator else CAPTURA_TERMEN_S, navigator)
	if not brut:
		return None

	def curata(gata):
		ecrane = _stivaAcum()
		if [id(e) for e in ecrane] != inainte:
			_jurnal("captura refuzata: ecranele s-au schimbat in timpul capturii")
			gata("(captura oprita: ecranul s-a schimbat in timpul capturii, cere din nou)")
			return
		from enigma import getDesktop
		s = getDesktop(0).size()
		# False (nu None) cand curatarea nu da nimic: None inseamna numai "firul nu a raspuns la timp"
		gata(Control.curataCapturaEchipa(brut, ecrane, (s.width(), s.height())) or _refuzText() or False)
	rez = _peFir.cere(curata, TERMEN_FIR_S)
	if rez is None:
		_jurnal("captura nereusita%s: firul interfetei nu a raspuns in %d s" % (cu, TERMEN_FIR_S))
	return rez or None


def _pisteCanal():
	"""Randurile cu pistele canalului deschis, pentru op "canal" (0.7.5, TC308, canalele fara sunet de pe 101W): pistele de
	sunet asa cum le-a inteles nucleul (PID, descriere, limba) si pistele din PMT pe care nucleul nu le cunoaste
	(iServiceInformation.sPisteNecunoscute, "pid:stream_type:inregistrare" in hex). Asa se vede din prima de ce un canal
	n-are sunet, fara taste pe ecranul omului. Numai citire; la orice lipsa, randul spune ce lipseste."""
	randuri = ["[piste]"]
	try:
		import NavigationInstance
		from enigma import iServiceInformation
		nav = NavigationInstance.instance
		serviciu = nav.getCurrentService() if nav else None
		info = serviciu and serviciu.info()
		if not info:
			randuri.append("  (fara canal deschis)")
			return randuri
		sunete = []
		piste = serviciu.audioTracks()
		n = piste.getNumberOfTracks() if piste else 0
		for i in range(n):
			t = piste.getTrackInfo(i)
			if t is None:
				continue
			sunete.append("%04x %s %s" % (t.getPID() & 0x1FFF, t.getDescription() or "?", t.getLanguage() or "-"))
		randuri.append("  Piste de sunet = %s" % (", ".join(sunete) if sunete else "niciuna"))
		randuri.append("  Piste necunoscute (PMT) = %s" % (info.getInfoString(iServiceInformation.sPisteNecunoscute) or "niciuna"))
	except Exception as e:
		randuri.append("  (pistele nu se pot citi: %r)" % (e,))
	return randuri


def _canal():
	"""Canalul deschis (op "canal"), ca Informatii despre canal (paginile din canal_info_web), pe firul enigma2."""
	def lucru(gata):
		from Plugins.Extensions.HdsWebControl import canal_info_web
		d = canal_info_web.stare()
		randuri = ["Canal deschis: %s%s" % ("da" if d.get("are_canal") else "nu", " (standby)" if d.get("standby") else "")]
		for p in d.get("pagini") or []:
			randuri.append("[%s]" % p.get("id"))
			for r in p.get("randuri") or []:
				if len(r) >= 2 and (str(r[0]).strip() or str(r[1]).strip()):
					randuri.append("  %s = %s" % (r[0], r[1]))
		randuri.extend(_pisteCanal())
		gata("\n".join(randuri))
	return _peFir.cere(lucru, TERMEN_FIR_S)


def _flux():
	"""Op "flux": de pe firul enigma2 numai referinta canalului deschis si demuxul lui (HdsAnalizaFlux.parametri, numere
	simple); filtrele de sectiune le citeste apoi broker-ul, pe firul sesiunii (Components/HdsAsistentaFlux)."""
	def lucru(gata):
		import NavigationInstance
		from Components.HdsAnalizaFlux import parametri
		nav = NavigationInstance.instance
		serviciu = nav.getCurrentService() if nav is not None else None
		ref = nav.getCurrentlyPlayingServiceReference() if nav is not None else None
		if serviciu is None or ref is None:
			gata({})
			return
		sref = ref.toString()
		canal = ""
		try:
			info = serviciu.info()
			canal = (info.getName() if info else "") or ""
		except Exception:
			pass
		# la televiziunea prin internet (4097, 5001, 5002...) referinta are adresa: nu pleaca, iar demuxul nu exista
		if not sref.startswith("1:"):
			gata({"ref": "iptv", "demux": None})
			return
		p = parametri(serviciu, sref, canal)
		try:
			# o inregistrare sau un flux TS din retea (1:...:cale): demuxul e al redarii, nu al antenei
			p["din_cale"] = bool(ref.getPath())
		except Exception:
			pass
		gata(p)
	return _peFir.cere(lucru, TERMEN_FIR_S)


# Op "flux" pe un transponder ales (TODO 15.11 01:55): canalul brut al tunerului liber, tinut numai cat il citeste
# broker-ul. Referinta se lasa NUMAI pe firul enigma2 (atunci tunerul se elibereaza), dupa citire sau, daca sesiunea
# se rupe la mijloc, singura dupa HdsAsistentaFlux.PAZA_S.
_fluxTp = {"canal": None, "paza": None}


def _lasaTunerulFlux():
	"""Pe firul enigma2: elibereaza tunerul luat de op-ul flux (referinta canalului brut lasata) si opreste paza."""
	_fluxTp["canal"] = None
	paza = _fluxTp["paza"]
	_fluxTp["paza"] = None
	if paza is not None:
		try:
			paza.stop()
		except Exception:
			pass


def _pozitieMotor(slot):
	"""Unde e antena tunerului cu motor, dupa nucleu (hdsKnownRotorPosition; -1 = nestiut), sau None."""
	try:
		from enigma import eDVBSatelliteEquipmentControl
		return int(eDVBSatelliteEquipmentControl.getInstance().hdsKnownRotorPosition(slot))
	except Exception:
		return None


def _fluxTransponder(cerut):
	"""Op "flux" cu transponder: pe firul enigma2 un tuner liber setat pentru pozitie, acordat pe transponderul cerut, cu
	demuxul luat (Components/HdsAsistentaFlux.ia_tuner_liber); canalul omului nu se schimba. Filtrele le citeste apoi
	broker-ul, pe firul sesiunii, si cheama _elibereazaFluxTp. -> dict (cu "eroare" cand nu se poate) sau None."""
	def lucru(gata):
		import time
		from enigma import eDVBResourceManager
		from Components import HdsAsistentaFlux as F
		from Components import HdsGasireSemnal as G
		_lasaTunerulFlux()

		def aloca(slot):
			return eDVBResourceManager.getInstance().allocateRawChannel(slot)
		urm = G.urmatoarea_inregistrare()
		curand = urm is not None and urm - time.time() < F.FARA_INREGISTRARE_S
		rez, canal = F.ia_tuner_liber(cerut, G.tunere(), G.transpondere, aloca, G.acordeaza,
			motiv_refuz=G._reguli().motiv_refuz, pozitie_motor=_pozitieMotor, inregistrare_curand=curand)
		if canal is not None:
			_fluxTp["canal"] = canal
			paza = eTimer()
			paza.callback.append(_lasaTunerulFlux)
			paza.start(int(F.PAZA_S * 1000), True)
			_fluxTp["paza"] = paza
			_jurnal("flux: tunerul %s luat pentru %s (demux %s)" % (rez.get("litera"), F.text_cerut(cerut), rez.get("demux")))
		gata(rez)
	return _peFir.cere(lucru, TERMEN_FIR_S)


def _elibereazaFluxTp():
	"""Din firul sesiunii, dupa citirea op-ului flux: tunerul liber se elibereaza pe firul enigma2."""
	def lucru(gata):
		_lasaTunerulFlux()
		gata(True)
	return _peFir.cere(lucru, TERMEN_FIR_S)


def _zap(referinta):
	"""Porneste canalul (op "zap"), ca din lista de canale, pe firul enigma2. -> (cod, text)."""
	def lucru(gata):
		import NavigationInstance
		from enigma import eServiceReference
		nav = NavigationInstance.instance
		if nav is None:
			gata((1, "(navigatia nu e gata)"))
			return
		ref = eServiceReference(referinta)
		if not ref.valid():
			gata((1, "(referinta rea)"))
			return
		nav.playService(ref)
		try:
			from Components.HdsCanalTinut import tine_minte
			tine_minte(ref)
		except Exception:
			pass
		gata((0, "pornit: %s" % referinta))
	return _peFir.cere(lucru, TERMEN_FIR_S)


TEXT_REPORNESTE_INTERFATA = N_("HD Satelit repornește acum interfața receptorului. Asistența continuă după repornire.")
TEXT_REPORNESTE_RECEPTOR = N_("HD Satelit repornește acum receptorul. Asistența continuă după repornire.")
REPORNIRE_DUPA_MS = 6000


def _reporneste(ce):
	"""Repornirea (op "reporneste"): anuntul pe ecran, apoi, dupa REPORNIRE_DUPA_MS (raspunsul pleaca intre timp si
	starea sesiunii e scrisa), interfata (quitMainloop 3) sau receptorul (quitMainloop 2). Sesiunea se reia singura dupa
	repornire (A.reia, din fisierul de stare). -> (cod, text)."""
	def lucru(gata):
		s = _session()
		if s is None:
			gata((1, "(fara sesiunea enigma2)"))
			return
		cod = 3 if ce == "interfata" else 2
		try:
			from Screens import HdsAnuntRetea
			HdsAnuntRetea.arata(s, _(TEXT_REPORNESTE_INTERFATA if cod == 3 else TEXT_REPORNESTE_RECEPTOR), "info")
		except Exception as e:
			_jurnal("anuntul repornirii: %r" % (e,))
		ceas = eTimer()

		def acum():
			ceas.stop()
			_vii.discard(ceas)
			try:
				from Screens.Standby import TryQuitMainloop
				s.open(TryQuitMainloop, cod)
			except Exception as e:
				_jurnal("repornirea: %r" % (e,))
				from enigma import quitMainloop
				quitMainloop(cod)
		ceas.callback.append(acum)
		_vii.add(ceas)
		ceas.start(REPORNIRE_DUPA_MS, True)
		gata((0, "repornesc %s in %d s; asistenta continua dupa repornire" % (ce, REPORNIRE_DUPA_MS // 1000)))
	return _peFir.cere(lucru, TERMEN_FIR_S)


TEXT_REPARA_PORNITA = ("pornit: cautarea in feedul HD Satelit, apoi instalarea (si pachetele imaginii ramase la jumatate sau cu "
	"fisiere sterse, cu --force-reinstall, ca la Repară imaginea) si repornirea interfetei; pasii in jurnalul "
	"hds-actualizari.log (randurile 'repara imaginea'), asistenta continua dupa repornire")


def _reparaActualizarea():
	"""Op "repara-actualizarea" (0.7.5, JAK, TODO 13.11 11:20): actualizarea rapida din meniu (HdsActualizari.actualizeazaRapid:
	cautarea semnata, planul cu pachetele imaginii ramase la jumatate, instalarea si repornirea interfetei), pornita pe
	firul enigma2, ca "Da" la o versiune din feed (HdsImagineOnline.porneste_feed). Omul nu tasteaza nimic, iar echipa nu
	da nicio comanda opkg: numai pachete din feedul semnat. -> (cod, text) imediat; restul il spune jurnalul."""
	def lucru(gata):
		from Components import HdsActualizari as Act
		a = Act.actualizari
		if a.ocupat():
			gata((1, "(actualizarile lucreaza acum: %s; incearca peste un minut)" % a.faza))
			return
		try:
			from Plugins.Extensions.HdsWebControl.actualizari_web import reporneste_rapid
		except ImportError as e:
			gata((1, "(repornirea dupa actualizare lipseste: %s)" % e))
			return
		# 0.7.8 (RPR8): „Repară imaginea” cu actualizarea (tot=True: si actualizarea gasita, ca inainte, plus fisierele sterse
		# ale imaginii puse la loc); un modul mai vechi in memorie: actualizarea rapida, ca inainte
		if hasattr(a, "reparaImaginea"):
			pornit = a.reparaImaginea(reporneste_rapid(_session), tot=True)
		else:
			pornit = a.actualizeazaRapid(reporneste_rapid(_session))
		if not pornit:
			gata((1, "(actualizarea nu a pornit: %s)" % (a.mesaj or a.poate_porni() or "?")))
			return
		gata((0, TEXT_REPARA_PORNITA))
	return _peFir.cere(lucru, TERMEN_FIR_S)


def _reparaBuchetele():
	"""Porneste pe firul interfetei; asteapta numai firul brokerului."""
	def lucru(gata):
		from Components import HdsReparaBuchete as R
		def terminat(rez):
			if rez is None:
				gata((1, R.mesaj_web() or _("Lista nu s-a putut repara. Nu am șters niciun buchet.")))
			else:
				gata((0, R.mesaj(rez) or _("Lista de buchete este în regulă. Nu am schimbat nimic.")))
		if not R.cerere(la_gata=terminat):
			gata((1, _("Lista de canale este în lucru. Încearcă din nou peste câteva secunde.")))
	return _peFir.cere(lucru, 60)


def _setare(cheie, valoare):
	"""O setare scrisa direct (op "setare-scrie"), pe firul enigma2, cu efectele ei; la tunere, actualizarea lor ca din
	meniu. -> (cod, text)."""
	def lucru(gata):
		from Components.config import config, configfile

		def dupa(c):
			if c.startswith("config.Nims."):
				from Components.NimManager import nimmanager
				nimmanager.sec.update()
		gata(Control.scrieSetare(config, cheie, valoare, salveaza=configfile.save, dupa=dupa))
	return _peFir.cere(lucru, TERMEN_FIR_S)


def _intrebare(text, variante="", secunde="", stop=None):
	"""Op "intrebare" (brokerul, pe firul sesiunii): intrebarea noua (A.puneIntrebare) merge la controler (fereastra de pe
	televizor; pagina web o vede in A.stare()), firul asteapta raspunsul (A.asteaptaRaspuns: raspunsul omului, timpul,
	EXIT, oprirea asistentei), apoi fereastra se inchide pe firul enigma2 si abia dupa aceea pleaca raspunsul cererii.
	-> (cod, text) pentru echipa."""
	c = _controler[0]
	if c is None:
		return 1, "(intrebarea nu se poate arata: interfata nu e gata)"
	# ASP7 (REGULA 0, 22.11.2026): raspunsul scris se cere la orice intrebare, si despre parole, chei sau conturi
	q = A.puneIntrebare(text, variante, secunde)
	if q is None:
		return 1, "(variante rele: intre 2 si %d, diferite, fiecare cel mult %d semne, despartite cu |)" % (
			A.INTREBARE_VARIANTE_MAX, A.INTREBARE_VARIANTA_SEMNE)
	c.cereIntrebare(q)
	try:
		# fereastra indata, nu la urmatoarea secunda a ceasului controlerului
		_trezeste(c._tic)
	except Exception as e:
		_jurnal("trezirea intrebarii: %r" % (e,))
	A.asteaptaRaspuns(q, stop)
	_peFir.cere(lambda gata: gata(c.inchideIntrebare(q.id)), TERMEN_FIR_S)
	return A.textRaspunsIntrebare(q)


def _setariAcum():
	"""settings de acum pentru copia de dinaintea asistentei (A.Sesiune._copia_inainte, „Pune înapoi cum era”):
	HdsCopieSetari.text_setari_acum (SETARI_FIXE puse, apoi config.pickle()), pe firul enigma2, ca la „Copia setărilor”.
	-> text sau None (dupa termen sau fara arborele config: copia ia atunci fisierul de pe disc)."""
	def lucru(gata):
		from Components import HdsCopieSetari
		gata(HdsCopieSetari.text_setari_acum())
	return _peFir.cere(lucru, TERMEN_FIR_S)


def ctxReceptor(session):
	ctx = {}
	ctx["captura"] = _captura
	# settings de acum, pentru copia facuta cand intra echipa; numai ctx-ul receptorului il are (si deci face copia)
	ctx["setari_acum"] = _setariAcum
	# AST8: cu raspunsul la intrebarea de inceput deasupra (_ecranCuInceput)
	ctx["ecran"] = _ecranCuInceput
	ctx["taste"] = _taste
	ctx["text"] = _text
	ctx["canal"] = _canal
	ctx["flux"] = _flux
	ctx["flux_tp"] = _fluxTransponder
	ctx["flux_tp_elibereaza"] = _elibereazaFluxTp
	ctx["zap"] = _zap
	ctx["reporneste"] = _reporneste
	ctx["setare"] = _setare
	ctx["repara_actualizarea"] = _reparaActualizarea
	ctx["repara_buchetele"] = _reparaBuchetele
	ctx["intrebare"] = _intrebare
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

def porneste(session, nivel=None, durata_min=None, de_la="televizor", versiune_text=None, nevoie="", detalii=""):
	if versiune_text is None:
		versiune_text = A.VERSIUNE_TEXT
	if nivel is None:
		nivel = A.NIVEL_PORNIRE
	if durata_min is None:
		durata_min = A.DURATA_IMPLICITA_MIN
	limba = _limba()
	rez = A.porneste(nivel=nivel, durata_min=durata_min, limba=limba, de_la=de_la,
		versiune_text=versiune_text, ctx=ctxReceptor(session), nevoie=nevoie, detalii=detalii)
	if rez[0]:
		# AST8: "Cu ce te ajut?" indata, fara sa astepte echipa (pornesteInceput, la sfarsitul fisierului)
		pornesteInceput()
	return rez


def reia(session):
	try:
		A.reia(ctx=ctxReceptor(session))
	except Exception as e:
		_jurnal("reluare: %r" % (e,))


def puneInapoi(session):
	"""Albastru "Pune înapoi cum era" (Screens/HdsAsistenta.py: ecranul asistentei si pagina de pornire): o singura
	intrebare, cu "Nu" ales (aceeasi ca la „Copia setărilor”: HdsCopieSetari.text_intrebare_punere), apoi cererea
	(A.cerePunereaInapoi) si repornirea interfetei, ca in Screens/HdsCopieSetari.py; copia o pune la loc enigma2.sh,
	inaintea interfetei. Sesiunea de asistenta nu se opreste (se reia singura dupa repornire). Aici, nu in
	Screens/HdsAsistenta.py: acolo Start porneste fara nicio intrebare (regula 0.6.13)."""
	copie = A.stareCopie()
	if not copie:
		return
	from Screens.MessageBox import MessageBox

	def dupa(da=False):
		if not da:
			return
		ok, mesaj = A.cerePunereaInapoi()
		if not ok:
			session.open(MessageBox, mesaj, MessageBox.TYPE_ERROR, timeout=10)
			return
		from Screens.Standby import TryQuitMainloop
		session.open(TryQuitMainloop, 3)
	session.openWithCallback(dupa, MessageBox, copie["intrebare"], MessageBox.TYPE_YESNO, default=False)


# Rosu "Oprește" pe ecranul asistentei, dupa Start (RCF, 15-16.11.2026)
TEXT_OPRESTI_ASISTENTA = N_("Oprești asistența?")
# o intrebare uitata deschisa (omul a plecat de la televizor) s-ar pune in calea tastelor trimise de echipa: dupa atatea
# secunde se inchide singura cu "Nu", iar asistenta ramane pornita
OPRIRE_INTREBARE_S = 30


def intreabaOprirea(session, dupa):
	"""Rosu "Oprește" pe ecranul asistentei (Screens/HdsAsistenta.py), cat asistenta merge: o intrebare scurta, cu "Nu"
	ales. Pe pagina de pornire Rosu e "Înapoi", iar dupa Start, pe acelasi ecran si in acelasi loc, opreste; pe 15.11.2026
	trei sesiuni s-au oprit asa, din greseala, la 35 s - 2 minute dupa salut (STADIU-ASX.md). dupa(da) primeste True
	numai la "Da"; "Nu", EXIT si timpul trecut dau False. Aici, nu in Screens/HdsAsistenta.py: acolo Start porneste fara
	nicio intrebare (regula 0.6.13). Tot ea si la Rosu din fereastra concluziilor: numai Rosu + „Da” opresc
	asistenta. Verde (alwaysOK in MsgBoxActions) ar fi inchis fereastra cu True, adica „Da” fara randul ales, iar pe
	ecranul asistentei Verde e „Schimbă durata”: aici Verde face ce face OK pe randul ales („Nu”, ales la deschidere)."""
	from Screens.MessageBox import MessageBox
	dlg = session.openWithCallback(lambda da=False: dupa(da is True), MessageBox, _(TEXT_OPRESTI_ASISTENTA),
		MessageBox.TYPE_YESNO, default=False, timeout=OPRIRE_INTREBARE_S, timeout_default=False)
	try:
		if dlg is not None:
			dlg["actions"].actions["alwaysOK"] = dlg.ok
	except Exception as e:
		_jurnal("intrebarea opririi (Verde): %r" % (e,))
	return dlg


def alegeDurata(session, dupa):
	"""Verde "Schimbă durata" pe ecranul asistentei pornite (Screens/HdsAsistenta.py): lista celor cinci durate
	(A.alegeriDurata), cu cea de acum aleasa; OK o schimba pe loc, socotita de acum (A.schimbaDurata), fara alta intrebare.
	EXIT lasa durata cum era. dupa(reusit) dupa alegere (False la EXIT). Aici, ca intreabaOprirea: ecranul asistentei nu
	deschide el ferestre de alegere."""
	from Screens.ChoiceBox import ChoiceBox
	alegeri = A.alegeriDurata()
	ses = A.sesiune()
	acum = getattr(ses, "durata_min", None)
	minute = [m for m, t in alegeri]
	sel = minute.index(acum) if acum in minute else 0

	def gata(ales=None):
		reusit = False
		if ales:
			reusit, _mesaj = A.schimbaDurata(ales[1], "televizor")
		dupa(reusit)
	session.openWithCallback(gata, ChoiceBox, title=_("Cât timp"), list=[(text, m) for m, text in alegeri],
		selection=sel)


TEXT_WEB_PE_RECEPTOR = N_("Pe receptor s-a deschis Asistența de la distanță: apasă Start acolo.")
TEXT_WEB_NU_POT = N_("Nu pot deschide Asistența de la distanță pe receptor acum.")


def _durataAleasa(durata_min):
	"""Durata venita din web (minute, ca text sau numar): una din A.DURATE_PRIMITE, altfel cea implicita (2 ore)."""
	try:
		durata_min = int(durata_min)
	except (TypeError, ValueError):
		return A.DURATA_IMPLICITA_MIN
	return durata_min if durata_min in A.DURATE_PRIMITE else A.DURATA_IMPLICITA_MIN


def pornesteWeb(session, nivel=None, durata_min=None):
	"""Start din web, dupa poarta locala: porneste direct si anunta pe receptor.
	Asistenta completa, cu durata aleasa in pagina (lipsa: 2 ore), fara intrebari. -> (reusit, mesaj)."""
	ses = A.sesiune()
	if ses is not None and ses.activa():
		return False, _("Asistența merge deja.")
	reusit, mesaj = porneste(session, nivel=nivel if nivel in A.NIVELE else A.NIVEL_PORNIRE,
		durata_min=_durataAleasa(durata_min),
		de_la="web")
	if reusit:
		try:
			from Screens import HdsAnuntRetea
			ses = A.sesiune()
			text = _("Asistența a pornit.") if ses is not None and ses.id else _(A.TEXT_VERIFICA)
			HdsAnuntRetea.arata(session,
				"%s (%s)" % (text, _("din pagina web")), "info")
		except Exception as e:
			_jurnal("anuntul pornirii din web: %r" % (e,))
	return reusit, mesaj


def cerereWeb(session, nivel="A", durata_min=None, nevoie="", detalii=""):
	"""Rezerva pentru apelurile fara incredere: deschide pagina de pornire pe receptor, cu durata aleasa in pagina web
	pusa pe randul "Cât timp". Porneste numai la Start apasat acolo. Ceilalti parametri raman pentru apelurile vechi.
	Ruta web locala foloseste pornesteWeb. -> (reusit, mesaj) despre deschiderea paginii."""
	if session is None:
		return False, _(TEXT_WEB_NU_POT)
	ses = A.sesiune()
	if ses is not None and ses.activa():
		return False, _("Asistența merge deja.")
	try:
		from Tools import Notifications
		from Screens.HdsAsistenta import HdsAsistenta
		Notifications.AddNotification(HdsAsistenta, din_web=_durataAleasa(durata_min))
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


# ---------------------------------------------------------------- intrebarea de inceput, iesirea, motivul opririi (AST8)
#
# 22.11.2026 (AS115, AS118, AS116): un om a pornit si a oprit asistenta de cinci ori in 19-111 s, fara sa spuna ce vrea, iar
# altul a oprit-o dupa cinci intrebari la rand. Deci:
# - indata ce sesiunea a pornit (porneste, inainte de inregistrare si de echipa), pe televizor si in pagina web intrebarea
#   "Cu ce te ajut?" cu variantele mari (INCEPUT_VARIANTE) si, din 0.7.8, randul "Altceva, scriu eu" (tastatura de pe
#   ecran, raspunsul scris); pe 0.7.7 "Altceva" e o varianta obisnuita. E aceeasi intrebare ca la op "intrebare" (A.Intrebare,
#   un singur loc), asteptata de un fir al ei (_asteaptaInceput), nu de o cerere: firul sesiunii nu sta dupa ea. Raspunsul
#   ajunge la echipa ca primul rand al op "ecran" (_ecranCuInceput: "intrebarea de inceput ...: raspuns: ..."; "inca
#   deschisa" cat omul n-a ales), deci fara camp nou pe server si fara op nou in catalog;
# - EXIT pe ecranul asistentei lasa asistenta pornita (ca pana acum) si spune asta intr-un anunt scurt (anuntaIesirea);
# - Rosu "Oprește" + Da: o singura intrebare optionala, "De ce oprești?" (intreabaMotivul); EXIT sau timpul o sar. Motivul
#   pleaca la server in campul "motiv" de la inchidere (tiparul lui: ASCII, cel mult 60 de semne): "de om (ecran): terminat".
# Textele: N_ (traducerile din .po, cand vin) si, pana atunci, INCEPUT_LIMBI pentru limbile in care ne cer oamenii ajutor
# (un pachet de proba pe 0.7.7 nu aduce .po).

INCEPUT_TEXT = N_("Cu ce te ajut?")
# (cheia pentru echipa, ASCII; eticheta pentru om)
INCEPUT_VARIANTE = (
	("Canale si receptie", N_("Canale și recepție")),
	("Internet si IPTV", N_("Internet și IPTV")),
	("Imagine si sunet", N_("Imagine și sunet")),
	("Extensii si actualizari", N_("Extensii și actualizări")),
)
INCEPUT_ALTCEVA = ("Altceva", N_("Altceva"))
INCEPUT_SCRIU = N_("Altceva, scriu eu")
# cat sta deschisa (cat intrebarea cea mai lunga a echipei); omul o inchide oricand cu EXIT
INCEPUT_S = 300
TEXT_FUNDAL = N_("Asistența lucrează. Poți privi televizorul; te anunț pe ecran când am ceva.")
TEXT_DE_CE_OPRESTI = N_("De ce oprești?")
# (codul pentru motivul de pe server, ASCII scurt; eticheta pentru om)
MOTIVE_OM = (
	("terminat", N_("Am terminat")),
	("dura-mult", N_("Durează prea mult")),
	("nu-stiu", N_("Nu știam ce să fac")),
	("altceva", N_("Altceva")),
)
# cat sta "De ce oprești?" (pe receptorul de proba, incarcat, 20 s nu ajungeau: tastele omului au mers apoi in meniu)
MOTIV_S = 30
# anuntul de la EXIT: cat sta (nu dispare la tasta: EXIT-ul insusi, la ridicare, l-ar ascunde indata)
ANUNT_IESIRE_MS = 8000
INCEPUT_RAND = "intrebarea de inceput (Cu ce te ajut?)"

INCEPUT_LIMBI = {
	"en": ("How can I help you?", "Channels and reception", "Internet and IPTV",
		"Picture and sound", "Plugins and updates", "Something else", "Something else, I'll type it",
		"Assistance keeps working. You can watch TV; I'll let you know on screen when I have something.",
		"Why are you stopping?", "I'm done", "It takes too long", "I didn't know what to do"),
	"pl": ("W czym mogę pomóc?", "Kanały i odbiór", "Internet i IPTV", "Obraz i dźwięk",
		"Wtyczki i aktualizacje", "Coś innego", "Coś innego, napiszę",
		"Pomoc działa dalej. Możesz oglądać telewizję; dam znać na ekranie, gdy będę coś miał.",
		"Dlaczego wyłączasz?", "Skończyłem", "Trwa za długo", "Nie wiedziałem, co robić"),
	"it": ("Come posso aiutarti?", "Canali e ricezione", "Internet e IPTV",
		"Immagine e audio", "Plugin e aggiornamenti", "Altro", "Altro, lo scrivo io",
		"L'assistenza continua a lavorare. Puoi guardare la TV; ti avviso sullo schermo quando ho qualcosa.",
		"Perché la fermi?", "Ho finito", "Ci vuole troppo", "Non sapevo cosa fare"),
	"de": ("Wobei kann ich helfen?", "Kanäle und Empfang", "Internet und IPTV",
		"Bild und Ton", "Plugins und Updates", "Etwas anderes", "Etwas anderes, ich schreibe es",
		"Die Hilfe arbeitet weiter. Du kannst fernsehen; ich melde mich auf dem Bildschirm, wenn ich etwas habe.",
		"Warum beendest du?", "Ich bin fertig", "Dauert zu lange", "Ich wusste nicht, was ich tun soll"),
	"fr": ("Comment puis-je t'aider ?", "Chaînes et réception",
		"Internet et IPTV", "Image et son", "Plugins et mises à jour", "Autre chose", "Autre chose, je l'écris",
		"L'assistance continue. Tu peux regarder la télé ; je te préviens à l'écran quand j'ai du nouveau.",
		"Pourquoi arrêtes-tu ?", "J'ai fini", "C'est trop long", "Je ne savais pas quoi faire"),
	"tr": ("Sana nasıl yardım edebilirim?", "Kanallar ve sinyal", "İnternet ve IPTV",
		"Görüntü ve ses", "Eklentiler ve güncellemeler", "Başka bir şey", "Başka bir şey, yazacağım",
		"Destek çalışmaya devam ediyor. Televizyon izleyebilirsin; bir şey olduğunda ekranda haber veririm.",
		"Neden durduruyorsun?", "Bitirdim", "Çok uzun sürüyor", "Ne yapacağımı bilmiyordum"),
	"ru": ("Чем могу помочь?", "Каналы и приём", "Интернет и IPTV",
		"Изображение и звук", "Плагины и обновления", "Другое", "Другое, напишу сам",
		"Помощь продолжает работать. Можете смотреть ТВ; я сообщу на экране, когда что-то будет.",
		"Почему вы останавливаете?", "Я закончил", "Слишком долго", "Не знал, что делать"),
	"es": ("¿En qué te ayudo?", "Canales y recepción", "Internet e IPTV",
		"Imagen y sonido", "Plugins y actualizaciones", "Otra cosa", "Otra cosa, la escribo",
		"La asistencia sigue trabajando. Puedes ver la tele; te aviso en pantalla cuando tenga algo.",
		"¿Por qué la detienes?", "Ya terminé", "Tarda demasiado", "No sabía qué hacer"),
	"el": ("Πώς μπορώ να σε βοηθήσω;", "Κανάλια και λήψη", "Internet και IPTV",
		"Εικόνα και ήχος", "Πρόσθετα και ενημερώσεις", "Κάτι άλλο", "Κάτι άλλο, θα το γράψω",
		"Η βοήθεια συνεχίζει. Μπορείς να βλέπεις τηλεόραση· θα σε ειδοποιήσω στην οθόνη όταν έχω κάτι.",
		"Γιατί τη σταματάς;", "Τελείωσα", "Αργεί πολύ", "Δεν ήξερα τι να κάνω"),
	"hu": ("Miben segíthetek?", "Csatornák és vétel", "Internet és IPTV",
		"Kép és hang", "Bővítmények és frissítések", "Más", "Más, beírom",
		"A segítség tovább dolgozik. Nézheted a tévét; szólok a képernyőn, ha van valami.",
		"Miért állítod le?", "Végeztem", "Túl sokáig tart", "Nem tudtam, mit tegyek"),
}
# ordinea textelor din INCEPUT_LIMBI (textele romanesti de mai sus)
_INCEPUT_ORDINE = (INCEPUT_TEXT,) + tuple(e for _c, e in INCEPUT_VARIANTE) + (INCEPUT_ALTCEVA[1], INCEPUT_SCRIU,
	TEXT_FUNDAL, TEXT_DE_CE_OPRESTI) + tuple(e for _c, e in MOTIVE_OM[:3])

# (sesiunea, intrebarea) pentru sesiunea pornita acum
_inceput = [None]


def trInceput(text):
	"""Textul tradus: din .po cand exista; altfel, in limbile din INCEPUT_LIMBI, de acolo; altfel romana."""
	try:
		tradus = _(text)
	except Exception:
		tradus = text
	limba = _limba()
	if tradus != text or limba == "ro" or limba not in INCEPUT_LIMBI or text not in _INCEPUT_ORDINE:
		return tradus
	return INCEPUT_LIMBI[limba][_INCEPUT_ORDINE.index(text)]


def textIesire():
	return trInceput(TEXT_FUNDAL)


def puneInceput():
	"""Intrebarea de inceput, cea deschisa de acum (A.Intrebare cu variantele INCEPUT_VARIANTE si, cand imaginea stie
	raspunsul scris, randul "Altceva, scriu eu"; altfel varianta "Altceva"). -> intrebarea."""
	scris = hasattr(A, "INTREBARE_SCRIS")
	chei = [c for c, _e in INCEPUT_VARIANTE] + ([] if scris else [INCEPUT_ALTCEVA[0]])
	etichete = [trInceput(e) for _c, e in INCEPUT_VARIANTE] + ([] if scris else [trInceput(INCEPUT_ALTCEVA[1])])
	with A._lacatIntrebare:
		vechi = A._intrebare[0]
		if vechi is not None and not vechi.gata.is_set():
			vechi.fara = "inlocuita"
			vechi.gata.set()
		A._intrebareNr[0] += 1
		if scris:
			q = A.Intrebare(A._intrebareNr[0], trInceput(INCEPUT_TEXT), chei, etichete, INCEPUT_S, scris=True)
			# eticheta randului scris, pe televizor (Controler._deschideIntrebarea) si in pagina web (public)
			q.eticheta_scris = trInceput(INCEPUT_SCRIU)
		else:
			q = A.Intrebare(A._intrebareNr[0], trInceput(INCEPUT_TEXT), chei, etichete, INCEPUT_S)
		q.inceput = True
		A._intrebare[0] = q
	return q


def pornesteInceput():
	"""Dupa Start (porneste): intrebarea de inceput pe televizor si in web, fara sa astepte echipa; firul ei o inchide la
	raspuns, la timp sau la oprirea asistentei, ca op "intrebare". Nu arunca."""
	try:
		c = _controler[0]
		ses = A.sesiune()
		if c is None or ses is None or not ses.activa():
			return
		q = puneInceput()
		_inceput[0] = (ses, q)
		c.cereIntrebare(q)
		try:
			_trezeste(c._tic)
		except Exception as e:
			_jurnal("trezirea intrebarii de inceput: %r" % (e,))
		import threading
		fir = threading.Thread(target=_asteaptaInceput, args=(c, q), name="HdsAsistentaInceput")
		fir.daemon = True
		fir.start()
	except Exception as e:
		_jurnal("intrebarea de inceput: %r" % (e,))


def _asteaptaInceput(c, q):
	try:
		A.asteaptaRaspuns(q)
		_peFir.cere(lambda gata: gata(c.inchideIntrebare(q.id)), TERMEN_FIR_S)
		_jurnal("intrebarea de inceput: %s" % A.textRaspunsIntrebare(q)[1])
	except Exception as e:
		_jurnal("intrebarea de inceput (fir): %r" % (e,))


def randInceput():
	"""Randul pentru echipa (primul rand al op "ecran"): raspunsul la intrebarea de inceput a sesiunii de acum, "inca
	deschisa" cat omul n-a ales, sau "" cand sesiunea n-are intrebare de inceput (reluata dupa o repornire)."""
	o = _inceput[0]
	if o is None or o[0] is not A.sesiune():
		return ""
	q = o[1]
	if not q.gata.is_set() and q.ramasS() > 0:
		return "%s: inca deschisa pe televizor de %d s (raspunsul vine la un op ecran urmator)" % (
			INCEPUT_RAND, max(0, int(A._acum() - q.pornita)))
	return "%s: %s" % (INCEPUT_RAND, A.textRaspunsIntrebare(q)[1])


def _ecranCuInceput():
	"""Op "ecran": textul ecranului, cu randul intrebarii de inceput deasupra (cand e)."""
	text = _ecranText()
	rand = randInceput()
	if not rand:
		return text
	return rand + "\n\n" + (text if text is not None else "(ecranul nu a raspuns la timp)")


# ceasul anuntului de la EXIT (tinut, ca eTimer-ul sa nu dispara inainte de vreme)
_ceasIesire = [None]


def anuntaIesirea(session, dupa_ms=400):
	"""EXIT pe ecranul asistentei, cat merge: asistenta ramane pornita; un anunt scurt, nemodal, spune asta. Vine dupa
	dupa_ms, cand ecranul de dedesubt (meniul sau imaginea canalului) s-a aratat: pus inainte de inchidere, ecranul
	aratat dupa il acoperea (vazut pe receptorul de proba, 22.11.2026)."""
	try:
		t = eTimer()
		t.callback.append(lambda: _arataIesirea(session))
		t.start(dupa_ms, True)
		_ceasIesire[0] = t
	except Exception as e:
		_jurnal("anuntul iesirii (ceas): %r" % (e,))
		_arataIesirea(session)


def _arataIesirea(session):
	try:
		from Screens import HdsAnuntRetea as AR
		# fereastra anunturilor (aceeasi ca AR.arata), dar fara ascunderea la tasta: ridicarea lui EXIT ar ascunde-o
		# indata (vazut pe receptorul de proba, 22.11.2026)
		if AR._fereastra[0] is None:
			AR._fereastra[0] = session.instantiateDialog(AR.HdsAnuntRetea)
		AR._fereastra[0].anunta(textIesire(), "info", durata_ms=ANUNT_IESIRE_MS, ascunde_la_tasta=False)
	except Exception as e:
		_jurnal("anuntul iesirii: %r" % (e,))


def intreabaMotivul(session, dupa):
	"""Dupa Rosu + Da: "De ce oprești?", o singura intrebare, optionala. dupa(cod) primeste codul (MOTIVE_OM) sau "" la
	EXIT, la timp sau cand fereastra nu se poate deschide; oprirea se face oricum (nu e o a doua confirmare)."""
	coduri = [c for c, _e in MOTIVE_OM]
	try:
		from Screens.MessageBox import MessageBox
		lista = [(trInceput(e), c) for c, e in MOTIVE_OM[:3]] + [(trInceput(INCEPUT_ALTCEVA[1]), MOTIVE_OM[3][0])]
		session.openWithCallback(lambda rez=None: dupa(rez if rez in coduri else ""), MessageBox,
			trInceput(TEXT_DE_CE_OPRESTI), MessageBox.TYPE_YESNO, timeout=MOTIV_S, timeout_default="", list=lista,
			default=0)
	except Exception as e:
		_jurnal("intrebarea motivului: %r" % (e,))
		dupa("")


def motivOprire(cod):
	"""Motivul pentru server si jurnal: "de om (ecran)" sau "de om (ecran): terminat"."""
	return "de om (ecran): %s" % cod if cod else "de om (ecran)"
