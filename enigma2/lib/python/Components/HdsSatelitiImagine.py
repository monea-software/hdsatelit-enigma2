# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSatelitiImagine.py: satellites.xml scurtat de o lista de canale adusa din alt panou sau de pe PC (0.7.5, 15.11.2026,
# SXP; propunerea TNB din TODO 15.11 02:45).
#
# CE SE INTAMPLA: o lista de canale straina vine cu satellites.xml-ul ei, de multe ori numai cu cativa sateliti, si il
# pune peste /etc/tuxbox/satellites.xml (sau in /etc/enigma2/satellites.xml, citit intai de nucleu: lib/dvb/db.cpp,
# eDVBDB::readSatellites). Satelitii lipsa dispar din NimManager.satList: motorul USALS nu-i mai are, Setari tuner nu-i
# mai ofera, iar canalele lor din lamedb raman gri (fara setarile satelitului nu se acordeaza nimic).
#
# CE FACE: la fiecare citire a listei satelitilor (NimManager.readTransponders: la pornire si la
# /web/servicelistreload?mode=3), inainte ca nucleul sa o citeasca, pozitiile care chiar sunt folosite si lipsesc din
# fisierul citit de nucleu se pun la loc din lista imaginii: pozitiile transponderelor din lamedb (canalele) si
# pozitiile salvate la tunere in /etc/enigma2/settings (DiSEqC A-D si satelitii cu LNB din modul avansat; config.Nims nu
# exista inca la readTransponders, de aceea se citeste fisierul). E o UNIRE: satelitii si transponderele omului raman
# neatinse (octet cu octet, HdsEditorSateliti), se adauga numai satelitii lipsa, cu transponderele lor din lista
# imaginii; inainte se face copia de siguranta (HdsEditorSateliti.scrie). Fara nimic de adaugat nu se scrie nimic.
# Fara intrebare (regula 1f): nu se pierde nimic si nu e nimic de hotarat; satelitii fara canale si fara tuner NU se
# pun singuri (omul poate vrea o lista scurta): pentru ei e randul "Pune la loc satelitii din imagine" din editorul de
# canale (TV, Avansat) si butonul din pagina web /editor-canale (Mod avansat, Sateliți).
#
# LISTA IMAGINII: tuxbox-common pune numai /etc/tuxbox/satellites.xml (restul sunt legaturi), deci o lista straina scrisa
# acolo o pierdea. Din 0.7.5 reteta pune si o copie, COPIE_IMAGINE, pe care n-o atinge nicio lista de canale. Pana la
# pachetul nou (si cand lista straina e in /etc/enigma2) lista imaginii e /etc/tuxbox/satellites.xml, daca nu e chiar
# fisierul citit de nucleu.
#
# TRANSPONDERELE NOI (SXE, 15.11.2026, TODO THR 15.11 06:04): cine are lista lui (schimbata in editor sau adusa din alt
# panou) nu primea transponderele adaugate in lista imaginii de o versiune noua (tuxbox-common): nucleul citeste lista
# omului. La aceeasi citire, dupa satelitii de mai sus, transponderele NOI ale listei imaginii se adauga la satelitii pe
# care omul ii are. NOI inseamna: pe care lista imaginii nu le avea la unirea de dinainte. Identitatile transponderelor
# imaginii de la ultima unire stau in STARE (langa copiile de siguranta), cu semnul copiei imaginii (marimea si ora):
# cat timp lista imaginii nu se schimba, la pornire se citeste numai primul rand din STARE (nimic citit intreg). Un
# transponder sters de om nu revine (lista imaginii il avea deja), iar unul pe care omul il are cu alta rata sau alt
# FEC ramane al lui (regula dublurilor din HdsEditorSateliti: aceeasi polarizare, cel mult 2 MHz, acelasi flux). Prima
# data (fara STARE) toate transponderele imaginii sunt noi: listele vechi primesc ce le lipseste o data. Fara intrebare
# (regula 1f): se adauga numai, la satelitii omului, cu copie de siguranta; satelitii si transponderele lui raman.
# Pentru cine vrea lista imaginii intreaga, in locul celei a lui: "Inapoi la lista imaginii" (editorul de canale de
# pe televizor, Avansat, cu intrebare; pagina web /editor-canale, Sateliți, se scrie la "Salvează satellites.xml"),
# cu copia de siguranta a listei omului.
#
# Nimic de aici nu ridica exceptii spre NimManager (e chemat din NimManager.__init__, la pornirea enigma2).
# Nimic din enigma2 la incarcare: modulul se probeaza pe PC.

import os
import re
import zlib

try:
	from Components import HdsEditorCanaleDate as D
except ImportError:  # pe PC, in probe
	import HdsEditorCanaleDate as D

COPIE_IMAGINE = "/usr/share/hdsatelit/satellites-imagine.xml"
LAMEDB = "/etc/enigma2/lamedb"
LAMEDB5 = "/etc/enigma2/lamedb5"
SETARI = "/etc/enigma2/settings"
STARE_NUME = "sateliti-imagine-cunoscute.txt"   # in dosarul copiilor (HdsEditorSateliti.dosar_copii)
_ANTET_STARE = "hds-sateliti-imagine 1"

_DISEQC = re.compile(br"^config\.Nims\.\d+\.diseqc[ABCD]=(\d{1,4})\s*$")
_AVANSAT = re.compile(br"^config\.Nims\.\d+\.advanced\.sat\.(\d{1,4})\.lnb=(\d+)\s*$")


def _jurnal(text):
	print("[HdsSatelitiImagine] %s" % text)


def _S():
	try:
		from Components import HdsEditorSateliti
	except ImportError:  # pe PC
		import HdsEditorSateliti
	return HdsEditorSateliti


def _poz(valoare):
	try:
		p = int(valoare)
	except (TypeError, ValueError):
		return None
	if p < 0:
		p += 3600
	return p if 0 <= p < 3600 else None


def _poz_rand_s(param):
	"""Pozitia din parametrii unui transponder de satelit: "s f:sr:pol:fec:poz:..." (lamedb 4) sau "s:f:sr:pol:fec:poz:..."
	(lamedb 5). None pentru cablu, terestru sau un rand rau."""
	param = param.strip()
	if len(param) < 3 or param[:1] != b"s" or param[1:2] not in (b" ", b":"):
		return None
	parti = param[2:].split(b":")
	return _poz(parti[4]) if len(parti) > 4 else None


def pozitii_lamedb(cale=None):
	"""Pozitiile (0..3599) transponderelor de satelit din lamedb (formatul 3, 4 sau 5). Se citeste numai sectiunea
	transponders, fara servicii: la fiecare pornire, si pe liste mari, trebuie sa fie repede."""
	rez = set()
	cai = (cale,) if cale else (LAMEDB, LAMEDB5)
	for c in cai:
		try:
			f = open(c, "rb")
		except (IOError, OSError):
			continue
		with f:
			antet = f.readline()
			if antet.startswith(b"eDVB services /5/"):
				for rand in f:
					if rand.startswith(b"t:") and b"," in rand:
						p = _poz_rand_s(rand.split(b",", 2)[1])
						if p is not None:
							rez.add(p)
			elif antet.startswith(b"eDVB services /"):
				if f.readline().strip() != b"transponders":
					continue
				for rand in f:
					r = rand.strip()
					if r == b"end":
						break
					p = _poz_rand_s(r)
					if p is not None:
						rez.add(p)
			else:
				continue
		return rez
	return rez


def pozitii_setari(cale=SETARI):
	"""Pozitiile salvate la tunere in settings: config.Nims.N.diseqcA..D si config.Nims.N.advanced.sat.POZ.lnb (cu LNB
	ales, nu 0). 3601 (nimic conectat) nu conteaza."""
	rez = set()
	try:
		f = open(cale, "rb")
	except (IOError, OSError):
		return rez
	with f:
		for rand in f:
			if not rand.startswith(b"config.Nims."):
				continue
			m = _DISEQC.match(rand)
			if m:
				p = _poz(m.group(1))
			else:
				m = _AVANSAT.match(rand)
				p = _poz(m.group(1)) if m and m.group(2) != b"0" else None
			if p is not None:
				rez.add(p)
	return rez


def _acelasi(a, b):
	try:
		return os.path.samefile(a, b)
	except OSError:
		return os.path.realpath(a) == os.path.realpath(b)


def cale_imagine(activ=None, copie=None):
	"""Lista satelitilor imaginii: COPIE_IMAGINE, altfel /etc/tuxbox/satellites.xml cand nucleul citeste alt fisier
	(lista straina pusa in /etc/enigma2). None cand nu e niciuna (lista straina a scris chiar peste /etc/tuxbox, pe o
	imagine fara copie)."""
	activ = activ or D.cale_sateliti()
	for c in ((copie,) if copie else (COPIE_IMAGINE, D.SATELITI)):
		if c and os.access(c, os.R_OK) and not _acelasi(c, activ):
			return c
	return None


def _citeste_imagine(activ, copie):
	c = cale_imagine(activ, copie)
	if c is None:
		return None
	S = _S()
	try:
		return S.citeste(c)
	except S.Eroare as e:
		_jurnal("lista imaginii %s nu se poate citi: %s" % (c, e.mesaj() if hasattr(e, "mesaj") else e))
		return None


def adauga_din(sateliti, imagine, pozitii):
	"""Satelitii de pe `pozitii` din lista `imagine` pusi in `sateliti` (numai cei care lipsesc). -> pozitiile puse"""
	puse = []
	for p in sorted(pozitii, key=lambda x: x - 3600 if x > 1800 else x):
		if sateliti.gaseste(p) is not None:
			continue
		s = imagine.gaseste(p)
		if s is None:
			continue
		sateliti.adauga_satelit_din(s)
		puse.append(p)
	return puse


def cale_stare(cale=None):
	"""STARE pentru fisierul citit de nucleu (`cale`): in dosarul copiilor lui de siguranta."""
	return os.path.join(_S().dosar_copii(cale or D.cale_sateliti()), STARE_NUME)


def _semn(cale):
	"""Marimea si ora copiei imaginii, ca text ("" cand nu se poate afla)."""
	try:
		st = os.stat(cale)
	except OSError:
		return ""
	return "%d %d" % (st.st_size, int(st.st_mtime))


def _citeste_stare(cale, intreaga=True):
	"""-> {"semn": text, "crc": int, "ids": set de identitati (None cand intreaga=False)}; None cand lipseste sau e
	stricata (atunci toate transponderele imaginii sunt noi)."""
	try:
		f = open(cale, "r")
	except (IOError, OSError):
		return None
	with f:
		cap = f.readline().split()
		if len(cap) != 6 or " ".join(cap[:2]) != _ANTET_STARE:
			return None
		try:
			rez = {"semn": "%s %s" % (int(cap[2]), int(cap[3])), "crc": int(cap[4], 16), "ids": None}
			if intreaga:
				ids = set()
				for rand in f:
					parti = rand.split()
					if len(parti) == 5:
						ids.add(tuple(int(x) for x in parti))
				if len(ids) != int(cap[5]):
					return None               # scrisa pe jumatate: o luam de la capat
				rez["ids"] = ids
		except ValueError:
			return None
	return rez


def _scrie_stare(cale, semn, crc, ids):
	"""Scrierea sigura (.nou, fsync, rename) a STARE. Nu ridica (la urmatoarea pornire se reface)."""
	try:
		try:
			os.makedirs(os.path.dirname(cale))
		except OSError:
			pass
		randuri = ["%s %s %08x %d\n" % (_ANTET_STARE, semn or "0 0", crc & 0xFFFFFFFF, len(ids))]
		randuri.extend("%d %d %d %d %d\n" % i for i in sorted(ids))
		_S()._scrie_sigur(cale, "".join(randuri).encode("ascii"))
	except Exception as e:
		_jurnal("starea listei imaginii nu s-a scris (%s): %r" % (cale, e))


def identitati(sateliti):
	"""{(pozitie 0..3599, polarizare, frecventa kHz, is_id, t2mi_plp_id)} ale transponderelor din `sateliti`."""
	rez = set()
	for s in sateliti.lista:
		p = s.poz
		for tp in s.transpondere:
			i = tp._identitate()
			if i is not None:
				rez.add((p,) + i)
	return rez


def adauga_transpondere_noi(sateliti, imagine, cunoscute):
	"""Transponderele din `imagine` care nu sunt in `cunoscute` (identitati), puse la satelitii pe care `sateliti` ii
	are deja (numai cele care lipsesc dupa regula dublurilor). -> [(pozitie, frecventa kHz, polarizare)] puse"""
	puse = []
	for si in imagine.lista:
		p = si.poz
		if p is None or sateliti.gaseste(p) is None:
			continue
		for tp in si.transpondere:
			i = tp._identitate()
			if i is None or (p,) + i in cunoscute:
				continue
			if sateliti.adauga_transponder_din(p, tp) is not None:
				puse.append((p, i[1], i[0]))
	return puse


def uneste_la_pornire(cale=None, copie=None, lamedb=None, setari=SETARI, stare=None, detalii=False):
	"""Din NimManager.readTransponders, inainte de eDVBDB.readSatellites: pozitiile cu canale (lamedb) si cele salvate
	la tunere (settings) care lipsesc din fisierul citit de nucleu se pun la loc din lista imaginii, iar satelitii
	omului primesc transponderele noi ale listei imaginii (unire, o singura scriere, cu copie de siguranta). Nu ridica
	niciodata. -> pozitiile satelitilor pusi; cu detalii=True (sateliti, transpondere puse: [(poz, kHz, pol)])"""
	try:
		puse, tp = _uneste(cale, copie, lamedb, setari, stare)
	except Exception as e:
		_jurnal("unirea cu lista imaginii nu a mers: %r" % (e,))
		puse, tp = [], []
	return (puse, tp) if detalii else puse


def _citeste_octeti(cale):
	try:
		with open(cale, "rb") as f:
			return f.read()
	except (IOError, OSError):
		return None


def _uneste(cale, copie, lamedb, setari, stare=None):
	cale = cale or D.cale_sateliti()
	if not os.access(cale, os.R_OK):
		return [], []                     # fara fisier nucleul nu are sateliti oricum; nu e cazul unei liste scurtate
	are = D.citeste_sateliti(cale)       # repede: numai etichetele <sat>
	if not are:
		return [], []                     # lista goala sau stricata nu e treaba unirii (nucleul nu o poate citi)
	dorite = pozitii_lamedb(lamedb) | pozitii_setari(setari)
	cale_im = cale_imagine(cale, copie)
	if cale_im is None:
		if dorite - set(are):
			_jurnal("%d pozitii cu canale lipsesc din %s, dar lista imaginii lipseste" % (len(dorite - set(are)), cale))
		return [], []
	# tot repede: satelitii care lipsesc la om si pe care lista imaginii chiar ii are
	sat_lipsa = (dorite - set(are)) & set(D.citeste_sateliti(cale_im)) if dorite - set(are) else set()
	# transponderele noi: numai cand copia imaginii s-a schimbat de la unirea de dinainte (primul rand din STARE)
	stare = stare or cale_stare(cale)
	semn = _semn(cale_im)
	cap = _citeste_stare(stare, intreaga=False)
	tp_de_vazut = cap is None or not semn or cap["semn"] != semn
	if not sat_lipsa and not tp_de_vazut:
		return [], []
	vechi = None
	date_im = crc = None
	if tp_de_vazut:
		date_im = _citeste_octeti(cale_im)
		if date_im is None:
			return [], []
		crc = zlib.crc32(date_im) & 0xFFFFFFFF
		vechi = _citeste_stare(stare) if cap is not None else None
		if vechi is not None and vechi["crc"] == crc:
			_scrie_stare(stare, semn, crc, vechi["ids"])   # acelasi cuprins, alta ora (pachetul pus din nou)
			tp_de_vazut = False
			if not sat_lipsa:
				return [], []
	S = _S()
	if tp_de_vazut:
		try:
			imagine = S.Sateliti(date_im, cale_im)
		except S.Eroare as e:
			_jurnal("lista imaginii %s nu se poate citi: %s" % (cale_im, e.mesaj() if hasattr(e, "mesaj") else e))
			return [], []
	else:
		imagine = _citeste_imagine(cale, cale_im)
		if imagine is None:
			return [], []
	if not sat_lipsa and _citeste_octeti(cale) == date_im:
		# lista omului e chiar lista imaginii: nimic de adaugat, numai identitatile tinute minte
		_scrie_stare(stare, semn, crc, identitati(imagine))
		return [], []
	try:
		sateliti = S.citeste(cale)
	except S.Eroare:
		return [], []
	puse = adauga_din(sateliti, imagine, dorite) if sat_lipsa else []
	tp = adauga_transpondere_noi(sateliti, imagine, (vechi or {}).get("ids") or set()) if tp_de_vazut else []
	copia = None
	if puse or tp:
		copia = S.scrie(sateliti, cale)  # Eroare: STARE ramane veche, se incearca din nou la urmatoarea pornire
	if tp_de_vazut:
		_scrie_stare(stare, semn, crc, identitati(imagine))
	if puse:
		_jurnal("%s: pusi la loc din lista imaginii %d sateliti cu canale sau la tunere (%s); copia: %s" %
			(cale, len(puse), ", ".join("%d" % p for p in puse), copia))
	if tp:
		_jurnal("%s: %d transpondere noi din lista imaginii (%s); copia: %s" %
			(cale, len(tp), ", ".join("%d:%d:%d" % x for x in tp[:20]) + (" ..." if len(tp) > 20 else ""), copia))
	return puse, tp


def diferita_de_imagine(cale=None, copie=None, sateliti=None):
	"""True cand fisierul citit de nucleu (sau `sateliti`, lista tinuta de pagina web) nu e la fel cu lista imaginii
	(randul si butonul "Inapoi la lista imaginii"); False si cand nu e lista imaginii. Repede: marimile intai."""
	try:
		cale = cale or (sateliti.cale if sateliti is not None else None) or D.cale_sateliti()
		cale_im = cale_imagine(cale, copie)
		if cale_im is None:
			return False
		if sateliti is not None:
			date = sateliti._original if not sateliti.schimbari else sateliti.octeti()   # neschimbata: fara refacere
			return date != _citeste_octeti(cale_im)
		if os.path.getsize(cale) != os.path.getsize(cale_im):
			return True
		return _citeste_octeti(cale) != _citeste_octeti(cale_im)
	except Exception as e:
		_jurnal("comparatia cu lista imaginii: %r" % (e,))
		return False


def lista_imaginii(cale=None, copie=None):
	"""Lista imaginii ca obiect nescris, fara cale (scrie() o pune in fisierul citit de nucleu, cu copia de siguranta
	a listei omului; pagina web o tine pana la "Salvează satellites.xml"). -> Sateliti; Eroare (HdsEditorSateliti)
	cand lista imaginii lipseste sau nu se poate citi"""
	S = _S()
	cale_im = cale_imagine(cale or D.cale_sateliti(), copie)
	date = _citeste_octeti(cale_im) if cale_im else None
	if date is None:
		raise S.Eroare(S._t("Lista sateliților imaginii nu se găsește pe receptor."))
	return S.Sateliti(date, None)


def inapoi_la_imagine(cale=None, copie=None):
	"""Pentru editorul de pe televizor: fisierul citit de nucleu primeste lista imaginii intreaga (copia de siguranta a
	listei omului inainte; satelitii si transponderele puse de om se pierd, raman in copie). -> calea copiei (None:
	era deja lista imaginii); Eroare (HdsEditorSateliti) cand nu merge"""
	cale = cale or D.cale_sateliti()
	sat = lista_imaginii(cale, copie)
	copia = _S().scrie(sat, cale)
	_jurnal("%s: inapoi la lista imaginii, la cerere; copia: %s" % (cale, copia))
	return copia


def lipsa_din_imagine(sateliti=None, copie=None):
	"""Pozitiile satelitilor din lista imaginii care lipsesc din `sateliti` (implicit fisierul citit de nucleu), de la
	vest la est. Lista goala cand nu e lista imaginii. Repede (numai etichetele <sat>), ca editorul sa arate randul numai
	cand are rost."""
	try:
		activ = (sateliti.cale if sateliti is not None else None) or D.cale_sateliti()
		cale_im = cale_imagine(activ, copie)
		if cale_im is None:
			return []
		if sateliti is None:
			are = set(D.citeste_sateliti(activ))
		else:
			are = set(s.poz for s in sateliti.lista)
		return sorted((p for p in D.citeste_sateliti(cale_im) if p not in are), key=lambda x: x - 3600 if x > 1800 else x)
	except Exception as e:
		_jurnal("lipsa din imagine: %r" % (e,))
		return []


def pune_la_loc_toti(sateliti, copie=None):
	"""Toti satelitii listei imaginii care lipsesc pusi in `sateliti` (obiectul HdsEditorSateliti.Sateliti, nescris).
	-> pozitiile puse"""
	imagine = _citeste_imagine(sateliti.cale or D.cale_sateliti(), copie)
	if imagine is None:
		return []
	return adauga_din(sateliti, imagine, [s.poz for s in imagine.lista])


def pune_la_loc_si_scrie(copie=None):
	"""Pentru editorul de pe televizor: toti satelitii lipsa ai imaginii scrisi in fisierul citit de nucleu (copie de
	siguranta inainte). -> numarul satelitilor pusi; Eroare (HdsEditorSateliti) cand scrierea nu merge"""
	S = _S()
	sateliti = S.citeste()
	puse = pune_la_loc_toti(sateliti, copie)
	if puse:
		S.scrie(sateliti)
		_jurnal("pusi la loc din lista imaginii, la cerere: %d sateliti" % len(puse))
	return len(puse)
