# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMediaCenter: porneste Media Center (Kodi 22 din OE-Alliance, redenumit; pachetul masinii) pe tot ecranul, in locul
# interfetei, si intoarce omul in enigma2 cand iese din el. Pachetul enigma2-plugin-extensions-hdsmediacenter, din feedul
# nostru, nu din imagine; trage cu el Kodi-ul masinii (RDEPENDS virtual-kodi).
#
# Drumul (acelasi ca in imaginile OE-Alliance; partea de stare e luata din pluginul OE-Alliance STBKodiLauncher,
# GPL-2.0-only, https://github.com/oe-alliance-plugins/STBKodiLauncher):
#   1. porneste(session): verifica programul si locul datelor (Kodi isi tine tot profilul pe /media/hdd/.kodi, fixat in
#      codul lui; locul ales ca in tools/enigma2.sh: discul de pe /media/hdd, altfel memoria interna cand are loc, altfel
#      un stick USB; vezi mediu()), scrie volumul si sunetul oprit pentru Kodi
#      (/tmp/stb-kodi-e2-audio) si starea LED-urilor (/tmp/stb-kodi-e2-hardware), leaga modulul Widevine adus de om
#      (calea unica a imaginii, Components/HdsWidevine.py) in dosarul cdm al profilului, cere modul HDMI 2160p cand
#      televizorul il prefera (VIDEO_CERERE, aplicat de tools/enigma2.sh inainte de Kodi; interfata Kodi ramane 1080p,
#      video-ul merge pe decodorul receptorului), apoi cere iesirea cu codul 15 (Screens/Standby.TryQuitMainloop:
#      intreaba numai daca se inregistreaza ceva sau ruleaza o instalare).
#   2. tools/enigma2.sh (imaginea, cazul 15) porneste Kodi; cand Kodi se termina, init porneste din nou enigma2.
#   3. La pornirea interfetei (WHERE_SESSIONSTART), daca ultima rulare n-a mers (/tmp/hds-kodi.stare: cod diferit de 0
#      sau motiv), omul afla de ce, o singura data.
#   4. „Power off system” si „Reboot” din Kodi (si oprirea la ceasul lui): Kodi nu opreste nimic pe un receptor
#      (FallbackPowerSyscall), ci iese cu 64 sau 66 (xbmc/application/ApplicationEnums.h). La intoarcerea in interfata
#      pluginul face oprirea sau repornirea CA DIN MENIUL enigma2 (Screens/Standby.TryQuitMainloop: intreaba numai daca se
#      inregistreaza ceva sau urmeaza o inregistrare; la oprire pune ceasul de trezire pentru urmatoarea inregistrare).
#      Hotararea coordonatorului, 13.11.2026 20:30 (KOD3).
#   5. Limba (hotararea coordonatorului, 13.11.2026 20:30): Media Center porneste in limba aleasa in enigma2. Kodi 22 nu
#      mai aduce singur o limba lipsa (CLangInfo::SetLanguage cade pe engleza), dar porneste singur un addon de limba aflat
#      in profil; deci, inainte de iesire, pluginul aduce addonul de limba din depozitul oficial (cel din
#      repository.xbmc.org/addon.xml, cu suma sha256 a depozitului) in <profil>/addons si scrie limba in guisettings.xml.
#      O singura data pentru fiecare limba a enigma2 (semnul .hds-limba din userdata): o limba aleasa apoi de om in Kodi
#      ramane. Fara internet porneste in engleza si incearca din nou data viitoare. Fara intrebari pentru om.
# Meniul Aplicatii (Components/HdsAplicatii.py, magazinul) cheama porneste(session) din acest fisier.

import gzip
import hashlib
import io
import os
import re
import shutil
import threading
import time
import zipfile
import xml.etree.ElementTree as ET

from Plugins.Plugin import PluginDescriptor

PROGRAM = "/usr/bin/kodi"
HDD = "/media/hdd"
# memoria interna (13.11.2026, coordonatorul, regula 1f: fara stick cand e loc): legata pe /media/hdd cat ruleaza Kodi;
# un profil nou cere INTERN_NOU_KB liberi, unul existent ramane cat sunt INTERN_MIN_KB (aceleasi praguri ca enigma2.sh)
INTERN = "/home/root/.media-center"
INTERN_MIN_KB = 512 * 1024
INTERN_NOU_KB = 2 * 1024 * 1024
MONTARI = "/proc/mounts"
STARE = "/tmp/hds-kodi.stare"
AUDIO = "/tmp/stb-kodi-e2-audio"
HARDWARE = "/tmp/stb-kodi-e2-hardware"
QUIT_KODI = 15     # Screens/Standby.py si tools/enigma2.sh.in
# modulul Widevine: calea unica din imagine (Components/HdsWidevine.py), adus de om de la Google dupa acceptul licentei
WIDEVINE = "/home/root/.local/share/widevine/libwidevinecdm.so"
VIDEO_MOD = "/proc/stb/video/videomode"
VIDEO_PREFERAT = "/proc/stb/video/videomode_preferred"
VIDEO_ALEGERI = "/proc/stb/video/videomode_choices"
VIDEO_CERERE = "/tmp/hds-kodi.videomode"   # citit si sters de tools/enigma2.sh (cazul 15)

# codurile de iesire ale Kodi (xbmc/application/ApplicationEnums.h): oprire, repornirea programului, repornire
KODI_OPRIRE = "64"
KODI_REPORNIRE_PROGRAM = "65"
KODI_REPORNIRE = "66"
# o iesire 64/66 mai veche de atat (dupa /proc/uptime) nu mai opreste nimic: un fisier ramas dupa o cadere a interfetei
# nu are voie sa opreasca receptorul mai tarziu
PROASPAT_S = 180
UPTIME = "/proc/uptime"

# limba (punctul 5 de sus)
KODI_SISTEM = "/usr/share/kodi/addons"
DEPOZIT_ADDON = KODI_SISTEM + "/repository.xbmc.org/addon.xml"
ENGLEZA = "resource.language.en_gb"   # vine cu Kodi
SEMN_LIMBA = ".hds-limba"             # in <profil>/.kodi/userdata: codul enigma2 aplicat ultima data
LIMBA_RETEA_S = 8                     # fiecare cerere in retea
LIMBA_MAX_S = 25                      # cat asteapta iesirea dupa limba; apoi Kodi porneste oricum
LIMBA_ZIP_MAX = 8 * 1024 * 1024       # un addon de limba are sub 1 MB

# Numele aratat omului (meniu, card): neutru, fiindca Kodi-ul nostru e modificat (petice OE-Alliance) si neaprobat de
# XBMC Foundation, deci fara „Kodi” in nume si fara sigla Kodi (politica marcii, kodi.wiki Official:Distribution_Policy).
NUME = "Media Center"


def N_(text):
	return text


TEXT_DESCRIERE = N_("Filme, muzică și poze de pe stick, disc sau din rețea, pe tot ecranul.")
# Singura mentiune a marcii permisa unei versiuni modificate si neaprobate (Distribution Policy, Rebranded Distributions):
# „Powered by Kodi”, netradusa, fara sigla si fara sa sugereze aprobarea XBMC Foundation.
MARCA = "Powered by Kodi"


def descriere():
	return _(TEXT_DESCRIERE) + " " + MARCA
TEXT_NEINSTALAT = N_("Centrul media nu e instalat. Îl găsești în meniul Aplicații.")
TEXT_FARA_DISC = N_("Nu e loc pentru datele centrului media: memoria receptorului are sub 2 GB liberi. "
	"Pune un stick USB (cel puțin 2 GB) și pornește din nou.")
TEXT_NUMAI_CITIRE = N_("Pe stickul sau discul conectat nu se poate scrie. Pune alt stick sau verifică discul și "
	"pornește din nou.")
TEXT_CADERE = N_("Centrul media s-a oprit neașteptat (codul %s). Dacă se repetă, trimite jurnalul din asistență.")

# ce se salveaza inainte de iesire (ca in STBKodiLauncher): numele, fisierul, numai primul camp
STARE_HARDWARE = (
	("led_blink", "/proc/stb/fp/led_blink", False),
	("led_brightness", "/proc/stb/fp/led_brightness", False),
	("led_color", "/proc/stb/fp/led_color", False),
	("led_fade", "/proc/stb/fp/led_fade", False),
	("aml_freerun_mode", "/sys/class/video/freerun_mode", True),
	("aml_dec_control", "/sys/module/amvdec_h264/parameters/dec_control", True),
	("aml_nal_skip_policy", "/sys/module/amvdec_h265/parameters/nal_skip_policy", True),
	("aml_di_debug_flag", "/sys/module/di/parameters/di_debug_flag", True),
	("aml_tsync_enable", "/sys/class/tsync/enable", True),
	("aml_frac_rate_policy", "/sys/class/amhdmitx/amhdmitx0/frac_rate_policy", True),
	("aml_display_mode", "/sys/class/display/mode", False),
)


def instalat(program=PROGRAM):
	return os.access(program, os.X_OK)


def _deschide(cale):
	return open(cale, "r")


def liberKb(dosar):
	try:
		s = os.statvfs(dosar)
		return s.f_bavail * s.f_frsize // 1024
	except (OSError, AttributeError):
		return 0


def mediu(montari=MONTARI, hdd=HDD, intern=INTERN, liber=None):
	"""Unde sta profilul, ca in tools/enigma2.sh.in (cazul 15): hdd daca e montat (discul inregistrarilor), altfel
	memoria interna (profil existent si INTERN_MIN_KB liberi, sau INTERN_NOU_KB liberi), altfel primul stick/disc USB
	montat langa hdd (/media/usb...); None daca nu e loc nicaieri. Partajarile de retea nu conteaza."""
	parinte = hdd.rsplit("/", 1)[0] + "/"
	usb = None
	try:
		with _deschide(montari) as f:
			randuri = f.read().splitlines()
	except (IOError, OSError):
		randuri = []
	for rand in randuri:
		c = rand.split()
		if len(c) < 2:
			continue
		dispozitiv, loc = c[0], c[1]
		if loc == hdd:
			return hdd
		if usb is None and loc.startswith(parinte + "usb") and "/" not in loc[len(parinte):] and \
			(dispozitiv.startswith("/dev/sd") or (dispozitiv.startswith("/dev/mmcblk") and not dispozitiv.startswith("/dev/mmcblk0"))):
			usb = loc
	if liber is None:
		liber = liberKb(os.path.dirname(intern))
	if (os.path.isdir(os.path.join(intern, ".kodi")) and liber >= INTERN_MIN_KB) or liber >= INTERN_NOU_KB:
		return intern
	return usb


def seScrie(dosar):
	"""True daca pe mediu se poate face dosarul profilului si scrie un fisier (stick pus pe numai citire)."""
	try:
		d = os.path.join(dosar, ".kodi")
		if not os.path.isdir(d):
			os.makedirs(d)
		proba = os.path.join(d, ".hds-scriere")
		with open(proba, "w") as f:
			f.write("1")
		os.remove(proba)
		return True
	except (IOError, OSError):
		return False


def motivNuPorneste(program=PROGRAM, montari=MONTARI, hdd=HDD, intern=INTERN, liber=None):
	"""None daca se poate porni; altfel textul pentru om (netradus)."""
	if not instalat(program):
		return TEXT_NEINSTALAT
	loc = mediu(montari, hdd, intern, liber)
	if loc is None:
		return TEXT_FARA_DISC
	if not seScrie(loc):
		return TEXT_NUMAI_CITIRE
	return None


def salveazaStarea(audio=AUDIO, hardware=HARDWARE, volum=None):
	"""Volumul si sunetul oprit al enigma2 (Kodi preia acelasi nivel) si starea LED-urilor/placii video."""
	try:
		if volum is None:
			from enigma import eDVBVolumecontrol
			vc = eDVBVolumecontrol.getInstance()
			volum = (max(0, min(100, int(vc.getVolume()))), 1 if vc.isMuted() else 0)
		with open(audio, "w") as f:
			f.write("%d %d\n" % volum)
	except Exception as e:
		print("[HdsMediaCenter] volumul: %r" % (e,))
	valori = []
	for nume, cale, primul in STARE_HARDWARE:
		try:
			with open(cale, "r") as f:
				v = f.read().strip()
		except (IOError, OSError):
			continue
		if primul and v:
			v = v.split(":", 1)[0].split(None, 1)[0]
		if v and "\n" not in v and "\r" not in v:
			valori.append("%s=%s\n" % (nume, v))
	try:
		with open(hardware, "w") as f:
			f.writelines(valori)
	except (IOError, OSError):
		pass


def citesteStarea(cale=STARE):
	"""Ultima rulare scrisa de tools/enigma2.sh (pornit, sfarsit, cod sau motiv), {} daca nu e."""
	r = {}
	try:
		with open(cale, "r") as f:
			for rand in f.read().splitlines():
				if "=" in rand:
					k, v = rand.split("=", 1)
					r[k.strip()] = v.strip()
	except (IOError, OSError):
		pass
	return r


def mesajDupaRulare(stare):
	"""Textul pentru om dupa o rulare care n-a mers (netradus, cu %s inlocuit), sau None."""
	motiv = stare.get("motiv")
	if motiv == "neinstalat":
		return TEXT_NEINSTALAT, None
	if motiv == "fara-disc":
		return TEXT_FARA_DISC, None
	if motiv == "numai-citire":
		return TEXT_NUMAI_CITIRE, None
	cod = stare.get("cod", "")
	# 64/66 = Power off / Reboot din Kodi (le face laPornire prin enigma2), 65 = repornirea programului: nu sunt caderi
	if cod and cod not in ("0", KODI_OPRIRE, KODI_REPORNIRE_PROGRAM, KODI_REPORNIRE):
		return TEXT_CADERE, cod
	return None


def uptime(cale=UPTIME):
	try:
		with open(cale, "r") as f:
			return int(float(f.read().split()[0]))
	except (IOError, OSError, ValueError, IndexError):
		return None


def actiuneDupaRulare(stare, acum=None):
	"""1 (oprire, ca din meniul enigma2) sau 2 (repornire) cand Kodi a iesit cu 64/66 si iesirea e proaspata; None altfel."""
	cod = stare.get("cod")
	if cod not in (KODI_OPRIRE, KODI_REPORNIRE):
		return None
	if acum is None:
		acum = uptime()
	try:
		sfarsit = int(stare.get("sfarsit", ""))
	except ValueError:
		return None
	if acum is None or sfarsit > acum or acum - sfarsit > PROASPAT_S:
		return None
	return 1 if cod == KODI_OPRIRE else 2


def _citeste(cale):
	try:
		with open(cale, "r") as f:
			return f.read().strip()
	except (IOError, OSError):
		return ""


def legaWidevine(loc, modul=WIDEVINE):
	"""<loc>/.kodi/cdm/libwidevinecdm.so -> modulul din calea unica, cand modulul exista. Un fisier adevarat pus acolo
	de alt instalator (inputstreamhelper din Kodi) ramane neatins; o legatura veche se inlocuieste. True daca e legat."""
	if not loc or not os.path.isfile(modul):
		return False
	cdm = os.path.join(loc, ".kodi", "cdm")
	tinta = os.path.join(cdm, "libwidevinecdm.so")
	try:
		if not os.path.isdir(cdm):
			os.makedirs(cdm)
		if os.path.islink(tinta):
			if os.readlink(tinta) == modul:
				return True
			os.remove(tinta)
		elif os.path.exists(tinta):
			return False
		os.symlink(modul, tinta)
		return True
	except OSError as e:
		print("[HdsMediaCenter] legatura Widevine: %r" % (e,))
		return False


def mod2160(acum, preferate, alegeri):
	"""Modul HDMI 2160p de cerut pentru Kodi, sau None: numai cand televizorul il da in lista preferata (EDID), cand
	receptorul il stie si cand iesirea nu e deja 2160p; aceeasi familie de frecventa (50 Hz ramane 50 Hz)."""
	if not acum or acum.startswith("2160"):
		return None
	pref = preferate.split()
	ale = alegeri.split()
	dorite = ("2160p50", "2160p") if acum.endswith("50") else ("2160p", "2160p50")
	for m in dorite:
		if m in pref and m in ale:
			return m
	return None


def cere2160(cerere=VIDEO_CERERE):
	m = mod2160(_citeste(VIDEO_MOD), _citeste(VIDEO_PREFERAT), _citeste(VIDEO_ALEGERI))
	try:
		if m:
			with open(cerere, "w") as f:
				f.write(m + "\n")
		elif os.path.exists(cerere):
			os.remove(cerere)
	except (IOError, OSError):
		pass
	return m


def idLimbaKodi(cod):
	"""Codul limbii enigma2 („ro_RO”) -> addonul de limba Kodi dorit („resource.language.ro_ro”); engleza -> en_gb."""
	cod = (cod or "").replace("-", "_").split(".")[0].strip().lower()
	if not re.match(r"^[a-z]{2,3}(_[a-z0-9]+)?$", cod) or cod.startswith("en"):
		return ENGLEZA
	return "resource.language." + cod


def _limbaPrefix(dorit):
	"""„resource.language.ro_ro” -> „resource.language.ro_” (aceeasi limba, alta tara: ar_AE -> ar_sa)."""
	return "resource.language." + dorit[len("resource.language."):].split("_", 1)[0] + "_"


_TAG_ADDON = re.compile(r"<addon\s[^>]*>")
_ATRIBUT = re.compile(r'\b(id|version)="([^"]*)"')


def cautaInIndex(bucati, dorit):
	"""(id, versiune) din addons.xml dat pe bucati (text): intai addonul exact, altfel primul cu aceeasi limba."""
	prefix = _limbaPrefix(dorit)
	gasit = None
	rest = ""
	for bucata in bucati:
		text = rest + bucata
		capat = 0
		for m in _TAG_ADDON.finditer(text):
			capat = m.end()
			a = dict(_ATRIBUT.findall(m.group(0)))
			i, v = a.get("id", ""), a.get("version", "")
			if not v:
				continue
			if i == dorit:
				return i, v
			if gasit is None and i.startswith(prefix):
				gasit = (i, v)
		i = text.rfind("<", capat)
		rest = text[i:] if i >= 0 else ""
		if len(rest) > 65536:   # nicio eticheta <addon ...> nu e atat de lunga
			rest = ""
	return gasit


def _url(adresa, timeout=LIMBA_RETEA_S):
	from urllib.request import urlopen, Request
	return urlopen(Request(adresa, headers={"User-Agent": "MediaCenter/22 (HD Satelit)"}), timeout=timeout)


def depozit(cale=DEPOZIT_ADDON):
	"""(info, datadir) din addonul depozitului oficial care vine cu Kodi (aceeasi versiune de Kodi = acelasi dosar)."""
	try:
		r = ET.parse(cale).getroot()
		info, date = r.findtext(".//info"), r.findtext(".//datadir")
		if info and date:
			return info.strip(), date.strip().rstrip("/")
	except Exception as e:
		print("[HdsMediaCenter] depozitul: %r" % (e,))
	return None


def _bucatiGzip(raspuns, marime=65536):
	d = gzip.GzipFile(fileobj=raspuns)
	while True:
		b = d.read(marime)
		if not b:
			return
		yield b.decode("utf-8", "replace")


def limbaInstalata(kodi, dorit, sistem=KODI_SISTEM):
	"""Id-ul addonului de limba gasit in profil sau in Kodi: exact, apoi aceeasi limba; None daca nu e."""
	if dorit == ENGLEZA:
		return ENGLEZA
	dosare = (os.path.join(kodi, "addons"), sistem)
	for dosar in dosare:
		if os.path.isfile(os.path.join(dosar, dorit, "addon.xml")):
			return dorit
	prefix = _limbaPrefix(dorit)
	for dosar in dosare:
		try:
			for n in sorted(os.listdir(dosar)):
				if n.startswith(prefix) and os.path.isfile(os.path.join(dosar, n, "addon.xml")):
					return n
		except OSError:
			pass
	return None


def aduLimba(kodi, dorit, url=_url, dep=None):
	"""Aduce addonul de limba din depozitul oficial in <kodi>/addons, verificat cu sha256; intoarce id-ul sau None."""
	dep = dep or depozit()
	if not dep:
		return None
	info, date = dep
	r = url(info)
	try:
		gasit = cautaInIndex(_bucatiGzip(r), dorit)
	finally:
		r.close()
	if not gasit:
		print("[HdsMediaCenter] limba %s nu e in depozit" % dorit)
		return None
	ida, ver = gasit
	adresa = "%s/%s/%s-%s.zip" % (date, ida, ida, ver)
	r = url(adresa + ".sha256")
	try:
		suma = r.read(512).decode("ascii", "replace").split()[0].lower()
	finally:
		r.close()
	r = url(adresa)
	try:
		continut = r.read(LIMBA_ZIP_MAX + 1)
	finally:
		r.close()
	if len(continut) > LIMBA_ZIP_MAX or hashlib.sha256(continut).hexdigest() != suma:
		print("[HdsMediaCenter] limba %s: arhiva nepotrivita" % ida)
		return None
	addons = os.path.join(kodi, "addons")
	lucru = os.path.join(addons, ".hds-limba-lucru")
	shutil.rmtree(lucru, ignore_errors=True)
	os.makedirs(lucru)
	try:
		with zipfile.ZipFile(io.BytesIO(continut)) as z:
			for n in z.namelist():
				if not n.startswith(ida + "/") or ".." in n.split("/"):
					print("[HdsMediaCenter] limba %s: nume strain in arhiva: %r" % (ida, n))
					return None
			z.extractall(lucru)
		if not os.path.isfile(os.path.join(lucru, ida, "addon.xml")):
			return None
		tinta = os.path.join(addons, ida)
		shutil.rmtree(tinta, ignore_errors=True)
		os.rename(os.path.join(lucru, ida), tinta)
	finally:
		shutil.rmtree(lucru, ignore_errors=True)
	return ida


def scrieLimbaKodi(userdata, ida):
	"""locale.language = ida in guisettings.xml (fisierul omului pastrat; unul stricat nu se atinge). True daca a scris."""
	cale = os.path.join(userdata, "guisettings.xml")
	if os.path.exists(cale):
		try:
			arbore = ET.parse(cale)
		except Exception as e:
			print("[HdsMediaCenter] guisettings.xml necitit, limba neschimbata: %r" % (e,))
			return False
		radacina = arbore.getroot()
	else:
		radacina = ET.Element("settings", {"version": "2"})
		arbore = ET.ElementTree(radacina)
	s = None
	for e in radacina.iter("setting"):
		if e.get("id") == "locale.language":
			s = e
			break
	if s is None:
		s = ET.SubElement(radacina, "setting", {"id": "locale.language"})
	s.text = ida
	s.attrib.pop("default", None)
	if not os.path.isdir(userdata):
		os.makedirs(userdata)
	arbore.write(cale + ".nou", encoding="utf-8", xml_declaration=True)
	os.replace(cale + ".nou", cale)
	return True


def oprireVerificareVersiune(kodi):
	"""Valoarea omului „false” pentru service.xbmc.versioncheck, numai daca omul n-are inca setari pentru el: o
	actualizare a addonului din depozit vine cu implicitul „true” si l-ar porni la loc."""
	d = os.path.join(kodi, "userdata", "addon_data", "service.xbmc.versioncheck")
	cale = os.path.join(d, "settings.xml")
	if os.path.exists(cale):
		return False
	try:
		if not os.path.isdir(d):
			os.makedirs(d)
		with open(cale, "w") as f:
			f.write('<settings version="2">\n    <setting id="versioncheck_enable">false</setting>\n</settings>\n')
		return True
	except (IOError, OSError) as e:
		print("[HdsMediaCenter] versioncheck: %r" % (e,))
		return False


def pregatesteLimba(loc, cod, url=_url, dep=None, sistem=KODI_SISTEM):
	"""Punctul 5 de sus. Intoarce ce a facut: „neschimbat”, „scris <id>” sau „fara-limba” (se reia data viitoare)."""
	kodi = os.path.join(loc, ".kodi")
	userdata = os.path.join(kodi, "userdata")
	semn = os.path.join(userdata, SEMN_LIMBA)
	if not cod or _citeste(semn) == cod:
		return "neschimbat"
	dorit = idLimbaKodi(cod)
	ida = limbaInstalata(kodi, dorit, sistem)
	if ida is None:
		try:
			ida = aduLimba(kodi, dorit, url, dep)
		except Exception as e:
			print("[HdsMediaCenter] limba %s: %r" % (dorit, e))
			ida = None
	if ida is None or not scrieLimbaKodi(userdata, ida):
		return "fara-limba"
	with open(semn, "w") as f:
		f.write(cod + "\n")
	return "scris " + ida


def limbaEnigma2():
	try:
		from Components.Language import language
		return language.getLanguage() or ""
	except Exception:
		return ""


_inCurs = []


def porneste(session, **kwargs):
	from Screens.MessageBox import MessageBox
	if _inCurs:   # OK apasat din nou cat se pregateste limba
		return
	motiv = motivNuPorneste()
	if motiv:
		session.open(MessageBox, _(motiv), type=MessageBox.TYPE_INFO, timeout=15)
		return
	salveazaStarea()
	loc = mediu()
	legaWidevine(loc)
	cere2160()
	oprireVerificareVersiune(os.path.join(loc, ".kodi"))
	cod = limbaEnigma2()
	gata = []

	def lucru():
		try:
			print("[HdsMediaCenter] limba %s: %s" % (cod, pregatesteLimba(loc, cod)))
		except Exception as e:
			print("[HdsMediaCenter] limba: %r" % (e,))
		gata.append(1)

	# limba se aduce intr-un fir (interfata nu se opreste), iesirea vine cand e gata sau dupa LIMBA_MAX_S
	fir = threading.Thread(target=lucru)
	fir.daemon = True
	fir.start()
	t0 = time.time()
	from enigma import eTimer
	ceas = eTimer()

	def verifica():
		if gata or time.time() - t0 > LIMBA_MAX_S:
			ceas.stop()
			del _inCurs[:]
			from Screens.Standby import TryQuitMainloop
			session.open(TryQuitMainloop, retvalue=QUIT_KODI, default_yes=False)
	_inCurs.append(ceas)
	ceas.callback.append(verifica)
	ceas.start(200, False)


def laPornire(reason, session=None, **kwargs):
	"""O singura data dupa intoarcere: de ce n-a mers ultima rulare (fisierul se muta deoparte dupa citire)."""
	if reason != 0 or session is None or not os.path.exists(STARE):
		return
	stare = citesteStarea()
	try:
		os.rename(STARE, STARE + ".citit")
	except OSError:
		pass
	actiune = actiuneDupaRulare(stare)
	if actiune:
		# ca din meniul enigma2 (punctul 4 de sus); default_yes=False: o intrebare despre o inregistrare la care nu
		# raspunde nimeni lasa receptorul pornit
		try:
			from Tools import Notifications
			from Screens.Standby import TryQuitMainloop
			Notifications.AddNotification(TryQuitMainloop, actiune, default_yes=False)
		except Exception as e:
			print("[HdsMediaCenter] oprirea ceruta din Kodi: %r" % (e,))
		return
	m = mesajDupaRulare(stare)
	if not m:
		return
	text = _(m[0]) % m[1] if m[1] is not None else _(m[0])
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddNotification(MessageBox, text, type=MessageBox.TYPE_INFO, timeout=15)
	except Exception as e:
		print("[HdsMediaCenter] mesajul de dupa rulare: %r" % (e,))


def Plugins(**kwargs):
	return [
		PluginDescriptor(name=NUME, description=descriere(), where=PluginDescriptor.WHERE_PLUGINMENU,
			fnc=porneste),
		PluginDescriptor(name=NUME, description=descriere(), where=PluginDescriptor.WHERE_EXTENSIONSMENU,
			fnc=porneste),
		PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=laPornire),
	]
