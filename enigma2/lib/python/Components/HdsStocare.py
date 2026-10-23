# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsStocare.py: „e acolo un disc adevarat?” pentru inregistrari si timeshift.
#
# De ce: pe Viper 4K V20 /media e un tmpfs de 64 KB, deci /media/hdd (si /hdd, legatura spre el)
# arata a disc, dar e memorie RAM. Locul implicit al inregistrarilor (/hdd/movie/, Tools/Directories.py) trecea de
# verificarea veche (fileExists(cale, 'w'): tmpfs-ul se poate scrie), inregistrarea pornea si cadea imediat cu „Write
# error while recording. Disk full?”. Aici locul e verificat dupa /proc/mounts: nu in RAM, nu pe memoria interna a
# receptorului (radacina; o inregistrare ar umple-o), cu o marime minima. Cand nu e un disc adevarat, inregistrarea nu
# porneste si omul primeste un mesaj limpede (RecordTimer.py, Screens/InfoBarGenerics.py).
#
# Aceeasi regula ca in Components/HdsFonturiGoogle.py (_altaPartitie, _esteInMemorie); nu o import de acolo, pentru
# ca acelea sunt functii interne ale altui modul, cu probele lor. De unit intr-un singur loc.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import os

# Sistemele de fisiere care stau in RAM: nu supravietuiesc nici macar unei reporniri (ca in HdsFonturiGoogle.py).
FS_IN_MEMORIE = ("tmpfs", "ramfs", "devtmpfs", "overlay", "squashfs", "rootfs")
# Sub atat nu e un loc de inregistrari (tmpfs-ul de /media are 64 KB; un minut HD are ~50 MB).
MINIM_DISC = 64 * 1024 * 1024


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _montari(cale_mounts="/proc/mounts"):
	lista = []
	try:
		with open(cale_mounts, "r", encoding="utf-8", errors="surrogateescape") as f:
			for linie in f:
				parti = linie.split()
				if len(parti) >= 3:
					lista.append((parti[1].replace("\\040", " "), parti[2], parti[0]))
	except (OSError, IOError):
		pass
	return lista


def montarePentru(cale, montari=None, realpath=None):
	"""(punct, fel, dispozitiv) al montarii care tine `cale` (cel mai lung punct de montare potrivit; la puncte egale,
	montarea de mai tarziu, care o acopera pe cea dinainte, ca „rootfs /” urmat de „/dev/mmcblk0p10 /”), sau None."""
	cale = (realpath or os.path.realpath)(cale)
	potrivit = None
	for punct, fel, disp in (montari if montari is not None else _montari()):
		if cale == punct or cale.startswith(punct.rstrip("/") + "/") or punct == "/":
			if potrivit is None or len(punct) >= len(potrivit[0]):
				potrivit = (punct, fel, disp)
	return potrivit


def verificaDisc(cale, montari=None, dev_radacina=None, statvfs=None, realpath=None):
	"""(bun, motiv): motiv e „” cand locul e un disc adevarat, altfel unul din „lipsa”, „ram”, „intern”, „mic”, „scriere”.
	`cale` e dosarul inregistrarilor (sau al timeshift-ului). Parametrii in plus sunt pentru probele de pe PC."""
	statvfs = statvfs or getattr(os, "statvfs", None)
	if not cale or not os.path.isdir(cale):
		return False, "lipsa"
	m = montarePentru(cale, montari, realpath)
	if m is not None and m[1] in FS_IN_MEMORIE:
		return False, "ram"
	try:
		if dev_radacina is None:
			dev_radacina = os.stat("/").st_dev
		if os.stat(cale).st_dev == dev_radacina:
			return False, "intern"
	except (OSError, IOError):
		return False, "lipsa"
	try:
		s = statvfs(cale)
		if s.f_blocks * s.f_frsize < MINIM_DISC:
			return False, "mic"
	except (OSError, IOError, AttributeError, TypeError):
		return False, "lipsa"
	if not os.access(cale, os.W_OK):
		return False, "scriere"
	return True, ""


def textMotiv(motiv, cale):
	return {
		"lipsa": _("locul „%s” nu există: nu este montat niciun disc acolo"),
		"ram": _("locul „%s” este în memoria RAM a receptorului, nu pe un disc"),
		"intern": _("locul „%s” este pe memoria internă a receptorului, prea mică pentru înregistrări"),
		"mic": _("discul din „%s” are mai puțin de 64 MB"),
		"scriere": _("pe „%s” nu se poate scrie"),
	}.get(motiv, _("locul „%s” nu este un disc")) % cale


def mesajInregistrare(motiv, cale):
	return _("Înregistrarea nu poate porni: %s. Conectează un disc sau un stick USB și alege-l ca loc pentru "
		"înregistrări.") % textMotiv(motiv, cale)


def mesajTimeshift(motiv, cale):
	return _("Timeshift nu poate porni: %s. Conectează un disc sau un stick USB și alege-l ca loc pentru "
		"timeshift.") % textMotiv(motiv, cale)


# ---------------------------------------------------------------- pauza (timeshift) refuzata de nucleu
#
# Nucleul nu da pauza unui serviciu (lib/service/servicedvb.cpp, eDVBServicePlay::timeshift) fara pista video (radio;
# si la redarea unui fisier), fara locul ales (config.usage.timeshift_path), cand statfs pe loc nu merge si cand pe loc
# sunt sub 1 GB liberi. Python primeste numai None (service.timeshift()), deci cauza se cauta aici, in aceeasi ordine,
# ca omul sa afle ce sa faca, nu ca "canalul nu poate fi pus pe pauza".

# Oglinda pragului din eDVBServicePlay::timeshift (f_bavail * f_bsize sub 1024*1024*1024 -> fara pauza); se schimba
# numai impreuna cu el. statfs din nucleu si os.statvfs dau acelasi f_bsize (pe ext4 si FAT egal cu f_frsize).
MINIM_LIBER_TIMESHIFT = 1024 * 1024 * 1024
TS_FARA_VIDEO = "fara_video"
TS_LOC = "loc"
TS_SPATIU = "spatiu"


def liberOcteti(cale, statvfs=None):
	"""Octetii liberi pe locul `cale` pentru un program obisnuit (f_bavail * f_bsize, ca nucleul), sau None."""
	statvfs = statvfs or getattr(os, "statvfs", None)
	try:
		s = statvfs(cale)
		return int(s.f_bavail) * int(s.f_bsize)
	except (OSError, IOError, AttributeError, TypeError, ValueError):
		return None


def cauzaFaraTimeshift(cale, are_video, montari=None, dev_radacina=None, statvfs=None, realpath=None):
	"""De ce nu a dat serviciul pauza: (TS_FARA_VIDEO, None) fara pista video; (TS_LOC, motiv) cand locul nu e un disc
	adevarat (verificaDisc; si calea care lipseste, ca la statfs-ul nereusit al nucleului); (TS_SPATIU, octeti liberi)
	sub MINIM_LIBER_TIMESHIFT; ("", None) cand nu se vede nicio cauza (redarea unui fisier, alta stare a nucleului)."""
	if not are_video:
		return TS_FARA_VIDEO, None
	bun, motiv = verificaDisc(cale, montari, dev_radacina, statvfs, realpath)
	if not bun:
		return TS_LOC, motiv
	liber = liberOcteti(cale, statvfs)
	if liber is not None and liber < MINIM_LIBER_TIMESHIFT:
		return TS_SPATIU, liber
	return "", None


def esteStick(cale, montari=None, realpath=None, sys_block="/sys/block"):
	"""True cand locul `cale` e pe un stick sau un cititor de carduri (/sys/block/<disc>/removable = 1, ca in
	Components/HdsDiscuri.py), False pe un hard disk sau cand nu se stie."""
	import re
	m = montarePentru(cale, montari, realpath)
	if m is None:
		return False
	nume = os.path.basename(m[2] or "")
	potrivit = re.match(r"^(sd[a-z]+|mmcblk[0-9]+)", nume)
	if not potrivit:
		return False
	try:
		with open(os.path.join(sys_block, potrivit.group(1), "removable"), "r", encoding="utf-8", errors="replace") as f:
			return f.read().strip() == "1"
	except (OSError, IOError):
		return False


def mesajTimeshiftFaraVideo():
	return _("Pauza merge numai la canalele cu imagine: posturile de radio nu se pot pune pe pauză.")


def mesajTimeshiftSpatiu(cale, liber, stick=None):
	"""Pauza nu porneste: sub 1 GB liberi pe locul ei. stick: True pe un stick, False pe un disc, None: se afla din cale."""
	if stick is None:
		stick = esteStick(cale)
	mb = max(0, int(liber) // (1024 * 1024))
	if stick:
		text = _("Nu e destul loc pentru pauză pe stick: trebuie cel puțin 1 GB liber, acum sunt %d MB.") % mb
	else:
		text = _("Nu e destul loc pentru pauză pe disc: trebuie cel puțin 1 GB liber, acum sunt %d MB.") % mb
	return (text + "\n\n" + _("Fă loc ștergând înregistrările de care nu mai ai nevoie, din lista 'Filme și înregistrări'.")
		+ "\n\n" + _("Detaliu tehnic: %s") % (_("locul pauzei este %s") % cale))
