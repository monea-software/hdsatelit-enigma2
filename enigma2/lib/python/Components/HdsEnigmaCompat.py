# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEnigmaCompat.py: functiile mici pe care pluginurile altor imagini le iau din modulul enigma
# (`from enigma import getBoxType`) si pe care nucleul nostru nu le are. Sunt facute aici in Python, cu numele, argumentele si
# valorile intoarse ca la ele, si puse in enigma la pornire (mytest.py, inainte de pluginuri). Un nume care exista deja in
# enigma nu se schimba. Nu arunca: o greseala aici lasa numai numele nepus.
#
#   getBoxType()                 modelul (BoxInfo "model"), ca in alte imagini
#   getBoxBrand()                marca (BoxInfo "brand")
#   checkInternetAccess(host, timeout=3)
#                                0 merge; 1 numele nu se rezolva; 2 legatura nu se face; 3 interfata nu e pornita; 4 nicio
#                                interfata de retea (aceleasi coduri ca in alte imagini). Asteapta cel mult
#                                timeout secunde numele (pe un fir separat) si tot atat legatura la fiecare adresa.
#   detectImageType(cale)        felul pozei dupa primii octeti: 0 PNG, 1 JPEG, 2 BMP, 3 GIF, 4 SVG, 5 WEBP, -1 altceva
#   getPeerStreamingBoxes()      receptoarele din retea care dau canale; aici lista e goala (nu le cautam)
#   setSpinnerOnOff(pornit)      pluginurile opresc rotita cat ruleaza altceva; la noi rotita o tine nucleul, deci nu face nimic
#   getBsodCounter()            0: nucleul incheie procesul la caderea fatala, fara contor accesibil din Python
#   getE2Rev()                   versiunea pachetului enigma2 al imaginii (din opkg), pentru rapoartele pluginurilor; "" cand nu se stie
#   eGetEnigmaDebugLvl()         0: nucleul nu expune un nivel numeric de jurnalizare
#
# completeazaTwisted(): numele HTTP vechi pentru pluginuri si adrese primite ca text.
import os
import socket

_DIR_RETEA = "/sys/class/net"


def getBoxType():
	from Components.SystemInfo import BoxInfo
	return BoxInfo.getItem("model") or ""


def getBoxBrand():
	from Components.SystemInfo import BoxInfo
	return BoxInfo.getItem("brand") or ""


def _stareLegatura(dosar=_DIR_RETEA):
	"""0 o interfata (alta decat lo) e pornita; 3 sunt interfete, dar niciuna pornita; 4 nicio interfata"""
	try:
		nume = [n for n in os.listdir(dosar) if n != "lo"]
	except OSError:
		return 4
	if not nume:
		return 4
	for n in nume:
		try:
			with open(os.path.join(dosar, n, "operstate")) as f:
				stare = f.read().strip()
		except OSError:
			continue
		# "unknown": interfete fara stare (ppp, tun) care merg
		if stare in ("up", "unknown"):
			return 0
	return 3


def _gazdaSiPort(host):
	text = str(host or "").strip()
	port = None
	if "://" in text:
		schema, text = text.split("://", 1)
		port = {"https": 443, "http": 80, "ftp": 21}.get(schema.lower())
	text = text.split("/", 1)[0].split("@")[-1]
	if text.startswith("["):
		gazda, _, rest = text[1:].partition("]")
		if rest.startswith(":") and rest[1:].isdigit():
			port = int(rest[1:])
	elif text.count(":") == 1:
		gazda, p = text.split(":")
		if p.isdigit():
			port = int(p)
	else:
		gazda = text
	return gazda, port or 80


def _rezolva(gazda, port, timeout, getaddrinfo=None):
	"""adresele gazdei sau codul de eroare (1 numele nu se rezolva sau nu raspunde in timeout secunde, 2 alta eroare). getaddrinfo nu are termen:
	ruleaza pe un fir separat, iar firul care cheama asteapta cel mult timeout secunde."""
	import threading
	getaddrinfo = getaddrinfo or socket.getaddrinfo
	rez = {}

	def lucru():
		try:
			rez["adrese"] = getaddrinfo(gazda, port, 0, socket.SOCK_STREAM)
		except (socket.gaierror, UnicodeError):
			rez["cod"] = 1
		except OSError:
			rez["cod"] = 2
	fir = threading.Thread(target=lucru, name="checkInternetAccess")
	fir.daemon = True
	fir.start()
	fir.join(max(0.1, float(timeout or 0)))
	if "adrese" in rez:
		return rez["adrese"]
	return rez.get("cod", 1)


def checkInternetAccess(host, timeout=3):
	legatura = _stareLegatura()
	if legatura:
		return legatura
	gazda, port = _gazdaSiPort(host)
	if not gazda:
		return 1
	adrese = _rezolva(gazda, port, timeout)
	if isinstance(adrese, int):
		return adrese
	for familie, fel, proto, _nume, adresa in adrese:
		s = None
		try:
			s = socket.socket(familie, fel, proto)
			s.settimeout(timeout)
			s.connect(adresa)
			return 0
		except OSError:
			continue
		finally:
			if s is not None:
				s.close()
	return 2


def detectImageType(cale):
	try:
		with open(cale, "rb") as f:
			b = f.read(12)
	except (OSError, TypeError):
		return -1
	if len(b) <= 4:
		return -1
	if b[1:4] == b"PNG":
		return 0
	if (len(b) > 9 and b[6:10] == b"JFIF") or b[:3] == b"\xff\xd8\xff":
		return 1
	if b[:2] == b"BM":
		return 2
	if b[:3] == b"GIF":
		return 3
	if b[:1] == b"<" and b[1:4].lower() == b"svg":
		return 4
	if len(b) > 11 and b[:4] == b"RIFF" and b[8:12] == b"WEBP":
		return 5
	return -1


def getPeerStreamingBoxes():
	return []


def setSpinnerOnOff(pornit):
	return None


def getBsodCounter():
	# bsod_active din C++ este o protectie la reintrare, iar erorile protejate nu sunt caderi ale interfetei.
	# Nu exista un contor BSOD al sesiunii expus aici; jurnalele pot fi din sesiuni mai vechi.
	return 0


def getE2Rev():
	try:
		with open("/var/lib/opkg/info/enigma2-hdsatelit.control", encoding="utf-8", errors="replace") as f:
			for rand in f:
				if rand.startswith("Version:"):
					return rand.split(":", 1)[1].strip()
	except OSError:
		pass
	return ""


def eGetEnigmaDebugLvl():
	# Interfata web il citeste numai ca informatie. Nu exista un nivel citibil in nucleu.
	return 0


NUME = ("getBoxType", "getBoxBrand", "checkInternetAccess", "detectImageType", "getPeerStreamingBoxes", "setSpinnerOnOff", "getBsodCounter",
	"getE2Rev", "eGetEnigmaDebugLvl")


# ------------------------------------------------------------------ twisted: adresa ca text
# Pluginurile scrise pentru Python 2 si trecute pe Python 3 dau adesea adresa ca text: getPage("http://..."), downloadPage("http://...", cale),
# resource.putChild("nume", ...). Twisted cere octeti si cade cu TypeError. Aici textul se face octeti (UTF-8) inainte de apel; octetii
# merg ca pana acum. Se pune o singura data (_textOcteti pe functie).

def _octeti(x):
	return x.encode("utf-8") if isinstance(x, str) else x


def _primulOcteti(f):
	def apel(url, *a, **k):
		return f(_octeti(url), *a, **k)
	apel._textOcteti = True
	apel.__name__ = getattr(f, "__name__", "apel")
	apel.__doc__ = getattr(f, "__doc__", None)
	return apel


def completeazaTwisted():
	"""Completeaza API-ul HTTP vechi pentru pluginuri. Intoarce numele schimbate."""
	schimbate = []
	try:
		from twisted.web import client
		from Components import HdsTwistedCompat
		schimbate.extend(HdsTwistedCompat.completeaza())
		for nume in ("getPage", "downloadPage"):
			f = getattr(client, nume, None)
			if f is not None and not getattr(f, "_textOcteti", False):
				setattr(client, nume, _primulOcteti(f))
				schimbate.append(nume)
	except Exception as e:
		print("[HdsEnigmaCompat] twisted.web.client: %r" % (e,))
	try:
		from twisted.web import resource
		f = resource.Resource.putChild
		if not getattr(f, "_textOcteti", False):
			def putChild(self, path, child):
				return f(self, _octeti(path), child)
			putChild._textOcteti = True
			resource.Resource.putChild = putChild
			schimbate.append("putChild")
	except Exception as e:
		print("[HdsEnigmaCompat] twisted.web.resource: %r" % (e,))
	return schimbate


# constante pe clasele din enigma pe care le cer pluginurile (clasa, nume, valoare): evGstRecordEnded = sfarsitul unei inregistrari facute
# prin GStreamer, evRecordAborted = o inregistrare oprita de alta imagine; imaginea nu le trimite niciodata, deci valorile sunt dupa ultimul
# eveniment al clasei (evNewEventInfo = 9 in lib/service/iservice.h), ca sa nu se confunde cu unul adevarat
CONSTANTE = (("iRecordableService", "evGstRecordEnded", 100), ("iRecordableService", "evRecordAborted", 101))

# Scalarea cu proportii exista deja in lista C++ (lib/gui/elistboxcontent.h si .cpp).
# Aliasul se pune numai cand nucleul expune numele care face operatia, fara valoare de rezerva.
ALIASURI = (("SCALE_ASPECT", "BT_KEEP_ASPECT_RATIO"),)


def completeaza(enigma=None):
	"""Pune numele, constantele si aliasurile care lipsesc. Intoarce lista celor puse."""
	puse = []
	try:
		if enigma is None:
			import enigma
		for nume in NUME:
			if not hasattr(enigma, nume):
				setattr(enigma, nume, globals()[nume])
				puse.append(nume)
		for nume, original in ALIASURI:
			if not hasattr(enigma, nume) and hasattr(enigma, original):
				setattr(enigma, nume, getattr(enigma, original))
				puse.append(nume)
		for clasa, nume, valoare in CONSTANTE:
			c = getattr(enigma, clasa, None)
			if c is not None and not hasattr(c, nume):
				setattr(c, nume, valoare)
				puse.append("%s.%s" % (clasa, nume))
	except Exception as e:
		print("[HdsEnigmaCompat] %r" % (e,))
	return puse
