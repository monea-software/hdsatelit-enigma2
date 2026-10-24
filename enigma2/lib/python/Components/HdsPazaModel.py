# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPazaModel.py: paza de model. Imaginea se scrie si porneste numai pe receptorul pentru care e construita.
#
# Regulile stau intr-un singur fisier, /etc/hdsatelit-model, scris la construire de reteta imaginii
# (hdsatelit-image.bb): numele receptorului, cipul, tipul placii din driver, antetul de fabrica al partitiei
# deviceinfo (HW=) si asezarea partitiilor data de bootloader. Acelasi fisier, plus versiunea si sumele SHA-256 ale lui
# kernel.bin si rootfs.tar.bz2, intra in pachetul de actualizare ca e2/update/hdsatelit-model (marcajul pachetului).
# Il citesc: acest modul (pe firul enigma2 si pe PC, in scripturile de pregatire), garda de la pornire din
# tools/enigma2.sh.in (awk) si pagina web paza_model_web.py. Fara fisierul de reguli (emulatorul de pe PC, alta
# imagine) paza „nu se aplica” si nu schimba nimic.
#
# Versiunea din texte ("Acest software (HD Satelit x.y.z)", ecranul, /paza-model, /actualizare): cea care ruleaza acum,
# din /etc/image-version (versiuneAcum), nu version= din reguli, care ramane al imaginii scrise pe receptor si nu se
# schimba printr-o actualizare prin pachete (0.6.2: dupa 0.6.1 pagina spunea "HD Satelit 0.6.0"). Imaginea scrisa se
# arata separat, numai cand difera ("Imaginea de bază", ca in Despre imagine).
#
# Amprenta receptorului:
# - cipul: CHIP_VERSION din /proc/msp/sys (driverul HiSilicon il citeste din cip);
# - partitiile: blkdevparts din /proc/cmdline (tabela data de bootloader) si marimea partitiei nucleului din
#   /proc/partitions;
# - placa: campul HW= din antetul partitiei deviceinfo (primii 4 KiB, scrisi din fabrica). Din antet se pastreaza numai
#   HW= si MAGICNUM=; adresa MAC din acelasi antet nu se pastreaza nicaieri;
# - tipul placii din driver: /proc/stb/info/boxtype (dovedeste driverul, nu receptorul; intra in potrivire ca pe PC sa se
#   poata proba un driver strain);
# - eticheta de la 0x3F6000 a partitiei deviceinfo („BOX_TYPE:<tip> UPD_PATH:<cale>”): o scrie showiframe al imaginii
#   care a rulat, din tipul placii spus de driverul ei. Pe un receptor de alt tip (de exemplu u571), la prima pornire a
#   imaginii noastre, eticheta e inca a lui, singurul semn care il deosebeste cand cipul si partitiile sunt la fel. De
#   aceea un BOX_TYPE care exista si difera de regula e nepotrivire („eticheta”); o eticheta lipsa nu hotaraste nimic,
#   iar UPD_PATH (numele modelului) se arata numai.
# - memoria interna (eMMC): marimea discului intreg mmcblk0 din /proc/partitions. Amiko Viper 4K V30 are aceeasi placa,
#   acelasi cip, acelasi tip de placa (u57) si aceeasi asezare a partitiilor ca V20; numai memoria interna difera (8 GB
#   fata de 4 GB: 3,66 GiB, 3837952 KiB, pe V20). Regulile pot da limitele (emmc_min_kib=, emmc_max_kib=, in KiB);
#   regulile scrise pe receptoarele de azi nu le au si nu se schimba printr-o actualizare (vin cu imaginea), deci
#   pentru machinebuild=viper4kv20 fara limite in reguli se foloseste EMMC_IMPLICIT: cel mult EMMC_MAXIM_V20_KIB (5 GiB,
#   cu marja fata de ambele). Hotaraste in ambele trepte; fara limite (alt model) nu se verifica. Un disc intreg
#   nelistat nu hotaraste nimic (ca eticheta lipsa): pe un receptor adevarat /proc/partitions il listeaza mereu, iar un
#   /proc/partitions necitit cade deja la "kernel"; uneltele de pe PC dau uneori numai randurile p9 si p10.
# Informative: board_revision (o constanta din driver, aceeasi pe toate placile u57), arborele dispozitivului, tunerele.
# Ce nu se poate citi nu se potriveste: paza cade inchisa.
#
# Doua trepte. Treapta intai (modelul confirmat pe un receptor adevarat; regulile fara „confirmat=nu”, cum sunt toate
# cele scrise pana acum): toate cheile de mai sus hotarasc. Treapta a doua (un model nou, cu regulile inca neverificate
# pe aparat, „confirmat=nu”): hotarasc numai cipul, tipul placii (din driver si din eticheta, fata de lista din
# „boxtype=”, de exemplu u57,u571) si locul nucleului si al sistemului (partitiile kernel si rootfs pe locurile din
# reguli, amandoua prezente); placa (HW=), tabela partitiilor si marimea nucleului sunt numai avertismente: interfata
# porneste, iar o nota arata valorile citite („model neconfirmat”). „boxtype=” poate fi o lista si in treapta intai; o
# singura valoare se compara ca pana acum.
#
# La pornire hotaraste garda din enigma2.sh (inaintea lui showiframe) si scrie verdictul in /tmp/hds-paza-model.stare
# (RAM), impreuna cu valorile citite. verdict() foloseste acel fisier ca singura sursa pentru stare si pentru randurile
# amprentei (dupa el a pornit sau nu showiframe); ce se citeste acum diferit se da separat („nepotriviri_acum”).
# Numai daca fisierul lipseste se face aici aceeasi comparatie. inPaza() citeste numai regulile si fisierul de stare
# (fara amprenta), fiindca il cheama panoul web la fiecare cerere.
# La scriere (actualizarea din meniu, Screens/HdsSoftwareUpdate.py) se cere marcajul pachetului, potrivirea lui cu
# amprenta si sumele SHA-256 ale fisierelor care se scriu; lucrarile lungi (dezarhivarea, sumele) ruleaza pe un fir
# separat (LucrareFundal), rezultatul se culege cu un eTimer.
#
# Fisierul nu importa nimic din enigma2 la incarcare; toate citirile primesc `radacina`, ca probele de pe PC sa dea un
# receptor fals. HDS_PAZA_RADACINA si HDS_PAZA_STARE sunt numai pentru probe; pe receptor nu le pune nimeni.

import hashlib
import os
import re
import threading

try:
	_
except NameError:
	def _(text):
		return text

FISIER_REGULI = "etc/hdsatelit-model"          # fata de radacina
# versiunea care ruleaza acum (randul version=, build-ul de 16 sau 19 cifre): o scrie pachetul enigma2-hdsatelit, deci
# o actualizare prin pachete o schimba; version= din FISIER_REGULI ramane al imaginii scrise pe receptor (0.6.2)
FISIER_VERSIUNE = "etc/image-version"          # fata de radacina
FISIER_STARE = "/tmp/hds-paza-model.stare"
NUME_MARCAJ = "hdsatelit-model"                # in e2/update/, langa kernel.bin
FORMAT = "1"
DISTRO = "hdsatelit"
MARIME_MAXIMA_TEXT = 16384
OCTETI_ANTET = 4096
DEPLASARE_ETICHETA = 0x3F6000
OCTETI_ETICHETA = 256
BLOC_SUMA = 1024 * 1024

# cheile care hotarasc, in ordinea din mesaj; primele cinci se socotesc si cand regulile sunt stricate
CHEI_AMPRENTA = ("cip", "hw", "partitii", "kernel", "boxtype", "eticheta", "emmc")
CHEI_DE_BAZA = CHEI_AMPRENTA[:5]
# treapta a doua: cheile care dau numai avertisment (la „kernel” numai marimea; locul hotaraste)
CHEI_AVERTISMENT = ("hw", "partitii", "kernel")
# cheia si valoarea care pun regulile in treapta a doua (orice alta valoare, sau lipsa, = treapta intai)
CHEIE_CONFIRMAT = "confirmat"
NECONFIRMAT = "nu"
# cheile obligatorii ale fisierului de reguli si ale marcajului
CHEI_REGULI = ("format", "distro", "model", "machinebuild", "chip", "boxtype", "hw", "partitions", "kernel_part",
	"kernel_kib", "rootfs_part")
CHEI_SUME = ("kernel_sha256", "rootfs_sha256")
FISIERE_SUME = (("kernel_sha256", "kernel.bin"), ("rootfs_sha256", "rootfs.tar.bz2"))

STARE_POTRIVIT = "potrivit"
STARE_NEPOTRIVIT = "nepotrivit"
STARE_NU_SE_APLICA = "nu-se-aplica"

# motivele refuzului unui pachet
PACHET_BUN = "bun"
REFUZ_FARA_MARCAJ = "fara-marcaj"
REFUZ_MARCAJ_STRICAT = "marcaj-stricat"
REFUZ_ALT_RECEPTOR = "alt-receptor"
REFUZ_NECITIT = "necitit"
REFUZ_SUMA = "suma"
REFUZ_SCHIMBAT = "schimbat"

# tipuri de placa din eticheta si un receptor cunoscut de acel tip (oe-alliance, u571.conf); numai pentru mesaj
EXEMPLU_TIP = {"u571": "Amiko Viper 4K V40"}

# memoria interna: limitele pentru regulile care nu le scriu, dupa machinebuild (min_kib, max_kib; None = fara limita)
EMMC_MAXIM_V20_KIB = 5 * 1024 * 1024
EMMC_IMPLICIT = {"viper4kv20": (None, EMMC_MAXIM_V20_KIB)}
# un receptor cunoscut cu memoria interna mai mare / mai mica decat cea ceruta de reguli; numai pentru mesaj
EXEMPLU_EMMC = {("viper4kv20", "mare"): "Amiko Viper 4K V30", ("viper4kv30", "mica"): "Amiko Viper 4K V20"}

_CARACTERE_SIGURE = re.compile(r"[^A-Za-z0-9_.:/ ,()'+-]")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def radacinaImplicita():
	return os.environ.get("HDS_PAZA_RADACINA") or "/"


def caleStare():
	return os.environ.get("HDS_PAZA_STARE") or FISIER_STARE


def _cale(radacina, rel):
	return os.path.join(radacina or radacinaImplicita(), rel)


def _citesteOcteti(cale, maxim, deplasare=0):
	"""cel mult `maxim` octeti de la `deplasare`, sau None daca nu se poate citi (numai citire, O_RDONLY)"""
	try:
		with open(cale, "rb") as f:
			if deplasare:
				f.seek(deplasare)
			return f.read(maxim)
	except (IOError, OSError, ValueError):
		return None


def _citesteText(cale, maxim=MARIME_MAXIMA_TEXT):
	date = _citesteOcteti(cale, maxim)
	if date is None:
		return None
	return date.decode("utf-8", "replace")


def _simplu(text, maxim=32):
	"""numai litere, cifre, _ . - (ca tr -cd in garda din enigma2.sh), cel mult `maxim`"""
	return re.sub(r"[^A-Za-z0-9_.-]", "", text or "")[:maxim]


def curat(text, maxim=80):
	"""textul fara caractere de control sau semne ciudate, taiat; pentru ecran, web si fisierul de stare"""
	return _CARACTERE_SIGURE.sub("", text or "")[:maxim].strip()


# ------------------------------------------------------------------ fisierul de reguli si marcajul pachetului

def cheiValori(text):
	"""{cheie: valoare} din randuri „cheie=valoare”; randurile goale si cele cu # se sar; prima aparitie castiga"""
	rez = {}
	for rand in (text or "").splitlines():
		rand = rand.strip()
		if not rand or rand.startswith("#") or "=" not in rand:
			continue
		cheie, valoare = rand.split("=", 1)
		cheie = cheie.strip()
		if cheie and cheie not in rez:
			rez[cheie] = valoare.strip()
	return rez


def reguliValide(reguli, cu_sume=False):
	"""True daca are toate cheile, formatul si distributia noastra (si sumele, la marcajul pachetului)"""
	if not reguli:
		return False
	for cheie in CHEI_REGULI + (CHEI_SUME if cu_sume else ()):
		if not reguli.get(cheie):
			return False
	if reguli.get("format") != FORMAT or reguli.get("distro") != DISTRO:
		return False
	if partitiiDinReguli(reguli.get("partitions")) is None:
		return False
	if not reguli.get("kernel_kib", "").isdigit():
		return False
	if cu_sume:
		for cheie in CHEI_SUME:
			if not _HEX64.match(reguli.get(cheie, "")):
				return False
	return True


def citesteReguli(radacina=None):
	"""Regulile imaginii care ruleaza, sau None daca fisierul lipseste (paza nu se aplica). Un fisier care exista dar
	nu se intelege da un dict gol: paza se aplica si nimic nu se potriveste."""
	text = _citesteText(_cale(radacina, FISIER_REGULI))
	if text is None:
		return None
	reguli = cheiValori(text)
	return reguli if reguliValide(reguli) else {}


def versiuneAcum(radacina=None):
	"""Versiunea care ruleaza acum, "0.6.1", din etc/image-version (HdsJurnalVersiuni: build_curent si
	versiune_din_build); "" cand fisierul lipseste, are alta forma sau HdsJurnalVersiuni nu se poate incarca (copia
	singura a acestui fisier din scripturile de pregatire). Regulile spun numai imaginea scrisa pe receptor, care nu se
	schimba printr-o actualizare prin pachete."""
	J = None
	try:
		from Components import HdsJurnalVersiuni as J
	except Exception:
		try:
			import importlib.util
			cale = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HdsJurnalVersiuni.py")
			if os.path.exists(cale):
				spec = importlib.util.spec_from_file_location("HdsJurnalVersiuni_paza", cale)
				J = importlib.util.module_from_spec(spec)
				spec.loader.exec_module(J)
		except Exception:
			J = None
	if J is None:
		return ""
	try:
		return J.versiune_din_build(J.build_curent(_cale(radacina, FISIER_VERSIUNE))) or ""
	except Exception:
		return ""


def versiuni(reguli, radacina=None):
	"""(versiunea de acum, imaginea scrisa) pentru texte: versiunea de acum din etc/image-version, altfel cea din
	reguli; imaginea scrisa (version= din reguli) numai cand difera de cea de acum, altfel sirul gol"""
	baza = (reguli or {}).get("version") or ""
	acum = versiuneAcum(radacina) or baza
	return acum, (baza if baza and baza != acum else "")


# ------------------------------------------------------------------ partitiile

def _kib(marime):
	"""'32M' -> 32768, '1024K' -> 1024, '1G' -> 1048576, '512' (octeti) -> 0.5 rotunjit in jos; '-' sau gunoi -> None"""
	m = re.match(r"^(\d+)([KkMmGg]?)$", marime or "")
	if not m:
		return None
	n = int(m.group(1))
	unitate = m.group(2).upper()
	if unitate == "K":
		return n
	if unitate == "M":
		return n * 1024
	if unitate == "G":
		return n * 1024 * 1024
	return n // 1024


def partitiiDinReguli(text):
	"""'boot:1M,...,kernel:32M,rootfs' -> [('boot', 1024), ..., ('kernel', 32768), ('rootfs', None)]; None daca e
	stricat (fara spatii, ca in garda din enigma2.sh)"""
	rez = []
	for bucata in (text or "").split(","):
		if ":" in bucata:
			nume, marime = bucata.split(":", 1)
			kib = _kib(marime)
			if kib is None:
				return None
		else:
			nume, kib = bucata, None
		if not re.match(r"^[A-Za-z0-9_]+$", nume):
			return None
		rez.append((nume, kib))
	return rez or None


def blkdevpartsBrut(cmdline, disc="mmcblk0"):
	"""Partea pentru `disc` din primul cuvant blkdevparts= din /proc/cmdline, ca text („1M(boot),...”), sau "" """
	for cuvant in (cmdline or "").split(" "):
		cuvant = cuvant.strip("\n")
		if not cuvant.startswith("blkdevparts="):
			continue
		for parte in cuvant[len("blkdevparts="):].split(";"):
			if parte.startswith(disc + ":"):
				return parte[len(disc) + 1:]
		return ""
	return ""


def partitiiDinText(brut):
	"""'1M(boot),...,-(others)' -> [(nume, kib sau None pentru „-”)]; None daca lipseste sau o intrare e stricata"""
	if not brut or re.search(r"[^A-Za-z0-9_@(),.-]", brut):
		return None
	rez = []
	for bucata in brut.split(","):
		m = re.match(r"^([0-9]+[KkMmGg]?|-)(?:@[0-9]+[KkMmGg]?)?\(([A-Za-z0-9_]+)\)(ro)?$", bucata)
		if not m:
			return None
		rez.append((m.group(2), None if m.group(1) == "-" else _kib(m.group(1))))
	return rez or None


def partitiiDinCmdline(cmdline, disc="mmcblk0"):
	"""blkdevparts pentru `disc` din /proc/cmdline -> [(nume, kib sau None)], sau None"""
	return partitiiDinText(blkdevpartsBrut(cmdline, disc))


def _indexDeviceinfo(brut):
	"""Locul (de la 1) al primei intrari care contine „(deviceinfo)” in textul blkdevparts, sau None"""
	if not brut or re.search(r"[^A-Za-z0-9_@(),.-]", brut):
		return None
	for i, bucata in enumerate(brut.split(","), 1):
		if "(deviceinfo)" in bucata:
			return i
	return None


def textPartitii(lista):
	"""[(nume, kib)] -> 'boot:1M,...,rootfs:7200M,others:-' (pentru ecran, web si fisierul de stare)"""
	if not lista:
		return ""
	bucati = []
	for nume, kib in lista:
		if kib is None:
			bucati.append("%s:-" % nume)
		elif kib % 1024 == 0:
			bucati.append("%s:%dM" % (nume, kib // 1024))
		else:
			bucati.append("%s:%dK" % (nume, kib))
	return ",".join(bucati)


def _marimiProcPartitions(text):
	"""{nume: kib} din /proc/partitions"""
	rez = {}
	for rand in (text or "").splitlines():
		c = rand.split()
		if len(c) == 4 and c[2].isdigit():
			rez[c[3]] = int(c[2])
	return rez


def _campuriAntet(date):
	"""numai HW= si MAGICNUM= din antetul deviceinfo (restul, cu adresa MAC, nu se pastreaza)"""
	rez = {}
	if not date:
		return rez
	for bucata in re.split(b"[\0\r\n]", date):
		for cheie in (b"HW", b"MAGICNUM"):
			if bucata.startswith(cheie + b"=") and cheie.decode() not in rez:
				valoare = bucata[len(cheie) + 1:]
				m = re.match(b"^[A-Za-z0-9_.-]{1,32}", valoare)
				rez[cheie.decode()] = m.group(0).decode("ascii") if m else ""
	return rez


def _eticheta(date):
	"""'BOX_TYPE:u57 UPD_PATH:/amiko/viper4kv20' din zona etichetei deviceinfo, sau ''"""
	if not date:
		return ""
	i = date.find(b"BOX_TYPE:")
	if i < 0:
		return ""
	bucata = re.split(b"[\0\r\n]", date[i:])[0]
	return curat(bucata.decode("ascii", "replace"), 120)


def _faraGhilimele(text):
	return (text or "").replace("'", "").replace('"', "")


def tipDinEticheta(eticheta):
	"""BOX_TYPE din eticheta, fara ghilimele ('' daca lipseste); aceeasi regula ca in garda din enigma2.sh"""
	m = re.search(r"BOX_TYPE:([^ ]*)", eticheta or "")
	return _faraGhilimele(m.group(1)) if m else ""


def caleDinEticheta(eticheta):
	"""UPD_PATH din eticheta, fara ghilimele ('' daca lipseste)"""
	m = re.search(r"UPD_PATH:([^ ]*)", eticheta or "")
	return _faraGhilimele(m.group(1)) if m else ""


# ------------------------------------------------------------------ amprenta receptorului

def amprentaDinTexte(msp_sys=None, boxtype=None, cmdline=None, partitions=None, antet=None, eticheta=None,
		board_revision=None, compatibil=None, nim_sockets=None):
	"""Amprenta din ce s-a citit (None = necitit). `antet`: primii 4 KiB ai partitiei deviceinfo, ca octeti (se
	pastreaza numai HW= si MAGICNUM=); `eticheta`: cei 256 de octeti de la 0x3F6000 ai aceleiasi partitii;
	`compatibil`: /proc/device-tree/compatible, ca octeti. Folosita de amprenta() si de scripturile de pe PC care
	primesc textele prin ssh (urca-pe-stick). Chei: cip, boxtype, partitii (text), partitii_lista, kernel_part,
	kernel_kib, rootfs_part, rootfs_kib, hw, magicnum, eticheta, board_revision, dt, tunere."""
	a = {}
	a["cip"] = ""
	for rand in (msp_sys or "").split("\n"):
		m = re.match(r"^[ \t\r\f\v]*CHIP_VERSION[ \t\r\f\v]*:[ \t\r\f\v]*([^ \t\r\f\v]*)", rand)
		if m:
			a["cip"] = _simplu(m.group(1))
			break
	a["boxtype"] = _simplu((boxtype or "").split("\n")[0])
	a["board_revision"] = _simplu((board_revision or "").split("\n")[0])
	brut = blkdevpartsBrut(cmdline)
	lista = partitiiDinText(brut)
	a["partitii_lista"] = lista or []
	a["partitii"] = textPartitii(lista)
	marimi = _marimiProcPartitions(partitions)
	nume = [n for n, _k in (lista or [])]
	a["kernel_part"] = ("mmcblk0p%d" % (nume.index("kernel") + 1)) if "kernel" in nume else ""
	a["rootfs_part"] = ("mmcblk0p%d" % (nume.index("rootfs") + 1)) if "rootfs" in nume else ""
	a["kernel_kib"] = marimi.get(a["kernel_part"], "") if a["kernel_part"] else ""
	a["rootfs_kib"] = marimi.get(a["rootfs_part"], "") if a["rootfs_part"] else ""
	a["emmc_kib"] = marimi.get("mmcblk0", "")
	campuri = _campuriAntet(antet) if _indexDeviceinfo(brut) is not None else {}
	a["hw"] = campuri.get("HW", "")
	a["magicnum"] = campuri.get("MAGICNUM", "")
	a["eticheta"] = _eticheta(eticheta) if _indexDeviceinfo(brut) is not None else ""
	a["dt"] = curat(",".join(x.decode("ascii", "replace") for x in (compatibil or b"").split(b"\0") if x), 80)
	tunere = []
	for rand in (nim_sockets or "").splitlines():
		rand = rand.strip()
		if rand.startswith("Name:"):
			tunere.append(curat(rand[5:], 40))
	a["tunere"] = tunere[:8]
	return a


def amprenta(radacina=None):
	"""Ce spune receptorul despre el acum (amprentaDinTexte cu fisierele de sub `radacina`). Valorile care nu se pot
	citi sunt "" (cheile hotaratoare) sau lipsesc. Partitia deviceinfo se ia dupa locul ei in blkdevparts."""
	cmdline = _citesteText(_cale(radacina, "proc/cmdline"), 4096)
	antet = eticheta = None
	di = _indexDeviceinfo(blkdevpartsBrut(cmdline))
	if di is not None:
		dispozitiv = _cale(radacina, "dev/mmcblk0p%d" % di)
		antet = _citesteOcteti(dispozitiv, OCTETI_ANTET)
		eticheta = _citesteOcteti(dispozitiv, OCTETI_ETICHETA, DEPLASARE_ETICHETA)
	return amprentaDinTexte(
		msp_sys=_citesteText(_cale(radacina, "proc/msp/sys")),
		boxtype=_citesteText(_cale(radacina, "proc/stb/info/boxtype"), 4096),
		cmdline=cmdline,
		partitions=_citesteText(_cale(radacina, "proc/partitions"), 65536),
		antet=antet,
		eticheta=eticheta,
		board_revision=_citesteText(_cale(radacina, "proc/stb/info/board_revision"), 64),
		compatibil=_citesteOcteti(_cale(radacina, "proc/device-tree/compatible"), 256),
		nim_sockets=_citesteText(_cale(radacina, "proc/bus/nim_sockets"), 8192))


def amprentaDinStare(st, baza=None):
	"""Amprenta scrisa de garda in fisierul de stare, peste `baza` (amprenta de acum): fiecare cheie scrisa de garda
	(cip, hw, boxtype, partitii, kernel, eticheta) ia valoarea de la pornire; o cheie lipsa din fisier ramane cea de
	acum. Pentru randurile verdictului de la pornire."""
	a = dict(baza or {})
	st = st or {}
	for cheie in ("cip", "hw", "boxtype"):
		if cheie in st:
			a[cheie] = _simplu(st.get(cheie))
	if "partitii" in st:
		lista = partitiiDinText(st.get("partitii", ""))
		a["partitii"] = textPartitii(lista)
		a["partitii_lista"] = lista or []
	if "kernel" in st:
		a["kernel_text"] = curat(st.get("kernel", ""), 120)
	if "eticheta" in st:
		a["eticheta"] = curat(st.get("eticheta", ""), 120)
	if "emmc" in st:
		e = (st.get("emmc") or "").strip()
		a["emmc_kib"] = int(e) if e.isdigit() else ""
	return a


def treapta(reguli):
	"""2 pentru regulile unui model neconfirmat („confirmat=nu”), altfel 1 (si fara reguli)"""
	return 2 if (reguli or {}).get(CHEIE_CONFIRMAT) == NECONFIRMAT else 1


def tipuriPlaca(reguli):
	"""Lista din „boxtype=” („u57” -> ["u57"], „u57,u571” -> ["u57", "u571"]); fara spatii, fara intrari goale"""
	return [t.strip() for t in ((reguli or {}).get("boxtype") or "").split(",") if t.strip()]


def limiteEmmc(reguli):
	"""(min_kib, max_kib) pentru memoria interna (None = fara limita la acel capat), sau None cand nu se verifica.
	Din reguli (emmc_min_kib=, emmc_max_kib=, numai cifre), altfel EMMC_IMPLICIT dupa machinebuild."""
	reguli = reguli or {}
	mic, mare = reguli.get("emmc_min_kib", "").strip(), reguli.get("emmc_max_kib", "").strip()
	mic = int(mic) if mic.isdigit() else None
	mare = int(mare) if mare.isdigit() else None
	if mic is None and mare is None:
		return EMMC_IMPLICIT.get(reguli.get("machinebuild", ""))
	return mic, mare


def textEmmc(kib):
	"""'3748 MiB'; "" pentru o marime necitita"""
	if kib == "" or kib is None:
		return ""
	return "%d MiB" % (int(kib) // 1024)


def _emmcAfara(reguli, kib):
	"""None cand marimea e in limite, nu se verifica sau nu e listata; "mare" / "mica" altfel"""
	lim = limiteEmmc(reguli)
	if lim is None or kib == "" or kib is None:
		return None
	mic, mare = lim
	if mare is not None and int(kib) > mare:
		return "mare"
	if mic is not None and int(kib) < mic:
		return "mica"
	return None


def _diferente(reguli, a):
	"""{cheie: (asteptat, gasit)} pentru fiecare cheie care nu se potriveste, dupa regula treptei intai; la „kernel”
	si „kernel_loc” (numai locul nucleului si al sistemului, fara marime). Regulile trebuie sa fie valide."""
	d = {}
	cip = a.get("cip", "")
	if not cip or cip.lower() != reguli["chip"].lower():
		d["cip"] = (reguli["chip"], cip)
	if not a.get("hw") or a.get("hw") != reguli["hw"]:
		d["hw"] = (reguli["hw"], a.get("hw", ""))
	asteptat = partitiiDinReguli(reguli["partitions"])
	gasit = a.get("partitii_lista") or []
	bune = len(gasit) >= len(asteptat)
	if bune:
		for (n1, k1), (n2, k2) in zip(asteptat, gasit):
			if n1 != n2 or (k1 is not None and k1 != k2):
				bune = False
				break
	if not bune:
		d["partitii"] = (reguli["partitions"], a.get("partitii", ""))
	kp = a.get("kernel_part") or ""
	rp = a.get("rootfs_part") or ""
	kib = a.get("kernel_kib", "")
	loc_bun = kp == reguli["kernel_part"] and rp == reguli["rootfs_part"] and str(kib) != "" and \
		a.get("rootfs_kib", "") != ""
	if not loc_bun or str(kib) != reguli["kernel_kib"]:
		d["kernel"] = (asteptat_text(reguli, "kernel"), textKernel(kp, kib, rp))
	if not loc_bun:
		d["kernel_loc"] = d["kernel"]
	tipuri = tipuriPlaca(reguli)
	if not a.get("boxtype") or a.get("boxtype") not in tipuri:
		d["boxtype"] = (reguli["boxtype"], a.get("boxtype", ""))
	tip = tipDinEticheta(a.get("eticheta"))
	if tip and tip not in tipuri:
		d["eticheta"] = (reguli["boxtype"], tip)
	if _emmcAfara(reguli, a.get("emmc_kib", "")):
		d["emmc"] = (asteptat_text(reguli, "emmc"), textEmmc(a.get("emmc_kib", "")))
	return d


def compara(reguli, a):
	"""[(cheie, asteptat, gasit)] pentru fiecare cheie hotaratoare care nu se potriveste; "" la gasit = necitit.
	In treapta a doua hotarasc numai cipul, tipul placii, eticheta si locul nucleului si al sistemului."""
	if not reguliValide(reguli):
		return [(c, "", valoareGasita(a, c)) for c in CHEI_DE_BAZA]
	d = _diferente(reguli, a)
	if treapta(reguli) == 2:
		chei = [c for c in CHEI_AMPRENTA if c not in CHEI_AVERTISMENT or (c == "kernel" and "kernel_loc" in d)]
	else:
		chei = CHEI_AMPRENTA
	return [(c,) + d[c] for c in chei if c in d]


def avertismente(reguli, a):
	"""[(cheie, asteptat, gasit)] pentru ce nu se potriveste, dar nu opreste nimic: numai in treapta a doua, cand
	locul nucleului si al sistemului e bun (placa, tabela partitiilor, marimea nucleului); altfel []"""
	if not reguliValide(reguli) or treapta(reguli) != 2:
		return []
	d = _diferente(reguli, a)
	return [(c,) + d[c] for c in CHEI_AVERTISMENT if c in d and not (c == "kernel" and "kernel_loc" in d)]


def textKernel(kernel_part, kernel_kib, rootfs_part):
	"""'mmcblk0p9 32768 KiB, mmcblk0p10'; "" daca partitia nucleului nu s-a gasit (necitit)"""
	if not kernel_part:
		return ""
	return "%s %s KiB, %s" % (kernel_part, kernel_kib if kernel_kib != "" else "?", rootfs_part or "-")


def valoareGasita(a, cheie):
	"""Valoarea citita pentru o cheie hotaratoare, ca text ("" = necitit; la eticheta, "" = fara eticheta)"""
	if cheie == "kernel":
		if "kernel_text" in a:
			return a["kernel_text"]
		return textKernel(a.get("kernel_part") or "", a.get("kernel_kib", ""), a.get("rootfs_part") or "")
	if cheie == "eticheta":
		return tipDinEticheta(a.get("eticheta"))
	if cheie == "emmc":
		return textEmmc(a.get("emmc_kib", ""))
	return a.get(cheie, "") or ""


def asteptat_text(reguli, cheie):
	"""Valoarea asteptata a unei chei hotaratoare, ca text"""
	if not reguli:
		return ""
	if cheie == "cip":
		return reguli.get("chip", "")
	if cheie == "partitii":
		return reguli.get("partitions", "")
	if cheie == "kernel":
		return textKernel(reguli.get("kernel_part", ""), reguli.get("kernel_kib", ""), reguli.get("rootfs_part", ""))
	if cheie == "eticheta":
		return reguli.get("boxtype", "")
	if cheie == "emmc":
		lim = limiteEmmc(reguli)
		if lim is None:
			return ""
		mic, mare = lim
		if mic is not None and mare is not None:
			return "%s - %s" % (textEmmc(mic), textEmmc(mare))
		if mare is not None:
			return _("cel mult %s") % textEmmc(mare)
		return _("cel puțin %s") % textEmmc(mic)
	return reguli.get(cheie, "")


def verifica(radacina=None, reguli=None):
	"""{stare, reguli, amprenta, nepotriviri, avertismente, treapta}. stare: STARE_NU_SE_APLICA fara fisierul de
	reguli, altfel STARE_POTRIVIT sau STARE_NEPOTRIVIT."""
	if reguli is None:
		reguli = citesteReguli(radacina)
	if reguli is None:
		return {"stare": STARE_NU_SE_APLICA, "reguli": None, "amprenta": {}, "nepotriviri": [], "avertismente": [],
			"treapta": 1, "versiune": "", "versiune_baza": ""}
	a = amprenta(radacina)
	nepotriviri = compara(reguli, a)
	acum, baza = versiuni(reguli, radacina)
	return {"stare": STARE_NEPOTRIVIT if nepotriviri else STARE_POTRIVIT, "reguli": reguli, "amprenta": a,
		"nepotriviri": nepotriviri, "avertismente": [] if nepotriviri else avertismente(reguli, a),
		"treapta": treapta(reguli), "versiune": acum, "versiune_baza": baza}


# ------------------------------------------------------------------ verdictul de la pornire

def stareaPornirii(cale=None):
	"""Fisierul scris de garda din enigma2.sh ({cheie: valoare}), sau None daca nu exista"""
	text = _citesteText(cale or caleStare(), 4096)
	if text is None:
		return None
	return cheiValori(text)


def _stareValida(st):
	return bool(st) and st.get("stare") in (STARE_POTRIVIT, STARE_NEPOTRIVIT)


def verdict(radacina=None, cale_stare=None):
	"""Verdictul pentru interfata, dict-ul lui verifica() plus:
	- „sursa”: pornire (fisierul garzii) sau acum (fara fisier: comparatia de acum);
	- „amprenta_verdict”: amprenta dupa care s-a dat verdictul (la pornire, cea din fisierul garzii);
	- „nepotriviri_acum”: ce nu se potriveste citit acum (poate diferi de pornire, de exemplu un driver cazut).
	Cu verdictul de la pornire, starea si „nepotriviri” vin numai din fisierul garzii, ca ecranul si pagina web sa nu se
	contrazica; „amprenta” ramane cea de acum (pentru ce se arata numai informativ)."""
	v = verifica(radacina)
	v["sursa"] = "acum"
	v["amprenta_verdict"] = v["amprenta"]
	v["nepotriviri_acum"] = list(v["nepotriviri"])
	if v["stare"] == STARE_NU_SE_APLICA:
		return v
	st = stareaPornirii(cale_stare)
	if not _stareValida(st):
		return v
	a_p = amprentaDinStare(st, v["amprenta"])
	v["sursa"] = "pornire"
	v["stare"] = st["stare"]
	v["amprenta_verdict"] = a_p
	if st["stare"] == STARE_POTRIVIT:
		v["nepotriviri"] = []
		# avertismentele treptei a doua, tot din fisierul garzii (numai cand regulile sunt in treapta a doua)
		chei = [c for c in (st.get("avertismente") or "").split() if c in CHEI_AVERTISMENT] \
			if treapta(v["reguli"]) == 2 else []
		v["avertismente"] = [(c, asteptat_text(v["reguli"], c), valoareGasita(a_p, c)) for c in chei]
	else:
		chei = [c for c in (st.get("nepotriviri") or "").split() if c in CHEI_AMPRENTA] or ["cip"]
		v["nepotriviri"] = [(c, asteptat_text(v["reguli"], c), valoareGasita(a_p, c)) for c in chei]
		v["avertismente"] = []
	return v


def inPaza(radacina=None, cale_stare=None):
	"""True cand interfata trebuie sa arate numai mesajul (alt receptor, sau amprenta necitita). Citeste numai regulile
	si verdictul garzii; amprenta se citeste numai cand verdictul lipseste."""
	try:
		reguli = citesteReguli(radacina)
		if reguli is None:
			return False
		st = stareaPornirii(cale_stare)
		if _stareValida(st):
			return st["stare"] == STARE_NEPOTRIVIT
		return verifica(radacina, reguli)["stare"] == STARE_NEPOTRIVIT
	except Exception as eroare:
		print("[HdsPazaModel] verdictul: %s" % eroare)
		return False


# ------------------------------------------------------------------ textele

def numeReceptor(a, reguli=None, nepotriviri=None):
	"""Numele receptorului pentru fraza simpla, dupa eticheta din deviceinfo (nu e dovada: se arata numai pe o
	nepotrivire). UPD_PATH /amiko/viper4kvNN (cu sau fara ghilimele) da numele; altfel un BOX_TYPE diferit de regula
	da „un receptor <tip>” (cu un exemplu, cand il stim). O eticheta cu numele din reguli nu se crede (o imagine de-a
	noastra pornita inainte pe alt receptor o rescrie asa). Eticheta bruta nu intra niciodata aici (randurile tehnice)."""
	eticheta = a.get("eticheta") or ""
	m = re.match(r"^/?amiko/viper4kv(\d+)/?$", caleDinEticheta(eticheta))
	nume = ("Amiko Viper 4K V%s" % m.group(1)) if m else ""
	if nume and not (reguli and nume == reguli.get("model")):
		return nume
	tip = tipDinEticheta(eticheta)
	if tip and not (reguli and tip in tipuriPlaca(reguli)):
		if tip in EXEMPLU_TIP:
			return _("un receptor %(tip)s (de exemplu %(model)s)") % {"tip": tip, "model": EXEMPLU_TIP[tip]}
		return _("un receptor %s") % tip
	# acelasi tip de placa, dar alta memorie interna (de pilda un Amiko Viper 4K V30 cu imaginea pentru V20)
	if nepotriviri and "emmc" in [n[0] for n in nepotriviri]:
		afara = _emmcAfara(reguli, a.get("emmc_kib", ""))
		model = EXEMPLU_EMMC.get(((reguli or {}).get("machinebuild", ""), afara))
		if afara == "mare":
			return (_("un receptor cu memoria internă mai mare (de exemplu %s)") % model) if model else \
				_("un receptor cu memoria internă mai mare")
		if afara == "mica":
			return (_("un receptor cu memoria internă mai mică (de exemplu %s)") % model) if model else \
				_("un receptor cu memoria internă mai mică")
	return _("model necunoscut")


def numeDinEticheta(a, reguli=None):
	"""True daca eticheta numeste un model Amiko Viper 4K (UPD_PATH /amiko/viper4kvNN): atunci eticheta bruta nu mai
	trebuie aratata (numele e in fraza simpla, sau e chiar numele nostru, scris de o imagine de-a noastra)"""
	return bool(re.match(r"^/?amiko/viper4kv(\d+)/?$", caleDinEticheta(a.get("eticheta"))))


def textPentru(reguli, versiune=None):
	""""Acest software (HD Satelit 0.1.6) este pentru receptorul ...". `versiune` = cea care ruleaza acum (verifica():
	"versiune", din etc/image-version); fara ea, version= din reguli (imaginea scrisa, care ramane aceeasi dupa o
	actualizare prin pachete: dupa 0.6.1 pagina spunea inca 0.6.0)"""
	valori = {"model": reguli.get("model") or "?", "hw": reguli.get("hw") or "?", "cip": reguli.get("chip") or "?"}
	versiune = versiune or reguli.get("version")
	if versiune:
		valori["versiune"] = versiune
		return _("Acest software (HD Satelit %(versiune)s) este pentru receptorul %(model)s (placa %(hw)s, procesor "
			"%(cip)s).") % valori
	return _("Acest software este pentru receptorul %(model)s (placa %(hw)s, procesor %(cip)s).") % valori


def textPentruPachet(marcaj):
	"""„Acest pachet (HD Satelit 0.1.6) este pentru receptorul ...” (refuzul unui pachet pentru alt receptor)"""
	valori = {"model": marcaj.get("model") or "?", "hw": marcaj.get("hw") or "?", "cip": marcaj.get("chip") or "?",
		"versiune": marcaj.get("version") or "?"}
	return _("Acest pachet (HD Satelit %(versiune)s) este pentru receptorul %(model)s (placa %(hw)s, procesor "
		"%(cip)s).") % valori


def textAlTau(a, reguli=None, nepotriviri=None):
	"""„Receptorul tău: ...”"""
	return _("Receptorul tău: %(model)s, placa %(hw)s, procesor %(cip)s.") % {
		"model": numeReceptor(a, reguli, nepotriviri),
		"hw": a.get("hw") or _("necunoscută"),
		"cip": a.get("cip") or _("necunoscut")}


def eticheteAmprenta():
	"""{cheie hotaratoare: numele ei pentru om}, pentru ecran si pentru web"""
	return {
		"cip": _("Procesorul"),
		"hw": _("Placa (antetul partiției deviceinfo)"),
		"partitii": _("Partițiile din memorie"),
		"kernel": _("Partițiile nucleului și ale sistemului"),
		"boxtype": _("Tipul plăcii spus de driver"),
		"eticheta": _("Tipul plăcii din eticheta receptorului"),
		"emmc": _("Memoria internă (eMMC)"),
	}


def primaDiferentaKernel(asteptat, gasit):
	"""(asteptat, gasit) scurtate la prima parte care difera din doua texte „mmcblk0p9 32768 KiB, mmcblk0p10”: nucleul
	(partitia si marimea), altfel partitia sistemului; textele intregi daca nu se vede nicio diferenta"""
	def parti(text):
		nucleu, _v, sistem = (text or "").partition(", ")
		return nucleu, sistem
	na, sa = parti(asteptat)
	ng, sg = parti(gasit)
	if na != ng:
		return na, ng
	if sa != sg:
		return sa, sg or "-"
	return asteptat, gasit


def randuriTehnice(nepotriviri):
	"""Cate un rand pentru fiecare nepotrivire (se arata mai mic, dupa fraza simpla)"""
	etichete = eticheteAmprenta()
	randuri = []
	for cheie, asteptat, gasit in nepotriviri:
		ce = etichete.get(cheie, cheie)
		if not gasit:
			randuri.append(_("%(ce)s: așteptat %(asteptat)s, dar nu s-a putut citi.") % {
				"ce": ce, "asteptat": asteptat or "?"})
			continue
		if cheie == "partitii" and asteptat:
			loc, asteptat, gasit = primaDiferenta(asteptat, gasit)
			randuri.append(_("%(ce)s: pe locul %(loc)d așteptat %(asteptat)s, găsit %(gasit)s.") % {
				"ce": ce, "loc": loc, "asteptat": asteptat, "gasit": gasit})
			continue
		if cheie == "kernel" and asteptat:
			asteptat, gasit = primaDiferentaKernel(asteptat, gasit)
		randuri.append(_("%(ce)s: așteptat %(asteptat)s, găsit %(gasit)s.") % {
			"ce": ce, "asteptat": asteptat or "?", "gasit": gasit})
	return randuri


def primaDiferenta(asteptat, gasit):
	"""(locul de la 1, intrarea asteptata, intrarea gasita) la prima partitie care nu se potriveste, din doua liste
	„nume:marime,...” (o intrare asteptata fara marime primeste orice marime); pe ecran, in locul listelor intregi"""
	a = asteptat.split(",")
	g = gasit.split(",")
	for i, intrare in enumerate(a):
		gi = g[i] if i < len(g) else ""
		if gi == intrare or (":" not in intrare and gi.split(":", 1)[0] == intrare):
			continue
		return i + 1, intrare, gi or _("nimic")
	return len(a), a[-1] if a else "?", g[len(a) - 1] if 0 < len(a) <= len(g) else _("nimic")


def necitit(nepotriviri):
	"""True daca o nepotrivire vine numai din ce nu s-a putut citi"""
	return bool(nepotriviri) and all(not gasit for _c, _a, gasit in nepotriviri)


def randEticheta(a, reguli=None):
	"""Randul tehnic cu eticheta bruta, cand exista si nu numeste un model Amiko Viper 4K (altfel [])"""
	eticheta = a.get("eticheta") or ""
	if not eticheta or numeDinEticheta(a, reguli):
		return []
	return [_("Eticheta din memoria receptorului: %s") % eticheta]


def mesajPornire(v):
	"""(titlu, [fraze simple], [randuri tehnice]) pentru ecranul de pe televizor si pentru web; amprenta e cea dupa care
	s-a dat verdictul"""
	reguli = v.get("reguli") or {}
	a = v.get("amprenta_verdict") or v.get("amprenta") or {}
	nep = v.get("nepotriviri") or []
	if necitit(nep):
		titlu = _("Receptorul nu poate fi recunoscut")
		fraze = [_("Nu am putut citi procesorul sau partițiile receptorului, deci nu se poate dovedi că acest software "
			"este pentru el."), textPentru(reguli, v.get("versiune"))]
		tehnice = randuriTehnice(nep)
	else:
		titlu = _("Software pentru alt receptor")
		fraze = [textPentru(reguli, v.get("versiune")), textAlTau(a, reguli, nep)]
		tehnice = randuriTehnice(nep) + randEticheta(a, reguli)
	fraze.append(_("Ca să nu strice receptorul, software-ul nu scrie nimic în memoria lui și nu pornește mai departe."))
	fraze.append(_("Pune la loc software-ul potrivit cu un stick USB, cum arată producătorul receptorului "
		"(la Amiko: Maintenance Mode)."))
	return titlu, fraze, tehnice


def mesajNeconfirmat(v):
	"""(titlu, [fraze], [randuri tehnice]) pentru un model neconfirmat (treapta a doua) care a trecut paza: interfata
	porneste; randurile tehnice sunt avertismentele (valorile citite care difera de cele asteptate)"""
	reguli = v.get("reguli") or {}
	return (_("Model neconfirmat: software pentru testeri"), [textPentru(reguli, v.get("versiune")),
		_("Modelul acesta nu este încă confirmat pe un receptor adevărat. Software-ul pornește, dar e numai pentru "
			"testeri: trimite-ne valorile de mai jos sau fișa receptorului, ca să îl putem confirma.")],
		randuriTehnice(v.get("avertismente") or []))


def mesajStare(v):
	"""(titlu, [fraze], [randuri tehnice]) pentru orice stare (pagina web o arata si pe receptorul potrivit)"""
	if v.get("stare") == STARE_NEPOTRIVIT:
		return mesajPornire(v)
	if v.get("stare") == STARE_POTRIVIT and treapta(v.get("reguli")) == 2:
		return mesajNeconfirmat(v)
	if v.get("stare") == STARE_POTRIVIT:
		return (_("Receptorul este cel potrivit"), [textPentru(v.get("reguli") or {}, v.get("versiune")),
			_("Receptorul acesta se potrivește: procesorul, placa și partițiile sunt cele cerute de software.")], [])
	return (_("Paza de model nu se aplică aici"), [_("Software-ul care rulează nu are semnul receptorului (de exemplu "
		"în emulatorul de pe calculator), deci paza de model nu verifică nimic.")], [])


def notaNeconfirmat(radacina=None, cale_stare=None):
	"""Textul notei de la pornire pentru un model neconfirmat care a trecut paza (titlul pe primul rand, frazele,
	apoi randurile tehnice), sau None (model confirmat, alt receptor, fara reguli). Pentru mytest.py."""
	reguli = citesteReguli(radacina)
	if not reguli or treapta(reguli) != 2:
		return None
	v = verdict(radacina, cale_stare)
	if v.get("stare") != STARE_POTRIVIT:
		return None
	titlu, fraze, tehnice = mesajNeconfirmat(v)
	return "\n\n".join([titlu] + fraze + (["\n".join(tehnice)] if tehnice else []))


def randuriAcum(v):
	"""Randurile tehnice pentru ce se citeste acum altfel decat la pornire ([] cand e la fel sau fara verdict de la
	pornire); pagina web le arata separat, sub „Citit acum”"""
	if v.get("sursa") != "pornire":
		return []
	pornire = [c for c, _a, _g in v.get("nepotriviri") or []]
	acum = v.get("nepotriviri_acum") or []
	if [c for c, _a, _g in acum] == pornire:
		return []
	if not acum:
		return [_("Acum toate valorile se potrivesc.")]
	return randuriTehnice(acum)


# ------------------------------------------------------------------ pachetul de actualizare

def verificaPachet(text_marcaj, radacina=None, a=None):
	"""Marcajul pachetului fata de receptorul acesta, fara sume (repede, pe firul enigma2). `a` e amprenta data (o
	singura citire pentru toate pachetele listei; scripturile de pe PC o citesc prin ssh); fara ea se citeste acum de
	sub `radacina`. Intoarce (cod, text pentru om, marcajul ca dict). cod = PACHET_BUN sau REFUZ_*."""
	if text_marcaj is None:
		return REFUZ_FARA_MARCAJ, textRefuz(REFUZ_FARA_MARCAJ), {}
	marcaj = cheiValori(text_marcaj)
	if not reguliValide(marcaj, cu_sume=True):
		return REFUZ_MARCAJ_STRICAT, textRefuz(REFUZ_MARCAJ_STRICAT), marcaj
	if a is None:
		a = amprenta(radacina)
	nep = compara(marcaj, a)
	if nep:
		cod = REFUZ_NECITIT if necitit(nep) else REFUZ_ALT_RECEPTOR
		return cod, textRefuz(cod, marcaj, a, nep), marcaj
	return PACHET_BUN, "", marcaj


def textRefuz(cod, marcaj=None, a=None, nepotriviri=None, fisier=None):
	"""Textul refuzului unui pachet; paragraful simplu se termina mereu cu „Nu s-a scris nimic pe receptor.”, iar
	randurile tehnice (daca sunt) vin dupa un rand gol. `fisier`: un nume sau o lista de nume (la REFUZ_SUMA)."""
	nimic = _("Nu s-a scris nimic pe receptor.")
	if cod == REFUZ_FARA_MARCAJ:
		t = _("Din pachet lipsește semnul receptorului, deci nu se poate verifica pentru ce receptor este. Îl au "
			"pachetele HD Satelit de la versiunea 0.1.6; o versiune mai veche sau o imagine de la altcineva se scrie "
			"numai cu un stick USB, cum arată producătorul receptorului.")
	elif cod == REFUZ_MARCAJ_STRICAT:
		t = _("Semnul receptorului din pachet este stricat sau de altă versiune, deci nu se poate verifica pentru ce "
			"receptor este pachetul.")
	elif cod == REFUZ_ALT_RECEPTOR:
		t = textPentruPachet(marcaj or {}) + "\n" + textAlTau(a or {}, marcaj, nepotriviri)
	elif cod == REFUZ_NECITIT:
		t = _("Nu am putut citi procesorul sau partițiile receptorului, deci nu se poate dovedi că pachetul este "
			"pentru el.")
	elif cod == REFUZ_SUMA:
		nume = [fisier] if isinstance(fisier, str) else list(fisier or [])
		if len(nume) > 1:
			t = _("Pachetul este stricat sau schimbat: %s nu au suma de control din semnul pachetului. Copiază din nou "
				"pachetul pe stick.") % ", ".join(nume)
		else:
			t = _("Pachetul este stricat sau schimbat: %s nu are suma de control din semnul pachetului. Copiază din nou "
				"pachetul pe stick.") % (nume[0] if nume else "?")
	elif cod == REFUZ_SCHIMBAT:
		t = _("Fișierele pachetului s-au schimbat după verificare. Verifică din nou pachetul.")
	else:
		t = ""
	t = (t + "\n" + nimic) if t else nimic
	if nepotriviri and cod in (REFUZ_ALT_RECEPTOR, REFUZ_NECITIT):
		tehnice = randuriTehnice(nepotriviri)
		if cod == REFUZ_ALT_RECEPTOR:
			tehnice += randEticheta(a or {}, marcaj)
		t += "\n\n" + "\n".join(tehnice)
	return t


def scurtRefuz(cod):
	"""Cateva cuvinte pentru randul pachetului din lista (refuzurile incep toate cu „nu se scrie”)"""
	if cod == PACHET_BUN:
		return _("pentru acest receptor, se verifică la OK")
	if cod == REFUZ_FARA_MARCAJ:
		return _("nu se scrie: fără semnul receptorului")
	if cod == REFUZ_ALT_RECEPTOR:
		return _("nu se scrie: pentru alt receptor")
	if cod == REFUZ_MARCAJ_STRICAT:
		return _("nu se scrie: semnul pachetului e stricat")
	if cod in (REFUZ_SUMA, REFUZ_SCHIMBAT):
		return _("nu se scrie: pachet stricat sau schimbat")
	return _("nu se scrie: receptorul nu se poate verifica")


def randSusRefuz(cod):
	"""Randul de sus al ecranului de actualizare dupa un refuz: „Nu se scrie: ... Nu s-a scris nimic pe receptor.”"""
	scurt = scurtRefuz(cod)
	return "%s%s. %s" % (scurt[:1].upper(), scurt[1:], _("Nu s-a scris nimic pe receptor."))


def sumeSha256(dosar, oprit=None):
	"""{cheie_suma: hex} pentru kernel.bin si rootfs.tar.bz2 din `dosar` (citire in bucati de 1 MiB; pe un fir separat,
	hashlib elibereaza GIL-ul). `oprit` e o functie: True = se renunta (intoarce None)."""
	rez = {}
	for cheie, nume in FISIERE_SUME:
		h = hashlib.sha256()
		with open(os.path.join(dosar, nume), "rb") as f:
			while True:
				if oprit is not None and oprit():
					return None
				bucata = f.read(BLOC_SUMA)
				if not bucata:
					break
				h.update(bucata)
		rez[cheie] = h.hexdigest()
	return rez


def sumeGresite(marcaj, sume):
	"""Numele fisierelor ale caror sume nu sunt cele din marcaj (lista goala = toate bune)"""
	gresite = []
	for cheie, nume in FISIERE_SUME:
		if not sume or sume.get(cheie) != (marcaj or {}).get(cheie):
			gresite.append(nume)
	return gresite


def semnFisiere(dosar):
	"""(marime, mtime) pentru kernel.bin, rootfs.tar.bz2 si marcaj; None la un fisier lipsa. Se compara inainte de
	scriere cu cel luat la verificarea sumelor."""
	semn = []
	for nume in ("kernel.bin", "rootfs.tar.bz2", NUME_MARCAJ):
		try:
			st = os.stat(os.path.join(dosar, nume))
			semn.append((nume, st.st_size, int(st.st_mtime)))
		except OSError:
			semn.append((nume, None, None))
	return tuple(semn)


class LucrareFundal(object):
	"""functie() pe un fir separat; la_sfarsit(rezultat, eroare) pe firul enigma2, cules de un eTimer la 100 ms.
	Apelantul tine obiectul in viata pana la sfarsit (altfel eTimer-ul e cules)."""

	def __init__(self, functie, la_sfarsit, interval_ms=100):
		from enigma import eTimer
		self._rez = {}
		self._oprit = False
		self._la_sfarsit = la_sfarsit
		self._ceas = eTimer()
		try:
			self._legatura = self._ceas.timeout.connect(self._verifica)
		except AttributeError:
			self._ceas.callback.append(self._verifica)
		fir = threading.Thread(target=self._ruleaza, args=(functie,), name="HdsPazaModel")
		fir.daemon = True
		fir.start()
		self._ceas.start(interval_ms, False)

	def oprit(self):
		return self._oprit

	def _ruleaza(self, functie):
		try:
			self._rez["r"] = functie()
		except Exception as eroare:
			self._rez["e"] = str(eroare) or eroare.__class__.__name__
		self._rez["gata"] = True

	def _verifica(self):
		if not self._rez.get("gata"):
			return
		self._ceas.stop()
		la_sfarsit, self._la_sfarsit = self._la_sfarsit, None
		if la_sfarsit is not None:
			la_sfarsit(self._rez.get("r"), self._rez.get("e"))

	def opreste(self):
		"""Rezultatul nu mai e dorit; firul se opreste la urmatoarea bucata citita."""
		self._oprit = True
		self._la_sfarsit = None
		self._ceas.stop()
