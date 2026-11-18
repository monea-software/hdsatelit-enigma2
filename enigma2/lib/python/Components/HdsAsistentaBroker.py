# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistentaBroker.py: rularea unei operatii din catalogul Asistentei (Components/HdsAsistentaCatalog.py). Cererea
# a fost deja verificata (semnatura si tiparele argumentelor) de HdsAsistenta.py; aici se ruleaza numai operatia ceruta
# si se intoarce raspunsul, filtrat si plafonat.
#
# Nivelul A: numai citiri (si textul ecranului, op "ecran") si trei probe (captura video cu OSD, un mesaj pe ecran, concluziile
# echipei pe ecran). Nivelul B ("Control complet", bifat de om pe pagina de pornire) adauga op-urile de control
# (CONTROL: tastele telecomenzii si textul intr-un camp), refuzate aici cand ctx["nivel"] nu e "B" (fara ecrane
# private, echipa vede ce e pe televizor; textul trimis spre noi trece in continuare prin filtrul de parole). Nimic nu scrie pe disc in afara jurnalului
# sesiunii. Externele se cheama cu lista de argumente (execve, FARA shell), cu termen si plafon de octeti. O singura
# operatie primeste o cale (op "citeste", din 0.6.21): numai sub RADACINI_CITIRE, verificata dupa realpath (nicio
# legatura spre afara, spre discuri sau stick-uri) si niciodata prin LOCURI_OPRITE (fisierele de parole si cheile private)
# sau LOCURI_NESIGURE (memoria bruta si fluxurile nucleului care nu se termina).
#
# Eduard, 12.11.2026 19:17 si 19:19 („cine a spus sa nu faca jurnalul despre rolele si problemele modulelor? eu am spus
# sa fie tot, tot, tot”; „FARA PAROLE, ATAT”): asistenta vede tot, si modulele de acces (jurnalele, fisierele si dosarele
# lor, procesele, setarile config.softcam...), si numele, gazdele, porturile, adresele MAC. Din tot ce pleaca spre echipa
# se ascund NUMAI parolele (Components/HdsAsistentaControl.mascheazaParole). Hotararea inlocuieste nota din 01.11.2026
# 23:40 (fara module si fara date personale in asistenta). Ce iese public pe forum (rapoartele testerilor, codurile QR)
# ramane curatat ca inainte (HdsBetaTester.curata, HdsDiagnostic.faraDatePersonale).
#
# Fiecare op din catalog are aici o functie (TABEL); o proba cere ca cele doua liste sa coincida. Partea de sus nu
# importa nimic din enigma2: functiile care au nevoie de receptor (captura, mesaj, memoria decodorului, setarile)
# primesc caile si uneltele prin argumente, iar probele de pe PC le dau pe ale lor.

import os
import re
import subprocess

from Components.HdsAsistentaControl import mascheazaParole
from Components.HdsProcFundal import nodOprit

RASPUNS_MAX = 1024 * 1024           # 1 MB de raspuns (text sau captura)
# coada unui fisier mai mare: putin sub plafon, ca randul de inceput si stelutele sa nu taie sfarsitul (_taie)
COADA_MAX = RASPUNS_MAX - 16 * 1024
CAPTURA_MAX = 2 * 1024 * 1024       # o captura (JPEG mic de la 0.6.15; PNG inainte) se plafoneaza aparte
# op-urile de control: numai la nivelul B (omul a lasat bifat "Control complet")
CONTROL = ("taste", "text", "zap", "reporneste", "setare-scrie", "instaleaza", "dezinstaleaza", "repara-actualizarea")
TERMEN_S = 20                       # cat asteapta un extern
MAX_RANDURI_JURNAL = 2000

CALE_JURNALE = "/home/root/logs"
IMAGE_VERSION = "/etc/image-version"

def _jurnal(text):
	print("[HdsAsistentaBroker] %s" % text)


class Rezultat(object):
	"""Raspunsul unei operatii: text (filtrat) sau octeti (captura), plus cod_iesire si o eticheta de tip."""

	def __init__(self, cod_iesire=0, text=None, octeti=None, tip="text"):
		self.cod_iesire = int(cod_iesire)
		self.text = text
		self.octeti = octeti
		self.tip = tip

	def marime(self):
		if self.octeti is not None:
			return len(self.octeti)
		return len((self.text or "").encode("utf-8", "replace"))


# ---------------------------------------------------------------- filtre si plafoane

def mascheaza(text):
	"""Iesirea spre echipa: numai parolele devin *** (Eduard, 12.11.2026 19:19), plus utilizatorul din adresele de flux
	IPTV, care e contul liniei (DSP 14.11.2026). Randurile modulelor de acces, numele de utilizator din afara adreselor,
	gazdele, porturile si adresele MAC raman. Trece aici orice raspuns text, al oricarei operatii (ruleaza)."""
	return mascheazaParole(text or "")


def _taie(text, limita=RASPUNS_MAX):
	octeti = (text or "").encode("utf-8", "replace")
	if len(octeti) <= limita:
		return text or ""
	return octeti[:limita].decode("utf-8", "ignore") + "\n... (raspuns taiat la %d octeti)" % limita


def _citeste(cale, maxim=RASPUNS_MAX, lista=False):
	try:
		with open(cale, "rb") as f:
			date = f.read(maxim + 1)
		if lista:
			from Components.HdsListeText import text_lista
			return text_lista(date)
		return date.decode("utf-8", "replace")
	except Exception as e:
		return "(nu se poate citi %s: %s)" % (os.path.basename(cale), type(e).__name__)


def _citesteCoada(cale, maxim=RASPUNS_MAX):
	"""Ultimii `maxim` octeti ai unui fisier obisnuit (fara primul rand, taiat, cand fisierul e mai mare)."""
	try:
		with open(cale, "rb") as f:
			f.seek(0, os.SEEK_END)
			marime = f.tell()
			f.seek(max(0, marime - maxim))
			date = f.read(maxim)
		text = date.decode("utf-8", "replace")
		if marime > maxim:
			text = text.split("\n", 1)[-1]
		return text
	except Exception as e:
		return "(nu se poate citi %s: %s)" % (os.path.basename(cale), type(e).__name__)


BUCATA_CITIRE = 16384     # cat cere o citire din fisier (o citire de 16 KiB din /proc/bus/nim_sockets merge pe Vu+ 4K)


def _citesteBucati(cale, de_la=0, maxim=RASPUNS_MAX, termen=10):
	"""Octetii unui fisier de la `de_la`, cel mult `maxim`, cititi in Python cu citiri de BUCATA_CITIRE, pe un fir cu
	termen (un disc care nu raspunde nu tine sesiunea). -> (cod, octeti, eroare): cod 0 bun, 1 eroare (octetii de pana
	atunci raman: un driver care da eroare la a doua citire lasa totusi textul primei), 124 dupa termen.
	Asistenta 636002 (Vu+ Ultimo 4K, 14.11.2026): head pe /proc/bus/nim_sockets da Input/output error, iar citirea din
	Python a aceluiasi fisier (op tunere) merge."""
	import threading
	stare = {"bucati": [], "eroare": None, "gata": False}

	def lucru():
		try:
			fd = os.open(cale, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
			try:
				ramas = maxim
				if de_la:
					try:
						os.lseek(fd, de_la, os.SEEK_SET)
					except OSError:
						# fisierele din /proc fara cautare: octetii de dinainte se citesc si se arunca
						sari = de_la
						while sari > 0:
							b = os.read(fd, min(BUCATA_CITIRE, sari))
							if not b:
								break
							sari -= len(b)
				while ramas > 0:
					b = os.read(fd, min(BUCATA_CITIRE, ramas))
					if not b:
						break
					stare["bucati"].append(b)
					ramas -= len(b)
			finally:
				os.close(fd)
		except Exception as e:
			stare["eroare"] = "%s: %s" % (type(e).__name__, getattr(e, "strerror", None) or e)
		stare["gata"] = True

	fir = threading.Thread(target=lucru, name="hds-asistenta-citire")
	fir.daemon = True
	fir.start()
	fir.join(termen)
	octeti = b"".join(stare["bucati"])
	if not stare["gata"]:
		return 124, octeti, "termen"
	return (1 if stare["eroare"] else 0), octeti, stare["eroare"]


def _ruleaza(argv, termen=TERMEN_S, limita=RASPUNS_MAX):
	"""Un extern, cu lista de argumente (fara shell), termen si plafon. -> (cod_iesire, text)."""
	try:
		p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
			stdin=subprocess.DEVNULL, env={"LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
	except Exception as e:
		return 127, "(nu se poate porni %s: %s)" % (argv[0], type(e).__name__)
	try:
		iesire, _err = p.communicate(timeout=termen)
	except subprocess.TimeoutExpired:
		p.kill()
		try:
			p.communicate(timeout=5)
		except Exception:
			pass
		return 124, "(a trecut termenul de %d s)" % termen
	text = (iesire or b"")[:limita + 1].decode("utf-8", "replace")
	return p.returncode, text


# ---------------------------------------------------------------- operatiile (nivelul A)

def op_info(ctx, args):
	parti = []
	ver = _citeste(ctx.get("image_version", IMAGE_VERSION), 4096).strip()
	if ver:
		parti.append("Imagine:\n" + ver)
	parti.append("Nucleu: " + _citeste("/proc/version", 1024).strip())
	parti.append("Uptime: " + _citeste("/proc/uptime", 128).strip())
	parti.append("Memorie:\n" + _citeste("/proc/meminfo", 4096).strip())
	cod, disc = _ruleaza(["df", "-h"], limita=16384)
	parti.append("Disc:\n" + disc.strip())
	parti.append("Temperaturi:\n" + _temperaturi(ctx))
	parti.append("Ceas:\n" + _ceas(ctx))
	# ce operatii stie receptorul acesta (unealta echipei alege dupa ele, de pilda "concluzii" din 0.6.13)
	parti.append("Operatii asistenta: " + " ".join(sorted(TABEL)))
	return Rezultat(0, text="\n\n".join(p for p in parti if p))


def _stareCeas():
	"""Starea ceasului din enigma2 (Components.HdsCeas), numai daca sincronizatorul e deja pornit (mytest.py). Operatiile
	ruleaza pe firul asistentei: nimic din C++ (nici timere, nici eDVBLocalTimeHandler), numai ce tine sincronizatorul in
	Python (starea orei vazuta ultima data pe firul enigma2, stare_vazuta)."""
	from Components import HdsCeas as C
	s = C._unic[0]
	if s is None:
		return None
	cod = s.stare_vazuta
	return {"mod": s.mod(), "server": s.server(), "in_curs": s.proces is not None,
		"transponder_pornit": bool(s.dvb_pornit),
		"stare_ceas": C.NUME_STARI[cod] if isinstance(cod, int) and 0 <= cod < len(C.NUME_STARI) else "",
		"ultima": dict(s.ultima), "esecuri": s.esecuri, "salvat": C.citesteCeasSalvat(s.cale_ceas) or 0,
		"sigura_salvata": C.citesteCeasSalvat(s.cale_sigura) or 0,
		# a treia sursa, ora prin HTTPS de la serverul nostru (din 0.7.6, CLK)
		"https": dict(getattr(s, "https", None) or {}), "https_in_curs": bool(getattr(s, "https_in_curs", False))}


def _ceas(ctx):
	"""De unde are receptorul ora (greseala 1265: un receptor fara ceas cu baterie ramasese ore in urma): ora UTC de acum,
	sursa aleasa, starea (salvata, provizorie, sigura), ultima incercare NTP cu motivul, esecurile la rand, ora salvata
	si programele NTP din imagine. Numai citiri."""
	import time
	fmt = "%Y-%m-%d %H:%M:%S"
	randuri = ["Ora receptorului (UTC): " + time.strftime(fmt, time.gmtime())]
	try:
		s = (ctx.get("ceas") or _stareCeas)()
	except Exception as e:
		s = False
		randuri.append("Starea: necitita (%s)" % e.__class__.__name__)
	if s:
		u = s.get("ultima") or {}
		randuri.append("Sursa: %s, server %s; ora din transponder %s" % (s.get("mod", "?"), s.get("server", "?"),
			"pornita" if s.get("transponder_pornit") else "oprita"))
		randuri.append("Starea: %s%s" % (s.get("stare_ceas") or "?", ", sincronizare in curs" if s.get("in_curs") else ""))
		if u.get("rezultat") in ("reusit", "esuat"):
			randuri.append("Ultima incercare NTP: %s la %s UTC (%s, %s)%s" % (u["rezultat"],
				time.strftime(fmt, time.gmtime(u.get("ora") or 0)), u.get("server", ""), u.get("program", "") or "-",
				(": " + u["motiv"]) if u.get("motiv") else ""))
		else:
			randuri.append("Ultima incercare NTP: niciuna de la pornire")
		randuri.append("Esecuri NTP la rand: %s" % s.get("esecuri", "?"))
		hx = s.get("https") or {}
		if hx.get("rezultat") in ("reusit", "esuat"):
			randuri.append("Ora prin HTTPS (%s, sursa a treia, dupa NTP nereusit): %s la %s UTC%s%s" % (hx.get("server", ""),
				hx["rezultat"], time.strftime(fmt, time.gmtime(hx.get("ora") or 0)),
				(", ceasul mutat cu %.0f s" % (hx.get("pas_s") or 0.0)) if hx.get("mutat") else
				(", diferenta %.1f s, nemutat" % (hx.get("pas_s") or 0.0) if hx["rezultat"] == "reusit" else ""),
				(": %s (%s)" % (hx.get("motiv", ""), hx.get("detaliu", ""))) if hx["rezultat"] == "esuat" else ""))
		else:
			randuri.append("Ora prin HTTPS: %s" % ("in curs" if s.get("https_in_curs") else "neceruta (NTP a mers sau ora e sigura)"))
		for nume, cheie in (("Ora salvata (fake-hwclock)", "salvat"), ("Ultima ora sigura salvata", "sigura_salvata")):
			v = s.get(cheie) or 0
			randuri.append("%s: %s" % (nume, time.strftime(fmt, time.gmtime(v)) if v else "lipseste"))
	elif s is None:
		randuri.append("Starea: sincronizatorul nu e pornit")
	rad = ctx.get("radacina") or "/"
	programe = [c for c in ("/usr/bin/ntpdate", "/usr/sbin/ntpdate", "/usr/sbin/ntpd", "/usr/bin/ntpd", "/sbin/ntpd",
		"/bin/ntpd") if os.access(os.path.join(rad, c.lstrip("/")), os.X_OK)]
	randuri.append("Programe NTP: " + (" ".join(programe) or "niciunul"))
	return "\n".join(randuri)


def _temperaturi(ctx):
	baza = ctx.get("thermal", "/sys/class/thermal")
	randuri = []
	try:
		for nume in sorted(os.listdir(baza)):
			cale = os.path.join(baza, nume, "temp")
			if os.path.exists(cale):
				val = _citeste(cale, 32).strip()
				randuri.append("%s: %s" % (nume, val))
	except Exception:
		pass
	return "\n".join(randuri) or "(fara senzori)"


# Fisierele de pornire ale tuturor formelor OE-Alliance: STARTUP, STARTUP_<cifre>, STARTUP_RECOVERY, STARTUP_ONCE si
# STARTUP_LINUX_<loc>_BOXMODE_<mod> (hdemmc, AX HD51; asistenta 801539, darog69, 14.11.2026: op placa arata numai STARTUP)
STARTUP_NUME = re.compile(r"^STARTUP(_[A-Z0-9_]{1,40})?$")
MAX_ALTE_BOOT = 100
TEXT_BOOT_NUMAI_STARTUP = "(pe /boot se citesc numai fisierele de pornire STARTUP*; restul numai ca nume, cu citeste /boot)"


def _textStartup(cale):
	"""Textul unui fisier de pornire, sau None cand nu e un fisier obisnuit (legatura, dosar) sau nu se poate citi:
	numai text ASCII de cel mult 4 KiB, altfel "(alt continut, N octeti)". Fisierele STARTUP nu au date de acces."""
	if os.path.islink(cale) or not os.path.isfile(cale):
		return None
	try:
		with open(cale, "rb") as f:
			date = f.read(4097)
	except (IOError, OSError):
		return None
	if len(date) > 4096 or not re.match(rb"^[\t\r\n -~]*$", date):
		return "(alt continut, %d octeti)" % len(date)
	return date.decode("ascii").strip()


def _textePornire(ctx):
	"""Textele fisierelor de pornire (STARTUP_NUME) de pe partitia de pornire, ca sa se vada forma locurilor de pe card
	fara niciun pas al omului, si dedesubt NUMAI numele celorlalte intrari din dosar (fara continut), ca sa se vada forma
	oricarui incarcator."""
	baza = ctx.get("boot", "/boot")
	randuri = []
	alte = []
	try:
		nume = sorted(os.listdir(baza))
	except OSError:
		return "(nu se poate citi)"
	for n in nume:
		text = _textStartup(os.path.join(baza, n)) if STARTUP_NUME.match(n) else None
		if text is None:
			alte.append(n)
		else:
			randuri.append("%s: %s" % (n, text))
	text = "\n".join(randuri) or "(niciun fisier)"
	if alte:
		text += "\nAlte fisiere pe /boot: " + " ".join(alte[:MAX_ALTE_BOOT])
		if len(alte) > MAX_ALTE_BOOT:
			text += " ... inca %d" % (len(alte) - MAX_ALTE_BOOT)
	return text


def _citesteBoot(ctx, cerut):
	"""op citeste pe /boot: dosarul da numai numele intrarilor (felul, marimea, numele, fara continut), iar un fisier se
	citeste numai daca e un fisier de pornire (STARTUP_NUME, _textStartup). /boot nu e o radacina de citire: restul
	partitiei de pornire (nucleul, arborele placii, imaginile de rezerva) ramane necitit."""
	baza = ctx.get("boot", "/boot")
	if cerut.rstrip("/") == "/boot":
		import stat as S
		try:
			nume = sorted(os.listdir(baza))
		except OSError as e:
			return Rezultat(1, text="(nu se poate citi /boot: %s)" % type(e).__name__)
		randuri = []
		for n in nume[:MAX_INTRARI_DOSAR]:
			try:
				st = os.lstat(os.path.join(baza, n))
			except OSError:
				continue
			fel = "d" if S.S_ISDIR(st.st_mode) else ("l" if S.S_ISLNK(st.st_mode) else ("f" if S.S_ISREG(st.st_mode) else "c"))
			randuri.append("%s %10s  %s" % (fel, st.st_size if fel == "f" else "-", n + ("/" if fel == "d" else "")))
		return Rezultat(0, text="/boot:\n" + ("\n".join(randuri) or "(dosar gol)"))
	n = cerut[len("/boot/"):]
	if "/" in n or not STARTUP_NUME.match(n):
		return Rezultat(1, text=TEXT_BOOT_NUMAI_STARTUP)
	text = _textStartup(os.path.join(baza, n))
	if text is None:
		return Rezultat(1, text="(nu exista: %s)" % cerut)
	return Rezultat(0, text=text)


def op_placa(ctx, args):
	parti = [
		"Procesor:\n" + _citeste("/proc/cpuinfo", 16384).strip(),
		"Linia de comanda: " + _citeste("/proc/cmdline", 4096).strip(),
		"Partitii:\n" + _citeste("/proc/partitions", 8192).strip(),
		"UUID si tipul partitiilor (blkid):\n" + _textBlkid(ctx),
		"/dev/.newMB-uuid:\n" + _textNewMbUuid(ctx),
		"Fisierele de pornire:\n" + _textePornire(ctx),
		"Module:\n" + _citeste("/proc/modules", 32768).strip(),
	]
	return Rezultat(0, text="\n\n".join(parti))


# Legatura UUID -> disc a locurilor de pe disc (root=UUID=... din STARTUP, Components/HdsMultiBoot; Wlad, asistenta 366732):
# fara blkid si fara /dev/.newMB-uuid (scris de initramfs-ul nucleului comun, AS11 8342a0ff3) echipa nu vede ce disc are
# UUID-ul din linia de comanda si nici daca nucleul pornit stie root=UUID (TODO 14.11 00:20). Numai citire, cu termen.
NEWMB_UUID = "/dev/.newMB-uuid"


def _textBlkid(ctx):
	ruleaza = ctx.get("ruleaza", _ruleaza)
	cod, text = ruleaza(["blkid"], termen=TERMEN_CITIRE_S, limita=16384)
	text = (text or "").strip()
	if cod == 124:
		return "(blkid nu a raspuns in %d s)" % TERMEN_CITIRE_S
	if cod != 0 and not text:
		return "(blkid nu e disponibil sau nu a gasit nicio partitie, cod %s)" % cod
	return text or "(blkid nu a gasit nicio partitie)"


def _textNewMbUuid(ctx):
	cale = ctx.get("newmb_uuid", NEWMB_UUID)
	if not os.path.lexists(cale):
		return "(nu exista: initramfs-ul nucleului pornit nu l-a scris)"
	text = _citeste(cale, 512).strip().replace("\x00", " ")
	return "exista: " + (text or "(gol)")


def op_pachete(ctx, args):
	cod, text = _ruleaza(["opkg", "list-installed"])
	return Rezultat(cod, text=text)


def op_retea(ctx, args):
	parti = []
	cod, rute = _ruleaza(["ip", "route"], limita=8192)
	parti.append("Rute:\n" + rute.strip())
	cod, adrese = _ruleaza(["ip", "-o", "addr"], limita=8192)
	parti.append("Adrese:\n" + adrese.strip())
	cod, wifi = _ruleaza(["iw", "dev"], limita=8192)
	if cod == 0 and wifi.strip():
		parti.append("Wi-Fi:\n" + wifi.strip())
	dns = []
	for rand in _citeste("/etc/resolv.conf", 4096).splitlines():
		if rand.strip().startswith("nameserver"):
			dns.append(rand.strip())
	parti.append("DNS:\n" + ("\n".join(dns) or "(niciunul)"))
	return Rezultat(0, text="\n\n".join(parti))


def op_tunere(ctx, args):
	# fisierul intreg, cu toate campurile scrise de driver (Type, Name, Frontend_Device, I2C_Device, Mode, Has_Outputs,
	# Internally_Connectable...; unele drivere, de pilda Vu+ 4K, scriu numai primele trei), cu citiri mici, ca un driver
	# care refuza citirile mari sau a doua citire sa dea totusi textul (randul TODO 14.11 17:41)
	cod, octeti, eroare = _citesteBucati(ctx.get("nim_sockets", "/proc/bus/nim_sockets"), 0, 65536, TERMEN_CITIRE_S)
	nim = octeti.decode("utf-8", "replace").strip()
	if eroare and not nim:
		nim = "(nu se poate citi nim_sockets: %s)" % eroare
	parti = ["Tunere:\n" + (nim or "(fara)")]
	stari = _stari_frontend(ctx)
	if stari:
		parti.append("Stare frontend:\n" + stari)
	# ce alte fisiere are fiecare tuner in /proc/stb/frontend (fbc_connect, fbc_link, mode...): numai numele, de citit
	# cu "citeste" (unele noduri nu se citesc pe toate placile)
	numele = _numeFrontend(ctx)
	if numele:
		parti.append("/proc/stb/frontend (cu citeste):\n" + numele)
	# placile HiSilicon (V20, V30, V40, SF8008): randul portului din /proc/msp/tuner (i2c, demodulatorul si tunerul,
	# cu adresele lor; dupa el recunoaste placa hds-blindscan) si numele celorlalte fisiere, de citit cu "citeste"
	msp = ctx.get("msp", "/proc/msp")
	if os.path.isfile(os.path.join(msp, "tuner")):
		parti.append("/proc/msp/tuner:\n" + _citeste(os.path.join(msp, "tuner"), 16384).strip())
	if os.path.isdir(msp):
		try:
			parti.append("/proc/msp (cu citeste): " + " ".join(sorted(os.listdir(msp))))
		except Exception:
			pass
	return Rezultat(0, text="\n\n".join(parti))


# ---------------------------------------------------------------- citirea unui fisier sau a unui dosar (op "citeste")
# Eduard, 01.11.2026 23:40: asistenta vede tot hardware-ul si tot ce e pe receptor; din 12.11.2026 19:19 si modulele de
# acces si datele omului, fara parole (vezi capul fisierului). Caile primite au trecut de tiparul din catalog (numai sub RADACINI_CITIRE, fara
# spatii); aici: realpath (legaturile simbolice si ".." se rezolva, iar locul real trebuie sa ramana sub
# RADACINI_REALE: /proc/<pid>/fd, /proc/<pid>/root sau o legatura din /tmp spre un disc cad), apoi LOCURI_OPRITE si
# LOCURI_NESIGURE pe calea ceruta si pe cea reala. Numai fisiere obisnuite (si cele din /proc, /sys) si dosare: un FIFO
# sau un socket din /tmp ar tine sesiunea pe loc. Fisierul se citeste prin head (termen si plafon, ca un extern), iar
# raspunsul trece prin mascheaza (numai parolele ca stelute). Din 12.11.2026 19:19 (Eduard: „FARA PAROLE, ATAT”) se citesc
# si fisierele modulelor de acces (jurnalele din /tmp si /var/log, /etc/init.d, /etc/tuxbox/config, oscam.server,
# CCcam.cfg), setarile intregi, Wi-Fi-ul, IPTV-ul, linia de comanda a proceselor: toate cu parolele mascate.
# Din 0.7.5 si pluginurile si fisierele interfetei (asistenta 423813, NeoBoot: .location si codul unui plugin strain
# care cade; TODO 14.11 17:55), numai citire: /usr/lib/enigma2/python/Plugins si /usr/share/enigma2. Restul lui /usr nu.
RADACINI_USR = ("/usr/lib/enigma2/python/Plugins", "/usr/share/enigma2")
RADACINI_CITIRE = ("/proc", "/sys", "/etc", "/var/log", "/home/root/logs", "/tmp") + RADACINI_USR
# unde duc pe receptor (OE: /var/log -> /var/volatile/log, /tmp -> /var/volatile/tmp)
RADACINI_REALE = RADACINI_CITIRE + ("/var/volatile/log", "/var/volatile/tmp")
# sub RADACINI_USR, in plus: cheile modulelor de acces lasate de unele pluginuri (constant.cw, dosarele keys; fisierele
# *.key sunt inchise oricum, din LOCURI_OPRITE)
LOCURI_OPRITE_USR = re.compile(r"(?i)\.cw$|(?:^|/)keys?(?:/|$)")
# o cale (sau tinta unei legaturi, ori locul dupa "..") din afara radacinilor: spus ca atare, nu ca fisier de parole (tinta nu
# se scrie: poate fi numele unui film sau al unui fisier personal de pe disc)
TEXT_IN_AFARA = ("(in afara cailor permise: calea sau tinta legaturii nu e sub /proc, /sys, /etc, /var/log, "
	"/home/root/logs, /tmp, /usr/lib/enigma2/python/Plugins sau /usr/share/enigma2; discurile nu se citesc)")
# Inchise raman numai fisierele care sunt ele insele parole sau chei private (formatul lor nu are o eticheta dupa care
# sa se mascheze parola): parolele sistemului (shadow, smbpasswd, htpasswd, .netrc, chap-secrets), cheile SSH si TLS,
# VPN-ul si WireGuard (numele, parola si cheia privata), fisierele *.key (cheile TLS si listele de chei), jetoanele si
# secretele conturilor (tin loc de parola) si cheile noastre (/etc/enigma2/hdsatelit/*.bin, hdsatelit-ssh).
LOCURI_OPRITE = re.compile(
	r"(?:^|/)g?shadow(?:[.~-]|$)|smbpasswd|htpasswd|passdb\.tdb|netrc|(?:chap|pap)-secrets|"
	r"hdsatelit-ssh|(?:^|/)\.?ssh(?:/|_|$)|dropbear|ssl/private|\.pem$|\.key$|\.p12$|\.pfx$|"
	r"vpn|wireguard|(?:^|/)wg\d|jeton|token|secret|"
	r"^/etc/enigma2/hdsatelit/[^/]*\.bin$")
# Nu tin secrete, dar nu se citesc: memoria bruta si fluxurile nucleului care nu se termina (ar tine sesiunea pana la
# termen sau ar citi memoria altor procese).
LOCURI_NESIGURE = re.compile(r"kcore|kmsg|pagemap|trace_pipe|(?:^|/)mem$")
TERMEN_CITIRE_S = 10
MAX_INTRARI_DOSAR = 2000
TEXT_CITIRE_OPRITA = "(inchis: fisierele de parole si cheile private nu se citesc; din rest se ascund numai parolele)"
# fisierele din /proc/stb pe care restul imaginii nu le citeste (Components/HdsProcFundal.nodOprit): numele da, continutul nu
TEXT_NOD_OPRIT = "(necitit: pe aceasta placa citirea poate opri nucleul sau poate astepta la nesfarsit)"


def _oprit(cale):
	c = (cale or "").lower()
	if LOCURI_OPRITE.search(c) or LOCURI_NESIGURE.search(c):
		return True
	return _sub(cale or "", RADACINI_USR) and bool(LOCURI_OPRITE_USR.search(c))


def _hisilicon(ctx):
	"""Placa are /proc/msp, ca in Components/HdsSunet.py; probele dau ctx["msp"] sau ctx["radacina"]."""
	return os.path.isdir(ctx.get("msp") or ctx.get("radacina", "").rstrip("/") + "/proc/msp")


def _sub(cale, radacini):
	return any(cale == r or cale.startswith(r + "/") for r in radacini)


# Ghidul tinut minte (Components/HdsEpgSalvare.CALE) e binar, de 7-50 MB: in loc de octeti, op citeste da pe el limbile
# ghidului pe fiecare canal (Components/HdsEpgDatLimbi.py; asistenta 615583, 12.11.2026: ghidul numai in maghiara). Numai
# citire, intr-un proces separat cu termen, ca interfata si asistenta sa nu astepte dupa un fisier mare.
EPG_DAT = "/home/root/epg.dat"
TERMEN_EPG_S = 50          # sub ASTEPTARE_IMPLICITA_S (60 s) a panoului echipei (unelte/asistenta/panou_client.py)


def _caleGhid(ctx):
	"""Unde e ghidul acum: din 0.7.5 locul se alege (memoria sau un stick/disc, Components/HdsEpgSalvare), iar calea
	efectiva sta in config.misc.epgcache_filename (EPS, TODO 13.11 21:40: cu ghidul pe stick raspunsul era "nu exista").
	Probele dau ctx["epg_cale"]; fara setare (sau goala), EPG_DAT."""
	if "epg_cale" in ctx:
		cale = ctx.get("epg_cale")
	else:
		cale = None
		try:
			from Components.config import config
			cale = config.misc.epgcache_filename.value
		except Exception:
			cale = None
	cale = str(cale or "").strip()
	return cale if cale.startswith("/") else EPG_DAT


def _citesteEpgDat(ctx, radacina):
	"""Rezumatul limbilor din ghidul tinut minte (EPG_DAT sau locul ales, _caleGhid); calea reala poate fi o legatura
	(pe un disc), dar tot un epg.dat obisnuit. Raspunsul spune ce fisier s-a citit."""
	ghid = _caleGhid(ctx)
	plin = os.path.realpath(radacina + ghid)
	if os.path.basename(plin) != "epg.dat" or _oprit(plin):
		return Rezultat(1, text=TEXT_CITIRE_OPRITA)
	try:
		st = os.stat(plin)
	except Exception:
		return Rezultat(1, text="(nu exista: %s; ghidul nu a fost inca salvat)" % ghid)
	import stat as S
	if not S.S_ISREG(st.st_mode):
		return Rezultat(1, text="(nu e un fisier obisnuit: %s)" % ghid)
	python = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	program = ("import sys; sys.path.insert(0, %r); from Components.HdsEpgDatLimbi import main; "
		"sys.exit(main(sys.argv[1:]))" % python)
	ruleaza = ctx.get("ruleaza", _ruleaza)
	# prioritate mica: interfata nu simte citirea; memoria o plafoneaza procesul insusi (HdsEpgDatLimbi.PLAFON_MEMORIE)
	argv = list(ctx.get("prioritate", ("nice", "-n", "19"))) + [ctx.get("python", "python3"), "-c", program, plin]
	cod, text = ruleaza(argv, termen=TERMEN_EPG_S)
	if cod == 124:
		return Rezultat(1, text="(%s nu s-a putut citi in %d s)" % (ghid, TERMEN_EPG_S))
	if ghid != EPG_DAT:
		text = "(ghidul e in locul ales: %s)\n%s" % (ghid, text)
	return Rezultat(cod, text=text)


def op_citeste(ctx, args):
	"""Un fisier (continutul, cel mult RASPUNS_MAX) sau un dosar (lista: felul, marimea, numele) de sub
	RADACINI_CITIRE; ctx["radacina"] muta totul intr-un dosar de proba. EPG_DAT: limbile ghidului, nu octetii."""
	radacina = ctx.get("radacina", "").rstrip("/")
	cerut = "/" + (args[0] if args else "").strip("/")
	de_la = _deLa(args, 1)
	if cerut == EPG_DAT:
		return _citesteEpgDat(ctx, radacina)
	if _sub(cerut, ("/boot",)):
		return _citesteBoot(ctx, cerut)
	if _oprit(cerut):
		return Rezultat(1, text=TEXT_CITIRE_OPRITA)
	if not _sub(cerut, RADACINI_CITIRE):
		return Rezultat(1, text=TEXT_IN_AFARA)
	hisilicon = _hisilicon(ctx)
	if nodOprit(cerut, hisilicon):
		return Rezultat(1, text=TEXT_NOD_OPRIT)
	try:
		baza = os.path.realpath(radacina) if radacina else ""

		def _real(cale):
			plin = os.path.realpath(radacina + cale)
			if baza and not (plin == baza or plin.startswith(baza + os.sep)):
				return plin, None
			return plin, "/" + plin[len(baza):].replace(os.sep, "/").strip("/")
		real_plin, real = _real(cerut)
		# radacina ceruta poate fi ea insasi o legatura (de pilda jurnalele mutate pe disc): locul ei real e permis,
		# numai pentru caile de sub ea
		_p, rad_real = _real([r for r in RADACINI_CITIRE if _sub(cerut, (r,))][0])
	except Exception:
		return Rezultat(1, text="(cale necunoscuta)")
	reale = RADACINI_REALE + ((rad_real,) if rad_real and rad_real != "/" else ())
	if real is not None and _oprit(real):
		return Rezultat(1, text=TEXT_CITIRE_OPRITA)
	if real is None or not _sub(real, reale):
		# o legatura din /etc/rcS.d spre /usr/bin, o legatura spre disc: nu e un fisier de parole (asistenta 423813)
		return Rezultat(1, text=TEXT_IN_AFARA)
	# dupa legaturi si dupa "..": tot acelasi fisier
	if nodOprit(real, hisilicon):
		return Rezultat(1, text=TEXT_NOD_OPRIT)
	try:
		st = os.stat(real_plin)
	except Exception:
		return Rezultat(1, text="(nu exista: %s)" % cerut)
	import stat as S
	if S.S_ISDIR(st.st_mode):
		return Rezultat(0, text=_dosar(real_plin, real, hisilicon))
	if not S.S_ISREG(st.st_mode):
		return Rezultat(1, text="(nu e un fisier obisnuit: %s)" % cerut)
	if de_la is not None:
		# "de la octetul" (randurile AS16, TODO 14.11 13:27 si 17:30): orice bucata a unui fisier mai mare decat plafonul
		return _bucataDeLa(real_plin, cerut, de_la, st.st_size)
	ruleaza = ctx.get("ruleaza", _ruleaza)
	# un fisier mai mare decat plafonul (un jurnal care creste): ultimul MB, unde e ce s-a intamplat acum, nu primul
	# (asistenta 252913); fisierele din /proc si /sys au marimea 0 si raman pe head
	coada = st.st_size > RASPUNS_MAX
	unealta = "tail" if coada else "head"
	cod, text = ruleaza([unealta, "-c", str(COADA_MAX if coada else RASPUNS_MAX + 1), real_plin],
		termen=TERMEN_CITIRE_S)
	if cod == 124:
		return Rezultat(1, text="(%s nu s-a putut citi in %d s)" % (cerut, TERMEN_CITIRE_S))
	if cod != 0 and st.st_size == 0 and _sub(real, ("/proc", "/sys")):
		# un driver care refuza citirea lui head (Input/output error la /proc/bus/nim_sockets pe Vu+ 4K, asistenta
		# 636002): inca o data, cu citirile mici din Python, ca op tunere; dupa un termen (124) nu se mai incearca
		cod2, octeti, eroare = _citesteBucati(real_plin, 0, RASPUNS_MAX + 1, TERMEN_CITIRE_S)
		if octeti or cod2 == 0:
			text = octeti.decode("utf-8", "replace")
			if eroare:
				text += "\n(citirea s-a oprit dupa %d octeti: %s)" % (len(octeti), eroare)
			cod = 0
	text = text.replace("\x00", " ")
	if coada and cod == 0:
		# primul rand poate fi taiat la jumatate
		text = "(fisierul are %d octeti: se arata ultimii %d)\n%s" % (st.st_size, COADA_MAX, text.split("\n", 1)[-1])
	return Rezultat(cod, text=text)


def _deLa(args, i):
	"""Argumentul "de la octetul" (cifre, verificate de catalog) de pe locul i, sau None cand lipseste."""
	if len(args) > i and args[i] not in (None, ""):
		try:
			return max(0, int(args[i]))
		except (TypeError, ValueError):
			return None
	return None


def _capBucata(de_la, lungime, marime):
	"""Randul de sus al unei bucati citite "de la octetul": ce octeti sunt si de unde continua cererea urmatoare."""
	sfarsit = de_la + lungime
	if sfarsit < marime:
		return "(fisierul are %d octeti: se arata octetii %d-%d; urmatorul: de la %d)" % (marime, de_la, sfarsit, sfarsit)
	return "(fisierul are %d octeti: se arata octetii %d-%d, pana la sfarsit)" % (marime, de_la, sfarsit)


def _bucataDeLa(real_plin, cerut, de_la, marime):
	"""Bucata de cel mult COADA_MAX octeti a unui fisier, de la octetul de_la, cu randul de sus (_capBucata)."""
	if marime and de_la >= marime:
		return Rezultat(1, text="(fisierul are %d octeti: de la %d nu mai e nimic)" % (marime, de_la))
	cod, octeti, eroare = _citesteBucati(real_plin, de_la, COADA_MAX, TERMEN_CITIRE_S)
	if cod == 124 and not octeti:
		return Rezultat(1, text="(%s nu s-a putut citi in %d s)" % (cerut, TERMEN_CITIRE_S))
	text = octeti.decode("utf-8", "replace").replace("\x00", " ")
	if eroare:
		text += "\n(citirea s-a oprit dupa %d octeti: %s)" % (len(octeti), eroare)
	return Rezultat(0 if octeti else cod, text="%s\n%s" % (_capBucata(de_la, len(octeti), max(marime, de_la + len(octeti))),
		text))


def _dosar(real_plin, real, hisilicon=False):
	"""Lista unui dosar: d (dosar), f (fisier, cu marimea), l (legatura, fara tinta: in /proc tintele sunt fisierele
	deschise, deci si filmele omului), altele cu felul lor; cele oprite apar "(inchis)"; cele ale modulelor de acces apar
	ca oricare altele (Eduard, 12.11.2026 19:17)."""
	import stat as S
	try:
		nume = sorted(os.listdir(real_plin))
	except Exception as e:
		return "(nu se poate citi dosarul: %s)" % type(e).__name__
	randuri = []
	for n in nume[:MAX_INTRARI_DOSAR]:
		cale = real.rstrip("/") + "/" + n
		try:
			st = os.lstat(os.path.join(real_plin, n))
		except Exception:
			continue
		if S.S_ISDIR(st.st_mode):
			fel, marime, arata = "d", "-", n + "/"
		elif S.S_ISREG(st.st_mode):
			fel, marime, arata = "f", str(st.st_size), n
		elif S.S_ISLNK(st.st_mode):
			fel, marime, arata = "l", "-", n
		else:
			fel, marime, arata = "c" if S.S_ISCHR(st.st_mode) else ("p" if S.S_ISFIFO(st.st_mode) else "s"), "-", n
		if _oprit(cale):
			arata += "  (inchis)"
		elif not S.S_ISDIR(st.st_mode) and nodOprit(cale, hisilicon):
			arata += "  (necitit)"
		randuri.append("%s %10s  %s" % (fel, marime, arata))
	if len(nume) > MAX_INTRARI_DOSAR:
		randuri.append("... inca %d" % (len(nume) - MAX_INTRARI_DOSAR))
	return "%s:\n%s" % (real, "\n".join(randuri) or "(dosar gol)")


def _stari_frontend(ctx):
	baza = ctx.get("dvb", "/proc/stb/frontend")
	randuri = []
	try:
		for nume in sorted(os.listdir(baza)):
			cale = os.path.join(baza, nume)
			if os.path.isdir(cale):
				for sub in ("status", "ber", "snr", "signal_power"):
					c = os.path.join(cale, sub)
					if os.path.exists(c):
						randuri.append("%s/%s: %s" % (nume, sub, _citeste(c, 64).strip()))
	except Exception:
		pass
	return "\n".join(randuri)


def _numeFrontend(ctx):
	baza = ctx.get("dvb", "/proc/stb/frontend")
	randuri = []
	try:
		for nume in sorted(os.listdir(baza)):
			cale = os.path.join(baza, nume)
			if os.path.isdir(cale):
				randuri.append("%s: %s" % (nume, " ".join(sorted(os.listdir(cale)))))
	except Exception:
		pass
	return "\n".join(randuri[:64])


def op_decodor(ctx, args):
	baza = ctx.get("stb", "/proc/stb")
	tinte = ("avs", "audio", "video", "vmpeg", "sync", "stream")
	hisilicon = _hisilicon(ctx)
	randuri = []
	for rad, _dirs, fisiere in _umbla(baza):
		for f in fisiere:
			if any(t in rad or t in f for t in tinte):
				cale = os.path.join(rad, f)
				rel = cale[len(baza):].lstrip("/\\")
				# numai numele: citirea fisierelor din lista opreste nucleul pe unele placi (Components/HdsProcFundal.nodOprit)
				val = "(necitit)" if nodOprit(rel, hisilicon) else _citeste(cale, 256).strip().replace("\n", " ")
				randuri.append("%s = %s" % (rel, val))
			if len(randuri) > 400:
				break
	return Rezultat(0, text="\n".join(randuri) or "(fara date de decodor)")


def _umbla(baza, adancime=3):
	baza = baza.rstrip("/")
	nivel_baza = baza.count("/")
	try:
		for rad, dirs, fisiere in os.walk(baza):
			if rad.count("/") - nivel_baza >= adancime:
				del dirs[:]
			yield rad, dirs, fisiere
	except Exception:
		return


def op_memorie(ctx, args):
	parti = ["Memorie:\n" + _citeste("/proc/meminfo", 4096).strip()]
	masura = ctx.get("memorie_driver")
	if masura is None:
		try:
			from Components import HdsMemorieDriver
			masura = HdsMemorieDriver.masoara()
		except Exception as e:
			masura = None
			parti.append("Memoria decodorului: (nu se poate masura: %s)" % type(e).__name__)
	if masura:
		parti.append("Memoria decodorului: " + str(masura))
	return Rezultat(0, text="\n\n".join(parti))


# Jurnalul paznicului (hds-watchdog.py, Components/HdsPaznic.CALE_JURNAL) sta in /home/root, nu in dosarul jurnalelor:
# op jurnale il arata in lista, iar op jurnal il citeste sub numele lui (si cu "de la octetul"), ca pe celelalte (asistenta
# 430032, 15.11.2026: pornirile si cererile de iesire ale paznicului nu se puteau citi; TODO 15.11 10:50, RFU). Numai acest
# fisier: restul lui /home/root ramane in afara.
JURNAL_PAZNIC = "hds-watchdog.log"


def _caleJurnalPaznic(ctx, baza):
	"""Calea jurnalului paznicului: ctx["jurnal_paznic"] (probele); cu dosarul jurnalelor obisnuit, HdsPaznic.CALE_JURNAL;
	cu un dosar de proba (ctx["jurnale"]), fisierul de langa el, ca pe receptor (/home/root/logs -> /home/root)."""
	if "jurnal_paznic" in ctx:
		return ctx["jurnal_paznic"]
	if baza == CALE_JURNALE:
		try:
			from Components.HdsPaznic import CALE_JURNAL
			return CALE_JURNAL
		except Exception:
			pass
	return os.path.join(os.path.dirname(baza.rstrip("/\\")), JURNAL_PAZNIC)


def op_jurnale(ctx, args):
	baza = ctx.get("jurnale", CALE_JURNALE)
	randuri = []
	try:
		nume_vazute = sorted(os.listdir(baza))
		for nume in nume_vazute:
			cale = os.path.join(baza, nume)
			if os.path.isfile(cale):
				randuri.append("%10d  %s" % (os.path.getsize(cale), nume))
	except Exception as e:
		return Rezultat(1, text="(nu se poate citi dosarul jurnalelor: %s)" % type(e).__name__)
	paznic = _caleJurnalPaznic(ctx, baza)
	if JURNAL_PAZNIC not in nume_vazute and os.path.isfile(paznic) and not os.path.islink(paznic):
		randuri.append("%10d  %s" % (os.path.getsize(paznic), JURNAL_PAZNIC))
	return Rezultat(0, text="\n".join(randuri) or "(niciun jurnal)")


# Jurnalele pe care le scrie imaginea (hds-*.log si rotirile lor, messages): cand lipsesc, "nu exista inca" (0.7.7,
# asistenta 683170, TODO 16.11 00:10: seq 1 automat cere hds-caderi.log, care lipseste pe un receptor fara nicio cadere,
# iar raspunsul "(jurnal necunoscut)" il facea pe operator sa creada ca a gresit numele).
_JURNAL_IMAGINE = re.compile(r"^(?:hds-[a-z0-9-]+\.log|messages)(?:\.[0-9]{1,2})?$")


def _textJurnalLipsa(nume, cale):
	"""Raspunsul lui op jurnal cand fisierul nu e de citit: "nu exista inca" pentru un jurnal al imaginii care lipseste;
	"necunoscut" pentru alt nume (cu sfatul op jurnale, care da lista) si cand numele e altceva decat un fisier (un
	dosar, o legatura spre afara)."""
	if os.path.lexists(cale):
		return "(jurnal necunoscut)"
	if _JURNAL_IMAGINE.match(nume):
		return "(jurnalul nu exista inca: %s)" % nume
	return "(jurnal necunoscut: %s; op jurnale da lista)" % nume


def op_jurnal(ctx, args):
	nume = args[0]
	randuri = int(args[1]) if len(args) > 1 and args[1] else 500
	randuri = max(1, min(randuri, MAX_RANDURI_JURNAL))
	baza = ctx.get("jurnale", CALE_JURNALE)
	# numai un fisier chiar din dosarul jurnalelor (realpath, fara legaturi simbolice spre afara)
	cale = os.path.join(baza, nume)
	try:
		real = os.path.realpath(cale)
		if os.path.dirname(real) != os.path.realpath(baza) or not os.path.isfile(real):
			real = None
		if real is None and nume == JURNAL_PAZNIC:
			# jurnalul paznicului, de langa dosarul jurnalelor (JURNAL_PAZNIC): numai fisierul lui, fara legaturi
			paznic = _caleJurnalPaznic(ctx, baza)
			if os.path.isfile(paznic) and not os.path.islink(paznic):
				real = os.path.realpath(paznic)
		if real is None:
			return Rezultat(1, text=_textJurnalLipsa(nume, cale))
	except Exception:
		return Rezultat(1, text="(jurnal necunoscut)")
	de_la = _deLa(args, 2)
	if de_la is not None:
		# "de la octetul" (randul AS16): primele `randuri` randuri de acolo (fara numar: toate, cel mult
		# MAX_RANDURI_JURNAL), cu randul de sus care spune de unde continua cererea urmatoare
		if not (len(args) > 1 and args[1]):
			randuri = MAX_RANDURI_JURNAL
		marime = os.path.getsize(real)
		rez = _bucataDeLa(real, nume, de_la, marime)
		if rez.cod_iesire != 0:
			return rez
		cap, _sep, text = rez.text.partition("\n")
		primele = text.split("\n")[:randuri]
		lungime = len("\n".join(primele).encode("utf-8", "replace"))
		if len(primele) < len(text.split("\n")):
			lungime += 1
			cap = _capBucata(de_la, lungime, marime)
		return Rezultat(0, text="%s\n%s" % (cap, "\n".join(primele)))
	# coada fisierului, nu inceputul (asistenta 252913: hds-interfata.log are 1,5 MB pe SF8008 si se intorcea mijlocul)
	text = _citesteCoada(real, COADA_MAX)
	ultimele = text.splitlines()[-randuri:]
	return Rezultat(0, text="\n".join(ultimele))


def op_dmesg(ctx, args):
	randuri = int(args[0]) if args and args[0] else 500
	randuri = max(1, min(randuri, MAX_RANDURI_JURNAL))
	cod, text = _ruleaza(["dmesg"])
	return Rezultat(cod, text="\n".join(text.splitlines()[-randuri:]))


def op_procese(ctx, args):
	baza = ctx.get("proc", "/proc")
	randuri = []
	try:
		for nume in sorted(os.listdir(baza), key=lambda n: int(n) if n.isdigit() else 0):
			if not nume.isdigit():
				continue
			comm = _citeste(os.path.join(baza, nume, "comm"), 128).strip()
			if comm:
				randuri.append("%6s  %s" % (nume, comm))
	except Exception as e:
		return Rezultat(1, text="(nu se pot citi procesele: %s)" % type(e).__name__)
	return Rezultat(0, text="\n".join(randuri))


# Citirea permite setarile tuturor ecranelor deschise (si ale modulelor de acces, config.softcam..., din 12.11.2026);
# scrierea isi pastreaza lista separata din Control.
SETARI_PERMISE = ("config.",)
# o setare care tine o parola, un PIN (al controlului parental) sau cheia cu care receptorul trimite ca tester
# (config.hds_beta.id, tine loc de parola la serverul nostru): valoarea intreaga devine ***; la fel cheile care se termina
# in token (config.plugins.hdswebcontrol.token e cheia de acces a interfetei web pentru scripturi; AS12, TODO 14.11 01:25)
_CHEIE_PAROLA = re.compile(r"(?i)(?:password|passwd|passphrase|pwd|parol|wep_key|(?:^|[._-])(?:pass|psk)[0-9]*$|pin(?:[._]?[0-9]+)?$|"
	r"(?:^|[._-])token$|"
	r"^config\.hds_beta\.(?:id|cod)$)")


def op_setari(ctx, args):
	cale = ctx.get("settings", "/etc/enigma2/settings")
	randuri = []
	for rand in _citeste(cale, 512 * 1024).splitlines():
		rand = rand.strip()
		if "=" not in rand:
			continue
		cheie = rand.split("=", 1)[0]
		if not any(cheie.startswith(p) for p in SETARI_PERMISE):
			continue
		if _CHEIE_PAROLA.search(cheie):
			rand = cheie + "=***"
		randuri.append(mascheazaParole(rand))
	return Rezultat(0, text="\n".join(randuri) or "(nicio setare in lista permisa)")


def op_captura(ctx, args):
	"""O captura video cu OSD, ca pe televizor."""
	faca = ctx.get("captura")
	if faca is None:
		return Rezultat(1, text="(captura nu e disponibila)")
	octeti = faca()
	if not octeti:
		return Rezultat(1, text="(captura nu s-a putut face acum)")
	if isinstance(octeti, str):
		# refuzul unelte (interfata nu e gata): textul lui
		return Rezultat(1, text=octeti)
	if len(octeti) > CAPTURA_MAX:
		return Rezultat(1, text="(captura prea mare)")
	from Components.HdsCapturi import felPoza, N_, _t
	tip = felPoza(octeti)
	if not tip:
		return Rezultat(1, text=_t(N_("(captura nu este JPG sau PNG)")))
	return Rezultat(0, octeti=octeti, tip=tip)


def op_ecran(ctx, args):
	"""Textul ecranului de sus (stiva, listele cu randul ales, setarile, textele), ca echipa sa mearga prin meniuri fara
	poze (Components/HdsAsistentaControl.textEcran), la fel ca pe televizor; textul trece prin filtrul de mai jos."""
	citeste = ctx.get("ecran")
	if citeste is None:
		return Rezultat(1, text="(ecranul nu se poate citi)")
	text = citeste()
	if text is None:
		return Rezultat(1, text="(ecranul nu a raspuns la timp)")
	return Rezultat(0, text=text)


def _controlPermis(ctx):
	return ctx.get("nivel") == "B"


# raspunsul unui op de control intr-o sesiune numai de citire (nivelul A, reluata de pe o imagine de dinainte de
# 0.6.16, cand omul putea debifa Control complet)
TEXT_FARA_CONTROL = "(control oprit: sesiune numai de citire; omul porneste din nou asistenta, care e completa)"


def op_taste(ctx, args):
	"""Tastele telecomenzii (lista alba, cel mult MAX_TASTE), apasate pe rand pe firul enigma2; raspunsul spune ce s-a
	apasat si da textul ecranului de dupa."""
	if not _controlPermis(ctx):
		return Rezultat(1, text=TEXT_FARA_CONTROL)
	from Components import HdsAsistentaControl as C
	lista, greseli = C.imparteTaste(args[0])
	if greseli:
		return Rezultat(1, text="(taste necunoscute: %s)" % " ".join(greseli[:10]))
	if not lista or len(lista) > C.MAX_TASTE:
		return Rezultat(1, text="(intre 1 si %d taste pe cerere)" % C.MAX_TASTE)
	apasa = ctx.get("taste")
	if apasa is None:
		return Rezultat(1, text="(tastele nu se pot trimite)")
	rez = apasa(lista)
	if rez is None:
		return Rezultat(1, text="(receptorul nu a terminat tastele la timp)")
	cod, text = rez
	return Rezultat(cod, text=text)


def op_text(ctx, args):
	"""Un text scris in campul deschis (tastatura de pe ecran sau randul de setare in modul text); refuzat pe ecranele
	si campurile private."""
	if not _controlPermis(ctx):
		return Rezultat(1, text=TEXT_FARA_CONTROL)
	scrie = ctx.get("text")
	if scrie is None:
		return Rezultat(1, text="(textul nu se poate scrie)")
	rez = scrie(args[0])
	if rez is None:
		return Rezultat(1, text="(receptorul nu a raspuns la timp)")
	cod, text = rez
	return Rezultat(cod, text=text)


def op_mesaj(ctx, args):
	"""Un mesaj scris pe ecranul televizorului; omul vede limpede ca vine de la HD Satelit."""
	arata = ctx.get("mesaj")
	text = args[0]
	if arata is None:
		return Rezultat(1, text="(mesajul nu se poate arata)")
	arata(text)
	return Rezultat(0, text="mesaj aratat pe ecran: " + text)


def op_intrebare(ctx, args):
	"""O intrebare pe televizor si in pagina web a asistentei (0.7.7, TODO 16.11 01:10): TEXT, apoi variantele ("Da|Nu|Nu
	stiu", 2-4; fara ele Nu / Da, cu Nu ales) si secundele (30-300, implicit 180). Asteapta raspunsul omului pe firul
	sesiunii (ctx["stop"] o opreste) si il da echipei: cod 0 "raspuns: Da ...", cod 1 cand n-a venit (timpul, EXIT,
	oprirea asistentei, standby). Lucrul cu ecranul il face ctx["intrebare"] (Screens/HdsAsistentaSemn._intrebare)."""
	intreaba = ctx.get("intrebare")
	if intreaba is None:
		return Rezultat(1, text="(intrebarea nu se poate arata)")
	rez = intreaba(args[0], args[1] if len(args) > 1 else "", args[2] if len(args) > 2 else "", ctx.get("stop"))
	if not rez:
		return Rezultat(1, text="(receptorul nu a raspuns)")
	cod, text = rez
	return Rezultat(cod, text=text)


def op_concluzii(ctx, args):
	"""Concluziile echipei la finalul asistentei (ce am gasit si ce am facut): pastrate pe receptor si aratate intr-o
	fereastra care sta pana la OK, apoi o data la sfarsitul sesiunii, cu multumirile. Raspunsul nu repeta textul."""
	pune = ctx.get("concluzii")
	if pune is None:
		return Rezultat(1, text="(concluziile nu se pot arata)")
	semne = pune(args[0])
	if not semne:
		return Rezultat(1, text="(concluzii goale)")
	return Rezultat(0, text="concluzii aratate pe ecran: %d semne" % int(semne))


def op_canal(ctx, args):
	"""Canalul deschis: serviciul, PID-urile, transponderul (frecventa, polarizarea, rata), tunerul si semnalul, ca in
	Informatii despre canal; si randurile modulelor de acces (mascheaza ascunde numai parolele)."""
	citeste = ctx.get("canal")
	if citeste is None:
		return Rezultat(1, text="(canalul nu se poate citi)")
	text = citeste()
	if text is None:
		return Rezultat(1, text="(receptorul nu a raspuns la timp)")
	return Rezultat(0, text=text)


def op_flux(ctx, args):
	"""Fluxul prins acum pe tunerul canalului deschis, din tabelele receptionate (PAT, SDT actual, NIT actual), nu din
	lamedb: TSID, ONID, reteaua, pozitia orbitala din descriptorul de livrare, primele servicii (Components/HdsAsistentaFlux;
	TODO 14.11 19:42). Numai citire: canalul omului nu se schimba. De pe firul enigma2 vin numai demuxul si referinta
	(ctx["flux"]); citirea filtrelor (cel mult HdsAsistentaFlux.TERMEN_S) se face aici, pe firul sesiunii.
	Cu argumente (POZITIE FRECVENTA POL [RATA]; TODO 15.11 01:55): pe un tuner LIBER acordat pe transponderul cerut
	(ctx["flux_tp"], pe firul enigma2), fara sa se schimbe canalul omului; tunerul se elibereaza dupa citire
	(ctx["flux_tp_elibereaza"]) si singur, dupa HdsAsistentaFlux.PAZA_S. Fara tuner liber: raspuns clar, nimic schimbat."""
	from Components import HdsAsistentaFlux as F
	cerut, motiv = F.cerere_din_argumente(args)
	if motiv:
		return Rezultat(1, text=motiv)
	if cerut is not None:
		ia_tp = ctx.get("flux_tp")
		if ia_tp is None:
			return Rezultat(1, text="(fluxul pe un transponder ales nu se poate citi pe acest receptor)")
		param = ia_tp(cerut)
		try:
			if param is None:
				return Rezultat(1, text="(receptorul nu a raspuns la timp)")
			if param.get("eroare"):
				return Rezultat(1, text=param["eroare"])
			cod, text = F.citesteText(param, sursa=ctx.get("flux_sursa"), termen=ctx.get("flux_termen", F.TERMEN_S))
		finally:
			elibereaza = ctx.get("flux_tp_elibereaza")
			if elibereaza is not None:
				elibereaza()
		return Rezultat(cod, text=text)
	ia = ctx.get("flux")
	if ia is None:
		return Rezultat(1, text="(fluxul nu se poate citi pe acest receptor)")
	param = ia()
	if param is None:
		return Rezultat(1, text="(receptorul nu a raspuns la timp)")
	cod, text = F.citesteText(param, sursa=ctx.get("flux_sursa"), termen=ctx.get("flux_termen", F.TERMEN_S))
	return Rezultat(cod, text=text)


def op_transpondere(ctx, args):
	"""Transponderele din lista de canale (lamedb), numai sectiunea lor, eventual ale unui singur satelit (namespace)."""
	from Components import HdsAsistentaControl as C
	cale = ctx.get("lamedb", "/etc/enigma2/lamedb")
	text = _citeste(cale, 8 * 1024 * 1024, lista=True)
	return Rezultat(0, text=C.transpondere(text, args[0] if args and args[0] else None))


def _cuControl(ctx, nume, *a):
	"""Ruleaza unealta de control `nume` din ctx (numai la nivelul B). -> Rezultat."""
	if not _controlPermis(ctx):
		return Rezultat(1, text=TEXT_FARA_CONTROL)
	f = ctx.get(nume)
	if f is None:
		return Rezultat(1, text="(%s nu se poate face pe acest receptor)" % nume)
	rez = f(*a)
	if rez is None:
		return Rezultat(1, text="(receptorul nu a raspuns la timp)")
	cod, text = rez
	return Rezultat(cod, text=text)


def op_zap(ctx, args):
	"""Porneste canalul cu referinta data (ca din lista de canale)."""
	return _cuControl(ctx, "zap", args[0])


def op_reporneste(ctx, args):
	"""Reporneste interfata sau receptorul intreg, cu anunt pe ecran; sesiunea continua dupa repornire (fisierul ei de
	stare)."""
	return _cuControl(ctx, "reporneste", args[0])


def op_setare_scrie(ctx, args):
	"""O setare scrisa direct (cheie si valoare ca in fisierul settings), numai sub prefixele permise si niciodata o
	cheie oprita (Components/HdsAsistentaControl.SETARI_SCRIERE, SETARI_OPRITE), prin obiectul config, cu efectele ei."""
	return _cuControl(ctx, "setare", args[0], args[1] if len(args) > 1 else "")


TERMEN_OPKG_S = 300


def _treciPeRezerva(ctx, text):
	"""Dupa un opkg update cu cod de eroare: daca a cazut lista feedului extern de pe moneasoftware.com, sursa trece pe
	serverul de rezerva (Components/HdsPluginuriExterne.dupa_update). True cand a trecut. Nu ridica exceptii."""
	try:
		try:
			from Components import HdsPluginuriExterne as X
		except ImportError:  # probe pe PC
			import HdsPluginuriExterne as X
		return bool(X.dupa_update((text or "").splitlines(), ctx.get("radacina", "/")))
	except Exception as e:
		print("[HdsAsistentaBroker] rezerva feedului extern: %r" % (e,))
		return False


# 0.7.7 (UPD, TODO 15.11 19:08 asistenta 421715 si 16.11 00:10 asistenta 683170): op instaleaza nu mai aduce pe bucati
# pachetele imaginii si nu mai opreste opkg la jumatate.
# - Un pachet care cere o versiune mai noua a imaginii (ServiceApp r11 cere enigma2-hdsatelit >= 0.7.6, IPTVplayer cere
#   ServiceApp) facea opkg sa puna programul imaginii singur, fara restul setului si fara repornirea interfetei: interfata
#   veche peste fisierele noi (caderea "undefined symbol" din 683170), iar o ciocnire cu fisierul unei teme lasa
#   enigma2-hdsatelit half-installed (opkg install fara --force-overwrite; 421715). Acum intai `opkg --noaction install`:
#   daca ar actualiza, ar cobori sau ar scoate un pachet al imaginii instalat (enigma2-hdsatelit, hdsatelit-*), nu se
#   instaleaza nimic si raspunsul spune ce sa trimita echipa (repara-actualizarea = actualizarea rapida, tot setul semnat,
#   cu --force-overwrite si repornirea), ca Extensii in 0.7.7 (EXG).
# - opkg nu mai e oprit cu SIGKILL la termen (fisiere amestecate, status vechi) si nu mai scrie pe o teava (la o iesire a
#   enigma2 ar fi murit de SIGPIPE): iesirea merge intr-un fisier din RAM, opkg ruleaza in sesiunea lui, iar dupa termen
#   raspunsul spune ca lucreaza inca; se culege cand iese.
_OPKG_LASATE = []
_IMAGINE_RAND = re.compile(r"^(?:Installing|Upgrading|Downgrading|Removing)\s+([A-Za-z0-9][A-Za-z0-9+._-]*)", re.M)
STATUS_OPKG = "/var/lib/opkg/status"


def _ruleazaOpkg(argv, termen=TERMEN_S, limita=RASPUNS_MAX):
	"""Ca _ruleaza, pentru opkg: iesirea intr-un fisier temporar (nu pe teava), opkg in sesiunea lui si niciun semnal la
	termen (atunci cod 124 si iesirea de pana acum; procesul se culege la un apel urmator). -> (cod_iesire, text)."""
	import tempfile
	for p in list(_OPKG_LASATE):
		if p.poll() is not None:
			_OPKG_LASATE.remove(p)
	try:
		f = tempfile.TemporaryFile(prefix="hds-asistenta-opkg-")
	except OSError:
		return _ruleaza(argv, termen, limita)
	try:
		try:
			p = subprocess.Popen(argv, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
				env={"LC_ALL": "C", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}, start_new_session=True)
		except Exception as e:
			return 127, "(nu se poate porni %s: %s)" % (argv[0], type(e).__name__)
		try:
			cod = p.wait(timeout=termen)
		except subprocess.TimeoutExpired:
			_OPKG_LASATE.append(p)
			cod = 124
		# pread nu muta pozitia comuna cu opkg (care poate scrie inca, dupa termen)
		if hasattr(os, "pread"):
			date = os.pread(f.fileno(), limita + 1, 0)
		else:
			f.seek(0)
			date = f.read(limita + 1)
		text = date.decode("utf-8", "replace")
	finally:
		f.close()
	if cod == 124:
		text += ("\n(opkg lucreaza inca dupa %d s; nu il opresc, ca pachetele sa nu ramana la jumatate. Urmareste cu op "
			"pachete si op jurnal hds-actualizari.log)" % termen)
	return cod, text


def _instalateImagine(ctx):
	"""Pachetele imaginii instalate acum (enigma2-hdsatelit, hdsatelit-*), din status-ul opkg"""
	rez, nume = set(), ""
	try:
		with open(ctx.get("opkg_status", STATUS_OPKG), "r", encoding="utf-8", errors="replace") as f:
			for rand in f:
				if rand.startswith("Package:"):
					nume = rand.split(":", 1)[1].strip()
				elif rand.startswith("Status:") and _alImaginii(nume):
					st = rand.split(":", 1)[1].split()
					if "not-installed" not in st and "config-files" not in st:
						rez.add(nume)
	except (IOError, OSError):
		pass
	return rez


def _alImaginii(nume):
	return nume == "enigma2-hdsatelit" or nume.startswith("hdsatelit-")


def imagineAtinsa(text, instalate):
	"""Pachetele imaginii instalate pe care un `opkg --noaction install` le-ar schimba (randurile Installing/Upgrading/
	Downgrading/Removing ale lui opkg 0.10), in ordine, fara repetari"""
	rez = []
	for nume in _IMAGINE_RAND.findall(text or ""):
		if _alImaginii(nume) and nume in instalate and nume not in rez:
			rez.append(nume)
	return rez


def _opkg(ctx, actiune, pachet):
	from Components import HdsAsistentaControl as C
	if not _controlPermis(ctx):
		return Rezultat(1, text=TEXT_FARA_CONTROL)
	tipar = C.PACHET_INSTALARE if actiune == "install" else C.PACHET
	if not tipar.match(pachet or ""):
		return Rezultat(1, text="(nume de pachet nepermis)")
	# update, status si proba --noaction nu schimba nimic: cu termen si oprire (o descarcare blocata nu tine lacatul lui
	# opkg o ora); numai instalarea si stergerea adevarate merg fara oprire (_ruleazaOpkg)
	ruleaza = ctx.get("opkg", _ruleaza)
	lucreaza = ctx.get("opkg", _ruleazaOpkg)
	feeduri = C.feeduriNoastre(ctx.get("opkg_conf", "/etc/opkg"))
	if not feeduri:
		return Rezultat(1, text="(niciun feed HD Satelit in /etc/opkg)")
	liste = ctx.get("opkg_liste", "/var/lib/opkg/lists")
	jurnal = []
	if actiune == "install":
		if not C.pachetInFeed(pachet, feeduri, liste):
			cod, text = ruleaza(["opkg", "update"], termen=120, limita=65536)
			jurnal.append("opkg update: cod %s" % cod)
			if cod != 0 and _treciPeRezerva(ctx, text):
				# moneasoftware.com nu raspunde: sursa pluginurilor externe a trecut pe serverul de rezerva (aceeasi sursa,
				# acelasi nume), deci lista se descarca inca o data, de acolo (ca in Extensii, HdsExtensiiLucru.treciPeRezerva)
				cod, text = ruleaza(["opkg", "update"], termen=120, limita=65536)
				jurnal.append("opkg update (serverul de rezerva): cod %s" % cod)
			if not C.pachetInFeed(pachet, feeduri, liste):
				return Rezultat(1, text="(%s nu e in feedurile HD Satelit)" % pachet)
		# 0.7.7 (UPD): pachetele imaginii nu se schimba pe bucati (vezi _OPKG_LASATE)
		cod, proba = ruleaza(["opkg", "--noaction", "install", pachet], termen=120, limita=65536)
		atinse = imagineAtinsa(proba, _instalateImagine(ctx))
		if atinse:
			jurnal.append(proba.strip())
			jurnal.append("(%s ar schimba pachetele imaginii: %s; nu se instaleaza pe bucati. Trimite intai "
				"repara-actualizarea (actualizarea rapida, tot setul semnat, cu repornirea interfetei), apoi din nou "
				"instaleaza %s)" % (pachet, ", ".join(atinse), pachet))
			return Rezultat(1, text="\n".join(jurnal))
		argv = ["opkg", "install", pachet]
	else:
		cod, stare = ruleaza(["opkg", "status", pachet], termen=30, limita=65536)
		if "Status:" not in stare or "not-installed" in stare:
			return Rezultat(1, text="(%s nu e instalat)" % pachet)
		argv = ["opkg", "remove", pachet]
	cod, text = lucreaza(argv, termen=TERMEN_OPKG_S, limita=256 * 1024)
	jurnal.append(text.strip())
	return Rezultat(cod, text="\n".join(jurnal))


def op_instaleaza(ctx, args):
	"""Un pachet din feedurile noastre oficiale (opkg install)."""
	return _opkg(ctx, "install", args[0])


def op_dezinstaleaza(ctx, args):
	"""Un plugin sau un modul instalat (opkg remove), numai enigma2-plugin-..."""
	return _opkg(ctx, "remove", args[0])


def op_repara_actualizarea(ctx, args):
	"""Termina o actualizare ramasa la jumatate (0.7.5, JAK, TODO 13.11 11:20): actualizarea rapida a meniului pe firul
	enigma2 (Screens/HdsAsistentaSemn._reparaActualizarea): cautarea semnata pune in plan si pachetele imaginii ramase
	half-installed (enigma2-hdsatelit, hdsatelit-*), pe care opkg le primeste cu --force-reinstall; apoi repornirea
	interfetei. Nicio comanda opkg data de echipa si nimic tastat de om."""
	return _cuControl(ctx, "repara_actualizarea")


TABEL = {
	"info": op_info,
	"placa": op_placa,
	"citeste": op_citeste,
	"pachete": op_pachete,
	"retea": op_retea,
	"tunere": op_tunere,
	"decodor": op_decodor,
	"memorie": op_memorie,
	"jurnale": op_jurnale,
	"jurnal": op_jurnal,
	"dmesg": op_dmesg,
	"procese": op_procese,
	"setari": op_setari,
	"captura": op_captura,
	"mesaj": op_mesaj,
	"intrebare": op_intrebare,
	"concluzii": op_concluzii,
	"ecran": op_ecran,
	"taste": op_taste,
	"text": op_text,
	"canal": op_canal,
	"flux": op_flux,
	"transpondere": op_transpondere,
	"zap": op_zap,
	"reporneste": op_reporneste,
	"setare-scrie": op_setare_scrie,
	"instaleaza": op_instaleaza,
	"dezinstaleaza": op_dezinstaleaza,
	"repara-actualizarea": op_repara_actualizarea,
}


def ruleaza(op, args, ctx=None):
	"""Ruleaza operatia `op` cu `args` (deja validate de catalog) si intoarce un Rezultat, cu iesirea text filtrata
	si plafonata. ctx: dictionar cu caile si uneltele (probele de pe PC dau ale lor; pe receptor, implicitele)."""
	ctx = ctx or {}
	functie = TABEL.get(op)
	if functie is None:
		return Rezultat(1, text="(operatie necunoscuta: %s)" % op)
	try:
		rez = functie(ctx, list(args or []))
	except Exception as e:
		_jurnal("%s: %s" % (op, e))
		return Rezultat(1, text="(eroare la %s: %s)" % (op, type(e).__name__))
	if rez.text is not None:
		# orice text, si cel al unui raspuns cu alt tip: _trimite_raspuns il trimite cand lipsesc octetii
		rez.text = _taie(mascheaza(rez.text))
	return rez
