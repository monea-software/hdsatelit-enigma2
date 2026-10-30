# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsProcesor.py: modul de lucru al procesorului (plafonul de frecventa), paza de caldura si citirile pentru ecranul
# „Procesor” (Screens/HdsProcesor.py), pagina web /procesor (HdsWebControl/procesor_web.py), „Informatii” si bara.
#
# Ce se schimba: numai scaling_max_freq din politica cpufreq (o singura politica pentru toate nucleele pe Hi3798MV200).
# Guvernorul (interactive, cu valorile puse de scriptul fabricantului) ramane cum e: el alege treapta dupa sarcina, sub
# plafon. Treptele se citesc din scaling_available_frequencies, nu sunt scrise in cod.
#
# Modurile (config.hds_procesor.mod):
#   normal       plafonul fabricantului (randul „echo N > .../scaling_max_freq” din /lib/modules/*/extra/load); sub
#                95 °C nu se scrie nimic cat timp nu s-a scris nimic in aceasta pornire a receptorului;
#   racoros      cel mult 800 MHz;
#   performanta  treapta cea mai inalta probata cat T < PERF_COBORARE (85 °C); la T >= 85 coboara direct la treapta
#                cea mai mica a procesorului (din scaling_available_frequencies) si urca la loc tot dintr-odata, numai
#                dupa ce T a stat PERF_RACIRE_S (60 s) la PERF_URCARE (78 °C) sau sub el;
#   automat      scara sus / fabricant / racoros: coborare la 80 si 88 °C, urcare cu o treapta la prag - 6 °C,
#                dupa 60 s.
# Treptele peste plafonul fabricantului se folosesc numai pana la treapta scrisa in PROBAT (/etc/enigma2), semnul pus
# dupa proba de caldura pe receptor. Fara semn: performanta nu exista, automat porneste de la plafonul fabricantului.
# Paza comuna (toate modurile, si normal): la T >= 95 °C plafonul coboara la 600 MHz; revine dupa 60 s la T <= 88 °C.
# In performanta treapta de caldura e oricum mai jos, deci acolo paza comuna nu mai schimba nimic.
# Coborarea cere 2 citiri la rand peste prag (un varf izolat de citire nu conteaza); urcarea e lenta. Fara temperatura
# valida 15 s, plafonul nu trece de al fabricantului (in performanta si inca URCARE_DUPA_S dupa ce temperatura
# revine). Cat paza driverului („Temp Control is ...” din pm_cpu) nu e in starea normala, nu se urca. Pragurile
# performantei sunt grupate in PERF_*, ca sa se mute usor dupa proba de caldura; celelalte sunt provizorii.
#
# Aplicarea: firul „hds-procesor” citeste la PERIOADA_S secunde (pm_cpu si scaling_max_freq, ~1,2 ms) si scrie
# plafonul numai cand se schimba hotararea. Daca plafonul citit difera de cel scris ultima data (l-a schimbat alt
# program sau paza driverului), nu se rescrie ALTCINEVA_S secunde. Scrierile in sysfs sunt in RAM. Tot la fiecare pas,
# o citire din /proc/stat: procesorul folosit intre doi pasi (folositRecent), pentru "Incarcare CPU" la deschidere.
# FABRICANT_RAM (/var/run, tmpfs) tine plafonul gasit la prima pornire a modulului in aceasta pornire a receptorului si
# semnul „am scris”, ca o repornire a interfetei sa nu ia valoarea noastra drept a fabricantului.
# La iesirea curata a enigma2 (laOprire) se pune la loc plafonul fabricantului, numai daca s-a scris ceva.
#
# Pornirea sigura (modurile care pot trece de plafonul fabricantului): primele PORNIRE_SIGURA_S secunde plafonul ramane
# al fabricantului. Cand plafonul trece prima data de al fabricantului, PROBA (/etc/enigma2) primeste boot_id si un
# contor; la iesirea curata se sterge. La pornire, un PROBA cu alt boot_id inseamna o pornire a receptorului incheiata
# necurat cu procesorul accelerat; la OPRIRI_NECURATE la rand modul accelerat salvat trece pe normal. Trecerea pe un mod
# care nu accelereaza sterge PROBA (pornirea nu se mai incheie cu procesorul accelerat).
#
# Alegerile setarii se fac o data, la pornirea interfetei, dupa receptor (cpufreq, trepte, semnul probei, senzorul);
# ecranul, pagina web si seteazaMod folosesc aceleasi alegeri. Senzorul pierdut dupa pornire e tratat de paza
# (fara_temp). Un mod salvat care nu e printre alegeri ramane salvat pana il schimba omul (ConfigModProcesor).
#
# Firul nu cheama nimic din enigma2: citeste si scrie fisiere. Mesajele pe ecran trec printr-o coada golita de un
# eTimer din firul principal. Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct,
# cu RADACINA spre un arbore fals.
#
# Mesajele pe ecran: „s-a incalzit” la intrarea in paza comuna sau in treapta de caldura a performantei, cel mult o
# data la MESAJ_PAUZA_S (un receptor care urca si coboara des pe prag nu umple ecranul); „s-a racit” la revenirea
# plafonului, numai dupa un „s-a incalzit” aratat. Intervalul de caldura se deschide si se inchide si cand plafonul
# e deja cel hotarat (l-a lasat un proces enigma2 cazut sau l-a pus alt program), nu numai la o scriere. Ecranul
# „Procesor” si pagina web spun „s-a racit” inca RACIT_ARATAT_S dupa revenire. Ceasul ultimului mesaj sta in
# FABRICANT_RAM (ceasul monoton e al sistemului, deci tine si peste o repornire a interfetei). In coada de mesaje a
# ecranului, „s-a racit” scoate un „s-a incalzit” inca nearatat (episodul s-a incheiat); in standby nu se arata nimic.
#
# Istoricul pentru grafic (ecranul „Procesor” si pagina web): la fiecare pas, firul pune temperatura, frecventa si
# modul in Istoric, un tampon circular cu cel mult ISTORIC_MINUTE minute incheiate si minutul de acum (cea mai mare
# temperatura din minut, media ei, media frecventei, daca procesorul a fost incetinit de caldura si modul). La fiecare
# minut incheiat firul scrie minutele in ISTORIC_RAM (/var/run, tmpfs, nimic pe eMMC); pregateste() le citeste inapoi
# cand boot_id e acelasi, deci ora ramane peste o repornire a interfetei si incepe din nou numai la repornirea
# receptorului. istoricGrafic() da punctele, bucatile de timp ale fiecarui mod cu pragurile lor, scara, liniile
# pragurilor si orele de sub grafic; desenGrafic() le face operatii de desen pentru eCanvas (televizorul); pagina web
# le deseneaza in SVG.

import glob
import io
import math
import os
import re
import sys
import threading
import time
from collections import deque

RADACINA = os.environ.get("HDS_PROCESOR_RADACINA", "/")

CPUFREQ = "/sys/devices/system/cpu/cpu0/cpufreq"
PM_CPU = ("/proc/msp/pm_cpu", "/proc/hisi/msp/pm_cpu")
PM_TEMP = ("/proc/msp/pm_temp", "/proc/hisi/msp/pm_temp")
TERMICE = ("/sys/class/thermal/thermal_zone0/temp", "/sys/devices/virtual/thermal/thermal_zone0/temp")
SCRIPT_LOAD = "/lib/modules/*/extra/load"
STAT = "/proc/stat"
BOOT_ID = "/proc/sys/kernel/random/boot_id"
FABRICANT_RAM = "/var/run/hds-procesor.fabricant"
ISTORIC_RAM = "/var/run/hds-procesor.istoric"   # minutele incheiate ale graficului (tmpfs), peste o repornire a interfetei
PROBA = "/etc/enigma2/hds-procesor.proba"
PROBAT = "/etc/enigma2/hds-procesor.probat"     # treapta cea mai inalta probata la caldura, in kHz (numai citit)
JURNAL = "/home/root/logs/hds-procesor.log"
JURNAL_RANDURI = 200
JURNAL_TAIERE_OCTETI = 24 * 1024
JURNAL_PE_PORNIRE = 50          # randuri scrise pe disc de un proces enigma2, ca un receptor la limita sa nu scrie des

MODURI = ("automat", "racoros", "normal", "performanta")
MODURI_ACCELERATE = ("automat", "performanta")
IMPLICIT = "normal"

PERIOADA_S = 5
PORNIRE_SIGURA_S = 180
URCARE_DUPA_S = 60
FARA_TEMP_S = 15
ALTCINEVA_S = 300
CITIRI_COBORARE = 2
OPRIRI_NECURATE = 2
TEMP_MIN = 1
TEMP_MAX = 125

# performanta: pragurile (°C) si cat timp trebuie sa stea racit, din proba de caldura pe Hi3798MV200: la 1600 MHz sub
# sarcina pe 4 nuclee 95 °C in ~80 s; in folosire obisnuita (canale HD si 4K, schimbari de canal) 71-76 °C; racirea la
# 400 MHz se opreste pe un platou de 75 °C. Urcarea e deci peste ce atinge receptorul in folosire obisnuita.
PERF_COBORARE = 85          # de aici plafonul coboara la treapta cea mai mica a procesorului
PERF_URCARE = 78            # si urca la loc, la treapta cea mai inalta probata, numai dupa racirea pana aici
PERF_RACIRE_S = 60          # secunde la rand la PERF_URCARE sau sub el

# celelalte praguri (°C), provizorii pana la proba de caldura
RACOROS_KHZ = 800000
PAZA_KHZ = 600000
AUTO_COBORARE = (80, 88)
HISTEREZIS = {"automat": 6}     # urcarea automatului: pragul treptei minus atat
PAZA_COBORARE = 95
PAZA_URCARE = 88
TEMP_GALBEN = 80

MESAJ_PAUZA_S = 300         # intre doua mesaje „s-a incalzit” pe ecran (sub sarcina coborarile vin la ~5-7 minute)
RACIT_ARATAT_S = 300        # cat timp ecranul si pagina spun „s-a racit” dupa revenirea plafonului

# graficul: istoricul din RAM si alegerile lui
ISTORIC_MINUTE = 60         # minutele incheiate tinute in tampon (graficul arata cel mult ultima ora)
GRAFIC_MINUTE = (60, 30)    # alegerile graficului, in minute; prima e cea implicita
GRAFIC_JOS = 50             # scara incepe de la 50 °C, mai jos numai daca temperatura coboara acolo
GRAFIC_SUS_MAX = 130
CEAS_POTRIVIT = 1577836800  # 2020-01-01: sub el ceasul receptorului nu e pus inca (sub grafic: „X min” in loc de ora)
MOTIVE_CALDURA = ("paza", "caldura", "driver")   # plafonul tinut jos de caldura (bara frecventei galbena)

# motivele plafonului de acum; ordinea da prioritatea la egalitate
MOTIVE = ("paza", "fara_temp", "caldura", "pornire_sigura", "altcineva", "driver", "")


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la afisare."""
	return text


NUME = {
	"automat": N_("Automat"),
	"racoros": N_("Răcoros"),
	"normal": N_("Normal (ca de la fabricant)"),
	"performanta": N_("Performanță"),
}

NUME_SCURT = {
	"automat": N_("Automat"),
	"racoros": N_("Răcoros"),
	"normal": N_("Normal"),
	"performanta": N_("Performanță"),
}


def monotonic():
	return time.monotonic()


def _jurnal(text):
	print("[HdsProcesor] %s" % text)


# ---------------------------------------------------------------- fisierele

def cale(c):
	"""Calea adevarata: exact c pe receptor, sau c sub RADACINA (arborele fals al probelor si al emulatorului)."""
	if not RADACINA or RADACINA == "/":
		return c
	return os.path.join(RADACINA, c.lstrip("/"))


def _procFundal(functie, *argumente):
	# fisierele driverului (/proc/msp, /proc/hisi), citite de pe firul principal: prin firul de fundal
	# (Components/HdsProcFundal.py); fara modul (probele de pe PC), direct
	try:
		from Components import HdsProcFundal
	except Exception:
		return functie(*argumente)
	return HdsProcFundal.citeste(functie, *argumente)


def _citeste_direct(c, maxim=16384):
	try:
		with io.open(cale(c), "r", encoding="utf-8", errors="replace") as f:
			return f.read(maxim)
	except (IOError, OSError):
		return None


def _citeste(c, maxim=16384):
	"""Ca _citeste_direct; fisierele driverului (/proc/msp, /proc/hisi) le citeste pe firul de fundal."""
	return _procFundal(_citeste_direct, c, maxim)


def _intreg(valoare, implicit=0):
	try:
		return int(str(valoare).strip())
	except (TypeError, ValueError):
		return implicit


def _scrieAtomic(c, text):
	"""Scrie in c.nou si muta peste c; intoarce True daca a reusit."""
	real = cale(c)
	nou = real + ".nou"
	try:
		with io.open(nou, "w", encoding="utf-8") as f:
			f.write(text)
		os.replace(nou, real)
		return True
	except (IOError, OSError):
		try:
			os.remove(nou)
		except OSError:
			pass
		return False


def _sterge(c):
	try:
		os.remove(cale(c))
		return True
	except OSError:
		return False


def citesteCheiValori(c):
	text = _citeste(c, 4096)
	if text is None:
		return None
	d = {}
	for rand in text.splitlines():
		cheie, semn, valoare = rand.partition("=")
		if semn:
			d[cheie.strip()] = valoare.strip()
	return d


def textCheiValori(d):
	return "".join("%s=%s\n" % (k, d[k]) for k in sorted(d))


# ---------------------------------------------------------------- citirea textelor (functii fara efecte)

_RE_TEMP = re.compile(r"temperature\s*=\s*(-?\d+)", re.I)
_RE_VOLT = re.compile(r"current\s+volt\s*=\s*(\d+)", re.I)
_RE_FREQ = re.compile(r"freq\s*=\s*(\d+)\s*\(khz\)", re.I)
_RE_STARE = re.compile(r"Temp\s+Control\s+is\s+([^\r\n]+)")
_RE_PAZA = {
	"coborare": re.compile(r"down\s+threshold:\s*(\d+)", re.I),
	"revenire": re.compile(r"up\s+threshold:\s*(\d+)", re.I),
	"repornire": re.compile(r"reboot\s+threshold:\s*(\d+)", re.I),
}
_RE_PAZA_PORNITA = re.compile(r"control\s+is\s+(on|off)", re.I)
_RE_LOAD = re.compile(r"^\s*echo\s+(\d+)\s*>\s*\S*/scaling_max_freq\s*$")


def parsePmCpu(text):
	"""/proc/msp/pm_cpu: frecventa vazuta de driver, tensiunea, temperatura si starea pazei driverului."""
	rez = {"frecventa_khz": None, "tensiune_mv": None, "temperatura": None, "stare_driver": None}
	if not text:
		return rez
	m = _RE_FREQ.search(text)
	if m:
		rez["frecventa_khz"] = int(m.group(1))
	m = _RE_VOLT.search(text)
	if m:
		rez["tensiune_mv"] = int(m.group(1))
	m = _RE_TEMP.search(text)
	if m:
		rez["temperatura"] = int(m.group(1))
	m = _RE_STARE.search(text)
	if m:
		rez["stare_driver"] = m.group(1).strip()
	return rez


def parsePmTemp(text):
	"""/proc/msp/pm_temp: pragurile pazei driverului, sau None daca lipsesc."""
	if not text:
		return None
	rez = {}
	for cheie, rx in _RE_PAZA.items():
		m = rx.search(text)
		if not m:
			return None
		rez[cheie] = int(m.group(1))
	m = _RE_PAZA_PORNITA.search(text)
	rez["pornita"] = bool(m) and m.group(1).lower() == "on"
	return rez


def parseTrepte(text):
	"""scaling_available_frequencies: treptele in kHz, crescator, fara repetari."""
	if not text:
		return []
	trepte = set()
	for parte in text.split():
		v = _intreg(parte, 0)
		if v > 0:
			trepte.add(v)
	return sorted(trepte)


def parseTimeInState(text):
	"""stats/time_in_state: [(khz, secunde)], crescator dupa frecventa. Unitatile nucleului sunt de 10 ms."""
	rez = []
	if not text:
		return rez
	for rand in text.splitlines():
		parti = rand.split()
		if len(parti) != 2:
			continue
		khz = _intreg(parti[0], 0)
		unitati = _intreg(parti[1], -1)
		if khz > 0 and unitati >= 0:
			rez.append((khz, unitati / 100.0))
	rez.sort()
	return rez


def plafonDinLoad(text):
	"""Plafonul pus de scriptul fabricantului: ultimul rand necomentat „echo N > .../scaling_max_freq”."""
	if not text:
		return None
	gasit = None
	for rand in text.splitlines():
		if rand.lstrip().startswith("#"):
			continue
		m = _RE_LOAD.match(rand)
		if m and int(m.group(1)) > 0:
			gasit = int(m.group(1))
	return gasit


def parseStat(text):
	"""Primul rand din /proc/stat: (total, inactiv) in unitati de ceas; None daca lipseste."""
	if not text:
		return None
	for rand in text.splitlines():
		if rand.startswith("cpu "):
			valori = [_intreg(x, 0) for x in rand.split()[1:9]]
			if len(valori) < 5:
				return None
			return sum(valori), valori[3] + valori[4]
	return None


def procentFolosit(inainte, acum):
	"""Procentul de timp in care procesorul a lucrat intre doua citiri din /proc/stat (inainte None = de la pornire)."""
	if acum is None:
		return None
	total, inactiv = acum
	if inainte is not None:
		total -= inainte[0]
		inactiv -= inainte[1]
	if total <= 0:
		return None
	return max(0, min(100, int(round(100.0 * (total - inactiv) / total))))


def temperaturaValida(t):
	return t is not None and TEMP_MIN <= t <= TEMP_MAX


def driverNormal(stare_driver):
	"""Starea pazei driverului: lipsa (alt receptor) sau „Normal Temp” inseamna ca driverul nu incetineste."""
	return not stare_driver or "normal" in stare_driver.lower()


# ---------------------------------------------------------------- treptele si hotararea (functii fara efecte)

def treaptaCelMult(trepte, khz):
	"""Cea mai mare treapta <= khz; daca nu e niciuna, cea mai mica treapta."""
	if not trepte:
		return None
	potrivite = [t for t in trepte if t <= khz]
	return max(potrivite) if potrivite else min(trepte)


def plafoane(trepte, fabricant):
	"""Plafoanele folosite, in kHz, din treptele reale: sus, fabricant, racoros, paza si jos (treapta cea mai mica,
	a performantei la caldura)."""
	if not trepte:
		return None
	sus = max(trepte)
	fab = treaptaCelMult(trepte, fabricant) if fabricant else sus
	return {
		"sus": sus,
		"fabricant": fab,
		"jos": min(trepte),
		"racoros": min(treaptaCelMult(trepte, RACOROS_KHZ), fab),
		"paza": min(treaptaCelMult(trepte, PAZA_KHZ), fab),
	}


def trepteFolosite(trepte, fabricant, probat=None):
	"""Treptele pe care le poate folosi paza: toate pana la plafonul fabricantului, iar peste el numai pana la treapta
	probata (semnul PROBAT). Fara semn nu se trece de plafonul fabricantului."""
	if not trepte:
		return []
	fab = treaptaCelMult(trepte, fabricant) if fabricant else max(trepte)
	limita = max(fab, probat or 0)
	return [t for t in trepte if t <= limita]


def scara(mod, pl):
	"""Treptele modului, de sus in jos: [(khz, prag)]; prag = temperatura de la care se coboara in treapta aceasta
	(None la prima). O treapta egala cu cea de deasupra se sare (de ex. fara treapta peste plafonul fabricantului).
	Performanta are doua trepte: sus si, de la PERF_COBORARE, direct treapta cea mai mica."""
	if mod == "racoros":
		niveluri = [(pl["racoros"], None)]
	elif mod == "performanta":
		niveluri = [(pl["sus"], None), (pl["jos"], PERF_COBORARE)]
	elif mod == "automat":
		niveluri = [(pl["sus"], None), (pl["fabricant"], AUTO_COBORARE[0]), (pl["racoros"], AUTO_COBORARE[1])]
	else:
		niveluri = [(pl["fabricant"], None)]
	rez = []
	for khz, prag in niveluri:
		if rez and khz >= rez[-1][0]:
			continue
		rez.append((khz, prag if rez else None))
	return rez


def _nivelPentru(niveluri, temp):
	nivel = 0
	for i, (khz, prag) in enumerate(niveluri):
		if prag is not None and temp >= prag:
			nivel = i
	return nivel


def pragUrcare(mod, prag):
	"""Temperatura pana la care trebuie sa scada ca plafonul sa urce de pe treapta coborata la `prag`: in performanta
	PERF_URCARE, in automat pragul minus HISTEREZIS."""
	if mod == "performanta":
		return PERF_URCARE
	return prag - HISTEREZIS.get(mod, 6)


def _primulSubFabricant(niveluri, fab):
	for i, (khz, prag) in enumerate(niveluri):
		if khz <= fab:
			return i
	return len(niveluri) - 1


def hotarare(mod, temp, acum, stare, trepte, plafon_fabricant, stare_driver=None):
	"""Hotararea pazei, fara efecte: (plafon_khz, stare_noua, motiv).

	stare e dictionarul intors data trecuta ({} la inceput); cheia „pornit_la” (ceasul monoton la pornirea
	interfetei) o pune cine cheama. motiv e unul din MOTIVE."""
	s = dict(stare or {})
	pl = plafoane(trepte, plafon_fabricant)
	if pl is None:
		s["plafon"], s["motiv"] = None, ""
		return None, s, ""
	if mod not in MODURI:
		mod = IMPLICIT
	fab = pl["fabricant"]
	niveluri = scara(mod, pl)
	valida = temperaturaValida(temp)
	driver_ok = driverNormal(stare_driver)

	mod_nou = s.get("mod") != mod or s.get("scara") != niveluri
	if mod_nou:
		# mod nou (sau alte trepte): se porneste de la treapta potrivita temperaturii de acum
		s["mod"] = mod
		s["scara"] = niveluri
		s["fara_temp_ultima"] = None
		if valida:
			s["nivel"] = _nivelPentru(niveluri, temp)
		elif mod == "performanta":
			# scara sare de sus direct la treapta cea mai mica: fara temperatura treapta ramane sus, iar plafonul il
			# tine fabricantul (candidatul de mai jos)
			s["nivel"], s["fara_temp_ultima"] = 0, acum
		else:
			s["nivel"] = _primulSubFabricant(niveluri, fab)
		s["nivel_caldura"] = valida     # treapta coborata de caldura (nu de lipsa temperaturii)
		s["de_la"] = acum
		s["peste"] = 0
		s["rece_de_la"] = None

	fara_temp = False
	if not valida:
		s["rece_de_la"] = None      # racirea performantei se numara numai pe temperaturi citite
		if s.get("fara_temp_de_la") is None:
			s["fara_temp_de_la"] = acum
		if acum - s["fara_temp_de_la"] >= FARA_TEMP_S:
			fara_temp = True
			if mod == "performanta":
				s["fara_temp_ultima"] = acum    # treapta ramane; plafonul il tine fabricantul (candidatul de mai jos)
			else:
				n = max(s["nivel"], _primulSubFabricant(niveluri, fab))
				if n != s["nivel"]:
					s["nivel"], s["de_la"], s["nivel_caldura"] = n, acum, False
		elif s.get("plafon") is not None and not mod_nou:
			# o citire lipsa sau stricata, scurta: nimic nu se schimba
			return s["plafon"], s, s.get("motiv", "")
	else:
		s["fara_temp_de_la"] = None
		# paza comuna
		if temp >= PAZA_COBORARE:
			s["paza_peste"] = s.get("paza_peste", 0) + 1
			s["paza_rece_de_la"] = None
			if not s.get("paza") and s["paza_peste"] >= CITIRI_COBORARE:
				s["paza"] = True
		else:
			s["paza_peste"] = 0
			if s.get("paza"):
				if temp <= PAZA_URCARE:
					if s.get("paza_rece_de_la") is None:
						s["paza_rece_de_la"] = acum
					if driver_ok and acum - s["paza_rece_de_la"] >= URCARE_DUPA_S:
						s["paza"] = False
						s["paza_rece_de_la"] = None
				else:
					s["paza_rece_de_la"] = None
		# treptele modului: coborare dupa CITIRI_COBORARE citiri, urcare cu o treapta dupa URCARE_DUPA_S; performanta
		# urca numai dupa PERF_RACIRE_S secunde la rand la PERF_URCARE sau sub el (rece_de_la)
		tinta = _nivelPentru(niveluri, temp)
		n = s["nivel"]
		rece = n > 0 and temp <= pragUrcare(mod, niveluri[n][1])
		if not rece:
			s["rece_de_la"] = None
		elif s.get("rece_de_la") is None:
			s["rece_de_la"] = acum
		if tinta > n:
			s["peste"] = s.get("peste", 0) + 1
			if s["peste"] >= CITIRI_COBORARE:
				s["nivel"], s["de_la"], s["peste"], s["nivel_caldura"] = tinta, acum, 0, True
				s["rece_de_la"] = None
		else:
			s["peste"] = 0
			if rece and driver_ok and acum - s["de_la"] >= URCARE_DUPA_S and (
					mod != "performanta" or acum - s["rece_de_la"] >= PERF_RACIRE_S):
				s["nivel"], s["de_la"], s["rece_de_la"] = n - 1, acum, None

	accelerat = niveluri[0][0] > fab
	khz_mod = niveluri[s["nivel"]][0]
	candidati = [(khz_mod, "caldura" if s["nivel"] > 0 and s.get("nivel_caldura", True) else "")]
	if s.get("paza"):
		candidati.append((pl["paza"], "paza"))
	if accelerat and fara_temp:
		candidati.append((fab, "fara_temp"))
	elif accelerat and s.get("fara_temp_ultima") is not None and acum - s["fara_temp_ultima"] < URCARE_DUPA_S:
		candidati.append((fab, ""))     # performanta: temperatura inca necitita sau abia revenita
	pornit_la = s.get("pornit_la")
	if accelerat and pornit_la is not None and acum - pornit_la < PORNIRE_SIGURA_S:
		candidati.append((fab, "pornire_sigura"))
	plafon = min(k for k, m in candidati)
	motiv = sorted((m for k, m in candidati if k == plafon), key=MOTIVE.index)[0]
	if not motiv and not driver_ok:
		motiv = "driver"
	s["plafon"], s["motiv"] = plafon, motiv
	return plafon, s, motiv


def _laRacire(mod, stare, motiv, temp):
	"""Plafonul e jos din cauza caldurii, dar temperatura a coborat deja la pragul de urcare: se asteapta numai cele
	URCARE_DUPA_S secunde (fraza de pe ecran nu mai spune „s-a incalzit” cu temperatura de acum)."""
	if temp is None or not stare:
		return False
	if motiv == "paza":
		return stare.get("paza_rece_de_la") is not None
	if motiv != "caldura":
		return False
	niveluri = stare.get("scara") or []
	n = stare.get("nivel", 0)
	if n <= 0 or n >= len(niveluri) or niveluri[n][1] is None:
		return False
	return temp <= pragUrcare(mod, niveluri[n][1])


# ---------------------------------------------------------------- ce se citeste de pe receptor

def trepteReceptor():
	return parseTrepte(_citeste(CPUFREQ + "/scaling_available_frequencies"))


def disponibil():
	"""cpufreq cu cel putin doua trepte si plafonul scriibil."""
	return len(trepteReceptor()) >= 2 and os.access(cale(CPUFREQ + "/scaling_max_freq"), os.W_OK)


def citestePmCpu():
	for c in PM_CPU:
		text = _citeste(c)
		if text:
			return parsePmCpu(text)
	return parsePmCpu(None)


def citesteTemperatura():
	"""(temperatura °C sau None, dictionarul din pm_cpu). Rezerva: zona termica 0 (alte receptoare)."""
	pm = citestePmCpu()
	t = pm.get("temperatura")
	if t is None:
		for c in TERMICE:
			v = _intreg(_citeste(c, 64), None)
			if v is not None:
				t = int(round(v / 1000.0)) if v > 1000 else v
				break
	return (t if temperaturaValida(t) else None), pm


def areSenzor():
	return citesteTemperatura()[0] is not None


def plafonProbat():
	"""Semnul probei de caldura: treapta cea mai inalta probata, in kHz, sau None (fisierul lipseste sau e stricat)."""
	v = _intreg(_citeste(PROBAT, 64), None)
	return v if v is not None and v > 0 else None


_paza_driver = []


def pazaDriver():
	"""Pragurile pazei driverului (pm_temp), citite o singura data."""
	if not _paza_driver:
		rez = None
		for c in PM_TEMP:
			rez = parsePmTemp(_citeste(c))
			if rez:
				break
		_paza_driver.append(rez)
	return _paza_driver[0]


def textLoad():
	try:
		fisiere = sorted(glob.glob(cale(SCRIPT_LOAD)))
	except Exception:
		fisiere = []
	for f in fisiere:
		try:
			with io.open(f, "r", encoding="utf-8", errors="replace") as h:
				return h.read(65536)
		except (IOError, OSError):
			continue
	return None


def jurnalDisc(text):
	"""Evenimentele rare (caldura, revenirea pe normal, alt program) in JURNAL, cel mult JURNAL_RANDURI randuri."""
	c = cale(JURNAL)
	if not os.path.isdir(os.path.dirname(c)):
		return
	try:
		with io.open(c, "a", encoding="utf-8") as f:
			f.write(u"%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
		if os.path.getsize(c) > JURNAL_TAIERE_OCTETI:
			with io.open(c, "r", encoding="utf-8", errors="replace") as f:
				randuri = f.readlines()[-JURNAL_RANDURI:]
			nou = c + ".nou"
			with io.open(nou, "w", encoding="utf-8") as f:
				f.writelines(randuri)
			os.replace(nou, c)
	except (IOError, OSError) as e:
		_jurnal("jurnalul %s: %s" % (c, e))


# ---------------------------------------------------------------- istoricul pentru grafic

class Istoric(object):
	"""Temperatura, frecventa si modul din fiecare minut: cel mult `minute` minute incheiate (tampon circular de marime
	fixa) si minutul de acum. Minutele se numara pe ceasul monoton de la primul pas (inceput), deci o potrivire a
	ceasului receptorului nu le muta. Scrie firul pazei (adauga, la fiecare pas); citeste firul principal (instantaneu:
	o copie de cel mult minute + 1 randuri, sub zavorul propriu, fara nicio citire de fisier). Minutele incheiate se
	pastreaza in ISTORIC_RAM (text, salveaza/incarca), ca o repornire a interfetei sa nu piarda ora.

	Un minut: [indice, temperatura cea mai mare, suma temperaturilor, cate, suma frecventelor in kHz, cate, caldura,
	modul]."""

	def __init__(self, minute=ISTORIC_MINUTE):
		self.gata = deque(maxlen=minute)
		self.curent = None
		self.inceput = None
		self.esantioane = 0
		self.inchise = 0            # minutele incheiate de la pornire (creste cand se incheie un minut)
		self.zavor = threading.Lock()

	def adauga(self, acum, temp, frecventa_khz=None, caldura=False, mod=None):
		"""O citire a pasului: temperatura (None = necitita), frecventa de acum in kHz, daca plafonul e tinut jos de
		caldura si modul aplicat. O citire cu ceasul mai vechi decat minutul de acum nu se ia in seama; un ceas care
		nu se potriveste cu minutele incarcate (alt ceas monoton) porneste istoricul din nou."""
		with self.zavor:
			if self.inceput is None or acum < self.inceput:
				self.gata.clear()
				self.curent = None
				self.inceput = acum
			i = int((acum - self.inceput) // 60)
			c = self.curent
			if c is not None and i < c[0]:
				return
			if c is None and self.gata and i <= self.gata[-1][0]:
				self.gata.clear()
				self.inceput = acum
				i = 0
			if c is None or i != c[0]:
				if c is not None:
					self.gata.append(tuple(c))
					self.inchise += 1
				c = self.curent = [i, None, 0, 0, 0, 0, False, None]
			if temperaturaValida(temp):
				c[1] = temp if c[1] is None else max(c[1], temp)
				c[2] += temp
				c[3] += 1
			if frecventa_khz and frecventa_khz > 0:
				c[4] += frecventa_khz
				c[5] += 1
			if caldura:
				c[6] = True
			if mod in MODURI:
				c[7] = mod
			self.esantioane += 1

	def instantaneu(self):
		"""(inceput, [minutele, cel mai vechi primul, apoi cel de acum], numarul citirilor)."""
		with self.zavor:
			minute = list(self.gata)
			if self.curent is not None:
				minute.append(tuple(self.curent))
			return self.inceput, minute, self.esantioane

	def semnatura(self):
		"""Ce se vede din istoric pe grafic: se schimba la un minut nou si cand minutul de acum isi schimba cea mai mare
		temperatura, media (rotunjita la 1 °C), frecventa medie (rotunjita la 100 MHz), caldura sau modul. Intre doua
		schimbari graficul nu se redeseneaza (axa timpului se muta cu cel mult un minut)."""
		with self.zavor:
			c = self.curent
			if c is None:
				return (self.inceput, len(self.gata))
			tmed = int(round(float(c[2]) / c[3])) if c[3] else None
			fmed = int(round(float(c[4]) / c[5] / 100000.0)) if c[5] else None
			return (self.inceput, c[0], c[1], tmed, fmed, c[6], c[7])

	def textSalvare(self, boot_id):
		"""Minutele incheiate ca text pentru ISTORIC_RAM (None fara nimic de pastrat)."""
		with self.zavor:
			if self.inceput is None or not self.gata:
				return None
			randuri = ["boot_id=%s" % boot_id, "inceput=%.3f" % self.inceput]
			for r in self.gata:
				randuri.append("%d %s %d %d %d %d %d %s" % (r[0], "-" if r[1] is None else "%d" % r[1], r[2], r[3], r[4],
					r[5], 1 if r[6] else 0, r[7] or "-"))
			return "\n".join(randuri) + "\n"

	def incarca(self, text, boot_id):
		"""Minutele din ISTORIC_RAM, numai daca sunt din aceeasi pornire a receptorului (boot_id); un fisier stricat
		sau din alta pornire lasa istoricul gol. Intoarce cate minute s-au incarcat."""
		if not text or not boot_id:
			return 0
		randuri = text.splitlines()
		if len(randuri) < 3 or randuri[0] != "boot_id=%s" % boot_id or not randuri[1].startswith("inceput="):
			return 0
		try:
			inceput = float(randuri[1].partition("=")[2])
			minute = []
			for rand in randuri[2:]:
				p = rand.split()
				if len(p) != 8:
					raise ValueError(rand)
				tmax = None if p[1] == "-" else int(p[1])
				minute.append((int(p[0]), tmax, int(p[2]), int(p[3]), int(p[4]), int(p[5]), p[6] == "1",
					p[7] if p[7] in MODURI else None))
		except ValueError:
			return 0
		indici = [m[0] for m in minute]
		if indici != sorted(set(indici)) or (indici and indici[0] < 0):
			return 0
		with self.zavor:
			self.gata.clear()
			self.gata.extend(minute[-self.gata.maxlen:])
			self.curent = None
			self.inceput = inceput
			return len(self.gata)


# ---------------------------------------------------------------- paza (firul) si aplicarea

class Procesor(object):
	"""Starea pazei si scrierea plafonului. Un singur obiect pe proces (procesor())."""

	def __init__(self, ceas=None):
		self.ceas = ceas or monotonic
		self.mod = IMPLICIT
		self.stare = {}
		self.trepte = []                # toate treptele receptorului (si pentru timpul pe trepte)
		self.trepte_folosite = []       # treptele pazei: peste plafonul fabricantului numai cele probate (PROBAT)
		self.probat = None
		self.fabricant = None           # plafonul fabricantului, in kHz (inainte de potrivirea pe trepte)
		self.racire = False             # plafonul sta jos dupa caldura, dar temperatura e deja sub pragul de urcare
		self.scris = None               # ultima valoare scrisa de acest proces
		self.atins = False              # s-a scris ceva in aceasta pornire a receptorului (FABRICANT_RAM)
		self.mesaj_la = None            # ceasul ultimului mesaj „s-a incalzit” (si in FABRICANT_RAM)
		self.in_caldura = False         # ultima scriere a fost de caldura (paza comuna sau treapta performantei)
		self.racire_de_anuntat = False  # s-a aratat „s-a incalzit”: la revenire se arata si „s-a racit”
		self.racit_la = None            # ceasul revenirii plafonului dupa caldura (fraza „s-a racit”)
		self.altcineva_pana = 0.0
		self.reia = False
		self.plafon_hotarat = None
		self.motiv = ""
		self.temperatura = None
		self.frecventa = None           # frecventa de acum a ultimului pas, in kHz (pentru istoric)
		self.stat = None                # /proc/stat la ultimul pas (total, inactiv)
		self.folosit = None             # procesorul folosit intre ultimii doi pasi, in %
		self.folosit_la = None          # ceasul pasului care l-a masurat
		self.istoric = Istoric()
		self.istoric_salvat = 0         # minutele incheiate scrise ultima data in ISTORIC_RAM
		self.boot_id = ""
		self.proba_numar = 0
		self.proba_scrisa = False
		self.eroare_scriere = False
		self.altcineva_de = 0
		self.ultim_motiv_scris = ""
		self.randuri_disc = 0
		self.mesaje = deque()
		self.zavor = threading.RLock()
		self.gata = threading.Event()
		self.fir = None
		self.pornit = False

	# ---- pregatirea ----

	def fabricantTreapta(self):
		pl = plafoane(self.trepte, self.fabricant)
		return pl["fabricant"] if pl else None

	def pregateste(self):
		"""O data la pornirea interfetei: treptele, plafonul fabricantului, semnele din RAM si boot_id."""
		self.trepte = trepteReceptor()
		ram = citesteCheiValori(FABRICANT_RAM)
		cpuinfo = _intreg(_citeste(CPUFREQ + "/cpuinfo_max_freq"), None)
		if ram is None:
			fab_ram = _intreg(_citeste(CPUFREQ + "/scaling_max_freq"), None)
			self.atins = False
			self.mesaj_la = None
			self._fabricant_ram = fab_ram
			self._scrieRam()
		else:
			fab_ram = _intreg(ram.get("fabricant"), None)
			self._fabricant_ram = fab_ram
			self.atins = ram.get("atins") == "1"
			self.mesaj_la = _intreg(ram.get("mesaj_la"), None)
		self.fabricant = plafonDinLoad(textLoad()) or fab_ram or cpuinfo or (max(self.trepte) if self.trepte else None)
		self.probat = plafonProbat()
		self.trepte_folosite = trepteFolosite(self.trepte, self.fabricant, self.probat)
		self.boot_id = (_citeste(BOOT_ID, 128) or "").strip()
		# ora graficului de dinainte de o repornire a interfetei (aceeasi pornire a receptorului)
		self.istoric.incarca(_citeste(ISTORIC_RAM, 16384), self.boot_id)
		self.istoric_salvat = self.istoric.inchise

	def _salveazaIstoric(self):
		"""Din firul pazei, la fiecare minut incheiat: minutele in ISTORIC_RAM (tmpfs, cativa KB)."""
		if self.istoric.inchise == self.istoric_salvat or not self.boot_id:
			return
		self.istoric_salvat = self.istoric.inchise
		text = self.istoric.textSalvare(self.boot_id)
		if text:
			_scrieAtomic(ISTORIC_RAM, text)

	def _scrieRam(self):
		_scrieAtomic(FABRICANT_RAM, textCheiValori({
			"fabricant": getattr(self, "_fabricant_ram", None) or "",
			"atins": "1" if self.atins else "0",
			"mesaj_la": "" if self.mesaj_la is None else "%d" % self.mesaj_la,
		}))

	def verificaProba(self):
		"""La pornire: True daca pornirile receptorului cu procesorul accelerat s-au incheiat necurat de
		OPRIRI_NECURATE ori la rand (atunci modul trebuie sa treaca pe normal). Aceeasi boot_id = enigma2 a cazut in
		aceeasi pornire a receptorului: nu se numara aici."""
		d = citesteCheiValori(PROBA)
		self.proba_numar = 0
		self.proba_scrisa = False
		if d is None:
			return False
		numar = _intreg(d.get("numar"), 0)
		boot_vechi = d.get("boot_id", "")
		if boot_vechi and self.boot_id and boot_vechi == self.boot_id:
			self.proba_numar = numar
			self.proba_scrisa = True
			return False
		if boot_vechi and self.boot_id:
			numar += 1
		if numar >= OPRIRI_NECURATE:
			_sterge(PROBA)
			return True
		self.proba_numar = numar
		return False

	def _scrieProba(self):
		if self.proba_scrisa or not self.boot_id:
			return
		if _scrieAtomic(PROBA, textCheiValori({"boot_id": self.boot_id, "numar": self.proba_numar})):
			self.proba_scrisa = True

	# ---- pasul pazei ----

	def pas(self, acum=None):
		"""Un pas: citeste, hotaraste, scrie numai la schimbare, apoi pune citirea in istoric (si minutele incheiate in
		ISTORIC_RAM). Nu arunca niciodata."""
		with self.zavor:
			try:
				acum = self.ceas() if acum is None else acum
				self._pas(acum)
				self.istoric.adauga(acum, self.temperatura, self.frecventa, self.motiv in MOTIVE_CALDURA, self.mod)
				self._salveazaIstoric()
			except Exception as e:
				_jurnal("pasul pazei: %r" % (e,))
			try:
				self._folosit(acum)
			except Exception as e:
				_jurnal("procesorul folosit: %r" % (e,))

	def _folosit(self, acum):
		"""Procesorul folosit intre doi pasi (PERIOADA_S): caseta "Incarcare CPU" deschisa abia acum il arata de la prima
		afisare, pana are propria diferenta (Converter/HdsCommon.cpu_load). O citire mica din /proc/stat pe pas."""
		stat = parseStat(_citeste(STAT, 2048))
		if stat is None:
			return
		if self.stat is not None:
			v = procentFolosit(self.stat, stat)
			if v is not None:
				self.folosit, self.folosit_la = v, (self.ceas() if acum is None else acum)
		self.stat = stat

	def _pas(self, acum):
		temp, pm = citesteTemperatura()
		self.temperatura = temp
		# frecventa de acum: din pm_cpu (aceeasi citire); scaling_cur_freq numai pe receptoarele fara pm_cpu
		self.frecventa = pm.get("frecventa_khz") or _intreg(_citeste(CPUFREQ + "/scaling_cur_freq", 64), None)
		plafon, self.stare, motiv = hotarare(self.mod, temp, acum, self.stare, self.trepte_folosite, self.fabricant,
			pm.get("stare_driver"))
		self.plafon_hotarat = plafon
		self.racire = _laRacire(self.mod, self.stare, motiv, temp)
		if plafon is None:
			self.motiv = motiv
			return
		actual = _intreg(_citeste(CPUFREQ + "/scaling_max_freq", 64), None)
		neatins = self.mod == IMPLICIT and not self.atins
		if actual is None:
			pass    # plafonul nu se poate citi: nu se scrie orbeste
		elif actual == plafon:
			self.reia = False
			self.altcineva_pana = 0.0
			if not neatins:
				self.scris = plafon
			# plafonul e deja cel hotarat (ramas de la un proces enigma2 cazut sau pus de alt program): intervalul de
			# caldura se deschide sau se inchide ca dupa o scriere (_mesaje nu face nimic daca nu s-a schimbat nimic)
			self._mesaje(motiv, temp, acum)
		elif acum < self.altcineva_pana and not (motiv == "paza" and actual > plafon):
			motiv = "altcineva"   # pauza; numai paza comuna (coborarea la caldura mare) trece peste ea
		elif self.scris is not None and actual != self.scris and not self.reia and motiv != "paza":
			self.altcineva_pana = acum + ALTCINEVA_S
			self.reia = True
			motiv = "altcineva"
			self._altcineva(actual)
		else:
			self.reia = False
			if not (neatins and plafon == self.fabricantTreapta()):
				# normal si neatins in aceasta pornire a receptorului: nu se scrie nimic
				self._scrie(plafon, actual, motiv, temp, acum)
		self.motiv = motiv

	def _altcineva(self, actual):
		self.altcineva_de += 1
		_jurnal("plafonul e %d kHz, nu %d kHz cat am scris: nu il rescriu %d s" % (actual, self.scris, ALTCINEVA_S))
		if self.altcineva_de <= 3:
			jurnalDisc("plafon schimbat de alt program: %d kHz (scris %d kHz); pauza %d s" % (
				actual, self.scris, ALTCINEVA_S))

	def _scrie(self, khz, actual, motiv, temp, acum=0.0):
		try:
			with io.open(cale(CPUFREQ + "/scaling_max_freq"), "w") as f:
				f.write(u"%d" % khz)
		except (IOError, OSError) as e:
			if not self.eroare_scriere:
				_jurnal("nu pot scrie plafonul %d kHz: %s" % (khz, e))
			self.eroare_scriere = True
			return False
		self.eroare_scriere = False
		self.scris = khz
		if not self.atins:
			self.atins = True
			self._scrieRam()
		fab = self.fabricantTreapta()
		if fab is not None and khz > fab and self.mod in MODURI_ACCELERATE:
			self._scrieProba()
		text = "plafon %s -> %d MHz (%s, %s, %s)" % ("?" if actual is None else "%d" % (actual // 1000), khz // 1000,
			self.mod, "fara temperatura" if temp is None else "%d C" % temp, motiv or "-")
		_jurnal(text)
		# pe disc numai evenimentele de caldura (intrarea si iesirea), nu scara obisnuita a modului Automat
		de_notat = ("paza", "fara_temp") if self.mod != "performanta" else ("paza", "fara_temp", "caldura")
		if (motiv in de_notat or self.ultim_motiv_scris in de_notat) and self.randuri_disc < JURNAL_PE_PORNIRE:
			self.randuri_disc += 1
			jurnalDisc(text)
		self.ultim_motiv_scris = motiv
		self._mesaje(motiv, temp, acum)
		return True

	def _mesaje(self, motiv, temp, acum):
		"""Dupa o scriere a plafonului: „s-a incalzit” la intrarea in caldura (paza comuna sau treapta performantei),
		cel mult o data la MESAJ_PAUZA_S; „s-a racit” la revenire (motiv gol), numai dupa un „s-a incalzit” aratat.
		Celelalte motive (fara temperatura, caldura automatului) nu deschid si nu inchid intervalul de caldura."""
		if motiv == "paza" or (motiv == "caldura" and self.mod == "performanta"):
			if self.in_caldura:
				return
			self.in_caldura = True
			self.racit_la = None
			if self.mesaj_la is None or acum - self.mesaj_la >= MESAJ_PAUZA_S:
				self.mesaj_la = acum
				self.racire_de_anuntat = True
				self._scrieRam()
				self.mesaje.append(textMotiv(motiv, temp))
		elif not motiv and self.in_caldura:
			self.in_caldura = False
			self.racit_la = acum
			if self.racire_de_anuntat:
				self.racire_de_anuntat = False
				self.mesaje.append(textRacit())

	def schimbaMod(self, mod):
		"""Modul nou, aplicat pe loc (firul principal); o alegere a omului ridica pauza „alt program”. Un mod care nu
		accelereaza sterge PROBA: o oprire necurata de acum nu mai e „cu procesorul accelerat”."""
		if mod not in MODURI:
			mod = IMPLICIT
		with self.zavor:
			if mod == self.mod:
				return
			_jurnal("modul %s -> %s" % (self.mod, mod))
			self.mod = mod
			self.altcineva_pana = 0.0
			self.reia = True
			# alt mod: o revenire a plafonului de acum nu mai inseamna „s-a racit”
			self.in_caldura = False
			self.racire_de_anuntat = False
			self.racit_la = None
			if mod not in MODURI_ACCELERATE:
				# si semnul ramas de la o pornire trecuta: sirul pornirilor accelerate s-a rupt
				_sterge(PROBA)
				self.proba_scrisa = False
			if self.pornit:
				try:
					self._pas(self.ceas())
				except Exception as e:
					_jurnal("aplicarea modului: %r" % (e,))

	# ---- firul ----

	def porneste(self):
		if self.fir is not None:
			return
		self.stare["pornit_la"] = self.ceas()
		self.gata.clear()
		self.pornit = True
		fir = threading.Thread(target=self._bucla, name="hds-procesor")
		fir.daemon = True
		self.fir = fir
		fir.start()

	def _bucla(self):
		self.pas()
		while not self.gata.wait(PERIOADA_S):
			self.pas()

	def opreste(self, asteptare_s=3.0):
		self.gata.set()
		fir, self.fir = self.fir, None
		if fir is not None and fir is not threading.current_thread():
			fir.join(asteptare_s)

	def laOprire(self):
		"""Iesirea curata a enigma2: firul se opreste, plafonul fabricantului se pune la loc (numai daca s-a scris
		ceva in aceasta pornire a receptorului), fisierul de proba se sterge."""
		self.opreste()
		with self.zavor:
			self.pornit = False
			if self.atins:
				fab = self.fabricantTreapta()
				actual = _intreg(_citeste(CPUFREQ + "/scaling_max_freq", 64), None)
				reusit = True
				if fab is not None and actual != fab:
					try:
						with io.open(cale(CPUFREQ + "/scaling_max_freq"), "w") as f:
							f.write(u"%d" % fab)
						_jurnal("la oprire: plafonul fabricantului pus la loc (%d MHz)" % (fab // 1000))
					except (IOError, OSError) as e:
						reusit = False
						_jurnal("la oprire: nu pot pune plafonul fabricantului: %s" % e)
				if reusit:
					self.atins = False
					self.scris = None
					self._scrieRam()
			_sterge(PROBA)
			self.proba_scrisa = False


_unic = [None]


def procesor():
	if _unic[0] is None:
		_unic[0] = Procesor()
	return _unic[0]


# ---------------------------------------------------------------- textele

def numeMod(mod, scurt=False):
	return _((NUME_SCURT if scurt else NUME).get(mod, NUME[IMPLICIT]))


def _mhz(khz):
	return int(khz) // 1000


DESCRIERI = {
	"automat": N_("Receptorul alege singur: lucrează repede cât e răcoros și încetinește când se încălzește."),
	"racoros": N_("Procesorul lucrează mai încet, deci receptorul se încălzește mai puțin când are mult de lucru. "
		"Meniurile și schimbarea canalelor pot fi puțin mai lente."),
	"normal": N_("Procesorul lucrează cât l-a reglat fabricantul. Recomandat dacă nu știi ce să alegi."),
	# %d: PERF_COBORARE, apoi PERF_URCARE
	"performanta": N_("Procesorul lucrează cât poate de repede. Când receptorul ajunge la %d °C, procesorul merge "
		"încet până se răcește la %d °C."),
}


def _format(text, original, valori):
	"""text % valori; o traducere cu alte semne de formatare nu arunca: se foloseste textul original."""
	try:
		return text % valori
	except (TypeError, ValueError):
		return original % valori


def descriereMod(mod):
	if mod not in DESCRIERI:
		return ""
	if mod == "performanta":
		return _format(_(DESCRIERI[mod]), DESCRIERI[mod], (PERF_COBORARE, PERF_URCARE))
	return _(DESCRIERI[mod])


def _treptePlafon():
	"""(toate treptele, treptele folosite de paza, plafonul fabricantului): din paza daca e pregatita, altfel citite."""
	p = procesor()
	trepte = p.trepte or trepteReceptor()
	fab = p.fabricant or _plafonFabricantCitit()
	folosite = p.trepte_folosite if (p.trepte and p.trepte_folosite) else trepteFolosite(trepte, fab, plafonProbat())
	return trepte, folosite, fab


def detaliuMod(mod, pl=None):
	"""Randul tehnic, mai mic: plafoanele si pragurile modului, din treptele folosite."""
	if pl is None:
		trepte, folosite, fab = _treptePlafon()
		pl = plafoane(folosite, fab)
	if not pl:
		return ""
	n = scara(mod, pl)
	if mod == "automat":
		if len(n) >= 3:
			return _("Cel mult %d MHz sub %d °C, apoi %d MHz și %d MHz.") % (_mhz(n[0][0]), n[1][1], _mhz(n[1][0]),
				_mhz(n[2][0]))
		if len(n) == 2:
			return _("Cel mult %d MHz sub %d °C, apoi %d MHz.") % (_mhz(n[0][0]), n[1][1], _mhz(n[1][0]))
		return _("Cel mult %d MHz.") % _mhz(n[0][0])
	if mod == "racoros":
		trepte = procesor().trepte or trepteReceptor() or [n[0][0]]
		text = _("Cel mult %d MHz. De obicei procesorul stă oricum pe %d MHz.")
		return text % (_mhz(n[0][0]), _mhz(min(trepte)))
	if mod == "performanta" and len(n) >= 2:
		text = N_("Cel mult %d MHz. De la %d °C: %d MHz, până stă %s la cel mult %d °C.")
		return _format(_(text), text, (_mhz(n[0][0]), n[1][1], _mhz(n[1][0]), textDurata(PERF_RACIRE_S), PERF_URCARE))
	return _("Cel mult %d MHz.") % _mhz(n[0][0])


RACIRE_TEMP = N_("Receptorul se răcește (%d °C). Procesorul revine la viteza obișnuită după %s.")
RACIRE = N_("Receptorul se răcește. Procesorul revine la viteza obișnuită după %s.")


def _asteptareRacire(motiv, mod=None):
	"""Cat sta plafonul jos dupa ce temperatura a coborat la pragul de urcare: paza comuna si treptele automatului
	URCARE_DUPA_S, performanta PERF_RACIRE_S la rand (si cel putin URCARE_DUPA_S de la coborare)."""
	if motiv == "caldura" and mod == "performanta":
		return max(PERF_RACIRE_S, URCARE_DUPA_S)
	return URCARE_DUPA_S


def textMotiv(motiv, temp=None, racire=False, mod=None):
	"""Fraza pentru ecran si web despre ce tine plafonul acum (gol cand nu e nimic de spus). racire: temperatura a
	coborat deja sub pragul de urcare, iar plafonul asteapta numai minutul de dupa racire (mod: modul aplicat, pentru
	cat asteapta). La caldura fraza spune si ca imaginea si sunetul merg (decodarea e in hardware)."""
	if motiv in ("paza", "caldura"):
		if racire:
			durata = textDurata(_asteptareRacire(motiv, mod))
			if temp is None:
				return _format(_(RACIRE), RACIRE, (durata,))
			return _format(_(RACIRE_TEMP), RACIRE_TEMP, (temp, durata))
		if temp is None:
			text = _("Receptorul s-a încălzit. Procesorul lucrează mai încet până se răcește.")
		else:
			cald = N_("Receptorul s-a încălzit (%d °C). Procesorul lucrează mai încet până se răcește.")
			text = _format(_(cald), cald, (temp,))
		return text + " " + _("Imaginea și sunetul nu sunt afectate.")
	if motiv == "fara_temp":
		return _("Temperatura nu se poate citi acum. Din siguranță, procesorul lucrează ca la fabricant.")
	if motiv == "pornire_sigura":
		return _("În primele 3 minute după pornire procesorul lucrează ca la fabricant.")
	if motiv == "altcineva":
		return _("Frecvența maximă a fost schimbată de alt program. O lăsăm așa câteva minute.")
	if motiv == "driver":
		return _("Receptorul s-a încălzit și își încetinește singur procesorul.")
	return ""


def textRacit():
	"""Dupa revenirea plafonului: mesajul pe ecran si fraza din ecranul „Procesor” si din web (RACIT_ARATAT_S)."""
	return _("Receptorul s-a răcit. Procesorul lucrează din nou la viteza obișnuită.")


def textIndisponibil():
	return _("Pe acest receptor frecvența procesorului nu se poate citi sau schimba.")


def textRevenireNormal():
	return _("Receptorul s-a oprit neașteptat de două ori cu procesorul accelerat. Am trecut înapoi pe modul Normal.")


def textPazaDriver(pd=None):
	pd = pazaDriver() if pd is None else pd
	if not pd or not pd.get("pornita"):
		return ""
	return _("Receptorul se apără singur de căldură: încetinește la %d °C.") % pd["coborare"]


# %s: numele scurt al modului Performanta, %d: treapta cea mai inalta a procesorului, in MHz
PERFORMANTA_ASCUNSA = N_("Modul %s (%d MHz) apare după ce receptorul trece proba de căldură.")


def textPerformantaAscunsa():
	"""Fara semnul probei de caldura Performanta nu se ofera: fraza spune ca modul exista si cand apare (receptorul are o
	treapta peste plafonul fabricantului, dar nu e probata). Gol cu treapta probata sau fara treapta peste fabricant."""
	try:
		trepte, folosite, fab = _treptePlafon()
		toate = plafoane(trepte, fab)
		pl = plafoane(folosite, fab)
	except Exception:
		return ""
	if not toate or not pl or toate["sus"] <= toate["fabricant"] or pl["sus"] > pl["fabricant"]:
		return ""
	return _format(_(PERFORMANTA_ASCUNSA), PERFORMANTA_ASCUNSA, (numeMod("performanta", scurt=True), _mhz(toate["sus"])))


def textNotaEcran(pd=None, disp=True):
	"""Nota gri din ecranul „Procesor” (sub citiri, cand nu e nimic de spus despre plafon): paza driverului si, fara
	semnul probei, cand apare Performanta."""
	parti = [textPazaDriver(pd)]
	if disp:
		parti.append(textPerformantaAscunsa())
	return " ".join(x for x in parti if x)


def textNotaIncarcare():
	return _("Numărul mare nu înseamnă procesor ocupat: include firele driverelor care așteaptă.")


def _plafonFabricantCitit():
	return plafonDinLoad(textLoad()) or _intreg(_citeste(CPUFREQ + "/cpuinfo_max_freq"), None)


# ---------------------------------------------------------------- modurile si setarea

def _moduriPosibile(cu_senzor=True):
	"""Ce moduri au sens acum pe receptor: Automat si Performanta cer senzorul de temperatura, Performanta si o treapta
	folosita peste plafonul fabricantului (semnul probei), Automat macar doua trepte in scara, Racoros o treapta sub
	plafonul fabricantului. cu_senzor=False: fara citirea senzorului (cand „disponibil” vine din alegerile setarii)."""
	trepte, folosite, fab = _treptePlafon()
	disp = len(trepte) >= 2 and disponibil()
	pl = plafoane(folosite, fab) if disp else None
	senzor = disp and cu_senzor and areSenzor()
	rez = []
	for mod in MODURI:
		if not disp:
			poate = mod == IMPLICIT
		elif mod == "racoros":
			poate = pl["racoros"] < pl["fabricant"]
		elif mod == "performanta":
			poate = senzor and pl["sus"] > pl["fabricant"]
		elif mod == "automat":
			poate = senzor and len(scara("automat", pl)) >= 2
		else:
			poate = True
		rez.append({"id": mod, "nume": numeMod(mod), "descriere": descriereMod(mod),
			"detaliu": detaliuMod(mod, pl) if pl else "", "disponibil": bool(poate)})
	return rez


def _alegeriSetare():
	"""Id-urile alegerilor lui config.hds_procesor.mod (fixate la pornirea interfetei), sau None fara setare."""
	try:
		from Components.config import config
		if "hds_procesor" not in config.content.items:
			return None
		return [x[0] if isinstance(x, tuple) else x for x in config.hds_procesor.mod.choices.choices]
	except Exception:
		return None


def moduri():
	"""[{id, nume, descriere, detaliu, disponibil}] in ordinea din MODURI. Dupa initConfig, „disponibil” inseamna
	„printre alegerile setarii”: televizorul, pagina web si seteazaMod ofera exact aceleasi moduri."""
	alese = _alegeriSetare()
	rez = _moduriPosibile(cu_senzor=alese is None)
	if alese is not None:
		for m in rez:
			m["disponibil"] = m["id"] in alese
	return rez


def alegeriMod():
	"""Alegerile pentru config.hds_procesor.mod: numai modurile care au sens pe acest receptor (texte netraduse,
	ConfigSelection le traduce la afisare)."""
	return [(m["id"], NUME[m["id"]]) for m in _moduriPosibile() if m["disponibil"]]


def _laSchimbareMod(element):
	"""Notificarea setarii: se aplica numai dupa salvare sau renuntare (valoarea egala cu cea salvata), nu la fiecare
	apasare stanga/dreapta din ecran."""
	try:
		if element.isChanged():
			return
		p = procesor()
		if p.pornit:
			p.schimbaMod(element.value)
		else:
			p.mod = element.value if element.value in MODURI else IMPLICIT
	except Exception as e:
		_jurnal("aplicarea modului: %r" % (e,))


_clasa = []


def _clasaSetare():
	"""ConfigModProcesor, facuta la prima chemare (fisierul nu importa config.py la incarcare)."""
	if _clasa:
		return _clasa[0]
	from Components.config import ConfigSelection

	class ConfigModProcesor(ConfigSelection):
		"""ConfigSelection care nu pierde modul salvat cand el lipseste din alegerile acestei porniri (senzorul nu s-a
		citit, semnul probei lipseste): randul arata modul implicit (rezerva), iar save() pastreaza valoarea salvata
		cat timp nimeni n-a ales altceva (ecranul „Personalizare” salveaza toate randurile). In starea asta
		isChanged() e fals, altfel „Personalizare” ar intreba la iesire de salvare fara nicio schimbare. „ales” il pune
		seteazaMod: alegerea omului pe ecranul „Procesor” sau in web se scrie mereu."""
		ales = False

		def _rezerva(self):
			sv = self.saved_value
			return sv is not None and sv not in self.choices and self.value == self.default and not self.ales

		def save(self):
			if self._rezerva():
				if self.callNotifiersOnSaveAndCancel:
					self.changed()
				return
			self.ales = False
			ConfigSelection.save(self)

		def isChanged(self):
			if self._rezerva():
				return False
			return ConfigSelection.isChanged(self)

	_clasa.append(ConfigModProcesor)
	return ConfigModProcesor


def initConfig():
	"""config.hds_procesor.mod si SystemInfo["HdsProcesor"] (randul din setup.xml si intrarea din meniu)."""
	from Components.config import config
	if "hds_procesor" in config.content.items:
		return
	from Components.config import ConfigSubsection
	config.hds_procesor = ConfigSubsection()
	config.hds_procesor.mod = _clasaSetare()(default=IMPLICIT, choices=alegeriMod())
	element = config.hds_procesor.mod
	element.callNotifiersOnSaveAndCancel = True
	element.addNotifier(_laSchimbareMod, initial_call=False)
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsProcesor"] = disponibil()
	except Exception as e:
		_jurnal("SystemInfo: %r" % (e,))


def _salveazaAles(element, mod):
	"""Alegerea omului: valoarea se salveaza si peste modul pastrat de rezerva."""
	element.value = mod
	element.ales = True
	element.save()


def seteazaMod(mod):
	"""Pentru ecran si web: salveaza modul si il aplica pe loc. Intoarce (reusit, mesaj). Numai alegerile setarii (ca
	televizorul); fara nicio schimbare nu se rescrie fisierul de setari (eMMC)."""
	initConfig()
	from Components.config import config, configfile
	element = config.hds_procesor.mod
	if not disponibil():
		return False, textIndisponibil()
	if mod not in (_alegeriSetare() or []):
		return False, _("Modul ales nu există pe acest receptor.")
	asteptat = None if mod == element.default else mod
	if element.value == mod and element.saved_value == asteptat:
		_laSchimbareMod(element)        # paza la zi; nimic de scris
		return True, _("Salvat. Modul se aplică pe loc.")
	_salveazaAles(element, mod)
	if element.value != mod:
		element.cancel()
		return False, _("Modul ales nu există pe acest receptor.")
	configfile.save()
	_citire["d"] = None     # raspunsul web si ecranul arata imediat plafonul noului mod, nu citirea memorata
	return True, _("Salvat. Modul se aplică pe loc.")


# ---------------------------------------------------------------- citirile pentru ecran, web, bara si Informatii

_citire = {"t": None, "d": None, "stat": None}
_zavor_citire = threading.Lock()


def folositRecent(max_varsta=15.0):
	"""(procent, varsta in secunde): procesorul folosit intre ultimii doi pasi ai pazei, sau None (paza oprita, inca
	fara doi pasi, ori pasul mai vechi de max_varsta). Fara citiri noi: numai ce a masurat firul pazei."""
	p = _unic[0]
	if p is None or not p.pornit or p.folosit is None or p.folosit_la is None:
		return None
	varsta = p.ceas() - p.folosit_la
	if not 0.0 <= varsta <= max_varsta:
		return None
	return p.folosit, varsta


def citire(max_varsta=1.0):
	"""O citire pentru ecran, web si bara; oricati o cer, se face cel mult o data la max_varsta secunde."""
	acum = monotonic()
	with _zavor_citire:
		if _citire["d"] is not None and acum - _citire["t"] < max_varsta:
			return _citire["d"]
		stat = parseStat(_citeste(STAT, 2048))
		d = citireNoua(_citire["stat"], stat)
		_citire.update({"t": acum, "d": d, "stat": stat})
		return d


def citireNoua(stat_inainte=None, stat_acum=None):
	p = procesor()
	trepte, folosite, fab = _treptePlafon()
	disp = len(trepte) >= 2 and disponibil()
	temp, pm = citesteTemperatura()
	cur = _intreg(_citeste(CPUFREQ + "/scaling_cur_freq", 64), None) or pm.get("frecventa_khz")
	maxim = _intreg(_citeste(CPUFREQ + "/scaling_max_freq", 64), None)
	pl = plafoane(folosite, fab) if folosite else None
	# intre doua citiri; daca intre ele nu s-a numarat nimic (citiri prea apropiate), de la pornire
	folosit = procentFolosit(stat_inainte, stat_acum)
	if folosit is None:
		folosit = procentFolosit(None, stat_acum)
	return {
		"disponibil": disp,
		"mod": p.mod,
		"plafon_mod_khz": scara(p.mod, pl)[0][0] if pl else None,
		"plafon_fabricant_khz": pl["fabricant"] if pl else None,
		"plafon_khz": maxim,
		"plafon_hotarat_khz": p.plafon_hotarat,
		"motiv": p.motiv if p.pornit else "",
		"racire": bool(p.racire) if p.pornit else False,
		"racit": _racitDeCurand(p),
		"frecventa_khz": cur,
		"temperatura": temp,
		"tensiune_mv": pm.get("tensiune_mv"),
		"stare_driver": pm.get("stare_driver"),
		"trepte": parseTimeInState(_citeste(CPUFREQ + "/stats/time_in_state", 4096)),
		"folosit_procent": folosit,
		"paza_driver": pazaDriver(),
		"paza_ruleaza": p.pornit,
	}


def _racitDeCurand(p):
	"""Plafonul a revenit dupa caldura acum cel mult RACIT_ARATAT_S secunde, e pe treapta de sus a modului si nimic
	altceva nu-l tine jos (dupa pierderea senzorului, performanta sta un minut pe plafonul fabricantului fara motiv:
	atunci nu se spune ca lucreaza din nou la viteza obisnuita)."""
	if not p.pornit or p.motiv or p.racit_la is None:
		return False
	try:
		pl = plafoane(p.trepte_folosite, p.fabricant)
		if pl and p.plafon_hotarat is not None and p.plafon_hotarat < scara(p.mod, pl)[0][0]:
			return False
		return p.ceas() - p.racit_la < RACIT_ARATAT_S
	except Exception:
		return False


SETATA_CALD = N_("cel mult %d MHz (%s, s-a încălzit)")


def textFrecventaSetata(d, cu_motiv=False):
	"""„cel mult 1600 MHz (Performanță)”; cu_motiv („Informații”, afisajul tehnic): cand plafonul e tinut jos de
	caldura, „cel mult 400 MHz (Performanță, s-a încălzit)”."""
	if d.get("plafon_khz"):
		valori = (_mhz(d["plafon_khz"]), numeMod(d.get("mod"), scurt=True))
		if cu_motiv and d.get("motiv") in ("paza", "caldura"):
			return _format(_(SETATA_CALD), SETATA_CALD, valori)
		return _("cel mult %d MHz (%s)") % valori
	return numeMod(d.get("mod"), scurt=True)


def textFrecventaSetataScurt(d):
	"""Pe ecranul „Procesor”, unde modul e pe randul de sus: „cel mult 1600 MHz”."""
	if d.get("plafon_khz"):
		return _("cel mult %d MHz") % _mhz(d["plafon_khz"])
	return _("nu se poate citi")


def textMotivCitire(d):
	"""Fraza motivului pentru o citire (ecran, web): gol pe un receptor fara cpufreq; dupa revenirea plafonului,
	RACIT_ARATAT_S secunde, „s-a racit”."""
	if not d.get("disponibil"):
		return ""
	text = textMotiv(d.get("motiv"), d.get("temperatura"), d.get("racire", False), d.get("mod"))
	if not text and d.get("racit"):
		return textRacit()
	return text


def racitCitire(d):
	"""Fraza citirii e „s-a racit” (vestea buna: pe ecran si in web cu alta culoare decat avertismentele)."""
	return bool(d.get("disponibil") and d.get("racit")
		and not textMotiv(d.get("motiv"), d.get("temperatura"), d.get("racire", False), d.get("mod")))


# unitatile (MHz, °C, mV) sunt aceleasi in toate limbile: numai „nu se poate citi” se traduce

def textFrecventa(khz):
	return "%d MHz" % _mhz(khz) if khz else _("nu se poate citi")


def textTemperatura(t):
	return u"%d °C" % t if t is not None else _("nu se poate citi")


def textTensiune(mv):
	return "%d mV" % mv if mv else _("nu se poate citi")


def textDurata(secunde):
	"""Cat timp: „45 s”, „32 min”, „5 h 29 min” (formele exista deja in traducerile imaginii)."""
	s = max(0, int(secunde or 0))
	if s < 60:
		return _("%d s") % s
	m = s // 60
	if m < 60:
		return _("%d min") % m
	return _("%d h %d min") % (m // 60, m % 60)


def trepteProcent(d):
	"""Timpul pe fiecare treapta de la pornire: [(khz, procent, secunde)]; gol fara cpufreq sau fara timp numarat."""
	trepte = (d.get("trepte") or []) if d.get("disponibil") else []
	total = sum(s for k, s in trepte)
	if total <= 0:
		return []
	return [(k, int(round(100.0 * s / total)), s) for k, s in trepte]


def textTreapta(procent, secunde):
	"""„89%, 32 min”: procentul si cat timp a stat procesorul pe treapta."""
	return u"%d%%, %s" % (procent, textDurata(secunde))


def textScurt(d=None):
	"""Toate citirile pe un rand, pentru afisajul tehnic: „cel mult 1600 MHz (Performanță); acum 400 MHz; 72 °C;
	980 mV”; gol daca nu se poate citi nimic. Pe bucati: campuriBara()."""
	c = campuriBara(d)
	return u"; ".join(x for x in (c["setata"], c["acum"], c["temperatura"], c["tensiune"]) if x)


def campuriBara(d=None):
	"""Citirile pe campuri, pentru afisajul tehnic (bara a doua, pagina receptorului): setata (modul si plafonul, cu
	„s-a încălzit” cand caldura il tine jos), acum, temperatura, tensiune, trepte (procentul pe fiecare treapta, pe un
	rand) si culoarea temperaturii. Campurile care nu se pot citi sunt goale."""
	d = d or citire(2.0)
	cur = d.get("frecventa_khz")
	t = d.get("temperatura")
	return {
		"setata": textFrecventaSetata(d, True) if d.get("disponibil") and d.get("plafon_khz") else "",
		"acum": _("acum %d MHz") % _mhz(cur) if cur else "",
		"temperatura": u"%d °C" % t if t is not None else "",
		"temperatura_culoare": temperaturaCuloare(t),
		"tensiune": textTensiune(d.get("tensiune_mv")) if d.get("tensiune_mv") else "",
		"trepte": u" · ".join(u"%d: %d%%" % (_mhz(k), pr) for k, pr, s in trepteProcent(d)),
	}


def randuriInformatii(d=None):
	"""Randurile pentru „Informatii” (Screens/Information.py si informatii_web.py): [(eticheta, valoare)]; cu timpul
	pe fiecare treapta („Treapta 400 MHz: 89%, 32 min”) si motivul cand caldura tine plafonul jos."""
	d = d or citire(1.0)
	rez = []
	if d.get("disponibil"):
		rez.append((_("Modul procesorului"), numeMod(d.get("mod"))))
		rez.append((_("Frecvența setată"), textFrecventaSetata(d, True)))
		rez.append((_("Frecvența de acum"), textFrecventa(d.get("frecventa_khz"))))
	rez.append((_("Temperatura"), textTemperatura(d.get("temperatura"))))
	if d.get("tensiune_mv"):
		rez.append((_("Tensiunea"), textTensiune(d.get("tensiune_mv"))))
	if d.get("folosit_procent") is not None:
		rez.append((_("Procesor folosit"), "%d%%" % d["folosit_procent"]))
	for khz, procent, secunde in trepteProcent(d):
		rez.append((_("Treapta %d MHz") % _mhz(khz), textTreapta(procent, secunde)))
	return rez


CEAS_INFORMATII_MS = 2000
LATIME_ETICHETA = 26


def randuriTextInformatii(d=None):
	"""randuriInformatii ca randuri de text aliniate ca in „Informatii” („  Eticheta:     valoare”)."""
	return [u"  %s%s" % ((e + ":").ljust(LATIME_ETICHETA), v) for e, v in randuriInformatii(d)]


def textInformatii(inainte, dupa, d=None):
	"""Textul „Informatii”: randurile date, cele ale procesorului, apoi restul."""
	return u"\n".join(list(inainte) + randuriTextInformatii(d) + list(dupa))


def textFaraSalt(eticheta, text):
	"""ScrollLabel.setText muta textul la inceput; la o improspatare vie se pune la loc pozitia derulata de om."""
	lung = getattr(eticheta, "long_text", None)
	poz = None
	if lung is not None:
		try:
			poz = lung.position()
		except Exception:
			poz = None
	eticheta.setText(text)
	if poz is None or poz.y() >= 0:
		return
	try:
		lung.move(poz)
		if getattr(eticheta, "total", None):
			eticheta.updateScrollbar()
	except Exception as e:
		_jurnal("pozitia textului: %r" % (e,))


class InformatiiVii(object):
	"""Randurile procesorului dintr-un ecran cu text derulabil (HdsReceiverInfo din „Informatii”), rescrise la
	CEAS_INFORMATII_MS numai cat ecranul se vede: ceasul porneste in onShown si se opreste in onHide si onClose.
	populate() da o data randurile de dinainte si de dupa (text()); ceasul refoloseste numai citirea procesorului
	(HdsProcesor.citire, cativa ms), nu reface tot ecranul, si nu muta textul derulat (textFaraSalt)."""

	def __init__(self, ecran, ms=CEAS_INFORMATII_MS, nume_text="text"):
		from enigma import eTimer
		self.ecran = ecran
		self.nume_text = nume_text
		self.ms = ms
		self.inainte = []
		self.dupa = []
		self.gata = False
		self.ceas = eTimer()
		self.ceas.callback.append(self.improspateaza)
		ecran.onShown.append(self.porneste)
		ecran.onHide.append(self.opreste)
		ecran.onClose.append(self.opreste)

	def porneste(self):
		self.ceas.start(self.ms, False)

	def opreste(self):
		self.ceas.stop()

	def text(self, inainte, dupa, d=None):
		"""Din populate(): tine randurile celelalte si intoarce textul intreg."""
		self.inainte, self.dupa, self.gata = list(inainte), list(dupa), True
		return textInformatii(self.inainte, self.dupa, d)

	def improspateaza(self):
		if not self.gata:
			return
		try:
			textFaraSalt(self.ecran[self.nume_text], textInformatii(self.inainte, self.dupa, citire(1.0)))
		except Exception as e:
			_jurnal("informatiile: %r" % (e,))


def textEcranInformatii(ecran, inainte, dupa):
	"""Din populate() al ecranului „Informatii”: textul intreg, cu randurile procesorului intre `inainte` si `dupa`.
	Ecranul adevarat are ecran.procesorVii (InformatiiVii, improspatarea vie); ecranul fals al paginii web
	(informatii_web._textEcran) nu il are si primeste o citire proaspata la fiecare cerere."""
	vii = getattr(ecran, "procesorVii", None)
	if vii is not None:
		return vii.text(inainte, dupa)
	return textInformatii(inainte, dupa)


def temperaturaCuloare(t):
	"""„normal”, „galben” (80-94 °C) sau „rosu” (de la 95 °C)."""
	if t is None or t < TEMP_GALBEN:
		return "normal"
	if t < PAZA_COBORARE:
		return "galben"
	return "rosu"


# ---------------------------------------------------------------- graficul (ecranul „Procesor” si pagina web)

NUME_GRAFIC = {
	60: N_("Ultima oră"),
	30: N_("Ultimele 30 de minute"),
}

TITLU_GRAFIC = {
	60: N_("Temperatura în ultima oră"),
	30: N_("Temperatura în ultimele 30 de minute"),
}

# %d: TEMP_GALBEN, apoi PAZA_COBORARE
LEGENDA_GRAFIC = N_("Linia colorată: temperatura cea mai mare din fiecare minut, galbenă de la %d °C, roșie de la %d °C. "
	"Barele de jos: viteza procesorului, galbene când a încetinit de căldură. Liniile drepte: unde încetinește procesorul "
	"(întreruptă: unde revine).")
ISTORIC_DE_LA = N_("Istoricul începe de la %s.")
ISTORIC_ACUM = N_("Istoricul începe acum %s.")

# culorile desenului pe televizor, 0xAARRGGBB ca la eCanvas (AA = transparenta, 0 = opac), cele ale skinului
# HDSatelit; culoriGrafic() le ia din skinul activ cand le are. Toate sunt opace (fill nu amesteca).
CULORI_GRAFIC = {
	"fundal": 0x0010162A,               # hdsPanelDialog, fara transparenta
	"grila": 0x002A3350,                # hdsTrack
	"eticheta": 0x00AEB9CC,             # hdsLabel: scara, orele, numele modurilor, liniile schimbarii de mod
	"normal": 0x009FB4FF,               # hdsBrandLight: temperatura sub TEMP_GALBEN
	"galben": 0x00F1C40F,               # hdsWarn: de la TEMP_GALBEN
	"rosu": 0x00FF6B5E,                 # hdsBad: de la PAZA_COBORARE
	"frecventa": 0x005F6D9F,            # hdsBrandLight amestecat 55% cu fundalul (contrast 3,6 fata de fundal)
	"frecventa_caldura": 0x00F5B83D,    # hdsAmber
	"prag_mod": 0x00F5B83D,             # hdsAmber: treptele de caldura ale modului si revenirea (intrerupta)
	"prag_paza": 0x00FF6B5E,            # hdsBad
	"prag_driver": 0x00FF6B5E,          # hdsBad
	"inceput": 0x00667085,              # hdsDisabled
}

# culoarea din desen -> numele culorii din skin (culoriGrafic)
CULORI_SKIN_GRAFIC = {
	"fundal": "hdsPanelDialog",
	"grila": "hdsTrack",
	"eticheta": "hdsLabel",
	"normal": "hdsBrandLight",
	"galben": "hdsWarn",
	"rosu": "hdsBad",
	"frecventa_caldura": "hdsAmber",
	"prag_mod": "hdsAmber",
	"prag_paza": "hdsBad",
	"prag_driver": "hdsBad",
	"inceput": "hdsDisabled",
}


def _amestec(a, b, parte):
	"""Culoarea a amestecata cu b (parte = cat din a), fara transparenta."""
	rez = 0
	for deplasare in (16, 8, 0):
		ca, cb = (a >> deplasare) & 0xFF, (b >> deplasare) & 0xFF
		rez |= int(round(cb + (ca - cb) * parte)) << deplasare
	return rez


def culoriGrafic(colorNames=None):
	"""CULORI_GRAFIC, cu culorile skinului activ (skin.colorNames: nume -> gRGB) unde le are. Toate sunt opace;
	frecventa e culoarea „normal” amestecata cu fundalul."""
	rez = dict(CULORI_GRAFIC)
	if colorNames is None or not hasattr(colorNames, "get"):
		return rez
	for cheie, nume in CULORI_SKIN_GRAFIC.items():
		c = colorNames.get(nume)
		if c is None:
			continue
		try:
			rez[cheie] = c.argb() & 0xFFFFFF
		except Exception:
			pass
	rez["frecventa"] = _amestec(rez["normal"], rez["fundal"], 0.55)
	return rez


def numeGrafic(minute):
	return _(NUME_GRAFIC.get(minute, NUME_GRAFIC[GRAFIC_MINUTE[0]]))


def titluGrafic(minute):
	return _(TITLU_GRAFIC.get(minute, TITLU_GRAFIC[GRAFIC_MINUTE[0]]))


def textLegendaGrafic():
	return _format(_(LEGENDA_GRAFIC), LEGENDA_GRAFIC, (TEMP_GALBEN, PAZA_COBORARE))


def textIstoricMemorie():
	"""Unde sta istoricul (fara taste: aceeasi fraza pe televizor si in web)."""
	return _("Istoricul se ține numai în memorie și începe din nou când repornește receptorul.")


def textDescriereGrafic():
	"""Descrierea randului „Graficul” din ecranul „Procesor”."""
	return _("Alege cu stânga, dreapta sau OK cât timp arată graficul.") + " " + textIstoricMemorie()


def textIstoric(g):
	"""„Istoricul începe de la 14:05.” cand istoricul e mai scurt decat graficul; altfel gol. O traducere cu alte semne
	de formatare nu arunca (_format)."""
	u = g.get("inceput_in_urma")
	if u is None or u >= g.get("minute", GRAFIC_MINUTE[0]):
		return ""
	if g.get("inceput_ora"):
		return _format(_(ISTORIC_DE_LA), ISTORIC_DE_LA, (g["inceput_ora"],))
	return _format(_(ISTORIC_ACUM), ISTORIC_ACUM, (textDurata(u * 60),))


def praguriMod(mod, pl):
	"""Liniile unui mod: [(°C, fel)]. „mod”: treptele de caldura (din scara: Performanta PERF_COBORARE, Automat
	AUTO_COBORARE); „revenire”: Performanta urca la loc numai sub PERF_URCARE (linie intrerupta). Normal si Racoros nu
	au linii proprii."""
	rez = []
	if not pl:
		return rez
	sc = scara(mod, pl)
	for khz, prag in sc[1:]:
		rez.append((prag, "mod"))
	if mod == "performanta" and len(sc) > 1:
		rez.append((PERF_URCARE, "revenire"))
	return rez


def praguriGrafic(mod, pl=None, pd=None):
	"""Liniile pragurilor care ajung in dreapta graficului: [(°C, numele scurt al modului sau "", fel)]. fel „mod” si
	„revenire”: ale modului (praguriMod); „paza”: paza comuna, in orice mod; „driver”: paza driverului (pm_temp), numai
	cand e pornita."""
	nume = numeMod(mod, scurt=True)
	rez = [(t, nume, fel) for t, fel in praguriMod(mod, pl)]
	rez.append((PAZA_COBORARE, "", "paza"))
	if pd and pd.get("pornita") and pd.get("coborare"):
		rez.append((pd["coborare"], "", "driver"))
	return rez


def _ora(perete):
	lt = time.localtime(perete)
	return "%02d:%02d" % (lt.tm_hour, lt.tm_min)


def _oreGrafic(minute, perete, pas=5):
	"""Semnele de sub grafic la fiecare `pas` minute rotunde ale ceasului, cel mult `minute` in urma:
	[(minute in urma, „14:10”, din zece in zece)]. Cu ceasul receptorului nepus: „10 min”, „20 min” ... „60 min” (cat in
	urma, aceeasi forma scurta pana la capat)."""
	rez = []
	if perete >= CEAS_POTRIVIT:
		t = time.localtime(perete)
		prim = perete - (t.tm_min % pas) * 60 - t.tm_sec
		for k in range(minute // pas + 2):
			x = prim - k * pas * 60
			in_urma = (perete - x) / 60.0
			if in_urma > minute:
				break
			lt = time.localtime(x)
			rez.append((round(in_urma, 3), "%02d:%02d" % (lt.tm_hour, lt.tm_min), lt.tm_min % 10 == 0))
	else:
		for m in range(pas, minute + 1, pas):
			rez.append((float(m), _("%d min") % m, m % 10 == 0))
	return rez


def istoricGrafic(minute=None, p=None, acum=None, perete=None):
	"""Datele graficului pentru ultimele `minute` minute (ecranul si pagina web): {"minute", "ruleaza", "versiune",
	"puncte", "segmente", "jos", "sus", "fsus", "praguri", "ore", "inceput_in_urma", "inceput_ora"}.

	puncte, cel mai vechi primul: [{"in_urma", "durata", "tmax", "tmed", "fmhz", "caldura", "legat", "mod"}]; minutul se
	termina acum in_urma minute (minutul de acum: 0) si a tinut durata minute (minutul de acum: cat a trecut din el);
	tmax si tmed in °C (None fara temperatura), fmhz media frecventei; legat: minutul de dinainte e si el in grafic; mod:
	modul aplicat in minutul acela. segmente: bucatile de timp ale fiecarui mod, [{"mod", "nume", "de_la", "pana_la",
	"praguri"}] (de_la/pana_la in minute in urma; prima incepe la marginea din stanga, ultima se termina acum), cu liniile
	modului (praguriMod). praguri: liniile care ajung in dreapta (modul de acum, paza comuna, paza driverului numai cand
	temperatura a trecut de 100 °C). jos/sus: scara in °C, din zece in zece, cu datele si liniile inauntru si 5 °C
	deasupra; fsus: treapta cea mai inalta, in MHz. O copie mica a istoricului si calcule simple, fara citiri de fisiere
	(in afara pragurilor driverului, citite o singura data): se poate chema din firul principal."""
	p = p or procesor()
	minute = minute if minute in GRAFIC_MINUTE else GRAFIC_MINUTE[0]
	acum = p.ceas() if acum is None else acum
	perete = time.time() if perete is None else perete
	inceput, randuri, versiune = p.istoric.instantaneu()
	puncte = []
	anterior = None
	mod_ant = None
	for r in randuri:
		i, tmax, tsuma, tnumar, fsuma, fnumar, caldura = r[:7]
		mod = r[7] if len(r) > 7 and r[7] in MODURI else None
		start = inceput + i * 60.0
		sfarsit = min(start + 60.0, acum)
		in_urma = max(0.0, acum - sfarsit) / 60.0
		if in_urma >= minute:
			mod_ant = mod or mod_ant
			continue
		mod = mod or mod_ant or p.mod
		mod_ant = mod
		puncte.append({
			"in_urma": round(in_urma, 3),
			"durata": round(max(0.0, sfarsit - start) / 60.0, 3),
			"tmax": tmax,
			"tmed": round(float(tsuma) / tnumar, 1) if tnumar else None,
			"fmhz": int(round(float(fsuma) / fnumar / 1000.0)) if fnumar else None,
			"caldura": bool(caldura),
			"legat": anterior is not None and i == anterior + 1,
			"mod": mod,
		})
		anterior = i
	if p.trepte:
		trepte, folosite, fab = p.trepte, p.trepte_folosite or p.trepte, p.fabricant
	else:
		try:
			trepte, folosite, fab = _treptePlafon()
		except Exception:
			trepte, folosite, fab = [], [], None
	pl = plafoane(folosite, fab) if folosite else None
	segmente = []
	for x in puncte:
		if segmente and segmente[-1]["mod"] == x["mod"]:
			continue
		stanga = float(minute) if not segmente else min(float(minute), x["in_urma"] + x["durata"])
		if segmente:
			segmente[-1]["pana_la"] = stanga
		segmente.append({"mod": x["mod"], "de_la": stanga, "pana_la": 0.0})
	if not segmente:
		segmente.append({"mod": p.mod, "de_la": float(minute), "pana_la": 0.0})
	for s in segmente:
		s["nume"] = numeMod(s["mod"], scurt=True)
		s["praguri"] = praguriMod(s["mod"], pl)
	temperaturi = [x["tmax"] for x in puncte if x["tmax"] is not None]
	pd = pazaDriver()
	if not temperaturi or max(temperaturi) <= 100:
		pd = None       # linia driverului numai cand temperatura a trecut de 100 °C (altfel e in nota ecranului)
	praguri = praguriGrafic(segmente[-1]["mod"], pl, pd)
	jos = GRAFIC_JOS
	if temperaturi:
		jos = min(jos, int(math.floor((min(temperaturi) - 5) / 10.0)) * 10)
	jos = max(0, jos)
	linii = [t for s in segmente for t, fel in s["praguri"]] + [t for t, nume, fel in praguri]
	sus = max(temperaturi + linii + [PAZA_COBORARE]) + 5
	sus = min(GRAFIC_SUS_MAX, int(math.ceil(sus / 10.0)) * 10)
	frecvente = [x["fmhz"] for x in puncte if x["fmhz"]]
	fsus = max([max(trepte) // 1000 if trepte else 0] + frecvente)
	return {
		"minute": minute,
		"ruleaza": bool(p.pornit),
		"versiune": versiune,
		"puncte": puncte,
		"segmente": segmente,
		"jos": jos,
		"sus": sus,
		"fsus": fsus,
		"praguri": praguri,
		"ore": _oreGrafic(minute, perete),
		"inceput_in_urma": None if inceput is None else round(max(0.0, acum - inceput) / 60.0, 3),
		"inceput_ora": _ora(perete - (acum - inceput)) if inceput is not None and perete >= CEAS_POTRIVIT else "",
	}


def fontGrafic(inaltime):
	"""Marimea textului din grafic (scara, orele, valorile pragurilor, modurile), dupa inaltimea panzei."""
	return max(14, min(21, int(round(inaltime * 0.073))))


def _pozitiiEtichete(etichete, rand, f, sus_lim, jos_lim):
	"""Casutele textelor din coloana din dreapta: {°C: y}. Liniile se opresc inaintea coloanei, deci fiecare text sta
	chiar in dreptul liniei lui (ca pe o scara); cand doua linii sunt prea aproape, textele se departeaza cat trebuie
	ca literele (cam 0,73 din marimea fontului, centrate in casuta) sa nu se atinga, in aceeasi ordine ca liniile.
	Casutele raman intre sus_lim si jos_lim."""
	departe = 0.84 * f + 2
	lo, hi = sus_lim + rand / 2.0, jos_lim - rand / 2.0
	ordine = sorted(etichete, key=lambda e: e[1])
	centre = [min(max(y, lo), hi) for t, y in ordine]
	for i in range(1, len(centre)):
		centre[i] = max(centre[i], centre[i - 1] + departe)
	if centre and centre[-1] > hi:
		centre[-1] = hi
		for i in range(len(centre) - 2, -1, -1):
			centre[i] = min(centre[i], centre[i + 1] - departe)
	return dict((t, int(round(c - rand / 2.0))) for (t, y), c in zip(ordine, centre))


def _latimeText(text, f):
	"""Latimea unui text in px, cu o marja (fonturile Hds: cel mult ~0,62 din marimea fontului pe litera)."""
	return int(len(text) * f * 0.62) + 4


def desenGrafic(g, latime, inaltime, culori=None, font=None):
	"""Graficul ca operatii de desen pe o panza latime x inaltime (Screens/HdsProcesor.py le da unui CanvasSource):
	("fill", x, y, l, h, culoare), ("linie", x0, y0, x1, y1, grosime, culoare), ("cerc", x, y, raza, culoare),
	("text", x, y, l, h, culoare, text, aliniere), aliniere „stanga”, „dreapta” sau „centru”. Umplerile si textele au
	coordonate intregi. font: marimea textului (fontGrafic, marita de „Marime fonturi” daca e cazul).

	Asezarea: la stanga scara in °C (din 10 in 10); in mijloc temperatura, dedesubt banda frecventei (o bara pe minut,
	galbena cand plafonul a fost tinut jos de caldura), jos orele; in dreapta o coloana ingusta cu valoarea fiecarei
	linii care ajunge acolo („85 °C”, in culoarea ei, in dreptul liniei, departate cat trebuie sa nu se suprapuna) si
	treapta de sus a benzii („1600”). Liniile se opresc inaintea coloanei, iar datele nu trec niciodata prin texte. Liniile modului se trag numai pe bucata de
	timp a modului lor; cand in grafic sunt mai multe moduri, o linie verticala desparte bucatile si numele fiecarui
	mod sta sus, deasupra bucatii lui. Temperatura cea mai mare din minut: linia colorata ca temperatura de pe ecran
	(normal, galben de la TEMP_GALBEN, rosu de la PAZA_COBORARE). Doua minute se leaga numai daca sunt unul dupa altul
	(o pauza a istoricului lasa gol); un minut singur si minutul de acum au un punct."""
	c = dict(CULORI_GRAFIC)
	c.update(culori or {})
	latime, inaltime = int(latime), int(inaltime)
	if latime < 160 or inaltime < 100:
		return [("fill", 0, 0, max(0, latime), max(0, inaltime), c["fundal"])]
	minute = g.get("minute") or GRAFIC_MINUTE[0]
	f = int(font or fontGrafic(inaltime))
	rand = int(round(f * 1.35))
	st = int(round(f * 3.7))                   # „100 °C” la stanga
	col = int(round(f * 3.4))                  # „115 °C”, „1600” in dreapta
	x0, x1 = st, latime - col - 8
	pw = float(x1 - x0)
	segmente = [s for s in (g.get("segmente") or ()) if s.get("de_la", 0) > s.get("pana_la", 0)]
	fasie = rand if len(segmente) > 1 else 0   # sus: numele modurilor, numai cand sunt mai multe
	sus_y = fasie + rand // 2 + 2
	jos_ore = inaltime - rand - 2              # linia de baza a benzii; orele sub ea
	banda = max(20, int(round(inaltime * 0.11)))
	sus_banda = jos_ore - banda
	jos_grafic = sus_banda - max(8, rand // 3)
	ph = float(jos_grafic - sus_y)
	tj, ts = g["jos"], g["sus"]
	if ts <= tj:
		ts = tj + 10

	def X(u):
		return x1 - min(float(minute), max(0.0, u)) * pw / minute

	def Y(t):
		return jos_grafic - (t - tj) * ph / (ts - tj)

	ops = [("fill", 0, 0, latime, inaltime, c["fundal"])]
	for t in range(tj, ts + 1, 10):
		y = int(round(Y(t)))
		ops.append(("fill", x0, y, x1 - x0, 1, c["grila"]))
		ops.append(("text", 0, y - rand // 2, st - 10, rand, c["eticheta"], u"%d °C" % t, "dreapta"))
	# orele: la o ora din 10 in 10 minute, la 30 de minute din 5 in 5; cu ceasul nepus textul („60 perc”) e mai lung,
	# iar daca nu incape intre doua semne se scrie numai la fiecare al doilea (linia grilei ramane la toate)
	ore = [(u, text) for u, text, zece in g.get("ore") or () if u <= minute and (minute <= 30 or zece)]
	lt = max([int(round(f * 3.4))] + [_latimeText(text, f) for u, text in ore])
	sari = 2 if lt > pw * (10.0 if minute > 30 else 5.0) / minute - 4 else 1
	for k, (u, text) in enumerate(ore):
		x = int(round(X(u)))
		ops.append(("fill", x, sus_y, 1, jos_ore - sus_y, c["grila"]))
		if k % sari == 0:
			ops.append(("text", min(max(0, x - lt // 2), latime - lt), jos_ore + 2, lt, rand, c["eticheta"], text,
				"centru"))
	u = g.get("inceput_in_urma")
	if u is not None and u < minute:
		ops.append(("fill", int(round(X(u))), sus_y, 2, jos_ore - sus_y, c["inceput"]))
	# banda frecventei: „MHz” in stanga, treapta de sus in dreapta
	fsus = g.get("fsus") or 0
	ops.append(("text", 0, sus_banda, st - 10, banda, c["eticheta"], "MHz", "dreapta"))
	if fsus > 0:
		ops.append(("text", x1 + 6, sus_banda, latime - x1 - 6, banda, c["eticheta"], "%d" % fsus, "stanga"))
	ops.append(("fill", x0, jos_ore, x1 - x0, 1, c["grila"]))
	for x in g["puncte"]:
		if not x.get("fmhz") or fsus <= 0:
			continue
		dr = int(round(X(x["in_urma"]))) - 1
		stg = max(x0, int(round(X(x["in_urma"] + x["durata"]))) + 1)
		if dr - stg < 1:
			continue
		h = max(2, int(round(banda * min(1.0, float(x["fmhz"]) / fsus))))
		ops.append(("fill", stg, jos_ore - h, dr - stg, h, c["frecventa_caldura"] if x.get("caldura") else c["frecventa"]))

	# liniile pragurilor: ale modurilor pe bucata lor de timp (intrerupta pentru revenire), paza pe toata latimea
	def linie(t, fel, xa, xb):
		if not tj <= t <= ts or xb - xa < 2:
			return
		y = int(round(Y(t)))
		culoare = c.get("prag_" + ("mod" if fel == "revenire" else fel), c["prag_paza"])
		if fel != "revenire":
			ops.append(("fill", int(round(xa)), y - 1, int(round(xb - xa)), 2, culoare))
			return
		pas = max(14, int(round((xb - xa) / 20.0)))
		x = xa
		while x < xb - 2:
			ops.append(("fill", int(round(x)), y - 1, int(min(pas * 0.6, xb - x)), 2, culoare))
			x += pas

	praguri = g.get("praguri") or ()
	if segmente:
		for s in segmente:
			for t, fel in s.get("praguri") or ():
				linie(t, fel, X(s["de_la"]), X(s["pana_la"]))
		for t, nume, fel in praguri:
			if fel in ("paza", "driver"):
				linie(t, fel, x0, x1)
	else:
		for t, nume, fel in praguri:
			linie(t, fel, x0, x1)
	# bucatile modurilor: linia verticala a schimbarii si numele modului sus
	if fasie:
		for n, s in enumerate(segmente):
			xa, xb = X(s["de_la"]), X(s["pana_la"])
			if n > 0:
				ops.append(("fill", int(round(xa)) - 1, 0, 2, jos_ore - 0, c["eticheta"]))
			nume = s.get("nume") or ""
			if nume and xb - xa - 12 >= _latimeText(nume, f):
				ops.append(("text", int(round(xa)) + 6, 0, int(round(xb - xa)) - 12, fasie, c["eticheta"], nume, "stanga"))
	# datele: cea mai mare temperatura din fiecare minut (colorata)
	gros = max(3.0, round(inaltime / 90.0, 1))

	def centru(x):
		return x["in_urma"] + x["durata"] / 2.0

	vazute = []     # punctele in ordine; None = minut in afara graficului (nu se leaga peste el)
	for x in g["puncte"]:
		vazute.append(x if centru(x) <= minute else None)
	ultim = len(vazute) - 1
	for n, x in enumerate(vazute):
		if x is None or x["tmax"] is None:
			continue
		a = vazute[n - 1] if n > 0 and x.get("legat") else None
		if a is not None and a["tmax"] is not None:
			culoare = c[temperaturaCuloare(max(a["tmax"], x["tmax"]))]
			ops.append(("linie", X(centru(a)), Y(a["tmax"]), X(centru(x)), Y(x["tmax"]), gros, culoare))
		else:
			a = None
		urm = vazute[n + 1] if n < ultim else None
		urm_legat = urm is not None and urm.get("legat") and urm["tmax"] is not None
		if n == ultim:
			ops.append(("cerc", X(centru(x)), Y(x["tmax"]), gros * 1.4, c[temperaturaCuloare(x["tmax"])]))
		elif a is None and not urm_legat:
			ops.append(("cerc", X(centru(x)), Y(x["tmax"]), gros, c[temperaturaCuloare(x["tmax"])]))
	# coloana din dreapta: valoarea liniilor care ajung aici, in afara datelor
	etichete = [(t, Y(t)) for t, nume, fel in praguri if tj <= t <= ts]
	pozitii = _pozitiiEtichete(etichete, rand, f, fasie, jos_grafic)
	for t, nume, fel in praguri:
		if t not in pozitii:
			continue
		culoare = c.get("prag_" + ("mod" if fel == "revenire" else fel), c["prag_paza"])
		ops.append(("text", x1 + 6, pozitii[t], latime - x1 - 6, rand, culoare, u"%d °C" % t, "stanga"))
	return ops


# ---------------------------------------------------------------- pornirea si oprirea (din mytest.py)

_ceas_mesaje = []


def _golesteMesaje():
	p = procesor()
	while p.mesaje:
		_arataMesaj(p.mesaje.popleft())


def _incalzitInAsteptare(Notifications):
	"""Mesajele „s-a incalzit” inca nearatate din coada ecranului (omul era intr-un meniu): [intrarile din coada]."""
	rez = []
	for x in list(getattr(Notifications, "notifications", None) or ()):
		try:
			if x[4] == "HdsProcesor" and x[3].get("text") not in (textRacit(), textRevenireNormal()):
				rez.append(x)
		except (IndexError, AttributeError, TypeError):
			continue
	return rez


def _arataMesaj(text):
	"""Mesaj scurt pe ecran, numai din firul principal (apare peste canal, sau dupa iesirea din meniu). In standby nu se
	arata nimic (la trezire ar fi vechi). „s-a racit” cu un „s-a incalzit” inca nearatat in coada: episodul s-a
	incheiat inainte ca omul sa-l vada, deci se scoate si acela si nu se mai arata nimic (ecranul „Procesor” si pagina
	web spun oricum ca s-a racit)."""
	try:
		standby = sys.modules.get("Screens.Standby")
		if standby is not None and getattr(standby, "inStandby", None) is not None:
			return
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		if text == textRacit():
			vechi = _incalzitInAsteptare(Notifications)
			if vechi:
				for x in vechi:
					try:
						Notifications.notifications.remove(x)
					except ValueError:
						pass
				return
		Notifications.AddPopup(text, MessageBox.TYPE_INFO, 15, "HdsProcesor")
	except Exception as e:
		_jurnal("mesajul: %r" % (e,))


def porneste():
	"""Din mytest.py, dupa pornirea sesiunii: setarea, pregatirea, verificarea pornirii trecute si firul pazei."""
	initConfig()
	from Components.config import config
	if not disponibil():
		_jurnal("cpufreq lipseste sau nu se poate scrie: nimic de pazit")
		return
	p = procesor()
	p.pregateste()
	element = config.hds_procesor.mod
	salvat = element.saved_value if element.saved_value is not None else element.value
	if p.verificaProba() and salvat in MODURI_ACCELERATE:
		# numai un mod care accelereaza trece pe normal; un mod ales dupa (racoros, normal) ramane al omului
		_jurnal("doua porniri la rand incheiate necurat cu procesorul accelerat: modul trece pe normal")
		jurnalDisc("doua porniri incheiate necurat cu procesorul accelerat: modul trece pe normal")
		_salveazaAles(element, IMPLICIT)
		try:
			from Components.config import configfile
			configfile.save()
		except Exception as e:
			_jurnal("salvarea setarii: %r" % (e,))
		_arataMesaj(textRevenireNormal())
	valoare = config.hds_procesor.mod.value
	p.mod = valoare if valoare in MODURI else IMPLICIT
	p.porneste()
	_jurnal("paza pornita (modul %s, fabricant %s kHz, trepte %s)" % (p.mod, p.fabricant, p.trepte))
	try:
		from enigma import eTimer
		ceas = eTimer()
		ceas.callback.append(_golesteMesaje)
		ceas.start(10000, False)
		_ceas_mesaje.append(ceas)
	except Exception as e:
		_jurnal("ceasul mesajelor: %r" % (e,))


def laOprire():
	"""Din mytest.py, la iesirea din enigma2."""
	for ceas in _ceas_mesaje:
		try:
			ceas.stop()
		except Exception:
			pass
	del _ceas_mesaje[:]
	if _unic[0] is not None and _unic[0].pornit:
		_unic[0].laOprire()
