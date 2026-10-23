# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# ecrane.py: ecranele navigatorului web pe televizor.
#
# HdsNavigatorEcran: fereastra pe tot ecranul care tine navigatorul deschis. Pana la prima pagina arata progresul (se
# cauta interfata camului, se porneste navigatorul, se incarca pagina, cu bara); apoi navigatorul (alt proces) are
# ecranul si telecomanda (lansator.py). Ferestrele cerute de pagina sau de telecomanda le deschide tot ea, peste
# navigatorul ascuns: tastatura (VirtualKeyBoard, cu puncte in loc de litere la parole), bara de adresa,
# utilizatorul si parola, alert/confirm/prompt, lista unui <select>, meniul navigatorului, favoritele, setarile. Dupa
# fiecare, navigatorul primeste iar ecranul (Navigator.reia).
#
# Doua moduri: MOD_CAM (butonul din ecranul camului: numai adresa interfetei web a camului, gasita la rulare de
# Components/HdsInterfeteCam.py, nimic pe disc) si MOD_OBISNUIT (meniul „Navigator web”: orice adresa, pagina de
# pornire, favorite, profil).
#
# Modul cam (0.2.8): butonul Albastru din „Module de acces condiționat” (Screens/CamSetup.py) si
# „Deschide pe televizor” din paginile web /acces-conditionat si /navigator. Cand pagina camului cere utilizator si
# parola, prima data raspunde ecranul, cu datele citite pe receptor (intrare_cam.py), fara nicio fereastra; daca nu se
# gasesc sau nu merg, le scrie omul in tastatura. Fara cam pornit sau fara pagina web: numai mesajul (fara codul QR).
#
# Navigatorul (pachetul hds-navigator) vine cu imaginea. Daca totusi lipseste (de exemplu in emulator) sau nu se poate
# folosi: un mesaj, iar in modul cam rezerva, un cod QR spre pagina „Interfețe CAM” din interfata web
# (HdsNavigatorRezerva). Nu se instaleaza nimic de aici: imaginea nu are feed online.
#
# Skinurile: blocurile HdsNavigator* din skinul ales, altfel skinurile de mai jos, facute la deschidere dupa marimea
# ecranului (1920x1080 sau 1280x720), numai cu fontul „Regular” si culori scrise direct.

import os

from enigma import eTimer, getDesktop, eSize

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.HdsCampText import CampText
from Components.MenuList import MenuList
from Components.Sources.StaticText import StaticText
from Components.Sources.CanvasSource import CanvasSource
from Components.ConfigList import ConfigListScreen
from Components.config import getConfigListEntry, ConfigNothing

from . import lansator as L
from . import setari as S

TERMEN_CAUTARE_S = 10      # cautarea interfetei camului (HdsInterfeteCam: cel mult 8 s)
PAS_CAUTARE_MS = 250
# modul cam: motivele pentru care nu se arata codul QR spre /interfete-cam (nu ruleaza niciun cam, camul n-are pagina
# web): acolo n-ar fi nimic de deschis, deci ramane numai mesajul, pe ecranul de progres (OK sau EXIT il inchid)
MOTIVE_FARA_REZERVA = ("fara-cam", "fara-web")


def _scara(latime, inaltime):
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))
	return x, y


def skinEcran(latime, inaltime):
	"""Fereastra pe tot ecranul, cu cardul progresului in mijloc."""
	x, y = _scara(latime, inaltime)
	cl, ch = x(1200), y(470)
	cx, cy = (latime - cl) // 2, (inaltime - ch) // 2
	return """
	<screen name="HdsNavigatorEcran" position="0,0" size="%(l)d,%(i)d" flags="wfNoBorder" backgroundColor="#00101828" title="Navigator web">
		<eLabel position="%(cx)d,%(cy)d" size="%(cl)d,%(ch)d" backgroundColor="#001c2638" zPosition="1" />
		<eLabel position="%(cx)d,%(cy)d" size="%(cl)d,%(linie)d" backgroundColor="#00f5b83d" zPosition="2" />
		<widget source="titlu" render="Label" position="%(tx)d,%(ty)d" size="%(tl)d,%(th)d" font="Regular;%(tf)d" halign="center" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#001c2638" transparent="1" zPosition="3" />
		<widget source="pas" render="Label" position="%(tx)d,%(py)d" size="%(tl)d,%(ph)d" font="Regular;%(pf)d" halign="center" valign="center" foregroundColor="#00e1e7f0" backgroundColor="#001c2638" transparent="1" zPosition="3" />
		<eLabel name="pista" position="%(bx)d,%(by)d" size="%(bl)d,%(bh)d" backgroundColor="#002a3350" zPosition="3" />
		<widget name="umplere" position="%(bx)d,%(by)d" size="%(bl)d,%(bh)d" backgroundColor="#00f5b83d" zPosition="4" />
		<widget source="nota" render="Label" position="%(tx)d,%(ny)d" size="%(tl)d,%(nh)d" font="Regular;%(nf)d" halign="center" valign="top" foregroundColor="#00f5b83d" backgroundColor="#001c2638" transparent="1" zPosition="3" />
		<widget source="jos" render="Label" position="%(tx)d,%(jy)d" size="%(tl)d,%(jh)d" font="Regular;%(jf)d" halign="center" valign="center" foregroundColor="#00a8b3c7" backgroundColor="#001c2638" transparent="1" zPosition="3" />
	</screen>""" % {
		"l": latime, "i": inaltime, "cx": cx, "cy": cy, "cl": cl, "ch": ch, "linie": max(2, y(4)),
		"tx": cx + x(40), "tl": cl - 2 * x(40),
		"ty": cy + y(36), "th": y(64), "tf": y(46),
		"py": cy + y(120), "ph": y(56), "pf": y(34),
		"bx": cx + x(100), "by": cy + y(200), "bl": cl - 2 * x(100), "bh": max(4, y(16)),
		"ny": cy + y(244), "nh": y(130), "nf": y(30),
		"jy": cy + ch - y(70), "jh": y(46), "jf": y(26),
	}


def skinRezerva(latime, inaltime):
	"""Codul QR spre pagina „Interfețe CAM”, cu motivul si adresa."""
	x, y = _scara(latime, inaltime)
	pl, ph = x(1500), y(760)
	q = y(520)
	return """
	<screen name="HdsNavigatorRezerva" position="center,center" size="%(pl)d,%(ph)d" flags="wfNoBorder" backgroundColor="#00101828" title="Interfața camului">
		<eLabel position="0,0" size="%(pl)d,%(linie)d" backgroundColor="#00f5b83d" zPosition="1" />
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(cl)d,%(th)d" font="Regular;%(tf)d" halign="left" valign="center" foregroundColor="#00f2f4f8" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="qr" render="Canvas" position="%(mx)d,%(qy)d" size="%(q)d,%(q)d" zPosition="2" />
		<widget source="motiv" render="Label" position="%(rx)d,%(qy)d" size="%(rl)d,%(mh)d" font="Regular;%(mf)d" halign="left" valign="top" foregroundColor="#00f5b83d" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="pasi" render="Label" position="%(rx)d,%(py)d" size="%(rl)d,%(pph)d" font="Regular;%(pf)d" halign="left" valign="top" foregroundColor="#00e1e7f0" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="adresa" render="Label" position="%(rx)d,%(ay)d" size="%(rl)d,%(ah)d" font="Regular;%(af)d" halign="left" valign="center" foregroundColor="#00ffffff" backgroundColor="#00101828" transparent="1" zPosition="1" />
		<widget source="jos" render="Label" position="%(mx)d,%(jy)d" size="%(cl)d,%(jh)d" font="Regular;%(jf)d" halign="left" valign="center" foregroundColor="#00a8b3c7" backgroundColor="#00101828" transparent="1" zPosition="1" />
	</screen>""" % {
		"pl": pl, "ph": ph, "linie": max(2, y(4)), "mx": x(50), "cl": pl - 2 * x(50),
		"ty": y(30), "th": y(70), "tf": y(46),
		"q": q, "qy": y(130),
		"rx": x(50) + q + x(50), "rl": pl - q - 3 * x(50),
		"mh": y(130), "mf": y(32),
		"py": y(270), "pph": y(250), "pf": y(30),
		"ay": y(560), "ah": y(90), "af": y(34),
		"jy": ph - y(90), "jh": y(60), "jf": y(26),
	}


def skinLista(latime, inaltime, nume):
	x, y = _scara(latime, inaltime)
	pl, ph = x(1300), y(800)
	return """
	<screen name="%(nume)s" position="center,center" size="%(pl)d,%(ph)d" title="Navigator web">
		<widget name="lista" position="%(m)d,%(m)d" size="%(ll)d,%(lh)d" font="Regular;%(f)d" itemHeight="%(ih)d" scrollbarMode="showOnDemand" />
		<widget source="nota" render="Label" position="%(m)d,%(ny)d" size="%(ll)d,%(nh)d" font="Regular;%(nf)d" halign="left" valign="top" foregroundColor="#00a8b3c7" />
	</screen>""" % {
		"nume": nume, "pl": pl, "ph": ph, "m": x(30), "ll": pl - 2 * x(30), "lh": y(620), "f": y(32), "ih": y(56),
		"ny": y(670), "nh": y(110), "nf": y(26),
	}


def skinSetari(latime, inaltime):
	x, y = _scara(latime, inaltime)
	pl, ph = x(1400), y(760)
	return """
	<screen name="HdsNavigatorSetari" position="center,center" size="%(pl)d,%(ph)d" title="Setări navigator">
		<widget name="config" position="%(m)d,%(m)d" size="%(ll)d,%(lh)d" font="Regular;%(f)d" secondfont="Regular;%(sf)d" itemHeight="%(ih)d" scrollbarMode="showOnDemand" />
		<widget source="descriere" render="Label" position="%(m)d,%(dy)d" size="%(ll)d,%(dh)d" font="Regular;%(df)d" halign="left" valign="top" foregroundColor="#00e1e7f0" />
		<widget source="nota" render="Label" position="%(m)d,%(ny)d" size="%(ll)d,%(nh)d" font="Regular;%(nf)d" halign="left" valign="top" foregroundColor="#00a8b3c7" />
	</screen>""" % {
		# valorile aproape cat etichetele (cu 16 erau greu de citit); skinul HDSatelit are ecranul lui (skin.xml)
		"pl": pl, "ph": ph, "m": x(30), "ll": pl - 2 * x(30), "lh": y(400), "f": y(30), "sf": y(28), "ih": y(56),
		"dy": y(450), "dh": y(170), "df": y(28), "ny": y(640), "nh": y(100), "nf": y(26),
	}


def _desktop():
	s = getDesktop(0).size()
	return s.width(), s.height()


def instalat(mediu=None):
	return (mediu or L.Mediu()).exista(L.CALE_LANSATOR)


def adresaCam(interfata):
	"""Adresa interfetei web a camului, deschisa chiar pe receptor: gazda anume pe care asculta camul, altfel
	127.0.0.1 (si cand asculta numai pe receptor)."""
	gazda = interfata.get("gazda") or "127.0.0.1"
	schema = interfata.get("schema") or "http"
	g = "[%s]" % gazda if ":" in gazda else gazda
	return "%s://%s:%d/" % (schema, g, int(interfata.get("port") or 0)), gazda, schema


def gazdaSimpla(gazda):
	"""Gazda fara paranteze drepte (IPv6) si cu litere mici, ca sa se poata compara."""
	return (gazda or "").strip().strip("[]").lower()


def setariCurente():
	c = S.initConfig()
	s = {"marire": c.marire.value, "font_minim": c.font_minim.value, "desen": c.desen.value,
		"chenar": bool(c.chenar.value)}
	s.update(S.setariChenar(c))   # stilul chenarului
	return s


class _EtichetaAscunsa(CampText):
	"""Textul tastaturii la parole: pe ecran puncte, pentru tastatura textul adevarat. Ca la tastatura obisnuita, cand
	punctele nu mai incap se vede coada lor (Components/HdsCampText.py)."""

	def __init__(self, text=""):
		self._adevarat = text or ""
		# Label.__init__ trece prin setText de mai jos: primeste textul adevarat (punctele le face setText)
		CampText.__init__(self, self._adevarat)

	def setText(self, text):
		self._adevarat = text or ""
		CampText.setText(self, u"\u2022" * len(self._adevarat))

	def getText(self):
		return self._adevarat

	text = property(getText, setText)


class TastaturaParola(VirtualKeyBoard):
	"""Tastatura enigma2 cu literele scrise ascunse (parole)."""

	def __init__(self, session, title="", text=""):
		VirtualKeyBoard.__init__(self, session, title=title, text=text)
		self.skinName = "VirtualKeyBoard"
		self["text"] = _EtichetaAscunsa(text)


# ---------------------------------------------------------------- fereastra navigatorului

class HdsNavigatorEcran(Screen, L.Ascultator):
	"""mod: L.MOD_OBISNUIT (adresa sau pagina de pornire) sau L.MOD_CAM (cauta interfata camului; `port` o alege
	dintre mai multe)."""

	def __init__(self, session, mod=L.MOD_OBISNUIT, adresa=None, port=None):
		latime, inaltime = _desktop()
		self.skin = skinEcran(latime, inaltime)
		Screen.__init__(self, session)
		self.mod = mod
		self.adresa = adresa
		self.port = port            # modul cam: interfata cu acest port, cand camul are mai multe
		self.nav = None
		self.cautare = None
		self.pornit_cautare = 0
		self.inchis = False
		self.eroare = None
		self.gata = False
		self.interfata = None       # modul cam: interfata deschisa (portul, schema, gazda), din HdsInterfeteCam
		self._intrare_incercata = False   # modul cam: datele de pe receptor s-au dat o data (intrare_cam.py)
		titlu = _("Interfața camului") if mod == L.MOD_CAM else _("Navigator web")
		self.setTitle(titlu)
		self["titlu"] = StaticText(titlu)
		self["pas"] = StaticText("")
		self["nota"] = StaticText("")
		self["jos"] = StaticText(_("EXIT: renunță"))
		self["umplere"] = Label("")
		self["actiuni"] = ActionMap(["OkCancelActions"], {
			"ok": self.ok,
			"cancel": self.renunta,
		}, -1)
		self.ceas = eTimer()
		self.ceas.callback.append(self._verificaCautarea)
		# la prima intrare in executie, nu la asezare: la asezare ecranul nu e inca modal, iar o fereastra deschisa
		# atunci (rezerva camului cand navigatorul lipseste) ar fi refuzata de Session.open
		self.onFirstExecBegin.append(self._incepe)
		self.onClose.append(self._laInchidere)

	# ------------------------------------------------ progresul

	def _bara(self, procent):
		try:
			w = self["umplere"]
			if procent < 0:
				w.hide()
				return
			if not hasattr(self, "_latime_bara"):
				s = w.instance.size()
				self._latime_bara, self._inaltime_bara = s.width(), s.height()
			w.instance.resize(eSize(max(1, int(self._latime_bara * min(100, procent) / 100.0)), self._inaltime_bara))
			w.show()
		except Exception as e:
			print("[HdsNavigator] bara: %s" % e)

	def _pas(self, text, procent, nota=""):
		self["pas"].setText(text)
		self["nota"].setText(nota)
		self._bara(procent)

	# ------------------------------------------------ inceputul

	def _incepe(self):
		if not instalat():
			self._faraNavigator("lipsa")
			return
		self._continua()

	def _continua(self):
		if self.mod == L.MOD_CAM:
			self._cautaCam()
		else:
			c = S.initConfig()
			self._pornesteObisnuit(self.adresa or S.adresaBuna(c.pagina_pornire.value) or S.PAGINA_IMPLICITA)

	# ------------------------------------------------ interfata camului

	def _cautaCam(self):
		from Components import HdsInterfeteCam as C
		self._pas(_("Se caută interfața web a camului..."), 10)
		self.cautare = C.cautare(reincarca=True)
		self.pornit_cautare = 0
		self.ceas.start(PAS_CAUTARE_MS, False)

	def _verificaCautarea(self):
		if self.inchis or self.cautare is None:
			self.ceas.stop()
			return
		self.pornit_cautare += 1
		if not self.cautare.gata:
			if self.pornit_cautare * PAS_CAUTARE_MS > TERMEN_CAUTARE_S * 1000:
				self.ceas.stop()
				self.cautare = None
				self._faraNavigator("cautare")
			return
		self.ceas.stop()
		rezultat, self.cautare = self.cautare.rezultat or {}, None
		interfete = []
		pornite = 0
		for cam in rezultat.get("cam_uri") or []:
			if cam.get("pornit"):
				pornite += 1
			for i in cam.get("interfete") or []:
				if i.get("web"):
					interfete.append((cam.get("nume") or _("Camul"), i))
		if not interfete:
			self._faraNavigator("fara-cam" if not pornite else "fara-web")
			return
		alese = [i for _n, i in interfete if self.port and i.get("port") == self.port]
		if len(interfete) == 1 or alese:
			self._pornesteCam(alese[0] if alese else interfete[0][1])
			return
		lista = [("%s (%s %d)" % (nume, _("portul"), i["port"]), i) for nume, i in interfete]
		self.session.openWithCallback(self._alesInterfata, ChoiceBox, title=_("Alege interfața"), list=lista)

	def _alesInterfata(self, ales):
		if self.inchis:
			return
		if not ales:
			self.close()
			return
		self._pornesteCam(ales[1])

	def _pornesteCam(self, interfata):
		adresa, gazda, schema = adresaCam(interfata)
		self.interfata = interfata
		self.nav = L.Navigator(self, L.MOD_CAM, adresa, setari=setariCurente(),
			cam={"gazda": gazda, "port": interfata.get("port"), "schema": schema})
		self.nav.porneste()

	# ------------------------------------------------ navigatorul obisnuit

	def _pornesteObisnuit(self, adresa):
		try:
			if not os.path.isdir(S.DOSAR_DATE):
				os.makedirs(S.DOSAR_DATE, 0o700)
		except OSError as e:
			print("[HdsNavigator] dosarul profilului: %s" % e)
		self.nav = L.Navigator(self, L.MOD_OBISNUIT, adresa, setari=setariCurente(),
			dosar_date=S.DOSAR_DATE, dosar_cache=S.DOSAR_CACHE)
		self.nav.porneste()

	# ------------------------------------------------ Ascultator

	def laPas(self, pas, procent):
		if self.inchis:
			return
		if pas == "pornire":
			self._pas(_("Se pornește navigatorul..."), 30, _("Prima pornire poate dura aproximativ 10 secunde."))
		elif procent >= 0:
			self._pas(_("Se încarcă pagina... %d %%") % procent, 50 + procent // 2)
		else:
			self._pas(_("Se încarcă pagina..."), 50)

	def laAratat(self):
		if self.inchis:
			return
		self.gata = True
		self._pas(_("Navigatorul este pe ecran."), -1, _("MENU sau EXIT pe prima pagină: meniul navigatorului."))
		self["jos"].setText("")

	def laEcranInapoi(self):
		# dupa fbClass.unlock() enigma2 isi redeseneaza tot ecranul: fereastra aceasta il acopera pe tot
		if self.inchis or self.instance is None:
			return
		self.hide()
		self.show()

	def laCerere(self, fel, date):
		if self.inchis or self.nav is None:
			return
		try:
			functie = getattr(self, "_cerere_" + fel.replace("-", "_"), None)
			if functie is None:
				self.nav.reia()
				return
			functie(date)
		except Exception as e:
			print("[HdsNavigator] fereastra %s: %s" % (fel, e.__class__.__name__))
			self.nav.reia()

	def laFavorit(self, adresa, titlu):
		if self.inchis or self.nav is None:
			return
		ok, mesaj = S.adaugaFavorit(adresa, titlu)
		self.session.openWithCallback(lambda *a: self.nav and self.nav.reia(), MessageBox, mesaj,
			MessageBox.TYPE_INFO if ok else MessageBox.TYPE_ERROR, timeout=4)

	def laOprit(self, motiv):
		if self.inchis:
			return
		self.nav = None
		if motiv is None:
			self.close()
			return
		self._faraNavigator(motiv)

	# ------------------------------------------------ ferestrele peste navigator

	def _cerere_tastatura(self, date):
		fel = date.get("fel")
		titluri = {
			"parola": _("Scrie parola"),
			"numar": _("Scrie numărul"),
		}
		titlu = titluri.get(fel, _("Scrie textul"))
		clasa = TastaturaParola if fel == "parola" else VirtualKeyBoard
		self.session.openWithCallback(self._dupaTastatura, clasa, title=titlu, text=date.get("valoare") or "")

	def _dupaTastatura(self, text=None):
		if self.nav is None:
			return
		if isinstance(text, str):
			self.nav.valoareCamp(text)
		self.nav.reia()

	def _cerere_adresa(self, date):
		if self.mod == L.MOD_CAM:
			self.nav.reia()
			return
		# un cuvant fara punct merge la cautarea Google (setari.adresaBuna)
		self.session.openWithCallback(self._dupaAdresa, VirtualKeyBoard, title=_("Adresa paginii sau cuvintele de căutat cu Google"),
			text=date.get("adresa") or "")

	def _dupaAdresa(self, text=None):
		if self.nav is None:
			return
		if isinstance(text, str) and text:
			a = S.adresaBuna(text)
			if a:
				self.nav.url(a)
		self.nav.reia()

	def _intraSingur(self, gazda, din_nou):
		"""Modul cam (etapa 2): la prima cerere de utilizator si parola venita de la gazda
		interfetei, datele citite pe receptor (intrare_cam.py) se dau navigatorului fara nicio fereastra. A doua cerere
		(datele n-au mers), alta gazda sau datele negasite: tastatura, ca inainte. True daca s-a raspuns aici."""
		if self.mod != L.MOD_CAM or din_nou or self._intrare_incercata or not self.interfata:
			return False
		self._intrare_incercata = True
		_adresa, gazda_cam, _schema = adresaCam(self.interfata)
		if gazdaSimpla(gazda) != gazdaSimpla(gazda_cam):
			print("[HdsNavigator] intrarea in interfata camului: cererea vine de la alta gazda; se cere in tastatura")
			return False
		from . import intrare_cam
		date = intrare_cam.date_intrare(self.interfata.get("port"))
		if date is None:
			return False
		self.nav.autentificare(date[0], date[1])
		date = None
		self.nav.continuaIncarcarea()
		return True

	def _cerere_autentificare(self, date):
		gazda = date.get("gazda") or ""
		if self._intraSingur(gazda, date.get("din_nou")):
			return
		if date.get("din_nou"):
			titlu = _("Utilizatorul sau parola nu au mers. Utilizatorul pentru %s:") % gazda
		else:
			titlu = _("Pagina cere utilizator și parolă. Utilizatorul pentru %s:") % gazda
		self.session.openWithCallback(self._dupaUtilizator, VirtualKeyBoard, title=titlu, text="")

	def _dupaUtilizator(self, utilizator=None):
		if self.nav is None:
			return
		if not isinstance(utilizator, str):
			self.nav.autentificare(None, None)
			self.nav.reia()
			return
		self._utilizator = utilizator
		self.session.openWithCallback(self._dupaParola, TastaturaParola, title=_("Parola"), text="")

	def _dupaParola(self, parola=None):
		if self.nav is None:
			return
		utilizator, self._utilizator = getattr(self, "_utilizator", None), None
		if not isinstance(parola, str):
			self.nav.autentificare(None, None)
		else:
			self.nav.autentificare(utilizator or "", parola)
		self.nav.reia()

	def _cerere_dialog(self, date):
		fel = date.get("fel")
		mesaj = (date.get("mesaj") or "")[:600]
		if fel == "intrebare":
			self.session.openWithCallback(self._dupaIntrebare, VirtualKeyBoard, title=mesaj or _("Scrie răspunsul"),
				text=date.get("implicit") or "")
		elif fel == "confirmare":
			self.session.openWithCallback(self._dupaConfirmare, MessageBox, mesaj or _("Continui?"), MessageBox.TYPE_YESNO)
		elif fel == "parasire":
			self.session.openWithCallback(self._dupaConfirmare, MessageBox,
				_("Părăsești pagina? Ce ai scris în ea se poate pierde."), MessageBox.TYPE_YESNO)
		else:
			self.session.openWithCallback(lambda *a: self._dupaConfirmare(True), MessageBox, mesaj or " ",
				MessageBox.TYPE_INFO)

	def _dupaConfirmare(self, da=False):
		if self.nav is None:
			return
		self.nav.dialog(bool(da))
		self.nav.reia()

	def _dupaIntrebare(self, text=None):
		if self.nav is None:
			return
		self.nav.dialog(isinstance(text, str), text if isinstance(text, str) else None)
		self.nav.reia()

	def _cerere_alegere(self, date):
		lista = []
		ales = 0
		for i, (text, activ_, grup) in enumerate(date.get("optiuni") or []):
			if grup or not activ_:
				continue
			if i == date.get("ales"):
				ales = len(lista)
			lista.append((text or " ", i))
		if not lista:
			self.nav.alegere(-1)
			self.nav.reia()
			return
		self.session.openWithCallback(self._dupaAlegere, ChoiceBox, title=_("Alege"), list=lista, selection=ales)

	def _dupaAlegere(self, ales=None):
		if self.nav is None:
			return
		self.nav.alegere(ales[1] if ales else -1)
		self.nav.reia()

	def _meniu(self, intrebare):
		lista = [(_("Înapoi la pagină"), "pagina")]
		if self.mod == L.MOD_OBISNUIT:
			lista += [(_("Adresă nouă sau căutare Google"), "adresa"), (_("Favorite"), "favorite"),
				(_("Adaugă pagina la favorite"), "adauga"), (_("Pagina de pornire"), "acasa")]
		lista += [
			(_("Pagina de dinainte (înapoi)"), "inapoi"),
			(_("Pagina următoare (înainte)"), "inainte"),
			(_("Reîncarcă pagina"), "reincarca"),
			(_("Trimite formularul (Enter)"), "enter"),
			(_("Scrie în pagină (TEXT)"), "scrie"),
			(_("Indicatorul (ALBASTRU)"), "indicator"),
			(_("Mărește pagina"), "mareste"),
			(_("Micșorează pagina"), "micsoreaza"),
			(_("Mărirea obișnuită"), "marire0"),
			(_("Setări navigator"), "setari"),
			(_("Închide navigatorul"), "inchide"),
		]
		selectie = len(lista) - 1 if intrebare else 0
		titlu = _("Închizi navigatorul?") if intrebare else _("Navigator web")
		self.session.openWithCallback(self._dupaMeniu, ChoiceBox, title=titlu, list=lista, selection=selectie)

	def _cerere_meniu(self, date):
		self._meniu(False)

	def _cerere_iesire(self, date):
		self._meniu(True)

	def _cerere_inchide(self, date):
		self.nav.opreste()

	def _cerere_favorite(self, date):
		if self.mod == L.MOD_CAM:
			self.nav.reia()
			return
		self.session.openWithCallback(self._dupaFavorite, HdsNavigatorFavorite)

	def _dupaFavorite(self, adresa=None):
		if self.nav is None:
			return
		if isinstance(adresa, str) and adresa:
			self.nav.url(adresa)
		self.nav.reia()

	def _dupaMeniu(self, ales=None):
		nav = self.nav
		if nav is None:
			return
		cheie = ales[1] if ales else "pagina"
		if cheie == "inchide":
			nav.opreste()
			return
		if cheie == "adresa":
			nav.ceresAdresa()  # raspunsul vine ca cerere „adresa”, cu adresa de acum in tastatura
			return
		if cheie == "favorite":
			self.session.openWithCallback(self._dupaFavorite, HdsNavigatorFavorite)
			return
		if cheie == "adauga":
			nav.ceresFavorit()  # raspunsul vine in laFavorit, care reia navigatorul
			return
		if cheie == "setari":
			self.session.openWithCallback(self._dupaSetari, HdsNavigatorSetari)
			return
		if cheie == "acasa":
			nav.url(S.adresaBuna(S.initConfig().pagina_pornire.value) or S.PAGINA_IMPLICITA)
		elif cheie == "inapoi":
			nav.inapoi()
		elif cheie == "inainte":
			nav.inainte()
		elif cheie == "reincarca":
			nav.reincarca()
		elif cheie == "enter":
			nav.enter()
		elif cheie == "scrie":
			nav.scrie()
		elif cheie == "indicator":
			nav.indicator()
		elif cheie == "mareste":
			nav.marirePas(1)
		elif cheie == "micsoreaza":
			nav.marirePas(-1)
		elif cheie == "marire0":
			nav.marirePas(0)
		nav.reia()

	def _dupaSetari(self, salvat=False):
		"""Dupa Setari navigator deschise din meniul navigatorului: chenarul si stilul lui se vad pe loc (celelalte setari
		se folosesc la urmatoarea pornire), apoi navigatorul primeste iar ecranul."""
		if self.nav is None:
			return
		if salvat:
			self.nav.schimbaChenar(S.setariChenar(S.initConfig()))
		self.nav.reia()

	# ------------------------------------------------ fara navigator

	def _faraNavigator(self, motiv):
		"""Navigatorul nu se poate folosi: in modul cam rezerva cu codul QR, altfel un mesaj. Cand nu ruleaza niciun
		cam sau camul nu are interfata web, numai mesajul: pe telefon n-ar fi nimic de deschis."""
		texte = {
			"lipsa": _("Navigatorul lipsește din această imagine."),
			"cautare": _("Căutarea interfeței camului nu s-a terminat la timp."),
			"fara-cam": _("Niciun cam nu rulează acum."),
			"fara-web": _("Camul nu are interfață web."),
		}
		text = texte.get(motiv) or L.textEroare(motiv, _)
		print("[HdsNavigator] fara navigator: %s" % motiv)
		self.eroare = text
		if self.mod == L.MOD_CAM and motiv not in MOTIVE_FARA_REZERVA:
			local = bool(getattr(self, "interfata", None) and self.interfata.get("doar_local"))
			self.session.openWithCallback(lambda *a: self.close(), HdsNavigatorRezerva, text, local)
			return
		self._pas(text, -1)
		self["jos"].setText(_("OK sau EXIT: închide"))

	# ------------------------------------------------ taste si inchidere

	def ok(self):
		if self.eroare is not None:
			self.close()

	def renunta(self):
		if self.nav is not None and self.nav.stare != L.OPRIT:
			self._pas(_("Se închide navigatorul..."), -1)
			self.nav.opreste()
			return
		self.close()

	def _laInchidere(self):
		self.inchis = True
		self.ceas.stop()
		self.cautare = None
		if self.nav is not None and self.nav.stare != L.OPRIT:
			self.nav.opreste()


# ---------------------------------------------------------------- rezerva: codul QR spre interfata web

def adresaPaginiiCam():
	"""http://<receptor>:<port>/interfete-cam, sau None fara retea."""
	try:
		from Plugins.Extensions.HdsWebControl.plugin import adresaWeb
		baza = adresaWeb()
	except Exception as e:
		print("[HdsNavigator] adresa interfetei web: %s" % e)
		baza = None
	return baza + "/interfete-cam" if baza else None


class HdsNavigatorRezerva(Screen):
	"""Motivul, codul QR si adresa paginii „Interfețe CAM” (butonul „Deschide” de acolo deschide interfata camului
	pe telefon). Codul nu contine nicio parola si niciun jeton: telefonul trece prin asocierea obisnuita."""

	def __init__(self, session, motiv, doar_local=False):
		latime, inaltime = _desktop()
		self.skin = skinRezerva(latime, inaltime)
		Screen.__init__(self, session)
		self.setTitle(_("Interfața camului"))
		self.adresa = adresaPaginiiCam()
		self["titlu"] = StaticText(_("Interfața camului pe telefon"))
		self["motiv"] = StaticText(motiv)
		if doar_local:
			pasi = _("Interfața web a camului ascultă doar pe receptor, deci se deschide numai pe televizor.")
		elif self.adresa:
			pasi = _("Scanează codul cu telefonul (în aceeași rețea cu receptorul). Se deschide pagina „Interfețe CAM”; acolo apasă „Deschide”.")
		else:
			pasi = _("Receptorul nu are legătură în rețea, deci pagina nu se poate deschide nici pe telefon.")
		self["pasi"] = StaticText(pasi)
		self["adresa"] = StaticText(self.adresa or "")
		self["jos"] = StaticText(_("OK sau EXIT: închide"))
		self["qr"] = CanvasSource()
		self["actiuni"] = ActionMap(["OkCancelActions"], {"ok": self.close, "cancel": self.close}, -1)
		self.onLayoutFinish.append(self._deseneaza)

	def _deseneaza(self):
		c = self["qr"]
		try:
			latime = inaltime = 0
			for r in getattr(self, "renderer", []) or []:
				if getattr(r, "source", None) is c and r.instance is not None:
					latime, inaltime = r.instance.size().width(), r.instance.size().height()
			if not latime:
				return
			if self.adresa:
				from .qr import deseneaza
				deseneaza(c, self.adresa, latime, inaltime)
			else:
				c.clear()
				c.fill(0, 0, latime, inaltime, 0x00101828)
			c.flush()
		except Exception as e:
			print("[HdsNavigator] codul QR: %s" % e)


# ---------------------------------------------------------------- favorite

class HdsNavigatorFavorite(Screen):
	"""Lista paginilor favorite. OK: Deschide sau Șterge din favorite. Intoarce adresa aleasa sau None."""

	def __init__(self, session):
		latime, inaltime = _desktop()
		self.skin = skinLista(latime, inaltime, "HdsNavigatorFavorite")
		Screen.__init__(self, session)
		self.setTitle(_("Favorite"))
		self["lista"] = MenuList([])
		self["nota"] = StaticText("")
		self["actiuni"] = ActionMap(["OkCancelActions"], {"ok": self.ok, "cancel": lambda: self.close(None)}, -1)
		self.onLayoutFinish.append(self.umple)

	def umple(self):
		self.favorite = S.citesteFavorite()
		self["lista"].setList([(x["titlu"] or x["adresa"], i) for i, x in enumerate(self.favorite)])
		if self.favorite:
			self["nota"].setText(_("OK pe o pagină: deschide-o sau scoate-o din favorite."))
		else:
			self["nota"].setText(_("Nu ai pagini favorite. În navigator: MENU, apoi „Adaugă pagina la favorite”."))

	def ok(self):
		rand = self["lista"].getCurrent()
		if not rand:
			return
		self._index = rand[1]
		self.session.openWithCallback(self._ales, ChoiceBox, title=self.favorite[self._index]["adresa"],
			list=[(_("Deschide"), "deschide"), (_("Scoate din favorite"), "sterge")])

	def _ales(self, ales=None):
		if not ales:
			return
		if ales[1] == "deschide":
			self.close(self.favorite[self._index]["adresa"])
			return
		S.stergeFavorit(self._index)
		self.umple()


# ---------------------------------------------------------------- setari

class HdsNavigatorSetari(Screen, ConfigListScreen):
	"""Pagina de pornire, marirea, literele, desenul, chenarul si stilul lui (culoarea, forma, grosimea, pulsul, viteza:
	randuri care apar numai cu chenarul pornit, viteza numai cu pulsul pornit); randurile 'Favorite' si 'Șterge datele
	de navigare' se deschid cu OK. OK pe o setare salveaza si inchide (cu True); EXIT renunta."""

	def __init__(self, session):
		latime, inaltime = _desktop()
		self.skin = skinSetari(latime, inaltime)
		Screen.__init__(self, session)
		self.setTitle(_("Setări navigator"))
		self.c = S.initConfig()
		self["descriere"] = StaticText("")
		self["nota"] = StaticText(_("OK: salvează. EXIT: renunță."))
		self._favorite = ConfigNothing()
		self._sterge = ConfigNothing()
		self._sterge_hbbtv = ConfigNothing()
		ConfigListScreen.__init__(self, self._randuri(), session=session)
		self["actiuni"] = ActionMap(["SetupActions"], {
			"ok": self.ok,
			"save": self.salveaza,
			"cancel": self.keyCancel,
		}, -2)
		self["config"].onSelectionChanged.append(self._descriere)
		self.onLayoutFinish.append(self._descriere)
		# randurile stilului apar si dispar dupa chenar si dupa puls, cele HbbTV dupa setarea principala HbbTV
		for e in (self.c.chenar, self.c.chenar_puls, self.c.hbbtv):
			e.addNotifier(self._randuriSchimbate, initial_call=False)
		self.onClose.append(self._faraNotificari)

	def _randuri(self):
		n = len(S.citesteFavorite())
		return [
			getConfigListEntry(_(S.ETICHETE["pagina_pornire"]), self.c.pagina_pornire, "pagina_pornire"),
			getConfigListEntry(_(S.ETICHETE["marire"]), self.c.marire, "marire"),
			getConfigListEntry(_(S.ETICHETE["font_minim"]), self.c.font_minim, "font_minim"),
			getConfigListEntry(_(S.ETICHETE["desen"]), self.c.desen, "desen"),
			getConfigListEntry(_(S.ETICHETE["chenar"]), self.c.chenar, "chenar"),
		] + [
			getConfigListEntry(_(S.ETICHETE[k]), getattr(self.c, k), k) for k in S.randuriChenar(self.c)
		] + [
			getConfigListEntry(_(S.ETICHETE["hbbtv"]), self.c.hbbtv, "hbbtv"),
		] + [
			getConfigListEntry(_(S.ETICHETE[k]), getattr(self.c, k), k) for k in S.randuriHbbtv(self.c)
		] + [
			getConfigListEntry(_(S.ETICHETE["sterge_hbbtv"]), self._sterge_hbbtv, "sterge_hbbtv"),
			getConfigListEntry(_("Favorite (%d)") % n, self._favorite, "favorite"),
			getConfigListEntry(_("Șterge datele de navigare"), self._sterge, "sterge"),
		]

	def _randuriSchimbate(self, element=None):
		"""Chenarul sau pulsul pornit / oprit: lista din nou, cu cursorul pe aceeasi setare."""
		curent = self["config"].getCurrent()
		lista = self._randuri()
		self["config"].setList(lista)
		if curent is not None and len(curent) > 1:
			for i, rand in enumerate(lista):
				if rand[1] is curent[1]:
					self["config"].setCurrentIndex(i)
					break
		self._descriere()

	def _faraNotificari(self):
		for e in (self.c.chenar, self.c.chenar_puls, self.c.hbbtv):
			if self._randuriSchimbate in e.notifiers:
				e.notifiers.remove(self._randuriSchimbate)

	def _stil(self):
		"""Setarile stilului chenarului (salvate sau renuntate impreuna cu celelalte)."""
		return tuple(getattr(self.c, k) for k in S.CHEI_STIL)

	def _cheie(self):
		r = self["config"].getCurrent()
		return r[2] if r and len(r) > 2 else None

	def _descriere(self):
		cheie = self._cheie()
		texte = {
			"favorite": _("OK: lista paginilor favorite."),
			"sterge": _("OK: șterge istoricul, cookie-urile, datele site-urilor și mărirea ținută minte."),
		}
		if cheie in S.DESCRIERI:
			self["descriere"].setText(_(S.DESCRIERI[cheie]))
		else:
			self["descriere"].setText(texte.get(cheie, ""))

	def ok(self):
		cheie = self._cheie()
		if cheie == "pagina_pornire":
			self.session.openWithCallback(self._dupaPagina, VirtualKeyBoard, title=_(S.ETICHETE["pagina_pornire"]),
				text=self.c.pagina_pornire.value)
		elif cheie == "favorite":
			self.session.openWithCallback(self._dupaFavorite, HdsNavigatorFavorite)
		elif cheie == "sterge":
			self.session.openWithCallback(self._stergeDatele, MessageBox,
				_("Ștergi datele de navigare? Se șterg cookie-urile, datele site-urilor și mărirea ținută minte. Favoritele rămân."),
				MessageBox.TYPE_YESNO)
		elif cheie == "sterge_hbbtv":
			self.session.openWithCallback(self._stergeHbbtv, MessageBox,
				_("Ștergi datele aplicațiilor HbbTV? Se șterg cookie-urile și datele salvate de aplicațiile canalelor."),
				MessageBox.TYPE_YESNO)
		else:
			self.salveaza()

	def _dupaPagina(self, text=None):
		if text is None:
			return
		a = S.adresaBuna(text)
		if not a:
			self.session.open(MessageBox, _("Adresa nu se poate deschide."), MessageBox.TYPE_ERROR, timeout=4)
			return
		self.c.pagina_pornire.value = a
		self["config"].invalidateCurrent()

	def _dupaFavorite(self, adresa=None):
		self["config"].setList(self._randuri())

	def _stergeDatele(self, da=False):
		if not da:
			return
		if L.cedeaza() is not None:   # o aplicatie HbbTV pornita automat si nevazuta lasa locul
			self.session.open(MessageBox, _("Închide întâi navigatorul, apoi șterge datele."), MessageBox.TYPE_INFO, timeout=5)
			return
		octeti = S.stergeDatele()
		print("[HdsNavigator] datele de navigare sterse (%d octeti)" % octeti)
		self.session.open(MessageBox, _("Datele de navigare au fost șterse."), MessageBox.TYPE_INFO, timeout=4)

	def _stergeHbbtv(self, da=False):
		if not da:
			return
		nav = L.cedeaza()   # o aplicatie HbbTV pornita automat si nevazuta se opreste pe loc
		if nav is not None:
			text = _("Închide întâi aplicația HbbTV, apoi șterge datele.") if nav.mod == L.MOD_HBBTV else \
				_("Închide întâi navigatorul, apoi șterge datele.")
			self.session.open(MessageBox, text, MessageBox.TYPE_INFO, timeout=5)
			return
		octeti = S.stergeDateleHbbtv()
		print("[HdsNavigator] datele HbbTV sterse (%d octeti)" % octeti)
		self.session.open(MessageBox, _("Datele HbbTV au fost șterse."), MessageBox.TYPE_INFO, timeout=4)

	def salveaza(self):
		for x in (self.c.pagina_pornire, self.c.chenar, self.c.marire, self.c.font_minim, self.c.desen, self.c.hbbtv_semn,
				self.c.hbbtv_autostart, self.c.hbbtv, self.c.hbbtv_clar):
			x.save()
		for x in self._stil():
			x.save()
		from Components.config import configfile
		configfile.save()
		try:
			# HbbTV si pornirea automata se aplica pe loc (Components/HdsHbbtvPornire.setari_salvate)
			from Components import HdsHbbtvPornire
			HdsHbbtvPornire.setari_salvate()
		except Exception as e:
			print("[HdsNavigator] setarile HbbTV: %s" % e)
		self.close(True)

	def keyCancel(self):
		self._faraNotificari()   # renuntarea pune valorile vechi: lista nu se mai face din nou
		for x in (self.c.pagina_pornire, self.c.chenar, self.c.marire, self.c.font_minim, self.c.desen, self.c.hbbtv_semn,
				self.c.hbbtv_autostart, self.c.hbbtv, self.c.hbbtv_clar):
			x.cancel()
		for x in self._stil():
			x.cancel()
		self.close(False)
