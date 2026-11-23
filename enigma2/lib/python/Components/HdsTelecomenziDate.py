# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Datele utilitarului „Telecomenzi” (Screens/HdsTelecomenzi.py). Doar în imaginea HDSatelit.

Fără importuri din enigma2, ca să se probeze pe PC (teste/test_telecomenzi.py). Aici stau:
- butoanele telecomenzii receptorului (Amiko Viper 4K V20): eticheta, codul Linux, comanda NEC, KeyId-ul HiSilicon;
  codurile sunt numere, nu KEYIDS[...], ca modulul să nu depindă de keyids.py (acolo 227 și 438 abia se adaugă);
- fișierul de asocieri /etc/enigma2/hds-telecomenzi.json: citire care nu aruncă nimic (un fișier stricat se mută
  deoparte ca .stricat și se pornește de la zero), scriere atomică (fișier .nou + os.replace);
- regulile asocierii (pașii, coliziunile, „ține apăsat 2 secunde = Sari”), ca stare pură, fără ecran;
- proba tastelor, contorul de semnale IR (numai semn, nu cod), exporturile pentru aplicații și pentru alte module.

Săgeata dreapta (KEY_RIGHT, comanda NEC 0x41) e în tabel ca toate celelalte: într-o captură lipsea numai
pentru că nu a fost apăsată; tasta merge.
"""
import json
import os
import time
import glob
import re
import threading


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: etichetele si mesajele de mai jos se
	traduc la folosire, in ecran si in pagina web (_())."""
	return text

VERSIUNE_FISIER = 1
TITLU_COMENZI_VIRTUALE = N_('Comenzi virtuale')
CALE_ASOCIERI = '/etc/enigma2/hds-telecomenzi.json'
CALE_IR = '/etc/enigma2/hds-ir-asocieri.txt'

# numele dispozitivului de intrare al telecomenzii receptorului (EVIOCGNAME pe /dev/input/event0)
NATIV = 'dreambox advanced remote control (native)'
# dispozitivele receptorului însuși nu sunt niciodată surse de asociere (telecomanda lui, panoul frontal)
PREFIX_PROPRIU = 'dreambox '
CLIENT_VIPER = 0xCD02            # codul de client NEC al telecomenzii Viper (octeții adresei 0x02, 0xCD)

# felurile unui eveniment de tastă (eRCKey::flags)
APASAT, ELIBERAT, TINUT, LUNG, ASCII = 0, 1, 2, 3, 4
FELURI = {APASAT: N_('apăsat'), ELIBERAT: N_('eliberat'), TINUT: N_('ținut'), LUNG: N_('apăsare lungă'),
	ASCII: N_('caracter')}

# modurile capturii din C++ (eRCMapper::setCapture) și motivele de oprire (captureEnded)
CAPTURA_OPRITA, CAPTURA_TOT, CAPTURA_ALTELE, CAPTURA_ASCULTA = 0, 1, 2, 3
OPRIRE_CERUTA, OPRIRE_FARA_TASTE, OPRIRE_TERMEN, OPRIRE_TASTE_IESIRE, OPRIRE_TINUTA, OPRIRE_SEMN_VIATA = 0, 1, 2, 3, 4, 5

# termenele (secunde); cele din C++ sunt puse de ecran la pornirea capturii
TERMEN_FARA_TASTE = 30
TERMEN_TOTAL_CITITOR = 120       # „Proba tastelor” și cititorul: 2 minute în total (revizia, P2)
TERMEN_TOTAL_ASOCIERE = 600      # asocierea nu oprește telecomanda receptorului, deci poate dura mai mult
TERMEN_SEMN_VIATA = 20           # ecranul trimite semnul la 5 s; fără el, C++ oprește captura
TINERE_SARI_MS = 2000            # la asociere: o tastă ținută 2 s pe telecomanda nouă = Sari (revizia, P10)
TINERE_IESIRE_MS = 3000          # la cititor și probă: orice tastă ținută 3 s = ieșire (în C++)

NUMAR_ISTORIC = 9                # rândurile istoricului din cititor (9 x 34 px încap deasupra rândului de ajutor)
MAX_TELECOMENZI = 32
MAX_TASTE = 512
MAX_NUME = 48

# (id, eticheta, cod Linux, nume Linux, comanda NEC), în ordinea de pe telecomandă, de sus în jos.
# Etichetele scrise cu litere mici se traduc (_()); cele mari sunt scrise așa pe telecomandă.
BUTOANE_VIPER = (
	('power', 'POWER', 116, 'KEY_POWER', 0x0C),
	('mute', 'MUTE', 113, 'KEY_MUTE', 0x02),
	('ecran1', N_('ecran 1'), 373, 'KEY_MODE', 0x31),
	('ecran2', N_('ecran 2'), 227, 'KEY_SWITCHVIDEOMODE', 0x32),
	('ecran3', N_('ecran 3'), 438, 'KEY_CONTEXT_MENU', 0x33),
	('1', '1', 2, 'KEY_1', 0x06),
	('2', '2', 3, 'KEY_2', 0x60),
	('3', '3', 4, 'KEY_3', 0x61),
	('4', '4', 5, 'KEY_4', 0x62),
	('5', '5', 6, 'KEY_5', 0x63),
	('6', '6', 7, 'KEY_6', 0x64),
	('7', '7', 8, 'KEY_7', 0x65),
	('8', '8', 9, 'KEY_8', 0x66),
	('9', '9', 10, 'KEY_9', 0x09),
	('anterior', '<', 412, 'KEY_PREVIOUS', 0x01),
	('0', '0', 11, 'KEY_0', 0x05),
	('urmator', '>', 407, 'KEY_NEXT', 0x43),
	('epg', 'EPG', 365, 'KEY_EPG', 0x44),
	('info', 'INFO', 358, 'KEY_INFO', 0x4C),
	('sus', N_('sus'), 103, 'KEY_UP', 0x55),
	('stanga', N_('stânga'), 105, 'KEY_LEFT', 0x03),
	('ok', 'OK', 352, 'KEY_OK', 0x1A),
	('dreapta', N_('dreapta'), 106, 'KEY_RIGHT', 0x41),
	('jos', N_('jos'), 108, 'KEY_DOWN', 0x5B),
	('menu', 'MENU', 139, 'KEY_MENU', 0x46),
	('exit', 'EXIT', 174, 'KEY_EXIT', 0x42),
	('audio', 'AUDIO', 392, 'KEY_AUDIO', 0x50),
	('ttx', 'TTX', 388, 'KEY_TEXT', 0x11),
	('subt', 'SUBT', 370, 'KEY_SUBTITLE', 0x00),
	('volplus', 'VOL+', 115, 'KEY_VOLUMEUP', 0x0A),
	('volminus', 'VOL-', 114, 'KEY_VOLUMEDOWN', 0x40),
	('chplus', 'CH+', 402, 'KEY_CHANNELUP', 0x1C),
	('chminus', 'CH-', 403, 'KEY_CHANNELDOWN', 0x18),
	('rosu', N_('roșu'), 398, 'KEY_RED', 0x14),
	('verde', N_('verde'), 399, 'KEY_GREEN', 0x10),
	('galben', N_('galben'), 400, 'KEY_YELLOW', 0x52),
	('albastru', N_('albastru'), 401, 'KEY_BLUE', 0x56),
	('emc', 'EMC', 393, 'KEY_VIDEO', 0x4B),
	('portal', 'Portal', 150, 'KEY_WWW', 0x47),
	('mplay', 'Mplay', 395, 'KEY_LIST', 0x15),
	('timer', 'Timer', 359, 'KEY_TIME', 0x45),
	('salt_inapoi', N_('salt înapoi'), 165, 'KEY_PREVIOUSSONG', 0x4D),
	('derulare_inapoi', N_('derulare înapoi'), 168, 'KEY_REWIND', 0x67),
	('derulare_inainte', N_('derulare înainte'), 208, 'KEY_FASTFORWARD', 0x68),
	('salt_inainte', N_('salt înainte'), 163, 'KEY_NEXTSONG', 0x69),
	('pauza', N_('pauză'), 119, 'KEY_PAUSE', 0x0B),
	('stop', N_('stop'), 128, 'KEY_STOP', 0x5D),
	('redare', N_('redare'), 207, 'KEY_PLAY', 0x59),
	('inregistrare', N_('înregistrare'), 167, 'KEY_RECORD', 0x51),
	('tv', 'TV', 377, 'KEY_TV', 0x04),
	('help', 'HELP', 138, 'KEY_HELP', 0x4A),
	('fav', 'FAV', 364, 'KEY_FAVORITES', 0x13),
	('radio', 'Radio', 385, 'KEY_RADIO', 0x54),
)

DUPA_ID = dict((b[0], b) for b in BUTOANE_VIPER)
DUPA_COD = dict((b[2], b) for b in BUTOANE_VIPER)
CODURI_VIPER = frozenset(DUPA_COD)
NUMAR_BUTOANE = len(BUTOANE_VIPER)

# ordinea pașilor la asociere: cele mai folosite întâi (proiectul, 2.4)
ORDINE_DE_BAZA = ('power', 'ok', 'sus', 'jos', 'stanga', 'dreapta', 'exit', 'menu')
# butoanele cu care omul ajunge oricând la meniu, deci și la Telecomenzi: tastele neasociate ale unei telecomenzi se
# opresc numai după ce le are pe toate (inclusiv MENU)
BUTOANE_NAVIGARE = ('ok', 'sus', 'jos', 'stanga', 'dreapta', 'exit', 'menu')
ORDINE_ASOCIERE = ORDINE_DE_BAZA + (
	'volplus', 'volminus', 'chplus', 'chminus', 'mute',
	'1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
	'rosu', 'verde', 'galben', 'albastru', 'info', 'epg',
)
ORDINE_ASOCIERE = ORDINE_ASOCIERE + tuple(b[0] for b in BUTOANE_VIPER if b[0] not in ORDINE_ASOCIERE)
INDEX_MENU = ORDINE_ASOCIERE.index('menu')

# numele Linux al câtorva taste de tastatură, pentru cititor (restul le dă keyids.py în ecran)
NUME_TASTE_EXTRA = {
	1: 'KEY_ESC', 14: 'KEY_BACKSPACE', 15: 'KEY_TAB', 28: 'KEY_ENTER', 57: 'KEY_SPACE',
	102: 'KEY_HOME', 104: 'KEY_PAGEUP', 107: 'KEY_END', 109: 'KEY_PAGEDOWN', 110: 'KEY_INSERT', 111: 'KEY_DELETE',
	142: 'KEY_SLEEP', 158: 'KEY_BACK', 159: 'KEY_FORWARD', 164: 'KEY_PLAYPAUSE', 166: 'KEY_STOPCD',
	172: 'KEY_HOMEPAGE', 353: 'KEY_SELECT', 369: 'KEY_PVR', 381: 'KEY_SAT', 510: 'KEY_ASCII',
}


def jurnal(text):
	print('[HdsTelecomenzi] %s' % text)


# ------------------------------------------------------------------ coduri

def keyid_viper(comanda):
	"""KeyId-ul HiSilicon (32 de biți, primul octet transmis jos) al unei comenzi NEC Viper: 0x<~cmd><cmd>CD02."""
	c = comanda & 0xFF
	return ((~c & 0xFF) << 24) | (c << 16) | CLIENT_VIPER


def nec_msb(comanda):
	"""Aceeași secvență citită în ordinea biților de pe fir (forma LIRC, IRremoteESP8266). Calculată, nu capturată."""
	octeti = (0x02, 0xCD, comanda & 0xFF, ~comanda & 0xFF)
	v = 0
	for o in octeti:
		r = 0
		for i in range(8):
			if o & (1 << i):
				r |= 1 << (7 - i)
		v = (v << 8) | r
	return v


def e_viper_ir(keyid):
	"""Egalitate exactă a celor 16 biți de jos cu 0xCD02 (revizia, P11): masca din showiframe, (k & cc) == cc,
	ar lua drept Viper și o telecomandă NEC cu adresa 0x02 (0xFD02)."""
	return (keyid & 0xFFFF) == CLIENT_VIPER


def difera_un_bit(a, b):
	"""RC5 și RC6 schimbă un bit la fiecare apăsare nouă a aceluiași buton (revizia, P12). Poziția lui în KeyId-ul
	driverului nu e dovedită, de aceea la asociere butonul se cere de două ori: dacă cele două coduri diferă
	exact într-un bit, se păstrează amândouă."""
	x = (a ^ b) & 0xFFFFFFFFFFFFFFFF
	return x != 0 and (x & (x - 1)) == 0


def e_dispozitiv_propriu(nume):
	return isinstance(nume, str) and nume.startswith(PREFIX_PROPRIU)


class ProfilTelecomanda(object):
	"""Descriere locala; lipsa listei nu inseamna o telecomanda Viper."""
	def __init__(self, model, butoane=(), dispozitive=(), viper=False, descriere=''):
		self.model = model
		self.butoane = tuple(butoane)
		self.dupa_cod = dict((b[2], b) for b in self.butoane)
		self.dupa_id = dict((b[0], b) for b in self.butoane)
		self.dispozitive = frozenset((NATIV,) + tuple(dispozitive))
		self.viper = viper
		self.descriere = descriere

	def propriu(self, nume):
		return nume in self.dispozitive

	def buton(self, ev):
		cod = ev['tinta'] if ev['tinta'] >= 0 else (ev['cod'] if self.propriu(ev['dispozitiv']) else -1)
		if self.butoane:
			return self.dupa_cod.get(cod)
		# Numai coduri Linux cunoscute; nu inventam taste fizice sau comenzi IR.
		if cod in DUPA_COD:
			b = DUPA_COD[cod]
			return (b[0], b[3], cod, b[3], None)
		nume = NUME_TASTE_EXTRA.get(cod)
		return ('key%d' % cod, nume, cod, nume, None) if nume else None


def _text_local(cale):
	try:
		with open(cale, 'r', encoding='utf-8', errors='replace') as f:
			return f.read(8192)
	except (OSError, IOError):
		return ''


_PROFIL_LACAT = threading.Lock()
_PROFIL_CITIRE = None


def profil_receptor(model=None, director=None, radacina=''):
	"""Citire izolata; rezultatul lent ramane legat de cererea initiala."""
	if threading.current_thread() is not threading.main_thread():
		return _profil_receptor(model, director, radacina)
	profil = ProfilTelecomanda(model or 'unknown', dispozitive=(('hisiir', 'hisiir/input0')
		if model == 'gbtrio4k' else ()))
	profil._cerere = (model, director, radacina)
	profil._citire = None
	_profil_cere(profil)
	citire = profil._citire
	if citire is not None:
		citire['gata'].wait(0.2)
	return profil_actual(profil)


def _profil_cere(profil):
	global _PROFIL_CITIRE
	with _PROFIL_LACAT:
		citire = _PROFIL_CITIRE
		if citire is None or citire['gata'].is_set():
			citire = {'cheie': profil._cerere, 'gata': threading.Event(), 'profil': None}
			_PROFIL_CITIRE = citire
			def incarca():
				try:
					citire['profil'] = _profil_receptor(*citire['cheie'])
				except Exception:
					# O citire nereusita ramane o proba limitata, nu opreste interfata.
					pass
				finally:
					citire['gata'].set()
			threading.Thread(target=incarca, name='HdsProfilTelecomanda', daemon=True).start()
		if citire['cheie'] == profil._cerere:
			profil._citire = citire


def profil_actual(profil):
	"""Preia numai pe firul principal; nu modifica obiectele unei sesiuni inchise."""
	if threading.current_thread() is not threading.main_thread() or not hasattr(profil, '_cerere'):
		return profil
	if profil._citire is None:
		_profil_cere(profil)
	citire = profil._citire
	if citire is not None and citire['gata'].is_set():
		return citire['profil'] or ProfilTelecomanda(profil.model, dispozitive=profil.dispozitive)
	return profil


def _profil_receptor(model=None, director=None, radacina=''):
	"""Modelul propriu si descrierea aferenta din imagine; fara profil, proba limitata."""
	if model is None:
		try:
			from Tools.HardwareInfo import getModelName
			model = getModelName()
		except Exception:
			model = 'unknown'
	try:
		from Components.HdsBoxInfoModele import MODELE
		cap = MODELE.get(model, {})
	except ImportError:
		cap = {}
	dispozitive = set()
	for cale in glob.glob(os.path.join(radacina or '/', 'sys/class/rc/rc*/input*/name')):
		nume = _text_local(cale).strip()
		if nume:
			dispozitive.add(nume)
	# Numele dovedit al driverului rc-core al Trio, nu un nume de tastatura USB.
	if model == 'gbtrio4k':
		dispozitive.update(('hisiir', 'hisiir/input0'))
	viper = model in ('viper4k', 'viper4kv20')
	if viper:
		return ProfilTelecomanda(model, BUTOANE_VIPER, dispozitive, True, 'telecomanda-viper.json')
	rcname = cap.get('rcname', '')
	butoane = []
	cale = ''
	if re.fullmatch(r'[a-zA-Z0-9_-]+', rcname):
		if director is None:
			director = '/usr/share/enigma2'
		cale = os.path.join(director, 'telecomanda-%s.json' % rcname)
		try:
			with open(cale, 'rb') as f:
				date = json.loads(f.read(512 * 1024).decode('utf-8'))
			iduri, coduri = set(), set()
			for b in date['butoane']:
				ident, cod, nume = b['id'], b['cod'], b['nume']
				if (not isinstance(ident, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,48}', ident)
						or type(cod) is not int or not 0 < cod <= 767 or cod in coduri or ident in iduri
						or not isinstance(nume, str) or not re.fullmatch(r'KEY_[A-Z0-9_]+', nume)
						or not isinstance(b['eticheta'], str) or not 0 < len(b['eticheta']) <= 48):
					raise ValueError('profil')
				butoane.append((ident, b['eticheta'], cod, nume, None))
				iduri.add(ident)
				coduri.add(cod)
			if not 0 < len(butoane) <= MAX_TASTE:
				raise ValueError('profil')
		except (OSError, ValueError, TypeError, KeyError):
			butoane = []
	return ProfilTelecomanda(model, butoane, dispozitive, descriere=cale if butoane else '')


def text_proba(proba, _):
	if proba.gata():
		return _('Toate butoanele merg.')
	if proba.profil.butoane:
		return _('%d din %d de butoane verificate') % (len(proba.verificate), len(proba.profil.butoane))
	return _('Taste cunoscute verificate: %d') % len(proba.verificate)


def detalii_profil(profil, _):
	if profil.butoane:
		return []
	return [_('Lipsește profilul complet al telecomenzii pentru acest model. Verificăm numai tastele cunoscute primite; proba nu poate confirma toate butoanele.')]


def citeste_ir(cale=None, radacina=''):
	"""Metadate rc-core si contoare optionale ale driverului; niciodata /dev/input sau LIRC."""
	if cale is not None:
		return _text_local(cale)
	contoare, protocoale = {}, set()
	for rc in sorted(glob.glob(os.path.join(radacina or '/', 'sys/class/rc/rc*'))):
		p = _text_local(os.path.join(rc, 'protocols'))
		protocoale.update(re.findall(r'\[([a-zA-Z0-9_-]+)\]', p))
		# rc-core nu garanteaza statistici. Acceptam numai contoare numite explicit
		# de driver; protocoalele disponibile nu dovedesc primirea unui semnal.
		for rand in _text_local(os.path.join(rc, 'statistics')).splitlines():
			m = re.fullmatch(r'\s*(unknown_frames|rx_frames)\s*[:=]\s*(\d+)\s*', rand)
			if m:
				fel = 'straine' if m[1] == 'unknown_frames' else 'cadre'
				cheie = rc
				if cheie not in contoare or fel == 'straine':
					contoare[cheie] = (int(m[2]), fel)
	legacy = '/proc/hisi/msp/ir'
	text = _text_local(os.path.join(radacina or '/', legacy.lstrip('/')))
	ok = ContorIR.citeste_ok(text)
	if ok is not None:
		# Acelasi driver poate expune ambele suprafete. Nu dublam semnalul.
		contoare = {legacy: (ok, 'faze')}
	return {'contoare': contoare, 'protocoale': sorted(protocoale)}


def detalii_ir(profil, contor, _):
	randuri = []
	if not profil.viper:
		if contor is not None and contor.protocoale:
			randuri.append(_('IR rc-core: %s') % ', '.join(contor.protocoale))
		else:
			randuri.append(_('Protocolul și adresa IR nu sunt confirmate pentru acest model.'))
	if contor is not None and contor.disponibil is None:
		randuri.append(_('Se verifică dacă există un contor IR disponibil.'))
	elif contor is None or not contor.disponibil:
		randuri.append(_('Nu există un contor IR disponibil; semnalele străine nu pot fi numărate.'))
	return randuri


def nume_tasta(cod, keyids=None):
	b = DUPA_COD.get(cod)
	if b is not None:
		return b[3]
	if cod in NUME_TASTE_EXTRA:
		return NUME_TASTE_EXTRA[cod]
	if keyids:
		for k, v in keyids.items():
			if v == cod:
				return k
	return ''


def eticheta(cod):
	b = DUPA_COD.get(cod)
	return b[1] if b is not None else ''


def text_cod(cod, keyids=None):
	"""„352 (0x160) KEY_OK”."""
	n = nume_tasta(cod, keyids)
	return ('%d (0x%X) %s' % (cod, cod, n)).rstrip()


# ------------------------------------------------------------------ fișierul de asocieri

def date_goale():
	return {'versiune': VERSIUNE_FISIER, 'codViperImplicit': True, 'telecomenzi': []}


def _intreg(v):
	"""Codul sursă din JSON: „28” sau „0x1C” (chei de dicționar) ori 28."""
	if isinstance(v, bool):
		raise ValueError('bool')
	if isinstance(v, int):
		return v
	if isinstance(v, str):
		s = v.strip().lower()
		return int(s, 16) if s.startswith('0x') else int(s)
	raise ValueError('tip')


def _curata_telecomanda(t, iduri):
	if not isinstance(t, dict):
		return None
	fel = t.get('fel')
	if fel not in ('usb', 'ir'):
		return None
	nume = t.get('nume')
	if not isinstance(nume, str) or not nume.strip():
		nume = str(t.get('dispozitiv') or t.get('protocol') or 'telecomandă')
	nume = nume.strip()[:MAX_NUME]
	r = {'id': '', 'nume': nume, 'fel': fel, 'activa': t.get('activa') is not False}
	if fel == 'usb':
		disp = t.get('dispozitiv')
		if not isinstance(disp, str) or not disp or e_dispozitiv_propriu(disp) or len(disp) > 255:
			return None
		r['dispozitiv'] = disp
		r['neasociate'] = 'opresc' if t.get('neasociate') == 'opresc' else 'trec'
		limita = 0x2FF
	else:
		prot = t.get('protocol')
		if not isinstance(prot, str) or not prot or len(prot) > 64:
			return None
		r['protocol'] = prot
		limita = 0xFFFFFFFFFFFFFFFF
	taste = {}
	sursa = t.get('taste')
	if isinstance(sursa, dict):
		for k, v in sursa.items():
			try:
				cod = _intreg(k)
				tinta = _intreg(v)
			except (ValueError, TypeError):
				continue
			if not 0 < cod <= limita or tinta not in CODURI_VIPER:
				continue
			if fel == 'ir' and e_viper_ir(cod):
				continue
			if len(taste) >= MAX_TASTE:
				break
			taste[cod] = tinta
	r['taste'] = taste
	ident = t.get('id')
	if not isinstance(ident, str) or not ident or ident in iduri or len(ident) > 32:
		ident = id_nou(fel, iduri)
	r['id'] = ident
	iduri.add(ident)
	return r


def id_nou(fel, iduri):
	i = 1
	while '%s-%d' % (fel, i) in iduri:
		i += 1
	return '%s-%d' % (fel, i)


def curata(brut):
	"""Datele din JSON, verificate: ce nu se înțelege se lasă deoparte, nimic nu aruncă."""
	d = date_goale()
	if not isinstance(brut, dict):
		return d
	d['codViperImplicit'] = brut.get('codViperImplicit') is not False
	iduri = set()
	lista = brut.get('telecomenzi')
	if isinstance(lista, list):
		for t in lista:
			r = _curata_telecomanda(t, iduri)
			if r is not None and len(d['telecomenzi']) < MAX_TELECOMENZI:
				d['telecomenzi'].append(r)
	return d


# Mesajele despre fișierul de asocieri, ca șabloane: modulul nu traduce (nu are enigma2); ecranul
# le trece prin _() și abia apoi pune numele sau motivul. Lista lor intră în textele de tradus (cod-unelte/texte_po.py).
FISIER_NECITIT = N_('fișierul de asocieri nu se poate citi (%s)')
FISIER_DEOPARTE = N_('fișierul de asocieri e stricat; l-am pus deoparte ca %s.stricat')
FISIER_IGNORAT = N_('fișierul de asocieri e stricat; îl ignor')
MESAJE_FISIER = (FISIER_NECITIT, FISIER_DEOPARTE, FISIER_IGNORAT)


def text_mesaj(sablon, argument, traducere=None):
	"""Mesajul gata de arătat: șablonul (tradus, dacă e dată `traducere`) cu argumentul pus; '' dacă nu e mesaj."""
	if not sablon:
		return ''
	text = traducere(sablon) if traducere is not None else sablon
	return text % argument if argument is not None else text


def incarca_cu_sablon(cale=CALE_ASOCIERI):
	"""(date, șablon, argument). Fișier lipsă = date goale, fără mesaj (șablon ''). Fișier stricat = mutat deoparte ca
	.stricat, date goale și un singur rând de informare; telecomanda receptorului merge oricum. Șablonul e unul din
	MESAJE_FISIER, netradus; argumentul (numele fișierului sau motivul) se pune după traducere."""
	try:
		with open(cale, 'rb') as f:
			brut = f.read(1024 * 1024 + 1)
	except FileNotFoundError:
		return date_goale(), '', None
	except OSError as e:
		return date_goale(), FISIER_NECITIT, str(e.strerror or e)
	try:
		if len(brut) > 1024 * 1024:
			raise ValueError('prea mare')
		obiect = json.loads(brut.decode('utf-8'))
		if not isinstance(obiect, dict) or not isinstance(obiect.get('telecomenzi', []), list):
			raise ValueError('forma')
	except (ValueError, UnicodeDecodeError):
		try:
			os.replace(cale, cale + '.stricat')
		except OSError:
			return date_goale(), FISIER_IGNORAT, None
		return date_goale(), FISIER_DEOPARTE, os.path.basename(cale)
	return curata(obiect), '', None


def incarca(cale=CALE_ASOCIERI):
	"""(date, mesaj): ca incarca_cu_sablon, cu mesajul în română, pentru jurnal și pentru pornire."""
	date, sablon, argument = incarca_cu_sablon(cale)
	return date, text_mesaj(sablon, argument)


def de_scris(date):
	"""Forma din fișier: codurile ca șiruri (JSON nu are chei numerice); IR în hexa."""
	lista = []
	for t in date['telecomenzi']:
		r = {'id': t['id'], 'nume': t['nume'], 'fel': t['fel'], 'activa': bool(t['activa'])}
		if t['fel'] == 'usb':
			r['dispozitiv'] = t['dispozitiv']
			r['neasociate'] = t.get('neasociate', 'trec')
			r['taste'] = dict((str(k), v) for k, v in sorted(t['taste'].items()))
		else:
			r['protocol'] = t['protocol']
			r['taste'] = dict(('0x%X' % k, v) for k, v in sorted(t['taste'].items()))
		lista.append(r)
	return {'versiune': VERSIUNE_FISIER, 'codViperImplicit': bool(date.get('codViperImplicit', True)), 'telecomenzi': lista}


def salveaza(date, cale=CALE_ASOCIERI):
	"""Scriere atomică: fișier .nou, fsync, os.replace. Întoarce '' sau textul erorii (nu aruncă)."""
	nou = cale + '.nou'
	try:
		text = json.dumps(de_scris(date), ensure_ascii=False, indent=1, sort_keys=True)
		with open(nou, 'wb') as f:
			f.write(text.encode('utf-8'))
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
	except (OSError, TypeError, ValueError) as e:
		try:
			os.unlink(nou)
		except OSError:
			pass
		return getattr(e, 'strerror', None) or str(e)
	return ''


# ------------------------------------------------------------------ lucrul cu asocierile

def gaseste(date, ident):
	for t in date['telecomenzi']:
		if t['id'] == ident:
			return t
	return None


def gaseste_dispozitiv(date, dispozitiv):
	for t in date['telecomenzi']:
		if t['fel'] == 'usb' and t['dispozitiv'] == dispozitiv:
			return t
	return None


def adauga_usb(date, dispozitiv, nume=None):
	"""O telecomandă USB nouă (sau cea existentă pentru același dispozitiv). Întoarce None dacă nu se poate."""
	if not isinstance(dispozitiv, str) or not dispozitiv or e_dispozitiv_propriu(dispozitiv):
		return None
	t = gaseste_dispozitiv(date, dispozitiv)
	if t is not None:
		return t
	if len(date['telecomenzi']) >= MAX_TELECOMENZI:
		return None
	iduri = set(x['id'] for x in date['telecomenzi'])
	nume = (nume or dispozitiv).strip()[:MAX_NUME] or dispozitiv[:MAX_NUME]
	# o tastatură lasă tastele neasociate să treacă; o telecomandă le oprește, ca un buton necunoscut să nu facă
	# ceva neașteptat (proiectul, 6), dar numai după OK, săgeți, EXIT și MENU (opreste_neasociate)
	neasociate = 'trec' if 'keyboard' in dispozitiv.lower() else 'opresc'
	t = {'id': id_nou('usb', iduri), 'nume': nume, 'fel': 'usb', 'dispozitiv': dispozitiv, 'activa': True,
		'neasociate': neasociate, 'taste': {}}
	date['telecomenzi'].append(t)
	return t


def sursa_pentru(t, cod_tinta):
	"""Codurile sursă ale unei telecomenzi care dau butonul Viper `cod_tinta`."""
	return sorted(k for k, v in t['taste'].items() if v == cod_tinta)


def asociaza(date, ident, cod_sursa, cod_tinta, muta=False):
	"""Pune cod_sursa -> cod_tinta pe telecomanda `ident`. Întoarce (stare, detaliu):
	('ok', None); ('folosit', cod_tinta_vechi) dacă același cod e deja al altui buton pe aceeași telecomandă și
	muta=False; ('alta', (ident_alt, cod_tinta_vechi)) dacă un cod IR e deja al altei telecomenzi și muta=False;
	('refuzat', motiv) pentru ce nu se poate asocia."""
	t = gaseste(date, ident)
	if t is None:
		return 'refuzat', 'telecomanda nu există'
	if cod_tinta not in CODURI_VIPER:
		return 'refuzat', 'butonul nu e pe telecomanda receptorului'
	if not isinstance(cod_sursa, int) or cod_sursa <= 0:
		return 'refuzat', 'cod greșit'
	if t['fel'] == 'ir' and e_viper_ir(cod_sursa):
		return 'refuzat', 'codul telecomenzii receptorului'
	if t['fel'] == 'usb' and cod_sursa > 0x2FF:
		return 'refuzat', 'cod greșit'
	vechi = t['taste'].get(cod_sursa)
	if vechi is not None and vechi != cod_tinta and not muta:
		return 'folosit', vechi
	if t['fel'] == 'ir':
		for alt in date['telecomenzi']:
			if alt is not t and alt['fel'] == 'ir' and cod_sursa in alt['taste']:
				if not muta:
					return 'alta', (alt['id'], alt['taste'][cod_sursa])
				del alt['taste'][cod_sursa]
	if len(t['taste']) >= MAX_TASTE and cod_sursa not in t['taste']:
		return 'refuzat', 'prea multe taste'
	t['taste'][cod_sursa] = cod_tinta
	return 'ok', None


def sterge_buton(date, ident, cod_tinta):
	"""Scoate toate codurile sursă care dau butonul Viper `cod_tinta` (refacerea unui buton, „Înapoi”)."""
	t = gaseste(date, ident)
	if t is None:
		return 0
	coduri = sursa_pentru(t, cod_tinta)
	for k in coduri:
		del t['taste'][k]
	return len(coduri)


def sterge_tasta(date, ident, cod_sursa):
	t = gaseste(date, ident)
	if t is None or cod_sursa not in t['taste']:
		return False
	del t['taste'][cod_sursa]
	return True


def sterge_telecomanda(date, ident):
	n = len(date['telecomenzi'])
	date['telecomenzi'] = [t for t in date['telecomenzi'] if t['id'] != ident]
	return len(date['telecomenzi']) != n


def sterge_tot(date):
	date['telecomenzi'] = []


def redenumeste(date, ident, nume):
	t = gaseste(date, ident)
	if t is None or not isinstance(nume, str) or not nume.strip():
		return False
	t['nume'] = nume.strip()[:MAX_NUME]
	return True


def comuta_activa(date, ident):
	t = gaseste(date, ident)
	if t is None:
		return None
	t['activa'] = not t['activa']
	return t['activa']


def comuta_neasociate(date, ident):
	t = gaseste(date, ident)
	if t is None or t['fel'] != 'usb':
		return None
	t['neasociate'] = 'trec' if t.get('neasociate') == 'opresc' else 'opresc'
	return t['neasociate']


def navigare_completa(t):
	"""Are asociate toate butoanele de navigare (OK, săgețile, EXIT și MENU)?"""
	facute = set(DUPA_COD[v][0] for v in t['taste'].values() if v in DUPA_COD)
	return all(i in facute for i in BUTOANE_NAVIGARE)


def opreste_neasociate(t):
	"""Tastele neasociate ale unei telecomenzi USB se opresc numai când ea are asociate toate butoanele de navigare,
	cu MENU. Până atunci trec, deci OK (KEY_ENTER), săgețile, EXIT și MENU merg ca
	înainte de asociere: o asociere neterminată (un termen, o cădere, „Păstrezi ce ai asociat? Da” după doi pași) sau
	una terminată fără MENU nu lasă omul fără telecomandă și fără drum spre meniu, nici după repornire. Alegerea „se
	opresc” rămâne scrisă în fișier și lucrează singură după ultimul dintre aceste butoane."""
	return t['fel'] == 'usb' and t.get('neasociate') == 'opresc' and navigare_completa(t)


def tabel_mapper(date):
	"""Ce primește eRCMapper: ([(dispozitiv, cod, cod_tinta)], [dispozitive cu tastele neasociate oprite]).
	Numai telecomenzile USB active; cele IR le traduce biblioteca din showiframe."""
	perechi, oprite = [], []
	for t in date['telecomenzi']:
		if t['fel'] != 'usb' or not t['activa']:
			continue
		for k, v in sorted(t['taste'].items()):
			perechi.append((t['dispozitiv'], k, v))
		if opreste_neasociate(t):
			oprite.append(t['dispozitiv'])
	return perechi, oprite


def incarca_in_mapper(mapper, date):
	"""Pune tabelul în eRCMapper (clear, add, setBlockUnmapped, setDefaultViper). `mapper` e obiectul C++ sau un
	fals în probe."""
	perechi, oprite = tabel_mapper(date)
	mapper.clear()
	for disp, cod, tinta in perechi:
		mapper.add(disp, cod, tinta)
	for disp in oprite:
		mapper.setBlockUnmapped(disp, True)
	mapper.setDefaultViper(bool(date.get('codViperImplicit', True)))
	return len(perechi)


def porneste(cale=CALE_ASOCIERI, mapper=None):
	"""La pornirea interfeței (mytest.py): asocierile din fișier în eRCMapper. Un fișier stricat se mută deoparte
	cu un singur rând în jurnal; telecomanda receptorului merge oricum. enigma se importă numai aici, ca modulul
	să rămână de probat pe PC."""
	if mapper is None:
		from enigma import eRCMapper
		mapper = eRCMapper.getInstance()
	if mapper is None:
		return 0
	date, mesaj = incarca(cale)
	if mesaj:
		jurnal(mesaj)
	n = incarca_in_mapper(mapper, date)
	mapper.apply()
	if n:
		jurnal('%d taste asociate, de pe %d telecomenzi' % (n, len(date['telecomenzi'])))
	return n


def text_ir(date, acum=None, asociere_in_curs=False):
	"""Fișierul citit de libhdsir.so: rânduri „protocol<TAB>KeyId<TAB>KeyIdViper” în hexa. Codurile Viper
	nu intră niciodată (egalitate exactă). Rândul „#asociere <secunde>” cere bibliotecii să nu mai dea taste străine
	cât ține asocierea, cu termen de 5 minute de la data scrisă (revizia, P11)."""
	randuri = ['# hds-ir-asocieri, scris de Telecomenzi']
	if asociere_in_curs:
		randuri.append('#asociere %d' % int(acum if acum is not None else time.time()))
	for t in date['telecomenzi']:
		if t['fel'] != 'ir' or not t['activa']:
			continue
		for k, v in sorted(t['taste'].items()):
			b = DUPA_COD.get(v)
			if b is None or e_viper_ir(k):
				continue
			randuri.append('%s\t0x%X\t0x%08X' % (t['protocol'], k, keyid_viper(b[4])))
	return '\n'.join(randuri[:257]) + '\n'


# ------------------------------------------------------------------ exporturi pentru aplicații

def tabel_viper():
	"""Butoanele Viper cu toate formele de cod (pentru export și pagina web)."""
	r = []
	for ident, et, cod, nume, cmd in BUTOANE_VIPER:
		r.append({'id': ident, 'eticheta': et, 'cod': cod, 'codHex': '0x%X' % cod, 'nume': nume,
			'necAdresa': '0x02 0xCD', 'necComanda': '0x%02X' % cmd, 'keyId': '0x%08X' % keyid_viper(cmd),
			'necMsb': '0x%08X' % nec_msb(cmd)})
	return r


def tabel_profil(profil=None):
	"""Codurile confirmate ale profilului; IR numai pentru profilul Viper dovedit."""
	if profil is None or profil.viper:
		return tabel_viper()
	return [{'id': b[0], 'eticheta': b[1], 'cod': b[2], 'codHex': '0x%X' % b[2], 'nume': b[3]}
		for b in profil.butoane]


def export_json(date, profil=None):
	corp = {'telecomandaReceptorului': tabel_profil(profil), 'asocieri': de_scris(date)['telecomenzi']}
	if profil is not None:
		corp['profil'] = {'model': profil.model, 'complet': bool(profil.butoane)}
	return json.dumps(corp, ensure_ascii=False, indent=1)


def export_csv(date, profil=None):
	randuri = ['sursa;dispozitiv;cod;cod_hex;nume;tinta;tinta_nume;nec_comanda;keyid']
	for b in tabel_profil(profil):
		randuri.append('%s;%s;%d;%s;%s;%s;%s;%s;%s' % ('telecomanda receptorului', NATIV, b['cod'], b['codHex'],
			b['nume'], b['id'], b['nume'], b.get('necComanda', ''), b.get('keyId', '')))
	for t in date['telecomenzi']:
		disp = t.get('dispozitiv') or t.get('protocol', '')
		for k, v in sorted(t['taste'].items()):
			b = DUPA_COD[v]
			nume = t['nume'].replace(';', ',')
			randuri.append('%s;%s;%d;0x%X;%s;%s;%s;;' % (nume, disp.replace(';', ','), k, k, nume_tasta(k) if t['fel'] == 'usb' else '',
				b[0], b[3]))
	return '\n'.join(randuri) + '\n'


# ------------------------------------------------------------------ pagina web

MODUL_WEB = 'Plugins.Extensions.HdsWebControl.plugin'


def adresa_pagina_web(modul):
	"""Adresa paginii /telecomenzi pentru rândul de pe ecran, sau '' (revizia, P21). `modul` e pluginul web deja
	încărcat (sys.modules), niciodată importat de aici. Adresa se ia din adresaWeb() a pluginului (IP plus portul din
	setări, implicit 80, fără „:80” în adresă), iar rândul se arată numai dacă serverul chiar ascultă (`_server_pornit`,
	pus de pornirea lui) și dacă pagina există: pluginul are `ARE_PAGINA_TELECOMENZI = True`
	odată cu pagina."""
	try:
		if modul is None or getattr(modul, 'ARE_PAGINA_TELECOMENZI', False) is not True:
			return ''
		if getattr(modul, '_server_pornit', None) is None:
			return ''
		adresa = modul.adresaWeb()
		if not isinstance(adresa, str) or not adresa.startswith('http://'):
			return ''
		return adresa.rstrip('/') + '/telecomenzi'
	except Exception:
		return ''


# ------------------------------------------------------------------ evenimentele din C++

def eveniment(t):
	"""Tuplul din eRCMapper.getEvents(): (numar, ms, dispozitiv, cod, fel, tinta, scan). `tinta` = codul Viper în
	care se traduce tasta (-1 = niciunul), `scan` = codul brut MSC_SCAN al dispozitivelor USB (-1 = niciunul)."""
	try:
		numar, ms, disp, cod, fel, tinta, scan = t
		return {'numar': int(numar), 'ms': int(ms), 'dispozitiv': str(disp), 'cod': int(cod), 'fel': int(fel),
			'tinta': int(tinta), 'scan': int(scan)}
	except (TypeError, ValueError):
		return None


def ancora_ceas(ev):
	"""(ms pe ceasul de perete, ms pe ceasul monoton al lui C++) luate la prima tastă a cititorului. Tasta ajunge aici
	chiar din keyEvent() (rawKey), deci cele două ceasuri se citesc aproape odată."""
	return int(round(time.time() * 1000)), ev['ms']


def ora_tastei(ev, ancora=None):
	"""„22:15:07.123”: ora tastei, dintr-un singur ceas. Cu `ancora` (ancora_ceas), ora se
	socotește din ceasul monoton al evenimentelor, în milisecunde întregi, deci două taste au orele în ordinea în care
	au venit, oricât de aproape ar fi și chiar peste granița unei secunde. Fără ancoră, e ora de acum, cu milisecundele
	ei (secundele și milisecundele din același ceas)."""
	if ancora is not None:
		ms = ancora[0] + (ev['ms'] - ancora[1])
	else:
		ms = int(time.time() * 1000)
	secunde, rest = divmod(ms, 1000)
	return time.strftime('%H:%M:%S', time.localtime(secunde)) + '.%03d' % rest


def rand_istoric(ev, ora=None, keyids=None, ancora=None, traduce=None):
	"""„22:15:07.123  Logitech USB Receiver  352 (0x160) KEY_OK  apăsat”."""
	if ora is None:
		ora = ora_tastei(ev, ancora)
	if ev['fel'] == ASCII:
		cod = 'caracter %r' % chr(ev['cod']) if 0 < ev['cod'] < 0x110000 else 'caracter %d' % ev['cod']
	else:
		cod = text_cod(ev['cod'], keyids)
	disp = ev['dispozitiv']
	if disp == NATIV:
		disp = 'telecomanda receptorului'
	scan = '  scan 0x%X' % ev['scan'] if ev['scan'] >= 0 else ''
	fel = FELURI.get(ev['fel'], str(ev['fel']))
	if traduce is not None:
		fel = traduce(fel)
	return '%s  %s  %s  %s%s' % (ora, disp[:32], cod, fel, scan)


class Proba(object):
	"""Taste primite direct sau prin asociere, limitate la profilul dovedit al modelului."""

	def __init__(self, profil=None):
		self.profil = profil if profil is not None else profil_receptor()
		self.verificate = set()
		self.ultima = None
		self.evenimente = []
		self.ancora = None
		self._in_asteptare = {}

	def actualizeaza_profil(self, profil):
		if profil is self.profil:
			return
		vechi = self.profil
		self.profil = profil
		if hasattr(vechi, '_cerere'):
			self.verificate = set()
			self.ultima = None
		elif profil.butoane:
			self.verificate.intersection_update(profil.dupa_id)
		for ev in self._in_asteptare.values():
			b = profil.buton(ev)
			if b is not None:
				self.verificate.add(b[0])
				self.ultima = b[0]
		self._in_asteptare.clear()

	def primeste(self, ev):
		"""Întoarce id-ul butonului Viper aprins de eveniment sau None."""
		if ev['fel'] != ASCII:
			# Numai coduri, in proba deschisa de om. Fara text tastat.
			print('[HdsTelecomenzi] tasta=%d semn=%d ms=%d' %
				(ev['cod'], ev['fel'], ev['ms']))
		if self.ancora is None:
			self.ancora = ancora_ceas(ev)
		# Pastram si eliberarile. Un buton aprins nu dovedeste tinerea.
		self.evenimente.append(dict(ev))
		self.evenimente = self.evenimente[-NUMAR_ISTORIC:]
		if ev['fel'] not in (APASAT, TINUT, LUNG):
			return None
		if hasattr(self.profil, '_cerere'):
			# Doar taste unice cat se incarca profilul, nu istoric nelimitat sau text.
			cheie = (ev['dispozitiv'], ev['cod'], ev['tinta'])
			if len(self._in_asteptare) < MAX_TASTE or cheie in self._in_asteptare:
				self._in_asteptare[cheie] = dict(ev)
		b = self.profil.buton(ev)
		if b is None:
			return None
		self.verificate.add(b[0])
		self.ultima = b[0]
		return b[0]

	def istoric(self, traduce=None):
		"""Aceeasi ordine si aceleasi faze pe televizor si in pagina web."""
		return [rand_istoric(ev, ancora=self.ancora, traduce=traduce)
			for ev in reversed(self.evenimente)]

	def ramase(self):
		return [b[0] for b in self.profil.butoane if b[0] not in self.verificate]

	def gata(self):
		return bool(self.profil.butoane) and len(self.verificate) == len(self.profil.butoane)


# repetarea și eliberarea tastei care pornește captura: 41 din 54 de apăsări Viper au o repetare,
# eliberarea vine la 169-364 ms (masurat pe telecomanda Viper)
CREDIT_TASTA_PORNIRE = 2


class ContorIR(object):
	"""Semn IR aproximativ, din contoarele disponibile ale driverului.

	Accepta Get(Try/OK) pentru faze HiSilicon si instantanee rc-core optionale.
	Cadrele nu includ eliberari sintetice; absenta contorului nu inseamna zero semnale.
	"""

	def __init__(self, credit=0, profil=None):
		self.pornit_la = time.perf_counter()
		self.profil = profil if profil is not None else profil_receptor()
		self.disponibil = None
		self.protocoale = []
		self.baze = {}
		self.cadre_native = 0
		self.ok = None
		self.native = 0
		self.straine = 0
		self.straine_dovedite = 0
		# tasta receptorului care a pornit captura (OK) era apasata
		# INAINTE de captura, deci repetarea (~280 ms) si eliberarea ei (169-364 ms, masurat pe telecomanda Viper) cresc contorul
		# fara sa fie evenimente in enigma2 (rcmapper.cpp nu face eveniment pentru o tasta apasata inainte). In prima
		# fereastra de dupa baza se scad cel mult `credit` semnale (CREDIT_TASTA_PORNIRE); apoi creditul nu mai exista.
		self.credit = credit

	@staticmethod
	def citeste_ok(text):
		for rand in text.splitlines():
			if 'Get(Try/OK)' in rand:
				try:
					return int(rand.rsplit('/', 1)[1].strip())
				except (ValueError, IndexError):
					return None
		return None

	def nativ(self, ev):
		if self.profil.propriu(ev['dispozitiv']) and ev['fel'] in (APASAT, TINUT, ELIBERAT):
			self.native += 1
			if ev['fel'] in (APASAT, TINUT):
				self.cadre_native += 1

	def fereastra(self, text):
		if isinstance(text, dict):
			return self._surse(text)
		ok = self.citeste_ok(text or '')
		self.disponibil = ok is not None
		if ok is None:
			return self.straine
		if self.ok is not None:
			if ok >= self.ok:
				# o tastă a receptorului poate cădea în fereastra de după semnalul ei (citirea a venit între ele): se scade
				# tot din număr, deci numărul nu rămâne mai mare din cauza ei
				rest = (ok - self.ok) - self.native
				rest -= min(self.credit, max(0, rest))      # V5: repetarea și eliberarea tastei de pornire
				self.straine = max(0, self.straine + rest)
			self.credit = 0
		self.ok = ok
		self.native = 0
		return self.straine

	def _surse(self, date):
		self.protocoale = date.get('protocoale', [])
		contoare = date.get('contoare', {})
		self.disponibil = bool(contoare)
		if not contoare:
			self.baze = {}
			self.native = self.cadre_native = 0
			return None
		faze, cadre, straine = 0, 0, 0
		comune = set()
		for sursa, (numar, fel) in contoare.items():
			vechi = self.baze.get(sursa)
			if vechi is None or vechi[1] != fel or numar < vechi[0]:
				continue
			comune.add(fel)
			delta = numar - vechi[0]
			if fel == 'straine':
				straine += delta
			elif fel == 'cadre':
				cadre += delta
			elif fel == 'faze':
				faze += delta
		if comune:
			rest = 0
			if 'faze' in comune:
				rest += faze - self.native
			if 'cadre' in comune:
				rest += cadre - self.cadre_native
			rest -= min(self.credit, max(0, rest))
			self.credit = 0
			# Creditul tastei de pornire si corectiile fazelor proprii se aplica
			# estimarii; un contor explicit de cadre necunoscute nu se reduce.
			estimat = max(0, self.straine - self.straine_dovedite + rest)
			self.straine_dovedite += straine
			self.straine = self.straine_dovedite + estimat
		self.baze = dict(contoare)
		self.native = self.cadre_native = 0
		return self.straine

	def reia(self, credit=0):
		"""După o pauză fără captură (tastele receptorului din pauză nu s-au numărat): baza se ia din nou, numărul
		de până acum rămâne. `credit`: captura pornește din nou la o tastă a receptorului (V5)."""
		self.ok = None
		self.pornit_la = time.perf_counter()
		self.native = 0
		self.credit = credit
		self.baze = {}
		self.cadre_native = 0
		self.disponibil = None


class DetectorTinere(object):
	"""O tastă ținută: timpul de la apăsare până la ultima repetare a aceleiași taste, fără eliberare între ele."""

	def __init__(self):
		self.cheie = None
		self.inceput = 0
		self.consumata = False

	def primeste(self, ev):
		"""Întoarce durata în ms cât tasta e ținută (0 la apăsare sau eliberare)."""
		cheie = (ev['dispozitiv'], ev['cod'])
		if ev['fel'] == APASAT:
			self.cheie, self.inceput, self.consumata = cheie, ev['ms'], False
			return 0
		if ev['fel'] == ELIBERAT:
			if cheie == self.cheie:
				self.cheie = None
			return 0
		if cheie == self.cheie and ev['fel'] in (TINUT, LUNG):
			return max(0, ev['ms'] - self.inceput)
		return 0


# ------------------------------------------------------------------ asocierea, ca stare

class Asociere(object):
	"""Pașii asocierii unei telecomenzi USB, fără ecran (proiectul 2.4, cu revizia P10).

	1. Prima tastă de pe un dispozitiv străin alege telecomanda (a receptorului nu se poate asocia).
	2. Numele: cel al dispozitivului; se schimbă după aceea cu GALBEN = Redenumește (se poate face asocierea și
	   numai de pe telecomanda nouă, când a receptorului nu merge).
	3. Buton cu buton, în ORDINE_ASOCIERE. Codul deja folosit pentru alt buton: se cere apăsat încă o dată ca să fie
	   mutat (fără fereastră de întrebare, ca să se poată răspunde și de pe telecomanda nouă). O tastă ținută 2 s pe
	   telecomanda nouă = Sari; ținută 2 s tasta asociată deja cu EXIT = Gata, după butoanele de bază (de_baza_facute).
	Fiecare buton se scrie imediat (apelantul salvează după `schimbat`), deci o cădere nu pierde ce s-a făcut."""

	ALEGE, PAS, GATA = 'alege', 'pas', 'gata'

	def __init__(self, date):
		self.date = date
		self.stare = self.ALEGE
		self.ident = None
		self.dispozitiv = None
		self.index = 0
		self.sarite = set()
		self.asociate = set()
		self.mesaj = ''
		self.refacere = False      # telecomanda era deja asociată
		self.confirma = None       # (cod_sursa, cod_tinta_vechi) cât se așteaptă a doua apăsare
		self.schimbat = False
		self.tinere = DetectorTinere()
		self.apasat = None         # (cod, ms) al tastei apăsate pe telecomanda nouă, până la eliberare

	def buton_curent(self):
		if self.stare != self.PAS or self.index >= len(ORDINE_ASOCIERE):
			return None
		return DUPA_ID[ORDINE_ASOCIERE[self.index]]

	def de_baza_facute(self):
		"""Gata se poate după butoanele de bază: OK, săgețile și EXIT asociate, iar
		pasul MENU trecut (asociat sau sărit). POWER și MENU pot lipsi de pe o telecomandă mică; fără MENU asociat,
		tastele neasociate nu se opresc (opreste_neasociate), deci un MENU al ei, dacă îl are, merge mai departe."""
		for i in BUTOANE_NAVIGARE:
			if i not in self.asociate and not (i == 'menu' and self.index > INDEX_MENU):
				return False
		return True

	def lipsa_pentru_gata(self):
		"""Dupa pasul MENU, butoanele de baza care lipsesc ca sa se poata Gata (sarite: OK, sagetile, EXIT); inainte de
		pasul MENU, lista goala (Gata vine oricum abia dupa el)."""
		if self.stare != self.PAS or self.index <= INDEX_MENU:
			return []
		return [i for i in BUTOANE_NAVIGARE if i != 'menu' and i not in self.asociate]

	def _trece(self):
		self.index += 1
		self.confirma = None
		if self.index >= len(ORDINE_ASOCIERE):
			self.stare = self.GATA
			self.mesaj = 'gata'

	def primeste(self, ev):
		"""Un eveniment brut. Întoarce un cuvânt pentru ecran: 'nimic', 'propriu', 'ales', 'refacere', 'asociat',
		'confirma', 'sarit', 'gata', 'alt_dispozitiv'."""
		self.schimbat = False
		if ev is None or ev['fel'] == ASCII:
			return 'nimic'
		disp = ev['dispozitiv']
		if self.stare == self.ALEGE:
			if ev['fel'] != APASAT:
				return 'nimic'
			if e_dispozitiv_propriu(disp):
				self.mesaj = 'propriu'
				return 'propriu'
			vechi = gaseste_dispozitiv(self.date, disp)
			t = adauga_usb(self.date, disp)
			if t is None:
				return 'nimic'
			self.ident, self.dispozitiv = t['id'], disp
			self.refacere = vechi is not None and bool(vechi['taste'])
			if self.refacere:
				self.asociate = set(DUPA_COD[v][0] for v in t['taste'].values() if v in DUPA_COD)
			self.stare = self.PAS
			self.index = 0
			self.tinere.primeste(ev)
			self.tinere.consumata = True     # tasta care a ales telecomanda, ținută, nu sare primul buton
			self.schimbat = True
			return 'refacere' if self.refacere else 'ales'
		if self.stare != self.PAS:
			return 'nimic'
		if disp != self.dispozitiv:
			return 'alt_dispozitiv' if ev['fel'] == APASAT and not e_dispozitiv_propriu(disp) else 'nimic'
		# codul se ia la eliberare, ca o tastă ținută 2 s să poată însemna Sari fără să fi fost asociată înainte
		durata = self.tinere.primeste(ev)
		cod = ev['cod']
		if ev['fel'] == APASAT:
			self.apasat = (cod, ev['ms'])
			return 'nimic'
		if self.apasat is None or self.apasat[0] != cod:
			return 'nimic'
		if ev['fel'] in (TINUT, LUNG):
			if durata >= TINERE_SARI_MS and not self.tinere.consumata:
				self.tinere.consumata = True
				t = gaseste(self.date, self.ident)
				if t is not None and t['taste'].get(cod) == 174 and self.de_baza_facute():
					self.stare = self.GATA
					return 'gata'
				return self.sari()
			return 'nimic'
		if ev['fel'] != ELIBERAT:
			return 'nimic'
		inceput = self.apasat[1]
		self.apasat = None
		if self.tinere.consumata:
			return 'nimic'
		if ev['ms'] - inceput >= TINERE_SARI_MS:
			return self.sari()          # ținută fără repetări (dispozitiv fără EV_REP)
		b = self.buton_curent()
		if b is None:
			return 'nimic'
		if self.confirma is not None and self.confirma[0] == cod:
			return self._pune(cod, b, muta=True)
		t = gaseste(self.date, self.ident)
		vechi = t['taste'].get(cod) if t is not None else None
		if vechi is not None and vechi != b[2]:
			self.confirma = (cod, vechi)
			return 'confirma'
		return self._pune(cod, b, muta=False)

	def _pune(self, cod, b, muta):
		sterge_buton(self.date, self.ident, b[2])      # un buton refăcut pierde codurile de dinainte
		stare, detaliu = asociaza(self.date, self.ident, cod, b[2], muta=muta)
		if stare != 'ok':
			self.mesaj = str(detaliu)
			return 'nimic'
		if muta and self.confirma is not None:
			vechi = DUPA_COD.get(self.confirma[1])
			if vechi is not None:
				self.asociate.discard(vechi[0])
		self.asociate.add(b[0])
		self.sarite.discard(b[0])
		self.schimbat = True
		self._trece()
		return 'gata' if self.stare == self.GATA else 'asociat'

	def sari(self):
		b = self.buton_curent()
		if b is None:
			return 'nimic'
		self.sarite.add(b[0])
		self._trece()
		return 'gata' if self.stare == self.GATA else 'sarit'

	def inapoi(self):
		"""ROȘU: refaci butonul dinainte (codurile lui se scot)."""
		if self.stare == self.GATA:
			self.stare = self.PAS
			self.index = len(ORDINE_ASOCIERE)
		if self.stare != self.PAS or self.index == 0:
			return False
		self.index -= 1
		self.confirma = None
		b = self.buton_curent()
		if sterge_buton(self.date, self.ident, b[2]):
			self.schimbat = True
		self.asociate.discard(b[0])
		self.sarite.discard(b[0])
		return True

	def termina(self):
		"""VERDE: gata (după butoanele de bază)."""
		if self.stare == self.PAS and self.de_baza_facute():
			self.stare = self.GATA
			return True
		return False

	def rezumat(self):
		t = gaseste(self.date, self.ident) if self.ident else None
		n = len(set(t['taste'].values())) if t is not None else 0
		return n, NUMAR_BUTOANE - n


# ------------------------------------------------------------------ desenul

def incarca_desen(cale):
	"""telecomanda-viper.json, scris de scriptul de desen: {latime, inaltime, butoane: [{id, cod, x, y, w, h, forma,
	poligon | cerc}]}. Întoarce (latime, inaltime, {id: buton}) sau None; butoanele necunoscute se sar."""
	try:
		with open(cale, 'rb') as f:
			d = json.loads(f.read(512 * 1024).decode('utf-8'))
		latime, inaltime = int(d['latime']), int(d['inaltime'])
		butoane = {}
		for b in d['butoane']:
			ident = b.get('id')
			if ident not in DUPA_ID:
				continue
			r = {'id': ident, 'forma': str(b.get('forma', '')), 'x': float(b['x']), 'y': float(b['y']),
				'w': float(b['w']), 'h': float(b['h'])}
			if 'cerc' in b:
				cx, cy, raza = (float(v) for v in b['cerc'])
				r['cerc'] = (cx, cy, raza)
			pol = b.get('poligon')
			if isinstance(pol, list) and len(pol) >= 3:
				r['poligon'] = [(float(p[0]), float(p[1])) for p in pol[:256]]
			if 'cerc' not in r and 'poligon' not in r:
				continue
			butoane[ident] = r
		return latime, inaltime, butoane
	except (OSError, ValueError, KeyError, TypeError, IndexError):
		return None
