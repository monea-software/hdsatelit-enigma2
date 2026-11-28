# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPornireStick.py: pornirea multipla de pe stick a receptoarelor ZGEMMA H8.2H Plus (h8) si H8.2H SE (h8se), fara ecran.
# Il folosesc ecranul Screens/HdsPornireMultipla.HdsPornireStick (Meniu > Standby si repornire > Imagini pe stick) si
# cardul "stick" din pagina web /alimentare (HdsWebControl/alimentare_web.py), deci amandoua arata si fac la fel.
# (MB1, 27.11.2026; Eduard 19:47: „sa il faci inainte de lansare”.)
#
# Cum porneste receptorul (dovedit de USB1 pe .129 in 27.11, nimic scris pe mtd0-8): nucleul din mtd8 are un initramfs
# OE-Alliance (acelasi /init pe h8 si h8se) care la fiecare pornire cauta sda..sdd cu p1 FAT si p2 ext4 cu eticheta
# "rootfs", citeste STARTUP de pe p1 (numai root=, rootsubdir= si rootfstype=) si porneste <p2>/linuxrootfsN. Cand
# subdosarul lipseste sau n-are sbin/init, porneste singur memoria interna (ubi0:rootfs). Cand a pornit un loc, copiaza
# el insusi STARTUP_N peste STARTUP. Nu stie de STARTUP_ONCE.
#   p1 (FAT, "STARTUP"):  STARTUP, STARTUP_1..9 (root=UUID=<p2> rootsubdir=linuxrootfsN rootfstype=ext4), STARTUP_FLASH
#   p2 (ext4, "rootfs"):  linuxrootfs1..9, cate o imagine in fiecare
#   p3 (swap):            pornit singur de Components/HdsSwap.py
# Pe stick /proc/cmdline ramane root=ubi0:rootfs: locul pornit se citeste din /proc/self/mountinfo (randul radacinii are
# campul root /linuxrootfsN pe partitia ext4), memoria interna din radacina ubifs.
#
# Ce face (fiecare intoarce (bun, textul pentru om)):
#   locuri()          memoria interna + linuxrootfsN de pe stick, cu numele si versiunea citite din dosarul fiecaruia;
#   alege(loc, o_data) STARTUP = STARTUP_N (sau STARTUP_FLASH); "o data": pornirea urmatoare in loc, apoi inapoi la cel
#                     implicit (marcajul STARTUP.hds-o-data pe p1, pus la loc de scriptul rcS pus in locul ales sau, pentru
#                     memoria interna, de laPornire() din mytest.py);
#   lucrari lungi pe un fir (una odata, starea in LUCRAREA): pregatesteStick (sterge stickul: p1 FAT 32 MiB, p2 ext4
#                     "rootfs", p3 swap 1 GB; numai din memoria interna), instaleaza (din feedul nostru, dintr-un zip de pe
#                     stick sau dintr-o adresa, cu sau fara setarile de acum), stergeLoc. Arhivele altor echipe care au
#                     numai rootfs.ubi (imaginea pentru memoria interna) le desface Components/HdsCititorUbi.py intr-un
#                     proces separat; la imaginile straine pregatesteStraina() pune driverele h8, "hold" pe pachetele
#                     care pot scrie nucleul sau partitiile de pornire si setarile tunerului (MB3, 27.11.2026).
# Nu se scrie niciodata pe mtd0-mtd8 si nici pe memoria interna; numai pe stick.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau `radacina` (un receptor fals) si `ruleaza`.

import os
import re
import shutil
import subprocess
import threading
import time

MASINI = ("h8", "h8se")
FLASH = "flash"
LOCURI_MAXIM = 9
STARTUP = "STARTUP"
STARTUP_FLASH = "STARTUP_FLASH"
COPIE = "STARTUP.hds-inainte"
O_DATA = "STARTUP.hds-o-data"
ABSENT = b"HDS-FARA-STARTUP\n"
TEXT_FLASH = "kernel=/dev/%s ubi.mtd=rootfs root=ubi0:rootfs flash=1 rootfstype=ubifs\n"
TEXT_LOC = "kernel=/dev/%s root=UUID=%s rootsubdir=linuxrootfs%s rootfstype=ext4\n"
SCRIPT_O_DATA = "etc/init.d/hds-o-data"
LEGATURA_O_DATA = "etc/rcS.d/S03hds-o-data"
DOSAR_ZIP = "hdsatelit/imagini-stick"
SWAP_MB = 1024
MINIM_SWAP_GB = 8
RX_LOC = re.compile(r"^linuxrootfs([1-9])$")
RX_DISC = re.compile(r"^sd[a-d]$")
RX_UUID = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
RX_ADRESA = re.compile(r"^https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/\S*$")
BLOC = 1024 * 1024
UA = "hdsatelit-receptor/1"


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la folosire."""
	return text


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


TITLU = N_("Imagini pe stick")
CAUT = N_("Caut imaginile de pe stick...")
FLASH_NUME = N_("Memoria internă")
LOC_NUME = N_("Locul %s pe stick")
ACUM = N_("pornită acum")
IMPLICIT = N_("pornește de obicei")
O_DATA_SEMN = N_("pornește o dată la următoarea repornire")
STRICAT = N_("nu poate porni")
FARA_NUME = N_("Imagine fără nume")
NOTA = N_("OK: pornește imaginea de acum înainte. GALBEN: o singură dată, apoi revine cea de obicei. ALBASTRU: șterge "
	"locul. MENU: pune o imagine nouă sau pregătește stickul.")
FARA_STICK = N_("Nu e pus un stick pregătit pentru mai multe imagini. Pune stickul și apasă MENU > Pregătește stickul.")
PREGATIT_INFO = N_("Pe stick: %(locuri)d locuri ocupate din %(maxim)d, %(liber)s liberi.")
INTREBARE = N_("Receptorul repornește în %s. Continui?")
INTREBARE_O_DATA = N_("Receptorul repornește o singură dată în %s, apoi revine la cea de obicei. Continui?")
INTREBARE_PREGATIRE = N_("Șterg TOT de pe stickul %(disc)s (%(marime)s) și îl pregătesc pentru mai multe imagini? Ce e "
	"pe el se pierde.")
DEJA = N_("Aceasta e imaginea pornită acum.")
NU_PORNESTE = N_("Imaginea din locul %s nu poate porni (lipsește sistemul), deci nu o aleg.")
NEGASIT = N_("Locul ales nu mai e pe stick. Deschide din nou lista.")
EROARE = N_("Nu am putut scrie pe stick, deci receptorul rămâne cum era.")
GATA_DE_ACUM = N_("Receptorul repornește în %s și o va porni de acum înainte.")
GATA_O_DATA = N_("Receptorul repornește o singură dată în %s.")
RAMANE = N_("%s pornește de acum înainte, și după repornire.")
OCUPAT = N_("Lucrez deja la stick. Așteaptă să termin.")
PREGATESTE_DIN_FLASH = N_("Stickul se pregătește din imaginea din memoria internă. Pornește întâi memoria internă.")
DISC_NECUNOSCUT = N_("Nu găsesc stickul ales. Pune-l din nou și încearcă iar.")
DISC_FOLOSIT = N_("Stickul e folosit acum și nu se poate șterge. Repornește receptorul și încearcă din nou.")
PREGATESC = N_("Pregătesc stickul...")
PREGATIT = N_("Stickul e gata. Acum poți pune imagini pe el.")
PREGATIRE_ESUATA = N_("Pregătirea stickului nu a reușit: %s")
NICIUN_DISC = N_("Nu găsesc niciun stick pus în receptor.")
FARA_LOC_LIBER = N_("Toate cele %d locuri de pe stick sunt ocupate. Șterge întâi un loc.")
LOC_OCUPAT = N_("Locul %s e deja ocupat. Șterge-l întâi sau alege alt loc.")
DESCARC = N_("Descarc imaginea... %s")
DESPACHETEZ = N_("Pun imaginea în locul %(loc)s... %(cat)s")
COPIEZ_SETARI = N_("Copiez setările de acum...")
INSTALAT = N_("Gata: %(imagine)s e în locul %(loc)s. O pornești cu OK sau cu GALBEN.")
INSTALARE_ESUATA = N_("Imaginea nu s-a putut pune: %s")
FARA_FEED = N_("Feedul HD Satelit nu are încă imaginea pentru stick a acestui receptor.")
FEED_NERASPUNS = N_("Feedul HD Satelit nu răspunde. Verifică internetul și încearcă din nou.")
ZIP_RAU = N_("Arhiva nu se poate citi.")
ZIP_FARA_TAR = N_("În arhivă nu găsesc imaginea receptorului (rootfs.tar.bz2 sau rootfs.ubi), deci nu se poate pune pe stick. "
	"Ia de pe site arhiva imaginii pentru acest receptor.")
DESFAC = N_("Desfac imaginea pentru memoria internă în locul %(loc)s... %(cat)s")
FARA_SISTEM = N_("În arhivă nu e un sistem care pornește (lipsește sbin/init).")
ADRESA_REA = N_("Adresa trebuie să înceapă cu http:// sau https://.")
NU_SE_DESCARCA = N_("Nu am putut descărca arhiva.")
FARA_LOC_STICK = N_("Pe stick nu e destul loc.")
STERG = N_("Șterg locul %s...")
STERS = N_("Locul %s e gol acum.")
STERGERE_ACUM = N_("Imaginea pornită acum nu se poate șterge. Pornește întâi alta.")
SURSA_FEED = N_("Din feedul HD Satelit")
SURSA_ZIP = N_("Dintr-o arhivă de pe stick")
SURSA_ADRESA = N_("De la o adresă de pe internet")
CU_SETARI = N_("Cu setările mele (canale, rețea, Wi-Fi, chei, pluginuri)")
FARA_SETARI = N_("Curată, fără setările mele")
NICIUN_ZIP = N_("Nu găsesc nicio arhivă .zip pe stick.")


def _log(text):
	print("[HdsPornireStick] %s" % text)


def _cale(radacina, rel):
	return os.path.join(radacina or "/", rel.lstrip("/"))


def _citeste(cale, maxim=65536):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim)
	except (IOError, OSError):
		return None


def _text(cale, maxim=65536):
	d = _citeste(cale, maxim)
	return d.decode("utf-8", "replace") if d is not None else ""


def _pm():
	try:
		from Components import HdsPornireMultipla as P
	except ImportError:
		import HdsPornireMultipla as P
	return P


def _marimeText(octeti):
	gb = octeti / 1024.0 / 1024 / 1024
	return "%.1f GB" % gb if gb >= 1 else "%d MB" % (octeti // 1024 // 1024)


# ------------------------------------------------------------------ receptorul si stickul

def model(radacina=None):
	"""{cheie: valoare} din /etc/hdsatelit-model (machine=, kernel_part=, machinebuild=)."""
	d = {}
	for rand in _text(_cale(radacina, "etc/hdsatelit-model")).splitlines():
		k, semn, v = rand.partition("=")
		if semn and not k.startswith("#"):
			d.setdefault(k.strip(), v.strip())
	return d


def disponibil(radacina=None):
	"""ZGEMMA H8.2H Plus / H8.2H SE (memoria NAND cu ubi0:rootfs). Nu cere stickul: fara el ecranul arata Pregateste."""
	if model(radacina).get("machine") not in MASINI:
		return False
	mtd = _text(_cale(radacina, "proc/mtd"))
	return '"kernel"' in mtd and '"rootfs"' in mtd


def _nucleu(radacina=None):
	p = model(radacina).get("kernel_part", "mtd8")
	return p if re.match(r"^mtd[0-9]{1,2}$", p) else "mtd8"


def textFlash(radacina=None):
	return TEXT_FLASH % _nucleu(radacina)


def textLoc(uuid, loc, radacina=None):
	return TEXT_LOC % (_nucleu(radacina), uuid, loc)


def blkid(dispozitiv, radacina=None):
	"""{TYPE, LABEL, UUID...} pentru /dev/<nume>. Pe PC: fisierul <radacina>/blkid/<nume> cu randul lui blkid."""
	nume = dispozitiv.rsplit("/", 1)[-1]
	if radacina:
		text = _text(_cale(radacina, "blkid/" + nume))
	else:
		try:
			text = subprocess.check_output(["blkid", "-c", "/dev/null", "/dev/" + nume], stderr=subprocess.DEVNULL,
				timeout=10).decode("utf-8", "replace")
		except (OSError, ValueError, subprocess.SubprocessError):
			text = ""
	return dict(re.findall(r'\b([A-Z_]+)="([^"]*)"', text))


def discuri(radacina=None):
	"""[{"disc": "sda", "marime": octeti, "nume": ...}] pentru discurile sd[a-d] din /proc/partitions."""
	rez = []
	for rand in _text(_cale(radacina, "proc/partitions")).splitlines():
		c = rand.split()
		if len(c) == 4 and c[2].isdigit() and RX_DISC.match(c[3]):
			nume = (_text(_cale(radacina, "sys/block/%s/device/vendor" % c[3]), 64).strip() + " " +
				_text(_cale(radacina, "sys/block/%s/device/model" % c[3]), 64).strip()).strip()
			rez.append({"disc": c[3], "marime": int(c[2]) * 1024, "nume": nume})
	return rez


def stickul(radacina=None):
	"""Stickul pregatit, ca /init: primul sd[a-d] cu p1 vfat si p2 cu eticheta rootfs (ext4); None cand nu e."""
	for d in discuri(radacina):
		b1, b2 = blkid(d["disc"] + "1", radacina), blkid(d["disc"] + "2", radacina)
		if b1.get("TYPE") != "vfat" or b2.get("LABEL") != "rootfs" or b2.get("TYPE") != "ext4":
			continue
		if not RX_UUID.match(b2.get("UUID", "")):
			continue
		d = dict(d, p1="/dev/%s1" % d["disc"], p2="/dev/%s2" % d["disc"], uuid=b2["UUID"])
		b3 = blkid(d["disc"] + "3", radacina)
		d["swap"] = "/dev/%s3" % d["disc"] if b3.get("TYPE") == "swap" else ""
		return d
	return None


def _montari(radacina=None):
	"""[(sursa, punct, root, fel)] din /proc/self/mountinfo; fara el din /proc/mounts (root "/")."""
	rez = []
	info = _text(_cale(radacina, "proc/self/mountinfo"))
	for rand in info.splitlines():
		parti = rand.split(" - ", 1)
		if len(parti) != 2:
			continue
		a, b = parti[0].split(), parti[1].split()
		if len(a) >= 5 and len(b) >= 2:
			rez.append((b[1], a[4].replace("\\040", " "), a[3], b[0]))
	if not info.strip():
		for rand in _text(_cale(radacina, "proc/mounts")).splitlines():
			c = rand.split()
			if len(c) >= 3:
				rez.append((c[0], c[1].replace("\\040", " "), "/", c[2]))
	return rez


def pornitAcum(radacina=None):
	"""{"loc": "flash" | "N" | "", "dev": partitia}: din ce loc ruleaza imaginea de acum."""
	for sursa, punct, root, fel in _montari(radacina):
		if punct != "/":
			continue
		if fel == "ubifs":
			return {"loc": FLASH, "dev": sursa}
		m = re.match(r"^/linuxrootfs([1-9])$", root)
		if fel == "ext4" and m:
			return {"loc": m.group(1), "dev": sursa}
	return {"loc": "", "dev": ""}


def _punct(dispozitiv, radacina=None):
	"""Unde e montata toata partitia (root "/"), cu radacina; None cand nu e."""
	for sursa, punct, root, fel in _montari(radacina):
		if sursa == dispozitiv and root == "/" and punct != "/":
			return _cale(radacina, punct)
	return None


def _monteaza(dispozitiv, fel, optiuni=None):
	import tempfile
	d = tempfile.mkdtemp(prefix="hds-stick-", dir="/tmp")
	cerere = ["mount", "-t", fel] + (["-o", optiuni] if optiuni else []) + [dispozitiv, d]
	try:
		cod = subprocess.call(cerere, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	except OSError:
		cod = -1
	if cod != 0:
		os.rmdir(d)
		return None, None

	def demonteaza():
		subprocess.call(["umount", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		try:
			os.rmdir(d)
		except OSError:
			pass
	return d, demonteaza


def _deschide(dispozitiv, fel, radacina=None, monteaza=None, optiuni=None):
	"""(dosarul partitiei, demonteaza sau None); (None, None) cand nu se poate."""
	p = _punct(dispozitiv, radacina)
	if p:
		return p, None
	if radacina and monteaza is None:
		return None, None
	return (monteaza or _monteaza)(_cale(radacina, dispozitiv) if radacina else dispozitiv, fel, optiuni)


def _numeImagine(dosar):
	try:
		return _pm().numeImagine(dosar)
	except Exception as e:
		_log("numele imaginii din %s: %r" % (dosar, e))
		return _(FARA_NUME)


def _numeFlash(acum, radacina=None, monteaza=None):
	if acum == FLASH:
		return _numeImagine(_cale(radacina, "/"))
	for sursa, punct, root, fel in _montari(radacina):
		if sursa == "ubi0:rootfs" and root == "/":
			return _numeImagine(_cale(radacina, punct))
	if radacina:
		nand = _cale(radacina, "nand")
		return _numeImagine(nand) if os.path.isdir(nand) else _(FARA_NUME)
	d, demonteaza = (monteaza or _monteaza)("ubi0:rootfs", "ubifs", "ro")
	if not d:
		return _(FARA_NUME)
	try:
		return _numeImagine(d)
	finally:
		demonteaza()


def _bun(dosar):
	return os.path.lexists(os.path.join(dosar, "sbin", "init")) or os.path.isfile(os.path.join(dosar, "sbin", "ldconfig"))


def _tintaStartup(date):
	"""Locul din textul unui STARTUP: "flash", "N" sau ""."""
	text = (date or b"").decode("ascii", "replace")
	p = dict(x.split("=", 1) for x in text.split() if "=" in x)
	m = RX_LOC.match(p.get("rootsubdir", ""))
	if m:
		return m.group(1)
	if p.get("root") == "ubi0:rootfs" or "flash=1" in text.split():
		return FLASH
	return ""


def _citesteODate(p1):
	"""(boot_id, locul tinta, STARTUP de pus la loc) din marcajul o_data; None cand nu e."""
	d = _citeste(os.path.join(p1, O_DATA), 8192)
	if not d:
		return None
	cap, _s, rest = d.partition(b"\n")
	parti = cap.decode("ascii", "replace").split()
	if len(parti) != 3 or parti[0] != "hds-o-data":
		return None
	return parti[1], parti[2], rest


def locuri(radacina=None, monteaza=None):
	"""{"stick": {...} sau None, "locuri": [...], "liber": "N" sau "", "acum", "implicit", "o_data", "eroare", "liber_octeti"}.
	Fiecare loc: loc ("flash" sau "N"), imagine, acum, implicit, o_data, porneste (se poate alege), sterge, strica."""
	acum = pornitAcum(radacina)["loc"]
	rez = {"disponibil": disponibil(radacina), "stick": None, "locuri": [], "liber": "", "acum": acum, "implicit": "",
		"o_data": "", "eroare": False, "liber_octeti": 0, "discuri": discuri(radacina)}
	st = stickul(radacina)
	rez["stick"] = st
	implicit, o_data, nume_loc = FLASH, "", {}
	if st:
		p1, dem1 = _deschide(st["p1"], "vfat", radacina, monteaza)
		if p1:
			try:
				implicit = _tintaStartup(_citeste(os.path.join(p1, STARTUP), 4096)) or FLASH
				od = _citesteODate(p1)
				if od:
					o_data = od[1]
					implicit = _tintaStartup(od[2]) or FLASH
			finally:
				if dem1:
					dem1()
		else:
			rez["eroare"] = True
		p2, dem2 = _deschide(st["p2"], "ext4", radacina, monteaza)
		if p2:
			try:
				try:
					nume = sorted(os.listdir(p2))
				except OSError:
					nume = []
				for n in nume:
					m = RX_LOC.match(n)
					if m and os.path.isdir(os.path.join(p2, n)):
						dosar = os.path.join(p2, n)
						nume_loc[m.group(1)] = (_numeImagine(dosar) if os.path.isdir(os.path.join(dosar, "etc"))
							else _(FARA_NUME), _bun(dosar))
				try:
					sv = os.statvfs(p2)
					rez["liber_octeti"] = sv.f_bavail * sv.f_frsize
				except (AttributeError, OSError):
					pass
			finally:
				if dem2:
					dem2()
		else:
			rez["eroare"] = True
	rez["implicit"], rez["o_data"] = implicit, o_data
	rez["locuri"].append({"loc": FLASH, "imagine": _numeFlash(acum, radacina, monteaza), "acum": acum == FLASH,
		"implicit": implicit == FLASH, "o_data": o_data == FLASH, "porneste": acum != FLASH and bool(st), "sterge": False,
		"strica": False})
	for n in sorted(nume_loc, key=int):
		imagine, bun = nume_loc[n]
		rez["locuri"].append({"loc": n, "imagine": imagine, "acum": acum == n, "implicit": implicit == n,
			"o_data": o_data == n, "porneste": bun and acum != n, "sterge": acum != n, "strica": not bun})
	if st:
		rez["liber"] = next((str(i) for i in range(1, LOCURI_MAXIM + 1) if str(i) not in nume_loc), "")
	return rez


def randuri(stare):
	"""Textele randurilor, in ordinea locurilor."""
	rez = []
	for l in stare.get("locuri", []):
		cap = _(FLASH_NUME) if l["loc"] == FLASH else _(LOC_NUME) % l["loc"]
		semne = [_(x) for k, x in (("acum", ACUM), ("o_data", O_DATA_SEMN), ("implicit", IMPLICIT), ("strica", STRICAT))
			if l.get(k)]
		rez.append("%s: %s%s" % (cap, l["imagine"], (" (" + ", ".join(semne) + ")") if semne else ""))
	return rez


def nota(stare):
	if not stare.get("stick"):
		return _(FARA_STICK)
	ocupate = len([l for l in stare.get("locuri", []) if l["loc"] != FLASH])
	info = _(PREGATIT_INFO) % {"locuri": ocupate, "maxim": LOCURI_MAXIM, "liber": _marimeText(stare.get("liber_octeti", 0))}
	return "%s %s" % (_(NOTA), info)


def publice(stare):
	"""Starea fara obiecte, pentru web."""
	st = stare.get("stick")
	return {"result": True, "stick": {"disc": st["disc"], "marime": _marimeText(st["marime"]), "nume": st["nume"]} if st else None,
		"locuri": [dict(l) for l in stare.get("locuri", [])], "randuri": randuri(stare), "nota": nota(stare),
		"liber": stare.get("liber", ""), "acum": stare.get("acum", ""), "eroare": stare.get("eroare", False),
		"discuri": [{"disc": d["disc"], "marime": _marimeText(d["marime"]), "nume": d["nume"]}
			for d in stare.get("discuri", [])],
		"pe_flash": stare.get("acum") == FLASH, "lucrare": stareLucrare()}


# ------------------------------------------------------------------ alegerea

def _scrie(dosar, nume, date):
	try:
		return _pm()._scrieAtomic(dosar, nume, date)
	except (IOError, OSError) as e:
		_log("scrierea %s: %r" % (nume, e))
		return False


def _bootId(radacina=None):
	return _text(_cale(radacina, "proc/sys/kernel/random/boot_id"), 64).strip() or "necunoscut"


def _hookText():
	"""Scriptul rcS pus in locul ales "o data": pune la loc STARTUP de dinainte si se sterge. Merge pe orice imagine
	Enigma2 cu sysvinit (busybox sh, blkid, mount)."""
	return """#!/bin/sh
# HD Satelit (HdsPornireStick): o singura pornire in aceasta imagine; pune la loc STARTUP de dinainte, apoi se sterge.
for p in /dev/sda1 /dev/sdb1 /dev/sdc1 /dev/sdd1; do
	[ -b "$p" ] || continue
	mkdir -p /hds-o-data
	mount -t vfat "$p" /hds-o-data 2>/dev/null || continue
	if [ -f /hds-o-data/%(marcaj)s ]; then
		tail -n +2 /hds-o-data/%(marcaj)s > /hds-o-data/STARTUP.hds-nou && mv /hds-o-data/STARTUP.hds-nou /hds-o-data/STARTUP
		rm -f /hds-o-data/%(marcaj)s
		sync
	fi
	umount /hds-o-data
done
rmdir /hds-o-data 2>/dev/null
rm -f /%(legatura)s /%(script)s
""" % {"marcaj": O_DATA, "legatura": LEGATURA_O_DATA, "script": SCRIPT_O_DATA}


def _puneHook(dosar):
	s = os.path.join(dosar, SCRIPT_O_DATA)
	l = os.path.join(dosar, LEGATURA_O_DATA)
	os.makedirs(os.path.dirname(s), exist_ok=True)
	os.makedirs(os.path.dirname(l), exist_ok=True)
	with open(s, "w") as f:
		f.write(_hookText())
	os.chmod(s, 0o755)
	if os.path.lexists(l):
		os.remove(l)
	try:
		os.symlink("../init.d/hds-o-data", l)
	except (OSError, NotImplementedError, AttributeError):
		shutil.copy(s, l)


def _scoateHook(dosar):
	for rel in (LEGATURA_O_DATA, SCRIPT_O_DATA):
		try:
			os.remove(os.path.join(dosar, rel))
		except OSError:
			pass


def _scoateHookuri(p2):
	try:
		nume = os.listdir(p2)
	except OSError:
		return
	for n in nume:
		if RX_LOC.match(n):
			_scoateHook(os.path.join(p2, n))


def alege(loc, o_data=False, radacina=None, monteaza=None):
	"""STARTUP = locul ales (o_data: numai pornirea urmatoare). (True, imaginea) sau (False, motivul)."""
	loc = str(loc)
	stare = locuri(radacina, monteaza)
	gasit = [l for l in stare["locuri"] if l["loc"] == loc]
	st = stare["stick"]
	if not gasit or not st:
		return False, _(NEGASIT)
	l = gasit[0]
	if l["acum"]:
		# imaginea pornita acum: "de acum" o face numai cea de obicei, fara repornire (reporneste)
		if o_data or l["implicit"]:
			return False, _(DEJA)
	elif not l["porneste"]:
		return False, _(NU_PORNESTE) % loc
	p1, dem1 = _deschide(st["p1"], "vfat", radacina, monteaza)
	if not p1:
		return False, _(EROARE)
	p2, dem2 = (None, None)
	try:
		flash = textFlash(radacina).encode("ascii")
		if _citeste(os.path.join(p1, STARTUP_FLASH), 4096) != flash and not _scrie(p1, STARTUP_FLASH, flash):
			return False, _(EROARE)
		if loc == FLASH:
			nou = flash
		else:
			nou = textLoc(st["uuid"], loc, radacina).encode("ascii")
			if _citeste(os.path.join(p1, "STARTUP_" + loc), 4096) != nou and not _scrie(p1, "STARTUP_" + loc, nou):
				return False, _(EROARE)
		vechi = _citeste(os.path.join(p1, STARTUP), 4096)
		vechi = ABSENT if vechi is None else vechi
		od = _citesteODate(p1)
		implicit = od[2] if od else (flash if vechi == ABSENT else vechi)
		if not _scrie(p1, COPIE, vechi):
			return False, _(EROARE)
		p2, dem2 = _deschide(st["p2"], "ext4", radacina, monteaza)
		if p2:
			_scoateHookuri(p2)
		if o_data:
			if loc != FLASH:
				if not p2:
					return False, _(EROARE)
				_puneHook(os.path.join(p2, "linuxrootfs" + loc))
			marcaj = ("hds-o-data %s %s\n" % (_bootId(radacina), loc)).encode("ascii") + implicit
			if not _scrie(p1, O_DATA, marcaj):
				return False, _(EROARE)
		else:
			try:
				os.remove(os.path.join(p1, O_DATA))
			except OSError:
				pass
		if not _scrie(p1, STARTUP, nou):
			_scrie(p1, STARTUP, vechi) if vechi != ABSENT else None
			return False, _(EROARE)
		_log("STARTUP = %s (%s)%s" % (loc, l["imagine"], ", o singura data" if o_data else ""))
		return True, l["imagine"]
	except (IOError, OSError) as e:
		_log("alegerea: %r" % (e,))
		return False, _(EROARE)
	finally:
		if dem2:
			dem2()
		if dem1:
			dem1()


def inapoi(radacina=None, monteaza=None):
	"""Repornirea a fost oprita pe ecran: STARTUP de dinainte, fara marcaj si fara scriptul o_data."""
	st = stickul(radacina)
	if not st:
		return False
	p1, dem1 = _deschide(st["p1"], "vfat", radacina, monteaza)
	if not p1:
		return False
	try:
		vechi = _citeste(os.path.join(p1, COPIE), 4096)
		if vechi is None:
			return False
		try:
			os.remove(os.path.join(p1, O_DATA))
		except OSError:
			pass
		p2, dem2 = _deschide(st["p2"], "ext4", radacina, monteaza)
		if p2:
			try:
				_scoateHookuri(p2)
			finally:
				if dem2:
					dem2()
		if vechi == ABSENT:
			try:
				os.remove(os.path.join(p1, STARTUP))
			except OSError:
				pass
			return True
		return _scrie(p1, STARTUP, vechi)
	finally:
		if dem1:
			dem1()


def laPornire(radacina=None, monteaza=None):
	"""Din mytest.py, o data la pornire: marcajul "o data" lasat de o pornire de dinainte (boot_id altul) se pune la loc.
	Acopera memoria interna (nu primeste scriptul rcS) si locurile care n-au pornit. True cand a pus la loc."""
	if not disponibil(radacina):
		return False
	st = stickul(radacina)
	if not st:
		return False
	p1, dem1 = _deschide(st["p1"], "vfat", radacina, monteaza)
	if not p1:
		return False
	try:
		od = _citesteODate(p1)
		if not od or od[0] == _bootId(radacina):
			return False
		bun = _scrie(p1, STARTUP, od[2]) if od[2] else True
		if bun:
			try:
				os.remove(os.path.join(p1, O_DATA))
			except OSError:
				pass
		_log("o data: pus la loc STARTUP (tinta era %s): %s" % (od[1], bun))
		return bun
	finally:
		if dem1:
			dem1()


def porneste():
	"""Chemat din mytest.py: laPornire pe un fir, dupa 15 s (stickul apare dupa pornire)."""
	if not disponibil():
		return

	def lucru():
		time.sleep(15)
		try:
			laPornire()
		except Exception as e:
			_log("la pornire: %r" % (e,))
	t = threading.Thread(target=lucru, name="HdsPornireStick")
	t.daemon = True
	t.start()


def reporneste(sesiune, loc, o_data=False, dupa_ms=0, fabrica_ceas=None, radacina=None, monteaza=None, Standby=None):
	"""Scrie alegerea, apoi TryQuitMainloop(2). La Nu pe ecranul de repornire, inapoi(). (True, text) sau (False, motiv)."""
	if sesiune is None:
		return False, _(EROARE)
	acum = pornitAcum(radacina)["loc"] == str(loc)
	ok, imagine = alege(loc, o_data, radacina, monteaza)
	if not ok or acum:
		return ok, (_(RAMANE) % imagine) if ok else imagine

	def renuntat(*_a):
		inapoi(radacina, monteaza)

	def acum():
		try:
			S = Standby
			if S is None:
				from Screens import Standby as S
			sesiune.openWithCallback(renuntat, S.TryQuitMainloop, 2)
		except Exception as e:
			_log("repornirea: %r" % (e,))
			inapoi(radacina, monteaza)

	if dupa_ms <= 0:
		acum()
	else:
		from Components import HdsAlimentare
		HdsAlimentare.programeaza(acum, dupa_ms, fabrica_ceas, nume="pornire-stick")
	return True, (_(GATA_O_DATA) if o_data else _(GATA_DE_ACUM)) % imagine


# ------------------------------------------------------------------ lucrarile lungi (una odata, pe un fir)

LUCRAREA = {"ce": "", "lucreaza": False, "text": "", "gata": False, "ok": False, "cand": 0}
_zavor = threading.Lock()


def stareLucrare():
	return {k: LUCRAREA[k] for k in ("ce", "lucreaza", "text", "gata", "ok")}


def _progres(text):
	LUCRAREA["text"] = text
	LUCRAREA["cand"] = time.time()


def pornesteLucrare(ce, functie, fir=None):
	"""functie() -> (ok, text), pe un fir. (True, text de inceput) sau (False, OCUPAT)."""
	with _zavor:
		if LUCRAREA["lucreaza"]:
			return False, _(OCUPAT)
		LUCRAREA.update(ce=ce, lucreaza=True, gata=False, ok=False, text=_(CAUT), cand=time.time())

	def lucru():
		try:
			ok, text = functie()
		except Exception as e:
			_log("%s: %r" % (ce, e))
			ok, text = False, "%s" % e
		LUCRAREA.update(lucreaza=False, gata=True, ok=bool(ok), text=text, cand=time.time())
		_log("%s: %s %s" % (ce, "bun" if ok else "esuat", text))

	if fir is not None:
		fir(lucru)
	else:
		t = threading.Thread(target=lucru, name="HdsPornireStick-" + ce)
		t.daemon = True
		t.start()
	return True, LUCRAREA["text"]


def _ruleaza(cerere, intrare=None, shell=False):
	"""(cod, iesirea) pentru o comanda; pe receptor."""
	try:
		p = subprocess.Popen(cerere, shell=shell, stdin=subprocess.PIPE if intrare is not None else subprocess.DEVNULL,
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		iesire, _e = p.communicate(intrare)
		return p.returncode, (iesire or b"").decode("utf-8", "replace")
	except OSError as e:
		return -1, "%s" % e


SCRIPT_PREGATIRE = r"""
set -eu
DISC=$1; SWAPMB=$2
udevadm control --stop-exec-queue 2>/dev/null || true
trap 'udevadm control --start-exec-queue 2>/dev/null || true' EXIT
dd if=/dev/zero of="$DISC" bs=1M count=40 conv=fsync 2>/dev/null
TOT=$(cat /sys/block/${DISC#/dev/}/size)
if [ "$SWAPMB" -gt 0 ]; then
	P2S=$(( TOT - 2048 - 65536 - SWAPMB * 2048 - 2048 ))
	printf 'label: dos\n2048,65536,c\n,%s,83\n,,82\n' "$P2S" | sfdisk -q "$DISC"
else
	printf 'label: dos\n2048,65536,c\n,,83\n' | sfdisk -q "$DISC"
fi
sleep 2; mdev -s 2>/dev/null || true
for p in ${DISC}1 ${DISC}2 ${DISC}3; do awk -v d="$p" '$1==d{print $2}' /proc/mounts | while read -r m; do umount "$m"; done; done
mkfs.vfat -F 32 -n STARTUP ${DISC}1 > /dev/null
mkfs.ext4 -q -F -L rootfs ${DISC}2
if [ "$SWAPMB" -gt 0 ]; then mkswap -L swap ${DISC}3 > /dev/null; fi
sync
"""


def pregatesteStick(disc, radacina=None, ruleaza=None):
	"""Sterge stickul `disc` (sda..sdd) si il pregateste: p1 FAT32 32 MiB "STARTUP", p2 ext4 "rootfs", p3 swap 1 GB (pe
	stickurile de cel putin 8 GB). Numai din memoria interna. (ok, text). Pe un fir (pornesteLucrare)."""
	ruleaza = ruleaza or _ruleaza
	if pornitAcum(radacina)["loc"] != FLASH:
		return False, _(PREGATESTE_DIN_FLASH)
	gasit = [d for d in discuri(radacina) if d["disc"] == disc]
	if not RX_DISC.match(disc or "") or not gasit:
		return False, _(DISC_NECUNOSCUT)
	dev = "/dev/" + disc
	_progres(_(PREGATESC))
	# swap-ul si montarile de pe stick (setarile, copiile) se opresc intai
	for rand in _text(_cale(radacina, "proc/swaps")).splitlines()[1:]:
		c = rand.split()
		if c and c[0].startswith(dev):
			ruleaza(["swapoff", c[0]])
	for sursa, punct, root, fel in sorted(_montari(radacina), key=lambda x: -len(x[1])):
		if sursa.startswith(dev):
			if punct == "/":
				return False, _(DISC_FOLOSIT)
			cod, _i = ruleaza(["umount", punct])
			if cod != 0:
				cod, _i = ruleaza(["umount", "-l", punct])
				if cod != 0:
					return False, _(DISC_FOLOSIT)
	swap = SWAP_MB if gasit[0]["marime"] >= MINIM_SWAP_GB * 1024 * 1024 * 1024 else 0
	cod, iesire = ruleaza(["/bin/sh", "-c", SCRIPT_PREGATIRE, "pregatire", dev, str(swap)])
	if cod != 0:
		return False, _(PREGATIRE_ESUATA) % (iesire.strip().splitlines() or ["cod %s" % cod])[-1]
	time.sleep(0 if radacina else 2)
	st = stickul(radacina)
	if not st:
		return False, _(PREGATIRE_ESUATA) % "blkid"
	p1, dem1 = _deschide(st["p1"], "vfat", radacina)
	if not p1:
		return False, _(PREGATIRE_ESUATA) % "mount"
	try:
		flash = textFlash(radacina).encode("ascii")
		if not (_scrie(p1, STARTUP_FLASH, flash) and _scrie(p1, STARTUP, flash)):
			return False, _(PREGATIRE_ESUATA) % "STARTUP"
	finally:
		if dem1:
			dem1()
	if st.get("swap"):
		ruleaza(["swapon", st["swap"]])
	# montarea obisnuita (/media/...) o refac regulile udev
	ruleaza(["udevadm", "trigger", "--action=add", "--subsystem-match=block"])
	return True, _(PREGATIT)


# ---- instalarea

def zipuri(radacina=None, monteaza=None):
	"""Arhivele .zip de pe stick si de pe discurile montate (radacina lor, hdsatelit/imagini-stick si un nivel mai jos)."""
	rez, vazute = [], set()
	puncte = [punct for sursa, punct, root, fel in _montari(radacina)
		if sursa.startswith("/dev/sd") and root == "/" and punct != "/" and fel in ("ext4", "vfat", "exfat", "ntfs", "fuseblk")]
	for punct in puncte:
		baza = _cale(radacina, punct)
		for sub in ("", DOSAR_ZIP, "images", "imagini"):
			d = os.path.join(baza, sub)
			try:
				nume = os.listdir(d)
			except OSError:
				continue
			for n in sorted(nume):
				cale = os.path.join(d, n)
				if n.lower().endswith(".zip") and os.path.isfile(cale) and os.path.realpath(cale) not in vazute:
					vazute.add(os.path.realpath(cale))
					rez.append({"cale": cale, "nume": n, "marime": _marimeText(os.path.getsize(cale))})
	return rez[:40]


def alegeMembru(nume, masina=""):
	"""Din numele unei arhive: rootfs.tar.bz2 (intai cel din dosarul masinii), altfel .tar.xz/.tar.gz, altfel rootfs.ubi
	(imaginea NAND a altor echipe, desfacuta de HdsCititorUbi); "" cand nu e."""
	for sufix in ("rootfs.tar.bz2", "rootfs.tar.xz", "rootfs.tar.gz", "rootfs.ubi"):
		gasite = [n for n in nume if n.endswith(sufix) and not n.endswith("/")]
		if gasite:
			pe_masina = [n for n in gasite if masina and ("/%s/" % masina in "/" + n)]
			return (pe_masina or sorted(gasite, key=len))[0]
	return ""


def _descarcaAdresa(adresa, cale, progres, deschide=None):
	try:
		from urllib.request import Request, urlopen
	except ImportError:
		from urllib2 import Request, urlopen
	cerere = Request(adresa, headers={"User-Agent": UA})
	r = (deschide or urlopen)(cerere, timeout=60)
	try:
		total = int(r.headers.get("Content-Length") or 0) if getattr(r, "headers", None) else 0
		n = 0
		with open(cale + ".partial", "wb") as f:
			while True:
				b = r.read(BLOC)
				if not b:
					break
				f.write(b)
				n += len(b)
				progres(n, total)
		os.replace(cale + ".partial", cale)
	finally:
		r.close()
	return cale


def _zipFeed(dosar, progres, canal="public"):
	"""(cale, None) sau (None, motiv): imaginea pentru stick a modelului din lista semnata a feedului."""
	try:
		from Components import HdsImagineOnline as O
	except ImportError:
		import HdsImagineOnline as O
	lista, cod = O.citeste_lista(canal)
	if not lista:
		return None, _(FEED_NERASPUNS)
	masina = O.masina_acum()
	img = O.alege_imaginea(lista, masina + "-usb", None, canal) if masina else None
	if not img:
		return None, _(FARA_FEED)
	cale, cod = O.descarca(img, dosar, progres=progres)
	if not cale:
		return None, _(NU_SE_DESCARCA)
	import hashlib
	h = hashlib.sha256()
	with open(cale, "rb") as f:
		for b in iter(lambda: f.read(BLOC), b""):
			h.update(b)
	if h.hexdigest() != img["sha256"]:
		os.remove(cale)
		return None, _(NU_SE_DESCARCA)
	return cale, None


FISIERE_SETARI = ("etc/network/interfaces", "etc/wpa_supplicant.conf", "etc/wpa_supplicant.wlan0.conf",
	"etc/wpa_supplicant.wlan1.conf", "etc/resolv.conf", "etc/hostname", "etc/timezone", "etc/localtime")
DOSARE_SETARI = ("etc/tuxbox/config", "usr/keys", "etc/dropbear", "home/root/.ssh")
# imaginile altor echipe: canalele si listele, fara settings (o tema sau un plugin pe care nu-l au o pot opri la pornire)
CANALE = re.compile(r"^(lamedb5?|bouquets\.(tv|radio)|userbouquet\..*|blacklist|whitelist|satellites\.xml|cables\.xml|"
	r"terrestrial\.xml|timers\.xml|autotimer\.xml)$")


def _copiaza(sursa, tinta):
	try:
		if os.path.islink(sursa):
			if os.path.lexists(tinta):
				os.remove(tinta)
			os.symlink(os.readlink(sursa), tinta)
		elif os.path.isdir(sursa):
			os.makedirs(tinta, exist_ok=True)
			for n in os.listdir(sursa):
				_copiaza(os.path.join(sursa, n), os.path.join(tinta, n))
		elif os.path.isfile(sursa):
			os.makedirs(os.path.dirname(tinta), exist_ok=True)
			shutil.copy2(sursa, tinta)
	except (IOError, OSError) as e:
		_log("copia %s: %r" % (sursa, e))


def _python(dosar):
	try:
		return sorted(n for n in os.listdir(os.path.join(dosar, "usr", "lib")) if re.match(r"^python3\.[0-9]+$", n))
	except OSError:
		return []


def copiazaSetari(dosar, radacina=None):
	"""Setarile imaginii de acum in imaginea din `dosar`: canalele, reteaua si Wi-Fi-ul, cheile (OSCam, usr/keys), ssh si,
	cand imaginea e tot HD Satelit, toate setarile enigma2 si pluginurile care ii lipsesc (aceeasi versiune de Python)."""
	acum = _cale(radacina, "/")
	a_noastra = os.path.isfile(os.path.join(dosar, "etc", "hdsatelit-model"))
	e2 = os.path.join(acum, "etc", "enigma2")
	try:
		nume = os.listdir(e2)
	except OSError:
		nume = []
	for n in nume:
		if a_noastra or CANALE.match(n):
			_copiaza(os.path.join(e2, n), os.path.join(dosar, "etc", "enigma2", n))
	for n in ("satellites.xml", "cables.xml", "terrestrial.xml"):
		if os.path.isfile(os.path.join(acum, "etc", "tuxbox", n)):
			_copiaza(os.path.join(acum, "etc", "tuxbox", n), os.path.join(dosar, "etc", "tuxbox", n))
	for rel in FISIERE_SETARI + DOSARE_SETARI:
		if os.path.lexists(os.path.join(acum, rel)):
			_copiaza(os.path.join(acum, rel), os.path.join(dosar, rel))
	py = _python(acum)
	if a_noastra and py and py == _python(dosar):
		for fel in ("Extensions", "SystemPlugins"):
			baza = os.path.join(acum, "usr", "lib", "enigma2", "python", "Plugins", fel)
			tinta = os.path.join(dosar, "usr", "lib", "enigma2", "python", "Plugins", fel)
			try:
				nume = os.listdir(baza)
			except OSError:
				continue
			for n in nume:
				if not os.path.exists(os.path.join(tinta, n)):
					_copiaza(os.path.join(baza, n), os.path.join(tinta, n))


def instaleaza(sursa, loc="", setari=True, radacina=None, monteaza=None, ruleaza_tar=None, deschide=None, ruleaza_ubi=None):
	"""Pune o imagine in locul `loc` (implicit primul liber). sursa: {"fel": "feed"}, {"fel": "zip", "cale": ...} sau
	{"fel": "adresa", "adresa": ...}. (ok, text). Pe un fir (pornesteLucrare)."""
	stare = locuri(radacina, monteaza)
	st = stare["stick"]
	if not st:
		return False, _(FARA_STICK)
	loc = str(loc or stare["liber"])
	if not loc:
		return False, _(FARA_LOC_LIBER) % LOCURI_MAXIM
	if not re.match(r"^[1-9]$", loc):
		return False, _(NEGASIT)
	if any(l["loc"] == loc for l in stare["locuri"]):
		return False, _(LOC_OCUPAT) % loc
	p2, dem2 = _deschide(st["p2"], "ext4", radacina, monteaza)
	if not p2:
		return False, _(EROARE)
	dosar = os.path.join(p2, "linuxrootfs" + loc)
	try:
		descarcari = os.path.join(p2, DOSAR_ZIP)
		os.makedirs(descarcari, exist_ok=True)

		def progres(n, total):
			_progres(_(DESCARC) % ("%d%%" % (n * 100 // total) if total else _marimeText(n)))

		fel = (sursa or {}).get("fel")
		if fel == "feed":
			_progres(_(DESCARC) % "")
			cale, motiv = _zipFeed(descarcari, progres)
			if not cale:
				return False, motiv
		elif fel == "zip":
			cale = sursa.get("cale", "")
			if not cale.lower().endswith(".zip") or not os.path.isfile(cale):
				return False, _(ZIP_RAU)
		elif fel == "adresa":
			adresa = (sursa.get("adresa") or "").strip()
			if not RX_ADRESA.match(adresa):
				return False, _(ADRESA_REA)
			nume = re.sub(r"[^A-Za-z0-9._-]", "_", adresa.split("?")[0].rsplit("/", 1)[-1])[:80] or "imagine.zip"
			if not nume.lower().endswith(".zip"):
				nume += ".zip"
			_progres(_(DESCARC) % "")
			try:
				cale = _descarcaAdresa(adresa, os.path.join(descarcari, nume), progres, deschide)
			except Exception as e:
				_log("descarcarea %s: %r" % (adresa, e))
				return False, _(NU_SE_DESCARCA)
		else:
			return False, _(ZIP_RAU)
		import zipfile
		try:
			z = zipfile.ZipFile(cale)
		except (zipfile.BadZipfile, IOError, OSError):
			return False, _(ZIP_RAU)
		with z:
			membru = alegeMembru(z.namelist(), model(radacina).get("machine", ""))
			if not membru:
				return False, _(ZIP_FARA_TAR)
			info = z.getinfo(membru)
			e_ubi = membru.endswith(".ubi")
			try:
				sv = os.statvfs(p2)
				if sv.f_bavail * sv.f_frsize < info.file_size * (3 if e_ubi else 4):
					return False, _(FARA_LOC_STICK)
			except (AttributeError, OSError):
				pass
			if os.path.lexists(dosar):
				shutil.rmtree(dosar, ignore_errors=True)
			os.makedirs(dosar)
			if e_ubi:
				bun = _desfaUbi(z, membru, descarcari, dosar, loc, ruleaza_ubi)
			else:
				optiune = {"bz2": "-xjf", ".xz": "-xJf", ".gz": "-xzf"}[membru[-3:]]
				bun = (ruleaza_tar or _despacheteaza)(z.open(membru), info.file_size, optiune, dosar, loc)
		if not bun or not _bun(dosar):
			shutil.rmtree(dosar, ignore_errors=True)
			return False, _(FARA_SISTEM) if bun else _(INSTALARE_ESUATA) % ("ubi" if e_ubi else "tar")
		if setari:
			_progres(_(COPIEZ_SETARI))
			copiazaSetari(dosar, radacina)
		if not os.path.isfile(os.path.join(dosar, "etc", "hdsatelit-model")):
			pregatesteStraina(dosar, setari, radacina)
		imagine = _numeImagine(dosar)
	finally:
		if dem2:
			dem2()
	p1, dem1 = _deschide(st["p1"], "vfat", radacina, monteaza)
	if not p1:
		return False, _(EROARE)
	try:
		flash = textFlash(radacina).encode("ascii")
		if _citeste(os.path.join(p1, STARTUP_FLASH), 4096) != flash:
			_scrie(p1, STARTUP_FLASH, flash)
		if not _scrie(p1, "STARTUP_" + loc, textLoc(st["uuid"], loc, radacina).encode("ascii")):
			return False, _(EROARE)
	finally:
		if dem1:
			dem1()
	return True, _(INSTALAT) % {"imagine": imagine, "loc": loc}


def _desfaUbi(z, membru, descarcari, dosar, loc, ruleaza_ubi=None):
	"""rootfs.ubi din zip: intai copiat pe stick (zip-ul nu se poate citi pe sarite), apoi desfacut in `dosar` de
	HdsCititorUbi.py intr-un proces python3 separat (interfata nu se ingreuneaza, memoria se elibereaza la sfarsit).
	Fisierul .ubi se sterge dupa. True cand a mers."""
	cale = os.path.join(descarcari, ".hds-loc%s.ubi" % loc)
	marime = z.getinfo(membru).file_size or 1
	try:
		n = 0
		with z.open(membru) as sursa:
			with open(cale, "wb") as f:
				while True:
					b = sursa.read(BLOC)
					if not b:
						break
					f.write(b)
					n += len(b)
					_progres(_(DESFAC) % {"loc": loc, "cat": "%d%%" % (n * 30 // marime)})
		if ruleaza_ubi is not None:
			return ruleaza_ubi(cale, dosar)
		return _cititorUbi(cale, dosar, loc)
	except (IOError, OSError) as e:
		_log("ubi: %r" % (e,))
		return False
	finally:
		try:
			os.remove(cale)
		except OSError:
			pass


def _cititorUbi(cale, dosar, loc):
	aici = os.path.dirname(os.path.abspath(__file__))
	cod = "import sys; sys.path.insert(0, sys.argv[1]); import HdsCititorUbi as C; sys.exit(C.main(sys.argv[1:]))"
	p = subprocess.Popen(["nice", "-n", "10", "python3", "-c", cod, aici, cale, dosar], stdout=subprocess.PIPE,
		stderr=subprocess.PIPE)
	for rand in iter(p.stdout.readline, b""):
		parti = rand.split()
		if len(parti) == 3 and parti[0] == b"P":
			try:
				_progres(_(DESFAC) % {"loc": loc, "cat": "%d%%" % (30 + int(parti[1]) * 70 // max(1, int(parti[2])))})
			except ValueError:
				pass
		elif parti[:1] == [b"GATA"]:
			_log("ubi %s: %s" % (dosar, rand.decode("ascii", "replace").strip()))
	eroare = p.stderr.read().decode("utf-8", "replace")
	p.stdout.close()
	p.stderr.close()
	cod = p.wait()
	if cod != 0:
		_log("ubi cod %s: %s" % (cod, eroare[-400:]))
	return cod == 0


# pachetele al caror postinst poate scrie nucleul sau partitiile de pornire (mtd0-8): raman pe loc in imaginile straine
RX_HOLD = re.compile(r"^(kernel-image|kernel-[0-9]|kernel$)|-(bootargs|recovery|fastboot|bootlogo|param|partitions)-|"
	r"^(bootargs|recovery|fastboot|bootlogo)-")
CHEI_SETARI = re.compile(r"^config\.(Nims\.|av\.|timezone\.|osd\.language=|misc\.country=)")
FARA_EXPERTI = ("config.misc.firstrun=false", "config.misc.languageselected=false", "config.misc.initialchannelselection=false",
	"config.misc.do_overscanwizard=false", "config.misc.wizardLanguageEnabled=false", "config.misc.videowizardenabled=false")


def pregatesteStraina(dosar, setari=True, radacina=None):
	"""Imaginea altei echipe din `dosar`, inainte de prima pornire: driverele h8 in modules-load.d (unele imagini nu le
	incarca singure), "hold" in opkg pe pachetele care pot scrie nucleul sau partitiile de pornire si, cu setarile,
	tunerul, motorul, iesirea video si ora de acum (si in forma config.Nims.N.dvbs.* ceruta de imaginile OE-A noi),
	fara expertii de la prima pornire. Lamedb5 al imaginii se scoate cand am pus canalele noastre (lamedb)."""
	acum = _cale(radacina, "/")
	# 1. driverele h8 (pe stick le pune initramfs-ul din memoria interna; imaginea trebuie sa le si incarce)
	ml = os.path.join(dosar, "etc", "modules-load.d")
	try:
		are = any(re.search(r"(?m)^h8_1\b", _text(os.path.join(ml, n)) or "") for n in os.listdir(ml))
	except OSError:
		are = False
	if not are:
		randuri = []
		try:
			for n in sorted(os.listdir(os.path.join(acum, "etc", "modules-load.d"))):
				for r in (_text(os.path.join(acum, "etc", "modules-load.d", n)) or "").splitlines():
					if re.match(r"^h8_[0-9]+$", r.strip()) and r.strip() not in randuri:
						randuri.append(r.strip())
		except OSError:
			pass
		if randuri:
			os.makedirs(ml, exist_ok=True)
			_scrie(ml, "_hds-h8.conf",("\n".join(randuri) + "\n").encode("ascii"))
	# 2. hold in opkg
	for rel in (("var", "lib", "opkg", "status"), ("usr", "lib", "opkg", "status")):
		cale = os.path.join(dosar, *rel)
		if os.path.islink(cale):
			continue
		text = _text(cale, 16 * 1024 * 1024)
		if not text:
			continue
		iesire, pachet = [], ""
		for r in text.split("\n"):
			if r.startswith("Package:"):
				pachet = r.split(":", 1)[1].strip()
			elif r.startswith("Status:") and pachet and RX_HOLD.search(pachet):
				c = r.split()
				if len(c) == 4:
					r = "Status: %s hold %s" % (c[1], c[3])
			iesire.append(r)
		nou = "\n".join(iesire)
		if nou != text:
			_scrie(os.path.dirname(cale), "status", nou.encode("utf-8"))
	if not setari:
		return
	e2 = os.path.join(dosar, "etc", "enigma2")
	if os.path.isfile(os.path.join(e2, "lamedb")):
		try:
			os.remove(os.path.join(e2, "lamedb5"))
		except OSError:
			pass
	# 3. settings: numai tunerul, motorul, video, ora si limba; restul imaginii ramane al ei
	noi = []
	for r in (_text(os.path.join(acum, "etc", "enigma2", "settings"), 4 * 1024 * 1024) or "").splitlines():
		if CHEI_SETARI.match(r) and "hds" not in r.split("=", 1)[0].lower():
			noi.append(r)
	dvbs = []
	for r in noi:
		m = re.match(r"^config\.Nims\.([0-9]+)\.(?!dvbs\.|dvbc\.|dvbt\.)(.*)$", r)
		if m:
			dvbs.append("config.Nims.%s.dvbs.%s" % (m.group(1), m.group(2)))
	if not noi:
		return
	noi += dvbs + list(FARA_EXPERTI)
	vechi = (_text(os.path.join(e2, "settings"), 4 * 1024 * 1024) or "").splitlines()
	tot = {}
	for r in vechi + noi:
		if "=" in r:
			tot[r.split("=", 1)[0]] = r
	os.makedirs(e2, exist_ok=True)
	_scrie(e2, "settings", ("\n".join(tot.values()) + "\n").encode("utf-8"))


def _despacheteaza(flux, marime, optiune, dosar, loc):
	"""Arhiva tar din `flux` (membrul din zip) prin tar-ul receptorului, cu progresul. True cand tar a iesit cu 0."""
	p = subprocess.Popen(["tar", optiune, "-", "-C", dosar], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
		stderr=subprocess.PIPE)
	n = 0
	try:
		while True:
			b = flux.read(BLOC)
			if not b:
				break
			p.stdin.write(b)
			n += len(b)
			_progres(_(DESPACHETEZ) % {"loc": loc, "cat": "%d%%" % (n * 100 // marime) if marime else _marimeText(n)})
		p.stdin.close()
	except (IOError, OSError) as e:
		_log("tar: %r" % (e,))
	eroare = p.stderr.read().decode("utf-8", "replace") if p.stderr else ""
	cod = p.wait()
	if cod != 0:
		_log("tar cod %s: %s" % (cod, eroare[-400:]))
	return cod == 0


def stergeLoc(loc, radacina=None, monteaza=None, ruleaza=None):
	"""Sterge linuxrootfsN si STARTUP_N; cand STARTUP pornea locul acela, STARTUP = memoria interna. (ok, text)."""
	loc = str(loc)
	stare = locuri(radacina, monteaza)
	st = stare["stick"]
	gasit = [l for l in stare["locuri"] if l["loc"] == loc and loc != FLASH]
	if not st or not gasit:
		return False, _(NEGASIT)
	if gasit[0]["acum"]:
		return False, _(STERGERE_ACUM)
	_progres(_(STERG) % loc)
	p2, dem2 = _deschide(st["p2"], "ext4", radacina, monteaza)
	if not p2:
		return False, _(EROARE)
	try:
		dosar = os.path.join(p2, "linuxrootfs" + loc)
		if ruleaza is not None or radacina:
			shutil.rmtree(dosar, ignore_errors=True)
		else:
			_ruleaza(["rm", "-rf", dosar])
		if os.path.exists(dosar):
			return False, _(EROARE)
	finally:
		if dem2:
			dem2()
	p1, dem1 = _deschide(st["p1"], "vfat", radacina, monteaza)
	if p1:
		try:
			for n in ("STARTUP_" + loc,):
				try:
					os.remove(os.path.join(p1, n))
				except OSError:
					pass
			od = _citesteODate(p1)
			if od and od[1] == loc:
				_scrie(p1, STARTUP, od[2] or textFlash(radacina).encode("ascii"))
				try:
					os.remove(os.path.join(p1, O_DATA))
				except OSError:
					pass
			if _tintaStartup(_citeste(os.path.join(p1, STARTUP), 4096)) == loc:
				_scrie(p1, STARTUP, textFlash(radacina).encode("ascii"))
		finally:
			if dem1:
				dem1()
	return True, _(STERS) % loc
