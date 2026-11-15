# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAsistentaFlux.py: operatia "flux" a Asistentei (Components/HdsAsistentaBroker.op_flux). Spune ce flux prinde acum
# tunerul canalului deschis, din tabelele RECEPTIONATE, nu din lista de canale (lamedb): TSID-ul din PAT si SDT, ONID-ul
# din SDT, reteaua (ID si nume) din NIT actual, descriptorul de livrare al transponderului prins (pozitia orbitala,
# frecventa, polarizarea, rata) si primele nume de servicii. Asa echipa afla pe ce satelit e antena fara scanare si fara
# nicio scriere (randul TODO 14.11 19:42, AS26: acolo pozitia s-a dedus din rasterul frecventelor).
#
# Numai citire: trei filtre de sectiune (PAT pe PID 0, SDT actual 0x42 pe PID 0x11, NIT actual 0x40 pe PID 0x10) pe
# demultiplexorul serviciului redat, deschise prin SursaDemux din Components/HdsAnalizaFlux.py (acelasi fel de filtru ca
# eDVBSectionReader). Canalul omului nu se schimba, tunerul nu se muta, nimic nu se scrie pe disc. Filtrele se inchid in
# finally; toata citirea dureaza cel mult TERMEN_S (NIT se repeta cel putin o data la 10 s). Ruleaza pe firul sesiunii
# de asistenta, nu pe firul enigma2: de pe firul enigma2 se ia numai demuxul si referinta (Screens/HdsAsistentaSemn._flux).
#
# "flux POZITIE FRECVENTA POL [RATA]" (TODO 15.11 01:55): acelasi citit pe un tuner LIBER acordat pe transponderul cerut,
# fara sa se schimbe canalul omului (ia_tuner_liber, mai jos; tunerul il ia si il elibereaza Screens/HdsAsistentaSemn).
#
# Partea de sus nu importa nimic din enigma2: probele de pe PC dau o sursa falsa (sectiuni facute de ele).

import re
import time

from Components.HdsAnalizaFlux import SursaDemux, antet, citeste_pat, descriptori, imparte, sectiune, text_dvb, _u16

TERMEN_S = 12.0            # toata citirea; NIT actual vine cel putin o data la 10 s
PAS_MS = 100               # un pas al buclei (poll)
CITIRI_PE_PAS = 64         # citiri pe filtru intr-un pas (driverul poate da o sectiune la o citire)
CITIRE = 65536
MAX_SERVICII = 12          # numele de servicii aratate
MAX_TRANSPORTURI = 400     # transporturile din NIT tinute minte

PID_PAT, PID_NIT, PID_SDT = 0x0000, 0x0010, 0x0011
TID_PAT, TID_NIT, TID_SDT = 0x00, 0x40, 0x42

POLARIZARE = ("H", "V", "L", "R")
MODULATIE_S = ("auto", "QPSK", "8PSK", "16QAM")
MODULATIE_C = {1: "QAM16", 2: "QAM32", 3: "QAM64", 4: "QAM128", 5: "QAM256"}


# ---------------------------------------------------------------- partea curata: descriptorii de livrare

def _bcd(octeti):
	"""Cifrele BCD ale octetilor -> numarul (None la o cifra mai mare de 9)."""
	n = 0
	for b in bytearray(octeti):
		hi, lo = b >> 4, b & 0x0F
		if hi > 9 or lo > 9:
			return None
		n = n * 100 + hi * 10 + lo
	return n


def text_pozitie(zecimi, est=True):
	"""Pozitia orbitala in zecimi de grad -> "19.2E" / "30.0W"."""
	if zecimi is None:
		return "?"
	return "%d.%d%s" % (zecimi // 10, zecimi % 10, "E" if est else "W")


def livrare_satelit(c):
	"""satellite_delivery_system_descriptor (0x43, EN 300 468 6.2.13.2) -> dict sau None."""
	c = bytearray(c or b"")
	if len(c) < 11:
		return None
	f = _bcd(c[0:4])                     # 8 cifre, in 10 kHz (011.72750 GHz -> 01172750)
	poz = _bcd(c[4:6])                   # 4 cifre, in zecimi de grad
	b = c[6]
	est = bool(b & 0x80)
	s2 = bool(b & 0x04)
	sr = _bcd(c[7:11])                   # 7 cifre in primii 28 de biti, in 100 simboluri/s (+ ultima cifra = FEC)
	if sr is not None:
		sr //= 10
	return {"fel": "satelit", "frecventa_mhz": (f / 100.0) if f is not None else None, "pozitie": poz, "est": est,
		"text_pozitie": text_pozitie(poz, est), "polarizare": POLARIZARE[(b >> 5) & 3],
		"sistem": "DVB-S2" if s2 else "DVB-S", "modulatie": MODULATIE_S[b & 3],
		"rata_ks": (sr / 10.0) if sr is not None else None}


def livrare_cablu(c):
	"""cable_delivery_system_descriptor (0x44) -> dict sau None."""
	c = bytearray(c or b"")
	if len(c) < 11:
		return None
	f = _bcd(c[0:4])                     # 8 cifre, in 100 Hz (0312.0000 MHz)
	sr = _bcd(c[7:11])
	if sr is not None:
		sr //= 10
	return {"fel": "cablu", "frecventa_mhz": (f / 10000.0) if f is not None else None,
		"modulatie": MODULATIE_C.get(c[6], "?"), "rata_ks": (sr / 10.0) if sr is not None else None}


def livrare_terestru(c):
	"""terrestrial_delivery_system_descriptor (0x5A) -> dict sau None (frecventa binara, in 10 Hz)."""
	c = bytearray(c or b"")
	if len(c) < 4:
		return None
	f = (c[0] << 24) | (c[1] << 16) | (c[2] << 8) | c[3]
	return {"fel": "terestru", "frecventa_mhz": f / 100000.0}


LIVRARE = {0x43: livrare_satelit, 0x44: livrare_cablu, 0x5A: livrare_terestru}


def text_dvb_curat(b, n=60):
	"""Numele vechi (ASY), pastrat pentru apelanti: acelasi lucru cu HdsAnalizaFlux.text_dvb, care scoate de tot codurile
	de control DVB (0x86/0x87 in mijlocul cuvintelor, 19.2E: "Sky Sport B undesliga") in orice set de caractere. O singura
	functie, nu doua copii (TODO 15.11 01:55)."""
	return text_dvb(b, n)


def citeste_sdt(s):
	"""SDT actual -> {"tsid", "onid", "servicii": {sid: {"nume", "furnizor", "tip"}}}, sau None (ca
	HdsAnalizaFlux.citeste_sdt, cu numele prin text_dvb_curat)."""
	s = sectiune(s)
	if s is None or s[0] not in (0x42, 0x46) or len(s) < 15:
		return None
	servicii = {}
	i, sfarsit = 11, len(s) - 4
	while i + 5 <= sfarsit:
		sid = _u16(s, i)
		n = ((s[i + 3] & 0x0F) << 8) | s[i + 4]
		rec = {"nume": u"", "furnizor": u"", "tip": None}
		for tag, c in descriptori(s, i + 5, min(i + 5 + n, sfarsit)):
			if tag == 0x48 and len(c) >= 2:
				rec["tip"] = c[0]
				np = c[1]
				rec["furnizor"] = text_dvb_curat(c[2:2 + np])
				j = 2 + np
				if j < len(c):
					rec["nume"] = text_dvb_curat(c[j + 1:j + 1 + c[j]])
		servicii[sid] = rec
		i += 5 + n
	return {"tsid": _u16(s, 3), "onid": _u16(s, 8), "servicii": servicii}


def citeste_nit_livrare(s):
	"""NIT actual -> {"retea_id", "nume", "transporturi": [{"tsid", "onid", "livrare"}]}, sau None. Spre deosebire de
	HdsAnalizaFlux.citeste_nit, tine si descriptorul de livrare al fiecarui transport."""
	s = sectiune(s)
	if s is None or s[0] != TID_NIT or len(s) < 16:
		return None
	sfarsit = len(s) - 4
	n = ((s[8] & 0x0F) << 8) | s[9]
	rez = {"retea_id": _u16(s, 3), "nume": u"", "transporturi": []}
	for tag, c in descriptori(s, 10, min(10 + n, sfarsit)):
		if tag == 0x40:
			rez["nume"] = text_dvb_curat(c)
	i = 10 + n
	if i + 2 > sfarsit:
		return rez
	lungime = ((s[i] & 0x0F) << 8) | s[i + 1]
	i += 2
	capat = min(sfarsit, i + lungime)
	while i + 6 <= capat:
		tsid, onid = _u16(s, i), _u16(s, i + 2)
		n = ((s[i + 4] & 0x0F) << 8) | s[i + 5]
		livrare = None
		for tag, c in descriptori(s, i + 6, min(i + 6 + n, capat)):
			f = LIVRARE.get(tag)
			if f is not None and livrare is None:
				livrare = f(c)
		rez["transporturi"].append({"tsid": tsid, "onid": onid, "livrare": livrare})
		i += 6 + n
	return rez


def din_referinta(sref):
	"""Ce spune lista de canale (referinta serviciului): TSID, ONID si pozitia din namespace (satelit), sau felul."""
	parti = (sref or "").split(":")
	rez = {"tsid": None, "onid": None, "ns": None, "text_pozitie": None}
	try:
		rez["tsid"] = int(parti[4], 16)
		rez["onid"] = int(parti[5], 16)
		ns = int(parti[6], 16)
		rez["ns"] = ns
		sus = (ns >> 16) & 0xFFFF
		if sus == 0xFFFF:
			rez["text_pozitie"] = "cablu"
		elif sus == 0xEEEE:
			rez["text_pozitie"] = "terestru"
		elif 0 < sus <= 3600:
			rez["text_pozitie"] = text_pozitie(sus) if sus <= 1800 else text_pozitie(3600 - sus, False)
	except (IndexError, ValueError):
		pass
	return rez


# ---------------------------------------------------------------- transponderul ales, pe un tuner liber
# (TODO 15.11 01:55, flux pe transponder ales) "flux POZITIE FRECVENTA POL [RATA]": acelasi citit, dar pe un tuner LIBER
# acordat pe transponderul cerut, fara sa se schimbe canalul omului. Tunerul se ia ca la scanare si la proba tunerului B
# (eDVBResourceManager.allocateRawChannel: refuza singur tunerele ocupate de canalul deschis, de inregistrari, de
# transmisii si pe cele legate sau dependente de unul ocupat), demuxul cu reserveDemux() al canalului brut. Un tuner cu
# motor se ia numai cand antena lui e deja pe pozitia ceruta (nucleul o stie): op-ul nu misca antena. Fara tuner liber:
# raspuns clar, nimic schimbat. Partea de aici nu atinge enigma2 (alocarea, acordul si celelalte vin ca functii).

POL_TEXT = {"H": 0, "V": 1, "L": 2, "R": 3}   # eDVBFrontendParametersSatellite.Polarisation_*
SISTEM_S, SISTEM_S2 = 0, 1
TOLERANTA_KHZ = 2000                          # satellites.xml si lista pot diferi cu cativa kHz (HdsGasireSemnal)
FARA_INREGISTRARE_S = 60                      # nicio luare de tuner cu o inregistrare programata mai devreme de atat
PAZA_S = TERMEN_S + 20                        # tunerul se elibereaza singur dupa atat, daca sesiunea nu o face
EXEMPLU = "flux 19.2E 11494 H 22000"


def pozitie_din_text(t):
	"""19.2E / 5.0W / 13E -> pozitia bruta in zecimi de grad (0..3599; 5.0W = 3550, ca in nimmanager), sau None."""
	m = re.match(r"^([0-9]{1,3})(?:[.,]([0-9]))?([EeWw])$", (t or "").strip())
	if not m:
		return None
	z = int(m.group(1)) * 10 + int(m.group(2) or 0)
	if z > 1800:
		return None
	if m.group(3) in "Ww":
		z = (3600 - z) % 3600
	return z


def text_pozitie_bruta(poz):
	"""Pozitia bruta (0..3599) -> 19.2E / 5.0W."""
	if poz is None:
		return "?"
	return text_pozitie(poz) if poz <= 1800 else text_pozitie(3600 - poz, False)


def cerere_din_argumente(args):
	"""Argumentele op-ului: [POZITIE, FRECVENTA, POL, RATA], toate optionale in catalog.
	-> (None, "") fara niciunul (canalul deschis, ca pana acum), (cerut, "") sau (None, motivul pentru echipa)."""
	a = [(x or "").strip() for x in (args or [])] + ["", "", "", ""]
	poz_t, f_t, pol_t, sr_t = a[:4]
	if not (poz_t or f_t or pol_t or sr_t):
		return None, ""
	if not (poz_t and f_t and pol_t):
		return None, "(transponderul cere cel putin POZITIE FRECVENTA POL, de pilda: %s)" % EXEMPLU
	poz = pozitie_din_text(poz_t)
	if poz is None:
		return None, "(pozitia %s nu se intelege: scrie-o ca 19.2E sau 5.0W)" % poz_t
	try:
		f = int(f_t)
	except ValueError:
		f = 0
	if not 2000 <= f <= 30000:
		return None, "(frecventa %s nu se intelege: in MHz, de pilda 11494)" % f_t
	pol = POL_TEXT.get(pol_t.upper())
	if pol is None:
		return None, "(polarizarea %s nu se intelege: H, V, L sau R)" % pol_t
	sr = None
	if sr_t:
		try:
			sr = int(sr_t)
		except ValueError:
			sr = 0
		if not 100 <= sr <= 100000:
			return None, "(rata %s nu se intelege: in kS/s, de pilda 27500)" % sr_t
	return {"poz": poz, "text_pozitie": text_pozitie_bruta(poz), "frecventa_mhz": f, "pol": pol_t.upper(),
		"polarisation": pol, "rata_ks": sr}, ""


def text_cerut(cerut):
	return "%s %d MHz %s%s" % (cerut["text_pozitie"], cerut["frecventa_mhz"], cerut["pol"],
		(" %d kS/s" % cerut["rata_ks"]) if cerut.get("rata_ks") else "")


def text_tp(tp):
	"""Transponderul acordat (campurile nucleului) -> text scurt pentru echipa."""
	return "%s MHz %s %s kS/s, %s" % (_num(tp["frequency"] / 1000.0),
		"HVLR"[tp["polarisation"]] if tp.get("polarisation") in (0, 1, 2, 3) else "?", _num(tp["symbol_rate"] / 1000.0),
		"DVB-S2" if tp.get("system") == SISTEM_S2 else "DVB-S")


def alege_transponder(cerut, lista):
	"""Transponderul de acordat: cel din satellites.xml (lista = HdsGasireSemnal.transpondere, cu toti parametrii
	nucleului) cu aceeasi polarizare, frecventa la +-2 MHz si, cand e data, rata la 1 %; cel mai apropiat. Fara el, cu
	RATA data: DVB-S cu FEC automat (DVB-S2 cere FEC-ul adevarat). -> (tp, de_unde) sau (None, motivul)."""
	f = cerut["frecventa_mhz"] * 1000
	sr = cerut["rata_ks"] * 1000 if cerut.get("rata_ks") else None
	gasit, dif_min = None, None
	for e in lista or []:
		t = e.get("tp") or {}
		if t.get("polarisation") != cerut["polarisation"]:
			continue
		dif = abs(int(t.get("frequency", 0)) - f)
		if dif > TOLERANTA_KHZ:
			continue
		if sr is not None and abs(int(t.get("symbol_rate", 0)) - sr) > max(1000, sr // 100):
			continue
		if dif_min is None or dif < dif_min:
			gasit, dif_min = t, dif
	if gasit is not None:
		return dict(gasit), "satellites.xml"
	if sr is None:
		return None, ("(transponderul %s nu e in satellites.xml: da si RATA (kS/s), de pilda: %s)" % (
			text_cerut(cerut), EXEMPLU))
	return ({"frequency": f, "symbol_rate": sr, "polarisation": cerut["polarisation"], "fec": 0, "inversion": 2,
		"orbital_position": cerut["poz"], "system": SISTEM_S, "modulation": 1, "rolloff": 0, "pilot": 2},
		"nu e in satellites.xml: DVB-S cu FEC automat")


def litera(slot):
	return chr(ord("A") + slot) if isinstance(slot, int) and 0 <= slot < 26 else str(slot)


def _primul(x):
	"""Legaturile SWIG intorc uneori (cod, obiect)."""
	if isinstance(x, (tuple, list)):
		return x[-1] if x else None
	return x


def ia_tuner_liber(cerut, tunere, transpondere, aloca, acordeaza, motiv_refuz=None, pozitie_motor=None,
		inregistrare_curand=False):
	"""Pe firul enigma2: un tuner liber, setat pentru pozitia ceruta, acordat pe transponder, cu demuxul luat.
	tunere = HdsGasireSemnal.tunere(); transpondere(poz, s2) = HdsGasireSemnal.transpondere; aloca(slot) = canalul brut
	sau None (ocupat); acordeaza(frontend, tp) = codul nucleului; pozitie_motor(slot) = unde e antena tunerului cu motor
	(None / -1 = nestiut). -> (rezultat, canal): rezultat {"demux", "slot", "litera", "tuner", "tp", "de_unde", "ales"}
	sau {"eroare": text}; canal = referinta care tine tunerul (None la eroare: nimic tinut)."""
	poz, unde = cerut["poz"], cerut["text_pozitie"]
	if inregistrare_curand:
		return {"eroare": "(o inregistrare programata incepe in mai putin de %d s: tunerul nu se ia acum)" %
			FARA_INREGISTRARE_S}, None
	setati = [t for t in tunere or [] if any(s.get("poz") == poz for s in t.get("sateliti") or [])]
	if not setati:
		return {"eroare": "(niciun tuner nu e setat pentru %s (Meniu > Setari tuner): fluxul nu se poate citi)" % unde}, None
	lista, _sarite = transpondere(poz, any(t.get("s2") for t in setati))
	tp, de_unde = alege_transponder(cerut, lista)
	if tp is None:
		return {"eroare": de_unde}, None
	if motiv_refuz is not None:
		m = motiv_refuz(tp)
		if m:
			return {"eroare": "(transponderul %s nu se poate acorda: %s)" % (text_tp(tp), m)}, None
	ocupate, motor, fara_s2 = [], [], []
	for t in sorted(setati, key=lambda x: bool(x.get("motor"))):
		slot = t["slot"]
		if tp["system"] == SISTEM_S2 and not t.get("s2"):
			fara_s2.append(litera(slot))
			continue
		if t.get("motor"):
			acum = pozitie_motor(slot) if pozitie_motor is not None else None
			if acum != poz:
				motor.append("%s (antena pe %s)" % (litera(slot), text_pozitie_bruta(acum) if isinstance(acum, int) and
					0 <= acum < 3600 else "nestiut"))
				continue
		canal = _primul(aloca(slot))
		if not canal:
			ocupate.append(litera(slot))
			continue
		fe = _primul(canal.getFrontend())
		if not fe:
			ocupate.append(litera(slot))
			continue
		cod = acordeaza(fe, tp)
		if cod != 0:
			return {"eroare": "(nucleul a refuzat acordul pe tunerul %s, codul %s: %s)" % (litera(slot), cod,
				text_tp(tp))}, None
		demux = _primul(canal.reserveDemux())
		if not isinstance(demux, int) or demux < 0:
			return {"eroare": "(tunerul %s e acordat, dar nu s-a putut lua un demux)" % litera(slot)}, None
		return {"demux": demux, "slot": slot, "litera": litera(slot), "tuner": t.get("nume") or "", "tp": tp,
			"de_unde": de_unde, "ales": cerut, "ref": None}, canal
	parti = []
	if ocupate:
		parti.append("ocupat: %s (canalul deschis, o inregistrare sau o transmisie)" % ", ".join(ocupate))
	if motor:
		parti.append("cu motor, pe alta pozitie: %s (op-ul nu misca antena)" % ", ".join(motor))
	if fara_s2:
		parti.append("fara DVB-S2: %s" % ", ".join(fara_s2))
	return {"eroare": "(niciun tuner liber pentru %s; %s. Canalul omului nu s-a schimbat.)" % (
		text_cerut(cerut), "; ".join(parti))}, None


# ---------------------------------------------------------------- strangerea sectiunilor

class Tabel(object):
	"""Sectiunile unui tabel (toate numerele de sectiune ale aceleiasi versiuni, cu acelasi table_id_extension)."""

	def __init__(self, tid):
		self.tid = tid
		self.ext = None
		self.versiune = None
		self.ultima = None
		self.sectiuni = {}

	def primeste(self, s):
		s = sectiune(s)
		if s is None or s[0] != self.tid or len(s) < 12:
			return
		tid, ext, ver, nr, ultima = antet(s)
		if self.ext is None:
			self.ext = ext
		elif ext != self.ext:
			return
		if self.versiune is not None and ver != self.versiune:
			self.sectiuni = {}
		self.versiune, self.ultima = ver, ultima
		self.sectiuni[nr] = s

	def gata(self):
		return self.ultima is not None and len(self.sectiuni) >= self.ultima + 1

	def lista(self):
		return [self.sectiuni[k] for k in sorted(self.sectiuni)]


def citeste(sursa, termen=TERMEN_S, ceas=None):
	"""Citeste PAT, SDT actual si NIT actual prin `sursa` (SursaDemux sau una falsa), cel mult `termen` secunde.
	-> {"pat", "sdt", "nit", "secunde", "erori"} (tabelele neprimite raman None)."""
	ceas = ceas or _monoton
	tabele = {PID_PAT: Tabel(TID_PAT), PID_SDT: Tabel(TID_SDT), PID_NIT: Tabel(TID_NIT)}
	tid = {PID_PAT: TID_PAT, PID_SDT: TID_SDT, PID_NIT: TID_NIT}
	deschise, resturi, erori = {}, {}, []
	pornit = ceas()
	try:
		for pid in (PID_PAT, PID_SDT, PID_NIT):
			try:
				fd = sursa.sectiuni(pid, tid[pid])
				deschise[fd] = pid
				resturi[fd] = b""
			except Exception as e:
				erori.append("filtrul PID 0x%04X: %s" % (pid, _eroare(e)))
		while deschise and ceas() - pornit < termen:
			for fd in sursa.asteapta(list(deschise), PAS_MS):
				pid = deschise.get(fd)
				if pid is None:
					continue
				for _i in range(CITIRI_PE_PAS):
					try:
						buf = sursa.citeste(fd, CITIRE)
					except Exception as e:
						erori.append("citirea PID 0x%04X: %s" % (pid, _eroare(e)))
						buf = None
					if not buf:
						break
					bucati, resturi[fd] = imparte(buf, resturi[fd])
					for s in bucati:
						tabele[pid].primeste(s)
				if tabele[pid].gata():
					sursa.inchide(fd)
					del deschise[fd]
	finally:
		for fd in list(deschise):
			sursa.inchide(fd)
	rez = {"pat": None, "sdt": None, "nit": None, "secunde": round(ceas() - pornit, 1), "erori": erori}
	t = tabele[PID_PAT]
	if t.sectiuni:
		rez["pat"] = citeste_pat(t.lista()[0])
	t = tabele[PID_SDT]
	if t.sectiuni:
		sdt = None
		for s in t.lista():
			d = citeste_sdt(s)
			if d is None:
				continue
			if sdt is None:
				sdt = d
			else:
				sdt["servicii"].update(d["servicii"])
		if sdt is not None:
			sdt["intreg"] = t.gata()
		rez["sdt"] = sdt
	t = tabele[PID_NIT]
	if t.sectiuni:
		nit = None
		for s in t.lista():
			d = citeste_nit_livrare(s)
			if d is None:
				continue
			if nit is None:
				nit = d
			else:
				nit["transporturi"].extend(d["transporturi"])
				if not nit["nume"]:
					nit["nume"] = d["nume"]
		if nit is not None:
			nit["transporturi"] = nit["transporturi"][:MAX_TRANSPORTURI]
			nit["intreg"] = t.gata()
		rez["nit"] = nit
	return rez


def _monoton():
	try:
		return time.monotonic()
	except AttributeError:
		return time.time()


def _eroare(e):
	return "%s %s" % (type(e).__name__, getattr(e, "strerror", None) or e)


# ---------------------------------------------------------------- textul pentru echipa

def _hexa(n):
	return "0x%04X (%d)" % (n, n) if n is not None else "?"


def _text_livrare(l):
	if not l:
		return "(fara descriptor de livrare)"
	if l["fel"] == "satelit":
		return "%s, %s MHz %s, %s %s, %s kS/s" % (l["text_pozitie"], _num(l["frecventa_mhz"]), l["polarizare"],
			l["sistem"], l["modulatie"], _num(l["rata_ks"]))
	if l["fel"] == "cablu":
		return "cablu, %s MHz, %s, %s kS/s" % (_num(l["frecventa_mhz"]), l["modulatie"], _num(l["rata_ks"]))
	return "terestru, %s MHz" % _num(l["frecventa_mhz"])


def _num(x):
	if x is None:
		return "?"
	return ("%.3f" % x).rstrip("0").rstrip(".")


def text(rez, param):
	"""Raspunsul operatiei: ce s-a primit din flux, apoi concluzia (pozitia antenei) si nepotrivirile cu lista."""
	ales = param.get("ales")
	lista = din_referinta(None if ales else param.get("ref"))
	if ales:
		# transponderul cerut de echipa, pe un tuner liber: "lista" e ce s-a cerut (pozitia), nu canalul deschis
		lista["text_pozitie"] = ales.get("text_pozitie")
	pat, sdt, nit = rez.get("pat"), rez.get("sdt"), rez.get("nit")
	if ales:
		r = ["Fluxul de pe transponderul cerut, pe tunerul liber %s (canalul omului neschimbat; citit din demux %s in %s s):"
			% (param.get("litera"), param.get("demux"), rez.get("secunde"))]
		r.append("Cerut: %s; acordat: %s, %s (%s)" % (text_cerut(ales), ales.get("text_pozitie"), text_tp(param["tp"]),
			param.get("de_unde")) if param.get("tp") else "Cerut: %s" % text_cerut(ales))
	else:
		r = ["Fluxul prins acum pe tunerul canalului deschis (citit din demux %s in %s s; nu din lista de canale):" % (
			param.get("demux"), rez.get("secunde"))]
	if param.get("canal"):
		r.append("Canal: %s" % param.get("canal"))
	if param.get("din_cale"):
		r.append("ATENTIE: canalul deschis e o inregistrare sau un flux TS din retea: tabelele sunt ale lui, nu ale antenei.")
	if not ales:
		r.append("Lista de canale spune: TSID %s, ONID %s, pozitia %s" % (_hexa(lista["tsid"]), _hexa(lista["onid"]),
			lista["text_pozitie"] or "?"))
	tsid = onid = None
	if pat:
		tsid = pat["tsid"]
		r.append("PAT: TSID %s, %d programe%s" % (_hexa(pat["tsid"]), len(pat["programe"]),
			", NIT pe PID 0x%04X" % pat["nit"] if pat.get("nit") is not None else ""))
	elif ales:
		r.append("PAT: neprimit (tunerul %s nu prinde transponderul cerut: antena, comutatorul DiSEqC, LNB-ul sau "
			"transponderul oprit)" % param.get("litera"))
	else:
		r.append("PAT: neprimit (tunerul nu are semnal sau demuxul nu primeste nimic)")
	if sdt:
		tsid = sdt["tsid"] if tsid is None else tsid
		onid = sdt["onid"]
		nume = [x["nume"] for _sid, x in sorted(sdt["servicii"].items()) if x.get("nume")]
		furnizori = sorted(set(x["furnizor"] for x in sdt["servicii"].values() if x.get("furnizor")))
		r.append("SDT actual: TSID %s, ONID %s, %d servicii%s" % (_hexa(sdt["tsid"]), _hexa(sdt["onid"]),
			len(sdt["servicii"]), "" if sdt.get("intreg") else " (nu toate sectiunile)"))
		if nume:
			r.append("  servicii: " + ", ".join(nume[:MAX_SERVICII]) + (" ..." if len(nume) > MAX_SERVICII else ""))
		if furnizori:
			r.append("  furnizori: " + ", ".join(furnizori[:6]))
	else:
		r.append("SDT actual: neprimit")
	al_nostru = None
	pozitii = {}
	if nit:
		for t in nit["transporturi"]:
			l = t.get("livrare")
			if l and l["fel"] == "satelit":
				pozitii[l["text_pozitie"]] = pozitii.get(l["text_pozitie"], 0) + 1
			if t["tsid"] == tsid and (onid is None or t["onid"] == onid):
				al_nostru = t
		r.append("NIT actual: reteaua %s \"%s\", %d transporturi%s" % (_hexa(nit["retea_id"]), nit["nume"],
			len(nit["transporturi"]), "" if nit.get("intreg") else " (nu toate sectiunile)"))
		if pozitii:
			r.append("  pozitiile din descriptorii de livrare: " + ", ".join(
				"%s (%d)" % (p, n) for p, n in sorted(pozitii.items(), key=lambda x: -x[1])))
		r.append("  transportul prins in NIT: " + (_text_livrare(al_nostru.get("livrare")) if al_nostru else
			"(TSID-ul prins nu e in NIT actual)"))
	else:
		r.append("NIT actual: neprimit in %s s (unele fluxuri nu-l trimit pe fiecare transponder)" % rez.get("secunde"))
	# concluzia
	poz = None
	l = al_nostru.get("livrare") if al_nostru else None
	if l and l["fel"] == "satelit":
		poz = l["text_pozitie"]
		r.append("Concluzie: antena e pe %s (descriptorul de livrare al transponderului prins, din NIT)." % poz)
	elif len(pozitii) == 1:
		poz = list(pozitii)[0]
		r.append("Concluzie: probabil %s (NIT anunta numai aceasta pozitie, dar fara transponderul prins)." % poz)
	elif l:
		r.append("Concluzie: transponderul prins e pe %s." % _text_livrare(l))
	else:
		r.append("Concluzie: pozitia nu se poate spune din flux; raman TSID/ONID si numele serviciilor de mai sus.")
	nepotriviri = []
	if lista["tsid"] is not None and tsid is not None and lista["tsid"] != tsid:
		nepotriviri.append("TSID: lista %s, fluxul %s" % (_hexa(lista["tsid"]), _hexa(tsid)))
	if lista["onid"] is not None and onid is not None and lista["onid"] != onid:
		nepotriviri.append("ONID: lista %s, fluxul %s" % (_hexa(lista["onid"]), _hexa(onid)))
	if poz and lista["text_pozitie"] and lista["text_pozitie"] not in ("cablu", "terestru") and poz != lista["text_pozitie"]:
		nepotriviri.append("pozitia: %s %s, fluxul %s" % ("cerut" if ales else "lista", lista["text_pozitie"], poz))
	if ales and l and l["fel"] == "satelit":
		# transportul prins e descris in NIT cu alta frecventa sau polarizare: alt transponder decat cel cerut
		# (comutatorul DiSEqC, alt satelit, LNB-ul sau tonul de 22 kHz)
		if l.get("frecventa_mhz") is not None and abs(l["frecventa_mhz"] - ales["frecventa_mhz"]) > TOLERANTA_KHZ / 1000.0:
			nepotriviri.append("frecventa: cerut %d MHz, NIT spune %s MHz" % (ales["frecventa_mhz"], _num(l["frecventa_mhz"])))
		if l.get("polarizare") in ("H", "V") and ales.get("pol") in ("H", "V") and l["polarizare"] != ales["pol"]:
			nepotriviri.append("polarizarea: cerut %s, NIT spune %s" % (ales["pol"], l["polarizare"]))
	if nepotriviri:
		r.append(("NEPOTRIVIRE cu transponderul cerut: " if ales else "NEPOTRIVIRE cu lista de canale: ") +
			"; ".join(nepotriviri))
	for e in rez.get("erori") or []:
		r.append("(eroare: %s)" % e)
	return "\n".join(r)


def citesteText(param, sursa=None, termen=TERMEN_S, ceas=None):
	"""Operatia "flux" cu parametrii serviciului (HdsAnalizaFlux.parametri) sau ai tunerului liber acordat pe
	transponderul cerut (ia_tuner_liber: "ales", "demux", "litera", "tp"). -> (cod, text)."""
	if not param or not (param.get("ref") or param.get("ales")):
		return 1, "(niciun canal deschis: receptorul e in standby sau nu reda nimic)"
	if param.get("demux") is None:
		return 1, ("(canalul deschis nu vine de pe tuner (televiziune prin internet, fisier) sau demuxul nu se stie: "
			"fluxul nu se poate citi)")
	if sursa is None:
		try:
			sursa = SursaDemux(param["demux"])
		except Exception as e:
			return 1, "(demuxul %s nu se poate deschide: %s)" % (param.get("demux"), _eroare(e))
	rez = citeste(sursa, termen=termen, ceas=ceas)
	cod = 0 if (rez.get("pat") or rez.get("sdt") or rez.get("nit")) else 1
	return cod, text(rez, param)
