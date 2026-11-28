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
#      apoi zip-ul se citeste din nou: structura (kernel.bin si rootfs.tar.bz2 in e2/update), cheile marcajului, sumele
#      SHA-256 recitite si, la urma, marcajul fata de receptor (aceeasi functie a instalarii, cu amprenta receptorului).
#      Abia apoi numele de lucru <nume>.zip.partial (pe care instalarea nu il vede) devine <nume>.zip. Oprirea si
#      erorile din pasii 1-2 sterg fisierul de lucru. Ce gaseste verificarea NU il sterge: fisierul ramane pe stick, iar
#      mesajul spune ce nu e bine si cum se numeste fisierul. Intreg (sumele bune, numai receptorul nu se potriveste) ramane
#      sub numele lui; stricat (structura, marcajul sau sumele) ramane sub numele de lucru, pe care instalarea nu il vede.
#      Pornita dintr-un loc de multiboot cu nucleul in alta partitie decat cea de baza (Vu+ Duo 4K Lite, locurile 2-8:
#      kernel=/dev/mmcblk0p5..p11), imaginea are alt loc al nucleului decat marcajul (regulile ei, locul de baza);
#      potrivirea cu receptorul e atunci cea a garzii de la pornire (HdsPazaModel.comparaPornire: numai partitiile
#      locului pot diferi). Pana in 0.7.6 verificarea cerea potrivirea stricta a pachetelor de instalat, cadea pe locul
#      nucleului si stergea copia abia facuta. Instalarea pachetelor ramane stricta.
# Copia numai CITESTE de pe receptor; nu scrie nimic pe memoria interna. Nu porneste ofgwrite.
#
# Modelele: eMMC HiSilicon (forma de mai sus) si, din 0.7.5, Vu+ 4K (familie=broadcom; JAKITAKI, Satedu, 14.11.2026).
# Pe Vu+ forma e a stickului Vu+, ca la OE-Alliance (Screens/ImageBackup.py) si ca zip-urile noastre de pe site:
# <nume>_usb.zip cu vuplus/<model>/imageversion, kernel_auto.bin (zImage, taiat la marimea din antet), rootfs.tar.bz2,
# reboot.update si marcajul. Fara initrd_auto.bin, splash_auto.bin si FARA mkpart.update (ar reface partitiile): copia
# pune inapoi numai nucleul si sistemul. Se pune inapoi ca imaginea Vu+ de pe site: zip-ul dezarhivat pe stick, apoi
# receptorul pornit cu stickul (incarcatorul Vu+; instalarea din meniu cauta kernel.bin si nu o vede).
# Celelalte Broadcom pe eMMC (familie=broadcom, nu Vu+) au forma arhivei lor de pe site: acelasi zip ca pe HiSilicon
# (imageversion, kernel.bin, rootfs.tar.bz2, marcajul), dar in dosarul modelului din reteta imaginii (IMAGEDIR din
# hdsatelit-image.bb, ca la arhivele OE-Alliance pentru aceste aparate): AX HD51 hd51/, GigaBlue UHD Quad 4K Pro
# gigablue/quad4kpro/, Dreambox DM900 si DM920 dm900/ si dm920/ (DOSARE_MODEL). Instalarea din meniu (Imagine noua de
# pe stick) cauta kernel.bin si rootfs.tar.bz2 in orice dosar al zip-ului, deci o vede si o pune inapoi ca pe arhiva de
# pe site. Fara fisierele de pornire ale producatorului (boot, gpt, bolt, rescue, splash pe GigaBlue): copia pune inapoi
# numai nucleul si sistemul. Pana in 0.7.6 orice Broadcom primea forma Vu+ (vuplus/<masina>, kernel_auto.bin), pe care
# nici instalarea din meniu, nici incarcatorul acestor receptoare nu o citesc. Un Broadcom fara forma cunoscuta in
# DOSARE_MODEL nu are copie (NU_FORMA), cu textul modelelor fara copie: o arhiva fara dosarul bun nu s-ar putea pune inapoi.
# NU inca: stocare=nand (Vu+ Solo SE, Solo2, Duo2, Zero: copia ar cere mkfs.ubifs/ubinize/nanddump, care nu sunt in
# imagine) si NeoBoot (/.multinfo: nucleul e un fisier al lui, pe care nu il stim gasi).
# Vu+ 4K cu pornirea multipla kexec (OE-Alliance kexec-multiboot; din 0.8.0, marci70, LinuxSat 164248 #973647, Ultimo 4K
# locul 2): orice loc porneste prin nucleul kexec din partitia nucleului (mmcblk0p1 pe Solo/Uno/Ultimo 4K), deci
# /proc/cmdline are mereu kexec=1, iar nucleul imaginii pornite e FISIERUL kernel= din STARTUP_N, socotit de la radacina
# partitiei din root=: /linuxrootfsN/zImage (memoria), <model>/linuxrootfsN/zImage (USB), /zImage (Recovery, locul 0,
# rootsubdir=linuxrootfs0 = radacina flash). Cu rootsubdir=linuxrootfsN, sistemul pornit e chiar dosarul locului, deci
# nucleul e /zImage in sistemul care ruleaza (aceeasi cale o copiaza unealta de copii OE-Alliance: cp /zImage). Copia ia
# fisierul intreg (nucleuLocKexec, citesteNucleuFisier), nu partitia nucleului, care e a nucleului kexec. Din Recovery
# dosarele celorlalte locuri (linuxrootfsN din radacina flash) nu intra in arhiva. Forma ramane a stickului Vu+;
# textGata si textPunere spun ca, pusa cu stickul, copia inlocuieste pornirea multipla (scrie si partitia nucleului,
# unde sta nucleul kexec).
# Refuzul (NU_KEXEC) ramane numai cand fisierul nucleului nu se gaseste sau nu are antet zImage/uImage.
# NU: imaginea pornita dintr-un dosar de pe disc sau stick de un program de pornire multipla al imaginii din memorie (MOH
# Boot: / pe disc, imaginea din memorie pe /oldroot, moh_image= in /proc/cmdline). Nucleul care ruleaza e al imaginii din
# memorie, iar arhiva imaginii nu are nucleul ei (fara /boot), deci o copie completa ar avea nucleul altei imagini.
# Refuzul vine inainte de copie, cu textul lui (NU_DOSAR). /oldroot intra oricum gol (GOALE), ca /run.
# Nucleul: kernel= din /proc/cmdline cand exista (slotul pornit, si de pe stick: /dev/sdaK pe SF8008), altfel
# kernel_part din reguli. Cand kernel= numeste altceva decat o partitie, copia nu se face: pana pe 14.11.2026 cadea pe
# kernel_part, adica pe nucleul ALTEI imagini cand pornirea era dintr-un loc de pe stick (typhoones12, SF8008). Fara
# kernel=, kernel_part se ia numai cand pornirea e chiar din locul de baza al regulilor (root= lipsa sau rootfs_part, fara
# alt subdosar decat linuxrootfs1); dintr-un alt loc fara kernel= in linia de comanda (Components/HdsPornireMultipla
# primeste si locuri emmcflash0.kernelN fara kernel=) kernel_part ar fi nucleul locului de baza, al altei imagini, deci
# copia nu se face. Fara
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
# zImage ARM (nucleul Vu+ 4K): semnul 0x016F2818 la 0x24, inceputul si sfarsitul (little-endian) la 0x28 si 0x2C
MAGIC_ZIMAGE = b"\x18\x28\x6f\x01"
ANTET_NUCLEU = 64
NUCLEU_MAXIM = 64 * 1024 * 1024
BLOC = 1024 * 1024
NIVEL_BZ2 = 9
# fisierele fara de care imaginea nu porneste (REGULI-FLASH-RECEPTOR, regula 7)
OBLIGATORII = ("./sbin/init", "./sbin/ldconfig", "./usr/bin/enigma2")
# dosarele care intra goale, ca in imaginea de pe site: pe imaginea noastra /run sta pe radacina (nu in RAM), iar pe receptorul de proba
# (11.11.2026) avea 408 intrari de rulare (pid-uri, baza udev, avahi); puse inapoi, ar strica pornirea serviciilor
# /oldroot: sub un program de pornire multipla e imaginea din memorie (cu setarile ei); nu intra niciodata in copie
GOALE = ("./run", "./oldroot")
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
# root= din /proc/cmdline care numeste o partitie a memoriei interne (pornirea din dosar: _pornireDinDosar)
_MEMORIE_RX = re.compile(r"^/dev/mmcblk[0-9]+p[0-9]+$")
_NUME_RX = re.compile(r"[^A-Za-z0-9_.+-]")
_KERNEL_RX = re.compile(r"^mmcblk[0-9]+p[0-9]+$")
# kernel= din /proc/cmdline: o partitie din memorie sau de pe un stick (locurile USB ale SF8008: /dev/sdaK)
_KERNEL_CMDLINE_RX = re.compile(r"^/dev/(mmcblk[0-9]+p[0-9]+|sd[a-z]+[0-9]+)$")

# FORMELE copiei (aceeasi tabela la scriere si la verificare): dosarul din zip, numele nucleului, sufixul, fisierele in plus
FORMA_EMMC = {"fel": "emmc", "subcale": "e2/update", "kernel": "kernel.bin", "sufix": "_mmc.zip", "in_plus": ()}
# reboot.update: ca toate zip-urile Vu+ 4K de pe site (masina din stratul OE-Alliance); fara el incarcatorul cere confirmare
FORMA_VUPLUS = {"fel": "vuplus", "subcale": "vuplus/%s", "kernel": "kernel_auto.bin", "sufix": "_usb.zip",
	"in_plus": (("reboot.update", "This file forces a reboot after the update.\n"),)}
# Broadcom pe eMMC care nu e Vu+ (machinebuild -> dosarul din zip): IMAGEDIR din reteta imaginii, acelasi dosar ca in
# arhiva de pe site (hdsatelit-0.7.6-ax51-*.zip: hd51/, hdsatelit-0.7.4-gbquad4kpro-*.zip: gigablue/quad4kpro/); forma
# FORMA_EMMC, numai cu alt dosar. Un model nou se adauga aici dupa arhiva lui de pe site (proba test_cpf_* o cere).
DOSARE_MODEL = {"ax51": "hd51", "gbquad4kpro": "gigablue/quad4kpro", "dm900": "dm900", "dm920": "dm920"}

PAS_NUCLEU, PAS_SISTEM, PAS_VERIFICARE = 1, 2, 3
PASI = 3

# de ce nu se poate face copia pe acest receptor (suport())
NU_REGULI = "fara-reguli"
NU_VUPLUS = "vuplus"  # pana in 0.7.4; din 0.7.5 Vu+ 4K are copia (FORMA_VUPLUS), ramane numai pentru textul vechi
NU_NAND = "nand"
NU_LOC = "loc-fara-partitie"
NU_DOSAR = "pornire-din-dosar"
NU_FORMA = "fara-forma"  # Broadcom fara forma arhivei cunoscuta (DOSARE_MODEL)
NU_KEXEC = "kexec-fara-nucleu"  # Vu+ 4K kexec: fisierul nucleului locului nu s-a gasit (nucleuLocKexec)

# dosarele locurilor kexec din radacina flash (Recovery): ale altor imagini, nu intra in copia Recovery-ului
_LOC_KEXEC_RX = re.compile(r"^linuxrootfs[0-9]+$")

# ce a gasit verificarea din pasul 3 (EroareCopie.fisier): fisierul stricat ramane sub numele de lucru, cel intreg sub numele lui
FISIER_STRICAT = "stricat"
FISIER_INTREG = "intreg"


class Oprita(Exception):
	"""Omul a oprit copia."""


class EroareCopie(Exception):
	"""O eroare cu text pentru om (fara inceputul 'Copia nu s-a facut:' in fata). `fisier` numai pentru ce gaseste
	verificarea din pasul 3: FISIER_STRICAT sau FISIER_INTREG (fisierul ramane pe stick); None altfel."""

	def __init__(self, text="", fisier=None):
		Exception.__init__(self, text)
		self.fisier = fisier


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


def forma(reguli):
	"""Forma copiei pentru regulile date: FORMA_EMMC pe HiSilicon; pe Broadcom FORMA_EMMC cu dosarul arhivei de pe site
	(DOSARE_MODEL) sau FORMA_VUPLUS cu dosarul modelului (Vu+ 4K); None pe un Broadcom fara forma cunoscuta."""
	if not P.broadcom(reguli):
		return FORMA_EMMC
	masina = (reguli or {}).get("machinebuild", "")
	if masina in DOSARE_MODEL:
		f = dict(FORMA_EMMC)
		f["subcale"] = DOSARE_MODEL[masina]
		return f
	if masina.startswith("vu"):
		f = dict(FORMA_VUPLUS)
		f["subcale"] = f["subcale"] % masina[2:]
		return f
	return None


def nucleuDinCmdline(cmdline):
	"""(are_kernel, partitia): are_kernel = /proc/cmdline are kernel=; partitia = "mmcblk0p13" / "sda1" cand kernel=
	numeste o partitie, "" altfel (un fisier, UUID, kexec)."""
	for cuvant in (cmdline or "").split():
		if cuvant.startswith("kernel="):
			m = _KERNEL_CMDLINE_RX.match(cuvant[7:])
			return True, (m.group(1) if m else "")
	return False, ""


def _pornireFaraPartitie(radacina, cmdline):
	"""True cand nucleul pornit nu sta intr-o partitie: kexec (Vu+ 4K cu pornire multipla), NeoBoot (/.multinfo, ca paza
	din ofgwrite) sau kernel= care nu e o partitie."""
	cuvinte = (cmdline or "").split()
	if "kexec=1" in cuvinte or os.path.exists(_cale(radacina, ".multinfo")):
		return True
	are, kp = nucleuDinCmdline(cmdline)
	return are and not kp


def _kexec(cmdline):
	"""True cand pornirea e prin nucleul kexec al pornirii multiple Vu+ 4K (kexec=1 in /proc/cmdline, in orice loc)."""
	return "kexec=1" in (cmdline or "").split()


def _parametru(cmdline, cheie):
	"""Valoarea primului cheie= din /proc/cmdline; "" cand lipseste."""
	for cuvant in (cmdline or "").split():
		if cuvant.startswith(cheie + "="):
			return cuvant[len(cheie) + 1:]
	return ""


def _subdosarKexec(cmdline):
	"""rootsubdir= al locului kexec, fara / la capete; "" la Recovery (linuxrootfs0 sau lipsa: radacina flash)."""
	sub = _parametru(cmdline, "rootsubdir").strip("/")
	return "" if sub in ("", "linuxrootfs0") else sub


def _nucleuFisierBun(cale):
	"""Fisierul are antet zImage sau uImage, iar marimea din antet incape in fisier (fisierul e cel mult NUCLEU_MAXIM)."""
	try:
		marime_fisier = os.path.getsize(cale)
		with open(cale, "rb") as f:
			marime = marimeUimage(f.read(ANTET_NUCLEU))
	except OSError:
		return False
	return marime is not None and ANTET_NUCLEU < marime <= marime_fisier <= NUCLEU_MAXIM


def nucleuLocKexec(radacina, cmdline):
	"""Calea fisierului nucleului locului kexec pornit, in sistemul care ruleaza: kernel= fara subdosarul locului
	(rootsubdir=linuxrootfs2, kernel=/linuxrootfs2/zImage -> /zImage; Recovery: kernel=/zImage -> /zImage); fara kernel=
	in linia de comanda (unele initramfs nu il pastreaza), /zImage, ca in forma kexec-multiboot. "" fara kexec=1, cand
	kernel= sta in afara dosarului locului, cand fisierul lipseste sau nu are antetul unui nucleu."""
	if not _kexec(cmdline):
		return ""
	sub = _subdosarKexec(cmdline)
	kernel = _parametru(cmdline, "kernel").lstrip("/")
	if not kernel:
		rel = "zImage"
	elif not sub:
		rel = kernel
	elif kernel.startswith(sub + "/"):
		rel = kernel[len(sub) + 1:]
	else:
		return ""
	if any(p in ("", ".", "..") for p in rel.split("/")):
		return ""
	cale = _cale(radacina, rel)
	return cale if os.path.isfile(cale) and _nucleuFisierBun(cale) else ""


def locuriKexecVecine(radacina_arhivei, cmdline):
	"""Pornita din Recovery-ul kexec (radacina flash), radacina are dosarele celorlalte locuri (linuxrootfsN): caile lor,
	ca sa nu intre in copie. [] in orice alt loc (sistemul pornit e chiar dosarul locului) si fara kexec."""
	if not _kexec(cmdline) or _subdosarKexec(cmdline):
		return []
	try:
		nume = os.listdir(radacina_arhivei)
	except OSError:
		return []
	return [os.path.join(radacina_arhivei, n) for n in sorted(nume)
		if _LOC_KEXEC_RX.match(n) and os.path.isdir(os.path.join(radacina_arhivei, n))]


def _dispozitivRadacina(radacina=None):
	"""Dispozitivul montat pe / (ultimul rand pentru / din /proc/mounts, nu rootfs-ul de la pornire); "" cand lipseste."""
	dispozitiv = ""
	for d, punct, tip in montari(radacina):
		if punct == "/" and tip != "rootfs":
			dispozitiv = d
	return dispozitiv


def _pornireDinDosar(radacina, cmdline):
	"""True cand imaginea ruleaza dintr-un dosar de pe disc sau stick, pornita de un program de pornire multipla al
	imaginii din memorie, cu nucleul acelei imagini (MOH Boot). Semnele, oricare: moh_image= in /proc/cmdline (MOH Boot
	pune peste /proc/cmdline un fisier al lui, cu el), o montare pe /oldroot (imaginea din memorie, mutata acolo) sau / pe un
	disc USB cand root= numeste o partitie a memoriei interne. Locurile de pe stick cu nucleul lor (root= si kernel= pe
	/dev/sd*), locurile din memorie si root=UUID nu sunt atinse."""
	cuvinte = (cmdline or "").split()
	if any(c.startswith("moh_image=") for c in cuvinte):
		return True
	if any(punct == "/oldroot" for _d, punct, _t in montari(radacina)):
		return True
	root = next((c[5:] for c in cuvinte if c.startswith("root=")), "")
	return bool(_MEMORIE_RX.match(root) and _USB_RX.match(_dispozitivRadacina(radacina)))


def suport(radacina=None):
	"""(True, "") cand copia se poate face pe acest receptor; altfel (False, NU_*)."""
	reguli = P.citesteReguli(radacina)
	if not reguli:
		return False, NU_REGULI
	if P.nand(reguli):
		return False, NU_NAND
	if forma(reguli) is None:
		return False, NU_FORMA
	cmdline = _citesteText(_cale(radacina, "proc/cmdline"), 4096) or ""
	if os.path.exists(_cale(radacina, ".multinfo")):
		return False, NU_LOC
	if _kexec(cmdline):
		# Vu+ 4K: nucleul locului e un fisier al lui; fara el (sau pe alt receptor decat Vu+) nu se face
		if forma(reguli)["fel"] != FORMA_VUPLUS["fel"]:
			return False, NU_LOC
		if not nucleuLocKexec(radacina, cmdline):
			return False, NU_KEXEC
	elif _pornireFaraPartitie(radacina, cmdline):
		return False, NU_LOC
	if _pornireDinDosar(radacina, cmdline):
		return False, NU_DOSAR
	return True, ""


def textSuport(motiv):
	if motiv == NU_VUPLUS:
		return _("Pe receptoarele Vu+ copia completă a imaginii nu se poate face încă. Fă copia setărilor (Meniu, Setări, "
			"Software & Firmware, Copia setărilor): ea păstrează canalele, setările și pluginurile, iar imaginea o iei de pe site.")
	if motiv == NU_LOC:
		return _("Imaginea rulează dintr-un loc de pornire multiplă al cărui nucleu nu stă într-o partiție, deci copia ei "
			"nu s-ar putea pune înapoi. Pornește imaginea HD Satelit din memoria receptorului și fă copia de acolo.")
	if motiv == NU_KEXEC:
		return _("Imaginea rulează dintr-un loc de pornire multiplă Vu+, dar fișierul nucleului acestui loc (zImage din "
			"dosarul locului) nu s-a găsit, deci copia nu s-ar putea pune înapoi. Fă copia setărilor (Meniu, Setări, "
			"Software & Firmware, Copia setărilor): ea păstrează canalele, setările și pluginurile.")
	if motiv == NU_DOSAR:
		return _("Imaginea rulează dintr-un dosar de pe disc sau de pe stick (pornire multiplă, de pildă MOH Boot), cu "
			"nucleul imaginii din memoria receptorului, deci o copie completă nu s-ar putea pune înapoi corect. Fă copia "
			"setărilor (Meniu, Setări, Software & Firmware, Copia setărilor): ea păstrează canalele, setările și pluginurile.")
	if motiv in (NU_NAND, NU_FORMA):
		return _("Pe acest receptor copia completă a imaginii nu se poate face încă. Fă copia setărilor (Meniu, Setări, "
			"Software & Firmware, Copia setărilor): ea păstrează canalele, setările și pluginurile, iar imaginea o iei de pe site.")
	return _("Imaginea care rulează nu spune pentru ce receptor este, deci copia ei nu s-ar putea pune înapoi. Copia "
		"completă se face numai pe imaginea HD Satelit pornită din memoria receptorului.")


def dispozitivNucleu(reguli, cmdline):
	"""mmcblk0p9 / sda1: partitia nucleului pornit (kernel= din /proc/cmdline: slotul ales, si locurile de pe stick),
	altfel, numai cand cmdline nu are kernel=, kernel_part= din reguli. "" cand kernel= nu numeste o partitie, cand
	regulile nu au o partitie eMMC si cand, fara kernel=, pornirea nu e din locul de baza al regulilor: root= altul decat
	/dev/<rootfs_part> sau rootsubdir= altul decat linuxrootfs1 (atunci kernel_part ar fi nucleul altui loc)."""
	are, kp = nucleuDinCmdline(cmdline)
	if are:
		return kp
	r = reguli or {}
	candidat = r.get("kernel_part", "")
	if not _KERNEL_RX.match(candidat):
		return ""
	cuvinte = (cmdline or "").split()
	root = next((c[5:] for c in cuvinte if c.startswith("root=")), "")
	subdosar = next((c[11:] for c in cuvinte if c.startswith("rootsubdir=")), "")
	if (root and r.get("rootfs_part") and root != "/dev/" + r["rootfs_part"]) or (subdosar and subdosar != P.SUBDOSAR_BAZA):
		return ""
	return candidat


def marimeUimage(antet):
	"""Octetii nucleului dupa antetul uImage (64 + marimea datelor) sau zImage ARM (sfarsit - inceput, din antet);
	None fara unul din ele."""
	if len(antet) >= ANTET_UIMAGE and antet[:4] == MAGIC_UIMAGE:
		return ANTET_UIMAGE + struct.unpack(">I", antet[12:16])[0]
	if len(antet) >= 0x30 and antet[0x24:0x28] == MAGIC_ZIMAGE:
		inceput, sfarsit = struct.unpack("<II", antet[0x28:0x30])
		return sfarsit - inceput if sfarsit > inceput else None
	return None


def citesteNucleu(cale_dispozitiv):
	"""Nucleul din partitie, taiat la marimea din antetul uImage. EroareCopie cand nu se poate citi sau nu are antet."""
	try:
		with open(cale_dispozitiv, "rb") as f:
			antet = f.read(ANTET_NUCLEU)
			marime = marimeUimage(antet)
			if marime is None:
				raise EroareCopie(_("Nucleul receptorului nu are forma cunoscută, deci copia nu se poate face."))
			f.seek(0, os.SEEK_END)
			partitie = f.tell()
			if marime <= ANTET_NUCLEU or marime > min(partitie, NUCLEU_MAXIM):
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


def citesteNucleuFisier(cale):
	"""Nucleul locului kexec (fisierul zImage al locului), INTREG, ca la unealta de copii OE-Alliance (cp /zImage): un
	fisier nu are rest de partitie de taiat. EroareCopie cand lipseste, nu se poate citi sau nu are antetul unui nucleu."""
	if not cale or not _nucleuFisierBun(cale):
		raise EroareCopie(_("Nucleul receptorului nu are forma cunoscută, deci copia nu se poate face."))
	try:
		with open(cale, "rb") as f:
			date = f.read(NUCLEU_MAXIM + 1)
	except OSError:
		raise EroareCopie(_("Nucleul receptorului nu se poate citi, deci copia nu se poate face."))
	if not ANTET_NUCLEU < len(date) <= NUCLEU_MAXIM or marimeUimage(date[:ANTET_NUCLEU]) is None:
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
		_tai(radacina_arhivei, dosar, dosare, exclus)
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


def _tai(radacina_arhivei, dosar, dosare, exclus=()):
	"""os.walk nu mai intra in dosarele GOALE (ele intra in arhiva numai ca dosar) si nici in cele din `exclus` (ele nu
	intra deloc: dosarele celorlalte locuri kexec, locuriKexecVecine)."""
	rel = os.path.relpath(dosar, radacina_arhivei)
	baza = "." if rel == "." else "./" + rel.replace(os.sep, "/")
	dosare[:] = [d for d in dosare if baza + "/" + d not in GOALE and os.path.join(dosar, d) not in exclus]


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
		_tai(radacina_arhivei, dosar, dosare, exclus)
	return vazute, sarite


def _legatSub(punct, radacina=None):
	"""True cand ceva e montat pe `punct`. /proc/mounts arata calea adevarata: pe receptor /tmp e o legatura spre
	/var/volatile/tmp (gasit pe receptorul de proba, 11.11.2026), deci se compara si calea cu legaturile rezolvate."""
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


def _intrare(nume, subcale=SUBCALE):
	"""Intrarea din zip: <subcale>/<nume> (e2/update sau vuplus/<model>), ora de acum, drepturile 0644, fara comprimare
	(bz2 e deja comprimat)."""
	info = zipfile.ZipInfo(subcale + "/" + nume, time.localtime(time.time())[:6])
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
		verificaLoc=None, fel=None):
	"""Zip-ul copiei in obiectul-fisier `f` (fisierul de pe stick; in proba de pe receptorul de proba, fara stick, iesirea ssh spre PC):
	imageversion, kernel.bin, rootfs.tar.bz2 (tar GNU -> bz2, cu SHA-256 din mers) si marcajul. Intoarce numarul
	fisierelor sarite; EroareCopie cand lipsesc fisierele de pornire."""
	fel = fel or FORMA_EMMC
	sc = fel["subcale"]
	sume = {"kernel_sha256": hashlib.sha256(nucleu).hexdigest()}
	with zipfile.ZipFile(f, "w", allowZip64=True) as z:
		z.writestr(_intrare(NUME_VERSIUNE, sc), versiune_imagine + "\n")
		z.writestr(_intrare(fel["kernel"], sc), nucleu)
		for nume_plus, text_plus in fel["in_plus"]:
			z.writestr(_intrare(nume_plus, sc), text_plus)
		with z.open(_intrare(NUME_ROOTFS, sc), "w", force_zip64=octeti > LIMITA_FARA_ZIP64) as dest:
			scriitor = _ScriitorBz2(dest, verificaLoc)
			with tarfile.open(fileobj=scriitor, mode="w|", format=tarfile.GNU_FORMAT) as tar:
				tar.copybufsize = BLOC  # bucati de 1 MiB: mai putine treceri prin Python, interfata ramane vie
				vazute, sarite = scrieArhiva(tar, radacina_arhivei, progres, oprit, exclus)
			scriitor.termina()
		lipsa = [n[2:] for n in OBLIGATORII if n not in vazute]
		if lipsa:
			raise EroareCopie(_("În sistem lipsesc fișiere de pornire (%s), deci copia nu ar porni.") % ", ".join(lipsa))
		sume["rootfs_sha256"] = scriitor.sha.hexdigest()
		z.writestr(_intrare(NUME_MARCAJ, sc), marcaj(text_reguli, versiune_imagine, sume))
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
	fel = forma(reguli)
	if not os.path.isdir(punct):
		raise EroareCopie(_("Stickul ales nu mai este în receptor."))
	cale_zip = os.path.join(punct, nume + fel["sufix"])
	cale_lucru = cale_zip + SUFIX_LUCRU

	# pasul 1: nucleul
	pas(PAS_NUCLEU)
	cmdline = _citesteText(_cale(radacina, "proc/cmdline"), 4096) or ""
	kexec = _kexec(cmdline)
	if kexec:
		# Vu+ 4K kexec: fisierul nucleului locului (partitia nucleului e a nucleului kexec)
		nucleu = citesteNucleuFisier(nucleuLocKexec(radacina, cmdline))
	else:
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
		exclus.update(locuriKexecVecine(radacina_arhivei, cmdline))
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
					verificaLoc, fel)
		except OSError as eroare:
			raise EroareCopie(_("Scrierea pe stick a căzut (%s). Verifică stickul și încearcă din nou.") % (
				eroare.strerror or eroare.__class__.__name__))
	except BaseException:
		_sterge(cale_lucru)
		raise
	finally:
		if legat:
			dezlegaRadacina(radacina_arhivei)

	# pasul 3: verificarea de pe stick, ca la instalare; ce gaseste ea nu sterge fisierul (_pastreaza)
	try:
		_scoateDinMemorie(cale_lucru)
		verifica(cale_lucru, radacina=radacina, amprenta=amprenta, progres=progres, oprit=oprit,
			la_inceput=lambda total: pas(PAS_VERIFICARE, total), fel=fel)
		os.rename(cale_lucru, cale_zip)
		_fsyncDosar(punct)
	except EroareCopie as eroare:
		if eroare.fisier is None:
			_sterge(cale_lucru)
			raise
		print("[HdsCopieImagine] verificarea copiei: %s" % (str(eroare).splitlines() or [""])[0])
		raise EroareCopie(_pastreaza(eroare, cale_lucru, cale_zip, punct), eroare.fisier)
	except BaseException:
		_sterge(cale_lucru)
		raise
	return {"cale": cale_zip, "nume": os.path.basename(cale_zip), "marime": os.path.getsize(cale_zip),
		"secunde": time.time() - inceput, "sarite": sarite, "fel": fel["fel"], "kexec": kexec}


def _fsyncDosar(punct):
	try:
		fd = os.open(punct, os.O_RDONLY)
		try:
			os.fsync(fd)
		finally:
			os.close(fd)
	except OSError:
		pass


def _pastreaza(eroare, cale_lucru, cale_zip, punct):
	"""Fisierul in care verificarea a gasit ceva ramane pe stick. Intreg (FISIER_INTREG: sumele bune, numai potrivirea cu
	receptorul) primeste numele lui, ca omul sa-l poata folosi; stricat ramane sub numele de lucru (.partial), pe care
	instalarea nu il vede, deci nu se pune inapoi din greseala. Intoarce textul erorii cu numele fisierului ramas."""
	cale = cale_lucru
	if eroare.fisier == FISIER_INTREG:
		try:
			os.rename(cale_lucru, cale_zip)
			cale = cale_zip
			_fsyncDosar(punct)
		except OSError:
			pass
	text = str(eroare)
	if os.path.exists(cale):
		text += "\n" + _("Fișierul a rămas pe stick: %s.") % os.path.basename(cale)
	return text


def verifica(cale_zip, radacina=None, amprenta=None, progres=None, oprit=None, la_inceput=None, fel=None):
	"""Verificarea instalarii pe zip-ul de pe stick: structura (dosarul si numele formei: e2/update sau vuplus/<model>),
	cheile marcajului, sumele SHA-256 recitite, apoi marcajul fata de receptor (HdsPazaModel.verificaPachet, ca instalarea).
	Sumele vin inaintea receptorului, ca mesajul sa spuna daca fisierul e intreg. Pornita dintr-un loc de multiboot
	(amprenta["multiboot"]), imaginea poate avea alt loc al nucleului decat marcajul: atunci potrivirea e a garzii de la
	pornire (HdsPazaModel.comparaPornire), in care numai partitiile locului pot diferi. EroareCopie la orice nepotrivire,
	cu .fisier = FISIER_STRICAT (structura, marcajul, sumele) sau FISIER_INTREG (numai receptorul)."""
	fel = fel or FORMA_EMMC
	sc = fel["subcale"]
	try:
		with zipfile.ZipFile(cale_zip) as z:
			nume = set(z.namelist())
			for n in (NUME_VERSIUNE, fel["kernel"], NUME_ROOTFS, NUME_MARCAJ) + tuple(p[0] for p in fel["in_plus"]):
				if sc + "/" + n not in nume:
					raise EroareCopie(_("Copia de pe stick nu e întreagă (lipsește %s).") % n, FISIER_STRICAT)
			text_marcaj = z.read(sc + "/" + NUME_MARCAJ).decode("utf-8", "replace")
			m = P.cheiValori(text_marcaj)
			if not P.reguliValide(m, cu_sume=True):
				raise EroareCopie(_("Instalarea nu ar primi copia: %s") % P.textRefuz(P.REFUZ_MARCAJ_STRICAT),
					FISIER_STRICAT)
			intrari = [z.getinfo(sc + "/" + fel["kernel"]), z.getinfo(sc + "/" + NUME_ROOTFS)]
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
					"stick.") % ", ".join(gresite), FISIER_STRICAT)
	except (zipfile.BadZipFile, OSError, KeyError) as eroare:
		raise EroareCopie(_("Copia de pe stick nu se poate citi înapoi (%s). Încearcă din nou, pe alt stick.") % (
			getattr(eroare, "strerror", None) or eroare.__class__.__name__), FISIER_STRICAT)
	# fisierul e intreg; acum marcajul fata de receptor, ca instalarea, cu toleranta garzii pentru locul de multiboot
	a = amprenta if amprenta is not None else P.amprenta(radacina)
	cod, text, _m = P.verificaPachet(text_marcaj, a=a)
	if cod != P.PACHET_BUN and not (a.get("multiboot") and not P.comparaPornire(m, a)):
		raise EroareCopie(_("Instalarea nu ar primi copia: %s") % text, FISIER_INTREG)
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


def textKexec():
	"""Cum se pune inapoi o copie facuta dintr-un loc kexec Vu+ 4K: stickul scrie partitia nucleului (acolo sta nucleul
	kexec, kexec-multiboot-recovery OE-Alliance: mmcblk0p1 pe Solo/Uno/Ultimo 4K) si sistemul din memorie, deci inlocuieste
	pornirea multipla. Dedus din scriptul OE-Alliance, nemasurat pe un aparat. Scurt: sta si in randul fix al ecranului."""
	return _("Copia e făcută dintr-un loc de pornire multiplă: pusă cu stickul, se scrie în memoria principală și "
		"înlocuiește pornirea multiplă (celelalte locuri nu mai pornesc).")


def textGata(r):
	if r.get("fel") == "vuplus":
		text = _("Copia e gata: %s (%d MB), făcută în %s. Se pune înapoi ca imaginea Vu+ de pe site: dezarhivezi fișierul "
			"pe un stick FAT32 (dosarul vuplus ajunge în rădăcina stickului), oprești receptorul, pui stickul și îl pornești."
			) % (r["nume"], (r["marime"] + 1024 * 1024 - 1) // (1024 * 1024), _textDurata(r["secunde"]))
		return text + (" " + textKexec() if r.get("kexec") else "")
	return _("Copia e gata: %s (%d MB), făcută în %s. Se pune înapoi din Meniu, Setări, Software & Firmware, Imagine nouă "
		"de pe stick.") % (r["nume"], (r["marime"] + 1024 * 1024 - 1) // (1024 * 1024), _textDurata(r["secunde"]))


def textDespre():
	return _("Copia completă are tot ce e pe receptor: imaginea, canalele, setările, pluginurile și modulele de acces. "
		"Se face pe un stick sau un disc USB, ca un fișier pe care instalarea de pe stick îl pune înapoi exact cum e acum. "
		"Receptorul rămâne pornit cât se face copia.")


def textPunere(radacina=None):
	"""Cum se pune inapoi copia, numai pe Vu+ (pe celelalte, si pe Broadcom cu forma arhivei de pe site, ramane randul fix
	al ecranului si al paginii web: Imagine noua de pe stick)."""
	f = forma(P.citesteReguli(radacina))
	if not f or f["fel"] != FORMA_VUPLUS["fel"]:
		return ""
	text = _("Pe Vu+ copia se pune înapoi ca imaginea de pe site: dezarhivezi fișierul pe un stick FAT32, oprești "
		"receptorul, pui stickul și îl pornești.")
	if _kexec(_citesteText(_cale(radacina, "proc/cmdline"), 4096)):
		text += " " + textKexec()
	return text


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
		r = {"ok": True, "mesaj": textGata(rez), "nume": rez["nume"], "marime": rez["marime"], "fel": rez.get("fel")}
	except Oprita:
		r = {"ok": False, "mesaj": _("Copia a fost oprită. Fișierul început s-a șters; pe receptor nu s-a schimbat nimic.")}
	except EroareCopie as eroare:
		if eroare.fisier:
			# fisierul a ramas pe stick: copia s-a scris, verificarea a gasit ceva
			r = {"ok": False, "mesaj": _("Copia s-a scris pe stick, dar verificarea de la sfârșit a găsit o problemă: %s"
				) % eroare}
		else:
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
