# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMouseUsb.py: mouse-ul pus direct in receptor (USB, receptorul unui mouse fara fir, touchpad-ul unei tastaturi).
# lib/driver/rcinput.cpp recunoaste mouse-ul dupa ce stie sa trimita (REL_X, REL_Y, BTN_LEFT), iar eRCMapper
# (lib/driver/rcmapper.cpp) aduna miscarea, rotita si butoanele pana la EV_SYN, le pune intr-o coada si anunta prin
# mouseEvent; getMouse() da pachetele (dx, dy, rotita, butoane) si goleste coada. Aici:
# - cursorul: o fereastra mica (EcranCursor: sageata alba cu contur inchis, data/hds-cursor-mouse.png) deasupra
#   tuturor ecranelor (zPosition ZPOZITIE), cat sageata de mare (eWidget.setShapeFromPixmap: in jurul ei se vad
#   ecranele de dedesubt), mutata la miscare si ascunsa singura dupa ASCUNDE_MS fara miscare si fara clic. In standby
#   nu apare si nu trimite nimic;
# - gesturile merg la locul cursorului prin Components/HdsMouseEcran.MouseEcran, aceleasi ca in panoul web: stanga =
#   clic la ridicarea butonului (alege; pe randul ales, la dublu clic sau intr-un meniu = OK; in setari doi pasi),
#   tinut si tras = trasul pe bara de derulare a listei; dreapta = IESIRE si mijloc (clic pe rotita) = MENIU, la
#   apasare; rotita = un rand pe pas, iar pasii adunati cat trece ROTITA_MS de la trimiterea de dinainte (o rotire
#   repede) = o pagina (MouseEcran.rotita);
# - pornit singur: porneste() se cheama la pornirea barei (Screens/InfoBar.py); un mouse pus si la cald trece prin
#   aceeasi cale (eInputDeviceInit urmareste /dev/input), fara nicio setare. Cu un binar enigma2 mai vechi (fara
#   getMouse) modulul nu face nimic.
# Modulul nu importa enigma2 la incarcare: CititorMouse se probeaza pe PC cu pachete false si un MouseEcran fals.
import time

ASCUNDE_MS = 3000       # cursorul se ascunde dupa atat timp fara miscare si fara clic
GOLIRE_MS = 15          # pachetele se iau din coada C++ dupa atat timp de la primul (pana atunci eRCMapper le aduna)
ROTITA_MS = 80          # pasii rotitei veniti in acest timp de la trimiterea de dinainte se trimit impreuna
PRAG_TRAS = 8           # pixeli: mai mult de atat cu butonul stang tinut = tras, nu clic
DUBLU_CLIC_S = 0.45     # al doilea clic in atat timp ...
DUBLU_CLIC_PX = 12      # ... si la cel mult atatia pixeli de primul = dublu clic
# viteza (|dx| + |dy| intr-un pachet, in unitatile mouse-ului) -> inmultitorul miscarii: incet = precis, repede = departe
ACCELERARE = ((6, 1.0), (20, 1.6), (None, 2.2))
VARF = 3                # varful sagetii in imagine (pixeli de la stanga si de sus; conturul sta in jurul lui)
MARIME_CURSOR = (32, 48)
ZPOZITIE = 100
IMAGINE = "hds-cursor-mouse.png"
STANGA, DREAPTA, MIJLOC = 1, 2, 4


def jurnal(text):
	print("[HdsMouseUsb] %s" % text)


class CititorMouse(object):
	"""Pachetele mouse-ului -> locul cursorului si gesturile. mouse: un obiect cu gest(fel, x, y, ...) (MouseEcran);
	marime: (latime, inaltime) ecranului enigma2; ceas: secunde. Cursorul porneste din mijlocul ecranului."""

	def __init__(self, mouse, marime=(1920, 1080), ceas=time.monotonic):
		self.mouse = mouse
		self.w, self.h = marime
		self.ceas = ceas
		self.x, self.y = self.w // 2, self.h // 2
		self.butoane = 0
		self._apasat = None             # (x0, y0): unde s-a apasat butonul stang
		self._tras = False
		self._ultimClic = (-1000.0, 0, 0)
		self.rotita = 0                 # pasii neadusi inca (> 0 = in jos, spre utilizator)

	def misca(self, dx, dy):
		viteza = abs(dx) + abs(dy)
		k = 1.0
		for prag, k in ACCELERARE:
			if prag is None or viteza < prag:
				break
		self.x = min(max(int(round(self.x + dx * k)), 0), self.w - 1)
		self.y = min(max(int(round(self.y + dy * k)), 0), self.h - 1)

	def _gest(self, fel, **arg):
		try:
			return self.mouse.gest(fel, **arg)
		except Exception as e:
			jurnal("gestul %s a cazut: %r" % (fel, e))
			return None

	def pachet(self, dx, dy, roti, butoane):
		"""Un pachet: intai miscarea (si trasul, cu stanga tinut), apoi butoanele schimbate, apoi rotita (adunata in
		self.rotita; o trimite trimiteRotita)."""
		if dx or dy:
			self.misca(dx, dy)
			if self.butoane & STANGA and self._apasat is not None:
				x0, y0 = self._apasat
				if self._tras or abs(self.x - x0) > PRAG_TRAS or abs(self.y - y0) > PRAG_TRAS:
					self._gest("drag", x=self.x, y=self.y, x0=x0, y0=y0, nou=not self._tras)
					self._tras = True
		schimbate = butoane ^ self.butoane
		self.butoane = butoane
		if schimbate & STANGA:
			if butoane & STANGA:
				self._apasat = (self.x, self.y)
				self._tras = False
			else:
				self._ridicare()
		if schimbate & DREAPTA and butoane & DREAPTA:
			self._gest("dreapta", x=self.x, y=self.y)
		if schimbate & MIJLOC and butoane & MIJLOC:
			self._gest("mijloc", x=self.x, y=self.y)
		if roti:
			# REL_WHEEL > 0 = rotita impinsa spre ecran = in sus; MouseEcran vrea pasi > 0 = in jos
			self.rotita -= roti

	def _ridicare(self):
		tras, self._tras = self._tras, False
		apasat, self._apasat = self._apasat, None
		if tras:
			return self._gest("dragend", x=self.x, y=self.y)
		if apasat is None:
			return None
		acum = self.ceas()
		t, ux, uy = self._ultimClic
		if acum - t < DUBLU_CLIC_S and abs(self.x - ux) <= DUBLU_CLIC_PX and abs(self.y - uy) <= DUBLU_CLIC_PX:
			clicuri = 2
			self._ultimClic = (-1000.0, 0, 0)   # al treilea clic incepe alt dublu clic
		else:
			clicuri = 1
			self._ultimClic = (acum, self.x, self.y)
		return self._gest("clic", x=self.x, y=self.y, clicuri=clicuri)

	def trimiteRotita(self):
		"""Pasii adunati, deodata (3 sau mai multi = o pagina in MouseEcran.rotita)."""
		pasi, self.rotita = self.rotita, 0
		if pasi:
			return self._gest("rotita", x=self.x, y=self.y, pasi=pasi)
		return None


def _clasaCursor():
	from Screens.Screen import Screen
	from Components.Pixmap import Pixmap

	class EcranCursor(Screen):
		skin = """<screen name="EcranCursor" position="0,0" size="%d,%d" flags="wfNoBorder" backgroundColor="#ff000000" zPosition="%d">
			<widget name="sageata" position="0,0" size="%d,%d" alphatest="blend" transparent="1" zPosition="1" />
		</screen>""" % (MARIME_CURSOR[0], MARIME_CURSOR[1], ZPOZITIE, MARIME_CURSOR[0], MARIME_CURSOR[1])

		def __init__(self, session):
			Screen.__init__(self, session)
			self["sageata"] = Pixmap()
			self.onLayoutFinish.append(self._imagine)

		def _imagine(self):
			from Tools.Directories import resolveFilename, SCOPE_SKIN_IMAGE
			from Tools.LoadPixmap import LoadPixmap
			p = LoadPixmap(resolveFilename(SCOPE_SKIN_IMAGE, IMAGINE))
			if p is not None:
				self["sageata"].instance.setPixmap(p)
				# fereastra acopera numai sageata (eWidget.setShapeFromPixmap): in jur se vad ecranele de dedesubt; un
				# fundal transparent ar arata imaginea video (gaura in meniu), nu meniul
				if hasattr(self.instance, "setShapeFromPixmap"):
					self.instance.setShapeFromPixmap(p)
			else:
				jurnal("lipseste imaginea cursorului %s" % IMAGINE)

	return EcranCursor


class MouseUsb(object):
	"""Legatura cu eRCMapper si cu ecranul: coada C++ -> CititorMouse -> cursorul si MouseEcran."""

	def __init__(self, session, mapper):
		from enigma import eTimer
		from Components.HdsMouseEcran import MouseEcran, marimeEcran
		self.session = session
		self.mapper = mapper
		self.cititor = CititorMouse(MouseEcran(self._ecranCurent), marimeEcran())
		self.cursor = None
		self._vizibil = False
		self.tGolire = eTimer()
		self.tGolire.callback.append(self.goleste)
		self.tAscunde = eTimer()
		self.tAscunde.callback.append(self.ascunde)
		self.tRotita = eTimer()
		self.tRotita.callback.append(self.laRotita)
		mapper.mouseEvent.get().append(self.anunt)
		jurnal("pornit (mouse-ul USB se recunoaste singur, si la cald)")

	def _ecranCurent(self):
		return getattr(self.session, "current_dialog", None)

	@staticmethod
	def _inStandby():
		try:
			from Screens import Standby
			return Standby.inStandby is not None
		except Exception:
			return False

	def anunt(self, _numar):
		if not self.tGolire.isActive():
			self.tGolire.start(GOLIRE_MS, True)

	def goleste(self):
		try:
			pachete = self.mapper.getMouse()
		except Exception as e:
			jurnal("getMouse a cazut: %r" % (e,))
			return
		if not pachete:
			return
		if self._inStandby():
			# in standby nimic nu se trimite; butoanele se tin minte, ca o ridicare de dupa trezire sa nu fie un clic
			self.cititor.rotita = 0
			self.cititor.butoane = pachete[-1][3]
			self.cititor._apasat = None
			self.cititor._tras = False
			self.ascunde()
			return
		# intai cursorul, ca ecranul deschis de un clic sa nu-l acopere pana la pachetul urmator
		for dx, dy, roti, butoane in pachete:
			self.cititor.pachet(dx, dy, roti, butoane)
		self.arata()
		if self.cititor.rotita and not self.tRotita.isActive():
			self.cititor.trimiteRotita()
			self.tRotita.start(ROTITA_MS, True)

	def laRotita(self):
		if self.cititor.rotita:
			self.cititor.trimiteRotita()
			self.tRotita.start(ROTITA_MS, True)

	def arata(self):
		try:
			from enigma import ePoint
			if self.cursor is None:
				self.cursor = self.session.instantiateDialog(_clasaCursor())
			self.cursor.instance.move(ePoint(self.cititor.x - VARF, self.cititor.y - VARF))
			if not self._vizibil:
				self.cursor.show()
				self._vizibil = True
		except Exception as e:
			jurnal("cursorul nu se poate arata: %r" % (e,))
		self.tAscunde.start(ASCUNDE_MS, True)

	def ascunde(self):
		self.tAscunde.stop()
		if self.cursor is not None and self._vizibil:
			self.cursor.hide()
		self._vizibil = False


_MOUSE = {}


def porneste(session):
	"""Pornit o data, din Screens/InfoBar.py. Fara eRCMapper.getMouse (binar enigma2 mai vechi): nimic."""
	if "m" in _MOUSE:
		return _MOUSE["m"]
	try:
		from enigma import eRCMapper
		mapper = eRCMapper.getInstance()
	except Exception:
		mapper = None
	if mapper is None or not hasattr(mapper, "getMouse") or not hasattr(mapper, "mouseEvent"):
		jurnal("binarul enigma2 nu da mouse-ul (fara eRCMapper.getMouse)")
		_MOUSE["m"] = None
		return None
	try:
		_MOUSE["m"] = MouseUsb(session, mapper)
	except Exception as e:
		jurnal("nu a pornit: %r" % (e,))
		_MOUSE["m"] = None
	return _MOUSE["m"]
