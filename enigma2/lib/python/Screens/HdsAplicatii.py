# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAplicatii.py: meniul „Aplicații” (0.7.5, meniul principal, data/menu.xml), ca pe televizoarele smart: grila de
# carduri 16:9, cate COLOANE pe rand si RANDURI_VIZIBILE randuri pe ecran (designul din Stitch, proiectul interfetei,
# ecranul „Aplicații (TV Smart Launcher)”). Totul dintr-o privire: titlul, grila, banda cu descrierea aplicatiei alese
# (randul care nu incape deruleaza) si tastele.
#   OK      actiunea cardului: Porneste (scurtatura in navigatorul imaginii, aplicatia instalata prin pluginul ei; EXIT
#           din aplicatie intoarce aici) sau, pe o aplicatie din feed neinstalata, Instaleaza;
#   MENU    Porneste / Actualizeaza / Dezinstaleaza (aplicatiile din feed), muta cardul (stanga, dreapta), il ascunde,
#           sau le arata din nou pe cele ascunse;
#   EXIT    inapoi in meniu.
# Magazinul (runda 2): starea aplicatiilor din feed (Instalat / Actualizare disponibila / Disponibil) vine din catalogul
# opkg al imaginii, citit pe un fir la deschidere (pana atunci se vad cele instalate, dupa dosarul pluginului);
# instalarea, actualizarea si stergerea trec prin fereastra Extensiilor (Screens/HdsExtensii.HdsExtensiiActiune:
# confirmarea cu sursa, versiunea si marimea, apoi progresul), cu planurile din Components/HdsExtensiiLucru.
# Lista, ordinea, ascunderea si mutarea in grila sunt in Components/HdsAplicatii.py (probele de pe PC); perechea web
# e /aplicatii-tv (HdsWebControl/aplicatii_tv_web.py), cu aceleasi carduri si aceleasi setari.
# Skinul: blocul HdsAplicatii din tema aleasa, altfel cel de mai jos, facut dupa marimea ecranului (1920x1080 sau
# 1280x720), numai cu fontul „Regular” (merge cu orice tema) si culori scrise direct (ale temei Clasic).

from enigma import eTimer, getDesktop, gRGB

from Screens.Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Components import HdsAplicatii as A


def N_(text):
	return text


FOND = "#00101828"
CULOARE_STARE = {A.INSTALAT: "#00a8b3c7", A.ACTUALIZARE: "#00f5b83d", A.DISPONIBIL: "#004fd18b"}
TEXTE_ACTIUNI = {
	"porneste": N_("Pornește"),
	"instaleaza": N_("Instalează"),
	"actualizeaza": N_("Actualizează"),
	"dezinstaleaza": N_("Dezinstalează"),
	"instaleaza-widevine": N_("Instalează modulul Widevine"),
}
FOND_CARD_GOL = "#001b2436"
CHIHLIMBAR = "#00f5b83d"


def _culoare(text):
	"""#RRGGBB -> gRGB (fara transparenta)."""
	try:
		v = int(text.lstrip("#"), 16)
	except (AttributeError, ValueError):
		v = 0x374EA1
	return gRGB((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)


def geometrie(latime, inaltime):
	"""Pozitiile cardurilor (x, y, l, i) pentru cele COLOANE x RANDURI_VIZIBILE locuri, la marimea ecranului."""
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))
	locuri = []
	for r in range(A.RANDURI_VIZIBILE):
		for c in range(A.COLOANE):
			locuri.append((x(72 + c * (420 + 32)), y(196 + r * 318), x(420), y(236)))
	return locuri, x, y


def skinAplicatii(latime, inaltime):
	locuri, x, y = geometrie(latime, inaltime)
	b = max(2, x(5))
	w = []
	for k, (cx, cy, cl, ch) in enumerate(locuri):
		w.append('<widget name="rama%d" position="%d,%d" size="%d,%d" backgroundColor="%s" zPosition="1" />'
			% (k, cx - b, cy - b, cl + 2 * b, ch + 2 * b, CHIHLIMBAR))
		w.append('<widget name="card%d" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="center" '
			'foregroundColor="#00ffffff" backgroundColor="%s" zPosition="2" />' % (k, cx, cy, cl, ch, y(44), FOND_CARD_GOL))
		# poza cardului (cand exista) peste culoare, cu numele pe o banda intunecata jos
		w.append('<widget name="poza%d" position="%d,%d" size="%d,%d" alphatest="blend" zPosition="3" />' % (k, cx, cy, cl, ch))
		w.append('<widget name="nume%d" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="center" '
			'noWrap="1" foregroundColor="#00ffffff" backgroundColor="#40000000" zPosition="4" />'
			% (k, cx, cy + ch - y(52), cl, y(52), y(32)))
		w.append('<widget name="stare%d" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="center" '
			'noWrap="1" foregroundColor="#00a8b3c7" backgroundColor="%s" transparent="1" zPosition="2" />'
			% (k, cx, cy + ch + y(10), cl, y(36), y(24), FOND))
	return """
	<screen name="HdsAplicatii" position="0,0" size="%(l)d,%(i)d" flags="wfNoBorder" backgroundColor="%(fond)s" title="Aplicații">
		<widget source="titlu" render="Label" position="%(mx)d,%(ty)d" size="%(tl)d,%(th)d" font="Regular;%(tf)d" halign="left" valign="center" foregroundColor="#00f2f4f8" backgroundColor="%(fond)s" transparent="1" />
		<eLabel position="%(mx)d,%(ly)d" size="%(ll)d,%(lh)d" backgroundColor="%(chi)s" />
		<widget source="subtitlu" render="Label" position="%(sx)d,%(ty)d" size="%(sl)d,%(th)d" font="Regular;%(sf)d" halign="right" valign="center" noWrap="1" foregroundColor="#00a8b3c7" backgroundColor="%(fond)s" transparent="1" />
		%(carduri)s
		<widget name="gol" position="%(mx)d,%(gy)d" size="%(bl)d,%(gh)d" font="Regular;%(bf)d" halign="center" valign="center" foregroundColor="#00e1e7f0" backgroundColor="%(fond)s" transparent="1" zPosition="3" />
		<eLabel position="%(mx)d,%(by)d" size="%(bl)d,%(bh)d" backgroundColor="#001b2436" />
		<widget source="descriere" render="Label" position="%(dx)d,%(by)d" size="%(dl)d,%(bh)d" font="Regular;%(bf)d" halign="left" valign="center" noWrap="1" foregroundColor="#00f3e3c3" backgroundColor="#001b2436" transparent="1" zPosition="1" />
		<widget source="taste" render="Label" position="%(mx)d,%(jy)d" size="%(bl)d,%(jh)d" font="Regular;%(jf)d" halign="left" valign="center" noWrap="1" foregroundColor="#00e1e7f0" backgroundColor="%(fond)s" transparent="1" />
	</screen>""" % {
		"l": latime, "i": inaltime, "fond": FOND, "chi": CHIHLIMBAR,
		"mx": x(72), "ty": y(46), "tl": x(700), "th": y(72), "tf": y(52),
		"ly": y(122), "ll": x(110), "lh": max(2, y(5)),
		"sx": x(800), "sl": x(1048), "sf": y(26),
		"carduri": "\n\t\t".join(w),
		"gy": y(300), "gh": y(200),
		"by": y(866), "bl": x(1776), "bh": y(64), "bf": y(28), "dx": x(96), "dl": x(1728),
		"jy": y(966), "jh": y(50), "jf": y(26),
	}


class HdsAplicatii(Screen):
	"""Grila aplicatiilor; `*argumente` vin de la meniu (data/menu.xml) si nu se folosesc."""

	def __init__(self, session, *argumente):
		s = getDesktop(0).size()
		self.skin = skinAplicatii(s.width(), s.height())
		self.marimeCard = geometrie(s.width(), s.height())[0][0][2:]
		Screen.__init__(self, session)
		self.setTitle(_("Aplicații"))
		self["titlu"] = StaticText(_("Aplicații"))
		self["subtitlu"] = StaticText(_("Pe tot ecranul, cu telecomanda"))
		self["descriere"] = StaticText("")
		self["taste"] = StaticText(_("OK: deschide    MENU: mai multe    EXIT: înapoi"))
		self["gol"] = Label("")
		self.locuri = A.COLOANE * A.RANDURI_VIZIBILE
		for k in range(self.locuri):
			self["rama%d" % k] = Label("")
			self["card%d" % k] = Label("")
			self["poza%d" % k] = Pixmap()
			self["nume%d" % k] = Label("")
			self["stare%d" % k] = Label("")
		self.aplicatii = []
		self.ales = 0
		self.inceput = 0      # primul rand vazut
		self.video = None     # WebKit-ul are video? (aflat la deschidere)
		self.catalog = None   # catalogul opkg (Components/HdsPachete), citit pe un fir
		self._poze = {}       # calea pozei -> pixmap (la marimea cardului), cat e deschis ecranul
		self.ceas = eTimer()
		self.ceas.callback.append(self._asteaptaCatalogul)
		self["actiuni"] = ActionMap(["OkCancelActions", "DirectionActions", "MenuActions"], {
			"ok": self.ok,
			"cancel": self.close,
			"up": lambda: self.misca("sus"),
			"down": lambda: self.misca("jos"),
			"left": lambda: self.misca("stanga"),
			"right": lambda: self.misca("dreapta"),
			"menu": self.meniu,
		}, -1)
		self.onLayoutFinish.append(self._laInceput)
		self.onClose.append(self.ceas.stop)

	def _laInceput(self):
		self.catalog = A.catalogAcum()
		self.reumple()
		if self.catalog is None:
			self.ceas.start(400, False)

	def _asteaptaCatalogul(self):
		if A.catalogInLucru():
			return
		self.ceas.stop()
		self.catalog = A.catalogAcum()
		self.reumple()

	# ------------------------------------------------ desenul

	def reumple(self, id_ales=None):
		if self.video is None:
			self.video = A.areVideo()
		if id_ales is None and self.aplicatii:
			id_ales = self.aplicatii[min(self.ales, len(self.aplicatii) - 1)]["id"]
		self.aplicatii = A.listaPentruOm(catalog=self.catalog)
		ids = [a["id"] for a in self.aplicatii]
		self.ales = ids.index(id_ales) if id_ales in ids else min(self.ales, max(0, len(ids) - 1))
		self.deseneaza()

	def _titlu(self, a):
		return _(a["titlu"]) if a.get("titlu_tradus") else a["titlu"]

	def _textStare(self, a):
		s = a.get("stare")
		if A.fel(a) == A.FEL_SCURTATURA and s != A.CERE_WIDEVINE:
			nota = A.stare(a, self.video)
			return _(nota) if nota else _("Instalat")
		text = _(A.TEXTE_STARE.get(s, ""))
		if s == A.DISPONIBIL:
			p = A.pachetDinCatalog(a, self.catalog)
			if p is not None and p.marime:
				try:
					from Components.HdsPachete import marime_text
					text += " · " + marime_text(p.marime)
				except ImportError:
					pass
		return text

	def _pixmap(self, cale):
		if cale not in self._poze:
			try:
				from Tools.LoadPixmap import LoadPixmap
				l, i = self.marimeCard
				self._poze[cale] = LoadPixmap(cale, width=l, height=i)
			except Exception as e:
				print("[HdsAplicatii] poza %s: %s" % (cale, e))
				self._poze[cale] = None
		return self._poze[cale]

	def deseneaza(self):
		n = len(self.aplicatii)
		self.inceput = A.primulRandVazut(self.ales, self.inceput)
		primul = self.inceput * A.COLOANE
		for k in range(self.locuri):
			i = primul + k
			rama, card, stare = self["rama%d" % k], self["card%d" % k], self["stare%d" % k]
			poza, nume = self["poza%d" % k], self["nume%d" % k]
			if i < n:
				a = self.aplicatii[i]
				titlu = self._titlu(a)
				pm = self._pixmap(A.pozaPentru(a)) if A.pozaPentru(a) else None
				if card.instance:
					card.instance.setBackgroundColor(_culoare(a["culoare"]))
				if pm is not None and poza.instance:
					poza.instance.setPixmap(pm)
					poza.show()
					card.setText("")
					nume.setText(titlu)
					nume.show()
				else:
					poza.hide()
					nume.hide()
					card.setText(titlu.upper())
				stare.setText(self._textStare(a))
				if stare.instance:
					stare.instance.setForegroundColor(_culoare(CULOARE_STARE.get(a.get("stare"), "#a8b3c7")[-6:]))
				card.show()
				stare.show()
				if i == self.ales:
					rama.show()
				else:
					rama.hide()
			else:
				for w in (card, stare, rama, poza, nume):
					w.hide()
		if n:
			self["gol"].setText("")
			a = self.aplicatii[self.ales]
			self["descriere"].setText(A.descriereIntreaga(a, _, self.video))
		else:
			ascunse = len(A.listaPentruOm(cu_ascunse=True, catalog=self.catalog))
			self["gol"].setText(_("Toate aplicațiile sunt ascunse. MENU: arată-le din nou.") if ascunse else
				_("Nicio aplicație instalată."))
			self["descriere"].setText("")

	# ------------------------------------------------ tastele

	def misca(self, directie):
		if self.aplicatii:
			self.ales = A.misca(self.ales, len(self.aplicatii), directie)
			self.deseneaza()

	def ok(self):
		if not self.aplicatii:
			return
		a = self.aplicatii[self.ales]
		actiuni = A.actiuni(a, a.get("stare"))
		if actiuni:
			self.fa(actiuni[0], a)

	def deschide(self):
		"""Porneste aplicatia aleasa (OK pe o aplicatie instalata)."""
		if self.aplicatii:
			self.fa("porneste", self.aplicatii[self.ales])

	def fa(self, actiune, a):
		if actiune == "instaleaza-widevine":
			eroare = A.instaleazaWidevine(self.session, lambda *r: self.reumple(a["id"]))
			if eroare:
				self._mesaj(_(eroare))
			return
		if actiune == "porneste":
			if A.fel(a) == A.FEL_SCURTATURA:
				from Plugins.Extensions.HdsNavigator.ecrane import HdsNavigatorEcran
				from Plugins.Extensions.HdsNavigator import lansator as L
				self.session.openWithCallback(lambda *r: self.reumple(a["id"]), HdsNavigatorEcran, L.MOD_APLICATIE,
					a["url"], None, a)
				return
			eroare = A.porneste(self.session, a)
			if eroare:
				self._mesaj(_(eroare), MessageBox.TYPE_ERROR)
			return
		self._planOpkg(actiune, a)

	# ------------------------------------------------ instalarea, actualizarea, stergerea (calea Extensiilor)

	def _mesaj(self, text, fel=None):
		self.session.open(MessageBox, text, MessageBox.TYPE_INFO if fel is None else fel, timeout=8)

	def _planOpkg(self, actiune, a):
		from Components import HdsExtensiiLucru as L
		from Components.Ipkg import opkgArguments, opkgProgram
		if self.catalog is None:
			self._mesaj(_("Se citește lista extensiilor. Încearcă din nou peste câteva secunde."))
			return
		p = A.pachetDinCatalog(a, self.catalog)
		if p is None:
			self._mesaj(_("Aplicația nu e în lista extensiilor. Descarcă lista din Extensii și încearcă din nou."))
			return
		motiv = L.motivOcupat(None, opkgProgram)
		if motiv is not None:
			self._mesaj(motiv[0])
			return
		if actiune == "instaleaza":
			plan, eroare = L.planInstalare(self.catalog, p, opkgArguments, self._nota(L))
		elif actiune == "actualizeaza":
			plan, eroare = L.planActualizare(self.catalog, [p], opkgArguments, self._nota(L))
		else:
			plan, eroare = L.planStergere(self.catalog, p, opkgArguments)
		if plan is None:
			if eroare is not None:
				self._mesaj(eroare[0], MessageBox.TYPE_ERROR)
			return
		plan.setdefault("titluri", L.titluri(self.catalog))
		from Screens.HdsExtensii import HdsExtensiiActiune
		self.session.openWithCallback(lambda schimbat=False: self._dupaActiune(a["id"], schimbat), HdsExtensiiActiune, plan)

	def _nota(self, L):
		catalog = self.catalog

		def nota(pachete):
			externe = ["„%s”" % n for n, _a in L.surseExterne(catalog, pachete)]
			if not externe:
				text = L.notaFeedExtern(catalog, pachete)
				if text:
					return text
				return _("Verificat de HD Satelit.") if L.culoareNota(catalog, pachete) == "bun" else ""
			return _("Nu este verificată de HD Satelit. Vine din feedul %s.") % ", ".join(externe)
		return nota

	def _dupaActiune(self, id_, schimbat=False):
		if not schimbat:
			return
		# opkg a schimbat ceva: catalogul se citeste din nou (pe fir), apoi grila
		self.catalog = A.catalogAcum()
		self.reumple(id_)
		if self.catalog is None:
			self.ceas.start(400, False)

	# ------------------------------------------------ MENU

	def meniu(self):
		toate = A.listaPentruOm(cu_ascunse=True, catalog=self.catalog)
		ascunse = len(toate) - len(self.aplicatii)
		lista = []
		if self.aplicatii:
			a = self.aplicatii[self.ales]
			titlu = self._titlu(a)
			for x in A.actiuni(a, a.get("stare")):
				lista.append((_(TEXTE_ACTIUNI[x]), x))
			if self.ales > 0:
				lista.append((_("Mută la stânga"), "stanga"))
			if self.ales < len(self.aplicatii) - 1:
				lista.append((_("Mută la dreapta"), "dreapta"))
			lista.append((_("Ascunde aplicația"), "ascunde"))
		else:
			titlu = _("Aplicații")
		if ascunse:
			lista.append((_("Arată toate aplicațiile (%d ascunse)") % ascunse, "arata"))
		if not lista:
			return
		self.session.openWithCallback(self._dupaMeniu, ChoiceBox, title=titlu, list=lista)

	def _dupaMeniu(self, ales=None):
		if not ales:
			return
		cheie = ales[1]
		a = self.aplicatii[self.ales] if self.aplicatii else None
		id_ = a["id"] if a else None
		if cheie in TEXTE_ACTIUNI and a:
			self.fa(cheie, a)
		elif cheie in ("stanga", "dreapta") and id_:
			# locul vecinului vazut, chiar daca intre ei sta una ascunsa sau care nu se arata acum
			vecin = self.aplicatii[self.ales + (-1 if cheie == "stanga" else 1)]["id"]
			A.schimbaSiSalveaza(id_, vecin)
			self.reumple(id_)
		elif cheie == "ascunde" and id_:
			A.ascundeSiSalveaza(id_)
			self.reumple()
		elif cheie == "arata":
			A.arataToate()
			self.reumple(id_)
