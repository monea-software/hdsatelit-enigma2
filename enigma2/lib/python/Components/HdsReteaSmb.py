# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsReteaSmb.py: lista dosarelor partajate ale unui calculator cu Windows sau ale unui NAS (Components/HdsStocareRetea,
# "Alege dosarul"), fara programe in plus: un client SMB2 mic, numai pentru atat.
#   - SMB 2.0.2 si 2.1 (dialectele pe care le primeste orice Windows si Samba de azi; montarea insasi foloseste SMB 3
#     din nucleu), cu semnarea HMAC-SHA256 cand serverul o cere (Windows 11 o cere din 24H2);
#   - autentificarea NTLMv2 in SPNEGO (MD4 scris aici: OpenSSL 3 nu il mai da implicit), fara schimbul de cheie;
#     fara utilizator: o sesiune anonima (multe servere nu dau atunci lista);
#   - IPC$, conducta srvsvc, DCE/RPC: BIND, apoi NetrShareEnum (opnum 15, nivelul 1); se pastreaza dosarele de disc
#     obisnuite (fara IPC$, imprimante si dosarele ascunse cu $).
# Parola ramane in memorie numai cat dureaza cererea; nimic nu se scrie in jurnal.
# Fisierul nu importa nimic din enigma2: probele de pe PC il folosesc direct (test_stocare_retea.py, cu Samba).

import hashlib
import hmac
import os
import socket
import struct
import time

TERMEN_S = 8.0
DIALECTE = (0x0202, 0x0210)
STATUS_OK = 0
STATUS_MAI_MULT = 0xC0000016
STATUS_DEPASIRE = 0x80000005
STATUS_LOGON = (0xC000006D, 0xC000006E, 0xC0000064, 0xC000006A, 0xC0000072, 0xC0000234, 0xC000015B, 0xC0000022)
STATUS_NUME = (0xC00000CC, 0xC0000034)
SRVSVC = "4b324fc8-1670-01d3-1278-5a47bf6ee188"
NDR = "8a885d04-1ceb-11c9-9fe8-08002b104860"
OID_SPNEGO = b"\x2b\x06\x01\x05\x05\x02"
OID_NTLM = b"\x2b\x06\x01\x04\x01\x82\x37\x02\x02\x0a"
STEAGURI_NTLM = 0x00000001 | 0x00000004 | 0x00000010 | 0x00000200 | 0x00008000 | 0x00080000 | 0x00800000 | \
	0x20000000 | 0x80000000


class EroareSmb(IOError):
	"""cod: acces (parola gresita sau fara drept), server, nesuportat, alta"""

	def __init__(self, cod, text=""):
		IOError.__init__(self, text or cod)
		self.cod = cod


# ------------------------------------------------------------------ MD4 (RFC 1320)

def md4(date):
	def rot(x, n):
		x &= 0xFFFFFFFF
		return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF
	a, b, c, d = 0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476
	lung = len(date) * 8
	date = date + b"\x80" + b"\x00" * ((55 - len(date)) % 64) + struct.pack("<Q", lung)
	for i in range(0, len(date), 64):
		x = struct.unpack("<16I", date[i:i + 64])
		aa, bb, cc, dd = a, b, c, d
		f = lambda x1, y, z: (x1 & y) | (~x1 & z)
		g = lambda x1, y, z: (x1 & y) | (x1 & z) | (y & z)
		h = lambda x1, y, z: x1 ^ y ^ z
		for k in (0, 4, 8, 12):
			a = rot(a + f(b, c, d) + x[k], 3)
			d = rot(d + f(a, b, c) + x[k + 1], 7)
			c = rot(c + f(d, a, b) + x[k + 2], 11)
			b = rot(b + f(c, d, a) + x[k + 3], 19)
		for k in (0, 1, 2, 3):
			a = rot(a + g(b, c, d) + x[k] + 0x5a827999, 3)
			d = rot(d + g(a, b, c) + x[k + 4] + 0x5a827999, 5)
			c = rot(c + g(d, a, b) + x[k + 8] + 0x5a827999, 9)
			b = rot(b + g(c, d, a) + x[k + 12] + 0x5a827999, 13)
		for k in (0, 2, 1, 3):
			a = rot(a + h(b, c, d) + x[k] + 0x6ed9eba1, 3)
			d = rot(d + h(a, b, c) + x[k + 8] + 0x6ed9eba1, 9)
			c = rot(c + h(d, a, b) + x[k + 4] + 0x6ed9eba1, 11)
			b = rot(b + h(c, d, a) + x[k + 12] + 0x6ed9eba1, 15)
		a, b, c, d = (a + aa) & 0xFFFFFFFF, (b + bb) & 0xFFFFFFFF, (c + cc) & 0xFFFFFFFF, (d + dd) & 0xFFFFFFFF
	return struct.pack("<4I", a, b, c, d)


# ------------------------------------------------------------------ NTLMv2 (MS-NLMP)

def _hm(cheie, date):
	return hmac.new(cheie, date, hashlib.md5).digest()


def ntowfv2(utilizator, parola, domeniu):
	return _hm(md4(parola.encode("utf-16-le")), (utilizator.upper() + domeniu).encode("utf-16-le"))


def mesajNegociere():
	return b"NTLMSSP\x00" + struct.pack("<II", 1, STEAGURI_NTLM) + b"\x00" * 16


def desfaProvocare(date):
	"""CHALLENGE_MESSAGE -> (provocarea serverului, informatiile tintei, steagurile) sau EroareSmb."""
	i = date.find(b"NTLMSSP\x00")
	if i < 0 or len(date) < i + 48:
		raise EroareSmb("alta", "NTLM fara provocare")
	m = date[i:]
	if struct.unpack("<I", m[8:12])[0] != 2:
		raise EroareSmb("alta", "NTLM: alt mesaj")
	steaguri = struct.unpack("<I", m[20:24])[0]
	provocare = m[24:32]
	lung, _max, poz = struct.unpack("<HHI", m[40:48])
	return provocare, m[poz:poz + lung], steaguri


def _timpInfo(info):
	"""MsvAvTimestamp (7) din informatiile tintei, sau None."""
	i = 0
	while i + 4 <= len(info):
		ident, lung = struct.unpack("<HH", info[i:i + 4])
		if ident == 0:
			break
		if ident == 7 and lung == 8:
			return info[i + 4:i + 12]
		i += 4 + lung
	return None


def mesajAutentificare(utilizator, parola, domeniu, provocare, info, steaguri, client=None, timp=None):
	"""AUTHENTICATE_MESSAGE (NTLMv2) -> (mesajul, cheia sesiunii)."""
	client = client or os.urandom(8)
	if not utilizator:
		lm, nt, cheie = b"", b"", b"\x00" * 16
	else:
		v2 = ntowfv2(utilizator, parola, domeniu)
		marca = _timpInfo(info)
		t = timp or marca or struct.pack("<Q", int((time.time() + 11644473600) * 10000000))
		temp = b"\x01\x01" + b"\x00" * 6 + t + client + b"\x00" * 4 + info + b"\x00" * 4
		dovada = _hm(v2, provocare + temp)
		nt = dovada + temp
		lm = b"\x00" * 24 if marca else _hm(v2, provocare + client) + client
		cheie = _hm(v2, dovada)
	d = domeniu.encode("utf-16-le")
	u = utilizator.encode("utf-16-le")
	w = b"HDSATELIT".decode("ascii").encode("utf-16-le")
	poz = 64
	campuri = b""
	date = b""
	for bucata in (lm, nt, d, u, w, b""):
		campuri += struct.pack("<HHI", len(bucata), len(bucata), poz + len(date))
		date += bucata
	st = steaguri & STEAGURI_NTLM
	if not utilizator:
		st |= 0x00000800        # anonim
	return b"NTLMSSP\x00" + struct.pack("<I", 3) + campuri + struct.pack("<I", st) + date, cheie


# ------------------------------------------------------------------ SPNEGO (DER mic)

def _der(tag, continut):
	n = len(continut)
	if n < 0x80:
		lung = struct.pack("B", n)
	elif n < 0x100:
		lung = b"\x81" + struct.pack("B", n)
	else:
		lung = b"\x82" + struct.pack(">H", n)
	return struct.pack("B", tag) + lung + continut


def spnegoInit(ntlm):
	mech = _der(0xa0, _der(0x30, _der(0x06, OID_NTLM)))
	jeton = _der(0xa2, _der(0x04, ntlm))
	return _der(0x60, _der(0x06, OID_SPNEGO) + _der(0xa0, _der(0x30, mech + jeton)))


def spnegoRaspuns(ntlm):
	return _der(0xa1, _der(0x30, _der(0xa2, _der(0x04, ntlm))))


# ------------------------------------------------------------------ SMB2

def _uuid(text):
	p = text.split("-")
	return struct.pack("<IHH", int(p[0], 16), int(p[1], 16), int(p[2], 16)) + bytes.fromhex(p[3] + p[4])


class Smb2(object):
	def __init__(self, gazda, port=445, termen=TERMEN_S, conecteaza=None):
		self.s = (conecteaza or socket.create_connection)((gazda, port), termen)
		self.s.settimeout(termen)
		self.gazda = gazda
		self.mid = 0
		self.sesiune = 0
		self.arbore = 0
		self.dialect = 0
		self.semneaza = False
		self.cheie = b""
		self.max_citire = 65536

	def inchide(self):
		try:
			self.s.close()
		except Exception:
			pass

	def _primeste(self):
		antet = self._exact(4)
		lung = struct.unpack(">I", antet)[0] & 0xFFFFFF
		return self._exact(lung)

	def _exact(self, n):
		rez = b""
		while len(rez) < n:
			b = self.s.recv(n - len(rez))
			if not b:
				raise EroareSmb("server", "legatura inchisa")
			rez += b
		return rez

	def cerere(self, comanda, corp):
		antet = bytearray(struct.pack("<4sHHIHHIIQIIQ16s", b"\xfeSMB", 64, 1 if self.dialect >= 0x0210 else 0, 0,
			comanda, 31, 0, 0, self.mid, 0xFEFF, self.arbore, self.sesiune, b"\x00" * 16))
		mesaj = bytearray(antet) + corp
		if self.semneaza and comanda != 1:
			struct.pack_into("<I", mesaj, 16, 0x00000008)
			semn = hmac.new(self.cheie, bytes(mesaj), hashlib.sha256).digest()[:16]
			mesaj[48:64] = semn
		self.mid += 1
		self.s.sendall(struct.pack(">I", len(mesaj)) + bytes(mesaj))
		while True:
			r = self._primeste()
			if r[:4] != b"\xfeSMB":
				raise EroareSmb("alta", "raspuns SMB2 de neinteles")
			stare = struct.unpack("<I", r[8:12])[0]
			if stare == 0x00000103:      # STATUS_PENDING: raspunsul adevarat vine dupa
				continue
			return stare, r

	def negociaza(self):
		corp = struct.pack("<HHHHI16sQ", 36, len(DIALECTE), 1, 0, 0, os.urandom(16), 0)
		corp += b"".join(struct.pack("<H", d) for d in DIALECTE)
		stare, r = self.cerere(0, corp)
		if stare != STATUS_OK:
			raise EroareSmb("nesuportat", "negocierea: 0x%08x" % stare)
		mod, self.dialect = struct.unpack("<HH", r[66:70])
		self.max_citire = min(65536, struct.unpack("<I", r[64 + 32:64 + 36])[0] or 65536)
		self.semneaza = bool(mod & 0x02)
		return self.dialect

	def autentifica(self, utilizator, parola, domeniu):
		corp = lambda jeton: struct.pack("<HBBIIHHQ", 25, 0, 1, 0, 0, 88, len(jeton), 0) + jeton
		stare, r = self.cerere(1, corp(spnegoInit(mesajNegociere())))
		if stare != STATUS_MAI_MULT:
			raise EroareSmb("acces" if stare in STATUS_LOGON else "alta", "sesiunea: 0x%08x" % stare)
		self.sesiune = struct.unpack("<Q", r[40:48])[0]
		poz, lung = struct.unpack("<HH", r[68:72])
		provocare, info, steaguri = desfaProvocare(r[poz:poz + lung])
		autent, cheie = mesajAutentificare(utilizator, parola, domeniu, provocare, info, steaguri)
		stare, r = self.cerere(1, corp(spnegoRaspuns(autent)))
		if stare != STATUS_OK:
			raise EroareSmb("acces" if stare in STATUS_LOGON else "alta", "sesiunea: 0x%08x" % stare)
		self.cheie = cheie
		flags = struct.unpack("<H", r[66:68])[0]
		if flags & 0x0003:      # oaspete sau sesiune nula: fara semnare
			self.semneaza = False
		elif self.semneaza and not utilizator:
			raise EroareSmb("acces", "serverul cere semnarea, deci un cont")

	def conecteazaArbore(self, cale):
		nume = cale.encode("utf-16-le")
		stare, r = self.cerere(3, struct.pack("<HHHH", 9, 0, 72, len(nume)) + nume)
		if stare != STATUS_OK:
			raise EroareSmb("acces" if stare in STATUS_LOGON else "alta", "IPC$: 0x%08x" % stare)
		self.arbore = struct.unpack("<I", r[36:40])[0]

	def deschide(self, nume):
		n = nume.encode("utf-16-le")
		corp = struct.pack("<HBBIQQIIIIIHHII", 57, 0, 0, 2, 0, 0, 0x0012019f, 0, 7, 1, 0, 120, len(n), 0, 0) + n
		stare, r = self.cerere(5, corp)
		if stare != STATUS_OK:
			raise EroareSmb("acces" if stare in STATUS_LOGON else "nesuportat", "conducta: 0x%08x" % stare)
		return r[64 + 64:64 + 80]

	def scrie(self, fid, date):
		corp = struct.pack("<HHIQ16sIIHHI", 49, 112, len(date), 0, fid, 0, 0, 0, 0, 0) + date
		stare, _r = self.cerere(9, corp)
		if stare != STATUS_OK:
			raise EroareSmb("alta", "scrierea: 0x%08x" % stare)

	def citeste(self, fid):
		rez = b""
		while True:
			corp = struct.pack("<HBBIQ16sIIIHH", 49, 0x50, 0, self.max_citire, 0, fid, 0, 0, 0, 0, 0) + b"\x00"
			stare, r = self.cerere(8, corp)
			if stare not in (STATUS_OK, STATUS_DEPASIRE):
				raise EroareSmb("alta", "citirea: 0x%08x" % stare)
			poz = struct.unpack("B", r[66:67])[0]
			lung = struct.unpack("<I", r[68:72])[0]
			rez += r[poz:poz + lung]
			if stare == STATUS_OK:
				return rez


# ------------------------------------------------------------------ DCE/RPC: srvsvc NetrShareEnum

def rpcBind(apel=1):
	ctx = struct.pack("<HBB", 0, 1, 0) + _uuid(SRVSVC) + struct.pack("<HH", 3, 0) + _uuid(NDR) + \
		struct.pack("<I", 2)
	corp = struct.pack("<HHIB3s", 4280, 4280, 0, 1, b"\x00" * 3) + ctx
	return struct.pack("<BBBBIHHI", 5, 0, 11, 3, 0x10, 16 + len(corp), 0, apel) + corp


def _sirNdr(text):
	t = (text + u"\x00").encode("utf-16-le")
	n = len(t) // 2
	b = struct.pack("<III", n, 0, n) + t
	return b + b"\x00" * ((4 - len(b) % 4) % 4)


def rpcShareEnum(gazda, apel=2):
	stub = struct.pack("<I", 0x00020000) + _sirNdr(u"\\\\" + gazda)
	stub += struct.pack("<IIIII", 1, 1, 0x00020004, 0, 0)       # nivelul 1, containerul gol
	stub += struct.pack("<I", 0xFFFFFFFF)                          # PreferedMaximumLength
	stub += struct.pack("<II", 0x00020008, 0)                      # ResumeHandle
	corp = struct.pack("<IHH", len(stub), 0, 15) + stub
	return struct.pack("<BBBBIHHI", 5, 0, 0, 3, 0x10, 16 + len(corp), 0, apel) + corp


def _citesteSir(date, i):
	maxim, _off, actual = struct.unpack("<III", date[i:i + 12])
	i += 12
	text = date[i:i + actual * 2].decode("utf-16-le", "replace").rstrip(u"\x00")
	i += actual * 2
	i += (4 - i % 4) % 4
	return text, i


def desfaShareEnum(raspuns):
	"""Raspunsul NetrShareEnum (cu antetul DCE/RPC) -> [(nume, tip, comentariu)]."""
	if len(raspuns) < 24 or raspuns[2] != 2:
		raise EroareSmb("alta", "DCE/RPC: nu e raspuns")
	date = raspuns[24:]
	i = 0
	_nivel, _sw, ptr_c, citite, ptr_b = struct.unpack("<IIIII", date[i:i + 20])
	i += 20
	if not ptr_b or not citite:
		return []
	maxim = struct.unpack("<I", date[i:i + 4])[0]
	i += 4
	intrari = []
	for _k in range(min(maxim, 1000)):
		p_nume, tip, p_com = struct.unpack("<III", date[i:i + 12])
		intrari.append([p_nume, tip, p_com])
		i += 12
	rez = []
	for p_nume, tip, p_com in intrari:
		nume = com = u""
		if p_nume:
			nume, i = _citesteSir(date, i)
		if p_com:
			com, i = _citesteSir(date, i)
		rez.append((nume, tip, com))
	return rez


def dosareDeDisc(intrari):
	"""Numai dosarele de disc obisnuite: fara IPC$, imprimante, dosarele de administrare si cele ascunse (cu $)."""
	return [n for n, tip, _c in intrari if (tip & 0xFFFF) == 0 and not tip & 0x80000000 and n and
		not n.endswith(u"$")]


def partajari(gazda, utilizator=u"", parola=u"", port=445, termen=TERMEN_S):
	"""Dosarele partajate ale serverului (lista de nume) sau EroareSmb (cu .cod)."""
	domeniu = u""
	if u"\\" in (utilizator or u""):
		domeniu, utilizator = utilizator.split(u"\\", 1)
	elif u"@" in (utilizator or u""):
		utilizator, domeniu = utilizator.split(u"@", 1)
	try:
		c = Smb2(gazda, port, termen)
	except socket.timeout:
		raise EroareSmb("server", "fara raspuns")
	except socket.gaierror:
		raise EroareSmb("nume", "nume necunoscut")
	except OSError:
		raise EroareSmb("server", "fara legatura")
	try:
		c.negociaza()
		c.autentifica(utilizator or u"", parola or u"", domeniu)
		c.conecteazaArbore(u"\\\\%s\\IPC$" % gazda)
		fid = c.deschide(u"srvsvc")
		c.scrie(fid, rpcBind())
		ack = c.citeste(fid)
		if len(ack) < 3 or ack[2] != 12:
			raise EroareSmb("nesuportat", "srvsvc: legatura refuzata")
		c.scrie(fid, rpcShareEnum(gazda))
		# un raspuns mai mare decat fragmentul DCE/RPC vine in mai multe fragmente: lipite intr-unul singur
		raspuns = c.citeste(fid)
		bucati = [raspuns]
		while len(bucati[-1]) >= 4 and not bucati[-1][3] & 0x02 and len(bucati) < 64:
			bucati.append(c.citeste(fid))
		if len(bucati) > 1:
			raspuns = bucati[0][:24] + b"".join(b[24:struct.unpack("<H", b[8:10])[0]] for b in bucati)
		return sorted(dosareDeDisc(desfaShareEnum(raspuns)), key=lambda n: n.lower())
	except socket.timeout:
		raise EroareSmb("termen", "fara raspuns")
	except struct.error:
		raise EroareSmb("alta", "raspuns de neinteles")
	finally:
		c.inchide()
