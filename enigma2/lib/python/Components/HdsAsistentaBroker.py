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
# (CONTROL: tastele telecomenzii si textul intr-un camp), refuzate aici cand ctx["nivel"] nu e "B"; ecranele private
# (Components/HdsAsistentaControl.py) raman inchise si la B. Nimic nu scrie pe disc in afara jurnalului
# sesiunii. Externele se cheama cu lista de argumente (execve, FARA shell), cu termen si plafon de octeti. O singura
# operatie primeste o cale (op "citeste", din 0.6.21): numai sub RADACINI_CITIRE, verificata dupa realpath (nicio
# legatura spre afara, spre discuri sau stick-uri) si niciodata prin LOCURI_OPRITE (modulele de acces, parolele,
# cheile, jetoanele, datele personale). Iesirea trece intai prin filtrul de secrete (parole,
# chei, jetoane) si prin mascarea adreselor MAC; caile si setarile cartelelor de acces (CAM) nu se citesc deloc.
#
# Fiecare op din catalog are aici o functie (TABEL); o proba cere ca cele doua liste sa coincida. Partea de sus nu
# importa nimic din enigma2: functiile care au nevoie de receptor (captura, mesaj, memoria decodorului, setarile)
# primesc caile si uneltele prin argumente, iar probele de pe PC le dau pe ale lor.

import os
import re
import subprocess

from Components.HdsAsistentaControl import cheieSecreta, mascheazaSecrete

# caile cartelelor de acces si ale modulelor de acces nu se citesc niciodata (nici numele fisierelor nu apar in
# raspuns): dupa forma, fara numele modulelor (orice cuvant care se termina in cam, camd sau cams, cititoarele de
# cartele, porturile si fisierele lor de chei si de configurare)
_CAM = re.compile(r"(?i)cam[ds]?(?![a-z])|card(?:d\b|[_.-]?serv)|(?<![a-z])[gs]box|(?<![a-z])new[c]s\b|cs3\d\dx|"
	r"radeg[a]st|constcw|tuxbox/config|/var/keys|\.key\b|\.cfg\b")

RASPUNS_MAX = 1024 * 1024           # 1 MB de raspuns (text sau captura)
CAPTURA_MAX = 2 * 1024 * 1024       # o captura (JPEG mic de la 0.6.15; PNG inainte) se plafoneaza aparte
# op-urile de control: numai la nivelul B (omul a lasat bifat "Control complet")
CONTROL = ("taste", "text", "zap", "reporneste", "setare-scrie", "instaleaza", "dezinstaleaza")
TERMEN_S = 20                       # cat asteapta un extern
MAX_RANDURI_JURNAL = 2000

CALE_JURNALE = "/home/root/logs"
IMAGE_VERSION = "/etc/image-version"
# adresa MAC: ultimii trei octeti mascati
_MAC = re.compile(r"\b([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){2})(:[0-9A-Fa-f]{2}){3}\b")


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
	"""Scoate numai randurile modulelor de acces; secretele devin stelute, SSID-ul ramane vizibil."""
	randuri = []
	for rand in (text or "").splitlines():
		if _CAM.search(rand):
			continue
		rand = mascheazaSecrete(rand)
		rand = _MAC.sub(lambda m: m.group(1) + ":xx:xx:xx", rand)
		randuri.append(rand)
	return "\n".join(randuri)


def _taie(text, limita=RASPUNS_MAX):
	octeti = (text or "").encode("utf-8", "replace")
	if len(octeti) <= limita:
		return text or ""
	return octeti[:limita].decode("utf-8", "ignore") + "\n... (raspuns taiat la %d octeti)" % limita


def _citeste(cale, maxim=RASPUNS_MAX):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim + 1).decode("utf-8", "replace")
	except Exception as e:
		return "(nu se poate citi %s: %s)" % (os.path.basename(cale), type(e).__name__)


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
	# ce operatii stie receptorul acesta (unealta echipei alege dupa ele, de pilda "concluzii" din 0.6.13)
	parti.append("Operatii asistenta: " + " ".join(sorted(TABEL)))
	return Rezultat(0, text="\n\n".join(p for p in parti if p))


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


def op_placa(ctx, args):
	parti = [
		"Procesor:\n" + _citeste("/proc/cpuinfo", 16384).strip(),
		"Linia de comanda: " + _citeste("/proc/cmdline", 4096).strip(),
		"Partitii:\n" + _citeste("/proc/partitions", 8192).strip(),
		"Module:\n" + _citeste("/proc/modules", 32768).strip(),
	]
	return Rezultat(0, text="\n\n".join(parti))


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
	nim = _citeste(ctx.get("nim_sockets", "/proc/bus/nim_sockets"), 16384).strip()
	parti = ["Tunere:\n" + (nim or "(fara)")]
	stari = _stari_frontend(ctx)
	if stari:
		parti.append("Stare frontend:\n" + stari)
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
# Eduard, 01.11.2026 23:40: asistenta vede tot hardware-ul si tot ce e pe receptor, in afara de datele personale si de
# modulele de acces (CAM si chei). Caile primite au trecut de tiparul din catalog (numai sub RADACINI_CITIRE, fara
# spatii); aici: realpath (legaturile simbolice si ".." se rezolva, iar locul real trebuie sa ramana sub
# RADACINI_REALE: /proc/<pid>/fd, /proc/<pid>/root sau o legatura din /tmp spre un disc cad), apoi LOCURI_OPRITE si
# _CAM pe calea ceruta si pe cea reala. Numai fisiere obisnuite (si cele din /proc, /sys) si dosare: un FIFO sau un
# socket din /tmp ar tine sesiunea pe loc. Fisierul se citeste prin head (termen si plafon, ca un extern), iar raspunsul
# trece prin mascheaza (randurile modulelor de acces scoase, secretele ca stelute, MAC-ul pe jumatate).
RADACINI_CITIRE = ("/proc", "/sys", "/etc", "/var/log", "/home/root/logs", "/tmp")
# unde duc pe receptor (OE: /var/log -> /var/volatile/log, /tmp -> /var/volatile/tmp)
RADACINI_REALE = RADACINI_CITIRE + ("/var/volatile/log", "/var/volatile/tmp")
LOCURI_OPRITE = re.compile(
	# parolele, cheile, jetoanele si conturile (ale sistemului si ale noastre)
	r"shadow|passwd|(?:^|[/._-])pass(?:word|phrase)?(?:[/._-]|$)|hdsatelit-ssh|wpa_supplicant|hostapd|dropbear|"
	r"(?:^|/)\.?ssh(?:/|_|$)|ssl/private|\.pem$|vpn|wireguard|(?:^|/)wg\d|samba|(?:^|/)smb|(?:^|/)ppp(?:/|$)|netrc|"
	r"(?:^|/)auto\.|jeton|token|secret|parol|chei|key|cred|auth(?!orized)|cookie|conturi|account|"
	r"^/etc/enigma2/hdsatelit/[^/]*\.bin$|"
	# memoria si fluxurile nucleului care nu se citesc (sau nu se termina)
	r"(?:^|/)environ$|kcore|kmsg|pagemap|trace_pipe|(?:^|/)mem$|"
	# setarile intregi si copiile lor (op "setari" le da filtrate), listele si datele omului
	# (identificatorii placii, seria memoriei, seriile si EEPROM-ul, se citesc: Eduard, 02.11.2026 01:19)
	r"^/etc/enigma2/settings(?:$|[._~-])|backup|iptv|forum-poze|navigator|browsere")
# modulele de acces, pe langa _CAM: nici numele lor nu apar in lista unui dosar
_CAM_FAMILIE = re.compile(r"(?<![a-z])ecm|(?<![a-z])emm|caid|provid|softcam|oscam|ncam|cccam")
TERMEN_CITIRE_S = 10
MAX_INTRARI_DOSAR = 2000
TEXT_CITIRE_OPRITA = "(inchis: modulele de acces, parolele, cheile si datele personale nu se citesc)"


def _cam(cale):
	c = (cale or "").lower()
	return bool(_CAM.search(c) or _CAM_FAMILIE.search(c))


def _oprit(cale):
	return _cam(cale) or bool(LOCURI_OPRITE.search((cale or "").lower()))


def _sub(cale, radacini):
	return any(cale == r or cale.startswith(r + "/") for r in radacini)


def op_citeste(ctx, args):
	"""Un fisier (continutul, cel mult RASPUNS_MAX) sau un dosar (lista: felul, marimea, numele) de sub
	RADACINI_CITIRE; ctx["radacina"] muta totul intr-un dosar de proba."""
	radacina = ctx.get("radacina", "").rstrip("/")
	cerut = "/" + (args[0] if args else "").strip("/")
	if not _sub(cerut, RADACINI_CITIRE) or _oprit(cerut):
		return Rezultat(1, text=TEXT_CITIRE_OPRITA)
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
	if real is None or not _sub(real, reale) or _oprit(real):
		return Rezultat(1, text=TEXT_CITIRE_OPRITA)
	try:
		st = os.stat(real_plin)
	except Exception:
		return Rezultat(1, text="(nu exista: %s)" % cerut)
	import stat as S
	if S.S_ISDIR(st.st_mode):
		return Rezultat(0, text=_dosar(real_plin, real))
	if not S.S_ISREG(st.st_mode):
		return Rezultat(1, text="(nu e un fisier obisnuit: %s)" % cerut)
	ruleaza = ctx.get("ruleaza", _ruleaza)
	cod, text = ruleaza(["head", "-c", str(RASPUNS_MAX + 1), real_plin], termen=TERMEN_CITIRE_S)
	if cod == 124:
		return Rezultat(1, text="(%s nu s-a putut citi in %d s)" % (cerut, TERMEN_CITIRE_S))
	return Rezultat(cod, text=text.replace("\x00", " "))


def _dosar(real_plin, real):
	"""Lista unui dosar: d (dosar), f (fisier, cu marimea), l (legatura, fara tinta: in /proc tintele sunt fisierele
	deschise, deci si filmele omului), altele cu felul lor; cele oprite apar "(inchis)", iar cele ale modulelor de acces
	nu apar deloc."""
	import stat as S
	try:
		nume = sorted(os.listdir(real_plin))
	except Exception as e:
		return "(nu se poate citi dosarul: %s)" % type(e).__name__
	randuri = []
	for n in nume[:MAX_INTRARI_DOSAR]:
		cale = real.rstrip("/") + "/" + n
		if _cam(cale):
			continue
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
		if LOCURI_OPRITE.search(cale.lower()):
			arata += "  (inchis)"
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


def op_decodor(ctx, args):
	baza = ctx.get("stb", "/proc/stb")
	tinte = ("avs", "audio", "video", "vmpeg", "sync", "stream")
	randuri = []
	for rad, _dirs, fisiere in _umbla(baza):
		for f in fisiere:
			if any(t in rad or t in f for t in tinte):
				cale = os.path.join(rad, f)
				val = _citeste(cale, 256).strip().replace("\n", " ")
				randuri.append("%s = %s" % (cale[len(baza):].lstrip("/"), val))
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


def op_jurnale(ctx, args):
	baza = ctx.get("jurnale", CALE_JURNALE)
	randuri = []
	try:
		for nume in sorted(os.listdir(baza)):
			cale = os.path.join(baza, nume)
			if os.path.isfile(cale):
				randuri.append("%10d  %s" % (os.path.getsize(cale), nume))
	except Exception as e:
		return Rezultat(1, text="(nu se poate citi dosarul jurnalelor: %s)" % type(e).__name__)
	return Rezultat(0, text="\n".join(randuri) or "(niciun jurnal)")


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
			return Rezultat(1, text="(jurnal necunoscut)")
	except Exception:
		return Rezultat(1, text="(jurnal necunoscut)")
	text = _citeste(real, RASPUNS_MAX)
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


# Citirea permite setarile tuturor ecranelor deschise; scrierea isi pastreaza lista separata din Control.
SETARI_PERMISE = ("config.",)


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
		if _CAM.search(cheie):
			continue
		randuri.append(mascheazaSecrete(rand))
	return Rezultat(0, text="\n".join(randuri) or "(nicio setare in lista permisa)")


def op_captura(ctx, args):
	"""O captura video cu OSD; unealta refuza modulele de acces si editarea unui secret."""
	faca = ctx.get("captura")
	if faca is None:
		return Rezultat(1, text="(captura nu e disponibila)")
	octeti = faca()
	if not octeti:
		return Rezultat(1, text="(captura nu s-a putut face acum)")
	if isinstance(octeti, str):
		# refuzul unelte (ecran privat): textul lui
		return Rezultat(1, text=octeti)
	if len(octeti) > CAPTURA_MAX:
		return Rezultat(1, text="(captura prea mare)")
	tip = "jpg" if octeti[:3] == b"\xff\xd8\xff" else "png"
	return Rezultat(0, octeti=octeti, tip=tip)


def op_ecran(ctx, args):
	"""Textul ecranului de sus (stiva, listele cu randul ales, setarile, textele), ca echipa sa mearga prin meniuri fara
	poze; un ecran privat da numai "(ecran privat)" si clasa (Components/HdsAsistentaControl.textEcran)."""
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
	apasat si da textul ecranului de dupa. Pe un ecran privat merge numai EXIT."""
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
	Informatii despre canal; randurile modulelor de acces le scoate filtrul (mascheaza)."""
	citeste = ctx.get("canal")
	if citeste is None:
		return Rezultat(1, text="(canalul nu se poate citi)")
	text = citeste()
	if text is None:
		return Rezultat(1, text="(receptorul nu a raspuns la timp)")
	return Rezultat(0, text=text)


def op_transpondere(ctx, args):
	"""Transponderele din lista de canale (lamedb), numai sectiunea lor, eventual ale unui singur satelit (namespace)."""
	from Components import HdsAsistentaControl as C
	cale = ctx.get("lamedb", "/etc/enigma2/lamedb")
	text = _citeste(cale, 8 * 1024 * 1024)
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


def _opkg(ctx, actiune, pachet):
	from Components import HdsAsistentaControl as C
	if not _controlPermis(ctx):
		return Rezultat(1, text=TEXT_FARA_CONTROL)
	if not C.PACHET.match(pachet or ""):
		return Rezultat(1, text="(numai pluginurile si modulele din feed: enigma2-plugin-...)")
	ruleaza = ctx.get("opkg", _ruleaza)
	feeduri = C.feeduriNoastre(ctx.get("opkg_conf", "/etc/opkg"))
	if not feeduri:
		return Rezultat(1, text="(niciun feed HD Satelit in /etc/opkg)")
	liste = ctx.get("opkg_liste", "/var/lib/opkg/lists")
	jurnal = []
	if actiune == "install":
		if not C.pachetInFeed(pachet, feeduri, liste):
			cod, text = ruleaza(["opkg", "update"], termen=120, limita=65536)
			jurnal.append("opkg update: cod %s" % cod)
			if not C.pachetInFeed(pachet, feeduri, liste):
				return Rezultat(1, text="(%s nu e in feedurile HD Satelit)" % pachet)
		argv = ["opkg", "install", pachet]
	else:
		cod, stare = ruleaza(["opkg", "status", pachet], termen=30, limita=65536)
		if "Status:" not in stare or "not-installed" in stare:
			return Rezultat(1, text="(%s nu e instalat)" % pachet)
		argv = ["opkg", "remove", pachet]
	cod, text = ruleaza(argv, termen=TERMEN_OPKG_S, limita=256 * 1024)
	jurnal.append(text.strip())
	return Rezultat(cod, text="\n".join(jurnal))


def op_instaleaza(ctx, args):
	"""Un plugin sau un modul din feedurile noastre oficiale (opkg install); configurarea si cheile modulelor nu."""
	return _opkg(ctx, "install", args[0])


def op_dezinstaleaza(ctx, args):
	"""Un plugin sau un modul instalat (opkg remove), numai enigma2-plugin-..."""
	return _opkg(ctx, "remove", args[0])


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
	"concluzii": op_concluzii,
	"ecran": op_ecran,
	"taste": op_taste,
	"text": op_text,
	"canal": op_canal,
	"transpondere": op_transpondere,
	"zap": op_zap,
	"reporneste": op_reporneste,
	"setare-scrie": op_setare_scrie,
	"instaleaza": op_instaleaza,
	"dezinstaleaza": op_dezinstaleaza,
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
	if rez.text is not None and rez.tip == "text":
		rez.text = _taie(mascheaza(rez.text))
	return rez
