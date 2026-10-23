# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsReteaProtocoale.py: protocoalele locurilor din retea (Components/HdsStocareRetea.py), numai partea de client:
#   - SSDP (cautarea serverelor media din casa), descrierea aparatului UPnP, ContentDirectory Browse si DIDL-Lite
#     (dosarele, filmele si subtitrarile date de server);
#   - WebDAV: PROPFIND cu Depth 1, autentificarea Basic si Digest (RFC 7616, MD5 si SHA-256, qop=auth);
#   - FTP: randurile MLSD si LIST (felul Unix si felul Windows);
#   - NFS: lista exporturilor unui server (RPC: portmapper GETPORT, apoi MOUNT EXPORT, pe TCP);
#   - NetBIOS: din raspunsul NBSTAT, numele aparatului si daca are serviciul de fisiere (sufixul 0x20);
#   - mDNS: intrebarea PTR pentru serviciile de fisiere (_smb, _nfs, _webdav, _ftp) si raspunsul (PTR, SRV, A).
#
# Toate functiile primesc si dau octeti sau texte: soclurile, termenele si firele sunt in HdsStocareRetea. Un XML venit
# din retea se citeste numai pana la MAX_XML octeti si fara entitati externe (expat din Python nu le incarca). Nimic de
# aici nu tine o parola: antetele de autentificare se fac la cerere si nu se scriu nicaieri.
#
# Fisierul nu importa nimic din enigma2: probele de pe PC il folosesc direct.

import base64
import hashlib
import os
import re
import struct
import time

try:
	from urllib.parse import quote, unquote, urljoin, urlsplit
except ImportError:		# pragma: no cover
	from urllib import quote, unquote
	from urlparse import urljoin, urlsplit

MAX_XML = 4 * 1024 * 1024
MAX_INTRARI = 5000

# ------------------------------------------------------------------ XML

def _xml(octeti):
	"""Radacina unui document XML venit din retea, sau None (gol, prea mare, stricat, cu DOCTYPE)."""
	if not octeti or len(octeti) > MAX_XML:
		return None
	if isinstance(octeti, str):
		octeti = octeti.encode("utf-8", "replace")
	# un DOCTYPE nu are ce cauta in raspunsurile UPnP sau WebDAV: refuzat, ca orice entitate sa nu se poata umfla
	if b"<!DOCTYPE" in octeti[:2048].upper() or b"<!ENTITY" in octeti.upper():
		return None
	try:
		import xml.etree.ElementTree as ET
		return ET.fromstring(octeti)
	except Exception:
		return None


def _local(tag):
	"""Numele fara spatiul de nume: '{urn:...}title' -> 'title'."""
	return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _copii(nod, nume):
	return [c for c in list(nod) if _local(c.tag) == nume]


def _primul(nod, nume):
	for c in list(nod):
		if _local(c.tag) == nume:
			return c
	return None


def _text(nod, nume, implicit=u""):
	c = _primul(nod, nume) if nod is not None else None
	if c is None or c.text is None:
		return implicit
	return c.text.strip()


def _cauta(nod, nume):
	"""Primul descendent cu numele dat (oricare spatiu de nume), sau None."""
	if nod is None:
		return None
	for c in nod.iter():
		if _local(c.tag) == nume:
			return c
	return None


def _int(text, implicit=None):
	try:
		return int(str(text).strip())
	except (TypeError, ValueError):
		return implicit


# ------------------------------------------------------------------ SSDP si UPnP

SSDP = ("239.255.255.250", 1900)
ST_SERVER_MEDIA = "urn:schemas-upnp-org:device:MediaServer:1"
SERVICIU_CONTINUT = "urn:schemas-upnp-org:service:ContentDirectory"


def intrebareSsdp(st=ST_SERVER_MEDIA, asteptare=2):
	"""M-SEARCH (UPnP Device Architecture 1.1, 1.3.2)."""
	return ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: %d\r\nST: %s\r\n"
		"USER-AGENT: Linux/4.4 UPnP/1.1 HDSatelit/1.0\r\n\r\n" % (asteptare, st)).encode("ascii")


def raspunsSsdp(date):
	"""Antetele unui raspuns SSDP (chei cu litere mici), sau {} daca nu e unul."""
	try:
		text = date.decode("utf-8", "replace") if isinstance(date, bytes) else date
	except Exception:
		return {}
	randuri = text.split("\r\n") if "\r\n" in text else text.split("\n")
	if not randuri or not (randuri[0].upper().startswith("HTTP/1.1 200") or randuri[0].upper().startswith("NOTIFY")):
		return {}
	antete = {}
	for r in randuri[1:]:
		if ":" in r:
			k, v = r.split(":", 1)
			antete[k.strip().lower()] = v.strip()
	return antete


def adresaHttpBuna(adresa, ip=None):
	"""True pentru o adresa http:// cu gazda (si, cand e dat ip, numai spre acel aparat: un raspuns SSDP nu poate
	trimite receptorul la alta gazda decat cea care a raspuns)."""
	try:
		p = urlsplit(adresa or "")
	except ValueError:
		return False
	if p.scheme not in ("http", "https") or not p.hostname:
		return False
	return ip is None or p.hostname == ip


def descriereAparat(octeti, adresa):
	"""Descrierea unui aparat UPnP -> {nume, producator, model, control (adresa ContentDirectory), udn} sau None
	daca nu are ContentDirectory. `adresa` e LOCATION (pentru adresele relative)."""
	r = _xml(octeti)
	if r is None:
		return None
	baza = _text(r, "URLBase") or adresa
	aparat = _cauta(r, "device")
	if aparat is None:
		return None
	control = u""
	for s in aparat.iter():
		if _local(s.tag) != "service":
			continue
		tip = _text(s, "serviceType")
		if tip.startswith(SERVICIU_CONTINUT):
			control = _text(s, "controlURL")
			break
	if not control:
		return None
	return {
		"nume": _text(aparat, "friendlyName") or urlsplit(adresa).hostname or u"",
		"producator": _text(aparat, "manufacturer"),
		"model": _text(aparat, "modelName"),
		"control": urljoin(baza, control),
		"udn": _text(aparat, "UDN"),
	}


def _xmlText(text):
	return (text or u"").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def cerereBrowse(obiect, start=0, cate=200):
	"""Corpul SOAP pentru ContentDirectory:1 Browse(BrowseDirectChildren) si antetul SOAPACTION."""
	corp = (u'<?xml version="1.0" encoding="utf-8"?>\r\n'
		u'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
		u's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
		u'<u:Browse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">'
		u'<ObjectID>%s</ObjectID><BrowseFlag>BrowseDirectChildren</BrowseFlag><Filter>*</Filter>'
		u'<StartingIndex>%d</StartingIndex><RequestedCount>%d</RequestedCount><SortCriteria></SortCriteria>'
		u'</u:Browse></s:Body></s:Envelope>') % (_xmlText(obiect), int(start), int(cate))
	return corp.encode("utf-8"), '"urn:schemas-upnp-org:service:ContentDirectory:1#Browse"'


def raspunsBrowse(octeti):
	"""Raspunsul Browse -> (DIDL-Lite ca text, NumberReturned, TotalMatches) sau None (eroare SOAP sau stricat)."""
	r = _xml(octeti)
	if r is None:
		return None
	rez = _cauta(r, "BrowseResponse")
	if rez is None:
		return None
	return _text(rez, "Result"), _int(_text(rez, "NumberReturned"), 0), _int(_text(rez, "TotalMatches"), 0)


EXT_SUBTITRARI = (".srt", ".ass", ".ssa", ".sub", ".smi", ".vtt", ".txt", ".idx")


def _durata(text):
	"""'1:23:45.000' -> secunde (int) sau None."""
	m = re.match(r"^\s*(\d+):(\d{1,2}):(\d{1,2})", text or "")
	if not m:
		return None
	return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


def didl(text, baza=u""):
	"""DIDL-Lite -> [{fel: 'dosar'|'fisier', id, titlu, adresa, marime, durata, mime, clasa, subtitrari: [adrese]}].
	Subtitrarile date de server: pistele <res> cu tip text (text/srt, application/x-subrip...), sec:CaptionInfo /
	CaptionInfoEx si elementele *subtitleFileUri; numai adrese http(s)."""
	r = _xml(text)
	if r is None:
		return []
	rez = []
	for n in list(r):
		fel = _local(n.tag)
		if fel not in ("container", "item") or len(rez) >= MAX_INTRARI:
			continue
		titlu = _text(n, "title") or n.get("id") or u"?"
		intrare = {"fel": "dosar" if fel == "container" else "fisier", "id": n.get("id") or u"", "titlu": titlu,
			"adresa": u"", "marime": None, "durata": None, "mime": u"", "clasa": _text(n, "class"), "subtitrari": [],
			"copii": _int(n.get("childCount"))}
		if fel == "item":
			for res in _copii(n, "res"):
				adresa = (res.text or u"").strip()
				info = res.get("protocolInfo") or u""
				mime = info.split(":")[2] if info.count(":") >= 3 else u""
				if not adresaHttpBuna(adresa):
					continue
				if mime.startswith("text/") or "subrip" in mime or mime in ("application/x-ass", "application/x-ssa",
						"smi/caption", "application/ttml+xml"):
					intrare["subtitrari"].append(urljoin(baza, adresa))
					continue
				if not intrare["adresa"]:
					intrare["adresa"] = urljoin(baza, adresa)
					intrare["mime"] = mime
					intrare["marime"] = _int(res.get("size"))
					intrare["durata"] = _durata(res.get("duration"))
			for c in n.iter():
				nume = _local(c.tag)
				if nume in ("CaptionInfo", "CaptionInfoEx", "subtitleFileUri", "subtitleURI"):
					adresa = (c.text or u"").strip()
					if adresaHttpBuna(adresa) and adresa not in intrare["subtitrari"]:
						intrare["subtitrari"].append(adresa)
			if not intrare["adresa"]:
				continue
		rez.append(intrare)
	return rez


# ------------------------------------------------------------------ WebDAV

CERERE_PROPFIND = (b'<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:"><d:prop><d:displayname/>'
	b'<d:resourcetype/><d:getcontentlength/><d:getlastmodified/><d:getcontenttype/></d:prop></d:propfind>')


def _dataHttp(text):
	try:
		import email.utils
		t = email.utils.parsedate_tz(text or "")
		return int(email.utils.mktime_tz(t)) if t else None
	except Exception:
		return None


def raspunsPropfind(octeti, cale):
	"""Multistatus -> [{nume, cale (decodata, fara schema si gazda), dosar, marime, data, mime}], fara dosarul
	cerut insusi (`cale`)."""
	r = _xml(octeti)
	if r is None:
		return None
	cerut = unquote(urlsplit(cale).path or cale).rstrip("/")
	rez = []
	for raspuns in r.iter():
		if _local(raspuns.tag) != "response" or len(rez) >= MAX_INTRARI:
			continue
		href = _text(raspuns, "href")
		if not href:
			continue
		drum = unquote(urlsplit(href).path or href)
		if drum.rstrip("/") == cerut:
			continue
		prop = None
		for ps in _copii(raspuns, "propstat"):
			stare = _text(ps, "status")
			if " 200" in stare or not stare:
				prop = _primul(ps, "prop")
				break
		if prop is None:
			continue
		tip = _primul(prop, "resourcetype")
		dosar = tip is not None and _primul(tip, "collection") is not None
		nume = drum.rstrip("/").rsplit("/", 1)[-1] or _text(prop, "displayname")
		if not nume:
			continue
		rez.append({"nume": nume, "cale": drum, "dosar": dosar, "marime": None if dosar else _int(_text(prop,
			"getcontentlength")), "data": _dataHttp(_text(prop, "getlastmodified")), "mime": _text(prop,
			"getcontenttype")})
	return rez


def antetBasic(utilizator, parola):
	return "Basic " + base64.b64encode((u"%s:%s" % (utilizator, parola)).encode("utf-8")).decode("ascii")


def provocareDigest(antet):
	"""WWW-Authenticate: Digest ... -> dict (realm, nonce, qop, algorithm, opaque) sau None."""
	if not antet or not antet.strip().lower().startswith("digest"):
		return None
	rez = {}
	for m in re.finditer(r'(\w+)\s*=\s*("([^"]*)"|([^,\s]*))', antet.strip()[6:]):
		rez[m.group(1).lower()] = m.group(3) if m.group(3) is not None else m.group(4)
	return rez if rez.get("nonce") else None


def antetDigest(provocare, metoda, uri, utilizator, parola, nc=1, cnonce=None):
	"""Antetul Authorization pentru Digest (RFC 7616: MD5, MD5-sess, SHA-256, qop=auth sau fara qop); None pentru un
	algoritm necunoscut sau qop fara auth."""
	alg = (provocare.get("algorithm") or "MD5").upper()
	sess = alg.endswith("-SESS")
	baza = alg[:-5] if sess else alg
	if baza == "MD5":
		h = lambda s: hashlib.md5(s.encode("utf-8")).hexdigest()
	elif baza == "SHA-256":
		h = lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()
	else:
		return None
	cnonce = cnonce or base64.b16encode(os.urandom(8)).decode("ascii").lower()
	realm = provocare.get("realm") or ""
	nonce = provocare["nonce"]
	ha1 = h("%s:%s:%s" % (utilizator, realm, parola))
	if sess:
		ha1 = h("%s:%s:%s" % (ha1, nonce, cnonce))
	ha2 = h("%s:%s" % (metoda, uri))
	qop = provocare.get("qop")
	campuri = ['username="%s"' % utilizator.replace('"', ''), 'realm="%s"' % realm, 'nonce="%s"' % nonce,
		'uri="%s"' % uri, 'algorithm=%s' % (provocare.get("algorithm") or "MD5")]
	if qop:
		if "auth" not in [q.strip() for q in qop.split(",")]:
			return None
		ncs = "%08x" % nc
		raspuns = h("%s:%s:%s:%s:auth:%s" % (ha1, nonce, ncs, cnonce, ha2))
		campuri += ['qop=auth', 'nc=%s' % ncs, 'cnonce="%s"' % cnonce]
	else:
		raspuns = h("%s:%s:%s" % (ha1, nonce, ha2))
	campuri.append('response="%s"' % raspuns)
	if provocare.get("opaque") is not None:
		campuri.append('opaque="%s"' % provocare["opaque"])
	return "Digest " + ", ".join(campuri)


def caleWebdav(dosar, nume=None):
	"""Calea codata pentru o cerere: '/Filme 2024/' + 'a b.mkv' -> '/Filme%202024/a%20b.mkv'."""
	cale = u"/" + u"/".join(p for p in (dosar or u"").split(u"/") if p)
	if nume:
		cale = cale.rstrip(u"/") + u"/" + nume
	elif not cale.endswith(u"/"):
		cale += u"/"
	return quote(cale.encode("utf-8"), safe="/")


# ------------------------------------------------------------------ FTP

_LUNI = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
	"nov": 11, "dec": 12}
_UNIX = re.compile(r"^([\-dlbcps])[rwxsStT\-]{9}[+@.]?\s+\d+\s+\S+\s+\S+\s+(\d+)\s+(\w{3})\s+(\d{1,2})\s+"
	r"(\d{1,2}:\d{2}|\d{4})\s(.+)$")
_WINDOWS = re.compile(r"^(\d{2})-(\d{2})-(\d{2,4})\s+(\d{1,2}):(\d{2})([AP]M)?\s+(<DIR>|\d+)\s+(.+)$", re.I)


def randLista(rand, an=None):
	"""Un rand LIST (Unix sau Windows/IIS) -> {nume, dosar, marime, data} sau None (legaturile Unix: numele de dinainte
	de ' -> ', ca fisier)."""
	rand = (rand or u"").rstrip("\r\n")
	m = _UNIX.match(rand)
	if m:
		fel, marime, luna, zi, ora_an, nume = m.groups()
		if fel == "l" and " -> " in nume:
			nume = nume.split(" -> ", 1)[0]
		if nume in (".", ".."):
			return None
		an = an or time.localtime().tm_year
		data = None
		try:
			if ":" in ora_an:
				h, mi = ora_an.split(":")
				data = int(time.mktime((an, _LUNI.get(luna.lower(), 1), int(zi), int(h), int(mi), 0, 0, 0, -1)))
			else:
				data = int(time.mktime((int(ora_an), _LUNI.get(luna.lower(), 1), int(zi), 0, 0, 0, 0, 0, -1)))
		except (ValueError, OverflowError):
			pass
		return {"nume": nume, "dosar": fel == "d", "marime": None if fel == "d" else int(marime), "data": data}
	m = _WINDOWS.match(rand)
	if m:
		lu, zi, an_, h, mi, ampm, marime, nume = m.groups()
		if nume in (".", ".."):
			return None
		an_ = int(an_)
		if an_ < 100:
			an_ += 2000 if an_ < 70 else 1900
		h = int(h)
		if ampm:
			h = h % 12 + (12 if ampm.upper() == "PM" else 0)
		try:
			data = int(time.mktime((an_, int(lu), int(zi), h, int(mi), 0, 0, 0, -1)))
		except (ValueError, OverflowError):
			data = None
		dosar = marime.upper() == "<DIR>"
		return {"nume": nume, "dosar": dosar, "marime": None if dosar else int(marime), "data": data}
	return None


def randMlsd(nume, fapte):
	"""Un rand MLSD (nume, {fapt: valoare}) -> {nume, dosar, marime, data} sau None (cdir, pdir)."""
	tip = (fapte.get("type") or "").lower()
	if tip in ("cdir", "pdir") or nume in (".", ".."):
		return None
	data = None
	m = fapte.get("modify") or ""
	if len(m) >= 14 and m[:14].isdigit():
		try:
			import calendar
			data = calendar.timegm((int(m[:4]), int(m[4:6]), int(m[6:8]), int(m[8:10]), int(m[10:12]),
				int(m[12:14]), 0, 0, 0))
		except (ValueError, OverflowError):
			data = None
	dosar = tip == "dir"
	return {"nume": nume, "dosar": dosar, "marime": None if dosar else _int(fapte.get("size")), "data": data}


def decodeazaNume(octeti):
	"""Un nume primit de la un server FTP: UTF-8, altfel Windows-1250 (serverele vechi din casa)."""
	if isinstance(octeti, str):
		return octeti
	try:
		return octeti.decode("utf-8")
	except UnicodeDecodeError:
		return octeti.decode("cp1250", "replace")


# ------------------------------------------------------------------ NFS (RPC pe TCP)

PROG_PORTMAP = 100000
PROG_MOUNT = 100005
PORT_PORTMAP = 111
MAX_RPC = 1024 * 1024


def _xdrSir(octeti):
	n = len(octeti)
	return struct.pack(">I", n) + octeti + b"\0" * ((4 - n % 4) % 4)


def cerereRpc(xid, program, versiune, procedura, argumente=b""):
	"""Un apel RPC (RFC 5531) cu AUTH_NULL, cu marcajul de fragment pentru TCP."""
	corp = struct.pack(">IIIIIIIIII", xid, 0, 2, program, versiune, procedura, 0, 0, 0, 0) + argumente
	return struct.pack(">I", 0x80000000 | len(corp)) + corp


def cerereGetport(xid, program, versiune, proto=6):
	return cerereRpc(xid, PROG_PORTMAP, 2, 3, struct.pack(">IIII", program, versiune, proto, 0))


def cerereExport(xid, versiune=3):
	return cerereRpc(xid, PROG_MOUNT, versiune, 5)


def corpRaspunsRpc(octeti, xid):
	"""Datele unui raspuns RPC acceptat (dupa antet) sau None. `octeti`: fragmentele TCP lipite (fara marcaje)."""
	try:
		rxid, tip, stare = struct.unpack(">III", octeti[:12])
		if rxid != xid or tip != 1 or stare != 0:
			return None
		lung = struct.unpack(">I", octeti[16:20])[0]
		i = 20 + lung + (4 - lung % 4) % 4
		acceptat = struct.unpack(">I", octeti[i:i + 4])[0]
		if acceptat != 0:
			return None
		return octeti[i + 4:]
	except struct.error:
		return None


def fragmenteRpc(citeste):
	"""Citeste un raspuns RPC de pe TCP (citeste(n) -> octeti, cel mult n): fragmentele lipite, sau None."""
	rez = b""
	while True:
		antet = _citesteTot(citeste, 4)
		if antet is None:
			return None
		marcaj = struct.unpack(">I", antet)[0]
		lung = marcaj & 0x7FFFFFFF
		if len(rez) + lung > MAX_RPC:
			return None
		bucata = _citesteTot(citeste, lung)
		if bucata is None:
			return None
		rez += bucata
		if marcaj & 0x80000000:
			return rez


def _citesteTot(citeste, n):
	rez = b""
	while len(rez) < n:
		b = citeste(n - len(rez))
		if not b:
			return None
		rez += b
	return rez


def raspunsGetport(corp):
	try:
		return struct.unpack(">I", corp[:4])[0]
	except (struct.error, TypeError):
		return None


def raspunsExport(corp):
	"""exportlist (RFC 1813, MOUNTPROC3_EXPORT) -> [(dosar, [grupuri])]."""
	rez = []
	i = 0
	try:
		while struct.unpack(">I", corp[i:i + 4])[0] == 1 and len(rez) < MAX_INTRARI:
			i += 4
			n = struct.unpack(">I", corp[i:i + 4])[0]
			dosar = corp[i + 4:i + 4 + n].decode("utf-8", "replace")
			i += 4 + n + (4 - n % 4) % 4
			grupuri = []
			while struct.unpack(">I", corp[i:i + 4])[0] == 1:
				i += 4
				n = struct.unpack(">I", corp[i:i + 4])[0]
				grupuri.append(corp[i + 4:i + 4 + n].decode("utf-8", "replace"))
				i += 4 + n + (4 - n % 4) % 4
			i += 4
			rez.append((dosar, grupuri))
	except (struct.error, IndexError):
		pass
	return rez


# ------------------------------------------------------------------ NetBIOS (raspunsul NBSTAT)

def numeNetbios(date):
	"""Raspunsul NBSTAT -> (numele aparatului, are serviciul de fisiere) sau ("", False). Intrebarea o face
	HdsAparateRetea.intrebare_netbios."""
	nume = u""
	fisiere = False
	try:
		if len(date) < 57:
			return nume, fisiere
		_id, steaguri, _qd, an = struct.unpack(">HHHH", date[:8])
		if not steaguri & 0x8000 or an < 1 or bytearray(date[12:13])[0] != 0x20:
			return nume, fisiere
		i = 12 + 34
		tip = struct.unpack(">H", date[i:i + 2])[0]
		if tip != 0x21:
			return nume, fisiere
		i += 10
		n = bytearray(date[i:i + 1])[0]
		i += 1
		for k in range(n):
			bucata = date[i + 18 * k:i + 18 * k + 18]
			if len(bucata) < 18:
				break
			text = bucata[:15].decode("ascii", "replace").strip()
			sufix = bytearray(bucata[15:16])[0]
			grup = struct.unpack(">H", bucata[16:18])[0] & 0x8000
			if grup or not text or u"�" in text:
				continue
			if sufix == 0x00 and not nume:
				nume = text
			elif sufix == 0x20:
				fisiere = True
				nume = nume or text
	except (struct.error, IndexError, ValueError):
		return u"", False
	return nume, fisiere


# ------------------------------------------------------------------ mDNS

MDNS = ("224.0.0.251", 5353)
SERVICII_MDNS = {
	"_smb._tcp.local": "smb",
	"_nfs._tcp.local": "nfs",
	"_webdav._tcp.local": "webdav",
	"_webdavs._tcp.local": "webdavs",
	"_ftp._tcp.local": "ftp",
}


def _numeDns(nume):
	return b"".join(struct.pack("B", len(e)) + e.encode("ascii") for e in nume.strip(".").split(".") if e) + b"\x00"


def intrebareMdns(ident=0):
	"""O intrebare PTR pentru toate serviciile de fisiere, cu bitul 'raspunde direct' (QU), ca raspunsul sa vina la
	soclul care a intrebat."""
	tipuri = sorted(SERVICII_MDNS)
	pachet = struct.pack(">HHHHHH", ident, 0, len(tipuri), 0, 0, 0)
	for t in tipuri:
		pachet += _numeDns(t) + struct.pack(">HH", 12, 0x8001)
	return pachet


def _numeDin(date, i, adancime=0):
	"""(numele, pozitia de dupa el) dintr-un pachet DNS, cu pointeri; ("", -1) daca e stricat."""
	parti = []
	sfarsit = -1
	while adancime < 20:
		if i >= len(date):
			return u"", -1
		lung = bytearray(date[i:i + 1])[0]
		if lung == 0:
			if sfarsit < 0:
				sfarsit = i + 1
			return u".".join(parti), sfarsit
		if lung & 0xC0 == 0xC0:
			if i + 2 > len(date):
				return u"", -1
			tinta = struct.unpack(">H", date[i:i + 2])[0] & 0x3FFF
			if sfarsit < 0:
				sfarsit = i + 2
			i = tinta
			adancime += 1
			continue
		parti.append(date[i + 1:i + 1 + lung].decode("utf-8", "replace"))
		i += 1 + lung
	return u"", -1


def raspunsMdns(date):
	"""Raspunsul mDNS -> {"ptr": [(tip, instanta)], "srv": {instanta: (gazda, port)}, "a": {gazda: ip}}."""
	rez = {"ptr": [], "srv": {}, "a": {}}
	try:
		_id, steaguri, qd, an, ns, ar = struct.unpack(">HHHHHH", date[:12])
		if not steaguri & 0x8000:
			return rez
		i = 12
		for _k in range(qd):
			_n, i = _numeDin(date, i)
			if i < 0:
				return rez
			i += 4
		for _k in range(an + ns + ar):
			nume, i = _numeDin(date, i)
			if i < 0 or i + 10 > len(date):
				return rez
			tip, _cls, _ttl, lung = struct.unpack(">HHIH", date[i:i + 10])
			i += 10
			if tip == 12:
				tinta, _j = _numeDin(date, i)
				if tinta:
					rez["ptr"].append((nume.lower(), tinta))
			elif tip == 33 and lung >= 7:
				port = struct.unpack(">H", date[i + 4:i + 6])[0]
				gazda, _j = _numeDin(date, i + 6)
				rez["srv"][nume] = (gazda, port)
			elif tip == 1 and lung == 4:
				rez["a"][nume.lower()] = ".".join(str(b) for b in bytearray(date[i:i + 4]))
			i += lung
	except (struct.error, IndexError):
		pass
	return rez


def serviciiMdns(raspunsuri, ip_sursa=None):
	"""Din raspunsurile mDNS: [{fel, nume, gazda (ip), port}] pentru serviciile de fisiere cunoscute."""
	rez = []
	for r in raspunsuri:
		for tip, instanta in r["ptr"]:
			fel = SERVICII_MDNS.get(tip.rstrip("."))
			if not fel:
				continue
			gazda, port = r["srv"].get(instanta, (u"", 0))
			ip = r["a"].get(gazda.lower()) if gazda else None
			ip = ip or ip_sursa
			if not ip:
				continue
			nume = instanta.split("." + tip.split(".")[0], 1)[0] if tip else instanta
			rez.append({"fel": fel, "nume": nume, "gazda": ip, "port": port})
	return rez
