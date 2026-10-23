# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDiscuri.py: initializarea (formatarea) si verificarea discurilor si a stick-urilor USB. O singura logica pentru
# ecranele de pe televizor (Screens/HarddiskSetup.py: HarddiskSelection, HarddiskFsckSelection, HarddiskSetup,
# HarddiskWait; Meniu > Setari > Inregistrari & Stocare > Format Hard Drive / Check Disk Health) si pentru pagina web
# /discuri (Plugins/Extensions/HdsWebControl/disc_web.py).
#
# CE SE OFERA (discuriOferite): hard diskurile din harddiskmanager.hdd (nedetasabile, ca HDDList) si, in plus,
# stick-urile si cititoarele de carduri USB (detasabile: /sys/block/sdX/removable = 1, cu mediu inauntru). Niciodata
# discul de pe care porneste sistemul, memoria interna (mmcblk) sau alte nume decat sd* si hd*.
#
# CE SE SCRIE PE DISC (formateaza): o singura partitie de la sectorul 2048 (1 MiB, aliniata), facuta cu sfdisk dupa ce
# se sterg semnaturile vechi (--wipe always, si pe partitia noua), apoi sistemul de fisiere:
#   - ext4 pe hard diskuri (singurul) si, al doilea in alegere, pe stick-uri: mkfs.ext4 al imaginii (e2fsprogs 1.47.3; /etc/mke2fs.conf al
#     imaginii nu cere orphan_file, deci nucleul 4.4 il monteaza), fara blocuri rezervate (-m 0), pe discurile de peste
#     4 GB cu -T largefile (un inod la 1 MB, ca inainte). ext4 tine fisiere oricat de mari (inregistrarile si timeshift-ul),
#     se repara singur dupa o oprire brusca si e sistemul pe care receptorul il foloseste si pentru el; un calculator
#     cu Windows nu il citeste fara programe in plus;
#   - FAT32 numai pe stick-uri, primul in alegere (televizor si web): mkfs.fat -F 32 (dosfstools 4.2 din imagine), partitia de tip c. Il citeste
#     orice calculator si de pe el scrie Maintenance Mode imaginea pe receptor (dosarul amiko/), dar un fisier are cel
#     mult 4 GB: o inregistrare lunga se rupe in bucati;
#   - exFAT NU: imaginea nu are mkfs.exfat (nici exfatprogs, nici exfat-utils, verificat in manifestul imaginii 0.3.0)
#     si nucleul 4.4.35 al receptorului nu monteaza exFAT; NTFS nu: ntfs-3g din imagine numai monteaza.
# Eticheta: HDSATELIT. Dupa scriere, sistemul montat de baza (udev mount.sh) si enigma2 (Harddisk.py, legaturile
# /media/hdd, /media/usb...) primesc evenimentul "add" al partitiei noi, ca la un stick pus in receptor; lucrarea
# asteapta montarea si face dosarul movie. Inainte nu se monta nimic: Harddisk.mount() cauta discul in /etc/fstab, pe
# care imaginea nu il are (Harddisk.initialize, check, mount si mkfs nu mai sunt chemate de nimic din imagine).
# Tipul vechi al partitiei nu poate fi citit de enigma2 in timpul formatarii: la "remove" (sfdisk reciteste tabela)
# /etc/udev/scripts/device-info.sh sterge /dev/fstype/<partitie>, iar la "add" fara sistem de fisiere (semnaturile
# sterse) nu scrie nimic; Harddisk.mountIfNeeded asteapta deci tipul nou si monteaza numai dupa mkfs.
#
# VERIFICAREA (verifica): fiecare partitie cu ext2, ext3 sau ext4 (fsck.ext4 -f -p) sau FAT (fsck.fat -a), apoi fiecare
# montare de dinainte se pune la loc exact cum era (acelasi loc, acelasi tip, aceleasi optiuni), deci legaturile
# /media/hdd si /media/usb raman bune.
#
# INAINTE DE LUCRU (cu discul ales):
#   - continut(): ce se pierde, spus pe nume: copiile setarilor HD Satelit (hdsatelit/copii-setari, citite de
#     restaurarea de la prima pornire), imaginea pentru scrierea receptorului (amiko/<model>/ din Maintenance Mode) si
#     alte imagini (<dosar>/<model>/rootfs.tar.bz2), inregistrarile din movie/, fisierul de swap, cat e ocupat;
#   - folosire(): swap-ul pornit pe disc (refuz si pe televizor si in web: altfel discul nu se poate demonta),
#     timeshift-ul sau o inregistrare care scrie pe disc, un fisier deschis de receptor pe disc (de pilda un film redat);
#   - inregistrarile receptorului: una in curs sau una care incepe in mai putin de PRAG_INREGISTRARE_S secunde.
#   Pagina web refuza formatarea si verificarea in toate aceste cazuri (motiveRefuz); televizorul le spune in intrebare
#   si omul alege (afara de swap, unde discul nu s-ar putea demonta).
# PRAG_INREGISTRARE_S = 10 minute: o formatare (stergere, partitie, sistem de fisiere, montare) tine pana la doua
# minute, o verificare a unui disc mare cateva minute; intre timp discul nu e montat, deci o inregistrare care ar
# porni atunci pe el ar cadea. Zece minute acopera lucrarea si pregatirea inregistrarii (comutarea pe canal se face
# inainte de inceput), cu rezerva; e mai mult decat cele 6 minute ale intrebarii de oprire (TryQuitMainloop), fiindca
# o repornire tine sub un minut.
#
# - ruleaza() / pornesteFir(): lucrarea pe un fir separat (si pe televizor: ecranul de asteptare intreaba starea, deci
#   interfata ramane vie si evenimentele discului ajung la enigma2), o singura lucrare deodata; stareLucru(),
#   textLucru(): progresul si rezultatul cu textele televizorului ("Initializing Harddisk...", "Everything is fine",
#   "Unable to initialize harddisk. Error: ...").
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau managerul de discuri, dosarele si uneltele
# (Unelte: comenzile, /proc/mounts, /proc/swaps, asteptarile).

import os
import re
import threading
import time

INITIALIZARE = "formatare"
VERIFICARE = "verificare"
FELURI = (INITIALIZARE, VERIFICARE)

LUCRU_IN_LUCRU = "in_lucru"
LUCRU_GATA = "gata"
LUCRU_EROARE = "eroare"

EXT4 = "ext4"
FAT32 = "vfat"
# ordinea alegerii pe un stick: FAT32 primul (il citeste orice calculator, de pe el scrie Maintenance Mode imaginea),
# ext4 al doilea; pe un hard disk numai ext4 (sisteme)
SISTEME = (FAT32, EXT4)
ETICHETA = "HDSATELIT"
# tipul partitiei in tabela MBR: Linux, respectiv W95 FAT32 (LBA)
TIP_PARTITIE = {EXT4: "83", FAT32: "c"}
INCEPUT_PARTITIE = 2048
MARE_MB = 4 * 1024

# vezi capul fisierului
PRAG_INREGISTRARE_S = 600
ASTEAPTA_PARTITIA_S = 15
ASTEAPTA_MONTAREA_S = 30

# numele pe care Harddisk.model() le stie (hdX: /proc/ide, sdX: /sys/block/.../device); memoria interna (mmcblk) si
# discurile NVMe nu sunt oferite
_DISC_RX = re.compile(r"^(sd[a-z]+|hd[a-z]+)$")
_STICK_RX = re.compile(r"^sd[a-z]+$")
_OCTAL = re.compile(r"\\([0-7]{3})")

DOSAR_COPII = "hdsatelit/copii-setari"
DOSAR_RECUPERARE = "amiko"
FISIER_IMAGINE = "rootfs.tar.bz2"
DOSAR_FILME = "movie"
FISIER_SWAP = "swapfile.hds"
EXT_FILME = (".ts",)
MAX_LISTARE = 5000

# Erorile, cu textele lui Harddisk.errorList (aceleasi coduri: rezultatul negativ e locul in lista)
ERORI = ("Everything is fine", "Creating partition failed", "Mkfs failed", "Mount failed", "Create movie folder failed",
	"Fsck failed", "Please Reboot", "Filesystem contains uncorrectable errors", "Unmount failed",
	"Pe disc nu e niciun sistem de fișiere pe care receptorul îl poate verifica (ext2, ext3, ext4 sau FAT).")
E_PARTITIE = -1
E_MKFS = -2
E_MONTARE = -3
E_FILME = -4
E_FSCK = -5
E_REPORNIRE = -6
E_NEREPARABIL = -7
E_DEMONTARE = -8
E_FARA_SISTEM = -9

_stare = {"lucru": None}
_lacat = threading.Lock()


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def N_(text):
	return text


# textele de mai jos se traduc la afisare
N_("Pe disc nu e niciun sistem de fișiere pe care receptorul îl poate verifica (ext2, ext3, ext4 sau FAT).")


def _jurnal(text):
	print("[HdsDiscuri] %s" % text)


def _hm(hm=None):
	if hm is not None:
		return hm
	from Components.Harddisk import harddiskmanager
	return harddiskmanager


# ------------------------------------------------------------------ uneltele (comenzi si fisiere ale sistemului)

class Unelte(object):
	"""Ce atinge sistemul: comenzile (liste de argumente, fara shell), /proc/mounts, /proc/swaps, /dev, sysfs si
	asteptarile. Probele de pe PC dau o subclasa."""
	sys_block = "/sys/block"
	sys_class_block = "/sys/class/block"
	dev = "/dev"
	proc_mounts = "/proc/mounts"
	proc_swaps = "/proc/swaps"
	dosar_fd = "/proc/self/fd"
	fstype = "/dev/fstype"

	def ruleaza(self, argumente, date=None):
		"""Codul de iesire al programului (127 cand nu porneste, ca /bin/sh)."""
		import subprocess
		_jurnal("ruleaza: %s" % " ".join(argumente))
		try:
			if date is None:
				return subprocess.call(list(argumente), stdin=subprocess.DEVNULL)
			return subprocess.run(list(argumente), input=date).returncode
		except OSError:
			return 127

	def iesire(self, argumente):
		"""Textul scris de program (gol la eroare)."""
		import subprocess
		try:
			return subprocess.run(list(argumente), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
				stderr=subprocess.DEVNULL).stdout.decode("utf-8", "replace")
		except OSError:
			return ""

	def montari(self):
		"""[(sursa, locul, tipul, optiunile)] din /proc/mounts, in ordinea lor."""
		rez = []
		try:
			with open(self.proc_mounts, encoding="utf-8", errors="surrogateescape") as f:
				for rand in f:
					p = rand.split()
					if len(p) >= 4:
						rez.append((p[0], _OCTAL.sub(lambda m: chr(int(m.group(1), 8)), p[1]), p[2], p[3]))
		except (IOError, OSError):
			pass
		return rez

	def swapuri(self):
		rez = []
		try:
			with open(self.proc_swaps, encoding="utf-8", errors="surrogateescape") as f:
				for rand in f.readlines()[1:]:
					p = rand.split()
					if p:
						rez.append(_OCTAL.sub(lambda m: chr(int(m.group(1), 8)), p[0]))
		except (IOError, OSError):
			pass
		return rez

	def deschise(self):
		"""Fisierele tinute deschise de procesul acesta (enigma2): caile reale."""
		rez = []
		try:
			nume = os.listdir(self.dosar_fd)
		except OSError:
			return rez
		for n in nume:
			try:
				rez.append(os.readlink(os.path.join(self.dosar_fd, n)))
			except OSError:
				pass
		return rez

	def exista(self, cale):
		return os.path.exists(cale)

	def asteapta(self, secunde):
		time.sleep(secunde)

	def scrie(self, cale, text):
		try:
			with open(cale, "w", encoding="utf-8") as f:
				f.write(text)
			return True
		except (IOError, OSError) as eroare:
			_jurnal("%s: %s" % (cale, eroare))
			return False

	def faDosar(self, cale):
		try:
			os.makedirs(cale, exist_ok=True)
			return True
		except OSError as eroare:
			_jurnal("dosarul %s: %s" % (cale, eroare))
			return False

	def tipSistem(self, dispozitiv):
		"""Sistemul de fisiere de pe /dev/<dispozitiv>: dupa udev (/dev/fstype, scris de device-info.sh), altfel blkid."""
		try:
			with open(os.path.join(self.fstype, dispozitiv), encoding="utf-8", errors="replace") as f:
				t = f.read().strip()
			if t:
				return t
		except (IOError, OSError):
			pass
		return self.iesire(("blkid", "-o", "value", "-s", "TYPE", _cale(self.dev, dispozitiv))).strip()


UNELTE = Unelte()


def _u(unelte=None):
	return unelte if unelte is not None else UNELTE


def _cale(*parti):
	"""Calea unui dispozitiv sau a unui fisier din /sys, mereu cu "/" (si in probele de pe PC)."""
	return "/".join([parti[0].rstrip("/")] + [p.strip("/") for p in parti[1:]])


# ------------------------------------------------------------------ discurile oferite

def numePartitie(disc, n):
	"""Numele partitiei n a discului, ca la nucleu: sda -> sda1, mmcblk0 -> mmcblk0p1, loop7 -> loop7p1."""
	return "%s%s%d" % (disc, "p" if disc[-1:].isdigit() else "", n)


def _citeste(cale):
	try:
		with open(cale, encoding="utf-8", errors="replace") as f:
			return f.read().strip()
	except (IOError, OSError):
		return ""


class DiscDetasabil(object):
	"""Un stick sau un cititor de carduri USB (removable = 1): ce arata ecranele, ca Harddisk (model, magistrala,
	capacitatea). Nu porneste nimic (Harddisk porneste hdparm si ceasul de somn al discului)."""
	detasabil = True

	def __init__(self, device, sys_block="/sys/block"):
		self.device = device
		self.sys_block = sys_block

	def _sys(self, nume):
		return os.path.join(self.sys_block, self.device, nume)

	def model(self):
		furnizor = _citeste(self._sys("device/vendor"))
		model = _citeste(self._sys("device/model"))
		if not furnizor and not model:
			return "USB"
		return furnizor + "(" + model + ")"

	def bus(self):
		return "USB"

	def diskSize(self):
		try:
			cap = int(_citeste(self._sys("size")))
		except ValueError:
			return 0
		return cap // 1000 * 512 // 1000

	def capacity(self):
		cap = self.diskSize()
		if cap == 0:
			return ""
		return "%d.%03d GB" % (cap // 1000, cap % 1000)


def textDisc(hdd):
	"""Textul din lista televizorului (HarddiskManager.HDDList): "model - magistrala (capacitate)"."""
	text = hdd.model() + " - " + hdd.bus()
	cap = hdd.capacity()
	if cap != "":
		text += " (" + cap + ")"
	return text


def esteDetasabil(hdd):
	return bool(getattr(hdd, "detasabil", False))


def _detasabile(hm, sys_block, luate):
	"""Stick-urile si cititoarele USB: sdX cu removable = 1 si cu mediu (marimea peste 0)."""
	sistem = getattr(hm, "system_disk", None)
	rez = []
	try:
		nume = sorted(os.listdir(sys_block))
	except OSError:
		return rez
	for n in nume:
		if not _STICK_RX.match(n) or n in luate or n == sistem:
			continue
		if _citeste(os.path.join(sys_block, n, "removable")) != "1":
			continue
		try:
			if int(_citeste(os.path.join(sys_block, n, "size")) or "0") <= 0:
				continue
		except ValueError:
			continue
		rez.append(DiscDetasabil(n, sys_block))
	return rez


def discuriOferite(hm=None, sys_block="/sys/block"):
	"""[(text, disc)]: hard diskurile (ca HDDList) apoi stick-urile USB, fara discul sistemului si fara memoria
	interna."""
	hm = _hm(hm)
	sistem = getattr(hm, "system_disk", None)
	rez = []
	luate = set()
	for hdd in list(getattr(hm, "hdd", [])):
		dispozitiv = getattr(hdd, "device", "") or ""
		if not _DISC_RX.match(dispozitiv) or dispozitiv == sistem:
			continue
		luate.add(dispozitiv)
		try:
			rez.append((textDisc(hdd), hdd))
		except Exception as eroare:
			_jurnal("%s nu se poate citi: %s" % (dispozitiv, eroare))
	for stick in _detasabile(hm, sys_block, luate):
		try:
			rez.append((textDisc(stick), stick))
		except Exception as eroare:
			_jurnal("%s nu se poate citi: %s" % (stick.device, eroare))
	return rez


def discul(dispozitiv, hm=None, sys_block="/sys/block"):
	"""discul cu numele `dispozitiv` (de exemplu "sda"), numai dintre discurile oferite; altfel None."""
	for _text, hdd in discuriOferite(hm, sys_block):
		if hdd.device == dispozitiv:
			return hdd
	return None


def sisteme(hdd):
	"""Sistemele de fisiere de ales la formatare, in ordinea alegerii: ext4 pe hard diskuri, FAT32 sau ext4 pe
	stick-uri."""
	return SISTEME if esteDetasabil(hdd) else (EXT4,)


def sistemImplicit(hdd):
	"""Sistemul folosit cand nu e ales altul: primul din alegere (FAT32 pe un stick, ext4 pe un hard disk)."""
	return sisteme(hdd)[0]


def textSistem(sistem):
	if sistem == FAT32:
		return _("FAT32: se citește pe orice calculator; un fișier are cel mult 4 GB, deci o înregistrare lungă se "
			"rupe în bucăți")
	return _("ext4: pentru înregistrări și timeshift, fișiere oricât de mari; un calculator cu Windows nu îl citește")


def numeSistem(sistem):
	return "FAT32" if sistem == FAT32 else "ext4"


def etichetaSistem(sistem):
	"""Randul scurt din alegerea de pe televizor (ChoiceBox); explicatia intreaga e in intrebare (textSistem)."""
	if sistem == FAT32:
		return _("FAT32: se citește pe orice calculator")
	return _("ext4: pentru înregistrări și timeshift")


def butonDa(hdd, fel):
	"""Textul raspunsului Da al intrebarii (televizor si web)."""
	if fel != INITIALIZARE:
		return _("Da, verifică")
	return _("Da, formatează") if esteDetasabil(hdd) else _("Da, inițializează")


def _montari(mounts=None):
	if mounts is not None:
		return mounts
	from Components.Harddisk import readMounts
	return readMounts()


def partitii(dispozitiv, sys_block="/sys/block", mounts=None):
	"""[{"nume": "sda1", "montare": ["/media/hdd"]}] pentru partitiile discului (ca getBlockDevInfo: intrarile din
	/sys/block/<disc> care incep cu numele discului)."""
	try:
		nume = sorted(x for x in os.listdir(os.path.join(sys_block, dispozitiv)) if x.startswith(dispozitiv))
	except OSError:
		nume = []
	tabel = _montari(mounts)
	rez = []
	for p in nume:
		dev = "/dev/" + p
		rez.append({"nume": p, "montare": [m for s, m in tabel if s == dev]})
	return rez


def descriere(hdd, sys_block="/sys/block", mounts=None):
	"""Ce arata ecranul HarddiskSetup (Model, Capacity, Bus) si, in plus, partitiile, montarile si felul discului."""
	return {
		"dispozitiv": hdd.device,
		"text": textDisc(hdd),
		"model": hdd.model(),
		"capacitate": hdd.capacity(),
		"magistrala": hdd.bus(),
		"detasabil": esteDetasabil(hdd),
		"sisteme": list(sisteme(hdd)),
		"partitii": partitii(hdd.device, sys_block, mounts),
	}


# ------------------------------------------------------------------ ce e pe disc si cine il foloseste

def _alDiscului(sursa, disc, dev="/dev"):
	"""True cand /dev/<sursa> e discul sau o partitie a lui (sda, sda1; nu sdaa)."""
	baza = _cale(dev, disc)
	if not sursa.startswith(baza):
		return False
	rest = sursa[len(baza):]
	return rest == "" or re.match(r"^p?\d+$", rest) is not None


def montariDisc(disc, unelte=None):
	"""[(sursa, locul, tipul, optiunile)] ale discului si ale partitiilor lui."""
	u = _u(unelte)
	rez = []
	for sursa, loc, tip, optiuni in u.montari():
		real = sursa
		if sursa.startswith("/dev/") and not _alDiscului(sursa, disc, u.dev):
			try:
				real = os.path.realpath(sursa)
			except (OSError, ValueError):
				real = sursa
		if _alDiscului(sursa, disc, u.dev) or _alDiscului(real, disc, u.dev):
			rez.append((sursa, loc, tip, optiuni))
	return rez


def _sub(cale, puncte):
	"""cale e chiar unul din puncte sau sub el."""
	cale = (cale or "").rstrip("/") + "/"
	for p in puncte:
		p = p.rstrip("/") + "/"
		if p != "/" and cale.startswith(p):
			return True
	return False


def _real(cale):
	try:
		return os.path.realpath(cale)
	except (OSError, ValueError):
		return cale


def _marime(octeti):
	if octeti >= 1024 ** 3:
		return "%.1f GB" % (octeti / 1024.0 ** 3)
	return "%d MB" % (octeti // (1024 * 1024))


def _listeaza(dosar):
	try:
		return sorted(os.listdir(dosar))[:MAX_LISTARE]
	except OSError:
		return []


def continut(puncte):
	"""Ce se pierde la formatare, spus pe nume, din locurile unde e montat discul (numai citiri scurte: listari de
	dosar, fara cautare in adancime). [texte]"""
	rez = []
	copii = []
	imagini = []
	alte_imagini = []
	filme = 0
	swap = False
	ocupat = 0
	try:
		from Components.HdsCopieSetari import TIPAR_NUME
	except ImportError:
		TIPAR_NUME = re.compile(r"^\d{8}-\d{6}-")
	for p in puncte:
		dosar_copii = os.path.join(p, *DOSAR_COPII.split("/"))
		for n in _listeaza(dosar_copii):
			if TIPAR_NUME.match(n) and os.path.isdir(os.path.join(dosar_copii, n)):
				copii.append(n)
		recuperare = os.path.join(p, DOSAR_RECUPERARE)
		for n in _listeaza(recuperare):
			d = os.path.join(recuperare, n)
			if os.path.isfile(os.path.join(d, FISIER_IMAGINE)) or os.path.isfile(os.path.join(d, "kernel.bin")):
				imagini.append(DOSAR_RECUPERARE + "/" + n)
		for n in _listeaza(p):
			d = os.path.join(p, n)
			if n == DOSAR_RECUPERARE or n.startswith(".") or not os.path.isdir(d) or os.path.islink(d):
				continue
			for m in _listeaza(d)[:50]:
				if os.path.isfile(os.path.join(d, m, FISIER_IMAGINE)):
					alte_imagini.append(n)
					break
		for n in _listeaza(os.path.join(p, DOSAR_FILME)):
			if n.lower().endswith(EXT_FILME):
				filme += 1
		if os.path.isfile(os.path.join(p, FISIER_SWAP)):
			swap = True
		try:
			s = os.statvfs(p)
			ocupat += (s.f_blocks - s.f_bfree) * s.f_frsize
		except (OSError, AttributeError):
			pass
	if copii:
		copii.sort()
		rez.append(_("Copiile de siguranță ale setărilor HD Satelit: %d (cea mai nouă: %s). Restaurarea de la prima "
			"pornire nu le mai găsește.") % (len(copii), copii[-1]))
	for i in imagini:
		rez.append(_("Imaginea pentru scrierea receptorului din Maintenance Mode (%s).") % i)
	if alte_imagini:
		rez.append(_("Alte imagini pentru receptor: %s.") % ", ".join(sorted(alte_imagini)[:5]))
	if filme:
		rez.append(_("Înregistrări: %d (dosarul movie).") % filme)
	if swap:
		rez.append(_("Fișierul de swap (%s).") % FISIER_SWAP)
	if ocupat >= 1024 * 1024:
		rez.append(_("Ocupat acum pe disc: %s.") % _marime(ocupat))
	return rez


def stareInregistrari(nav=None, config=None, InfoBar=None):
	"""Ce stie receptorul acum (pe firul enigma2): {"in_curs": numarul, "urmatoarea": ora (0 = niciuna), "fisiere":
	[fisierele inregistrarilor care merg], "timeshift": locul timeshift-ului pornit sau ""}."""
	rez = {"in_curs": 0, "urmatoarea": 0, "fisiere": [], "timeshift": ""}
	if nav is None:
		try:
			import NavigationInstance
			nav = NavigationInstance.instance
		except Exception:
			nav = None
	if nav is not None:
		try:
			rez["in_curs"] = len(nav.getRecordings() or [])
		except Exception as eroare:
			_jurnal("inregistrarile: %r" % eroare)
		try:
			urm = nav.RecordTimer.getNextRecordingTime()
			if urm and urm > 0:
				rez["urmatoarea"] = int(urm)
		except Exception as eroare:
			_jurnal("urmatoarea inregistrare: %r" % eroare)
		try:
			for t in nav.RecordTimer.timer_list:
				if getattr(t, "state", 0) == 2 and getattr(t, "Filename", None):   # TimerEntry.StateRunning
					rez["fisiere"].append(t.Filename)
		except Exception as eroare:
			_jurnal("fisierele inregistrarilor: %r" % eroare)
	try:
		if InfoBar is None:
			from Screens.InfoBar import InfoBar
		ib = InfoBar.instance
		if ib is not None and getattr(ib, "timeshift_enabled", False):
			if config is None:
				from Components.config import config
			rez["timeshift"] = config.usage.timeshift_path.value
	except Exception:
		pass
	return rez


def folosire(disc, inregistrari=None, unelte=None):
	"""Cine foloseste discul acum: [(cheie, text)], cheile "swap", "timeshift", "inregistrare", "deschis"."""
	u = _u(unelte)
	inregistrari = inregistrari or {}
	montari = montariDisc(disc, u)
	puncte = [loc for _s, loc, _t, _o in montari]
	reale = puncte + [_real(p) for p in puncte]
	rez = []
	for s in u.swapuri():
		if _alDiscului(s, disc, u.dev) or (puncte and (_sub(s, reale) or _sub(_real(s), reale))):
			rez.append(("swap", _("Swap-ul e pornit pe acest disc (%s). Oprește-l întâi din Fișier de swap.") % s))
			break
	if not puncte:
		return rez
	ts = inregistrari.get("timeshift") or ""
	deschise = u.deschise()
	timeshift = any(_sub(f, reale) and os.path.basename(f).startswith("timeshift") for f in deschise)
	if ts and _sub(_real(ts), reale):
		timeshift = True
	if timeshift:
		rez.append(("timeshift", _("Timeshift-ul (pauza) scrie acum pe acest disc.")))
	# Filename al unei inregistrari e calea fara extensie; pe disc se scriu <Filename>.ts, .ap, .sc, .meta
	inceputuri = [x for f in inregistrari.get("fisiere") or [] for x in (f, _real(f))]
	scrise = [f for f in inregistrari.get("fisiere") or [] if _sub(f, puncte) or _sub(_real(f), reale)]
	if scrise:
		rez.append(("inregistrare", _("O înregistrare scrie acum pe acest disc: %s.") % os.path.basename(scrise[0])))
	altele = [f for f in deschise if _sub(f, reale) and not os.path.basename(f).startswith("timeshift")
		and not any(f.startswith(x) for x in inceputuri)]
	if altele:
		rez.append(("deschis", _("Receptorul ține deschis un fișier de pe disc (de pildă un film care se redă): %s.")
			% os.path.basename(altele[0])))
	return rez


def motiveInregistrari(inregistrari, acum=None):
	"""Inregistrarile receptorului care opresc lucrarea din web: [(cheie, text)]."""
	inregistrari = inregistrari or {}
	acum = time.time() if acum is None else acum
	rez = []
	if inregistrari.get("in_curs"):
		rez.append(("in_curs", _("O înregistrare e în curs.")))
	urm = inregistrari.get("urmatoarea") or 0
	if urm and urm - acum < PRAG_INREGISTRARE_S:
		rez.append(("curand", _("O înregistrare începe în mai puțin de %d minute.") % (PRAG_INREGISTRARE_S // 60)))
	return rez


def motiveRefuz(disc, inregistrari=None, unelte=None, acum=None):
	"""Pentru pagina web: tot ce opreste formatarea sau verificarea discului acum: [(cheie, text)]."""
	return motiveInregistrari(inregistrari, acum) + folosire(disc, inregistrari, unelte)


def intrebare(hdd, fel, sistem=None, inregistrari=None, unelte=None, acum=None):
	"""(intrebarea, [detaliile]) ca pe televizor, cu ce se pierde si cine foloseste discul."""
	u = _u(unelte)
	text = textDisc(hdd)
	if fel == INITIALIZARE:
		sistem = sistem if sistem in sisteme(hdd) else sistemImplicit(hdd)
		if esteDetasabil(hdd):
			q = _("Formatezi stick-ul %s cu %s? Toate datele de pe el se pierd.") % (text, numeSistem(sistem))
		else:
			q = _("Inițializezi discul %s? Toate datele de pe disc se pierd.") % text
	else:
		q = _("Verifici sistemul de fișiere de pe %s? Poate dura mult.") % text
	detalii = [_("Model: %s") % hdd.model(), _("Capacitate: %s") % hdd.capacity()]
	montari = montariDisc(hdd.device, u)
	for sursa, loc, _t, _o in montari:
		detalii.append(_("Partiția %s e montată în %s.") % (os.path.basename(sursa), loc))
	if fel == INITIALIZARE:
		detalii.append(textSistem(sistem))
		gasite = continut([loc for _s, loc, _t, _o in montari])
		if gasite:
			detalii.append(_("Se pierd și:"))
			detalii += gasite
	else:
		detalii.append(_("Discul se demontează cât ține verificarea; înregistrările și timeshift-ul nu pot scrie pe el."))
	for _cheie, t in motiveRefuz(hdd.device, inregistrari, u, acum):
		detalii.append(t)
	return q, detalii


# ------------------------------------------------------------------ lucrarea

def stareLucru():
	return _stare["lucru"]


def inLucru():
	l = _stare["lucru"]
	return l is not None and l["stare"] == LUCRU_IN_LUCRU


def _incepe(hdd, fel, sistem):
	"""Pune starea "in lucru" pentru disc; False daca alta lucrare merge deja."""
	try:
		text = textDisc(hdd)
	except Exception:
		text = hdd.device
	with _lacat:
		if inLucru():
			return False
		_stare["lucru"] = {"fel": fel, "dispozitiv": hdd.device, "text_disc": text, "stare": LUCRU_IN_LUCRU,
			"sistem": sistem or "", "rezultat": None, "eroare": "", "bine": "", "loc": "", "timp": time.time(),
			"sfarsit": None}
		return True


def _demonteaza(montari, u):
	"""Demonteaza (cele mai adanci locuri intai). (bun, [montarile demontate])."""
	facute = []
	for m in sorted(montari, key=lambda x: -len(x[1])):
		if u.ruleaza(("umount", m[1])) != 0:
			_jurnal("umount %s a cazut" % m[1])
			return False, facute
		facute.append(m)
	return True, facute


def _monteazaLaLoc(montari, u):
	"""Pune la loc montarile de dinainte (cele mai scurte locuri intai), cu acelasi tip si aceleasi optiuni."""
	bun = True
	for sursa, loc, tip, optiuni in sorted(montari, key=lambda x: len(x[1])):
		u.faDosar(loc)
		if u.ruleaza(("mount", "-t", tip, "-o", optiuni, sursa, loc)) != 0:
			_jurnal("mount %s %s a cazut" % (sursa, loc))
			bun = False
	return bun


def _cauta(u, conditie, secunde):
	"""Asteapta pana cand conditie() e adevarata (o data pe secunda), cel mult `secunde`."""
	for _i in range(int(secunde) + 1):
		r = conditie()
		if r:
			return r
		u.asteapta(1)
	return conditie()


def formateaza(disc, sistem=EXT4, unelte=None, marime_mb=0, verifica_nume=True):
	"""Formatarea discului `disc` (numele, de exemplu "sdb"). (rezultat, locul unde s-a montat): rezultat 0 = bine,
	negativ = locul erorii in ERORI. Ruleaza pe un fir separat (comenzi si asteptari)."""
	u = _u(unelte)
	if verifica_nume and not _DISC_RX.match(disc or ""):
		return E_PARTITIE, ""
	if sistem not in SISTEME:
		sistem = EXT4
	bun, demontate = _demonteaza(montariDisc(disc, u), u)
	if not bun:
		_monteazaLaLoc(demontate, u)
		return E_DEMONTARE, ""
	cale = _cale(u.dev, disc)
	tabela = ("label: dos\nstart=%d, type=%s\n" % (INCEPUT_PARTITIE, TIP_PARTITIE[sistem])).encode("ascii")
	if u.ruleaza(("sfdisk", "--wipe", "always", "--wipe-partitions", "always", "-q", cale), tabela) != 0:
		return E_PARTITIE, ""
	part = numePartitie(disc, 1)
	cale_part = _cale(u.dev, part)
	if not _cauta(u, lambda: u.exista(cale_part) and u.exista(os.path.join(u.sys_block, disc, part)),
			ASTEAPTA_PARTITIA_S):
		_jurnal("partitia %s nu a aparut" % part)
		return E_PARTITIE, ""
	if sistem == FAT32:
		comanda = ("mkfs.fat", "-F", "32", "-n", ETICHETA, cale_part)
	else:
		comanda = ("mkfs.ext4", "-F", "-L", ETICHETA, "-m", "0")
		if marime_mb > MARE_MB:
			comanda += ("-T", "largefile")
		comanda += (cale_part,)
	if u.ruleaza(comanda) != 0:
		return E_MKFS, ""
	# ca la un stick pus acum in receptor: udev (mount.sh) monteaza in /run/media, enigma2 pune legatura stabila
	u.scrie(_cale(u.sys_class_block, part, "uevent"), "add")
	montat = _cauta(u, lambda: [m[1] for m in montariDisc(disc, u) if os.path.basename(m[0]) == part],
		ASTEAPTA_MONTAREA_S)
	if not montat:
		return E_MONTARE, ""
	loc = montat[0]
	if not u.faDosar(os.path.join(loc, DOSAR_FILME)):
		return E_FILME, loc
	return 0, loc


def _partitiiDeVerificat(disc, u, montari):
	"""[(partitia, comanda)] pentru partitiile cu un sistem de fisiere stiut; fara partitii, discul intreg (un stick
	fara tabela de partitii)."""
	tipuri = dict((os.path.basename(s), t) for s, _l, t, _o in montari)
	try:
		nume = sorted(x for x in os.listdir(os.path.join(u.sys_block, disc)) if x.startswith(disc))
	except OSError:
		nume = []
	if not nume:
		nume = [disc]
	rez = []
	for p in nume:
		tip = tipuri.get(p) or u.tipSistem(p)
		cale = _cale(u.dev, p)
		if tip in ("ext2", "ext3", "ext4"):
			rez.append((p, ("fsck.ext4", "-f", "-p", cale), "ext"))
		elif tip in ("vfat", "msdos", "fat"):
			rez.append((p, ("fsck.fat", "-a", cale), "fat"))
	return rez


def verifica(disc, unelte=None, verifica_nume=True):
	"""Verificarea discului: fiecare partitie stiuta, apoi montarile de dinainte puse la loc. (rezultat, locul)."""
	u = _u(unelte)
	if verifica_nume and not _DISC_RX.match(disc or ""):
		return E_FSCK, ""
	montari = montariDisc(disc, u)
	de_verificat = _partitiiDeVerificat(disc, u, montari)
	if not de_verificat:
		return E_FARA_SISTEM, ""
	bun, demontate = _demonteaza(montari, u)
	if not bun:
		_monteazaLaLoc(demontate, u)
		return E_DEMONTARE, ""
	rezultat = 0
	for _p, comanda, fel in de_verificat:
		res = u.ruleaza(comanda)
		if fel == "ext":
			if res & 2 == 2:
				r = E_REPORNIRE
			elif res & 4 == 4:
				r = E_NEREPARABIL
			elif res not in (0, 1):
				r = E_FSCK
			else:
				r = 0
		else:
			r = 0 if res in (0, 1) else E_FSCK
		if r != 0 and (rezultat == 0 or r == E_NEREPARABIL):
			rezultat = r
	if not _monteazaLaLoc(montari, u) and rezultat == 0:
		rezultat = E_MONTARE
	return rezultat, (montari[0][1] if montari else "")


def _fa(hdd, fel, sistem, unelte=None):
	"""Formatarea sau verificarea si rezultatul in stare; o exceptie se tine minte si merge mai departe."""
	try:
		if fel == INITIALIZARE:
			if sistem not in sisteme(hdd):
				sistem = sistemImplicit(hdd)
			try:
				marime = int(hdd.diskSize())
			except Exception:
				marime = 0
			rezultat, loc = formateaza(hdd.device, sistem, unelte, marime)
		else:
			rezultat, loc = verifica(hdd.device, unelte)
	except Exception as eroare:
		_jurnal("%s %s: %s" % (fel, hdd.device, eroare))
		_stare["lucru"] = dict(_stare["lucru"], stare=LUCRU_EROARE, eroare=str(eroare), sfarsit=time.time())
		raise
	text_eroare = ""
	if rezultat != 0 and isinstance(rezultat, int) and 0 < -rezultat < len(ERORI):
		text_eroare = _(ERORI[-rezultat])
	_stare["lucru"] = dict(_stare["lucru"], stare=LUCRU_GATA if rezultat == 0 else LUCRU_EROARE, rezultat=rezultat,
		eroare=text_eroare, bine=_(ERORI[0]), loc=loc or "", sfarsit=time.time())
	return rezultat


def ruleaza(hdd, fel, sistem=None, unelte=None):
	"""Lucrarea pe firul care cheama (probele). Daca alta lucrare merge deja, None, fara sa faca nimic."""
	if not _incepe(hdd, fel, sistem):
		return None
	return _fa(hdd, fel, sistem, unelte)


def pornesteFir(hdd, fel, porneste=None, sistem=None, unelte=None):
	"""Lucrarea pe un fir separat (televizorul si pagina web). (True, text) daca a pornit, (False, motivul) altfel."""
	if fel not in FELURI:
		return False, _("Lucrare necunoscută.")
	if fel == INITIALIZARE and sistem is not None and sistem not in sisteme(hdd):
		return False, _("Sistemul de fișiere ales nu se poate pune pe acest disc.")
	if not _incepe(hdd, fel, sistem):
		return False, _("Se lucrează deja la un disc. Așteaptă să se termine.")

	def lucru():
		try:
			_fa(hdd, fel, sistem, unelte)
		except Exception:
			pass   # tinuta minte in stare

	if porneste is None:
		t = threading.Thread(target=lucru, name="HdsDiscuri")
		t.daemon = True
		t.start()
	else:
		porneste(lucru)
	return True, textLucru(_stare["lucru"])


def textLucru(lucru):
	"""Textele ecranelor de pe televizor: in curs (HarddiskWait), apoi rezultatul (HarddiskSetup.hddReady)."""
	if not lucru:
		return ""
	if lucru["stare"] == LUCRU_IN_LUCRU:
		return _("Initializing Harddisk...") if lucru["fel"] == INITIALIZARE else _("Checking Filesystem...")
	if lucru["stare"] == LUCRU_GATA:
		return lucru.get("bine") or _("Everything is fine")
	if lucru["fel"] == INITIALIZARE:
		inceput = _("Unable to initialize harddisk.\nError: ")
	else:
		inceput = _("Unable to complete filesystem check.\nError: ")
	return inceput + (lucru.get("eroare") or str(lucru.get("rezultat")))
