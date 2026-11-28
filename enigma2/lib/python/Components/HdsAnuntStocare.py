# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAnuntStocare.py: anuntul de pe ecran cand omul pune sau scoate un stick, un hard disk sau un card (din 0.8.0).
#
# De ce: un stick nou pus in receptor era intampinat ori cu nimic (cand in fata era un meniu), ori cu o eroare rosie
# („Pe acest mediu nu s-au gasit fisiere care pot fi afisate”), fara numele si marimea lui si fara sa spuna ce se poate
# face cu el. La scoatere nu aparea nimic. Un stick FAT32 primea inregistrari si pauza emisiunii fara nicio vorba despre
# limita de 4 GB a unui fisier: pauza emisiunii se oprea in tacere dupa ~40 de minute, iar inregistrarea cu „Disc plin?”.
#
# Ce face:
# - la punere (evenimentele nucleului, din Plugins/SystemPlugins/Hotplug): dupa ce receptorul a montat discul, UN anunt pe
#   disc (nu unul pe partitie), PESTE orice ecran (Screens/HdsAnuntStocare.py, fereastra nemodala): numele si marimea, iar
#   un rand in plus numai cand e ceva de stiut: FAT32 (limita de 4 GB), disc care nu poate fi citit, disc numai pentru
#   citire. Tasta INFO sau EPG, cat e anuntul pe ecran, deschide pagina discului (Screens/HarddiskSetup: modelul, marimea, starea
#   si formatarea);
# - la scoatere: un anunt cu numele discului scos; daca pe el se salvau inregistrarile, o spune;
# - in standby, la pornire si cu optiunea oprita (config.usage.hds_anunt_stocare, Da din fabrica) nu apare nimic pe ecran;
#   ultimele anunturi raman pentru pagina web (/stocare, cardul „Ultimele discuri puse și scoase”);
# - cat merge formatarea sau verificarea din meniul nostru (Components/HdsDiscuri) nu se anunta nimic: partitiile dispar si
#   apar din nou fara ca omul sa fi atins discul;
# - FAT32 la pauza emisiunii (Screens/InfoBarGenerics.startTimeshift -> pauzaPornita): inregistratorul pauzei nu trimite
#   niciun eveniment la eroarea de scriere (lib/service/servicedvb.cpp), deci un ceas rar citeste marimea fisierului de pauza
#   NUMAI cand locul e FAT; la 4 GB spune ce s-a intamplat. La inregistrare (RecordTimer.gotRecordEvent ->
#   mesajEroareScriere) textul spune cauza adevarata: limita FAT32, nu „Disc plin?”.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC folosesc direct functiile curate (discDin,
# citesteDisc, textPunere, textScoatere, mesajEroareScriere), cu /sys si /proc/mounts date de ele.

import os
import time

# cat se asteapta dupa ultimul eveniment al unui disc pana la anunt: sistemul monteaza, apoi enigma2 da numele stabil
# (Hotplug.MOUNT_WAIT_MS = 2000) si citeste discul pe firul lui
ASTEPTARE_PUNERE_MS = 5000
# daca partitiile exista, dar niciuna nu e inca montata: inca atatea incercari, la atata timp
REINCERCARI = 3
REINCERCARE_MS = 3000
# cat timp managerul de discuri inca lucreaza la montare (reincearca la 5, 15 si 30 s): cel mult atatea asteptari in plus
REINCERCARI_MONTARE = 10
# evenimentele din primele secunde ale sesiunii sunt ale discurilor care se trezesc tarziu la pornire: fara anunt
LINISTE_LA_PORNIRE_S = 30
# marginea sub limita de la care fisierul se socoteste ajuns la ea
MARGINE_LIMITA = 4 * 1024 * 1024
ASTEPTARE_SCOATERE_MS = 1200
DURATA_ANUNT_MS = 12000
DURATA_LIMITA_MS = 30000
MAX_ULTIMELE = 8
# un fisier pe FAT nu trece de 4 GiB - 1
LIMITA_FAT = 4 * 1024 ** 3 - 1
FS_FAT = ("vfat", "msdos")
NUME_FS = {"vfat": "FAT32", "msdos": "FAT", "ntfs": "NTFS", "ntfs3": "NTFS", "fuseblk": "NTFS", "exfat": "exFAT"}
# ceasul pauzei emisiunii pe FAT
PAZA_PAUZA_MS = 20000
IGNORATE = ("loop", "ram", "mtdblock", "romblock", "zram", "dm-", "nbd", "sr")

PUS, FAT, NECITIT, NUMAI_CITIRE, SCOS = "pus", "fat", "necitit", "numai_citire", "scos"

_stare = {"sesiune": None, "pornit_la": 0.0}
_ceasuri = {}       # discul -> eTimer
_incercari = {}     # discul -> cate reincercari s-au facut
_cunoscute = {}     # discul -> ultima citire (citesteDisc), pentru numele de la scoatere
_ultimele = []      # cele mai noi intai: {"cand", "fel", "disc", "text"}
_avertizate = set() # punctele FAT despre care s-a spus deja la pornirea pauzei / inregistrarii
_paza = {"ceas": None, "bara": None, "loc": None}
_liniste = {}       # discul -> ora ultimului eveniment venit in timpul formatarii / verificarii noastre
LINISTE_DUPA_LUCRARE_S = 20


def N_(text):
	return text


def _t(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsAnuntStocare] %s" % text)


# ---------------------------------------------------------------- functii curate (probele de pe PC)

def discDin(device):
	"""Discul intreg al unui nume de dispozitiv: sda1 -> sda, mmcblk1p2 -> mmcblk1, nvme0n1p1 -> nvme0n1, sda -> sda.
	"" pentru ce nu e disc (loop, ram, mtdblock, sr)."""
	device = (device or "").replace("/dev/", "")
	if not device or device.startswith(IGNORATE):
		return ""
	if device.startswith(("mmcblk", "nvme")):
		cap, sep, coada = device.rpartition("p")
		if sep and coada.isdigit() and cap[-1:].isdigit():
			return cap
		return device
	return device.rstrip("0123456789") or device


def _citeste(cale):
	try:
		with open(cale, "r", encoding="utf-8", errors="replace") as f:
			return f.read().strip()
	except (OSError, IOError):
		return ""


def marime(octeti):
	"""Marimea cum scrie pe cutia discului (zecimal): 124 GB, 2 TB, 512 MB."""
	try:
		octeti = int(octeti)
	except (TypeError, ValueError):
		return ""
	if octeti <= 0:
		return ""
	if octeti >= 1000 ** 4:
		v = octeti / float(1000 ** 4)
		return ("%.1f TB" % v).replace(".0 TB", " TB")
	if octeti >= 1000 ** 3:
		return "%d GB" % int(round(octeti / float(1000 ** 3)))
	return "%d MB" % max(1, int(round(octeti / float(1000 ** 2))))


def _montariDisc(disc, cale_mounts="/proc/mounts"):
	"""[(partitia, punctul, felul, numai_citire)] pentru montarile discului, in ordinea din /proc/mounts."""
	rez = []
	try:
		with open(cale_mounts, "r", encoding="utf-8", errors="surrogateescape") as f:
			randuri = f.readlines()
	except (OSError, IOError):
		return rez
	for linie in randuri:
		p = linie.split()
		if len(p) < 4 or not p[0].startswith("/dev/"):
			continue
		if discDin(p[0]) != disc:
			continue
		rez.append((p[0][5:], p[1].replace("\\040", " "), p[2], "ro" in p[3].split(",")))
	return rez


def citesteDisc(disc, sys_block="/sys/block", cale_mounts="/proc/mounts"):
	"""Ce se stie despre disc fara sa fie atins (numai /sys si /proc/mounts): None cand nu mai exista."""
	baza = os.path.join(sys_block, disc)
	if not disc or not os.path.isdir(baza):
		return None
	fabricant = _citeste(os.path.join(baza, "device", "vendor"))
	model = _citeste(os.path.join(baza, "device", "model")) or _citeste(os.path.join(baza, "device", "name"))
	nume = " ".join(x for x in (fabricant, model) if x and x.lower() not in ("usb", "generic", "ata"))
	try:
		octeti = int(_citeste(os.path.join(baza, "size")) or 0) * 512
	except ValueError:
		octeti = 0
	try:
		partitii = sorted(x for x in os.listdir(baza) if x.startswith(disc) and os.path.isdir(os.path.join(baza, x)))
	except OSError:
		partitii = []
	montari = _montariDisc(disc, cale_mounts)
	feluri = []
	for _dev, _punct, fel, _ro in montari:
		if fel not in feluri:
			feluri.append(fel)
	return {
		"disc": disc,
		"nume": nume,
		"octeti": octeti,
		"marime": marime(octeti),
		"partitii": partitii,
		"montari": montari,
		"puncte": [m[1] for m in montari],
		"feluri": feluri,
		"numai_citire": bool(montari) and all(m[3] for m in montari),
	}


def numeAfisat(d):
	"""„Kingston DataTraveler 3.0, 124 GB”; fara model: „disc sda, 124 GB”."""
	nume = d.get("nume") or _t("disc %s") % d.get("disc", "")
	return "%s, %s" % (nume, d["marime"]) if d.get("marime") else nume


def felPunere(d):
	"""Cazul anuntului la punere, din citirea discului."""
	if not d.get("montari"):
		return NECITIT
	# FAT numai cand tot ce e montat de pe disc e FAT (un disc ext4 cu o partitie mica FAT de pornire nu e „FAT32”)
	if all(f in FS_FAT for f in d.get("feluri", ())) and d.get("octeti", 0) > LIMITA_FAT:
		return FAT
	if d.get("numai_citire"):
		return NUMAI_CITIRE
	return PUS


def textPunere(d):
	"""(felul, textul anuntului). O propozitie cu numele; un rand in plus numai cand e ceva de stiut."""
	fel = felPunere(d)
	text = _t("Stocare nouă: %s.") % numeAfisat(d)
	if fel == FAT:
		text += "\n" + _t("Este FAT32: o înregistrare se oprește la 4 GB (cam 40 de minute HD). Din Detalii o poți formata ext4.")
	elif fel == NECITIT:
		text += "\n" + _t("Receptorul nu o poate citi: nu are un sistem de fișiere cunoscut. Din Detalii o poți formata.")
	elif fel == NUMAI_CITIRE:
		text += "\n" + _t("Se poate numai citi, nu și scrie.")
	return fel, text


def textScoatere(d, loc_inregistrari=""):
	"""Textul anuntului la scoatere; `loc_inregistrari`: calea inregistrarilor (un rand in plus cand era pe discul scos)."""
	text = _t("Stocare scoasă: %s.") % numeAfisat(d)
	if d.get("are_inregistrari") or (loc_inregistrari and _subPunct(loc_inregistrari, d.get("puncte") or ())):
		text += "\n" + _t("Înregistrările și pauza emisiunii nu mai au unde se salva până o pui la loc.")
	return text


def textStareDisc(d):
	"""Pentru pagina discului (Screens/HarddiskSetup): ce sistem de fisiere are acum si unde e montat; "" fara disc."""
	if not d:
		return ""
	if not d.get("montari"):
		return _t("Acum: receptorul nu îl poate citi (fără un sistem de fișiere cunoscut). Formatarea îl face bun de folosit.")
	_dev, punct, fel, _ro = d["montari"][-1]
	text = _t("Acum: %s, montat în %s.") % (NUME_FS.get(fel, fel), punct)
	if felPunere(d) == FAT:
		text += " " + _t("Pe FAT32 o înregistrare se oprește la 4 GB; pentru înregistrări lungi formatează-l ext4.")
	return text


def _subPunct(cale, puncte):
	cale = cale.rstrip("/") + "/"
	if cale.startswith("/hdd/"):
		cale = "/media" + cale
	return any(cale.startswith(p.rstrip("/") + "/") for p in puncte if p and p != "/")


def felSistem(cale, cale_mounts="/proc/mounts", realpath=None):
	"""Felul sistemului de fisiere care tine `cale` ("" cand nu se afla)."""
	try:
		from Components import HdsStocare
		rand = HdsStocare.montarePentru(cale, HdsStocare._montari(cale_mounts), realpath)
	except Exception:
		rand = None
	return rand[1] if rand else ""


def atinsLimitaFat(fel, octeti_fisier):
	return fel in FS_FAT and (octeti_fisier or 0) >= LIMITA_FAT - MARGINE_LIMITA


def mesajEroareScriere(cale_fisier, fel=None, octeti=None, liber=None):
	"""Textul erorii de scriere a unei inregistrari, cu cauza adevarata cand se poate afla: limita de 4 GB a FAT32 (fisierul a
	ajuns la ea), discul plin (sub 64 MB liberi) sau, altfel, textul vechi. `fel`, `octeti`, `liber`: date de probe."""
	dosar = os.path.dirname(cale_fisier) or "/"
	if fel is None:
		fel = felSistem(dosar)
	if octeti is None:
		try:
			octeti = os.path.getsize(cale_fisier)
		except OSError:
			octeti = 0
	if atinsLimitaFat(fel, octeti):
		return _t("Înregistrarea s-a oprit la 4 GB: discul este FAT32, iar pe FAT32 un fișier nu poate fi mai mare. Discul nu este plin. "
			"Pentru înregistrări lungi formatează-l ext4: Meniu > Setări > Înregistrări și discuri > Formatarea discului.")
	if liber is None:
		try:
			st = os.statvfs(dosar)
			liber = st.f_bavail * st.f_frsize
		except OSError:
			liber = None
	if liber is not None and liber < 64 * 1024 * 1024:
		return _t("Înregistrarea s-a oprit: discul este plin. Șterge înregistrări vechi sau alege alt disc.")
	return _t("Write error while recording. Disk full?\n")


def textLimitaPauza():
	return _t("Pauza emisiunii s-a oprit la 4 GB: discul este FAT32, iar pe FAT32 un fișier nu poate fi mai mare. Ce a urmat nu s-a mai salvat. "
		"Din Detalii îl poți formata ext4.")


def textAvertizareFat():
	return _t("Discul este FAT32: pauza emisiunii și o înregistrare țin cel mult 4 GB (cam 40 de minute pe un canal HD).")


def fisierPauza(loc, listdir=None, stat=None):
	"""Marimea fisierului de pauza in care se scrie acum: cel mai nou „timeshift.XXXXXX” din `loc` (fara fisierele ajutatoare;
	un fisier vechi de 4 GB ramas de la o cadere nu conteaza); 0 cand nu e niciunul."""
	nou = None
	try:
		nume = (listdir or os.listdir)(loc)
	except OSError:
		return 0
	for n in nume:
		if not n.startswith("timeshift.") or n.count(".") != 1:
			continue
		try:
			st = (stat or os.stat)(os.path.join(loc, n))
		except OSError:
			continue
		if nou is None or st.st_mtime >= nou.st_mtime:
			nou = st
	return nou.st_size if nou is not None else 0


# ---------------------------------------------------------------- legatura cu enigma2

def pornit():
	try:
		from Components.config import config
		return bool(config.usage.hds_anunt_stocare.value)
	except Exception:
		return True


def _inStandby():
	try:
		from Screens import Standby
		return Standby.inStandby is not None
	except Exception:
		return False


def _lucrareDisc(disc=None):
	"""Formatarea sau verificarea din meniul nostru merge acum pe discul acesta? (alt disc pus sau scos intre timp se anunta)"""
	try:
		from Components import HdsDiscuri
		if not HdsDiscuri.inLucru():
			return False
		lucru = HdsDiscuri.stareLucru() or {}
		return disc is None or not lucru.get("dispozitiv") or discDin(lucru.get("dispozitiv")) == disc
	except Exception:
		return False


def _inMontare(disc):
	"""Managerul de discuri mai are ceva de montat de pe discul acesta (partitie in asteptare sau montare programata)?"""
	try:
		from Components.Harddisk import harddiskmanager as hm
		chei = list(getattr(hm, "pending", {})) + list(getattr(hm, "mount_timers", {}))
		return any(isinstance(c, str) and ":" not in c and discDin(c) == disc for c in chei)
	except Exception:
		return False


def _areInregistrari(d):
	"""Locul inregistrarilor e pe discul acesta? Se afla cat discul e pus (drumul adevarat: /media/hdd poate fi o legatura spre
	/media/sda1) si se tine minte pentru anuntul de la scoatere."""
	try:
		loc = _locInregistrari()
		if _subPunct(loc, d.get("puncte") or ()):
			return True
		return bool(d.get("puncte")) and _subPunct(os.path.realpath(loc), d["puncte"])
	except Exception:
		return False


def _locInregistrari():
	try:
		from Components.config import config
		return config.usage.default_path.value or "/hdd/movie/"
	except Exception:
		return "/hdd/movie/"


def _noteaza(fel, disc, text):
	_ultimele.insert(0, {"cand": int(time.time()), "fel": fel, "disc": disc, "text": text})
	del _ultimele[MAX_ULTIMELE:]
	_jurnal("%s %s: %s" % (fel, disc, text.replace("\n", " | ")))


def _arata(text, disc, detalii, durata_ms=DURATA_ANUNT_MS):
	"""Pe ecran, peste orice ecran; nimic in standby, fara sesiune sau cu optiunea oprita."""
	s = _stare["sesiune"]
	if s is None or _inStandby() or not pornit():
		return False
	try:
		from Screens import HdsAnuntStocare as F
		F.arata(s, text, disc if detalii else None, durata_ms)
		return True
	except Exception as e:
		_jurnal("anuntul: %r" % (e,))
		return False


def _programeaza(disc, ms, functie):
	from enigma import eTimer
	vechi = _ceasuri.pop(disc, None)
	if vechi is not None:
		vechi.stop()
	ceas = eTimer()
	ceas.callback.append(lambda: functie(disc))
	ceas.start(int(ms), True)
	_ceasuri[disc] = ceas


def eveniment(actiune, device):
	"""Din Hotplug.handleEvent, pentru fiecare eveniment de disc sau de partitie al nucleului: "add" / "remove"."""
	disc = discDin(device)
	if not disc:
		return
	acum = time.monotonic()
	if _lucrareDisc(disc):
		# formatarea / verificarea noastra scoate si pune partitiile; discul ramane cunoscut cu ce avea
		_liniste[disc] = acum
		return
	if acum - _liniste.get(disc, -LINISTE_DUPA_LUCRARE_S) < LINISTE_DUPA_LUCRARE_S:
		# ultimele evenimente ale aceleiasi lucrari (recitirea tabelei de partitii): starea noua se tine minte, fara anunt
		d = citesteDisc(disc)
		if d is not None:
			d["anuntat"] = True
			_cunoscute[disc] = d
		return
	if actiune == "add":
		_incercari[disc] = 0
		_programeaza(disc, ASTEPTARE_PUNERE_MS, _laPunere)
	elif actiune == "remove":
		# numai disparitia discului intreg se anunta (o partitie scoasa de o formatare facuta in alta parte nu)
		_programeaza(disc, ASTEPTARE_SCOATERE_MS, _laScoatere)


def _laPunere(disc):
	_ceasuri.pop(disc, None)
	try:
		d = citesteDisc(disc)
		if d is None:
			return
		if _lucrareDisc(disc):
			d["anuntat"] = True
			_cunoscute[disc] = d
			_liniste[disc] = time.monotonic()
			return
		vechi = _cunoscute.get(disc)
		if not d["octeti"]:
			# cititor de carduri fara card: nu e o stocare; daca avea un card montat, cardul a fost scos (evenimentul „change”)
			if vechi is not None and vechi.get("montari"):
				_cunoscute.pop(disc, None)
				_anuntaScoatere(disc, vechi)
			return
		n = _incercari.get(disc, 0)
		if not d["montari"] and (n < REINCERCARI or (_inMontare(disc) and n < REINCERCARI_MONTARE)):
			# montarea inca nu e facuta: mai asteapta (discuri mari, verificarea de la montare, reincercarile managerului)
			_incercari[disc] = n + 1
			_programeaza(disc, REINCERCARE_MS, _laPunere)
			return
		d["are_inregistrari"] = _areInregistrari(d)
		_cunoscute[disc] = d
		if time.time() - _stare["pornit_la"] < LINISTE_LA_PORNIRE_S:
			# discul s-a trezit tarziu la pornirea receptorului: era deja pus, nu se anunta
			d["anuntat"] = True
			return
		if vechi is not None and vechi.get("anuntat") and vechi.get("montari") == d["montari"]:
			# acelasi disc, aceeasi stare (un eveniment „change” fara schimbare): nu se repeta anuntul
			d["anuntat"] = True
			return
		d["anuntat"] = True
		fel, text = textPunere(d)
		_noteaza(fel, disc, text)
		_arata(text, disc, True)
	except Exception as e:
		_jurnal("punerea %s: %r" % (disc, e))


def _laScoatere(disc):
	_ceasuri.pop(disc, None)
	try:
		if citesteDisc(disc) is not None:
			return  # discul e inca acolo: a disparut numai o partitie
		_anuntaScoatere(disc, _cunoscute.pop(disc, None) or {"disc": disc, "nume": "", "marime": "", "puncte": []})
	except Exception as e:
		_jurnal("scoaterea %s: %r" % (disc, e))


def _anuntaScoatere(disc, d):
	text = textScoatere(d, _locInregistrari())
	_noteaza(SCOS, disc, text)
	_arata(text, disc, False)


def porneste(session):
	"""La pornirea sesiunii: discurile deja puse se tin minte (numele lor, pentru scoatere), fara niciun anunt."""
	_stare["sesiune"] = session
	_stare["pornit_la"] = time.time()
	try:
		for disc in os.listdir("/sys/block"):
			if discDin(disc) != disc:
				continue
			d = citesteDisc(disc)
			if d is not None and (d["montari"] or d["partitii"]):
				d["anuntat"] = True
				d["are_inregistrari"] = _areInregistrari(d)
				_cunoscute[disc] = d
	except Exception as e:
		_jurnal("pornirea: %r" % (e,))


def deschideDetalii(session, disc):
	"""Tasta INFO sau EPG pe anunt: pagina discului (modelul, marimea, starea, formatarea); fara disc cunoscut, „Locul înregistrărilor”."""
	try:
		# hard diskurile si stick-urile, ca in Meniu > Formatarea discului (Components/HdsDiscuri.discuriOferite; numai /sys)
		from Components import HdsDiscuri
		from Screens.HarddiskSetup import HarddiskSetup
		hd = HdsDiscuri.discul(disc)
		if hd is not None:
			session.open(HarddiskSetup, hd, HarddiskSetup.HARDDISK_INITIALIZE)
			return True
		from Screens.HdsLocInregistrari import HdsLocInregistrari
		session.open(HdsLocInregistrari)
		return True
	except Exception as e:
		_jurnal("detaliile %s: %r" % (disc, e))
		return False


def stareWeb():
	"""Pentru /api/stocare (cardul „Ultimele discuri puse și scoase” din /stocare)."""
	return {"pornit": pornit(), "ultimele": [dict(x) for x in _ultimele]}


def setPornit(da):
	"""Din pagina web: optiunea „Anunț pe ecran când pui sau scoți o stocare” (aceeasi ca in meniu)."""
	from Components.config import config, configfile
	config.usage.hds_anunt_stocare.value = bool(da)
	config.usage.hds_anunt_stocare.save()
	configfile.save()
	return stareWeb()


# ---------------------------------------------------------------- FAT32: pauza emisiunii si inregistrarea

def _discPentruLoc(loc):
	try:
		from Components import HdsStocare
		rand = HdsStocare.montarePentru(loc)
		return discDin(rand[2]) if rand else ""
	except Exception:
		return ""


def avertizeazaFat(loc):
	"""La pornirea pauzei emisiunii sau a unei inregistrari pe FAT: o data pe disc (pana la repornirea interfetei), anuntul
	scurt cu limita de 4 GB. -> True cand locul e FAT."""
	try:
		if felSistem(loc) not in FS_FAT:
			return False
		disc = _discPentruLoc(loc)
		if disc not in _avertizate and _arata(textAvertizareFat(), disc, bool(disc)):
			_avertizate.add(disc)
			_jurnal("FAT %s: anuntul limitei de 4 GB aratat la pornirea pe %s" % (disc, loc))
		return True
	except Exception as e:
		_jurnal("avertizarea FAT: %r" % (e,))
		return False


def pauzaPornita(bara, loc):
	"""Din InfoBarTimeshift.startTimeshift, dupa ce pauza a pornit: numai pe FAT, anuntul si ceasul limitei de 4 GB."""
	try:
		_oprestePaza()
		if not avertizeazaFat(loc):
			return
		from enigma import eTimer
		ceas = eTimer()
		ceas.callback.append(_pasPaza)
		_paza.update({"ceas": ceas, "bara": bara, "loc": loc})
		ceas.start(PAZA_PAUZA_MS, False)
	except Exception as e:
		_jurnal("paza pauzei: %r" % (e,))


def _oprestePaza():
	ceas = _paza.get("ceas")
	if ceas is not None:
		ceas.stop()
	_paza.update({"ceas": None, "bara": None, "loc": None})


def _pasPaza():
	try:
		bara, loc = _paza["bara"], _paza["loc"]
		if bara is None or not getattr(bara, "timeshift_enabled", 0):
			_oprestePaza()
			return
		if fisierPauza(loc) >= LIMITA_FAT - MARGINE_LIMITA:
			disc = _discPentruLoc(loc)
			_oprestePaza()
			text = textLimitaPauza()
			_noteaza("limita", disc, text)
			_arata(text, disc, bool(disc), DURATA_LIMITA_MS)
	except Exception as e:
		_jurnal("pasul pazei: %r" % (e,))
		_oprestePaza()


def _reseteaza():
	"""numai pentru probe"""
	_stare.update({"sesiune": None, "pornit_la": 0.0})
	_ceasuri.clear()
	_incercari.clear()
	_cunoscute.clear()
	del _ultimele[:]
	_avertizate.clear()
	_liniste.clear()
	_oprestePaza()
