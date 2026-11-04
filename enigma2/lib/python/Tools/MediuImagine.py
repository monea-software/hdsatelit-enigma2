# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Unde stau fisierele unei imagini inainte de ofgwrite: se primeste doar un disc USB (/dev/sd*) sau RAM (tmpfs).
Fara importuri enigma, ca sa se poata testa pe PC.

ofgwrite -r a citit arhiva din /root, adica de pe mmcblk0p10, chiar partitia pe care o rescria;
radacina a iesit goala si receptorul nu a mai pornit ("No valid root found")."""
import os
import posixpath
import re
import subprocess
import sys

PERMIS_USB = "usb"
PERMIS_RAM = "ram"
REFUZ_INTERN = "intern"
REFUZ_NECUNOSCUT = "necunoscut"
REFUZ_LIPSA = "lipsa"

FISIERE_IMAGINE = ("kernel.bin", "rootfs.tar.bz2")

_ESCAPARE_RX = re.compile(r"\\([0-7]{3})")
_USB_RX = re.compile(r"^/dev/sd[a-z]+[0-9]*$")


def _decodeaza(camp):
	return _ESCAPARE_RX.sub(lambda m: chr(int(m.group(1), 8)), camp)


def citesteMontari(text):
	"""(dispozitiv, punct_montare, tip) pentru fiecare rand din /proc/mounts; \\040 devine spatiu"""
	montari = []
	for linie in text.splitlines():
		campuri = linie.split()
		if len(campuri) >= 3:
			montari.append((_decodeaza(campuri[0]), _decodeaza(campuri[1]), campuri[2]))
	return montari


def montareaCaii(cale, montari):
	"""montarea care tine calea: punctul cel mai lung care o contine; la lungimi egale castiga randul de mai jos"""
	aleasa = None
	for dispozitiv, punct, tip in montari:
		punct = posixpath.normpath(punct)
		if punct == "/" or cale == punct or cale.startswith(punct + "/"):
			if aleasa is None or len(punct) >= len(aleasa[1]):
				aleasa = (dispozitiv, punct, tip)
	return aleasa


def verificaMediuScriere(cale, textMontari=None, realpath=os.path.realpath, stat=os.stat):
	"""(permis, motiv, dispozitiv, punct_montare) pentru folderul cu kernel.bin si rootfs.tar.bz2.
	Refuza tot ce sta pe eMMC, pe dispozitivul radacinii sau pe ceva necunoscut; orice eroare inseamna refuz.
	kernel.bin si rootfs.tar.bz2 trebuie sa stea pe aceeasi montare ca folderul: o legatura spre /root nu trece."""
	try:
		reala = posixpath.normpath(realpath(cale))
		if not reala.startswith("/"):
			return False, REFUZ_LIPSA, None, None
		if textMontari is None:
			with open("/proc/mounts", encoding="utf-8", errors="surrogateescape") as f:
				textMontari = f.read()
		montari = citesteMontari(textMontari)
		montare = montareaCaii(reala, montari)
		if montare is None:
			return False, REFUZ_NECUNOSCUT, None, None
		dispozitiv, punct, tip = montare
		devFolder = stat(reala).st_dev
		devRadacina = stat("/").st_dev
		if devFolder == devRadacina:
			return False, REFUZ_INTERN, dispozitiv, punct
		dispozitivReal = dispozitiv
		if dispozitiv.startswith("/dev/"):
			dispozitivReal = posixpath.normpath(realpath(dispozitiv))
		if punct == "/":
			return False, REFUZ_INTERN, dispozitiv, punct
		for d in (dispozitiv, dispozitivReal):
			if d.startswith("/dev/mmcblk") or d == "/dev/root":
				return False, REFUZ_INTERN, dispozitiv, punct
		for nume in FISIERE_IMAGINE:
			fisier = posixpath.join(reala, nume)
			fisierReal = posixpath.normpath(realpath(fisier))
			montareFisier = montareaCaii(fisierReal, montari)
			if fisierReal == fisier and montareFisier == montare:
				continue
			devFisier = stat(fisierReal).st_dev
			if montareFisier != montare or devFisier != devFolder:
				motiv = REFUZ_INTERN if devFisier == devRadacina else REFUZ_NECUNOSCUT
				return False, motiv, montareFisier[0], montareFisier[1]
		if tip == "tmpfs":
			return True, PERMIS_RAM, dispozitiv, punct
		if _USB_RX.match(dispozitivReal):
			return True, PERMIS_USB, dispozitiv, punct
		return False, REFUZ_NECUNOSCUT, dispozitiv, punct
	except Exception:
		return False, REFUZ_LIPSA, None, None


# NUMELE STICKULUI: ofgwrite pornit din sistem face "mkdir -p /newroot/<punctul de montare al stickului>" prin shell
# (ofgwrite.c, umount_rootfs). Fara ghilimele, pe un stick cu spatiu in eticheta (/run/media/HD SATELIT-sda1) dosarul nu
# se face, mutarea montarii cade fara sa opreasca nimic, radacina se sterge, iar tar nu mai gaseste arhiva: receptorul
# ramane fara sistem. Peticul imaginii pune ghilimele; in binar ramane sirul SIR_OFGWRITE_REPARAT. Cu programul reparat
# se refuza numai semnele care rup si ghilimelele; cu cel nereparat (sau necitit) numai litere, cifre si / . _ - + , : @ =.
# ofgwrite ia punctul de montare din ORICE montare a aceluiasi dispozitiv (castiga ultima), deci se verifica toate.
CALE_OFGWRITE_BIN = "/usr/bin/ofgwrite_bin"
SIR_OFGWRITE_REPARAT = b'mkdir -p "/newroot/%s"'
REFUZ_SPATII = "spatii"
REFUZ_SEMNE = "semne"

_PUNCT_SIGUR_RX = re.compile(r"^[A-Za-z0-9/._+,:@=-]+$")
_RUPE_GHILIMELE_RX = re.compile(r'["$`\\\r\n]')


def ofgwriteReparat(cale=CALE_OFGWRITE_BIN):
	"""True numai daca binarul lui ofgwrite cere dosarul de montare cu ghilimele; lipsa sau o eroare de citire: False."""
	try:
		with open(cale, "rb") as f:
			return SIR_OFGWRITE_REPARAT in f.read()
	except Exception:
		return False


def motivPunct(punct, reparat):
	"""None daca ofgwrite poate folosi punctul de montare; altfel REFUZ_SPATII sau REFUZ_SEMNE."""
	if reparat:
		if not _RUPE_GHILIMELE_RX.search(punct):
			return None
	elif _PUNCT_SIGUR_RX.fullmatch(punct):
		return None
	return REFUZ_SPATII if re.search(r"\s", punct) else REFUZ_SEMNE


def verificaNumeStick(cale, textMontari=None, reparat=None, realpath=os.path.realpath):
	"""(None, None) daca ofgwrite poate scrie de pe `cale`; altfel (REFUZ_SPATII / REFUZ_SEMNE / REFUZ_LIPSA, punctul de
	montare care nu merge). Se verifica montarea caii si toate celelalte montari ale aceluiasi dispozitiv."""
	try:
		if reparat is None:
			reparat = ofgwriteReparat()
		reala = posixpath.normpath(realpath(cale))
		if textMontari is None:
			with open("/proc/mounts", encoding="utf-8", errors="surrogateescape") as f:
				textMontari = f.read()
		montari = citesteMontari(textMontari)
		montare = montareaCaii(reala, montari)
		if montare is None:
			return REFUZ_LIPSA, None
		puncte = [montare[1]] + [p for d, p, t in montari if d == montare[0] and p != montare[1]]
		for punct in puncte:
			motiv = motivPunct(punct, reparat)
			if motiv:
				return motiv, punct
		return None, None
	except Exception:
		return REFUZ_LIPSA, None


# Stickul cu spatii sau semne in eticheta nu se refuza si nu se redenumeste: montarea lui se muta intr-un dosar fara ele,
# iar legatura din /media duce mai departe la ea. Omul nu vede nimic. Eticheta de pe stick ramane aceeasi, deci la
# urmatoarea montare (repornire, stick scos si pus la loc) dosarul ii poarta iar numele, iar mutarea se face din nou
# inainte de scriere. Se poate numai cand calea trece printr-o legatura din /media: caile tinute de ecran raman bune.
DOSAR_MEDIA = "/media"
_FARA_SEMNE_RX = re.compile(r"[^A-Za-z0-9._+,:@=-]")


def mutaMontarea(punct, dosarMedia=DOSAR_MEDIA, dosarTmp="/tmp", ruleaza=subprocess.call):
	"""Muta montarea `punct` langa ea, intr-un dosar fara spatii si fara semne, si refac legaturile din /media. True daca
	s-a mutat; fara legatura sau cu locul ocupat nu se atinge nimic."""
	parinte, nume = posixpath.split(punct)
	nou = posixpath.join(parinte, _FARA_SEMNE_RX.sub("", nume))
	if nou == punct or not _PUNCT_SIGUR_RX.fullmatch(nou):
		return False
	legaturi = []
	for n in os.listdir(dosarMedia):
		loc = posixpath.join(dosarMedia, n)
		if os.path.islink(loc) and posixpath.normpath(os.path.realpath(loc)) == punct:
			legaturi.append(loc)
	if not legaturi:
		return False
	if os.path.ismount(nou) or os.path.islink(nou):
		return False
	os.makedirs(nou, exist_ok=True)
	if os.listdir(nou):
		return False
	temporare = []
	try:
		for loc in legaturi:
			temporar = "%s.hds%d" % (loc, os.getpid())
			if os.path.lexists(temporar):
				os.remove(temporar)
			os.symlink(nou, temporar)
			temporare.append((temporar, loc))
	except OSError:
		for temporar, _loc in temporare:
			os.remove(temporar)
		os.rmdir(nou)
		raise
	if ruleaza(["/bin/mount", "-o", "move", punct, nou], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL) != 0:
		for temporar, _loc in temporare:
			os.remove(temporar)
		os.rmdir(nou)
		return False
	for temporar, loc in temporare:
		os.replace(temporar, loc)
	# mount.sh sterge la scoaterea stickului dosarul scris in fisierul lui din /tmp
	fisier = posixpath.join(dosarTmp, ".automount-" + nume)
	if os.path.exists(fisier):
		with open(fisier, "w", encoding="utf-8") as f:
			f.write(posixpath.basename(nou) + "\n")
	os.rmdir(punct)
	return True


def pregatesteNumeStick(cale):
	"""(motiv, punct) ca verificaNumeStick, dupa ce montarea cu spatii sau semne a fost mutata. Refuzul ramane numai daca
	mutarea n-a mers: atunci ofgwrite nu porneste."""
	motiv, punct = verificaNumeStick(cale)
	if motiv not in (REFUZ_SPATII, REFUZ_SEMNE) or posixpath.normpath(os.path.realpath(cale)) == posixpath.normpath(cale):
		return motiv, punct
	try:
		mutaMontarea(punct)
	except Exception as eroare:
		print("[MediuImagine] montarea %s nu s-a mutat: %s" % (punct, eroare))
	return verificaNumeStick(cale)


VITEZE_USB = ((20000, "USB 3.2"), (10000, "USB 3.1"), (5000, "USB 3.0"), (480, "USB 2.0"), (1, "USB 1.1"))


def versiuneUsb(cale, clasa="/sys/class/block"):
	"""„USB 3.0” sau „USB 2.0”: viteza la care lucreaza acum stickul, din sysfs. Un stick USB 3 pus intr-un port USB 2
	arata 2.0, adica exact ce conteaza pentru om. None cand nu e pe USB sau nu se poate citi."""
	try:
		with open("/proc/mounts", encoding="utf-8", errors="surrogateescape") as f:
			montare = montareaCaii(posixpath.normpath(os.path.realpath(cale)), citesteMontari(f.read()))
		loc = os.path.realpath(posixpath.join(clasa, posixpath.basename(montare[0])))
		while len(loc) > 1:
			fisier = posixpath.join(loc, "speed")
			if os.path.exists(fisier):
				with open(fisier) as f:
					viteza = float(f.read().strip())
				for prag, nume in VITEZE_USB:
					if viteza >= prag:
						return nume
				return None
			loc = posixpath.dirname(loc)
	except Exception:
		pass
	return None


if __name__ == "__main__":
	if len(sys.argv) != 2:
		print("folosire: python3 MediuImagine.py <folderul cu kernel.bin si rootfs.tar.bz2>")
		sys.exit(2)
	permis, motiv, dispozitiv, punct = verificaMediuScriere(sys.argv[1])
	if permis:
		motivNume, punctNume = verificaNumeStick(sys.argv[1])
		if motivNume:
			permis, motiv, punct = False, motivNume, punctNume
	print("%s: %s%s" % ("PERMIS" if permis else "REFUZAT", motiv, " (%s pe %s)" % (dispozitiv, punct) if dispozitiv else ""))
	sys.exit(0 if permis else 1)
