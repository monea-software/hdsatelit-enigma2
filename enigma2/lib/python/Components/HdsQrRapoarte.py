# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Rapoartele trimise prin coduri QR cand receptorul nu ajunge la serverul nostru (TODO 1860 b; Eduard 29.10.2026
16:04-16:26): in meniul Beta tester, un rand mic jos „Nu ai internet? Trimite prin cod QR”, aratat NUMAI cand serverul
testerilor nu raspunde; ecranul are codul general „Raport complet (dacă nu știi ce să alegi)” si codurile specifice,
numite dupa problema omului. Fiecare cod scanat cu telefonul deschide stb.hdsatelit.com/q/, care trimite singur
raportul (serverul si pagina sunt publicate din 29.10.2026).

Forma codurilor: CONTRACT-QR.md (lucru-sesiune/pilot-26-09/pornire-poza-eroare), sectiunile 1-2:
    https://stb.hdsatelit.com/q/#<F><S>.<i>.<n>.<D>
F = litera felului, S = CRC-32 (8 hexa mici) al blobului B, i/n = al catelea cod din cate, D = bucata i din base64url
(fara „=”) al lui B, B = DEFLATE brut (wbits=-15) al textului T in UTF-8. T = antetul „cheie=valoare” pana la primul
rand gol, apoi sectiunile „== nume”.

Fara date personale: textul trece prin curatarea jurnalelor testerilor (HdsBetaTester.curata: fara accesul conditionat,
parole, chei, jetoane, Wi-Fi; IP, MAC, e-mailuri, adrese web si caile filmelor inlocuite) si prin
HdsDiagnostic.faraDatePersonale. Fara numele canalelor, fara listele de canale, fara setari. Amprenta receptorului
pleaca numai la beta testerul inscris (nota >= 2), ca la raportul automat.

Modulul se incarca si pe PC (probele): radacina sistemului se da la fiecare functie."""
import base64
import os
import random
import re
import time
import zlib

try:
	from Components import HdsBetaTester as B
except ImportError:  # probe pe PC
	import HdsBetaTester as B

PREFIX = "https://stb.hdsatelit.com/q/#"
# codul general e mereu unul singur; un cod specific prea mare devine o secventa scurta
CODURI_GENERAL = 1
CODURI_SPECIFIC = 4
# semne base64 pe cod: cu prefixul (~44 de semne) incape in versiunea 20 a codului QR (666 octeti, Components/HdsQr)
BUCATA = 600
# textul unui raport, inainte de comprimare (cel mult; se taie de la coada sectiunilor)
TEXT_MAX = 16 * 1024
RANDURI_JURNAL = 25


def N_(text):
	return text


FELURI = ("g", "i", "r", "s", "v", "b", "a")
TITLURI = {
	"g": N_("Raport complet (dacă nu știi ce să alegi)"),
	"i": N_("Raport pentru probleme de internet"),
	"r": N_("Raport pentru probleme de recepție"),
	"s": N_("Raport pentru probleme de stocare"),
	"v": N_("Raport pentru probleme de imagine și sunet"),
	"b": N_("Raport pentru probleme la pornire"),
	"a": N_("Raport pentru alte probleme"),
}
RAND_MENIU = N_("Nu ai internet? Trimite prin cod QR")
RAND_MENIU_SCURT = N_("Receptorul nu ajunge la serverul nostru: trimiți raportul cu telefonul.")
INDEMN = N_("Scanează codul cu telefonul: raportul ne ajunge singur.")


def _t(text):
	return B._t(text)


# ------------------------------------------------------------------ citirile (numai fisiere mici, fara comenzi)

def _citeste(radacina, cale, maxim=65536):
	return B._citesteText(B._cale(radacina, cale), maxim) or ""


def _coada(radacina, cale, randuri=RANDURI_JURNAL, octeti=64 * 1024):
	text = B._citesteCoada(B._cale(radacina, cale), octeti) if hasattr(B, "_citesteCoada") else _citeste(radacina,
		cale, octeti)
	return "\n".join([r for r in (text or "").splitlines() if r.strip()][-randuri:])


def _curat(text):
	text = B.curata(text or "")
	try:
		from Components import HdsDiagnostic as D
	except ImportError:
		try:
			import HdsDiagnostic as D
		except ImportError:
			D = None
	if D is not None:
		text = D.faraDatePersonale(text)
	return text


def _stare(radacina):
	mem = B._meminfo(radacina)
	r = ["sus_s=%d" % int(B._sus(radacina) or 0),
		"memorie_kb=%s libera_kb=%s" % (mem.get("MemTotal", "?"), mem.get("MemAvailable", mem.get("MemFree", "?"))),
		"incarcare=%s" % B._incarcare(radacina)]
	try:
		st = os.statvfs(B._cale(radacina, "/"))
		r.append("loc_liber_mib=%d din %d" % (st.f_bavail * st.f_frsize // 1048576, st.f_blocks * st.f_frsize // 1048576))
	except (OSError, AttributeError):
		pass
	return r


def _retea(radacina):
	"""Placile, legatura si daca au adresa (fara adresa insasi), ruta implicita, cate servere DNS."""
	r = []
	for p in B._retea(radacina):
		r.append("%s %s %s %s" % (p.get("fel"), p.get("magistrala"), p.get("nume") or p.get("id"), p.get("driver")))
	baza = B._cale(radacina, "/sys/class/net")
	try:
		placi = sorted(os.listdir(baza))
	except OSError:
		placi = []
	for nume in placi:
		if nume == "lo":
			continue
		stare = _citeste(radacina, "/sys/class/net/%s/operstate" % nume, 64).strip()
		cablu = _citeste(radacina, "/sys/class/net/%s/carrier" % nume, 16).strip()
		viteza = _citeste(radacina, "/sys/class/net/%s/speed" % nume, 16).strip()
		r.append("%s stare=%s legatura=%s viteza=%s" % (B._txt(nume, 16), stare or "?", cablu or "?", viteza or "?"))
	adrese = _citeste(radacina, "/proc/net/fib_trie", 256 * 1024)
	r.append("adresa_ipv4=%s" % ("da" if re.search(r"/32 host LOCAL", adrese) and
		len(re.findall(r"/32 host LOCAL", adrese)) > 1 else "nu"))
	rute = _citeste(radacina, "/proc/net/route", 16384)
	r.append("ruta_implicita=%s" % ("da" if re.search(r"(?m)^\S+\t00000000\t", rute) else "nu"))
	dns = _citeste(radacina, "/etc/resolv.conf", 8192)
	r.append("servere_dns=%d" % len(re.findall(r"(?m)^\s*nameserver\s", dns)))
	return r


def _tunere(radacina):
	return ["%s %s %s %s" % (t.get("slot", ""), t.get("fel", ""), t.get("nume", ""), "/".join(t.get("moduri") or []))
		for t in B._tunere(radacina)]


def _stocare(radacina):
	r = []
	for rand in _citeste(radacina, "/proc/mounts", 65536).splitlines():
		p = rand.split()
		if len(p) >= 3 and p[0].startswith("/dev/"):
			r.append("%s %s %s" % (p[0], p[1], p[2]))
	for rand in _citeste(radacina, "/proc/partitions", 16384).splitlines()[2:]:
		p = rand.split()
		if len(p) == 4 and re.match(r"(sd[a-z]+\d*|mmcblk\d+(p\d+)?)$", p[3]):
			r.append("partitie %s %s KiB" % (p[3], p[2]))
	return r


def _imagine(radacina):
	r = ["hdmi=%s" % B._hdmi(radacina)]
	for cale in ("/proc/stb/video/videomode", "/proc/stb/video/aspect", "/proc/stb/vmpeg/0/xres",
			"/proc/stb/vmpeg/0/yres", "/proc/stb/vmpeg/0/framerate", "/proc/stb/audio/hdmi_choices",
			"/proc/stb/audio/ac3"):
		v = _citeste(radacina, cale, 256).strip()
		if v:
			r.append("%s=%s" % (cale.rsplit("/", 2)[-2] + "/" + cale.rsplit("/", 1)[-1], B._txt(v, 80)))
	return r


def _jurnale(radacina, nume):
	"""Coada jurnalelor imaginii cu numele dat (din /home/root/logs), curatata."""
	r = []
	for n in nume:
		text = _coada(radacina, os.path.join(B.CALE_LOGS, n))
		if text:
			r.append("-- %s" % n)
			r.extend(_curat(text).splitlines())
	return r


def _cadere():
	c = None
	try:
		c = B.ultimulJurnalCadere()
	except Exception:
		c = None
	if not c:
		return []
	randuri = [x for x in (c.get("text") or "").splitlines() if x.strip()][-RANDURI_JURNAL:]
	return ["-- %s" % c.get("nume", "")] + randuri


def _paznic(radacina):
	return _curat(_coada(radacina, B.CALE_PAZNIC, 15)).splitlines()


# ce sectiuni are fiecare fel (nume, functie); codul general le ia pe scurt pe toate
def _sectiuni(fel, radacina):
	if fel == "i":
		return [("retea", _retea(radacina)), ("jurnale", _jurnale(radacina, ("hds-retea.log", "hds-wifi.log")))]
	if fel == "r":
		# fara hds-zap.log si jurnalul scanarii: au numele canalelor (CONTRACT-QR 2: fara canale)
		return [("tunere", _tunere(radacina)), ("jurnale", _jurnale(radacina, ("hds-tuner.log", "hds-motor.log")))]
	if fel == "s":
		return [("stocare", _stocare(radacina)), ("jurnale", _jurnale(radacina, ("hds-discuri.log", "hds-mountall.log",
			"hds-inregistrari.log")))]
	if fel == "v":
		return [("imagine", _imagine(radacina)), ("jurnale", _jurnale(radacina, ("hds-hdmi.log",)))]
	if fel == "b":
		return [("stare", _stare(radacina)), ("paznic", _paznic(radacina)), ("jurnale", _jurnale(radacina,
			("hds-caderi.log", "hds-init-timpi.log"))), ("cadere", _cadere())]
	if fel == "a":
		return [("stare", _stare(radacina)), ("jurnale", _jurnale(radacina, ("hds-actualizare.log",
			"hds-actualizari.log", "hds-extensii.log", "hds-interfata.log"))), ("cadere", _cadere())]
	# g: scurt din toate
	return [("stare", _stare(radacina)), ("retea", _retea(radacina)), ("tunere", _tunere(radacina)),
		("stocare", _stocare(radacina)[:8]), ("paznic", _paznic(radacina)[-5:]), ("cadere", _cadere()[-8:])]


# ------------------------------------------------------------------ textul si codurile

def cheieNoua():
	return "%012x" % random.getrandbits(48)


def antet(fel, cheie, b=None, radacina="", acum=None, grupe=()):
	"""Antetul raportului (CONTRACT-QR 2), ca randuri „cheie=valoare”."""
	model, paza = "", {}
	try:
		model, paza = B.modelSiPaza(radacina or None)
	except Exception:
		pass
	r = ["format=1", "fel=%s" % fel, "masina=%s" % B._txt(model, 40), "model=%s" % B._txt(paza.get("boxtype", "")
		or model, 60), "imagine=%s" % B._txt(B.versiuneImagine(radacina or None), 40),
		"uptime=%d" % int(B._sus(radacina) or 0),
		"ora=%s" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(acum if acum is not None else time.time())),
		"limba=%s" % _limba(), "cheie=%s" % cheie, "cod=%s" % cheie[:6].upper()]
	try:
		b = B._b(b)
		if B.inscris(b) or B.notaVeche(b):
			a = B.amprenta(radacina)
			if a:
				r.append("amprenta=%s" % a)
	except Exception:
		pass
	if grupe:
		r.append("grupe=%s" % ",".join(grupe))
	return r


def _limba():
	try:
		from Components.config import config
		return (config.osd.language.value or "en")[:2]
	except Exception:
		return "ro"


def textRaport(fel, cheie=None, b=None, radacina="", acum=None, maxim=TEXT_MAX):
	"""Textul T al raportului felului `fel` (CONTRACT-QR 2), taiat la `maxim` octeti."""
	cheie = cheie or cheieNoua()
	grupe = [f for f in FELURI if f != "g"] if fel == "g" else ()
	r = antet(fel, cheie, b, radacina, acum, grupe)
	r.append("")
	for nume, randuri in _sectiuni(fel, radacina):
		if not randuri:
			continue
		r.append("== %s" % nume)
		r.extend(B._txt(x, 300) for x in randuri)
	text = "\n".join(r) + "\n"
	date = text.encode("utf-8")
	if len(date) > maxim:
		text = date[:maxim].decode("utf-8", "ignore").rsplit("\n", 1)[0] + "\n"
	return text


def blob(text):
	c = zlib.compressobj(9, zlib.DEFLATED, -15)
	return c.compress(text.encode("utf-8")) + c.flush()


def adrese(fel, text, bucata=BUCATA, n_max=None):
	"""Adresele codurilor QR pentru textul T (CONTRACT-QR 1). Cu `n_max`: textul se scurteaza de la coada pana incape
	in atatea coduri (codul general: unul singur)."""
	while True:
		b = blob(text)
		d = base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")
		bucati = [d[i:i + bucata] for i in range(0, len(d), bucata)] or [""]
		if n_max is None or len(bucati) <= n_max:
			break
		randuri = text.rstrip("\n").split("\n")
		if len(randuri) <= 12:
			bucati = bucati[:n_max]
			break
		# se taie din coada, cate un sfert din ce prisoseste, pana incape
		taie = max(1, (len(randuri) * (len(bucati) - n_max)) // (len(bucati) * 2))
		text = "\n".join(randuri[:-taie]) + "\n"
	s = "%08x" % (zlib.crc32(b) & 0xFFFFFFFF)
	n = len(bucati)
	return ["%s%s%s.%d.%d.%s" % (PREFIX, fel, s, i + 1, n, x) for i, x in enumerate(bucati)]


def coduri(fel, b=None, radacina="", cheie=None, acum=None):
	"""Adresele codurilor QR ale felului: unul pentru codul general, cel mult CODURI_SPECIFIC pentru celelalte."""
	text = textRaport(fel, cheie, b, radacina, acum)
	return adrese(fel, text, n_max=CODURI_GENERAL if fel == "g" else CODURI_SPECIFIC)


def legatura(fel, b=None, radacina="", cheie=None, acum=None):
	"""Pentru interfata web (telefonul care o deschide are de obicei internet): UN singur link cu raportul intreg
	(n = 1, fara limita codului QR); pagina /q/ il trimite la deschidere."""
	return adrese(fel, textRaport(fel, cheie, b, radacina, acum), bucata=10 ** 9)[0]


def titlu(fel):
	return _t(TITLURI[fel])
