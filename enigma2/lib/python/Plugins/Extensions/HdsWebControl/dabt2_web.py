# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# dabt2_web.py: fereastra „Fluxuri și setări” a DAB+ și DVB-T2 din satelit în interfața web (HdsWebControl).
#
# Pe televizor: Meniu > Scanare > Satelit > DAB+ prin satelit (sau DVB-T2 prin satelit) > „Fluxuri și setări”
# (Hds/DabT2/ecrane.EcranPrincipal). Aici: aceleasi fluxuri cu starea si numarul de posturi, aceleasi actiuni
# (actualizeaza lista, reface buchetele, cauta posturile unui flux, sterge un flux adaugat de mana, adauga de mana),
# aceleasi setari si acelasi „Despre”, din acelasi cod (Hds.DabT2: controlorul, buchete, liste, ecrane).
#
# Rute (poarta comuna a HdsJsonResource; ce schimba ceva cere, cu cookie, POST, aceeasi origine si antetul CSRF):
#   GET  /api/dabt2?fel=dab|t2                         fluxurile, starea, setarile, Despre, lucrul in curs si
#                                                      repunerea canalului de dinainte dupa invatare (ca pe televizor)
#   POST /api/dabt2-actiune?fel=&actiune=actualizeaza|buchete|invata|sterge[&flux=]
#   POST /api/dabt2-seteaza?cheie=tasta|dosar|latime|nedecodabile|liste_zilnic|rezerva&valoare=
#   POST /api/dabt2-manual?fel=&nume=&grade=&emisfera=E|V&frecventa=&pol=&sr=&sistem=&modulatie=&fec=&pid=
#                          [&fel_dab=&ip=&port=]  (DAB)   [&plp=]  (DVB-T2)
#   POST /api/dabt2-televizor?fel=                     deschide fereastra pe televizor
#   GET  /dabt2                                        pagina (?fel=t2 pentru DVB-T2)
#
# FIRUL: render_GET / render_POST ruleaza pe firul enigma2. Citirile sunt mici (listele sunt tinute in memorie de
# controlor dupa semnatura fisierelor); descarcarea listei merge pe firul de fundal al pachetului (Hds/DabT2/fundal),
# invatarea posturilor pe controlor, cu raspunsul in _LUCRU, citit de pagina cat lucrul e in curs. Fisierul nu importa
# nimic din enigma2 la incarcare: probele de pe PC dau obiectul lor pentru Hds.DabT2 (D) si sesiunea lor.


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (probele de pe PC)."""
	if not text:
		return text or ""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text

FELURI = ("dab", "t2")
ACTIUNI = ("actualizeaza", "buchete", "invata", "sterge")
CHEI_SETARI = ("tasta", "dosar", "latime", "nedecodabile", "liste_zilnic", "rezerva")
DA_NU = ("tasta", "nedecodabile", "liste_zilnic")
LATIMI = ("1920", "1280")
POLARIZARI = ("H", "V", "L", "R")
SISTEME = ("DVB-S", "DVB-S2")
MODULATII = ("QPSK", "8PSK", "16APSK", "32APSK")
FEC = ("auto", "1/2", "2/3", "3/4", "3/5", "4/5", "5/6", "7/8", "8/9", "9/10")
FELURI_DAB = ("edi", "ts2na", "ts2na12", "tsniv2ni")
REPUNERE_ARATATA_S = 600     # rezultatul repunerii canalului dupa invatare ramane in pagina atat
REPUNERE_ASTEAPTA_MAX_S = 120  # o repunere care „asteapta” mai mult de atat nu mai are verificare (s-a oprit fara rezultat)

# lucrul pornit din pagina (sau cel mai recent), pe fel: in_curs, mesaj, eroare
_LUCRU = {"dab": {"in_curs": False, "mesaj": "", "eroare": False},
	"t2": {"in_curs": False, "mesaj": "", "eroare": False}}
_FUNDAL = {}


class _Dep(object):
	"""Codul adevarat din Hds.DabT2, importat la prima folosire (probele de pe PC dau obiectul lor)."""

	def __getattr__(self, nume):
		if nume.startswith("__"):
			raise AttributeError(nume)
		import importlib
		modul = importlib.import_module("Hds.DabT2." + nume)
		setattr(self, nume, modul)
		return modul

	def controlor(self, fel):
		return self.imagine.controlor_dab() if fel == "dab" else self.imagine.controlor_t2()


_DEP = [None]


def _d(D=None):
	if D is not None:
		return D
	if _DEP[0] is None:
		_DEP[0] = _Dep()
	return _DEP[0]


def _jurnal(text):
	print("[HdsWebControl] dabt2: %s" % text)


def _text(x):
	if isinstance(x, bytes):
		return x.decode("utf-8", "replace")
	return x if isinstance(x, str) else ("" if x is None else str(x))


def fel_din(valoare):
	return valoare if valoare in FELURI else "dab"


def _acum(ctrl, D):
	"""Ca randul de jos al ferestrei la deschidere (EcranPrincipal._stare_curenta)."""
	_ = D.limba._
	if ctrl.stare == "canta" and ctrl.feed:
		return _("Canta acum: %s pe %s") % (_text(ctrl.feed.get("nume") or ctrl.feed.get("id")),
			_text(D.tuner.text_transponder(ctrl.tp)))
	if ctrl.stare == "pregatire":
		return _("Se pregateste un post.")
	return _("Tunerul porneste doar cand alegi un post din buchetul %s.") % _text(_(ctrl.profil.nume_buchet))


def fluxuri(ctrl, D):
	"""Randurile ferestrei: acelasi calcul ca EcranPrincipal.umple (ecrane.text_stare, ecrane.text_numar,
	tuner.multistream_neprins)."""
	prof = ctrl.profil
	memorate = D.buchete.citeste_servicii(prof)
	# posturile publicate pe stb.hdsatelit.com se socotesc ca in buchet: numai pe transponderele prinse
	stb = D.buchete.citeste_servicii_stb(prof)
	prinse = D.buchete.transpondere_prinse(prof) if stb else None
	rez = []
	for tp in ctrl.lista().get("transpondere", []):
		for f in tp.get("feeduri", []):
			if f.get("tip") != prof.tip:
				continue
			n = len(D.buchete.servicii_feed(prof, f, memorate, stb, tp, prinse))
			ms = bool(D.tuner.multistream_neprins(tp))
			# ca jos in fereastra, fara indemnul pentru telecomanda („apasa OK”): pagina are butonul ei
			parti = [_text(D.tuner.text_multistream())] if ms else [_text(D.ecrane.text_stare(f, tp=tp))]
			if not ms and not n:
				parti.append(_t("Posturile nu sunt căutate încă.") if prof.tip == "dab" else _t("Programele nu sunt "
					"căutate încă."))
			rez.append({
				"id": D.buchete._curata_id(f.get("id")),
				"nume": _text(f.get("nume") or f.get("id")),
				"transponder": _text(D.tuner.text_transponder(tp)),
				"numar": n,
				"numar_text": _text(D.ecrane.text_numar(prof, n)) if n else "",
				"stare": ". ".join(p.rstrip(".") for p in parti if p) + "." if any(parti) else "",
				"manual": f.get("sursa") == "manual",
				"multistream": ms,
			})
	return rez


def _setari(D):
	cfg = D.captura.configureaza()
	dosare = [["auto", "automat"]] + [[x, x] for x in D.captura.DOSARE]
	return {
		"tasta": bool(cfg.tasta.value),
		"dosar": _text(cfg.dosar.value),
		"dosare": dosare,
		"latime": _text(cfg.latime.value),
		"latimi": list(LATIMI),
		"nedecodabile": bool(cfg.nedecodabile.value),
		"liste_zilnic": bool(cfg.liste_zilnic.value),
		"ultima_zilnica": ultima_zilnica(D),
		"rezerva": _text(cfg.rezerva.value),
		"rezerve": [[v, _text(t)] for v, t in D.captura.variante_rezerva()],
	}


def ultima_zilnica(D):
	"""Ultima descarcare zilnica: „azi la 04:12: a mers” sau „... nu a mers (motiv)”; "" daca n-a fost niciuna."""
	try:
		import time
		st = D.liste.citeste_stare_zilnic()
		if not st:
			return ""
		cand = time.strftime("%d.%m.%Y %H:%M", time.localtime(st["la"]))
		if st.get("ok"):
			return _t("Ultima descărcare zilnică: %s, a mers.") % cand
		return _t("Ultima descărcare zilnică: %s, nu a mers (o nouă încercare peste 3 ore).") % cand
	except Exception:
		return ""


def repunere(ctrl):
	"""Dupa „Caută posturile din flux”: canalul de dinainte porneste din nou, iar verificarea de la 9 s spune daca a mers
	(Controlor.repunere: asteapta, pornit, fara_imagine, nepornit). Acelasi text ca fereastra de pe televizor; {} cand
	nu e nimic de spus (fara invatare, alt canal ales intre timp, rezultat mai vechi de REPUNERE_ARATATA_S)."""
	import time
	r = getattr(ctrl, "repunere", None)
	if not isinstance(r, dict) or not r.get("stare") or not r.get("mesaj"):
		return {}
	la_mono = r.get("la_mono")
	if isinstance(la_mono, (int, float)) and not isinstance(la_mono, bool):
		# varsta pe ceasul monoton (acelasi ca Hds.DabT2.compat.monoton pe Python 3): nu sare cand ora se potriveste din retea
		trecut = time.monotonic() - la_mono
	else:
		trecut = time.time() - (r.get("la") or 0)
	if trecut > (REPUNERE_ASTEAPTA_MAX_S if r.get("stare") == "asteapta" else REPUNERE_ARATATA_S):
		# „asteapta” mai vechi decat cea mai lunga verificare (9 s + rotirea antenei, cel mult 60 s) inseamna o verificare
		# oprita fara rezultat: pagina nu mai cere starea la 2 s fara sfarsit
		return {}
	return {"stare": _text(r.get("stare")), "mesaj": _text(r.get("mesaj")),
		"eroare": r.get("stare") in ("nepornit", "fara_imagine")}


def stare(fel, D=None):
	"""Pentru GET /api/dabt2."""
	D = _d(D)
	fel = fel_din(fel)
	ctrl = D.controlor(fel)
	_ = D.limba._
	return {
		"repunere": repunere(ctrl),
		"result": True,
		"fel": fel,
		"titlu": _text(_(ctrl.profil.titlu)),
		"acum": _text(_acum(ctrl, D)),
		"fluxuri": fluxuri(ctrl, D),
		"setari": _setari(D),
		"despre": _text(_(D.profil.DESPRE)),
		"lucru": dict(_LUCRU[fel]),
		"poate_invata": getattr(ctrl, "sesiune", None) is not None,
		# fapta „cauta” si randul ei de ajutor, aceleasi ca pe televizor (Hds/DabT2/ecrane)
		"text_cauta": _text(D.ecrane.text_cauta(ctrl.profil)),
		"ajutor_cauta": _text(D.ecrane.text_ajutor_cauta(ctrl.profil)),
		"multistream_in_nucleu": bool(D.tuner.nucleu_multistream()),
	}


def _cu_stare(fel, D, rezultat, mesaj):
	rez = stare(fel, D)
	rez.update({"result": bool(rezultat), "message": mesaj})
	return rez


def _ocupat(sesiune):
	"""Acelasi refuz ca la pornirea unei scanari: standby, o scanare deschisa pe televizor."""
	try:
		from . import scanare_web
	except ImportError:
		return None
	return scanare_web._ocupat(sesiune)


# ---------------------------------------------------------------- actiunile
def _actualizat(fel, D, ok, rez):
	if ok and isinstance(rez, tuple):
		ok, mesaj_jurnal = rez
	else:
		mesaj_jurnal = rez
	ctrl = D.controlor(fel)
	_ = D.limba._
	try:
		D.jurnal.noteaza(ctrl.profil.eticheta, "actualizare din web: %s %s" % (ok, mesaj_jurnal))
	except Exception:
		pass
	if ok:
		ctrl.lista(forteaza=True)
		r = ctrl.reface_buchete()
		_LUCRU[fel] = {"in_curs": False, "eroare": False,
			"mesaj": _text(_("Lista actualizata. Intrari in buchet: %d.") % r.get("intrari", 0))}
	else:
		_LUCRU[fel] = {"in_curs": False, "eroare": True, "mesaj": _text(D.ecrane.text_actualizare_esuata())}


def _invatat(fel, D, ok, rez):
	ctrl = D.controlor(fel)
	if ok:
		mesaj = _text(D.ecrane.text_gasite(ctrl.profil, rez))
	else:
		mesaj = rez
	_LUCRU[fel] = {"in_curs": False, "eroare": not ok, "mesaj": _text(mesaj)}


def actiune(fel, ce, flux="", D=None, sesiune=None):
	"""POST /api/dabt2-actiune."""
	D = _d(D)
	fel = fel_din(fel)
	if ce not in ACTIUNI:
		return _cu_stare(fel, D, False, _t("Se alege cu actiune=actualizeaza, buchete, invata sau sterge."))
	ctrl = D.controlor(fel)
	prof = ctrl.profil
	_ = D.limba._
	if ce == "actualizeaza":
		if _LUCRU[fel]["in_curs"]:
			return _cu_stare(fel, D, False, _t("Lucrul de dinainte nu s-a terminat. Așteaptă puțin."))
		fundal = _FUNDAL.get(fel)
		if fundal is None:
			fundal = _FUNDAL[fel] = D.fundal.Fundal("web-" + fel)
		_LUCRU[fel] = {"in_curs": True, "eroare": False, "mesaj": _text(_("Descarc lista de pe hdsatelit.com..."))}
		pornit = fundal.lanseaza(D.liste.actualizeaza, lambda ok, r: _actualizat(fel, D, ok, r), prof.tip,
			prof.director)
		if pornit is False:
			_LUCRU[fel] = {"in_curs": False, "eroare": True, "mesaj": _t("Descărcarea nu a pornit.")}
			return _cu_stare(fel, D, False, _LUCRU[fel]["mesaj"])
		return _cu_stare(fel, D, True, _LUCRU[fel]["mesaj"])
	if ce == "buchete":
		r = ctrl.reface_buchete()
		if r.get("eroare"):
			mesaj, ok = _("Buchetul nu s-a putut scrie. Detalii in jurnal."), False
		else:
			mesaj = (_("Buchet refacut. Intrari: %d, fluxuri: %d.") if r.get("schimbat") else
				_("Buchetul era la zi. Intrari: %d, fluxuri: %d.")) % (r.get("intrari", 0), r.get("feeduri", 0))
			ok = True
		_LUCRU[fel] = {"in_curs": False, "eroare": not ok, "mesaj": _text(mesaj)}
		return _cu_stare(fel, D, ok, _text(mesaj))
	f, tp = ctrl.cauta_feed(D.buchete._curata_id(flux or ""))
	if f is None:
		return _cu_stare(fel, D, False, _t("Fluxul nu mai e în listă. Citește pagina din nou."))
	if ce == "sterge":
		if f.get("sursa") != "manual":
			return _cu_stare(fel, D, False, _t("Se șterg numai fluxurile adăugate de mână."))
		D.ecrane.sterge_manual(prof, f.get("id"))
		ctrl.lista(forteaza=True)
		mesaj = _t("Am șters fluxul „%s”.") % _text(f.get("nume") or f.get("id"))
		_LUCRU[fel] = {"in_curs": False, "eroare": False, "mesaj": mesaj}
		return _cu_stare(fel, D, True, mesaj)
	# invata
	if D.tuner.multistream_neprins(tp):
		return _cu_stare(fel, D, False, _text(D.tuner.text_multistream()))
	if _LUCRU[fel]["in_curs"] or (getattr(ctrl, "mod", None) == "invata" and ctrl.stare != "oprit"):
		return _cu_stare(fel, D, False, _t("Lucrul de dinainte nu s-a terminat. Așteaptă puțin."))
	if sesiune is None:
		sesiune = getattr(ctrl, "sesiune", None)
	refuz = _ocupat(sesiune)
	if refuz:
		return _cu_stare(fel, D, False, refuz)
	if getattr(ctrl, "sesiune", None) is None:
		return _cu_stare(fel, D, False, _t("Receptorul nu a terminat pornirea. Încearcă din nou peste un minut."))
	_LUCRU[fel] = {"in_curs": True, "eroare": False,
		"mesaj": _text(D.ecrane.text_caut(ctrl.profil, _text(f.get("nume") or f.get("id"))))}
	ctrl.invata(f, tp, lambda ok, r: _invatat(fel, D, ok, r))
	return _cu_stare(fel, D, True, _LUCRU[fel]["mesaj"])


def seteaza(argumente, D=None, configfile=None):
	"""POST /api/dabt2-seteaza: o cheie sau o valoare straina nu schimba nimic."""
	D = _d(D)
	fel = fel_din(argumente.get("fel"))
	cheie, valoare = argumente.get("cheie"), argumente.get("valoare", "")
	if cheie not in CHEI_SETARI:
		return _cu_stare(fel, D, False, _t("Se alege cu cheie=tasta, dosar, latime, nedecodabile, liste_zilnic sau "
			"rezerva."))
	cfg = D.captura.configureaza()
	if cheie in DA_NU:
		if valoare not in ("0", "1"):
			return _cu_stare(fel, D, False, _t("Se alege cu valoare=1 sau valoare=0."))
		nou = valoare == "1"
	elif cheie == "dosar":
		if valoare != "auto" and valoare not in D.captura.DOSARE:
			return _cu_stare(fel, D, False, _t("Dosarul nu e unul din listă."))
		nou = valoare
	elif cheie == "rezerva":
		if valoare not in D.captura.REZERVE_MS:
			return _cu_stare(fel, D, False, _t("Rezerva nu e una din listă."))
		nou = valoare
	else:
		if valoare not in LATIMI:
			return _cu_stare(fel, D, False, _t("Lățimea nu e una din listă."))
		nou = valoare
	element = getattr(cfg, cheie)
	element.value = nou
	element.save()
	if configfile is None:
		from Components.config import configfile
	configfile.save()
	if cheie == "tasta":
		try:
			D.captura.obtine(D.controlor(fel).coord).leaga_tasta()
		except Exception as eroare:
			_jurnal("tasta capturii: %s" % eroare)
	if cheie == "nedecodabile":
		# ca la inchiderea Setarilor pe televizor: lista si buchetul fiecarui fel, daca s-a schimbat ceva
		for f in FELURI:
			try:
				ctrl = D.controlor(f)
				inainte = ctrl._lista_semn
				ctrl.lista()
				if ctrl._lista_semn != inainte:
					ctrl.reface_buchete()
			except Exception as eroare:
				_jurnal("lista %s dupa setare: %s" % (f, eroare))
	return _cu_stare(fel, D, True, _t("Salvat."))


def pozitie_din(grade, emisfera):
	"""„19,2” + E -> 192; „0,8” + V -> 3592 (zecimi de grad, ca in listele DAB+ / DVB-T2). Emisfera: E si V ca pana
	acum, plus W si literele limbii meniului (O = vest in franceza, Ny = vest in maghiara...); se salveaza tot zecimile
	de mai sus. None daca nu e valida."""
	try:
		g = float(str(grade).replace(",", ".").strip())
	except (TypeError, ValueError):
		return None
	emisfera = _emisfera(emisfera)
	if not 0 <= g <= 180 or emisfera not in ("E", "V"):
		return None
	zecimi = int(round(g * 10))
	if emisfera == "V" and zecimi:
		zecimi = 3600 - zecimi
	return zecimi if 0 <= zecimi <= 3599 else None


def _emisfera(text):
	"""„E” / „V” din ce trimite pagina (Components/HdsGrade.py, emisfera); fara modulul imaginii, numai E si V"""
	if text in ("E", "V"):
		return text
	try:
		from Components.HdsGrade import emisfera
		return emisfera(text)
	except Exception:
		return None


def _litere():
	"""literele estului si vestului in limba meniului, pentru lista din pagina (valorile trimise raman E si V)"""
	try:
		from Components.HdsGrade import litereEstVest
		est, vest = litereEstVest()
	except Exception:
		est, vest = "E", "V"
	scapa = lambda t: str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
	return scapa(est), scapa(vest)


def _intreg(argumente, cheie, minim, maxim):
	try:
		v = int(str(argumente.get(cheie, "")).strip())
	except (TypeError, ValueError):
		return None
	return v if minim <= v <= maxim else None


def manual(argumente, D=None):
	"""POST /api/dabt2-manual: aceleasi campuri si aceleasi limite ca „Adauga manual” pe televizor; fluxul se scrie
	cu ecrane.feed_manual si ecrane.adauga_manual (acelasi manual.json)."""
	D = _d(D)
	fel = fel_din(argumente.get("fel"))
	ctrl = D.controlor(fel)
	prof = ctrl.profil
	v = {"nume": (argumente.get("nume") or "").strip()[:40],
		"pozitie": pozitie_din(argumente.get("grade"), argumente.get("emisfera")),
		"frecventa": _intreg(argumente, "frecventa", 10700, 12750),
		"pol": argumente.get("pol"), "sr": _intreg(argumente, "sr", 1000, 60000),
		"sistem": argumente.get("sistem"), "modulatie": argumente.get("modulatie"), "fec": argumente.get("fec"),
		"pid": _intreg(argumente, "pid", 32, 8190), "multistream": "nu", "is_id": 0, "pls_cod": 0}
	gresite = []
	for cheie, bun in (("pozitie", v["pozitie"] is not None), ("frecventa", v["frecventa"] is not None),
			("pol", v["pol"] in POLARIZARI), ("sr", v["sr"] is not None), ("sistem", v["sistem"] in SISTEME),
			("modulatie", v["modulatie"] in MODULATII), ("fec", v["fec"] in FEC), ("pid", v["pid"] is not None)):
		if not bun:
			gresite.append(cheie)
	if fel == "dab":
		v["fel"] = argumente.get("fel_dab") or "edi"
		v["ip"] = (argumente.get("ip") or "239.0.0.1").strip()[:40]
		v["port"] = _intreg(argumente, "port", 1, 65535)
		if v["fel"] not in FELURI_DAB:
			gresite.append("fel_dab")
		if v["port"] is None:
			gresite.append("port")
	else:
		v["plp"] = _intreg(argumente, "plp", 0, 255)
		if v["plp"] is None:
			gresite.append("plp")
	if gresite:
		rez = _cu_stare(fel, D, False, _t("Verifică valorile: %s.") % ", ".join(gresite))
		rez["gresite"] = gresite
		return rez
	tp, feed = D.ecrane.feed_manual(prof, v)
	ok, mesaj = D.ecrane.adauga_manual(prof, tp, feed)
	if not ok:
		_jurnal("flux manual respins: %s" % mesaj)
		return _cu_stare(fel, D, False, _text(D.limba._("Datele feed-ului nu sunt valide.")))
	ctrl.lista(forteaza=True)
	mesaj = _t("Am adăugat fluxul „%s”. Apasă „%s” la el.") % (_text(feed.get("nume")),
		_text(D.ecrane.text_cauta(prof)))
	_LUCRU[fel] = {"in_curs": False, "eroare": False, "mesaj": mesaj}
	return _cu_stare(fel, D, True, mesaj)


def televizor(fel, sesiune=None, D=None):
	"""POST /api/dabt2-televizor: fereastra „Fluxuri și setări” a felului, deschisa pe televizor."""
	fel = fel_din(fel)
	refuz = _ocupat(sesiune)
	if refuz:
		return {"result": False, "message": refuz}
	try:
		from Screens.HdsComunPrincipal import HdsDabPrincipal, HdsT2miPrincipal
		dlg = sesiune.open(HdsDabPrincipal if fel == "dab" else HdsT2miPrincipal)
	except Exception as eroare:
		_jurnal("fereastra %s pe televizor: %s" % (fel, eroare))
		return {"result": False, "message": _t("Fereastra nu s-a deschis pe televizor (%s).") % eroare}
	if dlg is None:
		return {"result": False, "message": _t("Fereastra nu s-a deschis pe televizor. Detalii în jurnalul "
			"receptorului.")}
	return {"result": True, "message": _t("S-a deschis pe televizor: Fluxuri și setări.")}


# ---------------------------------------------------------------- cererile
CHEI_CERERE = ("fel", "actiune", "flux", "cheie", "valoare", "nume", "grade", "emisfera", "frecventa", "pol", "sr",
	"sistem", "modulatie", "fec", "pid", "fel_dab", "ip", "port", "plp")


def argumente(request):
	"""Argumentele cunoscute ale cererii ca text scurt: {cheie: text}, fara token."""
	rez = {}
	for cheie, valori in list((getattr(request, "args", None) or {}).items())[:30]:
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie not in CHEI_CERERE:
			continue
		v = (valori or [b""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:64].strip()
	return rez


def rute(baza, resource, sesiune=None, D=None):
	"""Resursele: ({nume: resursa de sub /api}, resursa paginii). `baza` e HdsJsonResource din plugin.py; `sesiune`
	intoarce sesiunea enigma2 tinuta de plugin.py."""

	def _sesiune():
		try:
			return sesiune() if callable(sesiune) else sesiune
		except Exception:
			return None

	class StareResource(baza):
		"""GET /api/dabt2: numai citire."""

		def render_GET(self, request):
			try:
				return self._raspunde(request, stare(argumente(request).get("fel"), D))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

	class ActiuneResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				a = argumente(request)
				return self._raspunde(request, actiune(a.get("fel"), a.get("actiune"), a.get("flux", ""), D,
					_sesiune()))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)   # numai cu ?token= (scripturi); din browser poarta cere POST

	class SeteazaResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, seteaza(argumente(request), D))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class ManualResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, manual(argumente(request), D))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class TelevizorResource(baza):
		schimbaCeva = True

		def render_POST(self, request):
			try:
				return self._raspunde(request, televizor(argumente(request).get("fel"), _sesiune(), D))
			except Exception as eroare:
				return self._eroare(request, _t("Eroare pe receptor: %s") % eroare, 500)

		def render_GET(self, request):
			return self.render_POST(request)

	class PaginaResource(resource.Resource):
		"""GET /dabt2: pagina „Fluxuri și setări”."""
		isLeaf = True

		def render_GET(self, request):
			return pagina(request)

	api = {
		b"dabt2": StareResource(),
		b"dabt2-actiune": ActiuneResource(),
		b"dabt2-seteaza": SeteazaResource(),
		b"dabt2-manual": ManualResource(),
		b"dabt2-televizor": TelevizorResource(),
	}
	return api, PaginaResource()


def pagina(request):
	"""Aceeasi poarta ca /paznic si /ceas."""
	from . import plugin as P
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return pagina_text(P._STIL_COMUN, config_pagina).encode("utf-8", "replace")


def _drumMeniu(id_intrare):
	"""Drumul de pe televizor spre ecran (meniu_web.drumHtml); modulul incarcat singur, fara pachet (probele de pe
	PC), nu are meniul, deci ramane „Meniu”."""
	try:
		from .meniu_web import drumHtml
	except ImportError:
		return "Meniu"
	return drumHtml(id_intrare)


def pagina_text(stil, config_pagina):
	est, vest = _litere()
	return (_traducePagina(PAGINA).replace("__STIL_COMUN__", stil).replace("__CONFIG__", config_pagina)
		.replace("__DRUM_DAB__", _drumMeniu("hds_satelit_dab")).replace("__DRUM_T2__", _drumMeniu("hds_satelit_dvbt2"))
		.replace("__LITERA_EST__", est).replace("__LITERA_VEST__", vest))


PAGINA = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fluxuri și setări DAB+ și DVB-T2</title>
<style>__STIL_COMUN__
  main{max-width:860px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 10px;}
  h2{font-size:1.05rem;margin:0 0 8px;}
  .file{display:flex;gap:8px;margin:0 0 12px;}
  .file a{flex:1;text-align:center;padding:10px;border:1px solid var(--bordura);border-radius:8px;text-decoration:none;color:var(--text);min-height:44px;}
  .file a.ales{background:var(--accent);border-color:var(--accent);}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .acum{font-size:1rem;line-height:1.45;margin:0;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 0;}
  button{background:#242a33;color:var(--text);border:1px solid var(--bordura);border-radius:8px;padding:10px 14px;min-height:44px;font:inherit;cursor:pointer;}
  button.principal{background:var(--accent);border-color:var(--accent);}
  button:disabled{opacity:.5;cursor:default;}
  .flux{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;padding:10px 0;border-bottom:1px solid var(--bordura);}
  .flux:last-child{border-bottom:0;}
  .flux b{display:block;overflow-wrap:anywhere;}
  .flux small{display:block;color:var(--text-slab);line-height:1.4;}
  .flux .numar{color:var(--text);}
  .flux .ms{color:var(--galben);}
  .rand{display:grid;grid-template-columns:1fr minmax(150px,240px);gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid var(--bordura);}
  .rand:last-child{border-bottom:0;}
  .rand select,.rand input{min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font:inherit;width:100%;}
  .pozitie{display:grid;grid-template-columns:1fr 90px;gap:8px;}
  summary{cursor:pointer;min-height:44px;line-height:44px;font-weight:600;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;min-height:1.3em;}
  .eroare{color:#ffb4a8;}
  .ascuns{display:none;}
  @media (max-width:560px){ .rand{grid-template-columns:1fr;} .flux{grid-template-columns:1fr;} }
</style>
</head>
<body>
<main>
<h1 id="titlu">Fluxuri și setări</h1>
<nav class="file"><a href="?fel=dab" id="filaDab">DAB+ din satelit</a><a href="?fel=t2" id="filaT2">DVB-T2 din satelit</a></nav>
<p class="mesaj" id="incarcare">Se citește starea...</p>
<div id="continut" class="ascuns">
  <section class="card">
    <p class="acum" id="acum"></p>
    <p class="mesaj" id="lucru" role="status"></p>
    <p class="mesaj ascuns" id="repunere" role="status"></p>
    <div class="butoane">
      <button type="button" id="actualizeaza">Actualizează lista de pe hdsatelit.com</button>
      <button type="button" id="buchete">Refă buchetele</button>
      <button type="button" id="televizor">Deschide pe televizor</button>
    </div>
    <p class="nota" id="drum">Pe televizor: <span id="drumDab">__DRUM_DAB__</span><span id="drumT2">__DRUM_T2__</span> &gt; Fluxuri și setări.</p>
  </section>
  <section class="card">
    <h2 id="titluFluxuri">Fluxuri în listă</h2>
    <p class="nota">Un flux e un transponder cu posturi DAB+ sau programe DVB-T2. <span id="notaCauta"></span></p>
    <div id="fluxuri"></div>
  </section>
  <section class="card">
    <details id="manual">
      <summary>Adaugă un flux de mână</summary>
      <div class="rand"><label for="m_nume">Nume</label><input id="m_nume" maxlength="40"></div>
      <div class="rand"><label for="m_grade">Poziția orbitală</label><div class="pozitie"><input id="m_grade" inputmode="decimal" value="19,2"><select id="m_emisfera"><option value="E">__LITERA_EST__</option><option value="V">__LITERA_VEST__</option></select></div></div>
      <div class="rand"><label for="m_frecventa">Frecvența (MHz)</label><input id="m_frecventa" inputmode="numeric" value="12460"></div>
      <div class="rand"><label for="m_pol">Polarizarea</label><select id="m_pol"><option value="H">Orizontală</option><option value="V">Verticală</option><option value="L">Circulară stânga</option><option value="R">Circulară dreapta</option></select></div>
      <div class="rand"><label for="m_sr">Rata de simboluri (kS/s)</label><input id="m_sr" inputmode="numeric" value="27500"></div>
      <div class="rand"><label for="m_sistem">Sistemul</label><select id="m_sistem"><option>DVB-S2</option><option>DVB-S</option></select></div>
      <div class="rand"><label for="m_modulatie">Modulația</label><select id="m_modulatie"><option>QPSK</option><option>8PSK</option><option>16APSK</option><option>32APSK</option></select></div>
      <div class="rand"><label for="m_fec">FEC</label><select id="m_fec"><option value="auto">auto</option><option>1/2</option><option>2/3</option><option>3/4</option><option>3/5</option><option>4/5</option><option>5/6</option><option>7/8</option><option>8/9</option><option>9/10</option></select></div>
      <div class="rand"><label for="m_pid">PID</label><input id="m_pid" inputmode="numeric" value="4096"></div>
      <div class="rand campDab"><label for="m_fel_dab">Felul</label><select id="m_fel_dab"><option value="edi">EDI prin MPE</option><option value="ts2na">ETI-NA în TS</option><option value="ts2na12">ETI-NA în TS (12)</option><option value="tsniv2ni">ETI-NI în TS</option></select></div>
      <div class="rand campDab"><label for="m_ip">IP (numai EDI)</label><input id="m_ip" value="239.0.0.1"></div>
      <div class="rand campDab"><label for="m_port">Port UDP (numai EDI)</label><input id="m_port" inputmode="numeric" value="50000"></div>
      <div class="rand campT2"><label for="m_plp">PLP</label><input id="m_plp" inputmode="numeric" value="0"></div>
      <p class="nota" id="notaMultistream">Fluxurile de pe transpondere cu mai multe fluxuri (multistream) nu se pot adăuga încă: imaginea nu le poate recepționa.</p>
      <div class="butoane"><button type="button" class="principal" id="adauga">Adaugă fluxul</button></div>
    </details>
  </section>
  <section class="card">
    <h2>Setări</h2>
    <div class="rand"><label for="s_tasta">Captura ecranului cu apăsare lungă pe INFO</label><select id="s_tasta"><option value="1">Da</option><option value="0">Nu</option></select></div>
    <div class="rand"><label for="s_dosar">Dosarul capturilor</label><select id="s_dosar"></select></div>
    <div class="rand"><label for="s_latime">Lățimea capturii</label><select id="s_latime"></select></div>
    <div class="rand"><label for="s_nedecodabile">Arată și fluxurile care nu se decodează</label><select id="s_nedecodabile"><option value="1">Da</option><option value="0">Nu</option></select></div>
    <div class="rand"><label for="s_liste_zilnic">Ia listele DAB+ și DVB-T2 de pe stb.hdsatelit.com în fiecare zi</label><select id="s_liste_zilnic"><option value="1">Da</option><option value="0">Nu</option></select></div>
    <p class="nota">O dată pe zi, în fundal, receptorul ia de pe stb.hdsatelit.com frecvențele și numele posturilor. Butonul „Actualizează lista” merge oricând. <span id="ultimaZilnica"></span></p>
    <div class="rand"><label for="s_rezerva">Rezervă la pornirea postului</label><select id="s_rezerva"></select></div>
    <p class="nota">La pornirea unui post, receptorul ține o rezervă din flux, ca întreruperile scurte să nu se vadă și să nu se audă. Postul pornește cu atât mai târziu. Aceeași rezervă la DAB+ și la DVB-T2.</p>
    <p class="nota">Aceleași setări sunt pe televizor, în „Fluxuri și setări”, pe tasta MENU.</p>
  </section>
  <section class="card">
    <h2>Despre</h2>
    <p class="acum" id="despre"></p>
  </section>
  <p class="mesaj" id="mesaj" role="status"></p>
</div>
</main>
<script>
var CFG = __CONFIG__;
var FEL = (new URLSearchParams(location.search).get("fel") === "t2") ? "t2" : "dab";
var S = {semn: "", urmarire: null};
function $(id){ return document.getElementById(id); }
function el(tag, cls, text){ var e = document.createElement(tag); if(cls){ e.className = cls; } if(text !== undefined){ e.textContent = text; } return e; }
function arata(e, da){ e.classList.toggle("ascuns", !da); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){ return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."}; });
  });
}
function mesaj(text, eroare){ var m = $("mesaj"); m.textContent = text || ""; m.classList.toggle("eroare", !!eroare); }
function optiuni(sel, lista, valoare){
  if(document.activeElement === sel){ return; }
  sel.textContent = "";
  lista.forEach(function(a){ var o = el("option", "", a[1]); o.value = a[0]; sel.appendChild(o); });
  sel.value = valoare;
}
function deseneazaFluxurile(d){
  var semn = JSON.stringify([d.fluxuri, d.lucru.in_curs, d.poate_invata]);
  if(semn === S.semn){ return; }
  S.semn = semn;
  var cutie = $("fluxuri"); cutie.textContent = "";
  $("titluFluxuri").textContent = "Fluxuri în listă: " + d.fluxuri.length;
  if(!d.fluxuri.length){ cutie.appendChild(el("p", "nota", "Lista e goală. Actualizează lista de pe hdsatelit.com sau adaugă un flux de mână.")); return; }
  d.fluxuri.forEach(function(f){
    var r = el("div", "flux"), t = el("div");
    t.appendChild(el("b", "", f.nume));
    var linie = el("small", "", f.transponder + (f.numar_text ? " · " : ""));
    if(f.numar_text){ linie.appendChild(el("span", "numar", f.numar_text)); }
    t.appendChild(linie);
    if(f.stare){ t.appendChild(el("small", f.multistream ? "ms" : "", f.stare)); }
    r.appendChild(t);
    var b = el("div", "butoane");
    if(!f.multistream){
      var inv = el("button", "", f.numar ? "Caută din nou" : d.text_cauta);
      inv.type = "button"; inv.disabled = d.lucru.in_curs || !d.poate_invata; inv.title = d.ajutor_cauta;
      inv.addEventListener("click", function(){ faActiunea("invata", f.id); });
      b.appendChild(inv);
    }
    if(f.manual){
      var st = el("button", "", "Șterge fluxul"); st.type = "button";
      st.addEventListener("click", function(){ if(confirm("Ștergi fluxul „" + f.nume + "”?")){ faActiunea("sterge", f.id); } });
      b.appendChild(st);
    }
    r.appendChild(b);
    cutie.appendChild(r);
  });
}
function deseneaza(d){
  $("titlu").textContent = "Fluxuri și setări: " + d.titlu;
  document.title = "Fluxuri și setări: " + d.titlu;
  $("filaDab").classList.toggle("ales", FEL === "dab"); $("filaT2").classList.toggle("ales", FEL === "t2");
  $("acum").textContent = d.acum;
  // ce face „Caută posturile din flux”, cu aceleasi cuvinte ca pe televizor
  $("notaCauta").textContent = "„" + d.text_cauta + "”: " + d.ajutor_cauta.charAt(0).toLowerCase() + d.ajutor_cauta.slice(1);
  var l = $("lucru"); l.textContent = d.lucru.mesaj || ""; l.classList.toggle("eroare", !!d.lucru.eroare);
  // dupa cautarea posturilor: canalul de dinainte, cu acelasi text ca fereastra de pe televizor
  var rp = d.repunere || {}, er = $("repunere");
  er.textContent = rp.mesaj || ""; er.classList.toggle("eroare", !!rp.eroare); arata(er, !!rp.mesaj);
  $("actualizeaza").disabled = d.lucru.in_curs;
  arata($("drumDab"), FEL === "dab"); arata($("drumT2"), FEL === "t2");
  deseneazaFluxurile(d);
  var s = d.setari;
  if(document.activeElement !== $("s_tasta")){ $("s_tasta").value = s.tasta ? "1" : "0"; }
  if(document.activeElement !== $("s_nedecodabile")){ $("s_nedecodabile").value = s.nedecodabile ? "1" : "0"; }
  if(document.activeElement !== $("s_liste_zilnic")){ $("s_liste_zilnic").value = s.liste_zilnic ? "1" : "0"; }
  $("ultimaZilnica").textContent = s.ultima_zilnica || "";
  optiuni($("s_rezerva"), s.rezerve, s.rezerva);
  optiuni($("s_dosar"), s.dosare, s.dosar);
  optiuni($("s_latime"), s.latimi.map(function(x){ return [x, x + " px"]; }), s.latime);
  Array.prototype.forEach.call(document.querySelectorAll(".campDab"), function(e){ arata(e, FEL === "dab"); });
  Array.prototype.forEach.call(document.querySelectorAll(".campT2"), function(e){ arata(e, FEL === "t2"); });
  arata($("notaMultistream"), !d.multistream_in_nucleu);
  $("despre").textContent = d.despre;
  // se citeste din nou cat lucrul e in curs si cat verificarea canalului repus (la ~9 s dupa invatare) nu a raspuns
  var asteapta = d.lucru.in_curs || (d.repunere && d.repunere.stare === "asteapta");
  if(asteapta && !S.urmarire){ S.urmarire = setTimeout(function(){ S.urmarire = null; citeste(); }, 2000); }
}
function citeste(){
  return cerere("/api/dabt2?fel=" + FEL).then(function(d){
    if(!d.result){ $("incarcare").textContent = d.message || "Receptorul nu a putut citi starea."; return; }
    $("incarcare").classList.add("ascuns"); $("continut").classList.remove("ascuns");
    deseneaza(d);
  }).catch(function(){ $("incarcare").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
function trimite(cale, q, text){
  mesaj(text || "Se trimite...");
  return cerere(cale, "POST", q).then(function(d){ mesaj(d.message, !d.result); if(d.fluxuri){ deseneaza(d); } return d; })
    .catch(function(){ mesaj("Receptorul nu răspunde.", true); });
}
function faActiunea(ce, flux){
  var q = new URLSearchParams(); q.set("fel", FEL); q.set("actiune", ce); if(flux){ q.set("flux", flux); }
  trimite("/api/dabt2-actiune", q);
}
function seteaza(cheie, valoare){
  var q = new URLSearchParams(); q.set("fel", FEL); q.set("cheie", cheie); q.set("valoare", valoare);
  trimite("/api/dabt2-seteaza", q, "Se salvează...");
}
$("actualizeaza").addEventListener("click", function(){ faActiunea("actualizeaza"); });
$("buchete").addEventListener("click", function(){ faActiunea("buchete"); });
$("televizor").addEventListener("click", function(){ var q = new URLSearchParams(); q.set("fel", FEL); trimite("/api/dabt2-televizor", q, "Se deschide pe televizor..."); });
["tasta", "dosar", "latime", "nedecodabile", "liste_zilnic", "rezerva"].forEach(function(c){ $("s_" + c).addEventListener("change", function(){ seteaza(c, this.value); }); });
$("adauga").addEventListener("click", function(){
  var q = new URLSearchParams(); q.set("fel", FEL);
  ["nume", "grade", "emisfera", "frecventa", "pol", "sr", "sistem", "modulatie", "fec", "pid", "fel_dab", "ip", "port", "plp"].forEach(function(c){ q.set(c, $("m_" + c).value); });
  trimite("/api/dabt2-manual", q, "Se adaugă...").then(function(d){ if(d && d.result){ $("manual").open = false; } });
});
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
		N_("Fluxuri și setări DAB+ și DVB-T2"),
		N_("Fluxuri și setări"),
		N_("DAB+ din satelit"),
		N_("DVB-T2 din satelit"),
		N_("Se citește starea..."),
		N_("Actualizează lista de pe hdsatelit.com"),
		N_("Refă buchetele"),
		N_("Deschide pe televizor"),
		N_("Pe televizor: <span id=\"drumDab\">__DRUM_DAB__</span><span id=\"drumT2\">__DRUM_T2__</span> &gt; "
			"Fluxuri și setări."),
		N_("Fluxuri în listă"),
		N_("Un flux e un transponder cu posturi DAB+ sau programe DVB-T2. <span id=\"notaCauta\"></span>"),
		N_("Adaugă un flux de mână"),
		N_("Nume"),
		N_("Poziția orbitală"),
		N_("Frecvența (MHz)"),
		N_("Polarizarea"),
		N_("Orizontală"),
		N_("Verticală"),
		N_("Circulară stânga"),
		N_("Circulară dreapta"),
		N_("Rata de simboluri (kS/s)"),
		N_("Sistemul"),
		N_("Modulația"),
		N_("auto"),
		N_("Felul"),
		N_("EDI prin MPE"),
		N_("ETI-NA în TS"),
		N_("ETI-NA în TS (12)"),
		N_("ETI-NI în TS"),
		N_("IP (numai EDI)"),
		N_("Port UDP (numai EDI)"),
		N_("Fluxurile de pe transpondere cu mai multe fluxuri (multistream) nu se pot adăuga încă: imaginea "
			"nu le poate recepționa."),
		N_("Adaugă fluxul"),
		N_("Setări"),
		N_("Captura ecranului cu apăsare lungă pe INFO"),
		N_("Da"),
		N_("Nu"),
		N_("Dosarul capturilor"),
		N_("Lățimea capturii"),
		N_("Arată și fluxurile care nu se decodează"),
		N_("Ia listele DAB+ și DVB-T2 de pe stb.hdsatelit.com în fiecare zi"),
		N_("O dată pe zi, în fundal, receptorul ia de pe stb.hdsatelit.com frecvențele și numele "
			"posturilor. Butonul „Actualizează lista” merge oricând. <span id=\"ultimaZilnica\"></span>"),
		N_("Rezervă la pornirea postului"),
		N_("La pornirea unui post, receptorul ține o rezervă din flux, ca întreruperile scurte să nu se "
			"vadă și să nu se audă. Postul pornește cu atât mai târziu. Aceeași rezervă la DAB+ și la DVB-T2."),
		N_("Aceleași setări sunt pe televizor, în „Fluxuri și setări”, pe tasta MENU."),
		N_("Despre"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Fluxuri în listă:"),
		N_("Lista e goală. Actualizează lista de pe hdsatelit.com sau adaugă un flux de mână."),
		N_("Caută din nou"),
		N_("Șterge fluxul"),
		N_("Ștergi fluxul „"),
		N_("Fluxuri și setări:"),
		N_("Receptorul nu a putut citi starea."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Se trimite..."),
		N_("Receptorul nu răspunde."),
		N_("Se salvează..."),
		N_("Se deschide pe televizor..."),
		N_("Se adaugă..."),
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
