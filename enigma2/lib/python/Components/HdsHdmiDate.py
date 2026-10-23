# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Starea iesirii HDMI, citita din fisierele driverului si scrisa pe intelesul oricui (ecranul Informatii HDMI,
Screens/HdsHdmiInfo.py). Doar in imaginea HDSatelit.

Sursele (toate optionale, fiecare camp poate lipsi pe alt receptor; atunci se scrie „necunoscut"):
  /proc/msp/hdmi0       starea driverului HDMI HiSilicon (perechi „Cheie : valoare", doua pe rand, pe sectiuni)
  /proc/msp/hdmi0_vo    imaginea trimisa (doua coloane despartite de „|": atributele iesirii | AVI InfoFrame)
  /proc/msp/hdmi0_ao    sunetul trimis (la fel, doua coloane)
  /proc/msp/hdmi0_sink  ce accepta televizorul (EDID: octetii bruti si ce a inteles driverul din ei)
  /proc/msp/disp0, disp1  afisajele (cel legat la HDMI are „Interface :HDMI0")
  /proc/stb/video/*, /proc/stb/vmpeg/0/*, /proc/stb/audio/*  fisierele Enigma2 (xres/yres in hexazecimal)

Fara importuri din enigma: se testeaza pe PC cu datele salvate de pe receptor (teste/test_hdmi_info.py).
Toate caile pornesc de la `radacina` ('/' pe receptor, alt dosar la probe). Nicio functie de aici nu scrie nimic
si niciuna nu arunca exceptii spre ecran: ce nu se poate citi sau intelege ramane None si se afiseaza „necunoscut".
"""
import os
import re

NECUNOSCUT = 'necunoscut'
TITLU = 'Informații HDMI'

# fisierele care se citesc la fiecare improspatare
HDMI0 = 'proc/msp/hdmi0'
HDMI0_VO = 'proc/msp/hdmi0_vo'
HDMI0_AO = 'proc/msp/hdmi0_ao'
HDMI0_SINK = 'proc/msp/hdmi0_sink'
DISP = ('proc/msp/disp1', 'proc/msp/disp0')
STB_VIDEO = 'proc/stb/video'
STB_VMPEG = 'proc/stb/vmpeg/0'
STB_AUDIO = 'proc/stb/audio'
STB_HDMI = 'proc/stb/hdmi'
EDID_BINAR = 'proc/stb/hdmi/raw_edid'      # pe alte receptoare (EDID binar); pe HiSilicon nu exista

# pagina pentru cunoscatori (textul brut, cu tasta albastra): (titlu, cale, dosar)
PAGINI_BRUTE = (
	('Starea driverului HDMI', HDMI0, False),
	('Imaginea trimisă', HDMI0_VO, False),
	('Sunetul trimis', HDMI0_AO, False),
	('Televizorul (EDID)', HDMI0_SINK, False),
	('Afișajul 1', 'proc/msp/disp1', False),
	('Afișajul 0', 'proc/msp/disp0', False),
	('Setările video Enigma2', STB_VIDEO, True),
	('Decodorul video', STB_VMPEG, True),
	('Setările de sunet Enigma2', STB_AUDIO, True),
	('Ieșirea HDMI Enigma2', STB_HDMI, True),
)

MAX_OCTETI = 65536          # un fisier din /proc mai mare decat atat nu e al nostru; nu citim mai mult

# tonurile valorilor (culoarea o alege ecranul)
NORMAL, BUN, ATENTIE, RAU, STINS = 'normal', 'bun', 'atentie', 'rau', 'stins'

# producatorii dupa codul EDID (cele trei litere din octetii 8-9); un cod necunoscut se arata ca atare
PRODUCATORI = {
	'GSM': 'LG', 'SAM': 'Samsung', 'SNY': 'Sony', 'PHL': 'Philips', 'MEI': 'Panasonic', 'SHP': 'Sharp',
	'TSB': 'Toshiba', 'VIZ': 'Vizio', 'HEC': 'Hisense', 'DEL': 'Dell', 'ACR': 'Acer', 'AUS': 'ASUS',
	'BNQ': 'BenQ', 'HWP': 'HP', 'LEN': 'Lenovo', 'VSC': 'ViewSonic', 'ENC': 'EIZO', 'NEC': 'NEC',
	'IVM': 'iiyama', 'AOC': 'AOC', 'ONK': 'Onkyo', 'YMH': 'Yamaha', 'DON': 'Denon', 'PIO': 'Pioneer',
}

# sunetul: codul driverului -> numele obisnuit
FORMATE_SUNET = {
	'L-PCM': 'PCM', 'LPCM': 'PCM', 'PCM': 'PCM', 'AC3': 'AC3', 'EAC3': 'E-AC3', 'E-AC3': 'E-AC3', 'DDP': 'E-AC3',
	'DTS': 'DTS', 'DTS-HD': 'DTS-HD', 'DTSHD': 'DTS-HD', 'MAT': 'TrueHD', 'MLP': 'TrueHD', 'AAC': 'AAC',
	'MP3': 'MP3', 'MPEG1': 'MPEG', 'MPEG2': 'MPEG', 'WMA': 'WMA', 'DST': 'DST', 'ATRAC': 'ATRAC',
	'ONE_BIT': 'DSD', 'DRA': 'DRA',
}

# inaltimea -> latimea obisnuita, pentru modurile scrise doar cu inaltimea (1080P_60, 720p50, pal)
LATIME = {2160: 3840, 1080: 1920, 720: 1280, 576: 720, 480: 720}


# ---------------------------------------------------------------- citirea fisierelor

def cale(radacina, relativ):
	return os.path.join(radacina or '/', relativ)


def citeste_text(cale_fisier):
	"""Continutul unui fisier text (cel mult MAX_OCTETI), sau None daca lipseste ori nu se poate citi."""
	try:
		with open(cale_fisier, 'rb') as f:
			date = f.read(MAX_OCTETI)
	except Exception:
		return None
	try:
		return date.decode('utf-8', 'replace')
	except Exception:
		return None


def citeste_binar(cale_fisier):
	try:
		with open(cale_fisier, 'rb') as f:
			return f.read(MAX_OCTETI)
	except Exception:
		return None


def citeste_dosar(cale_dosar, doar=None):
	"""{nume: valoare fara spatii la capete} pentru fisierele dintr-un dosar /proc/stb/... Fisierele *_apply nu se
	citesc (pe unele receptoare scrierea sau chiar citirea lor declanseaza ceva). `doar` = numele dorite."""
	rez = {}
	try:
		nume = sorted(os.listdir(cale_dosar))
	except Exception:
		return rez
	for n in nume:
		if n.endswith('_apply') or (doar is not None and n not in doar):
			continue
		p = os.path.join(cale_dosar, n)
		if not os.path.isfile(p):
			continue
		t = citeste_text(p)
		if t is not None:
			rez[n] = t.strip()
	return rez


# ---------------------------------------------------------------- perechile „Cheie : valoare"

_RX_ANTET = re.compile(r'^\s*-{3,}')
_RX_SEPARATOR = re.compile(r'\s{2,}')


def _norm(text):
	return re.sub(r'\s+', '', text or '').lower()


def _nume_antet(text):
	"""'---- VideoAttr ----- AVIIfno ---' -> ['VideoAttr', 'AVIIfno']"""
	return [t.strip() for t in re.split(r'-{3,}', text) if t.strip()]


def perechi_din_rand(rand):
	"""Perechile dintr-un rand cu una sau mai multe perechi despartite de cel putin doua spatii. Cheia poate avea
	spatiu inainte de „:" („HDMIEnable     : YES") sau nu („PreformatInTime: 2872438"); valoarea poate contine
	„:" („16:9") si spatii simple („OPEN START"). Ce nu e pereche (randuri de octeti) se sare."""
	rez = []
	cheie = None
	cuDouaPuncte = False       # cheia in asteptare avea deja „:" (valoarea e urmatoarea bucata)
	for bucata in _RX_SEPARATOR.split(rand.strip()):
		if not bucata:
			continue
		if bucata.startswith(':'):
			if cheie is not None and not cuDouaPuncte:
				rez.append((cheie, bucata[1:].strip()))
			elif cheie is not None:
				rez.append((cheie, ''))
			cheie, cuDouaPuncte = None, False
			continue
		if ':' in bucata:
			if cheie is not None and cuDouaPuncte:
				rez.append((cheie, ''))
			k, v = bucata.split(':', 1)
			k, v = k.strip(), v.strip()
			cheie, cuDouaPuncte = None, False
			if not k:
				continue
			if v:
				rez.append((k, v))
			else:
				cheie, cuDouaPuncte = k, True
			continue
		if cheie is not None and cuDouaPuncte:
			rez.append((cheie, bucata.strip()))
			cheie, cuDouaPuncte = None, False
		else:
			cheie, cuDouaPuncte = bucata.strip(), False
	if cheie is not None and cuDouaPuncte:
		rez.append((cheie, ''))
	return rez


class Perechi(object):
	"""Perechile unui fisier, in ordine, cu sectiunea fiecareia. Aceeasi cheie apare in mai multe sectiuni
	(HDCPEnable in APPAttr si SWStatus, TMDSMode in SWStatus si HWStatus), deci cautarea merge pe sectiuni."""

	def __init__(self, text, doua_coloane=False, una_pe_rand=False):
		self.intrari = []          # (sectiune normalizata, cheie normalizata, cheie, valoare)
		if not text:
			return
		stanga = dreapta = ''
		for rand in text.splitlines():
			if not rand.strip():
				continue
			if doua_coloane and '|' in rand:
				parti = [(rand.split('|', 1)[0], 'stanga'), (rand.split('|', 1)[1], 'dreapta')]
			else:
				parti = [(rand, 'tot')]
			for parte, loc in parti:
				if _RX_ANTET.match(parte):
					nume = _nume_antet(parte)
					if not nume:
						continue
					if loc == 'stanga':
						stanga = nume[0]
					elif loc == 'dreapta':
						dreapta = nume[0]
					else:
						stanga = nume[0]
						dreapta = nume[1] if len(nume) > 1 else nume[0]
					continue
				sectiune = dreapta if loc == 'dreapta' else stanga
				if una_pe_rand:
					if ':' not in parte:
						continue
					k, v = parte.split(':', 1)
					perechi = [(k.strip(), v.strip())] if k.strip() else []
				else:
					perechi = perechi_din_rand(parte)
				for k, v in perechi:
					self.intrari.append((_norm(sectiune), _norm(k), k, v))

	def __bool__(self):
		return bool(self.intrari)

	__nonzero__ = __bool__

	def val(self, cheie, *sectiuni):
		"""Valoarea cheii din prima sectiune data care o are; altfel prima aparitie oriunde; altfel None."""
		c = _norm(cheie)
		for s in sectiuni:
			ns = _norm(s)
			for sec, k, _k, v in self.intrari:
				if k == c and sec == ns:
					return v
		for sec, k, _k, v in self.intrari:
			if k == c:
				return v
		return None

	def din_sectiune(self, sectiune):
		ns = _norm(sectiune)
		return [(k, v) for sec, _n, k, v in self.intrari if sec == ns]


# ---------------------------------------------------------------- bucatile speciale din hdmi0 si hdmi0_sink

def evenimente(text):
	"""Tabelul „CNT|ErrTotal|HPD|UnHPD|..." cu randul „WR:" (sau „RD:") -> {'HPD': 2, 'UnHPD': 1, ...}."""
	rez = {}
	if not text:
		return rez
	randuri = text.splitlines()
	for i, rand in enumerate(randuri):
		if not rand.strip().upper().startswith('CNT|'):
			continue
		antet = [t.strip() for t in rand.strip().split('|')]
		valori = None
		for urm in randuri[i + 1:i + 4]:
			u = urm.strip().upper()
			if u.startswith('WR:') or (valori is None and u.startswith('RD:')):
				valori = [t.strip() for t in urm.strip().split('|')]
				if u.startswith('WR:'):
					break
		if valori is None:
			return rez
		for k, v in zip(antet[1:], valori[1:]):
			try:
				rez[k] = int(v)
			except ValueError:
				pass
		return rez
	return rez


def edid_din_text(text):
	"""Octetii EDID din sectiunea EDIDRawData a lui hdmi0_sink („/*00H:*/ 0x00,0xff,..."), sau b''."""
	if not text:
		return b''
	octeti = []
	inauntru = False
	for rand in text.splitlines():
		if _RX_ANTET.match(rand):
			nume = _norm(' '.join(_nume_antet(rand)))
			if inauntru and nume != 'edidrawdata':
				break
			inauntru = nume == 'edidrawdata'
			continue
		if inauntru:
			octeti.extend(int(h, 16) for h in re.findall(r'0x([0-9a-fA-F]{2})', rand))
	return bytes(bytearray(octeti[:512]))


def decodeaza_edid(date):
	"""Din primul bloc EDID: producatorul (cele trei litere), anul, numele televizorului (descriptorul 0xFC).
	{} daca octetii nu sunt un EDID."""
	rez = {}
	try:
		b = bytearray(date or b'')
		if len(b) < 128 or bytes(b[0:8]) != b'\x00\xff\xff\xff\xff\xff\xff\x00':
			return rez
		v = (b[8] << 8) | b[9]
		litere = ''.join(chr(((v >> s) & 31) + 64) for s in (10, 5, 0))
		if litere.isalpha() and litere.isupper():
			rez['producator'] = litere
		rez['cod_produs'] = b[10] | (b[11] << 8)
		if 0 < b[17] < 0xFF:
			rez['an'] = 1990 + b[17]
		for d in (54, 72, 90, 108):
			if b[d] == 0 and b[d + 1] == 0 and b[d + 3] == 0xFC:
				nume = bytes(b[d + 5:d + 18]).split(b'\x0a')[0]
				nume = ''.join(ch if 32 <= ord(ch) < 127 else ' ' for ch in nume.decode('latin-1')).strip()
				if nume:
					rez['nume'] = nume
				break
	except Exception:
		return {}
	return rez


def moduri_din_formatcap(text):
	"""Modurile din sectiunea FormatCap a lui hdmi0_sink -> lista de (latime, inaltime, 'p'|'i', frecventa),
	fara dubluri, in ordinea din fisier. Modurile de calculator (640x480_60, V800X600_60) se sar."""
	if not text:
		return []
	rez = []
	inauntru = False
	for rand in text.splitlines():
		if _RX_ANTET.match(rand):
			inauntru = _norm(' '.join(_nume_antet(rand))) == 'formatcap'
			continue
		if not inauntru:
			continue
		# intrarile au latime fixa, deci uneori le desparte un singur spatiu („4096X2160P60 256:135 720P_60 16:9");
		# fiecare cuvant se incearca singur, proportiile („16:9") nu sunt moduri
		for cuvant in rand.split():
			m = mod_tv(cuvant)
			if m and m not in rez:
				rez.append(m)
	return rez


def mod_tv(text):
	"""Un mod scris de driver sau de Enigma2 -> (latime, inaltime, 'p'|'i', frecventa) sau None.
	3840X2160P60, 1080P_60, 1080i_50, 720p50, 2160p, 1080i, pal, ntsc, 576p"""
	t = (text or '').strip()
	if not t:
		return None
	tl = t.lower()
	if tl == 'pal':
		return (720, 576, 'i', 50)
	if tl == 'ntsc':
		return (720, 480, 'i', 60)
	m = re.match(r'^(\d{3,4})x(\d{3,4})([pi])(\d{2,3})$', tl)
	if m:
		return (int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4)))
	m = re.match(r'^(2160|1080|720|576|480)([pi])_?(\d{2,3})?$', tl)
	if m:
		h = int(m.group(1))
		if m.group(3):
			f = int(m.group(3))
		else:
			f = 50 if h == 576 else 60        # Enigma2: 720p, 1080i, 2160p fara frecventa = 60 Hz
		return (LATIME[h], h, m.group(2), f)
	return None


def blocuri_sunet(perechi_sink):
	"""Formatele de sunet ale televizorului (sectiunea AudioCap, blocuri „NO.0:", „NO.1:") ->
	[{'format': 'PCM', 'canale': 2, 'frecvente': [32000, ...]}, ...]"""
	rez = []
	if not perechi_sink:
		return rez
	bloc = None
	for k, v in perechi_sink.din_sectiune('AudioCap'):
		if re.match(r'^NO\.\d+$', k.strip(), re.I):
			bloc = {}
			rez.append(bloc)
			continue
		if bloc is None:
			bloc = {}
			rez.append(bloc)
		kn = _norm(k)
		if kn == 'codetype':
			bloc['format'] = FORMATE_SUNET.get(v.strip().upper(), v.strip())
		elif kn == 'maxchannelnum':
			bloc['canale'] = _intreg(v)
		elif kn.startswith('samplerate'):
			bloc['frecvente'] = [int(x) for x in re.findall(r'\d+', v)]
	return [b for b in rez if b.get('format')]


# ---------------------------------------------------------------- starea, citita o data la 2 s

def _intreg(text, baza=10):
	try:
		return int(str(text).strip(), baza)
	except Exception:
		m = re.match(r'^\s*(\d+)', str(text or ''))
		return int(m.group(1)) if m and baza == 10 else None


def _da(v):
	"""YES/NO, Y/N, TRUE/FALSE, 1/0, ON/OFF -> True/False; altceva -> None"""
	if v is None:
		return None
	t = v.strip().upper()
	if t in ('YES', 'Y', 'TRUE', '1', 'ON', 'ENABLE', 'ENABLED'):
		return True
	if t in ('NO', 'N', 'FALSE', '0', 'OFF', 'DISABLE', 'DISABLED'):
		return False
	return None


class Stare(object):
	"""Tot ce s-a citit la o improspatare. Campurile lipsa raman goale; `gasit` spune daca a venit ceva."""

	def __init__(self):
		self.hdmi0 = Perechi(None)
		self.vo = Perechi(None)
		self.ao = Perechi(None)
		self.sink = Perechi(None)
		self.disp = Perechi(None)
		self.evenimente = {}
		self.edid = {}
		self.moduri = []
		self.sunet_tv = []
		self.video = {}
		self.vmpeg = {}
		self.audio = {}
		self.texte = {}            # cale relativa -> text brut (pentru pagina bruta)
		self.cheie_conectare = None

	@property
	def gasit(self):
		return bool(self.hdmi0 or self.vo or self.ao or self.sink or self.disp or any(self.video.values())
			or any(self.vmpeg.values()))


def _cheie_conectare(hdmi0, ev):
	"""Se schimba doar cand se conecteaza sau se deconecteaza cablul ori televizorul; atunci se reciteste EDID."""
	return (hdmi0.val('HotPlug', 'HWStatus'), hdmi0.val('Rsen', 'HWStatus'), ev.get('HPD'), ev.get('UnHPD'),
		ev.get('RsenCon'), ev.get('RsenDis'), ev.get('EdidFail'))


def citeste(radacina='/', anterior=None, brut=False):
	"""Citeste starea HDMI de sub `radacina`. `anterior` = starea de la citirea trecuta: daca nu s-a conectat sau
	deconectat nimic intre timp, ce accepta televizorul (hdmi0_sink, cel mai lung fisier) nu se mai citeste.
	`brut` = citeste si dosarele /proc/stb intregi, pentru pagina bruta. Nu arunca exceptii."""
	s = Stare()
	try:
		t = citeste_text(cale(radacina, HDMI0))
		s.texte[HDMI0] = t
		s.hdmi0 = Perechi(t)
		s.evenimente = evenimente(t)
		s.cheie_conectare = _cheie_conectare(s.hdmi0, s.evenimente) if s.hdmi0 else None

		t = citeste_text(cale(radacina, HDMI0_VO))
		s.texte[HDMI0_VO] = t
		s.vo = Perechi(t, doua_coloane=True)
		t = citeste_text(cale(radacina, HDMI0_AO))
		s.texte[HDMI0_AO] = t
		s.ao = Perechi(t, doua_coloane=True)

		# (o citire trecuta care n-a gasit nimic nu se pastreaza: se reincearca la fiecare improspatare)
		if anterior is not None and anterior.sink and s.cheie_conectare is not None and anterior.cheie_conectare == s.cheie_conectare:
			s.sink, s.edid, s.moduri, s.sunet_tv = anterior.sink, anterior.edid, anterior.moduri, anterior.sunet_tv
			s.texte[HDMI0_SINK] = anterior.texte.get(HDMI0_SINK)
		else:
			t = citeste_text(cale(radacina, HDMI0_SINK))
			s.texte[HDMI0_SINK] = t
			s.sink = Perechi(t)
			if s.sink and _da(s.sink.val('CapIsValid', 'SWStatus')) is False:
				s.sink = Perechi(None)
			else:
				s.moduri = moduri_din_formatcap(t)
				s.sunet_tv = blocuri_sunet(s.sink)
			s.edid = decodeaza_edid(edid_din_text(t)) if s.sink else {}
			if not s.edid:
				s.edid = decodeaza_edid(citeste_binar(cale(radacina, EDID_BINAR)))

		# afisajul legat la HDMI (pe acest receptor disp1; disp0 e iesirea analogica)
		for i, rel in enumerate(DISP):
			t = citeste_text(cale(radacina, rel))
			s.texte[rel] = t
			p = Perechi(t, una_pe_rand=True)
			if p and ('HDMI' in (p.val('Interface') or '').upper() or (i == len(DISP) - 1 and not s.disp)):
				if not s.disp:
					s.disp = p
			if s.disp and not brut:
				break

		s.video = citeste_dosar(cale(radacina, STB_VIDEO), None if brut else ('videomode', 'videomode_preferred'))
		s.vmpeg = citeste_dosar(cale(radacina, STB_VMPEG), None if brut else ('xres', 'yres', 'progressive', 'framerate', 'gamma'))
		s.audio = citeste_dosar(cale(radacina, STB_AUDIO), None if brut else ('ac3', 'dts'))
		if brut:
			s.texte[STB_HDMI] = _text_dosar(citeste_dosar(cale(radacina, STB_HDMI)))
		if not s.moduri and s.video.get('videomode_preferred'):
			for tok in s.video['videomode_preferred'].split():
				m = mod_tv(tok)
				if m and m not in s.moduri:
					s.moduri.append(m)
	except Exception as e:
		print('[HdsHdmiDate] citire: %s' % e)
	return s


def _text_dosar(valori):
	if not valori:
		return None
	return '\n'.join('%s: %s' % (k, v) for k, v in sorted(valori.items()))


def pagini_brute(stare):
	"""[(titlu, cale absoluta pe receptor, text)] pentru pagina bruta; doar sursele care exista."""
	rez = []
	for titlu, rel, dosar in PAGINI_BRUTE:
		if dosar:
			valori = {STB_VIDEO: stare.video, STB_VMPEG: stare.vmpeg, STB_AUDIO: stare.audio}.get(rel)
			text = _text_dosar(valori) if valori is not None else stare.texte.get(rel)
		else:
			text = stare.texte.get(rel)
		if text and text.strip():
			rez.append((titlu, '/' + rel, text.strip('\n')))
	return rez


# ---------------------------------------------------------------- textele pe intelesul oricui

def _nr(x, zecimale=3):
	"""50.0 -> '50', 59.94 -> '59,94', 23.976 -> '23,976'"""
	t = ('%.*f' % (zecimale, x)).rstrip('0').rstrip('.')
	return t.replace('.', ',')


def text_da_nu(v):
	return {True: 'Da', False: 'Nu'}.get(v, NECUNOSCUT)


def text_spatiu_culoare(v):
	"""RGB444 / RGB -> RGB; YCbCr444 -> YCbCr 4:4:4; YCBCR422 -> YCbCr 4:2:2; YCbCr420 -> YCbCr 4:2:0"""
	if not v:
		return None
	t = v.strip().upper().replace('_', '').replace(' ', '')
	if t.startswith('RGB'):
		return 'RGB'
	m = re.match(r'^(?:YCBCR|YUV)(4)(4|2)(4|2|0)$', t)
	if m:
		return 'YCbCr %s:%s:%s' % m.groups()
	return v.strip()


def biti_culoare(vo_biti, adancime):
	"""'08 Bit' -> 8; DeepColorMode '24 Bit(OFF)' / '24' -> 8, 30 -> 10, 36 -> 12"""
	n = _intreg(vo_biti) if vo_biti else None
	if n in (8, 10, 12, 16):
		return n
	n = _intreg(adancime) if adancime else None
	if n in (24, 30, 36, 48):
		return n // 3
	if n in (8, 10, 12, 16):
		return n
	return None


def text_cadre(f):
	return None if f is None else _nr(f, 3)


def _rezolutie_iesire(s):
	"""(latime, inaltime, 'p'|'i', frecventa) pentru ce iese acum pe HDMI, din sursa cea mai sigura."""
	lat = inalt = bal = frecv = None
	vt = s.vo.val('VideoTiming', 'VideoAttr') or s.vo.val('CurrentFormat', 'AVIIfno')
	m = re.match(r'^\s*(\d{3,4})\s*[*xX]\s*(\d{3,4})\s*([pPiI])\s*(\d+(?:\.\d+)?)?', vt or '')
	if m:
		lat, inalt, bal = int(m.group(1)), int(m.group(2)), m.group(3).lower()
		frecv = float(m.group(4)) if m.group(4) else None
	if lat is None:
		h, v = _intreg(s.hdmi0.val('HactiveCnt')), _intreg(s.hdmi0.val('VactiveCnt'))
		if h and v:
			lat, inalt = h, v
	if bal is None:
		p = _da(s.hdmi0.val('Progressive'))
		bal = {True: 'p', False: 'i'}.get(p)
	if lat is not None and bal == 'i' and inalt in (240, 288, 540):
		inalt *= 2              # la intretesut driverul numara randurile unui camp
	if frecv is None:
		ceas = _intreg(s.vo.val('PixelClk', 'VideoAttr'))
		ht, vt2 = _intreg(s.hdmi0.val('HsyncTotal')), _intreg(s.hdmi0.val('VsyncTotal'))
		if ceas and ht and vt2:
			frecv = round(ceas * 1000.0 / (ht * vt2) * (2 if bal == 'i' else 1), 2)
	if lat is None or frecv is None or bal is None:
		m = mod_tv(s.video.get('videomode', ''))
		if m:
			lat = lat or m[0]
			inalt = inalt or m[1]
			bal = bal or m[2]
			frecv = frecv or float(m[3])
	return lat, inalt, bal, frecv


def text_mod(mod):
	"""'720p50' -> '720p, 50 Hz'; '1080i' -> '1080i, 60 Hz'; 'pal' -> '576i, 50 Hz'"""
	if not mod:
		return None
	m = mod_tv(mod)
	if not m:
		return mod.strip()
	return '%d%s, %d Hz' % (m[1], m[2], m[3])


def _frecvente(moduri, inaltime, baleiaj):
	f = sorted(set(m[3] for m in moduri if m[1] == inaltime and m[2] == baleiaj and m[0] < 4000))
	return (', '.join(str(x) for x in f) + ' Hz') if f else 'Nu'


def _text_canale(n):
	if not n:
		return None
	return {1: 'mono', 2: 'stereo', 6: '5.1', 8: '7.1'}.get(n, '%d canale' % n)


def _titlu(text):
	return ('titlu', text)


def _rand(eticheta, valoare, ton=None):
	if valoare is None or valoare == '':
		return ('valoare', eticheta, NECUNOSCUT, STINS)
	return ('valoare', eticheta, valoare, ton or NORMAL)


def coloane(s, ales_in_setari=None):
	"""Cele trei coloane ale ecranului: liste de ('titlu', text) si ('valoare', eticheta, valoare, ton).
	`ales_in_setari` = modul din Setari (config.av.hds_videomode), daca ecranul il stie."""
	try:
		return [_coloana_iesire(s, ales_in_setari), _coloana_legatura(s), _coloana_televizor(s)]
	except Exception as e:
		print('[HdsHdmiDate] coloane: %s' % e)
		return [[_titlu('Ieșire HDMI'), _rand('Stare', None)], [], []]


def _coloana_iesire(s, ales):
	c = []
	lat, inalt, bal, frecv = _rezolutie_iesire(s)
	c.append(_titlu('Ieșire HDMI'))
	c.append(_rand('Rezoluție', ('%d x %d' % (lat, inalt)) if lat and inalt else None))
	if frecv and bal == 'i':
		# 1080i50 = 50 de campuri pe secunda, adica 25 de cadre intregi
		cadre = '%s (%s câmpuri)' % (text_cadre(frecv / 2.0), text_cadre(frecv))
	else:
		cadre = text_cadre(frecv)
	c.append(_rand('Cadre pe secundă', cadre))
	c.append(_rand('Baleiaj', {'p': 'Progresiv', 'i': 'Întrețesut'}.get(bal)))
	ales = ales or s.video.get('videomode')
	ton = None
	m = mod_tv(ales or '')
	# doar rezolutia si baleiajul: frecventa (50/60 Hz) o schimba driverul singur dupa canal (videomode_50hz/60hz)
	if m and inalt and bal and (m[1] != inalt or m[2] != bal):
		ton = ATENTIE          # iesirea nu e ce s-a ales in setari
	c.append(_rand('Ales în setări', text_mod(ales), ton))
	tmds = (s.hdmi0.val('TMDSMode', 'HWStatus') or '').upper().replace(' ', '')
	mt = re.match(r'^HDMI(\d)\.?(\d)', tmds)
	if mt:
		tmds_text = 'HDMI %s.%s' % mt.groups()
	elif tmds.startswith('DVI'):
		tmds_text = 'DVI, fără sunet'
	else:
		tmds_text = None
	c.append(_rand('Semnal TMDS', tmds_text))
	ceas = _intreg(s.vo.val('PixelClk', 'VideoAttr'))
	c.append(_rand('Frecvența pixelilor', (_nr(ceas / 1000.0, 3) + ' MHz') if ceas else None))

	c.append(_titlu('Culoare'))
	c.append(_rand('Spațiu de culoare', text_spatiu_culoare(s.vo.val('OutColorSpace', 'VedioPath', 'VideoPath')
		or s.hdmi0.val('OutColorSpace', 'APPAttr'))))
	b = biti_culoare(s.vo.val('OutBitDepth', 'VedioPath', 'VideoPath'), s.vo.val('DeepColorMode', 'VedioPath', 'VideoPath')
		or s.hdmi0.val('DeepColorMode', 'APPAttr'))
	c.append(_rand('Adâncime de culoare', ('%d biți' % b) if b else None))
	q = (s.vo.val('OutQuantization', 'VedioPath', 'VideoPath') or '').upper()
	c.append(_rand('Niveluri', 'limitate (16-235)' if q.startswith('LIMIT') else ('complete (0-255)' if q.startswith('FULL') else None)))
	col = s.vo.val('Colorimetry', 'VideoAttr') or ''
	mc = re.search(r'BT\.?\s*(709|601|2020)', col.upper())
	c.append(_rand('Colorimetrie', ('BT.%s' % mc.group(1)) if mc else (col.strip() or None)))
	c.append(_rand('HDR acum', _text_hdr_acum(s)))

	c.append(_titlu('Imaginea decodată acum'))
	xr, yr = _intreg(s.vmpeg.get('xres'), 16), _intreg(s.vmpeg.get('yres'), 16)
	if xr == 0 or yr == 0:
		c.append(_rand('Rezoluția canalului', 'nicio imagine', STINS))
	else:
		c.append(_rand('Rezoluția canalului', ('%d x %d' % (xr, yr)) if xr and yr else None))
	p = _da(s.vmpeg.get('progressive'))
	c.append(_rand('Baleiaj', {True: 'Progresiv', False: 'Întrețesut'}.get(p)))
	fr = _intreg(s.vmpeg.get('framerate'))
	c.append(_rand('Cadre pe secundă', text_cadre(fr / 1000.0 if fr and fr > 1000 else fr) if fr else None))
	if xr != 0 and yr != 0:
		c.append(_rand('HDR în canal', text_gama(s.vmpeg.get('gamma'))))
	return c


# gama imaginii decodate, din /proc/stb/vmpeg/0/gamma (hexazecimal, ca in decoder.cpp): aceleasi valori ca evenimentul
# 17 al decodorului (0 gama traditionala SDR, 1 gama traditionala HDR, 2 SMPTE ST 2084 = HDR10, 3 HLG)
GAMA = {0: 'Nu (SDR)', 1: 'HDR', 2: 'HDR10', 3: 'HLG'}


def text_gama(v):
	return GAMA.get(_intreg(v, 16))


def _text_hdr_acum(s):
	t = (s.disp.val('ActualDispOutType') or s.vo.val('HdrEotfType', 'HDRAttr') or '').upper()
	mod = (s.vo.val('HdrMode', 'HDRAttr') or '').upper()
	if 'DOLBY' in t:
		return 'Dolby Vision'
	if 'HLG' in t:
		return 'HLG'
	if '2084' in t or 'HDR10' in t or t == 'HDR':
		return 'HDR10'
	if t.startswith('SDR') or mod == 'DISABLE':
		return 'Nu (SDR)'
	return None


def _coloana_legatura(s):
	c = []
	h = s.hdmi0
	c.append(_titlu('Legătură'))
	cablu = _da(h.val('HotPlug', 'HWStatus'))
	c.append(_rand('Cablu HDMI', {True: 'conectat', False: 'neconectat'}.get(cablu), BUN if cablu else RAU))
	tv = _da(h.val('Rsen', 'HWStatus'))
	c.append(_rand('Televizorul răspunde', text_da_nu(tv) if tv is not None else None, BUN if tv else ATENTIE))
	iesire = _da(h.val('PhyOutputEnable', 'HWStatus'))
	mut = _da(h.val('AvMute', 'HWStatus'))
	if iesire is None and mut is None:
		semnal = None
	elif iesire is False:
		semnal = ('Nu, ieșirea e oprită', RAU)
	elif mut:
		semnal = ('Nu, imaginea e oprită', RAU)
	else:
		semnal = ('Da', BUN)
	c.append(_rand('Semnal trimis', semnal[0] if semnal else None, semnal[1] if semnal else None))

	ev = s.evenimente
	c.append(_titlu('Evenimente de la pornire'))
	c.append(_rand('Conectări', str(ev['HPD']) if 'HPD' in ev else None))
	c.append(_rand('Deconectări', str(ev['UnHPD']) if 'UnHPD' in ev else None))
	if 'ErrTotal' in ev:
		n = ev['ErrTotal']
		detalii = []
		if ev.get('EdidFail'):
			detalii.append('EDID %d' % ev['EdidFail'])
		if ev.get('HdcpFail'):
			detalii.append('HDCP %d' % ev['HdcpFail'])
		text = str(n) + (' (%s)' % ', '.join(detalii) if detalii else '')
		c.append(_rand('Erori', text, ATENTIE if n else None))
	else:
		c.append(_rand('Erori', None))

	c.append(_titlu('Protecție la copiere (HDCP)'))
	activ = _da(h.val('HDCPEnable', 'SWStatus'))
	c.append(_rand('HDCP pornit', text_da_nu(activ) if activ is not None else None))
	versiune = (h.val('HDCPMode', 'SWStatus') or '').upper()
	mv = re.search(r'(\d)\.(\d)', versiune)
	auto = (h.val('enHDCPMode', 'APPAttr') or '').upper() == 'AUTO'
	c.append(_rand('Versiune', ('%s.%s' % mv.groups() + (', aleasă automat' if auto else '')) if mv else None))
	auth = _da(h.val('HDCPAuthStatus', 'SWStatus'))
	cod = (h.val('HDCPErrCode', 'SWStatus') or '').strip()
	if auth:
		a = ('reușită', BUN)
	elif auth is False and (cod.upper() in ('', 'UNDO', 'NONE', 'NO_ERR', 'NOERR') or activ is False):
		a = ('nu s-a cerut', None)
	elif auth is False:
		a = ('eșuată (%s)' % cod, RAU)
	else:
		a = (None, None)
	c.append(_rand('Autentificare', a[0], a[1]))

	c.append(_titlu('Sunet HDMI'))
	ao = s.ao
	pornit = _da(ao.val('AudioEnable', 'AudioPath'))
	mut = _da(ao.val('AudioMute', 'AudioPath'))
	if pornit is None and mut is None:
		trimis = (None, None)
	elif pornit is False:
		trimis = ('Nu, sunetul HDMI e oprit', RAU)
	elif mut:
		trimis = ('Nu, sunetul e oprit', ATENTIE)
	else:
		trimis = ('Da', BUN)
	c.append(_rand('Sunet trimis', trimis[0], trimis[1]))
	fmt = (ao.val('CodeType', 'AudioAttr') or '').strip().upper()
	c.append(_rand('Format', FORMATE_SUNET.get(fmt, fmt or None)))
	c.append(_rand('Canale', _text_canale(_intreg(ao.val('ChannelCnt', 'AudioAttr')))))
	frec = _intreg(ao.val('SampleFreq', 'AudioAttr'))
	adanc = _intreg(ao.val('SampleDepth', 'AudioAttr'))
	if frec:
		es = _nr(frec / 1000.0, 1) + ' kHz' + ((', %d biți' % adanc) if adanc else '')
	else:
		es = None
	c.append(_rand('Eșantionare', es))
	c.append(_rand('AC3 / DTS în setări', text_setari_sunet(s.audio)))
	return c


# ce scrie imaginea in /proc/stb/audio/ac3 si dts (Setari A/V, tasta AUDIO)
SETARI_SUNET = {'downmix': 'stereo', 'passthrough': 'neschimbat', 'multichannel': 'PCM multicanal'}


def text_setari_sunet(audio):
	"""AC3 si DTS intr-un singur rand (coloana a doua are deja 18 randuri, cat incap in skin): 'stereo / neschimbat';
	un fisier gol (nescris de la pornire, cum era `dts` pe receptor) apare ca 'nescris', unul lipsa ca 'lipsă'"""
	if 'ac3' not in audio and 'dts' not in audio:
		return None
	texte = []
	for nume in ('ac3', 'dts'):
		if nume not in audio:
			texte.append('lipsă')
		else:
			v = (audio[nume] or '').lower()
			texte.append(SETARI_SUNET.get(v, v or 'nescris'))
	return ' / '.join(texte)


def _coloana_televizor(s):
	c = [_titlu('Televizor')]
	sk = s.sink
	c.append(_rand('Nume', s.edid.get('nume')))
	cod = s.edid.get('producator') or (sk.val('ManufacturerName', 'BasicCap') or '').strip().upper() or None
	c.append(_rand('Producător', (PRODUCATORI.get(cod) or ('cod %s' % cod)) if cod else None))
	an = s.edid.get('an') or _intreg(sk.val('YearOfManufacture', 'BasicCap'))
	c.append(_rand('An de fabricație', str(an) if an and 1990 < an < 2200 else None))
	nat = mod_tv((sk.val('NativeFormat', 'VidoCap', 'VideoCap') or '').split(' ')[0])
	c.append(_rand('Rezoluție nativă', ('%d x %d, %d Hz' % (nat[0], nat[1], nat[3])) if nat else None))
	h20 = _da(sk.val('HDMI2.0Support', 'BasicCap'))
	h14 = _da(sk.val('HDMI1.4Support', 'BasicCap'))
	ceas = _intreg(sk.val('MaxTMDSClock(MHz)', 'BasicCap'))
	ver = '2.0' if h20 else ('1.4' if h14 else None)
	c.append(_rand('Versiune HDMI', (ver + ((', %d MHz' % ceas) if ceas else '')) if ver else None))
	if s.moduri:
		c.append(_rand('2160p (4K)', _frecvente(s.moduri, 2160, 'p')))
		c.append(_rand('1080p', _frecvente(s.moduri, 1080, 'p')))
		c.append(_rand('1080i', _frecvente(s.moduri, 1080, 'i')))
		c.append(_rand('720p', _frecvente(s.moduri, 720, 'p')))
		sd = []
		for inalt, bal in ((576, 'p'), (576, 'i'), (480, 'p'), (480, 'i')):
			if any(m[1] == inalt and m[2] == bal for m in s.moduri):
				sd.append('%d%s' % (inalt, bal))
		c.append(_rand('SD', ', '.join(sd) if sd else 'Nu'))
	else:
		c.append(_rand('Moduri acceptate', None))
	c.append(_rand('HDR', _text_hdr_tv(s)))
	c.append(_rand('Culoare', _text_culoare_tv(sk)))
	if s.sunet_tv:
		for i, b in enumerate(s.sunet_tv[:4]):
			text = b['format'] + ((' ' + _text_canale(b['canale'])) if b.get('canale') else '')
			c.append(_rand('Sunet' if i == 0 else '', text))
		if len(s.sunet_tv) > 4:
			c.append(_rand('', 'și altele (%d)' % (len(s.sunet_tv) - 4)))
	else:
		c.append(_rand('Sunet', None))
	return c


def _text_hdr_tv(s):
	d, sk = s.disp, s.sink
	hdr10 = _da(d.val('bHdr10Support'))
	hlg = _da(d.val('bHlgSupport'))
	dv = _da(d.val('bDolbySupport'))
	if hdr10 is None:
		hdr10 = _da(sk.val('HdrEotfSt2084', 'HdrCap'))
	if hlg is None:
		hlg = _da(sk.val('HdrEotfHLG', 'HdrCap'))
	if dv is None:
		oui = (sk.val('DolbyOUI', 'DolbyCap') or '').strip().lower()
		dv = None if not oui else oui not in ('0', '0x0', '0x00', '0x000000')
	if hdr10 is None and hlg is None and dv is None:
		return None
	lista = [n for n, v in (('HDR10', hdr10), ('HLG', hlg), ('Dolby Vision', dv)) if v]
	return ', '.join(lista) if lista else 'Nu'


def _text_culoare_tv(sk):
	adanc = (sk.val('DeepColor', 'VidoCap', 'VideoCap') or '').upper()
	biti = [int(x) for x in re.findall(r'(\d+)BIT', adanc.replace('_', ''))]
	maxim = max([8] + [b // 3 if b > 16 else b for b in biti]) if adanc or biti else None
	bt2020 = 'BT2020' in (sk.val('Colorimetry', 'VidoCap', 'VideoCap') or '').upper()
	if maxim is None and not bt2020:
		return None
	parti = []
	if maxim:
		parti.append('până la %d biți' % maxim)
	if bt2020:
		parti.append('BT.2020')
	return ', '.join(parti)


def text_actualizat(secunde, interval=2.0):
	"""Randul de jos: cat de veche e ultima citire reusita, rotunjit in sus la secunda urmatoare (ecranul il scrie
	o data pe secunda si reciteste la 2 s, deci normal alterneaza „acum 1 s" si „acum 2 s"). Cand citirile nu mai
	reusesc, numarul creste si se spune de ce. None = nicio citire reusita de la deschidere."""
	if secunde is None:
		return 'Starea HDMI nu s-a putut citi'
	n = int(max(0.0, secunde) + 0.25) + 1       # 0,25 s toleranta pentru bataia de ceas venita putin mai devreme
	text = 'Actualizat acum %d s' % n
	if secunde > 2.5 * interval:
		text += ', starea HDMI nu se mai poate citi'
	return text
