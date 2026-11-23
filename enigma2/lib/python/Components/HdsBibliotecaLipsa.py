# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsBibliotecaLipsa.py: un program al altora (de obicei un modul de acces pus de mana, adus de pe stick sau din copia altei imagini)
# care nu porneste fiindca ii lipseste o biblioteca veche pe care feedul nostru o are (OpenSSL 1.0, 1.1, 3, libcrypt.so.1,
# incarcatorul ARM /lib/ld-linux.so.3) primeste pachetul singur, fara intrebare (Eduard, 11.11.2026 21:55: „omul nu face nimic”).
#
# Ce face: citeste antetul ELF al programului (interpretorul PT_INTERP si bibliotecile DT_NEEDED), le cauta in /lib si /usr/lib si,
# pentru cele lipsa care sunt in harta bibliotecilor (Components/HdsModuleLipsa.BIBLIOTECI), pune pachetul in coada lui HdsModuleLipsa
# (aceeasi lucrare opkg, acelasi mesaj mic pe ecran, numai din feedurile HD Satelit). Dupa instalare modulul porneste din nou singur.
# Cand:
#   - un modul de acces care nu a pornit (Components/HdsModuleAcces._dupa_operatie, motivul nu_a_pornit): ecranul modulelor, pagina
#     web, importul din alta imagine (HdsImportSurse alege modulul prin aceeasi Operatie);
#   - la pornirea interfetei, pentru modulul ales al fiecarui fel (verificaAlese, din HdsModuleLipsa.porneste): un modul ales care
#     cade la pornirea receptorului, inainte ca omul sa deschida ceva;
#   - 0.7.8: un plugin al carui modul .so nu porneste fiindca ii lipseste o biblioteca (lipsaPlugin, din
#     HdsModuleLipsa.cereBibliotecilePluginului): toate bibliotecile lipsa ale modulelor lui, nu numai prima spusa de dlopen.
# Un program pentru alt procesor (alt e_machine) nu cere nimic: nicio biblioteca nu l-ar porni. Nu importa enigma la incarcare
# (probele de pe PC); RADACINA pune un dosar in fata cailor, numai la probe. Nu arunca.
#
# Legaturile straine: preinst-ul unor pachete de module ale altora (ncam, oscam) face, cand gaseste libssl3,
# `ln -s libssl.so.3 /usr/lib/libssl.so.1.0.0` si `ln -s /usr/lib/libssl.so.3 /lib/libssl.so.1.0.0` (la fel .1.1 si libcrypto).
# Programul se incarca prin legatura, dar functiile scoase dupa OpenSSL 1.0 (EVP_MD_CTX_create) nu sunt acolo. O legatura care nu
# e a niciunui pachet opkg (nu e in /var/lib/opkg/info/*.list) si duce la o biblioteca cu alt nume si alt SONAME e straina. Biblioteca
# e lipsa cand toate caile ei din /lib si /usr/lib sunt legaturi straine; pachetul nostru cerut le sterge (preinst-ul lui). Cand
# fisierul adevarat exista langa o legatura straina, incarcatorul il ia pe el (prin /etc/ld.so.cache) si nu se cere nimic.
#
# Instalarea unui .ipk din fisier (Extensii, pe televizor si in web, 0.7.8): pachetele de module ale altora sunt de obicei un singur
# .ipk "all" cu programele pentru toate procesoarele (ARM, MIPS, AARCH64, SH4 in dosare separate), iar preinst-ul unora iese cu 1 cand
# nu gaseste OpenSSL 1.x pe receptor, inainte sa existe vreun program de pornit. pentruIpk() citeste din data.tar numai programele ELF
# ale procesorului receptorului (antetul intai, fara sa ruleze ceva) si spune ce biblioteci din harta le lipsesc; pachetePentruIpk()
# le pastreaza numai pe cele pe care listele opkg le au din feedul nostru. Components/HdsExtensiiLucru.Lucrare le pune intr-o rulare
# opkg separata, inaintea fisierului: intr-o singura comanda opkg ruleaza preinst-urile tuturor pachetelor inainte sa despacheteze
# ceva, iar un preinst cazut opreste tot (probat pe Octagon 0.7.7, opkg 0.10.0, in ambele ordini).
import io
import os
import posixpath
import struct
import tarfile
import time
import zlib

RADACINA = ""
DOSARE = ("/lib", "/usr/lib")
OPKG_INFO = "/var/lib/opkg/info"
ELF_MAXIM = 64 * 1024 * 1024
ANTET_MAXIM = 1024 * 1024
NUME_MAXIM = 255
# limitele citirii unui .ipk (pe firul lucrarii din Extensii); la orice limita nu se cere nimic, fisierul se instaleaza ca pana acum
IPK_MAXIM = 64 * 1024 * 1024        # cel mai mare fisier .ipk citit
DATE_MAXIM = 160 * 1024 * 1024      # cat se dezarhiveaza cel mult din data.tar
MEMBRI_MAXIM = 20000
PROGRAM_MAXIM = 32 * 1024 * 1024    # un program mai mare nu se citeste in memorie
TIMP_IPK_S = 20.0
_ERORI_IPK = (tarfile.TarError, OSError, IOError, EOFError, ValueError, zlib.error, struct.error, MemoryError)
try:
	import lzma
	_ERORI_IPK += (lzma.LZMAError,)
except ImportError:
	pass

# e_machine al procesorului receptorului, dupa os.uname().machine
_MASINI = {"arm": 40, "aarch64": 183, "mips": 8, "sh4": 42, "x86_64": 62, "i686": 3, "i386": 3}


def _jurnal(text):
	print("[HdsBibliotecaLipsa] %s" % text)


def _c(cale):
	return RADACINA + cale if RADACINA else cale


def masinaNoastra():
	"""e_machine asteptat pe receptor, sau None cand nu se stie"""
	try:
		m = os.uname()[4].lower()
	except (AttributeError, OSError):
		return None
	for prefix, cod in _MASINI.items():
		if m.startswith(prefix):
			return cod
	return None


def citesteElf(cale):
	"""(masina, interpretor, [biblioteci DT_NEEDED]) dintr-un ELF dinamic, sau None (nu e ELF, e stricat, nu se poate citi)."""
	r = _citesteElf(cale)
	return r[:3] if r else None


def _citesteElf(cale):
	"""(masina, interpretor, [biblioteci DT_NEEDED], SONAME sau "") dintr-un ELF dinamic, sau None. `cale`: calea fisierului sau un
	fisier deschis, cu seek (un program citit in memorie din .ipk, pentruIpk)."""
	try:
		if isinstance(cale, str):
			cale = _c(cale)
			if not os.path.isfile(cale) or os.path.getsize(cale) > ELF_MAXIM:
				return None
			f = open(cale, "rb")
		else:
			f = cale
		with f:
			date = f.read(ANTET_MAXIM)
			if date[:4] != b"\x7fELF" or len(date) < 52:
				return None
			clasa, ordine = date[4], date[5]
			if clasa not in (1, 2) or ordine not in (1, 2):
				return None
			o = "<" if ordine == 1 else ">"
			if clasa == 1:
				machine, = struct.unpack_from(o + "H", date, 18)
				phoff, = struct.unpack_from(o + "I", date, 28)
				phentsize, phnum = struct.unpack_from(o + "HH", date, 42)
			else:
				if len(date) < 64:
					return None
				machine, = struct.unpack_from(o + "H", date, 18)
				phoff, = struct.unpack_from(o + "Q", date, 32)
				phentsize, phnum = struct.unpack_from(o + "HH", date, 54)
			if phnum > 128 or phentsize < (32 if clasa == 1 else 56):
				return None
			segmente = []
			for i in range(phnum):
				p = phoff + i * phentsize
				f.seek(p)
				h = f.read(phentsize)
				if len(h) < phentsize:
					return None
				if clasa == 1:
					tip, off, vaddr, _pa, filesz = struct.unpack_from(o + "IIIII", h, 0)
				else:
					tip, _fl, off, vaddr, _pa, filesz = struct.unpack_from(o + "IIQQQQ", h, 0)
				segmente.append((tip, off, vaddr, filesz))

			def citeste(off, n):
				f.seek(off)
				return f.read(n)

			interpretor = ""
			for tip, off, _v, filesz in segmente:
				if tip == 3 and 0 < filesz <= 4096:  # PT_INTERP
					interpretor = citeste(off, filesz).split(b"\0", 1)[0].decode("ascii", "replace")
			dinamic = [s for s in segmente if s[0] == 2]  # PT_DYNAMIC
			incarcate = [s for s in segmente if s[0] == 1]  # PT_LOAD
			biblioteci = []
			soname = ""
			if dinamic:
				_t, off, _v, filesz = dinamic[0]
				pas = 8 if clasa == 1 else 16
				brut = citeste(off, min(filesz, 64 * 1024))
				needed, strtab, so = [], None, None
				for j in range(0, len(brut) - pas + 1, pas):
					if clasa == 1:
						tag, val = struct.unpack_from(o + "iI", brut, j)
					else:
						tag, val = struct.unpack_from(o + "qQ", brut, j)
					if tag == 0:
						break
					if tag == 1:
						needed.append(val)
					elif tag == 5:
						strtab = val
					elif tag == 14:  # DT_SONAME
						so = val
				if strtab is not None:
					baza = None
					for _t2, off2, vaddr2, filesz2 in incarcate:
						if vaddr2 <= strtab < vaddr2 + filesz2:
							baza = off2 + (strtab - vaddr2)
							break
					if baza is not None:
						for n in needed[:64]:
							s = citeste(baza + n, NUME_MAXIM + 1).split(b"\0", 1)[0]
							if s:
								biblioteci.append(s.decode("ascii", "replace"))
						if so is not None:
							soname = citeste(baza + so, NUME_MAXIM + 1).split(b"\0", 1)[0].decode("ascii", "replace")
			return machine, interpretor, biblioteci, soname
	except (OSError, IOError, struct.error, ValueError) as e:
		_jurnal("%s: %r" % (cale, e))
		return None


def _exista(nume):
	"""Biblioteca `nume` se gaseste in /lib sau /usr/lib: un fisier sau o legatura care nu e straina (legaturiStraine)."""
	cai = [d + "/" + nume for d in DOSARE if os.path.exists(_c(d + "/" + nume))]
	if not cai:
		return False
	straine = legaturiStraine(nume)
	return any(c not in straine for c in cai)


def _tinta(cale):
	"""Calea (fara RADACINA) a fisierului la care duce legatura `cale`, urmarita pas cu pas, sau None (lipsa, bucla)."""
	for _i in range(8):
		p = _c(cale)
		if not os.path.islink(p):
			return cale if os.path.exists(p) else None
		t = os.readlink(p).replace("\\", "/")
		cale = os.path.normpath(t if t.startswith("/") else os.path.dirname(cale) + "/" + t).replace("\\", "/")
		cale = "/" + cale.lstrip("/")
	return None


def _aleUnuiPachet(cai):
	"""Din `cai` (fara RADACINA), cele scrise in lista unui pachet opkg instalat (/var/lib/opkg/info/*.list, randuri cale TAB mod)."""
	cai = set(cai)
	gasite = set()
	try:
		d = _c(OPKG_INFO)
		for n in os.listdir(d):
			if not n.endswith(".list"):
				continue
			try:
				with open(os.path.join(d, n), "rb") as f:
					for r in f:
						c = r.split(b"\t", 1)[0].strip().decode("utf-8", "replace")
						if c in cai:
							gasite.add(c)
			except (IOError, OSError):
				pass
			if gasite == cai:
				break
	except (IOError, OSError):
		pass
	return gasite


def legaturiStraine(nume):
	"""Legaturile cu numele `nume` din /lib si /usr/lib puse de altii (nu sunt in lista niciunui pachet opkg) care duc la o biblioteca
	cu alt nume si alt SONAME (de pilda libssl.so.1.0.0 -> libssl.so.3) sau nicaieri: [cai fara RADACINA]."""
	candidati = []
	for d in DOSARE:
		cale = d + "/" + nume
		if not os.path.islink(_c(cale)):
			continue
		tinta = _tinta(cale)
		if tinta is not None:
			if os.path.basename(tinta) == nume:
				continue
			r = _citesteElf(tinta)
			if r and r[3] == nume:
				continue
		candidati.append(cale)
	if not candidati:
		return []
	ale = _aleUnuiPachet(candidati)
	return [c for c in candidati if c not in ale]


def lipsa(cale, harta=None):
	"""Bibliotecile (si interpretorul) programului de la `cale` care lipsesc si pe care feedul nostru le are: [(nume, pachet)].
	O biblioteca data numai de legaturi straine (legaturiStraine) e lipsa. `harta`: {nume: pachet}, implicit HdsModuleLipsa.BIBLIOTECI."""
	if harta is None:
		try:
			from Components.HdsModuleLipsa import BIBLIOTECI as harta
		except ImportError:
			from HdsModuleLipsa import BIBLIOTECI as harta
	elf = citesteElf(cale)
	if elf is None:
		return []
	masina, interpretor, biblioteci = elf
	noi = masinaNoastra()
	if noi is not None and masina != noi:
		return []
	rez = []
	if interpretor.startswith("/") and not os.path.exists(_c(interpretor)):
		nume = interpretor.rsplit("/", 1)[-1]
		if nume in harta:
			rez.append((nume, harta[nume]))
	for b in biblioteci:
		if "/" in b or b in [r[0] for r in rez]:
			continue
		if b in harta and not _exista(b):
			rez.append((b, harta[b]))
	return rez


def lipsaPlugin(dosar, harta, maxim=64):
	"""0.7.8 (CM1): bibliotecile din `harta` ({nume: pachet}) care lipsesc modulelor native (.so) ale pluginului din `dosar`:
	[(nume, pachet)], fara dubluri. dlopen spune numai prima biblioteca lipsa; asa se cer toate deodata. Se citesc numai antetele
	ELF (lipsa()), cel mult `maxim` fisiere, cel mult trei niveluri de dosare; nimic rulat."""
	rez = []
	try:
		baza = _c(dosar)
		if not os.path.isdir(baza):
			return []
		vazute = 0
		for rad, dosare, fisiere in os.walk(baza):
			adancime = rad[len(baza):].count(os.sep)
			if adancime >= 3:
				del dosare[:]
			for f in sorted(fisiere):
				if not (f.endswith(".so") or ".so." in f):
					continue
				vazute += 1
				if vazute > maxim:
					return rez
				cale = os.path.join(rad, f)
				if RADACINA:
					cale = cale[len(RADACINA):].replace(os.sep, "/")
				for b, p in lipsa(cale, harta):
					if b not in [x[0] for x in rez]:
						rez.append((b, p))
	except Exception as e:
		_jurnal("lipsaPlugin %s: %r" % (dosar, e))
	return rez


def cerePentru(cai, nume, dupa=None):
	"""Pachetele puse in coada pentru programele `cai` (un modul de acces `nume`); `dupa()` se cheama dupa o instalare reusita."""
	try:
		try:
			from Components import HdsModuleLipsa
		except ImportError:
			import HdsModuleLipsa
		puse = []
		for cale in cai:
			for bib, _pachet in lipsa(cale):
				p = HdsModuleLipsa.cereBiblioteca(bib, cale, nume, dupa=dupa)
				if p and p not in puse:
					puse.append(p)
		return puse
	except Exception as e:
		_jurnal("cerePentru: %r" % (e,))
		return []


# ---------------------------------------------------------------- un .ipk instalat din fisier

class _Felie(object):
	"""membrul data.tar.* din arhiva ar a unui .ipk deschis, citit in flux, pana la `marime` octeti"""

	def __init__(self, fh, marime):
		self.fh = fh
		self.ramas = marime

	def read(self, n=-1):
		if self.ramas <= 0:
			return b""
		if n is None or n < 0 or n > self.ramas:
			n = self.ramas
		b = self.fh.read(n)
		self.ramas -= len(b)
		return b


class _Oprit(Exception):
	"""citirea .ipk-ului s-a oprit inainte de sfarsit (o limita, arhiva necunoscuta): nu se stie tot ce cere pachetul"""


def _dateIpk(fh):
	"""fluxul lui data.tar.* dintr-un .ipk deschis: ar ca la Debian, sau tar ca la opkg-build vechi"""
	if fh.read(8) == b"!<arch>\n":
		for _k in range(16):
			antet = fh.read(60)
			if len(antet) < 60:
				break
			nume = antet[:16].strip().rstrip(b"/").decode("ascii", "replace")
			try:
				marime = int(antet[48:58].strip() or b"0")
			except ValueError:
				break
			if nume.startswith("data.tar") and marime > 0:
				return _Felie(fh, marime)
			fh.seek(marime + (marime % 2), 1)
		raise _Oprit("fara data.tar")
	fh.seek(0)
	t = tarfile.open(fileobj=fh, mode="r:*")
	for _k, m in zip(range(16), t):
		if m.isfile() and m.name.lstrip("./").startswith("data.tar"):
			return t.extractfile(m)
	raise _Oprit("fara data.tar")


def _programeIpk(cale, masina, timp_maxim):
	"""([(interpretor, [biblioteci DT_NEEDED])] ale programelor ELF pentru `masina` din data.tar al .ipk-ului `cale`, {numele
	fisierelor si legaturilor din pachet}). Un singur program odata in memorie. _Oprit la o limita."""
	inceput = time.time()
	programe, nume = [], set()
	with open(cale, "rb") as fh:
		with tarfile.open(fileobj=_dateIpk(fh), mode="r|*") as t:
			total = membri = 0
			for m in t:
				membri += 1
				total += max(0, m.size)
				if membri > MEMBRI_MAXIM or total > DATE_MAXIM or time.time() - inceput > timp_maxim:
					raise _Oprit("limita (%d fisiere, %d octeti, %.1f s)" % (membri, total, time.time() - inceput))
				if not (m.isfile() or m.issym() or m.islnk()):
					continue
				nume.add(posixpath.basename(m.name.rstrip("/")))
				if not m.isfile() or m.size < 52:
					continue
				f = t.extractfile(m)
				cap = f.read(20) if f is not None else b""
				if len(cap) < 20 or cap[:4] != b"\x7fELF" or cap[5] not in (1, 2):
					continue
				if struct.unpack_from("<H" if cap[5] == 1 else ">H", cap, 18)[0] != masina:
					continue
				if m.size > PROGRAM_MAXIM:
					raise _Oprit("program prea mare: %s" % m.name)
				r = _citesteElf(io.BytesIO(cap + f.read(m.size - len(cap))))
				if r:
					programe.append((r[1], r[2]))
	return programe, nume


def pentruIpk(cale, harta=None, masina=None, timp_maxim=TIMP_IPK_S):
	"""Bibliotecile din harta (implicit HdsModuleLipsa.BIBLIOTECI) cerute de programele din .ipk-ul `cale` care lipsesc pe receptor
	(ca la lipsa(): si cele date numai de legaturi straine): [(nume, pachet)], in ordinea gasirii, fara dubluri. Se citesc numai
	programele ELF pentru procesorul receptorului (`masina`, implicit masinaNoastra()); o biblioteca pe care pachetul o aduce el
	insusi (un fisier sau o legatura cu acelasi nume oriunde in data.tar) nu se cere. Nimic despachetat pe disc, nimic rulat. []
	cand nu se poate citi tot (arhiva necunoscuta, o limita, procesorul necunoscut)."""
	if harta is None:
		try:
			from Components.HdsModuleLipsa import BIBLIOTECI as harta
		except ImportError:
			from HdsModuleLipsa import BIBLIOTECI as harta
	if masina is None:
		masina = masinaNoastra()
	if masina is None or not isinstance(cale, str):
		return []
	try:
		cale = _c(cale)
		if not os.path.isfile(cale) or os.path.getsize(cale) > IPK_MAXIM:
			return []
		programe, din_pachet = _programeIpk(cale, masina, timp_maxim)
	except _Oprit as e:
		_jurnal("%s: citirea oprita (%s), nu se cere nimic" % (cale, e))
		return []
	except _ERORI_IPK as e:
		_jurnal("%s: %r, nu se cere nimic" % (cale, e))
		return []
	rez = []
	for interpretor, biblioteci in programe:
		cerute = []
		if interpretor.startswith("/") and not os.path.exists(_c(interpretor)):
			cerute.append(interpretor.rsplit("/", 1)[-1])
		cerute += [b for b in biblioteci if "/" not in b and b in harta and not _exista(b)]
		for b in cerute:
			if b in harta and b not in din_pachet and b not in [x[0] for x in rez]:
				rez.append((b, harta[b]))
	return rez


def pachetePentruIpk(cale, harta=None, masina=None, timp_maxim=TIMP_IPK_S):
	"""Ce se pune din feed INAINTEA .ipk-ului `cale`: {"biblioteci": [(nume, pachet)] din pentruIpk, "pachete": [pachetele
	neinstalate pe care listele opkg le au, cea mai noua versiune din feedul nostru], "negasite": [cele pe care listele nu le au
	deloc]}. Un pachet a carui versiune cea mai noua vine dintr-o sursa straina nu se pune. {} la orice eroare."""
	try:
		try:
			from Components import HdsModuleLipsa as ML
		except ImportError:
			import HdsModuleLipsa as ML
		biblioteci = pentruIpk(cale, harta, masina, timp_maxim)
		rez = {"biblioteci": biblioteci, "pachete": [], "negasite": []}
		for _b, pachet in biblioteci:
			if pachet in rez["pachete"] or pachet in rez["negasite"] or ML.instalat(pachet):
				continue
			versiune, motiv = ML.provenienta(pachet)
			if versiune is not None:
				rez["pachete"].append(pachet)
			elif motiv == "lipsa":
				rez["negasite"].append(pachet)
			else:
				_jurnal("%s nu se pune inaintea %s: %s" % (pachet, cale, motiv))
		return rez
	except Exception as e:
		_jurnal("pachetePentruIpk: %r" % (e,))
		return {}


def _executabileModul(fel, sufix):
	try:
		from Components.HdsInterfeteCam import citeste_script
		from Components.HdsModuleAcces import SistemAcces
	except ImportError:
		from HdsInterfeteCam import citeste_script
		from HdsModuleAcces import SistemAcces
	s = citeste_script(SistemAcces(RADACINA or "/"), "%s.%s" % (fel, sufix))
	return sorted(set(s.cai.values()))


_ceasuri = []


def _pornesteDinNou(fel, sufix, incercari=2):
	"""Modulul pornit din nou (Operatie „porneste”); daca alta operatie a modulelor ruleaza chiar atunci („ocupat”), inca o
	incercare peste 10 s."""
	try:
		from Components.HdsModuleAcces import Operatie
		rez = {}
		o = Operatie("porneste", fel, sufix, la_final=rez.update)
		if o.porneste() or rez.get("motiv") != "ocupat" or incercari <= 1:
			return
		from enigma import eTimer
		t = eTimer()
		_ceasuri.append(t)

		def iar():
			if t in _ceasuri:
				_ceasuri.remove(t)
			_pornesteDinNou(fel, sufix, incercari - 1)
		t.callback.append(iar)
		t.start(10000, True)
	except Exception as e:
		_jurnal("pornirea din nou a %s.%s: %r" % (fel, sufix, e))


def dupaCadereModul(fel, sufix):
	"""Un modul de acces care nu a pornit (HdsModuleAcces._dupa_operatie): bibliotecile lipsa din feed, apoi pornit din nou."""
	try:
		if not fel or not sufix:
			return []

		def din_nou():
			_pornesteDinNou(fel, sufix)
		return cerePentru(_executabileModul(fel, sufix), sufix, dupa=din_nou)
	except Exception as e:
		_jurnal("dupaCadereModul: %r" % (e,))
		return []


def verificaAlese():
	"""La pornirea interfetei: modulul ales al fiecarui fel, daca nu ruleaza si ii lipseste o biblioteca din feed."""
	try:
		try:
			from Components.HdsModuleAcces import SistemAcces, citeste, feluri
		except ImportError:
			from HdsModuleAcces import SistemAcces, citeste, feluri
		sistem = SistemAcces(RADACINA or "/")
		puse = []
		for fel in feluri(sistem):
			st = citeste(sistem, fel)
			e = st.ales_emulator()
			if e is None or e.pids:
				continue
			puse += dupaCadereModul(fel, e.sufix)
		return puse
	except Exception as e:
		_jurnal("verificaAlese: %r" % (e,))
		return []
