# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsGasireSemnal.py - logica pentru „Găsire semnal”: tunerele, sateliții, transponderele, luarea tunerului,
# oprirea și punerea la loc a canalului, acordul (DVB-S și DVB-S2), așteptarea motorului, citirea semnalului,
# verdictul și textele. Ecranul de pe televizor (Screens/Satfinder.py) și pagina web citesc același dicționar
# (Masurare.stare()), ca să nu existe două adevăruri.
#
# Acordul se face într-un singur loc: LuareTuner și acordeaza() de
# aici le folosește și ecranul motorului, nu se scriu a doua oară.
#
# Ce primește nucleul nu se hotărăște aici: regulile (motiv_refuz, listele de FEC, modulații, roll-off,
# transpondere_satelit, in_parametri) sunt scrise o singură dată în Screens/ScanerSatelit.py și se iau de acolo,
# leneș (funcția _reguli), fără să se încarce vreun ecran.
#
# Bucla principală nu stă niciodată: totul merge pe eTimer (alocarea cu reîncercare la 150 ms, citirea la 250 ms,
# paza la 5 s, canalul datorat după o cedare la 1 s). Nicio așteptare, niciun sleep, niciun fir.
#
# Pozițiile rămân brute peste tot (0..3599; 5,0° vest = 3550). Nucleul face singur USALS din ele; o traducere în
# -50 ar trimite antena spre 5,0° EST (sec.cpp: SatLon = abs(orbital_position) / 10).

import sys
import time

from Components.HdsMotorStare import stareMotor, secundeText

# ---------------------------------------------------------------- constante
# Câmpurile structurii eDVBFrontendParametersSatellite (lib/dvb/frontendparms.h). Numai ele ajung la nucleu.
CAMPURI_NUCLEU = ("frequency", "symbol_rate", "polarisation", "fec", "inversion", "orbital_position",
	"system", "modulation", "rolloff", "pilot")

SISTEM_DVB_S, SISTEM_DVB_S2 = 0, 1

PAS_CITIRE_MS = 250           # citirea frontendului
PAS_ALOCARE_MS = 150          # reîncercarea alocării după oprirea canalului
ALOCARE_MAXIM_S = 3.0         # fluxul 8001 dă drumul tunerului abia când bucla prelucrează închiderea
PAS_PAZA_MS = 5000            # înregistrările programate și pagina web
WEB_FARA_CERERE_S = 30        # pagina web închisă: măsurarea se oprește singură
PAS_DATORIE_MS = 1000         # canalul oprit de măsurare și rămas fără stăpân după o cedare: pornește când tunerul e liber
INREGISTRARE_OPRIRE_S = 90    # măsurarea dă tunerul înapoi cu 90 s înainte de începutul unei înregistrări
INREGISTRARE_ANUNT_S = 600    # sub 10 minute se spune de dinainte
PRINDERI_LA_RAND = 2          # „Semnal prins” = blocat la 2 citiri la rând, cu motorul oprit
MARJA_PRINDERE_S = 3          # peste timpul de prindere al nucleului (calcLockTimeout)
VARF_S = 10                   # vârful calității, pentru aliniere
TOLERANTA_FRECVENTA_KHZ = 2000
DETALII_MAXIM = 2             # câte mesaje încap sub listă (skin: 1000 x 168, HdsRegular 28)
MESAJ_SCURT_S = 6
# Nivelul cel mai mare pe care il poate da driverul tunerului: GetSignalStrength (hi_tuner.ko) tine procentul facut din
# AGC intre 3 si 98, iar FE_READ_SIGNAL_STRENGTH il da inmultit cu 655 (la_suta(98 * 655) = 97). Scara in dBm a
# tunerului RF lipseste (fisa lui nu e publica), deci 'prea puternic' nu are un prag in dBm: semnul e nivelul tinut la
# acest plafon cel putin VARF_S secunde, cu tunerul care nu prinde transponderul sau l-a pierdut. Cu semnalul prins nu
# se spune nimic: si calitatea e taiata la 98, iar un prag sub care ar fi rea nu e masurat.
NIVEL_PLAFON = 98 * 655

# timer.py:9-10 (TimerEntry.StateWaiting, StatePrepared)
TIMER_ASTEPTARE, TIMER_PREGATIT = 0, 1

# Fazele măsurării (stare()["faza"])
FAZE = ("oprita", "fara_tuner", "fara_sateliti", "alocare", "ocupat", "inregistrare", "inregistrare_programata",
	"refuzat", "acord", "motor", "prins", "fara_semnal", "pierdut", "standby")
FAZE_CU_CITIRE = ("acord", "motor", "prins", "fara_semnal", "pierdut")

# Numele valorilor, pentru afișare. FEC Auto se traduce la folosire.
NUME_FEC = {1: "1/2", 2: "2/3", 3: "3/4", 4: "5/6", 5: "7/8", 6: "8/9", 7: "3/5", 8: "4/5", 9: "9/10"}
NUME_MODULATIE = {1: "QPSK", 2: "8PSK"}
NUME_ROLLOFF = {0: "0,35", 1: "0,25", 2: "0,20"}


def _reguli():
	"""Regulile nucleului, scrise o singură dată în Screens/ScanerSatelit.py (numai funcțiile fără ecran)."""
	from Screens import ScanerSatelit
	return ScanerSatelit


def _nim():
	from Components.NimManager import nimmanager
	return nimmanager


def _nav():
	import NavigationInstance
	return NavigationInstance.instance


def _coordonator():
	"""Coordonatorul DAB+ / DVB-T2 din satelit, dacă e încărcat: Hds/DabT2/coordonator.py ține obiectul în
	sys.modules sub acest nume. Fără el, None."""
	m = sys.modules.get("hdsatelit_hds_coordonator")
	return getattr(m, "coordonator", None) if m is not None else None


def _ecran_standby():
	"""Ecranul Standby deschis acum, sau None. Screens.Standby e încărcat de la pornire (mytest.py), deci nu se
	importă aici: se ia din module."""
	modul = sys.modules.get("Screens.Standby")
	return getattr(modul, "inStandby", None) if modul is not None else None


# ---------------------------------------------------------------- liste pentru ecran și web
def polarizari():
	return [(0, _("Orizontală")), (1, _("Verticală")), (2, _("Circulară stânga")), (3, _("Circulară dreapta"))]


def sisteme(s2=True):
	return [(SISTEM_DVB_S, "DVB-S"), (SISTEM_DVB_S2, "DVB-S2")] if s2 else [(SISTEM_DVB_S, "DVB-S")]


def fec_dvbs():
	"""FEC-urile DVB-S: cele primite de nucleu (FEC_DVBS), fără „Niciuna” (15), care nu descrie un transponder."""
	return [(f, _("Auto") if f == 0 else NUME_FEC[f]) for f in _reguli().FEC_DVBS if f in NUME_FEC or f == 0]


def fec_dvbs2():
	"""FEC-urile DVB-S2: exact FEC_DVBS2 (fără Auto: nucleul refuză DVB-S2 cu FEC Auto, frontend.cpp prepare_sat)."""
	return [(f, NUME_FEC[f]) for f in _reguli().FEC_DVBS2]


def modulatii_dvbs2():
	return [(m, NUME_MODULATIE[m]) for m in _reguli().MOD_DVBS2]


def rolloffuri():
	return [(r, NUME_ROLLOFF[r]) for r in _reguli().ROLLOFF_VALIDE]


def piloti():
	return [(2, _("Auto")), (0, _("Oprit")), (1, _("Pornit"))]


# ---------------------------------------------------------------- texte mici
def text_pozitie(poz):
	"""192 -> „19,2°E”; 3550 -> „5,0°V”, scrisă ca în scaner (Screens/ScanerSatelit.py, text_pozitie), ca aceeași
	poziție să nu apară în două feluri. Numai pentru afișare, nucleul primește poziția brută."""
	return _reguli().text_pozitie(poz)


def text_transponder(tp):
	"""„11766 V 27500 DVB-S2 8PSK 3/4” sau „10758 V 22000 DVB-S 3/4” (cifre și prescurtări)."""
	pol = "HVLR"[tp["polarisation"]] if 0 <= tp["polarisation"] <= 3 else "?"
	fec = _("Auto") if tp["fec"] == 0 else NUME_FEC.get(tp["fec"], str(tp["fec"]))
	if tp["system"] == SISTEM_DVB_S2:
		return "%d %s %d DVB-S2 %s %s" % (tp["frequency"] // 1000, pol, tp["symbol_rate"] // 1000,
			NUME_MODULATIE.get(tp["modulation"], "?"), fec)
	return "%d %s %d DVB-S %s" % (tp["frequency"] // 1000, pol, tp["symbol_rate"] // 1000, fec)


def timp_prindere_s(tp):
	"""Cât așteaptă nucleul prinderea, după rata de simbol (lib/dvb/frontend.cpp, calcLockTimeout)."""
	sr = tp.get("symbol_rate", 0) if tp else 0
	if sr > 20000000:
		return 5
	if sr > 10000000:
		return 10
	return 20


def interval_incercare_s(tp):
	return timp_prindere_s(tp) + MARJA_PRINDERE_S


def plafon_din(din, nivel, acum):
	"""De cand sta nivelul la plafonul driverului (NIVEL_PLAFON), pe ceasul monoton; None cand nivelul e sub el sau nu
	se stie."""
	try:
		if nivel is None or int(nivel) < NIVEL_PLAFON:
			return None
	except (TypeError, ValueError):
		return None
	return acum if din is None else din


def intrare_prea_puternica(faza, din, acum):
	"""Semnalul care intra poate fi prea puternic (sau o interferenta): tunerul nu prinde transponderul sau l-a
	pierdut, iar nivelul sta la plafonul driverului de cel putin VARF_S secunde."""
	return faza in ("fara_semnal", "pierdut") and din is not None and acum - din >= VARF_S


def la_suta(valoare):
	"""0..65535 -> 0..100 (ca FrontendInfo), None rămâne None."""
	if valoare is None:
		return None
	try:
		return max(0, min(100, int(valoare) * 100 // 65536))
	except (TypeError, ValueError):
		return None


def _text_sarite(n):
	"""Câte transpondere ale satelitului lipsesc din listă, cu forma românească: singularul cu litere, pluralul fără
	"de" ("20 transpondere")."""
	if n == 1:
		return _("Un transponder al satelitului nu apare aici, fiindcă imaginea nu îl poate acorda încă.")
	return _("%d transpondere ale satelitului nu apar aici, fiindcă imaginea nu le poate acorda încă.") % n


# ---------------------------------------------------------------- tunere, sateliți, transpondere
def _loc_antena(slot):
	"""(latitudine, longitudine) ale antenei cu motor în modul simplu (config.Nims, nord și est pozitive), sau
	None. În modul avansat coordonatele sunt pe LNB și nu le folosim aici. Cu locul antenei nestabilit
	(Components/HdsLocul.py) tot None: orizontul nu se ghicește după copia neutră."""
	try:
		from Components import HdsLocul
		if not HdsLocul.stabilit():
			return None
	except Exception:
		return None
	try:
		from Components.config import config
		n = config.Nims[slot]
		if n.configMode.value != "simple" or n.diseqcMode.value != "positioner":
			return None
		lat, lon = float(n.latitude.float), float(n.longitude.float)
		if n.latitudeOrientation.value == "south":
			lat = -lat
		if n.longitudeOrientation.value == "west":
			lon = -lon
		return lat, lon
	except (AttributeError, IndexError, KeyError, TypeError, ValueError):
		return None


def _sub_orizont(poz, loc):
	if loc is None:
		return False
	from Components.DishMath import elevation, orbitalToDegrees
	return elevation(orbitalToDegrees(poz), loc[0], loc[1]) < 0


def tunere():
	"""Tunerele de satelit: [{"slot", "nume", "s2", "motor", "sateliti": [{"poz", "nume", "vizibil"}]}], întâi cele
	cu sateliți configurați. Un tuner nesetat („nothing”) rămâne în listă, fără sateliți, ca ecranul să spună că
	trebuie configurat, nu că nu există. Cu motor, lista are toți sateliții (NimManager.getSatListForNim); cei aflați
	sub orizontul locului trec la sfârșit, marcați, fiindcă motorul ar merge până la capăt degeaba."""
	nim = _nim()
	rez = []
	for s in nim.nim_slots:
		if not s.isCompatible("DVB-S"):
			continue
		motor = bool(nim.getRotorSatListForNim(s.slot))
		loc = _loc_antena(s.slot) if motor else None
		vazuti, nevazuti = [], []
		for x in nim.getSatListForNim(s.slot):
			poz = int(x[0])
			if _sub_orizont(poz, loc):
				nevazuti.append({"poz": poz, "nume": x[1], "vizibil": False})
			else:
				vazuti.append({"poz": poz, "nume": x[1], "vizibil": True})
		rez.append({"slot": s.slot, "nume": s.friendly_full_description, "s2": s.isCompatible("DVB-S2"),
			"motor": motor, "sateliti": vazuti + nevazuti})
	return sorted(rez, key=lambda t: not t["sateliti"])


def text_satelit(sat):
	"""Numele satelitului cu poziția scrisă ca în scaner și ca în rândul „Antena:”: „13.0E Hot Bird 13F/13G” din
	satellites.xml devine „13,0°E Hot Bird 13F/13G” (ScanerSatelit.nume_satelit)."""
	nume = _reguli().nume_satelit(sat["poz"], sat["nume"])
	if sat.get("vizibil", True):
		return nume
	return "%s (%s)" % (nume, _("sub orizont"))


def transpondere(poz, s2=True):
	"""Transponderele satelitului pe care tunerul le poate acorda: ([{"tp", "tsid", "onid"}], câte_sarite).
	„tp” are numai cele 10 câmpuri ale nucleului; tsid/onid (-1 = necunoscut) vin din satellites.xml și stau
	separat, ca să nu ajungă pe structura nucleului."""
	r = _reguli()
	lista_xml = _nim().getTransponders(poz) or []
	bune, sarite = r.transpondere_satelit(poz, lista_xml)
	id_uri = {}
	for x in lista_xml:
		if x[0] == 0 and len(x) > 11:
			id_uri[(x[1], x[3], x[2])] = (x[10], x[11])
	rez, nr_sarite = [], len(sarite)
	for tp in bune:
		if tp["system"] == SISTEM_DVB_S2 and not s2:
			nr_sarite += 1
			continue
		tsid, onid = id_uri.get((tp["frequency"], tp["polarisation"], tp["symbol_rate"]), (-1, -1))
		rez.append({"tp": dict((k, tp[k]) for k in CAMPURI_NUCLEU), "tsid": tsid, "onid": onid})
	return rez, nr_sarite


def potriveste(tp, lista):
	"""Indicele transponderului din listă care e același cu tp (aceeași polarizare, frecvența la ±2 MHz, rata la
	±1 %), cel mai apropiat, sau -1. lamedb și satellites.xml pot diferi cu câțiva kHz."""
	gasit, dif_min = -1, None
	for i, e in enumerate(lista):
		t = e["tp"]
		if t["polarisation"] != tp["polarisation"]:
			continue
		dif = abs(t["frequency"] - tp["frequency"])
		if dif > TOLERANTA_FRECVENTA_KHZ:
			continue
		if abs(t["symbol_rate"] - tp["symbol_rate"]) > max(1000, t["symbol_rate"] // 100):
			continue
		if dif_min is None or dif < dif_min:
			gasit, dif_min = i, dif
	return gasit


def _int(v):
	try:
		return int(v)
	except (TypeError, ValueError):
		return None


def transponder_din_campuri(valori, poz, s2=True):
	"""Transponderul bătut de mână, EXACT cum a fost bătut: (tp, "") sau (None, text pentru om).
	valori: frecventa (MHz), sr (kSymb/s), pol, sistem, fec, mod, rolloff, pilot. Nimic nu se înlocuiește din
	satellites.xml (revizia, punctul 5): ce se acordează e ce arată câmpurile."""
	r = _reguli()
	frecventa, sr = _int(valori.get("frecventa")), _int(valori.get("sr"))
	if not frecventa or not sr or frecventa <= 0 or sr <= 0:
		return None, _("Introdu frecvența (MHz) și rata de simbol (kSymb/s) ale transponderului.")
	sistem = _int(valori.get("sistem"))
	if sistem == SISTEM_DVB_S2 and not s2:
		return None, _("Tunerul nu are DVB-S2. Alege un transponder DVB-S.")
	pol, fec = _int(valori.get("pol")), _int(valori.get("fec"))
	tp = {"frequency": frecventa * 1000, "symbol_rate": sr * 1000, "polarisation": pol, "fec": fec,
		"inversion": 2, "orbital_position": _int(poz), "system": sistem, "modulation": 1, "rolloff": 0, "pilot": 2}
	if sistem == SISTEM_DVB_S:
		if fec not in r.FEC_DVBS:
			return None, _("Transponder pe care imaginea nu îl poate acorda: %s") % _("FEC pe care nucleul nu îl are")
	elif sistem == SISTEM_DVB_S2:
		tp["modulation"] = _int(valori.get("mod"))
		tp["rolloff"] = _int(valori.get("rolloff"))
		tp["pilot"] = _int(valori.get("pilot"))
		if tp["rolloff"] not in r.ROLLOFF_VALIDE:
			return None, _("Transponder pe care imaginea nu îl poate acorda: %s") % _("roll-off pe care nucleul nu îl are")
		if tp["pilot"] not in (0, 1, 2):
			return None, _("Transponder pe care imaginea nu îl poate acorda: %s") % _("pilot necunoscut")
	if tp["orbital_position"] is None:
		return None, _("Transponder pe care imaginea nu îl poate acorda: %s") % _("satelit necunoscut")
	motiv = r.motiv_refuz(tp)
	if motiv:
		return None, _("Transponder pe care imaginea nu îl poate acorda: %s") % motiv
	return tp, ""


def transponder_din_serviciu(serviciu, pozitii):
	"""Transponderul canalului care merge, citit ÎNAINTE de oprirea lui, sau None. Numai un canal de satelit de
	pe unul din sateliții tunerului (cheile: lib/dvb/frontend.cpp, PutSatelliteDataToDict; „polarization” cu z,
	rolloff și pilot numai la DVB-S2)."""
	if serviciu is None:
		return None
	info = serviciu.frontendInfo()
	if info is None:
		return None
	d = info.getTransponderData(True)
	if not d or d.get("tuner_type") != "DVB-S":
		return None
	tp = {"frequency": d.get("frequency", 0), "symbol_rate": d.get("symbol_rate", 0),
		"polarisation": d.get("polarization", -1), "fec": d.get("fec_inner", 0), "inversion": d.get("inversion", 2),
		"orbital_position": d.get("orbital_position"), "system": d.get("system", SISTEM_DVB_S),
		"modulation": d.get("modulation", 1), "rolloff": d.get("rolloff", 0), "pilot": d.get("pilot", 2)}
	if tp["orbital_position"] not in pozitii:
		return None
	if tp["inversion"] not in (0, 1, 2):
		tp["inversion"] = 2
	if tp["system"] == SISTEM_DVB_S:
		tp["rolloff"], tp["pilot"] = 0, 2
	if _reguli().motiv_refuz(tp):
		return None
	return tp


def acordeaza(frontend, tp):
	"""Acordul direct pe frontendul unui canal brut, ca Components/TuneTest.py: numai cele 10 câmpuri ale nucleului,
	setDVBS(parm, False) (motorul se mișcă singur prin SEC, ca la orice schimbare de canal), apoi frontend.tune.
	Întoarce codul nucleului: 0 = secvența a pornit; altceva = refuz înainte de orice mișcare (satelit fără
	configurare, frecvența intermediară în afara benzii LNB-ului, DVB-S2 fără FEC real)."""
	from enigma import eDVBFrontendParametersSatellite, eDVBFrontendParameters
	parm = _reguli().in_parametri(eDVBFrontendParametersSatellite, dict((k, tp[k]) for k in CAMPURI_NUCLEU))
	fp = eDVBFrontendParameters()
	fp.setDVBS(parm, False)
	cod = frontend.tune(fp)
	return 0 if cod is None else int(cod)


def anunta_motorul(text):
	"""Urma motorului (lib/dvb/hdsurmamotor.cpp, hds-motor.log): inaintea unui acord al masurarii, care poate misca
	antena prin USALS, nucleul afla cine il cere ("ecran: gasire semnal", "web: gasire semnal"); aceeasi functie ca la
	comenzile motorului (Components/HdsMotorTuner.anuntaCererea). Fara ea (PC, imagine veche): nimic."""
	try:
		from Components import HdsMotorTuner
		return HdsMotorTuner.anuntaCererea(text)
	except Exception:
		return False


def urmatoarea_inregistrare():
	"""Ora de ÎNCEPUT a celei mai apropiate înregistrări programate (secunde, ca time()), sau None.
	Numai timerele în așteptare sau pregătite, nu cele „doar comutare” și nu cele dezactivate. Nu se folosește
	getNextRecordingTime(): întoarce -1 fără timere și SFÂRȘITUL unei înregistrări care merge (revizia, punctul 6)."""
	try:
		lista = _nav().RecordTimer.timer_list
	except AttributeError:
		return None
	cel_mai_devreme = None
	for t in lista:
		if getattr(t, "justplay", False) or getattr(t, "disabled", False):
			continue
		if getattr(t, "state", None) not in (TIMER_ASTEPTARE, TIMER_PREGATIT):
			continue
		if cel_mai_devreme is None or t.begin < cel_mai_devreme:
			cel_mai_devreme = t.begin
	return cel_mai_devreme


def _inregistrare_pe_tuner(slot):
	"""True dacă o înregistrare care merge folosește tunerul (sau nu se știe pe care tuner e)."""
	try:
		inregistrari = _nav().getRecordings() or []
	except AttributeError:
		return False
	for rec in inregistrari:
		info = rec.frontendInfo()
		date = info.getFrontendData() if info is not None else None
		if not date or date.get("tuner_number") in (None, slot):
			return True
	return False


def _adrese_transmisie():
	"""Adresele aparatelor care primesc acum un canal prin receptor (transmisia in retea, portul 8001): sesiunile
	serverului local al imaginii (Hds/DabT2/server8001.py), altfel lista streamserverului enigma2. None daca nu se
	poate afla; [] daca nu e nicio transmisie. O adresa locala (127.0.0.1, ::1) e chiar receptorul (pagina /tv din
	panoul web trece prin el)."""
	adrese = None
	try:
		from Hds.DabT2 import server8001
		server = server8001.obtine()
	except Exception:
		server = None
	if server is not None:
		adrese = []
		for ses in list(getattr(server, "sesiuni", None) or []):
			if getattr(ses, "eroare", None):
				continue
			a = getattr(ses, "adresa", None)
			adrese.append(str(a[0] if isinstance(a, (list, tuple)) and a else a or ""))
	if not adrese:
		try:
			from enigma import eStreamServer
			lista = eStreamServer.getInstance().getConnectedClients()
		except Exception:
			lista = None
		if isinstance(lista, (list, tuple)):
			adrese = (adrese or []) + [str(c[0]) if isinstance(c, (list, tuple)) and c else "" for c in lista]
	return adrese


def _local(adresa):
	a = (adresa or "").lower()
	if a.startswith("::ffff:"):
		a = a[7:]
	return a in ("", "::1", "localhost") or a.startswith("127.")


def mesaj_tuner_ocupat(adrese):
	"""Textul de sub lista cand tunerul e tinut de o transmisie in retea: de ce si ce poti face. "" fara transmisie
	(atunci ramane textul obisnuit, cu transmisia sau extensia)."""
	if not adrese:
		return ""
	afara = []
	for a in adrese:
		a = a[7:] if a.lower().startswith("::ffff:") else a
		if not _local(a) and a not in afara:
			afara.append(a)
	text = _("Un canal se trimite acum în rețea (spre un telefon, un calculator sau pagina /tv a panoului web) și ține "
		"tunerul. Oprește redarea acolo, apoi apasă galben.")
	if afara:
		text += " " + _("Primește canalul: %s.") % ", ".join(afara[:3])
	return text


def _ora(t):
	return time.strftime("%H:%M", time.localtime(t))


# ---------------------------------------------------------------- luarea tunerului
class LuareTuner(object):
	"""Un tuner de satelit luat pentru acord direct (canal brut), cu oprirea și punerea la loc a canalului.

	Ordinea din Components/TuneTest.py:51-59: se încearcă întâi; canalul se oprește NUMAI dacă alocarea e refuzată
	(un canal de cablu sau din rețea nu se înnegrește degeaba); apoi se reîncearcă la 150 ms, cel mult 3 s. O
	înregistrare nu se oprește niciodată. Canalul oprit se ține minte o singură dată (după scaner nu se
	suprascrie) și se pune la loc la eliberare. Dacă între timp cineva a cerut alt canal (din web sau de la
	telecomandă), se pornește acela, nu cel vechi.

	Folosită de Masurare (aici) și de ecranul motorului."""

	def __init__(self, nume, la_cedare=None):
		self.nume = nume              # îl citește coordonatorul HdsComun
		self.la_cedare = la_cedare
		self.slot = -1
		self.canal = None
		self.frontend = None
		self.oldref = None
		self.am_oprit_canalul = False
		self._la_gata = None
		self._termen = 0.0
		self._sesiune = None
		self._ceas = None

	def are_tuner(self):
		return self.frontend is not None

	def asteapta(self):
		return self._la_gata is not None

	def _timer(self):
		if self._ceas is None:
			from enigma import eTimer
			self._ceas = eTimer()
			self._ceas.callback.append(self._reincearca)
		return self._ceas

	def ia(self, slot, la_gata, sesiune=None):
		"""Cere tunerul. la_gata(True, "") sau la_gata(False, "ocupat" | "inregistrare"); pe loc sau din eTimer."""
		if self.frontend is not None and self.slot == slot:
			la_gata(True, "")
			return
		if self.frontend is not None:
			self._da_drumul()
		self.slot, self._la_gata, self._sesiune = slot, la_gata, sesiune
		coord = _coordonator()
		if coord is not None:
			coord.cere_tuner(self)      # DAB+ / T2-MI cedează acum, sincron
		if self._incearca():
			return
		self._opreste_canalul()
		self._termen = time.monotonic() + ALOCARE_MAXIM_S
		self._timer().start(PAS_ALOCARE_MS, True)

	def _incearca(self):
		from enigma import eDVBResourceManager
		canal = eDVBResourceManager.getInstance().allocateRawChannel(self.slot)
		if canal is None:
			return False
		frontend = canal.getFrontend()
		if frontend is None:
			return False
		self.canal, self.frontend = canal, frontend
		la_gata, self._la_gata = self._la_gata, None
		if la_gata is not None:
			la_gata(True, "")
		return True

	def _reincearca(self):
		if self._la_gata is None:
			return
		if self._incearca():
			return
		if time.monotonic() < self._termen:
			self._timer().start(PAS_ALOCARE_MS, True)
			return
		# tot refuzat: canalul pornește la loc imediat, nu rămâne oprit degeaba
		motiv = "inregistrare" if _inregistrare_pe_tuner(self.slot) else "ocupat"
		la_gata, self._la_gata = self._la_gata, None
		self._elibereaza_la_coordonator()
		self.pune_canalul_la_loc()
		la_gata(False, motiv)

	def _opreste_canalul(self):
		nav = _nav()
		if not self.am_oprit_canalul:
			# canalul de pus la loc se ține minte numai la PRIMA oprire: după scaner (care pornește singur un
			# canal la ieșire) se oprește ce merge atunci, dar la sfârșit pornește tot canalul de la început
			self.oldref = nav.getCurrentlyPlayingServiceReference()
			self.am_oprit_canalul = True
		nav.stopService()
		s = self._sesiune
		if s is not None and getattr(s, "pipshown", False):
			# ca Screens/ServiceStopScreen.py: PiP-ul ține și el un tuner
			s.pipshown = False
			del s.pip

	def pune_canalul_la_loc(self):
		if not self.am_oprit_canalul:
			return
		nav = _nav()
		acum = nav.getCurrentlyPlayingServiceReference()
		vechi = self.oldref
		self.am_oprit_canalul, self.oldref = False, None
		if acum is not None:
			# după oprirea noastră referința e None; dacă nu mai e, s-a cerut între timp alt canal, care nu a
			# putut acorda cât țineam tunerul: acela pornește din nou, nu cel vechi (revizia, punctul 9)
			nav.playService(acum, forceRestart=True)
		elif vechi is not None:
			nav.playService(vechi)

	def uita_canalul(self):
		"""Canalul oprit de noi nu mai pornește de aici: îl pornește altcineva (ecranul Standby, la trezire).
		Întoarce referința lui, sau None."""
		vechi = self.oldref if self.am_oprit_canalul else None
		self.am_oprit_canalul, self.oldref = False, None
		return vechi

	def preia_canalul_cerut(self):
		"""Canalul cerut între timp (zap din web sau de la telecomandă), care nu a putut acorda cât ținem tunerul, se
		oprește acum și devine cel pus la loc la eliberare (sau dat mai departe de uita_canalul), în locul celui oprit
		de noi. Numai cu tunerul în mână. Întoarce referința lui, sau None."""
		if self.frontend is None:
			return None
		acum = _nav().getCurrentlyPlayingServiceReference()
		if acum is None:
			return None
		self.oldref, self.am_oprit_canalul = acum, True
		_nav().stopService()
		return acum

	def _elibereaza_la_coordonator(self):
		coord = _coordonator()
		if coord is not None:
			coord.elibereaza_tuner(self)

	def _da_drumul(self):
		# canalul brut se lasă: frontendul se închide singur după 3 s dacă nu îl ia nimeni (lib/dvb/dvb.h, dec_use)
		self.canal, self.frontend = None, None
		self._elibereaza_la_coordonator()

	def elibereaza(self, reda_canalul=True):
		self._la_gata = None
		if self._ceas is not None:
			self._ceas.stop()
		self._da_drumul()
		if reda_canalul:
			self.pune_canalul_la_loc()

	def cedeaza(self, motiv):
		"""Chemată de coordonatorul HdsComun când o extensie cere tunerul: îl dăm înapoi pe loc."""
		self._la_gata = None
		if self._ceas is not None:
			self._ceas.stop()
		self.canal, self.frontend = None, None
		if self.la_cedare is not None:
			self.la_cedare(motiv)


# ---------------------------------------------------------------- măsurarea
class Masurare(object):
	"""O singură măsurare deodată (un tuner). Ecranul o preia oricând; web-ul primește refuz cât e deschis ecranul.

	Cine cere: porneste, schimba, reacordeaza, opreste și arata_refuz primesc `cine`. Numai ecranul de pe televizor
	spune cine="ecran"; orice alt apelant (pagina web, sau cine uită să spună) e tratat ca web-ul: cât e deschis
	ecranul primește (False, motivul), iar măsurarea de pe televizor rămâne neatinsă. Toate întorc (reușit, text)."""

	def __init__(self):
		self.tuner = LuareTuner("Găsire semnal", la_cedare=self._la_cedare)
		self.faza = "oprita"
		self.slot = -1
		self.s2 = True
		self.tp = None
		self.extra = {}
		self.cine = ""
		self.sesiune = None
		self.ecran_deschis = False
		self._ascultatori = []
		self._ceas_citire = None
		self._ceas_paza = None
		self._standby_legat = False
		self._pas_ms = PAS_CITIRE_MS
		self._durate = []
		self._lent_scris = False
		self._generatie_tp = 0
		self.tsid = self.onid = None
		self.tsid_stare = ""           # "", "se_citeste", "citit", "necitit"
		self._tsid_in_asteptare = False
		self._tp_dupa_motor = None
		self._mesaj = ""               # detaliul fazei (refuzul, standby, înregistrarea)
		self._mesaj_scurt = ("", 0.0)  # un rând pentru câteva secunde (galbenul în mersul motorului)
		self._eveniment = ""           # pentru web: „preluată de televizor”, „oprită: pagina nu mai cere”
		self._motor_la_refuz = False
		self._motor = {}
		self._motor_era = False
		self._ultima_cerere_web = 0.0
		self._inregistrare_la = None
		self.incercari = 0
		self._t_acord = 0.0
		self._t_baza = 0.0
		self._blocate = 0
		self._varfuri = []
		self._in_driver = None         # (frontend, transponder) trimise ultima dată nucleului
		self._varf_asteapta = False    # citirile nu intră în vârf până iese nucleul din TUNING (vezi _acordeaza)
		# canalul oprit de măsurare și rămas fără stăpân după o cedare, cu paza lui (verificarea finală, Mediu A)
		self._program_datorat = None
		self._ceas_datorie = None
		self._goleste()

	# ---- ceasuri
	def _ceas(self, nume, functie):
		ceas = getattr(self, nume)
		if ceas is None:
			from enigma import eTimer
			ceas = eTimer()
			ceas.callback.append(functie)
			setattr(self, nume, ceas)
		return ceas

	def _porneste_citirea(self, ms=None):
		self._ceas("_ceas_citire", self._pas).start(self._pas_ms if ms is None else ms, True)

	def _opreste_citirea(self):
		if self._ceas_citire is not None:
			self._ceas_citire.stop()

	def _porneste_paza(self):
		self._ceas("_ceas_paza", self._pazeste).start(PAS_PAZA_MS, True)

	def _opreste_paza(self):
		if self._ceas_paza is not None:
			self._ceas_paza.stop()

	# ---- ascultători
	def asculta(self, functie):
		if functie not in self._ascultatori:
			self._ascultatori.append(functie)

	def nu_mai_asculta(self, functie):
		if functie in self._ascultatori:
			self._ascultatori.remove(functie)

	def _notifica(self):
		if not self._ascultatori:
			return
		s = self.stare()
		for f in list(self._ascultatori):
			f(s)

	# ---- valori
	def _goleste(self, si_varful=True):
		self.nivel = None
		self.calitate = None
		self.ber = None
		self.blocat = False
		self.stare_tuner = ""
		self._blocate = 0
		if si_varful:
			self._varfuri = []
			self._plafon_din = None

	def _seteaza_tp(self, tp, extra):
		schimbat = self.tp is None or any(self.tp.get(k) != tp.get(k) for k in CAMPURI_NUCLEU)
		self.tp = dict((k, tp[k]) for k in CAMPURI_NUCLEU)
		self.extra = dict(extra or {})
		if schimbat:
			self._generatie_tp += 1
			self.tsid = self.onid = None
			self.tsid_stare = ""

	def _faza(self, faza):
		self.faza = faza

	def _verifica(self, tp):
		if tp["system"] == SISTEM_DVB_S2 and not self.s2:
			return _("Tunerul nu are DVB-S2. Alege un transponder DVB-S.")
		motiv = _reguli().motiv_refuz(tp)
		if motiv:
			return _("Transponder pe care imaginea nu îl poate acorda: %s") % motiv
		return ""

	def _leaga_standby(self):
		if self._standby_legat:
			return
		from Components.config import config
		# initial_call=False: altfel tunerul s-ar da înapoi chiar la legare (ca HdsDishMotor.py)
		config.misc.standbyCounter.addNotifier(self._la_standby, initial_call=False)
		self._standby_legat = True

	# ---- pornire, schimbare, oprire
	def _cine(self, cine):
		"""Numai ecranul spune „ecran”; orice altceva e web-ul."""
		return "ecran" if cine == "ecran" else "web"

	def _refuz_pentru(self, cine):
		"""Motivul refuzului pentru cel care cere, sau "": cât e deschis ecranul, web-ul nu atinge măsurarea."""
		if cine != "ecran" and self.ecran_deschis:
			return _("Găsirea semnalului e deschisă pe televizor.")
		return ""

	def porneste(self, slot, tp, cine="web", sesiune=None, extra=None, s2=True):
		"""Pornește măsurarea pe slot, cu transponderul tp (cele 10 câmpuri). Întoarce (True, "") sau (False, text)."""
		cine = self._cine(cine)
		refuz = self._refuz_pentru(cine)
		if refuz:
			return False, refuz
		if cine == "web":
			self._ultima_cerere_web = time.monotonic()
		preluata = cine == "ecran" and self.cine == "web" and (self.tuner.are_tuner() or self.tuner.asteapta())
		self._eveniment = _("Măsurarea pornită din web a fost preluată de televizor.") if preluata else ""
		self.cine, self.sesiune, self.s2 = cine, sesiune, s2
		self._mesaj, self._motor_la_refuz, self._tp_dupa_motor = "", False, None
		self._mesaj_scurt = ("", 0.0)
		# fiecare pornire măsoară din nou cât durează citirea (măsurarea e una singură pe proces)
		self._durate, self._pas_ms = [], PAS_CITIRE_MS
		self._opreste_citirea()
		self._goleste()
		if (slot is None or slot < 0 or tp is None) and self.tuner.are_tuner():
			self.tuner.elibereaza(reda_canalul=False)
		if slot is None or slot < 0:
			self.slot, self.tp = -1, None
			self._faza("fara_tuner")
			self._notifica()
			return False, _("Receptorul nu are niciun tuner de satelit, deci aici nu se poate măsura semnalul.")
		if tp is None:
			self.slot, self.tp = slot, None
			self._faza("fara_sateliti")
			self._notifica()
			return False, _("Tunerul nu are niciun satelit configurat. Configurează antena în „Setări tuner”, apoi revino aici.")
		self._leaga_standby()
		if self.tuner.are_tuner() and self.tuner.slot != slot:
			self.tuner.elibereaza(reda_canalul=False)
		self.slot = slot
		self._seteaza_tp(tp, extra)
		self.incercari = 0
		eroare = self._verifica(self.tp)
		if eroare:
			self._refuz(eroare)
			return False, eroare
		inceput = urmatoarea_inregistrare()
		if inceput is not None and inceput - time.time() <= INREGISTRARE_OPRIRE_S:
			if self.tuner.are_tuner() or self.tuner.am_oprit_canalul:
				self.tuner.elibereaza(reda_canalul=True)
			self._faza("inregistrare_programata")
			self._mesaj = _("La %s începe o înregistrare programată și are nevoie de tuner. Măsoară după ce se termină.") % _ora(inceput)
			self._notifica()
			return False, self._mesaj
		self._porneste_paza()
		self._preia_datoria()
		if self.tuner.are_tuner():
			return self._acordeaza()
		self._faza("alocare")
		self._notifica()
		self.tuner.ia(slot, self._dupa_alocare, sesiune)
		return True, ""

	def _dupa_alocare(self, ok, motiv):
		if not ok:
			self._opreste_paza()
			self._goleste()
			# tunerul tinut de o transmisie in retea: textul spune de ce si ce poti face (verdictul se schimba si el)
			self._mesaj = mesaj_tuner_ocupat(_adrese_transmisie()) if motiv == "ocupat" else ""
			self._ocupat_transmisie = bool(self._mesaj)
			self._faza(motiv)
			self._notifica()
			return
		self._acordeaza()

	def schimba(self, tp, extra=None, cine="web"):
		"""Alt transponder pe același tuner (din ecran sau din web). Întoarce (reușit, text)."""
		cine = self._cine(cine)
		refuz = self._refuz_pentru(cine)
		if refuz:
			return False, refuz
		if tp is None or self.slot < 0:
			return False, _("Măsurarea nu e pornită.")
		if cine == "web":
			self._ultima_cerere_web = time.monotonic()
		eroare = self._verifica(tp)
		if eroare:
			self._seteaza_tp(tp, extra)
			self._tp_dupa_motor = None
			self._refuz(eroare)
			return False, eroare
		if (self.faza == "motor" and self.tp is not None and self.tuner.are_tuner()
				and tp["orbital_position"] == self.tp["orbital_position"]):
			# același satelit cât merge motorul: un acord acum ar uita poziția de plecare (estimarea dispare,
			# timpul maxim devine 6 minute); se acordează după oprire (revizia, punctul 4)
			self._tp_dupa_motor = (dict((k, tp[k]) for k in CAMPURI_NUCLEU), dict(extra or {}))
			self._notifica()
			return True, ""
		self._tp_dupa_motor = None
		self._seteaza_tp(tp, extra)
		self.incercari = 0
		if not self.tuner.are_tuner() or self.tuner.slot != self.slot:
			# fără tuner (după standby, după scaner) măsurarea pornește din nou și e a celui care cere acum: o cerere
			# din web face o măsurare a web-ului, cu paza ei de 30 s, nu una „a ecranului” rămasă fără pază. Un tuner
			# ținut pe alt slot decât cel arătat nu se acordează: porneste îl dă înapoi și ia slotul arătat.
			return self.porneste(self.slot, self.tp, cine, self.sesiune, self.extra, self.s2)
		return self._acordeaza()

	def reacordeaza(self, cine="web"):
		"""Același transponder, din nou (tasta galbenă). Întoarce (reușit, text)."""
		cine = self._cine(cine)
		refuz = self._refuz_pentru(cine)
		if refuz:
			return False, refuz
		if cine == "web":
			self._ultima_cerere_web = time.monotonic()
		if self.tp is None or self.slot < 0:
			return False, _("Măsurarea nu e pornită.")
		if self.faza == "motor":
			self._mesaj_scurt = (_("Antena se rotește: acordul din nou se face după ce se oprește."),
				time.monotonic() + MESAJ_SCURT_S)
			self._notifica()
			return False, self._mesaj_scurt[0]
		if not self.tuner.are_tuner() or self.tuner.slot != self.slot:
			return self.porneste(self.slot, self.tp, cine, self.sesiune, self.extra, self.s2)
		eroare = self._verifica(self.tp)
		if eroare:
			self._refuz(eroare)
			return False, eroare
		self.incercari = 0
		return self._acordeaza(ce="gasire semnal, reacordare")

	def opreste(self, reda_canalul=True, cine="web"):
		"""Dă tunerul înapoi și, dacă i se cere, pornește canalul oprit de noi. Întoarce (reușit, text)."""
		refuz = self._refuz_pentru(self._cine(cine))
		if refuz:
			return False, refuz
		self._opreste(reda_canalul)
		return True, ""

	def _opreste(self, reda_canalul=True):
		"""Oprirea: din opreste() și din modul (paza, standby). Ascultătorii rămân (ecranul și-l scoate singur la
		închidere), deci după scaner barele se mișcă din nou (revizia, punctul 18)."""
		self._opreste_citirea()
		self._opreste_paza()
		self._generatie_tp += 1
		self._tsid_in_asteptare = False
		self._tp_dupa_motor = None
		if not reda_canalul:
			# cine oprește fără canal (scanerul pornit din verde, standby-ul) ține el canalul de pus la loc: cel datorat
			# după o cedare trece înapoi în LuareTuner, ca paza datoriei să nu-l pornească peste scaner
			self._preia_datoria()
		self.tuner.elibereaza(reda_canalul)
		self._goleste()
		self._motor, self._motor_era = {}, False
		self._faza("oprita")
		self._notifica()

	def arata_refuz(self, text, slot=None, cine="web"):
		"""Câmpurile nu descriu un transponder care se poate acorda (de exemplu frecvența lipsă): nimic nu pleacă
		spre nucleu, iar ecranul spune de ce. Întoarce (reușit, text)."""
		refuz = self._refuz_pentru(self._cine(cine))
		if refuz:
			return False, refuz
		if slot is not None and slot >= 0:
			if slot != self.tuner.slot and (self.tuner.are_tuner() or self.tuner.asteapta()):
				# tunerul ținut e al altui slot: se dă înapoi, ca la porneste pe alt tuner (canalul oprit rămâne de pus
				# la loc la oprire). Altfel ecranul și pagina ar arăta slotul nou, iar acordul următor ar pleca pe
				# frontendul celui vechi (verificarea finală, Mediu 1)
				self.tuner.elibereaza(reda_canalul=False)
			self.slot = slot
		self._tp_dupa_motor = None
		self._refuz(text)
		return True, ""

	def tine_viu(self):
		"""Pagina web o cheamă la fiecare cerere de stare; fără ea 30 s, măsurarea se oprește singură."""
		self._ultima_cerere_web = time.monotonic()

	def spune_scurt(self, text):
		"""Un rând scurt deasupra detaliilor (o tastă care acum nu are ce face spune de ce). Cât merge citirea, rândul
		dispare după câteva secunde; fără citire rămâne până la următoarea pornire."""
		self._mesaj_scurt = (text, time.monotonic() + MESAJ_SCURT_S)
		self._notifica()

	def iesirea_opreste_antena(self):
		"""True când motorul se mișcă și la ieșire nu se pune niciun canal la loc: fără canal, frontendul se închide
		după 3 s și îi taie tensiunea, deci antena rămâne în drum (revizia, punctul 1)."""
		in_mers = self.faza == "motor" or (self.faza == "refuzat" and self._motor_la_refuz)
		return in_mers and not (self.tuner.am_oprit_canalul and self.tuner.oldref is not None)

	# ---- acordul
	def _acordeaza(self, faza="acord", ce="gasire semnal"):
		self._opreste_citirea()
		# la reacordarea singură a aceluiași transponder vârful din ultimele 10 s rămâne (ajută la aliniere)
		self._goleste(si_varful=faza == "acord")
		m = self._stare_motor()
		se_misca = bool(m.get("se_misca"))
		anunta_motorul("%s: %s" % (self.cine or "web", ce))
		cod = acordeaza(self.tuner.frontend, self.tp)
		if cod != 0:
			self._motor_la_refuz = se_misca
			self._refuz(_("Tunerul nu poate acorda %s: frecvența nu intră în banda LNB-ului sau satelitul lipsește din setările tunerului.") % text_transponder(self.tp))
			return False, self._mesaj
		in_driver = self._in_driver
		if in_driver is None or in_driver[0] is not self.tuner.frontend or in_driver[1] != self.tp:
			# alt transponder (sau alt tuner): până la SET_FRONTEND driverul arată încă transponderul de dinainte, cu
			# nucleul în TUNING (frontend.cpp, tune; cu motorul, câteva secunde: sec.cpp); până iese nucleul din
			# TUNING, citirile nu intră în vârful calității
			self._varf_asteapta = True
		self._in_driver = (self.tuner.frontend, dict(self.tp))
		self._motor_la_refuz = False
		self._mesaj = ""
		self.incercari += 1
		self._t_acord = self._t_baza = time.monotonic()
		self._faza(faza)
		self._notifica()
		self._porneste_citirea()
		return True, ""

	def _refuz(self, text):
		"""Refuz (din Python sau din nucleu): citirea se oprește și cifrele se golesc, ca ecranul să nu arate semnalul
		altui transponder rămas în driver sub „nu poate acorda” (revizia, punctul 2)."""
		self._opreste_citirea()
		self._goleste()
		self._mesaj = text
		self._faza("refuzat")
		self._notifica()

	def _reacord_singur(self):
		"""Reacordarea singură în „fără semnal” și „semnal pierdut”: nucleul doar marchează FAILED și nu știm dacă
		driverul mai caută după timpul lui (frontend.cpp, timeout)."""
		self._acordeaza(faza=self.faza, ce="gasire semnal, reacordare singura")

	# ---- citirea
	def _stare_motor(self):
		m = stareMotor()
		return m if m.get("slot") == self.slot else {}

	def _masoara_pasul(self, durata):
		"""Pasul citirii după media ultimelor 8 citiri: 250 ms; 500 ms peste 20 ms; 1 s peste 60 ms. Coboară la loc
		când citirile sunt iar repezi (o înregistrare care scrie pe disc încetinește citirea numai o vreme)."""
		self._durate = (self._durate + [durata])[-8:]
		medie = sum(self._durate) / len(self._durate)
		if medie > 0.060:
			self._pas_ms = 1000
			if not self._lent_scris:
				print("[HdsGasireSemnal] citirea frontendului dureaza %d ms, citesc o data pe secunda" % int(medie * 1000))
				self._lent_scris = True
		elif medie > 0.020:
			self._pas_ms = 500
		else:
			self._pas_ms = PAS_CITIRE_MS

	def _pas(self):
		fe = self.tuner.frontend
		if fe is None or self.faza not in FAZE_CU_CITIRE:
			return
		d = {}
		t0 = time.monotonic()
		fe.getFrontendStatus(d)
		self._masoara_pasul(time.monotonic() - t0)
		acum = time.monotonic()
		self.stare_tuner = d.get("tuner_state") or ""
		# FE_READ_STATUS poate arăta încă blocarea transponderului de dinainte până când secvența SEC ajunge la
		# SET_FRONTEND (cu motorul, aproape o secundă după acord). Starea nucleului iese din TUNING numai prin
		# evenimentul noului acord (frontend.cpp, feEvent), deci în TUNING blocarea citită nu se crede.
		self.blocat = bool(d.get("tuner_locked")) and self.stare_tuner != "TUNING"
		self.nivel = d.get("tuner_signal_power")
		self.calitate = d.get("tuner_signal_quality")
		self.ber = d.get("tuner_bit_error_rate")
		self._motor = self._stare_motor()
		if self.stare_tuner != "TUNING":
			# nucleul a primit evenimentul acordului de acum sau i-a trecut timpul (feEvent, timeout): driverul e pe
			# transponderul ales, deci și citirile din TUNING ale reacordărilor lui de acum încolo sunt ale lui
			self._varf_asteapta = False
		calitate = la_suta(self.calitate)
		if calitate is not None and not self._varf_asteapta and not self._motor.get("se_misca"):
			# în vârf intră numai citirile transponderului ales, cu antena oprită
			self._varfuri.append((acum, calitate))
		self._varfuri = [(t, v) for t, v in self._varfuri if acum - t <= VARF_S]
		if self._motor.get("se_misca") or self._varf_asteapta:
			# cat se misca antena sau cat driverul arata inca transponderul de dinainte, nivelul nu e al celui ales
			self._plafon_din = None
		elif self.stare_tuner != "TUNING":
			# in TUNING (si la reacordarea singura a aceluiasi transponder, la fiecare interval_incercare_s, mai scurt
			# decat VARF_S pe ratele mari) citirea nu se crede: numaratoarea ramane cum era
			self._plafon_din = plafon_din(self._plafon_din, self.nivel, acum)
		if self._motor.get("se_misca"):
			# cât se mișcă antena: nici verdict, nici acord nou; cifrele sunt citiri adevărate din timpul mersului
			self._motor_era = True
			self._blocate = 0
			self._faza("motor")
		else:
			if self._motor_era:
				self._motor_era = False
				self._t_baza = acum
				if self._tp_dupa_motor is not None:
					tp, extra = self._tp_dupa_motor
					self._tp_dupa_motor = None
					self._seteaza_tp(tp, extra)
					self.incercari = 0
					self._acordeaza(ce="gasire semnal, dupa motor")
					return
				if self.faza == "motor":
					self._faza("acord")
			if self.blocat:
				self._blocate += 1
				if self._blocate >= PRINDERI_LA_RAND and self.faza != "prins":
					self._faza("prins")
					self._mesaj = ""
					self._cere_tsid()
			else:
				self._blocate = 0
				if self.faza == "prins":
					self._faza("pierdut")
					self._t_baza = acum
				elif self.faza == "acord" and acum - self._t_baza >= interval_incercare_s(self.tp):
					self._faza("fara_semnal")
					self._reacord_singur()
					return
				elif self.faza in ("fara_semnal", "pierdut") and acum - self._t_baza >= interval_incercare_s(self.tp):
					self._reacord_singur()
					return
		self._notifica()
		self._porneste_citirea()

	# ---- TS ID / ON ID
	def _cere_tsid(self):
		if self._tsid_in_asteptare or self.tsid_stare == "citit" or self.tuner.canal is None:
			return
		generatie = self._generatie_tp
		self.tsid_stare = "se_citeste"
		cod = self.tuner.canal.requestTsidOnid(lambda tsid, onid: self._tsid_onid(generatie, tsid, onid))
		if cod is not None and cod != 0:
			# fără demux liber nucleul refuză pe loc (lib/dvb/dvb.cpp, requestTsidOnid)
			self.tsid_stare = "necitit"
			return
		self._tsid_in_asteptare = True

	def _tsid_onid(self, generatie, tsid, onid):
		self._tsid_in_asteptare = False
		if generatie != self._generatie_tp:
			# răspunsul e pentru un transponder de dinainte: se aruncă (revizia, punctul 16)
			if self.faza == "prins":
				self._cere_tsid()
			return
		if tsid is None or onid is None:
			self.tsid_stare = "necitit"
		else:
			self.tsid, self.onid, self.tsid_stare = int(tsid), int(onid), "citit"
		self._notifica()

	# ---- paza: înregistrări, pagina web
	def _pazeste(self):
		acum = time.time()
		inceput = urmatoarea_inregistrare()
		self._inregistrare_la = None
		if inceput is not None and inceput - acum <= INREGISTRARE_OPRIRE_S:
			self._opreste(reda_canalul=True)
			self._mesaj = _("Înregistrarea programată la %s are nevoie de tuner. Măsurarea s-a oprit și canalul a pornit la loc.") % _ora(inceput)
			self._faza("inregistrare_programata")
			self._notifica()
			return
		if inceput is not None and inceput - acum <= INREGISTRARE_ANUNT_S:
			self._inregistrare_la = inceput
		if self.cine == "web" and time.monotonic() - self._ultima_cerere_web > WEB_FARA_CERERE_S:
			self._opreste(reda_canalul=True)
			self._eveniment = _("Măsurarea s-a oprit: pagina web nu mai cere starea.")
			self._notifica()
			return
		self._porneste_paza()

	# ---- standby, coordonatorul
	def _la_standby(self, *argumente):
		if self._program_datorat is not None and _ecran_standby() is not None:
			# canalul datorat după o cedare trece acum la ecranul Standby, nu abia la bătaia pazei: o trezire în mai
			# puțin de o secundă l-ar pierde
			self._pazeste_datoria()
		if not (self.tuner.are_tuner() or self.tuner.asteapta() or self.tuner.am_oprit_canalul):
			return
		self._opreste(reda_canalul=False)
		self._preda_canalul_la_standby()
		self._mesaj = _("Receptorul a intrat în standby și tunerul a fost eliberat. Apasă galben ca să măsori din nou.")
		self._faza("standby")
		self._notifica()

	def _preda_canalul_la_standby(self):
		"""Standby.__init__ a ținut minte canalul de atunci, adică niciunul, fiindcă măsurarea îl oprise
		(Screens/Standby.py:51-57), deci la trezire n-ar porni nimic. Canalul oprit de noi trece la ecranul Standby,
		care îl pornește la trezire (__onClose), iar măsurarea îl uită: altfel, la următoarea măsurare, l-ar pune peste
		canalul ales după trezire. Dacă Standby ține minte alt canal (pornit între timp), rămâne acela.
		Screens.Standby e încărcat de la pornire (mytest.py), deci nu se importă aici: se ia din module. Ecranul
		Standby își pune inStandby înainte să crească contorul care ne cheamă (Standby.py, __onFirstExecBegin)."""
		ecran = _ecran_standby()
		if ecran is None:
			return      # fără ecranul Standby canalul rămâne al măsurării și pornește la oprirea ei
		vechi = self.tuner.uita_canalul()
		if vechi is not None and not getattr(ecran, "prev_running_service", None):
			ecran.prev_running_service = vechi

	def _la_cedare(self, motiv):
		"""Tunerul l-a luat altcineva prin coordonator (ecranul sau pagina „Rotirea antenei”, DAB+, T2-MI). Canalul
		oprit de măsurare nu mai rămâne în LuareTuner: acolo ar sta fără limită (paza se oprește aici, deci nici
		oprirea de la 30 s fără pagină nu mai vine) și ar porni mai târziu, la ieșirea din altă măsurare, peste canalul
		ales între timp. Trece în datoria măsurării și pornește când tunerul se eliberează (verificarea finală,
		Mediu A; ca HdsMotorComenzi.cedeaza, G3)."""
		self._opreste_citirea()
		self._opreste_paza()
		self._goleste()
		self._datoreaza(self.tuner.uita_canalul())
		self._mesaj = _("Tunerul a fost cerut de altă funcție a receptorului. Apasă galben ca să măsori din nou.")
		self._ocupat_transmisie = False
		self._faza("ocupat")
		self._notifica()

	# ---- canalul datorat după o cedare
	def _datoreaza(self, ref):
		if ref is None:
			return
		if self._program_datorat is None:
			self._program_datorat = ref
		self._ceas("_ceas_datorie", self._pazeste_datoria).start(PAS_DATORIE_MS, True)

	def _pazeste_datoria(self):
		"""O dată pe secundă cât există canalul datorat (ca HdsMotorComenzi._programulDatorat). Pornește numai când
		tunerul nu mai e ținut de nimeni prin coordonator, nu merge niciun canal și nu e deschis ecranul Standby. Un
		canal pornit între timp rămâne și datoria se stinge; în standby canalul trece la ecranul Standby, care îl
		pornește la trezire (Screens/Standby.py, __onClose)."""
		ref = self._program_datorat
		if ref is None:
			return
		nav = _nav()
		if nav is None:
			self._program_datorat = None
			return
		if nav.getCurrentlyPlayingServiceReference() is not None:
			self._program_datorat = None
			print("[HdsGasireSemnal] canalul oprit de masurare ramane oprit: intre timp a pornit alt canal")
			return
		ecran = _ecran_standby()
		if ecran is not None:
			self._program_datorat = None
			if not getattr(ecran, "prev_running_service", None):
				ecran.prev_running_service = ref
			return
		coord = _coordonator()
		if coord is not None and getattr(coord, "detinator", None) is not None:
			self._ceas_datorie.start(PAS_DATORIE_MS, True)
			return
		self._program_datorat = None
		print("[HdsGasireSemnal] tunerul s-a eliberat; canalul oprit de masurare porneste din nou")
		nav.playService(ref)

	def _preia_datoria(self):
		"""Măsurarea ia din nou tunerul (sau se oprește fără canal) înainte să pornească canalul datorat: îl ține
		LuareTuner, care îl pune la loc la oprire ca pe orice canal oprit de ea (ca TunerMotor.tineMinteProgramul).
		Dacă între timp merge alt canal, rămâne acela."""
		ref, self._program_datorat = self._program_datorat, None
		if self._ceas_datorie is not None:
			self._ceas_datorie.stop()
		if ref is None or self.tuner.am_oprit_canalul:
			return
		nav = _nav()
		if nav is not None and nav.getCurrentlyPlayingServiceReference() is None:
			self.tuner.am_oprit_canalul, self.tuner.oldref = True, ref

	# ---- ce se arată
	def _text_motor(self):
		m = self._motor
		prima = {"est": _("Antena se rotește spre est."), "vest": _("Antena se rotește spre vest.")}.get(
			m.get("directie"), _("Antena se rotește."))
		if m.get("de_la_orbital", -1) >= 0 and m.get("secunde_ramase") is not None:
			return prima + " " + _("Mai are aproximativ %s (estimat).") % secundeText(m["secunde_ramase"])
		ramas = _timp_maxim_ramas(self.slot)
		if ramas is not None:
			return prima + " " + _("Poziția de plecare nu e cunoscută: mersul poate ține încă până la %s.") % secundeText(ramas)
		return prima

	def verdict(self):
		return {
			"oprita": _("Măsurare oprită"),
			"fara_tuner": _("Niciun tuner de satelit"),
			"fara_sateliti": _("Niciun satelit configurat"),
			"alocare": _("Se acordează"),
			"ocupat": _("Tunerul e folosit de o transmisie") if getattr(self, "_ocupat_transmisie", False) else
				_("Tunerul e ocupat"),
			"inregistrare": _("Tunerul înregistrează"),
			"inregistrare_programata": _("Urmează o înregistrare"),
			"refuzat": _("Nu se poate acorda"),
			"acord": _("Se acordează"),
			"motor": _("Aștept motorul"),
			"prins": _("Semnal recepționat"),
			"fara_semnal": _("Fără semnal"),
			"pierdut": _("Semnal pierdut"),
			"standby": _("Măsurare oprită"),
		}[self.faza]

	def _varf(self):
		return max(v for t, v in self._varfuri) if self._varfuri else None

	def detalii(self):
		"""Mesajele de sub listă, cel mai important întâi, cel mult DETALII_MAXIM (revizia, punctul 7)."""
		f = self.faza
		lista = []
		scurt, pana_la = self._mesaj_scurt
		if scurt and time.monotonic() < pana_la:
			lista.append(scurt)
		canal_oprit = _("Canalul s-a oprit cât timp măsori și pornește la loc când ieși.") \
			if self.tuner.am_oprit_canalul and self.tuner.oldref is not None else ""
		inregistrare = _("La %s începe o înregistrare programată. Măsurarea se oprește singură cu un minut și jumătate înainte.") % _ora(self._inregistrare_la) \
			if self._inregistrare_la is not None else ""
		varf = self._varf()
		text_varf = _("Cea mai bună calitate în ultimele 10 s: %d %%.") % varf if varf is not None else ""
		text_atenuator = _("Nivelul e la maximul tunerului, dar semnalul nu se recepționează: poate fi prea puternic sau o "
			"interferență. Încearcă un atenuator de linie.") if self.prea_puternic() else ""
		fara_lista = _("Satelitul nu are transpondere în lista lui: se măsoară valorile bătute de mână.") \
			if self.extra.get("fara_lista") else ""
		interval = interval_incercare_s(self.tp)
		if f == "fara_tuner":
			lista.append(_("Receptorul nu are niciun tuner de satelit, deci aici nu se poate măsura semnalul."))
		elif f == "fara_sateliti":
			lista.append(_("Tunerul nu are niciun satelit configurat. Configurează antena în „Setări tuner”, apoi revino aici."))
		elif f == "ocupat":
			lista.append(self._mesaj or _("Tunerul de satelit e folosit de o transmisie în rețea sau de o extensie. Oprește-o, apoi apasă galben."))
		elif f == "inregistrare":
			lista.append(_("Tunerul de satelit înregistrează acum. Găsirea semnalului merge după terminarea înregistrării."))
		elif f in ("inregistrare_programata", "standby"):
			lista.append(self._mesaj)
		elif f == "refuzat":
			lista.append(self._mesaj)
			if self._motor_la_refuz:
				lista.append(_("Antena poate fi încă în mișcare spre satelitul de dinainte."))
		elif f == "alocare":
			lista.append(canal_oprit)
		elif f == "acord":
			lista += [inregistrare, fara_lista, canal_oprit]
			if self.extra.get("sarite"):
				lista.append(_text_sarite(self.extra["sarite"]))
		elif f == "motor":
			lista.append(self._text_motor())
			if self._tp_dupa_motor is not None:
				lista.append(_("Se acordează după ce antena se oprește."))
			else:
				lista.append(_("Cifrele sunt din timpul mersului. Verdictul vine după ce antena se oprește."))
		elif f == "prins":
			lista += [inregistrare, self._text_retea(), text_varf, canal_oprit]
		elif f == "fara_semnal":
			lista += [inregistrare, text_atenuator, fara_lista,
				_("Niciun semnal în %d s. Se încearcă singur din nou la fiecare %d s (încercarea %d). Mișcă antena încet.") % (
					timp_prindere_s(self.tp), interval, max(1, self.incercari)),
				text_varf]
		elif f == "pierdut":
			lista += [inregistrare, text_atenuator, _("Semnalul s-a pierdut. Se încearcă din nou la fiecare %d s.") % interval,
				text_varf]
		lista = [x for x in lista if x]
		return lista[:DETALII_MAXIM]

	def prea_puternic(self):
		"""Semnul de semnal prea puternic sau de interferenta (intrare_prea_puternica), pentru acum."""
		return intrare_prea_puternica(self.faza, getattr(self, "_plafon_din", None), time.monotonic())

	def _text_retea(self):
		if self.tsid_stare != "citit":
			return ""
		tsid_asteptat, onid_asteptat = self.extra.get("tsid", -1), self.extra.get("onid", -1)
		if onid_asteptat is None or onid_asteptat < 0:
			return ""
		if self.onid != onid_asteptat:
			return _("ON ID %d, iar în lista satelitului e %d. Antena poate fi pe alt satelit.") % (self.onid, onid_asteptat)
		if tsid_asteptat is None or tsid_asteptat < 0 or self.tsid != tsid_asteptat:
			return ""
		return _("Rețea confirmată: TS ID și ON ID sunt cele din lista satelitului.")

	def _text_id(self, valoare):
		if self.tsid_stare == "citit":
			return str(valoare)
		if self.tsid_stare == "se_citeste":
			return _("se citește")
		if self.tsid_stare == "necitit":
			return _("necitit")
		return ""

	def _text_antena(self):
		if self.tp is None:
			return ""
		m = self._motor
		if self.faza == "motor" and m.get("la_orbital", -1) >= 0:
			return "%s %s" % (_("spre"), text_pozitie(m["la_orbital"]))
		if self.faza == "motor":
			return _("se rotește")
		return text_pozitie(self.tp["orbital_position"])

	def stare(self):
		"""Starea ca dicționar simplu (numere și texte, nimic din enigma), pentru ecran și pentru web."""
		citeste = self.faza in FAZE_CU_CITIRE
		varf = self._varf()
		motor = dict(self._motor) if self._motor else {}
		return {
			"faza": self.faza,
			"verdict": self.verdict(),
			"detalii": self.detalii(),
			"eveniment": self._eveniment,
			"detinator": self.cine,
			"slot": self.slot,
			"tp": dict(self.tp) if self.tp else None,
			"tp_text": text_transponder(self.tp) if self.tp else "",
			"pozitie_text": self._text_antena(),
			"nivel_brut": self.nivel if citeste else None,
			"calitate_bruta": self.calitate if citeste else None,
			"nivel_la_suta": la_suta(self.nivel) if citeste else None,
			"calitate_la_suta": la_suta(self.calitate) if citeste else None,
			"calitate_db": None,   # nucleul nu are formula pentru tunerul nostru (frontend.cpp, 0x12345678)
			"ber": self.ber if citeste else None,
			"blocat": bool(self.blocat) if citeste else False,
			"stare_tuner": self.stare_tuner if citeste else "",
			"varf_calitate_10s": varf,
			# nivelul sta la plafonul driverului si tunerul nu prinde: poate fi prea puternic (sfatul e in detalii)
			"prea_puternic": self.prea_puternic() if citeste else False,
			"incercari": self.incercari,
			"secunde": int(time.monotonic() - self._t_acord) if citeste else 0,
			"motor": motor,
			"motor_text": self._text_motor() if self.faza == "motor" else "",
			"acord_dupa_motor": self._tp_dupa_motor is not None,
			"tsid": self.tsid if self.tsid_stare == "citit" else None,
			"onid": self.onid if self.tsid_stare == "citit" else None,
			"tsid_text": self._text_id(self.tsid),
			"onid_text": self._text_id(self.onid),
			"tsid_asteptat": self.extra.get("tsid", -1),
			"onid_asteptat": self.extra.get("onid", -1),
			"canal_oprit": bool(self.tuner.am_oprit_canalul),
			"canal_datorat": self._program_datorat is not None,
			"iesirea_opreste_antena": self.iesirea_opreste_antena(),
		}


def _timp_maxim_ramas(slot):
	"""Cât mai poate merge motorul după nucleu (mrt din sec.cpp minus cât a trecut), în secunde, sau None."""
	try:
		from enigma import eDVBSatelliteEquipmentControl
		sec = eDVBSatelliteEquipmentControl.getInstance()
		maxim = int(sec.hdsRotorSeconds(slot))
		trecut = int(sec.hdsRotorElapsedMs(slot))
	except (ImportError, AttributeError):
		return None
	if maxim <= 0 or trecut < 0:
		return None
	return max(0, maxim - trecut // 1000)


_masurare = None


def masurare():
	"""Măsurarea unică a procesului (ecranul și web-ul o împart)."""
	global _masurare
	if _masurare is None:
		_masurare = Masurare()
	return _masurare
