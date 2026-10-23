# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMotorTuner.py - tunerul care are motorul: care e, cine il mai foloseste, luarea si darea lui inapoi, acordul.
#
# Il folosesc comenzile motorului (Components/HdsMotorComenzi.py) si tinerea minte a pozitiei
# (Components/HdsMotorPozitie.py). La import nu se atinge nimic din enigma: `enigma`, `nimmanager`,
# `NavigationInstance` se iau numai in functii, ca probele de pe PC sa poata pune obiecte false.
#
# De unde vine fiecare lucru (lib/dvb si lib/python ale noastre):
#   - tunerele cu motor       config.Nims (NimManager.py:977-1001; mod simplu „positioner" sau LNB avansat „1_2")
#   - tunerele legate         configMode satposdepends / loopthrough / equal cu connectedTo (NimManager.py:165-180)
#   - luarea tunerului,       Components/HdsGasireSemnal.py (LuareTuner, transpondere, acordeaza): un singur modul
#     transponderele, acordul de acord pentru Gasire semnal si pentru motor
#   - starea si semnalul      frontend.getFrontendStatus(dict) (frontend.cpp:1355-1400)
#   - programul               NavigationInstance (Navigation.py:53, :83, :103, :111)
import os
import sys
import time

# peste cat timp o citire a semnalului e socotita prea lunga pentru bucla principala (atunci nu mai citim)
CITIRE_SEMNAL_MAX_S = 0.05
FISIER_LACAT_PROBA = "/etc/enigma2/hds-fara-motor"


def acum():
	"""ceasul pentru durate (secunde). Probele de pe PC il inlocuiesc cu unul pe care il misca ele."""
	return time.monotonic()


def acumPerete():
	"""ora adevarata (secunde de la 1970), pentru cronometrele de inregistrare"""
	return time.time()


def jurnal(text):
	"""un rand scurt in jurnalul enigma2, numai la schimbari (niciodata pe fiecare bataie de ceas)"""
	print("[HdsMotor] %s" % text)


def cronometru(functie):
	"""un eTimer legat de o functie, pe ambele feluri de legare din imagini (callback sau timeout.connect)"""
	from enigma import eTimer
	t = eTimer()
	try:
		t.callback.append(functie)
	except AttributeError:
		t.legatura_hds = t.timeout.connect(functie)
	return t


def controlSec():
	try:
		from enigma import eDVBSatelliteEquipmentControl
		return eDVBSatelliteEquipmentControl.getInstance()
	except Exception:
		return None


# urma comenzilor de motor (lib/dvb/hdsurmamotor.cpp, /home/root/logs/hds-motor.log): cat ramane valabila cererea
# anuntata nucleului; comenzile pleaca dupa tonul oprit si 13 V (cel mult 500 ms) sau dupa secventa nucleului
CERERE_MOTOR_MS = 8000


def anuntaCererea(text):
	"""Spune nucleului cine cere urmatoarele comenzi de motor ("ecran: motor pas", "web: gasire semnal"): randul din
	urma motorului le arata la "cerere", valabil CERERE_MOTOR_MS. True daca nucleul a primit-o; pe o imagine fara urma
	sau pe PC nu face nimic."""
	sec = controlSec()
	anunta = getattr(sec, "hdsMotorCerere", None) if sec is not None else None
	if anunta is None:
		return False
	try:
		anunta(str(text)[:90], CERERE_MOTOR_MS)
		return True
	except Exception:
		return False


def lacatProba():
	"""cu /etc/enigma2/hds-fara-motor se pot trimite numai oprirea si pornirea limitelor (proba pe receptor)"""
	return os.path.exists(FISIER_LACAT_PROBA)


# ------------------------------------------------------------------ tunerele

def _nimmanager():
	from Components.NimManager import nimmanager
	return nimmanager


def _nims():
	from Components.config import config
	return config.Nims


def numeTuner(slot):
	"""„A", „B"... (asa scrie pe spatele receptorului)"""
	return chr(ord("A") + int(slot))


def tunereSatelit():
	"""sloturile care pot primi satelit si nu sunt oprite in Setari tuner"""
	sloturi = []
	try:
		nm = _nimmanager()
		nims = _nims()
		for nim in nm.nim_slots:
			try:
				if nim.isCompatible("DVB-S") and nims[nim.slot].configMode.value != "nothing":
					sloturi.append(nim.slot)
			except Exception:
				continue
	except Exception:
		return []
	return sloturi


def areMotor(slot):
	"""True numai daca tunerul chiar trimite comenzi de motor: mod simplu cu „positioner" (USALS), sau un LNB avansat
	cu DiSEqC 1.2. getRotorSatListForNim (NimManager.py:989-993) spune „cu motor" si pentru un LNB 3601-3604 fara 1.2,
	deci aici se verifica si modul LNB-ului (revizia m5g.6)."""
	try:
		nim = _nims()[slot]
		mod = nim.configMode.value
		if mod == "simple":
			return nim.diseqcMode.value == "positioner"
		if mod != "advanced":
			return False
		for sat in list(nim.advanced.sat.values()):
			try:
				numar = int(sat.lnb.value)
				if numar and nim.advanced.lnb[numar].diseqcMode.value == "1_2":
					return True
			except Exception:
				continue
	except Exception:
		return False
	return False


def tunereCuMotor():
	"""[(slot, „A")] pentru tunerele de satelit care au motor"""
	return [(slot, numeTuner(slot)) for slot in tunereSatelit() if areMotor(slot)]


def tunereLegate(slot):
	"""sloturile care folosesc aceeasi antena prin tunerul cu motor (satposdepends, loopthrough, equal)"""
	legate = []
	try:
		nm = _nimmanager()
		nims = _nims()
		for nim in nm.nim_slots:
			if nim.slot == slot:
				continue
			try:
				c = nims[nim.slot]
				if c.configMode.value in ("satposdepends", "loopthrough", "equal") and int(c.connectedTo.value) == int(slot):
					legate.append(nim.slot)
			except Exception:
				continue
	except Exception:
		return []
	return legate


def sateliti(slot):
	"""[(orbital 0..3599, nume)] pentru tunerul cu motor, in ordinea din satellites.xml"""
	try:
		return [(int(x[0]), x[1]) for x in _nimmanager().getRotorSatListForNim(slot)]
	except Exception:
		return []


def numeSatelit(orbital):
	try:
		nume = _nimmanager().getSatName(orbital)
	except Exception:
		return ""
	return nume if nume and nume != "N/A" else ""


def pozitieLegata(slot, pozitie):
	"""orbitalul satelitului pe care setarile avansate il leaga de pozitia memorata N (fara USALS), altfel -1"""
	try:
		nim = _nims()[slot]
		if nim.configMode.value != "advanced":
			return -1
		for orbital, sat in list(nim.advanced.sat.items()):
			try:
				numar = int(sat.lnb.value)
				if not numar or int(orbital) >= 3600 or sat.usals.value:
					continue
				if nim.advanced.lnb[numar].diseqcMode.value == "1_2" and int(sat.rotorposition.value) == int(pozitie):
					return int(orbital)
			except Exception:
				continue
	except Exception:
		return -1
	return -1


def _locStabilit():
	"""locul antenei (Components/HdsLocul.py): fara el copiile din Setari tuner nu inseamna nimic (implicitul neutru)"""
	try:
		from Components import HdsLocul
		return HdsLocul.stabilit()
	except Exception:
		return False


def refuzFaraLoc(slot, orbital=None):
	"""textul refuzului unei miscari USALS cu locul nestabilit (Mergi la satelit), altfel None"""
	try:
		from Components import HdsLocul
		return HdsLocul.refuzUsals(slot, orbital)
	except Exception as e:
		jurnal("locul antenei nu se poate citi: %r" % (e,))
		return None


def coordonateUsals(slot):
	"""(„45,300 N", „23,270 E") din Setari tuner, in limba meniului (Components/HdsGrade.py), ca ecranul sa spuna cu ce
	lucreaza USALS; None daca nu se stiu sau daca locul antenei nu e stabilit (atunci nucleul nu primeste nicio miscare
	USALS)"""
	if not _locStabilit():
		return None
	try:
		nim = _nims()[slot]
		if nim.configMode.value == "simple":
			sursa = nim
		else:
			sursa = None
			for sat in list(nim.advanced.sat.values()):
				numar = int(sat.lnb.value)
				if numar and nim.advanced.lnb[numar].diseqcMode.value == "1_2":
					sursa = nim.advanced.lnb[numar]
					break
			if sursa is None:
				return None
		try:
			from Components import HdsGrade
		except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
			import HdsGrade
		lat = float(sursa.latitude.float)
		lon = float(sursa.longitude.float)
		if sursa.latitudeOrientation.value != "north":
			lat = -lat
		if sursa.longitudeOrientation.value != "east":
			lon = -lon
		return HdsGrade.latitudine(lat, 3), HdsGrade.longitudine(lon, 3)
	except Exception:
		return None


def coordonateUsalsNumere(slot):
	"""(latitudine, longitudine) in grade, nord si est pozitive, din aceleasi setari ca coordonateUsals, adica cele cu
	care nucleul calculeaza comanda 6E (sec.cpp:505-514); None daca nu se stiu. Nicio valoare inventata aici: unghiul
	real de rotire (Components/HdsMotorViteza.py) se calculeaza numai din ce e scris in Setari tuner. Cu locul antenei
	nestabilit: None."""
	if not _locStabilit():
		return None
	try:
		nim = _nims()[slot]
		if nim.configMode.value == "simple":
			sursa = nim
		else:
			sursa = None
			for sat in list(nim.advanced.sat.values()):
				numar = int(sat.lnb.value)
				if numar and nim.advanced.lnb[numar].diseqcMode.value == "1_2":
					sursa = nim.advanced.lnb[numar]
					break
			if sursa is None:
				return None
		lat = float(sursa.latitude.float)
		lon = float(sursa.longitude.float)
		if sursa.latitudeOrientation.value != "north":
			lat = -lat
		if sursa.longitudeOrientation.value != "east":
			lon = -lon
		return lat, lon
	except Exception:
		return None


# ------------------------------------------------------------------ cine mai foloseste antena

def _navigatie():
	try:
		import NavigationInstance
		return NavigationInstance.instance
	except Exception:
		return None


def inregistrarePeAntena(slot):
	"""True daca o inregistrare foloseste tunerul cu motor sau unul legat de el. Daca tunerul unei inregistrari nu se
	poate citi, raspunsul e True (partea sigura: nu miscam antena sub o inregistrare)."""
	nav = _navigatie()
	if nav is None:
		return False
	try:
		inregistrari = nav.getRecordings() or []
	except Exception:
		return False
	folosite = set([slot] + tunereLegate(slot))
	for rec in inregistrari:
		try:
			date = rec.frontendInfo().getFrontendData()
			numar = date.get("tuner_number", -1) if date else -1
		except Exception:
			numar = -1
		if numar < 0 or numar in folosite:
			return True
	return False


def secundePanaLaInregistrare():
	"""Cate secunde mai sunt pana PORNESTE urmatoarea inregistrare sau urmatorul cronometru de schimbare a canalului;
	None daca nu e nimic programat. Inceputul inregistrarii vine din HdsGasireSemnal.urmatoarea_inregistrare (numai
	cronometrele in asteptare sau pregatite): getNextRecordingTime() intoarce -1 fara cronometre si SFARSITUL unei
	inregistrari care merge (RecordTimer.py:700-707), care ar opri degeaba motorul. Cronometrele de schimbare a
	canalului (getNextZapTime, RecordTimer.py:692-698) iau si ele tunerul, deci se numara (revizia m5c)."""
	nav = _navigatie()
	if nav is None:
		return None
	cele = []
	try:
		inceput = _gasire().urmatoarea_inregistrare()
		if inceput is not None and inceput > 0:
			cele.append(inceput)
	except Exception as e:
		jurnal("inregistrarile programate nu se pot citi: %r" % (e,))
	try:
		zap = nav.RecordTimer.getNextZapTime()
		if zap is not None and zap > 0:
			cele.append(zap)
	except Exception:
		pass
	if not cele:
		return None
	return min(cele) - acumPerete()


def motivIndisponibil():
	"""textul care spune de ce nu se pot da comenzi, sau None"""
	if not tunereSatelit():
		return _("Receptorul nu are niciun tuner de satelit, deci motorul nu se poate comanda de aici.")
	if not tunereCuMotor():
		return _("Niciun tuner nu e setat cu motor. Motorul se alege în Setări tuner (DiSEqC 1.2 sau USALS).")
	return None


# ------------------------------------------------------------------ transponderele (din modulul comun)

def _gasire():
	"""Components/HdsGasireSemnal: luarea tunerului, transponderele si acordul sunt scrise o singura data acolo
	(un singur modul de acord); se importa aici, in functie, ca la import sa nu se incarce nimic"""
	from Components import HdsGasireSemnal
	return HdsGasireSemnal


def _s2(slot):
	try:
		return bool(_nimmanager().nim_slots[slot].isCompatible("DVB-S2"))
	except Exception:
		return False


def transpondereBune(orbital, slot=None):
	"""transponderele satelitului pe care nucleul le primeste (aceeasi filtrare ca la scanare si la Gasire semnal)"""
	try:
		lista, _sarite = _gasire().transpondere(orbital, s2=_s2(slot) if slot is not None else True)
	except Exception as e:
		jurnal("transponderele pentru %s nu se pot citi: %r" % (orbital, e))
		return []
	return [e["tp"] for e in lista]


def alegeTransponder(bune):
	"""transponderul de referinta: intai unul DVB-S cu rata mare (prinde cel mai usor), altfel primul"""
	if not bune:
		return None
	for tp in bune:
		if tp.get("system") == 0 and tp.get("symbol_rate", 0) >= 20000000:
			return tp
	return bune[0]


def transponderText(tp):
	"""„11362 H 22000 DVB-S 3/4" (acelasi text ca in Gasire semnal)"""
	if not tp:
		return ""
	try:
		return _gasire().text_transponder(tp)
	except Exception:
		return ""


def programPeTuner(slot):
	"""(transponder, are_semnal) pentru programul care merge acum, citit inainte de oprirea lui, daca e pe tunerul
	`slot`; altfel (None, False). Traducerea cheilor din getTransponderData(True) („polarization", „fec_inner",
	frontend.cpp:1065-1077; revizia m5a) o face HdsGasireSemnal.transponder_din_serviciu."""
	nav = _navigatie()
	try:
		serviciu = nav and nav.getCurrentService()
		info = serviciu and serviciu.frontendInfo()
		if not info:
			return None, False
		date = info.getFrontendData() or {}
		if date.get("tuner_number", -1) != slot:
			return None, False
		tp = _gasire().transponder_din_serviciu(serviciu, [o for o, _n in sateliti(slot)])
		if tp is None:
			return None, False
		return tp, bool(_stareServiciu(info).get("tuner_locked"))
	except Exception as e:
		jurnal("programul curent nu se poate citi: %r" % (e,))
		return None, False


def _stareServiciu(info):
	"""getFrontendStatus al serviciului nu are argument si intoarce dictionarul (iservice.h:452); imaginile vechi
	cer un dictionar de umplut"""
	try:
		stare = info.getFrontendStatus()
	except TypeError:
		stare = {}
		info.getFrontendStatus(stare)
	return stare or {}


def programulCurentPeSlot(slot):
	"""(pe_slot, are_semnal) pentru programul care merge acum; folosit de HdsMotorPozitie"""
	nav = _navigatie()
	try:
		serviciu = nav and nav.getCurrentService()
		info = serviciu and serviciu.frontendInfo()
		if not info:
			return False, False
		date = info.getFrontendData() or {}
		if date.get("tuner_number", -1) != slot:
			return False, False
		return True, bool(_stareServiciu(info).get("tuner_locked"))
	except Exception:
		return False, False


def sesiuneInfoBar():
	"""sesiunea in care sta PiP-ul (revizia m5g.1); din web nu avem alta"""
	try:
		from Screens.InfoBar import InfoBar
		return InfoBar.instance and InfoBar.instance.session
	except Exception:
		return None


def ecranStandby():
	try:
		from Screens import Standby
		return Standby.inStandby
	except Exception:
		return None


def programCurent():
	"""referinta programului care merge acum, sau None cand nu merge nimic. Arunca daca nu se poate citi (cine intreaba
	alege atunci partea sigura: nu porneste nimic peste)."""
	nav = _navigatie()
	if nav is None:
		raise RuntimeError("fara NavigationInstance")
	return nav.getCurrentlyPlayingServiceReference()


def pornesteProgramul(ref):
	nav = _navigatie()
	if nav is None:
		return False
	nav.playService(ref)
	return True


def tunerLaAltcineva():
	"""True cat tunerul unic e tinut de cineva prin coordonatorul HdsComun (Gasire semnal, DAB+, T2-MI): acelasi obiect
	din sys.modules pe care il folosesc ei (coordonator.py, obtine(); HdsGasireSemnal._coordonator)"""
	m = sys.modules.get("hdsatelit_hds_coordonator")
	coord = getattr(m, "coordonator", None) if m is not None else None
	return coord is not None and getattr(coord, "detinator", None) is not None


# ------------------------------------------------------------------ tunerul luat

def _acordFaraMotor(frontend, tp):
	"""acordul pe frontendul unui canal brut FARA comanda de motor: nucleul pune comutatoarele, tensiunea si tonul, dar
	nu trimite comanda de motor (setDVBS(parm, True), sec.cpp:497-498); aceleasi campuri (CAMPURI_NUCLEU) si aceeasi
	conversie (ScanerSatelit.in_parametri) ca HdsGasireSemnal.acordeaza. Intoarce codul nucleului (0 = pornit); arunca
	la o greseala."""
	from enigma import eDVBFrontendParametersSatellite, eDVBFrontendParameters
	from Screens.ScanerSatelit import in_parametri
	g = _gasire()
	parm = in_parametri(eDVBFrontendParametersSatellite, dict((k, tp[k]) for k in g.CAMPURI_NUCLEU))
	fp = eDVBFrontendParameters()
	fp.setDVBS(parm, True)
	cod = frontend.tune(fp)
	return 0 if cod is None else int(cod)


def acordFaraMotor(frontend, tp):
	"""acordul fara comanda de motor (verificarea readucerii pe alt transponder al aceluiasi satelit,
	Components/HdsMotorPozitie.py): codul nucleului, -1 la o greseala (nu arunca)"""
	if frontend is None or not tp:
		return -1
	try:
		return _acordFaraMotor(frontend, tp)
	except Exception as e:
		jurnal("acordul fara motor a dat eroare: %r" % (e,))
		return -1


class TunerMotor(object):
	"""Tunerul cu motor, luat prin HdsGasireSemnal.LuareTuner (alocarea cu reincercari, coordonatorul extensiilor,
	oprirea programului numai daca alocarea e refuzata, PiP-ul, punerea programului la loc, cu zapul facut intre timp
	castigator). Aici se adauga numai ce ii trebuie motorului: acordul fara comanda de motor, starea acordului,
	semnalul si predarea programului catre ecranul Standby."""

	def __init__(self, slot, la_cedare):
		self.slot = slot
		self.luare = _gasire().LuareTuner("Rotirea antenei", la_cedare=la_cedare)
		self.frontend = None
		self._citire_lenta = False

	def ia(self, la_gata):
		"""la_gata(True, "") cu frontendul luat, sau la_gata(False, "ocupat" | "inregistrare"); poate veni pe loc"""
		def gata(ok, motiv):
			if ok:
				self.frontend = self.luare.frontend
			la_gata(ok, motiv)
		self.luare.ia(self.slot, gata, sesiuneInfoBar())

	def programOprit(self):
		return bool(self.luare.am_oprit_canalul)

	def tineMinteProgramul(self, ref):
		"""programul oprit la o cedare de dinainte (HdsMotorComenzi, G3) trece pe luarea de acum: LuareTuner il pune la
		loc la eliberare ca pe orice program oprit de ea (pune_canalul_la_loc), cu zapul facut intre timp castigator.
		Numai daca luarea nu a oprit deja ea un program (acela ramane)."""
		l = self.luare
		if ref is not None and not l.am_oprit_canalul:
			l.am_oprit_canalul, l.oldref = True, ref

	def acorda(self, tp, fara_motor):
		"""Acordul cu motorul (fara_motor=False) e HdsGasireSemnal.acordeaza. Varianta fara comanda de motor
		(nucleul pune comutatoarele, tensiunea si tonul, dar nu trimite comanda de motor, sec.cpp:497-498) nu exista
		acolo; se face aici cu aceleasi campuri (CAMPURI_NUCLEU) si aceeasi conversie (ScanerSatelit.in_parametri),
		schimband numai setDVBS(parm, True). Intoarce True daca nucleul a primit acordul: pe drumul bun tune() pune
		starea TUNING pe loc (frontend.cpp:2529-2533); pe eroare intoarce un cod si starea ramane cea de dinainte."""
		if self.frontend is None or not tp:
			return False
		try:
			g = _gasire()
			if not fara_motor:
				cod = g.acordeaza(self.frontend, tp)
			else:
				cod = _acordFaraMotor(self.frontend, tp)
		except Exception as e:
			jurnal("acordul pe tunerul %s a dat eroare: %r" % (numeTuner(self.slot), e))
			return False
		if cod != 0:
			jurnal("nucleul a refuzat acordul pe tunerul %s (cod %d)" % (numeTuner(self.slot), cod))
			return False
		return self.stareAcord() == "TUNING"

	def stareAcord(self):
		"""IDLE / TUNING / FAILED / LOCKED / LOSTLOCK, sau „" daca nu se poate citi"""
		if self.frontend is None:
			return ""
		try:
			d = {}
			self.frontend.getFrontendStatus(d)
			return d.get("tuner_state", "")
		except Exception:
			return ""

	def semnal(self):
		"""{"prins": bool, "calitate": procent sau None, "citit": bool}. „Prins" = blocat si iesit din TUNING (pana
		la SET_FRONTEND, FE_READ_STATUS poate arata inca blocarea de dinainte; aflat de firul Gasire semnal). Calitatea
		vine pe scara 0..65535 si se scaleaza (revizia m5b) cu HdsGasireSemnal.la_suta. O citire mai lunga de 50 ms
		opreste citirile (bucla principala nu are voie sa stea)."""
		if self.frontend is None or self._citire_lenta:
			return {"prins": False, "calitate": None, "citit": False}
		inceput = acum()
		try:
			d = {}
			self.frontend.getFrontendStatus(d)
		except Exception:
			return {"prins": False, "calitate": None, "citit": False}
		if acum() - inceput > CITIRE_SEMNAL_MAX_S:
			self._citire_lenta = True
			jurnal("citirea semnalului a tinut peste 50 ms; nu mai citim pe tunerul %s" % numeTuner(self.slot))
		if "tuner_locked" not in d:
			return {"prins": False, "calitate": None, "citit": False}
		prins = bool(d.get("tuner_locked")) and d.get("tuner_state") != "TUNING"
		try:
			calitate = _gasire().la_suta(d.get("tuner_signal_quality"))
		except Exception:
			calitate = None
		return {"prins": prins, "calitate": calitate if prins else None, "citit": True}

	def elibereaza(self, reda_canalul=True, la_standby=False):
		"""Tunerul dat inapoi (nucleul inchide frontendul dupa 3 s, dvb.h:41-47). Cat e deschis ecranul Standby programul
		nu porneste: il primeste ecranul Standby, care il porneste la trezire (Standby.py:71-74).

		`la_standby` fara ecran Standby inseamna ca omul a trezit deja receptorul inainte sa se termine oprirea
		motorului (a doua apasare pe POWER, sub ~1,6 s cat asteapta oprirea dubla): Standby.py:81-84 pune inStandby
		INAINTE de standbyCounter += 1, deci cand lantul a pornit ecranul exista. La inchidere el a pornit
		prev_running_service, care era None (programul il oprisem noi, Standby.py:53-56), deci nu a pornit nimic:
		programul il pune aici LuareTuner, ca la o iesire obisnuita."""
		l = self.luare
		standby = ecranStandby()
		if reda_canalul and standby is not None:
			if l.am_oprit_canalul and standby is not None:
				nav = _navigatie()
				try:
					curent = nav.getCurrentlyPlayingServiceReference()
				except Exception:
					curent = None
				ref = curent if curent is not None else l.oldref
				if ref is not None:
					standby.prev_running_service = ref
			l.am_oprit_canalul, l.oldref = False, None
			l.elibereaza(reda_canalul=False)
		else:
			l.elibereaza(reda_canalul=reda_canalul)
		self.frontend = None
