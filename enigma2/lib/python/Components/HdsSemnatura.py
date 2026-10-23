# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSemnatura.py: semnatura actualizarilor prin pachete. Receptorul instaleaza
# numai ce e semnat cu o cheie HD Satelit de aici, chiar daca serverul feedului (stb.hdsatelit.com) ar fi spart: cheia
# privata nu sta pe server, ci pe PC-ul care publica (intr-un dosar privat).
#
# Ce se verifica (Components/HdsActualizari.py): stare.json al feedului, octet cu octet, cu stare.json.sig de langa el.
# stare.json are sha256 pentru fiecare <arh>/Packages ("indexuri") si pentru fiecare .ipk ("pachete"), deci o singura
# semnatura acopera listele si pachetele. Formatul (scris de oe-build/semnare_feed.py):
#     hdsatelit-semnatura 1 stare.json
#     ed25519 <id cheie: primele 16 semne hex din sha256(cheia publica)> <semnatura de 64 de octeti, base64>
# cate un rand pe cheie (la o rotire semneaza doua). Se semneaza PREFIX + scop + 0 + octetii fisierului, ca o semnatura
# facuta pentru alt fisier sa nu treaca drept aceasta. Ed25519 vine din python3-cryptography (in imagine, cu
# python3-pyopenssl); fara ea verificarea cade (nu se instaleaza nimic), nu se sare niciodata.
#
# Cheile (CHEI) vin in pachetul enigma2-hdsatelit, deci se schimba prin actualizare, semnata cu o cheie pe care
# receptorul o are deja. Rotirea:
#   - principala semneaza fiecare publicare; rezerva sta numai in copia cifrata, pentru cand principala se pierde sau
#     e furata;
#   - cheie noua: intai intra aici (intr-o actualizare semnata cu cheia de acum), publicarile se semneaza apoi cu
#     amandoua, abia la sfarsit numai cu cea noua; cea veche iese de aici cel mai devreme dupa ce versiunea cu cheia
#     noua e pe toate canalele;
#   - cheie furata: id-ul ei intra in REVOCATE, intr-o actualizare semnata cu rezerva;
#   - toate cheile pierdute: imaginea noua de pe stick (cu cheile noi) aduce receptorul inapoi; nu ramane blocat.
# Modulul nu importa nimic din enigma (probele de pe PC: teste/test_semnare_actualizari.py).

import base64
import binascii
import hashlib
import re

ANTET = 'hdsatelit-semnatura 1'
PREFIX = b'HDSATELIT-SEMNATURA-1\x00'
ALGORITM = 'ed25519'
MARIME_MAX = 8 * 1024
SEMNATURI_MAX = 8

# cheile publice HD Satelit (Ed25519) in care are incredere receptorul: (id, cheia publica in hex, rolul); un rand al
# carui id nu e chiar al cheii lui e lasat deoparte
CHEI = (
	('5b37a168db304d40', 'fc8a0063059ac962293f24e9df0eec6b9631bde629d8d95f137b6f30f12d6f51', 'principala'),  # 13.10.2026
	('ab509255ca887bca', '417c5679b51965e3d72c126ecd49cb94f1ee81aaa618305bc6093142b28311cb', 'rezerva'),  # 13.10.2026
)
# id-urile cheilor scoase din incredere (pierdute sau furate): nu mai trec niciodata, chiar daca ar fi si in CHEI
REVOCATE = ()

# de ce nu trece o semnatura
LIPSA, FORMA, NECUNOSCUTA, REVOCATA, GRESITA, FARA_VERIFICARE = (
	'lipsa', 'forma', 'necunoscuta', 'revocata', 'gresita', 'fara-verificare')
TEXTE_MOTIV = {
	LIPSA: 'lipseste semnatura',
	FORMA: 'semnatura nu se poate citi',
	NECUNOSCUTA: 'semnata cu o cheie necunoscuta',
	REVOCATA: 'semnata cu o cheie scoasa din incredere',
	GRESITA: 'semnatura nu se potriveste cu fisierul',
	FARA_VERIFICARE: 'semnatura nu se poate verifica pe receptor (python3-cryptography)',
}

_ID = re.compile(r'^[0-9a-f]{16}\Z')
_PUBLICA = re.compile(r'^[0-9a-f]{64}\Z')
_SCOP = re.compile(r'^[A-Za-z0-9._\-]{1,64}\Z')


def id_cheie(publica):
	"""primele 16 semne hex din sha256(cheia publica de 32 de octeti)"""
	return hashlib.sha256(publica).hexdigest()[:16]


def inel(chei=None, revocate=None):
	"""{id: cheia publica (32 de octeti)}: cheile din CHEI al caror id e chiar al lor, fara cele revocate"""
	chei = CHEI if chei is None else chei
	scoase = set(REVOCATE if revocate is None else revocate)
	rez = {}
	for intrare in chei:
		try:
			ident, hexa = intrare[0], intrare[1]
		except (TypeError, IndexError, KeyError):
			continue
		if not isinstance(ident, str) or not isinstance(hexa, str) or not _ID.match(ident) or not _PUBLICA.match(hexa):
			continue
		publica = binascii.unhexlify(hexa)
		if id_cheie(publica) != ident or ident in scoase:
			continue
		rez[ident] = publica
	return rez


def mesaj(scop, date):
	"""ce se semneaza pentru fisierul `scop` (de pilda stare.json) cu octetii `date`"""
	return PREFIX + scop.encode('ascii') + b'\x00' + date


def citeste(text):
	"""(scop, [(id, semnatura de 64 de octeti)]) din textul unui fisier .sig; ValueError cand nu are forma"""
	if isinstance(text, bytes):
		if len(text) > MARIME_MAX:
			raise ValueError('semnatura prea mare')
		text = text.decode('ascii')
	if len(text) > MARIME_MAX:
		raise ValueError('semnatura prea mare')
	randuri = [r.strip() for r in text.split('\n')]
	randuri = [r for r in randuri if r and not r.startswith('#')]
	if not randuri:
		raise ValueError('fisier gol')
	parti = randuri[0].split(' ')
	if len(parti) != 3 or ' '.join(parti[:2]) != ANTET or not _SCOP.match(parti[2]):
		raise ValueError('antet')
	semnaturi = []
	for r in randuri[1:]:
		p = r.split(' ')
		if len(p) != 3 or p[0] != ALGORITM or not _ID.match(p[1]):
			raise ValueError('rand')
		try:
			s = base64.b64decode(p[2].encode('ascii'), validate=True)
		except (binascii.Error, ValueError):
			raise ValueError('base64')
		if len(s) != 64:
			raise ValueError('lungime')
		semnaturi.append((p[1], s))
	if not semnaturi or len(semnaturi) > SEMNATURI_MAX:
		raise ValueError('numarul semnaturilor')
	return parti[2], semnaturi


def _ed25519(publica, semnatura, date):
	"""True cand semnatura Ed25519 se potriveste; ImportError cand verificarea nu se poate face pe receptor"""
	try:
		from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
		from cryptography.exceptions import InvalidSignature
	except Exception as e:
		raise ImportError('python3-cryptography: %s' % e)
	try:
		Ed25519PublicKey.from_public_bytes(publica).verify(semnatura, date)
	except (InvalidSignature, ValueError, TypeError):
		return False
	return True


def verifica(date, text, scop, chei=None, revocate=None):
	"""(bun, motiv, id): bun cand cel putin o semnatura din `text` (continutul fisierului .sig) e a unei chei de
	incredere si se potriveste cu octetii `date` ai fisierului `scop`. motiv: '' cand e bun, altfel LIPSA, FORMA,
	NECUNOSCUTA, REVOCATA, GRESITA sau FARA_VERIFICARE; id: cheia despre care e vorba ('' cand nu e una anume)."""
	if not text:
		return False, LIPSA, ''
	if not isinstance(date, bytes):
		return False, FORMA, ''
	try:
		scop_fisier, semnaturi = citeste(text)
	except (ValueError, UnicodeError):
		return False, FORMA, ''
	if scop_fisier != scop:
		return False, FORMA, ''
	scoase = set(REVOCATE if revocate is None else revocate)
	de_incredere = inel(chei, scoase)
	motiv, ident_motiv = NECUNOSCUTA, semnaturi[0][0]
	m = mesaj(scop, date)
	for ident, s in semnaturi:
		if ident in scoase:
			if motiv == NECUNOSCUTA:
				motiv, ident_motiv = REVOCATA, ident
			continue
		publica = de_incredere.get(ident)
		if publica is None:
			continue
		try:
			if _ed25519(publica, s, m):
				return True, '', ident
		except ImportError as e:
			print('[HdsSemnatura] %s' % e)
			return False, FARA_VERIFICARE, ident
		motiv, ident_motiv = GRESITA, ident
	return False, motiv, ident_motiv


def text_motiv(motiv, ident=''):
	"""motivul unei semnaturi care nu trece, pentru jurnal si randul de sub mesaj"""
	t = TEXTE_MOTIV.get(motiv, motiv)
	return '%s (cheia %s)' % (t, ident) if ident and motiv in (NECUNOSCUTA, REVOCATA, GRESITA) else t
