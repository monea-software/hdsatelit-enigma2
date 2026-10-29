# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Ajutorul pe televizor, fara internet (din 0.6.8). Datele si cautarea sunt in Components/HdsAjutor.py; aceleasi
pagini sunt in interfata web la /ajutor.

Trei ecrane:
  HdsAjutorCuprins  „Ajutor” din meniul principal: cele 13 capitole; OK deschide capitolul, VERDE cauta.
  HdsAjutorLista    paginile unui capitol sau rezultatele cautarii; OK deschide pagina.
  HdsAjutorPagina   o pagina: partile ei (la ce foloseste, cum ajungi, ce vezi, randurile si setarile, tastele, pas
                    cu pas, probleme si solutii, subiecte conexe), fara poze. Sus/Jos trec din bloc in bloc (un
                    paragraf, un rand de setari, o tasta, o problema), Stanga/Dreapta schimba pagina ecranului; OK pe
                    un bloc legat deschide pagina legata. VERDE cuprinsul, GALBEN cautarea, ALBASTRU lista tastelor
                    ecranului de dedesubt (ce arata inainte tasta HELP), cand ecranul are una.
Tasta HELP pe orice ecran (Components/HdsAjutor.porneste) cheama deschideDinEcran: pagina ecranului, sau cuprinsul
cand ecranul nu are pagina. ROSU inchide tot ajutorul (inapoi la ecranul sau la meniul din care s-a deschis), EXIT
numai ecranul de acum.

Textele din jur (titluri, butoane, numele partilor) vin din datele ajutorului, in limba interfetei (13 limbi); paginile
sunt in romana sau in engleza (celelalte limbi le vad in engleza, cu o insemnare).

Ca la „Ce e nou” (Screens/HdsJurnalVersiuni.py): lista are o singura inaltime de rand, deci textul se rupe aici pe
cuvinte, dupa latimea masurata a literelor (eticheta ascunsa „masura”), iar paginile listei sunt fixe: un bloc care
incape pe o pagina nu se rupe intre doua pagini. Latimile literelor se tin minte pe font, pentru paginile urmatoare.
Fiecare ecran are si un skin scris aici, pentru orice skin ales; skinul HDSatelit are ecranele lui (ambele teme).
"""
from enigma import eListboxPythonMultiContent, eSize, eTimer, getDesktop, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components.Sources.StaticText import StaticText
from Components import HdsAjutor as A

# culorile din skinul HDSatelit si rezerva pentru alt skin (0xRRGGBB)
CULORI = {
	"titlu": ("hdsBrandLight", 0x9FB4FF),
	"linie": ("hdsTrack", 0x2A3350),
	"eticheta": ("hdsLabel", 0xAEB9CC),
	"text": ("hdsText", 0xF2F4F8),
	"legatura": ("hdsBrandLight", 0x9FB4FF),
	"cursor": ("hdsBrand", 0x374EA1),
	"pe_cursor": ("white", 0xFFFFFF),
}
# fonturile: (alias din skin, rolul fontului pentru rezerva, marimea la 1920 px)
FONTURI = (
	("HdsAjutorTitlu", "Bold", 30),
	("HdsAjutorText", "Regular", 28),
	("HdsAjutorEticheta", "Fixed", 26),
	("HdsAjutorBold", "Bold", 28),
)
F_TITLU, F_TEXT, F_ETICHETA, F_BOLD = 0, 1, 2, 3
FONT_LISTA = ("HdsAjutorLista", "Regular", 32)
FONT_LISTA_MIC = ("HdsAjutorListaMic", "Fixed", 26)
LATIME_SEMN = 0.5
SEMN_LEGATURA = u"›"   # „›”
ELIPSA = u"…"
# coloana din dreapta a listelor (capitolul paginii la cautare, numarul paginilor in cuprins): cel mult atat din latime
DREAPTA_MAXIM = 0.42

# skinurile scrise aici (numerele socotite din marimea ecranului), pentru orice skin care nu are ecranele
# Tastele colorate sunt StaticText: o tasta fara text nu se vede deloc, nici semnul ei de culoare din cadrul skinului
# HDSatelit (HdsCadru1776 il ascunde numai pentru StaticText gol). Aici textul are culoarea tastei, pe fond
# transparent (un Label sub ConditionalShowHide nu se creeaza in imagine, test_locul_reparatii_044), deci o tasta
# goala nu lasa nici ea nimic pe ecran.
SKIN_LISTA = """
	<screen name="HdsAjutorLista" position="%d,%d" size="%d,%d">
		<widget name="lista" position="%d,%d" size="%d,%d" itemHeight="%d" scrollbarMode="showOnDemand" transparent="1" zPosition="2" />
		<widget name="stare" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#00AEB9CC" valign="center" transparent="1" zPosition="2" />
		<widget source="key_red" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#00FF6B5E" halign="center" valign="center" transparent="1" zPosition="2" />
		<widget source="key_green" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#005DDE96" halign="center" valign="center" transparent="1" zPosition="2" />
		<widget name="masura" position="0,0" size="1,1" noWrap="1" transparent="1" zPosition="0" />
	</screen>"""
SKIN_PAGINA = """
	<screen name="HdsAjutorPagina" position="%d,%d" size="%d,%d">
		<widget name="lista" position="%d,%d" size="%d,%d" itemHeight="40" scrollbarMode="showOnDemand" transparent="1" zPosition="2" />
		<widget name="stare" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="1" zPosition="2" />
		<widget name="online" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#00AEB9CC" valign="center" noWrap="1" transparent="1" zPosition="2" />
		<widget source="key_red" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#00FF6B5E" halign="center" valign="center" transparent="1" zPosition="2" />
		<widget source="key_green" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#005DDE96" halign="center" valign="center" transparent="1" zPosition="2" />
		<widget source="key_yellow" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#00EEC209" halign="center" valign="center" transparent="1" zPosition="2" />
		<widget source="key_blue" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#009FB4FF" halign="center" valign="center" transparent="1" zPosition="2" />
		<widget name="masura" position="0,0" size="1,1" noWrap="1" transparent="1" zPosition="0" />
	</screen>"""

# ecranul deschis fara `ecran` (din meniu: <screen module="HdsAjutor" screen="HdsAjutorCuprins" />): cand ajutorul se
# inchide, nu intoarce nimic, fiindca Menu.menuClosed ia orice rezultat adevarat drept „inchide tot meniul”; ROSU
# lasa atunci omul in meniul din care a venit (altfel ROSU inchidea si meniul Informatii)
_DIN_MENIU = object()
# latimile literelor masurate, pe font: (nume, marime) -> {semn: pixeli}
_SEMNE = {}
# ce ramane de facut dupa inchiderea ajutorului (o fapta aleasa in lista tastelor): ceasul tinut in viata
_DUPA = [None, None]


def _jurnal(text):
	print("[HdsAjutor] %s" % text)


def _culoare(cheie):
	nume, implicit = CULORI[cheie]
	try:
		import skin
		c = skin.colorNames.get(nume)
		if c is not None:
			v = c.argb()
			return v & 0xFFFFFF if (v >> 24) == 0xFF else v
	except Exception:
		pass
	return implicit


def _ecran():
	try:
		d = getDesktop(0).size()
		return d.width(), d.height()
	except Exception:
		return 1920, 1080


def _factor():
	return _ecran()[0] / 1920.0


def _font(alias, rol, marime):
	"""(gFont, marimea in pixeli, cheia pentru latimile literelor): aliasul skinului, daca il are (skin.parseFont, cu
	Marimea textului aleasa de om), altfel fontul HDSatelit al rolului la marimea data, scalata dupa ecran, prin
	HdsMarireText.fontCod (aceeasi Marime a textului)"""
	try:
		import skin
		if alias in skin.fonts:
			nume, m, _h = skin.fonts[alias]
			pm = max(1, m * skin.getFontScalePercent() // 100)
			return skin.parseFont(alias, ((1, 1), (1, 1))), pm, (nume, pm)
	except Exception:
		pass
	from Components.HdsMarireText import familieCod, fontCod, marimeCod
	m = max(1, int(marime * _factor()))
	pm = marimeCod(m)
	return fontCod(rol, m), pm, (familieCod(rol), pm)


def _rupe(text, latime_text, loc):
	"""textul rupt pe cuvinte in randuri care incap in `loc` pixeli (latime_text: text -> pixeli); un cuvant mai lung
	decat un rand se taie"""
	spatiu = latime_text(" ")
	randuri = []
	rand, lat = "", 0
	for cuvant in (text or "").split():
		w = latime_text(cuvant)
		while w > loc and len(cuvant) > 1:
			if rand:
				randuri.append(rand)
				rand, lat = "", 0
			n = len(cuvant)
			while n > 1 and latime_text(cuvant[:n]) > loc:
				n -= 1
			randuri.append(cuvant[:n])
			cuvant = cuvant[n:]
			w = latime_text(cuvant)
		if not rand:
			rand, lat = cuvant, w
		elif lat + spatiu + w <= loc:
			rand, lat = "%s %s" % (rand, cuvant), lat + spatiu + w
		else:
			randuri.append(rand)
			rand, lat = cuvant, w
	if rand:
		randuri.append(rand)
	return randuri or [""]


def _scurteaza(text, latime_text, loc):
	"""textul intreg daca incape in `loc` pixeli, altfel taiat la sfarsit, cu „…” (titlurile lungi din liste)"""
	text = text or ""
	if latime_text(text) <= loc:
		return text
	n = len(text)
	while n > 0 and latime_text(text[:n].rstrip() + ELIPSA) > loc:
		n -= 1
	return text[:n].rstrip() + ELIPSA if n else ""


def _dupaAjutor(rez=None, *args):
	"""Ajutorul s-a inchis. Daca omul a ales o fapta in lista tastelor ecranului (ALBASTRU), ea se face acum, pe ecranul
	de dedesubt, dupa ce ajutorul a plecat de pe ecran (altfel un ecran deschis de fapta ar sta sub ajutor)."""
	if not (isinstance(rez, tuple) and len(rez) == 2 and rez[0] == "actiune" and rez[1]):
		return
	try:
		actionmap, context, action = rez[1]
	except (TypeError, ValueError):
		return

	def fa():
		_DUPA[0] = None
		try:
			actionmap.action(context, action)
		except Exception as e:
			_jurnal("fapta din lista tastelor: %s" % e)
	t = eTimer()
	t.callback.append(fa)
	_DUPA[0] = t
	t.start(0, True)


def deschideDinEcran(session, dialog, dedesubt=()):
	"""Tasta HELP pe ecranul `dialog`: pagina lui de ajutor sau cuprinsul (cu o insemnare)."""
	ecran = dialog if (getattr(dialog, "helpList", None) or []) else None
	i = A.pagina_ecranului(dialog, dedesubt) if A.instalat() else None
	if i is None:
		nota = A.text("fara_pagina") if A.instalat() else None
		session.openWithCallback(_dupaAjutor, HdsAjutorCuprins, nota=nota, ecran=ecran)
	else:
		session.openWithCallback(_dupaAjutor, HdsAjutorPagina, i, ecran=ecran)


class _Baza(Screen):
	"""Ce au ecranele ajutorului in comun: masurarea textului, inchiderea intregului ajutor, culorile."""

	def __init__(self, session, ecran=_DIN_MENIU):
		Screen.__init__(self, session)
		# ecranele ajutorului deschise din alt ecran al ajutorului sau de tasta HELP primesc `ecran` (si None)
		self.dinMeniu = ecran is _DIN_MENIU
		self.ecran = None if self.dinMeniu else ecran
		self.limba = A.limba_interfetei()
		self.c = dict((k, _culoare(k)) for k in CULORI)
		self["masura"] = Label("")

	def T(self, cheie):
		return A.text(cheie, self.limba)

	def _latimeText(self, text, font):
		try:
			w = self["masura"]
			w.instance.setFont(font)
			w.setText(text)
			return w.instance.calculateSize().width()
		except Exception:
			return None

	def latimeFont(self, font, cheie, marime, texte):
		"""functia text -> pixeli pentru font; literele noi din `texte` se masoara o data (latimea lui „x<semn>x” minus a
		lui „xx”) si se tin minte pentru font. Fara masura: o latime medie."""
		semne = _SEMNE.setdefault(cheie, {})
		medie = max(1, int(LATIME_SEMN * marime))
		baza = semne.get("\0")
		if baza is None:
			baza = self._latimeText("xx", font)
			if not baza:
				return lambda t: len(t) * medie
			semne["\0"] = baza
		for text in texte:
			for s in text:
				if s not in semne:
					w = self._latimeText("x%sx" % s, font)
					semne[s] = max(0, w - baza) if w is not None else medie
		return lambda t: sum(semne.get(s, medie) for s in t)

	def _inchide(self, rez):
		"""inchiderea cu ROSU sau cu o fapta aleasa: in jos spre ecranul care a deschis ajutorul; spre meniu, fara rezultat"""
		if self.dinMeniu:
			self.close()
		else:
			self.close(rez)

	def inchideTot(self):
		self._inchide("inchide")

	def dupaCopil(self, rez=None, *args):
		"""un ecran al ajutorului deschis de aici s-a inchis: ROSU (inchide) si o fapta aleasa merg mai departe in jos"""
		if rez == "inchide" or (isinstance(rez, tuple) and rez and rez[0] == "actiune"):
			self._inchide(rez)

	def deschideCuprins(self):
		self.session.openWithCallback(self.dupaCopil, HdsAjutorCuprins, ecran=self.ecran)

	def cauta(self):
		if not A.instalat():
			return
		from Screens.VirtualKeyBoard import VirtualKeyBoard
		self.session.openWithCallback(self._dupaTastatura, VirtualKeyBoard, title=self.T("cauta_titlu"), text="")

	def _dupaTastatura(self, text=None):
		text = (text or "").strip()
		if not text:
			return
		pagini = A.cauta(text, self.limba)
		self.session.openWithCallback(self.dupaCopil, HdsAjutorLista, pagini, self.T("cauta_rezultate") % text,
			cautare=True, ecran=self.ecran)


class HdsAjutorLista(_Baza):
	"""Paginile unui capitol sau rezultatele cautarii (si, in HdsAjutorCuprins, capitolele)."""

	def __init__(self, session, pagini=None, titlu="", cautare=False, ecran=_DIN_MENIU, subtitlu=""):
		"""titlu: titlul ecranului (scurt, incape in bara de sus a skinului: „Capitolul 03”, „Caută: ...”); subtitlu:
		inaintea starii de sub lista (numele capitolului, care poate fi lung)"""
		_Baza.__init__(self, session, ecran)
		self.skinName = ["HdsAjutorLista"]
		self.skin = self._skinImplicit()
		self.pagini = list(pagini or [])
		self.cautare = cautare
		self.titlu = titlu
		self.subtitlu = subtitlu
		self.setTitle(titlu or self.T("ajutor"))
		self["lista"] = MenuList([], content=eListboxPythonMultiContent)
		self["stare"] = Label("")
		self["key_red"] = StaticText(self.T("inchide"))
		# fara pachetul ajutorului nu e nimic de cautat: tasta verde nu se vede si nu face nimic (cauta())
		self["key_green"] = StaticText(self.T("cauta") if A.instalat() else "")
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.ok,
			"cancel": self.close,
			"red": self.inchideTot,
			"green": self.cauta,
			"left": self.paginaSus,
			"right": self.paginaJos,
		}, -1)
		self.onLayoutFinish.append(self._pregateste)

	def _skinImplicit(self):
		l, i = _ecran()
		f = _factor()
		x, y = max(16, int(l * 0.0375)), max(24, int(i * 0.056))
		L, I = l - 2 * x, i - 2 * y
		p = max(8, int(L * 0.009))
		mMic, mButon = max(14, int(24 * f)), max(14, int(26 * f))
		hStare, hButon = max(24, int(44 * f)), max(28, int(52 * f))
		hLista = I - 4 * p - hStare - hButon
		lButon = max(180, int(L * 0.16))
		yJos = p + hLista + p + hStare + p
		return SKIN_LISTA % (
			x, y, L, I,
			p, p, L - 2 * p, hLista, max(36, int(64 * f)),
			p, p + hLista + p, L - 2 * p, hStare, mMic,
			p, yJos, lButon, hButon, mButon,
			2 * p + lButon, yJos, lButon, hButon, mButon)

	def _pregateste(self):
		self["masura"].hide()
		self.fontMare, mMare, self.cheieMare = _font(*FONT_LISTA)
		self.fontMic, mMic, self.cheieMic = _font(*FONT_LISTA_MIC)
		self.mMare, self.mMic = mMare, mMic
		lista = self["lista"]
		lista.l.setFont(0, self.fontMare)
		lista.l.setFont(1, self.fontMic)
		self.inaltime = max(36, int(mMare * 2))
		lista.l.setItemHeight(self.inaltime)
		try:
			self.latime = lista.instance.size().width() - max(24, int(40 * _factor()))
		except Exception:
			self.latime = int(1680 * _factor())
		self.construieste()

	def randuri(self):
		"""[(cheie, stanga, text, dreapta)] ale listei; la cautare, in dreapta capitolul paginii"""
		capitole = A.capitole(self.limba) if self.cautare else []
		rez = []
		for i in self.pagini:
			cap = A.capitol_pagina(i)
			dreapta = capitole[cap]["titlu"] if capitole and cap is not None and 0 <= cap < len(capitole) else ""
			rez.append((i, "", A.titlu_pagina(i, self.limba), dreapta))
		return rez

	def stare(self):
		if not A.instalat():
			return A.text("lipsa", self.limba)
		if self.cautare:
			return self.T("gasite_n") % len(self.pagini) if self.pagini else self.T("nimic_gasit")
		n = self.T("pagini_n") % len(self.pagini)
		return u"%s · %s" % (self.subtitlu, n) if self.subtitlu else n

	def construieste(self):
		c, h, w = self.c, self.inaltime, self.latime
		f = _factor()
		xs = max(8, int(16 * f))
		lStanga = max(48, int(72 * f))
		randuri = self.randuri()
		latMare = self.latimeFont(self.fontMare, self.cheieMare, self.mMare, [r[2] for r in randuri] + [ELIPSA])
		latMic = self.latimeFont(self.fontMic, self.cheieMic, self.mMic,
			[r[1] for r in randuri] + [r[3] for r in randuri] + [ELIPSA])
		# coloana din dreapta: cat cel mai lung text al ei, cel mult DREAPTA_MAXIM din latime; ce nu incape (in ea sau in
		# titlu) se taie cu „…”, nu iese din coloana
		lungi = [latMic(r[3]) for r in randuri if r[3]]
		lDreapta = min(max(lungi) + 2 * xs, int(w * DREAPTA_MAXIM)) if lungi else 0
		rez = []
		for cheie, stanga, text, dreapta in randuri:
			ld = lDreapta if dreapta else 0
			x = xs + (lStanga if stanga else 0)
			lText = max(1, w - x - ld - xs)
			rand = [cheie]
			if stanga:
				rand.append(MultiContentEntryText(pos=(xs, 0), size=(lStanga, h), font=1,
					flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=stanga, color=c["eticheta"], color_sel=c["pe_cursor"]))
			rand.append(MultiContentEntryText(pos=(x, 0), size=(lText, h), font=0,
				flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=_scurteaza(text, latMare, lText), color=c["text"],
				color_sel=c["pe_cursor"]))
			if dreapta:
				rand.append(MultiContentEntryText(pos=(w - ld, 0), size=(ld - xs, h), font=1,
					flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER, text=_scurteaza(dreapta, latMic, ld - 2 * xs),
					color=c["eticheta"], color_sel=c["pe_cursor"]))
			rez.append(rand)
		self["lista"].setList(rez)
		self["stare"].setText(self.stare())

	def ales(self):
		x = self["lista"].getCurrent()
		return x[0] if x else None

	def ok(self):
		i = self.ales()
		if i is not None:
			self.session.openWithCallback(self.dupaCopil, HdsAjutorPagina, i, ecran=self.ecran)

	def paginaSus(self):
		self["lista"].pageUp()

	def paginaJos(self):
		self["lista"].pageDown()


class HdsAjutorCuprins(HdsAjutorLista):
	"""„Ajutor” din meniul principal (si tasta HELP pe un ecran fara pagina): capitolele ajutorului."""

	def __init__(self, session, nota=None, ecran=_DIN_MENIU, *args):
		self.nota = nota
		HdsAjutorLista.__init__(self, session, [], A.text("ajutor"), ecran=ecran)
		# intai un ecran al lui in skin, apoi cel al listelor
		self.skinName = ["HdsAjutorCuprins", "HdsAjutorLista"]
		self.setTitle(self.T("ajutor"))

	def randuri(self):
		return [(c["i"], c["cod"], c["titlu"], self.T("pagini_n") % len(c["pagini"])) for c in A.capitole(self.limba)]

	def stare(self):
		if not A.instalat():
			return A.text("lipsa", self.limba)
		if self.nota:
			return self.nota
		if A.in_engleza(self.limba):
			return self.T("in_engleza")
		return self.T("versiune") % A.versiune() if A.versiune() else ""

	def ok(self):
		i = self.ales()
		cap = A.capitole(self.limba)
		if i is not None and 0 <= i < len(cap):
			# titlul ecranului scurt („Capitolul 03”): numele capitolului (pana la ~48 de semne) nu incape in bara de sus
			# a skinului, deci sta in starea de sub lista
			self.session.openWithCallback(self.dupaCopil, HdsAjutorLista, cap[i]["pagini"],
				self.T("capitol") % cap[i]["cod"], ecran=self.ecran, subtitlu=cap[i]["titlu"])


class HdsAjutorPagina(_Baza):
	"""O pagina de ajutor, fara poze."""

	def __init__(self, session, pagina, ecran=_DIN_MENIU):
		_Baza.__init__(self, session, ecran)
		self.skin = self._skinImplicit()
		self.i = pagina
		self.setTitle(A.titlu_pagina(pagina, self.limba) or self.T("ajutor"))
		self.blocuri = []           # [(prima linie selectabila, [liniile blocului], legatura, inceputul cu titlul)]
		self._randuri = []          # randurile desenate ale listei
		self._linii = []            # linia (bucatile) din care s-a desenat fiecare rand, pentru redesenare
		self._luminat = None
		self.pePagina = 0
		self["lista"] = MenuList([], content=eListboxPythonMultiContent)
		self["stare"] = Label("")
		self["online"] = Label("")
		self["key_red"] = StaticText(self.T("inchide"))
		self["key_green"] = StaticText(self.T("cuprins"))
		self["key_yellow"] = StaticText(self.T("cauta"))
		# fara lista tastelor ecranului de dedesubt, tasta albastra nu se vede deloc (nici semnul ei de culoare)
		self["key_blue"] = StaticText(self.T("tastele_ecranului") if self.ecran is not None else "")
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.ok,
			"cancel": self.close,
			"red": self.inchideTot,
			"green": self.deschideCuprins,
			"yellow": self.cauta,
			"blue": self.tasteleEcranului,
			"up": self.sus,
			"down": self.jos,
			"left": self.paginaSus,
			"right": self.paginaJos,
			"upRepeated": self.sus,
			"downRepeated": self.jos,
			"leftRepeated": self.paginaSus,
			"rightRepeated": self.paginaJos,
			"upUp": self._nimic,
			"downUp": self._nimic,
			"leftUp": self._nimic,
			"rightUp": self._nimic,
		}, -1)
		self.onLayoutFinish.append(self._pregateste)
		self.onClose.append(self._laInchidere)

	def _skinImplicit(self):
		l, i = _ecran()
		f = _factor()
		x, y = max(16, int(l * 0.0375)), max(24, int(i * 0.056))
		L, I = l - 2 * x, i - 2 * y
		p = max(8, int(L * 0.009))
		mMic, mButon = max(14, int(24 * f)), max(14, int(26 * f))
		hStare, hButon = max(22, int(36 * f)), max(28, int(52 * f))
		hLista = I - 5 * p - 2 * hStare - hButon
		lButon = max(160, int((L - 5 * p) / 4))
		yJos = p + hLista + p + hStare + p + hStare + p
		return SKIN_PAGINA % (
			x, y, L, I,
			p, p, L - 2 * p, hLista,
			p, p + hLista + p, L - 2 * p, hStare, mMic,
			p, p + hLista + 2 * p + hStare, L - 2 * p, hStare, mMic,
			p, yJos, lButon, hButon, mButon,
			2 * p + lButon, yJos, lButon, hButon, mButon,
			3 * p + 2 * lButon, yJos, lButon, hButon, mButon,
			4 * p + 3 * lButon, yJos, lButon, hButon, mButon)

	# ------------------------------------------------------------ pregatire

	def _pregateste(self):
		self["masura"].hide()
		self.fonturi = [_font(*x) for x in FONTURI]
		lista = self["lista"]
		for n, (font, _m, _k) in enumerate(self.fonturi):
			lista.l.setFont(n, font)
		self.inaltime = max(24, int(max(self.fonturi[F_TITLU][1], self.fonturi[F_TEXT][1]) * 1.45))
		lista.l.setItemHeight(self.inaltime)
		lista.selectionEnabled(True)
		try:
			marime = lista.instance.size()
			cate = marime.height() // self.inaltime
			if cate > 0 and cate * self.inaltime != marime.height():
				lista.instance.resize(eSize(marime.width(), cate * self.inaltime))
			self.pePagina = max(1, cate)
			self.latime = marime.width()
		except Exception as e:
			_jurnal("marimea listei: %s" % e)
			self.latime = int(1712 * _factor())
			self.pePagina = 0
		# bara de derulare si marginea ei nu fac parte din latimea scrisului
		self.latime = max(200, self.latime - max(24, int(40 * _factor())))
		try:
			lista.onSelectionChanged.append(self._laSchimbare)
		except Exception as e:
			_jurnal("urmarirea cursorului: %s" % e)
		self.construieste()

	def _laInchidere(self):
		try:
			self["lista"].onSelectionChanged.remove(self._laSchimbare)
		except Exception:
			pass

	def _nimic(self):
		pass

	# ------------------------------------------------------------ blocurile paginii

	def _masuri(self, pg):
		texte = [pg.get("t") or ""]
		for parte, elemente in pg.get("p") or []:
			texte.append(self.T(parte))
			for e in elemente:
				for x in e[:-1]:
					if isinstance(x, list):
						texte.extend("%s" % y for y in x)
					else:
						texte.append("%s" % x)
		texte.extend([self.T("valori"), self.T("din_fabrica"), self.T("cand"), SEMN_LEGATURA, "0123456789."])
		self.lat = []
		for font, m, cheie in self.fonturi:
			self.lat.append(self.latimeFont(font, cheie, m, texte))

	def _linie(self, bucati, titlu=False):
		"""o linie de lista: [(x, latime, font, culoare, text)]; titlu=True pune linia de sub titlul partii"""
		return (bucati, titlu)

	def _rupe(self, text, font, loc):
		return _rupe(text, self.lat[font], loc)

	def _blocTitlu(self, text):
		x0 = self.x0
		return [self._linie([(x0, self.latime - x0, F_TITLU, "titlu", t)], titlu=(n == len(r) - 1))
			for r in [self._rupe(text, F_TITLU, self.latime - x0)] for n, t in enumerate(r)]

	def _blocText(self, text, font=F_TEXT, culoare="text", x=None, prefix=""):
		x = self.x0 if x is None else x
		loc = self.latime - x
		return [self._linie([(x, loc, font, culoare, t)]) for t in self._rupe(prefix + text, font, loc)]

	def _blocEticheta(self, eticheta, text):
		"""„Eticheta: text”, in fontul etichetelor, rupt pe randuri"""
		return self._blocText("%s: %s" % (eticheta, text), F_ETICHETA, "eticheta")

	def _blocDouaColoane(self, stanga, dreapta, fontStanga, culoareStanga, lStanga):
		x0 = self.x0
		x1 = x0 + lStanga + self.spatiu
		a = self._rupe(stanga, fontStanga, lStanga) if stanga else []
		b = self._rupe(dreapta, F_TEXT, self.latime - x1) if dreapta else []
		linii = []
		for n in range(max(len(a), len(b), 1)):
			bucati = []
			if n < len(a):
				bucati.append((x0, lStanga, fontStanga, culoareStanga, a[n]))
			if n < len(b):
				bucati.append((x1, self.latime - x1, F_TEXT, "text", b[n]))
			linii.append(self._linie(bucati))
		return linii

	def _element(self, parte, e):
		"""liniile unui element al partii si pagina legata (-1)"""
		leg = e[-1] if e and isinstance(e[-1], int) else -1
		if parte == "randuri":
			nume, valori, fabrica, ce_face, cand = (list(e) + [""] * 5)[:5]
			linii = self._blocText(nume, F_BOLD) if nume else []
			if valori:
				linii += self._blocEticheta(self.T("valori"), valori)
			if fabrica:
				linii += self._blocEticheta(self.T("din_fabrica"), fabrica)
			if ce_face:
				linii += self._blocText(ce_face)
			if cand:
				linii += self._blocEticheta(self.T("cand"), cand)
			return linii, leg
		if parte == "taste":
			return self._blocDouaColoane(e[0], e[1], F_BOLD, "titlu", self.lTasta), leg
		if parte == "pas_cu_pas":
			titlu, pasi = e[0], e[1] if len(e) > 1 and isinstance(e[1], list) else []
			linii = self._blocText(titlu, F_BOLD) if titlu else []
			for n, pas in enumerate(pasi):
				linii += self._blocDouaColoane("%d." % (n + 1), pas, F_ETICHETA, "eticheta", self.lNumar)
			return linii, leg
		if parte == "probleme":
			linii = self._blocText(e[0], F_BOLD) if e[0] else []
			if len(e) > 2 and e[1]:
				linii += self._blocText(e[1])
			return linii, leg
		if parte == "legat_de":
			culoare = "legatura" if leg >= 0 else "text"
			return self._blocText(e[0], culoare=culoare, prefix=(SEMN_LEGATURA + " ") if leg >= 0 else ""), leg
		return self._blocText(e[0] if e else ""), leg

	def construieste(self):
		pg = A.pagina(self.i, self.limba)
		f = _factor()
		self.x0 = max(4, int(8 * f))
		self.spatiu = max(8, int(16 * f))
		self.lTasta = int(self.latime * 0.24)
		self.lNumar = max(30, int(48 * f))
		if pg is None:
			pg = {"t": "", "p": []}
			mesaj = A.text("lipsa", self.limba) if not A.instalat() else self.T("pagina_lipsa")
		else:
			mesaj = None
		self._masuri(pg)
		blocuri = []        # (felul, [linii], legatura)
		if mesaj:
			blocuri.append(("bloc", self._blocText(mesaj), -1))
		for parte, elemente in pg.get("p") or []:
			lipit = self._blocTitlu(self.T(parte))
			for e in elemente:
				linii, leg = self._element(parte, e)
				if not linii:
					continue
				blocuri.append(("bloc", lipit + linii, leg, len(lipit)))
				lipit = []
			if lipit:
				blocuri.append(("titlu", lipit, -1, len(lipit)))
		self._aseaza(blocuri)

	def _aseaza(self, blocuri):
		"""liniile listei din blocuri: un bloc care incape pe o pagina nu se rupe intre doua pagini; titlul partii sta
		langa primul ei bloc. Prima linie a blocului (dupa titlu) e cea selectabila."""
		n = self.pePagina
		rez = []
		self.blocuri = []
		for b in blocuri:
			fel, linii, leg = b[0], b[1], b[2]
			inainte = b[3] if len(b) > 3 else 0
			# blocul (cu titlul partii lipit de el) care nu mai incape pe restul paginii incepe pe pagina urmatoare;
			# unul mai lung decat o pagina incepe si el sus, ca sa se rupa cat mai putin
			if n and (len(rez) % n) and (len(rez) % n) + len(linii) > n:
				rez.extend([(None, None)] * (n - len(rez) % n))
			start = len(rez)
			for k, linie in enumerate(linii):
				selectabil = fel == "bloc" and k == inainte
				rez.append((len(self.blocuri) if selectabil else None, linie))
			if fel == "bloc":
				self.blocuri.append((start + inainte, list(range(start + inainte, start + len(linii))), leg, start))
		self._linii = [linie for _cheie, linie in rez]
		self._randuri = [self._desen(cheie, linie, False) for cheie, linie in rez]
		self._luminat = None
		self["lista"].setList(self._randuri)
		self._laSchimbare()

	def _desen(self, cheie, linie, luminat):
		c, h, w = self.c, self.inaltime, self.latime
		rand = [cheie]
		if linie is None:
			return [None]
		bucati, titlu = linie
		if luminat:
			rand.append(MultiContentEntryText(pos=(0, 0), size=(w + max(24, int(40 * _factor())), h), font=F_TEXT,
				text="", backcolor=c["cursor"], backcolor_sel=c["cursor"]))
		grosime = max(2, h // 20)
		for x, lat, font, culoare, text in bucati:
			culoare_text = c["pe_cursor"] if luminat else c[culoare]
			rand.append(MultiContentEntryText(pos=(x, 0), size=(max(1, lat), h - (2 * grosime if titlu else 0)),
				font=font, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=text, color=culoare_text,
				color_sel=c["pe_cursor"]))
		if titlu:
			rand.append(MultiContentEntryText(pos=(self.x0, h - 2 * grosime), size=(w - self.x0, grosime), font=F_TEXT,
				text="", backcolor=c["linie"], backcolor_sel=c["linie"]))
		return rand

	def _blocAles(self):
		try:
			x = self["lista"].getCurrent()
		except Exception:
			return None
		if not x or x[0] is None:
			return None
		k = x[0]
		return self.blocuri[k] if 0 <= k < len(self.blocuri) else None

	def _laSchimbare(self):
		"""Liniile blocului ales primesc fondul cursorului (prima linie il are de la lista); ale celui de dinainte, fondul
		obisnuit. Se redeseneaza numai randurile schimbate."""
		lista = self["lista"]
		bloc = self._blocAles()
		ales = bloc[0] if bloc else None
		if ales != self._luminat:
			schimbate = []
			for b, luminat in ((self._luminat, False), (ales, True)):
				if b is None:
					continue
				gasit = [x for x in self.blocuri if x[0] == b]
				if not gasit:
					continue
				for i in gasit[0][1]:
					if i == gasit[0][0] or not 0 <= i < len(self._randuri):
						continue
					linie = self._linii[i] if i < len(self._linii) else None
					if linie is None:
						continue
					self._randuri[i] = self._desen(None, linie, luminat)
					schimbate.append(i)
			self._luminat = ales
			for i in schimbate:
				try:
					lista.l.invalidateEntry(i)
				except Exception as e:
					_jurnal("redesenarea randului %d: %s" % (i, e))
					break
		self._stare(bloc)

	def _stare(self, bloc):
		bucati = []
		cap = A.capitol_pagina(self.i)
		capitole = A.capitole(self.limba)
		if cap is not None and 0 <= cap < len(capitole):
			bucati.append(capitole[cap]["titlu"])
		n = self.pePagina
		if n and self._randuri:
			try:
				i = self["lista"].getSelectionIndex()
			except Exception:
				i = 0
			total = (len(self._randuri) + n - 1) // n
			if total > 1:
				bucati.append(self.T("pagina_din") % (i // n + 1, total))
		if bloc and bloc[2] >= 0:
			bucati.append(self.T("indemn_legatura"))
		else:
			bucati.append(self.T("indemn_pagina"))
		self["stare"].setText(u" · ".join(b for b in bucati if b))
		if A.in_engleza(self.limba):
			self["online"].setText(self.T("in_engleza"))
		else:
			self["online"].setText(self.T("online") % A.adresa_online(self.i, self.limba) if A.instalat() else "")

	# ------------------------------------------------------------ taste

	def sus(self):
		self["lista"].up()

	def jos(self):
		self["lista"].down()

	def paginaSus(self):
		self["lista"].pageUp()

	def paginaJos(self):
		self["lista"].pageDown()

	def ok(self):
		bloc = self._blocAles()
		if bloc and bloc[2] >= 0 and bloc[2] != self.i:
			self.session.openWithCallback(self.dupaCopil, HdsAjutorPagina, bloc[2], ecran=self.ecran)

	def tasteleEcranului(self):
		lista = getattr(self.ecran, "helpList", None) if self.ecran is not None else None
		if not lista:
			return
		from Screens.HelpMenu import HelpMenu
		self.session.openWithCallback(self._dupaTaste, HelpMenu, lista)

	def _dupaTaste(self, *rez):
		if rez:
			self._inchide(("actiune", rez))
