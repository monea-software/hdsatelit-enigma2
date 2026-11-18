# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""oscam.srvid2 facut din lista de canale a receptorului, pentru modulul de acces ales. Doar in imaginea HDSatelit.

De ce (MGR/PLAN-078 punctul 5): modulele din familia OSCam (OSCam, OSCam-emu, -smod, Retuned; NCam cu ncam.srvid2) scriu numele
canalului in jurnal, in interfata lor web si in ecranul Informatii despre decriptare numai daca au fisierul srvid2 (sau srvid);
altfel arata unknown. Managerii de module ai altora il descarca de pe internet; aici il facem din lista de canale a receptorului
(lamedb: SID, CAID-urile tinute la cautare, numele, furnizorul), fara nicio sursa din afara.

Reguli:
  - numai in dosarul de configurare al modulului ALES al fiecarui fel (Components/HdsModuleAcces.dosare_configurare), numai la
    modulele din familia OSCam: in dosar e <x>.conf si <x>.server sau <x>.user sau <x>.dvbapi; fisierul e <x>.srvid2;
  - fisierul omului nu se atinge niciodata: un <x>.srvid2 cu randuri de canale fara semnul nostru (MARCA) sau un <x>.srvid cu
    randuri de canale (srvid2 are intaietate fata de srvid, deci l-ar ascunde). Un <x>.srvid2 numai cu comentarii (cel gol pe
    care il scrie modulul singur cand nu are niciunul) nu e al omului si se inlocuieste;
  - al nostru (cu MARCA) se reface numai cand lista de canale sau buchetele s-au schimbat (AMPRENTA din capul lui) si numai
    daca iese altfel; scrierea dintr-o bucata (fisier nou langa el, apoi os.replace);
  - cel mult RANDURI_MAXIM randuri (modulul avertizeaza peste 2000: procesor si timpi de raspuns mai mari), intai canalele
    din buchetele omului, in ordinea lor, apoi restul din lamedb; numai canalele cu CAID-uri (un rand fara CAID opreste
    citirea fisierului in modul); o pereche SID + CAID-uri o singura data (prima castiga);
  - campurile (nume, tip, pozitia, furnizor) fara | si fara caractere de control, scurtate pe granita unei litere, impreuna
    sub 128 de octeti (bufferul din init_srvid al modulului);
  - modulul citeste fisierul la pornire, deci numele apar de la urmatoarea pornire a modulului (nu-l repornim noi);
  - se face pe un fir, la INTARZIERE secunde dupa pornirea interfetei (dupa lucrul greu de la pornire), cu pauze scurte in
    citirea listei; in jurnalul enigma2 numai dosarul si cate randuri, niciun nume de canal.
Modulul nu importa enigma: probele de pe PC il incarca singur, cu dosare de proba."""
import hashlib
import io
import os
import posixpath
import re
import threading
import time

DOSAR_ENIGMA = "/etc/enigma2"
LAMEDB = ("lamedb", "lamedb5")          # in ordinea preferintei
FISIERE_BUCHETE = ("bouquets.tv", "bouquets.radio")
RANDURI_MAXIM = 2000
NUME_OCTETI = 60
FURNIZOR_OCTETI = 40
INTARZIERE = 300.0                      # secunde dupa pornirea interfetei
PAUZA_LA = 2000                         # servicii citite intre doua pauze scurte (firul enigma2 lucreaza intre timp)
PAUZA = 0.005
LAMEDB_MAXIM = 32 * 1024 * 1024
BUCHET_MAXIM = 4 * 1024 * 1024
SRVID_MAXIM = 8 * 1024 * 1024
TIPURI_RADIO = (2, 10)
SEMNE_FAMILIE = (".server", ".user", ".dvbapi")
MARCA = "# srvid2 facut de receptor din lista de canale; se reface singur cand se schimba lista"
_AMPRENTA = re.compile(r"^# amprenta: ([0-9a-f]{16})$", re.M)
_CONTROL = re.compile(u"[\u0000-\u001f\u007f-\u009f|]")
_BUCHET = re.compile(r'FROM BOUQUET "([^"/]+)"')
_SERVICIU = re.compile(r"^#SERVICE 1:0:([0-9a-fA-F]+):([0-9a-fA-F]+):([0-9a-fA-F]+):([0-9a-fA-F]+):([0-9a-fA-F]+):", re.M)


def _jurnal(text):
	print("[HdsSrvid] %s" % text)


def _taie(text, octeti):
	"""text fara | si fara caractere de control, cel mult `octeti` octeti UTF-8, taiat pe granita unei litere"""
	text = _CONTROL.sub(" ", text or "").strip()
	text = re.sub(r"\s+", " ", text)
	b = text.encode("utf-8")
	if len(b) <= octeti:
		return text
	return b[:octeti].decode("utf-8", "ignore").rstrip()


def pozitia(ns):
	"""descrierea randului: pozitia satelitului din spatiul de nume (19.2E, 30.0W) sau DVB-T / DVB-C"""
	p = (ns >> 16) & 0xFFFF
	if p == 0xEEEE:
		return "DVB-T"
	if p == 0xFFFF:
		return "DVB-C"
	if p > 1800:
		return "%.1fW" % ((3600 - p) / 10.0)
	return "%.1fE" % (p / 10.0)


def _caids(date):
	rez = []
	furnizor = ""
	for camp in date.split(","):
		if camp.startswith("p:"):
			furnizor = camp[2:]
		elif camp.startswith("C:"):
			try:
				c = int(camp[2:], 16)
			except ValueError:
				continue
			if 0 < c <= 0xFFFF and c not in rez:
				rez.append(c)
	return furnizor, rez


def servicii(text, pauza=None):
	"""Serviciile din textul unui lamedb (formatul 4 sau 5): [(sid, ns, tsid, onid, tip, nume, furnizor, [caid])], in ordinea
	din fisier. Un rand stricat se sare. `pauza()` se cheama la fiecare PAUZA_LA servicii."""
	if isinstance(text, bytes):
		text = text.decode("utf-8", "replace")
	randuri = text.replace("\r", "").split("\n")
	m = re.match(r"^eDVB services /(\d+)/", randuri[0] if randuri else "")
	if not m:
		return []
	rez = []
	if m.group(1) == "5":
		for rand in randuri[1:]:
			if not rand.startswith("s:"):
				continue
			poz = rand.find(',"')
			sf = rand.find('"', poz + 2) if poz >= 0 else -1
			if sf < 0:
				continue
			parti = rand[2:poz].split(":")
			try:
				sid, ns, tsid, onid = (int(x, 16) for x in parti[:4])
				tip = int(parti[4])
			except (ValueError, IndexError):
				continue
			furnizor, caids = _caids(rand[sf + 1:].lstrip(","))
			rez.append((sid, ns, tsid, onid, tip, rand[poz + 2:sf], furnizor, caids))
			if pauza and len(rez) % PAUZA_LA == 0:
				pauza()
		return rez
	try:
		i = randuri.index("services") + 1
	except ValueError:
		return []
	n = len(randuri)
	while i + 2 < n and randuri[i] != "end":
		cheie, nume, date = randuri[i], randuri[i + 1], randuri[i + 2]
		i += 3
		parti = cheie.split(":")
		try:
			sid, ns, tsid, onid = (int(x, 16) for x in parti[:4])
			tip = int(parti[4])
		except (ValueError, IndexError):
			continue
		furnizor, caids = _caids(date)
		rez.append((sid, ns, tsid, onid, tip, nume, furnizor, caids))
		if pauza and len(rez) % PAUZA_LA == 0:
			pauza()
	return rez


def _citeste(cale, maxim):
	with io.open(cale, "rb") as f:
		return f.read(maxim).decode("utf-8", "replace")


def fisiere_buchete(dosar=DOSAR_ENIGMA):
	"""Caile buchetelor omului, in ordinea din bouquets.tv si bouquets.radio (numai fisiere din dosar, fara cai)"""
	rez = []
	for nume in FISIERE_BUCHETE:
		try:
			text = _citeste(posixpath.join(dosar, nume), BUCHET_MAXIM)
		except (IOError, OSError):
			continue
		for b in _BUCHET.findall(text):
			cale = posixpath.join(dosar, b)
			if cale not in rez and os.path.isfile(cale):
				rez.append(cale)
	return rez


def din_buchete(dosar=DOSAR_ENIGMA):
	"""(sid, tsid, onid) ale canalelor din buchetele omului, in ordinea lor, fiecare o data"""
	rez, vazute = [], set()
	for cale in fisiere_buchete(dosar):
		try:
			text = _citeste(cale, BUCHET_MAXIM)
		except (IOError, OSError):
			continue
		for _tip, sid, tsid, onid, _ns in _SERVICIU.findall(text):
			cheie = (int(sid, 16), int(tsid, 16), int(onid, 16))
			if cheie not in vazute:
				vazute.add(cheie)
				rez.append(cheie)
	return rez


def randuri(lista, ordine=(), maxim=RANDURI_MAXIM):
	"""Randurile fisierului (fara antet): intai canalele din `ordine` ((sid, tsid, onid) ale buchetelor), apoi restul, numai cu
	CAID-uri, o pereche SID + CAID-uri o singura data, cel mult `maxim`."""
	dupa_cheie = {}
	for s in lista:
		dupa_cheie.setdefault((s[0], s[2], s[3]), s)
	alese, vazute = [], set()
	for s in [dupa_cheie[k] for k in ordine if k in dupa_cheie] + list(lista):
		sid, ns, _tsid, _onid, tip, nume, furnizor, caids = s
		if not caids or not 0 < sid <= 0xFFFF:
			continue
		pereche = (sid, tuple(caids))
		if pereche in vazute:
			continue
		vazute.add(pereche)
		alese.append("%04X:%s|%s|%s|%s|%s" % (sid, ",".join("%04X" % c for c in caids),
			_taie(nume, NUME_OCTETI) or "%04X" % sid, "Radio" if tip in TIPURI_RADIO else "TV", pozitia(ns),
			_taie(furnizor, FURNIZOR_OCTETI) or "-"))
		if len(alese) >= maxim:
			break
	return alese


def amprenta(dosar=DOSAR_ENIGMA):
	"""amprenta listei si a buchetelor (marimea si ora fiecarui fisier): alta = lista s-a schimbat"""
	h = hashlib.sha1()
	for cale in [posixpath.join(dosar, n) for n in LAMEDB + FISIERE_BUCHETE] + fisiere_buchete(dosar):
		try:
			st = os.stat(cale)
		except OSError:
			continue
		h.update(("%s %d %d\n" % (posixpath.basename(cale), st.st_size, int(st.st_mtime))).encode("utf-8"))
	return h.hexdigest()[:16]


def continut(dosar=DOSAR_ENIGMA, pauza=None):
	"""(textul fisierului, cate randuri) din lista de canale a receptorului; (None, 0) fara lamedb"""
	for nume in LAMEDB:
		cale = posixpath.join(dosar, nume)
		if os.path.isfile(cale):
			try:
				text = _citeste(cale, LAMEDB_MAXIM)
			except (IOError, OSError):
				continue
			lista = servicii(text, pauza)
			if lista:
				break
	else:
		return None, 0
	r = randuri(lista, din_buchete(dosar))
	antet = [MARCA, "# amprenta: %s" % amprenta(dosar),
		"# SID:CAID-uri|nume|tip|pozitie|furnizor; cel mult %d canale, intai cele din buchete" % RANDURI_MAXIM, ""]
	return "\n".join(antet + r) + "\n", len(r)


def _randuri_date(text):
	return [r for r in text.splitlines() if r.strip() and not r.lstrip().startswith("#")]


def prefix_familie(dosar, modul=None):
	"""<x> pentru care dosarul are <x>.conf si unul din <x>.server / .user / .dvbapi (familia OSCam), sau None. Intr-un dosar
	comun mai multor module (/etc/tuxbox/config cu oscam.conf si ncam.conf) se alege <x> cu care incepe numele modulului
	(oscam-emu -> oscam, ncam -> ncam), cel mai lung; cand nu se poate hotari (mai multe si niciunul nu se potriveste), None."""
	try:
		nume = sorted(os.listdir(dosar))
	except OSError:
		return None
	candidati = [n[:-5] for n in nume if n.endswith(".conf") and len(n) > 5 and
		any((n[:-5] + s) in nume for s in SEMNE_FAMILIE)]
	if modul:
		potrivite = [x for x in candidati if modul.lower().startswith(x.lower())]
		if potrivite:
			return max(potrivite, key=len)
	return candidati[0] if len(candidati) == 1 else None


def al_omului(dosar, x):
	"""motivul pentru care nu scriem (fisierul omului), sau None"""
	for nume, al_nostru_permis in ((x + ".srvid2", True), (x + ".srvid", False)):
		cale = posixpath.join(dosar, nume)
		if not os.path.isfile(cale):
			continue
		try:
			text = _citeste(cale, SRVID_MAXIM)
		except (IOError, OSError):
			return nume
		if al_nostru_permis and text.startswith(MARCA):
			continue
		if _randuri_date(text):
			return nume
	return None


def scrie(dosar, dosar_enigma=DOSAR_ENIGMA, pauza=None, modul=None):
	"""Pune <x>.srvid2 in `dosar` (al modulului cu sufixul `modul`) cand se cuvine. Intoarce ('scris', n), ('la_zi', 0),
	('al_omului', fisier), ('alt_modul', '') sau ('fara_lista', 0)."""
	x = prefix_familie(dosar, modul)
	if x is None:
		return "alt_modul", ""
	cale = posixpath.join(dosar, x + ".srvid2")
	motiv = al_omului(dosar, x)
	if motiv:
		# omul a pus intre timp <x>.srvid cu canale: al nostru (srvid2, cu intaietate in modul) l-ar ascunde, deci iese
		if motiv == x + ".srvid" and os.path.isfile(cale):
			try:
				if _citeste(cale, len(MARCA) + 1).startswith(MARCA):
					os.remove(cale)
			except (IOError, OSError):
				pass
		return "al_omului", motiv
	vechi = ""
	if os.path.isfile(cale):
		try:
			vechi = _citeste(cale, SRVID_MAXIM)
		except (IOError, OSError):
			vechi = ""
	m = _AMPRENTA.search(vechi)
	if vechi.startswith(MARCA) and m and m.group(1) == amprenta(dosar_enigma):
		return "la_zi", 0
	text, n = continut(dosar_enigma, pauza)
	if text is None or not n:
		return "fara_lista", 0
	if text == vechi:
		return "la_zi", 0
	nou = cale + ".hds-nou"
	with io.open(nou, "w", encoding="utf-8", newline="\n") as f:
		f.write(text)
	os.chmod(nou, 0o644)
	os.replace(nou, cale)
	return "scris", n


def dosare_alese(H=None, sistem=None):
	"""[(dosar, sufixul modulului)] ale modulelor alese (cate unul pe fel), cu dosarul existent"""
	if H is None:
		from Components import HdsModuleAcces as H
	sistem = sistem or H.SistemAcces()
	stari = H.feluri_de_aratat(sistem)
	alese = set()
	for st in stari:
		e = st.ales_emulator()
		if e is not None:
			alese.add((st.fel, e.sufix))
	rez = []
	for d in H.dosare_configurare(sistem, stari):
		if (d.get("fel"), d.get("sufix")) in alese and d.get("exista") and d.get("dosar"):
			cale = sistem.cale(d["dosar"].rstrip("/") or "/")
			if cale not in [c for c, _s in rez]:
				rez.append((cale, d["sufix"]))
	return rez


def asigura(H=None, dosar_enigma=DOSAR_ENIGMA, pauza=None):
	"""srvid2 in dosarul fiecarui modul ales; [(dosar, rezultat)]"""
	pauza = pauza or (lambda: time.sleep(PAUZA))
	rez = []
	for dosar, modul in dosare_alese(H):
		try:
			r = scrie(dosar, dosar_enigma, pauza, modul)
		except (IOError, OSError, ValueError) as e:
			r = ("eroare", e.__class__.__name__)
		rez.append((dosar, r))
		_jurnal("%s: %s %s" % (dosar, r[0], r[1]))
	return rez


def porneste(intarziere=INTARZIERE):
	"""Din pornirea interfetei (HdsModuleLipsa.porneste): asigura() pe un fir, dupa `intarziere` secunde. Nu arunca."""
	def lucreaza():
		time.sleep(intarziere)
		try:
			asigura()
		except Exception as e:
			_jurnal("eroare %s" % e.__class__.__name__)
	try:
		fir = threading.Thread(target=lucreaza, name="hds-srvid2")
		fir.daemon = True
		fir.start()
	except Exception as e:
		_jurnal("firul nu a pornit: %s" % e.__class__.__name__)
