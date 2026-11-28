# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCititorUbi.py: desface pe receptor o imagine UBI cu UBIFS (rootfs.ubi, imaginea pentru memoria interna NAND din
# arhivele altor echipe) intr-un dosar, de pilda <stick>/linuxrootfsN. Il foloseste Components/HdsPornireStick.py cand
# arhiva nu are rootfs.tar.* (MB3, 27.11.2026; Eduard 22:15: „orice imagine, si a altor echipe, intr-un loc liber de pe
# stick”). Scris de la zero dupa formatul de pe disc din nucleul Linux (drivers/mtd/ubi/ubi-media.h si
# fs/ubifs/ubifs-media.h, GPL-2.0); nu foloseste cod din ubi_reader.
#
# De ce in Python si nu nucleul (block2mtd + ubiattach + mount): receptorul nu are ubiattach (mtd-utils), un mtd facut
# cu block2mtd nu se mai poate scoate pana la repornire, iar UBI scrie in imagine la atasare (volumul cu autoresize).
# Aici nu se atinge nucleul si nici /dev/mtd*: se citeste numai fisierul .ubi si se scrie numai in dosarul tinta.
#
# Memoria (receptorul are 334 MB): se citeste intai arborele index si se tin numai inodurile, intrarile de dosar si
# locul fiecarui bloc de date (lnum, offs, len); datele se citesc si se scriu bloc cu bloc (4 KiB) la a doua trecere.
# Pe imaginile de 110-235 MB varful e de ~20-40 MB.
#
# Compresia blocurilor: fara, LZO (liblzo2 prin ctypes, apoi modulul lzo, apoi decodorul din fisier), zlib, zstd
# (compression.zstd din Python 3.14, apoi libzstd prin ctypes, apoi modulul zstandard).
#
# Folosire: python3 HdsCititorUbi.py rootfs.ubi /dosar/tinta      (ca root: proprietarii, drepturile, legaturile)
#           python3 HdsCititorUbi.py rootfs.ubi iesire.tar         (o arhiva tar, pentru probe pe PC)
# Pe iesirea standard: "P <octeti scrisi> <octeti in total>" din cand in cand si la sfarsit "GATA <fisiere> <dosare>
# <legaturi> <octeti>"; cod 0 cand a mers, 2 cand fisierul nu e o imagine UBI/UBIFS buna.

import os
import stat
import struct
import sys
import zlib

UBI_EC_MAGIC = b"UBI#"
UBI_VID_MAGIC = b"UBI!"
UBI_LAYOUT_VOLUME_ID = 0x7FFFEFFF
UBI_VTBL_RECORD = 172
UBIFS_MAGIC = 0x06101831
CH = struct.Struct("<IIQIBBH")  # magic, crc, sqnum, len, node_type, group_type, padding
INO, DATA, DENT, XENT, SB, MST, IDX = 0, 1, 2, 3, 6, 7, 9
UBIFS_BLOCK = 4096
UBIFS_XATTR_FL = 0x20
KEY_TYP_BITS = 29
PROGRES_PAS = 2 * 1024 * 1024


class ImagineRea(Exception):
	pass


# ---- decompresia

def lzo1x_decomprima(src, marime):
	"""Decodorul LZO1X (ca lzo1x_decompress_safe), scris dupa formatul fluxului; folosit cand nu e liblzo2."""
	dst = bytearray()
	ip = 0

	def lungime(t, baza):
		nonlocal ip
		if t == 0:
			while src[ip] == 0:
				t += 255
				ip += 1
			t += baza + src[ip]
			ip += 1
		return t

	def copie(m_pos, n):
		if m_pos < 0:
			raise ImagineRea("lzo: distanta rea")
		if m_pos + n <= len(dst):
			dst.extend(dst[m_pos:m_pos + n])
		else:
			for i in range(n):
				dst.append(dst[m_pos + i])

	stare = "bucla"
	t = 0
	if src[0] > 17:
		t = src[0] - 17
		ip = 1
		if t < 4:
			stare = "urmatoarea"
		else:
			dst.extend(src[ip:ip + t])
			ip += t
			stare = "prima"
	while True:
		if stare == "bucla":
			t = src[ip]
			ip += 1
			if t < 16:
				t = lungime(t, 15)
				dst.extend(src[ip:ip + t + 3])
				ip += t + 3
				stare = "prima"
				continue
			stare = "potrivire"
		elif stare == "prima":
			t = src[ip]
			ip += 1
			if t < 16:
				m_pos = len(dst) - (1 + 0x0800) - (t >> 2) - (src[ip] << 2)
				ip += 1
				copie(m_pos, 3)
				stare = "gata_potrivire"
				continue
			stare = "potrivire"
		elif stare == "urmatoarea":
			dst.extend(src[ip:ip + t])
			ip += t
			t = src[ip]
			ip += 1
			stare = "potrivire"
		if stare == "potrivire":
			if t >= 64:
				m_pos = len(dst) - 1 - ((t >> 2) & 7) - (src[ip] << 3)
				ip += 1
				copie(m_pos, (t >> 5) + 1)
			elif t >= 32:
				t = lungime(t & 31, 31)
				m_pos = len(dst) - 1 - ((src[ip] >> 2) + (src[ip + 1] << 6))
				ip += 2
				copie(m_pos, t + 2)
			elif t >= 16:
				m_pos = len(dst) - ((t & 8) << 11)
				t = lungime(t & 7, 7)
				m_pos -= (src[ip] >> 2) + (src[ip + 1] << 6)
				ip += 2
				if m_pos == len(dst):
					break
				m_pos -= 0x4000
				copie(m_pos, t + 2)
			else:
				m_pos = len(dst) - 1 - (t >> 2) - (src[ip] << 2)
				ip += 1
				copie(m_pos, 2)
			stare = "gata_potrivire"
		if stare == "gata_potrivire":
			t = src[ip - 2] & 3
			if t == 0:
				stare = "bucla"
			else:
				stare = "urmatoarea"
		if len(dst) > marime:
			raise ImagineRea("lzo: prea mult")
	return bytes(dst)


def _lzo():
	try:
		import ctypes
		import ctypes.util
		for nume in ("liblzo2.so.2", ctypes.util.find_library("lzo2") or ""):
			if not nume:
				continue
			try:
				lib = ctypes.CDLL(nume)
				f = lib.lzo1x_decompress_safe
			except (OSError, AttributeError):
				continue
			f.restype = ctypes.c_int
			f.argtypes = [ctypes.c_char_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p]
			tampon = ctypes.create_string_buffer(UBIFS_BLOCK * 2)

			def cu_lib(date, marime, f=f, tampon=tampon, ctypes=ctypes):
				if marime > len(tampon):
					raise ImagineRea("lzo: bloc prea mare")
				n = ctypes.c_ulong(marime)
				if f(date, len(date), tampon, ctypes.byref(n), None) != 0:
					raise ImagineRea("lzo: bloc stricat")
				return tampon.raw[:n.value]
			return cu_lib
	except ImportError:
		pass
	try:
		import lzo

		def cu_modul(date, marime, lzo=lzo):
			return lzo.decompress(date, False, marime)
		return cu_modul
	except ImportError:
		return lzo1x_decomprima


def _zstd():
	try:
		from compression import zstd

		def cu_py(date, marime, zstd=zstd):
			return zstd.decompress(date)
		return cu_py
	except ImportError:
		pass
	try:
		import ctypes
		lib = ctypes.CDLL("libzstd.so.1")
		f = lib.ZSTD_decompress
		f.restype = ctypes.c_size_t
		f.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t]
		tampon = ctypes.create_string_buffer(UBIFS_BLOCK * 2)

		def cu_lib(date, marime, f=f, tampon=tampon):
			n = f(tampon, len(tampon), date, len(date))
			if n > len(tampon):
				raise ImagineRea("zstd: bloc stricat")
			return tampon.raw[:n]
		return cu_lib
	except (ImportError, OSError, AttributeError):
		pass
	try:
		import zstandard

		def cu_modul(date, marime, z=zstandard.ZstdDecompressor()):
			return z.decompress(date, max_output_size=marime)
		return cu_modul
	except ImportError:
		return None


class Decompresie(object):
	def __init__(self):
		self.fel = {}

	def __call__(self, compr, date, marime):
		if compr == 0:
			return date
		if compr == 2:
			return zlib.decompress(date, -15)
		f = self.fel.get(compr)
		if f is None:
			f = _lzo() if compr == 1 else _zstd() if compr == 3 else None
			if f is None:
				raise ImagineRea("compresie necunoscuta %d" % compr)
			self.fel[compr] = f
		return f(date, marime)


# ---- stratul UBI

class Ubi(object):
	"""Volumul `nume` (implicit rootfs, altfel cel mai mare) dintr-un fisier .ubi: LEB -> locul in fisier."""

	def __init__(self, f, nume="rootfs"):
		self.f = f
		f.seek(0, 2)
		marime = f.tell()
		f.seek(0)
		ec = f.read(64)
		if ec[:4] != UBI_EC_MAGIC:
			raise ImagineRea("nu e o imagine UBI")
		self.vid_off, self.data_off = struct.unpack_from(">II", ec, 16)
		self.peb = self._peb(marime)
		leb = {}  # vol_id -> {lnum: (sqnum, peb)}
		for peb in range(marime // self.peb):
			f.seek(peb * self.peb)
			h = f.read(64)
			if h[:4] != UBI_EC_MAGIC:
				continue
			vid_off, data_off = struct.unpack_from(">II", h, 16)
			f.seek(peb * self.peb + vid_off)
			v = f.read(64)
			if v[:4] != UBI_VID_MAGIC:
				continue
			vol_id, lnum = struct.unpack_from(">II", v, 8)
			data_pad = struct.unpack_from(">I", v, 28)[0]
			sq = struct.unpack_from(">Q", v, 40)[0]
			vechi = leb.setdefault(vol_id, {}).get(lnum)
			if vechi is None or sq > vechi[0]:
				leb[vol_id][lnum] = (sq, peb * self.peb + data_off, data_pad)
		volume = self._tabel(leb.get(UBI_LAYOUT_VOLUME_ID, {}))
		ales = None
		for vid, n in volume.items():
			if n == nume and vid in leb:
				ales = vid
		if ales is None:
			candidati = [v for v in leb if v != UBI_LAYOUT_VOLUME_ID]
			if not candidati:
				raise ImagineRea("imaginea UBI nu are volume")
			ales = max(candidati, key=lambda v: len(leb[v]))
		self.volum = volume.get(ales, str(ales))
		self.leb = dict((l, (o, pad)) for l, (sq, o, pad) in leb[ales].items())
		pad = max([p for o, p in self.leb.values()] or [0])
		self.leb_marime = self.peb - self.data_off - pad

	def _peb(self, marime):
		p = 16 * 1024
		while p <= 4 * 1024 * 1024 and p < marime:
			self.f.seek(p)
			if self.f.read(4) == UBI_EC_MAGIC:
				return p
			p *= 2
		if marime <= 4 * 1024 * 1024:
			return marime
		raise ImagineRea("nu gasesc marimea blocului UBI")

	def _tabel(self, layout):
		volume = {}
		if not layout:
			return volume
		lnum = min(layout)
		off = layout[lnum][1]
		self.f.seek(off)
		date = self.f.read(UBI_VTBL_RECORD * 128)
		for i in range(len(date) // UBI_VTBL_RECORD):
			r = date[i * UBI_VTBL_RECORD:(i + 1) * UBI_VTBL_RECORD]
			rezervat = struct.unpack_from(">I", r, 0)[0]
			nlen = struct.unpack_from(">H", r, 14)[0]
			if rezervat and 0 < nlen <= 127:
				volume[i] = r[16:16 + nlen].decode("ascii", "replace")
		return volume

	def citeste(self, lnum, offs, n):
		loc = self.leb.get(lnum)
		if loc is None:
			return b"\xff" * n
		self.f.seek(loc[0] + offs)
		return self.f.read(n)


# ---- stratul UBIFS

class Ubifs(object):
	"""Arborele index citit o singura data: inoduri, intrari de dosar si locul blocurilor de date."""

	def __init__(self, ubi):
		self.ubi = ubi
		sb = self._nod(0, 0, 4096)
		if sb is None or sb[0] != SB:
			raise ImagineRea("nu e UBIFS (lipseste superblocul)")
		date = sb[2]
		self.leb_marime = struct.unpack_from("<I", date, 36)[0]
		self.compr = struct.unpack_from("<H", date, 84)[0]
		mst = None
		for lnum in (1, 2):
			bloc = ubi.citeste(lnum, 0, self.leb_marime)
			poz = 0
			while True:
				poz = bloc.find(struct.pack("<I", UBIFS_MAGIC), poz)
				if poz < 0 or poz + 64 > len(bloc):
					break
				magic, crc, sq, n, tip, grup, _p = CH.unpack_from(bloc, poz)
				if tip == MST and (mst is None or sq > mst[0]):
					mst = (sq, bloc[poz:poz + n])
				poz += 8
		if mst is None:
			raise ImagineRea("UBIFS fara nodul master")
		m = mst[1]
		self.radacina = struct.unpack_from("<III", m, 48)  # root_lnum, root_offs, root_len
		self.inoduri = {}   # inum -> (mode, uid, gid, size, mtime, nlink, data)
		self.intrari = {}   # inum parinte -> [(nume, inum)]
		self.blocuri = {}   # inum -> [(bloc, lnum, offs, len)]
		self._index()

	def _nod(self, lnum, offs, n):
		b = self.ubi.citeste(lnum, offs, n)
		if len(b) < 24:
			return None
		magic, crc, sq, lung, tip, grup, _p = CH.unpack_from(b, 0)
		if magic != UBIFS_MAGIC:
			return None
		if lung > len(b):
			b = self.ubi.citeste(lnum, offs, lung)
		return (tip, sq, b[:lung])

	def _index(self):
		stiva = [self.radacina]
		while stiva:
			lnum, offs, n = stiva.pop()
			nod = self._nod(lnum, offs, n)
			if nod is None or nod[0] != IDX:
				raise ImagineRea("index stricat la %d:%d" % (lnum, offs))
			b = nod[2]
			copii, nivel = struct.unpack_from("<HH", b, 24)
			for i in range(copii):
				bl, bo, blen, k_inum, k_rest = struct.unpack_from("<IIIII", b, 28 + i * 20)
				if nivel > 0:
					stiva.append((bl, bo, blen))
					continue
				tip = k_rest >> KEY_TYP_BITS
				if tip == DATA:
					self.blocuri.setdefault(k_inum, []).append((k_rest & ((1 << KEY_TYP_BITS) - 1), bl, bo, blen))
				elif tip == INO:
					f = self._nod(bl, bo, blen)
					if f and f[0] == INO:
						self._inod(f[2])
				elif tip == DENT:
					f = self._nod(bl, bo, blen)
					if f and f[0] == DENT:
						d = f[2]
						inum = struct.unpack_from("<Q", d, 40)[0]
						nlen = struct.unpack_from("<H", d, 50)[0]
						nume = bytes(d[56:56 + nlen])
						self.intrari.setdefault(k_inum, []).append((nume, inum))
				# XENT (atribute extinse) si celelalte se sar

	def _inod(self, d):
		inum = struct.unpack_from("<I", d, 24)[0]
		size, = struct.unpack_from("<Q", d, 48)
		mtime, = struct.unpack_from("<Q", d, 72)
		nlink, uid, gid, mode, flags, data_len = struct.unpack_from("<IIIIII", d, 92)
		if flags & UBIFS_XATTR_FL:
			return
		date = bytes(d[160:160 + data_len]) if data_len and not stat.S_ISREG(mode) else b""
		self.inoduri[inum] = (mode, uid, gid, size, mtime, nlink, date)

	def total(self):
		return sum(i[3] for i in self.inoduri.values() if stat.S_ISREG(i[0]))

	def continut(self, inum, decomp):
		"""Generator (pozitie, octeti) cu blocurile fisierului, in ordine; golurile raman zero."""
		for bloc, lnum, offs, n in sorted(self.blocuri.get(inum, ())):
			nod = self._nod(lnum, offs, n)
			if nod is None or nod[0] != DATA:
				raise ImagineRea("bloc de date stricat la %d:%d" % (lnum, offs))
			b = nod[2]
			marime, compr = struct.unpack_from("<IH", b, 40)
			yield bloc * UBIFS_BLOCK, decomp(compr, bytes(b[48:]), marime)[:marime]


def _dispozitiv(date):
	if len(date) >= 8:
		v = struct.unpack_from("<Q", date, 0)[0]
		return (v >> 8) & 0xfff, (v & 0xff) | ((v >> 12) & 0xfff00)
	v = struct.unpack_from("<I", date, 0)[0] if len(date) >= 4 else 0
	return (v >> 8) & 0xfff, (v & 0xff) | ((v >> 12) & 0xfff00)


# ---- scrierea

class ScriitorDosar(object):
	"""Scrie in dosar ca root: proprietarii, drepturile, legaturile simbolice si tari, dispozitivele, ora."""

	def __init__(self, dosar):
		self.dosar = dosar
		self.dosare = []
		self.root = hasattr(os, "geteuid") and os.geteuid() == 0

	def _cale(self, rel):
		return os.path.join(self.dosar, rel)

	def _meta(self, cale, i, legatura=False):
		mode, uid, gid, size, mtime, nlink, date = i
		if self.root:
			try:
				os.lchown(cale, uid, gid)
			except OSError:
				pass
		if not legatura:
			os.chmod(cale, stat.S_IMODE(mode))
		try:
			os.utime(cale, (mtime, mtime), follow_symlinks=False)
		except (OSError, NotImplementedError, TypeError):
			pass

	def dosar_(self, rel, i):
		cale = self._cale(rel)
		if not os.path.isdir(cale):
			os.mkdir(cale, 0o700)
		self.dosare.append((cale, i))

	def fisier(self, rel, i, blocuri):
		cale = self._cale(rel)
		with open(cale, "wb") as f:
			for poz, b in blocuri:
				if f.tell() != poz:
					f.seek(poz)
				f.write(b)
				yield len(b)
			f.truncate(i[3])
		self._meta(cale, i)

	def legatura(self, rel, i, tinta):
		cale = self._cale(rel)
		os.symlink(tinta, cale)
		self._meta(cale, i, True)

	def tare(self, rel, i, prima):
		os.link(self._cale(prima), self._cale(rel))

	def special(self, rel, i):
		mode = i[0]
		cale = self._cale(rel)
		if stat.S_ISFIFO(mode):
			os.mkfifo(cale, 0o600)
		elif stat.S_ISSOCK(mode):
			return
		else:
			ma, mi = _dispozitiv(i[6])
			os.mknod(cale, stat.S_IFMT(mode) | 0o600, os.makedev(ma, mi))
		self._meta(cale, i)

	def gata(self):
		for cale, i in reversed(self.dosare):
			self._meta(cale, i)


class ScriitorTar(object):
	"""Acelasi continut intr-o arhiva tar (probele de pe PC; Windows nu are lchown si mknod)."""

	def __init__(self, cale):
		import tarfile
		self.tarfile = tarfile
		self.tf = tarfile.open(cale, "w", format=tarfile.GNU_FORMAT)

	def _info(self, rel, i):
		t = self.tarfile.TarInfo(rel)
		t.uid, t.gid = i[1], i[2]
		t.mode = stat.S_IMODE(i[0])
		t.mtime = i[4]
		return t

	def dosar_(self, rel, i):
		t = self._info(rel, i)
		t.type = self.tarfile.DIRTYPE
		self.tf.addfile(t)

	def fisier(self, rel, i, blocuri):
		import io
		buf = bytearray()
		for poz, b in blocuri:
			if len(buf) < poz:
				buf.extend(b"\0" * (poz - len(buf)))
			buf[poz:poz + len(b)] = b
			yield len(b)
		del buf[i[3]:]
		buf.extend(b"\0" * (i[3] - len(buf)))
		t = self._info(rel, i)
		t.size = len(buf)
		self.tf.addfile(t, io.BytesIO(bytes(buf)))

	def legatura(self, rel, i, tinta):
		t = self._info(rel, i)
		t.type = self.tarfile.SYMTYPE
		t.linkname = tinta
		self.tf.addfile(t)

	def tare(self, rel, i, prima):
		t = self._info(rel, i)
		t.type = self.tarfile.LNKTYPE
		t.linkname = prima
		self.tf.addfile(t)

	def special(self, rel, i):
		mode = i[0]
		t = self._info(rel, i)
		if stat.S_ISFIFO(mode):
			t.type = self.tarfile.FIFOTYPE
		elif stat.S_ISSOCK(mode):
			return
		else:
			t.type = self.tarfile.BLKTYPE if stat.S_ISBLK(mode) else self.tarfile.CHRTYPE
			t.devmajor, t.devminor = _dispozitiv(i[6])
		self.tf.addfile(t)

	def gata(self):
		self.tf.close()


def _nume(b):
	return b.decode("utf-8", "surrogateescape")


def desface(cale_ubi, scriitor, progres=None):
	"""Scrie tot sistemul de fisiere din `cale_ubi` prin `scriitor`. Intoarce (fisiere, dosare, legaturi, octeti)."""
	decomp = Decompresie()
	nr = {"fis": 0, "dos": 0, "leg": 0, "oct": 0}
	with open(cale_ubi, "rb") as f:
		fs = Ubifs(Ubi(f))
		total = fs.total() or 1
		prime = {}
		urmator = [PROGRES_PAS]
		stiva = [(1, "")]
		while stiva:
			parinte, cale = stiva.pop()
			for nume, inum in sorted(fs.intrari.get(parinte, ())):
				n = _nume(nume)
				if not n or n in (".", "..") or "/" in n:
					continue
				i = fs.inoduri.get(inum)
				if i is None:
					continue
				rel = cale + "/" + n if cale else n
				mode = i[0]
				if stat.S_ISDIR(mode):
					scriitor.dosar_(rel, i)
					nr["dos"] += 1
					stiva.append((inum, rel))
				elif stat.S_ISREG(mode):
					if i[5] > 1 and inum in prime:
						scriitor.tare(rel, i, prime[inum])
					else:
						for n_oct in scriitor.fisier(rel, i, fs.continut(inum, decomp)):
							nr["oct"] += n_oct
							if progres and nr["oct"] >= urmator[0]:
								urmator[0] = nr["oct"] + PROGRES_PAS
								progres(nr["oct"], total)
						if i[5] > 1:
							prime[inum] = rel
					nr["fis"] += 1
				elif stat.S_ISLNK(mode):
					scriitor.legatura(rel, i, _nume(i[6]))
					nr["leg"] += 1
				else:
					scriitor.special(rel, i)
		scriitor.gata()
		if progres:
			progres(nr["oct"], total)
	return nr["fis"], nr["dos"], nr["leg"], nr["oct"]


def main(argv):
	if len(argv) != 3:
		sys.stderr.write("folosire: HdsCititorUbi.py rootfs.ubi dosar|iesire.tar\n")
		return 1

	def progres(n, total):
		sys.stdout.write("P %d %d\n" % (n, total))
		sys.stdout.flush()
	try:
		if argv[2].endswith(".tar"):
			scriitor = ScriitorTar(argv[2])
		else:
			if not os.path.isdir(argv[2]):
				os.makedirs(argv[2])
			scriitor = ScriitorDosar(argv[2])
		rez = desface(argv[1], scriitor, progres)
	except ImagineRea as e:
		sys.stderr.write("imagine rea: %s\n" % e)
		return 2
	except (IOError, OSError, struct.error, IndexError, zlib.error) as e:
		sys.stderr.write("eroare: %r\n" % (e,))
		return 3
	sys.stdout.write("GATA %d %d %d %d\n" % rez)
	sys.stdout.flush()
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv))
