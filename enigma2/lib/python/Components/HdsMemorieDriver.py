# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsMemorieDriver.py: cea mai mare bucata libera din memoria vmalloc a nucleului si repornirea intreaga a
# receptorului, nevazuta, in standby, cand bucata e prea mica.
#
# De ce: la fiecare oprire a procesului enigma2 driverul video (HiSilicon) pierde o zona de 4 MB din vmalloc, pana la
# repornirea receptorului. Demonul platformei (showiframe) cere la pornirea lui 33 MB dintr-o bucata (34611200 octeti,
# lib/dvb/hdspazavideo.h); fara ea poza posturilor de radio si filmele nu mai merg pana la repornirea receptorului.
# Repornirea interfetei nu ajuta (zonele raman pierdute); repornirea receptorului da.
#
# MASURATOAREA (masoara, bucataLibera): golurile dintre zonele ocupate din /proc/vmallocinfo, numai in intervalul
# VMALLOC al nucleului. vmallocinfo listeaza si modulele (sub lowmem; pe Viper 4K V20 0xbe800000-0xbfe00000), iar golul
# de acolo pana la inceputul intervalului (~530 MB) nu e memorie in care se poate mapa ceva. Intervalul: sfarsitul =
# VMALLOC_END al nucleelor ARM pe 32 de biti (0xff800000, ca in "Virtual kernel memory layout" de la pornire) sau, pe
# alte arhitecturi ori cand o intrare trece de el, cea mai mare adresa listata; inceputul = sfarsitul - VmallocTotal
# (/proc/meminfo). VmallocChunk nu ajuta: nucleul 4.4 il scrie 0. Zonele eliberate dar inca necuratate de nucleu nu
# sunt listate; nucleul le curata inainte sa refuze o mapare, deci se socotesc libere. O singura citire nu se crede cand
# iese sub prag (Esantioane): cu televizorul pornit bucata scade des pentru o clipa, asa ca sub prag se citeste la
# fiecare bataie a paznicului si se crede numai dupa un minut de citiri sub prag la rand; peste prag o citire pe minut.
#
# PRAG_KB (40 MB): sub atat bucata nu mai ajunge sigur (showiframe cere 33 MB; restul e marja).
#
# Omul nu vede niciodata un mesaj despre aceasta memorie: valoarea apare numai in ecranul "Memorie" din informatiile
# despre sistem, in ecranul si pagina paznicului (stare()) si in jurnalul paznicului.
#
# a) Dupa o actualizare (repornirea de dupa instalare din Screens/HdsActualizari.py, POST /api/actualizari-reporneste
#    si actualizarea rapida din HdsWebControl/actualizari_web.py): codRepornireDupaActualizare() da 2 (receptorul
#    intreg) cand memoria e sub prag si nu merge nicio inregistrare, altfel 3 (numai interfata, ca inainte; cu o
#    inregistrare in curs TryQuitMainloop intreaba si asteapta ca pana acum). Calea e tot TryQuitMainloop.
# b) Repornirea in standby (config.hds_paznic.repornire_noapte, Da din fabrica; numele setarii a ramas de cand se facea
#    numai noaptea): oricand receptorul sta in standby fara intrerupere de cel putin STANDBY_MINIM_S (o iesire scurta
#    din standby nu porneste nimic), cu memoria sub prag sau cu memoria pozelor si a filmelor lipsa (starea paznicului,
#    memorie_es=lipsa; crezuta numai daca receptorul a fost treaz in aceasta pornire, adica exista CALE_MINIM: dupa o
#    pornire direct in standby demonul nu are inca maparea, iar un paznic mai vechi o scrie lipsa), fara inregistrari
#    in curs sau in urmatoarele INREGISTRARE_CURAND_S, fara intrebare de repornire
#    pe ecran, fara lucrari in fundal si fara lucrarile imaginii (lucrariImagine), numai dupa UPTIME_MINIM_S de la
#    pornire si cu ceasul potrivit. Paza impotriva repornirilor in lant (CALE_NOAPTE, pe memoria interna): cel mult o
#    data pe pornire a receptorului (boot_id-ul de la cerere) si cel putin PAUZA_S intre doua reporniri de aici (un ceas
#    in urma fata de ora scrisa = prea devreme). Valoarea folosita e cea mai mica dintre masuratoarea de acum si cea
#    mai mica masurata in afara standby-ului in aceasta pornire a receptorului (CALE_MINIM, scrisa de bataie, pasMasuratoare):
#    in standby decodorul isi elibereaza maparile (pe Viper 4K V20 62 MB in standby fata de 45,7 MB cu televizorul
#    pornit, in aceeasi pornire), deci in standby masuratoarea iese mai buna decat cu televizorul pornit. Inainte de
#    repornire se scrie in CALE_NOAPTE semnul standby; la pornirea urmatoare (porneste), cu semnul proaspat, receptorul
#    intra in standby ca dupa un temporizator. Televizorul nu se aprinde: la pornire nu pleaca nimic pe CEC spre el, iar
#    intrarea in standby trimite <Standby> numai cand receptorul era sursa activa (Components/HdsStandbyTv.py).
# c) Filmul (sau canalul de pe internet) care nu porneste din lipsa memoriei decodorului (servicemp3: felul "decodor",
#    maparea demonului platformei lipseste; Components/HdsFilmRedare.py): playerul cere refacereFilm(). Cu aceleasi paze
#    ca b), fara cele ale standby-ului (hotarareFilm: receptorul treaz, pornit de cel putin FILM_UPTIME_MINIM_S, ceasul
#    potrivit, o data pe pornire si PAUZA_S de la ultima repornire de aici, oricare a fost, fara inregistrari acum sau
#    in urmatoarele INREGISTRARE_CURAND_S, fara intrebare de repornire, fara lucrari; maparea chiar lipsa, nu necitita),
#    receptorul se reporneste intreg (TryQuitMainloop 2, dupa FILM_ARATARE_S cu fraza scurta pe ecran) si dupa pornire
#    porneste filmul (CALE_FILM, citit o data de porneste(); filmul in playerul de filme, canalul pe locul lui), dupa ce
#    demonul isi are maparea (cel mult FILM_ASTEPTARE_S). Cand maparea e deja la loc, filmul se porneste din nou, fara
#    repornire. Nicio repornire care nu se poate face nu se spune ca defect: pe ecran ramane "Filmul nu poate porni acum."
#    Setarea repornirii in standby nu opreste c): omul a cerut chiar acum filmul, iar fara repornire el nu porneste.
# Fiecare repornire intreaga ceruta de aici scrie un rand in jurnalul paznicului (motivul si valoarea masurata).
#
# PROBA pe receptor (fara sa se strice memoria): CALE_PROBA (/tmp, deci dispare singur la repornirea receptorului) cu
# randuri "prag_mb=N" (pragul de proba, 1-1024), "uptime_min_s=N" (cat trebuie sa fi mers receptorul inainte de
# repornirea in standby sau pentru un film, 0-86400), "standby_min_s=N" (cat trebuie sa stea in standby, 0-3600) si
# "uscat=1" (proba uscata: unde s-ar reporni receptorul se scrie numai randul "PROBA uscata" in jurnalul paznicului;
# dupa o actualizare se reporneste atunci numai interfata, iar in standby si pentru film nimic, o data pe pornirea
# interfetei, respectiv la fiecare film). Nimic altceva.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import json
import os
import time

PRAG_KB = 40 * 1024             # sub atat bucata nu mai ajunge sigur (showiframe cere 34611200 octeti dintr-o bucata)
MARIME_ES = 34611200            # memoria partajata a driverului video cu showiframe (lib/dvb/hdspazavideo.h)
VMALLOC_END_ARM32 = 0xff800000  # arch/arm/include/asm/pgtable.h; Viper 4K V20: "vmalloc : 0xe0800000 - 0xff800000"
VARSTA_MASURATOARE_S = 60
ESANTION_S = 60                 # peste prag: o citire pe minut (o citire a lui vmallocinfo ia ~20 ms pe Viper 4K V20)
CONFIRMARE_S = 10               # sub prag: o citire la fiecare bataie a paznicului
CONFIRMARI = 6                  # cate citiri sub prag la rand (un minut) pana se crede ca memoria e sub prag

CALE_VMALLOCINFO = "/proc/vmallocinfo"
CALE_MEMINFO = "/proc/meminfo"
CALE_BOOT_ID = "/proc/sys/kernel/random/boot_id"
CALE_UPTIME = "/proc/uptime"
CALE_JURNAL = "/home/root/hds-watchdog.log"     # jurnalul paznicului (HdsPaznic.CALE_JURNAL)
CALE_MINIM = "/tmp/hds-memorie-minim"           # "boot_id liber_kb": cea mai mica masuratoare in afara standby-ului
CALE_NOAPTE = "/home/root/hds-repornire-noapte"  # ultima repornire in standby si semnul standby (JSON)
CALE_PROBA = "/tmp/hds-memorie-proba"

COD_RECEPTOR = 2                # TryQuitMainloop: repornirea receptorului (enigma2.sh: /sbin/reboot)
COD_INTERFATA = 3               # TryQuitMainloop: repornirea interfetei

STANDBY_MINIM_S = 5 * 60        # cat sta receptorul in standby, fara intrerupere, inainte de repornire
INREGISTRARE_CURAND_S = 30 * 60  # nicio inregistrare care incepe in atatea secunde
UPTIME_MINIM_S = 2 * 3600       # nicio repornire in standby mai devreme de atat de la pornirea receptorului
PAUZA_S = 6 * 3600              # cel putin atat intre doua reporniri in standby (paza impotriva repornirilor in lant)
STANDBY_PROASPAT_S = 30 * 60    # semnul standby mai vechi de atat (ceasul de perete) nu se mai ia in seama
CEAS_IN_URMA_S = 6 * 3600       # cu alt boot_id: cat de in urma poate fi ceasul de dupa pornire (fake-hwclock)
SEMN_RAMAS_S = 5 * 60           # semnul standby din aceeasi pornire, mai vechi de atat: repornirea nu s-a facut
VERIFICARE_S = 60               # cat de des se uita bataia la repornirea in standby (standby-ul se urmareste la fiecare bataie)
REPORNIRE_STANDBY_IMPLICIT = True

CALE_FILM = "/home/root/hds-film-dupa-repornire"  # filmul de pornit dupa repornirea pentru el (JSON)
FILM_UPTIME_MINIM_S = 5 * 60    # c): nicio repornire pentru film mai devreme de atat de la pornirea receptorului
FILM_ARATARE_S = 3              # cat sta fraza scurta pe ecran inainte de repornire
FILM_ASTEPTARE_S = 90           # dupa pornire: cat se asteapta maparea demonului inainte de a porni filmul oricum
FILM_PAS_MS = 1000              # cat de des se uita, dupa pornire, dupa mapare si dupa bara principala
REINCERCARE_S = 60              # acelasi film pornit din nou fara repornire: cel mult o data in atat
FAPTA_REPORNESTE = "reporneste"
FAPTA_REINCEARCA = "reincearca"
FAPTA_NIMIC = "nimic"
MOTIV_STANDBY = "standby"       # "motiv" in CALE_NOAPTE: de ce s-a facut ultima repornire de aici (lipsa = standby)
MOTIV_FILM = "film"


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _log(text):
	print("[HdsMemorieDriver] %s" % text)


# ---------------------------------------------------------------- masuratoarea

def zone(date):
	"""Zonele listate in vmallocinfo (bytes sau text): [(inceput, sfarsit)], ordonate. Randurile stricate se sar."""
	if isinstance(date, bytes):
		date = date.decode("ascii", "replace")
	rez = []
	for rand in date.splitlines():
		p = rand.split()
		if len(p) < 2:
			continue
		a, semn, b = p[0].partition("-")
		if not semn:
			continue
		try:
			a, b = int(a, 16), int(b, 16)
			int(p[1])
		except ValueError:
			continue
		if b > a:
			rez.append((a, b))
	rez.sort()
	return rez


def vmallocTotalKb(date):
	"""VmallocTotal din /proc/meminfo (kB), sau None."""
	if isinstance(date, bytes):
		date = date.decode("ascii", "replace")
	for rand in date.splitlines():
		if rand.startswith("VmallocTotal:"):
			try:
				return int(rand.split()[1])
			except (IndexError, ValueError):
				return None
	return None


def esteArm32(masina):
	m = (masina or "").lower()
	return m.startswith("arm") and not m.startswith("arm64")


def intervalVmalloc(zone_, total_kb, masina):
	"""(inceput, sfarsit) al intervalului VMALLOC, sau None fara zone sau fara VmallocTotal."""
	if not zone_ or not total_kb or total_kb <= 0:
		return None
	sus = max(b for a, b in zone_)
	sfarsit = VMALLOC_END_ARM32 if (esteArm32(masina) and sus <= VMALLOC_END_ARM32) else sus
	inceput = sfarsit - int(total_kb) * 1024
	if inceput < 0:
		inceput = 0
	return inceput, sfarsit


def bucataLibera(date_vmalloc, date_meminfo, masina):
	"""Cea mai mare bucata libera din intervalul VMALLOC. -> {'liber_kb', 'inceput', 'sfarsit', 'total_kb', 'zone',
	'es'} (es = cate mapari de MARIME_ES sunt listate) sau None cand nu se poate socoti. Nu arunca."""
	try:
		z = zone(date_vmalloc)
		total = vmallocTotalKb(date_meminfo)
		iv = intervalVmalloc(z, total, masina)
		if iv is None:
			return None
		inceput, sfarsit = iv
		gol = 0
		capat = inceput
		n = 0
		for a, b in z:
			if b <= inceput or a >= sfarsit:
				continue
			n += 1
			a = max(a, inceput)
			if a > capat:
				gol = max(gol, a - capat)
			capat = max(capat, min(b, sfarsit))
		if sfarsit > capat:
			gol = max(gol, sfarsit - capat)
		if not n:
			return None
		text = date_vmalloc.decode("ascii", "replace") if isinstance(date_vmalloc, bytes) else date_vmalloc
		es = sum(1 for r in text.splitlines() if len(r.split()) > 1 and r.split()[1] == str(MARIME_ES))
		return {"liber_kb": gol // 1024, "inceput": inceput, "sfarsit": sfarsit, "total_kb": total, "zone": n, "es": es}
	except Exception as e:
		_log("masuratoarea: %r" % (e,))
		return None


def _citeste(cale, maxim):
	with open(cale, "rb") as f:
		return f.read(maxim)


def masoara(cale_vmalloc=None, cale_meminfo=None, masina=None):
	"""Masuratoarea de acum, citita din /proc. -> dict (bucataLibera) sau None. Nu arunca."""
	try:
		date_v = _citeste(cale_vmalloc or CALE_VMALLOCINFO, 4 * 1024 * 1024)
		date_m = _citeste(cale_meminfo or CALE_MEMINFO, 16384)
	except (IOError, OSError) as e:
		_log("nu pot citi memoria nucleului: %s" % e)
		return None
	if masina is None:
		try:
			masina = os.uname()[4]
		except (AttributeError, OSError):
			masina = ""
	return bucataLibera(date_v, date_m, masina)


_cache = {"ora": None, "m": None}


def masuratoare(ceas=None, cititor=None):
	"""Masuratoarea, refacuta cel mult o data la VARSTA_MASURATOARE_S (ceasul monoton)."""
	ceas = ceas or time.monotonic
	acum = ceas()
	if _cache["ora"] is None or acum - _cache["ora"] >= VARSTA_MASURATOARE_S or acum < _cache["ora"]:
		_cache["m"] = (cititor or masoara)()
		_cache["ora"] = acum
	return _cache["m"]


class Esantioane(object):
	"""Masuratoarea crezuta, din citirile facute la bataia paznicului. O singura citire nu ajunge: cu televizorul pornit
	bucata cea mai mare scade des pentru o clipa (o mapare trecatoare a driverelor, sau vmallocinfo citit pe bucati cat
	se schimba; pe Viper 4K V20 o citire din sapte, pana la jumatate). Peste prag o citire se crede pe loc si se reface
	o data la ESANTION_S; sub prag se citeste la fiecare bataie (CONFIRMARE_S) si se crede numai dupa CONFIRMARI citiri
	sub prag la rand (un minut), cu valoarea cea mai mare dintre ele. La trecerea in standby sau din standby totul se ia
	de la capat (decodorul isi elibereaza sau isi reface maparile)."""

	def __init__(self, ceas=None, masura=None, prag_=None):
		self.ceas = ceas or time.monotonic
		self.masura = masura or masoara
		self.prag = prag_ or prag
		self.standby = None
		self.ultima = None      # ceasul monoton al ultimei citiri
		self.sub = []           # citirile sub prag, la rand, inca necrezute (cel mult CONFIRMARI)
		self.buna = None        # masuratoarea crezuta in starea de acum (dict de la bucataLibera)

	def pas(self, standby):
		"""O bataie (10 s). -> masuratoarea crezuta acum, sau None. Nu arunca."""
		try:
			acum = self.ceas()
			standby = bool(standby)
			if standby != self.standby:
				self.standby, self.ultima, self.sub, self.buna = standby, None, [], None
			if self.ultima is not None and 0 <= acum - self.ultima < (CONFIRMARE_S if self.sub else ESANTION_S):
				return self.buna
			self.ultima = acum
			m = self.masura()
			if not m or m.get("liber_kb") is None:
				return self.buna
			if not subPrag(m, self.prag()):
				self.sub, self.buna = [], m
			else:
				self.sub = (self.sub + [m])[-CONFIRMARI:]
				if len(self.sub) >= CONFIRMARI:
					self.buna = max(self.sub, key=lambda x: x["liber_kb"])
		except Exception as e:
			_log("citirea memoriei: %r" % (e,))
		return self.buna

	def valoare(self, standby=None):
		"""Masuratoarea crezuta, numai daca e din starea ceruta (None = oricare)."""
		if standby is not None and bool(standby) != self.standby:
			return None
		return self.buna


_esantioane = [None]


def esantioane():
	if _esantioane[0] is None:
		_esantioane[0] = Esantioane()
	return _esantioane[0]


def proba(cale=None):
	"""Valorile de proba din CALE_PROBA: {'prag_kb', 'uptime_min_s', 'standby_min_s', 'uscat'}; numai ce e bine scris."""
	rez = {}
	try:
		with open(cale or CALE_PROBA, "r", encoding="utf-8") as f:
			text = f.read(512)
	except (IOError, OSError):
		return rez
	for rand in text.splitlines():
		cheie, semn, valoare = rand.partition("=")
		cheie, valoare = cheie.strip(), valoare.strip()
		if not semn:
			continue
		if cheie == "prag_mb" and valoare.isdigit() and 1 <= int(valoare) <= 1024:
			rez["prag_kb"] = int(valoare) * 1024
		elif cheie == "uptime_min_s" and valoare.isdigit() and int(valoare) <= 86400:
			rez["uptime_min_s"] = int(valoare)
		elif cheie == "standby_min_s" and valoare.isdigit() and int(valoare) <= 3600:
			rez["standby_min_s"] = int(valoare)
		elif cheie == "uscat" and valoare == "1":
			rez["uscat"] = True
	return rez


def prag(cale_proba=None):
	return proba(cale_proba).get("prag_kb", PRAG_KB)


def subPrag(m, prag_kb=None):
	"""True / False; None cand nu exista masuratoare (atunci nu se face nimic)."""
	if not m or m.get("liber_kb") is None:
		return None
	return m["liber_kb"] < (PRAG_KB if prag_kb is None else prag_kb)


def mb(kb):
	return int(kb) // 1024


# ---------------------------------------------------------------- textele (numai informatie, niciun mesaj)

def textValoare(liber_kb, prag_kb):
	"""Randul de stare (ecranul si pagina paznicului)."""
	return _("Memoria decodorului: cea mai mare bucată liberă are %d MB (prag %d MB).") % (mb(liber_kb), mb(prag_kb))


def textEliberare(activ):
	"""Ce se intampla cu memoria cand nu mai ajunge: dupa setarea repornirii in standby."""
	if activ:
		return _("Memoria decodorului se eliberează singură în standby.")
	return _("Memoria decodorului se eliberează la o repornire a receptorului.")


def stare(m=None, prag_kb=None, cale_proba=None, activ=None):
	"""Pentru ecranele si paginile de informatii: {'liber_kb', 'prag_kb', 'sub_prag', 'text', 'eliberare'}. Sub prag
	textul primeste si propozitia eliberarii. Nu arunca."""
	rez = {"liber_kb": -1, "prag_kb": PRAG_KB, "sub_prag": False, "text": "", "eliberare": ""}
	try:
		if m is None:
			# masuratoarea crezuta de la bataie; fara ea (inainte de primul minut), o citire de cel mult un minut
			m = esantioane().valoare() or masuratoare()
		p = prag(cale_proba) if prag_kb is None else prag_kb
		rez["prag_kb"] = p
		if not m:
			return rez
		rez["liber_kb"] = int(m["liber_kb"])
		rez["sub_prag"] = bool(subPrag(m, p))
		rez["text"] = textValoare(m["liber_kb"], p)
		if rez["sub_prag"]:
			rez["eliberare"] = textEliberare(activaStandby() if activ is None else activ)
			rez["text"] += " " + rez["eliberare"]
	except Exception as e:
		_log("starea: %r" % (e,))
	return rez


# ---------------------------------------------------------------- jurnalul paznicului

def scrieJurnal(text, cale=None, ceas=None):
	"""Un rand in jurnalul paznicului, in formatul lui ("AAAA-LL-ZZ HH:MM:SS text"). Nu arunca."""
	t = (ceas or time.time)()
	rand = "%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)), text)
	try:
		fd = os.open(cale or CALE_JURNAL, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
		try:
			os.write(fd, rand.encode("utf-8", "replace"))
		finally:
			os.close(fd)
		return True
	except (IOError, OSError) as e:
		_log("jurnalul paznicului: %s" % e)
		return False


def randJurnal(motiv, m, prag_kb, acum_kb=None, lipsa_es=False):
	"""acum_kb: masuratoarea din standby, cand valoarea folosita e cea mai mica din afara standby-ului. lipsa_es: memoria
	pozelor si a filmelor lipseste (starea paznicului)."""
	rand = "repornesc receptorul (%s): cea mai mare bucata libera din vmalloc %d KB, prag %d KB" % (
		motiv, int(m["liber_kb"]) if m else -1, int(prag_kb))
	if m and acum_kb is not None and int(acum_kb) != int(m["liber_kb"]):
		rand += " (cea mai mica in afara standby-ului; acum %d KB)" % int(acum_kb)
	if lipsa_es:
		rand += "; memoria pozelor si a filmelor lipseste"
	return rand


# ---------------------------------------------------------------- a) repornirea dupa o actualizare

def hotarareActualizare(m, prag_kb, inregistrari):
	"""COD_RECEPTOR cand memoria e sub prag si nu merge nicio inregistrare; altfel COD_INTERFATA (ca inainte)."""
	if inregistrari:
		return COD_INTERFATA
	if subPrag(m, prag_kb):
		return COD_RECEPTOR
	return COD_INTERFATA


def _inregistrariAcum(sesiune):
	"""Cate inregistrari merg acum (sesiunea enigma2); -1 cand nu se poate citi (atunci nu se reporneste intreg)."""
	nav = getattr(sesiune, "nav", None)
	if nav is None:
		try:
			import NavigationInstance
			nav = NavigationInstance.instance
		except ImportError:
			nav = None
	if nav is None:
		return -1
	try:
		return len(nav.getRecordings() or [])
	except Exception:
		return -1


_ultim = [COD_INTERFATA]


def ultimulCod():
	"""Codul dat de ultima chemare a lui codRepornireDupaActualizare (mesajul actualizarii rapide)."""
	return _ultim[0]


def codRepornireDupaActualizare(sesiune=None, m=None, prag_kb=None, inregistrari=None, jurnal=None):
	"""Codul pentru TryQuitMainloop dupa o actualizare instalata. Masuratoarea e citita acum (nu din cache). La
	COD_RECEPTOR scrie randul in jurnalul paznicului. Nu arunca: la orice eroare COD_INTERFATA."""
	try:
		if m is None:
			# masuratoarea crezuta din afara standby-ului (o clipa de memorie putina nu reporneste receptorul); fara ea,
			# o citire acum
			m = esantioane().valoare(False) or masoara()
		p = prag() if prag_kb is None else prag_kb
		if inregistrari is None:
			inregistrari = _inregistrariAcum(sesiune)
		cod = hotarareActualizare(m, p, inregistrari != 0)
		if cod == COD_RECEPTOR and proba().get("uscat"):
			(jurnal or scrieJurnal)("PROBA uscata: " + randJurnal("dupa actualizare", m, p) + "; repornesc numai interfata")
			_log("proba uscata dupa actualizare: as reporni receptorul, repornesc numai interfata")
			_ultim[0] = COD_INTERFATA
			return COD_INTERFATA
		_ultim[0] = cod
		if cod == COD_RECEPTOR:
			(jurnal or scrieJurnal)(randJurnal("dupa actualizare", m, p))
			_log("dupa actualizare: repornesc receptorul (%d KB liberi dintr-o bucata, prag %d KB)" % (m["liber_kb"], p))
		elif m is not None and subPrag(m, p):
			_log("dupa actualizare: memoria e sub prag, dar merge o inregistrare: numai interfata")
		return cod
	except Exception as e:
		_log("codul repornirii: %r" % (e,))
		_ultim[0] = COD_INTERFATA
		return COD_INTERFATA


def textRepornire(cod):
	if cod == COD_RECEPTOR:
		return _("Actualizarea s-a instalat. Receptorul se repornește acum, ca să elibereze memoria decodorului.")
	return _("Actualizarea s-a instalat. Interfața se repornește acum.")


# ---------------------------------------------------------------- cea mai mica masuratoare din afara standby-ului

def bootId(cale=None):
	try:
		with open(cale or CALE_BOOT_ID, "r", encoding="utf-8") as f:
			return f.read(64).strip() or "?"
	except (IOError, OSError):
		return "?"


def citesteMinim(cale=None, boot=None):
	"""Cea mai mica masuratoare (KB) facuta in afara standby-ului in aceasta pornire a receptorului, sau None."""
	try:
		with open(cale or CALE_MINIM, "r", encoding="utf-8") as f:
			b, liber = f.read(128).split()
		return int(liber) if b == (boot or bootId()) else None
	except (IOError, OSError, ValueError):
		return None


def noteazaMinim(liber_kb, cale=None, boot=None):
	"""Tine cea mai mica masuratoare din afara standby-ului (scrie numai cand scade). Nu arunca."""
	try:
		liber_kb = int(liber_kb)
		if liber_kb < 0:
			return
		vechi = citesteMinim(cale, boot)
		if vechi is not None and vechi <= liber_kb:
			return
		cale = cale or CALE_MINIM
		with open(cale + ".nou", "w", encoding="utf-8") as f:
			f.write("%s %d\n" % (boot or bootId(), liber_kb))
		os.replace(cale + ".nou", cale)
	except (IOError, OSError, ValueError, TypeError) as e:
		_log("cea mai mica masuratoare: %r" % (e,))


def pasMasuratoare(standby, cale_minim=None, boot=None, esant=None):
	"""Din bataia paznicului (10 s): citirile memoriei (Esantioane, si in standby, pentru repornire) si, in afara
	standby-ului, cea mai mica masuratoare crezuta din aceasta pornire. Nimic pe ecran. Nu arunca."""
	try:
		s = bool(standby())
		m = (esant or esantioane()).pas(s)
		if not s and m and m.get("liber_kb") is not None:
			noteazaMinim(m["liber_kb"], cale_minim, boot)
	except Exception as e:
		_log("cea mai mica masuratoare: %r" % (e,))


# ---------------------------------------------------------------- b) repornirea in standby

def initConfig():
	"""config.hds_paznic.repornire_noapte (in subsectiunea paznicului, cu setarile lui)."""
	from Components.config import config, ConfigYesNo
	from Components import HdsPaznic
	HdsPaznic.initConfig()
	if "repornire_noapte" not in config.hds_paznic.dict():
		config.hds_paznic.repornire_noapte = ConfigYesNo(default=REPORNIRE_STANDBY_IMPLICIT)


def activaStandby():
	try:
		initConfig()
		from Components.config import config
		return bool(config.hds_paznic.repornire_noapte.value)
	except Exception as e:
		_log("setarea repornirii in standby: %r" % (e,))
		return False


def hotarareStandby(activ, standby_s, local, acum, ultima, boot, uptime_s, m, prag_kb, inregistrari, urmatoarea,
		intrebare, lucrari, lipsa_es=False, standby_minim=None, uptime_minim=None):
	"""Repornirea in standby, fara efecte. standby_s = de cate secunde sta receptorul in standby fara intrerupere (None =
	treaz); local = time.localtime(acum); ultima = randul din CALE_NOAPTE ({} fara); boot = boot_id-ul de acum;
	lipsa_es = memoria pozelor si a filmelor lipseste, vazuta dupa ce receptorul a fost treaz in aceasta pornire.
	-> (True, "") sau (False, motivul scurt)."""
	if not activ:
		return False, "oprita din setari"
	if standby_s is None:
		return False, "receptorul nu e in standby"
	if standby_s < (STANDBY_MINIM_S if standby_minim is None else standby_minim):
		return False, "in standby de prea putin timp"
	if local.tm_year < 2024:
		return False, "ceasul nu e potrivit"
	ultima = ultima or {}
	if ultima.get("boot") and ultima.get("boot") == boot:
		return False, "o data pe pornire"
	try:
		ora = float(ultima.get("ora") or 0)
	except (TypeError, ValueError):
		ora = 0
	if ora > 0 and acum - ora < PAUZA_S:
		# si cu ceasul in urma fata de ora scrisa (dupa pornire, inainte de NTP): prea devreme
		return False, "alta repornire de curand"
	if uptime_s is None or uptime_s < (UPTIME_MINIM_S if uptime_minim is None else uptime_minim):
		return False, "pornit de prea putin timp"
	if not lipsa_es:
		if not m:
			return False, "memoria nu se poate masura"
		if not subPrag(m, prag_kb):
			return False, "memoria e peste prag"
	if inregistrari is None or inregistrari != 0:
		return False, "inregistrare in curs"
	if urmatoarea and urmatoarea > 0 and urmatoarea - acum < INREGISTRARE_CURAND_S:
		return False, "inregistrare in urmatoarele 30 de minute"
	if intrebare:
		return False, "intrebare de repornire pe ecran"
	if lucrari:
		return False, "lucrare in curs: %s" % ", ".join(lucrari)
	return True, ""


def citesteNoaptea(cale=None):
	try:
		with open(cale or CALE_NOAPTE, "r", encoding="utf-8") as f:
			d = json.loads(f.read(4096))
		return d if isinstance(d, dict) else {}
	except (IOError, OSError, ValueError):
		return {}


def scrieNoaptea(d, cale=None):
	cale = cale or CALE_NOAPTE
	try:
		with open(cale + ".nou", "w", encoding="utf-8") as f:
			f.write(json.dumps(d, sort_keys=True))
			f.flush()
			os.fsync(f.fileno())
		os.replace(cale + ".nou", cale)
		return True
	except (IOError, OSError) as e:
		_log("nu pot scrie %s: %s" % (cale, e))
		return False


def uptime(cale=None):
	try:
		with open(cale or CALE_UPTIME, "r", encoding="utf-8") as f:
			return float(f.read(64).split()[0])
	except (IOError, OSError, ValueError, IndexError):
		return None


def lucrariImagine():
	"""Lucrarile imaginii care merg acum: nume scurte. Fiecare se intreaba separat; o eroare la una nu le opreste pe
	celelalte (si nu o socoteste in curs)."""
	rez = []
	for nume, functie in _LUCRARI:
		try:
			if functie():
				rez.append(nume)
		except Exception as e:
			_log("lucrarea %s: %r" % (nume, e))
	return rez


def _scanareDetaliata():
	"""Scanarea detaliata (culegerea canal cu canal), pornita din meniu sau din web."""
	from Components import HdsCulegereTotala
	return bool(HdsCulegereTotala.in_curs())


CALE_CULEGERE_NOAPTE = "/tmp/hds-culegere.pid"   # scanarea detaliata de noapte pornita din afara enigma2


def _scanareDeNoapte(cale=None):
	"""Programul de noapte al scanarii detaliate (proces separat): fisierul lui cu pid, cu procesul viu."""
	try:
		with open(cale or CALE_CULEGERE_NOAPTE, "r", encoding="utf-8") as f:
			pid = int(f.read(32).split()[0])
	except (IOError, OSError, ValueError, IndexError):
		return False
	return pid > 0 and os.path.exists("/proc/%d" % pid)


def _semnOcupat():
	"""Semnul ocupat al paznicului: scanarea canalelor, citirea pistelor, rotirea antenei."""
	from Components import HdsPaznic
	motive, pana = HdsPaznic.bataie().semn()
	return bool(motive)


def _copiaSetarilor():
	"""Copia setarilor (si cea automata, zilnica)."""
	from Components import HdsCopieSetari
	return bool(HdsCopieSetari.ocupat())


def _actualizarile():
	"""Cautarea sau instalarea unei actualizari si actualizarea rapida (verificarea zilnica e o cautare)."""
	from Components import HdsActualizari
	a = HdsActualizari.actualizari
	return bool(a.ocupat() or getattr(a, "rapid", False))


# Ghidul (Components/HdsEpgSalvare.py) se scrie la intrarea in standby si o data la 6 ore, pe firul lui, in cateva
# secunde (STANDBY_MINIM_S il acopera pe cel de la intrare), iar enigma2 il scrie oricum la iesire: nu opreste
# repornirea. Lucrarile din job_manager le da stareReceptor. Transmisiile spre browser si releele locale sunt
# inregistrari enigma2 (nav.getRecordings), deci le acopera conditia inregistrarilor.
_LUCRARI = [
	("scanarea detaliata", _scanareDetaliata),
	("scanarea detaliata de noapte", _scanareDeNoapte),
	("scanare, piste sau antena", _semnOcupat),
	("copia setarilor", _copiaSetarilor),
	("actualizarile", _actualizarile),
]


def _masuraStandby():
	"""Masuratoarea crezuta in standby (Esantioane, de la bataie), sau None."""
	return esantioane().valoare(True)


def _memoriaEsLipsa():
	"""Memoria pozelor si a filmelor lipseste acum (starea scrisa de paznic, de la un paznic viu)."""
	from Components import HdsPaznic
	s = HdsPaznic.stareEs()
	return bool(s.get("ruleaza")) and s.get("memorie_es") == HdsPaznic.MEMORIE_ES_LIPSA


class RepornireStandby(object):
	"""Repornirea in standby, intrebata din bataia paznicului (HdsPaznic.Bataie.pas, la 10 s): standby-ul se urmareste
	la fiecare bataie, restul cel mult o data la VERIFICARE_S."""

	def __init__(self, ceas=None, ceas_perete=None, activ=None, standby=None, masura=None, receptor=None, lucrari=None,
			cale_noapte=None, cale_proba=None, uptime_=None, reporneste=None, jurnal=None, minim=None, boot=None,
			lipsa_es=None):
		self.ceas = ceas or time.monotonic
		self.ceasPerete = ceas_perete or time.time
		self.activ = activ or activaStandby
		self.standby = standby or _inStandby
		self.masura = masura or _masuraStandby
		self.receptor = receptor or _stareReceptor
		self.lucrari = lucrari or lucrariImagine
		self.caleNoapte = cale_noapte
		self.caleProba = cale_proba
		self.uptime = uptime_ or uptime
		self.reporneste = reporneste or _repornesteReceptorul
		self.jurnal = jurnal or scrieJurnal
		self.minim = minim or citesteMinim
		self.boot = boot or bootId
		self.lipsaEs = lipsa_es or _memoriaEsLipsa
		self.standbyDe = None   # ceasul monoton de la care receptorul sta in standby fara intrerupere (None = treaz)
		self.ultima = None
		self.motiv = ""
		self.ceruta = False     # repornirea (sau proba uscata) ceruta de acest proces: nimic mai mult pana la iesire

	def pas(self):
		"""-> True cand a cerut repornirea. Nu arunca."""
		try:
			acum_m = self.ceas()
			if self.standby():
				if self.standbyDe is None or acum_m < self.standbyDe:
					self.standbyDe = acum_m
			else:
				self.standbyDe = None
			if self.ultima is not None and 0 <= acum_m - self.ultima < VERIFICARE_S:
				return False
			self.ultima = acum_m
			self._semnRamas()
			return self._verifica(acum_m)
		except Exception as e:
			_log("repornirea in standby: %r" % (e,))
			return False

	def _semnRamas(self):
		"""Semnul standby scris in aceasta pornire, dar receptorul tot merge (TryQuitMainloop nu s-a inchis): se scoate,
		ca o pornire de mai tarziu, facuta de om, sa nu intre in standby."""
		d = citesteNoaptea(self.caleNoapte)
		if d.get("standby") and d.get("boot") == self.boot() and self.ceasPerete() - float(d.get("ora", 0)) > SEMN_RAMAS_S:
			d["standby"] = 0
			scrieNoaptea(d, self.caleNoapte)
			_log("repornirea in standby nu s-a facut: semnul standby scos")

	def _verifica(self, acum_m):
		if self.ceruta:
			return False
		pr = proba(self.caleProba)
		activ = bool(self.activ())
		standby_s = None if self.standbyDe is None else acum_m - self.standbyDe
		standby_minim = pr.get("standby_min_s", STANDBY_MINIM_S)
		# intrebarile scumpe (vmallocinfo, inregistrarile, lucrarile) numai cu setarea pornita, dupa minutele de standby
		if not activ or standby_s is None or standby_s < standby_minim:
			return False
		acum = self.ceasPerete()
		local = time.localtime(acum)
		d = citesteNoaptea(self.caleNoapte)
		boot = self.boot()
		m = self.masura()
		acumKb = m["liber_kb"] if m else None
		ziua = self.minim()
		if m and ziua is not None and ziua < m["liber_kb"]:
			m = dict(m, liber_kb=ziua)
		# lipsa memoriei pozelor se crede numai daca receptorul a fost treaz in aceasta pornire (exista o masuratoare
		# crezuta din afara standby-ului): dupa o pornire direct in standby demonul nu-si face maparea pana la primul
		# canal, iar paznicul r6 o scria lipsa (fara paza asta: o repornire la fiecare PAUZA_S cat sta in standby)
		lipsa = bool(self.lipsaEs()) and ziua is not None
		p = pr.get("prag_kb", PRAG_KB)
		r = self.receptor() or {}
		da, motiv = hotarareStandby(activ, standby_s, local, acum, d, boot, self.uptime(), m, p,
			r.get("inregistrari", -1), r.get("urmatoarea", 0), r.get("intrebare_pe_tv", False),
			list(r.get("lucrari_nume") or []) + self.lucrari(), lipsa, standby_minim, pr.get("uptime_min_s"))
		if not da:
			if motiv != self.motiv:
				_log("repornirea in standby nu se face: %s" % motiv)
			self.motiv = motiv
			return False
		self.ceruta = True
		if pr.get("uscat"):
			# proba uscata: tot drumul, fara semn pe disc si fara repornire (o data pe pornirea interfetei)
			self.jurnal("PROBA uscata: " + randJurnal("in standby", m, p, acumKb, lipsa) + "; nu repornesc")
			_log("proba uscata: as reporni receptorul acum (%s KB, prag %d KB)" % (m["liber_kb"] if m else "?", p))
			return True
		if not scrieNoaptea({"zi": time.strftime("%Y-%m-%d", local), "ora": int(acum), "standby": 1,
				"liber_kb": int(m["liber_kb"]) if m else -1, "prag_kb": int(p), "boot": boot, "lipsa_es": int(lipsa),
					"motiv": MOTIV_STANDBY},
				self.caleNoapte):
			# fara semn pe disc s-ar putea reporni in lant sau s-ar trezi televizorul: nu se reporneste
			self.ceruta = False
			return False
		self.jurnal(randJurnal("in standby", m, p, acumKb, lipsa))
		_log("in standby: repornesc receptorul (%s KB liberi dintr-o bucata, prag %d KB)" % (m["liber_kb"] if m else "?", p))
		self.reporneste()
		return True


def _inStandby():
	from Screens import Standby
	return Standby.inStandby is not None


def _stareReceptor():
	"""Inregistrarile, urmatoarea inregistrare, intrebarea de repornire si lucrarile in fundal (HdsAlimentare)."""
	from Screens import Standby
	s = getattr(Standby.inStandby, "session", None)
	if s is None:
		return {}
	from Components.HdsAlimentare import stareReceptor
	r = stareReceptor(s, Standby=Standby)
	r["lucrari_nume"] = ["lucrari in fundal (%d)" % r["lucrari"]] if r.get("lucrari") else []
	return r


def _repornesteReceptorul():
	"""Calea sigura a imaginii (TryQuitMainloop 2, ca Repornire din meniu): in standby, fara inregistrari si lucrari,
	se inchide singura si enigma2.sh reporneste receptorul."""
	from Screens import Standby
	s = getattr(Standby.inStandby, "session", None)
	if s is None:
		_log("repornirea in standby: fara sesiune")
		return
	# daca ecranul Standby s-ar inchide la iesire, trezirea nu trimite nimic pe CEC (ca la un temporizator)
	try:
		from Components import HdsStandbyTv
		HdsStandbyTv.trezitDeTemporizator()
	except Exception as e:
		_log("CEC la repornire: %r" % (e,))
	s.open(Standby.TryQuitMainloop, COD_RECEPTOR)


_repornire = [None]


def repornireStandby():
	if _repornire[0] is None:
		_repornire[0] = RepornireStandby()
	return _repornire[0]


# ---------------------------------------------------------------- c) filmul care nu porneste din lipsa memoriei

def numarMapari(date_vmalloc):
	"""Cate mapari de MARIME_ES listeaza vmallocinfo (ca hisiCountEsMaps din lib/dvb/hdspazavideo.h)."""
	if isinstance(date_vmalloc, bytes):
		date_vmalloc = date_vmalloc.decode("ascii", "replace")
	n = 0
	for rand in (date_vmalloc or "").splitlines():
		p = rand.split()
		if len(p) > 1 and p[0].startswith("0x") and p[1] == str(MARIME_ES):
			n += 1
	return n


def mapareEs(cale=None):
	"""1 cand demonul platformei are maparea memoriei filmelor (vmallocinfo o listeaza), 0 cand nu, -1 cand vmallocinfo
	nu se poate citi (atunci nu se stie, deci nu se reporneste nimic). Citit acum, nu din cache."""
	try:
		date = _citeste(cale or CALE_VMALLOCINFO, 4 * 1024 * 1024)
	except (IOError, OSError) as e:
		_log("nu pot citi vmallocinfo: %s" % e)
		return -1
	if not date:
		return -1
	return 1 if numarMapari(date) >= 1 else 0


def hotarareFilm(standby, local, acum, ultima, boot, uptime_s, mapare, inregistrari, urmatoarea, intrebare, lucrari,
		uptime_minim=None):
	"""Ce se face pentru un film (sau canal de pe internet) refuzat din lipsa memoriei decodorului, fara efecte.
	mapare = mapareEs() acum; ultima = randul din CALE_NOAPTE ({} fara); boot = boot_id-ul de acum.
	-> (FAPTA_REPORNESTE | FAPTA_REINCEARCA | FAPTA_NIMIC, motivul scurt)."""
	if standby:
		return FAPTA_NIMIC, "receptorul e in standby"
	if mapare == 1:
		# maparea s-a facut intre timp (de pilda dupa o pornire direct in standby): filmul porneste din nou, fara repornire
		return FAPTA_REINCEARCA, "maparea e la loc"
	if mapare != 0:
		return FAPTA_NIMIC, "memoria nucleului nu se poate citi"
	if uptime_s is None or uptime_s < (FILM_UPTIME_MINIM_S if uptime_minim is None else uptime_minim):
		return FAPTA_NIMIC, "pornit de prea putin timp"
	if local.tm_year < 2024:
		return FAPTA_NIMIC, "ceasul nu e potrivit"
	ultima = ultima or {}
	if ultima.get("boot") and ultima.get("boot") == boot:
		return FAPTA_NIMIC, "o data pe pornire"
	try:
		ora = float(ultima.get("ora") or 0)
	except (TypeError, ValueError):
		ora = 0
	if ora > 0 and acum - ora < PAUZA_S:
		# si cu ceasul in urma fata de ora scrisa: prea devreme (paza impotriva repornirilor in lant)
		return FAPTA_NIMIC, "alta repornire de curand"
	if inregistrari is None or inregistrari != 0:
		return FAPTA_NIMIC, "inregistrare in curs"
	if urmatoarea and urmatoarea > 0 and urmatoarea - acum < INREGISTRARE_CURAND_S:
		return FAPTA_NIMIC, "inregistrare in urmatoarele 30 de minute"
	if intrebare:
		return FAPTA_NIMIC, "intrebare de repornire pe ecran"
	if lucrari:
		return FAPTA_NIMIC, "lucrare in curs: %s" % ", ".join(lucrari)
	return FAPTA_REPORNESTE, ""


def citesteFilm(cale=None):
	try:
		with open(cale or CALE_FILM, "r", encoding="utf-8") as f:
			d = json.loads(f.read(8192))
		return d if isinstance(d, dict) else {}
	except (IOError, OSError, ValueError):
		return {}


def scrieFilm(d, cale=None):
	return scrieNoaptea(d, cale or CALE_FILM)


def stergeFilm(cale=None):
	try:
		os.remove(cale or CALE_FILM)
	except OSError:
		pass


def _stareReceptorSesiune(sesiune):
	"""Inregistrarile, urmatoarea inregistrare, intrebarea de repornire si lucrarile in fundal, din sesiunea data."""
	from Screens import Standby
	from Components.HdsAlimentare import stareReceptor
	r = stareReceptor(sesiune, Standby=Standby)
	r["lucrari_nume"] = ["lucrari in fundal (%d)" % r["lucrari"]] if r.get("lucrari") else []
	return r


def _programeaza(secunde, functie):
	"""functie() dupa `secunde`, pe firul enigma2 (eTimer tinut pana se cheama)."""
	from enigma import eTimer
	t = eTimer()
	tinut = [t]

	def gata():
		tinut[0].stop()
		tinut[:] = []
		functie()
	t.callback.append(gata)
	t.start(int(secunde * 1000), True)
	_tinute.append(tinut)


_tinute = []
programeaza = _programeaza


def _repornesteDinSesiune(sesiune):
	"""Calea sigura a imaginii (TryQuitMainloop 2, ca Repornire din meniu); canalul tinut minte se scrie la inchidere."""
	from Screens import Standby
	sesiune.open(Standby.TryQuitMainloop, COD_RECEPTOR)


class RefacereFilm(object):
	"""Cererea playerului pentru un film refuzat cu felul "decodor". Toate dependentele se pot da (probele de pe PC)."""

	def __init__(self, ceas_perete=None, uptime_=None, boot=None, mapare=None, masura=None, receptor=None, lucrari=None,
			standby=None, cale_noapte=None, cale_film=None, cale_proba=None, jurnal=None, programeaza=None,
			reporneste=None, ceas=None):
		self.ceasPerete = ceas_perete or time.time
		self.ceas = ceas or time.monotonic
		self.uptime = uptime_ or uptime
		self.boot = boot or bootId
		self.mapare = mapare or mapareEs
		self.masura = masura or masoara
		self.receptor = receptor or _stareReceptorSesiune
		self.lucrari = lucrari or lucrariImagine
		self.standby = standby or _inStandby
		self.caleNoapte = cale_noapte
		self.caleFilm = cale_film
		self.caleProba = cale_proba
		self.jurnal = jurnal or scrieJurnal
		self.programeaza = programeaza or _programeaza
		self.reporneste = reporneste or _repornesteDinSesiune
		self.ceruta = False     # repornirea ceruta de acest proces: nimic mai mult pana la iesire
		self.motiv = ""
		self.reincercat = None  # (filmul, ceasul monoton) ultimei porniri din nou fara repornire

	def cere(self, sesiune, ref_text, canal=False, tehnic=""):
		"""-> FAPTA_REPORNESTE (fraza scurta pe ecran, repornirea dupa FILM_ARATARE_S), FAPTA_REINCEARCA (filmul se
		porneste din nou acum) sau FAPTA_NIMIC (numai "Filmul nu poate porni acum."). Nu arunca."""
		try:
			if self.ceruta:
				return FAPTA_REPORNESTE
			pr = proba(self.caleProba)
			acum = self.ceasPerete()
			local = time.localtime(acum)
			mapare = self.mapare()
			if "unreadable" in (tehnic or "") and mapare != 1:
				# servicemp3 nu a putut citi vmallocinfo: nu se stie ca memoria lipseste
				mapare = -1
			r = self.receptor(sesiune) or {}
			lucrari = list(r.get("lucrari_nume") or []) + self.lucrari()
			fapta, motiv = hotarareFilm(self.standby(), local, acum, citesteNoaptea(self.caleNoapte), self.boot(),
				self.uptime(), mapare, r.get("inregistrari", -1), r.get("urmatoarea", 0), r.get("intrebare_pe_tv", False),
				lucrari, pr.get("uptime_min_s"))
			if fapta == FAPTA_REINCEARCA:
				# o singura data pe film intr-un minut: altfel un refuz care tine ar porni filmul in bucla
				m_acum = self.ceas()
				din_nou = self.reincercat is not None and self.reincercat[0] == ref_text
				if din_nou and 0 <= m_acum - self.reincercat[1] < REINCERCARE_S:
					fapta, motiv = FAPTA_NIMIC, "pornit din nou de curand"
				else:
					self.reincercat = (ref_text, m_acum)
					_log("filmul: %s, il pornesc din nou" % motiv)
					return fapta
			m = self.masura()
			p = pr.get("prag_kb", PRAG_KB)
			if fapta == FAPTA_NIMIC:
				self.motiv = motiv
				self.jurnal("filmul nu porneste: memoria pozelor si a filmelor lipseste; nu repornesc: %s" % motiv)
				_log("filmul: nu repornesc (%s)" % motiv)
				return fapta
			if pr.get("uscat"):
				self.jurnal("PROBA uscata: " + randJurnal("pentru un film", m, p, lipsa_es=True) + "; nu repornesc")
				_log("proba uscata: as reporni receptorul pentru film")
				return FAPTA_NIMIC
			boot = self.boot()
			if not scrieNoaptea({"zi": time.strftime("%Y-%m-%d", local), "ora": int(acum), "standby": 0,
					"liber_kb": int(m["liber_kb"]) if m else -1, "prag_kb": int(p), "boot": boot, "lipsa_es": 1,
					"motiv": MOTIV_FILM}, self.caleNoapte):
				# fara semn pe disc s-ar putea reporni in lant: nu se reporneste
				return FAPTA_NIMIC
			scrieFilm({"ref": str(ref_text or ""), "canal": int(bool(canal)), "ora": int(acum), "boot": boot},
				self.caleFilm)
			self.ceruta = True
			self.jurnal(randJurnal("pentru un film", m, p, lipsa_es=True))
			_log("repornesc receptorul pentru film (%s)" % (ref_text,))
			self.programeaza(FILM_ARATARE_S, lambda: self.reporneste(sesiune))
			return FAPTA_REPORNESTE
		except Exception as e:
			_log("refacerea pentru film: %r" % (e,))
			return FAPTA_NIMIC


_refacere = [None]


def refacereFilm(sesiune, ref_text, canal=False, tehnic=""):
	"""Din playere (Screens/InfoBarGenerics.InfoBarFilmRefuz, MediaPlayer): un film refuzat cu felul "decodor"."""
	if _refacere[0] is None:
		_refacere[0] = RefacereFilm()
	return _refacere[0].cere(sesiune, ref_text, canal, tehnic)


def ultimaEliberare(cale=None):
	"""(ora, motiv) ultimei reporniri facute de aici (MOTIV_STANDBY sau MOTIV_FILM), sau None. Pentru Informatii >
	Memorie."""
	d = citesteNoaptea(cale)
	try:
		ora = int(d.get("ora") or 0)
	except (TypeError, ValueError):
		ora = 0
	if ora <= 0:
		return None
	return ora, (MOTIV_FILM if d.get("motiv") == MOTIV_FILM else MOTIV_STANDBY)


def textUltimaEliberare(cale=None):
	"""Data si ora ultimei reporniri de aici si motivul ei (pentru un film / in standby), sau "" fara niciuna."""
	u = ultimaEliberare(cale)
	if u is None:
		return ""
	ora, motiv = u
	cand = time.strftime("%d.%m.%Y %H:%M", time.localtime(ora))
	return "%s, %s" % (cand, _("pentru un film") if motiv == MOTIV_FILM else _("în standby"))


# ---------------------------------------------------------------- pornirea

def _semnProaspat(d, ceas_perete=None, boot=None, uptime_s=None):
	"""Semnul scris inainte de o repornire de aici e de la pornirea de dinainte: scris acum cel mult STANDBY_PROASPAT_S
	dupa ceasul de perete (care dupa pornire vine din fake-hwclock si poate fi in urma: o ora inapoi se primeste), sau
	alta pornire a nucleului (boot_id schimbat), abia pornita, cu ceasul inca in urma (inainte de NTP)."""
	varsta = (ceas_perete or time.time)() - float(d.get("ora", 0))
	if -3600 <= varsta <= STANDBY_PROASPAT_S:
		return True
	boot = boot or bootId()
	up = uptime() if uptime_s is None else uptime_s
	return bool(d.get("boot")) and d.get("boot") != boot and up is not None and up <= STANDBY_PROASPAT_S and \
		-CEAS_IN_URMA_S <= varsta < 0


def standbyLaPornire(cale=None, ceas_perete=None, boot=None, uptime_s=None):
	"""Semnul standby lasat de repornirea in standby: True cand e proaspat (si il sterge). Proaspat = alta pornire a
	nucleului (boot_id schimbat) de cel mult STANDBY_PROASPAT_S, sau scris acum cel mult STANDBY_PROASPAT_S dupa ceasul
	de perete (care dupa pornire vine din fake-hwclock si poate fi in urma: o ora inapoi se primeste). Nu arunca."""
	try:
		d = citesteNoaptea(cale)
		if not d.get("standby"):
			return False
		d["standby"] = 0
		scrieNoaptea(d, cale)
		return _semnProaspat(d, ceas_perete, boot, uptime_s)
	except Exception as e:
		_log("semnul standby: %r" % (e,))
		return False


def filmLaPornire(cale=None, ceas_perete=None, boot=None, uptime_s=None):
	"""Filmul lasat de repornirea pentru el ({'ref', 'canal'}), cand semnul e proaspat si de la alta pornire a
	nucleului; altfel None. Semnul se sterge oricum (o singura data). Nu arunca."""
	try:
		d = citesteFilm(cale)
		if not d:
			return None
		stergeFilm(cale)
		boot = boot or bootId()
		if not d.get("ref") or not d.get("boot") or d.get("boot") == boot:
			# aceeasi pornire: repornirea nu s-a facut (o intrebare cu "Nu"); nimic de pornit mai tarziu
			return None
		if not _semnProaspat(d, ceas_perete, boot, uptime_s):
			return None
		return {"ref": str(d["ref"]), "canal": bool(d.get("canal"))}
	except Exception as e:
		_log("filmul de dupa repornire: %r" % (e,))
		return None


class ReluareFilm(object):
	"""Dupa repornirea pentru film: asteapta bara principala si maparea demonului (cel mult FILM_ASTEPTARE_S, pe ceasul
	monoton), apoi porneste filmul in playerul de filme sau canalul pe locul lui (numai daca omul n-a ales intre timp
	altceva). Cat asteapta, playerul nu spune nimic despre felul "decodor" (reluareInCurs)."""

	def __init__(self, film, ceas=None, mapare=None, bara=None, deschide=None, porneste=None, curent=None,
			esuat=None, standby=None):
		self.film = film
		self.ceas = ceas or time.monotonic
		self.mapare = mapare or mapareEs
		self.bara = bara or _baraPrincipala
		self.deschide = deschide or _deschideFilm
		self.porneste = porneste or _pornesteCanal
		self.curent = curent or _serviciulCurent
		self.esuat = esuat or _serviciulEsuat
		self.standby = standby or _inStandby
		self.de_la = None
		self.gata = False

	def pas(self):
		"""-> True cand a terminat (a pornit filmul, sau nu mai e nimic de facut). Nu arunca."""
		if self.gata:
			return True
		try:
			acum = self.ceas()
			if self.de_la is None:
				self.de_la = acum
			if self.standby():
				_log("dupa repornirea pentru film: receptorul e in standby, nu pornesc nimic")
				self.gata = True
				return True
			bara = self.bara()
			if bara is None:
				return False
			mapat = self.mapare() == 1
			if not mapat and acum - self.de_la < FILM_ASTEPTARE_S:
				return False
			if not mapat:
				_log("dupa repornirea pentru film: maparea lipseste dupa %d s; pornesc oricum" % FILM_ASTEPTARE_S)
			ref = self.film["ref"]
			if self.film.get("canal"):
				cur = self.curent(bara)
				if cur is None or (cur == ref and self.esuat(bara)):
					_log("dupa repornirea pentru film: pornesc din nou canalul")
					self.porneste(bara, ref)
			else:
				_log("dupa repornirea pentru film: deschid filmul")
				self.deschide(bara, ref)
			self.gata = True
			return True
		except Exception as e:
			_log("reluarea filmului: %r" % (e,))
			self.gata = True
			return True


def _baraPrincipala():
	from Screens.InfoBar import InfoBar
	return InfoBar.instance


def _deschideFilm(bara, ref):
	from enigma import eServiceReference
	from Screens.InfoBar import MoviePlayer
	from Tools import Notifications
	Notifications.AddNotification(MoviePlayer, eServiceReference(ref))


def _pornesteCanal(bara, ref):
	from enigma import eServiceReference
	bara.session.nav.playService(eServiceReference(ref))


def _serviciulCurent(bara):
	r = bara.session.nav.getCurrentlyPlayingServiceReference()
	return r.toString() if r is not None else None


def _serviciulEsuat(bara):
	"""Canalul de acum a fost refuzat de servicemp3 din lipsa memoriei decodorului."""
	from Components import HdsFilmRedare
	s = bara.session.nav.getCurrentService()
	return HdsFilmRedare.esteDecodor(HdsFilmRedare.verdictDinInfo(s and s.info()))


_reluare = [None]


def reluareInCurs():
	"""True cat, dupa repornirea pentru film, filmul inca nu a fost pornit din nou."""
	r = _reluare[0]
	return r is not None and not r.gata


def _pornesteReluarea(film):
	from enigma import eTimer
	r = ReluareFilm(film)
	_reluare[0] = r
	t = eTimer()

	def pas():
		if r.pas():
			t.stop()
			_tinute[:] = [x for x in _tinute if x is not tinut]
	tinut = [t]
	t.callback.append(pas)
	t.start(FILM_PAS_MS, False)
	_tinute.append(tinut)


def porneste():
	"""Din HdsPaznic.porneste (mytest.py, dupa pornirea sesiunii): setarea si, dupa o repornire in standby, standby."""
	try:
		initConfig()
	except Exception as e:
		_log("setarea: %r" % (e,))
	if standbyLaPornire():
		_log("pornit dupa repornirea in standby: intru in standby")
		try:
			from Tools import Notifications
			import Screens.Standby
			Notifications.AddNotification(Screens.Standby.Standby)
		except Exception as e:
			_log("standby la pornire: %r" % (e,))
		stergeFilm()
		return
	film = filmLaPornire()
	if film:
		_log("pornit dupa repornirea pentru film: il pornesc cand demonul are maparea")
		try:
			_pornesteReluarea(film)
		except Exception as e:
			_log("filmul dupa repornire: %r" % (e,))
