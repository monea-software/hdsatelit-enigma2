# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRezolutieTv (0.7.5): rezolutia interfetei temei HD Satelit pe televizor, 1080p (1920x1080, ca pana acum) sau 2K
# (2560x1440). Logica comuna a ecranului „Rezoluția interfeței” (Meniu > Interfata si aspect, Screens/HdsRezolutieTv.py),
# a paginii web /tema-tv (HdsWebControl/tema_tv_web.py) si a pornirii (skin.py, loadSkinData).
#
# - Tema ramane UNA, scrisa pe 1920x1080. La 2K, skin.py face ecranul final 2560x1440, iar ScaraEcran inmulteste cu 4/3
#   pozitiile, marimile, fonturile, grosimile si pozele fisierelor HDSatelit cand le citeste (acelasi drum ca sub o tema
#   straina 2K). Orice schimbare a temei intra deci singura si in 2K; nu exista un al doilea skin de tinut la zi.
# - Setarea: config.skin.rezolutie_tv ("1080" / "1440"), facuta in skin.py (se citeste la pornire, inainte de ecrane).
#   Se aplica la repornirea interfetei. Numai cu tema HD Satelit aleasa: o tema straina isi spune singura rezolutia.
# - Se arata numai cand placa poate (poate2K): pe HiSilicon driverul interfetei hi_fb.ko trebuie sa fie cel peticit de
#   stratul 0.7.5 (clasa OE-Alliance hisi-hifb-wqhd: limitele 1920/1080 din hifb_set_par si hifb_disp_setdispsize
#   schimbate in 2560/1440) si memoria video sa tina doua pagini 2560x1440 (28800 KB; V20 are 40500, V10 49152). O limita
#   tinuta minte de la un refuz al placii (HdsTemaExterna.REZOLUTIE_PLACA) o ascunde, pana vine alt driver. Celelalte
#   placi (Broadcom: Vu+, Edision...) deocamdata nu: neprobate, iar pe Vu+ memoria video e fixata de bootloader.
# - Intoarcerea singura la 1080p: placa refuza 2560x1440 la pornire (driverul vechi), driverul nu mai e cel peticit, sau
#   interfata se opreste neasteptat in primele HdsSkinuri.PROBA_S secunde cu 2K (semnul probei in /tmp, ca la temele
#   alese). Atunci setarea revine pe 1080p, ramane un motiv in /tmp si omul il afla o data, la pornirea sesiunii.
# - 0.7.7 (SK2, Eduard 15.11.2026 23:13: „sa faci 2K si skinul nostru”): a treia valoare, „Automată” = 2K numai cand
#   placa poate (poate2K), iesirea video aleasa e 2160p (televizor 4K; pe o iesire 1080p o interfata 2K e doar micsorata
#   de placa) si nu exista adaugiri ale omului in skin_user.xml (acelea nu se scaleaza); altfel 1080p. Un refuz al placii
#   in Automată nu schimba setarea si nu arata niciun mesaj (limita ramane tinuta minte numai pentru pornirea asta a
#   receptorului: driverul peticit pus de actualizare se incarca abia la urmatoarea pornire); numai o oprire neasteptata
#   in primele PROBA_S secunde pune setarea pe 1080p, cu explicatia o data. Valorile vechi ("1080", "1440") raman.
# - 4K (3840x2160) nu se ofera (masurat in jurnalele testerilor, randul [gFBDC]): doua pagini 3840x2160 cer 64800 kB, iar
#   memoria video a interfetei e 49152 kB pe SF8008 / Viper 4K V10 / Ustym 4K Pro / GigaBlue Trio 4K, 40500 kB pe Viper 4K
#   V20/V40, 24300 kB pe GigaBlue Quad 4K Pro si Vu+ Duo 4K lite, 21600 kB pe Vu+ Uno 4K SE / Solo 4K / Duo 4K / Duo 4K SE /
#   Zero 4K (Ultimo 4K si AX HD51 nemasurate); cu o singura pagina enigma2 ar desena direct pe ecranul vazut, iar driverul
#   hi_fb (si cel peticit) refuza 3840x2160 (probat pe Viper 4K V20). Iesirea video 2160p e alta setare (Setari > Video) si merge.
#
# Modulul nu importa nimic din enigma2 la incarcare (probele de pe PC dau config si caile).

import glob
import json
import os
import time

RAUTO = "auto"
R1080 = "1080"
R1440 = "1440"
VALORI = (RAUTO, R1080, R1440)
# implicitul, intr-un singur loc (skin.py il ia de aici): 1080p pana se probeaza HbbTV si viteza la 2K pe placile cu
# driverul peticit (a doua parere, SK2 15.11.2026), apoi RAUTO
IMPLICITA = R1080
MARIMI = {R1080: (1920, 1080), R1440: (2560, 1440)}
# iesirea video aleasa (VideoOutput.py: config.av.hds_videomode, ex. "2160p50"); la pornirea temei (loadSkinData) setarea
# nu e inca facuta (InitAVSwitch vine dupa), deci se citeste din settings, apoi modul de acum al placii
SETTINGS = "/etc/enigma2/settings"
CHEIE_MOD_VIDEO = "config.av.hds_videomode="
MOD_VIDEO_PROC = "/proc/stb/video/videomode"
SKIN_USER = "/etc/enigma2/skin_user.xml"

HIFB = "/lib/modules/*/extra/hi_fb.ko"
HIFB_PROC = "/proc/msp/hifb0"
# doua pagini 2560x1440 x 4 octeti (fb.cpp cere yres_virtual = 2 x yres)
MEMORIE_2K_KB = 2 * 2560 * 1440 * 4 // 1024
# HdsTemaExterna.REZOLUTIE_PLACA (aceeasi limita, scrisa si de refuzul temelor straine)
LIMITA = "/etc/enigma2/hds-rezolutie-placa.json"
PROBA = "/tmp/hds-rezolutie-proba"
REFUZ = "/tmp/hds-rezolutie-refuz"
CADERI = os.environ.get("HDS_CADERI") or "/tmp/hds-enigma2.caderi"
UPTIME = "/proc/uptime"
SYSTEMINFO = "HdsRezolutie2K"

MOTIV_PLACA = "placa"
MOTIV_DRIVER = "driver"
MOTIV_CADERE = "cadere"

# semnaturile clasei OE-Alliance hisi-hifb-wqhd (aceleasi ca in unealta R2K/verifica_hifb_wqhd.py): (veche, peticita)
SEMNATURI = (
	("383400e31e0d52e3", "a03500e30a0c52e3"),
	("1e0d52e33e0000ca041091e5383400e3", "0a0c52e33e0000ca041091e5a03500e3"),
	("383400e3030058e11e0d5793", "a03500e3030058e10a0c5793"),
)


def N_(text):
	return text


NUME = {RAUTO: N_("Automată"), R1080: N_("1080p (1920x1080)"), R1440: N_("2K (2560x1440)")}
DESCRIERE = {
	# un singur rand in fereastra de alegere de pe televizor (proba pe receptorul de probe: textul mai lung se derula)
	RAUTO: N_("2K pe televizoarele 4K (ieșirea 2160p), altfel 1080p."),
	R1080: N_("Rezoluția obișnuită a temei HD Satelit."),
	R1440: N_("Text și poze mai fine pe televizoarele 2K și 4K."),
}
# ce foloseste Automată acum, langa „aleasă” (ecranul si pagina)
TEXT_AUTO_ACUM = N_("aleasă, acum %s")
NUME_SCURT = {R1080: "1080p", R1440: "2K"}
TEXT_MOTIV = {
	MOTIV_PLACA: N_("Receptorul n-a primit interfața 2K (%s), așa că a rămas la 1080p."),
	MOTIV_DRIVER: N_("Driverul grafic al receptorului nu poate 2K, așa că interfața a rămas la 1080p."),
	MOTIV_CADERE: N_("Interfața s-a oprit la pornirea în 2K, așa că a revenit singură la 1080p."),
}


def _t(text, traducere=None):
	return traducere(text) if traducere else text


def _jurnal(text):
	print("[HdsRezolutieTv] %s" % text)


def _citesteJson(cale):
	try:
		with open(cale, encoding="utf-8") as f:
			d = json.load(f)
		return d if isinstance(d, dict) else None
	except (IOError, OSError, ValueError):
		return None


def _scrieJson(cale, date):
	try:
		if not os.path.isdir(os.path.dirname(cale)):
			return False
		temp = cale + ".nou"
		with open(temp, "w", encoding="utf-8") as f:
			json.dump(date, f)
		os.replace(temp, cale)
		return True
	except (IOError, OSError) as eroare:
		_jurnal("%s: %s" % (cale, eroare))
		return False


def _sterge(cale):
	try:
		os.unlink(cale)
	except OSError:
		pass


def _uptime(cale=None):
	try:
		with open(cale or UPTIME, encoding="utf-8", errors="replace") as f:
			return int(float(f.read().split()[0]))
	except (IOError, OSError, ValueError, IndexError):
		return 0


def _config(config=None):
	if config is not None:
		return config
	from Components.config import config
	return config


# ------------------------------------------------------------------ ce poate placa

def caleHifb(tipar=None):
	"""calea driverului interfetei HiSilicon (hi_fb.ko), sau None pe celelalte placi"""
	gasite = sorted(glob.glob(tipar or HIFB))
	return gasite[0] if gasite else None


def hifbPeticit(cale):
	"""True: hi_fb.ko are limitele 2560/1440 (peticul stratului 0.7.5) si nicio semnatura veche; False: driverul din
	fabrica sau necunoscut; None: fisierul nu se poate citi"""
	try:
		with open(cale, "rb") as f:
			d = f.read()
	except (IOError, OSError):
		return None
	vechi = sum(d.count(bytes.fromhex(v)) for v, _n in SEMNATURI)
	noi = sum(d.count(bytes.fromhex(n)) for _v, n in SEMNATURI)
	return noi > 0 and vechi == 0


def memoriaHifbKb(cale=None):
	"""memoria video a interfetei in KB (/proc/msp/hifb0, „Total HD Buffer MemSize : 40500 KB”), sau None"""
	try:
		with open(cale or HIFB_PROC, encoding="utf-8", errors="replace") as f:
			for rand in f:
				if "MemSize" in rand and ":" in rand:
					parti = rand.split(":", 1)[1].split()
					if parti and parti[0].isdigit():
						return int(parti[0])
	except (IOError, OSError):
		pass
	return None


def limitaTinuta(cale=None, driver=None):
	"""(latime, inaltime) cea mai mare primita de placa la un refuz de dinainte, sau None. Cu `driver` (poate2K) refuzul
	conteaza numai daca e de la pornirea asta a receptorului si mai nou decat fisierul driverului: actualizarea pune
	hi_fb peticit pe disc, dar placa il incarca abia la urmatoarea pornire; un refuz din pornirea de dinainte nu mai
	spune nimic despre driverul incarcat acum."""
	d = _citesteJson(cale or LIMITA)
	if not d:
		return None
	try:
		m = (int(d["maxim"][0]), int(d["maxim"][1]))
	except (KeyError, TypeError, ValueError, IndexError):
		return None
	if driver:
		try:
			cand = int(d.get("ora") or 0)
			pornire = int(time.time()) - _uptime()
			if cand < int(os.path.getmtime(driver)) or cand < pornire:
				return None
		except (OSError, ValueError, TypeError):
			pass
	return m


def poate2K(hifb=None, proc=None, limita=None):
	"""True cand alegerea 2K are rost pe placa asta (vezi sus). hifb: tiparul driverului (probele)."""
	driver = caleHifb(hifb)
	if driver is None:
		return False
	if not hifbPeticit(driver):
		return False
	mem = memoriaHifbKb(proc)
	if mem is not None and mem < MEMORIE_2K_KB:
		return False
	lim = limitaTinuta(limita, driver)
	if lim and (lim[0] < MARIMI[R1440][0] or lim[1] < MARIMI[R1440][1]):
		return False
	return True


def _cai(cai, *nume):
	return {k: v for k, v in cai.items() if k in nume}


def modVideo(config=None, settings=None, proc=None):
	"""iesirea video aleasa ("2160p50", "1080p50"...) sau "": setarea din memorie cand e facuta (in sesiune), altfel
	randul ei din settings (la pornirea temei), altfel modul de acum al placii"""
	try:
		el = _config(config).av.content.items.get("hds_videomode")
		if el is not None and el.value:
			return str(el.value)
	except Exception:
		pass
	try:
		with open(settings or SETTINGS, encoding="utf-8", errors="replace") as f:
			for rand in f:
				if rand.startswith(CHEIE_MOD_VIDEO):
					v = rand[len(CHEIE_MOD_VIDEO):].strip()
					if v:
						return v
	except (IOError, OSError):
		pass
	try:
		with open(proc or MOD_VIDEO_PROC, encoding="utf-8", errors="replace") as f:
			return f.read().strip()
	except (IOError, OSError):
		return ""


def iesire4K(config=None, settings=None, modproc=None):
	"""True cand iesirea video e 2160p (televizor 4K)"""
	return modVideo(config, settings, modproc).startswith("2160")


def autoVrea2K(config=None, skinUser=None, **cai):
	"""Automată alege 2K: placa poate, iesirea e 2160p si nu sunt adaugiri ale omului in skin_user.xml. skinUser: True/False
	de la skin.py (fisierul chiar se aplica peste tema), None = se uita daca fisierul exista."""
	if skinUser is None:
		skinUser = os.path.exists(cai.get("skinuser") or SKIN_USER)
	if skinUser:
		return False
	if not iesire4K(config, cai.get("settings"), cai.get("modproc")):
		return False
	return poate2K(**_cai(cai, "hifb", "proc", "limita"))


def autoAlege(config=None, **cai):
	"""ce ar folosi Automată la pornirea interfetei: R1440 sau R1080"""
	return R1440 if autoVrea2K(config, **cai) else R1080


# ------------------------------------------------------------------ alegerea

def aleasa(config=None):
	try:
		v = _config(config).skin.rezolutie_tv.value
	except AttributeError:
		return IMPLICITA
	return v if v in VALORI else IMPLICITA


def peEcran(latime=None):
	"""rezolutia interfetei de acum (R1440 / R1080) dupa latimea desktopului, sau None cand nu se stie (PC)"""
	if latime is None:
		try:
			from enigma import getDesktop
			latime = getDesktop(0).size().width()
		except Exception:
			return None
	if not latime:
		return None
	return R1440 if latime >= MARIMI[R1440][0] else R1080


def eticheta(valoare, ales, acum=None, traducere=None):
	"""randul unei valori in ecran si in pagina: numele, iar la cea aleasa „(aleasă)”; la Automată aleasa si ce
	foloseste acum („(aleasă, acum 2K)”)"""
	nume = _t(NUME.get(valoare, valoare), traducere)
	if valoare != ales:
		return nume
	if valoare == RAUTO and acum in NUME_SCURT:
		return "%s  (%s)" % (nume, _t(TEXT_AUTO_ACUM, traducere) % NUME_SCURT[acum])
	return "%s  (%s)" % (nume, _t(N_("aleasă"), traducere))


def seAlege(config=None, **cai):
	"""ecranul si pagina se arata: placa poate 2K, sau interfata e deja pe 2K (ca omul sa se poata intoarce)"""
	return aleasa(config) == R1440 or poate2K(**cai)


def alege(valoare, config=None):
	"""(schimbat, mesaj). Alegerea se salveaza pe loc; se vede dupa repornirea interfetei."""
	if valoare not in VALORI:
		return False, N_("Alegere necunoscută.")
	c = _config(config).skin.rezolutie_tv
	if c.value == valoare:
		return False, N_("Rezoluția aceasta e deja aleasă.")
	c.value = valoare
	c.save()
	try:
		from Components.config import configfile
		configfile.save()
	except Exception:
		pass
	stergeRefuz()
	return True, N_("Rezoluția aleasă se vede după repornirea interfeței.")


def actualizeazaSystemInfo(config=None, **cai):
	"""SystemInfo["HdsRezolutie2K"]: intrarea din meniu (requires=) se arata numai cand se poate alege"""
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo[SYSTEMINFO] = bool(seAlege(config, **cai))
	except Exception as eroare:
		_jurnal("SystemInfo: %s" % eroare)


# ------------------------------------------------------------------ pornirea (skin.py)

def _caderiDupa(pornit, caderi=None):
	"""o oprire neasteptata scrisa in /tmp/hds-enigma2.caderi la sau dupa `pornit` (ca HdsSkinuri._caderiDupa)"""
	try:
		with open(caderi or CADERI, encoding="utf-8", errors="replace") as f:
			for rand in f:
				p = rand.split()
				if p and p[0].isdigit() and int(p[0]) >= pornit and p[2:3] != ["oprire"]:
					return True
	except (IOError, OSError):
		pass
	return False


def refuza(motiv, detaliu="", config=None, refuz=None, proba=None):
	"""2K nu porneste: alegerea revine pe 1080p (salvata la pornirea sesiunii), motivul ramane pentru om"""
	_sterge(proba or PROBA)
	_scrieJson(refuz or REFUZ, {"motiv": motiv, "detaliu": detaliu, "aratat": False})
	try:
		c = _config(config).skin.rezolutie_tv
		c.value = R1080
		c.save()
	except Exception as eroare:
		_jurnal("alegerea nu s-a putut pune pe 1080p: %s" % eroare)
	_jurnal("2K nu porneste (%s %s), interfata ramane 1080p" % (motiv, detaliu))


def deCerutLaPornire(temaHds, config=None, mediu=None, proba=None, caderi=None, uptime=None, refuz=None, **cai):
	"""skin.py, inainte de loadSkinData: marimea de cerut placii (2560, 1440) sau None (ramane cea din tema, 1080p).
	Automată (SK2): numai cand autoVrea2K; altfel nimic cerut placii, fara mesaj (Vu+ si celelalte nu se intreaba deloc)."""
	proba = proba or PROBA
	mediu = os.environ if mediu is None else mediu
	ales = aleasa(config)
	if ales not in (R1440, RAUTO) or not temaHds or mediu.get("HDS_MOD_SIGUR") == "1":
		_sterge(proba)
		return None
	semn = _citesteJson(proba)
	if semn and _caderiDupa(int(semn.get("pornit") or 0), caderi):
		# oprirea neasteptata in proba 2K e singurul lucru care schimba si Automată (pe 1080p, cu explicatia)
		refuza(MOTIV_CADERE, "", config, refuz, proba)
		return None
	if ales == RAUTO:
		if not autoVrea2K(config, **cai):
			_sterge(proba)
			return None
	driver = caleHifb(cai.get("hifb"))
	if driver is not None and not hifbPeticit(driver):
		refuza(MOTIV_DRIVER, "", config, refuz, proba)
		return None
	acum = _uptime(uptime) if uptime is None or isinstance(uptime, str) else int(uptime)
	_scrieJson(proba, {"pornit": acum})
	return MARIMI[R1440]


def dupaRaspunsPlaca(cerut, primit, config=None, limita=None, refuz=None, proba=None, intreaba=None):
	"""skin.py, dupa ce a cerut placii marimea: True = ecranul final e `cerut`. Refuzul (sau o placa ce nu se poate
	intreba) lasa 1080p si tine minte limita, ca alegerea sa nu se mai arate pana la alt driver. intreaba(latime,
	inaltime): la pornire placa sta pe modul de inceput (720x576) dupa un refuz; se intreaba si de 1920x1080, ca limita
	tinuta minte sa fie cat poate placa, nu modul de inceput (ca HdsTemaExterna.verificaRezolutiaPlacii)."""
	if primit and tuple(int(v) for v in primit) == tuple(cerut):
		lim = limitaTinuta(limita)
		if lim and (cerut[0] > lim[0] or cerut[1] > lim[1]):
			_sterge(limita or LIMITA)
		return True
	auto = aleasa(config) == RAUTO
	if not primit or not primit[0] or not primit[1]:
		if auto:
			_sterge(proba or PROBA)
			_jurnal("Automată: placa nu se poate intreba, interfata ramane 1080p")
			return False
		refuza(MOTIV_PLACA, "%dx%d" % tuple(cerut), config, refuz, proba)
		return False
	baza = MARIMI[R1080]
	if intreaba is not None and (primit[0] < baza[0] or primit[1] < baza[1]):
		try:
			p = intreaba(baza[0], baza[1])
			if p and p[0] and p[1]:
				primit = p
		except Exception:
			pass
	_scrieJson(limita or LIMITA, {"maxim": [int(primit[0]), int(primit[1])], "refuzat": list(cerut), "ora": int(time.time())})
	if auto:
		# Automată: setarea ramane, fara mesaj; limita tinuta minte opreste incercarea pana la urmatoarea pornire a
		# receptorului (limitaTinuta cu driverul), cand se incarca driverul de pe disc
		_sterge(proba or PROBA)
		_jurnal("Automată: placa a refuzat %dx%d, interfata ramane 1080p" % tuple(cerut))
		return False
	refuza(MOTIV_PLACA, "%dx%d" % tuple(cerut), config, refuz, proba)
	return False


def pornireReusita(proba=None):
	"""interfata a mers HdsSkinuri.PROBA_S secunde: semnul probei se sterge (SkinSelector, _pornireReusita)"""
	_sterge(proba or PROBA)


# ------------------------------------------------------------------ ce afla omul

def citesteRefuz(refuz=None):
	return _citesteJson(refuz or REFUZ)


def stergeRefuz(refuz=None):
	_sterge(refuz or REFUZ)


def textRefuz(r, traducere=None):
	if not r:
		return ""
	motiv = r.get("motiv")
	text = _t(TEXT_MOTIV.get(motiv, TEXT_MOTIV[MOTIV_PLACA]), traducere)
	return text % (r.get("detaliu") or "2560x1440") if "%s" in text else text


def deAratat(refuz=None):
	"""refuzul inca nespus omului (o singura data, la pornirea sesiunii), marcat ca spus"""
	r = citesteRefuz(refuz)
	if not r or r.get("aratat"):
		return None
	r["aratat"] = True
	_scrieJson(refuz or REFUZ, r)
	return r


def laPornireaSesiunii(traducere=None):
	"""SkinSelector, la pornirea sesiunii: alegerea intoarsa pe 1080p se scrie in settings, omul afla o data de ce"""
	r = deAratat()
	if not r:
		return None
	try:
		from Components.config import configfile
		configfile.save()
	except Exception as eroare:
		_jurnal("settings: %s" % eroare)
	text = textRefuz(r, traducere)
	try:
		from Tools import Notifications
		from Screens.MessageBox import MessageBox
		Notifications.AddPopup(text, MessageBox.TYPE_INFO, 20, "HdsRezolutieTv")
	except Exception as eroare:
		_jurnal("mesajul: %s" % eroare)
	return text
