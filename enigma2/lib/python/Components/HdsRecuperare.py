# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRecuperare.py - dosarul in care Maintenance Mode (actualizatorul Amiko din p7) cauta imaginea pe stick.
#
# Memoria interna NU se citeste: nimic de aici nu deschide ceva din /dev si nu atinge p6 (deviceinfo).
# Calea se CALCULEAZA exact cum o calculeaza showiframe (binarul Dinobot, md5 bb955c2a6eb937c97283da0e031b3b27,
# functia box_upd_default la 0x29c84). La fiecare pornire, showiframe (update_box_type, 0x2a5a8) citeste din p6
# eticheta "BOX_TYPE:<tip> UPD_PATH:<cale>" si o rescrie daca difera de ce calculeaza. Loader-ul Amiko din
# Maintenance Mode citeste aceeasi eticheta si cauta imaginea pe stick in <cale> (din consola:
# "get_dev_update_info ... {2 u57 ---------- /amiko/viper4kv20}", apoi
# "Searching image files in /newroot//amiko/viper4kv20").
#
# Ordinea din binar:
#   1. /proc/stb/info/upd_path: daca read() da MAI MULT de 1 octet, calea = continutul pana la primul \n
#      (daca nu e, pana la primul \r) si numele nu se mai citeste. Fisierul il scrie /etc/init.d/loadmodules
#      (pachet Dinobot) din "imagedir=" din /usr/lib/enigma.info. Imaginea HDSatelit nu are enigma.info,
#      deci acolo e numai "\n" (o imagine care il are gol ajunge asa la "/'e2/update'").
#   2. altfel FISIERUL /etc/hostname (nu numele din nucleu), cel mult 64 de octeti, taiat la fel, cautat
#      EXACT (litere mari si mici, spatii) in tabelul fix de mai jos. Un nume care nu e in tabel, sau un
#      /etc/hostname lipsa, da o cale GOALA, iar showiframe scrie atunci "UPD_PATH:" gol in p6. Ce face
#      loader-ul Amiko cu o cale goala nu e dovedit.
# Ce e mai sus vine din dezasamblarea binarului (radare2).
#
# Dosarul din regulile modelului: /etc/hdsatelit-model (scris la construirea imaginii) poate avea „upd_path=”, dosarul
# ales pentru model (pe Viper 4K V20 chiar calea din tabel pentru viper4kv20). enigma2.sh il pune in
# /proc/stb/info/upd_path inainte de showiframe, deci la pasul 1 calea vine de acolo si sursa se arata ca „regulile
# modelului”. Ordinea de mai sus ramane neschimbata (asa calculeaza showiframe): daca bufferul a ramas gol (un fisier
# de reguli fara camp, un driver fara nod), calea vine tot din tabelul dupa nume, iar dosarul din reguli se arata numai
# ca cel asteptat.

import os

try:
	_
except NameError:
	def _(text):
		return text

# (nume din /etc/hostname, cale scrisa in p6), in ordinea comparatiilor din box_upd_default.
# "dinobot4kpro" apare de doua ori si in binar; a doua comparatie nu se atinge niciodata.
TABEL_NUME = (
	(b"anadol4k", b"/dinobot/u5"),
	(b"dinobot4k", b"/dinobot/u5"),
	(b"anadol4kv2", b"/dinobot/u51"),
	(b"anadol4kcombo", b"/dinobot/u51"),
	(b"protek4kx1", b"/dinobot/u51"),
	(b"dinobot4kplus", b"/dinobot/u52"),
	(b"dinobot4kmini", b"/dinobot/u53"),
	(b"arivaatvcombo", b"/dinobot/u532"),
	(b"arivaatvtt", b"/dinobot/u533"),
	(b"dinobot4kpro", b"/dinobot/u54"),
	(b"hitube4k", b"/dinobot/u55"),
	(b"iziboxone4k", b"/dinobot/u55"),
	(b"jdhdduo", b"/dinobot/u42"),
	(b"spycatminiv2", b"/dinobot/u42"),
	(b"anadolprohd5", b"/dinobot/u42"),
	(b"iziboxecohd", b"/dinobot/u42"),
	(b"turing", b"/dinobot/u43"),
	(b"dinobot4kpro", b"/dinobot/u54"),
	(b"axashistwin", b"/axas/axashistwin"),
	(b"axashis4kcombo", b"/axas/axascombo"),
	(b"axashis4kcomboplus", b"/axas/axascomboplus"),
	(b"axashisc4k", b"/axas/axasc4k"),
	(b"viper4kv20", b"/amiko/viper4kv20"),
	(b"vipers", b"/amiko/vipers"),
)

# numele cu care imaginea iese din build pe Amiko Viper 4K V20 (base-files: hostname = "${MACHINEBUILD}")
NUME_VIPER4KV20 = "viper4kv20"

SURSA_UPD_PATH = "upd_path"
SURSA_REGULI = "reguli"
SURSA_NUME = "hostname"
SURSA_NECUNOSCUTA = "necunoscut"

# regulile modelului (aceeasi cale ca in Components/HdsPazaModel.FISIER_REGULI), fata de radacina
FISIER_REGULI = "etc/hdsatelit-model"
_CARACTERE_DOSAR = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./-")


def _citeste(cale, maxim):
	"""octetii cititi (cel mult `maxim`, un singur read, ca in binar) sau None daca fisierul nu se deschide"""
	try:
		with open(cale, "rb") as f:
			return f.read(maxim)
	except (IOError, OSError):
		return None


def _taie(date):
	"""ca in binar: pana la primul \\n, daca nu e pana la primul \\r, altfel tot; apoi strcmp se opreste la NUL"""
	i = date.find(b"\n")
	if i < 0:
		i = date.find(b"\r")
	if i >= 0:
		date = date[:i]
	return date.split(b"\0", 1)[0]


def _text(date):
	return date.decode("utf-8", "replace")


def _vizibil(text):
	"""pentru ecran: caracterele de control se scriu ca \\r, \\t sau \\xNN. Altfel un /etc/hostname scris cu CRLF
	s-ar afisa „viper4kv20” (cu \\r nevazut) si ar parea ca tocmai numele bun nu e cunoscut."""
	rez = []
	for ch in text or "":
		if ch == "\r":
			rez.append("\\r")
		elif ch == "\t":
			rez.append("\\t")
		elif ord(ch) < 32 or ord(ch) == 127:
			rez.append("\\x%02x" % ord(ch))
		else:
			rez.append(ch)
	return "".join(rez)


def dosarDinReguli(radacina="/"):
	"""„upd_path=” din regulile modelului (primul rand cu cheia, ca la garda din enigma2.sh), sau "" daca lipseste ori
	nu e o cale sigura (/ la inceput, numai litere, cifre, _ . / -, cel mult 60 de caractere). Nu arunca niciodata."""
	date = _citeste(os.path.join(radacina, FISIER_REGULI), 16384)
	if not date:
		return ""
	for rand in _text(date).splitlines():
		rand = rand.strip()
		if rand.startswith("#") or "=" not in rand:
			continue
		cheie, valoare = rand.split("=", 1)
		if cheie.strip() != "upd_path":
			continue
		valoare = valoare.strip()
		if valoare.startswith("/") and len(valoare) <= 60 and all(ch in _CARACTERE_DOSAR for ch in valoare):
			return valoare
		return ""
	return ""


def calculeaza(radacina="/"):
	"""Ce ar scrie showiframe in p6 la urmatoarea lui pornire. Intoarce un dict:
	boxtype (text), cale (text, "" = necunoscuta), sursa (SURSA_*), nume (textul din /etc/hostname sau None),
	reguli (dosarul din regulile modelului, "" daca lipseste). Nu arunca niciodata."""
	def c(rel):
		return os.path.join(radacina, rel)
	boxtype = _citeste(c("proc/stb/info/boxtype"), 32)
	rez = {
		"boxtype": _text(_taie(boxtype)) if boxtype else "",
		"cale": "",
		"sursa": SURSA_NECUNOSCUTA,
		"nume": None,
		"reguli": dosarDinReguli(radacina),
	}
	upd = _citeste(c("proc/stb/info/upd_path"), 64)
	if upd is not None and len(upd) > 1:
		rez["cale"] = _text(_taie(upd))
		rez["sursa"] = SURSA_REGULI if rez["reguli"] and rez["cale"] == rez["reguli"] else SURSA_UPD_PATH
		return rez
	nume = _citeste(c("etc/hostname"), 64)
	if nume is None:
		return rez
	nume = _taie(nume)
	rez["nume"] = _text(nume)
	for n, cale in TABEL_NUME:
		if nume == n:
			rez["cale"] = _text(cale)
			rez["sursa"] = SURSA_NUME
			break
	return rez


def dosarPeStick(cale):
	"""'/amiko/viper4kv20' -> 'amiko/viper4kv20/' (asa se scrie pe stick, fata de radacina lui); '' ramane ''"""
	cale = (cale or "").strip("/")
	return cale + "/" if cale else ""


def seAplica(radacina="/"):
	"""True numai pe receptoarele Dinobot, unde showiframe scrie eticheta (nu in emulatorul de pe PC)"""
	return os.path.exists(os.path.join(radacina, "usr/bin/showiframe"))


def randuriInformatii(info):
	"""Randurile pentru ecranul Informatii Receptor, din rezultatul lui calculeaza()"""
	l = [_("Recuperare prin Maintenance Mode (stick USB):")]
	dosar = dosarPeStick(info.get("cale"))
	reguli = info.get("reguli") or ""
	if dosar:
		l.append(_("  Dosar pe stick:           %s") % _vizibil(dosar))
		if info.get("sursa") == SURSA_REGULI:
			l.append(_("  Stabilit după:            regulile modelului (/etc/hdsatelit-model), la pornire"))
		elif info.get("sursa") == SURSA_UPD_PATH:
			l.append(_("  Stabilit după:            /proc/stb/info/upd_path, la pornire"))
		else:
			l.append(_("  Stabilit după:            numele receptorului „%s”, la pornire") % _vizibil(info.get("nume")))
		if reguli and dosarPeStick(reguli) != dosar:
			l.append(_("  Atenție: regulile modelului cer dosarul %s.") % _vizibil(dosarPeStick(reguli)))
		return l
	l.append(_("  Dosar pe stick:           necunoscut"))
	if info.get("sursa") == SURSA_UPD_PATH:
		l.append(_("  Atenție: /proc/stb/info/upd_path nu dă nicio cale."))
	elif info.get("nume") is None:
		l.append(_("  Atenție: lipsește numele receptorului (/etc/hostname)."))
	else:
		l.append(_("  Atenție: numele receptorului („%s”) nu e cunoscut de actualizatorul Amiko.") % _vizibil(info.get("nume")))
	l.append(_("  De la următoarea pornire a interfeței sau a receptorului, Maintenance Mode poate să nu mai găsească imaginea pe stick."))
	if reguli:
		l.append(_("  Atenție: regulile modelului cer dosarul %s.") % _vizibil(dosarPeStick(reguli)))
	elif info.get("boxtype") == "u57":
		l.append(_("  Pe Amiko Viper 4K V20 numele receptorului trebuie să fie %s.") % NUME_VIPER4KV20)
	return l


def textConfirmare(info):
	"""O fraza pentru ultima confirmare dinaintea scrierii reale"""
	dosar = dosarPeStick(info.get("cale"))
	if dosar:
		return _("Pentru recuperare, Maintenance Mode caută imaginea pe stick în dosarul %s.") % _vizibil(dosar)
	return _("Atenție: dosarul de recuperare de pe stick nu se poate afla (vezi Informații Receptor).")
