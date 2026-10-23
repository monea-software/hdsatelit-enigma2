# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMotorPlafon.py - cat asteapta nucleul semnalul dupa comanda de motor cand nu stie de unde pleaca antena.
#
# De ce (prima pornire dupa flash-ul 0.3.0): pozitia antenei nu se reda dupa flash (Components/
# HdsMotorPozitie.py), deci la primul acord nucleul nu stie plecarea (curRotorPos = -1). In ramura obisnuita a motorului
# (lib/dvb/sec.cpp:855-910) timpul maxim ramane atunci config.sec.motor_running_timeout = 360 s (NimManager.py:1103),
# iar bucla asteapta semnalul pana la el: ecranul a stat ~6 minute pe rotire, fara semnal. Cu plecarea stiuta nucleul
# isi calculeaza singur timpul (0,5 grade pe secunda, sec.cpp:857-866) si parametrul nu conteaza.
#
# Ce face: pune in nucleu (eDVBSatelliteEquipmentControl.setParam(MOTOR_RUNNING_TIMEOUT)) un plafon calculat:
#   - arcul: gradele de motor (unghiul orar USALS, Components/HdsMotorViteza.unghiMotor) de la marginea arcului vizibil
#     cea mai departata (elevatia ELEVATIE_MIN) pana la tinta, pentru cea mai rea tinta din lista tunerului. Parametrul e
#     unul singur pentru toate tunerele si toate tintele (tinta se afla abia in sec.cpp, la acord), deci se ia cel mai
#     lung drum posibil; fara sateliti vizibili in lista, tot arcul vizibil;
#   - viteza: cea mai mica dintre cele doua directii ale modelului invatat din mutarile adevarate ale motorului
#     (Components/HdsMotorViteza.Calibrare); pana la prima mutare masurata modelul da presupunerea lui (1,2 grade pe
#     secunda), care tine loc de valoarea prudenta;
#   - plafonul = t0 (pornirea si confirmarea semnalului, din acelasi model) + MARJA * arc / viteza + REZERVA_S, rotunjit
#     in sus, intre PLAFON_MIN_S si valoarea din setari. O asteptare prea scurta costa putin: motorul isi termina drumul
#     oricum (comanda 6E e un drum pana la un unghi), iar Components/HdsMotorPozitie.py trimite comanda o data din nou
#     cand mutarea s-a terminat fara semnal.
# Ramura cu masurarea curentului (sec.cpp:841) foloseste acelasi parametru la FIECARE mutare, si cu plecarea stiuta: de
# aceea plafonul acopera tot drumul posibil, nu o mutare obisnuita.
#
# Setarea omului: plafonul se pune numai cat config.sec.motor_running_timeout are valoarea implicita (360). Daca omul a
# schimbat-o, valoarea lui ramane in nucleu (o pune notificatorul din NimManager.py:1104) si aici nu se atinge nimic.
# Fara coordonatele locului (locul antenei nestabilit, Components/HdsLocul.py) arcul nu se poate calcula: ramane valoarea
# din setari.
#
# Cand se calculeaza: la pornire, inaintea primului zap (HdsMotorPozitie.restaureaza) si din bataia de 2 s a aceluiasi
# modul; calculul se reface numai cand se schimba amprenta (tunerele cu motor, coordonatele, modelul vitezei), deci si
# dupa fiecare mutare invatata si dupa schimbarea locului. La import nu se atinge nimic din enigma.
#
# Motorul pe 18 V (lib/dvb/hdsrotire.h): pe tunerele care nu masoara curentul motorului, sec.cpp roteste motorul pe
# 18 V si, spre o tinta pe 13 V, tine 18 V cat dureaza mutarea estimata. Tot de aici (aceeasi bataie, aceeasi amprenta)
# primeste nucleul viteza invatata a fiecarui motor pe cele doua directii (hdsSetRotorModel) si marginile arcului vizibil
# in unghiuri de motor (hdsSetRotorArc, pentru plecarea necunoscuta), indiferent de setarea timpului maxim.
#
# Proba de semnal dinaintea comenzii (lib/dvb/hdsrotire.h): cu plecarea necunoscuta si tinta pe 13 V, nucleul incearca
# intai transponderul tintei cu antena pe loc si, daca il prinde, nu mai trimite comanda. O blocare pe acelasi
# transponder al altui satelit ar lasa antena acolo cu pozitia crezuta gresita, de aceea proba se face numai pe un
# transponder fara geaman pe alt satelit al motorului. Lista transponderelor satelitilor motorului (satellites.xml, fara
# satelitii de sub orizont cand locul se stie) o pune tot de aici (hdsSetRotorTransponders), din aceeasi bataie, numai
# cand se schimba satelitii motorului, locul sau lista citita de NimManager. Fara lista nucleul nu face proba.
import math

from Components import DishMath
from Components import HdsMotorTuner as T
from Components import HdsMotorViteza as V

# marginea arcului vizibil: satelitul la orizont (elevatia observata, cu refractia, ca in DishMath)
ELEVATIE_MIN = 0.0
# cat se adauga peste drumul la viteza invatata (a fost masurata pe mutari adevarate, in directia cea mai inceata)
MARJA = 1.1
REZERVA_S = 3.0
PLAFON_MIN_S = 30
# config.sec.motor_running_timeout implicit (NimManager.py:1103), cand setarea nu se poate citi
IMPLICIT_S = 360


def jurnal(text):
	print("[HdsMotorPlafon] %s" % text)


# ------------------------------------------------------------------ geometria

def _elevatie(sat_grade, lat, lon):
	try:
		return DishMath.elevation(sat_grade % 360.0, float(lat), float(lon) % 360.0)
	except (ValueError, ZeroDivisionError, TypeError):
		return -99.0


def vizibil(sat_grade, lat, lon):
	"""True daca satelitul de la `sat_grade` (est pozitiv) e deasupra orizontului din locul (lat, lon)"""
	return _elevatie(sat_grade, lat, lon) >= ELEVATIE_MIN


def margini(lat, lon):
	"""(unghiul motorului la marginea de vest, la marginea de est) ale arcului vizibil din locul (lat nord pozitiv, lon
	est pozitiv), in grade de motor, est pozitiv; None daca din acest loc nu se vede niciun satelit"""
	if not vizibil(lon, lat, lon):
		return None
	unghiuri = []
	for semn in (-1.0, 1.0):
		jos, sus = 0.0, 90.0
		for _i in range(40):
			mijloc = (jos + sus) / 2.0
			if vizibil(lon + semn * mijloc, lat, lon):
				jos = mijloc
			else:
				sus = mijloc
		unghi = V.unghiMotor(lon + semn * jos, lat, lon)
		if unghi is None:
			return None
		unghiuri.append(unghi)
	return min(unghiuri), max(unghiuri)


def arcMaxim(lat, lon, tinte):
	"""gradele de motor ale celui mai lung drum posibil cand plecarea nu se stie: de la marginea arcului vizibil cea mai
	departata pana la tinta, pentru cea mai rea dintre `tinte` (grade, est pozitiv) aflate deasupra orizontului; fara
	nicio tinta vizibila, tot arcul. None daca locul nu vede niciun satelit."""
	m = margini(lat, lon)
	if m is None:
		return None
	vest, est = m
	cel_mai_lung = None
	for tinta in tinte:
		if not vizibil(tinta, lat, lon):
			continue
		unghi = V.unghiMotor(tinta, lat, lon)
		if unghi is None:
			continue
		drum = max(unghi - vest, est - unghi)
		if cel_mai_lung is None or drum > cel_mai_lung:
			cel_mai_lung = drum
	return cel_mai_lung if cel_mai_lung is not None else est - vest


def secunde(arc, viteza, t0):
	"""plafonul in secunde intregi (in sus) pentru drumul `arc` (grade de motor) la `viteza` (grade pe secunda)"""
	viteza = max(V.VITEZA_MIN, float(viteza))
	return int(math.ceil(max(0.0, t0) + MARJA * max(0.0, arc) / viteza + REZERVA_S))


def plafonSlot(slot):
	"""{"secunde", "arc", "viteza", "t0", "invatata"} pentru tunerul cu motor `slot`, sau None cand locul nu se stie"""
	loc = T.coordonateUsalsNumere(slot)
	if loc is None:
		return None
	tinte = [DishMath.orbitalToDegrees(orbital) for orbital, _nume in T.sateliti(slot)]
	arc = arcMaxim(loc[0], loc[1], tinte)
	if arc is None:
		return None
	model = V.calibrare().model(slot)
	viteza = min(model["viteza"]["est"], model["viteza"]["vest"])
	masurate = model["masurate"]["est"] + model["masurate"]["vest"]
	return {"secunde": secunde(arc, viteza, model["t0"]), "arc": arc, "viteza": viteza, "t0": model["t0"],
		"invatata": masurate > 0}


def calculeaza():
	"""(secunde, {slot: detalii}) cu cel mai mare plafon dintre tunerele cu motor, sau (None, {}) cand nu se poate"""
	detalii = {}
	for slot, _nume in T.tunereCuMotor():
		try:
			d = plafonSlot(slot)
		except Exception as e:
			jurnal("plafonul tunerului %s nu se poate calcula: %r" % (T.numeTuner(slot), e))
			d = None
		if d is not None:
			detalii[slot] = d
	if not detalii:
		return None, {}
	return max(d["secunde"] for d in detalii.values()), detalii


# ------------------------------------------------------------------ punerea in nucleu

def _clasaSec():
	try:
		from enigma import eDVBSatelliteEquipmentControl
	except Exception:
		return None
	if not hasattr(eDVBSatelliteEquipmentControl, "setParam") or \
			not hasattr(eDVBSatelliteEquipmentControl, "MOTOR_RUNNING_TIMEOUT"):
		return None
	return eDVBSatelliteEquipmentControl


def setareOm():
	"""(valoarea, valoarea implicita) din config.sec.motor_running_timeout, sau None cand nu se poate citi"""
	try:
		from Components.config import config
		element = config.sec.motor_running_timeout
		return int(element.value), int(getattr(element, "default", IMPLICIT_S))
	except Exception:
		return None


class Plafon(object):
	def __init__(self):
		self.amprenta = None
		self.calculat = None
		self.detalii = {}
		# ce am pus noi in nucleu (secunde), None = nimic
		self.aplicat = None
		self._lasat_omului = None

	def _amprenta(self):
		parti = []
		for slot, _nume in T.tunereCuMotor():
			model = V.calibrare().model(slot)
			parti.append((slot, T.coordonateUsalsNumere(slot), round(model["t0"], 2),
				round(model["viteza"]["est"], 3), round(model["viteza"]["vest"], 3)))
		return tuple(parti)

	def aplica(self):
		"""pune plafonul in nucleu (sau lasa valoarea omului); intoarce secundele puse de noi, sau None"""
		clasa = _clasaSec()
		setare = setareOm()
		if clasa is None or setare is None:
			return None
		valoare, implicita = setare
		if valoare != implicita:
			if self._lasat_omului != valoare:
				self._lasat_omului = valoare
				jurnal("timpul maxim al motorului e ales in setari (%d s); plafonul calculat nu se foloseste" % valoare)
			# valoarea omului e deja in nucleu: notificatorul din NimManager.py:1104 a pus-o la schimbare
			self.aplicat = None
			return None
		self._lasat_omului = None
		amprenta = self._amprenta()
		if amprenta != self.amprenta:
			self.amprenta = amprenta
			self.calculat, self.detalii = calculeaza()
		if self.calculat is None:
			if self.aplicat is not None:
				clasa.setParam(clasa.MOTOR_RUNNING_TIMEOUT, valoare)
				jurnal("locul antenei nu se mai stie; timpul maxim al motorului revine la %d s" % valoare)
			self.aplicat = None
			return None
		bun = max(PLAFON_MIN_S, min(valoare, self.calculat))
		# la fiecare bataie: o atribuire in nucleu; notificatorul setarii o poate fi rescris intre timp
		clasa.setParam(clasa.MOTOR_RUNNING_TIMEOUT, bun)
		if bun != self.aplicat:
			self.aplicat = bun
			for slot, d in sorted(self.detalii.items()):
				jurnal("tunerul %s: cel mai lung drum posibil %.1f grade de motor, viteza %.2f grade/s (%s), t0 %.1f s"
					% (T.numeTuner(slot), d["arc"], d["viteza"], "invatata" if d["invatata"] else "presupusa", d["t0"]))
			jurnal("timpul maxim al motorului cand plecarea antenei nu se stie: %d s (in loc de %d s)" % (bun, valoare))
		return bun


_unic = None
_ultima_eroare = [None]


def plafon():
	global _unic
	if _unic is None:
		_unic = Plafon()
	return _unic


# ------------------------------------------------------------------ modelul motorului in nucleu

_margini_cache = {}


def _marginiLoc(lat, lon):
	cheie = (round(float(lat), 4), round(float(lon), 4))
	if cheie not in _margini_cache:
		_margini_cache[cheie] = margini(lat, lon)
	return _margini_cache[cheie]


def _secCuModel():
	"""nucleul, daca stie de modelul motorului (lib/dvb/hdsrotire.h); altfel None (imagine veche)"""
	sec = T.controlSec()
	if sec is None or not hasattr(sec, "hdsSetRotorModel") or not hasattr(sec, "hdsSetRotorArc"):
		return None
	return sec


def valoriModel():
	"""[(slot, viteza spre est, viteza spre vest (miimi de grad de motor pe secunda), marginea de vest, marginea de est
	(zecimi de grad de motor; 0, 0 = locul nu se stie))] pentru tunerele cu motor"""
	valori = []
	for slot, _nume in T.tunereCuMotor():
		model = V.calibrare().model(slot)
		loc = T.coordonateUsalsNumere(slot)
		m = _marginiLoc(loc[0], loc[1]) if loc is not None else None
		arc = (int(round(m[0] * 10)), int(round(m[1] * 10))) if m is not None else (0, 0)
		valori.append((slot, int(round(model["viteza"]["est"] * 1000)), int(round(model["viteza"]["vest"] * 1000)),
			arc[0], arc[1]))
	return tuple(valori)


class ModelNucleu(object):
	"""pune modelul motorului in nucleu numai cand se schimba (amprenta = valorile puse)"""

	def __init__(self):
		self.amprenta = None

	def aplica(self):
		sec = _secCuModel()
		if sec is None:
			return None
		valori = valoriModel()
		if valori == self.amprenta:
			return valori
		for slot, est, vest, arc_vest, arc_est in valori:
			sec.hdsSetRotorModel(slot, est, vest)
			sec.hdsSetRotorArc(slot, arc_vest, arc_est)
			jurnal("tunerul %s: nucleul roteste motorul pe 18 V cu viteza %.2f grade/s spre est, %.2f spre vest, arcul %s"
				% (T.numeTuner(slot), est / 1000.0, vest / 1000.0,
				"%.1f..%.1f" % (arc_vest / 10.0, arc_est / 10.0) if arc_vest < arc_est else "nestiut"))
		self.amprenta = valori
		return valori


_model_nucleu = None
_ultima_eroare_model = [None]


def modelNucleu():
	global _model_nucleu
	if _model_nucleu is None:
		_model_nucleu = ModelNucleu()
	return _model_nucleu


def aplicaModelul():
	"""modelul motorului in nucleu (nu arunca; aceeasi eroare se scrie o singura data)"""
	try:
		rezultat = modelNucleu().aplica()
		_ultima_eroare_model[0] = None
		return rezultat
	except Exception as e:
		if repr(e) != _ultima_eroare_model[0]:
			_ultima_eroare_model[0] = repr(e)
			jurnal("modelul motorului nu a putut fi pus in nucleu: %r" % (e,))
		return None


# ------------------------------------------------------------------ transponderele motorului in nucleu

def _nimmanager():
	try:
		from Components.NimManager import nimmanager
	except Exception:
		return None
	return nimmanager


def transpondereMotor(slot):
	"""[(orbital, polarizare, frecventa kHz, rata simboluri/s)] ale satelitilor motorului de pe `slot`, din
	satellites.xml asa cum il are NimManager, fara satelitii de sub orizont cand locul se stie"""
	nm = _nimmanager()
	if nm is None:
		return []
	loc = T.coordonateUsalsNumere(slot)
	lista = []
	for orbital, _nume in T.sateliti(slot):
		if loc is not None and not vizibil(DishMath.orbitalToDegrees(orbital), loc[0], loc[1]):
			continue
		try:
			tps = nm.getTransponders(orbital) or []
		except Exception:
			continue
		for x in tps:
			try:
				if x[0] != 0:
					continue
				frecventa, rata, polarizare = int(x[1]), int(x[2]), int(x[3])
			except (IndexError, TypeError, ValueError):
				continue
			if frecventa > 0 and rata > 0 and 0 <= polarizare <= 3:
				lista.append((int(orbital), polarizare, frecventa, rata))
	return lista


def textTranspondere(lista):
	"""lista ca text pentru hdsSetRotorTransponders: "orbital polarizare frecventa rata" despartite prin ';'"""
	return ";".join("%d %d %d %d" % x for x in lista)


def _amprentaTranspondere():
	"""ce schimba lista: tunerele cu motor, satelitii si locul fiecaruia, lista citita de NimManager (alt obiect la
	recitirea satellites.xml)"""
	nm = _nimmanager()
	parti = [id(getattr(nm, "transponders", None)) if nm is not None else None]
	for slot, _nume in T.tunereCuMotor():
		parti.append((slot, tuple(o for o, _n in T.sateliti(slot)), T.coordonateUsalsNumere(slot)))
	return tuple(parti)


class TranspondereNucleu(object):
	"""pune transponderele satelitilor motorului in nucleu numai cand se schimba amprenta"""

	def __init__(self):
		self.amprenta = None

	def aplica(self):
		sec = T.controlSec()
		if sec is None or not hasattr(sec, "hdsSetRotorTransponders"):
			return None
		amprenta = _amprentaTranspondere()
		if amprenta == self.amprenta:
			return False
		puse = {}
		for slot, _nume in T.tunereCuMotor():
			lista = transpondereMotor(slot)
			sec.hdsSetRotorTransponders(slot, textTranspondere(lista))
			puse[slot] = len(lista)
			jurnal("tunerul %s: %d transpondere ale satelitilor motorului in nucleu (paza probei de semnal dinaintea "
				"comenzii)" % (T.numeTuner(slot), len(lista)))
		self.amprenta = amprenta
		return puse


_transpondere_nucleu = None
_ultima_eroare_tp = [None]


def transpondereNucleu():
	global _transpondere_nucleu
	if _transpondere_nucleu is None:
		_transpondere_nucleu = TranspondereNucleu()
	return _transpondere_nucleu


def aplicaTranspondere():
	"""transponderele motorului in nucleu (nu arunca; aceeasi eroare se scrie o singura data)"""
	try:
		rezultat = transpondereNucleu().aplica()
		_ultima_eroare_tp[0] = None
		return rezultat
	except Exception as e:
		if repr(e) != _ultima_eroare_tp[0]:
			_ultima_eroare_tp[0] = repr(e)
			jurnal("transponderele motorului nu au putut fi puse in nucleu: %r" % (e,))
		return None


def aplica():
	"""chemata de Components/HdsMotorPozitie.py (redarea si bataia de 2 s); nu arunca, iar aceeasi eroare se scrie in
	jurnal o singura data (nu la fiecare bataie). Pune si modelul motorului si transponderele lui in nucleu."""
	aplicaModelul()
	aplicaTranspondere()
	try:
		rezultat = plafon().aplica()
		_ultima_eroare[0] = None
		return rezultat
	except Exception as e:
		if repr(e) != _ultima_eroare[0]:
			_ultima_eroare[0] = repr(e)
			jurnal("plafonul nu a putut fi pus: %r" % (e,))
		return None
