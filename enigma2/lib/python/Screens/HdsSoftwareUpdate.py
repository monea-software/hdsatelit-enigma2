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
# normala, sincrona, in acest proces: e pornita ca o comanda shell DETASATA, in sesiune noua,
# care supravietuieste mortii Enigma2 (init opreste tot grupul de procese al lui enigma2.sh).
# Iesirea ei se scrie intr-un fisier jurnal PE ACELASI MEDIU montat (nu in /tmp, care
# poate sa nu supravietuiasca unei scrieri reale a radacinii), pentru control ulterior.
#
# TESTARE: intai emulator (ruleaza.sh) — tot fluxul (cautare, lista, confirmare, simulare,
# citirea iesirii), fara nicio scriere reala posibila acolo (binarul ofgwrite nu exista in
# containerul x86 al emulatorului — comportament asteptat, tratat clar in interfata, nu crash).
# Probele pe receptorul fizic se fac STRICT cu simularea ("-n"), niciodata cu scrierea reala.

# PAZNIC: inainte de dezarhivare si inainte de fiecare ofgwrite se verifica, cu
# Tools/MediuImagine.py, ca fisierele stau pe un stick USB (sau in RAM). O data, un ofgwrite -r cu
# imaginea in /root (pe mmcblk0p10, chiar radacina rescrisa) a lasat receptorul fara sistem.
# Tot acolo, numele stickului (MediuImagine.pregatesteNumeStick): ofgwrite fara peticul ghilimelelor goleste radacina
# cand punctul de montare al stickului are spatii; montarea se muta singura intr-un dosar fara spatii, fara nicio
# intrebare. Numai daca mutarea nu merge, pachetul nu se scrie si omul afla ce nume sa-i dea stickului.
#
# Stickul pus de nucleu pe numai citire dupa o eroare: dosarul curat nu se poate face pe el, dar arhiva se citeste. Cu cei mai putini
# pasi pentru om: intai alt disc USB pe care paznicul de mai sus il primeste, pe care se poate scrie si care are loc (dosarul curat,
# copia setarilor si jurnalul merg acolo, fara nicio intrebare). Discul de pe care ruleaza imaginea (primul Viper 4K pornit de pe un
# disc extern) nu intra: e chiar dispozitivul radacinii, pe care ofgwrite il rescrie, iar paznicul il refuza. Fara alt disc: un rand
# „Repară” primul in lista, cu aceeasi lucrare ca in Screens/HdsLocInregistrari.py, un singur OK, apoi lista se citeste din nou.

import glob
import os
import re
import shlex
import shutil
import subprocess
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
from Tools.MediuImagine import verificaMediuScriere, pregatesteNumeStick, versiuneUsb, REFUZ_INTERN, REFUZ_LIPSA, REFUZ_SPATII
from Components import HdsPazaModel


_proprietarActualizare = None
_rezervareOnline = None
_eliberariActualizare = []  # Screen.doClose goleste __dict__; ceasul trebuie sa traiasca si dupa inchiderea TV


def rezervaActualizarea(proprietar):
	"""O singura verificare/instalare de pe stick, din TV sau web, pe firul enigma2.
	Starea ocupata existenta opreste si pornirea unei imagini de pe internet."""
	global _proprietarActualizare, _rezervareOnline
	if _proprietarActualizare is proprietar:
		return True
	if _proprietarActualizare is not None:
		return False
	from Components.HdsImagineOnline import imagine_online
	if imagine_online.ocupat():
		return False
	_rezervareOnline = (imagine_online, imagine_online.faza, imagine_online.pas, imagine_online.mesaj)
	imagine_online.faza = "stick"
	imagine_online.pas = _("Este în curs o verificare sau o instalare de pe stick. Termină ori renunță la ea înainte de altă actualizare.")
	_proprietarActualizare = proprietar
	return True


def elibereazaActualizarea(proprietar):
	global _proprietarActualizare, _rezervareOnline
	if _proprietarActualizare is not proprietar:
		return
	if _rezervareOnline is not None:
		i, faza, pas, mesaj = _rezervareOnline
		if i.faza == "stick":
			i.faza, i.pas, i.mesaj = faza, pas, mesaj
	_proprietarActualizare = _rezervareOnline = None


def textActualizareOcupata():
	return _("Este în curs altă verificare sau instalare. Termină ori renunță la ea, apoi încearcă din nou.")


def elibereazaDupaLucrare(proprietar, lucrare):
	"""Un fir anulat poate inca inchide ultimul fisier; urmatoarea verificare asteapta sfarsitul lui."""
	if _proprietarActualizare is not proprietar:
		return

	def elibereaza():
		elibereazaActualizarea(proprietar)
		callback = getattr(proprietar, "_actualizareEliberata", None)
		if callback is not None:
			callback()

	if lucrare is None or getattr(lucrare, "_rez", {}).get("gata"):
		elibereaza()
		return
	from enigma import eTimer
	ceas = eTimer()

	def gata():
		if lucrare._rez.get("gata"):
			ceas.stop()
			if pastrata in _eliberariActualizare:
				_eliberariActualizare.remove(pastrata)
			proprietar._eliberareActualizare = None
			elibereaza()

	try:
		legatura = ceas.timeout.connect(gata)
	except AttributeError:
		ceas.callback.append(gata)
		legatura = None
	pastrata = (ceas, legatura)
	_eliberariActualizare.append(pastrata)
	proprietar._eliberareActualizare = pastrata
	ceas.start(100, False)


NUME_KERNEL = "kernel.bin"
NUME_KERNEL_VUPLUS = HdsPazaModel.NUME_NUCLEU_VUPLUS  # arhivele Vu+ 4K (vuplus/<model>/), vezi _radacinaPachet
NUME_ROOTFS = "rootfs.tar.bz2"
NUME_VERSIUNE = "imageversion"
NUME_MARCAJ = HdsPazaModel.NUME_MARCAJ  # semnul receptorului pentru care e pachetul
SUBCALE_UPDATE = ("e2", "update")  # structura standard
# arhivele .zip se cauta in radacina discului si in aceste dosare, ca la celelalte imagini OE-Alliance (dosareArhive)
DOSARE_ARHIVE = ("images", "downloaded_images", "imagebackups")
FOLDER_DEZARHIVARE = ".hds-actualizare-extrasa"  # dosarul curat, pe acelasi mediu
NUME_PACHET = (NUME_KERNEL, NUME_ROOTFS, NUME_VERSIUNE, NUME_MARCAJ)
BLOC_COPIE = 1024 * 1024
BLOC_SINCRONIZARE = 8 * 1024 * 1024  # fsync la atatia octeti scrisi in dosarul curat (vezi _copiaza)
# simularea (ofgwrite -n) ia de obicei 10-20 s; peste atat se opreste singura, cu mesaj (nu scrie nimic, deci se poate opri)
LIMITA_SIMULARE_S = 120
CALE_OFGWRITE = "/usr/bin/ofgwrite"
CALE_CMDLINE = "/proc/cmdline"
CALE_ENIGMA2_ETC = "/etc/enigma2"
PREFIX_FOLDER_BACKUP = "hds-backup-setari-"

# V20 are o singura pereche nucleu + sistem pe eMMC (p9, p10).
# La pornirea multipla cu linuxrootfsN folosim -mN si verificam destinatiile
# fata de kernel= si root=. Fara -m, cautarea GPT poate pierde nucleul.
# Un subdosar gol ar insemna stergerea intregii partitii userdata.
# Se scrie numai slotul pornit din memorie, dupa proba aceluiasi pachet.
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


def _copieCompleta(mountpoint):
	"""Copia setarilor (Components/HdsCopieSetari) chiar inainte de instalare, ca la imaginea online: prima pornire a imaginii noi
	pune ultima copie de pe stick. Fara ea ar pune una mai veche si s-ar pierde ce a adaugat omul de atunci (conturile de televiziune
	prin internet, Favoritele, setarile pluginurilor). Intoarce None sau textul erorii."""
	try:
		from Components import HdsCopieSetari
		# 0.7.4: pluginurile puse din fisiere, care nu sunt in feeduri, intra in copie cu pachetul lor refacut, ca la imaginea
		# online; numai cand modulul copiei stie parametrul (HdsCopieSetari.FA_COPIA_REFACE_PACHETE)
		kw = {"reface_pachete": True} if getattr(HdsCopieSetari, "FA_COPIA_REFACE_PACHETE", False) else {}
		rez = HdsCopieSetari.fa_copia(mountpoint, HdsCopieSetari.text_setari_acum(), fel="automata", **kw)
	except Exception as eroare:
		return str(eroare) or eroare.__class__.__name__
	if rez.get("ok") and rez.get("cale"):
		# cu regulile punerii la loc (ca la imaginea online): o copie pe care prima pornire ar refuza-o e o copie cazuta, iar
		# omul e intrebat inainte sa piarda ceva
		try:
			return HdsCopieSetari.verifica_punerea(rez["cale"])
		except Exception as eroare:
			return str(eroare) or eroare.__class__.__name__
	return " ".join(rez.get("mesaje") or []) or "?"


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


def numeDinVersiune(continut):
	"""Numele imaginii din textul unui fisier imageversion, sau None. Al nostru e UN SINGUR rand cu numele/versiunea
	(vezi cercetarea din antetul fisierului) si ramane cum e. Copiile facute cu unealta de copii a imaginilor OE-Alliance
	(Screens/ImageBackup.py) au forma ini: "[Image Version]", apoi distro=, displaydistro=, imageversion=7.6. (si mai
	jos "[Enigma2 Settings]"); acolo numele e "displaydistro imageversion" (sau distro), luat numai din prima sectiune.
	Pana la 0.8.0 lista „Imagine nouă de pe stick” arata "[Image Version]" in locul numelui la toate aceste copii
	(TODO 23.11 23:04, AS154, asistenta 653874, tamiciav7, SF8008 0.7.8)."""
	chei = {}
	for linie in (continut or "").splitlines():
		linie = linie.strip()
		if not linie:
			continue
		if linie.startswith("[") and linie.endswith("]"):
			if chei:
				break  # sectiunea urmatoare (setarile) nu mai e numele imaginii
			continue
		cheie, egal, valoare = linie.partition("=")
		if not egal:
			if chei:
				continue
			return linie
		chei.setdefault(cheie.strip().lower(), valoare.strip().strip("'\"").strip())
	if not chei:
		return None
	nume = chei.get("displaydistro") or chei.get("distro") or ""
	versiune = (chei.get("imageversion") or chei.get("imgversion") or "").rstrip(".")
	return ("%s %s" % (nume, versiune)).strip() or None


def _primaLinie(cale):
	"""Numele imaginii din e2/update/imageversion (numeDinVersiune), sau None."""
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			return numeDinVersiune(f.read(HdsPazaModel.MARIME_MAXIMA_TEXT))
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


def numeNucleu(intrari, radacina):
	"""Numele nucleului in dosarul `radacina` al arhivei: kernel.bin, sau kernel_auto.bin al arhivelor Vu+ 4K numai cand
	dosarul nu are kernel.bin (un dosar cu amandoua ramane cu kernel.bin, ca pana acum)."""
	return NUME_KERNEL if radacina + NUME_KERNEL in intrari else NUME_KERNEL_VUPLUS


def esteVuplus(c):
	"""Pachetul are nucleul in kernel_auto.bin (arhivele Vu+ 4K de pe site)."""
	return c.get("nucleu_in_zip") == NUME_KERNEL_VUPLUS


def _acelasiModel(c):
	"""machinebuild din marcajul pachetului e chiar al imaginii care ruleaza (regulile ei); False la orice lipsa sau eroare."""
	try:
		masina = HdsPazaModel.cheiValori(c.get("marcaj") or "").get("machinebuild") or ""
		return bool(masina) and masina == (HdsPazaModel.citesteReguli() or {}).get("machinebuild")
	except Exception as eroare:
		print("[HdsSoftwareUpdate] modelul pachetului: %s" % eroare)
		return False


def _radacinaPachet(intrari):
	"""Dosarul din arhiva care tine kernel.bin (sau kernel_auto.bin, arhivele Vu+ 4K: numeNucleu) si rootfs.tar.bz2:
	e2/update, ca la noi, sau alt dosar (arhivele altor echipe, <producator>/<model>/, vuplus/<model>/). None daca nu e
	niciunul. Se scrie numai dupa simulare."""
	toate = set(intrari)
	sufix = "/".join(SUBCALE_UPDATE) + "/"
	bune = []
	for n in intrari:
		for nucleu in (NUME_KERNEL, NUME_KERNEL_VUPLUS):
			if n == nucleu or n.endswith("/" + nucleu):
				radacina = n[: -len(nucleu)]
				if radacina + NUME_ROOTFS in toate and numeNucleu(toate, radacina) == nucleu:
					bune.append(radacina)
	if len(bune) < 2:
		return bune[0] if bune else None
	# arhiva cu mai multe modele: numai dosarul acestui receptor, altfel nu se ghiceste
	model = (HdsPazaModel.citesteReguli() or {}).get("machinebuild", "")
	ale_lui = [r for r in bune if model and model in r.split("/")]
	if len(ale_lui) == 1:
		return ale_lui[0]
	ale_noastre = [r for r in bune if r.endswith(sufix)]
	return ale_noastre[0] if len(ale_noastre) == 1 else None


def dosareArhive(punct):
	"""Dosarele in care se cauta arhivele .zip pe un disc: radacina, apoi DOSARE_ARHIVE, numai cele care sunt dosare
	adevarate (nu legaturi si nu puncte de montare), ca in celelalte imagini OE-Alliance (getImagesList din ecranele lor de
	scriere a imaginii). Un Ustym 4K PRO avea arhiva in images/."""
	dosare = [punct]
	for nume in DOSARE_ARHIVE:
		cale = os.path.join(punct, nume)
		try:
			if os.path.isdir(cale) and not os.path.islink(cale) and not os.path.ismount(cale):
				dosare.append(cale)
		except (OSError, ValueError):
			continue
	return dosare


def _candidatiDinZipuri(disc):
	"""Arhivele .zip din radacina discului si din dosarele images/, downloaded_images/, imagebackups/ (dosareArhive) care
	contin, oriunde in interior, kernel.bin si rootfs.tar.bz2 in acelasi dosar (_radacinaPachet). Nu dezarhiveaza acum:
	doar detecteaza si citeste versiunea. Un dosar care nu se poate citi nu ascunde celelalte."""
	rezultat = []
	for dosar in dosareArhive(disc.mountpoint):
		try:
			nume_fisiere = os.listdir(dosar)
		except OSError:
			continue
		rezultat.extend(_candidatiDinDosar(disc, dosar, nume_fisiere))
	return rezultat


def _candidatiDinDosar(disc, dosar, nume_fisiere):
	"""Pachetele din arhivele .zip ale unui singur dosar (`nume_fisiere`: continutul lui)."""
	rezultat = []
	for nume in sorted(nume_fisiere):
		if not nume.lower().endswith(".zip"):
			continue
		cale_zip = os.path.join(dosar, nume)
		if not os.path.isfile(cale_zip):
			continue
		try:
			with zipfile.ZipFile(cale_zip) as z:
				# numele cu bara inversa (arhive facute pe Windows) se cauta dupa forma cu „/”, dar se citesc dupa
				# numele lor adevarat
				originale = {}
				for n in z.namelist():
					originale.setdefault(n.replace("\\", "/"), n)
				radacina = _radacinaPachet(list(originale))
				if radacina is None:
					continue
				versiune = None
				nume_versiune = radacina + NUME_VERSIUNE
				if nume_versiune in originale:
					try:
						with z.open(originale[nume_versiune]) as f_versiune:
							continut = f_versiune.read(HdsPazaModel.MARIME_MAXIMA_TEXT).decode("utf-8", "replace")
						versiune = numeDinVersiune(continut)
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
					"nucleu_in_zip": numeNucleu(originale, radacina),
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
	amprenta receptorului citita o data pentru toata lista (fara ea se citeste acum). Arhiva Vu+ (kernel_auto.bin) cat
	poarta HdsPazaModel.SCRIERE_VUPLUS e inchisa: REFUZ_VUPLUS in locul verdictului bun si al celui fara marcaj (nu trece nici
	dupa avertisment), si in locul lui alt receptor cand marcajul e al aceluiasi model (pe un Broadcom pornit din alt loc paza
	stricta refuza si arhiva lui); celelalte refuzuri (alt model, marcaj stricat) raman, ca omul sa afle motivul adevarat."""
	try:
		cod, text, _marcaj = HdsPazaModel.verificaPachet(c.get("marcaj"), a=a)
	except Exception as eroare:
		print("[HdsSoftwareUpdate] paza de model: %s" % eroare)
		cod, text = HdsPazaModel.REFUZ_NECITIT, HdsPazaModel.textRefuz(HdsPazaModel.REFUZ_NECITIT)
	if esteVuplus(c) and not getattr(HdsPazaModel, "SCRIERE_VUPLUS", False) and \
			(cod in (HdsPazaModel.PACHET_BUN, HdsPazaModel.REFUZ_FARA_MARCAJ) or
			(cod == HdsPazaModel.REFUZ_ALT_RECEPTOR and _acelasiModel(c))):
		return HdsPazaModel.REFUZ_VUPLUS, HdsPazaModel.textRefuz(HdsPazaModel.REFUZ_VUPLUS)
	return cod, text


def cautaCandidati(discuri=None):
	"""Toate pachetele de actualizare de pe `discuri` (implicit mediile montate acum), fiecare cu verdictul pazei
	(„paza”). Amprenta receptorului se citeste o singura data, pentru toate pachetele. Cu `discuri` dat, functia
	atinge numai fisiere si, la un stick cu spatii in nume, montarea lui (interfata web o cheama pe un fir separat)."""
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
			c["nume_stick"] = pregatesteNumeStick(c["disc"].mountpoint)[0]
			c["usb"] = versiuneUsb(c["disc"].mountpoint)
			marcheazaMediu(c, discuri)
		asazaPachete(candidati)
	return candidati


# ---------------------------------------------------------------- tipul partitiei de pe stick (USB6, 22.11.2026)
# Cazul Wlad (forum 948 #3681-#3683, asistenta 036824, STADIU-AS101, Amiko Viper 4K V10): stickul avea FAT32, dar tabela
# MBR il arata cu tipul 07 (NTFS/exFAT). Linux il monta, deci imaginea vedea fisierele, dar recovery-ul producatorului
# (incarcatorul) se uita dupa tipul din tabela si vedea 0 MB. Reparatia a fost un singur octet (tipul 0c).
# Aici: pentru fiecare stick montat (/dev/sdXN, numai partitiile primare 1-4 dintr-o tabela MBR curata) se citesc 1024 de
# octeti din discul intreg (tabela si sectorul 1, unde ar sta antetul GPT) si 512 din partitie (sectorul de pornire, unde
# scrie FAT32 / FAT16 / FAT12). Se repara NUMAI FAT (cazul dovedit al lui Wlad; exFAT si NTFS nu se ating), numai cand si
# felul montarii (vfat/msdos din /proc/mounts) spune FAT, numai pe tabele MBR fara nicio intrare 0xEE si fara antet
# "EFI PART" (o tabela hibrida se sare toata), si niciodata pe discurile pornirii: discul radacinii (aflat din
# os.stat("/").st_dev si /sys/dev/block, ca HdsStocare.discRadacina, nu din /proc/mounts, unde stau rootfs sau /dev/root),
# discul montat pe /boot si orice disc cu fisiere STARTUP* pe oricare partitie montata; cand discul radacinii nu se poate
# afla (overlay, loop, dm, /sys care nu raspunde), nu se propune si nu se scrie nimic. Omul afla pe ecran si in web si poate apasa „Repara tipul
# partitiei": se scrie numai octetul tipului din tabela (ca `sfdisk --part-type <disc> <nr> <tip>`), dupa ce totul de mai
# sus se verifica din nou chiar inainte de scriere, iar sectorul 0 al discului si sectorul partitiei trebuie sa fie
# identice cu cele vazute (alt stick cu acelasi /dev/sdX nu e atins); fisierele raman. Memoria interna (mmcblk) nu se citeste si nu se
# scrie niciodata. Citirile si scrierea merg pe un fir separat (ecranul de mai jos cu HdsPazaModel.LucrareFundal,
# actualizare_web la fel), niciodata pe firul interfetei. Stau aici, nu in Components/HdsRecuperare.py, fiindca acela nu
# deschide nimic din /dev (paza lui, test_recuperare_hostname).
# FAT32 se pune la 0x0C (FAT32 cu LBA) si nu la 0x0B: e tipul care a mers la Wlad, il primeste orice incarcator cu LBA
# (toate receptoarele noastre), iar 0x0B si 0x0C sunt amandoua socotite bune la verificare, deci un stick cu 0x0B nu e
# atins. FAT16 -> 0x0E (cu LBA), FAT12 -> 0x01.

# sistemul de fisiere -> (tipurile MBR potrivite, tipul pus la reparare); numai FAT
TIPURI_BUNE = {
	"FAT32": ((0x0b, 0x0c), 0x0c),
	"FAT16": ((0x04, 0x06, 0x0e), 0x0e),
	"FAT12": ((0x01,), 0x01),
}
# felul montarii din /proc/mounts care se potriveste cu un sistem FAT
MONTARI_FAT = ("vfat", "msdos")
NUME_TIP = {0x01: "FAT12", 0x04: "FAT16", 0x06: "FAT16", 0x07: "NTFS/exFAT", 0x0b: "FAT32", 0x0c: "FAT32 LBA",
	0x0e: "FAT16 LBA", 0x83: "Linux"}
_TIP_EXTINS_SAU_GPT = (0x00, 0x05, 0x0f, 0x85, 0xee, 0xef)


def sistemFisiere(sector):
	"""Sistemul de fisiere din primul sector al partitiei: "FAT32", "FAT16", "FAT12", "exFAT", "NTFS" sau ""."""
	if not sector or len(sector) < 512:
		return ""
	if sector[3:11] == b"EXFAT   ":
		return "exFAT"
	if sector[3:11] == b"NTFS    ":
		return "NTFS"
	if sector[510:512] != b"\x55\xaa":
		return ""
	if sector[82:87] == b"FAT32":
		return "FAT32"
	if sector[54:59] == b"FAT16":
		return "FAT16"
	if sector[54:59] == b"FAT12":
		return "FAT12"
	return ""


def imparteDispozitiv(dispozitiv):
	"""'/dev/sdb1' -> ('/dev/sdb', 1); numai discurile USB/SATA sd* si partitiile 1-4; altfel (None, 0)."""
	d = (dispozitiv or "").strip()
	if d.startswith("/dev/"):
		d = d[5:]
	i = len(d)
	while i > 0 and d[i - 1].isdigit():
		i -= 1
	disc, nr = d[:i], d[i:]
	if not disc.startswith("sd") or not disc[2:].isalpha() or not nr or not 1 <= int(nr) <= 4:
		return None, 0
	return "/dev/" + disc, int(nr)


def montare(punct, mounts="/proc/mounts"):
	"""(dispozitiv, felul montarii) pentru `punct`, din /proc/mounts (ultima montare pe acel punct), sau ("", "")."""
	punct = (punct or "").rstrip("/") or "/"
	rez = ("", "")
	try:
		with open(mounts, "r") as f:
			for rand in f:
				parti = rand.split()
				if len(parti) >= 3 and (parti[1].replace("\\040", " ").rstrip("/") or "/") == punct:
					rez = (parti[0], parti[2])
	except (IOError, OSError):
		pass
	return rez


def dispozitivMontare(punct, mounts="/proc/mounts"):
	"""Dispozitivul montat pe `punct` (din /proc/mounts), sau ""."""
	return montare(punct, mounts)[0]


def _citesteOcteti(cale, inceput, marime):
	try:
		with open(cale, "rb") as f:
			f.seek(inceput)
			return f.read(marime)
	except (IOError, OSError):
		return b""


def tabelaMbrCurata(octeti):
	"""True pentru o tabela MBR fara GPT: semnatura 55 AA, nicio intrare 0xEE (nici hibrida) si sectorul 1 fara antetul
	"EFI PART". `octeti`: primii 1024 de octeti ai discului."""
	if len(octeti) < 512 or octeti[510:512] != b"\x55\xaa":
		return False
	b = bytearray(octeti)
	if any(b[446 + 16 * i + 4] == 0xee for i in range(4)):
		return False
	return octeti[512:520] != b"EFI PART"


def verificaTip(disc, nr, partitie):
	"""Tipul partitiei `nr` din tabela MBR a lui `disc` fata de sistemul de fisiere din `partitie` (cai: dispozitive sau,
	in probe, fisiere imagine). -> dict {disc, nr, partitie, tip, fs, bun, mbr, sector} cand nu se potrivesc, altfel None.
	Numai FAT, numai pe o tabela MBR curata (tabelaMbrCurata). "mbr" (sectorul 0 intreg: semnatura discului, toate
	intrarile) si "sector" (sectorul de pornire al partitiei: eticheta, numarul de serie) se compara din nou chiar inainte de
	scriere (reparaTip), ca alt stick care primeste acelasi /dev/sdX sa nu fie atins."""
	inceput = _citesteOcteti(disc, 0, 1024)
	if not tabelaMbrCurata(inceput):
		return None
	tip = bytearray(inceput)[446 + 16 * (nr - 1) + 4]
	if tip in _TIP_EXTINS_SAU_GPT:
		return None
	sector = _citesteOcteti(partitie, 0, 512)
	fs = sistemFisiere(sector)
	if fs not in TIPURI_BUNE:
		return None
	potrivite, bun = TIPURI_BUNE[fs]
	if tip in potrivite:
		return None
	return {"disc": disc, "nr": nr, "partitie": partitie, "tip": tip, "fs": fs, "bun": bun, "mbr": bytes(inceput[:512]),
		"sector": bytes(sector)}


def _discDe(dispozitiv):
	"""'/dev/sda10' -> '/dev/sda' (orice numar de partitie), '' pentru restul."""
	d = (dispozitiv or "").strip().rstrip("0123456789")
	return d if d.startswith("/dev/sd") and d[7:].isalpha() and d[7:] else ""


def discRadacina(st_dev=None, realpath=None, major=None, minor=None, mounts="/proc/mounts"):
	"""Discul sd* de pe care ruleaza imaginea ('/dev/sda'), din numerele radacinii (os.stat("/").st_dev si
	/sys/dev/block/<major>:<minor>), ca Components/HdsStocare.discRadacina, nu din /proc/mounts; "" numai cand e dovedit ca
	radacina e in memoria interna (mmcblk*, mtdblock*, sau fara dispozitiv de bloc cu ubifs/jffs2); None cand nu se poate
	afla (os.major lipsa, eroare, overlay/nfs/tmpfs, loop, dm, md, orice alt nume): atunci nu se propune si nu se scrie
	nicio reparare."""
	major = major or getattr(os, "major", None)
	minor = minor or getattr(os, "minor", None)
	if major is None or minor is None:
		return None
	try:
		if st_dev is None:
			st_dev = os.stat("/").st_dev
		mare, mic = major(st_dev), minor(st_dev)
		if not mare:
			return "" if montare("/", mounts)[1] in ("ubifs", "jffs2") else None
		parti = (realpath or os.path.realpath)("/sys/dev/block/%d:%d" % (mare, mic)).split("/")
	except (OSError, IOError, ValueError, TypeError):
		return None
	if "block" not in parti or parti.index("block") + 1 >= len(parti):
		return None
	nume = parti[parti.index("block") + 1]
	if nume.startswith("mmcblk") or nume.startswith("mtdblock"):
		return ""
	if nume.startswith("sd") and nume[2:].isalpha():
		return "/dev/" + nume
	return None


def _montariSd(mounts):
	"""[(dispozitiv, punct)] pentru fiecare rand /dev/sd* din /proc/mounts."""
	rez = []
	try:
		with open(mounts, "r") as f:
			for rand in f:
				parti = rand.split()
				if len(parti) >= 2 and parti[0].startswith("/dev/sd"):
					rez.append((parti[0], parti[1].replace("\\040", " ")))
	except (IOError, OSError):
		pass
	return rez


def discuriPornire(mounts="/proc/mounts", st_dev=None, realpath=None, major=None, minor=None):
	"""Discurile sd* ale pornirii, pe care nu se propune si nu se scrie nicio reparare: cel de pe care ruleaza imaginea
	(discRadacina), cel montat pe /boot si orice disc care are fisiere STARTUP* pe /boot sau pe ORICARE din partitiile lui
	montate (fiecare rand /dev/sd* din /proc/mounts). None cand discul radacinii nu se poate afla."""
	radacina = discRadacina(st_dev, realpath, major, minor, mounts)
	if radacina is None:
		return None
	rez = set()
	if radacina:
		rez.add(radacina)
	d = _discDe(dispozitivMontare("/boot", mounts))
	if d:
		rez.add(d)
	for dispozitiv, punct in [(dispozitivMontare("/boot", mounts), "/boot")] + _montariSd(mounts):
		try:
			if any(n.startswith("STARTUP") for n in os.listdir(punct)):
				d = _discDe(dispozitiv)
				if d:
					rez.add(d)
		except (IOError, OSError):
			continue
	return rez


def _deReparat(punct, mounts, oprite):
	"""(disc, nr, dispozitiv) pentru stickul montat pe `punct` daca poate primi o reparare (sd*1-4, montat vfat/msdos, nu
	e disc al pornirii), altfel None."""
	dispozitiv, fel = montare(punct, mounts)
	disc, nr = imparteDispozitiv(dispozitiv)
	if not disc or disc in oprite or fel not in MONTARI_FAT:
		return None
	return disc, nr, dispozitiv


def tipuriGresite(puncte, mounts="/proc/mounts", st_dev=None, realpath=None, major=None, minor=None):
	"""[info] pentru stickurile montate pe `puncte` cu tipul partitiei gresit (vezi verificaTip), cu "punct" in plus; fara
	discurile pornirii (discuriPornire) si numai cu montarea FAT. Pe firul separat: citeste /proc/mounts, numele din
	radacina fiecarui stick si cate 1,5 KB din fiecare."""
	rez, vazute = [], set()
	oprite = discuriPornire(mounts, st_dev, realpath, major, minor)
	if oprite is None:
		return []
	for punct in puncte:
		gasit = _deReparat(punct, mounts, oprite)
		if gasit is None or gasit[:2] in vazute:
			continue
		disc, nr, dispozitiv = gasit
		vazute.add((disc, nr))
		try:
			info = verificaTip(disc, nr, dispozitiv)
		except Exception as eroare:
			print("[HdsSoftwareUpdate] tipul partitiei %s: %s" % (dispozitiv, eroare))
			info = None
		if info:
			info["punct"] = punct
			rez.append(info)
	return rez


def numeTip(tip):
	return "%02X" % tip + (" (%s)" % NUME_TIP[tip] if tip in NUME_TIP else "")


def textTipGresit(info, nume=""):
	"""Textul pentru om (ecran si web): ce nu se potriveste, ce urmeaza daca ramane asa si ce face reparatia."""
	return _("Pe stickul „%s” partiția %d are sistemul de fișiere %s, dar tabela de partiții o arată ca tip %s. "
		"Recovery-ul producătorului nu vede atunci arhivele de pe stick (0 MB). Repară tipul partiției: schimb numai acest "
		"octet în %s, fișierele de pe stick rămân neatinse.") % (
		nume or info.get("punct") or info["partitie"], info["nr"], info["fs"], numeTip(info["tip"]), numeTip(info["bun"]))


def textRandTip(nume):
	return _("Repară tipul partiției pe „%s”") % nume


def reparaTip(info, mounts="/proc/mounts", st_dev=None, realpath=None, major=None, minor=None):
	"""Scrie in tabela MBR numai octetul tipului partitiei (info din tipuriGresite, cu "punct", "mbr" si "sector"). Chiar
	inainte de scriere verifica din nou tot, cu aceeasi lista intreaga ca la verificare: discul radacinii se poate afla si
	discul nu e al pornirii (radacina, /boot, STARTUP* pe oricare partitie montata), montarea e tot FAT, sectorul partitiei
	e acelasi octet cu octet, iar pe acelasi fisier deschis tabela e tot MBR curata, sectorul 0 e acelasi octet cu octet si
	tipul e cel vazut. Fara oricare din ele nu scrie. -> (True, text) sau (False, text). Ruleaza pe firul separat."""
	schimbata = _("Tabela de partiții a stickului s-a schimbat între timp. Caută din nou software-ul.")
	if info.get("fs") not in TIPURI_BUNE or not 1 <= info.get("nr", 0) <= 4 or not info.get("punct") or \
			len(info.get("mbr") or b"") != 512 or len(info.get("sector") or b"") != 512:
		return False, schimbata
	oprite = discuriPornire(mounts, st_dev, realpath, major, minor)
	if oprite is None:
		return False, _("Nu pot afla de pe ce disc pornește receptorul, deci nu schimb tabela stickului.")
	if info["disc"] in oprite or _deReparat(info["punct"], mounts, oprite) != (info["disc"], info["nr"], info["partitie"]):
		return False, schimbata
	if _citesteOcteti(info["partitie"], 0, 512) != info["sector"]:
		return False, schimbata
	loc = 446 + 16 * (info["nr"] - 1) + 4
	try:
		with open(info["disc"], "r+b") as f:
			inceput = f.read(1024)
			if not tabelaMbrCurata(inceput) or inceput[:512] != info["mbr"] or bytearray(inceput)[loc] != info["tip"]:
				return False, schimbata
			f.seek(loc)
			f.write(bytearray([info["bun"]]))
			f.flush()
			os.fsync(f.fileno())
	except (IOError, OSError) as eroare:
		return False, _("Tipul partiției nu s-a putut schimba: %s") % (getattr(eroare, "strerror", None) or eroare)
	return True, _("Gata: partiția %d a stickului are acum tipul %s. Recovery-ul producătorului poate citi arhivele de pe "
		"el.") % (info["nr"], numeTip(info["bun"]))


def stickNumaiCitire(punct):
	"""True cand pe `punct` se poate numai citi: aceeasi verificare ca la locul inregistrarilor (Components/HdsStocare.verificaDisc)."""
	try:
		from Components import HdsStocare
		return HdsStocare.verificaDisc(punct.rstrip("/") + "/")[1] == "numai_citire"
	except Exception as eroare:
		print("[HdsSoftwareUpdate] starea stickului: %s" % eroare)
		return False


def discDeReparat(disc):
	"""Discul intreg de verificat („sdb”) pentru partitia `disc`; „” fara dispozitiv sau cu stickul protejat din comutatorul lui, unde
	verificarea n-ar folosi la nimic."""
	try:
		from Components import HdsLocInregistrari, HdsStocare
		dispozitiv = getattr(disc, "device", None) or ""
		nume = HdsLocInregistrari.discul(dispozitiv) if dispozitiv else ""
		if not nume or HdsStocare._citesteSys("/sys/block/%s/ro" % nume) == "1":
			return ""
		return nume
	except Exception as eroare:
		print("[HdsSoftwareUpdate] discul de reparat: %s" % eroare)
		return ""


def _numeBunPentruOfgwrite(punct):
	"""Numele montarii, fara sa mute nimic: discul acesta nu e al pachetului, iar pe el poate merge o inregistrare."""
	from Tools.MediuImagine import verificaNumeStick
	return not verificaNumeStick(punct)[0]


def locDezarhivare(c, discuri):
	"""Alt disc pentru dosarul curat, cand pe stickul pachetului se poate numai citi: primit de paznic (un disc USB, nu dispozitivul
	radacinii), bun de scris, cu nume bun pentru ofgwrite si cu loc pentru pachet. None cand nu e niciunul."""
	try:
		from Components import HdsStocare
		marime = _marimePachet(c)
	except Exception as eroare:
		print("[HdsSoftwareUpdate] alt disc: %s" % eroare)
		return None
	for disc in discuri:
		punct = disc.mountpoint
		if punct == c["disc"].mountpoint:
			continue
		try:
			permis, motiv, _d, _p = verificaMediuScriere(punct)
			if not permis or motiv != "usb" or not HdsStocare.verificaDisc(punct.rstrip("/") + "/")[0]:
				continue
			if not _numeBunPentruOfgwrite(punct) or not _spatiuSuficient(punct, marime):
				continue
		except Exception as eroare:
			print("[HdsSoftwareUpdate] alt disc %s: %s" % (punct, eroare))
			continue
		return punct
	return None


def marcheazaMediu(c, discuri):
	"""Pune in pachet „numai_citire” (stickul lui), „loc_lucru” (unde se face dosarul curat; None: nicaieri) si „disc_reparat” (ce se
	verifica la OK, cand nu e alt loc)."""
	punct = c["disc"].mountpoint
	c["numai_citire"] = stickNumaiCitire(punct)
	c["loc_lucru"] = punct
	c["disc_reparat"] = ""
	if c["numai_citire"]:
		c["loc_lucru"] = locDezarhivare(c, discuri)
		if not c["loc_lucru"]:
			c["disc_reparat"] = discDeReparat(c["disc"])


def faraLoc(c):
	"""Pachetul sta pe un stick pus pe numai citire si nu e alt disc unde sa se pregateasca."""
	return bool(c.get("numai_citire")) and not c.get("loc_lucru")


def locLucru(c):
	return c.get("loc_lucru") or c["disc"].mountpoint


def numeMediu(c):
	return c["disc"].description or c["disc"].mountpoint


def textStickCazut(c, cu_ok=True):
	"""Sus in lista, cand pachetul nu are unde sa se pregateasca. `cu_ok`: si ce face OK (pagina web are legatura ei, nu OK)."""
	if c.get("disc_reparat"):
		text = _("Pe „%s” se poate numai citi, după o eroare a stickului, deci software-ul nu se poate pregăti pe el.") % numeMediu(c)
		if cu_ok:
			text += " " + _("Apasă OK: verific stickul, îi repar erorile și citesc lista din nou. Nu se formatează nimic.")
		return text
	return _("Pe „%s” se poate numai citi. Copiază software-ul pe alt stick și încearcă din nou.") % numeMediu(c)


def scurtNumeStick(motiv):
	"""Verdictul din lista cand stickul are un nume cu care ofgwrite nu poate scrie (None: numele e bun)."""
	if motiv == REFUZ_SPATII:
		return _("nu se poate instala: numele stickului are spații")
	if motiv:
		return _("nu se poate instala: numele stickului are semne neacceptate")
	return None


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
	return _("Software: %s") % "  ·  ".join(_numeSiVersiune(c)) + "\n" + \
		_("Acum se face numai o verificare (o simulare): nu se instalează nimic pe receptor. Continui?")


def discUsbTinta(cmdline=None):
	"""Partitia radacinii cand locul care ruleaza acum (si deci cel in care se scrie) e pe un disc USB: locul de pe stick
	al pornirii multiple sau un loc kexec de pe USB (tintaScrierii); "" altfel sau la orice eroare."""
	try:
		t = tintaScrierii(_citesteCmdline() if cmdline is None else cmdline)
	except ValueError:
		return ""
	return t["radacina"] if t["fel"] in ("usb", "kexec_usb") else ""


def textUltimaConfirmare(c, inregistrare=False, recuperare="", subdosar="", usb=""):
	"""Ultima confirmare: textul simplu (se termina cu intrebarea), apoi, dupa un rand gol, randurile mai mici: fraza
	cu dosarul pentru Maintenance Mode (`recuperare`, poate lipsi) si pachetul. `subdosar`: rootsubdir= din
	/proc/cmdline (primul Viper 4K, V10: sistemul intr-un subdosar, repararea cu arhiva producatorului); "" = o
	singura pereche de partitii (V20, V30, V40), textul de pana acum. `usb`: partitia locului de pe disc USB in care se
	scrie (discUsbTinta); imaginile din memoria interna nu se schimba."""
	sus = _("Atenție: o înregistrare este în curs chiar acum.") + "\n" if inregistrare else ""
	tehnic = (recuperare.strip() + "\n" if recuperare and recuperare.strip() else "") + \
		_("Software: %s") % "  ·  ".join(_numeSiVersiune(c))
	if esteCopieCompleta(c):
		pereche = _("Este o copie completă: se pune înapoi exact cum a fost făcută, cu setările, canalele și pluginurile ei. "
			"Setările de acum nu se mai copiază și nu se pun peste ea.")
	elif usb:
		pereche = _("Noul software se instalează în locul celui care rulează acum, pe discul USB (%s). Imaginile din memoria internă nu se schimbă. Înainte de instalare, setările și lista de canale se copiază pe stick.") % usb
	elif subdosar:
		pereche = _("Noul software se instalează în locul celui care rulează acum (dosarul %s din memoria internă): dacă nu pornește, repararea se face de mână, cu arhiva de recuperare a producătorului pe un stick. Înainte de instalare, setările și lista de canale se copiază pe stick.") % subdosar
	else:
		pereche = _("Receptorul are o singură pereche de nucleu și sistem în memoria internă (fără multiboot): dacă noul software nu pornește, singura reparare este Maintenance Mode, de mână. Înainte de instalare, setările și lista de canale se copiază pe stick.")
	return sus + _("Noul software se instalează acum pe receptor. Nu opri receptorul din priză și nu scoate stickul cât timp se instalează; interfața se oprește, iar receptorul repornește singur la final.") + "\n" + pereche + "\n" + \
		_("Instalezi acum software-ul pe receptor?") + "\n\n" + tehnic


def _descriereCandidat(c):
	"""Pachetul pe un singur rand de text: verdictul pazei (refuzurile incep cu „nu se scrie”), numele, versiunea si
	mediul. E cheia randului din lista; pe ecran randul il deseneaza _intrariPachet."""
	sursa = c["disc"].description or c["disc"].mountpoint
	parti = _numeSiVersiune(c) + [sursa]
	stick = scurtNumeStick(c.get("nume_stick"))
	if stick:
		parti.insert(0, stick)
	elif c.get("fel") == FEL_STRAINA:
		parti.insert(0, _("Nu este imagine HD Satelit și nu o putem verifica"))
	elif c.get("paza"):
		parti.insert(0, HdsPazaModel.scurtRefuz(c["paza"][0]))
	return "  ·  ".join(parti)


# ---------------------------------------------------------------- ordinea si starea pachetelor (Eduard, 04.11.2026)
# Fiecare imagine e o cartela a ei, cu semn colorat in fata si cu starea scrisa mare: cea mai noua compatibila, apoi
# celelalte compatibile, apoi cele incompatibile. Cea mai noua compatibila sta prima, deci OK o alege direct.
# Desenul: design-web-stitch/skin-pro/imagine-de-pe-stick.png.
FEL_NOUA = "noua"
FEL_BUNA = "buna"
FEL_STRAINA = "straina"
FEL_REA = "rea"
_NUME_IMAGINE_RX = re.compile(r"hdsatelit-(\d+(?:\.\d+)+)(?:\S*?[-_](20\d{6})(?!\d))?", re.I)
_NUME_STRAIN_RX = re.compile(r"^([^\W\d][^-_]*)[-_ ]+(\d+(?:\.\d+)*)")
# copia imaginii noastre facuta cu alta unealta: imageversion „HD Satelit 0.7.6” (displaydistro din usr/lib/enigma.info),
# „hdsatelit 0.7.6” (distro) sau arhiva backup-HD_Satelit-0.7.6-...zip; forma oficiala hdsatelit-0.7.6 e a _NUME_IMAGINE_RX
# versiunea poate lipsi: pe modelele fara cheile de identitate enigma.info n-are imageversion=, deci copia scrie
# "imageversion=." si numele ramane numai „HD Satelit”
_NUME_COPIE_HDS_RX = re.compile(r"(?<![^\W_])hd[ _]?satelit(?![^\W_])(?:[ _-]+v?(\d+(?:\.\d+)+))?", re.I)


def _literaMare(text):
	return text[:1].upper() + text[1:]


def versiuneSiData(c):
	"""((0, 7, 0), "20261104") din numele imaginii (hdsatelit-0.7.0-viper4kv20-20261104); ((), "") pentru alte nume"""
	nume_zip = os.path.basename(c.get("cale_zip") or "")
	for text in (c.get("versiune") or "", nume_zip):
		m = _NUME_IMAGINE_RX.search(text)
		if m:
			return tuple(int(x) for x in m.group(1).split(".")), m.group(2) or ""
	return (), ""


def esteCopieCompleta(c):
	"""Pachetul e o copie completa facuta de receptor (Components/HdsCopieImagine.py): marcajul are copie_completa=da.
	O copie completa se pune inapoi exact cum a fost facuta: fara copia setarilor de acum inainte de scriere, deci fara
	punerea ei la loc la prima pornire (hotararea din 11.11.2026, randul 205). Semnul e in marcaj, nu in numele fisierului:
	numele il poate schimba omul, marcajul e fisierul pe care instalarea il citeste si il verifica oricum."""
	return HdsPazaModel.cheiValori(c.get("marcaj") or "").get("copie_completa") == "da"


_COPIE_RX = re.compile(r"-copie-(20\d{6})-(\d{2})(\d{2})")


def _compatibil(c):
	return (c.get("paza") or (None,))[0] == HdsPazaModel.PACHET_BUN and not c.get("nume_stick")


def _deLaAltii(c):
	"""Imagine fara semn si fara nume HD Satelit: de la alta echipa sau de la producator. Se poate instala, dar omul e
	anuntat la OK ca nu stim daca e compatibila: nu e a noastra si nu o putem verifica (Eduard, 04.11.2026)."""
	return (c.get("paza") or (None,))[0] == HdsPazaModel.REFUZ_FARA_MARCAJ and not versiuneSiData(c)[0]


def _copieHds(c):
	"""(True, "0.7.6") cand imageversion sau numele arhivei spun ca e imaginea noastra copiata cu alta unealta (versiunea
	poate fi ""), altfel (False, "")"""
	gasit = False
	for text in (c.get("versiune") or "", os.path.basename(c.get("cale_zip") or "")):
		m = _NUME_COPIE_HDS_RX.search(text)
		if m:
			if m.group(1):
				return True, m.group(1)
			gasit = True
	return gasit, ""


def esteCopieHdsFaraSemn(c):
	"""Imagine fara semnul modelului care se numeste HD Satelit: copia imaginii noastre facuta cu unealta de copii a altei
	imagini sau a OE-Alliance (backup-HD_Satelit-0.7.6-...zip). Ramane neverificata, ca orice imagine fara semn (se poate
	instala numai dupa avertisment), dar omului nu i se mai spune ca nu e imagine HD Satelit (TODO 23.11 23:04, AS154,
	tamiciav7: copia lui de 0.7.6 era aratata ca imaginea altora)."""
	return _deLaAltii(c) and _copieHds(c)[0]


def numeImagineStraina(c):
	"""Numele imaginii altora, cum e scris in fisierele ei: imageversion, apoi numele arhivei („nume-7.6-model-data” da
	„nume 7.6”). Textul vine din arhiva, deci se curata; in cod nu e scris niciun nume de imagine."""
	gasit, versiune = _copieHds(c)
	if gasit:
		return ("HD Satelit %s" % versiune).strip()
	nume_zip = os.path.splitext(os.path.basename(c.get("cale_zip") or ""))[0]
	curate = [re.sub(r"[^\w .+-]", "", t, flags=re.U).strip()[:60] for t in (c.get("versiune") or "", nume_zip) if "=" not in t]
	for text in curate:
		m = _NUME_STRAIN_RX.match(text)
		if m:
			return "%s %s" % (m.group(1), m.group(2))
	for text in curate:
		if text:
			return text
	return _numePachet(c)


def textImagineStraina(c):
	"""Ce i se spune omului despre imaginea altora: sus in lista si in avertismentul de la OK"""
	if esteCopieHdsFaraSemn(c):
		return _("Este o copie a imaginii %s făcută cu altă unealtă, fără semnul modelului. Nu știm pentru ce receptor a "
			"fost făcută, deci nu o putem verifica.") % numeImagineStraina(c)
	return _("Nu este imagine HD Satelit, ci %s. Nu știm dacă este compatibilă cu acest receptor, pentru că nu ne "
		"aparține și nu o putem verifica.") % numeImagineStraina(c)


def textAvertismentStrain(c):
	"""Intrebarea de la OK pe imaginea altora; se termina cu intrebarea, „Nu” e ales"""
	return textImagineStraina(c) + "\n" + \
		_("Dacă nu este făcută pentru modelul acestui receptor, receptorul poate rămâne fără pornire până la recuperarea "
		"de pe stick.") + "\n" + \
		_("Dacă o instalezi, ea înlocuiește imaginea HD Satelit. Setările și lista de canale se copiază întâi pe stick.") + \
		"\n" + _("Continui?")


def textScurtStrain(c):
	"""Randul mic al cartelei unei imagini neverificate (si verdictul din pagina web)"""
	if esteCopieHdsFaraSemn(c):
		return _("Copie HD Satelit fără semnul modelului; nu o putem verifica")
	return _("Nu este imagine HD Satelit și nu o putem verifica")


def asazaPachete(candidati):
	"""Ordinea din lista si felul fiecarui pachet („fel”), in aceeasi lista: compatibilele primele, cea mai noua intai,
	apoi cele de la alte echipe si la sfarsit cele incompatibile."""
	# la aceeasi versiune si data decide numele arhivei, in care data sta tot la sfarsit
	candidati.sort(key=lambda c: versiuneSiData(c) + (os.path.basename(c.get("cale_zip") or ""),), reverse=True)
	# copiile complete dupa imaginile de pe site: „cea mai noua” ramane o imagine adevarata, cand e una pe stick
	candidati.sort(key=lambda c: (1 if esteCopieCompleta(c) else 0) if _compatibil(c) else (2 if _deLaAltii(c) else 3))
	for i, c in enumerate(candidati):
		if _compatibil(c):
			c["fel"] = FEL_NOUA if i == 0 else FEL_BUNA
		elif _deLaAltii(c):
			c["fel"] = FEL_STRAINA
			c["paza"] = (c["paza"][0], textImagineStraina(c))
		else:
			c["fel"] = FEL_REA
	return candidati


def textGasite(n):
	"""Randul de sus al listei"""
	if n == 1:
		return _("Am găsit o variantă de software. Apasă OK ca să fie verificată.")
	return _("Am găsit %d variante de software. Alege una și apasă OK ca să fie verificată.") % n


def textFel(fel):
	"""Eticheta starii, pe cartela si in pagina web"""
	if fel == FEL_NOUA:
		return _("Cea mai nouă compatibilă")
	if fel == FEL_BUNA:
		return _("Compatibilă")
	if fel == FEL_STRAINA:
		return _("Neverificată")
	return _("Incompatibilă")


def titluPachet(c):
	"""Randul mare al cartelei: „HD Satelit 0.7.0, 04.11.2026”; numele pachetului cand nu e o imagine HD Satelit"""
	versiune, data = versiuneSiData(c)
	if c.get("fel") == FEL_STRAINA:
		return _literaMare(numeImagineStraina(c))
	if esteCopieCompleta(c):
		m = _COPIE_RX.search(os.path.basename(c.get("cale_zip") or "") + " " + (c.get("versiune") or ""))
		if m:
			d = m.group(1)
			return _("Copia completă din %s") % ("%s.%s.%s, %s:%s" % (d[6:8], d[4:6], d[:4], m.group(2), m.group(3)))
		return _("Copia completă a imaginii")
	if not versiune:
		return _literaMare(_numePachet(c)) if c["tip"] == "folder" else _numePachet(c)
	titlu = "HD Satelit %s" % ".".join(str(x) for x in versiune)
	return titlu + (", %s.%s.%s" % (data[6:8], data[4:6], data[:4]) if data else "")


def detaliuPachet(c):
	"""Randul mic al cartelei: de ce nu se instaleaza, numele fisierului (daca nu e deja in titlu), stickul si viteza lui"""
	parti = []
	if c.get("fel") == FEL_STRAINA:
		parti.append(textScurtStrain(c))
	elif not _compatibil(c):
		parti.append(_literaMare(scurtNumeStick(c.get("nume_stick")) or HdsPazaModel.scurtRefuz((c.get("paza") or (None,))[0])))
	if faraLoc(c) and c.get("fel") != FEL_REA:
		parti.append(_("Pe stick se poate numai citi"))
	if versiuneSiData(c)[0]:
		parti.append(_literaMare(_numePachet(c)) if c["tip"] == "folder" else _numePachet(c))
	parti.append(c["disc"].description or c["disc"].mountpoint)
	if c.get("usb"):
		parti.append(c["usb"])
	return "  ·  ".join(parti)


# culorile din tema si rezerva pentru alt skin; fondul si chenarul cartelei, din desenul Stitch
_CULORI_LISTA = {
	"fond": ("hdsPanelSolid", 0x10162A),
	"chenar": ("hdsTrack", 0x2A3350),
	"fond_ales": (None, 0x16234D),
	"chenar_ales": ("hdsBrand", 0x374EA1),
	"text": ("hdsText", 0xF2F4F8),
	"text_ales": ("hdsSelText", 0xFFFFFF),
	"mic": ("hdsText2", 0xC9D2E3),
	"sters": ("hdsLabel", 0xAEB9CC),
	"pe_verde": ("hdsPanelSolid", 0x10162A),
	"alb": ("white", 0xFFFFFF),
}
_CULOARE_FEL = {
	FEL_NOUA: ("hdsGood", 0x4FD18B),
	FEL_BUNA: (None, 0x3B82F6),
	FEL_STRAINA: ("hdsAmber", 0xF5B83D),
	FEL_REA: ("hdsBad", 0xFF6B5E),
}


def _culoareTema(nume, rezerva):
	if nume:
		try:
			from skin import colorNames
			return colorNames[nume].argb() & 0xFFFFFF
		except Exception:
			pass
	return rezerva


def _culoriLista():
	c = dict((k, _culoareTema(*v)) for k, v in _CULORI_LISTA.items())
	c.update(dict((k, _culoareTema(*v)) for k, v in _CULOARE_FEL.items()))
	return c


def _cartela(lat, inalt, gol, c, chenar, margine=0):
	"""Dreptunghiurile cartelei: spatiul de sub ea si cel din dreapta (cu acelasi fond si pe randul ales, ca sa nu se
	lipeasca de vecina), chenarul si fondul"""
	from Components.MultiContent import MultiContentEntryText as T
	sus = inalt - gol
	return [
		T(pos=(0, sus), size=(lat + margine, gol), font=0, text="", backcolor=c["fond"], backcolor_sel=c["fond"]),
		T(pos=(lat, 0), size=(margine, sus), font=0, text="", backcolor=c["fond"], backcolor_sel=c["fond"]),
		T(pos=(0, 0), size=(lat, sus), font=0, text="", backcolor=c["chenar"], backcolor_sel=c["chenar_ales"]),
		T(pos=(chenar, chenar), size=(lat - 2 * chenar, sus - 2 * chenar), font=0, text="", backcolor=c["fond"],
			backcolor_sel=c["fond_ales"]),
	]


def _intrariPachet(p, lat, inalt, f, c, margine=0):
	"""Randul din lista pentru pachetul `p`: cheia (textul lui pe un rand), cartela, semnul in fata, titlul, randul mic
	si eticheta starii. `f`: scara fata de 1920 px."""
	from enigma import RT_HALIGN_CENTER, RT_HALIGN_LEFT, RT_VALIGN_CENTER
	from Components.MultiContent import MultiContentEntryText as T
	gol, chenar = int(14 * f), max(2, int(3 * f))
	sus = inalt - gol
	semn, x = int(30 * f), int(26 * f)
	xt = x + semn + int(26 * f)
	fel = p.get("fel") or FEL_REA
	culoare = c[fel]
	eticheta = textFel(fel)
	le = int(len(eticheta) * 19 * f) + int(44 * f)
	he = int(66 * f)
	xe = lat - le - int(26 * f)
	lt = max(10, xe - xt - int(20 * f))
	titlu = c["sters"] if fel == FEL_REA else c["text"]
	mic = c["sters"] if fel == FEL_REA else c["mic"]
	pe_eticheta = c["pe_verde"] if fel in (FEL_NOUA, FEL_STRAINA) else c["alb"]
	st = RT_HALIGN_LEFT | RT_VALIGN_CENTER
	return [_descriereCandidat(p)] + _cartela(lat, inalt, gol, c, chenar, margine) + [
		T(pos=(x, (sus - semn) // 2), size=(semn, semn), font=0, text="", backcolor=culoare, backcolor_sel=culoare),
		T(pos=(xt, int(12 * f)), size=(lt, int(50 * f)), font=0, flags=st, text=titluPachet(p), color=titlu,
			color_sel=c["text_ales"], backcolor=c["fond"], backcolor_sel=c["fond_ales"]),
		T(pos=(xt, int(62 * f)), size=(lt, int(38 * f)), font=1, flags=st, text=detaliuPachet(p), color=mic,
			color_sel=c["mic"], backcolor=c["fond"], backcolor_sel=c["fond_ales"]),
		T(pos=(xe, (sus - he) // 2), size=(le, he), font=2, flags=RT_HALIGN_CENTER | RT_VALIGN_CENTER, text=eticheta,
			color=pe_eticheta, color_sel=pe_eticheta, backcolor=culoare, backcolor_sel=culoare),
	]


def _intrariSimple(text, lat, inalt, f, c, margine=0):
	"""Randul fara stare („Caută din nou software de receptor”, „Nu am găsit...”): cartela, semn mic si text"""
	from enigma import RT_HALIGN_LEFT, RT_VALIGN_CENTER
	from Components.MultiContent import MultiContentEntryText as T
	gol, chenar = int(14 * f), max(2, int(3 * f))
	sus = inalt - gol
	semn, x = int(16 * f), int(33 * f)
	xt = x + semn + int(33 * f)
	return [text] + _cartela(lat, inalt, gol, c, chenar, margine) + [
		T(pos=(x, (sus - semn) // 2), size=(semn, semn), font=0, text="", backcolor=c["sters"], backcolor_sel=c["alb"]),
		T(pos=(xt, chenar), size=(max(10, lat - xt - int(26 * f)), sus - 2 * chenar), font=0, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER,
			text=text, color=c["text"], color_sel=c["text_ales"], backcolor=c["fond"], backcolor_sel=c["fond_ales"]),
	]


def _spatiuSuficient(mountpoint, octeti_necesari):
	try:
		st = os.statvfs(mountpoint)
		return (st.f_bavail * st.f_frsize) >= octeti_necesari
	except OSError:
		return True  # nu blocam daca nu putem verifica (mai bine incearca si esueaza clar)


def _sincronizeaza(dest):
	"""Ce s-a scris ajunge pe stick acum, nu cand vrea nucleul."""
	dest.flush()
	os.fsync(dest.fileno())


def _copiaza(sursa, dest, oprit=None, progres=None):
	"""Copiere in bucati de 1 MiB; `oprit()` adevarat (ecranul s-a inchis) opreste copierea. La fiecare BLOC_SINCRONIZARE
	si la sfarsit, fsync: procentul arata scrierea adevarata pe stick, nu memoria, iar sync-ul de la inceputul simularii
	(ofgwrite -n) nu mai are sute de MB de scris (pe un stick lent statea minute intregi, fara niciun semn pe ecran).
	`progres["gata"]` creste cu fiecare bucata."""
	nesincronizat = 0
	while True:
		if oprit is not None and oprit():
			raise OSError("copierea a fost oprita")
		bucata = sursa.read(BLOC_COPIE)
		if not bucata:
			break
		dest.write(bucata)
		nesincronizat += len(bucata)
		if nesincronizat >= BLOC_SINCRONIZARE:
			_sincronizeaza(dest)
			nesincronizat = 0
		if progres is not None:
			progres["gata"] = progres.get("gata", 0) + len(bucata)
	_sincronizeaza(dest)


def _extrageZip(candidat, tinta, oprit=None, progres=None):
	"""Scoate din zip-ul candidat numai cele patru fisiere ale pachetului (NUME_PACHET) in dosarul `tinta`. Ridica
	OSError/KeyError/zipfile.BadZipFile la orice problema; apelantul le arata. Nucleul Vu+ (kernel_auto.bin) intra in
	dosarul curat ca kernel.bin, numai cu poarta HdsPazaModel.SCRIERE_VUPLUS deschisa."""
	radacina = candidat["radacina_in_zip"]
	if esteVuplus(candidat) and not getattr(HdsPazaModel, "SCRIERE_VUPLUS", False):
		raise OSError("arhiva Vu+: instalarea din meniu este oprita")
	nucleu = candidat.get("nucleu_in_zip") or NUME_KERNEL
	with zipfile.ZipFile(candidat["cale_zip"]) as z:
		originale = {}
		for n in z.namelist():
			originale.setdefault(n.replace("\\", "/"), n)
		alese = [(nume_scurt, originale.get(radacina + (nucleu if nume_scurt == NUME_KERNEL else nume_scurt)))
			for nume_scurt in NUME_PACHET]
		alese = [(scurt, n) for scurt, n in alese if n is not None]
		if progres is not None:
			progres["total"] = sum(z.getinfo(n).file_size for _scurt, n in alese)
		for nume_scurt, nume_in_zip in alese:
			with z.open(nume_in_zip) as sursa, open(os.path.join(tinta, nume_scurt), "wb") as dest:
				_copiaza(sursa, dest, oprit, progres)


def _copiazaDosar(candidat, tinta, oprit=None, progres=None):
	"""Copiaza din dosarul e2/update de pe stick numai cele patru fisiere ale pachetului (NUME_PACHET) in `tinta`."""
	alese = [n for n in NUME_PACHET if os.path.isfile(os.path.join(candidat["cale_update"], n))]
	if progres is not None:
		progres["total"] = sum(os.path.getsize(os.path.join(candidat["cale_update"], n)) for n in alese)
	for nume_scurt in alese:
		with open(os.path.join(candidat["cale_update"], nume_scurt), "rb") as sursa, \
				open(os.path.join(tinta, nume_scurt), "wb") as dest:
			_copiaza(sursa, dest, oprit, progres)


def _pregatesteDosarCurat(candidat, oprit=None, progres=None):
	"""Dosarul curat al pachetului, pe acelasi mediu (pe alt disc, cand stickul e pe numai citire: locLucru):
	<mediu>/.hds-actualizare-extrasa/e2/update, golit si umplut numai cu fisierele pachetului (din zip sau din dosarul e2/update).
	Ruleaza pe un fir separat. Intoarce calea dosarului. `progres`: dict {"total", "gata"} in octeti, citit de ecran."""
	tinta = os.path.join(locLucru(candidat), FOLDER_DEZARHIVARE, *SUBCALE_UPDATE)
	if os.path.isdir(tinta):
		shutil.rmtree(tinta, ignore_errors=True)
	os.makedirs(tinta, exist_ok=True)
	if candidat["tip"] == "zip":
		_extrageZip(candidat, tinta, oprit, progres)
	else:
		_copiazaDosar(candidat, tinta, oprit, progres)
	return tinta


# -------------------------------------------------------------- pasii verificarii, aratati o data pe secunda

PAS_COPIERE, PAS_SUME, PAS_SIMULARE = 1, 2, 3
PASI_VERIFICARE = 3


def _durataText(secunde):
	"""„45 s”, „3 min”: cat a trecut sau cat mai e, rotunjit in sus la minut peste un minut."""
	secunde = max(1, int(secunde + 0.999))
	if secunde < 60:
		return _("%d s") % secunde
	return _("%d min") % ((secunde + 59) // 60)


def _textProcent(progres, trecut):
	"""„45 % (110 din 245 MB). Mai durează cam 2 min.”; procentul numai cand se stie totalul, timpul ramas dupa 3 s."""
	total = int((progres or {}).get("total") or 0)
	gata = min(int((progres or {}).get("gata") or 0), total)
	if total <= 0:
		return ""
	mb = 1024 * 1024
	text = _("%d %% (%d din %d MB).") % (gata * 100 // total, gata // mb, (total + mb - 1) // mb)
	if gata >= total:
		return text
	if trecut >= 3 and gata > 0:
		return text + " " + _("Mai durează cam %s.") % _durataText((total - gata) * trecut / float(gata))
	return text + " " + _("Se măsoară viteza stickului…")


def textPas(pas, progres=None, trecut=0, punct_numai_citire=""):
	"""Textul de sus al ecranului (si mesajul paginii web) cat lucreaza pasul `pas` (PAS_*); `trecut` in secunde."""
	if pas == PAS_COPIERE:
		if punct_numai_citire:
			text = _("Pasul 1 din 3: pe stick se poate numai citi, deci copiez software-ul într-un dosar curat pe „%s”.") % punct_numai_citire
		else:
			text = _("Pasul 1 din 3: se copiază software-ul într-un dosar curat.")
		procent = _textProcent(progres, trecut)
		return text + (" " + procent if procent else "")
	if pas == PAS_SUME:
		text = _("Pasul 2 din 3: se verifică dacă software-ul este întreg (sumele de control).")
		procent = _textProcent(progres, trecut)
		return text + (" " + procent if procent else "")
	# la simulare textul nu se schimba: fereastra lui ofgwrite sta peste interfata si arata ea pasii, iar o redesenare a
	# interfetei in timpul ei poate muta pagina aratata a ecranului
	return _("Pasul 3 din 3: programul de instalare verifică software-ul. Nu se instalează nimic pe receptor.") + " " + \
		_("De obicei durează sub un minut; după %d minute se oprește singură. EXIT o oprește oricând.") % (LIMITA_SIMULARE_S // 60)


# -------------------------------------------------------------- ecranul televizorului dupa o simulare oprita

FBIOGET_VSCREENINFO = 0x4600
FBIOPUT_VSCREENINFO = 0x4601
FBIO_SET_MANUAL_BLIT = 0x40014621  # _IOW('F', 0x21, __u8), ca in lib/gdi/fb.cpp
FB_ACTIVATE_ALL = 64
LOC_ACTIVATE = 84  # in struct fb_var_screeninfo (160 de octeti): dupa 8 campuri, 4 x fb_bitfield si nonstd
CALE_FB = "/dev/fb0"


def citesteEcranul(cale=CALE_FB):
	"""Modul ecranului (struct fb_var_screeninfo) inainte de simulare; None daca nu se poate citi. ofgwrite -n isi pune
	fereastra peste interfata schimband modul (mai multe pagini, alta pagina aratata) si il da inapoi numai cand se
	termina singur."""
	try:
		import fcntl
		fd = os.open(cale, os.O_RDWR)
		try:
			return bytes(fcntl.ioctl(fd, FBIOGET_VSCREENINFO, bytes(160)))
		finally:
			os.close(fd)
	except Exception as e:
		print("[HdsSoftwareUpdate] modul ecranului nu s-a citit: %s" % e)
		return None


def punEcranulLaLoc(salvat, cale=CALE_FB):
	"""Dupa o simulare oprita: modul ecranului de dinainte, ca la sfarsitul obisnuit al lui ofgwrite (close_framebuffer:
	FB_ACTIVATE_ALL, apoi fara blit manual). Nu arunca; True daca a mers."""
	if not salvat or len(salvat) < 160:
		return False
	try:
		import fcntl
		import struct
		date = bytearray(salvat)
		struct.pack_into("=I", date, LOC_ACTIVATE, FB_ACTIVATE_ALL)
		fd = os.open(cale, os.O_RDWR)
		try:
			fcntl.ioctl(fd, FBIOPUT_VSCREENINFO, bytes(date))
			try:
				fcntl.ioctl(fd, FBIO_SET_MANUAL_BLIT, b"\x00")
			except OSError:
				pass
		finally:
			os.close(fd)
		return True
	except Exception as e:
		print("[HdsSoftwareUpdate] modul ecranului nu s-a pus la loc: %s" % e)
		return False


def redeseneazaTotEcranul():
	"""Tot ecranul se redeseneaza la urmatoarea pictare (ca la schimbarea rezolutiei): fereastra lui ofgwrite oprit
	ramane altfel desenata peste interfata, unde ecranul nostru nu acopera (proba pe receptorul de proba, 11.11.2026)."""
	try:
		from enigma import getDesktop
		desktop = getDesktop(0)
		desktop.resize(desktop.size())
		# oprirea din pagina web nu trece prin hide()/show() pe televizor: pictarea se cere aici
		desktop.paint()
	except Exception as e:
		print("[HdsSoftwareUpdate] redesenarea ecranului: %s" % e)


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


def _citesteCmdline(cale=None):
	try:
		with open(cale or CALE_CMDLINE) as f:
			return f.read(4096)
	except (IOError, OSError, ValueError):
		return ""


def campCmdline(cmdline, cheie):
	"""Valoarea primului cuvant "cheie=..." din /proc/cmdline, sau "" """
	for cuvant in (cmdline or "").split():
		if cuvant.startswith(cheie + "="):
			return cuvant[len(cheie) + 1:]
	return ""


def subdosarRadacina(cmdline=None):
	"""rootsubdir= din /proc/cmdline (primul Viper 4K, V10: "linuxrootfs1"), numai litere, cifre si _; "" cand
	lipseste (V20, V30, V40) sau e ciudat. Fara `cmdline` se citeste /proc/cmdline."""
	v = campCmdline(_citesteCmdline() if cmdline is None else cmdline, "rootsubdir")
	return v if re.match(r"^[A-Za-z0-9_]{1,40}$", v) else ""


# UNDE SE SCRIE (USI, 16.11.2026; space71, SatFan 3085, Uclan Ustym 4K PRO): mereu locul care ruleaza acum, citit din
# /proc/cmdline. Pana in 0.7.6 orice radacina pe USB/UUID si orice pornire kexec se opreau cu „Imaginea rulează de pe un
# disc extern”, si pe locurile pornirii multiple unde celelalte imagini scriu fara grija. Argumentele sunt cele folosite de
# celelalte imagini OE-Alliance la scrierea imaginii, citite in ofgwrite 5.0.4 (comiterea retetei noastre, 9ef59e0):
#   - o singura pereche nucleu-sistem: -r -k (ofgwrite isi gaseste singur partitiile);
#   - loc din memorie cu rootsubdir (SF8008, Ustym 4K PRO, primul Viper 4K): -r -k -mN;
#   - loc din memorie al pornirii kexec (Vu+ 4K): -r<partitia din root=> -k -mN. Fara -r<partitie>, la kexec=1 ofgwrite
#     ia radacina din root= de acum (ofgwrite.c, „use kexec rootfs mode”), iar nucleul e fisierul <loc>/zImage;
#   - loc kexec de pe USB/HDD (rootsubdir=<model>/linuxrootfsN, root=/dev/sdXN gasit de initramfs): ca mai sus, plus
#     -s<model>/linuxrootfs, dosarul locului;
#   - loc de pe stick al pornirii multiple cu STARTUP (STARTUP_5/6 ale producatorului pe SF8008 si Ustym 4K PRO:
#     root=/dev/sda2 kernel=/dev/sda1, fara rootsubdir): -r<sda2> -k<sda1> -m0 (m0 = fara verificarea subdosarului).
# Ramane oprit, cu textul de pana acum: radacina pe un disc USB pe un receptor FARA pornire multipla (nu se stie ce
# porneste dupa, iar ofgwrite ar scrie memoria interna, alta imagine decat cea pornita), Recovery-ul kexec (radacina flash
# cu STARTUP*), un loc cu nucleul comun din memorie si sistemul pe USB, si orice forma necunoscuta. Pachetul nu are voie sa
# stea pe partitia in care se scrie (refuzTinta; radacina o pazeste deja Tools/MediuImagine).
_BLOC_EMMC = r"/dev/mmcblk0p[1-9][0-9]*"
_PARTITIE_USB = re.compile(r"^/dev/(sd[a-z])([1-9][0-9]?)$")
_SUBDOSAR_KEXEC_USB = re.compile(r"^(?:([A-Za-z0-9_-]{1,40})/)?linuxrootfs([1-9][0-9]?)$")
_EXTERNE = ("/dev/sd", "/dev/nvme", "/dev/mmcblk1", "/dev/disk/", "/dev/mapper/", "UUID=", "PARTUUID=")


def _textDiscExtern():
	return _("Imaginea rulează de pe un disc extern. Pornește imaginea din memoria internă și verifică din nou.")


def _textLocNesigur():
	return _("Slotul pornit din memoria internă nu poate fi stabilit sigur. Instalarea este oprită.")


def _pornireMultipla():
	"""True pe receptoarele cu pornire multipla (bootoptions cu STARTUP_N, kexec, schema flag): SystemInfo["HdsMultiboot"],
	socotit la pornire de Components/HdsPornireMultipla.disponibil. Orice eroare: False (deci refuz)."""
	try:
		from Components.SystemInfo import SystemInfo
		return bool(SystemInfo.get("HdsMultiboot"))
	except Exception as eroare:
		print("[HdsSoftwareUpdate] pornirea multipla: %s" % eroare)
		return False


def _tintaKexec(p):
	"""Locul kexec care ruleaza acum (kexec=1): din memorie sau de pe USB/HDD. ValueError pentru Recovery si forme necunoscute."""
	sub, root, nucleu = p.get("rootsubdir", ""), p.get("root", ""), p.get("kernel", "")
	# unele initramfs nu lasa kernel= in linia de comanda (Components/HdsPornireMultipla._acumKexec); cand e, e chiar al locului
	nucleu_bun = nucleu.lstrip("/") in ("", sub + "/zImage")
	if p.get("rootfstype", "ext4") == "ext4" and nucleu_bun:
		m = re.fullmatch(r"linuxrootfs([1-9])", sub)
		if m and re.fullmatch(_BLOC_EMMC, root):
			return {"fel": "kexec", "argumente": "-r%s -k -m%s" % (root[len("/dev/"):], m.group(1)), "subdosar": sub,
				"radacina": root, "nucleu": "/oldroot_remount/%s/zImage" % sub, "loc": m.group(1)}
		m = _SUBDOSAR_KEXEC_USB.fullmatch(sub)
		if m and _PARTITIE_USB.fullmatch(root):
			argumente = "-r%s -k" % root[len("/dev/"):]
			if m.group(1):
				argumente += " -s%s/linuxrootfs" % m.group(1)
			return {"fel": "kexec_usb", "argumente": "%s -m%s" % (argumente, m.group(2)), "subdosar": sub,
				"radacina": root, "nucleu": "/oldroot_remount/%s/zImage" % sub, "loc": m.group(2)}
	if root.startswith(_EXTERNE):
		raise ValueError(_textDiscExtern())
	raise ValueError(_textLocNesigur())


# GARDA PORNIRII (rapoartele pornirii 761249 si 486541, Octagon SF8008 cu 11 locuri pe stick): la locul de
# pe stick, -r<sdaM> -k<sdaK> vin direct din root= si kernel= ale liniei de comanda, iar programul de scriere scrie exact
# acele partitii. Unealta altei imagini poate lasa in STARTUP nucleul unui loc cu sistemul altuia (kernel=/dev/sda3 al lui
# STARTUP_6 cu root=/dev/sda10 al lui STARTUP_9); daca interfata porneste asa, instalarea ar pune nucleul nostru peste
# nucleul locului 6, iar simularea ar trece. Scrierea porneste deci numai cand perechea de acum e chiar a unui STARTUP_N,
# citite numai (Components/HdsPornireMultipla.startupuriCitite si locPornit). Fara STARTUP_N citite: refuz. STARTUP nu se
# repara aici (scriere pe partitia de pornire, hotararea e separata).
class RefuzPornire(ValueError):
	"""Refuzul garzii pornirii: textul pentru om si diagnosticul (HdsPornireMultipla.locPornit, plus cheia citit)."""

	def __init__(self, text, diagnostic=None):
		ValueError.__init__(self, text)
		self.diagnostic = diagnostic or {}


def _textPornireNeclara():
	return _("Pornirea receptorului este neclară. Instalarea este oprită.")


def _startupuriPornire():
	"""STARTUP_N de pe partitia de pornire, numai citite (HdsPornireMultipla.startupuriCitite); None cand nu se pot citi
	sau la orice eroare. Probele o inlocuiesc, ca pe _pornireMultipla."""
	try:
		from Components import HdsPornireMultipla
		return HdsPornireMultipla.startupuriCitite()
	except Exception as eroare:
		print("[HdsSoftwareUpdate] fisierele de pornire: %s" % eroare)
		return None


_gardaJurnal = [None]


def _jurnalGarda(text):
	"""Un rand in jurnalul interfetei, numai cand se schimba (fereastra Imagine noua de pe internet intreaba locul la fiecare
	jumatate de secunda)."""
	if text != _gardaJurnal[0]:
		_gardaJurnal[0] = text
		print("[HdsSoftwareUpdate] garda pornirii: %s" % text)


def _gardaPornireStick(p):
	"""Locul de pe stick (_tintaLocUsb): trece numai cand nucleul si sistemul pornite acum sunt ale aceluiasi STARTUP_N;
	altfel RefuzPornire cu motivul pentru om (vezi GARDA PORNIRII)."""
	fisiere = _startupuriPornire()
	if not fisiere:
		_jurnalGarda("fisierele STARTUP_N nu se pot citi, deci nu se scrie")
		raise RefuzPornire(_textPornireNeclara(), {"citit": False})
	try:
		from Components import HdsPornireMultipla
		d = dict(HdsPornireMultipla.locPornit(p, fisiere), citit=True)
		pe_stick = _(HdsPornireMultipla.PE_STICK)
	except Exception as eroare:
		_jurnalGarda("%s" % eroare)
		raise RefuzPornire(_textPornireNeclara(), {"citit": False})
	_jurnalGarda("kernel=%s root=%s; locurile nucleului %s, ale sistemului %s, locul %s; STARTUP_N fara forma stiuta %s" % (
		p.get("kernel", ""), p.get("root", ""), d["nucleu"], d["sistem"], d["loc"] or "-", d.get("fara_forma", [])))
	if d["loc"]:
		return d
	if d["amestec"]:
		# doua propozitii: ce s-a intamplat si ce face omul (fereastra de pe internet le pune in doua casete)
		locuri = {"nucleu": d["nucleu"][0], "sistem": d["sistem"][0]}
		d["motiv"] = _("Instalarea este oprită: receptorul a pornit cu nucleul locului %(nucleu)s și cu sistemul locului "
			"%(sistem)s, deci ar scrie peste nucleul locului %(nucleu)s.") % locuri
		d["ajutor"] = _("Alege locul %(sistem)s la Meniu > Standby și repornire > Repornește în altă imagine, apoi încearcă "
			"din nou.") % locuri
		raise RefuzPornire("%s %s" % (d["motiv"], d["ajutor"]), d)
	raise RefuzPornire("%s %s." % (pe_stick, _("Instalarea este oprită")), d)


def _tintaLocUsb(p, multiboot):
	"""Locul de pe stick al pornirii multiple cu STARTUP (root=/dev/sdXM kernel=/dev/sdXK pe acelasi disc, fara rootsubdir),
	numai pe un receptor cu pornire multipla; None altfel."""
	root, nucleu = p.get("root", ""), p.get("kernel", "")
	r, k = _PARTITIE_USB.fullmatch(root), _PARTITIE_USB.fullmatch(nucleu)
	if "rootsubdir" in p or p.get("rootfstype", "ext4") != "ext4" or not r or not k or r.group(1) != k.group(1) or \
			r.group(2) == k.group(2):
		return None
	if not (_pornireMultipla() if multiboot is None else multiboot):
		return None
	_gardaPornireStick(p)
	return {"fel": "usb", "argumente": "-r%s -k%s -m0" % (root[len("/dev/"):], nucleu[len("/dev/"):]), "subdosar": "",
		"radacina": root, "nucleu": nucleu, "loc": ""}


def _radacinaMutataDeInitramfs(root, mounts="/proc/mounts", oaspete="/etc/.guest"):
	"""USB1 (27.11.2026): ZGEMMA H8.2H Plus / SE pornit de pe stick. Initramfs-ul nucleului din mtd8 citeste STARTUP de pe
	stick si muta radacina pe stick (ext4, linuxrootfsN), dar /proc/cmdline ramane root=ubi0:rootfs. Fara paza asta,
	instalarea pornita din imaginea de pe stick ar scrie memoria interna (mtd8, mtd9). True cand linia de comanda spune
	o radacina ubi, dar / nu e ubifs, sau cand initramfs-ul a pus /etc/.guest."""
	if not root.startswith("ubi"):
		return False
	if os.path.exists(oaspete):
		return True
	tip = ""
	try:
		with open(mounts) as f:
			for rand in f:
				c = rand.split()
				if len(c) >= 3 and c[1] == "/":
					tip = c[2]
	except (IOError, OSError):
		return False
	return bool(tip) and tip not in ("ubifs", "rootfs")


def tintaScrierii(cmdline, multiboot=None):
	"""Unde scrie instalarea: locul care ruleaza acum (vezi mai sus). Intoarce {"fel", "argumente", "subdosar", "radacina",
	"nucleu", "loc"}; fel: "unic", "memorie", "kexec", "kexec_usb", "usb". ValueError cu textul pentru om la o pornire
	nesigura. `multiboot`: pornirea multipla a receptorului (None = SystemInfo, citit numai cand trebuie)."""
	chei = ("kernel", "root", "rootsubdir", "kexec", "rootfstype")
	campuri = [c.split("=", 1) for c in (cmdline or "").split() if "=" in c]
	if any(sum(k == cheie for k, _v in campuri) > 1 for cheie in chei):
		raise ValueError(_("Pornirea receptorului este neclară. Instalarea este oprită."))
	p = dict(campuri)
	if p.get("kexec") == "1":
		return _tintaKexec(p)
	root = p.get("root", "")
	if _radacinaMutataDeInitramfs(root):
		raise ValueError(_textDiscExtern())
	if any(d.startswith(_EXTERNE) for d in (root, p.get("kernel", ""))):
		t = _tintaLocUsb(p, multiboot)
		if t:
			return t
		raise ValueError(_textDiscExtern())
	if "rootsubdir" not in p:
		return {"fel": "unic", "argumente": "-r -k", "subdosar": "", "radacina": root, "nucleu": p.get("kernel", ""), "loc": ""}
	m = re.fullmatch(r"linuxrootfs([1-4])", p["rootsubdir"])
	if not m or not re.fullmatch(_BLOC_EMMC, root) or not re.fullmatch(_BLOC_EMMC, p.get("kernel", "")) or \
			p.get("kernel") == root or p.get("rootfstype", "ext4") != "ext4":
		raise ValueError(_textLocNesigur())
	return {"fel": "memorie", "argumente": "-r -k -m%s" % m.group(1), "subdosar": p["rootsubdir"], "radacina": root,
		"nucleu": p["kernel"], "loc": m.group(1)}


def _argumenteOfgwrite(cmdline, multiboot=None):
	"""Argumentele lui ofgwrite pentru locul care ruleaza acum (tintaScrierii); ValueError la pornire nesigura."""
	return tintaScrierii(cmdline, multiboot)["argumente"]


def _dispozitivReal(cale):
	try:
		return os.path.normpath(os.path.realpath(cale))
	except (OSError, ValueError):
		return cale


def refuzTinta(t, cale_pachet, verifica=None):
	"""Textul refuzului cand pachetul sta chiar pe o partitie in care se scrie (nucleul unui loc de pe stick: sda1 la
	STARTUP_5); None altfel. Radacina locului o refuza deja Tools/MediuImagine (acelasi dispozitiv cu /)."""
	tinte = set(_dispozitivReal(d) for d in (t.get("radacina"), t.get("nucleu")) if d and d.startswith("/dev/"))
	if not tinte:
		return None
	try:
		_permis, _motiv, dispozitiv, _punct = (verifica or verificaMediuScriere)(cale_pachet)
	except Exception as eroare:
		print("[HdsSoftwareUpdate] partitia pachetului: %s" % eroare)
		dispozitiv = None
	if not dispozitiv or _dispozitivReal(dispozitiv) not in tinte:
		return None
	return _("Instalarea este oprită: software-ul stă chiar pe partiția în care se instalează (%s). Copiază-l pe alt stick și încearcă din nou. Nu s-a instalat nimic.") % dispozitiv


def _tinteDinIesire(randuri):
	"""{"kernel": set, "rootfs": set}: toate destinatiile anuntate de ofgwrite (Found/Using cmdLine ... device, Using X as
	... device), din randurile deja scrise cu litere mici."""
	tinte = {"kernel": set(), "rootfs": set()}
	for rand in randuri:
		m = re.fullmatch(r"(?:found|using) cmdline (kernel|rootfs) device: (\S+)", rand)
		if m:
			tinte[m.group(1)].add(m.group(2))
		m = re.fullmatch(r"using (\S+) as (kernel|rootfs) device", rand)
		if m:
			tinte[m.group(2)].add(m.group(1))
	return tinte


def _simulareLocPornireMultipla(randuri, t):
	"""Locurile kexec si locul de pe stick (tintaScrierii): simularea trebuie sa numeasca exact nucleul si radacina locului
	care ruleaza acum, si nimic altceva, iar radacina de acum sa fie chiar aceea (se scrie locul pornit)."""
	if _tinteDinIesire(randuri) != {"kernel": {t["nucleu"].lower()}, "rootfs": {t["radacina"].lower()}}:
		return False
	if "current rootfs is: " + t["radacina"].lower() not in randuri:
		return False
	sloturi = set(r for r in randuri if r.startswith("flashing multiboot partition "))
	subdosare = set(r for r in randuri if r.startswith("current root sub dir is:"))
	if t["fel"] == "usb":
		return "flashing without rootsubdir check" in randuri and not sloturi and subdosare == {"current root sub dir is:"}
	return "kexec mode is: 1" in randuri and sloturi == {"flashing multiboot partition " + t["loc"]} and \
		subdosare == {"current root sub dir is: " + t["subdosar"].lower()}


def _simulareAratacorect(iesire, cmdline=None, multiboot=None):
	"""Verificare PROPRIE, din text, ca ofgwrite a recunoscut pachetul — NU se are incredere in
	textul lui de "succes" (identic la simulare si la scriere reala). Cere gasirea
	explicita a kernelului, rootfs-ului SI a dispozitivelor tinta, fara nicio mentiune de eroare.
	Cu rootsubdir=, destinatiile trebuie sa fie chiar kernel= si root=.
	Numarul dat prin -m trebuie sa corespunda subdosarului pornit. Locurile kexec si cel de pe stick: _simulareLocPornireMultipla."""
	txt = (iesire or "").lower()
	are_kernel = "found kernel file" in txt
	are_rootfs = any(s in txt for s in (
		"found rootfs file", "found ext4 rootfs", "found ext3 rootfs", "found ubi rootfs", "found ubifs rootfs"
	))
	cmdline = _citesteCmdline() if cmdline is None else cmdline
	try:
		t = tintaScrierii(cmdline, multiboot)
	except ValueError:
		return False
	subdosar = subdosarRadacina(cmdline)
	if t["fel"] in ("kexec", "kexec_usb", "usb"):
		are_dispozitive = _simulareLocPornireMultipla([r.strip() for r in txt.splitlines()], t)
	elif subdosar:
		kernel, radacina = campCmdline(cmdline, "kernel"), campCmdline(cmdline, "root")
		randuri = [r.strip() for r in txt.splitlines()]
		tinte = {"kernel": set(), "rootfs": set()}
		for rand in randuri:
			m = re.fullmatch(r"(?:found|using) cmdline (kernel|rootfs) device: (\S+)", rand)
			if m:
				tinte[m.group(1)].add(m.group(2))
			m = re.fullmatch(r"using (\S+) as (kernel|rootfs) device", rand)
			if m:
				tinte[m.group(2)].add(m.group(1))
		sloturi = [r for r in randuri if r.startswith("flashing multiboot partition ")]
		# Cu -m, subdosarul tinta este linuxrootfsN. Randul Current arata pornirea.
		# Forma veche Using cmdLine ramane citibila pentru probele deja salvate.
		slot_corect = set(sloturi) == {"flashing multiboot partition " + subdosar[-1]} or \
			(not sloturi and "using cmdline kernel device: " + kernel.lower() in randuri)
		subdosare = {r for r in randuri if r.startswith("current root sub dir is:")}
		are_dispozitive = tinte == {"kernel": {kernel.lower()}, "rootfs": {radacina.lower()}} and \
			slot_corect and subdosare == {"current root sub dir is: " + subdosar.lower()}
	else:
		are_dispozitive = "found cmdline kernel device" in txt and "found cmdline rootfs device" in txt
	are_eroare = ("error" in txt) or ("not found" in txt) or ("missing" in txt) or ("no such file" in txt)
	are_eroare = are_eroare or "flashing currently not running image" in txt
	return bool(are_kernel and are_rootfs and are_dispozitive and not are_eroare)


# Ce spune ofgwrite la simulare, pe intelesul omului (Eduard, 04.11.2026: „tot ce spune ăla să fie translatat în limbajul
# uman”). Randurile fara rost pentru om nu se arata; ce nu e in tabel ramane cum e, la sfarsit, ca sa nu se piarda o eroare.
_ANALIZA_FARA_ROST = re.compile(
	r"^(FBIO_|ofgwrite Utility|Author:|Based upon:|Use at your own risk|Don't use it|Flashing (rootfs|kernel)|Flash rootfs|Untar:|"
	r"Delete rootfs|Creating directory|"
	r"Searching image files|Found mounted |Found /proc/mtd|Device:|Using (kernel|rootfs) mtd device|Read /proc/cmdline|"
	r"Kexec mode|Chkroot mode|Current (rootfs|kernel|root sub dir) is:|Syncing filesystem|daemonize|Successfully|Checking E2|"
	r"E2 is stopped|Boxname detect|Flashing multiboot partition|Flashing without rootSubDir|Using user defined slot)", re.I)


def textNerecunoscut():
	return _("Software-ul nu a fost recunoscut corect de programul de instalare, deci nu se instalează. Pe receptor nu s-a schimbat nimic.")


def textOaspete():
	return _("Imaginea rulează ca oaspete într-un manager de multi-imagine. Instalarea de aici este oprită pentru a proteja imaginile. Folosește managerul din care ai pornit imaginea. Nu s-a scris nimic pe receptor.")


# NEO6 (NBT, TODO 16.11 06:05): pornita ca oaspete in NeoBoot, imaginea are /.multinfo in radacina (acelasi semn ca
# Components/HdsCopieImagine._pornireFaraPartitie). ofgwrite refuza oricum, dar omul afla numai dupa simulare, sub „A gasit
# o eroare si s-a oprit (codul 1)”. Acum semnul se vede pe firul separat, inainte de dosarul curat si de simulare, iar omul
# primeste direct textOaspete() (pe televizor si in pagina web, prin aceeasi metoda a ecranului).
RADACINA_NEOBOOT = "/"
OASPETE = "oaspete"


def pornitCaOaspete(radacina=None):
	"""True cand imaginea ruleaza ca oaspete in NeoBoot (/.multinfo); citire de fisier, numai pe firul separat."""
	return os.path.exists(os.path.join(radacina or RADACINA_NEOBOOT, ".multinfo"))


def pregatesteDacaNuEOaspete(candidat, oprit=None, progres=None):
	"""OASPETE sub NeoBoot (nimic copiat), altfel dosarul curat al pachetului (_pregatesteDosarCurat)."""
	if pornitCaOaspete():
		return OASPETE
	return _pregatesteDosarCurat(candidat, oprit=oprit, progres=progres)


def _analizaRand(rand):
	"""Propozitia pentru un rand al lui ofgwrite, "" daca nu e nimic de spus omului, None daca randul nu e cunoscut"""
	m = re.match(r"Found (?:tar\.xz )?(kernel|rootfs|nfi) file: (.*)$", rand, re.I)
	if m:
		nume = os.path.basename(m.group(2).strip())
		if m.group(1).lower() == "kernel":
			return _("A găsit nucleul sistemului (%s).") % nume
		return _("A găsit sistemul (%s).") % nume
	m = re.match(r"Found (\w+) rootfs$", rand, re.I)
	if m:
		return _("Programul poate instala sistemul în acest format (%s).") % m.group(1)
	m = re.match(r"Found mountpoint for rootfs file: (.*)$", rand, re.I)
	if m:
		return _("Fișierele stau pe stick (%s).") % os.path.basename(m.group(1).strip())
	m = re.match(r"(?:Found|Using) cmdline (kernel|rootfs) device: (\S+)", rand, re.I)
	gpt = re.fullmatch(r"Using (\S+) as (kernel|rootfs) device", rand, re.I)
	if m or gpt:
		fel, dispozitiv = m.groups() if m else (gpt.group(2), gpt.group(1))
		loc = os.path.basename(dispozitiv)
		# locul kexec: nucleul e fisierul /oldroot_remount/<loc>/zImage; locul de pe stick: partitii /dev/sd*
		kexec = re.match(r"/oldroot_remount/(.+)/zImage$", dispozitiv, re.I)
		if kexec and fel.lower() == "kernel":
			return _("Nucleul se va instala în dosarul %s, lângă sistem.") % kexec.group(1)
		if dispozitiv.startswith("/dev/sd"):
			if fel.lower() == "kernel":
				return _("Nucleul se va instala pe discul USB, pe partiția %s.") % loc
			return _("Sistemul se va instala pe discul USB, pe partiția %s.") % loc
		if fel.lower() == "kernel":
			return _("Nucleul se va instala în memoria internă, pe partiția %s.") % loc
		return _("Sistemul se va instala în memoria internă, pe partiția %s.") % loc
	jos = rand.lower()
	if 'the image runs from neoboot' in jos:
		return textOaspete()
	for semn, text in (
			("no kernel file was found", _("Nu a găsit nucleul sistemului în acest software.")),
			("no rootfs file was found", _("Nu a găsit sistemul în acest software.")),
			("no kernel device was found", _("Nu a găsit locul nucleului în memoria internă.")),
			("no rootfs device was found", _("Nu a găsit locul sistemului în memoria internă.")),
			("rootfs type is unknown", _("Nu recunoaște formatul sistemului.")),
			("kernel file is bigger", _("Nucleul este prea mare pentru locul lui din memoria internă.")),
			("rootfs file is bigger", _("Sistemul este prea mare pentru locul lui din memoria internă."))):
		if semn in jos:
			return text
	return "" if _ANALIZA_FARA_ROST.match(rand) else None


def analizaPeIntelesulOmului(iesire, cod, recunoscut=True):
	"""Textul pentru „Vezi ce a analizat ofgwrite”: rezultatul, ce a gasit, ce nu e tradus si ca nu s-a scris nimic"""
	randuri, necunoscute = [], []
	for rand in (iesire or "").splitlines():
		rand = rand.strip()
		if not rand:
			continue
		text = _analizaRand(rand)
		if text is None:
			necunoscute.append(rand)
		elif text and text not in randuri:
			randuri.append(text)
	if cod != 0:
		sus = _("A găsit o eroare și s-a oprit (codul %d).") % cod
	elif recunoscut:
		sus = _("Nu a găsit nicio eroare.")
	else:
		sus = textNerecunoscut()
	rez = [sus] + ["•  " + r for r in randuri]
	if necunoscute:
		rez += ["", _("Alte mesaje ale programului, netraduse:")] + necunoscute
	return "\n".join(rez + ["", _("Aceasta a fost numai o verificare: nu s-a instalat nimic pe receptor.")])


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
		self._reparari = []   # randurile „Repară” din capul listei: [{"disc", "nume", "text"}]
		# USB6: stickurile cu tipul partitiei gresit (tipuriGresite, citite pe un fir separat)
		self._tipuri = []
		self._lucrareTip = None
		self._notaTip = ""   # textul ultimei reparari, pastrat peste redesenarea listei
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
		self._analizaVazuta = False
		# marimea cartelelor pana la _pregatesteLista (citita din skin)
		self._latimeRand, self._inaltimeRand, self._scaraRand, self._margineRand = 1688, 124, 1.0, 24
		self._culoriRand = _culoriLista()
		self.onClose.append(self._laInchidere)

		self["detaliu"] = Label(_("Se caută software de receptor pe stick și pe disc…"))
		from enigma import eListboxPythonMultiContent
		self["lista"] = MenuList([], content=eListboxPythonMultiContent)
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
				"yellow": self._galben,
				"up": self._sus,
				"down": self._jos,
			}, -2)

		self.onLayoutFinish.append(self._pregatesteLista)
		self.onLayoutFinish.append(self._reincarca)
		getattr(self, "onLayoutFinish", []).append(self._cozileDetaliului)

	def _pregatesteLista(self):
		"""Fonturile si marimea cartelelor, din latimea listei din skin (pe tema HD Satelit 1712 px, la 1920 pe ecran).
		Marimea textului (Marimea fonturi) creste si literele, si cartela."""
		from enigma import getDesktop, gFont
		lista = self["lista"]
		try:
			import skin
			p = int(skin.getFontScalePercent())
		except Exception:
			p = 100
		scara = getDesktop(0).size().width() / 1920.0
		f = scara * p / 100.0
		self._inaltimeRand = int(123 * f)     # 5 cartele incap in lista de 616 px a temei, fara bara de derulare
		lista.l.setFont(0, gFont(skin.fontHds("Regular"), int(34 * f)))
		lista.l.setFont(1, gFont(skin.fontHds("Regular"), int(25 * f)))
		lista.l.setFont(2, gFont(skin.fontHds("Bold"), int(27 * f)))
		lista.l.setItemHeight(self._inaltimeRand)
		self._scaraRand = f
		latime = lista.instance.size().width()
		self._margineRand = int(24 * scara)
		self._latimeRand = latime - self._margineRand

	def _randPachet(self, c):
		return _intrariPachet(c, self._latimeRand, self._inaltimeRand, self._scaraRand, self._culoriRand, self._margineRand)

	def _randSimplu(self, text):
		return _intrariSimple(text, self._latimeRand, self._inaltimeRand, self._scaraRand, self._culoriRand, self._margineRand)

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

	def _detaliuRand(self):
		"""Sus in lista, tot textul pentru randul ales, pe mai multe randuri, ca sa nu se taie: pe cartela nu incape."""
		r = self._reparareSelectata()
		c = self._candidatSelectat()
		if r is not None:
			self["detaliu"].setText(r["text"])
		elif c is not None and c.get("fel") != FEL_REA and faraLoc(c):
			self["detaliu"].setText(textStickCazut(c))
		elif c is not None and c.get("fel") == FEL_STRAINA:
			self["detaliu"].setText(textImagineStraina(c))
		elif self._candidati:
			self["detaliu"].setText(textGasite(len(self._candidati)))
		if self._candidati:
			repara = r is not None or (c is not None and c.get("fel") != FEL_REA and bool(c.get("disc_reparat")))
			self._buton("key_green", _("Repară tipul partiției") if r is not None and r.get("tip") else (
				_("Repară stickul") if repara else _("Verifică software-ul")))
		elif r is not None:
			self._buton("key_green", _("Repară tipul partiției") if r.get("tip") else _("Repară stickul"))
		elif self._reparari:
			self._buton("key_green", "")

	def _sus(self):
		if not self._ocupat and self._faza == "lista":
			self["lista"].up()
			self._detaliuRand()
		elif self._faza in ("verificare", "rezultat"):
			# HDSatelit: iesirea simularii poate fi mai lunga decat caseta ei
			self["iesire"].pageUp()

	def _jos(self):
		if not self._ocupat and self._faza == "lista":
			self["lista"].down()
			self._detaliuRand()
		elif self._faza in ("verificare", "rezultat"):
			self["iesire"].pageDown()

	def _galben(self):
		"""Tasta galbena: dupa simulare arata sau ascunde ce a analizat ofgwrite; in rest reface lista."""
		if self._scriereRealaPornita:
			return
		if self._faza == "rezultat":
			self._arataAnaliza(not self._analizaVazuta)
		else:
			self._reincarca()

	def _arataAnaliza(self, arata):
		"""Ce a analizat ofgwrite se vede numai cand o cere omul (Eduard, 04.11.2026)."""
		self._analizaVazuta = arata
		if arata:
			self["lista"].hide()
			self["iesire"].show()
			self._buton("key_yellow", _("Ascunde ce a analizat ofgwrite"))
		else:
			self["iesire"].hide()
			self["lista"].show()
			self._buton("key_yellow", _("Vezi ce a analizat ofgwrite"))

	def _inapoi(self):
		"""Inapoi / EXIT. Dupa simulare intoarce la lista. In timpul copierii in dosarul curat si al sumelor (fir separat)
		inchide ecranul: _laInchidere opreste firul la urmatoarea bucata. In timpul simularii (ofgwrite -n, nu scrie
		nimic) o opreste si intoarce la lista."""
		if self._ocupat and self._faza == "verificare":
			self._oprireSimulare()
			return
		if self._faza == "rezultat" and not self._scriereRealaPornita:
			self._reincarca()
			return
		self._console.killAll()
		self.close()

	def _laInchidere(self):
		self._opreste = True
		self._opresteePas()
		lucrare = self._lucrare
		if self._lucrare is not None:
			self._lucrare.opreste()
			self._lucrare = None
		if getattr(self, "_lucrareTip", None) is not None:
			self._lucrareTip.opreste()
			self._lucrareTip = None
		if not self._scriereRealaPornita:
			elibereazaDupaLucrare(self, lucrare)

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
		asazaPachete(self._candidati)
		self["lista"].setList(self._randuriLista())
		self["lista"].moveToIndex(0)

	# -------------------------------------------------------------- faza 1: cautare

	def _reincarca(self):
		"""Lista imaginilor; ultimul rand, „Caută din nou software de receptor”, reface lista cu OK (ca tasta galbena)."""
		if self._ocupat:
			return
		elibereazaActualizarea(self)
		self._faza = "lista"
		self["iesire"].hide()
		self["lista"].show()
		self["detaliu"].setText(_("Se caută software de receptor pe stick și pe disc…"))
		eroare_cautare = None
		try:
			self._candidati = cautaCandidati()
		except Exception as eroare:
			self._candidati = []
			eroare_cautare = eroare
		self._reparari = self._randuriReparare()
		cauta_din_nou = self._randSimplu(_("Caută din nou software de receptor"))
		self._arataLista(eroare_cautare, cauta_din_nou)
		self._pornesteTipuri()

	def _arataLista(self, eroare_cautare=None, cauta_din_nou=None):
		"""Lista si textul de sus, din self._candidati si self._reparari (si dupa verificarea tipului partitiei)."""
		if cauta_din_nou is None:
			cauta_din_nou = self._randSimplu(_("Caută din nou software de receptor"))
		if self._candidati:
			self["lista"].setList(self._randuriLista())
			self["lista"].moveToIndex(0)
			self["detaliu"].setText(
				textGasite(len(self._candidati))
			)
			self._buton("key_green", _("Verifică software-ul"))
			if self._reparari:
				self._detaliuRand()
		else:
			self["lista"].setList([self._randReparare(r) for r in self._reparari] +
				[self._randSimplu(_("Nu am găsit software de receptor pe stick sau pe disc.")), cauta_din_nou])
			self["lista"].moveToIndex(0)
			if self._reparari:
				self._detaliuRand()
			elif eroare_cautare is not None:
				self["detaliu"].setText(_("Eroare la căutare: %s") % eroare_cautare)
			else:
				self["detaliu"].setText(
					_("Pune un stick cu software de receptor: arhiva .zip de pe site sau dosarul e2/update cu kernel.bin și "
					  "rootfs.tar.bz2. Apoi apasă OK pe „Caută din nou software de receptor”.")
				)
			if not self._reparari:
				self._buton("key_green", "")
		self._buton("key_yellow", _("Reîncarcă"))

	def _randuriReparare(self):
		"""Cate un rand „Repară” pentru fiecare stick pe numai citire cu un pachet care s-ar putea instala si fara alt loc;
		inaintea lor, cate unul pentru fiecare stick cu tipul partitiei gresit (USB6, cu "tip")."""
		rez = []
		if getattr(self, "_tipuri", None):
			rez = [{"disc": t["disc"], "nume": t.get("punct") or t["disc"], "text": textTipGresit(t), "tip": t}
				for t in self._tipuri]
		for c in self._candidati:
			if c.get("fel") != FEL_REA and faraLoc(c) and c.get("disc_reparat") and not any(r["disc"] == c["disc_reparat"] for r in rez):
				rez.append({"disc": c["disc_reparat"], "nume": numeMediu(c), "text": textStickCazut(c)})
		return rez

	def _randReparare(self, r):
		if r.get("tip"):
			return self._randSimplu(textRandTip(r["nume"]))
		return self._randSimplu(_("Repară „%s”") % r["nume"])

	def _randuriLista(self):
		return [self._randReparare(r) for r in self._reparari] + [self._randPachet(c) for c in self._candidati] + \
			[self._randSimplu(_("Caută din nou software de receptor"))]

	# -------------------------------------------------------------- tipul partitiei de pe stick (USB6)

	def _pornesteTipuri(self):
		"""Verificarea tipului partitiei pe stickurile montate, pe un fir separat (tipuriGresite);
		lista mediilor se ia aici, pe firul enigma2."""
		if self._lucrareTip is not None:
			self._lucrareTip.opreste()
			self._lucrareTip = None
		try:
			puncte = [d.mountpoint for d in _discuriMontate()]
		except Exception as eroare:
			print("[HdsSoftwareUpdate] stickurile pentru tipul partitiei: %s" % eroare)
			return
		self._lucrareTip = HdsPazaModel.LucrareFundal(lambda: tipuriGresite(puncte), self._dupaTipuri)

	def _dupaTipuri(self, rezultat, eroare):
		self._lucrareTip = None
		if eroare:
			print("[HdsSoftwareUpdate] tipul partitiei: %s" % eroare)
		tipuri = rezultat or []
		nota, self._notaTip = getattr(self, "_notaTip", ""), ""
		if tipuri == self._tipuri or self._ocupat or self._faza != "lista":
			return
		self._tipuri = tipuri
		self._reparari = self._randuriReparare()
		self._arataLista()
		if nota:
			self["detaliu"].setText(nota)

	def _reparaTip(self, info):
		"""Un singur OK: scrie octetul tipului pe un fir separat, apoi citeste lista din nou (si verifica din nou tipul)."""
		if self._ocupat:
			return
		if self._lucrareTip is not None:
			self._lucrareTip.opreste()
		self._ocupat = True
		self["detaliu"].setText(_("Repar tipul partiției de pe stick…"))

		def gata(rezultat, eroare):
			self._lucrareTip = None
			self._ocupat = False
			bun = bool(rezultat and rezultat[0])
			text = rezultat[1] if rezultat else _("Tipul partiției nu s-a putut schimba: %s") % eroare
			# dupa o reparare reusita randul dispare; dupa una nereusita ramane, iar verificarea din nou (aceleasi date)
			# nu mai redeseneaza lista, deci textul erorii ramane sus
			if bun:
				self._tipuri = []
			self._notaTip = text
			self._reincarca()
			self["detaliu"].setText(text)
		self._lucrareTip = HdsPazaModel.LucrareFundal(lambda: reparaTip(info), gata)

	def _reparareSelectata(self):
		index = self["lista"].getSelectionIndex()
		if 0 <= index < len(self._reparari):
			return self._reparari[index]
		return None

	def _candidatSelectat(self):
		index = self["lista"].getSelectionIndex() - len(self._reparari)
		if self._candidati and 0 <= index < len(self._candidati):
			return self._candidati[index]
		return None

	def _repara(self, disc):
		"""Un singur OK: aceeasi lucrare si acelasi ecran de asteptare ca randul „Repară” din Locul inregistrarilor."""
		from Screens.HdsLocInregistrari import pornesteReparare
		pornesteReparare(self.session, disc, self["detaliu"].setText, self._dupaReparare)

	def _dupaReparare(self, reusit=None):
		from Screens.HdsLocInregistrari import textDupaReparare
		self._reincarca()
		text = textDupaReparare(reusit)
		if text:
			# verificarea n-a mers, a fost oprita sau a trecut termenul (HdsDiscuri.opresteLucru): ce face omul mai departe
			if reusit is False:
				text += "\n" + _("Dacă stickul nu se repară, pune alt stick (sau formatează-l pe calculator, cu FAT32), "
					"copiază din nou arhiva de pe site și încearcă iar.")
			self["detaliu"].setText(text)

	# -------------------------------------------------------------- faza 2: alegere si verificare directa

	def _intreaba(self, callback, text, titlu, da, implicit_da, randuri):
		"""O intrebare cu „Da” / „Nu” in fereastra ei (Screens/HdsPazaModel.HdsPazaModelIntrebare)."""
		from Screens.HdsPazaModel import HdsPazaModelIntrebare
		self.session.openWithCallback(callback, HdsPazaModelIntrebare, text, titlu, da=da, implicit_da=implicit_da,
			randuri_mesaj=randuri[0], randuri_tehnic=randuri[1])

	def _ok(self):
		if self._ocupat:
			return
		if self._faza == "lista":
			reparare = self._reparareSelectata()
			if reparare is not None:
				if reparare.get("tip"):
					self._reparaTip(reparare["tip"])
				else:
					self._repara(reparare["disc"])
				return
			candidat = self._candidatSelectat()
			if candidat is None:
				# „Caută din nou software de receptor” (sau randul „Nu am găsit...”)
				self._reincarca()
				return
			self._semnVerificat = None
			if candidat.get("fel") != FEL_REA and faraLoc(candidat):
				if candidat.get("disc_reparat"):
					self._repara(candidat["disc_reparat"])
				else:
					self["detaliu"].setText(textStickCazut(candidat))
				return
			if not rezervaActualizarea(self):
				self["detaliu"].setText(textActualizareOcupata())
				return
			if candidat.get("fel") == FEL_STRAINA:
				self._candidatAles = candidat
				self._intreaba(self._dupaConfirmareVerificare, textAvertismentStrain(candidat),
					_("Imagine care nu este HD Satelit"), _("Da, continuă"), False, RANDURI_CONFIRMARE)
				return
			cod, text = candidat.get("paza") or pazaPachet(candidat)
			if cod != HdsPazaModel.PACHET_BUN:
				self._refuzPaza(text, cod)
				return
			self._candidatAles = candidat
			# R25 (analiza "cat mai simplu", 09.11.2026): verificarea nu scrie nimic pe receptor, deci OK o porneste direct;
			# singura alegere ramane ultima confirmare dinaintea scrierii (cu "Nu" ales), iar paza ramane intreaga: modelul,
			# locul, simularea, mediul si copia
			self._pregatesteSiVerifica()
		elif self._faza == "rezultat" and self._arataCorect and not self._scriereRealaPornita:
			self._intreabaFlashReal()

	def _dupaConfirmareVerificare(self, raspuns):
		if not raspuns or self._candidatAles is None:
			elibereazaActualizarea(self)
			return
		self._pregatesteSiVerifica()

	def _refuzMediu(self, cale):
		"""None daca fisierele stau pe un stick USB (sau in RAM); altfel arata refuzul in fereastra refuzurilor si
		intoarce textul scurt al refuzului. ofgwrite nu porneste niciodata dupa un refuz."""
		permis, motiv, dispozitiv, punct = verificaMediuScriere(cale)
		if permis:
			return self._refuzNumeStick(cale)
		if dispozitiv:
			unde = _("%s, montat pe %s") % (dispozitiv, punct)
		else:
			unde = cale
		if motiv == REFUZ_INTERN:
			scurt = _("Instalarea este oprită: fișierele imaginii stau pe memoria internă a receptorului (%s).") % unde
		elif motiv == REFUZ_LIPSA:
			scurt = _("Instalarea este oprită: nu am putut verifica unde stau fișierele imaginii (%s).") % unde
		else:
			scurt = _("Instalarea este oprită: fișierele imaginii nu stau pe un stick USB (%s).") % unde
		# fereastra de mesaj a skinului are loc pentru trei randuri; textul intreg merge in fereastra refuzurilor
		explicatie = _(
			"Imaginea trebuie să fie pe un stick USB. Din memoria internă nu se instalează niciodată: instalarea ar șterge chiar fișierele pe care le citește și receptorul nu ar mai porni.\n\nCopiază software-ul (kernel.bin, rootfs.tar.bz2, imageversion) pe un stick USB, introdu stickul și încearcă din nou. Nu s-a instalat nimic."
		)
		from Screens.HdsPazaModel import HdsPazaModelRefuz
		self.session.open(HdsPazaModelRefuz, scurt + "\n" + explicatie.replace("\n\n", "\n"),
			_("Instalarea este oprită"))
		return scurt

	def _refuzNumeStick(self, cale):
		"""None daca ofgwrite poate scrie de pe stickul acesta (o montare cu spatii se muta singura, aici, chiar inainte
		de scriere); altfel arata in fereastra refuzurilor ce nume sa-i dea omul stickului si intoarce textul scurt. Cu
		programul de scriere reparat trec si spatiile."""
		motiv, punct = pregatesteNumeStick(cale)
		if not motiv:
			return None
		nume = os.path.basename(punct or "") or cale
		if motiv == REFUZ_SPATII:
			scurt = _("Instalarea este oprită: numele stickului are spații (%s). Nu s-a instalat nimic.") % nume
		elif motiv == REFUZ_LIPSA:
			scurt = _("Instalarea este oprită: nu am putut verifica unde stau fișierele imaginii (%s).") % cale
		else:
			scurt = _("Instalarea este oprită: numele stickului are semne neacceptate (%s). Nu s-a instalat nimic.") % nume
		explicatie = _("Cu acest nume, instalarea ar șterge sistemul receptorului înainte să citească imaginea.") + "\n" + \
			_("Pune stickul în calculator, schimbă-i numele într-unul fără spații și fără semne (de exemplu "
				"HDSATELIT), apoi introdu-l din nou în receptor.")
		from Screens.HdsPazaModel import HdsPazaModelRefuz
		self.session.open(HdsPazaModelRefuz, scurt + "\n" + explicatie, _("Instalarea este oprită"))
		return scurt

	def _pregatesteSiVerifica(self):
		"""Dosarul curat al pachetului, pe un fir separat, apoi sumele si simularea."""
		candidat = self._candidatAles
		# stickul poate sa fi cazut dupa ce s-a citit lista
		marcheazaMediu(candidat, _discuriMontate())
		if faraLoc(candidat):
			self._reincarca()
			return
		punct = locLucru(candidat)
		refuz = self._refuzMediu(punct)
		if refuz:
			self._eroareInapoiLaLista(refuz)
			return
		try:
			marime = _marimePachet(candidat)
		except OSError as eroare:
			self._eroareInapoiLaLista(_("Nu am putut dezarhiva software-ul: %s") % eroare)
			return
		if not _spatiuSuficient(punct, marime):
			self._eroareInapoiLaLista(_("Spațiu insuficient pe %s pentru dezarhivare.") % punct)
			return
		self._ocupat = True
		self._opreste = False
		progres = {}
		self._pornestePas(PAS_COPIERE, progres, punct if candidat.get("numai_citire") else "")
		self._buton("key_green", "")
		self._buton("key_yellow", "")
		self._lucrare = HdsPazaModel.LucrareFundal(
			lambda: pregatesteDacaNuEOaspete(candidat, oprit=self._oprit, progres=progres),
			lambda cale, eroare: self._dosarGata(candidat, cale, eroare))

	# -------------------------------------------------------------- pasul si procentul, o data pe secunda

	def _pornestePas(self, pas, progres=None, punct=""):
		"""Textul de sus spune pasul (1-3 din 3), procentul si cat mai dureaza, reinnoit o data pe secunda; pagina web
		citeste acelasi text. La simulare, ceasul o opreste dupa LIMITA_SIMULARE_S."""
		self._pas = (pas, progres if progres is not None else {}, time.time(), punct)
		self._textPas = None
		ceas = getattr(self, "_ceasPas", None)
		if ceas is None:
			try:
				from enigma import eTimer
				ceas = eTimer()
				try:
					self._legaturaPas = ceas.timeout.connect(self._bataiePas)
				except AttributeError:
					ceas.callback.append(self._bataiePas)
				self._ceasPas = ceas
			except Exception as e:
				print("[HdsSoftwareUpdate] ceasul pasilor: %s" % e)
				ceas = None
		self._bataiePas()
		if ceas is not None:
			ceas.start(1000, False)

	def _opresteePas(self):
		self._pas = None
		ceas = getattr(self, "_ceasPas", None)
		if ceas is not None:
			ceas.stop()

	def _bataiePas(self):
		pas = getattr(self, "_pas", None)
		if pas is None:
			self._opresteePas()
			return
		numar, progres, inceput, punct = pas
		trecut = max(0.0, time.time() - inceput)
		text = textPas(numar, progres, trecut, punct)
		if text != getattr(self, "_textPas", None):
			self._textPas = text
			self["detaliu"].setText(text)
		if numar == PAS_SIMULARE and trecut >= LIMITA_SIMULARE_S:
			self._oprireSimulare(depasita=True)

	def _dosarGata(self, candidat, cale, eroare):
		self._opresteePas()
		self._lucrare = None
		self._ocupat = False
		if cale == OASPETE and not eroare:
			# NEO6: sub NeoBoot nu se copiaza si nu se simuleaza nimic; textul e cel al randului NeoBoot din simulare
			self._eroareInapoiLaLista(textOaspete())
			return
		if eroare or not cale:
			# stickul a cazut pe numai citire chiar acum: lista arata ce se poate face, in locul erorii brute
			marcheazaMediu(candidat, _discuriMontate())
			if candidat.get("numai_citire"):
				self._reincarca()
				return
			self._eroareInapoiLaLista(_("Nu am putut dezarhiva software-ul: %s") % (eroare or "?"))
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
			nimic = _("Nu s-a instalat nimic pe receptor.")
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
		if self._primitDupaAvertisment(cod):
			# fara semn nu sunt sume de verificat; se tine minte numai ca fisierele nu se schimba pana la scriere
			self._semnVerificat = (cale, HdsPazaModel.semnFisiere(cale))
			self._porneesteVerificare(cale)
			return
		if cod != HdsPazaModel.PACHET_BUN:
			self._refuzPaza(text, cod)
			return
		self._ocupat = True
		self._opreste = False
		progres = {}
		self._pornestePas(PAS_SUME, progres)
		self._buton("key_green", "")
		self._buton("key_yellow", "")
		semn = HdsPazaModel.semnFisiere(cale)
		self._lucrare = HdsPazaModel.LucrareFundal(
			lambda: HdsPazaModel.sumeSha256(cale, oprit=self._oprit, progres=progres),
			lambda sume, eroare: self._sumeGata(cale, marcaj, semn, sume, eroare))

	def _sumeGata(self, cale, marcaj, semn, sume, eroare):
		self._opresteePas()
		self._lucrare = None
		self._ocupat = False
		if eroare or sume is None:
			self._refuzPaza(_("Software-ul nu s-a putut citi de pe stick (%s).") % (eroare or "?") + "\n" +
				_("Nu s-a instalat nimic pe receptor."))
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

	def _primitDupaAvertisment(self, cod):
		"""Imaginea altora, pe care omul a primit-o dupa avertisment: tot fara semn. Daca intre timp are un semn, intra
		la paza obisnuita."""
		return cod == HdsPazaModel.REFUZ_FARA_MARCAJ and (self._candidatAles or {}).get("fel") == FEL_STRAINA

	def _refuzPazaInainteDeScriere(self, cale):
		"""Pe firul enigma2, chiar inainte de copie si de init 4: marcajul, amprenta si fisierele neschimbate de la
		sume. Intoarce textul refuzului (si il arata), sau None."""
		# Pe NAND nu pornim scrierea automata, nici dintr-un sistem USB.
		if HdsPazaModel.nand(HdsPazaModel.citesteReguli()):
			text = _("Instalarea din meniu nu este disponibilă pe acest model. "
				"Folosește arhiva pentru flash și metoda de instalare a receptorului. "
				"Imaginea USB se instalează din managerul de multi-imagine.")
			self._arataRefuzPaza(text)
			return text
		cod, text, _marcaj = HdsPazaModel.verificaPachet(_textMarcaj(os.path.join(cale, NUME_MARCAJ)))
		trece = cod == HdsPazaModel.PACHET_BUN or self._primitDupaAvertisment(cod)
		if trece and (not self._semnVerificat or self._semnVerificat[0] != cale or
				HdsPazaModel.semnFisiere(cale) != self._semnVerificat[1]):
			text = HdsPazaModel.textRefuz(HdsPazaModel.REFUZ_SCHIMBAT)
			trece = False
		if trece:
			return None
		self._arataRefuzPaza(text)
		return text.split("\n")[0]

	def _eroareInapoiLaLista(self, mesaj):
		"""Inapoi in lista, cu `mesaj` sus; tasta verde si cea galbena revin (lista e aceeasi)."""
		elibereazaActualizarea(self)
		self._faza = "lista"
		self["iesire"].hide()
		self["lista"].show()
		self["detaliu"].setText(mesaj)
		self._buton("key_green", _("Verifică software-ul") if self._candidati else "")
		self._buton("key_yellow", _("Reîncarcă"))

	def _blocheazaScrierea(self, mesaj):
		self._arataCorect = False
		self["detaliu"].setText(mesaj)
		self._buton("key_green", "")

	# -------------------------------------------------------------- faza 3: verificare (ofgwrite -n)

	def _porneesteVerificare(self, cale_pachet):
		self._pornireVerificata = None
		refuz = self._refuzMediu(cale_pachet)
		if refuz:
			self._eroareInapoiLaLista(refuz)
			return
		cmdline = _citesteCmdline()
		try:
			tinta = tintaScrierii(cmdline)
		except ValueError as eroare:
			self._arataCorect = False
			self._eroareInapoiLaLista(str(eroare))
			return
		refuz = refuzTinta(tinta, cale_pachet)
		if refuz:
			self._arataCorect = False
			self._eroareInapoiLaLista(refuz)
			return
		argumente = tinta["argumente"]
		self._cmdlineVerificare = cmdline
		self._faza = "verificare"
		self._ocupat = True
		self["iesire"].hide()
		self["lista"].show()
		self["iesire"].setText("")
		self["lista"].setList([self._randPachet(self._candidatAles)] if self._candidatAles else [])
		self._buton("key_green", "")
		self._buton("key_yellow", "")
		comanda = "%s -n %s %s" % (CALE_OFGWRITE, argumente, shlex.quote(cale_pachet))
		# fiecare simulare are numarul ei: raspunsul uneia oprite (EXIT sau prea lunga), venit tarziu, nu mai schimba nimic
		self._simulareNr = getattr(self, "_simulareNr", 0) + 1
		# si simularea isi pune fereastra peste interfata ("Check only, nothing is written", "Step 1 of 2"): textele ei in
		# limba omului (greseala 1201). ePopen nu primeste mediul, deci ofgwrite citeste fisierul scris aici
		# (/tmp/.ofgwrite-texte); la orice eroare fisierul e sters si fereastra ramane in engleza, ca inainte
		try:
			from Components.HdsTexteOfgwrite import scrieTexteOfgwrite
			scrieTexteOfgwrite()
		except Exception as eroare:
			print("[HdsSoftwareUpdate] textele programului de instalare (verificarea): %s" % eroare)
		self._ecranInainte = citesteEcranul()
		self._pornestePas(PAS_SIMULARE)
		self._console.ePopen(comanda, self._verificareGata, ("simulare", self._simulareNr))

	def _oprireSimulare(self, depasita=False):
		"""EXIT in timpul simularii, sau simularea mai lunga de LIMITA_SIMULARE_S: ofgwrite -n nu scrie nimic, deci se
		opreste oricand. Modul ecranului se pune la loc (fereastra lui ofgwrite ramanea peste interfata, care parea
		inghetata), iar omul se intoarce la lista cu un mesaj in cuvinte simple."""
		if self._faza != "verificare" or not self._ocupat:
			return
		self._opresteePas()
		self._simulareNr = getattr(self, "_simulareNr", 0) + 1
		self._console.killAll()
		punEcranulLaLoc(getattr(self, "_ecranInainte", None))
		self._ecranInainte = None
		redeseneazaTotEcranul()
		self._ocupat = False
		self._arataCorect = False
		self._pornireVerificata = None
		self.hide()
		self.show()
		if depasita:
			print("[HdsSoftwareUpdate] simularea a trecut de %d s: oprita" % LIMITA_SIMULARE_S)
			mesaj = _("Verificarea nu s-a terminat în %d minute și am oprit-o. Nu s-a instalat nimic pe receptor. "
				"Stickul poate fi prea lent sau poate avea erori: încearcă din nou, ori cu alt stick.") % (LIMITA_SIMULARE_S // 60)
		else:
			mesaj = _("Ai oprit verificarea. Nu s-a instalat nimic pe receptor.")
		self._eroareInapoiLaLista(mesaj)

	def _verificareGata(self, iesire, retval, extra_args=None):
		if isinstance(extra_args, tuple) and len(extra_args) == 2 and extra_args[0] == "simulare" and \
				extra_args[1] != getattr(self, "_simulareNr", 0):
			print("[HdsSoftwareUpdate] raspunsul unei simulari oprite (cod %s), lasat deoparte" % retval)
			return
		self._opresteePas()
		self._ecranInainte = None
		self._ocupat = False
		self._faza = "rezultat"
		# programul de instalare, chiar si la verificare, goleste ecranul cand termina: fara asta ramaneau numai textele schimbate, pe negru
		self.hide()
		self.show()
		self._ultimaIesire = iesire or _("(fără nicio ieșire de la ofgwrite)")
		cale = (self._candidatAles or {}).get("cale_finala") or ""
		cmdline = _citesteCmdline()
		self._arataCorect = retval == 0 and _simulareAratacorect(self._ultimaIesire, cmdline) and \
			getattr(self, "_cmdlineVerificare", cmdline) == cmdline and \
			_ofgwriteAGasitPachetul(self._ultimaIesire, cale)
		self._pornireVerificata = (cmdline, os.path.realpath(cale)) if self._arataCorect else None
		self._arataAnaliza(False)
		print("[HdsSoftwareUpdate] simularea, cod %s:\n%s" % (retval, self._ultimaIesire))
		self["iesire"].setText(analizaPeIntelesulOmului(iesire, retval, self._arataCorect))
		if self._arataCorect:
			self["detaliu"].setText(_("Software-ul a fost recunoscut corect: nucleul, sistemul și partițiile lor au fost găsite. Apasă OK sau Verde ca să îl instalezi pe receptor."))
			self._buton("key_green", _("Instalează pe receptor"))
		else:
			self["detaliu"].setText(textNerecunoscut())
			self._buton("key_green", "")

	# -------------------------------------------------------------- faza 4: confirmare informata si scriere reala

	def _intreabaFlashReal(self):
		"""Ultima confirmare, in fereastra intrebarilor, cu „Nu” ales: textul simplu sus, dosarul pentru Maintenance
		Mode si pachetul mai mic, dedesubt."""
		inregistrare = False
		try:
			inregistrare = bool(self.session.nav.getRecordings())
		except Exception:
			pass
		self._intreaba(self._dupaConfirmareFlashReal,
			textUltimaConfirmare(self._candidatAles, inregistrare, self._textRecuperare(), subdosarRadacina(), discUsbTinta()),
			_("Ultima confirmare"), _("Da, instalează acum"), False, RANDURI_CONFIRMARE)

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

		mountpoint = locLucru(self._candidatAles)
		if esteCopieCompleta(self._candidatAles):
			# copia completa are deja setarile ei: fara copia celor de acum, deci si fara punerea ei la loc la prima pornire
			self._pornesteScrierea(cale_pachet, mountpoint, _("Copia completă se pune înapoi exact cum a fost făcută; "
				"setările de acum nu se copiază."))
			return
		_bazaCanalelor("copie")
		folder_backup, fisiere_copiate, eroare_backup = _creeazaBackupSetari(mountpoint)
		eroare_backup = eroare_backup or _copieCompleta(mountpoint)
		if eroare_backup:
			# copie cazuta: scrierea asteapta raspunsul omului; implicit „Nu”
			self.session.openWithCallback(
				self._dupaIntrebareFaraCopie,
				MessageBox,
				_("Copia de siguranță nu s-a putut face (%s).\n\nContinui fără copie? Lista de canale, setările și datele canalelor se pierd la instalare.") % eroare_backup,
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
			self["detaliu"].setText(_("Instalarea nu a pornit, pentru că nu există copie de siguranță. Nu s-a instalat nimic pe receptor. Verifică stickul, apoi apasă din nou Verde."))
			return
		self._pornesteScrierea(self._candidatAles["cale_finala"], locLucru(self._candidatAles),
			_("Instalarea continuă fără copie de siguranță, cum ai ales."))

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
			_("Instalarea a pornit (interfața se poate opri oricând, e normal). Jurnal: %s") % cale_jurnal
		)
		self._buton("key_green", "")
		self._buton("key_yellow", "")

	def _porneesteFlashReal(self, cale_pachet, cale_jurnal):
		"""Comanda reala, DETASATA de acest proces: "init 4" opreste Enigma2 (deci si acest ecran) inainte ca ofgwrite sa
		apuce sa scrie. In sesiune noua (start_new_session): init opreste la schimbarea nivelului tot grupul de procese
		al lui enigma2.sh, deci o comanda pornita simplu cu "&" murea odata cu Enigma2, iar ofgwrite nu mai pornea:
		receptorul ramanea cu ecranul negru, fara interfata (proba pe receptor, 04.11.2026). Nu Console/ePopen, legat de
		bucla de evenimente a acestui proces.
		Intoarce None daca a pornit, sau textul refuzului daca paznicul a oprit scrierea."""
		refuz = self._refuzMediu(cale_pachet) or self._refuzPazaInainteDeScriere(cale_pachet)
		if refuz:
			return refuz
		cmdline = _citesteCmdline()
		try:
			tinta = tintaScrierii(cmdline)
		except ValueError as eroare:
			return str(eroare)
		refuz = refuzTinta(tinta, cale_pachet)
		if refuz:
			return refuz
		argumente = tinta["argumente"]
		if (" -m" in argumente or getattr(self, "_pornireVerificata", None) is not None) and (not self._arataCorect or
				getattr(self, "_pornireVerificata", None) != (cmdline, os.path.realpath(cale_pachet))):
			return _("Slotul sau pachetul nu mai corespunde verificării. Verifică din nou software-ul înainte de instalare.")
		try:
			jurnal = open(cale_jurnal, "wb")
		except OSError as eroare:
			print("[HdsSoftwareUpdate] jurnalul scrierii nu se poate deschide: %s" % eroare)
			return _("Pe stick nu se poate scrie, deci nu pornește instalarea. Pe receptor nu s-a schimbat nimic.")
		env_ofgwrite = None  # textele ferestrei programului, in limba omului; fara ele, engleza. Comanda ramane aceeasi
		try:
			from Components.HdsTexteOfgwrite import scrieTexteOfgwrite
			env_ofgwrite = scrieTexteOfgwrite()
		except Exception as eroare:
			print("[HdsSoftwareUpdate] textele programului de instalare: %s" % eroare)
		_bazaCanalelor("flash")
		comanda = (
			"echo '[hds] init 4 (opresc Enigma2 ca sa nu concureze cu scrierea)'; "
			"init 4; "
			"sleep 3; "
			"echo '[hds] pornesc scrierea reala'; "
			"%s %s %s; "
			"echo \"[hds] ofgwrite s-a intors, cod: $?\""
		) % (CALE_OFGWRITE, argumente, shlex.quote(cale_pachet))
		with jurnal:
			subprocess.Popen(["/bin/sh", "-c", comanda], stdin=subprocess.DEVNULL, stdout=jurnal, stderr=subprocess.STDOUT,
				close_fds=True, start_new_session=True, env=env_ofgwrite)
		return None
