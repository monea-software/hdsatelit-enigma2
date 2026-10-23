# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsScanareUltima.py - rezultatul ultimei scanari de servicii: ce transpondere s-au incercat (cu semnal sau fara) si
# TOATE serviciile citite din SDT pe ele, vechi si noi. Il da ruta GET /api/scanare-ultima a interfetei web
# (Plugins/Extensions/HdsWebControl/scanare_web.py).
#
# De ce: lamedb pastreaza si serviciile care nu mai sunt transmise, deci din el nu se vede ce a gasit o scanare. Nucleul
# (eDVBScan, prin eComponentScan.getFoundServices si getScannedTransponders) tine lista completa a scanarii de acum;
# Components/ServiceScan.py o copiaza aici la sfarsitul fiecarei treceri si la oprire. Lista de canale si lamedb nu se
# ating de aici.
#
# Cine trece pe aici: orice scanare deschisa in Screens/ServiceScan.py (dupa satelit, manuala, dupa operator, mai multi
# sateliti, cablu, terestru, din telecomanda sau din web prin /api/scanare-porneste). Scanarea detaliata (canal cu
# canal, Components/HdsCulegereTotala.py) si scanarea DAB+ / DVB-T2 prin satelit nu citesc SDT-ul prin nucleu, deci nu
# schimba rezultatul de aici.
#
# Felul inregistrarii:
#   - o scanare noua inlocuieste inregistrarea de dinainte chiar de la pornire ("stare": "in_curs"); dupa fiecare
#     trecere terminata se adauga transponderele si serviciile ei; la sfarsit "stare": "terminata" (sau "oprita",
#     daca s-a inchis inainte de capat, cu ce se citise pana atunci);
#   - "fel" vine din lista de scanare ("hds_fel", pus de ecranele HD Satelit si de web: "satelit/automat"); fara el,
#     felul receptiei ("satelit", "cablu", "terestru");
#   - orele sunt locale, ISO, fara fus ("2026-01-31T21:05:09"), dupa ceasul receptorului.
#
# Reteaua (din tabela NIT, numai la scanarile cu cautare in retea: cablu dupa operator, automat si toata banda;
# satelit si terestru cu cautarea in retea pornita): cheile de mai jos apar NUMAI cand au valoare, deci cheile vechi
# si raspunsul unui nucleu fara NIT raman exact ca inainte.
#   - in "transpondere": "tsid", "onid" (din SDT, ca in "tp"; la transponderele fara semnal, din NIT), "nid" (ID-ul
#     retelei din NIT-ul citit pe acel transponder), "mod" la cablu ("QAM64", "QAM256", "auto"...);
#   - in "servicii": "lcn" si "lcn_vizibil" (numarul logic al canalului din NIT, dupa sid, tsid si onid);
#     "lcn_vizibil" lipseste cand descriptorul ales nu are semn de vizibilitate (0x86 sub PDS 0x1A0);
#   - "retele": [{"nid", "nume", "pds": [private_data_specifier], "multiplexuri": [{"tsid", "onid", "sistem",
#     "f_khz", ...}], "lcn": [{"tsid", "onid", "sid", "lcn", "vizibil", "tag", "pds"}], "privati": [{"tag", "pds",
#     "hex"}]}]: tot ce a anuntat reteaua, si frecventele neacordate (lib/dvb/hdsretea.h). In "lcn", "vizibil"
#     lipseste la fel, la randurile din 0x86; un 0x86 citit ca numere nu mai apare in "privati".
#
# Pastrare: in memorie si in /tmp/hds-scanare-ultima.json (RAM): ramane dupa o repornire a interfetei (paznicul o
# reporneste uneori noaptea, intre o scanare si citirea ei), dispare la repornirea receptorului si nu scrie in memoria
# flash (dupa o scanare a unui satelit intreg fisierul are sute de KB). Se tine raspunsul gata facut (octeti), ca ruta
# sa nu refaca JSON-ul la fiecare cerere pe firul enigma2. Scris in .nou si apoi os.replace.
# La import nu se atinge nimic din enigma.
import json
import os
import time

FISIER = "/tmp/hds-scanare-ultima.json"

SISTEM_SATELIT, SISTEM_CABLU, SISTEM_TERESTRU = 0, 1, 2      # iDVBFrontend.feSatellite / feCable / feTerrestrial
POLARIZARI = {0: "H", 1: "V", 2: "L", 3: "R"}                 # eDVBFrontendParametersSatellite.Polarisation_*
SCAN_ONLY_FREE = 64                                            # eComponentScan.scanOnlyFree
SISTEME = {SISTEM_SATELIT: "satelit", SISTEM_CABLU: "cablu", SISTEM_TERESTRU: "terestru"}
# modulatia cablului in nucleu (eDVBFrontendParametersCable.Modulation_*); in descriptorul NIT 0 = nedefinit
MOD_CABLU = {0: "auto", 1: "QAM16", 2: "QAM32", 3: "QAM64", 4: "QAM128", 5: "QAM256"}
MOD_SATELIT = {0: "auto", 1: "QPSK", 2: "8PSK", 3: "16QAM"}  # modulation_type din descriptorul 0x43
# FEC_inner din descriptorii de livrare (EN 300 468, tabelele 35 si 39); 15 = fara codare convolutionala
FEC = {1: "1/2", 2: "2/3", 3: "3/4", 4: "5/6", 5: "7/8", 6: "8/9", 7: "3/5", 8: "4/5", 9: "9/10", 15: "fara"}
# cand acelasi serviciu are mai multe numere: HD simulcast (0x88), NorDig v2 (0x87), 0x83, apoi 0x86 (PDS 0x1A0)
PRIORITATE_LCN = {0x88: 0, 0x87: 1, 0x83: 2, 0x86: 3}

_STARE = {"octeti": None, "citit_fisier": False}


def _jurnal(text):
	print("[HdsScanareUltima] %s" % text)


def ora(secunde=None):
	"""Ora locala ISO, la secunda, fara fus: 2026-01-31T21:05:09."""
	return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() if secunde is None else secunde))


def _int(v, implicit=0):
	try:
		return int(v)
	except (TypeError, ValueError):
		return implicit


def transponder(t):
	"""Un rand din getScannedTransponders (nucleul) -> forma rutei:
	{"tp": "ns:tsid:onid" | None, "poz": pozitia orbitala | None, "f_khz", "pol": "H"/"V"/"L"/"R" | None,
	"sr": mii de simboluri pe secunda | None, "semnal": acordat sau nu}. Frecventa: satelitul si cablul vin in kHz,
	terestrul in Hz. "tp" lipseste (None) cand transponderul n-a dat tabele (fara semnal sau fara PAT/SDT).
	Nucleul cu NIT da inca patru campuri (tsid si onid din NIT, nid, modulatia cablului): din ele "tsid", "onid",
	"nid" si "mod", numai cand se stiu."""
	t = tuple(t)
	sistem, poz, frecventa, pol, sr, acordat, are_id, ns, tsid, onid = t[:10]
	sistem = _int(sistem, -1)
	frecventa = _int(frecventa)
	rez = {"tp": ("%x:%x:%x" % (_int(ns) & 0xFFFFFFFF, _int(tsid), _int(onid))) if are_id else None,
		"poz": None, "f_khz": frecventa, "pol": None, "sr": None, "semnal": bool(acordat)}
	if sistem == SISTEM_SATELIT:
		rez.update(poz=_int(poz), pol=POLARIZARI.get(_int(pol, -1)), sr=_int(sr) // 1000)
	elif sistem == SISTEM_CABLU:
		rez["sr"] = _int(sr) // 1000
	elif sistem == SISTEM_TERESTRU:
		rez["f_khz"] = frecventa // 1000
	if len(t) >= 14:
		nit_tsid, nit_onid, nid, mod = (_int(x, -1) for x in t[10:14])
		if are_id:
			rez.update(tsid=_int(tsid), onid=_int(onid))
		elif nit_tsid >= 0 and nit_onid >= 0:
			rez.update(tsid=nit_tsid, onid=nit_onid)
		if nid >= 0:
			rez["nid"] = nid
		if sistem == SISTEM_CABLU and mod in MOD_CABLU:
			rez["mod"] = MOD_CABLU[mod]
	return rez


def serviciu(s):
	"""Un rand din getFoundServices (nucleul) -> (din SDT?, forma rutei: {"cheie": "sid:ns:tsid:onid", "tip": tipul
	din SDT, "nume", "furnizor", "caid": [CAID-urile din descriptorul CA identifier al SDT-ului, fara dubluri, in
	ordine crescatoare]})."""
	sid, ns, tsid, onid, tip, nume, furnizor, caid, din_sdt = tuple(s)[:9]
	caiduri = sorted(set(_int(c) for c in (caid or [])))
	return bool(din_sdt), {"cheie": "%x:%x:%x:%x" % (_int(sid), _int(ns) & 0xFFFFFFFF, _int(tsid), _int(onid)),
		"tip": _int(tip), "nume": nume if isinstance(nume, str) else str(nume or ""),
		"furnizor": furnizor if isinstance(furnizor, str) else str(furnizor or ""), "caid": caiduri}


def _mux(m):
	"""Un multiplex anuntat in NIT (nucleul: tsid, onid, sistem, kHz, mii de simboluri, modulatia, fec, pozitia,
	polarizarea, S2) -> {"tsid", "onid", "sistem": "cablu" | "satelit" | "terestru", "f_khz", si dupa sistem: "sr",
	"mod", "fec", la satelit si "poz", "pol", "s2"}."""
	tsid, onid, sistem, f_khz, sr, mod, fec, poz, pol, s2 = (_int(x, -1) for x in tuple(m)[:10])
	rez = {"tsid": tsid, "onid": onid, "sistem": SISTEME.get(sistem, "necunoscut"), "f_khz": f_khz}
	if sistem == SISTEM_CABLU:
		rez["sr"] = sr
		if mod in MOD_CABLU and mod:
			rez["mod"] = MOD_CABLU[mod]
	elif sistem == SISTEM_SATELIT:
		rez.update(sr=sr, poz=poz, pol=POLARIZARI.get(pol), s2=s2 == 1)
		if mod in MOD_SATELIT:
			rez["mod"] = MOD_SATELIT[mod]
	if sistem in (SISTEM_CABLU, SISTEM_SATELIT) and fec in FEC:
		rez["fec"] = FEC[fec]
	return rez


def _lcn(n):
	"""Un numar logic din NIT (tsid, onid, sid, numarul, vizibil, tag, pds, lista) -> dictionar; "lista" (0x87) numai
	cand exista. vizibil: 1 / 0 (sau True / False), -1 cand descriptorul nu are semnul (0x86): atunci "vizibil"
	lipseste, nu se pune o valoare inventata."""
	t = tuple(n)
	tsid, onid, sid, numar = (_int(x) for x in t[:4])
	vizibil = _int(t[4], -1)
	rez = {"tsid": tsid, "onid": onid, "sid": sid, "lcn": numar}
	if vizibil >= 0:
		rez["vizibil"] = vizibil != 0
	rez.update(tag=_int(t[5]), pds=_int(t[6]))
	if _int(t[7], -1) >= 0:
		rez["lista"] = _int(t[7])
	return rez


def _privat(b):
	"""Un descriptor privat pastrat brut (tsid, onid, tag, pds, octeti) -> {"tag", "pds", "hex"}, cu "tsid" si "onid"
	cand e din bucla unui multiplex (fara ele: din bucla retelei)."""
	tsid, onid, tag, pds, octeti = tuple(b)[:5]
	if isinstance(octeti, str):
		octeti = octeti.encode("latin-1", "replace")
	rez = {"tag": _int(tag), "pds": _int(pds), "hex": bytes(bytearray(octeti or b"")).hex()}
	if _int(tsid, -1) >= 0:
		rez = dict(tsid=_int(tsid), onid=_int(onid), **rez)
	return rez


def retea(r):
	"""O retea din getNetworks (nucleul) -> {"nid", "nume", "pds", "multiplexuri", "lcn", "privati"} (+ "trunchiat":
	true cand nucleul a lasat ceva peste plafon)."""
	nid, nume, pds, muxuri, numere, privati, trunchiat = tuple(r)[:7]
	rez = {"nid": _int(nid), "nume": nume if isinstance(nume, str) else str(nume or ""),
		"pds": sorted(set(_int(x) for x in (pds or []))), "multiplexuri": [], "lcn": [], "privati": []}
	for cheie, lista, functie in (("multiplexuri", muxuri, _mux), ("lcn", numere, _lcn), ("privati", privati, _privat)):
		for x in lista or []:
			try:
				rez[cheie].append(functie(x))
			except Exception as e:
				_jurnal("%s: rand sarit: %r" % (cheie, e))
	if trunchiat:
		rez["trunchiat"] = True
	return rez


def _unesteRetele(liste):
	"""Retelele tuturor trecerilor, unite dupa nid (doua tunere pot citi aceeasi retea), fara randuri dublate."""
	rez, dupa_nid = [], {}
	for lista in liste:
		for r in lista:
			tinta = dupa_nid.get(r["nid"])
			if tinta is None:
				tinta = {"nid": r["nid"], "nume": r["nume"], "pds": [], "multiplexuri": [], "lcn": [], "privati": []}
				dupa_nid[r["nid"]] = tinta
				tinta["_vazute"] = set()
				rez.append(tinta)
			if not tinta["nume"] and r["nume"]:
				tinta["nume"] = r["nume"]
			tinta["pds"] = sorted(set(tinta["pds"]) | set(r["pds"]))
			for cheie in ("multiplexuri", "lcn", "privati"):
				for x in r.get(cheie, []):
					semn = (cheie,) + tuple(sorted(x.items()))
					if semn not in tinta["_vazute"]:
						tinta["_vazute"].add(semn)
						tinta[cheie].append(x)
			if r.get("trunchiat"):
				tinta["trunchiat"] = True
	for r in rez:
		del r["_vazute"]
	return rez


def _numere(retele):
	"""(sid, tsid, onid) -> (numarul, vizibil sau None): numarul ales dupa PRIORITATE_LCN, la egalitate primul citit;
	None cand descriptorul ales nu are semn de vizibilitate."""
	ales = {}
	for r in retele:
		for n in r["lcn"]:
			cheie = (n["sid"], n["tsid"], n["onid"])
			rang = PRIORITATE_LCN.get(n["tag"], 9)
			if cheie not in ales or rang < ales[cheie][0]:
				ales[cheie] = (rang, n["lcn"], n.get("vizibil"))
	return dict((k, (v[1], v[2])) for k, v in ales.items())


def _pozitii(lista_scanare, rulate):
	"""Pozitiile orbitale ale trecerilor pornite, in ordinea lor; "cablu" si "terestru" pentru celelalte."""
	pozitii = []
	for trecere in (lista_scanare or [])[:max(1, rulate)]:
		for tp in trecere.get("transponders") or []:
			fel = type(tp).__name__
			if fel.endswith("Satellite"):
				p = _int(getattr(tp, "orbital_position", None), None)
			elif fel.endswith("Cable"):
				p = "cablu"
			elif fel.endswith("Terrestrial"):
				p = "terestru"
			else:
				continue
			if p is not None and p not in pozitii:
				pozitii.append(p)
	return pozitii


def _felDin(lista_scanare):
	"""Felul scanarii: "hds_fel" din lista (ecranele si web-ul il pun), altfel felul receptiei."""
	for trecere in lista_scanare or []:
		fel = trecere.get("hds_fel")
		if fel:
			return str(fel)
	feluri = []
	for p in _pozitii(lista_scanare, len(lista_scanare or [])):
		f = p if isinstance(p, str) else "satelit"
		if f not in feluri:
			feluri.append(f)
	return "+".join(feluri) or "necunoscut"


class Scanare(object):
	"""Inregistrarea unei scanari (o fereastra ServiceScan), cu toate trecerile ei."""

	def __init__(self, lista_scanare, acum=None):
		self.lista = list(lista_scanare or [])
		self.inceput = ora(acum)
		self.sfarsit = None
		self.stare = "in_curs"
		self.treceri = {}            # numarul trecerii -> (transpondere, servicii, eroare, retele)
		self.rulate = 1

	def trecere(self, numar, transpondere, servicii, eroare=None, retele=None):
		"""Ce a citit trecerea `numar` (randurile nucleului). O trecere reluata (fereastra ascunsa si aratata din nou)
		isi inlocuieste randurile, nu le dubleaza. `retele`: getNetworks, None la un nucleu fara el."""
		self.treceri[numar] = (list(transpondere or []), list(servicii or []), eroare, list(retele or []))
		self.rulate = max(self.rulate, numar + 1)

	def corp(self):
		transpondere, servicii, vazute, erori, retele = [], [], set(), [], []
		for numar in sorted(self.treceri):
			tps, svs, eroare, rts = self.treceri[numar]
			lista = []
			for r in rts:
				try:
					lista.append(retea(r))
				except Exception as e:
					_jurnal("retea sarita: %r" % (e,))
			retele.append(lista)
			for t in tps:
				try:
					transpondere.append(transponder(t))
				except Exception as e:
					_jurnal("transponder sarit: %r" % (e,))
			for s in svs:
				try:
					din_sdt, rand = serviciu(s)
				except Exception as e:
					_jurnal("serviciu sarit: %r" % (e,))
					continue
				if din_sdt and rand["cheie"] not in vazute:
					vazute.add(rand["cheie"])
					servicii.append(rand)
			if eroare:
				erori.append(eroare)
		retele = _unesteRetele(retele)
		if retele:
			numere = _numere(retele)
			for rand in servicii:
				try:
					sid, _ns, tsid, onid = (int(x, 16) for x in rand["cheie"].split(":"))
				except ValueError:
					continue
				gasit = numere.get((sid, tsid, onid))
				if gasit is not None:
					rand["lcn"] = gasit[0]
					if gasit[1] is not None:
						rand["lcn_vizibil"] = gasit[1]
		doar_libere = any(_int(x.get("flags")) & SCAN_ONLY_FREE for x in self.lista)
		rez = {"result": True, "inceput": self.inceput, "sfarsit": self.sfarsit, "stare": self.stare,
			"fel": _felDin(self.lista), "pozitii": _pozitii(self.lista, self.rulate), "doar_libere": doar_libere,
			"eroare": "; ".join(erori) or None, "transpondere": transpondere, "servicii": servicii}
		if retele:
			rez["retele"] = retele
		return rez

	def publica(self, stare=None, acum=None):
		"""Inlocuieste ultima scanare cu aceasta (memorie si /tmp). `stare` "terminata" sau "oprita" o incheie."""
		if stare is not None and stare != "in_curs":
			self.stare = stare
			self.sfarsit = ora(acum)
		corp = self.corp()
		octeti = json.dumps(corp, ensure_ascii=False, separators=(",", ":")).encode("utf-8", "replace")
		_STARE["octeti"] = octeti
		_STARE["citit_fisier"] = True        # memoria e mai noua decat orice fisier ramas
		_scrie(octeti)
		return corp


def _scrie(octeti):
	nou = FISIER + ".nou"
	try:
		with open(nou, "wb") as f:
			f.write(octeti)
		os.replace(nou, FISIER)
	except Exception as e:
		_jurnal("nu am putut scrie %s: %r" % (FISIER, e))


def incepe(lista_scanare, acum=None):
	"""Scanarea noua: inregistrarea ei ia locul celei de dinainte de la pornire."""
	s = Scanare(lista_scanare, acum)
	s.publica()
	return s


def raspuns():
	"""Octetii JSON pentru ruta, sau None cand nu e nicio scanare de la pornirea receptorului. Dupa o repornire a
	interfetei, ultima scanare se citeste o data din /tmp."""
	if _STARE["octeti"] is None and not _STARE["citit_fisier"]:
		_STARE["citit_fisier"] = True
		try:
			with open(FISIER, "rb") as f:
				octeti = f.read()
			if json.loads(octeti.decode("utf-8")).get("result") is True:
				_STARE["octeti"] = octeti
		except (IOError, OSError, ValueError) as e:
			if not isinstance(e, (IOError, OSError)) or getattr(e, "errno", None) != 2:
				_jurnal("%s nu se poate citi: %r" % (FISIER, e))
	return _STARE["octeti"]


def ultima():
	"""Ultima scanare ca dictionar (pentru probe si pentru alte module), sau None."""
	octeti = raspuns()
	return json.loads(octeti.decode("utf-8")) if octeti else None
