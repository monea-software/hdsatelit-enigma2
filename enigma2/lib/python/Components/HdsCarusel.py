# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCarusel.py: cititorul caruselului de obiecte DSM-CC, prin care unele canale isi trimit aplicatia HbbTV numai in
# semnal (fara adresa pe internet). Din sectiunile DSM-CC ale serviciului (table_id 0x3B: DSI si DII, 0x3C: DDB, 0x3D:
# evenimentele de flux) reface modulele cu versiunile lor (decomprimate cu zlib cand DII-ul o cere), desface mesajele
# BIOP (poarta serviciului, dosarele, fisierele, fluxurile si evenimentele de flux) si scrie arborele de fisiere intr-un
# dosar, cu un fisier JSON alaturi: ce s-a citit, ce lipseste si de ce.
#
# Standardele: ISO/IEC 13818-6 (DSM-CC: DSI, DII, DDB, sectiunile lor, transactionId), ETSI EN 301 192 (caruselul de
# obiecte in DVB, data_broadcast_id, pistele 0x0B / 0x0C), ETSI TR 101 202 (BIOP in DVB: IOR, ObjectLocation,
# ConnBinder, tap-urile, ModuleInfo, compressed_module_descriptor, mesajele File / Directory / ServiceGateway / Stream /
# StreamEvent), ETSI TS 102 809 si TS 102 796 (transport_protocol_descriptor 0x0001 din AIT: component_tag-ul pistei cu
# DSI-ul). Cod scris de la zero. Partea comuna cu analiza fluxului (sectiunile, PMT, AIT, antetul mesajelor DSM-CC,
# DDB, filtrele de demux) vine din Components/HdsAnalizaFlux.py, nu se copiaza aici.
#
# Pistele: association_tag din tap-uri se cauta in association_tag_descriptor (0x14) din PMT, apoi octetul lui de jos
# in component_tag-urile din stream_identifier_descriptor (0x52). Un tag care nu e in PMT (se intampla: un carusel
# adevarat are tag-ul 9 in DSI si DII, iar pista lui are component_tag 42) se cauta pe pista DSI-ului; la fel un tag din
# deferred_association_tags_descriptor (0x15, pista altui serviciu, nefolosita aici). Blocurile DDB se potrivesc dupa
# (downloadId, moduleId, moduleVersion), oricare ar fi pista pe care vin. Un DII se recunoaste dupa downloadId si
# bitii 1-15 ai transactionId-ului (partea "identification"), care nu se schimba la actualizari.
#
# Versiunile: un modul se tine dupa (downloadId, moduleId). Un DII cu alta versiune a modulului (sau alta marime)
# incepe culegerea versiunii noi; versiunea veche, intreaga, ramane in arbore pana e gata cea noua. Un DSI nou (alt
# transactionId sau alta poarta) inseamna arbore refacut de la poarta; fisierele care nu mai sunt in carusel dispar la
# scrierea urmatoare (scrie_arbore face mereu dosarul intreg din nou). `versiune` creste la fiecare schimbare care cere
# arborele din nou.
#
# Limitele (memoria receptorului e mica, iar datele vin din satelit, deci nu sunt de incredere): MAX_MODUL octeti pe
# modul asa cum vine, MAX_MODUL_DESFACUT dupa decomprimare (si niciodata peste original_size din DII), MAX_CARUSEL pe
# tot ce se tine in memorie, MAX_ASTEPTARE blocuri venite inaintea DII-ului lor, MAX_FISIERE, MAX_ADANCIME si
# MAX_ARBORE_OCTETI in arbore. Numele din carusel nu ies niciodata din dosar: numele goale, "." si "..", "/", "\",
# caracterele de control si numele prea lungi se resping (nume_sigur); arborele se scrie intr-un dosar nou, cu O_EXCL.
#
# Trei parti:
# - partea curata (fara enigma2, se probeaza pe PC): CRC-ul rapid, DSI, DII, IOR, BIOP, evenimentele de flux, Carusel
#   (starea), arbore() si scrie_arbore(), legarea cu PMT si AIT (harta_pmt, pid_dsi);
# - fisierul de captura (sectiunile salvate pe receptor de unealta de captura): citeste_captura, din_captura;
# - rularea pe PC: python3 HdsCarusel.py CAPTURA DOSAR (arborele din captura, rezumatul pe ecran).
# Citirea din demux-ul receptorului e in Components/HdsCaruselDemux.py.

from __future__ import absolute_import

import json
import os
import shutil
import struct
import sys
import zlib

try:
	from Components import HdsAnalizaFlux as A
except ImportError:  # pe PC (teste, linia de comanda): dosarul modulului e in sys.path
	import HdsAnalizaFlux as A

# ---------------------------------------------------------------- numerele din standarde

TID_DSI_DII, TID_DDB, TID_EVENIMENTE = 0x3B, 0x3C, 0x3D
MSG_DSI, MSG_DII, MSG_DDB = 0x1006, 0x1002, 0x1003
TAG_OPTIUNI_LITE, TAG_BIOP = 0x49534F05, 0x49534F06       # LiteOptionsProfileBody, BIOPProfileBody
TAG_LEGATURA, TAG_LOCATIE = 0x49534F40, 0x49534F50        # ConnBinder, ObjectLocation
FOLOSIRE_NPT, FOLOSIRE_STARE_EVENIMENTE = 0x000B, 0x000C   # STR_NPT_USE, STR_STATUS_AND_EVENT_USE
FOLOSIRE_EVENIMENTE, FOLOSIRE_STARE = 0x000D, 0x000E       # STR_EVENT_USE, STR_STATUS_USE
FOLOSIRE_DII, FOLOSIRE_OBIECT = 0x0016, 0x0017             # BIOP_DELIVERY_PARA_USE, BIOP_OBJECT_USE
FOLOSIRE_ES, FOLOSIRE_PROGRAM = 0x0018, 0x0019             # BIOP_ES_USE, BIOP_PROGRAM_USE
D_COMPRIMAT = 0x09        # compressed_module_descriptor (userInfo din ModuleInfo)
D_NPT = 0x17              # NPT_reference_descriptor (0x3D)
D_EVENIMENT = 0x1A        # stream_event_descriptor (0x3D)
D_TIP_CONTINUT = 0x72     # content_type_descriptor (objectInfo al fisierului)
D_ASOCIERE = 0x14         # association_tag_descriptor (PMT)
D_COMPONENTA = 0x52       # stream_identifier_descriptor (PMT)
D_CARUSEL = 0x13          # carousel_identifier_descriptor (PMT)
D_DATE = 0x66             # data_broadcast_id_descriptor (PMT)
PROTOCOL_CARUSEL = 0x0001

FISIER, DOSAR, POARTA, FLUX, EVENIMENT = "fil", "dir", "srg", "str", "ste"
_TIPURI_LUNGI = {"DSM::File": FISIER, "DSM::Directory": DOSAR, "DSM::ServiceGateway": POARTA, "DSM::Stream": FLUX,
	"BIOP::StreamEvent": EVENIMENT, "DSM::StreamEvent": EVENIMENT}
_DOSARE = (DOSAR, POARTA)

# pistele de carusel din PMT: stream_type (ISO/IEC 13818-6 tipurile B, C, D) si data_broadcast_id (EN 301 192 si
# registrul DVB: 0x0007 carusel de obiecte, 0x00F0 MHP, 0x0123 HbbTV)
TIPURI_DSMCC = (0x0B, 0x0C, 0x0D)
DATE_CARUSEL = (0x0007, 0x00F0, 0x0123)

# ---------------------------------------------------------------- limitele

MAX_SECTIUNE = 4096
MAX_MODUL = 4 * 1024 * 1024            # un modul asa cum vine (inainte de decomprimare)
MAX_MODUL_DESFACUT = 8 * 1024 * 1024   # un modul decomprimat
MAX_CARUSEL = 16 * 1024 * 1024         # tot ce tine un carusel in memorie (blocuri, module intregi, asteptare)
MAX_MODULE = 512                       # module intr-un DII
MAX_DII = 16                           # DII-uri tinute (fiecare cu downloadId si transactionId-ul lui)
MAX_ASTEPTARE = 256                    # blocuri DDB venite inaintea DII-ului lor
MAX_ASTEPTARE_OCTETI = 1024 * 1024
MAX_OBIECTE = 4096                     # mesaje BIOP intr-un modul
MAX_LEGATURI = 4096                    # legaturi intr-un dosar
MAX_TAPS = 16
MAX_FISIERE = 4096                     # fisiere in arbore
MAX_ADANCIME = 24                      # dosare unul in altul
MAX_ARBORE_OCTETI = 32 * 1024 * 1024   # octetii tuturor fisierelor scrise (un fisier poate fi legat de mai multe ori)
MAX_NUME = 255                         # octetii unui nume
MAX_EVENIMENTE = 64                    # evenimentele de flux tinute minte
MAX_ERORI = 64
MAX_REPETARI = 512                     # amprentele sectiunilor 0x3B / 0x3D deja desfacute

# ---------------------------------------------------------------- unelte mici

_u16, _u32 = A._u16, A._u32


def _tip(octeti):
	"""objectKind / type_id ("fil\\0" sau forma lunga "DSM::File") -> FISIER, DOSAR, POARTA, FLUX, EVENIMENT sau textul."""
	t = bytes(octeti).split(b"\0")[0].decode("latin-1")
	return _TIPURI_LUNGI.get(t, t)


_INVERS = bytes(int("{0:08b}".format(i)[::-1], 2) for i in range(256))


def crc_bun(s):
	"""Sectiunea, cu CRC_32 la capat, are CRC-ul bun (CRC-32/MPEG-2). Acelasi raspuns ca HdsAnalizaFlux.crc32_mpeg(s) == 0,
	dar facut de zlib: CRC-ul MPEG-2 (fara reflexie) al octetilor e oglinda CRC-ului zlib (cu reflexie) al acelorasi
	octeti cu bitii intorsi; restul 0 al unuia e restul 0xFFFFFFFF al celuilalt. O sectiune de 4 KiB costa microsecunde,
	nu milisecunde ca bucla in Python."""
	return (zlib.crc32(bytes(s).translate(_INVERS)) & 0xFFFFFFFF) == 0xFFFFFFFF


def crc32_mpeg(date):
	"""CRC-32/MPEG-2 al octetilor (pentru sectiunile facute de unelte si de probe), prin zlib."""
	c = (zlib.crc32(bytes(date).translate(_INVERS)) & 0xFFFFFFFF) ^ 0xFFFFFFFF
	return int("{0:032b}".format(c)[::-1], 2)


def _taps(b, i, capat, n):
	"""n tap-uri BIOP de la i (id, use, association_tag, selector) -> ([{"id", "folosire", "asociere", "tranzactie",
	"termen"}], pozitia de dupa), sau (None, capat) la o taietura. Selectorul de tip 0x0001 (al unui DII) da
	transactionId si timeout."""
	rez = []
	for _k in range(n):
		if i + 7 > capat:
			return None, capat
		sl = b[i + 6]
		if i + 7 + sl > capat:
			return None, capat
		t = {"id": _u16(b, i), "folosire": _u16(b, i + 2), "asociere": _u16(b, i + 4), "tranzactie": None, "termen": None}
		if sl >= 10 and _u16(b, i + 7) == 0x0001:
			t["tranzactie"], t["termen"] = _u32(b, i + 9), _u32(b, i + 13)
		if len(rez) < MAX_TAPS:
			rez.append(t)
		i += 7 + sl
	return rez, i


# ---------------------------------------------------------------- IOR, DSI, DII

def citeste_ior(b, i, capat):
	"""IOP::IOR (TR 101 202: type_id aliniat la 4 octeti, taggedProfiles) -> ({"tip", "carusel", "modul", "versiune",
	"cheie", "taps", "alt_carusel"}, pozitia de dupa), sau (None, capat). Din BIOPProfileBody: ObjectLocation (carouselId,
	moduleId, versiunea, objectKey) si ConnBinder (tap-urile); un LiteOptionsProfileBody (obiect in alt carusel, pe alt
	serviciu) se noteaza in "alt_carusel"."""
	if i + 4 > capat:
		return None, capat
	n = _u32(b, i)
	i += 4
	if n > 64 or i + n > capat:
		return None, capat
	rez = {"tip": _tip(b[i:i + n]), "carusel": None, "modul": None, "versiune": None, "cheie": b"", "taps": [],
		"alt_carusel": False}
	i += n + ((4 - n % 4) % 4)
	if i + 4 > capat:
		return None, capat
	profile = _u32(b, i)
	i += 4
	if profile > 16:
		return None, capat
	for _k in range(profile):
		if i + 8 > capat:
			return None, capat
		tag, lung = _u32(b, i), _u32(b, i + 4)
		i += 8
		if i + lung > capat:
			return None, capat
		if tag == TAG_BIOP:
			if not _profil_biop(b, i, i + lung, rez):
				return None, capat
		elif tag == TAG_OPTIUNI_LITE:
			rez["alt_carusel"] = True
		i += lung
	if rez["modul"] is None and not rez["alt_carusel"]:
		return None, capat
	return rez, i


def _profil_biop(b, i, capat, rez):
	"""BIOPProfileBody: profile_data_byte_order (0 = big-endian), liteComponents (ObjectLocation, ConnBinder, altele
	sarite)."""
	if i + 2 > capat or b[i] != 0:
		return False
	j = i + 2
	for _k in range(b[i + 1]):
		if j + 5 > capat:
			return False
		tag, lung = _u32(b, j), b[j + 4]
		j += 5
		if j + lung > capat:
			return False
		if tag == TAG_LOCATIE:
			if lung < 9 or 9 + b[j + 8] > lung:
				return False
			rez["carusel"], rez["modul"] = _u32(b, j), _u16(b, j + 4)
			rez["versiune"] = (b[j + 6], b[j + 7])
			rez["cheie"] = bytes(b[j + 9:j + 9 + b[j + 8]])
		elif tag == TAG_LEGATURA and lung >= 1:
			taps, _x = _taps(b, j + 1, j + lung, b[j])
			if taps is None:
				return False
			rez["taps"] = taps
		j += lung
	return rez["modul"] is not None


def citeste_dsi(s):
	"""Sectiunea DSI (0x3B, messageId 0x1006) a unui carusel de obiecte -> {"tranzactie", "srg": IOR-ul portii
	serviciului}, sau None (alt mesaj, carusel de date, forma stricata). privateData = ServiceGatewayInfo, care incepe
	cu IOR-ul portii (tip "srg" sau "DSM::ServiceGateway")."""
	m = A.mesaj_dsmcc(s)
	if m is None or m[0] != MSG_DSI:
		return None
	_msg, tranzactie, i, capat = m
	i += 20                                   # serverId
	if i + 2 > capat:
		return None
	i += 2 + _u16(s, i)                       # compatibilityDescriptor
	if i + 2 > capat:
		return None
	n = _u16(s, i)
	i += 2
	ior, _j = citeste_ior(s, i, min(capat, i + n))
	if ior is None or ior["tip"] != POARTA or ior["alt_carusel"]:
		return None
	return {"tranzactie": tranzactie, "srg": ior}


def citeste_dii(s):
	"""Sectiunea DII (0x3B, messageId 0x1002) -> {"tranzactie", "descarcare", "bloc", "module": [{"id", "marime",
	"versiune", "taps", "eticheta", "comprimat", "metoda", "marime_desfacuta"}]}, sau None. "eticheta" = association_tag
	al tap-ului BIOP_OBJECT_USE (pista blocurilor)."""
	m = A.mesaj_dsmcc(s)
	if m is None or m[0] != MSG_DII:
		return None
	_msg, tranzactie, i, capat = m
	if i + 18 > capat:
		return None
	rez = {"tranzactie": tranzactie, "descarcare": _u32(s, i), "bloc": _u16(s, i + 4), "module": []}
	i += 16                                   # downloadId, blockSize, windowSize, ackPeriod, tCDownloadWindow/Scenario
	i += 2 + _u16(s, i)                       # compatibilityDescriptor
	if i + 2 > capat or rez["bloc"] == 0:
		return None
	n = _u16(s, i)
	i += 2
	for _k in range(n):
		if i + 8 > capat:
			return None
		lung = s[i + 7]
		if i + 8 + lung > capat:
			return None
		mod = {"id": _u16(s, i), "marime": _u32(s, i + 2), "versiune": s[i + 6], "taps": [], "eticheta": None,
			"comprimat": False, "metoda": None, "marime_desfacuta": None}
		_info_modul(mod, bytes(s[i + 8:i + 8 + lung]))
		if len(rez["module"]) < MAX_MODULE:
			rez["module"].append(mod)
		i += 8 + lung
	return rez


def _info_modul(mod, info):
	"""BIOP::ModuleInfo: moduleTimeOut, blockTimeOut, minBlockTime (cate 4 octeti), tap-urile, userInfo cu descriptorii
	(compressed_module_descriptor 0x09: compression_method, original_size)."""
	if len(info) < 13:
		return
	taps, j = _taps(info, 13, len(info), info[12])
	if taps is None:
		return
	mod["taps"] = taps
	obiect = [t for t in taps if t["folosire"] == FOLOSIRE_OBIECT]
	if obiect:
		mod["eticheta"] = obiect[0]["asociere"]
	if j < len(info):
		for tag, c in A.descriptori(info, j + 1, min(len(info), j + 1 + info[j])):
			if tag == D_COMPRIMAT and len(c) >= 5:
				mod["comprimat"], mod["metoda"], mod["marime_desfacuta"] = True, c[0], _u32(c, 1)


def desfa(date, metoda, marime_desfacuta, maxim=MAX_MODUL_DESFACUT):
	"""Modulul comprimat -> octetii desfacuti, sau None. compression_method cu bitii de jos 8 = deflate (ca in primul
	octet al antetului zlib, RFC 1950; un carusel adevarat pune chiar 0x78). Se citeste ca flux zlib, apoi ca deflate fara
	antet; niciodata peste original_size (cand e dat) si peste maxim; un flux care nu se incheie e stricat."""
	if metoda is not None and (metoda & 0x0F) != 8:
		return None
	limita = min(maxim, marime_desfacuta) if marime_desfacuta else maxim
	for w in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
		d = zlib.decompressobj(w)
		try:
			rez = d.decompress(bytes(date), limita + 1)
		except zlib.error:
			continue
		if len(rez) > limita or d.unconsumed_tail:
			return None
		if d.eof:
			return rez
	return None


def citeste_evenimente(s):
	"""Sectiunea 0x3D (DSMCC_descriptor_list) -> [{"id", "npt", "date"}] din stream_event_descriptor (0x1A: eventId,
	31 de biti rezervati, eventNPT pe 33 de biti, privateDataByte). Ceilalti descriptori (NPT_reference 0x17 si altii)
	se sar. None cand sectiunea nu e 0x3D."""
	if not s or s[0] != TID_EVENIMENTE or len(s) < 12:
		return None
	rez = []
	for tag, c in A.descriptori(s, 8, len(s) - 4):
		if tag == D_EVENIMENT and len(c) >= 10:
			rez.append({"id": _u16(c, 0), "npt": ((c[5] & 0x01) << 32) | _u32(c, 6), "date": bytes(c[10:])})
	return rez


# ---------------------------------------------------------------- BIOP

def mesaje_biop(date, maxim=MAX_OBIECTE):
	"""Mesajele BIOP ale unui modul intreg -> ({objectKey: obiect}, eroarea sau None). obiect = {"cheie", "tip",
	"continut" (fisier, memoryview din modul, fara copie), "tip_continut", "legaturi" (dosar, poarta: [{"nume": [octetii
	fiecarei componente], "tip", "legare", "ior"}]), "descriere", "taps", "evenimente" (flux, eveniment)}. Primul
	mesaj stricat opreste citirea modulului (restul nu se mai poate gasi)."""
	b = memoryview(bytes(date))
	rez = {}
	i, n = 0, len(b)
	while i < n:
		if len(rez) >= maxim:
			return rez, "prea multe obiecte"
		try:
			o, i = _mesaj(b, i, n)
		except (IndexError, ValueError, struct.error):
			o = None
		if o is None:
			return rez, "mesaj BIOP stricat la %d" % i
		rez[o["cheie"]] = o
	return rez, None


def _mesaj(b, i, n):
	"""Un mesaj BIOP de la i: magic "BIOP", versiunea 1.0, big-endian, message_type 0, message_size; objectKey, objectKind,
	objectInfo, serviceContextList, messageBody. -> (obiect, pozitia de dupa) sau (None, i)."""
	if i + 12 > n or bytes(b[i:i + 4]) != b"BIOP" or b[i + 4] != 1 or b[i + 6] != 0 or b[i + 7] != 0:
		return None, i
	capat = i + 12 + _u32(b, i + 8)
	if capat > n:
		return None, i
	j = i + 12
	cheie = bytes(b[j + 1:j + 1 + b[j]])
	j += 1 + b[j]
	fl = _u32(b, j)
	if fl > 64:
		return None, i
	tip = _tip(b[j + 4:j + 4 + fl])
	j += 4 + fl
	il = _u16(b, j)
	info = b[j + 2:j + 2 + il]
	j += 2 + il
	contexte = b[j]
	j += 1
	for _k in range(contexte):
		j += 6 + _u16(b, j + 4)
	corp = _u32(b, j)
	j += 4
	if j + corp > capat or len(info) != il:
		return None, i
	o = {"cheie": cheie, "tip": tip, "continut": None, "tip_continut": u"", "legaturi": [], "descriere": u"", "taps": [],
		"evenimente": []}
	if tip == FISIER:
		cl = _u32(b, j)
		if 4 + cl > corp:
			return None, i
		o["continut"] = b[j + 4:j + 4 + cl]
		if il >= 8:
			for tag, c in A.descriptori(info, 8, il):
				if tag == D_TIP_CONTINUT and not o["tip_continut"]:
					o["tip_continut"] = bytes(c).decode("latin-1")
	elif tip in _DOSARE:
		o["legaturi"] = _legaturi(b, j, j + corp)
		if o["legaturi"] is None:
			return None, i
	elif tip in (FLUX, EVENIMENT):
		_flux(o, info, b, j, j + corp)
	return o, capat


def _legaturi(b, j, capat):
	"""Corpul unui dosar sau al portii: bindings_count, apoi fiecare legatura (componentele numelui id/kind,
	bindingType, IOR, objectInfo) -> lista, sau None la o taietura."""
	n = _u16(b, j)
	j += 2
	rez = []
	for _k in range(n):
		if len(rez) >= MAX_LEGATURI or j >= capat:
			return None
		componente = b[j]
		j += 1
		nume, tip = [], u""
		for _c in range(componente):
			nume.append(bytes(b[j + 1:j + 1 + b[j]]))
			j += 1 + b[j]
			tip = _tip(b[j + 1:j + 1 + b[j]])
			j += 1 + b[j]
		legare = b[j]
		ior, j = citeste_ior(b, j + 1, capat)
		if ior is None or j + 2 > capat:
			return None
		j += 2 + _u16(b, j)                   # objectInfo al legaturii (fisier: ContentSize pe 8 octeti)
		if j > capat:
			return None
		rez.append({"nume": nume, "tip": tip or ior["tip"], "legare": legare, "ior": ior})
	return rez


def _info_flux(info, cu_nume, micro):
	"""Stream::Info_T (aDescription, aDuration = aSeconds pe 4 octeti si aMicroSeconds pe `micro` octeti, audio, video,
	data) si, la eveniment, EventList_T (eventNames_count, numele) -> (descrierea, [numele]), sau None la o taietura."""
	if len(info) < 1 or 1 + info[0] > len(info):
		return None
	descriere = bytes(info[1:1 + info[0]]).split(b"\0")[0].decode("latin-1")
	k = 1 + info[0] + 4 + micro + 3
	if k > len(info):
		return None
	nume = []
	if cu_nume:
		if k + 2 > len(info):
			return None
		n = _u16(info, k)
		k += 2
		for _e in range(n):
			if k >= len(info) or k + 1 + info[k] > len(info):
				return None
			nume.append(bytes(info[k + 1:k + 1 + info[k]]).split(b"\0")[0].decode("latin-1"))
			k += 1 + info[k]
	return descriere, nume


def _flux(o, info, b, j, capat):
	"""Flux (DSM::Stream) si eveniment de flux (BIOP::StreamEvent): objectInfo = Stream::Info_T, la eveniment urmat de
	numele evenimentelor; corpul = tap-urile, la eveniment urmate de eventIds. aMicroSeconds are 32 de biti in TS 102
	809 si 16 in TR 101 202: se incearca 32, apoi 16, si se alege forma la care numarul numelor e cel al eventIds."""
	ids = []
	if j < capat:
		taps, j = _taps(b, j + 1, capat, b[j])
		o["taps"] = taps or []
		if taps is not None and o["tip"] == EVENIMENT and j < capat:
			ids = [_u16(b, j + 1 + 2 * k) for k in range(b[j]) if j + 3 + 2 * k <= capat]
	ales = rezerva = None
	for micro in (4, 2):
		x = _info_flux(info, o["tip"] == EVENIMENT, micro)
		if x is None:
			continue
		if rezerva is None:
			rezerva = x
		if o["tip"] != EVENIMENT or len(x[1]) == len(ids):
			ales = x
			break
	o["descriere"], nume = ales or rezerva or (u"", [])
	o["evenimente"] = [{"nume": nume[k] if k < len(nume) else u"", "id": ids[k] if k < len(ids) else None}
		for k in range(max(len(nume), len(ids)))]


def nume_sigur(octeti):
	"""Un nume din carusel -> textul folosit pe disc, sau None cand nu se poate folosi fara risc: gol, "." sau "..", cu
	"/" sau "\\", cu caractere de control sau NUL in mijloc, mai lung de MAX_NUME octeti. Terminatorul NUL de la capat
	(unele carusele il pun) se scoate. UTF-8, altfel Latin-1."""
	b = bytes(octeti).rstrip(b"\0")
	if not b or len(b) > MAX_NUME:
		return None
	try:
		t = b.decode("utf-8")
	except UnicodeDecodeError:
		t = b.decode("latin-1")
	if t in (u".", u"..") or u"/" in t or u"\\" in t or any(ord(ch) < 0x20 or 0x7F <= ord(ch) < 0xA0 for ch in t):
		return None
	return t


# ---------------------------------------------------------------- modulul si caruselul

class Modul(object):
	"""Un modul (downloadId, moduleId) in versiunea anuntata de DII: blocurile (cate `bloc` octeti, ultimul mai scurt),
	apoi, intreg, datele (decomprimate daca DII-ul o cere) si obiectele BIOP. `octeti` = cat tine in memorie."""

	def __init__(self, descarcare, info, bloc):
		self.descarcare = descarcare
		self.info = info
		self.id = info["id"]
		self.versiune = info["versiune"]
		self.marime = info["marime"]
		self.bloc = bloc
		self.n = max(1, (self.marime + bloc - 1) // bloc)
		self.blocuri = {}
		self.octeti = 0
		self.date = None
		self.obiecte = None
		self.eroare = None

	def lungime_bloc(self, nr):
		return self.bloc if nr < self.n - 1 else self.marime - self.bloc * (self.n - 1)

	def pune(self, nr, date):
		"""Un bloc DDB. -> True cand modulul s-a umplut (atunci se cheama incheie())."""
		self.blocuri[nr] = date
		self.octeti += len(date)
		return len(self.blocuri) == self.n

	def incheie(self):
		"""Blocurile -> datele si obiectele BIOP; blocurile se elibereaza. -> True daca modulul e bun."""
		date = b"".join(self.blocuri[k] for k in range(self.n))
		self.blocuri = {}
		self.octeti = 0
		if self.info.get("comprimat"):
			date = desfa(date, self.info.get("metoda"), self.info.get("marime_desfacuta"))
			if date is None:
				self.eroare = "decomprimarea a cazut"
				return False
		self.obiecte, eroare = mesaje_biop(date)
		if eroare and not self.obiecte:
			self.eroare = eroare
			self.obiecte = None
			return False
		if eroare:
			self.eroare = eroare
		self.date = date
		self.octeti = len(date)
		return True

	def gata(self):
		return self.obiecte is not None

	def rezumat(self):
		return {"descarcare": self.descarcare, "id": self.id, "versiune": self.versiune, "marime": self.marime,
			"comprimat": bool(self.info.get("comprimat")), "marime_desfacuta": self.info.get("marime_desfacuta"),
			"blocuri": "%d/%d" % (self.n if self.gata() else len(self.blocuri), self.n), "gata": self.gata(),
			"eticheta": self.info.get("eticheta"), "eroare": self.eroare}


class Carusel(object):
	"""Starea unui carusel de obiecte, hranita cu sectiuni (sectiune(s, pid)), de pe un singur fir. Nu citeste nimic
	singura si nu scrie nimic pe disc: arbore() da arborele de acum, scrie_arbore() il pune pe disc.

	verifica_crc: CRC-ul se verifica in Python (rapid, prin zlib) pe fiecare sectiune folosita; o sectiune care repeta
	una deja desfacuta (acelasi antet si acelasi CRC) sau un bloc pe care il avem deja se sar inainte de verificare."""

	def __init__(self, verifica_crc=True, maxim=MAX_CARUSEL):
		self.verifica_crc = verifica_crc
		self.maxim = maxim
		self.dsi = None
		self.pid_dsi = None
		self.dii = {}             # (downloadId, extensia sectiunii) -> DII-ul citit, cu "pid" si "ordine"
		self.module = {}          # (downloadId, moduleId) -> Modul in versiunea ultimului DII
		self.vechi = {}           # (downloadId, moduleId) -> Modul intreg de dinainte, pana e gata cel nou
		self.asteptare = []       # (downloadId, moduleId, versiunea, nr, datele) venite inaintea DII-ului
		self.asteptare_octeti = 0
		self.evenimente = []      # evenimentele de flux (0x3D), cele mai noi la coada
		self.tinuti = 0           # octetii tinuti in module (blocuri si date)
		self.versiune = 0
		self.erori = []
		self._repetari = {}
		self._ordine = 0
		self.contoare = {"sectiuni": 0, "alte": 0, "stricate": 0, "crc": 0, "dsi": 0, "dii": 0, "ddb": 0, "blocuri": 0,
			"dubluri": 0, "asteptare": 0, "evenimente": 0, "actualizari": 0, "prea_mult": 0, "module_gata": 0}

	# ------------------------------------------------ intrarea

	def sectiune(self, s, pid=None):
		"""O sectiune citita din demux sau din captura (cu sau fara umplutura dupa ea). -> True cand arborele s-a schimbat
		(un modul nou intreg, alt DSI)."""
		self.contoare["sectiuni"] += 1
		b = bytes(s or b"")
		if len(b) < 12 or b[0] not in (TID_DSI_DII, TID_DDB, TID_EVENIMENTE):
			self.contoare["alte"] += 1
			return False
		n = ((b[1] & 0x0F) << 8) | b[2]
		if not (b[1] & 0x80) or n < 9 or 3 + n > len(b) or 3 + n > MAX_SECTIUNE:
			self.contoare["stricate"] += 1
			return False
		b = b[:3 + n]
		if b[0] == TID_DDB:
			return self._ddb(b)
		cheie = (b[0], b[3], b[4], b[5])
		if self._repetari.get(cheie) == b[-4:]:
			return False
		if self.verifica_crc and not crc_bun(b):
			self.contoare["crc"] += 1
			return False
		if len(self._repetari) >= MAX_REPETARI:
			self._repetari.clear()
		self._repetari[cheie] = b[-4:]
		if b[0] == TID_EVENIMENTE:
			return self._evenimente(b, pid)
		m = A.mesaj_dsmcc(b)
		if m is None:
			self.contoare["stricate"] += 1
			return False
		if m[0] == MSG_DSI:
			return self._dsi(b, pid)
		if m[0] == MSG_DII:
			return self._dii(b, pid)
		self.contoare["alte"] += 1
		return False

	def _eroare(self, text):
		if text not in self.erori:
			if len(self.erori) >= MAX_ERORI:
				self.erori.pop(0)
			self.erori.append(text)

	def _dsi(self, b, pid):
		d = citeste_dsi(b)
		if d is None:
			self.contoare["stricate"] += 1
			self._eroare("DSI fara poarta de carusel de obiecte")
			return False
		self.contoare["dsi"] += 1
		if self.dsi is not None and self.dsi == d:
			return False
		if self.dsi is not None:
			self.contoare["actualizari"] += 1
		self.dsi, self.pid_dsi = d, pid
		self.versiune += 1
		return True

	def _dii(self, b, pid):
		d = citeste_dii(b)
		if d is None:
			self.contoare["stricate"] += 1
			self._eroare("DII stricat")
			return False
		self.contoare["dii"] += 1
		# un DII se recunoaste dupa downloadId si partea "identification" a transactionId-ului (bitii 1-15, TS 102 809
		# B.2.5.2): bitul 0 si bitii de sus se schimba la fiecare actualizare a lui
		cheie_dii = (d["descarcare"], d["tranzactie"] & 0xFFFE)
		vechi = self.dii.get(cheie_dii)
		if vechi is not None and vechi["tranzactie"] != d["tranzactie"]:
			self.contoare["actualizari"] += 1
		self._ordine += 1
		d["pid"], d["ordine"] = pid, self._ordine
		self.dii[cheie_dii] = d
		if len(self.dii) > MAX_DII:
			del self.dii[min(self.dii, key=lambda k: self.dii[k]["ordine"])]
		schimbat = False
		for info in d["module"]:
			cheie = (d["descarcare"], info["id"])
			mod = self.module.get(cheie)
			if mod is not None and mod.versiune == info["versiune"] and mod.marime == info["marime"] and \
					mod.bloc == d["bloc"]:
				continue
			nou = Modul(d["descarcare"], info, d["bloc"])
			if info["marime"] > MAX_MODUL:
				nou.eroare = "modul prea mare (%d octeti)" % info["marime"]
				self._eroare("modulul %d: %s" % (info["id"], nou.eroare))
			if mod is not None:
				self.tinuti -= mod.octeti
				if mod.gata():
					self._scoate_vechi(cheie)
					self.vechi[cheie] = mod
					self.tinuti += mod.octeti
			self.module[cheie] = nou
			schimbat = self._din_asteptare(nou) or schimbat
		return schimbat

	def _scoate_vechi(self, cheie):
		v = self.vechi.pop(cheie, None)
		if v is not None:
			self.tinuti -= v.octeti

	def _ddb(self, b):
		self.contoare["ddb"] += 1
		d = A.citeste_ddb(b)
		if d is None:
			self.contoare["stricate"] += 1
			return False
		descarcare, modul, versiune, nr, date = d
		mod = self.module.get((descarcare, modul))
		if mod is None or mod.versiune != versiune:
			if self.verifica_crc and not crc_bun(b):
				self.contoare["crc"] += 1
				return False
			self._asteapta(descarcare, modul, versiune, nr, date)
			return False
		if mod.gata() or mod.eroare or nr in mod.blocuri:
			self.contoare["dubluri"] += 1
			return False
		if self.verifica_crc and not crc_bun(b):
			self.contoare["crc"] += 1
			return False
		return self._pune(mod, nr, date)

	def _asteapta(self, descarcare, modul, versiune, nr, date):
		for x in self.asteptare:
			if x[:4] == (descarcare, modul, versiune, nr):
				return
		while self.asteptare and (len(self.asteptare) >= MAX_ASTEPTARE or
				self.asteptare_octeti + len(date) > MAX_ASTEPTARE_OCTETI):
			self.asteptare_octeti -= len(self.asteptare.pop(0)[4])
		if len(date) <= MAX_ASTEPTARE_OCTETI:
			self.asteptare.append((descarcare, modul, versiune, nr, date))
			self.asteptare_octeti += len(date)
			self.contoare["asteptare"] += 1

	def _din_asteptare(self, mod):
		schimbat = False
		ramase = []
		for x in self.asteptare:
			if x[0] == mod.descarcare and x[1] == mod.id and x[2] == mod.versiune:
				self.asteptare_octeti -= len(x[4])
				if not mod.gata() and not mod.eroare and x[3] not in mod.blocuri:
					schimbat = self._pune(mod, x[3], x[4]) or schimbat
			else:
				ramase.append(x)
		self.asteptare = ramase
		return schimbat

	def _pune(self, mod, nr, date):
		if mod.eroare:
			return False
		if nr >= mod.n or len(date) != mod.lungime_bloc(nr):
			self.contoare["stricate"] += 1
			self._eroare("modulul %d: blocul %d are alta lungime" % (mod.id, nr))
			return False
		if self.tinuti + self.asteptare_octeti + len(date) > self.maxim:
			self.contoare["prea_mult"] += 1
			self._eroare("caruselul trece de %d octeti" % self.maxim)
			return False
		self.contoare["blocuri"] += 1
		inainte = mod.octeti
		plin = mod.pune(nr, date)
		self.tinuti += mod.octeti - inainte
		if not plin:
			return False
		inainte = mod.octeti
		bun = mod.incheie()
		self.tinuti += mod.octeti - inainte
		cheie = (mod.descarcare, mod.id)
		if not bun:
			self._eroare("modulul %d versiunea %d: %s" % (mod.id, mod.versiune, mod.eroare))
			return False
		if mod.eroare:
			self._eroare("modulul %d versiunea %d: %s" % (mod.id, mod.versiune, mod.eroare))
		self._scoate_vechi(cheie)
		if self.tinuti > self.maxim:
			self.contoare["prea_mult"] += 1
			self._eroare("caruselul trece de %d octeti" % self.maxim)
		self.contoare["module_gata"] += 1
		self.versiune += 1
		return True

	def _evenimente(self, b, pid):
		ev = citeste_evenimente(b)
		if ev is None:
			return False
		for e in ev:
			self.contoare["evenimente"] += 1
			e["pid"], e["versiune"], e["extensie"] = pid, (b[5] >> 1) & 0x1F, (b[3] << 8) | b[4]
			self.evenimente.append(e)
		del self.evenimente[:-MAX_EVENIMENTE]
		return False

	# ------------------------------------------------ iesirea

	def modul_gata(self, descarcare, modul):
		"""Versiunea intreaga cea mai noua a modulului, sau None."""
		cheie = (descarcare, modul)
		m = self.module.get(cheie)
		if m is not None and m.gata():
			return m
		return self.vechi.get(cheie)

	def obiect(self, ior):
		"""Obiectul la care trimite un IOR -> (obiectul, None) sau (None, ce lipseste)."""
		if ior is None or ior.get("modul") is None:
			return None, "fara locatie"
		m = self.modul_gata(ior["carusel"], ior["modul"])
		if m is None:
			return None, "modulul %d" % ior["modul"]
		o = m.obiecte.get(ior["cheie"])
		if o is None:
			return None, "obiectul %s din modulul %d" % (ior["cheie"].hex(), ior["modul"])
		return o, None

	def module_lipsa(self):
		"""Modulele ultimului DII care nu sunt inca intregi (nici in versiunea veche)."""
		return sorted(m.id for k, m in self.module.items() if self.modul_gata(*k) is None)

	def arbore(self, maxim_fisiere=MAX_FISIERE, maxim_octeti=MAX_ARBORE_OCTETI, maxim_adancime=MAX_ADANCIME):
		"""Arborele de acum, pornit din poarta serviciului (DSI) -> {"complet", "fisiere": [(calea ca tuplu de nume,
		obiectul)], "dosare": [cai, parintii inaintea copiilor], "fluxuri": [(cale, obiect)], "lipsa": [ce lipseste],
		"erori": [...], "octeti"}. Fiecare dosar se deschide o singura data (buclele si dosarele legate de doua ori se
		opresc si se spun); numele respinse de nume_sigur nu intra."""
		rez = {"complet": False, "fisiere": [], "dosare": [], "fluxuri": [], "lipsa": [], "erori": [], "octeti": 0}
		if self.dsi is None:
			rez["lipsa"].append("DSI")
			return rez
		poarta, lipsa = self.obiect(self.dsi["srg"])
		if poarta is None:
			rez["lipsa"].append(lipsa)
			return rez
		srg = self.dsi["srg"]
		vazute = {(srg["carusel"], srg["modul"], srg["cheie"])}
		coada = [((), poarta)]
		oprit = False
		while coada and not oprit:
			cale, o = coada.pop(0)
			nume_dosar = set()
			for leg in o["legaturi"]:
				aici = u"/".join(cale)
				if len(leg["nume"]) != 1:
					rez["erori"].append(u"%s: nume din %d bucati" % (aici, len(leg["nume"])))
					continue
				nume = nume_sigur(leg["nume"][0])
				if nume is None:
					rez["erori"].append(u"%s: nume respins %r" % (aici, leg["nume"][0][:40]))
					continue
				if nume in nume_dosar:
					rez["erori"].append(u"%s: numele %s de doua ori" % (aici, nume))
					continue
				nume_dosar.add(nume)
				c = cale + (nume,)
				ior = leg["ior"]
				if ior["alt_carusel"]:
					rez["erori"].append(u"%s: in alt carusel" % u"/".join(c))
					continue
				tinta, lipsa = self.obiect(ior)
				if tinta is None:
					if lipsa not in rez["lipsa"]:
						rez["lipsa"].append(lipsa)
					continue
				if tinta["tip"] in _DOSARE:
					semn = (ior["carusel"], ior["modul"], ior["cheie"])
					if semn in vazute:
						rez["erori"].append(u"%s: dosar deja deschis (bucla)" % u"/".join(c))
						continue
					if len(c) > maxim_adancime:
						rez["erori"].append(u"%s: prea adanc" % u"/".join(c))
						continue
					vazute.add(semn)
					rez["dosare"].append(c)
					coada.append((c, tinta))
				elif tinta["tip"] == FISIER:
					marime = len(tinta["continut"])
					if len(rez["fisiere"]) >= maxim_fisiere or rez["octeti"] + marime > maxim_octeti:
						rez["erori"].append(u"prea multe fisiere sau octeti; oprit la %s" % u"/".join(c))
						oprit = True
						break
					rez["fisiere"].append((c, tinta))
					rez["octeti"] += marime
				elif tinta["tip"] in (FLUX, EVENIMENT):
					rez["fluxuri"].append((c, tinta))
				else:
					rez["erori"].append(u"%s: tip necunoscut %s" % (u"/".join(c), tinta["tip"]))
		rez["complet"] = not rez["lipsa"] and not oprit
		return rez


# ---------------------------------------------------------------- arborele pe disc

_INTERZISE_WINDOWS = u'<>:"|?*'


def _pe_disc(nume):
	"""Numele (deja trecut prin nume_sigur) pe sistemul de fisiere de aici: pe Windows (rularea pe PC) caracterele pe
	care Windows nu le primeste devin "_"; pe receptor numele ramane cum e."""
	if os.name == "nt":
		return u"".join(u"_" if ch in _INTERZISE_WINDOWS else ch for ch in nume)
	return nume


def _sterge(cale):
	if os.path.islink(cale) or os.path.isfile(cale):
		os.remove(cale)
	elif os.path.isdir(cale):
		shutil.rmtree(cale, ignore_errors=True)


def scrie_arbore(arbore, dosar):
	"""Arborele -> dosar. Se scrie intai in dosar + ".nou" (sters inainte, deci nou si gol), cu O_EXCL si fara a urma
	legaturi simbolice; apoi dosarul vechi devine dosar + ".vechi", cel nou ia locul lui, iar cel vechi se sterge. ->
	(fisiere scrise, erori)."""
	nou, vechi = dosar + ".nou", dosar + ".vechi"
	_sterge(nou)
	_sterge(vechi)
	os.makedirs(nou)
	baza = os.path.realpath(nou)
	erori = []
	for cale in arbore["dosare"]:
		try:
			os.mkdir(os.path.join(nou, *[_pe_disc(x) for x in cale]))
		except OSError as e:
			erori.append(u"%s: %s" % (u"/".join(cale), e))
	scrise = 0
	steaguri = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
	for cale, o in arbore["fisiere"]:
		p = os.path.join(nou, *[_pe_disc(x) for x in cale])
		if not os.path.realpath(p).startswith(baza + os.sep):
			erori.append(u"%s: in afara dosarului" % u"/".join(cale))
			continue
		try:
			fd = os.open(p, steaguri, 0o644)
		except OSError as e:
			erori.append(u"%s: %s" % (u"/".join(cale), e))
			continue
		with os.fdopen(fd, "wb") as f:
			f.write(o["continut"])
		scrise += 1
	if os.path.lexists(dosar):
		os.rename(dosar, vechi)
	os.rename(nou, dosar)
	_sterge(vechi)
	return scrise, erori


def manifest(carusel, arbore, extra=None):
	"""Ce se scrie langa arbore (dosar + ".json"): DSI-ul, modulele, fisierele (cu tipul continutului), fluxurile si
	evenimentele lor, ce lipseste, erorile, contoarele, ultimele evenimente de flux."""
	m = {"complet": arbore["complet"], "dsi": None, "module": [], "fisiere": [], "dosare": [], "fluxuri": [],
		"lipsa": list(arbore["lipsa"]), "erori": list(carusel.erori) + list(arbore["erori"]),
		"contoare": dict(carusel.contoare), "octeti_tinuti": carusel.tinuti, "versiune": carusel.versiune,
		"evenimente": [{"id": e["id"], "npt": e["npt"], "date": e["date"].hex(), "pid": e["pid"],
			"versiune": e["versiune"]} for e in carusel.evenimente]}
	if carusel.dsi is not None:
		srg = carusel.dsi["srg"]
		m["dsi"] = {"tranzactie": "%08x" % carusel.dsi["tranzactie"], "pid": carusel.pid_dsi, "carusel": srg["carusel"],
			"modul": srg["modul"], "cheie": srg["cheie"].hex(), "taps": srg["taps"]}
	m["module"] = [x.rezumat() for _k, x in sorted(carusel.module.items())]
	m["fisiere"] = [{"cale": u"/".join(c), "marime": len(o["continut"]), "tip": o["tip_continut"]}
		for c, o in arbore["fisiere"]]
	m["dosare"] = [u"/".join(c) for c in arbore["dosare"]]
	m["fluxuri"] = [{"cale": u"/".join(c), "tip": o["tip"], "descriere": o["descriere"], "evenimente": o["evenimente"],
		"taps": o["taps"]} for c, o in arbore["fluxuri"]]
	if extra:
		m.update(extra)
	return m


def scrie_json(cale, date):
	with open(cale + ".nou", "w", encoding="utf-8") as f:
		json.dump(date, f, indent=1, sort_keys=True, ensure_ascii=True)
	os.replace(cale + ".nou", cale)


# ---------------------------------------------------------------- PMT, AIT si pista DSI-ului

def harta_pmt(s):
	"""Sectiunea PMT -> {"program", "etichete": {component_tag (0x52): PID}, "asocieri": {association_tag (0x14): PID},
	"amanate": [association_tag-urile din deferred_association_tags_descriptor (0x15), pe alt serviciu], "carusele":
	[PID-urile pistelor de carusel, in ordinea din PMT], "ait": PID-ul AIT sau None, "carusel_id": din prima bucla,
	"piste": [{"pid", "tip", "tag", "carusel_id", "date"}]}, sau None."""
	s = A.sectiune(s)
	if s is None or s[0] != 0x02 or len(s) < 16:
		return None
	rez = {"program": _u16(s, 3), "etichete": {}, "asocieri": {}, "amanate": [], "carusele": [], "ait": None,
		"carusel_id": None, "piste": []}
	n = ((s[10] & 0x0F) << 8) | s[11]
	for tag, c in A.descriptori(s, 12, min(12 + n, len(s) - 4)):
		if tag == D_CARUSEL and len(c) >= 4:
			rez["carusel_id"] = _u32(c, 0)
		elif tag == 0x15 and len(c) >= 1:
			rez["amanate"] += [_u16(c, 1 + 2 * k) for k in range(c[0] // 2) if 3 + 2 * k <= len(c)]
	i, sfarsit = 12 + n, len(s) - 4
	while i + 5 <= sfarsit:
		tip, pid = s[i], _u16(s, i + 1) & 0x1FFF
		lung = ((s[i + 3] & 0x0F) << 8) | s[i + 4]
		p = {"pid": pid, "tip": tip, "tag": None, "carusel_id": None, "date": None}
		for tag, c in A.descriptori(s, i + 5, min(i + 5 + lung, sfarsit)):
			if tag == D_COMPONENTA and len(c) >= 1:
				p["tag"] = c[0]
				rez["etichete"].setdefault(c[0], pid)
			elif tag == D_ASOCIERE and len(c) >= 2:
				rez["asocieri"].setdefault(_u16(c, 0), pid)
			elif tag == 0x15 and len(c) >= 1:
				rez["amanate"] += [_u16(c, 1 + 2 * k) for k in range(c[0] // 2) if 3 + 2 * k <= len(c)]
			elif tag == D_CARUSEL and len(c) >= 4:
				p["carusel_id"] = _u32(c, 0)
			elif tag == D_DATE and len(c) >= 2:
				p["date"] = _u16(c, 0)
			elif tag == 0x6F and tip == 0x05:
				rez["ait"] = pid
		if tip in TIPURI_DSMCC or p["carusel_id"] is not None or p["date"] in DATE_CARUSEL:
			rez["carusele"].append(pid)
		rez["piste"].append(p)
		i += 5 + lung
	return rez


def transport_carusel(aplicatie):
	"""Primul transport prin carusel (protocol 0x0001) al aplicatiei din AIT (forma HdsAnalizaFlux.citeste_ait), sau
	None."""
	for t in (aplicatie or {}).get("transporturi") or ():
		if t.get("protocol") == PROTOCOL_CARUSEL:
			return t
	return None


def pid_dsi(harta, aplicatie=None):
	"""PID-ul pistei cu DSI-ul: pentru o aplicatie din AIT, pista cu component_tag-ul transportului ei prin carusel
	(numai pe acest serviciu: un transport cu remote_connection = 1 da None); fara aplicatie, prima pista de carusel de
	obiecte din PMT (0x0B sau data_broadcast_id de carusel). -> (PID sau None, motivul)."""
	if not harta:
		return None, "fara PMT"
	if aplicatie is not None:
		t = transport_carusel(aplicatie)
		if t is None:
			return None, "aplicatia nu are transport prin carusel"
		if t.get("la_distanta"):
			return None, "caruselul e pe alt serviciu (%x.%x.%x)" % (t.get("onid", 0), t.get("tsid", 0), t.get("sid", 0))
		pid = harta["etichete"].get(t.get("tag"))
		if pid is None:
			return None, "component_tag %s nu e in PMT" % t.get("tag")
		return pid, "component_tag %d" % t["tag"]
	for p in harta["piste"]:
		if p["pid"] in harta["carusele"] and (p["tip"] == 0x0B or p["date"] in DATE_CARUSEL):
			return p["pid"], "prima pista de carusel de obiecte"
	return None, "PMT-ul nu are pista de carusel"


def pid_pentru_eticheta(harta, eticheta, pid_rezerva):
	"""association_tag dintr-un tap -> PID-ul pistei: intai association_tag_descriptor (0x14), apoi octetul de jos =
	component_tag (TS 102 809 B.3.2, TR 101 202 4.7.7.3); altfel pid_rezerva (pista DSI-ului). Un tag din
	deferred_association_tags_descriptor (pe alt serviciu) nu se urmeaza: tot pid_rezerva."""
	if harta and eticheta is not None:
		if eticheta in harta.get("asocieri", {}):
			return harta["asocieri"][eticheta]
		if (eticheta & 0xFF) in harta["etichete"]:
			return harta["etichete"][eticheta & 0xFF]
	return pid_rezerva


def piste_module(carusel, harta):
	"""PID-urile pe care vin blocurile modulelor de acum (din tap-urile BIOP_OBJECT_USE), fara pista DSI-ului."""
	rez = []
	for m in carusel.module.values():
		pid = pid_pentru_eticheta(harta, m.info.get("eticheta"), carusel.pid_dsi)
		if pid is not None and pid != carusel.pid_dsi and pid not in rez:
			rez.append(pid)
	return rez


# ---------------------------------------------------------------- fisierul de captura

# Forma fisierului (o scrie unealta de captura de pe receptor): MAGIC, apoi inregistrari: tipul (1 octet) si lungimea
# (4 octeti, big-endian), apoi continutul. R_ANTET si R_SFARSIT: JSON in UTF-8 (canalul, PID-urile, demux-ul, starea
# demux-ului inainte si dupa, contoarele). R_SECTIUNE: milisecundele de la inceput (4 octeti), PID-ul (2 octeti), apoi
# sectiunea asa cum a dat-o demux-ul. O captura oprita la mijloc se citeste pana la ultima inregistrare intreaga.
MAGIC = b"HDSCAR1\n"
R_ANTET, R_SECTIUNE, R_SFARSIT = 1, 2, 3
MAX_INREGISTRARE = 1024 * 1024


def citeste_captura(cale):
	"""Fisierul de captura -> ("antet", dict) / ("sectiune", ms, pid, octeti) / ("sfarsit", dict), in ordine."""
	with open(cale, "rb") as f:
		if f.read(len(MAGIC)) != MAGIC:
			raise ValueError("nu e o captura de carusel")
		while True:
			a = f.read(5)
			if len(a) < 5:
				return
			tip, n = struct.unpack(">BI", a)
			if n > MAX_INREGISTRARE:
				return
			c = f.read(n)
			if len(c) < n:
				return
			if tip == R_SECTIUNE and n >= 6:
				ms, pid = struct.unpack(">IH", c[:6])
				yield "sectiune", ms, pid, c[6:]
			elif tip in (R_ANTET, R_SFARSIT):
				try:
					yield ("antet" if tip == R_ANTET else "sfarsit"), json.loads(c.decode("utf-8"))
				except ValueError:
					yield ("antet" if tip == R_ANTET else "sfarsit"), {}


def din_captura(cale, dosar, verifica_crc=True):
	"""Captura de pe receptor -> arborele in `dosar` si manifestul in dosar + ".json". -> manifestul."""
	antet, sfarsit = {}, {}
	car = Carusel(verifica_crc=verifica_crc)
	harta, ait = None, None
	pid_pmt = pid_ait = None
	momente = []
	for r in citeste_captura(cale):
		if r[0] == "antet":
			antet = r[1]
			pid_pmt, pid_ait = antet.get("pmt_pid"), antet.get("ait_pid")
		elif r[0] == "sfarsit":
			sfarsit = r[1]
		else:
			_t, ms, pid, s = r
			if s[:1] == b"\x02" and pid == pid_pmt:
				h = harta_pmt(s)
				if h is not None and (antet.get("sid") in (None, h["program"])):
					harta = h
			elif s[:1] == b"\x74" and pid == pid_ait:
				a = A.citeste_ait(s)
				if a is not None and ait is None:
					ait = a
			elif car.sectiune(s, pid):
				momente.append(ms)
	aplicatie = None
	for a in (ait or {}).get("aplicatii") or ():
		if transport_carusel(a) is not None and a.get("cod") in (0x01, 0x02):
			aplicatie = a
			break
	arb = car.arbore()
	scrise, erori = scrie_arbore(arb, dosar)
	extra = {"captura": os.path.basename(cale), "antet": antet, "sfarsit": sfarsit, "scrise": scrise,
		"erori_disc": erori, "schimbari_ms": momente[:64],
		"aplicatie": None if aplicatie is None else {"org": aplicatie["org"], "id": aplicatie["id"],
			"nume": aplicatie.get("nume"), "cale": aplicatie.get("cale"), "pid_dsi": pid_dsi(harta, aplicatie)[0]},
		"pmt": harta}
	m = manifest(car, arb, extra)
	scrie_json(dosar + ".json", m)
	return m


def main(argv=None):
	import argparse
	p = argparse.ArgumentParser(description="Arborele caruselului DSM-CC dintr-o captura de sectiuni")
	p.add_argument("captura")
	p.add_argument("dosar")
	p.add_argument("--fara-crc", action="store_true", help="nu verifica CRC-ul sectiunilor")
	a = p.parse_args(argv)
	try:
		sys.stdout.reconfigure(errors="replace")   # o consola care nu stie un caracter din nume nu opreste rezumatul
	except (AttributeError, ValueError):
		pass
	m = din_captura(a.captura, a.dosar, verifica_crc=not a.fara_crc)
	print("complet: %s, fisiere: %d, dosare: %d, fluxuri: %d" % (m["complet"], len(m["fisiere"]), len(m["dosare"]),
		len(m["fluxuri"])))
	print("module: %s" % ", ".join("%d v%d %s" % (x["id"], x["versiune"], x["blocuri"]) for x in m["module"]))
	if m["lipsa"]:
		print("lipsa: %s" % ", ".join(m["lipsa"]))
	for e in m["erori"][:20]:
		print("eroare: %s" % e)
	print("contoare: %s" % json.dumps(m["contoare"], sort_keys=True))
	return 0 if m["complet"] else 1


if __name__ == "__main__":
	sys.exit(main())
