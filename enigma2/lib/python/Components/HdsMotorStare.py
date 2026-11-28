# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMotorStare.py - starea rotirii motorului de antena, intr-un singur loc.
#
# Acelasi dictionar il foloseste si ecranul de pe televizor (Screens/HdsDishMotor.py) si ruta din interfata
# web (Plugins/Extensions/HdsWebControl), ca sa nu existe doua adevaruri despre acelasi motor.
#
# De unde vine fiecare cifra (nimic nu e inventat):
#   - se misca / nu se misca        eDVBSatelliteEquipmentControl.isRotorMoving() (lib/dvb/sec.cpp:1503)
#   - slotul care se misca          hdsRotorMovingSlot()      (adaugat de noi in sec.cpp)
#   - pozitia de plecare            hdsRotorFromOrbital()  = curRotorPos din sec.cpp:366 (ROTOR_POS,
#                                   ultima pozitie CONFIRMATA; -1 cand inca nu a fost confirmata niciuna)
#   - pozitia tinta                 hdsRotorToOrbital()    = sat.orbital_position din sec.cpp:913
#   - comanda pusa pe fir           hdsRotorCmd() + hdsRotorUsesGotoxx() (6E unghi / 6B pozitie memorata)
#   - timpul maxim al motorului     hdsRotorSeconds()      = mrt din sec.cpp:854-863
#   - cat a trecut de la pornire    hdsRotorElapsedMs()    (ceasul porneste la SET_ROTOR_MOVING)
#   - numele satelitilor            nimmanager.getSatName() (satellites.xml)
#   - semnalul la sosire            frontendInfo().getFrontendStatus() al serviciului curent
#   - comenzile manuale             Components/HdsMotorComenzi.stareComenzi() (pas, miscare, pozitie memorata):
#                                   directia, octetii pusi pe fir si oprirea automata vin de acolo, pentru ca la
#                                   ele nucleul nu stie nici tinta, nici octetii
#
# Ce NU se poate sti: pozitia din timpul mersului. Motorul nu o raporteaza (comanda de stare 64 cere un canal
# de intoarcere pe care receptoarele nu il citesc). De aceea pozitia curenta e ESTIMATA intre plecare si
# sosire, iar campul `estimat` e adevarat: pe ecran si in web se scrie „estimat", niciodata ca fapt.

#
# Timpul
# si drumul nu mai vin din 0,5 grade pe secunda (plafonul nucleului, sec.cpp:864, nu viteza motorului) si din diferenta
# pozitiilor orbitale, ci din Components/HdsMotorViteza.py: unghiul real de rotire (USALS, din coordonatele tunerului),
# viteza invatata din mutarile adevarate ale motorului, prezicerea inghetata pe mutare si alunecarea lina la sosire.
# Plafonul nucleului (mrt) ramane neatins: se schimba numai ce se arata.
#
# dupa flash ecranul a scris ~6 minute "Antena se roteste", cu plecarea
# nestiuta, apoi "Antena a ajuns, inca fara semnal"; nimic masurat nu spunea ca antena se misca sau ca a ajuns. Acum:
#   - plecarea nestiuta (`plecare_nestiuta`): se spune ce se stie: comanda a plecat spre motor, de unde pleaca antena nu
#     se stie, iar timpul e o estimare (cel mult cat mai e pana la timpul maxim al nucleului, hdsRotorSeconds; il pune
#     Components/HdsMotorPlafon.py din viteza invatata);
#   - timpul maxim trecut fara semnal (`asteptare_trecuta`: hdsRotorArrived = 1 si tot timpul maxim trecut): numai
#     faptele masurate (cat s-a asteptat, ca semnalul nu a venit), fara "a ajuns", fara antena desenata pe tinta;
#   - `ramas_text`: randul de sub bara, acelasi pe televizor si in web, cand cifrele obisnuite nu se pot spune.
#   - MOT1 (0.8.0, 26.11 22:29: fereastra de dupa repornire "pare eroare"): titlul spune calm "Antena se muta pe
#     19,2°E", iar randul de jos "Pozitia de dinainte nu e cunoscuta; mutarea poate dura pana la ...". Ultima pozitie
#     prinsa cu semnal (HdsMotorPozitie.pozitieConfirmata, tinuta minte si cand readucerea uita pozitia) da: tinta egala
#     cu ea = mutare tacuta (`tacut`, fara panou automat); alta = plecarea estimata, cu antena animata dupa viteza; fara
#     ea, bara dupa timp (`procent_estimat`). Cheile vechi raman "nu se stie" (-1 / null).
# CABLUL: comanda spre motor nu are raspuns, deci fara cablu antena pare ca se roteste, iar nucleul asteapta degeaba
# semnalul (~90 s). Cand tot timpul maxim trece fara semnal (`asteptare_trecuta`; oprirea dupa curent inseamna ca
# motorul raspunde, deci cablul e), titlul panoului (acelasi pe televizor si in web) spune o data pe
# canal sa se verifice cablul (`indemn_cablu`), iar panoul ramane MILISECUNDE_INDEMN_CABLU ca sa se poata citi.

import os
import sys
import time

from Components.DishMath import orbitalToDegrees
from Components import HdsMotorViteza as V
try:
	from Components import HdsGrade
except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
	import HdsGrade

# cat timp ramane ecranul dupa ce motorul s-a oprit, ca utilizatorul sa apuce sa vada ca a ajuns
MILISECUNDE_DUPA_SOSIRE = 6000
# cat ramane panoul dupa o mutare terminata fara semnal, cand spune sa se verifice cablul (o data pe canal)
MILISECUNDE_INDEMN_CABLU = 15000
# aceeasi mutare, citita de mai multe ori: ora opririi (acum - de cand s-a oprit) se misca cel mult cu atat
MARJA_INDEMN_MS = 2000
# canalul (sau, fara canal, tunerul si pozitia) -> ora opririi mutarii la care s-a spus de cablu
_INDEMNURI = {}
# cat poate fi notata oprirea in nucleu dupa oprirea trimisa de comenzi si sa fie tot a ei (setRotorMoving(false) e chemat
# chiar inainte de ora opririi tinuta de comenzi; doua ceasuri, deci o marja)
MARJA_OPRIRE_MS = 200

# Cine a cerut ca panoul automat (HdsDishMotor, pus peste program de InfoBar) sa stea ascuns: ecranul „Rotirea antenei"
# (altfel acelasi desen ar aparea de doua ori, unul peste altul) si „Gasire semnal" (revizia semnal 4.5).
_ascuns_de = set()


def panou_automat_oprit(cine, da_nu):
	"""`cine` (un nume) cere ca panoul automat sa stea ascuns (da_nu=True) sau renunta la cerere (False)"""
	if da_nu:
		_ascuns_de.add(cine)
	else:
		_ascuns_de.discard(cine)


def panouAutomatAscuns():
	return bool(_ascuns_de)


def readucereInCurs():
	"""True cat merge mutarea pornita de readucerea antenei (Components/HdsMotorPozitie.py): pe
	televizor nu se spune nimic despre ea"""
	return "readucere" in _ascuns_de


def _readucere():
	"""starea readucerii (Components/HdsMotorPozitie.stareReaducere) pentru /api/motor; fara import"""
	m = sys.modules.get("Components.HdsMotorPozitie")
	f = getattr(m, "stareReaducere", None) if m is not None else None
	if f is None:
		return {"activa": False}
	try:
		return f()
	except Exception:
		return {"activa": False}


def _sec():
	try:
		from enigma import eDVBSatelliteEquipmentControl
		return eDVBSatelliteEquipmentControl.getInstance()
	except Exception:
		return None


def _numeSatelit(orbital):
	if orbital is None or orbital < 0:
		return ""
	try:
		from Components.NimManager import nimmanager
		nume = nimmanager.getSatName(orbital)
	except Exception:
		return ""
	return nume if nume and nume != "N/A" else ""


def gradeText(grade):
	"""13.0 -> „13,0 grade Est"; -5.0 -> „5,0 grade Vest"; None -> „necunoscut"; separatorul zecimal al limbii meniului
	(„13.0 degrees East" in engleza, Components/HdsGrade.py)"""
	if grade is None:
		return _("necunoscut")
	# „grade” se traduce si el
	return _("%s grade %s") % (HdsGrade.numar(abs(grade), 1), _("Est") if grade >= 0 else _("Vest"))


_diferentaScurta = V.diferentaScurta


def _semnalPrins():
	"""(are_semnal, se_stie): semnalul serviciului care ruleaza, fara sa deschidem noi vreun tuner.
	Se ia din NavigationInstance, nu dintr-o sesiune anume, ca sa mearga la fel si din interfata web.
	La serviciu getFrontendStatus() nu are argument si intoarce dictionarul (iservice.h:452, servicedvb.cpp:2061);
	forma veche, cu dictionarul de umplut, ramane numai pentru imagini vechi (inainte, apelul cu argument
	arunca TypeError, inghitit mai jos, deci „semnal prins" nu aparea niciodata)."""
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
		serviciu = nav and nav.getCurrentService()
		info = serviciu and serviciu.frontendInfo()
		if info is None:
			return False, False
		try:
			stare = info.getFrontendStatus()
		except TypeError:
			stare = {}
			info.getFrontendStatus(stare)
		stare = stare or {}
		if "tuner_locked" not in stare:
			return False, False
		return bool(stare.get("tuner_locked")), True
	except Exception:
		return False, False


# lista satelitilor tunerului cu motor, pentru punctele de pe bolta (ecranul si pagina web); tinuta minte pe tuner
SATELITI_TINUTI_S = 30.0
_sateliti_tinuti = {}


def desenDinSpate():
	"""(din_spate, sud) pentru desenul rotirii (Screens/HdsDishMotor.py si pagina web /motor): setarea
	config.usage.hds_motor_din_spate (Da, ca implicitul din 0.7.7, cand nu se poate citi) si longitudinea locului antenei in grade (Components/
	HdsLocul.py; None cand locul nu e stabilit: atunci desenul e numai oglindit, fara sudul in varf)"""
	try:
		from Components.config import config
		din_spate = bool(config.usage.hds_motor_din_spate.value)
	except Exception:
		din_spate = True
	sud = None
	if din_spate:
		try:
			from Components import HdsLocul
			loc = HdsLocul.locul()
			if loc is not None:
				sud = loc[1] / 1000.0
		except Exception:
			sud = None
	return din_spate, sud


# ------------------------------------------------------------------ bolta intreaga (dorinelu, forum 795, 14.11.2026)
# Cu locul antenei stabilit, desenul rotirii (televizor si web) arata tot arcul vazut din loc: capetele sunt orizontul din vest
# si din est, sudul locului (unghiul motorului 0, "pozitia 0" USALS) e in varful curbei, iar punctele stau dupa unghiul motorului
# (Components/HdsMotorViteza.unghiMotor), adica dupa cum se roteste antena. Marginile vin din Components/HdsMotorPlafon.margini
# (acelasi calcul ca nucleul, DishMath). O limita a motorului pusa din "Rotirea antenei", cu pozitia stiuta (HdsMotorComenzi,
# jurnalul limitelor), se marcheaza pe bolta; satelitii de dincolo de ea sau de sub orizont sunt "in afara".
CALE_LAMEDB = "/etc/enigma2/lamedb"
_pozitii_lamedb = {"cheie": None, "pozitii": frozenset()}


def pozitiiCuCanale(cale=None):
	"""Pozitiile orbitale (0..3599) care au transpondere in lista de canale (lamedb 4 sau 5), citite din nou numai cand
	fisierul se schimba. Pe bolta intreaga se deseneaza numai satelitii folositi, nu tot satellites.xml."""
	cale = cale or CALE_LAMEDB
	try:
		st = os.stat(cale)
		cheie = (cale, st.st_mtime, st.st_size)
	except OSError:
		return frozenset()
	if _pozitii_lamedb["cheie"] == cheie:
		return _pozitii_lamedb["pozitii"]
	pozitii = set()
	try:
		with open(cale, encoding="utf-8", errors="replace") as f:
			in_transpondere = False
			for rand in f:
				rand = rand.strip()
				if rand == "transponders":
					in_transpondere = True
					continue
				if rand in ("end", "services"):
					in_transpondere = False
				if rand.startswith("t:"):
					rand, in_transpondere = rand[2:], True
				if not in_transpondere or len(rand) < 8 or rand[8:9] != ":":
					continue
				try:
					orbital = int(rand[:8], 16) >> 16
				except ValueError:
					continue
				if 0 <= orbital < 3600:
					pozitii.add(orbital)
	except (IOError, OSError):
		pass
	_pozitii_lamedb["cheie"], _pozitii_lamedb["pozitii"] = cheie, frozenset(pozitii)
	return _pozitii_lamedb["pozitii"]


# Limitele practice (0.7.7, SCN; dorinelu, forum 795 #2676, Berlin, antena de 90 cm: "prinde pana pe la 56E si 30V"): cu
# setarea config.usage.hds_motor_elevatie_min (Elevatia minima in desenul rotirii, 0-30 grade) capetele boltii sunt unde
# satelitii ajung la acea elevatie, nu la orizontul geometric; din Berlin 18 grade dau ~56E si ~30V (DishMath). 0 = orizontul,
# ca pana acum. Numai desenul (televizor si web): rotirea, plafonul de timp al nucleului si listele scanarii raman pe orizont
# (Components/HdsMotorPlafon.py neatins). Satelitii dintre capat si orizont se deseneaza "in afara", ca cei sub orizont.
ELEVATIE_DESEN_MAX = 30


def elevatieDesen():
	"""Elevatia minima a desenului rotirii, in grade (0..ELEVATIE_DESEN_MAX); 0 cand setarea nu se poate citi."""
	try:
		from Components.config import config
		return max(0.0, min(float(ELEVATIE_DESEN_MAX), float(config.usage.hds_motor_elevatie_min.value)))
	except Exception:
		return 0.0


def _vizibilDesen(grade, lat, lon, elevatie=0.0):
	"""Satelitul de la `grade` (est pozitiv) e in desen: deasupra orizontului (elevatie 0, HdsMotorPlafon.vizibil) sau cel
	putin la `elevatie` grade deasupra lui"""
	from Components import HdsMotorPlafon as P
	if elevatie <= 0.0:
		return P.vizibil(grade, lat, lon)
	try:
		from Components import DishMath
		return DishMath.elevation(grade % 360.0, float(lat), float(lon) % 360.0) >= elevatie
	except (ValueError, ZeroDivisionError, TypeError):
		return False


def _capeteGrade(lat, lon, elevatie=0.0):
	"""(gradele satelitului de la capatul din vest, din est), est pozitiv, din locul (lat, lon): orizontul (elevatie 0) sau
	elevatia data; None fara arc"""
	if not _vizibilDesen(lon, lat, lon, elevatie):
		return None
	capete = []
	for semn in (-1.0, 1.0):
		jos, sus = 0.0, 90.0
		for _i in range(40):
			mijloc = (jos + sus) / 2.0
			if _vizibilDesen(lon + semn * mijloc, lat, lon, elevatie):
				jos = mijloc
			else:
				sus = mijloc
		g = lon + semn * jos
		capete.append(((g + 180.0) % 360.0) - 180.0)
	return capete[0], capete[1]


def _marginiDesen(lat, lon, elevatie):
	"""(unghiul motorului la capatul de vest, la cel de est) ale arcului de la elevatia data; la 0 chiar
	HdsMotorPlafon.margini (orizontul). None fara arc."""
	from Components import HdsMotorPlafon as P
	if elevatie <= 0.0:
		return P.margini(lat, lon)
	capete = _capeteGrade(lat, lon, elevatie)
	if capete is None:
		return None
	unghiuri = [V.unghiMotor(g, lat, lon) for g in capete]
	if None in unghiuri:
		return None
	return min(unghiuri), max(unghiuri)


def boltaVizibila(slot=None):
	"""Bolta intreaga pentru locul stabilit, sau None (locul nestabilit, nimic vizibil, eroare): {"a": unghiul motorului la
	capatul cel mai departat (scara desenului), "unghi_vest", "unghi_est", "grade_vest", "grade_est" (satelitul de la capat:
	orizontul sau elevatia minima aleasa, elevatieDesen), "elevatie" (cea folosita), "sud" (longitudinea locului = satelitul
	din sud), "lat", "limita_vest", "limita_est" (unghiul motorului al limitei puse, sau None)}. Cand din loc niciun satelit
	nu ajunge la elevatia aleasa (de pilda 30 de grade din nordul Scandinaviei), capetele raman la orizont."""
	try:
		from Components import HdsLocul
		loc = HdsLocul.locul() if HdsLocul.stabilit() else None
		if loc is None:
			return None
		lat, lon = loc[0] / 1000.0, loc[1] / 1000.0
		elevatie = elevatieDesen()
		margini = _marginiDesen(lat, lon, elevatie)
		capete = _capeteGrade(lat, lon, elevatie)
		if elevatie > 0.0 and (margini is None or capete is None):
			elevatie = 0.0
			margini = _marginiDesen(lat, lon, elevatie)
			capete = _capeteGrade(lat, lon, elevatie)
		if margini is None or capete is None:
			return None
	except Exception:
		return None
	b = {"a": max(abs(margini[0]), abs(margini[1]), 1.0), "unghi_vest": margini[0], "unghi_est": margini[1],
		"grade_vest": capete[0], "grade_est": capete[1], "elevatie": elevatie, "sud": lon, "lat": lat, "limita_vest": None,
		"limita_est": None}
	try:
		from Components import HdsMotorComenzi as C
		info = C.limiteInfo(slot)
		if info.get("stare") != "oprite":
			for parte in ("vest", "est"):
				orbital = (info.get(parte) or {}).get("orbital", -1)
				if orbital is not None and 0 <= int(orbital) < 3600:
					b["limita_" + parte] = V.unghiMotor(orbitalToDegrees(int(orbital)), lat, lon)
	except Exception:
		pass
	return b


def unghiPeBolta(grade, bolta):
	"""(unghiul motorului, in_afara) pentru satelitul de la `grade` (est pozitiv): in_afara = sub orizont, sub elevatia minima
	a desenului (bolta["elevatie"]) sau dincolo de o limita a motorului. Departe sub orizont (fara unghi in formula) unghiul
	e pus dincolo de capatul boltii, de partea lui."""
	unghi = V.unghiMotor(grade, bolta["lat"], bolta["sud"])
	afara = unghi is None or not _vizibilDesen(grade, bolta["lat"], bolta["sud"], bolta.get("elevatie", 0.0))
	if unghi is None:
		# departe sub orizont (formula nu da unghi): dincolo de capatul boltii, de partea lui, ca sa fie totusi marcat
		diferenta = ((grade - bolta["sud"] + 540.0) % 360.0) - 180.0
		unghi = (bolta["a"] + 30.0) * (1.0 if diferenta >= 0 else -1.0)
	if unghi is not None:
		if bolta.get("limita_vest") is not None and unghi < bolta["limita_vest"] - 0.05:
			afara = True
		if bolta.get("limita_est") is not None and unghi > bolta["limita_est"] + 0.05:
			afara = True
	return unghi, afara


def satelitiPeArc(slot):
	"""[(orbital, grade)] pentru satelitii din lista tunerului cu motor (Components/HdsMotorTuner.sateliti: setarile
	tunerului si satellites.xml), ca puncte pe bolta in ecranul de rotire si in pagina web. Se cer prin modul (nu prin
	functia importata), deci lista se poate inlocui la probe. Tinuta minte SATELITI_TINUTI_S secunde pe tuner, ca
	pagina web sa nu o ceara din nou la fiecare citire. Goala daca nu se poate citi (niciun tuner, imagine veche)."""
	if slot is None or slot < 0:
		return []
	acum = time.monotonic()
	tinut = _sateliti_tinuti.get(slot)
	if tinut is not None and 0 <= acum - tinut[0] < SATELITI_TINUTI_S:
		return tinut[1]
	try:
		from Components import HdsMotorTuner
		lista = [(int(orbital), orbitalToDegrees(int(orbital))) for orbital, _nume in HdsMotorTuner.sateliti(slot)]
	except Exception:
		lista = []
	_sateliti_tinuti[slot] = (acum, lista)
	return lista


def stareMotor():
	"""dictionarul complet al rotirii. `activ` spune daca merita aratat ceva."""
	return _suprapuneComenzile(_stareNucleu())


def _suprapuneComenzile(stare):
	"""La o miscare manuala (pas, miscare fara oprire, pozitie memorata) nucleul stie numai ca motorul se misca: tinta
	lipseste, iar la pas si la miscare nici octetii nu ii are. Directia, octetii, oprirea automata si textul vin atunci
	de la comenzi. Cheile noi (`manual`, `actiune`, `oprire_automata_s`, `comenzi`, `curent_text`) sunt mereu prezente;
	nimic vechi nu se scoate si nu se redenumeste (ruta /api/motor si test_motor_web.py raman la fel)."""
	try:
		from Components.HdsMotorComenzi import stareComenzi
		c = stareComenzi()
	except Exception:
		c = None
	if not c:
		return stare
	stare["comenzi"] = c
	if stare["slot"] < 0 or c.get("slot") != stare["slot"]:
		return stare
	if c.get("actiune") == "satelit" and c.get("stare") == "oprire":
		# „Mergi la satelit" oprit, cat se trimite oprirea: acordul de referinta (HdsMotorComenzi._opreste, revizia M1)
		# a pus deja setRotorMoving(false) in nucleu (frontend.cpp:2471-2472), deci nucleul spune „a ajuns", cu
		# pozitia tintei si bara plina. De fapt motorul merge pana pleaca oprirea dubla (cel mult ~1,6 s), iar unde se
		# opreste nu stie nimeni.
		stare["se_misca"] = True
		stare["a_ajuns"] = False
		stare["actiune"] = "satelit"
		stare["oprire_automata_s"] = None
		_faraFapteleNucleului(stare)
		stare["stare_text"] = _("Antena se oprește")
		_pozitiaNestiuta(stare, _("Poziția nu se știe"))
	elif c.get("manual") and stare["se_misca"]:
		stare["manual"] = True
		_faraFapteleNucleului(stare)
		stare["actiune"] = c.get("actiune") or ""
		stare["oprire_automata_s"] = c.get("oprire_automata_s")
		if c.get("directie"):
			stare["directie"] = c["directie"]
		if c.get("octeti") and stare["actiune"] in ("pas", "continuu"):
			stare["comanda"] = c.get("comanda") or ""
			stare["comanda_text"] = c["octeti"]
		if stare["pozitie_grade"] is None:
			stare["curent_text"] = _("Poziția nu se știe după o mișcare manuală")
		pozitie = c.get("pozitie")
		if stare["actiune"] == "referinta":
			stare["stare_text"] = _("Antena merge spre poziția de referință a motorului")
		elif stare["actiune"] == "pozitie" and pozitie is not None:
			if stare["la_nume"]:
				stare["stare_text"] = _("Antena merge spre poziția %d (%s)") % (pozitie, stare["la_nume"])
			else:
				stare["stare_text"] = _("Antena merge spre poziția %d") % pozitie
		else:
			stare["stare_text"] = _textStare(stare)
		if c.get("stare") == "oprire":
			stare["stare_text"] = _("Antena se oprește")
	elif c.get("actiune") == "satelit" and stare["se_misca"]:
		stare["actiune"] = "satelit"
		stare["oprire_automata_s"] = c.get("oprire_automata_s")
	elif stare["a_ajuns"] and _opritaDeComenzi(stare, c):
		# o miscare oprita de noi (OK, plafonul, o eroare, cedarea tunerului; manuala sau „Mergi la satelit"): „a ajuns"
		# ar minti, antena s-a oprit unde a oprit-o comanda. `a_ajuns` ramane adevarat (miscarea s-a terminat, iar pagina
		# web scrie atunci stare_text), `manual` spune ca ce se arata vine de la comenzi, nu de la nucleu: ecranul nu mai
		# scrie „Drumul s-a terminat la" si nu mai deseneaza antena pe tinta
		stare["manual"] = True
		_faraFapteleNucleului(stare)
		stare["stare_text"] = _("Motorul s-a oprit")
		if c.get("ultima_actiune") == "satelit":
			_pozitiaNestiuta(stare, _("Poziția nu se știe după oprire"))
		else:
			_pozitiaNestiuta(stare, _("Poziția nu se știe după o mișcare manuală"))
	return stare


def _opritaDeComenzi(stare, c):
	"""True daca oprirea pe care o arata nucleul e cea trimisa de comenzi. Nucleul o noteaza cel tarziu odata cu ele (la
	„Mergi la satelit" chiar mai devreme, la acordul de referinta); o oprire notata mai tarziu e a unei miscari noi a
	nucleului (de exemplu programul pus la loc la iesire), care a ajuns cu adevarat si ramane „a ajuns"."""
	oprire_ms = c.get("ultima_oprire_ms", -1)
	if not 0 <= oprire_ms <= MILISECUNDE_DUPA_SOSIRE + 1000:
		return False
	try:
		nucleu_ms = int(_sec().hdsRotorStoppedMs(stare["slot"]))
	except Exception:
		return True
	return nucleu_ms < 0 or nucleu_ms + MARJA_OPRIRE_MS >= oprire_ms


def _pozitiaNestiuta(stare, text):
	"""Pozitia nu mai rezulta din plecare si tinta (motorul a fost oprit sau miscat de mana): fara pozitie estimata,
	fara procent, fara grade si secunde ramase; `curent_text` spune de ce, iar ecranul si pagina scriu „necunoscut"."""
	stare["pozitie_grade"] = None
	stare["procent"] = -1
	stare["grade_ramase"] = None
	stare["secunde_ramase"] = None
	stare["intarziat"] = False
	stare["alunecare"] = False
	stare["curent_text"] = text


def _stareNucleu():
	stare = {
		"activ": False,
		"se_misca": False,
		"a_ajuns": False,
		"slot": -1,
		"estimat": True,
		"de_la_orbital": -1,
		"la_orbital": -1,
		"de_la_grade": None,
		"la_grade": None,
		"de_la_nume": "",
		"la_nume": "",
		"pozitie_grade": None,
		"directie": "",
		"grade_total": None,
		"grade_ramase": None,
		"procent": -1,
		"secunde_trecute": 0,
		"secunde_estimate": None,
		"secunde_ramase": None,
		"comanda": "",
		"comanda_text": "",
		"unghi_motor": None,
		"semnal_prins": False,
		"semnal_stiut": False,
		"stare_text": "",
		"manual": False,
		"actiune": "",
		"oprire_automata_s": None,
		"comenzi": {},
		"curent_text": "",
		# de unde vin gradele si timpul
		"unghi_real": False,          # True = grade de motor (USALS, din coordonatele tunerului); False = orbitale
		"grade_orbitale": None,       # diferenta pozitiilor orbitale, pentru comparatie
		"unghi_motor_de_la": None,    # unghiul motorului la plecare (grade, est pozitiv), cand se stie
		"viteza": None,               # grade de motor pe secunda folosite la aceasta mutare
		"viteza_invatata": False,     # False = presupusa (inca nicio mutare masurata pe acest motor)
		"mutari_masurate": 0,         # cate mutari masurate in directia acestei mutari
		"viteza_text": "",
		"intarziat": False,           # timpul prezis a trecut si semnalul inca nu a venit
		"alunecare": False,           # dupa sosire, cat bara si antena ajung lin la capat (ecranul bate mai des)
		"sosire": "",                 # „semnal”, „fara semnal”, „alta” (oprire care nu e sosire) sau „” (nu se stie)
		# plecarea nestiuta si asteptarea nucleului
		"plecare_nestiuta": False,    # tinta se stie, plecarea nu (dupa pornire, flash, o pozitie uitata)
		"secunde_maxime": None,       # timpul maxim al nucleului pentru aceasta mutare (mrt), cand se stie
		"fara_semnal_la_sosire": False,  # oprita fara semnal (hdsRotorArrived = 1) si semnalul tot nu e
		"asteptare_trecuta": False,   # nucleul a asteptat tot timpul maxim si semnalul nu a venit
		"ramas_text": "",             # randul de sub bara, cand nu se pot spune gradele si secundele ramase
		# plecarea nestiuta, estimata (MOT1, 0.8.0): cheile de mai sus raman -1 / null ("nu se stie"), iar desenul si bara
		# folosesc acestea, marcate estimat
		"plecare_estimata_orbital": -1,  # ultima pozitie prinsa cu semnal (HdsMotorPozitie.pozitieConfirmata), -1 = nu e
		"plecare_estimata_grade": None,
		"pozitie_estimata_grade": None,  # pozitia din drum, de la plecarea estimata spre tinta, dupa viteza motorului
		"procent_estimat": -1,           # bara: din drumul estimat sau, fara plecare, din timp (cel mult timpul maxim)
		"tacut": False,                  # tinta = ultima pozitie confirmata: mutare de siguranta, fara panou automat
	}
	sec = _sec()
	if sec is None:
		return stare

	try:
		se_misca = bool(sec.isRotorMoving())
	except Exception:
		return stare

	try:
		slot = int(sec.hdsRotorMovingSlot())
	except Exception:
		# motor de imagine veche, fara functiile noastre: aratam macar ca se misca
		stare["se_misca"] = se_misca
		stare["activ"] = se_misca
		stare["stare_text"] = _("Antena se roteste") if se_misca else ""
		return stare

	de_cand = -1
	if slot < 0:
		# nu se misca acum: mai aratam cateva secunde ultima miscare, ca sa se vada ca a ajuns
		slot = _ultimulSlot(sec)
		if slot < 0:
			return stare
		try:
			de_cand = int(sec.hdsRotorStoppedMs(slot))
		except Exception:
			return stare
		if de_cand < 0 or de_cand > max(MILISECUNDE_DUPA_SOSIRE, MILISECUNDE_INDEMN_CABLU):
			return stare
		stare["a_ajuns"] = True

	stare["slot"] = slot
	stare["se_misca"] = se_misca and not stare["a_ajuns"]
	stare["activ"] = True

	try:
		de_la = int(sec.hdsRotorFromOrbital(slot))
		la = int(sec.hdsRotorToOrbital(slot))
		comanda = int(sec.hdsRotorCmd(slot))
		gotoxx = bool(sec.hdsRotorUsesGotoxx(slot))
		trecut_ms = int(sec.hdsRotorElapsedMs(slot))
	except Exception:
		stare["stare_text"] = _("Antena se roteste")
		return stare

	stare["de_la_orbital"] = de_la
	stare["la_orbital"] = la
	stare["secunde_trecute"] = max(0, trecut_ms) / 1000.0 if trecut_ms >= 0 else 0.0

	if la >= 0:
		stare["la_grade"] = orbitalToDegrees(la)
		stare["la_nume"] = _numeSatelit(la)
	if de_la >= 0:
		stare["de_la_grade"] = orbitalToDegrees(de_la)
		stare["de_la_nume"] = _numeSatelit(de_la)

	if comanda >= 0:
		if gotoxx:
			stare["comanda"] = "6E"
			stare["comanda_text"] = "E0 31 6E %02X %02X" % ((comanda >> 8) & 0xFF, comanda & 0xFF)
			stare["unghi_motor"] = _unghiDinComanda(comanda)
		else:
			stare["comanda"] = "6B"
			stare["comanda_text"] = "E0 31 6B %02X" % (comanda & 0xFF)

	secunde_max = _secundeMaxime(sec, slot)
	stare["secunde_maxime"] = secunde_max if secunde_max > 0 else None
	if de_la >= 0 and la >= 0:
		_miscareCunoscuta(sec, stare, slot, de_la, la, comanda, gotoxx, trecut_ms, de_cand)
	elif la >= 0:
		# plecarea nu e cunoscuta (dupa pornirea receptorului, dupa flash, dupa o pozitie uitata): nu desenam intre doua
		# puncte, nu inventam un procent si nu spunem ca antena se roteste
		stare["pozitie_grade"] = None
		stare["plecare_nestiuta"] = True
		if stare["a_ajuns"]:
			stare["sosire"] = {0: "alta", 1: "fara semnal", 2: "semnal"}.get(_semnSosire(sec, slot), "")

	stare["semnal_prins"], stare["semnal_stiut"] = _semnalPrins()

	_faptele(stare, trecut_ms)
	if stare["plecare_nestiuta"]:
		_plecareEstimata(stare, slot)
	stare["stare_text"] = _textStare(stare)
	indemnCablu(stare, de_cand)
	if stare["a_ajuns"] and de_cand > MILISECUNDE_DUPA_SOSIRE and not stare["indemn_cablu"]:
		stare["activ"] = False
	return stare


def _canalTv():
	try:
		import NavigationInstance
		ref = NavigationInstance.instance.getCurrentlyPlayingServiceOrGroup()
		return ref.toString() if ref else None
	except Exception:
		return None


def indemnCablu(stare, de_cand, acum_ms=None, canal=None):
	"""CABLUL (sus): dupa tot timpul maxim fara semnal, o singura data pe canal, titlul spune sa se verifice cablul
	(`indemn_cablu` = True). Aceeasi mutare citita din nou (televizorul si pagina web) pastreaza indemnul."""
	stare["indemn_cablu"] = False
	if not (stare.get("a_ajuns") and stare.get("asteptare_trecuta")) or de_cand is None or de_cand < 0:
		return
	acum = int(time.monotonic() * 1000) if acum_ms is None else acum_ms
	oprita = acum - de_cand
	cheie = canal if canal is not None else _canalTv()
	if not cheie:
		cheie = "%s:%s" % (stare.get("slot"), stare.get("la_orbital"))
	vazut = _INDEMNURI.get(cheie)
	if vazut is None:
		_INDEMNURI[cheie] = oprita
	elif abs(vazut - oprita) > MARJA_INDEMN_MS:
		return
	stare["indemn_cablu"] = True
	stare["stare_text"] = _("Fără semnal: verifică cablul antenei")


def _faptele(stare, trecut_ms):
	"""Ce se poate spune fara presupuneri:
	- oprita fara semnal (hdsRotorArrived = 1) si semnalul tot nu e: unde e antena nu se stie; daca a trecut tot timpul
	  maxim al nucleului, `asteptare_trecuta`. Fara procent, fara antena desenata, numai cat s-a asteptat;
	- in mers cu plecarea nestiuta: comanda a plecat, plecarea nu se stie, deci nici cat mai dureaza (procentul -1,
	  timpul None); se spune numai plafonul: cel mult cat mai e pana la timpul maxim al nucleului (calculat din viteza
	  invatata, Components/HdsMotorPlafon.py)."""
	maxim = stare["secunde_maxime"]
	if stare["a_ajuns"]:
		if stare["sosire"] == "fara semnal" and not (stare["semnal_stiut"] and stare["semnal_prins"]):
			stare["fara_semnal_la_sosire"] = True
			stare["asteptare_trecuta"] = maxim is not None and trecut_ms >= maxim * 1000
			_pozitiaNestiuta(stare, _("Poziția antenei nu se știe"))
			stare["ramas_text"] = _("Fără semnal după %s de așteptare") % secundeText(max(0, trecut_ms) / 1000.0)
		return
	if stare["plecare_nestiuta"]:
		# fara plecare nu exista drum: niciun procent, niciun timp estimat si nicio pozitie din drum, oricum s-ar fi ajuns
		# aici (/api/motor trebuie sa spuna "nu se stie", -1 / null)
		stare["procent"] = -1
		stare["secunde_estimate"] = None
		stare["secunde_ramase"] = None
		stare["grade_ramase"] = None
		stare["pozitie_grade"] = None
	if stare["plecare_nestiuta"] and stare["se_misca"]:
		# o singura fraza calma (MOT1, 26.11 22:29: "pare eroare"); randul "Acum" il umple plecarea estimata, daca e
		ramase = None if maxim is None else maxim - stare["secunde_trecute"]
		# cat mai dureaza nu se stie; se spune numai plafonul nucleului (timpul maxim al mutarii), cand il are
		if ramase is not None and ramase >= 1:
			stare["ramas_text"] = _("Poziția de dinainte nu e cunoscută; mutarea poate dura până la %s") % secundeText(ramase)
		else:
			stare["ramas_text"] = _("Poziția de dinainte nu e cunoscută; se așteaptă semnalul")


# tinta egala cu ultima pozitie confirmata: mutarea e tacuta pana la capat (pe .129, 26.11, semnalul a venit la 15-77 s
# dupa comenzile spre pozitia pe care antena era deja); daca se termina fara semnal, apare mesajul obisnuit (cablul)


def _pozitieConfirmata(slot):
	"""HdsMotorPozitie.pozitieConfirmata fara import (modulul il incarca panoul automat); -1 cand lipseste"""
	m = sys.modules.get("Components.HdsMotorPozitie")
	f = getattr(m, "pozitieConfirmata", None) if m is not None else None
	try:
		return int(f(slot)) if f is not None else -1
	except Exception:
		return -1


def _plecareEstimata(stare, slot):
	"""Plecarea nestiuta (MOT1): cheile vechi raman "nu se stie"; aici se pune ce se poate estima, marcat estimat.
	- tinta = ultima pozitie prinsa cu semnal: mutare de siguranta, `tacut` toata mutarea (si la sosirea cu semnal);
	- alta pozitie confirmata: plecarea estimata de acolo, pozitia din drum si bara dupa viteza motorului
	  (HdsMotorViteza: drumMotor, prezice, parti; fara invatare, mutarea nu intra in viteza);
	- nimic stiut (sau presupunerea cazuta): bara dupa timp, din timpul maxim al nucleului (secunde_maxime)."""
	la = stare["la_orbital"]
	trecut = stare["secunde_trecute"]
	confirmat = _pozitieConfirmata(slot)
	if confirmat >= 0 and confirmat == la:
		if not stare.get("fara_semnal_la_sosire"):
			stare["tacut"] = True
		confirmat = -1   # plecarea = tinta nu da niciun drum de desenat
	if confirmat >= 0 and stare["se_misca"]:
		try:
			loc = _coordonate(slot)
		except Exception:
			loc = None
		try:
			grade, directie, unghiuri = V.drumMotor(confirmat, la, loc)
			prezis = V.calibrare().prezice(slot, grade, directie)
			p = V.parti(prezis, trecut)
			stare["plecare_estimata_orbital"] = confirmat
			stare["plecare_estimata_grade"] = orbitalToDegrees(confirmat)
			stare["pozitie_estimata_grade"] = round(V.orbitalLa(confirmat, la, loc, unghiuri, p["drum"]), 3)
			stare["procent_estimat"] = max(0, min(99, int(round(p["timp"] * 100))))
			return
		except Exception:
			pass
	maxim = stare["secunde_maxime"]
	if stare["se_misca"] and maxim:
		stare["procent_estimat"] = max(0, min(99, int(round(100.0 * trecut / maxim))))


def _faraFapteleNucleului(stare):
	"""o miscare a comenzilor (pas, oprire, pozitie memorata): textele de mai sus erau ale ultimei miscari a nucleului"""
	stare["plecare_nestiuta"] = False
	stare["tacut"] = False
	stare["plecare_estimata_orbital"] = -1
	stare["plecare_estimata_grade"] = None
	stare["pozitie_estimata_grade"] = None
	stare["procent_estimat"] = -1
	stare["fara_semnal_la_sosire"] = False
	stare["asteptare_trecuta"] = False
	stare["ramas_text"] = ""


def _secundeMaxime(sec, slot):
	"""timpul maxim al nucleului pentru miscarea slotului (mrt, sec.cpp:852-866), -1 daca nu se stie"""
	try:
		return int(sec.hdsRotorSeconds(slot))
	except Exception:
		return -1


def _tinereMs(sec, slot):
	"""cat tine nucleul 18 V dupa comanda (tinta pe 13 V), 0 = deloc sau o imagine fara functie"""
	try:
		return max(0, int(sec.hdsRotorTinereMs(slot)))
	except Exception:
		return 0


def _semnSosire(sec, slot):
	"""hdsRotorArrived: 2 = oprita dupa semnal, 1 = oprita de secventa fara semnal, 0 = oprita
	altfel (standby, zap in mers, oprirea noastra, inclusiv comenzile manuale din „Rotirea antenei”, care opresc prin
	setRotorMoving); None la o imagine fara functia asta (atunci nu se invata nimic)"""
	try:
		return int(sec.hdsRotorArrived(slot))
	except Exception:
		return None


def _coordonate(slot):
	from Components import HdsMotorTuner
	return HdsMotorTuner.coordonateUsalsNumere(slot)


def _miscareCunoscuta(sec, stare, slot, de_la, la, comanda, gotoxx, trecut_ms, oprit_ms):
	"""Plecarea si tinta se stiu: drumul in grade de motor, prezicerea inghetata a mutarii (HdsMotorViteza.miscare),
	invatarea o singura data dupa oprire (HdsMotorViteza.judeca) si ce se arata: procentul din timp, pozitia din drum,
	cat mai e, alunecarea lina de dupa sosire. Aceleasi cifre ajung pe ecran si in web."""
	secunde_max = _secundeMaxime(sec, slot)
	oprit = stare["a_ajuns"]
	tinere_ms = _tinereMs(sec, slot)
	e = V.miscare(slot, de_la, la, comanda, 1 if gotoxx else 0, secunde_max, trecut_ms, oprit_ms if oprit else -1,
		_coordonate, tinere_ms)
	stare["tinere_18v_ms"] = tinere_ms
	if oprit:
		semn = _semnSosire(sec, slot)
		stare["sosire"] = {0: "alta", 1: "fara semnal", 2: "semnal"}.get(semn, "")
		V.judeca(e, semn, max(0, trecut_ms), secunde_max)
	prezis = e["prezis"]
	diferenta = _diferentaScurta(de_la, la)
	stare["directie"] = "" if diferenta == 0 else ("est" if diferenta > 0 else "vest")
	stare["grade_orbitale"] = abs(diferenta) / 10.0
	stare["grade_total"] = round(e["grade"], 2)
	stare["unghi_real"] = e["unghiuri"] is not None
	if e["unghiuri"] is not None:
		stare["unghi_motor_de_la"] = round(e["unghiuri"][0], 2)
	stare["secunde_estimate"] = prezis["T"]
	stare["viteza"] = prezis["viteza"]
	stare["viteza_invatata"] = prezis["invatata"]
	stare["mutari_masurate"] = prezis["masurate"]
	stare["viteza_text"] = V.vitezaText(prezis)
	p = V.parti(prezis, stare["secunde_trecute"], oprit_ms / 1000.0 if oprit else None)
	procent = int(round(p["timp"] * 100))
	if stare["se_misca"]:
		procent = min(procent, 99)   # cat timp motorul se misca nu spunem niciodata „gata"
	stare["procent"] = max(0, min(100, procent))
	stare["pozitie_grade"] = round(V.orbitalLa(de_la, la, e["coordonate"], e["unghiuri"], p["drum"]), 3)
	stare["grade_ramase"] = round(e["grade"] * (1.0 - p["drum"]), 1)
	stare["secunde_ramase"] = p["secunde_ramase"]
	stare["intarziat"] = p["intarziat"]
	stare["alunecare"] = p["alunecare"]


def _ultimulSlot(sec):
	"""slotul care s-a miscat cel mai recent (cel mai mic timp de la oprire)"""
	gasit, cel_mai_recent = -1, None
	for slot in range(32):
		try:
			if not sec.hdsRotorInfoValid(slot):
				continue
			de_cand = int(sec.hdsRotorStoppedMs(slot))
		except Exception:
			return -1
		if de_cand < 0:
			continue
		if cel_mai_recent is None or de_cand < cel_mai_recent:
			cel_mai_recent, gasit = de_cand, slot
	return gasit


def _unghiDinComanda(valoare):
	"""unghiul motorului din valoarea comenzii 6E, cu tabelul din sec.cpp (zecimi in saisprezecimi)"""
	from Components.DishMath import GOTOX_TABLE
	intreg = (valoare >> 4) & 0xFF
	jos = valoare & 0x0F
	zecime = GOTOX_TABLE.index(jos) if jos in GOTOX_TABLE else 0
	grade = intreg + zecime / 10.0
	return grade if (valoare & 0xF000) == 0xE000 else -grade


def _textStare(stare):
	if stare["a_ajuns"]:
		if stare.get("fara_semnal_la_sosire"):
			# numai ce s-a masurat: nucleul a asteptat tot timpul maxim (sau motorul s-a oprit dupa curent) si semnalul
			# nu a venit; ca antena a ajuns nu se stie
			if stare.get("asteptare_trecuta"):
				return _("Timpul de așteptare a trecut, fără semnal")
			return _("Motorul s-a oprit, fără semnal")
		if stare["semnal_stiut"]:
			return _("Antena a ajuns, semnal recepționat") if stare["semnal_prins"] else _("Antena a ajuns, inca fara semnal")
		return _("Antena a ajuns")
	if stare.get("plecare_nestiuta"):
		# plecarea nu se stie: se spune calm unde merge antena (MOT1), fara "comanda" si fara "necunoscut"
		if stare.get("la_grade") is not None:
			return _("Antena se mută pe %s") % HdsGrade.pozitie(stare["la_grade"])
		return _("Antena se mută")
	if stare["directie"] == "est":
		return _("Antena se roteste spre est")
	if stare["directie"] == "vest":
		return _("Antena se roteste spre vest")
	return _("Antena se roteste")


def secundeText(secunde):
	if secunde is None:
		return _("necunoscut")
	secunde = int(round(secunde))
	if secunde < 60:
		return _("%d s") % secunde
	return _("%d min %d s") % (secunde // 60, secunde % 60)


def istoricTinta(stare):
	"""Ultimul semnal prins de acest receptor pe pozitia spre care merge antena (Components/HdsIstoricSemnal.py), pentru
	ecranul motorului si pagina antenei; u"" cand pozitia nu se stie sau istoricul e gol."""
	grade = stare.get("la_grade")
	if grade is None:
		grade = stare.get("pozitie_grade")
	if grade is None:
		return u""
	try:
		from Components import HdsIstoricSemnal as I
		poz = int(round(float(grade) * 10)) % 3600
		ist = I.istoric()
		if not ist.stiut():
			return u""
		return u"%s: %s" % (HdsGrade.pozitie(grade), I.text_istoric(ist.pozitie(poz)))
	except Exception:
		return u""


def boltaJson(stare):
	"""bolta intreaga pentru pagina web /motor, sau None: scara, capetele (unghi si eticheta), sudul, limitele si unghiurile
	plecarii, tintei, pozitiei de acum si ale satelitilor cu canale (cu "afara")"""
	b = boltaVizibila(stare.get("slot"))
	if b is None:
		return None

	def unghi(grade):
		if grade is None:
			return None
		u, _afara = unghiPeBolta(grade, b)
		return round(u, 2) if u is not None else None

	cu_canale = pozitiiCuCanale()
	sateliti = []
	for orbital, grade in satelitiPeArc(stare.get("slot")):
		if orbital not in cu_canale or orbital in (stare.get("de_la_orbital"), stare.get("la_orbital")):
			continue
		u, afara = unghiPeBolta(grade, b)
		if u is not None:
			sateliti.append({"orbital": orbital, "unghi": round(u, 2), "afara": bool(afara)})
	return {"a": round(b["a"], 2), "unghi_vest": round(b["unghi_vest"], 2), "unghi_est": round(b["unghi_est"], 2),
		"vest_scurt": HdsGrade.pozitie(b["grade_vest"]), "est_scurt": HdsGrade.pozitie(b["grade_est"]),
		"sud_scurt": HdsGrade.pozitie(b["sud"]),
		"limita_vest": round(b["limita_vest"], 2) if b["limita_vest"] is not None else None,
		"limita_est": round(b["limita_est"], 2) if b["limita_est"] is not None else None,
		"de_la": unghi(stare.get("de_la_grade")), "la": unghi(stare.get("la_grade")), "acum": unghi(stare.get("pozitie_grade")),
		# plecarea nestiuta: plecarea si pozitia estimate (MOT1), pentru desenul animat al paginii
		"de_la_estimat": unghi(stare.get("plecare_estimata_grade")), "acum_estimat": unghi(stare.get("pozitie_estimata_grade")),
		"sateliti": sateliti}


def stareJson():
	"""aceeasi stare, cu numere simple, pentru interfata web (fara obiecte enigma)"""
	stare = stareMotor()
	iesire = {}
	for cheie, valoare in stare.items():
		if isinstance(valoare, float):
			iesire[cheie] = round(valoare, 2)
		else:
			iesire[cheie] = valoare
	iesire["de_la_text"] = gradeText(stare["de_la_grade"])
	iesire["la_text"] = gradeText(stare["la_grade"])
	iesire["pozitie_text"] = gradeText(stare["pozitie_grade"])
	# etichetele de langa punctele de pe bolta, aceleasi ca pe televizor (Screens/HdsDishMotor.py, gradeScurt): pagina
	# nu le mai scrie singura
	iesire["de_la_scurt"] = HdsGrade.pozitie(stare["de_la_grade"]) if stare["de_la_grade"] is not None else ""
	iesire["la_scurt"] = HdsGrade.pozitie(stare["la_grade"]) if stare["la_grade"] is not None else ""
	# plecarea nestiuta, estimata (MOT1): textele gata facute, ca pe televizor
	pe = stare.get("plecare_estimata_grade")
	iesire["plecare_estimata_text"] = gradeText(pe) if pe is not None else ""
	iesire["plecare_estimata_scurt"] = HdsGrade.pozitie(pe) if pe is not None else ""
	ae = stare.get("pozitie_estimata_grade")
	iesire["pozitie_estimata_text"] = gradeText(ae) if ae is not None else ""
	# satelitii tunerului, pentru punctele de pe bolta din desenul paginii (numai cifre, fara nume)
	iesire["sateliti"] = [{"orbital": o, "grade": g} for o, g in satelitiPeArc(stare["slot"])] if stare["activ"] else []
	# desenul vazut din spatele antenei (aceeasi setare ca pe televizor) si sudul (longitudinea locului) pentru varful curbei
	iesire["din_spate"], iesire["sud_grade"] = desenDinSpate()
	# bolta intreaga (aceeasi ca pe televizor, Screens/HdsDishMotor.py): unghiurile motorului, gata socotite, ca pagina sa nu
	# repete formulele USALS
	iesire["bolta"] = boltaJson(stare) if stare.get("activ") else None
	# numai aici (pagina web a antenei), nu in stareMotor (televizorul)
	iesire["readucere"] = _readucere()
	# istoricul semnalului pe pozitia tinta, acelasi rand ca pe televizor (Screens/HdsDishMotor.py)
	iesire["istoric_text"] = istoricTinta(stare) if stare.get("activ") else u""
	if iesire["readucere"].get("activa"):
		iesire["readucere"]["sat_text"] = gradeText(orbitalToDegrees(iesire["readucere"]["sat"]))
	return iesire
