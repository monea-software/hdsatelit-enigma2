# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsImportSurse.py: sursele importului de canale și setări și importul propriu-zis, fără ecran. Le folosesc ecranul
# „Import canale și setări” (Plugins/Extensions/HdsImportSetari/plugin.py) și pagina web /import
# (Plugins/Extensions/HdsWebControl/scanare_import_web.py), deci amândouă văd aceleași surse și fac același import.
#
# Sursele sunt numai ce există în clipa căutării:
#   - mediile montate, citite din /proc/mounts (pe V20 stick-ul e la /run/media/<eticheta>-sda1, nu la /media/usb):
#     întâi stick-urile și cardurile, apoi discurile, apoi alte partiții ale memoriei interne; pe fiecare, până la
#     ADANCIME dosare în jos: un dosar cu lamedb / settings (copie plată sau etc/enigma2 luat ca atare), dosarul
#     etc/enigma2 al altei imagini (sloturi, OpenMultiBoot, NeoBoot, copii ale rădăcinii) și arhivele de copie
#     (.tar.gz, .tgz, .tar, .tar.bz2, .tar.xz) care au înăuntru un dosar cu lamedb sau settings;
#   - copiile de siguranță făcute de receptor înaintea unui import sau a unei actualizări
#     (/etc/enigma2/hds-backup-setari-*), la sfârșit: cu ele se poate întoarce un import.
# Se sar: dosarul amiko/ (fișierele Maintenance Mode), dosarele ascunse și ale sistemului Windows, legăturile
# simbolice și dosarele modulelor de acces condiționat, recunoscute fără să li se știe numele (după felul în care își
# numesc fișierele și după locurile lor standard, vezi _nume_de_modul și _loc_acces): nu se citesc, nu se arată.
# Arhivele se judecă după cuprins: din ele se iau numai fișierele din lista albă, deci o arhivă a unui modul de acces
# nu e o sursă și nimic din ea nu se arată. Pe mediu nu se scrie nimic.
#
# Importul copiază numai LISTA_ALBA (canalele, buchetele, înregistrările programate); din settings ia numai cheile
# tunerelor (CHEI_TUNERE) și setările sigure ale meniului (Components/HdsImportExtra.CHEI_SIGURE, verificate față de
# valorile permise acum), care merg în settings.din-copie (Components/HdsSetariDinCopie.py), nu în settings. Tot din
# copie, prin Components/HdsImportExtra.py: piconurile (numai dintr-un dosar, cu limite), lista pluginurilor instalate
# (potrivită cu sursele de pachete ale receptorului, pentru oferta de instalare) și rețeaua (citită aici, aplicată pe
# firul enigma2 de Components/HdsImportRetea.py, cu întoarcerea la cea de dinainte când nu merge). Skinul nu se aduce. O arhivă se tratează ca venită din afară: se citesc cel mult
# MAX_MEMBRI membri și MAX_DECOMPRIMAT octeți decomprimați, se scriu numai fișierele obișnuite din lista albă aflate
# în dosarul găsit la căutare, fiecare direct în <dosarul pregătirii>/<nume> (fără extractall, deci fără căi luate din
# arhivă), cel mult MAX_OCTETI în total. Fiecare pregătire scrie în dosarul ei (/tmp/hds-import.<n>) și îl mută la
# /tmp/hds-import numai dacă e cea mai nouă, deci două pregătiri nu își amestecă fișierele. Un lamedb care nu începe
# cu antetul lui nu se copiază.
#
# Înainte de import, copia de siguranță a fișierelor pe care importul le înlocuiește (copie_de_siguranta): dosarul
# /etc/enigma2/hds-backup-setari-<data>, cu canalele, buchetele, înregistrările programate și settings; se păstrează
# numai ultimele PASTRATE_COPII. Un lamedb de acum scris pe jumătate (lib/dvb/db.cpp scrie neatomic) se copiază cum
# e, cu o notă: tocmai receptorul cu lista stricată are nevoie de import, deci nu e motiv de refuz.
#
# Originea pozițiilor (Components/HdsIstoricSemnal.py, hds_origine_pozitii.json): pozițiile de satelit care intră noi în
# listă prin import sunt notate ca aduse din altă listă (semnul din lista Sateliți, cât receptorul nu le-a recepționat);
# întoarcerea unui import din copia receptorului pune la loc originea din copie, care o are (copie_de_siguranta o ia).
#
# După scriere: rândurile buchetelor imaginii (userbouquet.hds_*: DAB+ și DVB-T2 din satelit) se pun la loc în indexul
# luat din copie (pune_la_loc_buchetele_imaginii); înregistrările programate importate intră și în lista din memorie a
# lui RecordTimer (incarca_temporizatoarele, în incheie_importul), altfel ieșirea interfeței le scria peste: lista care
# rămâne e unirea celor de pe receptor cu cele din copie, fără dubluri (timers.xml importat e înlocuit de această
# unire la prima salvare). Cheile tunerelor puse de unele imagini sub config.Nims.N.dvbs.* se aduc la forma imaginii, iar
# valorile implicite ale imaginii sursă care diferă de ale acesteia se scriu (chei_setari_cu_note,
# chei_tuner_imagine). O arhivă fără lamedb sau settings direct, dar cu o arhivă de copie înăuntru (copia programată a
# unei imagini), se cercetează un nivel mai jos (cuprins_arhiva, _scoate_membrul). La prima pornire, cu întrebare, același
# import îl pornește Components/HdsImportAltaImagine.py.
#
# Firele: pe firul enigma2 rămân numai text_setari_acum() (config.pickle(), înainte de a porni firul: arborele config
# nu se citește de pe alt fir) și reîncărcarea listei de canale (reincarca_canale(), după). Căutarea (cauta_surse),
# pregătirea (pregateste), copia de siguranță și importul (importa) citesc și scriu pe discuri, deci merg pe un fir
# separat (Lucrare; porneste_importul le leagă). Un singur import odată, de pe televizor sau din web: zăvorul
# (ocupa / elibereaza) se dă înapoi numai la capătul firului, iar cât rulează o pregătire sau un import ocupa() nu îl
# mai dă nimănui. Fișierul nu importă nimic din enigma2 la încărcare: probele de pe PC îl folosesc direct.

import glob
import os
import posixpath
import re
import shutil
import stat
import sys
import threading
import time

CALE_ETC = "/etc/enigma2"
CALE_MOUNTS = "/proc/mounts"
CALE_SYS_BLOCK = "/sys/block"
DOSAR_TMP = "/tmp/hds-import"
PREFIX_COPIE_RECEPTOR = "hds-backup-setari-"

ADANCIME = 3                  # cât de adânc se caută pe un mediu (rădăcina = 0)
MAX_DOSARE = 600              # dosare citite pe un mediu
MAX_INTRARI = 5000            # intrări citite dintr-un singur dosar (un dosar picon/ poate avea zeci de mii)
TERMEN_S = 20.0               # toată căutarea
MAX_ARHIVA = 32 * 1024 * 1024  # mărimea arhivei pe disc
MAX_MEMBRI = 2000
MAX_OCTETI = 32 * 1024 * 1024  # totalul fișierelor scrise dintr-o arhivă
MAX_DECOMPRIMAT = 128 * 1024 * 1024  # cât se decomprimă dintr-o arhivă, la căutare și la pregătire
MAX_EXTRA = 4 * 1024 * 1024  # un fișier al rețelei sau o listă de pachete dintr-o arhivă
MAX_INTERIOARE = 3            # arhivele din interiorul unei arhive cercetate (copia programată a unei imagini are una)
PASTRATE_COPII = 5            # copiile de siguranță ale importului păstrate în /etc/enigma2 (cele mai noi)
REZERVA_SPATIU = 1024 * 1024  # spațiul lăsat liber pe /etc/enigma2 după copia de siguranță
# settings intră în copie fără jetonul interfeței web (e numai al acestui receptor) și fără depanarea pornită
CHEI_SCOASE_DIN_COPIE = ("config.plugins.hdswebcontrol.token", "config.crash.enabledebug")

FS_MEDII = ("vfat", "exfat", "ntfs", "ntfs3", "fuseblk", "ext2", "ext3", "ext4", "hfsplus", "btrfs", "xfs", "f2fs")
TIPAR_DISPOZITIV = re.compile(r"^/dev/(sd[a-z]+|hd[a-z]+|mmcblk\d+|nvme\d+n\d+)(?:p?\d+)?$")
SUFIXE_ARHIVA = (".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
DOSARE_SARITE = ("amiko", "system volume information", "lost+found", "recycler", "recycled")
# Modulele de acces condiționat nu se recunosc după o listă de nume, ci după felul în care își numesc fișierele și
# dosarele: un cuvânt (litere și cifre, între semne) care se termină în „cam”, „cams” sau „camd”, cu cifre la coadă sau
# nu („…cam”, „…cams”, „…camd”, „…cam2”); „camera”, „campion” sau „campina” nu se potrivesc.
# Plus locul standard al configurărilor, etc/tuxbox/config. Dosarul programelor modulelor obișnuite (usr/<fel>s,
# numele felului la plural) se termină în "cams", deci îl prinde regula numelor. Aceeași regulă, scrisă separat ca să
# meargă și singură, în Components/HdsCopieSetari.py (_nume_de_modul).
TIPAR_CUVANT_ACCES = re.compile(r"cams?d?[0-9]*$")
LOCURI_ACCES = ("/etc/tuxbox/config/",)

FISIERE_CANALE = ("lamedb", "lamedb5", "bouquets.tv", "bouquets.radio")
FISIERE_TEMPORIZATOARE = ("timers.xml", "autotimer.xml")
NUME_ORIGINE = "hds_origine_pozitii.json"    # Components/HdsIstoricSemnal.NUME_ORIGINE
NUME_SETARI = ("settings", "settings-fara-token")
TIPAR_BUCHET = re.compile(r"^userbouquet\.[A-Za-z0-9_.@+-]{1,120}\.(tv|radio)$")
TIPAR_RAND_INDEX = re.compile(r'^#SERVICE\s+1:7:\d+:.*FROM BOUQUET\s+"([^"]+)"', re.I)
INDEXURI_BUCHETE = ("bouquets.tv", "bouquets.radio")
PREFIX_BUCHET_IMAGINE = "userbouquet.hds_"
ANTET_LAMEDB = {"lamedb": "eDVB services /4/", "lamedb5": "eDVB services /5/"}
CHEI_TUNERE = ("config.Nims.",)
TIPAR_CHEIE_NIMS = re.compile(r"^config\.Nims\.(\d+)\.(.+)$")
SUBSECTIUNI_ALTE_TUNERE = ("dvbc.", "dvbt.", "atsc.")
# numele de sub config.Nims.N care spun că tunerul e de satelit (NimManager.py, ramura DVB-S)
CHEI_SATELIT = ("diseqcMode", "diseqcA", "diseqcB", "diseqcC", "diseqcD", "simpleSingleSendDiSEqC",
	"simpleDiSEqCSetVoltageTone", "simpleDiSEqCOnlyOnSatChange", "simpleDiSEqCSetCircularLNB", "positionerMode",
	"longitude", "longitudeOrientation", "latitude", "latitudeOrientation", "advanced", "connectedTo", "diseqc13V",
	"toneAmplitude", "powerMeasurement", "powerThreshold", "turningSpeed", "fastTurningBegin", "fastTurningEnd",
	"tuningstepsize", "rotorPositions", "turningspeedH", "turningspeedV", "userSatellitesList")
# semnele din settings ale imaginilor cu diseqcMode implicit "single": una se recunoaște după cheile copiei, ale
# imaginilor salvate și ale asistentului de restaurare, alta după "dvbs."
SEMNE_SINGLE = ("config.backupmanager.", "config.imagemanager.", "config.misc.restorewizardrun")

ORDINE_MEDIU = {"stick": 0, "disc": 1, "intern": 2, "receptor": 3}
# alegerile importului: (cheia, câmpul sursei care trebuie să fie adevărat ca alegerea să aibă sens)
ALEGERI = (("canale", "canale"), ("tunere", "setari"), ("temporizatoare", "temporizatoare"), ("retea", "retea"),
	("picon", "picon"), ("generale", "setari"), ("pachete", "pachete"))
# rețeaua se alege de mână (schimbarea ei poate întrerupe legătura cu pagina web); pluginurile înseamnă numai oferta
ALEGERI_IMPLICITE = {"canale": True, "tunere": True, "temporizatoare": False, "retea": False, "picon": True,
	"generale": True, "pachete": True}


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsImportSurse] %s" % text)


def _extra():
	"""Components/HdsImportExtra.py; fără pachetul Components (probele de pe PC), fișierul de lângă acesta."""
	try:
		from Components import HdsImportExtra
		return HdsImportExtra
	except ImportError:
		modul = sys.modules.get("hds_import_extra")
		if modul is None:
			import importlib.util
			spec = importlib.util.spec_from_file_location("hds_import_extra",
				os.path.join(os.path.dirname(os.path.abspath(__file__)), "HdsImportExtra.py"))
			modul = importlib.util.module_from_spec(spec)
			sys.modules["hds_import_extra"] = modul
			spec.loader.exec_module(modul)
		return modul


def _rel_extra(norm):
	"""Partea de la capătul căii unui membru de arhivă care e un fișier al rețelei sau o listă de pachete
	(HdsImportExtra.fel_extra): (rădăcina copiei, rel) sau None."""
	parti = norm.split("/")
	X = _extra()
	for i in range(len(parti)):
		rel = "/".join(parti[i:])
		if X.fel_extra(rel):
			return "/".join(parti[:i]), rel
	return None


def _forma_ro(unu, multe, n):
	"""Fara Components/HdsPlural (modulul incarcat singur): pluralul din catalogul instalat de enigma2, daca e; altfel
	forma romaneasca (msgid-urile sunt in romana): unu pentru n == 1, altfel multe, fara "de" ("20 canale")."""
	try:
		import builtins
		f = getattr(getattr(builtins.__dict__.get("_"), "__self__", None), "ngettext", None)
		if f is not None:
			return f(unu, multe, n)
	except Exception:
		pass
	return unu if n == 1 else multe


def ngettext(unu, multe, n):
	"""Pluralul tradus (Components/HdsPlural.ngettext: formele din Plural-Forms ale limbii, intors ca Forma, al carei %
	merge si cand forma pentru 1 n-are numarul, ca "un canal" din ro.po). Fara pachetul Components (probele de pe PC),
	forma romaneasca de mai sus. Numele e cel stiut de xgettext."""
	try:
		from Components.HdsPlural import ngettext as plural
	except ImportError:
		return _forma_ro(unu, multe, n)
	return plural(unu, multe, n)


# ---------------------------------------------------------------- numele fișierelor

def fisier_permis(nume):
	"""Numele unui fișier din lista albă a importului (numai numele, fără dosar)."""
	return (nume in FISIERE_CANALE or nume in FISIERE_TEMPORIZATOARE or nume in NUME_SETARI
		or bool(TIPAR_BUCHET.match(nume)))


def nume_tinta(nume):
	"""settings-fara-token (forma copiilor de mână) se importă ca settings."""
	return "settings" if nume in NUME_SETARI else nume


def _nume_de_modul(nume):
	"""Un cuvânt din `nume` (împărțit la orice semn care nu e literă sau cifră) are forma numelor modulelor de acces
	condiționat (TIPAR_CUVANT_ACCES)."""
	return any(TIPAR_CUVANT_ACCES.search(c) for c in re.split(r"[^a-z0-9]+", nume.lower()))


def _loc_acces(cale):
	"""`cale` trece prin unul din locurile standard ale modulelor de acces condiționat (LOCURI_ACCES)."""
	c = "/" + cale.replace("\\", "/").strip("/") + "/"
	return any(loc in c for loc in LOCURI_ACCES)


def _are_cam(nume):
	"""Numele sau calea (a unui membru de arhivă) e al unui modul de acces condiționat, după nume sau după loc."""
	return _nume_de_modul(nume) or _loc_acces(nume)


def _sarit(nume):
	n = nume.lower()
	return n.startswith(".") or n.startswith("$") or n in DOSARE_SARITE or _are_cam(n)


def este_arhiva(nume):
	"""O arhivă se judecă după cuprins, nu după nume: o copie a canalelor care are în nume un cuvânt de modul de acces
	(„…inainte-de-<modul>…”) e bună, iar o arhivă a unui modul nu are lamedb sau settings, deci nu devine sursă
	(cuprins_arhiva)."""
	return nume.lower().endswith(SUFIXE_ARHIVA)


def _normalizat(nume):
	"""Calea unui membru de arhivă, fără „./” la început, sau None pentru o cale absolută sau cu „..”."""
	if not nume or nume.startswith("/") or "\\" in nume:
		return None
	parti = [p for p in nume.split("/") if p not in ("", ".")]
	if not parti or ".." in parti:
		return None
	return "/".join(parti)


def cuprins_dosar(nume_fisiere):
	"""{"canale", "lamedb", "setari", "temporizatoare", "buchete"} pentru numele fișierelor dintr-un dosar, sau None
	când dosarul nu are nici canale (lamedb), nici setări. "lamedb": lista în formatul pe care îl citește imaginea
	(lib/dvb/db.cpp citește numai lamedb, formatul 4; lamedb5 singur nu aduce canale)."""
	nume = set(nume_fisiere)
	canale = bool(nume & set(FISIERE_CANALE[:2]))
	setari = bool(nume & set(NUME_SETARI))
	if not (canale or setari):
		return None
	return {
		"canale": canale,
		"lamedb": "lamedb" in nume,
		"setari": setari,
		"temporizatoare": bool(nume & set(FISIERE_TEMPORIZATOARE)),
		"buchete": len([n for n in nume if TIPAR_BUCHET.match(n)]),
	}


# ---------------------------------------------------------------- mediile montate

def _montari(cale_mounts):
	"""[(dispozitiv, punct, fel)] din /proc/mounts, în ordinea montării."""
	lista = []
	try:
		with open(cale_mounts, "r", encoding="utf-8", errors="surrogateescape") as f:
			for rand in f:
				parti = rand.split()
				if len(parti) >= 3:
					lista.append((parti[0], parti[1].replace("\\040", " "), parti[2]))
	except (OSError, IOError):
		pass
	return lista


def disc_din_dispozitiv(dispozitiv):
	"""/dev/sda1 -> sda, /dev/mmcblk1p1 -> mmcblk1, /dev/nvme0n1p2 -> nvme0n1; None pentru altceva."""
	m = TIPAR_DISPOZITIV.match(dispozitiv or "")
	return m.group(1) if m else None


def _citeste_sys(cale):
	try:
		with open(cale, "r") as f:
			return f.read().strip()
	except (OSError, IOError):
		return ""


def este_amovibil(disc, sys_block=CALE_SYS_BLOCK, citeste=None, realpath=None):
	"""Stick sau card: /sys/block/<disc>/removable = 1, drumul dispozitivului trece prin USB, sau un card mmcblk
	care nu e memoria de pe placă (aceea se deosebește în medii(), după rădăcină)."""
	citeste = citeste or _citeste_sys
	realpath = realpath or os.path.realpath
	if citeste(posixpath.join(sys_block, disc, "removable")) == "1":
		return True
	try:
		if "/usb" in realpath(posixpath.join(sys_block, disc)):
			return True
	except (OSError, ValueError):
		pass
	return disc.startswith("mmcblk")


def eticheta(punct, dispozitiv):
	"""Numele scurt al mediului: ultimul nume din punctul de montare, fără sufixul dispozitivului
	(/run/media/STICK-sda1 -> STICK)."""
	baza = posixpath.basename(punct.rstrip("/")) or punct
	sufix = "-" + posixpath.basename(dispozitiv or "")
	if len(baza) > len(sufix) and baza.endswith(sufix):
		baza = baza[:-len(sufix)]
	return baza


def medii_de_proba(text):
	"""Mediile din variabila HDS_COPIE_MEDII ("<dosar>|<stick sau disc>|<eticheta>;...", aceeași ca la
	Components/HdsCopieSetari.py), numai pentru probe: în emulator un dosar legat apare în /proc/mounts ca discul
	mașinii, iar dosarele containerului ar apărea și ele ca discuri. init nu o pune."""
	rez = []
	for parte in (text or "").split(";"):
		if not parte.strip():
			continue
		bucati = parte.split("|")
		punct = bucati[0]
		fel = bucati[1] if len(bucati) > 1 and bucati[1] in ("stick", "disc") else "stick"
		eticheta_ = bucati[2] if len(bucati) > 2 else posixpath.basename(punct.rstrip("/\\"))
		if os.path.isdir(punct):
			rez.append({"punct": punct, "dispozitiv": "", "fel": fel, "eticheta": eticheta_})
	rez.sort(key=lambda m: ORDINE_MEDIU[m["fel"]])
	return rez


def medii(cale_mounts=CALE_MOUNTS, sys_block=CALE_SYS_BLOCK, citeste=None, realpath=None):
	"""Mediile pe care se caută: [{"punct", "dispozitiv", "fel" (stick / disc / intern), "eticheta"}], stick-urile
	întâi, apoi discurile, apoi celelalte partiții ale memoriei interne; un dispozitiv montat de două ori apare o
	dată. Rădăcina receptorului nu e o sursă. Cu HDS_COPIE_MEDII pusă (numai probele) și /proc/mounts implicit:
	mediile din variabilă (medii_de_proba)."""
	if cale_mounts == CALE_MOUNTS and os.environ.get("HDS_COPIE_MEDII"):
		return medii_de_proba(os.environ["HDS_COPIE_MEDII"])
	montari = _montari(cale_mounts)
	dispozitiv_radacina = None
	for disp, punct, _fel in montari:
		if punct == "/":
			dispozitiv_radacina = disp
	disc_radacina = disc_din_dispozitiv(dispozitiv_radacina)
	rez = []
	vazute = set()
	for disp, punct, fel_fs in montari:
		disc = disc_din_dispozitiv(disp)
		if disc is None or fel_fs not in FS_MEDII or punct == "/" or disp == dispozitiv_radacina:
			continue
		if punct.startswith(("/boot", "/proc", "/sys", "/dev")):
			continue
		# același sistem de fișiere montat de două ori = aceeași rădăcină (dispozitiv și inod); o montare „bind” a
		# unui alt dosar de pe el are alt inod și rămâne; un fișier montat peste un fișier nu e un mediu
		try:
			st = os.stat(punct)
			if not stat.S_ISDIR(st.st_mode):
				continue
			cheie = (st.st_dev, st.st_ino)
		except OSError:
			cheie = disp
		if cheie in vazute:
			continue
		vazute.add(cheie)
		if disc == disc_radacina:
			fel = "intern"
		elif este_amovibil(disc, sys_block, citeste, realpath):
			fel = "stick"
		else:
			fel = "disc"
		rez.append({"punct": punct, "dispozitiv": disp, "fel": fel, "eticheta": eticheta(punct, disp)})
	rez.sort(key=lambda m: ORDINE_MEDIU[m["fel"]])
	return rez


def nume_mediu(mediu):
	fel = mediu.get("fel")
	nume = mediu.get("eticheta") or mediu.get("punct") or ""
	if fel == "stick":
		if (mediu.get("dispozitiv") or "").startswith("/dev/mmcblk"):
			return _("Card de memorie „%s”") % nume
		return _("Stick USB „%s”") % nume
	if fel == "disc":
		return _("Disc „%s”") % nume
	if fel == "intern":
		return _("Memoria receptorului, partiția „%s”") % nume
	return _("Copiile de siguranță de pe receptor")


# ---------------------------------------------------------------- imaginea din care vine un dosar

def identifica_distributie(cale_radacina):
	"""Numele imaginii din rădăcina unei copii (etc/image-version, etc/issue, etc/os-release), sau „”."""
	etc = os.path.join(cale_radacina, "etc")
	try:
		with open(os.path.join(etc, "image-version"), "r", encoding="utf-8", errors="replace") as f:
			info = {}
			for rand in f:
				if "=" in rand:
					k, v = rand.strip().split("=", 1)
					info[k.lower()] = v.strip("\"'")
		nume = info.get("creator") or info.get("distro") or info.get("distroname") or ""
		versiune = info.get("version") or info.get("imageversion") or ""
		if nume:
			return ("%s %s" % (nume, versiune)).strip()[:60]
	except (OSError, IOError, ValueError):
		pass
	for nume_fisier in ("issue", "issue.net"):
		try:
			with open(os.path.join(etc, nume_fisier), "r", encoding="utf-8", errors="replace") as f:
				curat = re.sub(r"\\[a-zA-Z]", "", f.readline().strip()).strip()
			if curat and not curat.startswith("Poky"):
				return curat[:60]
		except (OSError, IOError):
			pass
	try:
		with open(os.path.join(etc, "os-release"), "r", encoding="utf-8", errors="replace") as f:
			for rand in f:
				if rand.startswith("PRETTY_NAME="):
					return rand.split("=", 1)[1].strip("\"'\n")[:60]
	except (OSError, IOError):
		pass
	return ""


# ---------------------------------------------------------------- căutarea

def _prea_mult_decomprimat(m, max_decomprimat):
	"""Membrul trece de limita octeților decomprimați: tarfile citește arhiva în ordine, iar offset_data + size e cât
	s-a decomprimat până la capătul lui."""
	return getattr(m, "offset_data", 0) + max(0, getattr(m, "size", 0)) > max_decomprimat


def _membri_arhiva(t, nume_arhiva, max_membri, termen, max_decomprimat, interioare=None, extra=None):
	"""{dosar: {nume}} cu fișierele din lista albă ale unei arhive deschise (`t`, citită în ordine), sau None la o
	limită depășită. În `interioare` (dacă e dată) pune membrii care sunt ei înșiși arhive de copie (fișiere obișnuite,
	nu legături, cel mult MAX_ARHIVA), iar în `extra` căile fișierelor rețelei și ale listelor de pachete (_rel_extra)."""
	pe_dosare = {}
	for i, m in enumerate(t):
		if i >= max_membri:
			return None
		if _prea_mult_decomprimat(m, max_decomprimat):
			_jurnal("arhivă sărită %s: prea mare după decomprimare" % nume_arhiva)
			return None
		if termen is not None and i % 50 == 49 and time.time() > termen:
			_jurnal("arhivă sărită %s: s-a terminat timpul căutării" % nume_arhiva)
			return None
		if not m.isreg():
			continue
		norm = _normalizat(m.name)
		if norm is None:
			continue
		dosar, nume = posixpath.split(norm)
		if fisier_permis(nume) and not _are_cam(norm):
			pe_dosare.setdefault(dosar, set()).add(nume)
		elif (extra is not None and len(extra) < 64 and not _are_cam(norm) and 0 < m.size <= MAX_EXTRA
				and _rel_extra(norm)):
			extra.append(norm)
		elif (interioare is not None and este_arhiva(nume) and not nume.startswith(".") and not _are_cam(norm)
				and 0 < m.size <= MAX_ARHIVA):
			interioare.append(norm)
	return pe_dosare


def _cel_mai_bun_dosar(pe_dosare, extra=None):
	bune = [(d, cuprins_dosar(n), len(n)) for d, n in (pe_dosare or {}).items()]
	bune = [b for b in bune if b[1]]
	if not bune:
		return None
	bune.sort(key=lambda b: (not b[0].endswith("etc/enigma2"), not b[0].endswith("enigma2"), -b[2], b[0]))
	dosar, cuprins = bune[0][0], bune[0][1]
	cuprins["extra"] = extra_sub_radacina(dosar, extra or ())
	return dosar, cuprins


def extra_sub_radacina(dosar, membri):
	"""Căile de sub rădăcina copiei (HdsImportExtra.radacina_copiei(dosar); la o copie plată, rădăcina arhivei) ale
	membrilor `membri` care sunt fișiere ale rețelei sau liste de pachete."""
	X = _extra()
	rad = X.radacina_copiei(dosar) or ""
	rez = []
	for norm in membri:
		if rad and not norm.startswith(rad + "/"):
			continue
		rel = norm[len(rad) + 1:] if rad else norm
		if X.fel_extra(rel) and rel not in rez:
			rez.append(rel)
	return sorted(rez)


def _cuprins_interior(tarfile, cale, membru, max_membri, termen, max_decomprimat):
	"""Cuprinsul arhivei `membru` aflate în arhiva `cale` (copia programată a unei imagini: arhiva cu data are înăuntru
	<nume>-AutoBackup<MAC>.tar.gz, fără dosar), citită ca flux, cu aceleași limite. (dosar, cuprins) sau None."""
	with tarfile.open(cale, "r:*") as t:
		for m in t:
			if m.isreg() and _normalizat(m.name) == membru:
				f = t.extractfile(m)
				if f is None:
					return None
				extra = []
				with tarfile.open(fileobj=f, mode="r|*") as interior:
					pe_dosare = _membri_arhiva(interior, "%s/%s" % (os.path.basename(cale), membru), max_membri,
						termen, max_decomprimat, extra=extra)
				return _cel_mai_bun_dosar(pe_dosare, extra)
	return None


def cuprins_arhiva(cale, max_membri=MAX_MEMBRI, termen=None, max_decomprimat=MAX_DECOMPRIMAT):
	"""(dosarul din arhivă, cuprinsul lui) pentru dosarul cu cele mai multe fișiere de import care are lamedb sau
	settings (etc/enigma2 întâi), sau None: arhivă stricată, fără așa ceva, cu prea mulți membri, cu prea mulți octeți
	decomprimați, sau căutarea a ajuns la `termen` (time.time()) în mijlocul ei. Când arhiva nu are direct așa ceva,
	dar are înăuntru alte arhive de copie (copia programată a unei imagini), se caută un nivel mai jos, în cel mult
	MAX_INTERIOARE dintre ele; atunci cuprinsul are și "interioara" (numele membrului)."""
	import tarfile
	interioare = []
	extra = []
	try:
		with tarfile.open(cale, "r:*") as t:
			pe_dosare = _membri_arhiva(t, os.path.basename(cale), max_membri, termen, max_decomprimat, interioare,
				extra)
	except Exception as eroare:  # tarfile.TarError, EOFError, OSError, zlib.error, lzma.LZMAError
		_jurnal("arhivă necitită %s: %s" % (os.path.basename(cale), eroare.__class__.__name__))
		return None
	if pe_dosare is None:
		return None
	gasit = _cel_mai_bun_dosar(pe_dosare, extra)
	if gasit:
		return gasit
	for membru in interioare[:MAX_INTERIOARE]:
		if termen is not None and time.time() > termen:
			break
		try:
			gasit = _cuprins_interior(tarfile, cale, membru, max_membri, termen, max_decomprimat)
		except Exception as eroare:  # arhiva din interior stricată
			_jurnal("arhivă necitită %s/%s: %s" % (os.path.basename(cale), membru, eroare.__class__.__name__))
			continue
		if gasit:
			cuprins = dict(gasit[1])
			cuprins["interioara"] = membru
			return gasit[0], cuprins
	return None


def _timp(cale):
	try:
		return os.path.getmtime(cale)
	except OSError:
		return 0


def _sursa(mediu, cale, fel, cuprins, timp, rel, imagine="", dosar_arhiva=""):
	interioara = cuprins.get("interioara", "") if fel == "arhiva" else ""
	try:
		ex = _extra().cuprins_extra(cale, fel, cale if fel == "arhiva" else "", cuprins.get("extra") or ())
	except Exception as eroare:
		_jurnal("părțile de lângă canale %s: %s" % (os.path.basename(cale), eroare.__class__.__name__))
		ex = {"retea": False, "picon": False, "pachete": False}
	if fel == "dosar":
		id_sursa = cale
	elif interioara:
		id_sursa = cale + "#" + interioara + "!" + dosar_arhiva
	else:
		id_sursa = cale + "#" + dosar_arhiva
	return {
		"id": id_sursa,
		"cale": cale,
		"fel": fel,
		"dosar_arhiva": dosar_arhiva,
		"arhiva_interioara": interioara,
		"mediu": mediu["fel"],
		"mediu_nume": nume_mediu(mediu),
		"punct": mediu.get("punct", ""),
		"rel": rel,
		"imagine": imagine,
		"timp": timp,
		"canale": cuprins["canale"],
		"lamedb": cuprins.get("lamedb", cuprins["canale"]),
		"setari": cuprins["setari"],
		"temporizatoare": cuprins["temporizatoare"],
		"buchete": cuprins["buchete"],
		"retea": bool(ex.get("retea")),
		"picon": bool(ex.get("picon")),
		"pachete": bool(ex.get("pachete")),
		"extra": list(cuprins.get("extra") or []) if fel == "arhiva" else [],
	}


def _timp_dosar(dosar, nume):
	return max([_timp(os.path.join(dosar, n)) for n in nume if n in FISIERE_CANALE or n in NUME_SETARI] or [0])


def _intrari(dosar, termen, max_intrari=MAX_INTRARI):
	"""(fișiere, dosare, arhive) ale unui dosar, alese întâi după nume și apoi după felul intrării dat de readdir
	(os.scandir: fără stat pe fiecare intrare, deci un dosar cu mii de imagini nu costă mii de citiri pe stick):
	fișierele din lista albă, dosarele care nu se sar după nume (amiko/, ascunse, ale Windows, ale modulelor de acces
	condiționat), arhivele de copie („._nume.tar.gz” e fișierul de însoțire lăsat de macOS pe un stick FAT, nu o
	arhivă). Legăturile simbolice nu intră. Cel mult max_intrari intrări; None dacă dosarul nu se poate citi."""
	fisiere, dosare, arhive = [], [], []
	try:
		with os.scandir(dosar) as it:
			for i, e in enumerate(it):
				if i >= max_intrari or (i % 200 == 199 and time.time() > termen):
					break
				n = e.name
				permis = fisier_permis(n)
				arhiva = not permis and este_arhiva(n) and not n.startswith(".")
				try:
					if e.is_symlink():
						continue
					if permis or arhiva:
						if e.is_file(follow_symlinks=False):
							(fisiere if permis else arhive).append(n)
					elif not _sarit(n) and not _loc_acces(os.path.join(dosar, n)) and e.is_dir(follow_symlinks=False):
						dosare.append(n)
				except OSError:
					continue
	except OSError:
		return None
	return sorted(fisiere), sorted(dosare), sorted(arhive)


def cauta_pe_mediu(mediu, termen, adancime=ADANCIME, max_dosare=MAX_DOSARE, max_arhiva=MAX_ARHIVA):
	"""Sursele de pe un mediu, căutate în lățime până la `adancime` dosare sub rădăcina lui, până la `termen`."""
	radacina = mediu["punct"]
	gasite = []
	coada = [(radacina, 0)]
	citite = 0
	while coada and citite < max_dosare and time.time() < termen:
		dosar, nivel = coada.pop(0)
		citite += 1
		intrari = _intrari(dosar, termen)
		if intrari is None:
			continue
		fisiere, dosare, arhive = intrari
		rel = os.path.relpath(dosar, radacina)
		rel = "" if rel == "." else rel
		# un dosar cu fișierele copiei (sau etc/enigma2 al altei imagini sub el): sursa; sub el nu se mai caută, afară
		# de rădăcina mediului, unde pot sta și alte copii
		cuprins = cuprins_dosar(fisiere)
		if cuprins:
			gasite.append(_sursa(mediu, dosar, "dosar", cuprins, _timp_dosar(dosar, fisiere), rel))
			if nivel > 0:
				continue
		if "etc" in dosare:
			e2 = os.path.join(dosar, "etc", "enigma2")
			in_e2 = None if os.path.islink(e2) else _intrari(e2, termen)
			cuprins = cuprins_dosar(in_e2[0]) if in_e2 else None
			if cuprins:
				gasite.append(_sursa(mediu, e2, "dosar", cuprins, _timp_dosar(e2, in_e2[0]),
					posixpath.join(rel, "etc", "enigma2"), identifica_distributie(dosar)))
				if nivel > 0:
					continue
		if nivel < adancime:
			coada.extend((os.path.join(dosar, n), nivel + 1) for n in dosare)
		for n in arhive:
			if time.time() >= termen:
				break
			cale = os.path.join(dosar, n)
			try:
				marime = os.path.getsize(cale)
			except OSError:
				continue
			if not 0 < marime <= max_arhiva:
				continue
			gasit = cuprins_arhiva(cale, termen=termen)
			if gasit:
				gasite.append(_sursa(mediu, cale, "arhiva", gasit[1], _timp(cale), posixpath.join(rel, n),
					dosar_arhiva=gasit[0]))
	# etc/enigma2 găsit de la rădăcina unei imagini și apoi încă o dată ca dosar: rămâne primul (are numele imaginii)
	unice = []
	vazute = set()
	for s in gasite:
		if s["id"] not in vazute:
			vazute.add(s["id"])
			unice.append(s)
	unice.sort(key=lambda s: -s["timp"])
	return unice


def copii_receptor(dosar_etc=CALE_ETC):
	"""Copiile de siguranță ale receptorului (hds-backup-setari-*), cele mai noi întâi."""
	mediu = {"fel": "receptor", "punct": dosar_etc, "eticheta": ""}
	rez = []
	for dosar in glob.glob(os.path.join(dosar_etc, PREFIX_COPIE_RECEPTOR + "*")):
		if not os.path.isdir(dosar) or os.path.islink(dosar):
			continue
		try:
			nume = [n for n in os.listdir(dosar) if os.path.isfile(os.path.join(dosar, n))]
		except OSError:
			continue
		cuprins = cuprins_dosar(nume)
		if cuprins:
			rez.append(_sursa(mediu, dosar, "dosar", cuprins, _timp_dosar(dosar, nume), os.path.basename(dosar)))
	rez.sort(key=lambda s: -s["timp"])
	return rez


def cauta_surse(cale_mounts=CALE_MOUNTS, sys_block=CALE_SYS_BLOCK, dosar_etc=CALE_ETC, termen_s=TERMEN_S,
		citeste=None, realpath=None):
	"""Toate sursele, în ordinea arătată: stick-urile (cele mai noi copii întâi), discurile, memoria internă, copiile
	receptorului. Rulează pe un fir separat."""
	termen = time.time() + termen_s
	surse = []
	vazute = set()
	for mediu in medii(cale_mounts, sys_block, citeste, realpath):
		for s in cauta_pe_mediu(mediu, termen):
			if s["id"] not in vazute:
				vazute.add(s["id"])
				surse.append(s)
	for s in copii_receptor(dosar_etc):
		if s["id"] not in vazute:
			vazute.add(s["id"])
			surse.append(s)
	return surse


# ---------------------------------------------------------------- textele unei surse

def data_text(timp):
	if not timp:
		return ""
	return time.strftime("%d.%m.%Y %H:%M", time.localtime(timp))


def text_sursa(s):
	"""Rândul scurt al sursei (lista de alegere, rândul „Sursa”)."""
	nume = s.get("rel") or posixpath.basename(s.get("cale", ""))
	if s.get("mediu") == "receptor":
		return _("Copia din %s") % data_text(s.get("timp"))
	if s.get("imagine"):
		return "%s (%s)" % (s["imagine"], nume)
	return nume


def cuprins_text(s):
	parti = []
	if s.get("canale"):
		parti.append(_("canale"))
	if s.get("buchete"):
		parti.append(_("buchete: %d") % s["buchete"])
	if s.get("setari"):
		parti.append(_("setări"))
	if s.get("temporizatoare"):
		parti.append(_("înregistrări programate"))
	if s.get("retea"):
		parti.append(_("rețea"))
	if s.get("picon"):
		parti.append(_("piconuri"))
	if s.get("pachete"):
		parti.append(_("lista pluginurilor"))
	return ", ".join(parti)


def descriere_sursa(s):
	"""Textul de sub listă pentru sursa aleasă: unde e, ce fel de copie, de când, ce are."""
	if s.get("fel") == "arhiva":
		fel = _("arhivă de copie")
	elif s.get("imagine"):
		fel = _("dosarul etc/enigma2 al imaginii %s") % s["imagine"]
	else:
		fel = _("dosar de copie")
	# pe mediu ajunge calea de sub rădăcina lui (stick-ul e deja numit în față); copia receptorului: numele dosarului
	loc = s.get("rel") or posixpath.basename(s.get("cale", "").rstrip("/")) or s.get("cale", "")
	return _("%s, %s: %s\nDin %s. Are: %s.") % (s.get("mediu_nume", ""), fel, loc, data_text(s.get("timp")),
		cuprins_text(s))


def eticheta_alegere(cheie):
	"""Numele alegerii, același pe televizor și în pagina web /import."""
	return {
		"canale": _("Canale și buchete"),
		"tunere": _("Setările antenei"),
		"temporizatoare": _("Înregistrări programate"),
		"retea": _("Rețea și Wi-Fi"),
		"picon": _("Piconuri"),
		"generale": _("Setări generale"),
		"pachete": _("Pluginuri"),
	}[cheie]


def ajutor_alegere(cheie):
	"""Rândul de ajutor al unei alegeri pe televizor; același text stă sub căsuța ei în pagina web /import."""
	return {
		"tunere": _("Tunerele, LNB-urile, DiSEqC și motorul antenei, din copie."),
		"temporizatoare": _("Înregistrările programate în copie."),
		"retea": _("Cablul și Wi-Fi-ul din copie. Fără legătură cu ele, rămâne rețeaua de acum."),
		"picon": _("Piconurile din dosarul picon al copiei, în memoria receptorului."),
		"generale": _("Fusul orar, ecranul și alte setări din copie. Limba nu se schimbă."),
		"pachete": _("Pluginurile din copie, oferite după import ca să le instalezi."),
	}.get(cheie, "")


def text_fara_surse():
	return _("Nu am găsit nicio copie a canalelor. Pune în receptor un stick USB care are o copie: dosarul "
		"etc/enigma2 al altei imagini, un dosar cu lamedb și bouquets.tv sau o arhivă de copie (.tar.gz), apoi "
		"alege „Caută din nou”.")


def alegeri_surse(surse):
	"""Rândurile listei de alegere: [(text, id)], cu titlul fiecărui mediu (cheia None) deasupra surselor lui."""
	randuri = []
	ultim = None
	for s in surse:
		if s["mediu_nume"] != ultim:
			ultim = s["mediu_nume"]
			randuri.append((ultim + ":", None))
		randuri.append(("   " + text_sursa(s), s["id"]))
	return randuri


# ---------------------------------------------------------------- pregătirea și importul

class _InLucru(object):
	"""Numără pregătirile și importurile care rulează acum (ocupa() nu dă zăvorul cât rulează vreuna)."""

	def __enter__(self):
		with _ZAVOR:
			_STARE["in_lucru"] = _STARE.get("in_lucru", 0) + 1
		return self

	def __exit__(self, *exc):
		with _ZAVOR:
			_STARE["in_lucru"] = max(0, _STARE.get("in_lucru", 0) - 1)
		return False


def pregateste(sursa, dest=DOSAR_TMP, max_membri=MAX_MEMBRI, max_octeti=MAX_OCTETI,
		max_decomprimat=MAX_DECOMPRIMAT):
	"""(dosarul din care se importă, None) sau (None, motiv). Un dosar se folosește pe loc; dintr-o arhivă se scriu
	numai fișierele obișnuite din lista albă aflate în dosarul găsit la căutare, întâi în dosarul acestei pregătiri
	(`dest`.<n>), care devine `dest` numai dacă între timp nu a pornit o pregătire mai nouă. Rulează pe un fir separat."""
	with _InLucru():
		return _pregateste(sursa, dest, max_membri, max_octeti, max_decomprimat)


def _pregateste(sursa, dest, max_membri, max_octeti, max_decomprimat):
	if sursa.get("fel") == "dosar":
		if not os.path.isdir(sursa.get("cale", "")):
			return None, _("dosarul nu mai există: %s") % sursa.get("cale", "")
		return sursa["cale"], None
	import tarfile
	cale = sursa.get("cale", "")
	try:
		if os.path.getsize(cale) > MAX_ARHIVA:
			return None, _("arhiva e prea mare")
	except OSError:
		return None, _("arhiva nu mai există: %s") % cale
	with _ZAVOR_TMP:
		_GENERATIE[0] += 1
		a_mea = _GENERATIE[0]
	lucru = "%s.%d" % (dest, a_mea)
	shutil.rmtree(lucru, ignore_errors=True)
	try:
		os.makedirs(lucru)
		os.chmod(lucru, 0o700)    # poate primi wpa_supplicant.conf al copiei
	except OSError as eroare:
		return None, str(eroare)
	extra = sursa.get("extra") or ()
	interioara = sursa.get("arhiva_interioara") or ""
	if interioara:
		# copia programată a unei imagini: întâi arhiva din interior, într-un fișier al pregătirii, apoi fișierele din ea
		cale_interioara = os.path.join(lucru, ".interioara.tar")
		rez = _scoate_membrul(tarfile, cale, interioara, cale_interioara, max_membri, max_decomprimat)
		if rez is None:
			rez = _scoate_din_arhiva(tarfile, cale_interioara, sursa.get("dosar_arhiva", ""), lucru, max_membri,
				max_octeti, max_decomprimat, extra)
		try:
			os.remove(cale_interioara)
		except OSError:
			pass
	else:
		rez = _scoate_din_arhiva(tarfile, cale, sursa.get("dosar_arhiva", ""), lucru, max_membri, max_octeti,
			max_decomprimat, extra)
	if rez is not None:
		shutil.rmtree(lucru, ignore_errors=True)
		return None, rez
	with _ZAVOR_TMP:
		cea_mai_noua = _GENERATIE[0] == a_mea
		if cea_mai_noua:
			shutil.rmtree(dest, ignore_errors=True)
			try:
				os.rename(lucru, dest)
			except OSError as eroare:
				shutil.rmtree(lucru, ignore_errors=True)
				return None, str(eroare)
	if not cea_mai_noua:
		shutil.rmtree(lucru, ignore_errors=True)
		return None, _("între timp s-a pregătit altă copie")
	return dest, None


def _scoate_membrul(tarfile, cale, membru, tinta, max_membri, max_decomprimat):
	"""Scrie în `tinta` membrul obișnuit `membru` al arhivei `cale` (cel mult MAX_ARHIVA octeți); None dacă a mers,
	altfel motivul."""
	try:
		with tarfile.open(cale, "r:*") as t:
			for i, m in enumerate(t):
				if i >= max_membri:
					return _("arhiva are prea multe fișiere")
				if _prea_mult_decomprimat(m, max_decomprimat):
					return _("arhiva e prea mare după decomprimare")
				if not m.isreg() or _normalizat(m.name) != membru:
					continue
				if m.size > MAX_ARHIVA:
					return _("arhiva e prea mare")
				f = t.extractfile(m)
				if f is None:
					break
				with open(tinta, "wb") as g:
					ramas = m.size
					while ramas > 0:
						bucata = f.read(min(65536, ramas))
						if not bucata:
							break
						g.write(bucata)
						ramas -= len(bucata)
				return None
	except Exception as eroare:  # tarfile.TarError, EOFError, OSError, zlib.error, lzma.LZMAError
		return _("arhiva nu se poate citi (%s)") % eroare.__class__.__name__
	return _("arhiva nu are fișiere de canale sau de setări")


def _scoate_din_arhiva(tarfile, cale, dosar_arhiva, lucru, max_membri, max_octeti, max_decomprimat, extra=()):
	"""Scrie în `lucru` fișierele din lista albă aflate în `dosar_arhiva`, iar în `lucru`/extra fișierele `extra` (căi
	de sub rădăcina copiei: rețeaua, listele pachetelor); None dacă a mers, altfel motivul."""
	scrise = 0
	total = 0
	rad = _extra().radacina_copiei(dosar_arhiva) or ""
	# fișierele rețelei și listele pachetelor găsite la căutare: în <lucru>/extra/<calea de sub rădăcina copiei>
	dorite = dict(((rad + "/" + rel) if rad else rel, rel) for rel in (extra or ()) if _extra().fel_extra(rel))
	try:
		with tarfile.open(cale, "r:*") as t:
			for i, m in enumerate(t):
				if i >= max_membri:
					return _("arhiva are prea multe fișiere")
				if _prea_mult_decomprimat(m, max_decomprimat):
					return _("arhiva e prea mare după decomprimare")
				norm = _normalizat(m.name)
				if norm is None or not m.isreg():
					continue
				dosar, nume = posixpath.split(norm)
				if norm in dorite and not _are_cam(norm) and 0 < m.size <= MAX_EXTRA:
					total += m.size
					if total > max_octeti:
						return _("fișierele din arhivă sunt prea mari")
					f = t.extractfile(m)
					if f is not None:
						tinta = os.path.join(lucru, "extra", *dorite[norm].split("/"))
						os.makedirs(os.path.dirname(tinta), mode=0o700, exist_ok=True)
						with open(tinta, "wb") as g:
							g.write(f.read(m.size))
					continue
				if dosar != dosar_arhiva or not fisier_permis(nume):
					continue
				total += max(0, m.size)
				if total > max_octeti:
					return _("fișierele din arhivă sunt prea mari")
				f = t.extractfile(m)
				if f is None:
					continue
				tinta = os.path.join(lucru, nume_tinta(nume))
				with open(tinta + ".nou", "wb") as g:
					ramas = m.size
					while ramas > 0:
						bucata = f.read(min(65536, ramas))
						if not bucata:
							break
						g.write(bucata)
						ramas -= len(bucata)
				os.replace(tinta + ".nou", tinta)
				scrise += 1
	except Exception as eroare:  # tarfile.TarError, EOFError, OSError, zlib.error, lzma.LZMAError
		return _("arhiva nu se poate citi (%s)") % eroare.__class__.__name__
	if not scrise:
		return _("arhiva nu are fișiere de canale sau de setări")
	return None


def curata_tmp(dest=DOSAR_TMP):
	"""Șterge fișierele scoase dintr-o arhivă (în RAM), după import, și dosarele pregătirilor rămase."""
	shutil.rmtree(dest, ignore_errors=True)
	for dosar in glob.glob(glob.escape(dest) + ".*"):
		if os.path.isdir(dosar) and not os.path.islink(dosar):
			shutil.rmtree(dosar, ignore_errors=True)


def lamedb_valid(cale, nume="lamedb"):
	antet = ANTET_LAMEDB.get(nume, ANTET_LAMEDB["lamedb"])
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			return f.readline().strip() == antet
	except (OSError, IOError):
		return False


def lamedb_intreg(cale, nume="lamedb"):
	"""Formatul 4: antetul și cele două secțiuni (transponders, services) închise cu „end” (lib/dvb/db.cpp,
	saveServicelist); un lamedb scris pe jumătate nu le are."""
	if not lamedb_valid(cale, nume):
		return False
	try:
		capete = 0
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			for rand in f:
				if rand.rstrip("\r\n") == "end":
					capete += 1
		return capete >= 2
	except (OSError, IOError):
		return False


# ---------------------------------------------------------------- copia de siguranță dinaintea importului

def text_setari_acum(dosar_etc=CALE_ETC):
	"""settings pentru copia de siguranță: arborele config de acum (config.pickle(), ce ar scrie enigma2 la ieșire),
	altfel fișierul de pe disc; None dacă nu e niciunul. Pe firul enigma2, înainte de a porni firul importului: config
	nu se citește de pe alt fir. Components.config se folosește numai dacă e deja încărcat (pe receptor e mereu)."""
	modul = sys.modules.get("Components.config")
	if modul is not None:
		try:
			text = modul.config.pickle()
			if text:
				return text
		except Exception as eroare:
			_jurnal("config.pickle: %s" % eroare)
	try:
		with open(os.path.join(dosar_etc, "settings"), "r", encoding="utf-8", errors="surrogateescape") as f:
			return f.read()
	except (OSError, IOError):
		return None


def _fara_chei_scoase(text):
	randuri = [r for r in text.splitlines() if r.split("=", 1)[0].strip() not in CHEI_SCOASE_DIN_COPIE]
	return "\n".join(randuri) + ("\n" if randuri else "")


def _spatiu_liber(dosar):
	try:
		st = os.statvfs(dosar)
		return st.f_bavail * st.f_frsize
	except (AttributeError, OSError):
		return None  # fără statvfs (PC) nu se poate afla; copia se încearcă


def _fisiere_de_copiat(dosar_etc):
	# originea pozițiilor (Components/HdsIstoricSemnal.py) merge cu lista: întoarcerea importului o pune la loc
	nume = [n for n in FISIERE_CANALE + FISIERE_TEMPORIZATOARE + (NUME_ORIGINE,)]
	try:
		nume += sorted(n for n in os.listdir(dosar_etc) if TIPAR_BUCHET.match(n))
	except OSError:
		pass
	rez = []
	for n in nume:
		cale = os.path.join(dosar_etc, n)
		if os.path.isfile(cale) and not os.path.islink(cale):
			rez.append((cale, n))
	return rez


def copii_vechi_de_sters(dosar_etc=CALE_ETC, pastrate=PASTRATE_COPII):
	"""Dosarele hds-backup-setari-* de pe receptor în afară de cele mai noi `pastrate` (numele are data, deci ordinea
	numelor e ordinea în timp)."""
	dosare = sorted(d for d in glob.glob(os.path.join(dosar_etc, PREFIX_COPIE_RECEPTOR + "*"))
		if os.path.isdir(d) and not os.path.islink(d))
	return dosare[:-pastrate] if pastrate > 0 and len(dosare) > pastrate else []


def copie_de_siguranta(dosar_etc=CALE_ETC, text_setari=None, note=None, pastrate=PASTRATE_COPII):
	"""Copia fișierelor pe care importul le poate înlocui, într-un dosar nou dosar_etc/hds-backup-setari-<data>:
	lista de canale, buchetele, înregistrările programate și settings (`text_setari`, fără CHEI_SCOASE_DIN_COPIE).
	Întoarce (dosar, fișierele copiate, eroare). Eroare (importul nu pornește) = lipsa spațiului sau un fișier care
	nu s-a putut copia. Un lamedb care nu e întreg se copiază cum e și primește o notă în `note`: nu e motiv de refuz,
	tocmai receptorul cu lista stricată are nevoie de import. După o copie reușită rămân numai ultimele `pastrate`.
	Rulează pe firul importului (numai fișiere)."""
	de_copiat = _fisiere_de_copiat(dosar_etc)
	necesar = REZERVA_SPATIU + len(text_setari or "")
	for cale, _nume in de_copiat:
		try:
			necesar += os.path.getsize(cale)
		except OSError:
			pass
	liber = _spatiu_liber(dosar_etc)
	if liber is not None and liber < necesar:
		return None, [], _("spațiu insuficient pe %s") % dosar_etc
	baza = os.path.join(dosar_etc, PREFIX_COPIE_RECEPTOR + time.strftime("%Y%m%d_%H%M%S"))
	dosar = baza
	nr = 1
	while os.path.exists(dosar):
		nr += 1
		dosar = "%s-%d" % (baza, nr)
	try:
		os.makedirs(dosar)
	except OSError as eroare:
		return None, [], str(eroare)
	copiate, necopiate = [], []
	for cale, nume in de_copiat:
		try:
			shutil.copy2(cale, os.path.join(dosar, nume))
			copiate.append(nume)
		except (OSError, IOError):
			necopiate.append(nume)
	if text_setari is not None:
		try:
			with open(os.path.join(dosar, "settings"), "wb") as f:
				f.write(_fara_chei_scoase(text_setari).encode("utf-8", "surrogateescape"))
				f.flush()
				os.fsync(f.fileno())
			copiate.append("settings")
		except (OSError, IOError, UnicodeEncodeError):
			necopiate.append("settings")
	if necopiate:
		return dosar, copiate, ngettext("%d fișier nu s-a putut copia (%s)", "%d fișiere nu s-au putut copia (%s)",
			len(necopiate)) % (len(necopiate), ", ".join(necopiate[:5]))
	# numai formatul 4 (lamedb) se poate verifica: secțiunile lui se închid cu „end”; lamedb5 nu le are, iar imaginea
	# nu îl scrie (lib/dvb/db.cpp), deci unul găsit pe receptor e al altei imagini și intră în copie fără verificare
	if "lamedb" in copiate and not lamedb_intreg(os.path.join(dosar, "lamedb"), "lamedb"):
		if note is not None:
			note.append(_("Lista de canale de acum (%s) nu era întreagă; a intrat în copie așa cum era.") % "lamedb")
	for vechi in copii_vechi_de_sters(dosar_etc, pastrate):
		shutil.rmtree(vechi, ignore_errors=True)
	return dosar, copiate, None


def _copiaza(sursa, destinatie, mesaje):
	"""Copiază un fișier obișnuit; o legătură simbolică se sare (ar aduce conținutul altui fișier al receptorului)."""
	if os.path.islink(sursa):
		mesaje.append(_("Sărit (e un link simbolic, nu un fișier real): %s") % sursa)
		return False
	shutil.copy2(sursa, destinatie + ".nou")
	os.replace(destinatie + ".nou", destinatie)
	return True


def _fisier_setari(dosar):
	for nume in NUME_SETARI:
		cale = os.path.join(dosar, nume)
		if os.path.isfile(cale):
			return cale
	return None


def _litera_tuner(slot):
	try:
		n = int(slot)
	except ValueError:
		return slot
	return chr(ord("A") + n) if 0 <= n < 26 else slot


def chei_tuner_imagine(chei, toate=None):
	"""Cheile tunerelor din settings-ul altei imagini, aduse la forma acestei imagini. ({cheie: valoare}, note).
	- unele imagini pun satelitul sub config.Nims.N.dvbs.* (cablul, terestrul, ATSC sub dvbc., dvbt., atsc.);
	  imaginea și altele îl țin direct sub config.Nims.N. "dvbs." se scoate (cheia scrisă direct câștigă, dacă sunt
	  amândouă); dvbc., dvbt. și atsc. nu se aduc (alte nume și alte valori decât cele ale imaginii).
	- settings are numai valorile diferite de cele implicite ale imaginii care l-a scris, iar acelea diferă: configMode
	  e "simple" la celelalte imagini cunoscute, "nothing" aici (afară de primul tuner de satelit, "simple");
	  diseqcMode e "single" la unele (cele cu "dvbs." și cele cu SEMNE_SINGLE), "diseqc_a_b" la altele și aici.
	  Pe un tuner cu chei de satelit fără configMode se pune "simple", iar fără diseqcMode (în modul simplu, la o
	  copie a unei imagini cu "single") se pune "single": valoarea pe care o avea tunerul.
	  O copie HD Satelit (are chei config.hds*) nu se completează: valorile ei implicite sunt ale acestei imagini.
	`toate`: toate cheile din settings-ul sursei (semnele imaginii); implicit `chei`."""
	toate = chei if toate is None else toate
	note = []
	rez = {}
	alte_tunere = 0
	cu_dvbs = False
	for k, v in chei.items():
		m = TIPAR_CHEIE_NIMS.match(k)
		if not m:
			rez[k] = v
			continue
		slot, rest = m.groups()
		if rest.startswith("dvbs."):
			cu_dvbs = True
			continue
		if rest.startswith(SUBSECTIUNI_ALTE_TUNERE):
			alte_tunere += 1
			continue
		rez[k] = v
	for k, v in chei.items():
		m = TIPAR_CHEIE_NIMS.match(k)
		if m and m.group(2).startswith("dvbs."):
			rez.setdefault("config.Nims.%s.%s" % (m.group(1), m.group(2)[5:]), v)
	if alte_tunere:
		note.append(_("Setările tunerelor de cablu și terestre din copie nu se aduc (sunt scrise altfel)."))
	if any(k.startswith("config.hds") for k in toate):
		return rez, note
	single = cu_dvbs or any(k.startswith(SEMNE_SINGLE) for k in toate)
	sloturi = {}
	for k in rez:
		m = TIPAR_CHEIE_NIMS.match(k)
		if m:
			sloturi.setdefault(m.group(1), set()).add(m.group(2).split(".", 1)[0])
	for slot in sorted(sloturi, key=lambda s: int(s) if s.isdigit() else 999):
		campuri = sloturi[slot]
		if not campuri & set(CHEI_SATELIT):
			continue
		cheie_mod = "config.Nims.%s.configMode" % slot
		if cheie_mod not in rez:
			rez[cheie_mod] = "simple"
			note.append(_("Tunerul %s: modul lui lipsea din copie; am pus modul simplu, cel implicit în imaginea "
				"veche.") % _litera_tuner(slot))
		cheie_diseqc = "config.Nims.%s.diseqcMode" % slot
		if single and rez.get(cheie_mod) == "simple" and cheie_diseqc not in rez:
			rez[cheie_diseqc] = "single"
			note.append(_("Tunerul %s: DiSEqC lipsea din copie; am pus un singur LNB, cum e implicit în imaginea "
				"veche.") % _litera_tuner(slot))
	return rez, note


def _citeste_settings(cale):
	toate = {}
	with open(cale, "r", encoding="utf-8", errors="replace") as f:
		for rand in f:
			rand = rand.strip()
			if "=" not in rand:
				continue
			k, v = rand.split("=", 1)
			toate[k.strip()] = v
	return toate


def chei_setari_cu_note(cale, tunere, generale):
	"""({cheie: valoare}, note) din settings-ul sursei, numai cheile tunerelor (trecute prin chei_tuner_imagine).
	Setările generale nu mai vin de aici, ci din lista albă HdsImportExtra.CHEI_SIGURE (_importa); `generale` a rămas
	pentru apelanții vechi și nu mai adaugă nimic."""
	prefixe = CHEI_TUNERE if tunere else ()
	if not prefixe:
		return {}, []
	toate = _citeste_settings(cale)
	chei = dict((k, v) for k, v in toate.items() if k.startswith(prefixe))
	if not tunere:
		return chei, []
	tuner = dict((k, v) for k, v in chei.items() if k.startswith(CHEI_TUNERE))
	restul = dict((k, v) for k, v in chei.items() if not k.startswith(CHEI_TUNERE))
	tuner, note = chei_tuner_imagine(tuner, toate)
	restul.update(tuner)
	return restul, note


def chei_setari(cale, tunere, generale):
	"""{cheie: valoare} din settings-ul sursei, numai cu prefixele alese (chei_setari_cu_note, fără note)."""
	return chei_setari_cu_note(cale, tunere, generale)[0]


def _buchet_din_rand(rand):
	"""Numele fișierului din "#SERVICE 1:7:...:FROM BOUQUET "userbouquet.x.tv" ORDER BY bouquet", sau None."""
	m = TIPAR_RAND_INDEX.match(rand.strip())
	return m.group(1) if m else None


def randuri_buchete_imagine(dest=CALE_ETC):
	"""{index: [rânduri]}: rândurile din bouquets.tv / bouquets.radio de acum care arată spre buchetele imaginii
	(userbouquet.hds_*, de pildă "DAB+ din satelit" și "DVB-T2 din satelit", puse o singură dată, la prima pornire, de
	Hds/DabT2/imagine.py) și al căror fișier există. Citit înainte ca importul să înlocuiască indexul."""
	rez = {}
	for index in INDEXURI_BUCHETE:
		try:
			with open(os.path.join(dest, index), "r", encoding="utf-8", errors="surrogateescape") as f:
				randuri = f.read().splitlines()
		except (OSError, IOError):
			continue
		ale = []
		for rand in randuri:
			nume = _buchet_din_rand(rand)
			if nume and nume.startswith(PREFIX_BUCHET_IMAGINE) and os.path.isfile(os.path.join(dest, nume)):
				ale.append(rand.rstrip())
		if ale:
			rez[index] = ale
	return rez


def pune_la_loc_buchetele_imaginii(dest, ale_imaginii):
	"""După ce importul a înlocuit indexul cu al copiei: rândurile buchetelor imaginii care lipsesc din el se adaugă la
	sfârșit (altfel listele DAB+ și DVB-T2 din satelit dispăreau din lista de canale, iar semnul lor de "pus o dată"
	nu le mai punea). Întoarce câte rânduri s-au adăugat."""
	adaugate = 0
	for index, randuri in (ale_imaginii or {}).items():
		cale = os.path.join(dest, index)
		try:
			with open(cale, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
				text = f.read()
		except (OSError, IOError):
			continue
		are = set(n for n in (_buchet_din_rand(r) for r in text.splitlines()) if n)
		lipsa = [r for r in randuri if _buchet_din_rand(r) not in are]
		if not lipsa:
			continue
		capat = "\r\n" if "\r\n" in text else "\n"   # buchetele scrise de enigma2 au CRLF (lib/dvb/db.cpp)
		if text and not text.endswith("\n"):
			text += capat
		text += capat.join(lipsa) + capat
		try:
			with open(cale + ".nou", "w", encoding="utf-8", errors="surrogateescape", newline="\n") as f:
				f.write(text)
			os.replace(cale + ".nou", cale)
			adaugate += len(lipsa)
		except (OSError, IOError) as eroare:
			_jurnal("buchetele imaginii în %s: %s" % (index, eroare))
	return adaugate


def incarca_temporizatoarele(cale, rt=None, creeaza=None):
	"""Înregistrările programate importate (timers.xml) intră și în lista din memorie a lui RecordTimer, fără dubluri
	(același serviciu, același început și sfârșit), ca la loadTimer (record cu ignoreTSC, fără salvare), apoi o
	salvare. Fără asta, RecordTimer scria la ieșirea interfeței (shutdown -> saveTimer) lista din memorie peste fișierul
	importat. Pe firul enigma2. Întoarce câte s-au adăugat."""
	import xml.etree.ElementTree as ET
	if rt is None:
		import NavigationInstance
		nav = NavigationInstance.instance
		rt = getattr(nav, "RecordTimer", None) if nav is not None else None
	if rt is None:
		return 0
	if creeaza is None:
		from RecordTimer import createTimer as creeaza
	try:
		radacina_xml = ET.parse(cale).getroot()
	except Exception as eroare:  # ET.ParseError, OSError
		_jurnal("timers.xml importat necitit: %s" % eroare.__class__.__name__)
		return 0
	vazute = set()
	for t in list(getattr(rt, "timer_list", [])) + list(getattr(rt, "processed_timers", [])):
		try:
			vazute.add((str(t.service_ref), int(t.begin), int(t.end)))
		except (AttributeError, TypeError, ValueError):
			continue
	adaugate = 0
	for el in radacina_xml.findall("timer"):
		try:
			t = creeaza(el)
			cheie = (str(t.service_ref), int(t.begin), int(t.end))
		except Exception as eroare:  # atribute lipsă sau greșite într-un timers.xml al altei imagini
			_jurnal("temporizator sărit: %s" % eroare.__class__.__name__)
			continue
		if cheie in vazute:
			continue
		vazute.add(cheie)
		rt.record(t, True, dosave=False)
		adaugate += 1
	if adaugate:
		rt.saveTimer()
	return adaugate


def importa(dosar, alegeri, dest=CALE_ETC, copie=None, setari=None, reincarca=None, text_setari=None, sursa=None,
		context=None, dest_picon=None, catalog=None, radacina_pregatita=None):
	"""Importul din `dosar` în `dest`, după alegeri ({"canale", "tunere", "temporizatoare", "retea", "picon",
	"generale", "pachete"}: bool). `sursa`: sursa aleasă (locurile piconurilor, ale rețelei și ale listei pluginurilor);
	`context`: ce s-a citit pe firul enigma2 înainte (context_import: valorile permise ale setărilor sigure).
	Întâi copia de siguranță a fișierelor de acum: copie(dest) -> (dosar, fișiere, eroare), implicit
	copie_de_siguranta cu `text_setari`; cu eroare importul nu pornește. Apoi canalele și buchetele, înregistrările
	programate și cheile de setări în settings.din-copie. Întoarce {"ok", "mesaje", "canale", "setari",
	"temporizatoare"}; "canale" > 0 cere reîncărcarea listei de canale, care se face pe firul enigma2
	(incheie_importul); `reincarca`, dacă e dat, se cheamă aici (probele). Rulează pe firul importului: numai fișiere."""
	with _InLucru():
		return _importa(dosar, alegeri, dest, copie, setari, reincarca, text_setari, sursa, context, dest_picon,
			catalog, radacina_pregatita)


def _importa(dosar, alegeri, dest, copie, setari, reincarca, text_setari, sursa=None, context=None, dest_picon=None,
		catalog=None, radacina_pregatita=None):
	note_copie = []
	if copie is None:
		def copie(d):
			return copie_de_siguranta(d, text_setari=text_setari, note=note_copie)
	if setari is None:
		from Components import HdsSetariDinCopie as setari
	mesaje = []
	rez = {"ok": False, "mesaje": mesaje, "canale": 0, "setari": 0, "temporizatoare": 0}
	if not os.path.isdir(dosar):
		mesaje.append(_("Dosarul sursă nu există: %s") % dosar)
		return rez
	try:
		os.makedirs(dest, exist_ok=True)
	except OSError as eroare:
		mesaje.append(str(eroare))
		return rez
	# copia de siguranță a fișierelor de acum: numai ce suprascrie importul
	folder, fisiere, eroare = copie(dest)
	if eroare:
		mesaje.append(_("Importul nu a pornit: copia de siguranță a setărilor de acum nu s-a putut face (%s).")
			% eroare)
		return rez
	if fisiere:
		# numele dosarului ajunge: copia stă lângă setări, în /etc/enigma2, și apare în lista surselor
		mesaje.append(_("Copia de siguranță de acum: %s (%s).") % (os.path.basename(folder or ""),
			ngettext("%d fișier", "%d fișiere", len(fisiere)) % len(fisiere)))
	mesaje.extend(note_copie)
	importate = []
	if alegeri.get("canale"):
		ale_imaginii = randuri_buchete_imagine(dest)
		pozitii_inainte = _pozitii_lamedb(os.path.join(dest, "lamedb"))
		lamedb_copiat = False
		copiate = 0
		for nume in FISIERE_CANALE:
			cale = os.path.join(dosar, nume)
			if not os.path.isfile(cale):
				continue
			if nume in ANTET_LAMEDB and not lamedb_valid(cale, nume):
				mesaje.append(_("Sărit: %s nu este o listă de canale bună.") % nume)
				continue
			if _copiaza(cale, os.path.join(dest, nume), mesaje):
				copiate += 1
				lamedb_copiat = lamedb_copiat or nume == "lamedb"
		if lamedb_copiat:
			_noteaza_originea(dest, dosar, pozitii_inainte, sursa)
		for cale in sorted(glob.glob(os.path.join(dosar, "userbouquet.*"))):
			nume = os.path.basename(cale)
			if TIPAR_BUCHET.match(nume) and os.path.isfile(cale) and _copiaza(cale, os.path.join(dest, nume), mesaje):
				copiate += 1
		rez["canale"] = copiate
		if copiate:
			importate.append(ngettext("canale și buchete (%d fișier)", "canale și buchete (%d fișiere)", copiate)
				% copiate)
			pune_la_loc_buchetele_imaginii(dest, ale_imaginii)
			if not os.path.isfile(os.path.join(dosar, "lamedb")) and os.path.isfile(os.path.join(dosar, "lamedb5")):
				mesaje.append(_("Copia are numai lamedb5, pe care această imagine nu îl citește: lista de canale a "
					"rămas cea de dinainte."))
		else:
			mesaje.append(_("Sursa aleasă nu are canale."))
	if alegeri.get("temporizatoare"):
		n = 0
		for nume in FISIERE_TEMPORIZATOARE:
			cale = os.path.join(dosar, nume)
			if os.path.isfile(cale) and _copiaza(cale, os.path.join(dest, nume), mesaje):
				n += 1
		rez["temporizatoare"] = n
		if n:
			importate.append(ngettext("înregistrări programate (%d fișier)", "înregistrări programate (%d fișiere)", n)
				% n)
	if importate:
		mesaje.append(_("Importate: %s.") % ", ".join(importate))
	if rez["canale"] and reincarca is not None:
		try:
			if reincarca():
				mesaje.append(_("Lista de canale s-a reîncărcat."))
		except Exception as eroare:
			_jurnal("reîncărcarea listei: %s" % eroare)
		rez["reincarcat"] = True
	cale_setari = _fisier_setari(dosar)
	if (alegeri.get("tunere") or alegeri.get("generale")) and cale_setari:
		chei, note_tunere = chei_setari_cu_note(cale_setari, alegeri.get("tunere"), False)
		mesaje.extend(note_tunere)
		rez["setari_antena"] = len(chei)
		if alegeri.get("generale"):
			sigure, lasate = _extra().chei_sigure(_citeste_settings(cale_setari), (context or {}).get("setari"))
			rez["setari_generale"] = len(sigure)
			rez["setari_lasate"] = lasate
			chei.update(sigure)
		if chei:
			in_asteptare, eroare = setari.scrie(chei)
			if eroare:
				mesaje.append(_("Setările alese nu s-au putut pregăti (%s); setările receptorului au rămas "
					"neschimbate.") % eroare)
			else:
				rez["setari"] = len(chei)
				mesaje.append(_("Setări pregătite: %d. Se aplică după repornirea interfeței.") % len(chei))
				if in_asteptare > len(chei):
					mesaje.append(_("Setări importate care așteaptă repornirea interfeței: %d.") % in_asteptare)
	_importa_extra(dosar, alegeri, rez, sursa, context, dest_picon, catalog, radacina_pregatita)
	rez["ok"] = bool(rez["canale"] or rez["setari"] or rez.get("temporizatoare") or rez.get("picon")
		or rez.get("_retea") or (rez.get("pachete") or {}).get("total"))
	if not rez["ok"]:
		mesaje.append(_("Nu s-a importat nimic."))
	return rez


def _importa_extra(dosar, alegeri, rez, sursa, context, dest_picon, catalog, radacina_pregatita):
	"""Piconurile, lista pluginurilor și rețeaua din copie (HdsImportExtra), pe firul importului. Rețeaua numai se
	citește aici: planul (cu parola Wi-Fi) stă în rez["_retea"], pe care incheie_importul îl scoate înainte ca rezultatul
	să ajungă în starea comună, și se aplică pe firul enigma2 (Components/HdsImportRetea.py)."""
	if not sursa or not any(alegeri.get(k) for k in ("picon", "pachete", "retea")):
		return
	X = _extra()
	mesaje = rez["mesaje"]
	fel = sursa.get("fel")
	try:
		if fel == "arhiva":
			loc = X.locuri_extra(sursa.get("cale", ""), "arhiva", sursa.get("cale", ""),
				radacina_pregatita or os.path.join(dosar, "extra"))
		else:
			loc = X.locuri_extra(sursa.get("cale", dosar), "dosar")
	except Exception as eroare:
		_jurnal("locurile din copie: %s" % eroare.__class__.__name__)
		return
	if alegeri.get("picon") and loc.get("picon"):
		r = X.copiaza_piconuri(loc["picon"], dest_picon or X.DEST_PICON)
		rez["picon"] = r["copiate"]
		if r["copiate"]:
			mesaje.append(_("Piconuri aduse: %d.") % r["copiate"])
		if r["oprit"] == "spatiu":
			mesaje.append(_("Piconurile nu încap în memoria receptorului; au rămas pe stick sau pe disc."))
		elif r["oprit"] == "limita":
			mesaje.append(_("Copia are mai multe piconuri decât încap; am adus o parte."))
	if alegeri.get("pachete") and loc.get("pachete"):
		nume, total = X.citeste_pachete(loc["pachete"])
		potrivite = {"oferite": [], "instalate": 0, "lipsa": len(nume), "fara_lista": True}
		if nume:
			try:
				if catalog is None:
					try:
						from Components import HdsPachete
					except ImportError:
						HdsPachete = None
					catalog = HdsPachete.incarca() if HdsPachete is not None else None
				if catalog is not None:
					potrivite = X.potriveste_pachete(nume, catalog)
			except Exception as eroare:
				_jurnal("sursele de pachete: %s" % eroare.__class__.__name__)
		potrivite["total"] = total
		rez["pachete"] = potrivite
		if total:
			mesaje.append(_("Pluginuri în copie: %d; în sursele receptorului și neinstalate: %d.")
				% (total, len(potrivite["oferite"])))
	if alegeri.get("retea"):
		try:
			plan = X.citeste_retea(loc.get("retea"))
		except Exception as eroare:
			_jurnal("rețeaua din copie: %s" % eroare.__class__.__name__)
			plan = None
		if plan and (plan.get("cablu") or plan.get("wifi")):
			rez["_retea"] = plan
		else:
			mesaje.append(_("Copia nu are setări de rețea pe care să le pot folosi."))


def _istoric_semnal():
	try:
		from Components import HdsIstoricSemnal as I
	except ImportError:
		try:
			import HdsIstoricSemnal as I
		except ImportError:
			return None
	return I


def _pozitii_lamedb(cale):
	"""Pozițiile de satelit din lista de canale de acum (Components/HdsIstoricSemnal.pozitii_lamedb), sau None."""
	I = _istoric_semnal()
	try:
		return I.pozitii_lamedb(cale) if I is not None else None
	except Exception as eroare:
		_jurnal("pozitiile listei: %s" % eroare.__class__.__name__)
		return None


def _noteaza_originea(dest, dosar, inainte, sursa):
	"""Lista de canale tocmai importată (Components/HdsIstoricSemnal.py, originea pozițiilor): pozițiile noi în listă
	sunt aduse din altă listă; cele care erau deja rămân cum erau. Întoarcerea unui import din copia de siguranță a
	receptorului pune la loc originea din copie (sau nimic, la o copie fără ea). Pe firul importului; nu aruncă."""
	I = _istoric_semnal()
	if I is None:
		return
	try:
		if (sursa or {}).get("mediu") == "receptor":
			I.originea_din_copie(dest, dosar)
		else:
			noi = I.lista_noua(dest, inainte, "import")
			_jurnal("pozitii aduse noi in lista: %d" % len(noi))
	except Exception as eroare:
		_jurnal("originea pozitiilor: %s" % eroare.__class__.__name__)


def reincarca_canale():
	"""Reîncarcă lista de canale și buchetele din /etc/enigma2 (firul enigma2)."""
	from enigma import eDVBDB
	db = eDVBDB.getInstance()
	if not db:
		return False
	db.reloadServicelist()
	db.reloadBouquets()
	return True


def pregateste_si_importa(sursa, alegeri, text_setari=None, anulat=None, dest_tmp=DOSAR_TMP, dest=CALE_ETC,
		context=None, dest_picon=None, catalog=None):
	"""Tot lucrul importului de pe firul lui: pregătirea sursei, importul (fără reîncărcarea listei), apoi ștergerea
	fișierelor scoase din arhivă. `anulat` (threading.Event): pus înainte de import (ecranul închis cât se pregătea
	copia), nu se mai scrie nimic pe receptor."""
	with _InLucru():
		try:
			dosar, motiv = pregateste(sursa, dest_tmp)
			if dosar is None:
				return {"ok": False, "mesaje": [_("Importul nu a pornit: %s.") % motiv]}
			if anulat is not None and anulat.is_set():
				return {"ok": False, "anulat": True, "mesaje": [_("Importul s-a oprit înainte să schimbe ceva.")]}
			return importa(dosar, alegeri, dest=dest, text_setari=text_setari, sursa=sursa, context=context,
				dest_picon=dest_picon, catalog=catalog,
				radacina_pregatita=os.path.join(dosar, "extra") if sursa.get("fel") == "arhiva" else None)
		finally:
			curata_tmp(dest_tmp)


def context_import(alegeri):
	"""Pe firul enigma2, înainte de firul importului: ce nu se poate citi de pe alt fir (arborele config: valorile
	permise ale setărilor sigure și modurile video declarate de televizor)."""
	context = {}
	if alegeri.get("generale"):
		try:
			context["setari"] = _extra().context_setari()
		except Exception as eroare:
			_jurnal("setările sigure: %s" % eroare.__class__.__name__)
			context["setari"] = {}
	return context


def incheie_importul(rez, eroare=None, reincarca=None, incarca=None, dest=CALE_ETC, dupa=None, aplica_retea=None):
	"""Pe firul enigma2, la capătul firului importului: reîncărcarea listei de canale (dacă s-au scris canale) și a
	înregistrărilor programate (incarca_temporizatoarele, dacă s-a scris timers.xml), apoi rețeaua din copie, dacă e
	(Components/HdsImportRetea.aplica, cu întoarcerea la cea de dinainte când nu merge; durează până la un minut), și
	abia apoi zăvorul dat înapoi, rezultatul ținut minte pentru ecran și web și dupa(rezultat). Întoarce rezultatul
	(fără rețea: cel final)."""
	if not isinstance(rez, dict):
		rez = {"ok": False, "mesaje": [_("Importul s-a oprit: %s.") % (eroare or _("eroare necunoscută"))]}
	if rez.get("canale") and not rez.get("reincarcat"):
		try:
			if (reincarca or reincarca_canale)():
				rez.setdefault("mesaje", []).append(_("Lista de canale s-a reîncărcat."))
		except Exception as e:
			_jurnal("reîncărcarea listei: %s" % e)
	if rez.get("temporizatoare"):
		try:
			n = (incarca or incarca_temporizatoarele)(os.path.join(dest, "timers.xml"))
			rez["temporizatoare_noi"] = n
			_jurnal("înregistrări programate adăugate în listă: %d" % n)
		except Exception as e:
			_jurnal("înregistrările programate: %s" % e)
	plan = rez.pop("_retea", None)

	def final(r):
		elibereaza(r)
		if dupa is not None:
			dupa(r)

	if not plan:
		final(rez)
		return rez

	def gata_retea(stare):
		rez["retea"] = stare
		rez.setdefault("mesaje", []).extend(stare.get("mesaje") or [])
		if stare.get("adus"):
			rez["ok"] = True
		final(rez)

	try:
		if aplica_retea is None:
			from Components.HdsImportRetea import aplica as aplica_retea
		aplica_retea(plan, gata_retea)
	except Exception as e:
		_jurnal("rețeaua: %s" % e.__class__.__name__)
		gata_retea({"adus": False, "mesaje": [_("Rețeaua din copie nu s-a aplicat; a rămas cea de dinainte.")]})
	return rez


# ---------------------------------------------------------------- starea comună (televizor și web)

_STARE = {"surse": None, "cand": 0, "cauta": False, "ocupat": False, "ultimul": None, "in_lucru": 0}
_ZAVOR = threading.Lock()
_ZAVOR_TMP = threading.Lock()    # dosarul /tmp/hds-import: care pregătire îl ia
_GENERATIE = [0]                 # numărul ultimei pregătiri pornite
_VII = []    # căutarea și importul în curs: Lucrarea (cu eTimer-ul ei) ținută în viață până la sfârșit


def stare():
	return _STARE


def ocupat():
	"""Un import rezervat sau un fir de import care încă lucrează."""
	return bool(_STARE["ocupat"] or _STARE.get("in_lucru"))


def ocupa():
	"""True dacă importul a fost rezervat pentru apelant; False dacă merge deja unul sau dacă un fir al unui import
	mai vechi încă lucrează (de exemplu ecranul s-a închis în timpul pregătirii)."""
	with _ZAVOR:
		if _STARE["ocupat"] or _STARE.get("in_lucru"):
			return False
		_STARE["ocupat"] = True
		return True


def elibereaza(rezultat=None):
	with _ZAVOR:
		_STARE["ocupat"] = False
		if rezultat is not None:
			_STARE["ultimul"] = rezultat


def alegeri_efective(alegeri, sursa):
	"""Alegerile de import, fără cele pe care sursa nu le poate da."""
	return dict((cheie, bool(alegeri.get(cheie)) and bool(sursa and sursa.get(camp))) for cheie, camp in ALEGERI)


def sursa_dupa_id(id_sursa, surse=None):
	for s in (surse if surse is not None else (_STARE["surse"] or [])):
		if s["id"] == id_sursa:
			return s
	return None


class Lucrare(object):
	"""functie() pe un fir separat; la_sfarsit(rezultat, eroare) pe firul enigma2, verificat de un eTimer la 100 ms.
	Obiectul trebuie ținut în viață de apelant până la sfârșit (eTimer-ul altfel e cules)."""

	def __init__(self, functie, la_sfarsit, interval_ms=100):
		from enigma import eTimer
		self._rez = {}
		self._la_sfarsit = la_sfarsit
		self._ceas = eTimer()
		try:
			self._legatura = self._ceas.timeout.connect(self._verifica)
		except AttributeError:
			self._ceas.callback.append(self._verifica)
		fir = threading.Thread(target=self._ruleaza, args=(functie,), name="HdsImportSurse")
		fir.daemon = True
		fir.start()
		self._ceas.start(interval_ms, False)

	def _ruleaza(self, functie):
		try:
			self._rez["r"] = functie()
		except Exception as eroare:
			self._rez["e"] = str(eroare)
		self._rez["gata"] = True

	def _verifica(self):
		if not self._rez.get("gata"):
			return
		self._ceas.stop()
		la_sfarsit, self._la_sfarsit = self._la_sfarsit, None
		if la_sfarsit is not None:
			la_sfarsit(self._rez.get("r"), self._rez.get("e"))

	def opreste(self):
		"""Rezultatul nu mai e dorit (ecranul s-a închis); firul își termină treaba singur."""
		self._la_sfarsit = None
		self._ceas.stop()


def porneste_cautarea(la_sfarsit=None):
	"""Pornește căutarea surselor (dacă nu merge deja una) și ține rezultatul în starea comună; la_sfarsit(surse)
	se cheamă pe firul enigma2. Întoarce Lucrarea, sau None dacă o căutare merge deja."""
	with _ZAVOR:
		if _STARE["cauta"]:
			return None
		_STARE["cauta"] = True

	lucrare = []
	terminat = []

	def _gata(surse, eroare):
		if eroare:
			_jurnal("căutarea surselor: %s" % eroare)
		_STARE.update(surse=surse or [], cand=time.time(), cauta=False)
		terminat.append(True)
		for l in lucrare:
			if l in _VII:
				_VII.remove(l)
		if la_sfarsit is not None:
			la_sfarsit(_STARE["surse"])

	try:
		l = Lucrare(cauta_surse, _gata)
	except Exception:
		_STARE["cauta"] = False
		raise
	if not terminat:
		lucrare.append(l)
		_VII.append(l)
	return l


def porneste_importul(sursa, alegeri, la_sfarsit=None, anulat=None):
	"""Pe firul enigma2: rezervă importul (None dacă merge deja unul), ia textul settings de acum (text_setari_acum),
	pornește pregateste_si_importa pe firul lui; la capăt, tot pe firul enigma2, incheie_importul (lista de canale,
	zăvorul) și la_sfarsit(rezultat). Lucrarea stă în _VII până la capăt, deci un ecran închis între timp nu lasă
	zăvorul luat și nici fișiere pe jumătate: zăvorul se dă înapoi numai când firul a terminat."""
	if not ocupa():
		return None
	lucrare = []
	terminat = []

	def _gata(rez, eroare):
		terminat.append(True)
		for l in lucrare:
			if l in _VII:
				_VII.remove(l)

		def dupa(rezultat):
			if la_sfarsit is not None:
				la_sfarsit(rezultat)
		incheie_importul(rez, eroare, dupa=dupa)

	try:
		text = text_setari_acum()
		context = context_import(alegeri)
		l = Lucrare(lambda: pregateste_si_importa(sursa, alegeri, text, anulat, context=context), _gata)
	except Exception as eroare:
		elibereaza({"ok": False, "mesaje": [_("Importul nu a pornit: %s.") % eroare]})
		raise
	if not terminat:
		lucrare.append(l)
		_VII.append(l)
	return l
