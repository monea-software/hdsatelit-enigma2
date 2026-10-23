# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# disc_web.py: dosarele inregistrarilor, formatarea si verificarea discurilor si fisierul de swap in interfata web
# (HdsWebControl).
#
# Orice ecran sau setare de pe receptor are pereche in interfata web. Pe televizor, Meniu > Setari > Inregistrari &
# Stocare:
#   - Recording Locations (entryID RecordPaths, Screens/RecordPaths.py RecordPathsSettings): locul implicit, al
#     inregistrarilor programate si al celor imediate (numai la nivelul Expert) si locul timeshift; OK deschide alegerea
#     dosarului (Screens/LocationBox.py, MovieLocationBox / TimeshiftLocationBox, cu dosar nou, stergerea unui dosar si
#     lista dosarelor tinute minte). Pagina: /locuri-inregistrari, aceleasi randuri, aceleasi alegeri, dosarul ales
#     navigand prin aceleasi dosare, aceleasi verificari si aceleasi efecte (Components/HdsDosareInregistrari.py).
#     Pagina /stocare (stocare_web.py) arata discul pe care se salveaza si discurile conectate: aici numai o legatura.
#   - Format Hard Drive (entryID harddisk_init) si Check Disk Health (harddisk_check): lista hard diskurilor si a
#     stick-urilor USB (HarddiskSelection), apoi Rosu cu alegerea sistemului de fisiere (numai la un stick: FAT32
#     primul, ext4 al doilea), intrebarea cu ce se pierde si ecranul de asteptare (HarddiskSetup, HarddiskWait). Pagina:
#     /discuri?f=formatare|verificare, aceeasi lista, aceeasi alegere, aceeasi intrebare (confirmare in doi pasi),
#     aceeasi lucrare (Components/HdsDiscuri.py, pe un fir), progresul si rezultatul in pagina. Din pagina formatarea
#     si verificarea se refuza cat o inregistrare e in curs sau incepe in mai putin de 10 minute si cat discul e folosit
#     (swap, timeshift, o inregistrare, un fisier deschis); pe televizor intrebarea spune acelasi lucru si omul alege.
#   - Swap File (entryID hds_swap_manager, Screens/SwapManager.py): discurile montate, swap-urile active, activarea
#     fisierului de 512 MB si oprirea. Pagina: /swap, aceleasi comenzi (Components/HdsSwap.py); activarea si oprirea
#     cu confirmare. Un swap deja pornit nu se rescrie si un swapfile.hds care nu e fisier obisnuit nu se atinge.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/locuri-inregistrari                       randurile, alegerile, listele tinute minte
#   GET  /api/locuri-inregistrari-dosare?cale=<dosar>   dosarele de sub <dosar> (gol: discurile montate), pe un fir
#   POST /api/locuri-inregistrari-seteaza?rand=<rand>&valoare=<alegere> | &dosar=<dosar ales navigand> [&cod=]
#   POST /api/locuri-inregistrari-dosar-nou?parinte=<dosar>&nume=<nume>
#   POST /api/locuri-inregistrari-sterge-dosar?cale=<dosar>&pas=intreaba | &cod= | &pas=renunta   (numai gol)
#   POST /api/locuri-inregistrari-scoate?lista=filme|timeshift&dosar=<dosar>&pas=intreaba | &cod= | &pas=renunta
#   GET  /api/discuri                                   discurile oferite, partitiile, lucrarea de acum
#   POST /api/discuri-lucru?disc=<sda>&fel=formatare|verificare[&sistem=ext4|vfat]&pas=intreaba | &cod= | &pas=renunta
#   GET  /api/swap                                      discurile montate, swap-urile active, lucrarea de acum
#   POST /api/swap-activeaza?punct=<punct de montare>&pas=intreaba | &cod= | &pas=renunta
#   POST /api/swap-opreste?punct=<punct de montare>&pas=intreaba | &cod= | &pas=renunta
#   GET  /locuri-inregistrari, /discuri, /swap          paginile
# Actiunile cu confirmare nu se fac cu ?token= (numai din browserul conectat). Un disc, un dosar sau un punct de
# montare se ia numai din lista de acum (sau, la dosare, numai sub discurile montate, fara dosarele sistemului si fara
# ".."), niciodata o cale oarecare din cerere.
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2. Listarea unui dosar (poate fi pe o partajare de retea)
# merge pe un fir (meniu_comun_web.peFir); formatarea si verificarea pe firul lor (HdsDiscuri.pornesteFir), pagina
# intreaba din nou cat merg; comenzile swap cu Components.Console (nu opresc firul). Verificarea dosarului ales si
# salvarea setarilor raman pe firul enigma2, ca pe televizor (notificatorii setarilor). Fisierul nu importa nimic din
# enigma2 la incarcare: probele de pe PC dau modulele lor (H, D, S), setarile, discurile si firul lor.

import os
import time

MAX_CALE = 400
MAX_NUME = 255
TIMP_FIR_S = 30
# cat timp (secunde de la sfarsit) se arata in pagina rezultatul ultimei lucrari
VARSTA_LUCRU = 600
LISTE = ("filme", "timeshift")
FILE = ("formatare", "verificare")


def _t(text):
	from .meniu_comun_web import _t as t
	return t(text)


def _c():
	from . import meniu_comun_web
	return meniu_comun_web


def _h(H=None):
	if H is not None:
		return H
	from Components import HdsDosareInregistrari
	return HdsDosareInregistrari


def _d(D=None):
	if D is not None:
		return D
	from Components import HdsDiscuri
	return HdsDiscuri


def _s(S=None):
	if S is not None:
		return S
	from Components import HdsSwap
	return HdsSwap


def _config(config=None):
	if config is None:
		from Components.config import config
	return config


def _salveaza(configfile=None):
	if configfile is not None:
		configfile.save()
		return True
	return _c().salveazaSetari()


# ------------------------------------------------------------------ locurile inregistrarilor

def stareLocuri(H=None, config=None):
	"""Pentru GET /api/locuri-inregistrari."""
	H = _h(H)
	config = _config(config)
	return {
		"result": True,
		"expert": bool(H.expert(config)),
		"randuri": H.randuri(config),
		"liste": {"filme": list(config.movielist.videodirs.value),
			"timeshift": list(config.usage.allowed_timeshift_paths.value)},
		"min_liber_timeshift_mb": H.MIN_LIBER_TIMESHIFT_MB,
	}


def _cuStare(rez, H, config, mesaj, bun):
	r = stareLocuri(H, config)
	r.update(rez or {})
	r.update({"result": bool(bun), "message": mesaj})
	return r


def listeazaDosare(argumente, radacini_, H=None):
	"""GET /api/locuri-inregistrari-dosare (pe un fir): fara cale, discurile montate; altfel dosarele de sub ea."""
	H = _h(H)
	cale = argumente.get("cale", "")
	if not cale:
		return {"result": True, "cale": "", "parinte": None, "liber_mb": None,
			"dosare": [{"cale": r["cale"], "nume": r["nume"], "fel": r.get("fel", "")} for r in radacini_]}
	dosar = H.dosarPermis(cale, radacini_)
	if dosar is None:
		return {"result": False, "message": _t("Dosarul ales nu se poate folosi. Alege din nou.")}
	rez = H.dosare(dosar, radacini_)
	return {"result": True, "cale": dosar, "parinte": rez["parinte"], "dosare": rez["dosare"],
		"liber_mb": H.liberMB(dosar)}


def seteazaLoc(argumente, radacini_, H=None, config=None, configfile=None):
	"""POST /api/locuri-inregistrari-seteaza: o alegere din lista randului (valoare=) sau un dosar ales navigand
	(dosar=, care intra apoi in lista tinuta minte). Aceleasi verificari ca pe televizor: dosarul trebuie sa se poata
	scrie; la timeshift, sub MIN_LIBER_TIMESHIFT_MB liberi, intai o confirmare (cod=)."""
	H = _h(H)
	C = _c()
	config = _config(config)
	rand = argumente.get("rand", "")
	if argumente.get("pas") == "renunta":
		# "Renunță" la intrebarea despre spatiul pentru timeshift: codul cerut nu mai e bun, nimic schimbat
		dosar = H.dosarPermis(argumente.get("dosar", ""), radacini_)
		C.uita("loc-timeshift", dosar or argumente.get("dosar", ""))
		return _cuStare(None, H, config, _t("Nu s-a schimbat nimic."), True)
	if rand not in H.randuriVazute(config):
		return _cuStare(None, H, config, _t("Rândul ales nu mai este pe ecran. Pagina se încarcă din nou."), False)
	dosar_nou = None
	if argumente.get("valoare"):
		valoare = argumente["valoare"]
		rand_acum = [r for r in H.randuri(config) if r["cheie"] == rand][0]
		if valoare not in [a[0] for a in rand_acum["alegeri"]]:
			return _cuStare(None, H, config, _t("Alegerea nu mai este în lista rândului. Alege din nou."), False)
	elif argumente.get("dosar"):
		valoare = H.dosarPermis(argumente["dosar"], radacini_)
		if valoare is None:
			return _cuStare(None, H, config, _t("Dosarul ales nu se poate folosi. Alege din nou."), False)
		dosar_nou = valoare
	else:
		return _cuStare(None, H, config, _t("Nu s-a trimis nicio setare."), False)
	if not H.poateScrie(valoare):
		return _cuStare(None, H, config, H.textNuSePoateScrie(valoare), False)
	if dosar_nou is not None and rand == H.RAND_TIMESHIFT and not H.destulLocTimeshift(dosar_nou):
		cod = argumente.get("cod", "")
		if not cod:
			liber = H.liberMB(dosar_nou)
			detalii = [_t("Spațiu liber: %s MB") % liber] if liber is not None else []
			return C.raspunsIntrebare("loc-timeshift", dosar_nou, _t("There might not be enough Space on the selected "
				"Partition.\nDo you really want to continue?"), _t("Da, folosește-l"), detalii)
		if not C.verifica("loc-timeshift", dosar_nou, cod):
			return _cuStare(C.codGresit(), H, config, C.codGresit()["message"], False)
	if dosar_nou is not None:
		H.adaugaInLista(H.listaTinuta(rand, config), dosar_nou)
	valori = H.valori(config)
	valori[rand] = valoare
	H.salveaza(valori[H.RAND_IMPLICIT], valori[H.RAND_TEMPORIZATOR], valori[H.RAND_IMEDIAT], valori[H.RAND_TIMESHIFT],
		config)
	_salveaza(configfile)
	return _cuStare(None, H, config, _t("Salvat."), True)


def dosarNou(argumente, radacini_, H=None, config=None):
	"""POST /api/locuri-inregistrari-dosar-nou: un singur nume nou in dosarul de acum (ca in meniul navigatorului)."""
	H = _h(H)
	parinte = H.dosarPermis(argumente.get("parinte", ""), radacini_)
	if parinte is None:
		return {"result": False, "message": _t("Un dosar nou se face numai într-un dosar ales, nu în lista discurilor.")}
	bun, rez = H.faDosar(parinte, argumente.get("nume", ""))
	if not bun:
		return {"result": False, "message": rez}
	return {"result": True, "message": _t("Dosarul a fost făcut."), "cale": rez}


def stergeDosar(argumente, radacini_, H=None, config=None):
	"""POST /api/locuri-inregistrari-sterge-dosar: in doi pasi; numai un dosar gol, sub discurile montate, care nu e
	chiar discul."""
	H = _h(H)
	C = _c()
	cale_ceruta = argumente.get("cale", "")
	if argumente.get("pas") == "renunta":
		C.uita("sterge-dosar", cale_ceruta)
		return {"result": True, "message": _t("Nu s-a șters nimic.")}
	cale = H.dosarPermis(cale_ceruta, radacini_)
	if cale is None or any(r["cale"] == cale for r in radacini_):
		return {"result": False, "message": _t("Dosarul ales nu se poate șterge.")}
	if argumente.get("pas") == "intreaba":
		return C.raspunsIntrebare("sterge-dosar", cale, _t("Ștergi de pe disc dosarul %s?") % cale, _t("Da, șterge"),
			[_t("Se șterge numai dacă e gol.")])
	if not C.verifica("sterge-dosar", cale, argumente.get("cod", "")):
		return C.codGresit()
	bun, mesaj = H.stergeDosar(cale, _config(config))
	if not bun:
		return {"result": False, "message": mesaj}
	return {"result": True, "message": _t("Dosarul a fost șters."), "parinte": os.path.dirname(cale.rstrip(os.sep))}


def scoateDinLista(argumente, H=None, config=None, configfile=None):
	"""POST /api/locuri-inregistrari-scoate: in doi pasi, un dosar scos din lista tinuta minte (filme sau timeshift)."""
	H = _h(H)
	C = _c()
	config = _config(config)
	lista = argumente.get("lista", "")
	dosar = argumente.get("dosar", "")
	if lista not in LISTE:
		return _cuStare(None, H, config, _t("Lista aleasă nu există."), False)
	element = config.usage.allowed_timeshift_paths if lista == "timeshift" else config.movielist.videodirs
	tinta = lista + ":" + dosar
	if argumente.get("pas") == "renunta":
		C.uita("scoate-dosar", tinta)
		return _cuStare(None, H, config, _t("Nu s-a schimbat nimic."), True)
	if dosar not in element.value:
		return _cuStare(None, H, config, _t("Dosarul nu mai este în listă."), False)
	if argumente.get("pas") == "intreaba":
		return C.raspunsIntrebare("scoate-dosar", tinta, _t("Scoți dosarul %s din listă?") % dosar, _t("Da, scoate"),
			[_t("Dosarul rămâne pe disc; numai nu mai apare între alegeri.")])
	if not C.verifica("scoate-dosar", tinta, argumente.get("cod", "")):
		r = C.codGresit()
		return _cuStare(r, H, config, r["message"], False)
	H.scoateDinLista(element, dosar)
	_salveaza(configfile)
	return _cuStare(None, H, config, _t("Dosarul a fost scos din listă."), True)


# ------------------------------------------------------------------ discurile (formatare, verificare)

def _inregistrari(D, inregistrare=None):
	"""Ce stie receptorul acum despre inregistrari si timeshift (HdsDiscuri.stareInregistrari, pe firul enigma2).
	Probele dau o functie care intoarce acelasi dictionar sau numai True / False (o inregistrare in curs)."""
	if inregistrare is None:
		return D.stareInregistrari()
	r = inregistrare()
	if isinstance(r, dict):
		return r
	return {"in_curs": 1 if r else 0, "urmatoarea": 0, "fisiere": [], "timeshift": ""}


def _textSisteme(D, hdd):
	return [[s, D.numeSistem(s), D.textSistem(s)] for s in D.sisteme(hdd)]


def _lucruDisc(D, acum=None):
	l = D.stareLucru()
	if not l:
		return None
	acum = time.time() if acum is None else acum
	sfarsit = l.get("sfarsit")
	if l["stare"] != D.LUCRU_IN_LUCRU and sfarsit and acum - sfarsit > VARSTA_LUCRU:
		return None
	return {"fel": l["fel"], "dispozitiv": l["dispozitiv"], "text_disc": l.get("text_disc", ""), "stare": l["stare"],
		"text": D.textLucru(l), "secunde": int((sfarsit or acum) - (l.get("timp") or acum)), "timp": l.get("timp") or 0}


def stareDiscuri(D=None, hm=None, sys_block="/sys/block", mounts=None, inregistrare=None, unelte=None):
	"""Pentru GET /api/discuri: hard diskurile si stick-urile USB oferite, felul lor, sistemele de fisiere de ales la
	formatare, lucrarea de acum si inregistrarile care ar opri o lucrare pornita de aici."""
	D = _d(D)
	discuri = []
	for _text, hdd in D.discuriOferite(hm, sys_block):
		try:
			d = D.descriere(hdd, sys_block, mounts)
		except Exception as eroare:
			_c().jurnal("discuri: %s nu se poate citi: %s" % (getattr(hdd, "device", "?"), eroare))
			continue
		d["magistrala_text"] = _t(d["magistrala"])
		d["felul"] = _t("USB Stick") if d["detasabil"] else _t("Harddisk")
		d["sisteme"] = _textSisteme(D, hdd)
		discuri.append(d)
	inreg = _inregistrari(D, inregistrare)
	return {
		"result": True,
		"discuri": discuri,
		"lucru": _lucruDisc(D),
		"inregistrare": bool(inreg.get("in_curs")),
		"opriri": [t for _c2, t in D.motiveInregistrari(inreg)],
		"prag_minute": D.PRAG_INREGISTRARE_S // 60,
	}


def lucruDisc(argumente, D=None, hm=None, sys_block="/sys/block", mounts=None, inregistrare=None, porneste=None,
		unelte=None):
	"""POST /api/discuri-lucru: pas=intreaba -> intrebarea televizorului, cu ce se pierde; cod=... -> aceeasi lucrare ca
	pe televizor. Se refuza (si la intrebare, si la cod) cat o inregistrare e in curs sau incepe in mai putin de
	PRAG_INREGISTRARE_S secunde si cat discul e folosit de swap, timeshift, o inregistrare sau un fisier deschis."""
	D = _d(D)
	C = _c()
	fel = argumente.get("fel", "")
	disc = argumente.get("disc", "")
	sistem = argumente.get("sistem", "") if fel == "formatare" else ""
	tinta = fel + ":" + disc + ":" + sistem
	if argumente.get("pas") == "renunta":
		C.uita("disc", tinta)
		return {"result": True, "message": _t("Nu s-a făcut nimic.")}
	if fel not in FILE:
		return {"result": False, "message": _t("Lucrare necunoscută.")}

	def cuStare(mesaj, extra=None):
		rez = stareDiscuri(D, hm, sys_block, mounts, inregistrare, unelte)
		rez.update(extra or {})
		rez.update({"result": False, "message": mesaj})
		return rez

	hdd = D.discul(disc, hm, sys_block)
	if hdd is None:
		return cuStare(_t("Discul ales nu mai este în listă. Alege din nou."))
	if fel == "formatare":
		if not sistem:
			sistem = D.sistemImplicit(hdd)
			tinta = fel + ":" + disc + ":" + sistem
		if sistem not in D.sisteme(hdd):
			return cuStare(_t("Sistemul de fișiere ales nu se poate pune pe acest disc."))
	if D.inLucru():
		return cuStare(_t("Se lucrează deja la un disc. Așteaptă să se termine."))
	inreg = _inregistrari(D, inregistrare)
	motive = D.motiveRefuz(disc, inreg, unelte)
	if motive:
		C.uita("disc", tinta)
		inceput = _t("Formatarea nu se face acum din pagină:") if fel == "formatare" else \
			_t("Verificarea nu se face acum din pagină:")
		return cuStare(inceput + " " + " ".join(t for _k, t in motive), {"motive": [t for _k, t in motive]})
	if argumente.get("pas") == "intreaba":
		q, detalii = D.intrebare(hdd, fel, sistem or None, inreg, unelte)
		return C.raspunsIntrebare("disc", tinta, q, D.butonDa(hdd, fel), detalii)
	if not C.verifica("disc", tinta, argumente.get("cod", "")):
		rez = stareDiscuri(D, hm, sys_block, mounts, inregistrare, unelte)
		rez.update(C.codGresit())
		return rez
	pornit, text = D.pornesteFir(hdd, fel, porneste, sistem or None, unelte)
	rez = stareDiscuri(D, hm, sys_block, mounts, inregistrare, unelte)
	rez.update({"result": bool(pornit), "message": text})
	return rez


# ------------------------------------------------------------------ fisierul de swap

def _lucruSwap(S, acum=None):
	l = S.stareLucru()
	if not l:
		return None
	acum = time.time() if acum is None else acum
	if l["stare"] != S.LUCRU_IN_LUCRU and acum - (l.get("timp") or 0) > VARSTA_LUCRU:
		return None
	return {"fel": l["fel"], "punct": l["punct"], "stare": l["stare"], "text": S.textLucru(l), "timp": l.get("timp") or 0}


def stareSwap(S=None, hm=None):
	"""Pentru GET /api/swap."""
	S = _s(S)
	active = S.swapuriActive()
	return {
		"result": True,
		"discuri": S.discuri(hm, active),
		"active": active,
		"text_active": S.textActive(active),
		"marime_mb": S.MARIME_MB_IMPLICITA,
		"fisier": S.CALE_SWAPFILE,
		"lucru": _lucruSwap(S),
	}


def activeazaSwap(argumente, S=None, hm=None, consola=None):
	"""POST /api/swap-activeaza: ca Verde pe televizor, dar in doi pasi (pas=intreaba -> intrebarea si codul legat de
	disc; cod= -> fisierul de 512 MB si pornirea; pas=renunta). Un swap deja pornit sau un swapfile.hds care nu e un
	fisier obisnuit se refuza inainte de intrebare (HdsSwap.motivRefuz)."""
	S = _s(S)
	C = _c()
	punct = argumente.get("punct", "")
	if argumente.get("pas") == "renunta":
		C.uita("swap-activeaza", punct)
		return {"result": True, "message": _t("Nu s-a schimbat nimic.")}
	disc = [d for d in S.discuri(hm) if d["punct"] == punct]
	if not disc:
		rez = stareSwap(S, hm)
		rez.update({"result": False, "message": _t("Discul ales nu mai este montat. Alege din nou.")})
		return rez
	motiv = S.motivRefuz(S.caleSwap(punct))
	if motiv:
		rez = stareSwap(S, hm)
		rez.update({"result": False, "message": motiv})
		return rez
	if argumente.get("pas") == "intreaba":
		return C.raspunsIntrebare("swap-activeaza", punct, _t("Pornești swap-ul pe %s?") % disc[0]["nume"],
			_t("Activează swap (512 MB)"), [_t("Calea: %s") % S.caleSwap(punct)])
	if not C.verifica("swap-activeaza", punct, argumente.get("cod", "")):
		rez = stareSwap(S, hm)
		rez.update(C.codGresit())
		return rez
	pornit, text = S.activeaza(punct, consola=consola, hm=hm)
	rez = stareSwap(S, hm)
	rez.update({"result": bool(pornit), "message": text})
	return rez


def opresteSwap(argumente, S=None, hm=None, consola=None):
	"""POST /api/swap-opreste: in doi pasi."""
	S = _s(S)
	C = _c()
	punct = argumente.get("punct", "")
	if argumente.get("pas") == "renunta":
		C.uita("swap-opreste", punct)
		return {"result": True, "message": _t("Nu s-a oprit nimic.")}
	disc = [d for d in S.discuri(hm) if d["punct"] == punct]
	if not disc:
		rez = stareSwap(S, hm)
		rez.update({"result": False, "message": _t("Discul ales nu mai este montat. Alege din nou.")})
		return rez
	if argumente.get("pas") == "intreaba":
		return C.raspunsIntrebare("swap-opreste", punct, _t("Oprești swap-ul de pe %s?") % disc[0]["nume"],
			_t("Da, oprește swap-ul"), [_t("Ce e acum în swap se mută înapoi în memoria receptorului; poate dura puțin.")])
	if not C.verifica("swap-opreste", punct, argumente.get("cod", "")):
		rez = stareSwap(S, hm)
		rez.update(C.codGresit())
		return rez
	pornit, text = S.opreste(punct, consola=consola, hm=hm)
	rez = stareSwap(S, hm)
	rez.update({"result": bool(pornit), "message": text})
	return rez


# ------------------------------------------------------------------ cererile

def argumente(request):
	"""Argumentele cererii ca text scurt, numai cheile stiute, fara token."""
	C = _c()
	rez = C.argumente(request, ("cale", "dosar", "parinte", "valoare", "punct"), MAX_CALE)
	rez.update(C.argumente(request, ("nume",), MAX_NUME))
	rez.update(C.argumente(request, ("rand", "pas", "cod", "lista", "fel", "disc", "sistem"), 40))
	return rez


class _Steaguri(object):
	dosare = [False]


def _peFirImplicit(request, lucru, steag):
	return _c().peFir(request, lucru, steag, TIMP_FIR_S)


def rute(baza, resource, H=None, D=None, S=None, config=None, configfile=None, hm=None, radacini=None, fir=None,
		consola=None, sys_block="/sys/block", mounts=None, inregistrare=None, porneste=None, unelte=None):
	"""({nume: resursa de sub /api}, {nume: resursa pagina}). `baza` e HdsJsonResource din plugin.py. Probele dau
	modulele, setarile, managerul de discuri, radacinile navigarii, firul si consola lor."""
	pe_fir = fir or _peFirImplicit

	def _rad():
		return radacini() if radacini is not None else _h(H).radacini()

	def _apara(obiect, request, lucru):
		try:
			return obiect._raspunde(request, lucru())
		except Exception as eroare:
			return obiect._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	def _refuz(obiect, request):
		refuz = _c().numaiBrowser(request)
		return obiect._eroare(request, refuz, 403) if refuz else None

	class Locuri(baza):
		def render_GET(self, request):
			return _apara(self, request, lambda: stareLocuri(H, config))

	class Dosare(baza):
		def render_GET(self, request):
			if _Steaguri.dosare[0]:
				return self._eroare(request, _t("Receptorul citește deja un dosar. Încearcă din nou peste câteva "
					"secunde."), 503)
			try:
				arg, rad = argumente(request), _rad()
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)
			return pe_fir(request, lambda: listeazaDosare(arg, rad, H), _Steaguri.dosare)

	class Seteaza(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return _apara(self, request, lambda: seteazaLoc(argumente(request), _rad(), H, config, configfile))

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class DosarNou(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return _apara(self, request, lambda: dosarNou(argumente(request), _rad(), H, config))

		def render_GET(self, request):
			return self.render_POST(request)

	class StergeDosar(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return _refuz(self, request) or _apara(self, request, lambda: stergeDosar(argumente(request), _rad(), H,
				config))

		def render_GET(self, request):
			return self.render_POST(request)

	class Scoate(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return _refuz(self, request) or _apara(self, request, lambda: scoateDinLista(argumente(request), H, config,
				configfile))

		def render_GET(self, request):
			return self.render_POST(request)

	class Discuri(baza):
		def render_GET(self, request):
			return _apara(self, request, lambda: stareDiscuri(D, hm, sys_block, mounts, inregistrare, unelte))

	class LucruDisc(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return _refuz(self, request) or _apara(self, request, lambda: lucruDisc(argumente(request), D, hm, sys_block,
				mounts, inregistrare, porneste, unelte))

		def render_GET(self, request):
			return self.render_POST(request)

	class Swap(baza):
		def render_GET(self, request):
			return _apara(self, request, lambda: stareSwap(S, hm))

	class SwapActiveaza(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return _refuz(self, request) or _apara(self, request, lambda: activeazaSwap(argumente(request), S, hm,
				consola))

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token=, deci refuzat

	class SwapOpreste(baza):
		schimbaCeva = True

		def render_POST(self, request):
			return _refuz(self, request) or _apara(self, request, lambda: opresteSwap(argumente(request), S, hm,
				consola))

		def render_GET(self, request):
			return self.render_POST(request)

	def _pagina(functie):
		class Pagina(resource.Resource):
			isLeaf = True

			def render_GET(self, request):
				return _c().pagina(request, functie)
		return Pagina()

	class PaginaDiscuri(resource.Resource):
		"""GET /discuri?f=formatare|verificare: drumul de pe televizor dupa fila ceruta."""
		isLeaf = True

		def render_GET(self, request):
			fel = _c().argumente(request, ("f",), 20).get("f")
			return _c().pagina(request, pagina_verificare if fel == "verificare" else pagina_discuri)

	api = {
		b"locuri-inregistrari": Locuri(),
		b"locuri-inregistrari-dosare": Dosare(),
		b"locuri-inregistrari-seteaza": Seteaza(),
		b"locuri-inregistrari-dosar-nou": DosarNou(),
		b"locuri-inregistrari-sterge-dosar": StergeDosar(),
		b"locuri-inregistrari-scoate": Scoate(),
		b"discuri": Discuri(),
		b"discuri-lucru": LucruDisc(),
		b"swap": Swap(),
		b"swap-activeaza": SwapActiveaza(),
		b"swap-opreste": SwapOpreste(),
	}
	pagini = {
		b"locuri-inregistrari": _pagina(pagina_locuri),
		b"discuri": PaginaDiscuri(),
		b"swap": _pagina(pagina_swap),
	}
	return api, pagini


# ------------------------------------------------------------------ paginile

def _sablon(text, stil, config_pagina, id_intrare):
	C = _c()
	return C.sablon(text, stil, config_pagina, {"__DRUM_MENIU__": C.drumHtml(id_intrare),
		"__SCRIPT_DISC__": _traducePagina(SCRIPT_DISC, "js")})


def pagina_locuri(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_LOCURI), stil, config_pagina, "RecordPaths")


def pagina_discuri(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_DISCURI), stil, config_pagina, "harddisk_init")


def pagina_verificare(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_DISCURI), stil, config_pagina, "harddisk_check")


def pagina_swap(stil, config_pagina):
	return _sablon(_traducePagina(PAGINA_SWAP), stil, config_pagina, "hds_swap_manager")


# stilul propriu al celor trei pagini: tabelele se asaza pe randuri pe telefon, lista dosarelor ca randuri de atins
STIL_DISC = """
  .tabel th{overflow-wrap:normal;word-break:normal;white-space:nowrap;}
  .tabel td.actiuni{white-space:nowrap;text-align:right;}
  .tabel td.actiuni button{margin:2px 0 2px 6px;}
  .mic{color:var(--text-slab);font-size:.8rem;overflow-wrap:anywhere;}
  .legaturi a{color:inherit;}
  .cale{font-family:monospace;overflow-wrap:anywhere;}
  ul.dosare{list-style:none;margin:8px 0 0;padding:0;}
  ul.dosare li{border-bottom:1px solid var(--bordura);}
  ul.dosare li:last-child{border-bottom:0;}
  ul.dosare button{width:100%;text-align:left;border:0;background:transparent;border-radius:0;overflow-wrap:anywhere;}
  .rand .camp{display:flex;flex-wrap:wrap;gap:6px;}
  .file{margin:0 0 12px;}
  .rand .camp select{flex:1 1 160px;min-width:0;}
  @media (max-width:560px){
    .tabel thead{display:none;}
    .tabel, .tabel tbody, .tabel tr, .tabel td{display:block;width:auto;}
    .tabel tr{padding:8px 0;border-bottom:1px solid var(--bordura);}
    .tabel td{border:0;padding:2px 0;}
    .tabel td.actiuni{text-align:left;white-space:normal;padding-top:6px;}
    .tabel td.actiuni button{margin:4px 8px 0 0;}
  }
"""

# ajutoarele comune ale celor trei pagini (dupa SCRIPT_COMUN din meniu_comun_web)
SCRIPT_DISC = r"""
function legaturi(){
  Array.prototype.forEach.call(document.querySelectorAll("a[data-cale]"), function(a){ a.href = adresa(a.getAttribute("data-cale")); });
}
function buton(text, clasa, apasat){
  var b = document.createElement("button"); b.type = "button"; b.textContent = text;
  if(clasa){ b.className = clasa; }
  b.addEventListener("click", apasat);
  return b;
}
function celula(tr, text, clasa){
  var td = document.createElement("td"); td.textContent = text || ""; if(clasa){ td.className = clasa; }
  tr.appendChild(td); return td;
}
var CEAS = null;
function programeaza(functie, ms){ if(CEAS){ clearTimeout(CEAS); } CEAS = setTimeout(functie, ms); }
"""

PAGINA_LOCURI = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Locurile înregistrărilor</title>
<style>__STIL_COMUN__ __STIL_PAGINI__""" + STIL_DISC + """</style>
</head>
<body>
<main>
<h1>Locurile înregistrărilor</h1>
<p class="mesaj" id="incarcare">Se citesc setările...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Unde se salvează</h2>
    <div id="randuri"></div>
    <p class="nota" id="notaExpert">La nivelul Expert (Meniu > Setări > Nivelul setărilor) apar și locul înregistrărilor programate și cel al înregistrărilor imediate.</p>
    <p class="nota">Un dosar în care nu se poate scrie nu se poate alege. Pentru timeshift, sub 1024 MB liberi se cere o confirmare.</p>
  </section>
  <section class="card ascuns" id="cardNavigator">
    <h2 id="titluNavigator"></h2>
    <p class="nota cale" id="caleNavigator"></p>
    <ul class="dosare" id="dosare"></ul>
    <div class="butoane">
      <button type="button" class="principal" id="alegeAici">Alege dosarul acesta</button>
      <button type="button" id="dosarNou">Dosar nou</button>
      <button type="button" class="rosu" id="stergeDosar">Șterge dosarul</button>
      <button type="button" id="inchideNavigator">Renunță</button>
    </div>
    <div class="rand ascuns" id="randNou">
      <label for="numeNou">Numele dosarului nou</label>
      <div class="camp"><input id="numeNou" maxlength="255" autocomplete="off"><button type="button" class="principal" id="faDosar">Fă dosarul</button></div>
    </div>
  </section>
  <section class="card">
    <h2>Dosarele ținute minte</h2>
    <p class="nota">Dosarele alese odată rămân între alegerile rândurilor. Pentru filme și înregistrări:</p>
    <ul class="dosare" id="listaFilme"></ul>
    <p class="nota">Pentru timeshift:</p>
    <ul class="dosare" id="listaTimeshift"></ul>
  </section>
  <p class="nota legaturi">Discul pe care se salvează înregistrările, spațiul liber și discurile conectate sunt în <a data-cale="/stocare" href="/stocare">Locul înregistrărilor</a>; formatarea și verificarea discurilor în <a data-cale="/discuri" href="/discuri">Discurile</a>.</p>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
__SCRIPT_DISC__
var NAV = {rand: null, cale: "", titlu: ""};
function trimite(q){
  mesaj("Se salvează...");
  cerere("/api/locuri-inregistrari-seteaza", "POST", q).then(function(d){
    if(d.confirmare){ arataConfirmarea("/api/locuri-inregistrari-seteaza", q, d.confirmare, dupaSalvare); return; }
    dupaSalvare(d);
  }).catch(nimicNuRaspunde);
}
function dupaSalvare(d){
  mesaj(d.message, !d.result);
  if(d.randuri){ arata(d); }
  if(d.result && d.randuri){ inchideNavigator(); }
}
function rand(r){
  var div = document.createElement("div"); div.className = "rand";
  var l = document.createElement("label"); l.htmlFor = "r_" + r.cheie; l.textContent = r.text;
  var camp = document.createElement("div"); camp.className = "camp";
  var s = document.createElement("select"); s.id = "r_" + r.cheie;
  r.alegeri.forEach(function(a){ var o = document.createElement("option"); o.value = a[0]; o.textContent = a[1]; s.appendChild(o); });
  s.value = r.valoare;
  s.addEventListener("change", function(){ var q = new URLSearchParams(); q.set("rand", r.cheie); q.set("valoare", s.value); trimite(q); });
  camp.appendChild(s);
  camp.appendChild(buton("Alt dosar...", "", function(){ deschideNavigator(r); }));
  div.appendChild(l); div.appendChild(camp);
  return div;
}
function lista(id, valori, cheie){
  var ul = $(id); ul.textContent = "";
  if(!valori.length){ var g = document.createElement("li"); g.className = "nota"; g.textContent = "Niciun dosar."; ul.appendChild(g); return; }
  valori.forEach(function(v){
    var li = document.createElement("li"); li.className = "butoane";
    var s = document.createElement("span"); s.className = "cale"; s.textContent = v; s.style.flex = "1 1 200px"; s.style.alignSelf = "center";
    li.appendChild(s);
    li.appendChild(buton("Scoate din listă", "", function(){ var q = new URLSearchParams(); q.set("lista", cheie); q.set("dosar", v); cuConfirmare("/api/locuri-inregistrari-scoate", q, function(d){ if(d.randuri){ arata(d); } }); }));
    ul.appendChild(li);
  });
}
function arata(d){
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  var c = $("randuri");
  if(!c.contains(document.activeElement)){ c.textContent = ""; d.randuri.forEach(function(r){ c.appendChild(rand(r)); }); }
  $("notaExpert").classList.toggle("ascuns", !!d.expert);
  lista("listaFilme", d.liste.filme || [], "filme");
  lista("listaTimeshift", d.liste.timeshift || [], "timeshift");
}
function citeste(){
  return cerere("/api/locuri-inregistrari").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi setările."; return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function deschideNavigator(r){
  NAV.rand = r.cheie; NAV.titlu = r.titlu_alegere;
  $("titluNavigator").textContent = r.titlu_alegere;
  $("cardNavigator").classList.remove("ascuns");
  var v = r.valoare && r.valoare.charAt(0) === "/" ? r.valoare : "";
  mergi(v, true);
  $("cardNavigator").scrollIntoView({block: "start"});
}
function inchideNavigator(){ $("cardNavigator").classList.add("ascuns"); $("randNou").classList.add("ascuns"); NAV.rand = null; }
function mergi(cale, laInceput){
  cerere("/api/locuri-inregistrari-dosare?cale=" + encodeURIComponent(cale)).then(function(d){
    if(!d.result){ if(laInceput && cale){ mergi("", false); return; } mesaj(d.message, true); return; }
    NAV.cale = d.cale;
    var t = d.cale ? d.cale : "Discurile montate";
    if(d.cale && d.liber_mb !== null && d.liber_mb !== undefined){ t += " (liber: " + d.liber_mb + " MB)"; }
    $("caleNavigator").textContent = t;
    var ul = $("dosare"); ul.textContent = "";
    if(d.cale){
      var li = document.createElement("li");
      li.appendChild(buton(d.parinte ? "< Dosarul de deasupra >" : "< Lista discurilor >", "", function(){ mergi(d.parinte || "", false); }));
      ul.appendChild(li);
    }
    d.dosare.forEach(function(x){ var li = document.createElement("li"); li.appendChild(buton(x.nume, "", function(){ mergi(x.cale, false); })); ul.appendChild(li); });
    if(!d.dosare.length){ var g = document.createElement("li"); g.className = "nota"; g.textContent = d.cale ? "Niciun dosar aici." : "Niciun disc montat."; ul.appendChild(g); }
    $("alegeAici").disabled = !d.cale; $("dosarNou").disabled = !d.cale; $("stergeDosar").disabled = !d.cale || !d.parinte;
  }).catch(nimicNuRaspunde);
}
$("alegeAici").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("rand", NAV.rand); q.set("dosar", NAV.cale); trimite(q); });
$("dosarNou").addEventListener("click", function(){ $("randNou").classList.remove("ascuns"); $("numeNou").focus(); });
$("faDosar").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("parinte", NAV.cale); q.set("nume", $("numeNou").value);
  cerere("/api/locuri-inregistrari-dosar-nou", "POST", q).then(function(d){
    mesaj(d.message, !d.result);
    if(d.result){ $("numeNou").value = ""; $("randNou").classList.add("ascuns"); mergi(d.cale, false); }
  }).catch(nimicNuRaspunde);
});
$("stergeDosar").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("cale", NAV.cale);
  cuConfirmare("/api/locuri-inregistrari-sterge-dosar", q, function(d){ if(d.result){ mergi(d.parinte ? d.parinte + "/" : "", false); citeste(); } });
});
$("inchideNavigator").addEventListener("click", inchideNavigator);
legaturi();
citeste();
</script>
</body>
</html>
"""

PAGINA_DISCURI = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Discurile</title>
<style>__STIL_COMUN__ __STIL_PAGINI__""" + STIL_DISC + """</style>
</head>
<body>
<main>
<h1>Discurile</h1>
<p class="mesaj" id="incarcare">Se citesc discurile...</p>
<div id="continut" class="ascuns">
  <div class="butoane file">
    <button type="button" id="filaFormatare" aria-pressed="false">Formatare</button>
    <button type="button" id="filaVerificare" aria-pressed="false">Verificare</button>
  </div>
  <section class="card ascuns" id="cardLucru">
    <h2>Lucrarea de acum</h2>
    <p class="intrebare" id="lucruText"></p>
    <p class="nota" id="lucruTimp"></p>
  </section>
  <section class="card">
    <h2>Hard diskurile și stick-urile USB</h2>
    <p class="nota" id="explicatie"></p>
    <p class="nota" id="gol">Niciun hard disk și niciun stick USB găsit.</p>
    <table class="tabel" id="tabel"><thead><tr><th>Discul</th><th>Felul</th><th>Capacitatea</th><th>Partițiile</th><th></th></tr></thead><tbody id="discuri"></tbody></table>
    <p class="nota">Apar hard diskurile și stick-urile USB, ca pe televizor. Memoria internă și discul de pe care pornește sistemul nu apar niciodată.</p>
    <p class="nota eroare ascuns" id="notaOpriri"></p>
  </section>
  <p class="nota">Din pagină, formatarea și verificarea nu pornesc cât o înregistrare e în curs sau începe în mai puțin de <span id="prag">10</span> minute, nici cât discul e folosit de swap, de timeshift, de o înregistrare sau de un film care se redă: între timp discul nu e montat și o înregistrare de pe el s-ar pierde. Pe televizor întrebarea spune același lucru și alegi tu.</p>
  <p class="nota legaturi">Discul pe care se salvează înregistrările este în <a data-cale="/stocare" href="/stocare">Locul înregistrărilor</a>; fișierul de swap în <a data-cale="/swap" href="/swap">Fișier de swap</a>.</p>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
__SCRIPT_DISC__
var FILA = new URLSearchParams(location.search).get("f") === "verificare" ? "verificare" : "formatare";
var ULTIMA = null;
var ALES = {};
var EXPLICATII = {
  formatare: "Formatarea face pe disc o singură partiție și dosarul movie: ext4 pe un hard disk; pe un stick USB alegi FAT32 (se citește pe orice calculator, fișiere de cel mult 4 GB) sau ext4 (pentru înregistrări și timeshift). Toate datele de pe disc se pierd; întrebarea spune pe nume ce e pe el.",
  verificare: "Verificarea rulează fsck.ext4 sau fsck.fat pe fiecare partiție și repară singură ce poate. Discul se demontează cât ține verificarea, apoi se montează la loc."
};
function alegeFila(f){
  FILA = f;
  [["filaFormatare", "formatare"], ["filaVerificare", "verificare"]].forEach(function(x){
    $(x[0]).setAttribute("aria-pressed", f === x[1] ? "true" : "false");
    $(x[0]).classList.toggle("principal", f === x[1]);
  });
  $("explicatie").textContent = EXPLICATII[f];
  try{ history.replaceState(null, "", "?f=" + f + (CFG.jeton ? "&token=" + encodeURIComponent(CFG.jeton) : "")); }catch(e){}
  if(ULTIMA){ arata(ULTIMA); }
}
function inLucru(d){ return d.lucru && d.lucru.stare === "in_lucru"; }
function alegereSistem(k, oprit){
  var s = document.createElement("select"); s.setAttribute("aria-label", "Sistemul de fișiere pentru " + k.model);
  (k.sisteme || []).forEach(function(x){ var o = document.createElement("option"); o.value = x[0]; o.textContent = x[1]; o.title = x[2]; s.appendChild(o); });
  if(ALES[k.dispozitiv]){ s.value = ALES[k.dispozitiv]; }
  ALES[k.dispozitiv] = s.value;
  s.addEventListener("change", function(){ ALES[k.dispozitiv] = s.value; });
  s.disabled = oprit;
  return s;
}
function arata(d){
  ULTIMA = d;
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  var ocupat = inLucru(d);
  var opriri = d.opriri || [];
  var l = d.lucru;
  $("cardLucru").classList.toggle("ascuns", !l);
  if(l){
    $("lucruText").textContent = (l.text_disc ? l.text_disc + ": " : "") + l.text;
    $("lucruText").classList.toggle("eroare", l.stare === "eroare");
    $("lucruTimp").textContent = ocupat ? ("În lucru de " + l.secunde + " s. Nu scoate discul și nu opri receptorul.") : ("A durat " + l.secunde + " s.");
  }
  if(d.prag_minute){ $("prag").textContent = String(d.prag_minute); }
  var corp = $("discuri"); corp.textContent = "";
  d.discuri.forEach(function(k){
    var tr = document.createElement("tr");
    var n = celula(tr, k.model);
    var mic = document.createElement("div"); mic.className = "mic"; mic.textContent = "/dev/" + k.dispozitiv; n.appendChild(mic);
    celula(tr, k.felul + " (" + k.magistrala_text + ")"); celula(tr, k.capacitate);
    var p = celula(tr, "");
    if(!k.partitii.length){ p.textContent = "niciuna"; }
    k.partitii.forEach(function(x){ var r = document.createElement("div"); r.textContent = x.nume + (x.montare.length ? " în " + x.montare.join(", ") : " (nemontată)"); p.appendChild(r); });
    var a = celula(tr, "", "actiuni");
    var oprit = ocupat || opriri.length > 0;
    var b;
    if(FILA === "formatare"){
      if(k.detasabil && (k.sisteme || []).length > 1){ a.appendChild(alegereSistem(k, oprit)); }
      b = buton(k.detasabil ? "Formatează" : "Inițializează", "rosu", function(){ lucreaza(k); });
    } else {
      b = buton("Verifică", "principal", function(){ lucreaza(k); });
    }
    b.disabled = oprit; a.appendChild(b);
    corp.appendChild(tr);
  });
  var are = d.discuri.length > 0;
  $("tabel").classList.toggle("ascuns", !are); $("gol").classList.toggle("ascuns", are);
  $("notaOpriri").textContent = opriri.length ? "Acum nu se poate din pagină: " + opriri.join(" ") : "";
  $("notaOpriri").classList.toggle("ascuns", !opriri.length);
  programeaza(citeste, ocupat ? 2000 : 15000);
}
function citeste(){
  return cerere("/api/discuri").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi discurile."; programeaza(citeste, 15000); return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; programeaza(citeste, 15000); });
}
function lucreaza(k){
  var q = new URLSearchParams(); q.set("disc", k.dispozitiv); q.set("fel", FILA);
  if(FILA === "formatare"){ q.set("sistem", ALES[k.dispozitiv] || ((k.sisteme || [["ext4"]])[0][0])); }
  cuConfirmare("/api/discuri-lucru", q, function(d){ if(d.discuri){ arata(d); } else { citeste(); } });
}
$("filaFormatare").addEventListener("click", function(){ alegeFila("formatare"); });
$("filaVerificare").addEventListener("click", function(){ alegeFila("verificare"); });
alegeFila(FILA);
legaturi();
citeste();
</script>
</body>
</html>
"""

PAGINA_SWAP = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fișier de swap</title>
<style>__STIL_COMUN__ __STIL_PAGINI__""" + STIL_DISC + """</style>
</head>
<body>
<main>
<h1>Fișier de swap (memorie virtuală)</h1>
<p class="mesaj" id="incarcare">Se citesc discurile...</p>
<div id="continut" class="ascuns">
  <section class="card ascuns" id="cardLucru">
    <h2>Lucrarea de acum</h2>
    <p class="intrebare" id="lucruText"></p>
  </section>
  <section class="card">
    <h2>Discurile montate</h2>
    <p class="nota" id="gol">Niciun disc HDD/USB montat momentan.</p>
    <table class="tabel" id="tabel"><thead><tr><th>Discul</th><th>Swap</th><th></th></tr></thead><tbody id="discuri"></tbody></table>
    <p class="nota" id="active"></p>
  </section>
  <p class="nota">Activarea face în rădăcina discului ales fișierul <span id="fisier"></span> de <span id="marime"></span> MB și îl pornește ca memorie virtuală. Swap-ul nu repornește singur după o repornire a receptorului.</p>
  <p class="nota legaturi">Discurile conectate și locul înregistrărilor sunt în <a data-cale="/stocare" href="/stocare">Locul înregistrărilor</a>.</p>
  <p class="mesaj" id="mesaj"></p>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Aceleași setări sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
__SCRIPT_DISC__
function inLucru(d){ return d.lucru && d.lucru.stare === "in_lucru"; }
function arata(d){
  $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
  var ocupat = inLucru(d);
  $("cardLucru").classList.toggle("ascuns", !d.lucru);
  if(d.lucru){ $("lucruText").textContent = d.lucru.text; $("lucruText").classList.toggle("eroare", d.lucru.stare === "eroare"); }
  var corp = $("discuri"); corp.textContent = "";
  d.discuri.forEach(function(k){
    var tr = document.createElement("tr");
    var n = celula(tr, k.nume);
    var mic = document.createElement("div"); mic.className = "mic"; mic.textContent = k.punct; n.appendChild(mic);
    celula(tr, k.activ ? "ACTIV" : "inactiv");
    var a = celula(tr, "", "actiuni");
    var act = buton("Activează swap (" + d.marime_mb + " MB)", "principal", function(){ activeaza(k); });
    var op = buton("Oprește swap", "rosu", function(){ opreste(k); });
    act.disabled = ocupat || k.activ; op.disabled = ocupat || !k.activ;
    a.appendChild(act); a.appendChild(op);
    corp.appendChild(tr);
  });
  var are = d.discuri.length > 0;
  $("tabel").classList.toggle("ascuns", !are); $("gol").classList.toggle("ascuns", are);
  $("active").textContent = d.text_active || "";
  $("fisier").textContent = d.fisier; $("marime").textContent = d.marime_mb;
  programeaza(citeste, ocupat ? 1000 : 10000);
}
function citeste(){
  return cerere("/api/swap").then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi discurile."; programeaza(citeste, 10000); return; }
    arata(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; programeaza(citeste, 10000); });
}
function activeaza(k){
  var q = new URLSearchParams(); q.set("punct", k.punct);
  cuConfirmare("/api/swap-activeaza", q, function(d){ if(d.discuri){ arata(d); } else { citeste(); } });
}
function opreste(k){
  var q = new URLSearchParams(); q.set("punct", k.punct);
  cuConfirmare("/api/swap-opreste", q, function(d){ if(d.discuri){ arata(d); } else { citeste(); } });
}
legaturi();
citeste();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire."""
	return text


TEXTE_PAGINA = {
	"html": (
		N_("Locurile înregistrărilor"),
		N_("Se citesc setările..."),
		N_("Unde se salvează"),
		N_("La nivelul Expert (Meniu > Setări > Nivelul setărilor) apar și locul înregistrărilor programate "
			"și cel al înregistrărilor imediate."),
		N_("Un dosar în care nu se poate scrie nu se poate alege. Pentru timeshift, sub 1024 MB liberi se "
			"cere o confirmare."),
		N_("Alege dosarul acesta"),
		N_("Dosar nou"),
		N_("Șterge dosarul"),
		N_("Renunță"),
		N_("Numele dosarului nou"),
		N_("Fă dosarul"),
		N_("Dosarele ținute minte"),
		N_("Dosarele alese odată rămân între alegerile rândurilor. Pentru filme și înregistrări:"),
		N_("Pentru timeshift:"),
		N_("Discul pe care se salvează înregistrările, spațiul liber și discurile conectate sunt în <a "
			"data-cale=\"/stocare\" href=\"/stocare\">Locul înregistrărilor</a>; formatarea și verificarea "
			"discurilor în <a data-cale=\"/discuri\" href=\"/discuri\">Discurile</a>."),
		N_("Aceleași setări sunt pe televizor, în __DRUM_MENIU__."),
		N_("Discurile"),
		N_("Se citesc discurile..."),
		N_("Formatare"),
		N_("Verificare"),
		N_("Lucrarea de acum"),
		N_("Hard diskurile și stick-urile USB"),
		N_("Niciun hard disk și niciun stick USB găsit."),
		N_("Discul"),
		N_("Felul"),
		N_("Capacitatea"),
		N_("Partițiile"),
		N_("Apar hard diskurile și stick-urile USB, ca pe televizor. Memoria internă și discul de pe care "
			"pornește sistemul nu apar niciodată."),
		N_("Din pagină, formatarea și verificarea nu pornesc cât o înregistrare e în curs sau începe în mai "
			"puțin de <span id=\"prag\">10</span> minute, nici cât discul e folosit de swap, de timeshift, de "
			"o înregistrare sau de un film care se redă: între timp discul nu e montat și o înregistrare de "
			"pe el s-ar pierde. Pe televizor întrebarea spune același lucru și alegi tu."),
		N_("Discul pe care se salvează înregistrările este în <a data-cale=\"/stocare\" href=\"/stocare\">Locul "
			"înregistrărilor</a>; fișierul de swap în <a data-cale=\"/swap\" href=\"/swap\">Fișier de swap</a>."),
		N_("Fișier de swap"),
		N_("Fișier de swap (memorie virtuală)"),
		N_("Discurile montate"),
		N_("Niciun disc HDD/USB montat momentan."),
		N_("Swap"),
		N_("Activarea face în rădăcina discului ales fișierul <span id=\"fisier\"></span> de <span "
			"id=\"marime\"></span> MB și îl pornește ca memorie virtuală. Swap-ul nu repornește singur după o "
			"repornire a receptorului."),
		N_("Discurile conectate și locul înregistrărilor sunt în <a data-cale=\"/stocare\" "
			"href=\"/stocare\">Locul înregistrărilor</a>."),
	),
	"js": (
		N_("Se salvează..."),
		N_("Alt dosar..."),
		N_("Niciun dosar."),
		N_("Scoate din listă"),
		N_("Receptorul nu a putut citi setările."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Discurile montate"),
		N_("< Dosarul de deasupra >"),
		N_("< Lista discurilor >"),
		N_("Niciun dosar aici."),
		N_("Niciun disc montat."),
		N_("Formatarea face pe disc o singură partiție și dosarul movie: ext4 pe un hard disk; pe un stick "
			"USB alegi FAT32 (se citește pe orice calculator, fișiere de cel mult 4 GB) sau ext4 (pentru "
			"înregistrări și timeshift). Toate datele de pe disc se pierd; întrebarea spune pe nume ce e pe "
			"el."),
		N_("Verificarea rulează fsck.ext4 sau fsck.fat pe fiecare partiție și repară singură ce poate. "
			"Discul se demontează cât ține verificarea, apoi se montează la loc."),
		N_("Sistemul de fișiere pentru"),
		N_("În lucru de"),
		N_("s. Nu scoate discul și nu opri receptorul."),
		N_("A durat"),
		N_("în"),
		N_("(nemontată)"),
		N_("Formatează"),
		N_("Inițializează"),
		N_("Verifică"),
		N_("Acum nu se poate din pagină:"),
		N_("Receptorul nu a putut citi discurile."),
		N_("Activează swap ("),
		N_("Oprește swap"),
	),
}


def _traducePagina(sablon, fel="pagina"):
	"""Sablonul in limba receptorului; fara pachetul HdsWebControl (probele de pe PC), sablonul ca atare."""
	try:
		from .traducere_pagini import traduce
	except ImportError:
		return sablon
	return traduce(sablon, TEXTE_PAGINA, fel)
# ---------------------------------------------------------------- sfarsitul traducerii paginilor
