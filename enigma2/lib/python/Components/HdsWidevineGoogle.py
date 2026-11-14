# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsWidevineGoogle.py: programul (python3, fara enigma2) care aduce pe receptorul OMULUI modulul Widevine
# (libwidevinecdm.so, ARM pe 32 de biti) de pe serverele Google si il pune in calea unica a imaginii,
# /home/root/.local/share/widevine/libwidevinecdm.so (+ manifest.json alaturi). Il porneste numai Components/HdsWidevine.py,
# DUPA ce omul a citit licenta Google pe ecran si a apasat „Accept” (Eduard, 13.11.2026 09:12); fara --accept-licenta
# nu face nimic. HD Satelit nu distribuie si nu modifica modulul: aparatul omului il descarca direct de la Google.
#
# Drumul (ca inputstreamhelper din Kodi): lista de recuperare ChromeOS (recovery.json) -> imaginea unui Chromebook ARM pe
# 32 de biti (bob, kevin, scarlet; ~1,2 GB, verificata cu SHA-1 si marimea) descarcata in --dosar (memoria interna cand
# are loc, cu LOC_PESTE_FLASH ramas liber dupa ea, altfel un stick sau disc; HdsWidevine.mediu) -> libwidevinecdm.so scos din imagine (Components/HdsChromeOS.py, MIT) -> verificat
# ca biblioteca ARM pe 32 de biti -> pus in --tinta -> arhiva stearsa. Modulul are ~10 MB.
#
# Iesirea, cate un rand, pentru HdsWidevine.py (si pentru om in jurnal):
#   PROCENT <0-100> | STARE <text> | GATA <versiunea> | EROARE <cod> <text>
# Coduri de iesire: 0 gata, 2 Google nu mai are imaginea, 4 fara accept, 6 loc prea putin,
# 7 modulul nu e in imagine, 8 nu e ARM pe 32 de biti, 9 retea/descarcare.

import argparse
import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import urllib.request

RECOVERY_JSON = "https://dl.google.com/dl/edgedl/chromeos/recovery/recovery.json"
# Chromebook-urile ARM cu sistem pe 32 de biti (inputstreamhelper config.py, 24.08.2026): scoase din actualizari, ultima
# versiune ChromeOS 15509.81.0, modulul 4.10.2662.3. Adresele directe, daca Google le scoate din lista.
PLACI = ("bob", "kevin", "scarlet")
ADRESE_DIRECTE = {
	"bob": "https://dl.google.com/dl/edgedl/chromeos/recovery/chromeos_15509.81.0_bob_recovery_stable-channel_mp-v2.bin.zip",
	"kevin": "https://dl.google.com/dl/edgedl/chromeos/recovery/chromeos_15509.81.0_kevin_recovery_stable-channel_mp-v2.bin.zip",
	"scarlet": "https://dl.google.com/dl/edgedl/chromeos/recovery/chromeos_15509.81.0_scarlet_recovery_stable-channel_mp-v8.bin.zip",
}
TINTA = "/home/root/.local/share/widevine"
NUME_CDM = "libwidevinecdm.so"
LOC_PESTE = 20 * 1024 * 1024     # ca inputstreamhelper: 20 MB peste marimea arhivei (stick, disc)
LOC_PESTE_FLASH = 1024 * 1024 * 1024   # pe memoria receptorului raman macar 1 GB liberi cat sta arhiva acolo


def rand(text):
	sys.stdout.write(text + "\n")
	sys.stdout.flush()


def versiune(text):
	return tuple(int(x) for x in re.findall(r"\d+", text or "0"))


def alege(intrari, placi=PLACI):
	"""Imaginea cea mai noua, apoi cea mai mica, dintre placile ARM pe 32 de biti (ca select_best_chromeos_image)."""
	cea_buna = None
	for d in intrari:
		try:
			placa = d["file"].split("_")[2]
		except (KeyError, IndexError, AttributeError):
			continue
		if placa not in placi:
			continue
		d = dict(d, boardname=placa)
		if cea_buna is None or versiune(d.get("version")) > versiune(cea_buna.get("version")) or (
				versiune(d.get("version")) == versiune(cea_buna.get("version")) and
				int(d.get("zipfilesize", 0)) < int(cea_buna.get("zipfilesize", 0))):
			cea_buna = d
	return cea_buna


def _deschide(url, timp=60, metoda=None):
	cerere = urllib.request.Request(url, method=metoda) if metoda else url
	return urllib.request.urlopen(cerere, timeout=timp, context=ssl.create_default_context())


def citeste_lista():
	with _deschide(RECOVERY_JSON) as r:
		return json.loads(r.read().decode("utf-8"))


def elf_arm32(cale):
	"""Biblioteca ELF pe 32 de biti pentru ARM (EI_CLASS=1, e_machine=40)."""
	with open(cale, "rb") as f:
		h = f.read(20)
	return len(h) == 20 and h[:4] == b"\x7fELF" and h[4] == 1 and h[18:20] == b"\x28\x00"


def versiune_modul(cale):
	"""Versiunea scrisa in biblioteca (4.10.x.y), din sirurile ei; "" daca nu se gaseste."""
	try:
		with open(cale, "rb") as f:
			date = f.read()
	except (IOError, OSError):
		return ""
	m = re.search(rb"(?<![\d.])4\.10\.\d{3,5}\.\d{1,3}(?![\d.])", date)
	return m.group(0).decode("ascii") if m else ""


def pe_flash(dosar, radacina="/"):
	try:
		return os.stat(dosar).st_dev == os.stat(radacina).st_dev
	except OSError:
		return True


def descarca(url, tinta, marime, sha1, pas=4 * 1024 * 1024):
	h = hashlib.sha1()
	n = 0
	ultim = -1
	with _deschide(url, timp=120) as r, open(tinta + ".partial", "wb") as f:
		while True:
			bucata = r.read(pas)
			if not bucata:
				break
			f.write(bucata)
			h.update(bucata)
			n += len(bucata)
			if marime:
				p = min(90, n * 90 // marime)
				if p != ultim:
					rand("PROCENT %d" % p)
					ultim = p
	if marime and n != marime:
		raise IOError("marimea nu se potriveste: %d in loc de %d" % (n, marime))
	if sha1 and h.hexdigest() != sha1.lower():
		raise IOError("suma SHA-1 nu se potriveste")
	os.replace(tinta + ".partial", tinta)


def instaleaza(dosar, tinta, accept):
	if not accept:
		rand("EROARE 4 licenta neacceptata")
		return 4
	try:
		ales = alege(citeste_lista())
	except Exception as e:
		ales = None
		rand("STARE lista Google necitita (%s), incerc adresa directa" % (e,))
	if ales is None:
		ales = {"boardname": "bob", "url": ADRESE_DIRECTE["bob"], "zipfilesize": "0", "sha1": "", "version": "15509.81.0"}
	marime = int(ales.get("zipfilesize") or 0)
	lucru = os.path.join(dosar, "hds-widevine")
	shutil.rmtree(lucru, ignore_errors=True)   # o arhiva ramasa de la o rulare oprita (curent, repornire)
	peste = LOC_PESTE_FLASH if pe_flash(dosar) else LOC_PESTE
	if shutil.disk_usage(dosar).free < (marime or 1300 * 1024 * 1024) + peste:
		rand("EROARE 6 loc prea putin")
		return 6
	os.makedirs(lucru, exist_ok=True)
	arhiva = os.path.join(lucru, os.path.basename(ales["url"]))
	try:
		rand("STARE descarc imaginea %s de la Google" % ales["boardname"])
		try:
			descarca(ales["url"], arhiva, marime, ales.get("sha1", ""))
		except Exception as e:
			rand("EROARE 9 descarcarea: %s" % (e,))
			return 9
		rand("STARE scot modulul din imagine")
		sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
		from HdsChromeOS import ChromeOSImage
		if not ChromeOSImage(arhiva).extract_file(filename=NUME_CDM, extract_path=lucru):
			rand("EROARE 7 modulul nu e in imagine")
			return 7
		scos = os.path.join(lucru, NUME_CDM)
		if not elf_arm32(scos):
			rand("EROARE 8 nu e o biblioteca ARM pe 32 de biti")
			return 8
		rand("PROCENT 95")
		v = versiune_modul(scos)
		os.makedirs(tinta, exist_ok=True)
		nou = os.path.join(tinta, NUME_CDM + ".nou")
		shutil.copyfile(scos, nou)
		os.chmod(nou, 0o644)
		os.replace(nou, os.path.join(tinta, NUME_CDM))
		with open(os.path.join(tinta, "manifest.json.nou"), "w") as f:
			json.dump({"name": "WidevineCdm", "version": v, "x-hds-placa": ales["boardname"],
				"x-hds-chromeos": ales.get("version", ""), "x-hds-sursa": ales["url"]}, f)
		os.replace(os.path.join(tinta, "manifest.json.nou"), os.path.join(tinta, "manifest.json"))
		rand("PROCENT 100")
		rand("GATA %s" % (v or "?"))
		return 0
	finally:
		shutil.rmtree(lucru, ignore_errors=True)


def main(argv=None):
	a = argparse.ArgumentParser(description="Modulul Widevine adus de la Google, dupa acceptul licentei.")
	a.add_argument("--instaleaza", action="store_true")
	a.add_argument("--accept-licenta", action="store_true")
	a.add_argument("--dosar", required=False, default="/media/hdd")
	a.add_argument("--tinta", default=TINTA)
	o = a.parse_args(argv)
	if not o.instaleaza:
		a.print_help()
		return 1
	return instaleaza(o.dosar, o.tinta, o.accept_licenta)


if __name__ == "__main__":
	sys.exit(main())
