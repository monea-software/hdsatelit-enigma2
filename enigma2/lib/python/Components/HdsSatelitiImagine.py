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
# CE FACEA PANA LA 0.7.6 (scos in 0.7.7, vezi SATELITII STERSI NU MAI REVIN mai jos): la fiecare citire a listei
# satelitilor (NimManager.readTransponders: la pornire si la
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
# SATELITII STERSI NU MAI REVIN (0.7.7, 16.11.2026, SAT; forum 1588 lme, cererea lui Eduard 06:32 "A sters, nu mai
# revine automat. Mai simplu, ca la alte imagini."): unirea de la pornire NU mai pune la loc niciun satelit. Punea inapoi
# orice pozitie cu canale in lamedb sau salvata la un tuner, deci un satelit sters in editor, de mana din satellites.xml
# sau printr-o lista instalata de om revenea la fiecare pornire (la lme: 28,2E si 19,2E, satelitii impliciti ai tarii
# GB scrisi fortat la prima pornire in diseqcA/diseqcB si ramasi in settings dupa trecerea tunerului pe modul avansat).
# Acum fisierul citit de nucleu e adevarul, ca in OE-Alliance (NimManager.readTransponders citeste satellites.xml si
# atat): ce lipseste ramane lipsa pana il pune omul (editorul, "Pune la loc satelitii din imagine", lista imaginii).
# Raman: transponderele noi ale listei imaginii la satelitii pe care omul ii are (SXE, mai sus) si butoanele manuale.
# Referintele tunerelor la un satelit care nu mai e in lista se scot (portul DiSEqC "nimic conectat", LNB nefolosit):
# la pornire in NimManager.hdsSatelitiSalvatiLipsa, la stergerea din editor (televizor, web) prin scoate_de_la_tunere.
# Numai cheile active ale modului tunerului conteaza (referinte_tuner), nu si cele ramase de la alt mod.
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

_NIMS = re.compile(br"^config\.Nims\.(\d+)\.([A-Za-z0-9_.]+)=(.*?)\s*$")
# porturile DiSEqC folosite de fiecare fel al modului simplu (motorul nu are porturi: foloseste toata lista)
_PORTURI = {"single": "A", "toneburst_a_b": "AB", "diseqc_a_b": "AB", "diseqc_a_b_c_d": "ABCD"}
DISEQC_IMPLICIT = "diseqc_a_b"        # NimManager: nim.diseqcMode = ConfigSelection(..., "diseqc_a_b")
NIMIC_CONECTAT = "3601"


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


def porturi_diseqc(fel):
	"""Literele porturilor DiSEqC folosite de felul `fel` al modului simplu ("single" -> "A"; motorul -> "")."""
	return _PORTURI.get(str(fel or DISEQC_IMPLICIT), "")


def _poz_tuner(valoare):
	"""Pozitia unei valori salvate la tuner (0..3599); 3601-3604 ("nimic conectat", "toti satelitii") si valorile rele
	-> None."""
	try:
		p = int(str(valoare).strip())
	except (TypeError, ValueError):
		return None
	return p if 0 <= p < 3600 else None


def referinte_tuner(salvate, mod_implicit="nothing"):
	"""[(cheie, pozitie)] ale satelitilor folositi cu adevarat de un tuner, din valorile lui salvate (dict, ca
	config.Nims[N].content.stored_values): in modul simplu numai porturile DiSEqC ale felului ales (porturi_diseqc), in
	modul avansat satelitii cu LNB ales (cheia "advanced.sat.<cheia din settings>"). Cheile celuilalt mod (raman in
	settings de la prima pornire, cand diseqcA/diseqcB se scriu fortat, sau de la o schimbare de mod) nu conteaza.
	`mod_implicit`: configMode cand lipseste ("simple" la primul tuner de satelit, "nothing" la celelalte)."""
	if not isinstance(salvate, dict):
		return []
	mod = str(salvate.get("configMode") or mod_implicit)
	rez = []
	if mod == "simple":
		for litera in porturi_diseqc(salvate.get("diseqcMode")):
			p = _poz_tuner(salvate.get("diseqc" + litera))
			if p is not None:
				rez.append(("diseqc" + litera, p))
	elif mod == "advanced":
		avansat = salvate.get("advanced")
		sateliti = avansat.get("sat") if isinstance(avansat, dict) else None
		if isinstance(sateliti, dict):
			for cheie in sorted(sateliti, key=lambda k: str(k)):
				valori = sateliti[cheie]
				p = _poz_tuner(cheie)
				if p is None or not isinstance(valori, dict):
					continue
				if str(valori.get("lnb", "0")).strip() not in ("", "0"):
					rez.append(("advanced.sat.%s" % cheie, p))
	return rez


def setari_tunere(cale=SETARI):
	"""{N: valorile salvate ale tunerului N, ca dict imbricat (config.Nims.N.advanced.sat.282.lnb -> ["advanced"]["sat"]
	["282"]["lnb"])} din fisierul settings. Valorile raman text."""
	rez = {}
	try:
		f = open(cale, "rb")
	except (IOError, OSError):
		return rez
	with f:
		for rand in f:
			if not rand.startswith(b"config.Nims."):
				continue
			m = _NIMS.match(rand)
			if not m:
				continue
			try:
				n, cale_cheie, valoare = int(m.group(1)), m.group(2).decode("ascii"), m.group(3).decode("utf-8", "replace")
			except (ValueError, UnicodeDecodeError):
				continue
			d = rez.setdefault(n, {})
			parti = cale_cheie.split(".")
			for p in parti[:-1]:
				urm = d.get(p)
				if not isinstance(urm, dict):
					urm = d[p] = {}
				d = urm
			d[parti[-1]] = valoare
	return rez


def pozitii_setari(cale=SETARI):
	"""Pozitiile folosite de tunere dupa settings (referinte_tuner: numai cheile active ale modului fiecarui tuner;
	configMode lipsa = "nothing", fiindca primul tuner de satelit il are mereu scris). 3601 nu conteaza."""
	rez = set()
	for _n, salvate in setari_tunere(cale).items():
		for _cheie, p in referinte_tuner(salvate):
			rez.add(p)
	return rez


def text_scoase(scoase):
	"""Textul scurt pentru om: [(slot, cheie, pozitie)] -> "Tuner A: 28,2°E (DiSEqC B); Tuner B: 19,2°E (LNB)"."""
	parti = []
	for slot, cheie, p in scoase:
		unde = "DiSEqC %s" % cheie[-1] if cheie.startswith("diseqc") else "LNB"
		parti.append("%s %s: %s (%s)" % (_t("Tuner"), chr(65 + int(slot)) if 0 <= int(slot) < 26 else slot,
			D.text_pozitie(p), unde))
	return "; ".join(parti)


def _t(text):
	try:
		return _(text)  # noqa: F821  (builtins pe receptor)
	except NameError:
		return text


def scoate_de_la_tunere(pozitii, aplica=True, nimmgr=None, cfg=None, salveaza=None):
	"""Pe receptor, pe firul enigma2, dupa stergerea din editor (televizor, web): pozitiile date scoase din configurarea
	tunerelor de satelit, pe obiectele config.Nims (settings scris direct s-ar pierde la oprire): portul DiSEqC al felului
	ales care arata spre ele devine "nimic conectat" (3601), LNB-ul lor din modul avansat devine nefolosit ("0"); restul
	tunerului ramane. Cu aplica=False numai spune ce s-ar scoate (textul intrebarii). Nu ridica.
	-> [(slot, cheie, pozitie)]"""
	pozitii = set(p for p in (_poz_tuner(x) for x in (pozitii or ())) if p is not None)
	scoase = []
	if not pozitii:
		return scoase
	try:
		if nimmgr is None:
			from Components.NimManager import nimmanager as nimmgr
		if cfg is None:
			from Components.config import config as cfg
		sloturi = list(nimmgr.nim_slots)
	except Exception as e:
		_jurnal("tunerele nu se pot citi: %r" % (e,))
		return scoase
	schimbat = False
	for slot in sloturi:
		try:
			if not slot.isCompatible("DVB-S"):
				continue
			nim = cfg.Nims[slot.slot]
			mod = nim.configMode.value
			if mod == "simple":
				for litera in porturi_diseqc(nim.diseqcMode.value):
					el = getattr(nim, "diseqc" + litera)
					p = _poz_tuner(el.value)
					if p in pozitii:
						scoase.append((slot.slot, "diseqc" + litera, p))
						if aplica:
							el.value = NIMIC_CONECTAT
							el.save()
							schimbat = True
			elif mod == "advanced":
				for p in sorted(pozitii):
					if p not in nim.advanced.sat:
						continue
					lnb = nim.advanced.sat[p].lnb
					if lnb.value != "0":
						scoase.append((slot.slot, "advanced.sat.%d" % p, p))
						if aplica:
							lnb.value = "0"
							lnb.save()
							schimbat = True
		except Exception as e:
			_jurnal("tunerul %s: %r" % (getattr(slot, "slot", "?"), e))
	if schimbat:
		try:
			if salveaza is None:
				from Components.config import configfile
				salveaza = configfile.save
			salveaza()
		except Exception as e:
			_jurnal("setarile tunerelor nu s-au salvat: %r" % (e,))
		_jurnal("scoase de la tunere: %s" % ", ".join("%s/%s" % (s, c) for s, c, _p in scoase))
	return scoase


def sterge_din_lista(poz, cale=None):
	"""Pentru televizor si pentru pagina web fara modul avansat: satelitul de pe `poz` scos din fisierul citit de nucleu
	(copie de siguranta inainte) si din configurarea tunerelor. Nu revine singur la pornire (unirea nu mai pune la loc
	sateliti). -> (numele satelitului, [(slot, cheie, pozitie)] scoase de la tunere); Eroare (HdsEditorSateliti) cand nu
	merge (atunci nici tunerele nu se ating)."""
	S = _S()
	sateliti = S.citeste(cale)
	s = sateliti.sterge_satelit(poz)
	S.scrie(sateliti, cale)
	p = s.poz
	_jurnal("%s: satelitul %s (%s) sters la cererea omului" % (sateliti.cale, p, s.name))
	return s.name, scoate_de_la_tunere([p])


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
	"""Din NimManager.readTransponders, inainte de eDVBDB.readSatellites: satelitii omului primesc transponderele noi ale
	listei imaginii (unire, o singura scriere, cu copie de siguranta). Din 0.7.7 (SAT) niciun satelit nu se mai pune la
	loc: un satelit care lipseste din fisier ramane lipsa (vezi antetul); lamedb si setari nu se mai citesc (raman ca
	argumente pentru cine le da). Nu ridica niciodata. -> pozitiile satelitilor pusi (mereu []); cu detalii=True
	([], transpondere puse: [(poz, kHz, pol)])"""
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
	cale_im = cale_imagine(cale, copie)
	if cale_im is None:
		return [], []
	# 0.7.7 (SAT): niciun satelit nu se mai pune la loc singur (un satelit sters de om nu revine; vezi antetul)
	sat_lipsa = set()
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
	puse = []
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
