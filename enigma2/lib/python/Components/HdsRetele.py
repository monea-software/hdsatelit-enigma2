# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsRetele.py - retelele citite la scanare din tabela NIT, pastrate pe receptor: numele retelei, frecventele anuntate
# si numerele canalelor date de operator. Le folosesc ecranele, nu numai rezultatul pentru programatori
# (/api/scanare-ultima, Components/HdsScanareUltima.py, care tine numai ultima scanare si numai in /tmp):
#   - sfarsitul scanarii (Components/ServiceScan.py): reteaua gasita, cate frecvente anunta, cate canale au numar;
#   - lista de canale (Screens/ChannelSelection.py): lista retelei in ordinea numerelor operatorului, cu numarul lui
#     langa canal, iar cifrele de pe telecomanda duc la el; listele omului (bouquets.tv, userbouquet.*) nu se ating;
#   - bara de informatii si informatiile canalului (Components/Converter/HdsInfo.py, Components/HdsInformatiiCanal.py):
#     numele retelei si numarul operatorului;
#   - interfata web (rezultatul scanarii, lista de canale, informatiile canalului).
#
# Fisierul FISIER se scrie la sfarsitul unei scanari terminate care a citit NIT-ul (cablu dupa operator, automat, toata
# banda si, numai pentru informatie, pe o frecventa; satelit si terestru cu cautarea in retea). O scanare noua a
# aceleiasi retele (acelasi fel de receptie, acelasi ID de retea si, la satelit, aceeasi pozitie) o aduce la zi;
# celelalte retele raman. O scanare cu cautare in retea (completa) inlocuieste reteaua; una fara (cablu pe o frecventa,
# NIT citit numai pentru informatie) a vazut numai multiplexul ales si se UNESTE cu ce era (_uneste): nimic nu se pierde,
# numele si numerele vin din NIT-ul nou, canalele multiplexului scanat din scanarea noua. Scris in .nou, fsync, apoi
# os.replace: dupa o cadere a curentului ramane fisierul vechi sau cel nou, niciodata unul pe jumatate. Numai ASCII
# (pe receptor Python-ul ruleaza cu locale ASCII). Un fisier stricat se citeste ca gol si se scrie din nou la
# urmatoarea scanare (datele vin oricand din semnal); unul care nu se poate citi din alt motiv nu se scrie peste.
# Forma:
#   {"v": 1, "retele": [{
#     "cheie": "cablu:53" | "terestru:N" | "satelit:<pozitia>:<nid>", "sistem": "cablu" | "terestru" | "satelit",
#     "nid": ID-ul retelei, "poz": pozitia orbitala in zecimi (satelit) sau null, "nume": numele din NIT,
#     "actualizat": ora scanarii (locala, ISO), "pds": [private_data_specifier], "numere": cate numere a anuntat
#     reteaua, "fara_canal": cate numere n-au avut canalul in scanare,
#     "multiplexuri": [{"tsid", "onid", "f_khz", ...}] (frecventele anuntate, ca in /api/scanare-ultima),
#     "canale": [{"lcn", "cheie": "sid:ns:tsid:onid" (hexa), "nume", "tip"(, "ascuns": true)}] (in ordinea numerelor),
#     "fara_numar": [{"cheie", "nume", "tip"}] (canalele retelei fara numar; numai cand reteaua are numere)}]}
# Lista retelei in lista de canale are radacina o cerere a nucleului cu un semn al retelei (cale_lista,
# retea_din_cale): nucleul o poate citi oricand (canalele locului, dupa nume), iar lista de canale o umple in ordinea
# numerelor.
# La import nu se atinge nimic din enigma.
import json
import os
import re
import time

FISIER = "/etc/enigma2/hds-retele.json"
V = 1
MAX_RETELE = 32            # cele mai vechi pleaca primele
MAX_CANALE = 4096          # pe retea, numerotate si fara numar
MAX_MULTIPLEXURI = 512
MAX_OCTETI = 4 * 1024 * 1024
VERIFICARE_S = 2.0         # cat de des se uita la fisier citirea din cache (bara il cere la fiecare schimbare)

POZ_CABLU, POZ_TERESTRU = 0xFFFF, 0xEEEE
TIPURI_TV = (1, 17, 22, 25, 31, 32, 134, 195)     # ca service_types_tv din Screens/ChannelSelection.py
TIPURI_RADIO = (2, 10)
SEMN = "hdsretea"                                 # semnul retelei in calea listei (cuvant intreg, numai litere si cifre)

# generatie: creste la fiecare citire a unui fisier schimbat (lista retelei o compara cu cea de la umplere, generatie())
_CACHE = {"cale": None, "semn": None, "date": None, "verificat": 0.0, "index": None, "eroare": False, "generatie": 0}


def _jurnal(text):
	print("[HdsRetele] %s" % text)


def _int(v, implicit=0):
	try:
		return int(v)
	except (TypeError, ValueError):
		return implicit


def _monoton():
	return getattr(time, "monotonic", time.time)()


def ora(secunde=None):
	return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() if secunde is None else secunde))


def loc_din_ns(ns):
	"""Locul unui namespace DVB: "cablu", "terestru" sau pozitia orbitala in zecimi (0..3599), ca in nucleu."""
	sus = (_int(ns) & 0xFFFFFFFF) >> 16
	if sus == POZ_CABLU:
		return "cablu"
	if sus == POZ_TERESTRU:
		return "terestru"
	return sus % 3600


def sistem_din_loc(loc):
	return loc if loc in ("cablu", "terestru") else "satelit"


def parti_cheie(cheie):
	"""Cheia unui serviciu ("sid:ns:tsid:onid", hexa) -> (sid, ns, tsid, onid), sau None."""
	try:
		sid, ns, tsid, onid = (int(x, 16) for x in str(cheie).split(":"))
	except (ValueError, TypeError):
		return None
	return sid, ns & 0xFFFFFFFF, tsid, onid


def din_ref(ref):
	"""O referinta DVB (text "1:0:tip:sid:tsid:onid:ns:..." sau eServiceReference) -> (sid, ns, tsid, onid), sau None
	(flux, dosar, marcaj)."""
	if ref is None:
		return None
	text = ref if isinstance(ref, str) else None
	if text is None:
		try:
			text = ref.toString()
		except Exception:
			return None
	parti = text.split(":")
	if len(parti) < 10 or (len(parti) > 10 and parti[10]):
		return None
	try:
		if int(parti[0]) != 1 or int(parti[1] or "0") & 0x47:
			return None
		sid, tsid, onid, ns = (int(p or "0", 16) for p in parti[3:7])
	except ValueError:
		return None
	if not sid:
		return None
	return sid, ns & 0xFFFFFFFF, tsid, onid


def refstr(canal):
	"""Referinta unui canal din fisier, ca in lamedb: "1:0:<tip>:<sid>:<tsid>:<onid>:<ns>:0:0:0:"."""
	p = parti_cheie(canal.get("cheie"))
	if p is None:
		return None
	sid, ns, tsid, onid = p
	return "1:0:%X:%X:%X:%X:%X:0:0:0:" % (_int(canal.get("tip"), 1) or 1, sid, tsid, onid, ns)


# ------------------------------------------------------------------ din rezultatul scanarii

def _cheie_retea(sistem, nid, poz):
	if sistem == "satelit":
		return "satelit:%d:%d" % (_int(poz), nid)
	return "%s:%d" % (sistem, nid)


def _locul_retelei(r, transpondere):
	"""Locul retelei: din transponderele scanate care au citit-o (nid), altfel din frecventele anuntate."""
	numar = {}
	for t in transpondere:
		if t.get("nid") != r.get("nid") or not t.get("tp"):
			continue
		try:
			loc = loc_din_ns(int(t["tp"].split(":")[0], 16))
		except (ValueError, IndexError):
			continue
		numar[loc] = numar.get(loc, 0) + 1
	if numar:
		return sorted(numar.items(), key=lambda x: (-x[1], str(x[0])))[0][0]
	sisteme = {}
	for m in r.get("multiplexuri") or []:
		s = m.get("sistem")
		if s in ("cablu", "terestru"):
			sisteme[s] = sisteme.get(s, 0) + 1
		elif s == "satelit" and m.get("poz") is not None:
			p = _int(m.get("poz"))
			sisteme[p % 3600] = sisteme.get(p % 3600, 0) + 1
	if sisteme:
		return sorted(sisteme.items(), key=lambda x: (-x[1], str(x[0])))[0][0]
	return None


def din_scanare(corp, acum=None):
	"""Rezultatul unei scanari (forma din Components/HdsScanareUltima.py: "retele", "servicii", "transpondere") ->
	retelele de pastrat, in forma fisierului. Canalele cu numar sunt serviciile cu "lcn" (numarul ales de
	HdsScanareUltima dupa descriptori) care apar in numerele acelei retele; "lcn_vizibil" false = ascuns."""
	if not isinstance(corp, dict):
		return []
	transpondere = [t for t in corp.get("transpondere") or [] if isinstance(t, dict)]
	servicii = [s for s in corp.get("servicii") or [] if isinstance(s, dict)]
	actualizat = corp.get("sfarsit") or ora(acum)
	rez = []
	for r in corp.get("retele") or []:
		if not isinstance(r, dict) or r.get("nid") is None:
			continue
		nid = _int(r.get("nid"))
		loc = _locul_retelei(r, transpondere)
		if loc is None:
			continue
		sistem = sistem_din_loc(loc)
		triplete = set()
		for n in r.get("lcn") or []:
			try:
				triplete.add((_int(n["sid"]), _int(n["tsid"]), _int(n["onid"])))
			except (KeyError, TypeError):
				continue
		multiplexuri = []
		tps = set()
		for m in (r.get("multiplexuri") or [])[:MAX_MULTIPLEXURI]:
			if isinstance(m, dict):
				multiplexuri.append(dict(m))
				tps.add((_int(m.get("tsid"), -1), _int(m.get("onid"), -1)))
		canale, fara, gasite = [], [], set()
		for s in servicii:
			p = parti_cheie(s.get("cheie"))
			if p is None or loc_din_ns(p[1]) != loc:
				continue
			sid, ns, tsid, onid = p
			rand = {"cheie": "%x:%x:%x:%x" % (sid, ns, tsid, onid), "nume": (s.get("nume") or u"").strip(),
				"tip": _int(s.get("tip"))}
			lcn = _int(s.get("lcn"), 0) if "lcn" in s else 0
			if lcn > 0 and (sid, tsid, onid) in triplete:
				rand = dict(lcn=lcn, **rand)
				if s.get("lcn_vizibil") is False:
					rand["ascuns"] = True
				canale.append(rand)
				gasite.add((sid, tsid, onid))
			elif (tsid, onid) in tps:
				fara.append(rand)
		canale.sort(key=lambda c: (c["lcn"], c["cheie"]))
		fara.sort(key=lambda c: (c["nume"].lower(), c["cheie"]))
		retea = {"cheie": _cheie_retea(sistem, nid, loc), "sistem": sistem, "nid": nid,
			"poz": loc if sistem == "satelit" else None, "nume": (r.get("nume") or u"").strip(),
			"actualizat": actualizat, "pds": sorted(set(_int(x) for x in r.get("pds") or [])),
			"numere": len(triplete), "fara_canal": len(triplete - gasite), "multiplexuri": multiplexuri,
			"canale": canale[:MAX_CANALE], "fara_numar": fara[:max(0, MAX_CANALE - len(canale))] if canale else []}
		if r.get("trunchiat"):
			retea["trunchiat"] = True
		rez.append(retea)
	return rez


# ------------------------------------------------------------------ fisierul

def _citeste_fisier(cale):
	"""-> (date, se_poate_scrie). Lipsa sau stricat: gol, se scrie; alta eroare de citire: gol, NU se scrie peste."""
	try:
		with open(cale, "rb") as f:
			octeti = f.read(MAX_OCTETI + 1)
	except (IOError, OSError) as e:
		if getattr(e, "errno", None) == 2:
			return {"v": V, "retele": []}, True
		_jurnal("%s nu se poate citi: %r" % (cale, e))
		return {"v": V, "retele": []}, False
	if len(octeti) > MAX_OCTETI:
		_jurnal("%s e prea mare, il ignor" % cale)
		return {"v": V, "retele": []}, True
	try:
		date = json.loads(octeti.decode("utf-8"))
	except (ValueError, UnicodeDecodeError, RecursionError) as e:
		_jurnal("%s stricat, il scriu din nou la urmatoarea scanare: %r" % (cale, e))
		return {"v": V, "retele": []}, True
	if not isinstance(date, dict) or not isinstance(date.get("retele"), list):
		return {"v": V, "retele": []}, True
	if _int(date.get("v")) > V:
		_jurnal("%s e scris de o versiune mai noua, nu il schimb" % cale)
		return date, False
	return date, True


def _scrie_fisier(cale, date):
	nou = cale + ".nou"
	try:
		octeti = json.dumps(date, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
		with open(nou, "wb") as f:
			f.write(octeti)
			f.flush()
			os.fsync(f.fileno())
		os.replace(nou, cale)
		return True
	except Exception as e:
		_jurnal("%s nu s-a putut scrie: %r" % (cale, e))
		try:
			os.remove(nou)
		except OSError:
			pass
		return False


def _scanate(corp):
	"""(tsid, onid) ale transponderelor care au dat tabele in scanarea `corp` (au "tp")."""
	rez = set()
	for t in corp.get("transpondere") or []:
		if isinstance(t, dict) and t.get("tp"):
			try:
				_ns, tsid, onid = (int(x, 16) for x in str(t["tp"]).split(":"))
			except ValueError:
				continue
			rez.add((tsid, onid))
	return rez


def _numere_nit(corp, nid):
	"""(sid, tsid, onid) -> (numarul, vizibil sau None) din NIT-ul retelei `nid` al scanarii, ales ca pentru serviciile
	scanate (Components/HdsScanareUltima.py, aceeasi ordine a descriptorilor)."""
	from Components import HdsScanareUltima
	retele = [dict(r, lcn=r.get("lcn") or []) for r in corp.get("retele") or []
		if isinstance(r, dict) and _int(r.get("nid"), -1) == nid]
	return HdsScanareUltima._numere(retele)


def _uneste(vechi, nou, scanate, numere):
	"""Reteaua `nou` (din_scanare, dupa o scanare FARA cautare in retea, deci numai multiplexul ales) unita cu `vechi`
	(aceeasi cheie, din fisier, de pilda de la o cautare in retea de dinainte). Nimic din ce era nu se pierde:
	  - numele, PDS-urile si numerele anuntate vin din NIT-ul nou (NIT-ul e acelasi pe toata reteaua); nume gol = cel vechi;
	  - multiplexurile: cele din NIT-ul nou, plus cele vechi care lipsesc din el;
	  - canalele multiplexurilor scanate acum (`scanate`, (tsid, onid)) sunt cele noi (SDT-ul lor e la zi); canalele
	    vechi de pe celelalte multiplexuri raman, cu numarul si semnul de ascuns din NIT-ul nou cand NIT-ul are serviciul
	    (`numere`), altfel cum erau. Un canal care primeste numar trece intre cele numerotate.
	Canale noi fara serviciu nu apar: randurile vin numai din servicii scanate (acum sau inainte)."""
	rez = dict(nou)
	if not rez.get("nume"):
		rez["nume"] = (vechi.get("nume") or u"").strip()
	rez["pds"] = sorted(set(nou.get("pds") or []) | set(_int(x) for x in vechi.get("pds") or []))
	anuntate = set((_int(m.get("tsid"), -1), _int(m.get("onid"), -1)) for m in nou.get("multiplexuri") or [])
	multiplexuri = list(nou.get("multiplexuri") or [])
	for m in vechi.get("multiplexuri") or []:
		if isinstance(m, dict) and (_int(m.get("tsid"), -1), _int(m.get("onid"), -1)) not in anuntate:
			multiplexuri.append(dict(m))
	rez["multiplexuri"] = multiplexuri[:MAX_MULTIPLEXURI]
	canale, fara = list(nou.get("canale") or []), list(nou.get("fara_numar") or [])
	vazute = set(c.get("cheie") for c in canale + fara)
	for c in (vechi.get("canale") or []) + (vechi.get("fara_numar") or []):
		if not isinstance(c, dict):
			continue
		p = parti_cheie(c.get("cheie"))
		if p is None or (p[2], p[3]) in scanate or c.get("cheie") in vazute:
			continue
		vazute.add(c.get("cheie"))
		rand = {"cheie": c.get("cheie"), "nume": (c.get("nume") or u"").strip(), "tip": _int(c.get("tip"))}
		lcn, ascuns = _int(c.get("lcn"), 0), bool(c.get("ascuns"))
		gasit = numere.get((p[0], p[2], p[3]))
		if gasit is not None and _int(gasit[0]) > 0:
			lcn, ascuns = _int(gasit[0]), gasit[1] is False
		if lcn > 0:
			rand = dict(lcn=lcn, **rand)
			if ascuns:
				rand["ascuns"] = True
			canale.append(rand)
		else:
			fara.append(rand)
	canale.sort(key=lambda c: (c["lcn"], c["cheie"]))
	fara.sort(key=lambda c: (c["nume"].lower(), c["cheie"]))
	rez["canale"] = canale[:MAX_CANALE]
	rez["fara_numar"] = fara[:max(0, MAX_CANALE - len(rez["canale"]))] if rez["canale"] else []
	if numere:
		cu_rand = set()
		for c in rez["canale"]:
			p = parti_cheie(c.get("cheie"))
			if p is not None:
				cu_rand.add((p[0], p[2], p[3]))
		rez["numere"] = len(numere)
		rez["fara_canal"] = len(set(numere) - cu_rand)
	else:
		rez["numere"], rez["fara_canal"] = _int(vechi.get("numere")), _int(vechi.get("fara_canal"))
	return rez


def actualizeaza(corp, cale=None, acum=None, completa=True):
	"""Retelele scanarii `corp` intra in fisier, celelalte retele raman. `completa` (scanare cu cautare in retea):
	fiecare inlocuieste reteaua cu aceeasi cheie; altfel (cablu pe o frecventa, NIT numai pentru informatie) se uneste
	cu ea (_uneste). -> cheile scrise (lista goala: nicio retea in scanare sau fisierul nu s-a putut scrie). Nu arunca."""
	try:
		noi = din_scanare(corp, acum)
	except Exception as e:
		_jurnal("retelele scanarii: %r" % (e,))
		return []
	if not noi:
		return []
	cale = cale or FISIER
	date, se_poate = _citeste_fisier(cale)
	if not se_poate:
		return []
	if not completa:
		try:
			dupa_cheie = dict((r.get("cheie"), r) for r in date.get("retele") or [] if isinstance(r, dict))
			scanate = _scanate(corp)
			noi = [_uneste(dupa_cheie[r["cheie"]], r, scanate, _numere_nit(corp, r["nid"]))
				if isinstance(dupa_cheie.get(r["cheie"]), dict) else r for r in noi]
		except Exception as e:
			# o retea veche cu forma neasteptata: fisierul ramane cum era, datele vin din nou la scanarea urmatoare
			_jurnal("unirea cu reteaua de dinainte: %r" % (e,))
			return []
	chei = set(r["cheie"] for r in noi)
	vechi = [r for r in date.get("retele") or [] if isinstance(r, dict) and r.get("cheie") not in chei]
	toate = noi + vechi
	if len(toate) > MAX_RETELE:
		toate = noi + sorted(vechi, key=lambda r: str(r.get("actualizat") or ""), reverse=True)[:max(0, MAX_RETELE - len(noi))]
	toate.sort(key=lambda r: ({"cablu": 0, "terestru": 1}.get(r.get("sistem"), 2), str(r.get("nume") or "").lower(),
		str(r.get("cheie"))))
	if not _scrie_fisier(cale, {"v": V, "retele": toate}):
		return []
	uita()
	return [r["cheie"] for r in noi]


def uita():
	"""Citirea urmatoare merge din nou la fisier (dupa o scriere, in probe)."""
	_CACHE.update(cale=None, semn=None, date=None, verificat=0.0, index=None)


def semn_fisier(cale=None):
	"""Semnul fisierului de acum, sau None (lipseste): marimea, ora scrierii si ora inodului (in ns), inodul si
	discul. Un fisier pus peste cel vechi (copiat in .nou, apoi mv; os.replace) are alt inod; unul scris pe loc are
	alta ora a inodului, chiar cu aceeasi marime si cu ora scrierii pusa inapoi (cp -p, scp -p, touch -r)."""
	try:
		st = os.stat(cale or FISIER)
	except OSError:
		return None
	return (st.st_size, getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)), getattr(st, "st_ctime_ns", 0),
		st.st_ino, st.st_dev)


def citeste(cale=None, acum_la_fisier=False):
	"""Datele fisierului ({"v", "retele"}), tinute in memorie; fisierul se priveste din nou cel mult o data la
	VERIFICARE_S (semn_fisier), sau chiar acum (acum_la_fisier). Fara fisier: retele goale."""
	cale = cale or FISIER
	acum = _monoton()
	if (not acum_la_fisier and _CACHE["cale"] == cale and _CACHE["date"] is not None and
			acum - _CACHE["verificat"] < VERIFICARE_S):
		return _CACHE["date"]
	semn = semn_fisier(cale)
	if _CACHE["cale"] != cale or semn != _CACHE["semn"] or _CACHE["date"] is None:
		date = {"v": V, "retele": []}
		if semn is not None:
			date, _scrie = _citeste_fisier(cale)
		_CACHE.update(cale=cale, semn=semn, date=date, index=None, generatie=_CACHE["generatie"] + 1)
	_CACHE["verificat"] = acum
	return _CACHE["date"]


def generatie(cale=None):
	"""Versiunea datelor citite din fisier, dupa ce fisierul a fost privit chiar acum: alt numar = alt fisier de la
	citirea de dinainte (o scanare noua, un fisier pus de mana, unul sters). Lista retelei (Screens/ChannelSelection.py,
	hdsReteaLaZi) o tine pe cea de la umplere: alta generatie = lista se umple din nou."""
	citeste(cale, acum_la_fisier=True)
	return _CACHE["generatie"]


def retele(cale=None):
	return [r for r in citeste(cale).get("retele") or [] if isinstance(r, dict)]


def retea(cheie, cale=None):
	for r in retele(cale):
		if r.get("cheie") == cheie:
			return r
	return None


def _index(cale=None):
	"""(serviciu (sid, tsid, onid, loc) -> (retea, canal), multiplex (tsid, onid, loc) -> retea), din cache."""
	date = citeste(cale)
	if _CACHE["index"] is not None and _CACHE["index"][0] is date:
		return _CACHE["index"][1], _CACHE["index"][2]
	servicii, muxuri = {}, {}
	for r in date.get("retele") or []:
		if not isinstance(r, dict):
			continue
		loc = r.get("poz") if r.get("sistem") == "satelit" else r.get("sistem")
		for m in r.get("multiplexuri") or []:
			muxuri.setdefault((_int(m.get("tsid"), -1), _int(m.get("onid"), -1), loc), r)
		for c in (r.get("canale") or []) + (r.get("fara_numar") or []):
			p = parti_cheie(c.get("cheie"))
			if p is not None:
				servicii.setdefault((p[0], p[2], p[3], loc_din_ns(p[1])), (r, c))
				muxuri.setdefault((p[2], p[3], loc_din_ns(p[1])), r)
	_CACHE["index"] = (date, servicii, muxuri)
	return servicii, muxuri


def pentru_ref(ref, cale=None):
	"""Ce se stie despre canalul `ref` (text sau eServiceReference): {"retea": numele retelei, "nid", "cheie_retea",
	"sistem", "lcn": numarul operatorului sau None, "sid", "tsid", "onid", "ns"}, sau None (canal din afara
	retelelor pastrate, flux, dosar)."""
	p = din_ref(ref)
	if p is None:
		return None
	sid, ns, tsid, onid = p
	loc = loc_din_ns(ns)
	try:
		servicii, muxuri = _index(cale)
	except Exception as e:
		_jurnal("indexul retelelor: %r" % (e,))
		return None
	gasit = servicii.get((sid, tsid, onid, loc))
	r, canal = gasit if gasit is not None else (muxuri.get((tsid, onid, loc)), None)
	if r is None:
		return None
	lcn = canal.get("lcn") if canal is not None else None
	return {"retea": r.get("nume") or u"", "nid": r.get("nid"), "cheie_retea": r.get("cheie"), "sistem": r.get("sistem"),
		"lcn": lcn if lcn else None, "sid": sid, "tsid": tsid, "onid": onid, "ns": ns}


# ------------------------------------------------------------------ lista retelei (lista de canale)

def are_lista(r):
	"""Reteaua are lista ei in lista de canale: macar un canal cu numar."""
	return bool(r and any(not c.get("ascuns") for c in r.get("canale") or []))


def retele_cu_lista(loc=None, cale=None):
	"""Retelele cu lista, toate sau numai ale unui loc ("cablu", "terestru", pozitia), in ordinea fisierului."""
	rez = []
	for r in retele(cale):
		if not are_lista(r):
			continue
		if loc is not None and (r.get("poz") if r.get("sistem") == "satelit" else r.get("sistem")) != loc:
			continue
		rez.append(r)
	return rez


def _de_felul(c, radio):
	return _int(c.get("tip")) in (TIPURI_RADIO if radio else TIPURI_TV)


def randuri_lista(cheie, radio=False, cale=None):
	"""Randurile listei retelei: [(numarul sau 0, referinta text, nume)]: intai canalele cu numar, in ordinea
	numerelor (golurile raman goale; doua canale cu acelasi numar raman amandoua), apoi canalele retelei fara numar,
	dupa nume. Ascunsele de operator nu intra. Numai TV sau numai radio."""
	r = retea(cheie, cale)
	if r is None:
		return []
	rez = []
	for c in r.get("canale") or []:
		if not c.get("ascuns") and _de_felul(c, radio):
			s = refstr(c)
			if s:
				rez.append((_int(c.get("lcn")), s, c.get("nume") or u""))
	for c in r.get("fara_numar") or []:
		if _de_felul(c, radio):
			s = refstr(c)
			if s:
				rez.append((0, s, c.get("nume") or u""))
	return rez


def ref_pentru_numar(cheie, numar, radio=False, cale=None):
	"""Canalul cu numarul operatorului `numar` din lista retelei (primul, cand sunt doua), sau None."""
	for n, s, _nume in randuri_lista(cheie, radio, cale):
		if n == numar:
			return s
	return None


def semn(cheie):
	"""Cheia retelei ca un singur cuvant al cererii nucleului (numai litere si cifre): "hdsreteacablu53"."""
	return SEMN + re.sub(r"[^a-z0-9]", "x", str(cheie).lower())


def cale_lista(r, service_types):
	"""Calea radacinii listei retelei `r`, dupa felurile de servicii ale listei (service_types din lista de canale,
	"1:7:1:0:0:0:0:0:0:0:(type == 1) || ..."): canalele locului retelei cu semnul ei, o cerere pe care nucleul o stie
	(numele unui serviciu nu poate fi semnul, deci conditia e mereu adevarata)."""
	i = service_types.rfind(":")
	loc = POZ_CABLU if r.get("sistem") == "cablu" else POZ_TERESTRU if r.get("sistem") == "terestru" else _int(r.get("poz"))
	return "%s(satellitePosition == %d) && (name != %s) && %s ORDER BY name" % (service_types[:i + 1], loc,
		semn(r.get("cheie")), service_types[i + 1:])


_SEMN_IN_CALE = re.compile(r"\(name != (" + SEMN + r"[a-z0-9]+)\)")


def retea_din_cale(cale, fisier=None):
	"""Cheia retelei a carei lista e radacina cu calea `cale`, sau None (alta lista; retea care nu mai e in fisier)."""
	m = _SEMN_IN_CALE.search(cale or "")
	if m is None:
		return None
	for r in retele(fisier):
		if semn(r.get("cheie")) == m.group(1):
			return r.get("cheie")
	return None


def e_cale_de_retea(cale):
	"""Calea are semnul unei liste de retea (chiar daca reteaua nu mai e in fisier)."""
	return _SEMN_IN_CALE.search(cale or "") is not None


# ------------------------------------------------------------------ rezumatul de la sfarsitul scanarii

def rezumat(corp):
	"""Retelele unei scanari, pentru ecranul de scanare si web: [{"nume", "nid", "sistem", "frecvente": cate
	multiplexuri anunta, "cu_numar": canale cu numar gasite, "tv", "radio": dintre ele, "fara_canal"}]."""
	rez = []
	for r in din_scanare(corp):
		vazute = [c for c in r["canale"] if not c.get("ascuns")]
		rez.append({"nume": r["nume"], "nid": r["nid"], "sistem": r["sistem"], "cheie": r["cheie"], "poz": r["poz"],
			"frecvente": len(r["multiplexuri"]), "cu_numar": len(vazute),
			"tv": sum(1 for c in vazute if _de_felul(c, False)), "radio": sum(1 for c in vazute if _de_felul(c, True)),
			"fara_canal": r["fara_canal"]})
	return rez
