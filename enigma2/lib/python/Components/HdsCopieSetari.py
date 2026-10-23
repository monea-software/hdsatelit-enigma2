# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCopieSetari.py: copia setarilor receptorului pe un stick sau un disc si punerea ei la loc, de mana sau singura
# la prima pornire dupa scrierea unei imagini noi. O singura logica pentru ecranul „Copia setărilor”
# (Screens/HdsCopieSetari.py), pentru pagina web /copie-setari (Plugins/Extensions/HdsWebControl/copie_setari_web.py) si
# pentru tools/enigma2.sh.in, care ruleaza fisierul ca program („python3 ... HdsCopieSetari.py pornire”) inainte de
# enigma2. La incarcare nu se importa nimic din enigma2 (probele de pe PC si enigma2.sh il folosesc direct).
#
# Copia: dosarul <mediu>/hdsatelit/copii-setari/<AAAALLZZ-hhmmss>-<model>, scris intai ca .<nume>.part (sarit de
# import si de lista copiilor) si redenumit la sfarsit, dupa fsync pe fiecare fisier:
#   setari.tar.gz             tot etc/enigma2 (canalele, buchetele, fisierele hds_*, hdsatelit/ cu cheile de traducere
#                             criptate, locurile din retea si parolele lor criptate (retea-locuri.json, retea-parole.bin,
#                             Components/HdsStocareRetea.py), hdsdab/ si hdst2mi/ = listele DAB+ si DVB-T2, timers.xml,
#                             hds-motor-pozitie.json,
#                             hdswebcontrol-browsere.json, hdswebcontrol-aplicatii.json = parola pentru aplicatii) si
#                             etc/tuxbox/*.xml, cu excluderile lui copie-de-mana.sh
#                             (settings* la orice adancime, semnul garzii, fisierele .nou, SEMNE_PORNIRE = semnele
#                             unei porniri sau probe in curs, numele de module de acces conditionat: _nume_de_modul),
#                             fara legaturi; plus
#                             etc/enigma2/settings-fara-token: settings fara jetonul interfetei web si fara
#                             config.crash.enabledebug (importul il recunoaste), cu SETARI_FIXE scrise (vezi mai jos);
#   retea.tar.gz              etc/network/interfaces, etc/resolv.conf, etc/wpa_supplicant.conf (cu parolele Wi-Fi),
#                             brute, cu drepturile lor (pe FAT drepturile nu se pastreaza, in arhiva da);
#   machine-id                /etc/machine-id (fisierul cheilor de traducere pus sub 0.1.9 e legat de el);
#   authorized_keys           /home/root/.ssh/authorized_keys;
#   sistem.json               setarile omului din afara /etc/enigma2 (stare_sistem): „Fără parolă în rețeaua locală” a
#                             SSH-ului, sursele de pachete adaugate de om, interfata implicita cand sunt doua
#                             configurate (/etc/default_gw); numai valori verificate, fara parole; scris cand e ceva;
#   acces-conditionat.tar.gz  modulele de acces conditionat instalate, gasite dupa conventia pachetelor (fisiere in
#                             /usr/<fel>s sau un script /etc/init.d/<fel>.<x>, felurile dupa forma: feluri_acces):
#                             pachetul .ipk daca e pe receptor, altfel fisierele lui dupa lista opkg
#                             (info/<pachet>.list = „opkg files”), informatiile opkg ale pachetului, /etc/tuxbox/config
#                             si legaturile de pornire; in fisier nu e scris niciun nume de modul sau de fel;
#   copie.txt                 formatul, data, felul (manuala / automata), modelul, amprenta receptorului (sha256 al
#                             adresei MAC a lui eth0, litere mici, fara sfarsit de rand, calculata aici ca in
#                             copie-de-mana.sh; adresa nu se scrie), versiunea imaginii si md5-ul fiecarui fisier.
# Valorile (jetonul, parolele, cheile, machine-id, setarile modulelor) nu se tiparesc si nu intra in jurnale.
#
# Punerea la loc (pune_la_loc), numai cu enigma2 oprit, aceleasi reguli ca trusa de dupa flash
# (scripturi/trusa-dupa-flash-021.sh, carligul enigma2_pre_start.sh):
#   - copia se verifica intreaga inainte de orice scriere: md5-urile din copie.txt, forma fiecarei arhive (numai
#     fisiere obisnuite si dosare sub caile permise, fara legaturi in afara celor de pornire ale modulelor, fara „..”,
#     limite de marime); orice abatere = nimic scris;
#   - canalele (tot etc/enigma2 din copie) pe orice receptor; setarile, reteaua, fisierele receptorului
#     (FISIERE_PROPRII: browserele asociate, parola pentru aplicatiile de telefon, pozitia si viteza motorului,
#     temporizatoarele, discul ales, treapta probata a procesorului si fisierele criptate cu identitatea receptorului:
#     cheile de traducere, conturile subtitrarilor),
#     machine-id, cheile SSH, sistem.json si modulele de acces conditionat NUMAI pe receptorul copiei (aceeasi amprenta
#     si acelasi model);
#   - setarile se unesc ca in trusa: pleaca de la copie, pastreaza din setarile de acum PASTREZ si jetonul web, scot
#     SCOT; instantaneul settings.inainte-de-copie si semnul garzii (.hds-setari-din-copie, secundele din /proc/uptime
#     si id-ul pornirii) le foloseste garda de caderi din enigma2.sh;
#   - semnele trecerilor DAB+ o singura data (SEMNE_O_DATA, aceleasi nume ca SEMN_* din Hds/DabT2/imagine.py) se scot
#     dupa dezarhivare, ca trecerile sa ajunga si la buchetele copiei; FISIERE_NEPUSE (semnele placilor 2D si video,
#     oprirea lor automata, proba procesorului, lacatul de proba al motorului) nu se pun niciodata;
#   - reteaua: <nume>.nou langa tinta, cel facut de imagine pastrat o data ca <nume>.din-imagine, wpa_supplicant.conf
#     0600, resolv.conf fara „nameserver 0.0.0.0”; nimic nu reporneste reteaua: adresa din copie vine la pornirea
#     receptorului, pe care interfata o face singura o data (rezultat.json, „repornire”) cand un fisier s-a schimbat;
#   - semnul „gata” in /home/root/hds-restaurare (acelasi ca al trusei, in afara /etc/enigma2: o resetare la valorile
#     din fabrica nu aduce nimic inapoi); rezultatul in rezultat.json (numai nume si numere), pentru mesajul de pe
#     televizor;
#   - jurnalul (hds-restaurare.log) spune la sfarsit ce s-a pus si ce nu, cu motivul; serviciul si rezervele traducerii
#     din copie (sau ca lipsesc: atunci ramane valoarea din fabrica a imaginii); care SETARI_FIXE erau in copie; daca
#     fisierele criptate cu identitatea receptorului (cheile de traducere, conturile subtitrarilor) se pot citi acum,
#     dupa machine-id pus la loc (numai numele serviciilor care au cheie, niciodata o valoare).
#
# SETARI_FIXE: enigma2 scrie in settings numai valorile diferite de cea din fabrica (ConfigElement.save). Cand o versiune
# noua schimba valoarea din fabrica, o alegere egala cu vechea valoare dispare fara urma: dupa flash (copia, trusa) si la
# o actualizare fara flash. Setarile din lista primesc save_forced si sunt scrise o data cu valoarea de acum
# (fixeaza_setari): la pornirea interfetei (porneste; cele ale traducerii le scrie Components/HdsTraducereSubtitrari.py
# in legaNucleul, dupa verificarea cheilor, fiindca mutaServiciulVechi se uita la randul lipsa) si inainte de
# config.pickle() la copie. Ce nu e in copie si de ce: inventarul din test_copie_setari_audit_023.py.
# pornire() (din enigma2.sh) lucreaza numai daca exista o cerere (din meniu sau web) sau daca lipseste semnul primei
# porniri (prima-pornire); la prima pornire cauta o copie numai daca settings lipseste (imagine proaspat scrisa) si
# „gata” nu exista: cea mai noua copie a acestui receptor, altfel cea mai noua de acelasi model (numai canalele).
# Fara niciuna, numai semnul pentru copia altei imagini (Components/HdsImportAltaImagine.py): dupa pornirea sesiunii
# (porneste) se cauta copia unei alte imagini si se intreaba daca se aduce.
#
# Variabilele HDS_RADACINA, HDS_ETH0, HDS_BOXTYPE, HDS_BOOT_ID, HDS_UPTIME, HDS_OPKG si HDS_COPIE_MEDII sunt numai
# pentru probe (HDS_COPIE_MEDII: „<dosar>|<stick sau disc>|<eticheta>;...”, fiindca in emulator si pe PC un dosar
# legat nu apare ca /dev/sd* in /proc/mounts); init nu pune niciuna.

import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import threading
import time

FORMAT = 1
DOSAR_PE_MEDIU = "hdsatelit/copii-setari"
TIPAR_NUME = re.compile(r"^(\d{8})-(\d{6})-([A-Za-z0-9_.-]{0,32})(-\d{1,3})?$")
DESCRIERE = "copie.txt"
ARH_SETARI = "setari.tar.gz"
ARH_RETEA = "retea.tar.gz"
ARH_ACCES = "acces-conditionat.tar.gz"
FIS_MASINA = "machine-id"
FIS_CHEI = "authorized_keys"
FIS_SISTEM = "sistem.json"
# o imagine mai veche sare randul md5 al unui fisier pe care nu-l stie (citeste_descriere): copia ramane buna acolo
FISIERE_COPIE = (ARH_SETARI, ARH_RETEA, ARH_ACCES, FIS_MASINA, FIS_CHEI, FIS_SISTEM)
SETTINGS_COPIE = "etc/enigma2/settings-fara-token"

DOSAR_RESTAURARE = "home/root/hds-restaurare"
SEMN_GATA = "gata"
SEMN_PRIMA = "prima-pornire"
CERERE = "cerere"
REZULTAT = "rezultat.json"

JETON = "config.plugins.hdswebcontrol.token"
# ca in trusa: din setarile de acum raman modul video ales dupa flash si versiunea vazuta in „Ce e nou”; nu trec din
# copie depanarea si comutatorul accelerarii 2D (accelerarea porneste dupa flash, oprirea automata ramane), nici setarea
# IPv6 (urmeaza semnul /etc/hds-ipv6-pornit al receptorului, Components/HdsIpv6.py; dupa flash IPv6 e oprit)
PASTREZ = ("config.av.hds_videomode", "config.hdsatelit.jurnal.ultimaVazuta")
SCOT = ("config.crash.enabledebug", "config.usage.hds_accel_2d", "config.usage.hds_ipv6")
CHEI_SCOASE_DIN_COPIE = (JETON, "config.crash.enabledebug")
# semnele trecerilor o singura data ale lui Hds/DabT2/imagine.py (SEMN_PORT, SEMN_PORT_FORMA, SEMN_MARCAJE), sub
# etc/enigma2; un test compara numele cu cele de acolo
SEMNE_O_DATA = ("hdsdab/port-8898", "hdsdab/port-8898-ts", "hdsdab/marcaje-mux", "hdst2mi/marcaje-mux")
# fisierele receptorului (caile sub etc/enigma2): numai pe receptorul copiei. Cele criptate cu identitatea receptorului
# (cheile de traducere, conturile subtitrarilor, parolele locurilor din retea) nu se pot citi pe altul: puse acolo i-ar
# lua locul fisierului lui (la o cerere din meniu) si ar cere cheile din nou; discul ales (UUID), treapta probata a procesorului si viteza masurata a
# motorului sunt ale aparatului. Parola pentru aplicatiile de telefon si aplicatiile vazute (hdswebcontrol-aplicatii.json,
# Plugins/Extensions/HdsWebControl/aplicatii_web.py, 0600) raman dupa o versiune noua pe acelasi receptor (aplicatiile
# din afara casei nu trebuie scrise din nou), dar nu trec pe altul.
FISIERE_PROPRII = ("hdswebcontrol-browsere.json", "hdswebcontrol-aplicatii.json", "hds-motor-pozitie.json",
	"timers.xml", "hdsatelit/traducere-chei.bin", "hdsatelit/subtitrari-conturi.bin", "hds-disc-hdd",
	"hds-procesor.probat", "hds-motor-viteza.json", "hdsatelit/retea-parole.bin")
# semnele unei porniri sau probe in curs: placa 2D (hds-accel.*), placa video (hds-gpu.pornire, lib/gdi/hdsgpu.cpp: ramas
# = „pornirea de data trecuta nu s-a terminat”), proba procesorului (hds-procesor.proba cu boot_id: alt boot_id = o
# pornire cazuta cu procesorul accelerat, Components/HdsProcesor.py); nu intra in copie
SEMNE_PORNIRE = ("hds-accel.pornire", "hds-accel.lucru", "hds-gpu.pornire", "hds-procesor.proba")
# pe niciun receptor (nici din copiile mai vechi): SEMNE_PORNIRE, oprirea automata a placilor (hds-fara-accel,
# hds-fara-gpu), vechiul comutator al accelerarii, lacatul de proba al motorului (hds-fara-motor,
# Components/HdsMotorTuner.py) si evenimentul paznicului (hds-paznic.eveniment, aratat o data la pornirea sesiunii,
# Hds/DabT2/bataie.py): spun ce s-a intamplat pe imaginea veche, nu ce a ales omul
FISIERE_NEPUSE = SEMNE_PORNIRE + ("hds-fara-accel", "hds-cu-accel", "hds-fara-gpu", "hds-fara-motor",
	"hds-paznic.eveniment")
FISIERE_RETEA = ("etc/network/interfaces", "etc/resolv.conf", "etc/wpa_supplicant.conf")
# setarile omului din afara /etc/enigma2 (sistem.json): regula „Fără parolă în rețeaua locală” (Components/HdsAccesSsh.py),
# sursele de pachete adaugate (Components/HdsPachete.py), interfata implicita (Screens/NetworkSetup.py, fara rand nou)
FIS_REGULA_SSH = "etc/security/hds-ssh-retea-locala.conf"
FIS_SURSE = "etc/opkg/hds-surse-utilizator.conf"
FIS_POARTA = "etc/default_gw"
TIPAR_INTERFATA = re.compile(r"^[A-Za-z0-9._-]{1,15}\n?\Z")
MAX_SURSE = 50

MAX_DESCRIERE = 64 * 1024
MAX_ARHIVA = 64 * 1024 * 1024
MAX_MEMBRI = 5000
MAX_DECOMPRIMAT = 256 * 1024 * 1024
MAX_RETEA = 1024 * 1024
MAX_CHEI = 64 * 1024
MAX_SISTEM = 64 * 1024
REZERVA_SPATIU = 2 * 1024 * 1024
PASTRATE_IMPLICIT = 5
PASTRATE_MAXIM = 10
ASTEPTARE_MEDII_S = 20     # cat asteapta prima pornire stickurile inca nemontate
UPTIME_MEDII_S = 30        # sub atatea secunde de la pornire se mai asteapta un stick care nu a aparut inca
ZI_S = 24 * 3600
TOLERANTA_ZI_S = 1800

# modulele de acces conditionat (conventia OE-A, ca in Components/HdsModuleAcces.py), fara niciun nume scris aici:
# felurile se afla dupa forma pe receptor (feluri_acces: in etc/init.d un nume N cu locul gol N.None sau cu legatura N
# spre un script N.<x>, aceeasi regula ca HdsInterfeteCam.feluri_din_nume, scrisa si aici fiindca modulul ruleaza si
# singur la pornire); pentru fiecare fel: programele in usr/<fel>s/, scripturile etc/init.d/<fel>.<x>, legatura aleasa
# etc/init.d/<fel> si legaturile rc spre ea; setarile in etc/tuxbox/config
DOSAR_CONFIG_ACCES = "etc/tuxbox/config/"
SUFIX_GOL_ACCES = "None"
_FEL = r"[A-Za-z][A-Za-z0-9_-]{0,31}"
_NUME_FEL_ACCES = re.compile(r"^%s$" % _FEL)
TIPAR_FEL_PRINCIPAL = re.compile(r"cam$", re.I)
TIPAR_SCRIPT_ACCES = re.compile(r"^etc/init\.d/(%s)\.([A-Za-z0-9][A-Za-z0-9._+-]{0,63})$" % _FEL)
TIPAR_LEGATURA_ALEASA = re.compile(r"^etc/init\.d/(%s)$" % _FEL)
TIPAR_LEGATURA_RC = re.compile(r"^etc/rc[0-6S]\.d/[SK][0-9]{2}(%s)$" % _FEL)
TIPAR_CUVANT_ACCES = re.compile(r"cams?d?[0-9]*$")   # vezi _nume_de_modul
TIPAR_PACHET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,99}$")
SUFIXE_INFO_OPKG = ("control", "list", "conffiles", "postinst", "prerm", "postrm", "preinst", "md5sums")
DOSARE_PACHET_PERMISE = ("usr/bin/", "usr/lib/", "usr/share/", "usr/sbin/")
DOSARE_PACHET_OPRITE = ("usr/lib/enigma2/",)
DOSARE_IPK = ("var/cache/opkg", "home/root", "tmp")
META_ACCES = "hds-copie/"
PACHETE_ACCES = META_ACCES + "pachete.json"

ANTET_LAMEDB = "eDVB services /4/"


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsCopieSetari] %s" % text)


def ngettext(unu, multe, n):
	try:
		from Components.HdsImportSurse import ngettext as ng
	except ImportError:
		return unu if n == 1 else multe
	return ng(unu, multe, n)


# ---------------------------------------------------------------- caile

def radacina(rad=None):
	if rad:
		return rad
	return os.environ.get("HDS_RADACINA") or "/"


def _c(rad, rel):
	return os.path.join(rad, *rel.split("/"))


def dosar_restaurare(rad=None):
	return _c(radacina(rad), DOSAR_RESTAURARE)


def cale_jurnal(rad=None):
	return _c(radacina(rad), "home/root/logs/hds-restaurare.log")


def _citeste_mic(cale, maxim=4096):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim)
	except (OSError, IOError):
		return None


def _scrie_atomic(cale, date, mod=None):
	"""Scrie `date` (octeti) langa tinta (.nou), fsync, apoi os.replace; drepturile `mod` puse inainte de mutare."""
	nou = cale + ".nou"
	fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
	try:
		with os.fdopen(fd, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		if mod is not None:
			os.chmod(nou, mod)
		os.replace(nou, cale)
	except Exception:
		try:
			os.remove(nou)
		except OSError:
			pass
		raise


def _sincronizeaza():
	try:
		os.sync()
	except AttributeError:
		pass


def _md5(cale):
	h = hashlib.md5()
	with open(cale, "rb") as f:
		for bucata in iter(lambda: f.read(65536), b""):
			h.update(bucata)
	return h.hexdigest()


# ---------------------------------------------------------------- receptorul

def amprenta_aici(rad=None):
	"""sha256 al adresei MAC a lui eth0 (litere mici, fara sfarsit de rand), ca in copie-de-mana.sh; „” fara eth0."""
	rad = radacina(rad)
	cale = os.environ.get("HDS_ETH0") or _c(rad, "sys/class/net/eth0/address")
	date = _citeste_mic(cale, 256)
	if not date:
		return ""
	adresa = date.split(b"\n", 1)[0].replace(b"\r", b"").strip().lower()
	if not adresa:
		return ""
	return hashlib.sha256(adresa).hexdigest()


def model_aici(rad=None):
	rad = radacina(rad)
	cale = os.environ.get("HDS_BOXTYPE") or _c(rad, "proc/stb/info/boxtype")
	date = _citeste_mic(cale, 128)
	if not date:
		return ""
	rand = date.split(b"\n", 1)[0].decode("ascii", "ignore")
	return re.sub(r"[^A-Za-z0-9_.-]", "", rand)[:32]


def versiune_imagine(rad=None):
	"""(randul version= din /etc/image-version, versiunea scrisa "0.2.1"), ca in HdsCommon.image_version_text: 16
	cifre, sau 19 cand o parte a versiunii are doua cifre ("0.3.10", fiecare parte pe doua cifre)."""
	date = _citeste_mic(_c(radacina(rad), "etc/image-version"), 4096) or b""
	for rand in date.decode("ascii", "ignore").splitlines():
		if rand.startswith("version="):
			v = re.sub(r"[^0-9]", "", rand[8:])
			if len(v) == 19:
				return v, ("%d.%d.%d" % (int(v[1:3]), int(v[3:5]), int(v[5:7]))) if v[0] == "0" else v[7:15]
			v = v[:16]
			if len(v) == 16:
				return v, ("%s.%s.%s" % (v[1], v[2], v[3])) if v[0] == "0" else v[4:12]
			return v, v
	return "", ""


def _uptime():
	u = os.environ.get("HDS_UPTIME")
	if u:
		try:
			return int(float(u))
		except ValueError:
			pass
	try:
		with open("/proc/uptime", "r", encoding="ascii") as f:
			return int(float(f.read().split()[0]))
	except (OSError, ValueError, IndexError):
		return int(time.time())


def _boot_id(rad):
	cale = os.environ.get("HDS_BOOT_ID") or _c(rad, "proc/sys/kernel/random/boot_id")
	date = _citeste_mic(cale, 128) or b""
	return re.sub(r"[^0-9a-f-]", "", date.split(b"\n", 1)[0].decode("ascii", "ignore"))[:40]


def _data_text(t):
	try:
		return time.strftime("%d.%m.%Y %H:%M", time.localtime(int(t)))
	except (ValueError, OverflowError, OSError):
		return ""


# ---------------------------------------------------------------- mediile

def _dosar_recuperare(rad):
	"""Dosarul in care Maintenance Mode cauta imaginea pe stick (Components/HdsRecuperare.py, calculul lui
	showiframe), de exemplu „amiko/viper4kv20/”; „” cand nu se stie."""
	try:
		from Components import HdsRecuperare
	except ImportError:
		return ""
	try:
		return HdsRecuperare.dosarPeStick(HdsRecuperare.calculeaza(rad).get("cale", ""))
	except Exception:
		return ""


def este_stick_de_actualizare(punct, dosar_recuperare=""):
	"""Stickul de pe care se scrie imaginea: are dosarul lui Maintenance Mode sau e2/update/ (ecranul de
	actualizare din meniu)."""
	if dosar_recuperare and os.path.isdir(os.path.join(punct, *dosar_recuperare.strip("/").split("/"))):
		return True
	return os.path.isdir(os.path.join(punct, "e2", "update"))


def _medii_de_proba():
	rez = []
	for parte in (os.environ.get("HDS_COPIE_MEDII") or "").split(";"):
		if not parte.strip():
			continue
		bucati = parte.split("|")
		punct = bucati[0]
		fel = bucati[1] if len(bucati) > 1 and bucati[1] in ("stick", "disc") else "stick"
		eticheta = bucati[2] if len(bucati) > 2 else os.path.basename(punct.rstrip("/\\"))
		rez.append({"punct": punct, "dispozitiv": "", "fel": fel, "eticheta": eticheta})
	return rez


def nume_mediu(mediu):
	fel = mediu.get("fel")
	nume = mediu.get("eticheta") or mediu.get("punct") or ""
	if fel == "disc":
		text = _("Disc „%s”") % nume
	elif (mediu.get("dispozitiv") or "").startswith("/dev/mmcblk"):
		text = _("Card de memorie „%s”") % nume
	else:
		text = _("Stick USB „%s”") % nume
	if mediu.get("actualizare"):
		text += " " + _("(stickul de actualizare)")
	return text


def medii(rad=None, cale_mounts=None):
	"""Unde se poate face o copie: stickurile si discurile montate (HdsImportSurse.medii: dupa /proc/mounts), fara
	memoria interna. Stickul de actualizare intai, apoi celelalte stickuri, apoi discurile. Fiecare:
	{"id" (punctul de montare), "punct", "fel", "eticheta", "actualizare", "nume"}."""
	rad = radacina(rad)
	lista = _medii_de_proba()
	if not lista and not os.environ.get("HDS_COPIE_MEDII"):
		try:
			from Components import HdsImportSurse
			lista = HdsImportSurse.medii(cale_mounts or HdsImportSurse.CALE_MOUNTS)
		except Exception as eroare:
			_jurnal("mediile: %s" % eroare.__class__.__name__)
			lista = []
	dosar = _dosar_recuperare(rad)
	rez = []
	for m in lista:
		if m.get("fel") not in ("stick", "disc") or not os.path.isdir(m.get("punct", "")):
			continue
		m = dict(m)
		m["actualizare"] = m["fel"] == "stick" and este_stick_de_actualizare(m["punct"], dosar)
		m["id"] = m["punct"]
		m["nume"] = nume_mediu(m)
		rez.append(m)
	rez.sort(key=lambda m: (0 if m["actualizare"] else 1, 0 if m["fel"] == "stick" else 1))
	return rez


def mediu_dupa_id(id_mediu, lista):
	for m in lista:
		if m["id"] == id_mediu:
			return m
	return None


def mediu_implicit(lista):
	"""Stickul de actualizare daca e bagat (de pe el se face flash-ul), altfel primul stick, altfel discul."""
	return lista[0] if lista else None


# ---------------------------------------------------------------- facerea copiei

def _nume_de_modul(nume):
	"""Un cuvant din `nume` (impartit la orice semn care nu e litera sau cifra) are forma numelor modulelor de acces
	conditionat: se termina in cam, cams sau camd, cu cifre la coada sau nu. Fara lista de nume; aceeasi regula
	ca in Components/HdsImportSurse.py (_nume_de_modul), scrisa si aici ca modulul sa mearga si singur (pornire)."""
	return any(TIPAR_CUVANT_ACCES.search(c) for c in re.split(r"[^a-z0-9]+", nume.lower()))


def _exclus_setari(rel):
	"""Membrii lui etc/enigma2 care nu intra in copie, pe fiecare nume din cale (ca --exclude din copie-de-mana.sh, dar
	numele de module se recunosc dupa regula generala _nume_de_modul, mai larga decat cele doua nume ale scriptului)."""
	for nume in rel.split("/"):
		if nume.startswith("settings") or nume == ".hds-setari-din-copie":
			return True
		if nume.endswith(".nou") or re.search(r"\.nou\.[0-9]+$", nume):
			return True
		if nume in SEMNE_PORNIRE:
			return True
		if _nume_de_modul(nume):
			return True
	return False


def _info_tar(nume, st, fel=tarfile.REGTYPE):
	ti = tarfile.TarInfo(nume)
	ti.type = fel
	ti.mode = stat.S_IMODE(st.st_mode) if st is not None else 0o644
	ti.mtime = int(st.st_mtime) if st is not None else int(time.time())
	ti.uid = ti.gid = 0
	ti.uname = ti.gname = "root"
	return ti


def _adauga_fisier(tf, cale, nume, st=None):
	st = st or os.lstat(cale)
	ti = _info_tar(nume, st)
	with open(cale, "rb") as f:
		date = f.read()
	ti.size = len(date)
	tf.addfile(ti, io.BytesIO(date))
	return len(date)


def _adauga_date(tf, nume, date, mod=0o644):
	ti = _info_tar(nume, None)
	ti.mode = mod
	ti.size = len(date)
	tf.addfile(ti, io.BytesIO(date))


def _adauga_dosar(tf, nume, st=None):
	ti = _info_tar(nume, st, tarfile.DIRTYPE)
	if st is None:
		ti.mode = 0o755
	tf.addfile(ti)


def _deschide_tar_scriere(cale):
	f = open(cale, "wb")
	tf = tarfile.open(fileobj=f, mode="w:gz", format=tarfile.GNU_FORMAT, compresslevel=6)
	return f, tf


def _inchide_tar_scriere(f, tf):
	tf.close()
	f.flush()
	os.fsync(f.fileno())
	f.close()


def _fisiere_setari(rad):
	"""[(cale, nume in arhiva, este_dosar)]: tot etc/enigma2 (fara excluderi si legaturi) si etc/tuxbox/*.xml."""
	rez = []
	e2 = _c(rad, "etc/enigma2")
	if os.path.isdir(e2) and not os.path.islink(e2):
		rez.append((e2, "etc/enigma2", True))
		for dosar, dosare, fisiere in os.walk(e2):
			rel_dosar = os.path.relpath(dosar, e2).replace("\\", "/")
			rel_dosar = "" if rel_dosar == "." else rel_dosar + "/"
			pastrate = []
			for d in sorted(dosare):
				cale = os.path.join(dosar, d)
				if os.path.islink(cale) or _exclus_setari(rel_dosar + d):
					continue
				pastrate.append(d)
				rez.append((cale, "etc/enigma2/" + rel_dosar + d, True))
			dosare[:] = pastrate
			for n in sorted(fisiere):
				cale = os.path.join(dosar, n)
				if _exclus_setari(rel_dosar + n):
					continue
				try:
					st = os.lstat(cale)
				except OSError:
					continue
				if stat.S_ISREG(st.st_mode):
					rez.append((cale, "etc/enigma2/" + rel_dosar + n, False))
	tux = _c(rad, "etc/tuxbox")
	if os.path.isdir(tux) and not os.path.islink(tux):
		xml = []
		for n in sorted(os.listdir(tux)):
			cale = os.path.join(tux, n)
			if n.endswith(".xml") and os.path.isfile(cale) and not os.path.islink(cale):
				xml.append((cale, "etc/tuxbox/" + n, False))
		if xml:
			rez.append((tux, "etc/tuxbox", True))
			rez.extend(xml)
	return rez


def text_settings_fara_token(text):
	"""settings fara jetonul interfetei web si fara config.crash.enabledebug, fara CR."""
	randuri = []
	for rand in (text or "").splitlines():
		rand = rand.rstrip("\r")
		if rand.split("=", 1)[0].strip() in CHEI_SCOASE_DIN_COPIE:
			continue
		randuri.append(rand)
	return "\n".join(randuri) + ("\n" if randuri else "")


def _text_settings_de_pe_disc(rad):
	date = _citeste_mic(_c(rad, "etc/enigma2/settings"), 4 * 1024 * 1024)
	return None if date is None else date.decode("utf-8", "surrogateescape")


def curata_resolv(text):
	"""resolv.conf fara „nameserver 0.0.0.0” (scris de udhcpc) si fara „nameserver” gol; randurile goale: niciunul la
	inceput si la sfarsit, cel mult unul intre doua randuri (ca curata_resolv din copie-de-mana.sh). None daca nu
	ramane niciun nameserver."""
	iesire = []
	gol = False
	for rand in (text or "").splitlines():
		r = rand.rstrip("\r")
		if re.match(r"^\s*nameserver\s+0\.0\.0\.0\s*$", r) or re.match(r"^\s*nameserver\s*$", r):
			continue
		if not r.strip():
			gol = True
			continue
		if gol and iesire:
			iesire.append("")
		gol = False
		iesire.append(r)
	if not any(re.match(r"^\s*nameserver\s", r) for r in iesire):
		return None
	return "\n".join(iesire) + "\n"


def _lista_opkg(cale):
	"""Caile din info/<pachet>.list (ce arata „opkg files”), relative la radacina, fara „..”."""
	rez = []
	date = _citeste_mic(cale, 1024 * 1024) or b""
	for rand in date.decode("utf-8", "replace").splitlines()[:MAX_MEMBRI]:
		cale_fisier = rand.split("\t", 1)[0].strip()
		if not cale_fisier.startswith("/"):
			continue
		norm = _normalizat(cale_fisier.lstrip("/"))
		if norm:
			rez.append(norm)
	return rez


def _strofe_status(rad):
	"""{pachet: strofa din /var/lib/opkg/status}."""
	rez = {}
	date = _citeste_mic(_c(rad, "var/lib/opkg/status"), 8 * 1024 * 1024) or b""
	for strofa in re.split(r"\n\s*\n", date.decode("utf-8", "replace")):
		m = re.search(r"^Package:\s*(\S+)", strofa, re.M)
		if m:
			rez[m.group(1)] = strofa.strip("\n") + "\n"
	return rez


def _camp(strofa, nume):
	m = re.search(r"^%s:\s*(.*)$" % re.escape(nume), strofa or "", re.M)
	return m.group(1).strip() if m else ""


def feluri_din_nume_acces(nume, legatura):
	"""Felurile modulelor de acces din numele aflate in etc/init.d (aceeasi regula ca HdsInterfeteCam.feluri_din_nume):
	un nume N cu locul gol N.None sau cu legatura N spre un script N.<x>; felul terminat in "cam" primul.
	`legatura(n)`: tinta legaturii n sau None."""
	toate = set(nume)
	candidati = set()
	for n in toate:
		c = n.split(".", 1)[0]       # prefixul unui script N.<x> sau legatura N insasi
		if _NUME_FEL_ACCES.match(c):
			candidati.add(c)
	rez = []
	for c in candidati:
		if c + "." + SUFIX_GOL_ACCES in toate:
			rez.append(c)
			continue
		t = legatura(c)
		if t:
			b = os.path.basename(t)
			if b.startswith(c + ".") and len(b) > len(c) + 1:
				rez.append(c)
	rez.sort(key=lambda f: (not TIPAR_FEL_PRINCIPAL.search(f), f.lower(), f))
	return rez


def feluri_acces(rad=None):
	"""Felurile modulelor de acces de pe receptorul din `rad` (etc/init.d); [] cand dosarul nu se citeste."""
	initd = _c(radacina(rad), "etc/init.d")
	try:
		nume = os.listdir(initd)
	except OSError:
		return []
	return feluri_din_nume_acces(nume, lambda n: _citeste_legatura(os.path.join(initd, n)))


def _dosare_programe(feluri):
	"""usr/<fel>s/ pentru fiecare fel: dosarele in care pachetele isi pun programele (conventia OE-A)"""
	return tuple("usr/%ss/" % f for f in feluri)


def _e_fisier_de_acces(rel, feluri):
	"""un program din dosarul programelor unui fel sau un script <fel>.<x> (altul decat locul gol)"""
	if feluri and rel.startswith(_dosare_programe(feluri)):
		return True
	m = TIPAR_SCRIPT_ACCES.match(rel)
	return bool(m and m.group(1) in feluri and m.group(2) != SUFIX_GOL_ACCES)


def module_acces(rad=None):
	"""Ce intra in copia modulelor de acces conditionat: {"pachete": [{"nume", "versiune", "arhitectura", "fisiere",
	"info", "strofa", "ipk"}], "libere": [rel], "config": [rel], "legaturi": [rel], "feluri": [fel]}. Numai citire."""
	rad = radacina(rad)
	feluri = feluri_acces(rad)
	rez = {"pachete": [], "libere": [], "config": [], "legaturi": [], "feluri": feluri}
	info = _c(rad, "var/lib/opkg/info")
	strofe = _strofe_status(rad)
	ale_pachetelor = set()
	try:
		liste = sorted(n for n in os.listdir(info) if n.endswith(".list"))
	except OSError:
		liste = []
	for n in liste:
		pachet = n[:-5]
		if not TIPAR_PACHET.match(pachet):
			continue
		fisiere = _lista_opkg(os.path.join(info, n))
		if not any(_e_fisier_de_acces(f, feluri) for f in fisiere):
			continue
		strofa = strofe.get(pachet, "")
		p = {
			"nume": pachet,
			"versiune": _camp(strofa, "Version"),
			"arhitectura": _camp(strofa, "Architecture"),
			"fisiere": [f for f in fisiere if os.path.lexists(_c(rad, f))],
			"info": [],
			"strofa": strofa,
			"ipk": None,
		}
		for sufix in SUFIXE_INFO_OPKG:
			rel = "var/lib/opkg/info/%s.%s" % (pachet, sufix)
			if os.path.isfile(_c(rad, rel)) and not os.path.islink(_c(rad, rel)):
				p["info"].append(rel)
		p["ipk"] = _gaseste_ipk(rad, p)
		ale_pachetelor.update(fisiere)
		rez["pachete"].append(p)
	# programele si scripturile puse fara opkg
	for dosar_programe in _dosare_programe(feluri):
		prog = _c(rad, dosar_programe.rstrip("/"))
		if os.path.isdir(prog) and not os.path.islink(prog):
			for n in sorted(os.listdir(prog)):
				rel = dosar_programe + n
				if rel not in ale_pachetelor and os.path.isfile(_c(rad, rel)) and not os.path.islink(_c(rad, rel)):
					rez["libere"].append(rel)
	initd = _c(rad, "etc/init.d")
	try:
		scripturi = sorted(os.listdir(initd))
	except OSError:
		scripturi = []
	for n in scripturi:
		rel = "etc/init.d/" + n
		cale = _c(rad, rel)
		if _e_fisier_de_acces(rel, feluri) and rel not in ale_pachetelor and os.path.isfile(cale) \
				and not os.path.islink(cale):
			rez["libere"].append(rel)
		elif TIPAR_LEGATURA_ALEASA.match(rel) and _legatura_buna(rel, _citeste_legatura(cale), feluri):
			rez["legaturi"].append(rel)
	for nivel in "0123456S":
		d = _c(rad, "etc/rc%s.d" % nivel)
		try:
			nume = sorted(os.listdir(d))
		except OSError:
			continue
		for n in nume:
			rel = "etc/rc%s.d/%s" % (nivel, n)
			if TIPAR_LEGATURA_RC.match(rel) and _legatura_buna(rel, _citeste_legatura(_c(rad, rel)), feluri):
				rez["legaturi"].append(rel)
	cfg = _c(rad, DOSAR_CONFIG_ACCES.rstrip("/"))
	if os.path.isdir(cfg) and not os.path.islink(cfg):
		for dosar, dosare, fisiere in os.walk(cfg):
			dosare[:] = sorted(d for d in dosare if not os.path.islink(os.path.join(dosar, d)))
			rel_dosar = os.path.relpath(dosar, _c(rad, "")).replace("\\", "/")
			for n in sorted(fisiere):
				cale = os.path.join(dosar, n)
				if os.path.isfile(cale) and not os.path.islink(cale):
					rez["config"].append(rel_dosar + "/" + n)
	return rez


def _citeste_legatura(cale):
	try:
		return os.readlink(cale) if os.path.islink(cale) else None
	except OSError:
		return None


def _legatura_buna(rel, tinta, feluri):
	"""Legaturile de pornire ale modulelor, numai pentru felurile date: etc/init.d/<fel> spre un script <fel>.<x> din
	acelasi dosar, legaturile rc ale felului spre ../init.d/<fel>."""
	if not tinta:
		return False
	m = TIPAR_LEGATURA_ALEASA.match(rel)
	if m:
		return m.group(1) in feluri and bool(re.match(r"^%s\.[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$" % re.escape(m.group(1)),
			tinta))
	m = TIPAR_LEGATURA_RC.match(rel)
	if m:
		return m.group(1) in feluri and tinta in ("../init.d/%s" % m.group(1), "/etc/init.d/%s" % m.group(1))
	return False


def _gaseste_ipk(rad, p):
	"""Pachetul .ipk al versiunii instalate, daca a ramas pe receptor (memoria opkg, /home/root, /tmp)."""
	if not p["versiune"]:
		return None
	versiune = p["versiune"].split(":", 1)[-1]
	nume = "%s_%s_%s.ipk" % (p["nume"], versiune, p["arhitectura"]) if p["arhitectura"] else None
	for d in DOSARE_IPK:
		dosar = _c(rad, d)
		try:
			fisiere = os.listdir(dosar)
		except OSError:
			continue
		for n in fisiere:
			if (n == nume or (n.startswith("%s_%s_" % (p["nume"], versiune)) and n.endswith(".ipk"))):
				cale = os.path.join(dosar, n)
				if os.path.isfile(cale) and not os.path.islink(cale) and os.path.getsize(cale) <= MAX_ARHIVA:
					return cale
	return None


def _scrie_acces(rad, cale, module):
	"""acces-conditionat.tar.gz: (numarul fisierelor, numarul pachetelor) sau (0, 0) daca nu e nimic de pus."""
	if not (module["pachete"] or module["libere"] or module["config"]):
		return 0, 0
	feluri = module["feluri"] if "feluri" in module else feluri_acces(rad)
	f, tf = _deschide_tar_scriere(cale)
	n = 0
	vazute = set()
	try:
		meta = []
		for p in module["pachete"]:
			intrare = {"nume": p["nume"], "versiune": p["versiune"], "arhitectura": p["arhitectura"],
				"strofa": p["strofa"], "ipk": None}
			if p["ipk"]:
				intrare["ipk"] = META_ACCES + "ipk/" + os.path.basename(p["ipk"])
				_adauga_fisier(tf, p["ipk"], intrare["ipk"])
				n += 1
			meta.append(intrare)
		_adauga_date(tf, PACHETE_ACCES, json.dumps(meta, ensure_ascii=True, indent=1).encode("ascii"))
		toate = []
		for p in module["pachete"]:
			toate.extend(p["fisiere"])
			toate.extend(p["info"])
		toate.extend(module["libere"])
		toate.extend(module["config"])
		toate.extend(module["legaturi"])
		for rel in toate:
			if rel in vazute:
				continue
			vazute.add(rel)
			c = _c(rad, rel)
			try:
				st = os.lstat(c)
			except OSError:
				continue
			if stat.S_ISREG(st.st_mode):
				_adauga_fisier(tf, c, rel, st)
				n += 1
			elif stat.S_ISLNK(st.st_mode) and _legatura_buna(rel, _citeste_legatura(c), feluri):
				ti = _info_tar(rel, st, tarfile.SYMTYPE)
				ti.linkname = _citeste_legatura(c)
				tf.addfile(ti)
				n += 1
	finally:
		_inchide_tar_scriere(f, tf)
	return n, len(module["pachete"])


def _spatiu_liber(dosar):
	try:
		st = os.statvfs(dosar)
		return st.f_bavail * st.f_frsize
	except (AttributeError, OSError):
		return None


def _nume_copie(dosar_copii, acum, model):
	baza = time.strftime("%Y%m%d-%H%M%S", time.localtime(acum)) + "-" + (model or "receptor")
	nume = baza
	nr = 1
	while os.path.exists(os.path.join(dosar_copii, nume)) or os.path.exists(os.path.join(dosar_copii, "." + nume + ".part")):
		nr += 1
		nume = "%s-%d" % (baza, nr)
	return nume


def fa_copia(punct, text_setari=None, fel="manuala", rad=None, acum=None):
	"""Copia setarilor pe mediul montat in `punct`. `text_setari`: settings de acum (config.pickle() pe firul enigma2);
	fara el, fisierul de pe disc. Intoarce {"ok", "mesaje", "cale", "nume", "marime", "are"}. Ruleaza pe un fir
	separat (stickul poate fi lent); pe receptor nu scrie nimic."""
	rad = radacina(rad)
	acum = int(time.time() if acum is None else acum)
	mesaje = []
	rez = {"ok": False, "mesaje": mesaje, "cale": None, "nume": None, "marime": 0, "are": []}
	if not os.path.isdir(punct):
		mesaje.append(_("Mediul ales nu mai este montat."))
		return rez
	dosar_copii = os.path.join(punct, *DOSAR_PE_MEDIU.split("/"))
	fisiere = _fisiere_setari(rad)
	module = module_acces(rad)
	necesar = REZERVA_SPATIU
	marimi = [cale for cale, _n, este_dosar in fisiere if not este_dosar]
	for p in module["pachete"]:
		marimi.extend(_c(rad, rel) for rel in p["fisiere"])
		if p["ipk"]:
			marimi.append(p["ipk"])
	for cale in marimi:
		try:
			necesar += os.path.getsize(cale)
		except OSError:
			pass
	liber = _spatiu_liber(punct)
	if liber is not None and liber < necesar:
		mesaje.append(_("Pe mediul ales nu e destul loc (trebuie cam %d MB).") % (necesar // (1024 * 1024) + 1))
		return rez
	model = model_aici(rad)
	amprenta = amprenta_aici(rad)
	imagine, versiune = versiune_imagine(rad)
	try:
		os.makedirs(dosar_copii, exist_ok=True)
	except OSError as eroare:
		mesaje.append(_("Dosarul copiilor nu s-a putut face pe mediu (%s).") % (eroare.strerror or eroare))
		return rez
	nume = _nume_copie(dosar_copii, acum, model)
	part = os.path.join(dosar_copii, "." + nume + ".part")
	are = []
	md5 = []
	try:
		os.makedirs(part)
		# canalele, listele, fisierele hds si settings fara jeton
		if text_setari is None:
			text_setari = _text_settings_de_pe_disc(rad)
		cale = os.path.join(part, ARH_SETARI)
		f, tf = _deschide_tar_scriere(cale)
		nr = 0
		try:
			for c, n, este_dosar in fisiere:
				if este_dosar:
					_adauga_dosar(tf, n, os.lstat(c))
				else:
					_adauga_fisier(tf, c, n)
					nr += 1
			if text_setari is not None:
				if not any(n == "etc/enigma2" for _c2, n, _d in fisiere):
					_adauga_dosar(tf, "etc/enigma2")
				_adauga_date(tf, SETTINGS_COPIE, text_settings_fara_token(text_setari).encode("utf-8", "surrogateescape"),
					0o600)
		finally:
			_inchide_tar_scriere(f, tf)
		are.append("setari")
		lamedb = _c(rad, "etc/enigma2/lamedb")
		if os.path.isfile(lamedb):
			from_lamedb = _citeste_mic(lamedb, 64) or b""
			if not from_lamedb.startswith(ANTET_LAMEDB.encode("ascii")):
				mesaje.append(_("Lista de canale de acum nu are forma obișnuită; a intrat în copie așa cum e."))
		# reteaua si Wi-Fi: numai fisierele obisnuite, negoale
		retea = [rel for rel in FISIERE_RETEA if os.path.isfile(_c(rad, rel)) and not os.path.islink(_c(rad, rel))
			and os.path.getsize(_c(rad, rel)) > 0]
		if retea:
			f, tf = _deschide_tar_scriere(os.path.join(part, ARH_RETEA))
			try:
				for rel in retea:
					_adauga_fisier(tf, _c(rad, rel), rel)
			finally:
				_inchide_tar_scriere(f, tf)
			are.append("retea")
		# machine-id: 32 de semne hex mici si un rand nou
		mid = _citeste_mic(_c(rad, "etc/machine-id"), 64)
		if mid is not None and re.match(rb"^[0-9a-f]{32}\n$", mid):
			_scrie_atomic(os.path.join(part, FIS_MASINA), mid)
			are.append("masina")
		chei = _citeste_mic(_c(rad, "home/root/.ssh/authorized_keys"), MAX_CHEI + 1)
		if chei and len(chei) <= MAX_CHEI and chei_bune(chei):
			_scrie_atomic(os.path.join(part, FIS_CHEI), chei)
			are.append("chei")
		nr_acces, nr_pachete = _scrie_acces(rad, os.path.join(part, ARH_ACCES), module)
		if nr_acces:
			are.append("acces")
		elif os.path.exists(os.path.join(part, ARH_ACCES)):
			os.remove(os.path.join(part, ARH_ACCES))
		# setarile omului din afara /etc/enigma2
		sistem = stare_sistem(rad)
		if sistem:
			_scrie_atomic(os.path.join(part, FIS_SISTEM), json.dumps(sistem, ensure_ascii=True, sort_keys=True,
				indent=1).encode("ascii"))
			are.append("sistem")
		for n in FISIERE_COPIE:
			if os.path.isfile(os.path.join(part, n)):
				md5.append((n, _md5(os.path.join(part, n))))
		randuri = [
			"# Copia setarilor receptorului HD Satelit. Are parolele Wi-Fi si setarile modulelor de acces conditionat:",
			"# tine stickul la tine.",
			"format=%d" % FORMAT,
			"data=%d" % acum,
			"data_text=%s" % _data_text(acum),
			"fel=%s" % ("automata" if fel == "automata" else "manuala"),
			"model=%s" % model,
			"amprenta=%s" % amprenta,
			"imagine=%s" % imagine,
			"versiune=%s" % versiune,
			"are=%s" % ",".join(are),
			"pachete_acces=%d" % nr_pachete,
		]
		randuri += ["md5 %s %s" % (n, h) for n, h in md5]
		_scrie_atomic(os.path.join(part, DESCRIERE), ("\n".join(randuri) + "\n").encode("ascii", "replace"))
		_sincronizeaza()
		final = os.path.join(dosar_copii, nume)
		os.rename(part, final)
		_sincronizeaza()
	except Exception as eroare:
		shutil.rmtree(part, ignore_errors=True)
		_jurnal("copia: %s" % eroare.__class__.__name__)
		mesaje.append(_("Copia nu s-a putut scrie pe mediu (%s). Pe receptor nu s-a schimbat nimic.")
			% (getattr(eroare, "strerror", None) or eroare.__class__.__name__))
		return rez
	marime = 0
	for n, _h in md5:
		try:
			marime += os.path.getsize(os.path.join(final, n))
		except OSError:
			pass
	rez.update(ok=True, cale=final, nume=nume, marime=marime, are=are)
	mesaje.insert(0, _("Copia e gata: %s.") % _data_text(acum))
	return rez


def chei_bune(date):
	"""authorized_keys: text, fara cheie privata, fiecare rand negol o cheie publica (cu sau fara optiuni)."""
	try:
		text = date.decode("ascii")
	except UnicodeDecodeError:
		return False
	if "PRIVATE KEY" in text:
		return False
	randuri = [r for r in text.splitlines() if r.strip() and not r.lstrip().startswith("#")]
	if not randuri:
		return False
	tipar = re.compile(r"(^|\s)(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh\.com|"
		r"sk-ecdsa-sha2-nistp256@openssh\.com) [A-Za-z0-9+/]+=*")
	return all(tipar.search(r) for r in randuri)


# ---------------------------------------------------------------- setarile din afara /etc/enigma2 (sistem.json)

def _modul_imagine(nume):
	"""Un modul al imaginii (de ex. „Components.HdsPachete”) sau None. Modulele folosite aici nu importa enigma2 la
	incarcare: merg si din enigma2.sh, cand motorul ruleaza ca program."""
	try:
		return __import__(nume, fromlist=[nume.rsplit(".", 1)[-1]])
	except Exception as eroare:
		_jurnal("%s nu se poate incarca: %s" % (nume, eroare.__class__.__name__))
		return None


def stare_sistem(rad=None):
	"""Setarile omului din afara /etc/enigma2, pentru sistem.json; {} cand nu e nimic de pus. Numai citire.
	  ssh_fara_parola   „Fără parolă în rețeaua locală”, cand fisierul regulii exista: pornita = o regula „-”
						(faraParolaInRetea din Components/HdsAccesSsh.py);
	  surse_pachete     [[nume, adresa]]: sursele adaugate de om, numai randurile care trec verificarea
						(citeste_surse_utilizator din Components/HdsPachete.py: fara spatii, fara parole in adresa);
	  poarta_implicita  interfata din /etc/default_gw, octet cu octet (Screens/NetworkSetup.py o scrie fara rand nou)."""
	rad = radacina(rad)
	rez = {}
	regula = _citeste_mic(_c(rad, FIS_REGULA_SSH), 64 * 1024)
	if regula is not None and not os.path.islink(_c(rad, FIS_REGULA_SSH)):
		rez["ssh_fara_parola"] = any(r.startswith("-") for r in regula.decode("utf-8", "replace").splitlines())
	if os.path.isfile(_c(rad, FIS_SURSE)):
		pachete = _modul_imagine("Components.HdsPachete")
		if pachete is not None:
			surse = [[n, a] for n, a in pachete.citeste_surse_utilizator(rad)][:MAX_SURSE]
			if surse:
				rez["surse_pachete"] = surse
	poarta = _citeste_mic(_c(rad, FIS_POARTA), 64)
	if poarta is not None:
		text = poarta.decode("ascii", "replace")
		if TIPAR_INTERFATA.match(text):
			rez["poarta_implicita"] = text
	return rez


def _sistem_din_copie(dosar):
	"""(stare, None) din sistem.json, fiecare valoare verificata din nou ca la citirea de pe receptor; (None, motiv)
	cand fisierul nu e bun. Cheile necunoscute (de la o versiune mai noua) se lasa deoparte."""
	date = _citeste_mic(os.path.join(dosar, FIS_SISTEM), MAX_SISTEM + 1)
	if not date or len(date) > MAX_SISTEM:
		return None, "lipseste sau e prea mare"
	try:
		d = json.loads(date.decode("ascii"))
	except (ValueError, UnicodeDecodeError):
		return None, "nu e JSON"
	if not isinstance(d, dict):
		return None, "nu e un obiect JSON"
	rez = {}
	if "ssh_fara_parola" in d:
		if not isinstance(d["ssh_fara_parola"], bool):
			return None, "ssh_fara_parola nu e da / nu"
		rez["ssh_fara_parola"] = d["ssh_fara_parola"]
	if "poarta_implicita" in d:
		if not isinstance(d["poarta_implicita"], str) or not TIPAR_INTERFATA.match(d["poarta_implicita"]):
			return None, "interfata implicita nu are forma unui nume de interfata"
		rez["poarta_implicita"] = d["poarta_implicita"]
	if "surse_pachete" in d:
		surse = d["surse_pachete"]
		if not isinstance(surse, list) or len(surse) > MAX_SURSE:
			return None, "sursele de pachete nu sunt o lista buna"
		pachete = _modul_imagine("Components.HdsPachete")
		if pachete is not None:
			vazute = []
			for s in surse:
				if (not isinstance(s, list) or len(s) != 2 or not all(isinstance(x, str) for x in s)
						or pachete.verifica_sursa(s[0], s[1], vazute) is not None):
					return None, "o sursa de pachete nu trece verificarea"
				vazute.append(s[0])
			rez["surse_pachete"] = [list(s) for s in surse]
	return rez, None


# ---------------------------------------------------------------- copiile gasite

def citeste_descriere(dosar):
	"""Campurile din copie.txt ({"format", "data", ..., "md5": {fisier: hex}}), sau None daca nu e o copie buna."""
	date = _citeste_mic(os.path.join(dosar, DESCRIERE), MAX_DESCRIERE + 1)
	if not date or len(date) > MAX_DESCRIERE:
		return None
	d = {"md5": {}}
	for rand in date.decode("ascii", "replace").splitlines():
		if rand.startswith("#"):
			continue
		if rand.startswith("md5 "):
			parti = rand.split()
			if len(parti) == 3 and parti[1] in FISIERE_COPIE and re.match(r"^[0-9a-f]{32}$", parti[2]):
				d["md5"][parti[1]] = parti[2]
			continue
		k, egal, v = rand.partition("=")
		if egal:
			d[k.strip()] = v.strip()
	try:
		if int(d.get("format", "0")) != FORMAT:
			return None
		d["data"] = int(d.get("data", "0"))
	except ValueError:
		return None
	if ARH_SETARI not in d["md5"]:
		return None
	if not re.match(r"^([0-9a-f]{64})?$", d.get("amprenta", "")):
		return None
	d["model"] = re.sub(r"[^A-Za-z0-9_.-]", "", d.get("model", ""))[:32]
	d["versiune"] = re.sub(r"[^0-9A-Za-z.]", "", d.get("versiune", ""))[:16]
	d["fel"] = "automata" if d.get("fel") == "automata" else "manuala"
	d["are"] = [a for a in d.get("are", "").split(",") if a]
	return d


def _e_acest_receptor(d, amprenta, model):
	return bool(amprenta) and d.get("amprenta") == amprenta and d.get("model", "") == model


def copii(lista_medii=None, rad=None):
	"""Copiile de pe mediile montate, cele mai noi intai: [{"id" (calea dosarului), "nume", "mediu", "mediu_nume",
	"data", "data_text", "versiune", "model", "acest", "fel", "are", "marime"}]. Numai citire."""
	rad = radacina(rad)
	lista_medii = medii(rad) if lista_medii is None else lista_medii
	amprenta = amprenta_aici(rad)
	model = model_aici(rad)
	rez = []
	for m in lista_medii:
		dosar_copii = os.path.join(m["punct"], *DOSAR_PE_MEDIU.split("/"))
		try:
			nume = os.listdir(dosar_copii)
		except OSError:
			continue
		for n in nume:
			cale = os.path.join(dosar_copii, n)
			if not TIPAR_NUME.match(n) or os.path.islink(cale) or not os.path.isdir(cale):
				continue
			d = citeste_descriere(cale)
			if d is None:
				continue
			marime = 0
			for f in d["md5"]:
				try:
					marime += os.path.getsize(os.path.join(cale, f))
				except OSError:
					pass
			rez.append({
				"id": cale, "nume": n, "mediu": m["id"], "mediu_nume": m.get("nume") or nume_mediu(m),
				"data": d["data"], "data_text": d.get("data_text") or _data_text(d["data"]),
				"versiune": d["versiune"], "model": d["model"], "acest": _e_acest_receptor(d, amprenta, model),
				"fel": d["fel"], "are": d["are"], "marime": marime,
			})
	rez.sort(key=lambda c: (-c["data"], c["id"]))
	return rez


def copie_dupa_id(id_copie, lista):
	for c in lista:
		if c["id"] == id_copie:
			return c
	return None


def sterge_copia(id_copie, lista=None, rad=None):
	"""Sterge numai un dosar de copie care e in lista copiilor gasite acum. (ok, mesaj)."""
	lista = copii(rad=rad) if lista is None else lista
	c = copie_dupa_id(id_copie, lista)
	if c is None:
		return False, _("Copia nu mai este pe mediu.")
	try:
		shutil.rmtree(c["id"])
		_sincronizeaza()
	except OSError as eroare:
		return False, _("Copia nu s-a putut șterge (%s).") % (eroare.strerror or eroare.__class__.__name__)
	return True, _("Copia din %s a fost ștearsă.") % c["data_text"]


def curata_automate(punct, pastrate, rad=None):
	"""Pastreaza pe mediul `punct` numai cele mai noi `pastrate` copii automate ale acestui receptor; cele facute de
	mana raman. Intoarce cate s-au sters."""
	rad = radacina(rad)
	m = {"punct": punct, "id": punct, "fel": "stick", "eticheta": ""}
	automate = [c for c in copii([m], rad) if c["fel"] == "automata" and c["acest"]]
	sterse = 0
	for c in automate[max(1, int(pastrate)):]:
		try:
			shutil.rmtree(c["id"])
			sterse += 1
		except OSError:
			pass
	if sterse:
		_sincronizeaza()
	return sterse


def descriere_copie(c):
	"""Textul de sub lista pentru copia aleasa: de unde, de cand, ce are, al cui receptor."""
	parti = []
	are = c.get("are") or []
	if "setari" in are:
		parti.append(_("canalele, buchetele, listele DAB+ și DVB-T2, setările"))
	if "retea" in are:
		parti.append(_("rețeaua și Wi-Fi"))
	if "acces" in are:
		parti.append(_("modulele de acces condiționat"))
	if "chei" in are:
		parti.append(_("cheile SSH"))
	receptor = _("acest receptor") if c.get("acest") else _("alt receptor (se pun la loc numai canalele)")
	fel = _("automată") if c.get("fel") == "automata" else _("făcută de mână")
	return _("%s, copia din %s (%s, imaginea %s), %s.\nAre: %s.") % (c.get("mediu_nume", ""), c.get("data_text", ""),
		fel, c.get("versiune") or "?", receptor, "; ".join(parti) or _("nimic"))


def text_avertisment():
	return _("Copia are parolele Wi-Fi și setările modulelor de acces condiționat: ține stickul la tine.")


def text_intrebare_punere(c):
	"""Intrebarea dinaintea punerii la loc (televizor si web; raspunsul ales e „Nu”). Caseta de mesaj are loc pentru
	trei randuri, deci textul e scurt."""
	if c.get("acest"):
		return _("Pui la loc copia din %s? Interfața repornește și o pune la loc. Dacă rețeaua din copie e alta, "
			"receptorul mai repornește o dată, singur.") % c.get("data_text", "")
	return _("Copia din %s e de pe alt receptor: se pun la loc numai canalele și listele DAB+ și DVB-T2. Interfața "
		"repornește acum. Continui?") % c.get("data_text", "")


def text_intrebare_stergere(c):
	return _("Ștergi copia din %s de pe %s? Nu se mai poate aduce înapoi.") % (c.get("data_text", ""),
		c.get("mediu_nume", ""))


def cerere_in_asteptare(rad=None):
	"""O copie aleasa asteapta repornirea interfetei (cererea scrisa, enigma2.sh inca nu a pus-o la loc)."""
	return os.path.isfile(os.path.join(dosar_restaurare(rad), CERERE))


# ---------------------------------------------------------------- verificarea copiei

def _normalizat(nume):
	if not nume or nume.startswith("/") or "\\" in nume or any(ord(ch) < 32 for ch in nume):
		return None
	parti = [p for p in nume.split("/") if p not in ("", ".")]
	if not parti or ".." in parti:
		return None
	return "/".join(parti)


def verifica_copia(dosar, d=None):
	"""None daca fisierele copiei sunt intregi (md5 din copie.txt), altfel motivul."""
	d = d or citeste_descriere(dosar)
	if d is None:
		return _("copia nu are o descriere bună (copie.txt)")
	for n, h in d["md5"].items():
		cale = os.path.join(dosar, n)
		if not os.path.isfile(cale) or os.path.islink(cale):
			return _("lipsește %s din copie") % n
		maxim = {ARH_RETEA: MAX_RETEA, FIS_MASINA: 64, FIS_CHEI: MAX_CHEI, FIS_SISTEM: MAX_SISTEM}.get(n, MAX_ARHIVA)
		if os.path.getsize(cale) > maxim:
			return _("%s e prea mare") % n
		if _md5(cale) != h:
			return _("%s nu mai e cum a fost scris (md5)") % n
	return None


def _parcurge(cale, permis, functie=None, max_decomprimat=MAX_DECOMPRIMAT):
	"""O trecere prin arhiva: fiecare membru verificat (cale curata, fel permis: fisier, dosar sau legatura, loc
	permis de `permis(nume, ti)`, limitele); `functie(nume, ti, date)` primeste membrii in ordine, cu continutul
	fisierelor (None la dosare si legaturi). Intoarce None daca a mers, altfel motivul; un singur membru rau = toata
	arhiva refuzata. Fara extractall si fara cai luate din arhiva."""
	total = 0
	try:
		with tarfile.open(cale, "r:gz") as t:
			for i, m in enumerate(t):
				if i >= MAX_MEMBRI:
					return _("arhiva are prea multe fișiere")
				nume = _normalizat(m.name)
				if nume is None:
					return _("arhiva are o cale nepermisă")
				if not (m.isreg() or m.isdir() or m.issym()):
					return _("arhiva are un fișier de un fel nepermis")
				if not permis(nume, m):
					return _("arhiva are un fișier în afara locurilor permise")
				date = None
				if m.isreg():
					total += max(0, m.size)
					if total > max_decomprimat:
						return _("arhiva e prea mare după decomprimare")
					if functie is not None:
						f = t.extractfile(m)
						date = f.read() if f is not None else b""
						if len(date) != m.size:
							return _("arhiva e tăiată")
				if functie is not None:
					functie(nume, m, date)
	except Exception as eroare:  # tarfile.TarError, EOFError, OSError, zlib.error
		return _("arhiva nu se poate citi (%s)") % eroare.__class__.__name__
	return None


def _citeste_arhiva(cale, permis, max_decomprimat=MAX_DECOMPRIMAT):
	"""Toti membrii unei arhive mici (reteaua, modulele), cu continutul: ([(nume, ti, date)], None) sau (None, motiv)."""
	membri = []
	motiv = _parcurge(cale, permis, lambda n, m, date: membri.append((n, m, date)), max_decomprimat)
	return (None, motiv) if motiv else (membri, None)


def _permis_setari(nume, m):
	if m.issym():
		return False
	if nume in ("etc", "etc/enigma2", "etc/tuxbox"):
		return m.isdir()
	if nume.startswith("etc/enigma2/"):
		return True
	return bool(re.match(r"^etc/tuxbox/[^/]+\.xml$", nume)) and m.isreg()


def _permis_retea(nume, m):
	return (m.isreg() and nume in FISIERE_RETEA) or (m.isdir() and nume in ("etc", "etc/network"))


def _pachete_din_meta(membri):
	for nume, _m, date in membri:
		if nume == PACHETE_ACCES and date is not None:
			try:
				lista = json.loads(date.decode("ascii"))
			except (ValueError, UnicodeDecodeError):
				return None
			if not isinstance(lista, list):
				return None
			bune = []
			for p in lista:
				if not isinstance(p, dict) or not TIPAR_PACHET.match(str(p.get("nume", ""))):
					return None
				bune.append(p)
			return bune
	return []


def _permis_acces(feluri):
	"""Locurile permise in copia modulelor (pachetele se verifica apoi dupa lista lor, in _verifica_acces), pentru
	felurile receptorului pe care se pune copia (feluri_acces): o copie nu poate aduce scripturi sau legaturi de
	pornire ale altor programe. Intoarce functia (nume, membru) -> bool pentru _citeste_arhiva."""
	feluri = tuple(feluri)
	programe = _dosare_programe(feluri)

	def permis(nume, m):
		if m.isdir():
			return True
		if m.issym():
			return _legatura_buna(nume, m.linkname, feluri)
		s = TIPAR_SCRIPT_ACCES.match(nume)
		return ((bool(programe) and nume.startswith(programe)) or nume.startswith(DOSAR_CONFIG_ACCES)
			or (s is not None and s.group(1) in feluri) or nume.startswith(META_ACCES)
			or nume.startswith("var/lib/opkg/info/")
			or (nume.startswith(DOSARE_PACHET_PERMISE) and not nume.startswith(DOSARE_PACHET_OPRITE)))
	return permis


def _fisierele_pachetelor(membri, nume_pachete):
	"""{cale: pachet} din listele opkg (info/<pachet>.list) aflate in copie, numai pentru pachetele din lista."""
	rez = {}
	for nume, _m, date in membri:
		mm = re.match(r"^var/lib/opkg/info/(.+)\.list$", nume)
		if mm and mm.group(1) in nume_pachete and date is not None:
			for rand in date.decode("utf-8", "replace").splitlines():
				norm = _normalizat(rand.split("\t", 1)[0].strip().lstrip("/"))
				if norm:
					rez[norm] = mm.group(1)
	return rez


def _verifica_acces(membri):
	"""(pachetele, None) daca fiecare membru e la locul lui: informatiile opkg numai ale pachetelor din lista, programele
	din usr/ numai daca sunt in lista opkg a acelui pachet; altfel (None, motiv)."""
	pachete = _pachete_din_meta(membri)
	if pachete is None:
		return None, _("lista pachetelor din copie nu e bună")
	nume_pachete = set(p["nume"] for p in pachete)
	ale_pachetelor = _fisierele_pachetelor(membri, nume_pachete)
	for nume, m, _date in membri:
		if m.isdir():
			continue
		mm = re.match(r"^var/lib/opkg/info/(.+)\.([a-z0-9]+)$", nume)
		if nume.startswith("var/lib/opkg/info/"):
			if not mm or mm.group(1) not in nume_pachete or mm.group(2) not in SUFIXE_INFO_OPKG:
				return None, _("copia modulelor are informații opkg străine")
		elif nume.startswith(META_ACCES):
			if nume != PACHETE_ACCES and not re.match(r"^hds-copie/ipk/[A-Za-z0-9][A-Za-z0-9.+_~-]*\.ipk$", nume):
				return None, _("copia modulelor are un fișier necunoscut")
		elif nume.startswith(DOSARE_PACHET_PERMISE) and nume not in ale_pachetelor:
			return None, _("copia modulelor are un program care nu e al niciunui pachet")
	for p in pachete:
		if p.get("ipk") and not any(n == p["ipk"] for n, _m, _d in membri):
			return None, _("lista pachetelor din copie nu e bună")
	return pachete, None


# ---------------------------------------------------------------- punerea la loc

def _perechi(text):
	for rand in (text or "").splitlines():
		rand = rand.rstrip("\r")
		i = rand.find("=")
		if i < 1:
			continue
		yield rand[:i], rand[i + 1:]


def unire_setari(acum_text, copie_text):
	"""Setarile unite ca in trusa (awk-ul din enigma2_pre_start.sh): cheile din copie, in ordinea lor, cu valorile
	copiei, afara de PASTREZ (valoarea de acum, daca exista) si de SCOT si jeton (sarite); apoi cheile de acum care nu
	erau in copie (jetonul web de acum ramane), fara SCOT. Randurile fara „=” sau cu cheie goala se sar; CR scos."""
	acum = {}
	ordine = []
	for k, v in _perechi(acum_text):
		if k not in acum:
			ordine.append(k)
		acum[k] = v
	iesire = []
	vazute = set()
	for k, v in _perechi(copie_text):
		if k in SCOT or k in vazute or k == JETON:
			continue
		if k in PASTREZ and k in acum:
			v = acum[k]
		iesire.append("%s=%s" % (k, v))
		vazute.add(k)
	for k in ordine:
		if k not in vazute and k not in SCOT:
			iesire.append("%s=%s" % (k, acum[k]))
			vazute.add(k)
	return "".join(r + "\n" for r in iesire)


class _Pregatire(object):
	"""Fisierele scrise langa tinte (<tinta>.hds-nou), verificate dupa scriere, inaintea oricarei mutari; muta() le
	pune peste tinte (redenumire in acelasi dosar), curata() le sterge pe toate."""

	def __init__(self):
		self.de_mutat = []

	def scrie(self, tinta, date, mod):
		d = os.path.dirname(tinta)
		if not os.path.isdir(d):
			os.makedirs(d)
		nou = tinta + ".hds-nou"
		self.de_mutat.append((nou, tinta))
		fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
		with os.fdopen(fd, "wb") as f:
			f.write(date)
			f.flush()
			os.fsync(f.fileno())
		os.chmod(nou, mod)
		if _citeste_mic(nou, len(date) + 1) != date:
			raise IOError("scriere nepotrivita")

	def muta(self):
		n = 0
		for nou, tinta in self.de_mutat:
			os.replace(nou, tinta)
			n += 1
		self.de_mutat = []
		return n

	def curata(self):
		for nou, _tinta in self.de_mutat:
			try:
				os.remove(nou)
			except OSError:
				pass
		self.de_mutat = []


def _mod_fisier(m, implicit=0o644):
	return (m.mode & 0o755) if m is not None and m.mode else implicit


def _forma_retea(nume, date):
	if not date:
		return False
	text = date.decode("utf-8", "replace")
	if nume.endswith("interfaces"):
		return re.search(r"^iface ", text, re.M) is not None
	if nume.endswith("resolv.conf"):
		return re.search(r"^\s*nameserver\s", text, re.M) is not None
	return re.search(r"^(ctrl_interface=|\s*network=)", text, re.M) is not None


def _rezultat_gol(motiv):
	return {"ok": False, "acest": False, "pus": [], "note": [], "repornire": "nu", "aratat": False, "motiv": motiv,
		"cand": int(time.time()), "copie": {}}


def pune_la_loc(dosar, rad=None, motiv="cerere", porneste_modulele=None):
	"""Pune la loc copia din `dosar`, cu enigma2 oprit (enigma2.sh). Ordinea ca in carligul trusei: totul pregatit si
	verificat langa tinte, apoi canalele, semnul garzii si setarile, apoi reteaua, machine-id si cheile; modulele de
	acces conditionat la sfarsit. Intoarce {"ok", "acest", "pus", "note", "repornire" (ceruta / nu), "copie", ...};
	jurnalul (pe iesirea standard, in hds-restaurare.log) are numai nume de fisiere si numere."""
	rad = radacina(rad)
	if porneste_modulele is None:
		porneste_modulele = rad == "/"
	rez = _rezultat_gol(motiv)
	note = rez["note"]
	pus = rez["pus"]
	d = citeste_descriere(dosar)
	if d is None:
		_jurnal("copia nu are copie.txt bun, nu scriu nimic")
		note.append(_("Copia nu are o descriere bună; nu s-a pus nimic la loc."))
		return rez
	rez["copie"] = {"nume": os.path.basename(dosar.rstrip("/\\")), "data_text": d.get("data_text") or _data_text(d["data"]),
		"versiune": d["versiune"]}
	motiv_rau = verifica_copia(dosar, d)
	if motiv_rau:
		_jurnal("copia nu e intreaga, nu scriu nimic")
		note.append(_("Copia nu e întreagă (%s); nu s-a pus nimic la loc.") % motiv_rau)
		return rez
	acest = _e_acest_receptor(d, amprenta_aici(rad), model_aici(rad))
	rez["acest"] = acest
	if not acest:
		_jurnal("copia e de pe alt receptor (amprenta sau modelul difera): pun numai canalele, fara setari, fara retea "
			"si fara fisierele receptorului")
	arh_setari = os.path.join(dosar, ARH_SETARI)
	eroare = _parcurge(arh_setari, _permis_setari)
	if eroare:
		_jurnal("arhiva canalelor refuzata, nu scriu nimic")
		note.append(_("Arhiva canalelor din copie nu e bună (%s); nu s-a pus nimic la loc.") % eroare)
		return rez
	retea = None
	if acest and ARH_RETEA in d["md5"]:
		retea, eroare = _citeste_arhiva(os.path.join(dosar, ARH_RETEA), _permis_retea, MAX_RETEA * 4)
		if retea is None:
			_jurnal("arhiva retelei refuzata, nu scriu nimic")
			note.append(_("Arhiva rețelei din copie nu e bună (%s); nu s-a pus nimic la loc.") % eroare)
			return rez
	acces = None
	pachete = []
	if acest and ARH_ACCES in d["md5"]:
		acces, eroare = _citeste_arhiva(os.path.join(dosar, ARH_ACCES), _permis_acces(feluri_acces(rad)))
		if acces is not None:
			pachete, eroare = _verifica_acces(acces)
			if pachete is None:
				acces = None
		if acces is None:
			_jurnal("copia modulelor de acces conditionat refuzata; restul se pune")
			note.append(_("Copia modulelor de acces condiționat nu e bună (%s); nu s-a pus la loc.") % eroare)
	sistem = None
	sistem_refuzat = False
	if acest and FIS_SISTEM in d["md5"]:
		sistem, eroare = _sistem_din_copie(dosar)
		if sistem is None:
			sistem_refuzat = True
			_jurnal("sistem.json refuzat (%s); restul se pune" % eroare)
	E = _c(rad, "etc/enigma2")
	S = os.path.join(E, "settings")
	canale = _Pregatire()     # etc/enigma2 si instantaneul setarilor
	rest = _Pregatire()       # reteaua, machine-id, cheile: mutate dupa setari
	stare_canale = {"n": 0, "settings": None}
	retea_puse = []
	masina = False
	chei_noi = 0
	nou_settings = None
	sistem_puse = []
	# ce nu s-a pus, pentru rezumatul din jurnal: etc/tuxbox (ca trusa, raman cele din imagine), semnele, fisierele
	# receptorului pe alt receptor
	nepus = {"tuxbox": 0, "semne": 0, "proprii": 0}

	def pune_membru(nume, m, date):
		if m.isdir():
			return
		if nume.startswith("etc/tuxbox/"):
			nepus["tuxbox"] += 1
			return
		if not nume.startswith("etc/enigma2/"):
			return
		rel = nume[len("etc/enigma2/"):]
		if nume == SETTINGS_COPIE:
			stare_canale["settings"] = date.decode("utf-8", "surrogateescape")
			return
		if _exclus_setari(rel) or rel.split("/")[-1] in FISIERE_NEPUSE:
			nepus["semne"] += 1
			return
		if not acest and rel in FISIERE_PROPRII:
			nepus["proprii"] += 1
			return
		if rel == "lamedb" and not date.startswith(ANTET_LAMEDB.encode("ascii")):
			note.append(_("Lista de canale din copie nu are forma obișnuită; a rămas cea de acum."))
			return
		tinta = os.path.join(E, *rel.split("/"))
		if os.path.islink(tinta) or os.path.isdir(tinta):
			return
		canale.scrie(tinta, date, _mod_fisier(m))
		stare_canale["n"] += 1

	try:
		# 1. fisierele din etc/enigma2, langa tinte (a doua trecere prin arhiva, membru cu membru)
		eroare = _parcurge(arh_setari, _permis_setari, pune_membru)
		if eroare:
			raise IOError(eroare)
		# 2. setarile unite (numai pe acest receptor), cu instantaneul celor de acum pentru garda de caderi
		settings_copie = stare_canale["settings"]
		if acest and settings_copie is not None:
			acum_text = _text_settings_de_pe_disc(rad)
			unit = unire_setari(acum_text, settings_copie)
			asteptate = len(set(k for k, _v in _perechi(settings_copie) if k not in SCOT and k != JETON))
			nn = unit.count("\n")
			if nn < asteptate:
				raise IOError("unire prea scurta")
			nou_settings = unit.encode("utf-8", "surrogateescape")
			_jurnal("chei: in copie %d, dupa unire %d" % (asteptate, nn))
			_jurnal_setari(settings_copie, acum_text)
			if acum_text is not None and not os.path.exists(os.path.join(E, ".hds-setari-din-copie")):
				canale.scrie(os.path.join(E, "settings.inainte-de-copie"), _citeste_mic(S, 8 * 1024 * 1024), 0o600)
		# 3. reteaua: una la fel cu cea din imagine sau o legatura in imagine nu se atinge; cea din imagine pastrata o
		# data ca <nume>.din-imagine
		for nume, m, date in retea or []:
			if m.isdir():
				continue
			if nume == "etc/resolv.conf":
				curat = curata_resolv(date.decode("utf-8", "replace"))
				if curat is None:
					_jurnal("reteaua: resolv.conf fara nameserver real, ramane cel al imaginii")
					continue
				date = curat.encode("utf-8")
			if not _forma_retea(nume, date):
				raise IOError("forma retelei")
			tinta = _c(rad, nume)
			if os.path.islink(tinta):
				_jurnal("reteaua: %s e o legatura in imagine, nu il schimb" % nume)
				continue
			if os.path.isfile(tinta) and _citeste_mic(tinta, MAX_RETEA) == date:
				_jurnal("reteaua: %s e la fel ca in copie" % nume)
				continue
			if os.path.isfile(tinta) and not os.path.exists(tinta + ".din-imagine"):
				shutil.copy2(tinta, tinta + ".din-imagine")
				if _citeste_mic(tinta, MAX_RETEA) != _citeste_mic(tinta + ".din-imagine", MAX_RETEA):
					raise IOError("copia din imagine")
			rest.scrie(tinta, date, 0o600 if nume.endswith("wpa_supplicant.conf") else 0o644)
			retea_puse.append(nume)
		# 4. machine-id si cheile SSH (numai pe acest receptor)
		if acest and FIS_MASINA in d["md5"]:
			mid = _citeste_mic(os.path.join(dosar, FIS_MASINA), 64)
			tinta = _c(rad, "etc/machine-id")
			if mid and re.match(rb"^[0-9a-f]{32}\n$", mid) and _citeste_mic(tinta, 64) != mid:
				# drepturile celui facut de imagine (0644 pe receptor), 0444 daca lipseste
				try:
					mod = stat.S_IMODE(os.stat(tinta).st_mode)
				except OSError:
					mod = 0o444
				rest.scrie(tinta, mid, mod)
				masina = True
		if acest and FIS_CHEI in d["md5"]:
			chei = _citeste_mic(os.path.join(dosar, FIS_CHEI), MAX_CHEI + 1)
			if chei and len(chei) <= MAX_CHEI and chei_bune(chei):
				tinta = _c(rad, "home/root/.ssh/authorized_keys")
				vechi = [r for r in (_citeste_mic(tinta, MAX_CHEI) or b"").decode("ascii", "replace").splitlines() if r.strip()]
				noi = [r for r in chei.decode("ascii").splitlines() if r.strip() and not r.startswith("#") and r not in vechi]
				if noi:
					ssh = os.path.dirname(tinta)
					if not os.path.isdir(ssh):
						os.makedirs(ssh)
					os.chmod(ssh, 0o700)
					rest.scrie(tinta, "".join(r + "\n" for r in vechi + noi).encode("ascii"), 0o600)
					chei_noi = len(noi)
			else:
				note.append(_("Cheile SSH din copie nu au forma obișnuită; nu s-au pus la loc."))
		# 5. setarile omului din afara /etc/enigma2 (numai pe acest receptor; sursele de pachete dupa mutare, prin
		# scrierea lui HdsPachete)
		if sistem and "ssh_fara_parola" in sistem:
			ssh = _modul_imagine("Components.HdsAccesSsh")
			tinta = _c(rad, FIS_REGULA_SSH)
			if ssh is not None and not os.path.islink(tinta):
				date = ssh.textRegula(sistem["ssh_fara_parola"]).encode("utf-8")
				vechi = _citeste_mic(tinta, 64 * 1024)
				# fara fisier PAM cere parola: la fel ca regula oprita
				if vechi != date and not (vechi is None and not sistem["ssh_fara_parola"]):
					rest.scrie(tinta, date, 0o644)
					sistem_puse.append("ssh")
		if sistem and "poarta_implicita" in sistem:
			tinta = _c(rad, FIS_POARTA)
			date = sistem["poarta_implicita"].encode("ascii")
			if not os.path.islink(tinta) and _citeste_mic(tinta, 64) != date:
				rest.scrie(tinta, date, 0o644)
				sistem_puse.append("poarta")
	except Exception as eroare:
		canale.curata()
		rest.curata()
		_jurnal("pregatirea a cazut (%s), nu scriu nimic" % eroare.__class__.__name__)
		note.append(_("Copia nu s-a putut pregăti pe receptor (memoria plină sau copia stricată); nu s-a pus nimic "
			"la loc."))
		return rez
	try:
		# canalele (si instantaneul), apoi semnele DAB+ ale trecerilor o singura data
		canale.muta()
		_jurnal("lista de canale si fisierele din etc/enigma2 scoase din copie: %d" % stare_canale["n"])
		if stare_canale["n"]:
			pus.append("canale")
		for s in SEMNE_O_DATA:
			cale = os.path.join(E, *s.split("/"))
			if os.path.exists(cale):
				os.remove(cale)
				_jurnal("DAB+: semnul %s scos; trecerea lui se face din nou la pornirea care urmeaza, si peste buchetele "
					"copiei" % s)
		if nou_settings is not None:
			# semnul garzii inaintea setarilor: o cadere de curent intre ele nu lasa setari unite fara garda
			A = _uptime()
			B = _boot_id(rad)
			semn = os.path.join(E, ".hds-setari-din-copie")
			_scrie_atomic(semn, ("%d\n%s\n" % (A, B) if B else "%d\n" % A).encode("ascii"), 0o644)
			if (_citeste_mic(semn, 64) or b"").split(b"\n", 1)[0] != str(A).encode("ascii"):
				raise IOError("semnul garzii")
			_sincronizeaza()
			_scrie_atomic(S, nou_settings, 0o644)
			pus.append("setari")
			_jurnal("setarile puse")
		rest.muta()
		if retea_puse:
			pus.append("retea")
			rez["repornire"] = "ceruta"
			_jurnal("reteaua: %d fisiere puse la loc; adresa din copie vine la repornirea receptorului (nimic repornit "
				"acum)" % len(retea_puse))
		if masina:
			pus.append("masina")
			_jurnal("machine-id pus la loc")
		if chei_noi:
			pus.append("chei")
			_jurnal("cheile SSH: %d puse la loc" % chei_noi)
		if "ssh" in sistem_puse:
			_jurnal("SSH: regula 'Fara parola in reteaua locala' pusa la loc: %s" % ("PORNITA (din reteaua de acasa se intra "
				"ca root fara parola)" if sistem["ssh_fara_parola"] else "oprita"))
		if "poarta" in sistem_puse:
			_jurnal("reteaua: interfata implicita pusa la loc (/etc/default_gw)")
		if sistem and sistem.get("surse_pachete"):
			pachete = _modul_imagine("Components.HdsPachete")
			surse = [tuple(s) for s in sistem["surse_pachete"]]
			if pachete is not None and pachete.citeste_surse_utilizator(rad) != surse:
				motiv = pachete.scrie_surse_utilizator(surse, rad)
				if motiv is None:
					sistem_puse.append("surse")
					_jurnal("sursele de pachete adaugate de om: %d puse la loc" % len(surse))
				else:
					_jurnal("sursele de pachete nu s-au scris")
		if sistem_puse:
			pus.append("sistem")
	except Exception as eroare:
		canale.curata()
		rest.curata()
		_jurnal("mutarea s-a oprit (%s)" % eroare.__class__.__name__)
		note.append(_("Punerea la loc s-a oprit la jumătate; setările și rețeaua au rămas cele de acum."))
	# modulele de acces conditionat, la sfarsit (opkg poate dura)
	if acces:
		try:
			n, motive = _pune_acces(rad, acces, pachete, porneste_modulele)
			if n:
				pus.append("acces")
				_jurnal("modulele de acces conditionat: %d fisiere puse la loc" % n)
			note.extend(motive)
		except Exception as eroare:
			_jurnal("modulele de acces conditionat: %s" % eroare.__class__.__name__)
			note.append(_("Modulele de acces condiționat nu s-au putut pune la loc."))
	_sincronizeaza()
	rez["ok"] = bool(pus)
	_jurnal("randuri lamedb: %d; chei settings: %d" % (_numara_randuri(os.path.join(E, "lamedb")), _numara_chei(S)))
	try:
		if acest:
			_jurnal_criptate(rad)
		rez["nepus"] = _jurnal_rezumat(pus, nepus, acest, d, stare_canale["settings"], acces, sistem_refuzat)
	except Exception as eroare:
		_jurnal("rezumatul: %s" % eroare.__class__.__name__)
	return rez


def _curat_jurnal(valoare):
	"""O valoare de setare care nu e secreta (un cod de serviciu, o lista de coduri), fara semne ciudate, pentru jurnal."""
	return re.sub(r"[^A-Za-z0-9,_.-]", "", valoare or "")[:80]


def _jurnal_setari(copie_text, acum_text):
	"""In jurnal: serviciul si rezervele traducerii din setarile copiei (lipsa = ramane valoarea din fabrica a imaginii
	de acum), care SETARI_FIXE au rand in copie si ce PASTREZ ramane din setarile de acum. Numai coduri si nume."""
	valori = dict(_perechi(copie_text))
	serviciu = valori.get("config.hds_traducere.serviciu")
	if serviciu is None:
		T = _modul_imagine("Components.HdsTraducereSubtitrari")
		_jurnal("traducerea: serviciul nu e in copie, ramane cel din fabrica al imaginii (%s)"
			% _curat_jurnal(getattr(T, "SERVICIU_IMPLICIT", "?")))
	else:
		_jurnal("traducerea: serviciul din copie: %s" % _curat_jurnal(serviciu))
	if "config.hds_traducere.rezerve" in valori:
		_jurnal("traducerea: rezervele din copie: %s" % (_curat_jurnal(valori["config.hds_traducere.rezerve"]) or "niciuna"))
	lipsa = [c for c, _m in SETARI_FIXE if c not in valori]
	_jurnal("setarile scrise mereu: %d din %d in copie%s" % (len(SETARI_FIXE) - len(lipsa), len(SETARI_FIXE),
		(" (fara rand, raman cele din fabrica ale imaginii: %s)" % ", ".join(lipsa)) if lipsa else ""))
	acum = dict(_perechi(acum_text))
	pastrate = [k for k in PASTREZ if k in acum]
	if pastrate:
		_jurnal("din setarile de acum raman: %s" % ", ".join(pastrate))


def _jurnal_criptate(rad):
	"""In jurnal: daca fisierele criptate cu identitatea receptorului se pot citi acum, dupa machine-id pus la loc:
	cheile de traducere (versiunea plicului si serviciile care au cheie) si conturile subtitrarilor (cate campuri).
	Niciodata o valoare sau identitatea."""
	retea = _c(rad, "sys/class/net")
	cale = _c(rad, "etc/enigma2/hdsatelit/traducere-chei.bin")
	if not os.path.isfile(cale):
		_jurnal("cheile de traducere: nu sunt pe receptor")
	else:
		T = _modul_imagine("Components.HdsTraducereSubtitrari")
		if T is not None:
			chei = T.Chei(cale=cale, identitate=T.identitateAparat(retea, _c(rad, "sys/bus/mmc/devices")),
				identitate_veche=T.identitateVeche(retea, _c(rad, "etc/machine-id")))
			v = T.versiunePlic(_citeste_mic(cale, 64 * 1024) or b"")
			plic = ("plicul v%d" % v) if v else "fisierul nu e un plic al cheilor"
			servicii = sorted(chei.citeste())
			if servicii:
				_jurnal("cheile de traducere: se citesc pe acest receptor (%s); au cheie: %s" % (plic, ", ".join(servicii)))
			else:
				_jurnal("cheile de traducere: NU se citesc pe acest receptor (%s): la pornire se pun deoparte si trebuie "
					"puse din nou" % plic)
	cale = _c(rad, "etc/enigma2/hdsatelit/subtitrari-conturi.bin")
	if os.path.isfile(cale):
		K = _modul_imagine("Components.HdsSubtitrariInternet.conturi")
		if K is not None:
			campuri = K.Conturi(cale=cale, identitate=K.identitateAparat(retea, _c(rad, "etc/machine-id"))).citeste()
			_jurnal("conturile subtitrarilor: %s" % ("se citesc (%d campuri)" % len(campuri) if campuri
				else "NU se citesc pe acest receptor"))
	cale = _c(rad, "etc/enigma2/hdsatelit/retea-parole.bin")
	if os.path.isfile(cale):
		S = _modul_imagine("Components.HdsStocareRetea")
		T = _modul_imagine("Components.HdsTraducereSubtitrari")
		if S is not None and T is not None:
			ident = T.identitateAparat(retea, _c(rad, "sys/bus/mmc/devices"))
			n = len(S.Parole(cale=cale, identitate=(S.ETICHETA_PAROLE + ident) if ident else "").citeste())
			_jurnal("parolele locurilor din retea: %s" % ("se citesc (%d)" % n if n else "NU se citesc pe acest receptor: "
				"se scriu din nou la Locuri din retea"))


def _jurnal_rezumat(pus, nepus, acest, d, settings_copie, acces, sistem_refuzat):
	"""Rezumatul punerii la loc in jurnal: ce s-a pus si ce nu, cu motivul. Intoarce codurile celor nepuse (rezultat.json:
	numai nume)."""
	_jurnal("pus la loc: %s" % (", ".join(pus) or "nimic"))
	coduri = []
	randuri = []
	if nepus["tuxbox"]:
		coduri.append("tuxbox")
		randuri.append("etc/tuxbox: %d fisiere xml in copie, raman cele din imagine (ca trusa)" % nepus["tuxbox"])
	if nepus["semne"]:
		coduri.append("semne")
		randuri.append("%d semne ale imaginii vechi (porniri, probe, opriri automate)" % nepus["semne"])
	if not acest:
		coduri.append("alt-receptor")
		randuri.append("copia e de pe alt receptor: setarile, reteaua, machine-id, cheile SSH, sistem.json, modulele de "
			"acces conditionat si %d fisiere ale receptorului" % nepus["proprii"])
	scoase = [k for k in SCOT if k in dict(_perechi(settings_copie))]
	if acest and scoase:
		coduri.append("setari-scoase")
		randuri.append("din setari: %s" % ", ".join(scoase))
	if acest and ARH_ACCES in d["md5"] and not acces:
		coduri.append("acces")
		randuri.append("modulele de acces conditionat (copia lor refuzata)")
	if sistem_refuzat:
		coduri.append("sistem")
		randuri.append("sistem.json (refuzat)")
	_jurnal("nepus: %s" % ("; ".join(randuri) or "nimic"))
	return coduri


def _numara_randuri(cale):
	date = _citeste_mic(cale, 64 * 1024 * 1024)
	return date.count(b"\n") if date else 0


def _numara_chei(cale):
	date = _citeste_mic(cale, 8 * 1024 * 1024)
	return sum(1 for r in (date or b"").splitlines() if b"=" in r)


def _pune_acces(rad, membri, pachete, porneste_modulele):
	"""Pune la loc modulele de acces conditionat. Intoarce (numarul fisierelor puse, notele pentru ecran)."""
	note = []
	pus = 0
	feluri = feluri_acces(rad)
	programe = _dosare_programe(feluri)
	opkg = os.environ.get("HDS_OPKG") or (_c(rad, "usr/bin/opkg") if rad == "/" else "")
	instalate = set()
	date_dupa_nume = dict((n, (m, date)) for n, m, date in membri)
	for p in pachete:
		ipk = p.get("ipk")
		if ipk and ipk in date_dupa_nume and opkg and os.path.isfile(opkg):
			d = os.path.join(dosar_restaurare(rad), "ipk")
			os.makedirs(d, exist_ok=True)
			cale = os.path.join(d, os.path.basename(ipk))
			_scrie_atomic(cale, date_dupa_nume[ipk][1], 0o600)
			try:
				import subprocess
				r = subprocess.run([opkg, "install", cale], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
					timeout=180)
				if r.returncode == 0:
					instalate.add(p["nume"])
			except Exception:
				pass
			try:
				os.remove(cale)
			except OSError:
				pass
	# fisierele pachetelor neinstalate prin opkg: numai unde imaginea nu are deja un fisier (afara de programele si
	# scripturile modulelor si de informatiile opkg ale pachetului)
	pachet_al = {}
	for nume, _m, date in membri:
		mm = re.match(r"^var/lib/opkg/info/(.+)\.list$", nume)
		if mm and date is not None:
			for rand in date.decode("utf-8", "replace").splitlines():
				norm = _normalizat(rand.split("\t", 1)[0].strip().lstrip("/"))
				if norm:
					pachet_al[norm] = mm.group(1)
	sarite = 0
	for nume, m, date in membri:
		if nume.startswith(META_ACCES):
			continue
		pachet = pachet_al.get(nume)
		mm = re.match(r"^var/lib/opkg/info/(.+)\.[a-z0-9]+$", nume)
		if mm:
			pachet = mm.group(1)
		if pachet in instalate and not nume.startswith(DOSAR_CONFIG_ACCES):
			continue
		tinta = _c(rad, nume)
		if m.isdir():
			if not os.path.isdir(tinta) and not os.path.lexists(tinta):
				os.makedirs(tinta)
			continue
		if m.issym():
			if os.path.lexists(tinta) and not os.path.islink(tinta):
				continue
			d = os.path.dirname(tinta)
			if not os.path.isdir(d):
				os.makedirs(d)
			nou = tinta + ".hds-nou"
			try:
				os.remove(nou)
			except OSError:
				pass
			os.symlink(m.linkname, nou)
			os.replace(nou, tinta)
			pus += 1
			continue
		e_program = bool(programe) and nume.startswith(programe)
		s = TIPAR_SCRIPT_ACCES.match(nume)
		suprascrie = (e_program or nume.startswith(DOSAR_CONFIG_ACCES)
			or (s is not None and s.group(1) in feluri) or nume.startswith("var/lib/opkg/info/"))
		if os.path.lexists(tinta) and (not suprascrie or os.path.islink(tinta) or os.path.isdir(tinta)):
			sarite += 1
			continue
		d = os.path.dirname(tinta)
		if not os.path.isdir(d):
			os.makedirs(d)
		_scrie_atomic(tinta, date, _mod_fisier(m, 0o755 if e_program else 0o644))
		pus += 1
	if sarite:
		note.append(ngettext("%d fișier al modulelor exista deja în imagine și a rămas al imaginii.",
			"%d fișiere ale modulelor existau deja în imagine și au rămas ale imaginii.", sarite) % sarite)
	# pachetele puse din fisiere: trecute in starea opkg, ca opkg sa stie de ele
	status = _c(rad, "var/lib/opkg/status")
	if os.path.isdir(os.path.dirname(status)):
		vechi = (_citeste_mic(status, 8 * 1024 * 1024) or b"").decode("utf-8", "replace")
		adaugat = vechi
		for p in pachete:
			if p["nume"] in instalate or not p.get("strofa"):
				continue
			if re.search(r"^Package:\s*%s\s*$" % re.escape(p["nume"]), adaugat, re.M):
				continue
			adaugat = adaugat.rstrip("\n") + ("\n\n" if adaugat.strip() else "") + str(p["strofa"]).strip("\n") + "\n"
		if adaugat != vechi:
			_scrie_atomic(status, adaugat.encode("utf-8"), 0o644)
	if porneste_modulele:
		_porneste_modulul(rad)
	return pus, note


def _porneste_modulul(rad):
	"""Scriptul ales al fiecarui fel (/etc/init.d/<fel>, felurile in ordinea lui feluri_acces: intai al modulelor
	obisnuite), pornit direct cu "start", fara interpretor de comenzi, cu termen; numai daca legatura arata spre un
	script <fel>.<x> care nu e cel gol."""
	import subprocess
	feluri = feluri_acces(rad)
	for fel in feluri:
		legatura = _c(rad, "etc/init.d/" + fel)
		tinta = _citeste_legatura(legatura)
		if not tinta or not _legatura_buna("etc/init.d/" + fel, tinta, feluri) or tinta.endswith("." + SUFIX_GOL_ACCES):
			continue
		script = _c(rad, "etc/init.d/" + tinta)
		if os.path.isfile(script) and os.access(script, os.X_OK):
			try:
				subprocess.run([script, "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
					start_new_session=True)
			except Exception:
				pass


# ---------------------------------------------------------------- pornirea (din enigma2.sh)

def _scrie_rezultat(rad, rez):
	d = dosar_restaurare(rad)
	os.makedirs(d, exist_ok=True)
	_scrie_atomic(os.path.join(d, REZULTAT), json.dumps(rez, ensure_ascii=True, sort_keys=True).encode("ascii"), 0o600)


def citeste_rezultat(rad=None):
	date = _citeste_mic(os.path.join(dosar_restaurare(rad), REZULTAT), 64 * 1024)
	if not date:
		return None
	try:
		rez = json.loads(date.decode("ascii"))
	except (ValueError, UnicodeDecodeError):
		return None
	return rez if isinstance(rez, dict) else None


def _atinge(cale):
	with open(cale, "ab"):
		pass


def cere_punerea(id_copie, lista=None, rad=None):
	"""Cererea de punere la loc, facuta la urmatoarea pornire a interfetei (enigma2.sh). (ok, mesaj)."""
	rad = radacina(rad)
	lista = copii(rad=rad) if lista is None else lista
	c = copie_dupa_id(id_copie, lista)
	if c is None or citeste_descriere(c["id"]) is None:
		return False, _("Copia nu mai este pe mediu.")
	d = dosar_restaurare(rad)
	try:
		os.makedirs(d, exist_ok=True)
		_scrie_atomic(os.path.join(d, CERERE), (c["id"] + "\n").encode("utf-8", "surrogateescape"), 0o600)
	except OSError as eroare:
		return False, _("Cererea nu s-a putut scrie (%s).") % (eroare.strerror or eroare.__class__.__name__)
	return True, _("Copia se pune la loc la repornirea interfeței.")


def anuleaza_cererea(rad=None):
	try:
		os.remove(os.path.join(dosar_restaurare(rad), CERERE))
	except OSError:
		pass


def _blocuri_nemontate():
	"""Discurile USB (sd*) vazute de nucleu care nu au inca nicio partitie montata."""
	try:
		discuri = [n for n in os.listdir("/sys/block") if n.startswith("sd")]
	except OSError:
		return False
	try:
		with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as f:
			montate = f.read()
	except OSError:
		montate = ""
	for disc in discuri:
		if "/dev/" + disc not in montate:
			return True
	return False


def _cea_mai_noua(rad):
	"""(copia aleasa la prima pornire, toate): a acestui receptor, altfel de acelasi model (numai canalele)."""
	toate = copii(rad=rad)
	model = model_aici(rad)
	for c in toate:
		if c["acest"]:
			return c, toate
	for c in toate:
		if c["model"] == model:
			return c, toate
	return None, toate


def _marcheaza_alta_imagine(rad):
	"""Prima pornire fara copie HD Satelit: dupa pornirea sesiunii se cauta copia altei imagini
	si se intreaba daca se aduce (Components/HdsImportAltaImagine.py). Aici numai semnul, fara alta cautare,
	ca pornirea sa nu se lungeasca."""
	try:
		from Components import HdsImportAltaImagine
		if HdsImportAltaImagine.marcheaza_cautarea(rad):
			_jurnal("dupa pornirea interfetei se cauta o copie a altei imagini")
	except Exception as eroare:
		_jurnal("semnul copiei altei imagini: %s" % eroare.__class__.__name__)


def pornire(rad=None, asteapta=True):
	"""Chemata din enigma2.sh inainte de enigma2: cererea din meniu sau web, altfel prima pornire a imaginii.
	Intoarce 0 mereu (pornirea receptorului nu depinde de copie)."""
	rad = radacina(rad)
	d = dosar_restaurare(rad)
	try:
		os.makedirs(d, exist_ok=True)
	except OSError:
		return 0
	cerere = os.path.join(d, CERERE)
	if os.path.isfile(cerere):
		date = _citeste_mic(cerere, 4096) or b""
		# cererea se sterge intai: o cadere la punere nu o repeta la fiecare pornire
		try:
			os.remove(cerere)
		except OSError:
			pass
		dosar = date.decode("utf-8", "surrogateescape").strip()
		if not os.path.isfile(os.path.join(dosar, DESCRIERE)):
			_jurnal("cererea arata spre o copie care nu mai e pe mediu, nu scriu nimic")
			_scrie_rezultat(rad, {"ok": False, "pus": [], "note": [_("Copia aleasă nu mai era pe mediu la repornire; "
				"nu s-a pus nimic la loc.")], "repornire": "nu", "aratat": False, "motiv": "cerere",
				"cand": int(time.time()), "copie": {}})
			return 0
		_jurnal("=== %s, cererea din meniu sau web" % time.strftime("%Y-%m-%d %H:%M:%S"))
		rez = pune_la_loc(dosar, rad, "cerere")
		_atinge(os.path.join(d, SEMN_GATA))
		_atinge(os.path.join(d, SEMN_PRIMA))
		_scrie_rezultat(rad, rez)
		return 0
	prima = os.path.join(d, SEMN_PRIMA)
	if os.path.exists(prima):
		return 0
	gata = os.path.join(d, SEMN_GATA)
	if os.path.exists(gata) or os.path.exists(_c(rad, "etc/enigma2/settings")):
		_atinge(prima)
		return 0
	_jurnal("=== %s, prima pornire a imaginii, caut o copie a setarilor" % time.strftime("%Y-%m-%d %H:%M:%S"))
	try:
		inceput = time.time()
		while True:
			aleasa, toate = _cea_mai_noua(rad)
			if aleasa is not None or not asteapta:
				break
			if time.time() - inceput >= ASTEPTARE_MEDII_S:
				break
			if not _blocuri_nemontate() and _uptime() >= UPTIME_MEDII_S:
				break
			time.sleep(1)
		if aleasa is None:
			_jurnal("nicio copie a acestui model pe mediile montate (%d copii gasite)" % len(toate))
			_marcheaza_alta_imagine(rad)
			return 0
		_jurnal("copia aleasa: %s (%s)" % (os.path.basename(aleasa["id"]), "acest receptor" if aleasa["acest"]
			else "alt receptor"))
		rez = pune_la_loc(aleasa["id"], rad, "automat")
		_atinge(gata)
		_scrie_rezultat(rad, rez)
		return 0
	finally:
		# semnul primei porniri se scrie si dupa o eroare neprinsa (un stick sau o copie ciudata): altfel cautarea s-ar
		# relua la fiecare pornire
		try:
			_atinge(prima)
		except OSError:
			pass


# ---------------------------------------------------------------- textele rezultatului

def texte_puse(pus):
	nume = {
		"canale": _("canalele, buchetele și listele DAB+ și DVB-T2"),
		"setari": _("setările"),
		"retea": _("rețeaua și Wi-Fi"),
		"masina": _("cheile de traducere ale receptorului"),
		"chei": _("cheile SSH"),
		"acces": _("modulele de acces condiționat"),
	}
	return [nume[p] for p in pus if p in nume]


def mesaj_rezultat(rez):
	"""Mesajul scurt de pe televizor (si din web) dupa o punere la loc."""
	c = rez.get("copie") or {}
	puse = texte_puse(rez.get("pus") or [])
	if puse:
		text = _("Am pus la loc din copia din %s (imaginea %s): %s.") % (c.get("data_text", ""),
			c.get("versiune") or "?", ", ".join(puse))
	else:
		text = _("Copia setărilor nu s-a pus la loc.")
	if rez.get("pus") and not rez.get("acest"):
		text += " " + _("Copia era de pe alt receptor, deci numai canalele.")
	note = rez.get("note") or []
	if note:
		text += "\n" + "\n".join(note[:3])
	return text


# ---------------------------------------------------------------- pe receptor: setarile, starea comuna, ceasul

def config_copie():
	"""config.hds_copie_setari: automat (oprita / zilnic), pastrate (copii automate pe mediu), ultima (secunde)."""
	from Components.config import config, ConfigSubsection, ConfigSelection, ConfigInteger
	# hasattr(config, ...) nu merge: ConfigSubsection.__getattr__ arunca KeyError pentru o cheie lipsa, iar hasattr()
	# prinde numai AttributeError; se cauta in content.items, ca in Components/HdsJurnalVersiuni.py
	if "hds_copie_setari" not in config.content.items:
		config.hds_copie_setari = ConfigSubsection()
		c = config.hds_copie_setari
		c.automat = ConfigSelection(default="oprita", choices=[("oprita", _("Oprită")), ("zilnic", _("Zilnic"))])
		c.pastrate = ConfigSelection(default=str(PASTRATE_IMPLICIT),
			choices=[(str(i), str(i)) for i in range(1, PASTRATE_MAXIM + 1)])
		c.ultima = ConfigInteger(default=0)
	return config.hds_copie_setari


def seteaza_automat(automat=None, pastrate=None):
	"""Schimba copia automata (ecranul si web). (ok, mesaj)."""
	c = config_copie()
	if automat is not None:
		if automat not in ("oprita", "zilnic"):
			return False, _("Alegere necunoscută.")
		c.automat.value = automat
	if pastrate is not None:
		try:
			n = int(pastrate)
		except (TypeError, ValueError):
			return False, _("Numărul copiilor păstrate trebuie să fie între 1 și %d.") % PASTRATE_MAXIM
		if not 1 <= n <= PASTRATE_MAXIM:
			return False, _("Numărul copiilor păstrate trebuie să fie între 1 și %d.") % PASTRATE_MAXIM
		c.pastrate.value = str(n)
	c.save()
	from Components.config import configfile
	configfile.save()
	return True, text_automat()


def text_automat():
	c = config_copie()
	if c.automat.value != "zilnic":
		return _("Copia automată e oprită.")
	text = _("Copia automată se face zilnic; se păstrează ultimele %s pe mediu.") % c.pastrate.value
	if c.ultima.value:
		text += " " + _("Ultima: %s.") % _data_text(c.ultima.value)
	return text


# Setarile scrise mereu in settings (save_forced), cu motivul: valoarea lor din fabrica s-a schimbat intre versiunile
# publicate (de la 0.1.0) sau e
# alegerea cea mai vizibila. Nu intra: modelul Gemini (urmeaza valoarea din fabrica, schimbata cand Google scoate un
# model), accelerarea 2D (SCOT, o hotaraste imaginea), locul antenei din Nims (schimbat inainte de 0.1.0, si
# creat pe tuner), semnele asistentului de pornire (stare, nu alegere).
SETARI_FIXE = (
	("config.hds_traducere.serviciu", "0.1.9: azure in locul lui gemini"),
	("config.hds_traducere.rezerve", "lantul rezervelor, ales impreuna cu serviciul (din 0.1.9)"),
	("config.osd.language", "17.09.2026: ro_RO in locul lui en_EN; limba meniului"),
	("config.usage.infobar_timeout", "0.1.5: 8 secunde in locul lui 5"),
	("config.av.aspectratio", "23.09.2026: 16_9_always in locul lui 4_3_letterbox"),
	("config.plugins.hdswebcontrol.port", "0.1.6: 80 in locul lui 8080"),
)
PREFIX_TRADUCERE = "config.hds_traducere."


def _element_config(cale, radacina_config):
	"""Elementul de configurare de la `cale` („config.a.b”) din arborele `radacina_config`, sau None daca nu exista
	(inca). Fara getattr pe ConfigSubsection: __getattr__ arunca KeyError pentru o cheie lipsa."""
	obiect = radacina_config
	for nume in cale.split(".")[1:]:
		try:
			copii = obiect.dict()
		except AttributeError:
			return None
		if nume not in copii:
			return None
		obiect = copii[nume]
	return obiect


def fixeaza_setari(prefix=None, fara=None, radacina_config=None):
	"""save_forced pe SETARI_FIXE care exista acum (cele cu `prefix`, fara cele cu `fara`) si save() o data pe cele fara
	rand in settings (saved_value None): valoarea de acum intra in config.pickle() (copia) si in settings la urmatoarea
	salvare (orice setare schimbata, iesirea din enigma2). Fara configfile.save() aici. Sare elementele care nu sunt
	setari (ConfigNothing, sectiuni). -> numele scrise acum."""
	if radacina_config is None:
		from Components.config import config as radacina_config
	scrise = []
	for cale, _motiv in SETARI_FIXE:
		if (prefix and not cale.startswith(prefix)) or (fara and cale.startswith(fara)):
			continue
		el = _element_config(cale, radacina_config)
		if el is None or not hasattr(el, "save_forced") or el.__class__.__name__ == "ConfigNothing":
			continue
		el.save_forced = True
		if el.saved_value is None:
			el.save()
			scrise.append(cale)
	if scrise:
		_jurnal("setarile scrise mereu, randul pus acum: %s" % ", ".join(scrise))
	return scrise


_STARE = {"cauta": False, "lucreaza": None, "medii": [], "copii": [], "cand": 0, "ultimul": None}
_ZAVOR = threading.Lock()
_VII = []


def stare():
	return _STARE


def ocupat():
	return bool(_STARE["lucreaza"])


def _porneste_lucrare(functie, la_sfarsit):
	from Components.HdsImportSurse import Lucrare
	lucrare = []
	terminat = []

	def _gata(rez, eroare):
		terminat.append(True)
		for l in lucrare:
			if l in _VII:
				_VII.remove(l)
		la_sfarsit(rez, eroare)

	l = Lucrare(functie, _gata)
	if not terminat:
		lucrare.append(l)
		_VII.append(l)
	return l


def porneste_cautarea(la_sfarsit=None):
	"""Mediile si copiile, citite pe un fir separat; rezultatul in starea comuna (ecran si web)."""
	with _ZAVOR:
		if _STARE["cauta"]:
			return False
		_STARE["cauta"] = True

	def lucru():
		m = medii()
		return m, copii(m)

	def gata(rez, eroare):
		if eroare or not rez:
			_jurnal("cautarea copiilor: %s" % eroare)
			rez = ([], [])
		_STARE.update(medii=rez[0], copii=rez[1], cauta=False, cand=time.time())
		if la_sfarsit is not None:
			la_sfarsit()

	try:
		_porneste_lucrare(lucru, gata)
	except Exception:
		_STARE["cauta"] = False
		raise
	return True


def text_setari_acum():
	"""settings de acum, din arborele config (ce ar scrie enigma2 la iesire), pe firul enigma2; intai SETARI_FIXE puse
	cu valoarea de acum (fixeaza_setari), ca o alegere egala cu valoarea din fabrica sa intre si ea in copie."""
	modul = sys.modules.get("Components.config")
	if modul is not None:
		try:
			fixeaza_setari(radacina_config=modul.config)
		except Exception as eroare:
			_jurnal("setarile scrise mereu: %s" % eroare.__class__.__name__)
		try:
			text = modul.config.pickle()
			if text:
				return text
		except Exception as eroare:
			_jurnal("config.pickle: %s" % eroare.__class__.__name__)
	return None


def porneste_copia(id_mediu, fel="manuala", la_sfarsit=None):
	"""Pe firul enigma2: ia setarile de acum si porneste copia pe un fir separat. (pornit, mesaj)."""
	with _ZAVOR:
		if _STARE["lucreaza"]:
			return False, _("O copie se face deja. Așteaptă să se termine.")
		_STARE["lucreaza"] = "copie"
	m = mediu_dupa_id(id_mediu, _STARE["medii"] or medii())
	if m is None:
		_STARE["lucreaza"] = None
		return False, _("Mediul ales nu mai este montat.")
	text = text_setari_acum()

	def lucru():
		rez = fa_copia(m["punct"], text, fel)
		if rez.get("ok") and fel == "automata":
			try:
				sterse = curata_automate(m["punct"], int(config_copie().pastrate.value))
				if sterse:
					rez["mesaje"].append(ngettext("%d copie automată veche ștearsă.", "%d copii automate vechi șterse.",
						sterse) % sterse)
			except Exception as eroare:
				_jurnal("curatarea copiilor automate: %s" % eroare.__class__.__name__)
		return rez

	def gata(rez, eroare):
		if not isinstance(rez, dict):
			rez = {"ok": False, "mesaje": [_("Copia s-a oprit: %s.") % (eroare or "?")]}
		_STARE["lucreaza"] = None
		_STARE["ultimul"] = rez
		if rez.get("ok") and fel == "automata":
			try:
				c = config_copie()
				c.ultima.value = int(time.time())
				c.ultima.save()
				from Components.config import configfile
				configfile.save()
			except Exception as e:
				_jurnal("ultima copie automata: %s" % e.__class__.__name__)
		porneste_cautarea()
		if la_sfarsit is not None:
			la_sfarsit(rez)

	try:
		_porneste_lucrare(lucru, gata)
	except Exception:
		_STARE["lucreaza"] = None
		raise
	return True, _("Se face copia pe %s…") % m["nume"]


class _Ceas(object):
	"""Copia automata zilnica: o verificare la 15 minute (prima la 10 minute dupa pornire)."""

	def __init__(self):
		from enigma import eTimer
		self.t = eTimer()
		try:
			self._legatura = self.t.timeout.connect(self.verifica)
		except AttributeError:
			self.t.callback.append(self.verifica)
		self.t.start(10 * 60 * 1000, True)

	def verifica(self):
		try:
			self._verifica()
		finally:
			self.t.start(15 * 60 * 1000, True)

	def _verifica(self):
		c = config_copie()
		acum = int(time.time())
		if c.automat.value != "zilnic" or acum < 1704067200 or ocupat():
			return
		if c.ultima.value and acum - int(c.ultima.value) < ZI_S - TOLERANTA_ZI_S:
			return
		lista = medii()
		m = mediu_implicit(lista)
		if m is None:
			return
		_STARE["medii"] = lista
		porneste_copia(m["id"], "automata")


_CEAS = []


def porneste(session):
	"""Din mytest.py, dupa pornirea sesiunii: SETARI_FIXE (fara cele ale traducerii), mesajul de dupa punerea la loc (cu
	repornirea receptorului o data, cand reteaua din copie intra numai la pornire) si ceasul copiei automate. Nu
	arunca."""
	try:
		config_copie()
	except Exception as eroare:
		_jurnal("setarile copiei: %s" % eroare.__class__.__name__)
	try:
		# cele ale traducerii le scrie legaNucleul, dupa verificarea cheilor (Components/HdsTraducereSubtitrari.py)
		fixeaza_setari(fara=PREFIX_TRADUCERE)
	except Exception as eroare:
		_jurnal("setarile scrise mereu: %s" % eroare.__class__.__name__)
	try:
		_arata_rezultatul(session)
	except Exception as eroare:
		_jurnal("mesajul punerii la loc: %s" % eroare.__class__.__name__)
	try:
		# prima pornire fara copie HD Satelit: copia altei imagini, cu intrebare (semnul l-a pus pornire())
		from Components import HdsImportAltaImagine
		HdsImportAltaImagine.porneste(session)
	except Exception as eroare:
		_jurnal("copia altei imagini: %s" % eroare.__class__.__name__)
	try:
		if not _CEAS:
			_CEAS.append(_Ceas())
	except Exception as eroare:
		_jurnal("ceasul copiei automate: %s" % eroare.__class__.__name__)


def _arata_rezultatul(session):
	rez = citeste_rezultat()
	if not rez:
		return
	from Tools import Notifications
	from Screens.MessageBox import MessageBox
	if rez.get("repornire") == "ceruta":
		rez["repornire"] = "facuta"
		_scrie_rezultat(radacina(), rez)
		text = mesaj_rezultat(rez) + "\n" + _("Receptorul repornește o dată acum, ca să intre rețeaua din copie.")

		def reporneste(*_a):
			from Screens.Standby import TryQuitMainloop
			session.open(TryQuitMainloop, 2)
		Notifications.AddNotificationWithCallback(reporneste, MessageBox, text, type=MessageBox.TYPE_INFO, timeout=15)
		return
	if not rez.get("aratat"):
		rez["aratat"] = True
		_scrie_rezultat(radacina(), rez)
		Notifications.AddPopup(mesaj_rezultat(rez), MessageBox.TYPE_INFO, 20, "HdsCopieSetari")


if __name__ == "__main__":
	# din enigma2.sh: python3 -E -s -B .../Components/HdsCopieSetari.py pornire
	sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
	if len(sys.argv) > 1 and sys.argv[1] == "pornire":
		try:
			pornire()
		except Exception as eroare:
			_jurnal("pornirea s-a oprit: %s" % eroare.__class__.__name__)
	sys.exit(0)
