# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSoftwareUpdate.py — Actualizarea imaginii HDSatelit direct din interfata, fara trucuri
# externe (stick + Maintenance Mode ramane doar plasa de siguranta, nu calea normala).
# Cod 100% propriu, scris de la zero.
#
# NUME: "Hds" la inceput, NU doar "SoftwareUpdate" — gasit in emulator: skin.xml are DEJA un
# `<screen name="SoftwareUpdate">` pentru ecranul cu acelasi nume al altor imagini (actualizare de PACHETE opkg
# din feed, o functie DIFERITA de asta). Enigma2 cauta skin-ul
# DUPA NUMELE CLASEI, in skin.xml INAINTE de a incerca atributul `skin` din clasa Python
# (skin.py, readSkin()) — cu numele vechi, ecranul s-ar fi deschis cu skinul GRESIT (widget-uri
# feedstatus_*/package_*/activity/traffic_*, nimic din ce foloseste codul de mai jos),
# confirmat cu jurnalul emulatorului: "warning, skin is missing element detaliu/lista".
# Cu numele nou, fara nicio coliziune, se foloseste corect skinul din clasa (mai jos).
#
# MECANISMUL, din cercetarea DIRECTA pe stratul comun de masina
# (meta-dinobot/u57), valabil identic pentru orice DISTRO, deci si pentru HDSatelit:
#   - un pachet de actualizare e o structura e2/update/kernel.bin + e2/update/rootfs.tar.bz2,
#     cu un fisier e2/update/imageversion (UN SINGUR RAND cu numele/versiunea imaginii, scris
#     de clasa de imagine dinobot-emmc-multiboot_image.bbclass — nu chei "cheie=valoare").
#   - utilitarul `ofgwrite` (deja in imagine, GPL-2.0, vezi hdsatelit-base.bb) scrie kernelul
#     si rootfs-ul pe flash, cu RECUNOASTERE AUTOMATA a dispozitivelor tinta din /proc/cmdline
#     — verificat pe receptorul fizic (Amiko Viper 4K V20, u57): "Found cmdLine
#     kernel device: /dev/mmcblk0p9", "...rootfs device: /dev/mmcblk0p10". NU trebuie sa
#     ghicim/hardcodam noi numele dispozitivelor — de-aici de ce codul de mai jos NU foloseste
#     "boxbranding" (modulul exista doar ca incercare opționala, fara efect, in alta parte a
#     codului nostru — pachetul boxbranding nici nu e in RDEPENDS-ul imaginii HDSatelit; si
#     "/etc/image-version" propriu HDSatelit, scris de Makefile.am, NU are cheile de
#     dispozitiv — acelea veneau doar din fisierul imaginii de dinainte de primul flash).
#   - Paza de model (Components/HdsPazaModel.py): un pachet se verifica si se scrie numai daca are
#     e2/update/hdsatelit-model (marcajul pus la construire), marcajul se potriveste cu amprenta
#     receptorului (cipul, antetul deviceinfo, partitiile, tipul placii din driver si din eticheta) si sumele
#     SHA-256 ale lui kernel.bin si rootfs.tar.bz2 sunt cele din marcaj. Amprenta se citeste o data pe
#     cautare, pentru toate pachetele listei. Marcajul nu e semnat: paza e impotriva greselilor (un zip pentru
#     alt receptor, un pachet stricat), nu impotriva cuiva care face un marcaj fals.
#   - Dosarul curat: ofgwrite ia dintr-un dosar orice fisier care seamana a nucleu („kernel” si „.bin” in nume,
#     uImage) sau a sistem (rootfs.*, orice *.tar.xz), iar ultimul gasit castiga (find_image_files). De aceea si
#     pachetul din zip, si cel din dosarul e2/update de pe stick se copiaza intai in dosarul curat
#     .hds-actualizare-extrasa/e2/update, numai cu cele patru nume ale pachetului; sumele, simularea si scrierea
#     se fac numai pe acel dosar, iar iesirea simularii trebuie sa numeasca exact kernel.bin si rootfs.tar.bz2 din
#     el. Copierea si sumele ruleaza pe un fir separat (HdsPazaModel.LucrareFundal), rezultatul se culege cu un
#     eTimer; chiar inainte de scriere se verifica din nou marcajul, amprenta si ca fisierele (marime, ora) nu
#     s-au schimbat de la sume.
#   - Intrebarile si refuzurile au fereastra lor (Screens/HdsPazaModel.py): fereastra de mesaj a skinului
#     HDSatelit are loc numai pentru trei randuri.
#
# ATENTIE, gasit cu dovada directa: iesirea lui
# `ofgwrite -n` (simulare, NU scrie nimic — verificat cu uptime/PID/mtime/dmesg neschimbate)
# scrie totusi "Successfully flashed rootfs!"/"...kernel!" la fel ca la o scriere REALA — text
# INSELATOR. Codul de mai jos NU arata userului niciun mesaj de succes bazat pe acel text:
# verifica doar, cu propria logica, ca pachetul a fost RECUNOSCUT (kernel + rootfs + dispozitive
# gasite, fara "error"), arata userului iesirea bruta, onest, si abia apoi il lasa sa decida
# separat, cu un al doilea avertisment explicit, daca trece la scrierea reala.
#
# Scrierea reala foloseste "init 4" inainte de ofgwrite (procedura probata), NU flag-ul
# "-f" al lui ofgwrite. "init 4" opreste Enigma2 (si tot runlevel-ul 3) — inclusiv procesul
# Python care ruleaza acest ecran — deci secventa init-4+ofgwrite NU poate rula ca o functie
# normala, sincrona, in acest proces: e pornita ca o comanda shell DETASATA (os.system cu "&"),
# care supravietuieste mortii Enigma2 (proces copil, nu e omorat doar pentru ca parintele
# dispare). Iesirea ei se scrie intr-un fisier jurnal PE ACELASI MEDIU montat (nu in /tmp, care
# poate sa nu supravietuiasca unei scrieri reale a radacinii), pentru control ulterior.
#
# TESTARE: intai emulator (ruleaza.sh) — tot fluxul (cautare, lista, confirmare, simulare,
# citirea iesirii), fara nicio scriere reala posibila acolo (binarul ofgwrite nu exista in
# containerul x86 al emulatorului — comportament asteptat, tratat clar in interfata, nu crash).
# Probele pe receptorul fizic se fac STRICT cu simularea ("-n"), niciodata cu scrierea reala.

# PAZNIC: inainte de dezarhivare si inainte de fiecare ofgwrite se verifica, cu
# Tools/MediuImagine.py, ca fisierele stau pe un stick USB (sau in RAM). O data, un ofgwrite -r cu
# imaginea in /root (pe mmcblk0p10, chiar radacina rescrisa) a lasat receptorul fara sistem.

import glob
import os
import shlex
import shutil
import time
import zipfile

from .Screen import Screen
from Components.ActionMap import ActionMap
from Components.MenuList import MenuList
from Components.Label import Label
from Components.Button import Button
from Components.ScrollLabel import ScrollLabel
from Components.Console import Console
from Components.Harddisk import harddiskmanager

from Screens.MessageBox import MessageBox
from Tools.MediuImagine import verificaMediuScriere, REFUZ_INTERN, REFUZ_LIPSA
from Components import HdsPazaModel

NUME_KERNEL = "kernel.bin"
NUME_ROOTFS = "rootfs.tar.bz2"
NUME_VERSIUNE = "imageversion"
NUME_MARCAJ = HdsPazaModel.NUME_MARCAJ  # semnul receptorului pentru care e pachetul
SUBCALE_UPDATE = ("e2", "update")  # structura standard
FOLDER_DEZARHIVARE = ".hds-actualizare-extrasa"  # dosarul curat, pe acelasi mediu
NUME_PACHET = (NUME_KERNEL, NUME_ROOTFS, NUME_VERSIUNE, NUME_MARCAJ)
BLOC_COPIE = 1024 * 1024
CALE_OFGWRITE = "/usr/bin/ofgwrite"
CALE_ENIGMA2_ETC = "/etc/enigma2"
PREFIX_FOLDER_BACKUP = "hds-backup-setari-"

# Receptorul are o singura pereche kernel + radacina pe eMMC (mmcblk0p9, mmcblk0p10), fara sloturi: o scriere
# reala sterge tot /etc/enigma2, iar un rootfs care nu porneste se repara numai din Maintenance Mode.
# Inainte de scriere se face o copie a datelor omului pe mediul imaginii, un dosar plat
# hds-backup-setari-AAAALLZZ_HHMMSS/ cu:
#   - fisierele de canale si temporizatoare de mai jos si toate userbouquet.*;
#   - settings din config.pickle() (arborele pe care enigma2 l-ar scrie la iesire; fisierul de pe disc e scris
#     neatomic de saveToFile), fara CHEI_SCOASE_DIN_COPIE;
#   - datele imaginii: fisierele hds_* (datele canalelor, baza canalelor) si dosarul hdsatelit/ (alegerile
#     pistelor, ecranul de pornire); fara legaturi simbolice si fara fisierele temporare .nou / .nou.<nr>.
# Un fisier care exista si nu s-a putut copia, lipsa spatiului sau un lamedb nevalid (scris chiar atunci de
# lib/dvb/db.cpp, tot neatomic; se reia o data dupa PAUZA_RELUARE_LAMEDB) = copie cazuta: scrierea nu porneste
# fara intrebarea „Continui fara copie?”, cu „Nu” ales. HdsImportSetari cheama aceeasi functie, cu date_hds=False
# (numai ce suprascrie importul, fara hdsatelit/ pe eMMC). Dosarul plat nu se pune la loc singur: fisierele se iau
# de acolo de mana.
FISIERE_SETARI_SIMPLE = ("lamedb", "lamedb5", "bouquets.tv", "bouquets.radio", "timers.xml", "autotimer.xml")
NUME_SETARI = "settings"
PREFIX_DATE_HDS = "hds_"
DOSAR_DATE_HDS = "hdsatelit"
# jetonul interfetei web e numai al acestui receptor; depanarea pornita ar umple discul cu jurnalul la pornire
CHEI_SCOASE_DIN_COPIE = ("config.plugins.hdswebcontrol.token", "config.crash.enabledebug")
ANTET_LAMEDB = "eDVB services /4/"
PAUZA_RELUARE_LAMEDB = 2
REZERVA_SPATIU_COPIE = 1024 * 1024


def _hdsAfisajActualizare(pornita):
	"""Afisajul din fata arata „UPD” cat scrie ofgwrite (Components/HdsAfisaj.py). Nu arunca."""
	try:
		from Components import HdsAfisaj
		HdsAfisaj.actualizare(pornita)
	except Exception:
		pass


def _esteTemporar(nume):
	"""Fisierele scrise pe jumatate de scriitorii atomici (.nou, .nou.<nr>, .bak.nou) nu intra in copie."""
	if nume.endswith(".nou"):
		return True
	baza, _punct, coada = nume.rpartition(".")
	return bool(baza) and coada.isdigit() and baza.endswith(".nou")


def _lamedbValid(cale):
	"""Primul rand e antetul formatului 4, iar sectiunile transponders si services se inchid cu cate un rand
	"end" (lib/dvb/db.cpp, saveServicelist)."""
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			if f.readline().rstrip("\r\n") != ANTET_LAMEDB:
				return False
			capete = 0
			for rand in f:
				if rand.rstrip("\r\n") == "end":
					capete += 1
			return capete >= 2
	except OSError:
		return False


def _faraCheiScoase(text):
	"""Randurile „cheie=valoare” fara CHEI_SCOASE_DIN_COPIE; restul neschimbat."""
	randuri = []
	for rand in text.splitlines():
		cheie = rand.split("=", 1)[0].strip()
		if cheie in CHEI_SCOASE_DIN_COPIE:
			continue
		randuri.append(rand)
	return "\n".join(randuri) + ("\n" if randuri else "")


def _textSetari():
	"""settings pentru copie: config.pickle() pe firul enigma2, altfel fisierul de pe disc; None daca nu exista
	niciunul. Intoarce textul intreg, cu cheile scoase abia la scriere."""
	try:
		from Components.config import config
		text = config.pickle()
		if text:
			return text
	except Exception:
		pass
	cale = os.path.join(CALE_ENIGMA2_ETC, NUME_SETARI)
	if not os.path.isfile(cale):
		return None
	with open(cale, "r", encoding="utf-8", errors="surrogateescape") as f:
		return f.read()


def _scrieTextSetari(cale, text):
	try:
		date = text.encode("utf-8", "surrogateescape")
	except UnicodeEncodeError:
		date = text.encode("utf-8", "replace")
	with open(cale, "wb") as f:
		f.write(date)
		f.flush()
		os.fsync(f.fileno())


def _fisiereDeCopiat(date_hds):
	"""[(cale_sursa, nume_relativ)]: numai fisiere obisnuite, fara legaturi simbolice."""
	perechi = []
	for nume in FISIERE_SETARI_SIMPLE:
		perechi.append((os.path.join(CALE_ENIGMA2_ETC, nume), nume))
	for cale in sorted(glob.glob(os.path.join(CALE_ENIGMA2_ETC, "userbouquet.*"))):
		perechi.append((cale, os.path.basename(cale)))
	if date_hds:
		for cale in sorted(glob.glob(os.path.join(CALE_ENIGMA2_ETC, PREFIX_DATE_HDS + "*"))):
			perechi.append((cale, os.path.basename(cale)))
		dosar = os.path.join(CALE_ENIGMA2_ETC, DOSAR_DATE_HDS)
		if os.path.isdir(dosar) and not os.path.islink(dosar):
			for radacina, dosare, fisiere in os.walk(dosar):
				dosare[:] = sorted(d for d in dosare if not os.path.islink(os.path.join(radacina, d)))
				for nume in sorted(fisiere):
					cale = os.path.join(radacina, nume)
					perechi.append((cale, os.path.relpath(cale, CALE_ENIGMA2_ETC)))
	rezultat = []
	for cale, nume in perechi:
		if os.path.islink(cale) or not os.path.isfile(cale) or _esteTemporar(os.path.basename(cale)):
			continue
		rezultat.append((cale, nume))
	return rezultat


def _bazaCanalelor(cerere):
	"""Baza canalelor (Components/HdsCulegereCanale.py) inainte de copie ("copie": scrisa acum, daca s-a schimbat
	ceva, ca sa intre in copie) si inainte de flash ("flash": nicio scriere pana la repornirea interfetei). Nu arunca."""
	try:
		from Components import HdsCulegereCanale
		if cerere == "copie":
			HdsCulegereCanale.inainte_de_copie()
		else:
			HdsCulegereCanale.opreste_scrierile()
	except Exception as eroare:
		print("[HdsSoftwareUpdate] baza canalelor (%s): %s" % (cerere, eroare))


def _creeazaBackupSetari(mountpoint, date_hds=True):
	"""Copia din antetul de mai sus, intr-un dosar nou pe mediul dat. Nu arunca niciodata; intoarce
	(dosar_sau_None, lista_fisierelor_copiate, eroare_sau_None). O eroare inseamna copie incompleta."""
	folder = os.path.join(mountpoint, PREFIX_FOLDER_BACKUP + time.strftime("%Y%m%d_%H%M%S"))
	copiate = []
	try:
		de_copiat = _fisiereDeCopiat(date_hds)
		text_setari = _textSetari()
	except (OSError, ValueError) as eroare:
		return None, copiate, str(eroare)
	necesar = REZERVA_SPATIU_COPIE + len(text_setari or "")
	for cale, _nume in de_copiat:
		try:
			necesar += os.path.getsize(cale)
		except OSError:
			pass
	if not _spatiuSuficient(mountpoint, necesar):
		return None, copiate, _("spațiu insuficient pe %s") % mountpoint
	try:
		os.makedirs(folder, exist_ok=True)
	except OSError as eroare:
		return None, copiate, str(eroare)
	necopiate = []
	for cale, nume in de_copiat:
		tinta = os.path.join(folder, nume)
		try:
			os.makedirs(os.path.dirname(tinta), exist_ok=True)
			shutil.copy2(cale, tinta)
			copiate.append(nume)
		except OSError:
			necopiate.append(nume)
	if text_setari is not None:
		try:
			_scrieTextSetari(os.path.join(folder, NUME_SETARI), _faraCheiScoase(text_setari))
			copiate.append(NUME_SETARI)
		except OSError:
			necopiate.append(NUME_SETARI)
	if "lamedb" in copiate and not _lamedbValid(os.path.join(folder, "lamedb")):
		time.sleep(PAUZA_RELUARE_LAMEDB)
		try:
			shutil.copy2(os.path.join(CALE_ENIGMA2_ETC, "lamedb"), os.path.join(folder, "lamedb"))
		except OSError:
			pass
		if not _lamedbValid(os.path.join(folder, "lamedb")):
			return folder, copiate, _("lista de canale (lamedb) nu e întreagă")
	if necopiate:
		return folder, copiate, _("%d fișiere nu s-au putut copia (%s)") % (len(necopiate), ", ".join(necopiate[:5]))
	return folder, copiate, None


# ---------------------------------------------------------------- descoperirea pachetelor

def _discuriMontate():
	"""Discuri reale montate (HDD/USB), la fel ca SwapManager.py — nimic inventat aici."""
	rezultat = []
	for partitie in harddiskmanager.getMountedPartitions():
		if partitie.mountpoint and partitie.mountpoint not in ("/", "/boot") and os.path.isdir(partitie.mountpoint):
			rezultat.append(partitie)
	return rezultat


def _primaLinie(cale):
	"""Primul rand nevid dintr-un fisier text mic, sau None. e2/update/imageversion e UN SINGUR
	rand cu numele/versiunea (nu chei=valoare) — vezi cercetarea din antetul fisierului."""
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			for linie in f:
				linie = linie.strip()
				if linie:
					return linie
	except OSError:
		pass
	return None


def _textMarcaj(cale):
	"""Textul marcajului de model (cel mult HdsPazaModel.MARIME_MAXIMA_TEXT octeti), sau None daca lipseste."""
	try:
		if os.path.getsize(cale) > HdsPazaModel.MARIME_MAXIMA_TEXT:
			return ""
		with open(cale, "rb") as f:
			return f.read().decode("utf-8", "replace")
	except OSError:
		return None


def _candidatDinFolder(disc):
	"""None daca <disc>/e2/update nu are structura completa; altfel un dict cu detaliile. „cale_finala” (dosarul
	curat) e gata abia dupa copiere."""
	cale_update = os.path.join(disc.mountpoint, *SUBCALE_UPDATE)
	cale_kernel = os.path.join(cale_update, NUME_KERNEL)
	cale_rootfs = os.path.join(cale_update, NUME_ROOTFS)
	if os.path.isfile(cale_kernel) and os.path.isfile(cale_rootfs):
		return {
			"tip": "folder",
			"disc": disc,
			"cale_update": cale_update,
			"cale_finala": None,
			"cale_zip": None,
			"versiune": _primaLinie(os.path.join(cale_update, NUME_VERSIUNE)),
			"marcaj": _textMarcaj(os.path.join(cale_update, NUME_MARCAJ)),
		}
	return None


def _candidatiDinZipuri(disc):
	"""Scaneaza DOAR radacina discului (fara subfoldere — conventie proprie, simpla) pentru
	fisiere .zip care contin, oriunde in interior, structura e2/update/kernel.bin +
	e2/update/rootfs.tar.bz2. Nu dezarhiveaza acum — doar detecteaza si citeste versiunea."""
	rezultat = []
	try:
		nume_fisiere = os.listdir(disc.mountpoint)
	except OSError:
		return rezultat
	sufix_kernel = "/".join(SUBCALE_UPDATE) + "/" + NUME_KERNEL
	sufix_rootfs = "/".join(SUBCALE_UPDATE) + "/" + NUME_ROOTFS
	for nume in sorted(nume_fisiere):
		if not nume.lower().endswith(".zip"):
			continue
		cale_zip = os.path.join(disc.mountpoint, nume)
		try:
			with zipfile.ZipFile(cale_zip) as z:
				# numele cu bara inversa (arhive facute pe Windows) se cauta dupa forma cu „/”, dar se citesc dupa
				# numele lor adevarat
				originale = {}
				for n in z.namelist():
					originale.setdefault(n.replace("\\", "/"), n)
				intrari = list(originale)
				potriviri_kernel = [n for n in intrari if n.endswith(sufix_kernel)]
				potriviri_rootfs = [n for n in intrari if n.endswith(sufix_rootfs)]
				if not potriviri_kernel or not potriviri_rootfs:
					continue
				radacina = potriviri_kernel[0][: -len(NUME_KERNEL)]
				versiune = None
				nume_versiune = radacina + NUME_VERSIUNE
				if nume_versiune in originale:
					try:
						continut = z.read(originale[nume_versiune]).decode("utf-8", "replace")
						versiune = next((l.strip() for l in continut.splitlines() if l.strip()), None)
					except Exception:
						versiune = None
				marcaj = None
				nume_marcaj = radacina + NUME_MARCAJ
				if nume_marcaj in originale:
					# un marcaj care nu se poate citi (criptat, date stricate) = marcaj stricat, numai pentru acest zip
					try:
						info = z.getinfo(originale[nume_marcaj])
						if info.file_size > HdsPazaModel.MARIME_MAXIMA_TEXT:
							marcaj = ""
						else:
							marcaj = z.read(info).decode("utf-8", "replace")
					except Exception as eroare:
						print("[HdsSoftwareUpdate] marcajul din %s nu se poate citi: %s" % (nume, eroare))
						marcaj = ""
				rezultat.append({
					"tip": "zip",
					"disc": disc,
					"cale_finala": None,  # gata doar dupa dezarhivare
					"cale_zip": cale_zip,
					"radacina_in_zip": radacina,
					"versiune": versiune,
					"marcaj": marcaj,
				})
		except Exception as eroare:
			# un zip care nu se poate citi nu ascunde celelalte pachete
			print("[HdsSoftwareUpdate] %s nu se poate citi: %s" % (nume, eroare))
			continue
	return rezultat


def pazaPachet(c, a=None):
	"""(cod, text) al pazei de model pentru un pachet gasit: marcajul lui fata de receptorul acesta, fara sume. `a`:
	amprenta receptorului citita o data pentru toata lista (fara ea se citeste acum)."""
	try:
		cod, text, _marcaj = HdsPazaModel.verificaPachet(c.get("marcaj"), a=a)
	except Exception as eroare:
		print("[HdsSoftwareUpdate] paza de model: %s" % eroare)
		cod, text = HdsPazaModel.REFUZ_NECITIT, HdsPazaModel.textRefuz(HdsPazaModel.REFUZ_NECITIT)
	return cod, text


def cautaCandidati(discuri=None):
	"""Toate pachetele de actualizare de pe `discuri` (implicit mediile montate acum), fiecare cu verdictul pazei
	(„paza”). Amprenta receptorului se citeste o singura data, pentru toate pachetele. Cu `discuri` dat, functia
	atinge numai fisiere (interfata web o cheama pe un fir separat)."""
	if discuri is None:
		discuri = _discuriMontate()
	candidati = []
	for disc in discuri:
		c = _candidatDinFolder(disc)
		if c:
			candidati.append(c)
		candidati.extend(_candidatiDinZipuri(disc))
	if candidati:
		try:
			a = HdsPazaModel.amprenta()
		except Exception as eroare:
			print("[HdsSoftwareUpdate] amprenta: %s" % eroare)
			a = None
		for c in candidati:
			c["paza"] = pazaPachet(c, a)
	return candidati


def _numePachet(c):
	"""Numele pachetului: arhiva, sau dosarul e2/update"""
	if c["tip"] == "folder":
		return _("dosarul e2/update")
	return os.path.basename(c["cale_zip"])


def _numeSiVersiune(c):
	"""[numele pachetului, versiunea]; versiunea lipseste cand numele o contine deja"""
	nume = _numePachet(c)
	versiune = c.get("versiune") or ""
	if versiune and versiune in nume:
		return [nume]
	return [nume, versiune or _("versiune necunoscută")]


# randurile de text si randurile tehnice ale ferestrei fiecarei intrebari (Screens/HdsPazaModel.skinIntrebare)
RANDURI_VERIFICARE = (4, 0)
RANDURI_CONFIRMARE = (9, 4)


def textVerificare(c):
	"""Intrebarea de dinaintea simularii, pentru pachetul `c`"""
	return _("Pachetul: %s") % "  ·  ".join(_numeSiVersiune(c)) + "\n" + \
		_("Acum se face numai o verificare (o simulare): nu se scrie nimic pe receptor. Continui?")


def textUltimaConfirmare(c, inregistrare=False, recuperare=""):
	"""Ultima confirmare: textul simplu (se termina cu intrebarea), apoi, dupa un rand gol, randurile mai mici: fraza
	cu dosarul pentru Maintenance Mode (`recuperare`, poate lipsi) si pachetul."""
	sus = _("Atenție: o înregistrare este în curs chiar acum.") + "\n" if inregistrare else ""
	tehnic = (recuperare.strip() + "\n" if recuperare and recuperare.strip() else "") + \
		_("Pachet: %s") % "  ·  ".join(_numeSiVersiune(c))
	return sus + _("Noul software se scrie acum pe receptor. Nu opri receptorul din priză și nu scoate stickul cât "
		"timp scrie; interfața se oprește, iar receptorul repornește singur la final.") + "\n" + _(
		"Receptorul are o singură pereche de nucleu și sistem în memoria internă (fără multiboot): dacă noul "
		"software nu pornește, singura reparare este Maintenance Mode, de mână. Înainte de scriere, setările "
		"și lista de canale se copiază pe stick.") + "\n" + _("Scrii acum software-ul pe receptor?") + "\n\n" + tehnic


def _descriereCandidat(c):
	"""Randul pachetului in lista: verdictul pazei (refuzurile incep cu „nu se scrie”), numele, versiunea si mediul;
	ce e mai putin important sta la dreapta, unde randul se poate taia."""
	sursa = c["disc"].description or c["disc"].mountpoint
	parti = _numeSiVersiune(c) + [sursa]
	if c.get("paza"):
		parti.insert(0, HdsPazaModel.scurtRefuz(c["paza"][0]))
	return "  ·  ".join(parti)


def _spatiuSuficient(mountpoint, octeti_necesari):
	try:
		st = os.statvfs(mountpoint)
		return (st.f_bavail * st.f_frsize) >= octeti_necesari
	except OSError:
		return True  # nu blocam daca nu putem verifica (mai bine incearca si esueaza clar)


def _copiaza(sursa, dest, oprit=None):
	"""Copiere in bucati de 1 MiB; `oprit()` adevarat (ecranul s-a inchis) opreste copierea."""
	while True:
		if oprit is not None and oprit():
			raise OSError("copierea a fost oprita")
		bucata = sursa.read(BLOC_COPIE)
		if not bucata:
			return
		dest.write(bucata)


def _extrageZip(candidat, tinta, oprit=None):
	"""Scoate din zip-ul candidat numai cele patru fisiere ale pachetului (NUME_PACHET) in dosarul `tinta`. Ridica
	OSError/KeyError/zipfile.BadZipFile la orice problema; apelantul le arata."""
	radacina = candidat["radacina_in_zip"]
	with zipfile.ZipFile(candidat["cale_zip"]) as z:
		originale = {}
		for n in z.namelist():
			originale.setdefault(n.replace("\\", "/"), n)
		for nume_scurt in NUME_PACHET:
			nume_in_zip = originale.get(radacina + nume_scurt)
			if nume_in_zip is not None:
				with z.open(nume_in_zip) as sursa, open(os.path.join(tinta, nume_scurt), "wb") as dest:
					_copiaza(sursa, dest, oprit)


def _copiazaDosar(candidat, tinta, oprit=None):
	"""Copiaza din dosarul e2/update de pe stick numai cele patru fisiere ale pachetului (NUME_PACHET) in `tinta`."""
	for nume_scurt in NUME_PACHET:
		sursa_cale = os.path.join(candidat["cale_update"], nume_scurt)
		if os.path.isfile(sursa_cale):
			with open(sursa_cale, "rb") as sursa, open(os.path.join(tinta, nume_scurt), "wb") as dest:
				_copiaza(sursa, dest, oprit)


def _pregatesteDosarCurat(candidat, oprit=None):
	"""Dosarul curat al pachetului, pe acelasi mediu: <mediu>/.hds-actualizare-extrasa/e2/update, golit si umplut numai
	cu fisierele pachetului (din zip sau din dosarul e2/update). Ruleaza pe un fir separat. Intoarce calea dosarului."""
	tinta = os.path.join(candidat["disc"].mountpoint, FOLDER_DEZARHIVARE, *SUBCALE_UPDATE)
	if os.path.isdir(tinta):
		shutil.rmtree(tinta, ignore_errors=True)
	os.makedirs(tinta, exist_ok=True)
	if candidat["tip"] == "zip":
		_extrageZip(candidat, tinta, oprit)
	else:
		_copiazaDosar(candidat, tinta, oprit)
	return tinta


def _marimePachet(candidat):
	"""Octetii de copiat in dosarul curat (zip-ul intreg, sau fisierele pachetului din dosar)."""
	if candidat["tip"] == "zip":
		return os.path.getsize(candidat["cale_zip"])
	total = 0
	for nume_scurt in NUME_PACHET:
		cale = os.path.join(candidat["cale_update"], nume_scurt)
		if os.path.isfile(cale):
			total += os.path.getsize(cale)
	return total


def _fisiereGasiteDeOfgwrite(iesire):
	"""(nuclee, sisteme): caile anuntate de ofgwrite la „Found kernel file:” si la fisierele de sistem („Found rootfs
	file:”, „Found tar.xz rootfs file:”, „Found nfi file:”), in ordinea din iesire (ofgwrite.c, find_image_files)."""
	nuclee, sisteme = [], []
	for rand in (iesire or "").splitlines():
		rand = rand.strip()
		for inceput, lista in (("Found kernel file: ", nuclee), ("Found rootfs file: ", sisteme),
				("Found tar.xz rootfs file: ", sisteme), ("Found nfi file: ", sisteme)):
			if rand.startswith(inceput):
				lista.append(rand[len(inceput):].strip())
	return nuclee, sisteme


def _ofgwriteAGasitPachetul(iesire, dosar):
	"""True numai daca simularea a gasit exact un nucleu si un sistem, adica kernel.bin si rootfs.tar.bz2 din `dosar`
	(ofgwrite scrie calea dupa realpath)."""
	nuclee, sisteme = _fisiereGasiteDeOfgwrite(iesire)
	if len(nuclee) != 1 or len(sisteme) != 1:
		return False
	try:
		baza = os.path.realpath(dosar)
	except (OSError, ValueError):
		baza = dosar
	return os.path.normpath(nuclee[0]) == os.path.normpath(os.path.join(baza, NUME_KERNEL)) and \
		os.path.normpath(sisteme[0]) == os.path.normpath(os.path.join(baza, NUME_ROOTFS))


def _simulareAratacorect(iesire):
	"""Verificare PROPRIE, din text, ca ofgwrite a recunoscut pachetul — NU se are incredere in
	textul lui de "succes" (identic la simulare si la scriere reala). Cere gasirea
	explicita a kernelului, rootfs-ului SI a dispozitivelor tinta, fara nicio mentiune de eroare."""
	txt = (iesire or "").lower()
	are_kernel = "found kernel file" in txt
	are_rootfs = any(s in txt for s in (
		"found rootfs file", "found ext4 rootfs", "found ext3 rootfs", "found ubi rootfs", "found ubifs rootfs"
	))
	are_dispozitive = "found cmdline kernel device" in txt and "found cmdline rootfs device" in txt
	are_eroare = ("error" in txt) or ("not found" in txt) or ("missing" in txt) or ("no such file" in txt)
	return bool(are_kernel and are_rootfs and are_dispozitive and not are_eroare)


def skinActualizare(latime, inaltime):
	"""Skinul ecranului, socotit la deschidere pentru `latime` x `inaltime` (asezarea e gandita pe 1920x1080: fereastra
	1500x820, litere de 28). Niciun skin nu are un bloc HdsSoftwareUpdate, deci acesta e folosit in orice skin."""
	def x(v):
		return int(round(v * latime / 1920.0))

	def y(v):
		return int(round(v * inaltime / 1080.0))
	valori = {"fl": x(1500), "fh": y(820), "m": x(30), "cl": x(1440), "dy": y(20), "dh": y(140), "ly": y(170),
		"lh": y(560), "f": y(28), "ih": y(56), "fc": y(20), "by": y(755), "bl": x(360), "bh": y(50), "bf": y(26),
		"b2": x(410), "b3": x(790)}
	return """
	<screen name="HdsSoftwareUpdate" position="center,center" size="%(fl)d,%(fh)d" title="Imagine nouă de pe stick">
		<widget name="detaliu" position="%(m)d,%(dy)d" size="%(cl)d,%(dh)d" font="Regular;%(f)d" />
		<widget name="lista" position="%(m)d,%(ly)d" size="%(cl)d,%(lh)d" font="Regular;%(f)d" itemHeight="%(ih)d" scrollbarMode="showOnDemand" />
		<widget name="iesire" position="%(m)d,%(ly)d" size="%(cl)d,%(lh)d" font="Console;%(fc)d" scrollbarMode="showOnDemand" />
		<widget name="key_red" position="%(m)d,%(by)d" size="%(bl)d,%(bh)d" zPosition="1" font="Regular;%(bf)d" halign="center" valign="center" backgroundColor="#9f1313" transparent="0" />
		<widget name="key_green" position="%(b2)d,%(by)d" size="%(bl)d,%(bh)d" zPosition="1" font="Regular;%(bf)d" halign="center" valign="center" backgroundColor="#1f771f" transparent="0" />
		<widget name="key_yellow" position="%(b3)d,%(by)d" size="%(bl)d,%(bh)d" zPosition="1" font="Regular;%(bf)d" halign="center" valign="center" backgroundColor="#a08000" transparent="0" />
	</screen>
	""" % valori


class HdsSoftwareUpdate(Screen):

	def __init__(self, session):
		try:
			from enigma import getDesktop
			marime = getDesktop(0).size()
			self.skin = skinActualizare(marime.width(), marime.height())
		except Exception:
			self.skin = skinActualizare(1920, 1080)
		Screen.__init__(self, session)
		self.setTitle(_("Imagine nouă de pe stick"))
		self._console = Console()
		self._candidati = []
		self._candidatAles = None
		self._ultimaIesire = ""
		self._arataCorect = False
		self._ocupat = False
		self._scriereRealaPornita = False
		self._faza = "cautare"
		# paza de model: lucrarea de pe firul separat (dosarul curat, apoi sumele) si semnul fisierelor (marime, ora)
		# luat cand sumele au iesit bune
		self._lucrare = None
		self._opreste = False
		self._semnVerificat = None
		self.onClose.append(self._laInchidere)

		self["detaliu"] = Label(_("Se caută pachete de actualizare pe mediile montate (USB/HDD)…"))
		self["lista"] = MenuList([])
		self["iesire"] = ScrollLabel("")
		self["iesire"].hide()
		self["key_red"] = Button(_("Înapoi"))
		self["key_green"] = Button("")
		self["key_yellow"] = Button(_("Reîncarcă"))

		self["actiuni"] = ActionMap(
			["OkCancelActions", "ColorActions", "DirectionActions"],
			{
				"cancel": self._inapoi,
				"red": self._inapoi,
				"ok": self._ok,
				"green": self._ok,
				"yellow": self._reincarca,
				"up": self._sus,
				"down": self._jos,
			}, -2)

		self.onLayoutFinish.append(self._reincarca)
		getattr(self, "onLayoutFinish", []).append(self._cozileDetaliului)

	def _cozileDetaliului(self):
		"""Textul marit (Marimea textului peste 100 %, Components/HdsMarireText): detaliul de sus are loc si pentru cozile
		ultimului rand, din cei 10 px liberi de sub el (la 125 % se taiau). La 100 % nu se schimba nimic."""
		try:
			from Components import HdsMarireText as MT
			from enigma import getDesktop
			MT.locPentruCozi(self["detaliu"].instance, max(1, 10 * getDesktop(0).size().height() // 1080))
		except Exception as e:
			print("[HdsSoftwareUpdate] textul marit: %s" % e)

	# -------------------------------------------------------------- navigare in lista

	def _sus(self):
		if not self._ocupat and self._faza == "lista":
			self["lista"].up()
		elif self._faza in ("verificare", "rezultat"):
			# HDSatelit: iesirea simularii poate fi mai lunga decat caseta ei
			self["iesire"].pageUp()

	def _jos(self):
		if not self._ocupat and self._faza == "lista":
			self["lista"].down()
		elif self._faza in ("verificare", "rezultat"):
			self["iesire"].pageDown()

	def _inapoi(self):
		"""Inapoi / EXIT. In timpul copierii in dosarul curat si al sumelor (fir separat) inchide ecranul: _laInchidere
		opreste firul la urmatoarea bucata. Numai in timpul simularii (ofgwrite -n) ecranul asteapta."""
		if self._ocupat and self._faza == "verificare":
			return
		self._console.killAll()
		self.close()

	def _laInchidere(self):
		self._opreste = True
		if self._lucrare is not None:
			self._lucrare.opreste()
			self._lucrare = None

	def _oprit(self):
		return self._opreste

	def _buton(self, nume, text):
		"""Textul unei taste colorate; fara text tasta nu se arata (altfel ramane o caseta colorata goala)."""
		self[nume].setText(text)
		if text:
			self[nume].show()
		else:
			self[nume].hide()

	def _marcheazaRefuzat(self, cod, text):
		"""Randul pachetului ales spune de acum refuzul aflat abia dupa OK (suma rea, fisiere schimbate)."""
		c = self._candidatAles
		if c is None or not any(x is c for x in self._candidati):
			return
		c["paza"] = (cod, text)
		index = self["lista"].getSelectionIndex()
		self["lista"].setList([_descriereCandidat(x) for x in self._candidati] + [_("Caută din nou pachetele")])
		self["lista"].moveToIndex(index)

	# -------------------------------------------------------------- faza 1: cautare

	def _reincarca(self):
		"""Lista pachetelor; ultimul rand, „Caută din nou pachetele”, reface lista cu OK (ca tasta galbena)."""
		if self._ocupat:
			return
		self._faza = "lista"
		self["iesire"].hide()
		self["lista"].show()
		self["detaliu"].setText(_("Se caută pachete de actualizare pe mediile montate (USB/HDD)…"))
		eroare_cautare = None
		try:
			self._candidati = cautaCandidati()
		except Exception as eroare:
			self._candidati = []
			eroare_cautare = eroare
		cauta_din_nou = _("Caută din nou pachetele")
		if self._candidati:
			randuri = [_descriereCandidat(c) for c in self._candidati]
			self["lista"].setList(randuri + [cauta_din_nou])
			self["detaliu"].setText(
				_("Pachete găsite: %d. Alege unul și apasă OK ca să fie verificat.") % len(self._candidati)
			)
			self._buton("key_green", _("Verifică pachetul"))
		else:
			self["lista"].setList([_("Niciun pachet găsit pe mediile montate acum."), cauta_din_nou])
			if eroare_cautare is not None:
				self["detaliu"].setText(_("Eroare la căutare: %s") % eroare_cautare)
			else:
				self["detaliu"].setText(
					_("Conectează un stick cu pachetul de actualizare (dosarul e2/update cu kernel.bin și "
					  "rootfs.tar.bz2, sau o arhivă .zip cu aceeași structură), apoi apasă OK pe „Caută din nou "
					  "pachetele”.")
				)
			self._buton("key_green", "")
		self._buton("key_yellow", _("Reîncarcă"))

	def _candidatSelectat(self):
		index = self["lista"].getSelectionIndex()
		if self._candidati and 0 <= index < len(self._candidati):
			return self._candidati[index]
		return None

	# -------------------------------------------------------------- faza 2: alegere + confirmare 1

	def _intreaba(self, callback, text, titlu, da, implicit_da, randuri):
		"""O intrebare cu „Da” / „Nu” in fereastra ei (Screens/HdsPazaModel.HdsPazaModelIntrebare)."""
		from Screens.HdsPazaModel import HdsPazaModelIntrebare
		self.session.openWithCallback(callback, HdsPazaModelIntrebare, text, titlu, da=da, implicit_da=implicit_da,
			randuri_mesaj=randuri[0], randuri_tehnic=randuri[1])

	def _ok(self):
		if self._ocupat:
			return
		if self._faza == "lista":
			candidat = self._candidatSelectat()
			if candidat is None:
				# „Caută din nou pachetele” (sau randul „Niciun pachet găsit”)
				self._reincarca()
				return
			self._semnVerificat = None
			cod, text = candidat.get("paza") or pazaPachet(candidat)
			if cod != HdsPazaModel.PACHET_BUN:
				self._refuzPaza(text, cod)
				return
			self._candidatAles = candidat
			self._intreaba(self._dupaConfirmareVerificare, textVerificare(candidat), _("Verificarea pachetului"),
				_("Da, verifică pachetul"), True, RANDURI_VERIFICARE)
		elif self._faza == "rezultat" and self._arataCorect and not self._scriereRealaPornita:
			self._intreabaFlashReal()

	def _dupaConfirmareVerificare(self, raspuns):
		if not raspuns or self._candidatAles is None:
			return
		self._pregatesteSiVerifica()

	def _refuzMediu(self, cale):
		"""None daca fisierele stau pe un stick USB (sau in RAM); altfel arata refuzul in fereastra refuzurilor si
		intoarce textul scurt al refuzului. ofgwrite nu porneste niciodata dupa un refuz."""
		permis, motiv, dispozitiv, punct = verificaMediuScriere(cale)
		if permis:
			return None
		if dispozitiv:
			unde = _("%s, montat pe %s") % (dispozitiv, punct)
		else:
			unde = cale
		if motiv == REFUZ_INTERN:
			scurt = _("Scrierea este oprită: fișierele imaginii stau pe memoria internă a receptorului (%s).") % unde
		elif motiv == REFUZ_LIPSA:
			scurt = _("Scrierea este oprită: nu am putut verifica unde stau fișierele imaginii (%s).") % unde
		else:
			scurt = _("Scrierea este oprită: fișierele imaginii nu stau pe un stick USB (%s).") % unde
		# fereastra de mesaj a skinului are loc pentru trei randuri; textul intreg merge in fereastra refuzurilor
		explicatie = _(
			"Imaginea trebuie să fie pe un stick USB. Din memoria internă nu se scrie niciodată: "
			"scrierea ar șterge chiar fișierele pe care le citește și receptorul nu ar mai porni.\n\n"
			"Copiază pachetul (kernel.bin, rootfs.tar.bz2, imageversion) pe un stick USB, "
			"introdu stickul și încearcă din nou. Nu s-a scris nimic."
		)
		from Screens.HdsPazaModel import HdsPazaModelRefuz
		self.session.open(HdsPazaModelRefuz, scurt + "\n" + explicatie.replace("\n\n", "\n"),
			_("Scrierea este oprită"))
		return scurt

	def _pregatesteSiVerifica(self):
		"""Dosarul curat al pachetului, pe un fir separat, apoi sumele si simularea."""
		candidat = self._candidatAles
		refuz = self._refuzMediu(candidat["disc"].mountpoint)
		if refuz:
			self._eroareInapoiLaLista(refuz)
			return
		try:
			marime = _marimePachet(candidat)
		except OSError as eroare:
			self._eroareInapoiLaLista(_("Nu am putut dezarhiva pachetul: %s") % eroare)
			return
		if not _spatiuSuficient(candidat["disc"].mountpoint, marime):
			self._eroareInapoiLaLista(_("Spațiu insuficient pe %s pentru dezarhivare.") % candidat["disc"].mountpoint)
			return
		self._ocupat = True
		self._opreste = False
		self["detaliu"].setText(_("Se copiază pachetul într-un dosar curat pe stick. Durează până la un minut."))
		self._buton("key_green", "")
		self._buton("key_yellow", "")
		self._lucrare = HdsPazaModel.LucrareFundal(
			lambda: _pregatesteDosarCurat(candidat, oprit=self._oprit),
			lambda cale, eroare: self._dosarGata(candidat, cale, eroare))

	def _dosarGata(self, candidat, cale, eroare):
		self._lucrare = None
		self._ocupat = False
		if eroare or not cale:
			self._eroareInapoiLaLista(_("Nu am putut dezarhiva pachetul: %s") % (eroare or "?"))
			return
		candidat["cale_finala"] = cale
		self._pornesteSumele(cale)

	# -------------------------------------------------------------- paza de model (Components/HdsPazaModel.py)

	def _refuzPaza(self, text, cod=None):
		"""Refuzul pazei: sus o fraza scurta care spune ca nu se scrie, textul intreg in fereastra refuzului (fereastra
		de mesaj a skinului are loc numai pentru trei randuri). Nimic nu porneste dupa el."""
		if cod is not None:
			sus = HdsPazaModel.randSusRefuz(cod)
		else:
			sus = text.split("\n")[0]
			nimic = _("Nu s-a scris nimic pe receptor.")
			if nimic not in sus:
				sus = "%s %s" % (sus, nimic)
		self._eroareInapoiLaLista(sus)
		self._arataRefuzPaza(text)

	def _arataRefuzPaza(self, text):
		from Screens.HdsPazaModel import HdsPazaModelRefuz
		self.session.open(HdsPazaModelRefuz, text)

	def _pornesteSumele(self, cale):
		"""Marcajul din dosarul pachetului fata de receptor (repede), apoi sumele SHA-256 pe un fir separat; simularea
		porneste numai dupa ce sumele ies bune."""
		cod, text, marcaj = HdsPazaModel.verificaPachet(_textMarcaj(os.path.join(cale, NUME_MARCAJ)))
		if cod != HdsPazaModel.PACHET_BUN:
			self._refuzPaza(text, cod)
			return
		self._ocupat = True
		self._opreste = False
		self["detaliu"].setText(_("Se verifică dacă pachetul este întreg (sumele de control). Durează câteva secunde."))
		self._buton("key_green", "")
		self._buton("key_yellow", "")
		semn = HdsPazaModel.semnFisiere(cale)
		self._lucrare = HdsPazaModel.LucrareFundal(
			lambda: HdsPazaModel.sumeSha256(cale, oprit=self._oprit),
			lambda sume, eroare: self._sumeGata(cale, marcaj, semn, sume, eroare))

	def _sumeGata(self, cale, marcaj, semn, sume, eroare):
		self._lucrare = None
		self._ocupat = False
		if eroare or sume is None:
			self._refuzPaza(_("Pachetul nu s-a putut citi de pe stick (%s).") % (eroare or "?") + "\n" +
				_("Nu s-a scris nimic pe receptor."))
			return
		gresite = HdsPazaModel.sumeGresite(marcaj, sume)
		if gresite:
			text = HdsPazaModel.textRefuz(HdsPazaModel.REFUZ_SUMA, fisier=gresite)
			self._marcheazaRefuzat(HdsPazaModel.REFUZ_SUMA, text)
			self._refuzPaza(text, HdsPazaModel.REFUZ_SUMA)
			return
		if HdsPazaModel.semnFisiere(cale) != semn:
			text = HdsPazaModel.textRefuz(HdsPazaModel.REFUZ_SCHIMBAT)
			self._marcheazaRefuzat(HdsPazaModel.REFUZ_SCHIMBAT, text)
			self._refuzPaza(text, HdsPazaModel.REFUZ_SCHIMBAT)
			return
		self._semnVerificat = (cale, semn)
		self._porneesteVerificare(cale)

	def _refuzPazaInainteDeScriere(self, cale):
		"""Pe firul enigma2, chiar inainte de copie si de init 4: marcajul, amprenta si fisierele neschimbate de la
		sume. Intoarce textul refuzului (si il arata), sau None."""
		cod, text, _marcaj = HdsPazaModel.verificaPachet(_textMarcaj(os.path.join(cale, NUME_MARCAJ)))
		if cod == HdsPazaModel.PACHET_BUN and (not self._semnVerificat or self._semnVerificat[0] != cale or
				HdsPazaModel.semnFisiere(cale) != self._semnVerificat[1]):
			text = HdsPazaModel.textRefuz(HdsPazaModel.REFUZ_SCHIMBAT)
			cod = HdsPazaModel.REFUZ_SCHIMBAT
		if cod == HdsPazaModel.PACHET_BUN:
			return None
		self._arataRefuzPaza(text)
		return text.split("\n")[0]

	def _eroareInapoiLaLista(self, mesaj):
		"""Inapoi in lista, cu `mesaj` sus; tasta verde si cea galbena revin (lista e aceeasi)."""
		self._faza = "lista"
		self["iesire"].hide()
		self["lista"].show()
		self["detaliu"].setText(mesaj)
		self._buton("key_green", _("Verifică pachetul") if self._candidati else "")
		self._buton("key_yellow", _("Reîncarcă"))

	def _blocheazaScrierea(self, mesaj):
		self._arataCorect = False
		self["detaliu"].setText(mesaj)
		self._buton("key_green", "")

	# -------------------------------------------------------------- faza 3: verificare (ofgwrite -n)

	def _porneesteVerificare(self, cale_pachet):
		refuz = self._refuzMediu(cale_pachet)
		if refuz:
			self._eroareInapoiLaLista(refuz)
			return
		self._faza = "verificare"
		self._ocupat = True
		self["lista"].hide()
		self["iesire"].show()
		self["iesire"].setText(_("Se face simularea scrierii (ofgwrite -n): nu se scrie nimic…"))
		self["detaliu"].setText(_("Așteaptă câteva secunde și nu opri receptorul."))
		self._buton("key_green", "")
		self._buton("key_yellow", "")
		comanda = "%s -n -r -k %s" % (CALE_OFGWRITE, shlex.quote(cale_pachet))
		self._console.ePopen(comanda, self._verificareGata)

	def _verificareGata(self, iesire, retval, extra_args=None):
		self._ocupat = False
		self._faza = "rezultat"
		self._ultimaIesire = iesire or _("(fără nicio ieșire de la ofgwrite)")
		cale = (self._candidatAles or {}).get("cale_finala") or ""
		self._arataCorect = _simulareAratacorect(self._ultimaIesire) and _ofgwriteAGasitPachetul(self._ultimaIesire, cale)
		self._buton("key_yellow", _("Reîncarcă"))
		self["iesire"].setText(
			(_("Cod de ieșire: %d\n\n") % retval) +
			self._ultimaIesire +
			_("\n\n(Simulare: nu s-a scris nimic pe receptor, orice ar spune textul de mai sus; ofgwrite scrie "
			  "„Successfully flashed” și la simulare.)")
		)
		if self._arataCorect:
			self["detaliu"].setText(_("Pachetul a fost recunoscut corect: nucleul, sistemul și partițiile lor au fost "
				"găsite. Apasă OK sau Verde ca să îl scrii pe receptor."))
			self._buton("key_green", _("Scrie pe receptor"))
		else:
			self["detaliu"].setText(_("Pachetul nu a fost recunoscut corect de ofgwrite, deci nu se scrie. Mesajele "
				"programului sunt mai jos."))
			self._buton("key_green", "")

	# -------------------------------------------------------------- faza 4: confirmare 2 + scriere reala

	def _intreabaFlashReal(self):
		"""Ultima confirmare, in fereastra intrebarilor, cu „Nu” ales: textul simplu sus, dosarul pentru Maintenance
		Mode si pachetul mai mic, dedesubt."""
		inregistrare = False
		try:
			inregistrare = bool(self.session.nav.getRecordings())
		except Exception:
			pass
		self._intreaba(self._dupaConfirmareFlashReal,
			textUltimaConfirmare(self._candidatAles, inregistrare, self._textRecuperare()),
			_("Ultima confirmare"), _("Da, scrie acum"), False, RANDURI_CONFIRMARE)

	def _textRecuperare(self):
		"""Fraza cu dosarul de pe stick in care cauta Maintenance Mode, calculat ca showiframe
		(Components/HdsRecuperare.py, fara citirea memoriei interne). Goala in emulator sau daca ceva cade:
		confirmarea nu se opreste niciodata din cauza ei."""
		try:
			from Components import HdsRecuperare
			if not HdsRecuperare.seAplica():
				return ""
			return HdsRecuperare.textConfirmare(HdsRecuperare.calculeaza()) + "\n\n"
		except Exception:
			return ""

	def _dupaConfirmareFlashReal(self, raspuns):
		if not raspuns or self._candidatAles is None or self._scriereRealaPornita:
			return
		cale_pachet = self._candidatAles["cale_finala"]
		refuz = self._refuzMediu(cale_pachet) or self._refuzPazaInainteDeScriere(cale_pachet)
		if refuz:
			self._blocheazaScrierea(refuz)
			return
		self._scriereRealaPornita = True  # o singura scriere reala per deschidere a ecranului

		mountpoint = self._candidatAles["disc"].mountpoint
		_bazaCanalelor("copie")
		folder_backup, fisiere_copiate, eroare_backup = _creeazaBackupSetari(mountpoint)
		if eroare_backup:
			# copie cazuta: scrierea asteapta raspunsul omului; implicit „Nu”
			self.session.openWithCallback(
				self._dupaIntrebareFaraCopie,
				MessageBox,
				_("Copia de siguranță nu s-a putut face (%s).\n\n"
				  "Continui fără copie? Lista de canale, setările și datele canalelor se pierd la scriere.") % eroare_backup,
				MessageBox.TYPE_YESNO, default=False
			)
			return
		if fisiere_copiate:
			mesaj_backup = _("Setări/canale copiate în %s (%d fișiere).") % (folder_backup, len(fisiere_copiate))
		else:
			mesaj_backup = _("Niciun fișier de setări/canale găsit de copiat (receptor neconfigurat încă); nimic de pierdut.")
		self._pornesteScrierea(cale_pachet, mountpoint, mesaj_backup)

	def _dupaIntrebareFaraCopie(self, raspuns):
		"""Raspunsul la „Continui fara copie?”. „Nu” (sau inchiderea intrebarii) = nimic pornit; butonul verde ramane,
		ca scrierea sa se poata cere din nou dupa ce stickul e reparat."""
		if not raspuns or self._candidatAles is None:
			self._scriereRealaPornita = False
			self["detaliu"].setText(_("Scrierea nu a pornit, pentru că nu există copie de siguranță. Nu s-a scris nimic "
				"pe receptor. Verifică stickul, apoi apasă din nou Verde."))
			return
		self._pornesteScrierea(self._candidatAles["cale_finala"], self._candidatAles["disc"].mountpoint,
			_("Scrierea continuă fără copie de siguranță, cum ai ales."))

	def _pornesteScrierea(self, cale_pachet, mountpoint, mesaj_backup):
		cale_jurnal = os.path.join(mountpoint, "hds-actualizare-jurnal.txt")
		_hdsAfisajActualizare(True)
		refuz = self._porneesteFlashReal(cale_pachet, cale_jurnal)
		if refuz:
			_hdsAfisajActualizare(False)
			self._scriereRealaPornita = False
			self._blocheazaScrierea(refuz)
			return
		self["detaliu"].setText(
			mesaj_backup + "\n" +
			_("Scrierea a pornit (interfața se poate opri oricând, e normal). Jurnal: %s") % cale_jurnal
		)
		self._buton("key_green", "")

	def _porneesteFlashReal(self, cale_pachet, cale_jurnal):
		"""Comanda reala, DETASATA de acest proces: "init 4" opreste Enigma2 (deci si acest
		ecran) inainte ca ofgwrite sa apuce sa scrie — procedura probata. Nu se
		poate astepta sincron un callback dintr-un proces care urmeaza sa fie omorat; de-aici
		os.system() cu "&" (proces copil independent, care supravietuieste mortii parintelui),
		nu Console/ePopen (legat de bucla de evenimente a acestui proces Enigma2).
		Intoarce None daca a pornit, sau textul refuzului daca paznicul a oprit scrierea."""
		refuz = self._refuzMediu(cale_pachet) or self._refuzPazaInainteDeScriere(cale_pachet)
		if refuz:
			return refuz
		_bazaCanalelor("flash")
		comanda = (
			"{ echo '[hds] init 4 (opresc Enigma2 ca sa nu concureze cu scrierea)'; "
			"init 4; "
			"sleep 3; "
			"echo '[hds] pornesc scrierea reala'; "
			"%s -r -k %s; "
			"echo \"[hds] ofgwrite s-a intors, cod: $?\"; "
			"} > %s 2>&1 &"
		) % (CALE_OFGWRITE, shlex.quote(cale_pachet), shlex.quote(cale_jurnal))
		os.system(comanda)
		return None
