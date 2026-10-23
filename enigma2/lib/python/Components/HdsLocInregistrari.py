# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsLocInregistrari.py: locul inregistrarilor si discurile conectate. O singura logica pentru ecranul de pe televizor
# (Screens/HdsLocInregistrari.py) si pentru pagina web /stocare (Plugins/Extensions/HdsWebControl/stocare_web.py).
#
# - candidati(): partitiile montate pe care se poate inregistra, din harddiskmanager.getMountedPartitions(), fara
#   radacina, fara ce sta in RAM si fara partajari de retea (statvfs pe o partajare cazuta poate bloca un fir la
#   nesfarsit). Citeste numai /proc/mounts si /sys, deci merge pe firul enigma2. necitite(): stick-urile si discurile
#   USB pe care nu le-a montat nimeni (sistem de fisiere necunoscut sau lipsa).
# - cereStare(): spatiul liber si verificarea de disc adevarat (Components/HdsStocare.verificaDisc) pentru fiecare
#   candidat si pentru locul de acum, pe un fir separat: pe un stick FAT prima citire a spatiului liber poate parcurge
#   toata tabela FAT, secunde intregi. Rezultatul se tine VARSTA_STARE secunde; cel mult un fir de citire deodata.
# - foloseste(): pe un fir separat face dosarul „movie” pe discul ales (niciodata o formatare) si il verifica; setarile
#   se schimba pe firul enigma2, cand rezultatul e cules de un eTimer (tragere, nu impingere: reactor.callFromThread nu
#   trezeste prompt bucla reactorului imaginii, vezi ScreenshotResource din HdsWebControl/plugin.py). Cel mult o
#   pregatire deodata. Setarile schimbate: config.usage.default_path (<disc>/movie/), instantrec_path si timer_path
#   (inapoi la „<default>” daca duceau in alta parte), timeshift_path (<disc>/, numai daca locul lui de acum nu e un
#   disc bun), config.movielist.videodirs si allowed_timeshift_paths (se adauga locul), last_videodir (numai daca nu
#   mai exista). Cand discul ales e cel de pe /media/hdd si default_path e /hdd/movie/ (aceeasi cale prin legatura),
#   setarea ramane cum e: se face numai dosarul.
# - texte(): frazele ecranului si ale paginii, pe intelesul oricui, cu explicatia tehnica separat (se arata mai mic);
#   explicatiile despre loc si cele despre discuri sunt date si separat (pagina web arata discurile intr-un tabel).
#
# Alegerea singura a discului (cand locul inregistrarilor nu e un disc bun):
# - fiecare disc are o identitate (identitate(): UUID-ul sistemului de fisiere din /dev/disk/by-uuid, altfel calea reala
#   a montarii), iar discul folosit ultima data se tine minte in config.usage.hds_disc_inregistrari (setareDisc(),
#   definita la prima folosire; aplicaLoc o pune dupa fiecare pregatire reusita, tineMinte dupa fiecare inregistrare
#   pornita pe un disc bun, oricum ar fi fost ales locul). Numele /media/usb, /media/usb2 tin de ordinea in care apar
#   discurile, identitatea nu. Discul tinut minte cu mai putin de LIBER_MINIM_RETINUT liber nu se ia singur.
# - decizie(): dupa o citire terminata, ce face receptorul singur: nimic (locul e bun), discul tinut minte, singurul disc
#   bun, o intrebare (mai multe discuri, niciunul tinut minte) sau „niciun disc”. La pornirea unui temporizator nu se
#   intreaba (poate nu e nimeni la televizor): se ia discul cu cel mai mult loc liber.
# - alegeInFundal(): aceeasi decizie fara niciun ecran, dintr-un eTimer (citirea si pregatirea pe fire), pentru
#   temporizatoare (RecordTimer.hdsVerificaDisc) si pentru programarea unei inregistrari (RecordTimer.record, prin
#   laProgramare()). Notificarile enigma2 se arata numai cand bara e deasupra (nu in asteptare, nu cu ghidul deschis),
#   deci partea automata nu poate astepta un ecran; ecranul „Locul înregistrărilor” se pune in notificari numai pentru
#   intrebare si pentru „niciun disc”. Dupa o alegere reusita, un mesaj scurt.
# - ecranul (Screens/HdsLocInregistrari.py) face acelasi lucru cand e deschis de la tasta rosie, de la timeshift sau
#   din notificari; din meniu arata discul care va fi folosit, fara „nu am unde”.
#
# Pe firul enigma2, realpath se face numai pe caile discurilor locale (_canonicSigur): pe o partajare de retea cazuta,
# lstat poate bloca firul. Firele de citire si de pregatire folosesc realpath oriunde.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau managerul de discuri, setarile, citirile de
# disc si ceasul lor.

import os
import re
import sys
import threading
import time

# cat timp (secunde) e buna o citire a discurilor; dupa atat, cererea urmatoare porneste o citire noua
VARSTA_STARE = 20
# dupa o citire cazuta (exceptie pe fir), cat timp nu se porneste alt fir: ecranul si pagina intreaba mai departe, dar
# fara un fir nou la fiecare intrebare
VARSTA_ESEC = 5
# pasul eTimer-ului care culege rezultatul pregatirii si aplica setarile pe firul enigma2
PAS_CULEGERE_MS = 200
DOSAR_FILME = "movie"
# locurile in care se monteaza discurile si stick-urile (numele stabile din Components/Harddisk.py, montarile udev, fstab);
# altceva montat de pe un disc (de exemplu fisierele legate intr-un container) nu e un loc de inregistrari
PREFIXE_LOCURI = ("/media/", "/run/media/", "/mnt/", "/autofs/")
# caile pe care realpath e sigur pe firul enigma2 (discuri locale; /hdd e legatura spre /media/hdd), daca tabelul
# montarilor nu arata acolo o partajare de retea
PREFIXE_LOCALE = ("/media/", "/run/media/", "/mnt/", "/hdd/")
STILURI_CALE = ("<default>", "<current>", "<timer>")
# un fisier pe vfat nu poate trece de 4 GB: o inregistrare se opreste acolo (nota se arata numai pe discurile mai mari)
LIMITA_FAT = 4 * 1024 ** 3

# scopul ecranului: de unde a venit omul (tasta rosie, un temporizator care porneste, timeshift, meniul sau o
# inregistrare tocmai programata din ghid, din lista ori din web)
SCOP_MENIU = "meniu"
SCOP_INREGISTRARE = "inregistrare"
SCOP_TEMPORIZATOR = "temporizator"
SCOP_TIMESHIFT = "timeshift"
SCOP_PROGRAMARE = "programare"
SCOPURI = (SCOP_MENIU, SCOP_INREGISTRARE, SCOP_TEMPORIZATOR, SCOP_TIMESHIFT, SCOP_PROGRAMARE)

# actiunile randurilor
ACT_FOLOSESTE = "foloseste"
ACT_ACTUAL = "actual"
ACT_CONTINUA = "continua"
ACT_INCHIDE = "inchide"
# un stick sau un disc pe care receptorul nu il poate citi: randul deschide ecranul de formatare existent
# (Screens/HarddiskSetup.py, cu alegerea sistemului de fisiere si intrebarea lui); aici nu se formateaza nimic
ACT_FORMATEAZA = "formateaza"

# decizia de dupa o citire (decizie())
DEC_BUN = "bun"             # locul e un disc bun: nimic de facut
DEC_DISC = "disc"           # un disc se foloseste singur
DEC_INTREABA = "intreaba"   # mai multe discuri bune, niciunul tinut minte
DEC_NICIUNUL = "niciunul"   # niciun disc bun
# de ce s-a luat discul (in decizie si in pregatire; None = ales de om din lista)
DE_CE_RETINUT = "retinut"   # discul folosit data trecuta
DE_CE_SINGUR = "singur"     # singurul disc bun conectat
DE_CE_LIBER = "liber"       # la un temporizator, cu mai multe discuri: cel cu cel mai mult loc liber
DE_CE_ALES = "ales"         # ales de om la intrebare (ecranul deschis de la tasta rosie, timeshift, programare)

# setarea care tine minte discul inregistrarilor (identitate())
SETARE_DISC = "hds_disc_inregistrari"
# id-ul notificarii cu ecranul „Locul înregistrărilor” (acelasi ca in RecordTimer.hdsVerificaDisc): un singur ecran
ID_ECRAN = "HdsFaraDisc"
ID_MESAJ = "HdsLocAles"
# cat sta pe ecran mesajul de dupa o alegere facuta in fundal (fraza si explicatia cu drumul din meniu)
MESAJ_FUNDAL_S = 10
# pasul si termenul alegerii in fundal
PAS_FUNDAL_MS = 250
TERMEN_FUNDAL_S = 90
FUNDAL_CITIRE = "citire"
FUNDAL_PREGATIRE = "pregatire"
# paza impotriva unei bucle ecran -> „locul e bun” -> tasta rosie -> ecran: de cate ori se poate inchide singur ecranul
# cu „locul e bun” pentru acelasi loc, intr-un interval
INCHIDERI_BUN = 3
INTERVAL_INCHIDERI_S = 10
# discul tinut minte se ia singur numai daca are loc pentru o inregistrare (cam un sfert de ora pe un canal HD); cu mai
# putin, regulile obisnuite (singurul disc bun, intrebarea, la un temporizator cel cu cel mai mult loc liber)
LIBER_MINIM_RETINUT = 1024 ** 3

_DISC_RX = re.compile(r"^(sd[a-z]+|hd[a-z]+|vd[a-z]+|mmcblk[0-9]+|nvme[0-9]+n[0-9]+)")


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele din tabel se traduc la folosire."""
	return text


PRIMA_FRAZA = {
	SCOP_MENIU: N_("Nu am unde să înregistrez."),
	SCOP_INREGISTRARE: N_("Nu am unde să înregistrez."),
	SCOP_TEMPORIZATOR: N_("O înregistrare programată nu poate porni: nu am unde să înregistrez."),
	SCOP_TIMESHIFT: N_("Nu am unde să salvez timeshift-ul."),
	SCOP_PROGRAMARE: N_("Nu am unde să salvez înregistrarea programată."),
}

# dupa „Conectează un stick USB sau un hard disk extern.”: ce se intampla cand omul il conecteaza
DUPA_CONECTARE = {
	SCOP_MENIU: "",
	SCOP_INREGISTRARE: N_("Când îl conectezi, pornesc singur înregistrarea."),
	SCOP_TEMPORIZATOR: N_("Când îl conectezi, înregistrarea programată pornește singură."),
	SCOP_TIMESHIFT: N_("Când îl conectezi, pornesc singur timeshift-ul."),
	SCOP_PROGRAMARE: N_("Conectează-l înainte de ora înregistrării."),
}


def _stocare():
	from Components import HdsStocare
	return HdsStocare


def marime(octeti):
	"""4,3 GB / 734 MB, ca in navigatorul de fisiere."""
	if octeti is None:
		return ""
	from Components import HdsNavigator
	return HdsNavigator.formatSize(octeti)


def _cuPunct(fraza):
	"""Prima litera mare si punct la sfarsit (textMotiv din HdsStocare da o bucata de fraza)."""
	fraza = (fraza or "").strip()
	if not fraza:
		return ""
	fraza = fraza[:1].upper() + fraza[1:]
	return fraza if fraza.endswith(".") else fraza + "."


def _canonic(cale, realpath=None):
	"""Calea reala, fara „/” la sfarsit (/hdd/movie/ si /media/hdd/movie sunt acelasi loc prin legaturi)."""
	if not cale:
		return ""
	try:
		return ((realpath or os.path.realpath)(cale).rstrip("/")) or "/"
	except (OSError, ValueError, TypeError):
		return cale.rstrip("/") or "/"


def _sub(cale, punct):
	"""cale e punct sau in interiorul lui (ambele canonice)."""
	return bool(cale and punct) and (cale == punct or cale.startswith(punct.rstrip("/") + "/"))


def _tabel():
	from Components import HdsNavigator
	return HdsNavigator.readMountTable()


def _deRetea(cale, tabel):
	"""cale sta pe o partajare de retea sau sub autofs, dupa tabelul montarilor (text, fara nicio atingere de disc)."""
	from Components import HdsNavigator
	t = (cale or "").rstrip("/") or "/"
	if t == "/hdd" or t.startswith("/hdd/"):
		t = "/media/hdd" + t[4:]
	if t == "/autofs" or t.startswith("/autofs/"):
		return True
	punct = ""
	for k in tabel:
		if (t == k or t.startswith(k.rstrip("/") + "/")) and len(k) > len(punct):
			punct = k
	sursa, fel = tabel.get(punct, ("", ""))
	return HdsNavigator.isNetworkSource(sursa, fel) or fel == "autofs"


def _canonicSigur(cale, realpath=None, tabel=None):
	"""Ca _canonic, dar realpath numai pe caile discurilor locale; o cale de retea ramane text (fara „/” la sfarsit).
	Pentru firul enigma2."""
	if not cale:
		return ""
	text = cale.rstrip("/") or "/"
	if not (text + "/").startswith(PREFIXE_LOCALE):
		return text
	if _deRetea(text, _tabel() if tabel is None else tabel):
		return text
	return _canonic(cale, realpath)


# ------------------------------------------------------------------ discurile

def discul(dispozitiv):
	"""sda1 -> sda, mmcblk1p1 -> mmcblk1 (discul din /sys/block)."""
	m = _DISC_RX.match(dispozitiv or "")
	return m.group(1) if m else ""


def esteAmovibil(dispozitiv, citeste=None):
	"""/sys/block/<disc>/removable: 1 la stick-uri, 0 la hard diskuri; None daca nu se stie."""
	d = discul(dispozitiv)
	if not d:
		return None
	try:
		if citeste is not None:
			text = citeste("/sys/block/%s/removable" % d)
		else:
			with open("/sys/block/%s/removable" % d) as f:
				text = f.read()
		return text.strip() == "1"
	except (IOError, OSError, ValueError):
		return None


def numeDispozitiv(descriere, dispozitiv, amovibil=None):
	"""Numele aratat omului: modelul citit de pe dispozitiv („Cruzer Blade (sda1)”), sau felul lui („Stick USB (sda1)”,
	„Hard disk (sdb1)”) cand modelul lipseste sau e unul generic, fara inteles pentru om („USB_DRIVE”, „Flash Disk”;
	Components/HdsNavigator.isGenericModel, acelasi fel ca in navigatorul de fisiere)."""
	from Components import HdsNavigator
	model = (descriere or "").split(" (Partition")[0].strip()
	if not model or model.startswith("External Storage") or HdsNavigator.isGenericModel(model):
		model = _("USB Stick") if amovibil else _("Harddisk")
	else:
		# descrierile locurilor fixe din Components/Harddisk.py („Harddisk”, „USB Stick”, „Card”) au traduceri; in
		# modelele citite din /sys, „_” tine locul spatiului
		model = _(model).replace("_", " ")
	if dispozitiv:
		return "%s (%s)" % (model, dispozitiv)
	return model


def _uuidDin(dispozitiv):
	"""UUID-ul sistemului de fisiere de pe /dev/<dispozitiv> (Components/Harddisk.deviceUuid: legaturile udev din
	/dev/disk/by-uuid, fara proces), sau None."""
	if not dispozitiv:
		return None
	try:
		from Components.Harddisk import deviceUuid
	except ImportError:
		return None
	try:
		return deviceUuid(dispozitiv)
	except Exception:
		return None


def identitate(dispozitiv, real, uuid=None):
	"""„uuid:<UUID>” sau, cand UUID-ul nu se stie, „loc:<calea reala a montarii>” (pe receptor /run/media/<eticheta>-sda1).
	Numele stabile (/media/usb, /media/usb2) nu sunt bune aici: tin de ordinea in care apar discurile."""
	u = (uuid or _uuidDin)(dispozitiv) if dispozitiv else None
	if u:
		return "uuid:%s" % u
	return ("loc:%s" % real) if real else ""


def _locRetea(punct):
	"""(id, nume, fel) al unui loc din retea bun pentru inregistrari, montat in punct, sau None."""
	try:
		from Components import HdsStocareRetea
		return HdsStocareRetea.pentruInregistrari(punct)
	except Exception:
		return None


def candidati(hm=None, tabel=None, realpath=None, citeste=None, uuid=None):
	"""[{punct, real, dispozitiv, nume, fel, id}] pentru partitiile montate pe care se poate inregistra. `punct` e
	numele stabil (/media/hdd, /media/usb, ...) din Components/Harddisk.py; se ia o singura data pentru acelasi loc real;
	numai sub PREFIXE_LOCURI. `id` e identitate() (discul tinut minte)."""
	if hm is None:
		from Components.Harddisk import harddiskmanager as hm
	from Components import HdsNavigator
	if tabel is None:
		tabel = HdsNavigator.readMountTable()
	in_memorie = _stocare().FS_IN_MEMORIE
	rez = []
	vazute = set()
	try:
		partitii = list(hm.getMountedPartitions())
	except Exception as eroare:
		print("[HdsLocInregistrari] lista partitiilor: %s" % eroare)
		return rez
	for p in partitii:
		punct = (getattr(p, "mountpoint", None) or "").rstrip("/")
		if not punct:
			continue
		# partajarile de retea ies inainte de realpath (lstat pe o partajare cazuta poate bloca firul enigma2); un loc autofs
		# nemontat inca iese si el (realpath l-ar monta)
		sursa, fel = tabel.get(punct, ("", ""))
		if HdsNavigator.isNetworkSource(sursa, fel):
			# un loc din retea montat din Locuri din retea si trecut de proba de scriere si viteza
			# (Components/HdsStocareRetea.pentruInregistrari, numai text si memorie): fara realpath
			retea = _locRetea(punct)
			if retea is not None and punct not in vazute:
				vazute.add(punct)
				rez.append({"punct": punct, "real": punct, "dispozitiv": "", "nume": retea[1], "fel": fel,
					"id": "retea:" + retea[0]})
			continue
		if fel in in_memorie or fel == "autofs":
			continue
		real = _canonic(punct, realpath)
		if real == "/" or not any((x + "/").startswith(pr) for x in (punct, real) for pr in PREFIXE_LOCURI):
			continue
		sursa, fel = tabel.get(real, (sursa, fel))
		if HdsNavigator.isNetworkSource(sursa, fel) or fel in in_memorie:
			continue
		if real in vazute:
			continue
		vazute.add(real)
		dispozitiv = getattr(p, "device", None) or ""
		amovibil = getattr(p, "removable", None)
		if amovibil is None and dispozitiv:
			amovibil = esteAmovibil(dispozitiv, citeste)
		rez.append({
			"punct": punct,
			"real": real,
			"dispozitiv": dispozitiv,
			"nume": numeDispozitiv(getattr(p, "description", ""), dispozitiv, amovibil),
			"fel": fel,
			"id": identitate(dispozitiv, real, uuid),
		})
	return rez


def necitite(hm=None, fel_fs=None):
	"""[{dispozitiv, nume}] pentru partitiile USB pe care nu le-a montat nimeni si nu mai sunt in asteptare (udev nu
	cunoaste sistemul lor de fisiere, iar montarea proprie din Components/Harddisk.py a renuntat)."""
	if hm is None:
		from Components.Harddisk import harddiskmanager as hm
	if fel_fs is None:
		from Components.Harddisk import deviceFsType as fel_fs
	try:
		from Components.Harddisk import NOT_MOUNTED_FS
	except ImportError:
		NOT_MOUNTED_FS = ("swap",)
	rez = []
	asteptare = getattr(hm, "pending", None) or {}
	ocupate = set(getattr(hm, "busy", None) or {}) | set(getattr(hm, "mount_timers", None) or {})
	for dispozitiv in sorted(asteptare.keys()):
		p = asteptare[dispozitiv]
		if not getattr(p, "usb", False) or getattr(p, "has_partitions", False) or getattr(p, "is_cdrom", False):
			continue
		if dispozitiv in ocupate:
			continue
		try:
			fel = fel_fs(dispozitiv)
		except Exception:
			fel = None
		if fel in NOT_MOUNTED_FS:
			continue
		rez.append({
			"dispozitiv": dispozitiv,
			"nume": numeDispozitiv(getattr(p, "description", ""), dispozitiv, getattr(p, "removable", None)),
			"fel": fel or "",
		})
	return rez


# ------------------------------------------------------------------ locul de acum

def locInregistrari(config=None, preferat=None, poateScrie=None):
	"""Dosarul in care ar merge o inregistrare pornita acum cu tasta rosie, dupa aceeasi regula ca
	InfoBarInstantRecord.instantRecord: locul inregistrarilor imediate, sau locul implicit daca acela lipseste."""
	if config is None:
		from Components.config import config
	if preferat is None:
		from Components.UsageConfig import preferredPath as preferat
	cale = preferat(config.usage.instantrec_path.value)
	if not cale or not (poateScrie or _poateScrie)(cale):
		cale = config.usage.default_path.value
	return cale


def locTimeshift(config=None):
	if config is None:
		from Components.config import config
	return config.usage.timeshift_path.value


def locTemporizator(dirname=None, config=None, poateScrie=None):
	"""Unde ar merge acum o inregistrare programata: dosarul ei, daca se poate scrie in el, altfel locul implicit (ca
	RecordTimerEntry.calculateFilename)."""
	if dirname and (poateScrie or _poateScrie)(dirname):
		return dirname
	if config is None:
		from Components.config import config
	return config.usage.default_path.value


def _modulSetari():
	"""Components.config, daca e incarcat. Enigma2 il incarca la pornire, inaintea oricarui ecran; fara el (probele de
	pe PC) nu se incearca un import la fiecare chemare: texte() ruleaza la fiecare bataie a ceasului ecranului, iar un
	import cazut cauta din nou pe toate caile."""
	return sys.modules.get("Components.config")


def setareDisc(config=None):
	"""config.usage.hds_disc_inregistrari: identitatea discului folosit ultima data pentru inregistrari. Se defineste
	aici, la prima folosire (ConfigSubsection incarca atunci valoarea salvata); None cand setarile nu se pot folosi
	(probele de pe PC fara Components.config)."""
	if config is None:
		config = getattr(_modulSetari(), "config", None)
		if config is None:
			return None
	u = getattr(config, "usage", None)
	if u is None:
		return None
	try:
		return getattr(u, SETARE_DISC)
	except (AttributeError, KeyError):
		pass
	ConfigText = getattr(_modulSetari(), "ConfigText", None)
	if ConfigText is None:
		return None
	try:
		setattr(u, SETARE_DISC, ConfigText(default=""))
		return getattr(u, SETARE_DISC)
	except Exception as eroare:
		print("[HdsLocInregistrari] setarea discului: %s" % eroare)
		return None


def discRetinut(config=None):
	"""Identitatea discului tinut minte, sau „”."""
	s = setareDisc(config)
	try:
		return (s.value or "") if s is not None else ""
	except Exception:
		return ""


def _poateScrie(cale):
	try:
		return os.path.isdir(cale) and os.access(cale, os.W_OK)
	except (OSError, TypeError, ValueError):
		return False


# ------------------------------------------------------------------ citirea (pe un fir)

def _spatiu(cale, statvfs=None):
	statvfs = statvfs or getattr(os, "statvfs", None)
	try:
		s = statvfs(cale)
		return int(s.f_bavail) * int(s.f_frsize), int(s.f_blocks) * int(s.f_frsize)
	except Exception:
		return None, None


def citesteStare(cand, cale_loc, verifica=None, statvfs=None, isdir=None, realpath=None):
	"""Citirea propriu-zisa (atinge discurile, deci numai pe un fir): {loc, discuri}. `cand` e lista din candidati().
	loc["punct"]: discul pe care se salveaza acum (locul e bun); loc["pe_disc"]: discul pe care duce locul, si cand locul
	nu e bun (de exemplu /hdd/movie/ pe stick-ul de pe /media/hdd, fara dosarul movie)."""
	verifica = verifica or _stocare().verificaDisc
	isdir = isdir or os.path.isdir
	real_loc = _canonic(cale_loc, realpath)
	bun, motiv = verifica(cale_loc)
	loc = {"cale": cale_loc, "bun": bool(bun), "motiv": motiv, "liber": None, "total": None, "punct": None,
		"pe_disc": None}
	if bun:
		loc["liber"], loc["total"] = _spatiu(cale_loc, statvfs)
	discuri = []
	for c in cand:
		d = dict(c)
		b, m = verifica(c["punct"] + "/")
		d["bun"], d["motiv"] = bool(b), m
		d["liber"], d["total"] = _spatiu(c["punct"], statvfs) if b else (None, None)
		try:
			d["are_movie"] = bool(isdir(c["punct"] + "/" + DOSAR_FILME))
		except (OSError, TypeError, ValueError):
			d["are_movie"] = False
		pe_el = _sub(real_loc, c.get("real") or _canonic(c["punct"], realpath))
		d["folosit"] = bool(bun) and pe_el
		if d["folosit"]:
			loc["punct"] = c["punct"]
		if pe_el and loc["pe_disc"] is None:
			loc["pe_disc"] = c["punct"]
		discuri.append(d)
	return {"loc": loc, "discuri": discuri}


_zavor = threading.Lock()
_citire = {"rez": None, "cheie": None, "timp": 0.0, "in_lucru": False, "esec": 0.0}


def _citesteSiTine(cheie, cand, cale_loc, citeste):
	try:
		rez = citeste(cand, cale_loc)
	except Exception as eroare:
		print("[HdsLocInregistrari] citirea discurilor: %s" % eroare)
		rez = None
	with _zavor:
		if rez is not None:
			_citire["rez"] = rez
			_citire["cheie"] = cheie
			_citire["timp"] = time.time()
			_citire["esec"] = 0.0
		else:
			_citire["esec"] = time.time()
		_citire["in_lucru"] = False


def _pornesteFir(tinta, *argumente):
	fir = threading.Thread(target=tinta, args=argumente)
	fir.daemon = True
	fir.start()


def _cheie(cand, cale_loc):
	return (cale_loc, tuple((c["punct"], c.get("dispozitiv")) for c in cand))


def cereStare(cand, cale_loc, din_nou=False, acum=None, citeste=None, porneste=None):
	"""(rezultat, se_citeste): ultima citire (None daca nu e una pentru aceleasi discuri si acelasi loc) si daca o
	citire e in curs. Porneste una noua pe un fir cand cea tinuta e mai veche de VARSTA_STARE, e pentru alte discuri
	sau se cere din_nou. Dupa o citire cazuta, VARSTA_ESEC secunde nu porneste alt fir (decat la din_nou), dar spune
	mai departe ca se citeste, ca ecranul si pagina sa intrebe din nou. Nu atinge discurile pe firul care o cheama."""
	acum = time.time() if acum is None else acum
	cheie = _cheie(cand, cale_loc)
	with _zavor:
		rez = _citire["rez"] if _citire["cheie"] == cheie else None
		vechi = rez is None or din_nou or acum - _citire["timp"] >= VARSTA_STARE
		asteapta = not din_nou and 0 <= acum - _citire["esec"] < VARSTA_ESEC
		pornesc = vechi and not asteapta and not _citire["in_lucru"]
		if pornesc:
			_citire["in_lucru"] = True
		in_lucru = _citire["in_lucru"] or (vechi and asteapta)
	if pornesc:
		try:
			(porneste or _pornesteFir)(_citesteSiTine, cheie, list(cand), cale_loc, citeste or citesteStare)
		except Exception as eroare:
			print("[HdsLocInregistrari] firul de citire nu a pornit: %s" % eroare)
			with _zavor:
				_citire["in_lucru"] = False
			in_lucru = False
	return rez, in_lucru


def uitaCitirea():
	"""Dupa o schimbare (disc ales, disc pus sau scos): cererea urmatoare citeste din nou."""
	with _zavor:
		_citire["rez"] = None
		_citire["cheie"] = None
		_citire["timp"] = 0.0
		_citire["esec"] = 0.0


# ------------------------------------------------------------------ pregatirea discului ales (pe un fir)

def motivEroare(eroare):
	"""Motivul unei erori de scriere, dupa errno: „fisier” (movie exista, dar nu e dosar), „plin”, „numai_citire”
	(stick protejat la scriere sau montat numai pentru citire dupa erori), altfel „scriere”."""
	import errno
	return {
		errno.EEXIST: "fisier",
		errno.ENOTDIR: "fisier",
		errno.ENOSPC: "plin",
		errno.EROFS: "numai_citire",
	}.get(getattr(eroare, "errno", None), "scriere")


def pregatesteDisc(punct, cale_timeshift, ultimul_dosar, verifica=None, isdir=None, mkdir=None):
	"""Face dosarul movie pe discul ales, daca lipseste (fara sa stearga sau sa formateze nimic), si il verifica.
	Intoarce {bun, motiv, dosar, facut, timeshift_bun, ultimul_bun, eroare}."""
	verifica = verifica or _stocare().verificaDisc
	isdir = isdir or os.path.isdir
	mkdir = mkdir or os.mkdir
	dosar = punct.rstrip("/") + "/" + DOSAR_FILME
	rez = {"dosar": dosar + "/", "facut": False, "bun": False, "motiv": "", "eroare": "", "timeshift_bun": False,
		"ultimul_bun": False}
	bun, motiv = verifica(punct.rstrip("/") + "/")
	if not bun:
		rez["motiv"] = motiv
		return rez
	try:
		if not isdir(dosar):
			mkdir(dosar, 0o755)
			rez["facut"] = True
	except (OSError, IOError) as eroare:
		rez["motiv"] = motivEroare(eroare)
		# textul tehnic (in engleza) merge numai in jurnal; omul vede motivul (textMotivDisc)
		rez["eroare"] = str(eroare)[:160]
		print("[HdsLocInregistrari] %s: %s" % (dosar, eroare))
		return rez
	bun, motiv = verifica(dosar + "/")
	rez["bun"], rez["motiv"] = bool(bun), motiv
	if cale_timeshift:
		rez["timeshift_bun"] = bool(verifica(cale_timeshift)[0])
	try:
		rez["ultimul_bun"] = bool(ultimul_dosar) and bool(isdir(ultimul_dosar))
	except (OSError, TypeError, ValueError):
		rez["ultimul_bun"] = False
	return rez


def _adaugaLoc(element, cale, realpath=None, tabel=None):
	"""Adauga cale in lista unui ConfigLocations daca nu are deja acelasi loc (setValue pastreaza si locurile ascunse,
	ale discurilor scoase acum)."""
	valoare = list(element.value)
	real = _canonicSigur(cale, realpath, tabel)
	if any(_canonicSigur(v, realpath, tabel) == real for v in valoare):
		return False
	element.value = valoare + [cale]
	element.save()
	return True


def aplicaLoc(punct, pregatire, scop=SCOP_MENIU, config=None, configfile=None, realpath=None, tabel=None, ident=None):
	"""Pe firul enigma2: setarile pentru discul ales, dupa pregatirea lui. Intoarce lista setarilor schimbate; in
	pregatire["dosar_setare"] pune dosarul inregistrarilor asa cum e scris in setare (/hdd/movie/ ramane /hdd/movie/),
	ca textele sa scrie calea la fel peste tot. `ident` (identitate()) devine discul tinut minte."""
	if config is None:
		from Components.config import config
	if configfile is None:
		from Components.config import configfile
	if tabel is None:
		tabel = _tabel()

	def locul(cale):
		# pe firul enigma2 numai realpath sigur: caile de retea din setari raman text
		return _canonicSigur(cale, realpath, tabel)
	u = config.usage
	dosar = pregatire["dosar"]
	real_dosar = locul(dosar)
	real_punct = locul(punct)
	schimbate = []
	if locul(u.default_path.value) != real_dosar:
		u.default_path.value = dosar
		u.default_path.save()
		schimbate.append("default_path")
	for nume in ("instantrec_path", "timer_path"):
		element = getattr(u, nume)
		v = element.value
		if v == "<default>":
			continue
		if v not in STILURI_CALE and _sub(locul(v), real_punct):
			continue
		element.value = "<default>"
		element.save()
		schimbate.append(nume)
	# timeshift-ul se muta pe discul ales numai daca locul lui de acum nu e un disc bun (sau daca de acolo a venit omul)
	if scop == SCOP_TIMESHIFT or not pregatire.get("timeshift_bun"):
		loc_ts = punct.rstrip("/") + "/"
		if locul(u.timeshift_path.value) != real_punct:
			u.timeshift_path.value = loc_ts
			u.timeshift_path.save()
			schimbate.append("timeshift_path")
		if _adaugaLoc(u.allowed_timeshift_paths, loc_ts, realpath, tabel):
			schimbate.append("allowed_timeshift_paths")
	try:
		ml = config.movielist
		if _adaugaLoc(ml.videodirs, u.default_path.value, realpath, tabel):
			schimbate.append("videodirs")
		if not pregatire.get("ultimul_bun") and locul(ml.last_videodir.value) != real_dosar:
			ml.last_videodir.value = u.default_path.value
			ml.last_videodir.save()
			schimbate.append("last_videodir")
	except (AttributeError, KeyError):
		# config.movielist exista numai dupa incarcarea lui Screens/MovieSelection.py (ConfigSubsection da KeyError
		# pentru o cheie lipsa)
		pass
	if ident:
		s = setareDisc(config)
		if s is not None and s.value != ident:
			s.value = ident
			s.save()
			schimbate.append(SETARE_DISC)
	if schimbate:
		configfile.save()
	pregatire["dosar_setare"] = u.default_path.value
	print("[HdsLocInregistrari] recordings on %s (%s), changed: %s" % (punct, dosar, ", ".join(schimbate) or "-"))
	return schimbate


_lucru = {"stare": None, "punct": None, "nume": None, "scop": SCOP_MENIU, "rez": None, "aplicat": False,
	"schimbate": [], "timp": 0.0, "id": "", "de_ce": None}
_ceasuri = []       # eTimer-ul care culege pregatirea (tinut aici, altfel GC-ul l-ar culege)
LUCRU_GATA = "gata"
LUCRU_IN_LUCRU = "in_lucru"
LUCRU_EROARE = "eroare"


def _pregatesteSiTine(punct, cale_timeshift, ultimul_dosar, pregateste):
	try:
		rez = pregateste(punct, cale_timeshift, ultimul_dosar)
	except Exception as eroare:
		print("[HdsLocInregistrari] pregatirea lui %s: %s" % (punct, eroare))
		rez = {"bun": False, "motiv": "scriere", "eroare": str(eroare)[:160], "dosar": punct.rstrip("/") + "/movie/"}
	with _zavor:
		_lucru["rez"] = rez
		_lucru["stare"] = LUCRU_GATA if rez.get("bun") else LUCRU_EROARE


def _ceasEnigma(functie):
	from enigma import eTimer
	ceas = eTimer()
	ceas.callback.append(functie)
	return ceas


def foloseste(punct, cand, scop=SCOP_MENIU, config=None, pregateste=None, porneste=None, ceas=None, de_ce=None):
	"""Porneste pregatirea discului `punct` (unul din candidati()). (True, "") daca a pornit, altfel (False, motivul
	pe intelesul oricui). Pe firul enigma2. `de_ce` (DE_CE_*) spune textelor de dupa daca discul l-a luat receptorul
	singur sau l-a ales omul la intrebare (None: ales din meniu sau din pagina web)."""
	alesi = [c for c in cand if c["punct"] == punct]
	if not alesi:
		return False, _("Discul ales nu mai este conectat. Alege din nou.")
	if config is None:
		from Components.config import config
	try:
		ultimul = config.movielist.last_videodir.value
	except (AttributeError, KeyError):
		ultimul = ""
	with _zavor:
		if _lucru["stare"] == LUCRU_IN_LUCRU:
			return False, _("Se pregătește deja un disc. Așteaptă puțin.")
		_lucru.update({"stare": LUCRU_IN_LUCRU, "punct": punct, "nume": alesi[0]["nume"], "scop": scop, "rez": None,
			"aplicat": False, "schimbate": [], "timp": time.time(), "id": alesi[0].get("id") or "", "de_ce": de_ce})
	try:
		(porneste or _pornesteFir)(_pregatesteSiTine, punct, config.usage.timeshift_path.value, ultimul,
			pregateste or pregatesteDisc)
	except Exception as eroare:
		print("[HdsLocInregistrari] firul de pregatire nu a pornit: %s" % eroare)
		with _zavor:
			_lucru["stare"] = LUCRU_EROARE
			_lucru["rez"] = {"bun": False, "motiv": "scriere", "eroare": str(eroare)[:160], "dosar": ""}
		return False, _("Nu am putut pregăti discul. Încearcă din nou.")
	# culegerea: un eTimer pe firul enigma2, pana cand pregatirea e gata (merge si dupa inchiderea ecranului)
	try:
		c = (ceas or _ceasEnigma)(culege)
		del _ceasuri[:]
		_ceasuri.append(c)
		c.start(PAS_CULEGERE_MS, False)
	except Exception as eroare:
		print("[HdsLocInregistrari] ceasul culegerii: %s" % eroare)
	return True, ""


def culege(config=None, configfile=None, realpath=None):
	"""Pe firul enigma2: daca pregatirea s-a terminat si setarile nu sunt inca puse, le pune (o singura data).
	Intoarce starea pregatirii (dictionar nou) sau None daca nu s-a cerut niciuna."""
	with _zavor:
		if _lucru["stare"] is None:
			return None
		stare = _lucru["stare"]
		gata = stare == LUCRU_GATA and not _lucru["aplicat"]
		if gata:
			_lucru["aplicat"] = True
		punct, rez, scop, ident = _lucru["punct"], _lucru["rez"], _lucru["scop"], _lucru.get("id")
	if stare != LUCRU_IN_LUCRU:
		# numai oprit: culege() poate rula chiar din acest eTimer, iar obiectul lui nu se sterge in timpul chemarii;
		# se inlocuieste la pregatirea urmatoare
		for c in _ceasuri:
			try:
				c.stop()
			except Exception:
				pass
	if gata:
		try:
			schimbate = aplicaLoc(punct, rez, scop, config, configfile, realpath, ident=ident)
		except Exception as eroare:
			print("[HdsLocInregistrari] setarile pentru %s: %s" % (punct, eroare))
			with _zavor:
				_lucru["stare"] = LUCRU_EROARE
				rez = dict(rez or {})
				rez["eroare"] = str(eroare)[:160]
				_lucru["rez"] = rez
			schimbate = []
		with _zavor:
			_lucru["schimbate"] = schimbate
		uitaCitirea()
	return stareLucru()


def stareLucru():
	"""{stare, punct, nume, scop, rez, aplicat, schimbate, id, de_ce} al ultimei pregatiri, sau None."""
	with _zavor:
		if _lucru["stare"] is None:
			return None
		d = dict(_lucru)
		d["rez"] = dict(_lucru["rez"]) if _lucru["rez"] else None
		d["schimbate"] = list(_lucru["schimbate"])
		return d


def uitaLucrul():
	"""Pentru probe."""
	with _zavor:
		_lucru.update({"stare": None, "punct": None, "nume": None, "scop": SCOP_MENIU, "rez": None, "aplicat": False,
			"schimbate": [], "timp": 0.0, "id": "", "de_ce": None})
	del _ceasuri[:]


# ------------------------------------------------------------------ textele

def textMotivDisc(motiv):
	"""De ce nu se poate folosi un disc conectat, pe scurt."""
	return {
		"ram": _("este în memoria RAM a receptorului"),
		"intern": _("este memoria internă a receptorului"),
		"mic": _("are mai puțin de 64 MB"),
		"scriere": _("pe el nu se poate scrie"),
		"lipsa": _("nu mai răspunde"),
		"fisier": _("pe el există un fișier movie, care nu este dosar"),
		"plin": _("este plin"),
		"numai_citire": _("pe el se poate numai citi, nu și scrie"),
	}.get(motiv, _("nu se poate folosi"))


def drumMeniu():
	"""Unde se schimba locul pe televizor, cu numele meniurilor asa cum le arata el (traduse)."""
	return _("Poți alege alt loc din Meniu, „%s”, „%s”, „%s”.") % (_("Settings"), _("Recording & Storage Setup"),
		_("Locul înregistrărilor"))


# unde se salveaza, dupa o alegere facuta de receptor sau la intrebare (textAutomat)
TEXT_SALVARE = {
	SCOP_TIMESHIFT: N_("Timeshift-ul se salvează pe „%s”."),
	SCOP_TEMPORIZATOR: N_("Înregistrarea programată se salvează pe „%s”."),
	SCOP_PROGRAMARE: N_("Înregistrările programate se salvează pe „%s”."),
}
DE_CE_TEXT = {
	DE_CE_RETINUT: N_("Este discul folosit data trecută."),
	DE_CE_SINGUR: N_("Este singurul stick sau disc conectat."),
	DE_CE_LIBER: N_("Dintre discurile conectate, are cel mai mult loc liber."),
	DE_CE_ALES: N_("Țin minte alegerea."),
}


def textAutomat(lucru):
	"""(text, detaliu) dupa o pregatire reusita pornita de receptor singur sau dupa intrebare (lucru["de_ce"]): unde se
	salveaza, de ce acolo, ce s-a facut pe disc si unde se schimba locul."""
	nume = lucru.get("nume") or lucru.get("punct") or ""
	rez = lucru.get("rez") or {}
	text = _(TEXT_SALVARE.get(lucru.get("scop"), N_("Înregistrările se salvează pe „%s”."))) % nume
	parti = []
	de_ce = DE_CE_TEXT.get(lucru.get("de_ce"))
	if de_ce:
		parti.append(_(de_ce))
	if rez.get("facut"):
		parti.append(_("Am făcut pe el dosarul movie."))
	parti.append(drumMeniu())
	return text, " ".join(parti)


def textLucru(lucru):
	"""(text, detaliu) pentru starea unei pregatiri (ecranul si pagina web). La o eroare, detaliul e motivul pe
	intelesul oricui; textul tehnic al erorii ramane in jurnal (pregatesteDisc). O pregatire pornita de receptor
	singur sau dupa intrebare (de_ce), in afara meniului, se incheie cu textAutomat."""
	if not lucru:
		return "", ""
	nume = lucru.get("nume") or lucru.get("punct") or ""
	rez = lucru.get("rez") or {}
	if lucru["stare"] == LUCRU_IN_LUCRU:
		return _("Se pregătește „%s”...") % nume, ""
	if lucru["stare"] == LUCRU_GATA and lucru.get("aplicat"):
		if lucru.get("de_ce") and lucru.get("scop") != SCOP_MENIU:
			return textAutomat(lucru)
		# calea asa cum e scrisa in setare, la fel ca in texte() (/hdd/movie/, nu /media/hdd/movie/)
		detaliu = _("Dosarul înregistrărilor: %s.") % (rez.get("dosar_setare") or rez.get("dosar", ""))
		if "timeshift_path" in (lucru.get("schimbate") or []):
			detaliu += " " + _("Tot aici se salvează și timeshift-ul.")
		return _("Gata. Înregistrările se salvează acum pe „%s”.") % nume, detaliu
	if lucru["stare"] == LUCRU_GATA:
		return _("Se pregătește „%s”...") % nume, ""
	detaliu = _cuPunct(textMotivDisc(rez["motiv"])) if rez.get("motiv") else ""
	return _("Nu am putut pregăti „%s” pentru înregistrări.") % nume, detaliu


def disculLocului(cale, cand, realpath=None, tabel=None):
	"""(punct, radacina): punctul discului din `cand` pe care duce `cale`, si cand dosarul inca nu exista (/hdd/movie/
	pe stick-ul de pe /media/hdd), si daca `cale` e chiar radacina lui; (None, False) daca locul nu e pe niciunul. Nu
	atinge discurile: realpath numai pe caile locale."""
	if not cale:
		return None, False
	real = _canonicSigur(cale, realpath, tabel)
	for c in cand:
		r = c.get("real") or c["punct"]
		if _sub(real, r):
			return c["punct"], real == r.rstrip("/")
	return None, False


# ------------------------------------------------------------------ decizia

def _liber(d):
	return d.get("liber") or 0


def decizie(stare, retinut="", scop=SCOP_INREGISTRARE):
	"""Ce face receptorul singur dupa o citire terminata (cereStare): {fel, disc, discuri, de_ce}.
	- DEC_BUN: locul e un disc bun;
	- DEC_DISC: `disc` se foloseste singur: cel tinut minte (DE_CE_RETINUT), singurul disc bun (DE_CE_SINGUR) sau, la
	  pornirea unui temporizator cu mai multe discuri si niciunul tinut minte, cel cu cel mai mult loc liber
	  (DE_CE_LIBER: poate nu e nimeni la televizor sa raspunda);
	- DEC_INTREABA: `discuri`, cele bune, intai cel cu cel mai mult loc liber;
	- DEC_NICIUNUL.
	None daca nu e nicio citire."""
	if not stare:
		return None
	loc = stare.get("loc") or {}
	rez = {"fel": DEC_NICIUNUL, "disc": None, "discuri": [], "de_ce": None}
	if loc.get("bun"):
		rez["fel"] = DEC_BUN
		return rez
	buni = [d for d in (stare.get("discuri") or []) if d.get("bun")]
	if retinut:
		tinut = [d for d in buni if d.get("id") == retinut and (d.get("liber") is None or
			d["liber"] >= LIBER_MINIM_RETINUT)]
		if tinut:
			rez.update(fel=DEC_DISC, disc=tinut[0], de_ce=DE_CE_RETINUT)
			return rez
	# un loc din retea (id "retea:...") se ia singur numai cand e cel tinut minte (ales anume de om): altfel un NAS cu
	# mult loc liber ar castiga mereu, si cand serverul e stins la ora inregistrarii; la intrebare apare dupa discuri
	locale = [d for d in buni if not str(d.get("id") or "").startswith("retea:")]
	if len(locale) == 1:
		rez.update(fel=DEC_DISC, disc=locale[0], de_ce=DE_CE_SINGUR)
	elif len(locale) > 1:
		# sortarea pastreaza ordinea discurilor (hdd, usb, ...) la loc liber egal
		dupa_loc = sorted(locale, key=_liber, reverse=True)
		if scop == SCOP_TEMPORIZATOR:
			rez.update(fel=DEC_DISC, disc=dupa_loc[0], de_ce=DE_CE_LIBER)
		else:
			rez.update(fel=DEC_INTREABA, discuri=dupa_loc + [d for d in buni if d not in locale])
	elif buni and scop != SCOP_TEMPORIZATOR:
		rez.update(fel=DEC_INTREABA, discuri=sorted(buni, key=_liber, reverse=True))
	return rez


_inchideri = {}


def inchidereBunPermisa(cale, acum=None):
	"""Ecranul deschis pentru un loc rau afla la citire ca locul e bun (un disc pus chiar atunci) si se inchide singur,
	iar cine l-a deschis porneste din nou. Daca asta se repeta de INCHIDERI_BUN ori in INTERVAL_INCHIDERI_S secunde
	pentru acelasi loc (verificarea de pe firul enigma2 nu se potriveste cu cea de pe fir), ecranul ramane deschis."""
	acum = time.time() if acum is None else acum
	recente = [t for t in _inchideri.get(cale, []) if 0 <= acum - t < INTERVAL_INCHIDERI_S]
	if len(recente) >= INCHIDERI_BUN:
		_inchideri[cale] = recente
		print("[HdsLocInregistrari] %s: the screen found the place good %d times in %d s, it stays open" % (cale,
			len(recente), INTERVAL_INCHIDERI_S))
		return False
	recente.append(acum)
	_inchideri[cale] = recente
	return True


# ------------------------------------------------------------------ ce arata ecranul si pagina

def texte(stare, cand, necit, scop=SCOP_MENIU, cale=None, motiv=None, se_citeste=False, folosit_punct=None,
		realpath=None, retinut=None, automat_oprit=False):
	"""Ce arata ecranul si pagina: {titlu, text, detaliu, detaliu_loc, randuri: [{text, actiune, punct, detaliu}], bun,
	automat, intrebare, cauta}. `cauta`: locul nu se stie inca (se citesc discurile). `stare` e rezultatul lui cereStare (sau None cat timp se citeste), `cand` lista din
	candidati(), `necit` din necitite(); `cale` si `motiv` vin de la cine a deschis ecranul (tasta rosie: dosarul si
	motivul din verificaDisc). `folosit_punct`: discul ales chiar acum (ecranul, dupa „Gata”), aratat ca loc de acum cat
	se citeste din nou. `detaliu_loc` are numai explicatiile despre loc (pagina web arata starea discurilor in tabelul
	ei). `retinut`: identitatea discului tinut minte (None: din setare).
	Cand locul nu e bun, textele urmeaza decizie(). Din meniu (si in pagina web, si in lista inregistrarilor programate):
	discul care va fi folosit singur la prima inregistrare („automat”, cu „bun” True: nu e nimic de reparat) sau
	intrebarea; „nu am unde” numai cand nu e niciun disc bun. In celelalte scopuri ecranul lucreaza singur
	(Screens/HdsLocInregistrari.py): pana la o citire noua arata cautarea (`stare` None), apoi pregatirea, intrebarea sau
	„niciun disc”. `automat_oprit`: pregatirea automata a cazut, deci se arata toate discurile bune de ales."""
	if scop not in SCOPURI:
		scop = SCOP_MENIU
	if retinut is None:
		retinut = discRetinut()
	singur = scop != SCOP_MENIU
	loc = (stare or {}).get("loc") or {}
	discuri = (stare or {}).get("discuri")
	if cale is None:
		cale = loc.get("cale") or ""
	citit = stare is not None and loc.get("cale") == cale
	if citit:
		# citirea de pe fir e mai noua decat ce a stiut cine a deschis ecranul
		motiv = loc.get("motiv") or ""
	if discuri is None:
		# citirea nu e gata: discurile cunoscute, fara spatiu si fara verificare
		discuri = [dict(c, bun=None, motiv="", liber=None, total=None, are_movie=None,
			folosit=bool(folosit_punct) and c["punct"] == folosit_punct) for c in cand]
	rai = [d for d in discuri if d.get("bun") is False]
	# nu se stie inca: meniul inainte de prima citire (motiv None); ecranul care lucreaza singur, pana la o citire
	# terminata a locului lui (altfel ar arata „nu am unde” o clipa, apoi ar pregati discul)
	necunoscut = motiv is None or (singur and not citit)
	loc_bun = not necunoscut and motiv == ""
	dec = None
	if not necunoscut and not loc_bun:
		dec = decizie({"loc": {"bun": False}, "discuri": discuri}, retinut, scop)
	automat = None
	intrebare = False
	bun = loc_bun
	randuri = []
	detalii_loc = []
	detalii_disc = []
	titlu = _("Locul înregistrărilor")
	if necunoscut:
		text = _("Caut un stick USB sau un hard disk...") if singur else _("Se citesc discurile...")
	elif loc_bun:
		folosit = [d for d in discuri if d.get("folosit")]
		if scop == SCOP_TIMESHIFT:
			# de la timeshift, locul e cel al timeshift-ului (config.usage.timeshift_path)
			if folosit:
				text = _("Timeshift-ul se salvează pe „%s”.") % folosit[0]["nume"]
			else:
				text = _("Timeshift-ul se salvează în %s.") % cale
			detalii_loc.append(_("Dosarul timeshift-ului: %s.") % cale)
		else:
			if folosit:
				text = _("Înregistrările se salvează pe „%s”.") % folosit[0]["nume"]
			else:
				text = _("Înregistrările se salvează în %s.") % cale
			detalii_loc.append(_("Dosarul înregistrărilor: %s.") % cale)
		if loc.get("liber") is not None:
			detalii_loc.append(_("Liber: %s din %s.") % (marime(loc["liber"]), marime(loc["total"])))
	elif dec["fel"] == DEC_DISC and not automat_oprit:
		d = dec["disc"]
		automat = d["punct"]
		if singur:
			# ecranul porneste chiar acum pregatirea; textLucru o arata pana e gata
			text = _("Se pregătește „%s”...") % d["nume"]
		else:
			bun = True
			text = _("Înregistrările se vor salva pe „%s”.") % d["nume"]
			if d.get("are_movie"):
				detalii_loc.append(_("La prima înregistrare îl aleg singur."))
			else:
				detalii_loc.append(_("La prima înregistrare îl aleg singur și fac pe el dosarul movie."))
			if d.get("liber") is not None:
				detalii_loc.append(_("Liber: %s din %s.") % (marime(d["liber"]), marime(d["total"])))
	elif dec["fel"] in (DEC_INTREABA, DEC_DISC):
		intrebare = True
		if dec["fel"] == DEC_DISC:
			# pregatirea automata a cazut: toate discurile bune, de ales de om
			text = _("Nu am putut pregăti „%s” pentru înregistrări.") % dec["disc"]["nume"]
			detalii_loc.append(_("Alege alt disc sau încearcă din nou."))
		else:
			if scop == SCOP_TIMESHIFT:
				text = _("Am găsit mai multe discuri. Pe care salvez timeshift-ul?")
			else:
				text = _("Am găsit mai multe discuri. Pe care salvez înregistrările?")
			# drumul din meniu il spune mesajul de dupa alegere (textAutomat): aici e loc pentru discurile rele
			detalii_loc.append(_("Țin minte discul ales."))
	else:
		# niciun disc bun: „nu am unde”, cu ce e de facut
		if rai:
			a_doua = _("Pe discurile conectate nu se poate înregistra.")
		elif necit:
			a_doua = _("„%s” este conectat, dar receptorul nu îl poate citi.") % necit[0]["nume"]
		else:
			a_doua = _("Nu am găsit niciun stick USB sau hard disk.")
		text = _(PRIMA_FRAZA[scop]) + " " + a_doua
		detalii_loc.append(_("Conectează un stick USB sau un hard disk extern."))
		if DUPA_CONECTARE.get(scop):
			detalii_loc.append(_(DUPA_CONECTARE[scop]))
		probleme = len(rai) + len(necit)
		if probleme <= 1:
			# sfatul despre memoria interna, si cu un disc rau sau necitit conectat; cu doua sau mai multe, explicatiile
			# lor (mai jos) sunt cele utile si nu ar mai incapea toate in caseta (5 randuri in germana si rusa)
			detalii_loc.append(_("Nu înregistra în memoria internă a receptorului: e prea mică și receptorul se poate "
				"bloca."))
		if not probleme and cale and motiv and motiv != "lipsa":
			# nimic conectat, locul pus de mana in RAM sau pe memoria interna: explicatia tehnica
			detalii_loc.append(_cuPunct(_stocare().textMotiv(motiv, cale)))
	if loc_bun and singur:
		# locul a devenit bun cat era deschis ecranul (un disc pus acum): cine l-a deschis poate merge mai departe
		randuri.append({"text": _("Continuă"), "actiune": ACT_CONTINUA, "punct": None, "detaliu": ""})
	if intrebare:
		for d in (dec["discuri"] or sorted([x for x in discuri if x.get("bun")], key=_liber, reverse=True)):
			randuri.append({"text": _randIntrebare(d), "actiune": ACT_FOLOSESTE, "punct": d["punct"],
				"detaliu": _detaliuRand(d, cu_liber=False)})
	elif not necunoscut and not (singur and automat):
		for d in discuri:
			if d.get("bun") is False:
				continue
			# locul liber al discului pe care se salveaza (acum sau la prima inregistrare) e deja in detaliu: explicatia
			# randului lui nu il mai spune o data
			if loc_bun and d.get("folosit"):
				randuri.append({"text": _("„%s”: aici se salvează acum") % d["nume"], "actiune": ACT_ACTUAL,
					"punct": d["punct"], "detaliu": _detaliuRand(d, cu_liber=loc.get("liber") is None)})
			elif automat and d["punct"] == automat:
				# din meniu: discul ales singur la prima inregistrare; OK il pregateste de acum
				randuri.append({"text": _("„%s”: aici se vor salva") % d["nume"], "actiune": ACT_FOLOSESTE,
					"punct": d["punct"], "detaliu": _detaliuRand(d, cu_liber=d.get("liber") is None)})
			elif loc_bun or automat:
				if scop == SCOP_TIMESHIFT:
					rand = _("Folosește „%s” pentru timeshift și înregistrări") % d["nume"]
				else:
					rand = _("Folosește „%s” pentru înregistrări") % d["nume"]
				randuri.append({"text": rand, "actiune": ACT_FOLOSESTE, "punct": d["punct"], "detaliu": _detaliuRand(d)})
	for d in rai:
		detalii_disc.append(_("„%s” nu se poate folosi: %s.") % (d["nume"], textMotivDisc(d.get("motiv"))))
	for n in necit:
		detalii_disc.append(_("„%s” nu poate fi citit de receptor. Îl poți formata aici sau pe un calculator, ca FAT32. "
			"Formatarea șterge tot de pe el.") % n["nume"])
		# drumul spre formatare (randul 'Formatează'), numai dupa citire si nu cat ecranul pregateste singur alt disc
		disc_intreg = discul(n.get("dispozitiv"))
		if disc_intreg and not necunoscut and not (singur and automat):
			randuri.append({"text": _("Formatează „%s”") % n["nume"], "actiune": ACT_FORMATEAZA, "punct": None,
				"disc": disc_intreg, "detaliu": _("Deschide formatarea. Înainte să șteargă ceva, receptorul te întreabă.")})
	if se_citeste and stare is None and cand and not necunoscut:
		detalii_disc.append(_("Se citesc discurile..."))
	randuri.append({"text": _("Închide"), "actiune": ACT_INCHIDE, "punct": None, "detaliu": ""})
	return {"titlu": titlu, "text": text, "detaliu": " ".join(x for x in detalii_loc + detalii_disc if x),
		"detaliu_loc": " ".join(x for x in detalii_loc if x), "randuri": randuri, "bun": bun, "automat": automat,
		"intrebare": intrebare, "cauta": necunoscut}


def _randIntrebare(d):
	"""Randul unui disc la intrebare: numele, locul liber si marimea (pe acelasi rand, ca discurile sa se compare)."""
	if d.get("liber") is not None:
		return _("„%s”, liber %s din %s") % (d["nume"], marime(d["liber"]), marime(d["total"]))
	return "„%s”" % d["nume"]


def _detaliuRand(d, cu_liber=True):
	"""Explicatia randului ales: spatiul liber (daca nu e deja in rand), ce se face pe disc si, pe un disc FAT32 mai
	mare de 4 GB, cat poate tine o inregistrare (un fisier vfat nu trece de 4 GB, iar inregistrarea nu se imparte in
	bucati)."""
	parti = []
	if cu_liber and d.get("liber") is not None:
		parti.append(_("Liber: %s din %s.") % (marime(d["liber"]), marime(d["total"])))
	elif cu_liber and d.get("bun") is None:
		parti.append(_("Se citește discul..."))
	if d.get("folosit"):
		pass
	elif d.get("are_movie"):
		parti.append(_("Dosarul movie există deja pe el."))
	else:
		parti.append(_("Se face pe el dosarul movie. Nu se șterge nimic."))
	if d.get("fel") == "vfat" and (d.get("total") or 0) > LIMITA_FAT:
		parti.append(_("Pe FAT32, o înregistrare se oprește la 4 GB (cam o oră pe un canal HD)."))
	return " ".join(parti)


# ------------------------------------------------------------------ alegerea in fundal (fara ecran)

_fundal = {"pas": None, "scop": SCOP_TEMPORIZATOR, "cale": "", "motiv": None, "cand": [], "timp": 0.0, "arata": True,
	"punct": None}
_ceasFundal = []    # eTimer-ul alegerii in fundal (tinut aici, altfel GC-ul l-ar culege)


def inFundal():
	"""Pasul alegerii in fundal (FUNDAL_CITIRE, FUNDAL_PREGATIRE) sau None."""
	return _fundal["pas"]


def alegeInFundal(cale, scop=SCOP_TEMPORIZATOR, arata=True, ceas=None, acum=None):
	"""Pe firul enigma2, fara niciun ecran: citeste din nou discurile (pe un fir) si ia decizia. Un disc de folosit
	singur (cel tinut minte, singurul bun sau, la un temporizator, cel cu cel mai mult loc liber) se pregateste (pe un
	fir) si primeste setarile, apoi un mesaj scurt. Pentru intrebare si pentru „niciun disc”, ecranul „Locul
	înregistrărilor” in notificari, daca `arata`. Una singura deodata: False daca alta e in curs sau nu a putut porni."""
	acum = time.time() if acum is None else acum
	if _fundal["pas"] is not None and 0 <= acum - _fundal["timp"] < TERMEN_FUNDAL_S:
		return False
	try:
		cand = candidati()
	except Exception as eroare:
		print("[HdsLocInregistrari] alegerea in fundal, discurile: %s" % eroare)
		return False
	_fundal.update({"pas": FUNDAL_CITIRE, "scop": scop if scop in SCOPURI else SCOP_TEMPORIZATOR, "cale": cale or "",
		"motiv": None, "cand": cand, "timp": acum, "arata": bool(arata), "punct": None})
	# o citire noua: cea tinuta (pana la VARSTA_STARE secunde) poate fi de dinainte ca discul sa fie scos sau pus
	cereStare(cand, _fundal["cale"], din_nou=True)
	try:
		c = (ceas or _ceasEnigma)(pasFundal)
		del _ceasFundal[:]
		_ceasFundal.append(c)
		c.start(PAS_FUNDAL_MS, False)
	except Exception as eroare:
		print("[HdsLocInregistrari] ceasul alegerii in fundal: %s" % eroare)
		_fundal["pas"] = None
		return False
	return True


def _gataFundal():
	_fundal["pas"] = None
	# numai oprit: pasFundal ruleaza chiar din acest eTimer (ca la culege)
	for c in _ceasFundal:
		try:
			c.stop()
		except Exception:
			pass


def pasFundal(acum=None, anunta=None, deschide=None, retinut=None):
	"""Un pas al alegerii in fundal (din eTimer-ul ei, pe firul enigma2). Intoarce pasul in care a ramas (None: gata).
	`anunta` si `deschide` sunt pentru probe (mesajul scurt si ecranul din notificari). O exceptie opreste alegerea (cu
	un rand in jurnal): altfel s-ar repeta la fiecare bataie a ceasului, pana la TERMEN_FUNDAL_S; reincercarea
	temporizatorului sau o programare noua o porneste din nou."""
	try:
		return _pasFundal(acum, anunta, deschide, retinut)
	except Exception as eroare:
		print("[HdsLocInregistrari] choosing the disk in the background: %s" % eroare)
		_gataFundal()
		return None


def _pasFundal(acum, anunta, deschide, retinut):
	acum = time.time() if acum is None else acum
	pas = _fundal["pas"]
	if pas is None:
		_gataFundal()
		return None
	if not 0 <= acum - _fundal["timp"] < TERMEN_FUNDAL_S:
		print("[HdsLocInregistrari] choosing the disk in the background: no result in %d s" % TERMEN_FUNDAL_S)
		_gataFundal()
		return None
	scop, cale = _fundal["scop"], _fundal["cale"]
	if pas == FUNDAL_CITIRE:
		stare, se_citeste = cereStare(_fundal["cand"], cale)
		if stare is None or se_citeste:
			return pas
		_fundal["motiv"] = (stare.get("loc") or {}).get("motiv")
		dec = decizie(stare, discRetinut() if retinut is None else retinut, scop)
		if dec["fel"] == DEC_BUN:
			_gataFundal()
			return None
		if dec["fel"] == DEC_DISC:
			pornit, _mesaj = foloseste(dec["disc"]["punct"], _fundal["cand"], scop, de_ce=dec["de_ce"])
			if not pornit:
				# alt disc se pregateste chiar acum (ecranul sau pagina web): dupa el citirea incepe din nou
				return pas
			_fundal["pas"] = FUNDAL_PREGATIRE
			_fundal["punct"] = dec["disc"]["punct"]
			return FUNDAL_PREGATIRE
		_gataFundal()
		if _fundal["arata"]:
			(deschide or deschideEcran)(cale, _fundal["motiv"], scop)
		return None
	lucru = culege()
	al_meu = lucru is not None and lucru.get("punct") == _fundal["punct"]
	if al_meu and (lucru["stare"] == LUCRU_IN_LUCRU or (lucru["stare"] == LUCRU_GATA and not lucru.get("aplicat"))):
		return pas
	_gataFundal()
	if not al_meu:
		return None
	if lucru["stare"] == LUCRU_GATA:
		if not _fundal["arata"]:
			# o reincercare a aceluiasi temporizator: mesajul s-a aratat o data (RecordTimer.hdsVerificaDisc)
			return None
		text, detaliu = textLucru(lucru)
		if anunta is not None:
			anunta(text, detaliu)
		else:
			anuntaScurt(text, detaliu, scop)
	elif _fundal["arata"]:
		# pregatirea a cazut (stick protejat la scriere, plin): ecranul arata de ce si discurile de ales
		(deschide or deschideEcran)(cale, _fundal["motiv"], scop)
	return None


def uitaFundal():
	"""Pentru probe."""
	_fundal.update({"pas": None, "scop": SCOP_TEMPORIZATOR, "cale": "", "motiv": None, "cand": [], "timp": 0.0,
		"arata": True, "punct": None})
	del _ceasFundal[:]
	_inchideri.clear()


def anuntaScurt(text, detaliu="", scop=SCOP_TEMPORIZATOR):
	"""Mesajul de dupa o alegere facuta in fundal: se arata cand bara e deasupra si se inchide singur dupa
	MESAJ_FUNDAL_S. In ecranul „Locul înregistrărilor” (fraza sus, explicatia dedesubt), nu intr-un MessageBox: caseta
	lui de text are trei randuri, iar explicatia cu drumul din meniu nu ar incapea."""
	try:
		from Tools import Notifications
	except ImportError:
		return False
	try:
		from Screens.HdsLocInregistrari import HdsLocInregistrari
	except ImportError:
		HdsLocInregistrari = None
	if HdsLocInregistrari is None:
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text=text, type=MessageBox.TYPE_INFO, timeout=MESAJ_FUNDAL_S, id=ID_MESAJ)
		return True
	Notifications.RemovePopup(ID_MESAJ)
	Notifications.AddNotificationWithID(ID_MESAJ, HdsLocInregistrari, None, None, scop, mesaj=(text, detaliu))
	return True


def deschideEcran(cale, motiv, scop):
	"""Ecranul „Locul înregistrărilor” prin notificari, unul singur deodata (ID_ECRAN): pentru intrebare, pentru „niciun
	disc” si dupa o pregatire cazuta."""
	try:
		from Tools import Notifications
		from Screens.HdsLocInregistrari import HdsLocInregistrari
	except ImportError:
		return False
	if [x for x in Notifications.current_notifications if x[0] == ID_ECRAN] or \
			[x for x in Notifications.notifications if x[4] == ID_ECRAN]:
		return False
	Notifications.AddNotificationWithID(ID_ECRAN, HdsLocInregistrari, cale, motiv, scop)
	return True


def tineMinte(cale, config=None, configfile=None, cand=None, realpath=None, tabel=None):
	"""Dupa ce o inregistrare porneste pe un disc bun (RecordTimer.hdsVerificaDisc): discul ei devine cel tinut minte,
	si cand locul a fost ales din „Dosarele înregistrărilor” sau din fereastra temporizatorului. Pe firul enigma2:
	citeste numai /proc/mounts, /sys si /dev/disk/by-uuid; scrie setarile numai la o schimbare. True daca s-a
	schimbat."""
	s = setareDisc(config)
	if s is None:
		return False
	if cand is None:
		cand = candidati()
	punct, _radacina = disculLocului(cale, cand, realpath, tabel)
	ident = [c.get("id") or "" for c in cand if c["punct"] == punct][:1]
	if not ident or not ident[0] or s.value == ident[0]:
		return False
	s.value = ident[0]
	s.save()
	if configfile is None:
		configfile = getattr(_modulSetari(), "configfile", None)
	if configfile is not None:
		configfile.save()
	print("[HdsLocInregistrari] recording on %s: this disk is remembered (%s)" % (punct, ident[0]))
	return True


def laProgramare(dirname=None, justplay=False):
	"""Carligul din RecordTimer.record, dupa ce s-a pus un temporizator nou (din ghid, din lista, din web): daca locul
	lui nu e un disc bun, discul se alege acum, nu la ora inregistrarii (alegeInFundal, scopul „programare”)."""
	if justplay:
		return False
	try:
		cale = locTemporizator(dirname)
	except Exception as eroare:
		print("[HdsLocInregistrari] locul inregistrarii programate: %s" % eroare)
		return False
	return alegeInFundal(cale, SCOP_PROGRAMARE)
