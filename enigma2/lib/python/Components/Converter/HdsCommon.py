# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
# Functii comune pentru convertoarele skinului HDSatelit (hdsatelit.com).
# Nu e convertor: nu se pune in <convert type="...">.
#
# Reguli pentru tot fisierul (receptoarele au putine resurse si o exceptie
# scapata aici inseamna ecran de eroare):
# - nicio functie publica nu arunca exceptie; totul intoarce u"" / None / [] / {}
# - fara fire, fara retea, fara bucle pe timer; singura citire de disc pe drumul
#   des folosit e /tmp/hdsatelit/receptie.json, cel mult o data la 2 secunde
# - memoria nu creste: fiecare memo are marime fixa
# - se compileaza pe Python 2.7 si 3.x (fara f-string, fara adnotari)
from __future__ import absolute_import

import os
import sys
import json
from time import time as _time_now

try:
	from enigma import iServiceInformation as _ISI
except Exception:
	_ISI = None

try:
	from Components.Converter.HdsLang import EN as _EN, LANG_ALIAS as _LANG_ALIAS, cod_limba as _cod_limba, incarca as _incarca
except Exception:
	_EN, _LANG_ALIAS = {}, {}

	def _cod_limba(raw):
		return "en"

	def _incarca(cod):
		return {}

try:
	_unicode = unicode  # noqa: F821 (Python 2)
	PY2 = True
except NameError:
	_unicode = str
	PY2 = False

# ceasul se poate inlocui in teste
_now = _time_now

SEP = u" · "
DEG = u"°"
RECEPTIE_JSON = "/tmp/hdsatelit/receptie.json"


# ---------------------------------------------------------------- texte

def u(s):
	"""Orice valoare -> text unicode, fara exceptie."""
	if s is None:
		return u""
	if isinstance(s, _unicode):
		return s
	try:
		if isinstance(s, bytes):
			return s.decode("utf-8", "replace")
		return _unicode(s)
	except Exception:
		return u""


def out(s):
	"""Text pentru enigma2: str cu octeti UTF-8 pe Python 2, str pe Python 3."""
	try:
		if PY2:
			if isinstance(s, _unicode):
				return s.encode("utf-8", "replace")
			return s if isinstance(s, str) else ""
		if isinstance(s, bytes):
			return s.decode("utf-8", "replace")
		return s if isinstance(s, str) else ""
	except Exception:
		return ""


def join(parts, sep=SEP):
	return sep.join([p for p in parts if p])


_logged = set()


def log_once(where, err):
	"""Un singur mesaj pe fel de eroare, nu la fiecare eveniment."""
	try:
		key = (where, err.__class__.__name__)
		if key in _logged or len(_logged) > 64:
			return
		_logged.add(key)
		print("[HdsInfo] %s: %s" % (where, err))
	except Exception:
		pass


# ---------------------------------------------------------------- limba

# code: codul modulului de limba ("ro", "pt_br", "zh_hk"...); t: tabelul limbii active (doar ea e in
# memorie, engleza e in _EN); gen creste la fiecare schimbare de limba
_lang = {"raw": object(), "code": "en", "t": {}, "gen": 0}


def refresh_lang():
	"""Citeste config.osd.language; ieftin, se cheama doar la evStart si la constructie.
	Modulul limbii se incarca doar cand limba se schimba."""
	try:
		mod = sys.modules.get("Components.config")
		raw = mod.config.osd.language.value if mod is not None else None
	except Exception:
		raw = None
	if raw == _lang["raw"]:
		return
	_lang["raw"] = raw
	try:
		code = _cod_limba(raw)
	except Exception:
		code = "en"
	if code != _lang["code"]:
		try:
			t = _incarca(code)
		except Exception:
			t = {}
		_lang["code"] = code
		_lang["t"] = t if isinstance(t, dict) else {}
		_lang["gen"] += 1


def lang_code():
	return _lang["code"]


def lang_gen():
	return _lang["gen"]


def tr(key):
	v = _lang["t"].get(key)
	if v is None:
		v = _EN.get(key)
		if v is None:
			return u(key)
	if key[:1] == "_":
		return v  # separatoarele pot fi goale
	return v or _EN.get(key) or u(key)


# Limbile de la dreapta la stanga. enigma2 (lib/gdi/font.cpp) da textul prin fribidi cu directia luata din
# prima litera „tare": un rand care incepe cu araba devine paragraf de la dreapta la stanga, iar bucatile
# latine si numerele din el isi schimba ordinea („474 MHz · DVB-T2 · ارضي" iesea „MHz · DVB-T2 474 · ارضي")
# si randul se lipeste la dreapta in coloanele facute pentru stanga. Un semn LRM (U+200E, fara latime,
# prezent in fonts/HdsScripturi.ttf) pus in fata tine paragraful de la stanga la dreapta; cuvintele arabe
# raman scrise corect de la dreapta la stanga in interiorul lui.
RTL_LANGS = ("ar", "fa", "he")
_LRM = u"‎"


def _are_rtl(s):
	for ch in s:
		o = ord(ch)
		if 0x0590 <= o <= 0x08FF or 0xFB1D <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF:
			return True
	return False


def ltr(s):
	"""Textul pentru afisare, cand limba e RTL si textul are litere RTL: LRM in fata (paragraf de la stanga
	la dreapta) si LRM inaintea cifrelor si literelor latine care vin dupa un cuvant RTL. Fara al doilea,
	fribidi lipeste numarul de cuvantul arab dinaintea lui („ارضي · 474 MHz" iesea „474 · ارضي MHz").
	Intre doua cuvinte RTL nu se pune nimic, ca ordinea lor sa ramana de la dreapta la stanga."""
	try:
		if not s or _lang["code"] not in RTL_LANGS or not _are_rtl(s):
			return s
		rez = []
		dupa_rtl = False
		for ch in s:
			o = ord(ch)
			if 0x0590 <= o <= 0x08FF or 0xFB1D <= o <= 0xFDFF or 0xFE70 <= o <= 0xFEFF:
				dupa_rtl = True
			elif dupa_rtl and o < 0x0590 and ch.isalnum():
				rez.append(_LRM)
				dupa_rtl = False
			rez.append(ch)
		if rez[0] != _LRM:
			rez.insert(0, _LRM)
		return u"".join(rez)
	except Exception:
		return s


# greaca se scrie cu majuscule fara accent
_EL_FARA_ACCENT = {0x386: 0x391, 0x388: 0x395, 0x389: 0x397, 0x38A: 0x399, 0x38C: 0x39F, 0x38E: 0x3A5, 0x38F: 0x3A9,
	0x390: 0x3AA, 0x3B0: 0x3AB}


def upper(s):
	s = u(s)
	try:
		code = lang_code()
		if code == "tr":
			s = s.replace(u"i", u"İ")
		s = s.upper()
		if code == "el":
			s = s.translate(_EL_FARA_ACCENT)
		return s
	except Exception:
		return s


def fmt_int_group(n):
	"""11856 -> 11.856 (ro), 11,856 (en), 11856 (fr)."""
	try:
		n = int(n)
	except Exception:
		return u""
	sep = tr("_thou") if "_thou" in _EN else u","
	s = u"%d" % abs(n)
	if sep and len(s) > 3:
		groups = []
		while len(s) > 3:
			groups.insert(0, s[-3:])
			s = s[:-3]
		groups.insert(0, s)
		s = sep.join(groups)
	return (u"-" if n < 0 else u"") + s


def fmt_dec(x, digits=1):
	try:
		s = u"%.*f" % (digits, float(x))
	except Exception:
		return u""
	sep = tr("_dec") if "_dec" in _EN else u"."
	return s.replace(u".", sep)


def fmt_mhz(mhz, group=False):
	"""MHz ca intreg daca e intreg, altfel cu o zecimala."""
	try:
		whole = int(mhz)
		frac = mhz - whole
	except Exception:
		return u""
	if abs(frac) < 0.05:
		return fmt_int_group(whole) if group else u"%d" % whole
	text = fmt_dec(mhz, 1)
	if group and whole >= 1000:
		dec = tr("_dec") if "_dec" in _EN else u"."
		text = fmt_int_group(whole) + dec + text.split(dec)[-1]
	return text


def orbital(pos):
	"""192 -> „19,2°E”; literele si separatorul limbii barei („5,0°V” in romana, „5.0°W” in engleza), aceleasi ca pe
	ecrane si in web (Components/HdsGrade.py); fara modul, forma de dinainte."""
	try:
		pos = int(pos)
	except Exception:
		return u""
	if pos < 0 or pos > 3600:
		return u""
	try:
		try:
			from Components.HdsGrade import pozitieOrbitala
		except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
			from HdsGrade import pozitieOrbitala
		text = pozitieOrbitala(pos, lang_code())
		if text:
			return u(text)
	except Exception as e:
		log_once("orbital", e)
	if pos > 1800:
		return fmt_dec((3600 - pos) / 10.0) + DEG + u"W"
	return fmt_dec(pos / 10.0) + DEG + u"E"


# ---------------------------------------------------------------- enumuri enigma2

SAT_POL = {0: u"H", 1: u"V", 2: u"L", 3: u"R"}
SAT_POL_KEY = {0: "pol_h", 1: "pol_v", 2: "pol_l", 3: "pol_r"}
SAT_SYSTEM = {0: u"DVB-S", 1: u"DVB-S2"}
SAT_MOD = {1: u"QPSK", 2: u"8PSK", 3: u"QAM16", 4: u"16APSK", 5: u"32APSK"}
FEC = {1: u"1/2", 2: u"2/3", 3: u"3/4", 4: u"5/6", 5: u"7/8", 6: u"8/9", 7: u"3/5", 8: u"4/5", 9: u"9/10", 10: u"6/7"}
ROLLOFF = {0: 0.35, 1: 0.25, 2: 0.20}
PLS_MODE = {0: u"Root", 1: u"Gold", 2: u"Combo"}
CAB_MOD = {1: u"QAM16", 2: u"QAM32", 3: u"QAM64", 4: u"QAM128", 5: u"QAM256"}
TER_RATE = {0: u"1/2", 1: u"2/3", 2: u"3/4", 3: u"5/6", 4: u"7/8", 6: u"6/7", 7: u"8/9", 8: u"3/5", 9: u"4/5"}
TER_CONST = {0: u"QPSK", 1: u"QAM16", 2: u"QAM64", 4: u"QAM256"}
TER_TMODE = {0: u"2K", 1: u"8K", 3: u"4K", 4: u"1K", 5: u"16K", 6: u"32K"}
TER_GUARD = {0: u"1/32", 1: u"1/16", 2: u"1/8", 3: u"1/4", 5: u"1/128", 6: u"19/128", 7: u"19/256"}
TER_BW_INDEX = {0: 8.0, 1: 7.0, 2: 6.0, 4: 5.0, 5: 1.712, 6: 10.0}
VIDEO_CODEC = {0: u"MPEG-2", 1: u"H.264", 2: u"H.263", 3: u"VC-1", 4: u"MPEG-4", 5: u"VC-1", 6: u"MPEG-1",
	7: u"H.265", 8: u"VP8", 9: u"VP9", 10: u"XviD", 13: u"DivX 3", 14: u"DivX 4", 15: u"DivX 5",
	16: u"AVS", 18: u"VP6", 21: u"Spark", 40: u"AVS2"}
GAMMA = {0: u"SDR", 1: u"HDR", 2: u"HDR10", 3: u"HLG"}
PROGRESSIVE = {0: u"i", 1: u"p"}
ASPECT_WIDE = (3, 4, 7, 8, 0xB, 0xC, 0xF, 0x10)
ASPECT_43 = (1, 2, 5, 6, 9, 0xA, 0xD, 0xE)


def ival(d, key, default=-1):
	"""Valoare intreaga dintr-un dictionar, sau default."""
	try:
		v = d.get(key, default)
		if v is None:
			return default
		return int(v)
	except Exception:
		return default


def to_mhz(value):
	"""Frecventa in MHz din Hz, kHz sau MHz (imaginile difera: terestru in Hz, restul in kHz)."""
	try:
		v = float(value)
	except Exception:
		return None
	if v <= 0:
		return None
	for div in (1.0, 1000.0, 1000000.0, 1000000000.0):
		m = v / div
		if 30.0 <= m <= 15000.0:
			return m
	return None


def terrestrial_channel(mhz):
	"""Canal european: UHF 21-69 (474-858 MHz), VHF 5-12 (177,5-226,5 MHz)."""
	try:
		if 470.0 <= mhz <= 862.0:
			n = (mhz - 306.0) / 8.0
			if abs(n - round(n)) < 0.07:
				return int(round(n))
		elif 174.0 <= mhz <= 230.0:
			n = (mhz - 177.5) / 7.0 + 5
			if abs(n - round(n)) < 0.08:
				return int(round(n))
	except Exception:
		pass
	return None


# ---------------------------------------------------------------- CAID

# (inceput, sfarsit, nume). Registrul DVB castiga unde imaginile nu sunt de acord.
CAID_TABLE = (
	(0x0100, 0x01FF, u"Seca Mediaguard"),
	(0x0200, 0x02FF, u"CCETT"),
	(0x0300, 0x03FF, u"Kabel Deutschland"),
	(0x0400, 0x04FF, u"Eurodec"),
	(0x0500, 0x05FF, u"Viaccess"),
	(0x0600, 0x06FF, u"Irdeto"),
	(0x0700, 0x07FF, u"DigiCipher"),
	(0x0800, 0x08FF, u"Matra"),
	(0x0900, 0x09FF, u"NDS VideoGuard"),
	(0x0A00, 0x0AFF, u"Nokia"),
	(0x0B00, 0x0BFF, u"Conax"),
	(0x0C00, 0x0CFF, u"NTL"),
	(0x0D00, 0x0DFF, u"CryptoWorks"),
	(0x0E00, 0x0EFF, u"PowerVu"),
	(0x0F00, 0x0FFF, u"Sony"),
	(0x1000, 0x10FF, u"Tandberg"),
	(0x1100, 0x11FF, u"Thomson"),
	(0x1200, 0x12FF, u"TV/Com"),
	(0x1300, 0x14FF, u"HPT / HRT"),
	(0x1500, 0x15FF, u"IBM"),
	(0x1600, 0x16FF, u"Nera"),
	(0x1700, 0x17FF, u"BetaCrypt"),
	(0x1800, 0x18FF, u"Nagravision"),
	(0x1900, 0x19FF, u"Titan"),
	(0x1E00, 0x1E07, u"Alticast"),
	(0x1EC0, 0x1EC2, u"Cryptoguard"),
	(0x2000, 0x20FF, u"Telefonica"),
	(0x2100, 0x21FF, u"Stentor"),
	(0x2200, 0x22FF, u"Harmonic"),
	(0x2300, 0x23FF, u"Barco"),
	(0x2400, 0x24FF, u"StarGuide"),
	(0x2500, 0x25FF, u"Mentor"),
	(0x2600, 0x26FF, u"BISS"),
	(0x2600, 0x2601, u"BISS"),
	(0x2602, 0x2602, u"BISS2"),
	(0x2610, 0x2610, u"BISS-CA"),
	(0x2700, 0x270F, u"PolyCipher"),
	(0x2710, 0x2711, u"DRE-Crypt 3"),
	(0x2712, 0x2712, u"Derincrypt"),
	(0x4347, 0x4347, u"Crypton"),
	(0x4700, 0x47FF, u"DigiCipher"),
	(0x4800, 0x48FF, u"Telemann"),
	(0x4900, 0x49FF, u"CryptoWorks China"),
	(0x4A02, 0x4A02, u"Tongfang"),
	(0x4A10, 0x4A1F, u"EasyCas"),
	(0x4A20, 0x4A2F, u"AlphaCrypt"),
	(0x4A30, 0x4A3F, u"DVN"),
	(0x4A60, 0x4A6F, u"Neotion"),
	(0x4A70, 0x4A7F, u"DreamCrypt"),
	(0x4A80, 0x4A8F, u"ThalesCrypt"),
	(0x4AA0, 0x4AAF, u"SIDSA"),
	(0x4ABF, 0x4ABF, u"DGCrypt"),
	(0x4AC0, 0x4ACF, u"Latens"),
	(0x4AD0, 0x4AD1, u"XCrypt"),
	(0x4AD4, 0x4AD5, u"Widevine"),
	(0x4ADE, 0x4ADE, u"CerberCrypt"),
	(0x4AE0, 0x4AE1, u"DRE-Crypt"),
	(0x4AE2, 0x4AE3, u"Microsoft"),
	(0x4AE5, 0x4AE5, u"IK SATPROF"),
	(0x4AEA, 0x4AEA, u"Cryptoguard"),
	(0x4AEB, 0x4AEB, u"Abel DRM"),
	(0x4AEE, 0x4AEE, u"BulCrypt"),
	(0x4AEF, 0x4AEF, u"NetUP"),
	(0x4AF6, 0x4AF6, u"Tongfang"),
	(0x4AF8, 0x4AF8, u"Griffin"),
	(0x4AFC, 0x4AFC, u"Panaccess"),
	(0x4B00, 0x4B02, u"Tongfang"),
	(0x4B03, 0x4B03, u"DuoCrypt"),
	(0x4B05, 0x4B06, u"DigiCAP"),
	(0x4B0A, 0x4B0B, u"Sumavision"),
	(0x4B13, 0x4B14, u"Microsoft"),
	(0x4B20, 0x4B22, u"Multikom Deltasat"),
	(0x4B42, 0x4B43, u"CI Plus"),
	(0x4B64, 0x4B64, u"TVKey"),
	(0x5347, 0x5347, u"GkWare"),
	(0x5501, 0x551A, u"Griffin"),
	(0x5581, 0x5581, u"BulCrypt"),
	(0x5601, 0x5604, u"Verimatrix"),
	(0x56C0, 0x56C9, u"Google"),
	(0x7700, 0x7704, u"DRE-Crypt"),
	(0x7BE0, 0x7BE1, u"DRE-Crypt"),
	(0xAA00, 0xAA01, u"BestCAS"),
)
# cel mai ingust interval primul
_CAID_SORTED = tuple(sorted(CAID_TABLE, key=lambda e: (e[1] - e[0], e[0])))
_caid_memo = {}


def caid_name(caid):
	"""Numele sistemului, sau None daca nu e in tabel."""
	try:
		caid = int(caid) & 0xFFFF
	except Exception:
		return None
	if caid in _caid_memo:
		return _caid_memo[caid]
	name = None
	for lo, hi, n in _CAID_SORTED:
		if lo <= caid <= hi:
			name = n
			break
	if len(_caid_memo) > 512:
		_caid_memo.clear()
	_caid_memo[caid] = name
	return name


def clean_caids(raw):
	if not isinstance(raw, (list, tuple)):
		return []
	seen = set()
	for c in raw:
		try:
			c = int(c) & 0xFFFF
		except Exception:
			continue
		if c:
			seen.add(c)
	return sorted(seen)


def group_caids(caids):
	"""[(nume, [caid, ...]), ...] in ordinea CAID-urilor."""
	groups = []
	index = {}
	for c in caids:
		name = caid_name(c) or (u"0x%04X" % c)
		if name not in index:
			index[name] = len(groups)
			groups.append((name, []))
		groups[index[name]][1].append(c)
	return groups


# ---------------------------------------------------------------- satelit

_sat_names = {}
_sat_xml = {"loaded": False, "names": {}}
SAT_XML_PATHS = ("/etc/tuxbox/satellites.xml", "/etc/enigma2/satellites.xml", "/usr/share/tuxbox/satellites.xml")


def _clean_sat(name):
	name = u(name).strip()
	if not name:
		return u""
	try:
		import re
		name = re.sub(u"^\\s*\\d+([.,]\\d+)?\\s*°?\\s*[EWew]\\s*[-:]?\\s+", u"", name)
		name = re.sub(u"\\s*\\(\\d+([.,]\\d+)?\\s*°?\\s*[EWew]\\)\\s*$", u"", name)
		name = name.replace(u"&amp;", u"&").replace(u"&apos;", u"'").replace(u"&quot;", u"\"")
	except Exception:
		pass
	return name.strip()


def _load_sat_xml():
	"""satellites.xml citit o singura data, doar daca nimmanager nu raspunde."""
	_sat_xml["loaded"] = True
	names = {}
	try:
		import re
		for path in SAT_XML_PATHS:
			try:
				if not os.path.isfile(path) or os.path.getsize(path) > 4 * 1024 * 1024:
					continue
				f = open(path, "rb")
				try:
					data = f.read().decode("utf-8", "replace")
				finally:
					f.close()
			except Exception:
				continue
			for m in re.finditer(u"<sat\\s[^>]*>", data):
				tag = m.group(0)
				n = re.search(u"name=\"([^\"]*)\"", tag)
				p = re.search(u"position=\"(-?\\d+)\"", tag)
				if not n or not p:
					continue
				pos = int(p.group(1))
				if pos < 0:
					pos += 3600
				prev = names.get(pos)
				if prev is None or (u"Ku" in n.group(1) and u"Ku" not in prev):
					names[pos] = n.group(1)
			if names:
				break
	except Exception as e:
		log_once("satellites.xml", e)
	_sat_xml["names"] = names


def sat_name(pos):
	try:
		pos = int(pos)
	except Exception:
		return u""
	if pos in _sat_names:
		return _sat_names[pos]
	name = u""
	try:
		mod = sys.modules.get("Components.NimManager")
		nm = getattr(mod, "nimmanager", None) if mod is not None else None
		if nm is not None:
			try:
				name = u(nm.getSatDescription(pos))
			except Exception:
				name = u""
	except Exception:
		name = u""
	if not name:
		if not _sat_xml["loaded"]:
			_load_sat_xml()
		name = u(_sat_xml["names"].get(pos, u""))
	name = _clean_sat(name)
	if len(_sat_names) > 256:
		_sat_names.clear()
	_sat_names[pos] = name
	return name


def sat_full(pos):
	return join([orbital(pos), sat_name(pos)], u" ")


# ---------------------------------------------------------------- referinta

def parse_ref(sref):
	"""Desface referinta: tip, tip serviciu, SID..., cale (URL decodat)."""
	r = {"type": -1, "stype": -1, "fields": [], "path": u"", "url": False, "host": u"", "urlpath": []}
	s = u(sref)
	if not s:
		return r
	f = s.split(u":")
	r["fields"] = f
	try:
		r["type"] = int(f[0])
	except Exception:
		pass
	try:
		r["stype"] = int(f[2], 16)
	except Exception:
		pass
	if len(f) > 10:
		path = f[10].replace(u"%3a", u":").replace(u"%3A", u":")
		r["path"] = path
		if u"://" in path:
			r["url"] = True
			try:
				rest = path.split(u"://", 1)[1]
				hostpart = rest.split(u"/", 1)[0]
				if u"@" in hostpart:
					hostpart = hostpart.split(u"@")[-1]  # fara nume si parola
				r["host"] = hostpart
				r["urlpath"] = rest.split(u"/")[1:] if u"/" in rest else []
			except Exception:
				pass
	return r


# tipurile de serviciu radio din DVB, cum le socoteste si enigma2 in lista de radio: 0x02 si 0x0A
RADIO_STYPES = (2, 10)
# terminatii de flux doar audio (radio pe internet cu tip 1 in referinta)
AUDIO_EXT = (u".mp3", u".aac", u".aacp", u".m4a", u".ogg", u".oga", u".opus", u".flac", u".wma", u".pls")


def is_audio_url(path):
	"""Adresa unui flux doar audio, dupa terminatie (fara ?parametri si #)."""
	p = u(path).lower().split(u"?", 1)[0].split(u"#", 1)[0].rstrip(u"/")
	return p.endswith(AUDIO_EXT)


def norm_ref(sref):
	"""Primele 11 campuri, litere mici (pentru comparatia cu receptie.json)."""
	try:
		return u":".join(u(sref).strip().split(u":")[:11]).lower()
	except Exception:
		return u""


def is_local_host(host):
	h = u(host).lower().split(u":")[0]
	return h in (u"127.0.0.1", u"localhost", u"0.0.0.0", u"::1")


def host_port(host):
	try:
		return int(u(host).rsplit(u":", 1)[1])
	except Exception:
		return -1


# ---------------------------------------------------------------- receptie.json

_rj = {"checked": -1000.0, "mtime": None, "data": None}


def receptie(sref):
	"""Datele pluginului pentru serviciul redat, sau None.

	Cel mult un os.stat la 2 s, citire doar la mtime nou, valabil 15 s,
	doar pentru acelasi serviciu. JSON stricat: ignorat pana la urmatorul mtime.
	"""
	try:
		now = _now()
		if now - _rj["checked"] >= 2.0 or now < _rj["checked"]:
			_rj["checked"] = now
			try:
				st = os.stat(RECEPTIE_JSON)
			except Exception:
				_rj["mtime"] = None
				_rj["data"] = None
				st = None
			if st is not None and st.st_mtime != _rj["mtime"]:
				_rj["mtime"] = st.st_mtime
				_rj["data"] = None
				if 0 < st.st_size <= 65536:
					try:
						f = open(RECEPTIE_JSON, "rb")
						try:
							raw = f.read(65537)
						finally:
							f.close()
						d = json.loads(raw.decode("utf-8", "replace"))
						if isinstance(d, dict):
							_rj["data"] = d
					except Exception:
						_rj["data"] = None
		d = _rj["data"]
		mt = _rj["mtime"]
		if d is None or mt is None:
			return None
		age = now - mt
		if age > 15.0 or age < -60.0:
			return None
		want = norm_ref(sref)
		if not want or norm_ref(d.get("sref_redat")) != want:
			return None
		return d
	except Exception as e:
		log_once("receptie.json", e)
		return None


def rj_dict(d, key):
	try:
		v = d.get(key)
		return v if isinstance(v, dict) else {}
	except Exception:
		return {}


# ---------------------------------------------------------------- transponder

def tp_kind(tp):
	"""'s', 'c', 't', 'a', 'dab' sau '' dupa tuner_type (tipul vine din transponder, nu din tuner)."""
	try:
		t = u(tp.get("tuner_type")).upper()
	except Exception:
		return ""
	if t.startswith(u"DVB-S") or t == u"SATELLITE":
		return "s"
	if t.startswith(u"DVB-C") or t == u"CABLE":
		return "c"
	if t.startswith(u"DVB-T") or t == u"TERRESTRIAL":
		return "t"
	if t.startswith(u"ATSC"):
		return "a"
	if u"DAB" in t:
		return "dab"
	if isinstance(tp, dict) and ival(tp, "orbital_position") >= 0:
		return "s"
	return ""


def sat_system(tp):
	return SAT_SYSTEM.get(ival(tp, "system"), u"DVB-S")


def ter_is_t2(tp):
	return ival(tp, "system") == 1 or ival(tp, "plp_id") >= 0


def mis_pls(tp):
	parts = []
	isid = ival(tp, "is_id")
	if isid >= 0:
		parts.append(u"MIS %d" % isid)
	code = ival(tp, "pls_code", 0)
	mode = ival(tp, "pls_mode", 0)
	if code > 0 and not (mode == 0 and code == 1):
		parts.append(join([u"PLS", PLS_MODE.get(mode, u""), u"%d" % code], u" "))
	return join(parts)


def fec_text(tp, kind):
	if kind == "t":
		v = ival(tp, "code_rate_hp")
		if v == 5:
			return tr("auto")
		return TER_RATE.get(v, u"")
	v = ival(tp, "fec_inner")
	if v == 0:
		return tr("auto")
	return FEC.get(v, u"")


def modulation_text(tp, kind):
	if kind == "s":
		return SAT_MOD.get(ival(tp, "modulation"), u"")
	if kind == "c":
		return CAB_MOD.get(ival(tp, "modulation"), u"")
	if kind == "t":
		return TER_CONST.get(ival(tp, "constellation"), u"")
	return u""


def bandwidth_text(tp):
	bw = ival(tp, "bandwidth")
	if bw < 0:
		return u""
	if bw < 100:
		mhz = TER_BW_INDEX.get(bw)
	else:
		mhz = bw / 1000000.0
	if not mhz:
		return u""
	return fmt_mhz(mhz) + u" MHz"


def symbol_rate(tp):
	sr = ival(tp, "symbol_rate")
	if sr <= 0:
		return u""
	if sr >= 100000:
		sr = sr // 1000
	return u"%d" % sr


def freq_short(tp, kind):
	"""11856 V (satelit), 354 MHz (cablu), 482 MHz CH22 (terestru)."""
	mhz = to_mhz(tp.get("frequency") if isinstance(tp, dict) else None)
	if mhz is None:
		return u""
	if kind == "s":
		return join([fmt_mhz(mhz), SAT_POL.get(ival(tp, "polarization"), u"")], u" ")
	text = fmt_mhz(mhz) + u" MHz"
	if kind == "t":
		ch = terrestrial_channel(mhz)
		if ch:
			text += u" CH%d" % ch
	return text


def freq_long(tp, kind):
	"""11.856 MHz V."""
	mhz = to_mhz(tp.get("frequency") if isinstance(tp, dict) else None)
	if mhz is None:
		return u""
	text = fmt_mhz(mhz, True) + u" MHz"
	if kind == "s":
		return join([text, SAT_POL.get(ival(tp, "polarization"), u"")], u" ")
	if kind == "t":
		ch = terrestrial_channel(mhz)
		if ch:
			text += u" CH%d" % ch
	return text


def system_text(tp, kind):
	if kind == "s":
		parts = [join([sat_system(tp), SAT_MOD.get(ival(tp, "modulation"), u"")], u" "), mis_pls(tp)]
		if ival(tp, "t2mi_plp_id") >= 0:
			parts.append(u"T2-MI")
		return join(parts)
	if kind == "c":
		return join([u"DVB-C", CAB_MOD.get(ival(tp, "modulation"), u"")], u" ")
	if kind == "t":
		t2 = ter_is_t2(tp)
		parts = [join([u"DVB-T2" if t2 else u"DVB-T", TER_CONST.get(ival(tp, "constellation"), u"")], u" ")]
		if t2 and ival(tp, "plp_id") >= 0:
			parts.append(u"PLP %d" % ival(tp, "plp_id"))
		return join(parts)
	if kind == "a":
		return u"ATSC"
	return u""


def tp_line(tp, kind, short=False):
	"""Randul tehnic din InfoBar pentru un transponder DVB. `short`: la satelit fara numele satelitului si fara FEC
	(randul barei de jos, unde stau si SEMNAL / CALITATE; amandoua sunt pe pagina 1 a celei de-a doua bare)."""
	if kind == "s":
		pos = ival(tp, "orbital_position")
		sys_part = join([sat_system(tp), SAT_MOD.get(ival(tp, "modulation"), u""), u"" if short else fec_text(tp, "s")], u" ")
		sr = symbol_rate(tp)
		where = (orbital(pos) if short else sat_full(pos)) if pos >= 0 else u""
		parts = [where, freq_short(tp, "s"), (u"SR " + sr) if sr else u"", sys_part]
		if ival(tp, "t2mi_plp_id") >= 0:
			parts.append(u"T2-MI PLP %d" % ival(tp, "t2mi_plp_id"))
		return join(parts)
	if kind == "c":
		sr = symbol_rate(tp)
		return join([tr("rec_cable"), freq_short(tp, "c"), (u"SR " + sr) if sr else u"", CAB_MOD.get(ival(tp, "modulation"), u"")])
	if kind == "t":
		return join([tr("rec_terr"), freq_short(tp, "t"), bandwidth_text(tp), u"DVB-T2" if ter_is_t2(tp) else u"DVB-T"])
	if kind == "a":
		return join([u"ATSC", freq_short(tp, "a")])
	return u""


def carrier_short(tp):
	"""19,2°E 12460 H."""
	kind = tp_kind(tp)
	if not kind and isinstance(tp, dict) and tp.get("frequency"):
		kind = "s"
	if kind == "s":
		pos = ival(tp, "orbital_position")
		return join([orbital(pos) if pos >= 0 else u"", freq_short(tp, "s")], u" ")
	if kind in ("c", "t", "a"):
		return freq_short(tp, kind)
	return u""


# ---------------------------------------------------------------- pagina tehnica extinsa: transponder

TER_HIER = {1: u"α=1", 2: u"α=2", 3: u"α=4"}
ON_OFF_AUTO = {0: "off", 1: "on", 2: "auto"}
# tipul serviciului din referinta (EN 300 468, service_type); None = cheie de traducere in al doilea camp
SERVICE_TYPES = {
	0x01: (u"TV SD MPEG-2", None), 0x02: (u"", "radio"), 0x03: (u"", "teletext"), 0x0A: (u"AAC", "radio"),
	0x0C: (u"", "data_service"), 0x11: (u"TV HD MPEG-2", None), 0x16: (u"TV SD H.264", None),
	0x19: (u"TV HD H.264", None), 0x1F: (u"TV HEVC", None), 0x20: (u"TV UHD HEVC", None),
}


def enum_auto(tp, key, table, auto_value):
	"""Valoare din tabel; auto_value -> „auto" tradus; necunoscut -> gol."""
	v = ival(tp, key)
	if v == auto_value:
		return tr("auto")
	return table.get(v, u"")


def on_off(tp, key):
	k = ON_OFF_AUTO.get(ival(tp, key))
	return tr(k) if k else u""


def code_rate_text(tp):
	"""HP 2/3, iar LP doar cand exista ierarhie (alfa 1, 2 sau 4)."""
	hp = enum_auto(tp, "code_rate_hp", TER_RATE, 5)
	if not hp:
		return u""
	parts = [u"HP " + hp]
	if ival(tp, "hierarchy_information") in TER_HIER and not ter_is_t2(tp):
		lp = enum_auto(tp, "code_rate_lp", TER_RATE, 5)
		if lp:
			parts.append(u"LP " + lp)
	return join(parts)


def terr_channel_text(tp):
	"""CH22 UHF / CH5 VHF, doar pe rasterul european si cu latimea de banda potrivita (8 MHz UHF, 7 MHz VHF)."""
	mhz = to_mhz(tp.get("frequency") if isinstance(tp, dict) else None)
	if mhz is None:
		return u""
	ch = terrestrial_channel(mhz)
	if not ch:
		return u""
	uhf = mhz >= 470.0
	bw = ival(tp, "bandwidth")
	if bw >= 0:
		mhz_bw = TER_BW_INDEX.get(bw) if bw < 100 else bw / 1000000.0
		if mhz_bw and abs(mhz_bw - (8.0 if uhf else 7.0)) > 0.01:
			return u""
	return u"CH%d %s" % (ch, u"UHF" if uhf else u"VHF")


def service_type_text(stype):
	e = SERVICE_TYPES.get(stype)
	if e is None:
		return (u"0x%02X" % stype) if 0 < stype < 256 else u""
	fixed, key = e
	return join([tr(key) if key else u"", fixed], u" ")


def namespace_text(ref_fields, ns_int):
	"""Namespace-ul din referinta (campul 7), altfel din sNamespace; hex cu majuscule."""
	try:
		if len(ref_fields) > 6:
			v = int(ref_fields[6], 16) & 0xFFFFFFFF
			if v:
				return u"%X" % v
	except Exception:
		pass
	try:
		v = int(ns_int)
		if v == -1:
			return u""
		v &= 0xFFFFFFFF
		return (u"%X" % v) if v else u""
	except Exception:
		return u""


def id_dec_hex(vals, width):
	"""`1019 · 1 (03FB · 0001)`; valorile negative sunt „-"."""
	if not vals or max(vals) <= 0:
		return u""
	dec = join([(u"%d" % v) if v >= 0 else u"-" for v in vals])
	hx = join([(u"%0*X" % (width, v)) if v >= 0 else u"-" for v in vals])
	return u"%s (%s)" % (dec, hx)


# ---------------------------------------------------------------- pagina tehnica extinsa: acces, piste

MAX_ROWS = 6
# randurile care se pot cere din skin (`AudioTrack,n`, `CaRow,n`...): pana la 32; „+N” (more_text) numara tot peste 6,
# cat arata varianta de 624 px; varianta pe tot ecranul isi da numarul de randuri vazute (`SelAudio,1,11`)
ROW_LIMIT = 32


def clean_caidpids(raw):
	"""[(caid, ecm_pid)] fara dubluri, in ordinea CAID-urilor; ecm_pid -1 cand lipseste.
	Elementele pot avea 2 sau 3 campuri (pe unele imagini vechi 2)."""
	if not isinstance(raw, (list, tuple)):
		return []
	seen = set()
	rows = []
	for e in raw:
		try:
			caid = int(e[0]) & 0xFFFF
		except Exception:
			continue
		if not caid:
			continue
		try:
			pid = int(e[1])
		except Exception:
			pid = -1
		if not 0 < pid < 0x1FFF:
			pid = -1
		k = (caid, pid)
		if k in seen:
			continue
		seen.add(k)
		rows.append(k)
	rows.sort()
	return rows


def ca_rows(caidpids, caids):
	"""Randurile de acces: din PMT cu PID-ul ECM; CAID-urile fara PID (din lista de canale) la sfarsit."""
	rows = []
	have = set()
	for caid, pid in caidpids:
		have.add(caid)
		name = caid_name(caid) or u"0x%04X" % caid
		if pid > 0:
			rows.append(join([name, u"CAID %04X" % caid, u"ECM PID %d" % pid]))
		else:
			rows.append(join([name, u"CAID %04X" % caid, tr("param_list")]))
	for caid in caids:
		if caid not in have:
			rows.append(join([caid_name(caid) or u"0x%04X" % caid, u"CAID %04X" % caid, tr("param_list")]))
	return rows


def more_text(n):
	return (u"+%d" % (n - MAX_ROWS)) if n > MAX_ROWS else u""


SUB_FILE_KIND = {1: u"Text", 2: u"SSA", 3: u"ASS", 4: u"SRT", 5: u"VobSub", 6: u"PGS", 7: u"VTT", 8: u"SUB", 9: u"SUB", 10: u"MPL2", 11: u"TMPlayer", 12: u"SAMI"}


def sub_text(e):
	"""Un rand de subtitrare din getSubtitleList: DVB · germană / TXT 150 · germană / SRT · engleză."""
	try:
		kind = int(e[0])
	except Exception:
		return u""
	lang = language_name(e[4]) if len(e) > 4 else u""
	if kind == 0:
		pid = ival({"p": e[1]}, "p")
		return join([u"DVB", lang, (u"PID %d" % pid) if pid > 0 else u""])
	if kind == 1:
		try:
			page = int(e[2]) & 0xFF
			mag = int(e[3]) & 0x0F
			return join([u"TXT %x%02x" % (mag or 8, page), lang])
		except Exception:
			return join([u"TXT", lang])
	if kind == 2:
		# la un fisier de langa film, si numele lui, cand tuplul il are
		return join([SUB_FILE_KIND.get(ival({"k": e[2]}, "k"), u"") or tr("n_subs"), lang, e[6] if len(e) > 6 else u""])
	return u""


def same_sub(a, b):
	try:
		return a is not None and b is not None and len(a) >= 4 and len(b) >= 4 and tuple(a[:4]) == tuple(b[:4])
	except Exception:
		return False


# ---------------------------------------------------------------- audio

AUDIO_CODECS = (
	(u"E-AC3", u"E-AC-3"), (u"EAC3", u"E-AC-3"), (u"AC3+", u"E-AC-3"), (u"DD+", u"E-AC-3"), (u"E-AC-3", u"E-AC-3"),
	(u"AC4", u"AC-4"), (u"AC-4", u"AC-4"),
	(u"AC3", u"AC-3"), (u"AC-3", u"AC-3"), (u"DOLBY", u"AC-3"),
	(u"DTS-HD", u"DTS-HD"), (u"DTS", u"DTS"),
	(u"HE-AAC", u"HE-AAC"), (u"AAC+", u"HE-AAC"), (u"AAC_PLUS", u"HE-AAC"), (u"HEAAC", u"HE-AAC"),
	(u"AAC", u"AAC"), (u"MP3", u"MP3"), (u"LAYER 3", u"MP3"),
	(u"MPEG", u"MPEG"), (u"MP2", u"MPEG"), (u"LPCM", u"PCM"), (u"PCM", u"PCM"),
	(u"WMA", u"WMA"), (u"OPUS", u"Opus"), (u"VORBIS", u"Vorbis"), (u"FLAC", u"FLAC"),
)
MULTICHANNEL = (u"AC-3", u"E-AC-3", u"AC-4", u"DTS", u"DTS-HD")


def audio_codec(desc):
	d = u(desc).strip()
	if not d:
		return u""
	up = d.upper()
	for needle, name in AUDIO_CODECS:
		if needle in up:
			return name
	return d[:12]


_lang_memo = {}
# coduri locale sau fara o limba anume (nedeterminat, mai multe, fara vorbire, versiunea originala)
_FARA_LIMBA = (u"und", u"mul", u"mis", u"zxx", u"qaa")


def _limba_iso639(low):
	"""Numele limbii dupa Tools/ISO639.py (cod de 2 sau 3 litere), tradus daca imaginea are traducerea, sau gol."""
	if not (len(low) in (2, 3) and low.isalpha()) or low in _FARA_LIMBA or low.startswith(u"q"):
		return u""
	try:
		from Tools.ISO639 import LanguageCodes
		nume = LanguageCodes.get(str(low))
	except Exception:
		return u""
	if not nume:
		return u""
	try:
		return u(_(nume[0]))  # noqa: F821
	except NameError:
		return u(nume[0])


def _ca_tabelul(nume):
	"""Numele unei limbi din afara tabelului skinului (din traducerile imaginii: „Suedeză”) scris ca numele din tabel:
	cu litera mica in limbile interfetei care le scriu asa („germană”, deci „suedeză”), neschimbat in rest."""
	if not nume or not nume[:1].isupper():
		return nume
	model = tr(u"lang_deu")
	if model[:1].islower():
		return nume[:1].lower() + nume[1:]
	return nume


def language_name(code):
	"""Numele limbii unei piste, in limba receptorului, NUMAI cand textul e chiar o limba: un cod ISO 639 („deu”,
	„ger”, „de”, „deu/eng”) sau numele unei limbi („Deutsch”). getLanguage() da uneori textul componentei din EIT
	(„Stereo”, „Originalton”, „Audiodeskription”): acela nu e o limba si nu se arata (gol). Recunoasterea e cea a
	alegerii pistelor (Components/HdsPisteLimbi.limbiDinText, cu tabelul Tools/ISO639.py); numele vin din tabelul
	skinului (lang_*) sau, pentru celelalte limbi, din traducerile imaginii. Pe imaginile fara HdsPisteLimbi (skinul
	pe alta imagine) raman numai codurile din Tools/ISO639.py, pe care il au toate imaginile enigma2."""
	c = u(code).strip()
	if not c:
		return u""
	cheie_memo = (_lang["gen"], c)
	v = _lang_memo.get(cheie_memo)
	if v is not None:
		return v
	low = c.lower()
	if u"/" in low:
		low = low.split(u"/")[0].strip()
	v = u""
	if len(low) in (2, 3) and low.isalpha() and (u"lang_" + _LANG_ALIAS.get(low, low)) in _EN \
			and low not in _FARA_LIMBA:
		v = tr(u"lang_" + _LANG_ALIAS.get(low, low))
	else:
		try:
			from Components import HdsPisteLimbi as PL
		except ImportError:
			PL = None
		if PL is not None:
			try:
				coduri = PL.limbiDinText(c)
				if coduri:
					key = u"lang_" + coduri[0]
					v = tr(key) if key in _EN else _ca_tabelul(u(PL.numeLimba(coduri[0])))
			except Exception:
				v = u""
		else:
			v = _ca_tabelul(_limba_iso639(low))
	if len(_lang_memo) > 200:
		_lang_memo.clear()
	_lang_memo[cheie_memo] = v
	return v


# stream_content al componentelor de sunet din EIT (EN 300 468, descriptorul componentei): 2 MPEG-1 Layer II, 4 AC-3,
# 6 AAC / HE-AAC, 7 DTS
_EIT_SUNET = (2, 4, 6, 7)
# cuvintele care spun numai felul sunetului (le arata deja codecul): un text al componentei facut numai din ele nu e o
# varianta a pistei
_SUNET_TEHNIC = frozenset((u"stereo", u"mono", u"dual", u"dolby", u"digital", u"surround", u"ac3", u"ac-3", u"eac3",
	u"e-ac-3", u"aac", u"he-aac", u"mpeg", u"mp2", u"dd", u"dd+", u"ddp", u"dts", u"hd", u"sd", u"hq", u"audio", u"ton",
	u"tonspur", u"sound", u"channel", u"channels", u"kanal", u"multichannel", u"mehrkanal", u"mehrkanalton",
	u"zweikanal", u"zweikanalton", u"atmos", u"2ch", u"6ch", u"pcm"))


# codurile ISO 639 ale pistelor de sunet care nu sunt o limba: aceleasi etichete ca ecranul AUDIO (Screens/AudioSelection.py)
# si playerul din web (HdsWebControl/player.js), din traducerile imaginii
_SUNET_NEDEFINIT = (u"und", u"unk", u"xxx", u"---")
_SUNET_DESCRIERE = (u"qad", u"nar")


def _tradus(text):
	try:
		return u(_(text))  # noqa: F821
	except NameError:
		return u(text)


def _eticheta_fara_limba(low):
	"""Eticheta unui cod de pista care nu e o limba (litere mici), sau None pentru orice alt text: „Nedefinită” (und),
	„Descriere audio” (qad, nar), „Altă limbă” (mis), originala (qaa-qtz, tabelul skinului)."""
	if low in _SUNET_NEDEFINIT:
		return _tradus(u"Nedefinită")
	if low in _SUNET_DESCRIERE:
		return _tradus(u"Descriere audio")
	if low == u"mis":
		return _tradus(u"Altă limbă")
	if len(low) == 3 and low[0] == u"q" and u"a" <= low[1] <= u"t" and u"a" <= low[2] <= u"z":
		return tr(u"lang_qaa")
	return None


def varianta_pistei(text):
	"""Ce spune textul componentei din EIT despre o pista audio cand nu e o limba si nici numai felul sunetului:
	„Audiodeskription”, „Originalton”, „Klare Sprache” (asa cum il trimite postul). Gol pentru „Stereo”, „Dolby
	Digital 5.1” si altele ca ele, si pentru numele de limbi."""
	t = u(text).strip()
	if not t or language_name(t):
		return u""
	low = t.lower()
	eticheta = _eticheta_fara_limba(low)
	if eticheta is not None:
		return eticheta
	for ch in u"/,;:()[]|":
		low = low.replace(ch, u" ")
	cuvinte = low.split()
	if all(w in _SUNET_TEHNIC or w.replace(u".", u"").isdigit() for w in cuvinte):
		return u""
	return t[:24]


def componente_sunet(info):
	"""[(cod ISO 639, text)] ale componentelor de sunet ale emisiunii de acum (EIT, getComponentData: tag, tip,
	stream_content, ISO 639, text), in ordinea lor; [] fara emisiune sau fara descriptorii componentelor."""
	try:
		ev = info.getEvent(0) if info is not None else None
		lista = ev.getComponentData() if ev is not None else None
	except Exception:
		return []
	rez = []
	for c in lista or ():
		try:
			if int(c[2]) in _EIT_SUNET:
				rez.append((u(c[3]).strip().lower(), u(c[4]).strip()))
		except Exception:
			continue
	return rez


def limba_pistei(text, componente, vazute):
	"""(numele limbii, varianta) ale unei piste audio. getLanguage() da codul ISO 639 al pistei sau, cand emisiunea are
	descriptorul componentei in EIT, textul lui („Stereo”, „Audiodeskription”) in locul codului (getTrackInfo din
	lib/service/servicedvb.cpp). Atunci limba se ia din codul ISO al aceleiasi componente: componenta de sunet cu acelasi
	text; la mai multe cu acelasi text, a cata e pista printre cele cu textul acela (`vazute`: {text: cate piste au
	trecut}). `componente`: componente_sunet(info), sau o functie care le da (citite numai cand trebuie). Varianta:
	textul componentei cand spune ceva despre pista (varianta_pistei), „originală” la codul qaa fara alt text."""
	t = u(text).strip()
	nume = language_name(t)
	if nume or not t:
		return (nume, u"")
	varianta = varianta_pistei(t)
	if callable(componente):
		componente = componente()
	potrivite = [iso for iso, txt in componente or () if txt == t]
	if potrivite:
		k = vazute.get(t, 0)
		vazute[t] = k + 1
		iso = potrivite[min(k, len(potrivite) - 1)]
		nume = language_name(iso)
		if not nume and not varianta and iso == u"qaa":
			varianta = tr(u"lang_qaa")
	return (nume, varianta)


# ---------------------------------------------------------------- tuner

_fe_memo = {"t": -1000.0, "ref": None, "val": None}
_tuner_names = {}


def _fe_const(name):
	try:
		mod = sys.modules.get("enigma")
		return getattr(mod.iFrontendInformation, name)
	except Exception:
		return None


def ref_din_flux(sref):
	"""Serviciul se reda dintr-un flux (cale cu URL: releul DAB+ / DVB-T2 local, IPTV), deci nu are tuner al lui. Un
	astfel de serviciu pe tipul 1 e un canal PVR fara frontend: enigma2 da 0 pe tot la frontendInfo (lockState 0,
	frontendNumber 0), adica „tunerul A fara semnal”, ceea ce nu e adevarat."""
	return bool(parse_ref(sref)["url"])


def flux_releu(sref):
	"""Post DAB+ / program DVB-T2 din satelit venit prin releul local (http://127.0.0.1:<port>/dab/... sau /t2/...):
	are un purtator tinut de un tuner al receptorului, chiar daca semnalul lui nu se stie inca."""
	r = parse_ref(sref)
	return (bool(r["url"]) and is_local_host(r["host"]) and bool(r["urlpath"])
		and r["urlpath"][0].lower() in (u"dab", u"t2", u"t2mi"))


def _din_procent(p):
	"""Procent 0-100 -> valoarea pe 16 biti pe care percent16 o duce inapoi exact in acelasi procent."""
	return (max(0, min(100, int(p))) * 65535 + 99) // 100


def semnal_purtator(sref):
	"""Semnalul tunerului care tine purtatorul unui flux local (DAB+ / DVB-T2 din satelit), din receptie.json, in
	forma lui frontend_status: {'power','quality','lock','ber','number'}, numai cheile citite de controlor; None cand
	fisierul lipseste, e vechi, e al altui serviciu sau nu are inca nicio valoare de semnal."""
	p = rj_dict(receptie(sref) or {}, "purtator")
	val = {}
	for cheie, din in (("power", "semnal"), ("quality", "calitate")):
		v = ival(p, din)
		if 0 <= v <= 100:
			val[cheie] = _din_procent(v)
	if isinstance(p.get("prins"), bool):
		val["lock"] = 1 if p["prins"] else 0
	if ival(p, "ber") >= 0:
		val["ber"] = ival(p, "ber")
	if not val:
		return None
	if 0 <= ival(p, "tuner") <= 25:
		val["number"] = ival(p, "tuner")
	val["purtator"] = True
	return val


def frontend_status(service, sref):
	"""{'power','quality','ber','lock','number'} citite din placa, memo 0,5 s pe serviciu. La un serviciu redat dintr-un
	flux: tunerul care tine purtatorul (semnal_purtator, cu 'purtator': True) sau None, niciodata zerourile canalului
	PVR."""
	now = _now()
	if _fe_memo["ref"] == sref and 0.0 <= now - _fe_memo["t"] < 0.5:
		return _fe_memo["val"]
	val = None
	try:
		din_flux = ref_din_flux(sref)
		fe = None if din_flux else (service and service.frontendInfo())
		if din_flux:
			val = semnal_purtator(sref)
		elif fe:
			val = {}
			got = False
			for key, cname in (("power", "signalPower"), ("quality", "signalQuality"), ("ber", "bitErrorRate"), ("lock", "lockState"), ("number", "frontendNumber")):
				c = _fe_const(cname)
				if c is None:
					continue
				try:
					v = fe.getFrontendInfo(c)
					val[key] = int(v)
					got = True
				except Exception:
					pass
			if not got:
				try:
					d = fe.getAll(False)
				except Exception:
					d = None
				if isinstance(d, dict) and d:
					val = {
						"power": ival(d, "tuner_signal_power"),
						"quality": ival(d, "tuner_signal_quality"),
						"ber": ival(d, "tuner_bit_error_rate"),
						"lock": ival(d, "tuner_locked"),
						"number": ival(d, "tuner_number"),
					}
				else:
					val = None
	except Exception as e:
		log_once("frontend", e)
		val = None
	_fe_memo["t"] = now
	_fe_memo["ref"] = sref
	_fe_memo["val"] = val
	return val


def percent16(v):
	try:
		v = int(v)
	except Exception:
		return None
	if v < 0:
		return None
	return max(0, min(100, v * 100 // 65535))


def tuner_name(number):
	try:
		number = int(number)
	except Exception:
		return u""
	if number < 0 or number > 25:
		return u""
	if number in _tuner_names:
		return _tuner_names[number]
	kind = u""
	try:
		mod = sys.modules.get("Components.NimManager")
		nm = getattr(mod, "nimmanager", None) if mod is not None else None
		slot = nm.nim_slots[number] if nm is not None else None
		if slot is not None:
			for attr in ("getType", "getFriendlyType"):
				fn = getattr(slot, attr, None)
				if fn is not None:
					try:
						kind = u(fn())
					except Exception:
						kind = u""
					if kind:
						break
			if not kind:
				kind = u(getattr(slot, "description", u""))
	except Exception:
		kind = u""
	name = join([u"%c" % (65 + number), kind[:24]])
	if len(_tuner_names) > 32:
		_tuner_names.clear()
	_tuner_names[number] = name
	return name


# ---------------------------------------------------------------- serviciul, citit o data pe eveniment

def isi(name):
	"""Constanta iServiceInformation, sau None pe imaginile unde lipseste."""
	try:
		return getattr(_ISI, name, None)
	except Exception:
		return None


def hbbtv_semnalat(r):
	"""HbbTV pe canalul care ruleaza: True / False / None (nu se stie).
	Un nucleu cu sHBBTVUrl raspunde el. Nucleul imaginii HDSatelit citeste AIT-ul si da
	sAITPID din PMT (lib/dvb/pmt.cpp): 0 = fara AIT HbbTV, peste 0 = PID-ul AIT. Cat PMT-ul nu e citit (-1), si pe
	imaginile fara sAITPID, raspunsul vine din baza pistelor (Components/HdsPisteCanale.py, citita din PMT); un canal
	pe care baza nu-l stie e „nu se stie”, nu „nu”. Daca AIT-ul are si o aplicatie de pornit la ROSU: hbbtv_rosu."""
	if isi("sHBBTVUrl") is not None:
		return bool(r.gets("sHBBTVUrl"))
	# nucleul care da PID-ul AIT din PMT (sAITPID: -1 PMT necitit sau program din cache, 0 fara AIT, altfel PID-ul)
	if isi("sAITPID") is not None:
		v = r.geti("sAITPID")
		if v >= 0:
			return v > 0
	try:
		from Components import HdsPisteCanale, HdsIndexCanale
		cheie = HdsIndexCanale.cheie_din_ref(r.sref())
		rec = HdsPisteCanale.baza().inregistrare(cheie) if cheie else None
	except Exception:
		return None
	if rec and "hb" in rec:
		return rec["hb"] == 1
	return None


def hbbtv_rosu(r):
	"""Semnul rosu HbbTV din bara: True cand AIT-ul citit de nucleu pe canalul redat are o aplicatie de pornit la ROSU
	si setarea semnului e pornita (Components/HdsHbbtv.arata_semn, numai pe imaginea HDSatelit). Pe imaginile fara
	sAITPID / sHBBTVAit sau fara modul: False."""
	if isi("sAITPID") is None or isi("sHBBTVAit") is None:
		return False
	if r.geti("sAITPID") <= 0:
		return False

	def fn():
		from Components import HdsHbbtv
		return HdsHbbtv.arata_semn(r.info(), _ISI)
	return r._memo("hbbtv_rosu", fn) is True


def text_hbbtv(r):
	"""„da” / „nu are” (canalul nu anunta HbbTV) / „nu se știe” (nu s-a citit inca) pentru afisaj."""
	v = hbbtv_semnalat(r)
	return tr("unknown") if v is None else (tr("yes") if v else tr("no_value"))


class Snap(object):
	__slots__ = ("what", "src", "f")


_snap = [None]


def snapshot(source, what):
	"""Datele citite din serviciu se impart intre toate convertoarele care primesc acelasi eveniment.

	Sursa trimite acelasi tuplu `what` tuturor convertoarelor legate de ea, deci
	`what is` + aceeasi sursa inseamna acelasi moment. Nu se tine niciun obiect enigma2
	(serviciul nu ramane viu dupa schimbare), doar valori Python.
	"""
	s = _snap[0]
	if what is not None and s is not None and s.what is what and s.src == id(source):
		return s
	s = Snap()
	s.what = what
	s.src = id(source)
	s.f = {}
	if what is not None:
		_snap[0] = s
	return s


class Reader(object):
	"""Citiri lenese din serviciul curent; fiecare valoare o singura data pe eveniment."""

	def __init__(self, source, what):
		self.source = source
		self.f = snapshot(source, what).f
		self._service = False
		self._info = False

	def service(self):
		if self._service is False:
			try:
				self._service = self.source.service
			except Exception:
				self._service = None
		return self._service

	def info(self):
		if self._info is False:
			self._info = None
			try:
				s = self.service()
				if s is not None:
					i = s.info()
					if i:
						self._info = i
			except Exception:
				self._info = None
		return self._info

	def _memo(self, key, fn):
		f = self.f
		if key in f:
			return f[key]
		try:
			v = fn()
		except Exception as e:
			log_once(key, e)
			v = None
		f[key] = v
		return v

	def geti(self, name):
		def fn():
			c = isi(name)
			i = self.info()
			if c is None or i is None:
				return -1
			v = i.getInfo(c)
			return int(v) if v is not None else -1
		v = self._memo("i:" + name, fn)
		return -1 if v is None else v

	def gets(self, name):
		def fn():
			c = isi(name)
			i = self.info()
			if c is None or i is None:
				return u""
			return u(i.getInfoString(c))
		v = self._memo("s:" + name, fn)
		return v or u""

	def sref(self):
		"""Referinta din info; daca imaginea o da goala, cea tinuta de sursa (session.CurrentService.serviceref)."""
		s = self.gets("sServiceref")
		if s or self.info() is None:
			return s

		def fn():
			ref = getattr(self.source, "serviceref", None)
			ts = getattr(ref, "toString", None)
			return u(ts()) if ts is not None else u""
		return self._memo("sref_src", fn) or u""

	def ref(self):
		v = self._memo("ref", lambda: parse_ref(self.sref()))
		return v or parse_ref(u"")

	def tp(self):
		def fn():
			i = self.info()
			if i is None:
				return {}
			d = None
			c = isi("sTransponderData")
			if c is not None:
				try:
					d = i.getInfoObject(c)
				except Exception:
					d = None
			if not isinstance(d, dict) or not d:
				d = None
				try:
					fe = self.service().frontendInfo()
					if fe:
						for call in (lambda: fe.getTransponderData(True), lambda: fe.getAll(True)):
							try:
								d = call()
							except Exception:
								d = None
							if isinstance(d, dict) and d:
								break
				except Exception:
					d = None
			return d if isinstance(d, dict) else {}
		return self._memo("tp", fn) or {}

	def caids(self):
		def fn():
			i = self.info()
			c = isi("sCAIDs")
			if i is None or c is None:
				return []
			return clean_caids(i.getInfoObject(c))
		return self._memo("caids", fn) or []

	def crypted(self):
		return self.geti("sIsCrypted") == 1 or bool(self.caids())

	def acces_acum(self):
		"""„criptat” / „fta” din analiza de acum (CAID-urile sau sIsCrypted din PMT), None cat nu s-a aflat inca:
		nucleul da sIsCrypted = -1 pana vine PMT-ul (servicedvb.cpp), iar -1 nu inseamna FTA."""
		if self.caids() or self.geti("sIsCrypted") == 1:
			return "criptat"
		if self.geti("sIsCrypted") == 0:
			return "fta"
		return None

	def acces(self):
		"""Ce arata bara pentru acces: starea de acum; pana vine analiza, cea tinuta minte pe canal (modulul imaginii
		Components/HdsAccesCanale.py), iar fara ea None = nimic pe ecran. Pe imaginile
		fara modul nu se tine minte nimic, dar nici nu se mai arata FTA inainte de analiza."""
		def fn():
			acum = self.acces_acum()
			try:
				from Components import HdsAccesCanale
			except ImportError:
				return acum
			try:
				return HdsAccesCanale.acces(self.sref(), acum)
			except Exception as e:
				log_once("acces tinut minte", e)
				return acum
		return self._memo("acces", fn)

	def caidpids(self):
		def fn():
			i = self.info()
			c = isi("sCAIDPIDs")
			if i is None or c is None:
				return []
			return clean_caidpids(i.getInfoObject(c))
		return self._memo("caidpids", fn) or []

	def track_list(self):
		"""([(codec, limba, pid), ...], indicele pistei curente sau -1). Toate pistele audio."""
		def fn():
			s = self.service()
			a = s and s.audioTracks()
			if not a:
				return ([], -1)
			n = int(a.getNumberOfTracks() or 0)
			if n <= 0:
				return ([], -1)
			try:
				cur = int(a.getCurrentTrack())
			except Exception:
				cur = -1
			rows = []
			limbi = []
			vazute = {}
			comp = []

			def componente():
				# componentele EIT se citesc o singura data, numai daca o pista are textul componentei in locul limbii
				if not comp:
					comp.append(componente_sunet(self.info()))
				return comp[0]
			for k in range(min(n, 32)):
				ti = a.getTrackInfo(k)
				desc = lang = u""
				pid = -1
				if ti:
					for attr in ("getDescription", "getLanguage", "getPID"):
						fnc = getattr(ti, attr, None)
						if fnc is None:
							continue
						try:
							v = fnc()
						except Exception:
							continue
						if attr == "getDescription":
							desc = u(v)
						elif attr == "getLanguage":
							lang = u(v)
						else:
							pid = ival({"p": v}, "p")
				nume, varianta = limba_pistei(lang, componente, vazute)
				limbi.append(nume)
				# pistele „Audiodeskription” / „Originalton” raman deosebite: varianta langa limba
				rows.append((audio_codec(desc), join([nume, varianta]), pid))
			self.f["limbi_piste"] = limbi
			return (rows, cur if 0 <= cur < n else -1)
		v = self._memo("tracks", fn)
		return v if v else ([], -1)

	def sub_list(self):
		"""(lista de tupluri din getSubtitleList cu cel putin 5 campuri, pista pornita sau None)."""
		def fn():
			s = self.service()
			sub = s and s.subtitle()
			if not sub:
				return ([], None)
			lst = sub.getSubtitleList()
			rows = [e for e in lst if isinstance(e, (list, tuple)) and len(e) >= 5] if isinstance(lst, (list, tuple)) else []
			cur = None
			fnc = getattr(sub, "getCachedSubtitle", None)
			if fnc is not None:
				try:
					cur = fnc()
				except Exception:
					cur = None
			return (rows[:32], cur if isinstance(cur, (list, tuple)) else None)
		v = self._memo("sublist", fn)
		return v if v else ([], None)

	def rj(self):
		return self._memo("rj", lambda: receptie(self.sref()))

	def audio(self):
		"""(numar piste, codec pista curenta, limba pista curenta)."""
		def fn():
			s = self.service()
			a = s and s.audioTracks()
			if not a:
				return (0, u"", u"")
			n = int(a.getNumberOfTracks() or 0)
			if n <= 0:
				return (0, u"", u"")
			cur = -1
			try:
				cur = int(a.getCurrentTrack())
			except Exception:
				cur = -1
			if cur < 0 or cur >= n:
				cur = 0
			ti = a.getTrackInfo(cur)
			if not ti:
				return (n, u"", u"")
			desc = u""
			lang = u""
			try:
				desc = u(ti.getDescription())
			except Exception:
				pass
			try:
				lang = u(ti.getLanguage())
			except Exception:
				pass
			nume = language_name(lang)
			if not nume and lang:
				# textul componentei din EIT in locul limbii: limba din codul ISO al componentei, ca in track_list
				self.track_list()
				limbi = self.f.get("limbi_piste") or []
				nume = limbi[cur] if 0 <= cur < len(limbi) else u""
			return (n, audio_codec(desc), nume)
		return self._memo("audio", fn) or (0, u"", u"")

	def subtitles(self):
		def fn():
			s = self.service()
			sub = s and s.subtitle()
			if not sub:
				return 0
			lst = sub.getSubtitleList()
			return len(lst) if isinstance(lst, (list, tuple)) else 0
		return self._memo("subs", fn) or 0

	def kind(self):
		"""Felul receptiei: s, c, t, a, dab_native, dab_relay, dab_streamer, t2mi_url, ip, file, record sau ''."""
		def fn():
			if self.info() is None:
				return ""
			r = self.ref()
			path = r["path"].lower()
			if r["type"] == 4115 or path.startswith(u"dab://"):
				return "dab_native"
			if r["url"]:
				host = r["host"]
				port = host_port(host)
				up = [p.lower() for p in r["urlpath"]]
				if port == 5237 and is_local_host(host):
					return "dab_streamer"
				if u"t2mi" in up:
					return "t2mi_url"
				if port == 8888 and is_local_host(host):
					return "dab_relay"
				if u"dab" in up and is_local_host(host):
					return "dab_relay"
				return "ip"
			k = tp_kind(self.tp())
			if path.startswith(u"/"):
				return "record" if r["type"] in (1, 257) else "file"
			if k == "dab":
				return "dab_native"
			if k:
				return k
			if r["type"] not in (1, 257, -1):
				return "file"
			return ""
		return self._memo("kind", fn) or ""

	def rj_type(self):
		d = self.rj()
		if not d:
			return u""
		return u(d.get("tip")).upper()

	def is_dab(self):
		k = self.kind()
		if k in ("dab_native", "dab_relay", "dab_streamer"):
			return True
		return self.rj_type().startswith(u"DAB")

	def is_t2mi(self):
		k = self.kind()
		if k == "t2mi_url":
			return True
		if k == "s" and ival(self.tp(), "t2mi_plp_id") >= 0:
			return True
		if self.rj_type() == u"T2-MI":
			return True
		return k == "ip" and bool(rj_dict(self.rj() or {}, "t2"))

	def carrier_tp(self):
		"""Transponderul purtator pentru DAB sau T2-MI venit ca flux: din json, din URL, din referinta 4115."""
		def fn():
			d = self.rj()
			p = rj_dict(d or {}, "purtator")
			if p:
				return p
			k = self.kind()
			r = self.ref()
			cref = None
			if k == "dab_native":
				f = r["fields"]
				if len(f) > 6:
					cref = u"1:0:%s:0:0:0:" % u":".join(f[2:7])
			elif k == "dab_streamer" and len(r["urlpath"]) > 1:
				cref = r["urlpath"][1]
			elif k == "t2mi_url":
				up = r["urlpath"]
				for i, seg in enumerate(up):
					if seg.lower() == u"t2mi" and len(up) > i + 2:
						cref = up[i + 2]
						break
			if not cref or cref.count(u":") < 9:
				return {}
			return static_tp(cref)
		return self._memo("carrier", fn) or {}


_static_tp_memo = {"ref": None, "tp": {}}


def static_tp(cref):
	"""Transponderul din lista de canale pentru o referinta (fara acordare)."""
	if _static_tp_memo["ref"] == cref:
		return _static_tp_memo["tp"]
	tp = {}
	try:
		mod = sys.modules.get("enigma")
		ref = mod.eServiceReference(str(cref) if not PY2 else u(cref).encode("utf-8"))
		sinfo = mod.eServiceCenter.getInstance().info(ref)
		c = isi("sTransponderData")
		if sinfo and c is not None:
			d = sinfo.getInfoObject(ref, c)
			if isinstance(d, dict):
				tp = d
	except Exception as e:
		log_once("static_tp", e)
		tp = {}
	_static_tp_memo["ref"] = cref
	_static_tp_memo["tp"] = tp
	return tp


# ================================================================ OSD extins

def reader_etp(r):
	"""(transponder, fel) pentru campurile de receptie; la DAB/T2-MI prin flux, purtatorul. Memo pe eveniment."""
	def fn():
		k = r.kind()
		if k in ("s", "c", "t", "a"):
			return (r.tp(), k)
		if k == "record":
			tp = r.tp()
			return (tp, tp_kind(tp))
		if k in ("dab_native", "dab_relay", "dab_streamer", "t2mi_url", "ip"):
			tp = r.carrier_tp()
			if tp:
				kk = tp_kind(tp)
				if not kk and tp.get("frequency"):
					kk = "s"
				return (tp, kk)
		return ({}, "")
	v = r._memo("etp", fn)
	return v if v else ({}, "")


# ---------------------------------------------------------------- optiuni comune: pagina si filtre de receptie

FILTERS = ("OnS", "OnC", "OnT", "OnT1", "OnT2", "OnDvb", "OnIp", "OnRotor")
# felurile de receptie prin flux care au un purtator DVB tinut de un tuner al receptorului (reader_etp)
FEL_FLUX_PURTATOR = ("dab_native", "dab_relay", "dab_streamer", "t2mi_url", "ip")


def parse_page_filters(tokens):
	"""(pagina 1..6 sau 0, filtre) din bucatile argumentului: `P2`, `OnS`, `OnC`... Restul se ignora."""
	page = 0
	filters = []
	for t in tokens:
		t = str(t).strip()
		if len(t) == 2 and t[0] == "P" and t[1] in "123456":
			page = int(t[1])
		elif t in FILTERS and t not in filters:
			filters.append(t)
	return page, tuple(filters)


def filter_ok(r, filters):
	"""Adevarat daca felul receptiei se potriveste cu macar un filtru (fara filtre: mereu)."""
	if not filters:
		return True
	if r.info() is None:
		return False
	k = r.kind()
	tp, ek = reader_etp(r)
	for f in filters:
		if f == "OnS" and ek == "s":
			return True
		if f == "OnC" and ek == "c":
			return True
		if f == "OnT" and ek == "t":
			return True
		if f == "OnT1" and ek == "t" and not ter_is_t2(tp):
			return True
		if f == "OnT2" and ek == "t" and ter_is_t2(tp):
			return True
		if f == "OnRotor" and k == "s":
			n = fe_number(r)
			if n >= 0 and has_rotor(n, ival(tp, "orbital_position")):
				return True
		# un post DAB+ / un program DVB-T2 venit prin releu: semnalul e al tunerului care tine purtatorul (DVB)
		if f == "OnDvb" and (k in ("s", "c", "t", "a") or (k in FEL_FLUX_PURTATOR and ek in ("s", "c", "t", "a"))):
			return True
		if f == "OnIp" and k not in ("s", "c", "t", "a", "") and ek not in ("s", "c", "t", "a"):
			return True
	return False


# ---------------------------------------------------------------- pagini (SecondInfoBar: manual, cu rotire doar la cerere)

PAGES = (1, 2, 3, 4, 5, 6)
# ordinea in care se arata paginile: ghidul canalului (5) primul, apoi paginile tehnice. Numerele din skin (P1..P6,
# Page,<n>) raman; se schimba doar locul lor in lista paginilor valide, deci pozitia, punctele si titlul.
PAGE_ORDER = (5, 1, 2, 3, 4, 6)
EPG_PAGE = 5
PAGE_KEYS = {1: "page_reception", 2: "page_antenna", 3: "page_av", 4: "page_service", 5: "page_guide", 6: "page_receiver"}
# cat timp ramane valabila cererea de redeschidere a barei pe ghid dupa un ecran deschis din ea (secunde)
PAGE_RESUME_S = 5.0
# 0 = manual (implicit): pagina se schimba doar din tastele ecranului (stanga / dreapta) si ramane
# pe loc oricat sta ecranul deschis. Altfel secundele pe pagina, alese in panoul de setari al skinului (HdsSkinSetari):
# config.plugins.HdsSkin.pagina, sau `rotire=` / `pagina=` din fisierul lui, daca pluginul nu a definit inca optiunea
PAGE_MANUAL = 0.0
PAGE_PERIOD = PAGE_MANUAL
PAGE_PERIODS = (0, 4, 5, 6, 7, 8, 10, 12, 15, 20)
# o versiune mai veche a panoului scria `pagina=7` in orice .conf salvat, si cand nu alesese nimeni timpul (7 era
# implicitul); deci `pagina=7` nu e o alegere: se trece mai departe (config, apoi manual). Celelalte valori vechi raman.
PAGE_OLD_DEFAULT = 7
PAGE_CONF = "/etc/enigma2/hdsatelit-culori.conf"

try:
	import weakref as _weakref
except Exception:
	_weakref = None

# active = pagina aratata; valid = paginile cu date pentru serviciul redat, in ordinea PAGE_ORDER; t0 = cand a pornit
# numaratoarea rotirii; period = secundele pe pagina (0 = manual), citite o data la fiecare aratare (page_start), nu la
# tic; neatins = de la aratare omul nu a apasat nicio tasta de pagina sau de cursor (atunci bara trece singura pe ghid
# cand vine EPG-ul); reia = (serviciu, id emisiune, moment) dupa un ecran deschis din bara, ca bara sa se redeschida
# pe ghid cu cursorul pe aceeasi emisiune
_pages = {"active": 5, "valid": PAGE_ORDER, "t0": 0.0, "slot": 0, "shown": False, "period": PAGE_PERIOD,
	"neatins": False, "reia": None}
_page_conf = {"mtime": None, "v": None}


def _page_period_value(v):
	"""Secundele pe pagina din text (0 = manual), doar valorile din panou; altfel None. Nu arunca."""
	try:
		n = int(v.strip())
	except Exception:
		return None
	return float(n) if n in PAGE_PERIODS else None


def _page_period_conf():
	"""Alegerea din fisierul panoului; recitit doar cand se schimba mtime. None daca lipseste.
	`rotire=` (forma noua): 0 = manual sau secundele. `pagina=` (forma veche), doar cand lipseste `rotire=`:
	7 = implicitul vechi, nu o alegere (None); celelalte valori raman."""
	try:
		st = os.stat(PAGE_CONF)
	except Exception:
		_page_conf["mtime"] = None
		_page_conf["v"] = None
		return None
	try:
		if _page_conf["mtime"] != st.st_mtime:
			_page_conf["mtime"] = st.st_mtime
			_page_conf["v"] = None
			nou = vechi = None
			with open(PAGE_CONF, "rb") as f:
				for line in f.read(4096).splitlines():
					line = line.strip()
					if line.startswith(b"rotire="):
						nou = _page_period_value(line.split(b"=", 1)[1])
					elif line.startswith(b"pagina="):
						vechi = _page_period_value(line.split(b"=", 1)[1])
						if vechi == PAGE_OLD_DEFAULT:
							vechi = None
			_page_conf["v"] = nou if nou is not None else vechi
	except Exception as e:
		_page_conf["v"] = None
		log_once("page_period", e)
	return _page_conf["v"]


def page_period_read():
	"""Secundele pe pagina, 0 = manual: fisierul panoului HdsSkinSetari (scris atomic la salvare; ramane si cand
	/etc/enigma2/settings nu apuca sa se salveze), altfel optiunea din config, altfel manual.
	Ieftin (un stat, fisierul doar cand s-a schimbat); se cheama doar din page_start. Nu arunca."""
	v = _page_period_conf()
	if v is not None:
		return v
	try:
		mod = sys.modules.get("Components.config")
		v = _page_period_value(mod.config.plugins.HdsSkin.pagina.value)
		if v is not None:
			return v
	except Exception:
		pass
	return PAGE_PERIOD
# pagina (0 = orice schimbare) -> {id: convertor}, cu referinte slabe (nu tin convertorul viu)
_page_subs = {}


def page_active():
	return _pages["active"]


def page_hidden(page):
	"""Convertorul paginii `page` (P<n>) nu are ce arata: pagina nu e cea activa sau ecranul cu pagini e ascuns. Cat e
	ascuns, page_stop lasa activa prima pagina din ordine (ghidul), deci verificarea numai a paginii active ar face
	convertoarele ei sa se recalculeze la fiecare eveniment al serviciului (la fiecare zap, de cateva ori), pentru un
	ecran care nu se vede. La aratare page_start le reimprospateaza."""
	return bool(page) and (not _pages["shown"] or _pages["active"] != page)


def page_valid():
	return _pages["valid"]


def page_subscribe(conv, page):
	try:
		d = _page_subs.get(page)
		if d is None:
			d = _weakref.WeakValueDictionary() if _weakref is not None else {}
			_page_subs[page] = d
		d[id(conv)] = conv
	except Exception as e:
		log_once("page_subscribe", e)


def page_unsubscribe(conv):
	try:
		for d in list(_page_subs.values()):
			d.pop(id(conv), None)
	except Exception:
		pass


def page_set(active, valid=None):
	"""Schimba pagina activa (si lista paginilor valide); anunta doar convertoarele atinse. Intoarce True daca s-a schimbat ceva.
	La schimbarea paginii (tasta sau rotire) numaratoarea rotirii o ia de la capat: pagina aleasa sta o perioada intreaga."""
	old = _pages["active"]
	oldvalid = _pages["valid"]
	valid = page_order(valid if valid is not None else oldvalid) or (1,)
	try:
		active = int(active)
	except Exception:
		active = 0
	if active not in PAGES:
		active = valid[0]
	if active == old and valid == oldvalid:
		return False
	_pages["active"] = active
	_pages["valid"] = valid
	if active != old:
		_pages["t0"] = _now()
		_pages["slot"] = 0
	targets = {}
	for p in (0, old, active):
		d = _page_subs.get(p)
		if d is None:
			continue
		try:
			for k, conv in list(d.items()):
				targets[k] = conv
		except Exception:
			pass
	for conv in list(targets.values()):
		try:
			conv._on_page()
		except Exception as e:
			log_once("page notify", e)
	return True


def page_order(pages):
	"""Paginile date, fara dubluri, in ordinea de aratare (PAGE_ORDER); numerele necunoscute se lasa deoparte."""
	try:
		have = set([int(p) for p in pages])
	except Exception:
		return ()
	return tuple([p for p in PAGE_ORDER if p in have])


def valid_pages(r):
	"""Paginile cu date pentru serviciul redat, in ordinea de aratare: 5 ghidul doar cu EPG (emisiunea de acum din
	serviciu sau program in cache-ul EPG), 1 receptia mereu, 2 antena doar la receptie DVB, 3 imagine si sunet cand
	ruleaza ceva, 4 serviciu la DVB si inregistrari, 6 receptor mereu."""
	pages = set([1, 6])
	try:
		if r.info() is not None:
			k = r.kind()
			if k in ("s", "c", "t", "a"):
				pages.add(2)
			pages.add(3)
			if k in ("s", "c", "t", "a", "record"):
				pages.add(4)
			if event_data(r, 0) or epg_list(r):
				pages.add(EPG_PAGE)
	except Exception as e:
		log_once("valid_pages", e)
	return page_order(pages)


def _page_before(valid, cur):
	"""Pagina valida care vine in ordine chiar inaintea lui `cur`; daca nu e niciuna, prima valida de dupa ea."""
	try:
		k = PAGE_ORDER.index(cur)
	except ValueError:
		return valid[0]
	for p in reversed(PAGE_ORDER[:k]):
		if p in valid:
			return p
	for p in PAGE_ORDER[k + 1:]:
		if p in valid:
			return p
	return valid[0]


def page_next(valid, cur, d):
	"""Pagina de la `d` locuri de `cur` in lista `valid` (ordinea de aratare), cu trecere de la un capat la altul."""
	valid = tuple(valid) or (1,)
	if cur not in valid:
		return valid[0]
	return valid[(valid.index(cur) + (1 if d > 0 else -1)) % len(valid)]


def page_touch():
	"""O tasta a omului pe bara (pagina, cursor, descriere): bara nu mai e „neatinsa”, cererea de redeschidere se
	sterge, iar rotirea (daca e aleasa) o ia de la capat, ca pagina sa nu se schimbe sub mana lui."""
	_pages["neatins"] = False
	_pages["reia"] = None
	_pages["t0"] = _now()
	_pages["slot"] = 0


def page_step(d):
	"""Tasta de pagina: urmatoarea (d > 0) sau precedenta pagina valida, dupa locul in ordinea de aratare, cu trecere
	de la un capat la altul. Intoarce pagina aratata."""
	nxt = page_next(_pages["valid"], _pages["active"], d)
	page_touch()
	page_set(nxt)
	return nxt


def page_resume_set(sref, event_id):
	"""Dupa un ecran deschis din bara (temporizator, ghid): bara se redeschide pe ghid, cu cursorul pe emisiunea
	`event_id`, daca serviciul e acelasi si nu au trecut mai mult de PAGE_RESUME_S secunde."""
	_pages["reia"] = (norm_ref(sref), event_id, _now())


def _page_resume(r):
	"""Id-ul emisiunii din cererea de redeschidere, daca e inca valabila pentru serviciul redat; altfel None (si
	cererea expirata se sterge)."""
	v = _pages.get("reia")
	if not v:
		return None
	sref, eid, t = v
	dt = _now() - t
	if not 0.0 <= dt <= PAGE_RESUME_S or not sref or sref != norm_ref(r.sref()):
		_pages["reia"] = None
		return None
	return eid


def page_start(r):
	"""Ecranul se arata (sau serviciul se schimba cat se vede): prima pagina valida din ordine (ghidul cand exista
	EPG); dupa un ecran deschis din bara, ghidul cu cursorul pe aceeasi emisiune. Cu rotire, numaratoarea porneste
	de acum. Se cheama de doua ori la aratare (ecranul si PageTick): cererea de redeschidere nu se consuma aici."""
	era_ascuns = not _pages["shown"]
	_pages["shown"] = True
	_pages["t0"] = _now()
	_pages["slot"] = 0
	_pages["period"] = page_period_read()
	_pages["neatins"] = True
	sel_reset()
	epg_reset()
	ca_reset()
	valid = valid_pages(r)
	target = valid[0]
	eid = _page_resume(r)
	if eid is not None and EPG_PAGE in valid:
		target = EPG_PAGE
		epg_select_id(eid)
	# aceeasi pagina ca la ascundere: page_set nu anunta nimic, deci pagina se redeseneaza aici: ghidul mereu (cursorul
	# sters la ascundere, sau pus pe emisiunea de dinainte de ecranul deschis din bara), oricare alta la trecerea din
	# ascuns in vazut (cat a fost ascuns ecranul, convertoarele ei nu s-au recalculat: page_hidden)
	if not page_set(target, valid) and (target == EPG_PAGE or era_ascuns):
		page_refresh(target)


def page_stop():
	"""Ecranul se ascunde: inapoi la prima pagina din ordine, ca la urmatoarea deschidere sa se vada intai ea. Cererea
	de redeschidere nu se sterge aici (ecranul deschis din bara o ascunde)."""
	_pages["shown"] = False
	_pages["slot"] = 0
	sel_reset()
	epg_reset()
	ca_reset()
	valid = _pages["valid"]
	page_set(valid[0] if valid else 1)


def page_tick(r, dirty=False):
	"""Chemat de PageTick la fiecare 500 ms si cand vin date noi despre serviciu (dirty, de ex. EPG-ul).
	Manual (period 0): pagina nu se misca singura; la dirty se reface doar lista paginilor valide si pagina ramane
	aceeasi cat e valida. Cu rotire: nu citeste nimic daca nu a venit randul schimbarii; pagina urmatoare dupa ordinea
	de aratare. Cat bara e neatinsa, ghidul care tocmai a devenit valid (EPG venit dupa aratare) trece in fata.
	Pagina care nu mai e valida trece pe cea valida dinaintea ei in ordine (1 e mereu valida)."""
	if not _pages["shown"]:
		return False
	period = _pages["period"]
	advance = False
	if period and period > 0:
		now = _now()
		if now < _pages["t0"]:
			_pages["t0"] = now
			_pages["slot"] = 0
		slot = int((now - _pages["t0"]) / period)
		advance = slot != _pages["slot"]
		_pages["slot"] = slot
	if not advance and not dirty:
		return False
	valid = valid_pages(r)
	cur = _pages["active"]
	if advance:
		nxt = page_next(valid, cur, 1)
	elif _pages["neatins"] and valid[0] == EPG_PAGE and cur != EPG_PAGE:
		nxt = EPG_PAGE
	elif cur in valid:
		nxt = cur
	else:
		nxt = _page_before(valid, cur)
	return page_set(nxt, valid)


def page_dots():
	"""`·  •  ·  ·` : un semn pe fiecare pagina valida, `•` pe cea activa (fontul skinului nu are cercuri)."""
	return u"  ".join([u"•" if p == _pages["active"] else u"·" for p in _pages["valid"]])


def page_position():
	"""(pozitia paginii active intre cele valide, 1..n; n)."""
	valid = _pages["valid"]
	try:
		return valid.index(_pages["active"]) + 1, len(valid)
	except Exception:
		return 1, len(valid)


def page_refresh(page=None):
	"""Redeseneaza convertoarele unei pagini (implicit cea activa) fara s-o schimbe, doar cat se vede ecranul.
	Chemat dupa o alegere din afisaj sau din web: selectTrack si enableSubtitles nu trimit niciun eveniment de serviciu.
	Toti primesc acelasi `what` nou, deci serviciul se citeste o singura data (Reader / snapshot). True daca a anuntat."""
	if not _pages["shown"]:
		return False
	page = _pages["active"] if page is None else page
	what = (-1, "hds_refresh", _now())
	targets = {}
	d = _page_subs.get(page)
	if d is not None:
		try:
			for k, conv in list(d.items()):
				targets[k] = conv
		except Exception:
			pass
	for conv in list(targets.values()):
		try:
			fn = getattr(conv, "_on_refresh", None)
			if fn is not None:
				fn(what)
			else:
				conv._on_page()
		except Exception as e:
			log_once("page refresh", e)
	return bool(targets)


# ---------------------------------------------------------------- pagina 3: cursorul si alegerile din afisaj
# Afisajul detaliat e interactiv pe pagina 3 (Video, audio): sus / jos muta un cursor pe o singura lista, in ordinea
# pistele audio, „Fara subtitrari”, subtitrarile, apoi „Alte alegeri” (canal audio, downmix AC3 / DTS). OK alege
# randul: pe imaginea HDSatelit din Screens/SecondInfoBar.py, pe celelalte din HdsSkinSetari/taste_afisaj.py. Starea
# sta aici, langa pagini, ca sa mearga pe orice imagine care are skinul. Cursorul se tine dupa cheie (pista i, tuplul
# subtitrarii, numele alegerii), nu dupa pozitie: o lista reordonata nu muta cursorul pe alta pista; o pista care
# dispare il lasa pe randul de la aceeasi pozitie (taiat la ultimul rand).
# Alegerea efectiva a pistei si a subtitrarii NU se face aici: se cheama modulul imaginii Components/HdsPisteLimbi.py
# (tine minte alegerea facuta de mana pe canal); doar unde lipseste (alte imagini) se merge pe drumul clasic.

SEL_PAGE = 3
# k = cheia randului sub cursor; cat timp omul nu a apasat sus / jos (mut False) cursorul sta pe pista audio pornita
# i = ultima pozitie (pentru cheia care dispare); top = primul rand vazut in coloana; vis = randurile vazute (din skin)
_sel = {"k": None, "i": 0, "mut": False, "top": {"a": 0, "s": 0}, "vis": {"a": MAX_ROWS, "s": MAX_ROWS}}


def sel_reset():
	"""La aratare, la zap si la ascundere: cursorul revine pe pista audio pornita, listele sus."""
	_sel["k"] = None
	_sel["i"] = 0
	_sel["mut"] = False
	_sel["top"] = {"a": 0, "s": 0}


def sel_visible(col, n):
	"""Skinul spune cate randuri se vad in coloana `a` (sunet) sau `s` (subtitrari, cu „Fara subtitrari”)."""
	try:
		n = int(n)
		if col in ("a", "s") and 1 <= n <= ROW_LIMIT:
			_sel["vis"][col] = n
	except Exception:
		pass


def sub_key(e):
	"""Cheia unei subtitrari: primele 4 campuri ale tuplului (fel, PID, pagina, magazin), ca in same_sub."""
	try:
		return tuple([int(x) for x in e[:4]])
	except Exception:
		return None


def _sysinfo(name):
	try:
		from Components.SystemInfo import SystemInfo
		return bool(SystemInfo.get(name, False))
	except Exception:
		pass
	try:
		from Components.SystemInfo import BoxInfo
		return bool(BoxInfo.getItem(name, False))
	except Exception:
		return False


def _cfg_downmix(kind):
	"""config.av.downmix_ac3 / downmix_dts, sau None pe imaginile unde lipseste."""
	try:
		mod = sys.modules.get("Components.config")
		return getattr(mod.config.av, "downmix_" + kind, None)
	except Exception:
		return None


def sel_extras(r):
	"""Alegerile din dreapta, doar cele care se pot folosi aici: canalul audio (daca serviciul are piste si
	audioChannel), downmix AC3 / DTS (daca placa il stie), „Revino la alegerea automata” (doar cand canalul are o
	alegere facuta de mana, tinuta minte de HdsPisteLimbi). HbbTV e doar un rand de citit, nu intra in cursor."""
	def fn():
		out = []
		if r.track_list()[0] and piste_canal(r.service()) is not None:
			out.append("canal")
		if _sysinfo("CanDownmixAC3") and _cfg_downmix("ac3") is not None:
			out.append("ac3")
		if _sysinfo("CanDownmixDTS") and _cfg_downmix("dts") is not None:
			out.append("dts")
		if piste_memorat(r)["are"]:
			out.append("auto")
		return tuple(out)
	return r._memo("sel_extras", fn) or ()


def sel_items(r):
	"""Lista randurilor alegibile, in ordinea cursorului: ("a", i), ("s", None), ("s", cheie), ("x", nume)."""
	rows = r.track_list()[0]
	subs = r.sub_list()[0]
	items = [("a", k) for k in range(len(rows))]
	items.append(("s", None))
	for e in subs:
		k = sub_key(e)
		if k is not None:
			items.append(("s", k))
	for x in sel_extras(r):
		items.append(("x", x))
	return items


def _sel_home(r):
	"""Unde sta cursorul pana la prima apasare: pista audio pornita; fara piste, subtitrarea pornita sau „Fara subtitrari”."""
	rows, cur = r.track_list()
	if rows:
		return ("a", cur if cur >= 0 else 0)
	scur = r.sub_list()[1]
	return ("s", sub_key(scur) if scur is not None else None)


def sel_pos(r):
	"""(randurile alegibile, pozitia cursorului). Nu schimba nimic in afara de pozitia tinuta minte."""
	items = sel_items(r)
	if not items:
		return items, -1
	k = _sel["k"] if _sel["mut"] else _sel_home(r)
	try:
		i = items.index(k)
	except ValueError:
		i = max(0, min(_sel["i"], len(items) - 1))
	_sel["i"] = i
	if _sel["mut"]:
		_sel["k"] = items[i]
	return items, i


def sel_move(r, d):
	"""Sus (-1) / jos (+1); de la capat se trece la celalalt capat, ca in liste. True daca s-a mutat."""
	items, i = sel_pos(r)
	if i < 0 or len(items) < 2:
		return False
	i = (i + d) % len(items)
	_sel["i"] = i
	_sel["k"] = items[i]
	_sel["mut"] = True
	return True


def sel_column(r, col):
	"""(numarul de randuri al coloanei, pozitia cursorului in ea sau -1). `a` = piste audio; `s` = „Fara subtitrari”
	(randul 0) si subtitrarile; `x` = alegerile din dreapta."""
	items, i = sel_pos(r)
	k = items[i] if i >= 0 else None
	if col == "a":
		n = len(r.track_list()[0])
		return n, (k[1] if k is not None and k[0] == "a" else -1)
	if col == "s":
		keys = [None] + [sub_key(e) for e in r.sub_list()[0]]
		j = -1
		if k is not None and k[0] == "s":
			try:
				j = keys.index(k[1])
			except ValueError:
				j = -1
		return len(keys), j
	ex = sel_extras(r)
	j = -1
	if k is not None and k[0] == "x" and k[1] in ex:
		j = ex.index(k[1])
	return len(ex), j


def sel_top(r, col):
	"""Primul rand vazut in coloana `a` / `s`: lista se deruleaza cat sa se vada cursorul."""
	if col not in ("a", "s"):
		return 0
	n, j = sel_column(r, col)
	v = _sel["vis"][col]
	top = _sel["top"].get(col, 0)
	if j >= 0:
		if j < top:
			top = j
		elif j >= top + v:
			top = j - v + 1
	top = max(0, min(top, n - v)) if n > v else 0
	_sel["top"][col] = top
	return top


def sel_on_row(r, col, n):
	"""Adevarat cand cursorul e pe randul vazut n (1..) al coloanei."""
	cnt, j = sel_column(r, col)
	return j >= 0 and j == sel_top(r, col) + n - 1


def sel_more(r, col):
	"""„1-6 / 14” cand coloana are mai multe randuri decat se vad; altfel nimic."""
	n = sel_column(r, col)[0]
	v = _sel["vis"].get(col, MAX_ROWS)
	if n <= v:
		return u""
	top = sel_top(r, col)
	return u"%d-%d / %d" % (top + 1, min(n, top + v), n)


def extra_text(r, name):
	"""„Canal audio: Stereo”, „Downmix AC3: pornit”."""
	if name == "canal":
		c = piste_canal(r.service())
		val = {0: tr("sel_left"), 1: tr("sel_stereo"), 2: tr("sel_right")}.get(c, u"")
		return u"%s: %s" % (tr("sel_audio_channel"), val) if val else tr("sel_audio_channel")
	if name in ("ac3", "dts"):
		on = _downmix_acum(name, _cfg_downmix(name))
		return u"%s: %s" % (tr("sel_downmix_" + name), tr("on") if on else tr("off"))
	if name == "auto":
		return tr("sel_auto")
	return u""


def sel_ok(r, prop):
	"""OK pe pagina 3: alege randul de sub cursor. `prop` = proprietarul barei (InfoBar sau MoviePlayer), pentru
	subtitrari. OK pe subtitrarea deja pornita o opreste (ca in ecranul Audio). True daca s-a schimbat ceva."""
	items, i = sel_pos(r)
	if i < 0:
		return False
	kind, v = items[i]
	service = r.service()
	if kind == "a":
		return piste_alege_audio(service, v, getattr(prop, "session", None))
	if kind == "s":
		subs, scur = r.sub_list()
		if v is None:
			t = None
		else:
			t = None
			for e in subs:
				if sub_key(e) == v:
					t = e
					break
			if t is None:
				return False
			if same_sub(t, scur):
				t = None
		return piste_alege_subtitrare(prop, t)
	if kind == "x":
		return alege_extra(service, v)
	return False


def alege_extra(service, name):
	"""Canalul audio trece la urmatorul (stanga, stereo, dreapta); downmix-ul se comuta si se salveaza."""
	if name == "canal":
		c = piste_canal(service)
		if c is None:
			return False
		return piste_alege_canal(service, (c + 1) % 3)
	if name == "auto":
		return piste_uita()
	if name in ("ac3", "dts"):
		c = _cfg_downmix(name)
		if c is None:
			return False
		try:
			from Components.AVSwitch import setDownmix
		except ImportError:
			setDownmix = None
		try:
			if setDownmix is not None:
				# imaginea HDSatelit: pune valoarea, trece iesirea pe Manual daca era pe Automat, o singura scriere
				setDownmix(name, not _downmix_acum(name, c))
			else:
				c.value = not c.value
				c.save()
			return True
		except Exception as e:
			log_once("downmix", e)
	return False


def _downmix_acum(name, c):
	"""Downmix-ul AC3 / DTS pe care il face driverul acum (Components/AVSwitch.downmixAcum pe imaginea HDSatelit: pe
	„Automat” valoarea randului din setari nu e cea folosita); pe alte imagini valoarea din setari."""
	try:
		from Components.AVSwitch import downmixAcum
		v = downmixAcum(name)
	except Exception:
		v = None
	return bool(c is not None and c.value) if v is None else bool(v)


def sunet_stare(r):
	"""Ce se trimite pentru pista de sunet care merge si de ce (Components/HdsSunet.stare, numai pe imaginea HDSatelit):
	{"text", "motiv", "volum", ...}, sau None pe alte imagini si fara pista. O citire pe pas al barei (memo)."""
	def fn():
		try:
			from Components import HdsSunet
		except ImportError:
			return None
		s = HdsSunet.stare(service=r.service())
		return s if isinstance(s, dict) and s.get("text") else None
	return r._memo("sunet_stare", fn)


# ---------------------------------------------------------------- stratul subtire spre HdsPisteLimbi (un singur loc)
# Pe imaginea HDSatelit alegerea o face modulul Components/HdsPisteLimbi.py (acelasi drum ca pornirea automata dupa
# limba; tine minte alegerea de mana pe canal, definitiv). Numele sunt cele din API-ul lui:
# alegeAudioDeMana(session, index), alegeSubtitrareDeMana(session, tuplu, infobar=),
# stareCanal(session), uitaAlegeri(session), reaplicaAcum(session). Canalul audio (stanga / stereo / dreapta) nu e in
# modul: selectChannel direct. Unde modulul lipseste (alte imagini, sau o imagine HDSatelit mai veche), drumul clasic
# al imaginii: selectTrack al serviciului, iar la subtitrari metoda enableSubtitle a barei (pe alte imagini) sau,
# pe imaginea HDSatelit, AudioSelection.enableSubtitle (chemata, nu copiata). Toate intorc True / False si nu arunca.

_pl_mod = [False]


def _pl():
	"""Modulul Components.HdsPisteLimbi sau None; importul se incearca o singura data."""
	if _pl_mod[0] is False:
		try:
			from Components import HdsPisteLimbi as M
			_pl_mod[0] = M
		except Exception:
			_pl_mod[0] = None
	return _pl_mod[0]


def _pl_fn(name):
	M = _pl()
	fn = getattr(M, name, None) if M is not None else None
	return fn if callable(fn) else None


def _sesiune(session=None):
	if session is not None:
		return session
	p = _proprietar(None)
	return getattr(p, "session", None)


def piste_alege_audio(service, index, session=None):
	fn = _pl_fn("alegeAudioDeMana")
	session = _sesiune(session)
	if fn is not None and session is not None:
		try:
			return bool(fn(session, int(index)))
		except Exception as e:
			log_once("alegeAudioDeMana", e)
			return False
	try:
		a = service and service.audioTracks()
		if a and 0 <= int(index) < int(a.getNumberOfTracks() or 0):
			a.selectTrack(int(index))
			return True
	except Exception as e:
		log_once("selectTrack", e)
	return False


class _UmbraAudio(object):
	"""Ce foloseste AudioSelection.enableSubtitle din ecranul lui: doar bara (self.infobar)."""
	__slots__ = ("infobar",)

	def __init__(self, infobar):
		self.infobar = infobar


def _proprietar(prop):
	if prop is not None:
		return prop
	try:
		from Screens.InfoBar import InfoBar
		return InfoBar.instance
	except Exception:
		return None


def piste_alege_subtitrare(prop, t):
	"""t = tuplul din getSubtitleList sau None (oprite)."""
	prop = _proprietar(prop)
	if prop is None:
		return False
	fn = _pl_fn("alegeSubtitrareDeMana")
	session = getattr(prop, "session", None)
	if fn is not None and session is not None:
		try:
			return bool(fn(session, t, infobar=prop))
		except Exception as e:
			log_once("alegeSubtitrareDeMana", e)
			return False
	try:
		m = getattr(prop, "enableSubtitle", None)
		if callable(m):
			m(t)
			return True
		from Screens.AudioSelection import AudioSelection
		m = AudioSelection.enableSubtitle
		m = getattr(m, "__func__", m)
		m(_UmbraAudio(prop), t)
		return True
	except Exception as e:
		log_once("enableSubtitle", e)
	return False


def piste_subtitrare_pornita(prop):
	"""Tuplul subtitrarii care se vede, sau None."""
	prop = _proprietar(prop)
	try:
		if prop is not None and prop.subtitles_enabled:
			return prop.selected_subtitle or None
	except Exception:
		pass
	return None


def piste_canal(service):
	"""0 stanga, 1 stereo, 2 dreapta, sau None cand serviciul nu are canal audio."""
	try:
		ch = service and service.audioChannel()
		if ch:
			v = int(ch.getCurrentChannel())
			return v if v in (0, 1, 2) else None
	except Exception:
		pass
	return None


def piste_alege_canal(service, n):
	try:
		ch = service and service.audioChannel()
		if ch and n in (0, 1, 2):
			ch.selectChannel(n)
			return True
	except Exception as e:
		log_once("selectChannel", e)
	return False


_MEMO_GOL = {"are": False, "a": None, "s": False, "s_t": None}


def piste_memorat(r):
	"""Ce tine minte HdsPisteLimbi pe canalul care merge (alegerea facuta de mana, definitiva):
	are = exista o alegere; a = indicele pistei audio alese de mana (sau None); s = subtitrarea aleasa de mana
	(True) sau nu; s_t = tuplul ei (None = „Fara subtitrari” tinut minte). O data pe citire (Reader)."""
	def fn():
		f = _pl_fn("stareCanal")
		session = _sesiune(None)
		if f is None or session is None:
			return _MEMO_GOL
		st = f(session) or {}
		mem = st.get("memorat") or {}
		ult = st.get("ultima") or {}
		rez = {"are": bool(mem.get("a") or mem.get("s")), "a": None, "s": False, "s_t": None}
		ua = ult.get("audio") or {}
		if mem.get("a") and ua.get("motiv") == "memorat" and ua.get("cheie") == st.get("cheie"):
			rez["a"] = ua.get("index")
		us = ult.get("subtitrare") or {}
		if mem.get("s") and us.get("motiv") in ("memorat", "memorat-oprit") and us.get("cheie") == st.get("cheie"):
			rez["s"] = True
			rez["s_t"] = us.get("tuplu")
		return rez
	return r._memo("piste_memorat", fn) or _MEMO_GOL


def piste_uita():
	"""„Revino la alegerea automata”: HdsPisteLimbi uita alegerea de mana a canalului si aplica pe loc preferintele."""
	f = _pl_fn("uitaAlegeri")
	g = _pl_fn("reaplicaAcum")
	session = _sesiune(None)
	if f is None or session is None:
		return False
	try:
		f(session)
		if g is not None:
			g(session)
		return True
	except Exception as e:
		log_once("uitaAlegeri", e)
	return False


# ---------------------------------------------------------------- EPG

GENRE_KEYS = dict((n, "genre_%d" % n) for n in range(1, 12))
_EV_FIELDS = ("name", "short", "ext", "begin", "dur", "genre", "rating")
_epg = {"gen": 0, "ref": None, "t": -1000.0, "g": -1, "val": (), "what": None}


def epg_changed(what=None):
	"""Chemat la evUpdatedEventInfo: lista emisiunilor urmatoare se reciteste (o data pe eveniment, oricati convertori)."""
	if what is not None and _epg["what"] is what:
		return
	_epg["what"] = what
	_epg["gen"] += 1


def _call(obj, name, *args):
	fn = getattr(obj, name, None)
	if fn is None:
		return None
	try:
		return fn(*args)
	except Exception:
		return None


def _genre_level1(ev):
	lst = _call(ev, "getGenreDataList")
	if isinstance(lst, (list, tuple)):
		for g in lst:
			try:
				return int(g[0])
			except Exception:
				continue
	g = _call(ev, "getGenreData")
	if g is None:
		return -1
	if isinstance(g, (list, tuple)):
		for x in g:
			v = _call(x, "getLevel1")
			if v is not None:
				return ival({"v": v}, "v")
		return -1
	return ival({"v": _call(g, "getLevel1")}, "v")


def _rating_age(ev):
	p = _call(ev, "getParentalData")
	if p is None:
		return -1
	if isinstance(p, (list, tuple)):
		p = p[0] if p else None
		if isinstance(p, (list, tuple)):
			return ival({"v": p[1] if len(p) > 1 else -1}, "v")
	return ival({"v": _call(p, "getRating")}, "v")


def ev_dict(ev):
	"""O emisiune (eServiceEvent) ca dictionar de valori Python, sau None cand nu are nume. Nu arunca."""
	if not ev:
		return None
	name = u(_call(ev, "getEventName")).strip()
	if not name:
		return None
	return {
		"id": ival({"v": _call(ev, "getEventId")}, "v", -1),
		"name": name[:200],
		"short": u(_call(ev, "getShortDescription")).strip()[:600],
		"ext": u(_call(ev, "getExtendedDescription")).strip()[:2400],
		"begin": ival({"v": _call(ev, "getBeginTime")}, "v", 0),
		"dur": ival({"v": _call(ev, "getDuration")}, "v", 0),
		"genre": _genre_level1(ev),
		"rating": _rating_age(ev),
	}


def event_data(r, n):
	"""Emisiunea n (0 acum, 1 urmatoarea) a serviciului redat, ca dictionar de valori Python, sau None."""
	def fn():
		i = r.info()
		if i is None:
			return None
		return ev_dict(_call(i, "getEvent", n))
	return r._memo("event%d" % n, fn)


def hhmm(t):
	try:
		import time
		return u(time.strftime("%H:%M", time.localtime(int(t))))
	except Exception:
		return u""


def event_times_text(ev):
	"""20:15-21:45 · 90 min."""
	if not ev or ev["begin"] <= 0:
		return u""
	parts = [hhmm(ev["begin"])]
	if ev["dur"] > 0:
		parts[0] += u"-" + hhmm(ev["begin"] + ev["dur"])
		parts.append(u"%d %s" % (ev["dur"] // 60, tr("unit_min")))
	return join(parts)


def genre_text(level1):
	key = GENRE_KEYS.get(level1)
	return tr(key) if key else u""


def rating_text(rating):
	"""Varsta din descriptorul DVB: 1..15 inseamna rating + 3 ani (EN 300 468); restul nu se arata."""
	if 1 <= rating <= 15:
		return u"%d+" % (rating + 3)
	return u""


def next_events(r):
	"""[(inceput, titlu), ...] emisiunile de dupa cea curenta, din cache-ul EPG al imaginii; memo 60 s pe serviciu."""
	sref = r.sref()
	if not sref:
		return ()
	now = _now()
	if _epg["ref"] == sref and _epg["g"] == _epg["gen"] and 0.0 <= now - _epg["t"] < 60.0:
		return _epg["val"]
	val = ()
	try:
		mod = sys.modules.get("enigma")
		epgc = getattr(mod, "eEPGCache", None)
		if epgc is None:
			return ()
		cache = epgc.getInstance()
		ref = str(sref) if not PY2 else u(sref).encode("utf-8")
		lst = cache.lookupEvent(["BT", (ref, 0, -1, 1440)])
		rows = []
		if isinstance(lst, (list, tuple)):
			for e in lst[:12]:
				try:
					begin = int(e[0])
					title = u(e[1]).strip()
				except Exception:
					continue
				if begin > 0 and title:
					rows.append((begin, title[:120]))
		rows.sort()
		cutoff = now
		cur = event_data(r, 0)
		if cur and cur["begin"] > 0:
			cutoff = cur["begin"] + max(cur["dur"], 1) - 1
		val = tuple([x for x in rows if x[0] > cutoff][:6])
	except Exception as e:
		log_once("lookupEvent", e)
		val = ()
	_epg["ref"] = sref
	_epg["g"] = _epg["gen"]
	_epg["t"] = now
	_epg["val"] = val
	return val


def event_line(ev):
	"""Randul orelor unei emisiuni: „10:02-10:15 · 13 min · Știri · 12+”; genul si varsta doar cand exista."""
	if not ev:
		return u""
	return join([event_times_text(ev), genre_text(ev.get("genre", -1)), rating_text(ev.get("rating", -1))])


# ---------------------------------------------------------------- pagina 5: ghidul canalului, navigabil
# Lista din dreapta: emisiunile serviciului redat de acum inainte (prima e cea de acum), din cache-ul EPG al imaginii,
# cerute o singura data (lookupEvent „IBDT” pe 24 de ore) si recitite la EPG nou sau dupa 60 s; cand cursorul ajunge
# la capat se cere bucata urmatoare, pana la EPG_DAYS zile si EPG_ROWS randuri. Descrierile se cer numai pentru
# emisiunea aleasa (lookupEventId). Cursorul se tine dupa id-ul emisiunii, ca la pagina 3 dupa cheie.
# Tastele (sus / jos, OK, INFO, culorile, REC, EPG) le leaga Screens/SecondInfoBar.py pe imaginea HDSatelit si
# HdsSkinSetari/taste_afisaj.py (doar sus / jos) pe celelalte imagini; functiile de aici nu tin de nicio imagine.

EPG_ROWS = 100
EPG_DAYS = 7
EPG_CHUNK = 1440
EPG_TTL = 60.0
EPG_VIS = 8
# rows = (id, inceput, durata, titlu); span = minutele cerute pana acum de la t (bucatile urmatoare adauga la el)
_epg_list = {"ref": None, "g": -1, "t": -1000.0, "rows": (), "span": EPG_CHUNK, "done": False}
# id = emisiunea sub cursor; i = ultima pozitie (pentru id-ul care dispare); mut = omul a apasat sus / jos (abia atunci
# se deseneaza cursorul); top = primul rand vazut; vis = randurile vazute (le spune skinul, EpgRow,<n>,<vazute>);
# drawn = skinul activ deseneaza lista (un convertor EpgRow s-a creat): numai atunci tastele ghidului lucreaza
_epg_sel = {"id": None, "i": 0, "mut": False, "top": 0, "vis": EPG_VIS, "drawn": False}
# tastele ghidului legate de ecranul imaginii (SecondInfoBar): numai atunci se scriu textele tastelor colorate
# on = tastele ghidului legate de ecranul imaginii; desc = descrierea intreaga a emisiunii alese e pe ecran
_epg_keys = {"on": False, "desc": False}
# randul scurt din banda dupa o inregistrare pusa din bara
_epg_note = {"text": u"", "until": 0.0}
# ultima emisiune ceruta cu lookupEventId (un singur loc: descrierea se cere doar pentru randul ales)
_epg_ev = {"key": None, "val": None}
EPG_NOTE_S = 4.0


def _epg_query_ref(sref):
	"""Referinta pentru cache-ul EPG: nucleul primeste numai referinte DVB (tip 1); un flux cu SID (tip 4097, 5001...)
	se cauta cu partea DVB a referintei, cum o pun importurile de EPG. None cand nu se poate cere nimic."""
	f = u(sref).split(u":")
	if len(f) < 10:
		return None
	if f[0] == u"1":
		ref = u":".join(f[:11]) if len(f) > 10 else u":".join(f[:10]) + u":"
	else:
		try:
			if int(f[3], 16) <= 0:
				return None
		except Exception:
			return None
		ref = u"1:" + u":".join(f[1:10]) + u":"
	return ref if not PY2 else ref.encode("utf-8")


def _epg_cache():
	try:
		mod = sys.modules.get("enigma")
		epgc = getattr(mod, "eEPGCache", None)
		return epgc.getInstance() if epgc is not None else None
	except Exception:
		return None


def _epg_read(sref, start, minutes):
	"""[(id, inceput, durata, titlu)] din cache pentru `minutes` minute de la `start` (-1 = acum), in ordinea timpului."""
	ref = _epg_query_ref(sref)
	cache = _epg_cache()
	if ref is None or cache is None:
		return []
	try:
		lst = cache.lookupEvent(["IBDT", (ref, 0, int(start), int(minutes))])
	except Exception as e:
		log_once("lookupEvent IBDT", e)
		return []
	rows = []
	seen = set()
	if isinstance(lst, (list, tuple)):
		for e in lst[:EPG_ROWS + 20]:
			try:
				eid = int(e[0])
				begin = int(e[1])
				dur = int(e[2])
				title = u(e[3]).strip()
			except Exception:
				continue
			if begin <= 0 or not title or eid in seen:
				continue
			seen.add(eid)
			rows.append((eid, begin, max(dur, 0), title[:120]))
	rows.sort(key=lambda x: x[1])
	return rows


def _eit_rows(r):
	"""Acum si urmeaza din serviciu (EIT), cand cache-ul EPG nu are nimic (canale fara program pe zile)."""
	rows = []
	for n in (0, 1):
		ev = event_data(r, n)
		if ev and ev["begin"] > 0:
			rows.append((ev["id"], ev["begin"], ev["dur"], ev["name"][:120]))
	return rows


def epg_list(r):
	"""Emisiunile serviciului redat pentru ghid, de acum inainte: ((id, inceput, durata, titlu), ...). Inregistrarile
	si fisierele nu au lista (cache-ul nu are program pentru ele). Memo pe serviciu; nu arunca."""
	try:
		if r.info() is None or r.kind() in ("record", "file", ""):
			return ()
		sref = r.sref()
		if not sref:
			return ()
		now = _now()
		m = _epg_list
		if not (m["ref"] == sref and m["g"] == _epg["gen"] and 0.0 <= now - m["t"] < EPG_TTL):
			span = m["span"] if m["ref"] == sref else EPG_CHUNK
			m["rows"] = tuple(_epg_read(sref, -1, span)[:EPG_ROWS])
			m["ref"] = sref
			m["g"] = _epg["gen"]
			m["t"] = now
			m["span"] = span
			m["done"] = False
		rows = tuple([x for x in m["rows"] if x[1] + max(x[2], 1) > now])
		if not rows:
			return tuple(_eit_rows(r))
		cur = event_data(r, 0)
		if cur and cur["begin"] > 0 and cur["begin"] < rows[0][1] and cur["begin"] + cur["dur"] > now:
			rows = ((cur["id"], cur["begin"], cur["dur"], cur["name"][:120]),) + rows
		return rows
	except Exception as e:
		log_once("epg_list", e)
		return ()


def epg_more(r):
	"""Cursorul a ajuns la capatul listei: se cere bucata urmatoare (inca EPG_CHUNK minute), pana la EPG_DAYS zile si
	EPG_ROWS randuri. True daca lista a crescut."""
	m = _epg_list
	try:
		sref = r.sref()
		if m["done"] or m["ref"] != sref or not m["rows"] or len(m["rows"]) >= EPG_ROWS:
			return False
		if m["span"] + EPG_CHUNK > EPG_DAYS * 1440:
			m["done"] = True
			return False
		last = m["rows"][-1]
		start = last[1] + max(last[2], 60)
		have = set([x[0] for x in m["rows"]])
		new = [x for x in _epg_read(sref, start, EPG_CHUNK) if x[0] not in have and x[1] >= last[1]]
		m["span"] += EPG_CHUNK
		if not new:
			m["done"] = True
			return False
		m["rows"] = (m["rows"] + tuple(new))[:EPG_ROWS]
		return True
	except Exception as e:
		log_once("epg_more", e)
		return False


def epg_reset():
	"""La aratare, la zap si la ascundere: cursorul pe emisiunea de acum, nedesenat, lista sus."""
	_epg_sel["id"] = None
	_epg_sel["i"] = 0
	_epg_sel["mut"] = False
	_epg_sel["top"] = 0


def epg_visible(n):
	"""Skinul spune cate randuri se vad in lista (EpgRow,<n>,<vazute>); de aici se stie si ca lista e desenata."""
	try:
		n = int(n)
		if 1 <= n <= ROW_LIMIT:
			_epg_sel["vis"] = n
			_epg_sel["drawn"] = True
	except Exception:
		pass


def epg_keys_on(on=True):
	"""Ecranul imaginii (SecondInfoBar) leaga tastele ghidului: textele tastelor colorate se pot arata."""
	_epg_keys["on"] = bool(on)


def epg_select_id(eid):
	"""Cursorul pe emisiunea cu id-ul dat (dupa un ecran deschis din bara), desenat."""
	_epg_sel["id"] = eid
	_epg_sel["mut"] = True


def epg_pos(r):
	"""(randurile, pozitia cursorului). Nemutat: emisiunea de acum (randul 0). Id disparut: aceeasi pozitie."""
	rows = epg_list(r)
	if not rows:
		return rows, -1
	i = 0
	if _epg_sel["mut"]:
		i = -1
		for k, x in enumerate(rows):
			if x[0] == _epg_sel["id"]:
				i = k
				break
		if i < 0:
			i = max(0, min(_epg_sel["i"], len(rows) - 1))
		_epg_sel["id"] = rows[i][0]
	_epg_sel["i"] = i
	return rows, i


def epg_move(r, d):
	"""Sus (-1) / jos (+1). Prima apasare: jos trece pe emisiunea urmatoare, sus arata cursorul pe cea de acum. Sus pe
	primul rand ramane acolo (lista e in timp, nu cerc); jos pe ultimul cere bucata urmatoare. True daca s-a schimbat."""
	rows, i = epg_pos(r)
	if i < 0:
		return False
	mut = _epg_sel["mut"]
	j = i + d if (mut or d > 0) else i
	if j >= len(rows) and epg_more(r):
		rows = epg_list(r)
	j = max(0, min(j, len(rows) - 1))
	changed = (not mut) or j != i
	_epg_sel["mut"] = True
	_epg_sel["i"] = j
	_epg_sel["id"] = rows[j][0]
	page_touch()
	return changed


def epg_moved():
	"""Omul a mutat cursorul (se deseneaza fundalul randului ales)."""
	return bool(_epg_sel["mut"])


def epg_desc_set(on):
	"""Ecranul imaginii a deschis (sau a inchis) descrierea intreaga a emisiunii alese peste ghid."""
	_epg_keys["desc"] = bool(on)


def epg_help_text(r):
	"""Randul de ajutor al ghidului, dupa ce fac acum sagetile si OK: in descriere (sus / jos deruleaza, OK = meniul
	emisiunii), cu cursorul mutat (OK = descrierea) sau nemutat (OK inchide bara). Gol unde tastele nu lucreaza."""
	if not epg_keys_work(r):
		return u""
	if _epg_keys.get("desc"):
		return tr("epg_help_desc")
	return tr("epg_help_moved") if epg_moved() else tr("epg_help")


def ca_help_text(r):
	"""Pe pagina accesului, numai cand lista CAID-urilor se deruleaza cu sus / jos (tastele imaginii legate)."""
	if not _epg_keys["on"] or len(ca_entries(r)) <= _ca_view["vis"]:
		return u""
	return tr("ca_help")


def epg_top(r):
	"""Primul rand vazut: lista se deruleaza cat sa se vada cursorul."""
	rows, i = epg_pos(r)
	v = _epg_sel["vis"]
	top = _epg_sel["top"]
	if i >= 0:
		if i < top:
			top = i
		elif i >= top + v:
			top = i - v + 1
	n = len(rows)
	top = max(0, min(top, n - v)) if n > v else 0
	_epg_sel["top"] = top
	return top


def epg_row(r, n):
	"""Randul vazut n (1..) al listei, sau None."""
	rows = epg_list(r)
	k = epg_top(r) + n - 1
	return rows[k] if 0 <= k < len(rows) else None


def epg_on_row(r, n):
	"""Cursorul desenat e pe randul vazut n."""
	if not _epg_sel["mut"]:
		return False
	rows, i = epg_pos(r)
	return i >= 0 and i == epg_top(r) + n - 1


def epg_more_text(r):
	"""„1-8 / 42” cand lista are mai multe randuri decat se vad; altfel nimic."""
	rows = epg_list(r)
	v = _epg_sel["vis"]
	if len(rows) <= v:
		return u""
	top = epg_top(r)
	return u"%d-%d / %d" % (top + 1, min(len(rows), top + v), len(rows))


def epg_chosen(r):
	"""Randul ales: cel de sub cursor, sau emisiunea de acum cat cursorul nu s-a mutat; None fara lista."""
	rows, i = epg_pos(r)
	return rows[i] if i >= 0 else None


def epg_lookup_id(sref, eid):
	"""Emisiunea `eid` din cache-ul EPG, ca dictionar (ev_dict), sau None. Un singur loc tinut minte."""
	key = (norm_ref(sref), eid)
	if _epg_ev["key"] == key:
		return _epg_ev["val"]
	val = None
	try:
		ref = _epg_query_ref(sref)
		cache = _epg_cache()
		mod = sys.modules.get("enigma")
		esr = getattr(mod, "eServiceReference", None)
		if ref is not None and cache is not None and esr is not None and eid is not None and int(eid) >= 0:
			val = ev_dict(cache.lookupEventId(esr(ref), int(eid)))
	except Exception as e:
		log_once("lookupEventId", e)
		val = None
	_epg_ev["key"] = key
	_epg_ev["val"] = val
	return val


def epg_event(r):
	"""Emisiunea aleasa, cu descrieri: dictionarul lui ev_dict. La inregistrari, emisiunea inregistrarii."""
	def fn():
		row = epg_chosen(r)
		now = event_data(r, 0)
		if row is None:
			return now
		if now and (row[0] == now["id"] or row[1] == now["begin"]):
			return now
		nxt = event_data(r, 1)
		if nxt and (row[0] == nxt["id"] or row[1] == nxt["begin"]):
			return nxt
		ev = epg_lookup_id(r.sref(), row[0])
		if ev:
			return ev
		return {"id": row[0], "name": row[3], "short": u"", "ext": u"", "begin": row[1], "dur": row[2],
			"genre": -1, "rating": -1}
	return r._memo("epg_event", fn)


def epg_short_line(ev):
	"""Textul scurt al emisiunii pe un singur rand: randurile din EIT fara cel care repeta titlul (sau inceputul lui),
	unite cu „ · ”; gol cand nu ramane nimic in afara titlului."""
	if not ev:
		return u""
	name = u" ".join(u(ev.get("name")).split())
	parts = []
	for line in u(ev.get("short")).replace(u"\r", u"\n").split(u"\n"):
		line = u" ".join(line.split())
		if name and line.startswith(name):
			line = line[len(name):].lstrip(u" -:,.\u00b7\u2013")
		if line and line not in parts:
			parts.append(line)
	return SEP.join(parts)


def _local(t):
	try:
		import time
		return time.localtime(int(t))
	except Exception:
		return None


def epg_day_offset(t):
	"""Zile de azi pana la ziua lui t (0 azi, 1 maine...), dupa ceasul receptorului."""
	a = _local(_now())
	b = _local(t)
	if a is None or b is None:
		return 0
	try:
		import datetime
		return (datetime.date(b.tm_year, b.tm_mon, b.tm_mday) - datetime.date(a.tm_year, a.tm_mon, a.tm_mday)).days
	except Exception:
		return 0


def epg_when_text(r):
	"""Eticheta emisiunii alese: „Acum”, „Urmează”, „Azi 21:45”, „Mâine 06:30”, „Luni 06:30”; „Înregistrare” la
	inregistrari."""
	if r.kind() in ("record", "file"):
		return tr("epg_recording") if event_data(r, 0) else u""
	ev = epg_event(r)
	if not ev or ev["begin"] <= 0:
		return tr("now") if ev else u""
	now = _now()
	if ev["begin"] <= now < ev["begin"] + max(ev["dur"], 1):
		return tr("now")
	rows = epg_list(r)
	future = [x for x in rows if x[1] > now]
	if future and (future[0][0] == ev["id"] or future[0][1] == ev["begin"]):
		return tr("next")
	d = epg_day_offset(ev["begin"])
	if d == 0:
		day = tr("epg_today")
	elif d == 1:
		day = tr("epg_tomorrow")
	else:
		lt = _local(ev["begin"])
		day = tr("day_long_%d" % lt.tm_wday) if lt is not None else u""
	return join([day, hhmm(ev["begin"])], u" ")


def epg_row_text(r, n):
	"""„10:15  Shift”; pe alta zi decat azi cu ziua in fata: „Lu 06:30  Știrile dimineții”."""
	row = epg_row(r, n)
	if row is None:
		return u""
	eid, begin, dur, title = row
	t = hhmm(begin)
	if epg_day_offset(begin) != 0:
		lt = _local(begin)
		if lt is not None:
			t = u"%s %s" % (tr("day_short_%d" % lt.tm_wday), t)
	return u"%s  %s" % (t, epg_tr("titlu", title))


# ---------------------------------------------------------------- traducerea automata a ghidului
# Pe imaginea HDSatelit, cu „Tradu EPG” pornita, titlurile si descrierile din ghid trec prin
# Components/HdsTraducereEpg.py: traducerea din memorie sau originalul pe loc; cand vine traducerea, pagina ghidului se
# reciteste (page_refresh). Pe celelalte imagini modulul lipseste si textul ramane neschimbat.

class _AscultaGhidul(object):
	def hdsTraducereEpg(self):
		try:
			page_refresh(EPG_PAGE)
		except Exception as e:
			log_once("epg traducere", e)


_epg_tr = {"incarcat": False, "mod": None, "cine": _AscultaGhidul()}


def epg_tr(fel, text):
	"""Textul unei emisiuni (fel: titlu, scurta, lunga) tradus de traducerea automata a ghidului, sau neschimbat."""
	if not text:
		return text
	if not _epg_tr["incarcat"]:
		_epg_tr["incarcat"] = True
		try:
			from Components import HdsTraducereEpg
			_epg_tr["mod"] = HdsTraducereEpg
		except Exception:
			_epg_tr["mod"] = None
	m = _epg_tr["mod"]
	if m is None:
		return text
	try:
		# a doua bara ascunsa (paginile ei se calculeaza si atunci) nu cere traduceri noi: la aratare paginile se
		# recitesc (page_set) si atunci cer ce lipseste
		return m.text(fel, text, _epg_tr["cine"], False, bool(_pages.get("shown")))
	except Exception as e:
		log_once("epg_tr", e)
		return text


def epg_row_now(r, n):
	"""Randul vazut n e emisiunea de acum."""
	row = epg_row(r, n)
	if row is None:
		return False
	now = _now()
	return row[1] <= now < row[1] + max(row[2], 1)


def _timer_list():
	try:
		mod = sys.modules.get("NavigationInstance")
		inst = getattr(mod, "instance", None) if mod is not None else None
		rt = getattr(inst, "RecordTimer", None)
		lst = getattr(rt, "timer_list", None)
		return list(lst) if lst else []
	except Exception:
		return []


def timer_ref(t):
	"""Referinta unui temporizator, ca text normalizat."""
	try:
		sr = getattr(t, "service_ref", None)
		ref = getattr(sr, "ref", sr)
		fn = getattr(ref, "toString", None)
		return norm_ref(fn() if fn is not None else ref)
	except Exception:
		return u""


# un temporizator de comutare nu are durata: e al emisiunii care incepe la cel mult atatea secunde de el
TIMER_ZAP_S = 900


def epg_timer_for(sref, eid, begin, dur, timers=None):
	"""Temporizatorul pus pe emisiune, sau None: acelasi serviciu si acelasi id; fara id, o inregistrare al carei
	interval acopera mijlocul emisiunii sau o comutare care porneste aproape de inceputul ei (TIMER_ZAP_S).
	`timers` = lista deja citita (o data pe desen)."""
	me = norm_ref(sref)
	if not me:
		return None
	mid = int(begin) + max(int(dur), 0) // 2
	for t in (timers if timers is not None else _timer_list()):
		try:
			if timer_ref(t) != me:
				continue
			if getattr(t, "repeated", 0):
				continue
			teit = getattr(t, "eit", None)
			if teit is not None and eid is not None and int(eid) >= 0:
				# amandoua au id: numai acelasi id e al emisiunii (orele ar prinde si vecinii scurti)
				if int(teit) == int(eid):
					return t
				continue
			if getattr(t, "justplay", False):
				if abs(int(t.begin) - int(begin)) <= TIMER_ZAP_S:
					return t
			elif int(t.begin) <= mid <= int(t.end):
				return t
		except Exception:
			continue
	return None


def epg_row_timer(r, n):
	"""„inregistrare”, „comutare” (doar comutare) sau "" pentru randul vazut n. Lista temporizatoarelor se citeste
	o data pe desen (memo pe eveniment)."""
	row = epg_row(r, n)
	if row is None:
		return u""
	timers = r._memo("epg_timers", _timer_list) or []
	if not timers:
		return u""
	t = epg_timer_for(r.sref(), row[0], row[1], row[2], timers)
	if t is None:
		return u""
	return u"comutare" if getattr(t, "justplay", False) else u"inregistrare"


def epg_live(r):
	"""Serviciu viu cu program (nu inregistrare, nu fisier): temporizatorul si inregistrarea au sens."""
	return r.info() is not None and r.kind() not in ("record", "file", "") and bool(epg_list(r))


def epg_keys_work(r):
	"""Tastele ghidului lucreaza: legate de ecranul imaginii, lista desenata de skin, pagina ghidului pe ecran."""
	return _epg_keys["on"] and _epg_sel["drawn"] and _pages["active"] == EPG_PAGE and _pages["shown"]


def epg_key_text(r, color):
	"""Textul tastei colorate pe ghid, numai unde tasta chiar lucreaza si cat nu se vede randul scurt din banda."""
	if not epg_keys_work(r) or epg_note() or not epg_live(r):
		return u""
	if color in ("red", "green"):
		# pe o emisiune cu temporizator si rosul si verdele il scot (cu intrebare), deci amandoua scriu „Anulează”
		ev = epg_event(r)
		if ev and epg_timer_for(r.sref(), ev["id"], ev["begin"], ev["dur"]) is not None:
			return tr("epg_key_untimer")
		return tr("epg_key_rec") if color == "red" else tr("epg_key_timer")
	if color == "yellow":
		return tr("epg_key_guide")
	if color == "blue":
		return tr("epg_key_all")
	return u""


def epg_note_set(text, secs=EPG_NOTE_S):
	"""Randul scurt din banda („Înregistrare pusă: ...”), cateva secunde."""
	_epg_note["text"] = u(text)[:120]
	_epg_note["until"] = _now() + float(secs)


def epg_note():
	"""Randul scurt din banda, cat e valabil; altfel nimic."""
	if _epg_note["text"] and _now() < _epg_note["until"]:
		return _epg_note["text"]
	_epg_note["text"] = u""
	return u""


# ---------------------------------------------------------------- tunerul si setarile antenei (doar citite)

def cvalue(obj, *names):
	"""Valoarea unei setari config (obj.a.b.value) sau None, fara exceptie."""
	try:
		for n in names:
			if isinstance(n, int) or (isinstance(n, str) and n.isdigit()):
				obj = obj[int(n)]
			else:
				obj = getattr(obj, n)
		return obj.value
	except Exception:
		return None


def csub(obj, *names):
	"""Obiectul config de la capatul drumului, sau None."""
	try:
		for n in names:
			if isinstance(n, int):
				obj = obj[n]
			else:
				obj = getattr(obj, n)
		return obj
	except Exception:
		return None


def nim_config(n, kind="s"):
	"""config.Nims[n] pe tipul de receptie: unele imagini au subsectiuni (dvbs, dvbc, dvbt), altele sunt plate."""
	try:
		mod = sys.modules.get("Components.config")
		nim = mod.config.Nims[int(n)]
	except Exception:
		return None
	sub = {"s": "dvbs", "c": "dvbc", "t": "dvbt"}.get(kind)
	if sub:
		try:
			x = getattr(nim, sub)
			if x is not None:
				return x
		except Exception:
			pass
	return nim


def nim_slot(n):
	try:
		mod = sys.modules.get("Components.NimManager")
		nm = getattr(mod, "nimmanager", None)
		return nm.nim_slots[int(n)]
	except Exception:
		return None


def fe_number(r):
	"""Numarul tunerului care reda (0 = A), sau -1. Fara citire din placa (frontendNumber nu face ioctl). La un serviciu
	redat dintr-un flux: tunerul care tine purtatorul, din receptie.json, sau -1 (enigma2 ar da 0, adica „A”)."""
	def fn():
		if ref_din_flux(r.sref()):
			n = ival(rj_dict(r.rj() or {}, "purtator"), "tuner")
			return n if 0 <= n <= 25 else -1
		s = r.service()
		fe = s and s.frontendInfo()
		if not fe:
			return -1
		c = _fe_const("frontendNumber")
		if c is not None:
			try:
				v = int(fe.getFrontendInfo(c))
				if 0 <= v <= 25:
					return v
			except Exception:
				pass
		return -1
	v = r._memo("fenum", fn)
	return -1 if v is None else v


def tuner_full(n, kind):
	"""A · DVB-S2 NIM · DVB-S2X."""
	if n < 0:
		return u""
	slot = nim_slot(n)
	desc = u(getattr(slot, "description", u"")) if slot is not None else u""
	typ = u""
	if slot is not None:
		for attr in ("getType", "getFriendlyType"):
			fn = getattr(slot, attr, None)
			if fn is not None:
				try:
					typ = u(fn())
				except Exception:
					typ = u""
				if typ:
					break
	# „DVB-S2 NIM · DVB-S2”: tipul care se citeste deja in descriere nu se mai scrie o data
	if typ == desc or (typ and typ.upper() in desc.upper()):
		typ = u""
	# tipul ales pe un tuner combinat poate fi altul decat receptia de acum (DVB-C pe un tuner care reda DVB-T2): atunci nu se scrie
	prefix = {"s": u"DVB-S", "c": u"DVB-C", "t": u"DVB-T", "a": u"ATSC"}.get(kind)
	if typ and prefix and not typ.upper().startswith(prefix):
		typ = u""
	return join([u"%c" % (65 + n), desc[:24], typ[:12]])


def config_mode_text(n, kind):
	nim = nim_config(n, kind)
	mode = u(cvalue(nim, "configMode"))
	if mode == u"simple":
		return tr("nim_simple")
	if mode == u"advanced":
		return tr("nim_advanced")
	if mode in (u"equal", u"loopthrough", u"satposdepends"):
		other = u(cvalue(nim, "connectedTo"))
		letter = (u"%c" % (65 + int(other))) if other.isdigit() and int(other) < 26 else u"?"
		return tr("nim_equal" if mode == u"equal" else "nim_linked").replace(u"{0}", letter)
	if mode == u"enabled":
		return tr("on")
	return u""


def _port_letter(nim, orbpos):
	for letter in ("A", "B", "C", "D"):
		sat = csub(nim, "diseqc" + letter)
		try:
			if sat is not None and int(getattr(sat, "orbital_position")) == int(orbpos):
				return letter
		except Exception:
			continue
	return u""


def _adv_sat_lnb(nim, orbpos):
	"""(numarul LNB, sectiunea LNB) in modul avansat, sau (0, None).
	HDSatelit: aceeasi regula ca SecConfigure.updateAdvanced (NimManager.py:267-283):
	un satelit din lista ia LNB-ul lui anume sau, cand nu are (lnb 0), LNB-ul „toti satelitii” (sat[3601..3604] ->
	LNB 33..36, motorul). Fara asta, dupa trecerea tunerului cu motor din modul simplu in cel avansat (Configurare LNB
	sau Setari tuner) bara nu mai vedea motorul, LNB-ul si DiSEqC-ul. Alocarea anume are intaietate, ca in
	Components/HdsLnb.lnbPentruSatelit; regula e scrisa aici, fara import de acolo, fiindca bara o citeste des."""
	try:
		sats = nim.advanced.sat
		num = int(sats[int(orbpos)].lnb.value)
	except Exception:
		# satelitul nu e in lista tunerului: nici „toti satelitii” nu il iau (updateAdvanced 272-276)
		return 0, None
	if num <= 0:
		for x in (3601, 3602, 3603, 3604):
			try:
				num = int(sats[x].lnb.value)
			except Exception:
				num = 0
			if num > 0:
				break
	if num <= 0:
		return 0, None
	try:
		return num, nim.advanced.lnb[num]
	except Exception:
		return num, None


def _adv_usals(nim, orbpos, num):
	"""nucleul misca motorul prin USALS (NimManager.py:477-480): la LNB 34-36 mereu, altfel dupa `usals` al
	satelitului; la LNB 33 („toti satelitii”) dupa cel al lui sat[3601]"""
	if num >= 34:
		return True
	return bool(cvalue(nim, "advanced", "sat", (3601 + num - 33) if num > 32 else int(orbpos), "usals"))


CSW_PORT = {"AA": u"A", "AB": u"B", "BA": u"C", "BB": u"D"}


def diseqc_text(n, orbpos):
	"""1.0 · port B / toneburst B / 1.1 · port A · intrare 3 / 1.2 / fara."""
	nim = nim_config(n, "s")
	mode = u(cvalue(nim, "configMode"))
	if mode == u"simple":
		dm = u(cvalue(nim, "diseqcMode"))
		port = _port_letter(nim, orbpos) if orbpos >= 0 else u""
		if dm == u"single":
			if cvalue(nim, "simpleSingleSendDiSEqC"):
				return join([u"1.0", (tr("port") + u" A")])
			return tr("none")
		if dm == u"toneburst_a_b":
			return join([u"toneburst", port])
		if dm in (u"diseqc_a_b", u"diseqc_a_b_c_d"):
			return join([u"1.0", (tr("port") + u" " + port) if port else u""])
		if dm in (u"positioner", u"positioner_select"):
			return u"1.2"
		return u""
	if mode == u"advanced" and orbpos >= 0:
		num, lnb = _adv_sat_lnb(nim, orbpos)
		if lnb is None:
			return u""
		dm = u(cvalue(lnb, "diseqcMode"))
		parts = []
		if dm in (u"none", u""):
			parts.append(tr("none"))
		else:
			parts.append(dm.replace(u"_", u"."))
			port = CSW_PORT.get(str(cvalue(lnb, "commitedDiseqcCommand")))
			if port and dm != u"1_2":
				parts.append(tr("port") + u" " + port)
			ucsw = u(cvalue(lnb, "uncommittedDiseqcCommand"))
			if dm in (u"1_1", u"1_2") and ucsw.isdigit() and int(ucsw) > 0:
				parts.append(tr("input") + u" " + ucsw)
		tb = u(cvalue(lnb, "toneburst"))
		if tb in (u"A", u"B"):
			parts.append(u"toneburst " + tb)
		return join(parts)
	return u""


# (lofl, lofh, prag) in MHz pentru LNB-urile cu valori fixe in imagini
LNB_UNIVERSAL = (9750, 10600, 11700)
LNB_CIRCULAR = (10750, 10750, 10750)
LNB_C_BAND = (5150, 5150, 5150)


def lnb_params(n, orbpos):
	"""(fel, (lofl, lofh, prag) sau None) din setarile tunerului; fel = universal, circular, c_band, user, unicable, ka_sat sau ''."""
	nim = nim_config(n, "s")
	mode = u(cvalue(nim, "configMode"))
	if mode == u"simple":
		dm = u(cvalue(nim, "diseqcMode"))
		if dm == u"single" and orbpos in (360, 560) and cvalue(nim, "simpleDiSEqCSetCircularLNB"):
			return "circular", LNB_CIRCULAR
		if dm:
			return "universal", LNB_UNIVERSAL
		return "", None
	if mode == u"advanced" and orbpos >= 0:
		num, lnb = _adv_sat_lnb(nim, orbpos)
		if lnb is None:
			return "", None
		lof = u(cvalue(lnb, "lof"))
		if lof == u"universal_lnb":
			return "universal", LNB_UNIVERSAL
		if lof == u"circular_lnb":
			return "circular", LNB_CIRCULAR
		if lof == u"c_band":
			return "c_band", LNB_C_BAND
		if lof == u"user_defined":
			vals = (ival({"v": cvalue(lnb, "lofl")}, "v"), ival({"v": cvalue(lnb, "lofh")}, "v"), ival({"v": cvalue(lnb, "threshold")}, "v"))
			if min(vals) > 0:
				return "user", vals
			return "user", None
		if lof.startswith(u"unicable") or lof == u"jess":
			return "unicable", None
		if lof == u"ka_sat":
			return "ka_sat", None
	return "", None


def lnb_text(n, orbpos):
	kind, vals = lnb_params(n, orbpos)
	if kind == "universal":
		return join([tr("lnb_universal"), u"9750/10600/11700"])
	if kind == "circular":
		return join([tr("lnb_circular"), u"10750"])
	if kind == "c_band":
		return join([tr("lnb_c_band"), u"5150"])
	if kind == "user":
		if vals is None:
			return u"LOF"
		return u"LOF %d/%d/%d" % vals
	if kind == "unicable":
		return u"Unicable / JESS"
	if kind == "ka_sat":
		return u"Ka-Sat"
	return u""


def lnb_band_text(n, tp):
	"""joasă · 1.744 MHz (banda si frecventa intermediara calculate din setarile LNB; doar la LNB cunoscut)."""
	pos = ival(tp, "orbital_position")
	mhz = to_mhz(tp.get("frequency") if isinstance(tp, dict) else None)
	if mhz is None or pos < 0:
		return u""
	kind, vals = lnb_params(n, pos)
	if vals is None:
		return u""
	lofl, lofh, thr = vals
	if lofl == lofh:
		fi = abs(mhz - lofl)
		band = u""
	else:
		high = mhz >= thr
		fi = abs(mhz - (lofh if high else lofl))
		band = tr("band_high") if high else tr("band_low")
	if not 250.0 <= fi <= 2500.0:
		return u""
	return join([band, fmt_mhz(fi, True) + u" MHz"])


def _speed(val):
	"""ConfigFloat [2, 3] -> 2,3."""
	try:
		if isinstance(val, (list, tuple)) and len(val) >= 2:
			return float(val[0]) + float(val[1]) / 10.0
		return float(val)
	except Exception:
		return 0.0


def rotor_mode_text(n, orbpos):
	"""USALS · 2,3°/s / manual · 2,3°/s (doar cand tunerul are motor)."""
	nim = nim_config(n, "s")
	mode = u(cvalue(nim, "configMode"))
	section = None
	name = u""
	if mode == u"simple" and u(cvalue(nim, "diseqcMode")) in (u"positioner", u"positioner_select"):
		section = nim
		pm = u(cvalue(nim, "positionerMode"))
		name = u"USALS" if pm == u"usals" else (tr("manual") if pm == u"manual" else u"")
	elif mode == u"advanced" and orbpos >= 0:
		num, lnb = _adv_sat_lnb(nim, orbpos)
		if lnb is not None and u(cvalue(lnb, "diseqcMode")) == u"1_2":
			section = lnb
			name = u"USALS" if _adv_usals(nim, orbpos, num) else u"DiSEqC 1.2"
	if section is None:
		return u""
	sp = _speed(cvalue(section, "turningspeedH"))
	return join([name, (fmt_dec(sp, 1) + DEG + u"/s") if sp > 0 else u""])


def has_rotor(n, orbpos):
	return bool(rotor_mode_text(n, orbpos))


def usals_angle_text(n, orbpos):
	"""„USALS 12,3°E”: unghiul la care se roteste motorul pentru satelitul `orbpos`, din coordonatele din Setari tuner
	(aceeasi socoteala ca nucleul, Components/DishMath.py). Numai pe imaginea HDSatelit si numai la USALS; altfel gol."""
	try:
		if n < 0 or orbpos < 0 or not rotor_mode_text(n, orbpos).startswith(u"USALS"):
			return u""
		from Components import DishMath, HdsMotorTuner
		c = HdsMotorTuner.coordonateUsalsNumere(n)
		if not c:
			return u""
		a = DishMath.motorAngle(DishMath.orbitalToDegrees(orbpos), c[0], c[1])
		# literele limbii barei, ca pozitiile (Components/HdsGrade.py)
		try:
			try:
				from Components.HdsGrade import pozitie
			except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
				from HdsGrade import pozitie
			text = u(pozitie(a, 1, lang_code()))
		except Exception:
			text = u""
		return u"USALS %s" % (text or (fmt_dec(abs(a), 1) + DEG + (u"E" if a >= 0 else u"W")))
	except Exception:
		return u""


def rotor_position():
	"""(pozitia din config.misc.lastrotorposition, motorul se misca) sau (-1, False)."""
	pos = -1
	try:
		mod = sys.modules.get("Components.config")
		pos = int(mod.config.misc.lastrotorposition.value)
	except Exception:
		pos = -1
	moving = False
	try:
		mod = sys.modules.get("enigma")
		moving = bool(mod.eDVBSatelliteEquipmentControl.getInstance().isRotorMoving())
	except Exception:
		moving = False
	return pos, moving


def antenna_5v_text(n):
	nim = nim_config(n, "t")
	v = cvalue(nim, "terrestrial_5V")
	if v is None:
		return u""
	return tr("on") if v else tr("off")


# ---------------------------------------------------------------- semnal cinstit (SNR)

# placi la care imaginea scoate dB dintr-o formula pe numele placii, fara legatura cu masura reala
FAKE_DB_NIMS = (u"DVB-S2 NIM",)
SNR_RANGE = {"s": 25.0, "c": 50.0, "t": 45.0, "a": 45.0}
_snr_memo = {"t": -1000.0, "ref": None, "val": None}


def frontend_snr(service, sref):
	"""{'db': sutimi de dB sau -1, 'raw': 0..65535 sau -1, 'number': tuner}, memo 0,5 s."""
	now = _now()
	if _snr_memo["ref"] == sref and 0.0 <= now - _snr_memo["t"] < 0.5:
		return _snr_memo["val"]
	val = None
	try:
		# un serviciu redat dintr-un flux nu are tuner al lui (zerourile canalului PVR nu sunt o masura)
		fe = None if ref_din_flux(sref) else (service and service.frontendInfo())
		if fe:
			val = {"db": -1, "raw": -1, "number": -1}
			for key, cname in (("db", "signalQualitydB"), ("raw", "snrValue"), ("number", "frontendNumber")):
				c = _fe_const(cname)
				if c is None:
					continue
				try:
					val[key] = int(fe.getFrontendInfo(c))
				except Exception:
					pass
	except Exception as e:
		log_once("frontend snr", e)
		val = None
	_snr_memo["t"] = now
	_snr_memo["ref"] = sref
	_snr_memo["val"] = val
	return val


def snr_db_honest(snr, kind):
	"""dB doar daca placa nu e in lista celor cu formula falsa si valoarea e plauzibila pentru felul receptiei; altfel None."""
	if not snr:
		return None
	db = snr.get("db", -1)
	if db <= 0 or db == 0x12345678:
		return None
	n = snr.get("number", -1)
	slot = nim_slot(n) if n >= 0 else None
	desc = u(getattr(slot, "description", u"")).strip() if slot is not None else u""
	if not desc or desc in FAKE_DB_NIMS:
		return None
	top = SNR_RANGE.get(kind)
	value = db / 100.0
	if top is None or not 0.0 < value <= top:
		return None
	return value


def snr_raw_pct(snr):
	"""SNR brut al driverului in procente; None cand placa nu da nimic (0 = fara citire)."""
	try:
		raw = int(snr.get("raw", -1))
	except Exception:
		return None
	if raw <= 0:
		return None
	return percent16(raw)


TUNER_STATES = {"LOCKED": "st_locked", "TUNING": "st_tuning", "FAILED": "st_failed", "LOSTLOCK": "st_lost", "IDLE": "st_idle"}
_state_memo = {"t": -1000.0, "ref": None, "val": u""}


def tuner_state(service, sref):
	now = _now()
	if _state_memo["ref"] == sref and 0.0 <= now - _state_memo["t"] < 0.9:
		return _state_memo["val"]
	val = u""
	try:
		if ref_din_flux(sref):
			# flux: starea tunerului care tine purtatorul, dupa lock-ul citit de controlor; nestiut = gol
			lock = ival(semnal_purtator(sref) or {}, "lock")
			val = u"LOCKED" if lock == 1 else (u"LOSTLOCK" if lock == 0 else u"")
		else:
			fe = service and service.frontendInfo()
			d = fe.getAll(False) if fe else None
			if isinstance(d, dict):
				val = u(d.get("tuner_state")).upper()
	except Exception as e:
		log_once("tuner_state", e)
		val = u""
	_state_memo["t"] = now
	_state_memo["ref"] = sref
	_state_memo["val"] = val
	return val


# ---------------------------------------------------------------- receptorul (fisiere citite rar, memo pe modul)

PROC_STAT = "/proc/stat"
PROC_MEMINFO = "/proc/meminfo"
PROC_UPTIME = "/proc/uptime"
PROC_CPUINFO = "/proc/cpuinfo"
ENIGMA_INFO = "/usr/lib/enigma.info"
IMAGE_VERSION = "/etc/image-version"
CHIPSET_FILE = "/proc/stb/info/chipset"
TEMP_FILES = (
	("/proc/stb/fp/temp_sensor_avs", 1), ("/proc/stb/power/avs", 1), ("/proc/stb/fp/temp_sensor", 1),
	("/proc/stb/sensors/temp0/value", 1), ("/proc/stb/sensors/temp/value", 1),
	("/sys/devices/virtual/thermal/thermal_zone0/temp", 1000), ("/proc/hisi/msp/pm_cpu", 0),
)


def read_small(path, limit=16384):
	"""Continutul unui fisier mic ca text, sau None daca lipseste."""
	try:
		if not os.path.exists(path):
			return None
		f = open(path, "rb")
		try:
			return f.read(limit).decode("utf-8", "replace")
		finally:
			f.close()
	except Exception:
		return None


def _kv_file(text):
	d = {}
	for line in (text or u"").splitlines():
		if u"=" not in line or line.lstrip().startswith(u"#"):
			continue
		k, v = line.split(u"=", 1)
		d[k.strip().lower()] = v.strip().strip(u"'\"")
	return d


# regulile modelului pentru care e construita imaginea (aceleasi ca in Components/HdsPazaModel.py)
HDSATELIT_MODEL = "/etc/hdsatelit-model"


def _model_din_reguli():
	"""(marca, model) din primul „model=” al regulilor modelului: „Amiko Viper 4K V20” -> (u"Amiko", u"Viper 4K
	V20"); numai litere, cifre, spatii si . _ - + ( ), cel mult 60 de caractere; (u"", u"") fara fisier sau cheie"""
	for line in (read_small(HDSATELIT_MODEL) or u"").splitlines():
		line = line.strip()
		if line.startswith(u"#") or u"=" not in line:
			continue
		k, v = line.split(u"=", 1)
		if k.strip() == u"model":
			v = u"".join(ch for ch in v.strip() if ch.isalnum() or ch in u" ._-+()").strip()[:60]
			marca, _sep, rest = v.partition(u" ")
			return (marca, rest.strip()) if rest.strip() else (u"", v)
	return u"", u""


_box = {"val": None}


def box_info():
	"""Marca, modelul, imaginea, cipul si nucleele, citite o singura data."""
	if _box["val"] is not None:
		return _box["val"]
	info = {"brand": u"", "model": u"", "distro": u"", "version": u"", "build": u"", "soc": u"", "cores": 0, "ver_text": u""}
	try:
		ei = _kv_file(read_small(ENIGMA_INFO))
		info["brand"] = ei.get(u"displaybrand") or ei.get(u"brand") or u""
		info["model"] = ei.get(u"displaymodel") or ei.get(u"model") or u""
		info["distro"] = ei.get(u"displaydistro") or ei.get(u"distro") or u""
		info["version"] = ei.get(u"imageversion") or u""
		info["build"] = ei.get(u"imagebuild") or u""
		info["soc"] = ei.get(u"socfamily") or u""
		if not info["model"]:
			try:
				import boxbranding as bb
				for key, fname in (("brand", "getMachineBrand"), ("model", "getMachineName"), ("distro", "getImageDistro"),
						("version", "getImageVersion"), ("build", "getImageBuild")):
					if not info[key]:
						info[key] = u(_call(bb, fname)).strip()
			except Exception:
				pass
		if not info["model"]:
			iv = _kv_file(read_small(IMAGE_VERSION))
			info["brand"] = info["brand"] or iv.get(u"machine_brand", u"")
			info["model"] = iv.get(u"machine_name", u"")
			info["distro"] = info["distro"] or iv.get(u"distro", u"") or iv.get(u"creator", u"")
			info["version"] = info["version"] or iv.get(u"version", u"")
		# numele din regulile modelului (pe V20 acelasi ca textul de mai jos); textul scris aici ramane rezerva
		marca_reguli, model_reguli = _model_din_reguli()
		if not info["model"]:
			if model_reguli:
				info["brand"] = info["brand"] or marca_reguli
				info["model"] = model_reguli
			else:
				try:
					bt = (read_small("/proc/stb/info/boxtype", 64) or u"").strip().lower()
					hn = (read_small("/etc/hostname", 64) or u"").strip().lower()
					# primul Viper 4K (V10): driverul spune viper4k si numele de gazda e viper4k (fara v20)
					if bt == u"viper4k" or hn == u"viper4k":
						info["brand"] = info["brand"] or u"Amiko"
						info["model"] = u"Viper 4K V10"
					elif bt == u"u57" or u"viper4k" in hn:
						info["brand"] = info["brand"] or u"Amiko"
						info["model"] = u"Viper 4K V20" if u"viper4kv20" in hn else u"Viper 4K"
				except Exception:
					pass
		elif info["model"].lower() == u"viper 4k":
			if model_reguli:
				info["model"] = model_reguli
			else:
				# numele gazdei pus de imagine spune sigur varianta placii (viper4kv20)
				hn = (read_small("/etc/hostname", 64) or u"").strip().lower()
				if u"viper4kv20" in hn:
					info["model"] = u"Viper 4K V20"
		if not info["soc"]:
			info["soc"] = (read_small(CHIPSET_FILE, 256) or u"").strip()
		cpu = read_small(PROC_CPUINFO, 65536) or u""
		cores = 0
		hw = u""
		for line in cpu.splitlines():
			low = line.lower()
			# un nucleu = „processor : <numar>”; nucleele ARMv7 au si randul „Processor : ARMv7 ...” (fara numar),
			# care nu e alt nucleu
			if low.startswith(u"processor") and u":" in low and low.split(u":", 1)[1].strip().isdigit():
				cores += 1
			elif not hw and (low.startswith(u"hardware") or low.startswith(u"system type") or low.startswith(u"model name")) and u":" in line:
				hw = line.split(u":", 1)[1].strip()
		info["cores"] = cores
		if not info["soc"]:
			info["soc"] = hw
		info["ver_text"] = image_version_text()
	except Exception as e:
		log_once("box_info", e)
	for k in ("brand", "model", "distro", "version", "build", "soc"):
		info[k] = u(info[k])[:40]
	_box["val"] = info
	return info


def box_name():
	b = box_info()
	brand, model = b["brand"], b["model"]
	if brand and model.lower().startswith(brand.lower()):
		brand = u""
	return join([brand, model], u" ")


def image_version_text(text=None):
	"""Versiunea din /etc/image-version cand are forma OE (`version=` cu 16 cifre: felul, major, minor, revizia,
	AAAALLZZ, hhmm): "0.1.4"; felul 1 = experimentala. Cu 19 cifre (o parte a versiunii are doua cifre)
	major, minor si revizia stau pe cate doua cifre: "0.3.10". Gol pe celelalte forme. Se citeste o
	singura data, cu box_info."""
	try:
		if text is None:
			text = read_small(IMAGE_VERSION, 4096)
		v = _kv_file(text).get(u"version", u"").strip()
		if len(v) == 19 and v.isdigit() and all(u"0" <= c <= u"9" for c in v):
			# aceeasi zi si ora la sfarsit; versiunea fara zerourile din fata fiecarei parti
			ver = u"%d.%d.%d" % (int(v[1:3]), int(v[3:5]), int(v[5:7]))
			v = v[0] + u"000" + v[7:]
		else:
			ver = None
		if len(v) == 16 and v.isdigit():
			date = u"%s.%s.%s" % (v[10:12], v[8:10], v[4:8])
			if v[0] == u"0":
				return u"%s (%s)" % (ver or u"%s.%s.%s" % (v[1], v[2], v[3]), date)
			return u"%s (%s)" % (tr("image_experimental"), date)
	except Exception as e:
		log_once("image_version", e)
	return u""


def image_name(scurt=False):
	"""HD Satelit 0.1.4 pe imaginea noastra; pe celelalte numele si versiunea date de imagine. scurt: fara partea din
	paranteza (data versiunii, numarul constructiei), pentru locurile inguste."""
	b = box_info()
	ver = b.get("ver_text", u"")
	distro = b["distro"]
	if distro.replace(u" ", u"").lower() == u"hdsatelit":
		distro = u"HD Satelit"
	if ver:
		if scurt:
			ver = ver.split(u" (")[0]
		return join([distro, ver], u" ")
	build = b["build"] if b["build"].isdigit() else u""
	return join([distro, b["version"], (u"(%s)" % build) if build and not scurt else u""], u" ")


def chipset_text(with_cores=True):
	"""Cipul receptorului („Hi3798MV200”), cu „Număr nuclee: 4” dupa el cand `with_cores` (altfel numarul are randul
	lui, cores_text)."""
	b = box_info()
	soc = b["soc"].strip()
	low = soc.lower()
	if low.startswith(u"hisi"):
		# numele cipului dat de HiSilicon: Hi3798MV200 (socfamily=hisi3798mv200 in enigma.info), la fel ca din chipset
		soc = u"Hi" + soc[4:].upper()
	elif len(low) > 4 and low[:2] in (u"37", u"38") and low[:4].isdigit():
		# cipurile HiSilicon pentru receptoare apar fara prefix in /proc/stb/info/chipset (3798mv200)
		soc = u"Hi" + soc.upper()
	elif low.startswith(u"bcm"):
		soc = u"Broadcom BCM" + soc[3:].upper()
	elif low.startswith(u"brcm"):
		soc = u"Broadcom " + soc[4:].upper()
	elif soc and soc == low:
		soc = soc.upper()
	cores = b["cores"]
	if not with_cores:
		return soc
	return join([soc, (u"%s: %d" % (tr("cnt_cores"), cores)) if cores > 1 else u""])


def cores_text():
	"""Numarul nucleelor procesorului („4”), gol cand nu se stie sau e unul singur (randul se ascunde)."""
	n = box_info()["cores"]
	return (u"%d" % n) if n > 1 else u""


_cpu = {"t": -1000.0, "sample": None, "prev": None}
# pasul obisnuit intre doua citiri din /proc/stat; o caseta care abia s-a aratat cere unul mai scurt (HdsSignal)
CPU_PAS_S = 1.5
# cat de veche poate fi masurarea pazei procesorului folosita la prima afisare (paza masoara la 5 s)
CPU_PAZA_S = 15.0


def _cpu_read():
	text = read_small(PROC_STAT, 4096)
	if not text:
		return None
	try:
		f = [int(x) for x in text.splitlines()[0].split()[1:9]]
		idle = f[3] + (f[4] if len(f) > 4 else 0)
		return (sum(f), idle)
	except Exception:
		return None


def cpu_sample(min_gap=CPU_PAS_S):
	"""O citire din /proc/stat, cel mult una la min_gap secunde (implicit 1,5 s) pentru toate widgeturile."""
	now = _now()
	if 0.0 <= now - _cpu["t"] < min_gap:
		return
	s = _cpu_read()
	if s is None:
		_cpu["t"] = now
		return
	_cpu["prev"] = (_cpu["t"], _cpu["sample"])
	_cpu["t"] = now
	_cpu["sample"] = s


def cpu_load(min_gap=CPU_PAS_S):
	"""Procentul de procesor folosit intre ultimele doua citiri (cel mult 60 s distanta), sau None. Fara o diferenta
	proaspata: masurarea pazei procesorului (numai pe imaginea HDSatelit, la 5 s, _cpu_paza). Daca nici ea nu e si
	min_gap e mic (o caseta care abia s-a aratat), citirea noua se face dupa numai atatea secunde de la cea dinainte.
	Procentul apare la prima afisare sau aproape pe loc, fara sa blocheze ecranul si fara valori mai vechi de 60 s."""
	cpu_sample()
	v = _cpu_percent()
	if v is None:
		v = _cpu_paza()
	if v is None and min_gap < CPU_PAS_S:
		cpu_sample(min_gap)
		v = _cpu_percent()
	return v


def _cpu_paza():
	"""Procentul masurat de paza procesorului intre ultimii ei doi pasi (Components/HdsProcesor.folositRecent, cel
	mult CPU_PAZA_S secunde), sau None pe alte imagini si cand paza nu merge."""
	p = procesor_modul()
	if p is None:
		return None
	try:
		r = p.folositRecent(CPU_PAZA_S)
		return max(0, min(100, int(r[0]))) if r else None
	except Exception as e:
		log_once("cpu_paza", e)
		return None


def _cpu_percent():
	"""Procentul dintre ultimele doua citiri din _cpu, sau None (lipsa, mai departe de 60 s, numaratori stricate)."""
	prev = _cpu["prev"]
	cur = _cpu["sample"]
	if not prev or prev[1] is None or cur is None:
		return None
	if not 0.0 < _cpu["t"] - prev[0] <= 60.0:
		return None
	total = cur[0] - prev[1][0]
	idle = cur[1] - prev[1][1]
	if total <= 0 or idle < 0:
		return None
	return max(0, min(100, int(round(100.0 * (total - idle) / total))))


_file_memo = {}


def _memo_file(key, max_age, fn):
	"""Rezultatul lui fn tinut max_age secunde (si „lipsa"), ca N widgeturi sa citeasca o singura data."""
	now = _now()
	e = _file_memo.get(key)
	if e is not None and 0.0 <= now - e[0] < max_age:
		return e[1]
	try:
		v = fn()
	except Exception as err:
		log_once(key, err)
		v = None
	if len(_file_memo) > 16:
		_file_memo.clear()
	_file_memo[key] = (now, v)
	return v


def mem_free():
	"""(liber MB, total MB) sau None."""
	def fn():
		text = read_small(PROC_MEMINFO, 8192)
		if not text:
			return None
		d = {}
		for line in text.splitlines():
			parts = line.replace(u":", u" ").split()
			if len(parts) >= 2 and parts[1].isdigit():
				d[parts[0]] = int(parts[1])
		total = d.get(u"MemTotal", 0)
		free = d.get(u"MemAvailable")
		if free is None:
			free = d.get(u"MemFree", 0) + d.get(u"Buffers", 0) + d.get(u"Cached", 0)
		if total <= 0:
			return None
		return (min(free, total) // 1024, total // 1024)
	return _memo_file("meminfo", 4.0, fn)


def temperature():
	"""Temperatura in grade, din primul senzor gasit, sau None (fara senzor randul ramane gol)."""
	def fn():
		import re
		for path, div in TEMP_FILES:
			text = read_small(path, 2048)
			if not text:
				continue
			if div == 0:
				m = re.search(u"temperature\\s*=\\s*(-?\\d+)", text)
				value = int(m.group(1)) if m else None
			else:
				m = re.search(u"-?\\d+", text)
				value = int(m.group(0)) // div if m else None
			if value is not None and 1 <= value <= 125:
				return value
		return None
	return _memo_file("temp", 20.0, fn)


_procesor = {"m": None, "cautat": False}


def procesor_modul():
	"""Components/HdsProcesor (numai pe imaginea HDSatelit), cautat o singura data; None pe alte imagini."""
	if not _procesor["cautat"]:
		_procesor["cautat"] = True
		try:
			from Components import HdsProcesor
			_procesor["m"] = HdsProcesor
		except Exception:
			_procesor["m"] = None
	return _procesor["m"]


def procesor_camp(cheie):
	"""Un camp din HdsProcesor.campuriBara() (setata = modul si plafonul, tensiune, trepte = timpul pe fiecare
	frecventa), din citirea memorata 2 s a modulului; text gol pe alte imagini sau cand nu se poate citi."""
	p = procesor_modul()
	if p is None:
		return u""
	try:
		v = u(p.campuriBara().get(cheie) or u"")
	except Exception as e:
		log_once("procesor_" + cheie, e)
		return u""
	if cheie == "trepte":
		v = trepte_text(v)
	return v


def trepte_text(v):
	"""„400: 89% · 600: 5%” -> „400 MHz: 89% ·600 MHz: 5%” cu spatii care nu se rup in pereche: in coloana ingusta
	fiecare pereche ramane intreaga, iar randul se rupe inainte de „·”, nu dupa el."""
	parti = []
	for p in u(v).split(SEP):
		p = p.strip()
		if not p:
			continue
		if u":" in p:
			a, b = p.split(u":", 1)
			a = a.strip()
			if a.isdigit():
				a = u"%s MHz" % a
			p = u"%s: %s" % (a, b.strip())
		parti.append(p.replace(u" ", u"\u00a0"))
	return u" \u00b7\u00a0".join(parti)


def procesor_temperatura():
	"""Temperatura procesorului din citirea de 2 s a HdsProcesor, sau None (atunci temperature(), memorata 20 s)."""
	p = procesor_modul()
	if p is None:
		return None
	try:
		t = p.citire(2.0).get("temperatura")
		return int(t) if t is not None else None
	except Exception as e:
		log_once("procesor_temp", e)
		return None


def uptime_seconds():
	def fn():
		text = read_small(PROC_UPTIME, 256)
		if not text:
			return None
		return int(float(text.split()[0]))
	v = _memo_file("uptime", 20.0, fn)
	if v is None:
		return None
	return v


def uptime_text(sec):
	if sec is None or sec < 0:
		return u""
	h = sec // 3600
	m = (sec % 3600) // 60
	return u"%d h %02d %s" % (h, m, tr("unit_min"))


def stream_clients():
	"""Numarul clientilor de flux (fara adrese), sau 0/None pe imaginile fara API."""
	def fn():
		mod = sys.modules.get("enigma")
		srv = getattr(mod, "eStreamServer", None)
		if srv is not None:
			try:
				lst = srv.getInstance().getConnectedClients()
				if isinstance(lst, (list, tuple)):
					return len(lst)
			except Exception:
				pass
		try:
			cnt = 0
			citit = False
			# HDSatelit: clientii din reteaua locala se numara pe IPv4 si pe IPv6
			# (acelasi tipar ca alaturi, in HdsComun/sesiuni8001.py) -- un client pe
			# retea locala prin IPv6 nu era numarat deloc altfel.
			for cale in ("/proc/net/tcp", "/proc/net/tcp6"):
				tcp = read_small(cale, 32768)
				if not tcp:
					continue
				citit = True
				for line in tcp.splitlines()[1:]:
					parts = line.split()
					if len(parts) >= 4:
						loc = parts[1]
						st = parts[3]
						if st == "01" and (loc.endswith(":1F41") or loc.endswith(":1F42")):
							# HDSatelit: pluginurile
							# proprii HdsDab/HdsT2mi/HdsDvbI se conecteaza CHIAR ELE, prin bucla locala
							# (127.0.0.1 / ::1), la acest port ca sa preia purtatorul de la
							# streamserver-ul enigma2 -- o astfel de conexiune arata identic cu un
							# client extern real -- umfland numarul afisat userului exact cand se uita
							# la un canal DAB/T2-MI. "0100007F" e 127.0.0.1 in hex (ordinea de octeti
							# folosita de kernel in acest fisier, verificat direct); IPv6 loopback
							# (::1) apare complet ca zerouri urmate de "1".
							rem = parts[2] if len(parts) >= 3 else ""
							rem_upper = rem.upper()
							e_loopback = rem_upper.startswith("0100007F:") or rem_upper.startswith("00000000000000000000000001000000:")
							if not e_loopback:
								cnt += 1
			return cnt if citit else 0
		except Exception:
			pass
		return 0
	return _memo_file("stream", 4.0, fn)


# ================================================================ CAM-ul care decodeaza
#
# Doar doua surse: API-ul CI din enigma2 (eDVBCI_UI, eDVBCIInterfaces) si starea standard a serviciului
# (sIsCrypted, sCAIDs, evVideoSizeChanged dupa evStart, sVideoHeight). Nu se citeste niciun fisier sau proces
# al vreunui program de decodare si nu se deschide nicio legatura de retea.
# Singurul fisier citit e /proc/stb/tsmux/input<n> (driverul receptorului: prin ce slot CI trece tunerul),
# doar cand exista sloturi CI gata, cel mult o data pe schimbare de serviciu sau de stare CI.

try:
	from enigma import eDVBCI_UI as _CI_UI
except Exception:
	_CI_UI = None

try:
	from enigma import eDVBCIInterfaces as _CI_IF
except Exception:
	_CI_IF = None

TSMUX_INPUT = "/proc/stb/tsmux/input%d"
CAM_NAME_MAX = 32
CAM_KINDS = ("s", "c", "t", "a")

# what = ultimul eveniment tratat; start = None (niciun evStart / evEnd vazut), True dupa evStart, False dupa evEnd; video = evVideoSizeChanged dupa evStart;
# gen = creste la fiecare ciStateChanged; hooked = abonat la ciStateChanged; slots = numarul sloturilor (-1 necitit);
# tsmux = {tuner: slot} citit din driver pana la urmatorul zap
# t_start = cand a pornit serviciul redat (evStart), ca raspunsul camului scris inainte sa nu fie luat drept al lui
_cam = {"what": None, "start": None, "video": False, "gen": 0, "hooked": False, "slots": -1, "tsmux": {},
	"t_start": None}
# {id: convertor}, cu referinte slabe (nu tin convertorul viu)
_cam_subs = _weakref.WeakValueDictionary() if _weakref is not None else {}


def _ci_ui():
	try:
		return _CI_UI.getInstance() if _CI_UI is not None else None
	except Exception:
		return None


def _ci_if():
	try:
		return _CI_IF.getInstance() if _CI_IF is not None else None
	except Exception:
		return None


def cam_slots():
	"""Numarul sloturilor CI (citit o singura data; 0 cand imaginea nu are API sau receptorul nu are CI)."""
	n = _cam["slots"]
	if n >= 0:
		return n
	n = 0
	try:
		ci = _ci_if()
		if ci is not None:
			n = int(ci.getNumOfSlots() or 0)
	except Exception as e:
		log_once("cam_slots", e)
		n = 0
	n = n if 0 <= n <= 8 else 0
	_cam["slots"] = n
	return n


def _ci_changed(slot=-1):
	"""Chemat de enigma2 (ciStateChanged): starea unui slot sau a decodarii s-a schimbat."""
	try:
		_cam["gen"] += 1
		_cam["tsmux"] = {}
		for conv in list(_cam_subs.values()):
			try:
				conv._on_cam()
			except Exception as e:
				log_once("cam notify", e)
	except Exception as e:
		log_once("ci_changed", e)


def cam_subscribe(conv):
	"""Convertorul primeste _on_cam() la schimbarea starii CI. Abonamentul la enigma2 se pune o singura data."""
	try:
		_cam_subs[id(conv)] = conv
	except Exception:
		pass
	if _cam["hooked"]:
		return
	_cam["hooked"] = True
	try:
		if cam_slots() <= 0:
			return
		ui = _ci_ui()
		sig = getattr(ui, "ciStateChanged", None) if ui is not None else None
		if sig is not None:
			sig.get().append(_ci_changed)
	except Exception as e:
		log_once("cam_subscribe", e)


def cam_unsubscribe(conv):
	try:
		_cam_subs.pop(id(conv), None)
	except Exception:
		pass


# ------------------------------------------------------------ inregistrarile in curs (semnul REC)

_rec_subs = {}
_rec = {"hooked": False}


def inregistrari_in_curs():
	"""Cate inregistrari merg acum (Navigation.getRecordings, ca sursa session.RecordState); 0 fara navigare."""
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
		return len(nav.getRecordings()) if nav is not None else 0
	except Exception as e:
		log_once("inregistrari_in_curs", e)
		return 0


def _rec_event(*args):
	for conv in list(_rec_subs.values()):
		try:
			conv._on_rec()
		except Exception as e:
			log_once("rec", e)


def rec_subscribe(conv):
	"""Convertorul primeste _on_rec() cand porneste sau se opreste o inregistrare. Abonamentul la enigma2
	(Navigation.record_event) se pune o singura data, cand navigarea exista."""
	try:
		_rec_subs[id(conv)] = conv
	except Exception:
		pass
	if _rec["hooked"]:
		return
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
		ev = getattr(nav, "record_event", None) if nav is not None else None
		if ev is not None:
			ev.append(_rec_event)
			_rec["hooked"] = True
	except Exception as e:
		log_once("rec_subscribe", e)


def rec_unsubscribe(conv):
	try:
		_rec_subs.pop(id(conv), None)
	except Exception:
		pass


def cam_event(what, name):
	"""evStart / evEnd / evVideoSizeChanged ale serviciului redat. Acelasi `what` se trateaza o singura data."""
	try:
		if what is not None and _cam["what"] is what:
			return
		_cam["what"] = what
		if name in ("evStart", "evEnd"):
			_cam["start"] = (name == "evStart")
			_cam["video"] = False
			_cam["tsmux"] = {}
			if name == "evStart":
				_cam["t_start"] = _now()
		elif name == "evVideoSizeChanged" and _cam["start"] is True:
			_cam["video"] = True
	except Exception as e:
		log_once("cam_event", e)


def cam_start():
	"""Serviciul redat a pornit acum (chemat si de imagine la evStart, cand niciun convertor CAM nu e treaz)."""
	_cam["t_start"] = _now()


def cam_picture(r):
	"""Imaginea se decodeaza: evVideoSizeChanged venit dupa evStart si inaltime video reala.

	In enigma2 nu exista un semn „codat" pentru serviciul redat. Decodorul nu poate citi antetul video din
	pachete codate, deci evenimentul de marime vine doar cand imaginea chiar se decodeaza. Inaltimea singura nu
	ajunge (pe unele imagini ramane cea a canalului dinainte). Daca evStart nu a fost vazut (convertor creat
	dupa zap), ramane doar inaltimea."""
	try:
		if r.geti("sVideoHeight") <= 0:
			return False
		if _cam["start"] is None:
			return True
		return _cam["start"] is True and bool(_cam["video"])
	except Exception:
		return False


def _clean_name(s):
	t = u(s)
	t = u"".join([c if (c >= u" " and c != u"\x7f") else u" " for c in t])
	t = u" ".join(t.split())
	if len(t) > CAM_NAME_MAX:
		t = t[:CAM_NAME_MAX - 1].rstrip() + u"…"
	return t


def ci_module_name(slot):
	"""Numele dat de modulul din slot (Application Information), sau `CI <n>` cand modulul nu da nume."""
	name = u""
	try:
		ui = _ci_ui()
		if ui is not None:
			name = _clean_name(ui.getAppName(slot))
	except Exception as e:
		log_once("ci_module_name", e)
		name = u""
	try:
		return name or (u"CI %d" % (int(slot) + 1))
	except Exception:
		return u"CI"


def _ci_state(ui, slot):
	try:
		return int(ui.getState(slot))
	except Exception:
		return -1


def _ci_decoding(ui, slot):
	"""Starea decodarii (2 = modulul CI+ decodeaza); -1 pe imaginile fara getDecodingState."""
	fn = getattr(ui, "getDecodingState", None)
	if fn is None:
		return -1
	try:
		return int(fn(slot))
	except Exception:
		return -1


def _tsmux_slot(n):
	"""Slotul CI prin care trece tunerul n dupa driver (`CI0` -> 0), sau -1. Memo pana la urmatorul zap / schimbare CI."""
	if n < 0:
		return -1
	memo = _cam["tsmux"]
	if n in memo:
		return memo[n]
	v = -1
	try:
		t = read_small(TSMUX_INPUT % n, 64)
		t = u(t).strip().upper() if t else u""
		if t[:2] == u"CI" and t[2:3].isdigit():
			v = int(t[2:3])
	except Exception:
		v = -1
	if len(memo) < 16:
		memo[n] = v
	return v


def _ns_equal(a, b):
	try:
		a, b = int(a) & 0xFFFFFFFF, int(b) & 0xFFFFFFFF
		return a == b or (a >> 16) == (b >> 16)
	except Exception:
		return False


def _as_list(x):
	return list(x) if isinstance(x, (list, tuple)) else []


def ci_slot_matches(r, slot):
	"""Serviciul redat poate trece prin slot, dupa aceeasi regula ca enigma2 (recheckPMTHandlers):
	referinta, furnizorul sau un CAID din regulile slotului; fara reguli, un CAID anuntat de modul.
	In plus, driverul (tsmux) poate spune direct ca tunerul trece prin slot (doar dovada pentru, niciodata impotriva)."""
	if _tsmux_slot(fe_number(r)) == slot:
		return True
	ci = _ci_if()
	if ci is None:
		return False
	caids = set(r.caids())
	try:
		rules = ci.getDescrambleRules(slot)
	except Exception:
		rules = None
	rules = _as_list(rules)
	services = _as_list(rules[0]) if len(rules) > 0 else []
	providers = _as_list(rules[1]) if len(rules) > 1 else []
	rcaids = _as_list(rules[2]) if len(rules) > 2 else []
	if services or providers or rcaids:
		me = norm_ref(r.sref())
		for s in services:
			if me and norm_ref(s) == me:
				return True
		prov = r.gets("sProvider").lower()
		ns = r.geti("sNamespace")
		for p in providers:
			try:
				if prov and u(p[0]).lower() == prov and _ns_equal(p[1], ns):
					return True
			except Exception:
				continue
		for c in rcaids:
			try:
				if int(c) in caids:
					return True
			except Exception:
				continue
		return False
	try:
		mc = ci.readCICaIds(slot)
	except Exception:
		mc = None
	for c in _as_list(mc):
		try:
			if int(c) in caids:
				return True
		except Exception:
			continue
	return False


def cam_source(r):
	"""("ci", slot) modul CI, ("other", -1) imagine decodata fara modul CI potrivit, ("", -1) nimic de aratat.

	FTA, fara serviciu, inregistrare, fisier, flux: nimic. Codat fara imagine si fara modul CI+ care decodeaza: nimic.
	Memo pe eveniment (toate convertoarele CAM ale aceluiasi eveniment citesc o singura data)."""
	def fn():
		if r.info() is None or r.kind() not in CAM_KINDS or not r.crypted():
			return ("", -1)
		n = cam_slots()
		ui = _ci_ui() if n > 0 else None
		ready = []
		if ui is not None:
			for slot in range(n):
				st = _ci_state(ui, slot)
				if st in (-1, 0, 3):
					continue
				if _ci_decoding(ui, slot) == 2 and ci_slot_matches(r, slot):
					return ("ci", slot)
				if st == 2:
					ready.append(slot)
		if not cam_picture(r):
			return ("", -1)
		for slot in ready:
			if ci_slot_matches(r, slot):
				return ("ci", slot)
		return ("other", -1)
	v = r._memo("cam", fn)
	return v if v else ("", -1)


def cam_name(r):
	"""Numele modulului CI care decodeaza; cand imaginea se decodeaza fara modul CI, numele camului ales in gestiunea
	modulelor de acces (access_module_name); `Altele` (tradus) numai cand nu se afla nimic; altfel gol."""
	kind, slot = cam_source(r)
	if kind == "ci":
		return ci_module_name(slot)
	if kind == "other":
		return access_module_name() or tr("cam_other")
	return u""


# ---------------------------------------------------------------- pagina 4: camul care decripteaza acum
# Ce spune camul care decripteaza (CAID-ul, PID-ul ECM, furnizorul, timpul, protocolul, local sau prin retea) si numele
# camului ales in gestiunea camurilor le da modulul imaginii Components/HdsEcm.py; skinul (care merge si pe alte
# imagini) nu citeste nimic al vreunui cam. Fara modul: nicio caseta, niciun rand de la cam, CAM = „Altele”.
# Numele cititorului, adresele si porturile nu ajung niciodata aici.

ECM_FRESH_S = 120.0
ECM_ROWS = 4
_ca_view = {"top": 0, "vis": 7}
_ecm_mod = [False]


def _ecm():
	"""Modulul imaginii Components.HdsEcm, sau None; importul se incearca o singura data."""
	if _ecm_mod[0] is False:
		try:
			from Components import HdsEcm
			_ecm_mod[0] = HdsEcm
		except Exception:
			_ecm_mod[0] = None
	return _ecm_mod[0]


def ecm_info():
	"""Ce spune camul care decripteaza acum (dictionarul lui HdsEcm.stare, cu `mtime`), sau {}."""
	m = _ecm()
	if m is None:
		return {}
	try:
		return m.stare() or {}
	except Exception as e:
		log_once("ecm", e)
		return {}


def _service_caids(r):
	caids = list(r.caids())
	for c, p in r.caidpids():
		if c not in caids:
			caids.append(c)
	return caids


def ecm_active(r):
	"""CAID-ul prin care se decripteaza acum serviciul redat, sau -1: numai daca raspunsul camului e proaspat
	(ECM_FRESH_S), e scris dupa pornirea serviciului (t_start; altfel e al canalului dinainte, chiar cu acelasi CAID),
	CAID-ul lui e al canalului si, cand PMT-ul da PID-urile ECM ale CAID-ului, PID-ul raspunsului e unul dintre ele.
	Canal nedecriptat: -1."""
	try:
		if r.info() is None or r.kind() not in CAM_KINDS:
			return -1
		d = ecm_info()
		caid = d.get("caid", -1)
		if caid <= 0:
			return -1
		mtime = d.get("mtime", 0.0)
		acum = _now()
		age = acum - mtime
		if not -5.0 <= age <= ECM_FRESH_S:
			return -1
		t0 = _cam.get("t_start")
		# t0 din viitor = ceasul receptorului s-a dat inapoi dupa pornire: nu se mai poate compara
		if t0 is not None and t0 <= acum + 5.0 and _cam.get("start") is not False and mtime < t0 - 1.0:
			return -1
		caids = _service_caids(r)
		if not caids or caid not in caids:
			return -1
		pid = d.get("pid", 0)
		pids = [p for c, p in r.caidpids() if c == caid and 0 < p < 0x1FFF]
		if pid > 0 and pids and pid not in pids:
			return -1
		return caid
	except Exception as e:
		log_once("ecm_active", e)
		return -1


def ecm_system_name(caid, d=None):
	"""Numele sistemului pentru CAID (tabelul skinului), altfel ce scrie camul, altfel 0x...."""
	name = caid_name(caid)
	if name:
		return name
	if d and d.get("system"):
		return d["system"]
	return u"0x%04X" % caid


def ecm_rows(r):
	"""Randurile „de la CAM” pentru pagina 4, numai cand camul decripteaza acum canalul: sistemul si CAID-ul, PID-ul
	ECM si furnizorul, timpul ECM si pasii, protocolul si locul (local / prin retea)."""
	caid = ecm_active(r)
	if caid <= 0:
		return []
	d = ecm_info()
	rows = [u"%s: %s · CAID %04X" % (tr("ecm_system"), ecm_system_name(caid, d), caid)]
	# furnizorul 000000 = niciun furnizor (nu se arata); pasii retelei (hops) nu spun nimic omului, nu se arata
	prov = u""
	if d.get("prov", -1) > 0:
		prov = u"%06X" % d["prov"]
	if d.get("prov_name"):
		prov = join([prov, d["prov_name"]], u" ")
	rows.append(join([(u"%s: %d" % (tr("ecm_pid"), d["pid"])) if d.get("pid", 0) > 0 else u"",
		(u"%s: %s" % (tr("provider"), prov)) if prov else u""]))
	rows.append((u"%s: %d ms" % (tr("ecm_time"), d["ms"])) if d.get("ms", -1) >= 0 else u"")
	where = u""
	if "local" in d:
		where = tr("ecm_local") if d["local"] else tr("ecm_net")
	rows.append(join([(u"%s: %s" % (tr("ecm_protocol"), d["protocol"])) if d.get("protocol") else u"", where]))
	return [x for x in rows if x][:ECM_ROWS]


def access_module_name():
	"""Numele camului ales in gestiunea modulelor de acces (HdsEcm.nume_cam), sau gol."""
	m = _ecm()
	if m is None:
		return u""
	try:
		return _clean_name(m.nume_cam() or u"")
	except Exception as e:
		log_once("access_module", e)
		return u""


def ca_entries(r):
	"""[(caid, ecm_pid)] ale canalului: din PMT cu PID-ul ECM, apoi CAID-urile din lista de canale (pid -1)."""
	if r.kind() not in DVB_KINDS_ALL:
		return []
	rows = []
	have = set()
	for caid, pid in r.caidpids():
		have.add(caid)
		rows.append((caid, pid))
	for caid in r.caids():
		if caid not in have:
			rows.append((caid, -1))
	return rows


DVB_KINDS_ALL = ("s", "c", "t", "a", "record")


def ca_visible(n):
	"""Skinul spune cate randuri de CAID se vad pe pagina 4 (CaSys,<n>,<vazute>)."""
	try:
		n = int(n)
		if 1 <= n <= ROW_LIMIT:
			_ca_view["vis"] = n
	except Exception:
		pass


def ca_reset():
	_ca_view["top"] = 0


def ca_scroll(r, d):
	"""Sus / jos pe pagina 4: lista CAID-urilor se deruleaza cu un rand. True daca s-a miscat."""
	n = len(ca_entries(r))
	v = _ca_view["vis"]
	top = max(0, min(_ca_view["top"] + d, max(0, n - v)))
	if top == _ca_view["top"]:
		return False
	_ca_view["top"] = top
	return True


def ca_entry(r, n):
	"""Randul vazut n (1..) al listei CAID, dupa derulare, sau None."""
	rows = ca_entries(r)
	v = _ca_view["vis"]
	top = max(0, min(_ca_view["top"], max(0, len(rows) - v)))
	_ca_view["top"] = top
	k = top + n - 1
	return rows[k] if 0 <= k < len(rows) and n <= v else None


def ca_ids_text(entry):
	caid, pid = entry
	return join([u"CAID %04X" % caid, (u"%s: %d" % (tr("ecm_pid"), pid)) if pid > 0 else tr("param_list")])


def ca_count_text(r):
	"""„Număr CAID-uri: 11”, cu „1-7 / 11” cand lista se deruleaza."""
	rows = ca_entries(r)
	if not rows:
		return u""
	t = u"%s: %d" % (tr("cnt_caids"), len(rows))
	v = _ca_view["vis"]
	if len(rows) > v:
		top = max(0, min(_ca_view["top"], len(rows) - v))
		t = join([t, u"%d-%d / %d" % (top + 1, top + v, len(rows))])
	return t


def access_groups(r):
	"""[(nume, [caid...])] ale canalului, in ordinea CAID-urilor."""
	return group_caids(r.caids())


def access_short(r, without=-1, max_chars=0):
	"""Accesul pe scurt, ca in bara: „Seca Mediaguard / Viaccess” (cel mult doua sisteme), „CRIPTAT”/„FTA” cand nu
	sunt CAID-uri, nimic cat nu se stie. `without` = CAID-ul decriptat acum: sistemul lui se scoate din text.
	`max_chars` > 0: numai sistemele care incap impreuna in atatea litere (celelalte se sar, nu se taie pe jumatate)."""
	k = r.kind()
	if k not in DVB_KINDS_ALL:
		return u""
	caids = r.caids()
	if caids:
		skip = (caid_name(without) or (u"0x%04X" % without)) if without > 0 else None
		names = [g[0] for g in group_caids(caids) if g[0] != skip]
		if max_chars > 0:
			ales = []
			for n in names:
				if len(ales) < 2 and len(u" / ".join(ales + [n])) <= max_chars:
					ales.append(n)
			return u" / ".join(ales)
		return u" / ".join(names[:2])
	acces = r.acces()
	if acces == "criptat":
		return tr("encrypted")
	if acces == "fta":
		return tr("fta_short")
	return u""


def access_head(r):
	"""Capul paginii accesului: sistemul prin care se decripteaza acum primul, apoi celelalte, cel mult doua nume si
	„+N” pentru restul („Nagravision / Irdeto +2”)."""
	if r.kind() not in DVB_KINDS_ALL:
		return u""
	caids = r.caids()
	if not caids:
		return access_short(r)
	names = [g[0] for g in group_caids(caids)]
	act = ecm_active(r)
	if act > 0:
		a = caid_name(act) or (u"0x%04X" % act)
		if a in names:
			names.remove(a)
		names.insert(0, a)
	text = u" / ".join(names[:2])
	if len(names) > 2:
		text = u"%s +%d" % (text, len(names) - 2)
	return text


def active_system_short(r):
	"""Sistemul prin care se decripteaza acum, cu numele scurt din bara (grupul CAID-ului), sau gol."""
	caid = ecm_active(r)
	if caid <= 0:
		return u""
	return caid_name(caid) or (u"0x%04X" % caid)


# ---------------------------------------------------------------- pagina 6: procesorul si reteaua

CPUFREQ_DIR = "/sys/devices/system/cpu/cpu0/cpufreq/"
NET_ROUTE = "/proc/net/route"
NET_FIB = "/proc/net/fib_trie"
SYS_NET = "/sys/class/net/"


def _read_int(path):
	try:
		return int((read_small(path, 64) or u"").strip())
	except Exception:
		return -1


def cpu_freq():
	"""(frecventa de acum, plafonul) in kHz din cpufreq (numai citire), sau None. Tinut 1,5 s."""
	def fn():
		cur = _read_int(CPUFREQ_DIR + "scaling_cur_freq")
		if cur <= 0:
			cur = _read_int(CPUFREQ_DIR + "cpuinfo_cur_freq")
		mx = _read_int(CPUFREQ_DIR + "scaling_max_freq")
		if mx <= 0:
			mx = _read_int(CPUFREQ_DIR + "cpuinfo_max_freq")
		return (cur, mx) if cur > 0 else None
	return _memo_file("cpufreq", 1.5, fn)


def freq_text(khz):
	"""600000 -> „600 MHz”; 1200000 -> „1,2 GHz”."""
	mhz = int(khz) // 1000
	if mhz >= 1000:
		return u"%s GHz" % fmt_dec(mhz / 1000.0, 1)
	return u"%d MHz" % mhz


def cpu_freq_text():
	"""„600 MHz · maxim 1,2 GHz”, sau gol pe placile fara cpufreq."""
	f = cpu_freq()
	if not f:
		return u""
	cur, mx = f
	return join([freq_text(cur), (u"%s %s" % (tr("cpu_max"), freq_text(mx))) if mx > 0 else u""])


def _hex_ipv4(h):
	"""Adresa IPv4 din /proc/net/route (8 cifre hex, ordinea octetilor a nucleului: 0100000A = 10.0.0.1)."""
	try:
		v = int(h, 16)
		return (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF)
	except Exception:
		return None


def _local_ipv4():
	"""Adresele IPv4 ale receptorului, din /proc/net/fib_trie (randurile „/32 host LOCAL”), fara bucla locala."""
	text = read_small(NET_FIB, 65536) or u""
	last = None
	out = []
	for line in text.splitlines():
		t = line.strip()
		if t.startswith(u"|--") or t.startswith(u"+--"):
			last = t[3:].strip().split(u"/")[0].split()[0] if t[3:].strip() else None
		elif u"/32 host LOCAL" in t and last and not last.startswith(u"127.") and last not in out:
			out.append(last)
	return out


def _ip_tuple(s):
	try:
		p = tuple(int(x) for x in u(s).split(u"."))
		return p if len(p) == 4 else None
	except Exception:
		return None


def net_default():
	"""(interfata, adresa IPv4, e Wi-Fi) pentru ruta implicita, citite din /proc (fara nimic trimis in retea si fara
	socluri): interfata din /proc/net/route, adresa ei din /proc/net/fib_trie (cea din reteaua interfetei).
	("", "", False) fara retea. Tinut 5 s."""
	def fn():
		text = read_small(NET_ROUTE, 16384) or u""
		iface = u""
		retele = []
		for line in text.splitlines()[1:]:
			p = line.split()
			try:
				if len(p) < 8 or not int(p[3], 16) & 1:
					continue
				if p[1] == u"00000000" and not iface:
					iface = p[0]
				elif p[1] != u"00000000":
					retele.append((p[0], _hex_ipv4(p[1]), _hex_ipv4(p[7])))
			except Exception:
				continue
		if not iface or u"/" in iface or iface.startswith(u"."):
			return (u"", u"", False)
		ip = u""
		locale = _local_ipv4()
		for nume, net, mask in retele:
			if nume != iface or net is None or mask is None:
				continue
			for a in locale:
				t = _ip_tuple(a)
				if t is not None and all((t[k] & mask[k]) == net[k] for k in range(4)):
					ip = a
					break
			if ip:
				break
		wifi = os.path.exists(SYS_NET + iface + "/wireless") or os.path.exists(SYS_NET + iface + "/phy80211")
		return (iface, ip, wifi)
	return _memo_file("netdef", 5.0, fn) or (u"", u"", False)


def internet_state():
	"""True / False / None (nu s-a aflat inca). Convertorul nu intreaba reteaua: raspunsul il da modulul imaginii
	Components/HdsStareRetea.py (o proba pe firul lui, rar, numai cand se cere); pe celelalte imagini None. Fara ruta
	implicita raspunsul e False."""
	if not net_default()[0]:
		return False
	try:
		from Components import HdsStareRetea
	except ImportError:
		return None
	try:
		return HdsStareRetea.internet()
	except Exception as e:
		log_once("internet", e)
		return None


def net_link_text():
	"""„Cablu” / „Wi-Fi” / „fără rețea”."""
	iface, ip, wifi = net_default()
	if not iface:
		return tr("net_none")
	return tr("net_wifi") if wifi else tr("net_cable")


def net_internet_text():
	"""„da” / „nu” / „se verifică” pe imaginea HDSatelit; pe celelalte „nu se știe” (nu au proba)."""
	v = internet_state()
	if v is None:
		try:
			from Components import HdsStareRetea  # noqa: F401
			return tr("net_checking")
		except ImportError:
			return tr("unknown")
	return tr("yes") if v else tr("no")


# ---------------------------------------------------------------- latimea textului si scurtarea cu „…”
# eLabel taie textul unui rand (noWrap) la marginea widgetului, in mijlocul literei si fara semn. Widgeturile cu
# Fit=<font>:<marime>:<latime> in argumentul convertorului primesc textul scurtat dupa latimea lui in pixeli, cu „…”.
# FIT_TABLES[(font, marime)]: avansul fiecarei litere din FIT_CHARS, in pixeli intregi, scris ca chr(48 + latime)
# („/” = litera pe care fontul nu o are); facute din fisierele .ttf ale skinului (HDSatelit/fonts) cu FreeType, pentru
# perechile folosite in skin. Alta marime a aceluiasi font: tabelul cel mai apropiat, marit sau micsorat. O litera din
# afara tabelului se socoteste cat cea mai lata litera a fontului, deci textul iese mai scurt, niciodata taiat. Marirea
# fonturilor din setarile imaginii (skin.getFontScalePercent, numai pe imaginea HDSatelit) se tine in seama.

FIT_RANGES = ((0x20, 0x7E), (0xA0, 0x17F), (0x218, 0x21B), (0x386, 0x3CE), (0x400, 0x45F), (0x2011, 0x2014),
	(0x2018, 0x201E), (0x2022, 0x2022), (0x2026, 0x2026))
ELLIPSIS = u"\u2026"
FIT_TABLES = {
	('HdsBold', 38): (
		'::AIFQL9<<EF:<:?FFFFFFFFFF::FFFARIIHLEDLM<;HESNNGNHEELHTHFF=?=F@<FHCHF>EH;;F;THGHH@C?HDOEDB?E?F::FFF'
		'FECGP>EF<PC@F>><HI:8>>ENOOAIIIIIISHEEEE<<<<LNNNNNNFNLLLLFGIFFFFFFRCFFFF;;;;GHGGGGGFGHHHHDHDIFIFIFHCH'
		'CHCHCLHLHEFEFEFEFEFLELELELEMHMH<;<;<;<;<;GE;;HFFE;E;E;E<E;NHNHNHKNHNGNGNGTUH@H@H@ECECECECE?E?E?LHLHL'
		'HLHLHLHTOFDFFBFBFB=ECE?I:IP?/P/MP>IIEHEFMN<HHSNENLG/FEFOHPN<FHDH>HHHEGDCHG>FFHFBGJGCHCHMFNO>HGHOEEME'
		'IE<<;UUMHNHLIHIELERGNNHLSMNLGHEHOHMKXYKQHIXIFGGAHFODJJFGNIGHHCCDMEIHSTKOGCPFFFHACC;;;QRHFJDI//CV77:7'
		'??B>O'
	),
	('HdsCond', 33): (
		'78=BAID7::@A8:8<AAAAAAAAAA88AAA=JBCBE@?EE98B?KFFAFB@@EBKA@@;<;A>9@B>B@:@B88@8KBABB<>;B?G??=<@<A78AAC'
		'A@?BK;@A:K@=A;;9BC87;;@IJI=BBBBBBIB@@@@9999EFFFFFFAFEEEE@AB@@@@@@I>@@@@8888ABAAAAAABBBBB?B?B@B@B@B>B'
		'>B>B>EBEB@@@@@@@@@@E@E@E@E@EBEB9898989898A@88B@@?8?8?8?9?8FBFBFBDFBFAFAFAJKB<B<B<@>@>@>@>@;@;@;EBEBE'
		'BEBEBEBKG@?@@=@=@=9@>@;B8CH</H/EH:BC?A@@EF9BBKF@FEA/@@@HAHF9@B>B:BBB?A>>BB:@@B@>ACB>B=BF@FG:BABG@@E?'
		'B@998KLEBFAEBBC?D@IAFFBDKEFEAB@AHAFDNNDJBBNB@AA=A@F>CC@AFBABB>=?F?CBJJCGA>H@@@B=>>888HJB@C?B//AQ6686'
		'<<=<I'
	),
	('HdsRegular', 33): (
		'99=ECKH7::BC9;9<CCCCCCCCCC99CCC>NEEEHBAHH99DANIJDJDBBHDNCBC;<;C>9BD@DC;BD88A8ODDDD=@<D@JAA?<B<C99CCC'
		'CBACK<@C;KA>C;;9DF97;<@HIJ>EEEEEEMEBBBB9999HIJJJJJCJHHHHBDEBBBBBBL@CCCC8888DDDDDDDCDDDDDADAEBEBEBE@E'
		'@E@E@HDHDBCBCBCBCBCHBHBHBHBHDHD9898989898BA98DAAA8A8A8A9A8IDIDIDFIDJDJDJDOOD=D=D=B@B@B@B@B<B<B<HDHDH'
		'DHDHDHDNJBABC?C?C?;B@B<E9EK</K/GK;EEACBCHJ9DDNIBJHD/CBBJCJJ9BD@D;DDEAD@@DD;ABDB@DED@D@DHBIJ;DDDJBBHA'
		'EB999OPHDIDHEDEAGBLCIIDGNHJHDEBDJCHGRRGLEESEBDC>CCH@EEACHEDDD@@AHAEDMNGIC@KBCCD>@@888LMDAEAE//AQ6686'
		'<<=<J'
	),
	('HdsBold', 32): (
		'89>EBLH8::BB9:9<BBBBBBBBBB99BBB?MEEDGBAGH::DAMIIDIDBBHDNDCB;<;B>:CD@DB<BD99B9ODDDD>@=DAJBA?<B<B89BBB'
		'BB@CK<BB:K@>B<<:DE97<<BIJJ?EEEEEEMDBBBB::::GIIIIIIBIHHHHCDECCCCCCL@BBBB9999DDDDDDDBDDDDDADAECECECD@D'
		'@D@D@GDGDBBBBBBBBBBGBGBGBGBHDHD:9:9:9:9:9CB:9DBBA9A9A9A:A9IDIDIDGIDIDIDIDNOD>D>D>B@B@B@B@B=B=B=HDHDH'
		'DHDHDHDNJCACB?B?B?;B@B=E9EK=/K/HK<EEADBBHI:DDMIBIHD/CBCKDKI:CDAD<DDEADA@DC<BBDB@DFD@D@DHBIJ<DDDJBBIA'
		'EB:::OOIEIEHEDEAGBMDIIEGMHIHDDBEKDHGRRGLDERECCC?DBJAFFBCIEDDD@@AHBEDNNFJC@KBBBD?@@999LLDBFAE//@P6686'
		'==?<J'
	),
	('HdsCond', 28): (
		'67;@>EA688=>787;>>>>>>>>>>77>>>;F@@?B==BB77?=GCC?C?>=B?G>>=9;9><8>?<?>9=?77=7G????:<9?=D==;:=:>67>>@'
		'>=<?G9>>8G=;>998?@769:>EFE;@@@@@@E?====7777BCCCCCC>CBBBB>?@>>>>>>E<>>>>7777???????>?????=?=@>@>@>?<?'
		'<?<?<B?B?=>=>=>=>=>B=B=B=B=B?B?7777777777?=77?===7=7=7=8=7C?C?C?AC?C?C?C?FG?:?:?:><><><><=9=9=9B?B?B'
		'?B?B?B?GD>=>=;=;=;8><=9@7@D:/D/BD9@@=?==BC7??GC=CB?/>=>D>EC7>?<?9??@=?<<??9=>?><?@?<?;?C=CC9???C==B='
		'@>777GHB?C?B@?@=A=E?CC?AGBCB??=?D>BAIJAF??I@>?>;?>C<@@=>C@???<;=B=@?FF@D><E>>>?;<<777EF?=@=?//>L5575'
		'::;;E'
	),
	('HdsRegular', 28): (
		'77;B@GD688?@797:@@@@@@@@@@77@@@<IBBBD@>DE88A?IEFAFA??DAJ@@@9:9@<8@A=A@9?A77?7JAAAA;=:A>F?>=;?;@77@@@'
		'@?>@G:>@9G><@::8AB76::>EFF<BBBBBBHB@@@@8888DEFFFFF@FDDDD@AA@@@@@@H=@@@@7777AAAAAAA@AAAAA>A>B@B@B@B=B'
		'=B=B=DADA@@@@@@@@@@D?D?D?D?EAEA8787878787?>87A???7?7?7?7?7EAEAEACEAFAFAFAJKA;A;A;?=?=?=?=?:?:?:DADAD'
		'ADADADAJF@>@@=@=@=9?=?:B7BG:/G/DG:BB?@@@EF8AAIE?FDA/@?@F@FF8@A=A:AAB>A==AA:??A?=ABA>A=AD?EF:AAAF@@E?'
		'B?888JKEAEADBAB?C@H@EEADIEFDAB?AF@ECMMCHBBMB@A@<@@E>BB>@EBAAA==>D?BAIICFA>G@@@A<>=777HIA>B>A//>L5575'
		'::;;F'
	),
}
_fit_memo = {"idx": None, "maxim": {}, "scala": None}


def _fit_index():
	idx = _fit_memo["idx"]
	if idx is None:
		idx = {}
		k = 0
		for a, b in FIT_RANGES:
			for c in range(a, b + 1):
				idx[c] = k
				k += 1
		_fit_memo["idx"] = idx
	return idx


def _font_scale():
	"""Procentul de marire a fonturilor din setarile imaginii (100 pe celelalte imagini)."""
	s = _fit_memo["scala"]
	if s is None:
		try:
			import skin
			fn = getattr(skin, "getFontScalePercent", None)
			s = fn if callable(fn) else False
		except Exception:
			s = False
		_fit_memo["scala"] = s
	if s is False:
		return 100
	try:
		return int(s())
	except Exception:
		return 100


def _fit_table(font, size):
	"""(tabelul, factorul) pentru fontul `font` de marimea `size`, sau (None, 1.0) cand fontul nu are tabel."""
	best = None
	for (f, s), tab in FIT_TABLES.items():
		if f != font:
			continue
		if best is None or abs(s - size) < abs(best[0] - size):
			best = (s, tab)
	if best is None:
		return None, 1.0
	return best[1], float(size) / best[0]


def text_width(text, font, size):
	"""Latimea in pixeli a textului pe un rand, cu fontul skinului `font` de marimea `size`; None fara tabel."""
	size = max(1, int(size) * _font_scale() // 100)
	tab, k = _fit_table(font, size)
	if tab is None:
		return None
	idx = _fit_index()
	maxim = _fit_memo["maxim"].get(id(tab))
	if maxim is None:
		maxim = max(ord(c) - 48 for c in tab if c != u"/")
		_fit_memo["maxim"][id(tab)] = maxim
	w = 0
	for c in u(text):
		i = idx.get(ord(c))
		if i is None or tab[i] == u"/":
			w += maxim
		else:
			w += ord(tab[i]) - 48
	return w * k


def fit(text, font, size, width):
	"""Textul scurtat cu „…” ca sa incapa pe un rand in `width` pixeli; neschimbat cand incape sau fara tabel.
	Se lasa o margine (2 % din latime, cel putin 4 px) pentru rotunjirile desenarii."""
	text = u(text)
	if not text or u"\n" in text:
		return text
	try:
		width = int(width)
		loc = width - max(4, width // 50)
		w = text_width(text, font, size)
		if w is None or w <= loc:
			return text
		loc -= text_width(ELLIPSIS, font, size)
		lo, hi = 0, len(text)
		while lo < hi:
			mid = (lo + hi + 1) // 2
			if text_width(text[:mid], font, size) <= loc:
				lo = mid
			else:
				hi = mid - 1
		cut = text[:lo].rstrip(u" ,;:-\u00b7\u2013")
		return (cut + ELLIPSIS) if cut else ELLIPSIS
	except Exception as e:
		log_once("fit", e)
		return text


def parse_fit(tokens):
	"""(font, marime, latime) din bucata `Fit=HdsBold:38:852` a argumentului, sau None."""
	for tk in tokens:
		tk = str(tk).strip()
		if not tk.startswith("Fit="):
			continue
		p = tk[4:].split(":")
		try:
			return (p[0], int(p[1]), int(p[2]))
		except Exception:
			return None
	return None
