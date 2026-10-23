# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Unde stau fisierele unei imagini inainte de ofgwrite: se primeste doar un disc USB (/dev/sd*) sau RAM (tmpfs).
Fara importuri enigma, ca sa se poata testa pe PC.

ofgwrite -r a citit arhiva din /root, adica de pe mmcblk0p10, chiar partitia pe care o rescria;
radacina a iesit goala si receptorul nu a mai pornit ("No valid root found")."""
import os
import posixpath
import re
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


if __name__ == "__main__":
	if len(sys.argv) != 2:
		print("folosire: python3 MediuImagine.py <folderul cu kernel.bin si rootfs.tar.bz2>")
		sys.exit(2)
	permis, motiv, dispozitiv, punct = verificaMediuScriere(sys.argv[1])
	print("%s: %s%s" % ("PERMIS" if permis else "REFUZAT", motiv, " (%s pe %s)" % (dispozitiv, punct) if dispozitiv else ""))
	sys.exit(0 if permis else 1)
