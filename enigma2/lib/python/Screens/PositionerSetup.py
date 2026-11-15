# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# PositionerSetup.py — Calculator unghiuri satelit + asistent aliniere motor.
# Cod 100% propriu, scris de la zero. Formulele de azimut/elevatie/skew pentru
# sateliti geostationari sunt matematica publica standard (geometrie sferica),
# comuna oricarui calculator de acest fel, nu cod copiat din vreo distributie
# Enigma2. Verificate contra valorii masurate pe receptorul Amiko
# Viper 4K (Bucuresti approx 45.300N/23.270E
# spre Astra 19.2E -> Azimut asteptat 185.72 grade; formula de mai jos da 185.72).
#
# Acest ecran NU miscă nimic — e doar calculator si ghid text. Miscarea reala
# a motorului (DiSEqC 1.2/USALS) ramane in NimManager/sec.cpp, ca pana acum;
# bannerul OSD cu antena care se roteste e deja Dish.py (InfoBarDish).

from math import radians, degrees, sin, cos, tan, atan, sqrt

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.config import config, ConfigSubsection, ConfigInteger, getConfigListEntry
from Components.Sources.StaticText import StaticText
from Components.NimManager import nimmanager

RAZA_PAMANT_KM = 6378.14
RAZA_ORBITA_GEO_KM = 42164.0


def initConfigPositioner():
	# HDSatelit: hasattr(config, ...) NU e sigur -- ConfigSubsection.__getattr__
	# arunca KeyError (nu AttributeError) pentru o cheie lipsa, iar hasattr() din Python 3
	# prinde doar AttributeError. Vezi HdsWebControl/plugin.py pentru explicatia completa.
	if "hds_positioner" not in config.content.items:
		config.hds_positioner = ConfigSubsection()
		# Implicit Romania (aceleasi valori ca implicitul USALS din NimManager).
		config.hds_positioner.lat = ConfigInteger(default=453, limits=(-900, 900))   # grade * 10 (45.3N)
		config.hds_positioner.lon = ConfigInteger(default=233, limits=(-1800, 1800))  # grade * 10 (23.3E)


def orbpozToGrade(orbpos):
	"""Converteste orbpos-ul Enigma2 (zecimi de grad, 0-3599, Est 0-1800, Vest 1801-3599) in grade semnate (Est +, Vest -)."""
	if orbpos > 1800:
		return -(3600 - orbpos) / 10.0
	return orbpos / 10.0


def calculeazaUnghiuri(lat_grade, lon_grade, sat_lon_grade):
	"""Azimut (0=Nord, 90=Est, 180=Sud, 270=Vest), Elevatie si Skew (grade), pentru satelit geostationar."""
	lat = radians(lat_grade)
	dlon = radians(sat_lon_grade - lon_grade)

	# Elevatie
	cos_el = cos(lat) * cos(dlon)
	numitor = sqrt(max(1e-9, 1 - cos_el * cos_el))
	elevatie = degrees(atan((cos_el - RAZA_PAMANT_KM / RAZA_ORBITA_GEO_KM) / numitor))

	# Azimut (formula standard pentru emisfera de referinta a observatorului)
	if lat == 0:
		azimut = 90.0 if dlon > 0 else 270.0
	else:
		a = degrees(atan(abs(tan(dlon)) / sin(abs(lat))))
		if lat_grade >= 0:  # emisfera nordica
			azimut = (180 - a) if sat_lon_grade > lon_grade else (180 + a)
		else:  # emisfera sudica
			azimut = a if sat_lon_grade > lon_grade else (360 - a)

	# Skew LNB (aproximare standard, unghi de rotatie a capului LNB fata de vertical)
	skew = 0.0 if lat == 0 else degrees(atan(sin(dlon) / tan(lat)))

	return azimut, elevatie, skew


def N_(text):
	return text


# cele 16 directii ale busolei, din 22,5 in 22,5 grade, pornind de la nord: (prescurtarea, cuvantul)
DIRECTII = (
	(N_("N"), N_("nord")), (N_("NNE"), N_("nord-nord-est")), (N_("NE"), N_("nord-est")), (N_("ENE"), N_("est-nord-est")),
	(N_("E"), N_("est")), (N_("ESE"), N_("est-sud-est")), (N_("SE"), N_("sud-est")), (N_("SSE"), N_("sud-sud-est")),
	(N_("S"), N_("sud")), (N_("SSV"), N_("sud-sud-vest")), (N_("SV"), N_("sud-vest")), (N_("VSV"), N_("vest-sud-vest")),
	(N_("V"), N_("vest")), (N_("VNV"), N_("vest-nord-vest")), (N_("NV"), N_("nord-vest")), (N_("NNV"), N_("nord-nord-vest")),
)


def directie(azimut):
	"""Azimutul (grade, 0 = nord) -> (prescurtarea, cuvantul) traduse, pentru busola."""
	i = int(((azimut % 360) + 11.25) // 22.5) % 16
	return _(DIRECTII[i][0]), _(DIRECTII[i][1])


def puncteCardinale():
	"""N, E, S, V in limba meniului (busola din pagina web)."""
	return [_(DIRECTII[i][0]) for i in (0, 4, 8, 12)]


def directieInCuvinte(azimut, elevatie, numar=None):
	"""Ce face omul cu antena, intr-o fraza: spre ce parte a lumii si cat de sus. `numar` scrie unghiul in limba
	meniului (Components.HdsGrade.numar); fara el, cu o zecimala."""
	if elevatie <= 0:
		return _("Satelitul e sub orizont din locul acesta: nu se poate prinde.")
	prescurtare, cuvant = directie(azimut)
	scrie = numar or (lambda x, z: "%.*f" % (z, x))
	return _("Îndreaptă antena spre %s (%s, %s°), la %s° deasupra orizontului.") % (
		cuvant, prescurtare, scrie(azimut, 0), scrie(elevatie, 0))


# Busola desenata pe televizor (INB, 15.11.2026; TODO 14.11 22:14): aceeasi busola ca in pagina web /antena/calculator
# (scanare_web.py, busola()): nordul sus, sageata spre satelit; langa ea elevatia (sfertul de cerc de la orizont in sus)
# si rotirea LNB-ului vazut din spatele antenei. Culorile, opace, din tema HDSatelit (hdsPanelDialog, hdsText, hdsText2).
BUSOLA_CULORI = {
	"fond": 0x10162A, "inel": 0x5A6478, "liniute": 0x8A94A8, "text": 0xF2F4F8, "text2": 0xC9D2E3,
	"sageata": 0x2E8BFF, "orizont": 0x6B7A90, "lnb": 0xF5C518,
}


def _peBusola(cx, cy, azimut, raza):
	"""punctul de pe busola la `azimut` (0 = nord, sus; 90 = est, dreapta), ca x/y din SVG-ul paginii web"""
	u = radians(azimut)
	return cx + sin(u) * raza, cy - cos(u) * raza


def deseneazaBusola(panza, latime, inaltime, azimut=None, elevatie=None, skew=None, puncte=None, font=None,
		numar=None, aliniere=0, culori=BUSOLA_CULORI):
	"""Deseneaza pe `panza` (CanvasSource sau o panza de proba cu aceleasi metode) busola, elevatia si rotirea LNB-ului.
	`latime` si `inaltime` = marimea reala a panzei, in pixeli. `azimut` None = numai fondul (locul nu e stabilit).
	`font(marime)` da fontul pentru litere si etichete (None = desenul fara litere); `numar(x, zecimale)` scrie unghiul in
	limba meniului (Components.HdsGrade.numar); `aliniere` = steagurile writeText pentru textul centrat.
	Satelitul sub orizont: busola fara sageata, fara elevatie si fara LNB (ca in pagina web, care nu deseneaza busola)."""
	c = culori
	scrie = numar or (lambda x, z: "%.*f" % (z, x))
	panza.clear()
	panza.fill(0, 0, int(latime), int(inaltime), c["fond"])
	if azimut is None or latime <= 0 or inaltime <= 0:
		panza.flush()
		return

	def text(x, y, l, i, culoare, sir, marime):
		f = font(max(1, int(round(marime)))) if font else None
		if f is not None and sir:
			panza.writeText(int(round(x)), int(round(y)), int(round(l)), int(round(i)), culoare, c["fond"], f, sir, aliniere)

	# busola: un patrat in stanga, cat inaltimea panzei
	zona = min(float(inaltime), latime * 0.4)
	cx, cy = zona / 2.0, inaltime / 2.0
	r = zona / 2.0 - max(4.0, zona * 0.04)
	panza.drawRing(cx, cy, r, max(1.5, r * 0.02), c["inel"])
	for i in range(16):
		lung = r * (0.12 if i % 4 == 0 else 0.06)
		x0, y0 = _peBusola(cx, cy, i * 22.5, r - lung)
		x1, y1 = _peBusola(cx, cy, i * 22.5, r)
		panza.drawLine(x0, y0, x1, y1, max(1.0, r * 0.015), c["liniute"])
	litere = puncte if puncte and len(puncte) == 4 else ["N", "E", "S", "V"]
	cutie = r * 0.34
	for i, litera in enumerate(litere):
		x, y = _peBusola(cx, cy, i * 90.0, r * 0.74)
		text(x - cutie / 2.0, y - cutie / 2.0, cutie, cutie, c["text"] if i == 0 else c["text2"], litera, r * 0.2)
	vizibil = elevatie is not None and elevatie > 0
	if vizibil:
		vx, vy = _peBusola(cx, cy, azimut, r * 0.6)
		panza.drawLine(cx, cy, vx, vy, max(2.0, r * 0.05), c["sageata"])
		panza.fillCircle(vx, vy, max(3.0, r * 0.08), c["sageata"])
	panza.fillCircle(cx, cy, max(2.0, r * 0.04), c["text"])

	if not vizibil:
		panza.flush()
		return

	# elevatia: sfertul de cerc din coltul de jos, orizontul pe jos, raza spre satelit
	rest = latime - zona
	lz = rest / 2.0
	eticheta = inaltime * 0.26
	marime = inaltime * 0.085
	ox, oy = zona + lz * 0.12, inaltime - eticheta
	re = max(4.0, min(lz * 0.76, oy - inaltime * 0.08))
	panza.drawLine(ox, oy, ox + re, oy, max(1.5, re * 0.015), c["orizont"])
	panza.drawLine(ox, oy, ox, oy - re, max(1.0, re * 0.01), c["inel"])
	panza.drawArc(ox, oy, re, max(1.5, re * 0.015), 270.0, 90.0, c["inel"], 0)
	u = radians(max(0.0, min(90.0, elevatie)))
	ex, ey = ox + cos(u) * re, oy - sin(u) * re
	panza.drawArc(ox, oy, re * 0.32, max(2.0, re * 0.03), 360.0 - degrees(u), degrees(u), c["sageata"], 0)
	panza.drawLine(ox, oy, ex, ey, max(2.0, re * 0.04), c["sageata"])
	panza.fillCircle(ex, ey, max(3.0, re * 0.06), c["sageata"])
	text(zona, oy + inaltime * 0.02, lz, marime * 1.3, c["text2"], _("Elevație"), marime)
	text(zona, oy + inaltime * 0.02 + marime * 1.3, lz, marime * 1.3, c["text"], scrie(elevatie, 1) + "°", marime)

	# LNB-ul vazut din spatele antenei: cercul capului si bara lui, rotita cu skew-ul (pozitiv = in sens invers acelor de
	# ceas, cum se vede din spatele antenei spre un satelit aflat la est); linia subtire = pozitia fara rotire
	lx = zona + lz + lz / 2.0
	ly = (inaltime - eticheta) / 2.0 + inaltime * 0.04
	rl = max(4.0, min(lz * 0.22, (inaltime - eticheta) * 0.3))
	panza.drawLine(lx - rl * 1.9, ly, lx + rl * 1.9, ly, max(1.0, rl * 0.03), c["orizont"])
	panza.drawRing(lx, ly, rl, max(1.5, rl * 0.06), c["inel"])
	a = radians(-(skew or 0.0))
	dx, dy = cos(a) * rl * 1.6, sin(a) * rl * 1.6
	panza.drawLine(lx - dx, ly - dy, lx + dx, ly + dy, max(3.0, rl * 0.16), c["lnb"])
	panza.fillCircle(lx, ly, max(2.0, rl * 0.12), c["text"])
	text(zona + lz, oy + inaltime * 0.02, lz, marime * 1.3, c["text2"], _("Rotirea LNB-ului (skew)"), marime)
	text(zona + lz, oy + inaltime * 0.02 + marime * 1.3, lz, marime * 1.3, c["text"],
		u"%s%s°  %s" % ("+" if (skew or 0) > 0 else "", scrie(skew or 0.0, 1), _("privit din spatele antenei")), marime * 0.8)
	panza.flush()


class HdsPositionerSetup(Screen, ConfigListScreen):
	# HDSatelit (gasit printr-un grep pe `<screen name="..."` din skin.xml):
	# clasa se numea `PositionerSetup`,
	# nume care COLIDA cu `<screen name="PositionerSetup">` deja existent in skin.xml (widget-uri "list"/
	# "Lock"/"lock_off", ecranul STOCK de control motor DiSEqC -- nimic din ce foloseste calculatorul propriu,
	# "config"/"rezultat"/"ghid"/"key_red"/"key_green"). Redenumit `Hds...`, acelasi tipar ca
	# HdsSoftwareUpdate/TempFanControl/HdsLogManager/HdsButtonSetup.
	skin = """
	<screen name="HdsPositionerSetup" resolution="1920,1080" position="center,center" size="1000,820" title="Calculator de unghiuri">
		<widget name="config" position="30,30" size="940,110" scrollbarMode="showOnDemand" font="Regular;24" secondfont="Regular;16" itemHeight="42" />
		<widget source="rezultat" render="Label" position="30,150" size="940,120" font="Regular;26" />
		<widget source="busola" render="Canvas" position="30,280" size="940,300" />
		<widget source="ghid" render="Label" position="30,590" size="940,160" font="Regular;20" />
		<widget source="key_red" render="Label" position="30,760" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="310,760" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [], session=session)
		# titlul ca randul din meniu (Calculator de unghiuri, tradus in toate limbile)
		self.setTitle(_("Calculator de unghiuri"))
		initConfigPositioner()

		# Lista de sateliti reala, din lamedb/satellites.xml deja incarcat de nimmanager (fara date proprii inventate).
		# intrarile din nimmanager.satList au mai mult de doua campuri (pozitia, numele, steagurile): se iau primele doua
		self._sateliti = sorted(
			((orbpozToGrade(sat[0]), sat[1]) for sat in nimmanager.satList if len(sat) >= 2),
			key=lambda t: t[0])
		if not self._sateliti:
			self._sateliti = [(19.2, _("Astra (implicit, nicio listă de sateliți încărcată)"))]
		self._index_sat = 0

		self["rezultat"] = StaticText("")
		# busola desenata (deseneazaBusola): panza eCanvas, redesenata la fiecare calcul
		from Components.Sources.CanvasSource import CanvasSource
		self["busola"] = CanvasSource()
		self["ghid"] = StaticText(_(
			"Locul tău e locul antenei, același pentru motorul USALS: OK pe primul rând îl schimbă (țara și orașul "
			"sau coordonatele). Satelitul se alege cu Galben/Albastru, iar azimutul, elevația și skew-ul se calculează "
			"pe loc. Ecranul e doar calculator: antena se rotește din Rotirea antenei."))
		self["key_red"] = StaticText(_("Înapoi"))
		self["key_green"] = StaticText(_("Recalculează"))

		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions"],
			{
				"ok": self._alegeLocul,
				"cancel": self.close,
				"red": self.close,
				"green": self._recalculeaza,
				"yellow": self._satelitAnterior,
				"blue": self._satelitUrmator,
			}, -2)

		# locul: cel unic al antenei (Components/HdsLocul.py), nu o copie a calculatorului; randul doar il arata, OK il schimba.
		# Importul aici: pagina web /antena (scanare_web) incarca modulul numai pentru calculeazaUnghiuri.
		from Components.config import ConfigSelection, NoSave
		self._loc = NoSave(ConfigSelection([("loc", "")], "loc"))
		self.list = [getConfigListEntry(_("Locul tău"), self._loc)]
		self._scrieLoc()
		self["config"].list = self.list
		self["config"].onSelectionChanged.append(self._recalculeaza)
		self.onLayoutFinish.append(self._recalculeaza)

	def _scrieLoc(self):
		from Components import HdsLocul
		self._loc.setChoices([("loc", HdsLocul.textLoc())], "loc")
		try:
			self["config"].invalidateCurrent()
		except Exception:
			pass

	def _alegeLocul(self):
		from Screens.HdsLocul import deschide

		def gata(schimbat):
			self._scrieLoc()
			self._recalculeaza()
		deschide(self.session, gata)

	def _satelitAnterior(self):
		if self._sateliti:
			self._index_sat = (self._index_sat - 1) % len(self._sateliti)
			self._recalculeaza()

	def _satelitUrmator(self):
		if self._sateliti:
			self._index_sat = (self._index_sat + 1) % len(self._sateliti)
			self._recalculeaza()

	def _recalculeaza(self):
		# pozitia satelitului si unghiurile in limba meniului (literele si separatorul zecimal): Components/HdsGrade.py
		from Components import HdsGrade, HdsLocul
		sat_lon, sat_nume = self._sateliti[self._index_sat]
		loc = HdsLocul.grade()
		if loc is None:
			self["rezultat"].setText("%s\n%s" % (_("Locul antenei nu e stabilit. Apasă OK și alege țara și orașul."),
				_("Satelit: %s (%s)") % (sat_nume, HdsGrade.pozitie(sat_lon))))
			self._deseneazaBusola(None, None, None)
			return
		lat, lon = loc
		az, el, skew = calculeazaUnghiuri(lat, lon, sat_lon)
		self["rezultat"].setText(_(
			"Satelit: %s (%s)\n"
			"Azimut: %s grade  |  Elevație: %s grade  |  Skew LNB: %s grade") % (
			sat_nume, HdsGrade.pozitie(sat_lon), HdsGrade.numar(az, 1), HdsGrade.numar(el, 1), HdsGrade.numar(skew, 1))
			+ "\n" + directieInCuvinte(az, el, HdsGrade.numar))
		self._deseneazaBusola(az, el, skew)

	def _marimePanza(self):
		"""marimea reala a panzei busolei (dupa skin si scalarea lui), sau None inainte de asezare"""
		for e in getattr(self["busola"], "downstream_elements", ()):
			inst = getattr(e, "instance", None)
			if inst is not None:
				m = inst.size()
				if m.width() > 0 and m.height() > 0:
					return m.width(), m.height()
		return None

	def _deseneazaBusola(self, az, el, skew):
		"""busola, elevatia si LNB-ul pe panza; fontul pus din cod urmeaza Marimea textului (Components/HdsMarireText)"""
		m = self._marimePanza()
		if m is None:
			return
		from Components import HdsGrade
		from enigma import RT_HALIGN_CENTER, RT_VALIGN_CENTER

		def font(marime):
			try:
				import skin
				from Components import HdsMarireText as MT
				try:
					familie = skin.fontHds("Regular")
				except Exception:
					familie = "Regular"
				return MT.fontCod(familie, marime)
			except Exception:
				return None
		try:
			deseneazaBusola(self["busola"], m[0], m[1], az, el, skew, puncteCardinale(), font, HdsGrade.numar,
				RT_HALIGN_CENTER | RT_VALIGN_CENTER)
		except Exception as e:
			print("[HdsPositionerSetup] busola: %s" % e)
