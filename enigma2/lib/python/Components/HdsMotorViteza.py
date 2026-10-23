# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMotorViteza.py - cat se roteste cu adevarat motorul si cat ii ia, invatat din mutarile lui.
#
# De ce: desenul rotirii ajungea pe la jumatate cand antena sosise, spunea ca mai e cam tot atat, apoi sarea la capat,
# si nu invata nimic din mutarile facute. Cauzele, din cod:
#   - ecranul presupunea 0,5 grade pe secunda, adica plafonul nucleului (sec.cpp:864: „un motor foarte incet”, ca
#     nucleul sa nu renunte prea devreme), nu viteza unui motor obisnuit (~1-2 grade pe secunda);
#   - gradele erau diferenta pozitiilor orbitale; motorul se roteste insa cu unghiul orar USALS (din latitudinea si
#     longitudinea locului), care e mai mare (13,0E dintr-un loc din Romania: 13,1 grade orbitale, 14,7 grade de motor);
#   - timpul adevarat al fiecarei mutari se pierdea, deci nimic nu se invata;
#   - la sosire procentul sarea pe 100.
#
# Ce face modulul:
#   - unghiul de rotire al motorului intre doi sateliti, din coordonatele USALS ale tunerului (aceleasi cu care nucleul
#     calculeaza comanda 6E, Components/DishMath.py). Fara coordonate: diferenta orbitala, spusa ca atare in stare
#     (niciodata un loc inventat);
#   - modelul timpului unei mutari: T = t0 + A / v. `A` = gradele de motor, `v` = viteza pe directie (est, vest),
#     `t0` = ce nu e mers (pornirea si confirmarea semnalului: frontend.cpp cere semnal de 5 ori la rand, la 250 ms,
#     dupa o secunda de la comanda), comun pe motor. Potrivit prin cele mai mici patrate pe ultimele mutari, cu doua
#     presupuneri slabe (1,2 grade pe secunda si 2 s) care conteaza numai pana se strang masuratori;
#   - invatarea numai din sosiri adevarate: semnul pus de SET_ROTOR_STOPPED (sec.cpp, hdsRotorArrived), sub timpul
#     maxim al nucleului, drumuri de cel putin GRADE_MIN_INVATARE; o oprire din standby, dintr-un zap in mers sau din
#     comenzile manuale nu se invata, nici mutarea trimisa din nou de plasa de sosire (faraInvatare);
#   - prezicerea se ingheata la inceputul fiecarei mutari, ca o masuratoare noua sa nu mute desenul in mers; dupa
#     sosire, desenul si bara ajung la capat lin, in ALUNECARE_S, fara salt; cand semnalul intarzie, se apropie de
#     capat din ce in ce mai incet, fara sa spuna „gata”.
# Duratele se masoara numai cu ceasul monoton (hdsNowMs din sec.cpp e CLOCK_MONOTONIC, ca time.monotonic): o potrivire
# a orei prin NTP in timpul unei mutari nu strica nimic.
# Pastrare: /etc/enigma2/hds-motor-viteza.json (dosarul setarilor, ca hds-motor-pozitie.json), scris numai cand se
# invata o mutare, in .nou si apoi os.replace. La import nu se atinge nimic din enigma.
#
# Motorul pe 18 V (lib/dvb/hdsrotire.h): pe tunerele care nu masoara curentul, sec.cpp roteste motorul pe 18 V; spre o
# tinta pe 13 V tine 18 V cat dureaza mutarea estimata (hdsRotorTinereMs) si abia apoi pune tensiunea tintei, deci
# semnalul nu poate veni inainte de capatul tinerii. O asemenea sosire, sub tinere + TINERE_PRAG_MS, nu spune viteza
# motorului (a ajuns undeva in timpul tinerii) si nu se invata; prezicerea afisata e cel putin
# tinerea + SEMNAL_DUPA_TINERE_S.
# Mutarile vechi invatate erau mai ales pe 13 V (mai incete); cele noi, pe 18 V, le inlocuiesc treptat.
import json
import math
import os
import time

from Components import DishMath
try:
	from Components import HdsGrade
except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
	import HdsGrade

FISIER = "/etc/enigma2/hds-motor-viteza.json"
# presupunerile de dinainte de prima mutare masurata: un motor obisnuit pe 13 V si ce nu e mers intr-o mutare cu semnal
VITEZA_PRESUPUSA = 1.2
T0_PRESUPUS = 2.0
# de la SET_ROTOR_MOVING pana cand motorul chiar se invarte (comanda DiSEqC pleaca imediat dupa, sec.cpp:879-880)
PORNIRE_S = 0.3
# cate mutari se tin minte pe motor si cat de repede se uita cele vechi (cea mai noua are greutatea 1)
ESANTIOANE_MAX = 12
UITARE = 0.8
# drumurile scurte nu se invata: acolo timpul e mai mult pornire si confirmarea semnalului decat mers
GRADE_MIN_INVATARE = 3.0
VITEZA_MIN = 0.3
VITEZA_MAX = 6.0
T0_MAX = 6.0
# greutatea presupunerilor (t0 ca o masuratoare; viteza ca o mutare de ~3 grade) si legatura dintre directii: o
# directie fara masuratori ia viteza celeilalte, nu presupunerea
GREUTATE_T0 = 1.0
GREUTATE_VITEZA = 10.0
GREUTATE_LEGATURA = 60.0
# o masuratoare prea departe de model (dupa cel putin 4) se pune deoparte; 3 la rand = motorul s-a schimbat, se reia
ABATERE_MIN_S = 4.0
ABATERE_PARTE = 0.5
RESPINSE_PENTRU_RELUARE = 3
# afisajul: pana la PRAG_LINIAR merge drept, apoi se apropie de PLAFON fara sa-l atinga cat motorul merge
PRAG_LINIAR = 0.9
PLAFON = 0.99
# cat tine trecerea lina pana la capat dupa sosire
ALUNECARE_S = 1.2
# aceeasi mutare: aceeasi cheie si pornirea la cel mult atatea milisecunde
POTRIVIRE_MS = 1500
# dupa capatul tinerii pe 18 V, tensiunea tintei, tonul, acordarea si 5 citiri bune la 250 ms (~1,5 s);
# o sosire mai devreme de tinere + TINERE_PRAG_MS a fost tinuta de 18 V
SEMNAL_DUPA_TINERE_S = 1.5
TINERE_PRAG_MS = 3000
# mutarea trimisa din nou de plasa de sosire (Components/HdsMotorPozitie.py, cu plecarea dovedita) dupa una care n-a
# adus semnalul: antena putea fi deja pe drum (motorul ramas pe 13 V), deci timpul ei nu spune viteza; se tine minte
# (tinta, ora) pe slot si se potriveste cu urmatoarea mutare spre aceeasi tinta pornita in atatea milisecunde
FARA_INVATARE_MS = 120000


def acumMs():
	"""ceasul monoton, in milisecunde (acelasi ceas ca hdsNowMs din sec.cpp). Probele de pe PC il inlocuiesc."""
	return time.monotonic() * 1000.0


def jurnal(text):
	print("[HdsMotorViteza] %s" % text)


# ------------------------------------------------------------------ unghiul motorului

def unghiMotor(sat_grade, lat, lon):
	"""unghiul orar al motorului (grade, est pozitiv) pentru satelitul de la `sat_grade` (est pozitiv), din locul
	(lat nord pozitiv, lon est pozitiv); aceeasi formula ca DishMath.gotoAngleValue, fara rotunjirea la zecimi.
	None daca nu se poate calcula (satelit sub orizont, numere stricate)."""
	try:
		unghi_orar = DishMath.hourAngle(sat_grade % 360.0, float(lat), float(lon) % 360.0)
	except (ValueError, ZeroDivisionError, TypeError):
		return None
	if unghi_orar != unghi_orar or DishMath.elevation(sat_grade % 360.0, float(lat), float(lon) % 360.0) < -90:
		return None
	if lat >= 0:
		return 180.0 - unghi_orar
	return -unghi_orar if unghi_orar < 180 else 360.0 - unghi_orar


def diferentaScurta(de_la, la):
	"""drumul cel mai scurt intre doua pozitii orbitale (zecimi), semnat: pozitiv = spre est"""
	diferenta = (la - de_la) % 3600
	if diferenta > 1800:
		diferenta -= 3600
	return diferenta


def drumMotor(de_la, la, coordonate):
	"""(grade de motor, directie, unghiuri) pentru mutarea de la pozitia orbitala `de_la` la `la` (zecimi). Cu
	coordonate: unghiul real de rotire, iar `unghiuri` = (unghiul de plecare, unghiul tintei). Fara coordonate:
	diferenta orbitala, iar `unghiuri` = None."""
	diferenta = diferentaScurta(de_la, la)
	de_la_grade = DishMath.orbitalToDegrees(de_la)
	if coordonate:
		lat, lon = coordonate
		a0 = unghiMotor(de_la_grade, lat, lon)
		a1 = unghiMotor(de_la_grade + diferenta / 10.0, lat, lon)
		if a0 is not None and a1 is not None:
			grade = abs(a1 - a0)
			directie = "" if grade < 1e-6 else ("est" if a1 > a0 else "vest")
			return grade, directie, (a0, a1)
	directie = "" if diferenta == 0 else ("est" if diferenta > 0 else "vest")
	return abs(diferenta) / 10.0, directie, None


def _normalizeaza(grade):
	grade = (grade + 180.0) % 360.0 - 180.0
	return 180.0 if grade == -180.0 else grade


def orbitalLa(de_la, la, coordonate, unghiuri, parte):
	"""unde e indreptata antena (grade orbitale, est pozitiv) cand s-a facut `parte` din rotirea motorului. Cu unghiuri:
	unghiul motorului se imparte liniar, iar satelitul spre care arata se afla prin injumatatire (unghiul creste cu
	longitudinea). Fara: impartire liniara in grade orbitale."""
	diferenta = diferentaScurta(de_la, la) / 10.0
	start = DishMath.orbitalToDegrees(de_la)
	if unghiuri is None or not coordonate or parte <= 0.0:
		return _normalizeaza(start + diferenta * max(0.0, parte))
	if parte >= 1.0:
		return _normalizeaza(start + diferenta)
	lat, lon = coordonate
	a0, a1 = unghiuri
	tinta = a0 + (a1 - a0) * parte
	jos, sus = (start, start + diferenta) if diferenta >= 0 else (start + diferenta, start)
	for _i in range(40):
		mijloc = (jos + sus) / 2.0
		unghi = unghiMotor(mijloc, lat, lon)
		if unghi is None:
			return _normalizeaza(start + diferenta * parte)
		if unghi < tinta:
			jos = mijloc
		else:
			sus = mijloc
	return _normalizeaza((jos + sus) / 2.0)


# ------------------------------------------------------------------ modelul si invatarea

def _rezolva(m, b):
	"""sistem liniar mic (eliminare Gauss cu pivot); None daca e singular"""
	n = len(b)
	a = [list(m[i]) + [b[i]] for i in range(n)]
	for c in range(n):
		p = max(range(c, n), key=lambda r: abs(a[r][c]))
		if abs(a[p][c]) < 1e-12:
			return None
		a[c], a[p] = a[p], a[c]
		for r in range(n):
			if r != c:
				f = a[r][c] / a[c][c]
				for k in range(c, n + 1):
					a[r][k] -= f * a[c][k]
	return [a[i][n] / a[i][i] for i in range(n)]


def potriveste(esantioane):
	"""Modelul T = t0 + A / v din mutarile masurate [(directie, grade, secunde)], cea mai noua la sfarsit. Necunoscutele
	sunt t0 si 1/v pe fiecare directie; presupunerile slabe si legatura dintre directii tin sistemul rezolvabil si cu o
	singura masuratoare. Intoarce {"t0", "viteza": {"est", "vest"}, "masurate": {"est", "vest"}}."""
	k0 = 1.0 / VITEZA_PRESUPUSA
	m = [[0.0] * 3 for _i in range(3)]
	b = [0.0] * 3

	def adauga(rand, tinta, greutate):
		for i in range(3):
			b[i] += greutate * rand[i] * tinta
			for j in range(3):
				m[i][j] += greutate * rand[i] * rand[j]

	adauga((1.0, 0.0, 0.0), T0_PRESUPUS, GREUTATE_T0)
	adauga((0.0, 1.0, 0.0), k0, GREUTATE_VITEZA)
	adauga((0.0, 0.0, 1.0), k0, GREUTATE_VITEZA)
	adauga((0.0, 1.0, -1.0), 0.0, GREUTATE_LEGATURA)
	masurate = {"est": 0, "vest": 0}
	n = len(esantioane)
	for i, (directie, grade, secunde) in enumerate(esantioane):
		greutate = UITARE ** (n - 1 - i)
		rand = (1.0, grade, 0.0) if directie == "est" else (1.0, 0.0, grade)
		adauga(rand, secunde, greutate)
		masurate["est" if directie == "est" else "vest"] += 1
	x = _rezolva(m, b) or [T0_PRESUPUS, k0, k0]
	t0 = x[0]
	if not 0.0 <= t0 <= T0_MAX:
		# t0 in afara marginilor: se fixeaza la margine si se potrivesc din nou numai vitezele
		t0 = min(T0_MAX, max(0.0, t0))
		m2 = [[m[1][1], m[1][2]], [m[2][1], m[2][2]]]
		b2 = [b[1] - m[1][0] * t0, b[2] - m[2][0] * t0]
		x = [t0] + (_rezolva(m2, b2) or [k0, k0])
	viteze = {}
	for i, directie in ((1, "est"), (2, "vest")):
		k = x[i]
		viteze[directie] = VITEZA_MAX if k <= 1.0 / VITEZA_MAX else min(VITEZA_MAX, max(VITEZA_MIN, 1.0 / k))
	return {"t0": t0, "viteza": viteze, "masurate": masurate}


class Calibrare(object):
	"""mutarile masurate si modelul fiecarui motor (cheia = slotul tunerului), pastrate in `fisier`"""

	def __init__(self, fisier=FISIER):
		self.fisier = fisier
		self.sloturi = self._citeste()
		self._modele = {}

	def _citeste(self):
		try:
			with open(self.fisier) as f:
				date = json.load(f)
		except (IOError, OSError):
			return {}
		except Exception as e:
			jurnal("fisierul vitezei motorului e stricat, il ignor: %r" % (e,))
			return {}
		sloturi = {}
		for cheie, valoare in (date.get("sloturi") or {}).items():
			if isinstance(valoare, dict):
				sloturi[str(cheie)] = {"esantioane": self._curata(valoare.get("esantioane")),
					"respinse": self._curata(valoare.get("respinse"))}
		return sloturi

	@staticmethod
	def _curata(lista):
		bune = []
		for e in lista or []:
			try:
				directie, grade, secunde = e[0], float(e[1]), float(e[2])
			except (TypeError, ValueError, IndexError):
				continue
			if directie in ("est", "vest") and grade > 0 and secunde > 0:
				bune.append((directie, grade, secunde))
		return bune[-ESANTIOANE_MAX:]

	def _scrie(self):
		nou = self.fisier + ".nou"
		date = {"versiune": 1, "sloturi": dict((k, {"esantioane": [list(e) for e in v["esantioane"]],
			"respinse": [list(e) for e in v["respinse"]]}) for k, v in self.sloturi.items())}
		try:
			with open(nou, "w") as f:
				json.dump(date, f, sort_keys=True)
				f.flush()
				os.fsync(f.fileno())
			os.replace(nou, self.fisier)
			return True
		except Exception as e:
			jurnal("viteza motorului nu a putut fi scrisa: %r" % (e,))
			try:
				os.remove(nou)
			except OSError:
				pass
			return False

	def _slot(self, slot):
		return self.sloturi.setdefault(str(slot), {"esantioane": [], "respinse": []})

	def model(self, slot):
		cheie = str(slot)
		if cheie not in self._modele:
			self._modele[cheie] = potriveste(self.sloturi.get(cheie, {}).get("esantioane", []))
		return self._modele[cheie]

	def prezice(self, slot, grade, directie):
		"""durata asteptata a unei mutari, din modelul de acum: {T, mers, pornire, viteza, t0, invatata, masurate}"""
		model = self.model(slot)
		directie = directie if directie in ("est", "vest") else "est"
		viteza = model["viteza"][directie]
		mers = max(0.0, grade) / viteza
		t0 = model["t0"]
		masurate = model["masurate"]
		return {"T": t0 + mers, "mers": mers, "pornire": min(PORNIRE_S, t0), "viteza": viteza, "t0": t0,
			"invatata": masurate["est"] + masurate["vest"] > 0, "masurate": masurate[directie], "directie": directie}

	def invata(self, slot, directie, grade, secunde):
		"""o mutare masurata; intoarce „invatata”, „respinsa” sau „reluata” (3 respinse la rand = alt motor)"""
		date = self._slot(slot)
		model = self.model(slot)
		if len(date["esantioane"]) >= 4:
			asteptat = model["t0"] + grade / model["viteza"][directie]
			if abs(secunde - asteptat) > max(ABATERE_MIN_S, ABATERE_PARTE * asteptat):
				date["respinse"] = (date["respinse"] + [(directie, grade, secunde)])[-RESPINSE_PENTRU_RELUARE:]
				if len(date["respinse"]) >= RESPINSE_PENTRU_RELUARE:
					date["esantioane"], date["respinse"] = list(date["respinse"]), []
					rezultat = "reluata"
				else:
					rezultat = "respinsa"
				self._modele.pop(str(slot), None)
				self._scrie()
				return rezultat
		date["respinse"] = []
		date["esantioane"] = (date["esantioane"] + [(directie, grade, secunde)])[-ESANTIOANE_MAX:]
		self._modele.pop(str(slot), None)
		self._scrie()
		return "invatata"


_calibrare = None


def calibrare():
	global _calibrare
	if _calibrare is None:
		_calibrare = Calibrare()
	return _calibrare


# ------------------------------------------------------------------ o mutare: prezicerea inghetata si afisajul

_miscari = {}
_fara_invatare = {}


def faraInvatare(slot, la):
	"""urmatoarea mutare spre `la` pe slot, pornita in FARA_INVATARE_MS de acum, nu se invata (reluarea plasei)"""
	_fara_invatare[slot] = (la, acumMs())


def miscare(slot, de_la, la, cmd, gotoxx, secunde_max, trecut_ms, oprit_de_ms, coordonate, tinere_ms=0):
	"""Intrarea mutarii curente a slotului, cu prezicerea inghetata la prima vedere. Aceeasi mutare = aceeasi pereche
	plecare/tinta/comanda si aceeasi pornire (ceasul monoton minus cat a trecut). `coordonate` = functie(slot) sau
	None; se cheama o singura data pe mutare. `tinere_ms` = cat tine nucleul 18 V dupa comanda, 0 =
	deloc."""
	acum = acumMs()
	pornire = acum - max(0, trecut_ms) - (oprit_de_ms if oprit_de_ms is not None and oprit_de_ms >= 0 else 0)
	cheie = (de_la, la, cmd, gotoxx, secunde_max)
	e = _miscari.get(slot)
	if e is not None and e["cheie"] == cheie and abs(e["pornire_ms"] - pornire) <= POTRIVIRE_MS:
		return e
	loc = None
	if coordonate is not None:
		try:
			loc = coordonate(slot)
		except Exception:
			loc = None
	grade, directie, unghiuri = drumMotor(de_la, la, loc)
	prezis = calibrare().prezice(slot, grade, directie)
	tinere_ms = max(0, int(tinere_ms or 0))
	if tinere_ms > 0:
		# semnalul vine abia dupa tinerea pe 18 V
		prezis = dict(prezis, T=max(prezis["T"], tinere_ms / 1000.0 + SEMNAL_DUPA_TINERE_S))
	f = _fara_invatare.get(slot)
	fara = f is not None and f[0] == la and f[1] - POTRIVIRE_MS <= pornire <= f[1] + FARA_INVATARE_MS
	if fara:
		del _fara_invatare[slot]
	e = {"cheie": cheie, "pornire_ms": pornire, "slot": slot, "de_la": de_la, "la": la, "grade": grade,
		"directie": directie, "unghiuri": unghiuri, "coordonate": loc, "prezis": prezis,
		"judecata": False, "rezultat": "", "tinere_ms": tinere_ms, "fara_invatare": fara}
	_miscari[slot] = e
	return e


def esteSosire(semn, trecut_ms, secunde_max):
	"""True daca oprirea e o sosire din care se poate invata. `semn` = hdsRotorArrived: 2 = dupa semnal; 1 = fara
	semnal (motorul oprit dupa curent, sau timpul maxim trecut); 0 = standby, zap in mers, oprirea noastra; None = o
	imagine fara semn (nu se invata nimic: fara el o oprire nu se poate deosebi de o sosire). La timpul maxim nucleul
	renunta cu motorul poate inca in mers, deci nu e o masuratoare."""
	if semn is None or semn <= 0:
		return False
	if semn == 2:
		return True
	return secunde_max is None or secunde_max <= 0 or trecut_ms < secunde_max * 1000


def judeca(e, semn, trecut_ms, secunde_max):
	"""o singura data pe mutare, dupa oprire: se invata din ea sau nu. Intoarce motivul, pentru jurnal si probe."""
	if e["judecata"]:
		return e["rezultat"]
	e["judecata"] = True
	secunde = trecut_ms / 1000.0
	if e.get("fara_invatare"):
		# reluarea plasei de sosire: antena putea fi deja pe drum, timpul nu spune viteza
		e["rezultat"] = "reluare dupa o mutare fara semnal"
	elif not esteSosire(semn, trecut_ms, secunde_max):
		e["rezultat"] = "nu e sosire"
	elif e.get("tinere_ms", 0) > 0 and trecut_ms < e["tinere_ms"] + TINERE_PRAG_MS:
		# a ajuns cat tinea 18 V: timpul e al tinerii, nu al motorului
		e["rezultat"] = "tinuta pe 18 V"
	elif e["directie"] not in ("est", "vest") or e["grade"] < GRADE_MIN_INVATARE:
		e["rezultat"] = "drum scurt"
	elif not VITEZA_MIN / 2.0 <= e["grade"] / max(secunde, 0.001) <= VITEZA_MAX:
		e["rezultat"] = "timp nepotrivit"
	else:
		e["rezultat"] = calibrare().invata(e["slot"], e["directie"], e["grade"], secunde)
		jurnal("mutare de %.1f grade spre %s in %.1f s: %s" % (e["grade"], e["directie"], secunde, e["rezultat"]))
	return e["rezultat"]


def _aproape(parte):
	"""drept pana la PRAG_LINIAR, apoi tot mai incet spre PLAFON, fara sa-l atinga (derivata continua)"""
	if parte <= PRAG_LINIAR:
		return max(0.0, parte)
	loc = PLAFON - PRAG_LINIAR
	return PRAG_LINIAR + loc * (1.0 - math.exp(-(parte - PRAG_LINIAR) / loc))


def _lin(pornire, parte):
	"""de la `pornire` spre 1, incetinind la capat (fara salt la inceput si fara oprire bruta la sfarsit)"""
	g = min(1.0, max(0.0, parte))
	return pornire + (1.0 - pornire) * (1.0 - (1.0 - g) * (1.0 - g))


def parti(prezis, trecut_s, oprit_de_s=None):
	"""Afisajul unei mutari dupa prezicerea ei inghetata. `trecut_s` = cat a mers (la oprire: tot drumul), `oprit_de_s`
	= None cat merge, altfel de cand s-a oprit. Intoarce {drum, timp, secunde_ramase, intarziat, alunecare}:
	`drum` = cat din rotire s-a facut (pentru antena desenata si gradele ramase), `timp` = cat din asteptare (bara);
	amandoua sub PLAFON cat motorul merge si 1 la capatul alunecarii."""
	total = max(0.1, prezis["T"])
	mers = max(0.1, prezis["mers"])
	pornire = prezis.get("pornire", 0.0)
	timp = _aproape(trecut_s / total)
	drum = _aproape(max(0.0, trecut_s - pornire) / mers)
	if oprit_de_s is None:
		intarziat = trecut_s >= total
		return {"drum": drum, "timp": timp, "secunde_ramase": None if intarziat else total - trecut_s,
			"intarziat": intarziat, "alunecare": False}
	parte = oprit_de_s / ALUNECARE_S
	return {"drum": _lin(drum, parte), "timp": _lin(timp, parte), "secunde_ramase": 0.0, "intarziat": False,
		"alunecare": parte < 1.0}


def vitezaText(prezis):
	"""randul cu viteza motorului, pe ecran si in web (acelasi text)"""
	viteza = HdsGrade.numar(prezis["viteza"], 1)
	if not prezis["invatata"]:
		return _("Viteza motorului: %s grade/s, presupusă până la prima mutare măsurată") % viteza
	directie = _("spre est") if prezis["directie"] == "est" else _("spre vest")
	n = prezis["masurate"]
	if n <= 0:
		return _("Viteza motorului: %s grade/s %s, luată din mutările în cealaltă direcție") % (viteza, directie)
	try:
		from Components.HdsIndexCanale import ngettext
	except Exception:
		def ngettext(unu, multe, n):
			return unu if n == 1 else multe
	return _("Viteza motorului: %s grade/s %s, învățată din %s") % (viteza, directie,
		ngettext("%d mutare", "%d mutări", n) % n)
