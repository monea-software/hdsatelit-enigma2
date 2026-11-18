# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com & hdsatelit.com
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMontareDiscuri.py: „Montarea discurilor” (0.7.5, cererea tamiciav7 si darog69: un stick apare ca /media/hdd si omul
# nu are cum sa-l treaca pe /media/usb sau /media/mmc, nici sa-l demonteze). O singura logica pentru ecranul de pe
# televizor (Screens/HdsMontareDiscuri.py) si pagina web /montare-discuri (HdsWebControl/montare_web.py):
#   - lista(): stick-urile, hard diskurile USB/SATA si cardurile SD ale receptorului (nu memoria interna si nici discul
#     de pe care porneste imaginea), cu locul de acum din /media si alegerile de loc;
#   - porneste(LOC, disc, nume): locul ales se tine minte dupa UUID (Harddisk.setMediaName, /etc/enigma2/hds-media-names.json,
#     ramane si dupa repornire) si se aplica ACUM: discul iese si intra din nou in lista lui Harddisk, pe aceeasi cale ca la
#     scoaterea si punerea stickului (montarea sistemului din /run/media ramane neatinsa); dosarele inregistrarilor,
#     programarile (HdsLocInregistrari.mutaCaiMedia) si locul ghidului TV (config.misc.hds_epg_loc) merg dupa disc;
#   - porneste(DEMONTARE, disc): demontare curata (sync, apoi umount fara -l: un fisier deschis opreste demontarea si
#     numele se pun la loc), dupa care discul se poate scoate; ramane demontat pana il scoti, pana la „Montează la loc” sau
#     pana la repornire;
#   - porneste(MONTARE, disc): montarea la loc a unui disc demontat de aici, pe locul ales.
# Refuz (si pe televizor si in web) cat o inregistrare sau timeshift-ul scrie pe disc (Harddisk.mediaNameBusy) si, la
# demontare, cat swap-ul e pornit pe el (HdsDiscuri.folosire). Lucrul cu discul merge pe un fir (HdsStocareDisc.cere, cu
# termen), iar ce tine de enigma2 (lista lui Harddisk, setarile, programarile) pe firul interfetei, cules de un eTimer.
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau managerul de discuri, firul si ceasul lor.

import os
import re
import subprocess
import time

LOC = "loc"
DEMONTARE = "demontare"
MONTARE = "montare"
FELURI = (LOC, DEMONTARE, MONTARE)

IN_LUCRU = "in_lucru"
GATA = "gata"
EROARE = "eroare"

TERMEN_FIR_S = 30
TERMEN_UMOUNT_S = 20
# dupa ce discul intra din nou in lista: cat se asteapta numele nou (scheduleMount + planul de montare)
TERMEN_NUME_S = 20
INTARZIERE_MONTARE_MS = 3000
PAS_MS = 250
# cat timp ramane in pagina rezultatul ultimei lucrari
VARSTA_LUCRU_S = 600

SYS_BLOCK = "/sys/class/block/"
MEDIA = "/media/"
HDD = "/media/hdd"
_DISPOZITIV_RX = re.compile(r"^(sd[a-z]+[0-9]*|mmcblk[0-9]+(p[0-9]+)?|nvme[0-9]+n[0-9]+(p[0-9]+)?)$")

# discurile demontate de aici si inca prezente: dispozitiv -> {"nume", "eticheta", "sd", "physdev", "loc"}
_demontate = {}
_stare = {"lucru": None, "gen": 0, "ceas": None}


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsMontareDiscuri] %s" % text)


def _hm(hm=None):
	if hm is not None:
		return hm
	from Components.Harddisk import harddiskmanager
	return harddiskmanager


def _H():
	from Components import Harddisk
	return Harddisk


def dispozitivBun(dispozitiv):
	return bool(dispozitiv) and _DISPOZITIV_RX.match(dispozitiv) is not None


def discul(dispozitiv):
	"""sdb1 -> sdb, mmcblk1p1 -> mmcblk1, nvme0n1p2 -> nvme0n1 (discul intreg, pentru HdsDiscuri.folosire)."""
	m = re.match(r"^(mmcblk[0-9]+|nvme[0-9]+n[0-9]+)(p[0-9]+)?$", dispozitiv or "")
	if m:
		return m.group(1)
	return re.sub(r"[0-9]+$", "", dispozitiv or "")


def _marime(dispozitiv):
	try:
		with open(SYS_BLOCK + dispozitiv + "/size") as f:
			octeti = int(f.read().strip()) * 512
	except (OSError, ValueError):
		return ""
	for unitate in ("B", "KB", "MB", "GB"):
		if octeti < 1024:
			return "%d %s" % (octeti, unitate)
		octeti /= 1024.0
	return "%.1f TB" % octeti


def _prezent(dispozitiv):
	return os.path.exists(SYS_BLOCK + dispozitiv)


def _feluri(p):
	return bool(getattr(p, "usb", False) or getattr(p, "sata", False)), bool(getattr(p, "sd", False))


def _partitiiAle(hm, sarite=None):
	"""Partitiile de stick/disc/card pe care le stie managerul (listate sau inca asteptand numele): {dispozitiv: p}.
	`sarite` (dict, optional) primeste {dispozitiv: motiv} pentru partitiile cu nume de disc lasate deoparte."""
	H = _H()
	rez = {}
	for p in list(hm.partitions) + list(hm.pending.values()):
		dev = getattr(p, "device", None)
		if not dev or not dispozitivBun(dev):
			continue
		if getattr(p, "is_cdrom", False) or getattr(p, "has_partitions", False):
			continue
		motiv = ""
		mediu, sd = _feluri(p)
		if not getattr(p, "is_hotplug", False):
			motiv = MOTIV_FARA_HOTPLUG
		elif not (mediu or sd):
			motiv = "nici USB, nici SATA, nici card SD (physdev %s)" % getattr(p, "physdev", "?")
		elif H.isBootSlot(dev):
			motiv = "loc de pornire al unei imagini"
		if motiv:
			if sarite is not None and dev not in rez:
				sarite.setdefault(dev, motiv)
			continue
		rez.setdefault(dev, p)
		if sarite is not None:
			sarite.pop(dev, None)
	return rez


# ------------------------------------------------------------------ discurile montate pe care managerul nu le stie
# 0.7.7 (DRG, darog69, Vu+ Duo4K, forum 789 #2619): pagina /montare-discuri spunea "niciun disc" desi hard diskul era in
# /media/hdd si stickul in /media/usb. Lista vine din managerul de discuri, care la pornire putea scoate o partitie din
# liste cand pregatirea ei trecea de termen (Harddisk.retryLater o reia acum). Ca pagina si ecranul sa nu mai spuna
# "niciun disc" cand un disc e montat: lista ia si discurile montate in /media sau /run/media pe care managerul nu le
# stie (din /proc/mounts si /sys), iar interfata le pune singura inapoi in manager (reparaNecunoscute, fara nicio
# apasare); in jurnal, un rand pentru fiecare disc sarit, cu motivul (o data pe disc si motiv).

PAUZA_REPARARE_S = 60
# 16.11 (DRG2, darog69 789 #2882, Vu+ Duo4K): o partitie pe care managerul o tine fara is_hotplug (partitie fixa) nu are
# alegeri de loc; daca e montata in /media sau /run/media si e pe USB/SATA/card, apare totusi in lista (ca disc necunoscut),
# nu se mai sare in tacere. Cele sarite pentru alt motiv (loc de pornire, nici USB nici SATA) raman sarite.
MOTIV_FARA_HOTPLUG = "nu vine din lista de discuri conectate (is_hotplug)"
_jurnalizate = set()
_reparate = {}


def _jurnalOData(dispozitiv, motiv):
	if (dispozitiv, motiv) in _jurnalizate:
		return
	_jurnalizate.add((dispozitiv, motiv))
	_jurnal("%s: %s" % (dispozitiv, motiv))


def _felFizic(dispozitiv):
	"""(usb, sata, sd, physdev) dupa calea din /sys a discului, ca HarddiskManager.addHotplugPartition."""
	H = _H()
	try:
		# path al lui Harddisk (acelasi os.path pe receptor; probele ii dau sistemul de fisiere fals)
		physdev = getattr(H, "path", os.path).realpath("/sys/block/" + discul(dispozitiv) + "/device")[4:]
	except (OSError, ValueError):
		physdev = ""
	usb = "/usb" in physdev
	sata = not usb and H.isSataPhysdev(physdev)
	sd = not usb and not sata and H.isSdCard(dispozitiv)
	return usb, sata, sd, physdev


def _montateNecunoscute(cunoscute, hm):
	"""{dispozitiv: [locuri]}: partitiile de stick/disc/card montate in /media sau /run/media pe care managerul nu le are
	(nici in partitions, nici in pending). Nu discul de pe care porneste imaginea, nu un loc de pornire, nu memoria interna."""
	H = _H()
	locuri = {}
	for sursa, loc in H.readMounts():
		if not sursa.startswith("/dev/"):
			continue
		dev = sursa[len("/dev/"):]
		if not dispozitivBun(dev) or dev in cunoscute:
			continue
		if not (loc.startswith(MEDIA) or loc.startswith(H.SYSTEM_MOUNT_BASE)):
			continue
		if loc not in locuri.setdefault(dev, []):
			locuri[dev].append(loc)
	# numele stabile facute ca legaturi (cand montarea bind n-a mers): /media/hdd -> /run/media/hdd-sda1
	esteAlias = getattr(H, "isAliasOf", None)
	try:
		nume_media = sorted(getattr(H, "listdir", os.listdir)(MEDIA)) if esteAlias is not None else []
	except OSError:
		nume_media = []
	for dev, l in locuri.items():
		for nume in nume_media:
			alias = MEDIA + nume
			try:
				if alias not in l and any(esteAlias(alias, x) for x in list(l)):
					l.append(alias)
			except Exception as e:
				_jurnalOData(alias, "legatura necitita: %r" % (e,))
	rez = {}
	for dev, l in sorted(locuri.items()):
		if discul(dev) == getattr(hm, "system_disk", None) or H.isBootSlot(dev):
			continue
		usb, sata, sd, physdev = _felFizic(dev)
		if not (usb or sata or sd):
			_jurnalOData(dev, "montat in %s, dar nu e stick, disc USB/SATA sau card SD (physdev %s)" % (", ".join(l), physdev or "?"))
			continue
		_jurnalOData(dev, "montat in %s, dar managerul de discuri nu-l are in liste" % ", ".join(l))
		rez[dev] = sorted(l, key=lambda x: (not x.startswith(MEDIA), x))
	return rez


def reparaNecunoscute(randuri, hm=None, acum=None):
	"""Pe firul interfetei, dupa lista(): discurile montate pe care managerul nu le stie (randurile "necunoscut") intra din
	nou in lista lui, ca la punerea stickului, fara fereastra de cautare a fisierelor; cel mult o data pe minut pentru acelasi
	disc. Intoarce dispozitivele puse din nou."""
	hm = _hm(hm)
	acum = time.monotonic() if acum is None else acum
	puse = []
	for r in randuri or []:
		dev = r.get("dispozitiv")
		if not r.get("necunoscut") or not dispozitivBun(dev) or inLucru():
			continue
		if dev in _reparate and acum - _reparate[dev] < PAUZA_REPARARE_S:
			continue
		_reparate[dev] = acum
		try:
			if dev in hm.pending or any(getattr(p, "device", None) == dev for p in hm.partitions):
				continue
			hm.addHotplugPartition(dev)
			p = hm.pending.get(dev)
			if p is None:
				_jurnal("%s: managerul de discuri nu l-a primit inapoi" % dev)
				continue
			p.notify_mount = False
			hm.scheduleMount(dev, 500)
			_jurnal("%s: pus din nou in lista managerului de discuri" % dev)
			puse.append(dev)
		except Exception as e:
			_jurnal("%s: punerea inapoi in lista: %r" % (dev, e))
	return puse


def _numele(p, dispozitiv, eticheta):
	try:
		from Components.HdsLocInregistrari import numeDispozitiv
		return numeDispozitiv(getattr(p, "description", ""), dispozitiv, getattr(p, "removable", None), eticheta)
	except Exception:
		return "%s (%s)" % (eticheta or _("USB Stick"), dispozitiv)


def lista(hm=None):
	"""Randurile ecranului (pe un fir: citeste /dev, /sys si /proc/mounts). Fiecare: dispozitiv, nume, eticheta, marime,
	sistem, stare (montat / se_monteaza / demontat), loc (/media/<nume> de acum), ales (numele tinut minte, gol =
	Automat), alegeri [[valoare, text]], sd, poate_demonta, poate_monta."""
	hm = _hm(hm)
	H = _H()
	for dev in list(_demontate):
		if not _prezent(dev):
			_demontate.pop(dev, None)
	rez = []
	sarite = {}
	partitii = _partitiiAle(hm, sarite)
	for dev, motiv in sorted(sarite.items()):
		_jurnalOData(dev, "sarit din lista: %s" % motiv)
	for dev, p in sorted(partitii.items()):
		if dev in _demontate:
			continue
		eticheta = H.deviceLabel(dev)
		mediu, sd = _feluri(p)
		listat = p in hm.partitions
		loc = (getattr(p, "mountpoint", "") or "") if listat else ""
		info = hm.mediaNameInfo(dev) if mediu else {"valoare": "", "alegeri": []}
		alegeri = []
		for valoare, text in info.get("alegeri") or []:
			alegeri.append([valoare, _("Automat") if not valoare else text])
		rez.append({"dispozitiv": dev, "nume": _numele(p, dev, eticheta), "eticheta": eticheta, "marime": _marime(dev),
			"sistem": H.deviceFsType(dev), "stare": "montat" if listat else "se_monteaza", "loc": loc,
			"locuri": [m for m in H.findMountpoints(dev)], "ales": info.get("valoare", ""), "alegeri": alegeri, "sd": sd,
			"poate_demonta": listat, "poate_monta": False})
	for dev, d in sorted(_demontate.items()):
		rez.append({"dispozitiv": dev, "nume": d["nume"], "eticheta": d["eticheta"], "marime": _marime(dev),
			"sistem": H.deviceFsType(dev), "stare": "demontat", "loc": "", "locuri": H.findMountpoints(dev),
			"ales": "", "alegeri": [], "sd": d["sd"], "poate_demonta": False, "poate_monta": not d["sd"]})
	try:
		sarite_de_tot = set(d for d, motiv in sarite.items() if motiv != MOTIV_FARA_HOTPLUG)
		necunoscute = _montateNecunoscute(set(partitii) | set(_demontate) | sarite_de_tot, hm)
	except Exception as e:
		_jurnal("discurile montate necunoscute: %r" % (e,))
		necunoscute = {}
	for dev, locuri in necunoscute.items():
		eticheta = H.deviceLabel(dev)
		sd = _felFizic(dev)[2]
		loc = next((x for x in locuri if x.startswith(MEDIA)), locuri[0])
		rez.append({"dispozitiv": dev, "nume": _numele(None, dev, eticheta), "eticheta": eticheta, "marime": _marime(dev),
			"sistem": H.deviceFsType(dev), "stare": "montat", "loc": loc, "locuri": locuri, "ales": "", "alegeri": [],
			"sd": sd, "poate_demonta": False, "poate_monta": False, "necunoscut": True})
	return rez


def textStare(rand):
	"""Starea unui rand, in cuvinte."""
	if rand["stare"] == "demontat":
		if rand.get("sd"):
			return _("Demontat. Poți scoate cardul; ca să-l montezi la loc, scoate-l și pune-l din nou.")
		return _("Demontat. Poți scoate discul în siguranță.")
	if rand["stare"] == "se_monteaza":
		return _("Se montează...")
	if rand.get("loc"):
		return _("Montat în %s") % rand["loc"]
	return _("Montat")


# ------------------------------------------------------------------ cine foloseste discul

def motivRefuz(dispozitiv, fel, hm=None, folosire=None):
	"""Textul refuzului, sau "" cand se poate. Pe firul interfetei (inregistrarile si timeshift-ul enigma2). `folosire`:
	[(cheie, text)] din HdsDiscuri.folosire, citit pe fir (numai la demontare)."""
	hm = _hm(hm)
	if fel == MONTARE:
		return ""
	try:
		ocupat = hm.mediaNameBusy(dispozitiv)
	except Exception as e:
		_jurnal("mediaNameBusy %s: %r" % (dispozitiv, e))
		ocupat = False
	if ocupat:
		return _("O înregistrare sau timeshift-ul scrie acum pe acest disc. Încearcă după ce se termină.")
	for cheie, text in folosire or []:
		if cheie in ("swap", "inregistrare", "timeshift"):
			return text
	return ""


def _citesteFolosire(dispozitiv, inregistrari):
	from Components import HdsDiscuri
	return HdsDiscuri.folosire(discul(dispozitiv), inregistrari)


def _inregistrari():
	try:
		from Components import HdsDiscuri
		return HdsDiscuri.stareInregistrari()
	except Exception:
		return {}


# ------------------------------------------------------------------ lucrul pe disc (pe fir)

def _ruleaza(argumente, termen=TERMEN_UMOUNT_S):
	"""(cod, iesirea) fara shell; HDS_PROBA_MOUNT=1 (probele) numai scrie comanda."""
	if os.environ.get("HDS_PROBA_MOUNT"):
		_jurnal("PROBA: %s" % " ".join(argumente))
		return 0, ""
	try:
		p = subprocess.run(list(argumente), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=termen)
		return p.returncode, p.stdout.decode("utf-8", "replace").strip()
	except (OSError, ValueError, subprocess.SubprocessError) as e:
		return 1, str(e)


def demonteazaPeFir(dispozitiv, ruleaza=None, montari=None):
	"""sync, apoi umount pe fiecare loc al partitiei: intai numele din /media (montarile bind), apoi montarea sistemului
	din /run/media; cele mai adanci intai. -> {"bun", "demontate", "iesire"}. Fara -l: un fisier deschis opreste demontarea."""
	ruleaza = ruleaza or _ruleaza
	if montari is None:
		montari = _H().findMountpoints(dispozitiv)
	ruleaza(("sync",))
	demontate = []
	for loc in sorted(montari, key=lambda x: (not x.startswith(MEDIA), -len(x))):
		if loc in ("/", ""):
			continue
		cod, iesire = ruleaza(("umount", loc))
		if cod != 0:
			_jurnal("umount %s: %s %s" % (loc, cod, iesire))
			return {"bun": False, "demontate": demontate, "iesire": iesire}
		demontate.append(loc)
	return {"bun": True, "demontate": demontate, "iesire": ""}


# ------------------------------------------------------------------ dupa disc: caile inregistrarilor si ghidul TV

def mutaCaile(vechi, nou, muta=None, ghid=None):
	"""Dosarele inregistrarilor, programarile si locul ghidului TV merg dupa disc, de pe `vechi` pe `nou` (/media/...).
	/hdd e legatura spre /media/hdd: cand discul pleaca de pe /media/hdd, si caile /hdd/... merg dupa el."""
	if not vechi or not nou or vechi.rstrip("/") == nou.rstrip("/"):
		return []
	if muta is None:
		from Components.HdsLocInregistrari import mutaCaiMedia as muta
	schimbate = []
	try:
		schimbate += muta(vechi, nou)
		if vechi.rstrip("/") == HDD:
			schimbate += muta("/hdd", nou)
	except Exception as e:
		_jurnal("caile %s -> %s: %r" % (vechi, nou, e))
	if (ghid or _mutaGhidul)(vechi.rstrip("/"), nou.rstrip("/")):
		schimbate.append("ghid")
	return schimbate


def _mutaGhidul(vechi, nou):
	try:
		from Components.config import config
		from Components import HdsEpgSalvare
		el = getattr(config.misc, "hds_epg_loc", None)
		if el is None or el.value != vechi:
			return False
		el.setChoices(HdsEpgSalvare.alegeri(nou), default=HdsEpgSalvare.INTERN)
		el.value = nou
		el.save()
		return True
	except Exception as e:
		_jurnal("ghidul %s -> %s: %r" % (vechi, nou, e))
		return False


# ------------------------------------------------------------------ lucrarea (una odata)

def stareLucru():
	l = _stare["lucru"]
	if l is not None and l["stare"] != IN_LUCRU and time.time() - (l.get("sfarsit") or 0) > VARSTA_LUCRU_S:
		_stare["lucru"] = l = None
	return l


def inLucru():
	l = _stare["lucru"]
	return l is not None and l["stare"] == IN_LUCRU


def _termina(l, bun, mesaj):
	if _stare["lucru"] is not l:
		return
	l.update(stare=GATA if bun else EROARE, mesaj=mesaj, sfarsit=time.time())
	_jurnal("%s %s: %s" % (l["fel"], l["dispozitiv"], mesaj))
	ceas = _stare.get("ceas")
	if ceas is not None:
		ceas.stop()


def _ceasNou(functie):
	from enigma import eTimer
	t = eTimer()
	t.callback.append(functie)
	return t


def porneste(fel, dispozitiv, nume=None, hm=None, cere=None, ceas=None):
	"""Porneste lucrarea (pe firul interfetei). -> (bun, mesaj): bun=False cu motivul cand nu porneste. Starea se
	citeste cu stareLucru() (ecranul si pagina o urmaresc)."""
	hm = _hm(hm)
	if fel not in FELURI or not dispozitivBun(dispozitiv):
		return False, _("Discul ales nu mai este conectat. Alege din nou.")
	if inLucru():
		return False, _("Se lucrează deja la un disc. Așteaptă să se termine.")
	if fel == MONTARE:
		if dispozitiv not in _demontate:
			return False, _("Discul ales nu mai este conectat. Alege din nou.")
	elif dispozitiv not in _partitiiAle(hm):
		return False, _("Discul ales nu mai este conectat. Alege din nou.")
	if fel == LOC and not isinstance(nume, str):
		return False, _("Alege un nume din listă.")
	motiv = motivRefuz(dispozitiv, LOC if fel == LOC else fel, hm)
	if motiv:
		return False, motiv
	if cere is None:
		from Components.HdsStocareDisc import cere
	_stare["gen"] += 1
	l = {"fel": fel, "dispozitiv": dispozitiv, "nume": nume, "stare": IN_LUCRU, "mesaj": _("Se lucrează..."),
		"timp": time.time(), "sfarsit": None, "gen": _stare["gen"], "pas": "fir", "pana": 0, "vechi": ""}
	_stare["lucru"] = l
	cheie = ("montare-discuri", l["gen"])
	if fel == LOC:
		pana = time.monotonic() + TERMEN_FIR_S
		functie = lambda: hm.setMediaName(dispozitiv, nume, valid=lambda: time.monotonic() < pana)
	elif fel == DEMONTARE:
		inregistrari = _inregistrari()
		def functie():
			# pe fir: nimic din enigma2 (mediaNameBusy s-a intrebat mai sus, pe firul interfetei)
			folosire = _citesteFolosire(dispozitiv, inregistrari)
			refuz = next((text for cheie, text in folosire if cheie in ("swap", "inregistrare", "timeshift")), "")
			if refuz:
				return {"refuz": refuz}
			return demonteazaPeFir(dispozitiv)
	else:
		functie = lambda: None
	l["cheie"] = cheie
	l["cere"] = cere
	cere(cheie, functie, termen=TERMEN_FIR_S, varsta=VARSTA_LUCRU_S)
	if ceas is None:
		ceas = _ceasNou(lambda: pas(hm))
	_stare["ceas"] = ceas
	ceas.start(PAS_MS, False)
	return True, l["mesaj"]


def pas(hm=None, stare=None, acum=None):
	"""Un pas al lucrarii, pe firul interfetei (eTimer-ul lui porneste, sau probele)."""
	hm = _hm(hm)
	l = _stare["lucru"]
	if l is None or l["stare"] != IN_LUCRU:
		ceas = _stare.get("ceas")
		if ceas is not None:
			ceas.stop()
		return
	acum = time.monotonic() if acum is None else acum
	if l["pas"] == "fir":
		if stare is None:
			from Components.HdsStocareDisc import stare
		rez = stare(l["cheie"])
		if rez is None or rez["stare"] == "asteapta":
			return
		if rez["stare"] != "gata":
			_termina(l, False, _("Discul nu răspunde la timp. Încearcă din nou."))
			return
		_dupaFir(l, rez["valoare"], hm, acum)
	elif l["pas"] == "nume":
		_asteaptaNumele(l, hm, acum)


def _partitiaListata(hm, dispozitiv):
	return next((p for p in hm.partitions if getattr(p, "device", None) == dispozitiv and getattr(p, "is_hotplug", False)), None)


def _reintra(hm, dispozitiv, p):
	"""Discul iese si intra din nou in lista lui Harddisk, ca la scoaterea si punerea stickului: numele vechi din /media
	se scot (legaturile si montarile bind; montarea sistemului din /run/media ramane), iar planul de montare ii da numele
	ales (Harddisk.freeMediaName il ia intai pe cel ales)."""
	physdev = getattr(p, "physdev", None) if p is not None else None
	hm.removeHotplugPartition(dispozitiv)
	hm.addHotplugPartition(dispozitiv, physdev or None)
	hm.scheduleMount(dispozitiv, INTARZIERE_MONTARE_MS)


def _dupaFir(l, valoare, hm, acum):
	dispozitiv = l["dispozitiv"]
	if l["fel"] == LOC:
		valoare = valoare or {}
		if not valoare.get("result"):
			_termina(l, False, valoare.get("message") or _("Numele nu se poate schimba acum."))
			return
		p = _partitiaListata(hm, dispozitiv)
		if p is None:
			# inca se monteaza: numele ales il ia la anuntul montarii
			_termina(l, True, _("Locul a fost salvat. Discul îl primește când termină de montat."))
			return
		if motivRefuz(dispozitiv, LOC, hm):
			_termina(l, True, _("Locul a fost salvat. Se folosește la următoarea punere a discului (acum o "
				"înregistrare scrie pe el)."))
			return
		l["vechi"] = getattr(p, "mountpoint", "") or ""
		_reintra(hm, dispozitiv, p)
		l.update(pas="nume", pana=acum + TERMEN_NUME_S, mesaj=_("Se montează pe locul ales..."))
		return
	if l["fel"] == DEMONTARE:
		valoare = valoare or {}
		if valoare.get("refuz"):
			_termina(l, False, valoare["refuz"])
			return
		p = _partitiaListata(hm, dispozitiv) or _partitiiAle(hm).get(dispozitiv)
		if not valoare.get("bun"):
			# un fisier deschis: numele care apucasera sa se demonteze se pun la loc
			if valoare.get("demontate"):
				_reintra(hm, dispozitiv, p)
			_termina(l, False, _("Discul e folosit de un program și nu s-a putut demonta. Oprește redarea sau "
				"pluginul care îl folosește și încearcă din nou."))
			return
		H = _H()
		eticheta = H.deviceLabel(dispozitiv)
		_demontate[dispozitiv] = {"nume": _numele(p, dispozitiv, eticheta), "eticheta": eticheta,
			"sd": bool(getattr(p, "sd", False)), "physdev": getattr(p, "physdev", None), "loc": getattr(p, "mountpoint", "")}
		hm.removeHotplugPartition(dispozitiv)
		# un nume bind demontat lasa un dosar gol in /media: fara el, /hdd/movie ar duce in memoria interna
		for loc in valoare.get("demontate") or []:
			if loc.startswith(MEDIA):
				hm.removeEmptyDir(loc)
		mesaj = _("Discul a fost demontat. Îl poți scoate în siguranță.")
		if _ghidulPe(getattr(p, "mountpoint", "")):
			mesaj += " " + _("Ghidul TV se păstra pe el; până îl pui la loc, receptorul îl ține în memoria internă.")
		_termina(l, True, mesaj)
		return
	# MONTARE
	d = _demontate.pop(dispozitiv, None) or {}
	hm.addHotplugPartition(dispozitiv, d.get("physdev") or None)
	hm.scheduleMount(dispozitiv, 500)
	l.update(pas="nume", pana=acum + TERMEN_NUME_S, mesaj=_("Se montează..."))


def _ghidulPe(loc):
	try:
		from Components.config import config
		return bool(loc) and config.misc.hds_epg_loc.value.rstrip("/") == loc.rstrip("/")
	except Exception:
		return False


def _asteaptaNumele(l, hm, acum):
	dispozitiv = l["dispozitiv"]
	p = _partitiaListata(hm, dispozitiv)
	if p is None:
		if acum >= l["pana"]:
			_termina(l, False, _("Discul nu s-a montat la timp. Scoate-l și pune-l din nou."))
		return
	nou = getattr(p, "mountpoint", "") or ""
	schimbate = mutaCaile(l["vechi"], nou) if l["vechi"] else []
	if l["fel"] == MONTARE:
		_termina(l, True, _("Discul a fost montat în %s.") % nou)
		return
	mesaj = _("Discul este acum în %s.") % nou
	if schimbate:
		mesaj += " " + _("Dosarele înregistrărilor și locul ghidului TV merg după el.")
	_termina(l, True, mesaj)


def textLucru(l=None):
	l = l if l is not None else stareLucru()
	return (l or {}).get("mesaj", "")
