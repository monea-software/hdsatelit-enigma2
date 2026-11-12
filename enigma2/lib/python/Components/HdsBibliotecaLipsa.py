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
#     cade la pornirea receptorului, inainte ca omul sa deschida ceva.
# Un program pentru alt procesor (alt e_machine) nu cere nimic: nicio biblioteca nu l-ar porni. Nu importa enigma la incarcare
# (probele de pe PC); RADACINA pune un dosar in fata cailor, numai la probe. Nu arunca.
import os
import struct

RADACINA = ""
DOSARE = ("/lib", "/usr/lib")
ELF_MAXIM = 64 * 1024 * 1024
ANTET_MAXIM = 1024 * 1024
NUME_MAXIM = 255

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
	try:
		cale = _c(cale)
		if not os.path.isfile(cale) or os.path.getsize(cale) > ELF_MAXIM:
			return None
		with open(cale, "rb") as f:
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
			if dinamic:
				_t, off, _v, filesz = dinamic[0]
				pas = 8 if clasa == 1 else 16
				brut = citeste(off, min(filesz, 64 * 1024))
				needed, strtab = [], None
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
			return machine, interpretor, biblioteci
	except (OSError, IOError, struct.error, ValueError) as e:
		_jurnal("%s: %r" % (cale, e))
		return None


def _exista(nume):
	return any(os.path.exists(_c(d + "/" + nume)) for d in DOSARE)


def lipsa(cale, harta=None):
	"""Bibliotecile (si interpretorul) programului de la `cale` care lipsesc si pe care feedul nostru le are: [(nume, pachet)].
	`harta`: {nume: pachet}, implicit HdsModuleLipsa.BIBLIOTECI."""
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
