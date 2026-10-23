# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# antena_web.py: „Configurare LNB”, „Găsire semnal” si comenzile din „Rotirea antenei” in interfata web
# (HdsWebControl).
#
# Sectiunea „Orientarea și setarea antenei” cu tunerul, LNB-ul, motorul, calculatorul, gasirea semnalului si DiSEqC
# la indemana; orice ecran de pe televizor are si pagina lui in interfata web. Aici sunt trei dintre ele.
#
# O SINGURA LOGICA, NIMIC SCRIS A DOUA OARA: tot ce citeste, planifica, scrie, acordeaza sau misca vine din aceleasi
# module ca ecranele de pe televizor:
#   - Configurare LNB  Components/HdsLnb.py (citeste, planifica, detalii) si Components/HdsLnbAplicare.py (aplica,
#                      proba de semnal, pastreaza, revino, motivOcupat, „Ce era înainte”);
#   - Găsire semnal    Components/HdsGasireSemnal.py (tunere, transpondere, masurare(): porneste, schimba,
#                      reacordeaza, opreste, stare, tine_viu), cu cine="web";
#   - Rotirea antenei  Components/HdsMotorComenzi.py (comenzi(): pas, continuu, pozitii, limite, mergi la satelit,
#                      opreste, mentine, elibereaza), cu stapan="web", si Components/HdsMotorStare.py pentru afisaj;
#   - Locul antenei    Components/HdsLocul.py (locul unic al motorului USALS, tabelul tarilor si oraselor, seteaza),
#                      acelasi ca ecranul Screens/HdsLocul.py; pagina /antena/locul. Locul dupa internet:
#                      Components/HdsLoculInternet.py (aceeasi cautare, CAUTARE, ca pe televizor).
# Web-ul adauga numai ce nu are un ecran: alegerea valorilor din formular, verificarea lor si textele paginii.
#
# ADRESELE: cele din data/menu.xml (web="/antena/lnb", "/motor", "/antena/semnal", regula din 19:13: meniul web se
# construieste din menu.xml). /antena ramane pagina din scanare_web.py; /antena/lnb si /antena/semnal duc la paginile
# de aici (PaginaAntena alege dupa restul adresei).
#
# POARTA: resursele API mostenesc HdsJsonResource din plugin.py (reteaua locala, apoi ?token= sau cookie-ul
# browserului asociat; antetul Host e verificat inainte, in _CerereHds.process). Tot ce misca motorul, porneste o
# masurare (acordul poate misca motorul) sau schimba LNB-ul cere POST (GET = 405), numai cu cookie-ul unui browser
# asociat (cu ?token= = 403), din pagina receptorului (Origin egal cu Host) si cu antetul CSRF al paginii. Citirile
# merg cu GET, cu cookie sau cu jeton.
#
# FIRUL ENIGMA2: totul ruleaza pe firul principal (reactorul e chiar bucla enigma2), dar nimic nu asteapta: modulele
# de mai sus isi fac singure asteptarile pe eTimer (proba LNB-ului, alocarea tunerului, mersul motorului). Aici nu e
# niciun sleep, nicio bucla de asteptare si niciun reactor.callLater.
#
# TEXTE: paginile si mesajele scrise aici sunt in romana, ca restul interfetei web. Textele care vin din module (planul,
# proba, verdictul, motivele) trec prin _() acolo, deci vin in limba aleasa pe receptor. Unde pagina spune acelasi lucru
# ca ecranul, se foloseste acelasi text (acelasi msgid), prin _t().
#
# URMA MOTORULUI: nucleul scrie fiecare comanda trimisa motorului, cu cine a
# cerut-o, in /home/root/logs/hds-motor.log (si .1), din lib/dvb/hdsurmamotor.cpp. Aici: GET /api/motor-comenzi?urma=N
# o citeste (numai fisierul, cele mai noi randuri intai, cu o propozitie pentru om), iar inainte de orice comanda din
# web (motorul, Gasire semnal) nucleul afla ca vine din web (eDVBSatelliteEquipmentControl.hdsMotorCerere), ca randul
# sa spuna cine a cerut-o. Ruta e un parametru al lui /api/motor-comenzi: rutele noi s-ar lega si in plugin.py.
#
# Fisierul nu importa nimic din enigma2 la incarcare: plugin.py il incarca la pornire, iar probele de pe PC
# (teste/test_antena_web.py) il pot incarca fara receptor.

import hashlib
import json
import os

# limitele formularului (aceleasi ca in scanare_web.argumente, plus refuzul limpede cand sunt prea multe campuri)
MAX_ARGUMENTE = 60
MAX_TEXT_ARGUMENT = 200

TENSIUNI = ("polarization", "13V", "18V")
TONURI = ("band", "on", "off")
CAMPURI_MANUAL = ("frecventa", "sr", "pol", "sistem", "fec", "mod", "rolloff", "pilot")
ACTIUNI_CU_INTREBARE = {"memoreaza": "memoreaza", "limita_est": "limita_est", "limita_vest": "limita_vest",
	"limite_oprite": "limite_oprite"}
ECRAN_MOTOR = "HdsDishMotorEcran"

# urma comenzilor de motor scrisa de nucleu (lib/dvb/hdsurmamotor.cpp; dosarul se schimba cu HDS_URMA_MOTOR_DIR, la fel
# ca acolo)
DOSAR_URMA_MOTOR = "/home/root/logs"
FISIER_URMA_MOTOR = "hds-motor.log"
URMA_IMPLICIT = 100
URMA_MAX = 500
URMA_CITIRE_MAX = 512 * 1024
# cat ramane valabila cererea anuntata nucleului inainte de o comanda din web (comenzile pleaca dupa tonul oprit, 13 V
# si 500 ms, sau dupa ce se termina secventa nucleului: cel mult cateva secunde)
CERERE_MOTOR_MS = 8000


def N_(text):
	"""Marcaj pentru xgettext (po/Makefile.am, --keyword=N_), fara efect: textele se traduc la folosire, cu _t."""
	return text


COMENZI_URMA = {"oprire": N_("oprire"), "limite_oprite": N_("limitele oprite"),
	"limita_est": N_("limita de est memorată"), "limita_vest": N_("limita de vest memorată"),
	"mers_est": N_("mers spre est"), "mers_vest": N_("mers spre vest"), "limite_pornite": N_("limitele pornite"),
	"memoreaza_pozitia": N_("poziția memorată"), "mergi_la_pozitia": N_("mergi la poziția memorată"),
	"mergi_la_unghi": N_("mergi la unghiul"), "recalculeaza_pozitiile": N_("pozițiile recalculate"),
	"alta_comanda": N_("altă comandă")}

MESAJ_DOAR_BROWSER = N_("Comenzile acestea se dau numai din pagina receptorului, dintr-un browser conectat cu codul "
	"de pe televizor.")


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi daca nu exista (pe PC)."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _jurnal(text):
	print("[HdsWebControl] antena: %s" % text)


def _plugin():
	from . import plugin
	return plugin


def _sesiune():
	"""Sesiunea enigma2 tinuta de plugin.py (porneste(), la WHERE_SESSIONSTART)."""
	try:
		return getattr(_plugin(), "_sesiune", None)
	except Exception:
		return None


def _int(text, minim=None, maxim=None):
	try:
		n = int(str(text).strip())
	except (TypeError, ValueError):
		return None
	if (minim is not None and n < minim) or (maxim is not None and n > maxim):
		return None
	return n


def _dialoguri(sesiune):
	deschise = []
	if sesiune is None:
		return deschise
	curent = getattr(sesiune, "current_dialog", None)
	if curent is not None:
		deschise.append(curent)
	for x in getattr(sesiune, "dialog_stack", None) or []:
		deschise.append(x[0] if isinstance(x, tuple) else x)
	return deschise


def _ecranDeschis(nume_clasa):
	"""True daca pe televizor e deschis ecranul cu clasa data (in fata sau sub alte ferestre)."""
	for d in _dialoguri(_sesiune()):
		if d.__class__.__name__ == nume_clasa:
			return True
	return False


def argumente(request):
	"""Argumentele cererii (adresa si corpul formularului): (dict cheie -> text, eroare). Numai chei scurte din litere
	mici, cifre si _ (fara „token”); prea multe chei = refuz limpede, nu taiere pe tacute."""
	brute = getattr(request, "args", None) or {}
	if len(brute) > MAX_ARGUMENTE + 1:
		return {}, _t("Cererea are prea multe câmpuri.")
	rez = {}
	for cheie, valori in brute.items():
		if isinstance(cheie, bytes):
			cheie = cheie.decode("utf-8", "replace")
		if cheie == "token" or not cheie or len(cheie) > 40 or not all(c.islower() or c.isdigit() or c == "_" for c in cheie):
			continue
		v = (valori or [""])[0]
		if isinstance(v, bytes):
			v = v.decode("utf-8", "replace")
		rez[cheie] = str(v)[:MAX_TEXT_ARGUMENT].strip()
	return rez, None


# ================================================================== Configurare LNB
def _lnb():
	from Components import HdsLnb, HdsLnbAplicare
	return HdsLnb, HdsLnbAplicare


def _nm():
	from Components.NimManager import nimmanager
	return nimmanager


def _voie(model, lnb):
	"""Ce se poate schimba pe LNB-ul dat: exact randurile pe care le arata ecranul (ConfigLNB._construieste). In modul
	simplu se schimba numai tipul (si comenzile la 13 V, pe tot tunerul)."""
	if not model.get("editabil"):
		return {"tip": False, "rest": False, "port": False}
	simplu = model.get("mod") == "simple"
	return {"tip": bool(lnb.get("editabil_tip")), "rest": bool(lnb.get("editabil_rest")) and not simplu,
		"port": bool(lnb.get("editabil_port")) and not simplu}


def _alegeriTensiune(L, lnb):
	valori = list(TENSIUNI) + ([L.DIFERA] if lnb.get("tensiune") == L.DIFERA else [])
	return [[v, L.textTensiune(v)] for v in valori]


def _alegeriTon(L, lnb):
	valori = list(TONURI) + ([L.DIFERA] if lnb.get("ton") == L.DIFERA else [])
	return [[v, L.textTon(v)] for v in valori]


def _alegeriPort(L, lnb):
	alegeri = [[v, t] for v, t in L.alegeriPort()]
	if lnb.get("comanda") not in [a[0] for a in alegeri]:
		alegeri.append([lnb.get("comanda"), L.textPort(lnb.get("comanda"))])
	return alegeri


def _ajutorLnb():
	"""Aceleasi texte de ajutor ca pe televizor (Screens/ConfigLNB.py, _ajutor), deci aceleasi traduceri."""
	return {
		"tip": _t("Universal: aproape toate antenele Ku din România. Un oscilator: LNB vechi cu o singură frecvență. "
			"Banda C: antenele mari de bandă C. Personalizat: scrie valorile de pe eticheta LNB-ului."),
		"tip_simplu": _t("În modul simplu, receptorul lucrează numai cu LNB universal. Dacă alegi alt tip, tunerul "
			"trece în modul avansat, cu aceiași sateliți și același motor. Vezi tot ce se schimbă înainte de salvare."),
		"lof": _t("Frecvența oscilatorului local, scrisă pe LNB, în MHz."),
		"prag": _t("Peste această frecvență, receptorul folosește oscilatorul de sus și pornește tonul de 22 kHz."),
		"tensiune": _t("13 V alege polarizarea verticală, 18 V pe cea orizontală. Lasă „după polarizare”, în afară de "
			"cazul în care un comutator cere altceva."),
		"ton": _t("Tonul de 22 kHz alege banda de sus la LNB-ul universal sau ieșirea unui comutator de 22 kHz."),
		"tensiune_marita": _t("Ridică puțin tensiunea spre LNB, pentru cabluri lungi. Cât anume, hotărăște placa tunerului."),
		"port": _t("Portul comutatorului DiSEqC la care e legat acest LNB."),
		"diseqc13V": _t("Trimite comenzile DiSEqC la 13 V. Unele comutatoare și motoare o cer."),
		"proba": _t("Ce face receptorul pentru un transponder de pe acest satelit: frecvența intermediară, tensiunea "
			"și tonul."),
		"unicable": _t("LNB-ul Unicable se configurează din Setări tuner."),
		"fix": _t("Comutatorul, sateliții și motorul se schimbă din Setări tuner."),
	}


def stareAplicare():
	"""Starea aplicarii (HdsLnbAplicare.stare()) plus ce arata intrebarea de pe televizor: rezultatul probei si
	alegerea implicita (pe „Da” numai cu semnal prins)."""
	_L, A = _lnb()
	st = dict(A.stare())
	faza = st.get("faza")
	st["text_proba"] = A.APLICARE.textProba() if faza != A.LIBER else ""
	st["da_implicit"] = bool(A.APLICARE.raspunsImplicit()) if faza == A.CONFIRMARE else False
	st["din_web"] = st.get("de_unde") == "web"
	slot = st.get("slot", -1)
	st["litera"] = chr(ord("A") + slot) if isinstance(slot, int) and slot >= 0 else ""
	return st


def lnbDate(slot=None):
	"""GET /api/lnb[?slot=N]: tunerele de satelit, LNB-urile tunerului ales cu valorile, alegerile si „Probă de calcul”
	ale fiecaruia, plus starea aplicarii. Numai citire."""
	L, A = _lnb()
	rez = {"result": True, "tunere": [], "slot": -1, "model": None, "lnburi": [], "aplicare": stareAplicare(),
		"copie": False, "ocupat": "", "mesaj": "", "ajutor": _ajutorLnb(),
		"secunde_confirmare": A.SECUNDE_CONFIRMARE,
		"tipuri": {"personalizat": L.TIP_PERSONALIZAT, "universal": L.TIP_UNIVERSAL}}
	tunere = list(L.tunereSatelit())
	if not tunere:
		rez["mesaj"] = _t("Receptorul nu are niciun tuner de satelit.")
		return rez
	ales = _int(slot)
	if ales not in tunere:
		st = rez["aplicare"]
		ales = st["slot"] if st.get("faza") != A.LIBER and st.get("slot") in tunere else tunere[0]
	model = L.citeste(ales)
	nm = _nm()
	serviciu = A.serviciulCurent()
	rez["slot"] = ales
	rez["tunere"] = [{"slot": s, "text": L.textMod(model) if s == ales else L.numeTuner(s)} for s in tunere]
	rez["model"] = {"slot": ales, "litera": model["litera"], "nume": model["nume"], "mod": model["mod"],
		"simplu": model["mod"] == "simple", "antena": model["antena"], "motiv": model["motiv"],
		"editabil": bool(model["editabil"]), "diseqc13V": bool(model["diseqc13V"]), "amprenta": model["amprenta"],
		"motor": bool(model.get("motor"))}
	for lnb in model["lnburi"]:
		try:
			proba = L.probaDeCalcul(lnb, nm, serviciu, model)
		except Exception as eroare:
			_jurnal("proba de calcul: %s" % eroare)
			proba = ""
		rez["lnburi"].append({
			"id": lnb["id"], "cheie": str(lnb["id"]).lower(), "eticheta": lnb["eticheta"],
			"tip": lnb["tip"], "lofl": lnb["lofl"], "lofh": lnb["lofh"], "prag": lnb["prag"],
			"tensiune": lnb["tensiune"], "ton": lnb["ton"], "tensiune_marita": bool(lnb["tensiune_marita"]),
			"comanda": lnb["comanda"], "tip_text": L.textTip(lnb["tip"]), "tensiune_text": L.textTensiune(lnb["tensiune"]),
			"ton_text": L.textTon(lnb["ton"]), "port_text": L.textDiseqc(lnb), "voie": _voie(model, lnb),
			"alegeri": {"tip": [[t, L.textTip(t)] for t in L.TIPURI_DE_ALES], "tensiune": _alegeriTensiune(L, lnb),
				"ton": _alegeriTon(L, lnb), "comanda": _alegeriPort(L, lnb)},
			"proba": proba,
		})
	try:
		rez["copie"] = bool(A.areCopieDeDinainte(ales))
	except Exception as eroare:
		_jurnal("copia de dinainte: %s" % eroare)
	rez["ocupat"] = A.motivOcupat(_sesiune()) or ""
	return rez


def _alegeriDinCerere(L, model, cerere):
	"""Ciorna din formular: (alegeri, None) sau (None, textul greselii). Pagina trimite numai campurile schimbate, cu
	cheile l_<id>_<camp> (id-ul LNB-ului cu litere mici). Fiecare valoare se verifica fata de alegerile ecranului; un
	camp pe care ecranul nu il lasa schimbat nu se poate schimba nici de aici."""
	alegeri = L.alegeriDinModel(model)
	for lnb in model["lnburi"]:
		prefix = "l_%s_" % str(lnb["id"]).lower()
		voie = _voie(model, lnb)
		a = alegeri["lnb"][lnb["id"]]
		eticheta = lnb["eticheta"]
		cheie = prefix + "tip"
		if cheie in cerere and cerere[cheie] != a["tip"]:
			if not voie["tip"] or cerere[cheie] not in L.TIPURI_DE_ALES:
				return None, _t("%s: tipul LNB-ului nu se poate schimba aici.") % eticheta
			a["tip"] = cerere[cheie]
		if a["tip"] == L.TIP_PERSONALIZAT:
			for camp in ("lofl", "lofh", "prag"):
				cheie = prefix + camp
				if cheie not in cerere:
					continue
				n = _int(cerere[cheie], 0, L.PRAG_MEREU_JOS)
				if n is None:
					return None, _t("%s: frecvențele se scriu în MHz, ca număr între 0 și %d.") % (eticheta,
						L.PRAG_MEREU_JOS)
				a[camp] = n
		for camp, permise in (("tensiune", [v for v, _x in _alegeriTensiune(L, lnb)]),
				("ton", [v for v, _x in _alegeriTon(L, lnb)]),
				("comanda", [v for v, _x in _alegeriPort(L, lnb)])):
			cheie = prefix + camp
			if cheie not in cerere or cerere[cheie] == a[camp]:
				continue
			if not voie["port" if camp == "comanda" else "rest"] or cerere[cheie] not in permise:
				return None, _t("%s: această valoare nu se poate schimba aici (%s).") % (eticheta, camp)
			a[camp] = cerere[cheie]
		cheie = prefix + "tensiune_marita"
		if cheie in cerere:
			valoare = cerere[cheie] in ("1", "da", "true", "on")
			if valoare != bool(a["tensiune_marita"]):
				if not voie["rest"]:
					return None, _t("%s: tensiunea mărită nu se poate schimba aici.") % eticheta
				a["tensiune_marita"] = valoare
	if "diseqc13v" in cerere:
		alegeri["diseqc13V"] = cerere["diseqc13v"] in ("1", "da", "true", "on")
	return alegeri, None


def _semnPlan(plan):
	"""Semnul planului vazut in previzualizare: aplicarea se face numai daca planul refacut pe server e acelasi."""
	date = {"slot": plan.get("slot"), "fel": plan.get("fel"), "amprenta": plan.get("amprenta"),
		"tinta": [list(x) for x in plan.get("tinta") or []]}
	return hashlib.sha1(json.dumps(date, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()


def _planDinCerere(cerere):
	"""(plan, None) sau (None, motiv). „fel=inainte”: planul lui „Ce era înainte” (HdsLnbAplicare.planCeEraInainte);
	altfel planul ciornei (HdsLnb.planifica), cu aceleasi verificari ca ecranul (ConfigLNB._salveaza)."""
	L, A = _lnb()
	slot = _int(cerere.get("slot"))
	if slot not in list(L.tunereSatelit()):
		return None, _t("Tunerul ales nu mai este printre tunerele de satelit. Reîncarcă pagina.")
	if cerere.get("fel") == "inainte":
		plan = A.planCeEraInainte(slot)
		if plan is None:
			return None, _t("Nu am setări de dinainte pentru acest tuner.")
		return plan, None
	model = L.citeste(slot)
	if not model["editabil"]:
		return None, model["motiv"]
	alegeri, eroare = _alegeriDinCerere(L, model, cerere)
	if eroare:
		return None, eroare
	if not L.areSchimbari(model, alegeri):
		return None, _t("Nu ai schimbat nimic.")
	greseala = L.valideaza(model, alegeri)
	if greseala:
		return None, greseala
	return L.planifica(model, alegeri, _nm(), A.serviciulCurent()), None


def _planPentruWeb(plan):
	L, A = _lnb()
	oprire = plan.get("oprire") or ""
	return {"fel": plan.get("fel", "schimbare"), "slot": plan.get("slot"),
		"titlu": _t("Ce era înainte") if plan.get("fel") == "inainte" else _t("Ce se schimbă"),
		"rezumat": list(plan.get("rezumat") or []), "avertismente": list(plan.get("avertismente") or []),
		"oprire": oprire, "detalii": L.detalii(plan), "trece_in_avansat": bool(plan.get("trece_in_avansat")),
		"nota": "" if oprire else _t("După aplicare verific semnalul pe canalul care rulează, apoi te întreb dacă "
			"păstrezi setările. Dacă nu răspunzi în %d de secunde, revin singur la ce era.") % A.SECUNDE_CONFIRMARE,
		"semn": _semnPlan(plan)}


def lnbProba(cerere):
	"""„Probă de calcul” pentru ciorna din formular, pe fiecare LNB (numai citire, fara plan)."""
	L, A = _lnb()
	slot = _int(cerere.get("slot"))
	if slot not in list(L.tunereSatelit()):
		return {"result": False, "message": _t("Tunerul ales nu mai este printre tunerele de satelit. Reîncarcă "
			"pagina.")}
	model = L.citeste(slot)
	alegeri, eroare = _alegeriDinCerere(L, model, cerere)
	if eroare:
		return {"result": False, "message": eroare}
	nm = _nm()
	serviciu = A.serviciulCurent()
	proba = {}
	for lnb in model["lnburi"]:
		dupa = L.lnbDupaAlegeri(model, alegeri, lnb["id"])
		try:
			proba[str(lnb["id"]).lower()] = L.probaDeCalcul(dupa, nm, serviciu, model)
		except Exception as e:
			_jurnal("proba de calcul: %s" % e)
			proba[str(lnb["id"]).lower()] = ""
	return {"result": True, "proba": proba, "greseala": L.valideaza(model, alegeri) or ""}


def lnbPlan(cerere):
	"""POST /api/lnb-plan: ce s-ar schimba (previzualizarea „Ce se schimbă” sau „Ce era înainte”). Nu scrie nimic.
	Ca pe televizor, previzualizarea nu se deschide cat tunerul e ocupat (motivOcupat)."""
	if cerere.get("doar") == "proba":
		return lnbProba(cerere)
	_L, A = _lnb()
	ocupat = A.motivOcupat(_sesiune())
	if ocupat:
		return {"result": False, "message": ocupat}
	plan, eroare = _planDinCerere(cerere)
	if eroare:
		return {"result": False, "message": eroare}
	return {"result": True, "plan": _planPentruWeb(plan)}


def lnbAplica(cerere):
	"""POST /api/lnb-aplica: planul se reface pe server si se aplica numai daca e acelasi cu cel din previzualizare
	(semnul). Apoi HdsLnbAplicare face ce face si pentru televizor: sec.update(), proba de semnal, intrebarea cu 60 s."""
	_L, A = _lnb()
	ocupat = A.motivOcupat(_sesiune())
	if ocupat:
		return {"result": False, "message": ocupat, "aplicare": stareAplicare()}
	plan, eroare = _planDinCerere(cerere)
	if eroare:
		return {"result": False, "message": eroare, "aplicare": stareAplicare()}
	if plan.get("oprire"):
		return {"result": False, "message": plan["oprire"], "aplicare": stareAplicare()}
	if cerere.get("semn") != _semnPlan(plan):
		return {"result": False, "message": _t("Setările tunerului s-au schimbat între timp. Verifică din nou."),
			"aplicare": stareAplicare()}
	reusit, motiv = A.aplica(plan, "web")
	if reusit:
		_jurnal("schimbare de LNB aplicata din web pe tunerul %s" % chr(ord("A") + int(plan["slot"])))
	return {"result": bool(reusit), "message": motiv or "", "aplicare": stareAplicare()}


def lnbRaspuns(cerere):
	"""POST /api/lnb-raspuns?raspuns=pastrez|revin: raspunsul la „Păstrezi noile setări?” pentru o schimbare pornita
	din web. Una pornita pe televizor se raspunde acolo (acolo e deschisa intrebarea)."""
	_L, A = _lnb()
	st = A.stare()
	raspuns = cerere.get("raspuns")
	if st.get("faza") not in (A.PROBA, A.CONFIRMARE):
		return {"result": False, "message": st.get("mesaj") or _t("Nicio schimbare de LNB nu așteaptă răspuns."),
			"aplicare": stareAplicare()}
	if st.get("de_unde") != "web":
		return {"result": False, "message": _t("Schimbarea a fost pornită de pe televizor. Răspunde acolo."),
			"aplicare": stareAplicare()}
	if raspuns == "pastrez":
		if st.get("faza") != A.CONFIRMARE:
			return {"result": False, "message": _t("Verificarea semnalului nu s-a terminat. Așteaptă întrebarea."),
				"aplicare": stareAplicare()}
		rezultat = A.pastreaza()
	elif raspuns == "revin":
		rezultat = A.revino("om")
	else:
		return {"result": False, "message": _t("Răspuns necunoscut."), "aplicare": stareAplicare()}
	st = stareAplicare()
	return {"result": rezultat is not None, "message": st.get("mesaj") or "", "aplicare": st}


# ================================================================== Găsire semnal
def _gasire():
	from Components import HdsGasireSemnal
	return HdsGasireSemnal


def _serviciuCurent():
	try:
		import NavigationInstance
		nav = NavigationInstance.instance
		return nav.getCurrentService() if nav is not None else None
	except Exception:
		return None


def _tuneriSemnal(G):
	tunere = []
	for t in G.tunere():
		sateliti = [{"poz": s["poz"], "nume": s["nume"], "vizibil": bool(s.get("vizibil", True)),
			"text": G.text_satelit(s)} for s in t["sateliti"]]
		tunere.append({"slot": t["slot"], "nume": t["nume"], "s2": bool(t["s2"]), "motor": bool(t["motor"]),
			"sateliti": sateliti})
	return tunere


def _listaTranspondere(G, tuner, poz, tp=None):
	lista, sarite = G.transpondere(poz, tuner["s2"])
	ales = G.potriveste(tp, lista) if tp is not None else (0 if lista else -1)
	text_sarite = ""
	if sarite:
		try:
			# acelasi text ca pe televizor (cu „de” de la 20 in sus), scris o singura data in modul
			text_sarite = G._text_sarite(sarite)
		except Exception as eroare:
			_jurnal("textul transponderelor sarite: %s" % eroare)
	return {"transpondere": [{"text": G.text_transponder(e["tp"]), "tp": e["tp"], "tsid": e["tsid"], "onid": e["onid"]}
		for e in lista], "sarite": sarite, "text_sarite": text_sarite, "ales": ales}


def semnalStare(tine_viu=True):
	"""Starea masurarii (Masurare.stare(), acelasi dictionar ca pe televizor). Cererea de stare a paginii tine
	masurarea web-ului pornita (tine_viu); fara cereri 30 s, modulul o opreste singur si pune programul la loc."""
	m = _gasire().masurare()
	if tine_viu and m.cine == "web" and not m.ecran_deschis:
		m.tine_viu()
	s = dict(m.stare())
	s["ecran_deschis"] = bool(m.ecran_deschis)
	s["result"] = True
	return s


def semnalDate():
	"""GET /api/gasire-semnal: tunerele de satelit cu satelitii lor, transponderul de la care porneste pagina (al
	masurarii care merge, altfel al programului de pe ecran, ca pe televizor), listele pentru transponderul batut de
	mana si starea masurarii. Numai citire: deschiderea paginii nu opreste nimic."""
	G = _gasire()
	m = G.masurare()
	tunere = _tuneriSemnal(G)
	initial = None
	if m.slot is not None and m.slot >= 0 and m.tp is not None and m.faza not in ("oprita", "fara_tuner", "fara_sateliti"):
		initial = {"slot": m.slot, "tp": dict(m.tp), "din": "masurare"}
	else:
		serviciu = _serviciuCurent()
		for t in tunere:
			try:
				tp = G.transponder_din_serviciu(serviciu, [s["poz"] for s in t["sateliti"]])
			except Exception as eroare:
				_jurnal("transponderul programului: %s" % eroare)
				tp = None
			if tp is not None:
				initial = {"slot": t["slot"], "tp": tp, "din": "program"}
				break
		if initial is None and m.slot is not None and m.slot >= 0 and m.tp is not None:
			initial = {"slot": m.slot, "tp": dict(m.tp), "din": "masurare"}
	if initial is not None:
		tuner = [t for t in tunere if t["slot"] == initial["slot"]]
		if tuner and initial["tp"].get("orbital_position") in [s["poz"] for s in tuner[0]["sateliti"]]:
			initial.update(_listaTranspondere(G, tuner[0], initial["tp"]["orbital_position"], initial["tp"]))
		else:
			initial = None
	liste = {"polarizari": G.polarizari(), "sisteme": G.sisteme(True), "fec_dvbs": G.fec_dvbs(),
		"fec_dvbs2": G.fec_dvbs2(), "modulatii": G.modulatii_dvbs2(), "rolloffuri": G.rolloffuri(), "piloti": G.piloti()}
	return {"result": True, "tunere": tunere, "initial": initial, "liste": liste, "stare": semnalStare(False),
		"sistem_s2": G.SISTEM_DVB_S2}


def _tunerSemnal(G, slot):
	for t in _tuneriSemnal(G):
		if t["slot"] == slot:
			return t
	return None


def semnalTranspondere(cerere):
	"""GET /api/gasire-semnal-transpondere?slot=&poz=: transponderele pe care tunerul le poate acorda pe satelit."""
	G = _gasire()
	t = _tunerSemnal(G, _int(cerere.get("slot")))
	if t is None:
		return {"result": False, "message": _t("Tunerul ales nu mai este printre tunerele de satelit. Reîncarcă "
			"pagina.")}
	poz = _int(cerere.get("poz"))
	if poz not in [s["poz"] for s in t["sateliti"]]:
		return {"result": False, "message": _t("Satelitul ales nu este în setările acestui tuner.")}
	rez = _listaTranspondere(G, t, poz)
	rez["result"] = True
	return rez


def semnalPorneste(cerere):
	"""POST /api/gasire-semnal-porneste: masoara transponderul ales (tp=<numarul din lista>) sau pe cel batut de mana
	(tp=manual, cu campurile lui), exact cum e ales. Daca masurarea web-ului merge pe acelasi tuner, schimba
	transponderul (Masurare.schimba); altfel o porneste (Masurare.porneste). Cat e deschis ecranul pe televizor,
	modulul refuza cu motivul lui."""
	G = _gasire()
	m = G.masurare()
	slot = _int(cerere.get("slot"))
	t = _tunerSemnal(G, slot)
	_anuntaMotor("web: gasire semnal")
	if t is None:
		return {"result": False, "message": _t("Tunerul ales nu mai este printre tunerele de satelit. Reîncarcă "
			"pagina."),
			"stare": semnalStare(False)}
	poz = _int(cerere.get("poz"))
	if poz not in [s["poz"] for s in t["sateliti"]]:
		return {"result": False, "message": _t("Satelitul ales nu este în setările acestui tuner."),
			"stare": semnalStare(False)}
	lista, sarite = G.transpondere(poz, t["s2"])
	ales = cerere.get("tp", "")
	if ales not in ("", "manual"):
		i = _int(ales, 0, len(lista) - 1)
		if i is None:
			return {"result": False, "message": _t("Lista transponderelor s-a schimbat. Alege din nou."),
				"stare": semnalStare(False)}
		e = lista[i]
		tp = e["tp"]
		extra = {"tsid": e["tsid"], "onid": e["onid"], "sarite": sarite, "fara_lista": False}
	else:
		valori = dict((k, cerere.get(k)) for k in CAMPURI_MANUAL)
		tp, eroare = G.transponder_din_campuri(valori, poz, t["s2"])
		if eroare:
			reusit, text = m.arata_refuz(eroare, slot, cine="web")
			return {"result": False, "message": eroare if reusit else text, "stare": semnalStare(False)}
		extra = {"tsid": -1, "onid": -1, "sarite": sarite, "fara_lista": not lista}
	# acelasi tuner = tunerul tinut chiar pe slotul cerut, nu numai slotul aratat (dupa un refuz pe alt slot, m.slot e
	# cel nou, iar tunerul poate fi inca al celui vechi; verificarea finala, Mediu 1)
	if m.cine == "web" and m.slot == slot and m.tuner.slot == slot and (m.tuner.are_tuner() or m.tuner.asteapta()):
		if m.tp == tp and m.faza not in ("oprita", "refuzat"):
			return {"result": True, "message": "", "stare": semnalStare()}
		reusit, text = m.schimba(tp, extra, cine="web")
	else:
		reusit, text = m.porneste(slot, tp, "web", _sesiune(), extra, t["s2"])
	return {"result": bool(reusit), "message": text or "", "stare": semnalStare()}


def semnalReacordeaza(cerere):
	"""POST /api/gasire-semnal-reacordeaza: acelasi transponder, din nou (tasta galbena de pe televizor)."""
	_anuntaMotor("web: gasire semnal, reacordare")
	reusit, text = _gasire().masurare().reacordeaza(cine="web")
	return {"result": bool(reusit), "message": text or "", "stare": semnalStare()}


def semnalOpreste(cerere):
	"""POST /api/gasire-semnal-opreste: da tunerul inapoi si porneste programul oprit de masurare. Numai pentru
	masurarea web-ului: cea de pe televizor se opreste de acolo."""
	m = _gasire().masurare()
	if m.cine != "web":
		return {"result": True, "message": "", "stare": semnalStare(False)}
	reusit, text = m.opreste(True, cine="web")
	return {"result": bool(reusit), "message": text or "", "stare": semnalStare(False)}


# ================================================================== Rotirea antenei: comenzile
def _motor():
	from Components import HdsMotorComenzi, HdsMotorTuner
	return HdsMotorComenzi, HdsMotorTuner


def motorDate(cerere=None):
	"""GET /api/motor-comenzi[?slot=N]: ce trebuie paginii ca sa dea comenzi: de ce nu se poate (daca e cazul),
	tunerele cu motor, satelitii pentru „Mergi la satelit” (ca lista de pe televizor), locul USALS, starea comenzilor."""
	C, T = _motor()
	c = C.comenzi()
	slot = _int((cerere or {}).get("slot"))
	if slot is not None and c.tuner is None:
		c.alegeSlot(slot)
	d = C.stareComenzi()
	slot = d.get("slot", -1)
	rez = {"result": True, "motiv": c.motivIndisponibil() or "", "tunere": [], "slot": slot, "sateliti": [],
		"curent": None, "usals": "", "pasi": list(C.PASI), "comenzi": d, "ecran_deschis": _ecranDeschis(ECRAN_MOTOR)}
	rez["tunere"] = [{"slot": s, "nume": _t("Tunerul %s") % n} for s, n in T.tunereCuMotor()]
	if slot is not None and slot >= 0:
		from Components.HdsMotorStare import gradeText
		from Components.DishMath import orbitalToDegrees
		rez["sateliti"] = [{"orbital": o, "text": "%s (%s)" % (nume, gradeText(orbitalToDegrees(o)))}
			for o, nume in T.sateliti(slot)]
		L = _locul()
		if L.stabilit():
			rez["usals"] = _t("Locul antenei: %s") % L.textLoc()
		# „Mergi la satelit" cere locul antenei pe acest tuner (USALS) si locul nu e stabilit
		rez["loc_nestabilit"] = bool(L.refuzUsals(slot))
	rez["locul"] = _locul().stare()
	if c.referinta:
		rez["curent"] = c.referinta.get("orbital_position")
	elif c.pozitie_stiuta is not None:
		rez["curent"] = c.pozitie_stiuta
	return rez


def motorComanda(cerere):
	"""POST /api/motor-comanda?actiune=...: o comanda a motorului, prin aceleasi functii ca tastele ecranului, cu
	stapan="web". Cat se misca motorul, orice comanda doar il opreste (regula modulului). Comenzile care suprascriu
	ceva (memorarea, limitele) intorc intai intrebarea (aceeasi ca pe televizor), iar pagina le trimite din nou cu
	confirmat=1."""
	C, _T = _motor()
	c = C.comenzi()
	actiune = cerere.get("actiune", "")
	_anuntaMotor("web: motor %s" % actiune[:30])
	slot = _int(cerere.get("slot"))
	if slot is not None and c.tuner is None:
		c.alegeSlot(slot)
	rez = {"result": False, "message": "", "intrebare": "", "actiune": actiune}
	if actiune == "mentine":
		ok, text = c.mentine("web")
	elif actiune == "opreste":
		ok, text = c.opreste("web")
	elif actiune == "elibereaza":
		ok, text = c.elibereaza("web")
		if not ok and c.stapan == "ecran":
			text = _t("Tunerul e ținut de ecranul „Rotirea antenei” de pe televizor. Se dă înapoi când ieși de acolo.")
	elif actiune == "marime":
		ok, text = c.marimePas(1 if cerere.get("delta") == "1" else -1)
	else:
		motiv = c.motivIndisponibil()
		if motiv:
			ok, text = False, motiv
		elif actiune in ("pas", "continuu"):
			est = cerere.get("est") == "1"
			ok, text = c.pas(est, "web") if actiune == "pas" else c.continuu(est, "web")
		elif actiune == "la_pozitie":
			ok, text = c.laPozitie(cerere.get("pozitie"), "web")
		elif actiune == "la_referinta":
			ok, text = c.laReferinta("web")
		elif actiune == "la_satelit":
			ok, text = c.laSatelit(cerere.get("orbital"), "web")
		elif actiune == "limite_pornite":
			ok, text = c.limitePornite("web")
		elif actiune in ACTIUNI_CU_INTREBARE:
			confirmat = cerere.get("confirmat") == "1"
			if actiune == "memoreaza":
				ok, text = c.memoreaza(cerere.get("pozitie"), confirmat, "web")
			elif actiune == "limita_est":
				ok, text = c.limitaEst(confirmat, "web")
			elif actiune == "limita_vest":
				ok, text = c.limitaVest(confirmat, "web")
			else:
				ok, text = c.limiteOprite(confirmat, "web")
			if not ok and not confirmat and text and text == _intrebareMotor(c, actiune, cerere.get("pozitie")):
				# modulul a intors intrebarea, nu un refuz: pagina o arata si trimite din nou cu confirmat=1
				rez["intrebare"] = text
				text = ""
		else:
			ok, text = False, _t("Comandă necunoscută.")
	rez["result"] = bool(ok)
	rez["message"] = text or ""
	rez["comenzi"] = C.stareComenzi()
	return rez


def _anuntaMotor(text):
	"""Spune nucleului cine cere urmatoarele comenzi de motor (intra in urma, hds-motor.log), valabil CERERE_MOTOR_MS.
	Pe PC sau pe o imagine fara urma nu face nimic."""
	try:
		from enigma import eDVBSatelliteEquipmentControl
		sec = eDVBSatelliteEquipmentControl.getInstance()
		anunta = getattr(sec, "hdsMotorCerere", None) if sec is not None else None
		if anunta is not None:
			anunta(str(text)[:90], CERERE_MOTOR_MS)
	except Exception:
		pass


def _dosarUrma():
	return os.environ.get("HDS_URMA_MOTOR_DIR") or DOSAR_URMA_MOTOR


def _pozitieUrma(orbital):
	"""pozitia din urma (zecimi de grad, 3600 - x pentru vest, -1 necunoscuta) ca text, de exemplu 19,2 grade Est"""
	try:
		o = int(orbital)
	except (TypeError, ValueError):
		return ""
	if o < 0:
		return _t("necunoscută")
	v = o % 3600
	est = v <= 1800
	grade = v / 10.0 if est else (3600 - v) / 10.0
	return _t("%s grade %s") % (("%.1f" % grade).replace(".", ","), _t("Est") if est else _t("Vest"))


def _textUrma(r):
	"""o propozitie pentru om dintr-un rand al urmei"""
	ev = r.get("eveniment")
	ora = str(r.get("ora", ""))
	cine = str(r.get("motiv") or "")
	if r.get("cerere"):
		cine += "; cerere: %s" % r.get("cerere")
	if ev == "comanda":
		ce = _t(COMENZI_URMA[r.get("comanda")]) if r.get("comanda") in COMENZI_URMA else str(r.get("comanda", ""))
		if "unghi" in r:
			try:
				u = float(r["unghi"])
				ce += " %s" % (_t("%s grade %s") % (("%.1f" % abs(u)).replace(".", ","), _t("Est") if u >= 0 else _t("Vest")))
			except (TypeError, ValueError):
				pass
		if "pozitia" in r:
			ce += " %s" % r["pozitia"]
		if "pasi" in r:
			ce += _t(", %s pași") % r["pasi"]
		elif "secunde" in r:
			ce += _t(", cel mult %s s") % r["secunde"]
		elif r.get("fara_oprire"):
			ce += _t(", fără oprire")
		cale = "din acordare" if r.get("cale") == "acordare" else _t("comandă directă")
		text = "%s, tunerul %s: %s (%s; %s)" % (ora, r.get("tuner"), ce, cale, cine)
		if r.get("rezultat"):
			text += "; driverul a refuzat-o (%s)" % r.get("rezultat")
		if "sat" in r and r.get("cale") == "acordare":
			text += "; spre %s" % _pozitieUrma(r.get("sat"))
		text += _t("; antena crezută pe %s") % _pozitieUrma(r.get("crezuta", -1))
		if "tensiune_rotire" in r:
			text += _textTensiuneComanda(r)
	elif ev == "tensiune_rotire":
		text = _textTensiuneRotire(r, ora, cine)
	elif ev == "proba_semnal":
		text = _textProbaSemnal(r, ora, cine)
	elif ev == "goto_omis":
		text = _t("%s, tunerul %s: acordare pe %s fără nicio comandă spre motor, nucleul credea antena deja acolo "
			"(%s)") % (
			ora, r.get("tuner"), _pozitieUrma(r.get("sat", -1)), cine)
		if r.get("omise"):
			text += _t("; încă %s la fel nescrise") % r.get("omise")
	elif ev == "pozitie_crezuta":
		text = _t("%s, tunerul %s: poziția crezută de nucleu schimbată din %s în %s (%s)") % (ora, r.get("tuner"),
			_pozitieUrma(r.get("crezuta", -1)), _pozitieUrma(r.get("spre", -1)), cine)
	elif ev == "readucere":
		text = _textReaducere(r, ora, cine)
	else:
		text = "%s: %s" % (ora, ev)
	if r.get("tp"):
		text += "; transponderul %s" % r.get("tp")
	if r.get("pierdute"):
		text += _t("; %s rânduri pierdute înainte") % r.get("pierdute")
	return text


def _durataUrma(ms):
	"""milisecundele din urma ca text scurt: 12,4 s, 1 min 5 s"""
	try:
		ms = int(ms)
	except (TypeError, ValueError):
		return "?"
	if ms < 60000:
		return ("%.1f s" % (ms / 1000.0)).replace(".", ",")
	s = int(round(ms / 1000.0))
	return "%d min %d s" % (s // 60, s % 60)


_PLECARE_URMA = {"stiuta": N_("de la poziția știută"), "zona": N_("de undeva de pe drumul mutării oprite înainte"),
	"necunoscuta": N_("de la o poziție necunoscută, deci cel mai lung drum posibil")}


def _textTensiuneComanda(r):
	"""campurile rotirii pe 18 V din randul comenzii de motor (lib/dvb/hdsrotire.h)"""
	try:
		grade = ("%.1f" % float(r.get("rotire_grade", 0))).replace(".", ",")
	except (TypeError, ValueError):
		grade = "?"
	plecare = _t(_PLECARE_URMA.get(r.get("plecare"), ""))
	if r.get("tensiune_rotire") != 18:
		return _t("; motorul pe 13 V (mutare de 0 grade)")
	text = _t("; motorul pe 18 V, %s grade %s") % (grade, plecare)
	if r.get("tensiune_tinta") == 18:
		return text + _t("; transponderul e tot pe 18 V")
	text += _t("; 18 V ținut %s, apoi 13 V pentru transponder") % _durataUrma(r.get("rotire_plan_ms"))
	return text + _t(_PROBA_URMA.get(r.get("proba"), ""))


# proba de semnal dinaintea comenzii (lib/dvb/hdsrotire.h), in randul comenzii de motor
_PROBA_URMA = {"fara_semnal": N_("; înainte, cu antena pe loc, transponderul nu a dat semnal"),
	"geaman": N_("; fără încercarea cu antena pe loc: transponderul are un geamăn pe alt satelit al motorului"),
	"fara_lista": N_("; fără încercarea cu antena pe loc: lista transponderelor nu era încă în receptor")}


def _textProbaSemnal(r, ora, cine):
	"""randul "proba_semnal": semnalul tintei incercat cu antena pe loc, inaintea comenzii de motor"""
	inceput = "%s, tunerul %s: " % (ora, r.get("tuner"))
	unde = _pozitieUrma(r.get("sat", -1))
	if r.get("faza") == "prinsa":
		return inceput + _t("semnal prins cu antena pe loc în %s, deci fără nicio comandă spre motor: antena era deja "
			"pe %s (%s)") % (
			_durataUrma(r.get("durata_ms")), unde, cine)
	if r.get("faza") == "fara_semnal":
		return inceput + _t("cu antena pe loc nu a venit semnal în %s, urmează comanda spre %s (%s)") % (
			_durataUrma(r.get("durata_ms")), unde, cine)
	return inceput + _t("încercarea semnalului cu antena pe loc: %s") % r.get("faza")


def _textTensiuneRotire(r, ora, cine):
	"""randul "tensiune_rotire": capatul tinerii pe 18 V sau mersul oprit in timpul ei"""
	inceput = "%s, tunerul %s: " % (ora, r.get("tuner"))
	unde = _pozitieUrma(r.get("sat", -1))
	if r.get("faza") == "gata":
		return inceput + "motorul a mers pe 18 V %s spre %s (estimat %s), acum tensiunea transponderului (%s)" % (
			_durataUrma(r.get("tinut_ms")), unde, _durataUrma(r.get("plan_ms")), cine)
	if r.get("faza") == "intrerupta":
		return inceput + _t("mersul spre %s oprit după %s pe 18 V din %s estimate (%s)") % (unde,
			_durataUrma(r.get("tinut_ms")), _durataUrma(r.get("plan_ms")), cine)
	return inceput + "tensiunea motorului: %s" % r.get("faza")


def _textReaducere(r, ora, cine):
	"""randul "readucere" (Components/HdsMotorPozitie.py)"""
	faza = r.get("faza")
	inc = r.get("incercare")
	unde = _pozitieUrma(r.get("sat", -1))
	inceput = "%s, tunerul %s: " % (ora, r.get("tuner"))
	if faza == "pornita":
		text = _t("readucerea antenei spre %s, încercarea %s, după %s fără semnal (%s)") % (unde, inc,
			_durataUrma(r.get("fara_semnal_ms")), cine)
	elif faza == "semnal_revenit":
		text = _t("semnalul a revenit pe %s la %s după readucere (încercarea %s)") % (unde,
			_durataUrma(r.get("dupa_ms")), inc)
		if r.get("mers_ms") is not None:
			text += "; motorul a mers %s" % _durataUrma(r.get("mers_ms"))
	elif faza == "fara_semnal":
		text = _t("tot fără semnal pe %s după readucere (încercarea %s, %s)") % (unde, inc,
			_durataUrma(r.get("dupa_ms")))
		if r.get("mers_ms") is not None:
			text += "; motorul a mers %s" % _durataUrma(r.get("mers_ms"))
		if r.get("urmatoarea_s") is not None:
			text += _t("; următoarea încercare peste %s") % _durataUrma(int(r.get("urmatoarea_s")) * 1000)
	elif faza == "incheiata":
		cate = _t("o încercare") if inc == 1 else _t("%s încercări") % inc
		text = _t("readucerea spre %s s-a încheiat fără semnal, după %s (alt satelit, standby sau tunerul luat)") % (
			unde, cate)
	elif faza == "refuzata":
		text = "readucerea spre %s nu a pornit (codul nucleului %s)" % (unde, r.get("cod", 0))
	elif faza == "ocolire":
		text = _t("readucerea antenei spre %s prin altă poziție, încercarea %s, după %s fără semnal (%s)") % (unde, inc,
			_durataUrma(r.get("fara_semnal_ms")), cine)
	elif faza in ("ocolire_semnal", "ocolire_fara_semnal"):
		acolo = _t("semnal pe poziția ocolirii") if faza == "ocolire_semnal" else _t("drumul ocolirii s-a încheiat "
			"fără semnal acolo")
		text = _t("%s după %s; acum înapoi spre %s (încercarea %s; %s)") % (acolo, _durataUrma(r.get("dupa_ms")), unde,
			inc,
			cine)
		if r.get("mers_ms") is not None:
			text += "; motorul a mers %s" % _durataUrma(r.get("mers_ms"))
	elif faza == "ocolire_refuzata":
		text = _t("ocolirea pentru %s nu a pornit (codul %s); încercarea %s merge direct (%s)") % (unde, r.get("cod",
			0), inc,
			cine)
	elif faza == "ocolire_oprita":
		text = _t("ocolirea pentru %s s-a oprit după %s (încercarea %s; %s)") % (unde, _durataUrma(r.get("dupa_ms")),
			inc,
			cine)
	elif faza == "verificare":
		text = (_t("verificarea %s pe alt transponder al satelitului %s, fără comandă spre motor, după %s fără semnal "
			"(%s)")
			% (inc, unde, _durataUrma(r.get("fara_semnal_ms")), cine))
	elif faza == "verificare_prins":
		text = (_t("verificarea %s a recepționat alt transponder al satelitului %s după %s: antena e la locul ei, "
			"nicio rotire; "
			"transponderul canalului nu emite acum (%s)") % (inc, unde, _durataUrma(r.get("dupa_ms")), cine))
	elif faza == "verificare_fara_semnal":
		text = (_t("verificarea %s: niciun transponder al satelitului %s nu se recepționează după %s, deci antena nu e "
			"acolo; "
			"urmează comanda spre motor (%s)") % (inc, unde, _durataUrma(r.get("dupa_ms")), cine))
	elif faza == "verificare_refuzata":
		text = _t("verificarea %s pentru %s nu a pornit (codul %s); readucerea merge ca înainte (%s)") % (inc, unde,
			r.get("cod", 0), cine)
	elif faza == "verificare_oprita":
		text = _t("verificarea %s pentru %s s-a oprit după %s (%s)") % (inc, unde, _durataUrma(r.get("dupa_ms")), cine)
	elif faza == "verificare_zap":
		text = (_t("verificarea %s pentru %s merge mai departe după un zap pe același satelit, la %s de la pornire; "
			"canalul ales pornește la capătul ei (%s)") % (inc, unde, _durataUrma(r.get("dupa_ms")), cine))
	else:
		text = "readucerea antenei: %s" % faza
	return inceput + text


def motorUrma(cerere=None):
	"""GET /api/motor-comenzi?urma=N: ultimele N randuri (implicit URMA_IMPLICIT, cel mult URMA_MAX) din urma comenzilor
	de motor, cele mai noi intai, fiecare cu o propozitie pentru om in "text". Numai citire de fisier, cel mult
	URMA_CITIRE_MAX octeti de la capatul fiecaruia; un rand stricat se numara in "nevalide" si se sare."""
	n = _int((cerere or {}).get("urma"), 1, URMA_MAX) or URMA_IMPLICIT
	cale = os.path.join(_dosarUrma(), FISIER_URMA_MOTOR)
	lista, nevalide, exista = [], 0, False
	for c in (cale + ".1", cale):
		try:
			with open(c, "rb") as f:
				f.seek(0, 2)
				marime = f.tell()
				f.seek(max(0, marime - URMA_CITIRE_MAX))
				date = f.read()
		except (IOError, OSError):
			continue
		exista = True
		linii = date.split(b"\n")
		if marime > URMA_CITIRE_MAX:
			linii = linii[1:]    # primul rand poate fi taiat de citirea de la capat
		for linie in linii:
			linie = linie.strip()
			if not linie:
				continue
			try:
				r = json.loads(linie.decode("utf-8", "replace"))
			except ValueError:
				r = None
			if isinstance(r, dict) and "eveniment" in r:
				lista.append(r)
			else:
				nevalide += 1
	lista = lista[-n:]
	lista.reverse()
	for r in lista:
		r["text"] = _textUrma(r)
	return {"result": True, "fisier": cale, "exista": exista, "randuri": lista, "nevalide": nevalide,
		"pierdute": sum(_int(r.get("pierdute"), 0) or 0 for r in lista)}


def _intrebareMotor(c, actiune, pozitie):
	try:
		return c.confirmare(ACTIUNI_CU_INTREBARE[actiune], int(pozitie) if actiune == "memoreaza" else None)
	except (TypeError, ValueError):
		return None


# ================================================================== Locul antenei
def _locul():
	from Components import HdsLocul
	return HdsLocul


def _grade(text, maxim):
	"""„44,426" sau „-8.61" -> float in [-maxim, maxim], altfel None"""
	try:
		x = float(str(text).strip().replace(",", "."))
	except (TypeError, ValueError):
		return None
	if x != x or not -maxim <= x <= maxim:
		return None
	return x


MESAJ_COORDONATE = N_("Latitudinea se scrie între -90 și 90, longitudinea între -180 și 180 (grade, cu virgulă sau "
	"punct).")


def _loculInternet():
	from Components import HdsLoculInternet
	return HdsLoculInternet


def _stareInternet():
	"""starea cautarii dupa internet (aceeasi ca pe televizor) si daca receptorul are ruta spre internet (citita
	local, fara nicio conexiune)"""
	I = _loculInternet()
	st = I.CAUTARE.stare()
	st["retea"] = bool(I.retea())
	return st


def loculDate(cerere=None):
	"""GET /api/locul[?tara=RO]: locul de acum, tarile si (cu tara=) orasele tarii, din tabelul din imagine (nicio
	cerere pe internet), plus starea cautarii dupa internet (internet.retea spune daca pagina arata optiunea)"""
	L = _locul()
	tari = L.tari()
	rez = {"result": True, "locul": L.stare(), "tari": [[cod, nume] for cod, nume in tari], "sursa_date": L.ATRIBUIRE}
	rez["sursa_text"] = _t(_loculInternet().NOTA_SURSA) % L.ATRIBUIRE
	rez["internet"] = _stareInternet()
	tara = (cerere or {}).get("tara", "")
	if tara:
		if tara not in dict(tari):
			return {"result": False, "message": _t("Țara nu e în tabel.")}
		rez["tara"] = tara
		# al patrulea camp: coordonatele scrise ca pe televizor (lista oraselor din Screens/HdsLocul.py), in limba
		# meniului; pagina nu le mai scrie singura
		rez["orase"] = [[nume, lat / 1000.0, lon / 1000.0, L.textCoordonate(lat, lon)] for nume, lat, lon in L.orase(tara)]
	return rez


def loculInternetPorneste(cerere=None):
	"""POST /api/locul-internet: porneste cautarea locului dupa internet. Fara ruta spre internet nu pleaca nicio
	cerere (starea spune de ce). Nu scrie nimic: locul se scrie abia cu /api/locul-seteaza si internet=<semn>."""
	_loculInternet().CAUTARE.porneste()
	return {"result": True, "internet": _stareInternet()}


def loculInternetStare(cerere=None):
	"""GET /api/locul-internet-stare: starea cautarii (pagina o intreaba cat timp se cauta)"""
	return {"result": True, "internet": _stareInternet()}


def loculSeteaza(cerere):
	"""POST /api/locul-seteaza: tara= si oras= (din tabel), lat= si lon= (grade, nord si est pozitive) sau internet=
	(semnul locului gasit dupa internet, confirmat in pagina). Acelasi HdsLocul.seteaza ca pe televizor: locul unic,
	copiile din Setari tuner, settings, nucleul."""
	L = _locul()
	if cerere.get("internet"):
		# numai locul aratat in pagina (semnul lui), cat e inca valabil
		ok, text = _loculInternet().CAUTARE.foloseste(str(cerere.get("internet")))
	elif cerere.get("tara") or cerere.get("oras"):
		tara, oras = cerere.get("tara", ""), cerere.get("oras", "")
		loc = L.gasesteOras(tara, oras)
		if loc is None:
			return {"result": False, "message": _t(L.MESAJ_ORAS), "locul": L.stare()}
		ok, text = L.seteaza(loc[0], loc[1], tara, oras, L.SURSA_TABEL)
	else:
		lat, lon = _grade(cerere.get("lat"), 90), _grade(cerere.get("lon"), 180)
		if lat is None or lon is None:
			return {"result": False, "message": _t(MESAJ_COORDONATE), "locul": L.stare()}
		ok, text = L.seteaza(int(round(lat * 1000)), int(round(lon * 1000)), "", "", L.SURSA_MANA)
	if ok:
		text = _t("Locul antenei este acum: %s") % L.textLoc()
	return {"result": bool(ok), "message": text or "", "locul": L.stare()}


# ================================================================== rutele
def _restulCaii(request):
	"""Primul segment de dupa /antena/ („lnb”, „semnal”) sau "". Pe o resursa isLeaf, Twisted lasa restul adresei in
	request.postpath; request.path ramane rezerva."""
	rest = getattr(request, "postpath", None)
	if rest:
		primul = rest[0]
		return primul.decode("utf-8", "replace") if isinstance(primul, bytes) else str(primul)
	cale = getattr(request, "path", None)
	if isinstance(cale, bytes):
		cale = cale.decode("utf-8", "replace")
	if isinstance(cale, str) and cale.startswith("/antena/"):
		return cale[len("/antena/"):].split("/")[0]
	return ""


def rute(baza, resource, NOT_DONE_YET, pagina_antena=None):
	"""Resursele: (rutele de sub /api, resursa paginii /antena). `baza` e HdsJsonResource din plugin.py: fiecare cerere
	trece prin aceeasi poarta ca restul interfetei. `pagina_antena` e resursa paginii /antena din scanare_web.py, care
	primeste tot ce nu e /antena/lnb sau /antena/semnal. Pagina /motor ramane resursa din plugin.py, care cheama
	paginaMotor() de aici."""

	class _Citire(baza):
		"""GET, numai citire: cu cookie sau cu jeton. `lucru(cerere)` intoarce corpul JSON."""

		def render_GET(self, request):
			cerere, eroare = argumente(request)
			if eroare:
				return self._eroare(request, eroare)
			try:
				corp = self.lucru(cerere)
			except Exception as e:
				_jurnal("%s: %s" % (self.__class__.__name__, e))
				return self._eroare(request, _t("Eroare pe receptor: %s") % e, 500)
			return self._raspunde(request, corp)

	class _Comanda(baza):
		"""POST, schimba ceva (misca motorul, acordeaza tunerul, scrie setari): numai din pagina receptorului, cu
		cookie-ul browserului asociat, aceeasi origine si antetul CSRF (_verificaAcces cu schimbaCeva). Cu ?token=,
		refuz: aceste comenzi au nevoie de pagina, cu intrebarile si paza ei. GET = 405."""
		schimbaCeva = True

		def render_POST(self, request):
			P = _plugin()
			if P.PARAM_JETON in request.args:
				return self._eroare(request, _t(MESAJ_DOAR_BROWSER), 403)
			cerere, eroare = argumente(request)
			if eroare:
				return self._eroare(request, eroare)
			try:
				corp = self.lucru(cerere)
			except Exception as e:
				_jurnal("%s: %s" % (self.__class__.__name__, e))
				return self._eroare(request, _t("Eroare pe receptor: %s") % e, 500)
			return self._raspunde(request, corp)

		def render_GET(self, request):
			request.setHeader(b"allow", b"POST")
			return self._eroare(request, _t("Comanda se trimite cu POST, din pagina receptorului."), 405)

	class _CitireCuFormular(baza):
		"""POST fara nicio schimbare (planul LNB-ului, cu toate campurile ciornei in corp): aceeasi poarta, fara CSRF."""

		def render_POST(self, request):
			cerere, eroare = argumente(request)
			if eroare:
				return self._eroare(request, eroare)
			try:
				corp = self.lucru(cerere)
			except Exception as e:
				_jurnal("%s: %s" % (self.__class__.__name__, e))
				return self._eroare(request, _t("Eroare pe receptor: %s") % e, 500)
			return self._raspunde(request, corp)

	# ---- Configurare LNB
	class LnbResource(_Citire):
		"""GET /api/lnb[?slot=N]: tunerul, LNB-urile, alegerile si starea aplicarii."""
		def lucru(self, cerere):
			return lnbDate(cerere.get("slot"))

	class LnbPlanResource(_CitireCuFormular):
		"""POST /api/lnb-plan: ce s-ar schimba (sau, cu doar=proba, „Probă de calcul” pentru ciorna). Nu scrie nimic."""
		def lucru(self, cerere):
			return lnbPlan(cerere)

	class LnbAplicaResource(_Comanda):
		"""POST /api/lnb-aplica: aplica planul vazut in previzualizare (semn=), cu proba si intrebarea de 60 s."""
		def lucru(self, cerere):
			return lnbAplica(cerere)

	class LnbRaspunsResource(_Comanda):
		"""POST /api/lnb-raspuns?raspuns=pastrez|revin."""
		def lucru(self, cerere):
			return lnbRaspuns(cerere)

	class LnbStareResource(_Citire):
		"""GET /api/lnb-stare: proba, intrebarea si secundele ramase."""
		def lucru(self, cerere):
			st = stareAplicare()
			st["result"] = True
			return st

	# ---- Găsire semnal
	class SemnalResource(_Citire):
		"""GET /api/gasire-semnal: tunerele, satelitii, transponderul de pornire, listele si starea masurarii."""
		def lucru(self, cerere):
			return semnalDate()

	class SemnalTranspondereResource(_Citire):
		"""GET /api/gasire-semnal-transpondere?slot=&poz=: transponderele satelitului."""
		def lucru(self, cerere):
			return semnalTranspondere(cerere)

	class SemnalStareResource(_Citire):
		"""GET /api/gasire-semnal-stare: nivelul, calitatea, BER-ul, blocarea, verdictul (si tine masurarea pornita)."""
		def lucru(self, cerere):
			return semnalStare()

	class SemnalPornesteResource(_Comanda):
		"""POST /api/gasire-semnal-porneste: masoara transponderul ales."""
		def lucru(self, cerere):
			return semnalPorneste(cerere)

	class SemnalReacordeazaResource(_Comanda):
		"""POST /api/gasire-semnal-reacordeaza."""
		def lucru(self, cerere):
			return semnalReacordeaza(cerere)

	class SemnalOpresteResource(_Comanda):
		"""POST /api/gasire-semnal-opreste."""
		def lucru(self, cerere):
			return semnalOpreste(cerere)

	# ---- Rotirea antenei: comenzile (afisajul ramane /api/motor, in plugin.py)
	class MotorComenziResource(_Citire):
		"""GET /api/motor-comenzi: tunerele cu motor, satelitii, locul USALS, starea comenzilor; cu ?urma=N, ultimele N
		rânduri din urma comenzilor de motor (motorUrma)."""
		def lucru(self, cerere):
			if cerere.get("urma") is not None:
				return motorUrma(cerere)
			return motorDate(cerere)

	class MotorComandaResource(_Comanda):
		"""POST /api/motor-comanda?actiune=...: o comanda a motorului."""
		def lucru(self, cerere):
			return motorComanda(cerere)

	# ---- Locul antenei
	class LoculResource(_Citire):
		"""GET /api/locul[?tara=RO]: locul antenei, tarile si orasele unei tari."""
		def lucru(self, cerere):
			return loculDate(cerere)

	class LoculSeteazaResource(_Comanda):
		"""POST /api/locul-seteaza: locul din tabel (tara, oras), scris (lat, lon) sau gasit dupa internet (internet)."""
		def lucru(self, cerere):
			return loculSeteaza(cerere)

	class LoculInternetResource(_Comanda):
		"""POST /api/locul-internet: porneste cautarea locului dupa internet (numai din browserul conectat: cu ?token=
		nu pleaca nicio cerere spre internet)."""
		def lucru(self, cerere):
			return loculInternetPorneste(cerere)

	class LoculInternetStareResource(_Citire):
		"""GET /api/locul-internet-stare: starea cautarii locului dupa internet."""
		def lucru(self, cerere):
			return loculInternetStare(cerere)

	# ---- paginile
	class PaginaAntena(resource.Resource):
		"""GET /antena[/...]: /antena/lnb, /antena/semnal si /antena/locul sunt paginile de aici; restul e pagina din
		scanare_web.py."""
		isLeaf = True

		def render_GET(self, request):
			cale = _restulCaii(request)
			if cale == "lnb":
				return paginaLnb(request)
			if cale == "semnal":
				return paginaSemnal(request)
			if cale == "locul":
				return paginaLocul(request)
			if pagina_antena is not None:
				return pagina_antena.render_GET(request)
			return paginaLnb(request)

	api = {
		b"lnb": LnbResource(),
		b"lnb-plan": LnbPlanResource(),
		b"lnb-aplica": LnbAplicaResource(),
		b"lnb-raspuns": LnbRaspunsResource(),
		b"lnb-stare": LnbStareResource(),
		b"gasire-semnal": SemnalResource(),
		b"gasire-semnal-transpondere": SemnalTranspondereResource(),
		b"gasire-semnal-stare": SemnalStareResource(),
		b"gasire-semnal-porneste": SemnalPornesteResource(),
		b"gasire-semnal-reacordeaza": SemnalReacordeazaResource(),
		b"gasire-semnal-opreste": SemnalOpresteResource(),
		b"motor-comenzi": MotorComenziResource(),
		b"motor-comanda": MotorComandaResource(),
		b"locul": LoculResource(),
		b"locul-seteaza": LoculSeteazaResource(),
		b"locul-internet": LoculInternetResource(),
		b"locul-internet-stare": LoculInternetStareResource(),
	}
	return api, PaginaAntena()


# ================================================================== paginile
def _pagina(request, sablon):
	"""Aceeasi poarta ca /antena si /ecrane: reteaua locala, apoi ?token= sau cookie-ul browserului asociat; un browser
	neconectat primeste pagina de asociere. Paginile dau comenzi, deci cu cookie primesc tokenul CSRF; cu ?token=
	pagina doar arata (comenzile cer browserul conectat)."""
	P = _plugin()
	if not P._esteAdresaLocala(P._adresaClient(request)):
		request.setResponseCode(403)
		request.setHeader(b"content-type", b"text/plain; charset=utf-8")
		return _t("Acces permis doar din rețeaua locală.").encode("utf-8")
	P._anteteHtml(request)
	if P.PARAM_JETON in request.args and P._jetonValid(request):
		config_pagina = P._configPanou("", P._jetonConfigurat(), "")   # jetonul de pe SERVER, nu cel primit
	else:
		secret, browser = P._sesiuneDinCerere(request)
		if browser is None:
			return P._PAGINA_ASOCIERE.encode("utf-8")
		config_pagina = P._configPanou(P.csrfPentru(secret), "", browser.get("nume", ""))
	return sablon.replace("__STIL_COMUN__", P._STIL_COMUN).replace("__CONFIG__", config_pagina).encode("utf-8", "replace")


def paginaLnb(request):
	return _pagina(request, _traducePagina(PAGINA_LNB))


def paginaSemnal(request):
	return _pagina(request, _traducePagina(PAGINA_SEMNAL))


def paginaMotor(request):
	return _pagina(request, _traducePagina(PAGINA_MOTOR))


def paginaLocul(request):
	return _pagina(request, _traducePagina(PAGINA_LOCUL))


# ------------------------------------------------------------------ ce au in comun cele trei pagini
# Stilul general (_STIL_COMUN) vine din plugin.py la cerere (__STIL_COMUN__), ca la scanare_web.py; aici e numai ce e
# al acestor pagini. Totul se aseaza si pe telefon (375 px): o singura coloana, butoane care trec pe randul urmator,
# niciun element mai lat decat ecranul.
_STIL_PAGINI = """
  main{max-width:760px;margin:0 auto;}
  h1{font-size:1.25rem;margin:0 0 4px;}
  h3{font-size:.95rem;margin:18px 0 6px;color:var(--text-slab);}
  .subtitlu{color:var(--text-slab);font-size:.85rem;margin:0 0 14px;min-height:1.2em;}
  .card{background:var(--panou);border:1px solid var(--bordura);border-radius:10px;padding:16px;margin:0 0 12px;}
  .card h2{font-size:1rem;margin:0 0 10px;}
  label.eticheta{display:block;margin:12px 0 4px;color:var(--text-slab);font-size:.9rem;}
  select,input.text{width:100%;min-height:44px;padding:8px 10px;border-radius:8px;border:1px solid var(--bordura);background:#0f1216;color:var(--text);font-size:16px;}
  .bifa{display:flex;gap:10px;align-items:center;min-height:44px;margin-top:8px;cursor:pointer;}
  .bifa input{width:22px;height:22px;flex:none;}
  .nota{color:var(--text-slab);font-size:.85rem;margin:6px 0 0;line-height:1.45;}
  .mesaj{margin:10px 0 0;line-height:1.45;font-size:.92rem;}
  .eroare{color:#ffb4a8;}
  .avert{color:#ffd88a;}
  .butoane{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}
  .butoane .buton{flex:1 1 140px;}
  .buton{min-height:44px;padding:10px 16px;border-radius:8px;border:none;background:var(--accent);color:#fff;font:inherit;cursor:pointer;}
  .buton.secundar{background:transparent;border:1px solid var(--bordura);color:var(--text);}
  .buton.rosu{background:var(--rosu);}
  .buton[disabled]{opacity:.5;cursor:default;}
  .linie{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid var(--bordura);font-size:.92rem;}
  .linie:last-child{border-bottom:none;}
  .linie span:first-child{color:var(--text-slab);flex:none;}
  .linie span:last-child{text-align:right;overflow-wrap:anywhere;min-width:0;}
  .intrebare{margin:12px 0 0;padding:12px;border:1px solid var(--galben);border-radius:8px;line-height:1.45;white-space:pre-line;}
  .ascuns{display:none !important;}
  ul.lista{margin:8px 0 0;padding-left:20px;line-height:1.5;}
  ul.cod{margin:8px 0 0;padding-left:0;list-style:none;font-family:ui-monospace,Consolas,monospace;font-size:.8rem;line-height:1.5;overflow-wrap:anywhere;}
  details{margin-top:10px;} summary{cursor:pointer;color:var(--text-slab);min-height:32px;}
  .doua{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
  .doua > div{min-width:0;}
  footer{margin:16px 0 0;color:var(--text-slab);font-size:.85rem;display:flex;flex-wrap:wrap;gap:8px 18px;}
"""

# Legaturile din subsolul celor trei pagini: aceleasi locuri ca in subsolul panoului.
_SUBSOL = """<footer>
  <a href="/antena">Orientarea și setarea antenei</a>
  <a href="/antena/lnb">Configurare LNB</a>
  <a href="/motor">Rotirea antenei</a>
  <a href="/antena/locul">Locul antenei</a>
  <a href="/antena/semnal">Găsire semnal</a>
</footer>"""

# Ajutoarele de JavaScript ale paginilor (aceleasi ca in pagina /antena): adresa cu jetonul in modul jeton, cererea cu
# antetul CSRF si keepalive la inchiderea paginii, elemente create numai cu textContent (niciun text venit din receptor
# nu intra ca HTML).
_JS_COMUN = """
var CFG = __CONFIG__;
function $(id){ return document.getElementById(id); }
function adresa(cale){
  if(!CFG.jeton){ return cale; }
  return cale + (cale.indexOf("?") === -1 ? "?" : "&") + "token=" + encodeURIComponent(CFG.jeton);
}
function cerere(cale, metoda, date, laInchidere){
  var optiuni = {method: metoda || "GET", cache: "no-store", credentials: "same-origin", headers: {}};
  if(CFG.csrf){ optiuni.headers["X-HDS-CSRF"] = CFG.csrf; }
  if(date){
    optiuni.headers["Content-Type"] = "application/x-www-form-urlencoded";
    optiuni.body = date.toString();
  }
  if(laInchidere){ optiuni.keepalive = true; }
  return fetch(adresa(cale), optiuni).then(function(r){
    if(r.status === 401 && !CFG.jeton){ location.replace("/"); throw new Error("browser deconectat"); }
    return r.json().catch(function(){
      return {result: false, message: "Receptorul a răspuns neașteptat (HTTP " + r.status + ")."};
    });
  });
}
function el(tag, clasa, text){
  var e = document.createElement(tag);
  if(clasa){ e.className = clasa; }
  if(text !== undefined && text !== null){ e.textContent = text; }
  return e;
}
function goleste(e){ while(e.firstChild){ e.removeChild(e.firstChild); } }
function arata(e, da){ e.classList.toggle("ascuns", !da); }
function mesaj(e, text, eroare){ e.textContent = text || ""; e.classList.toggle("eroare", !!eroare); }
function linie(parinte, stanga, dreapta){
  if(dreapta === undefined || dreapta === null || dreapta === ""){ return; }
  var r = el("div", "linie");
  r.appendChild(el("span", "", stanga));
  r.appendChild(el("span", "", String(dreapta)));
  parinte.appendChild(r);
}
function optiuni(select, lista, ales){
  goleste(select);
  lista.forEach(function(x){
    var o = el("option", "", x[1]);
    o.value = String(x[0]);
    if(String(x[0]) === String(ales)){ o.selected = true; }
    select.appendChild(o);
  });
}
function buton(text, clasa, apasare){
  var b = el("button", "buton" + (clasa ? " " + clasa : ""), text);
  b.type = "button";
  b.addEventListener("click", apasare);
  return b;
}
function secunde(s){
  s = Math.max(0, Math.round(s));
  return s < 60 ? s + " s" : Math.floor(s / 60) + " min " + (s % 60) + " s";
}
// o intrebare in pagina (pe telefon, fara ferestre ale browserului): „Nu” e alegerea pregatita
function intreaba(cutie, text, textDa, textNu, laDa, laNu){
  goleste(cutie);
  cutie.appendChild(el("div", "", text));
  var nu = buton(textNu || "Nu", "secundar", function(){ arata(cutie, false); if(laNu){ laNu(); } });
  var da = buton(textDa || "Da", "", function(){ arata(cutie, false); laDa(); });
  var rand = el("div", "butoane");
  rand.appendChild(nu);
  rand.appendChild(da);
  cutie.appendChild(rand);
  arata(cutie, true);
  cutie.scrollIntoView({block: "nearest"});
  nu.focus();
}
Array.prototype.forEach.call(document.querySelectorAll("footer a"), function(a){
  a.href = adresa(a.getAttribute("href"));
});
"""


# ------------------------------------------------------------------ Locul antenei
# Acelasi tabel si aceeasi functie de salvare ca ecranul de pe televizor (Screens/HdsLocul.py): Components/HdsLocul.py.
PAGINA_LOCUL = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Locul antenei</title>
<style>__STIL_COMUN__""" + _STIL_PAGINI + """
  #acum{font-size:1.05rem;}
</style>
</head>
<body>
<main>
<h1>Locul antenei</h1>
<p class="subtitlu">Motorul USALS calculează unghiul spre fiecare satelit din locul tău. Același loc ca pe televizor.</p>
<div class="card">
  <h2>Acum</h2>
  <p class="mesaj" id="acum">Se încarcă...</p>
</div>
<div class="card ascuns" id="cardInternet">
  <h2>Află locul după internet</h2>
  <p class="nota">Receptorul întreabă serverul HD Satelit ce oraș arată adresa lui de internet. Locul se schimbă numai după ce îl confirmi.</p>
  <div class="butoane"><button type="button" class="buton" id="cautaInternet">Află locul după internet</button></div>
  <p class="mesaj" id="mesajInternet" role="status"></p>
  <div class="intrebare ascuns" id="intrebareInternet"></div>
  <p class="nota">Orașul după adresa de internet: <a href="https://db-ip.com" target="_blank" rel="noopener noreferrer">IP Geolocation by DB-IP</a>, licența CC BY 4.0. Serverul nu păstrează adresa de internet.</p>
</div>
<p class="nota avert ascuns" id="faraInternet">Receptorul nu are internet acum: alege țara și orașul din listă.</p>
<div class="card" id="cardOras">
  <h2>Țara și orașul</h2>
  <label class="eticheta" for="tara">Țara</label>
  <select id="tara"></select>
  <label class="eticheta" for="oras">Orașul</label>
  <select id="oras"></select>
  <p class="nota">Alege orașul cel mai apropiat: câțiva kilometri nu contează pentru unghiul antenei.</p>
  <div class="butoane"><button type="button" class="buton" id="salveazaOras">Salvează locul</button></div>
</div>
<div class="card">
  <h2>Coordonatele scrise de mână</h2>
  <div class="doua">
    <div><label class="eticheta" for="lat">Latitudinea (grade, nord +)</label><input class="text" id="lat" inputmode="decimal"></div>
    <div><label class="eticheta" for="lon">Longitudinea (grade, est +)</label><input class="text" id="lon" inputmode="decimal"></div>
  </div>
  <p class="nota">Cu virgulă sau punct, de exemplu 44,426 și 26,103. Sudul și vestul se scriu cu minus.</p>
  <div class="butoane"><button type="button" class="buton secundar" id="salveazaMana">Salvează coordonatele</button></div>
</div>
<p class="mesaj" id="mesaj" role="status"></p>
<p class="nota" id="sursa"></p>
""" + _SUBSOL + """
</main>
<script>""" + _JS_COMUN + """
var S = {tari: [], ultim: null};
var IMPLICIT = {RO: "București", MD: "Chișinău"};
function arataLocul(l){
  const acum = $("acum");
  S.ultim = l.stabilit + "|" + l.text;
  acum.textContent = l.stabilit ? l.text : "Nestabilit. Până îl alegi, motorul USALS nu rotește antena spre niciun satelit; pașii, pozițiile memorate și limitele merg.";
  acum.classList.toggle("avert", !l.stabilit);
  // cifrele pe care omul le scrie acum in campuri nu se schimba sub degete
  const a = document.activeElement;
  if (l.stabilit && a !== $("lat") && a !== $("lon")){ $("lat").value = String(l.lat).replace(".", ","); $("lon").value = String(l.lon).replace(".", ","); }
}
function incarcaOrase(tara, ales){
  return cerere("/api/locul?tara=" + encodeURIComponent(tara)).then(function(d){
    if (!d.result){ mesaj($("mesaj"), d.message, true); return; }
    // coordonatele vin scrise de receptor, ca pe televizor (literele si separatorul limbii meniului)
    optiuni($("oras"), d.orase.map(o => [o[0], o[0] + "  (" + (o[3] || "") + ")"]), ales);
  }).catch(function(){ mesaj($("mesaj"), "Receptorul nu răspunde.", true); });
}
function trimite(p){
  mesaj($("mesaj"), "Se salvează...");
  cerere("/api/locul-seteaza", "POST", p).then(function(d){
    mesaj($("mesaj"), d.message, !d.result);
    if (d.locul) arataLocul(d.locul);
  }).catch(function(){ mesaj($("mesaj"), "Receptorul nu răspunde.", true); });
}
// locul dupa internet: cardul apare numai cand receptorul are ruta spre internet; fara ea, lista ca pana acum
function arataInternet(i){
  const are = !!(i && i.retea);
  arata($("cardInternet"), are);
  arata($("faraInternet"), !are);
}
function alegeDinLista(tara, oras){
  if (S.tari.some(function(t){ return t[0] === tara; })){
    $("tara").value = tara;
    incarcaOrase(tara, oras || IMPLICIT[tara] || "");
  }
  $("cardOras").scrollIntoView({block: "nearest"});
}
function cautareCazuta(){
  $("cautaInternet").disabled = false;
  mesaj($("mesajInternet"), "Receptorul nu răspunde.", true);
}
function urmaresteInternet(d){
  if (!d.result){ $("cautaInternet").disabled = false; mesaj($("mesajInternet"), d.message, true); return; }
  const i = d.internet;
  if (i.stare === "lucreaza"){
    mesaj($("mesajInternet"), i.mesaj);
    setTimeout(function(){ cerere("/api/locul-internet-stare").then(urmaresteInternet).catch(cautareCazuta); }, 700);
    return;
  }
  $("cautaInternet").disabled = !CFG.csrf;
  if (i.stare === "gasit" && i.gasit){
    mesaj($("mesajInternet"), "");
    // "Alege din listă": lista se deschide pe orasul din tabel cel mai apropiat de locul gasit (orasul gasit poate lipsi din tabel)
    intreaba($("intrebareInternet"), i.intrebare, "Folosește acest loc", "Alege din listă", function(){
      const p = new URLSearchParams();
      p.set("internet", i.semn);
      trimite(p);
    }, function(){ alegeDinLista(i.gasit.tara_lista || i.gasit.tara, i.gasit.oras_lista); });
    return;
  }
  // fara internet, serverul nu raspunde, raspuns stricat: mesajul si lista, ca pana acum
  mesaj($("mesajInternet"), i.mesaj, true);
  if (i.stare === "fara_retea"){ arataInternet(i); mesaj($("mesaj"), i.mesaj, true); }
  $("cardOras").scrollIntoView({block: "nearest"});
}
$("cautaInternet").addEventListener("click", function(){
  arata($("intrebareInternet"), false);
  this.disabled = true;
  mesaj($("mesajInternet"), "Se caută...");
  cerere("/api/locul-internet", "POST", new URLSearchParams()).then(urmaresteInternet).catch(cautareCazuta);
});
$("tara").addEventListener("change", function(){ incarcaOrase(this.value, IMPLICIT[this.value] || ""); });
$("salveazaOras").addEventListener("click", function(){
  if (!$("oras").value) return;
  const p = new URLSearchParams();
  p.set("tara", $("tara").value);
  p.set("oras", $("oras").value);
  trimite(p);
});
$("salveazaMana").addEventListener("click", function(){
  const p = new URLSearchParams();
  p.set("lat", $("lat").value.trim());
  p.set("lon", $("lon").value.trim());
  trimite(p);
});
// locul schimbat din alta parte (televizorul, alt browser): "Acum" si listele se refac singure, fara sa re-incarci pagina
function locSchimbat(l){
  arataLocul(l);
  const a = document.activeElement;
  if (l.tara && a !== $("tara") && a !== $("oras") && S.tari.some(function(t){ return t[0] === l.tara; })){
    $("tara").value = l.tara;
    incarcaOrase(l.tara, l.oras || IMPLICIT[l.tara] || "");
  }
}
function urmaresteLocul(){
  setTimeout(function(){
    if (document.hidden){ urmaresteLocul(); return; }
    cerere("/api/locul").then(function(d){
      if (d.result && d.locul && S.ultim !== d.locul.stabilit + "|" + d.locul.text) locSchimbat(d.locul);
    }).catch(function(){}).then(urmaresteLocul);
  }, 3000);
}
cerere("/api/locul").then(function(d){
  if (!d.result){ mesaj($("mesaj"), d.message, true); return; }
  S.tari = d.tari;
  arataLocul(d.locul);
  $("sursa").textContent = d.sursa_text || ("Coordonatele orașelor: " + d.sursa_date + ".");
  arataInternet(d.internet);
  const tara = d.locul.tara || "RO";
  optiuni($("tara"), d.tari, tara);
  incarcaOrase(tara, d.locul.oras || IMPLICIT[tara] || "");
  if (!CFG.csrf){
    $("salveazaOras").disabled = $("salveazaMana").disabled = $("cautaInternet").disabled = true;
    mesaj($("mesaj"), "Locul se schimbă numai dintr-un browser conectat cu codul de pe televizor. Aici se vede numai locul de acum.");
  }
  urmaresteLocul();
}).catch(function(){ mesaj($("acum"), "Receptorul nu răspunde.", true); });
</script>
</body>
</html>
"""


# ------------------------------------------------------------------ Configurare LNB
PAGINA_LNB = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Configurare LNB</title>
<style>__STIL_COMUN__""" + _STIL_PAGINI + """
  @media(max-width:520px){ .card{padding:14px;} }
</style>
</head>
<body>
<main>
<h1>Configurare LNB</h1>
<p class="subtitlu" id="subtitlu">Se citesc setările tunerului...</p>

<div class="card ascuns" id="cardSetari">
  <div id="randTuner">
    <label class="eticheta" for="tuner">Tuner</label>
    <select id="tuner"></select>
  </div>
  <div class="linie"><span>Antena</span><span id="antena"></span></div>
  <div id="randLnb">
    <label class="eticheta" for="lnb">LNB</label>
    <select id="lnb"></select>
  </div>
  <div id="campuri"></div>
  <label class="bifa"><input type="checkbox" id="d13v"> Comenzi DiSEqC la 13 V</label>
  <p class="nota" id="ajutor13v"></p>
  <div class="linie"><span>Probă de calcul</span><span id="proba"></span></div>
  <p class="nota" id="ajutorProba"></p>
  <div class="butoane">
    <button type="button" class="buton" id="salveaza">Vezi ce se schimbă</button>
    <button type="button" class="buton secundar" id="renunta">Renunță la schimbări</button>
    <button type="button" class="buton secundar ascuns" id="inainte">Ce era înainte</button>
  </div>
  <div class="intrebare ascuns" id="intrebareLnb"></div>
  <div class="mesaj" id="mesaj" role="status"></div>
</div>

<div class="card ascuns" id="cardPlan">
  <h2 id="titluPlan">Ce se schimbă</h2>
  <p class="mesaj eroare" id="oprire"></p>
  <ul class="lista" id="rezumat"></ul>
  <ul class="lista avert" id="avertismente"></ul>
  <p class="nota" id="notaPlan"></p>
  <details id="cutieDetalii"><summary>Detalii</summary><ul class="cod" id="detalii"></ul></details>
  <div class="butoane">
    <button type="button" class="buton" id="aplica">Aplică</button>
    <button type="button" class="buton secundar" id="inapoiPlan">Înapoi</button>
  </div>
  <div class="mesaj" id="mesajPlan" role="status"></div>
</div>

<div class="card ascuns" id="cardProba">
  <h2 id="titluProba">Verificarea semnalului</h2>
  <p class="mesaj" id="textProba" role="status"></p>
  <div class="intrebare ascuns" id="intrebare"></div>
  <div class="butoane" id="randRevin">
    <button type="button" class="buton rosu" id="revin">Revin la ce era</button>
  </div>
  <div class="mesaj" id="mesajProba" role="status"></div>
</div>

""" + _SUBSOL + """
</main>
<script>""" + _JS_COMUN + """
var S = {date: null, lnb: "", ciorna: {}, d13v: null, proba: {}, plan: null, ceasProba: null, ceasStare: null,
  fazaVazuta: "", intrebareFacuta: false};

function lnbCurent(){
  var l = (S.date && S.date.lnburi) || [];
  for(var i = 0; i < l.length; i++){ if(l[i].id === S.lnb){ return l[i]; } }
  return l.length ? l[0] : null;
}
function valoare(l, camp){
  var c = S.ciorna[l.id];
  return (c && Object.prototype.hasOwnProperty.call(c, camp)) ? c[camp] : l[camp];
}
function areCiorna(){
  return Object.keys(S.ciorna).length > 0 || (S.d13v !== null && S.d13v !== S.date.model.diseqc13V);
}
function puneCiorna(l, camp, v){
  var c = S.ciorna[l.id] || {};
  if(String(v) === String(l[camp])){ delete c[camp]; } else { c[camp] = v; }
  if(Object.keys(c).length){ S.ciorna[l.id] = c; } else { delete S.ciorna[l.id]; }
  schimbat();
}
function parametri(){
  var p = new URLSearchParams();
  p.set("slot", String(S.date.slot));
  (S.date.lnburi || []).forEach(function(l){
    var c = S.ciorna[l.id];
    if(!c){ return; }
    Object.keys(c).forEach(function(camp){
      var v = c[camp];
      p.set("l_" + l.cheie + "_" + camp, v === true ? "1" : (v === false ? "0" : String(v)));
    });
  });
  if(S.d13v !== null && S.d13v !== S.date.model.diseqc13V){ p.set("diseqc13v", S.d13v ? "1" : "0"); }
  return p;
}

function camp(parinte, eticheta, control, ajutor){
  var id = "c" + Math.random().toString(36).slice(2);
  var l = el("label", "eticheta", eticheta);
  l.htmlFor = id;
  control.id = id;
  parinte.appendChild(l);
  parinte.appendChild(control);
  if(ajutor){ parinte.appendChild(el("p", "nota", ajutor)); }
}
function citit(parinte, eticheta, text){
  linie(parinte, eticheta, text || "-");
}
function alegere(parinte, eticheta, l, nume, lista, ajutor){
  var s = el("select");
  optiuni(s, lista, valoare(l, nume));
  s.addEventListener("change", function(){ puneCiorna(l, nume, s.value); deseneazaCampuri(); });
  camp(parinte, eticheta, s, ajutor);
}
function numar(parinte, eticheta, l, nume, ajutor){
  var i = el("input", "text");
  i.inputMode = "numeric";
  i.value = String(valoare(l, nume));
  i.addEventListener("input", function(){
    var t = i.value.trim();
    puneCiorna(l, nume, /^[0-9]+$/.test(t) ? parseInt(t, 10) : t);
  });
  camp(parinte, eticheta, i, ajutor);
}
function deseneazaCampuri(){
  var c = $("campuri");
  goleste(c);
  var l = lnbCurent();
  if(!l){ return; }
  var a = S.date.ajutor, v = l.voie;
  if(v.tip){
    var tip = valoare(l, "tip");
    var ajutorTip = (S.date.model.simplu && tip !== S.date.tipuri.universal) ? a.tip_simplu : a.tip;
    alegere(c, "Tipul LNB-ului", l, "tip", l.alegeri.tip, ajutorTip);
    if(tip === S.date.tipuri.personalizat){
      var d = el("div", "doua");
      var j = el("div"), s = el("div");
      numar(j, "Oscilator jos (MHz)", l, "lofl");
      numar(s, "Oscilator sus (MHz)", l, "lofh");
      d.appendChild(j); d.appendChild(s);
      c.appendChild(d);
      c.appendChild(el("p", "nota", a.lof));
      numar(c, "Prag de bandă (MHz)", l, "prag", a.prag);
    }
  } else {
    citit(c, "Tipul LNB-ului", l.tip_text);
    c.appendChild(el("p", "nota", l.tip === "unicable" ? a.unicable : a.fix));
  }
  if(v.rest){
    alegere(c, "Tensiune", l, "tensiune", l.alegeri.tensiune, a.tensiune);
    alegere(c, "Ton 22 kHz", l, "ton", l.alegeri.ton, a.ton);
    var b = el("label", "bifa");
    var x = el("input");
    x.type = "checkbox";
    x.checked = !!valoare(l, "tensiune_marita");
    x.addEventListener("change", function(){ puneCiorna(l, "tensiune_marita", x.checked); });
    b.appendChild(x);
    b.appendChild(document.createTextNode(" Tensiune mărită (cablu lung)"));
    c.appendChild(b);
    c.appendChild(el("p", "nota", a.tensiune_marita));
  } else {
    citit(c, "Tensiune", l.tensiune_text);
    citit(c, "Ton 22 kHz", l.ton_text);
  }
  if(v.port){
    alegere(c, "Port DiSEqC", l, "comanda", l.alegeri.comanda, a.port);
  } else {
    citit(c, "Port DiSEqC", l.port_text);
    if(v.tip){ c.appendChild(el("p", "nota", a.fix)); }
  }
  $("proba").textContent = S.proba[l.cheie] !== undefined ? S.proba[l.cheie] : l.proba;
}
function schimbat(){
  S.plan = null;
  arata($("cardPlan"), false);
  $("renunta").disabled = !areCiorna();
  arata($("inainte"), !!S.date.copie && !areCiorna());
  mesaj($("mesaj"), "");
  if(S.ceasProba){ clearTimeout(S.ceasProba); }
  S.ceasProba = setTimeout(cereProba, 350);
}
function cereProba(){
  S.ceasProba = null;
  var p = parametri();
  p.set("doar", "proba");
  cerere("/api/lnb-plan", "POST", p).then(function(d){
    if(!d.result){ mesaj($("mesaj"), d.message, true); return; }
    S.proba = d.proba || {};
    var l = lnbCurent();
    if(l){ $("proba").textContent = S.proba[l.cheie] !== undefined ? S.proba[l.cheie] : l.proba; }
    if(d.greseala){ mesaj($("mesaj"), d.greseala, true); }
  }).catch(function(){});
}

function deseneaza(){
  var d = S.date;
  arata($("cardSetari"), !!d.model);
  if(!d.model){
    $("subtitlu").textContent = d.mesaj || "Receptorul nu are niciun tuner de satelit.";
    return;
  }
  var m = d.model;
  $("subtitlu").textContent = m.motiv || (m.simplu ? "Tunerul " + m.litera + " e în modul simplu." : "Tunerul " + m.litera + " e în modul avansat.");
  arata($("randTuner"), d.tunere.length > 1);
  optiuni($("tuner"), d.tunere.map(function(t){ return [t.slot, t.text]; }), d.slot);
  $("antena").textContent = m.antena || "-";
  var lnburi = d.lnburi || [];
  if(!lnburi.some(function(l){ return l.id === S.lnb; })){ S.lnb = lnburi.length ? lnburi[0].id : ""; }
  arata($("randLnb"), lnburi.length > 1);
  optiuni($("lnb"), lnburi.map(function(l){ return [l.id, l.eticheta]; }), S.lnb);
  var bifa = $("d13v");
  bifa.checked = S.d13v !== null ? S.d13v : m.diseqc13V;
  bifa.disabled = !m.editabil;
  $("ajutor13v").textContent = d.ajutor.diseqc13V;
  $("ajutorProba").textContent = d.ajutor.proba;
  deseneazaCampuri();
  arata($("salveaza"), m.editabil && !!CFG.csrf);
  $("renunta").disabled = !areCiorna();
  arata($("renunta"), m.editabil && !!CFG.csrf);
  arata($("inainte"), !!d.copie && !areCiorna() && !!CFG.csrf);
  if(!CFG.csrf){ mesaj($("mesaj"), "Setările se schimbă numai dintr-un browser conectat cu codul de pe televizor."); }
  else if(d.ocupat && d.aplicare.faza === "liber"){ mesaj($("mesaj"), d.ocupat); }
}
function incarca(slot, pastreazaMesaj){
  var cale = "/api/lnb" + (slot !== undefined && slot !== null ? "?slot=" + encodeURIComponent(slot) : "");
  return cerere(cale).then(function(d){
    if(!d.result){ $("subtitlu").textContent = d.message || "Setările tunerului nu se pot citi."; return; }
    S.date = d;
    S.proba = {};
    deseneaza();
    if(!pastreazaMesaj){ mesaj($("mesaj"), ""); }
    deseneazaAplicarea(d.aplicare);
  }).catch(function(){ $("subtitlu").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}

$("tuner").addEventListener("change", function(){
  var nou = $("tuner").value;
  if(areCiorna()){
    intreaba($("intrebareLnb"), "Ai schimbări nesalvate pe tunerul " + S.date.model.litera + ". Le lași?", "Da, le las", "Nu",
      function(){ S.ciorna = {}; S.d13v = null; incarca(nou); },
      function(){ $("tuner").value = String(S.date.slot); });
    return;
  }
  incarca(nou);
});
$("lnb").addEventListener("change", function(){ S.lnb = $("lnb").value; deseneazaCampuri(); });
$("d13v").addEventListener("change", function(){ S.d13v = $("d13v").checked; schimbat(); });
$("renunta").addEventListener("click", function(){ S.ciorna = {}; S.d13v = null; S.proba = {}; deseneaza(); schimbat(); });

// ---- previzualizarea: ce se schimba (sau ce era inainte), apoi Aplica
function arataPlanul(plan){
  S.plan = plan;
  $("titluPlan").textContent = plan.titlu;
  mesaj($("oprire"), plan.oprire, true);
  arata($("oprire"), !!plan.oprire);
  var r = $("rezumat"); goleste(r);
  plan.rezumat.forEach(function(x){ r.appendChild(el("li", "", x)); });
  var a = $("avertismente"); goleste(a);
  plan.avertismente.forEach(function(x){ a.appendChild(el("li", "", x)); });
  $("notaPlan").textContent = plan.nota || "";
  var det = $("detalii"); goleste(det);
  plan.detalii.forEach(function(x){ det.appendChild(el("li", "", x)); });
  arata($("cutieDetalii"), plan.detalii.length > 0);
  $("aplica").disabled = !!plan.oprire;
  arata($("aplica"), !plan.oprire);
  mesaj($("mesajPlan"), "");
  arata($("cardPlan"), true);
  $("cardPlan").scrollIntoView({block: "start"});
}
function cerePlanul(p){
  $("salveaza").disabled = true;
  mesaj($("mesaj"), "Se pregătește lista schimbărilor...");
  cerere("/api/lnb-plan", "POST", p).then(function(d){
    $("salveaza").disabled = false;
    if(!d.result){ mesaj($("mesaj"), d.message, true); return; }
    mesaj($("mesaj"), "");
    arataPlanul(d.plan);
  }).catch(function(){ $("salveaza").disabled = false; mesaj($("mesaj"), "Receptorul nu răspunde.", true); });
}
$("salveaza").addEventListener("click", function(){
  if(!areCiorna()){ mesaj($("mesaj"), "Nu ai schimbat nimic."); return; }
  cerePlanul(parametri());
});
$("inainte").addEventListener("click", function(){
  if(areCiorna()){ mesaj($("mesaj"), "Salvează sau renunță întâi la schimbările de pe tunerul " + S.date.model.litera + ".", true); return; }
  var p = new URLSearchParams();
  p.set("slot", String(S.date.slot));
  p.set("fel", "inainte");
  cerePlanul(p);
});
$("inapoiPlan").addEventListener("click", function(){ arata($("cardPlan"), false); S.plan = null; });
$("aplica").addEventListener("click", function(){
  if(!S.plan){ return; }
  var p = S.plan.fel === "inainte" ? new URLSearchParams() : parametri();
  p.set("slot", String(S.date.slot));
  if(S.plan.fel === "inainte"){ p.set("fel", "inainte"); }
  p.set("semn", S.plan.semn);
  $("aplica").disabled = true;
  mesaj($("mesajPlan"), "Se aplică...");
  cerere("/api/lnb-aplica", "POST", p).then(function(d){
    $("aplica").disabled = false;
    if(!d.result){ mesaj($("mesajPlan"), d.message, true); if(d.aplicare){ deseneazaAplicarea(d.aplicare); } return; }
    arata($("cardPlan"), false);
    S.intrebareFacuta = false;
    deseneazaAplicarea(d.aplicare);
  }).catch(function(){ $("aplica").disabled = false; mesaj($("mesajPlan"), "Receptorul nu răspunde.", true); });
});

// ---- proba, intrebarea „Păstrezi noile setări?” si numaratoarea (ceasul e al receptorului)
function deseneazaAplicarea(st){
  if(!st){ return; }
  var faza = st.faza, card = $("cardProba"), q = $("intrebare");
  if(faza === "liber"){
    if(S.fazaVazuta && S.fazaVazuta !== "liber"){
      arata(card, true);
      $("textProba").textContent = st.text_proba || "";
      mesaj($("mesajProba"), st.mesaj);
      arata(q, false);
      arata($("randRevin"), false);
      S.fazaVazuta = "liber";
      S.ciorna = {}; S.d13v = null;
      incarca(S.date ? S.date.slot : null, true);
    }
    S.fazaVazuta = "liber";
    return;
  }
  S.fazaVazuta = faza;
  arata(card, true);
  arata($("cardPlan"), false);
  $("titluProba").textContent = "Verificarea semnalului, tunerul " + st.litera;
  $("textProba").textContent = st.text_proba || "";
  mesaj($("mesajProba"), "");
  if(!st.din_web){
    arata(q, false);
    arata($("randRevin"), false);
    mesaj($("mesajProba"), "Schimbarea a fost pornită de pe televizor și așteaptă răspunsul acolo.");
  } else if(faza === "confirmare"){
    arata($("randRevin"), false);
    if(!S.intrebareFacuta || !q.firstChild){
      S.intrebareFacuta = true;
      goleste(q);
      q.appendChild(el("div", "", "Păstrezi noile setări? Dacă nu răspunzi, revin singur la ce era."));
      var da = buton("Da, păstrez noile setări", "", function(){ raspunde("pastrez"); });
      var nu = buton("", "rosu", function(){ raspunde("revin"); });
      nu.id = "nu";
      var rand = el("div", "butoane");
      if(st.da_implicit){ rand.appendChild(da); rand.appendChild(nu); } else { rand.appendChild(nu); rand.appendChild(da); }
      q.appendChild(rand);
      arata(q, true);
      (st.da_implicit ? da : nu).focus();
    }
    $("nu").textContent = "Nu, revin la ce era (" + Math.max(0, st.secunde) + " s)";
  } else if(faza === "proba"){
    arata(q, false);
    arata($("randRevin"), true);
  } else {
    arata(q, false);
    arata($("randRevin"), false);
    mesaj($("mesajProba"), st.mesaj || "Receptorul pornește din nou programul.");
  }
  planificaStarea(1000);
}
function planificaStarea(ms){
  if(S.ceasStare){ clearTimeout(S.ceasStare); }
  S.ceasStare = setTimeout(citesteStarea, ms);
}
function citesteStarea(){
  S.ceasStare = null;
  cerere("/api/lnb-stare").then(deseneazaAplicarea).catch(function(){ planificaStarea(3000); });
}
function raspunde(r){
  var p = new URLSearchParams();
  p.set("raspuns", r);
  arata($("intrebare"), false);
  cerere("/api/lnb-raspuns", "POST", p).then(function(d){
    mesaj($("mesajProba"), d.message, !d.result);
    deseneazaAplicarea(d.aplicare);
  }).catch(function(){ mesaj($("mesajProba"), "Receptorul nu răspunde.", true); planificaStarea(2000); });
}
$("revin").addEventListener("click", function(){ raspunde("revin"); });
window.addEventListener("beforeunload", function(e){
  if(S.date && S.date.model && areCiorna()){ e.preventDefault(); e.returnValue = ""; }
});
incarca(null);
</script>
</body>
</html>
"""


# ------------------------------------------------------------------ Găsire semnal
PAGINA_SEMNAL = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Găsire semnal</title>
<style>__STIL_COMUN__""" + _STIL_PAGINI + """
  .verdict{font-size:1.6rem;font-weight:600;margin:0 0 6px;}
  .verdict.prins{color:#6fdc9a;} .verdict.rau{color:#ff8f7f;} .verdict.asteapta{color:#ffd88a;}
  .masura{display:grid;grid-template-columns:5.5em 1fr 3.2em;gap:10px;align-items:center;margin:10px 0;}
  .masura .nume{color:var(--text-slab);font-size:.9rem;}
  .masura .cifra{text-align:right;font-size:1.25rem;font-variant-numeric:tabular-nums;}
  .bara{height:18px;border-radius:9px;background:#0f1216;border:1px solid var(--bordura);overflow:hidden;min-width:0;}
  .bara div{height:100%;width:0;background:var(--albastru);transition:width .2s linear;}
  .bara.calitate div{background:var(--accent);}
</style>
</head>
<body>
<main>
<h1>Găsire semnal</h1>
<p class="subtitlu" id="subtitlu">Se citesc tunerele...</p>

<div class="card ascuns" id="cardAlegere">
  <div id="randTuner">
    <label class="eticheta" for="tuner">Tuner</label>
    <select id="tuner"></select>
  </div>
  <label class="eticheta" for="satelit">Satelit</label>
  <select id="satelit"></select>
  <label class="eticheta" for="transponder">Transponder</label>
  <select id="transponder"></select>
  <p class="nota" id="sarite"></p>
  <div id="manual" class="ascuns">
    <div class="doua">
      <div><label class="eticheta" for="frecventa">Frecvența (MHz)</label><input class="text" id="frecventa" inputmode="numeric"></div>
      <div><label class="eticheta" for="sr">Rata de simbol (kSymb/s)</label><input class="text" id="sr" inputmode="numeric"></div>
    </div>
    <div class="doua">
      <div><label class="eticheta" for="pol">Polarizare</label><select id="pol"></select></div>
      <div><label class="eticheta" for="sistem">Sistem</label><select id="sistem"></select></div>
    </div>
    <div id="randS2" class="doua">
      <div><label class="eticheta" for="mod">Modulație</label><select id="mod"></select></div>
      <div><label class="eticheta" for="fec2">FEC</label><select id="fec2"></select></div>
      <div><label class="eticheta" for="rolloff">Roll-off</label><select id="rolloff"></select></div>
      <div><label class="eticheta" for="pilot">Pilot</label><select id="pilot"></select></div>
    </div>
    <div id="randS1"><label class="eticheta" for="fec1">FEC</label><select id="fec1"></select></div>
  </div>
  <div class="butoane">
    <button type="button" class="buton" id="masoara">Pornește măsurarea</button>
    <button type="button" class="buton secundar" id="reacord">Acordează din nou</button>
    <button type="button" class="buton secundar" id="opreste">Oprește măsurarea</button>
  </div>
  <div class="intrebare ascuns" id="intrebare"></div>
  <p class="nota" id="notaPornire">Măsurarea ia tunerul: programul de pe televizor se oprește dacă folosește același tuner și pornește la loc când oprești măsurarea sau închizi pagina.</p>
  <div class="mesaj" id="mesaj" role="status"></div>
</div>

<div class="card ascuns" id="cardSemnal">
  <div class="verdict" id="verdict" role="status"></div>
  <div class="masura"><span class="nume">Nivel</span><div class="bara"><div id="baraNivel"></div></div><span class="cifra" id="nivel">-</span></div>
  <div class="masura"><span class="nume">Calitate</span><div class="bara calitate"><div id="baraCalitate"></div></div><span class="cifra" id="calitate">-</span></div>
  <div id="linii"></div>
  <ul class="lista" id="detalii"></ul>
  <p class="mesaj avert" id="eveniment"></p>
</div>

""" + _SUBSOL + """
</main>
<script>""" + _JS_COMUN + """
var S = {date: null, lista: null, ceas: null, ceasAcord: null, stare: null, curent: null};
var ASTEPTARE = {alocare: 1, acord: 1, motor: 1}, RAU = {fara_semnal: 1, pierdut: 1, refuzat: 1, ocupat: 1,
  inregistrare: 1, inregistrare_programata: 1, fara_tuner: 1, fara_sateliti: 1};

function tunerAles(){
  var t = S.date.tunere;
  for(var i = 0; i < t.length; i++){ if(String(t[i].slot) === $("tuner").value){ return t[i]; } }
  return t[0];
}
function aWebului(){
  var s = S.stare;
  return !!s && s.detinator === "web" && !s.ecran_deschis && ["oprita", "standby", "fara_tuner", "fara_sateliti"].indexOf(s.faza) === -1;
}
function puneListe(){
  var L = S.date.liste;
  optiuni($("pol"), L.polarizari, "0");
  optiuni($("mod"), L.modulatii, "2");
  optiuni($("fec2"), L.fec_dvbs2, "3");
  optiuni($("rolloff"), L.rolloffuri, "0");
  optiuni($("pilot"), L.piloti, "2");
  optiuni($("fec1"), L.fec_dvbs, "0");
}
function puneSistemele(){
  var t = tunerAles();
  optiuni($("sistem"), t.s2 ? S.date.liste.sisteme : S.date.liste.sisteme.slice(0, 1), $("sistem").value || "0");
  arataSistemul();
}
function arataSistemul(){
  var s2 = $("sistem").value === String(S.date.sistem_s2);
  arata($("randS2"), s2);
  arata($("randS1"), !s2);
}
function umpleManual(tp){
  $("frecventa").value = String(Math.round(tp.frequency / 1000));
  $("sr").value = String(Math.round(tp.symbol_rate / 1000));
  $("pol").value = String(tp.polarisation);
  $("sistem").value = String(tp.system);
  if(tp.system === S.date.sistem_s2){
    $("mod").value = String(tp.modulation); $("fec2").value = String(tp.fec);
    $("rolloff").value = String(tp.rolloff); $("pilot").value = String(tp.pilot);
  } else { $("fec1").value = String(tp.fec); }
  arataSistemul();
}
function puneSatelitii(pozitie){
  var t = tunerAles();
  optiuni($("satelit"), t.sateliti.map(function(s){ return [s.poz, s.text]; }), pozitie);
  if(!t.sateliti.length){ mesaj($("mesaj"), "Tunerul nu are niciun satelit configurat. Configurează antena în „Setări tuner”, apoi revino aici."); }
}
function puneTranspondere(d, tp){
  S.lista = d.transpondere;
  var lista = d.transpondere.map(function(e, i){ return [i, e.text]; });
  lista.push(["manual", "Introdus de mână"]);
  optiuni($("transponder"), lista, d.ales >= 0 ? d.ales : "manual");
  $("sarite").textContent = d.text_sarite || "";
  if(d.ales < 0 && tp){ umpleManual(tp); }
  else if(!d.transpondere.length){ mesaj($("mesaj"), "Satelitul nu are transpondere în lista lui: scrie valorile de mână."); }
  arata($("manual"), $("transponder").value === "manual");
}
function incarcaTranspondere(){
  var t = tunerAles();
  if(!t.sateliti.length){ S.lista = []; optiuni($("transponder"), [["manual", "Introdus de mână"]], "manual"); arata($("manual"), true); return Promise.resolve(); }
  var cale = "/api/gasire-semnal-transpondere?slot=" + t.slot + "&poz=" + encodeURIComponent($("satelit").value);
  return cerere(cale).then(function(d){
    if(!d.result){ mesaj($("mesaj"), d.message, true); return; }
    puneTranspondere(d, null);
  });
}
function parametri(){
  var p = new URLSearchParams();
  p.set("slot", String(tunerAles().slot));
  p.set("poz", $("satelit").value);
  var ales = $("transponder").value;
  p.set("tp", ales);
  if(ales === "manual"){
    var s2 = $("sistem").value === String(S.date.sistem_s2);
    p.set("frecventa", $("frecventa").value.trim());
    p.set("sr", $("sr").value.trim());
    p.set("pol", $("pol").value);
    p.set("sistem", $("sistem").value);
    p.set("fec", s2 ? $("fec2").value : $("fec1").value);
    p.set("mod", $("mod").value);
    p.set("rolloff", $("rolloff").value);
    p.set("pilot", $("pilot").value);
  }
  return p;
}
function trimite(cale, p){
  return cerere(cale, "POST", p || new URLSearchParams()).then(function(d){
    mesaj($("mesaj"), d.message, !d.result);
    if(d.stare){ deseneazaStarea(d.stare); }
    planifica(500);
    return d;
  }).catch(function(){ mesaj($("mesaj"), "Receptorul nu răspunde.", true); });
}
function masoara(){ return trimite("/api/gasire-semnal-porneste", parametri()); }
// ca pe televizor: cat merge masurarea, alta alegere se acordeaza singura (dupa o mica pauza, nu la fiecare tasta)
function laSchimbare(){
  if(S.ceasAcord){ clearTimeout(S.ceasAcord); S.ceasAcord = null; }
  if(aWebului()){ S.ceasAcord = setTimeout(function(){ S.ceasAcord = null; masoara(); }, 400); }
}

function procent(e, bara, v){
  $(e).textContent = v === null || v === undefined ? "-" : v + "%";
  $(bara).style.width = (v === null || v === undefined ? 0 : Math.max(0, Math.min(100, v))) + "%";
}
function deseneazaStarea(s){
  S.stare = s;
  arata($("cardSemnal"), true);
  var v = $("verdict");
  v.textContent = s.verdict;
  v.className = "verdict" + (s.faza === "prins" ? " prins" : (RAU[s.faza] ? " rau" : (ASTEPTARE[s.faza] ? " asteapta" : "")));
  procent("nivel", "baraNivel", s.nivel_la_suta);
  procent("calitate", "baraCalitate", s.calitate_la_suta);
  var l = $("linii"); goleste(l);
  if(s.blocat !== undefined && s.faza !== "oprita"){ linie(l, "Blocat", s.blocat ? "da" : "nu"); }
  linie(l, "BER", s.ber);
  linie(l, "Antena", s.pozitie_text);
  linie(l, "Transponder", s.tp_text);
  if(s.tsid_text){ linie(l, "TS ID", s.tsid_text); }
  if(s.onid_text){ linie(l, "ON ID", s.onid_text); }
  if(s.varf_calitate_10s !== null && s.varf_calitate_10s !== undefined){ linie(l, "Cea mai bună calitate (10 s)", s.varf_calitate_10s + "%"); }
  if(s.incercari > 1){ linie(l, "Încercări", s.incercari); }
  var d = $("detalii"); goleste(d);
  (s.detalii || []).forEach(function(x){ d.appendChild(el("li", "", x)); });
  $("eveniment").textContent = s.eveniment || "";
  var web = aWebului();
  var comenzi = !!CFG.csrf && !s.ecran_deschis;
  $("masoara").textContent = web ? "Măsoară acest transponder" : "Pornește măsurarea";
  $("masoara").disabled = !comenzi;
  $("reacord").disabled = !comenzi || !web;
  $("opreste").disabled = !comenzi || !web;
  if(s.ecran_deschis){ mesaj($("mesaj"), "Găsirea semnalului e deschisă pe televizor. De aici se vede măsurarea de acolo."); }
}
function planifica(ms){
  if(S.ceas){ clearTimeout(S.ceas); }
  S.ceas = setTimeout(citeste, ms);
}
function citeste(){
  S.ceas = null;
  cerere("/api/gasire-semnal-stare").then(function(s){
    if(s.result){ deseneazaStarea(s); }
    planifica(document.hidden ? 5000 : 500);
  }).catch(function(){ planifica(3000); });
}

$("tuner").addEventListener("change", function(){ puneSistemele(); puneSatelitii(null); incarcaTranspondere().then(laSchimbare); });
$("satelit").addEventListener("change", function(){ incarcaTranspondere().then(laSchimbare); });
$("transponder").addEventListener("change", function(){
  arata($("manual"), $("transponder").value === "manual");
  if($("transponder").value === "manual" && S.lista && S.lista.length && S.stare && S.stare.tp){ umpleManual(S.stare.tp); }
  laSchimbare();
});
["frecventa", "sr"].forEach(function(id){ $(id).addEventListener("input", laSchimbare); });
["pol", "mod", "fec1", "fec2", "rolloff", "pilot"].forEach(function(id){ $(id).addEventListener("change", laSchimbare); });
$("sistem").addEventListener("change", function(){ arataSistemul(); laSchimbare(); });
$("masoara").addEventListener("click", masoara);
$("reacord").addEventListener("click", function(){ trimite("/api/gasire-semnal-reacordeaza"); });
$("opreste").addEventListener("click", function(){
  if(S.stare && S.stare.iesirea_opreste_antena){
    intreaba($("intrebare"), "Antena se rotește încă. Dacă oprești acum, motorul se oprește din drum, iar antena merge unde trebuie la următorul canal de satelit. Oprești măsurarea?",
      "Da, opresc", "Nu", function(){ trimite("/api/gasire-semnal-opreste"); });
    return;
  }
  trimite("/api/gasire-semnal-opreste");
});
// la inchiderea paginii masurarea se opreste si programul porneste la loc (altfel ar ramane oprit pana la 30 s)
window.addEventListener("pagehide", function(){
  if(CFG.csrf && aWebului()){ cerere("/api/gasire-semnal-opreste", "POST", new URLSearchParams(), true).catch(function(){}); }
});
document.addEventListener("visibilitychange", function(){ if(!document.hidden){ planifica(0); } });

function porneste(){
  cerere("/api/gasire-semnal").then(function(d){
    if(!d.result){ $("subtitlu").textContent = d.message || "Tunerele nu se pot citi."; return; }
    S.date = d;
    if(!d.tunere.length){
      $("subtitlu").textContent = "Receptorul nu are niciun tuner de satelit, deci aici nu se poate măsura semnalul.";
      return;
    }
    $("subtitlu").textContent = d.initial && d.initial.din === "program" ? "Pornește de la transponderul programului de pe televizor." : "";
    arata($("cardAlegere"), true);
    arata($("randTuner"), d.tunere.length > 1);
    var slot = d.initial ? d.initial.slot : d.tunere[0].slot;
    optiuni($("tuner"), d.tunere.map(function(t){ return [t.slot, t.nume]; }), slot);
    puneListe();
    puneSistemele();
    if(d.initial){
      puneSatelitii(d.initial.tp.orbital_position);
      puneTranspondere(d.initial, d.initial.tp);
    } else {
      puneSatelitii(null);
      incarcaTranspondere();
    }
    if(!CFG.csrf){ mesaj($("mesaj"), "Măsurarea se pornește numai dintr-un browser conectat cu codul de pe televizor. Aici se vede starea."); }
    deseneazaStarea(d.stare);
    planifica(500);
  }).catch(function(){ $("subtitlu").textContent = "Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."; });
}
porneste();
</script>
</body>
</html>
"""


# ------------------------------------------------------------------ Rotirea antenei
# Afisajul e cel de pana acum (mutat aici din plugin.py, neschimbat la desen), cu trei reparatii:
# cand pozitia nu se stie (dupa o mutare de mana sau o oprire pe drum) antena nu se mai
# deseneaza pe plecare si nici pe tinta, iar celula „Acum” spune de ce; cartela nu se face verde cand motorul a fost
# oprit (numai la o sosire adevarata); „Oprire singură în” cat merge o comanda cu plafon. Sub afisaj sunt comenzile, in
# aceeasi ordine si cu aceleasi reguli ca banda ecranului de pe televizor.
# Desenul: acelasi ca pe televizor (Screens/HdsDishMotor.py), cu aceleasi cifre;
# satelitii vin din `sateliti` al starii (numai orbital si grade), iar gradele de langa puncte sunt scrise din cifre.
PAGINA_MOTOR = """<!DOCTYPE html>
<html lang="ro">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rotirea antenei</title>
<style>__STIL_COMUN__""" + _STIL_PAGINI + """
  svg{width:100%;height:auto;display:block;}
  .randuri{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px;}
  @media(max-width:520px){.randuri{grid-template-columns:1fr;}}
  .celula{text-align:center;min-width:0;}
  .eticheta-mica{color:var(--text-slab);font-size:.75rem;text-transform:uppercase;letter-spacing:.04em;}
  .valoare{font-size:1.05rem;margin-top:3px;overflow-wrap:anywhere;}
  .sat{color:var(--text-slab);font-size:.85rem;}
  .celula.plecare .valoare{color:#b99cff;} .celula.acum .valoare{color:#38b6ff;} .celula.tinta .valoare{color:#ffc250;}
  .bara{height:14px;border-radius:7px;background:#1b2836;overflow:hidden;margin-top:14px;}
  .bara span{display:block;height:100%;width:0;background:#2f6fa8;transition:width .25s linear;}
  .ajuns .bara span{background:var(--verde);}
  .ramas{text-align:center;margin-top:10px;font-size:.95rem;}
  .detaliu{text-align:center;margin-top:6px;color:var(--text-slab);font-size:.78rem;overflow-wrap:anywhere;}
  .gol{color:var(--text-slab);font-size:.9rem;margin:0;}
  #titlu{color:var(--text-slab);text-transform:uppercase;letter-spacing:.04em;font-size:.95rem;}
  .oprire{width:100%;min-height:56px;font-size:1.1rem;font-weight:600;}
  .oprire.misca{box-shadow:0 0 0 3px #ffb4a8;}
  .pasi{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center;margin-top:12px;}
  .marime{display:flex;align-items:center;gap:6px;}
  .marime .buton{min-width:44px;padding:10px 0;}
  .marime span{min-width:4.5em;text-align:center;font-size:.9rem;}
  @media(max-width:420px){.pasi{grid-template-columns:1fr 1fr;} .marime{grid-column:1 / span 2;grid-row:2;justify-content:center;}}
  .stare-comenzi{font-size:.9rem;line-height:1.5;}
  .limite-oprite{color:#ff8f7f;font-weight:600;}
  .limite-stare{font-size:.9rem;line-height:1.5;margin:4px 0 8px;padding:8px 10px;border-left:3px solid #38b6ff;background:rgba(56,182,255,.06);}
  .limite-stare.oprite{border-left-color:#ff8f7f;}
  .limite-stare p{margin:0;}
  .limite-stare .nota{margin-top:4px;}
</style>
</head>
<body>
<main>
<h1>Rotirea antenei</h1>
<p class="subtitlu" id="subtitlu"></p>
<div class="card" id="cutie">
  <h2 id="titlu">Se încarcă...</h2>
  <div id="continut"><p class="gol">Se citește starea motorului...</p></div>
</div>

<div class="card" id="cardComenzi">
  <h2>Comenzi</h2>
  <p class="mesaj" id="motivMotor"></p>
  <div id="comenzi" class="ascuns">
    <div id="randTunerMotor">
      <label class="eticheta" for="tunerMotor">Tunerul cu motor</label>
      <select id="tunerMotor"></select>
    </div>
    <div class="stare-comenzi" id="stareComenzi"></div>
    <div class="stare-comenzi" id="limite"></div>
    <div class="mesaj avert" id="mesajMotor" role="status"></div>
    <div class="stare-comenzi" id="semnalMotor"></div>
    <div class="butoane"><button type="button" class="buton rosu oprire" id="oprire">Oprește motorul</button></div>
    <div class="pasi">
      <button type="button" class="buton secundar" id="pasVest">Pas spre vest</button>
      <div class="marime">
        <button type="button" class="buton secundar" id="pasMic" aria-label="Pas mai mic">-</button>
        <span id="pas">Pas: 1</span>
        <button type="button" class="buton secundar" id="pasMare" aria-label="Pas mai mare">+</button>
      </div>
      <button type="button" class="buton secundar" id="pasEst">Pas spre est</button>
    </div>
    <div class="butoane">
      <button type="button" class="buton secundar" id="contVest">Mișcare spre vest</button>
      <button type="button" class="buton secundar" id="contEst">Mișcare spre est</button>
    </div>
    <p class="nota">Mișcarea fără oprire merge până la a doua apăsare, până la Oprește motorul sau până la oprirea singură. Cât se mișcă motorul, orice comandă doar îl oprește.</p>

    <h3>Mergi la satelit</h3>
    <select id="satelitMotor" aria-label="Satelitul"></select>
    <p class="nota" id="usals"></p>
    <p class="nota"><a id="legaturaLoc" href="/antena/locul">Schimbă locul antenei</a></p>
    <div class="butoane"><button type="button" class="buton" id="mergiSatelit">Mergi la satelit</button></div>

    <h3>Poziții memorate</h3>
    <label class="eticheta" for="pozitie">Numărul poziției (1-255)</label>
    <input class="text" id="pozitie" inputmode="numeric" value="1">
    <div class="butoane">
      <button type="button" class="buton secundar" id="laPozitie">Mergi la poziția memorată</button>
      <button type="button" class="buton secundar" id="memoreaza">Memorează aici poziția</button>
      <button type="button" class="buton secundar" id="laZero">Mergi la poziția 0 (referința motorului)</button>
    </div>

    <h3>Limite</h3>
    <div class="limite-stare" id="limiteStare" role="status"></div>
    <p class="nota">Comenzile de mai jos se trimit motorului; starea de deasupra se schimbă după ce pleacă.</p>
    <div class="butoane">
      <button type="button" class="buton secundar" id="limitaEst">Limita de est este aici</button>
      <button type="button" class="buton secundar" id="limitaVest">Limita de vest este aici</button>
      <button type="button" class="buton secundar" id="limitePornite">Pornește limitele</button>
      <button type="button" class="buton rosu" id="limiteOprite">Oprește limitele (periculos)</button>
    </div>
    <div class="intrebare ascuns" id="intrebareMotor"></div>

    <div class="butoane"><button type="button" class="buton secundar" id="termina">Termină și dă tunerul înapoi</button></div>
    <p class="nota" id="notaProgram"></p>
  </div>
</div>

""" + _SUBSOL + """
</main>
<script>""" + _JS_COMUN + """
// Acelasi desen ca pe televizor (Screens/HdsDishMotor.py: deseneazaRotirea si deseneazaFaraTinta), in SVG, cu aceleasi
// cifre: satelitii sunt puncte pe bolta, plecarea (violet) si tinta (aurie) mai mari si cu gradele langa ele, antena
// lata sta in centru si se roteste, raza semnalului e un con ascutit la satelit si lat la antena. Unghiurile ca in
// eCanvas si ca in SVG: grade, 0 = dreapta, pozitiv = in sensul acelor de ceas pe ecran (180 = vest/stanga, 270 = sus,
// 360 = est/dreapta). In SVG intra numai cifre si etichetele gradelor scrise de receptor (scapate): niciun nume.
const CX = 430, CY = 192, RAZA = 156, MARGINE = 4;
const TALER_DEPARTE = 16, TALER_RAZA = 40, TALER_DESCHIDERE = 50, TALER_GROS = 8, ETICHETA_L = 86, ETICHETA_I = 24;
const C = {fond: "#101820", arc: "#2d4356", facut: "#38b6ff", satelit: "#6f8ba3", plecare: "#b99cff", tinta: "#ffc250",
  antena: "#f2f6fa", brat: "#bfd4e6"};
// raza semnalului, doua straturi: [culoare, opacitate]; pe televizor octetul de sus e transparenta (C0 = 0,25 opac)
const CON_MERS = [["#38b6ff", 0.25], ["#38b6ff", 0.44]], CON_SOSIT = [["#ffc250", 0.28], ["#ffc250", 0.5]];
const z = v => v.toFixed(2);
function pe(unghi, raza, cx, cy){
  const a = unghi * Math.PI / 180;
  return [(cx === undefined ? CX : cx) + raza * Math.cos(a), (cy === undefined ? CY : cy) + raza * Math.sin(a)];
}
function drumArc(cx, cy, raza, de_la, pana_la){
  const [x0, y0] = pe(de_la, raza, cx, cy), [x1, y1] = pe(pana_la, raza, cx, cy);
  return `M ${z(x0)} ${z(y0)} A ${z(raza)} ${z(raza)} 0 ${pana_la - de_la > 180 ? 1 : 0} 1 ${z(x1)} ${z(y1)}`;
}
function arcSvg(cx, cy, raza, de_la, pana_la, culoare, gros){
  return `<path d="${drumArc(cx, cy, raza, de_la, pana_la)}" fill="none" stroke="${culoare}" stroke-width="${gros}" stroke-linecap="round"/>`;
}
function linieSvg(a, b, culoare, gros){
  return `<line x1="${z(a[0])}" y1="${z(a[1])}" x2="${z(b[0])}" y2="${z(b[1])}" stroke="${culoare}" stroke-width="${gros}" stroke-linecap="round"/>`;
}
function cercSvg(p, r, culoare){ return `<circle cx="${z(p[0])}" cy="${z(p[1])}" r="${r}" fill="${culoare}"/>`; }
function poligonSvg(puncte, culoare, opac){
  const o = opac === undefined ? "" : ` fill-opacity="${opac}"`;
  return `<polygon points="${puncte.map(q => z(q[0]) + "," + z(q[1])).join(" ")}" fill="${culoare}"${o}/>`;
}
// etichetele gradelor vin de la receptor (HdsMotorStare.stareJson: la_scurt, de_la_scurt), aceleasi ca pe televizor
// (Screens/HdsDishMotor.py, gradeScurt), in limba meniului: „19,2°E”, „5.0°W”; pagina nu le mai scrie singura
function scapat(t){
  return String(t === undefined || t === null ? "" : t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
// eticheta punctului de la `unghi`: lipita de bolta pe dinafara, spre stanga la vest, spre dreapta la est, centrata sus
function cutieEticheta(unghi){
  const [x, y] = pe(unghi, RAZA + 13), c = Math.cos(unghi * Math.PI / 180), s = Math.sin(unghi * Math.PI / 180);
  const stanga = Math.min(Math.max(0, x + c * ETICHETA_L / 2 - ETICHETA_L / 2), 860 - ETICHETA_L);
  const sus = Math.min(Math.max(0, y + s * ETICHETA_I / 2 - ETICHETA_I / 2), 250 - ETICHETA_I);
  return [stanga, sus, c < -0.3 ? "end" : (c > 0.3 ? "start" : "middle")];
}
function seSuprapun(a, b){
  return !(a[0] + ETICHETA_L + 4 <= b[0] || b[0] + ETICHETA_L + 4 <= a[0] || a[1] + ETICHETA_I + 4 <= b[1] || b[1] + ETICHETA_I + 4 <= a[1]);
}
function etichetaSvg(cutie, culoare, text){
  const x = cutie[2] === "end" ? cutie[0] + ETICHETA_L : (cutie[2] === "start" ? cutie[0] : cutie[0] + ETICHETA_L / 2);
  return `<text x="${z(x)}" y="${z(cutie[1] + ETICHETA_I / 2)}" fill="${culoare}" font-size="19" text-anchor="${cutie[2]}" dominant-baseline="central">${text}</text>`;
}
// antena rotita spre `unghi`: stalpul si talpa (fixe), bratul, talerul lat, bratul LNB-ului si sarmele, LNB-ul, butucul
function antenaSvg(unghi){
  const a = unghi * Math.PI / 180, ux = Math.cos(a), uy = Math.sin(a), nx = -uy, ny = ux;
  let s = linieSvg([CX, CY], [CX, CY + 26], C.brat, 6);
  s += poligonSvg([[CX - 20, CY + 32], [CX + 20, CY + 32], [CX + 9, CY + 22], [CX - 9, CY + 22]], C.brat);
  const v = [CX + TALER_DEPARTE * ux, CY + TALER_DEPARTE * uy], f = [v[0] + TALER_RAZA * ux, v[1] + TALER_RAZA * uy];
  s += linieSvg([CX, CY], v, C.brat, 6);
  s += arcSvg(f[0], f[1], TALER_RAZA, unghi + 180 - TALER_DESCHIDERE, unghi + 180 + TALER_DESCHIDERE, C.antena, TALER_GROS);
  const focar = [v[0] + TALER_RAZA / 2 * ux, v[1] + TALER_RAZA / 2 * uy];
  s += linieSvg(v, focar, C.brat, 2.5);
  for (const semn of [-1, 1])
    s += linieSvg(pe(unghi + 180 + semn * (TALER_DESCHIDERE - 5), TALER_RAZA, f[0], f[1]), focar, C.brat, 1.4);
  s += poligonSvg([[-4, -5], [3, -5], [5, -3], [5, 3], [3, 5], [-4, 5]]
    .map(([l, t]) => [focar[0] + l * ux + t * nx, focar[1] + l * uy + t * ny]), C.tinta);
  s += cercSvg([CX, CY], 8, C.antena) + `<circle cx="${CX}" cy="${CY}" r="11.5" fill="none" stroke="${C.facut}" stroke-width="2"/>`;
  return s;
}
function deseneaza(d){
  let s = `<rect width="860" height="250" rx="8" fill="${C.fond}"/>`;
  if (d.la_grade === null) {
    // tinta nu se stie (pas, miscare fara oprire): bolta goala si sageata directiei; nicio antena, niciun satelit
    s += arcSvg(CX, CY, RAZA, 180, 360, C.arc, 4);
    if (d.directie === "est" || d.directie === "vest") {
      const semn = d.directie === "est" ? 1 : -1, r = RAZA * 0.62, inceput = 270 - semn * 32, capat = 270 + semn * 32;
      s += arcSvg(CX, CY, r, Math.min(inceput, capat), Math.max(inceput, capat), C.facut, 7);
      s += poligonSvg([pe(capat + semn * 9, r), pe(capat - semn, r - 12), pe(capat - semn, r + 12)], C.facut);
    }
    return `<svg viewBox="0 0 860 250" role="img" aria-label="Antena și drumul ei">${s}</svg>`;
  }
  const plecare = d.de_la_grade !== null, de_la = plecare ? d.de_la_grade : d.la_grade, la = d.la_grade;
  const jos = Math.min(de_la, la) - MARGINE, sus = Math.max(de_la, la) + MARGINE;
  const u = g => 180 + 180 * Math.min(1, Math.max(0, sus <= jos ? 0.5 : (g - jos) / (sus - jos)));
  // pozitia nu se stie (o mutare de mana, o oprire pe drum, plecarea necunoscuta): antena si raza nu se deseneaza
  const stiuta = d.pozitie_grade !== null, uDeLa = u(de_la), uLa = u(la), uAcum = u(stiuta ? d.pozitie_grade : de_la);
  if (stiuta) {
    // raza semnalului: varful pe bolta, unde e indreptata antena, baza pe gura talerului; aurie cand a ajuns pe tinta
    const f = pe(uAcum, TALER_DEPARTE + TALER_RAZA), varf = pe(uAcum, RAZA);
    const straturi = d.a_ajuns && !d.manual ? CON_SOSIT : CON_MERS;
    [TALER_DESCHIDERE, TALER_DESCHIDERE * 0.45].forEach((deschidere, i) => {
      s += poligonSvg([varf, pe(uAcum + 180 - deschidere, TALER_RAZA, f[0], f[1]), pe(uAcum + 180 + deschidere, TALER_RAZA, f[0], f[1])],
        straturi[i][0], straturi[i][1]);
    });
  }
  // bolta: tot drumul subtire, apoi bucata facuta, mai groasa si aprinsa
  s += arcSvg(CX, CY, RAZA, 180, 360, C.arc, 4);
  const mic = Math.min(uDeLa, uAcum), mare = Math.max(uDeLa, uAcum);
  if (stiuta && plecare && mare - mic > 0.05) s += arcSvg(CX, CY, RAZA, mic, mare, C.facut, 6);
  // ceilalti sateliti ai tunerului: puncte de alta culoare decat bolta, putin mai groase decat ea
  for (const sat of (d.sateliti || []))
    if (sat.orbital !== d.de_la_orbital && sat.orbital !== d.la_orbital && sat.grade >= jos && sat.grade <= sus)
      s += cercSvg(pe(u(sat.grade), RAZA), 4.5, C.satelit);
  // plecarea (violet) si tinta (aurie, cu un inel in jur), mai mari decat punctele obisnuite
  if (plecare) s += cercSvg(pe(uDeLa, RAZA), 6.5, C.plecare);
  const t = pe(uLa, RAZA);
  s += `<circle cx="${z(t[0])}" cy="${z(t[1])}" r="11" fill="none" stroke="${C.tinta}" stroke-opacity="0.5" stroke-width="1.6"/>` + cercSvg(t, 7, C.tinta);
  if (stiuta) s += antenaSvg(uAcum);
  // gradele plecarii si ale tintei; cand plecarea e prea aproape de tinta ramane numai eticheta tintei
  const cutieLa = cutieEticheta(uLa);
  s += etichetaSvg(cutieLa, C.tinta, scapat(d.la_scurt));
  if (plecare) {
    const cutieDeLa = cutieEticheta(uDeLa);
    if (!seSuprapun(cutieDeLa, cutieLa)) s += etichetaSvg(cutieDeLa, C.plecare, scapat(d.de_la_scurt));
  }
  return `<svg viewBox="0 0 860 250" role="img" aria-label="Antena și drumul ei">${s}</svg>`;
}
// o zecimala mereu, ca pe televizor („%.1f”): „17,0 grade”, nu „17 grade”
function nr(x){ return (Math.round(x * 10) / 10).toFixed(1).replace(".", ","); }
function celula(eticheta, valoare, sat, fel){
  const c = el("div", "celula" + (fel ? " " + fel : ""));
  c.appendChild(el("div", "eticheta-mica", eticheta));
  c.appendChild(el("div", "valoare", valoare));
  c.appendChild(el("div", "sat", sat || ""));
  return c;
}
// readucerea antenei dupa pierderea semnalului (HdsMotorPozitie.stareReaducere, in /api/motor): numai aici, nu pe televizor
function notaReaducere(d){
  const r = d.readucere || {};
  if (!r.activa) return "";
  const unde = r.sat_text || "satelitul canalului";
  // verificarea pe alt transponder al aceluiasi satelit, inaintea oricarei rotiri (fara comanda spre motor)
  if (r.verificare) return "Fără semnal pe " + unde + ": se verifică alt transponder al satelitului (" + r.verificare.tp_text + ", " + r.verificare.referinta + " din " + r.verificare.referinte + "), fără rotirea antenei.";
  if (r.la_loc) {
    let t = "Antena e la locul ei pe " + unde + ": se recepționează " + r.la_loc.tp_text + ". Transponderul canalului nu emite acum, deci antena nu se rotește";
    if (r.urmatoarea_s !== null && r.urmatoarea_s !== undefined) t += "; următoarea verificare peste " + secunde(r.urmatoarea_s);
    return t + ".";
  }
  if (r.in_curs && r.ocolire) {
    // ocolirea: prin alt satelit, apoi inapoi (HdsMotorPozitie, stareReaducere)
    const prin = r.ocolire.prin_text || "altă poziție";
    if (r.ocolire.faza === "inapoi") return "Readucerea antenei pe " + unde + " după pierderea semnalului: încercarea " + r.incercari + ", prin " + prin + "; antena se întoarce pe " + unde + ".";
    return "Readucerea antenei pe " + unde + " după pierderea semnalului: încercarea " + r.incercari + ", prin " + prin + ", în curs.";
  }
  if (r.in_curs) return "Readucerea antenei pe " + unde + " după pierderea semnalului: încercarea " + r.incercari + ", în curs.";
  const u = r.ultima || {};
  if (r.semnal_revenit) {
    let t = "Semnalul a revenit pe " + unde + " după readucerea antenei (încercarea " + r.incercari + ")";
    if (u.dupa_ms !== undefined && u.dupa_ms >= 0) t += ", la " + secunde(Math.round(u.dupa_ms / 1000));
    return t + ".";
  }
  let t = "Fără semnal pe " + unde + " de " + secunde(r.fara_semnal_s) + "; încercări de readucere a antenei: " + r.incercari;
  if (r.urmatoarea_s !== null && r.urmatoarea_s !== undefined) t += ", următoarea peste " + secunde(r.urmatoarea_s);
  return t + ".";
}
function afiseaza(d){
  const titlu = $("titlu"), continut = $("continut");
  // verde numai la o sosire adevarata; dupa o oprire (manual) miscarea s-a terminat, dar antena nu a ajuns nicaieri stiut;
  // dupa timpul maxim fara semnal (fara_semnal_la_sosire) nu se stie nici ca a ajuns
  $("cutie").className = "card" + (d.a_ajuns && !d.manual && !d.fara_semnal_la_sosire ? " ajuns" : "");
  goleste(continut);
  if (!d.activ){
    titlu.textContent = "Antena nu se rotește";
    continut.appendChild(el("p", "gol", "Când receptorul mută antena spre alt satelit, aici se vede drumul ei, gradele și cât mai are de mers."));
    const c = d.comenzi || {};
    if (c.pozitie_stiuta !== undefined && c.pozitie_stiuta >= 0 && S.pozitii[c.pozitie_stiuta])
      continut.appendChild(el("p", "nota", "Antena e pe " + S.pozitii[c.pozitie_stiuta] + "."));
    if (notaReaducere(d)) continut.appendChild(el("p", "nota", notaReaducere(d)));
    $("subtitlu").textContent = "";
    return;
  }
  // textul vine de la receptor (HdsMotorStare._textStare); cand lipseste nu se spune nimic despre miscare
  titlu.textContent = d.stare_text || "Rotirea antenei";
  continut.insertAdjacentHTML("beforeend", deseneaza(d));
  const randuri = el("div", "randuri");
  randuri.appendChild(celula("De la", d.de_la_text, d.de_la_nume, "plecare"));
  randuri.appendChild(celula("Acum (estimat)", d.pozitie_grade === null ? (d.curent_text || d.pozitie_text) : d.pozitie_text, "", "acum"));
  randuri.appendChild(celula("Până la", d.la_text, d.la_nume, "tinta"));
  continut.appendChild(randuri);
  const proc = d.procent < 0 ? 0 : d.procent;
  const bara = el("div", "bara"), plin = el("span");
  plin.style.width = proc + "%";
  bara.appendChild(plin);
  continut.appendChild(bara);
  // plecarea nestiuta sau timpul maxim trecut fara semnal: randul vine gata de la receptor, ca pe televizor
  if (d.ramas_text && !d.manual) continut.appendChild(el("div", "ramas", d.ramas_text));
  else if (d.a_ajuns) continut.appendChild(el("div", "ramas", d.stare_text));
  else if (d.grade_ramase === null) continut.appendChild(el("div", "ramas", "Motorul merge, timpul nu se poate estima"));
  // timpul prezis a trecut: nici „0 s”, nici un timp inventat (acelasi text ca pe televizor)
  else if (d.intarziat || d.secunde_ramase === null || d.secunde_ramase === undefined)
    continut.appendChild(el("div", "ramas", "Aproape gata, se așteaptă semnalul pe satelitul nou"));
  else continut.appendChild(el("div", "ramas", `Mai are de mers ${nr(d.grade_ramase)} grade, aproximativ ${secunde(d.secunde_ramase)}`));
  if (d.oprire_automata_s !== null && d.oprire_automata_s !== undefined && !d.a_ajuns)
    continut.appendChild(el("div", "ramas", "Oprire singură în " + secunde(d.oprire_automata_s)));
  const det = [];
  if (d.comanda_text) det.push("comanda " + d.comanda_text);
  if (d.unghi_motor !== null) det.push("unghi motor " + nr(Math.abs(d.unghi_motor)) + " grade " + (d.unghi_motor >= 0 ? "Est" : "Vest"));
  // gradele de motor (unghiul orar USALS) cand se stiu coordonatele, altfel diferenta pozitiilor orbitale
  if (d.grade_total !== null) det.push((d.unghi_real ? "rotire " : "drum total ") + nr(d.grade_total) + " grade");
  det.push("tuner " + (d.slot + 1));
  continut.appendChild(el("div", "detaliu", det.join("   |   ")));
  // viteza motorului: presupusa pana la prima mutare masurata, apoi invatata din mutarile lui (acelasi text ca pe televizor)
  if (d.viteza_text) continut.appendChild(el("div", "detaliu viteza", d.viteza_text));
  // ultimul semnal prins de acest receptor pe pozitia tinta (istoricul semnalului), acelasi rand ca pe televizor
  if (d.istoric_text) continut.appendChild(el("div", "detaliu", d.istoric_text));
  if (notaReaducere(d)) continut.appendChild(el("div", "detaliu", notaReaducere(d)));
  $("subtitlu").textContent = "Poziția din timpul mersului este estimată: motorul nu o raportează.";
}

// ---- comenzile: aceleasi functii ca tastele ecranului de pe televizor (Components/HdsMotorComenzi.py)
var S = {info: null, comenzi: {}, pozitii: {}, bataie: 0, trimis: false};
const MISCARE = ["misca_manual", "misca_nucleu", "trimite", "oprire"];

function slotAles(){ return $("tunerMotor").value || (S.info ? String(S.info.slot) : ""); }
function incarcaInfo(){
  const slot = slotAles();
  return cerere("/api/motor-comenzi" + (slot !== "" ? "?slot=" + encodeURIComponent(slot) : "")).then(function(d){
    if (!d.result) return;
    S.info = d;
    optiuni($("tunerMotor"), d.tunere.map(t => [t.slot, t.nume]), d.slot);
    arata($("randTunerMotor"), d.tunere.length > 1);
    const ales = $("satelitMotor").value;
    optiuni($("satelitMotor"), d.sateliti.map(s => [s.orbital, s.text]), ales !== "" ? ales : (d.curent !== null ? d.curent : ""));
    S.pozitii = {};
    d.sateliti.forEach(s => { S.pozitii[s.orbital] = s.text; });
    // fara locul antenei „Mergi la satelit” nu porneste (motorul USALS calculeaza unghiul din el)
    $("usals").textContent = d.loc_nestabilit ? "Locul antenei nu e stabilit, deci „Mergi la satelit” nu pornește. Alege-l mai întâi." : (d.usals || "");
    $("usals").classList.toggle("eroare", !!d.loc_nestabilit);
    deseneazaComenzile(d.comenzi || {});
  }).catch(function(){});
}
function deseneazaComenzile(c){
  S.comenzi = c;
  const info = S.info;
  if (!info) return;
  if (info.motiv){
    mesaj($("motivMotor"), info.motiv);
    arata($("comenzi"), false);
    return;
  }
  if (!CFG.csrf){
    mesaj($("motivMotor"), "Comenzile motorului se dau numai dintr-un browser conectat cu codul de pe televizor. Aici se vede numai rotirea.");
    arata($("comenzi"), false);
    return;
  }
  mesaj($("motivMotor"), info.ecran_deschis || c.stapan === "ecran" ? "Ecranul „Rotirea antenei” e deschis și pe televizor: comenzile de acolo și de aici merg la același motor." : "");
  arata($("comenzi"), true);
  // oprirea singura se vede in afisajul de sus, langa drum
  $("stareComenzi").textContent = "Tunerul " + c.tuner + " are motor   |   Pas: " + c.pas;
  $("pas").textContent = "Pas: " + c.pas;
  // starea limitelor: ce a trimis acest receptor (motorul nu o raporteaza), aceleasi texte ca pe televizor
  const lt = c.limite_texte || {};
  const oprite = (c.limite_stare || c.limite) === "oprite";
  const lim = $("limite");
  lim.className = "stare-comenzi" + (oprite ? " limite-oprite" : "");
  lim.textContent = lt.stare || (oprite ? "Limitele sunt oprite. Pornesc singure la ieșire." :
    (c.limite === "pornite" ? "Limite: pornite" : "Limite: nu se știe"));
  const ls = $("limiteStare");
  ls.className = "limite-stare" + (oprite ? " oprite" : "");
  ls.textContent = "";
  // numai randul starii e rosu cand limitele sunt oprite; est, vest si nota raman obisnuite
  [lt.stare, lt.est, lt.vest].forEach(function(t, i){ if (t) ls.appendChild(el("p", i === 0 && oprite ? "limite-oprite" : "", t)); });
  if (lt.nota) ls.appendChild(el("p", "nota", lt.nota));
  let text = c.motiv || "";
  if (text && !c.eroare && c.motiv_de_acum_s !== null && c.motiv_de_acum_s > 8 && c.stare !== "misca_nucleu") text = "";
  if (c.lacat_proba) text = "Mod de probă: se pot trimite numai oprirea și pornirea limitelor.";
  const m = $("mesajMotor");
  m.textContent = text;
  m.className = "mesaj " + (c.eroare ? "eroare" : "avert");
  $("semnalMotor").textContent = textSemnal(c);
  const misca = MISCARE.indexOf(c.stare) !== -1;
  $("oprire").classList.toggle("misca", misca);
  $("termina").disabled = !c.tuner_luat || c.stapan !== "web";
  $("notaProgram").textContent = c.tuner_luat ? "" : "La prima comandă programul de pe televizor se oprește; pornește la loc când apeși Termină sau închizi pagina.";
}
function textSemnal(c){
  if (!c.tuner_luat) return "";
  const s = c.semnal, loc = ((c.referinta_satelit || "") + "  " + (c.referinta || "")).trim();
  if (!s) return "";
  if (!s.citit) return "Semnalul nu se poate citi pe acest tuner.";
  if (s.prins) return s.calitate !== null && s.calitate !== undefined ? "Semnal pe " + loc + ": recepționat, calitate " + s.calitate + " %" : "Semnal pe " + loc + ": recepționat";
  return "Semnal pe " + loc + ": fără semnal";
}
function comanda(actiune, extra, laInchidere){
  const p = new URLSearchParams();
  p.set("actiune", actiune);
  const slot = slotAles();
  if (slot !== "") p.set("slot", slot);
  Object.keys(extra || {}).forEach(k => p.set(k, String(extra[k])));
  return cerere("/api/motor-comanda", "POST", p, laInchidere).then(function(d){
    if (laInchidere) return d;
    if (d.intrebare){
      intreaba($("intrebareMotor"), d.intrebare, "Da", "Nu", function(){
        comanda(actiune, Object.assign({}, extra || {}, {confirmat: "1"}));
      });
      return d;
    }
    if (d.message) { const m = $("mesajMotor"); m.textContent = d.message; m.className = "mesaj " + (d.result ? "avert" : "eroare"); }
    if (d.comenzi) deseneazaComenzile(d.comenzi);
    return d;
  }).catch(function(){ if (!laInchidere) mesaj($("mesajMotor"), "Receptorul nu răspunde.", true); });
}
function pozitieScrisa(){
  const t = $("pozitie").value.trim();
  const n = /^[0-9]+$/.test(t) ? parseInt(t, 10) : 0;
  if (n < 1 || n > 255){ mesaj($("mesajMotor"), "Poziția trebuie să fie un număr între 1 și 255.", true); return null; }
  return n;
}
$("oprire").addEventListener("click", () => comanda("opreste"));
$("pasVest").addEventListener("click", () => comanda("pas", {est: 0}));
$("pasEst").addEventListener("click", () => comanda("pas", {est: 1}));
$("pasMic").addEventListener("click", () => comanda("marime", {delta: -1}));
$("pasMare").addEventListener("click", () => comanda("marime", {delta: 1}));
$("contVest").addEventListener("click", () => comanda("continuu", {est: 0}));
$("contEst").addEventListener("click", () => comanda("continuu", {est: 1}));
$("mergiSatelit").addEventListener("click", () => { if ($("satelitMotor").value !== "") comanda("la_satelit", {orbital: $("satelitMotor").value}); });
$("laPozitie").addEventListener("click", () => { const n = pozitieScrisa(); if (n) comanda("la_pozitie", {pozitie: n}); });
$("memoreaza").addEventListener("click", () => { const n = pozitieScrisa(); if (n) comanda("memoreaza", {pozitie: n}); });
$("laZero").addEventListener("click", () => comanda("la_referinta"));
$("limitaEst").addEventListener("click", () => comanda("limita_est"));
$("limitaVest").addEventListener("click", () => comanda("limita_vest"));
$("limitePornite").addEventListener("click", () => comanda("limite_pornite"));
$("limiteOprite").addEventListener("click", () => comanda("limite_oprite"));
$("termina").addEventListener("click", () => comanda("elibereaza"));
$("tunerMotor").addEventListener("change", incarcaInfo);
$("legaturaLoc").href = adresa("/antena/locul");
function aWebului(){ return !!CFG.csrf && S.comenzi.tuner_luat && S.comenzi.stapan === "web"; }
// pagina ascunsa (pe telefon si cand ecranul se stinge singur, dupa ~30 s fara atingere, sau alta aplicatie): se
// opreste numai miscarea fara capat („continuu”; fara „mentine”, modulul o opreste oricum dupa 5 s). Pasii si
// drumurile spre o pozitie memorata sau spre un satelit merg pana la capat, cu plafonul lor; cu motorul oprit,
// modulul da tunerul si programul inapoi dupa 2 minute fara nicio cerere (verificarea finala, Mediu 3)
document.addEventListener("visibilitychange", function(){
  if (document.hidden){
    if (aWebului() && S.comenzi.actiune === "continuu" && MISCARE.indexOf(S.comenzi.stare) !== -1) comanda("opreste", {}, true);
  } else { incarcaInfo(); programeaza(0); }
});
// pagina inchisa: oprirea, limitele la loc, tunerul si programul inapoi (acelasi lant ca EXIT pe televizor)
window.addEventListener("pagehide", function(){ if (aWebului()) comanda("elibereaza", {}, true); });

async function citeste(){
  let d;
  try { d = await cerere("/api/motor"); }
  catch(e){ $("subtitlu").textContent = "Receptorul nu răspunde."; programeaza(); return; }
  if (d.result === false && d.message){ $("subtitlu").textContent = d.message; programeaza(); return; }
  afiseaza(d);
  if (d.comenzi) deseneazaComenzile(d.comenzi);
  // la 2 s: pagina e inca deschisa (fara asta, miscarea fara oprire se opreste dupa 5 s, iar tunerul se da
  // inapoi dupa 2 minute de tacere)
  S.bataie += 1;
  if (S.bataie % 4 === 0 && !document.hidden && aWebului()) comanda("mentine", {}, false);
  if (S.bataie % 60 === 0) incarcaInfo();
  // dupa sosire bara si antena ajung lin la capat in ~1,2 s: atunci mai des, ca pe televizor
  programeaza(d.alunecare ? 200 : undefined);
}
function programeaza(ms){ clearTimeout(S.ceas); S.ceas = setTimeout(citeste, ms === undefined ? 500 : ms); }
incarcaInfo().then(() => programeaza(0));
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- traducerea paginilor
# Textele sabloanelor de mai sus, traduse la cerere in limba receptorului (traducere_pagini.py). Un text
# nou sau schimbat in sablon se scrie si aici (proba textelor paginilor web il cere).
TEXTE_PAGINA = {
	"html": (
		N_("Locul antenei"),
		N_("Motorul USALS calculează unghiul spre fiecare satelit din locul tău. Același loc ca pe "
			"televizor."),
		N_("Acum"),
		N_("Se încarcă..."),
		N_("Află locul după internet"),
		N_("Receptorul întreabă serverul HD Satelit ce oraș arată adresa lui de internet. Locul se schimbă "
			"numai după ce îl confirmi."),
		N_("Orașul după adresa de internet: <a href=\"https://db-ip.com\" target=\"_blank\" rel=\"noopener "
			"noreferrer\">IP Geolocation by DB-IP</a>, licența CC BY 4.0. Serverul nu păstrează adresa de "
			"internet."),
		N_("Receptorul nu are internet acum: alege țara și orașul din listă."),
		N_("Țara și orașul"),
		N_("Țara"),
		N_("Orașul"),
		N_("Alege orașul cel mai apropiat: câțiva kilometri nu contează pentru unghiul antenei."),
		N_("Salvează locul"),
		N_("Coordonatele scrise de mână"),
		N_("Latitudinea (grade, nord +)"),
		N_("Longitudinea (grade, est +)"),
		N_("Cu virgulă sau punct, de exemplu 44,426 și 26,103. Sudul și vestul se scriu cu minus."),
		N_("Salvează coordonatele"),
		N_("Orientarea și setarea antenei"),
		N_("Configurare LNB"),
		N_("Rotirea antenei"),
		N_("Găsire semnal"),
		N_("Se citesc setările tunerului..."),
		N_("Tuner"),
		N_("Antena"),
		N_("Comenzi DiSEqC la 13 V"),
		N_("Probă de calcul"),
		N_("Vezi ce se schimbă"),
		N_("Renunță la schimbări"),
		N_("Ce era înainte"),
		N_("Ce se schimbă"),
		N_("Detalii"),
		N_("Aplică"),
		N_("Înapoi"),
		N_("Verificarea semnalului"),
		N_("Revin la ce era"),
		N_("Se citesc tunerele..."),
		N_("Satelit"),
		N_("Transponder"),
		N_("Frecvența (MHz)"),
		N_("Rata de simbol (kSymb/s)"),
		N_("Polarizare"),
		N_("Sistem"),
		N_("Modulație"),
		N_("Roll-off"),
		N_("Pilot"),
		N_("Pornește măsurarea"),
		N_("Acordează din nou"),
		N_("Oprește măsurarea"),
		N_("Măsurarea ia tunerul: programul de pe televizor se oprește dacă folosește același tuner și "
			"pornește la loc când oprești măsurarea sau închizi pagina."),
		N_("Nivel"),
		N_("Calitate"),
		N_("Se citește starea motorului..."),
		N_("Comenzi"),
		N_("Tunerul cu motor"),
		N_("Oprește motorul"),
		N_("Pas spre vest"),
		N_("Pas: 1"),
		N_("Pas spre est"),
		N_("Mișcare spre vest"),
		N_("Mișcare spre est"),
		N_("Mișcarea fără oprire merge până la a doua apăsare, până la Oprește motorul sau până la oprirea "
			"singură. Cât se mișcă motorul, orice comandă doar îl oprește."),
		N_("Mergi la satelit"),
		N_("Schimbă locul antenei"),
		N_("Poziții memorate"),
		N_("Numărul poziției (1-255)"),
		N_("Mergi la poziția memorată"),
		N_("Memorează aici poziția"),
		N_("Mergi la poziția 0 (referința motorului)"),
		N_("Limite"),
		N_("Comenzile de mai jos se trimit motorului; starea de deasupra se schimbă după ce pleacă."),
		N_("Limita de est este aici"),
		N_("Limita de vest este aici"),
		N_("Pornește limitele"),
		N_("Oprește limitele (periculos)"),
		N_("Termină și dă tunerul înapoi"),
		N_("Pas mai mic"),
		N_("Pas mai mare"),
		N_("Satelitul"),
	),
	"js": (
		N_("browser deconectat"),
		N_("Receptorul a răspuns neașteptat (HTTP"),
		N_("Nu"),
		N_("Da"),
		N_("Nestabilit. Până îl alegi, motorul USALS nu rotește antena spre niciun satelit; pașii, "
			"pozițiile memorate și limitele merg."),
		N_("Receptorul nu răspunde."),
		N_("Se salvează..."),
		N_("Folosește acest loc"),
		N_("Alege din listă"),
		N_("Se caută..."),
		N_("Coordonatele orașelor:"),
		N_("Locul se schimbă numai dintr-un browser conectat cu codul de pe televizor. Aici se vede numai "
			"locul de acum."),
		N_("Tipul LNB-ului"),
		N_("Oscilator jos (MHz)"),
		N_("Oscilator sus (MHz)"),
		N_("Prag de bandă (MHz)"),
		N_("Tensiune"),
		N_("Ton 22 kHz"),
		N_("Tensiune mărită (cablu lung)"),
		N_("Port DiSEqC"),
		N_("Receptorul nu are niciun tuner de satelit."),
		N_("Tunerul"),
		N_("e în modul simplu."),
		N_("e în modul avansat."),
		N_("Setările se schimbă numai dintr-un browser conectat cu codul de pe televizor."),
		N_("Setările tunerului nu se pot citi."),
		N_("Receptorul nu răspunde. Verifică dacă e pornit și în aceeași rețea."),
		N_("Ai schimbări nesalvate pe tunerul"),
		N_(". Le lași?"),
		N_("Da, le las"),
		N_("Se pregătește lista schimbărilor..."),
		N_("Nu ai schimbat nimic."),
		N_("Salvează sau renunță întâi la schimbările de pe tunerul"),
		N_("Se aplică..."),
		N_("Verificarea semnalului, tunerul"),
		N_("Schimbarea a fost pornită de pe televizor și așteaptă răspunsul acolo."),
		N_("Păstrezi noile setări? Dacă nu răspunzi, revin singur la ce era."),
		N_("Da, păstrez noile setări"),
		N_("Nu, revin la ce era ("),
		N_("Receptorul pornește din nou programul."),
		N_("Tunerul nu are niciun satelit configurat. Configurează antena în „Setări tuner”, apoi revino "
			"aici."),
		N_("Introdus de mână"),
		N_("Satelitul nu are transpondere în lista lui: scrie valorile de mână."),
		N_("Blocat"),
		N_("Antena"),
		N_("Transponder"),
		N_("Cea mai bună calitate (10 s)"),
		N_("Încercări"),
		N_("Măsoară acest transponder"),
		N_("Pornește măsurarea"),
		N_("Găsirea semnalului e deschisă pe televizor. De aici se vede măsurarea de acolo."),
		N_("Antena se rotește încă. Dacă oprești acum, motorul se oprește din drum, iar antena merge unde "
			"trebuie la următorul canal de satelit. Oprești măsurarea?"),
		N_("Da, opresc"),
		N_("Tunerele nu se pot citi."),
		N_("Receptorul nu are niciun tuner de satelit, deci aici nu se poate măsura semnalul."),
		N_("Pornește de la transponderul programului de pe televizor."),
		N_("Măsurarea se pornește numai dintr-un browser conectat cu codul de pe televizor. Aici se vede "
			"starea."),
		N_("satelitul canalului"),
		N_("Fără semnal pe"),
		N_(": se verifică alt transponder al satelitului ("),
		N_("din"),
		N_("), fără rotirea antenei."),
		N_("Antena e la locul ei pe"),
		N_(": se recepționează"),
		N_(". Transponderul canalului nu emite acum, deci antena nu se rotește"),
		N_("; următoarea verificare peste"),
		N_("altă poziție"),
		N_("Readucerea antenei pe"),
		N_("după pierderea semnalului: încercarea"),
		N_(", prin"),
		N_("; antena se întoarce pe"),
		N_(", în curs."),
		N_("Semnalul a revenit pe"),
		N_("după readucerea antenei (încercarea"),
		N_(", la"),
		N_("de"),
		N_("; încercări de readucere a antenei:"),
		N_(", următoarea peste"),
		N_("Antena nu se rotește"),
		N_("Când receptorul mută antena spre alt satelit, aici se vede drumul ei, gradele și cât mai are de "
			"mers."),
		N_("Antena e pe"),
		N_("Rotirea antenei"),
		N_("De la"),
		N_("Acum (estimat)"),
		N_("Până la"),
		N_("Motorul merge, timpul nu se poate estima"),
		N_("Aproape gata, se așteaptă semnalul pe satelitul nou"),
		N_("Oprire singură în"),
		N_("unghi motor"),
		N_("grade"),
		N_("Est"),
		N_("Vest"),
		N_("Poziția din timpul mersului este estimată: motorul nu o raportează."),
		N_("Locul antenei nu e stabilit, deci „Mergi la satelit” nu pornește. Alege-l mai întâi."),
		N_("Comenzile motorului se dau numai dintr-un browser conectat cu codul de pe televizor. Aici se "
			"vede numai rotirea."),
		N_("Ecranul „Rotirea antenei” e deschis și pe televizor: comenzile de acolo și de aici merg la "
			"același motor."),
		N_("are motor   |   Pas:"),
		N_("Pas:"),
		N_("Limitele sunt oprite. Pornesc singure la ieșire."),
		N_("Limite: pornite"),
		N_("Limite: nu se știe"),
		N_("Mod de probă: se pot trimite numai oprirea și pornirea limitelor."),
		N_("La prima comandă programul de pe televizor se oprește; pornește la loc când apeși Termină sau "
			"închizi pagina."),
		N_("Semnalul nu se poate citi pe acest tuner."),
		N_("Semnal pe"),
		N_(": recepționat, calitate"),
		N_(": recepționat"),
		N_(": fără semnal"),
		N_("Poziția trebuie să fie un număr între 1 și 255."),
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
