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
MODELE = {"vusolo4k": (480, 320, 32), "vuuno4kse": (400, 240, 32),
	"vuduo4k": (480, 320, 32), "vuduo4kse": (480, 320, 32),
	"gbquad4kpro": (400, 240, 16)}
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
		return {"latime": marime[0], "inaltime": marime[1], "bpp": marime[2]}
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
		self.color_scena = None
		self.color_revizie = ""
		self.color_cadru = None
		self._colorValoare = None
		self._vremeEcrane = set()
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
			eDBoxLCD.getInstance().setLCDBrightness(int(A.valoareLumina(treapta, A.TREPTE_LUMINA_COLOR)))
		self.lumina = treapta

	def _sigla(self, acum):
		from Tools.PiconResolver import cauta_sigla, generatie_sigle
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
			self.color_cadru = None
			self.color_revizie = "live"
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
		from Components import HdsAfisajScena as S
		from Components import HdsAfisajRandare as R
		secunde = max(0.0, acum - a.cititLa)
		id_ = a.intrare.d.id
		if self._vremeEcrane and self.mesajul is None and not self.inAsteptare:
			id_ = "vremea.acum"
		format_ = getattr(getattr(a.intrare, "f", None), "id", "")
		text = textColor(a.pereche, secunde, id_, format_)
		fel = a.pereche[0] if a.pereche else "fix"
		animatii = getattr(getattr(c, "color_animatii", None), "value", "nu") == "da"
		imagine = ""
		if fel == "personaj":
			marime = "400x240" if self.infoColor["latime"] == 400 else "480x320"
			imagine = pozaExpresie(a.intrare.expresie, a.cadru if animatii else 0, marime)
			if animatii:
				# O singura poza intermediara la clipire.
				e = a.intrare.expresie
				urmator = min(a.cadru + 1, len(e.cadre) - 1)
				inchis = tuple(e.cadre[a.cadru]) == P.F_INCHISI
				inchide = tuple(e.cadre[urmator]) == P.F_INCHISI
				if inchis or inchide:
					ramas = a.cadruLa + e.durate[a.cadru] / 1000.0 - acum
					if 0 < ramas <= 0.085:
						imagine = "afisaj-color/%s/stari/01.png" % marime
					elif ramas > 0.085:
						ms = min(ms, max(20, int((ramas - 0.08) * 1000)))
		elif id_ in ("canal.numar", "canal.nume", "canal.numar_nume", "evenimente.zap"):
			imagine = self._sigla(acum) if c.color_picon.value != "nu" else ""
		detalii = dict(imagine=imagine, format=format_,
			titlu=A._(getattr(a.intrare.d, "eticheta", "")),
			picon_mode=c.color_picon.value)
		if self._colorValoare and self._colorValoare[0] is a:
			detalii["valoare"] = self._colorValoare[1]
		if self.inAsteptare:
			detalii["asteptare"] = self.previzualizareAsteptare or c.asteptare.value
		if self.recEsuatLa is not None and 0 <= acum - self.recEsuatLa < A.REC_ESUAT_S:
			if id_ != "evenimente.actualizare":
				detalii["rec_esuat"] = True
				id_ = "evenimente.rec_esuata"
		scena = S.scena(self.ctx, id_, text, a.pereche, acum, detalii)
		if (c.color_picon.value != "nu" and not self.inAsteptare
				and self.mesajul is None and not self._vremeEcrane):
			picon = self._sigla(acum)
			if picon and scena["pagina"] != "inregistrare_esuata":
				scena.update(pagina="picon", imagine=picon, stins=False,
					titlu=self.ctx.numeServiciu(), picon_mode=c.color_picon.value)
		scena["bara"] = getattr(getattr(c, "color_bara", None), "value", "da") == "da"
		self.color_scena = scena
		self.color_imagine, self.color_text = scena.get("imagine", ""), scena.get("valoare", text)
		self.color_cadru = R.cadru(scena, (self.infoColor["latime"], self.infoColor["inaltime"]))
		self.color_revizie = self.color_cadru[2]
		R.pastreaza(self.color_cadru[1])
		if self.ecran is not None:
			self.ecran.arataCadru(self.color_cadru[1])
			self.ecran.show()
		return ms

	def _trebuieNumar(self):
		return True

	def _puneExpresia(self, e, acum):
		m = self.mesajul
		if m and m.intrare.d.id in ("evenimente.actualizare", "evenimente.fara_semnal"):
			return
		if self.recEsuatLa is not None and 0 <= acum - self.recEsuatLa < A.REC_ESUAT_S:
			return
		A.Afisaj._puneExpresia(self, e, acum)

	def _pana(self, a, acum):
		# Cadrele LED nu dicteaza redesenarea LCD-ului. O scena statica sta pe loc.
		c = A._cfg()
		animatii = getattr(getattr(c, "color_animatii", None), "value", "nu") == "da"
		if a.pereche and a.pereche[0] == "personaj" and animatii:
			return A.Afisaj._pana(self, a, acum)
		cand = [acum + A.DORMI_MAXIM_S]
		if self._vremeEcrane:
			cand.append(acum + 10)
		for termen in (a.pana, self.previzualizarePana):
			if termen is not None:
				cand.append(termen)
		if self.recEsuatLa is not None:
			sfarsit = self.recEsuatLa + A.REC_ESUAT_S
			if sfarsit > acum:
				cand.append(sfarsit)
		if self.motorPana is not None:
			cand.append(acum + A.MOTOR_PAS_S)
		if self.mesajul is None:
			r = self._candCiteste(a)
			if r is not None:
				cand.append(r)
		r = self._personajCand(acum)
		if r is not None:
			cand.append(r)
		id_ = a.intrare.d.id
		if id_.startswith(("canal.", "emisiune.")) or id_ == "evenimente.zap":
			cand.append(acum + 1)
		elif a.pereche and a.pereche[0] in ("alternat", "secventa"):
			cand.append(acum + 2)
		return max(20, int((min(cand) - acum) * 1000 + 0.5))

	def _laInregistrare(self, serviciu, eveniment):
		A.Afisaj._laInregistrare(self, serviciu, eveniment)
		# Semnul REC si eroarea nu depind de animatia personajului.
		self.timer.start(0, True)

	def _puneMesaj(self, id_data, valoare, secunde=None):
		# Actualizarea in curs nu poate fi acoperita de volum sau de zap.
		m = self.mesajul
		if m is not None and m.intrare.d.id == "evenimente.actualizare":
			if id_data != "evenimente.actualizare" and m.pana > self.ceas():
				return False
		if secunde is None:
			secunde = {"evenimente.volum": 2, "evenimente.mut": 2,
				"evenimente.zap": 8, "evenimente.rec": 4}.get(id_data)
		if not A.Afisaj._puneMesaj(self, id_data, valoare, secunde):
			return False
		self._colorValoare = (self.mesajul, valoare)
		return True

	def textAcum(self):
		return self.color_text

	def _iesiDinAsteptare(self):
		self.lumina = None
		A.Afisaj._iesiDinAsteptare(self)

	def opreste(self):
		if self.pastreazaLaOprire and self.color_scena:
			from Components import HdsAfisajRandare as R
			s = dict(self.color_scena, pagina="actualizare", progres=None,
				procent=None, valoare="", detaliu=A._("Se scrie"))
			self.color_scena = s
			self.color_cadru = R.cadru(s, (self.infoColor["latime"], self.infoColor["inaltime"]))
			self.color_revizie = self.color_cadru[2]
			if self.ecran is not None:
				self.ecran.arataCadru(self.color_cadru[1])
		A.Afisaj.opreste(self)
		if K.permite("live", color=True):
			self.live.opreste()
		if self.ecran is not None and not self.pastreazaLaOprire:
			self.session.deleteDialog(self.ecran)
			self.ecran = None


def cadruPrevizualizare(alegere="", expresie="", cadru=0, valori=None):
	"""Unicul cadru nativ, pentru LCD, meniu si web; nu scrie pe dispozitiv."""
	from Components import HdsAfisajRandare as R
	from Components import HdsAfisajScena as S
	motor = getattr(A, "_afisaj", None)
	if not alegere and not expresie and getattr(motor, "ultim", None) == "live":
		raise ValueError("Previzualizarea video este oferita de driver")
	info = getattr(motor, "infoColor", None) or A.colorInfo() or dict(latime=480, inaltime=320)
	marime = (info["latime"], info["inaltime"])
	if not alegere and not expresie and getattr(motor, "color_cadru", None):
		return motor.color_cadru
	valori = valori or A.Valori(getattr(motor, "session", None))
	ctx = valori.ctx
	if expresie:
		e = P.expresie(expresie)
		if e is None:
			raise ValueError("Expresie necunoscuta")
		c = A._cfg()
		animatii = getattr(getattr(c, "color_animatii", None), "value", "nu") == "da"
		poza = pozaExpresie(e, cadru if animatii else 0,
			"400x240" if marime[0] == 400 else "480x320")
		s = S.scena(ctx, "personaj." + expresie, detalii=dict(imagine=poza))
	else:
		d, f = D.alegere(alegere or "ceas.ora:24")
		if d is None:
			raise ValueError("Alegere necunoscuta")
		v = valori.valoare(d)
		per = D.pereche(d, f, v)
		if per is None and d.grupa == D.GRUPA_EVENIMENTE:
			v = D.exemplu(d, f)
			per = D.pereche(d, f, v)
		detalii = dict(valoare=v, format=f.id, titlu=A._(d.eticheta))
		if motor is not None and hasattr(motor, "_sigla"):
			if getattr(getattr(A._cfg(), "color_picon", None), "value", "nu") != "nu":
				detalii["imagine"] = motor._sigla(motor.ceas())
		s = S.scena(ctx, d.id, textColor(per, 0, d.id, f.id), per, detalii=detalii)
	s["bara"] = getattr(getattr(A._cfg(), "color_bara", None), "value", "da") == "da"
	return R.cadru(s, marime)


def vremeDeschisa(ecran, pornita):
	motor = getattr(A, "_afisaj", None)
	if not isinstance(motor, Afisaj):
		return
	if pornita:
		motor._vremeEcrane.add(id(ecran))
	else:
		motor._vremeEcrane.discard(id(ecran))
	motor.timer.start(0, True)
