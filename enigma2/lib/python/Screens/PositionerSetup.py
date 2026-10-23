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


class HdsPositionerSetup(Screen, ConfigListScreen):
	# HDSatelit (gasit printr-un grep pe `<screen name="..."` din skin.xml):
	# clasa se numea `PositionerSetup`,
	# nume care COLIDA cu `<screen name="PositionerSetup">` deja existent in skin.xml (widget-uri "list"/
	# "Lock"/"lock_off", ecranul STOCK de control motor DiSEqC -- nimic din ce foloseste calculatorul propriu,
	# "config"/"rezultat"/"ghid"/"key_red"/"key_green"). Redenumit `Hds...`, acelasi tipar ca
	# HdsSoftwareUpdate/TempFanControl/HdsLogManager/HdsButtonSetup.
	skin = """
	<screen name="HdsPositionerSetup" resolution="1920,1080" position="center,center" size="1000,560" title="Calculator unghiuri satelit">
		<widget name="config" position="30,30" size="940,110" scrollbarMode="showOnDemand" font="Regular;24" secondfont="Regular;16" itemHeight="42" />
		<widget source="rezultat" render="Label" position="30,160" size="940,120" font="Regular;26" />
		<widget source="ghid" render="Label" position="30,300" size="940,200" font="Regular;20" />
		<widget source="key_red" render="Label" position="30,500" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget source="key_green" render="Label" position="310,500" size="260,40" zPosition="1" font="Regular;22" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [], session=session)
		self.setTitle(_("Calculator unghiuri satelit"))
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
		self["ghid"] = StaticText(_(
			"Locul tău e locul antenei, același pentru motorul USALS: OK pe primul rând îl schimbă (țara și orașul "
			"sau coordonatele). Satelitul se alege cu Galben/Albastru, iar azimutul, elevația și skew-ul se calculează "
			"pe loc. Ecranul e doar calculator: antena se rotește din Rotirea antenei."))
		self["key_red"] = StaticText(_("Inapoi"))
		self["key_green"] = StaticText(_("Recalculeaza"))

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
		self.list = [getConfigListEntry(_("%s (netestat)") % _("Locul tău"), self._loc)]
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
			return
		lat, lon = loc
		az, el, skew = calculeazaUnghiuri(lat, lon, sat_lon)
		self["rezultat"].setText(_(
			"Satelit: %s (%s)\n"
			"Azimut: %s grade  |  Elevație: %s grade  |  Skew LNB: %s grade") % (
			sat_nume, HdsGrade.pozitie(sat_lon), HdsGrade.numar(az, 1), HdsGrade.numar(el, 1), HdsGrade.numar(skew, 1)))
