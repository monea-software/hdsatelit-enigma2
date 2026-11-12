# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCopieImagine.py: copia COMPLETA a imaginii care ruleaza (nucleul si tot sistemul, cu setarile, canalele si
# pluginurile), facuta de receptor pe un stick sau un disc USB, intr-un fisier care se pune inapoi cu instalarea de pe
# stick a imaginii (Meniu > Setari > Software & Firmware > Imagine noua de pe stick, Screens/HdsSoftwareUpdate.py).
# Cerut de JAKITAKI (Satedu p=68457, 08.11.2026, si forumul nostru 768 #1572, 10.11.2026): „Full Backup” fara plugin
# separat. Ecranul: Screens/HdsCopieImagine.py; perechea web: HdsWebControl/copie_imagine_web.py (/copie-imagine).
#
# FORMA = a imaginilor noastre de pe site pentru acelasi model (hdsatelit-image.bb, hds_marcaj_model_zip): un zip
# <nume>_mmc.zip cu e2/update/imageversion (un rand), e2/update/kernel.bin, e2/update/rootfs.tar.bz2 si
# e2/update/hdsatelit-model (marcajul). Marcajul = fisierul de reguli al imaginii care ruleaza (/etc/hdsatelit-model,
# scris la construire din aceleasi randuri ca marcajul de pe site) plus imageversion=, kernel_sha256= si rootfs_sha256=.
# Instalarea il verifica la fel ca pe cel de pe site: HdsPazaModel.verificaPachet (marcajul fata de amprenta
# receptorului), apoi sumele SHA-256 ale fisierelor. Zip-ul sta in RADACINA stickului, acolo unde il cauta instalarea.
#
# Cum se face (mecanismul cunoscut al copiilor complete eMMC, scris de la zero aici):
#   1. nucleul: citit din partitia slotului pornit (kernel= din /proc/cmdline, altfel kernel_part= din reguli), numai
#      cat spune antetul uImage (64 de octeti + marimea din antet), ca fisierul kernel.bin de pe site. Fara antet uImage
#      nu se ghiceste nimic: copia nu se face.
#   2. sistemul: radacina montata inca o data (mount --bind /) intr-un dosar din /tmp, deci numai sistemul de fisiere al
#      radacinii, cu dosarele de sub montari (/dev cu nodurile statice, /media, /tmp goale), fara /proc, /sys, stickuri
#      sau discuri. Arhiva tar (forma GNU, nume „./...”, ca pe site) se comprima bz2 si se scrie DIRECT in zip, pe stick,
#      cu suma SHA-256 socotita din mers: nimic in /tmp (RAM), nimic pe memoria interna (REGULI-FLASH-RECEPTOR, regula 1).
#      Fisierul de swap activ nu intra. Un fisier disparut intre listare si citire se sare; unul care se scurteaza in
#      timpul citirii se completeaza cu zerouri (arhiva ramane buna).
#   3. verificarea, ca la instalare, DE PE STICK: fisierul se scrie pe disc (fsync), paginile lui se scot din memorie,
#      apoi zip-ul se citeste din nou: structura (kernel.bin si rootfs.tar.bz2 in e2/update), marcajul (aceeasi functie a
#      instalarii, cu amprenta receptorului) si sumele SHA-256 recitite. Abia apoi numele de lucru <nume>.zip.partial
#      (pe care instalarea nu il vede) devine <nume>.zip. Oprirea sau orice eroare sterg fisierul de lucru.
# Copia numai CITESTE de pe receptor; nu scrie nimic pe memoria interna. Nu porneste ofgwrite.
#
# Modelele: numai eMMC HiSilicon (toate regulile fara familie=broadcom). Vu+ 4K (familie=broadcom) si Vu+ Solo SE
# (stocare=nand) NU inca: zip-ul Vu+ de pe site are si initrd_auto.bin, splash_auto.bin si mkpart.update, pe care
# receptorul pornit nu le are, iar pe NAND copia ar cere mkfs.ubifs/ubinize/nanddump, care nu sunt in imagine. Fara
# fisierul de reguli (emulatorul de pe PC, alta imagine) copia nu se face: un zip fara marcaj nu s-ar putea instala.
#
# Fisierul nu importa nimic din enigma2 la incarcare; `radacina` (fisierele de reguli, cmdline, mounts) si
# `radacina_arhivei` (ce se arhiveaza) se dau din probele de pe PC (teste/test_copie_imagine_074.py).

import bz2
import hashlib
import os
import re
import shutil
import stat
import struct
import subprocess
import tarfile
import threading
import time
import zipfile

from Components import HdsPazaModel as P


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


SUBCALE = "e2/update"
NUME_KERNEL = "kernel.bin"
NUME_ROOTFS = "rootfs.tar.bz2"
NUME_VERSIUNE = "imageversion"
NUME_MARCAJ = P.NUME_MARCAJ
SUFIX_ZIP = "_mmc.zip"
SUFIX_LUCRU = ".partial"
PREFIX = "hdsatelit-"
CUVANT_COPIE = "-copie-"
DOSAR_LEGARE = "/tmp/hds-copie-imagine-radacina"
MAGIC_UIMAGE = b"\x27\x05\x19\x56"
ANTET_UIMAGE = 64
NUCLEU_MAXIM = 64 * 1024 * 1024
BLOC = 1024 * 1024
NIVEL_BZ2 = 9
# fisierele fara de care imaginea nu porneste (REGULI-FLASH-RECEPTOR, regula 7)
OBLIGATORII = ("./sbin/init", "./sbin/ldconfig", "./usr/bin/enigma2")
# dosarele care intra goale, ca in imaginea de pe site: pe imaginea noastra /run sta pe radacina (nu in RAM), iar pe .122
# (11.11.2026) avea 408 intrari de rulare (pid-uri, baza udev, avahi); puse inapoi, ar strica pornirea serviciilor
GOALE = ("./run",)
# cererile de punere la loc a copiei setarilor (Components/HdsCopieSetari: cerere, inceputa.json) nu intra: puse inapoi
# cu copia completa, prima pornire ar pune peste ea o copie a setarilor
FARA = ("./home/root/hds-restaurare/cerere", "./home/root/hds-restaurare/inceputa.json")
# semnul copiei complete in marcaj: instalarea de pe stick (Screens/HdsSoftwareUpdate.esteCopieCompleta) o pune inapoi
# exact cum a fost facuta, fara copia setarilor de acum. In marcaj, nu in numele fisierului: numele il poate schimba
# omul, iar marcajul e chiar fisierul pe care instalarea il citeste si il verifica (reguliValide trece peste cheile in plus).
CHEIE_COPIE = "copie_completa"
# locul cerut: nucleul + 60 % din octetii radacinii (pe site bz2 da 41 %) + rezerva; in timpul scrierii, sub REZERVA_MINIMA
# libera copia se opreste (stickul nu se umple pana la capat)
RAPORT_LOC = 0.6
REZERVA_LOC = 64 * 1024 * 1024
REZERVA_MINIMA = 16 * 1024 * 1024
LIMITA_FARA_ZIP64 = 1536 * 1024 * 1024
_USB_RX = re.compile(r"^/dev/sd[a-z]+[0-9]*$")
_NUME_RX = re.compile(r"[^A-Za-z0-9_.+-]")
_KERNEL_RX = re.compile(r"^mmcblk[0-9]+p[0-9]+$")

PAS_NUCLEU, PAS_SISTEM, PAS_VERIFICARE = 1, 2, 3
PASI = 3

# de ce nu se poate face copia pe acest receptor (suport())
NU_REGULI = "fara-reguli"
NU_VUPLUS = "vuplus"
NU_NAND = "nand"


class Oprita(Exception):
	"""Omul a oprit copia."""


class EroareCopie(Exception):
	"""O eroare cu text pentru om (fara „Copia nu s-a făcut:” in fata)."""


# ------------------------------------------------------------------------------------------- receptorul

def _cale(radacina, rel):
	return os.path.join(radacina or "/", rel.lstrip("/"))


def _citesteText(cale, maxim=65536):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except OSError:
		return None


def textReguli(radacina=None):
	"""Fisierul de reguli al imaginii care ruleaza, ca text (None cand lipseste)."""
	return _citesteText(_cale(radacina, P.FISIER_REGULI), P.MARIME_MAXIMA_TEXT)


def suport(radacina=None):
	"""(True, "") cand copia se poate face pe acest receptor; altfel (False, NU_*)."""
	reguli = P.citesteReguli(radacina)
	if not reguli:
		return False, NU_REGULI
	if P.nand(reguli):
		return False, NU_NAND
	if P.broadcom(reguli):
		return False, NU_VUPLUS
	return True, ""


def textSuport(motiv):
	if motiv == NU_VUPLUS:
		return _("Pe receptoarele Vu+ copia completă a imaginii nu se poate face încă. Fă copia setărilor (Meniu, Setări, "
			"Software & Firmware, Copia setărilor): ea păstrează canalele, setările și pluginurile, iar imaginea o iei de pe site.")
	if motiv == NU_NAND:
		return _("Pe acest receptor copia completă a imaginii nu se poate face încă. Fă copia setărilor (Meniu, Setări, "
			"Software & Firmware, Copia setărilor): ea păstrează canalele, setările și pluginurile, iar imaginea o iei de pe site.")
	return _("Imaginea care rulează nu spune pentru ce receptor este, deci copia ei nu s-ar putea pune înapoi. Copia "
		"completă se face numai pe imaginea HD Satelit pornită din memoria receptorului.")


def dispozitivNucleu(reguli, cmdline):
	"""„mmcblk0p9”: partitia nucleului pornit (kernel= din /proc/cmdline, pe pornirea multipla slotul ales), altfel
	kernel_part= din reguli. "" cand niciuna nu e o partitie eMMC."""
	kp, _rsd = P.nucleuPornit(cmdline)
	for candidat in (kp, (reguli or {}).get("kernel_part", "")):
		if candidat and _KERNEL_RX.match(candidat):
			return candidat
	return ""


def marimeUimage(antet):
	"""Octetii nucleului dupa antetul uImage (64 + marimea datelor); None fara antet uImage."""
	if len(antet) < ANTET_UIMAGE or antet[:4] != MAGIC_UIMAGE:
		return None
	return ANTET_UIMAGE + struct.unpack(">I", antet[12:16])[0]


def citesteNucleu(cale_dispozitiv):
	"""Nucleul din partitie, taiat la marimea din antetul uImage. EroareCopie cand nu se poate citi sau nu are antet."""
	try:
		with open(cale_dispozitiv, "rb") as f:
			antet = f.read(ANTET_UIMAGE)
			marime = marimeUimage(antet)
			if marime is None:
				raise EroareCopie(_("Nucleul receptorului nu are forma cunoscută, deci copia nu se poate face."))
			f.seek(0, os.SEEK_END)
			partitie = f.tell()
			if marime <= ANTET_UIMAGE or marime > min(partitie, NUCLEU_MAXIM):
				raise EroareCopie(_("Nucleul receptorului nu are forma cunoscută, deci copia nu se poate face."))
			f.seek(0)
			date = f.read(marime)
	except EroareCopie:
		raise
	except OSError:
		raise EroareCopie(_("Nucleul receptorului nu se poate citi, deci copia nu se poate face."))
	if len(date) != marime:
		raise EroareCopie(_("Nucleul receptorului nu se poate citi, deci copia nu se poate face."))
	return date


def montari(radacina=None):
	"""[(dispozitiv, punct, tip)] din /proc/mounts (punctul decodat: \\040 = spatiu)."""
	text = _citesteText(_cale(radacina, "proc/mounts"), 262144) or ""
	rez = []
	for rand in text.splitlines():
		parti = rand.split()
		if len(parti) < 3:
			continue
		punct = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), parti[1])
		rez.append((parti[0], punct, parti[2]))
	return rez


def _octetiLiberi(punct):
	try:
		return shutil.disk_usage(punct).free  # statvfs: f_bavail * f_frsize
	except OSError:
		return 0


def _nume(punct):
	return os.path.basename(punct.rstrip("/")) or punct


def _gb(octeti):
	return "%.1f GB" % (octeti / 1e9)


def medii(radacina=None, root_dev=None):
	"""Stickurile si discurile USB pe care se poate scrie: [{"id": punctul, "nume": text, "liber": octeti}]. Numai
	/dev/sd* (ca paznicul instalarii, Tools/MediuImagine), niciodata memoria interna sau dispozitivul radacinii; un
	dispozitiv montat de doua ori apare o data."""
	if root_dev is None:
		try:
			root_dev = os.stat("/").st_dev
		except OSError:
			root_dev = None
	vazute = set()
	rez = []
	for dispozitiv, punct, _tip in montari(radacina):
		if not _USB_RX.match(dispozitiv) or dispozitiv in vazute or punct == "/":
			continue
		try:
			if root_dev is not None and os.stat(punct).st_dev == root_dev:
				continue
		except OSError:
			continue
		if not os.access(punct, os.W_OK):
			continue
		vazute.add(dispozitiv)
		liber = _octetiLiberi(punct)
		rez.append({"id": punct, "nume": _("%s (%s liberi)") % (_nume(punct), _gb(liber)), "liber": liber,
			"dispozitiv": dispozitiv})
	return rez


def mediuImplicit(lista):
	"""Locul cu cel mai mult loc liber (omul nu are de ales nimic cand are un singur stick)."""
	return max(lista, key=lambda m: m["liber"]) if lista else None


def _swapuri(radacina=None):
	text = _citesteText(_cale(radacina, "proc/swaps"), 8192) or ""
	return set(r.split()[0] for r in text.splitlines()[1:] if r.split())


def numeCopie(versiune, masina, acum=None):
	"""„hdsatelit-0.7.4-viper4kv20-copie-20261111-1930”: aceeasi forma ca imaginile de pe site (instalarea scoate din
	el versiunea si data), cu „copie” in nume."""
	t = time.localtime(acum if acum is not None else time.time())
	nume = "%s%s-%s%s%s" % (PREFIX, versiune or "0", masina or "receptor", CUVANT_COPIE, time.strftime("%Y%m%d-%H%M", t))
	return _NUME_RX.sub("", nume)


def marcaj(text_reguli, versiune_imagine, sume):
	"""Marcajul copiei: regulile imaginii care ruleaza, ca atare, plus imageversion= si sumele (ca hds_marcaj_model_zip)."""
	baza = text_reguli if text_reguli.endswith("\n") else text_reguli + "\n"
	return baza + "%s=da\nimageversion=%s\nkernel_sha256=%s\nrootfs_sha256=%s\n" % (
		CHEIE_COPIE, versiune_imagine, sume["kernel_sha256"], sume["rootfs_sha256"])


# ------------------------------------------------------------------------------------------- scrierea

class _ScriitorBz2(object):
	"""Obiect-fisier pentru tarfile: comprima bz2, scrie in `dest` (intrarea din zip) si socoteste SHA-256 a ce scrie."""

	def __init__(self, dest, verifica=None):
		self._dest = dest
		self._comp = bz2.BZ2Compressor(NIVEL_BZ2)
		self.sha = hashlib.sha256()
		self.scrisi = 0
		self._verifica = verifica

	def _scrie(self, date):
		if date:
			self._dest.write(date)
			self.sha.update(date)
			self.scrisi += len(date)
			if self._verifica is not None:
				self._verifica(self.scrisi)

	def write(self, date):
		self._scrie(self._comp.compress(date))
		return len(date)

	def termina(self):
		self._scrie(self._comp.flush())


class _CititorFix(object):
	"""Citeste exact `marime` octeti dintr-un fisier: daca fisierul s-a scurtat, restul e zero; daca a crescut, se taie.
	Numara octetii in progres."""

	def __init__(self, f, marime, progres, oprit):
		self._f = f
		self._rest = marime
		self._progres = progres
		self._oprit = oprit

	def read(self, n=-1):
		if self._oprit is not None and self._oprit():
			raise Oprita()
		if n is None or n < 0 or n > self._rest:
			n = self._rest
		if n <= 0:
			return b""
		date = self._f.read(n)
		if len(date) < n:
			date += b"\0" * (n - len(date))
		self._rest -= n
		if self._progres is not None:
			self._progres["gata"] = self._progres.get("gata", 0) + n
		return date


def numaraRadacina(radacina_arhivei, exclus=()):
	"""(octeti in fisierele obisnuite, numarul intrarilor) sub `radacina_arhivei`, fara a urma legaturile."""
	octeti = intrari = 0
	vazute = set()  # legaturile tari se citesc o singura data
	for dosar, dosare, fisiere in os.walk(radacina_arhivei):
		dosare.sort()
		_tai(radacina_arhivei, dosar, dosare)
		for nume in dosare + fisiere:
			intrari += 1
			cale = os.path.join(dosar, nume)
			if cale in exclus:
				continue
			try:
				st = os.lstat(cale)
			except OSError:
				continue
			if stat.S_ISREG(st.st_mode):
				if st.st_nlink > 1:
					if (st.st_dev, st.st_ino) in vazute:
						continue
					vazute.add((st.st_dev, st.st_ino))
				octeti += st.st_size
	return octeti, intrari + 1


def _tai(radacina_arhivei, dosar, dosare):
	"""os.walk nu mai intra in dosarele GOALE (ele intra in arhiva numai ca dosar)."""
	rel = os.path.relpath(dosar, radacina_arhivei)
	baza = "." if rel == "." else "./" + rel.replace(os.sep, "/")
	dosare[:] = [d for d in dosare if baza + "/" + d not in GOALE]


def scrieArhiva(tar, radacina_arhivei, progres=None, oprit=None, exclus=()):
	"""Toata radacina in `tar`, in ordinea dosarelor: „.” intai, apoi fiecare dosar cu intrarile lui. Intoarce
	(numele „./...” vazute dintre OBLIGATORII, numarul fisierelor sarite)."""
	vazute = set()
	sarite = 0

	def adauga(cale, arc):
		nonlocal sarite
		if oprit is not None and oprit():
			raise Oprita()
		try:
			info = tar.gettarinfo(cale, arcname=arc)
		except OSError:
			sarite += 1
			return
		if info is None:  # socket: nu intra in arhiva
			return
		if arc in FARA:
			return
		if arc in OBLIGATORII:
			vazute.add(arc)
		if info.isreg():
			try:
				f = open(cale, "rb")
			except OSError:
				sarite += 1
				return
			with f:
				tar.addfile(info, _CititorFix(f, info.size, progres, oprit))
		else:
			tar.addfile(info)

	adauga(radacina_arhivei, ".")
	for dosar, dosare, fisiere in os.walk(radacina_arhivei):
		dosare.sort()
		fisiere.sort()
		rel = os.path.relpath(dosar, radacina_arhivei)
		baza = "." if rel == "." else "./" + rel.replace(os.sep, "/")
		for nume in dosare + fisiere:
			cale = os.path.join(dosar, nume)
			if cale in exclus:
				continue
			adauga(cale, baza + "/" + nume)
		_tai(radacina_arhivei, dosar, dosare)
	return vazute, sarite


def _legatSub(punct, radacina=None):
	"""True cand ceva e montat pe `punct`. /proc/mounts arata calea adevarata: pe receptor /tmp e o legatura spre
	/var/volatile/tmp (gasit pe .122, 11.11.2026), deci se compara si calea cu legaturile rezolvate."""
	cai = {punct, os.path.realpath(punct)}
	return any(p in cai for _d, p, _t in montari(radacina))


def legaRadacina(dosar=DOSAR_LEGARE):
	"""Radacina montata inca o data in `dosar` (mount --bind /). O legare ramasa de la o copie cazuta se scoate intai;
	daca legarea nu se poate dovedi, se scoate si ea (nimic ramas montat)."""
	if _legatSub(dosar):
		dezlegaRadacina(dosar)
	os.makedirs(dosar, exist_ok=True)
	if subprocess.call(["mount", "--bind", "/", dosar]) != 0 or not _legatSub(dosar):
		dezlegaRadacina(dosar)
		raise EroareCopie(_("Sistemul nu s-a putut pregăti pentru copiere, deci copia nu se poate face."))
	return dosar


def dezlegaRadacina(dosar=DOSAR_LEGARE):
	for argumente in (["umount", dosar], ["umount", "-l", dosar]):
		if not _legatSub(dosar) and not os.path.ismount(dosar):
			break
		subprocess.call(argumente)
	try:
		if not _legatSub(dosar) and not os.path.ismount(dosar):
			os.rmdir(dosar)
	except OSError:
		pass


def _intrare(nume):
	"""Intrarea din zip: e2/update/<nume>, ora de acum, drepturile 0644, fara comprimare (bz2 e deja comprimat)."""
	info = zipfile.ZipInfo(SUBCALE + "/" + nume, time.localtime(time.time())[:6])
	info.compress_type = zipfile.ZIP_STORED
	info.external_attr = (stat.S_IFREG | 0o644) << 16
	return info


def _sterge(cale):
	try:
		os.remove(cale)
	except OSError:
		pass


def _scoateDinMemorie(cale):
	"""Paginile fisierului scrise pe disc si scoase din memorie: citirea de dupa vine de pe stick."""
	try:
		fd = os.open(cale, os.O_RDONLY)
		try:
			os.fsync(fd)
			if hasattr(os, "posix_fadvise"):
				os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
		finally:
			os.close(fd)
	except OSError:
		pass


def scrieZip(f, nucleu, radacina_arhivei, text_reguli, versiune_imagine, octeti, progres=None, oprit=None, exclus=(),
		verificaLoc=None):
	"""Zip-ul copiei in obiectul-fisier `f` (fisierul de pe stick; in proba de pe .122, fara stick, iesirea ssh spre PC):
	imageversion, kernel.bin, rootfs.tar.bz2 (tar GNU -> bz2, cu SHA-256 din mers) si marcajul. Intoarce numarul
	fisierelor sarite; EroareCopie cand lipsesc fisierele de pornire."""
	sume = {"kernel_sha256": hashlib.sha256(nucleu).hexdigest()}
	with zipfile.ZipFile(f, "w", allowZip64=True) as z:
		z.writestr(_intrare(NUME_VERSIUNE), versiune_imagine + "\n")
		z.writestr(_intrare(NUME_KERNEL), nucleu)
		with z.open(_intrare(NUME_ROOTFS), "w", force_zip64=octeti > LIMITA_FARA_ZIP64) as dest:
			scriitor = _ScriitorBz2(dest, verificaLoc)
			with tarfile.open(fileobj=scriitor, mode="w|", format=tarfile.GNU_FORMAT) as tar:
				tar.copybufsize = BLOC  # bucati de 1 MiB: mai putine treceri prin Python, interfata ramane vie
				vazute, sarite = scrieArhiva(tar, radacina_arhivei, progres, oprit, exclus)
			scriitor.termina()
		lipsa = [n[2:] for n in OBLIGATORII if n not in vazute]
		if lipsa:
			raise EroareCopie(_("În sistem lipsesc fișiere de pornire (%s), deci copia nu ar porni.") % ", ".join(lipsa))
		sume["rootfs_sha256"] = scriitor.sha.hexdigest()
		z.writestr(_intrare(NUME_MARCAJ), marcaj(text_reguli, versiune_imagine, sume))
	return sarite


def faCopia(punct, progres=None, oprit=None, radacina=None, radacina_arhivei=None, amprenta=None, acum=None):
	"""Copia completa pe `punct`. `progres` (dict comun cu ecranul): pas, total, gata, inceput. `oprit()` = True opreste.
	`radacina` / `radacina_arhivei` / `amprenta`: numai pentru probele de pe PC (fara ele: receptorul, cu legarea
	radacinii). Intoarce {"cale", "nume", "marime", "secunde", "sarite"}; ridica EroareCopie sau Oprita."""
	progres = progres if progres is not None else {}
	inceput = time.time()

	def pas(n, total=0):
		progres.update({"pas": n, "total": total, "gata": 0, "inceput": time.time()})

	def verificaOprit():
		if oprit is not None and oprit():
			raise Oprita()

	ok, motiv = suport(radacina)
	if not ok:
		raise EroareCopie(textSuport(motiv))
	text_reguli = textReguli(radacina)
	reguli = P.citesteReguli(radacina)
	versiune = P.versiuneAcum(radacina) or reguli.get("version", "")
	nume = numeCopie(versiune, reguli.get("machinebuild", ""), acum)
	if not os.path.isdir(punct):
		raise EroareCopie(_("Stickul ales nu mai este în receptor."))
	cale_zip = os.path.join(punct, nume + SUFIX_ZIP)
	cale_lucru = cale_zip + SUFIX_LUCRU

	# pasul 1: nucleul
	pas(PAS_NUCLEU)
	cmdline = _citesteText(_cale(radacina, "proc/cmdline"), 4096) or ""
	kp = dispozitivNucleu(reguli, cmdline)
	if not kp:
		raise EroareCopie(_("Nucleul receptorului nu se poate citi, deci copia nu se poate face."))
	nucleu = citesteNucleu(_cale(radacina, "dev/" + kp))
	verificaOprit()

	legat = False
	try:
		if radacina_arhivei is None:
			radacina_arhivei = legaRadacina()
			legat = True
		exclus = set(os.path.join(radacina_arhivei, s.lstrip("/")) for s in _swapuri(radacina))
		octeti, _intrari = numaraRadacina(radacina_arhivei, exclus)
		necesar = len(nucleu) + int(octeti * RAPORT_LOC) + REZERVA_LOC
		liber = _octetiLiberi(punct)
		if liber < necesar:
			raise EroareCopie(_("Pe stick nu e destul loc: copia are nevoie de cam %s, iar liberi sunt %s.") % (
				_gb(necesar), _gb(liber)))
		verificaOprit()

		# pasul 2: sistemul, scris direct in zip, pe stick
		pas(PAS_SISTEM, octeti)

		ultim = [0]

		def verificaLoc(scrisi):
			if scrisi - ultim[0] >= 32 * BLOC:
				ultim[0] = scrisi
				if _octetiLiberi(punct) < REZERVA_MINIMA:
					raise EroareCopie(_("Stickul s-a umplut în timpul copiei. Fă loc pe el sau folosește alt stick."))

		try:
			with open(cale_lucru, "wb") as f:
				sarite = scrieZip(f, nucleu, radacina_arhivei, text_reguli, nume, octeti, progres, oprit, exclus,
					verificaLoc)
		except OSError as eroare:
			raise EroareCopie(_("Scrierea pe stick a căzut (%s). Verifică stickul și încearcă din nou.") % (
				eroare.strerror or eroare.__class__.__name__))
	except BaseException:
		_sterge(cale_lucru)
		raise
	finally:
		if legat:
			dezlegaRadacina(radacina_arhivei)

	# pasul 3: verificarea de pe stick, ca la instalare
	try:
		_scoateDinMemorie(cale_lucru)
		verifica(cale_lucru, radacina=radacina, amprenta=amprenta, progres=progres, oprit=oprit,
			la_inceput=lambda total: pas(PAS_VERIFICARE, total))
		os.rename(cale_lucru, cale_zip)
		try:
			fd = os.open(punct, os.O_RDONLY)
			try:
				os.fsync(fd)
			finally:
				os.close(fd)
		except OSError:
			pass
	except BaseException:
		_sterge(cale_lucru)
		raise
	return {"cale": cale_zip, "nume": os.path.basename(cale_zip), "marime": os.path.getsize(cale_zip),
		"secunde": time.time() - inceput, "sarite": sarite}


def verifica(cale_zip, radacina=None, amprenta=None, progres=None, oprit=None, la_inceput=None):
	"""Verificarea instalarii pe zip-ul de pe stick: structura e2/update, marcajul fata de receptor
	(HdsPazaModel.verificaPachet, ca instalarea), sumele SHA-256 recitite. EroareCopie la orice nepotrivire."""
	try:
		with zipfile.ZipFile(cale_zip) as z:
			nume = set(z.namelist())
			for n in (NUME_VERSIUNE, NUME_KERNEL, NUME_ROOTFS, NUME_MARCAJ):
				if SUBCALE + "/" + n not in nume:
					raise EroareCopie(_("Copia de pe stick nu e întreagă (lipsește %s).") % n)
			text_marcaj = z.read(SUBCALE + "/" + NUME_MARCAJ).decode("utf-8", "replace")
			if amprenta is None:
				cod, text, m = P.verificaPachet(text_marcaj, radacina=radacina)
			else:
				cod, text, m = P.verificaPachet(text_marcaj, a=amprenta)
			if cod != P.PACHET_BUN:
				raise EroareCopie(_("Instalarea nu ar primi copia: %s") % text)
			intrari = [z.getinfo(SUBCALE + "/" + NUME_KERNEL), z.getinfo(SUBCALE + "/" + NUME_ROOTFS)]
			total = sum(i.file_size for i in intrari)
			if la_inceput is not None:
				la_inceput(total)
			sume = {}
			for cheie, info in zip(("kernel_sha256", "rootfs_sha256"), intrari):
				h = hashlib.sha256()
				with z.open(info) as f:
					while True:
						if oprit is not None and oprit():
							raise Oprita()
						bucata = f.read(BLOC)
						if not bucata:
							break
						h.update(bucata)
						if progres is not None:
							progres["gata"] = progres.get("gata", 0) + len(bucata)
				sume[cheie] = h.hexdigest()
			gresite = P.sumeGresite(m, sume)
			if gresite:
				raise EroareCopie(_("Copia de pe stick nu are sumele de control scrise (%s). Încearcă din nou, pe alt "
					"stick.") % ", ".join(gresite))
	except (zipfile.BadZipFile, OSError, KeyError) as eroare:
		raise EroareCopie(_("Copia de pe stick nu se poate citi înapoi (%s). Încearcă din nou, pe alt stick.") % (
			getattr(eroare, "strerror", None) or eroare.__class__.__name__))
	return True


# ------------------------------------------------------------------------------------------- lucrul pe fir (TV + web)

_lacat = threading.Lock()
_stare = {"lucreaza": False, "oprit": False, "progres": {}, "mediu": "", "rezultat": None, "inceput": 0}


def ocupat():
	return _stare["lucreaza"]


def _textDurata(secunde):
	secunde = max(1, int(secunde + 0.999))
	if secunde < 60:
		return _("%d s") % secunde
	return _("%d min") % ((secunde + 59) // 60)


def _textProcent(progres, trecut):
	total = int((progres or {}).get("total") or 0)
	gata = min(int((progres or {}).get("gata") or 0), total)
	if total <= 0:
		return ""
	mb = 1024 * 1024
	text = _("%d %% (%d din %d MB).") % (gata * 100 // total, gata // mb, (total + mb - 1) // mb)
	if gata >= total:
		return text
	if trecut >= 5 and gata > 0:
		return text + " " + _("Mai durează cam %s.") % _textDurata((total - gata) * trecut / float(gata))
	return text + " " + _("Se măsoară viteza…")


def textPas(progres, acum=None):
	"""„Pasul 2 din 3: ... 45 % (210 din 467 MB). Mai durează cam 6 min.”"""
	pas = (progres or {}).get("pas") or PAS_NUCLEU
	trecut = (acum if acum is not None else time.time()) - ((progres or {}).get("inceput") or time.time())
	if pas == PAS_NUCLEU:
		return _("Pasul 1 din 3: se citește nucleul și se socotește mărimea sistemului.")
	if pas == PAS_SISTEM:
		text = _("Pasul 2 din 3: se copiază sistemul pe stick (canalele, setările și pluginurile sunt în el).")
	else:
		text = _("Pasul 3 din 3: copia se citește înapoi de pe stick și se verifică, ca la instalare.")
	procent = _textProcent(progres, trecut)
	return text + (" " + procent if procent else "")


def textGata(r):
	return _("Copia e gata: %s (%d MB), făcută în %s. Se pune înapoi din Meniu, Setări, Software & Firmware, Imagine nouă "
		"de pe stick.") % (r["nume"], (r["marime"] + 1024 * 1024 - 1) // (1024 * 1024), _textDurata(r["secunde"]))


def textDespre():
	return _("Copia completă are tot ce e pe receptor: imaginea, canalele, setările, pluginurile și modulele de acces. "
		"Se face pe un stick sau un disc USB, ca un fișier pe care instalarea de pe stick îl pune înapoi exact cum e acum. "
		"Receptorul rămâne pornit cât se face copia.")


def textParole():
	"""Randul despre parole, pe ecran si in pagina web (hotararea din 11.11.2026: scurt, fara alarma)."""
	return _("Copia are și parolele (Wi-Fi, interfața web, modulele de acces), deci păstrează stickul ca pe o cheie.")


def _ruleaza(punct):
	r = None
	try:
		try:
			os.nice(10)  # pe Linux numai acest fir: interfata ramane vie
		except OSError:
			pass
		rez = faCopia(punct, _stare["progres"], lambda: _stare["oprit"])
		r = {"ok": True, "mesaj": textGata(rez), "nume": rez["nume"], "marime": rez["marime"]}
	except Oprita:
		r = {"ok": False, "mesaj": _("Copia a fost oprită. Fișierul început s-a șters; pe receptor nu s-a schimbat nimic.")}
	except EroareCopie as eroare:
		r = {"ok": False, "mesaj": _("Copia nu s-a făcut: %s") % eroare}
	except Exception as eroare:
		print("[HdsCopieImagine] copia a cazut: %r" % (eroare,))
		r = {"ok": False, "mesaj": _("Copia nu s-a făcut: eroare pe receptor (%s).") % eroare.__class__.__name__}
	finally:
		with _lacat:
			_stare["rezultat"] = r
			_stare["lucreaza"] = False


# ceasul de pe firul enigma2 care arata mesajul de la sfarsit (copia merge si cu ecranul inchis); firul copiei nu
# atinge interfata
_ceas = []


def _pornesteCeasul():
	try:
		from enigma import eTimer
	except Exception:  # in afara lui enigma2 (probele, python3 de pe receptor) nu e ceas si nici mesaj
		return
	if not _ceas:
		t = eTimer()
		try:
			legatura = t.timeout.connect(_verificaSfarsit)
		except AttributeError:
			t.callback.append(_verificaSfarsit)
			legatura = None
		_ceas[:] = [t, legatura]
	_ceas[0].start(1000, False)


# ecranele deschise (Screens/HdsCopieImagine.py): cat unul e deschis, rezultatul se vede in el, fara mesajul de deasupra
ecrane = []


def _verificaSfarsit():
	if _stare["lucreaza"]:
		return
	_ceas[0].stop()
	if _stare["rezultat"] is not None and not ecrane:
		mesajTelevizor(_stare["rezultat"])


def porneste(punct):
	"""(True, text) cand copia a pornit pe firul ei; (False, motiv) altfel."""
	ok, motiv = suport()
	if not ok:
		return False, textSuport(motiv)
	if not any(m["id"] == punct for m in medii()):
		return False, _("Alege un stick sau un disc USB din listă.")
	with _lacat:
		if _stare["lucreaza"]:
			return False, _("Copia se face deja.")
		_stare.update({"lucreaza": True, "oprit": False, "progres": {"pas": PAS_NUCLEU, "inceput": time.time()},
			"mediu": punct, "rezultat": None, "inceput": time.time()})
	fir = threading.Thread(target=_ruleaza, args=(punct,), name="HdsCopieImagine")
	fir.daemon = True
	fir.start()
	_pornesteCeasul()
	return True, _("Copia a pornit. Nu scoate stickul până nu scrie „Copia e gata”.")


def opreste():
	if _stare["lucreaza"]:
		_stare["oprit"] = True
		return True
	return False


def stare():
	"""Starea comuna pentru ecran si web: lucreaza, textul pasului, rezultatul ultimei copii."""
	with _lacat:
		lucreaza = _stare["lucreaza"]
		progres = dict(_stare["progres"])
		rezultat = _stare["rezultat"]
		mediu = _stare["mediu"]
		oprit = _stare["oprit"]
	return {"lucreaza": lucreaza, "oprit": oprit, "pas": progres.get("pas") or 0, "pasi": PASI,
		"text": textPas(progres) if lucreaza else "", "mediu": mediu, "rezultat": rezultat}


def mesajTelevizor(r):
	"""La sfarsit, un mesaj scurt pe televizor (copia merge si cu ecranul inchis); pe firul enigma2."""
	try:
		from Screens.MessageBox import MessageBox
		from Tools import Notifications
		Notifications.AddPopup(r["mesaj"], MessageBox.TYPE_INFO if r["ok"] else MessageBox.TYPE_ERROR, 20,
			"HdsCopieImagine")
	except Exception as eroare:
		print("[HdsCopieImagine] mesajul de la sfarsit: %r" % (eroare,))
