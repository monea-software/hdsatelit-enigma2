# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistentaBroker.py: rularea unei operatii din catalogul Asistentei (Components/HdsAsistentaCatalog.py). Cererea
# a fost deja verificata (semnatura si tiparele argumentelor) de HdsAsistenta.py; aici se ruleaza numai operatia ceruta
# si se intoarce raspunsul, filtrat si plafonat.
#
# Nivelul A: numai citiri si trei probe (captura OSD, un mesaj pe ecran, concluziile echipei pe ecran). Nimic nu scrie pe disc in afara jurnalului
# sesiunii. Externele se cheama cu lista de argumente (execve, FARA shell), cu termen si plafon de octeti; nu exista
# nicio cale libera de fisier (jurnalele se citesc dupa nume, din /home/root/logs). Iesirea trece intai prin filtrul de
# secrete (Components/HdsModSigur.SECRET: parole, chei, jetoane) si prin mascarea adreselor MAC; caile si setarile
# cartelelor de acces (CAM) nu se citesc deloc.
#
# Fiecare op din catalog are aici o functie (TABEL); o proba cere ca cele doua liste sa coincida. Partea de sus nu
# importa nimic din enigma2: functiile care au nevoie de receptor (captura, mesaj, memoria decodorului, setarile)
# primesc caile si uneltele prin argumente, iar probele de pe PC le dau pe ale lor.

import os
import re
import subprocess

try:
	from Components import HdsModSigur
	_SECRET = HdsModSigur.SECRET
except Exception:
	# acelasi tipar ca in Components/HdsModSigur.py (parole, chei, jetoane, parola in adresa)
	_SECRET = re.compile(
		r"(?i)(token|password|passwd|passphrase|parola|psk|secret"
		r"|pin(?:[.][0-9]+)*\s*=|key(?:[.][0-9]+)*\s*="
		r"|(?:api|access|private|auth)[ _.-]?key\s*[=:]"
		r"|[?&;](?:pass|pwd|pw|auth|sid|sessionid|sig|signature)="
		r"|\bauthorization\s*[=:]|\bbearer\s+[a-z0-9._~+/=-]{6,}"
		r"|\b(?:set-)?cookie\s*:"
		r"|[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@)")

# caile cartelelor de acces si ale modulelor de acces nu se citesc niciodata (nici numele fisierelor nu apar in
# raspuns): dupa forma, fara numele modulelor (orice cuvant care se termina in cam, camd sau cams, cititoarele de
# cartele, porturile si fisierele lor de chei si de configurare)
_CAM = re.compile(r"(?i)cam[ds]?(?![a-z])|card(?:d\b|[_.-]?serv)|(?<![a-z])[gs]box|(?<![a-z])new[c]s\b|cs3\d\dx|"
	r"radeg[a]st|constcw|tuxbox/config|/var/keys|\.key\b|\.cfg\b")

RASPUNS_MAX = 1024 * 1024           # 1 MB de raspuns (text sau captura)
CAPTURA_MAX = 2 * 1024 * 1024       # o captura PNG poate fi mai mare; se plafoneaza aparte
TERMEN_S = 20                       # cat asteapta un extern
MAX_RANDURI_JURNAL = 2000

CALE_JURNALE = "/home/root/logs"
IMAGE_VERSION = "/etc/image-version"
# adresa MAC: ultimii trei octeti mascati
_MAC = re.compile(r"\b([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){2})(:[0-9A-Fa-f]{2}){3}\b")
# numele retelei Wi-Fi nu se arata
_SSID = re.compile(r"(?i)\b(ssid|essid)\b\s*[:=].*$")


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
	"""Scoate randurile cu secrete, mascheaza MAC-urile si numele retelelor Wi-Fi. Pastreaza restul."""
	randuri = []
	for rand in (text or "").splitlines():
		if _SECRET.search(rand) or _CAM.search(rand):
			continue
		rand = _MAC.sub(lambda m: m.group(1) + ":xx:xx:xx", rand)
		rand = _SSID.sub(lambda m: m.group(0).split(":", 1)[0].split("=", 1)[0] + "= (ascuns)", rand)
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
	return Rezultat(0, text="\n\n".join(parti))


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


# setari: numai cheile din aceste prefixe tehnice (audio, video, interfata, subtitrari, retea fara parole); nimic
# altceva nu se copiaza. FARA prefixul generic "config.hds" (ar lasa sa treaca numele si e-mailul testerului,
# config.hds_beta.nume/email); daca vreodata e nevoie de o setare a noastra, se adauga aici prefixul ei exact.
SETARI_PERMISE = (
	"config.av.", "config.osd.", "config.subtitles.", "config.usage.",
	"config.skin.", "config.misc.rcused", "config.network.",
	# tunerele (modul, LNB-urile, comutatoarele, motorul): fara secrete; ce nu e in settings e valoarea implicita
	"config.Nims.",
)
# ... afara de cheile care, chiar sub un prefix permis, pot avea ceva personal sau un secret
SETARI_OPRITE = re.compile(
	r"(?i)(pass|pwd|parola|psk|secret|token|key|pin|auth|login|user|card|cam|mail|email|nume|name)")


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
		if SETARI_OPRITE.search(cheie):
			continue
		randuri.append(rand)
	return Rezultat(0, text="\n".join(randuri) or "(nicio setare in lista permisa)")


def op_captura(ctx, args):
	"""O captura numai a meniurilor (OSD), niciodata imaginea canalului; refuzata cat ecranul „Acces SSH" e deschis
	(parola lui root pe ecran nu trebuie sa ajunga intr-o captura)."""
	faca = ctx.get("captura")
	if faca is None:
		return Rezultat(1, text="(captura nu e disponibila)")
	octeti = faca()
	if not octeti:
		return Rezultat(1, text="(captura nu s-a putut face acum)")
	if len(octeti) > CAPTURA_MAX:
		return Rezultat(1, text="(captura prea mare)")
	return Rezultat(0, octeti=octeti, tip="png")


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


TABEL = {
	"info": op_info,
	"placa": op_placa,
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
