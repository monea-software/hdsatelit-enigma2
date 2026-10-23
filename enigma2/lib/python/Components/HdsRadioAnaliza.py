# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRadioAnaliza.py: nivelurile sunetului unui post de radio, din fluxul lui, pe orice format de sunet.
#
# Fluxul audio al postului se citeste in paralel cu decodorul, din demultiplexor, cu acelasi fel de filtru ca cititorul
# de RDS al nucleului (eDVBPESReader din lib/dvb/demux.cpp): /dev/dvb/adapterA/demuxD deschis O_RDWR,
# DMX_SET_BUFFER_SIZE 64 KB, DMX_SET_PES_FILTER cu DMX_IN_FRONTEND, DMX_OUT_TAP, DMX_PES_OTHER si
# DMX_IMMEDIATE_START, DMX_STOP si close la oprire. Citirea e intr-un fir separat (poll cu 0,5 s, os.read), deci
# firul enigma2 nu asteapta niciodata dupa demultiplexor. Sunetul auzit nu se atinge, iar fluxul e acelasi si cand
# iesirea trimite AC-3 / DTS neschimbat spre bara de sunet, deci barele merg si atunci.
#
# Din PES se scoate fluxul elementar (stream id 0xC0-0xDF si 0xBD). Felul sunetului se afla din el (trei cadre la rand
# de acelasi fel), iar barele se fac din datele fiecarui format, fara decodarea sunetului:
# - MPEG-1/2 Layer II si Layer I (aici, in Python): factorii de scala ai celor 32 de subbenzi, adica varful semnalului
#   din banda, in trepte de 2 dB (cam 250 de campuri de biti pe cadru). La 48 kHz o subbanda are 750 Hz;
# - AAC (ADTS, LATM/LOAS; LC si miezul HE-AAC), AC-3, E-AC-3, DTS si PCM SMPTE 302M: in nucleu, eHdsSpectru
#   (lib/dvb/hdsspectru.cpp): liniile spectrale AAC, exponentii AC-3 / E-AC-3, factorii de scala DTS, esantioanele PCM,
#   adunate pe aceleasi 32 de benzi si aduse pe aceeasi scara ca la MP2. Aici se afla felul, se taie cadrele si se da
#   nucleului cate un cadru, cel mult 32 pe secunda (la AAC fiecare al doilea, la AC-3 fiecare, la DTS fiecare al
#   treilea); nucleul lucreaza fara GIL.
# Pentru ecran si web rezultatul e acelasi pe orice format: (subbenzi, f0, f1), deci desenul nu stie de format.
#
# Starea e cinstita: fara date in 3 secunde sau filtrul refuzat -> „fara-date”, cu motivul in cuvinte, o singura linie
# in jurnal, fara reincercari in bucla. Un format cunoscut fara nucleu (imagine veche) sau cu cadre pe care nucleul nu
# le poate citi -> „fara-bare”; un format necunoscut -> „necunoscut”. Firul nu arunca niciodata: orice greseala il
# opreste cu starea „fara-date”.
#
# Fisierul nu importa nimic din enigma2 la incarcare (eHdsSpectru se cauta la primul cadru care il cere); se poate proba
# pe PC (probele dau un os si un fcntl falsi si pot da nucleul prin FABRICA_SPECTRU) si din fisier (SursaFisier), fara
# demultiplexor.

import math
import os
import re
import struct
import threading
import time
from collections import deque

# ---------------------------------------------------------------- API-ul Linux DVB (linux/dvb/dmx.h)

_IOC_NONE = 0
_IOC_WRITE = 1


def _IOC(directie, tip, nr, marime):
	return (directie << 30) | (marime << 16) | (ord(tip) << 8) | nr


# struct dmx_pes_filter_params { __u16 pid; enum input; enum output; enum pes_type; __u32 flags; }: 20 de octeti,
# cu doi octeti de aliniere dupa pid; ordinea octetilor e a masinii
PES_FILTRU = struct.Struct("=H2xIIII")
DMX_START = _IOC(_IOC_NONE, "o", 41, 0)
DMX_STOP = _IOC(_IOC_NONE, "o", 42, 0)
DMX_SET_PES_FILTER = _IOC(_IOC_WRITE, "o", 44, PES_FILTRU.size)
DMX_SET_BUFFER_SIZE = _IOC(_IOC_NONE, "o", 45, 0)
DMX_IN_FRONTEND = 0
DMX_OUT_TAP = 1
DMX_PES_OTHER = 20
DMX_IMMEDIATE_START = 4
MARIME_TAMPON = 64 * 1024

DEMUX = "/dev/dvb/adapter%d/demux%d"

# ---------------------------------------------------------------- timpi si limite

FARA_DATE_S = 3.0          # fara niciun octet atata timp: starea „fara-date”
POLL_MS = 500
CITIRE_MAX = 16384
ES_MAX = 65536             # fluxul elementar nesincronizat nu creste peste atat
PES_MAX = 262144
CADRE_TINUTE = 16          # ultimele cadre MP2 (cam 0,4 s la 48 kHz), pentru ferestrele cerute de ecran si de web
DEBIT_FEREASTRA_S = 2.0
FACTOR_GOL = 63            # indicele factorului de scala pentru „nimic in banda”
# banda de sus a postului: cea mai inalta subbanda cu date in ultimele BANDA_FEREASTRA_S secunde (codorul taie
# frecventele inalte dupa debit: la 128-256 kbit/s pe la 15-17 kHz), numarata numai daca are date in cel putin
# BANDA_PRAG din cadre (o subbanda atinsa rar ar lasa o bara aproape mereu goala). Urca in cel mult o secunda, coboara
# numai dupa fereastra intreaga, ca barele sa nu se aseze altfel la fiecare pasaj linistit. Masurat pe muzica codata
# MP2 la 256 kbit/s: cea mai inalta subbanda cu date e 19-23 din 27 (23 in 3% din cadre, 22 in 42%).
BANDA_FEREASTRA_S = 10
BANDA_PRAG = 0.1
BANDA_MINIMA = 4

# ---------------------------------------------------------------- MPEG audio Layer II

DEBITE_MPEG1_L2 = (0, 32, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384)
DEBITE_LSF_L2 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)
FRECVENTE = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000)}
MODURI = ("stereo", "joint_stereo", "dual", "mono")


def _biti_alocare(tabel):
	"""Bitii campului de alocare pe fiecare subbanda, pentru tabelele B.2a-d din ISO 11172-3 si B.1 din 13818-3."""
	if tabel in (0, 1):
		return (4,) * 11 + (3,) * 12 + (2,) * ((27 if tabel == 0 else 30) - 23)
	if tabel == 2:
		return (4,) * 2 + (3,) * 6
	if tabel == 3:
		return (4,) * 2 + (3,) * 10
	return (4,) * 4 + (3,) * 7 + (2,) * 19


BITI_ALOCARE = tuple(_biti_alocare(t) for t in range(5))


def tabel_alocare(kbps, canale, frecventa, lsf):
	"""Tabelul de alocare dupa debitul pe canal si esantionare (ca in ISO 11172-3, anexa B)."""
	if lsf:
		return 4
	pe_canal = kbps // canale
	if (frecventa == 48000 and pe_canal >= 56) or (56 <= pe_canal <= 80):
		return 0
	if frecventa != 48000 and pe_canal >= 96:
		return 1
	if frecventa != 32000 and pe_canal <= 48:
		return 2
	return 3


def antet_mp2(b, i):
	"""Antetul cadrului MPEG-1/2 Layer II de la pozitia i: (lungime, kbps, frecventa, mod, extensie_mod, crc, lsf)
	sau None."""
	if i + 4 > len(b) or b[i] != 0xFF or (b[i + 1] & 0xE0) != 0xE0:
		return None
	v = (b[i + 1] >> 3) & 3
	strat = (b[i + 1] >> 1) & 3
	if strat != 2 or v not in (2, 3):
		return None
	crc = not (b[i + 1] & 1)
	idx_debit = b[i + 2] >> 4
	idx_frecv = (b[i + 2] >> 2) & 3
	if idx_debit in (0, 15) or idx_frecv == 3:
		return None
	umplere = (b[i + 2] >> 1) & 1
	mod = b[i + 3] >> 6
	ext = (b[i + 3] >> 4) & 3
	lsf = v == 2
	kbps = (DEBITE_LSF_L2 if lsf else DEBITE_MPEG1_L2)[idx_debit]
	frecv = FRECVENTE[v][idx_frecv]
	lungime = 144000 * kbps // frecv + umplere
	if lungime < 8:
		return None
	return (lungime, kbps, frecv, mod, ext, crc, lsf)


_ZERO = bytes(200)


def factori_mp2(b, i, antet):
	"""Factorii de scala ai cadrului: (subbenzi, [indicii canalului 0], [ai canalului 1 sau None]); pentru fiecare
	subbanda cel mai mic indice din cadru (varful), FACTOR_GOL unde banda nu are nimic. None daca cadrul nu se poate
	citi pana la capat (intrare stricata)."""
	lungime, kbps, frecv, mod, ext, crc, lsf = antet
	canale = 1 if mod == 3 else 2
	tabel = tabel_alocare(kbps, canale, frecv, lsf)
	biti = BITI_ALOCARE[tabel]
	subbenzi = len(biti)
	limita = (4 + ext * 4) if mod == 1 else subbenzi
	if limita > subbenzi:
		limita = subbenzi
	start = i + 4 + (2 if crc else 0)
	sfarsit = i + lungime
	bucata = bytes(b[start:min(sfarsit, start + 200)])
	L_real = len(bucata) * 8
	if len(bucata) < 200:
		bucata = bucata + _ZERO[:200 - len(bucata)]
	L = 1600
	n = int.from_bytes(bucata, "big")
	poz = 0
	aloc0 = [0] * subbenzi
	aloc1 = [0] * subbenzi
	for sb in range(subbenzi):
		w = biti[sb]
		masca = (1 << w) - 1
		if sb < limita:
			poz += w
			aloc0[sb] = (n >> (L - poz)) & masca
			if canale == 2:
				poz += w
				aloc1[sb] = (n >> (L - poz)) & masca
		else:
			poz += w
			v = (n >> (L - poz)) & masca
			aloc0[sb] = v
			aloc1[sb] = v
	if poz > L_real:
		return None
	scf0 = [0] * subbenzi
	scf1 = [0] * subbenzi
	for sb in range(subbenzi):
		if aloc0[sb]:
			poz += 2
			scf0[sb] = (n >> (L - poz)) & 3
		if canale == 2 and aloc1[sb]:
			poz += 2
			scf1[sb] = (n >> (L - poz)) & 3
	if poz > L_real:
		return None
	f0 = [FACTOR_GOL] * 32
	f1 = [FACTOR_GOL] * 32 if canale == 2 else None
	for sb in range(subbenzi):
		for ch in range(canale):
			if ch == 0:
				if not aloc0[sb]:
					continue
				s = scf0[sb]
			else:
				if not aloc1[sb]:
					continue
				s = scf1[sb]
			cate = 3 if s == 0 else (1 if s == 2 else 2)
			minim = 63
			for _k in range(cate):
				poz += 6
				if poz > L:
					return None
				val = (n >> (L - poz)) & 63
				if val < minim:
					minim = val
			if ch == 0:
				f0[sb] = minim
			else:
				f1[sb] = minim
	if poz > L_real:
		return None
	return (subbenzi, f0, f1)


def _banda_sus(factori):
	"""Cea mai inalta subbanda cu date dintr-un cadru (subbenzi, f0, f1), sau -1 cand cadrul e gol (liniste)."""
	subbenzi, f0, f1 = factori
	for sb in range(min(subbenzi, 32) - 1, -1, -1):
		if f0[sb] < FACTOR_GOL or (f1 is not None and f1[sb] < FACTOR_GOL):
			return sb
	return -1


def db_din_factor(indice):
	"""Nivelul in dB (0 dB = plin) al unui indice de factor de scala: 2 * 2^(-i/3), deci 2,0 dB pe treapta."""
	if indice >= FACTOR_GOL:
		return -120.0
	return 6.02 - 2.0069 * indice


# ---------------------------------------------------------------- MPEG audio Layer I

DEBITE_MPEG1_L1 = (0, 32, 64, 96, 128, 160, 192, 224, 256, 288, 320, 352, 384, 416, 448)
DEBITE_LSF_L1 = (0, 32, 48, 56, 64, 80, 96, 112, 128, 144, 160, 176, 192, 224, 256)


def antet_mp1(b, i):
	"""Antetul cadrului MPEG-1/2 Layer I: (lungime, kbps, frecventa, mod, extensie_mod, crc, lsf) sau None."""
	if i + 4 > len(b) or b[i] != 0xFF or (b[i + 1] & 0xE0) != 0xE0:
		return None
	v = (b[i + 1] >> 3) & 3
	if (b[i + 1] >> 1) & 3 != 3 or v not in (2, 3):
		return None
	idx_debit = b[i + 2] >> 4
	idx_frecv = (b[i + 2] >> 2) & 3
	if idx_debit in (0, 15) or idx_frecv == 3:
		return None
	lsf = v == 2
	kbps = (DEBITE_LSF_L1 if lsf else DEBITE_MPEG1_L1)[idx_debit]
	frecv = FRECVENTE[v][idx_frecv]
	lungime = (12000 * kbps // frecv + ((b[i + 2] >> 1) & 1)) * 4
	return (lungime, kbps, frecv, b[i + 3] >> 6, (b[i + 3] >> 4) & 3, not (b[i + 1] & 1), lsf)


def factori_mp1(b, i, antet):
	"""Factorii de scala ai unui cadru Layer I (unul pe subbanda si canal): (32, f0, f1) ca factori_mp2, sau None."""
	lungime, kbps, frecv, mod, ext, crc, lsf = antet
	canale = 1 if mod == 3 else 2
	limita = (4 + ext * 4) if mod == 1 else 32
	start = i + 4 + (2 if crc else 0)
	bucata = bytes(b[start:min(i + lungime, start + 80)])
	L_real = len(bucata) * 8
	n = int.from_bytes(bucata + bytes(80 - len(bucata)), "big")
	L = 640
	poz = 0
	aloc = [[0] * 32, [0] * 32]
	for sb in range(32):
		for ch in range(canale if sb < limita else 1):
			poz += 4
			v = (n >> (L - poz)) & 15
			if v == 15:
				return None
			aloc[ch][sb] = v
		if sb >= limita and canale == 2:
			aloc[1][sb] = aloc[0][sb]
	f = [[FACTOR_GOL] * 32, [FACTOR_GOL] * 32]
	for sb in range(32):
		for ch in range(canale):
			if aloc[ch][sb]:
				poz += 6
				f[ch][sb] = (n >> (L - poz)) & 63
	if poz > L_real:
		return None
	return (32, f[0], f[1] if canale == 2 else None)


# ---------------------------------------------------------------- AC-3, E-AC-3, DTS, PCM 302M: antetele

# marimea cadrului AC-3 in cuvinte de 16 biti, pe frmsizecod // 2 si frecventa (48; 44,1; 32 kHz) (A/52, tabelul 5.18)
_AC3_CUVINTE = ((64, 69, 96), (80, 87, 120), (96, 104, 144), (112, 121, 168), (128, 139, 192), (160, 174, 240),
	(192, 208, 288), (224, 243, 336), (256, 278, 384), (320, 348, 480), (384, 417, 576), (448, 487, 672),
	(512, 557, 768), (640, 696, 960), (768, 835, 1152), (896, 975, 1344), (1024, 1114, 1536), (1152, 1253, 1728),
	(1280, 1393, 1920))
_AC3_DEBITE = (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 384, 448, 512, 576, 640)
_AC3_FRECVENTE = (48000, 44100, 32000)
_AC3_CANALE = (2, 1, 2, 3, 3, 4, 4, 5)


def antet_ac3(b, i):
	"""(lungime, kbps, frecventa, canale, lfe, bsid, acmod) pentru un cadru AC-3 (bsid <= 10), sau None. acmod 0 = doua
	canale independente (1+1), nu stereo."""
	if i + 8 > len(b) or b[i] != 0x0B or b[i + 1] != 0x77:
		return None
	fscod = b[i + 4] >> 6
	cod = b[i + 4] & 0x3F
	bsid = b[i + 5] >> 3
	if fscod == 3 or cod >= 38 or bsid > 10:
		return None
	lungime = _AC3_CUVINTE[cod >> 1][fscod] * 2
	if fscod == 1:
		lungime += 2 * (cod & 1)
	acmod = b[i + 6] >> 5
	# lfeon vine dupa campurile de amestec, a caror prezenta depinde de acmod
	poz = 3 + (2 if (acmod & 1) and acmod != 1 else 0) + (2 if acmod & 4 else 0) + (2 if acmod == 2 else 0)
	lfe = (b[i + 6] >> (7 - poz)) & 1 if poz < 8 else (b[i + 7] >> (15 - poz)) & 1
	frecv = _AC3_FRECVENTE[fscod] >> (bsid - 8 if bsid > 8 else 0)
	return (lungime, _AC3_DEBITE[cod >> 1] >> (bsid - 8 if bsid > 8 else 0), frecv, _AC3_CANALE[acmod], lfe, bsid,
		acmod)


_EAC3_BLOCURI = (1, 2, 3, 6)


def antet_eac3(b, i):
	"""(lungime, kbps, frecventa, canale, lfe, bsid, independent, blocuri, acmod) pentru un cadru E-AC-3 (bsid 11-16),
	sau None. independent: programul 0 (al carui sunet da barele); cadrele dependente si ale altor programe se sar."""
	if i + 6 > len(b) or b[i] != 0x0B or b[i + 1] != 0x77:
		return None
	bsid = b[i + 5] >> 3
	if not 10 < bsid <= 16:
		return None
	strmtyp = b[i + 2] >> 6
	if strmtyp == 3:
		return None
	lungime = ((((b[i + 2] & 7) << 8) | b[i + 3]) + 1) * 2
	fscod = b[i + 4] >> 6
	if fscod == 3:
		fs2 = (b[i + 4] >> 4) & 3
		if fs2 == 3:
			return None
		frecv = (24000, 22050, 16000)[fs2]
		blocuri = 6
	else:
		frecv = _AC3_FRECVENTE[fscod]
		blocuri = _EAC3_BLOCURI[(b[i + 4] >> 4) & 3]
	acmod = (b[i + 4] >> 1) & 7
	lfe = b[i + 4] & 1
	kbps = int(lungime * 8 * frecv / (256.0 * blocuri) / 1000 + 0.5)
	independent = strmtyp != 1 and ((b[i + 2] >> 3) & 7) == 0
	return (lungime, kbps, frecv, _AC3_CANALE[acmod], lfe, bsid, independent, blocuri, acmod)


_DTS_FRECVENTE = (0, 8000, 16000, 32000, 0, 0, 11025, 22050, 44100, 0, 0, 12000, 24000, 48000, 0, 0)
_DTS_CANALE = (1, 2, 2, 2, 2, 3, 3, 4, 4, 5)
_DTS_DEBITE = (32, 56, 64, 96, 112, 128, 192, 224, 256, 320, 384, 448, 512, 576, 640, 768, 960, 1024, 1152, 1280,
	1344, 1408, 1411, 1472, 1536)


def antet_dts(b, i):
	"""(lungime, kbps, frecventa, canale, lfe, esantioane) pentru un cadru al nucleului DTS (big-endian, 16 biti), cu
	extensia DTS-HD de dupa el inclusa in lungime cand exista, sau None."""
	if i + 12 > len(b) or b[i:i + 4] != b"\x7f\xfe\x80\x01":
		return None
	if ((b[i + 4] >> 2) & 0x1F) != 31:          # esantioanele de la coada: mereu 32
		return None
	npcm = (((b[i + 4] & 1) << 6) | (b[i + 5] >> 2)) + 1
	lungime = (((b[i + 5] & 3) << 12) | (b[i + 6] << 4) | (b[i + 7] >> 4)) + 1
	amode = ((b[i + 7] & 0x0F) << 2) | (b[i + 8] >> 6)
	sr = (b[i + 8] >> 2) & 0x0F
	rate = ((b[i + 8] & 3) << 3) | (b[i + 9] >> 5)
	lfe = (b[i + 10] >> 1) & 3
	if lungime < 96 or npcm & 7 or amode > 9 or not _DTS_FRECVENTE[sr] or lfe == 3:
		return None
	j = i + lungime
	if j + 10 <= len(b) and b[j:j + 4] == b"\x64\x58\x20\x25":
		# DTS-HD: substream-ul de extensie (sincronizarea 0x64582025) sta dupa nucleu; se sare cu el
		mare = (b[j + 5] >> 5) & 1
		if mare:
			ext = ((((b[j + 6] & 0x01) << 19) | (b[j + 7] << 11) | (b[j + 8] << 3) | (b[j + 9] >> 5)) & 0xFFFFF) + 1
		else:
			ext = (((b[j + 6] & 0x1F) << 11) | (b[j + 7] << 3) | (b[j + 8] >> 5)) + 1
		lungime += ext
	kbps = _DTS_DEBITE[rate] if rate < len(_DTS_DEBITE) else 0
	return (lungime, kbps, _DTS_FRECVENTE[sr], _DTS_CANALE[amode], 1 if lfe else 0, npcm * 32)


def antet_s302m(b, i):
	"""(lungime, kbps, 48000, canale, biti) pentru un pachet PCM SMPTE 302M (antetul AES3 de 4 octeti), sau None."""
	if i + 4 > len(b):
		return None
	marime = (b[i] << 8) | b[i + 1]
	canale = ((b[i + 2] >> 6) & 3) * 2 + 2
	biti = ((b[i + 3] >> 4) & 3) * 4 + 16
	if biti > 24 or b[i + 3] & 0x0F or marime < 20:
		return None
	pereche = {16: 5, 20: 6, 24: 7}[biti] * (canale // 2)
	if marime % pereche:
		return None
	return (marime + 4, 48000 * canale * biti // 1000, 48000, canale, biti)


# ---------------------------------------------------------------- AAC: antetele ADTS si LATM/LOAS

FRECVENTE_AAC = (96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350)


def antet_adts(b, i):
	"""(lungime, frecventa, canale, profil) sau None."""
	if i + 7 > len(b) or b[i] != 0xFF or (b[i + 1] & 0xF6) != 0xF0:
		return None
	profil = (b[i + 2] >> 6) + 1          # tipul obiectului audio: 1 principal, 2 LC, 3 SSR
	idx = (b[i + 2] >> 2) & 15
	if idx >= len(FRECVENTE_AAC):
		return None
	canale = ((b[i + 2] & 1) << 2) | (b[i + 3] >> 6)
	lungime = ((b[i + 3] & 3) << 11) | (b[i + 4] << 3) | (b[i + 5] >> 5)
	if lungime < 7:
		return None
	return (lungime, FRECVENTE_AAC[idx], canale, profil)


class _Biti(object):
	"""Citire de biti pentru LATM (drum rar; nu trebuie sa fie rapid)."""

	def __init__(self, b, i, sfarsit):
		self.b = b
		self.poz = i * 8
		self.sfarsit = sfarsit * 8

	def ia(self, n):
		if self.poz + n > self.sfarsit:
			raise ValueError("LATM taiat")
		v = 0
		for _k in range(n):
			octet = self.b[self.poz >> 3]
			v = (v << 1) | ((octet >> (7 - (self.poz & 7))) & 1)
			self.poz += 1
		return v


def _asc(r):
	"""AudioSpecificConfig: (tip obiect, frecventa, canale)."""
	tip = r.ia(5)
	if tip == 31:
		tip = 32 + r.ia(6)
	idx = r.ia(4)
	frecv = r.ia(24) if idx == 15 else (FRECVENTE_AAC[idx] if idx < len(FRECVENTE_AAC) else 0)
	canale = r.ia(4)
	if tip in (5, 29):
		idx2 = r.ia(4)
		frecv = r.ia(24) if idx2 == 15 else (FRECVENTE_AAC[idx2] if idx2 < len(FRECVENTE_AAC) else frecv)
	return (tip, frecv, canale)


def _latm_valoare(r):
	cati = r.ia(2)
	v = 0
	for _k in range(cati + 1):
		v = (v << 8) | r.ia(8)
	return v


def antet_loas(b, i):
	"""(lungime, config) pentru un cadru LOAS (sincronizare 0x2B7); config = (tip obiect, frecventa, canale) cand cadrul
	poarta StreamMuxConfig, altfel None. None daca nu e cadru LOAS."""
	if i + 3 > len(b) or b[i] != 0x56 or (b[i + 1] & 0xE0) != 0xE0:
		return None
	lungime = 3 + (((b[i + 1] & 0x1F) << 8) | b[i + 2])
	if lungime < 4:
		return None
	config = None
	if i + lungime <= len(b):
		config = config_loas(b, i, lungime)[0]
	return (lungime, config)


def config_loas(b, i, lungime):
	"""(config, biti): configuratia AAC din StreamMuxConfig-ul cadrului LOAS de la i si cati biti de la inceputul
	incarcaturii o cuprind; (None, 0) fara configuratie in cadru sau cand nu se poate citi."""
	try:
		r = _Biti(b, i + 3, i + lungime)
		if r.ia(1):                             # useSameStreamMux = 1: fara StreamMuxConfig
			return (None, 0)
		versiune = r.ia(1)
		if versiune:
			if r.ia(1):                         # audioMuxVersionA: nu se foloseste in DVB
				return (None, 0)
			_latm_valoare(r)                    # taraBufferFullness
		r.ia(1)                                 # allStreamsSameTimeFraming
		r.ia(6)                                 # numSubFrames
		r.ia(4)                                 # numProgram
		r.ia(3)                                 # numLayer
		if versiune:
			_latm_valoare(r)                    # lungimea ASC
		config = _asc(r)
		return (config, r.poz - (i + 3) * 8)
	except (ValueError, IndexError):
		return (None, 0)


PROFILURI_AAC = {1: "AAC Main", 2: "AAC", 3: "AAC SSR", 4: "AAC LTP", 5: "HE-AAC", 29: "HE-AAC v2"}

# ---------------------------------------------------------------- din PES in fluxul elementar


class Pes(object):
	"""Reface pachetele PES din bucatile citite din demultiplexor si da mai departe partea de sunet (fluxul
	elementar)."""

	def __init__(self):
		self.tampon = bytearray()
		# pachete audio private (0xBD) la rand al caror inceput e un antet PCM 302M cu marimea pachetului
		self.s302m = 0

	def _nota_302m(self, sid, pachet, inceput):
		rest = len(pachet) - inceput
		if sid == 0xBD and rest >= 24:
			marime = (pachet[inceput] << 8) | pachet[inceput + 1]
			if marime + 4 == rest and not pachet[inceput + 3] & 0x0F:
				self.s302m += 1
				return
		self.s302m = 0

	def adauga(self, date):
		"""-> fluxul elementar (bytes) scos din pachetele PES complete de pana acum."""
		t = self.tampon
		t += date
		iesire = bytearray()
		while True:
			i = t.find(b"\x00\x00\x01")
			if i < 0:
				if len(t) > 2:
					del t[:len(t) - 2]
				break
			if i:
				del t[:i]
			if len(t) < 9:
				break
			sid = t[3]
			lung = (t[4] << 8) | t[5]
			audio = 0xC0 <= sid <= 0xDF or sid == 0xBD
			if lung == 0:
				# PES fara lungime (numai la video): pana la urmatorul inceput
				j = t.find(b"\x00\x00\x01", 6)
				if j < 0:
					if len(t) > PES_MAX:
						del t[:]
					break
				pachet = bytes(t[:j])
				del t[:j]
			else:
				if len(t) < 6 + lung:
					break
				pachet = bytes(t[:6 + lung])
				del t[:6 + lung]
			if not audio or len(pachet) < 9 or (pachet[6] & 0xC0) != 0x80:
				continue
			inceput = 9 + pachet[8]
			if inceput < len(pachet):
				self._nota_302m(sid, pachet, inceput)
				iesire += pachet[inceput:]
		return bytes(iesire)


# ---------------------------------------------------------------- nucleul pentru formatele fara factori de scala

# felul -> numarul lui la eHdsSpectru.cadru (lib/dvb/hdsspectru.h)
FEL_NUCLEU = {"adts": 1, "loas": 2, "ac3": 3, "eac3": 4, "dts": 5, "s302m": 6}
CADRE_PE_SECUNDA_MAX = 32.0      # cate cadre pe secunda primeste nucleul, cel mult (ecranul deseneaza 20 pe secunda)
INFO_NUCLEU_LA = 50              # dupa atatea cadre date nucleului se citesc din nou esantionarea si canalele lui
RELE_PANA_LA_FARA_BARE = 24      # cadre refuzate de nucleu la rand, fara niciunul bun: „fara-bare”

# Pentru probe: o functie care intoarce un obiect cu cadru(fel, bytes) si info(), ca eHdsSpectru. None: se cauta
# eHdsSpectru in enigma, o singura data.
FABRICA_SPECTRU = None
_spectru_cautat = [False, None]


def fabrica_spectru():
	"""Constructorul nucleului (eHdsSpectru), sau None cand imaginea nu il are (enigma2 vechi, PC)."""
	if FABRICA_SPECTRU is not None:
		return FABRICA_SPECTRU
	if not _spectru_cautat[0]:
		_spectru_cautat[0] = True
		try:
			from enigma import eHdsSpectru
			_spectru_cautat[1] = eHdsSpectru
		except Exception:
			_spectru_cautat[1] = None
	return _spectru_cautat[1]


def lungime_loas(b, i):
	"""Lungimea unui cadru LOAS (numai antetul de 3 octeti), sau 0."""
	if i + 3 > len(b) or b[i] != 0x56 or (b[i + 1] & 0xE0) != 0xE0:
		return 0
	lungime = 3 + (((b[i + 1] & 0x1F) << 8) | b[i + 2])
	return lungime if lungime >= 4 else 0


CODEC_TEXT = {"ac3": "AC-3", "eac3": "E-AC-3", "dts": "DTS", "s302m": "PCM"}

# ---------------------------------------------------------------- recunoasterea felului si citirea cadrelor


class Flux(object):
	"""Fluxul elementar: gaseste felul, citeste cadrele si tine ce afla. Fara fire; il hraneste Analizor."""

	def __init__(self, ceas=time.time):
		self.ceas = ceas
		self.es = bytearray()
		self.fel = None              # „mp2”, „mp1”, „adts”, „loas”, „ac3”, „eac3”, „dts”, „s302m” cand e sigur
		self.info = {}
		self.cadre = deque(maxlen=CADRE_TINUTE)   # (timp, subbenzi, f0, f1), din orice format
		self.octeti = deque()        # (timp, octeti) pentru debitul masurat
		self.numar_cadre = 0
		self.cadre_rele = 0
		self.octeti_primiti = 0
		# [secunda, [cate cadre au avut subbanda k ca cea mai inalta cu date, pentru k = 0..31]]
		self.benzi_sus = deque(maxlen=BANDA_FEREASTRA_S + 2)
		self._banda_gata = (None, -1)                          # (secunda, banda de sus) calculata ultima data
		self.lacat = threading.Lock()
		# nucleul (formatele fara factori de scala)
		self.nucleu = None
		self._nucleu_cautat = False
		self._pas = 1                # se da nucleului fiecare al `_pas`-lea cadru
		self._pana_la_nucleu = 0
		self._date_nucleului = 0
		self.nucleu_bune = 0
		self.nucleu_rele_la_rand = 0
		self._info_la = 0
		self._config_loas = None     # (bitii configuratiei LOAS, masca ultimului octet, configuratia citita din ei)
		# recunoasterea: pozitiile dinainte au fost cercetate la bucata de dinainte si nu incep niciun cadru, deci
		# cautarea continua de aici (pe un sunet necunoscut costul ramane pe octetii noi, nu pe tot tamponul); inceputurile
		# taiate de capatul datelor se incearca din nou cand vin octetii lor
		self._reluare = 0
		self._taiate = []
		# durata sunetului din cadrele citite (pentru debitul nominal al unui fisier de proba)
		self.durata_cadre = 0.0
		self.octeti_cadre = 0
		# pachete PES la rand care arata ca PCM 302M (Pes.s302m); 302M nu are sincronizare, deci numai atunci se
		# incearca
		self.pachete_302m = 0

	# ---- recunoasterea

	def _lungime(self, fel, b, i):
		if fel == "mp2":
			a = antet_mp2(b, i)
		elif fel == "mp1":
			a = antet_mp1(b, i)
		elif fel == "adts":
			a = antet_adts(b, i)
		elif fel == "loas":
			return lungime_loas(b, i)
		elif fel == "ac3":
			a = antet_ac3(b, i)
		elif fel == "eac3":
			a = antet_eac3(b, i)
		elif fel == "dts":
			a = antet_dts(b, i)
		else:
			a = antet_s302m(b, i)
		return a[0] if a else 0

	_FELURI = {0xFF: ("mp2", "mp1", "adts"), 0x56: ("loas",), 0x0B: ("ac3", "eac3"), 0x7F: ("dts",)}
	# cati octeti cere antetul fiecarui fel (antet_*): cu mai putini, cadrul nu e stricat, ci taiat de capatul datelor
	_ANTET_MIN = {"mp2": 4, "mp1": 4, "adts": 7, "loas": 3, "ac3": 8, "eac3": 6, "dts": 12, "s302m": 4}
	# primii doi octeti ai unui cadru posibil: 0xFF / 0x56 cu 111xxxxx dupa ei, 0x0B 0x77, 0x7F 0xFE (cautat in C, nu
	# octet cu octet in Python)
	_SINCRONIZARE = re.compile(b"[\xff\x56][\xe0-\xff]|\x0b\x77|\x7f\xfe")

	def _recunoaste(self):
		"""Cauta trei cadre la rand de acelasi fel; -> True daca felul e sigur (si fluxul incepe cu un cadru).
		PCM 302M nu are sincronizare: se incearca numai la inceputul unui pachet (inceputul fluxului adunat).
		Un inceput care pare bun dar e taiat de capatul datelor nu opreste cautarea: daca mai departe sunt trei cadre
		intregi, castiga ele; altfel se asteapta restul de la primul inceput taiat. Nimic nu se cerceteaza de doua ori:
		cautarea continua de unde a ramas la bucata de dinainte (self._reluare), iar inceputurile taiate de atunci
		(self._taiate) se incearca din nou cu octetii noi; ce e inaintea lor si a locului de reluare se lasa. Pe un sunet
		necunoscut costul pe bucata ramane pe octetii ei."""
		b = self.es
		n = len(b)
		taiate = []
		if self.pachete_302m:
			r = self._incearca("s302m", b, 0, n)
			if r:
				return True
			if r is False:
				taiate.append(0)
		for i in self._taiate:
			if taiate and i <= taiate[-1]:
				continue
			if i + 4 > n:
				taiate.append(i)
				continue
			taiat = False
			for fel in self._FELURI.get(b[i], ()):
				r = self._incearca(fel, b, i, n)
				if r:
					return True
				if r is False:
					taiat = True
			if taiat:
				taiate.append(i)
		i = min(self._reluare, n)
		cauta = self._SINCRONIZARE.search
		while i + 4 <= n:
			m = cauta(b, i)
			if m is None:
				i = max(i, n - 1)       # ultimul octet poate incepe un cadru cu octetii care vin
				break
			i = m.start()
			if i + 4 > n:
				break
			taiat = False
			for fel in self._FELURI.get(b[i], ()):
				r = self._incearca(fel, b, i, n)
				if r:
					return True
				if r is False:
					taiat = True
			if taiat:
				taiate.append(i)
			i += 1
		# se pastreaza numai de la primul inceput taiat (sau de la locul de reluare)
		k = min(taiate[0] if taiate else i, i, n)
		if k:
			del b[:k]
		self._taiate = [t - k for t in taiate]
		self._reluare = i - k
		return False

	def _incearca(self, fel, b, i, n):
		"""Trei cadre de felul `fel` de la i: felul se tine minte, fluxul incepe de la i si -> True; cadre bune pana la
		capatul datelor (poate, cu restul): False; altfel None. Un antet caruia ii lipsesc octeti la capatul datelor e
		„taiat” (False), nu stricat: se incearca din nou cu octetii care vin."""
		h = self._ANTET_MIN.get(fel, 4)
		if i + h > n:
			return False
		l1 = self._lungime(fel, b, i)
		if not l1:
			return None
		if i + l1 + h > n:
			return False
		l2 = self._lungime(fel, b, i + l1)
		if not l2:
			return None
		if i + l1 + l2 + h > n:
			return False
		l3 = self._lungime(fel, b, i + l1 + l2)
		if not l3:
			return None
		del b[:i]
		self.fel = fel
		self._pas = 1
		self._pana_la_nucleu = 0
		self._reluare = 0
		self._taiate = []
		return True

	# ---- cadrele

	def adauga(self, es):
		acum = self.ceas()
		if es:
			self.octeti_primiti += len(es)
			self.es += es
		# dupa o pierdere a sincronizarii se cauta din nou in ce a ramas (de cel mult cateva ori pe bucata)
		for _incercare in range(8):
			if self.fel is None and not self._recunoaste():
				return
			if not self._cadrele(acum):
				return

	def _cadrele(self, acum):
		"""Citeste cadrele intregi de la inceputul fluxului. -> True daca sincronizarea s-a pierdut pe drum."""
		b = self.es
		i = 0
		n = len(b)
		fel = self.fel
		while i + 4 <= n:
			if fel == "mp2" or fel == "mp1":
				a = antet_mp2(b, i) if fel == "mp2" else antet_mp1(b, i)
				if a is None:
					self._pierdut(i)
					return True
				if i + a[0] > n:
					break
				f = factori_mp2(b, i, a) if fel == "mp2" else factori_mp1(b, i, a)
				if f is None:
					self.cadre_rele += 1
				else:
					self._nota_nivele(acum, f)
				self._nota_mpeg(a, acum, fel)
				i += a[0]
			else:
				# antetul intreg inainte de citire: cateva octeti lipsa la capatul bucatii nu sunt o pierdere a
				# sincronizarii (AC-3 cere 8, DTS 12)
				if i + self._ANTET_MIN.get(fel, 4) > n:
					break
				lung = self._lungime(fel, b, i)
				if not lung:
					self._pierdut(i)
					return True
				if i + lung > n:
					break
				# DTS: extensia DTS-HD de dupa nucleu intra in lungime numai cand antetul ei e in tampon
				if fel == "dts" and i + lung + 10 > n:
					break
				self._cadru_nucleu(fel, b, i, lung, acum)
				i += lung
			self.numar_cadre += 1
		if i:
			del b[:i]
		if len(b) > ES_MAX:
			del b[:]
		return False

	def _pierdut(self, i):
		"""Sincronizarea s-a pierdut (octeti lipsa sau stricati): se cauta din nou felul de la pozitia i. La PCM 302M
		(fara sincronizare) se asteapta inceputul pachetului urmator."""
		if self.fel == "s302m":
			del self.es[:]
		else:
			del self.es[:i + 1]
		self.fel = None
		self._reluare = 0
		self._taiate = []
		self.cadre_rele += 1

	def _nota_nivele(self, acum, f):
		"""Nivelele unui cadru (subbenzi, f0, f1), din orice format."""
		with self.lacat:
			self.cadre.append((acum, f[0], f[1], f[2]))
		self.nota_banda(_banda_sus(f), acum)

	def _nota_debit(self, octeti, acum):
		self.octeti.append((acum, octeti))
		while self.octeti and acum - self.octeti[0][0] > DEBIT_FEREASTRA_S:
			self.octeti.popleft()

	def debit_masurat(self):
		"""kbit/s din octetii cadrelor din ultimele 2 secunde, sau 0."""
		copie = list(self.octeti)     # firul analizorului o schimba; list() o copiaza dintr-o bucata
		if len(copie) < 2:
			return 0
		t0 = copie[0][0]
		t1 = copie[-1][0]
		if t1 - t0 < 0.25:
			return 0
		total = sum(o for _t, o in copie[1:])
		return int(round(total * 8 / (t1 - t0) / 1000.0))

	def _nota_durata(self, octeti, esantioane, frecv):
		if frecv:
			self.durata_cadre += float(esantioane) / frecv
			self.octeti_cadre += octeti

	def _nota_mpeg(self, a, acum, fel):
		lungime, kbps, frecv, mod, ext, crc, lsf = a
		strat = "Layer II" if fel == "mp2" else "Layer I"
		self.info = {
			"format": fel, "codec": ("MPEG-2 " if lsf else "MPEG-1 ") + strat, "debit": kbps,
			"esantionare": frecv, "mod": MODURI[mod], "canale": 1 if mod == 3 else 2, "crc": crc, "bare": True,
		}
		self._nota_debit(lungime, acum)
		self._nota_durata(lungime, (1152 if not lsf else 576) if fel == "mp2" else 384, frecv)

	def _nota_aac(self, lungime, config, acum):
		info = dict(self.info) if self.info.get("format") == "aac" else {"format": "aac", "codec": "AAC", "bare": False}
		if config:
			tip, frecv, canale = config
			if not info.get("sbr"):
				info["codec"] = PROFILURI_AAC.get(tip, "AAC")
			if frecv and not info.get("din_nucleu"):
				info["esantionare"] = frecv
			if tip == 29:
				info["canale"] = 2              # stereo parametric: un canal in flux, doua la iesire
			elif canale and not info.get("din_nucleu"):
				info["canale"] = canale
		self._nota_debit(lungime, acum)
		info["debit"] = self.debit_masurat()
		info["debit_masurat"] = True
		self.info = info
		frecv = info.get("esantionare") or 48000
		self._nota_durata(lungime, 1024, frecv / 2 if self._he_aac() else frecv)

	def _he_aac(self):
		return bool(self.info.get("sbr")) or str(self.info.get("codec", "")).startswith("HE-AAC")

	# ---- formatele date nucleului

	def _config_aac(self, fel, b, i, lung):
		"""Configuratia AAC (tip, frecventa, canale) din antetul cadrului: ADTS direct; LOAS numai cand cadrul poarta
		StreamMuxConfig. Encoderele o repeta in fiecare cadru: se citeste bit cu bit o data, apoi se recunoaste dupa
		aceiasi biti de la inceputul cadrului (fara citirea lor)."""
		if fel == "adts":
			a = antet_adts(b, i)
			return (a[3], a[1], a[2]) if a else None
		if i + 4 > len(b) or b[i + 3] & 0x80:           # useSameStreamMux: nimic nou in cadru
			return None
		tinut = self._config_loas
		if tinut:
			octeti, masca, config = tinut
			k = len(octeti)
			bucata = bytearray(b[i + 3:i + 3 + k])
			if len(bucata) == k:
				bucata[-1] &= masca
				if bytes(bucata) == octeti:
					return config
		config, biti = config_loas(b, i, lung)
		if config and biti:
			k = (biti + 7) // 8
			masca = (0xFF << (k * 8 - biti)) & 0xFF
			bucata = bytearray(b[i + 3:i + 3 + k])
			bucata[-1] &= masca
			self._config_loas = (bytes(bucata), masca, config)
		return config

	def _cadru_nucleu(self, fel, b, i, lung, acum):
		"""Un cadru AAC / AC-3 / E-AC-3 / DTS / PCM: informatiile din antet si, la fiecare al `_pas`-lea, nivelele din
		nucleu."""
		sare = False
		if fel in ("adts", "loas"):
			config = self._config_aac(fel, b, i, lung)
			self._nota_aac(lung, config, acum)
			# cadrele AAC au 1024 de esantioane ale nucleului; cu SBR esantionarea auzita e dublul lui
			cps = (self.info.get("esantionare") or 48000) / 1024.0
			if self._he_aac():
				cps /= 2.0
		else:
			if fel == "ac3":
				a = antet_ac3(b, i)
				lungime, kbps, frecv, canale, lfe = a[:5]
				esantioane = 1536
			elif fel == "eac3":
				a = antet_eac3(b, i)
				lungime, kbps, frecv, canale, lfe = a[:5]
				esantioane = 256 * a[7]
				sare = not a[6]
			elif fel == "dts":
				a = antet_dts(b, i)
				lungime, kbps, frecv, canale, lfe = a[:5]
				esantioane = a[5]
			else:
				a = antet_s302m(b, i)
				lungime, kbps, frecv, canale = a[:4]
				lfe = 0
				esantioane = (a[0] - 4) // ({16: 5, 20: 6, 24: 7}[a[4]] * (canale // 2))
			cps = float(frecv) / esantioane
			if not sare:
				info = dict(self.info) if self.info.get("format") == fel else {"format": fel, "bare": False}
				info.update({"codec": CODEC_TEXT[fel], "esantionare": frecv, "canale": canale, "lfe": bool(lfe)})
				# AC-3 / E-AC-3 cu acmod 0: doua canale mono independente (1+1), scrise „două canale”, ca la MP2 dual
				if fel in ("ac3", "eac3") and a[-1] == 0:
					info["mod"] = "dual"
				else:
					info.pop("mod", None)
				if fel == "s302m":
					info["biti"] = a[4]
				if kbps:
					info["debit"] = kbps
				self.info = info
			self._nota_debit(lungime, acum)
			if not sare:
				self._nota_durata(lungime, esantioane, frecv)
		if sare:
			return
		# plafonul e adevarat (rotunjire in sus): AAC 47 -> fiecare al doilea, AC-3 31 -> fiecare, DTS 94 -> al treilea
		self._pas = max(1, int(math.ceil(cps / CADRE_PE_SECUNDA_MAX - 1e-9)))
		self._pana_la_nucleu -= 1
		if self._pana_la_nucleu > 0:
			return
		self._pana_la_nucleu = self._pas
		nucleu = self._nucleu()
		if nucleu is None:
			return
		try:
			rez = nucleu.cadru(FEL_NUCLEU[fel], bytes(b[i:i + lung]))
		except Exception:
			rez = None
		self._date_nucleului += 1
		if rez:
			f0, f1 = rez
			self.nucleu_bune += 1
			self.nucleu_rele_la_rand = 0
			self._nota_nivele(acum, (32, list(f0), list(f1) if f1 is not None else None))
			self.info["bare"] = True
		else:
			self.nucleu_rele_la_rand += 1
			self.cadre_rele += 1
			if self.nucleu_rele_la_rand >= RELE_PANA_LA_FARA_BARE:
				self.info["bare"] = False
		if self._date_nucleului >= self._info_la:
			self._info_la = self._date_nucleului + INFO_NUCLEU_LA
			self._info_din_nucleu(fel, nucleu)

	def _nucleu(self):
		if not self._nucleu_cautat:
			self._nucleu_cautat = True
			fabrica = fabrica_spectru()
			try:
				self.nucleu = fabrica() if fabrica is not None else None
			except Exception:
				self.nucleu = None
		return self.nucleu

	def _info_din_nucleu(self, fel, nucleu):
		"""La AAC nucleul stie ce nu se vede in antet: SBR (HE-AAC), stereo parametric, esantionarea auzita."""
		try:
			d = nucleu.info()
		except Exception:
			return
		if not d or fel not in ("adts", "loas") or not d.get("bune"):
			return
		info = dict(self.info)
		info["din_nucleu"] = True
		if d.get("esantionare"):
			info["esantionare"] = d["esantionare"]
		if d.get("ps"):
			info["codec"] = "HE-AAC v2"
			info["sbr"] = True
			info["canale"] = 2
		elif d.get("sbr"):
			info["codec"] = "HE-AAC"
			info["sbr"] = True
		if d.get("canale") and not d.get("ps"):
			info["canale"] = d["canale"]
		if d.get("lfe"):
			info["lfe"] = True
		self.info = info

	def are_nucleu(self):
		"""False cand un format care cere nucleul nu il are (imagine veche); True in rest."""
		if self.fel not in FEL_NUCLEU:
			return True
		return self._nucleu() is not None

	def debit_nominal(self):
		"""Octeti pe secunda din lungimea si durata cadrelor citite (pentru fisierele de proba), sau 0."""
		if self.durata_cadre <= 0:
			return 0
		return int(self.octeti_cadre / self.durata_cadre)

	# ---- ce citesc ecranul si web-ul

	def nota_banda(self, sus, acum):
		"""Cea mai inalta subbanda cu date a unui cadru (-1: cadru gol), numarata pe secunda."""
		if sus < 0:
			return
		secunda = int(acum)
		with self.lacat:
			if not self.benzi_sus or self.benzi_sus[-1][0] != secunda:
				self.benzi_sus.append([secunda, [0] * 32])
			self.benzi_sus[-1][1][min(sus, 31)] += 1

	def banda_sus(self, acum=None):
		"""Cea mai inalta subbanda cu date in cel putin BANDA_PRAG din cadrele din ultimele BANDA_FEREASTRA_S secunde,
		sau -1 daca nu se stie. Se calculeaza cel mult o data pe secunda (ecranul o cere la fiecare cadru)."""
		if acum is None:
			acum = self.ceas()
		secunda = int(acum)
		if self._banda_gata[0] == secunda:
			return self._banda_gata[1]
		total = [0] * 32
		with self.lacat:
			for s, numere in self.benzi_sus:
				if acum - s <= BANDA_FEREASTRA_S:
					for k in range(32):
						total[k] += numere[k]
		n = sum(total)
		sus = -1
		if n:
			prag = BANDA_PRAG * n
			strans = 0
			for k in range(31, -1, -1):
				strans += total[k]
				if strans >= prag:
					sus = k
					break
		self._banda_gata = (secunda, sus)
		return sus

	def nivele(self, fereastra, acum=None):
		"""(subbenzi, f0, f1) cu cel mai mic indice (varful) din cadrele din ultimele `fereastra` secunde; daca in
		fereastra n-a venit niciun cadru, cel mai nou cadru. None fara cadre. `subbenzi` se opreste la banda de sus
		a postului (banda_sus), ca barele sa se intinda numai pe frecventele pe care postul le transmite."""
		if acum is None:
			acum = self.ceas()
		with self.lacat:
			cadre = list(self.cadre)
		if not cadre:
			return None
		alese = [c for c in cadre if acum - c[0] <= fereastra] or cadre[-1:]
		subbenzi = alese[-1][1]
		sus = self.banda_sus(acum)
		if sus >= 0:
			subbenzi = min(subbenzi, max(BANDA_MINIMA, sus + 1))
		f0 = list(alese[0][2])
		f1 = list(alese[0][3]) if alese[0][3] is not None else None
		for c in alese[1:]:
			for sb in range(32):
				if c[2][sb] < f0[sb]:
					f0[sb] = c[2][sb]
				if f1 is not None and c[3] is not None and c[3][sb] < f1[sb]:
					f1[sb] = c[3][sb]
		return (subbenzi, f0, f1)

	def varsta_ultimului_cadru(self, acum=None):
		if acum is None:
			acum = self.ceas()
		with self.lacat:
			if not self.cadre:
				return None
			return acum - self.cadre[-1][0]


# ---------------------------------------------------------------- sursele de date


class SursaDemux(object):
	"""Filtrul PES pe PID-ul audio, pe unul din demultiplexoarele date (in ordine)."""

	def __init__(self, pid, cai, os_mod=os, fcntl_mod=None, select_mod=None):
		self.pid = pid
		self.cai = list(cai)
		self.os = os_mod
		self.fcntl = fcntl_mod
		self.select = select_mod
		self.fd = -1
		self.cale = None
		self.poll = None

	def _module(self):
		if self.fcntl is None:
			import fcntl
			self.fcntl = fcntl
		if self.select is None:
			import select
			self.select = select

	def deschide(self, cale):
		"""-> None daca filtrul merge, altfel motivul (text tehnic scurt, pentru jurnal)."""
		self._module()
		self.inchide()
		try:
			fd = self.os.open(cale, self.os.O_RDWR | getattr(self.os, "O_NONBLOCK", 0))
		except OSError as e:
			return "%s: %s" % (cale, e.strerror or e)
		try:
			try:
				self.fcntl.ioctl(fd, DMX_SET_BUFFER_SIZE, MARIME_TAMPON)
			except (OSError, IOError):
				pass            # ca in nucleu: tamponul implicit ramane, filtrul merge si asa
			self.fcntl.ioctl(fd, DMX_SET_PES_FILTER,
				PES_FILTRU.pack(self.pid, DMX_IN_FRONTEND, DMX_OUT_TAP, DMX_PES_OTHER, DMX_IMMEDIATE_START))
		except (OSError, IOError) as e:
			try:
				self.os.close(fd)
			except OSError:
				pass
			return "%s: filtrul refuzat (%s)" % (cale, getattr(e, "strerror", None) or e)
		self.fd = fd
		self.cale = cale
		self.poll = self.select.poll()
		self.poll.register(fd, self.select.POLLIN | getattr(self.select, "POLLPRI", 0))
		return None

	def citeste(self, ms):
		"""-> octetii sositi (poate b"") in cel mult `ms` milisecunde."""
		if self.fd < 0:
			return b""
		gata = self.poll.poll(ms)
		if not gata:
			return b""
		try:
			return self.os.read(self.fd, CITIRE_MAX)
		except (OSError, IOError) as e:
			if getattr(e, "errno", None) in (11, 4, 75):   # EAGAIN, EINTR, EOVERFLOW (tampon depasit: se continua)
				return b""
			raise

	def inchide(self):
		if self.fd >= 0:
			try:
				self.fcntl.ioctl(self.fd, DMX_STOP)
			except (OSError, IOError):
				pass
			try:
				self.os.close(self.fd)
			except OSError:
				pass
		self.fd = -1
		self.poll = None


# ---------------------------------------------------------------- fluxul releului local (DAB+ / DVB-T2 din satelit)

CONECTARE_S = 2.0          # conectarea la releul local
ANTET_S = 8.0              # raspunsul releului: el asteapta pana la 6 s sa apara postul in ansamblu
ANTET_MAX = 4096
CITIRE_HTTP = 65536        # un program DVB-T2 vine in TS-ul intreg al PLP-ului (zeci de Mbit/s): bucati mari
RECONECTARI_MAX = 5        # releul inchide conexiunea cat postul merge (repornit, client lent): cereri noi, cel mult
RECONECTARE_PAUZA_S = 2.0  # ... atatea, la atata timp una de alta
RECONECTARI_UITATE_S = 30.0  # fluxul merge atat dupa o cerere noua: numaratoarea o ia de la capat (ascultari lungi)
TS_PACHET = 188
_SINCRON = b"\x47"


def adresa_releu(cale):
	"""Calea unei referinte (campul 11, cu %3a) -> (gazda, port, drum) daca e un flux al releului local DAB+ / DVB-T2
	(http://127.0.0.1:<port>/dab/... sau /t2/...), altfel None. Numai adrese locale: barele nu cer nimic din retea."""
	try:
		text = cale.decode("utf-8", "replace") if isinstance(cale, bytes) else ("%s" % cale)
	except Exception:
		return None
	text = text.replace("%3a", ":").replace("%3A", ":")
	if not text.lower().startswith("http://"):
		return None
	rest = text[7:]
	gazda_port, _, drum = rest.partition("/")
	gazda, _, port = gazda_port.rpartition(":")
	if not gazda:
		gazda, port = gazda_port, "80"
	if gazda not in ("127.0.0.1", "localhost") or not port.isdigit() or not 0 < int(port) < 65536:
		return None
	bucati = [b for b in drum.split("/") if b]
	if not bucati or bucati[0].lower() not in ("dab", "t2", "t2mi"):
		return None
	return gazda, int(port), "/" + "/".join(bucati)


class FiltruTs(object):
	"""Pachetele TS ale unui PID (sau ale primului PID cu sunet, cand pid e None), din bucati oarecare de flux (fara
	granite de pachet), lipite ca din DMX_OUT_TAP: sarcina fiecarui pachet, de la PES-ul intai.

	Cautarea e in C, nu pachet cu pachet in Python: octetii 1 si 2 ai tuturor pachetelor aliniate se iau prin feliere
	cu pas 188, iar in octetul 2 se cauta (bytes.find) numai locurile cu octetul de jos al PID-ului. In Python intra
	doar pachetele gasite (pista audio: cateva sute pe secunda), si la DVB-T2, unde TS-ul PLP-ului are zeci de Mbit/s.
	Sincronizarea (0x47 la fiecare 188 de octeti) se verifica la fiecare bucata, tot prin feliere; pierduta, se cauta
	din nou."""

	def __init__(self, pid=None):
		self.pid = pid if pid is not None and 0 <= pid < 0x1FFF else None
		self._rest = b""
		self.pachete = 0           # pachete ale PID-ului date mai departe
		self.resincronizari = 0
		self.octeti = 0

	def _sincron(self, date, inceput):
		"""Primul loc >= inceput de unde 0x47 se repeta la 188 de octeti de trei ori (sau pana la capat), sau -1."""
		i = date.find(_SINCRON, inceput)
		while i >= 0:
			bun = True
			for k in (1, 2):
				j = i + k * TS_PACHET
				if j < len(date) and date[j:j + 1] != _SINCRON:
					bun = False
					break
			if bun and i + TS_PACHET <= len(date):
				return i
			if bun:
				return -1          # prea putine date dupa el: se asteapta bucata urmatoare
			i = date.find(_SINCRON, i + 1)
		return -1

	def _aliniate(self, date):
		"""-> (inceputul primului pachet aliniat, numarul pachetelor intregi), cu sincronizarea verificata."""
		i = 0
		while True:
			if date[i:i + 1] != _SINCRON:
				i = self._sincron(date, i)
				if i < 0:
					return -1, 0
				self.resincronizari += 1
			n = (len(date) - i) // TS_PACHET
			if n <= 0:
				return i, 0
			sinc = date[i:i + n * TS_PACHET:TS_PACHET]
			if sinc == _SINCRON * n:
				return i, n
			# primul pachet fara 0x47: pana la el totul e bun, de acolo se cauta din nou
			rau = next(k for k in range(n) if sinc[k:k + 1] != _SINCRON)
			if rau:
				return i, rau
			i = self._sincron(date, i + 1)
			if i < 0:
				return -1, 0
			self.resincronizari += 1

	def _alege_pid(self, date, i, n):
		"""Fara PID dat: primul pachet cu inceput de PES audio (MPEG 0xC0-0xDF sau privat cu sunet)."""
		for k in range(n):
			p = date[i + k * TS_PACHET:i + (k + 1) * TS_PACHET]
			if not p[1] & 0x40:
				continue
			o = 4
			afc = (p[3] >> 4) & 3
			if afc & 2:
				o += 1 + p[4]
			if not afc & 1 or o + 4 > TS_PACHET or p[o:o + 3] != b"\x00\x00\x01":
				continue
			if 0xC0 <= p[o + 3] <= 0xDF or _sunet_privat(p, o):
				return ((p[1] & 0x1F) << 8) | p[2]
		return None

	def adauga(self, bucata):
		"""Bucata de flux -> octetii pachetelor PID-ului (poate b"")."""
		if not bucata:
			return b""
		self.octeti += len(bucata)
		date = self._rest + bucata if self._rest else bytes(bucata)
		self._rest = b""
		iesire = bytearray()
		i = 0
		while i < len(date):
			i, n = self._aliniate_de_la(date, i)
			if i < 0:
				self._rest = date[-(2 * TS_PACHET):] if len(date) > 2 * TS_PACHET else date
				break
			if n == 0:
				self._rest = date[i:]
				break
			if self.pid is None:
				self.pid = self._alege_pid(date, i, n)
			if self.pid is not None:
				self._scoate(date, i, n, iesire)
			i += n * TS_PACHET
		return bytes(iesire)

	def _aliniate_de_la(self, date, i):
		if i == 0:
			return self._aliniate(date)
		j, n = self._aliniate(date[i:])
		return (j + i if j >= 0 else -1), n

	def _scoate(self, date, i, n, iesire):
		sus, jos = self.pid >> 8, self.pid & 0xFF
		sfarsit = i + n * TS_PACHET
		octet1 = date[i + 1:sfarsit:TS_PACHET]
		octet2 = date[i + 2:sfarsit:TS_PACHET]
		cauta = bytes(bytearray([jos]))
		k = octet2.find(cauta)
		while k >= 0:
			b1 = octet1[k]
			# TEI (pachet stricat) se sare; PID-ul intreg trebuie sa se potriveasca
			if not b1 & 0x80 and b1 & 0x1F == sus:
				p = date[i + k * TS_PACHET:i + (k + 1) * TS_PACHET]
				afc = (p[3] >> 4) & 3
				o = 4
				if afc & 2:
					o += 1 + p[4]
				if afc & 1 and o < TS_PACHET:
					iesire += p[o:]
					self.pachete += 1
			k = octet2.find(cauta, k + 1)


class _AsteptareSelect(object):
	"""poll(ms) pe un singur soclu cu select.select, unde modulul select nu are poll."""

	def __init__(self, select_mod, sock):
		self.select = select_mod
		self.sock = sock

	def poll(self, ms):
		r, _w, _x = self.select.select([self.sock], [], [], max(0, ms) / 1000.0)
		return r


class SursaHttp(object):
	"""Fluxul postului cerut a doua oara de la releul local DAB+ / DVB-T2 (aceeasi cale ca playerul), pentru barele
	unui post care nu vine din demultiplexorul tunerului: la tipul 1 cu sursa http (eHdsFluxHttp) sunetul trece prin
	demultiplexorul redarii, unde un filtru DMX_IN_FRONTEND nu primeste nimic.

	Releul da fiecarui client aceleasi bucati (un singur decodor DAB+ / un singur TS pe post, coada fixa pe client, cel
	care nu citeste destul e deconectat singur), deci al doilea client nu atinge redarea si nu acordeaza nimic: tunerul
	il tine controlorul (EDI) sau sesiunea 8001 a releului. Conexiunea se inchide la oprirea analizorului (cel mult
	POLL_MS); fara clienti releul isi opreste sursa singur, iar la plecarea de pe post controlorul il opreste oricum.

	Raspunsul: TS (video/MP2T sau octetul 0x47) -> pachetele PID-ului audio (FiltruTs); sunet fara TS (LOAS / MP2 pe
	4097, audio/aac sau audio/mpeg) -> impachetat in PES ca din demultiplexor (pes_din_es)."""

	def __init__(self, cale_ref, pid=None, socket_mod=None, select_mod=None, ceas=time.time):
		self.adresa = adresa_releu(cale_ref)
		self.pid = pid if pid is not None and pid > 0 else None
		self.cai = [cale_ref]
		self.socket = socket_mod
		self.select = select_mod
		self.ceas = ceas
		self.sock = None
		self.poll = None
		self.fd = -1
		self.fel = None             # "ts" sau "es"
		self.filtru = None
		self._prima = b""
		self._oprire = None
		self.inchis_de_releu = False
		self._inchis_la = 0.0
		self._reconectat_la = 0.0
		self.reconectari = 0

	def leaga_oprirea(self, eveniment):
		"""Evenimentul de oprire al analizorului: asteptarea raspunsului se intrerupe la el."""
		self._oprire = eveniment

	def _module(self):
		if self.socket is None:
			import socket
			self.socket = socket
		if self.select is None:
			import select
			self.select = select

	def _oprit(self):
		return self._oprire is not None and self._oprire.is_set()

	def deschide(self, cale=None):
		"""-> None daca releul trimite fluxul, altfel motivul (text tehnic scurt, pentru jurnal)."""
		self._module()
		self.inchide()
		if self.adresa is None:
			return "%s: nu e o adresa a releului local" % (cale or "?")
		gazda, port, drum = self.adresa
		try:
			s = self.socket.create_connection((gazda, port), CONECTARE_S)
		except (OSError, IOError) as e:
			return "%s:%d%s: %s" % (gazda, port, drum, getattr(e, "strerror", None) or e)
		try:
			s.sendall(("GET %s HTTP/1.0\r\nHost: %s:%d\r\nUser-Agent: hdsatelit-bare\r\n\r\n" % (drum, gazda, port))
				.encode("ascii"))
			s.setblocking(False)
		except (OSError, IOError) as e:
			s.close()
			return "%s%s: %s" % (gazda, drum, getattr(e, "strerror", None) or e)
		self.sock = s
		self.fd = s.fileno()
		if hasattr(self.select, "poll"):
			self.poll = self.select.poll()
			self.poll.register(self.fd, self.select.POLLIN | getattr(self.select, "POLLPRI", 0))
		else:
			self.poll = _AsteptareSelect(self.select, s)     # PC fara poll (probele de pe Windows)
		motiv = self._antet(drum)
		if motiv:
			self.inchide()
		return motiv

	def _antet(self, drum):
		"""Citeste antetul raspunsului (cel mult ANTET_S, intrerupt de oprire). -> None sau motivul."""
		primit = b""
		termen = self.ceas() + ANTET_S
		while b"\r\n\r\n" not in primit:
			if self._oprit():
				return "oprit"
			if self.ceas() > termen:
				return "%s: releul nu a raspuns in %d s" % (drum, ANTET_S)
			if not self.poll.poll(200):
				continue
			try:
				b = self.sock.recv(ANTET_MAX)
			except (OSError, IOError) as e:
				if getattr(e, "errno", None) in (11, 4):
					continue
				return "%s: %s" % (drum, getattr(e, "strerror", None) or e)
			if not b:
				return "%s: releul a inchis fara raspuns" % drum
			primit += b
			if len(primit) > ANTET_MAX and b"\r\n\r\n" not in primit:
				return "%s: antet prea lung" % drum
		antet, _, corp = primit.partition(b"\r\n\r\n")
		randuri = antet.decode("latin-1", "replace").split("\r\n")
		parti = randuri[0].split(" ", 2)
		if len(parti) < 2 or not parti[0].startswith("HTTP/") or parti[1] != "200":
			return "%s: %s" % (drum, randuri[0][:80])
		tip = ""
		for r in randuri[1:]:
			nume, _, valoare = r.partition(":")
			if nume.strip().lower() == "content-type":
				tip = valoare.strip().lower()
		if "mp2t" in tip:
			self.fel = "ts"
		elif tip.startswith("audio/"):
			self.fel = "es"
		else:
			self.fel = None          # se afla din primii octeti
		self._prima = corp
		return None

	def _fel_din_date(self, date):
		if self.fel is None and len(date) >= 2 * TS_PACHET + 1:
			self.fel = "ts" if date[:1] == _SINCRON and date[TS_PACHET:TS_PACHET + 1] == _SINCRON else "es"
		return self.fel

	def _reconecteaza(self):
		"""Releul a inchis conexiunea cat postul merge inca (releul repornit de controlor, client lent aruncat): cel mult
		RECONECTARI_MAX cereri noi, la RECONECTARE_PAUZA_S una de alta. Un releu oprit de tot (plecarea de pe post) refuza
		conectarea pe loc, iar analizorul se opreste oricum odata cu postul. -> True daca fluxul vine din nou."""
		acum = self.ceas()
		if (not self.inchis_de_releu or self.reconectari >= RECONECTARI_MAX or self._oprit()
				or acum - self._inchis_la < RECONECTARE_PAUZA_S):
			return False
		self.reconectari += 1
		if self.filtru is not None and self.filtru.pid is not None:
			self.pid = self.filtru.pid           # PID-ul gasit in flux ramane
		self.filtru = None
		if self.deschide() is None:
			self.inchis_de_releu = False
			self._reconectat_la = self.ceas()
			return True
		self._inchis_la = self.ceas()
		return False

	def citeste(self, ms):
		"""-> pachetele PES ale sunetului sosite (poate b"") in cel mult `ms` milisecunde."""
		if self.sock is None and not self._reconecteaza():
			return b""
		date, self._prima = self._prima, b""
		if (not date or self.fel is None) and self.poll.poll(0 if date else ms):
			try:
				b = self.sock.recv(CITIRE_HTTP)
			except (OSError, IOError) as e:
				if getattr(e, "errno", None) not in (11, 4):
					raise
				b = None
			if b == b"":
				# releul a inchis (repornit, client lent aruncat, post oprit): analizorul spune „datele s-au oprit”,
				# iar citirile urmatoare cer fluxul din nou (_reconecteaza)
				self.inchis_de_releu = True
				self._inchis_la = self.ceas()
				self.inchide()
			elif b:
				date += b
				if self.reconectari and self.ceas() - self._reconectat_la >= RECONECTARI_UITATE_S:
					self.reconectari = 0         # fluxul merge de mult dupa ultima cerere noua: alte opriri au iar voie
		if not date:
			return b""
		fel = self._fel_din_date(date)
		if fel is None:
			self._prima = date        # prea putin ca sa se stie felul: se pastreaza pentru citirea urmatoare
			return b""
		if fel == "es":
			return pes_din_es(date)
		if self.filtru is None:
			self.filtru = FiltruTs(self.pid)
		return self.filtru.adauga(date)

	def inchide(self):
		if self.sock is not None:
			try:
				self.sock.close()
			except (OSError, IOError):
				pass
		self.sock = None
		self.poll = None
		self.fd = -1


def _sunet_privat(p, o):
	"""Un PES privat (0xBD) care incepe cu sunet: AC-3 / E-AC-3, DTS sau un antet PCM 302M a carui marime e chiar
	marimea pachetului (teletextul si subtitrarile nu trec de nicio proba)."""
	if len(p) < o + 13 or p[o + 3] != 0xBD:
		return False
	inceput = o + 9 + p[o + 8]
	date = p[inceput:inceput + 4]
	if len(date) < 4:
		return False
	if date[:2] == b"\x0b\x77" or date == b"\x7f\xfe\x80\x01":
		return True
	lung = (p[o + 4] << 8) | p[o + 5]
	return bool(lung) and ((date[0] << 8) | date[1]) + 4 == lung - 3 - p[o + 8] and not date[3] & 0x0F


def pes_din_ts(date, pid=None):
	"""Pachetele PES ale unui PID dintr-un flux de transport (188 de octeti pe pachet), lipite, ca din DMX_OUT_TAP.
	Fara pid: primul PID care poarta PES audio MPEG (stream id 0xC0-0xDF), altfel primul cu sunet privat (0xBD:
	AC-3, E-AC-3, DTS, PCM 302M). -> (pid, octeti)."""
	bucati = {}
	candidati = []               # (pid, e MPEG) in ordinea aparitiei
	for i in range(0, len(date) - 187, 188):
		p = date[i:i + 188]
		if p[0] != 0x47:
			continue
		pp = ((p[1] & 0x1F) << 8) | p[2]
		afc = (p[3] >> 4) & 3
		o = 4
		if afc & 2:
			o += 1 + p[4]
		if not afc & 1 or o >= 188:
			continue
		if pid is None and p[1] & 0x40 and p[o:o + 3] == b"\x00\x00\x01" and pp not in bucati:
			mpeg = 0xC0 <= p[o + 3] <= 0xDF
			if mpeg or _sunet_privat(p, o):
				candidati.append((pp, mpeg))
				bucati[pp] = bytearray()
		if pp == pid or (pid is None and pp in bucati):
			bucati.setdefault(pp, bytearray()).extend(p[o:])
	if pid is None and candidati:
		pid = ([c for c, mpeg in candidati if mpeg] or [candidati[0][0]])[0]
	return pid, bytes(bucati.get(pid, b""))


def pes_din_es(es, marime=2024):
	"""Un flux elementar (MP2, ADTS) impachetat in pachete PES audio (stream id 0xC0), ca din demultiplexor."""
	iesire = bytearray()
	for i in range(0, len(es), marime):
		bucata = es[i:i + marime]
		iesire += b"\x00\x00\x01\xc0" + struct.pack(">H", len(bucata) + 3) + b"\x80\x00\x00" + bucata
	return bytes(iesire)


class SursaFisier(object):
	"""Fluxul unui post din fisier (TS sau PES), dat in bucati la viteza sunetului, in bucla. Pentru probele din
	emulator si de pe PC, unde nu exista demultiplexor."""

	def __init__(self, cale, pid=None, octeti_pe_secunda=None, bucla=True, ceas=time.time, dormi=time.sleep):
		self.cale = cale
		self.pid = pid
		self.bucla = bucla
		self.ceas = ceas
		self.dormi = dormi
		self.date = b""
		self.poz = 0
		self.ops = octeti_pe_secunda
		self.fd = -1
		self.t_ultim = None

	def deschide(self, cale=None):
		try:
			with open(self.cale, "rb") as f:
				brut = f.read()
		except (OSError, IOError) as e:
			return "%s: %s" % (self.cale, e)
		if brut[:1] == b"\x47" and len(brut) >= 376 and brut[188:189] == b"\x47":
			self.pid, self.date = pes_din_ts(brut, self.pid)
		elif brut[:3] == b"\x00\x00\x01":
			self.date = brut
		else:
			self.date = pes_din_es(brut)      # fisier .mp2 / .aac: fluxul elementar, fara PES
		if not self.date:
			return "%s: nu are sunet" % self.cale
		if not self.ops:
			self.ops = self._debit_estimat()
		self.fd = 0
		self.poz = 0
		self.t_ultim = self.ceas()
		return None

	def _debit_estimat(self):
		"""Octetii pe secunda ai fisierului, din lungimea si durata primelor cadre (orice format), plus antetele PES."""
		pes = Pes()
		es = pes.adauga(self.date[:400000])
		fl = Flux(ceas=lambda: 0.0)
		fl.pachete_302m = pes.s302m
		fl._nucleu_cautat = True        # numai lungimile; nucleul nu trebuie aici
		fl.adauga(es)
		ops = fl.debit_nominal()
		if ops:
			return int(ops * 1.03)
		return 24000

	def citeste(self, ms):
		if self.fd < 0:
			return b""
		self.dormi(ms / 1000.0 / 5)
		acum = self.ceas()
		cati = int((acum - self.t_ultim) * self.ops)
		if cati <= 0:
			return b""
		self.t_ultim = acum
		cati = min(cati, CITIRE_MAX)
		bucata = self.date[self.poz:self.poz + cati]
		self.poz += len(bucata)
		if self.poz >= len(self.date):
			if self.bucla:
				self.poz = 0
			else:
				self.fd = -1
		return bucata

	def inchide(self):
		self.fd = -1


# ---------------------------------------------------------------- analizorul (firul)

STARE_OPRIT = "oprit"
STARE_ASTEAPTA = "asteapta"
STARE_BARE = "bare"                 # barele merg (orice format)
STARE_FARA_BARE = "fara-bare"       # format cunoscut, dar fara nivele (imagine fara nucleu, cadre refuzate)
STARE_ALTUL = "necunoscut"
STARE_FARA_DATE = "fara-date"
# numele vechi (ecranul, web-ul si probele de dinainte)
STARE_MP2 = STARE_BARE
STARE_AAC = STARE_FARA_BARE


def _jurnal(text):
	print("[HdsRadio] %s" % text)


class Analizor(object):
	"""Un fir care citeste sursa si hraneste Flux. start() si opreste() se cheama de pe firul enigma2 si nu asteapta."""

	def __init__(self, sursa, ceas=time.time, jurnal=_jurnal, fir=True):
		self.sursa = sursa
		self.ceas = ceas
		self.jurnal = jurnal
		self.flux = Flux(ceas)
		self.pes = Pes()
		self.stare = STARE_OPRIT
		self.motiv = ""
		self._opreste = threading.Event()
		self._fir = None
		self._cu_fir = fir
		self._inainte = None
		self.pornit_la = None
		leaga = getattr(sursa, "leaga_oprirea", None)
		if leaga is not None:
			leaga(self._opreste)     # sursa care asteapta un raspuns (releul) se opreste odata cu analizorul

	def porneste(self, inainte=None):
		"""Porneste firul. `inainte`: analizorul de dinainte (firul nou il asteapta sa se inchida, ca pe PID-ul audio sa
		nu fie doua filtre ale noastre deodata)."""
		self.stare = STARE_ASTEAPTA
		self.pornit_la = self.ceas()
		self._inainte = inainte
		if not self._cu_fir:
			return
		self._fir = threading.Thread(target=self._ruleaza, name="HdsRadioAnaliza")
		self._fir.daemon = True
		self._fir.start()

	def opreste(self):
		self._opreste.set()

	def oprit(self):
		return self._opreste.is_set()

	def viu(self):
		return self._fir is not None and self._fir.is_alive()

	def _ruleaza(self):
		try:
			if self._inainte is not None and self._inainte._fir is not None:
				self._inainte._fir.join(2.0)
			self._inainte = None
			if self._opreste.is_set():
				return
			self.bucla()
		except Exception as e:
			self._stare(STARE_FARA_DATE, "eroare: %s" % e)
		finally:
			try:
				self.sursa.inchide()
			except Exception:
				pass
			if self.stare in (STARE_ASTEAPTA,):
				self.stare = STARE_OPRIT

	def _stare(self, stare, motiv="", nota=""):
		"""`nota` (felul sunetului) intra numai in jurnal; `motiv` ajunge si in descriere()."""
		if stare != self.stare or motiv != self.motiv:
			self.stare = stare
			self.motiv = motiv
			text = motiv or nota
			self.jurnal("analizor: %s%s" % (stare, (" (%s)" % text) if text else ""))

	def bucla(self):
		"""Deschide pe rand caile sursei; fara date in FARA_DATE_S pe toate: starea „fara-date”, fara reincercari."""
		cai = getattr(self.sursa, "cai", None) or [None]
		motive = []
		for cale in cai:
			if self._opreste.is_set():
				return
			if self.stare == STARE_FARA_DATE:
				self._stare(STARE_ASTEAPTA)     # calea de dinainte n-a dat sunet; se incearca urmatoarea
			motiv = self.sursa.deschide(cale) if cale is not None else self.sursa.deschide()
			if motiv:
				motive.append(motiv)
				continue
			if self._citeste_pana_la_oprire():
				return
			if self.motiv and self.stare == STARE_FARA_DATE:
				motive.append("%s: %s" % (cale or "sursa", self.motiv))
			else:
				motive.append("%s: nicio dată în %d s" % (cale or "sursa", FARA_DATE_S))
			self.sursa.inchide()
		if not self._opreste.is_set():
			self._stare(STARE_FARA_DATE, "; ".join(motive))

	def _citeste_pana_la_oprire(self):
		"""-> True daca a venit sunet (si s-a citit pana la oprire), False daca in FARA_DATE_S n-a venit niciun octet
		de sunet. Octetii care nu sunt de sunet (PES video, alt serviciu cu acelasi PID) nu tin firul in asteptare:
		dupa FARA_DATE_S fara sunet starea e „fara-date” si calea se lasa. Cand poll() raspunde fara date (POLLERR,
		EAGAIN), o pauza scurta tine firul departe de procesor."""
		inceput = self.ceas()
		primit = False               # au venit octeti de sunet (flux elementar)
		bruti = False                # au venit octeti pe filtru
		ultim = inceput
		pauza = POLL_MS / 5000.0
		while not self._opreste.is_set():
			t0 = time.time()
			date = self.sursa.citeste(POLL_MS)
			acum = self.ceas()
			if date:
				bruti = True
				inainte = self.flux.octeti_primiti
				self.hraneste(date)
				if self.flux.octeti_primiti > inainte:
					primit = True
					ultim = acum
			elif time.time() - t0 < pauza:
				self._opreste.wait(pauza)
			if not primit and acum - inceput >= FARA_DATE_S:
				if bruti:
					self._stare(STARE_FARA_DATE, "vin date pe PID, dar nu sunet")
				return False
			if primit and acum - ultim >= FARA_DATE_S:
				self._stare(STARE_FARA_DATE, "datele s-au oprit")
				ultim = acum
		return True

	def hraneste(self, date):
		"""Bucatile citite -> PES -> flux elementar -> cadre; starea dupa ce s-a aflat."""
		es = self.pes.adauga(date)
		fl = self.flux
		fl.pachete_302m = self.pes.s302m
		if es:
			fl.adauga(es)
		fel = fl.fel
		if fel and fl.numar_cadre:
			info = fl.info
			if info.get("bare") and fl.cadre:
				self._stare(STARE_BARE, nota=info.get("codec", fel))
			elif fel in FEL_NUCLEU and (not fl.are_nucleu() or info.get("bare") is False and fl.nucleu_rele_la_rand
					>= RELE_PANA_LA_FARA_BARE):
				self._stare(STARE_FARA_BARE, nota=info.get("codec", fel))
		elif fel is None and not fl.numar_cadre and fl.octeti_primiti > (262144 if fl.pachete_302m else 32768):
			# pachetele PCM 302M au pana la ~20 KB, iar recunoasterea cere trei
			self._stare(STARE_ALTUL)

	# ---- pentru ecran si web (de pe firul enigma2)

	def nivele(self, fereastra=0.06):
		if self.stare != STARE_BARE:
			return None
		return self.flux.nivele(fereastra)

	def descriere(self):
		"""Starea si datele sunetului, ca dictionar simplu (pentru ecran si pentru web)."""
		d = dict(self.flux.info)
		d["stare"] = self.stare
		d["motiv"] = self.motiv
		if self.stare == STARE_BARE and d.get("format") in ("mp2", "mp1"):
			d["debit_masurat"] = self.flux.debit_masurat()
		d.pop("din_nucleu", None)
		return d
