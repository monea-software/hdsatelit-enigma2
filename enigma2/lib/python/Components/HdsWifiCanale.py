# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsWifiCanale.py: utilitarul "Cat de aglomerat e Wi-Fi-ul" (din 0.4.4), aceeasi logica pe televizor
# (Screens/HdsUnelteRetea.py, HdsWifiCanaleScreen) si in interfata web (HdsWebControl/unelte_retea_web.py, /wifi-canale).
#
# Din rezultatele unei cautari Wi-Fi (fiecare punct de acces auzit, cu frecventa si puterea semnalului) se socoteste,
# pentru canalele 1-13 din banda de 2,4 GHz:
#   - cate retele se aud pe fiecare canal si cat de tare;
#   - cat de incarcat e fiecare canal: o retea apasa pe canalul ei si, din ce in ce mai putin, pe cele 4 canale de o
#     parte si de alta (un canal de 20 MHz are 4 canale vecine care se suprapun cu el): PONDERI. O retea care se aude
#     tare apasa mai mult decat una abia auzita (putere());
#   - canalul cel mai liber de recomandat pentru router, cu o explicatie in cuvinte simple. Canalele 1, 6 si 11 nu se
#     suprapun intre ele, deci sunt alese inainte, daca nu e altul cu mult mai liber; 12 si 13 (permise in Europa) nu
#     se recomanda decat daca sunt cu mult mai libere, fiindca unele telefoane si laptopuri nu le vad.
# Reteaua la care e legat receptorul (si celelalte puncte ale ei: acelasi nume, sau aceeasi adresa fizica in afara de
# ultimul octet, ca reteaua de oaspeti a aceluiasi router) nu se numara: sfatul e unde sa se mute chiar routerul omului.
#
# Cautarea: intai prin wpa_supplicant (wpa_cli scan / scan_results: acelasi proces care face si conectarea, deci nu se
# bat doua cautari pe placa), iar cand supplicantul nu porneste sau nu raspunde, prin "iwlist <placa> scan". Nimic nu
# se trimite in retea in afara cautarii obisnuite a placii (probe request), aceeasi ca la lista retelelor.
#
# Modulul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import re

CANALE = tuple(range(1, 14))
# cat apasa o retea pe un canal aflat la 0, 1, 2, 3, 4 canale de al ei (mai departe: deloc)
PONDERI = (1.0, 0.8, 0.6, 0.4, 0.2)
NESUPRAPUSE = (1, 6, 11)
# cat se adauga la incarcare cand se alege un canal (ca sa castige 1, 6, 11 la o diferenta mica)
ADAOS_SUPRAPUS = 0.35
ADAOS_12_13 = 0.15
# "la fel de liber": diferenta sub care nu merita schimbat canalul routerului
DIFERENTA_MICA = 0.25
PRAG_LIBER = 0.6
PRAG_FOARTE = 1.8
# o incarcare de atat umple bara
INCARCARE_PLINA = 3.0

LIBER = "liber"
AGLOMERAT = "aglomerat"
FOARTE = "foarte_aglomerat"


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


# ---------------------------------------------------------------- frecvente, canale, puteri

def canal(frecventa):
	"""Canalul din banda de 2,4 GHz pentru frecventa in MHz (2412 -> 1 ... 2472 -> 13, 2484 -> 14), altfel None."""
	try:
		f = int(frecventa)
	except (TypeError, ValueError):
		return None
	if f == 2484:
		return 14
	if 2412 <= f <= 2472 and (f - 2407) % 5 == 0:
		return (f - 2407) // 5
	return None


def frecventa_canal(c):
	return 2484 if c == 14 else 2407 + 5 * c


def banda(frecventa):
	try:
		f = int(frecventa)
	except (TypeError, ValueError):
		return ""
	if 2400 <= f < 2500:
		return "2.4"
	if 4900 <= f < 5900:
		return "5"
	if 5925 <= f < 7125:
		return "6"
	return ""


def dbm(semnal):
	"""Puterea in dBm: valorile negative sunt deja dBm; cele pozitive (unele drivere dau procente 0-100) se aduc la o
	valoare apropiata in dBm (100% = -50, 0% = -100), ca regula lui WlanTools.signalPercent intoarsa."""
	if semnal is None:
		return None
	try:
		s = float(semnal)
	except (TypeError, ValueError):
		return None
	if s < 0:
		return int(round(s))
	return int(round(min(100.0, s) / 2.0 - 100.0))


def putere(d):
	"""Cat apasa o retea dupa puterea ei (0,05 .. 1): -45 dBm sau mai tare = 1, -70 dBm = 0,5, -95 dBm = 0,05."""
	if d is None:
		return 0.05
	return max(0.05, min(1.0, (d + 95.0) / 50.0))


def treapta(d):
	"""Treptele semnalului (1..4), aceleasi praguri ca pictograma retelei (HdsStareRetea.treapta_wifi)."""
	if d is None:
		return 0
	if d >= -55:
		return 4
	if d >= -65:
		return 3
	if d >= -75:
		return 2
	return 1


def cuvant_semnal(d):
	return {4: _("foarte bun"), 3: _("bun"), 2: _("slab"), 1: _("foarte slab")}.get(treapta(d), _("necunoscut"))


# ---------------------------------------------------------------- citirea cautarii

def _ssid_wpa(text):
	from Components import WlanTools
	return WlanTools.decodeSsid(text)


def _ssid_bytes(text):
	"""SSID-ul (octeti) din textul cu \\xNN si scapari simple (wpa_cli si iwlist le scriu la fel)."""
	try:
		return _ssid_wpa(text)
	except ImportError:
		pass
	rez = bytearray()
	i = 0
	while i < len(text):
		c = text[i]
		if c == "\\" and i + 1 < len(text):
			n = text[i + 1]
			if n == "x" and re.match(r"[0-9a-fA-F]{2}", text[i + 2:i + 4] or ""):
				rez.append(int(text[i + 2:i + 4], 16))
				i += 4
				continue
			simple = {"\\": 0x5c, "\"": 0x22, "e": 0x1b, "n": 0x0a, "r": 0x0d, "t": 0x09}
			if n in simple:
				rez.append(simple[n])
				i += 2
				continue
		rez.extend(c.encode("utf-8"))
		i += 1
	return bytes(rez)


def _nume(ssid):
	if not ssid or not ssid.strip(b"\0"):
		return ""
	return ssid.decode("utf-8", "replace")


def _punct(bssid, frecventa, semnal, ssid):
	f = None
	try:
		f = int(frecventa)
	except (TypeError, ValueError):
		pass
	d = dbm(semnal)
	return {"bssid": (bssid or "").lower(), "frecventa": f, "canal": canal(f), "banda": banda(f), "dbm": d,
		"treapta": treapta(d), "ssid": ssid, "nume": _nume(ssid), "ascunsa": not _nume(ssid)}


def citeste_scan_results(text):
	"""Fiecare punct de acces din iesirea "wpa_cli scan_results" (bssid, frecventa, semnal, steaguri, ssid), si cele
	ascunse (ocupa si ele canalul). Ad-hoc si mesh se sar."""
	rez = []
	for rand in (text or "").splitlines():
		if not rand or rand.startswith("bssid"):
			continue
		c = rand.split("\t", 4)
		if len(c) != 5:
			continue
		bssid, frecventa, semnal, steaguri, ssid = c
		if "[IBSS]" in steaguri or "[MESH]" in steaguri:
			continue
		try:
			int(frecventa)
			int(semnal)
		except ValueError:
			continue
		rez.append(_punct(bssid, frecventa, int(semnal), _ssid_bytes(ssid)))
	return rez


_CELULA = re.compile(r"Cell\s+\d+\s*-\s*Address:\s*([0-9A-Fa-f:]{17})")
_ESSID = re.compile(r'ESSID:"(.*)"\s*$')
_CANAL = re.compile(r"(?:^|\s)Channel[:=]\s*(\d+)")
_CANAL_PAR = re.compile(r"\(Channel\s+(\d+)\)")
_FRECV = re.compile(r"Frequency[:=]\s*([0-9.]+)\s*(GHz|MHz)?")
_SEMNAL_DBM = re.compile(r"Signal level[:=]\s*(-?\d+)\s*dBm")
_SEMNAL_PROC = re.compile(r"Signal level[:=]\s*(\d+)\s*/\s*(\d+)")
_CALITATE = re.compile(r"Quality[:=]\s*(\d+)\s*/\s*(\d+)")
_MOD = re.compile(r"Mode:\s*(\S+)")


def citeste_iwlist(text):
	"""Fiecare celula din iesirea "iwlist <placa> scan" (wireless-tools). Semnalul: "Signal level=-48 dBm"; cand
	driverul da numai procente ("Signal level=78/100" sau numai "Quality=52/70"), procentul. Ad-hoc se sare."""
	rez = []
	cur = None

	def gata(x):
		if x is None:
			return
		if (x.get("mod") or "").lower() in ("ad-hoc", "mesh"):
			return
		f = x.get("frecventa")
		if f is None and x.get("canal_text") is not None:
			c = x["canal_text"]
			if 1 <= c <= 14:
				f = frecventa_canal(c)
		semnal = x.get("dbm")
		if semnal is None:
			semnal = x.get("procent", x.get("procent_calitate"))
		rez.append(_punct(x["bssid"], f, semnal, x.get("ssid", b"")))

	for rand in (text or "").splitlines():
		m = _CELULA.search(rand)
		if m:
			gata(cur)
			cur = {"bssid": m.group(1)}
			continue
		if cur is None:
			continue
		s = rand.strip()
		m = _ESSID.search(s)
		if m:
			cur["ssid"] = _ssid_bytes(m.group(1))
			continue
		m = _FRECV.search(s)
		if m:
			try:
				v = float(m.group(1))
				cur["frecventa"] = int(round(v * 1000)) if (m.group(2) or "GHz") == "GHz" and v < 100 else int(round(v))
			except ValueError:
				pass
			m2 = _CANAL_PAR.search(s)
			if m2 and "canal_text" not in cur:
				cur["canal_text"] = int(m2.group(1))
			continue
		m = _CANAL.search(s)
		if m:
			cur["canal_text"] = int(m.group(1))
			continue
		m = _MOD.search(s)
		if m:
			cur["mod"] = m.group(1)
		m = _SEMNAL_DBM.search(s)
		if m:
			v = int(m.group(1))
			if v < 0:
				cur["dbm"] = v
		else:
			m = _SEMNAL_PROC.search(s)
			if m and int(m.group(2)) > 0:
				cur["procent"] = 100.0 * int(m.group(1)) / int(m.group(2))
		m = _CALITATE.search(s)
		if m and int(m.group(2)) > 0 and "procent" not in cur:
			cur["procent_calitate"] = 100.0 * int(m.group(1)) / int(m.group(2))
	gata(cur)
	return rez


# ---------------------------------------------------------------- incarcarea canalelor si recomandarea

def _acelasi_router(a, b):
	"""Doua adrese fizice care difera numai in ultimul octet: acelasi router (reteaua de oaspeti, alt SSID)."""
	a = (a or "").lower().split(":")
	b = (b or "").lower().split(":")
	return len(a) == 6 and len(b) == 6 and a[:5] == b[:5]


def ale_mele(puncte, bssid_meu=None, ssid_meu=None):
	"""Punctele care sunt ale retelei omului: chiar cel la care e legat receptorul, celelalte cu acelasi nume si
	celelalte retele ale aceluiasi router."""
	rez = set()
	if not bssid_meu and not ssid_meu:
		return rez
	for i, p in enumerate(puncte):
		if bssid_meu and (p["bssid"] == bssid_meu.lower() or _acelasi_router(p["bssid"], bssid_meu)):
			rez.add(i)
		elif ssid_meu and p["ssid"] and p["ssid"] == ssid_meu:
			rez.add(i)
	return rez


def nivel(incarcare):
	if incarcare < PRAG_LIBER:
		return LIBER
	if incarcare < PRAG_FOARTE:
		return AGLOMERAT
	return FOARTE


def text_nivel(n):
	return {LIBER: _("liber"), AGLOMERAT: _("aglomerat"), FOARTE: _("foarte aglomerat")}.get(n, n)


def incarcari(puncte, mele=()):
	"""{canal: incarcarea} pentru canalele 1-13, din punctele de 2,4 GHz care nu sunt ale omului."""
	rez = dict((c, 0.0) for c in CANALE)
	for i, p in enumerate(puncte):
		if i in mele or p["canal"] is None:
			continue
		for c in CANALE:
			dist = abs(c - p["canal"])
			if dist < len(PONDERI):
				rez[c] += putere(p["dbm"]) * PONDERI[dist]
	return rez


def scor(c, incarcare):
	return incarcare + (0.0 if c in NESUPRAPUSE else ADAOS_SUPRAPUS) + (ADAOS_12_13 if c >= 12 else 0.0)


def recomandat(inc, al_meu=None):
	"""Canalul cu scorul cel mai mic (incarcarea, plus adaosurile pentru canalele care se suprapun cu doua din 1/6/11 si
	pentru 12-13); la egalitate, canalul de acum al routerului omului (nu se cere o schimbare fara folos), apoi cel mai
	mic."""
	cel_mai_bun = min(CANALE, key=lambda c: (round(scor(c, inc[c]), 6), c))
	if al_meu in inc and round(scor(al_meu, inc[al_meu]), 6) <= round(scor(cel_mai_bun, inc[cel_mai_bun]), 6):
		return al_meu
	return cel_mai_bun


def vecine(puncte, c, mele=()):
	"""Cate retele (in afara de ale omului) se aud pe canalul c si pe cele care se suprapun cu el (cel mult 4 de o parte)."""
	return sum(1 for i, p in enumerate(puncte) if i not in mele and p["canal"] is not None and
		abs(p["canal"] - c) < len(PONDERI))


def analiza(puncte, bssid_meu=None, ssid_meu=None, poarta=""):
	"""Tot ce arata ecranul si pagina: canalele 1-13 (retele, incarcare, procentul barei, nivelul), retelele auzite
	(cele mai tari intai), canalul recomandat, canalul routerului omului si explicatia."""
	mele = ale_mele(puncte, bssid_meu, ssid_meu)
	inc = incarcari(puncte, mele)
	al_meu = None
	for i in sorted(mele):
		if puncte[i]["canal"] is not None and (not bssid_meu or puncte[i]["bssid"] == bssid_meu.lower()):
			al_meu = puncte[i]["canal"]
			break
	if al_meu is None:
		for i in sorted(mele):
			if puncte[i]["canal"] is not None:
				al_meu = puncte[i]["canal"]
				break
	rec = recomandat(inc, al_meu)
	canale = []
	for c in CANALE:
		canale.append({"canal": c, "retele": sum(1 for i, p in enumerate(puncte) if i not in mele and p["canal"] == c),
			"incarcare": round(inc[c], 2), "procent": int(round(min(100.0, 100.0 * inc[c] / INCARCARE_PLINA))),
			"nivel": nivel(inc[c]), "nivel_text": text_nivel(nivel(inc[c])), "al_meu": c == al_meu, "recomandat": c == rec})
	retele = []
	for i, p in enumerate(puncte):
		retele.append({"nume": p["nume"] or _("(rețea ascunsă)"), "bssid": p["bssid"], "canal": p["canal"],
			"banda": p["banda"], "dbm": p["dbm"], "treapta": p["treapta"], "semnal": cuvant_semnal(p["dbm"]),
			"a_mea": i in mele})
	retele.sort(key=lambda r: (-(r["dbm"] if r["dbm"] is not None else -999), r["nume"].lower()))
	pe24 = [p for p in puncte if p["canal"] is not None]
	alte = [p for p in puncte if p["canal"] is None]
	return {
		"canale": canale,
		"retele": retele,
		"recomandat": rec,
		"al_meu": al_meu,
		"numar": len(pe24),
		"numar_alte_benzi": len(alte),
		"explicatie": explicatie(puncte, mele, inc, rec, al_meu, poarta),
	}


def explicatie(puncte, mele, inc, rec, al_meu, poarta=""):
	"""Cateva fraze simple: ce canal, de ce, si cum se schimba."""
	fraze = []
	n_rec = vecine(puncte, rec, mele)
	if not [p for i, p in enumerate(puncte) if i not in mele and p["canal"] is not None]:
		fraze.append(_("Receptorul nu găsește nicio altă rețea de 2,4 GHz: orice canal e liber."))
	elif n_rec == 0:
		fraze.append(_("Pe canalul %d și pe cele de lângă el nu e nicio altă rețea.") % rec)
	elif nivel(inc[rec]) == LIBER:
		fraze.append(_("Pe canalul %d și pe cele de lângă el sunt %d rețele, dar cu semnal slab.") % (rec, n_rec))
	else:
		fraze.append(_("Pe canalul %d și pe cele de lângă el sunt %d rețele: e cel mai puțin aglomerat, dar tot nu e liber.")
			% (rec, n_rec))
	if al_meu is not None:
		if al_meu == rec:
			fraze.append(_("Routerul tău e deja pe acest canal. Nu e nevoie de nicio schimbare."))
		elif al_meu in inc and scor(al_meu, inc[al_meu]) - scor(rec, inc[rec]) < DIFERENTA_MICA:
			fraze.append(_("Routerul tău e pe canalul %d, aproape la fel de liber. Schimbarea ar ajuta puțin.") % al_meu)
		elif al_meu in inc:
			fraze.append(_("Routerul tău e pe canalul %d, unde sunt %d rețele vecine. Pe canalul %d ar fi mai puțină înghesuială.")
				% (al_meu, vecine(puncte, al_meu, mele), rec))
		else:
			fraze.append(_("Routerul tău e pe canalul %d. Pe canalul %d ar fi mai puțină înghesuială.") % (al_meu, rec))
	else:
		fraze.append(_("Receptorul nu e legat prin Wi-Fi, deci nu știe care e rețeaua ta: în socoteală intră toate rețelele găsite."))
	if rec in NESUPRAPUSE:
		fraze.append(_("Canalele 1, 6 și 11 nu se suprapun unul cu altul; de aceea sunt alese întâi."))
	else:
		fraze.append(_("Canalele 1, 6 și 11 sunt mai aglomerate aici; canalul %d e totuși mai liber.") % rec)
	if poarta:
		fraze.append(_("Canalul se schimbă din pagina routerului (de obicei http://%s), la setările Wi-Fi de 2,4 GHz.") % poarta)
	else:
		fraze.append(_("Canalul se schimbă din pagina routerului, la setările Wi-Fi de 2,4 GHz."))
	return fraze


# ---------------------------------------------------------------- cautarea (pe firul enigma2, fara sa astepte)

_ultima = [None]


def ultima():
	"""Ultimul rezultat (al televizorului sau al paginii web), sau None."""
	return _ultima[0]


class Cautare(object):
	"""O cautare pe placa `placa`. gata(rezultat) se cheama o data, pe firul enigma2: rezultat = {"stare": "gata",
	"sursa": "wpa_cli" / "iwlist", ...analiza()} sau {"stare": "eroare", "mesaj": ...}. `control`: fabrica WlanControl
	(probele dau una falsa); `poarta`: functia care da adresa routerului (pentru fraza cu pagina routerului)."""

	def __init__(self, placa, gata, control=None, poarta=None, ceas=None):
		if control is None:
			from Components.WlanControl import WlanControl as control
		self.placa = placa
		self.gata_fn = gata
		self.control = control(placa)
		self.poarta = poarta or _poarta_implicita
		self.ceas = ceas
		self.terminata = False
		self.oprita = False

	def porneste(self):
		self.control.ensureSupplicant(self._pornit)

	def opreste(self):
		self.oprita = True
		self.control.stop()

	def _pornit(self, bun):
		if self.oprita:
			return
		if not bun:
			self._iwlist()
			return
		self.control.scan(self._cautat, raw=True)

	def _cautat(self, text):
		if self.oprita:
			return
		if text is None:
			self._iwlist()
			return
		puncte = citeste_scan_results(text)
		self.control.status(lambda st: self._cu_stare(puncte, st, "wpa_cli"))

	def _cu_stare(self, puncte, st, sursa):
		if self.oprita:
			return
		bssid = ssid = None
		if (st or {}).get("wpa_state") == "COMPLETED":
			bssid = st.get("bssid")
			ssid = _ssid_bytes(st.get("ssid", "")) if st.get("ssid") else None
		self._termina(puncte, bssid, ssid, sursa)

	def _iwlist(self):
		def sus(_cod, _iesire):
			if self.oprita:
				return
			self.control.execute(("iwlist", self.placa, "scan"), cautat)

		def cautat(cod, iesire):
			if self.oprita:
				return
			if cod != 0 or "Cell" not in (iesire or ""):
				if cod == 0 and "No scan results" in (iesire or ""):
					self._termina([], None, None, "iwlist")
					return
				self._eroare(_("Căutarea rețelelor n-a reușit. Încearcă din nou."))
				return
			self._termina(citeste_iwlist(iesire), None, None, "iwlist")
		self.control.execute(("ip", "link", "set", self.placa, "up"), sus)

	def _termina(self, puncte, bssid, ssid, sursa):
		if self.terminata:
			return
		self.terminata = True
		try:
			poarta = self.poarta() or ""
		except Exception:
			poarta = ""
		rez = analiza(puncte, bssid, ssid, poarta)
		rez["stare"] = "gata"
		rez["sursa"] = sursa
		rez["placa"] = self.placa
		_ultima[0] = rez
		self.gata_fn(rez)

	def _eroare(self, mesaj):
		if self.terminata:
			return
		self.terminata = True
		self.gata_fn({"stare": "eroare", "mesaj": mesaj, "placa": self.placa})


def _poarta_implicita():
	try:
		from Components import HdsStareRetea
		return HdsStareRetea.legatura().get("poarta") or ""
	except Exception:
		return ""


def placi_wifi(sysfs="/sys/class/net"):
	"""Placile Wi-Fi ale receptorului (dupa WlanTools.getWlanDriver), in ordinea numelui."""
	import os
	try:
		from Components import WlanTools
		nume = sorted(os.listdir(sysfs))
	except (ImportError, OSError):
		return []
	return [n for n in nume if WlanTools.getWlanDriver(n, sysfs) is not None]
