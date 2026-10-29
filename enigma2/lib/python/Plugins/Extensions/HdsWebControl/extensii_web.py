# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# extensii_web.py: "Extensii și aplicații" in interfata web (HdsWebControl), perechea ecranului de pe televizor
# Meniu > Extensii si aplicatii (Screens/PluginBrowser.py = Screens/HdsExtensii.py, entryID plugin_selection).
#
# Aceleasi file (Pe receptor, Actualizari, categoriile din surse, Din fisier, Surse, cautarea), aceleasi randuri cu
# aceleasi insigne si detalii, aceleasi actiuni (instalare, actualizare, actualizeaza tot, stergere, fisier .ipk de pe
# un disc al receptorului, sursele adaugate sau sterse, descarcarea listei, repornirea interfetei, pornirea unei
# extensii pe televizor), din aceeasi logica: Components/HdsExtensiiLucru.py (randurile, planurile, sursele, lucrarea
# opkg, cate una odata pentru televizor si pagina) si Components/HdsPachete.py (datele din fisierele opkg). Ce schimba
# pachetele sau sursele se face in doi pasi (intrebarea cu acelasi sens ca pe televizor, apoi codul), numai din
# browserul conectat. Actualizarile imaginii sunt in /actualizari (actualizari_web.py): aici numai legatura.
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/extensii?fila=<id>&cauta=<text>          filele, randurile filei, lista, cautarea fisierelor, lucrarea
#   POST /api/extensii-instaleaza?pachet=<nume>         pas=intreaba -> intrebarea; cod=<cod> -> opkg install
#   POST /api/extensii-actualizeaza?pachet=<nume>|tot=1 la fel, opkg upgrade (tot: fila Actualizari)
#   POST /api/extensii-sterge?pachet=<nume>             la fel, opkg remove --autoremove
#   POST /api/extensii-fisier?cale=<cale>               la fel, opkg install <fisier>; numai un fisier gasit la cautare
#   POST /api/extensii-sursa-adauga?nume=..&adresa=..   la fel; apoi se descarca lista
#   POST /api/extensii-sursa-sterge?nume=<nume>         la fel; numai sursele adaugate de utilizator
#   POST /api/extensii-sursa-afla?pachet=<nume>         sursa deschisa a unui plugin (0.6.6): marimea si locul, pe un
#                                                       fir; starea vine in GET /api/extensii ("sursa")
#   POST /api/extensii-sursa-descarca?pachet=<nume>     in doi pasi (intrebarea cu marimea si locul), apoi descarcarea
#                                                       pe stick sau disc (Components/HdsSursaPachet.py)
#   POST /api/extensii-sursa-opreste                    opreste descarcarea sursei (fisierul partial se sterge)
#   GET  /api/extensii-sursa-fisier                     arhiva descarcata ultima, data browserului
#   POST /api/extensii-reporneste                       la fel; repornirea interfetei (TryQuitMainloop 3)
#   POST /api/extensii-opreste                          la fel; opreste opkg numai dupa un minut fara raspuns
#   POST /api/extensii-descarca-lista                   opkg update
#   POST /api/extensii-cauta-fisiere?retea=0|1          cauta fisiere .ipk pe stick, disc, memorie (sau in retea)
#   POST /api/extensii-deschide?plugin=<n>&nume=<nume>  extensia instalata se deschide pe televizor (ca OK)
#   GET  /extensii                                      pagina
#
# FIRUL: totul ruleaza pe firul enigma2 si e scurt; singurul lucru lung, citirea catalogului (fisierele opkg, cu
# surse externe pot fi mai multi MB), se face pe un fir separat (meniu_comun_web.peFir), iar catalogul se tine minte in
# Components/HdsExtensiiLucru.py pana la urmatoarea schimbare. opkg ruleaza ca pe televizor (Components/Ipkg.py,
# eConsoleAppContainer, lista de argumente). Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau
# un Mediu fals.

import os

ARGUMENTE = ("fila", "cauta", "pachet", "tot", "cale", "retea", "nume", "adresa", "plugin", "pas", "cod", "feed", "fel")
LUNGIMI = {"cale": 1024, "adresa": 300, "cauta": 120, "nume": 120, "feed": 80}
_INCARCARE = [False]      # citirea catalogului pe fir: una singura odata
_FISIERE = {"local": None, "retea": None}   # ultimele cautari terminate, ca ecranul: lista ramane pana vine alta


def _t(text):
	from .meniu_comun_web import _t as t
	return t(text)


def _comun():
	from . import meniu_comun_web
	return meniu_comun_web


class Mediu(object):
	"""Ce foloseste pagina pe receptor: componenta, pluginurile, sesiunea. Probele de pe PC dau unul fals."""

	def __init__(self, L=None, plugins=None, pluginuri=None, sesiune=None, ocupat=None, modSigur=None,
			reporneste=None, peFir=None):
		self._L, self._plugins, self._pluginuri = L, plugins, pluginuri
		self._sesiune, self._ocupat, self._modSigur = sesiune, ocupat, modSigur
		self._reporneste, self._peFir = reporneste, peFir

	@property
	def L(self):
		if self._L is None:
			from Components import HdsExtensiiLucru
			self._L = HdsExtensiiLucru
		return self._L

	@property
	def P(self):
		return self.L.P

	@property
	def S(self):
		return self.L.S

	@property
	def plugins(self):
		if self._plugins is None:
			from Components.PluginComponent import plugins
			self._plugins = plugins
		return self._plugins

	def pluginuri(self):
		"""extensiile din fila Pe receptor: aceeasi lista ca ecranul (WHERE_PLUGINMENU)"""
		if self._pluginuri is not None:
			return list(self._pluginuri())
		from Plugins.Plugin import PluginDescriptor
		return list(self.plugins.getPlugins(PluginDescriptor.WHERE_PLUGINMENU))

	def program(self):
		return self.L.opkgProgram()

	def sesiune(self):
		return self._sesiune() if self._sesiune is not None else _comun().sesiune()

	def ocupat(self, s):
		return self._ocupat(s) if self._ocupat is not None else _comun().ocupat(s)

	def textModSigur(self):
		if self._modSigur is not None:
			return self._modSigur()
		try:
			from Components import HdsModSigur
			return HdsModSigur.textPentruExtensii()
		except Exception:
			return ""

	def reporneste(self, s):
		if self._reporneste is not None:
			return self._reporneste(s)
		from .tema_tv_web import reporneste
		return reporneste(s)

	def peFir(self, request, lucru, steag, timeout_s):
		if self._peFir is not None:
			return self._peFir(request, lucru, steag, timeout_s)
		return _comun().peFir(request, lucru, steag, timeout_s)


def argumente(request):
	"""{cheie: text} numai pentru cheile stiute (fara token), fiecare cu lungimea ei"""
	rez = _comun().argumente(request, ARGUMENTE, 1024)
	for cheie in list(rez):
		rez[cheie] = rez[cheie][:LUNGIMI.get(cheie, 64)]
	return rez


# ------------------------------------------------------------------ starea paginii

def _cautariFisiere(M):
	"""{'local': CautareIpk sau None, 'retea': ...}: cele in curs sau ultimele (ale ecranului sau ale paginii)"""
	rez = {}
	for fel, retea in (("local", False), ("retea", True)):
		c = M.P.ultima_cautare(retea)
		if c is not None and c.gata:
			_FISIERE[fel] = c
		rez[fel] = c
	return rez


def _fisiereGasite():
	"""[FisierIpk]: cele de pe stick, disc si memorie, apoi cele din retea (ca in fila Din fisier de pe televizor)"""
	rez = []
	for fel in ("local", "retea"):
		c = _FISIERE[fel]
		if c is not None:
			rez += list(c.fisiere or [])
	return rez


def _stareCautari(M, cautari):
	P = M.P
	loc, ret = cautari["local"], cautari["retea"]
	gata_loc, gata_ret = _FISIERE["local"], _FISIERE["retea"]

	def lent(c):
		return c is not None and not c.gata and P._ceas() - c.pornit > 10
	return {
		"niciuna": loc is None and gata_loc is None,
		"in_curs": loc is not None and not loc.gata,
		"retea_in_curs": ret is not None and not ret.gata,
		"lent": lent(loc) or lent(ret),
		"gasite": len(gata_loc.fisiere) if gata_loc is not None else None,
		"taiate": bool(gata_loc is not None and gata_loc.taiat),
		"retea_gasite": len(gata_ret.fisiere) if gata_ret is not None else None,
		"locuri_retea": list(gata_loc.locuri_retea) if gata_loc is not None else [],
	}


def _stareLucrare(L):
	l = L.STARE["lucrare"]
	if l is None:
		return None
	r = l.rezultat or {}
	return {"fel": l.plan.get("fel"), "nume": l.plan.get("nume", ""), "faza": l.faza, "din_web": l.din_web,
		"titlu": l.titluLucru() if l.faza == "lucru" else r.get("titlu", ""), "pas": l.pas,
		"jurnal": [[f, t] for f, t in l.jurnal[-12:]], "rezultat": r or None, "poate_opri": l.poateOpri(),
		"secunde_fara_raspuns": l.secundeFaraRaspuns()}


def _indice(pluginuri, plugin):
	"""locul extensiei in lista (dupa obiect: doua intrari ale aceluiasi plugin au aceeasi functie)"""
	for i, x in enumerate(pluginuri):
		if x is plugin:
			return i
	return -1


def _actiuni(L, catalog, fel, obj, extra, pluginuri):
	"""butoanele randului, din aceleasi taste ca pe televizor (HdsExtensiiLucru.taste)"""
	rosu, verde = L.taste(catalog, fel, obj, extra, pluginuri)
	rez = []
	if fel == "plugin":
		rez.append({"f": "deschide", "text": _t("Deschide pe televizor"), "plugin": _indice(pluginuri, obj),
			"nume": obj.name or ""})
		if verde == "Actualizează":
			rez.append({"f": "actualizeaza", "text": _t(verde), "pachet": extra.nume, "principal": True})
		if rosu:
			rez.append({"f": "sterge", "text": _t(rosu), "pachet": extra.nume, "rosu": True})
	elif fel == "pachet":
		if verde == "Repornește interfața":
			rez.append({"f": "reporneste", "text": _t(verde), "principal": True})
		elif verde == "Actualizează":
			rez.append({"f": "actualizeaza", "text": _t(verde), "pachet": obj.nume, "principal": True})
		elif verde == "Instalează":
			rez.append({"f": "instaleaza", "text": _t(verde), "pachet": obj.nume, "principal": True})
		elif verde == L.BUTON_INLOCUITOR:
			# pachet numai pentru Python 2 (0.6.8): butonul instaleaza direct inlocuitorul pentru Python 3
			rez.append({"f": "instaleaza", "text": _t(verde), "pachet": L.inlocuitorRand(catalog, fel, obj, extra)[0].nume,
				"principal": True})
		elif verde == "Deschide":
			pl = L.pluginPentru(pluginuri, obj)
			rez.append({"f": "deschide", "text": _t("Deschide pe televizor"), "plugin": _indice(pluginuri, pl),
				"nume": pl.name or ""})
		if rosu:
			rez.append({"f": "sterge", "text": _t(rosu), "pachet": obj.nume, "rosu": True})
	elif fel == "fisier":
		if verde == L.BUTON_INLOCUITOR:
			rez.append({"f": "instaleaza", "text": _t(verde), "pachet": L.inlocuitorRand(catalog, fel, obj, extra)[0].nume,
				"principal": True})
		elif verde:
			rez.append({"f": "fisier", "text": _t("Instalează fișierul"), "cale": obj.cale, "principal": True})
	elif fel == "sursa":
		rez.append({"f": "descarca", "text": _t("Descarcă lista")})
		if rosu:
			rez.append({"f": "sursa-sterge", "text": _t(rosu), "nume": obj[0], "rosu": True})
	elif fel == "feed":
		rez.append({"f": "descarca", "text": _t("Descarcă lista")})
	elif fel == "adauga":
		rez.append({"f": "adauga", "text": _t("Adaugă o sursă"), "principal": True})
	# 0.6.6: sursa deschisa a pluginului, numai cand pachetul are arhiva ei langa el in feed
	p = L.pachetCuSursa(catalog, fel, obj, extra)
	if p is not None:
		rez.append({"f": "sursa", "text": _t("Descarcă sursa"), "pachet": p.nume})
	return rez


def _cheie(fel, obj, pluginuri):
	if fel == "plugin":
		return "plugin:%d" % _indice(pluginuri, obj)
	if fel == "pachet":
		return "pachet:" + obj.nume
	if fel == "fisier":
		return "fisier:" + obj.cale_text
	if fel == "sursa":
		return "sursa:" + obj[0]
	if fel == "feed":
		return "feed:" + obj.id
	return fel


def _rand(M, catalog, fel, obj, extra, pluginuri):
	L, P = M.L, M.P
	_ic, titlu, sub, insigna, culoare, mic = L.descriereRand(catalog, fel, obj, extra)
	d = L.detalii(catalog, fel, obj, extra)
	return {"fel": fel, "cheie": _cheie(fel, obj, pluginuri), "titlu": P._curat(titlu, 200),
		"subtitlu": P._curat(sub, 300), "insigna": insigna or "", "culoare": culoare or "", "mic": mic or "",
		"detalii": {"insigna": d["insigna"], "culoare": d["culoare"],
			"randuri": [[a, P._curat(b, 400)] for a, b in zip(d["etichete"], d["valori"])],
			"descriere": P._curat(d["descriere"], 1500)},
		"actiuni": _actiuni(L, catalog, fel, obj, extra, pluginuri)}


def datePrincipale(M):
	"""ce se citeste numai pe firul enigma2: pluginurile, modul sigur, opkg, repornirea ceruta, avertismentele"""
	plugins = M.plugins
	return {"pluginuri": M.pluginuri(), "mod_sigur": M.textModSigur(), "opkg": bool(M.program()),
		"restart": bool(getattr(plugins, "restartRequired", False)),
		"avertismente": [[str(n), M.P._curat(str(e), 160)] for n, e in list(getattr(plugins, "warnings", None) or [])[:6]]}


def stare(arg, M, catalog, date=None):
	"""Corpul lui GET /api/extensii"""
	L, P = M.L, M.P
	date = date or datePrincipale(M)
	pluginuri = date["pluginuri"]
	cauta = P._curat(arg.get("cauta", ""), 40).replace("\n", " ").strip()
	cautari = _cautariFisiere(M)
	fisiere = _fisiereGasite()
	gasite = _FISIERE["local"] is not None or _FISIERE["retea"] is not None
	file = []
	if cauta:
		file.append(("cautare", _t("Căutare: %s") % cauta, len(L.randuriCautare(catalog, pluginuri, cauta))))
	file += L.file(catalog, len(pluginuri) + len(L.dupaRepornire(catalog, M.plugins)))
	file.append(("fisiere", _t("Din fișier"), len(fisiere) if gasite else None))
	file.append(L.filaSurse(catalog))
	ids = [f[0] for f in file]
	fila = arg.get("fila") or ("cautare" if cauta else "instalate")
	if fila not in ids:
		fila = "cautare" if cauta else "instalate"
	filtru = _filtruCerut(arg)
	filtruWeb = None
	if fila == "fisiere":
		randuri = [("fisier", f, None) for f in fisiere]
	else:
		toateRandurile = L.randuri(catalog, fila, pluginuri, M.plugins, cauta)
		randuri = L.filtreaza(catalog, toateRandurile, filtru, fila)
		filtruWeb = _filtruWeb(L, catalog, toateRandurile, randuri, filtru, fila)
	conf = catalog.configurare
	if not conf.surse:
		lista = _t("Nicio sursă de pachete")
	elif not catalog.surse_cu_lista:
		lista = _t("Lista nu a fost descărcată")
	else:
		lista = _t("Lista din %s") % P.text_varsta(catalog.varsta_liste)
	ultima = L.STARE.get("descarcare") or {}
	lucrare = _stareLucrare(L)
	toate = catalog.actualizari()
	cf = _stareCautari(M, cautari)
	descarcare = L.descarcareInCurs()
	sursa = _stareSursa(M)
	return {
		"result": True,
		"file": [{"id": i, "eticheta": e, "numar": n} for i, e, n in file],
		"fila": fila,
		"cauta": cauta,
		"randuri": [_rand(M, catalog, fel, o, x, pluginuri) for fel, o, x in randuri],
		# toate actualizarile, si cand filtrul arata numai o parte (butonul spune "toate", ca MENU pe televizor)
		"tot": [o.nume for o in catalog.actualizari()] if fila == "actualizari" else [],
		"filtru": filtruWeb,
		"gol": _textGol(fila, cauta, conf.surse, cf),
		"lista": lista,
		"surse": len(conf.surse),
		"mod_sigur": date["mod_sigur"] if fila == "instalate" else "",
		"opkg": date["opkg"],
		"repornire_ceruta": date["restart"] or bool(lucrare and (lucrare["rezultat"] or {}).get("repornire")),
		"avertismente": date["avertismente"],
		"descarcare": {"in_curs": descarcare, "cod": ultima.get("cod"), "motiv": ultima.get("motiv", ""),
			"cand": P.text_varsta(ultima.get("cand")) if ultima.get("cand") else "",
			# ce contine lista descarcata ultima oara (0.6.6), acelasi text ca pe televizor
			"rezumat": L.textDescarcare(catalog, ultima, ultima.get("inainte")) if ultima.get("cand") and not descarcare
			else "", "id": int(ultima.get("cand") or 0)},
		# Actualizeaza toate (0.6.6): din orice fila, cand sunt cel putin doua
		"toate": len(toate), "text_toate": _t("Actualizează toate (%d)") % len(toate) if len(toate) >= 2 else "",
		"cautare_fisiere": cf,
		"lucrare": lucrare,
		"sursa": sursa,
		"lucreaza": descarcare or cf["in_curs"] or cf["retea_in_curs"] or bool(lucrare and lucrare["faza"] == "lucru") or
			bool(sursa and sursa["faza"] in ("marime", "lucru")),
	}


def _filtruCerut(arg):
	"""filtrul din adresa paginii (feed=, fel=): numai litere, cifre si . _ : -"""
	rez = {}
	for cheie in ("feed", "fel"):
		v = (arg.get(cheie) or "").strip()
		rez[cheie] = v if v and all(c.isalnum() or c in "._:-" for c in v) else ""
	return rez


def _filtruWeb(L, catalog, toate, aratate, filtru, fila):
	"""filtrul listei pentru pagina (aceleasi alegeri ca randul filtrului de pe televizor), sau None cand fila nu are
	pachete si filtrul nu e activ; textele vin traduse"""
	if not L.areFiltru(fila):
		return None
	total = sum(1 for r in toate if r[0] in ("plugin", "pachet"))
	if not total and not L.filtruActiv(filtru, fila):
		return None
	feeduri, feluri = L.alegeriFiltru(catalog, toate, fila)
	if filtru.get("feed") and filtru["feed"] not in [k for k, _t_ in feeduri]:
		feeduri.append((filtru["feed"], "%s (0)" % L.numeFeedFiltru(filtru["feed"])))
	fel = filtru.get("fel", "") if fila in L.FILE_AMESTECATE else ""
	if fel and fel not in [k for k, _t_ in feluri]:
		feluri.append((fel, "%s (0)" % L.numeFelFiltru(fel)))
	n = sum(1 for r in aratate if r[0] in ("plugin", "pachet"))
	return {"feed": filtru.get("feed", ""), "fel": fel, "activ": L.filtruActiv(filtru, fila),
		"feeduri": [[k, t] for k, t in feeduri], "feluri": [[k, t] for k, t in feluri],
		"titlu": _t("Filtrul listei"), "eticheta_feed": _t("Feedul"), "eticheta_fel": _t("Felul"),
		"text_tot": _t("Arată tot"), "aratate": _t("%d din %d") % (n, total)}


def _stareSursa(M):
	"""descarcarea sursei unui plugin (aceeasi ca pe televizor), cu textele gata traduse, sau None"""
	S = M.S
	d = S.curenta()
	if d is None:
		return None
	x = d.stare()
	x.update({"antet": _t("Sursa pluginului %s") % d.titlu, "text_fisier": _t("Ia fișierul pe calculator"),
		"text_opreste": _t("Oprește descărcarea"), "fisier_web": S.fisier_descarcat() is not None,
		"asteapta": _t("Se află mărimea sursei și locul unde se salvează...") if d.faza == "marime" else ""})
	return x


def _textGol(fila, cauta, surse, cf):
	if fila == "instalate":
		return (_t("Nu ai extensii instalate. Funcțiile imaginii sunt în meniu; extensii noi adaugi din celelalte "
			"file."))
	if fila == "cautare":
		return _t("Nimic nu se potrivește cu %s.") % cauta
	if fila == "fisiere":
		if cf["in_curs"] or cf["niciuna"]:
			return _t("Se caută fișiere .ipk pe stick și disc.") + (" " + _t("Un stick sau un disc răspunde greu.")
				if cf["lent"] else "")
		return _t("Niciun fișier .ipk pe stick sau disc. Copiază pachetul pe un stick USB, apoi caută din nou.")
	if not surse:
		return _t("Nicio sursă de pachete. Adaugă una în fila Surse.")
	return _t("Nimic aici.")


def _catalog(M):
	"""catalogul tinut minte sau, daca s-a schimbat ceva, citit acum (ca ecranul, la fiecare deschidere)"""
	c = M.L.catalogLaZi()
	return c if c is not None else M.L.incarcaCatalog()


# ------------------------------------------------------------------ actiunile

def _refuz(text):
	return {"result": False, "message": text}


def _doiPasi(request, arg, actiune, tinta, intrebare, buton, detalii, fa):
	"""pas=intreaba: intrebarea si codul; cod=<cod>: fa(); pas=renunta: nimic. Numai din browserul conectat."""
	C = _comun()
	pas = arg.get("pas", "")
	if pas == "renunta":
		C.uita(actiune, tinta)
		return {"result": True, "message": _t("Nu s-a făcut nimic.")}
	if pas == "intreaba":
		return C.raspunsIntrebare(actiune, tinta, intrebare, buton, detalii)
	cod = arg.get("cod", "")
	if not cod:
		return _refuz(_t("Acțiunea cere întâi confirmarea din pagină."))
	if not C.verifica(actiune, tinta, cod):
		return C.codGresit()
	return fa()


def _notaWeb(L, catalog):
	"""nota despre sursele pachetelor, ca pe televizor (fara ghilimele)"""
	def nota(pachete):
		externe = ["%s (%s)" % (n, a) if a else n for n, a in L.surseExterne(catalog, pachete)]
		if not externe:
			text = L.notaFeedExtern(catalog, pachete)
			if text:
				return text
			return _t("Verificat de HD Satelit.") if L.culoareNota(catalog, pachete) == "bun" else ""
		if len(externe) == 1:
			return _t("Nu este verificat de HD Satelit. Vine din sursa %s.") % externe[0]
		return _t("Nu sunt verificate de HD Satelit. Vin din sursele %s.") % ", ".join(externe)
	return nota


def _detaliiPlan(plan):
	rez = ["%s: %s" % (a, b) if a else b for a, b in plan.get("randuri", ()) if b]
	if plan.get("nota"):
		rez.append(plan["nota"])
	return rez


def _pornestePlan(request, arg, M, catalog, actiune, tinta, plan):
	"""intrebarea planului (aceeasi ca pe televizor, in HdsExtensiiActiune), apoi lucrarea opkg"""
	L = M.L

	def fa():
		motiv = L.motivOcupat(None, M.program)
		if motiv is not None:
			return _refuz(motiv[0])
		plan["titluri"] = L.titluri(catalog)
		L.pornesteLucrarea(plan, plugins=M.plugins, din_web=True)
		return {"result": True, "message": _t("A pornit. Progresul se vede în pagină."), "lucrare": _stareLucrare(L)}
	return _doiPasi(request, arg, actiune, tinta, plan["titlu"], _t(plan["buton"]), _detaliiPlan(plan), fa)


def _inceput(request, M):
	"""refuzurile comune actiunilor cu opkg: cheia din adresa, alta lucrare sau descarcare, imagine fara opkg"""
	refuz = _comun().numaiBrowser(request)
	if refuz:
		return _refuz(refuz)
	motiv = M.L.motivOcupat(None, M.program)
	if motiv is not None:
		return _refuz(motiv[0])
	return None


def instaleaza(arg, request, M):
	nume = arg.get("pachet", "")
	if arg.get("pas") == "renunta":
		return _doiPasi(request, arg, "extensii-instaleaza", nume, "", "", None, None)
	r = _inceput(request, M)
	if r:
		return r
	catalog = _catalog(M)
	p = catalog.pachete.get(nume)
	if p is None or p.instalat or not (p.se_poate_instala or p.python2):
		return _refuz(_t("Pachetul nu se mai poate instala. Reîncarcă pagina."))
	plan, eroare = M.L.planInstalare(catalog, p, nota=_notaWeb(M.L, catalog))
	if plan is None:
		return _refuz(eroare[0])
	if plan.get("fel") == "python2":
		return _refuzPython2(M.L, plan)
	return _pornestePlan(request, arg, M, catalog, "extensii-instaleaza", nume, plan)


def _refuzPython2(L, plan):
	"""pachet sau fisier numai pentru Python 2 (0.6.8): nimic instalat; mesajul, motivul si inlocuitorul, cu butonul
	lui in pagina (ca fereastra de pe televizor)"""
	parti = [plan.get("subtitlu", "")]
	parti += ["%s: %s" % (a, b) for a, b in plan.get("randuri", ()) if a == _t("Motivul")]
	if plan.get("nota"):
		parti.append(plan["nota"])
	rez = _refuz(" ".join(x for x in parti if x))
	if plan.get("inlocuitor"):
		rez["python2"] = {"inlocuitor": plan["inlocuitor"], "text": _t(L.BUTON_INLOCUITOR)}
	return rez


def actualizeaza(arg, request, M):
	tot = arg.get("tot") == "1"
	if arg.get("pas") == "renunta":
		return _doiPasi(request, arg, "extensii-actualizeaza", "*" if tot else arg.get("pachet", ""), "", "", None, None)
	r = _inceput(request, M)
	if r:
		return r
	catalog = _catalog(M)
	if tot:
		pachete = catalog.actualizari()
		tinta = "*"
	else:
		p = catalog.pachete.get(arg.get("pachet", ""))
		pachete = [p] if p is not None else []
		tinta = arg.get("pachet", "")
	plan, eroare = M.L.planActualizare(catalog, pachete, nota=_notaWeb(M.L, catalog))
	if plan is None:
		return _refuz(eroare[0] if eroare else _t("Nu e nimic de actualizat. Reîncarcă pagina."))
	if tot:
		# codul e legat de lista vazuta: o actualizare noua aparuta intre intrebare si confirmare cere alta intrebare
		tinta = "*" + ",".join(sorted(plan["pachete"]))
	return _pornestePlan(request, arg, M, catalog, "extensii-actualizeaza", tinta, plan)


def sterge(arg, request, M):
	nume = arg.get("pachet", "")
	if arg.get("pas") == "renunta":
		return _doiPasi(request, arg, "extensii-sterge", nume, "", "", None, None)
	r = _inceput(request, M)
	if r:
		return r
	catalog = _catalog(M)
	p = catalog.pachete.get(nume)
	if p is None or not p.se_poate_sterge:
		return _refuz(_t("Pachetul nu mai este instalat. Reîncarcă pagina."))
	plan, eroare = M.L.planStergere(catalog, p)
	if plan is None:
		return _refuz(eroare[0])
	return _pornestePlan(request, arg, M, catalog, "extensii-sterge", nume, plan)


def fisier(arg, request, M):
	cale = arg.get("cale", "")
	if arg.get("pas") == "renunta":
		return _doiPasi(request, arg, "extensii-fisier", cale, "", "", None, None)
	r = _inceput(request, M)
	if r:
		return r
	_cautariFisiere(M)
	f = None
	for x in _fisiereGasite():
		if x.utf8 and x.cale == cale:
			f = x
			break
	if f is None:
		return _refuz(_t("Fișierul nu mai este în lista găsită. Caută din nou."))
	catalog = _catalog(M)
	plan, eroare = M.L.planFisier(f, catalog=catalog)
	if plan is None:
		return _refuz(eroare[0])
	if plan.get("fel") == "python2":
		return _refuzPython2(M.L, plan)
	return _pornestePlan(request, arg, M, catalog, "extensii-fisier", cale, plan)


def sursaAdauga(arg, request, M):
	P = M.P
	nume = P.curata_nume_sursa(arg.get("nume", ""))
	adresa = arg.get("adresa", "").strip()
	tinta = nume + " " + adresa
	if arg.get("pas") == "renunta":
		return _doiPasi(request, arg, "extensii-sursa-adauga", tinta, "", "", None, None)
	refuz = _comun().numaiBrowser(request)
	if refuz:
		return _refuz(refuz)
	if not nume:
		return _refuz(_t("Numele sursei nu poate fi gol."))
	catalog = _catalog(M)
	motiv = P.verifica_sursa(nume, adresa, catalog.configurare.nume_surse())
	if motiv:
		return _refuz(motiv)

	def fa():
		eroare = M.L.adaugaSursa(catalog, nume, adresa)
		if eroare:
			return _refuz(eroare)
		rez = {"result": True, "message": _t("Sursa a fost adăugată.")}
		# ca pe televizor: lista sursei noi se descarca imediat
		if not M.L.descarcareInCurs() and not M.L.lucrareInCurs() and M.program():
			M.L.pornesteDescarcarea()
			rez["message"] = _t("Sursa a fost adăugată. Se descarcă lista ei.")
		return rez
	return _doiPasi(request, arg, "extensii-sursa-adauga", tinta, _t("Adaugi sursa %s?") % nume, _t("Adaugă"),
		[adresa, _t("Pachetele din ea nu sunt verificate de HD Satelit.")], fa)


def sursaSterge(arg, request, M):
	nume = arg.get("nume", "")
	if arg.get("pas") == "renunta":
		return _doiPasi(request, arg, "extensii-sursa-sterge", nume, "", "", None, None)
	refuz = _comun().numaiBrowser(request)
	if refuz:
		return _refuz(refuz)
	catalog = _catalog(M)
	if nume not in catalog.configurare.nume_surse() or not catalog.configurare.e_a_utilizatorului(nume):
		return _refuz(_t("Numai sursele adăugate de tine se pot șterge."))

	def fa():
		eroare = M.L.stergeSursa(catalog, nume)
		if eroare:
			return _refuz(eroare)
		return {"result": True, "message": _t("Sursa a fost ștearsă.")}
	return _doiPasi(request, arg, "extensii-sursa-sterge", nume, _t("Ștergi sursa %s?") % nume, _t("Șterge sursa"),
		[_t("Extensiile instalate din ea rămân pe receptor.")], fa)


def _lucrareRepornire(L):
	l = L.STARE["lucrare"]
	return l is not None and l.faza == "gata" and bool((l.rezultat or {}).get("repornire"))


def reporneste(arg, request, M):
	if arg.get("pas") == "renunta":
		return _doiPasi(request, arg, "extensii-reporneste", "", "", "", None, None)
	refuz = _comun().numaiBrowser(request)
	if refuz:
		return _refuz(refuz)
	if M.L.lucrareInCurs():
		return _refuz(_t("Așteaptă să se termine instalarea."))
	if not (getattr(M.plugins, "restartRequired", False) or _lucrareRepornire(M.L)):
		return _refuz(_t("Nu e nevoie de repornirea interfeței acum."))

	def fa():
		s = M.sesiune()
		if s is None:
			return _refuz(_t("Interfața nu este pornită încă."))
		return M.reporneste(s)
	return _doiPasi(request, arg, "extensii-reporneste", "", _t("Repornești interfața acum?"), "Repornește interfața",
		[_t("Extensiile noi apar după repornire. Imaginea revine în mai puțin de un minut.")], fa)


def opreste(arg, request, M):
	if arg.get("pas") == "renunta":
		return _doiPasi(request, arg, "extensii-opreste", "", "", "", None, None)
	refuz = _comun().numaiBrowser(request)
	if refuz:
		return _refuz(refuz)
	l = M.L.STARE["lucrare"]
	if l is None or not l.poateOpri():
		return _refuz(_t("Instalarea încă răspunde. Se poate opri numai după un minut fără niciun răspuns."))

	def fa():
		if not l.opreste():
			return _refuz(_t("Instalarea a răspuns între timp. Așteaptă să se termine."))
		return {"result": True, "message": _t("Instalarea a fost oprită."), "lucrare": _stareLucrare(M.L)}
	return _doiPasi(request, arg, "extensii-opreste", "", _t("Oprești instalarea?"), _t("Oprește"),
		[_t("Nu mai răspunde de un minut. Oprește-o numai dacă rețeaua s-a blocat.")], fa)


def descarcaLista(arg, request, M):
	L = M.L
	if L.descarcareInCurs():
		return _refuz(_t("Lista se descarcă deja. Încearcă din nou peste un minut."))
	if L.lucrareInCurs():
		return _refuz(_t("Așteaptă să se termine instalarea."))
	catalog = _catalog(M)
	if not catalog.configurare.surse:
		return _refuz(_t("Nicio sursă de pachete. Adaugă una în fila Surse."))
	if not M.program():
		return _refuz(_t("Instalarea pachetelor nu este disponibilă în această imagine."))
	L.pornesteDescarcarea()
	return {"result": True, "message": _t("Se descarcă lista de pachete.")}


def _pachetCuSursa(M, catalog, nume):
	p = catalog._toate.get(nume or "")
	return M.L.pachetCuSursa(catalog, "pachet", p, None) if p is not None else None


def sursaAfla(arg, request, M):
	"""butonul Descarcă sursa (0.6.6): porneste aflarea marimii si a locului, pe un fir (ca pe televizor); pagina
	citeste starea din GET /api/extensii si, la intrebare, cere /api/extensii-sursa-descarca"""
	S = M.S
	if S.in_lucru():
		return _refuz(_t("Se descarcă deja o sursă. Așteaptă să se termine."))
	catalog = _catalog(M)
	p = _pachetCuSursa(M, catalog, arg.get("pachet", ""))
	if p is None:
		return _refuz(_t(S.TEXT_NEGASIT))
	d, motiv = M.L.descarcareSursa(catalog, "pachet", p, None)
	if d is None:
		return _refuz(motiv)
	return {"result": True, "message": _t("Se află mărimea sursei și locul unde se salvează...")}


def sursaDescarca(arg, request, M):
	"""in doi pasi: intrebarea (marimea, locul) a descarcarii aflate deja, apoi pornirea ei"""
	S = M.S
	d = S.curenta()
	nume = arg.get("pachet", "")
	if arg.get("pas") == "renunta":
		S.uita(d)
	if d is None or d.faza != "intrebare":
		if d is not None and d.faza in ("negasit", "fara-loc"):
			return _refuz(d.text_fara_loc() if d.faza == "fara-loc" else d.text_negasit())
		return _refuz(_t("Apasă din nou Descarcă sursa."))

	def fa():
		if not d.porneste():
			return _refuz(_t("Apasă din nou Descarcă sursa."))
		return {"result": True, "message": _t("Se descarcă sursa pluginului %s") % d.titlu}
	return _doiPasi(request, arg, "extensii-sursa-descarca", nume, d.intrebare(), _t("Descarcă"), d.detalii(), fa)


def sursaOpreste(arg, request, M):
	d = M.S.curenta()
	if d is None or not d.opreste():
		return _refuz(_t("Nu se descarcă nicio sursă acum."))
	return {"result": True, "message": _t("Descărcarea se oprește.")}


def cautaFisiere(arg, request, M):
	"""ca tasta albastra in fila Din fisier: pe stick, disc si memorie; reteaua numai la cerere (retea=1) sau daca a
	fost deschisa inainte"""
	P = M.P
	cautari = _cautariFisiere(M)
	if arg.get("retea") == "1":
		if cautari["retea"] is not None and not cautari["retea"].gata:
			return _refuz(_t("Se caută deja în rețea."))
		locuri = list(_FISIERE["local"].locuri_retea) if _FISIERE["local"] is not None else []
		if not locuri:
			return _refuz(_t("Nu am găsit dosare de rețea. Caută întâi pe stick și disc."))
		P.cautare_ipk(locuri)
		return {"result": True, "message": _t("Se caută și în rețea. Lista se poate folosi între timp.")}
	if cautari["local"] is not None and not cautari["local"].gata:
		return _refuz(_t("Căutarea fișierelor rulează încă."))
	P.cautare_ipk()
	if _FISIERE["retea"] is not None and (cautari["retea"] is None or cautari["retea"].gata) and \
			_FISIERE["local"] is not None and _FISIERE["local"].locuri_retea:
		P.cautare_ipk(list(_FISIERE["local"].locuri_retea))
	return {"result": True, "message": _t("Se caută fișiere .ipk pe stick și disc.")}


def deschide(arg, request, M):
	"""OK pe o extensie instalata: ecranul ei se deschide pe televizor"""
	try:
		i = int(arg.get("plugin", ""))
	except ValueError:
		return _refuz(_t("Extensia nu e în listă. Reîncarcă pagina."))
	pluginuri = M.pluginuri()
	if not 0 <= i < len(pluginuri) or (pluginuri[i].name or "") != arg.get("nume", ""):
		return _refuz(_t("Lista extensiilor s-a schimbat. Reîncarcă pagina."))
	s = M.sesiune()
	motiv = M.ocupat(s)
	if motiv:
		return _refuz(motiv)
	plugin = pluginuri[i]
	avertismente = len(getattr(M.plugins, "warnings", None) or [])
	try:
		plugin(session=s)
	except Exception as eroare:
		return _refuz(_t("Extensia %s nu a putut porni: %s") % (plugin.name, M.P._curat(str(eroare), 200)))
	if len(getattr(M.plugins, "warnings", None) or []) > avertismente:
		return _refuz(_t("Extensia %s nu a putut porni. Mesajul e pe televizor.") % plugin.name)
	return {"result": True, "message": _t("Extensia %s s-a deschis pe televizor.") % plugin.name}


# ------------------------------------------------------------------ rutele

def rute(baza, resource, mediu=None):
	"""({nume: resursa de sub /api}, {nume: resursa paginii}). `baza` e HdsJsonResource din plugin.py."""

	def M():
		return mediu if mediu is not None else Mediu()

	class StareResource(baza):
		"""GET /api/extensii: numai citire; catalogul se citeste pe un fir separat cand s-a schimbat"""

		def render_GET(self, request):
			try:
				m = M()
				arg = argumente(request)
				c = m.L.catalogLaZi()
				if c is not None:
					return self._raspunde(request, stare(arg, m, c))
				if _INCARCARE[0]:
					return self._raspunde(request, {"result": True, "se_incarca": True,
						"message": _t("Se citește lista pachetelor...")})
				date = datePrincipale(m)

				def lucru():
					try:
						return stare(arg, m, m.L.incarcaCatalog(), date)
					except Exception as eroare:
						return {"result": False, "message": _t("Lista pachetelor nu s-a putut citi: %s") % eroare}
				return m.peFir(request, lucru, _INCARCARE, 60)
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ActiuneResource(baza):
		schimbaCeva = True
		functie = None

		def render_POST(self, request):
			try:
				return self._raspunde(request, self.functie(argumente(request), request, M()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	def actiune(f):
		r = ActiuneResource()
		r.functie = f
		return r

	class SursaFisierResource(baza):
		"""GET /api/extensii-sursa-fisier: arhiva sursei descarcata ultima pe stick sau disc, data browserului (numai
		fisierul descarcarii curente, nicio alta cale); trimisa pe bucati (FileSender), fara sa tina firul enigma2"""

		def render_GET(self, request):
			try:
				cale = M().S.fisier_descarcat()
				if cale is None:
					return self._eroare(request, _t("Nicio sursă descărcată acum."), 404)
				from twisted.protocols.basic import FileSender
				from twisted.web.server import NOT_DONE_YET
				f = open(cale, "rb")
				nume = os.path.basename(cale).encode("ascii", "replace").replace(b'"', b"_")
				request.setHeader(b"content-type", b"application/octet-stream")
				request.setHeader(b"content-disposition", b'attachment; filename="' + nume + b'"')
				request.setHeader(b"content-length", str(os.path.getsize(cale)).encode("ascii"))
				request.setHeader(b"cache-control", b"no-store")

				def gata(_r):
					try:
						f.close()
					finally:
						try:
							request.finish()
						except Exception:
							pass
				FileSender().beginFileTransfer(f, request).addBoth(gata)
				return NOT_DONE_YET
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class PaginaResource(resource.Resource):
		"""GET /extensii"""
		isLeaf = True

		def render_GET(self, request):
			return _comun().pagina(request, pagina_text)

	api = {
		b"extensii": StareResource(),
		b"extensii-instaleaza": actiune(instaleaza),
		b"extensii-actualizeaza": actiune(actualizeaza),
		b"extensii-sterge": actiune(sterge),
		b"extensii-fisier": actiune(fisier),
		b"extensii-sursa-adauga": actiune(sursaAdauga),
		b"extensii-sursa-sterge": actiune(sursaSterge),
		b"extensii-reporneste": actiune(reporneste),
		b"extensii-opreste": actiune(opreste),
		b"extensii-descarca-lista": actiune(descarcaLista),
		b"extensii-cauta-fisiere": actiune(cautaFisiere),
		b"extensii-deschide": actiune(deschide),
		b"extensii-sursa-afla": actiune(sursaAfla),
		b"extensii-sursa-descarca": actiune(sursaDescarca),
		b"extensii-sursa-opreste": actiune(sursaOpreste),
		b"extensii-sursa-fisier": SursaFisierResource(),
	}
	return api, {b"extensii": PaginaResource()}


def pagina_text(stil, config_pagina):
	C = _comun()
	return C.sablon(_traducePagina(PAGINA), stil, config_pagina, {"__DRUM_MENIU__": C.drumHtml("plugin_selection")})


PAGINA = r"""<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Extensii și aplicații</title>
<style>__STIL_COMUN__
__STIL_PAGINI__
  .file{margin:0 0 12px;}
  .cautare{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px;}
  .cautare input{flex:1 1 200px;min-width:0;}
  .element{cursor:pointer;}
  .filtru{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:flex-end;margin-bottom:10px;}
  .filtru label{display:flex;flex-direction:column;gap:4px;min-width:0;}
  .filtru select{max-width:100%;}
  .element .stanga{display:flex;flex-direction:column;gap:2px;min-width:0;}
  .element .titlu{overflow-wrap:anywhere;}
  .element .dreapta{display:flex;flex-direction:column;align-items:flex-end;gap:4px;text-align:right;min-width:0;}
  .insigna{display:inline-block;padding:2px 8px;border:1px solid currentColor;border-radius:6px;font-size:.8rem;line-height:1.4;}
  .insigna.bun{color:var(--bine);}
  .insigna.chihlimbar{color:var(--chihlimbar);}
  .insigna.rau{color:var(--eroare);}
  .detalii{padding:6px 0 14px;}
  .detalii th{width:34%;}
  .descriere{white-space:pre-line;line-height:1.45;overflow-wrap:anywhere;margin:8px 0 0;}
  .jurnal{list-style:none;margin:8px 0 0;padding:0;font-size:.85rem;line-height:1.45;}
  .jurnal li{overflow-wrap:anywhere;}
  @media (max-width:560px){ .element .dreapta{align-items:flex-start;text-align:left;} }
</style>
</head>
<body>
<main>
<h1>Extensii și aplicații</h1>
<p class="nota">Extensiile de pe receptor, pachetele din surse, fișierele .ipk de pe stick sau disc și sursele de pachete. Actualizările imaginii sunt în pagina <a href="/actualizari" id="legaturaActualizari">Actualizare software</a>.</p>
<p class="mesaj" id="incarcare">Se citește lista...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <h2>Lista pachetelor</h2>
    <div class="status-linie"><span>Lista</span><span id="lista"></span></div>
    <p class="nota" id="stareText"></p>
    <div class="butoane">
      <button type="button" id="descarca">Descarcă lista</button>
      <button type="button" id="toate" class="principal ascuns"></button>
      <button type="button" id="reporneste" class="principal ascuns">Repornește interfața</button>
    </div>
    <p class="descriere ascuns" id="rezumatLista"></p>
  </section>
  <section class="card ascuns" id="avertismente"></section>
  <section class="card ascuns" id="lucrare">
    <h2 id="lucrareTitlu"></h2>
    <p class="intrebare" id="lucrarePas"></p>
    <ul class="jurnal" id="lucrareJurnal"></ul>
    <div class="butoane">
      <button type="button" id="lucrareReporneste" class="principal ascuns">Repornește interfața</button>
      <button type="button" id="lucrareInlocuitor" class="principal ascuns"></button>
      <button type="button" id="opreste" class="rosu ascuns">Oprește instalarea</button>
    </div>
  </section>
  <section class="card ascuns" id="sursaCard">
    <h2 id="sursaTitlu"></h2>
    <p class="intrebare" id="sursaText"></p>
    <progress id="sursaBara" class="ascuns" max="100" value="0"></progress>
    <div class="butoane">
      <a id="sursaFisier" class="buton principal ascuns" download></a>
      <button type="button" id="sursaOpreste" class="rosu ascuns"></button>
    </div>
  </section>
  <nav class="butoane file" id="file" aria-label="File"></nav>
  <form class="cautare" id="formCauta">
    <input type="search" id="cauta" maxlength="40" placeholder="Caută o extensie după nume" aria-label="Caută o extensie după nume">
    <button type="submit">Caută</button>
    <button type="button" id="iesi" class="ascuns">Înapoi</button>
  </form>
  <section class="card ascuns" id="fisiere">
    <h2>Fișiere .ipk</h2>
    <p class="nota" id="fisiereText"></p>
    <div class="butoane">
      <button type="button" id="cautaFisiere">Caută din nou</button>
      <button type="button" id="cautaRetea" class="ascuns">Caută și în rețea</button>
    </div>
    <p class="nota" id="locuriRetea"></p>
  </section>
  <section class="card ascuns" id="formSursa">
    <h2>Adaugă o sursă</h2>
    <div class="rand"><label for="sursaNume">Numele sursei (litere mici, cifre și -)</label><input id="sursaNume" maxlength="32" autocomplete="off"></div>
    <div class="rand"><label for="sursaAdresa">Adresa (http:// sau https://)</label><input id="sursaAdresa" maxlength="300" value="https://" autocomplete="off" inputmode="url"></div>
    <p class="nota">Pachetele din ea apar apoi în file, cu numele sursei. Nu sunt verificate de HD Satelit.</p>
    <div class="butoane"><button type="button" id="sursaAdauga" class="principal">Adaugă</button><button type="button" id="sursaRenunta">Renunță</button></div>
  </section>
  <section class="card" id="randuri"></section>
  <p class="mesaj" id="mesaj"></p>
  <div class="butoane ascuns" id="inlocuitorBara"><button type="button" id="inlocuitor" class="principal"></button></div>
  <div id="confirmare" class="card ascuns"></div>
  <p class="nota">Aceleași extensii și acțiuni sunt pe televizor, în __DRUM_MENIU__.</p>
</div>
</main>
<script>
__SCRIPT_COMUN__
var D = null, FILA = "instalate", CAUTA = "", FILA_DINAINTE = "instalate", DESCHIS = "", CEAS = null, CAUTAT = false, SURSA = "", LISTA_CERUTA = false, FEED = "", FEL = "";
function el(tip, clasa, text){ var e = document.createElement(tip); if(clasa){ e.className = clasa; } if(text !== undefined && text !== null){ e.textContent = text; } return e; }
function programeaza(ms){ if(CEAS){ clearTimeout(CEAS); CEAS = null; } if(ms){ CEAS = setTimeout(citeste, ms); } }
function citeste(){
  var q = "/api/extensii?fila=" + encodeURIComponent(FILA) + (CAUTA ? "&cauta=" + encodeURIComponent(CAUTA) : "") +
    (FEED ? "&feed=" + encodeURIComponent(FEED) : "") + (FEL ? "&fel=" + encodeURIComponent(FEL) : "");
  return cerere(q).then(function(d){
    if(d.se_incarca){ $("incarcare").textContent = d.message || "Se citește lista..."; programeaza(800); return; }
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi lista."; $("incarcare").classList.remove("ascuns"); return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    D = d; FILA = d.fila; arata(d);
    if(d.fila === "fisiere" && d.cautare_fisiere.niciuna && !CAUTAT){ CAUTAT = true; trimite("/api/extensii-cauta-fisiere", new URLSearchParams(), true); }
    programeaza(d.lucreaza ? 1500 : 0);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; $("incarcare").classList.remove("ascuns"); });
}
function trimite(cale, q, tacut){
  if(!tacut){ mesaj("Se trimite..."); }
  cerere(cale, "POST", q).then(function(d){ if(!tacut || !d.result){ mesaj(d.message, !d.result); } citeste(); }).catch(nimicNuRaspunde);
}
var INLOCUITOR = "";
function arataInlocuitor(x){ INLOCUITOR = x && x.inlocuitor ? x.inlocuitor : ""; $("inlocuitorBara").classList.toggle("ascuns", !INLOCUITOR); if(INLOCUITOR){ $("inlocuitor").textContent = x.text; } }
function instaleazaInlocuitor(nume){ arataInlocuitor(null); var q = new URLSearchParams(); q.set("pachet", nume); cuConfirmare("/api/extensii-instaleaza", q, dupa); }
function dupa(d){ arataInlocuitor(d && d.python2); citeste(); }
function arataStare(d){
  $("lista").textContent = d.lista + (d.descarcare.in_curs ? " · se descarcă acum" : "");
  var p = [];
  if(d.mod_sigur){ p.push(d.mod_sigur); }
  if(d.repornire_ceruta){ p.push("Extensiile noi apar după repornirea interfeței."); }
  if(!d.opkg){ p.push("Instalarea pachetelor nu este disponibilă în această imagine."); }
  if(!d.descarcare.in_curs && d.descarcare.cod !== null && d.descarcare.cod !== undefined && d.descarcare.cod !== 0 && d.descarcare.motiv){ p.push("Ultima descărcare (" + d.descarcare.cand + "): " + d.descarcare.motiv); }
  $("stareText").textContent = p.join(" ");
  $("descarca").disabled = d.descarcare.in_curs || !d.surse || !d.opkg;
  $("toate").classList.toggle("ascuns", !d.text_toate); $("toate").textContent = d.text_toate || ""; $("toate").disabled = !d.opkg;
  var rz = $("rezumatLista");
  if(LISTA_CERUTA && !d.descarcare.in_curs && d.descarcare.rezumat){ rz.textContent = d.descarcare.rezumat; rz.classList.remove("ascuns"); LISTA_CERUTA = false; }
  $("reporneste").classList.toggle("ascuns", !d.repornire_ceruta);
  var a = $("avertismente"); a.textContent = "";
  if(d.avertismente.length){
    a.appendChild(el("h2", null, "Extensii care nu au putut porni"));
    d.avertismente.forEach(function(x){ a.appendChild(el("p", "nota", x[0] + ": " + x[1])); });
  }
  a.classList.toggle("ascuns", !d.avertismente.length);
}
function arataLucrarea(d){
  var l = d.lucrare, c = $("lucrare");
  c.classList.toggle("ascuns", !l);
  if(!l){ return; }
  $("lucrareTitlu").textContent = l.titlu;
  var pas = l.faza === "lucru" ? (l.pas || "Pornește") : ((l.rezultat || {}).stare || "");
  if(l.faza === "lucru" && l.secunde_fara_raspuns > 60){ pas = "Nu mai răspunde de un minut."; }
  $("lucrarePas").textContent = pas;
  $("lucrarePas").classList.toggle("eroare", l.faza === "gata" && l.rezultat && !l.rezultat.reusit);
  var j = $("lucrareJurnal"); j.textContent = "";
  l.jurnal.forEach(function(x){ j.appendChild(el("li", x[0] === "eroare" ? "eroare" : null, x[1])); });
  $("lucrareReporneste").classList.toggle("ascuns", !(l.faza === "gata" && l.rezultat && l.rezultat.repornire));
  var ri = l.faza === "gata" && l.rezultat && l.rezultat.inlocuitor ? l.rezultat : null, bi = $("lucrareInlocuitor");
  bi.classList.toggle("ascuns", !ri); bi.textContent = ri ? ri.textInlocuitor : ""; bi.dataset.pachet = ri ? ri.inlocuitor : "";
  $("opreste").classList.toggle("ascuns", !l.poate_opri);
}
function arataSursa(d){
  var s = d.sursa, c = $("sursaCard");
  c.classList.toggle("ascuns", !s);
  if(!s){ return; }
  $("sursaTitlu").textContent = s.antet;
  $("sursaText").textContent = s.faza === "lucru" ? s.progres : (s.mesaj || s.asteapta || "");
  $("sursaText").classList.toggle("eroare", ["negasit", "fara-loc", "eroare"].indexOf(s.faza) !== -1);
  $("sursaBara").classList.toggle("ascuns", s.faza !== "lucru");
  $("sursaBara").value = s.procent || 0;
  var a = $("sursaFisier");
  a.classList.toggle("ascuns", !s.fisier_web);
  if(s.fisier_web){ a.href = adresa("/api/extensii-sursa-fisier"); a.textContent = s.text_fisier; }
  $("sursaOpreste").classList.toggle("ascuns", s.faza !== "lucru");
  $("sursaOpreste").textContent = s.text_opreste;
  if(s.faza === "intrebare" && SURSA){ var q = new URLSearchParams(); q.set("pachet", SURSA); SURSA = ""; cuConfirmare("/api/extensii-sursa-descarca", q, dupa); }
  else if(s.faza !== "marime"){ SURSA = ""; }
}
function arataFile(d){
  var f = $("file"); f.textContent = "";
  d.file.forEach(function(x){
    var b = el("button", x.id === d.fila ? "principal" : null, x.eticheta + (x.numar !== null && x.id !== "cautare" ? " " + x.numar : ""));
    b.type = "button"; b.setAttribute("aria-pressed", x.id === d.fila ? "true" : "false");
    b.addEventListener("click", function(){ FILA = x.id; DESCHIS = ""; $("formSursa").classList.add("ascuns"); citeste(); });
    f.appendChild(b);
  });
  $("iesi").classList.toggle("ascuns", !d.cauta);
}
function arataFisiere(d){
  var c = $("fisiere"), cf = d.cautare_fisiere;
  c.classList.toggle("ascuns", d.fila !== "fisiere");
  if(d.fila !== "fisiere"){ return; }
  var t = [];
  if(cf.in_curs){ t.push("Se caută fișiere .ipk pe stick și disc."); }
  else if(cf.gasite !== null){ t.push("Fișiere .ipk de pe stick și disc" + (cf.retea_gasite !== null ? " și din rețea" : "") + (cf.taiate ? ", cele mai noi " + cf.gasite : "") + "."); }
  if(cf.retea_in_curs){ t.push("Se caută în rețea; lista se poate folosi între timp."); }
  else if(cf.retea_gasite !== null){ t.push(cf.retea_gasite ? cf.retea_gasite + " găsite în rețea." : "Niciun fișier .ipk în rețea."); }
  if(cf.lent){ t.push("Un loc răspunde greu."); }
  $("fisiereText").textContent = t.join(" ");
  $("cautaFisiere").disabled = cf.in_curs;
  $("cautaRetea").classList.toggle("ascuns", !cf.locuri_retea.length);
  $("cautaRetea").disabled = cf.retea_in_curs;
  $("cautaRetea").textContent = cf.retea_gasite !== null ? "Caută din nou în rețea" : "Caută și în rețea";
  $("locuriRetea").textContent = cf.locuri_retea.length ? "Dosarele de rețea (un calculator sau un NAS) nu se caută singure, pot răspunde greu: " + cf.locuri_retea.join(", ") + "." : "";
}
function detalii(r){
  var x = el("div", "detalii");
  var dt = r.detalii;
  if(dt.insigna){ var p = el("p"); p.appendChild(el("span", "insigna " + (dt.culoare || ""), dt.insigna)); x.appendChild(p); }
  if(dt.randuri.length){
    var t = el("table");
    dt.randuri.forEach(function(v){ var tr = el("tr"); tr.appendChild(el("th", null, v[0])); tr.appendChild(el("td", null, v[1])); t.appendChild(tr); });
    x.appendChild(t);
  }
  if(dt.descriere){ x.appendChild(el("p", "descriere", dt.descriere)); }
  var b = el("div", "butoane");
  r.actiuni.forEach(function(a){
    var bt = el("button", a.rosu ? "rosu" : (a.principal ? "principal" : null), a.text); bt.type = "button";
    bt.disabled = !D.opkg && ["instaleaza", "actualizeaza", "sterge", "fisier", "descarca"].indexOf(a.f) !== -1;
    bt.addEventListener("click", function(){ actiune(a); });
    b.appendChild(bt);
  });
  x.appendChild(b);
  return x;
}
function arataFiltru(d, c){
  var f = d.filtru; if(!f){ return; }
  var b = el("div", "filtru"); b.setAttribute("role", "group"); b.setAttribute("aria-label", f.titlu);
  function lista(eticheta, alegeri, valoare, pune){
    var l = el("label", null, eticheta); var s = el("select");
    alegeri.forEach(function(a){ var o = el("option", null, a[1]); o.value = a[0]; if(a[0] === valoare){ o.selected = true; } s.appendChild(o); });
    s.addEventListener("change", function(){ pune(s.value); DESCHIS = ""; citeste(); });
    l.appendChild(s); b.appendChild(l);
  }
  lista(f.eticheta_feed, f.feeduri, f.feed, function(v){ FEED = v; });
  if(f.feluri.length){ lista(f.eticheta_fel, f.feluri, f.fel, function(v){ FEL = v; }); }
  b.appendChild(el("span", "nota", f.aratate));
  if(f.activ){ var t = el("button", null, f.text_tot); t.type = "button"; t.addEventListener("click", function(){ FEED = ""; FEL = ""; DESCHIS = ""; citeste(); }); b.appendChild(t); }
  c.appendChild(b);
}
function arataRanduri(d){
  var c = $("randuri"); c.textContent = "";
  arataFiltru(d, c);
  if(d.fila === "actualizari" && d.tot.length){
    var bt = el("button", "principal", "Actualizează toate"); bt.type = "button";
    bt.addEventListener("click", function(){ var q = new URLSearchParams(); q.set("tot", "1"); cuConfirmare("/api/extensii-actualizeaza", q, dupa); });
    var bb = el("div", "butoane"); bb.appendChild(bt); c.appendChild(bb);
  }
  if(!d.randuri.length){ c.appendChild(el("p", "nota", d.gol)); return; }
  d.randuri.forEach(function(r){
    var deschis = DESCHIS === r.cheie;
    var rnd = el("div", "rand element" + (deschis ? " ales" : ""));
    rnd.tabIndex = 0; rnd.setAttribute("role", "button"); rnd.setAttribute("aria-expanded", deschis ? "true" : "false");
    var st = el("div", "stanga"); st.appendChild(el("strong", "titlu", r.titlu));
    if(r.subtitlu){ st.appendChild(el("span", "nota", r.subtitlu)); }
    var dr = el("div", "dreapta");
    if(r.insigna){ dr.appendChild(el("span", "insigna " + r.culoare, r.insigna)); }
    if(r.mic){ dr.appendChild(el("span", "nota", r.mic)); }
    rnd.appendChild(st); rnd.appendChild(dr);
    function comuta(){ DESCHIS = deschis ? "" : r.cheie; arata(D); }
    rnd.addEventListener("click", comuta);
    rnd.addEventListener("keydown", function(e){ if(e.key === "Enter" || e.key === " "){ e.preventDefault(); comuta(); } });
    c.appendChild(rnd);
    if(deschis){ c.appendChild(detalii(r)); }
  });
}
function arata(d){ arataStare(d); arataLucrarea(d); arataSursa(d); arataFile(d); arataFisiere(d); arataRanduri(d); }
function actiune(a){
  var q = new URLSearchParams();
  if(a.f === "instaleaza" || a.f === "actualizeaza" || a.f === "sterge"){ q.set("pachet", a.pachet); cuConfirmare("/api/extensii-" + a.f, q, dupa); }
  else if(a.f === "fisier"){ q.set("cale", a.cale); cuConfirmare("/api/extensii-fisier", q, dupa); }
  else if(a.f === "reporneste"){ cuConfirmare("/api/extensii-reporneste", q, dupaRepornire); }
  else if(a.f === "sursa-sterge"){ q.set("nume", a.nume); cuConfirmare("/api/extensii-sursa-sterge", q, dupa); }
  else if(a.f === "deschide"){ q.set("plugin", String(a.plugin)); q.set("nume", a.nume); trimite("/api/extensii-deschide", q); }
  else if(a.f === "descarca"){ LISTA_CERUTA = true; trimite("/api/extensii-descarca-lista", q); }
  else if(a.f === "sursa"){ q.set("pachet", a.pachet); SURSA = a.pachet; trimite("/api/extensii-sursa-afla", q); }
  else if(a.f === "adauga"){ $("formSursa").classList.remove("ascuns"); $("formSursa").scrollIntoView({block: "center"}); $("sursaNume").focus(); }
}
function dupaRepornire(d){ if(d && d.result){ setTimeout(function(){ location.reload(); }, 20000); } else { citeste(); } }
$("descarca").addEventListener("click", function(){ LISTA_CERUTA = true; trimite("/api/extensii-descarca-lista", new URLSearchParams()); });
$("toate").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("tot", "1"); cuConfirmare("/api/extensii-actualizeaza", q, dupa); });
$("reporneste").addEventListener("click", function(){ cuConfirmare("/api/extensii-reporneste", new URLSearchParams(), dupaRepornire); });
$("lucrareReporneste").addEventListener("click", function(){ cuConfirmare("/api/extensii-reporneste", new URLSearchParams(), dupaRepornire); });
$("lucrareInlocuitor").addEventListener("click", function(){ var n = $("lucrareInlocuitor").dataset.pachet; if(n){ instaleazaInlocuitor(n); } });
$("inlocuitor").addEventListener("click", function(){ if(INLOCUITOR){ instaleazaInlocuitor(INLOCUITOR); } });
$("opreste").addEventListener("click", function(){ cuConfirmare("/api/extensii-opreste", new URLSearchParams(), dupa); });
$("sursaOpreste").addEventListener("click", function(){ trimite("/api/extensii-sursa-opreste", new URLSearchParams()); });
$("cautaFisiere").addEventListener("click", function(){ trimite("/api/extensii-cauta-fisiere", new URLSearchParams()); });
$("cautaRetea").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("retea", "1"); trimite("/api/extensii-cauta-fisiere", q); });
$("formCauta").addEventListener("submit", function(e){
  e.preventDefault();
  var t = $("cauta").value.trim();
  if(!t){ iesiDinCautare(); return; }
  if(!CAUTA){ FILA_DINAINTE = FILA; }
  CAUTA = t; FILA = "cautare"; DESCHIS = ""; citeste();
});
function iesiDinCautare(){ CAUTA = ""; $("cauta").value = ""; FILA = FILA_DINAINTE; DESCHIS = ""; citeste(); }
$("iesi").addEventListener("click", iesiDinCautare);
$("sursaAdauga").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("nume", $("sursaNume").value); q.set("adresa", $("sursaAdresa").value.trim());
  cuConfirmare("/api/extensii-sursa-adauga", q, function(d){ if(d.result && !d.confirmare){ $("formSursa").classList.add("ascuns"); } citeste(); });
});
$("sursaRenunta").addEventListener("click", function(){ $("formSursa").classList.add("ascuns"); });
$("legaturaActualizari").href = adresa("/actualizari");
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
		N_("Extensii și aplicații"),
		N_("Extensiile de pe receptor, pachetele din surse, fișierele .ipk de pe stick sau disc și sursele "
			"de pachete. Actualizările imaginii sunt în pagina <a href=\"/actualizari\" "
			"id=\"legaturaActualizari\">Actualizare software</a>."),
		N_("Se citește lista..."),
		N_("Lista pachetelor"),
		N_("Lista"),
		N_("Descarcă lista"),
		N_("Repornește interfața"),
		N_("Oprește instalarea"),
		N_("Caută"),
		N_("Înapoi"),
		N_("Fișiere .ipk"),
		N_("Caută din nou"),
		N_("Caută și în rețea"),
		N_("Adaugă o sursă"),
		N_("Numele sursei (litere mici, cifre și -)"),
		N_("Adresa (http:// sau https://)"),
		N_("Pachetele din ea apar apoi în file, cu numele sursei. Nu sunt verificate de HD Satelit."),
		N_("Adaugă"),
		N_("Renunță"),
		N_("Aceleași extensii și acțiuni sunt pe televizor, în __DRUM_MENIU__."),
		N_("File"),
		N_("Caută o extensie după nume"),
	),
	"js": (
		N_("Se citește lista..."),
		N_("Receptorul nu a putut citi lista."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
		N_("· se descarcă acum"),
		N_("Extensiile noi apar după repornirea interfeței."),
		N_("Instalarea pachetelor nu este disponibilă în această imagine."),
		N_("Ultima descărcare ("),
		N_("Extensii care nu au putut porni"),
		N_("Pornește"),
		N_("Nu mai răspunde de un minut."),
		N_("Se caută fișiere .ipk pe stick și disc."),
		N_("Fișiere .ipk de pe stick și disc"),
		N_("și din rețea"),
		N_(", cele mai noi"),
		N_("Se caută în rețea; lista se poate folosi între timp."),
		N_("găsite în rețea."),
		N_("Niciun fișier .ipk în rețea."),
		N_("Un loc răspunde greu."),
		N_("Caută din nou în rețea"),
		N_("Caută și în rețea"),
		N_("Dosarele de rețea (un calculator sau un NAS) nu se caută singure, pot răspunde greu:"),
		N_("Actualizează toate"),
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
