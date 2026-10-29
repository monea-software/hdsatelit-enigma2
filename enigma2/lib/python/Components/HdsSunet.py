# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSunet.py: iesirea sunetului AC3 si DTS spre televizor (HDMI) si spre iesirea optica: „Automat” sau „Manual”.
#
# Driverul are doua comutatoare, /proc/stb/audio/ac3 si /proc/stb/audio/dts, fiecare cu „downmix” (receptorul
# decodeaza si trimite stereo PCM) si „passthrough” (fluxul pleaca neschimbat; il decodeaza televizorul sau bara de
# sunet). Pe HiSilicon (driverele Dinobot) AC3+ (E-AC3) nu are comutator propriu: urmeaza comutatorul ac3.
#
# Manual: hotarasc setarile existente config.av.downmix_ac3 si config.av.downmix_dts (Components/AVSwitch.py).
# Automat: comutatoarele se pun dupa ce anunta aparatul legat prin HDMI (EDID), citit numai din ce arata driverul:
#   - /proc/msp/hdmi0_sink, sectiunea AudioCap (HiSilicon: blocuri NO.x cu CodeType si MaxChannelNum);
#   - rezerva: EDID-ul brut (EDIDRawData din acelasi fisier sau /proc/stb/hdmi/raw_edid), blocul audio CEA-861.
#   Un format pleaca neschimbat numai daca aparatul il anunta cu mai mult de 2 canale; fara EDID valid, stereo.
#   Cand decodorul receptorului pentru un format lipseste (sectiunea „AUD LIB” din /proc/msp/avplay00 are alte
#   biblioteci, dar nu pe acesta), formatul pleaca neschimbat daca aparatul il primeste, altfel nu are alta cale.
# In Automat setarile manuale nu se ating: raman pentru „Manual”. O schimbare a lor facuta de om (isChanged: valoarea
# difera de cea salvata) trece iesirea pe „Manual”; refacerea lor (renuntare, incarcare, pornire) nu.
# Scrierea in /proc/stb/audio trece prin AVSwitch.writeAudioChoice, numai cand valoarea difera de cea din fisier
# (showiframe poate reactiona la fiecare scriere).
# Reevaluarea in Automat: la pornire, la schimbarea setarii si la pornirea fiecarui canal (evStart, inainte sa
# porneasca sunetul), cel mult o data la PAUZA_CITIRE_S dupa o citire valida; dupa o citire fara EDID (televizor
# stins sau inca nepregatit), la fiecare pornire de canal.
#
# stare(): ce se trimite pentru pista care merge si de ce (bara de informatii, ecrane, interfata web); felul pistei
# unui film (servicemp3: „audio/x-ac3”, „E-AC-3”...) se aduce la numele de la canale (felNormal).
# pistaPreferata(): cand AC3 pleaca efectiv neschimbat si setarea pistei e pe Da, intre pistele cu aceeasi limba ca
# pista aleasa trece inainte AC3, apoi AC3+. O alegere facuta de mana (motivul „memorat”) nu se schimba. Randul
# setarii se arata numai cand Components/HdsPisteLimbi.py o cheama (pistaLegata, SystemInfo["HdsSunetPista"]).
# pastreaza(): cat lucreaza, o schimbare a randurilor AC3 / DTS se tine minte pentru Manual fara sa atinga driverul
# (interfata web, cand aceeasi cerere pune si iesirea).
#
# DTS recodat in AC3 (din imaginea 0.4.0): elementul GStreamer hdsdtsac3 (reteta gstreamer1.0-plugin-hds-dts-ac3)
# primeste DTS-ul filmelor de la dcaparse si da AC3 5.1; peticul dvbaudiosink (gstreamer1.0-plugin-dvbmediasink.bbappend)
# nu mai primeste audio/x-dts cand SETARE_DTS_AC3 incepe cu "1", deci decodebin pune elementul intre parser si sink,
# iar AC3-ul pleaca pe calea AC3 (comutatorul ac3: neschimbat pe Automat cu un televizor care il primeste sau pe Manual
# cu AC3 downmix pe Nu). Sink-ul citeste fisierul la negocierea formatului: schimbarea se aplica de la urmatorul film.
# Setarea config.av.hds_dts_ac3 (oprita din fabrica: cine are DTS acum nu vede nicio schimbare) si randul ei
# (SystemInfo["HdsSunetDtsAc3"]) exista numai cand elementul e in imagine; pe 0.3.x nu se vede nimic si nu se scrie
# nimic. Fisierul se scrie numai cand ce spune difera de setare (eMMC).
#
# Partea de sus nu importa enigma: se probeaza pe PC cu arbori /proc falsi (HDS_PROBA_SUNET = radacina lor; nodurile
# /proc/stb/audio vin din AVSwitch.audioRoot, deci din HDS_PROBA_STB_AUDIO).

from __future__ import absolute_import

import os
import re
import threading
import time

IESIRE_MANUAL = "manual"
IESIRE_AUTO = "auto"
IESIRE_IMPLICIT = IESIRE_MANUAL

DOWNMIX = "downmix"
TRECERE = "passthrough"
COMUTATOARE = ("ac3", "dts")

SINK = "proc/msp/hdmi0_sink"
EDID_BINAR = "proc/stb/hdmi/raw_edid"
AVPLAY = ("proc/msp/avplay00", "proc/msp/avplay01")
SOUND = "proc/msp/sound0"
MAX_OCTETI = 65536
PAUZA_CITIRE_S = 20.0
PAUZA_STARE_S = 5.0          # stare() cheamata des (bara, web): fara EDID, se reciteste cel mult o data la 5 s
ASTEPTARE_NAVIGARE_MS = 2000
INCERCARI_NAVIGARE = 90
# DTS recodat in AC3: pluginul GStreamer al elementului hdsdtsac3 si setarea citita de dvbaudiosink (fata de radacina)
ELEMENT_DTS_AC3 = "usr/lib/gstreamer-1.0/libgsthdsdtsac3.so"
SETARE_DTS_AC3 = "etc/enigma2/hds-dts-ac3"

# numele formatelor, ca in enigma (lib/service/servicedvb.cpp: MPEG, AC3, AC3+, AAC, AAC-HE, DTS, DTS-HD, LPCM)
FORMATE_DRIVER = {
	"L-PCM": "PCM", "LPCM": "PCM", "PCM": "PCM", "AC3": "AC3", "EAC3": "AC3+", "E-AC3": "AC3+", "DDP": "AC3+",
	"DTS": "DTS", "DTS-HD": "DTS-HD", "DTSHD": "DTS-HD", "MAT": "TrueHD", "MLP": "TrueHD", "TRUEHD": "TrueHD",
	"AAC": "AAC", "MP3": "MP3", "MPEG1": "MPEG", "MPEG2": "MPEG", "DRA": "DRA",
}
# codurile formatelor din blocul audio CEA-861 (Short Audio Descriptor)
FORMATE_CEA = {1: "PCM", 2: "AC3", 3: "MPEG", 4: "MP3", 5: "MPEG", 6: "AAC", 7: "DTS", 10: "AC3+", 11: "DTS-HD",
	12: "TrueHD"}
# formatele aparatului care deschid fiecare comutator
FORMATE_COMUTATOR = {"ac3": ("AC3",), "dts": ("DTS", "DTS-HD")}
# bibliotecile de decodare ale driverului (libHA.AUDIO.<NUME>.decode.so) pentru fiecare comutator; cele PASSTHROUGH
# numai impacheteaza fluxul, nu decodeaza
DECODOARE = {"ac3": ("AC33", "AC3", "DOLBYPLUS", "DDP", "EAC3", "MS12", "DOLBYMS12"), "dts": ("DTSS", "DTS", "DTSHD", "DTSM6")}

FELURI_AC3 = ("AC3", "AC3+")
FELURI_DTS = ("DTS", "DTS-HD")
NUME_FEL = {"MPEG": "MP2", "AC3": "AC3", "AC3+": "AC3+", "AAC": "AAC", "AAC-HE": "HE-AAC", "DTS": "DTS",
	"DTS-HD": "DTS-HD", "LPCM": "PCM"}
# pistele filmelor (lib/service/servicemp3.cpp): descrierea e numele caps-ului GStreamer („audio/x-ac3”) sau eticheta
# codecului data de demuxer („AC-3 (ATSC A/52)”, „E-AC-3”, „DTS-HD MA”); se compara inceputul, in ordinea de aici
# (cel mai lung intai)
FELURI_FILM = (("AUDIO/X-EAC3", "AC3+"), ("AUDIO/X-AC3", "AC3"), ("AUDIO/X-DTS", "DTS"), ("E-AC-3", "AC3+"),
	("E-AC3", "AC3+"), ("EAC3", "AC3+"), ("AC-3", "AC3"), ("DTS-HD", "DTS-HD"), ("DTS", "DTS"))


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la afisare."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# textele motivelor (codul motivului -> text); %(format)s = numele formatului, %(canale)s = „5.1”
MOTIVE = {
	"tv-primeste": N_("Televizorul primește %(format)s (până la %(canale)s) și îl decodează el."),
	"tv-nu-primeste": N_("Televizorul nu primește %(format)s, deci receptorul îl decodează și trimite stereo."),
	"tv-stereo": N_("Televizorul primește %(format)s numai stereo, deci receptorul îl decodează el."),
	"fara-edid": N_("Televizorul nu a spus ce sunet primește (poate e stins), deci receptorul trimite stereo."),
	"fara-decodor-tv": N_("Receptorul nu are decodor pentru %(format)s; sunetul pleacă neschimbat și îl decodează televizorul."),
	"fara-decodor": N_("Receptorul nu are decodor pentru %(format)s, iar televizorul nu îl primește: pista aceasta poate fi fără sunet. Alege altă pistă de sunet."),
	"manual-trecere": N_("Manual: %(rand)s este pe Nu, deci sunetul pleacă neschimbat."),
	"manual-trecere-fara-tv": N_("Manual: %(rand)s este pe Nu, dar televizorul nu anunță %(format)s. Dacă nu se aude, pune Ieșirea sunetului pe Automat."),
	"manual-downmix": N_("Manual: %(rand)s este pe Da, deci receptorul îl decodează și trimite stereo."),
	"aac": N_("Receptorul decodează AAC și trimite stereo."),
	"mp2": N_("Sunetul MP2 are cel mult două canale."),
	"alt": N_("Receptorul decodează sunetul și trimite stereo."),
}
TEXT_TRIMIS = N_("Sunet: %s, trimis neschimbat la televizor")
TEXT_DECODAT = N_("Sunet: %s, decodat în receptor, stereo")
TEXT_STEREO = N_("Sunet: %s, stereo")
TEXT_VOLUM = N_("Volumul se reglează de la televizor sau de la bara de sunet.")
TEXT_MESAJ_TRECERE = N_("Sunetul AC3 pleacă acum neschimbat spre televizor. Volumul se reglează de la televizor sau de la bara de sunet.")
RAND_COMUTATOR = {"ac3": "AC3 downmix", "dts": "DTS downmix"}

# ce s-a citit si ce s-a scris (numai in memorie)
_STARE = {"tv": None, "tv_t": 0.0, "tv_valid": False, "decodoare": None, "decizie": None, "scris": {}, "nav": None,
	"incercari": 0, "ceas": None, "aplic": False, "pornit": False, "pastreaza": False, "pista_legata": False}


# ---------------------------------------------------------------- citirea (curata, fara enigma)

def radacina():
	return os.environ.get("HDS_PROBA_SUNET") or "/"


def _cale(rad, relativ):
	return os.path.join(rad or radacina(), relativ)


def _citeste(cale, binar=False):
	try:
		with open(cale, "rb") as f:
			date = f.read(MAX_OCTETI)
	except (IOError, OSError):
		return None
	if binar:
		return date
	try:
		return date.decode("utf-8", "replace")
	except Exception:
		return None


# Citirile din /proc ale driverului HiSilicon (/proc/msp/avplay00 si celelalte, /proc/hisi, /proc/stb/hdmi) se fac
# NUMAI intr-un fir de fundal: pe Octagon SF8008 citirea lui /proc/msp/avplay00 a ramas blocata in nucleu, pe firul
# principal, iar paznicul a oprit interfata care nu mai raspundea. Firul principal asteapta citirea cel mult
# ASTEPTARE_CITIRE_S (o citire buna din /proc ia sub o milisecunda), apoi foloseste ce s-a citit deja (None = nu se
# stie). O citire care nu se termina in TIMP_CITIRE_S marcheaza driverul "blocat" pana la repornirea interfetei: nu se
# mai porneste niciun fir (altfel s-ar strange fire blocate), iar sunetul se socoteste ca pana acum fara date
# (decodorul presupus prezent). Un singur fir de citire odata.
PROC_IN_FUNDAL = ("proc/msp/", "proc/hisi/", "proc/stb/hdmi/")
ASTEPTARE_CITIRE_S = 0.2
TIMP_CITIRE_S = 1.0
_FUNDAL = {"fir": None, "pornit_t": 0.0, "blocat": False, "citite": {}}
_FUNDAL_LACAT = threading.Lock()


def citireBlocata():
	"""True dupa o citire din /proc a driverului care n-a raspuns in TIMP_CITIRE_S (pana la repornirea interfetei)."""
	_verificaFirul()
	return _FUNDAL["blocat"]


def _verificaFirul():
	fir = _FUNDAL["fir"]
	if not _FUNDAL["blocat"] and fir is not None and fir.is_alive() and time.time() - _FUNDAL["pornit_t"] > TIMP_CITIRE_S:
		_FUNDAL["blocat"] = True
		print("[HdsSunet] citirea din /proc a driverului nu raspunde de %.1f s (%s): nu mai citesc pana la repornirea "
			"interfetei" % (time.time() - _FUNDAL["pornit_t"], getattr(fir, "hds_cale", "?")))


def _citesteInFir(cale, binar):
	t0 = time.time()
	date = _citeste(cale, binar)
	durata = time.time() - t0
	with _FUNDAL_LACAT:
		_FUNDAL["citite"][(cale, binar)] = date
	if durata > TIMP_CITIRE_S and not _FUNDAL["blocat"]:
		_FUNDAL["blocat"] = True
		print("[HdsSunet] citirea lui %s a durat %.1f s: nu mai citesc pana la repornirea interfetei" % (cale, durata))


def _citesteProc(cale, binar=False):
	"""Ca _citeste, pentru fisierele driverului (PROC_IN_FUNDAL): citirea in fundal, asteptata cel mult
	ASTEPTARE_CITIRE_S; altfel ce s-a citit ultima data (None la inceput)."""
	_verificaFirul()
	if not _FUNDAL["blocat"]:
		fir = _FUNDAL["fir"]
		if fir is None or not fir.is_alive():
			fir = threading.Thread(target=_citesteInFir, args=(cale, binar), name="HdsSunetProc")
			fir.daemon = True
			fir.hds_cale = cale
			_FUNDAL["fir"], _FUNDAL["pornit_t"] = fir, time.time()
			fir.start()
			fir.join(ASTEPTARE_CITIRE_S)
			_verificaFirul()
	with _FUNDAL_LACAT:
		return _FUNDAL["citite"].get((cale, binar))


def _citesteDriver(rad, relativ, binar=False):
	"""Un fisier al arborelui /proc: cele ale driverului (PROC_IN_FUNDAL) prin firul de fundal, celelalte direct."""
	cale = _cale(rad, relativ)
	if relativ.startswith(PROC_IN_FUNDAL):
		return _citesteProc(cale, binar)
	return _citeste(cale, binar)


def _sectiune(text, nume):
	"""Textul dintre antetul „---- <nume> ----” si antetul urmator, sau None."""
	m = re.search(r"-{3,}\s*" + re.escape(nume) + r"\s*-{3,}[^\n]*\n", text or "")
	if not m:
		return None
	rest = text[m.end():]
	n = re.search(r"^\s*-{3,}", rest, re.M)
	return rest[:n.start()] if n else rest


def _adauga(rez, fmt, canale):
	if not fmt:
		return
	vechi = rez.get(fmt)
	if vechi is None or (canale or 0) > vechi:
		rez[fmt] = canale or 0


def formateDinSink(text):
	"""Sectiunea AudioCap din /proc/msp/hdmi0_sink -> {"PCM": 2, "AC3": 6, "AC3+": 6}; {} cand EDID-ul e valid dar
	fara sectiune; None cand driverul spune ca EDID-ul nu e valid sau fisierul lipseste."""
	if not text:
		return None
	if re.search(r"CapIsValid\s*:\s*NO\b", text) or re.search(r"CapFromSink\s*:\s*NO\b", text):
		return None
	bloc = _sectiune(text, "AudioCap")
	if bloc is None:
		return {}
	rez = {}
	for parte in re.split(r"NO\.\d+\s*:", bloc):
		m = re.search(r"CodeType\s*:\s*(\S+)", parte)
		if not m:
			continue
		cod = m.group(1).strip().upper()
		fmt = FORMATE_DRIVER.get(cod, cod)
		c = re.search(r"MaxChannelNum\s*:\s*(\d+)", parte)
		_adauga(rez, fmt, int(c.group(1)) if c else 0)
	return rez


def edidDinText(text):
	"""Octetii EDID din sectiunea EDIDRawData a lui hdmi0_sink („0x00,0xff,...”), sau b"" cand lipsesc."""
	bloc = _sectiune(text or "", "EDIDRawData")
	if not bloc:
		return b""
	octeti = [int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]{2})", bloc)]
	return bytes(bytearray(octeti))


def formateDinEdid(date):
	"""Blocul audio din extensiile CEA-861 ale unui EDID brut -> {"PCM": 2, "AC3": 6, ...}; None cand EDID-ul lipseste
	sau nu are antetul corect; {} cand nu are extensie CEA sau bloc audio."""
	if not date or len(date) < 128:
		return None
	date = bytearray(date)
	if date[0:8] != bytearray(b"\x00\xff\xff\xff\xff\xff\xff\x00"):
		return None
	rez = {}
	for start in range(128, len(date) - 127, 128):
		bloc = date[start:start + 128]
		if bloc[0] != 0x02:
			continue
		sfarsit = bloc[2]
		if sfarsit < 4 or sfarsit > 127:
			continue
		i = 4
		while i < sfarsit:
			antet = bloc[i]
			eticheta, lungime = (antet >> 5) & 7, antet & 0x1f
			if eticheta == 1:
				for j in range(i + 1, min(i + 1 + lungime, sfarsit) - 2, 3):
					cod = (bloc[j] >> 3) & 0x0f
					_adauga(rez, FORMATE_CEA.get(cod), (bloc[j] & 7) + 1)
			i += 1 + lungime
	return rez


def formateTv(rad=None):
	"""Ce sunet primeste aparatul legat prin HDMI: {"PCM": 2, "AC3": 6, ...}, sau None cand nu se stie (fara HDMI,
	televizor stins, EDID invalid, alt driver fara fisierele de mai sus)."""
	text = _citesteDriver(rad, SINK)
	rez = formateDinSink(text)
	if rez:
		return rez
	if text is not None and rez is None:
		return None             # driverul HiSilicon spune ca nu are EDID valid
	edid = edidDinText(text) if text else b""
	if not edid:
		edid = _citesteDriver(rad, EDID_BINAR, binar=True) or b""
	din_edid = formateDinEdid(edid)
	if din_edid:
		return din_edid
	return rez if rez is not None else din_edid


def decodoare(rad=None):
	"""{"ac3": True/False/None, "dts": ...}: daca driverul are decodorul fiecarui comutator, din „AUD LIB” (avplay00).
	None = nu se stie (fisier lipsa, lista goala)."""
	rez = dict((n, None) for n in COMUTATOARE)
	for rel in AVPLAY:
		text = _citesteDriver(rad, rel)
		if not text:
			continue
		bloc = _sectiune(text, "AUD LIB")
		if bloc is None:
			continue
		nume = set(n.upper() for n in re.findall(r"libHA\.AUDIO\.([A-Za-z0-9_]+)\.(?:decode|codec)\.so", bloc))
		if not nume:
			continue
		for n in COMUTATOARE:
			rez[n] = any(d in nume for d in DECODOARE[n])
		return rez
	return rez


def formatIesire(rad=None):
	"""Ce arata driverul ca pleaca acum pe HDMI si pe optic (/proc/msp/sound0: „DataFormat(PCM)”):
	{"hdmi": "PCM", "optic": "PCM"}, cu None unde nu se stie."""
	text = _citesteDriver(rad, SOUND) or ""
	rez = {"hdmi": None, "optic": None}
	for cheie, eticheta in (("hdmi", "HDMI"), ("optic", "SPDIF")):
		m = re.search(eticheta + r"\s+Status\s*:[^\n]*?DataFormat\(([^)]*)\)", text)
		if m:
			rez[cheie] = m.group(1).strip() or None
	return rez


def textCanale(n):
	if not n:
		return u""
	return {1: u"mono", 2: u"stereo", 3: u"2.1", 6: u"5.1", 7: u"6.1", 8: u"7.1"}.get(int(n), u"%d" % int(n))


def textTv(tv):
	"""„PCM stereo, AC3 5.1, AC3+ 5.1” (numai numele formatelor si canalele anuntate de aparat)."""
	if not tv:
		return u""
	ordine = ("PCM", "AC3", "AC3+", "DTS", "DTS-HD", "TrueHD", "AAC", "MPEG", "MP3")
	chei = sorted(tv.keys(), key=lambda k: (ordine.index(k) if k in ordine else len(ordine), k))
	return u", ".join((u"%s %s" % (k, textCanale(tv[k]))).strip() for k in chei)


# ---------------------------------------------------------------- decizia (curata)

def decide(tv, dec=None):
	"""Automat: {"ac3": (valoare, motiv, format), "dts": (...)}. tv = formateTv() (None = nu se stie); dec =
	decodoare() (None sau valori None = decodorul se presupune prezent)."""
	dec = dec or {}
	rez = {}
	for n in COMUTATOARE:
		fmt = FORMATE_COMUTATOR[n][0]
		anuntat = bool(tv) and any(f in tv for f in FORMATE_COMUTATOR[n])
		canale = max([tv.get(f) or 0 for f in FORMATE_COMUTATOR[n] if f in tv] + [0]) if anuntat else 0
		fara_decodor = dec.get(n) is False
		if fara_decodor:
			rez[n] = (TRECERE, "fara-decodor-tv", fmt) if anuntat else (DOWNMIX, "fara-decodor", fmt)
		elif tv is None:
			rez[n] = (DOWNMIX, "fara-edid", fmt)
		elif anuntat and canale > 2:
			rez[n] = (TRECERE, "tv-primeste", fmt)
		elif anuntat:
			rez[n] = (DOWNMIX, "tv-stereo", fmt)
		else:
			rez[n] = (DOWNMIX, "tv-nu-primeste", fmt)
	return rez


def felNormal(fel):
	"""felul pistei cu numele de la canale (AC3, AC3+, DTS, DTS-HD...), si pentru pistele filmelor (FELURI_FILM)"""
	fel = (fel or "").strip().upper()
	if fel in NUME_FEL:
		return fel
	for inceput, nume in FELURI_FILM:
		if fel.startswith(inceput):
			return nume
	return fel


def comutatorPentru(fel):
	fel = felNormal(fel)
	if fel in FELURI_AC3:
		return "ac3"
	if fel in FELURI_DTS:
		return "dts"
	return None


def areDtsAc3(rad=None):
	"""True cand imaginea are elementul hdsdtsac3 (din 0.4.0): numai atunci exista setarea si randul ei"""
	return os.path.isfile(_cale(rad, ELEMENT_DTS_AC3))


def dtsAc3Scris(rad=None):
	"""Ce vede dvbaudiosink acum: True cand fisierul setarii incepe cu "1" (lipsa = oprit)"""
	date = _citeste(_cale(rad, SETARE_DTS_AC3), binar=True)
	return bool(date) and date[:1] == b"1"


def scrieDtsAc3(pornit, rad=None):
	"""Fisierul pentru dvbaudiosink ("1" / "0"), scris (.nou, apoi mutat peste) numai cand ce spune difera de `pornit`:
	oprit fara fisier nu scrie nimic. True daca s-a scris."""
	pornit = bool(pornit)
	if dtsAc3Scris(rad) == pornit:
		return False
	cale = _cale(rad, SETARE_DTS_AC3)
	nou = cale + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(b"1\n" if pornit else b"0\n")
		os.replace(nou, cale)
	except (IOError, OSError) as e:
		print("[HdsSunet] DTS recodat in AC3: %s nu s-a scris: %s" % (cale, e))
		return False
	print("[HdsSunet] DTS recodat in AC3: %s" % ("pornit" if pornit else "oprit"))
	return True


def _laSchimbareaDtsAc3(element):
	scrieDtsAc3(element.value)


def textMotiv(cod, fmt=u"", canale=0, rand=u""):
	sablon = MOTIVE.get(cod)
	if not sablon:
		return u""
	try:
		return _t(sablon) % {"format": fmt, "canale": textCanale(canale) or u"5.1", "rand": _t(rand)}
	except Exception:
		return _t(sablon)


# ---------------------------------------------------------------- setarile si scrierea (cu enigma, importuri tarzii)

def _config():
	from Components.config import config
	return config


def _setare(nume):
	try:
		return getattr(_config().av, nume)
	except Exception:
		return None


def areComutatoare():
	try:
		from Components.AVSwitch import AUDIO_CHOICES
	except Exception:
		return False
	return any(DOWNMIX in (AUDIO_CHOICES.get(n) or ()) and TRECERE in (AUDIO_CHOICES.get(n) or ()) for n in COMUTATOARE)


def initConfig():
	"""Setarile noi, inainte de setarile AC3 / DTS downmix (Components/AVSwitch.InitAVSwitch), fara notificatori."""
	from Components.config import config, ConfigSelection, ConfigYesNo
	from Components.SystemInfo import SystemInfo
	# etichete scurte (lista Setup are 1176 px si pentru literele marite); ce inseamna fiecare spune descrierea randului.
	# Textele raman netraduse: setarea se face la pornire, inainte ca limba sa fie activa, iar ConfigSelection si
	# pagina web le traduc la afisare.
	config.av.hds_sunet_iesire = ConfigSelection(choices=[
		(IESIRE_AUTO, N_("Automat")),
		(IESIRE_MANUAL, N_("Manual"))], default=IESIRE_IMPLICIT)
	config.av.hds_sunet_pista51 = ConfigYesNo(default=True)
	config.av.hds_sunet_mesaj = ConfigYesNo(default=False)
	SystemInfo["HdsSunet"] = areComutatoare()
	_STARE["pista_legata"] = SystemInfo["HdsSunet"] and _pistaLegataAcum()
	SystemInfo["HdsSunetPista"] = _STARE["pista_legata"]
	# DTS recodat in AC3: numai cu elementul in imagine; notificatorul face fisierul ca setarea si la pornire (de pilda
	# dupa o copie a setarilor pusa la loc), fara scriere cand e deja la fel
	SystemInfo["HdsSunetDtsAc3"] = False
	try:
		if areDtsAc3():
			config.av.hds_dts_ac3 = ConfigYesNo(default=False)
			config.av.hds_dts_ac3.addNotifier(_laSchimbareaDtsAc3, initial_call=True)
			SystemInfo["HdsSunetDtsAc3"] = True
	except Exception as e:
		print("[HdsSunet] DTS recodat in AC3: %s" % e)


def _pistaLegataAcum():
	"""True cand Components/HdsPisteLimbi.py cheama pistaPreferata la alegerea pistei (functia _pista51); fara ea
	randul „Alege singur pista AC3” n-ar avea niciun efect, deci nu se arata nici pe televizor, nici in web"""
	try:
		from Components import HdsPisteLimbi
	except Exception:
		return False
	return hasattr(HdsPisteLimbi, "_pista51")


def pistaLegata():
	return bool(_STARE.get("pista_legata"))


class pastreaza(object):
	"""with pastreaza(): o schimbare a randurilor AC3 / DTS downmix facuta intre timp nu scrie in driver si nu trece
	iesirea pe Manual (laSchimbareDeMana); valoarea ramane pentru Manual. Dupa aceea comutatoarele se pun o
	singura data (aplica sau notificatorul iesirii)."""

	def __enter__(self):
		_STARE["pastreaza"] = True
		return self

	def __exit__(self, *a):
		_STARE["pastreaza"] = False
		return False


def automat():
	el = _setare("hds_sunet_iesire")
	return el is not None and el.value == IESIRE_AUTO and areComutatoare()


def _valoareNod(nume):
	try:
		from Components.AVSwitch import audioRoot
		with open(os.path.join(audioRoot(), nume)) as f:
			return f.read().strip()
	except Exception:
		return None


def efectiv(nume):
	"""Ce e acum in comutator: DOWNMIX, TRECERE sau None (fara comutator)."""
	v = _valoareNod(nume)
	if v in (DOWNMIX, TRECERE):
		return v
	return _STARE["scris"].get(nume)


def _scrie(nume, valoare):
	"""Scrie in comutator numai cand difera de ce e acolo. True daca s-a scris."""
	try:
		from Components.AVSwitch import AUDIO_CHOICES, writeAudioChoice
	except Exception:
		return False
	if valoare not in (AUDIO_CHOICES.get(nume) or ()):
		return False
	if _valoareNod(nume) == valoare:
		_STARE["scris"][nume] = valoare
		return False
	if writeAudioChoice(nume, valoare):
		_STARE["scris"][nume] = valoare
		return True
	return False


def _mesajVolum():
	"""O singura data pe receptor: la prima trecere a sunetului AC3 pe trimitere neschimbata."""
	el = _setare("hds_sunet_mesaj")
	if el is None or el.value:
		return
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(_t(TEXT_MESAJ_TRECERE), MessageBox.TYPE_INFO, 15, "HdsSunetVolum")
	except Exception as e:
		print("[HdsSunet] mesajul despre volum: %s" % e)
		return
	el.value = True
	el.save()


def valoriManuale():
	rez = {}
	for n in COMUTATOARE:
		el = _setare("downmix_" + n)
		if el is not None:
			rez[n] = DOWNMIX if el.value else TRECERE
	return rez


def citesteTv(fortat=False, acum=None, pauzaInvalid=0.0):
	"""Formatele aparatului, recitite cel mult o data la PAUZA_CITIRE_S dupa o citire valida si cel mult o data la
	`pauzaInvalid` secunde dupa una fara EDID (fortat = oricum)."""
	acum = time.time() if acum is None else acum
	trecut = acum - _STARE["tv_t"]
	if (fortat or not _STARE["tv_t"] or trecut < 0 or trecut >= PAUZA_CITIRE_S
			or (not _STARE["tv_valid"] and trecut >= pauzaInvalid)):
		tv = formateTv()
		_STARE["tv"], _STARE["tv_t"], _STARE["tv_valid"] = tv, acum, tv is not None
		dec = decodoare()
		if any(v is not None for v in dec.values()) or _STARE["decodoare"] is None:
			_STARE["decodoare"] = dec
	return _STARE["tv"]


def aplica(fortat=False, acum=None, laPornire=False):
	"""Pune comutatoarele dupa setare: in Automat dupa aparatul legat, in Manual dupa randurile AC3 / DTS downmix.
	Intoarce {nume: valoarea dorita}. La pornire (inainte de interfata) nu se pune niciun mesaj."""
	if not areComutatoare():
		return {}
	if automat():
		citesteTv(fortat, acum)
		decizie = decide(_STARE["tv"], _STARE["decodoare"])
		_STARE["decizie"] = decizie
		dorit = dict((n, decizie[n][0]) for n in decizie)
	else:
		_STARE["decizie"] = None
		dorit = valoriManuale()
	inainte_ac3 = efectiv("ac3")
	_STARE["aplic"] = True
	try:
		for n in COMUTATOARE:
			if n in dorit:
				_scrie(n, dorit[n])
	finally:
		_STARE["aplic"] = False
	if dorit.get("ac3") == TRECERE and inainte_ac3 != TRECERE and not laPornire:
		_mesajVolum()
	return dorit


def treciPeManual():
	"""Iesirea trece pe Manual (si se salveaza); notificatorul ei pune comutatoarele dupa randurile AC3 / DTS."""
	el = _setare("hds_sunet_iesire")
	if el is None or el.value == IESIRE_MANUAL:
		return False
	el.value = IESIRE_MANUAL
	el.save()
	print("[HdsSunet] iesirea sunetului trece pe Manual (schimbare de mana a randurilor AC3 / DTS)")
	_redeseneazaRandul(el)
	return True


def _redeseneazaRandul(el):
	"""Ecranul deschis care arata randul „Ieșirea sunetului” (Setari A/V: schimbarea s-a facut pe alt rand al lui)
	redeseneaza randul cu valoarea noua; ConfigList redeseneaza singur numai randul curent."""
	try:
		from Screens.InfoBar import InfoBar
		sesiune = InfoBar.instance.session
		lista = sesiune.current_dialog["config"]
		randuri = lista.list
	except Exception:
		return
	for rand in randuri or ():
		if isinstance(rand, tuple) and len(rand) > 1 and rand[1] is el:
			try:
				lista.invalidate(rand)
			except Exception as e:
				print("[HdsSunet] randul iesirii nu s-a redesenat: %s" % e)
			return


def laSchimbareDeMana(nume, element):
	"""Din notificatorii setarilor AC3 / DTS downmix (AVSwitch): True daca AVSwitch trebuie sa scrie valoarea acum.
	In Manual: da. In Automat: o schimbare facuta de om trece iesirea pe Manual (care scrie tot); altfel comutatorul
	e al lui Automat si nu se scrie nimic. In pastreaza(): nu se scrie nimic si iesirea ramane cum e."""
	if _STARE.get("pastreaza"):
		return False
	if not automat():
		return True
	try:
		schimbat = element.isChanged()
	except Exception:
		schimbat = False
	if schimbat:
		treciPeManual()
	return False


def _laSchimbareaIesirii(element):
	aplica(fortat=True, laPornire=not _STARE["pornit"])


def _laEveniment(ev):
	try:
		from enigma import iPlayableService
		if ev != iPlayableService.evStart:
			return
	except Exception:
		return
	if automat():
		try:
			aplica()
		except Exception as e:
			print("[HdsSunet] reevaluarea la pornirea canalului: %s" % e)


def _legaNavigarea():
	"""Se leaga la evenimentele serviciilor cand exista Navigation (se creeaza dupa InitAVSwitch)."""
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
	except Exception:
		nav = None
	if nav is not None:
		if _laEveniment not in nav.event:
			nav.event.append(_laEveniment)
		_STARE["nav"] = nav
		print("[HdsSunet] legat la pornirea canalelor (reevaluarea pe Automat)")
		return
	_STARE["incercari"] += 1
	if _STARE["incercari"] < INCERCARI_NAVIGARE and _STARE["ceas"] is not None:
		_STARE["ceas"].start(ASTEPTARE_NAVIGARE_MS, True)
	else:
		print("[HdsSunet] fara Navigation dupa %d incercari: Automat nu se mai reevalueaza la pornirea canalelor"
			% _STARE["incercari"])


def porneste():
	"""Dupa setarile AC3 / DTS downmix: notificatorul iesirii (pune comutatoarele o data acum) si legatura la
	pornirea canalelor."""
	el = _setare("hds_sunet_iesire")
	if el is None:
		return
	el.addNotifier(_laSchimbareaIesirii, initial_call=True)
	_STARE["pornit"] = True
	try:
		from enigma import eTimer
		ceas = eTimer()
		ceas.callback.append(_legaNavigarea)
		_STARE["ceas"] = ceas
		ceas.start(ASTEPTARE_NAVIGARE_MS, True)
	except Exception as e:
		print("[HdsSunet] fara reevaluare la pornirea canalelor: %s" % e)


# ---------------------------------------------------------------- pista 5.1 (pentru Components/HdsPisteLimbi.py)

def prefera51():
	"""True cand intre pistele de aceeasi limba AC3 / AC3+ trebuie sa treaca inainte: setarea e pe Da si comutatorul
	ac3 e efectiv pe trimitere neschimbata (nu setarea manuala, care in Automat doarme)."""
	el = _setare("hds_sunet_pista51")
	if el is None or not el.value:
		return False
	return efectiv("ac3") == TRECERE


def _limbaPistei(p):
	limbi = p.get("limbi") or ()
	return limbi[0] if limbi else None


def pistaPreferata(piste, index, curenta, motiv=None):
	"""Dupa alegerea dupa limba (HdsPisteLimbi.alegePistaAudio: index, motiv; index None = ramane `curenta`):
	indexul pistei AC3 (apoi AC3+) cu aceeasi prima limba ca pista aleasa, cand prefera51(); altfel `index`.
	`piste` = forma comuna din HdsPisteLimbi (index, fel, limbi, descriere)."""
	if motiv == "memorat" or not piste:
		return index
	ales = index if index is not None else curenta
	pista = None
	for p in piste:
		if p.get("index") == ales:
			pista = p
			break
	if pista is None or (pista.get("fel") or "").upper() == "AC3":
		return index
	if not prefera51():
		return index
	limba = _limbaPistei(pista)
	cand = [p for p in piste if (p.get("fel") or "").upper() in FELURI_AC3 and not p.get("descriere")
		and _limbaPistei(p) == limba]
	if not cand:
		return index
	cand.sort(key=lambda p: (FELURI_AC3.index((p.get("fel") or "").upper()), 0 if p.get("index") == curenta else 1,
		p.get("index")))
	ales_nou = cand[0]["index"]
	if (pista.get("fel") or "").upper() == "AC3+" and ales_nou == ales:
		return index
	return ales_nou


# ---------------------------------------------------------------- starea, pentru bara, ecrane si web

def felPistei(service):
	"""Felul pistei audio care merge („AC3”, „MPEG”, ...) sau None."""
	try:
		audio = service and service.audioTracks()
		if not audio:
			return None
		i = audio.getCurrentTrack()
		if i is None or i < 0:
			return None
		info = audio.getTrackInfo(i)
		return (info.getDescription() or "").strip().upper() or None
	except Exception:
		return None


def stare(fel=None, service=None, cuDriver=False):
	"""Ce se trimite pentru pista care merge si de ce. `fel` = felul pistei (sau din `service`). Intoarce:
	{"iesire": auto/manual, "fel", "format" (numele pe ecran), "trimis" (True = neschimbat, False = decodat, None =
	fara comutator), "text" („Sunet: AC3, trimis neschimbat la televizor”), "motiv", "volum" (textul despre volum,
	numai la trimitere), "tv" (formatele aparatului sau None), "tv_text", "comutatoare" {ac3, dts}, "driver"
	(numai cu cuDriver: {"hdmi", "optic"} din /proc/msp/sound0)}."""
	if fel is None and service is not None:
		fel = felPistei(service)
	fel = felNormal(fel)
	auto = automat()
	tv = citesteTv(pauzaInvalid=PAUZA_STARE_S)
	comutatoare = dict((n, efectiv(n)) for n in COMUTATOARE)
	rez = {"iesire": IESIRE_AUTO if auto else IESIRE_MANUAL, "fel": fel or None, "format": None, "trimis": None,
		"text": u"", "motiv": u"", "volum": u"", "tv": tv, "tv_text": textTv(tv), "comutatoare": comutatoare}
	if cuDriver:
		rez["driver"] = formatIesire()
	if not fel:
		return rez
	fmt = NUME_FEL.get(fel, fel)
	rez["format"] = fmt
	n = comutatorPentru(fel)
	if n is None or comutatoare.get(n) is None:
		rez["text"] = _t(TEXT_STEREO) % fmt
		cod = "aac" if fel.startswith("AAC") else ("mp2" if fel == "MPEG" else "alt")
		rez["motiv"] = textMotiv(cod)
		return rez
	trimis = comutatoare[n] == TRECERE
	rez["trimis"] = trimis
	rez["text"] = (_t(TEXT_TRIMIS) if trimis else _t(TEXT_DECODAT)) % fmt
	canale = 0
	if tv:
		canale = max([tv.get(f, 0) or 0 for f in FORMATE_COMUTATOR[n]] + [0])
	if auto:
		decizie = _STARE["decizie"] or decide(tv, _STARE["decodoare"])
		cod = decizie[n][1]
		rez["motiv"] = textMotiv(cod, FORMATE_COMUTATOR[n][0] if cod.startswith("fara-decodor") else fmt, canale)
	else:
		anuntat = bool(tv) and any(f in tv for f in FORMATE_COMUTATOR[n])
		if trimis:
			cod = "manual-trecere" if (anuntat or tv is None) else "manual-trecere-fara-tv"
		else:
			cod = "manual-downmix"
		rez["motiv"] = textMotiv(cod, fmt, canale, RAND_COMUTATOR[n])
	if trimis:
		rez["volum"] = _t(TEXT_VOLUM)
	return rez
