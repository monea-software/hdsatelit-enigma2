# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsEditorCanaleUnelte.py: uneltele editorului de canale (Components/HdsEditorCanale.py), aceleasi pe televizor si in
# pagina web: cautarea, sortarea, canalele de test si cele fara nume, dublurile, canalele care nu mai exista (randuri
# de buchet fara serviciu in lamedb), problemele gasite la deschidere, fluxurile m3u, arhivele (import si export).
#
# Canalele de test: doua grupe, niciuna bifata de aici. „Fara nume”: numele gol sau numai semne („.”, „-”, „_”,
# spatii). „Nume de test”: TIPARE_TEST (Test, Test42, ARD-Test-1, Service 13233 = numele pus cand lipseste SDT,
# Ch-5590, „SID 0x...”, numele facut la scanare „12271H SID 0x200”, N/A, Unknown). Fiecare rand are frecventa,
# polarizarea, SID-ul si daca are imagine / sunet (din PID-urile tinute minte), ca omul sa judece: un canal cu „.” poate
# fi un flux care porneste uneori.
#
# Nimic din enigma2 la incarcare: probele pe PC.

import io
import os
import re
import tarfile
import time
import unicodedata
import zipfile

try:
	from Components import HdsEditorCanaleDate as D
except ImportError:
	import HdsEditorCanaleDate as D

MAX_ARHIVA = 64 * 1024 * 1024        # octetii despachetati dintr-o arhiva
MAX_FISIERE_ARHIVA = 5000

TIPARE_TEST = (
	re.compile(r"^test\b", re.I),
	re.compile(r"\btest[\s_-]*\d*$", re.I),
	re.compile(r"\b[a-z]{2,}-test-\d+\b", re.I),
	re.compile(r"^service\s*\d+$", re.I),
	re.compile(r"^ch[\s_-]?\d+$", re.I),
	re.compile(r"^channel\s*\d+$", re.I),
	re.compile(r"\bSID\s*(0x)?[0-9a-f]+$", re.I),
	re.compile(r"^\d+\s*[HVLR]?\s+SID\s+0x[0-9a-f]+$", re.I),
	re.compile(r"^n/?a$", re.I),
	re.compile(r"^unknown$", re.I),
	re.compile(r"^(tv|radio|data|service|program{1,2}e?)\s*\d+$", re.I),
	re.compile(r"^\(?\d+\)?$"),
)


def _t(text):
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def fara_nume(nume):
	"""Numele gol sau numai semne si spatii (fara nicio litera sau cifra)."""
	return not any(c.isalnum() for c in (nume or ""))


def nume_de_test(nume):
	n = (nume or "").strip()
	if not n or fara_nume(n):
		return False
	return any(t.search(n) for t in TIPARE_TEST)


def normalizeaza(text):
	t = "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()
	return " ".join(re.sub(r"[^0-9a-z+]+", " ", t).split())


# ---------------------------------------------------------------- grupele uneltelor

class Grupa(object):
	__slots__ = ("id", "titlu", "explicatie", "randuri")

	def __init__(self, id_, titlu, explicatie, randuri):
		self.id, self.titlu, self.explicatie, self.randuri = id_, titlu, explicatie, randuri


class Rand(object):
	__slots__ = ("ref", "nume", "poz_text", "frecv", "pol", "sid", "are_video", "are_sunet", "buchete", "buchet_id",
		"indice", "id_intrare", "inlocuire", "tp_text", "tip", "furnizor", "ascuns", "cheie", "grup", "buchet_nume",
		"poz")

	def __init__(self, **k):
		for a in self.__slots__:
			setattr(self, a, k.get(a))


def _rand_canal(s, c, harta):
	return Rand(ref=c.ref, nume=c.nume, poz_text=c.poz_text, frecv=c.frecv, pol=c.pol, sid=c.sid,
		are_video=c.are_video, are_sunet=c.are_sunet, buchete=len(harta.get(c.cheie, ())), tp_text=c.tp_text,
		tip=c.tip, furnizor=c.furnizor, ascuns=c.ascuns, cheie=c.cheie, poz=c.poz)


def canale_test(s, radio=None):
	"""[Grupa "fara_nume", Grupa "test"] din toate serviciile din lamedb (si cele ascunse)."""
	harta = s._harta_buchete()
	goale, test = [], []
	for c in s.toate(radio):
		if fara_nume(c.nume):
			goale.append(_rand_canal(s, c, harta))
		elif nume_de_test(c.nume):
			test.append(_rand_canal(s, c, harta))
	ordine = lambda r: (D.ordine_pozitie(r.poz), r.frecv or 0, r.pol or "", r.sid or 0)
	goale.sort(key=ordine)
	test.sort(key=ordine)
	return [
		Grupa("fara_nume", _t("Canale fără nume"), _t("Numele e gol sau are numai semne (punct, liniuță, spații). "
			"Unele pot fi fluxuri care pornesc numai uneori: uită-te la frecvență și la imagine / sunet."), goale),
		Grupa("test", _t("Nume de test"), _t("Nume puse de emițător pentru probe sau de receptor când lipsește "
			"numele (Test, Service 1234, Ch-12, SID ...)."), test),
	]


def dubluri(s):
	harta = s._harta_buchete()
	in_buchet = []
	for b in s.d.buchete.values():
		if b.id in ("bouquets.tv", "bouquets.radio"):
			continue
		vazute = {}
		for k, i in enumerate(b.intrari):
			if i.fel not in ("canal", "flux"):
				continue
			cheie = i.cheie or i.ref
			if cheie in vazute:
				x = s._info_intrare(i)
				c = x.serviciu
				in_buchet.append(Rand(ref=i.ref, nume=x.nume, poz_text=c.poz_text if c else "", frecv=c.frecv if c else None,
					pol=c.pol if c else "", sid=c.sid if c else None, are_video=c.are_video if c else None,
					are_sunet=c.are_sunet if c else None, buchete=len(harta.get(i.cheie, ())), buchet_id=b.id,
					indice=k, id_intrare=i.id, tp_text=c.tp_text if c else "", cheie=i.cheie,
					buchet_nume=D.fara_mod(b.nume)))
			else:
				vazute[cheie] = k
	pe_nume = {}
	for c in s.toate(None):
		if fara_nume(c.nume):
			continue
		pe_nume.setdefault((normalizeaza(c.nume), c.poz, c.tip), []).append(c)
	acelasi = []
	for (n, poz, tip), lista in sorted(pe_nume.items(), key=lambda x: (D.ordine_pozitie(x[0][1]), x[0][0])):
		if len(lista) < 2:
			continue
		for c in lista:
			r = _rand_canal(s, c, harta)
			r.grup = n
			acelasi.append(r)
	pe_cheie = []
	for cheie, k5s in s.d.lamedb.pe_cheie().items():
		if len(k5s) > 1:
			for k5 in k5s:
				sv = s.d.lamedb.servicii[k5]
				pe_cheie.append(Rand(ref=sv.ref, nume=sv.nume, sid=sv.sid, cheie=cheie, grup=cheie))
	return [
		Grupa("in_buchet", _t("De două ori în același buchet"), _t("Al doilea rând al aceluiași canal din buchet. "
			"Ștergerea scoate numai rândul în plus."), in_buchet),
		Grupa("acelasi_nume", _t("Același nume pe aceeași poziție"), _t("Canale diferite (alt SID sau alt "
			"transponder) cu același nume pe același satelit. Nu sunt neapărat dubluri: uită-te la frecvență."), acelasi),
		Grupa("aceeasi_cheie", _t("Același canal de două ori în listă"), _t("Același SID pe același transponder, "
			"scris de două ori cu alt tip de serviciu."), pe_cheie),
	]


def _candidat(s, i, x, pe_sid, pe_nume):
	"""Serviciul la care se poate lega un rand fara serviciu: acelasi SID, TSID, ONID sub alt spatiu de nume (o lista
	cautata din nou), altfel acelasi nume pe aceeasi pozitie."""
	r = i.r
	d = r.date
	cand = pe_sid.get((d[1], d[2], d[3]))
	if cand:
		poz = D.poz_din_ns(d[4])
		bune = [c for c in cand if c.poz == poz] or cand
		return bune[0]
	if x.nume:
		cand = pe_nume.get((normalizeaza(x.nume), D.poz_din_ns(d[4])))
		if cand:
			return cand[0]
	return None


def referinte_moarte(s):
	pe_sid, pe_nume = {}, {}
	for c in s.toate(None):
		k5 = c.k5
		pe_sid.setdefault((k5[0], k5[2], k5[3]), []).append(c)
		pe_nume.setdefault((normalizeaza(c.nume), c.poz), []).append(c)
	rez = []
	for b in s.d.buchete.values():
		for k, i in enumerate(b.intrari):
			if i.fel != "canal" or s.d.lamedb.dupa_cheie(i.cheie):
				continue
			x = s._info_intrare(i)
			d = i.r.date
			poz = D.poz_din_ns(d[4])
			rez.append(Rand(ref=i.ref, nume=x.nume or _t("fără nume"), poz_text=D.text_pozitie(poz), sid=d[1],
				buchet_id=b.id, indice=k, id_intrare=i.id, inlocuire=_candidat(s, i, x, pe_sid, pe_nume), cheie=i.cheie,
				buchet_nume=D.fara_mod(b.nume)))
	return [Grupa("moarte", _t("Canale care nu mai există"), _t("Rânduri din buchete al căror canal nu mai e în "
		"lista receptorului (după o căutare nouă sau o listă adusă din altă parte). Unde am găsit același canal, "
		"„Repară” îl leagă din nou; altfel rândul se scoate."), rez)]


def buchete_goale(s):
	rez = []
	for b in s.d.buchete.values():
		if b.id in ("bouquets.tv", "bouquets.radio") or b.intrari:
			continue
		if b.id in ("userbouquet.favourites.tv", "userbouquet.favourites.radio"):
			continue
		rez.append(Rand(nume=D.fara_mod(b.nume), buchet_id=b.id))
	return Grupa("buchete_goale", _t("Buchete goale"), _t("Buchete fără niciun rând."), rez)


def transpondere_goale(s):
	"""Transponderele din lamedb fara niciun serviciu (raman dupa stergeri sau dupa cautari pe frecvente goale).
	Randul: nume = textul transponderului, cheie = cheia lui ca text (ns:tsid:onid)."""
	folosite = set(sv.tp_cheie for sv in s.d.lamedb.servicii.values())
	rez = []
	for k, t in s.d.lamedb.transpondere.items():
		if k in folosite:
			continue
		poz, poz_text, frecv, pol, sr, text = s._info_tp(t)
		rez.append(Rand(nume=text or t.cheie_text(), poz_text=poz_text, poz=poz, frecv=frecv, pol=pol,
			cheie=t.cheie_text()))
	rez.sort(key=lambda r: (D.ordine_pozitie(r.poz), r.frecv or 0, r.pol or ""))
	return Grupa("transpondere_goale", _t("Transpondere fără canale"), _t("Transpondere din lista receptorului fără "
		"niciun canal (rămase după ștergeri sau după căutări pe frecvențe goale). Nu încurcă, dar se pot șterge."), rez)


MAX_RANDURI_COMPARARE = 1000


def compara(s, vechi, acum=None, fel="copie"):
	"""Lista sesiunii (s.d, cu schimbarile nesalvate) fata de `vechi` (Date, de obicei o copie de siguranta).
	Cu acum=Date si fel="import": ce s-ar schimba daca `acum` (lista din arhiva) ar inlocui lista de acum (`vechi`)."""
	acum = acum if acum is not None else s.d

	def rand_sv(sv, db, inainte=None):
		tp = db.transpondere.get(sv.tp_cheie)
		if tp is not None:
			poz, poz_text, frecv, pol, sr, text = s._info_tp(tp)
		else:
			poz = D.poz_din_ns(sv.ns)
			poz_text, frecv, pol, text = D.text_pozitie(poz), None, "", ""
		return Rand(ref=sv.ref, nume=sv.nume, poz_text=poz_text, poz=poz, frecv=frecv, pol=pol, sid=sv.sid,
			tp_text=text, cheie=sv.cheie, buchet_nume=(_t("înainte: %s") % inainte) if inainte is not None else None)

	noi, scoase, redenumite = [], [], []
	for k, sv in acum.lamedb.servicii.items():
		v = vechi.lamedb.servicii.get(k)
		if v is None:
			noi.append(rand_sv(sv, acum.lamedb))
		elif v.nume != sv.nume:
			redenumite.append(rand_sv(sv, acum.lamedb, v.nume))
	for k, v in vechi.lamedb.servicii.items():
		if k not in acum.lamedb.servicii:
			scoase.append(rand_sv(v, vechi.lamedb))
	ordine = lambda r: (D.ordine_pozitie(r.poz), r.frecv or 0, r.pol or "", r.sid or 0)
	for l in (noi, scoase, redenumite):
		l.sort(key=ordine)

	def nume_b(b):
		if b.id in ("bouquets.tv", "bouquets.radio"):
			return _t("Lista buchetelor") + (" (Radio)" if b.id == "bouquets.radio" else "")
		return D.fara_mod(b.nume) or b.id

	b_noi, b_scoase, b_schimbate = [], [], []
	for bid in sorted(set(acum.buchete) | set(vechi.buchete)):
		a, v = acum.buchete.get(bid), vechi.buchete.get(bid)
		if v is None:
			b_noi.append(Rand(nume=nume_b(a), buchet_id=bid, buchet_nume=_t("rânduri: %d") % len(a.intrari)))
		elif a is None:
			b_scoase.append(Rand(nume=nume_b(v), buchet_id=bid, buchet_nume=_t("rânduri: %d") % len(v.intrari)))
		else:
			ra = [(i.ref, i.descriere or "") for i in a.intrari]
			rv = [(i.ref, i.descriere or "") for i in v.intrari]
			if ra == rv and a.nume == v.nume:
				continue
			sa, sv_ = set(ra), set(rv)
			parti = [_t("rânduri puse: %d") % len(sa - sv_), _t("scoase: %d") % len(sv_ - sa)]
			if sa == sv_ and ra != rv:
				parti = [_t("altă ordine")]
			if a.nume != v.nume:
				parti.append(_t("înainte: %s") % D.fara_mod(v.nume))
			b_schimbate.append(Rand(nume=nume_b(a), buchet_id=bid, buchet_nume=" · ".join(parti)))

	def grupa(id_, titlu, explicatie, randuri):
		if len(randuri) > MAX_RANDURI_COMPARARE:
			explicatie = (explicatie + " " if explicatie else "") + _t("Se arată primele %d.") % MAX_RANDURI_COMPARARE
			randuri = randuri[:MAX_RANDURI_COMPARARE]
		return Grupa(id_, titlu, explicatie, randuri)

	if fel == "import":
		return [
			grupa("canale_noi", _t("Canale care vin din arhivă"), _t("Sunt în arhivă, dar nu în lista de acum."), noi),
			grupa("canale_scoase", _t("Canale care dispar"), _t("Sunt în lista de acum, dar nu în arhivă: la "
				"„Înlocuiește lista de acum” pleacă; la „Adaugă numai ce lipsește” rămân."), scoase),
			grupa("canale_redenumite", _t("Canale cu alt nume în arhivă"), "", redenumite),
			grupa("buchete_noi", _t("Buchete care vin din arhivă"), "", b_noi),
			grupa("buchete_scoase", _t("Buchete care dispar"), _t("La „Înlocuiește lista de acum” pleacă."), b_scoase),
			grupa("buchete_schimbate", _t("Buchete schimbate de arhivă"), _t("Rânduri puse sau scoase față de lista de "
				"acum, sau altă ordine."), b_schimbate),
		]
	return [
		grupa("canale_noi", _t("Canale noi"), _t("În lista de acum, dar nu în copie."), noi),
		grupa("canale_scoase", _t("Canale care nu mai sunt"), _t("În copie, dar nu în lista de acum."), scoase),
		grupa("canale_redenumite", _t("Canale redenumite"), _t("Același canal, cu alt nume decât în copie."),
			redenumite),
		grupa("buchete_noi", _t("Buchete noi"), "", b_noi),
		grupa("buchete_scoase", _t("Buchete care nu mai sunt"), "", b_scoase),
		grupa("buchete_schimbate", _t("Buchete schimbate"), _t("Rânduri puse sau scoase față de copie, sau altă "
			"ordine."), b_schimbate),
	]


def compara_import(s, dosar):
	"""Ce s-ar schimba daca lista din dosarul despachetat al unei arhive ar inlocui lista de acum."""
	arhiva = D.citeste_dosar(dosar, sateliti=os.path.join(dosar, "satellites.xml"))
	return compara(s, s.d, acum=arhiva, fel="import")


_HD_NUME = re.compile(r"(^|[^0-9a-z])(hd|fhd|uhd|4k|8k)([^0-9a-z]|$)", re.I)


def hd_in_nume_sd(nume, tip):
	"""Numele spune HD / UHD / 4K, dar tipul serviciului din lamedb e unul SD (filtrul HD al listei nu-l prinde)."""
	return bool(_HD_NUME.search(nume or "")) and tip in D.TIPURI_TV and tip not in D.TIPURI_HD and \
		tip not in D.TIPURI_UHD


def verifica(s):
	"""Unealta Verifica lista: ce s-ar scrie altfel decat se vede (nume prea lungi, randuri care nu s-ar citi la fel), canalele
	al caror satelit lipseste din satellites.xml, marcajele fara canale sub ele, canalele cu HD in nume si tip SD,
	serviciile de date. Nimic nu se schimba aici."""
	harta = s._harta_buchete()
	# 1. scrierea: lamedb si fiecare buchet scrise si citite din nou
	scriere = []
	try:
		db2 = D.citeste_lamedb(s.d.lamedb.text().encode("utf-8", "surrogateescape"))
		if set(db2.servicii) != set(s.d.lamedb.servicii):
			scriere.append(Rand(nume=_t("Lista canalelor (lamedb)"), buchet_nume=_t("nu se citește la fel")))
	except Exception:
		scriere.append(Rand(nume=_t("Lista canalelor (lamedb)"), buchet_nume=_t("nu se citește la fel")))
	for b in s.d.buchete.values():
		try:
			b2 = D.citeste_buchet(b.id, b.text().encode("utf-8", "surrogateescape"), lambda: 0)
			if [i.ref for i in b2.intrari] != [i.ref for i in b.intrari]:
				raise ValueError()
		except Exception:
			scriere.append(Rand(nume=D.fara_mod(b.nume) or b.id, buchet_id=b.id, buchet_nume=_t("nu se citește la fel")))
	# 2. nume prea lungi (se scurteaza la scriere: tamponul de 256 de octeti al imaginii)
	lungi = []
	for sv in s.d.lamedb.servicii.values():
		if len(sv.nume.encode("utf-8", "surrogateescape")) > D.LUNGIME_MAXIMA:
			lungi.append(_rand_canal(s, s._canal(sv), harta))
	# 3. pozitii de satelit fara satelit in satellites.xml (numai cand fisierul a fost citit)
	fara_sat = []
	if s.d.sateliti:
		for c in s.toate(None):
			if isinstance(c.poz, int) and c.poz not in s.d.sateliti:
				fara_sat.append(_rand_canal(s, c, harta))
	# 4. marcaje fara niciun canal sub ele (pana la marcajul urmator sau la sfarsit)
	goale = []
	for b in s.d.buchete.values():
		if b.id in ("bouquets.tv", "bouquets.radio"):
			continue
		l = b.intrari
		for k, i in enumerate(l):
			if i.fel != "marcaj":
				continue
			urm = k + 1
			while urm < len(l) and l[urm].fel == "spatiu":
				urm += 1
			if urm >= len(l) or l[urm].fel == "marcaj":
				x = s._info_intrare(i)
				goale.append(Rand(nume=x.nume or _t("fără nume"), buchet_id=b.id, id_intrare=i.id, indice=k,
					buchet_nume=D.fara_mod(b.nume)))
	# 5. HD in nume, tip SD; 6. serviciile de date (nu se pot porni pe televizor)
	hd, date = [], []
	for c in s.toate(None):
		if c.tip == "date":
			date.append(_rand_canal(s, c, harta))
		elif hd_in_nume_sd(c.nume, c.stype):
			hd.append(_rand_canal(s, c, harta))
	ordine = lambda r: (D.ordine_pozitie(r.poz), r.frecv or 0, r.pol or "", r.sid or 0)
	for l in (lungi, fara_sat, hd, date):
		l.sort(key=ordine)
	return [
		Grupa("scriere", _t("Rânduri care nu s-ar scrie la fel"), _t("Lista e scrisă și citită din nou, ca la "
			"salvare. Când grupa e goală, lista se scrie exact cum o vezi."), scriere),
		Grupa("nume_lungi", _t("Nume prea lungi"), _t("Receptorul citește cel mult 250 de octeți pe rând: la salvare "
			"numele acestea se scurtează."), lungi),
		Grupa("fara_satelit", _t("Canale de pe sateliți care nu sunt în satellites.xml"), _t("Receptorul nu are "
			"setările acestor sateliți: canalele nu pornesc până nu pui satelitul în setările antenei. Nimic nu e "
			"bifat; le ștergi numai dacă vrei."), fara_sat),
		Grupa("marcaje_goale", _t("Marcaje fără canale sub ele"), _t("Marcajul e urmat de alt marcaj sau e la "
			"sfârșitul buchetului."), goale),
		Grupa("hd_nume_sd", _t("HD în nume, tip SD în listă"), _t("Numele spune HD sau 4K, dar emițătorul îl "
			"anunță ca SD: filtrul „HD și 4K” nu-l prinde. Filtrul „HD în nume, tip SD” din „Adaugă canale” le "
			"arată pe toate, cu bife."), hd),
		Grupa("date", _t("Servicii de date"), _t("Nu se pot porni pe televizor (ghid de programe, actualizări, "
			"date ale operatorului). Le poți șterge, dar unele le folosește receptorul."), date),
	]


MAX_FLUXURI = 300           # cate adrese de fluxuri se incearca la o verificare
SECUNDE_FLUX = 5


def _raspunde_fluxul(adresa):
	"""None cand fluxul raspunde (cod HTTP sub 400 sau un raspuns oarecare la rtsp / rtmp / udp), altfel textul
	motivului pentru om. Se citesc cel mult cateva sute de octeti."""
	if not adresa.lower().startswith(("http://", "https://")):
		return None
	try:
		try:
			from urllib.request import Request, urlopen
		except ImportError:
			from urllib2 import Request, urlopen
		r = urlopen(Request(adresa, headers={"User-Agent": "Enigma2 HbbTV", "Range": "bytes=0-511"}),
			timeout=SECUNDE_FLUX)
		cod = getattr(r, "status", None) or r.getcode()
		r.read(512)
		r.close()
		return None if cod is None or cod < 400 else _t("răspunde cu eroarea %d") % cod
	except Exception as e:
		cod = getattr(e, "code", None)
		if cod:
			return _t("răspunde cu eroarea %d") % cod
		return _t("nu răspunde")


def fluxuri_care_nu_raspund(s):
	"""Fluxurile (adrese de internet) din buchete care nu raspund acum; se incearca pe 8 fire, cel mult
	MAX_FLUXURI adrese, fiecare cel mult SECUNDE_FLUX secunde. Randurile se pot scoate din buchete."""
	import threading
	pe_adresa = {}
	locale = 0
	for b in s.d.buchete.values():
		for i in b.intrari:
			if i.fel != "flux":
				continue
			adresa = D.decodeaza(i.r.cale)
			gazda = adresa.split("://", 1)[-1].split("/", 1)[0].rsplit("@", 1)[-1]
			gazda = (gazda[1:].split("]", 1)[0] if gazda.startswith("[") else gazda.rsplit(":", 1)[0]).lower()
			if gazda in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
				# releele receptorului (DVB-T2 si DAB+ din satelit, DVB-I): merg numai cand sunt pornite
				locale += 1
				continue
			pe_adresa.setdefault(adresa, []).append((b, i))
	adrese = list(pe_adresa)[:MAX_FLUXURI]
	rezultat = {}
	coada = list(adrese)
	paza = threading.Lock()

	def lucreaza():
		while True:
			with paza:
				if not coada:
					return
				adresa = coada.pop()
			rezultat[adresa] = _raspunde_fluxul(adresa)

	fire = [threading.Thread(target=lucreaza) for _k in range(8)]
	for f in fire:
		f.daemon = True
		f.start()
	for f in fire:
		f.join(SECUNDE_FLUX * (len(adrese) // 8 + 2))
	randuri = []
	for adresa in adrese:
		motiv = rezultat.get(adresa)
		if motiv is None:
			continue
		for b, i in pe_adresa[adresa]:
			x = s._info_intrare(i)
			gazda = adresa.split("://", 1)[-1].split("/", 1)[0]
			randuri.append(Rand(nume=x.nume or gazda, poz_text=gazda, buchet_id=b.id, id_intrare=i.id,
				buchet_nume=D.fara_mod(b.nume) + " · " + motiv, ref=i.ref))
	explicatie = _t("Am încercat %d adrese de fluxuri din buchete: acestea nu răspund acum. Un flux poate merge din "
		"nou mai târziu; scoate-l numai dacă știi că nu mai există.") % len(adrese)
	if locale:
		explicatie += " " + _t("Releele receptorului (adresele 127.0.0.1) nu se încearcă: merg numai când sunt pornite. "
			"Rânduri sărite: %d.") % locale
	return Grupa("fluxuri", _t("Fluxuri care nu răspund"), explicatie, randuri)


def probleme(s):
	"""Ce merita aratat la deschidere: {fel: numar}, numai felurile cu ceva gasit."""
	rez = {}
	for g in canale_test(s):
		if g.randuri:
			rez[g.id] = len(g.randuri)
	for g in dubluri(s):
		if g.randuri and g.id != "acelasi_nume":
			rez[g.id] = len(g.randuri)
	g = referinte_moarte(s)[0]
	if g.randuri:
		rez["moarte"] = len(g.randuri)
	g = buchete_goale(s)
	if g.randuri:
		rez["buchete_goale"] = len(g.randuri)
	n = len(s.nelegate())
	if n:
		rez["nelegate"] = n
	return rez


# ---------------------------------------------------------------- cautarea si sortarea

def rang_cautare(nume, q):
	"""0 = numele incepe cu textul cautat (normalizat), 1 = un cuvant din nume incepe cu el, 2 = restul."""
	n = normalizeaza(nume)
	if not q or n.startswith(q):
		return 0
	return 1 if (" " + q) in (" " + n) else 2


def cauta(canale, text, chei=None):
	"""Canalele care se potrivesc cu textul: in nume si furnizor (fara diacritice, cuvant cu cuvant), SID (zecimal
	sau 0x hex), frecventa (MHz). chei: numai canalele cu aceste chei (filtrele bazei)."""
	q = normalizeaza(text)
	if chei is not None:
		canale = [c for c in canale if c.cheie in chei]
	if not q:
		return list(canale)
	cuv = q.split()
	numar = None
	t = (text or "").strip().lower()
	try:
		numar = int(t, 16) if t.startswith("0x") else (int(t) if t.isdigit() else None)
	except ValueError:
		numar = None
	rez = []
	for c in canale:
		n = normalizeaza(c.nume) + " " + normalizeaza(c.furnizor)
		if all(w in n for w in cuv):
			rez.append(c)
		elif numar is not None and (c.sid == numar or c.frecv == numar):
			rez.append(c)
	# intai numele care incep cu textul, apoi cele cu un cuvant care incepe cu el, apoi restul (ordinea data ramane in
	# fiecare grupa: sortarea e stabila)
	return sorted(rez, key=lambda c: rang_cautare(c.nume, q))


def sorteaza(intrari, cheie, indici=None, invers=False):
	"""Intrarile sortate: indici=None -> fiecare portiune dintre doua marcaje separat (marcajele si randurile goale stau
	pe loc); altfel numai pozitiile date, intre ele."""
	l = list(intrari)
	if indici is not None:
		poz = sorted(set(k for k in indici if 0 <= k < len(l)))
		valori = sorted((l[k] for k in poz), key=cheie, reverse=invers)
		for k, v in zip(poz, valori):
			l[k] = v
		return l
	rez = []
	bucata = []
	for i in l:
		if i.fel in ("marcaj", "spatiu"):
			rez.extend(sorted(bucata, key=cheie, reverse=invers))
			bucata = []
			rez.append(i)
		else:
			bucata.append(i)
	rez.extend(sorted(bucata, key=cheie, reverse=invers))
	return rez


# ---------------------------------------------------------------- m3u

_EXTINF = re.compile(r"^#EXTINF:[^,]*?(?:group-title=\"([^\"]*)\")?[^,]*,(.*)$", re.I)
_GRUP = re.compile(r'group-title="([^"]*)"', re.I)


def citeste_m3u(text):
	"""[(grupa, nume, adresa)] dintr-un m3u / m3u8 (EXTINF, EXTGRP)."""
	if isinstance(text, bytes):
		try:
			text = text.decode("utf-8")
		except UnicodeDecodeError:
			text = text.decode("latin-1")
	rez = []
	nume, grupa, grupa_ext = None, "", ""
	for rand in text.replace("\r", "").split("\n"):
		rand = rand.strip()
		if not rand:
			continue
		if rand.upper().startswith("#EXTINF"):
			virgula = rand.find(",", rand.rfind('"') + 1 if '"' in rand else 0)
			nume = rand[virgula + 1:].strip() if virgula >= 0 else ""
			m = _GRUP.search(rand)
			grupa = m.group(1).strip() if m else ""
		elif rand.upper().startswith("#EXTGRP:"):
			grupa_ext = rand[8:].strip()
		elif rand.startswith("#"):
			continue
		elif "://" in rand:
			rez.append((grupa or grupa_ext, nume or rand, rand))
			nume, grupa = None, ""
	return rez


def exporta_m3u(s, buchet_id, gazda="", port=8001):
	"""Buchetul ca m3u: canalele DVB prin serverul de flux al receptorului (http://gazda:8001/<ref>), fluxurile cu
	adresa lor."""
	b = s._b(buchet_id)
	r = ["#EXTM3U"]
	grupa = ""
	for i in b.intrari:
		x = s._info_intrare(i)
		if x.fel == "marcaj":
			grupa = x.nume
			continue
		if x.fel == "canal":
			url = "http://%s:%d/%s" % (gazda or "127.0.0.1", port, i.ref)
		elif x.fel == "flux":
			url = D.decodeaza(i.r.cale)
		else:
			continue
		nume = (x.nume or "").replace(",", " ")
		if grupa:
			r.append('#EXTINF:-1 group-title="%s",%s' % (grupa.replace('"', "'"), nume))
		else:
			r.append("#EXTINF:-1,%s" % nume)
		r.append(url)
	return "\n".join(r) + "\n"


# ---------------------------------------------------------------- arhivele

def _nume_sigur(nume):
	n = nume.replace("\\", "/")
	if n.startswith("/") or any(p == ".." for p in n.split("/")):
		return None
	return n


def despacheteaza_arhiva(date, dest, nume=""):
	"""Arhiva (tar, tar.gz, tar.bz2, tar.xz, zip) din octeti in dest, numai fisiere obisnuite, fara cai periculoase,
	cel mult MAX_ARHIVA octeti. -> dosarul cu lista (cel care are lamedb sau bouquets.tv), sau None."""
	total = [0]

	def scrie(cale, octeti):
		total[0] += len(octeti)
		if total[0] > MAX_ARHIVA:
			raise ValueError("arhiva prea mare")
		d = os.path.dirname(cale)
		if not os.path.isdir(d):
			os.makedirs(d)
		with open(cale, "wb") as f:
			f.write(octeti)

	buf = io.BytesIO(date)
	if date[:4] == b"PK\x03\x04":
		with zipfile.ZipFile(buf) as z:
			membri = z.infolist()
			if len(membri) > MAX_FISIERE_ARHIVA:
				raise ValueError("prea multe fisiere")
			for m in membri:
				n = _nume_sigur(m.filename)
				if not n or m.filename.endswith("/"):
					continue
				if m.file_size > MAX_ARHIVA:
					raise ValueError("fisier prea mare")
				scrie(os.path.join(dest, n), z.read(m))
	else:
		with tarfile.open(fileobj=buf, mode="r:*") as t:
			n_fis = 0
			for m in t:
				n_fis += 1
				if n_fis > MAX_FISIERE_ARHIVA:
					raise ValueError("prea multe fisiere")
				if not m.isfile():
					continue
				n = _nume_sigur(m.name)
				if not n:
					continue
				if m.size > MAX_ARHIVA:
					raise ValueError("fisier prea mare")
				f = t.extractfile(m)
				if f is not None:
					scrie(os.path.join(dest, n), f.read())
	return gaseste_lista(dest)


def gaseste_lista(dest):
	"""Dosarul (cel mai putin adanc) care are lamedb sau bouquets.tv."""
	cel_mai_bun = None
	for rad, dosare, fisiere in os.walk(dest):
		if "lamedb" in fisiere or "bouquets.tv" in fisiere or "lamedb5" in fisiere:
			adanc = rad.count(os.sep)
			if cel_mai_bun is None or adanc < cel_mai_bun[0]:
				cel_mai_bun = (adanc, rad)
	if cel_mai_bun is None:
		return None
	rad = cel_mai_bun[1]
	if "lamedb" not in os.listdir(rad) and "lamedb5" in os.listdir(rad):
		# o lista numai cu lamedb5: se citeste la fel (parserul formatului 5)
		with open(os.path.join(rad, "lamedb5"), "rb") as f:
			date = f.read()
		with open(os.path.join(rad, "lamedb"), "wb") as f:
			f.write(date)
	return rad


def ce_are_arhiva(director):
	"""Ce se poate importa dintr-un dosar: {"servicii": n, "transpondere": n, "buchete": [(id, nume, n, radio)]}."""
	d = D.citeste_dosar(director, None, "/nu-exista")
	buchete = []
	for rad in ("bouquets.tv", "bouquets.radio"):
		r = d.buchete.get(rad)
		if r is None:
			continue
		for i in r.intrari:
			b = d.buchete.get(i.fisier) if i.fel == "subbuchet" else None
			if b is not None:
				n = sum(1 for j in b.intrari if j.fel in ("canal", "flux", "alternative", "altul"))
				buchete.append((b.id, D.fara_mod(b.nume) or b.id, n, b.radio))
	return {"servicii": len(d.lamedb.servicii), "transpondere": len(d.lamedb.transpondere), "buchete": buchete}


def arhiva_listei(s, fel="tar.gz", sateliti=D.SATELITI):
	"""Lista de acum (din editor, cu schimbarile nesalvate) ca arhiva cu etc/enigma2 si etc/tuxbox/satellites.xml,
	cum o citesc programele de pe calculator. -> octeti."""
	fisiere = s.text_fisiere()
	extra = {}
	try:
		with open(sateliti, "rb") as f:
			extra["etc/tuxbox/satellites.xml"] = f.read()
	except (IOError, OSError):
		pass
	buf = io.BytesIO()
	acum = time.time()
	if fel == "zip":
		with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
			for nume, date in sorted(fisiere.items()):
				z.writestr("etc/enigma2/" + nume, date)
			for nume, date in extra.items():
				z.writestr(nume, date)
	else:
		with tarfile.open(fileobj=buf, mode="w:gz") as t:
			for nume, date in sorted(list(("etc/enigma2/" + k, v) for k, v in fisiere.items()) + list(extra.items())):
				ti = tarfile.TarInfo(nume)
				ti.size = len(date)
				ti.mtime = acum
				ti.mode = 0o644
				t.addfile(ti, io.BytesIO(date))
	return buf.getvalue()
