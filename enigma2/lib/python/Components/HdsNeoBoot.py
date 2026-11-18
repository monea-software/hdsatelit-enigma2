# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsNeoBoot.py: imaginea ii da pluginului NeoBoot (gutosie si ramurile lui) ce asteapta de la o imagine OE-Alliance, fara sa
# schimbe nimic din codul pluginului. Nu atinge pornirea (/sbin/init, neoinit) si nu instaleaza nimic.
#
# Ce repara (TODO 14.11 18:37, Eduard: "pai cauta solutii, ce daca cauza e NeoBoot"; agentul NEO, runda-0013):
#   1. Traducerile stricate ale pluginurilor nu mai inchid interfata. NeoBoot isi ia textele cu gettext.dgettext("NeoBoot", ...)
#      si, daca nu le gaseste, din domeniul enigma2. Traducerea lui araba pentru "External Storage %s" e fara %s, deci
#      files/Harddisk.py face _("External Storage %s") % dev si cade cu TypeError "not all arguments converted" chiar la
#      importul modulului: pe un receptor cu interfata in araba NeoBoot si NeoReboot nu se mai incarca deloc (raportul 905961,
#      Vu+ Uno 4K SE, forum 1275). Acum gettext.dgettext si gettext.dngettext intorc textul original (englez) cand traducerea
#      are alte locuri %... decat originalul (numar, ordine, tip sau nume). Asa face si msgfmt -c la construirea traducerilor.
#      Textele enigma2 (_ pus de Language.py cu gettext.install) nu trec pe aici; numai cine cheama dgettext / dngettext.
#      Tot aici (0.7.5, MCX): un catalog cu Plural-Forms necitit (de pilda "plural=EXPRESSION", lasat din sablon) nu mai
#      opreste importul pluginului: pluralul lui trece pe regula n != 1, ca in biblioteca gettext din C (_c2py).
#   2. files/mountpoint.sh ramas gol. NeoBoot il scrie o singura data, la prima deschidere, din randurile
#      "/dev/sdXN /media/hdd" ale lui /proc/mounts. Pe 0.7.4 /media/hdd era legatura, nu montare, deci fisierul a iesit numai cu
#      "#!/bin/sh" si "exit 0"; fara el nu se monteaza /media/sdXN, neo.sh nu se mai face ("chmod: neo.sh: No such file",
#      JAKITAKI, Vu+ Zero 4K) si alegerea imaginii la OK nu merge. Din 0.7.5 /media/hdd e montare bind (Harddisk.bindName),
#      deci un fisier gol se muta deoparte (mountpoint.sh.hds-gol, nu se sterge) si NeoBoot il face din nou, bun, la
#      urmatoarea deschidere. Un fisier cu cel putin un rand de montare ramane neatins.
#   3. Marimile din panoul de discuri NeoBoot (0.7.7; ideea si multumirile: JAKITAKI, forumul Satedu). Copia veche
#      files/Harddisk.py din NeoBoot recunoaste udev numai dupa /dev/.udev. Imaginea are eudev, care isi tine datele in
#      /run/udev si nu face /dev/.udev, deci NeoBoot punea tipul -1 si dev_path gol, iar mountDevice() lua primul rand din
#      /proc/mounts (radacina): la fiecare partitie panoul arata marimea memoriei interne. Cand NeoBoot e instalat, imaginea
#      face legatura /dev/.udev -> /run/udev daca lipseste (/dev e devtmpfs, deci la fiecare pornire a interfetei), inainte
#      de importul pluginului. Harddisk.py al nostru le accepta deja pe amandoua.
#      Cu tipul udev, NeoBoot trimite la import (de doua ori) "sdparm --set=SCT=0" la fiecare disc USB. Pe o punte USB-SATA
#      dupa SAT-4 (tabelele 140 si 142), bitul STANDBY_Z citit urmeaza discul (IDENTIFY DEVICE, cuvantul 49 bit 13); cand e
#      1, scrierea lui inapoi cu timpul 0 devine ATA STANDBY IMMEDIATE: discul s-ar opri la fiecare pornire a interfetei. Imaginea opreste cronometrul discului cu
#      hdparm -S0 si il pune in repaus cu hdparm -y dupa timpul ales, deci comanda aceasta (numai ea, numai fara callback)
#      se lasa deoparte in Console.ePopen cat timp NeoBoot e instalat: discul se poarta ca inainte de legatura.
#
# Legatura: PluginComponent.readPluginList cheama pregateste() inainte de importul pluginurilor.

import gettext
import os
import re

NEOBOOT_DIRS = (
	"/usr/lib/enigma2/python/Plugins/Extensions/NeoBoot",
)
MOUNTPOINT_SH = "files/mountpoint.sh"
SUFIX_GOL = ".hds-gol"
SEMN_UDEV = "/dev/.udev"
DATE_UDEV = "/run/udev"
SDPARM_SCT_ZERO = "--set=SCT=0"

# un loc de format %: %%, %s, %5.2f, %-10s, %(nume)s, %*d
_LOC = re.compile(r"%(?:\(([^)]*)\))?[#0\- +]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?([diouxXeEfFgGcrsa%])")
# tipurile care primesc orice valoare
_ORICE = frozenset("sra")
_NUMERE = frozenset("diouxXeEfFgGc")

_verdicte = {}
_original = {}
_console = {}


def locuri(text):
	"""locurile de format % din text, fara %%: lista de (nume sau None, tip)"""
	if not text or "%" not in text:
		return []
	return [(m.group(1), m.group(2)) for m in _LOC.finditer(text) if m.group(2) != "%"]


def potrivita(original, tradus):
	"""True daca tradus poate primi aceleasi argumente % ca originalul fara sa cada"""
	if tradus == original:
		return True
	cheie = (original, tradus)
	v = _verdicte.get(cheie)
	if v is not None:
		return v
	lo, lt = locuri(original), locuri(tradus)
	if not lo:
		# originalul nu se formateaza: un "%" din traducere ("100% gata") nu e o greseala
		return True
	numite_o = [n for n, t in lo if n is not None]
	numite_t = [n for n, t in lt if n is not None]
	if numite_o or numite_t:
		# cu dictionar: o cheie lipsa din original cade (KeyError), una lasata deoparte nu
		v = bool(numite_o) and len(numite_t) == len(lt) and len(numite_o) == len(lo) and set(numite_t) <= set(numite_o)
		if v:
			tip_o = dict((n, t) for n, t in lo)
			v = all(t in _ORICE or t == tip_o[n] or (t in _NUMERE and tip_o[n] in _NUMERE) for n, t in lt)
	else:
		# cu tuplu sau o singura valoare: acelasi numar, in aceeasi ordine; %s primeste orice, un numar cere un numar
		v = len(lo) == len(lt) and all(tt in _ORICE or to == tt or (tt in _NUMERE and to in _NUMERE)
			for (n1, to), (n2, tt) in zip(lo, lt))
	if len(_verdicte) < 20000:
		_verdicte[cheie] = v
	if not v:
		print("[HdsNeoBoot] traducere cu alte locuri %%, se pastreaza originalul: %r -> %r" % (original, tradus))
	return v


# FRZ 0.7.7 (pachetul de testeri 2459, Vu+ Uno 4K SE 0.7.6: firul interfetei 4,4 s in genericpath.exists <- _dgettext, iar
# UserSkin 8,3 s in tr() la fiecare rand al listei de fisiere): gettext.dgettext cauta catalogul (gettext.find: os.path.exists pe
# fiecare limba din LANGUAGE/LC_ALL/LC_MESSAGES/LANG) la FIECARE apel, iar pluginurile il cheama pe fiecare text. Raspunsul se
# tine minte pe (domeniu, text, limba din mediu, dosarul legat cu bindtextdomain): o alta limba (pluginurile isi pun singure
# LANGUAGE) sau alt dosar dau alta cheie. Python tine minte si el cataloagele deschise, deci un .mo schimbat pe disc nu se
# vedea nici inainte pana la repornire; la fiecare citire a listei de pluginuri (pregateste) memoria se goleste.
_raspunsuri = {}
MAX_RASPUNSURI = 50000
_MEDIU_LIMBA = ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")


def _limbaMediu():
	"""limbile cerute din mediu, ca la gettext.find (prima variabila cu valoare)"""
	for v in _MEDIU_LIMBA:
		x = os.environ.get(v)
		if x:
			return x
	return ""


def _tine(cheie, raspuns):
	if len(_raspunsuri) < MAX_RASPUNSURI:
		_raspunsuri[cheie] = raspuns
	return raspuns


def _dgettext(domain, message):
	cheie = ("d", domain, message, _limbaMediu(), getattr(gettext, "_localedirs", {}).get(domain))
	r = _raspunsuri.get(cheie)
	if r is not None:
		return r
	tradus = _original["dgettext"](domain, message)
	return _tine(cheie, tradus if potrivita(message, tradus) else message)


def _dngettext(domain, msgid1, msgid2, n):
	cheie = ("n", domain, msgid1, msgid2, n, _limbaMediu(), getattr(gettext, "_localedirs", {}).get(domain))
	r = _raspunsuri.get(cheie)
	if r is not None:
		return r
	tradus = _original["dngettext"](domain, msgid1, msgid2, n)
	original = msgid1 if n == 1 else msgid2
	return _tine(cheie, tradus if potrivita(original, tradus) else original)


def _pluralRezerva(n):
	"""regula n != 1 (singular, plural), cea pe care o ia si biblioteca gettext din C cand Plural-Forms nu se poate citi"""
	return int(n != 1)


def _c2py(plural):
	# 0.7.5 (MCX, 15.11.2026; raportul pluginului extern 791532, File Commander, SF8008): o traducere a unui plugin cu
	# antetul Plural-Forms lasat cum l-a scris xgettext ("nplurals=INTEGER; plural=EXPRESSION;", croata File Commander-ului
	# de la OE-Alliance) facea ca gettext.translation sa arunce ValueError "invalid token in plural form: EXPRESSION" chiar la
	# incarcarea catalogului, deci pluginul nu se mai importa deloc in limba aceea. Acum catalogul se incarca, iar pluralul
	# trece pe regula n != 1; textele raman traduse.
	try:
		return _original["c2py"](plural)
	except (ValueError, RecursionError, SyntaxError) as err:
		print("[HdsNeoBoot] Plural-Forms necitit (%r: %s): regula n != 1" % (plural[:80], err))
		return _pluralRezerva


def instaleazaTraduceriSigure():
	"""gettext.dgettext si gettext.dngettext cu verificarea locurilor %, iar gettext.c2py cu regula n != 1 cand
	Plural-Forms nu se poate citi; o singura data"""
	if _original:
		return False
	_original["dgettext"] = gettext.dgettext
	_original["dngettext"] = gettext.dngettext
	gettext.dgettext = _dgettext
	gettext.dngettext = _dngettext
	if callable(getattr(gettext, "c2py", None)):
		_original["c2py"] = gettext.c2py
		gettext.c2py = _c2py
	return True


def areMontare(text):
	"""True daca scriptul are cel putin o comanda mount (nu umount)"""
	for rand in (text or "").splitlines():
		cuvinte = rand.strip().split()
		if cuvinte and os.path.basename(cuvinte[0]) == "mount":
			return True
	return False


def reparaMountpointGol(dosar):
	"""muta deoparte files/mountpoint.sh fara nicio montare, ca NeoBoot sa-l scrie din nou; True daca l-a mutat"""
	cale = os.path.join(dosar, MOUNTPOINT_SH)
	try:
		if not os.path.isfile(cale) or os.path.getsize(cale) > 65536:
			return False
		with open(cale, "r", errors="replace") as f:
			text = f.read()
		if areMontare(text):
			return False
		os.replace(cale, cale + SUFIX_GOL)
	except (IOError, OSError) as err:
		print("[HdsNeoBoot] %s: %s" % (cale, err))
		return False
	print("[HdsNeoBoot] %s fara nicio montare (facut cand /media/hdd era legatura), mutat in %s; NeoBoot il face din nou" % (cale, cale + SUFIX_GOL))
	return True


def semnUdev(semn=SEMN_UDEV, tinta=DATE_UDEV):
	"""legatura semn -> tinta (/dev/.udev -> /run/udev) cand semnul lipseste si tinta e dosar; True daca a facut-o.
	Un semn existent (legatura, chiar rupta, dosar sau fisier) ramane neatins."""
	try:
		if os.path.lexists(semn) or not os.path.isdir(tinta):
			return False
		os.symlink(tinta, semn)
	except OSError as err:
		print("[HdsNeoBoot] %s: %s" % (semn, err))
		return False
	print("[HdsNeoBoot] %s -> %s (pentru files/Harddisk.py din NeoBoot)" % (semn, tinta))
	return True


def comandaSctZero(cmd):
	"""True pentru lista de argumente (program, argv0, argumente...) a lui sdparm cu --set=SCT=0"""
	if isinstance(cmd, str) or not isinstance(cmd, (list, tuple)) or len(cmd) < 3:
		return False
	return os.path.basename(str(cmd[0])) == "sdparm" and SDPARM_SCT_ZERO in cmd[2:]


def instaleazaOprireSct():
	"""Console.ePopen lasa deoparte sdparm --set=SCT=0 trimis fara callback; o singura data, separat de traduceri"""
	if _console:
		return False
	try:
		from Components.Console import Console
	except Exception as err:
		print("[HdsNeoBoot] Console: %s" % err)
		return False
	original = Console.ePopen

	def ePopen(self, cmd, callback=None, *args, **kwargs):
		if callback is None and comandaSctZero(cmd):
			print("[HdsNeoBoot] lasat deoparte (discul ramane cu cronometrul lui, repausul il face enigma2): %s" % " ".join(map(str, cmd[1:])))
			return None
		return original(self, cmd, callback, *args, **kwargs)

	Console.ePopen = ePopen
	_console["ePopen"] = original
	return True


def pregateste(dosare=NEOBOOT_DIRS, semn=SEMN_UDEV, tinta=DATE_UDEV):
	"""inainte de importul pluginurilor"""
	instaleazaTraduceriSigure()
	# FRZ 0.7.7: la fiecare citire a listei de pluginuri (pornirea, dupa opkg) raspunsurile tinute minte se uita: un catalog .mo
	# pus intre timp (o extensie noua, o limba noua a ei) se vede de acum, ca fara memorie
	_raspunsuri.clear()
	mutate = 0
	cuNeoBoot = False
	for dosar in dosare:
		if os.path.isdir(dosar):
			cuNeoBoot = True
			if reparaMountpointGol(dosar):
				mutate += 1
	if cuNeoBoot:
		# paza intai, apoi semnul: cu semnul, NeoBoot trimite sdparm --set=SCT=0 chiar la import
		instaleazaOprireSct()
		semnUdev(semn, tinta)
	return mutate
