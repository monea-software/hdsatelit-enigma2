# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDriverLipsa.py: omul baga un stick Wi-Fi sau un adaptor de retea USB al carui driver nu e in imagine; receptorul ia
# singur driverul din feedul nostru, il porneste si spune pe ecran cand e gata, fara nimic de ales (0.7.4, 11.11.2026:
# driverele in feed, nu in imagine, instalate automat; regula "cat mai simplu").
#
# Harta ID USB -> pachet: HARTA (data/hds-drivere-pachete.json, in /usr/share/enigma2), FACUTA de unealta din pachetele
# construite (unealta harta_drivere.py din depozitul de constructie: aliasurile din sectiunea .modinfo a
# modulelor, pe fiecare masina), nu scrisa de mana. Numai un pachet din harta, pe masina receptorului (arhitecturile din
# /etc/opkg/arch.conf), ajunge la opkg.
#
# Cand:
#   - Plugins/SystemPlugins/Hotplug: evenimentul nucleului "add" pe o interfata USB (DEVTYPE=usb_interface, cu MODALIAS);
#     dupa ASTEPTARE_MS, daca interfata tot n-are driver (udev a incarcat deja modulul, daca era pe receptor), se cauta in
#     harta; "add" pe dispozitivul intreg (DEVTYPE=usb_device) pentru stickurile care pornesc ca CD (COMUTARE);
#   - la pornire, o singura trecere prin /sys/bus/usb/devices (stickul ramas in mufa), dupa INTARZIERE_PORNIRE_MS.
# Cum: aceeasi lucrare opkg ca la Extensii si la modulele Python lipsa (Components/HdsExtensiiLucru.Lucrare, acelasi jurnal
# hds-extensii.log), una odata; cu opkg ocupat se reincearca peste PAS_ASTEPTARE_MS. Listele surselor noastre lipsa sau
# vechi: intai opkg update. Pachetul se instaleaza numai daca cea mai noua versiune e intr-un feed HD Satelit
# (Components/HdsModuleLipsa.provenienta). Dupa instalare (postinst-ul modulului face depmod) se scrie "add" in uevent-ul
# interfetei: udev incarca modulul (80-drivers.rules), fara sa scoata omul stickul; la COMUTARE, regula udev a stickului
# CD cheama usb_modeswitch, stickul revine cu ID-ul lui Wi-Fi, iar driverul vine la evenimentul urmator.
# Fara internet (nu se descarca listele): se reincearca singur la PAS_FARA_INTERNET_MS, de cel mult MAX_ESECURI_LISTE ori
# (o ora); o instalare cazuta cu listele inca proaspete se reia o data, dupa o descarcare noua a listelor (care, fara
# internet, cade si intra in aceeasi reincercare). Dupa ora, pachetul nu ramane tinut minte: o conectare noua sau pornirea
# il cer din nou.
# Pe ecran: mesajul mic al imaginii (Screens/HdsAnuntRetea), nemodal. In pagina web: /retea, cardul "Adaptoare USB"
# (stareWeb(): ce se instaleaza acum si ultimele mesaje, aceleasi texte ca pe televizor).
# Tunerele DVB pe USB (VU+ Turbo / Turbo2 pe Vu+, "fel": "tuner" in harta, 12.11.2026): puntea vtuner
# (lib/dvb/hdsvtuner.cpp) leaga tunerele USB numai la pornirea interfetei, deci un tuner bagat din mers (driverul abia
# instalat sau deja pe receptor) apare in Setari tunere dupa repornirea interfetei: receptorul spune asta si intreaba o
# data pe sesiune "Repornesc interfata acum?" (Da: TryQuitMainloop 3, care intreaba singur daca o inregistrare e in curs;
# in standby intrebarea vine la trezire); in pagina web, butonul din cardul "Adaptoare USB" (repornesteInterfata).
# Fara internet, din fisierul de completari de pe stick (pasul 4d, 12.11.2026): cand listele nu se descarca sau pachetul
# nu e in listele online, daca pe un stick e fisierul hdsatelit-<baza>-<model>-completari.zip (sau dosarul dezarhivat),
# driverul stickului bagat (pachetul din harta si "cu") se ia din el, cu aceeasi verificare ca feedul online
# (Components/HdsLimbaRestaurare.instaleazaDinStick: stare.json semnat, indexurile semnate, sumele); numai driverul
# acestui stick, nu toate driverele din fisier. La bagarea stickului cu fisierul (stickNou, din ascultatorul hotplug al
# lui HdsLimbaRestaurare), stickurile Wi-Fi fara driver se cauta din nou si driverul lor vine de pe stick.
# O singura incercare pe pachet si sesiune (fara bucla). Nu importa nimic din enigma la incarcare (probele de pe PC);
# RADACINA pune un dosar in fata cailor de sistem, numai la probe. Nu arunca.
import fnmatch
import json
import os
import re
import time

RADACINA = ""
HARTA = "/usr/share/enigma2/hds-drivere-pachete.json"
OPKG_INFO = "/var/lib/opkg/info"
ASTEPTARE_MS = 4000
INTARZIERE_PORNIRE_MS = 25000
PAS_ASTEPTARE_MS = 60000
PAS_URMATOR_MS = 1500
PAS_FARA_INTERNET_MS = 300000
MAX_ESECURI_LISTE = 12
VERIFICARE_DUPA_MS = 5000
DURATA_MESAJ_MS = 9000
MAX_ULTIMELE = 8
REPORNIRE_DUPA_MS = 1500
# stickurile care pornesc ca CD cu driverul pe el (Realtek "ZeroCD"); regula udev a imaginii (40-realtek-zerocd.rules)
# le comuta cu usb_modeswitch, daca e instalat
COMUTARE = {"0bda:1a2b": "usb-modeswitch"}

_NUME_PACHET = re.compile(r"^[a-z0-9][a-z0-9+.\-]{0,120}\Z")
_MODALIAS = re.compile(r"^usb:v[0-9A-F]{4}p[0-9A-F]{4}[0-9A-Za-z*]{0,80}\Z")

_harta = [None]
_asteapta = {}       # devpath -> modalias, in asteptarea driverului de la udev
_coada = []          # [{"pachet", "nume", "dispozitive": {devpath: modalias}}]
_rezultat = {}       # pachet -> {"stare": instalat | esuat | lipsa | refuzat | nu_porneste, "motiv"}
_ultimele = []       # [{"cand", "text", "stare"}] pentru pagina web, cel mult MAX_ULTIMELE
_stare = {"sesiune": None, "pornit": False, "ceas": None, "lucrare": None, "liste": False, "esecuri_liste": 0,
	"masina": None, "ceasuri": [], "forteaza": False, "tuner": None, "stick": None}


def N_(text):
	return text


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _cuNume(nume, fraza, frazaUsb, *alte):
	"""Mesajul despre dispozitivul „nume”: fraza (primul %s = numele adevarat al stickului, un nume propriu) sau, cand
	stickul nu-si spune numele si a primit bucata „adaptorul USB”, frazaUsb, scrisa intreaga. In islandeza, finlandeza si
	estoniana substantivul se declina dupa locul din fraza, deci bucata tradusa o singura data nu se potriveste in toate
	frazele. alte = ceilalti parametri ai frazei (in frazaUsb fara numele)."""
	if nume == _t("adaptorul USB"):
		return frazaUsb % alte if alte else frazaUsb
	return fraza % ((nume,) + alte)


def _jurnal(text):
	print("[HdsDriverLipsa] %s" % text)


def _c(cale):
	return RADACINA + cale if RADACINA else cale


def _citeste(cale):
	try:
		with open(_c(cale), encoding="utf-8", errors="replace") as f:
			return f.read().strip()
	except OSError:
		return ""


# ---------------------------------------------------------------- harta

def harta():
	"""{pachet: {"nume", "alias": [...], "masini": [...]}} din HARTA, citita o data; {} cand lipseste sau e stricata"""
	if _harta[0] is None:
		h = {}
		try:
			with open(_c(HARTA), encoding="utf-8") as f:
				date = json.load(f)
			if date.get("format") == 1 and isinstance(date.get("drivere"), dict):
				for p, d in date["drivere"].items():
					if _NUME_PACHET.match(p) and isinstance(d, dict) and isinstance(d.get("alias"), list):
						h[p] = {"nume": str(d.get("nume") or p), "alias": [a for a in d["alias"] if isinstance(a, str)],
							"masini": [m for m in d.get("masini") or [] if isinstance(m, str)],
							# firmware-ul cerut de modul (pachetul care il pune), instalat odata cu driverul
							"cu": [x for x in d.get("cu") or [] if isinstance(x, str) and _NUME_PACHET.match(x)],
							# "tuner": un tuner DVB (apare in Setari tunere dupa repornirea interfetei)
							"fel": str(d.get("fel") or "")}
		except (OSError, ValueError, AttributeError) as e:
			_jurnal("harta %s: %s" % (HARTA, e))
		_harta[0] = h
	return _harta[0]


def masina():
	"""arhitectura masinii receptorului (din arch.conf) care apare in harta: u57, sf8008, gbmv200 ...; None altfel"""
	if _stare["masina"] is None:
		toate = set()
		for d in harta().values():
			toate.update(d["masini"])
		gasita = ""
		try:
			from Components import HdsPachete
			arh = HdsPachete.citeste_configurarea(RADACINA or "/").arhitecturi
			gasita = next((a for a in sorted(arh, key=lambda x: -arh[x]) if a in toate), "")
		except Exception as e:
			_jurnal("arch.conf: %r" % (e,))
		_stare["masina"] = gasita
	return _stare["masina"] or None


def pachetePentru(modalias):
	"""pachetele din harta care prind modaliasul unei interfete USB, pe masina receptorului"""
	m = masina()
	if not m or not modalias or not _MODALIAS.match(modalias):
		return []
	return [p for p, d in sorted(harta().items()) if m in d["masini"] and any(fnmatch.fnmatchcase(modalias, a) for a in d["alias"])]


def instalat(pachet):
	return os.path.exists(_c("%s/%s.control" % (OPKG_INFO, pachet)))


def numeDispozitiv(devpath, pachet=None):
	"""numele stickului, cum il spune el pe USB (producatorul si produsul); altfel cipul din harta"""
	baza = "/sys" + devpath
	for cale in (baza, os.path.dirname(baza)):
		produs = _citeste(cale + "/product")
		if produs:
			producator = _citeste(cale + "/manufacturer")
			if producator and producator.lower() not in produs.lower():
				produs = "%s %s" % (producator, produs)
			return produs[:60]
	if pachet and pachet in harta():
		return harta()[pachet]["nume"]
	return _t("adaptorul USB")


# ---------------------------------------------------------------- evenimentele USB

def eveniment(ev):
	"""Din Hotplug.handleEvent, pentru SUBSYSTEM == "usb"."""
	try:
		if ev.get("SUBSYSTEM") != "usb":
			return
		devpath = ev.get("DEVPATH") or ""
		if not devpath.startswith("/devices/"):
			return
		actiune = ev.get("ACTION")
		if actiune == "remove":
			_asteapta.pop(devpath, None)
			return
		if actiune != "add":
			return
		if ev.get("DEVTYPE") == "usb_interface" and ev.get("MODALIAS"):
			if not harta():
				return
			_asteapta[devpath] = ev["MODALIAS"]
			_intarzie(ASTEPTARE_MS, lambda: verifica(devpath))
		elif ev.get("DEVTYPE") == "usb_device":
			_comutare(devpath, ev.get("PRODUCT") or "")
	except Exception as e:
		_jurnal("eveniment: %r" % (e,))


def _idDinProdus(produs):
	"""PRODUCT=bda/1a2b/200 -> "0bda:1a2b" """
	b = produs.split("/")
	if len(b) < 2:
		return ""
	try:
		return "%04x:%04x" % (int(b[0], 16), int(b[1], 16))
	except ValueError:
		return ""


def _comutare(devpath, produs):
	pachet = COMUTARE.get(_idDinProdus(produs))
	if pachet is None:
		return None
	if instalat(pachet):
		return None
	return cere(pachet, devpath, "", numeDispozitiv(devpath))


def verifica(devpath, modalias=None, laPornire=False):
	"""Interfata USB fara driver dupa asteptare: pachetul din harta in coada (sau modulul deja instalat pornit din nou).
	laPornire: trecerea prin stickurile ramase in mufa la pornire (un tuner cu driver e deja legat de punte)."""
	try:
		modalias = modalias or _asteapta.pop(devpath, None)
		_asteapta.pop(devpath, None)
		baza = _c("/sys" + devpath)
		if not modalias or not os.path.isdir(baza):
			return None
		if os.path.exists(baza + "/driver"):
			if laPornire:
				return None
			# un tuner DVB pe USB cu driverul pe receptor, bagat din mers: puntea il leaga abia la repornirea interfetei
			tuner = next((p for p in pachetePentru(modalias) if harta()[p]["fel"] == "tuner"), None)
			if tuner:
				tunerConectat(numeDispozitiv(devpath, tuner))
			return None
		pachete = pachetePentru(modalias)
		if not pachete:
			return None
		gata = [p for p in pachete if instalat(p)]
		if gata and gata[0] not in _rezultat:
			# driverul e pe receptor (de pilda instalat cand stickul nu era in mufa): udev il incarca la un "add" nou
			_rezultat[gata[0]] = {"stare": "instalat", "motiv": ""}
			_jurnal("%s e instalat, interfata %s fara driver: add din nou" % (gata[0], devpath))
			_reincarca({devpath: modalias})
			return None
		# acelasi ID in doua drivere (produsul a iesit cu doua cipuri, ca 050d:7050 la rt2500usb si rt73usb): urmatorul
		# pachet numai cand cel dinainte e pe receptor si stickul tot n-are driver
		for p in pachete:
			if not instalat(p) and p not in _rezultat:
				return cere(p, devpath, modalias, numeDispozitiv(devpath, p))
		return None
	except Exception as e:
		_jurnal("verifica %s: %r" % (devpath, e))
		return None


def trecereLaPornire():
	"""Stickurile ramase in mufa la pornire: interfetele fara driver si stickurile CD."""
	n = 0
	try:
		dosar = _c("/sys/bus/usb/devices")
		for nume in sorted(os.listdir(dosar)):
			cale = os.path.join(dosar, nume)
			try:
				devpath = os.path.realpath(cale)[len(_c("/sys")):]
			except OSError:
				continue
			if os.path.exists(_c("/sys%s/bInterfaceNumber" % devpath)):
				# interfata (1-1:1.0): are modalias; dispozitivul intreg (1-1) are idVendor
				modalias = _citeste("/sys%s/modalias" % devpath)
				if modalias and verifica(devpath, modalias, laPornire=True):
					n += 1
			else:
				v, p = _citeste("/sys%s/idVendor" % devpath), _citeste("/sys%s/idProduct" % devpath)
				if v and p and _comutare(devpath, "%s/%s" % (v, p)):
					n += 1
	except OSError as e:
		_jurnal("trecerea la pornire: %s" % e)
	return n


def cere(pachet, devpath, modalias, nume):
	"""Pachetul in coada pentru dispozitivul de la devpath, sau None (deja incercat in sesiunea asta, nume rau)."""
	if not _NUME_PACHET.match(pachet or "") or pachet in _rezultat:
		return None
	el = next((x for x in _coada if x["pachet"] == pachet), None)
	if el is None:
		if not _coada and _stare["lucrare"] is None:
			_stare["esecuri_liste"] = 0
		el = {"pachet": pachet, "nume": nume, "dispozitive": {}, "incercari": 0}
		_coada.append(el)
		_jurnal("in coada: %s pentru %s (%s)" % (pachet, nume, modalias or devpath))
	el["dispozitive"][devpath] = modalias
	if _stare["pornit"]:
		_programeaza(PAS_URMATOR_MS)
	return pachet


# ---------------------------------------------------------------- lucrul, unul odata

def porneste(session):
	"""Din Hotplug (autostart, cu sesiunea): trecerea la pornire si coada incep dupa INTARZIERE_PORNIRE_MS."""
	_stare["sesiune"] = session
	if _stare["pornit"]:
		return
	_stare["pornit"] = True
	_intarzie(INTARZIERE_PORNIRE_MS, _dupaPornire)


def _dupaPornire():
	if harta():
		trecereLaPornire()
	if _coada:
		_programeaza(PAS_URMATOR_MS)


def _intarzie(ms, functie):
	try:
		from enigma import eTimer
	except ImportError:
		return
	t = eTimer()

	def gata():
		if t in _stare["ceasuri"]:
			_stare["ceasuri"].remove(t)
		functie()
	t.callback.append(gata)
	_stare["ceasuri"].append(t)
	t.start(ms, True)


def _programeaza(ms):
	try:
		from enigma import eTimer
	except ImportError:
		return
	if _stare["ceas"] is None:
		_stare["ceas"] = eTimer()
		_stare["ceas"].callback.append(_urmatorul)
	if not _stare["ceas"].isActive():
		_stare["ceas"].start(ms, True)


def _M():
	from Components import HdsModuleLipsa
	return HdsModuleLipsa


def _X():
	from Components import HdsExtensiiLucru
	return HdsExtensiiLucru


def _ocupat():
	try:
		X = _X()
		if X.lucrareInCurs() or X.descarcareInCurs():
			return True
	except Exception:
		pass
	try:
		return bool(_M()._opkgRuleaza())
	except Exception:
		return False


def _noteaza(text, stare):
	if not text:
		return
	_ultimele.insert(0, {"cand": int(time.time()), "text": text, "stare": stare})
	del _ultimele[MAX_ULTIMELE:]


def _mesaj(text, stare="lucru"):
	_noteaza(text, stare)
	s = _stare["sesiune"]
	if s is None or not text:
		return
	try:
		from Screens import HdsAnuntRetea
		HdsAnuntRetea.arata(s, text, "", DURATA_MESAJ_MS)
	except Exception as e:
		_jurnal("mesaj: %r" % (e,))


def _urmatorul():
	"""Primul pachet din coada: listele surselor, provenienta, lucrarea opkg. Chemat de ceas."""
	try:
		if not _coada or _stare["lucrare"] is not None:
			return
		if _ocupat():
			_programeaza(PAS_ASTEPTARE_MS)
			return
		el = _coada[0]
		M = _M()
		conf = M._configurare()
		if not _stare["liste"] and (_stare.get("forteaza") or M.listeVechi(conf)):
			_stare["liste"] = True
			_stare["forteaza"] = False
			_actualizeazaListele()
			return
		versiune, motiv = M.provenienta(el["pachet"], conf)
		if versiune is None:
			if motiv == "lipsa" and not _stare["liste"]:
				_stare["liste"] = True
				_actualizeazaListele()
				return
			# nu e in listele online: poate e in fisierul de completari de pe stick
			if motiv == "lipsa" and dinStick(el):
				return
			_coada.pop(0)
			if motiv == "lipsa":
				text = _cuNume(el["nume"], _t("Pentru %s nu există încă driver în feedul HD Satelit."),
					_t("Pentru adaptorul USB nu există încă driver în feedul HD Satelit."))
			else:
				text = _cuNume(el["nume"], _t("Driverul pentru %s are o versiune mai nouă în altă sursă; nu îl instalez singur."),
					_t("Driverul pentru adaptorul USB are o versiune mai nouă în altă sursă; nu îl instalez singur."))
			_rezultat[el["pachet"]] = {"stare": "lipsa" if motiv == "lipsa" else "refuzat", "motiv": text}
			_jurnal("%s nu se instaleaza: %s" % (el["pachet"], motiv))
			_mesaj(text, "eroare")
			_programeaza(PAS_URMATOR_MS)
			return
		_pornesteLucrarea(el, versiune)
	except Exception as e:
		_jurnal("urmatorul: %r" % (e,))


def _actualizeazaListele():
	X = _X()
	_jurnal("opkg update inainte de driver")
	d = X.pornesteDescarcarea()

	def gata(eveniment_, parametru):
		if eveniment_ == X.IpkgComponent.EVENT_DONE:
			d.removeCallback(gata)
			if parametru == 0:
				_stare["esecuri_liste"] = 0
				_programeaza(PAS_URMATOR_MS)
			else:
				_jurnal("opkg update: cod %s" % parametru)
				listaCazuta()
	d.addCallback(gata)


def listaCazuta():
	"""opkg update n-a mers (de obicei fara internet: omul are numai stickul Wi-Fi fara driver): se reincearca singur la
	PAS_FARA_INTERNET_MS (cand omul leaga cablul, driverul vine fara alt pas), de cel mult MAX_ESECURI_LISTE ori."""
	_stare["esecuri_liste"] += 1
	primul = _coada[0] if _coada else None
	# fara internet: driverul din fisierul de completari de pe stick, daca e unul
	if primul is not None and dinStick(primul):
		# urmatorul din coada incearca din nou listele (si, fara internet, tot stickul), nu „nu exista driver in feed”
		_stare["liste"] = False
		return
	if primul is not None and _stare["esecuri_liste"] == 1:
		_mesaj(_cuNume(primul["nume"], _t("Driverul pentru %s se ia din feedul HD Satelit, dar receptorul nu are internet acum. "
			"Leagă receptorul la internet prin cablu sau copiază pe un stick fișierul cu completările pentru receptorul tău, de "
			"pe pagina imaginii, și pune stickul în receptor: driverul se instalează singur."),
			_t("Driverul pentru adaptorul USB se ia din feedul HD Satelit, dar receptorul nu are internet acum. Leagă receptorul "
			"la internet prin cablu sau copiază pe un stick fișierul cu completările pentru receptorul tău, de pe pagina "
			"imaginii, și pune stickul în receptor: driverul se instalează singur.")), "asteapta")
	if _stare["esecuri_liste"] < MAX_ESECURI_LISTE:
		_stare["liste"] = False
		_programeaza(PAS_FARA_INTERNET_MS)
		return
	del _coada[:]
	_jurnal("listele surselor nu se descarca (%d incercari); la urmatoarea conectare sau pornire, din nou" % _stare["esecuri_liste"])
	_stare["esecuri_liste"] = 0
	_stare["liste"] = False


def planDriver(el, versiune):
	"""planul lucrarii opkg (Components/HdsExtensiiLucru.Lucrare) pentru driverul din coada"""
	X = _X()
	pachete = [el["pachet"]] + [x for x in harta().get(el["pachet"], {}).get("cu", []) if not instalat(x)]
	argumente = X.opkgArguments("install", pachete)
	if argumente is None:
		return None
	titlu = _cuNume(el["nume"], _t("driverul pentru %s"), _t("driverul pentru adaptorul USB"))
	return {"fel": "instaleaza", "titlu": titlu, "nume": titlu, "subtitlu": el["pachet"], "icoana": "altele", "randuri": [],
		"nota": "", "externe": [], "notaCuloare": "", "buton": N_("Instalează"), "argumente": argumente, "repornire": False,
		"pachete": pachete, "tinte": [{"nume": el["pachet"], "titlu": el["pachet"], "la": versiune, "de": "", "acces": False}],
		"automat": True}


def _pornesteLucrarea(el, versiune):
	X = _X()
	plan = planDriver(el, versiune)
	if plan is None:
		_coada.pop(0)
		_rezultat[el["pachet"]] = {"stare": "esuat", "motiv": _t("Numele pachetului nu este valid.")}
		return
	_stare["lucrare"] = el
	l = X.Lucrare(plan)

	def ascultator(eveniment_, *date):
		if eveniment_ == "gata":
			l.lasa(ascultator)
			dupaLucrare(el, l)
	l.asculta(ascultator)
	_jurnal("instalez %s %s pentru %s" % (el["pachet"], versiune, el["nume"]))
	_mesaj(_seInstaleaza(el["nume"]))
	l.porneste()


def _seInstaleaza(nume):
	return _cuNume(nume, _t("Se instalează driverul pentru %s."), _t("Se instalează driverul pentru adaptorul USB."))


def dupaLucrare(el, lucrare):
	"""Sfarsitul lucrarii opkg: stickul primeste driverul (add in uevent), apoi verificarea si mesajul."""
	try:
		if el in _coada:
			_coada.remove(el)
		_stare["lucrare"] = None
		rez = getattr(lucrare, "rezultat", None) or {}
		if not rez.get("reusit") and el.get("incercari", 0) < 1:
			# poate n-a fost internet (listele erau inca proaspete, deci nu s-au descarcat): intai listele, apoi din nou
			el["incercari"] = el.get("incercari", 0) + 1
			_coada.insert(0, el)
			_stare["liste"] = False
			_stare["forteaza"] = True
			_jurnal("%s n-a mers (%s): listele din nou, apoi o incercare" % (el["pachet"], rez.get("stare")))
			return
		if not rez.get("reusit"):
			motiv = rez.get("stare") or _t("Operațiunea nu a reușit.")
			_rezultat[el["pachet"]] = {"stare": "esuat", "motiv": motiv}
			_mesaj(_cuNume(el["nume"], _t("Driverul pentru %s nu s-a instalat: %s"),
				_t("Driverul pentru adaptorul USB nu s-a instalat: %s"), motiv), "eroare")
			return
		_rezultat[el["pachet"]] = {"stare": "instalat", "motiv": ""}
		_jurnal("%s instalat pentru %s" % (el["pachet"], el["nume"]))
		_reincarca(el["dispozitive"])
		if el["pachet"] in COMUTARE.values():
			# stickul CD se comuta si revine cu alt ID: driverul lui vine la evenimentul urmator, fara mesaj aici
			return
		_intarzie(VERIFICARE_DUPA_MS, lambda: verificaDupa(el))
	except Exception as e:
		_jurnal("dupaLucrare: %r" % (e,))
	finally:
		if _coada:
			_programeaza(PAS_URMATOR_MS)


def _reincarca(dispozitive):
	""""add" in uevent-ul fiecarei interfete: nucleul trimite evenimentul din nou, udev incarca modulul nou instalat
	(80-drivers.rules) sau comuta stickul CD (40-realtek-zerocd.rules)."""
	for devpath in dispozitive:
		try:
			with open(_c("/sys%s/uevent" % devpath), "w") as f:
				f.write("add\n")
		except OSError as e:
			_jurnal("uevent %s: %s" % (devpath, e))


def verificaDupa(el):
	"""dupa instalare: macar o interfata a stickului are acum driver?"""
	merg = [d for d in el["dispozitive"] if os.path.exists(_c("/sys%s/driver" % d))]
	if merg and harta().get(el["pachet"], {}).get("fel") == "tuner":
		tunerConectat(el["nume"])
		return True
	if merg or not el["dispozitive"]:
		_mesaj(_cuNume(el["nume"], _t("%s este gata de folosit."), _t("Adaptorul USB este gata de folosit.")), "gata")
		return True
	ramase = [d for d in el["dispozitive"] if os.path.isdir(_c("/sys" + d))]
	if not ramase:
		# stickul a fost scos intre timp: driverul ramane instalat, merge la urmatoarea conectare
		_noteaza(_cuNume(el["nume"], _t("Driverul pentru %s s-a instalat."), _t("Driverul pentru adaptorul USB s-a instalat.")),
			"gata")
		return True
	_rezultat[el["pachet"]] = {"stare": "nu_porneste", "motiv": ""}
	# alt driver pentru acelasi ID (alt cip sub acelasi nume de produs): il incearca pe el, fara sa scoata omul stickul
	urmatorul = [d for d in ramase if verifica(d, el["dispozitive"].get(d))]
	if urmatorul:
		return False
	_mesaj(_cuNume(el["nume"], _t("Driverul pentru %s s-a instalat, dar adaptorul nu pornește. Scoate-l și bagă-l din nou."),
		_t("Driverul pentru adaptorul USB s-a instalat, dar adaptorul nu pornește. Scoate-l și bagă-l din nou.")), "eroare")
	return False


# ---------------------------------------------------------------- fara internet: fisierul de completari de pe stick

def _L():
	from Components import HdsLimbaRestaurare
	return HdsLimbaRestaurare


class _Rezultat(object):
	"""rezultatul instalarii de pe stick, in forma lucrarii opkg (rezultat = {"reusit", "stare"}) cerute de dupaLucrare"""

	def __init__(self, rezultat):
		self.rezultat = rezultat


def dinStick(el):
	"""Driverul din coada (pachetul si "cu"), din fisierul de completari de pe stick, pe fir separat; False cand pe niciun
	stick nu e un fisier de completari (atunci ramane calea obisnuita: internetul)."""
	try:
		L = _L()
		if not L.candidatiStick(RADACINA or "/", toate=True):
			return False
		from Components.HdsImportSurse import Lucrare
	except Exception as e:
		_jurnal("stick: %r" % (e,))
		return False
	pachete = [el["pachet"]] + [x for x in harta().get(el["pachet"], {}).get("cu", []) if not instalat(x)]
	_stare["lucrare"] = el
	_jurnal("%s din fisierul de completari de pe stick, pentru %s" % (el["pachet"], el["nume"]))
	_mesaj(_cuNume(el["nume"], _t("Am găsit completările pe stick. Se instalează driverul pentru %s."),
		_t("Am găsit completările pe stick. Se instalează driverul pentru adaptorul USB.")))

	def gata(rez, eroare):
		_stare["stick"] = None
		rez = rez or {}
		if not eroare and rez.get("amanat") and not rez.get("stick") and not rez.get("puse"):
			# opkg ocupat sau alta operatie in lucru: acelasi pachet, mai tarziu
			_stare["lucrare"] = None
			_programeaza(PAS_ASTEPTARE_MS)
			return
		reusit = el["pachet"] in (rez.get("puse") or [])
		if reusit:
			motiv = ""
		elif rez.get("loc"):
			motiv = _t("Nu este destul loc pe receptor.")
		else:
			motiv = _t("Fișierul cu completările de pe stick nu are driverul pentru acest receptor.")
		# o singura incercare: o cadere nu se intoarce la descarcarea listelor
		el["incercari"] = max(1, el.get("incercari", 0))
		dupaLucrare(el, _Rezultat({"reusit": reusit, "stare": motiv}))
	_stare["stick"] = Lucrare(lambda: L.instaleazaDinStick(pachete, RADACINA or "/"), gata)
	return True


def stickNou():
	"""Din HdsLimbaRestaurare.stickMontat: pe un stick bagat acum e fisierul de completari. Stickurile Wi-Fi fara driver
	se cauta din nou (si cele refuzate mai devreme fiindca driverul nu era in listele online), iar primul din coada vine
	de pe stick, fara sa mai astepte internetul."""
	try:
		if not _stare["pornit"] or not harta():
			return False
		for p in [p for p, r in _rezultat.items() if r.get("stare") in ("lipsa", "esuat")]:
			del _rezultat[p]
		trecereLaPornire()
		if not _coada or _stare["lucrare"] is not None or _ocupat():
			return False
		if _stare["ceas"] is not None:
			_stare["ceas"].stop()
		return dinStick(_coada[0])
	except Exception as e:
		_jurnal("stickNou: %r" % (e,))
		return False


# ---------------------------------------------------------------- tunerul USB: repornirea interfetei

def tunerConectat(nume):
	"""Un tuner DVB pe USB are driver, dar interfata nu-l vede inca: mesajul si intrebarea, o data pe sesiune."""
	if _stare["tuner"]:
		return False
	_stare["tuner"] = nume
	_jurnal("tuner USB conectat din mers: %s; cere repornirea interfetei" % nume)
	_noteaza(_cuNume(nume, _t("%s este gata. Apare în Setări tuner după repornirea interfeței."),
		_t("Adaptorul USB este gata. Apare în Setări tuner după repornirea interfeței.")), "repornire")
	s = _stare["sesiune"]
	if s is None:
		return True
	try:
		from Screens import Standby
		if Standby.inStandby is not None:
			# in standby nu vede nimeni intrebarea: vine cand omul porneste receptorul
			Standby.inStandby.onClose.append(lambda: _intreaba(nume))
			return True
	except Exception:
		pass
	_intreaba(nume)
	return True


def _intreaba(nume):
	s = _stare["sesiune"]
	if s is None:
		return
	try:
		from Screens.MessageBox import MessageBox

		def raspuns(da):
			if da:
				repornesteInterfata()
		s.openWithCallback(raspuns, MessageBox, _cuNume(nume, _t("%s este gata. Ca să apară în Setări tuner, interfața trebuie "
			"repornită (câteva secunde). Repornesc interfața acum?"), _t("Adaptorul USB este gata. Ca să apară în Setări tuner, "
			"interfața trebuie repornită (câteva secunde). Repornesc interfața acum?")), MessageBox.TYPE_YESNO)
	except Exception as e:
		_jurnal("intrebarea repornirii: %r" % (e,))


def repornesteInterfata():
	"""Da la intrebare sau butonul din pagina web: ca "Repornește interfața" din meniu (TryQuitMainloop 3)."""
	s = _stare["sesiune"]
	if s is None or not _stare["tuner"]:
		return {"result": False, "message": _t("Nu e nevoie de repornirea interfeței acum.")}
	try:
		from Screens.Standby import TryQuitMainloop
	except Exception as e:
		_jurnal("repornirea interfetei: %r" % (e,))
		return {"result": False, "message": _t("Interfața nu este gata pentru repornire.")}

	def acum():
		try:
			s.open(TryQuitMainloop, 3)
		except Exception as e:
			_jurnal("repornirea interfetei: %r" % (e,))
	# dupa REPORNIRE_DUPA_MS, ca raspunsul cererii din pagina web sa plece inainte ca interfata sa se opreasca
	_intarzie(REPORNIRE_DUPA_MS, acum)
	return {"result": True, "message": _t("Interfața repornește; tunerul apare în Setări tuner.")}


# ---------------------------------------------------------------- pagina web

def stareWeb():
	"""Pentru /api/retea (cardul "Adaptoare USB" din /retea): ce se instaleaza acum si ultimele mesaje."""
	lucru = _stare["lucrare"]
	return {
		"lucru": _seInstaleaza(lucru["nume"]) if lucru else "",
		"coada": [x["nume"] for x in _coada if x is not lucru],
		"ultimele": [dict(x) for x in _ultimele],
		"harta": bool(harta()),
		# un tuner USB bagat din mers asteapta repornirea interfetei (butonul din card)
		"repornire": _stare["tuner"] or "",
	}


def _reseteaza():
	"""numai pentru probe: starea modulului ca la pornire"""
	_harta[0] = None
	_asteapta.clear()
	del _coada[:]
	_rezultat.clear()
	del _ultimele[:]
	_stare.update(sesiune=None, pornit=False, ceas=None, lucrare=None, liste=False, esecuri_liste=0, masina=None, ceasuri=[],
		forteaza=False, tuner=None, stick=None)
