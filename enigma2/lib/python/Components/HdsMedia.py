# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMedia.py: fisierele pe care le arata playerul media (Plugins/Extensions/MediaPlayer) si vizualizatorul de poze
# (Plugins/Extensions/PicturePlayer), intr-un singur loc pentru ecranele de pe televizor si pentru interfata web
# (Plugins/Extensions/HdsWebControl/media_web.py, paginile /player si /poze).
#
# - Extensiile fiecarui ecran si modelul (regex) listei lui de fisiere: ecranele de pe televizor iau MODEL_PLAYER si
#   MODEL_POZE de aici (aceleasi modele ca inainte, deci televizorul arata aceleasi fisiere). Pagina web foloseste
#   aceleasi extensii, verificate pe terminatia numelui.
# - Ordinea randurilor: cheieSortare, aceeasi ca Components/FileList.sortKey (fara mari si mici, fara diacritice).
# - Radacinile pentru web: discurile montate (harddiskmanager.getMountedPartitions, ca lista de dispozitive de pe
#   televizor), FARA memoria interna "/" si fara nimic din /etc, /home, /root, /proc, /dev, /sys, /tmp, /var, /usr,
#   /bin, /sbin, /lib, /boot (pe televizor playerul arata si "Memoria interna"; din retea nu se ajunge acolo).
# - caleSigura: paza unei cai venite din retea (fara "." si "..", os.path.realpath sub o radacina, deci o legatura
#   simbolica ce iese afara e refuzata, numai extensiile ecranului).
# - listeazaDosar: dosarele si fisierele unui dosar, ca lista de pe televizor (toate dosarele, fisierele cu extensia
#   ecranului), cu marimea si data. Citeste discul: in interfata web ruleaza pe un fir separat.
# - fisiereDeSters: ce sterge "delete file" din meniul playerului (MediaPlayer.deleteFile, offlineOperations ->
#   deleteFromDisk din lib/service): o inregistrare .ts cu bucatile ei vechi (.001, .002 ...), .meta, .ap, .sc, .cuts si
#   .eit (servicedvb.cpp, getListOfFilenames), orice alt fisier al playerului cu .cuts, semnele si locul unde ai ramas
#   (servicemp3.cpp). Listele de redare (m3u, pls, e2pls) nu au stergere pe televizor ("You cannot delete this").
#
# Fisierul importa la incarcare numai os, stat si unicodedata: probele de pe PC il incarca fara receptor. Harddisk si
# HdsNavigator se iau in functii.

import os
import stat
from unicodedata import normalize, combining

# playerul media: aceleasi extensii ca lista lui de pe televizor (m3u, pls si e2pls sunt liste de redare, tipul 4098)
EXTENSII_PLAYER = ("mp2", "mp3", "ogg", "ts", "wav", "wave", "m3u", "pls", "e2pls", "mpg", "mpeg", "vob", "avi", "divx",
	"m4v", "mkv", "webm", "mka", "flv", "3gp", "ogv", "opus", "aac", "ac3", "dts", "mp4", "m4a", "dat", "flac", "mov", "m2ts")
LISTE_REDARE = ("m3u", "pls", "e2pls")
# vizualizatorul de poze
EXTENSII_POZE = ("jpeg", "jpg", "jpe", "png", "bmp", "gif")
TIPURI_POZE = {"jpeg": "image/jpeg", "jpg": "image/jpeg", "jpe": "image/jpeg", "png": "image/png", "bmp": "image/bmp",
	"gif": "image/gif"}

MODEL_PLAYER = r"(?i)^.*\.(" + "|".join(EXTENSII_PLAYER) + ")"
MODEL_POZE = r"(?i)^.*\.(" + "|".join(EXTENSII_POZE) + ")"

# etichetele detaliilor unei poze (tasta INFO, Pic_Exif), dupa numele fisierului, in ordinea lui ePicLoad.getInfo
ETICHETE_EXIF = ("EXIF-Version:", "Make:", "Camera:", "Date/Time:", "Width / Height:", "Flash used:", "Orientation:",
	"User Comments:", "Metering Mode:", "Exposure Program:", "Light Source:", "CompressedBitsPerPixel:",
	"ISO Speed Rating:", "X-Resolution:", "Y-Resolution:", "Resolution Unit:", "Brightness:", "Exposure Time:",
	"Exposure Bias:", "Distance:", "CCD-Width:", "ApertureFNumber:")

MAX_CALE = 1024
# intrari citite dintr-un dosar (un dosar urias nu tine firul la nesfarsit)
MAX_INTRARI = 5000

INTERZISE = ("/etc", "/home", "/root", "/proc", "/dev", "/sys", "/tmp", "/var", "/usr", "/bin", "/sbin", "/lib", "/boot")
# ordinea dispozitivelor, ca in lista de pe televizor (Components/FileList.STORAGE_ORDER)
ORDINE_DISPOZITIVE = {"usb": 0, "hdd": 1, "card": 2, "dvd": 3, "net": 4, "flash": 5}


def extensie(nume):
	"""Terminatia numelui (fara punct, cu litere mici), sau "" fara terminatie."""
	baza = os.path.basename(nume or "")
	return baza.rsplit(".", 1)[-1].lower() if "." in baza else ""


def cheieSortare(nume):
	"""Ordinea randurilor, aceeasi ca Components/FileList.sortKey: fara mari si mici si fara diacritice."""
	return "".join(c for c in normalize("NFKD", nume) if not combining(c)).casefold()


def _parti(cale):
	return cale.replace("\\", "/").split("/") if os.sep == "\\" else cale.split("/")


def interzis(real):
	"""True pentru o cale reala unde interfata web nu are ce cauta: radacina sistemului si dosarele lui."""
	if real == "/":
		return True
	for p in INTERZISE:
		if real == p or real.startswith(p + "/"):
			return True
	# /run e al sistemului, afara de /run/media (unde se monteaza stickurile cu nume stabile in /media)
	return real.startswith("/run/") and not real.startswith("/run/media/")


def _partitii():
	from Components.Harddisk import harddiskmanager
	return harddiskmanager.getMountedPartitions()


def radacini(partitii=None, tabel=None):
	"""Discurile din care interfata web poate alege: [{"cale", "real", "nume", "fel"}], in ordinea de pe televizor.
	Fara memoria interna "/" si fara un loc al sistemului (INTERZISE); un disc vazut de doua ori (nume stabil si locul
	real) apare o data."""
	from Components.HdsNavigator import deviceKind, deviceName, readMountTable
	if partitii is None:
		partitii = _partitii()
	if tabel is None:
		tabel = readMountTable()
	rez = []
	vazute = set()
	for n, p in enumerate(partitii):
		mp = getattr(p, "mountpoint", None)
		if not mp:
			continue
		cale = mp.rstrip("/") or "/"
		if cale == "/":
			continue
		try:
			real = os.path.realpath(cale)
		except (OSError, ValueError):
			continue
		if interzis(real) or real in vazute or not os.path.isdir(real):
			continue
		vazute.add(real)
		fel = deviceKind(cale, getattr(p, "device", None), tabel)
		nume = deviceName(cale, getattr(p, "description", ""), getattr(p, "device", None), fel, tabel)
		rez.append((ORDINE_DISPOZITIVE.get(fel, 9), n, {"cale": cale, "real": real, "nume": nume, "fel": fel}))
	rez.sort(key=lambda x: x[:2])
	return [x[2] for x in rez]


def radacinaPentru(real, rad):
	"""Radacina (din `rad`) care tine calea reala `real`, sau None."""
	for r in rad:
		if real == r["real"] or real.startswith(os.path.join(r["real"], "")):
			return r
	return None


def caleSigura(cale, rad, extensii=None, dosar=False):
	"""(cale, real) daca `cale` (cale pentru Python, venita din retea) e un fisier cu una din `extensii` (sau un dosar,
	cu dosar=True) sub una din radacinile `rad`; altfel None. Fara "." si "..", calea reala (legaturile urmate) trebuie
	sa ramana sub radacina, iar terminatia se cere si numelui cerut, si celui real."""
	if not cale or len(cale) > MAX_CALE or "\0" in cale or not os.path.isabs(cale):
		return None
	if any(x in (".", "..") for x in _parti(cale)):
		return None
	try:
		real = os.path.realpath(cale)
	except (OSError, ValueError):
		return None
	if interzis(real) or radacinaPentru(real, rad) is None:
		return None
	if dosar:
		return (cale, real) if os.path.isdir(real) else None
	if extensii is not None and (extensie(cale) not in extensii or extensie(real) not in extensii):
		return None
	return (cale, real) if os.path.isfile(real) else None


def listeazaDosar(dosar, extensii, rad=None):
	"""(dosare, fisiere, taiat) din `dosar` (cale pentru Python): dosare = [(nume, cale)], fisiere = [(nume, cale, marime,
	data)], fiecare in ordinea cheieSortare, ca lista de pe televizor: toate dosarele, fisierele cu una din `extensii`.
	Cu `rad`, o legatura simbolica ce duce in afara radacinilor nu se arata. taiat = True daca dosarul are mai mult de
	MAX_INTRARI intrari. None daca dosarul nu se poate citi."""
	try:
		nume = os.listdir(dosar)
	except OSError:
		return None
	taiat = len(nume) > MAX_INTRARI
	dosare = []
	fisiere = []
	for n in nume[:MAX_INTRARI]:
		cale = os.path.join(dosar, n)
		try:
			st = os.stat(cale)
		except OSError:
			continue
		if rad is not None and os.path.islink(cale):
			try:
				real = os.path.realpath(cale)
			except (OSError, ValueError):
				continue
			if interzis(real) or radacinaPentru(real, rad) is None:
				continue
		if stat.S_ISDIR(st.st_mode):
			dosare.append((n, cale))
		elif stat.S_ISREG(st.st_mode) and extensie(n) in extensii:
			fisiere.append((n, cale, st.st_size, int(st.st_mtime)))
	dosare.sort(key=lambda x: cheieSortare(x[0]))
	fisiere.sort(key=lambda x: cheieSortare(x[0]))
	return dosare, fisiere, taiat


# inregistrarile (serviciul DVB, lib/service/servicedvb.cpp): fisierele care pleaca odata cu ele
EXTENSII_DVB = ("ts",)
INSOTITE_DVB = (".meta", ".ap", ".sc", ".cuts", ".hdsdecodare")
# bucatile vechi ale unei inregistrari impartite (enigma 1): cel mult atatea
MAX_BUCATI = 999


def fisiereDeSters(real):
	"""Caile pe care le sterge televizorul pentru fisierul `real` (cale reala, deja verificata cu caleSigura), in
	ordinea din lib/service, numai cele care exista: fisierul, apoi bucatile .001... (pana la prima lipsa), .meta, .ap,
	.sc, .cuts, .hdsdecodare, .eit la o inregistrare .ts; fisierul si .cuts la celelalte. [] pentru o lista de redare."""
	ext = extensie(real)
	if ext in LISTE_REDARE or not ext:
		return []
	cai = [real]
	if ext in EXTENSII_DVB:
		for n in range(1, MAX_BUCATI + 1):
			bucata = "%s.%03d" % (real, n)
			if not os.path.isfile(bucata):
				break
			cai.append(bucata)
		cai += [real + x for x in INSOTITE_DVB]
		cai.append(real[:-len(ext) - 1] + ".eit")
	else:
		cai.append(real + ".cuts")
	return [cai[0]] + [c for c in cai[1:] if os.path.lexists(c)]


def pozeDinDosar(dosar):
	"""Caile pozelor dintr-un dosar, in ordinea listei de pe televizor (numai numele, fara sa citeasca fiecare fisier:
	vizualizatorul sare singur peste ce nu e poza). [] daca dosarul nu se poate citi."""
	try:
		nume = os.listdir(dosar)
	except OSError:
		return []
	pastrate = [n for n in nume[:MAX_INTRARI] if extensie(n) in EXTENSII_POZE]
	pastrate.sort(key=cheieSortare)
	return [os.path.join(dosar, n) for n in pastrate]
