# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAnalizaFlux.py: analiza fluxului unui serviciu fara imagine. Ce fel de date trimite (carusel DSM-CC de obiecte
# sau de date, actualizare de software SSU, date IP prin MPE, aplicatii AIT, ghidul programelor, teletext), pistele
# cu PID-ul si debitul fiecareia, modulele si fisierele caruselului (unde se pot citi), furnizorul si ce anunta
# tabelele SDT, NIT si AIT. Tot de aici: tipul pistei video pe care decodorul nu il cunoaste (AVS, AVS2, AVS3, VVC,
# AV1 si altele), pentru mesajul „format necunoscut” (Components/HdsEcranNegru.py).
#
# De ce din demux: nucleul (lib/dvb/pmt.cpp, eDVBServicePMTHandler::getProgramInfo) pastreaza numai pistele video,
# audio, subtitrarile, teletextul, PCR-ul si, pe canalul redat, AIT-ul HbbTV (Components/HdsHbbtv.py, cu aplicatiile
# in forma lui citeste_ait de aici); celelalte tipuri nu ajung in Python. Analiza citeste deci singura
# tabelele, cu filtre de sectiune pe demultiplexorul serviciului redat (acelasi fel de filtru ca eDVBSectionReader din
# lib/dvb/demux.cpp), iar la pistele PES numara octetii cu un filtru PES spre demux (DMX_OUT_TAP, ca eDVBPESReader).
# Nimic nu se scrie pe disc; rezultatul sta in memorie, pe referinta serviciului, PASTRAT_S secunde.
#
# Cand ruleaza: numai la cerere (OK pe mesajul de ecran negru, butonul din web) sau, cu config.usage.hds_analiza_flux
# pe „automat”, cand apare mesajul „Serviciu de date” sau „format necunoscut”. Un singur fir de lucru odata; la
# schimbarea canalului se opreste (filtrele se inchid in finally, cel tarziu dupa un pas de POLL_MS).
#
# Trei parti:
# - partea curata (fara enigma2, se probeaza pe PC): sectiunile si CRC-ul, textul DVB, PAT, PMT cu toate pistele si
#   descriptorii, SDT, NIT, AIT, DSM-CC (DSI, DII, DDB si mesajele BIOP ale caruselului de obiecte), MPE (antetele IP),
#   UNT; felurile de date si textele pentru televizor si web (sectiuni_text, pentru_verdict);
# - cititorul (Analiza): sarcini cu limite de timp, de octeti si de sectiuni, cel mult MAX_FILTRE filtre deschise
#   odata, pe un fir separat. Filtrele se deschid printr-o sursa: SursaDemux (Linux DVB) pe receptor, una falsa in
#   probe. Debitul unei piste = octetii cititi in fereastra de masura (aproximativ, cu antetele pachetelor TS
#   socotite); debitul intregii frecvente = contorul de pachete al portului tunerului (/proc/hisi/msp/demux_port,
#   numai HiSilicon), citit la inceputul si la sfarsitul analizei;
# - starea pentru ecran si web: porneste(), stare(), opreste(), rezultatul tinut minte.

import errno
import os
import struct
import threading
import time
import zlib

# ---------------------------------------------------------------- limitele

POLL_MS = 100              # un pas al buclei de citire; oprirea ceruta se vede cel tarziu dupa atat
TABEL_S = 3.0              # PAT, PMT, SDT: se repeta de cateva ori pe secunda sau la cel mult 2 s
NIT_S = 6.0                # NIT actual se repeta cel putin o data la 10 s; se asteapta cat merg celelalte
MASURA_S = 2.0             # fereastra de masura a unei piste
CARUSEL_S = 8.0            # un modul al caruselului (blocurile DDB vin intr-un ciclu de cateva secunde)
TOTAL_S = 30.0             # toata analiza
MAX_FILTRE = 4             # filtrele analizei deschise deodata, pe langa ale nucleului
MAX_PISTE = 24             # pistele din PMT masurate
MAX_OCTETI_PISTA = 4 * 1024 * 1024
MAX_SECTIUNI_PASTRATE = 64 # sectiuni pastrate pe pista pentru desfacere (tabelele mici)
MAX_MPE = 48               # datagrame MPE desfacute pe pista (pentru adrese)
MAX_CRC = 400              # sectiuni verificate cu CRC in Python pe o analiza
MAX_MODUL = 256 * 1024     # un modul al caruselului reasamblat (inainte de decomprimare)
MAX_MODUL_DESFACUT = 1024 * 1024
MAX_MODULE_CITITE = 6
MAX_CARUSEL_OCTETI = 1024 * 1024
MAX_FISIERE = 400
TAMPON_TABEL = 64 * 1024
TAMPON_MASURA = 512 * 1024
CITIRE = 65536
MAX_CITIRI = 2048           # citiri pe filtru intr-un pas (driverul poate da o singura sectiune la o citire)
CITIRE_S = 0.05            # timpul maxim de citire pe filtru intr-un pas
PASTRAT_S = 600.0          # rezultatul tinut minte pe serviciu
PROASPAT_S = 120.0         # la OK pe mesaj, un rezultat mai nou de atat se arata fara o analiza noua
FACTOR_TS = 188.0 / 184.0  # octetii sectiunilor / PES -> octetii pachetelor TS care ii poarta
MASURA_MIN_S = 0.05        # sub atat, o masura nu da debit (fereastra prea scurta)

ADAPTOR = 0
DEMUX = "/dev/dvb/adapter%d/demux%d"
HISI_MAIN = "/proc/hisi/msp/demux_main"
HISI_PORT = "/proc/hisi/msp/demux_port"

# ---------------------------------------------------------------- textele


def N_(text):
	"""Marcaj pentru xgettext, fara efect: textul se traduce la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


# felurile de date (cheia, textul); ordinea e cea din „Ce trimite”
K_OC, K_DC, K_SSU, K_MPE, K_INT, K_APP, K_MHEG, K_EPG, K_TTX, K_SUB, K_CA, K_FLUX, K_PRIV = (
	"oc", "dc", "ssu", "mpe", "int", "app", "mheg", "epg", "ttx", "sub", "ca", "flux", "priv")
K_VIDEO, K_VIDEO_NECUNOSCUT, K_AUDIO = "video", "video_necunoscut", "audio"
FELURI = {
	K_VIDEO_NECUNOSCUT: N_("Imagine într-un format necunoscut"),
	K_OC: N_("Carusel de obiecte (DSM-CC)"),
	K_DC: N_("Carusel de date (DSM-CC)"),
	K_SSU: N_("Actualizare de software (SSU)"),
	K_MPE: N_("Date IP (MPE)"),
	K_INT: N_("Anunțuri IP/MAC (INT)"),
	K_APP: N_("Aplicații interactive (AIT)"),
	K_MHEG: N_("Aplicații MHEG-5"),
	K_EPG: N_("Ghidul programelor (EIT)"),
	K_TTX: N_("Teletext"),
	K_SUB: N_("Subtitrări"),
	K_CA: N_("Mesaje pentru accesul condiționat"),
	K_FLUX: N_("Flux de date"),
	K_PRIV: N_("Date private"),
	K_VIDEO: N_("Imagine"),
	K_AUDIO: N_("Sunet"),
}
ORDINE_FELURI = (K_VIDEO_NECUNOSCUT, K_OC, K_DC, K_SSU, K_MPE, K_INT, K_APP, K_MHEG, K_EPG, K_TTX, K_SUB, K_CA, K_FLUX,
	K_PRIV, K_VIDEO, K_AUDIO)

T_TITLU = N_("Analiza fluxului")
T_CITESTE = N_("Se citește fluxul... %d / %d")
T_DUREAZA = N_("Analiza durează cel mult 30 de secunde. Schimbarea canalului o oprește.")
T_CITESTE_SCURT = N_("Se analizează fluxul...")
T_INDEMN = N_("Sus și jos derulează. OK sau EXIT închide.")
S_SCURT = N_("Pe scurt")
S_PISTE = N_("Piste")
S_APLICATII = N_("Aplicații")
S_CARUSEL = N_("Carusel")
S_SSU = N_("Actualizări de software")
S_IP = N_("Date IP")
S_RETEA = N_("Rețea și frecvență")
S_ERORI = N_("Nu s-a putut citi")
T_CE_TRIMITE = N_("Ce trimite: %s")
T_FURNIZOR = N_("Furnizor: %s")
T_TIP_SERVICIU = N_("Tipul serviciului: %s")
T_DEBIT_SERVICIU = N_("Debitul serviciului: %s (măsurat)")
T_DEBIT_FRECVENTA = N_("Debitul întregii frecvențe: %s")
T_ERORI_TS = N_("Pachete cu erori cât a durat analiza: %d")
T_CEL_PUTIN = N_("cel puțin %s")
T_TABELE = N_("tabele %s")
T_MODULE = N_("Module: %d, în total %s")
T_FISIERE = N_("Fișiere: %s")
T_NUME_MODULE = N_("Numele modulelor: %s")
T_SI_INCA = N_("și încă %d")
T_MODULE_CITITE = N_("Module citite: %d din %d.")
T_PORNESTE_SINGURA = N_("pornește singură")
T_LA_CERERE = N_("la cerere")
T_OPRITA = N_("nu rulează")
T_SSU_OUI = N_("OUI %s, modelul %s, versiunea %s")
T_SSU_VERSIUNE = N_("OUI %s, versiunea %s")
T_DESTINATII = N_("Destinații: %s")
T_CRIPTATE = N_("Datele sunt criptate.")
T_RETEA = N_("Rețeaua: %s")
T_TV = N_("Canale TV")
T_RADIO = N_("Posturi radio")
T_SERVICII_DATE = N_("Servicii de date")
T_ALTE = N_("Alte servicii")
T_FRECVENTE_NIT = N_("Frecvențe anunțate de rețea: %d")
T_LIPSA_TABEL = N_("Tabela %s nu a venit în %d s.")
T_FARA_DEMUX = N_("Demultiplexorul canalului nu se poate folosi.")
T_OPRITA_ZAP = N_("Analiza s-a oprit: s-a schimbat canalul.")
T_FARA_PISTE = N_("Canalul nu are piste în PMT.")
T_PISTA_VIDEO = N_("pista video %s: %s")
T_NICIO_ANALIZA = N_("Fluxul acestui canal nu a fost analizat încă.")

# ---------------------------------------------------------------- nume din standarde (ISO/IEC 13818-1, ETSI TS 101 162)

# stream_type -> (numele pistei, felul: "video" / "audio" / "sec" (sectiuni) / "pes" / "?" (privat: intai sectiunile,
# apoi PES)). Numele de codecuri raman cum sunt; cele care descriu (secțiuni, metadate...) se traduc (N_ / _t) cand se
# desface pista. Tipurile care lipsesc: „tip privat 0x..” de la 0x80 in sus, „tip necunoscut 0x..” sub 0x80.
STREAM_TYPES = {
	0x01: ("MPEG-1 video", "video"), 0x02: ("MPEG-2 video", "video"), 0x03: ("MPEG-1 audio", "audio"),
	0x04: ("MPEG-2 audio", "audio"), 0x05: (N_("secțiuni private"), "sec"), 0x06: (N_("date private (PES)"), "pes"),
	0x07: ("MHEG", "pes"), 0x08: ("DSM-CC", "pes"), 0x09: ("H.222.1", "pes"), 0x0A: ("DSM-CC A (MPE)", "sec"),
	0x0B: ("DSM-CC B (U-N)", "sec"), 0x0C: (N_("DSM-CC C (descriptori de flux)"), "sec"),
	0x0D: (N_("DSM-CC D (secțiuni)"), "sec"),
	0x0E: (N_("pistă auxiliară"), "pes"), 0x0F: ("AAC (ADTS)", "audio"), 0x10: ("MPEG-4 Visual", "video"),
	0x11: ("AAC (LATM)", "audio"), 0x12: ("MPEG-4 SL (PES)", "pes"), 0x13: (N_("MPEG-4 SL (secțiuni)"), "sec"),
	0x14: (N_("DSM-CC (descărcare sincronizată)"), "sec"), 0x15: (N_("metadate (PES)"), "pes"),
	0x16: (N_("metadate (secțiuni)"), "sec"),
	0x17: (N_("metadate (carusel de date)"), "sec"), 0x18: (N_("metadate (carusel de obiecte)"), "sec"),
	0x19: (N_("metadate (descărcare sincronizată)"), "sec"), 0x1A: ("IPMP", "pes"), 0x1B: ("H.264", "video"),
	0x1C: ("MPEG-4 audio", "audio"), 0x1D: (N_("text MPEG-4"), "pes"), 0x1E: (N_("video auxiliar MPEG-4"), "video"),
	0x1F: ("H.264 SVC", "video"), 0x20: ("H.264 MVC", "video"), 0x21: ("JPEG 2000", "video"),
	0x22: ("MPEG-2 3D video", "video"), 0x23: ("H.264 3D", "video"), 0x24: ("H.265 HEVC", "video"),
	0x25: (N_("H.265 HEVC (parte temporală)"), "video"), 0x26: ("H.264 MVCD", "video"),
	0x27: (N_("H.265 HEVC (strat de îmbunătățire)"), "video"), 0x28: (N_("H.265 HEVC (pe straturi)"), "video"),
	0x29: (N_("H.265 HEVC (pe straturi)"), "video"), 0x2A: (N_("H.265 HEVC (pe straturi)"), "video"),
	0x2B: (N_("H.265 HEVC (pe straturi)"), "video"), 0x2D: ("MPEG-H 3D audio", "audio"), 0x2E: ("MPEG-H 3D audio", "audio"),
	0x31: (N_("H.265 HEVC (subflux)"), "video"), 0x32: ("JPEG XS", "video"), 0x33: ("H.266 VVC", "video"),
	0x34: (N_("H.266 VVC (parte temporală)"), "video"), 0x35: ("EVC", "video"), 0x42: ("AVS", "video"),
	0x81: ("AC-3 (ATSC)", "audio"), 0x82: ("DTS", "audio"), 0x83: ("Dolby TrueHD", "audio"),
	0x84: ("E-AC-3", "audio"), 0x85: ("DTS-HD", "audio"), 0x86: ("SCTE-35 / DTS-HD", "?"), 0x87: ("E-AC-3 (ATSC)", "audio"),
	0xD1: ("Dirac", "video"), 0xD2: ("AVS2", "video"), 0xD4: ("AVS3", "video"), 0xEA: ("VC-1", "video"),
}
# pistele video pe care nucleul le da decodorului (lib/dvb/pmt.cpp: MPEG-1/2, MPEG-4 Part 2, H.264, H.265, AVS)
VIDEO_CUNOSCUT = (0x01, 0x02, 0x10, 0x1B, 0x24, 0x27, 0x42)
# registration_descriptor (0x05) pe o pista PES privata: format_identifier -> (nume, fel)
INREGISTRARI = {b"AV01": ("AV1", "video"), b"AVSV": ("AVS", "video"), b"AVS3": ("AVS3", "video"),
	b"VC-1": ("VC-1", "video"), b"HEVC": ("H.265 HEVC", "video"), b"AC-3": ("AC-3", "audio"),
	b"EAC3": ("E-AC-3", "audio"), b"DTS1": ("DTS", "audio"), b"DTS2": ("DTS", "audio"), b"DTS3": ("DTS", "audio"),
	b"Opus": ("Opus", "audio"), b"KLVA": (N_("metadate KLV"), "pes"), b"CUEI": ("SCTE-35", "sec")}
T_TIP_PRIVAT = N_("tip privat 0x%02X")
T_TIP_NECUNOSCUT = N_("tip necunoscut 0x%02X")

# data_broadcast_id (ETSI TS 101 162) -> felul
DATA_BROADCAST = {0x0001: K_FLUX, 0x0002: K_FLUX, 0x0003: K_FLUX, 0x0004: K_FLUX, 0x0005: K_MPE, 0x0006: K_DC,
	0x0007: K_OC, 0x0008: K_FLUX, 0x0009: K_FLUX, 0x000A: K_SSU, 0x000B: K_INT, 0x00F0: K_OC, 0x00F1: K_MPE,
	0x0106: K_MHEG, 0x0123: K_OC}

# application_type din AIT (ETSI TS 102 809)
APLICATII = {0x0001: "DVB-J (MHP)", 0x0002: "DVB-HTML (MHP)", 0x0010: "HbbTV"}


def nume_tabel(tid):
	"""Numele scurt al unui table_id (pentru detaliul tehnic al unei piste)."""
	nume = {0x00: "PAT", 0x01: "CAT", 0x02: "PMT", 0x3A: "DSM-CC MPE", 0x3B: "DSI/DII", 0x3C: "DDB", 0x3D: "DSM-CC SD",
		0x3E: "MPE", 0x3F: "DSM-CC", 0x40: "NIT", 0x41: "NIT", 0x42: "SDT", 0x46: "SDT", 0x4A: "BAT", 0x4B: "UNT",
		0x4C: "INT", 0x70: "TDT", 0x73: "TOT", 0x74: "AIT"}
	if tid in nume:
		return nume[tid]
	if 0x4E <= tid <= 0x6F:
		return "EIT"
	if 0x80 <= tid <= 0x8F:
		return "ECM/EMM"
	return "0x%02X" % tid


def fel_din_tabel(tid):
	"""Felul de date pe care il arata un table_id vazut pe o pista, sau None (caruselul se lamureste din DSI)."""
	if tid in (0x3A, 0x3E):
		return K_MPE
	if tid == 0x4B:
		return K_SSU
	if tid == 0x4C:
		return K_INT
	if tid == 0x74:
		return K_APP
	if 0x4E <= tid <= 0x6F:
		return K_EPG
	if 0x80 <= tid <= 0x8F:
		return K_CA
	if tid >= 0x90:
		return K_PRIV
	return None


# ---------------------------------------------------------------- texte venite din flux

def curat(text, n=120):
	"""Text din satelit: fara caractere de control, spatiile stranse, taiat la `n` litere cu „…” la capat."""
	try:
		t = text if isinstance(text, str) else str(text)
	except Exception:
		return u""
	t = u"".join(c if (c >= u" " and not (u"\x7f" <= c <= u"\x9f")) else u" " for c in t)
	t = u" ".join(t.split())
	if len(t) > n:
		t = t[:max(1, n - 1)].rstrip() + u"\u2026"
	return t


# ISO/IEC 6937: octetii 0xC1-0xCF sunt accentele puse INAINTEA literei
_ACCENTE_6937 = {0xC1: u"̀", 0xC2: u"́", 0xC3: u"̂", 0xC4: u"̃", 0xC5: u"̄", 0xC6: u"̆",
	0xC7: u"̇", 0xC8: u"̈", 0xCA: u"̊", 0xCB: u"̧", 0xCD: u"̋", 0xCE: u"̨", 0xCF: u"̌"}
_ISO8859 = {0x01: "iso8859-5", 0x02: "iso8859-6", 0x03: "iso8859-7", 0x04: "iso8859-8", 0x05: "iso8859-9",
	0x06: "iso8859-10", 0x07: "iso8859-11", 0x09: "iso8859-13", 0x0A: "iso8859-14", 0x0B: "iso8859-15"}
_ALTE = {0x11: "utf-16-be", 0x12: "euc-kr", 0x13: "gb2312", 0x14: "big5", 0x15: "utf-8"}


def _din_6937(b):
	import unicodedata
	rez = []
	i = 0
	while i < len(b):
		c = b[i]
		if c in _ACCENTE_6937 and i + 1 < len(b) and 0x41 <= b[i + 1] <= 0x7A:
			rez.append(unicodedata.normalize("NFC", chr(b[i + 1]) + _ACCENTE_6937[c]))
			i += 2
			continue
		rez.append(chr(c))
		i += 1
	return u"".join(rez)


def text_dvb(b, n=120):
	"""Un sir DVB (ETSI EN 300 468, anexa A) -> text: primul octet < 0x20 alege setul de caractere; implicit ISO 6937.
	Codurile de control 0x80-0x9F (accentuare, rand nou) se scot."""
	b = bytes(b or b"")
	if not b:
		return u""
	c = b[0]
	try:
		if c >= 0x20:
			t = _din_6937(b)
		elif c in _ISO8859:
			t = b[1:].decode(_ISO8859[c], "replace")
		elif c == 0x10 and len(b) >= 3:
			tabel = b[2]
			t = b[3:].decode("iso8859-%d" % tabel, "replace") if 1 <= tabel <= 15 and tabel != 12 else b[3:].decode("latin-1")
		elif c in _ALTE:
			t = b[1:].decode(_ALTE[c], "replace")
			if c == 0x11:
				t = u"".join(x for x in t if not (u"" <= x <= u""))
		elif c == 0x1F:
			t = _din_6937(b[2:])
		else:
			t = _din_6937(b[1:])
	except Exception:
		t = b.decode("latin-1", "replace")
	return curat(t, n)


# ---------------------------------------------------------------- sectiunile

def _crc_tabel():
	tabel = []
	for i in range(256):
		c = i << 24
		for _k in range(8):
			c = ((c << 1) ^ 0x04C11DB7) if c & 0x80000000 else (c << 1)
		tabel.append(c & 0xFFFFFFFF)
	return tabel


_CRC = _crc_tabel()


def crc32_mpeg(date):
	"""CRC-32/MPEG-2 (polinomul 0x04C11DB7, pornit din 0xFFFFFFFF); peste o sectiune cu CRC-ul ei da 0."""
	c = 0xFFFFFFFF
	for b in bytearray(date):
		c = ((c << 8) & 0xFFFFFFFF) ^ _CRC[((c >> 24) ^ b) & 0xFF]
	return c


def sectiune(date, crc=True):
	"""Octetii unei sectiuni -> sectiunea (taiata la lungimea ei) sau None. Cu crc=True, o sectiune cu
	section_syntax_indicator trebuie sa aiba CRC-ul bun."""
	b = bytes(date or b"")
	if len(b) < 3:
		return None
	lungime = ((b[1] & 0x0F) << 8) | b[2]
	if 3 + lungime > len(b):
		return None
	s = b[:3 + lungime]
	if b[1] & 0x80:
		if lungime < 9:
			return None
		if crc and crc32_mpeg(s) != 0:
			return None
	return s


def imparte(buf, rest=b""):
	"""Octetii cititi dintr-un filtru de sectiune -> (sectiunile intregi, restul pentru citirea urmatoare). Driverul
	poate da mai multe sectiuni la o citire; umplutura (0xFF) incheie."""
	b = rest + bytes(buf or b"")
	sectiuni = []
	i = 0
	while i + 3 <= len(b):
		if b[i] == 0xFF:
			return sectiuni, b""
		n = ((b[i + 1] & 0x0F) << 8) | b[i + 2]
		if i + 3 + n > len(b):
			break
		sectiuni.append(b[i:i + 3 + n])
		i += 3 + n
	rest = b[i:]
	return sectiuni, (rest if len(rest) <= 4096 else b"")


def antet(s):
	"""(table_id, table_id_extension, versiunea, section_number, last_section_number) al unei sectiuni lungi."""
	return s[0], (s[3] << 8) | s[4], (s[5] >> 1) & 0x1F, s[6], s[7]


def _u16(b, i):
	return (b[i] << 8) | b[i + 1]


def _u32(b, i):
	return (b[i] << 24) | (b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3]


def descriptori(b, i, sfarsit):
	"""Descriptorii dintre i si sfarsit: [(tag, continut)]; unul taiat incheie lista."""
	rez = []
	sfarsit = min(sfarsit, len(b))
	while i + 2 <= sfarsit:
		tag, n = b[i], b[i + 1]
		if i + 2 + n > sfarsit:
			break
		rez.append((tag, bytes(b[i + 2:i + 2 + n])))
		i += 2 + n
	return rez


# ---------------------------------------------------------------- PAT, PMT, SDT, NIT

def citeste_pat(s):
	"""-> {"tsid", "programe": {program: PID PMT}, "nit": PID NIT sau None}, sau None."""
	s = sectiune(s)
	if s is None or s[0] != 0x00 or len(s) < 12:
		return None
	programe, nit = {}, None
	i, sfarsit = 8, len(s) - 4
	while i + 4 <= sfarsit:
		program, pid = _u16(s, i), _u16(s, i + 2) & 0x1FFF
		if program:
			programe[program] = pid
		else:
			nit = pid
		i += 4
	return {"tsid": _u16(s, 3), "programe": programe, "nit": nit}


def desfa_pista(tip, pid, d):
	"""Pista din PMT (stream_type, PID, descriptorii) -> dictionar simplu: numele tipului, felul, ce spun
	descriptorii (data_broadcast_id, SSU, AIT, teletext, subtitrari, limba, component_tag, formatul inregistrat)."""
	nume, fel = STREAM_TYPES.get(tip, (None, "?"))
	nume = _t(nume) if nume else _t(T_TIP_PRIVAT if tip >= 0x80 else T_TIP_NECUNOSCUT) % tip
	p = {"pid": pid, "stream_type": tip, "tip_text": nume, "fel_pes": fel, "felul": None, "limba": u"",
		"component_tag": None, "data_broadcast": None, "ssu": [], "ait": False, "carusel_id": None, "inregistrare": u""}
	for tag, c in d:
		if tag == 0x05 and len(c) >= 4:
			p["inregistrare"] = curat(c[:4].decode("latin-1"), 8)
			if tip == 0x06 or tip >= 0x80:
				nou = INREGISTRARI.get(bytes(c[:4]))
				# 'AVSV' e inregistrarea comuna a generatiilor AVS: generatia o spune stream_type (0xD2 AVS2, 0xD4 AVS3)
				if nou and bytes(c[:4]) == b"AVSV" and tip in (0xD2, 0xD4):
					nou = None
				if nou:
					p["tip_text"], p["fel_pes"] = _t(nou[0]), nou[1]
		elif tag == 0x0A and len(c) >= 3:
			p["limba"] = curat(c[:3].decode("latin-1"), 3)
		elif tag == 0x13 and len(c) >= 4:
			p["carusel_id"] = _u32(c, 0)
		elif tag == 0x52 and len(c) >= 1:
			p["component_tag"] = c[0]
		elif tag in (0x46, 0x56):
			p["felul"] = K_TTX
			p["fel_pes"] = "pes"
		elif tag == 0x59:
			p["felul"] = K_SUB
			p["fel_pes"] = "pes"
		elif tag == 0x6F:
			p["ait"] = True
		elif tag in (0x6A, 0x7A, 0x7B, 0x7C) and tip == 0x06:
			p["tip_text"] = {0x6A: "AC-3", 0x7A: "E-AC-3", 0x7B: "DTS", 0x7C: "AAC"}[tag]
			p["fel_pes"] = "audio"
		elif tag == 0x66 and len(c) >= 2:
			p["data_broadcast"] = _u16(c, 0)
			if p["data_broadcast"] == 0x000A:
				p["ssu"] = _ssu_din_selector(c[2:])
	if p["felul"] is None:
		if p["fel_pes"] == "video":
			p["felul"] = K_VIDEO if tip in VIDEO_CUNOSCUT else K_VIDEO_NECUNOSCUT
		elif p["fel_pes"] == "audio":
			p["felul"] = K_AUDIO
	if p["ait"]:
		p["felul"] = K_APP
	if p["data_broadcast"] is not None and p["felul"] is None:
		p["felul"] = DATA_BROADCAST.get(p["data_broadcast"], K_FLUX)
	return p


def _oui_text(oui):
	return u"%02X-%02X-%02X" % ((oui >> 16) & 0xFF, (oui >> 8) & 0xFF, oui & 0xFF)


def _ssu_din_selector(c):
	"""selector_byte-ii data_broadcast_id 0x000A (ETSI TS 102 006, 7.1): [{"oui", "versiune"}]."""
	rez = []
	if not c:
		return rez
	i, sfarsit = 1, min(len(c), 1 + c[0])
	while i + 6 <= sfarsit and len(rez) < 8:
		oui = (c[i] << 16) | (c[i + 1] << 8) | c[i + 2]
		versiune = (c[i + 4] & 0x1F) if c[i + 4] & 0x20 else None
		rez.append({"oui": _oui_text(oui), "versiune": versiune})
		i += 6 + c[i + 5]
	return rez


def citeste_pmt(s):
	"""-> {"program", "pcr", "piste": [pista desfacuta]}, sau None."""
	s = sectiune(s)
	if s is None or s[0] != 0x02 or len(s) < 16:
		return None
	n = ((s[10] & 0x0F) << 8) | s[11]
	sfarsit = len(s) - 4
	i = 12 + n
	piste = []
	while i + 5 <= sfarsit and len(piste) < 64:
		tip, pid = s[i], _u16(s, i + 1) & 0x1FFF
		n = ((s[i + 3] & 0x0F) << 8) | s[i + 4]
		piste.append(desfa_pista(tip, pid, descriptori(s, i + 5, min(i + 5 + n, sfarsit))))
		i += 5 + n
	return {"program": _u16(s, 3), "pcr": _u16(s, 8) & 0x1FFF, "piste": piste}


def citeste_sdt(s):
	"""-> {"tsid", "onid", "servicii": {sid: {"nume", "furnizor", "tip"}}}, sau None."""
	s = sectiune(s)
	if s is None or s[0] not in (0x42, 0x46) or len(s) < 15:
		return None
	servicii = {}
	i, sfarsit = 11, len(s) - 4
	while i + 5 <= sfarsit:
		sid = _u16(s, i)
		n = ((s[i + 3] & 0x0F) << 8) | s[i + 4]
		rec = {"nume": u"", "furnizor": u"", "tip": None}
		for tag, c in descriptori(s, i + 5, min(i + 5 + n, sfarsit)):
			if tag == 0x48 and len(c) >= 2:
				rec["tip"] = c[0]
				np = c[1]
				rec["furnizor"] = text_dvb(c[2:2 + np], 60)
				j = 2 + np
				if j < len(c):
					rec["nume"] = text_dvb(c[j + 1:j + 1 + c[j]], 60)
		servicii[sid] = rec
		i += 5 + n
	return {"tsid": _u16(s, 3), "onid": _u16(s, 8), "servicii": servicii}


def citeste_nit(s):
	"""-> {"retea_id", "nume", "frecvente": numarul transponderelor, "ssu": [{"oui"}]}, sau None."""
	s = sectiune(s)
	if s is None or s[0] not in (0x40, 0x41) or len(s) < 16:
		return None
	sfarsit = len(s) - 4
	n = ((s[8] & 0x0F) << 8) | s[9]
	rez = {"retea_id": _u16(s, 3), "nume": u"", "frecvente": 0, "ssu": []}
	for tag, c in descriptori(s, 10, min(10 + n, sfarsit)):
		if tag == 0x40:
			rez["nume"] = text_dvb(c, 60)
		elif tag == 0x4A:
			rez["ssu"].extend(_ssu_din_legatura(c))
	i = 10 + n
	if i + 2 > sfarsit:
		return rez
	lungime = ((s[i] & 0x0F) << 8) | s[i + 1]
	i += 2
	capat = min(sfarsit, i + lungime)
	while i + 6 <= capat:
		rez["frecvente"] += 1
		n = ((s[i + 4] & 0x0F) << 8) | s[i + 5]
		for tag, c in descriptori(s, i + 6, min(i + 6 + n, capat)):
			if tag == 0x4A:
				rez["ssu"].extend(_ssu_din_legatura(c))
		i += 6 + n
	return rez


def _ssu_din_legatura(c):
	"""linkage_descriptor cu linkage_type 0x09 (serviciul de actualizare a software-ului): [{"oui"}]."""
	if len(c) < 8 or c[6] != 0x09:
		return []
	i, sfarsit, rez = 8, min(len(c), 8 + c[7]), []
	while i + 4 <= sfarsit and len(rez) < 8:
		oui = (c[i] << 16) | (c[i + 1] << 8) | c[i + 2]
		rez.append({"oui": _oui_text(oui), "versiune": None})
		i += 4 + c[i + 3]
	return rez


# ---------------------------------------------------------------- AIT (ETSI TS 102 809)
# Aceleasi reguli ca nucleul (lib/dvb/hdsait.cpp), ca aplicatiile sa iasa la fel pe ambele drumuri
# (Components/HdsHbbtv.din_nucleu): o bucla sau un descriptor care trece de capatul lui strica sectiunea intreaga
# (None); un camp gresit inauntrul unui descriptor strica numai descriptorul (la nume si adrese, restul lui).

AIT_MAX_APLICATII = 64
AIT_MAX_TRANSPORTURI = 8
AIT_MAX_ADRESE = 4
AIT_MAX_EXTENSII = 8
AIT_MAX_PROFILE = 8
AIT_MAX_ETICHETE = 16
AIT_MAX_LIMITE = 8
AIT_MAX_VARSTE = 8
PROTOCOL_CARUSEL, PROTOCOL_IP, PROTOCOL_HTTP = 0x0001, 0x0002, 0x0003


def _descriptori_stricti(b, i, capat):
	"""Ca descriptori(), dar None cand unul trece de capat."""
	rez = []
	while i < capat:
		if i + 2 > capat:
			return None
		n = b[i + 1]
		if i + 2 + n > capat:
			return None
		rez.append((b[i], bytes(b[i + 2:i + 2 + n])))
		i += 2 + n
	return rez


def _text_ait(octeti, n):
	return curat(bytes(octeti).decode("latin-1"), n)


def ait_transport(c):
	"""Continutul unui transport_protocol_descriptor (0x02) -> {"protocol", "eticheta", "la_distanta", "onid", "tsid",
	"sid", "tag", "adrese", "extensii"} (adresele ca octeti), sau None cand selectorul nu se poate citi deloc."""
	if len(c) < 3:
		return None
	t = {"protocol": _u16(c, 0), "eticheta": c[2], "la_distanta": 0, "onid": 0, "tsid": 0, "sid": 0, "tag": -1,
		"adrese": [], "extensii": []}
	s = c[3:]
	n = len(s)
	if t["protocol"] == PROTOCOL_CARUSEL:
		if n < 1:
			return None
		if s[0] & 0x80:
			if n < 8:
				return None
			t.update(la_distanta=1, onid=_u16(s, 1), tsid=_u16(s, 3), sid=_u16(s, 5), tag=s[7])
		else:
			if n < 2:
				return None
			t["tag"] = s[1]
		return t
	if t["protocol"] == PROTOCOL_HTTP:
		q, prima = 0, True
		while q < n and len(t["adrese"]) < AIT_MAX_ADRESE:
			lb = s[q]
			if q + 1 + lb > n:
				break
			baza = s[q + 1:q + 1 + lb]
			q += 1 + lb
			if lb:
				t["adrese"].append(baza)
			if q >= n:
				break
			ext = s[q]
			q += 1
			taiat = False
			for _k in range(ext):
				if q >= n:
					taiat = True
					break
				le = s[q]
				if q + 1 + le > n:
					taiat = True
					break
				if prima and lb and len(t["extensii"]) < AIT_MAX_EXTENSII:
					t["extensii"].append(s[q + 1:q + 1 + le])
				q += 1 + le
			if lb:
				prima = False
			if taiat:
				break
		return t if t["adrese"] else None
	return t


def _descriptor_aplicatie(c, a):
	"""application_descriptor (0x00) -> True daca s-a putut citi (atunci profilele, vizibilitatea, prioritatea si
	etichetele intra in a)."""
	if len(c) < 1:
		return False
	p = c[0]
	if p % 5 or 1 + p + 2 > len(c):
		return False
	for q in range(1, 1 + p, 5):
		if len(a["profile"]) >= AIT_MAX_PROFILE:
			break
		a["profile"].append([_u16(c, q), c[q + 2], c[q + 3], c[q + 4]])
	f = c[1 + p]
	a["legat"], a["vizibilitate"], a["prioritate"] = (f >> 7) & 1, (f >> 5) & 3, c[2 + p]
	a["etichete"] = list(c[3 + p:3 + p + AIT_MAX_ETICHETE])
	return True


def _nume_aplicatie(c):
	"""Primul nume din application_name_descriptor (0x01) -> (limba, octetii numelui), sau None."""
	if len(c) < 4 or 4 + c[3] > len(c):
		return None
	return c[:3], c[4:4 + c[3]]


def _limite(c):
	rez = []
	if not c:
		return rez
	q = 1
	for _k in range(c[0]):
		if len(rez) >= AIT_MAX_LIMITE or q >= len(c) or q + 1 + c[q] > len(c):
			break
		rez.append(c[q + 1:q + 1 + c[q]])
		q += 1 + c[q]
	return rez


def ait_aplicatie(org, app, cod, proprii, comuni):
	"""O aplicatie din descriptorii ei si din cei comuni -> dictionarul aplicatiei, cu textele ca octeti (aceeasi forma
	ca dictionarul nucleului, lib/dvb/pmt.cpp getHbbtvInfo); ait_text() le face texte."""
	a = {"org": org, "id": app, "cod": cod, "prioritate": -1, "vizibilitate": -1, "legat": -1, "profile": [],
		"etichete": [], "nume": b"", "limba": b"", "transporturi": [], "cale": b"", "utilizare": -1, "limite": [],
		"varste": []}
	are_descriptor = are_nume = are_cale = False
	tp, tc = [], []
	for tag, c in proprii:
		if tag == 0x00:
			if not are_descriptor:
				are_descriptor = _descriptor_aplicatie(c, a)
		elif tag == 0x01:
			if not are_nume:
				n = _nume_aplicatie(c)
				if n is not None:
					a["limba"], a["nume"] = n
					are_nume = True
		elif tag == 0x02:
			t = ait_transport(c)
			if t is not None:
				tp.append(t)
		elif tag == 0x15:
			if not are_cale:
				a["cale"], are_cale = c, True
		elif tag == 0x16:
			if a["utilizare"] < 0 and len(c) >= 1:
				a["utilizare"] = c[0]
		elif tag == 0x17:
			for x in _limite(c):
				if len(a["limite"]) < AIT_MAX_LIMITE:
					a["limite"].append(x)
		elif tag == 0x55:
			for q in range(0, len(c) - 3, 4):
				if len(a["varste"]) < AIT_MAX_VARSTE:
					a["varste"].append([c[q:q + 3], c[q + 3]])
	for tag, c in comuni:
		if tag == 0x02:
			t = ait_transport(c)
			if t is not None:
				tc.append(t)
		elif tag == 0x01 and not are_nume:
			n = _nume_aplicatie(c)
			if n is not None:
				a["limba"], a["nume"] = n
				are_nume = True
		elif tag == 0x15 and not are_cale:
			a["cale"], are_cale = c, True
	# transporturile in ordinea etichetelor: intai cel din bucla aplicatiei, apoi cel comun cu aceeasi eticheta
	for i, e in enumerate(a["etichete"]):
		if len(a["transporturi"]) >= AIT_MAX_TRANSPORTURI:
			break
		if e in a["etichete"][:i]:
			continue
		t = next((x for x in tp if x["eticheta"] == e), None) or next((x for x in tc if x["eticheta"] == e), None)
		if t is not None:
			a["transporturi"].append(t)
	if not a["transporturi"]:
		a["transporturi"] = list(tp or tc)[:AIT_MAX_TRANSPORTURI]
	return a


def ait_text(a):
	"""Dictionarul unei aplicatii cu textele ca octeti (ait_aplicatie, nucleul) -> acelasi dictionar cu texte, plus
	"adresa" = prima adresa HTTP, dupa ordinea transporturilor (sau "")."""
	rez = dict(a)
	rez["nume"] = text_dvb(bytes(a.get("nume") or b""), 60)
	rez["limba"] = _text_ait(a.get("limba") or b"", 3).lower()
	# adresele si caile se folosesc la pornirea aplicatiei: niciodata taiate (un camp are cel mult 255 de octeti)
	rez["cale"] = _text_ait(a.get("cale") or b"", 255)
	rez["limite"] = [_text_ait(x, 255) for x in a.get("limite") or ()]
	rez["varste"] = [[_text_ait(x[0], 3), x[1]] for x in a.get("varste") or ()]
	transporturi = []
	for t in a.get("transporturi") or ():
		t = dict(t)
		t["adrese"] = [_text_ait(x, 255) for x in t.get("adrese") or ()]
		t["extensii"] = [_text_ait(x, 255) for x in t.get("extensii") or ()]
		transporturi.append(t)
	rez["transporturi"] = transporturi
	rez["adresa"] = next((t["adrese"][0] for t in transporturi if t["protocol"] == PROTOCOL_HTTP and t["adrese"]), u"")
	return rez


def citeste_ait(s):
	"""-> {"tip", "test", "versiune", "sectiune", "ultima", "aplicatii": [aplicatia ca la ait_text: "org", "id", "cod",
	"nume", "limba", "adresa", "cale", "prioritate", "vizibilitate", "legat", "profile", "etichete", "transporturi",
	"utilizare", "limite", "varste"]}, sau None (sectiune stricata, CRC gresit, current_next_indicator 0)."""
	s = sectiune(s)
	if s is None or s[0] != 0x74 or len(s) < 16 or not (s[1] & 0x80) or not (s[5] & 0x01):
		return None
	sfarsit = len(s) - 4
	n = ((s[8] & 0x0F) << 8) | s[9]
	if 10 + n + 2 > sfarsit:
		return None
	comuni = _descriptori_stricti(s, 10, 10 + n)
	if comuni is None:
		return None
	i = 10 + n
	lungime = ((s[i] & 0x0F) << 8) | s[i + 1]
	i += 2
	capat = i + lungime
	if capat > sfarsit:
		return None
	aplicatii = []
	while i < capat:
		if i + 9 > capat:
			return None
		n = ((s[i + 7] & 0x0F) << 8) | s[i + 8]
		if i + 9 + n > capat:
			return None
		proprii = _descriptori_stricti(s, i + 9, i + 9 + n)
		if proprii is None:
			return None
		if len(aplicatii) < AIT_MAX_APLICATII:
			aplicatii.append(ait_text(ait_aplicatie(_u32(s, i), _u16(s, i + 4), s[i + 6], proprii, comuni)))
		i += 9 + n
	return {"tip": _u16(s, 3) & 0x7FFF, "test": s[3] >> 7, "versiune": (s[5] >> 1) & 0x1F, "sectiune": s[6],
		"ultima": s[7], "aplicatii": aplicatii}


# ---------------------------------------------------------------- DSM-CC (ISO/IEC 13818-6, ETSI EN 301 192, TR 101 202)

MSG_DII, MSG_DSI, MSG_DDB = 0x1002, 0x1006, 0x1003
TAG_BIOP, TAG_LOCATIE = 0x49534F06, 0x49534F50
FELURI_DOSAR = ("dir", "srg", "DSM::Directory", "DSM::ServiceGateway")


def mesaj_dsmcc(s):
	"""Sectiunea 0x3B / 0x3C -> (messageId, transactionId / downloadId, inceputul corpului, sfarsitul), sau None."""
	if len(s) < 8 + 12 + 4:
		return None
	i = 8
	if s[i] != 0x11 or s[i + 1] != 0x03:
		return None
	msg, tid32 = _u16(s, i + 2), _u32(s, i + 4)
	adaptare, lungime = s[i + 9], _u16(s, i + 10)
	corp = i + 12 + adaptare
	sfarsit = min(len(s) - 4, i + 12 + lungime)
	if corp > sfarsit:
		return None
	return msg, tid32, corp, sfarsit


def citeste_ior(b, i, sfarsit):
	"""IOP::IOR -> ({"fel", "carusel", "modul", "cheie"}, pozitia de dupa), sau (None, sfarsit)."""
	if i + 4 > sfarsit:
		return None, sfarsit
	n = _u32(b, i)
	i += 4
	if n > 64 or i + n > sfarsit:
		return None, sfarsit
	fel = bytes(b[i:i + n]).split(b"\0")[0].decode("latin-1")
	i += n + ((4 - n % 4) % 4)
	if i + 4 > sfarsit:
		return None, sfarsit
	profile = _u32(b, i)
	i += 4
	rez = {"fel": fel, "carusel": None, "modul": None, "cheie": b""}
	for _k in range(min(profile, 8)):
		if i + 8 > sfarsit:
			break
		tag, lungime = _u32(b, i), _u32(b, i + 4)
		i += 8
		capat = min(sfarsit, i + lungime)
		if tag == TAG_BIOP and i + 2 <= capat:
			j = i + 2
			for _c in range(b[i + 1]):
				if j + 5 > capat:
					break
				ctag, clung = _u32(b, j), b[j + 4]
				j += 5
				if ctag == TAG_LOCATIE and j + 9 <= capat:
					rez["carusel"], rez["modul"] = _u32(b, j), _u16(b, j + 4)
					kl = b[j + 8]
					rez["cheie"] = bytes(b[j + 9:j + 9 + kl])
				j += clung
		i = capat
	return rez, i


def citeste_dsi(s):
	"""DSI -> {"fel": K_OC, "srg": locatia portii} (carusel de obiecte) sau {"fel": K_DC, "grupuri": [...]} (carusel de
	date sau SSU), sau None."""
	m = mesaj_dsmcc(s)
	if m is None or m[0] != MSG_DSI:
		return None
	_msg, _tid, i, sfarsit = m
	i += 20                                        # serverId
	if i + 2 > sfarsit:
		return None
	i += 2 + _u16(s, i)                            # compatibilityDescriptor
	if i + 2 > sfarsit:
		return None
	n = _u16(s, i)
	i += 2
	capat = min(sfarsit, i + n)
	if capat - i >= 8:
		lung_tip = _u32(s, i)
		tip = bytes(s[i + 4:i + 4 + min(lung_tip, 32)])
		if lung_tip <= 32 and (tip.startswith(b"srg") or tip.startswith(b"DSM::ServiceGateway")):
			ior, _j = citeste_ior(s, i, capat)
			return {"fel": K_OC, "srg": ior}
	return {"fel": K_DC, "grupuri": _grupuri(s, i, capat)}


def _grupuri(b, i, sfarsit):
	"""GroupInfoIndication (EN 301 192, 8.1.1): [{"id", "marime", "oui", "model", "versiune", "nume"}]."""
	if i + 2 > sfarsit:
		return []
	n = _u16(b, i)
	i += 2
	rez = []
	for _k in range(min(n, 32)):
		if i + 10 > sfarsit:
			break
		g = {"id": _u32(b, i), "marime": _u32(b, i + 4), "oui": None, "model": None, "versiune": None, "nume": u""}
		i += 8
		lung = _u16(b, i)
		j, capat = i + 2, min(sfarsit, i + 2 + lung)
		if lung >= 2:
			nd = _u16(b, j)
			j += 2
			for _d in range(min(nd, 16)):
				if j + 2 > capat:
					break
				dl = b[j + 1]
				c = b[j + 2:j + 2 + dl]
				if len(c) >= 8 and c[0] == 0x01 and g["oui"] is None:
					g["oui"] = _oui_text((c[1] << 16) | (c[2] << 8) | c[3])
					g["model"], g["versiune"] = _u16(c, 4), _u16(c, 6)
				j += 2 + dl
		i = min(sfarsit, i + 2 + lung)
		if i + 2 > sfarsit:
			rez.append(g)
			break
		gl = _u16(b, i)
		for tag, c in descriptori(b, i + 2, min(sfarsit, i + 2 + gl)):
			if tag == 0x02 and not g["nume"]:
				g["nume"] = text_dvb(c, 60)
		i = min(sfarsit, i + 2 + gl)
		rez.append(g)
	return rez


def citeste_dii(s):
	"""DII -> {"descarcare", "bloc", "module": [{"id", "marime", "versiune", "nume", "comprimat", "tag"}]}, sau None."""
	m = mesaj_dsmcc(s)
	if m is None or m[0] != MSG_DII:
		return None
	_msg, _tid, i, sfarsit = m
	if i + 18 > sfarsit:
		return None
	rez = {"descarcare": _u32(s, i), "bloc": _u16(s, i + 4), "module": []}
	i += 16
	i += 2 + _u16(s, i)                            # compatibilityDescriptor
	if i + 2 > sfarsit:
		return rez
	n = _u16(s, i)
	i += 2
	for _k in range(min(n, 512)):
		if i + 8 > sfarsit:
			break
		mod = {"id": _u16(s, i), "marime": _u32(s, i + 2), "versiune": s[i + 6], "nume": u"", "comprimat": False,
			"tag": None}
		lung = s[i + 7]
		_info_modul(mod, bytes(s[i + 8:min(sfarsit, i + 8 + lung)]))
		rez["module"].append(mod)
		i += 8 + lung
	return rez


def _info_modul(mod, info):
	"""moduleInfo: BIOP::ModuleInfo (carusel de obiecte, TR 101 202) sau descriptori (carusel de date, EN 301 192)."""
	if len(info) >= 13:
		taps = []
		j = 13
		for _k in range(min(info[12], 8)):
			if j + 7 > len(info):
				break
			taps.append((_u16(info, j + 2), _u16(info, j + 4)))
			j += 7 + info[j + 6]
		obiecte = [tag for use, tag in taps if use == 0x0017]
		if obiecte and j < len(info):
			mod["tag"] = obiecte[0]
			for tag, c in descriptori(info, j + 1, min(len(info), j + 1 + info[j])):
				if tag == 0x09 and len(c) >= 1:
					mod["comprimat"] = True
			return
	for tag, c in descriptori(info, 0, len(info)):
		if tag == 0x02 and not mod["nume"]:
			mod["nume"] = text_dvb(c, 60)
		elif tag == 0x09 and len(c) >= 1:
			mod["comprimat"] = True


def citeste_ddb(s):
	"""DDB -> (downloadId, moduleId, versiunea, blockNumber, datele), sau None."""
	m = mesaj_dsmcc(s)
	if m is None or m[0] != MSG_DDB:
		return None
	_msg, descarcare, i, sfarsit = m
	if i + 6 > sfarsit:
		return None
	return descarcare, _u16(s, i), s[i + 2], _u16(s, i + 4), bytes(s[i + 6:sfarsit])


def mesaje_biop(date, maxim=MAX_FISIERE):
	"""Mesajele BIOP dintr-un modul -> [{"cheie", "fel", "legaturi": [{"nume", "fel", "modul", "cheie"}]}]."""
	rez = []
	i, n = 0, len(date)
	while i + 12 <= n and len(rez) < maxim:
		if date[i:i + 4] != b"BIOP":
			break
		capat = i + 12 + _u32(date, i + 8)
		if capat > n:
			break
		try:
			rez.append(_mesaj_biop(date, i + 12, capat))
		except (IndexError, ValueError):
			break
		i = capat
	return rez


def _mesaj_biop(b, j, capat):
	kl = b[j]
	cheie = bytes(b[j + 1:j + 1 + kl])
	j += 1 + kl
	fl = _u32(b, j)
	if fl > 32:
		raise ValueError("objectKind")
	fel = bytes(b[j + 4:j + 4 + fl]).split(b"\0")[0].decode("latin-1")
	j += 4 + fl
	j += 2 + _u16(b, j)                            # objectInfo
	for _k in range(b[j]):                         # serviceContextList
		j += 4
		j += 2 + _u16(b, j)
	j += 1
	corp = _u32(b, j)
	j += 4
	sfarsit = min(capat, j + corp)
	m = {"cheie": cheie, "fel": fel, "legaturi": []}
	if fel in FELURI_DOSAR and j + 2 <= sfarsit:
		m["legaturi"] = _legaturi(b, j, sfarsit)
	return m


def _legaturi(b, j, sfarsit):
	n = _u16(b, j)
	j += 2
	rez = []
	for _k in range(min(n, MAX_FISIERE)):
		if j + 1 > sfarsit:
			break
		nume, fel = [], u""
		componente = b[j]
		j += 1
		for _c in range(componente):
			il = b[j]
			nume.append(curat(bytes(b[j + 1:j + 1 + il]).split(b"\0")[0].decode("utf-8", "replace"), 60))
			j += 1 + il
			kl = b[j]
			fel = bytes(b[j + 1:j + 1 + kl]).split(b"\0")[0].decode("latin-1")
			j += 1 + kl
		j += 1                                     # bindingType
		ior, j = citeste_ior(b, j, sfarsit)
		if j + 2 > sfarsit:
			break
		j += 2 + _u16(b, j)                        # objectInfo al legaturii
		rez.append({"nume": u"/".join(x for x in nume if x), "fel": fel, "modul": (ior or {}).get("modul"),
			"cheie": (ior or {}).get("cheie") or b""})
	return rez


def arbore_fisiere(mesaje, srg_cheie=None, maxim=MAX_FISIERE):
	"""Mesajele BIOP citite (mesaje: [(moduleId, mesaj)]) -> caile fisierelor si dosarelor, pornind din poarta
	serviciului (srg). Un dosar al carui modul nu s-a citit apare numai cu „/” la sfarsit."""
	dupa_cheie = {}
	srg = None
	for modul, m in mesaje:
		dupa_cheie[(modul, m["cheie"])] = m
		if m["fel"] in ("srg", "DSM::ServiceGateway") and (srg is None or m["cheie"] == srg_cheie):
			srg = m
	if srg is None:
		return []
	cai, coada, vazute = [], [(u"", srg)], set()
	while coada and len(cai) < maxim:
		prefix, m = coada.pop(0)
		for leg in m["legaturi"]:
			cale = prefix + leg["nume"]
			if leg["fel"] in ("dir", "DSM::Directory"):
				cai.append(cale + u"/")
				cheie = (leg["modul"], leg["cheie"])
				urm = dupa_cheie.get(cheie)
				if urm is not None and cheie not in vazute:
					vazute.add(cheie)
					coada.append((cale + u"/", urm))
			else:
				cai.append(cale)
			if len(cai) >= maxim:
				break
	return cai


# ---------------------------------------------------------------- MPE si UNT

def citeste_mpe(s):
	"""datagram_section (EN 301 192, 7.1) -> {"criptat", "ip": (sursa, destinatia, protocolul, portul) sau None}."""
	b = bytes(s or b"")
	if len(b) < 12 or b[0] != 0x3E:
		return None
	criptat = bool(b[5] & 0x30)
	llc = bool(b[5] & 0x02)
	i = 12 + (8 if llc else 0)
	sfarsit = len(b) - 4
	if criptat or i + 20 > sfarsit:
		return {"criptat": criptat, "ip": None}
	v = b[i] >> 4
	if v == 4:
		ihl = (b[i] & 0x0F) * 4
		if ihl < 20 or i + ihl > sfarsit or not _suma_ip_buna(b[i:i + ihl]):
			return {"criptat": False, "ip": None}
		proto = b[i + 9]
		src = u".".join(str(x) for x in b[i + 12:i + 16])
		dst = u".".join(str(x) for x in b[i + 16:i + 20])
		port = _u16(b, i + ihl + 2) if proto in (6, 17) and i + ihl + 4 <= sfarsit else None
		return {"criptat": False, "ip": (src, dst, proto, port)}
	if v == 6 and i + 40 <= sfarsit:
		proto = b[i + 6]
		dst = u":".join(u"%x" % _u16(b, i + 24 + 2 * k) for k in range(8))
		src = u":".join(u"%x" % _u16(b, i + 8 + 2 * k) for k in range(8))
		port = _u16(b, i + 42) if proto in (6, 17) and i + 44 <= sfarsit else None
		return {"criptat": False, "ip": (src, dst, proto, port)}
	return {"criptat": False, "ip": None}


def _suma_ip_buna(h):
	suma = 0
	for k in range(0, len(h) - 1, 2):
		suma += (h[k] << 8) | h[k + 1]
	while suma >> 16:
		suma = (suma & 0xFFFF) + (suma >> 16)
	return suma == 0xFFFF


def citeste_unt(s):
	"""Update Notification Table (ETSI TS 102 006, 9.4) -> {"oui", "platforme"}, sau None."""
	s = sectiune(s)
	if s is None or s[0] != 0x4B or len(s) < 18:
		return None
	oui = (s[8] << 16) | (s[9] << 8) | s[10]
	sfarsit = len(s) - 4
	i = 12
	if i + 2 <= sfarsit:
		i += 2 + (((s[i] & 0x0F) << 8) | s[i + 1])
	platforme = 0
	while i + 4 <= sfarsit and platforme < 64:
		i += 2 + (((s[i] & 0x0F) << 8) | s[i + 1])
		if i + 2 > sfarsit:
			break
		i += 2 + (((s[i] & 0x0F) << 8) | s[i + 1])
		platforme += 1
	return {"oui": _oui_text(oui), "platforme": platforme}


# ---------------------------------------------------------------- debitul intregii frecvente (HiSilicon)

def port_din_main(text, demux):
	"""/proc/hisi/msp/demux_main -> (PortId-ul demuxului, TEICnt, CCDiscCnt), sau None."""
	for rand in (text or u"").splitlines():
		p = rand.split()
		if len(p) >= 4 and p[0] == str(demux):
			try:
				return int(p[1]), int(p[2]), int(p[3])
			except ValueError:
				return None
	return None


def pachete_din_port(text, port):
	"""/proc/hisi/msp/demux_port -> (AllTsCnt, ErrTsCnt) al portului, sau None."""
	for rand in (text or u"").splitlines():
		p = rand.split()
		if len(p) >= 3 and p[0] == str(port):
			try:
				return int(p[1], 16), int(p[2], 16)
			except ValueError:
				continue
	return None


def diferenta32(a, b):
	"""b - a pe un contor de 32 de biti care se poate intoarce la zero."""
	return (b - a) & 0xFFFFFFFF


class ContorFrecventa(object):
	"""Contorul de pachete al portului tunerului, citit la inceput si la sfarsit (fara filtru deschis)."""

	def __init__(self, demux, citeste=None, ceas=None):
		self.demux = demux
		self.citeste = citeste or _citeste_proc
		self.ceas = ceas or _monoton
		self.inceput = self._proba()

	def _proba(self):
		m = port_din_main(self.citeste(HISI_MAIN), self.demux)
		if m is None:
			return None
		p = pachete_din_port(self.citeste(HISI_PORT), m[0])
		if p is None:
			return None
		return self.ceas(), p[0], p[1], m[1] + m[2]

	def rezultat(self):
		"""(debitul in biti/s, pachete cu erori in timpul analizei), sau (None, None)."""
		sfarsit = self._proba()
		if self.inceput is None or sfarsit is None:
			return None, None
		dt = sfarsit[0] - self.inceput[0]
		if dt < 0.5:
			return None, None
		pachete = diferenta32(self.inceput[1], sfarsit[1])
		erori = diferenta32(self.inceput[2], sfarsit[2]) + max(0, sfarsit[3] - self.inceput[3])
		return pachete * 188.0 * 8.0 / dt, erori


def _procFundal(functie, *argumente):
	# fisierele driverului (/proc/msp, /proc/hisi), citite de pe firul principal: prin firul de fundal
	# (Components/HdsProcFundal.py); fara modul (probele de pe PC), direct
	try:
		from Components import HdsProcFundal
	except Exception:
		return functie(*argumente)
	return HdsProcFundal.citeste(functie, *argumente)


def _citeste_proc_direct(cale):
	try:
		with open(cale, "rb") as f:
			return f.read(16384).decode("latin-1")
	except (IOError, OSError):
		return None


def _citeste_proc(cale):
	"""Ca _citeste_proc_direct; fisierele driverului (/proc/msp, /proc/hisi) le citeste pe firul de fundal."""
	return _procFundal(_citeste_proc_direct, cale)


def _monoton():
	try:
		return time.monotonic()
	except AttributeError:
		return time.time()


# ---------------------------------------------------------------- sursa: Linux DVB (linux/dvb/dmx.h)

DMX_STOP = 0x6F2A                  # _IO('o', 42)
DMX_SET_FILTER = 0x403C6F2B        # _IOW('o', 43, struct dmx_sct_filter_params), 60 de octeti
DMX_SET_PES_FILTER = 0x40146F2C    # _IOW('o', 44, struct dmx_pes_filter_params), 20 de octeti
DMX_SET_BUFFER_SIZE = 0x6F2D       # _IO('o', 45)
DMX_CHECK_CRC = 1
DMX_IMMEDIATE_START = 4
DMX_IN_FRONTEND = 0
DMX_OUT_TAP = 1
DMX_PES_OTHER = 20
FILTRU_SECTIUNE = struct.Struct("@H16s16s16sII")
FILTRU_PES = struct.Struct("=H2xIIII")


def structura_sectiune(pid, tid=None, ext=None, crc=False):
	"""struct dmx_sct_filter_params: octetul 0 al filtrului = table_id, 1-2 = table_id_extension (octetii 3-4 ai
	sectiunii; driverul sare peste lungime, ca eDVBTableSpec). Fara tid: toate sectiunile PID-ului."""
	filtru, masca = bytearray(16), bytearray(16)
	if tid is not None:
		filtru[0], masca[0] = tid & 0xFF, 0xFF
	if ext is not None:
		filtru[1], filtru[2] = (ext >> 8) & 0xFF, ext & 0xFF
		masca[1] = masca[2] = 0xFF
	flags = DMX_IMMEDIATE_START | (DMX_CHECK_CRC if crc else 0)
	return FILTRU_SECTIUNE.pack(pid & 0x1FFF, bytes(filtru), bytes(masca), bytes(16), 0, flags)


def structura_pes(pid):
	return FILTRU_PES.pack(pid & 0x1FFF, DMX_IN_FRONTEND, DMX_OUT_TAP, DMX_PES_OTHER, DMX_IMMEDIATE_START)


class SursaDemux(object):
	"""Filtrele analizei pe /dev/dvb/adapterA/demuxD, deschise fara blocare; `os_`, `fcntl_`, `select_` se dau in
	probe."""

	def __init__(self, demux, adaptor=ADAPTOR, os_=None, fcntl_=None, select_=None):
		self.cale = DEMUX % (adaptor, demux)
		self.os = os_ or os
		if fcntl_ is None:
			import fcntl as fcntl_
		if select_ is None:
			import select as select_
		self.fcntl = fcntl_
		self.select = select_

	def _deschide(self, tampon, structura, comanda):
		fd = self.os.open(self.cale, self.os.O_RDWR | getattr(self.os, "O_NONBLOCK", 0))
		try:
			try:
				self.fcntl.ioctl(fd, DMX_SET_BUFFER_SIZE, tampon)
			except (IOError, OSError):
				pass
			self.fcntl.ioctl(fd, comanda, structura)
		except Exception:
			self.os.close(fd)
			raise
		return fd

	def sectiuni(self, pid, tid=None, ext=None, crc=False, tampon=TAMPON_TABEL):
		return self._deschide(tampon, structura_sectiune(pid, tid, ext, crc), DMX_SET_FILTER)

	def pes(self, pid, tampon=TAMPON_MASURA):
		return self._deschide(tampon, structura_pes(pid), DMX_SET_PES_FILTER)

	def asteapta(self, fds, ms):
		if not fds:
			time.sleep(ms / 1000.0)
			return []
		p = self.select.poll()
		for fd in fds:
			p.register(fd, self.select.POLLIN)
		try:
			return [fd for fd, _ev in p.poll(ms)]
		except (IOError, OSError):
			return []

	def citeste(self, fd, n=CITIRE):
		"""Octetii cititi; None cand nu e nimic; b"" dupa o depasire a tamponului (EOVERFLOW)."""
		try:
			return self.os.read(fd, n)
		except (IOError, OSError) as e:
			if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
				return None
			if e.errno == errno.EOVERFLOW:
				return b""
			raise

	def inchide(self, fd):
		try:
			self.fcntl.ioctl(fd, DMX_STOP)
		except Exception:
			pass
		try:
			self.os.close(fd)
		except OSError:
			pass


# ---------------------------------------------------------------- sarcinile cititorului

class Sarcina(object):
	"""Un filtru deschis de analiza: ce citeste, pana cand, si ce face cu octetii."""
	fel = "sectiuni"
	tid = None
	ext = None
	crc = False
	tampon = TAMPON_TABEL

	def __init__(self, pid, limita_s):
		self.pid = pid
		self.limita_s = limita_s
		self.gata = False
		self.octeti = 0
		self.depasiri = 0
		self.inceput = None
		self.sfarsit = None
		self.rest = b""

	def primeste(self, buf, analiza):
		if buf == b"":
			self.depasiri += 1
			self.rest = b""
			return
		self.octeti += len(buf)
		if self.fel != "sectiuni":
			return
		sectiuni, self.rest = imparte(buf, self.rest)
		for s in sectiuni:
			if self.gata:
				break
			self.sectiune(s, analiza)

	def sectiune(self, s, analiza):
		pass

	def incheie(self, analiza, expirat):
		pass


class SarcinaTabel(Sarcina):
	"""Un tabel intreg (toate sectiunile unei versiuni a unui (table_id, extensie))."""
	crc = True

	def __init__(self, pid, tid, ext, limita_s, la_gata):
		Sarcina.__init__(self, pid, limita_s)
		self.tid, self.ext = tid, ext
		self.la_gata = la_gata
		self.sectiuni = {}
		self.cheie = None

	def sectiune(self, s, analiza):
		s = analiza.verifica(s)
		if s is None or len(s) < 12 or s[0] != self.tid:
			return
		_tid, ext, ver, nr, ultim = antet(s)
		if self.ext is not None and ext != self.ext:
			return
		if self.cheie is None:
			self.cheie = (ext, ver)
		if (ext, ver) != self.cheie:
			return
		self.sectiuni[nr] = s
		if all(k in self.sectiuni for k in range(ultim + 1)):
			self.gata = True

	def incheie(self, analiza, expirat):
		lista = [self.sectiuni[k] for k in sorted(self.sectiuni)]
		self.la_gata(lista, self)


class SarcinaMasura(Sarcina):
	"""O pista din PMT: octetii in fereastra de masura, table_id-urile vazute, cateva sectiuni pastrate pentru
	desfacere (DSI/DII, AIT, UNT) si antetele datagramelor MPE."""
	tampon = TAMPON_MASURA

	def __init__(self, pista, fel, limita_s):
		Sarcina.__init__(self, pista["pid"], limita_s)
		self.pista = pista
		self.fel = fel
		self.tabele = set()
		self.pastrate = {}
		self.mpe = []

	def sectiune(self, s, analiza):
		if len(s) < 3:
			return
		tid = s[0]
		self.tabele.add(tid)
		if tid == 0x3E:
			if len(self.mpe) < MAX_MPE:
				m = citeste_mpe(s)
				if m is not None:
					self.mpe.append(m)
			return
		if tid not in (0x3B, 0x4B, 0x74) or len(self.pastrate) >= MAX_SECTIUNI_PASTRATE or len(s) < 12:
			return
		cheie = (tid,) + antet(s)[1:]
		if cheie not in self.pastrate:
			s = analiza.verifica(s)
			if s is not None:
				self.pastrate[cheie] = s

	def primeste(self, buf, analiza):
		Sarcina.primeste(self, buf, analiza)
		if self.octeti >= MAX_OCTETI_PISTA:
			self.gata = True

	def incheie(self, analiza, expirat):
		analiza.laMasura(self)


class SarcinaModul(Sarcina):
	"""Blocurile DDB ale unui modul al caruselului, pana e intreg."""
	tid = 0x3C
	crc = True

	def __init__(self, pid, descarcare, modul, bloc, limita_s):
		Sarcina.__init__(self, pid, limita_s)
		self.ext = modul["id"]
		self.descarcare = descarcare
		self.modul = modul
		self.bloc = max(1, bloc)
		self.blocuri = {}
		self.n = max(1, (modul["marime"] + self.bloc - 1) // self.bloc)
		self.memorie = 0

	def sectiune(self, s, analiza):
		d = citeste_ddb(s)
		if d is None:
			return
		descarcare, modul, versiune, nr, date = d
		if descarcare != self.descarcare or modul != self.modul["id"] or versiune != self.modul["versiune"]:
			return
		if nr in self.blocuri or nr >= self.n:
			return
		self.memorie += len(date)
		if self.memorie > MAX_MODUL:
			self.gata = True
			return
		self.blocuri[nr] = date
		if len(self.blocuri) == self.n:
			self.gata = True

	def date(self):
		if len(self.blocuri) != self.n:
			return None
		b = b"".join(self.blocuri[k] for k in range(self.n))[:self.modul["marime"]]
		if self.modul.get("comprimat"):
			try:
				b = zlib.decompressobj().decompress(b, MAX_MODUL_DESFACUT)
			except zlib.error:
				return None
		return b

	def incheie(self, analiza, expirat):
		analiza.laModul(self)


# ---------------------------------------------------------------- analiza (pe firul ei)

class Analiza(object):
	"""O analiza a serviciului redat. Parametrii vin de pe firul enigma2 (numere simple); porneste() lanseaza firul;
	progres() si rezultat() se citesc de pe orice fir."""

	def __init__(self, param, sursa, ceas=None, contor=None):
		self.p = dict(param)
		self.sursa = sursa
		self.ceas = ceas or _monoton
		self.contor = contor
		self.oprit = threading.Event()
		self.zavor = threading.Lock()
		self.coada = []
		self.active = {}
		self.facute = 0
		self.stiute = 0
		self.crc_facute = 0
		self.date = {"pat": None, "pmt": None, "sdt": None, "nit": None, "piste": {}, "dsi": [], "dii": [],
			"ait": [], "unt": [], "module": [], "biop": [], "lipsa": [], "eroare": None}
		self.module_programate = set()
		self._rezultat = None
		self.fir = None

	# ---- firul

	def porneste(self):
		self.fir = threading.Thread(target=self.ruleaza, name="HdsAnalizaFlux")
		self.fir.daemon = True
		self.fir.start()

	def opreste(self):
		self.oprit.set()

	def ruleaza(self):
		try:
			self._ruleaza()
		except Exception as e:
			self.date["eroare"] = "%s: %s" % (type(e).__name__, e)
			print("[HdsAnalizaFlux] %s" % self.date["eroare"])
		finally:
			# filtrele ramase deschise (limita TOTAL_S, oprire, eroare) se inchid; ce au adunat pana acum intra in
			# rezultat (incheie), iar tabelele fara nicio sectiune apar la „lipsa”
			acum = self.ceas()
			for fd, s in list(self.active.items()):
				try:
					self._inchide(fd, s, acum)
				except Exception as e:
					print("[HdsAnalizaFlux] inchidere PID %d: %s" % (s.pid, e))
			for fd in list(self.active):
				self.sursa.inchide(fd)
			self.active = {}
		rez = self._construieste()
		with self.zavor:
			self._rezultat = rez

	def _ruleaza(self):
		inceput = self.ceas()
		sid = self.p.get("sid")
		self.adauga(SarcinaTabel(0x0000, 0x00, None, TABEL_S, self._laPat))
		if (self.p.get("pmt_pid") or -1) > 0:
			self.adauga(SarcinaTabel(self.p["pmt_pid"], 0x02, sid, TABEL_S, self._laPmt))
		self.adauga(SarcinaTabel(0x0011, 0x42, self.p.get("tsid"), TABEL_S, self._laSdt))
		self.adauga(SarcinaTabel(0x0010, 0x40, None, NIT_S, self._laNit))
		while not self.oprit.is_set():
			acum = self.ceas()
			if acum - inceput >= TOTAL_S:
				break
			while self.coada and len(self.active) < MAX_FILTRE and not self.oprit.is_set():
				self._deschide(self.coada.pop(0), acum)
			if not self.active and not self.coada:
				break
			pregatite = self.sursa.asteapta(list(self.active), POLL_MS)
			for fd in pregatite:
				s = self.active.get(fd)
				if s is None:
					continue
				limita = self.ceas() + CITIRE_S
				for _k in range(MAX_CITIRI):
					try:
						buf = self.sursa.citeste(fd)
					except Exception as e:
						print("[HdsAnalizaFlux] PID %d: %s" % (s.pid, e))
						s.gata = True
						break
					if buf is None:
						break
					s.primeste(buf, self)
					if s.gata or self.ceas() >= limita:
						break
			acum = self.ceas()
			for fd, s in list(self.active.items()):
				if s.gata or acum - s.inceput >= s.limita_s:
					self._inchide(fd, s, acum)

	def _deschide(self, s, acum):
		try:
			if s.fel == "pes":
				fd = self.sursa.pes(s.pid, s.tampon)
			else:
				fd = self.sursa.sectiuni(s.pid, s.tid, s.ext, s.crc, s.tampon)
		except Exception as e:
			print("[HdsAnalizaFlux] filtrul PID %d: %s" % (s.pid, e))
			if not self.facute and not self.active:
				# primul filtru nu se deschide: demultiplexorul nu se poate folosi deloc
				self.date["eroare"] = _t(T_FARA_DEMUX)
				self.oprit.set()
				return
			self.facute += 1
			s.inceput = s.sfarsit = acum
			try:
				s.incheie(self, True)
			except Exception as e2:
				print("[HdsAnalizaFlux] PID %d: %s" % (s.pid, e2))
			return
		s.inceput = acum
		self.active[fd] = s

	def _inchide(self, fd, s, acum):
		del self.active[fd]
		self.sursa.inchide(fd)
		s.sfarsit = acum
		self.facute += 1
		try:
			s.incheie(self, not s.gata)
		except Exception as e:
			print("[HdsAnalizaFlux] PID %d: %s: %s" % (s.pid, type(e).__name__, e))

	def adauga(self, s, primul=False):
		if primul:
			self.coada.insert(0, s)
		else:
			self.coada.append(s)
		self.stiute += 1

	def verifica(self, s):
		"""CRC-ul in Python numai pentru sectiunile mici si numai de MAX_CRC ori pe analiza."""
		if len(s) > 4096 or self.crc_facute >= MAX_CRC:
			return sectiune(s, crc=False)
		self.crc_facute += 1
		return sectiune(s, crc=True)

	def progres(self):
		"""(facute, stiute): filtrele incheiate si cele stiute pana acum."""
		return self.facute, max(self.stiute, 1)

	def rezultat(self):
		with self.zavor:
			return self._rezultat

	# ---- tabelele

	def _laPat(self, sectiuni, s):
		for x in sectiuni:
			pat = citeste_pat(x)
			if pat:
				if self.date["pat"] is None:
					self.date["pat"] = pat
				else:
					self.date["pat"]["programe"].update(pat["programe"])
		if not sectiuni:
			self.date["lipsa"].append(("PAT", TABEL_S))
		if (self.p.get("pmt_pid") or -1) <= 0:
			pid = ((self.date["pat"] or {}).get("programe") or {}).get(self.p.get("sid"))
			if pid:
				self.p["pmt_pid"] = pid
				self.adauga(SarcinaTabel(pid, 0x02, self.p.get("sid"), TABEL_S, self._laPmt), primul=True)

	def _laPmt(self, sectiuni, s):
		pmt = None
		for x in sectiuni:
			pmt = citeste_pmt(x) or pmt
		if pmt is None:
			self.date["lipsa"].append(("PMT", TABEL_S))
			return
		self.date["pmt"] = pmt
		for p in pmt["piste"][:MAX_PISTE]:
			self.date["piste"][p["pid"]] = {"pista": p, "octeti": 0, "durata": 0.0, "depasiri": 0, "tabele": [],
				"mpe": [], "fel_citit": None}
			fel = "pes" if p["fel_pes"] in ("pes", "video", "audio") else "sectiuni"
			self.adauga(SarcinaMasura(p, fel, MASURA_S))

	def _laSdt(self, sectiuni, s):
		for x in sectiuni:
			sdt = citeste_sdt(x)
			if sdt:
				if self.date["sdt"] is None:
					self.date["sdt"] = sdt
				else:
					self.date["sdt"]["servicii"].update(sdt["servicii"])
		if not sectiuni:
			self.date["lipsa"].append(("SDT", TABEL_S))

	def _laNit(self, sectiuni, s):
		for x in sectiuni:
			nit = citeste_nit(x)
			if nit:
				if self.date["nit"] is None:
					self.date["nit"] = nit
				else:
					self.date["nit"]["frecvente"] += nit["frecvente"]
					self.date["nit"]["ssu"].extend(nit["ssu"])
		if not sectiuni:
			self.date["lipsa"].append(("NIT", NIT_S))

	# ---- pistele

	def laMasura(self, s):
		rec = self.date["piste"].get(s.pid)
		if rec is None:
			return
		rec["octeti"] += s.octeti
		rec["durata"] += max(0.0, (s.sfarsit or 0) - (s.inceput or 0))
		rec["depasiri"] += s.depasiri
		rec["tabele"] = sorted(set(rec["tabele"]) | s.tabele)
		rec["mpe"].extend(s.mpe)
		if s.octeti:
			rec["fel_citit"] = s.fel
		elif s.fel == "sectiuni" and s.pista["fel_pes"] == "?":
			# pista privata fara sectiuni: poate fi PES; o a doua masura, cu filtru PES
			self.adauga(SarcinaMasura(s.pista, "pes", MASURA_S))
		for cheie in sorted(s.pastrate):
			tid, sec = cheie[0], s.pastrate[cheie]
			if tid == 0x3B:
				self._laUN(sec, s.pid)
			elif tid == 0x74:
				a = citeste_ait(sec)
				if a:
					a["pid"] = s.pid
					self.date["ait"].append(a)
			elif tid == 0x4B:
				u = citeste_unt(sec)
				if u:
					self.date["unt"].append(u)

	def _laUN(self, s, pid):
		dsi = citeste_dsi(s)
		if dsi is not None:
			dsi["pid"] = pid
			if not any(x["pid"] == pid and x["fel"] == dsi["fel"] for x in self.date["dsi"]):
				self.date["dsi"].append(dsi)
			self._programeazaModule()
			return
		dii = citeste_dii(s)
		if dii is not None:
			dii["pid"] = pid
			if not any(x["pid"] == pid and x["descarcare"] == dii["descarcare"] and x["module"] == dii["module"]
					for x in self.date["dii"]):
				self.date["dii"].append(dii)
			self._programeazaModule()

	# ---- caruselul de obiecte: modulul portii (srg), apoi modulele dosarelor

	def _pidDupaTag(self, tag, implicit):
		pmt = self.date["pmt"] or {}
		for p in pmt.get("piste", []):
			if tag is not None and p.get("component_tag") == tag:
				return p["pid"]
		return implicit

	def _programeazaModule(self, dorite=None):
		"""Modulele de citit: al portii serviciului din DSI, apoi (dorite) ale dosarelor gasite in el."""
		tinte = []
		for dsi in self.date["dsi"]:
			srg = dsi.get("srg") if dsi["fel"] == K_OC else None
			if srg and srg.get("modul") is not None:
				tinte.append((srg.get("carusel"), srg["modul"]))
		tinte.extend(dorite or [])
		memorie = sum(m["modul"]["marime"] for m in self.date["module"])
		for carusel, modul_id in tinte:
			for dii in self.date["dii"]:
				if carusel is not None and dii["descarcare"] != carusel:
					continue
				for mod in dii["module"]:
					cheie = (dii["descarcare"], mod["id"], mod["versiune"])
					if mod["id"] != modul_id or cheie in self.module_programate:
						continue
					if mod["marime"] > MAX_MODUL or memorie + mod["marime"] > MAX_CARUSEL_OCTETI:
						continue
					if len(self.module_programate) >= MAX_MODULE_CITITE:
						return
					self.module_programate.add(cheie)
					memorie += mod["marime"]
					pid = self._pidDupaTag(mod.get("tag"), dii["pid"])
					self.adauga(SarcinaModul(pid, dii["descarcare"], mod, dii["bloc"], CARUSEL_S))

	def laModul(self, s):
		date = s.date()
		self.date["module"].append({"modul": s.modul, "citit": date is not None})
		if date is None:
			return
		noi = []
		for m in mesaje_biop(date):
			self.date["biop"].append((s.modul["id"], m))
			for leg in m["legaturi"]:
				if leg["fel"] in ("dir", "DSM::Directory") and leg["modul"] is not None:
					noi.append((s.descarcare, leg["modul"]))
		if noi:
			self._programeazaModule(noi)

	# ---- rezultatul

	def _construieste(self):
		try:
			frecventa = self.contor.rezultat() if self.contor is not None else (None, None)
		except Exception:
			frecventa = (None, None)
		try:
			return construieste(self.date, self.p, frecventa, self.oprit.is_set() and self.p.get("oprita_de_zap"))
		except Exception as e:
			print("[HdsAnalizaFlux] rezultatul: %s: %s" % (type(e).__name__, e))
			return {"stare": "eroare", "eroare": str(e), "feluri": [], "piste": [], "timp": time.time(),
				"ref": self.p.get("ref"), "canal": self.p.get("canal") or u""}


def _categorie(tip):
	if tip in (0x01, 0x11, 0x16, 0x19, 0x1F, 0x20, 0x86):
		return "tv"
	if tip in (0x02, 0x0A):
		return "radio"
	if tip in (0x0C, 0x10):
		return "date"
	return "alte"


def _felul_pistei(pista, rec, dsi):
	felul = pista.get("felul")
	tabele = rec["tabele"]
	if felul is None or felul in (K_FLUX, K_PRIV):
		for tid in tabele:
			f = fel_din_tabel(tid)
			if f is not None and f != K_PRIV:
				return f
	if felul is None and any(t in (0x3B, 0x3C) for t in tabele):
		return dsi[0]["fel"] if dsi else K_DC
	if felul is None and (tabele or rec["octeti"]):
		return K_PRIV
	return felul


def alege_actualizari(surse):
	"""Actualizarile de software aflate din mai multe locuri (PMT, DSI, UNT, NIT) -> un rand pe producator (OUI), cel
	mai bogat: cu modelul si versiunea din DSI cand exista, altfel cu versiunea anuntata in PMT, altfel numai OUI-ul."""
	pe_oui = {}
	ordine = []
	for x in surse:
		oui = x.get("oui")
		if not oui:
			continue
		if oui not in pe_oui:
			pe_oui[oui] = []
			ordine.append(oui)
		pe_oui[oui].append(x)
	rez = []
	for oui in ordine:
		lista = pe_oui[oui]
		alese = [x for x in lista if x.get("model") is not None]
		if not alese:
			alese = [x for x in lista if x.get("versiune") is not None][:1] or lista[:1]
		vazute = set()
		for x in alese:
			cheie = (x.get("model"), x.get("versiune"))
			if cheie not in vazute:
				vazute.add(cheie)
				rez.append({"oui": oui, "model": x.get("model"), "versiune": x.get("versiune")})
	return rez


def construieste(d, p, frecventa=(None, None), oprita=False):
	"""Datele culese -> rezultatul analizei (numai tipuri simple, pentru ecran si JSON)."""
	piste, feluri = [], []
	debit_total, debit_stiut = 0.0, False
	for pid in sorted(d["piste"]):
		rec = d["piste"][pid]
		pista = rec["pista"]
		felul = _felul_pistei(pista, rec, [x for x in d["dsi"] if x["pid"] == pid])
		debit = None
		if rec["durata"] >= MASURA_MIN_S and rec["octeti"]:
			debit = rec["octeti"] * 8.0 * FACTOR_TS / rec["durata"]
			debit_total += debit
			debit_stiut = True
		piste.append({"pid": pid, "stream_type": pista["stream_type"], "tip_text": pista["tip_text"],
			"felul": felul, "debit": debit, "cel_putin": rec["depasiri"] > 0, "tabele": rec["tabele"],
			"limba": pista.get("limba") or u"", "inregistrare": pista.get("inregistrare") or u"",
			"data_broadcast": pista.get("data_broadcast")})
		if felul and felul not in feluri:
			feluri.append(felul)
	sdt = d.get("sdt") or {}
	serviciu = (sdt.get("servicii") or {}).get(p.get("sid")) or {}
	numarate = {"tv": 0, "radio": 0, "date": 0, "alte": 0}
	for sv in (sdt.get("servicii") or {}).values():
		numarate[_categorie(sv.get("tip"))] += 1
	aplicatii = []
	for a in d["ait"]:
		for x in a["aplicatii"]:
			adresa = x["adresa"] + (x["cale"] if x["adresa"] and x["cale"] else u"")
			aplicatii.append({"nume": x["nume"], "tip": APLICATII.get(a["tip"], u"0x%04X" % a["tip"]), "cod": x["cod"],
				"adresa": curat(adresa, 200)})
	carusele = []
	for dsi in d["dsi"]:
		srg = dsi.get("srg") or {}
		c = {"pid": dsi["pid"], "fel": dsi["fel"], "module": 0, "marime": 0, "nume_module": [], "fisiere": [],
			"citite": 0, "de_citit": 0, "grupuri": []}
		for dii in d["dii"]:
			if dsi["fel"] == K_OC and srg.get("carusel") is not None:
				if dii["descarcare"] != srg["carusel"]:
					continue
			elif dii["pid"] != dsi["pid"]:
				continue
			c["module"] += len(dii["module"])
			c["marime"] += sum(m["marime"] for m in dii["module"])
			c["nume_module"].extend(m["nume"] for m in dii["module"] if m["nume"])
		if dsi["fel"] == K_OC:
			c["fisiere"] = arbore_fisiere(d["biop"], srg.get("cheie"))
			c["citite"] = sum(1 for m in d["module"] if m["citit"])
			c["de_citit"] = len(d["module"])
		else:
			c["grupuri"] = [{"oui": g["oui"], "model": g["model"], "versiune": g["versiune"], "marime": g["marime"],
				"nume": g["nume"]} for g in dsi.get("grupuri", [])]
		carusele.append(c)
	surse_ssu = [x for pid in sorted(d["piste"]) for x in d["piste"][pid]["pista"].get("ssu", [])]
	surse_ssu += [g for c in carusele for g in c["grupuri"] if g["oui"]]
	surse_ssu += [{"oui": u["oui"]} for u in d["unt"]]
	surse_ssu += list((d.get("nit") or {}).get("ssu") or [])
	actualizari = alege_actualizari(surse_ssu)
	if K_SSU not in feluri and any(g["oui"] for c in carusele for g in c["grupuri"]):
		feluri.append(K_SSU)
	feluri.sort(key=lambda f: ORDINE_FELURI.index(f) if f in ORDINE_FELURI else 99)
	ip = []
	for pid in sorted(d["piste"]):
		mpe = d["piste"][pid]["mpe"]
		if not mpe:
			continue
		dest = {}
		for m in mpe:
			if m.get("ip"):
				_src, dst, proto, port = m["ip"]
				k = (dst, port, proto)
				dest[k] = dest.get(k, 0) + 1
		ip.append({"pid": pid, "criptat": any(m.get("criptat") for m in mpe),
			"destinatii": [{"adresa": a, "port": pt, "protocol": {6: "TCP", 17: "UDP"}.get(pr, str(pr)), "numar": n}
				for (a, pt, pr), n in sorted(dest.items(), key=lambda x: (-x[1], x[0][0]))[:8]]})
	nit = d.get("nit") or {}
	video_necunoscut = [{"pid": x["pid"], "codec": x["tip_text"], "stream_type": x["stream_type"]}
		for x in piste if x["felul"] == K_VIDEO_NECUNOSCUT]
	if oprita:
		stare = "oprita"
	elif d.get("eroare") and not piste:
		stare = "eroare"
	else:
		stare = "gata"
	return {
		"stare": stare,
		"eroare": d.get("eroare"),
		"ref": p.get("ref"), "canal": p.get("canal") or u"", "timp": time.time(),
		"serviciu": {"nume": serviciu.get("nume") or u"", "furnizor": serviciu.get("furnizor") or p.get("furnizor") or u"",
			"tip": serviciu.get("tip") if serviciu.get("tip") is not None else p.get("tip_serviciu")},
		"feluri": feluri,
		"piste": piste,
		"debit_serviciu": debit_total if debit_stiut else None,
		"debit_frecventa": frecventa[0],
		"erori_ts": frecventa[1],
		"aplicatii": aplicatii[:16],
		"carusele": carusele,
		"actualizari": actualizari[:8],
		"ip": ip,
		"retea": {"nume": nit.get("nume") or u"", "frecvente": nit.get("frecvente") or 0,
			"onid": sdt.get("onid"), "tsid": sdt.get("tsid"), "servicii": numarate if sdt else None},
		"video_necunoscut": video_necunoscut,
		"lipsa": list(d.get("lipsa") or []),
	}


# ---------------------------------------------------------------- textele rezultatului

def _dec(x, cifre=1):
	try:
		from Components.Converter.HdsCommon import fmt_dec
		t = fmt_dec(x, cifre)
		if t:
			return t
	except Exception:
		pass
	return (u"%.*f" % (cifre, x)).replace(u".", u",")


def text_debit(bps):
	"""Biti pe secunda -> „2,4 Mbit/s” / „380 kbit/s” / „12 bit/s”."""
	if bps is None:
		return u"-"
	if bps >= 1e6:
		return _dec(bps / 1e6, 1) + u" Mbit/s"
	if bps >= 1e3:
		return u"%d kbit/s" % int(round(bps / 1e3))
	return u"%d bit/s" % int(round(bps))


def text_marime(n):
	if n >= 1024 * 1024:
		return _dec(n / 1048576.0, 1) + u" MB"
	if n >= 1024:
		return u"%d kB" % int(round(n / 1024.0))
	return u"%d B" % n


def text_pid(pid):
	return u"%d (0x%04X)" % (pid, pid)


def _lista(elemente, maxim):
	elemente = [e for e in elemente if e]
	if len(elemente) <= maxim:
		return u", ".join(elemente)
	return u", ".join(elemente[:maxim]) + u" " + _t(T_SI_INCA) % (len(elemente) - maxim)


def text_feluri(rez, maxim=4):
	return _lista([_t(FELURI[f]) for f in (rez or {}).get("feluri", []) if f in FELURI], maxim)


def _tip_serviciu(tip):
	try:
		from Components.Converter.HdsCommon import service_type_text
		t = service_type_text(int(tip))
		if t:
			return t
	except Exception:
		pass
	return u"0x%02X" % int(tip)


def rand_pista(x):
	"""Randul unei piste: PID, felul pe intelesul oricui, debitul, apoi tipul tehnic si tabelele vazute."""
	parti = [u"PID " + text_pid(x["pid"])]
	if x.get("felul") in FELURI:
		parti.append(_t(FELURI[x["felul"]]))
	if x.get("debit") is not None:
		d = u"~ " + text_debit(x["debit"])
		parti.append(_t(T_CEL_PUTIN) % d if x.get("cel_putin") else d)
	tehnic = [x.get("tip_text") or u""]
	if x.get("limba"):
		tehnic.append(x["limba"])
	if x.get("tabele"):
		nume = []
		for t in x["tabele"]:
			n = nume_tabel(t)
			if n not in nume:
				nume.append(n)
		tehnic.append(_t(T_TABELE) % u", ".join(nume[:6]))
	parti.append(u", ".join(t for t in tehnic if t))
	return u" · ".join(p for p in parti if p)


def sectiuni_text(rez):
	"""Rezultatul -> [{"titlu", "randuri"}], aceleasi pe televizor si in web."""
	if not rez:
		return []
	sect = []
	scurt = []
	if rez.get("feluri"):
		scurt.append(_t(T_CE_TRIMITE) % text_feluri(rez, 8))
	sv = rez.get("serviciu") or {}
	if sv.get("furnizor"):
		scurt.append(_t(T_FURNIZOR) % curat(sv["furnizor"], 60))
	if sv.get("tip") is not None:
		scurt.append(_t(T_TIP_SERVICIU) % _tip_serviciu(sv["tip"]))
	if rez.get("debit_serviciu") is not None:
		scurt.append(_t(T_DEBIT_SERVICIU) % (u"~ " + text_debit(rez["debit_serviciu"])))
	if rez.get("debit_frecventa") is not None:
		scurt.append(_t(T_DEBIT_FRECVENTA) % text_debit(rez["debit_frecventa"]))
	if rez.get("erori_ts"):
		scurt.append(_t(T_ERORI_TS) % rez["erori_ts"])
	if scurt:
		sect.append({"titlu": _t(S_SCURT), "randuri": scurt})
	if rez.get("piste"):
		sect.append({"titlu": _t(S_PISTE), "randuri": [rand_pista(x) for x in rez["piste"]]})
	elif rez.get("stare") == "gata" and not rez.get("lipsa"):
		sect.append({"titlu": _t(S_PISTE), "randuri": [_t(T_FARA_PISTE)]})
	apps = []
	for a in rez.get("aplicatii") or []:
		cod = {1: _t(T_PORNESTE_SINGURA), 2: _t(T_LA_CERERE)}.get(a.get("cod"), _t(T_OPRITA))
		apps.append(u" · ".join(x for x in (curat(a.get("nume"), 60) or u"-", a.get("tip"), cod,
			curat(a.get("adresa"), 120)) if x))
	if apps:
		sect.append({"titlu": _t(S_APLICATII), "randuri": apps})
	car = []
	for c in rez.get("carusele") or []:
		cap = u"PID %s · %s" % (text_pid(c["pid"]), _t(FELURI.get(c["fel"], FELURI[K_DC])))
		if c.get("module"):
			cap += u" · " + _t(T_MODULE) % (c["module"], text_marime(c["marime"]))
		car.append(cap)
		if c.get("fisiere"):
			car.append(_t(T_FISIERE) % _lista([curat(f, 80) for f in c["fisiere"]], 24))
			if c.get("de_citit"):
				car.append(_t(T_MODULE_CITITE) % (c["citite"], c["module"] or c["de_citit"]))
		if c.get("nume_module"):
			car.append(_t(T_NUME_MODULE) % _lista([curat(n, 40) for n in c["nume_module"]], 12))
	if car:
		sect.append({"titlu": _t(S_CARUSEL), "randuri": car})
	ssu = []
	for a in rez.get("actualizari") or []:
		if a.get("model") is not None:
			versiune = (u"0x%04X" % a["versiune"]) if a.get("versiune") is not None else u"-"
			ssu.append(_t(T_SSU_OUI) % (a["oui"], u"0x%04X" % a["model"], versiune))
		elif a.get("versiune") is not None:
			# versiunea anuntata in PMT (update_version, 5 biti, TS 102 006): numar mic, scris zecimal
			ssu.append(_t(T_SSU_VERSIUNE) % (a["oui"], u"%d" % a["versiune"]))
		else:
			ssu.append(u"OUI %s" % a["oui"])
	if ssu:
		sect.append({"titlu": _t(S_SSU), "randuri": ssu})
	ip = []
	for x in rez.get("ip") or []:
		dest = [u"%s%s (%s)" % (y["adresa"], (u":%d" % y["port"]) if y.get("port") is not None else u"", y["protocol"])
			for y in x.get("destinatii") or []]
		rand = u"PID " + text_pid(x["pid"])
		if dest:
			rand += u" · " + _t(T_DESTINATII) % _lista(dest, 5)
		ip.append(rand)
		if x.get("criptat"):
			ip.append(_t(T_CRIPTATE))
	if ip:
		sect.append({"titlu": _t(S_IP), "randuri": ip})
	r = rez.get("retea") or {}
	retea = []
	if r.get("nume"):
		retea.append(_t(T_RETEA) % curat(r["nume"], 60))
	if r.get("servicii"):
		s = r["servicii"]
		retea.append(u" · ".join(u"%s: %d" % (_t(t), s[k]) for k, t in (("tv", T_TV), ("radio", T_RADIO),
			("date", T_SERVICII_DATE), ("alte", T_ALTE)) if s.get(k)))
	if r.get("frecvente"):
		retea.append(_t(T_FRECVENTE_NIT) % r["frecvente"])
	if r.get("onid") is not None and r.get("tsid") is not None:
		retea.append(u"ONID %d · TSID %d" % (r["onid"], r["tsid"]))
	retea = [x for x in retea if x]
	if retea:
		sect.append({"titlu": _t(S_RETEA), "randuri": retea})
	erori = [_t(T_LIPSA_TABEL) % (t, int(s)) for t, s in rez.get("lipsa") or []]
	if rez.get("stare") == "oprita":
		erori.append(_t(T_OPRITA_ZAP))
	elif rez.get("eroare"):
		erori.append(curat(rez["eroare"], 160))
	if erori:
		sect.append({"titlu": _t(S_ERORI), "randuri": erori})
	return sect


def text_ecran(sectiuni, upper=None):
	"""Sectiunile ca un singur text (casuta derulabila de pe televizor)."""
	upper = upper or (lambda s: s.upper())
	return u"\n\n".join(upper(s["titlu"]) + u"\n" + u"\n".join(s["randuri"]) for s in sectiuni)


# ---------------------------------------------------------------- starea (firul enigma2)

_STARE = {"analiza": None, "ref": None, "rezultate": {}}
_ZAVOR = threading.Lock()
_fabrica_sursa = SursaDemux
_fabrica_contor = ContorFrecventa


def parametri(service, sref, canal=u"", furnizor=u""):
	"""Ce ia firul de lucru din serviciul redat (numere simple): demuxul, SID-ul, TSID, PID-ul PMT, tipul."""
	p = {"ref": sref, "canal": canal, "furnizor": furnizor, "sid": None, "tsid": None, "pmt_pid": -1,
		"tip_serviciu": None, "demux": None}
	parti = (sref or "").split(":")
	try:
		p["tip_serviciu"] = int(parti[2], 16)
		p["sid"] = int(parti[3], 16)
		p["tsid"] = int(parti[4], 16)
	except (IndexError, ValueError):
		pass
	try:
		s = service.stream()
		d = s and s.getStreamingData()
		if isinstance(d, dict):
			n = d.get("demux")
			if isinstance(n, int) and 0 <= n < 16:
				p["demux"] = n
			for pid, fel in d.get("pids") or []:
				if fel == "pmt":
					p["pmt_pid"] = pid
	except Exception:
		pass
	if p["pmt_pid"] <= 0:
		try:
			from enigma import iServiceInformation
			info = service.info()
			v = info.getInfo(iServiceInformation.sPMTPID) if info else -1
			if v and v > 0:
				p["pmt_pid"] = v
		except Exception:
			pass
	return p


def porneste(param, sursa=None, contor=None, ceas=None):
	"""Porneste analiza pentru serviciul din `param` (vezi parametri). -> True daca a pornit; False daca merge deja una
	pe acelasi serviciu sau demuxul nu se poate folosi (atunci rezultatul spune de ce)."""
	sref = param.get("ref")
	with _ZAVOR:
		a = _STARE["analiza"]
		if a is not None and a.rezultat() is None and _STARE["ref"] == sref:
			return False
	opreste()
	with _ZAVOR:
		vechi = _STARE["analiza"]
		if vechi is not None and vechi.rezultat() is not None:
			_STARE["rezultate"][_STARE["ref"]] = vechi.rezultat()
	if sursa is None:
		try:
			if param.get("demux") is None:
				raise ValueError("demux necunoscut")
			sursa = _fabrica_sursa(param["demux"])
		except Exception as e:
			print("[HdsAnalizaFlux] sursa: %s" % e)
			with _ZAVOR:
				_STARE["rezultate"][sref] = {"stare": "eroare", "eroare": _t(T_FARA_DEMUX), "ref": sref,
					"canal": param.get("canal") or u"", "timp": time.time(), "feluri": [], "piste": []}
			return False
	if contor is None:
		try:
			contor = _fabrica_contor(param.get("demux") or 0)
		except Exception:
			contor = None
	a = Analiza(param, sursa, ceas=ceas, contor=contor)
	with _ZAVOR:
		_STARE["analiza"] = a
		_STARE["ref"] = sref
		_STARE["rezultate"].pop(sref, None)
	a.porneste()
	return True


def opreste(zap=False):
	"""Opreste analiza care merge (la schimbarea canalului, la oprirea serviciului). Firul ei se incheie dupa cel mult
	un pas de POLL_MS; rezultatul („oprita”) ramane pentru serviciul ei."""
	with _ZAVOR:
		a = _STARE["analiza"]
	if a is not None and a.rezultat() is None:
		a.p["oprita_de_zap"] = bool(zap)
		a.opreste()


def _curata_vechi(acum):
	for ref in [r for r, x in _STARE["rezultate"].items() if acum - x.get("timp", 0) > PASTRAT_S]:
		del _STARE["rezultate"][ref]


def stare(sref):
	"""{"stare": "nimic" | "citeste" | "gata" | "eroare" | "oprita", "progres": (facute, stiute), "rezultat"} pentru
	serviciul `sref`. Rezultatul unei analize terminate trece in memoria pe servicii."""
	acum = time.time()
	with _ZAVOR:
		a = _STARE["analiza"]
		if a is not None and _STARE["ref"] == sref:
			rez = a.rezultat()
			if rez is None:
				return {"stare": "citeste", "progres": a.progres(), "rezultat": None}
			_STARE["rezultate"][sref] = rez
			_STARE["analiza"] = None
		_curata_vechi(acum)
		rez = _STARE["rezultate"].get(sref)
	if rez is None:
		return {"stare": "nimic", "progres": (0, 0), "rezultat": None}
	return {"stare": rez.get("stare") or "gata", "progres": (0, 0), "rezultat": rez}


def proaspat(sref, acum=None):
	"""Rezultatul terminat pentru `sref`, daca e mai nou de PROASPAT_S secunde, altfel None."""
	s = stare(sref)
	rez = s.get("rezultat")
	acum = time.time() if acum is None else acum
	if rez is not None and s["stare"] == "gata" and acum - rez.get("timp", 0) < PROASPAT_S:
		return rez
	return None


def merge(sref=None):
	"""O analiza e in lucru (pentru `sref`, sau pentru oricare serviciu)."""
	with _ZAVOR:
		a = _STARE["analiza"]
		return a is not None and a.rezultat() is None and (sref is None or _STARE["ref"] == sref)


def piste_din_nucleu(text):
	"""Pistele din PMT pe care nucleul nu le cunoaste (iServiceInformation.sPisteNecunoscute, lib/dvb/pmt.cpp:
	„pid:stream_type:inregistrare” in hex, despartite prin virgula) -> lista de piste in forma lui desfa_pista, numite
	cu aceleasi tabele ca analiza. Bucatile stricate se sar."""
	piste = []
	for parte in (text or u"").split(u","):
		bucati = parte.strip().split(u":")
		if len(bucati) != 3:
			continue
		try:
			pid, tip, reg = int(bucati[0], 16), int(bucati[1], 16), int(bucati[2], 16)
		except ValueError:
			continue
		d = []
		if reg:
			d.append((0x05, bytearray(((reg >> 24) & 0xFF, (reg >> 16) & 0xFF, (reg >> 8) & 0xFF, reg & 0xFF))))
		piste.append(desfa_pista(tip & 0xFF, pid & 0x1FFF, d))
	return piste


def video_necunoscut_din_nucleu(text):
	"""Prima pista video din PMT pe care decodorul nu o cunoaste (AV1, H.266 VVC, AVS2, AVS3...), dupa nucleu, fara
	sa citeasca demultiplexorul: {"pid", "codec", "stream_type", "detaliu"} sau None. Pentru mesajul de ecran negru
	(Components/HdsEcranNegru.py), imediat ce PMT-ul e citit."""
	for p in piste_din_nucleu(text):
		if p["felul"] != K_VIDEO_NECUNOSCUT:
			continue
		tehnic = u"stream_type 0x%02X" % p["stream_type"]
		if p["inregistrare"]:
			tehnic += u", " + p["inregistrare"]
		return {"pid": p["pid"], "codec": p["tip_text"], "stream_type": p["stream_type"],
			"detaliu": _t(T_PISTA_VIDEO) % (text_pid(p["pid"]), u"%s (%s)" % (p["tip_text"], tehnic))}
	return None


def pentru_verdict(sref):
	"""Ce ia mesajul de ecran negru din analiza (ieftin, pe firul enigma2): {"stare", "feluri", "codec"} sau None."""
	s = stare(sref)
	if s["stare"] == "nimic":
		return None
	rez = s.get("rezultat") or {}
	codec = u""
	for v in rez.get("video_necunoscut") or []:
		codec = _t(T_PISTA_VIDEO) % (text_pid(v["pid"]), u"%s (stream_type 0x%02X)" % (v["codec"], v["stream_type"]))
		break
	return {"stare": s["stare"], "feluri": text_feluri(rez, 2) if rez else u"", "codec": codec}
