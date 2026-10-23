# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSwap.py: fisierul de swap (memorie virtuala) pe un disc montat. O singura logica pentru ecranul de pe televizor
# (Screens/SwapManager.py, Meniu > Setari > Inregistrari & Stocare > Swap File) si pentru pagina web /swap
# (Plugins/Extensions/HdsWebControl/disc_web.py).
#
# - discuriMontate(): discurile montate din harddiskmanager.getMountedPartitions(), fara / si /boot, numai cele al caror
#   punct de montare e un dosar; nimic detectat aici.
# - swapuriActive(): /proc/swaps, cu spatiile din cai decodate (\040, unescapeMountPath), altfel un swap activ de pe un
#   stick cu spatiu in eticheta ar parea inactiv.
# - activeaza(punct): pe discul ales, fisierul CALE_SWAPFILE de MARIME_MB_IMPLICITA MB: fallocate, iar daca nu merge (de
#   exemplu pe FAT) dd din /dev/zero; apoi drepturile 600, mkswap si swapon. opreste(punct): swapoff pe acel fisier.
#   Comenzile merg cu Components.Console, ca liste de argumente (program, argv0, argumente), fara shell, una dupa alta,
#   pe firul enigma2, fara sa-l opreasca. Cel mult o lucrare deodata (televizorul si pagina web impart aceeasi stare).
# - stareLucru(): ce se lucreaza acum sau ce s-a terminat ultima data (pagina web o arata, ecranul isi reincarca lista).
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau managerul de discuri si consola lor.

import os
import re
import time

CALE_SWAPFILE = "swapfile.hds"  # numele fisierului, facut in radacina discului ales
MARIME_MB_IMPLICITA = 512
CALE_SWAPS = "/proc/swaps"
EXCLUSE = ("/", "/boot")

LUCRU_IN_LUCRU = "in_lucru"
LUCRU_GATA = "gata"
LUCRU_EROARE = "eroare"
ACTIVEAZA = "activeaza"
OPRESTE = "opreste"

_OCTAL = re.compile(r"\\([0-7]{3})")

_stare = {"lucru": None}
_consola = [None]


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _decodeaza(cale):
	"""\\040 si celelalte coduri octale din /proc/swaps si /proc/mounts (ca Components/Harddisk.unescapeMountPath)."""
	return _OCTAL.sub(lambda m: chr(int(m.group(1), 8)), cale)


def swapuriActive(cale_swaps=None):
	"""Fisierele si partitiile de swap active acum, din /proc/swaps (fara nicio comanda)."""
	active = []
	try:
		with open(cale_swaps or CALE_SWAPS, encoding="utf-8", errors="surrogateescape") as f:
			for linie in f.readlines()[1:]:
				parti = linie.split()
				if parti:
					active.append(_decodeaza(parti[0]))
	except OSError:
		pass
	return active


def _hm(hm=None):
	if hm is not None:
		return hm
	from Components.Harddisk import harddiskmanager
	return harddiskmanager


def discuriMontate(hm=None):
	"""Partitiile montate pe care se poate face swap: fara / si /boot, numai cu punctul de montare un dosar."""
	rezultat = []
	for partitie in _hm(hm).getMountedPartitions():
		if partitie.mountpoint and partitie.mountpoint not in EXCLUSE and os.path.isdir(partitie.mountpoint):
			rezultat.append(partitie)
	return rezultat


def caleSwap(punct):
	return os.path.join(punct, CALE_SWAPFILE)


def numeDisc(partitie):
	return partitie.description or os.path.basename(partitie.mountpoint.rstrip("/")) or partitie.mountpoint


def discuri(hm=None, active=None):
	"""[{punct, nume, cale, activ}] pentru discurile montate, in ordinea ecranului."""
	active = swapuriActive() if active is None else active
	rez = []
	for p in discuriMontate(hm):
		cale = caleSwap(p.mountpoint)
		rez.append({"punct": p.mountpoint, "nume": numeDisc(p), "cale": cale, "activ": cale in active})
	return rez


def textRand(d):
	"""Randul din lista ecranului: numele, punctul de montare, ACTIV sau inactiv."""
	return "%s (%s): %s" % (d["nume"], d["punct"], _("ACTIV") if d["activ"] else _("inactiv"))


def textActive(active=None):
	active = swapuriActive() if active is None else active
	return _("Swap-uri active în acest moment: %s") % (", ".join(active) if active else _("niciunul"))


# ------------------------------------------------------------------ lucrarea

def stareLucru():
	return _stare["lucru"]


def inLucru():
	l = _stare["lucru"]
	return l is not None and l["stare"] == LUCRU_IN_LUCRU


def textLucru(lucru):
	"""Fraza pentru o lucrare: in curs (aceeasi ca pe televizor), terminata bine sau cu eroare."""
	if lucru is None:
		return ""
	punct = lucru["punct"]
	if lucru["stare"] == LUCRU_IN_LUCRU:
		if lucru["fel"] == ACTIVEAZA:
			return _("Se creează fișierul de swap pe %s ...") % punct
		return _("Se oprește swap-ul de pe %s ...") % punct
	if lucru["fel"] == ACTIVEAZA:
		if lucru["stare"] == LUCRU_GATA:
			return _("Swap-ul de pe %s e pornit.") % punct
		return _("Swap-ul nu a pornit pe %s (%s, codul %d).") % (punct, lucru.get("pas") or "", lucru.get("cod") or 0)
	if lucru["stare"] == LUCRU_GATA:
		return _("Swap-ul de pe %s s-a oprit.") % punct
	return _("Swap-ul de pe %s nu s-a oprit (codul %d).") % (punct, lucru.get("cod") or 0)


def _cons(consola=None):
	if consola is not None:
		return consola
	if _consola[0] is None:
		from Components.Console import Console
		_consola[0] = Console()
	return _consola[0]


def _incepe(fel, punct, gata):
	_stare["lucru"] = {"fel": fel, "punct": punct, "stare": LUCRU_IN_LUCRU, "pas": "", "cod": 0, "timp": time.time()}
	_stare["gata"] = gata


def _termina(stare, pas="", cod=0):
	lucru = dict(_stare["lucru"], stare=stare, pas=pas, cod=cod)
	_stare["lucru"] = lucru
	gata = _stare.pop("gata", None)
	if gata is not None:
		try:
			gata(lucru)
		except Exception as eroare:
			print("[HdsSwap] dupa lucrare: %s" % eroare)


def _discBun(punct, hm=None):
	return any(p.mountpoint == punct for p in discuriMontate(hm))


def _real(cale):
	try:
		return os.path.realpath(cale)
	except (OSError, ValueError):
		return cale


def esteActiv(cale, active=None):
	"""True cand fisierul de swap `cale` e pornit (in /proc/swaps), si sub alt nume al aceleiasi cai: punctul de montare
	din harddiskmanager poate fi un alias al locului scris in /proc/swaps."""
	active = swapuriActive() if active is None else active
	real = _real(cale)
	return any(x == cale or _real(x) == real for x in active)


def motivRefuz(cale, active=None, lstat=None):
	"""De ce nu se face fisierul de swap `cale` acum, sau None. Un swap pornit nu se rescrie: pe kernelul receptorului
	(4.4) fallocate da ETXTBSY, iar dd ar scrie zerouri peste swap-ul in folosinta. Un nume care exista si nu e un
	fisier obisnuit (dosar, legatura simbolica, dispozitiv) nu se atinge: dd ar scrie prin legatura in alta parte."""
	import stat
	if esteActiv(cale, active):
		return _("Swap-ul e deja pornit pe acest disc.")
	try:
		st = (lstat or os.lstat)(cale)
	except OSError:
		return None
	if not stat.S_ISREG(st.st_mode):
		return _("Pe disc există deja %s și nu e un fișier obișnuit. Swap-ul nu se pornește.") % CALE_SWAPFILE
	return None


def activeaza(punct, gata=None, consola=None, hm=None, chmod=None, lstat=None):
	"""Porneste lucrarea pe discul `punct` (numai un disc din discuriMontate). (True, text) daca a pornit, altfel
	(False, motivul). `gata(lucru)` se cheama la sfarsit, pe firul enigma2. Nu porneste peste un swap deja pornit si
	nici peste un swapfile.hds care nu e un fisier obisnuit (motivRefuz)."""
	if inLucru():
		return False, _("Se lucrează deja la un fișier de swap. Așteaptă să se termine.")
	if not _discBun(punct, hm):
		return False, _("Discul ales nu mai este montat. Alege din nou.")
	cale = caleSwap(punct)
	motiv = motivRefuz(cale, lstat=lstat)
	if motiv:
		return False, motiv
	cons = _cons(consola)
	chmod = chmod or os.chmod
	_incepe(ACTIVEAZA, punct, gata)

	def dupaSwapon(_date, cod, _extra=None):
		_termina(LUCRU_GATA if cod == 0 else LUCRU_EROARE, "swapon", cod)

	def dupaMkswap(_date, cod, _extra=None):
		if cod != 0:
			_termina(LUCRU_EROARE, "mkswap", cod)
			return
		cons.ePopen(("swapon", "swapon", cale), dupaSwapon)

	def drepturi():
		try:
			chmod(cale, 0o600)
		except OSError:
			_termina(LUCRU_EROARE, "chmod", 1)
			return
		cons.ePopen(("mkswap", "mkswap", cale), dupaMkswap)

	def dupaDd(_date, cod, _extra=None):
		# ca "fallocate ... || dd ...; chmod 600 ... && mkswap ... && swapon ...": drepturile se pun oricum
		drepturi()

	def dupaFallocate(_date, cod, _extra=None):
		if cod == 0:
			drepturi()
			return
		# fallocate lipseste sau nu merge pe acest sistem de fisiere (FAT): dd e mai lent, dar merge oriunde
		cons.ePopen(("dd", "dd", "if=/dev/zero", "of=" + cale, "bs=1M", "count=%d" % MARIME_MB_IMPLICITA), dupaDd)

	cons.ePopen(("fallocate", "fallocate", "-l", "%dM" % MARIME_MB_IMPLICITA, cale), dupaFallocate)
	return True, textLucru(_stare["lucru"])


def opreste(punct, gata=None, consola=None, hm=None):
	"""swapoff pe fisierul de swap al discului `punct` (numai un disc din discuriMontate). (True, text) sau (False,
	motivul)."""
	if inLucru():
		return False, _("Se lucrează deja la un fișier de swap. Așteaptă să se termine.")
	if not _discBun(punct, hm):
		return False, _("Discul ales nu mai este montat. Alege din nou.")
	cons = _cons(consola)
	_incepe(OPRESTE, punct, gata)

	def dupaSwapoff(_date, cod, _extra=None):
		_termina(LUCRU_GATA if cod == 0 else LUCRU_EROARE, "swapoff", cod)

	cons.ePopen(("swapoff", "swapoff", caleSwap(punct)), dupaSwapoff)
	return True, textLucru(_stare["lucru"])
