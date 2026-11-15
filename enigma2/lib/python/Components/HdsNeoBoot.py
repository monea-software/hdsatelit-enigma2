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
#   2. files/mountpoint.sh ramas gol. NeoBoot il scrie o singura data, la prima deschidere, din randurile
#      "/dev/sdXN /media/hdd" ale lui /proc/mounts. Pe 0.7.4 /media/hdd era legatura, nu montare, deci fisierul a iesit numai cu
#      "#!/bin/sh" si "exit 0"; fara el nu se monteaza /media/sdXN, neo.sh nu se mai face ("chmod: neo.sh: No such file",
#      JAKITAKI, Vu+ Zero 4K) si alegerea imaginii la OK nu merge. Din 0.7.5 /media/hdd e montare bind (Harddisk.bindName),
#      deci un fisier gol se muta deoparte (mountpoint.sh.hds-gol, nu se sterge) si NeoBoot il face din nou, bun, la
#      urmatoarea deschidere. Un fisier cu cel putin un rand de montare ramane neatins.
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

# un loc de format %: %%, %s, %5.2f, %-10s, %(nume)s, %*d
_LOC = re.compile(r"%(?:\(([^)]*)\))?[#0\- +]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?([diouxXeEfFgGcrsa%])")
# tipurile care primesc orice valoare
_ORICE = frozenset("sra")
_NUMERE = frozenset("diouxXeEfFgGc")

_verdicte = {}
_original = {}


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


def _dgettext(domain, message):
	tradus = _original["dgettext"](domain, message)
	return tradus if potrivita(message, tradus) else message


def _dngettext(domain, msgid1, msgid2, n):
	tradus = _original["dngettext"](domain, msgid1, msgid2, n)
	original = msgid1 if n == 1 else msgid2
	return tradus if potrivita(original, tradus) else original


def instaleazaTraduceriSigure():
	"""gettext.dgettext si gettext.dngettext cu verificarea locurilor %; o singura data"""
	if _original:
		return False
	_original["dgettext"] = gettext.dgettext
	_original["dngettext"] = gettext.dngettext
	gettext.dgettext = _dgettext
	gettext.dngettext = _dngettext
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


def pregateste(dosare=NEOBOOT_DIRS):
	"""inainte de importul pluginurilor"""
	instaleazaTraduceriSigure()
	mutate = 0
	for dosar in dosare:
		if os.path.isdir(dosar) and reparaMountpointGol(dosar):
			mutate += 1
	return mutate
