# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMozaic.py (ecranul): toate canalele TV ale transponderului canalului de acum, pe 2, 4 sau 9 celule, cu pagini.
# Se deschide cu o tasta din bara (actiunea "mozaic" din Components/HdsTasteRapide.py, din fabrica 0 tinut apasat).
# Celula aleasa e vie, cu sunet (decodorul 0); a doua fereastra video, unde exista, arata viu inca o celula si, pe
# HiSilicon, lasa poze in urma (Components/HdsMozaic.py). Tastele: sagetile muta celula (si canalul cu sunet), CH+/CH- si
# PAGE+/PAGE- schimba pagina, ROSU 2, VERDE 4, GALBEN 9 (tinut minte), OK pune canalul ales pe tot ecranul, EXIT
# intoarce canalul de dinainte. Perechea web: Plugins/Extensions/HdsWebControl/mozaic_web.py.
# Desenul: celule pe fond inchis, chenar albastru pe celula aleasa, numarul si numele canalului sub imagine, emisiunea de
# acum dedesubt, bara tastelor jos; acelasi desen in pagina web.

import threading

from enigma import eTimer, ePoint, eSize, eServiceCenter, eServiceReference, getDesktop, iPlayableService
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ServiceEventTracker import ServiceEventTracker
from Components.SystemInfo import SystemInfo
from Components.VideoWindow import VideoWindow
from Components import HdsMozaic as M
from Screens.Screen import Screen

MAX = max(M.ALEGERI)
INCERCARI = 2      # pozele incercate pe un canal intr-o sesiune a mozaicului (negru, nedecriptat: nu la nesfarsit)
FUNDAL = "#0b1422"
CELULA = "#16233a"
ACCENT = "#2e8bff"
TEXT = "#f2f5fa"
STINS = "#9fb0c8"


def _desktop():
	try:
		d = getDesktop(0).size()
		if d.width() > 0 and d.height() > 0:
			return d.width(), d.height()
	except Exception:
		pass
	return 1920, 1080


def _skin(latime, inaltime):
	f = latime / 1920.0
	mare, mic, titlu = int(27 * f), int(22 * f), int(32 * f)
	w = ['<screen name="HdsMozaic" position="0,0" size="%d,%d" flags="wfNoBorder" backgroundColor="%s">'
		% (latime, inaltime, FUNDAL)]
	w.append('<widget name="selectie" position="0,0" size="10,10" backgroundColor="%s" zPosition="1" />' % ACCENT)
	for i in range(MAX):
		w.append('<widget name="fundal%d" position="0,0" size="10,10" backgroundColor="%s" zPosition="2" />' % (i, CELULA))
		w.append('<widget name="poza%d" position="0,0" size="10,10" zPosition="3" />' % i)
		w.append('<widget name="nume%d" position="0,0" size="10,10" font="Regular;%d" foregroundColor="%s" '
			'backgroundColor="%s" transparent="1" valign="top" noWrap="1" zPosition="4" />' % (i, mare, TEXT, CELULA))
		w.append('<widget name="program%d" position="0,0" size="10,10" font="Regular;%d" foregroundColor="%s" '
			'backgroundColor="%s" transparent="1" valign="top" noWrap="1" zPosition="4" />' % (i, mic, STINS, CELULA))
		w.append('<widget name="gol%d" position="0,0" size="10,10" font="Regular;%d" foregroundColor="%s" '
			'backgroundColor="%s" transparent="1" halign="center" valign="center" zPosition="4" />' % (i, mic, STINS, CELULA))
	w.append('<widget name="video0" position="0,0" size="10,10" zPosition="5" />')
	w.append('<widget name="video1" position="0,0" size="10,10" zPosition="5" />')
	w.append('<widget name="titlu" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="%s" '
		'backgroundColor="%s" transparent="1" valign="center" noWrap="1" />'
		% (int(48 * f), int(16 * f), int(1300 * f), int(56 * f), titlu, TEXT, FUNDAL))
	w.append('<widget name="pagina" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="%s" '
		'backgroundColor="%s" transparent="1" halign="right" valign="center" />'
		% (int(1372 * f), int(16 * f), int(500 * f), int(56 * f), mic, STINS, FUNDAL))
	w.append('<widget name="taste" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="%s" '
		'backgroundColor="%s" transparent="1" halign="center" valign="center" noWrap="1" />'
		% (int(48 * f), inaltime - int(58 * f), latime - int(96 * f), int(50 * f), mic, STINS, FUNDAL))
	w.append('</screen>')
	return "\n".join(w)


class HdsMozaic(Screen):
	def __init__(self, session, infobar=None):
		self.latime, self.inaltime = _desktop()
		self.skin = _skin(self.latime, self.inaltime)
		Screen.__init__(self, session)
		self.infobar = infobar
		self.setTitle(_("Mozaic"))
		self.vechi = session.nav.getCurrentlyPlayingServiceReference()
		vechi_text = self.vechi.toString() if self.vechi else ""
		self.canale = M.canaleTransponder(vechi_text)
		self.ales = 0
		curat = M.curata(vechi_text)
		for i, (ref, _nume) in enumerate(self.canale):
			if ref == curat:
				self.ales = i
		self.aleasa = M.asezareAleasa()
		self.pe = M.asezareEfectiva(self.aleasa, len(self.canale))
		self.doi = M.aDouaFereastra(SystemInfo.get("NumVideoDecoders", 1))
		self.metoda = M.metodaPozeiDoi() if self.doi else None
		self.pip = None
		self.pipRef = None
		self.pipCelula = None
		self.pipPornit = 0
		self.runda = []           # pe placile fara poze din fereastra a doua: canalele de trecut pe decodorul 0
		self.inRunda = False
		self.firPoza = None
		self.geo = []
		self.pornit = None        # canalul pornit acum pe decodorul 0
		self.cript = {}           # indice -> canalul e criptat (a doua fereastra numai pe cele necriptate)
		self.areVideo = False     # decodorul 0 a aratat primul cadru al canalului pornit (altfel grab -v ia cadrul vechi)
		self.rundeFacute = set()  # (pagina, asezare) pe care runda decodorului 0 s-a facut deja: o singura data
		self.incercari = {}       # referinta -> pozele incercate (cel mult INCERCARI pe sesiune, si pe a doua fereastra)
		self.pornitLa = 0
		self["selectie"] = Label("")
		for i in range(MAX):
			self["fundal%d" % i] = Label("")
			self["poza%d" % i] = Pixmap()
			self["nume%d" % i] = Label("")
			self["program%d" % i] = Label("")
			self["gol%d" % i] = Label("")
		self["video0"] = VideoWindow(decoder=0, fb_width=self.latime, fb_height=self.inaltime)
		self["video1"] = VideoWindow(decoder=1, fb_width=self.latime, fb_height=self.inaltime)
		self["titlu"] = Label("")
		self["pagina"] = Label("")
		self["taste"] = Label(_("Săgeți: alege · CH+/CH-: pagina · ROȘU 2 · VERDE 4 · GALBEN 9 · OK: pe tot ecranul · EXIT: înapoi"))
		self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions", "ListboxFallbackActions",
				"HdsPaginiActions"], {
			"ok": self.peTotEcranul,
			"cancel": self.inapoi,
			"left": lambda: self.mutaSel("stanga"),
			"right": lambda: self.mutaSel("dreapta"),
			"up": lambda: self.mutaSel("sus"),
			"down": lambda: self.mutaSel("jos"),
			"red": lambda: self.asezare(2),
			"green": lambda: self.asezare(4),
			"yellow": lambda: self.asezare(9),
			"fallbackPageUp": lambda: self.pagina(1),
			"fallbackPageDown": lambda: self.pagina(-1),
			"pageUp": lambda: self.pagina(1),
			"pageDown": lambda: self.pagina(-1),
		}, -2)
		self.__urmaritor = ServiceEventTracker(screen=self, eventmap={
			iPlayableService.evVideoSizeChanged: self._video,
			iPlayableService.evVideoFramerateChanged: self._video,
			iPlayableService.evVideoProgressiveChanged: self._video,
		})
		self.ceas = eTimer()
		self.ceas.callback.append(self.tic)
		self.onLayoutFinish.append(self.porneste)
		self.onClose.append(self.laInchidere)

	def _video(self):
		self.areVideo = True

	def _zap(self, ref):
		import time
		self.pornit = ref
		self.pornitLa = time.time()
		self.areVideo = False
		self.session.nav.playService(eServiceReference(ref))

	def _maiIncearca(self, ref):
		"""True daca pentru canal se mai poate incerca o poza (cel mult INCERCARI); numara incercarea"""
		n = self.incercari.get(ref, 0)
		if n >= INCERCARI:
			return False
		self.incercari[ref] = n + 1
		return True

	# ---------------------------------------------------------------- desenul

	def _pune(self, nume, r):
		w = self[nume].instance
		if w:
			w.move(ePoint(int(r[0]), int(r[1])))
			w.resize(eSize(max(1, int(r[2])), max(1, int(r[3]))))

	def porneste(self):
		if self.pip is None and getattr(self.session, "pipshown", False):
			# PiP-ul omului ocupa a doua fereastra: il inchidem (mozaicul o foloseste)
			try:
				self.session.pipshown = False
				del self.session.pip
			except Exception:
				pass
		for i in range(MAX):
			try:
				self["poza%d" % i].instance.setScale(1)
			except Exception:
				pass
		if not self.canale:
			self["titlu"].setText(_("Mozaic"))
			self["gol0"].setText(_("Canalul de acum nu e pe un transponder din listă (fișier, IPTV sau niciun canal)."))
			self._pune("gol0", (0, 0, self.latime, self.inaltime))
			self["video1"].hide()
			self["video0"].hide()
			return
		self.deseneaza()
		self.ceas.start(500, False)

	def deseneaza(self):
		"""pune celulele paginii celulei alese; pornesc canalul ales (sunet) si a doua fereastra"""
		self.geo = M.geometrie(self.latime, self.inaltime, self.pe)
		n = len(self.canale)
		p = M.paginaIndexului(self.ales, self.pe)
		celule = M.celulelePaginii(p, self.pe, n)
		self["titlu"].setText(_("Mozaic: %d canale pe transponder") % n)
		self["pagina"].setText(_("Pagina %d din %d") % (p + 1, M.pagini(n, self.pe)))
		for k in range(MAX):
			vizibil = k < len(celule)
			for nume in ("fundal", "poza", "nume", "program", "gol"):
				w = self["%s%d" % (nume, k)]
				if vizibil:
					w.show()
				else:
					w.hide()
			if not vizibil:
				continue
			g = self.geo[k]
			i = celule[k]
			ref, nume_canal = self.canale[i]
			self._pune("fundal%d" % k, g["chenar"])
			self._pune("poza%d" % k, g["video"])
			self._pune("gol%d" % k, g["video"])
			x, y, l, h = g["eticheta"]
			self._pune("nume%d" % k, (x + 10, y + 4, l - 20, h // 2))
			self._pune("program%d" % k, (x + 10, y + 4 + h // 2, l - 20, h // 2 - 4))
			self["nume%d" % k].setText(u"%d  %s" % (i + 1, nume_canal))
			self["program%d" % k].setText(M.emisiuneaDeAcum(ref))
			self.arataPoza(k, ref)
		self.alegeCelula()

	def arataPoza(self, k, ref):
		if M.pozaExista(ref):
			try:
				self["poza%d" % k].instance.setPixmapFromFile(M.calePoza(ref))
				self["poza%d" % k].show()
				self["gol%d" % k].setText("")
				return
			except Exception:
				pass
		self["poza%d" % k].hide()
		self["gol%d" % k].setText(_("imaginea apare în câteva secunde"))

	def _celula(self, i):
		"""locul pe pagina (0..pe-1) al canalului i, sau None daca nu e pe pagina de acum"""
		p = M.paginaIndexului(self.ales, self.pe)
		return (i - p * self.pe) if M.paginaIndexului(i, self.pe) == p else None

	def alegeCelula(self):
		k = self._celula(self.ales)
		g = self.geo[k]
		x, y, l, h = g["chenar"]
		self._pune("selectie", (x - 4, y - 4, l + 8, h + 8))
		self["selectie"].show()
		self._pune("video0", g["video"])
		self["video0"].show()
		ref = self.canale[self.ales][0]
		if self.pornit != ref:
			self._zap(ref)
		self.planificaDoi(nou=True)

	# ---------------------------------------------------------------- a doua fereastra si pozele

	def planificaDoi(self, nou=False):
		n = len(self.canale)
		celule = M.celulelePaginii(M.paginaIndexului(self.ales, self.pe), self.pe, n)
		if nou:
			self.pipCelula = None
			# fara poze din a doua fereastra: o runda pe decodorul 0 prin canalele paginii fara poza
			# o singura data pe (pagina, asezare): altfel canalele fara poza (negre, nedecriptate) ar intoarce runda la nesfarsit
			cheie = (M.paginaIndexului(self.ales, self.pe), self.pe)
			if self.metoda is None and self.pe > 2 and cheie not in self.rundeFacute:
				self.rundeFacute.add(cheie)
				self.runda = [i for i in celule if i != self.ales and not M.pozaExista(self.canale[i][0])]
		if not self.doi:
			self.opresteDoi()
			return
		celule = [i for i in celule if not self._criptat(i) and self.incercari.get("2:" + self.canale[i][0], 0) < INCERCARI]
		urm = M.urmatoareaDeVizitat(celule, (self.ales,), self.pipCelula)
		if urm is None:
			self.opresteDoi()
			return
		if self.pe == 2 or self.metoda is None:
			# pe 2 amandoua vii; fara poze din a doua fereastra, ea sta pe celula urmatoare celei alese
			urm = M.urmatoareaDeVizitat(celule, (self.ales,), self.ales)
		self.pornesteDoi(urm)

	def _criptat(self, i):
		if i not in self.cript:
			self.cript[i] = M.criptat(self.canale[i][0])
		return self.cript[i]

	def pornesteDoi(self, i):
		import time
		k = self._celula(i)
		if k is None:
			return
		ref = self.canale[i][0]
		self._pune("video1", self.geo[k]["video"])
		self["video1"].show()
		self.pipCelula = i
		if self.pipRef == ref and self.pip is not None:
			return
		self.opresteServiciulDoi()
		try:
			s = eServiceCenter.getInstance().play(eServiceReference(ref))
			if s and not s.setTarget(1):
				s.start()
				self.pip = s
				self.pipRef = ref
				self.pipPornit = time.time()
				return
		except Exception as e:
			print("[HdsMozaic] a doua fereastra: %s" % e)
		self.doi = False
		self["video1"].hide()

	def opresteServiciulDoi(self):
		if self.pip is not None:
			try:
				self.pip.stop()
			except Exception:
				pass
		self.pip = None
		self.pipRef = None

	def opresteDoi(self):
		self.opresteServiciulDoi()
		self.pipCelula = None
		self["video1"].hide()

	def tic(self):
		"""la 0,5 s: poza celulei de pe a doua fereastra dupa PE_CELULA_S, apoi celula urmatoare; runda pe decodorul 0"""
		import time
		acum = time.time()
		if self.firPoza is not None and self.firPoza.is_alive():
			return
		if self.firPoza is not None:
			self.firPoza = None
			self.reimprospateaza()
			if self.inRunda:
				self.inRunda = False
				self.urmatorulDinRunda()
				return
			if self.pe > 2 and self.metoda:
				self.planificaDoi()
			return
		if self.runda or self.inRunda:
			if self.inRunda and acum - self.pornitLa >= M.RUNDA_UNU_S:
				if self.areVideo and self._maiIncearca(self.pornit):
					self._pozaDecodor0()
				elif acum - self.pornitLa >= M.RUNDA_UNU_S + 4:
					# fara imagine (fara semnal, nedecriptat): canalul urmator din runda
					self.inRunda = False
					self.urmatorulDinRunda()
			elif not self.inRunda:
				self.urmatorulDinRunda()
			return
		if self.pip is not None and self.pe > 2 and self.metoda and acum - self.pipPornit >= M.PE_CELULA_S:
			self._maiIncearca("2:" + (self.pipRef or ""))
			if not M.aDouaFereastraArata():
				# fara imagine in a doua fereastra (SF8008, 14.11): fara captura, mai departe
				self.planificaDoi()
			elif self._paza():
				ref, k = self.pipRef, self._celula(self.pipCelula)
				if k is not None:
					self.firPoza = threading.Thread(target=M.pozaFereastraDoi,
						args=(ref, self.geo[k]["video"], self.latime, self.metoda), name="HdsMozaic")
					self.firPoza.start()
		elif self.pornit and self.areVideo and acum - self.pornitLa >= M.PE_CELULA_S + 3 and not M.pozaExista(self.pornit) and self._maiIncearca(self.pornit):
			# canalul cu sunet isi lasa si el poza (folosita cand pleci de pe el)
			self._pozaDecodor0()

	def _paza(self):
		try:
			from Plugins.Extensions.HdsWebControl import captura_sigura as P
			ce, _motiv = P.decide("video")
			if ce != "da":
				return False
			P.incepeVideo()
		except Exception:
			pass
		return True

	def _pozaDecodor0(self):
		if self._paza():
			self.firPoza = threading.Thread(target=M.pozaDecodor0, args=(self.pornit,), name="HdsMozaic")
			self.firPoza.start()

	def urmatorulDinRunda(self):
		"""pe placile fara poze din a doua fereastra: decodorul 0 trece pe canalul urmator fara poza (fara sunet stabil cat
		dureaza runda), apoi revine pe celula aleasa"""
		import time
		k_ales = self._celula(self.ales)
		while self.runda:
			i = self.runda.pop(0)
			k = self._celula(i)
			if k is None:
				continue
			ref = self.canale[i][0]
			self._pune("video0", self.geo[k]["video"])
			self.inRunda = True
			self._zap(ref)
			return
		self.inRunda = False
		if k_ales is not None:
			self.alegeCelula()

	def reimprospateaza(self):
		n = len(self.canale)
		celule = M.celulelePaginii(M.paginaIndexului(self.ales, self.pe), self.pe, n)
		for k, i in enumerate(celule):
			self.arataPoza(k, self.canale[i][0])

	# ---------------------------------------------------------------- tastele

	def _opresteRunda(self):
		if self.runda or self.inRunda:
			self.runda = []
			self.inRunda = False

	def mutaSel(self, directie):
		if not self.canale:
			return
		self._opresteRunda()
		vechi = M.paginaIndexului(self.ales, self.pe)
		self.ales = M.muta(self.ales, directie, len(self.canale), self.pe)
		if M.paginaIndexului(self.ales, self.pe) != vechi:
			self.opresteDoi()
			self.deseneaza()
		else:
			self.alegeCelula()

	def pagina(self, pas):
		if not self.canale:
			return
		self._opresteRunda()
		self.ales = M.paginaVecina(self.ales, pas, len(self.canale), self.pe)
		self.opresteDoi()
		self.deseneaza()

	def asezare(self, a):
		if not self.canale:
			return
		self._opresteRunda()
		M.tineMinteAsezarea(a)
		self.aleasa = a
		self.pe = M.asezareEfectiva(a, len(self.canale))
		self.opresteDoi()
		self.deseneaza()

	def _ecranIntreg(self):
		self._pune("video0", (0, 0, self.latime, self.inaltime))

	def peTotEcranul(self):
		"""canalul ales ramane pornit (fara zap nou), pe tot ecranul; intra in istoric si ramane ultimul canal, ca un zap"""
		if not self.canale:
			self.close()
			return
		ref = self.canale[self.ales][0]
		if self.pornit != ref:
			self.session.nav.playService(eServiceReference(ref))
		if self.vechi is None or ref != M.curata(self.vechi.toString()):
			sl = getattr(self.infobar, "servicelist", None)
			try:
				sl.addToHistory(eServiceReference(ref))
				sl.saveChannel(eServiceReference(ref))
			except Exception as e:
				print("[HdsMozaic] istoricul: %s" % e)
		self.close()

	def inapoi(self):
		if self.vechi is not None and self.pornit is not None and self.pornit != M.curata(self.vechi.toString()):
			self.session.nav.playService(self.vechi)
		self.close()

	def laInchidere(self):
		self.ceas.stop()
		self.opresteDoi()
		self._ecranIntreg()
