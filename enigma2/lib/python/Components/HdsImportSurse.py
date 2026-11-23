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
#     (.tar.gz, .tgz, .tar, .tar.bz2, .tar.xz, și .zip din 0.7.5/0.7.6: copiile unor imagini sunt zip) care au
#     înăuntru un dosar cu lamedb sau settings;
#   - copiile de siguranță făcute de receptor înaintea unui import sau a unei actualizări
#     (/etc/enigma2/hds-backup-setari-*), la sfârșit: cu ele se poate întoarce un import.
# Când imaginea pornește de pe un stick sau un disc (un loc de pe USB), celelalte partiții ale lui sunt tot stickul
# omului, nu memoria receptorului, iar partiția rădăcinii montată întreagă și altundeva (un loc de pe disc, /media/hdd)
# se caută și ea, fără locul pornit acum (medii cu discul_pornirii, _chei_proprii). Sub rădăcina unei imagini nu se
# coboară în dosarele sistemului; copiile complete ale altor imagini (cu ghidul TV, /home, modulele) se citesc până la
# MAX_ARHIVA_MEDIU, după copiile mici de pe același mediu, iar la o limită copia găsită până acolo rămâne. Fiecare
# montare sărită și fiecare mediu căutat lasă un rând în jurnal.
# Locurile altor imagini din memoria receptorului (pornire multiplă cu rootsubdir=linuxrootfsN: Ustym 4K PRO, SF8008,
# V10, Trio 4K, HD51), fără stick: surse_memorie, mediul "memorie". Partiția locurilor se montează NUMAI pentru citit
# într-un dosar al ei din /tmp cât ține căutarea și din nou cât ține importul (monteaza_numai_citire), apoi se
# demontează; locul pornit acum se sare. Pe partițiile memoriei nu se scrie nimic.
# Se sar: dosarul amiko/ (fișierele Maintenance Mode), dosarele ascunse și ale sistemului Windows, legăturile
# simbolice și dosarele modulelor de acces condiționat, recunoscute fără să li se știe numele (după felul în care își
# numesc fișierele și după locurile lor standard, vezi _nume_de_modul și _loc_acces): nu devin surse, nu se citesc, nu
# se arată. Arhivele se judecă după cuprins: o arhivă a unui modul de acces nu are lamedb sau settings, deci nu e o
# sursă și nimic din ea nu se arată. Pe mediu nu se scrie nimic.
# Fișierele modulelor de acces ale unei copii care e sursă (de sub rădăcina altei imagini sau din arhiva ei, locurile
# HdsImportExtra.LOCURI_ACCES) se copiază ca atare la import, cu alegerea „acces” (regula din 31.10.2026), iar
# pachetele modulelor se instalează din nou (HdsImportExtra.importa_acces). Sursa ține despre ele numai un bool; din
# arhivă se scot abia la pregătire, când alegerea e făcută, în <dosarul pregătirii>/extra.
#
# Importul copiază numai LISTA_ALBA (canalele, buchetele, înregistrările programate); din settings ia numai cheile
# tunerelor (CHEI_TUNERE) și setările sigure ale meniului (Components/HdsImportExtra.CHEI_SIGURE, verificate față de
# valorile permise acum), care merg în settings.din-copie (Components/HdsSetariDinCopie.py), nu în settings. Tot din
# copie, prin Components/HdsImportExtra.py: piconurile (numai dintr-un dosar, cu limite), lista pluginurilor instalate
# (potrivită cu sursele de pachete ale receptorului, pentru oferta de instalare) și rețeaua (citită aici, aplicată pe
# firul enigma2 de Components/HdsImportRetea.py, cu întoarcerea la cea de dinainte când nu merge) și modulele de acces
# (HdsImportExtra.importa_acces: fișierele ca atare, pachetele instalate din nou; modulul ales în copie se alege aici pe
# firul enigma2, în incheie_importul). Skinul nu se aduce. O arhivă se tratează ca venită din afară: se citesc cel mult
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
# După scriere: rândurile buchetelor care nu țin de lista de canale se pun la loc, la sfârșit, în indexul luat din copie
# (randuri_buchete_imagine, pune_la_loc_buchetele_imaginii): ale imaginii, pe care le scriu ea și extensiile ei din
# starea lor, nu din listă (userbouquet.hds*: IPTV, DVB-I, DAB+ și DVB-T2 din satelit; locurile extensiilor din
# hds_locuri, de pildă Radio online), de la orice sursă; ale omului care nu depind de lamedb (numai fluxuri de internet,
# buchete din el sau gol, ca la listele de pe internet, Components/HdsListeInternet.py), numai când sursa nu e o copie
# a acestui receptor: întoarcerea la o copie aduce lista exact cum era. Fișierele din sursă se copiază ca înainte, în afară
# de buchetele imaginii care sunt deja pe receptor (buchete_imagine_pe_receptor): ale lui rămân, cu sub-buchetele lor, nu
# cele din copie. În rezultat, "buchete_pastrate" (nu se numără ca aduse). Apoi randurile indexului copiei care trimit la
# un userbouquet fara fisier pe receptor se scot (scoate_randurile_fara_fisier): buchetul n-ar avea ce deschide.
# Numele buchetelor (TIPAR_BUCHET) primesc litere cu diacritice, spatii si &, ca in listele obisnuite (din 0.7.7); un nume
# citit de pe un stick FAT montat cu iocharset=iso8859-1 (octeti latin-1) se scrie pe receptor in UTF-8 (buchet_latin1).
# Înregistrările programate importate intră și în lista din memorie a lui RecordTimer (incarca_temporizatoarele, în
# incheie_importul), altfel ieșirea interfeței le scria peste: lista care rămâne e unirea celor de pe receptor cu cele din copie, fără dubluri (timers.xml importat e înlocuit de această
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
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import threading
import time

CALE_ETC = "/etc/enigma2"
CALE_MOUNTS = "/proc/mounts"
CALE_SYS_BLOCK = "/sys/block"
DOSAR_TMP = "/tmp/hds-import"
# 0.7.5 (MA9, Bogdanici13, forum 795, TODO 09.11 16:54): arhiva de copie trimisa din calculator, din pagina web /import.
# Sta in /tmp (memoria receptorului, pana la repornire), cate una: o arhiva noua o inlocuieste pe cea dinainte. Apare in
# lista surselor ca mediul calculator, pe televizor si in web, si se importa ca o copie de pe stick.
DOSAR_CALCULATOR = "/tmp/hds-import-calculator"
PREFIX_COPIE_RECEPTOR = "hds-backup-setari-"

ADANCIME = 3                  # cât de adânc se caută pe un mediu (rădăcina = 0)
MAX_DOSARE = 600              # dosare citite pe un mediu
MAX_INTRARI = 5000            # intrări citite dintr-un singur dosar (un dosar picon/ poate avea zeci de mii)
TERMEN_S = 20.0               # toată căutarea
MAX_ARHIVA = 32 * 1024 * 1024  # arhiva trimisă din calculator (ține în memorie); pe mediu, peste ea = arhivă mare
# O arhivă tar de pe stick sau disc se citește de acolo, pe bucăți, deci poate fi mai mare: copiile complete ale altor
# imagini au și ghidul TV (epg.dat din etc/enigma2), /home și modulele. Cele mari se citesc după celelalte de pe același
# mediu (cauta_pe_mediu), ca să nu ia timpul copiilor mici.
MAX_ARHIVA_MEDIU = 256 * 1024 * 1024
MAX_MEMBRI = 20000
MAX_OCTETI = 32 * 1024 * 1024  # totalul fișierelor scrise dintr-o arhivă
MAX_DECOMPRIMAT = 512 * 1024 * 1024  # cât se decomprimă dintr-o arhivă, la căutare și la pregătire
MAX_EXTRA = 4 * 1024 * 1024  # un fișier al rețelei sau o listă de pachete dintr-o arhivă
MAX_INTERIOARE = 3            # arhivele din interiorul unei arhive cercetate (copia programată a unei imagini are una)
PASTRATE_COPII = 5            # copiile de siguranță ale importului păstrate în /etc/enigma2 (cele mai noi)
REZERVA_SPATIU = 1024 * 1024  # spațiul lăsat liber pe /etc/enigma2 după copia de siguranță
# settings intră în copie fără jetonul interfeței web (e numai al acestui receptor) și fără depanarea pornită
CHEI_SCOASE_DIN_COPIE = ("config.plugins.hdswebcontrol.token", "config.crash.enabledebug")

FS_MEDII = ("vfat", "msdos", "exfat", "ntfs", "ntfs3", "fuseblk", "ext2", "ext3", "ext4", "hfsplus", "btrfs", "xfs",
	"f2fs", "tntfs", "texfat", "ufsd", "sdfat")
# Prin FUSE (exFAT si NTFS pe nucleele fara driver): fuseblk, sau cu subtipul pus de programul de montare
# (fuseblk.exfat, fuse.exfat, fuseblk.ntfs-3g); sursa ramane dispozitivul (/dev/sda1).
PREFIXE_FS_FUSE = ("fuseblk.", "fuse.")
TIPAR_DISPOZITIV = re.compile(r"^/dev/(sd[a-z]+|hd[a-z]+|mmcblk\d+|nvme\d+n\d+)(?:p?\d+)?$")
SUFIXE_ARHIVA = (".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")
# rootfs-ul unei imagini (din copiile complete de imagine): nu e o copie a setarilor si se citeste foarte incet (bz2/xz)
TIPAR_ROOTFS = re.compile(r"^rootfs[^/]*\.(tar|tgz|tbz2|txz)", re.I)
# Dosarele sistemului de sub radacina unei imagini (rootfs-ul altui loc montat intreg, o copie a radacinii): acolo nu
# stau copii ale setarilor, iar coborarea in ele ar lua bugetul dosarelor si timpul cautarii.
DOSARE_SISTEM = ("bin", "boot", "dev", "lib", "lib32", "lib64", "media", "mnt", "proc", "run", "sbin", "srv", "sys",
	"tmp", "usr", "var")
# Montarile de lucru ale receptorului intr-un dosar hds-* din /tmp (/tmp e legatura spre /var/volatile/tmp): lista
# pornirii multiple (Components/HdsPornireMultipla.py, hds-pornire-*), copia imaginii (hds-copie-imagine-radacina). Nu
# sunt medii: tin cateva secunde, iar o cautare care le-ar citi ar putea opri demontarea lor.
TIPAR_MONTARE_LUCRU = re.compile(r"^(?:/var/volatile)?/tmp/hds-[^/]+/?$")
# 0.7.7: locurile altor imagini din memoria receptorului. Partitia lor (userdata la SF8008 si inrudite, p3 si p8 la
# HD51) e montata de sistem numai ca / (subdosarul locului pornit) sau deloc. Se monteaza in DOSAR_MEMORIE % <partitia>
# (nu incepe cu hds-import: curata_tmp sterge /tmp/hds-import.*): o partitie deja montata cu montarea simpla (o a doua
# montare cu -o ro da EBUSY pe nucleul 4.4) si apoi `mount -o remount,bind,ro` numai pe ea, pe calea reala (busybox
# cauta in /proc/mounts /var/volatile/tmp/..., nu /tmp/..., si altfel nu face nimic); o partitie nemontata cu ro,noload.
# Fara "ro" dovedit in mountinfo pentru montarea noastra: demontata si sarita (probat pe receptor: scrierea prin ea cade
# cu Read-only file system, iar / ramane rw).
DOSAR_MEMORIE = "/tmp/hds-locuri-ro-%s"
CALE_MOUNTINFO = "/proc/self/mountinfo"
TIPAR_PARTITIE_MEMORIE = re.compile(r"^/dev/mmcblk0p[1-9][0-9]*$")
TIPAR_LOC_MEMORIE = re.compile(r"^linuxrootfs[1-9][0-9]*$")
TERMEN_MEMORIE_S = 5.0          # cautarea in locurile din memorie, din TERMEN_S
# 0.7.5/0.7.6 (SMB, TODO 15.11 06:20 (import .zip)): copiile unor imagini sunt arhive zip. Zip-ul se citeste prin
# _ArhivaZip, cu aceeasi forma ca tarfile (membri, extractfile), deci cautarea si pregatirea sunt aceleasi. Un zip se
# judeca dupa cuprinsul lui (lista de la coada, fara decomprimare), nu dupa marime: imaginile de scris de pe stick sunt
# zip-uri de sute de MB fara lamedb si se sar fara mesaj. Din zip se decomprima numai fisierele scoase (MAX_OCTETI).
SUFIXE_ZIP = (".zip",)
MAX_ZIP = 4 * 1024 * 1024 * 1024    # marimea unui zip pe disc (FAT32 nu are fisiere mai mari)
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
# 0.7.7 (BQN, asistenta 365893): numele unui fisier de buchet se judeca dupa ce nu are voie sa aiba, nu dupa o lista de
# litere permise. Listele obisnuite au in nume litere cu diacritice (Türksat, TurkmenÄlem), spatii, &, apostrofuri sau
# paranteze; tiparul vechi, numai ASCII, le lasa pe dinafara la import si in copia de siguranta, iar randul lor ramanea
# in bouquets.tv (buchetul disparea fara niciun mesaj). Refuzate: / si \ (cai), ghilimelele (incheie numele in randul
# FROM BOUQUET citit de nucleu), : si % (nucleul le scrie in referinta ca %xx si le decodeaza la citire,
# lib/service/service.cpp, deci randul din index n-ar mai avea acelasi nume ca fisierul), caracterele de control (si
# C1), despartitoarele de rand pe care le vede splitlines (U+2028, U+2029) si octetii care nu sunt UTF-8 (surogatele lui
# surrogateescape: nu se pot scrie in jurnal si in JSON). Cel mult MAX_OCTETI_NUME octeti UTF-8: impreuna cu ".nou" al
# scrierilor atomice incape in 255, limita unui nume de fisier.
MAX_OCTETI_NUME = 250
_TIPAR_NUME_BUCHET = re.compile('^userbouquet\\.[^\\x00-\\x1f\\x7f-\\x9f/\\\\":%\\u2028\\u2029\\ud800-\\udfff]+'
	'\\.(tv|radio)\\Z')


class _NumeBuchet(object):
	"""TIPAR_BUCHET: match(nume) ca la un tipar re (None sau potrivirea), cu lungimea numarata in octeti UTF-8."""

	def match(self, nume):
		if not isinstance(nume, str):
			return None
		m = _TIPAR_NUME_BUCHET.match(nume)
		if m is None or len(nume.encode("utf-8")) > MAX_OCTETI_NUME:
			return None
		return m


TIPAR_BUCHET = _NumeBuchet()
TIPAR_RAND_INDEX = re.compile(r'^#SERVICE\s+1:7:\d+:.*FROM BOUQUET\s+"([^"]+)"', re.I)
INDEXURI_BUCHETE = ("bouquets.tv", "bouquets.radio")
PREFIX_BUCHET_IMAGINE = "userbouquet.hds_"
# 0.7.7: buchetele care rămân în index după import (randuri_buchete_imagine). Ale imaginii:
# userbouquet.hds* (hdsiptv, hdsdvbi, hds_dab, hds_t2, hds_abertis; ca Components/HdsBucheteOrfane.PREFIX_PROPRII) și
# rădăcinile locurilor extensiilor (Components/HdsLocuriLista.py, /etc/enigma2/hds_locuri/<id>.json, câmpul "buchet").
PREFIX_BUCHETE_IMAGINE = "userbouquet.hds"
DOSAR_LOCURI = "hds_locuri"
MAX_LOC = 64 * 1024           # un fișier al registrului locurilor
# ale listei de canale, nu ale omului: favoritele vin din sursă, ultima scanare ține de lista veche
BUCHETE_LISTEI = ("userbouquet.favourites.tv", "userbouquet.favourites.radio", "userbouquet.LastScanned.tv",
	"userbouquet.LastScanned.radio")
TIPAR_SERVICIU = re.compile(r"^#SERVICE ", re.I)
TIPAR_ETICHETA = re.compile(r"^#SERVICE\s+1:64:", re.I)
TIPAR_TRIMITERE = re.compile(r"^#SERVICE\s+1:7:", re.I)
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

ORDINE_MEDIU = {"calculator": -1, "stick": 0, "disc": 1, "intern": 2, "memorie": 3, "receptor": 4}
# alegerile importului: (cheia, câmpul sursei care trebuie să fie adevărat ca alegerea să aibă sens)
ALEGERI = (("canale", "canale"), ("tunere", "setari"), ("temporizatoare", "temporizatoare"), ("retea", "retea"),
	("picon", "picon"), ("generale", "setari"), ("acces", "acces"), ("pachete", "pachete"))
# rețeaua se alege de mână (schimbarea ei poate întrerupe legătura cu pagina web); pluginurile înseamnă numai oferta;
# modulele de acces: fișierele copiate ca atare și pachetele instalate din nou (HdsImportExtra.importa_acces)
ALEGERI_IMPLICITE = {"canale": True, "tunere": True, "temporizatoare": False, "retea": False, "picon": True,
	"generale": True, "acces": True, "pachete": True}


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
		or bool(TIPAR_BUCHET.match(nume)) or buchet_latin1(nume) is not None)


def buchet_latin1(nume):
	"""Numele UTF-8 al unui buchet citit de pe un stick FAT: nucleele receptoarelor monteaza FAT cu iocharset=iso8859-1
	(SF8008: /media/hdd), deci un fisier userbouquet.Türksat.tv pus de pe calculator vine cu ü ca un octet latin-1, adica
	un nume care nu e UTF-8 (surogate in Python), iar randul din bouquets.tv il cere in UTF-8. Si UTF-8 citit ca latin-1
	(mai jos). None cand numele e deja bun sau nu devine un nume bun de buchet (TIPAR_BUCHET)."""
	if not isinstance(nume, str) or not nume.startswith("userbouquet."):
		return None
	try:
		nume.encode("utf-8")
	except UnicodeEncodeError:
		try:
			reparat = nume.encode("utf-8", "surrogateescape").decode("latin-1")
		except UnicodeError:
			return None
		return reparat if TIPAR_BUCHET.match(reparat) else None
	# 0.7.7 (UTF): stickurile FAT se monteaza acum cu utf8. Un fisier scris de receptor pe stick inainte (FTP, Samba,
	# copiat din receptor, cu montarea iso8859-1) are in FAT octetii UTF-8 ca litere latin-1, deci vine ca TÃ¼rksat:
	# numele care, scris inapoi in latin-1, e UTF-8 bun si altul decat el e numele adevarat (cel din bouquets.tv).
	try:
		reparat = nume.encode("latin-1").decode("utf-8")
	except UnicodeError:
		return None
	return reparat if reparat != nume and TIPAR_BUCHET.match(reparat) else None


def nume_tinta(nume):
	"""settings-fara-token (forma copiilor de mână) se importă ca settings; un buchet cu numele în latin-1 (stick FAT),
	cu numele UTF-8 (buchet_latin1)."""
	if nume in NUME_SETARI:
		return "settings"
	return buchet_latin1(nume) or nume


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


def _are_cam_fisier(cale):
	"""_are_cam pentru un fisier din lista alba (fisier_permis) dintr-o arhiva: un buchet al omului (TIPAR_BUCHET) se judeca
	numai dupa dosarele si locul lui, nu si dupa nume. Numele vine din ce a scris omul (Webcams, Live cam) si poate avea
	forma numelor de module, dar fisierul e o lista de canale (ca in Components/HdsCopieSetari.py). Altfel buchetul lipsea
	din cuprinsul arhivei (numarul buchetelor aratat omului), desi scoaterea din arhiva il lua."""
	dosar, nume = posixpath.split(cale)
	if TIPAR_BUCHET.match(nume) or buchet_latin1(nume) is not None:
		return bool(dosar and _nume_de_modul(dosar)) or _loc_acces(cale)
	return _are_cam(cale)


def _sarit(nume):
	n = nume.lower()
	return n.startswith(".") or n.startswith("$") or n in DOSARE_SARITE or _are_cam(n)


def este_arhiva(nume):
	"""O arhivă se judecă după cuprins, nu după nume: o copie a canalelor care are în nume un cuvânt de modul de acces
	(„…inainte-de-<modul>…”) e bună, iar o arhivă a unui modul nu are lamedb sau settings, deci nu devine sursă
	(cuprins_arhiva). Tar sau zip."""
	return este_tar(nume) or este_zip(nume)


def este_tar(nume):
	return nume.lower().endswith(SUFIXE_ARHIVA)


def este_zip(nume):
	return nume.lower().endswith(SUFIXE_ZIP)


class _MembruZip(object):
	"""Un membru zip in forma unui membru tarfile (name, size, mode, offset_data, isreg). Numele cu bara inversa (unele programe
	de pe Windows) se scriu cu /; dosarele, legaturile simbolice (in external_attr) si membrii criptati nu sunt fisiere
	obisnuite, deci nu se citesc niciodata. offset_data e 0: din zip nu se decomprima in ordine, ci numai ce se scoate."""

	def __init__(self, info):
		self.info = info
		nume = info.filename
		if not info.flag_bits & 0x800:
			# fara semnul UTF-8 (bitul 11) zipfile citeste numele ca cp437, dar zip-urile facute pe Linux il au tot in UTF-8:
			# userbouquet.Türksat.tv devenea userbouquet.T├╝rksat.tv si nu se mai potrivea cu randul din bouquets.tv. Un nume
			# cp437 adevarat (Türksat de pe Windows) nu e UTF-8 valid dupa intoarcere, deci ramane cum l-a citit zipfile.
			try:
				nume = nume.encode("cp437").decode("utf-8")
			except (UnicodeEncodeError, UnicodeDecodeError):
				pass
		self.name = nume.replace("\\", "/")
		mod = (info.external_attr >> 16) & 0xFFFF
		self._legatura = bool(mod) and stat.S_ISLNK(mod)
		self._dosar = info.filename.endswith(("/", "\\")) or (bool(mod) and stat.S_ISDIR(mod))
		self._criptat = bool(info.flag_bits & 0x1)
		self.mode = (mod & 0o7777) or 0o644
		self.size = info.file_size
		self.offset_data = 0

	def isreg(self):
		return not (self._dosar or self._legatura or self._criptat)

	isfile = isreg

	def isdir(self):
		return self._dosar


class _ArhivaZip(object):
	"""Un zip deschis in forma lui tarfile.TarFile, cat folosesc cautarea si pregatirea: membrii in ordine,
	extractfile, with."""

	def __init__(self, cale):
		import zipfile
		self._z = zipfile.ZipFile(cale)

	def __iter__(self):
		for info in self._z.infolist():
			yield _MembruZip(info)

	def extractfile(self, membru):
		if not membru.isreg():
			return None
		return self._z.open(membru.info)

	def close(self):
		self._z.close()

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		self.close()


class _Arhive(object):
	"""In locul modulului tarfile la citirea copiilor: open(cale) deschide un zip cu _ArhivaZip si orice altceva (si
	arhivele din interior, date ca fileobj) cu tarfile."""

	def __getattr__(self, nume):
		import tarfile
		return getattr(tarfile, nume)

	def open(self, name=None, mode="r", fileobj=None, **kw):
		import tarfile
		if fileobj is None and name and este_zip(os.path.basename(name)):
			return _ArhivaZip(name)
		return tarfile.open(name, mode, fileobj=fileobj, **kw)


def _arhive():
	return _Arhive()


def zip_pare_copie(cale):
	"""Lista de la coada zip-ului (fara decomprimare) are un fisier al importului sau o arhiva tar de copie. False
	pentru zip-urile care nu sunt copii (imaginile de scris pe stick, piconurile): se sar fara mesaj. True si cand
	zip-ul nu se poate citi: motivul il da cuprins_arhiva."""
	import zipfile
	try:
		with zipfile.ZipFile(cale) as z:
			for i, info in enumerate(z.infolist()):
				if i >= 20000:
					return True
				nume = posixpath.basename(info.filename.replace("\\", "/"))
				if fisier_permis(nume):
					return True
				# copia programata a unei imagini (o arhiva tar de copie inauntru); rootfs-ul unei imagini nu e copie
				if este_tar(nume) and 0 < info.file_size <= MAX_ARHIVA and not nume.lower().startswith("rootfs"):
					return True
	except Exception:
		return True
	return False


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
		"buchete": len([n for n in nume if TIPAR_BUCHET.match(n) or buchet_latin1(n)]),
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


def fel_fs_mediu(fel_fs):
	"""Felul sistemului de fișiere al unui stick, card sau disc (FS_MEDII, sau FUSE cu subtip: PREFIXE_FS_FUSE)."""
	f = (fel_fs or "").lower()
	return f in FS_MEDII or f.startswith(PREFIXE_FS_FUSE)


def _radacini_montari(cale_mountinfo):
	"""{punctul de montare: campul root din mountinfo} (ce dosar al partitiei arata montarea: "/" = toata partitia);
	{} cand fisierul lipseste."""
	rez = {}
	try:
		with open(cale_mountinfo, "r", encoding="utf-8", errors="surrogateescape") as f:
			for rand in f:
				a = rand.split(" - ", 1)[0].split()
				if len(a) >= 5:
					rez.setdefault(a[4].replace("\\040", " "), a[3].replace("\\040", " "))
	except (OSError, IOError):
		pass
	return rez


def medii(cale_mounts=CALE_MOUNTS, sys_block=CALE_SYS_BLOCK, citeste=None, realpath=None, discul_pornirii=False,
		cale_mountinfo=None, jurnal=None):
	"""Mediile pe care se caută: [{"punct", "dispozitiv", "fel" (stick / disc / intern), "eticheta"}], stick-urile
	întâi, apoi discurile, apoi celelalte partiții ale memoriei interne; un dispozitiv montat de două ori apare o
	dată. Rădăcina receptorului nu e o sursă. Cu HDS_COPIE_MEDII pusă (numai probele) și /proc/mounts implicit:
	mediile din variabilă (medii_de_proba).
	discul_pornirii (căutarea importului): când imaginea pornește de pe un stick sau un disc (un loc de pe USB sau HDD,
	root=/dev/sdaN), celelalte partiții ale lui sunt tot stickul sau discul omului, judecate ca orice stick sau disc;
	"intern" rămâne numai memoria de pe placă (mmcblk). Partiția rădăcinii montată ÎNTREAGĂ și altundeva (de pildă /media/hdd la
	un loc de pe disc, câmpul root din mountinfo = "/") intră și ea, cu "radacina": True; locul pornit acum se sare la
	căutare (_chei_proprii), deci imaginea nu se găsește pe ea însăși. jurnal (listă, opțional) primește câte un rând
	pentru fiecare montare a unui dispozitiv bloc care nu devine mediu, cu motivul."""
	if cale_mounts == CALE_MOUNTS and os.environ.get("HDS_COPIE_MEDII"):
		return medii_de_proba(os.environ["HDS_COPIE_MEDII"])
	montari = _montari(cale_mounts)
	dispozitiv_radacina = None
	for disp, punct, _fel in montari:
		if punct == "/":
			dispozitiv_radacina = disp
	disc_radacina = disc_din_dispozitiv(dispozitiv_radacina)
	radacini = {}
	if discul_pornirii:
		if cale_mountinfo is None and cale_mounts == CALE_MOUNTS:
			cale_mountinfo = "/proc/self/mountinfo"
		radacini = _radacini_montari(cale_mountinfo) if cale_mountinfo else {}

	def sarit(disp, punct, fel_fs, motiv):
		if jurnal is not None:
			jurnal.append("%s %s (%s): %s" % (disp, punct, fel_fs, motiv))

	rez = []
	vazute = set()
	for disp, punct, fel_fs in montari:
		disc = disc_din_dispozitiv(disp)
		if disc is None or punct == "/":
			continue
		if not fel_fs_mediu(fel_fs):
			sarit(disp, punct, fel_fs, "felul sistemului de fisiere")
			continue
		if TIPAR_MONTARE_LUCRU.match(punct):
			sarit(disp, punct, fel_fs, "montare de lucru a receptorului")
			continue
		radacina_intreaga = False
		if disp == dispozitiv_radacina:
			if radacini.get(punct) != "/":
				sarit(disp, punct, fel_fs, "partitia imaginii pornite (numai locul ei)")
				continue
			radacina_intreaga = True
		if punct.startswith(("/boot", "/proc", "/sys", "/dev")):
			sarit(disp, punct, fel_fs, "loc al sistemului")
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
		if disc == disc_radacina and (not discul_pornirii or disc.startswith("mmcblk")):
			fel = "intern"
		elif este_amovibil(disc, sys_block, citeste, realpath):
			fel = "stick"
		else:
			fel = "disc"
		m = {"punct": punct, "dispozitiv": disp, "fel": fel, "eticheta": eticheta(punct, disp)}
		if radacina_intreaga:
			m["radacina"] = True
		rez.append(m)
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
	if fel == "memorie":
		# locul altei imagini din memorie (surse_memorie); locul se vede in randul sursei (linuxrootfsN/etc/enigma2)
		return _("Memoria receptorului")
	if fel == "calculator":
		return _("Trimisă din calculator")
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
		versiune = info.get("imageversion") or info.get("version") or ""
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


def _loc_acces_membru(norm):
	"""Calea unui membru de arhivă trece printr-unul din locurile fișierelor modulelor de acces (sub orice rădăcină)."""
	c = "/" + norm + "/"
	return any("/" + loc + "/" in c for loc in _extra().LOCURI_ACCES)


def _membri_arhiva(t, nume_arhiva, max_membri, termen, max_decomprimat, interioare=None, extra=None, acces=None):
	"""{dosar: {nume}} cu fișierele din lista albă ale unei arhive deschise (`t`, citită în ordine), sau None la o
	limită depășită. În `interioare` (dacă e dată) pune membrii care sunt ei înșiși arhive de copie (fișiere obișnuite,
	nu legături, cel mult MAX_ARHIVA), în `extra` căile fișierelor rețelei și ale listelor de pachete (_rel_extra), iar
	în `acces` căile fișierelor obișnuite din locurile modulelor de acces (numai ca să fie numărate sub rădăcina copiei;
	nu se scot și nu ajung în sursă).
	La o limită (membri, octeți decomprimați, termenul), dosarul cu lamedb sau settings găsit până acolo rămâne: copiile
	complete ale altor imagini au după etc/enigma2 și ghidul TV, /home sau modulele, iar copia nu se pierde din cauza
	lor (pregătirea se oprește la aceeași limită, _scoate_din_arhiva). Fără un asemenea dosar: None."""
	pe_dosare = {}

	def la_limita(motiv):
		if _cel_mai_bun_dosar(pe_dosare) is not None:
			_jurnal("arhivă citită până la limită %s (%s); copia găsită până acolo rămâne" % (nume_arhiva, motiv))
			return pe_dosare
		_jurnal("arhivă sărită %s: %s" % (nume_arhiva, motiv))
		return None

	for i, m in enumerate(t):
		if i >= max_membri:
			return la_limita("prea mulți membri")
		if _prea_mult_decomprimat(m, max_decomprimat):
			return la_limita("prea mare după decomprimare")
		if termen is not None and i % 50 == 49 and time.time() > termen:
			return la_limita("s-a terminat timpul căutării")
		if not m.isreg():
			continue
		norm = _normalizat(m.name)
		if norm is None:
			continue
		dosar, nume = posixpath.split(norm)
		if fisier_permis(nume) and not _are_cam_fisier(norm):
			pe_dosare.setdefault(dosar, set()).add(nume)
		elif (acces is not None and len(acces) < _extra().MAX_FISIERE_ACCES and _loc_acces_membru(norm)
				and m.size <= _extra().MAX_FISIER_ACCES):
			acces.append(norm)
		elif (extra is not None and len(extra) < 64 and not _are_cam(norm) and 0 < m.size <= MAX_EXTRA
				and _rel_extra(norm)):
			extra.append(norm)
		elif (interioare is not None and este_tar(nume) and not nume.startswith(".") and not _are_cam(norm)
				and 0 < m.size <= MAX_ARHIVA):
			interioare.append(norm)
	return pe_dosare


def _cel_mai_bun_dosar(pe_dosare, extra=None, acces=None):
	bune = [(d, cuprins_dosar(n), len(n)) for d, n in (pe_dosare or {}).items()]
	bune = [b for b in bune if b[1]]
	if not bune:
		return None
	bune.sort(key=lambda b: (not b[0].endswith("etc/enigma2"), not b[0].endswith("enigma2"), -b[2], b[0]))
	dosar, cuprins = bune[0][0], bune[0][1]
	cuprins["extra"] = extra_sub_radacina(dosar, extra or ())
	cuprins["acces"] = len(acces_sub_radacina(dosar, acces or ()))
	return dosar, cuprins


def acces_sub_radacina(dosar, membri):
	"""Căile de sub rădăcina copiei (etc/enigma2 al ei, ca la extra_sub_radacina) ale membrilor `membri` care sunt
	fișiere ale modulelor de acces (HdsImportExtra.este_loc_acces); o copie plată nu are rădăcină, deci niciunul."""
	X = _extra()
	rad = X.radacina_copiei(dosar)
	if rad is None:
		return []
	rez = []
	for norm in membri:
		if rad and not norm.startswith(rad + "/"):
			continue
		rel = norm[len(rad) + 1:] if rad else norm
		if X.este_loc_acces(rel):
			rez.append(rel)
	return rez


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
				acces = []
				with tarfile.open(fileobj=f, mode="r|*") as interior:
					pe_dosare = _membri_arhiva(interior, "%s/%s" % (os.path.basename(cale), membru), max_membri,
						termen, max_decomprimat, extra=extra, acces=acces)
				return _cel_mai_bun_dosar(pe_dosare, extra, acces)
	return None


def _motiv_necitita(eroare):
	"""Felul motivului pentru o arhivă care nu se poate citi (necitite, text_necitite)."""
	import tarfile
	if isinstance(eroare, tarfile.ReadError):
		mesaj = str(eroare).lower()
		# arhiva tăiată: tarfile spune "unexpected end of data" sau "truncated", în rest nu e o arhivă tar
		return "rupta" if ("end of data" in mesaj or "truncated" in mesaj) else "nu_e_tar"
	if isinstance(eroare, (EOFError, tarfile.TarError)):
		return "rupta"
	if isinstance(eroare, OSError) and eroare.__class__.__name__ not in ("BadGzipFile", "LZMAError"):
		return "mediu"
	return "rupta"


def cuprins_arhiva(cale, max_membri=MAX_MEMBRI, termen=None, max_decomprimat=MAX_DECOMPRIMAT, necitite=None):
	"""(dosarul din arhivă, cuprinsul lui) pentru dosarul cu cele mai multe fișiere de import care are lamedb sau
	settings (etc/enigma2 întâi), sau None: arhivă stricată, fără așa ceva, cu prea mulți membri, cu prea mulți octeți
	decomprimați, sau căutarea a ajuns la `termen` (time.time()) în mijlocul ei. Când arhiva nu are direct așa ceva,
	dar are înăuntru alte arhive de copie (copia programată a unei imagini), se caută un nivel mai jos, în cel mult
	MAX_INTERIOARE dintre ele; atunci cuprinsul are și "interioara" (numele membrului). necitite (listă, opțional)
	primește (numele arhivei, motivul) când arhiva nu se poate citi deloc sau e prea mare pentru căutare: omul află de
	ce copia lui nu apare (asistența 821342: tar.tar sărită fără niciun mesaj)."""
	tarfile = _arhive()
	if este_zip(os.path.basename(cale)) and not zip_pare_copie(cale):
		return None
	interioare = []
	extra = []
	acces = []
	try:
		with tarfile.open(cale, "r:*") as t:
			pe_dosare = _membri_arhiva(t, os.path.basename(cale), max_membri, termen, max_decomprimat, interioare,
				extra, acces)
	except Exception as eroare:  # tarfile.TarError, EOFError, OSError, zlib.error, lzma.LZMAError
		_jurnal("arhivă necitită %s: %s" % (os.path.basename(cale), eroare.__class__.__name__))
		if necitite is not None:
			necitite.append((os.path.basename(cale), _motiv_necitita(eroare)))
		return None
	if pe_dosare is None:
		# prea mulți membri sau prea mult de decomprimat; termenul căutării atins nu e vina arhivei
		if necitite is not None and not (termen is not None and time.time() > termen):
			necitite.append((os.path.basename(cale), "prea_mare"))
		return None
	gasit = _cel_mai_bun_dosar(pe_dosare, extra, acces)
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
		ex = {"retea": False, "picon": False, "pachete": False, "acces": False}
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
		# fișierele modulelor de acces: numai dacă sunt (nicio cale, niciun nume)
		"acces": bool(cuprins.get("acces")) if fel == "arhiva" else bool(ex.get("acces")),
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


def _cheie_dosar(cale):
	try:
		st = os.stat(cale)
		return (st.st_dev, st.st_ino)
	except OSError:
		return None


def _chei_proprii():
	"""(dispozitiv, inod) ale rădăcinii și ale lui /etc/enigma2 ale imaginii pornite: pe partiția rădăcinii montată
	întreagă (mediul cu "radacina"), locul pornit acum nu e copia altei imagini și nu se citește."""
	return set(k for k in (_cheie_dosar("/"), _cheie_dosar(CALE_ETC)) if k)


def _radacina_imagine(dosare):
	"""Dosarul are forma rădăcinii unei imagini (etc lângă usr, bin sau sbin): rootfs-ul altui loc, o copie a
	rădăcinii."""
	return "etc" in dosare and any(n in dosare for n in ("usr", "bin", "sbin"))


def cauta_pe_mediu(mediu, termen, adancime=ADANCIME, max_dosare=MAX_DOSARE, max_arhiva=MAX_ARHIVA_MEDIU, necitite=None,
		proprii=None, stare=None):
	"""Sursele de pe un mediu, căutate în lățime până la `adancime` dosare sub rădăcina lui, până la `termen`;
	necitite (listă, opțional): arhivele sărite, cu motivul (cuprins_arhiva). Sub rădăcina unei imagini nu se coboară
	în dosarele sistemului (DOSARE_SISTEM, etc). Într-un dosar, arhivele cele mai noi se citesc întâi; cele de peste
	MAX_ARHIVA (până la max_arhiva) după tot restul mediului, cu timpul rămas; rootfs-ul unei imagini nu se citește.
	proprii: (dispozitiv, inod) ale dosarelor care nu se citesc (locul pornit acum, _chei_proprii). stare (dict,
	opțional) primește "dosare" (câte s-au citit) și "arhive" (câte s-au cercetat)."""
	radacina = mediu["punct"]
	gasite = []
	coada = [(radacina, 0)]
	citite = 0
	cercetate = [0]
	mari = []

	def cerceteaza(cale, rel, n, mare=False):
		lung = len(necitite) if necitite is not None else 0
		cercetate[0] += 1
		gasit = cuprins_arhiva(cale, termen=termen, necitite=necitite)
		if necitite is not None and len(necitite) > lung:
			# numele cu dosarul lui, ca în lista surselor
			necitite[-1] = (posixpath.join(rel, n), necitite[-1][1])
		elif mare and not gasit and necitite is not None and time.time() > termen:
			necitite.append((posixpath.join(rel, n), "prea_mare"))
		if gasit:
			gasite.append(_sursa(mediu, cale, "arhiva", gasit[1], _timp(cale), posixpath.join(rel, n),
				dosar_arhiva=gasit[0]))

	while coada and citite < max_dosare and time.time() < termen:
		dosar, nivel = coada.pop(0)
		if proprii and _cheie_dosar(dosar) in proprii:
			continue
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
			proprie = bool(proprii) and _cheie_dosar(e2) in proprii
			in_e2 = None if os.path.islink(e2) or proprie else _intrari(e2, termen)
			cuprins = cuprins_dosar(in_e2[0]) if in_e2 else None
			if cuprins:
				gasite.append(_sursa(mediu, e2, "dosar", cuprins, _timp_dosar(e2, in_e2[0]),
					posixpath.join(rel, "etc", "enigma2"), identifica_distributie(dosar)))
				if nivel > 0:
					continue
		if nivel < adancime:
			sistem = DOSARE_SISTEM + ("etc",) if _radacina_imagine(dosare) else ()
			coada.extend((os.path.join(dosar, n), nivel + 1) for n in dosare if n not in sistem)
		for n in sorted(arhive, key=lambda n: (-_timp(os.path.join(dosar, n)), n)):
			if time.time() >= termen:
				break
			if este_tar(n) and TIPAR_ROOTFS.match(n):
				continue
			cale = os.path.join(dosar, n)
			try:
				marime = os.path.getsize(cale)
			except OSError:
				continue
			limita = MAX_ZIP if este_zip(n) else max_arhiva
			if not 0 < marime <= limita:
				if necitite is not None and marime > limita:
					necitite.append((posixpath.join(rel, n), "prea_mare"))
				continue
			if not este_zip(n) and marime > MAX_ARHIVA:
				mari.append((cale, rel, n))
				continue
			cerceteaza(cale, rel, n)
	# arhivele mari (copiile complete ale altor imagini), după restul mediului, cele mai noi întâi
	for cale, rel, n in sorted(mari, key=lambda x: -_timp(x[0])):
		if time.time() >= termen:
			if necitite is not None:
				necitite.append((posixpath.join(rel, n), "prea_mare"))
			continue
		cerceteaza(cale, rel, n, mare=True)
	if stare is not None:
		stare.update(dosare=citite, arhive=cercetate[0])
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


def copii_calculator(termen, dosar=DOSAR_CALCULATOR, necitite=None):
	"""Arhiva trimisa din calculator (salveaza_din_calculator), ca sursa a mediului calculator; [] cand nu e."""
	if not os.path.isdir(dosar) or os.path.islink(dosar):
		return []
	return cauta_pe_mediu({"fel": "calculator", "punct": dosar, "eticheta": ""}, termen, adancime=0, necitite=necitite)


def sterge_din_calculator(dosar=DOSAR_CALCULATOR):
	"""Sterge arhivele trimise din calculator (numai fisierele din dosarul lor). Intoarce cate a sters."""
	n = 0
	try:
		nume = os.listdir(dosar)
	except OSError:
		return 0
	for x in nume:
		cale = os.path.join(dosar, x)
		if os.path.isfile(cale) and not os.path.islink(cale):
			try:
				os.remove(cale)
				n += 1
			except OSError:
				pass
	return n


def nume_din_calculator(nume):
	"""Numele fisierului trimis, fara dosare si fara semne care nu au ce cauta intr-un nume; "" cand nu e o arhiva."""
	nume = posixpath.basename((u"%s" % (nume or "")).replace("\\", "/")).strip()
	nume = "".join(c for c in nume if c.isprintable() and c not in '<>:"|?*')
	if not nume or nume.startswith(".") or len(nume) > 200 or not este_arhiva(nume):
		return ""
	return nume


def salveaza_din_calculator(nume, date, dosar=DOSAR_CALCULATOR, max_arhiva=MAX_ARHIVA):
	"""Scrie arhiva trimisa din pagina web in DOSAR_CALCULATOR (in locul celei de dinainte) si verifica de pe loc ca are o
	lista de canale sau setari (cuprins_arhiva). Intoarce calea; ValueError cu textul pentru om cand nu e buna."""
	n = nume_din_calculator(nume)
	if not n:
		raise ValueError(_("Alege o arhivă de copie: .tar.gz, .tgz, .tar, .tar.bz2, .tar.xz sau .zip."))
	if not date:
		raise ValueError(_("Fișierul trimis e gol."))
	if len(date) > max_arhiva:
		raise ValueError(_("Arhiva e prea mare: cel mult %d MB.") % (max_arhiva // (1024 * 1024)))
	if os.path.islink(dosar):
		raise ValueError(_("Arhiva nu se poate scrie pe receptor."))
	os.makedirs(dosar, exist_ok=True)
	try:
		os.chmod(dosar, 0o700)
	except OSError:
		pass
	sterge_din_calculator(dosar)
	cale = os.path.join(dosar, n)
	parte = cale + ".part"
	try:
		with open(parte, "wb") as f:
			f.write(date)
		os.replace(parte, cale)
	except (IOError, OSError):
		try:
			os.remove(parte)
		except OSError:
			pass
		raise ValueError(_("Arhiva nu se poate scrie pe receptor."))
	necitite = []
	gasit = cuprins_arhiva(cale, termen=time.time() + TERMEN_S, necitite=necitite)
	if not gasit:
		try:
			os.remove(cale)
		except OSError:
			pass
		motiv = text_necitite([("", n, necitite[-1][1])]) if necitite else []
		raise ValueError(motiv[0] if motiv else _("În arhivă nu am găsit o listă de canale sau setări."))
	return cale


# ---------------------------------------------------------------- locurile altor imagini din memoria receptorului

_LOCURI_MONTATE = {}    # dosarul montarii -> cate cautari si importuri il folosesc acum
_ZAVOR_LOCURI = threading.Lock()


def _montari_info(cale_mountinfo=CALE_MOUNTINFO):
	"""[(campul root, punctul, optiunile montarii, felul, dispozitivul)] din mountinfo, in ordine; [] cand lipseste."""
	rez = []
	try:
		with open(cale_mountinfo, "r", encoding="utf-8", errors="surrogateescape") as f:
			for rand in f:
				a, semn, b = rand.partition(" - ")
				a, b = a.split(), b.split()
				if semn and len(a) >= 6 and len(b) >= 2:
					rez.append((a[3].replace("\\040", " "), a[4].replace("\\040", " "), a[5], b[0], b[1]))
	except (OSError, IOError):
		pass
	return rez


def _locuri_din_startup():
	"""[(root=, rootsubdir=)] din fisierele de pornire ale locurilor (STARTUP_N, STARTUP_LINUX_N_BOXMODE_M), citite cu
	Components/HdsPornireMultipla.py de pe partitia de pornire deja montata (nimic montat, nimic scris): la HD51 locul 1
	sta pe alta partitie (p3) decat locurile 2-4 (p8). [] cand nu se pot citi."""
	try:
		from Components import HdsPornireMultipla as P
		boot = P.dosarBoot()
		if not boot:
			return []
		rez = []
		for _n, _fisier, date in P.startupuri(boot):
			st = P.citesteStartup(date)
			if st and not st.get("repetate"):
				rez.append((st["p"].get("root", ""), st["p"].get("rootsubdir", "")))
		return rez
	except Exception as eroare:
		_jurnal("locurile din memorie, fisierele de pornire: %s" % eroare.__class__.__name__)
		return []


def locuri_memorie(cale_mountinfo=CALE_MOUNTINFO, din_startup=None):
	"""Partitiile memoriei de pe placa (/dev/mmcblk0pN) cu locurile altor imagini (subdosarele linuxrootfsN):
	[{"dispozitiv", "fs", "baza", "monteaza", "subdosare", "acum"}]. Din randul lui / din mountinfo (campul root
	/linuxrootfsN = rootsubdir: partitia radacinii) si din fisierele de pornire (_locuri_din_startup). "baza": unde se vede
	toata partitia: o montare intreaga facuta deja de sistem (radacina flash la /boot la kexec), altfel DOSAR_MEMORIE, de
	montat ("monteaza"). "acum": subdosarul locului pornit (numai pe partitia radacinii). Radacina montata intreaga ca /
	(fara rootsubdir) nu intra: celelalte locuri ar fi chiar sub sistemul pornit."""
	info = _montari_info(cale_mountinfo)
	radacini = [x for x in info if x[1] == "/"]
	if not radacini:
		return []
	camp_root, _p, _o, _fs, dev_rad = radacini[-1]
	sub_acum = camp_root.strip("/")
	perechi = [(dev_rad, None)] if sub_acum else []
	for dev, sub in (din_startup or _locuri_din_startup)():
		if TIPAR_LOC_MEMORIE.match(sub or ""):
			perechi.append((dev, sub))
	rez = []
	pe_dispozitiv = {}
	for dev, sub in perechi:
		if not TIPAR_PARTITIE_MEMORIE.match(dev or "") or (dev == dev_rad and not sub_acum):
			continue
		if dev not in pe_dispozitiv:
			montari = [x for x in info if x[4] == dev]
			intregi = [x[1] for x in montari if x[0] == "/" and x[1] != "/" and not TIPAR_MONTARE_LUCRU.match(x[1])]
			loc = {"dispozitiv": dev, "fs": montari[0][3] if montari else "ext4",
				"baza": intregi[0] if intregi else DOSAR_MEMORIE % posixpath.basename(dev), "monteaza": not intregi,
				"subdosare": [], "acum": sub_acum if dev == dev_rad else ""}
			pe_dispozitiv[dev] = loc
			rez.append(loc)
		if sub and sub not in pe_dispozitiv[dev]["subdosare"]:
			pe_dispozitiv[dev]["subdosare"].append(sub)
	return rez


def _ruleaza(comanda):
	try:
		return subprocess.call(comanda, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	except OSError:
		return -1


def _numai_citire(real, dispozitiv, info):
	"""Montarea de deasupra din `real` e a dispozitivului si numai pentru citit (optiunile montarii, nu ale superblocului)."""
	ale_lui = [x for x in info if x[1] == real]
	return bool(ale_lui) and ale_lui[-1][4] == dispozitiv and "ro" in ale_lui[-1][2].split(",")


def _demonteaza(real, ruleaza, cale_mountinfo):
	for _i in range(4):    # si montarile puse una peste alta
		if not [x for x in _montari_info(cale_mountinfo) if x[1] == real]:
			return
		if ruleaza(["umount", real]) != 0:
			ruleaza(["umount", "-l", real])


def demonteaza_locul(dosar, ruleaza=None, cale_mountinfo=CALE_MOUNTINFO):
	"""Demonteaza dosarul unui loc din memorie si sterge dosarul gol (os.rmdir: niciodata cu ce e in el)."""
	_demonteaza(os.path.realpath(dosar), ruleaza or _ruleaza, cale_mountinfo)
	try:
		os.rmdir(dosar)
	except OSError:
		pass


def monteaza_numai_citire(dispozitiv, fs, dosar, ruleaza=None, cale_mountinfo=CALE_MOUNTINFO):
	"""Partitia locurilor din memorie montata NUMAI pentru citit in dosarul ei (DOSAR_MEMORIE % <partitia>). True numai
	cand mountinfo arata montarea noastra cu "ro"; altfel nu ramane nimic montat. Pe partitie nu se scrie nimic: una deja
	montata (rw, ca /) primeste a doua montare simpla (acelasi superbloc, fara reluarea jurnalului), facuta imediat ro numai
	pentru ea (remount,bind,ro, pe calea reala); una nemontata se monteaza ro,noload (fara reluarea jurnalului ext4)."""
	ruleaza = ruleaza or _ruleaza
	if fs != "ext4" or not TIPAR_PARTITIE_MEMORIE.match(dispozitiv or "") or \
			dosar != DOSAR_MEMORIE % posixpath.basename(dispozitiv):
		return False
	try:
		os.makedirs(dosar, 0o700, exist_ok=True)
	except OSError:
		return False
	real = os.path.realpath(dosar)
	if real == os.path.realpath("/"):
		return False
	info = _montari_info(cale_mountinfo)
	if [x for x in info if x[1] == real]:
		# ramasa de la o interfata oprita in timpul cautarii: buna numai daca e a partitiei si numai pentru citit
		if _numai_citire(real, dispozitiv, info):
			return True
		_demonteaza(real, ruleaza, cale_mountinfo)
		info = _montari_info(cale_mountinfo)
		if [x for x in info if x[1] == real]:
			return False
	if [x for x in info if x[4] == dispozitiv]:
		if ruleaza(["mount", "-t", fs, dispozitiv, real]) == 0:
			ruleaza(["mount", "-o", "remount,bind,ro", real])
	else:
		ruleaza(["mount", "-t", fs, "-o", "ro,noload", dispozitiv, real])
	if _numai_citire(real, dispozitiv, _montari_info(cale_mountinfo)):
		return True
	_jurnal("montarea numai pentru citit a lui %s nu s-a dovedit; nu citesc nimic de acolo" % dispozitiv)
	demonteaza_locul(dosar, ruleaza, cale_mountinfo)
	return False


class _LocMontat(object):
	"""Partitia unui loc din memorie montata numai pentru citit cat tine blocul (cautarea, importul); mem None = nimic de
	montat (partitia se vede deja intreaga). Cautarea si importul pot merge deodata: o singura montare, demontata de
	ultimul care iese. `with _LocMontat(mem) as montat:` (False = nemontata, nu se citeste nimic)."""

	def __init__(self, mem):
		self.mem = mem
		self.luat = False

	def __enter__(self):
		if not self.mem:
			return True
		d = self.mem.get("dosar") or ""
		with _ZAVOR_LOCURI:
			n = _LOCURI_MONTATE.get(d, 0)
			if n == 0 and not monteaza_numai_citire(self.mem.get("dispozitiv") or "", self.mem.get("fs") or "ext4", d):
				return False
			_LOCURI_MONTATE[d] = n + 1
		self.luat = True
		return True

	def __exit__(self, *exc):
		if self.luat:
			d = self.mem.get("dosar") or ""
			with _ZAVOR_LOCURI:
				n = _LOCURI_MONTATE.get(d, 1) - 1
				if n > 0:
					_LOCURI_MONTATE[d] = n
				else:
					_LOCURI_MONTATE.pop(d, None)
					demonteaza_locul(d)
		return False


def _numar_loc(sub):
	try:
		return int(sub[len("linuxrootfs"):])
	except ValueError:
		return 0


def surse_memorie(termen, cautate=(), necitite=None, cale_mountinfo=CALE_MOUNTINFO, din_startup=None):
	"""Sursele din locurile altor imagini din memoria receptorului (locuri_memorie), mediul "memorie", fara locul pornit
	acum (subdosarul lui si cheia dispozitiv/inod a lui /). Partitia se monteaza numai pentru citit cat tine cautarea si
	se demonteaza la capat; sursa tine "memorie" (dispozitivul, felul, dosarul), ca importul sa o monteze din nou.
	cautate: dispozitivele cautate deja ca medii (partitia montata intreaga la /media/hdd), sarite aici. necitite (lista,
	optional) primeste (locul, numele arhivei, motivul)."""
	rez = []
	proprii = None
	for loc in locuri_memorie(cale_mountinfo, din_startup):
		dev = loc["dispozitiv"]
		if dev in cautate or time.time() >= termen:
			continue
		mem = {"dispozitiv": dev, "fs": loc["fs"], "dosar": loc["baza"]} if loc["monteaza"] else None
		with _LocMontat(mem) as montat:
			if not montat:
				_jurnal("locurile din memorie: %s nu s-a putut monta numai pentru citit; sărit" % dev)
				continue
			if proprii is None:
				proprii = _chei_proprii()
			baza = loc["baza"]
			try:
				in_baza = [n for n in os.listdir(baza) if TIPAR_LOC_MEMORIE.match(n)]
			except OSError:
				in_baza = []
			for sub in sorted(set(loc["subdosare"]) | set(in_baza), key=_numar_loc):
				punct = os.path.join(baza, sub)
				if sub == loc["acum"] or os.path.islink(punct) or not os.path.isdir(punct) or time.time() >= termen:
					continue
				sarite, cifre = [], {}
				gasite = cauta_pe_mediu({"punct": punct, "dispozitiv": dev, "fel": "memorie", "eticheta": sub}, termen,
					necitite=sarite, proprii=proprii, stare=cifre)
				_jurnal("locul %s din memorie (%s, %s): %d dosare citite, %d arhive cercetate, %d surse" % (sub, dev,
					"montat numai pentru citit" if mem else baza, cifre.get("dosare", 0), cifre.get("arhive", 0),
					len(gasite)))
				if necitite is not None:
					necitite.extend((sub, posixpath.join(sub, nume), motiv) for nume, motiv in sarite)
				for s in gasite:
					s["rel"] = posixpath.join(sub, s["rel"]) if s.get("rel") else sub
					s["punct"] = baza
					if mem:
						s["memorie"] = dict(mem)
					rez.append(s)
	return rez


def cauta_surse(cale_mounts=CALE_MOUNTS, sys_block=CALE_SYS_BLOCK, dosar_etc=CALE_ETC, termen_s=TERMEN_S,
		citeste=None, realpath=None, necitite=None, dosar_calculator=DOSAR_CALCULATOR, cale_mountinfo=None, memorie=None):
	"""Toate sursele, în ordinea arătată: stick-urile (cele mai noi copii întâi), discurile, memoria internă, locurile
	altor imagini din memorie (surse_memorie), copiile receptorului. Rulează pe un fir separat. necitite (listă,
	opțional) primește (mediul, numele arhivei, motivul) pentru arhivele de copie care nu se pot citi (text_necitite);
	aceeași listă rămâne și în _NECITITE, de unde o ia porneste_cautarea (semnătura apelului din Lucrare rămâne cea
	veche). memorie: locurile din memorie se caută (None: numai pe receptor, cu /proc/mounts adevărat)."""
	termen = time.time() + termen_s
	surse = []
	vazute = set()
	colector = []
	# intai arhiva trimisa chiar acum din calculator (pagina web /import)
	for s in copii_calculator(termen, dosar_calculator):
		if s["id"] not in vazute:
			vazute.add(s["id"])
			surse.append(s)
	# un rand de jurnal pentru fiecare montare sarita si pentru fiecare mediu cautat: raportul receptorului spune singur
	# de ce o copie nu apare
	sarite_medii = []
	lista_medii = medii(cale_mounts, sys_block, citeste, realpath, discul_pornirii=True, cale_mountinfo=cale_mountinfo,
		jurnal=sarite_medii)
	for rand in sarite_medii:
		_jurnal("montare sărită: %s" % rand)
	# locurile altor imagini din memoria receptorului (pornire multipla), fara stick, fara cele cautate deja ca medii:
	# intai (dureaza putin, cu termenul lor), ca stickurile si discurile mari sa nu le ia timpul; in lista vin dupa ele
	if memorie is None:
		memorie = cale_mounts == CALE_MOUNTS and not os.environ.get("HDS_COPIE_MEDII")
	din_memorie, sarite_memorie = [], []
	if memorie:
		try:
			cautate = set(m.get("dispozitiv") for m in lista_medii if m.get("dispozitiv"))
			din_memorie = surse_memorie(min(termen, time.time() + TERMEN_MEMORIE_S), cautate, sarite_memorie,
				cale_mountinfo or CALE_MOUNTINFO)
		except Exception as eroare:
			_jurnal("locurile din memorie: %s" % eroare)
	proprii = _chei_proprii() if any(m.get("radacina") for m in lista_medii) else None
	for mediu in lista_medii:
		sarite = []
		cifre = {}
		gasite = cauta_pe_mediu(mediu, termen, necitite=sarite, proprii=proprii if mediu.get("radacina") else None,
			stare=cifre)
		_jurnal("mediul %s (%s, %s%s): %d dosare citite, %d arhive cercetate, %d surse, %d arhive sărite%s" % (
			mediu.get("punct"), mediu.get("dispozitiv") or "-", mediu.get("fel"),
			", partiția rădăcinii" if mediu.get("radacina") else "", cifre.get("dosare", 0), cifre.get("arhive", 0),
			len(gasite), len(sarite), ", timpul căutării s-a terminat" if time.time() >= termen else ""))
		colector.extend((mediu.get("eticheta") or "", nume, motiv) for nume, motiv in sarite)
		for s in gasite:
			if s["id"] not in vazute:
				vazute.add(s["id"])
				surse.append(s)
	colector.extend(sarite_memorie)
	for s in din_memorie:
		if s["id"] not in vazute:
			vazute.add(s["id"])
			surse.append(s)
	for s in copii_receptor(dosar_etc):
		if s["id"] not in vazute:
			vazute.add(s["id"])
			surse.append(s)
	_NECITITE[:] = colector
	if necitite is not None:
		necitite.extend(colector)
	return surse


_NECITITE = []    # arhivele sărite la ultima căutare (cauta_surse), pentru porneste_cautarea


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
	if s.get("acces"):
		parti.append(_("module de acces"))
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
		"acces": _("Module de acces"),
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
		"acces": _("Fișierele modulelor de acces, copiate așa cum sunt, și modulele, instalate din nou din sursele de "
			"pachete."),
		"pachete": _("Pluginurile din copie, oferite după import ca să le instalezi."),
	}.get(cheie, "")


def text_fara_surse():
	return _("Nu am găsit nicio copie a canalelor. Pune în receptor un stick USB care are o copie: dosarul "
		"etc/enigma2 al altei imagini, un dosar cu lamedb și bouquets.tv sau o arhivă de copie (.tar.gz sau .zip), apoi "
		"alege „Caută din nou”.")


def text_necitite(necitite):
	"""Rândurile de sub lista surselor pentru arhivele de copie sărite: [(mediul, numele, motivul)] -> [text]."""
	motive = {
		"nu_e_tar": _("nu e o arhivă tar sau tar.gz (poate e alt fel de arhivă, cu nume schimbat)"),
		"rupta": _("e ruptă: copiată sau descărcată pe jumătate"),
		"mediu": _("nu se poate citi de pe stick sau disc"),
		# limitele cautarii s-au schimbat (MAX_ARHIVA_MEDIU, MAX_MEMBRI): textul fara cifre, deja tradus
		"prea_mare": _("arhiva e prea mare"),
	}
	randuri = []
	for _mediu, nume, motiv in necitite or []:
		randuri.append(_("Arhiva %s nu apare în listă: %s.") % (nume, motive.get(motiv, motive["rupta"])))
	return randuri


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
		max_decomprimat=MAX_DECOMPRIMAT, cu_acces=False):
	"""(dosarul din care se importă, None) sau (None, motiv). Un dosar se folosește pe loc; dintr-o arhivă se scriu
	numai fișierele obișnuite din lista albă aflate în dosarul găsit la căutare, întâi în dosarul acestei pregătiri
	(`dest`.<n>), care devine `dest` numai dacă între timp nu a pornit o pregătire mai nouă. `cu_acces` (alegerea
	„acces”): și fișierele modulelor de acces de sub rădăcina copiei, ca atare, în <dosar>/extra/<cale>. Rulează pe un
	fir separat."""
	with _InLucru():
		return _pregateste(sursa, dest, max_membri, max_octeti, max_decomprimat, cu_acces)


def _pregateste(sursa, dest, max_membri, max_octeti, max_decomprimat, cu_acces=False):
	if sursa.get("fel") == "dosar":
		if not os.path.isdir(sursa.get("cale", "")):
			return None, _("dosarul nu mai există: %s") % sursa.get("cale", "")
		return sursa["cale"], None
	tarfile = _arhive()
	cale = sursa.get("cale", "")
	try:
		if os.path.getsize(cale) > (MAX_ZIP if este_zip(os.path.basename(cale)) else MAX_ARHIVA_MEDIU):
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
				max_octeti, max_decomprimat, extra, cu_acces and sursa.get("acces"))
		try:
			os.remove(cale_interioara)
		except OSError:
			pass
	else:
		rez = _scoate_din_arhiva(tarfile, cale, sursa.get("dosar_arhiva", ""), lucru, max_membri, max_octeti,
			max_decomprimat, extra, cu_acces and sursa.get("acces"))
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


def _scoate_din_arhiva(tarfile, cale, dosar_arhiva, lucru, max_membri, max_octeti, max_decomprimat, extra=(),
		cu_acces=False):
	"""Scrie în `lucru` fișierele din lista albă aflate în `dosar_arhiva`, iar în `lucru`/extra fișierele `extra` (căi
	de sub rădăcina copiei: rețeaua, listele pachetelor) și, cu `cu_acces`, fișierele modulelor de acces de sub rădăcina
	copiei (HdsImportExtra.este_loc_acces), ca atare, cu limitele lor (MAX_FISIERE_ACCES, MAX_FISIER_ACCES,
	MAX_TOTAL_ACCES; ce trece de ele se lasă, fără eroare); None dacă a mers, altfel motivul. La limita membrilor sau a
	octeților decomprimați, cu lamedb sau settings deja scrise (ca la căutare, _membri_arhiva): ce s-a scris rămâne și
	pregătirea merge mai departe."""
	scrise = 0
	esentiale = 0
	total = 0
	X = _extra()
	rad_copie = X.radacina_copiei(dosar_arhiva)
	cu_acces = bool(cu_acces) and rad_copie is not None
	acces_scrise = 0
	acces_total = 0
	rad = rad_copie or ""
	# fișierele rețelei și listele pachetelor găsite la căutare: în <lucru>/extra/<calea de sub rădăcina copiei>
	dorite = dict(((rad + "/" + rel) if rad else rel, rel) for rel in (extra or ()) if _extra().fel_extra(rel))
	try:
		with tarfile.open(cale, "r:*") as t:
			for i, m in enumerate(t):
				if i >= max_membri or _prea_mult_decomprimat(m, max_decomprimat):
					if esentiale:
						_jurnal("arhivă scoasă până la limită %s: %d fișiere" % (os.path.basename(cale), scrise))
						break
					if i >= max_membri:
						return _("arhiva are prea multe fișiere")
					return _("arhiva e prea mare după decomprimare")
				norm = _normalizat(m.name)
				if norm is None or not m.isreg():
					continue
				dosar, nume = posixpath.split(norm)
				rel_acces = None
				if cu_acces and (not rad or norm.startswith(rad + "/")):
					rel_acces = norm[len(rad) + 1:] if rad else norm
					if not X.este_loc_acces(rel_acces):
						rel_acces = None
				if rel_acces is not None:
					# fișierul unui modul de acces: scris ca atare (octeții din arhivă, fără să fie citit ca text)
					if (acces_scrise >= X.MAX_FISIERE_ACCES or m.size > X.MAX_FISIER_ACCES
							or acces_total + m.size > X.MAX_TOTAL_ACCES):
						continue
					f = t.extractfile(m)
					if f is None:
						continue
					tinta = os.path.join(lucru, "extra", *rel_acces.split("/"))
					os.makedirs(os.path.dirname(tinta), mode=0o700, exist_ok=True)
					with open(tinta, "wb") as g:
						shutil.copyfileobj(f, g, 65536)
					os.chmod(tinta, 0o755 if m.mode & 0o111 else 0o600)
					acces_scrise += 1
					acces_total += m.size
					continue
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
				if nume == "lamedb" or nume in NUME_SETARI:
					esentiale += 1
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


def chei_tuner_imagine(chei, toate=None, radacini=()):
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
	`toate`: toate cheile din settings-ul sursei (semnele imaginii); implicit `chei`.
	`radacini`: intrarile fizice de satelit dovedite de topologia receptorului."""
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
	# Numai sursa cunoscuta si radacinile fizice pot completa implicitul nescris.
	# Nu completam o radacina cu chei explicite sau o copie cu o radacina activa.
	if single and radacini and not any(rez.get("config.Nims.%s.configMode" % s,
			"simple" if s == min(radacini) else "nothing") in ("simple", "advanced") for s in radacini):
		for slot in radacini:
			prefix = "config.Nims.%s." % slot
			if any(k.startswith(prefix) for k in chei):
				continue
			rez.update({prefix + "configMode": "simple", prefix + "diseqcMode": "single",
				prefix + "diseqcA": "192"})
			note.append(_("Tunerul %s: copia nu avea chei salvate; am păstrat valorile implicite ale sursei: "
				"mod simplu, un LNB, 19,2°E.") % _litera_tuner(str(slot)))
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


def chei_setari_cu_note(cale, tunere, generale, radacini=()):
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
	tuner, note = chei_tuner_imagine(tuner, toate, radacini)
	restul.update(tuner)
	return restul, note


def chei_setari(cale, tunere, generale):
	"""{cheie: valoare} din settings-ul sursei, numai cu prefixele alese (chei_setari_cu_note, fără note)."""
	return chei_setari_cu_note(cale, tunere, generale)[0]


def _buchet_din_rand(rand):
	"""Numele fișierului din "#SERVICE 1:7:...:FROM BOUQUET "userbouquet.x.tv" ORDER BY bouquet", sau None."""
	m = TIPAR_RAND_INDEX.match(rand.strip())
	return m.group(1) if m else None


def locuri_extensii(dest=CALE_ETC):
	"""Buchetele rădăcină ale locurilor extensiilor (Components/HdsLocuriLista.py, de pildă Radio online:
	userbouquet.radioonline.radio): le scrie și le leagă extensia din starea ei, nu din lista de canale."""
	rez = set()
	dosar = os.path.join(dest, DOSAR_LOCURI)
	try:
		nume = os.listdir(dosar)
	except OSError:
		return rez
	for n in nume:
		if not n.endswith(".json"):
			continue
		try:
			with open(os.path.join(dosar, n), "r", encoding="utf-8", errors="replace") as f:
				d = json.loads(f.read(MAX_LOC))
		except (OSError, IOError, ValueError):
			continue
		buchet = d.get("buchet") if isinstance(d, dict) else None
		if isinstance(buchet, str) and TIPAR_BUCHET.match(buchet):
			rez.add(buchet)
	return rez


def nu_depinde_de_lista(cale):
	"""Buchetul nu depinde de lista de canale (lamedb): are numai fluxuri de internet și trimiteri la alte buchete (IPTV,
	Radio online și DVB-I au sub-buchete), sau e gol; etichetele (1:64) nu contează. Același semn ca la listele de pe
	internet (Components/HdsListeInternet._fara_lista). Un fișier care nu se poate citi: False."""
	try:
		with open(cale, "r", encoding="utf-8", errors="surrogateescape") as f:
			for rand in f:
				r = rand.strip()
				if not TIPAR_SERVICIU.match(r) or TIPAR_ETICHETA.match(r):
					continue
				mic = r.lower()
				if "%3a//" in mic or "http" in mic or TIPAR_TRIMITERE.match(r):
					continue
				return False
	except (OSError, IOError):
		return False
	return True


def buchete_imagine_pe_receptor(dest=CALE_ETC):
	"""Numele buchetelor imaginii care sunt acum pe receptor (userbouquet.hds* și rădăcinile locurilor extensiilor,
	locuri_extensii). Importul nu le înlocuiește cu cele din copie."""
	locuri = locuri_extensii(dest)
	try:
		nume = os.listdir(dest)
	except OSError:
		return set()
	return set(n for n in nume if TIPAR_BUCHET.match(n) and (n.startswith(PREFIX_BUCHETE_IMAGINE) or n in locuri)
		and os.path.isfile(os.path.join(dest, n)))


def randuri_buchete_imagine(dest=CALE_ETC, ale_omului=True):
	"""{index: [rânduri]}: rândurile din bouquets.tv / bouquets.radio de acum care arată spre buchete care nu țin de
	lista de canale și al căror fișier există, în ordinea lor: ale imaginii (userbouquet.hds*: IPTV, DVB-I, DAB+ și
	DVB-T2 din satelit, puse de modulele lor, și rădăcinile locurilor extensiilor, locuri_extensii) și, cu `ale_omului`,
	buchetele omului care nu depind de lamedb (nu_depinde_de_lista; fără BUCHETE_LISTEI). Citit înainte ca importul să
	înlocuiască indexul."""
	rez = {}
	locuri = locuri_extensii(dest)
	for index in INDEXURI_BUCHETE:
		try:
			with open(os.path.join(dest, index), "r", encoding="utf-8", errors="surrogateescape") as f:
				randuri = f.read().splitlines()
		except (OSError, IOError):
			continue
		ale = []
		vazute = set()
		for rand in randuri:
			nume = _buchet_din_rand(rand)
			if not nume or nume in vazute or "/" in nume or not os.path.isfile(os.path.join(dest, nume)):
				continue
			if nume.startswith(PREFIX_BUCHETE_IMAGINE) or nume in locuri or (ale_omului and TIPAR_BUCHET.match(nume)
					and nume not in BUCHETE_LISTEI and nu_depinde_de_lista(os.path.join(dest, nume))):
				vazute.add(nume)
				ale.append(rand.rstrip())
		if ale:
			rez[index] = ale
	return rez


def pune_la_loc_buchetele_imaginii(dest, ale_imaginii, nume_adaugate=None):
	"""După ce importul a înlocuit indexul cu al copiei: rândurile din randuri_buchete_imagine care lipsesc din el se
	adaugă la sfârșit, în ordinea lor, fiecare în indexul din care era (altfel IPTV, Radio online, DVB-I, listele DAB+ și
	DVB-T2 din satelit și fluxurile omului dispăreau din lista de canale, iar semnul de "pus o dată" nu le mai punea).
	Întoarce câte rânduri s-au adăugat; numele lor intră în `nume_adaugate`, dacă e dat."""
	adaugate = 0
	for index, randuri in (ale_imaginii or {}).items():
		cale = os.path.join(dest, index)
		try:
			with open(cale, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
				text = f.read()
		except (OSError, IOError):
			continue
		are = set(n for n in (_buchet_din_rand(r) for r in text.splitlines()) if n)
		lipsa = []
		for r in randuri:
			nume = _buchet_din_rand(r)
			if nume and nume not in are:
				are.add(nume)
				lipsa.append(r)
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
			if nume_adaugate is not None:
				nume_adaugate.extend(_buchet_din_rand(r) for r in lipsa)
		except (OSError, IOError) as eroare:
			_jurnal("buchetele imaginii în %s: %s" % (index, eroare))
	return adaugate


def _decodat_ca_nucleul(nume):
	"""Numele din referinta asa cum il deschide nucleul: %xx decodat (lib/service/service.cpp, decode)."""
	return re.sub(r"%([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), nume) if "%" in nume else nume


def scoate_randurile_fara_fisier(dest, indexuri, scoase=None):
	"""Dupa ce importul a scris indexurile copiei (`indexuri`, din INDEXURI_BUCHETE): randurile lor care trimit la un
	userbouquet al carui fisier nu e pe receptor (lipsea din copie sau importul nu l-a putut lua) se scot, ca buchetul sa
	nu ramana in lista fara sa se poata deschide. Raman ale imaginii (userbouquet.hds*, radacinile din hds_locuri), cele
	ale listei (favoritele, ultima scanare: le reface nucleul) si randurile cu nume de cale. Restul textului ramane
	octet cu octet. Intoarce cate randuri s-au scos; numele lor intra in `scoase`, daca e dat."""
	locuri = locuri_extensii(dest)
	n = 0
	for index in indexuri:
		cale = os.path.join(dest, index)
		try:
			with open(cale, "r", encoding="utf-8", errors="surrogateescape", newline="") as f:
				text = f.read()
		except (OSError, IOError):
			continue
		randuri = text.split("\n")
		ramase = []
		for rand in randuri:
			nume = _buchet_din_rand(rand)
			if (nume and nume.startswith("userbouquet.") and "/" not in nume
					and not nume.startswith(PREFIX_BUCHETE_IMAGINE) and nume not in locuri and nume not in BUCHETE_LISTEI
					and not os.path.isfile(os.path.join(dest, nume))
					and not os.path.isfile(os.path.join(dest, _decodat_ca_nucleul(nume)))):
				n += 1
				if scoase is not None:
					scoase.append(nume)
				continue
			ramase.append(rand)
		if len(ramase) == len(randuri):
			continue
		try:
			with open(cale + ".nou", "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
				f.write("\n".join(ramase))
			os.replace(cale + ".nou", cale)
		except (OSError, IOError) as eroare:
			_jurnal("randurile fara fisier din %s: %s" % (index, eroare))
	return n


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
		context=None, dest_picon=None, catalog=None, radacina_pregatita=None, rad_sistem="/", opkg=None):
	"""Importul din `dosar` în `dest`, după alegeri ({"canale", "tunere", "temporizatoare", "retea", "picon",
	"generale", "acces", "pachete"}: bool). `rad_sistem`, `opkg`: rădăcina receptorului și comanda opkg pentru modulele
	de acces (numai probele le schimbă). `sursa`: sursa aleasă (locurile piconurilor, ale rețelei și ale listei pluginurilor);
	`context`: ce s-a citit pe firul enigma2 înainte (context_import: valorile permise ale setărilor sigure).
	Întâi copia de siguranță a fișierelor de acum: copie(dest) -> (dosar, fișiere, eroare), implicit
	copie_de_siguranta cu `text_setari`; cu eroare importul nu pornește. Apoi canalele și buchetele, înregistrările
	programate și cheile de setări în settings.din-copie. Întoarce {"ok", "mesaje", "canale", "setari",
	"temporizatoare"}; "canale" > 0 cere reîncărcarea listei de canale, care se face pe firul enigma2
	(incheie_importul); `reincarca`, dacă e dat, se cheamă aici (probele). Rulează pe firul importului: numai fișiere."""
	with _InLucru():
		return _importa(dosar, alegeri, dest, copie, setari, reincarca, text_setari, sursa, context, dest_picon,
			catalog, radacina_pregatita, rad_sistem, opkg)


def _importa(dosar, alegeri, dest, copie, setari, reincarca, text_setari, sursa=None, context=None, dest_picon=None,
		catalog=None, radacina_pregatita=None, rad_sistem="/", opkg=None):
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
		# ale omului numai când sursa nu e o copie a acestui receptor (întoarcerea aduce lista exact cum era în copie)
		din_copia_receptorului = isinstance(sursa, dict) and sursa.get("mediu") == "receptor"
		ale_imaginii = randuri_buchete_imagine(dest, ale_omului=not din_copia_receptorului)
		# buchetele imaginii de pe receptor rămân ale lui; cele din copie (alt receptor HD Satelit, o copie mai veche) nu
		# le înlocuiesc: IPTV-ul își are sub-buchetele și sursele numai aici, DVB-I, Radio online și releele la fel
		ale_receptorului = buchete_imagine_pe_receptor(dest)
		pozitii_inainte = _pozitii_lamedb(os.path.join(dest, "lamedb"))
		lamedb_copiat = False
		copiate = 0
		indexuri_copiate = []
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
				if nume in INDEXURI_BUCHETE:
					indexuri_copiate.append(nume)
		if lamedb_copiat:
			_noteaza_originea(dest, dosar, pozitii_inainte, sursa)
		neluate = []
		for cale in sorted(glob.glob(os.path.join(dosar, "userbouquet.*"))):
			nume = nume_tinta(os.path.basename(cale))
			if nume in ale_receptorului:
				neluate.append(nume)
				continue
			if TIPAR_BUCHET.match(nume) and os.path.isfile(cale) and _copiaza(cale, os.path.join(dest, nume), mesaje):
				copiate += 1
		if neluate:
			_jurnal("buchetele imaginii rămân cele de pe receptor, nu cele din copie: %s" % ", ".join(neluate))
		rez["canale"] = copiate
		if copiate:
			importate.append(ngettext("canale și buchete (%d fișier)", "canale și buchete (%d fișiere)", copiate)
				% copiate)
			pastrate = []
			pune_la_loc_buchetele_imaginii(dest, ale_imaginii, pastrate)
			if pastrate:
				rez["buchete_pastrate"] = pastrate
				_jurnal("buchete păstrate în index (nu țin de lista de canale): %s" % ", ".join(pastrate))
			fara_fisier = []
			scoate_randurile_fara_fisier(dest, indexuri_copiate, fara_fisier)
			if fara_fisier:
				_jurnal("randuri scoase din index (fisierul buchetului nu e in copie sau nu s-a putut lua): %s"
					% ", ".join(fara_fisier))
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
		chei, note_tunere = chei_setari_cu_note(cale_setari, alegeri.get("tunere"), False,
			(context or {}).get("radacini_satelit", ()))
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
				rez["note_tunere"] = note_tunere
				mesaje.append(_("Setări pregătite: %d. Se aplică după repornirea interfeței.") % len(chei))
				if in_asteptare > len(chei):
					mesaje.append(_("Setări importate care așteaptă repornirea interfeței: %d.") % in_asteptare)
	_importa_extra(dosar, alegeri, rez, sursa, context, dest_picon, catalog, radacina_pregatita)
	_importa_acces(dosar, alegeri, rez, sursa, radacina_pregatita, rad_sistem, opkg)
	acces = rez.get("acces") or {}
	rez["ok"] = bool(rez["canale"] or rez["setari"] or rez.get("temporizatoare") or rez.get("picon")
		or rez.get("_retea") or (rez.get("pachete") or {}).get("total") or acces.get("copiate")
		or acces.get("puse"))
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


def _importa_acces(dosar, alegeri, rez, sursa, radacina_pregatita, rad_sistem="/", opkg=None):
	"""Modulele de acces din copie (HdsImportExtra.importa_acces), pe firul importului, cu alegerea „acces”: fișierele
	de sub rădăcina copiei (dosarul altei imagini pe mediu sau, la o arhivă, <pregătire>/extra), listele ei de pachete.
	În rez["acces"] ajung numai numere și nume de pachete; modulul de ales stă în rez["_acces_alege"], scos de
	incheie_importul (alegerea se face pe firul enigma2)."""
	if not sursa or not alegeri.get("acces"):
		return
	X = _extra()
	fel = sursa.get("fel")
	try:
		if fel == "arhiva":
			rad_copie = radacina_pregatita or os.path.join(dosar, "extra")
			loc = X.locuri_extra(sursa.get("cale", ""), "arhiva", sursa.get("cale", ""), rad_copie)
		else:
			rad_copie = X.radacina_copiei(sursa.get("cale", dosar))
			loc = X.locuri_extra(sursa.get("cale", dosar), "dosar")
		if not rad_copie:
			return
		r = X.importa_acces(rad_copie, loc.get("pachete") or [], rad_sistem, opkg)
	except Exception as eroare:
		_jurnal("modulele de acces: %s" % eroare.__class__.__name__)
		rez["mesaje"].append(_("Modulele de acces nu s-au putut aduce din copie."))
		return
	alege = r.pop("alege", None)
	if alege:
		rez["_acces_alege"] = alege
	rez["acces"] = r
	rez["mesaje"].extend(X.texte_acces(r))


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
		context=None, dest_picon=None, catalog=None, rad_sistem="/", opkg=None):
	"""Tot lucrul importului de pe firul lui: pregătirea sursei, importul (fără reîncărcarea listei), apoi ștergerea
	fișierelor scoase din arhivă. `anulat` (threading.Event): pus înainte de import (ecranul închis cât se pregătea
	copia), nu se mai scrie nimic pe receptor. Sursa dintr-un loc al memoriei ("memorie"): partiția lui montată numai
	pentru citit cât ține tot importul, apoi demontată."""
	mem = sursa.get("memorie") if isinstance(sursa, dict) else None
	with _InLucru(), _LocMontat(mem if isinstance(mem, dict) else None) as montat:
		try:
			if not montat:
				return {"ok": False, "mesaje": [_("Importul nu a pornit: %s.") % (_("dosarul nu mai există: %s")
					% sursa.get("cale", ""))]}
			dosar, motiv = pregateste(sursa, dest_tmp, cu_acces=bool(alegeri.get("acces")))
			if dosar is None:
				return {"ok": False, "mesaje": [_("Importul nu a pornit: %s.") % motiv]}
			if anulat is not None and anulat.is_set():
				return {"ok": False, "anulat": True, "mesaje": [_("Importul s-a oprit înainte să schimbe ceva.")]}
			return importa(dosar, alegeri, dest=dest, text_setari=text_setari, sursa=sursa, context=context,
				dest_picon=dest_picon, catalog=catalog,
				radacina_pregatita=os.path.join(dosar, "extra") if sursa.get("fel") == "arhiva" else None,
				rad_sistem=rad_sistem, opkg=opkg)
		finally:
			curata_tmp(dest_tmp)


def context_import(alegeri):
	"""Pe firul enigma2, înainte de firul importului: ce nu se poate citi de pe alt fir (arborele config: valorile
	permise ale setărilor sigure și modurile video declarate de televizor)."""
	context = {}
	if alegeri.get("tunere"):
		try:
			from Components.NimManager import nimmanager
			context["radacini_satelit"] = tuple(t.slot for t in nimmanager.nim_slots
				if t.isCompatible("DVB-S") and getattr(t, "fbc_role", 0) in (0, 1))
		except Exception as eroare:
			_jurnal("topologia tunerelor: %s" % eroare.__class__.__name__)
	if alegeri.get("generale"):
		try:
			context["setari"] = _extra().context_setari()
		except Exception as eroare:
			_jurnal("setările sigure: %s" % eroare.__class__.__name__)
			context["setari"] = {}
	return context


def incheie_importul(rez, eroare=None, reincarca=None, incarca=None, dest=CALE_ETC, dupa=None, aplica_retea=None,
		alege_modul=None):
	"""Pe firul enigma2, la capătul firului importului: reîncărcarea listei de canale (dacă s-au scris canale) și a
	înregistrărilor programate (incarca_temporizatoarele, dacă s-a scris timers.xml), apoi rețeaua din copie, dacă e
	(Components/HdsImportRetea.aplica, cu întoarcerea la cea de dinainte când nu merge; durează până la un minut), apoi
	modulul de acces ales în copie, dacă e (alege_modul_de_acces, Components/HdsModuleAcces.Operatie), și abia apoi
	zăvorul dat înapoi, rezultatul ținut minte pentru ecran și web și dupa(rezultat). Întoarce rezultatul (fără rețea
	și fără modul de ales: cel final)."""
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
	modul = rez.pop("_acces_alege", None)

	def gata_tot(r):
		elibereaza(r)
		if dupa is not None:
			dupa(r)

	def final(r):
		if modul:
			alege_modul_de_acces(modul, r, gata_tot, alege_modul)
		else:
			gata_tot(r)

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


def alege_modul_de_acces(modul, rez, gata, alege_modul=None):
	"""Pe firul enigma2: modulul ales în copie ({"fel", "sufix", "nume", "reporneste"}, HdsImportExtra.modul_de_ales)
	ales și pornit aici ca din ecranul modulelor (Components/HdsModuleAcces.Operatie: oprește modulul de acum, schimbă
	legătura, pornește modulul nou; „reporneste” când era deja cel ales, fiindcă fișierele lui s-au schimbat), apoi
	gata(rez), o singură dată. `alege_modul(modul, la_final)` numai pentru probe."""
	terminat = []
	mesaje = rez.setdefault("mesaje", [])

	def la_final(rezultat):
		if terminat:
			return
		terminat.append(True)
		if (rezultat or {}).get("ok"):
			mesaje.append(_("Modulul ales în imaginea veche, %s, e ales și aici și pornit.") % modul.get("nume", ""))
			rez.setdefault("acces", {})["ales"] = modul.get("nume", "")
		else:
			mesaje.append(_("Modulul %s nu a pornit acum; îl pornești din Meniu, Acces condiționat, Module de acces "
				"condiționat.") % modul.get("nume", ""))
		gata(rez)

	try:
		if alege_modul is None:
			from Components import HdsModuleAcces

			def alege_modul(m, la_final):
				o = HdsModuleAcces.Operatie("reporneste" if m.get("reporneste") else "alege", m["fel"], m["sufix"],
					la_final=la_final)
				o.porneste()   # o ține în viață HdsModuleAcces cât lucrează (_curenta, scriptul în curs)
		alege_modul(modul, la_final)
	except Exception as e:
		_jurnal("alegerea modulului: %s" % e.__class__.__name__)
		la_final({"ok": False})


# ---------------------------------------------------------------- starea comună (televizor și web)

_STARE = {"surse": None, "cand": 0, "cauta": False, "ocupat": False, "ultimul": None, "in_lucru": 0, "necitite": []}
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

	del _NECITITE[:]

	def _gata(surse, eroare):
		if eroare:
			_jurnal("căutarea surselor: %s" % eroare)
		_STARE.update(surse=surse or [], cand=time.time(), cauta=False, necitite=list(_NECITITE))
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
