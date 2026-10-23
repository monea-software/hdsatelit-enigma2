# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsCeasHttps.py: „ceasul receptorului e în urmă” la orice cerere HTTPS, nu numai la fonturi.
#
# De ce: dupa un flash sau dupa o lunga oprire din priza receptorul porneste cu ora salvata (fake-hwclock), care poate fi
# cu zile sau luni in urma, iar pana pune ora NTP sau un transponder certificatele site-urilor par „încă nevalabile”.
# Pana la 0.2.5 numai fonturile spuneau ca de vina e ceasul; traducerea, listele DAB+ si DVB-T2, DVB-I, modelele OCR,
# subtitrarile descarcate si pachetele dadeau o eroare de retea care il trimitea pe om sa verifice internetul.
#
# Ce face:
#   1. felCertificat(eroare): ce spune eroarea despre certificat. Eroarea poate fi o exceptie (urllib, ssl, cu tot lantul
#      ei: reason, __cause__, __context__, args) sau textul unui program (iesirea lui opkg). Codurile X509 din
#      ssl.SSLCertVerificationError.verify_code au intaietate; altfel textul. NU_INCA („not yet valid”), EXPIRAT
#      („has expired”), ALT (alt motiv stiut: nume gresit, emitent necunoscut, semnat de el insusi) sau NECUNOSCUT
#      (verificarea a cazut, motivul nu se vede: opkg cu wget -q spune numai „wget returned 5”).
#   2. judecaCeasul(): ora de acum fata de ce stie receptorul, cu aceleasi repere ca lib/dvb/dvbtime.cpp:
#        IN_URMA    ora e inaintea limitei de jos: data construirii din /etc/image-version (minus o saptamana, ca in C++;
#                   cel putin ORA_MINIMA_COD) sau ultima ora sigura salvata (minus o zi). Vadit gresita.
#        IN_VIITOR  ora e dupa ORA_MAXIMA (2037, cat duce nucleul pe 32 de biti). Vadit gresita.
#        NESIGUR    C++ spune ca ora nu e inca sigura (salvata, provizorie sau necunoscuta): exact cazul de dupa flash.
#        None       ora e sigura (NTP, doua transpondere, RTC) sau nu se poate spune nimic.
#   3. Ceasul e de vina numai asa: NU_INCA cu IN_URMA sau NESIGUR; EXPIRAT cu IN_VIITOR; NECUNOSCUT cu oricare dintre ele.
#      ALT nu e niciodata ceasul. Cand ceasul nu e de vina, fiecare loc isi pastreaza mesajul lui obisnuit.
#   4. Textul pentru om: ca ceasul e in urma (sau inainte, sau ora nu e sigura), ce ora arata si ce sa faca (Data si ora:
#      „Sincronizează acum” sau un canal din satelit; ora nu se poate pune de mana in imagine). mesaj() e textul intreg,
#      texte() il da in doua (cauza, ce faci) pentru paginile care le arata separat, scurt() e un singur rand.
#   5. O resincronizare a orei prin Internet (HdsCeas, NTP), CEL MULT O DATA pe pornirea enigma2, numai cand sincronizarea
#      e pornita (sursa „auto” sau „ntp”), nu ruleaza deja si HdsCeas a pornit-o (mytest.py). Cererea pleaca pe firul
#      enigma2 (reactor.callFromThread din firele descarcarilor). Fara bucle: nicio descarcare nu se reia de aici.
#   6. Verificarea certificatelor NU se atinge nicaieri: modulul doar citeste eroarea dupa ce verificarea a refuzat.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import calendar
import re
import threading
import time

try:
	from Components import HdsCeas as _C
except ImportError:
	try:
		import HdsCeas as _C
	except ImportError:
		_C = None

# felul erorii de certificat
NU_INCA, EXPIRAT, ALT, NECUNOSCUT = "nu_inca", "expirat", "alt", "necunoscut"
# ceasul
IN_URMA, IN_VIITOR, NESIGUR = "in_urma", "in_viitor", "nesigur"

CALE_IMAGE_VERSION = "/etc/image-version"
CALE_ORA_SIGURA = "/etc/hds-ora-sigura.data"   # aceeasi ca HdsCeas.CALE_ORA_SIGURA si HDS_ORA_SIGURA din dvbtime.cpp

# aceleasi repere ca lib/dvb/dvbtime.h
MARJA_CONSTRUIRE_S = 7 * 86400
ORA_MINIMA_COD = 1789776000      # 2026-09-19 00:00:00 UTC
ORA_MAXIMA = 2145916799          # 2037-12-31 23:59:59 UTC
# ultima ora sigura salvata: cu o zi de rabdare (C++ lasa 120 s), ca „vadit in urma” sa fie vadit
MARJA_ORA_SIGURA_S = 86400

# starile orei din C++ (ca HdsCeas): de la SIGURA_INTERNET in sus ora e sigura
SIGURA_INTERNET = 3

# codurile X509_V_ERR din OpenSSL (ssl.SSLCertVerificationError.verify_code)
_COD_NU_INCA = (9, 11)           # CERT_NOT_YET_VALID, CRL_NOT_YET_VALID
_COD_EXPIRAT = (10, 12)          # CERT_HAS_EXPIRED, CRL_HAS_EXPIRED

# textele (mici), dupa ce s-a vazut ca e vorba de un certificat
_TEXT_NU_INCA = ("not yet valid", "not yet activated", "not_yet_valid")
_TEXT_EXPIRAT = ("has expired", "cert_has_expired", "certificate expired")
_TEXT_ALT = ("self signed", "self-signed", "unable to get local issuer", "unable to get issuer", "name mismatch",
	"ip address mismatch", "doesn't match", "does not match", "not trusted", "unknown ca", "revoked",
	"signature failure", "unsupported certificate purpose", "invalid ca", "path length")
_TEXT_CERTIFICAT = ("certif",)
# verificarea a cazut, fara motiv: wget (GNU) iese cu 5 la „SSL verification failure”; opkg cu wget -q spune numai atat
_RE_WGET_5 = re.compile(r"wget returned 5\b")

_DIN_CEAS = object()             # stare implicita: se citeste din C++


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsCeasHttps] %s" % text)


# ---------------------------------------------------------------- felul erorii

def _lant(eroare):
	"""Eroarea si cele din spatele ei (reason la URLError, __cause__, __context__, args), fara repetari, cel mult 8."""
	vazute = []
	coada = [eroare]
	while coada and len(vazute) < 8:
		e = coada.pop(0)
		if e is None or any(e is v for v in vazute):
			continue
		vazute.append(e)
		if isinstance(e, BaseException):
			for nume in ("reason", "__cause__", "__context__"):
				x = getattr(e, nume, None)
				if isinstance(x, BaseException):
					coada.append(x)
			for x in getattr(e, "args", ()) or ():
				if isinstance(x, BaseException):
					coada.append(x)
	return vazute


def _text(x):
	try:
		return u"%s" % (x,)
	except Exception:
		try:
			return repr(x)
		except Exception:
			return u""


def felDinText(text):
	"""Felul erorii de certificat dintr-un text (iesirea unui program, mesajul unei exceptii) sau None."""
	t = (text or u"").lower()
	if not t:
		return None
	if _RE_WGET_5.search(t):
		return NECUNOSCUT
	if not any(x in t for x in _TEXT_CERTIFICAT):
		return None
	if any(x in t for x in _TEXT_NU_INCA):
		return NU_INCA
	if any(x in t for x in _TEXT_EXPIRAT):
		return EXPIRAT
	if any(x in t for x in _TEXT_ALT):
		return ALT
	if ("verify failed" in t or "verify_failed" in t or "ssl certificate problem" in t or "ssl peer certificate" in t
			or "cannot verify" in t or "sslcertverificationerror" in t or "certificate verification" in t):
		return NECUNOSCUT
	return None


def felCertificat(eroare):
	"""NU_INCA, EXPIRAT, ALT, NECUNOSCUT sau None (nu e o eroare de certificat). `eroare`: o exceptie, un text sau o
	lista de randuri (iesirea unui program)."""
	if eroare is None:
		return None
	if isinstance(eroare, (list, tuple)):
		return felDinText(u"\n".join(_text(x) for x in eroare))
	if not isinstance(eroare, BaseException):
		return felDinText(_text(eroare))
	texte = []
	for e in _lant(eroare):
		cod = getattr(e, "verify_code", None)
		if isinstance(cod, int) and not isinstance(cod, bool) and cod > 0:
			if cod in _COD_NU_INCA:
				return NU_INCA
			if cod in _COD_EXPIRAT:
				return EXPIRAT
			return ALT
		texte.append(e.__class__.__name__)
		texte.append(_text(e))
		mesaj = getattr(e, "verify_message", None)
		if mesaj:
			texte.append(_text(mesaj))
	return felDinText(u" ".join(texte))


# ---------------------------------------------------------------- ceasul

def _citesteMic(cale, maxim=4096):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (IOError, OSError):
		return u""


def oraConstruirii(text=None):
	"""Data construirii din /etc/image-version („version=0<versiune><YYYYMMDDHHMM>”, Makefile.am) minus o saptamana, ca
	hdsceas::oraDinImageVersion din dvbtime.cpp; 0 cand nu se poate citi."""
	if text is None:
		text = _citesteMic(CALE_IMAGE_VERSION)
	m = re.search(r"(?m)^version=(\d{13,})\s*$", text or u"")
	if not m:
		return 0
	d = m.group(1)[-12:]
	try:
		an, luna, zi, ora, minut = int(d[0:4]), int(d[4:6]), int(d[6:8]), int(d[8:10]), int(d[10:12])
		if not (1 <= luna <= 12 and 1 <= zi <= 31 and ora < 24 and minut < 60):
			return 0
		return calendar.timegm((an, luna, zi, ora, minut, 0, 0, 0, 0)) - MARJA_CONSTRUIRE_S
	except (ValueError, OverflowError):
		return 0


def oraSiguraSalvata(cale=None):
	"""Ultima ora sigura salvata de HdsCeas (secunde UTC) sau 0."""
	text = _citesteMic(cale or CALE_ORA_SIGURA, 64).strip()
	try:
		return calendar.timegm(time.strptime(text, "%Y-%m-%d %H:%M:%S"))
	except (ValueError, OverflowError):
		return 0


def limitaDeJos(construire=None, sigura=None):
	"""Sub ora asta ceasul e vadit in urma: data construirii (cel putin ORA_MINIMA_COD, ca minimImagine din C++) si
	ultima ora sigura salvata, minus o zi."""
	construire = oraConstruirii() if construire is None else construire
	if not (ORA_MINIMA_COD < construire <= ORA_MAXIMA):
		construire = ORA_MINIMA_COD
	sigura = oraSiguraSalvata() if sigura is None else sigura
	jos = construire
	if ORA_MINIMA_COD < sigura <= ORA_MAXIMA:
		jos = max(jos, sigura - MARJA_ORA_SIGURA_S)
	return jos


def stareCeas():
	"""Starea orei din C++ (HdsCeas: 0 necunoscuta .. 5 sigura RTC) sau None (fara C++, de pilda pe PC)."""
	if _C is None:
		return None
	try:
		return _C.stareOra(_C._handler())
	except Exception:
		return None


def judecaCeasul(acum=None, stare=_DIN_CEAS, jos=None):
	"""IN_URMA, IN_VIITOR, NESIGUR sau None (ceasul pare bun, sau nu se stie nimic despre el)."""
	acum = time.time() if acum is None else acum
	jos = limitaDeJos() if jos is None else jos
	if stare is _DIN_CEAS:
		stare = stareCeas()
	if acum < jos:
		return IN_URMA
	if acum > ORA_MAXIMA:
		return IN_VIITOR
	if stare is not None and stare < SIGURA_INTERNET:
		return NESIGUR
	return None


def _ceasulEDeVina(fel, ceas):
	if fel == NU_INCA:
		return ceas in (IN_URMA, NESIGUR)
	if fel == EXPIRAT:
		return ceas == IN_VIITOR
	if fel == NECUNOSCUT:
		return ceas in (IN_URMA, IN_VIITOR, NESIGUR)
	return False


def deVinaECeasul(eroare, acum=None, stare=_DIN_CEAS, jos=None):
	"""IN_URMA, IN_VIITOR sau NESIGUR cand eroarea de certificat vine de la ceas, altfel None."""
	fel = felCertificat(eroare)
	if fel is None or fel == ALT:
		return None
	ceas = judecaCeasul(acum, stare, jos)
	return ceas if _ceasulEDeVina(fel, ceas) else None


# ---------------------------------------------------------------- resincronizarea (o singura data)

_RESINCRONIZARE = {"ceruta": False}
_LACAT = threading.Lock()


def _peFirulPrincipal(functie):
	principal = getattr(threading, "main_thread", None)
	if principal is not None and threading.current_thread() is principal():
		functie()
		return True
	try:
		from twisted.internet import reactor
		reactor.callFromThread(functie)
		return True
	except Exception as e:
		_jurnal("resincronizarea nu a putut fi trimisa pe firul enigma2: %r" % (e,))
		return False


def ceareResincronizare(planifica=None):
	"""Cere o sincronizare a orei prin Internet (HdsCeas), cel mult o data pe pornirea enigma2. -> True daca a cerut-o
	acum. Nimic cand HdsCeas nu e pornit, cand sursa e numai transponderul sau cand o sincronizare merge deja."""
	s = _C._unic[0] if _C is not None else None
	if s is None:
		return False
	try:
		if s.mod() not in ("auto", "ntp") or s.inCurs():
			return False
	except Exception:
		return False
	with _LACAT:
		if _RESINCRONIZARE["ceruta"]:
			return False
		_RESINCRONIZARE["ceruta"] = True

	def sincronizeaza():
		try:
			pornit, motiv = s.sincronizeaza()
			_jurnal("resincronizare ceruta dupa o eroare de certificat: %s" % motiv)
		except Exception as e:
			_jurnal("resincronizarea: %r" % (e,))

	return bool((planifica or _peFirulPrincipal)(sincronizeaza))


# ---------------------------------------------------------------- textele pentru om

def textOra(acum):
	try:
		return time.strftime("%d.%m.%Y %H:%M", time.localtime(acum))
	except (ValueError, OverflowError, OSError):
		return u"?"


def _cauza(ceas, ora):
	if ceas == IN_URMA:
		return _("Ceasul receptorului e în urmă (arată %s), de aceea certificatele site-urilor par încă nevalabile.") % ora
	if ceas == IN_VIITOR:
		return _("Ceasul receptorului e înainte (arată %s), de aceea certificatele site-urilor par expirate.") % ora
	return _("Ora receptorului nu e încă sigură (arată %s), iar certificatul site-ului nu se potrivește cu ea: de vină "
		"e ceasul, nu internetul.") % ora


def textCeFaci():
	return _("Potrivește ora din Meniu › Setări › Sistem și dispozitive › Data și ora, apoi încearcă din nou.")


def _scurt(ceas, ora):
	if ceas == IN_URMA:
		return _("Ceasul e în urmă (%s): potrivește ora în Data și ora.") % ora
	if ceas == IN_VIITOR:
		return _("Ceasul e înainte (%s): potrivește ora în Data și ora.") % ora
	return _("Ora nu e încă sigură (%s): potrivește ora în Data și ora.") % ora


def texte(eroare, acum=None, stare=_DIN_CEAS, jos=None, resincronizeaza=True):
	"""(cauza, ce_faci) cand eroarea de certificat vine de la ceas, altfel None. Cauza spune si ca ora se sincronizeaza
	acum, cand s-a cerut chiar acum o resincronizare."""
	acum = time.time() if acum is None else acum
	ceas = deVinaECeasul(eroare, acum, stare, jos)
	if ceas is None:
		return None
	ora = textOra(acum)
	cauza = _cauza(ceas, ora)
	_jurnal("eroare de certificat din cauza ceasului (%s, ceasul arata %s)" % (ceas, ora))
	if resincronizeaza and ceareResincronizare():
		cauza += u" " + _("Ora se sincronizează acum prin Internet.")
	return cauza, textCeFaci()


def mesaj(eroare, acum=None, stare=_DIN_CEAS, jos=None, resincronizeaza=True):
	"""Textul intreg (cauza si ce faci) cand eroarea de certificat vine de la ceas, altfel None."""
	t = texte(eroare, acum, stare, jos, resincronizeaza)
	return None if t is None else u"%s %s" % t


def scurt(eroare, acum=None, stare=_DIN_CEAS, jos=None, resincronizeaza=True):
	"""Un singur rand (ecranele cu loc putin), cand eroarea de certificat vine de la ceas, altfel None."""
	acum = time.time() if acum is None else acum
	ceas = deVinaECeasul(eroare, acum, stare, jos)
	if ceas is None:
		return None
	ora = textOra(acum)
	_jurnal("eroare de certificat din cauza ceasului (%s, ceasul arata %s)" % (ceas, ora))
	if resincronizeaza:
		ceareResincronizare()
	return _scurt(ceas, ora)
