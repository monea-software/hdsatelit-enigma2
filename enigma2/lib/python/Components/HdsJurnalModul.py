# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Cititoarele, clientii si ultimele randuri din jurnal ale modulului de acces care ruleaza, citite din interfata lui web,
pe receptor (127.0.0.1). Doar in imaginea HDSatelit.

Il folosesc ecranul Informații despre decriptare (Screens/CamInfo.py, deschis din OK > Despre decriptare pe modulul
care ruleaza, din INFO si din meniu) si pagina web Acces condiționat (HdsWebControl/acces_conditionat_web.py, ruta
/api/acces-conditionat-jurnal), ca pe televizor sa se vada dintr-o privire, fara navigator, ce arata pagina modulului.

De unde: API-ul interfetei web a modulelor din familia OSCam (OSCam, OSCam-emu, -smod, Retuned: /oscamapi; NCam:
/ncamapi), adica:
  - <api>.json?part=status: clientii modulului; tipul r (cititor local) si p (cititor prin retea) sunt cititoarele,
    tipul c clientii (de pilda dvbapi, legatura receptorului); s, h, m, a, x sunt ale modulului insusi si nu se arata;
  - <api>.html?part=status&appendlog=1: jurnalul tinut in memorie de modul (loghistorylines), in <log><![CDATA[...]]>.
Un modul din alta familie (raspunsul 404 pe ambele) nu da nimic, fara mesaj.

Reguli:
  - numai citire, numai spre 127.0.0.1 (sau ::1), pe portul interfetei aflat de Components/HdsModuleAcces.py din
    configurarea modulului (httpport); nimic trimis in afara receptorului si nimic schimbat in modul;
  - pe reteaua de acasa interfata merge fara parola (asa vin configurarile noastre). Cand totusi cere (401), se
    incearca o data utilizatorul si parola din configurarea modulului (HdsNavigator/intrare_cam.date_intrare, ca la
    navigator); daca nici asa nu merge, citirea se opreste (cine cheama nu mai incearca pana la redeschidere: multe
    incercari gresite inchid interfata, failban);
  - se cheama NUMAI pe un fir separat (cererile au termen); rezultatul e un dictionar simplu;
  - adresele (ip, port) cititoarelor si clientilor nu se pastreaza; nimic din cititoare sau din jurnal nu se scrie in
    jurnalul enigma2 (ajunge in rapoartele testerilor).
Modulul nu importa enigma: probele de pe PC il incarca singur si dau un server HTTP de proba."""
import json
import re
import socket
import ssl

try:
	from urllib.parse import unquote
	from urllib.request import (HTTPBasicAuthHandler, HTTPDigestAuthHandler, HTTPHandler, HTTPPasswordMgrWithDefaultRealm,
		HTTPSHandler, Request, build_opener)
	from urllib.error import HTTPError, URLError
except ImportError:  # Python 2 (numai probe vechi)
	from urllib import unquote
	from urllib2 import (HTTPBasicAuthHandler, HTTPDigestAuthHandler, HTTPHandler, HTTPPasswordMgrWithDefaultRealm,
		HTTPSHandler, Request, build_opener, HTTPError, URLError)

GAZDA = "127.0.0.1"
API = ("oscamapi", "ncamapi")       # in ordinea incercarii; NCam intai cand numele modulului il spune
TERMEN = 3.0                        # secunde pentru o cerere
OCTETI_MAXIM = 512 * 1024           # cat se citeste cel mult dintr-un raspuns
RANDURI_JURNAL = 10                 # ultimele randuri din jurnal aratate
CITITOARE_MAXIM = 32
CLIENTI_MAXIM = 16
TEXT_MAXIM = 80                     # semne intr-un camp aratat (nume, stare, canal)
RAND_MAXIM = 200                    # semne intr-un rand de jurnal aratat
TIPURI_CITITOR = ("r", "p")
TIPURI_CLIENT = ("c",)
# ce scrie modulul in <log> cand nu tine jurnalul in memorie (loghistorylines = 0)
FARA_ISTORIC = "loghistorylines is set to 0"

# erorile intoarse in "eroare"
NU_RASPUNDE = "nu_raspunde"         # conexiune refuzata, termen, raspuns stricat
PAROLA = "parola"                   # 401 si dupa utilizatorul si parola din configurare
FARA_API = "fara_api"               # nu e un modul din familia OSCam (404 pe ambele API-uri)

_LOG = re.compile(r"<log>\s*<!\[CDATA\[(.*?)\]\]>\s*</log>", re.S)
# "2026/11/17 10:15:01 1A2B3C4D p   (reader) text" -> "10:15:01 (reader) text": fara data, fara firul si litera felului,
# ca randul sa incapa pe ecran
_RAND_JURNAL = re.compile(r"^(?:\d{4}/\d\d/\d\d\s+)?(\d\d:\d\d:\d\d)(?:\.\d+)?\s+(?:[0-9A-Fa-f]{8}\s+)?"
	r"(?:[a-zA-Z]\s+(?=\())?(.*)$")
_CONTROL = re.compile(u"[\u0000-\u001f\u007f-\u009f]")


def _scurt(text, maxim=TEXT_MAXIM):
	"""text de aratat: fara caractere de control, fara spatii la capete, cel mult `maxim` semne"""
	if text is None:
		return ""
	if not isinstance(text, str):
		text = str(text)
	text = _CONTROL.sub(" ", text).strip()
	return text if len(text) <= maxim else text[:maxim - 1] + u"\u2026"


def ordine_api(nume=""):
	"""API-urile in ordinea incercarii: NCam intai cand numele modulului contine ncam"""
	if "ncam" in (nume or "").lower():
		return ("ncamapi", "oscamapi")
	return API


class _Raspuns(object):
	__slots__ = ("cod", "date", "motiv")

	def __init__(self, cod, date=b"", motiv=""):
		self.cod, self.date, self.motiv = cod, date, motiv


class _DigestOData(HTTPDigestAuthHandler):
	"""Digest (asa cere OSCam) cu o singura incercare a datelor: urllib ar reincerca de 5 ori datele gresite, iar fiecare
	incercare gresita e numarata de failban-ul modulului"""

	def http_error_auth_reqed(self, auth_header, host, req, headers):
		if self.retried >= 1:
			raise HTTPError(req.full_url, 401, "digest", headers, None)
		return HTTPDigestAuthHandler.http_error_auth_reqed(self, auth_header, host, req, headers)


def cere_http(protocol, port, cale, intrare=None, termen=TERMEN, gazda=GAZDA):
	"""GET <protocol>://<gazda>:<port><cale>. `intrare` = (utilizator, parola) sau None. Intoarce _Raspuns: cod 0 cand nu
	s-a putut vorbi deloc cu interfata (motiv = clasa erorii). Fara certificat verificat: e chiar receptorul."""
	url = "%s://%s:%d%s" % ("https" if protocol == "https" else "http", gazda, int(port), cale)
	manere = []
	if protocol == "https":
		context = ssl.create_default_context()
		context.check_hostname = False
		context.verify_mode = ssl.CERT_NONE
		manere.append(HTTPSHandler(context=context))
	else:
		manere.append(HTTPHandler())
	if intrare:
		parole = HTTPPasswordMgrWithDefaultRealm()
		parole.add_password(None, url, intrare[0], intrare[1])
		manere += [_DigestOData(parole), HTTPBasicAuthHandler(parole)]
	deschizator = build_opener(*manere)
	cerere = Request(url, headers={"Cache-Control": "no-cache", "Connection": "close"})
	try:
		r = deschizator.open(cerere, timeout=termen)
		try:
			return _Raspuns(r.getcode() or 200, r.read(OCTETI_MAXIM + 1)[:OCTETI_MAXIM])
		finally:
			r.close()
	except HTTPError as e:
		try:
			e.close()
		except Exception:
			pass
		return _Raspuns(e.code, b"", "HTTP %d" % e.code)
	except (URLError, socket.error, socket.timeout, ssl.SSLError, ValueError, OSError) as e:
		motiv = getattr(e, "reason", None) or e
		return _Raspuns(0, b"", motiv.__class__.__name__ if not isinstance(motiv, str) else motiv)


def _radacina(date):
	"""obiectul de sub cheia oscam / ncam din raspunsul JSON (sau primul obiect, la alt nume)"""
	if isinstance(date, dict):
		for cheie in ("oscam", "ncam"):
			if isinstance(date.get(cheie), dict):
				return date[cheie]
		for v in date.values():
			if isinstance(v, dict):
				return v
	return {}


def _ecm(text):
	"""timpul de raspuns in ms, ca text, sau "" cand nu e unul (gol, 0, -1, nenumeric)"""
	t = (text or "").strip()
	return t if t.isdigit() and int(t) > 0 else ""


def _hex_nenul(text):
	"""True pentru un numar hexazecimal diferit de 0 (srvid, caid din cererea de acum a clientului)"""
	try:
		return int((text or "0").strip() or "0", 16) != 0
	except ValueError:
		return False


def stare_din_json(text):
	"""(versiune, cititoare, clienti) din <api>.json?part=status. Fiecare: {nume, protocol, stare, canal, ecm}. Arunca
	ValueError la un raspuns care nu e JSON."""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "replace")
	date = json.loads(text.strip().lstrip("(").rstrip(")") if text.strip().startswith("(") else text)
	r = _radacina(date)
	cititoare, clienti = [], []
	for c in (r.get("status") or {}).get("client") or []:
		if not isinstance(c, dict):
			continue
		tip = c.get("type") or ""
		if tip not in TIPURI_CITITOR + TIPURI_CLIENT:
			continue
		cerere = c.get("request") if isinstance(c.get("request"), dict) else {}
		legatura = c.get("connection") if isinstance(c.get("connection"), dict) else {}
		nume = unquote(c.get("rname_enc") or "") if tip in TIPURI_CITITOR else unquote(c.get("name_enc") or "")
		# fara nicio cerere inca (srvid si caid 0000), canalul ("unknown") si timpul nu spun nimic
		are_cerere = _hex_nenul(cerere.get("srvid")) or _hex_nenul(cerere.get("caid"))
		rand = {
			"nume": _scurt(nume or c.get("desc") or ""),
			"protocol": _scurt(c.get("protocol") or ""),
			"stare": _scurt(legatura.get("status") or ""),
			"canal": _scurt(cerere.get("chname") or "") if are_cerere else "",
			"ecm": _ecm(cerere.get("ecmtime")) if are_cerere else "",
		}
		if tip in TIPURI_CITITOR:
			if len(cititoare) < CITITOARE_MAXIM:
				cititoare.append(rand)
		elif len(clienti) < CLIENTI_MAXIM:
			clienti.append(rand)
	return _scurt(r.get("version") or ""), cititoare, clienti


def jurnal_din_xml(text, randuri=RANDURI_JURNAL):
	"""Ultimele `randuri` randuri din <log> al lui <api>.html?part=status&appendlog=1, fara data si fara firul modulului
	in fata (ora ramane). None cand modulul nu tine jurnalul in memorie sau raspunsul nu are <log>."""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "replace")
	m = _LOG.search(text or "")
	if not m:
		return None
	continut = m.group(1)
	if FARA_ISTORIC in continut:
		return None
	rez = []
	for rand in continut.splitlines():
		rand = rand.strip()
		if not rand:
			continue
		p = _RAND_JURNAL.match(rand)
		if p:
			rand = p.group(1) + " " + re.sub(r"\s+", " ", p.group(2).strip())
		rez.append(_scurt(rand, RAND_MAXIM))
	return rez[-randuri:] if randuri else rez


def _date_intrare(port):
	"""utilizatorul si parola interfetei din configurarea modulului (ca la navigator), sau None"""
	try:
		from Plugins.Extensions.HdsNavigator.intrare_cam import date_intrare
	except ImportError:
		return None
	try:
		return date_intrare(port)
	except Exception:
		return None


def interfata_pentru(nume, pid=None, H=None, sistem=None):
	"""{port, protocol, ...} al interfetei web a modulului aratat (numele lui din ecran si procesul care lucreaza), din
	Components/HdsModuleAcces.interfete_web (modulele din lista dupa sufix, cele pornite de alt program dupa nume sau
	pid); altfel din procesul dat (HdsModuleAcces.interfata_modul). None cand nu are. Pe un fir separat."""
	if H is None:
		from Components import HdsModuleAcces as H
	sistem = sistem or H.SistemAcces()
	for i in H.interfete_web(sistem):
		if i.get("sufix") == nume or (pid is not None and not i.get("fel") and i.get("pid") == pid):
			return i
	if pid:
		try:
			return H.interfata_modul(sistem, [int(pid)])
		except (TypeError, ValueError):
			return None
	return None


def citeste(port, protocol="http", nume="", randuri=RANDURI_JURNAL, cere=None, intrare=None, termen=TERMEN):
	"""Starea modulului de pe `port`: {ok, eroare, motiv, api, versiune, cititoare, clienti, jurnal}. jurnal e None cand
	modulul nu-l tine in memorie. `cere` = cere_http (probele dau altul); `intrare(port)` = (utilizator, parola) sau
	None, chemat numai dupa un 401. Se cheama numai pe un fir separat."""
	cere = cere or cere_http
	intrare = _date_intrare if intrare is None else intrare
	rez = {"ok": False, "eroare": "", "motiv": "", "api": "", "versiune": "", "cititoare": [], "clienti": [],
		"jurnal": None}
	date_om = None
	for api in ordine_api(nume):
		r = cere(protocol, port, "/%s.json?part=status" % api, date_om, termen)
		if r.cod == 401 and date_om is None:
			date_om = intrare(port)
			if date_om:
				r = cere(protocol, port, "/%s.json?part=status" % api, date_om, termen)
		if r.cod == 401:
			rez.update(eroare=PAROLA, motiv="HTTP 401")
			return rez
		if r.cod == 0:
			rez.update(eroare=NU_RASPUNDE, motiv=r.motiv)
			return rez
		if r.cod == 404:
			continue
		if r.cod != 200:
			rez.update(eroare=NU_RASPUNDE, motiv="HTTP %d" % r.cod)
			return rez
		try:
			versiune, cititoare, clienti = stare_din_json(r.date)
		except ValueError:
			rez.update(eroare=NU_RASPUNDE, motiv="JSON")
			return rez
		rez.update(ok=True, api=api, versiune=versiune, cititoare=cititoare, clienti=clienti)
		j = cere(protocol, port, "/%s.html?part=status&appendlog=1" % api, date_om, termen)
		if j.cod == 200:
			rez["jurnal"] = jurnal_din_xml(j.date, randuri)
		return rez
	rez.update(eroare=FARA_API)
	return rez


# ---------------------------------------------------------------- textele, aceleasi pe televizor si in web

def randuri_text(rez, _=None):
	"""Randurile de aratat pentru rezultatul lui citeste (fara titlul modulului): cititoarele, clientii si jurnalul, cu
	titlurile lor; [] cand nu e nimic de spus (alt fel de modul). `_` = functia de traducere."""
	_ = _ or (lambda s: s)
	if not rez:
		return []
	if not rez.get("ok"):
		e = rez.get("eroare")
		if e == PAROLA:
			return [_("Interfața web a modulului cere utilizator și parolă, iar cele din setările modulului nu merg.")]
		if e == NU_RASPUNDE:
			return [_("Interfața web a modulului nu răspunde.")]
		return []
	linii = [_("Cititoarele:")]
	linii += ["  " + rand_text(c) for c in rez.get("cititoare") or []] or ["  " + _("Niciunul")]
	if rez.get("clienti"):
		linii.append(_("Clienții:"))
		linii += ["  " + rand_text(c) for c in rez["clienti"]]
	if rez.get("jurnal"):
		linii.append(_("Jurnalul modulului, ultimele rânduri:"))
		linii += ["  " + r for r in rez["jurnal"]]
	return linii


def rand_text(c):
	"""nume: stare (protocol), canal, 245 ms: numai partile care exista"""
	parti = [c.get("stare") or ""]
	if c.get("protocol"):
		parti[0] = (parti[0] + " (%s)" % c["protocol"]).strip()
	if c.get("canal"):
		parti.append(c["canal"])
	if c.get("ecm"):
		parti.append("%s ms" % c["ecm"])
	corp = ", ".join(p for p in parti if p)
	return "%s: %s" % (c.get("nume") or "-", corp) if corp else (c.get("nume") or "-")
