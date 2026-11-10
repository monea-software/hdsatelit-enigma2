# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsDiagnostic.py: diagnosticul pornirii. Codurile de eroare, ce se arata pe ecranul de pe televizor
# (Screens/HdsPazaModel.py), in pagina web /paza-model (paza_model_web.py) si in textul de copiat, si o comanda pentru
# calea de rezerva din enigma2.sh, cand interfata nu porneste.
#
# Ecranul apare singur numai cand pornirea nu reuseste (paza de model: alt receptor sau amprenta necitita). Cand
# receptorul porneste normal nu se arata nimic in plus; datele raman de citit oricand in meniu (Informatii despre
# sistem > Diagnosticul pornirii) si in interfata web (/paza-model).
#
# CODURILE (CODURI): stabile, un numar nu se schimba si nu se refoloseste; un caz nou primeste un numar nou. Forma: E si
# trei cifre (incape pe afisajul din fata de patru cifre). Ultimele doua cifre spun cheia pazei de model
# (Components/HdsPazaModel.CHEI_AMPRENTA): 01 cip, 02 boxtype, 03 eticheta, 04 hw, 05 partitii, 06 kernel, 07 emmc.
# E1xx = valoarea s-a citit si e alta decat cea ceruta; E2xx = valoarea nu s-a putut citi (E203 si E207 nu exista: o
# eticheta lipsa si un disc nelistat nu hotarasc nimic). E199 = o cheie pe care tabelul nu o stie inca. E290 = regulile
# imaginii stricate; E291 = garda de la pornire nu a lasat verdict (fisierul de stare lipseste). E3xx = interfata nu
# porneste (modul sigur din enigma2.sh si calea de rezerva); E306-E308 sunt pastrate pentru calea de rezerva.
# Codul principal (unul singur, mare pe ecran si pe afisaj): E290, apoi cheile in ordinea ORDINE_CHEI, apoi E199,
# E291 si codurile E3xx. Aceeasi ordine o are fragmentul de shell din enigma2.sh, care citeste acelasi fisier de stare.
#
# Fara date personale: amprenta pazei nu pastreaza adresa MAC; jurnalele din pagina trec prin faraDatePersonale
# (fara randurile cu parole, chei sau jetonul web, adresele MAC mascate, fara numere de serie).
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau modulul pazei lor (M) si radacina lor.
# Rulat ca program (python3 HdsDiagnostic.py --rezerva [--limba de] [--radacina /]) scrie textul diagnosticului, in
# limba receptorului, pentru calea de rezerva (imaginea pe ecran si pagina web fara enigma2).

import os
import re
import sys

def _t(text):
	return traduce(text)


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textele din tabele se traduc la folosire."""
	return text


# ------------------------------------------------------------------ codurile

GRUPA_ALT_RECEPTOR = "alt-receptor"
GRUPA_NECITIT = "necitit"
GRUPA_INTERFATA = "interfata"

# (cod, grupa, ce inseamna); textul se traduce la folosire
CODURI = (
	("E101", GRUPA_ALT_RECEPTOR, N_("Procesorul receptorului nu este cel pentru care e făcut software-ul.")),
	("E102", GRUPA_ALT_RECEPTOR, N_("Driverul spune alt tip de placă decât cel pentru care e făcut software-ul.")),
	("E103", GRUPA_ALT_RECEPTOR, N_("Eticheta din memoria receptorului spune alt tip de placă.")),
	("E104", GRUPA_ALT_RECEPTOR, N_("Placa receptorului (antetul de fabrică) este alta.")),
	("E105", GRUPA_ALT_RECEPTOR, N_("Partițiile din memoria receptorului sunt așezate altfel.")),
	("E106", GRUPA_ALT_RECEPTOR, N_("Partiția nucleului sau a sistemului e în alt loc sau are altă mărime.")),
	("E107", GRUPA_ALT_RECEPTOR, N_("Memoria internă are altă mărime decât la modelul pentru care e software-ul.")),
	("E108", GRUPA_ALT_RECEPTOR, N_("The device tree identifies another receiver model.")),
	("E199", GRUPA_ALT_RECEPTOR, N_("O altă valoare a receptorului nu se potrivește.")),
	("E201", GRUPA_NECITIT, N_("Procesorul nu s-a putut citi: driverul procesorului nu s-a încărcat.")),
	("E202", GRUPA_NECITIT, N_("Tipul plăcii nu s-a putut citi: driverul plăcii nu s-a încărcat.")),
	("E204", GRUPA_NECITIT, N_("Placa nu s-a putut citi din antetul de fabrică.")),
	("E205", GRUPA_NECITIT, N_("Partițiile nu s-au putut citi din linia de pornire.")),
	("E206", GRUPA_NECITIT, N_("Partiția nucleului sau a sistemului nu s-a găsit.")),
	("E208", GRUPA_NECITIT, N_("Modelul plăcii nu s-a putut citi.")),
	("E290", GRUPA_NECITIT, N_("Semnul receptorului din software este stricat.")),
	("E291", GRUPA_NECITIT, N_("Verificarea de la pornire nu a dat niciun rezultat.")),
	("E301", GRUPA_INTERFATA, N_("Interfața a căzut de mai multe ori la pornire și a pornit în modul sigur.")),
	("E302", GRUPA_INTERFATA, N_("Interfața cade și în modul sigur.")),
	("E303", GRUPA_INTERFATA, N_("Interfața nu pornește deloc.")),
	("E304", GRUPA_INTERFATA, N_("Driverele receptorului lipsesc sau nu s-au încărcat.")),
	("E305", GRUPA_INTERFATA, N_("Interfața nu a apărut în 5 minute: s-a blocat la pornire.")),
	("E309", GRUPA_INTERFATA, N_("Interfața s-a oprit la pornire din alt motiv.")),
)
_GRUPE = dict((c, g) for c, g, _x in CODURI)
_TEXTE = dict((c, t) for c, _g, t in CODURI)

COD_ALTA_CHEIE = "E199"
COD_REGULI_STRICATE = "E290"
COD_FARA_VERDICT = "E291"
COD_MOD_SIGUR = "E301"
COD_MOD_SIGUR_CADE = "E302"

# cheile pazei de model in ordinea codului principal si ultimele doua cifre ale codului lor
ORDINE_CHEI = ("cip", "boxtype", "model_id", "eticheta", "emmc", "hw", "partitii", "kernel")
CIFRE_CHEI = {"cip": "01", "boxtype": "02", "eticheta": "03", "hw": "04", "partitii": "05", "kernel": "06",
	"emmc": "07", "model_id": "08"}
# cheile care nu au cod de valoare necitita (o valoare lipsa nu hotaraste nimic): raman E1xx. Modelul placii lipsa (model_id gol)
# poate opri numai regulile cu model_id= (E208); fara el se hotaraste numai dupa un model citit (E108).
FARA_NECITIT = ("eticheta", "emmc")

# titlurile grupelor (aceleasi texte ca mesajul pazei de model, Components/HdsPazaModel.mesajPornire)
TITLURI = {
	GRUPA_ALT_RECEPTOR: N_("Software pentru alt receptor"),
	GRUPA_NECITIT: N_("Receptorul nu poate fi recunoscut"),
	GRUPA_INTERFATA: N_("Interfața nu pornește"),
}
TITLU_MENIU = "Diagnosticul pornirii"

FORUM = "https://stb.hdsatelit.com/forum/"
FORUM_SCURT = "stb.hdsatelit.com/forum"
EMAIL = "contact@hdsatelit.com"
PAGINA_WEB = "/paza-model"

# modul sigur (enigma2.sh, Components/HdsModSigur.py): semnul din RAM si pragul treptei a doua
SEMN_MOD_SIGUR = "/tmp/hds-mod-sigur"
PRAG_MOD_SIGUR_CADE = 3
# codurile lasate de calea de rezerva (tools/hds-rezerva.sh, datele ferestrei in $HDS_REZERVA_DOSAR/date.txt,
# randul „coduri=E304 E309”), pentru ecran si pagina web
FISIER_CODURI_REZERVA = "/tmp/hds-rezerva/date.txt"
# nodurile driverelor care lipseau inainte de enigma2 (randuri „lipsa=/dev/fb0”), scrise de tools/hds-rezerva.sh in
# $HDS_REZERVA_DOSAR/drivere: E304
FISIER_DRIVERE_LIPSA = "/tmp/hds-rezerva/drivere"

# marimea textului din codul QR (Components/HdsQr: cel mult 213 octeti)
MAX_QR = 200


def textCod(cod):
	"""Ce inseamna un cod, tradus („” pentru un cod necunoscut)"""
	return _t(_TEXTE.get(cod, ""))


def grupaCod(cod):
	return _GRUPE.get(cod, GRUPA_ALT_RECEPTOR if (cod or "").startswith("E1") else GRUPA_NECITIT)


def titluCod(cod):
	"""Titlul ecranului pentru codul principal"""
	return _t(TITLURI[grupaCod(cod)])


def codCheie(cheie, gasit):
	"""Codul unei nepotriviri a pazei: E1xx (citit si altul) sau E2xx (necitit); E199 pentru o cheie necunoscuta"""
	cifre = CIFRE_CHEI.get(cheie)
	if cifre is None:
		return COD_ALTA_CHEIE
	if not gasit and cheie not in FARA_NECITIT:
		return "E2" + cifre
	return "E1" + cifre


# ------------------------------------------------------------------ modulul pazei si sursele

def _m(M=None):
	if M is not None:
		return M
	from Components import HdsPazaModel
	return HdsPazaModel


def _citesteText(cale, maxim=4096):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim).decode("utf-8", "replace")
	except (IOError, OSError, ValueError):
		return None


def reguliStricate(v, M=None):
	"""True cand fisierul de reguli exista, dar nu se intelege (citesteReguli da {}), sau garda a scris
	reguli=stricate"""
	M = _m(M)
	reguli = v.get("reguli")
	if reguli is None or v.get("stare") == M.STARE_NU_SE_APLICA:
		return False
	return not M.reguliValide(reguli)


def coduriPaza(v, M=None):
	"""Codurile pazei de model pentru un verdict (Components/HdsPazaModel.verdict()), in ordinea codului principal;
	[] cand receptorul se potriveste sau paza nu se aplica"""
	M = _m(M)
	if v.get("stare") != M.STARE_NEPOTRIVIT:
		return []
	if reguliStricate(v, M):
		return [COD_REGULI_STRICATE]
	nep = dict((c, g) for c, _a, g in (v.get("nepotriviri") or []))
	rez = [codCheie(c, nep[c]) for c in ORDINE_CHEI if c in nep]
	if [c for c in nep if c not in CIFRE_CHEI]:
		rez.append(COD_ALTA_CHEIE)
	return rez or [COD_ALTA_CHEIE]


def driverePierdute(cale=None):
	"""Nodurile driverelor care lipseau inainte de enigma2 (FISIER_DRIVERE_LIPSA), ca lista; [] fara fisier"""
	text = _citesteText(cale or FISIER_DRIVERE_LIPSA, 1024) or ""
	return [r[6:].strip()[:40] for r in text.split("\n") if r.startswith("lipsa=") and r[6:].strip()][:8]


def coduriInterfata(cale_semn=None, cale_rezerva=None, mediu=None, cale_drivere=None):
	"""Codurile E3xx, in ordinea numerelor: modul sigur (semnul din RAM sau HDS_MOD_SIGUR=1 al acestui proces),
	driverele lipsa inainte de enigma2 (E304) si cele lasate de calea de rezerva din enigma2.sh"""
	rez = []
	if driverePierdute(cale_drivere):
		rez.append("E304")
	mediu = os.environ if mediu is None else mediu
	semn = _citesteText(cale_semn or SEMN_MOD_SIGUR)
	if semn is not None or mediu.get("HDS_MOD_SIGUR") == "1":
		rez.append(COD_MOD_SIGUR)
		randuri = (semn or "").split("\n")
		if sum(1 for r in randuri if r.startswith("oprire=")) >= PRAG_MOD_SIGUR_CADE or \
				any(r.startswith("automat=") for r in randuri):
			rez.append(COD_MOD_SIGUR_CADE)
	text = _citesteText(cale_rezerva or FISIER_CODURI_REZERVA, 4096) or ""
	# in datele ferestrei numai randul coduri= (celelalte campuri nu sunt coduri); un fisier cu un singur rand de coduri
	# se citeste intreg
	randuri = [r for r in text.split("\n") if r.startswith("coduri=")]
	if randuri:
		text = randuri[0]
	for cod in re.findall(r"\bE3[0-9]{2}\b", text):
		if cod in _TEXTE and cod not in rez:
			rez.append(cod)
	return sorted(rez)


def coduri(v, M=None, cale_semn=None, cale_rezerva=None, mediu=None, cale_drivere=None):
	"""Toate codurile, in ordinea codului principal: paza de model, garda fara verdict (E291), interfata (E3xx)"""
	M = _m(M)
	rez = coduriPaza(v, M)
	if v.get("stare") != M.STARE_NU_SE_APLICA and v.get("sursa") == "acum" and not reguliStricate(v, M):
		rez.append(COD_FARA_VERDICT)
	for cod in coduriInterfata(cale_semn, cale_rezerva, mediu, cale_drivere):
		if cod not in rez:
			rez.append(cod)
	return rez


def codPrincipal(v, M=None, **k):
	"""Primul cod (cel mare pe ecran si pe afisaj), sau "" """
	c = coduri(v, M, **k)
	return c[0] if c else ""


# ------------------------------------------------------------------ randurile

STARE_BUN = "bun"
STARE_RAU = "rau"
STARE_NECITIT = "necitit"
STARE_AVERTISMENT = "avertisment"
STARE_INFO = "info"

# numele scurte pentru televizor (coloana din stanga a tabelului)
ETICHETE_TV = {
	"cip": N_("Procesor"),
	"boxtype": N_("Tip placă (driver)"),
	"model_id": N_("Modelul plăcii"),
	"eticheta": N_("Etichetă"),
	"hw": N_("Placă (HW)"),
	"emmc": N_("Memorie internă"),
	"kernel": N_("Nucleu și sistem"),
	"partitii": N_("Partiții"),
	"tunere": N_("Tunere"),
	"pornire": N_("Model (încărcător)"),
}
ORDINE_TV = ("cip", "boxtype", "model_id", "eticheta", "hw", "emmc", "kernel", "partitii")
# valorile numai informative din amprenta (Components/HdsPazaModel.informatiiPornire, cand exista): ce spune
# incarcatorul receptorului in /proc/cmdline si driverul
CHEI_INFORMATIVE = ("pornire_masina", "pornire_oem", "pornire_model", "ram", "tip_tunere", "chipset",
	"versiune_drivere")
MAX_VALOARE_TV = 34


def scurt(text, maxim=MAX_VALOARE_TV):
	"""Textul taiat la `maxim` semne, cu trei puncte la sfarsit cand e mai lung"""
	text = text or ""
	return text if len(text) <= maxim else text[:maxim - 3].rstrip() + "..."


def _faraDisc(text):
	"""'mmcblk0p12 16384 KiB, mmcblk0p16' -> 'p12 16384 KiB, p16' (pe televizor)"""
	return re.sub(r"\bmmcblk0(p[0-9]+)", r"\1", text or "")


def _stari(v):
	nep = dict((c, g) for c, _a, g in (v.get("nepotriviri") or []))
	avert = dict((c, g) for c, _a, g in (v.get("avertismente") or []))
	return nep, avert


def randuri(v, M=None, tv=False):
	"""[{cheie, eticheta, citit, cerut, stare, cod}] pentru fiecare cheie a pazei si tunere. Valorile sunt cele dupa
	care s-a dat verdictul (la pornire, ale garzii). tv=True: numele scurte, partitiile numai ca numar si prima
	diferenta, nucleul fara numele discului, valorile taiate."""
	M = _m(M)
	reguli = v.get("reguli") or {}
	a = v.get("amprenta") or {}
	a_v = v.get("amprenta_verdict") or a
	nep, avert = _stari(v)
	nu_se_aplica = v.get("stare") == M.STARE_NU_SE_APLICA
	etichete = M.eticheteAmprenta()
	liber = locLiber() if not nu_se_aplica else None
	rez = []
	for cheie in (ORDINE_TV if tv else tuple(M.CHEI_AMPRENTA)):
		if cheie == "emmc" and not a_v.get("emmc_kib") and M.limiteEmmc(reguli) is None:
			continue
		cerut = "" if nu_se_aplica else M.asteptat_text(reguli, cheie)
		if cheie == "emmc" and M.limiteEmmc(reguli) is None:
			cerut = ""
		citit = M.valoareGasita(a_v, cheie) if cheie in M.CHEI_AMPRENTA else ""
		if cheie in nep:
			citit = nep[cheie] or citit
		elif cheie in avert:
			citit = avert[cheie] or citit
		if cheie == "eticheta":
			cale = M.caleDinEticheta(a_v.get("eticheta"))
			if citit and cale:
				citit = "%s (%s)" % (citit, cale)
		if cheie in nep:
			stare = STARE_RAU if (nep[cheie] or cheie in FARA_NECITIT) else STARE_NECITIT
			cod = codCheie(cheie, nep[cheie])
		elif cheie in avert:
			stare, cod = STARE_AVERTISMENT, ""
		elif nu_se_aplica or (cheie in ("eticheta", "model_id") and not citit):
			# modelul placii necitit hotaraste numai cu model_id= in reguli (atunci e in nepotriviri, E208)
			stare, cod = STARE_INFO, ""
		elif not citit:
			# necitit, dar fara sa hotarasca (treapta a doua): nu se arata ca potrivit
			stare, cod = STARE_AVERTISMENT, ""
		else:
			stare, cod = STARE_BUN, ""
		if v.get("partitii_informative") and cheie in ("kernel", "partitii"):
			cerut, stare, cod = "", STARE_INFO, ""
		if not citit:
			citit = _t("lipsește (nu se verifică)") if cheie in ("eticheta", "model_id") else _t("nu s-a putut citi")
		if cheie == "emmc" and liber:
			citit = _t("%(marime)s, liber %(liber)d MiB") % {"marime": citit, "liber": liber[0]}
		if tv:
			if cheie == "partitii":
				citit, cerut = _partitiiTv(M, a_v, {} if v.get("partitii_informative") else reguli,
					cheie in nep or cheie in avert, citit, cerut)
			elif cheie == "kernel":
				citit, cerut = _faraDisc(citit), _faraDisc(cerut)
			citit, cerut = scurt(citit), scurt(cerut)
		rez.append({"cheie": cheie, "eticheta": _t(ETICHETE_TV[cheie]) if tv else etichete.get(cheie, cheie),
			"citit": citit, "cerut": cerut, "stare": stare, "cod": cod})
	tunere = [M.curat(t, 40) for t in (a.get("tunere") or [])]
	if tv:
		text_tunere = scurt("%d: %s" % (len(tunere), ", ".join(tunere))) if tunere else _t("niciunul găsit")
	else:
		text_tunere = ", ".join(tunere) if tunere else _t("niciunul găsit")
	if a.get("tip_tunere") and tunere:
		text_tunere = "%s (%s)" % (text_tunere, a.get("tip_tunere"))
		if tv:
			text_tunere = scurt(text_tunere)
	rez.append({"cheie": "tunere", "eticheta": _t(ETICHETE_TV["tunere"]) if tv else _t("Tunere"),
		"citit": text_tunere, "cerut": "", "stare": STARE_INFO, "cod": ""})
	# ce spune incarcatorul receptorului (MODEL=, OEM=, mem= din /proc/cmdline), cand exista
	pornire = ", ".join(x for x in (a.get("pornire_model") or a.get("pornire_masina"), a.get("pornire_oem"),
		a.get("ram")) if x)
	if pornire:
		# numai informativ: ce spune incarcatorul nu se compara (pe Viper 4K V20 MODEL=1G, nu numele modelului)
		rez.append({"cheie": "pornire", "eticheta": _t(ETICHETE_TV["pornire"]), "citit": scurt(pornire) if tv else
			pornire, "cerut": "", "stare": STARE_INFO, "cod": ""})
	return rez


def _partitiiTv(M, a, reguli, diferit, citit, cerut):
	"""Partitiile pe televizor: numarul lor si, cand difera, prima intrare care nu se potriveste"""
	lista = a.get("partitii_lista") or []
	if not lista:
		return citit, cerut
	ceruta = M.partitiiDinReguli(reguli.get("partitions")) or [] if reguli else []
	n_citit = _t("%d partiții") % len(lista)
	n_cerut = (_t("%d partiții") % len(ceruta)) if ceruta else cerut
	# paza cere numai primele partitii (HdsPazaModel._diferente): una in plus nu e o nepotrivire
	if ceruta and not diferit and len(lista) > len(ceruta):
		n_cerut = _t("cel puțin %s") % n_cerut
	if not diferit or not cerut:
		return n_citit, n_cerut
	try:
		loc, asteptat, gasit = M.primaDiferenta(cerut, a.get("partitii") or "")
	except Exception:
		return n_citit, n_cerut
	return (_t("locul %(loc)d: %(intrare)s") % {"loc": loc, "intrare": gasit},
		_t("locul %(loc)d: %(intrare)s") % {"loc": loc, "intrare": asteptat})


def software(v):
	"""„HD Satelit 0.6.8 pentru Octagon SF8008 4K UHD (sf8008)”; "" fara reguli"""
	reguli = v.get("reguli") or {}
	if not reguli:
		return ""
	versiune = v.get("versiune") or reguli.get("version") or "?"
	model = reguli.get("model") or "?"
	mb = reguli.get("machinebuild") or ""
	text = _t("HD Satelit %(versiune)s pentru %(model)s") % {"versiune": versiune, "model": model}
	return "%s (%s)" % (text, mb) if mb else text


# ------------------------------------------------------------------ locul liber si aparatele USB

DOSAR_USB = "/sys/bus/usb/devices"
# puntea USB a discului M.2 intern al Octagon SF8008 Supreme (acelasi semn ca stratul OE-A pentru Supreme)
LOC_PUNTE_M2 = "1-1.4"


def locLiber(cale="/"):
	"""(liber, total) in MiB pentru sistemul pornit, sau None"""
	try:
		st = os.statvfs(cale)
	except (OSError, AttributeError):
		return None
	return (st.f_bavail * st.f_frsize // (1024 * 1024), st.f_blocks * st.f_frsize // (1024 * 1024))


def _citesteUsb(dosar, nume):
	t = _citesteText(os.path.join(dosar, nume), 64)
	return re.sub(r"[^A-Za-z0-9 ._-]", "", (t or "").strip())[:32]


def aparateUsb(dosar=None):
	"""Aparatele USB ca idVendor:idProduct (fara numere de serie), cel mult 12"""
	dosar = dosar or DOSAR_USB
	rez = []
	try:
		nume = sorted(os.listdir(dosar))
	except OSError:
		return rez
	for n in nume:
		if ":" in n:
			continue
		v, p = _citesteUsb(os.path.join(dosar, n), "idVendor"), _citesteUsb(os.path.join(dosar, n), "idProduct")
		if re.match(r"^[0-9a-fA-F]{4}$", v) and re.match(r"^[0-9a-fA-F]{4}$", p):
			rez.append("%s:%s" % (v.lower(), p.lower()))
	return rez[:12]


def discInternM2(dosar=None):
	"""True cand puntea discului M.2 intern (JMicron, la locul USB 1-1.4) exista"""
	return "jmicron" in _citesteUsb(os.path.join(dosar or DOSAR_USB, LOC_PUNTE_M2), "manufacturer").lower()


# ------------------------------------------------------------------ textele

def rugaminte():
	return _t("Fă o poză acestui ecran și trimite-o pe forumul unde ai găsit software-ul sau la %s.") % EMAIL


def ceFaci():
	return _t("Software-ul nu scrie nimic în memoria receptorului. Pune la loc software-ul potrivit cu un stick USB, "
		"cum arată producătorul receptorului.")


def notaSlot(v):
	"""Nota slotului pornit, numai la o pornire de multiboot trecuta (Components/HdsPazaModel: nota_slot)"""
	text = v.get("nota_slot")
	return _t(text) if text else ""


def textAdresa(adresa):
	if adresa:
		return _t("Toate datele, în interfața web: %s") % adresa
	return _t("Toate datele, în interfața web a receptorului, la pagina %s") % PAGINA_WEB


def textQr(adresa, v=None, M=None):
	"""Textul codului QR: adresa paginii web (cand receptorul are adresa in retea), altfel un e-mail spre noi cu codul
	in subiect; "" daca nu incape"""
	if adresa:
		return adresa if len(adresa.encode("utf-8")) <= MAX_QR else ""
	if v is None:
		return ""
	t = adresaMail(v, M, cu_corp=False)
	return t if len(t.encode("utf-8")) <= MAX_QR else ""


def subiect(v, M=None):
	"""„HD Satelit E102 sf8008 0.6.8” (subiectul e-mailului)"""
	reguli = v.get("reguli") or {}
	parti = ["HD Satelit"]
	cod = codPrincipal(v, M)
	if cod:
		parti.append(cod)
	for x in (reguli.get("machinebuild"), v.get("versiune") or reguli.get("version")):
		if x:
			parti.append(x)
	return " ".join(parti)


def _url(text):
	try:
		from urllib.parse import quote
	except ImportError:  # Python 2 (probele vechi)
		from urllib import quote
	return quote(text.encode("utf-8"), safe="")


def adresaMail(v, M=None, cu_corp=True, maxim=1800):
	"""mailto: spre contact@hdsatelit.com cu subiectul si (cu_corp) datele de baza ale diagnosticului"""
	t = "mailto:%s?subject=%s" % (EMAIL, _url(subiect(v, M)))
	if cu_corp:
		corp = _url("\n".join(dateCheie(v, M)) + "\n")
		while len(t) + 6 + len(corp) > maxim and "%0A" in corp:
			corp = corp[:corp.rfind("%0A", 0, len(corp) - 3) + 3]
		t += "&body=" + corp
	return t


def dateCheie(v, M=None, adresa=""):
	"""Randurile „cheie=valoare” ale diagnosticului (aceleasi in orice limba, pentru noi): codurile, software-ul,
	verdictul si valorile citite fata de cele cerute"""
	M = _m(M)
	reguli = v.get("reguli") or {}
	a = v.get("amprenta") or {}
	a_v = v.get("amprenta_verdict") or a
	toate = coduri(v, M)
	r = ["cod=%s" % (toate[0] if toate else "-"), "coduri=%s" % (" ".join(toate) or "-")]
	r.append("software=HD Satelit %s" % (v.get("versiune") or reguli.get("version") or "?"))
	if v.get("versiune_baza"):
		r.append("imagine_baza=HD Satelit %s" % v["versiune_baza"])
	r.append("model=%s" % (reguli.get("model") or "-"))
	r.append("machinebuild=%s" % (reguli.get("machinebuild") or "-"))
	r.append("stare=%s" % v.get("stare", ""))
	r.append("treapta=%s" % v.get("treapta", 1))
	r.append("sursa=%s" % v.get("sursa", ""))
	nep, avert = _stari(v)
	for cheie in M.CHEI_AMPRENTA:
		gasit = nep.get(cheie) if cheie in nep else avert.get(cheie) if cheie in avert else M.valoareGasita(a_v, cheie)
		semn = "NU" if cheie in nep else "avertisment" if cheie in avert else "da"
		r.append("%s=%s | cerut=%s | potrivit=%s" % (cheie, gasit or "-", M.asteptat_text(reguli, cheie) or "-", semn))
	if a_v.get("partitii"):
		r.append("partitii_citite=%s" % a_v.get("partitii"))
	if reguli.get("partitions"):
		r.append("partitii_cerute=%s" % reguli.get("partitions"))
	for cheie, nume in (("eticheta", "eticheta_bruta"), ("board_revision", "board_revision"), ("dt", "dt")):
		if a.get(cheie):
			r.append("%s=%s" % (nume, M.curat(a.get(cheie), 120)))
	r.append("tunere=%s" % (", ".join(a.get("tunere") or []) or "-"))
	for cheie in CHEI_INFORMATIVE:
		if a.get(cheie):
			r.append("%s=%s" % (cheie, M.curat(str(a.get(cheie)), 80)))
	lipsa = driverePierdute()
	if lipsa:
		r.append("drivere_lipsa=%s" % " ".join(lipsa))
	liber = locLiber()
	if liber:
		r.append("loc_liber=%d MiB din %d MiB (/)" % liber)
	usb = aparateUsb()
	if usb:
		r.append("usb=%s" % " ".join(usb))
		r.append("disc_intern_m2=%s" % ("da" if discInternM2() else "nu"))
	try:
		r.append("nucleu=%s" % M.curat(os.uname()[2], 60))
	except Exception:
		pass
	if adresa:
		r.append("adresa=%s" % adresa)
	return r


def textComplet(v, M=None, adresa="", jurnale_=None):
	"""Textul de copiat (butonul „Copiază tot”, /paza-model/text): titlul, codurile cu ce inseamna, rugamintea, apoi
	randurile „cheie=valoare” si, daca sunt date, jurnalele"""
	M = _m(M)
	toate = coduri(v, M)
	titlu = titluCod(toate[0]) if toate else _t(TITLU_MENIU)
	r = ["HD Satelit: %s" % _t(TITLU_MENIU), titlu]
	for cod in toate:
		r.append("%s: %s" % (cod, textCod(cod)))
	if v.get("stare") == M.STARE_NEPOTRIVIT:
		a = v.get("amprenta_verdict") or v.get("amprenta") or {}
		r.append(M.textPentru(v.get("reguli") or {}, v.get("versiune")))
		r.append(M.textAlTau(a, v.get("reguli"), v.get("nepotriviri")))
		pagina = M.paginaModel(a)
		if pagina:
			r.append(pagina)
	if toate:
		r.append(rugaminte())
		r.append(_t("Forumul: %s") % FORUM)
	if notaSlot(v):
		r.append(notaSlot(v))
	r.append("")
	r.extend(dateCheie(v, M, adresa))
	for titlu_j, text_j in jurnale_ or []:
		r.append("")
		r.append("----- %s -----" % titlu_j)
		r.append(text_j.rstrip("\n"))
	return "\n".join(r) + "\n"


# ------------------------------------------------------------------ jurnalele (numai pe receptorul oprit de paza)

MAX_RANDURI_JURNAL = 40
MAX_RANDURI_RAPORT = 30
MAX_OCTETI_JURNAL = 64 * 1024
MAX_OCTETI_RAPORT = 512 * 1024
JURNAL_CADERI = "/home/root/logs/hds-caderi.log"
DOSAR_CADERI = "/home/root/logs"
ASCUNS = "<ascuns>"
ADRESA_ASCUNSA = "<adresa ascunsa>"
# orice adresa cu schema (http://, rtsp://, si forma codata http%3a// din referintele de serviciu), intreaga
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*(?:://|%3[Aa]//|%3[Aa]%2[Ff]%2[Ff])[^\s\"'<>]*")
# utilizator:parola@gazda fara schema
_CU_PAROLA = re.compile(r"[^\s/:@\"'<>]+:[^\s/@\"'<>]*@[^\s/\"'<>]+")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# adresele MAC: cu despartitoare, si 12 cifre hexa langa mac/ether/hwaddr/bdaddr
_MAC = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{2}([:-])[0-9A-Fa-f]{2}(?:\1[0-9A-Fa-f]{2}){4}(?![0-9A-Fa-f])")
_MAC_LIPIT = re.compile(r"((?:mac|ether|hwaddr|bdaddr|address)[^0-9A-Za-z]{0,3})[0-9A-Fa-f]{12}(?![0-9A-Fa-f])", re.I)
# IPv6 (intreg, sau scurtat cu ::; adresele fe80:: au MAC-ul inauntru)
_IPV6 = re.compile(r"(?<![0-9A-Za-z:])(?:(?:[0-9A-Fa-f]{1,4}:){5,7}[0-9A-Fa-f]{1,4}|"
	r"[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6}::(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?|"
	r"::[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})(?![0-9A-Za-z:])")
# siruri lungi de cifre hexa (chei, cuvinte de control, serii, sume)
_HEXA_LUNG = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{16,}(?![0-9A-Za-z])")
# randurile care se scot intregi: parole, chei, jetonul, utilizatori, retele Wi-Fi, serii, chei CAM
_RAND_SCOS = re.compile(r"pass(word|wd)?|parol|token|jeton|secret|\bkey|cheie|psk|\bpin\b|auth|user|login|"
	r"utilizator|ssid|wpa|wifi|wlan.*(essid|network)|serial|\bS/N\b|\bsn\s*[=:]|cpuid|chipid|chip_id|die.?id|\buuid\b|"
	r"\bcid\b|\bcw\b|control.?word|\bbiss|\becm\b|\bemm\b|cookie|session", re.I)
_NUCLEU = re.compile(r"error|fail|unknown symbol|disagrees|version magic|invalid|not found|hi_|hi-|dvb|frontend|"
	r"tuner|insmod|modprobe|oops|panic|segfault|enigma2", re.I)


def faraDatePersonale(text):
	"""Textul bun de pus pe un forum public: fara randurile cu parole, chei, jetonul web, utilizatori, retele Wi-Fi,
	serii sau chei CAM; orice adresa URL, utilizator:parola@, e-mail si IPv6 ascunse intregi; adresele MAC mascate;
	sirurile lungi de cifre hexa ascunse."""
	randuri_ = []
	for rand in (text or "").split("\n"):
		if _RAND_SCOS.search(rand):
			continue
		rand = _URL.sub(ADRESA_ASCUNSA, rand)
		rand = _CU_PAROLA.sub(ADRESA_ASCUNSA, rand)
		rand = _EMAIL.sub(ASCUNS, rand)
		rand = _MAC.sub("xx:xx:xx:xx:xx:xx", rand)
		rand = _MAC_LIPIT.sub(lambda m: m.group(1) + "xxxxxxxxxxxx", rand)
		rand = _IPV6.sub(ASCUNS, rand)
		rand = _HEXA_LUNG.sub(ASCUNS, rand)
		randuri_.append(rand)
	text = "\n".join(randuri_)
	try:
		from Components.HdsModSigur import _faraSecrete
		text = _faraSecrete(text)
	except Exception:
		pass
	return text


def _citesteCoada(cale, octeti):
	try:
		if os.path.islink(cale):
			return None
		marime = os.path.getsize(cale)
		with open(cale, "rb") as f:
			if marime > octeti:
				f.seek(marime - octeti)
			date = f.read(octeti)
	except (IOError, OSError):
		return None
	return date.decode("utf-8", "replace").replace("\r", "")


def _citesteInceput(cale, octeti):
	try:
		if os.path.islink(cale):
			return None
		with open(cale, "rb") as f:
			date = f.read(octeti)
	except (IOError, OSError):
		return None
	return date.decode("utf-8", "replace").replace("\r", "")


def _coada(cale, n=MAX_RANDURI_JURNAL):
	text = _citesteCoada(cale, MAX_OCTETI_JURNAL)
	if text is None:
		return None
	return "\n".join(text.rstrip("\n").split("\n")[-n:])


def _ultimaCadere(dosar):
	try:
		nume = [n for n in os.listdir(dosar) if n.startswith("enigma2_crash_") and n.endswith(".log")]
	except OSError:
		return None
	cai = [os.path.join(dosar, n) for n in nume if not os.path.islink(os.path.join(dosar, n))]
	if not cai:
		return None
	return max(cai, key=lambda c: (os.path.getmtime(c), c))


def ultimaEroare(text, n=MAX_RANDURI_RAPORT):
	"""Din raportul de eroare: numai jurnalul enigma2 (fara sumele fisierelor si lista pachetelor din raportul lui
	bsod.cpp, Components/HdsModSigur.textBrutRaport), apoi ultimul Traceback pana la eroare; fara Traceback, ultimele
	randuri ale jurnalului. Cel mult n randuri."""
	if "<enigma2crashlog>" in (text or ""):
		try:
			from Components.HdsModSigur import textBrutRaport
			text = textBrutRaport(text)
		except Exception:
			return ""
	randuri_ = (text or "").rstrip("\n").split("\n")
	inceput = None
	for i, rand in enumerate(randuri_):
		if "Traceback (most recent call last)" in rand:
			inceput = i
	if inceput is None:
		return "\n".join(randuri_[-n:])
	bloc = [randuri_[inceput]]
	for rand in randuri_[inceput + 1:]:
		bloc.append(rand)
		if re.match(r"^[ <0-9.>]*[A-Za-z_][A-Za-z0-9_.]*(Error|Exception|Exit|Interrupt|Warning)\b", rand):
			break
	return "\n".join(bloc[-n:])


def _nucleu(n=MAX_RANDURI_JURNAL):
	"""Randurile nucleului despre drivere si erori (dmesg), cel mult n; None daca nu se poate citi"""
	try:
		import subprocess
		p = subprocess.Popen(["dmesg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		iesire, _e = p.communicate()
	except Exception:
		return None
	randuri_ = [r for r in iesire.decode("utf-8", "replace").split("\n") if _NUCLEU.search(r)]
	return "\n".join(randuri_[-n:])


def jurnale(dosar=None, cale_caderi=None, cu_nucleu=True):
	"""[(titlu, text)]: opririle interfetei (hds-caderi.log), ultima eroare din ultimul raport de eroare si randurile
	nucleului despre drivere, fiecare numai sfarsitul si trecut prin faraDatePersonale. Numai pentru receptorul oprit
	de paza (acolo nu se poate asocia niciun browser, deci /jurnale-* nu se pot deschide)."""
	rez = []
	t = _coada(cale_caderi or JURNAL_CADERI)
	if t:
		rez.append((_t("Opririle interfeței"), faraDatePersonale(t)))
	c = _ultimaCadere(dosar or DOSAR_CADERI)
	if c:
		t = ultimaEroare(_citesteInceput(c, MAX_OCTETI_RAPORT) or "")
		if t:
			rez.append((_t("Ultima eroare a interfeței") + " (%s)" % os.path.basename(c), faraDatePersonale(t)))
	if cu_nucleu:
		t = _nucleu()
		if t:
			rez.append((_t("Nucleul: driverele și erorile"), faraDatePersonale(t)))
	return rez


# ------------------------------------------------------------------ calea de rezerva (fara enigma2)

CALE_SETARI = "/etc/enigma2/settings"
DOSAR_PO = "/usr/share/enigma2/po"
LIMBI = ('ar', 'ca', 'cs', 'da', 'de', 'el', 'en', 'es', 'et', 'fi', 'fr', 'fy', 'hr', 'hu', 'is', 'it', 'lt', 'lv', 'nl', 'no', 'pl', 'pt', 'ro', 'ru', 'sk', 'sl', 'sr', 'sv', 'tr', 'uk')


def _codLimba(valoare):
	valoare = str(valoare or "").strip()
	if not re.fullmatch(r"[A-Za-z]{2,3}(?:[_-][A-Za-z0-9-]+)?", valoare):
		return "en"
	limba = re.split("[_-]", valoare, 1)[0].lower()
	return limba if limba in LIMBI else "en"


def _limbaSetari(cale=None):
	text = _citesteText(CALE_SETARI if cale is None else cale, 1 << 20) or ""
	valoare = ""
	for rand in text.splitlines():
		if rand.startswith("config.osd.language="):
			valoare = rand.split("=", 1)[1]
	return _codLimba(valoare)


# Textele engleze raman disponibile si fara fisierele .mo.
TEXTE_ENGLEZA = {
	"%(ce)s: așteptat %(asteptat)s, dar nu s-a putut citi.": "%(ce)s: expected %(asteptat)s, but it could not be read.",
	"%(ce)s: așteptat %(asteptat)s, găsit %(gasit)s.": "%(ce)s: expected %(asteptat)s, found %(gasit)s.",
	"%(ce)s: pe locul %(loc)d așteptat %(asteptat)s, găsit %(gasit)s.": "%(ce)s: at position %(loc)d expected %(asteptat)s, found %(gasit)s.",
	"%(marime)s, liber %(liber)d MiB": "%(marime)s, %(liber)d MiB free",
	"%d partiții": "%d partitions",
	"Acest software (HD Satelit %(versiune)s) este pentru receptorul %(model)s (placa %(hw)s, procesor %(cip)s).": "This software (HD Satelit %(versiune)s) is for the %(model)s receiver (board %(hw)s, processor %(cip)s).",
	"Acest software este pentru receptorul %(model)s (placa %(hw)s, procesor %(cip)s).": "This software is for the %(model)s receiver (board %(hw)s, processor %(cip)s).",
	"Acest software nu spune pentru ce receptor este făcut, deci poate fi pentru alt tip de receptor. Software-ul HD Satelit spune asta de la versiunea 0.1.6; o versiune mai veche sau o imagine de la altcineva se instalează numai cu un stick USB, cum arată producătorul receptorului.": "This software does not say which receiver it is made for, so it may be for a different type of receiver. HD Satelit software includes this information from version 0.1.6 onwards; an older version or an image from someone else can only be installed using a USB stick, following the receiver manufacturer's instructions.",
	"Acum toate valorile se potrivesc.": "All values match now.",
	"Alte coduri: %s.": "Other codes: %s.",
	"Ca să nu strice receptorul, software-ul nu scrie nimic în memoria lui și nu pornește mai departe.": "So as not to damage the receiver, the software writes nothing to its memory and does not start any further.",
	"Cerut de software": "Required by the software",
	"Citit pe receptor": "Read on the receiver",
	"Cod": "Code",
	"Coduri:": "Codes:",
	"Da": "Yes",
	"Dacă nu se schimbă nimic, aici apare în curând codul de diagnostic.": "If nothing changes, the diagnostic code appears here soon.",
	"Datele despre receptor din acest software sunt stricate sau de altă versiune, deci nu se poate verifica pentru ce receptor este.": "The receiver data in this software is damaged or from another version, so we cannot check which receiver it is for.",
	"De obicei pornirea durează sub un minut.": "The start usually takes less than a minute.",
	"Detalii": "Details",
	"Diagnosticul pornirii": "Startup diagnostics",
	"Driverele receptorului lipsesc sau nu s-au încărcat.": "The receiver's drivers are missing or did not load.",
	"Driverul plăcii nu s-a încărcat, deci tipul plăcii nu s-a putut citi și nu se poate dovedi că acest software este pentru el.": "The board driver was not loaded, so the board type could not be read and it cannot be proven that this software is for it.",
	"Driverul spune alt tip de placă decât cel pentru care e făcut software-ul.": "The driver reports a different board type from the one the software is made for.",
	"Eticheta din memoria receptorului spune alt tip de placă.": "The label in the receiver's memory names another board type.",
	"Eticheta din memoria receptorului: %s": "Label in the receiver's memory: %s",
	"Etichetă": "Label",
	"Fișierele software-ului s-au schimbat după verificare. Verifică-l din nou.": "The software files changed after the check. Check it again.",
	"Forumul: %s": "Forum: %s",
	"Fă o poză acestui ecran și trimite-o pe forumul unde ai găsit software-ul sau la %s.": "Take a photo of this screen and send it to the forum where you found the software or to %s.",
	"Fă o poză acestui ecran și trimite-o pe forumul unde ai găsit software-ul sau la contact@hdsatelit.com.": "Take a photo of this screen and send it to the forum where you found the software or to contact@hdsatelit.com.",
	"HD Satelit %(versiune)s pentru %(model)s": "HD Satelit %(versiune)s for %(model)s",
	"HD Satelit pornește…": "HD Satelit is starting…",
	"Imaginea pentru receptorul tău și pașii de instalare: %s": "The image for your receiver and installation steps: %s",
	"Interfața a căzut de mai multe ori la pornire și a pornit în modul sigur.": "The interface crashed several times at startup and started in safe mode.",
	"Interfața cade și în modul sigur.": "The interface crashes in safe mode too.",
	"Interfața nu a apărut în 5 minute: s-a blocat la pornire.": "The interface did not appear within 5 minutes: it got stuck at startup.",
	"Interfața nu pornește": "The interface does not start",
	"Interfața nu pornește deloc.": "The interface does not start at all.",
	"Interfața s-a oprit la pornire din alt motiv.": "The interface stopped at startup for another reason.",
	"Interfața se încearcă din nou peste %d minute.": "The interface is tried again in %d minutes.",
	"Memoria internă (eMMC)": "Internal memory (eMMC)",
	"Memoria internă are altă mărime decât la modelul pentru care e software-ul.": "The internal memory has a different size from the model the software is for.",
	"Memorie internă": "Internal memory",
	"Model (încărcător)": "Model (bootloader)",
	"Modelul plăcii": "Board model",
	"Modelul plăcii nu s-a putut citi.": "The board model could not be read.",
	"Model neconfirmat: software pentru testeri": "Unconfirmed model: software for testers",
	"Modelul acesta nu este încă confirmat pe un receptor adevărat. Software-ul pornește, dar e numai pentru testeri: trimite-ne valorile de mai jos sau fișa receptorului, ca să îl putem confirma.": "This model is not yet confirmed on a real receiver. The software starts, but it is only for testers: send us the values below or the receiver sheet, so we can confirm it.",
	"Nu": "No",
	"Nu am putut citi procesorul sau partițiile receptorului, deci nu se poate dovedi că acest software este pentru el.": "The processor or the partitions of the receiver could not be read, so it cannot be proven that this software is for it.",
	"Nu s-a instalat nimic pe receptor.": "Nothing has been installed on the receiver.",
	"Nucleu și sistem": "Kernel and system",
	"Nucleul: driverele și erorile": "Kernel: drivers and errors",
	"O altă valoare a receptorului nu se potrivește.": "Another value of the receiver does not match.",
	"OK sau EXIT închide fereastra.": "OK or EXIT closes the window.",
	"Opririle interfeței": "Interface stops",
	"Partiția nucleului sau a sistemului e în alt loc sau are altă mărime.": "The kernel or system partition is in another place or has another size.",
	"Partiția nucleului sau a sistemului nu s-a găsit.": "The kernel or system partition was not found.",
	"Partiții": "Partitions",
	"Partițiile din memoria receptorului sunt așezate altfel.": "The partitions in the receiver's memory are laid out differently.",
	"Pagina receptorului tău": "Your receiver's page",
	"Partițiile din memorie": "Partitions in memory",
	"Partițiile nu s-au putut citi din linia de pornire.": "The partitions could not be read from the boot command line.",
	"Partițiile nucleului și ale sistemului": "Kernel and system partitions",
	"Pasul pornirii: %s": "Start step: %s",
	"Paza de model nu se aplică aici": "The model guard does not apply here",
	"Placa (antetul partiției deviceinfo)": "Board (header of the deviceinfo partition)",
	"Placa nu s-a putut citi din antetul de fabrică.": "The board could not be read from the factory header.",
	"Placa receptorului (antetul de fabrică) este alta.": "The receiver's board (factory header) is a different one.",
	"Placă (HW)": "Board (HW)",
	"Pornirea a reușit. Câteva valori diferă de cele așteptate: modelul nu este încă confirmat.": "The start succeeded. Some values differ from the expected ones: the model is not confirmed yet.",
	"Pornirea a reușit: receptorul se potrivește cu software-ul.": "The start succeeded: the receiver matches the software.",
	"Pornirea durează mai mult decât de obicei…": "The start takes longer than usual…",
	"Pornirea s-a oprit înainte de interfață, la pasul arătat pe afișaj.": "The start stopped before the interface, at the step shown on the display.",
	"Procesor": "Processor",
	"Procesorul": "Processor",
	"Procesorul nu s-a putut citi: driverul procesorului nu s-a încărcat.": "The processor could not be read: the processor driver did not load.",
	"Procesorul receptorului nu este cel pentru care e făcut software-ul.": "The receiver's processor is not the one the software is made for.",
	"Pune la loc software-ul potrivit cu un stick USB, cum arată producătorul receptorului (la Amiko: Maintenance Mode).": "Put the right software back with a USB stick, as the receiver's manufacturer describes (on Amiko: Maintenance Mode).",
	"Pune la loc software-ul potrivit cu un stick USB, cum arată producătorul receptorului (la Octagon: ține apăsat Standby pe receptor la pornire, apoi Recovery From USB).": "Put the right software back with a USB stick, as the receiver's manufacturer describes (on Octagon: hold Standby on the receiver while switching on, then Recovery From USB).",
	"Pune la loc software-ul potrivit cu un stick USB, cum arată producătorul receptorului (la Uclan Ustym 4K PRO: butonul RECOVERY din spate).": "Put the right software back with a USB stick, as the receiver manufacturer describes (on Uclan Ustym 4K PRO: the rear RECOVERY button).",
	"Receptorul acesta se potrivește: procesorul, placa și partițiile sunt cele cerute de software.": "This receiver matches: the processor, the board and the partitions are the ones the software requires.",
	"Receptorul este cel potrivit": "This is the right receiver",
	"Receptorul nu poate fi recunoscut": "The receiver cannot be recognized",
	"Receptorul tău: %(model)s, placa %(hw)s, procesor %(cip)s.": "Your receiver: %(model)s, board %(hw)s, processor %(cip)s.",
	"Semnul receptorului din software este stricat.": "The receiver mark in the software is damaged.",
	"Software pentru alt receptor": "Software for another receiver",
	"Software-ul care rulează nu are semnul receptorului (de exemplu în emulatorul de pe calculator), deci paza de model nu verifică nimic.": "The running software has no receiver mark (for example in the emulator on the computer), so the model guard checks nothing.",
	"Software-ul este stricat sau schimbat: %s nu are suma de control așteptată. Copiază-l din nou pe stick.": "The software is damaged or changed: %s does not have the expected checksum. Copy it to the stick again.",
	"Software-ul este stricat sau schimbat: %s nu au suma de control așteptată. Copiază-l din nou pe stick.": "The software is damaged or changed: %s do not have the expected checksum. Copy it to the stick again.",
	"Software-ul nu scrie nimic în memoria receptorului. Pune la loc software-ul potrivit cu un stick USB, cum arată producătorul receptorului.": "The software writes nothing to the receiver's memory. Put the right software back with a USB stick, as the receiver's manufacturer describes.",
	"Software-ul nu se poate instala": "The software cannot be installed",
	"Săgețile sus și jos aleg, OK confirmă, EXIT înseamnă Nu.": "Use the up and down arrows to choose, OK to confirm, EXIT means No.",
	"Tip placă (driver)": "Board type (driver)",
	"Tipul plăcii din eticheta receptorului": "Board type in the receiver label",
	"Tipul plăcii nu s-a putut citi: driverul plăcii nu s-a încărcat.": "The board type could not be read: the board driver did not load.",
	"Tipul plăcii spus de driver": "Board type reported by the driver",
	"Toate datele, de copiat, din calculator sau telefon:": "All the data, to copy, from a computer or phone:",
	"Toate datele, în interfața web a receptorului, la pagina %s": "All the data, in the receiver's web interface, on the page %s",
	"Toate datele, în interfața web: %s": "All the data, in the web interface: %s",
	"Tunere": "Tuners",
	"Ultima eroare a interfeței": "Last interface error",
	"Verificarea de la pornire nu a dat niciun rezultat.": "The check at startup gave no result.",
	"cel mult %s": "at most %s",
	"cel puțin %s": "at least %s",
	"lipsește (nu se verifică)": "missing (not checked)",
	"locul %(loc)d: %(intrare)s": "place %(loc)d: %(intrare)s",
	"model necunoscut": "unknown model",
	"necunoscut": "unknown",
	"necunoscută": "unknown",
	"niciunul găsit": "none found",
	"nimic": "nothing",
	"nu s-a putut citi": "could not be read",
	"nu se poate instala: este pentru alt tip de receptor": "cannot be installed: it is for another type of receiver",
	"nu se poate instala: fișierele sunt stricate": "cannot be installed: the files are damaged",
	"nu se poate instala: fișierele sunt stricate sau schimbate": "cannot be installed: the files are damaged or changed",
	"nu se poate instala: poate fi pentru alt tip de receptor": "cannot be installed: it may be for another type of receiver",
	"nu se poate instala: receptorul nu se poate verifica": "cannot be installed: the receiver cannot be checked",
	"pentru acest receptor, se verifică la OK": "for this receiver, checked at OK",
	"un receptor %(tip)s (de exemplu %(model)s)": "a %(tip)s receiver (for example %(model)s)",
	"un receptor %s": "a %s receiver",
	"un receptor cu memoria internă mai mare": "a receiver with a larger internal memory",
	"un receptor cu memoria internă mai mare (de exemplu %s)": "a receiver with a larger internal memory (for example %s)",
	"un receptor cu memoria internă mai mică": "a receiver with a smaller internal memory",
	"un receptor cu memoria internă mai mică (de exemplu %s)": "a receiver with a smaller internal memory (for example %s)",
}

TEXT_SLOT_NECITIT = N_("The boot slot could not be read; partitions do not block startup.")
TEXT_SLOT_CITIT = N_("Boot partitions read from the running slot; they do not identify the receiver.")
TEXTE_ROMANA = {
	TEXT_SLOT_NECITIT: "Slotul de pornire nu s-a putut citi; partițiile nu opresc pornirea.",
	TEXT_SLOT_CITIT: "Partițiile sunt citite din slotul pornit; ele nu identifică receptorul.",
	"The device tree identifies another receiver model.": "Arborele dispozitivelor arată alt model de receptor.",
	"This receiver matches the hardware required by the software.": "Receptorul acesta are componentele cerute de software.",
}


def _traducator(limba, dosar_po=DOSAR_PO):
	"""Catalogul limbii alese, cu engleza la un text lipsa sau netradus."""
	limba = _codLimba(limba)
	if limba == "ro":
		return lambda text: TEXTE_ROMANA.get(text, text)
	catalog = None
	try:
		import gettext
		catalog = gettext.translation("enigma2", dosar_po, languages=[limba]).gettext
	except Exception:
		pass

	def tr(text):
		tradus = catalog(text) if catalog else text
		return tradus if tradus and tradus != text else TEXTE_ENGLEZA.get(text, text)
	return tr


def limbaDiagnostic(limba=None, cale_setari=None, dosar_po=None):
	"""Limba salvata si traducatorul ei, fara sa schimbe limba globala a interfetei."""
	limba = _limbaSetari(cale_setari) if limba is None else _codLimba(limba)
	return limba, _traducator(limba, DOSAR_PO if dosar_po is None else dosar_po)


_LIMBA_DIAGNOSTIC = None
_TRADUCATOR_DIAGNOSTIC = None


def pregatesteLimba(limba=None, cale_setari=None, dosar_po=None):
	global _LIMBA_DIAGNOSTIC, _TRADUCATOR_DIAGNOSTIC
	_LIMBA_DIAGNOSTIC, _TRADUCATOR_DIAGNOSTIC = limbaDiagnostic(limba, cale_setari, dosar_po)
	return _LIMBA_DIAGNOSTIC


def traduce(text):
	if not text:
		return text or ""
	if _TRADUCATOR_DIAGNOSTIC is None:
		pregatesteLimba()
	return _TRADUCATOR_DIAGNOSTIC(text)


def _instaleazaLimba(limba, dosar=DOSAR_PO):
	pregatesteLimba(limba, dosar_po=dosar)


TEXT_PAGINA_REZERVA = N_("Toate datele, de copiat, din calculator sau telefon:")
TEXT_REINCERCARE = N_("Interfața se încearcă din nou peste %d minute.")
TEXT_CODURI = N_("Coduri:")
TEXTE_PORNIRE = {
	"porneste": N_("HD Satelit pornește…"),
	"pasul": N_("Pasul pornirii: %s"),
	"obisnuit": N_("De obicei pornirea durează sub un minut."),
	"lent": N_("Pornirea durează mai mult decât de obicei…"),
	"lent2": N_("Dacă nu se schimbă nimic, aici apare în curând codul de diagnostic."),
	"E306": N_("Pornirea s-a oprit înainte de interfață, la pasul arătat pe afișaj."),
}


def texteRezervaLimba(limba, dosar_po=DOSAR_PO):
	"""Textele rezervei din acelasi catalog ca ecranul, cu baza engleza."""
	tr = _traducator(limba, dosar_po)
	rez = {"titlu_E1": tr(TITLURI[GRUPA_ALT_RECEPTOR]), "titlu_E2": tr(TITLURI[GRUPA_NECITIT]),
		"titlu_E3": tr(TITLURI[GRUPA_INTERFATA]),
		"rugaminte": tr("Fă o poză acestui ecran și trimite-o pe forumul unde ai găsit software-ul sau la %s.") % EMAIL,
		"pagina": tr(TEXT_PAGINA_REZERVA), "reincercare": tr(TEXT_REINCERCARE), "coduri": tr(TEXT_CODURI),
		"forum": FORUM, "email": EMAIL}
	for cod, _g, text in CODURI:
		rez[cod] = tr(text)
	rez.update((cheie, tr(text)) for cheie, text in TEXTE_PORNIRE.items())
	return rez


class _TexteRezerva(dict):
	"""TEXTE_REZERVA["de"] sau .get("de"): texteRezervaLimba, citite la prima cerere a limbii (o singura sursa: po)"""

	def __missing__(self, limba):
		if limba not in LIMBI:
			raise KeyError(limba)
		v = texteRezervaLimba(limba)
		self[limba] = v
		return v

	def get(self, limba, implicit=None):
		try:
			return self[limba]
		except KeyError:
			return implicit

	def __contains__(self, limba):
		return limba in LIMBI

	def keys(self):
		return list(LIMBI)


TEXTE_REZERVA = _TexteRezerva()


def texteRezerva(cod, limba=None, dosar_po=DOSAR_PO, cale_setari=None):
	"""Textele unui cod in limba salvata, sau in cea ceruta explicit pentru probe."""
	_limba, tr = limbaDiagnostic(limba, cale_setari, dosar_po)
	return {"titlu": tr(TITLURI[grupaCod(cod)]), "cod": cod, "text": tr(_TEXTE.get(cod, "")),
		"rugaminte": tr("Fă o poză acestui ecran și trimite-o pe forumul unde ai găsit software-ul sau la %s.") % EMAIL,
		"forum": FORUM, "email": EMAIL, "pagina": tr("Toate datele, în interfața web: %s")}


def main(argv=None):
	argv = list(sys.argv[1:] if argv is None else argv)

	def optiune(nume, implicit):
		if nume in argv:
			i = argv.index(nume)
			if i + 1 < len(argv):
				return argv[i + 1]
		return implicit
	if "--texte" in argv:
		t = texteRezerva(optiune("--texte", ""), optiune("--limba", "") or None)
		for cheie in ("titlu", "cod", "text", "rugaminte", "forum", "email", "pagina"):
			sys.stdout.write("%s=%s\n" % (cheie, t[cheie].replace("\n", " ")))
		return 0
	if "--rezerva" not in argv and "--cod" not in argv:
		sys.stdout.write("folosire: HdsDiagnostic.py --rezerva [--limba ro] [--radacina /] | --cod | --texte E305\n")
		return 2
	aici = os.path.dirname(os.path.abspath(__file__))
	sys.path.insert(0, os.path.dirname(aici))
	limba = optiune("--limba", "") or _limbaSetari()
	pregatesteLimba(limba)
	from Components import HdsPazaModel as M
	radacina = optiune("--radacina", None)
	v = M.verdict(radacina)
	if "--cod" in argv:
		sys.stdout.write(codPrincipal(v, M) + "\n")
		return 0
	sys.stdout.write(textComplet(v, M))
	return 0


if __name__ == "__main__":
	sys.exit(main())
