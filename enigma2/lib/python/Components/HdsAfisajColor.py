# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-only
# Afisaj color: aceleasi date si evenimente, cu iesire pe desktopul LCD.
# Video merge prin driver. Nu capturam si nu comprimam cadre in Python.

import os
import time

from Components import HdsAfisaj as A
from Components import HdsAfisajDate as D
from Components import HdsAfisajPersonaj as P
from Components import HdsAfisajCompat as K

DOSAR = "/usr/share/enigma2/HDSatelit/afisaj-color"
MODELE = {"vusolo4k": (480, 320), "vuuno4kse": (400, 240),
	"vuduo4k": (480, 320)}
LIVE = ("nu", "imagine", "osd")
PICON = ("nu", "singur", "nume_ora")


def _citeste(cale):
	try:
		with open(cale, "r", encoding="ascii") as f:
			return f.read(256).strip()
	except (OSError, UnicodeError):
		return ""


def _model():
	try:
		from boxbranding import getMachineBuild
		return getMachineBuild().lower()
	except ImportError:
		model = _citeste("/proc/stb/info/model").lower()
		return "vu" + model if "vu" + model in MODELE else model


def detecteaza(radacina="/proc/stb/lcd", model=None):
	"""Datele driverului au intaietate; modelul e rezerva cand lipsesc."""
	texte = [_citeste(os.path.join(radacina, n)) for n in ("xres", "yres", "bpp")]
	if all(texte):
		for baza in (16, 10):
			try:
				x, y, b = [int(t, baza) for t in texte]
			except ValueError:
				continue
			if 320 <= x <= 1920 and 180 <= y <= 1080 and b in (16, 24, 32):
				return {"latime": x, "inaltime": y, "bpp": b}
		return None
	model = (_model() if model is None else model).lower().replace(" ", "")
	marime = MODELE.get(model)
	if marime:
		return {"latime": marime[0], "inaltime": marime[1], "bpp": 32}
	return None


def _textColor(pereche, secunde=0):
	"""Textul intreg, cu diacritice; alternarea urmeaza timpul real."""
	if not pereche:
		return ""
	fel, v = pereche
	if fel in ("fix", "dreapta", "derulat", "punct"):
		return str(v)
	if fel == "bara":
		return "%d%%" % round(max(0.0, min(1.0, float(v))) * 100)
	if fel == "alternat":
		return str(v[int(secunde / 2) % len(v)]) if v else ""
	if fel == "secventa":
		for tip, text, ms in v:
			durata = ms / 1000.0 if ms else max(3.0, len(str(text)) * 0.16)
			if secunde < durata:
				return _textColor((tip, text), secunde)
			secunde -= durata
		return str(v[-1][1]) if v else ""
	if fel == "sageti":
		return A._("Vest") if v == "vest" else A._("Est")
	if fel == "inel":
		return A._("Se lucreaza")
	return ""


def textColor(pereche, secunde=0, id_data="", id_format=""):
	text = _textColor(pereche, secunde)
	# Ecranul color poate arata separatorii lipsa de pe afisajul simplu.
	ore = ("ceas.ora", "ceas.utc", "asteptare.ora", "asteptare.rec",
		"emisiune.inceput", "emisiune.sfarsit", "emisiune.interval",
		"inregistrari.urmatoarea_ora")
	doua_puncte = id_data in ore
	if id_data in ("ceas.secunde", "ceas.minutar", "ceas.cronometru",
			"redare.pozitie") and id_format == "ms":
		doua_puncte = True
	if id_data == "asteptare.ora_data":
		doua_puncte = int(secunde / 2) % 2 == 0
	if text.strip().isdigit() and len(text.strip()) in (3, 4):
		text = text.strip()
		if doua_puncte:
			return text[:-2] + ":" + text[-2:]
		if id_data == "ceas.data" or id_data == "asteptare.ora_data":
			return text[:-2] + "." + text[-2:]
	return text


# Cadre foto ale aceleiasi fete. Mastile raman numai chei de expresie.
def pozaExpresie(expresie, cadru=0, marime="480x320"):
	e = P.expresie(expresie) if isinstance(expresie, str) else expresie
	if e is None:
		return ""
	m = tuple(e.cadre[cadru % len(e.cadre)])
	stari = {P.F_DESCHISI: 0, P.F_INCHISI: 2, P.F_STANGA: 3,
		P.F_DREAPTA: 4, P.F_JOS: 5, P.F_ZAMBET: 6, P.F_VESELI: 6,
		P.F_RAS: 7, P.F_MARI: 8, P.F_CU_OCHIUL: 9, P.F_SOMN: 10,
		P.F_SOMN_Z: 11, P.F_CASCAT: 12, P.F_TRIST: 13}
	stare = stari.get(m)
	if stare is None:
		if e.id == "ameteste":
			stare = (3, 4, 5, 13)[cadru % 4]
		elif m[:2] == (P.JOS, P.JOS):
			stare = 14
		elif m[2:] == (P.OCHI_MARE, P.OCHI_MARE):
			stare = 15
		else:
			stare = 2 if P.INCHIS in m else 0
	return "afisaj-color/%s/stari/%02d.png" % (marime, stare)


class IesireLive(object):
	"""Comenzi mici, numai la schimbare; fara bucla de cadre video."""
	def __init__(self, radacina="/proc/stb/lcd"):
		self.radacina = radacina
		self.eroare = ""
		self.mod = None
		self.plan = {"nu": []}
		live = os.path.join(radacina, "live_enable")
		alegeri = _citeste(live + "_choices").split()
		if os.path.exists(live) and {"enable", "disable"}.issubset(alegeri):
			self.plan = {"nu": [(live, "disable")], "imagine": [(live, "enable")]}
		# Unele drivere au un selector separat pentru video si OSD.
		mode = os.path.join(radacina, "mode")
		moduri = _citeste(mode + "_choices").split()
		if os.path.exists(mode) and {"0", "1", "3"}.issubset(moduri):
			self.plan = {"nu": [(mode, "0")], "imagine": [(mode, "1")],
				"osd": [(mode, "3")]}

	def capabilitati(self):
		return tuple(m for m in LIVE if m in self.plan)

	def aplica(self, mod):
		if not K.permite("live", color=True):
			self.mod = None
			return False
		if mod not in self.plan:
			self.eroare = A._("Driverul nu ofera acest mod live pe afisaj.")
			return False
		if self.mod == mod:
			return True
		vechi = []
		try:
			for cale, valoare in self.plan[mod]:
				inainte = _citeste(cale)
				if inainte != valoare:
					with open(cale, "w", encoding="ascii") as f:
						f.write(valoare)
					vechi.append((cale, inainte))
		except OSError as eroare:
			for cale, valoare in reversed(vechi):
				try:
					with open(cale, "w", encoding="ascii") as f:
						f.write(valoare)
				except OSError:
					pass
			self.eroare = A._("Afisajul nu primeste comanda live: %s") % eroare
			return False
		self.mod = mod
		self.eroare = ""
		return True

	def opreste(self):
		return self.aplica("nu")


class Afisaj(A.Afisaj):
	"""Motorul comun ramane responsabil de lista, evenimente si asteptare."""
	def __init__(self, session, info=None, ceas=None):
		self.infoColor = info or detecteaza()
		self.live = IesireLive()
		self.ecran = None
		self.color_imagine = ""
		self.color_text = ""
		self._refPicon = None
		self._picon = ""
		self._piconLa = 0
		A.Afisaj.__init__(self, session, ceas=ceas)
		if session is not None:
			from Screens.HdsAfisajColor import HdsAfisajColor
			self.ecran = session.instantiateSummaryDialog(
				HdsAfisajColor, self.infoColor, zPosition=20)
			if K.permite("lcd", color=True):
				self.ecran.show()

	def scrie(self, sir):
		# Motorul comun nu scrie niciun octet de segmente pe LCD.
		self.ultim = sir
		self.eroare = None
		return True

	def _lumineaza(self, acum):
		if not K.permite("lumina", color=True):
			self.lumina = None
			return
		treapta = self.treaptaDorita(acum)
		if treapta == self.lumina:
			return
		if treapta is not None:
			from enigma import eDBoxLCD
			# API-ul LCD asteapta numar zecimal 0..255.
			eDBoxLCD.getInstance().setLCDBrightness(round((treapta - 1) * 255 / 6))
		self.lumina = treapta

	def _sigla(self, acum):
		from Components.Renderer.Picon import cauta_sigla, generatie_sigle
		ref = self.ctx.ref()
		ref = ref.toString() if ref is not None else ""
		g = generatie_sigle()
		if (ref != self._refPicon or acum - self._piconLa >= 60
				or g != getattr(self, "_piconGeneratie", -1)):
			self._picon = cauta_sigla(ref, nume=self.ctx.numeServiciu()) if ref else ""
			self._refPicon, self._piconLa = ref, acum
			self._piconGeneratie = g
		return self._picon

	def pas(self, acum=None):
		acum = self.ceas() if acum is None else acum
		if not K.permite("lcd", color=True):
			self._colorCedat = True
			self.live.mod = None
			self.lumina = None
			if self.ecran is not None:
				self.ecran.hide()
			if K.permite("lumina", color=True):
				self._lumineaza(acum)
			return 1000
		if getattr(self, "_colorCedat", False):
			self._colorCedat = False
			self.ultim, self.lumina, self.arata = None, None, None
		c = A._cfg()
		mod = "nu" if self.inAsteptare else c.color_live.value
		if not self.live.aplica(mod):
			eroare = self.live.eroare
			self.live.aplica("nu")
			self.live.eroare = eroare
			mod = "nu"
		if mod != "nu":
			self.ultim = "live"
			if self.ecran is not None:
				self.ecran.hide()
			self.color_imagine = ""
			self.color_text = A._("Numai imaginea") if mod == "imagine" else A._("Imaginea cu OSD")
			self._lumineaza(acum)
			return 60000
		ms = A.Afisaj.pas(self, acum)
		a = self.mesajul or self.arata
		if a is None:
			return ms
		secunde = max(0.0, acum - a.cititLa)
		text = textColor(a.pereche, secunde, a.intrare.d.id,
			getattr(getattr(a.intrare, "f", None), "id", ""))
		imagine = ""
		titlu = A._(getattr(a.intrare.d, "eticheta", ""))
		fel = a.pereche[0] if a.pereche else "fix"
		if fel == "personaj":
			e = a.intrare.expresie
			marime = "400x240" if self.infoColor["latime"] == 400 else "480x320"
			imagine = pozaExpresie(e, a.cadru, marime)
			# Cate o poza intermediara la inchiderea si deschiderea ochilor.
			urmator = min(a.cadru + 1, len(e.cadre) - 1)
			inchis = tuple(e.cadre[a.cadru]) == P.F_INCHISI
			inchide = tuple(e.cadre[urmator]) == P.F_INCHISI
			if inchis or inchide:
				ramas = a.cadruLa + e.durate[a.cadru] / 1000.0 - acum
				if 0 < ramas <= 0.085:
					imagine = "afisaj-color/%s/stari/01.png" % marime
				elif ramas > 0.085:
					ms = min(ms, max(20, int((ramas - 0.08) * 1000)))
			titlu = P.nume(e)
		elif a.intrare.d.id == "vremea.acum":
			from Components import HdsVremea as V
			vreme = V.date()
			titlu = vreme.get("oras", "")
			text = V.textTemperatura(vreme.get("temperatura"),
				V.setari()["unitate"])
			stare = V._t(vreme.get("stare") or "")
			text = " ".join(t for t in (text, stare) if t)
			imagine = vreme.get("pictograma", "")
			fel = "vremea"
		elif c.color_picon.value != "nu" and not self.inAsteptare and self.mesajul is None:
			imagine = self._sigla(acum)
			if imagine:
				fel = "picon"
				text = self.ctx.numeServiciu() if c.color_picon.value == "nume_ora" else ""
				titlu = ""
		self.color_imagine, self.color_text = imagine, text
		stins = fel != "picon" and a.intrare.d.id in ("texte.nimic", "asteptare.stins")
		if self.ecran is not None:
			self.ecran.show()
			self.ecran.arata(titlu, text, imagine, fel, a.pereche,
				a.intrare.d.id, secunde, self.viteza(), stins,
				c.color_picon.value != "singur" or fel != "picon")
			if self.ecran.animat:
				ms = min(ms, 50)
		if fel in ("alternat", "secventa") or c.color_picon.value != "nu":
			ms = min(ms, 1000)
		return ms

	def _puneMesaj(self, id_data, valoare, secunde=None):
		if not A.Afisaj._puneMesaj(self, id_data, valoare, secunde):
			return False
		# Durata automata urmeaza textul LCD, nu cele patru pozitii LED.
		m = self.mesajul
		if secunde is None and m.pereche and m.pereche[0] == "derulat":
			m.pana = self.ceas() + max(3.0, len(str(m.pereche[1])) * 0.16)
		return True

	def textAcum(self):
		return self.color_text

	def _iesiDinAsteptare(self):
		self.lumina = None
		A.Afisaj._iesiDinAsteptare(self)

	def opreste(self):
		A.Afisaj.opreste(self)
		if K.permite("live", color=True):
			self.live.opreste()
		if self.ecran is not None:
			self.session.deleteDialog(self.ecran)
			self.ecran = None
