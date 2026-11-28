# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsScreensaver.py: screensaverele (protectia ecranului) si ecranul de alegere „Screensaver”.
# Lista, textele si datele vin din Components/HdsScreensavere.py; designul din Stitch (paralel-1111b/SSV/stitch, tema Pro).
#
# Cum se folosesc:
# - mecanismul (Screens/ScreenSaver.py, InfoBarScreenSaver) ia clasa cu ecranAles() si o deschide ca dialog
#   (session.instantiateDialog, show/hide); ceasurile merg numai cat ecranul se vede (onShow/onHide), deci ascuns nu
#   consuma nimic. Tastele le prinde mecanismul.
# - proba din ecranul de alegere sau din pagina web: deschide(session, ident) deschide screensaverul ca ecran obisnuit;
#   prima tasta il inchide (si nu trece mai departe).
#
# Regulile tuturor: blocul intreg se muta incet (pozitieDrift la 30 s; sigla canalului cu ricoseu la 2 s), litere mari,
# o singura schimbare la cateva secunde. Skinul fiecaruia e scris pentru 1920x1080 si scalat la desktop (scaledSkin),
# deci la 1280x720 e aceeasi asezare. Screensaverele sunt la fel in amandoua temele (sunt poze pe tot ecranul, fara
# ferestre); ecranul de alegere are intrarea lui in skin.xml (Clasic) si skin_pro.xml (Pro), aici ramane rezerva.

from __future__ import absolute_import

import os
import random
import re
import time

from enigma import eActionMap, ePicLoad, ePoint, eSize, eTimer, getDesktop, gRGB

from Screens.Screen import Screen
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components import HdsScreensavere as S
from Tools.ScaledSkin import scaledSkin

FUNDAL = "#00050710"
TEXT = "#00F2F4F8"
TEXT2 = "#00C9D2E3"
ETICHETA = "#00AEB9CC"
BRAND = "#00374EA1"
GALBEN = "#00F5B83D"
VERDE = "#004FD18B"
PICTOGRAME_VREME = "/usr/share/enigma2/vremea"
POZE_SSV = "/usr/share/enigma2/HDSatelit/screensaver"


def _skin(sablon):
	return _fonturiSigure(scaledSkin(sablon, 1920))


# SSV1 (0.8.0): literele foarte mari nu se deseneaza deloc. Memoria de glife a enigma2 (lib/gdi/font.cpp,
# FTC_SBit_Cache_Lookup) tine marginea de sus, latimea si avansul unei litere intr-un octet cu semn, deci o litera mai
# inalta sau mai lata de 127 px lipseste. Masurat pe HdsRegular.ttf: cifrele, ":", "-", "°", "C" si "F" incap pana la
# 175 px (la 176 cifra 0 are 128 px deasupra liniei), orice litera (cu diacritice, "M", "%") pana la 134 px. Asa se vedea
# "Ceas" (220 px: numai ":", cifrele aveau 160 px) si "Ceas, vremea si canalul" cu textul la 120 % (170 -> 204 px).
# Plafonul e marimea finala trimisa la FreeType: dupa scaledSkin (la 3840 de puncte totul se dubleaza) si dupa Marimea
# textului din skin.py (config.osd.fontscale), cu fata fontului la scara 100 (cea mai mare din teme).
PLAFON_CIFRE = 170  # probat pe SF8008 (AS234); 175 e limita masurata
PLAFON_TEXT = 128  # 134 e limita masurata pentru litere
ETICHETE_CIFRE = ("ora", "secunde", "temperatura")  # numai cifre, ":", "-", "°C"/"°F"
_FONT_ETICHETA = re.compile(r'(<widget name="(\w+)"[^>]*? font=")([^";]+);(\d+)"')


def _procentText():
	try:
		from Components.HdsMarireText import procent
		return max(1, int(procent()))
	except Exception:
		return 100


def marimeFinala(nume, marime, p=100):
	"""Marimea la care se deseneaza fontul unei etichete: Marimea textului (p) il poate micsora, dar nu il mareste peste
	marimea scrisa (casetele sunt facute pentru 100 %, iar literele sunt deja mari), si nu trece de plafon."""
	plafon = PLAFON_CIFRE if nume in ETICHETE_CIFRE else PLAFON_TEXT
	return max(1, min(marime, marime * p // 100, plafon))


def _fonturiSigure(skin, p=None):
	"""Fonturile skinului (deja scalat la ecran) scrise asa incat skin.py (_hds_scaleaza: marime * p // 100) sa ajunga la
	marimeFinala: cea mai mare valoare v cu v * p // 100 <= tinta."""
	p = _procentText() if p is None else max(1, int(p))

	def inlocuieste(m):
		tinta = marimeFinala(m.group(2), int(m.group(4)), p)
		v = tinta if p == 100 else ((tinta + 1) * 100 - 1) // p
		return '%s%s;%d"' % (m.group(1), m.group(3), max(1, v))

	return _FONT_ETICHETA.sub(inlocuieste, skin)


def _ecran():
	try:
		m = getDesktop(0).size()
		return m.width(), m.height()
	except Exception:
		return 1920, 1080


def _scara():
	return _ecran()[0] / 1920.0


def _culoare(text):
	v = int(text.lstrip("#"), 16)
	return gRGB((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF, (v >> 24) & 0xFF)


def _ecranul(continut, fundal=FUNDAL):
	# fara sigla fixa in colt: orice lucru care sta pe loc ore intregi se arde pe ecranele OLED/plasma
	return """<screen name="%%s" position="0,0" size="1920,1080" backgroundColor="%s" flags="wfNoBorder">%s
</screen>""" % (fundal, continut)


class HdsSsvBaza(Screen):
	"""Baza: blocul (widgeturile din BLOC) se muta impreuna cu pozitieDrift; ceasul secundei (REIMPROSPATARE) cheama
	actualizeaza(). Subclasele dau NUME, SKIN, BLOC, MARIME_BLOC (in 1920x1080) si actualizeaza()."""
	ALLOW_SUSPEND = True
	NUME = "HdsSsvBaza"
	SKIN = _ecranul("")
	BLOC = ()
	MARIME_BLOC = (800, 300)
	REIMPROSPATARE = 1000
	PAS_DRIFT = 30000

	def __init__(self, session, cu_taste=False):
		Screen.__init__(self, session)
		self.skinName = [self.NUME]
		self.skin = _skin(self.SKIN % self.NUME)
		self._locuri = []
		self._pas = random.randint(0, 500)
		self._cu_taste = cu_taste
		self._legat = False
		self._ceas = eTimer()
		self._ceas.callback.append(self._bate)
		self._drift = eTimer()
		self._drift.callback.append(self._muta)
		self.onLayoutFinish.append(self._asezat)
		self.onShow.append(self._pornit)
		self.onHide.append(self._oprit)
		self.onClose.append(self._inchis)

	# ---- asezarea si mutarea
	def _asezat(self):
		self._locuri = []
		for nume in self.BLOC:
			w = self.get(nume)
			inst = getattr(w, "instance", None)
			if inst is not None:
				p = inst.position()
				self._locuri.append((inst, p.x(), p.y()))
		self.asezat()
		self._muta()

	def asezat(self):
		pass

	def _muta(self):
		if not self._locuri:
			return
		self._pas += 1
		k = _scara()
		lat, inalt = _ecran()
		x, y = S.pozitieDrift(self._pas, lat, inalt, int(self.MARIME_BLOC[0] * k), int(self.MARIME_BLOC[1] * k))
		x0 = min(p[1] for p in self._locuri)
		y0 = min(p[2] for p in self._locuri)
		for inst, px, py in self._locuri:
			inst.move(ePoint(x + px - x0, y + py - y0))

	# ---- ceasurile merg numai cat se vede
	def _pornit(self):
		self._bate()
		self._ceas.start(self.REIMPROSPATARE, False)
		self._drift.start(self.PAS_DRIFT, False)
		if self._cu_taste and not self._legat:
			eActionMap.getInstance().bindAction("", -0x7FFFFFFF, self._tasta)
			self._legat = True

	def _oprit(self):
		self._ceas.stop()
		self._drift.stop()

	def _inchis(self):
		self._oprit()
		if self._legat:
			eActionMap.getInstance().unbindAction("", self._tasta)
			self._legat = False

	def _tasta(self, tasta, apasare):
		if apasare == 0:  # apasarea, nu eliberarea
			self.close()
		return 1  # tasta nu trece mai departe

	def _bate(self):
		try:
			self.actualizeaza()
		except Exception as eroare:  # un screensaver nu are voie sa cada interfata
			print("[HdsScreensaver] %s: %s" % (self.NUME, eroare))

	def actualizeaza(self):
		pass

	# ---- unelte mici pentru subclase
	def text(self, nume, valoare):
		if self[nume].getText() != valoare:
			self[nume].setText(valoare)

	def latimeBara(self, nume, latime_plina, procent):
		inst = self[nume].instance
		if inst is not None:
			k = _scara()
			inst.resize(eSize(max(1, int(latime_plina * k * max(0, min(100, procent)) / 100.0)), max(1, int(8 * k))))

	def culoareText(self, nume, culoare):
		inst = self[nume].instance
		if inst is not None:
			inst.setForegroundColor(_culoare(culoare))


# ------------------------------------------------------------------ 1. Ceas

class HdsSsvCeas(HdsSsvBaza):
	NUME = "HdsSsvCeas"
	SKIN = _ecranul("""
	<widget name="ora" position="200,300" size="760,240" font="Regular;220" foregroundColor="%s" backgroundColor="%s" transparent="1" halign="right" valign="center" noWrap="1" />
	<widget name="secunde" position="980,384" size="200,120" font="Regular;84" foregroundColor="%s" backgroundColor="%s" transparent="1" valign="center" noWrap="1" />
	<widget name="data" position="200,560" size="1000,64" font="Regular;44" foregroundColor="%s" backgroundColor="%s" transparent="1" noWrap="1" />
	<widget name="linie" position="200,644" size="560,3" backgroundColor="%s" />""" % (
		TEXT, FUNDAL, "#007E95E6", FUNDAL, TEXT2, FUNDAL, BRAND))
	BLOC = ("ora", "secunde", "data", "linie")
	MARIME_BLOC = (1000, 350)

	def __init__(self, session, cu_taste=False):
		HdsSsvBaza.__init__(self, session, cu_taste)
		self["ora"] = Label("")
		self["secunde"] = Label("")
		self["data"] = Label("")
		self["linie"] = Label("")

	def actualizeaza(self):
		t = time.time()
		self.text("ora", S.textOra(t))
		self.text("secunde", time.strftime(":%S", time.localtime(t)))
		self.text("data", S.textData(t))


# ------------------------------------------------------------------ 2. Vremea

class HdsSsvVremea(HdsSsvBaza):
	NUME = "HdsSsvVremea"
	REIMPROSPATARE = 5000
	SKIN = _ecranul("""
	<widget name="oras" position="160,140" size="900,64" font="Regular;48" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="pictograma" position="160,230" size="200,200" alphatest="blend" scale="1" />
	<widget name="temperatura" position="380,210" size="560,240" font="Regular;200" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" valign="center" noWrap="1" />
	<widget name="stare" position="160,460" size="1100,56" font="Regular;40" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="ora" position="1240,140" size="460,110" font="Regular;96" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" halign="right" noWrap="1" />
	<widget name="data" position="1100,260" size="600,52" font="Regular;36" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" halign="right" noWrap="1" />
	<widget name="zi0" position="160,600" size="440,52" font="Regular;38" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="poza0" position="160,664" size="110,110" alphatest="blend" scale="1" />
	<widget name="grade0" position="290,680" size="320,80" font="Regular;56" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" valign="center" noWrap="1" />
	<widget name="zi1" position="700,600" size="440,52" font="Regular;38" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="poza1" position="700,664" size="110,110" alphatest="blend" scale="1" />
	<widget name="grade1" position="830,680" size="320,80" font="Regular;56" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" valign="center" noWrap="1" />
	<widget name="zi2" position="1240,600" size="440,52" font="Regular;38" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="poza2" position="1240,664" size="110,110" alphatest="blend" scale="1" />
	<widget name="grade2" position="1370,680" size="320,80" font="Regular;56" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" valign="center" noWrap="1" />
	<widget name="actualizat" position="1100,800" size="600,40" font="Regular;28" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" halign="right" noWrap="1" />""" % dict(
		t=TEXT, t2=TEXT2, e=ETICHETA, f=FUNDAL))
	BLOC = ("oras", "pictograma", "temperatura", "stare", "ora", "data", "zi0", "poza0", "grade0", "zi1", "poza1",
		"grade1", "zi2", "poza2", "grade2", "actualizat")
	MARIME_BLOC = (1540, 700)

	def __init__(self, session, cu_taste=False):
		HdsSsvBaza.__init__(self, session, cu_taste)
		for n in ("oras", "temperatura", "stare", "ora", "data", "actualizat", "zi0", "grade0", "zi1", "grade1", "zi2", "grade2"):
			self[n] = Label("")
		for n in ("pictograma", "poza0", "poza1", "poza2"):
			self[n] = Pixmap()
		self._poze = {}

	def _poza(self, nume, cale):
		if self._poze.get(nume) == cale:
			return
		self._poze[nume] = cale
		if cale and os.path.isfile(cale):
			self[nume].instance.setPixmapFromFile(cale)
			self[nume].show()
		else:
			self[nume].hide()

	def actualizeaza(self):
		from Components import HdsVremea as V
		t = time.time()
		self.text("ora", S.textOra(t))
		self.text("data", S.textData(t, cu_anul=False))
		try:
			d = V.date() or {}
		except Exception:
			d = {}
		unitate = "C"
		try:
			unitate = V.setari().get("unitate", "C")
		except Exception:
			pass
		if not d.get("oras"):
			self.text("oras", _("Vremea"))
			self.text("temperatura", "")
			self.text("stare", _("Se încarcă vremea. Fără internet nu se poate afla."))
			return
		self.text("oras", d["oras"])
		self.text("temperatura", V.textTemperatura(d.get("temperatura"), unitate))
		self.text("stare", _(d.get("stare") or ""))
		self._poza("pictograma", d.get("pictograma"))
		numeZile = (_("Azi"), _("Mâine"), _("Poimâine"))
		for i, z in enumerate((d.get("zile") or [])[:3]):
			self.text("zi%d" % i, numeZile[i])
			mn, mx = z.get("min"), z.get("max")
			self.text("grade%d" % i, "%s / %s" % (V.textTemperatura(mx, unitate) if mx is not None else "-",
				V.textTemperatura(mn, unitate) if mn is not None else "-"))
			if z.get("cod") is not None:
				self._poza("poza%d" % i, PICTOGRAME_VREME + "/" + V._stare(z["cod"])[1] + ".png")
		cand = d.get("actualizat")
		self.text("actualizat", (_("Actualizat la %s") % S.textOra(cand)) if cand else "")


# ------------------------------------------------------------------ 3. Ce urmeaza pe canal

class HdsSsvUrmeaza(HdsSsvBaza):
	NUME = "HdsSsvUrmeaza"
	REIMPROSPATARE = 10000
	SKIN = _ecranul("""
	<widget name="sigla" position="160,150" size="220,132" alphatest="blend" scale="1" />
	<widget name="canal" position="400,170" size="900,90" font="Regular;64" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" valign="center" noWrap="1" />
	<widget name="ora" position="1300,170" size="400,90" font="Regular;80" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" halign="right" valign="center" noWrap="1" />
	<widget name="acum" position="160,330" size="1540,90" font="Regular;64" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="baraFundal" position="160,440" size="900,8" backgroundColor="#00222A40" />
	<widget name="bara" position="160,440" size="900,8" backgroundColor="%(b)s" />
	<widget name="interval" position="1090,422" size="610,48" font="Regular;36" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="ora1" position="160,520" size="200,64" font="Regular;46" foregroundColor="%(g)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="titlu1" position="380,520" size="1320,64" font="Regular;46" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="ora2" position="160,600" size="200,64" font="Regular;46" foregroundColor="%(g)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="titlu2" position="380,600" size="1320,64" font="Regular;46" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="ora3" position="160,680" size="200,64" font="Regular;46" foregroundColor="%(g)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="titlu3" position="380,680" size="1320,64" font="Regular;46" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />""" % dict(
		t=TEXT, t2=TEXT2, e=ETICHETA, f=FUNDAL, b=BRAND, g=GALBEN))
	BLOC = ("sigla", "canal", "ora", "acum", "baraFundal", "bara", "interval", "ora1", "titlu1", "ora2", "titlu2", "ora3", "titlu3")
	MARIME_BLOC = (1540, 600)

	def __init__(self, session, cu_taste=False):
		HdsSsvBaza.__init__(self, session, cu_taste)
		for n in ("canal", "ora", "acum", "interval", "ora1", "titlu1", "ora2", "titlu2", "ora3", "titlu3"):
			self[n] = Label("")
		self["sigla"] = Pixmap()
		self["bara"] = Label("")
		self["baraFundal"] = Label("")
		self._sigla = None

	def actualizeaza(self):
		from enigma import eEPGCache
		from ServiceReference import ServiceReference
		self.text("ora", S.textOra())
		ref = self.session.nav.getCurrentlyPlayingServiceOrGroup()
		if ref is None:
			self.text("canal", _("Niciun canal"))
			return
		refs = ref.toString()
		self.text("canal", ServiceReference(ref).getServiceName().replace("\x86", "").replace("\x87", ""))
		if self._sigla != refs:
			self._sigla = refs
			try:
				from Components.Renderer.Picon import getPiconName
				cale = getPiconName(refs)
			except Exception:
				cale = ""
			if cale:
				self["sigla"].instance.setPixmapFromFile(cale)
				self["sigla"].show()
			else:
				self["sigla"].hide()
		ev = eEPGCache.getInstance().lookupEvent(["BDT", (refs, 0, -1, 720)]) or []
		ev = [e for e in ev if e and e[2]][:4]
		if not ev:
			self.text("acum", _("Ghidul nu are emisiuni pentru acest canal."))
			self.text("interval", "")
			self.latimeBara("bara", 900, 0)
			for i in (1, 2, 3):
				self.text("ora%d" % i, "")
				self.text("titlu%d" % i, "")
			return
		inceput, durata, titlu = ev[0]
		self.text("acum", _("Acum: %s") % titlu)
		self.text("interval", "%s - %s" % (S.textOra(inceput), S.textOra(inceput + durata)))
		self.latimeBara("bara", 900, 100.0 * (time.time() - inceput) / max(1, durata))
		for i in (1, 2, 3):
			if i < len(ev):
				self.text("ora%d" % i, S.textOra(ev[i][0]))
				self.text("titlu%d" % i, ev[i][2])
			else:
				self.text("ora%d" % i, "")
				self.text("titlu%d" % i, "")


# ------------------------------------------------------------------ 4. Galeria de poze

class HdsSsvGalerie(HdsSsvBaza):
	NUME = "HdsSsvGalerie"
	REIMPROSPATARE = 20000
	PAS_DRIFT = 20000
	SKIN = _ecranul("""
	<widget name="poza" position="0,0" size="1920,1080" alphatest="off" zPosition="0" />
	<widget name="banda" position="0,900" size="1920,180" backgroundColor="#80000000" zPosition="1" />
	<widget name="ora" position="96,912" size="420,120" font="Regular;100" foregroundColor="%(t)s" backgroundColor="#80000000" transparent="1" valign="center" noWrap="1" zPosition="2" />
	<widget name="data" position="540,940" size="700,64" font="Regular;40" foregroundColor="%(t2)s" backgroundColor="#80000000" transparent="1" valign="center" noWrap="1" zPosition="2" />
	<widget name="cate" position="1240,940" size="584,64" font="Regular;30" foregroundColor="%(e)s" backgroundColor="#80000000" transparent="1" halign="right" valign="center" noWrap="1" zPosition="2" />
	<widget name="fara" position="160,400" size="1600,200" font="Regular;44" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" halign="center" valign="center" zPosition="2" />""" % dict(
		t=TEXT, t2=TEXT2, e=ETICHETA, f=FUNDAL), fundal="#00000000")
	BLOC = ()

	def __init__(self, session, cu_taste=False):
		HdsSsvBaza.__init__(self, session, cu_taste)
		self["poza"] = Pixmap()
		self["banda"] = Label("")
		for n in ("ora", "data", "cate", "fara"):
			self[n] = Label("")
		self._poze = None
		self._ale_omului = False
		self._i = -1
		self._incarcator = ePicLoad()
		try:
			self._incarcator.PictureData.get().append(self._gata)
		except AttributeError:
			self._legatura = self._incarcator.PictureData.connect(self._gata)
		self._ceasOra = eTimer()
		self._ceasOra.callback.append(self._ora)
		self.onShow.append(lambda: self._ceasOra.start(10000, False))
		self.onHide.append(self._ceasOra.stop)

	def asezat(self):
		lat, inalt = _ecran()
		self._incarcator.setPara((lat, inalt, 1, 1, False, 1, "#00000000"))

	def _muta(self):
		pass  # poza se schimba la 20 s; ora sare intre stanga si dreapta la fiecare poza (_gata)

	def _ora(self):
		self.text("ora", S.textOra())
		self.text("data", S.textData(cu_anul=False))

	def actualizeaza(self):
		self._ora()
		if self._poze is None:
			self._poze = S.cautaPoze()
			self._ale_omului = bool(self._poze)
			if not self._poze:
				self._poze = S.pozeNoastre()
			random.shuffle(self._poze)
		if not self._poze:
			self["poza"].hide()
			self.text("fara", _("Pune poze într-un dosar „Poze” pe stick sau pe disc și apar aici singure."))
			return
		self._i = (self._i + 1) % len(self._poze)
		self._incarcator.startDecode(self._poze[self._i])

	def _gata(self, informatii=None):
		ptr = self._incarcator.getData()
		if ptr is None:
			return
		self["poza"].instance.setPixmap(ptr)
		self["poza"].show()
		self.text("fara", "")
		eticheta = _("Pozele tale") if self._ale_omului else _("Imaginile HD Satelit")
		self.text("cate", _("%(ce)s · %(i)d din %(n)d") % dict(ce=eticheta, i=self._i + 1, n=len(self._poze)))
		# banda cu ora se muta cu fiecare poza: jos si sus pe rand, ora stanga si dreapta, cativa pixeli in plus
		# (marginea benzii nu ramane in acelasi loc ore intregi)
		k = _scara()
		dx = 0 if (self._i // 2) % 2 == 0 else int(700 * k)
		dy = int(((self._i * 7) % 5) * 6 * k)
		sus = self._i % 2 == 1
		baza_y = (0 if sus else 900) + (dy if sus else -dy)
		self["banda"].instance.move(ePoint(0, int(baza_y * k)))
		for nume, (x, y) in (("ora", (96, 12)), ("data", (540, 40)), ("cate", (1240, 40))):
			self[nume].instance.move(ePoint(int(x * k) + (dx if nume != "cate" else -dx), int((baza_y + y) * k)))


# ------------------------------------------------------------------ 5. Stiri HD Satelit

_STIRI = None


def _stiri():
	global _STIRI
	if _STIRI is None:
		_STIRI = S.Stiri()
	return _STIRI


class HdsSsvStiri(HdsSsvBaza):
	NUME = "HdsSsvStiri"
	REIMPROSPATARE = 12000
	SKIN = _ecranul("""
	<widget name="eticheta" position="160,240" size="900,48" font="Regular;34" foregroundColor="%(g)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="ora" position="1240,200" size="460,110" font="Regular;96" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" halign="right" noWrap="1" />
	<widget name="titlu" position="160,340" size="1540,190" font="Regular;64" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" valign="top" />
	<widget name="cand" position="160,560" size="900,52" font="Regular;36" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="cate" position="1300,560" size="400,52" font="Regular;36" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" halign="right" noWrap="1" />""" % dict(
		t=TEXT, t2=TEXT2, e=ETICHETA, f=FUNDAL, g=GALBEN))
	BLOC = ("eticheta", "ora", "titlu", "cand", "cate")
	MARIME_BLOC = (1540, 420)

	def __init__(self, session, cu_taste=False):
		HdsSsvBaza.__init__(self, session, cu_taste)
		for n in ("eticheta", "ora", "titlu", "cand", "cate"):
			self[n] = Label("")
		self._i = -1

	def actualizeaza(self):
		self.text("ora", S.textOra())
		self.text("eticheta", _("Știri de pe hdsatelit.com"))
		titluri = _stiri().citeste()
		if not titluri:
			self.text("titlu", _("Titlurile apar aici când receptorul are internet."))
			self.text("cand", "")
			self.text("cate", "")
			return
		self._i = (self._i + 1) % len(titluri)
		titlu, cand = titluri[self._i]
		self.text("titlu", titlu)
		self.text("cand", S.textData(cand, cu_anul=False) + ", " + S.textOra(cand) if cand else "")
		self.text("cate", "%d / %d" % (self._i + 1, len(titluri)))


# ------------------------------------------------------------------ 6. Sigla canalului

class HdsSsvSigla(HdsSsvBaza):
	NUME = "HdsSsvSigla"
	REIMPROSPATARE = 30000
	PAS_DRIFT = 2000
	SKIN = _ecranul("""
	<widget name="sigla" position="0,0" size="400,240" alphatest="blend" scale="1" />
	<widget name="nume" position="0,60" size="600,120" font="Regular;72" foregroundColor="%(t)s" backgroundColor="#00000000" transparent="1" halign="center" valign="center" noWrap="1" />
	<widget name="ora" position="0,250" size="400,56" font="Regular;40" foregroundColor="%(t2)s" backgroundColor="#00000000" transparent="1" halign="center" noWrap="1" />""" % dict(
		t=TEXT, t2=TEXT2), fundal="#00000000")
	BLOC = ("sigla", "nume", "ora")
	MARIME_BLOC = (600, 310)

	def __init__(self, session, cu_taste=False):
		HdsSsvBaza.__init__(self, session, cu_taste)
		self["sigla"] = Pixmap()
		self["nume"] = Label("")
		self["ora"] = Label("")
		self._xy = None
		self._d = None
		self._ref = None

	def _muta(self):
		if not self._locuri:
			return
		k = _scara()
		lat, inalt = _ecran()
		lb, ib = int(self.MARIME_BLOC[0] * k), int(self.MARIME_BLOC[1] * k)
		if self._xy is None:
			self._xy = (random.randint(0, max(0, lat - lb)), random.randint(0, max(0, inalt - ib)))
			self._d = (max(1, int(6 * k)), max(1, int(4 * k)))
		x, y, dx, dy = S.pasRicoseu(self._xy[0], self._xy[1], self._d[0], self._d[1], lat, inalt, lb, ib)
		self._xy, self._d = (x, y), (dx, dy)
		for inst, px, py in self._locuri:
			inst.move(ePoint(x + px, y + py))

	def actualizeaza(self):
		from ServiceReference import ServiceReference
		self.text("ora", S.textOra())
		ref = self.session.nav.getCurrentlyPlayingServiceOrGroup()
		refs = ref.toString() if ref is not None else ""
		if refs == self._ref:
			return
		self._ref = refs
		cale = ""
		if refs:
			try:
				from Components.Renderer.Picon import getPiconName
				cale = getPiconName(refs)
			except Exception:
				cale = ""
		if cale:
			self["sigla"].instance.setPixmapFromFile(cale)
			self["sigla"].show()
			self.text("nume", "")
		else:
			self["sigla"].hide()
			self.text("nume", ServiceReference(ref).getServiceName() if ref is not None else "HD Satelit")


# ------------------------------------------------------------------ 7. Calendarul

def _calendarSkin():
	celule = []
	for c in range(7):
		celule.append('<widget name="cap%d" position="%d,250" size="100,52" font="Regular;34" foregroundColor="%s" backgroundColor="%s" transparent="1" halign="center" noWrap="1" />' % (
			c, 160 + c * 110, ETICHETA, FUNDAL))
	for r in range(6):
		for c in range(7):
			celule.append('<widget name="z%d_%d" position="%d,%d" size="100,80" font="Regular;48" foregroundColor="%s" backgroundColor="%s" transparent="1" halign="center" valign="center" noWrap="1" zPosition="2" />' % (
				r, c, 160 + c * 110, 316 + r * 90, TEXT, FUNDAL))
	return _ecranul("""
	<widget name="luna" position="160,160" size="770,72" font="Regular;56" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="azi" position="160,316" size="100,80" backgroundColor="%(b)s" zPosition="1" />
	%(celule)s
	<widget name="ora" position="1020,160" size="680,200" font="Regular;180" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="data" position="1020,370" size="680,56" font="Regular;40" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="titluLibere" position="1020,480" size="680,48" font="Regular;34" foregroundColor="%(g)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="libera0" position="1020,540" size="680,52" font="Regular;36" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="libera1" position="1020,600" size="680,52" font="Regular;36" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="libera2" position="1020,660" size="680,52" font="Regular;36" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />""" % dict(
		t=TEXT, t2=TEXT2, f=FUNDAL, b=BRAND, g=GALBEN, celule="\n\t".join(celule)))


class HdsSsvCalendar(HdsSsvBaza):
	NUME = "HdsSsvCalendar"
	REIMPROSPATARE = 20000
	SKIN = _calendarSkin()
	BLOC = ("luna", "azi", "ora", "data", "titluLibere", "libera0", "libera1", "libera2") + tuple(
		"cap%d" % c for c in range(7)) + tuple("z%d_%d" % (r, c) for r in range(6) for c in range(7))
	MARIME_BLOC = (1540, 700)

	def __init__(self, session, cu_taste=False):
		HdsSsvBaza.__init__(self, session, cu_taste)
		for n in self.BLOC:
			self[n] = Label("")
		self._zi = None

	def actualizeaza(self):
		import datetime
		self.text("ora", S.textOra())
		azi = datetime.date.today()
		if azi == self._zi:
			return
		self._zi = azi
		self.text("data", S.textData(cu_anul=False))
		self.text("luna", "%s %d" % (_(S.LUNI_TITLU[azi.month - 1]), azi.year))
		for c in range(7):
			self.text("cap%d" % c, _(S.ZILE_SCURT[c]))
		tara = S.tara()
		libere = dict(S.zileLibere(tara, azi.year))
		grila = S.grilaLunii(azi.year, azi.month)
		k = _scara()
		for r in range(6):
			for c in range(7):
				nume = "z%d_%d" % (r, c)
				zi = grila[r][c] if r < len(grila) else 0
				self.text(nume, str(zi) if zi else "")
				if not zi:
					continue
				d = datetime.date(azi.year, azi.month, zi)
				if d in libere:
					self.culoareText(nume, GALBEN)
				elif c >= 5:
					self.culoareText(nume, ETICHETA)
				else:
					self.culoareText(nume, TEXT)
				if d == azi:
					p = self[nume].instance.position()
					self["azi"].instance.move(ePoint(p.x(), p.y()))
		apropiate = S.zileLibereApropiate(tara, azi)
		self.text("titluLibere", _("Zile libere apropiate") if apropiate else "")
		for i in range(3):
			if i < len(apropiate):
				d, n = apropiate[i]
				self.text("libera%d" % i, "%d %s · %s" % (d.day, _(S.LUNI[d.month - 1]), _(n)))
			else:
				self.text("libera%d" % i, "")

	def _muta(self):
		HdsSsvBaza._muta(self)
		self._zi = None  # dupa mutare, patratul zilei de azi se pune din nou peste zi
		self.actualizeaza()


# ------------------------------------------------------------------ 8. Receptorul

class HdsSsvReceptor(HdsSsvBaza):
	NUME = "HdsSsvReceptor"
	REIMPROSPATARE = 5000
	SKIN = _ecranul("""
	<widget name="ora" position="1240,140" size="460,110" font="Regular;96" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" halign="right" noWrap="1" />
	<widget name="e0" position="160,260" size="700,48" font="Regular;34" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="v0" position="160,312" size="700,110" font="Regular;90" foregroundColor="%(v)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="e1" position="1000,260" size="700,48" font="Regular;34" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="v1" position="1000,312" size="700,110" font="Regular;90" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="e2" position="160,500" size="700,48" font="Regular;34" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="v2" position="160,552" size="700,110" font="Regular;72" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="f2" position="160,676" size="600,8" backgroundColor="#00222A40" />
	<widget name="b2" position="160,676" size="600,8" backgroundColor="%(b)s" />
	<widget name="e3" position="1000,500" size="700,48" font="Regular;34" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="v3" position="1000,552" size="700,110" font="Regular;90" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="f3" position="1000,676" size="600,8" backgroundColor="#00222A40" />
	<widget name="b3" position="1000,676" size="600,8" backgroundColor="%(b)s" />
	<widget name="inregistrare" position="160,760" size="1540,56" font="Regular;40" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />""" % dict(
		t=TEXT, t2=TEXT2, e=ETICHETA, f=FUNDAL, b=BRAND, v=VERDE))
	BLOC = ("ora", "e0", "v0", "e1", "v1", "e2", "v2", "f2", "b2", "e3", "v3", "f3", "b3", "inregistrare")
	MARIME_BLOC = (1540, 680)

	def __init__(self, session, cu_taste=False):
		HdsSsvBaza.__init__(self, session, cu_taste)
		for n in ("ora", "e0", "v0", "e1", "v1", "e2", "v2", "e3", "v3", "inregistrare", "b2", "b3", "f2", "f3"):
			self[n] = Label("")
		self._procesor = S.Procesor()

	def actualizeaza(self):
		from enigma import iFrontendInformation
		self.text("ora", S.textOra())
		self.text("e0", _("Temperatura"))
		grade = S.temperatura()
		self.text("v0", ("%d°C" % grade) if grade is not None else "-")
		self.culoareText("v0", VERDE if grade is None or grade < 65 else (GALBEN if grade < 80 else "#00FF6B5E"))
		self.text("e1", _("Procesor"))
		p = self._procesor.procent()
		self.text("v1", ("%d%%" % p) if p is not None else "-")
		self.text("e2", _("Disc liber"))
		d = S.disc()
		if d:
			self.text("v2", _("%(liber)s din %(total)s") % dict(liber=S.textOcteti(d[1]), total=S.textOcteti(d[2])))
			self.latimeBara("b2", 600, 100.0 * d[1] / d[2])
		else:
			self.text("v2", _("Fără disc"))
			self.latimeBara("b2", 600, 0)
		self.text("e3", _("Semnal"))
		semnal = None
		try:
			s = self.session.nav.getCurrentService()
			fe = s and s.frontendInfo()
			if fe:
				semnal = fe.getFrontendInfo(iFrontendInformation.signalQuality) * 100 // 65536
		except Exception:
			semnal = None
		self.text("v3", ("%d%%" % semnal) if semnal else "-")
		self.latimeBara("b3", 600, semnal or 0)
		self.text("inregistrare", self._inregistrare())

	def _inregistrare(self):
		acum = time.time()
		try:
			lista = [t for t in self.session.nav.RecordTimer.timer_list
				if t.begin > acum and not getattr(t, "disabled", False) and not getattr(t, "justplay", False)]
		except Exception:
			lista = []
		if not lista:
			return _("Nicio înregistrare programată.")
		t = min(lista, key=lambda x: x.begin)
		import datetime
		zi = datetime.date.fromtimestamp(t.begin)
		cand = _("azi") if zi == datetime.date.today() else S.textData(t.begin, cu_anul=False)
		return _("Următoarea înregistrare: %(nume)s, %(cand)s la %(ora)s") % dict(nume=t.name, cand=cand, ora=S.textOra(t.begin))


# ------------------------------------------------------------------ 9. Cer de noapte

NUMAR_STELE = 48


def _cerSkin():
	stele = "\n\t".join('<widget name="s%d" position="0,0" size="3,3" backgroundColor="#00404A60" />' % i for i in range(NUMAR_STELE))
	return _ecranul("""
	%(stele)s
	<widget name="luna" position="1440,160" size="240,240" alphatest="blend" scale="1" />
	<widget name="faza" position="1300,420" size="520,48" font="Regular;32" foregroundColor="%(e)s" backgroundColor="#00030509" transparent="1" halign="center" noWrap="1" />
	<widget name="ora" position="160,760" size="640,170" font="Regular;150" foregroundColor="%(t)s" backgroundColor="#00030509" transparent="1" noWrap="1" />
	<widget name="data" position="160,930" size="900,56" font="Regular;40" foregroundColor="%(t2)s" backgroundColor="#00030509" transparent="1" noWrap="1" />""" % dict(
		t=TEXT, t2=TEXT2, e=ETICHETA, stele=stele), fundal="#00030509")


class HdsSsvCer(HdsSsvBaza):
	NUME = "HdsSsvCer"
	REIMPROSPATARE = 3000
	SKIN = _cerSkin()
	BLOC = ("ora", "data")
	MARIME_BLOC = (900, 230)
	CULORI = ("#00404A60", "#00707C94", "#00B4BCCC", "#00E6E9F0")

	def __init__(self, session, cu_taste=False):
		HdsSsvBaza.__init__(self, session, cu_taste)
		for i in range(NUMAR_STELE):
			self["s%d" % i] = Label("")
		self["luna"] = Pixmap()
		for n in ("faza", "ora", "data"):
			self[n] = Label("")
		self._ora_stelelor = None
		self._faza = None

	def _aseazaStelele(self):
		ora = int(time.time() // 3600)
		if ora == self._ora_stelelor:
			return
		self._ora_stelelor = ora  # o data pe ora stelele si luna se muta in alte locuri
		k = _scara()
		lat, inalt = _ecran()
		r = random.Random(ora)
		lx, ly = int(r.randint(900, 1560) * k), int(r.randint(60, 300) * k)
		for nume, (x, y) in (("luna", (lx, ly)), ("faza", (lx - int(140 * k), ly + int(260 * k)))):
			inst = self[nume].instance
			if inst is not None:
				inst.move(ePoint(x, y))
		for i, (x, y, m) in enumerate(S.stele(NUMAR_STELE, lat, int(inalt * 0.7), samanta=ora)):
			inst = self["s%d" % i].instance
			if inst is not None:
				inst.move(ePoint(x, y))
				inst.resize(eSize(max(1, int(m * k)), max(1, int(m * k))))

	def actualizeaza(self):
		self._aseazaStelele()
		for _i in range(4):  # cateva stele isi schimba lumina la fiecare 3 s
			inst = self["s%d" % random.randrange(NUMAR_STELE)].instance
			if inst is not None:
				inst.setBackgroundColor(_culoare(random.choice(self.CULORI)))
				inst.invalidate()
		self.text("ora", S.textOra())
		self.text("data", S.textData(cu_anul=False))
		varsta, luminata, nume = S.fazaLunii()
		faza = int(round(varsta / S.LUNA_SINODICA * 8)) % 8
		if faza != self._faza:
			self._faza = faza
			cale = "%s/luna-%d.png" % (POZE_SSV, faza)
			if os.path.isfile(cale):
				self["luna"].instance.setPixmapFromFile(cale)
				self["luna"].show()
			else:
				self["luna"].hide()
		self.text("faza", "%s · %d%%" % (_(nume), int(round(luminata * 100))))


# ------------------------------------------------------------------ 10. Ceas, vremea si canalul (mozaicul)

def _vremeaAcum():
	"""(datele vremii, unitatea) din Components/HdsVremea.py; ({}, "C") fara ele."""
	try:
		from Components import HdsVremea as V
		d = V.date() or {}
		return d, V.setari().get("unitate", "C")
	except Exception:
		return {}, "C"


def _emisiuni(session, cate=4):
	"""(numele canalului, referinta, [(inceput, durata, titlu)]) pentru canalul care merge."""
	from enigma import eEPGCache
	from ServiceReference import ServiceReference
	ref = session.nav.getCurrentlyPlayingServiceOrGroup()
	if ref is None:
		return "", "", []
	refs = ref.toString()
	nume = ServiceReference(ref).getServiceName().replace("\x86", "").replace("\x87", "")
	ev = eEPGCache.getInstance().lookupEvent(["BDT", (refs, 0, -1, 720)]) or []
	return nume, refs, [e for e in ev if e and e[2]][:cate]


class HdsSsvMozaic(HdsSsvBaza):
	NUME = "HdsSsvMozaic"
	REIMPROSPATARE = 10000
	SKIN = _ecranul("""
	<widget name="ora" position="160,180" size="760,200" font="Regular;170" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="data" position="160,390" size="760,56" font="Regular;40" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="linieV" position="980,190" size="2,250" backgroundColor="#00222A40" />
	<widget name="oras" position="1040,180" size="660,50" font="Regular;36" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="pictograma" position="1040,244" size="130,130" alphatest="blend" scale="1" />
	<widget name="temperatura" position="1190,230" size="510,150" font="Regular;120" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" valign="center" noWrap="1" />
	<widget name="stare" position="1040,390" size="660,48" font="Regular;34" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="maine" position="1040,440" size="660,44" font="Regular;32" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="linieO" position="160,540" size="1540,2" backgroundColor="#00222A40" />
	<widget name="acum" position="160,580" size="1540,70" font="Regular;48" foregroundColor="%(t)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="baraFundal" position="160,664" size="900,8" backgroundColor="#00222A40" />
	<widget name="bara" position="160,664" size="900,8" backgroundColor="%(b)s" />
	<widget name="interval" position="1090,646" size="610,44" font="Regular;32" foregroundColor="%(e)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />
	<widget name="urmeaza" position="160,710" size="1540,56" font="Regular;36" foregroundColor="%(t2)s" backgroundColor="%(f)s" transparent="1" noWrap="1" />""" % dict(
		t=TEXT, t2=TEXT2, e=ETICHETA, f=FUNDAL, b=BRAND))
	BLOC = ("ora", "data", "linieV", "oras", "pictograma", "temperatura", "stare", "maine", "linieO", "acum", "baraFundal",
		"bara", "interval", "urmeaza")
	MARIME_BLOC = (1540, 590)

	def __init__(self, session, cu_taste=False):
		HdsSsvBaza.__init__(self, session, cu_taste)
		for n in self.BLOC:
			self[n] = Pixmap() if n == "pictograma" else Label("")
		self._pictograma = None

	def actualizeaza(self):
		self.text("ora", S.textOra())
		self.text("data", S.textData(cu_anul=False))
		d, unitate = _vremeaAcum()
		if d.get("oras"):
			from Components import HdsVremea as V
			self.text("oras", d["oras"])
			self.text("temperatura", V.textTemperatura(d.get("temperatura"), unitate))
			self.text("stare", _(d.get("stare") or ""))
			zile = d.get("zile") or []
			if len(zile) > 1 and zile[1].get("max") is not None and zile[1].get("min") is not None:
				self.text("maine", _("Mâine %(max)s / %(min)s") % dict(max=V.textTemperatura(zile[1]["max"], unitate),
					min=V.textTemperatura(zile[1]["min"], unitate)))
			cale = d.get("pictograma")
			if cale != self._pictograma and cale and os.path.isfile(cale):
				self._pictograma = cale
				self["pictograma"].instance.setPixmapFromFile(cale)
		else:
			self.text("oras", _("Vremea"))
			self.text("stare", _("Fără internet nu se poate afla."))
		nume, _refs, ev = _emisiuni(self.session, 3)
		if not ev:
			self.text("acum", (_("Acum pe %s") % nume) if nume else "")
			self.text("interval", "")
			self.text("urmeaza", _("Ghidul nu are emisiuni pentru acest canal.") if nume else "")
			self.latimeBara("bara", 900, 0)
			return
		inceput, durata, titlu = ev[0]
		self.text("acum", _("Acum pe %(canal)s: %(titlu)s") % dict(canal=nume, titlu=titlu))
		self.text("interval", "%s - %s" % (S.textOra(inceput), S.textOra(inceput + durata)))
		self.latimeBara("bara", 900, 100.0 * (time.time() - inceput) / max(1, durata))
		self.text("urmeaza", (_("Urmează: %s") % " · ".join("%s %s" % (S.textOra(e[0]), e[2]) for e in ev[1:])) if len(ev) > 1 else "")


# ------------------------------------------------------------------ lista si alegerea

CLASE = {
	"ceas": HdsSsvCeas,
	"vremea": HdsSsvVremea,
	"urmeaza": HdsSsvUrmeaza,
	"galerie": HdsSsvGalerie,
	"stiri": HdsSsvStiri,
	"sigla": HdsSsvSigla,
	"calendar": HdsSsvCalendar,
	"receptor": HdsSsvReceptor,
	"cer": HdsSsvCer,
	"mozaic": HdsSsvMozaic,
}
_pe_rand = [None]


def ecranAles(ident=None):
	"""Clasa screensaverului ales de om (sau a celui dat). „Automat”: ziua mozaicul, noaptea cerul (S.automat).
	„Pe rand”: la fiecare pornire urmatorul din lista."""
	ident = ident or S.ales()
	if ident == "automat":
		ident = S.automat()
	elif ident == "pe-rand":
		_pe_rand[0] = S.urmatorulPeRand(_pe_rand[0])
		ident = _pe_rand[0]
	return CLASE.get(ident, HdsSsvCeas)


def deschide(session, ident=None):
	"""Proba: screensaverul ca ecran obisnuit; prima tasta il inchide."""
	return session.open(ecranAles(ident), cu_taste=True)


SKIN_ALEGERE = """
<screen name="HdsScreensaverAlegere" position="48,27" size="1184,666" backgroundColor="#0D10162A" flags="wfNoBorder" title="Screensaver">
	<widget source="Title" render="Label" position="21,12" size="900,38" font="Bold;27" foregroundColor="#00F2F4F8" transparent="1" />
	<widget source="global.CurrentTime" render="Label" position="963,12" size="200,38" font="Regular;24" foregroundColor="#00C9D2E3" transparent="1" halign="right">
		<convert type="ClockToText">Format:%H:%M</convert>
	</widget>
	<eLabel position="21,59" size="1142,1" backgroundColor="#99FFFFFF" />
	<widget name="lista" position="21,76" size="440,484" itemHeight="44" font="Regular;22" scrollbarMode="showOnDemand" foregroundColor="#00F2F4F8" backgroundColor="#0D10162A" backgroundColorSelected="#00374EA1" foregroundColorSelected="#00FFFFFF" />
	<widget name="poza" position="485,76" size="678,381" alphatest="off" />
	<widget name="fara_poza" position="485,76" size="678,381" font="Regular;24" foregroundColor="#00C9D2E3" backgroundColor="#000D1120" halign="center" valign="center" zPosition="2" />
	<widget name="descriere" position="485,468" size="678,60" font="Regular;20" foregroundColor="#00C9D2E3" transparent="1" />
	<widget name="dupa" position="485,532" size="678,30" font="Regular;20" foregroundColor="#00F5B83D" transparent="1" noWrap="1" />
	<eLabel position="21,584" size="10,10" backgroundColor="#001F771F" />
	<widget source="key_green" render="Label" position="38,574" size="220,30" font="Regular;20" foregroundColor="#00F2F4F8" transparent="1" valign="center" noWrap="1" />
	<eLabel position="271,584" size="10,10" backgroundColor="#00B8A200" />
	<widget source="key_yellow" render="Label" position="288,574" size="220,30" font="Regular;20" foregroundColor="#00F2F4F8" transparent="1" valign="center" noWrap="1" />
	<widget name="stare" position="21,616" size="1142,36" font="Regular;20" foregroundColor="#00AEB9CC" transparent="1" noWrap="1" />
</screen>"""


def _configTimp():
	"""Setarea timpului de pornire a mecanismului (Screens/ScreenSaver.py, agentul RSS), daca exista."""
	try:
		from Components.config import config
	except ImportError:
		return None
	for sectiune, cheie in (("usage", "hds_protectie_dupa"), ("usage", "screenSaverStartTimer"), ("hds_radio", "protectie_dupa")):
		c = getattr(getattr(config, sectiune, None), cheie, None)
		if c is not None and hasattr(c, "handleKey"):
			return c
	return None


class HdsScreensaverAlegere(Screen):
	"""Lista cu previzualizare; OK (sau verde) il alege pe loc, galben il probeaza pe tot ecranul,
	stanga/dreapta schimba „Porneste dupa”. Fara „Salveaza”: ce alegi ramane."""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.skinName = ["HdsScreensaverAlegere"]
		self.skin = scaledSkin(SKIN_ALEGERE)
		self.setTitle(_("Screensaver"))
		from Components.Sources.StaticText import StaticText
		self["key_green"] = StaticText(_("Alege"))
		self["key_yellow"] = StaticText(_("Probează"))
		self["lista"] = MenuList([])
		self["poza"] = Pixmap()
		self["fara_poza"] = Label("")
		self["descriere"] = Label("")
		self["dupa"] = Label("")
		self["stare"] = Label("")
		self._timp = _configTimp()
		self["actiuni"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"], {
			"ok": self.alege,
			"green": self.alege,
			"yellow": self.proba,
			"cancel": self.close,
			"red": self.close,
			"left": lambda: self._schimbaTimp(-1),
			"right": lambda: self._schimbaTimp(1),
			"up": lambda: self._muta("up"),
			"down": lambda: self._muta("down"),
		}, -1)
		self.onLayoutFinish.append(self._umple)

	def _randuri(self):
		ales = S.ales()
		return [((S.nume(i) + ("   " + _("(ales)") if i == ales else "")), i) for i in S.IDURI]

	def _umple(self):
		ales = S.ales()
		self["lista"].setList(self._randuri())
		self["lista"].moveToIndex(S.IDURI.index(ales) if ales in S.IDURI else 0)
		self._arata()

	def _muta(self, directie):
		if directie == "up":
			self["lista"].up()
		else:
			self["lista"].down()
		self._arata()

	def _curent(self):
		c = self["lista"].getCurrent()
		return c[1] if c else S.IMPLICIT

	def _arata(self):
		ident = self._curent()
		self["descriere"].setText(S.descriere(ident))
		cale = S.previzualizare(ident) if ident not in ("pe-rand", "automat") else S.previzualizare(S.automat())
		if cale:
			self["poza"].instance.setPixmapFromFile(cale)
			self["poza"].show()
			self["fara_poza"].setText("")
		else:
			self["poza"].hide()
			self["fara_poza"].setText(S.nume(ident))
		if self._timp is not None:
			self["dupa"].setText(_("Pornește după: %s  (stânga / dreapta)") % self._timp.getText())
		else:
			self["dupa"].setText("")

	def _schimbaTimp(self, sens):
		if self._timp is None:
			return
		from Components.config import KEY_LEFT, KEY_RIGHT
		self._timp.handleKey(KEY_LEFT if sens < 0 else KEY_RIGHT)
		self._timp.save()
		self._arata()

	def alege(self):
		ident = self._curent()
		if S.alege(ident):
			self["stare"].setText(_("Ales: %s") % S.nume(ident))
			index = self["lista"].getSelectionIndex()
			self["lista"].setList(self._randuri())
			self["lista"].moveToIndex(index)

	def proba(self):
		deschide(self.session, self._curent())
