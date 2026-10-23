# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Indexul canalelor pentru cautarea din lista de canale (Screens/HdsCautareCanale.py).

Ce se citeste, ca text (enigma2 din 2011 nu da din Python CAID-urile si cache-ul unui serviciu):
  - lamedb (/etc/enigma2/lamedb, formatul 3 sau 4 scris de eDVBDB::saveServicelist): tipul serviciului, numele,
    furnizorul, CAID-urile (C:xxxx, din descriptorul CA_identifier al SDT la scanare), cache-ul (c:TTvvvv; 00 = PID
    video, 05 = tipul video) si steagurile (f:2 = ascuns); transponderul da pozitia orbitala sau cablu / terestru;
  - buchetele cu fluxuri: DVB-T2 din satelit (HdsT2mi, http://127.0.0.1:8889/t2/...), DAB+ din satelit (HdsDab,
    http://127.0.0.1:8898/dab/..., referintele vechi pe 8888) si orice alt flux (internet, inclusiv HdsDvbI);
  - masuratorile facute cand un canal a rulat: rezolutia exacta si codecul, din grupa vd a bazei unice
    (Components/HdsBazaCanale.py), prin masuratori() mai jos; clasa Masuratori citeste fisierul de dinainte (migrarea);
  - pistele fiecarui canal (limbile, formatul si canalele sunetului, subtitrarile, teletextul, HbbTV) din baza lui
    Components/HdsPisteCanale.py (randurile „Are”, „Format sunet”, „Sunet”, „Piste sunet”, „Limbă sunet”,
    „Subtitrare”), date ca trasaturi prin Index.aplica_piste; pentru formatul sunetului, la un canal fara piste stiute,
    si PID-ul de sunet tinut in lamedb (c:01 MPEG, c:04 AC3).

Regulile filtrelor: un grup fara nicio optiune aleasa nu filtreaza; in acelasi grup optiunile
sunt alternative (SAU); intre grupuri conditiile se aduna (SI). Accesul (FTA / criptat) si sistemul de criptare sunt
doua grupuri, ca „criptat + Nagravision" sa dea doar canalele Nagravision (in acelasi grup ar fi dat SAU).
Randurile pistelor: un canal fara piste stiute nu intra la niciun filtru de piste (in afara de teletextul
dovedit de c:02 din lamedb si de formatul sunetului din lamedb); daca in „Are” e ales numai felul subtitrarii (DVB
si/sau teletext) si e aleasa si o limba in „Subtitrare”, limba se cauta doar in felul ales („Subtitrari DVB + Romana” =
subtitrare DVB in romana).
Serviciile fara nume in SDT (numele facut la scanare, „12271H SID 0x200”, lib/dvb/scan.cpp) stau la coada listei si se
arata cu furnizorul transponderului, cand un alt canal de pe acelasi transponder il are (Canal.nume_afisat).

Nimic din enigma nu se importa aici: modulul se incarca si pe PC, in teste
(test_cautare_canale.py).
"""
import json
import os
import re

try:
	from Components import HdsFisierSigur as _S
except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
	import HdsFisierSigur as _S


def _(text):
	"""Traducerea imaginii (builtins._ pus de Components/Language.py); pe PC, in teste, textul asa cum e."""
	try:
		import builtins
		f = builtins.__dict__.get('_')
	except Exception:
		f = None
	if f is None or f is _:
		return text
	return f(text)


# ---------------------------------------------------------------- grupurile si optiunile

GRUPURI = ('tip', 'rez', 'acces', 'sistem', 'cod', 'poz', 'are', 'fsunet', 'msunet', 'psunet', 'lsunet', 'lsub')
# cate canale trec intre doua opriri ale lucrului in bucati (Index.aplica_treptat): pe PC sub 1 ms, pe receptor 5-15 ms
PAS_TREPTAT = 250
# randurile pistelor (HdsPisteCanale): se arata de la o singura optiune (un canal fara piste stiute nu intra, deci si o
# optiune singura filtreaza); celelalte randuri cer cel putin doua
GRUPURI_PISTE = ('are', 'fsunet', 'msunet', 'psunet', 'lsunet', 'lsub')
# randurile sunetului (formatul, mono / stereo / multicanal, numarul pistelor); cele ale imaginii, ascunse cand se cauta
# numai posturi de radio (vezi numai_radio)
GRUPURI_SUNET = ('fsunet', 'msunet', 'psunet')
GRUPURI_IMAGINE = ('rez', 'cod')
TIPURI_NUMAI_RADIO = frozenset(('radio', 'dab'))
# filtrele pe doua coloane (ecranul de cautare si pagina /cautare): in stanga grupurile cu optiuni putine si scurte, in
# dreapta cele cu multe optiuni; un grup care nu e aici merge in dreapta
COLOANA_STANGA = ('tip', 'rez', 'acces', 'cod', 'msunet', 'psunet')
COLOANA_DREAPTA = ('sistem', 'poz', 'are', 'fsunet', 'lsunet', 'lsub')
# cautarea dupa piste (randurile de mai sus si "Actualizeaza pistele"): "netestat" punea semnul "(netestat)" pe
# televizor (indiciul randurilor pistelor, titlul alegerii de la MENU) si in web (/cautare). Probata pe receptor:
# "Actualizeaza pistele" (2 transpondere, 3 canale citite) si filtrele pistelor (formatul sunetului, limba sunetului,
# limba subtitrarii: fiecare canal gasit are pista ceruta, pistele stiute la 8017 canale din 8836), deci fara semn.
# Un singur loc.
STARE_PISTE = None


def semnPiste(text):
	"""Textul cu semnul starii cautarii dupa piste (Components/HdsStareMeniu.py), sau textul asa cum e."""
	if not STARE_PISTE:
		return text
	try:
		from Components import HdsStareMeniu as S
	except ImportError:
		try:
			import HdsStareMeniu as S
		except ImportError:
			return text
	return S.cuSemn(text, STARE_PISTE, _)


TITLURI = {
	'tip': _('Tip'),
	'rez': _('Rezoluție'),
	'acces': _('Acces'),
	'sistem': _('Sistem'),
	'cod': _('Codare'),
	'poz': _('Poziție'),
	'are': _('Are'),
	'fsunet': _('Format sunet'),
	'msunet': _('Sunet'),
	'psunet': _('Piste sunet'),
	'lsunet': _('Limbă sunet'),
	'lsub': _('Subtitrare'),
}
OPTIUNI_FIXE = {
	'tip': (('tv', 'TV'), ('radio', 'Radio'), ('dab', 'DAB+'), ('t2', 'DVB-T2'), ('internet', _('Internet'))),
	'rez': (('sd', 'SD'), ('720', 'HD 720p'), ('1080', 'Full HD 1080'), ('4k', '4K')),
	'acces': (('fta', 'FTA'), ('criptat', _('Criptat'))),
	'cod': (('mpeg2', 'MPEG-2'), ('h264', 'H.264'), ('h265', 'H.265')),
	'are': (('ttx', _('Teletext')), ('subdvb', _('Subtitrări DVB')), ('subttx', _('Subtitrări teletext')), ('hbbtv', 'HbbTV')),
	# numele formatelor ca pe restul ecranelor imaginii (AC3+ pentru E-AC3, fara marci)
	'fsunet': (('mpeg', 'MPEG'), ('aac', 'AAC'), ('ac3', 'AC3'), ('eac3', 'AC3+'), ('dts', 'DTS'),
		('alt', _('Alt format'))),
	# „multi” = mai mult de doua canale (5.1 si altele): PMT-ul spune adesea numai „multicanal”, fara numarul exact
	'msunet': (('mono', _('Mono')), ('stereo', _('Stereo')), ('multi', _('5.1 (multicanal)'))),
	'psunet': (('1', '1'), ('2', '2'), ('3', _('3 sau mai multe'))),
}
# in titlul ecranului, o optiune aleasa se scrie cu randul ei („sunet Engleză”, „subtitrare Română”)
PREFIX_TITLU = {'lsunet': _('sunet %s'), 'lsub': _('subtitrare %s'), 'msunet': _('sunet %s'),
	'psunet': _('piste de sunet: %s')}
# textele cu _() de mai sus se traduc la incarcarea modulului, cand
# limba receptorului poate sa nu fie inca pusa (in emulator /cautare scria „Has” in loc de „Are”, pe un receptor in
# romana). De aceea se traduc din nou la folosire, prin titlu(), eticheta optiunilor si eticheta_titlu(); _() din
# dictionarele de sus ramane, ca textele sa fie gasite la extragerea traducerilor.
_MSGID_TITLU = {'tip': 'Tip', 'rez': 'Rezoluție', 'acces': 'Acces', 'sistem': 'Sistem', 'cod': 'Codare',
	'poz': 'Poziție', 'are': 'Are', 'fsunet': 'Format sunet', 'msunet': 'Sunet', 'psunet': 'Piste sunet',
	'lsunet': 'Limbă sunet', 'lsub': 'Subtitrare'}
_MSGID_OPTIUNI = {
	'tip': {'radio': 'Radio', 'internet': 'Internet'},
	'acces': {'criptat': 'Criptat'},
	'sistem': {'alt': 'Alt sistem'},
	'are': {'ttx': 'Teletext', 'subdvb': 'Subtitrări DVB', 'subttx': 'Subtitrări teletext'},
	'fsunet': {'alt': 'Alt format'},
	'msunet': {'mono': 'Mono', 'stereo': 'Stereo', 'multi': '5.1 (multicanal)'},
	'psunet': {'3': '3 sau mai multe'},
}
_MSGID_ARE = _MSGID_OPTIUNI['are']
_MSGID_PREFIX = {'lsunet': 'sunet %s', 'lsub': 'subtitrare %s', 'msunet': 'sunet %s', 'psunet': 'piste de sunet: %s'}


_ETICHETA_FORMAT = dict(OPTIUNI_FIXE['fsunet'])


def eticheta_format_sunet(canal):
	"""Formatele sunetului unui canal, pentru o coloana ingusta: „MPEG”, „MPEG/AC3”; „” cand nu se stiu."""
	fs = getattr(canal, 'fs', ())
	return '/'.join(_ETICHETA_FORMAT[v] if v != 'alt' else _('Alt format') for v, _e in OPTIUNI_FIXE['fsunet']
		if v in fs)


def eticheta_mod_sunet(canal):
	"""Cel mai bogat fel de sunet stiut al canalului: „multicanal”, „stereo”, „mono”, sau „”."""
	ms = getattr(canal, 'ms', ())
	for v, msgid in (('multi', 'multicanal'), ('stereo', 'stereo'), ('mono', 'mono')):
		if v in ms:
			return _(msgid)
	return ''


def numai_radio(selectie):
	"""Se cauta numai posturi de radio: in randul „Tip” sunt alese numai Radio si / sau DAB+. Atunci randurile imaginii
	(rezolutia, codarea video) nu au ce arata si se ascund."""
	tipuri = set((selectie or {}).get('tip') or ())
	return bool(tipuri) and tipuri <= TIPURI_NUMAI_RADIO


def titlu(g):
	"""Titlul randului `g`, tradus acum (in limba de acum a receptorului)."""
	m = _MSGID_TITLU.get(g)
	return _(m) if m else TITLURI[g]

# sistemele de criptare, in ordinea de pe ecran; intervalele sunt cele din registrul DVB, aceleasi ca in
# Components/Converter/HdsCommon.py (CAID_TABLE), unde bara de informatii da numele complet
SISTEME = (
	('irdeto', 'Irdeto', ((0x0600, 0x06FF),)),
	('nagra', 'Nagravision', ((0x1800, 0x18FF),)),
	('viaccess', 'Viaccess', ((0x0500, 0x05FF),)),
	('conax', 'Conax', ((0x0B00, 0x0BFF),)),
	('seca', 'Mediaguard', ((0x0100, 0x01FF),)),
	('cryptoworks', 'Cryptoworks', ((0x0D00, 0x0DFF),)),
	('nds', 'Videoguard', ((0x0900, 0x09FF),)),
	('powervu', 'PowerVu', ((0x0E00, 0x0EFF),)),
	('biss', 'BISS', ((0x2600, 0x26FF),)),
	('verimatrix', 'Verimatrix', ((0x5601, 0x5604),)),
)
SISTEM_ALT = ('alt', _('Alt sistem'))
_NUME_SISTEM = dict((s[0], s[1]) for s in SISTEME)
_NUME_SISTEM[SISTEM_ALT[0]] = SISTEM_ALT[1]

# tipurile de serviciu (EN 300 468, tabelul 87) cunoscute de lista de canale; restul (date, NVOD, mozaic) nu se arata
TIPURI_TV = frozenset((0x01, 0x11, 0x16, 0x19, 0x1F, 0x20, 0x86, 0xC3))
TIPURI_RADIO = frozenset((0x02, 0x0A))
# rezerva pentru un canal inca neprivit: rezolutiile posibile dupa tipul declarat. HD (0x11, 0x19) nu spune 720p sau
# 1080, deci intra la amandoua. Tipul 0x1F inseamna DOAR codare noua (H.265), nu rezolutie: cele mai multe canale
# declarate asa sunt 1080, deci 0x1F ramane HD (altfel multe canale H.265 ar aparea ca 4K fara sa fie). 4K ramane
# pentru tipul 0x20, pentru numele care o spun singure (vezi
# rez_din_tip_si_nume) si pentru inaltimea masurata la vizionare (categorie_rezolutie). 0x86 si 0xC3 nu spun nimic.
REZ_DIN_TIP = {0x01: ('sd',), 0x16: ('sd',), 0x11: ('720', '1080'), 0x19: ('720', '1080'),
	0x1F: ('1080',), 0x20: ('4k',)}
ETICHETA_REZ_DIN_TIP = {0x01: 'SD', 0x16: 'SD', 0x11: 'HD', 0x19: 'HD', 0x1F: 'HD', 0x20: '4K'}
# numele care spun singure ca e ultra: „UHD" sau „4K" ca si cuvant intreg (nu prinde „H4K1" sau „uhdtv24")
_NUME_ULTRA = re.compile(r'(?<![0-9a-z])(4k|uhd)(?![0-9a-z])', re.I)
COD_DIN_TIP = {0x01: 'mpeg2', 0x11: 'mpeg2', 0x16: 'h264', 0x19: 'h264', 0x1F: 'h265', 0x20: 'h265'}
# c:05 (cVTYPE) din lamedb: numerotarea din lib/dvb/decoder.h, aceeasi in lamedb-urile importate de pe alte receptoare:
# 1 H.264, 3 VC-1, 4 MPEG-4 p2, 5 VC-1 SM, 6 MPEG-1, 7 H.265; MPEG-2 nu se scrie (-1). Un lamedb scris de o versiune
# mai veche a nucleului avea 2 MPEG-1, 3 MPEG-4 p2, 4 VC-1: toate „alt" oricum.
# PID-ul pistei de sunet alese, in intrarea formatului ei (lib/dvb/db.cpp, setCachedAudio): c:01 MPEG, c:04 AC3,
# c:12 HE-AAC, c:13 DD+ (AC3+), c:14 DTS, c:15 AAC, c:16 LPCM (alt format), c:17 DTS-HD (cu DTS)
FORMAT_DIN_CACHE = {1: 'mpeg', 4: 'ac3', 12: 'aac', 13: 'eac3', 14: 'dts', 15: 'aac', 16: 'alt', 17: 'dts'}
COD_DIN_VTYPE = {1: 'h264', 7: 'h265'}
# iServiceInformation.sVideoType (tipul fluxului video din PMT), aceeasi numerotare: 0 MPEG-2, 1 H.264, 7 H.265
COD_DIN_SVIDEOTYPE = {0: 'mpeg2', 1: 'h264', 7: 'h265'}
ETICHETA_COD = {'mpeg2': 'MPEG-2', 'h264': 'H.264', 'h265': 'H.265'}

ETICHETA_TIP = {'tv': '', 'radio': 'Radio', 'dab': 'DAB+', 't2': 'DVB-T2', 'internet': 'Internet'}
_MSGID_TIP = {'radio': 'Radio', 'internet': 'Internet'}


def eticheta_tip(tip):
	"""Felul canalului in coloana rezultatelor („Radio”, „DAB+”, „DVB-T2”, „Internet”; nimic la TV), tradus acum."""
	e = ETICHETA_TIP.get(tip, '')
	return _(_MSGID_TIP[tip]) if tip in _MSGID_TIP else e

FURNIZORI_PURTATORI = ('HDSatelit T2-MI', 'HDSatelit ETI')   # serviciile purtatoare ale HdsT2mi / HdsDab
DX_DONTSHOW = 2

POZ_CABLU = 'cablu'
POZ_TERESTRU = 'terestru'

DIRECTOR = '/etc/enigma2'
CALE_MASURATORI = '/etc/enigma2/hds_masuratori_canale.json'


# ---------------------------------------------------------------- texte

def _forma_ro(unu, multe, n):
	"""Fara Components/HdsPlural (modulul incarcat singur): pluralul din catalogul instalat de enigma2, daca e; altfel
	forma romaneasca (msgid-urile sunt in romana): unu pentru n == 1, altfel multe, fara "de" ("20 canale")."""
	try:
		import builtins
		f = getattr(getattr(builtins.__dict__.get("_"), "__self__", None), "ngettext", None)
		if f is not None:
			return f(unu, multe, n)
	except Exception:
		pass
	return unu if n == 1 else multe


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components/HdsPlural.ngettext: formele din Plural-Forms ale limbii, intors ca Forma, al carei %
	merge si cand forma pentru 1 n-are numarul, ca "un canal" din ro.po). Fara pachetul Components (probele de pe PC),
	forma romaneasca de mai sus. Numele e cel stiut de xgettext."""
	try:
		from Components.HdsPlural import ngettext as plural
	except ImportError:
		return _forma_ro(unu, multe, n)
	return plural(unu, multe, n)


def text_numar(n):
	"""Niciun canal, un canal, 5 canale, 128 canale (in ro.po singularul cu litere si pluralul fara "de")."""
	if n <= 0:
		return _('Niciun canal')
	return ngettext('%d canal', '%d canale', n) % n


def text_pozitie(poz):
	if poz == POZ_CABLU:
		return _('Cablu')
	if poz == POZ_TERESTRU:
		return _('Terestru')
	if not isinstance(poz, int):
		return ''
	# ca in bara de informatii si in scaner: literele si separatorul zecimal ale limbii meniului (Components/HdsGrade.py)
	try:
		from Components.HdsGrade import pozitieOrbitala
	except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
		from HdsGrade import pozitieOrbitala
	return pozitieOrbitala(poz)


def _cheie_ordine_poz(poz):
	"""Sateliti de la est la vest, apoi cablu, apoi terestru."""
	if poz == POZ_CABLU:
		return (1, 0)
	if poz == POZ_TERESTRU:
		return (2, 0)
	semn = poz if poz <= 1800 else poz - 3600
	return (0, -semn)


# ---------------------------------------------------------------- nume fara diacritice

_TABEL = {}
for _litere, _inlocuire in (
		(u'ăâàáäãåāąă', 'a'), (u'çćčĉ', 'c'), (u'ďđ', 'd'), (u'èéêëěēęėĕ', 'e'), (u'ğĝ', 'g'), (u'ĥ', 'h'),
		(u'ìíîïīįı', 'i'), (u'ĵ', 'j'), (u'ķ', 'k'), (u'ľĺłļ', 'l'), (u'ñńňņ', 'n'), (u'òóôöõøőō', 'o'),
		(u'řŕ', 'r'), (u'șşśšŝ', 's'), (u'țţťŧ', 't'), (u'ùúûüůűūųŭ', 'u'), (u'ýÿ', 'y'), (u'žźż', 'z')):
	for _l in _litere:
		_TABEL[ord(_l)] = _inlocuire
_TABEL[ord(u'ß')] = 'ss'
_TABEL[ord(u'æ')] = 'ae'
_TABEL[ord(u'œ')] = 'oe'


_NU_LITERA = re.compile(r'[\W_]+', re.UNICODE)


def _simplu(text):
	t = (text or '').lower()
	# un nume numai cu litere ASCII (cele mai multe) nu are ce inlocui: translate e partea cea mai scumpa la citirea
	# lamedb-ului (o data pe fiecare canal)
	if _ascii(t):
		return t
	return t.translate(_TABEL)


def _ascii(t):
	try:
		return t.isascii()
	except AttributeError:          # Python fara str.isascii
		return False


def normalizeaza(text):
	"""Numele pentru comparare: litere mici, fara diacritice, doar litere si cifre („Pro TV" -> „protv")."""
	return _NU_LITERA.sub('', _simplu(text))


def cuvinte(text):
	return [c for c in _NU_LITERA.split(_simplu(text)) if c]


# ---------------------------------------------------------------- CAID-uri si referinte

def sistem_caid(caid):
	for cheie, _nume, intervale in SISTEME:
		for lo, hi in intervale:
			if lo <= caid <= hi:
				return cheie
	return SISTEM_ALT[0]


def cheie_din_ref(ref):
	"""Cheia unui serviciu, aceeasi din lamedb, din buchet si din referinta care ruleaza.
	DVB fara cale: „sid:ns:tsid:onid" (hex, litere mici, fara tipul serviciului); flux: primele 11 campuri."""
	if not ref:
		return None
	parti = ref.split(':')
	if len(parti) < 10:
		return None
	try:
		campuri = [int(parti[0]), int(parti[1])] + [int(p or '0', 16) for p in parti[2:10]]
	except ValueError:
		return None
	cale = parti[10] if len(parti) > 10 else ''
	if not cale and campuri[0] == 1 and not (campuri[1] & 7):
		return '%x:%x:%x:%x' % (campuri[3], campuri[6], campuri[4], campuri[5])
	if not cale:
		return None
	return '%d:%d:%x:%x:%x:%x:%x:%x:%x:%x:' % tuple(campuri) + cale.lower().replace('%3A', '%3a').replace(':', '%3a')


# prefixele marcajelor ansamblurilor din buchetele DAB+ / DVB-T2 din satelit (Hds/DabT2/buchete.PREFIX_MARCAJ)
PREFIXE_MARCAJ = ('MUX DAB+: ', 'MUX DVB-T2: ')


def ansamblu_din_marcaj(text):
	"""„MUX DAB+: DR Deutschland” -> „DR Deutschland” (numele ansamblului, pentru cautare si semnele randului); un
	marcaj fara prefix ramane intreg."""
	text = (text or '').strip()
	for prefix in PREFIXE_MARCAJ:
		if text.startswith(prefix):
			return text[len(prefix):].strip()
	return text


def _feed_din_url(cale, marcaj):
	"""„http%3a//127.0.0.1%3a8889/t2/<feed>/<plp>" -> feed."""
	cale = cale.replace('%3a', ':').replace('%3A', ':')
	if marcaj not in cale:
		return None
	rest = cale.split(marcaj, 1)[1]
	return rest.split('/', 1)[0] or None


# ---------------------------------------------------------------- canalul

_GOL = frozenset()
_ARE_TTX = frozenset(('ttx',))

# cuvintele dupa care se gasesc si fluxurile noastre (normalizate: „DAB+” -> „dab”, „DVB-T2” -> „dvbt2”), pe langa
# numele postului si numele ansamblului (marcajul buchetului); vezi cuvinte_flux si Canal.rang
CUVINTE_FEL = {'dab': ('dab', 'dabplus'), 't2': ('dvbt2', 't2')}


def cuvinte_flux(tip, ansamblu=''):
	"""Textele in plus in care se cauta un post DAB/T2: felul, apoi ansamblul intreg si de la fiecare cuvant al lui
	(„DR Deutschland” se gaseste si cu „deutsch”). Normalizate ca numele. () pentru restul canalelor."""
	rez = list(CUVINTE_FEL.get(tip, ()))
	if ansamblu:
		cuv = cuvinte(ansamblu)
		for i in range(len(cuv)):
			s = ''.join(cuv[i:])
			if s and s not in rez:
				rez.append(s)
	return tuple(rez)

class Canal(object):
	__slots__ = ('nume', 'cheie', 'sufixe', 'ref', 'cheie_mas', 'tip', 'stype', 'poz', 'sisteme', 'acces',
		'rez_baza', 'rez_eticheta_baza', 'cod_baza', 'cod_sigur_baza', 'rez', 'rez_eticheta', 'cod', 'cod_sigur',
		'masti', 'buchet', 'radio', 'ttx_lamedb', 'are', 'ls', 'lsd', 'lst', 'm_lsd', 'm_lst', 'stiut',
		'furnizor', 'fara_nume', 'fs_lamedb', 'fs', 'ms', 'np', 'ansamblu', 'alte', 'tp')

	def __init__(self, nume, ref, cheie_mas, tip, stype=0, poz=None, sisteme=(), acces=None, rez=(), rez_eticheta='',
			cod='', cod_sigur=False, buchet=None, radio=False, ttx_lamedb=False, furnizor='', fara_nume=False,
			fs_lamedb=(), ansamblu='', tp=''):
		self.nume = nume
		self.ansamblu = ansamblu            # DAB/T2: numele ansamblului (marcajul din buchet), altfel ''
		# felul si ansamblul, normalizate (Canal.rang); fara apel pentru canalele din lamedb (cate unul pe fiecare)
		self.alte = cuvinte_flux(tip, ansamblu) if tip in CUVINTE_FEL else ()
		self.furnizor = furnizor
		self.tp = tp                        # transponderul pentru om ("11538 H"), din lamedb
		self.fara_nume = fara_nume          # numele facut la scanare („12271H SID 0x200”), vezi nume_afisat
		self.cheie = normalizeaza(furnizor + ' ' + nume if fara_nume and furnizor else nume)   # ca text_cautat()
		self.sufixe = None                  # se calculeaza la prima ordonare dupa text (rang)
		self.ref = ref
		self.cheie_mas = cheie_mas
		self.tip = tip
		self.stype = stype
		self.poz = poz
		self.sisteme = tuple(sisteme)
		self.acces = acces                  # 'fta', 'criptat' sau None (nu se stie)
		self.rez_baza = tuple(rez)
		self.rez_eticheta_baza = rez_eticheta
		self.cod_baza = cod
		self.cod_sigur_baza = cod_sigur
		self.rez = self.rez_baza
		self.rez_eticheta = rez_eticheta
		self.cod = cod
		self.cod_sigur = cod_sigur
		self.masti = None
		self.buchet = buchet                # buchetul din care vine un flux (pentru pozitionarea listei la pornire)
		self.radio = radio
		self.ttx_lamedb = ttx_lamedb        # c:02 (cTPID) in lamedb: canalul are teletext (servicedvb.cpp 2580)
		self.fs_lamedb = frozenset(fs_lamedb) if fs_lamedb else _GOL   # formatul sunetului din lamedb (FORMAT_DIN_CACHE)
		self.m_lsd = self.m_lst = 0
		# ce face aplica_piste(None), fara apelul de metoda (o data pe fiecare canal din lamedb)
		self.stiut = False
		self.fs, self.ms, self.np = self.fs_lamedb, _GOL, None
		self.are = _ARE_TTX if ttx_lamedb else _GOL
		self.ls = self.lsd = self.lst = ()

	def text_cautat(self):
		"""Textul in care se cauta numele: numele; la un serviciu fara nume, si furnizorul („ert” il gaseste)."""
		if self.fara_nume and self.furnizor:
			return self.furnizor + ' ' + self.nume
		return self.nume

	def nume_afisat(self):
		"""Numele de aratat: numele; la un serviciu fara nume „Fără nume · ERT · 12271H SID 0x200” (furnizorul numai
		cand se stie), ca sa nu para un nume adevarat."""
		if not self.fara_nume:
			return self.nume
		parti = [_('Fără nume')]
		if self.furnizor:
			parti.append(self.furnizor)
		parti.append(self.nume)
		return u' · '.join(parti)

	def rang(self, q):
		"""0: numele incepe cu textul, 1: un cuvant incepe cu textul (sau felul / ansamblul unui post DAB-T2), 2: textul
		e in mijlocul numelui, 3: textul e numai in mijlocul felului sau al ansamblului. None: nu se potriveste deloc."""
		if self.cheie.startswith(q):
			return 0
		in_nume = q in self.cheie
		if in_nume:
			if self.sufixe is None:
				cuv = cuvinte(self.text_cautat())
				self.sufixe = tuple(''.join(cuv[i:]) for i in range(1, len(cuv)))
			for s in self.sufixe:
				if s.startswith(q):
					return 1
		for a in self.alte:
			if a.startswith(q):
				return 1
		if in_nume:
			return 2
		for a in self.alte:
			if q in a:
				return 3
		return None

	def se_potriveste(self, q):
		"""Textul cautat (normalizat) e in nume, in felul sau in ansamblul postului."""
		if q in self.cheie:
			return True
		for a in self.alte:
			if q in a:
				return True
		return False

	def eticheta_acces(self):
		if self.acces == 'fta':
			return 'FTA'
		if self.acces == 'criptat':
			if not self.sisteme:
				return _('Criptat')
			nume = [_(_MSGID_OPTIUNI['sistem'][s]) if s in _MSGID_OPTIUNI['sistem'] else _NUME_SISTEM.get(s, s)
				for s in self.sisteme]
			if len(nume) > 2:
				return '%s +%d' % (nume[0], len(nume) - 1)
			return '/'.join(nume)
		return ''

	def eticheta_cod(self):
		return ETICHETA_COD.get(self.cod, '')

	def eticheta_pozitie(self):
		if self.tip == 'internet' and self.poz is None:
			return 'Internet'
		return text_pozitie(self.poz)

	def aplica_masurare(self, masurare):
		"""masurare = [inaltime, progresiv (1/0/-1), cod] sau None (inapoi la ce spune lamedb)."""
		self.rez, self.rez_eticheta = self.rez_baza, self.rez_eticheta_baza
		self.cod, self.cod_sigur = self.cod_baza, self.cod_sigur_baza
		if not masurare:
			return
		try:
			inaltime, progresiv, cod = int(masurare[0]), int(masurare[1]), masurare[2]
		except (TypeError, ValueError, IndexError):
			return
		if inaltime > 0:
			categorie, linii = categorie_rezolutie(inaltime)
			self.rez = (categorie,)
			self.rez_eticheta = '%d%s' % (linii, {1: 'p', 0: 'i'}.get(progresiv, ''))
		if cod in ETICHETA_COD:
			self.cod, self.cod_sigur = cod, True

	def aplica_piste(self, trasaturi):
		"""trasaturi = HdsPisteCanale.trasaturi(inregistrare): (optiunile „Are”, teletextul e stiut, limbile sunetului,
		limbile subtitrarilor DVB, limbile paginilor de subtitrare teletext[, (formatele sunetului, mono / stereo /
		multi, numarul pistelor de sunet sau None)]); None = canal fara piste stiute. Formatul sunetului: din piste,
		altfel din lamedb (fs_lamedb)."""
		self.stiut = bool(trasaturi)       # canalul are o inregistrare in baza pistelor
		self.fs, self.ms, self.np = self.fs_lamedb, _GOL, None
		if not trasaturi:
			self.are = _ARE_TTX if self.ttx_lamedb else _GOL
			self.ls = self.lsd = self.lst = ()
			return
		are, tt_stiut, ls, lsd, lst = trasaturi[:5]
		are = set(are)
		if not tt_stiut and self.ttx_lamedb:
			are.add('ttx')
		self.are = frozenset(are)
		self.ls, self.lsd, self.lst = tuple(ls), tuple(lsd), tuple(lst)
		if len(trasaturi) > 5 and trasaturi[5]:
			fs, ms, np = trasaturi[5]
			if fs:
				self.fs = frozenset(fs)
			self.ms = frozenset(ms)
			self.np = np if isinstance(np, int) and np > 0 else None


def rez_din_tip_si_nume(stype, nume):
	"""Rezolutiile posibile si eticheta pentru un canal inca neprivit.
	Un canal cu tipul 0x1F al carui nume spune UHD sau 4K intra si la 4K, fiindca unii emitatori trimit ultra pe
	tipul de HD; restul canalelor 0x1F raman HD pana cand inaltimea se masoara la vizionare."""
	rez, et = REZ_DIN_TIP.get(stype, ()), ETICHETA_REZ_DIN_TIP.get(stype, '')
	if stype == 0x1F and nume and _NUME_ULTRA.search(nume):
		return ('1080', '4k'), 'HD/4K'
	return rez, et


def categorie_rezolutie(inaltime):
	"""Inaltimea masurata -> (categoria filtrului, liniile de afisat)."""
	if inaltime >= 1500:
		return '4k', 2160
	if inaltime >= 900:
		return '1080', 1080
	if inaltime >= 650:
		return '720', 720
	return 'sd', 576 if inaltime > 480 else inaltime


# ---------------------------------------------------------------- lamedb

# polarizarea din randul transponderului de satelit (lamedb: 0 orizontala, 1 verticala, 2 circulara stanga, 3 dreapta)
_POLARIZARE = {0: 'H', 1: 'V', 2: 'L', 3: 'R'}


def text_transponder(date):
	"""Randul transponderului din lamedb -> transponderul pentru om: "11538 H" (satelit: frecventa in MHz si
	polarizarea), "346 MHz" (cablu: frecventa in kHz in lamedb; terestru: in Hz); "" cand randul nu se intelege."""
	try:
		if date.startswith('s '):
			c = date[2:].split(':')
			return ('%d %s' % ((int(c[0]) + 500) // 1000, _POLARIZARE.get(int(c[2]), ''))).strip()
		if date.startswith('c '):
			return '%d MHz' % ((int(date[2:].split(':')[0]) + 500) // 1000)
		if date.startswith('t '):
			return '%d MHz' % ((int(date[2:].split(':')[0]) + 500000) // 1000000)
	except (ValueError, IndexError):
		pass
	return ''


def citeste_lamedb(text):
	"""Textul lamedb -> lista de Canal. Un fisier care nu se intelege da lista goala (nu ridica)."""
	randuri = text.split('\n')
	if not randuri or not randuri[0].startswith('eDVB services /'):
		return []
	n = len(randuri)
	i = 1
	if i >= n or randuri[i].strip() != 'transponders':
		return []
	i += 1
	transpondere, frecvente = {}, {}
	while i < n and randuri[i].strip() != 'end':
		cheie = randuri[i].strip().lower()
		date = randuri[i + 1].strip() if i + 1 < n else ''
		poz = None
		if date.startswith('s '):
			try:
				poz = int(date[2:].split(':')[4])
				if poz < 0:
					poz += 3600
			except (ValueError, IndexError):
				poz = None
		elif date.startswith('c '):
			poz = POZ_CABLU
		elif date.startswith('t '):
			poz = POZ_TERESTRU
		transpondere[_cheie_tp(cheie)] = poz
		frecvente[_cheie_tp(cheie)] = text_transponder(date)
		# blocul se incheie cu „/"; sarim pana la el (un rand in plus nu strica citirea)
		i += 1
		while i < n and randuri[i].strip() != '/' and randuri[i].strip() != 'end':
			i += 1
		if i < n and randuri[i].strip() == '/':
			i += 1
	i += 1
	if i >= n or randuri[i].strip() != 'services':
		return []
	i += 1
	canale = []
	while i + 2 < n and randuri[i].strip() != 'end':
		cheie, nume, date = randuri[i].strip(), randuri[i + 1].rstrip('\r'), randuri[i + 2].rstrip('\r')
		i += 3
		c = _canal_lamedb(cheie, nume, date, transpondere, frecvente)
		if c is not None:
			canale.append(c)
	furnizori_pe_transponder(canale)
	return canale


def _cheie_tp(cheie):
	parti = cheie.split(':')
	try:
		return (int(parti[0], 16), int(parti[1], 16), int(parti[2], 16))
	except (ValueError, IndexError):
		return None


def _canal_lamedb(cheie, nume, date, transpondere, frecvente=None):
	parti = cheie.split(':')
	if len(parti) < 6:
		return None
	try:
		sid, ns, tsid, onid = int(parti[0], 16), int(parti[1], 16), int(parti[2], 16), int(parti[3], 16)
		stype = int(parti[4])
	except ValueError:
		return None
	if stype in TIPURI_RADIO:
		tip = 'radio'
	elif stype in TIPURI_TV:
		tip = 'tv'
	else:
		return None
	if not nume.strip():
		return None
	furnizor, caids, steaguri, vpid, vtype, tpid = '', [], 0, None, None, None
	formate = set()
	if len(date) > 1 and date[1] == ':':
		for camp in date.split(','):
			if len(camp) < 2 or camp[1] != ':':
				continue
			litera, valoare = camp[0], camp[2:]
			try:
				if litera == 'p':
					furnizor = valoare
				elif litera == 'C':
					caids.append(int(valoare, 16))
				elif litera == 'c':
					idx, val = int(valoare[:2]), int(valoare[2:], 16)
					if idx == 0:
						vpid = val
					elif idx == 2:
						tpid = val
					elif idx == 5:
						vtype = val
					elif idx in FORMAT_DIN_CACHE:
						formate.add(FORMAT_DIN_CACHE[idx])
				elif litera == 'f':
					steaguri = int(valoare, 16)
			except ValueError:
				continue
	else:
		furnizor = date
	if steaguri & DX_DONTSHOW or furnizor in FURNIZORI_PURTATORI:
		return None
	poz = transpondere.get((ns, tsid, onid))
	if poz is None:
		sus = ns >> 16
		if sus == 0xFFFF:
			poz = POZ_CABLU
		elif sus == 0xEEEE:
			poz = POZ_TERESTRU
		elif 0 < sus < 3600:
			poz = sus
	sisteme = []
	for caid in caids:
		s = sistem_caid(caid)
		if s not in sisteme:
			sisteme.append(s)
	if sisteme:
		sisteme = [s[0] for s in SISTEME if s[0] in sisteme] + ([SISTEM_ALT[0]] if SISTEM_ALT[0] in sisteme else [])
	if tip == 'radio':
		rez, rez_et, cod, sigur = (), '', '', False
	else:
		rez, rez_et = rez_din_tip_si_nume(stype, nume)
		declarat = COD_DIN_TIP.get(stype, '')
		if vtype is not None:
			cod, sigur = COD_DIN_VTYPE.get(vtype, 'alt'), True
		elif vpid is not None and declarat not in ('h264', 'h265'):
			cod, sigur = 'mpeg2', True
		else:
			# PID video fara tip pe un serviciu declarat H.264/H.265: nu e dovada de MPEG-2 (un program care nu
			# stie HEVC scrie PID-ul si lasa tipul gol, vazut in lamedb-ul emulatorului la tipul 0x1F)
			cod, sigur = declarat, False
	ref = '1:0:%X:%X:%X:%X:%X:0:0:0:' % (stype, sid, tsid, onid, ns)
	nume = nume.strip()
	fara_nume = ' SID 0x' in nume and _NUME_SCANARE.match(nume) is not None
	if furnizor.startswith('DVB-') and _FURNIZOR_SCANARE.match(furnizor):
		furnizor = ''
	return Canal(nume, ref, '%x:%x:%x:%x' % (sid, ns, tsid, onid), tip, stype, poz, sisteme,
		'criptat' if caids else 'fta', rez, rez_et, cod, sigur, radio=(tip == 'radio'), ttx_lamedb=tpid is not None,
		furnizor=furnizor, fara_nume=fara_nume, fs_lamedb=formate,
		tp=(frecvente or {}).get((ns, tsid, onid), ''))


# numele si furnizorul facute la scanare pentru un serviciu gasit numai in PAT, fara SDT (lib/dvb/scan.cpp):
# „12271H SID 0x200” (satelit), „474000 SID 0x1” (cablu, terestru); furnizorul „DVB-S2 8PSK 12271H 39.0°E” sau gol
_NUME_SCANARE = re.compile(r'^\d+[HV]? SID 0x[0-9a-fA-F]+$')
_FURNIZOR_SCANARE = re.compile(r'^DVB-[SCT]2? ')


def furnizori_pe_transponder(canale):
	"""Serviciile fara nume, fara furnizor adevarat, primesc furnizorul cel mai des intalnit la canalele cu nume de pe
	acelasi transponder (aceeasi cheie ns:tsid:onid). Schimba canalele pe loc."""
	fara = [c for c in canale if c.fara_nume and not c.furnizor and c.cheie_mas]
	if not fara:
		return
	pe_tp = dict((c.cheie_mas[c.cheie_mas.find(':') + 1:], {}) for c in fara)
	for c in canale:
		if c.furnizor and not c.fara_nume and c.cheie_mas:
			d = pe_tp.get(c.cheie_mas[c.cheie_mas.find(':') + 1:])
			if d is not None:
				d[c.furnizor] = d.get(c.furnizor, 0) + 1
	for c in fara:
		d = pe_tp[c.cheie_mas[c.cheie_mas.find(':') + 1:]]
		if d:
			c.furnizor = sorted(d.items(), key=lambda x: (-x[1], x[0]))[0][0]
			c.cheie = normalizeaza(c.text_cautat())
			c.sufixe = None


# ---------------------------------------------------------------- randurile care arata la fel

def _transponder_canal(c):
	"""Transponderul unui canal DVB (spatiul de nume, TSID si ONID din cheia lui); la un flux, referinta lui."""
	k = c.cheie_mas
	return k[k.find(':') + 1:] if k else c.ref


def _sid_canal(c):
	if not c.cheie_mas:
		return None
	try:
		return int(c.cheie_mas.split(':', 1)[0], 16)
	except ValueError:
		return None


def _imparte(lista, cheie):
	"""Lista impartita dupa cheie, in ordinea primei aparitii a fiecarei chei."""
	grupe, ordine = {}, []
	for x in lista:
		k = cheie(x)
		if k not in grupe:
			grupe[k] = []
			ordine.append(k)
		grupe[k].append(x)
	return [grupe[k] for k in ordine]


def _texte_deosebire(canale):
	"""Canale diferite care arata la fel -> {id(canal): [bucatile care il deosebesc]}: pozitia, cand difera; intre cele
	de pe aceeasi pozitie, transponderul (frecventa si polarizarea), cand difera; intre cele de pe acelasi transponder,
	furnizorul, cand fiecare il are pe al lui, altfel SID-ul (acelasi pe toate listele si pe siturile cu sateliti)."""
	rez = dict((id(c), []) for c in canale)
	pe_poz = _imparte(canale, lambda c: c.poz)
	for l1 in pe_poz:
		if len(pe_poz) > 1:
			for c in l1:
				t = c.eticheta_pozitie()
				if t:
					rez[id(c)].append(t)
		if len(l1) < 2:
			continue
		pe_tp = _imparte(l1, _transponder_canal)
		for l2 in pe_tp:
			if len(pe_tp) > 1:
				for c in l2:
					if c.tp:
						rez[id(c)].append(c.tp)
			if len(l2) < 2:
				continue
			furnizori = [c.furnizor for c in l2]
			if all(furnizori) and len(set(furnizori)) == len(furnizori):
				for c in l2:
					rez[id(c)].append(c.furnizor)
				continue
			for c in l2:
				sid = _sid_canal(c)
				if sid is not None:
					rez[id(c)].append('SID %d' % sid)
	return rez


def deosebiri_treptat(elemente, nume=None, vizibil=None, canal=None, pas=None):
	"""Ce deosebeste randurile care altfel arata la fel (acelasi nume, aceleasi semne), ca omul sa stie care e care.
	elemente: randurile, in ordinea de pe ecran; nume(e): cheia ieftina a numelui (implicit Canal.cheie); vizibil(e): tot
	ce arata randul, ca tuplu (cerut numai pentru numele care apar de cel putin doua ori; implicit numele afisat si
	pozitia); canal(e): Canal-ul randului, sau None pentru un rand fara canal (implicit chiar e). Acelasi canal de doua
	ori in lista nu are ce deosebi. Generator: un yield la fiecare `pas` randuri. -> {id(e): text}, numai pentru randurile
	dintr-un grup de cel putin doua canale diferite (bucatile din _texte_deosebire, cu " · " intre ele)."""
	nume = nume or (lambda c: c.cheie)
	vizibil = vizibil or (lambda c: (c.nume_afisat(), c.poz))
	canal = canal or (lambda c: c)
	pas = pas or PAS_TREPTAT
	pe_nume = {}
	for i, e in enumerate(elemente):
		if canal(e) is not None:
			pe_nume.setdefault(nume(e), []).append(e)
		if i % pas == pas - 1:
			yield
	rez = {}
	facute = 0
	for lista in pe_nume.values():
		if len(lista) < 2:
			continue
		for grup in _imparte(lista, vizibil):
			unice, vazute = [], set()
			for e in grup:
				c = canal(e)
				if id(c) not in vazute:
					vazute.add(id(c))
					unice.append(c)
			if len(unice) < 2:
				continue
			texte = _texte_deosebire(unice)
			for e in grup:
				t = u' · '.join(texte[id(canal(e))])
				if t:
					rez[id(e)] = t
		facute += len(lista)
		if facute >= pas:
			facute = 0
			yield
	return rez


def deosebiri(elemente, nume=None, vizibil=None, canal=None):
	"""deosebiri_treptat dintr-o bucata."""
	gen = deosebiri_treptat(elemente, nume, vizibil, canal)
	while True:
		try:
			next(gen)
		except StopIteration as gata:
			return gata.value


# ---------------------------------------------------------------- buchetele

# releul DAB+ asculta pe 8898 (Hds/DabT2/profil.py, DAB.port); referintele scrise inainte pe 8888 (porturi_vechi)
# raman posturi DAB+ pana cand buchetul se reface
MARCAJ_DAB = '127.0.0.1:8898/dab/'
MARCAJE_DAB = (MARCAJ_DAB, '127.0.0.1:8888/dab/')
MARCAJ_T2 = '127.0.0.1:8889/t2/'


def _marcaj_dab(cale_simpla):
	"""Marcajul DAB+ gasit in cale (portul de acum sau cel vechi), altfel None."""
	for m in MARCAJE_DAB:
		if m in cale_simpla:
			return m
	return None


def fisiere_buchete(director):
	"""Buchetele din bouquets.tv / bouquets.radio (FROM BOUQUET "..."), in ordine, fara dubluri."""
	rez = []
	for index in ('bouquets.tv', 'bouquets.radio'):
		text = _citeste_text(os.path.join(director, index))
		if not text:
			continue
		for linie in text.splitlines():
			if 'FROM BOUQUET "' not in linie:
				continue
			nume = linie.split('FROM BOUQUET "', 1)[1].split('"', 1)[0]
			if nume and '/' not in nume and nume not in rez:
				rez.append(nume)
	for nume in ('userbouquet.hds_t2.tv', 'userbouquet.hds_dab.radio', 'userbouquet.hdsdvbi.tv',
			'userbouquet.hdsdvbi.radio'):
		if nume not in rez and os.path.isfile(os.path.join(director, nume)):
			rez.append(nume)
	return rez


def citeste_buchet(text, nume_fisier, pozitii_feed=None):
	"""Fluxurile dintr-un buchet (referintele DVB fara cale vin din lamedb) -> lista de Canal."""
	pozitii_feed = pozitii_feed or {}
	rez = []
	intrari = []
	for linie in (text or '').splitlines():
		linie = linie.rstrip('\r')
		if linie.startswith('#SERVICE '):
			intrari.append([linie[9:].strip(), None])
		elif linie.startswith('#DESCRIPTION ') and intrari and intrari[-1][1] is None:
			intrari[-1][1] = linie[13:].strip()
	radio_buchet = nume_fisier.endswith('.radio')
	# marcajul de deasupra: in buchetele DAB+ / DVB-T2 din satelit fiecare ansamblu (feed) are un marcaj cu numele lui
	# (Hds/DabT2/buchete.py, intrari_noi), urmat de posturile lui
	marcaj = ''
	for ref, descriere in intrari:
		parti = ref.split(':')
		if len(parti) > 1 and parti[1] == '64':
			# numai marcajele noastre (1:64:4844xxxx, Hds/DabT2/buchete.ref_marcaj) sunt ansambluri; un marcaj pus de om
			# (de pilda „Preferatele mele” in Favorite) nu e numele ansamblului posturilor de sub el
			nostru = len(parti) > 2 and parti[2].upper().startswith('4844') and len(parti[2]) == 8
			marcaj = ansamblu_din_marcaj(descriere or ':'.join(parti[11:])) if nostru else ''
			continue
		if len(parti) < 11 or not parti[10] or 'FROM BOUQUET' in ref:
			continue
		try:
			fel, steaguri, stype = int(parti[0]), int(parti[1]), int(parti[2] or '0', 16)
		except ValueError:
			continue
		if steaguri & 64 or (steaguri & 7) == 7:     # marcaj sau director
			continue
		cale = parti[10]
		nume = descriere or ':'.join(parti[11:]).strip()
		if not nume:
			continue
		cheie_mas = cheie_din_ref(ref)
		simpla = cale.replace('%3a', ':').replace('%3A', ':')
		marcaj_dab = _marcaj_dab(simpla)
		if marcaj_dab:
			feed = _feed_din_url(cale, marcaj_dab)
			c = Canal(nume, ref, cheie_mas, 'dab', stype, pozitii_feed.get(('dab', feed)), (), 'fta', (), '', '',
				False, buchet=nume_fisier, radio=True, ansamblu=marcaj)
		elif MARCAJ_T2 in simpla:
			feed = _feed_din_url(cale, MARCAJ_T2)
			radio = stype in TIPURI_RADIO
			c = Canal(nume, ref, cheie_mas, 't2', stype, pozitii_feed.get(('t2', feed)), (), None,
				*(((), '') if radio else rez_din_tip_si_nume(stype, nume)),
				'' if radio else COD_DIN_TIP.get(stype, ''), False, buchet=nume_fisier, radio=radio, ansamblu=marcaj)
		elif '://' in simpla:
			radio = radio_buchet or stype in TIPURI_RADIO
			c = Canal(nume, ref, cheie_mas, 'internet', stype, None, (), None, (), '', '', False,
				buchet=nume_fisier, radio=radio)
		else:
			continue
		rez.append(c)
	return rez


def _citeste_text(cale):
	try:
		with open(cale, 'rb') as f:
			return f.read().decode('utf-8', 'replace')
	except (IOError, OSError):
		return None


# ---------------------------------------------------------------- buchetele DAB+ / DVB-T2 din satelit in lista de canale
# Posturile nu sunt in lamedb (sunt fluxuri de la releele locale), deci nu apar in „Toate”, „Sateliți” sau „Furnizori”,
# iar cu „mai multe buchete” oprit (implicit) nici buchetul lor nu se vede. Lista de canale le pune un dosar in
# „Sateliți” si pagina /canale le pune in lista de buchete (Screens/ChannelSelection.py, canale_web.py).
# In plus: buchetul "Canale de pe internet (DVB-I)" (Plugins/SystemPlugins/HdsDvbI), mereu in lista, fara nicio
# scanare: cu "mai multe buchete" oprit sta tot ca dosar in "Sateliti".
BUCHETE_FLUXURI = (('dab', 'radio', 'userbouquet.hds_dab.radio'), ('t2', 'tv', 'userbouquet.hds_t2.tv'),
	('dvbi', 'tv', 'userbouquet.hdsdvbi.tv'), ('dvbi', 'radio', 'userbouquet.hdsdvbi.radio'))
_buchete_fluxuri = {}


def fel_flux(ref_sau_cale):
	"""'dab' sau 't2' pentru referinta (sau calea) unui post DAB+ / DVB-T2 din satelit, altfel None."""
	c = (ref_sau_cale or '').replace('%3a', ':').replace('%3A', ':')
	if _marcaj_dab(c):
		return 'dab'
	if MARCAJ_T2 in c:
		return 't2'
	return None


def ref_buchet_flux(fisier):
	"""Referinta dosarului unui buchet, aceeasi ca randul din bouquets.tv / bouquets.radio."""
	return '1:7:%d:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % (2 if fisier.endswith('.radio') else 1, fisier)


def fel_buchet_flux(ref_sau_cale):
	"""'dab' / 't2' pentru dosarul (referinta sau calea lui) unui buchet DAB+ / DVB-T2 din satelit, altfel None."""
	c = ref_sau_cale or ''
	for fel, _lista, fisier in BUCHETE_FLUXURI:
		if ('FROM BOUQUET "%s"' % fisier) in c:
			return fel
	return None


def buchete_fluxuri(lista, director=None):
	"""[(fel, fisier)] ale listei 'tv' sau 'radio' care se pot deschide: fisierul exista si e trecut in
	bouquets.<lista> (eDVBDB incarca un userbouquet numai prin index; un buchet scos de om din lista ramane scos).
	Se tine minte dupa data si marimea fisierelor: la umplerea listei „Sateliți” costa cateva os.stat."""
	director = director or DIRECTOR
	index = os.path.join(director, 'bouquets.%s' % lista)
	ale_listei = [(fel, f) for fel, l, f in BUCHETE_FLUXURI if l == lista]
	sem = _semnatura([index] + [os.path.join(director, f) for _fel, f in ale_listei])
	vechi = _buchete_fluxuri.get((director, lista))
	if vechi is not None and vechi[0] == sem:
		return vechi[1]
	text = _citeste_text(index) or ''
	rez = [(fel, f) for fel, f in ale_listei
		if os.path.isfile(os.path.join(director, f)) and ('FROM BOUQUET "%s"' % f) in text]
	_buchete_fluxuri[(director, lista)] = (sem, rez)
	return rez


def nume_buchet_flux(fel):
	"""Numele buchetului, tradus acum (in fisier #NAME e scris in romana, la scanare)."""
	if fel == 'dvbi':
		return _('Canale de pe internet (DVB-I)')
	return _('DAB+ din satelit') if fel == 'dab' else _('DVB-T2 din satelit')


def fel_dosar_text(fel):
	"""Felul dosarului, sub numele lui in panoul din dreapta al listei."""
	if fel == 'dvbi':
		return _('Canale primite prin internet, din listele DVB-I ale țării alese')
	return _('Posturi de radio DAB+ recepționate din satelit') if fel == 'dab' else _('Canale DVB-T2 recepționate din satelit')


def text_buchet_gol(fel, cuOk=True):
	"""Ce vede omul intr-un buchet DAB+ / DVB-T2 gol: ce e si cum se umple. cuOk: in lista buchetului, unde OK porneste
	cautarea (numai sagetile si OK); fara: in pagina web."""
	ce, unde = _texte_gol(fel)
	if cuOk:
		ok = _('Apasă OK ca să alegi țara.') if fel == 'dvbi' else _('Apasă OK ca să cauți acum.')
		return ce + '\n\n' + ok + ' ' + unde
	return ce + '\n\n' + unde


def _texte_gol(fel):
	if fel == 'dvbi':
		return (_('Aici apar canalele de pe internet (DVB-I) ale țării alese, fără nicio scanare și fără antenă. Lista e goală: încă nu ai ales țara sau listele ei nu s-au descărcat.'),
			_('Țara se alege în Meniu > Setări > Surse de pe internet > DVB-I (televiziune prin internet).'))
	if fel == 'dab':
		return (_('Aici apar posturile de radio DAB+ recepționate din satelit. Lista e goală: încă nu ai căutat posturi DAB+.'),
			_('Căutarea e în Meniu > Scanare > Satelit > DAB+ prin satelit.'))
	return (_('Aici apar canalele DVB-T2 recepționate din satelit (televiziune terestră trimisă prin satelit). Lista e goală: încă nu ai căutat canale DVB-T2.'),
		_('Căutarea e în Meniu > Scanare > Satelit > DVB-T2 prin satelit.'))


def texte_dosar(fel, n):
	"""(sus, jos) pentru randul dosarului in panoul din dreapta al listei, deasupra si dedesubtul barii emisiunii:
	gol = ce e si unde e cautarea; cu posturi = cate are si cum se completeaza."""
	if not n:
		return _texte_gol(fel)
	if fel == 'dvbi':
		return (ngettext('%d canal', '%d canale', n) % n + '.',
			_('Lista se actualizează singură de pe internet, din oră în oră.'))
	if fel == 'dab':
		return (ngettext('%d post', '%d posturi', n) % n + '.',
			_('Lista se completează când cauți din nou în Meniu > Scanare > Satelit > DAB+ prin satelit.'))
	return (ngettext('%d canal', '%d canale', n) % n + '.',
		_('Lista se completează când cauți din nou în Meniu > Scanare > Satelit > DVB-T2 prin satelit.'))


def _semnatura(cai):
	rez = []
	for cale in cai:
		try:
			st = os.stat(cale)
			rez.append((cale, st.st_mtime, st.st_size))
		except OSError:
			rez.append((cale, None, None))
	return tuple(rez)


# ---------------------------------------------------------------- indexul

class Index(object):
	def __init__(self, canale, complet=True):
		"""complet=False: numai ordinea si bitii (fara limbi, masti si numarare), pentru un index facut pe un fir si
		terminat pe firul enigma2 cu aplica_treptat (Screens/HdsCautareCanale.py, pregatirea in fundal)."""
		# ordinea de baza: dupa nume (fara diacritice); numele fara nicio litera sau cifra (de ex. „.") spre sfarsit, iar
		# serviciile fara nume (numele facut la scanare) la coada; filtrarea pastreaza ordinea
		canale.sort(key=lambda c: (c.fara_nume, not c.cheie, c.cheie, c.nume.lower()))
		self.canale = canale
		self.biti = {}
		for g in ('tip', 'rez', 'acces', 'cod', 'are', 'fsunet', 'msunet', 'psunet'):
			self.biti[g] = dict((v, 1 << k) for k, (v, _e) in enumerate(OPTIUNI_FIXE[g]))
		self.biti['sistem'] = dict((s[0], 1 << k) for k, s in enumerate(SISTEME + (SISTEM_ALT,)))
		pozitii = sorted(set(c.poz for c in canale if c.poz is not None), key=_cheie_ordine_poz)
		self.pozitii = pozitii
		self.biti['poz'] = dict((p, 1 << k) for k, p in enumerate(pozitii))
		self.masurari_aplicate = {}
		# privirea aplicata ultima data si versiunea ei (obiectul tinut, nu id-ul lui, care se poate refolosi)
		self.masurari_marcaj = (None, None)
		self.piste_aplicate = None
		self.limba_receptor = None
		self.nume_limba = _nume_limba_implicit
		self.limbi = {'lsunet': [], 'lsub': []}
		self.optiuni = {}
		self.cu_optiuni = dict((g, 0) for g in GRUPURI)
		if complet:
			self._limbi()
			for c in canale:
				self._masti(c)
			self._numara()

	def _limbi(self):
		for _pas in self._limbi_treptat():
			pass

	def _limbi_treptat(self, pas=None):
		"""Limbile care exista in piste: intai limba receptorului, apoi dupa numarul de canale, apoi dupa nume. Bitii
		randurilor „Sunet” si „Subtitrare” se dau in aceasta ordine. Generator: un yield la fiecare `pas` canale."""
		pas = pas or PAS_TREPTAT
		numere = {'lsunet': {}, 'lsub': {}}
		for i, c in enumerate(self.canale):
			for l in c.ls:
				numere['lsunet'][l] = numere['lsunet'].get(l, 0) + 1
			for l in set(c.lsd) | set(c.lst):
				numere['lsub'][l] = numere['lsub'].get(l, 0) + 1
			if i % pas == pas - 1:
				yield
		for g in ('lsunet', 'lsub'):
			numar = numere[g]
			ordine = sorted(numar, key=lambda l: (l != self.limba_receptor, -numar[l], self.nume_limba(l).lower(), l))
			self.limbi[g] = ordine
			self.biti[g] = dict((l, 1 << k) for k, l in enumerate(ordine))

	def _masti(self, c):
		b = self.biti
		mt = b['tip'].get(c.tip, 0)
		mr = 0
		for r in c.rez:
			mr |= b['rez'].get(r, 0)
		ma = b['acces'].get(c.acces, 0)
		ms = 0
		for s in c.sisteme:
			ms |= b['sistem'].get(s, 0)
		mc = b['cod'].get(c.cod, 0)
		mp = b['poz'].get(c.poz, 0)
		mare = 0
		for v in c.are:
			mare |= b['are'].get(v, 0)
		mfs = 0
		for v in c.fs:
			mfs |= b['fsunet'].get(v, 0)
		mms = 0
		for v in c.ms:
			mms |= b['msunet'].get(v, 0)
		mps = b['psunet'].get(str(min(c.np, 3)), 0) if c.np else 0
		mls = 0
		for l in c.ls:
			mls |= b['lsunet'].get(l, 0)
		mld = mlt = 0
		for l in c.lsd:
			mld |= b['lsub'].get(l, 0)
		for l in c.lst:
			mlt |= b['lsub'].get(l, 0)
		c.m_lsd, c.m_lst = mld, mlt
		# in ordinea din GRUPURI
		c.masti = (mt, mr, ma, ms, mc, mp, mare, mfs, mms, mps, mls, mld | mlt)

	def _numara(self):
		for _pas in self._numara_treptat():
			pass

	def _numara_treptat(self, pas=None):
		"""Optiunile de aratat: doar cele cu cel putin un canal, in ordinea fixa. cu_optiuni: cate canale au cel putin
		o optiune in fiecare grup (de ex. la cate canale se stie sunetul mono / stereo / multicanal). Generator: un yield
		la fiecare `pas` canale; optiunile se schimba o singura data, la sfarsit."""
		pas = pas or PAS_TREPTAT
		numar = dict((g, {}) for g in GRUPURI)
		for k, c in enumerate(self.canale):
			for i, g in enumerate(GRUPURI):
				m = c.masti[i]
				if m:
					d = numar[g]
					d[m] = d.get(m, 0) + 1
			if k % pas == pas - 1:
				yield
		optiuni = {}
		self.cu_optiuni = dict((g, sum(numar[g].values())) for g in GRUPURI)
		for i, g in enumerate(GRUPURI):
			if g == 'sistem':
				lista = [(s[0], _(_MSGID_OPTIUNI['sistem'][s[0]]) if s[0] in _MSGID_OPTIUNI['sistem'] else s[1])
					for s in SISTEME + (SISTEM_ALT,)]
			elif g == 'poz':
				lista = [(p, text_pozitie(p)) for p in self.pozitii]
			elif g in ('lsunet', 'lsub'):
				lista = [(l, self.nume_limba(l)) for l in self.limbi[g]]
			else:
				msgid = _MSGID_OPTIUNI.get(g, {})
				lista = [(v, _(msgid[v]) if v in msgid else e) for v, e in OPTIUNI_FIXE[g]]
			rez = []
			for v, eticheta in lista:
				bit = self.biti[g].get(v, 0)
				n = sum(k for m, k in numar[g].items() if m & bit)
				if n:
					rez.append((v, eticheta, n))
			optiuni[g] = rez
		self.optiuni = optiuni

	def grupuri_vizibile(self, fara_imagine=False):
		"""Grupurile cu cel putin doua optiuni folosite (unul cu o singura optiune nu are ce alege); randurile pistelor
		de la o optiune (vezi GRUPURI_PISTE). fara_imagine: fara rezolutie si codare video (se cauta numai radio, vezi
		numai_radio)."""
		return [g for g in GRUPURI if len(self.optiuni.get(g, ())) >= (1 if g in GRUPURI_PISTE else 2) and
			not (fara_imagine and g in GRUPURI_IMAGINE)]

	def eticheta_titlu(self, g, eticheta):
		"""Cum se scrie o optiune aleasa in titlul ecranului („sunet Engleză”)."""
		prefix = _(_MSGID_PREFIX[g]) if g in _MSGID_PREFIX else PREFIX_TITLU.get(g)
		return prefix % eticheta if prefix else eticheta

	def parti_titlu(self, selectie):
		"""Filtrele alese, cate o bucata pe rand, in ordinea randurilor: optiunile aceluiasi rand despartite cu „ / ”,
		sub prefixul randului o singura data („sunet Mono / Stereo”, „piste de sunet: 1 / 2”, „MPEG-2 / H.264”)."""
		parti = []
		for g in GRUPURI:
			alese = selectie.get(g) or ()
			if not alese:
				continue
			etichete = [eticheta for v, eticheta, _n in self.optiuni.get(g, ()) if v in alese]
			if etichete:
				parti.append(self.eticheta_titlu(g, ' / '.join(etichete)))
		return parti

	def canale_cu_piste(self):
		"""Cate canale au o inregistrare in baza pistelor (teletextul din lamedb singur nu ajunge)."""
		return sum(1 for c in self.canale if c.stiut)

	def aplica_masurari(self, masurari):
		"""masurari: {cheie: [inaltime, progresiv, cod]}. Se reface doar ce s-a schimbat. O privire peste baza unica
		(HdsIndexCanale.masuratori().toate(), cu `versiune`) aceeasi si cu aceeasi versiune ca data trecuta = nimic de
		facut; altfel se citeste o singura data, rand cu rand."""
		if masurari is None:
			masurari = {}
		v = getattr(masurari, 'versiune', None)
		if v is not None and self.masurari_marcaj[0] is masurari and self.masurari_marcaj[1] == v:
			return False
		marcaj = (masurari, v) if v is not None else (None, None)
		if not isinstance(masurari, dict):
			masurari = dict(masurari.items())
		schimbat = False
		vechi = self.masurari_aplicate
		chei = set(vechi) | set(masurari)
		if not chei:
			self.masurari_marcaj = marcaj
			return False
		dupa_cheie = None
		for k in chei:
			nou = masurari.get(k)
			if vechi.get(k) == nou:
				continue
			if dupa_cheie is None:
				dupa_cheie = {}
				for c in self.canale:
					if c.cheie_mas is not None:
						dupa_cheie.setdefault(c.cheie_mas, []).append(c)
			for c in dupa_cheie.get(k, ()):
				c.aplica_masurare(nou)
				self._masti(c)
				schimbat = True
		self.masurari_aplicate = dict((k, list(v)) for k, v in masurari.items())
		self.masurari_marcaj = marcaj
		if schimbat:
			self._numara()
		return schimbat

	def la_zi(self, masurari, versiune_piste, limba_receptor=None):
		"""Indexul are deja masuratorile si pistele de acum (aceleasi priviri, aceleasi versiuni): nimic de refacut."""
		v = getattr(masurari, 'versiune', None)
		if v is None or self.masurari_marcaj != (masurari, v):
			return False
		return versiune_piste is not None and self.piste_aplicate == (versiune_piste, None, limba_receptor)

	def aplica_treptat(self, masurari, trasaturi, versiune=None, limba_receptor=None, nume_limba=None,
			pas=None):
		"""Masuratorile si pistele pe tot indexul, apoi limbile, mastile si numararea, pentru un index nou, facut cu
		complet=False si inca nefolosit. Generator: un yield la fiecare `pas` canale, ca firul enigma2 sa lucreze in
		felii scurte (Screens/HdsCautareCanale.py). masurari si trasaturi: dictionare sau privirile bazei unice, citite
		numai de pe firul enigma2."""
		pas = pas or PAS_TREPTAT
		if masurari is None:
			masurari = {}
		v = getattr(masurari, 'versiune', None)
		aplicate = {}
		for k, c in enumerate(self.canale):
			if c.cheie_mas:
				m = masurari.get(c.cheie_mas)
				if m:
					c.aplica_masurare(m)
					aplicate[c.cheie_mas] = list(m)
				c.aplica_piste(trasaturi.get(c.cheie_mas) if trasaturi is not None else None)
			else:
				c.aplica_piste(None)
			if k % pas == pas - 1:
				yield
		self.masurari_aplicate = aplicate
		self.masurari_marcaj = (masurari, v) if v is not None else (None, None)
		if nume_limba is not None:
			self.nume_limba = nume_limba
		self.limba_receptor = limba_receptor
		for _pas in self._limbi_treptat(pas):
			yield
		for k, c in enumerate(self.canale):
			self._masti(c)
			if k % pas == pas - 1:
				yield
		for _pas in self._numara_treptat(pas):
			yield
		self.piste_aplicate = (versiune, id(trasaturi) if versiune is None else None, limba_receptor)

	def aplica_piste(self, trasaturi, versiune=None, limba_receptor=None, nume_limba=None):
		"""trasaturi: {cheie: HdsPisteCanale.trasaturi(inregistrare)} (HdsPisteCanale.Baza.trasaturi()). versiune: a
		bazei; aceeasi versiune de doua ori = nimic de facut. -> True daca s-a schimbat ceva."""
		marcaj = (versiune, id(trasaturi) if versiune is None else None, limba_receptor)
		if versiune is not None and marcaj == self.piste_aplicate:
			return False
		if nume_limba is not None:
			self.nume_limba = nume_limba
		self.limba_receptor = limba_receptor
		trasaturi = trasaturi or {}
		for c in self.canale:
			c.aplica_piste(trasaturi.get(c.cheie_mas) if c.cheie_mas else None)
		self._limbi()
		for c in self.canale:
			self._masti(c)
		self._numara()
		self.piste_aplicate = marcaj
		return True

	def conditii(self, selectie):
		"""Grupurile alese ale selectiei: [(indicele grupului in GRUPURI, masca optiunilor alese, fel)], SAU in grup
		(masca), SI intre grupuri. fel: None, sau (dvb, ttx) pentru limba subtitrarii cuplata cu „Subtitrari DVB” si/sau
		„Teletext” alese la „Are”: limba se cauta numai in felul ales."""
		selectie = selectie or {}
		fel_sub = set(selectie.get('are') or ())
		cuplat = bool(selectie.get('lsub')) and bool(fel_sub) and fel_sub <= set(('subdvb', 'subttx'))
		i_lsub = GRUPURI.index('lsub')
		rez = []
		for i, g in enumerate(GRUPURI):
			valori = selectie.get(g)
			if not valori:
				continue          # grup fara optiuni alese: nu filtreaza
			m = 0
			for v in valori:
				m |= self.biti[g].get(v, 0)
			fel = ('subdvb' in fel_sub, 'subttx' in fel_sub) if (i == i_lsub and cuplat) else None
			rez.append((i, m, fel))
		return rez

	@staticmethod
	def masca(c, i, fel):
		"""Masca canalului in grupul i, ca in conditii(): la limba subtitrarii cuplata, numai felul ales."""
		if fel is None:
			return c.masti[i]
		dvb, ttx = fel
		return (c.m_lsd if dvb else 0) | (c.m_lst if ttx else 0)

	def numara_fatetat_treptat(self, canale, selectie, pas=None):
		"""Numarul fiecarei optiuni cu selectia data (numaratoarea „fatetata”): optiunea X din grupul G = cate canale din
		`canale` au X si trec de TOATE celelalte grupuri alese (in G insusi optiunile se aduna cu SAU, deci bifarea lui X
		nu e oprita de ce e deja bifat in G); fara nimic ales, numerele de pe toata lista. O singura trecere: fiecare canal
		numara cate grupuri alese nu trece; 0 = intra la optiunile tuturor grupurilor, exact 1 (grupul G) = numai la
		optiunile lui G. Generator: un yield la fiecare `pas` canale; la sfarsit intoarce {grup: {valoare: n}} (cu 0
		pentru optiunile fara niciun canal)."""
		pas = pas or PAS_TREPTAT
		cond = self.conditii(selectie)
		fel_i = dict((i, fel) for i, _m, fel in cond)
		numar = [{} for _g in GRUPURI]
		grupuri = range(len(GRUPURI))
		for k, c in enumerate(canale):
			if k % pas == pas - 1:
				yield
			rata = None
			n = 0
			for i, m, fel in cond:
				if not (self.masca(c, i, fel) & m):
					n += 1
					if n > 1:
						break
					rata = i
			if n == 0:
				for i in grupuri:
					mk = self.masca(c, i, fel_i.get(i))
					if mk:
						d = numar[i]
						d[mk] = d.get(mk, 0) + 1
			elif n == 1:
				mk = self.masca(c, rata, fel_i.get(rata))
				if mk:
					d = numar[rata]
					d[mk] = d.get(mk, 0) + 1
		rez = {}
		for i, g in enumerate(GRUPURI):
			biti = self.biti.get(g, {})
			rez[g] = dict((v, sum(k for mk, k in numar[i].items() if mk & bit)) for v, bit in biti.items())
		i_are = GRUPURI.index('are')
		if any(fel is not None for _i, _m, fel in cond) and i_are in fel_i:
			# limba subtitrarii cuplata cu „Are”: ce ar ramane cu o optiune X din „Are” depinde de X (limba se cauta in
			# felul lui X), deci randul „Are” se numara separat, cate o trecere pe optiune (numai in acest caz rar)
			alte = [(i, m, fel) for i, m, fel in cond if i != i_are]
			for v, bit in self.biti['are'].items():
				fel_v = ((v == 'subdvb', v == 'subttx') if v in ('subdvb', 'subttx') else None)
				cond_v = [(i, m, fel_v if fel is not None else None) for i, m, fel in alte]
				n = 0
				for k, c in enumerate(canale):
					if k % pas == pas - 1:
						yield
					if c.masti[i_are] & bit and all(self.masca(c, i, fel) & m for i, m, fel in cond_v):
						n += 1
				rez['are'][v] = n
		return rez

	def numara_fatetat(self, canale, selectie):
		"""numara_fatetat_treptat dintr-o bucata."""
		gen = self.numara_fatetat_treptat(canale, selectie)
		while True:
			try:
				next(gen)
			except StopIteration as gata:
				return gata.value

	def canale_pentru_text(self, text=''):
		"""Canalele care se potrivesc cu textul (numele; la posturile DAB / T2 si felul si ansamblul, ca filtreaza), in
		ordinea indexului, fara filtre: baza numerelor de langa optiuni cand se cauta un text. Fara text: tot indexul
		(lista insasi, necopiata)."""
		q = normalizeaza(text)
		if not q:
			return self.canale
		return [c for c in self.canale if q in c.cheie or (c.alte and c.se_potriveste(q))]

	def filtreaza(self, text='', selectie=None):
		"""-> lista de Canal. Textul se cauta in nume (fara diacritice, spatii, semne); selectie = {grup: set(valori)}."""
		q = normalizeaza(text)
		conditii = self.conditii(selectie)
		canale = self.canale
		if q:
			# numele, apoi (numai la posturile DAB / T2) felul si ansamblul: „DAB+”, „DVB-T2”, „DR Deutschland”
			canale = [c for c in canale if q in c.cheie or (c.alte and c.se_potriveste(q))]
		for i, m, fel in conditii:
			if fel is not None:
				dvb, ttx = fel
				canale = [c for c in canale if (dvb and c.m_lsd & m) or (ttx and c.m_lst & m)]
			else:
				canale = [c for c in canale if c.masti[i] & m]
		if q:
			# serviciile fara nume raman la coada si cand textul se potriveste mai bine cu ele (furnizorul, „SID”)
			canale = sorted(canale, key=lambda c: (c.fara_nume, c.rang(q)))
		elif canale is self.canale:
			canale = list(canale)
		return canale


def _nume_limba_implicit(cod):
	return (cod or '').upper()


def titlu_cautare(titlu, text, parti, maxim=None, incape=None):
	"""Titlul cautarii: „<titlu>: „<text>”, <filtrele randurilor>”. maxim: cate caractere incap in titlul de pe ecran;
	incape: in locul lui maxim, o functie (text) -> True cand textul incape in titlul de pe ecran (latimea masurata cu
	fontul titlului din skin, Screens/HdsCautareCanale.py: literele late, ca „Â”, nu mai trec de capatul lui). Bucatile
	care nu mai incap se inlocuiesc cu „… (+N)” (N = cate bucati nu se mai vad), nu se taie la mijlocul unui cuvant; o
	singura bucata prea lunga se taie la litera, cu „…”."""
	bucati = (['„%s”' % text] if text else []) + list(parti)
	if not bucati:
		return titlu
	rez = titlu + ': ' + ', '.join(bucati)
	dupa_latime = incape is not None
	if not dupa_latime:
		if maxim is None:
			return rez
		incape = lambda s: len(s) <= maxim
	if incape(rez):
		return rez
	for k in range(len(bucati) - 1, 0, -1):
		cap = titlu + ': ' + ', '.join(bucati[:k])
		coada = ' … (+%d)' % (len(bucati) - k)
		if incape(cap + coada):
			return cap + coada
	coada = ' (+%d)' % (len(bucati) - 1) if len(bucati) > 1 else ''
	prima = titlu + ': ' + bucati[0]
	if not dupa_latime:
		return prima[:max(len(titlu) + 3, maxim - len(coada) - 1)].rstrip() + '…' + coada
	# dupa latime: cel mai lung inceput care incape cu „…” (cel putin titlul si „: „”), cautat prin injumatatire
	jos, sus = len(titlu) + 3, len(prima)
	while jos < sus:
		n = (jos + sus + 1) // 2
		if incape(prima[:n].rstrip() + '…' + coada):
			jos = n
		else:
			sus = n - 1
	return prima[:jos].rstrip() + '…' + coada


# ---------------------------------------------------------------- incarcarea, cu memorie

_memorie = {'semnatura': None, 'index': None}


def semnatura(director=DIRECTOR, pozitii_feed=None):
	"""Ce trebuie sa ramana la fel ca indexul din memorie sa fie bun: lamedb si buchetele (data, marimea) si pozitiile
	fluxurilor. Cateva os.stat."""
	buchete = fisiere_buchete(director)
	cai = [os.path.join(director, 'lamedb')] + [os.path.join(director, b) for b in buchete]
	return (director, _semnatura(cai), tuple(sorted((pozitii_feed or {}).items(), key=repr)))


def construieste(director=DIRECTOR, pozitii_feed=None, complet=True):
	"""Citirea lamedb-ului si a buchetelor si indexul, fara masuratori si piste. Numai fisiere si obiecte noi, nimic
	din enigma2 si nimic comun: se poate chema de pe un fir. -> (semnatura, Index)."""
	sem = semnatura(director, pozitii_feed)
	buchete = fisiere_buchete(director)
	canale = citeste_lamedb(_citeste_text(os.path.join(director, 'lamedb')) or '')
	for b in buchete:
		canale.extend(citeste_buchet(_citeste_text(os.path.join(director, b)), b, pozitii_feed))
	# acelasi flux in doua buchete: o singura data. Copia pastrata (de pilda din Favorite, fara marcaj) ia ansamblul
	# postului DAB+ / DVB-T2 din copia din buchetul lui, unde marcajul de deasupra il da
	vazute, unice = {}, []
	for c in canale:
		k = c.cheie_mas or c.ref
		pastrat = vazute.get(k)
		if pastrat is not None:
			if not pastrat.ansamblu and c.ansamblu and pastrat.tip == c.tip:
				pastrat.ansamblu = c.ansamblu
				pastrat.alte = cuvinte_flux(pastrat.tip, c.ansamblu) if pastrat.tip in CUVINTE_FEL else ()
			continue
		vazute[k] = c
		unice.append(c)
	return sem, Index(unice, complet=complet)


def din_memorie(sem=None):
	"""Indexul din memorie (pentru semnatura data, daca e data), sau None."""
	if _memorie['index'] is None or (sem is not None and _memorie['semnatura'] != sem):
		return None
	return _memorie['index']


def pune_in_memorie(sem, index):
	_memorie['index'] = index
	_memorie['semnatura'] = sem


def incarca(director=DIRECTOR, pozitii_feed=None, masurari=None, fortat=False, piste=None, versiune_piste=None,
		limba_receptor=None, nume_limba=None):
	"""Indexul pentru directorul de setari, pe loc. Se reface doar cand lamedb sau un buchet s-a schimbat (data,
	marimea). pozitii_feed: {('dab'|'t2', feed): pozitie} din listele HdsDab / HdsT2mi (optional).
	piste: {cheie: trasaturi} din HdsPisteCanale (Baza.trasaturi()), cu versiunea bazei (optional)."""
	sem = semnatura(director, pozitii_feed)
	if fortat or _memorie['semnatura'] != sem or _memorie['index'] is None:
		pune_in_memorie(*construieste(director, pozitii_feed))
	index = _memorie['index']
	index.aplica_masurari(masurari)
	if piste is not None:
		index.aplica_piste(piste, versiune_piste, limba_receptor, nume_limba)
	return index


def uita():
	_memorie['semnatura'] = None
	_memorie['index'] = None


# ---------------------------------------------------------------- masuratorile

def _jurnal_masuratori(text):
	print('[HdsIndexCanale] %s' % text)


def _completeaza_masuratoarea(vechi, nou):
	"""[inaltime, progresiv, cod] din `nou`, cu ce nu se stie in el (inaltimea 0, codul '') luat din `vechi` (sau None);
	progresivul merge cu inaltimea. Aceeasi regula la notare si la unirea memoriei peste fisier."""
	if not vechi:
		return [nou[0] or 0, nou[1] if nou[0] else -1, nou[2] or '']
	return [nou[0] or vechi[0], nou[1] if nou[0] else vechi[1], nou[2] or vechi[2]]


class Masuratori(object):
	"""Rezolutia si codecul vazute cand un canal a rulat. {cheie: [inaltime, progresiv, cod]}.
	Fisierul se scrie atomic (temporar + os.replace), doar daca s-a schimbat ceva; cine foloseste clasa hotaraste
	cand (in imagine: cel mult o data la 30 s, ca memoria flash sa nu se toceasca). Un fisier care nu s-a putut citi
	nu e scris peste (Components/HdsFisierSigur.py): eroare de citire = numai citire pana la o citire buna, JSON
	stricat = pus deoparte ca .stricat-AAAALLZZ inaintea primei scrieri, v mai mare sau peste MAX_OCTETI = numai
	citire."""
	VERSIUNE = 1
	MAXIM = 20000
	MAX_OCTETI = 4 * 1024 * 1024

	def __init__(self, cale=CALE_MASURATORI, monoton=None, ceas=None):
		self.cale = cale
		self.date = None
		self.murdar = False
		self.fisier = _S.FisierJson(cale, self.MAX_OCTETI, self.VERSIUNE, jurnal=_jurnal_masuratori, monoton=monoton,
			ceas=ceas)

	def toate(self):
		if self.date is None:
			self.date = self._citeste()
		elif self.fisier.la_timp():
			self._reciteste()
		return self.date

	def _citeste(self):
		"""-> {cheie: [inaltime, progresiv, cod]}; gol si la o citire nereusita (starea ei ramane in self.fisier)."""
		j = self.fisier.citeste()
		if j is None:
			return {}
		if not isinstance(j.get('s'), dict):
			self.fisier.stricat('"s" nu e un obiect')
			return {}
		rez = {}
		for k, v in j['s'].items():
			if isinstance(v, list) and len(v) == 3:
				rez[k] = v
		return rez

	def _reciteste(self):
		"""O citire noua; numai daca reuseste, masuratorile din memorie se unesc peste fisier, pe campuri: ce nu s-a aflat
		in memorie (inaltimea 0, codul '') ramane de pe disc."""
		disc = self._citeste()
		if self.fisier.stare == _S.CITIT:
			self.date = _S.uneste_peste(disc, self.date or {}, self.MAXIM, _completeaza_masuratoarea)

	def noteaza(self, cheie, inaltime, progresiv, cod):
		"""-> True daca s-a schimbat ceva."""
		if not cheie:
			return False
		try:
			inaltime = int(inaltime)
			progresiv = int(progresiv) if progresiv in (0, 1, True, False) else -1
		except (TypeError, ValueError):
			return False
		if inaltime <= 0 or inaltime > 4320:
			inaltime = 0
		cod = cod if cod in ETICHETA_COD or cod == 'alt' else ''
		date = self.toate()
		vechi = date.get(cheie)
		nou = _completeaza_masuratoarea(vechi, [inaltime, progresiv, cod])
		if not nou[0] and not nou[2]:
			return False
		if vechi == nou:
			return False
		if vechi is not None:
			del date[cheie]          # la sfarsit: cele vazute de curand raman cand lista se taie
		date[cheie] = nou
		while len(date) > self.MAXIM:
			del date[next(iter(date))]
		self.murdar = True
		return True

	def salveaza(self):
		if not self.murdar or self.date is None:
			return False
		if not self.fisier.poate_scrie(self._reciteste):
			return False
		director = os.path.dirname(self.cale) or '.'
		tmp = '%s.tmp%d' % (self.cale, os.getpid())
		try:
			if not os.path.isdir(director):
				os.makedirs(director)
			with open(tmp, 'wb') as f:
				f.write(json.dumps({'v': self.VERSIUNE, 's': self.date}, separators=(',', ':')).encode('utf-8'))
				f.flush()
				try:
					os.fsync(f.fileno())
				except OSError:
					pass
			os.replace(tmp, self.cale)
			self.fisier.scris()
		except (IOError, OSError):
			try:
				os.remove(tmp)
			except OSError:
				pass
			return False
		self.murdar = False
		return True


def masurare_din_rand(rec):
	"""Grupa vd a unui rand din baza unica -> [inaltime, progresiv, cod] ca in Masuratori (inaltimea necunoscuta 0),
	sau None daca nu se stie nici inaltimea, nici codecul."""
	vd = rec.get('vd') if rec else None
	if not isinstance(vd, list) or len(vd) < 7:
		return None
	inaltime = vd[1] if isinstance(vd[1], int) and not isinstance(vd[1], bool) and vd[1] > 0 else 0
	progresiv = vd[2] if vd[2] in (0, 1) and not isinstance(vd[2], bool) else -1
	cod = vd[6] if vd[6] in ETICHETA_COD or vd[6] == 'alt' else ''
	if not inaltime and not cod:
		return None
	return [inaltime, progresiv if inaltime else -1, cod]


class MasuratoriBaza(object):
	"""Adaptorul masuratorilor peste baza unica (Components/HdsBazaCanale.py, grupa vd), cu aceleasi metode ca
	Masuratori: toate() e o privire care desface randul cerut (fara toata baza in memorie), noteaza() scrie grupa vd,
	salveaza() lasa baza sa scrie la prag."""

	def __init__(self, B, b=None):
		self._B = B
		self._b = b
		self._vedere = None

	def _baza(self):
		if self._b is None:
			self._b = self._B.baza()
		return self._b

	def toate(self):
		if self._vedere is None:
			self._vedere = self._B.Vedere(self._baza(), masurare_din_rand, ('vd',), ('vd',))
		return self._vedere

	def noteaza(self, cheie, inaltime, progresiv, cod):
		"""-> True daca baza s-a schimbat."""
		if not cheie:
			return False
		try:
			inaltime = int(inaltime)
			progresiv = int(progresiv) if progresiv in (0, 1, True, False) else -1
		except (TypeError, ValueError):
			return False
		if inaltime <= 0 or inaltime > 4320:
			inaltime = 0
		cod = cod if cod in ETICHETA_COD or cod == 'alt' else ''
		if not inaltime and not cod:
			return False
		vd = [-1, inaltime or -1, progresiv if inaltime else -1, -1, -1, '', cod]
		return self._baza().actualizeaza(cheie, {'vd': vd}, 'v')

	def salveaza(self):
		return self._baza().salveaza(self._B.PRAG)


_MASURATORI = []


def masuratori():
	"""Masuratorile procesului: adaptorul peste baza unica; clasa Masuratori (fisierul de dinainte) numai daca baza
	unica nu se incarca."""
	if not _MASURATORI:
		try:
			try:
				from Components import HdsBazaCanale as B
			except ImportError:  # pe PC, in teste, Components e chiar dosarul modulului
				import HdsBazaCanale as B
			_MASURATORI.append(MasuratoriBaza(B))
		except Exception as e:
			_jurnal_masuratori('baza unica: %s; masuratorile de dinainte' % e)
			_MASURATORI.append(Masuratori())
	return _MASURATORI[0]
