# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsSamba.py: setarea "Partajare în rețea (Samba)" (Setari > Retea si Internet, sectiunea hds_samba din setup.xml; in
# web cardul Samba din pagina /retea, retea_web.py). 0.7.5/0.7.6, MA9 si SMB, TODO 15.11 06:20 (tfrc, TODO 09.11 17:30).
#
# Ce face: dosarele receptorului se vad din calculatorul sau telefonul din casa, ca \\hdsatelit.local\Harddisk.
#   - Da/Nu (config.usage.hds_samba, din fabrica Nu) si dosarul (config.usage.hds_samba_dosar, din fabrica /media/hdd).
#   - Pornita = merge fara alt pas (regula 1f): daca serverul Samba lipseste, se instaleaza singur din feedul imaginii
#     (opkg update, opkg install samba; wsdd2 vine cu el, ca receptorul sa apara si in Retea in Windows); dosarul
#     implicit; numele din retea e numele receptorului (hdsatelit.local, al doilea hdsatelit2.local).
#   - Discul ales nu e montat (/media/hdd gol pe memoria interna): se partajeaza /media (toate stickurile si discurile),
#     nu dosarul gol de pe memoria interna, iar starea o spune.
#   - Parola: aceeasi ca la FTP (Components/HdsParolaLocala.py, bifa "FTP și Samba"). Cand omul si-a pus parola
#     receptorului si o cere la FTP, Samba o cere si ea (utilizator root). Altfel root are parola goala si dosarul
#     primeste si oaspeti (Kodi, VLC, Android). Windows 11 24H2 nu mai primeste oaspeti, deci acolo se scrie root si
#     campul de parola ramane gol; starea arata exact ce se scrie. Din afara casei nu se primeste nimeni (hosts allow
#     cu retelele de acasa, aceleasi ca la SSH: HdsAccesSsh.RETELE_LOCALE).
#
# Pachetul samba (OE-Alliance, citit din .ipk 4.25.0-r2): smb.conf include distro/smb-global.conf (care include
# distro/smb-shares.conf, cu [Root] = / si [Harddisk] = /media/hdd pentru root), apoi smb-shares.conf, facut de
# /etc/init.d/samba la start si reload din /etc/samba/shares/*.conf. Scriptul STERGE un fisier din shares/ care nu are
# un singur rand "path =" cu un dosar existent, deci aici: un fisier pe sectiune, un singur path, rescrise la fiecare
# aplicare. Sectiunile cu acelasi nume se unesc in Samba (valorile de mai tarziu castiga), deci [Root] si [Harddisk]
# din pachet se opresc (available = no) cand omul a ales alt dosar, iar dosarul ales le inlocuieste valorile.
# Parola: /etc/samba/private/smbpasswd (passdb smbpasswd), scris aici direct, 0600: hash-ul NT (MD4 pe UTF-16LE, din
# Components/HdsReteaSmb.md4); parola nu trece prin niciun program, nu se scrie in jurnal. Oprita: smbd oprit, scos de
# la pornire (update-rc.d -f samba remove; o actualizare a pachetului il pune la loc, deci la pornirea interfetei se
# opreste din nou) si contul root dezactivat in smbpasswd.
#
# FIRUL: notificatorul setarii ia valorile pe firul enigma2 si porneste aplicarea pe un fir separat, dupa
# ASTEPTARE_S (stanga/dreapta pe televizor nu instaleaza la fiecare apasare); un singur fir odata (_ZAVOR).
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC schimba RADACINA si PROGRAME.

import os
import subprocess
import threading
import time

RADACINA = ""
CAI = {
	"init": "/etc/init.d/samba",
	"smbd": "/usr/sbin/smbd",
	"shares": "/etc/samba/shares",
	"smbpasswd": "/etc/samba/private/smbpasswd",
	"hostname": "/etc/hostname",
	"proc": "/proc",
	"jurnal_opkg": "/tmp/hds-samba-opkg.log",
}
PROGRAME = {
	"opkg": "/usr/bin/opkg",
	"update-rc.d": "/usr/sbin/update-rc.d",
	"sh": "/bin/sh",
}
PACHET = "samba"
PREFIX = "hdsatelit"
TIMP_UPDATE_S = 180
TIMP_INSTALARE_S = 900
TIMP_INIT_S = 60
ASTEPTARE_S = 2.0

# dosarele din care alege omul: (cale, numele din retea, textul alegerii)
DOSAR_IMPLICIT = "/media/hdd"
DOSAR_REZERVA = "/media"


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele se traduc la afisare."""
	return text


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


DOSARE = (
	(DOSAR_IMPLICIT, "Harddisk", N_("Discul (/media/hdd)")),
	(DOSAR_REZERVA, "Media", N_("Toate stickurile și discurile (/media)")),
	("/", "Root", N_("Tot receptorul (/)")),
)
# sectiunile puse de pachet in distro/smb-shares.conf: (numele, dosarul)
SECTIUNI_PACHET = (("Root", "/"), ("Harddisk", DOSAR_IMPLICIT))

T_OPRITA = N_("Oprită: dosarele receptorului nu se văd în rețea.")
T_INSTALEZ = N_("Se instalează Samba din feedul imaginii...")
T_PORNESC = N_("Se pornește...")
T_PORNITA = N_("Pornită. În Windows scrie în bara de adrese din Explorer: %s")
T_ALTE = N_("Pe telefon sau televizor (VLC, Kodi) și pe Mac: %s")
T_FARA_PAROLA = N_("Utilizator: root. Parola: lasă câmpul gol.")
T_CU_PAROLA = N_("Utilizator: root. Parola: parola receptorului (Setări > Rețea > Parola receptorului).")
T_REZERVA = N_("Discul nu e montat: se partajează /media, cu toate stickurile și discurile.")
T_ALTFEL = N_("Serverul Samba rulează, pornit și făcut în afara acestei setări. Alege Da ca să-l facă receptorul.")
T_NU_RULEAZA = N_("Setarea e pornită, dar serverul Samba nu rulează.")
T_LIPSA_FEED = N_("Samba nu e încă în feedul acestei imagini. Încearcă după următoarea actualizare.")
T_NEINSTALAT = N_("Samba nu s-a instalat. Verifică legătura la internet, apoi alege din nou Da.")
T_OPKG_OCUPAT = N_("Altă instalare rulează acum. Samba se instalează la următoarea alegere sau pornire.")
T_FARA_OPKG = N_("Instalarea pachetelor nu este disponibilă în această imagine.")


def _jurnal(text):
	print("[HdsSamba] %s" % text)


def _cale(cale):
	return RADACINA + cale if RADACINA else cale


def _citeste(cale, maxim=65536):
	try:
		with open(_cale(cale), "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (IOError, OSError):
		return None


def _scrieAtomic(cale, text, mod):
	tinta = _cale(cale)
	dosar = os.path.dirname(tinta)
	if dosar and not os.path.isdir(dosar):
		os.makedirs(dosar, 0o755)
	nou = tinta + ".nou"
	fd = os.open(nou, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mod)
	with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
		f.write(text)
		f.flush()
		try:
			os.fsync(f.fileno())
		except OSError:
			pass
	try:
		os.chmod(nou, mod)
	except OSError:
		pass
	os.replace(nou, tinta)


def _sterge(cale):
	try:
		os.remove(_cale(cale))
		return True
	except OSError:
		return False


# ---------------------------------------------------------------- ce e pe receptor

def instalat():
	"""True cand serverul Samba e instalat (smbd si scriptul lui de pornire)."""
	return os.path.isfile(_cale(CAI["smbd"])) and os.path.isfile(_cale(CAI["init"]))


def ruleaza():
	"""True cand un proces smbd ruleaza (/proc/<pid>/comm)."""
	proc = _cale(CAI["proc"])
	try:
		nume = os.listdir(proc)
	except OSError:
		return False
	for pid in nume:
		if not pid.isdigit():
			continue
		try:
			with open(os.path.join(proc, pid, "comm"), "rb") as f:
				if f.read(32).strip() == b"smbd":
					return True
		except (IOError, OSError):
			continue
	return False


def numeGazda():
	"""Numele receptorului in retea (/etc/hostname), din fabrica hdsatelit."""
	text = (_citeste(CAI["hostname"], 256) or "").strip().split("\n")[0].strip()
	ok = text and all(c.isalnum() or c in "-." for c in text) and len(text) <= 63
	return text if ok else "hdsatelit"


def _montat(cale):
	"""True cand dosarul e (sau duce la) un punct de montare: /media/hdd fara disc e un dosar gol pe memoria interna."""
	reala = os.path.realpath(_cale(cale))
	if RADACINA:
		# pe PC: montarea se imita cu fisierul .montat din dosar
		return os.path.isdir(reala) and os.path.exists(os.path.join(reala, ".montat"))
	return os.path.ismount(reala)


def dosarEfectiv(ales):
	"""(dosarul partajat, numele din retea, rezerva): dosarul ales, sau /media cand discul ales nu e montat."""
	for cale, nume, _text in DOSARE:
		if cale == ales:
			break
	else:
		ales, nume = DOSAR_IMPLICIT, "Harddisk"
	if ales in ("/", DOSAR_REZERVA):
		return ales, nume, False
	if _montat(ales):
		return ales, nume, False
	return DOSAR_REZERVA, "Media", True


# ---------------------------------------------------------------- parola

def parolaSamba():
	"""(textul parolei, ceruta): parola receptorului cand e pusa si ceruta la FTP (bifa "FTP și Samba"), altfel
	("", False): root cu parola goala, iar dosarul primeste si oaspeti."""
	try:
		from Components import HdsParolaLocala as P
	except ImportError:
		return "", False
	try:
		if not P.ceruta(P.FTP):
			return "", False
		text = (P._citeste(P.CALE_PAROLA, P.MAX_PAROLA + 8) or "").rstrip("\r\n")
	except Exception as eroare:
		_jurnal("parola receptorului: %s" % eroare.__class__.__name__)
		return "", False
	if not text:
		return "", False
	return text, True


def cuParola():
	"""True cand Samba cere parola receptorului (pusa si ceruta la FTP). Numai citiri tinute minte (merge pe firul enigma2)."""
	try:
		from Components import HdsParolaLocala as P
		return bool(P.ceruta(P.FTP))
	except Exception:
		return False


def hashNt(parola):
	"""Hash-ul NT (MD4 pe UTF-16LE), cu litere mari, ca in smbpasswd."""
	from Components.HdsReteaSmb import md4
	return md4((parola or "").encode("utf-16-le")).hex().upper()


def randSmbpasswd(parola, activ=True, cand=None):
	"""Randul lui root din smbpasswd: steagurile (11 semne intre paranteze) U = cont obisnuit, D = dezactivat."""
	steaguri = ("U" if activ else "DU").ljust(11)
	return "root:0:%s:%s:[%s]:LCT-%08X:\n" % ("X" * 32, hashNt(parola), steaguri, int(cand if cand is not None else time.time()))


def scrieSmbpasswd(parola, activ=True):
	"""Scrie randul lui root in smbpasswd (0600); conturile puse de om cu smbpasswd raman. True daca a mers."""
	altele = [r for r in (_citeste(CAI["smbpasswd"], 1 << 20) or "").splitlines(True)
		if r.strip() and not r.startswith("root:")]
	altele = [r.rstrip("\r\n") + "\n" for r in altele]
	try:
		_scrieAtomic(CAI["smbpasswd"], "".join(altele) + randSmbpasswd(parola, activ), 0o600)
		return True
	except (IOError, OSError) as eroare:
		_jurnal("smbpasswd nu se poate scrie: %s" % eroare.__class__.__name__)
		return False


# ---------------------------------------------------------------- dosarele partajate

def hostsAllow():
	try:
		from Components.HdsAccesSsh import RETELE_LOCALE
	except ImportError:
		RETELE_LOCALE = ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "::1",
			"fe80::/10", "fc00::/7")
	return " ".join(RETELE_LOCALE)


def textSectiune(nume, cale, cu_parola):
	"""Sectiunea dosarului partajat. Valorile puse aici le inlocuiesc pe cele din pachet (aceeasi sectiune)."""
	randuri = [
		"# Scris de receptor (Setari > Retea > Partajare in retea). Se rescrie la fiecare schimbare.",
		"[%s]" % nume,
		"\tcomment = HD Satelit",
		"\tpath = %s" % cale,
		"\tavailable = yes",
		"\tbrowseable = yes",
		"\tread only = no",
		"\tforce user = root",
		"\tforce create mode = 0644",
		"\tforce directory mode = 0755",
		"\twide links = yes",
		"\tfollow symlinks = yes",
		"\thosts allow = %s" % hostsAllow(),
	]
	if cu_parola:
		randuri += ["\tguest ok = no", "\tvalid users = root"]
	else:
		# fara parola: root cu parola goala si oaspetii (valid users gol = oricine a intrat)
		randuri += ["\tguest ok = yes", "\tvalid users ="]
	return "\n".join(randuri) + "\n"


def textOprita(nume, cale):
	"""O sectiune a pachetului oprita (alt dosar ales)."""
	return ("# Scris de receptor: sectiunea pachetului oprita, omul a ales alt dosar.\n"
		"[%s]\n\tpath = %s\n\tavailable = no\n" % (nume, cale))


def fisierSectiune(nume):
	return "%s/%s-%s.conf" % (CAI["shares"], PREFIX, nume.lower())


def fisiereleNoastre():
	"""Fisierele scrise de noi in /etc/samba/shares (numele incep cu PREFIX)."""
	dosar = _cale(CAI["shares"])
	try:
		return sorted("%s/%s" % (CAI["shares"], n) for n in os.listdir(dosar)
			if n.startswith(PREFIX + "-") and n.endswith(".conf"))
	except OSError:
		return []


def scrieSectiuni(ales, cu_parola):
	"""Scrie dosarul partajat si opreste sectiunile pachetului care nu sunt el. (dosar, nume, rezerva)."""
	cale, nume, rezerva = dosarEfectiv(ales)
	dorite = {fisierSectiune(nume): textSectiune(nume, cale, cu_parola)}
	for n, c in SECTIUNI_PACHET:
		if n != nume:
			dorite[fisierSectiune(n)] = textOprita(n, c)
	for f in fisiereleNoastre():
		if f not in dorite:
			_sterge(f)
	for f, text in dorite.items():
		if _citeste(f) != text:
			_scrieAtomic(f, text, 0o644)
	return cale, nume, rezerva


def scoateSectiuni():
	"""Oprita: dosarul partajat se scoate; sectiunile pachetului raman oprite (daca smbd porneste totusi)."""
	for f in fisiereleNoastre():
		_sterge(f)
	for n, c in SECTIUNI_PACHET:
		_scrieAtomic(fisierSectiune(n), textOprita(n, c), 0o644)


# ---------------------------------------------------------------- programele

def _ruleaza(argv, termen, iesire=None):
	"""(cod, None); -1 programul lipseste, -2 termenul a trecut."""
	try:
		p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=iesire or subprocess.DEVNULL,
			stderr=subprocess.STDOUT if iesire else subprocess.DEVNULL, close_fds=True)
	except OSError:
		return -1
	try:
		return p.wait(termen)
	except subprocess.TimeoutExpired:
		try:
			p.kill()
			p.wait(5)
		except Exception:
			pass
		return -2


def _init(comanda):
	return _ruleaza([PROGRAME["sh"], _cale(CAI["init"]), comanda], TIMP_INIT_S)


def _laPornire(da):
	program = PROGRAME["update-rc.d"]
	if not os.path.isfile(_cale(program)) and not RADACINA:
		return -1
	argv = [program, PACHET, "defaults"] if da else [program, "-f", PACHET, "remove"]
	return _ruleaza(argv, TIMP_INIT_S)


def _opkgOcupat():
	try:
		from Components.HdsActualizari import opkg_ocupat
		return bool(opkg_ocupat("/"))
	except Exception:
		return False


def instaleaza():
	"""opkg update, apoi opkg install samba. (reusit, mesaj gol sau motivul pentru om)."""
	if not os.path.isfile(_cale(PROGRAME["opkg"])) and not RADACINA:
		return False, T_FARA_OPKG
	if _opkgOcupat():
		return False, T_OPKG_OCUPAT
	try:
		fd = os.open(_cale(CAI["jurnal_opkg"]), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
			0o600)
		iesire = os.fdopen(fd, "wb")
	except OSError:
		iesire = None
	try:
		_jurnal("opkg update, apoi opkg install %s" % PACHET)
		_ruleaza([PROGRAME["opkg"]] + _argumenteUpdate(), TIMP_UPDATE_S, iesire)
		cod = _ruleaza([PROGRAME["opkg"], "install", PACHET], TIMP_INSTALARE_S, iesire)
	finally:
		if iesire is not None:
			iesire.close()
	# 0.7.9 (BLD8): pachetele descarcate de opkg stau in /var/cache/opkg, in RAM; dupa instalare se sterg
	try:
		from Components import HdsCuratenie
		HdsCuratenie.golesteCacheOpkgDupa([PROGRAME["opkg"], "install", PACHET])
	except Exception:
		pass
	if cod == 0 and instalat():
		return True, ""
	return False, motivInstalare(_citeste(CAI["jurnal_opkg"], 262144) or "")


def motivInstalare(jurnal_opkg):
	"""Motivul pentru om din jurnalul opkg: pachetul lipsa din feed sau altceva (internetul)."""
	text = (jurnal_opkg or "")[-8192:].lower()
	if "unknown package" in text or "cannot find package" in text or "no packages installed" in text:
		return T_LIPSA_FEED
	return T_NEINSTALAT


# ---------------------------------------------------------------- aplicarea

_ZAVOR = threading.Lock()
_STARE = {"lucru": "", "eroare": "", "rezerva": False, "dosar": "", "nume": "", "cu_parola": False}
_CEAS = [None]


def aplica(da, ales=DOSAR_IMPLICIT):
	"""Aplica alegerea (pe un fir separat: poate instala din feed). Intoarce starea (dict)."""
	with _ZAVOR:
		_STARE["eroare"] = ""
		if not da:
			_STARE["lucru"] = ""
			if instalat():
				_init("stop")
				_laPornire(False)
				parola, _c = parolaSamba()
				scrieSmbpasswd(parola, activ=False)
				scoateSectiuni()
			_jurnal("oprita")
			return dict(_STARE)
		if not instalat():
			_STARE["lucru"] = T_INSTALEZ
			ok, motiv = instaleaza()
			if not ok:
				_STARE["lucru"], _STARE["eroare"] = "", motiv
				_jurnal("instalarea nu a mers")
				return dict(_STARE)
		_STARE["lucru"] = T_PORNESC
		parola, cu_parola = parolaSamba()
		scrieSmbpasswd(parola, activ=True)
		cale, nume, rezerva = scrieSectiuni(ales, cu_parola)
		_STARE.update(dosar=cale, nume=nume, rezerva=rezerva, cu_parola=cu_parola)
		_laPornire(True)
		_init("restart" if ruleaza() else "start")
		_STARE["lucru"] = ""
		_jurnal("pornita: %s ca %s, %s" % (cale, nume, "cu parola" if cu_parola else "fara parola"))
		return dict(_STARE)


def aplicaParola():
	"""Parola receptorului s-a schimbat (HdsParolaLocala.aplicaTot): smbpasswd si dosarul rescrise, apoi reload, pe un
	fir separat. Fara Samba instalat sau pornit nu face nimic."""
	if not instalat():
		return False
	ales = _ALES[0]
	if ales is None:
		return False
	da, dosar = ales

	def lucreaza():
		with _ZAVOR:
			parola, cu_parola = parolaSamba()
			scrieSmbpasswd(parola, activ=da)
			if da:
				cale, nume, rezerva = scrieSectiuni(dosar, cu_parola)
				_STARE.update(dosar=cale, nume=nume, rezerva=rezerva, cu_parola=cu_parola)
				if ruleaza():
					_init("reload")
	_porneste(lucreaza)
	return True


def _porneste(functie, *argumente):
	t = threading.Thread(target=functie, args=argumente, name="HdsSamba")
	t.daemon = True
	t.start()
	return t


# ultima alegere luata pe firul enigma2: (da, dosar)
_ALES = [None]


def programeaza(da, ales):
	"""Alegerea omului (luata pe firul enigma2): aplicata dupa ASTEPTARE_S, numai ultima."""
	_ALES[0] = (bool(da), ales)
	if _CEAS[0] is not None:
		_CEAS[0].cancel()
	ceas = threading.Timer(ASTEPTARE_S, aplica, (bool(da), ales))
	ceas.daemon = True
	_CEAS[0] = ceas
	if da and not instalat():
		_STARE["lucru"] = T_INSTALEZ
	ceas.start()


def laPornire(da, ales, atinsa=True):
	"""La pornirea interfetei: pornita, dar lipsa sau oprita, se aduce la alegere; oprita, dar smbd ruleaza (o
	actualizare a pachetului l-a pus la pornire), se opreste. Setarea neatinsa de om (Nu din fabrica, nesalvata) nu
	atinge nimic: cine si-a instalat si facut singur Samba inainte de 0.7.6 il pastreaza asa, cu parolele lui."""
	if not atinsa:
		_ALES[0] = None
		return None
	_ALES[0] = (bool(da), ales)
	if da or (instalat() and ruleaza()):
		_porneste(aplica, bool(da), ales)
	return None


# ---------------------------------------------------------------- starea pentru ecran si web

def adresa(nume=None):
	"""\\\\<gazda>.local\\<nume>"""
	return "\\\\%s.local\\%s" % (numeGazda(), nume or _STARE.get("nume") or "Harddisk")


def adresaSmb(nume=None):
	return "smb://%s.local/%s" % (numeGazda(), nume or _STARE.get("nume") or "Harddisk")


def stare(da=None, ales=None):
	"""{"pornita", "instalat", "ruleaza", "adresa", "adresa_smb", "cu_parola", "rezerva", "lucru", "eroare", "linii"}."""
	if da is None or ales is None:
		da, ales = _ALES[0] or (False, DOSAR_IMPLICIT)
	inst = instalat()
	merge = inst and ruleaza()
	_cale_ef, nume, rezerva = dosarEfectiv(ales)
	cu_parola = cuParola() if da else False
	rez = {"pornita": bool(da), "instalat": inst, "ruleaza": merge, "adresa": adresa(nume), "adresa_smb": adresaSmb(nume),
		"cu_parola": cu_parola, "rezerva": rezerva, "lucru": _t(_STARE["lucru"]) if _STARE["lucru"] else "",
		"eroare": _t(_STARE["eroare"]) if _STARE["eroare"] else ""}
	rez["linii"] = linii(rez)
	return rez


def linii(s):
	"""Randurile starii, traduse: aceleasi pe televizor si in web."""
	if not s["pornita"]:
		return [_t(T_ALTFEL)] if s["ruleaza"] else [_t(T_OPRITA)]
	if s["lucru"]:
		return [s["lucru"]]
	if s["eroare"]:
		return [s["eroare"]]
	if not s["ruleaza"]:
		return [_t(T_NU_RULEAZA)]
	rez = [_t(T_PORNITA) % s["adresa"], _t(T_CU_PAROLA) if s["cu_parola"] else _t(T_FARA_PAROLA)]
	if s["rezerva"]:
		rez.append(_t(T_REZERVA))
	rez.append(_t(T_ALTE) % s["adresa_smb"])
	return rez


# ---------------------------------------------------------------- setarile

def _schimbat(element=None):
	try:
		from Components.config import config
		u = config.usage
		alegere = (bool(u.hds_samba.value), u.hds_samba_dosar.value)
		# salvarea ecranului cheama notificatorul si fara schimbare: aceeasi alegere, fara eroare, nu se aplica din nou
		if alegere == _ALES[0] and not _STARE["eroare"]:
			return
		programeaza(*alegere)
	except Exception as eroare:
		_jurnal("aplicarea setarii: %s" % eroare)


def _stareSetare():
	return stare()["linii"]


def initConfig():
	"""Din InitUsageConfig: config.usage.hds_samba (Da/Nu, din fabrica Nu) si config.usage.hds_samba_dosar; o schimbare
	din ecran sau din web se aplica singura ("Renunță" pune valoarea salvata inapoi, cu aplicarea ei). Apoi alegerea
	salvata se aplica o data (laPornire)."""
	from Components.config import config, ConfigYesNo, ConfigSelection
	config.usage.hds_samba = ConfigYesNo(default=False)
	config.usage.hds_samba_dosar = ConfigSelection(default=DOSAR_IMPLICIT, choices=[(c, _t(t)) for c, _n, t in DOSARE])
	for element in (config.usage.hds_samba, config.usage.hds_samba_dosar):
		# Nu ales de om se scrie si el (altfel arata ca neatins la pornirea urmatoare)
		element.save_forced = True
		element.callNotifiersOnSaveAndCancel = True
		element.addNotifier(_schimbat, initial_call=False)
		element.hdsStare = _stareSetare   # starea de acum in ecranul de setari (Screens/Setup.py)
	try:
		atinsa = config.usage.hds_samba.saved_value is not None or config.usage.hds_samba_dosar.saved_value is not None
		laPornire(bool(config.usage.hds_samba.value), config.usage.hds_samba_dosar.value, atinsa)
	except Exception as eroare:
		_jurnal("aplicarea la pornire: %s" % eroare)


def _argumenteUpdate(rad="/"):
	"""OPK1 (0.8.0): ['update'], or ['-f', <conf>, 'update'] when a dead foreign source is skipped (HdsSurseOpkg)"""
	try:
		try:
			from Components import HdsSurseOpkg
		except ImportError:
			import HdsSurseOpkg
		return HdsSurseOpkg.argumente_update(rad)
	except Exception as e:
		print("[HdsSurseOpkg] %r" % (e,))
		return ["update"]
