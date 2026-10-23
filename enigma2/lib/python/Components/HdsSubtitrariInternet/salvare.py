# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# salvare.py: fisierul descarcat -> o subtitrare langa film.
#
# - arhivele zip (subs.ro, SubDL): se alege subtitrarea potrivita (episodul SxxEyy al filmului, apoi SRT, apoi cea mai
#   mare), cu paza la arhive umflate (cel mult MAX_OCTETI dezarhivati pe fisier, cel mult MAX_MEMBRI membri); RAR si 7z
#   nu se deschid (unrar nu e liber), cu un mesaj;
# - numele: numele filmului, limba in doua litere si extensia („film.ro.srt”), deci cititorul imaginii
#   (Components/HdsSubtitrariFilm.py) il gaseste singur si ii stie limba; un fisier care exista nu se suprascrie niciodata
#   („film.ro.2.srt”);
# - scrierea: atomica (.nou + os.replace); daca dosarul filmului nu se poate scrie (disc numai citire, retea), in
#   DOSARE_REZERVA, cu drumul in mesaj.
# Fisierul omului nu se schimba: octetii se scriu cum au venit (codarea o alege cititorul).

import io
import os
import re
import zipfile

from . import limbi as LB

EXTENSII = (".srt", ".sub", ".ass", ".ssa", ".vtt", ".smi", ".sami", ".txt", ".mpl")
MAX_OCTETI = 5 * 1024 * 1024
MAX_MEMBRI = 200
# (dosarul, punctul de montare care trebuie sa existe sau None): /media/hdd numai daca e chiar un disc montat, altfel
# dosarul s-ar face pe radacina din eMMC (si s-ar ascunde apoi sub discul montat mai tarziu)
DOSARE_REZERVA = (("/media/hdd/subtitrari", "/media/hdd"), ("/tmp/hds-subtitrari", None))


def montat(cale):
	"""Un punct de montare chiar montat (/media/hdd poate fi o legatura spre /run/media/...: ismount pe legatura da
	False, deci pe calea reala). Folosit si de tv.py (dosarul subtitrarilor de pe canale)."""
	return os.path.ismount(os.path.realpath(cale))


class EroareSalvare(Exception):
	"""Textul pentru om."""


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _episod(nume):
	m = re.search(r"(?i)S(\d{1,2})[ ._-]?E(\d{1,3})|(\d{1,2})x(\d{2,3})", nume or "")
	if not m:
		return None
	return (int(m.group(1) or m.group(3)), int(m.group(2) or m.group(4)))


def dinArhiva(octeti, nume, film=None):
	"""-> (octetii subtitrarii, numele ei). O arhiva zip se deschide; un fisier text trece asa cum e."""
	if octeti[:4] == b"Rar\x21":       # semnul arhivelor RAR
		raise EroareSalvare(_t("Arhiva e RAR; receptorul deschide numai arhive ZIP."))
	if octeti[:6] == b"7z\xbc\xaf\x27\x1c":
		raise EroareSalvare(_t("Arhiva e 7z; receptorul deschide numai arhive ZIP."))
	if octeti[:4] != b"PK\x03\x04":
		if len(octeti) > MAX_OCTETI:
			raise EroareSalvare(_t("Fișierul primit e prea mare pentru o subtitrare."))
		return octeti, nume
	try:
		z = zipfile.ZipFile(io.BytesIO(octeti))
		membri = [m for m in z.infolist()[:MAX_MEMBRI] if not m.is_dir()]
	except (zipfile.BadZipFile, OSError, ValueError):
		raise EroareSalvare(_t("Arhiva primită e stricată."))
	subtitrari = [m for m in membri if os.path.splitext(m.filename)[1].lower() in EXTENSII and 0 < m.file_size <= MAX_OCTETI]
	if not subtitrari:
		interzise = [m for m in membri if os.path.splitext(m.filename)[1].lower() in (".rar", ".7z")]
		if interzise:
			raise EroareSalvare(_t("Arhiva are înăuntru o arhivă RAR sau 7z; receptorul deschide numai ZIP."))
		raise EroareSalvare(_t("Arhiva nu are nicio subtitrare."))
	dorit = _episod((film or {}).get("release") or (film or {}).get("nume"))

	def cheie(m):
		ep = _episod(os.path.basename(m.filename))
		return (
			0 if (dorit and ep == dorit) else (1 if not dorit or ep is None else 2),
			0 if m.filename.lower().endswith(".srt") else 1,
			-m.file_size,
		)
	ales = sorted(subtitrari, key=cheie)[0]
	try:
		with z.open(ales) as f:
			date = f.read(MAX_OCTETI + 1)
	except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError):
		raise EroareSalvare(_t("Subtitrarea din arhivă nu se poate citi."))
	if len(date) > MAX_OCTETI:
		raise EroareSalvare(_t("Subtitrarea din arhivă e prea mare."))
	return date, os.path.basename(ales.filename)


def numeFisier(cale_film, limba, nume_sursa, exista=os.path.exists):
	"""Calea noua langa film: „film.ro.srt”, sau „film.ro.2.srt” daca exista deja."""
	dosar = os.path.dirname(cale_film)
	baza = os.path.splitext(os.path.basename(cale_film))[0]
	ext = os.path.splitext(nume_sursa or "")[1].lower()
	if ext not in EXTENSII:
		ext = ".srt"
	doua = LB.DOUA.get(limba) or "und"
	cale = os.path.join(dosar, "%s.%s%s" % (baza, doua, ext))
	n = 2
	while exista(cale) and n < 100:
		cale = os.path.join(dosar, "%s.%s.%d%s" % (baza, doua, n, ext))
		n += 1
	return cale


def _scrie(cale, octeti):
	nou = cale + ".nou"
	fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
	try:
		rest = octeti
		while rest:
			rest = rest[os.write(fd, rest):]
		os.fsync(fd)
	finally:
		os.close(fd)
	os.replace(nou, cale)


def salveaza(octeti, nume_sursa, cale_film, limba):
	"""-> (calea scrisa, mesaj pentru om). Langa film, altfel intr-un dosar de rezerva."""
	cale = numeFisier(cale_film, limba, nume_sursa)
	try:
		_scrie(cale, octeti)
		return cale, _t("Subtitrarea s-a salvat lângă film: %s") % os.path.basename(cale)
	except (OSError, IOError):
		try:
			os.unlink(cale + ".nou")
		except OSError:
			pass
	for dosar, montare in DOSARE_REZERVA:
		if montare and not montat(montare):
			continue
		try:
			if not os.path.isdir(dosar):
				os.makedirs(dosar)
			cale = numeFisier(os.path.join(dosar, os.path.basename(cale_film)), limba, nume_sursa)
			_scrie(cale, octeti)
			return cale, _t("Dosarul filmului nu se poate scrie; subtitrarea s-a salvat în %s") % cale
		except (OSError, IOError):
			continue
	raise EroareSalvare(_t("Subtitrarea nu s-a putut salva nicăieri."))
